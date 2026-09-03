"""
llm_client.py — LLM 调用封装
Monte Carlo 模式：GLM-Z1-9B（硅基流动，免费）
两者均硅基流动，开阳控制台可切。
08-23：MiniMax 退役——原第二客户端与对应 usage 为死代码，已清除；
use_minimax 参数保留但仅作叙事开关。
"""

import os
import re
import time
import json
from typing import Optional

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


# ── API 配置 ──────────────────────────────────────────────
# 硅基流动（Monte Carlo 用，免费）
SILICONFLOW_BASE_URL   = "https://api.siliconflow.cn/v1"
SILICONFLOW_MODEL_GLM  = "THUDM/GLM-Z1-9B-0414"
SILICONFLOW_MODEL_QWEN = "Qwen/Qwen3-8B"
SILICONFLOW_MODEL_NARRATIVE = "deepseek-ai/DeepSeek-V4-Flash"  # 叙事用，更强
SILICONFLOW_MODEL      = SILICONFLOW_MODEL_GLM   # Monte Carlo 默认用 GLM-Z1-9B

# ── 配置 TTL（08-17 审查修复 LLM③：天璇配置缓存永不失效——改开阳控制台
#    配置须重启容器才生效，与天枢热更行为不一致。加 60s TTL 后自动重读）──
_CFG_TTL = 60.0
_last_cfg_ts = 0.0


def _apply_llm_config():
    """08-16：读天枢共享 llm_config.json（天璇挂载 macro_scan/data → /app/macro_data），
    开阳控制台改的模型在此覆盖代码常量。文件缺失/损坏 → 忽略走默认。
    08-17：加 60s TTL——每次调用检查，过期才重读（原导入期一次性执行永不刷新）。"""
    global SILICONFLOW_MODEL, SILICONFLOW_MODEL_NARRATIVE, _last_cfg_ts
    now = time.time()
    if now - _last_cfg_ts < _CFG_TTL:
        return
    try:
        with open("/app/macro_data/llm_config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        us = cfg.get("usages") or {}
        SILICONFLOW_MODEL = us.get("sim_mc", {}).get("model") or SILICONFLOW_MODEL
        SILICONFLOW_MODEL_NARRATIVE = (
            us.get("sim_narrative", {}).get("model") or SILICONFLOW_MODEL_NARRATIVE)
    except Exception:
        pass
    _last_cfg_ts = now


_apply_llm_config()

# key 从环境变量读，fallback 到 key.txt
def _load_key(env_var: str, fallback_path: str) -> str:
    val = os.environ.get(env_var, "")
    if val:
        return val
    try:
        with open(fallback_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

SILICONFLOW_KEY = _load_key(
    "SILICONFLOW_API_KEY",
    "/vol2/1000/software/macro-scan/key.txt"
)


# ── 客户端单例 ────────────────────────────────────────────
_sf_client: Optional["OpenAI"] = None
_dynamic_clients: dict = {}   # base_url|keyprefix -> OpenAI 客户端（配置覆盖的平台）

def _get_sf_client():
    global _sf_client
    if _sf_client is None:
        if not HAS_OPENAI:
            raise ImportError("需要安装 openai 库：pip install openai")
        _sf_client = OpenAI(
            api_key=SILICONFLOW_KEY,
            base_url=SILICONFLOW_BASE_URL,
        )
    return _sf_client


# ── 配置解析（08-16：开阳控制台统一配置——平台/模型/API key 可换）─────────
_usage_cache: Optional[dict] = None
_usage_cache_ts = 0.0

def _load_usage_cfg(usage_id: str) -> dict:
    """读天枢共享 llm_config.json（挂载 /app/macro_data），返回该使用点配置。
    配置由开阳控制台写（含 base_url/api_key/model 展开值）。
    08-17：加 60s TTL——原懒加载只读一次，改配置不生效需重启。"""
    global _usage_cache, _usage_cache_ts
    now = time.time()
    if _usage_cache is None or (now - _usage_cache_ts) > _CFG_TTL:
        try:
            with open("/app/macro_data/llm_config.json", encoding="utf-8") as f:
                _usage_cache = json.load(f).get("usages") or {}
        except Exception:
            _usage_cache = {}
        _usage_cache_ts = now
    return _usage_cache.get(usage_id) or {}


def _get_dynamic_client(base_url: str, api_key: str) -> Optional["OpenAI"]:
    """按配置的 base_url/api_key 建 OpenAI 兼容客户端（缓存 by url+key 前缀）。"""
    if not HAS_OPENAI or not base_url or not api_key:
        return None
    key = base_url + "|" + api_key[:8]
    if key not in _dynamic_clients:
        _dynamic_clients[key] = OpenAI(api_key=api_key, base_url=base_url)
    return _dynamic_clients[key]


def _resolve_client(usage_id: str, default_client, default_key: str,
                    default_base: str, default_model: str):
    """返回 (client, model)。配置覆盖（platform 展开的 base_url+key+model）→ 动态客户端；
    否则默认客户端 + 模型（08-17：_apply_llm_config TTL 内刷新，默认模型随配置更新）。"""
    _apply_llm_config()   # 08-17：TTL 检查，配置改了默认模型也刷新
    u = _load_usage_cfg(usage_id)
    cfg_base = (u.get("base_url") or "").rstrip("/")
    cfg_key = u.get("api_key") or ""
    cfg_model = u.get("model") or ""
    if cfg_base and cfg_key:
        client = _get_dynamic_client(cfg_base, cfg_key)
        if client is not None:
            return client, cfg_model or default_model
    return default_client(), cfg_model or default_model


# ── 核心调用函数 ──────────────────────────────────────────
def call_llm(
    prompt: str,
    use_minimax: bool = False,
    max_retries: int = 2,
    temperature: float = 0.4,
    max_tokens: int = 256,
) -> str:
    """
    调用 LLM，返回原始文本。
    use_minimax=False → sim_mc（Monte Carlo，默认 GLM-Z1-9B / 硅基流动）
    use_minimax=True  → sim_narrative（叙事，默认 DeepSeek-V4-Flash）
    08-16：走开阳控制台统一配置（llm_config.json 可换平台/模型/API key）；
    失败时返回空字符串，不抛异常。
    """
    usage_id = "sim_narrative" if use_minimax else "sim_mc"
    client, model = _resolve_client(
        usage_id,
        _get_sf_client, SILICONFLOW_KEY, SILICONFLOW_BASE_URL,
        SILICONFLOW_MODEL_NARRATIVE if use_minimax else SILICONFLOW_MODEL,
    )

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                print(f"[LLM 调用失败 {model}] {e}")
    return ""


def parse_action(text: str, valid_actions: list[str]) -> str:
    """
    从 LLM 输出里提取 ACTION: xxx。
    找不到或不在 valid_actions 里时返回 "HOLD"。
    """
    m = re.search(r"ACTION:\s*([A-Z0-9_]+)", text, re.I)
    if m:
        action = m.group(1).upper()
        if action in valid_actions:
            return action
    return "HOLD"


def test_connection() -> dict:
    """测试两个模型连通性"""
    test_prompt = (
        "你是全球宏观对冲基金CIO。当前状态：外部压力上升(pressure_shift=0.19)，"
        "信贷收紧(credit_tightening=0.29)，市场情绪中性(sentiment=0.0)，VIX上涨(vix_shift=0.33)。"
        "请判断仓位方向，必须以 ACTION: SHORT_MARKET 或 ACTION: DECREASE_RISK 或 ACTION: HOLD 结尾。"
    )
    results = {}
    for model_name, model_id in [("GLM-Z1-9B", SILICONFLOW_MODEL_GLM), ("Qwen3-8B", SILICONFLOW_MODEL_QWEN)]:
        print(f"\n测试 {model_name}...")
        client = _get_sf_client()
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": test_prompt}],
                temperature=0.4, max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
            action = parse_action(text, ["SHORT_MARKET", "DECREASE_RISK", "HOLD"])
            print(f"  响应：{text[:120]}...")
            print(f"  动作：{action}")
            results[model_name] = {"connected": True, "action": action}
        except Exception as e:
            print(f"  失败：{e}")
            results[model_name] = {"connected": False, "action": None}
    return results


if __name__ == "__main__":
    results = test_connection()
    for model, r in results.items():
        print(f"{model}: {'成功' if r['connected'] else '失败'}, 动作={r['action']}")
