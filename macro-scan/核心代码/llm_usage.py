#!/usr/bin/env python3
"""
llm_usage.py — LLM 使用点统一登记 + 运行时配置（08-16，开阳控制台统一修改模型）

背景：系统多处调用 LLM（MiMo / Claude / SiliconFlow / MiniMax），模型散落在环境变量
与代码常量里，改模型要改代码或 compose env。此模块提供：
  1. LLM_USAGES 静态清单（每个使用点的 id/名称/用途/默认模型/端点/所属容器）
  2. llm_config.json 运行时配置（data 目录，天枢/天璇/天玑共享；配置优先于默认）
  3. get_model(usage_id) —— 各调用点读取"配置覆盖的模型"（未配置返回 None，走默认）

配置文件契约（data/llm_config.json，原子写）：
  {
    "schema_version": "1.0",
    "updated": "ISO",
    "usages": { "<usage_id>": {"model": "<model-name>"} }   # 只存被修改过的
  }

接入方式（各调用点）：
  model = get_model("translate_titles") or TRANSLATE_MODEL   # 配置优先，默认兜底
"""

import datetime
import json
import os

# data 根（天枢运行时数据目录；天璇挂载为 /app/macro_data）
DATA_DIR = os.environ.get(
    "WORLDSIM_DATA_DIR",
    "/vol2/1000/software/macro-scan/data"
    if os.path.isdir("/vol2/1000/software/macro-scan/data")
    else "/workspace/data",
)
CONFIG_PATH = os.path.join(DATA_DIR, "llm_config.json")


# ── LLM 使用点静态清单 ────────────────────────────────────────────
# default_model: None = 跟随环境变量/代码常量（配置未覆盖时）；str = 代码默认值
LLM_USAGES = [
    {
        "id": "translate_titles",
        "name": "新闻标题翻译",
        "purpose": "fetch_news_titles.py 标题英→中（LLM 逐条并发 4）",
        "default_model": "mimo-v2.5",
        "endpoint": "MiMo (OPENAI_COMPAT_URL)",
        "container": "tianshu",
        "adjustable": True,
    },
    {
        "id": "openai_compat",
        "name": "通用 OpenAI 兼容",
        "purpose": "hybrid_llm.call_openai_compat 无显式 model 的调用（含 run_macro_analysis 宏观分析）",
        "default_model": None,  # 跟随 OPENAI_COMPAT_MODEL env
        "endpoint": "MiMo (OPENAI_COMPAT_URL)",
        "container": "tianshu",
        "adjustable": True,
    },
    {
        "id": "claude_reason",
        "name": "Claude 推理",
        "purpose": "hybrid_llm.call_claude（reason mode=claude）",
        "default_model": "claude-sonnet-4-6",
        "endpoint": "Anthropic",
        "container": "tianshu",
        "adjustable": True,
    },
    {
        "id": "sim_mc",
        "name": "天璇 Monte Carlo",
        "purpose": "macro-sim llm_client SILICONFLOW_MODEL（MC 默认 GLM-Z1-9B）",
        "default_model": "THUDM/GLM-Z1-9B-0414",
        "endpoint": "SiliconFlow",
        "container": "tianxuan",
        "adjustable": True,
    },
    {
        "id": "sim_narrative",
        "name": "天璇 叙事合成",
        "purpose": "macro-sim llm_client QWEN_LARGE（叙事用更强模型）",
        "default_model": "Qwen/Qwen3.5-27B",
        "endpoint": "SiliconFlow",
        "container": "tianxuan",
        "adjustable": True,
    },
    {
        "id": "sim_minimax",
        "name": "天璇 MiniMax",
        "purpose": "macro-sim llm_client MINIMAX_MODEL（单次探索）",
        "default_model": "MiniMax-M3",
        "endpoint": "MiniMax",
        "container": "tianxuan",
        "adjustable": True,
    },
]
_USAGE_IDS = {u["id"] for u in LLM_USAGES}


# ── 配置读写 ───────────────────────────────────────────────────────

def load_config() -> dict:
    """读 llm_config.json；不存在/损坏 → 空配置（全部走默认）。"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict) and isinstance(cfg.get("usages"), dict):
            return cfg
    except Exception:
        pass
    return {"schema_version": "1.0", "usages": {}}


def save_config(cfg: dict) -> bool:
    """原子写 llm_config.json。返回是否成功。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        cfg["schema_version"] = "1.0"
        cfg["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
        return True
    except Exception as e:
        print(f"[llm_usage] 写配置失败: {e}")
        return False


def get_model(usage_id: str) -> str | None:
    """返回某使用点在配置里覆盖的模型；未配置返回 None（调用方走默认）。"""
    if usage_id not in _USAGE_IDS:
        return None
    try:
        return load_config().get("usages", {}).get(usage_id, {}).get("model") or None
    except Exception:
        return None


def set_model(usage_id: str, model: str) -> tuple[bool, str]:
    """控制台修改使用点模型。model 空 → 删除覆盖（回默认）。"""
    if usage_id not in _USAGE_IDS:
        return False, f"未知使用点: {usage_id}"
    model = (model or "").strip()
    if not model:
        return False, "模型名不能为空"
    cfg = load_config()
    cfg.setdefault("usages", {})
    cfg["usages"][usage_id] = {"model": model}
    if save_config(cfg):
        return True, "ok"
    return False, "写配置失败"


def effective_models() -> list[dict]:
    """清单 + 当前生效模型 + 是否被配置覆盖（给控制 API / 开阳展示）。"""
    cfg = load_config().get("usages", {})
    out = []
    for u in LLM_USAGES:
        override = cfg.get(u["id"], {}).get("model")
        out.append({
            **u,
            "model": override or u["default_model"] or "（env 默认）",
            "overridden": bool(override),
        })
    return out


if __name__ == "__main__":
    for u in effective_models():
        flag = " [配置覆盖]" if u["overridden"] else ""
        print(f"{u['id']:<20} {u['container']:<10} {u['model']}{flag}  ({u['purpose'][:40]})")
