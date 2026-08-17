"""governance.py — 政权更迭引擎（08-17）

按 soul.governance 配置内生触发三类更迭事件（仅预测期启用）：
  1. election（民主定期选举）：到选举周期必换届，按 transition_prob 概率切换
     到候选 regime（alternate_regime），否则延续现行；single_term=true 强制切换。
  2. succession / coup（长期执政继承 / 政变）：每月按 succession_risk × 压力调制
     概率触发，切换到 succession_regime（继承/政变后风格）。
  3. hybrid：选举 + 继承/政变风险并存（俄罗斯类）。

更迭事件 = ① 切换该 agent 的 soul regime（_resolve_regime_by_id）
            ② 对 world 施加 GRV 冲击（transition_impact / break_impact）
            ③ 记录事件（world._governance_events，报告渲染用）

设计：每个 MC run 独立随机 → 更迭是路径分叉的内生来源（与 activation 概率正交）。
"""

import random

# ── 默认冲击（soul.governance 未显式配置时兜底）────────────────────────
ELECTION_IMPACT = {
    "us_china_strategic": 6.0,   # 换届 → 战略维度波动
    "global_composite":   4.0,
}
BREAK_IMPACT = {                 # 继承/政变 → 系统性冲击
    "global_composite":  15.0,
    "russia_europe":     10.0,
    "market_sentiment":  -0.15,
}
MAX_RISK = 0.9                  # 单月触发概率上限


def _resolve_regime_by_id(soul_raw: dict, regime_id: str) -> dict:
    """强制选择 soul.regimes 中指定 id 的 regime（合并顶层公共字段）。
    找不到时原样返回（fallback，不崩）。"""
    regimes = soul_raw.get("regimes") or []
    for rg in regimes:
        if rg.get("id") == regime_id:
            merged = {k: v for k, v in soul_raw.items() if k != "regimes"}
            for k in ("id", "since", "until", "label"):
                merged.pop(k, None)
            merged.update({k: v for k, v in rg.items()
                           if k not in ("id", "since", "until", "label")})
            merged["_regime_id"] = rg.get("id")
            merged["_regime_label"] = rg.get("label", "")
            return merged
    return soul_raw


def _apply_impact(world, impact: dict) -> None:
    """把更迭冲击写到 world：grv_dimensions 维度 clamp 0-100，其余 world 属性直接加。"""
    gd = world.grv_dimensions
    for k, v in (impact or {}).items():
        if k in gd:
            gd[k] = min(100.0, max(0.0, gd[k] + v))
        elif hasattr(world, k):
            cur = getattr(world, k) or 0.0
            setattr(world, k, cur + v)


def check_governance_transitions(world, agents: dict, rng: random.Random | None = None) -> list[dict]:
    """每月检查所有主权 agent 的更迭条件，返回触发的事件列表（含 GRV 冲击已施加）。

    world: MacroWorldState（cycle 1-based；social_stress 作内部压力源 0-100）
    agents: {agent_id: MacroAgent}——触发时切换 ag.soul 到目标 regime
    """
    rng = rng or random
    events: list[dict] = []
    for aid, ag in agents.items():
        soul_raw = getattr(ag, "_soul_raw", None)
        if not soul_raw:
            continue
        # 08-17 触发后锁定：autocratic 继承/政变是"一次性"事件——发生后进入新
        # 政权稳定期，本次仿真内不再反复触发（G1 实测 100%+每月重复的根因）
        if getattr(ag, "_gov_done", False):
            continue
        gov = (ag.soul or {}).get("governance") or {}
        if not gov:
            continue
        mech = gov.get("change_mechanism")
        cycle_now = world.cycle  # 1-based

        if mech == "election":
            cycle = int(gov.get("cycle_months", 48))
            offset = int(gov.get("next_election_offset", 12))
            if cycle_now < offset or (cycle_now - offset) % cycle != 0:
                continue
            # 换届：single_term 强制切换；否则 transition_prob 概率切换
            single = bool(gov.get("single_term", False))
            alt = gov.get("alternate_regime", "")
            if alt and (single or rng.random() < float(gov.get("transition_prob", 0.4))):
                ag.soul = _resolve_regime_by_id(soul_raw, alt)
                events.append({
                    "agent": aid, "month": cycle_now, "type": "election_transition",
                    "to_regime": alt,
                    "label": f"{ag.soul.get('_regime_label') or alt}接任",
                })
            else:
                events.append({
                    "agent": aid, "month": cycle_now, "type": "election_hold",
                    "to_regime": None, "label": "换届延续（现行路线）",
                })
            _apply_impact(world, gov.get("transition_impact") or ELECTION_IMPACT)

        elif mech in ("succession", "coup", "hybrid"):
            risk = float(gov.get("succession_risk", 0.01))
            thr = float(gov.get("coup_pressure_threshold", 0.75))
            pressure = (world.social_stress or 0.0) / 100.0  # 0-1
            mod = 3.0 if pressure > thr else 1.0
            if rng.random() < min(MAX_RISK, risk * mod):
                break_regime = gov.get("succession_regime", "")
                if break_regime:
                    ag.soul = _resolve_regime_by_id(soul_raw, break_regime)
                events.append({
                    "agent": aid, "month": cycle_now, "type": "succession_break",
                    "to_regime": break_regime,
                    "label": f"{ag.soul.get('_regime_label') or '继承/政变后'}接管",
                })
                _apply_impact(world, gov.get("break_impact") or BREAK_IMPACT)
                ag._gov_done = True   # 一次性事件：锁定本仿真期不再触发

    if events:
        existing = getattr(world, "_governance_events", None) or []
        world._governance_events = existing + events
    return events
