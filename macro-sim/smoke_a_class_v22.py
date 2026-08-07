"""A 类激活 v2.2 本地 smoke 验证脚本（验证后删除）"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.simulation import load_agents, MacroSimModel
from core.world_state import MacroWorldState
from core.board_baseline import derive_board_baseline, get_board_ctx
from core.agents.sovereign import _eval_trigger

print("=" * 60)
print("[1/5] load_agents: 17 个 Agent 加载")
agents, gcfg = load_agents(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config/agents.yaml"))
s_ids = [a for a in agents if a.startswith("S")]
print(f"  加载 {len(agents)} agents, S 类: {s_ids}")
assert len(agents) == 17, f"期望 17, 实际 {len(agents)}"
assert len(s_ids) == 5, f"期望 5 S 类, 实际 {len(s_ids)}"
assert agents["A4"].activation_prob == 0, "A4 应挂起"
assert agents["A4"].soul == {}, "A4 soul 应已移除"
assert agents["A6"].soul == {}, "A6 soul 应已移除"
for sid in s_ids:
    assert agents[sid].soul, f"{sid} soul 未加载"
print("  OK: 17 agents, A4/A6 无 soul, S1-S5 有 soul")

print("[2/5] S 类 ctx 供给（D1 验证）")
world = MacroWorldState(
    vix=15.0, vix_baseline=15.0,
    grv=80.0, grv_baseline=50.0,
    grv_energy=30.0, grv_energy_baseline=30.0,
    grv_military=0.4, grv_trade=0.5, us_china_grv=70.0,
    t10y2y=-15.0, credit_spread=250.0, dff=5.0, situation_level=2,
    total_cycles=12,
    grv_dimensions={
        "global_composite": 80.0, "russia_europe": 65.0, "taiwan_strait": 55.0,
        "us_china_strategic": 70.0, "middle_east_energy": 50.0,
        "sanctions_risk": 45.0, "energy_grid_risk": 40.0,
    },
)
ctx = world.get_agent_context("russia", soul=agents["S4_russia"].soul)
missing = [k for k in ("russia_europe", "taiwan_strait", "us_china_strategic",
                       "global_composite", "middle_east_energy", "sanctions_risk",
                       "energy_grid_risk", "economic_buffer_months",
                       "domestic_political_pressure", "wti_price") if k not in ctx]
print(f"  russia ctx: russia_europe={ctx.get('russia_europe')} economic_buffer_months={ctx.get('economic_buffer_months')}")
assert not missing, f"S 类 ctx 缺失变量: {missing}"
print(f"  OK: 全部 trigger 变量已供给（缺失: {missing or '无'}）")

print("[3/5] red_line_triggers 可判定（D2 验证）")
t1 = _eval_trigger("russia_europe > 75 AND sanctions_risk > 65", ctx)
t2 = _eval_trigger("russia_europe > 70", ctx)
print(f"  russia_europe=65, sanctions_risk=45: '>75 AND >65'={t1}（期望 False）, '>70'={t2}（期望 False）")
assert t1 == False and t2 == False
ctx_high = dict(ctx); ctx_high["russia_europe"] = 78.0; ctx_high["sanctions_risk"] = 70.0
t3 = _eval_trigger("russia_europe > 75 AND sanctions_risk > 65", ctx_high)
print(f"  高压场景 russia_europe=78: '>75 AND >65'={t3}（期望 True）")
assert t3 == True
print("  OK: red_line_triggers 数值判定正常")

print("[4/5] 3 步仿真：S 类行动产生 + GRV delta 直写 + Board")
derive_board_baseline(world.grv_dimensions)
random.seed(42)
model = MacroSimModel(world, agents=agents)
s_act_seen = {}
sanctions_before = world.grv_dimensions.get("sanctions_risk")
for i in range(3):
    snap = model.step()
    acts = snap.get("actions", {})
    s_acts = {k: v for k, v in acts.items() if k.startswith("S")}
    for k, v in s_acts.items():
        s_act_seen[k] = v
    print(f"  step{i}: S行动={s_acts or '无'}")
sanctions_after = world.grv_dimensions.get("sanctions_risk")
print(f"  sanctions_risk: {sanctions_before} -> {sanctions_after}")
ctx_b = get_board_ctx("S1_usa")
print(f"  S1_usa Board ctx: {ctx_b}")
# 断言：3 步内至少 1 个 S 行动（activation 0.3 × 5 agents × 3 步，期望 ~4.5 次）
assert s_act_seen, "3 步内 S 类零行动——激活链路故障"
print(f"  OK: S 类产生行动 {s_act_seen}")

print("[5/5] Board 基线 /100 归一化（A5 验证）")
baseline = derive_board_baseline(world.grv_dimensions)
b_s1s2 = baseline[("S1_usa", "S2_china")]
cur_us_china = world.grv_dimensions.get("us_china_strategic")
print(f"  S1-S2 strategic_rivalry: rel={b_s1s2['rel']} intensity={b_s1s2['intensity']}（当前 us_china={cur_us_china} → 期望 {cur_us_china/100:.2f}）")
assert abs(b_s1s2["intensity"] - cur_us_china / 100.0) < 1e-6, "Board 强度应 = GRV/100"
b_s1s5 = baseline[("S1_usa", "S5_saudi")]
assert abs(b_s1s5["intensity"] - 0.60) < 1e-6
print(f"  OK: Board 基线归一化正确（美沙常量 0.60）")

print("=" * 60)
print("SMOKE 全部通过")
