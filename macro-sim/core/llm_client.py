"""
llm_client.py — LLM 调用封装

两个使用点（模型一律由配置决定，代码不留模型名）：
  sim_mc        Monte Carlo 决策
  sim_narrative 叙事
08-23：MiniMax 退役——原第二客户端与对应 usage 为死代码，已清除；
use_minimax 参数保留但仅作叙事开关。
P2（2026-10-10，CHG-20261010T231251）：四个模型名常量全部删除，改由 core/llm_cfg
四层兜底链解析（L1 主配置 → L2 快照 → L3 模板 → L4 env）；全链无解 → 单次调用失败，不崩溃。
"""

import os
import re
import time
import json
from typing import Optional

from core import llm_cfg

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


# ── API 配置 ──────────────────────────────────────────────
# 地址不是模型名，允许常驻；模型一律走 llm_cfg.resolve()（P2）
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

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
    os.environ.get("SILICONFLOW_KEY_FILE", "")
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


# ── 配置解析（P2：统一走 core/llm_cfg 四层兜底链；60s TTL 由该模块维护）─────────


def _get_dynamic_client(base_url: str, api_key: str) -> Optional["OpenAI"]:
    """按配置的 base_url/api_key 建 OpenAI 兼容客户端（缓存 by url+key 前缀）。"""
    if not HAS_OPENAI or not base_url or not api_key:
        return None
    key = base_url + "|" + api_key[:8]
    if key not in _dynamic_clients:
        _dynamic_clients[key] = OpenAI(api_key=api_key, base_url=base_url)
    return _dynamic_clients[key]


def _resolve_client(usage_id: str):
    """返回 (client, model)。平台/地址/模型由 llm_cfg.resolve() 决定（代码零模型字面量）；
    密钥按平台映射取 env（配置永不带 key，与天枢同构）。
    解析失败 → raise，由 call_llm 降级为「单次调用失败」。"""
    cfg = llm_cfg.resolve(usage_id)
    model = cfg["model"]
    key = cfg["api_key"] or (SILICONFLOW_KEY if cfg["platform"] == "siliconflow" else "")
    if not key:
        raise ValueError(f"{usage_id}: 平台 {cfg['platform']} 无可用 api_key")
    if cfg["base_url"] == SILICONFLOW_BASE_URL:
        return _get_sf_client(), model
    return (_get_dynamic_client(cfg["base_url"], key) or _get_sf_client()), model


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
    use_minimax=False → sim_mc（Monte Carlo）
    use_minimax=True  → sim_narrative（叙事）
    P2：平台/地址/模型由 core/llm_cfg 四层兜底链解析（代码零模型字面量）；
    配置解析失败或调用失败均返回空字符串，不抛异常。
    """
    usage_id = "sim_narrative" if use_minimax else "sim_mc"
    try:
        client, model = _resolve_client(usage_id)
    except Exception as e:
        print(f"[llm_client] {usage_id} 配置解析失败，本次调用放弃：{e}")
        return ""

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
    """测试两个在用使用点（sim_mc / sim_narrative）连通性；模型由配置决定。
    P2：原 Qwen3-8B 基准条目删除（仅 CLI 对比用途，无对应配置使用点）。"""
    test_prompt = (
        "你是全球宏观对冲基金CIO。当前状态：外部压力上升(pressure_shift=0.19)，"
        "信贷收紧(credit_tightening=0.29)，市场情绪中性(sentiment=0.0)，VIX上涨(vix_shift=0.33)。"
        "请判断仓位方向，必须以 ACTION: SHORT_MARKET 或 ACTION: DECREASE_RISK 或 ACTION: HOLD 结尾。"
    )
    results = {}
    for usage_id in ("sim_mc", "sim_narrative"):
        print(f"\n测试 {usage_id}...")
        try:
            client, model_id = _resolve_client(usage_id)
        except Exception as e:
            print(f"  配置解析失败：{e}")
            results[usage_id] = {"connected": False, "action": None}
            continue
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": test_prompt}],
                temperature=0.4, max_tokens=256,
            )
            text = resp.choices[0].message.content or ""
            action = parse_action(text, ["SHORT_MARKET", "DECREASE_RISK", "HOLD"])
            print(f"  模型：{model_id}")
            print(f"  响应：{text[:120]}...")
            print(f"  动作：{action}")
            results[usage_id] = {"connected": True, "action": action, "model": model_id}
        except Exception as e:
            print(f"  失败：{e}")
            results[usage_id] = {"connected": False, "action": None}
    return results


if __name__ == "__main__":
    results = test_connection()
    for model, r in results.items():
        print(f"{model}: {'成功' if r['connected'] else '失败'}, 动作={r['action']}")
