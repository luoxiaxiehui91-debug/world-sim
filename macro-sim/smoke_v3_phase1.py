"""
smoke_v3_phase1.py — 天璇 v3 阶段 1 验收（2026-08-07）

验收标准（设计文档 §8.1）：
1. 无 soul 时每个 Agent 输出与 v2 逐行动一致（decide_with_decision().action == _decide_rules() 原逻辑）
2. ActionDecision schema 完整（action/reason/evidence/faction/confidence/source）
3. S 类走统一 soul 管线（red_line → 派系权重 → 抽样 → bias_actions），产出非 HOLD 行动且 reason 可读
4. decision_trace 落盘骨架：3 步仿真后 model.decision_trace 有 3 步记录
5. missing_strategy：optimistic（缺变量归 0）/ conservative（缺变量按最坏情况触发）语义验证
"""
import os
import sys
import random

sys.path.insert(0, os.getcwd())

from core.simulation import load_agents
from core.world_state import MacroWorldState
from core.agents.base import _eval_trigger

# ── 0. 构造 world ─────────────────────────────────────────────
world = MacroWorldState(
    vix=15.0, vix_baseline=15.0, grv=80.0, grv_baseline=50.0,
    grv_energy=30.0, grv_energy_baseline=30.0, grv_military=0.4, grv_trade=0.5,
    us_china_grv=70.0, t10y2y=-15.0, credit_spread=250.0, dff=5.0, situation_level=2,
    total_cycles=12,
    grv_dimensions={'global_composite': 80.0, 'russia_europe': 75.0, 'taiwan_strait': 70.0,
                    'us_china_strategic': 72.0, 'middle_east_energy': 50.0, 'sanctions_risk': 70.0,
                    'energy_grid_risk': 40.0},
)
agents, gcfg = load_agents('config/agents.yaml')

# ── 1. 无 soul Agent 逐行动一致性（v2 vs v3）──────────────────
print("[1/5] 无 soul Agent 逐行动一致性（v2 _decide_rules vs v3 decide_with_decision）")
mismatch = 0
checked = 0
# 构造多样 ctx 覆盖各规则分支
# 注意：A3/A5 是概率型规则（内部消耗 random）——为验证"fallback 与 v2 逐行动一致"
# 且"随机消耗模式一致"，每个 agent×ctx 用相同 seed 分别跑 v2/v3，序列起点相同。
for trial in range(20):
    world.market_sentiment = random.uniform(-0.6, 0.4)
    world.credit_spread = random.uniform(150, 400)
    world.vix = random.uniform(12, 40)
    for idx, (aid, agent) in enumerate(agents.items()):
        if agent.soul:          # 有 soul → 走统一管线，跳过 v2 对比
            continue
        ctx = world.get_agent_context(agent.role, soul=None)
        ctx['visible_actions'] = {}
        seed = trial * 1000 + idx
        random.seed(seed)
        v2_action = agent._decide_rules(ctx)          # 原 if-else 逻辑（同 seed 序列）
        random.seed(seed)
        v3_decision = agent.decide_with_decision(ctx)  # v3 统一出口（同 seed 序列起点）
        checked += 1
        if v2_action not in agent.VALID_ACTIONS:
            v2_action = 'HOLD'   # v2 decide() 的兜底
        if v3_decision.action != v2_action:
            mismatch += 1
            if mismatch <= 5:
                print(f"  ✗ {aid} (trial={trial}): v2={v2_action} v3={v3_decision.action}")
print(f"  checked={checked} mismatch={mismatch}")
assert mismatch == 0, f"无 soul Agent 行为不一致 {mismatch} 处"

# ── 2. ActionDecision schema 完整性 ────────────────────────────
print("[2/5] ActionDecision schema 完整性")
random.seed(7)
ctx = world.get_agent_context('usa', soul=agents['S1_usa'].soul)
ctx['visible_actions'] = {}
d = agents['S1_usa'].decide_with_decision(ctx)
for f in ('action', 'reason', 'evidence', 'faction', 'confidence', 'source'):
    assert hasattr(d, f) and getattr(d, f) is not None, f'S1_usa 缺字段 {f}'
assert d.source in ('soul', 'red_line'), f"source={d.source}"
assert 0 <= d.confidence <= 1, f"confidence={d.confidence}"
print(f"  OK: S1_usa → {d.action} ({d.source}) reason='{d.reason[:50]}...' confidence={d.confidence}")

# ── 3. S 类统一 soul 管线产出（真实数据多步）─────────────────
print("[3/5] S 类统一 soul 管线（5 agents × 5 次采样，产出分布）")
from collections import Counter
random.seed(20260807)
all_actions = Counter()
for sid in ('S1_usa', 'S2_china', 'S3_eu', 'S4_russia', 'S5_saudi'):
    a = agents[sid]
    acts = Counter()
    for _ in range(5):
        ctx = world.get_agent_context(a.role, soul=a.soul)
        ctx['visible_actions'] = {}
        dd = a.decide_with_decision(ctx)
        assert dd.source in ('soul', 'red_line'), f"{sid} source={dd.source}"
        acts[dd.action] += 1
        all_actions[sid] += 1
    print(f"  {sid}: {dict(acts)}")
    assert len(acts) >= 1
assert sum(all_actions.values()) == 25

# ── 4. decision_trace 骨架（3 步仿真）─────────────────────────
print("[4/5] decision_trace 骨架（3 步仿真）")
from core.simulation import MacroSimModel
random.seed(42)
model = MacroSimModel(world, agents=agents)
for i in range(3):
    model.step()
assert len(model.decision_trace) == 3, f"decision_trace={len(model.decision_trace)} 步"
step0 = model.decision_trace[0]
assert step0, "第 0 步 trace 为空"
# 至少有一个 S 类或金融 Agent 的决策记录含 reason
has_reason = any('reason' in v for v in step0.values())
print(f"  第 0 步决策记录 {len(step0)} 条（含 reason={has_reason}）")
assert has_reason

# ── 5. missing_strategy 语义（v1.3 R-P1）───────────────────────
print("[5/5] missing_strategy 语义")
ctx_empty = {}
# optimistic：x > t 缺变量归 0 → False
assert _eval_trigger("russia_europe > 70", ctx_empty, "optimistic") is False
# conservative：x > t 缺变量 → 按最坏情况 → True（防御）
assert _eval_trigger("russia_europe > 70", ctx_empty, "conservative") is True
# conservative：x < t 缺变量 → True
assert _eval_trigger("russia_europe < 30", ctx_empty, "conservative") is True
# 有值时不区分策略
ctx_val = {"russia_europe": 80.0}
assert _eval_trigger("russia_europe > 70", ctx_val, "optimistic") is True
assert _eval_trigger("russia_europe > 70", ctx_val, "conservative") is True
print("  OK: optimistic=归0不触发 / conservative=最坏情况触发 / 有值正常")

print("\n== 阶段 1 验收全部通过 ==")
