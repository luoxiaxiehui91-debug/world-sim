# -*- coding: utf-8 -*-
"""
回归测试：R3 校准守卫 + 测量层纯函数（macro-sim · 天璇）

目的
----
锁定 R3（v2.0.31）修复的真实行为，防第 4 轮回退：
1. A2 grv 触发线 0.8→0.6（grv_stress>0.3 即 TIGHTEN，0.4 线时代不触发）
2. 死变量豁免修复（qa-r2b blocking #2：dead/silence 超限变量不得计入加权）
3. 守卫 A/B/C 判定（合成 delta/tgt/agents）
4. _run_ease_probe ①决策层 ctx → EASE_CREDIT（P0-2 能力闸）
5. _extract_preclamp_delta / _step_eligibility 口径锁定

运行方式
--------
    cd /s/world-sim/macro-sim && python tests/test_calibrator_guards.py

自包含纯 Python 脚本，不依赖 pytest（macro-sim 未安装 pytest）。
顶部把 macro-sim 根目录加入 sys.path，`core` 包可解析。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agents.base import AgentParams, MacroAgent
from core.agents.financial import CommercialBankAgent
from core.calibrator import (
    ERROR_WEIGHTS,
    MONTHLY_SCALE,
    _eligible_for_weighted,
    _extract_preclamp_delta,
    _step_eligibility,
    check_guards,
    classify_a2_state,
)

_PASSED = []


def _t(name: str, fn):
    fn()
    _PASSED.append(name)
    print(f"  ✓ {name}")


# ── 1) _step_eligibility N/U/S/T ─────────────────────────

def test_eligibility_classes():
    assert _step_eligibility(0.01, 0.0) == "N", "中性怠工"
    assert _step_eligibility(0.06, 0.0) == "U", "中性乱动"
    assert _step_eligibility(0.001, 0.1) == "S", "有信号不响应"
    assert _step_eligibility(0.02, 0.1) == "T", "可测"
    # EPS 边界：|t|=0.03 是信号门槛（EPS_TGT 冻结不动）
    assert _step_eligibility(0.02, 0.0299) == "N"
    assert _step_eligibility(0.02, 0.0301) == "T"


# ── 2) _extract_preclamp_delta 口径 ──────────────────────

def test_extract_preclamp_delta():
    d = _extract_preclamp_delta({
        "delta": {"market_sentiment": 0.4, "bank_credit_tightening": 0.25, "liquidity_premium": -0.1}
    })
    assert abs(d["market_sentiment"] - 0.4 * MONTHLY_SCALE) < 1e-9, "sentiment 必须 ×MONTHLY_SCALE"
    assert d["bank_credit_tightening"] == 0.25, "credit 走 else 分支无缩放"
    assert d["liquidity_premium"] == -0.1, "liquidity 走 else 分支无缩放"
    # 未写变量 → 0.0
    d2 = _extract_preclamp_delta({"delta": {}})
    assert d2["market_sentiment"] == 0.0 and d2["liquidity_premium"] == 0.0
    assert MONTHLY_SCALE == 0.25, "MONTHLY_SCALE 冻结 0.25"


# ── 3) 死变量豁免（qa-r2b blocking #2）──────────────────

def test_eligible_for_weighted():
    assert not _eligible_for_weighted({"sufficient": True, "dead": True, "silence_frac": 0.1}), "dead 必须排除"
    assert not _eligible_for_weighted({"sufficient": True, "dead": False, "silence_frac": 0.55}), "silence>0.50 必须排除"
    assert not _eligible_for_weighted({"sufficient": False, "dead": False, "silence_frac": 0.1}), "insufficient 必须排除"
    assert _eligible_for_weighted({"sufficient": True, "dead": False, "silence_frac": 0.20}), "三条件满足才可入池"


def test_weighted_exclusion_math():
    """模拟 run_probe 加权公式，验证 dead 变量即使 n_active≥20 也不投票。"""
    per_var = {
        "market_sentiment":       {"consistency_rate": 0.60, "eligible_for_weighted": True},
        "bank_credit_tightening": {"consistency_rate": 0.99, "eligible_for_weighted": False},  # dead 但高一致率
        "liquidity_premium":      {"consistency_rate": 0.60, "eligible_for_weighted": True},
    }
    w_ok = sum(ERROR_WEIGHTS[v] for v in ERROR_WEIGHTS if per_var[v]["eligible_for_weighted"])
    w_cons = sum(ERROR_WEIGHTS[v] * per_var[v]["consistency_rate"]
                 for v in ERROR_WEIGHTS if per_var[v]["eligible_for_weighted"])
    weighted = w_cons / w_ok
    # 若 dead 的 credit（0.99）错误入池，weighted=(0.4*0.6+0.35*0.99+0.25*0.6)=0.7065；
    # 正确排除后 = (0.4*0.6+0.25*0.6)/0.65 = 0.60
    assert abs(weighted - 0.60) < 1e-9, f"dead 变量不得投票，weighted={weighted}"


# ── 4) 守卫 A/B/C ───────────────────────────────────────

def _mk_agents(sens=1.0, mag=1.0):
    # 每个 Agent 独立 AgentParams（共享同一对象会互相污染，见 test_guard_b_collapse）
    def _p():
        return AgentParams(sensitivity=sens, threshold=0.5, magnitude=mag)
    return {aid: MacroAgent(agent_id=aid, role=f"r-{aid}", info_delay=1, activation_prob=0.5, params=_p())
            for aid in ("A1", "A2", "A3")}


def test_guard_a_pass_and_fail():
    agents = _mk_agents()
    # 活跃：每步 |d|≥0.005，无沉默
    ds = {v: [0.02] * 10 for v in ERROR_WEIGHTS}
    ts = {v: [0.1] * 10 for v in ERROR_WEIGHTS}
    g = check_guards([], agents, ds, ts, n_steps=10)
    assert g["A_active"]["pass"] is True
    # 沉默：目标有信号但 delta≈0 → silence_frac=1.0 → FAIL
    ds_sil = {v: [0.0] * 10 for v in ERROR_WEIGHTS}
    g2 = check_guards([], agents, ds_sil, ts, n_steps=10)
    assert g2["A_active"]["pass"] is False, "silence_frac=1.0 必须 FAIL"
    assert g2["all_pass"] is False


def test_guard_b_collapse():
    agents = _mk_agents(sens=1.0, mag=1.0)
    agents["A2"].params.sensitivity = 0.05
    agents["A2"].params.magnitude = 0.05
    ds = {v: [0.02] * 10 for v in ERROR_WEIGHTS}
    ts = {v: [0.1] * 10 for v in ERROR_WEIGHTS}
    g = check_guards([], agents, ds, ts, n_steps=10)
    assert "A2" in g["B_collapse"]["collapsed"]
    # 1 个塌缩 < 2 → pass
    assert g["B_collapse"]["pass"] is True
    # 2 个塌缩 → FAIL
    agents["A3"].params.sensitivity = 0.05
    agents["A3"].params.magnitude = 0.05
    g2 = check_guards([], agents, ds, ts, n_steps=10)
    assert g2["B_collapse"]["pass"] is False
    assert g2["all_pass"] is False


def test_guard_c_bands():
    agents = _mk_agents()
    ds = {v: [0.02] * 10 for v in ERROR_WEIGHTS}
    ts = {v: [0.1] * 10 for v in ERROR_WEIGHTS}
    assert check_guards([], agents, ds, ts, n_steps=10)["C_tuning"]["pass"] is False, "0 次调参=没发生校准"
    changes = [{"agent": "A2", "param": "threshold", "new": 0.4} for _ in range(15)]
    g = check_guards(changes, agents, ds, ts, n_steps=10)
    assert g["C_tuning"]["pass"] is True and g["C_tuning"]["n_changes"] == 15
    churn = [{"agent": "A2", "param": "threshold", "new": 0.4} for _ in range(60)]
    assert check_guards(churn, agents, ds, ts, n_steps=10)["C_tuning"]["pass"] is False, "churn>50 FAIL"


# ── 5) A2 触发线回归 + EASE ①决策层 ─────────────────────

def _a2():
    return CommercialBankAgent(
        agent_id="A2", role="commercial bank", info_delay=2, activation_prob=0.7,
        params=AgentParams(sensitivity=1.0, threshold=0.5, magnitude=1.0),
    )


def test_a2_grv_trigger_contract_line():
    """触发线契约（R4a 回退后=0.8×0.5=0.4）：0.35 不触发（R3 候选 0.3 线已回退）、
    0.45 触发、边界 0.4 严格 >。"""
    a2 = _a2()
    base = {"credit_spread": 200, "bank_credit_tightening": 0.3,
            "vix_stress": 0.1, "visible_actions": {}}
    # 0.35 ∈ (0.3, 0.4]：R3 候选线会触发，契约线 0.4 不触发 → 必须不收紧（回退实证）
    assert a2._decide_rules({**base, "grv_stress": 0.35}) != "TIGHTEN_CREDIT"
    # 0.45 > 0.4：契约线触发 → TIGHTEN
    assert a2._decide_rules({**base, "grv_stress": 0.45}) == "TIGHTEN_CREDIT"
    # 边界 0.4 严格 >：不触发（与 R3 的 0.3 边界语义一致）
    assert a2._decide_rules({**base, "grv_stress": 0.4}) != "TIGHTEN_CREDIT"


def test_a2_spread_trigger_unchanged():
    a2 = _a2()
    # spread 触发线 325 保持不动：spread=350 且 grv/vix 低 → 仍 TIGHTEN
    assert a2._decide_rules({"credit_spread": 350, "bank_credit_tightening": 0.3,
                             "grv_stress": 0.1, "vix_stress": 0.1, "visible_actions": {}}) == "TIGHTEN_CREDIT"


def test_ease_layer1_ctx():
    """锁定 _run_ease_probe ①决策层合成 ctx（QA R1 终局）→ EASE_CREDIT。"""
    a2 = _a2()
    ctx = {
        "credit_spread": 150.0,            # <250 easing ✓ / <325 tighten ✗
        "bank_credit_tightening": 0.3,     # <0.5 easing ✓
        "grv_stress": 0.1,                 # <0.25 easing ✓ / <0.3 tighten ✗
        "vix_stress": 0.1,                 # <0.35 tighten ✗
        "visible_actions": {},             # 无 hf SHORT / retail PANIC 挡死
    }
    assert a2._decide_rules(ctx) == "EASE_CREDIT", "①决策层 EASE 可达性必须成立"


# ── 6) R4a：S 类归因 ─────────────────────────────────────


def test_classify_a2_state():
    """R4a S 类归因三分类（纯函数）：冷却/激活门/决策无信号/实际行动残差。"""
    # 冷却中（countdown>0）→ rate_limit（info_delay 机制）
    assert classify_a2_state(2, False, False) == "rate_limit"
    assert classify_a2_state(1, False, True) == "rate_limit", "冷却优先于一切"
    # 未冷却 + 实际行动 → acted_other（A2 写了其他 var，对本 var 未写）
    assert classify_a2_state(0, True, True) == "acted_other"
    # 未冷却 + 未行动 + 通过激活门 → tighten_signal_false（决策层 HOLD）
    assert classify_a2_state(0, False, True) == "tighten_signal_false"
    # 未冷却 + 未行动 + 未通过激活门 → activation_gate（随机门）
    assert classify_a2_state(0, False, False) == "activation_gate"


def test_s_class_attribution_mapping():
    """R4a S 类→三分类计数语义（与 run_probe 落盘口径一致）：S 类=|t|≥EPS_TGT ∧ |d|<EPS_ACT。"""
    from core.calibrator import EPS_TGT, EPS_ACT
    # 构造模拟步序列（a2_state 已由 classify_a2_state 生成）
    steps = [
        {"d": 0.001, "t": 0.10, "state": "rate_limit"},             # S → rate_limit
        {"d": 0.001, "t": 0.10, "state": "activation_gate"},        # S → activation_gate
        {"d": 0.001, "t": -0.10, "state": "tighten_signal_false"},  # S → tighten_signal_false
        {"d": 0.02, "t": 0.10, "state": "acted_other"},             # T 类不计入 S
        {"d": 0.001, "t": 0.01, "state": "activation_gate"},        # |t|<EPS_TGT → N 类不计入
    ]
    counts = {"activation_gate": 0, "rate_limit": 0, "tighten_signal_false": 0,
              "acted_other": 0, "n_s": 0}
    for s in steps:
        if abs(s["t"]) >= EPS_TGT and abs(s["d"]) < EPS_ACT:
            counts["n_s"] += 1
            counts[s["state"]] += 1
    assert counts["n_s"] == 3, "只有前 3 步是 S 类"
    assert counts["rate_limit"] == 1 and counts["activation_gate"] == 1
    assert counts["tighten_signal_false"] == 1 and counts["acted_other"] == 0
    assert counts["rate_limit"] + counts["activation_gate"] + counts["tighten_signal_false"] == counts["n_s"]


# ── 主入口 ───────────────────────────────────────────────

def main():
    print(f"test_calibrator_guards: 共 {len(_PASSED)} 组用例")
    _t("test_eligibility_classes", test_eligibility_classes)
    _t("test_extract_preclamp_delta", test_extract_preclamp_delta)
    _t("test_eligible_for_weighted", test_eligible_for_weighted)
    _t("test_weighted_exclusion_math", test_weighted_exclusion_math)
    _t("test_guard_a_pass_and_fail", test_guard_a_pass_and_fail)
    _t("test_guard_b_collapse", test_guard_b_collapse)
    _t("test_guard_c_bands", test_guard_c_bands)
    _t("test_a2_grv_trigger_contract_line", test_a2_grv_trigger_contract_line)
    _t("test_a2_spread_trigger_unchanged", test_a2_spread_trigger_unchanged)
    _t("test_ease_layer1_ctx", test_ease_layer1_ctx)
    _t("test_classify_a2_state", test_classify_a2_state)
    _t("test_s_class_attribution_mapping", test_s_class_attribution_mapping)
    print(f"全部通过（{len(_PASSED)} 组，断言 ≥ 12 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
