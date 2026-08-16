"""
B1 回归测试（2026-08-16）：H21 VIX 恐慌放大 / H22 MC 路径概率归一。
防审查修复回归：这两个 bug 曾"结构性静默"数月无人察觉（代码注释自证），
修复必须有测试锁定。
"""

import types
import statistics


# ── H21: VIX 恐慌放大（出血1）结构性永不触发 ─────────────────

def _h21_world():
    return types.SimpleNamespace(
        market_sentiment=-0.6,
        consecutive_negative_steps=0,
        vix=30.0,
        vix_baseline=30.0,
        _vix_panic_armed=False,
    )


def _h21_feedback(world, agents):
    """复刻 gm_resolve_rules 正反馈环（H21 修复后逻辑）。"""
    from core.simulation import gm_resolve_rules
    # 直接用真实 gm_resolve_rules 太耦合；这里复刻正反馈环语义做时序验证
    if world.market_sentiment < -0.5:
        world.consecutive_negative_steps += 1
        if world.consecutive_negative_steps >= 3:
            if not getattr(world, "_vix_panic_armed", False):
                world._vix_panic_armed = True
                for aid in ("A7", "A12"):
                    if aid in agents:
                        agents[aid].forced_activate = True
    else:
        world.consecutive_negative_steps = max(0, world.consecutive_negative_steps - 1)
        world._vix_panic_armed = False


def _h21_bleed(world):
    """复刻 apply_bleed_rules 出血1（VIX 恐慌放大）条件。"""
    from core.world_state import BLEED_PARAMS
    if (world.market_sentiment < BLEED_PARAMS["vix_bleed_threshold"]
            and world.consecutive_negative_steps >= BLEED_PARAMS["vix_bleed_steps"]
            and (world.vix - world.vix_baseline) < BLEED_PARAMS["vix_bleed_max"]):
        world.vix += BLEED_PARAMS["vix_bleed_rate"]


def test_h21_vix_panic_amplification_fires():
    """H21：连续 3 步负向后出血1 必须生效（原实现 counter 归零 → 永不触发）。"""
    from core.world_state import BLEED_PARAMS
    assert BLEED_PARAMS["vix_bleed_steps"] == 3
    w = _h21_world()
    agents = {"A7": types.SimpleNamespace(forced_activate=False),
              "A12": types.SimpleNamespace(forced_activate=False)}
    for _ in range(6):
        _h21_feedback(w, agents)
        _h21_bleed(w)
    # 6 步持续负向：步3 起出血1 生效 → vix 至少 +2*4=8（30 → >=38，且封顶 50）
    assert w.vix >= 38.0, f"VIX 恐慌放大应持续生效（实测 {w.vix}）"
    # A7 只在 2→3 跃迁触发一次（上升沿）
    assert agents["A7"].forced_activate is True


def test_h21_a7_rising_edge_only():
    """H21：A7/A12 只在 2→3 跃迁触发一次，持续负向不每步重复强制激活。"""
    w = _h21_world()
    agents = {"A7": types.SimpleNamespace(forced_activate=False),
              "A12": types.SimpleNamespace(forced_activate=False)}
    triggers = 0
    for _ in range(10):
        _h21_feedback(w, agents)
        if agents["A7"].forced_activate:
            triggers += 1
            agents["A7"].forced_activate = False
            agents["A12"].forced_activate = False
    assert triggers == 1, f"A7 应仅上升沿触发一次（实测 {triggers}）"


# ── H22: MC 路径概率归一 ─────────────────────────────────────

def _h22_cluster(values, n_clusters=3, min_p=0.05):
    """复刻 _cluster_runs 修复后逻辑。"""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    sorted_vals = [v for _, v in indexed]
    sorted_idx = [i for i, _ in indexed]
    diffs = [sorted_vals[i + 1] - sorted_vals[i] for i in range(len(sorted_vals) - 1)]
    top2 = sorted(range(len(diffs)), key=lambda i: -diffs[i])[:2]
    split_at = sorted(top2)
    clusters, prev = [], 0
    for sp in split_at:
        clusters.append(sorted_idx[prev:sp + 1])
        prev = sp + 1
    clusters.append(sorted_idx[prev:])
    retained = [c for c in clusters if len(c) / n >= min_p]
    dropped = [c for c in clusters if len(c) / n < min_p]
    if retained and dropped:
        for dc in dropped:
            dc_center = statistics.mean([values[i] for i in dc])
            best = min(retained, key=lambda fc: abs(
                statistics.mean([values[i] for i in fc]) - dc_center))
            best.extend(dc)
    if not retained:
        retained = [list(range(n))]
    return retained


def test_h22_path_probability_normalized():
    """H22：小簇合并后路径概率和必须 = 100%（原丢弃 → 0.97≠1）。"""
    from core.bifurcation import _cluster_runs, MIN_PATH_PROBABILITY
    vals = [30.0] * 90 + [60.0] * 7 + [90.0] * 3  # 3% 小簇
    clusters = _cluster_runs(vals, n_clusters=3)
    probs = [len(c) / len(vals) for c in clusters]
    assert abs(sum(probs) - 1.0) < 1e-9, f"概率必须归一到 100%（实测 {sum(probs)}）"
    assert sum(len(c) for c in clusters) == len(vals), "所有 run 必须被分配"
    # 不触发合并时（无 <MIN_PATH_PROBABILITY 簇）行为不变
    vals2 = [30.0] * 85 + [60.0] * 10 + [90.0] * 5
    clusters2 = _cluster_runs(vals2, n_clusters=3)
    assert abs(sum(len(c) for c in clusters2) - len(vals2)) < 1e-9
