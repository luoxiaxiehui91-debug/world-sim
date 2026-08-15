"""
observability.py — 可观测性计数器（T1-2）

纯只读日志模块，不改任何决策数据。所有写操作强隔离：出错只跳过自己，绝不阻断调用方。

功能：
  Heartbeat  — 写入 .scheduler_heartbeat，外部脚本可据此判断调度器存活
  Job 计数   — 按任务名累计当日触发次数
  合成器统计 — 触发次数 / LLM消耗 / ntfy发送 / 抑制原因（从 synthesis_log.db 读取）
  日终清洗   — 写入 data/observability_YYYY-MM-DD.json

使用：
  from observability import observe
  observe.heartbeat()
  observe.job_fired("grv_update")
"""

import os
import json
import time
import datetime
import sqlite3
import threading

# ══════════════════════════════════════════════════════════════════════════════
# 配置常量
# ══════════════════════════════════════════════════════════════════════════════
try:
    from optim_config import DATA_DIR
except ImportError:
    DATA_DIR = os.environ.get("DATA_DIR", "/workspace/data")

HEARTBEAT_FILE = os.path.join(DATA_DIR, ".scheduler_heartbeat")
OBS_PREFIX     = os.path.join(DATA_DIR, "observability")
SYNTHESIS_DB   = os.path.join(DATA_DIR, "news.db")  # synthesis_log 表在 news.db 中
FLUSH_INTERVAL = 60  # 每 60 秒刷盘一次


# ══════════════════════════════════════════════════════════════════════════════
# Observability 单例
# ══════════════════════════════════════════════════════════════════════════════
class _Observability:
    """零风险计数器。所有方法 try/except 包裹，绝不抛异常到调用方。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._today = ""
        self._jobs = {}        # job_name -> count
        self._last_flush = 0

    # ── 心跳 ────────────────────────────────────────────────────────────────
    def heartbeat(self) -> None:
        """写入当前时间戳到心跳文件。外部脚本可检测文件 age > 5min → 调度器异常。"""
        try:
            ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(ts + "\n")
            self._auto_flush()
        except Exception:
            pass

    # ── 任务计数 ────────────────────────────────────────────────────────────
    def job_fired(self, job_name: str) -> None:
        """记录一次任务触发。线程安全。"""
        try:
            with self._lock:
                self._jobs[job_name] = self._jobs.get(job_name, 0) + 1
            self._auto_flush()
        except Exception:
            pass

    # ── 刷盘 ────────────────────────────────────────────────────────────────
    def _auto_flush(self) -> None:
        """节流刷盘：距上次 FLUSH_INTERVAL 秒内不重复写。"""
        now = time.time()
        if now - self._last_flush < FLUSH_INTERVAL:
            return
        self._last_flush = now
        self._flush()

    def _flush(self) -> None:
        """写入当日 observability JSON（覆盖写，因为本质是计数器快照）。"""
        try:
            today = datetime.date.today().isoformat()
            path = f"{OBS_PREFIX}_{today}.json"

            with self._lock:
                jobs_copy = dict(self._jobs)

            record = {
                "date": today,
                "updated": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "scheduler": {
                    "heartbeat_ok": True,
                    "total_jobs_fired": sum(jobs_copy.values()),
                    "by_job": jobs_copy,
                },
            }

            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# 公共接口：读取合成器统计（从 synthesis_log 表，纯只读）
# ══════════════════════════════════════════════════════════════════════════════
def read_synthesizer_stats(today: str = None) -> dict:
    """
    从 synthesis_log 表读取当日合成器统计。纯读，不改任何数据。

    返回：
      {
        "staging_mode": true/false/null,
        "rules_evaluated": N,
        "rules_triggered": N,
        "llm_calls": N,
        "ntfy_sends": N,
        "suppressed_by_staging": N,
        "suppressed_by_limit": N,
        "suppressed_by_cooldown": N,
      }
    若 news.db 不存在或表不存在，返回零计数字典。
    """
    if today is None:
        today = datetime.date.today().isoformat()
    # 时区口径（P0-2 家族修复）：today 是本地（北京）日期，PG session 是 UTC，
    # 必须转 UTC 区间，否则早上 8 点前的轮次（UTC 仍在昨日）被漏计为 0。
    try:
        from zoneinfo import ZoneInfo
        _local = datetime.datetime.fromisoformat(today + "T00:00:00").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        _utc_start = _local.astimezone(datetime.timezone.utc)
        _utc_end = _utc_start + datetime.timedelta(days=1)
    except Exception:
        _utc_start = datetime.datetime.fromisoformat(today + "T00:00:00")
        _utc_end = _utc_start + datetime.timedelta(days=1)

    empty = {
        "staging_mode": None,
        "rules_evaluated": 0,
        "rules_triggered": 0,
        "llm_calls": 0,
        "ntfy_sends": 0,
        "suppressed_by_staging": 0,
        "suppressed_by_limit": 0,
        "suppressed_by_cooldown": 0,
    }

    try:
        import pg_read as _pg
        conn = _pg.connect()
        if conn is None:
            return empty

        # 检查 synthesis_log 表是否存在（PG news schema）
        cur = conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='news' AND table_name='synthesis_log'"
        )
        if not cur.fetchone():
            conn.close()
            return empty

        # 当日评估数（E0-C: SQLite log_time 列本不存在（历史恒 0），改用 triggered_at）
        cur = conn.execute(
            "SELECT COUNT(*) as n FROM news.synthesis_log WHERE triggered_at >= %s AND triggered_at < %s",
            (_utc_start, _utc_end)
        )
        evaluated = cur.fetchone()["n"]

        # 触发数：SQLite resonance_ok 列本不存在（历史恒 0），PG 无此列 → 按今日触发总数计
        cur = conn.execute(
            "SELECT COUNT(*) as n FROM news.synthesis_log WHERE triggered_at >= %s AND triggered_at < %s",
            (_utc_start, _utc_end)
        )
        triggered = cur.fetchone()["n"]

        # LLM 调用数
        cur = conn.execute(
            "SELECT COUNT(*) as n FROM news.synthesis_log "
            "WHERE triggered_at >= %s AND triggered_at < %s AND llm_success = 1",
            (_utc_start, _utc_end)
        )
        llm_calls = cur.fetchone()["n"]

        # ntfy 发送数
        cur = conn.execute(
            "SELECT COUNT(*) as n FROM news.synthesis_log "
            "WHERE triggered_at >= %s AND triggered_at < %s AND ntfy_success = 1",
            (_utc_start, _utc_end)
        )
        ntfy_sends = cur.fetchone()["n"]

        # 各抑制原因计数
        suppress = {}
        cur = conn.execute(
            "SELECT suppress_reason, COUNT(*) as n FROM news.synthesis_log "
            "WHERE triggered_at >= %s AND triggered_at < %s AND suppress_reason IS NOT NULL "
            "GROUP BY suppress_reason",
            (_utc_start, _utc_end)
        )
        for row in cur:
            suppress[row["suppress_reason"]] = row["n"]

        # 读取 STAGING_MODE（从 signal_synthesizer.py 的环境变量或常量推断）
        staging = None
        try:
            from signal_synthesizer import STAGING_MODE
            staging = STAGING_MODE
        except Exception:
            try:
                staging = os.environ.get("STAGING_MODE", "true").lower() in ("true", "1", "yes")
            except Exception:
                pass

        conn.close()
        return {
            "staging_mode": staging,
            "rules_evaluated": evaluated,
            "rules_triggered": triggered,
            "llm_calls": llm_calls,
            "ntfy_sends": ntfy_sends,
            "suppressed_by_staging": suppress.get("staging", 0),
            "suppressed_by_limit": suppress.get("daily_limit", 0),
            "suppressed_by_cooldown": suppress.get("cooldown", 0),
        }

    except Exception:
        return empty


# ══════════════════════════════════════════════════════════════════════════════
# 公共接口：读取心跳状态
# ══════════════════════════════════════════════════════════════════════════════
def check_heartbeat(max_age_seconds: int = 300) -> dict:
    """
    读取心跳文件，返回 {"alive": bool, "last_beat": str, "age_seconds": int}
    max_age_seconds: 超过此秒数判定为"可能异常"
    """
    try:
        if not os.path.exists(HEARTBEAT_FILE):
            return {"alive": False, "last_beat": None, "age_seconds": -1}
        with open(HEARTBEAT_FILE) as f:
            last_beat = f.readline().strip()
        last_dt = datetime.datetime.strptime(last_beat, "%Y-%m-%dT%H:%M:%S")
        age = (datetime.datetime.now() - last_dt).total_seconds()
        return {
            "alive": age <= max_age_seconds,
            "last_beat": last_beat,
            "age_seconds": round(age),
        }
    except Exception:
        return {"alive": False, "last_beat": None, "age_seconds": -1}


# ══════════════════════════════════════════════════════════════════════════════
# 每日健康摘要推送（三数字 ntfy）
# ══════════════════════════════════════════════════════════════════════════════
def daily_health_push() -> None:
    """
    每日推送三个数字到 ntfy，防止"系统运行但数据链断路无人感知"。

    三个数字：
      1. grv_latest.json 的 updated 时间戳（采集是否跑通）
      2. 当日降级 fetcher 数量（GRV source_quality != "gdelt+gpr" 计数）
      3. predictions 表当前行数（天璇→天玑 数据链是否有数据）

    出错只记日志，绝不抛异常（遵循 observability 零风险原则）。
    """
    import urllib.request
    try:
        ntfy_url = os.environ.get("NTFY_URL", "https://ntfy.sh/***REMOVED***")
        today = datetime.date.today().isoformat()

        # ── 数字1：grv_latest.json updated 时间戳 ──────────────────────────
        grv_path = os.path.join(DATA_DIR, "grv_latest.json")
        grv_updated = "N/A"
        try:
            with open(grv_path, encoding="utf-8") as f:
                grv = json.load(f)
            grv_updated = grv.get("updated", "N/A")
        except Exception:
            grv_updated = "读取失败"

        # ── 数字2：降级 fetcher 数量（source_quality != gdelt+gpr）──────────
        degraded_count = 0
        try:
            with open(grv_path, encoding="utf-8") as f:
                grv = json.load(f)
            sq = grv.get("source_quality", "gdelt+gpr")
            if sq != "gdelt+gpr":
                degraded_count = 1  # GRV 整体降级
        except Exception:
            degraded_count = -1  # 无法读取

        # ── 数字3：predictions 表当前行数 ─────────────────────────────────
        # P0-C 口径纠偏 (2026-08-15, 全量审查 Track B): 当前天璇 D1 落 SQLite
        # forecast_tracker.db、天玑 D3 读同一文件（D2 转 PG 尚未完成）——真实权威源是
        # SQLite，PG tianji.predictions 仅 7 行历史迁移数据，查它会造成
        # "链路已断但显示健康"的假象（此前 verifier 连崩 2 天，PG 却显示 7 行不告警）。
        # 优先读 SQLite（mode=ro 只读，不违反 P6 纪律）；D2 转 PG 完成后切回 PG 查询。
        predictions_rows = 0
        try:
            _db = os.path.join(DATA_DIR, "forecast_tracker.db")
            if os.path.exists(_db):
                _c = sqlite3.connect(f"file:{_db}?mode=ro", uri=True)
                predictions_rows = _c.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
                _c.close()
            else:
                predictions_rows = -1  # 文件不存在（P6 删库后 D2 未完成中间态）
        except Exception:
            predictions_rows = -1

        # ── 推送 ──────────────────────────────────────────────────────────
        # 判断整体健康状态
        alert = predictions_rows == 0 or grv_updated == "读取失败"
        icon = "🔴" if alert else "🟢"

        title = f"{icon} 世界推演 日健康摘要 {today}"
        body = (
            f"GRV更新: {grv_updated}\n"
            f"降级fetcher: {degraded_count if degraded_count >= 0 else '无法读取'}\n"
            f"predictions表行数: {predictions_rows if predictions_rows >= 0 else 'DB不存在'}"
        )
        if predictions_rows == 0:
            body += "\n⚠️ predictions表为空——天璇→天玑数据链断路"

        data = body.encode("utf-8")
        req = urllib.request.Request(
            ntfy_url,
            data=data,
            headers={
                "Title": title.encode("utf-8"),
                "Priority": "high" if alert else "default",
                "Tags": "world-sim,health",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)

    except Exception as e:
        # 只记录，不抛出
        try:
            print(f"[observability] daily_health_push failed: {e}", flush=True)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# 单例
# ══════════════════════════════════════════════════════════════════════════════
observe = _Observability()
