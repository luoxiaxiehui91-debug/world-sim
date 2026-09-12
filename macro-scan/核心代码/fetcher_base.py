#!/usr/bin/env python3
"""
fetcher_base.py — macro-scan 新数据源通用适配层（R1 加固基类 + v1.1 日档回填）

为所有新接入源（World Bank / Statistics of the World / Frankfurter /
CoinGecko / OpenSanctions bulk data / USGS / UK Carbon / Binance+Kraken /
MarketAux+Currents+Sugra / HDX）提供统一能力：
  - 固定间隔自限速（rate_interval 秒/请求；当前为固定 sleep，非真·令牌桶）
  - 统一重试 + 指数退避（429/5xx 重试；4xx 客户端错误不重试直接降级）
  - 失败降级（collect 异常 / 请求最终失败 → 返回 None 或空，不抛，不阻断调度）
  - as-of 时间戳（save_json 自动写入 updated 字段）
  - JSON 原子写（.tmp + os.replace）
  - 契约版本化（save_json 自动注入 _schema_version；缺失 status 时补默认值并告警）
  - 保留良值（load_previous_good + _is_good 谓词，降级时保留上次良值不覆盖）
  - 配置回退（load_config_with_fallback 统一取代各 fetcher 的 ImportError 块）
  - 日档回填（RetryOnMissingMixin：collect 返回空时进程内重试，opt-in）

非商用内部系统：商用授权约束不适用，仅需代码注释标注数据来源（礼貌规范）。
"""
import os
import json
import time
import tempfile
import datetime
import logging
import requests

# 日志目录（B：可用环境变量 MACRO_SCAN_LOG_DIR 覆盖；默认沿用容器内约定路径）
LOG_DIR = os.environ.get("MACRO_SCAN_LOG_DIR", "/var/log/macro-scan")


def _probe_writable(d: str) -> bool:
    """探测目录是否可写（创建 + 写探针 + 删除）。"""
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


def resolve_log_dir(data_dir: str = "") -> str:
    """解析一个**可写**的日志目录（A：不可写时回退，避免非 root 环境 PermissionError）。

    优先级：LOG_DIR（默认 /var/log/macro-scan，可被 MACRO_SCAN_LOG_DIR 覆盖）
            → <data_dir>/logs → <tempdir>/macro-scan-logs

    回退时输出 WARNING 留痕（项目红线：任何兜底必须留痕）。
    全部不可写时返回 LOG_DIR —— 保持原行为，由 FileHandler 显式抛出，不静默吞掉。
    """
    candidates = [LOG_DIR]
    if data_dir:
        candidates.append(os.path.join(data_dir, "logs"))
    candidates.append(os.path.join(tempfile.gettempdir(), "macro-scan-logs"))

    for d in candidates:
        if _probe_writable(d):
            if d != LOG_DIR:
                logging.getLogger("fetcher").warning(
                    "日志目录 %s 不可写，已回退至 %s（可用环境变量 MACRO_SCAN_LOG_DIR 显式指定）",
                    LOG_DIR, d,
                )
            return d

    logging.getLogger("fetcher").error("所有候选日志目录均不可写：%s", candidates)
    return LOG_DIR


class Status:
    """契约状态枚举（集中定义，向前兼容旧字符串值）。"""
    OK = "ok"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    RETRY_LIMIT = "retry_limit"
    SKIPPED = "skipped"
    KEY_MISSING = "key_missing"


class RetryOnMissingMixin:
    """Mixin: 日档缺失时进程内自动重试（opt-in per fetcher）。

    挂载方式 — 子类继承时放在 FetcherBase 前面即启用：
        class MyFetcher(RetryOnMissingMixin, FetcherBase):
            ...

    可覆写类属性：
        retry_max_attempts: int = 3     # 含首次，最多尝试次数
        retry_cooldown_seconds: int = 600  # 重试间隔（秒）

    行为：run() 返回 None 时，等待 cooldown 后重新调用 super().run()。
    所有重试在同一个进程内完成——scheduler 后台不等待子进程退出，安全无阻塞。

    仅当 collect() 返回非 None 才算"成功拿到数据"。
    不重试"返回了数据但数据可能偏旧"的情况（那是 Stale 检测的活，非本 mixin 职责）。
    """
    retry_max_attempts: int = 3
    retry_cooldown_seconds: int = 600  # 10 分钟

    def run(self):
        for attempt in range(self.retry_max_attempts):
            result = super().run()
            if result is not None:
                return result
            if attempt < self.retry_max_attempts - 1:
                self.logger.info(
                    f"[{self.name}] 日档回填：collect 返回空，"
                    f"{self.retry_cooldown_seconds}s 后重试 "
                    f"({attempt + 1}/{self.retry_max_attempts})"
                )
                time.sleep(self.retry_cooldown_seconds)
        self.logger.warning(
            f"[{self.name}] 日档回填：{self.retry_max_attempts} 次尝试均失败"
        )
        return None


class FetcherBase:
    # ── 契约元数据（子类覆写） ────────────────────────────────
    name = "base"
    rate_interval = 1.0      # 固定间隔：每次请求间隔（秒）
    max_retries = 3
    base_backoff = 2.0       # 退避基数（秒），第 n 次等待 base_backoff * 2^n
    _SCHEMA_VERSION = "1.0"  # 输出契约版本（save_json 自动注入）

    feeds_grv = False        # 是否直接喂 geo_risk_vector（GRV 消费方读取）
    schedule = None          # 建议调度槽（如 "0606"），仅元数据，调度器仍读 scheduler.py
    output_file = None       # 该 fetcher 的输出文件名（供 load_previous_good 使用）

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.proxies = None   # 子类可覆盖为 {"https": PROXY_URL}（部分源直连不可达时）
        self.logger = self._get_logger()

    # ── 日志 ──────────────────────────────────────────────────
    def _get_logger(self):
        logger = logging.getLogger(f"fetcher.{self.name}")
        if not logger.handlers:
            log_dir = resolve_log_dir(self.data_dir)
            h = logging.FileHandler(os.path.join(log_dir, f"{self.name}.log"), encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(h)
            logger.setLevel(logging.INFO)
        return logger

    # ── 网络：固定间隔限速 + 重试退避 ────────────────────────
    def request(self, url, params=None, headers=None, timeout=15):
        """带固定间隔限速 + 重试退避的 GET。最终失败返回 None（不抛）。

        - 每次请求前 sleep(rate_interval)（固定间隔，非真·令牌桶）。
        - 429 / 5xx：指数退避重试（max_retries 次）。
        - 4xx（非 429）：客户端错误，不重试，直接返回 None（避免对 404 空转重试）。
        """
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                if self.rate_interval > 0:
                    time.sleep(self.rate_interval)
                r = requests.get(url, params=params, headers=headers, timeout=timeout,
                                 proxies=self.proxies)
                if r.status_code == 429 or r.status_code >= 500:
                    wait = self.base_backoff * (2 ** attempt)
                    self.logger.warning(
                        f"[{self.name}] HTTP {r.status_code} @ {url} 退避 {wait}s (尝试 {attempt+1}/{self.max_retries})"
                    )
                    time.sleep(wait)
                    last_exc = RuntimeError(f"HTTP {r.status_code}")
                    continue
                if 400 <= r.status_code < 500:
                    self.logger.warning(
                        f"[{self.name}] 客户端错误 {r.status_code} @ {url}，不重试"
                    )
                    return None
                return r
            except Exception as e:
                wait = self.base_backoff * (2 ** attempt)
                self.logger.warning(
                    f"[{self.name}] 请求异常 {e} @ {url} 退避 {wait}s (尝试 {attempt+1}/{self.max_retries})"
                )
                time.sleep(wait)
                last_exc = e
        self.logger.error(f"[{self.name}] 请求最终失败 @ {url}: {last_exc}")
        return None

    # ── 写盘：原子写 + 契约版本化 + status 兜底 ───────────────
    def save_json(self, filename: str, payload: dict) -> str:
        """原子写 JSON：注入 _schema_version、兜底 status、追加 updated 时间戳。"""
        os.makedirs(self.data_dir, exist_ok=True)
        payload = dict(payload)
        if "_schema_version" not in payload:
            payload["_schema_version"] = self._SCHEMA_VERSION
        if "status" not in payload:
            self.logger.warning(
                f"[{self.name}] 输出缺 status 字段，补默认 {Status.UNAVAILABLE}"
            )
            payload["status"] = Status.UNAVAILABLE
        payload.setdefault(
            "updated", datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        )
        path = os.path.join(self.data_dir, filename)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        self.logger.info(f"[{self.name}] 写入 {path}")
        return path

    # ── 配置回退（取代各 fetcher 重复的 ImportError 块）────────
    @staticmethod
    def _workspace_root():
        return os.environ.get(
            "OPENCLAW_WORKSPACE",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )

    @staticmethod
    def default_data_dir():
        return os.path.join(FetcherBase._workspace_root(), "data")

    @staticmethod
    def load_config_with_fallback(primary, fallbacks):
        """统一配置回退。

        primary: 需要从 optim_config 导入的变量名列表。
        fallbacks: {变量名: 默认值 或 (默认值, 环境变量名)}。
        成功从 optim_config 导入全部 primary 则返回 {名: 值}；
        optim_config 不可导入（ImportError）则回退到 fallbacks（支持 env 覆盖）。
        """
        try:
            import optim_config as oc
            return {n: getattr(oc, n) for n in primary}
        except ImportError:
            out = {}
            for n, fb in fallbacks.items():
                if isinstance(fb, (tuple, list)) and len(fb) == 2:
                    default, env_var = fb
                    out[n] = os.environ.get(env_var, default) if env_var else default
                else:
                    out[n] = fb
            return out

    # ── 保留良值（降级时不覆盖上次良值）─────────────────────
    def _is_good(self, data: dict) -> bool:
        """判断 data 是否为可保留的'良值'。默认 ok-only；子类按需覆写。

        实际语义（以源码 _load_previous_good 为准）：
          - earthquake/crypto_extra/hdx/sanctions：ok-only
          - energy：ok/partial 且 grid_carbon_risk 非空
          - news：ok/partial
        """
        return data.get("status") == Status.OK

    # 良值 staleness 上限（秒）。超过此时限的旧值不再用于降级。
    # 子类可覆写：月频源（fao/china_meso）可设为 35天；I15 事件源可设为 4小时。
    _MAX_STALE_SECONDS: int = 48 * 3600  # 默认 48 小时

    def load_previous_good(self) -> dict | None:
        """读上次良值（经 _is_good 判定）。无则返回 None。降级时保留旧值。
        若良值的 updated 字段超过 _MAX_STALE_SECONDS，视为过期，返回 None。
        """
        import datetime as _dt
        if not self.output_file:
            return None
        path = os.path.join(self.data_dir, self.output_file)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        if not self._is_good(data):
            return None
        updated_str = data.get("updated", "")
        if updated_str:
            try:
                updated_dt = _dt.datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                now = _dt.datetime.now(_dt.timezone.utc)
                age_s = (now - updated_dt).total_seconds()
                if age_s > self._MAX_STALE_SECONDS:
                    self.logger.warning(
                        f"[{self.name}] 上次良值已过期 {age_s/3600:.1f}h（上限 {self._MAX_STALE_SECONDS/3600:.0f}h），丢弃降级"
                    )
                    return None
            except Exception:
                pass  # 时间戳格式异常时不拦截，保持旧行为
        return data

    # ── 采集（子类实现） ─────────────────────────────────────
    def collect(self):
        """子类实现：返回 dict（将被 save_json 包裹 updated）。"""
        raise NotImplementedError

    def run(self):
        try:
            result = self.collect()
            if result is None:
                self.logger.warning(f"[{self.name}] collect 返回空")
            return result
        except Exception as e:
            self.logger.error(f"[{self.name}] collect 异常: {e}")
            return None
