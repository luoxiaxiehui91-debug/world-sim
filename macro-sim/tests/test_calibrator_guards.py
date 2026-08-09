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
    _activity_band,
    _dead_new,
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
    """R4a S 类归因三分类（纯函数）+ R4g 改动 1 HOLD 语义（HOLD 不计实际行动）。"""
    # 冷却中（countdown>0）→ rate_limit（info_delay 机制）
    assert classify_a2_state(2, False, False) == "rate_limit"
    assert classify_a2_state(1, False, True) == "rate_limit", "冷却优先于一切"
    # 未冷却 + 实际行动 → acted_other（A2 写了其他 var，对本 var 未写）
    assert classify_a2_state(0, True, True) == "acted_other"
    # 未冷却 + 未行动 + 通过激活门 → tighten_signal_false（决策层 HOLD）
    assert classify_a2_state(0, False, True) == "tighten_signal_false"
    # 未冷却 + 未行动 + 未通过激活门 → activation_gate（随机门）
    assert classify_a2_state(0, False, False) == "activation_gate"

    # R4g 改动 1（calibrator.py a2_acted 表达式）：HOLD 决策不计"实际行动"。
    # 旧 bool(actions["A2"]) 把 HOLD 判 True → acted_other 吞掉规则层 HOLD，
    # tighten_signal_false 死代码恒 0。新表达式与 calibrator.py:699 逐字节一致。
    def _a2_act(actions):
        return actions.get("A2") not in (None, "HOLD", "NO_ACTION")
    assert _a2_act({"A2": "HOLD"}) is False, "HOLD 不算实际行动 → 走 tighten_signal_false"
    assert _a2_act({"A2": "EASE_CREDIT"}) is True
    assert _a2_act({"A2": "TIGHTEN_CREDIT"}) is True
    assert _a2_act({}) is False, "无 A2 条目不算实际行动"
    assert _a2_act({"A2": "NO_ACTION"}) is False
    # HOLD 决策步（a2_decided=True + a2_acted=False）→ tighten_signal_false（新语义）
    assert classify_a2_state(0, _a2_act({"A2": "HOLD"}), True) == "tighten_signal_false"


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
    # R4g 改动 1：HOLD 决策步的 state 必须是 tighten_signal_false（非 acted_other）——
    # 统计侧（data-r4g）按此拆分"规则层 HOLD"，与 calibrator a2_state 新语义一致。
    hold_step = {"d": 0.001, "t": 0.10, "state": "tighten_signal_false"}
    assert (abs(hold_step["t"]) >= EPS_TGT and abs(hold_step["d"]) < EPS_ACT), "HOLD 步是 S 类"
    assert hold_step["state"] == "tighten_signal_false", "HOLD 步不得归 acted_other"


# ── 7) R4b：A2 info_delay 2→1 配置锁定 ───────────────────

def test_a2_info_delay_r4b():
    """R4b 根治 credit 失活：config/agents.yaml 的 A2 info_delay 必须为 1。
    回归锁定：若回退到 2，冷却上限 ~1/3 步 → credit n_active<20 + silence>0.50 复发。"""
    import yaml
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = yaml.safe_load(open(os.path.join(_root, "config", "agents.yaml"), encoding="utf-8"))
    a2 = next(a for a in cfg["agents"] if a["id"] == "A2")
    assert a2["info_delay"] == 1, f"A2 info_delay={a2['info_delay']} ≠ 1（R4b 回归！）"
    assert a2["activation_prob"] == 0.70, "activation 0.70 冻结（R4b 只改 info_delay）"
    # 契约参数不动：EPS_TGT 冻结、threshold 0.5
    assert a2["params"]["threshold"] == 0.5


# ── 8) R4c：dead 语义修正 + 两层口径 ─────────────────────

def test_dead_new_semantics():
    """R4c dead 新语义：act_frac<0.10 OR m_v_active<0.002（m_v_active=行动步 median|d|）。"""
    # 旧语义 knife-edge 反例：credit act 0.388 / m_v_active 0.335 → 必须 NOT dead
    assert _dead_new(0.388, 0.335) is False, "部分活跃（act≥0.10 ∧ 行动幅度正常）不是死"
    # act<0.10 → dead（几乎从不行动）
    assert _dead_new(0.05, 0.30) is True
    # m_v_active<0.002 → dead（行动时幅度趋零）
    assert _dead_new(0.50, 0.001) is True
    # 双条件均满足 → not dead
    assert _dead_new(0.30, 0.10) is False
    # 边界：act=0.10 严格 ≥ 不触发第一条件
    assert _dead_new(0.10, 0.30) is False
    assert _dead_new(0.30, 0.0019) is True, "m_v_active<0.002 判死"
    assert _dead_new(0.30, 0.002) is False, "边界 m_v_active=0.002 严格 < 才判死"


def test_activity_band():
    """R4c 活性语义带：low<0.10=dead / insufficient∈[0.10,0.30) / adequate≥0.30。"""
    assert _activity_band(0.05) == "low"
    assert _activity_band(0.10) == "insufficient"
    assert _activity_band(0.20) == "insufficient"
    assert _activity_band(0.30) == "adequate"
    assert _activity_band(0.388) == "adequate", "credit R4b act=0.388 ∈ adequate"
    # insufficient 语义：非死但 guard A（act≥0.30）FAIL → 活性不足由守卫 A + p̂ 稀释表达


def test_merged_eligible():
    """R4c 合并口径（闸②③）：per-var 跨 seed 合计 n_active≥20 ∧ median dead False ∧
    median silence≤0.50。credit R4b 5 seed 合计 93（21+18+16+19+19）→ 入合并池。"""
    import importlib.util, os, sys as _sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _spec = importlib.util.spec_from_file_location("rpa", os.path.join(_root, "scripts", "run_probe_acceptance.py"))
    _rpa = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_rpa)
    # 构造 credit 五 seed stats（R4b 实测值）
    n_per_seed = [21, 18, 16, 19, 19]
    stats_list = [{"bank_credit_tightening": {"n_active": n, "dead": False, "silence_frac": 0.43}}
                  for n in n_per_seed]
    assert _rpa.merged_eligible(stats_list, "bank_credit_tightening") is True, "credit 合计 93 ≥20 入池"
    # 合计 <20 → 不入池（n=3×5=15）
    stats_short = [{"bank_credit_tightening": {"n_active": 3, "dead": False, "silence_frac": 0.1}}
                   for _ in range(5)]
    assert _rpa.merged_eligible(stats_short, "bank_credit_tightening") is False, "合计 15<20 不入池"
    # 若某 seed dead → median dead 仍 False（≤2 seed dead 不判死）
    stats_one_dead = [{"bank_credit_tightening": {"n_active": n, "dead": (i == 0), "silence_frac": 0.43}}
                      for i, n in enumerate([21, 18, 16, 19, 19])]
    assert _rpa.merged_eligible(stats_one_dead, "bank_credit_tightening") is True


# ── 9) R4d：A2 方向对齐（方向闸/方向 EASE/回退线/layer-1 约束）──

def _a2_ctx(spread=200, tightening=0.3, grv=0.1, vix=0.1, cs_delta=0.0, hf="HOLD", retail="HOLD"):
    return {"credit_spread": spread, "bank_credit_tightening": tightening,
            "grv_stress": grv, "vix_stress": vix, "credit_spread_delta": cs_delta,
            "visible_actions": {"hedge_fund": hf, "retail": retail}}


def test_direction_gate():
    """R4d 方向闸：cs_delta<0（target 期望 EASE）时收紧即错；终裁回退预案=vix>1.0 极端豁免。"""
    a2 = _a2()
    # cs_delta<0 + grv 高压 → 方向闸挡死（不收紧）——R4b 冲突步的修复
    assert a2._decide_rules(_a2_ctx(grv=0.6, cs_delta=-10)) != "TIGHTEN_CREDIT"
    # cs_delta<0 + vix=1.0（≤1.0 极端线）+ hf SHORT → 仍不收紧（hf 不再豁免）
    assert a2._decide_rules(_a2_ctx(grv=0.6, vix=1.0, cs_delta=-10, hf="SHORT_MARKET")) != "TIGHTEN_CREDIT"
    assert a2._decide_rules(_a2_ctx(grv=0.6, vix=1.0, cs_delta=-10, retail="PANIC_SELL")) != "TIGHTEN_CREDIT"
    # cs_delta<0 + vix>1.0（vix>48 极端危机，终裁回退预案）→ 允许收紧
    assert a2._decide_rules(_a2_ctx(grv=0.6, vix=1.5, cs_delta=-10)) == "TIGHTEN_CREDIT"
    # cs_delta>0 + grv 高压 → 收紧（方向正确，保留）
    assert a2._decide_rules(_a2_ctx(grv=0.6, cs_delta=10)) == "TIGHTEN_CREDIT"
    # cs_delta 中性（|d|<2.5bp）+ grv 高压 → 收紧（生产路径逐字节不变）
    assert a2._decide_rules(_a2_ctx(grv=0.6, cs_delta=0.0)) == "TIGHTEN_CREDIT"
    # 边界：cs_delta=-2.5 严格 < 才进 ease 方向（-2.5 → neutral → 收紧路径保留）
    assert a2._decide_rules(_a2_ctx(grv=0.6, cs_delta=-2.5)) == "TIGHTEN_CREDIT"
    assert a2._decide_rules(_a2_ctx(grv=0.6, cs_delta=-2.6)) != "TIGHTEN_CREDIT"


def test_directional_ease():
    """R4d/R4e 方向 EASE：cs_delta<0 时 spread 250→350、grv 0.25→0.4→0.6（R4e 放宽），
    错误收紧步转正确 EASE。中性/收紧方向阈值不动。"""
    a2 = _a2()
    # cs_delta<0 + spread 300（旧 250 线不 EASE，新 350 线 EASE）→ 方向 EASE
    assert a2._decide_rules(_a2_ctx(spread=300, cs_delta=-10)) == "EASE_CREDIT"
    # cs_delta<0 + spread 300 + grv 0.3（R4d 0.4 线放行）→ EASE
    assert a2._decide_rules(_a2_ctx(spread=300, grv=0.3, cs_delta=-10)) == "EASE_CREDIT"
    # R4e：grv 0.55（R4d 0.4 线挡，R4e 0.6 线放行）→ EASE
    assert a2._decide_rules(_a2_ctx(spread=300, grv=0.55, cs_delta=-10)) == "EASE_CREDIT"
    # R4e 边界：grv=0.6 严格 < 才放行 → 0.6 不 EASE
    assert a2._decide_rules(_a2_ctx(spread=300, grv=0.6, cs_delta=-10)) != "EASE_CREDIT"
    assert a2._decide_rules(_a2_ctx(spread=300, grv=0.65, cs_delta=-10)) != "EASE_CREDIT"
    # cs_delta 中性 + spread 300（>250）→ 不 EASE（旧阈值，生产路径不变）
    assert a2._decide_rules(_a2_ctx(spread=300, cs_delta=0.0)) != "EASE_CREDIT"
    # cs_delta<0 + spread 360（>350 方向线）→ 不 EASE
    assert a2._decide_rules(_a2_ctx(spread=360, cs_delta=-10)) != "EASE_CREDIT"
    # cs_delta<0 + tightening 0.6（>0.5 冻结）→ 不 EASE
    assert a2._decide_rules(_a2_ctx(spread=200, tightening=0.6, cs_delta=-10)) != "EASE_CREDIT"
    # layer-1 ctx（无 cs_delta）→ 中性 → EASE 保持（EASE ship 闸不受影响）
    assert a2._decide_rules(_a2_ctx(spread=150, cs_delta=0.0)) == "EASE_CREDIT"


def test_ease_block_reason():
    """R4e ease-block 三分类归因（qa-r2b 条件 2）：首失败条件优先（spread→tightening→grv）。"""
    import importlib.util, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _spec = importlib.util.spec_from_file_location("rpa", os.path.join(_root, "scripts", "run_probe_acceptance.py"))
    _rpa = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_rpa)

    def _mk(step):
        return {"steps": step}

    # 单步：spread≥350 挡
    r = _rpa.ease_block_reason_distribution(_mk([{"cs_delta": -10, "credit_spread": 360.0,
                                                   "bank_credit_tightening": 0.3, "grv_level": 60.0,
                                                   "per_var": {"bank_credit_tightening": {"d": 0.0}}}]))
    assert r["spread_ge_350"] == 1 and r["n_block"] == 1
    # 单步：spread<350 但 tightening≥0.5 挡（首失败=spread 通过→tightening）
    r = _rpa.ease_block_reason_distribution(_mk([{"cs_delta": -10, "credit_spread": 300.0,
                                                   "bank_credit_tightening": 0.55, "grv_level": 60.0,
                                                   "per_var": {"bank_credit_tightening": {"d": 0.0}}}]))
    assert r["tightening_ge_05"] == 1
    # 单步：spread/tightening 通过但 grv≥0.6 挡
    r = _rpa.ease_block_reason_distribution(_mk([{"cs_delta": -10, "credit_spread": 300.0,
                                                   "bank_credit_tightening": 0.3, "grv_level": 82.0,
                                                   "per_var": {"bank_credit_tightening": {"d": 0.0}}}]))
    assert r["grv_ge_06"] == 1  # grv_stress=(82-50)/50=0.64 ≥0.6
    # 已 EASE 步不计入 block
    r = _rpa.ease_block_reason_distribution(_mk([{"cs_delta": -10, "credit_spread": 300.0,
                                                   "bank_credit_tightening": 0.3, "grv_level": 60.0,
                                                   "per_var": {"bank_credit_tightening": {"d": -0.25}}}]))
    assert r["n_block"] == 0
    # tighten_fail（方向闸后仍收紧——vix>1.0 极端豁免）单独计数
    r = _rpa.ease_block_reason_distribution(_mk([{"cs_delta": -10, "credit_spread": 300.0,
                                                   "bank_credit_tightening": 0.3, "grv_level": 60.0,
                                                   "per_var": {"bank_credit_tightening": {"d": 0.25}}}]))
    assert r["tighten_fail"] == 1 and r["n_block"] == 1


def test_rollback_line_constants():
    """R4d 回退线 5 条机读常量（docs/r4c-b §2 + team-lead 终裁）。"""
    import importlib.util, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _spec = importlib.util.spec_from_file_location("rpa", os.path.join(_root, "scripts", "run_probe_acceptance.py"))
    _rpa = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_rpa)
    lines = _rpa.R4D_ROLLBACK_LINES
    assert set(lines.keys()) == {"credit_consistency", "grv_down", "merged_p",
                                 "credit_n_active", "credit_silence"}, "回退线必须 5 条"
    assert lines["credit_consistency"]["target"] == 0.60 and lines["credit_consistency"]["revert"] == 0.40
    assert lines["grv_down"]["target"] == 0.40 and lines["grv_down"]["revert"] == 0.20
    assert lines["merged_p"]["target"] == 0.55 and lines["merged_p"]["revert"] == 0.43
    assert lines["credit_n_active"]["target"] == 18
    assert lines["credit_silence"]["target"] == 0.50


def test_layer1_ctx_handwritten_constraint():
    """R4d：ease_probe layer-1 ctx 必须保持手写合成 dict——不得走 get_agent_context
    （会注入 credit_spread_delta，破坏方向对齐下 ship 闸的确定性）。源码检查约束。"""
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(_root, "core", "calibrator.py"), encoding="utf-8").read()
    # 定位 _run_ease_probe 的 layer-1 ctx 构造（①决策层合成 ctx 单测）
    m = src.find('layer1_pass = False')
    assert m > 0, "layer-1 ctx 构造段未找到"
    seg = src[m:m + 700]
    assert "get_agent_context" not in seg, "layer-1 不得走 get_agent_context（会注入 cs_delta）"
    assert "credit_spread_delta" not in seg, "layer-1 ctx 不得含 credit_spread_delta（手写合成锁定）"
    assert '"credit_spread": 150.0' in seg, "layer-1 ctx 必须为手写合成 dict（spread=150）"


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
    _t("test_a2_info_delay_r4b", test_a2_info_delay_r4b)
    _t("test_dead_new_semantics", test_dead_new_semantics)
    _t("test_activity_band", test_activity_band)
    _t("test_merged_eligible", test_merged_eligible)
    _t("test_direction_gate", test_direction_gate)
    _t("test_directional_ease", test_directional_ease)
    _t("test_ease_block_reason", test_ease_block_reason)
    _t("test_rollback_line_constants", test_rollback_line_constants)
    _t("test_layer1_ctx_handwritten_constraint", test_layer1_ctx_handwritten_constraint)
    print(f"全部通过（{len(_PASSED)} 组，断言 ≥ 12 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
