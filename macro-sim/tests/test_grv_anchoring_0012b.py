# -*- coding: utf-8 -*-
"""
回归测试：0012b GRV 锚定修复 —— grv_dimensions["global_composite"] 增量注入标量 world.grv
（macro-sim · 天璇）

目的
----
锁定 0012b 修复的传导链，防止 dict→标量 通道再次静默解耦（门控 vol_ratio 恒 0.001 根因）：
1. 预测期（inject_world=None）：本步 composite 增量【等量】注入标量 grv —— 传导链活着。
2. 缓和类行动（composite 下降）同向传导 —— 证明是【增量注入】而非只增棘轮（v1 整值覆盖 bug 的反面）。
3. 校准期（inject_world 非空）：注入被 `if not inject_world` 门控跳过 —— 校准轨迹不被污染。

方法（双跑对照隔离注入量）
--------------------------
同一起点 world 跑两次：一次让 gm_resolve_rules 把 global_composite 抬 BUMP（模拟 S 类主权行动
的 grv_impact_map，如 MILITARY_DEPLOYMENT: global_composite +N），一次不动。均值回归(:345)与
能源出血(:295)在两跑完全相同、自动抵消 → 两跑 grv 之差 == 本步注入的地缘增量。
gm_resolve_rules 用 monkeypatch 桩确定化 composite 增量（该函数本身由 test_calibrator_guards
的 gm 用例单独覆盖）；被测对象是 step() 内的锚定接线（起点捕获 pre + Phase 3.5 增量注入 + 门控）。

运行方式
--------
    cd /s/world-sim/macro-sim && python tests/test_grv_anchoring_0012b.py

自包含纯 Python 脚本，不依赖 pytest（macro-sim 未安装 pytest）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.simulation as sim_mod
from core.simulation import MacroSimModel
from core.world_state import MacroWorldState
from core.agents.base import MacroAgent, AgentParams

_PASSED = []


def _t(name, fn):
    fn()
    _PASSED.append(name)
    print(f"  ✓ {name}")


# ── 桩与工装 ─────────────────────────────────────────────

def _stub_gm(bump):
    """替身 gm_resolve_rules：把 global_composite 抬 bump（模拟 S 类行动写地缘维度），
    返回空 delta（不触碰金融变量，_apply_delta 为 no-op）。被测的是 step() 的锚定接线，
    非 gm 本身。"""
    def _f(actions, world, agents, cfg):
        gd = world.grv_dimensions
        gd["global_composite"] = gd.get("global_composite", 0.0) + bump
        return {}
    return _f


def _mk_world(grv=60.0, composite=55.0):
    """最小真实 MacroWorldState（补齐所有无默认字段）。baseline==value 使均值回归为 no-op，
    化简推理；两跑差值本就抵消 decay/bleed，此处仅为可读。"""
    return MacroWorldState(
        vix=20.0, vix_baseline=20.0,
        grv=grv, grv_baseline=grv,
        grv_energy=20.0, grv_energy_baseline=20.0,
        grv_military=30.0, grv_trade=30.0,
        us_china_grv=50.0, t10y2y=-10.0,
        credit_spread=200.0, dff=5.0, situation_level=2,
        grv_dimensions={"global_composite": composite, "us_china_strategic": 50.0},
    )


def _mk_sim(world):
    """单个惰性 agent（activation_prob=0 → 永不行动 → step 不触碰 get_agent_context）；
    global_cfg 由构造函数置空。step() 的地缘增量全由 _stub_gm 提供。"""
    agent = MacroAgent(agent_id="S1", role="sovereign-test", info_delay=1,
                       activation_prob=0.0,
                       params=AgentParams(sensitivity=1.0, threshold=0.5, magnitude=1.0))
    return MacroSimModel(world, agents={"S1": agent},
                         governance_enabled=False, force_activate_all=False)


def _diff_two_runs(bump, inject_world):
    """同起点跑两次（act=composite+bump / non=composite 不变），返回 act.grv - non.grv。
    decay/bleed 两跑相同 → 差值 == 本步锚定注入的地缘增量。"""
    orig = sim_mod.gm_resolve_rules
    try:
        w_act = _mk_world()
        sim_mod.gm_resolve_rules = _stub_gm(bump)
        _mk_sim(w_act).step(inject_world=inject_world)

        w_non = _mk_world()
        sim_mod.gm_resolve_rules = _stub_gm(0.0)
        _mk_sim(w_non).step(inject_world=inject_world)
    finally:
        sim_mod.gm_resolve_rules = orig
    return w_act.grv - w_non.grv


# ── 1) 预测期：composite 增量等量注入标量 grv ─────────────

def test_prediction_composite_delta_reaches_scalar():
    """核心传导：预测期 S 类行动抬 global_composite +7 → 标量 grv 同步 +7
    （若 Phase 3.5 或起点 pre 捕获被删/接错，diff 归零 → 本用例 FAIL，杜绝静默解耦）。"""
    diff = _diff_two_runs(bump=7.0, inject_world=None)
    assert abs(diff - 7.0) < 1e-6, f"预测期 composite +7 必须等量注入标量 grv（实测 diff={diff}）"


# ── 2) 缓和类行动：负增量同向传导（非棘轮）────────────────

def test_negative_composite_delta_also_reaches_scalar():
    """缓和类行动（如 CEASEFIRE_SIGNAL: global_composite -8）→ 标量 grv 同向下降 -8。
    证明是【增量注入】：正负对称、可回落——v1 整值覆盖会让冲击只增不减（永久棘轮），此用例即其反面守卫。"""
    diff = _diff_two_runs(bump=-8.0, inject_world=None)
    assert abs(diff - (-8.0)) < 1e-6, f"缓和行动 composite -8 必须同向注入标量 grv（实测 diff={diff}）"


# ── 3) 校准期：门控跳过注入（校准轨迹不被污染）────────────

def test_calibration_period_skips_injection():
    """校准期（inject_world 非空）：`if not inject_world` 门控必须跳过注入 →
    composite 抬 7 也不入标量 grv（diff==0）。护栏失效则校准逐点拟合被地缘增量污染。"""
    diff = _diff_two_runs(bump=7.0, inject_world={"market_sentiment": -0.3})
    assert abs(diff) < 1e-9, f"校准期必须跳过注入，标量 grv 不受 composite 影响（实测 diff={diff}）"


# ── 4) 无行动步：Δ=0 为 no-op（不引入漂移）────────────────

def test_no_action_step_is_noop_on_injection():
    """无 S 类行动（composite 不动）时锚定注入为 no-op：预测期与校准期 grv 轨迹逐点一致
    （证明本次修复不改变裸推/无信号世界的既有行为）。"""
    orig = sim_mod.gm_resolve_rules
    try:
        w_pred = _mk_world()
        sim_mod.gm_resolve_rules = _stub_gm(0.0)
        _mk_sim(w_pred).step(inject_world=None)

        w_cal = _mk_world()
        sim_mod.gm_resolve_rules = _stub_gm(0.0)
        _mk_sim(w_cal).step(inject_world={"market_sentiment": 0.0})
    finally:
        sim_mod.gm_resolve_rules = orig
    # market_sentiment 注入在校准期只覆盖内生变量，不碰 grv 通道 → 两跑 grv 必须逐点一致
    assert abs(w_pred.grv - w_cal.grv) < 1e-9, \
        f"Δ=0 时锚定为 no-op，预测/校准 grv 应一致（pred={w_pred.grv} cal={w_cal.grv}）"


# ── 主入口 ───────────────────────────────────────────────

def main():
    print("test_grv_anchoring_0012b: GRV 锚定增量注入传导链")
    _t("test_prediction_composite_delta_reaches_scalar", test_prediction_composite_delta_reaches_scalar)
    _t("test_negative_composite_delta_also_reaches_scalar", test_negative_composite_delta_also_reaches_scalar)
    _t("test_calibration_period_skips_injection", test_calibration_period_skips_injection)
    _t("test_no_action_step_is_noop_on_injection", test_no_action_step_is_noop_on_injection)
    print(f"全部通过（{len(_PASSED)} 组）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
