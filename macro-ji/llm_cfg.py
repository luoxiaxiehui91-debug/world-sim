#!/usr/bin/env python3
"""llm_cfg.py — 天璇/天玑侧 LLM 使用点配置解析（P2，与天枢 llm_usage 同构的四层兜底链）

取值链（唯一入口；本文件及调用方代码中**不留任何模型名字面量**）：

  L1 主配置   /app/macro_data/llm_config.json            开阳控制台唯一写入目标
  L2 快照     /app/macro_data/llm_config.json.bak        控制台保存前自动轮转（last-known-working）
  L3 git 模板 /app/shared_config|/app/config/llm_config.default.json
  L4 env      过渡保留（仅 verify_llm 有 VERIFY_LLM_MODEL；P3 摘除）
  全链无解 → raise ValueError（单次调用失败，由调用方降级；不崩溃进程）

回落留痕：来源变化时打印 `[llm_cfg] ⚠️ …`；`resolve()` 返回体带 `source`
（truth / snapshot / template / none），与天枢 `/llm-usage` 的 `config_source` 同义。

用法：
    from core import llm_cfg            # 天璇（core 为包）
    import llm_cfg                      # 天玑（/app 平铺）
    cfg = llm_cfg.resolve("sim_mc")
    base, key, model = llm_cfg.resolve_endpoint("verify_llm")

⚠️ 本文件在 `macro-sim/core/` 与 `macro-ji/` 各存一份（跨容器复制，与 llm_judge.ACTION_CRITERIA
   同惯例）。两份**必须字节一致**——由 scripts/check_llm_config.py 检查项 9（G5）守卫。
"""
import json
import os
import time

# ── 路径 ────────────────────────────────────────────────────────────────
_DATA_CFG = "/app/macro_data/llm_config.json"
_SNAP_CFG = _DATA_CFG + ".bak"
# L3 模板候选：天玑把宿主 config 挂到 /app/config；天璇为**避免覆盖镜像内 config/agents.yaml**
# （macro-sim/run.py 依赖 /app/config/agents.yaml），改挂到 /app/shared_config。
_TPL_CANDIDATES = (
    "/app/shared_config/llm_config.default.json",
    "/app/config/llm_config.default.json",
)
DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"

# 平台 → 密钥 env（配置永不带 key，与天枢 llm_usage.PLATFORM_ENV_KEYS 同构）
_PLATFORM_KEY_ENV = {
    "siliconflow": "SILICONFLOW_API_KEY",
    "mimo_plan": "OPENAI_COMPAT_KEY",
    "mimo_api": "MIMO_API_KEY",
}
# 过渡期 env 模型名兜底（D2=C 后仅剩天玑历史注入，P3 摘除）
_ENV_MODEL_KEY = {"verify_llm": "VERIFY_LLM_MODEL"}

# 60s TTL：与天璇原 _apply_llm_config 行为一致（控制台改配置自动生效，不需重启）
_CFG_TTL = 60.0
_cache = {"ts": 0.0, "cfg": {}, "source": "none"}
_last_source = ["none"]


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _announce(source, path):
    """来源变化才打印，避免回落稳态下刷屏。"""
    if source != _last_source[0]:
        if source != "truth":
            print(f"[llm_cfg] ⚠️ 配置来源={source}（{path or '无可用配置文件'}）"
                  f"——非 L1 主配置，请检查 data/llm_config.json", flush=True)
        _last_source[0] = source


def _load_config():
    """按 L1→L2→L3 返回 (cfg, source)；全不可用 → ({}, 'none')。"""
    for path, src in ((_DATA_CFG, "truth"), (_SNAP_CFG, "snapshot")):
        d = _read_json(path)
        if d and (d.get("usages") or {}):
            _announce(src, path)
            return d, src
    for path in _TPL_CANDIDATES:
        d = _read_json(path)
        if d and (d.get("usages") or {}):
            _announce("template", path)
            return d, "template"
    _announce("none", "")
    return {}, "none"


def _cached_config():
    now = time.time()
    if _cache["cfg"] and (now - _cache["ts"]) < _CFG_TTL:
        return _cache["cfg"], _cache["source"]
    cfg, src = _load_config()
    _cache["ts"] = now
    _cache["cfg"] = cfg
    _cache["source"] = src
    return cfg, src


def resolve(usage_id: str) -> dict:
    """解析一个使用点 → {"base_url","api_key","model","platform","source"}。

    全链无 model → raise ValueError（调用方应按「单次调用失败」降级，不要让进程崩溃）。
    """
    cfg, src = _cached_config()
    u = (cfg.get("usages") or {}).get(usage_id) or {}
    platform = u.get("platform") or "siliconflow"
    base_url = (u.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    model = u.get("model") or os.environ.get(_ENV_MODEL_KEY.get(usage_id, ""), "")
    if not model:
        raise ValueError(
            f"{usage_id}: 配置链（source={src}）无 model 且无 env 兜底——"
            "请在开阳控制台为该使用点指定模型")
    env_name = _PLATFORM_KEY_ENV.get(platform, "SILICONFLOW_API_KEY")
    return {"base_url": base_url,
            "api_key": os.environ.get(env_name, ""),
            "model": model,
            "platform": platform,
            "source": src}


def resolve_endpoint(usage_id: str):
    """(base_url, api_key, model) 三元——chronicler / readable_report / llm_judge 的直接消费形态。"""
    c = resolve(usage_id)
    if not c["api_key"]:
        raise ValueError(f"{usage_id}: 平台 {c['platform']} 无可用 api_key（env {_PLATFORM_KEY_ENV.get(c['platform'], 'SILICONFLOW_API_KEY')} 未注入）")
    return c["base_url"], c["api_key"], c["model"]


def config_source(usage_id: str = "") -> str:
    """仅取来源（供验收/巡检对拍）；不触发 model 校验。"""
    cfg, src = _cached_config()
    if usage_id and not (cfg.get("usages") or {}).get(usage_id):
        return src + "|usage-missing"
    return src
