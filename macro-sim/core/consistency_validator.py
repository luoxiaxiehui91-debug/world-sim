"""
consistency_validator.py — 跨 Agent 行动一致性校验

在 Monte Carlo 每个 run 结束后检查各 Agent 行动是否存在逻辑矛盾。

两层检查：
  Layer 1：规则表字符串匹配（零 LLM 成本，<1ms）
  Layer 2：LLM 经济学机制校验（仅在 Layer 1 命中且 use_llm=True 时触发）

设计原则：
  - 只拦截同一经济体内的机制不兼容（基于 IS-LM、Taylor Rule、Mundell-Fleming）
  - 跨经济体政策分歧（Fed加息 vs PBOC降息）永远不触发，是仿真的驱动力而非错误
  - 宁可漏报，不误报：规则表刻意保守，只放有文献支撑的真矛盾
  - 不丢 run：矛盾只标注警告，路径树概率数字不变
"""

from __future__ import annotations


# ── Layer 1：规则表 ────────────────────────────────────────
# 格式：(agent_id_A, action_A, agent_id_B, action_B, reason)
# 所有规则均为同一经济体内的机制不兼容，跨经济体组合不在此列。

# R1：同一 Agent 工具方向相反（单工具单调性约束）
_SAME_AGENT_RULES: list[tuple[str, str, str, str, str]] = [
    ("A1", "CUT_50BP",  "A1", "HIKE_25BP", "Fed 同时降息 50bp 与加息 25bp"),
    ("A1", "CUT_25BP",  "A1", "HIKE_25BP", "Fed 同时降息 25bp 与加息 25bp"),
    ("A11","CUT_25BP",  "A11","HIKE_25BP", "ECB 同时降息与加息"),
    ("A11","QE_EXPAND", "A11","HIKE_25BP", "ECB 同时 QE 扩表与加息（短期内方向相反）"),
    ("A7", "CUT_25BP",  "A7", "RAISE_RATES","同一 EM 央行同步降息与加息"),
    ("A8", "CUT_RRR",   "A8", "TIGHTEN_CN", "PBOC 同时降准与货币收紧"),
    ("A8", "CUT_LPR",   "A8", "TIGHTEN_CN", "PBOC 同时降 LPR 与货币收紧"),
]

# R2：同一美国金融体系内部的机制矛盾
_US_MECHANISM_RULES: list[tuple[str, str, str, str, str]] = [
    # Fed 加息（收紧流动性）+ 商业银行大规模放贷（扩张信贷）
    # 注：Fed加息 + 银行小幅放贷属于正常，此处只标注 EASE_CREDIT（显著放贷）
    ("A1", "HIKE_25BP",  "A2", "EASE_CREDIT",
     "Fed 加息收紧美国流动性，商业银行同步显著放贷——美国金融体系内方向相反"),
    # 散户恐慌性抛售 + 媒体同时放大乐观情绪（同一市场情绪环境）
    ("A10","PANIC_SELL", "A6", "AMPLIFY_OPTIMISM",
     "散户恐慌性抛售与媒体放大乐观情绪在同一市场环境中矛盾"),
    # 散户 FOMO 追涨 + 媒体放大恐慌（同一市场情绪环境）
    ("A10","FOMO_BUY",   "A6", "AMPLIFY_FEAR",
     "散户 FOMO 追涨与媒体放大恐慌在同一市场环境中矛盾"),
]

# 合并所有 Layer 1 规则
CONTRADICTION_RULES = _SAME_AGENT_RULES + _US_MECHANISM_RULES


def validate_step_actions(
    actions: dict[str, str],
    world_state: dict | None = None,
    use_llm: bool = False,
) -> list[dict]:
    """
    校验单步 Agent 行动集合是否存在逻辑矛盾。

    Parameters
    ----------
    actions     : {agent_id: action_string}，HOLD/NO_ACTION 已过滤
    world_state : 当前世界状态快照（供 Layer 2 LLM 使用）
    use_llm     : 是否启用 Layer 2 LLM 校验（MC 阶段应保持 False）

    Returns
    -------
    list of {rule, reason, layer}；空列表表示无矛盾。
    """
    issues: list[dict] = []

    # Layer 1：规则表匹配
    for (aid_a, act_a, aid_b, act_b, reason) in CONTRADICTION_RULES:
        a_match = actions.get(aid_a) == act_a
        b_match = actions.get(aid_b) == act_b
        if a_match and b_match:
            issues.append({
                "rule":   f"{aid_a}:{act_a} ↔ {aid_b}:{act_b}",
                "reason": reason,
                "layer":  1,
            })

    # Layer 2：LLM 经济学机制校验（默认关闭）
    if issues and use_llm and world_state is not None:
        llm_result = _llm_check(actions, issues, world_state)
        if llm_result:
            issues.append({
                "rule":   "LLM经济学校验",
                "reason": llm_result,
                "layer":  2,
            })

    return issues


def validate_run_actions(
    history: list[dict],
    use_llm: bool = False,
) -> list[dict]:
    """
    校验整个 run 的行动历史，返回所有步骤中出现的矛盾列表。
    每个矛盾条目额外包含 step 字段。
    """
    all_issues: list[dict] = []
    for snap in history:
        step_actions = {
            aid: act
            for aid, act in snap.get("actions", {}).items()
            if act not in ("HOLD", "NO_ACTION")
        }
        if not step_actions:
            continue
        step_issues = validate_step_actions(
            step_actions,
            world_state=snap,
            use_llm=use_llm,
        )
        for issue in step_issues:
            all_issues.append({**issue, "step": snap.get("cycle", -1)})
    return all_issues


def _llm_check(
    actions: dict[str, str],
    layer1_issues: list[dict],
    world_state: dict,
) -> str:
    """
    Layer 2：调用 LLM 判断 Layer 1 命中的矛盾是否为真实经济学矛盾。
    只有 use_llm=True 时才被调用，MC 阶段不触发。
    返回 LLM 给出的简短判断（空字符串表示 LLM 认为无矛盾）。
    """
    try:
        from core.llm_client import call_llm

        issues_str = "\n".join(f"  - {i['reason']}" for i in layer1_issues)
        actions_str = ", ".join(f"{k}:{v}" for k, v in actions.items())
        grv = world_state.get("grv", "N/A")
        sentiment = world_state.get("market_sentiment", "N/A")

        prompt = (
            f"当前宏观仿真步骤中，12个Agent的行动如下：\n{actions_str}\n\n"
            f"当前世界状态：GRV={grv}, 市场情绪={sentiment}\n\n"
            f"规则表检测到以下潜在矛盾：\n{issues_str}\n\n"
            f"请基于 IS-LM / Taylor Rule / Mundell-Fleming 三元悖论判断：\n"
            f"1. 如果矛盾涉及不同经济体（如Fed vs PBOC）→ 回复「跨经济体分歧，不是矛盾」\n"
            f"2. 如果是同一经济体内的机制不兼容 → 回复「确认矛盾：[一句话说明原因]」\n"
            f"只输出以上两种格式之一，不要其他文字。"
        )

        raw = call_llm(prompt, use_minimax=False)
        if not raw:
            return ""

        import re
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        if "跨经济体" in raw or "不是矛盾" in raw:
            return ""
        if "确认矛盾" in raw:
            return raw
        return ""

    except Exception as e:
        print(f"[consistency_validator] Layer 2 LLM 调用失败（非阻断）: {e}")
        return ""
