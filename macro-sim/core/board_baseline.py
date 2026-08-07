"""
board_baseline.py — Board 基线派生器（v2.2，activation §3.3 + A5 量纲修复）

设计（用户"动态 + 数值不确定"两点 + QClaw deepreview2 A5）：
- Board 是动态场：基线每天随 GRV 变（跨仿真），行动偏离随步衰减回基线（仿真内）
- 强度 = 当日 GRV 维度分数映射 / 100 归一化（A5：board_set clamp [0,1]，GRV 0-100 直传会饱和）
- 语义锚点（0-100 含义，/100 后 0-1）：<0.30 合作 | 0.30-0.60 紧张 | 0.60-0.80 对抗 | >0.80 冲突边缘
- 常量关系对：美沙安保 60、中沙贸易 45（GRV 无直接维度）

模块级状态（跨仿真）：
  _baseline: 当日基线（derive_board_baseline 重置，来自 GRV）
  _board_cur: 仿真内当前场（行动 push 偏离 + board_decay_step 每步 ×0.95 衰减回基线）
"""

# 关系对 → (rel 语义名, GRV 维度名)；dim=None 表示常量关系对
REL_SPEC = {
    ("S1_usa",   "S2_china"):  ("strategic_rivalry",  "us_china_strategic"),
    ("S1_usa",   "S4_russia"): ("sanctions_conflict", "sanctions_risk"),
    ("S3_eu",    "S4_russia"): ("energy_standoff",    "russia_europe"),
    ("S5_saudi", "S4_russia"): ("opec_cooperation",   "middle_east_energy"),
    ("S1_usa",   "S5_saudi"):  ("security_pact",      None),   # 常量 60（美沙安保契约）
    ("S2_china", "S5_saudi"):  ("energy_imports",     None),   # 常量 45（中沙石油贸易）
}
# 常量关系对强度（0-100，derive 时 /100）
_CONST_INTENSITY = {
    ("S1_usa", "S5_saudi"): 60.0,
    ("S2_china", "S5_saudi"): 45.0,
}

_baseline: dict = {}
_board_cur: dict = {}


def derive_board_baseline(grv: dict) -> dict:
    """Board 基线 = GRV 维度分数映射（每日刷新；值 /100 归一化）。
    grv: 含 GRV 维度 0-100 值的 dict（world.grv_dimensions 或 grv_latest.json）。"""
    global _baseline, _board_cur
    _baseline = {}
    for (a, b), (rel, dim) in REL_SPEC.items():
        raw = _CONST_INTENSITY[(a, b)] if dim is None else float(grv.get(dim, 50.0))
        _baseline[(a, b)] = {"rel": rel, "intensity": raw / 100.0}
    # 当前场 = 基线拷贝（仿真开始时无偏离）
    _board_cur = {k: dict(v) for k, v in _baseline.items()}
    return _baseline


def board_decay_step(decay: float = 0.95):
    """仿真内每步：board_cur 向 baseline 衰减（行动 push 的偏离逐步回落）。
    稳态偏离 = push / (1 - decay)；decay 0.95 → push 0.02 → 稳态 0.40。"""
    if not _board_cur:
        return
    for k, v in _baseline.items():
        base = v["intensity"]
        cur = _board_cur[k]["intensity"]
        _board_cur[k]["intensity"] = base + (cur - base) * decay


def board_push(agent_a: str, agent_b: str, delta: float):
    """sovereign 行动 push 偏离（delta 已 /100 归一化；双向关系对自动匹配）。"""
    key = _norm_key(agent_a, agent_b)
    if key is None:
        return
    cur = _board_cur[key]["intensity"]
    _board_cur[key]["intensity"] = max(0.0, min(1.0, cur + delta))


def board_push_all(agent_id: str, delta: float):
    """sovereign 行动对该 agent 的所有关系对 push 同一偏离（简化版，试点用）。"""
    for k in list(_board_cur.keys()):
        if agent_id in k:
            cur = _board_cur[k]["intensity"]
            _board_cur[k]["intensity"] = max(0.0, min(1.0, cur + delta))


def get_board_ctx(agent_id: str) -> dict:
    """C1：S 类 Agent 决策用——该 agent 所有关系对的 {rel: 当前强度 0-1}。"""
    out = {}
    for k, v in _board_cur.items():
        if agent_id in k:
            out[v["rel"]] = round(v["intensity"], 3)
    return out


def _norm_key(a: str, b: str):
    if (a, b) in _board_cur:
        return (a, b)
    if (b, a) in _board_cur:
        return (b, a)
    return None
