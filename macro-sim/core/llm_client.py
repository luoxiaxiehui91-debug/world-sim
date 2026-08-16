"""
llm_client.py — LLM 调用封装
Monte Carlo 模式：GLM-Z1-9B（硅基流动，免费）
单次探索模式：MiniMax-M3（Anthropic 兼容）
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
SILICONFLOW_MODEL_QWEN_LARGE = "Qwen/Qwen3.5-27B"  # 叙事用，更强
SILICONFLOW_MODEL      = SILICONFLOW_MODEL_GLM   # Monte Carlo 默认用 GLM-Z1-9B

# MiniMax-M3（单次探索用，Anthropic 兼容）
MINIMAX_BASE_URL = "https://api.minimaxi.com/v1"
MINIMAX_MODEL    = "MiniMax-M3"


def _apply_llm_config():
    """08-16：读天枢共享 llm_config.json（天璇挂载 macro_scan/data → /app/macro_data），
    开阳控制台改的模型在此覆盖代码常量。文件缺失/损坏 → 忽略走默认。"""
    global SILICONFLOW_MODEL, SILICONFLOW_MODEL_QWEN_LARGE, MINIMAX_MODEL
    try:
        with open("/app/macro_data/llm_config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        us = cfg.get("usages") or {}
        SILICONFLOW_MODEL = us.get("sim_mc", {}).get("model") or SILICONFLOW_MODEL
        SILICONFLOW_MODEL_QWEN_LARGE = (
            us.get("sim_narrative", {}).get("model") or SILICONFLOW_MODEL_QWEN_LARGE)
        MINIMAX_MODEL = us.get("sim_minimax", {}).get("model") or MINIMAX_MODEL
    except Exception:
        pass


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
MINIMAX_KEY = _load_key("MINIMAX_API_KEY", "")


# ── 客户端单例 ────────────────────────────────────────────
_sf_client: Optional["OpenAI"] = None
_mm_client: Optional["OpenAI"] = None

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

def _get_mm_client():
    global _mm_client
    if _mm_client is None:
        if not HAS_OPENAI:
            raise ImportError("需要安装 openai 库：pip install openai")
        _mm_client = OpenAI(
            api_key=MINIMAX_KEY,
            base_url=MINIMAX_BASE_URL,
        )
    return _mm_client


# ── 核心调用函数 ──────────────────────────────────────────
def call_llm(
    prompt: str,
    use_minimax: bool = False,
    max_retries: int = 2,
    temperature: float = 0.4,
) -> str:
    """
    调用 LLM，返回原始文本。
    use_minimax=False → GLM-Z1-9B（硅基流动，免费，Monte Carlo 用）
    use_minimax=True  → MiniMax-M3（单次探索用）
    失败时返回空字符串，不抛异常。
    """
    client = _get_sf_client()
    model  = SILICONFLOW_MODEL_QWEN_LARGE if use_minimax else SILICONFLOW_MODEL

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=256,
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
                temperature=0.4, max_tokens=256,
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
