"""
simulation.py — 主仿真调度器 v2

核心变化：
- 维护 action_history 队列，每个 Agent 按 info_delay 读取延迟后的行动
- Agent 从 agents.yaml 动态加载（工厂函数）
- GM 规则使用 AgentParams.magnitude 放大/缩小影响
- 兼容校准循环（外部可注入当月真实外生变量覆盖仿真结果）
"""

import random
import copy
import importlib
from collections import deque
from typing import Optional

import yaml

from core.world_state import (
    MacroWorldState,
    apply_sentiment_delta,
    apply_natural_decay,
    apply_bleed_rules,
)
from core.agents.base import MacroAgent, AgentParams
from core.agents.sovereign import SovereignAgent


# ── Agent 工厂：从 agents.yaml 加载 ──────────────────────

def load_agents(config_path: str = "/app/config/agents.yaml") -> tuple[dict[str, MacroAgent], dict]:
    """从 agents.yaml 构建 Agent 字典，返回 (agents, global_cfg)"""
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        # 容器外开发时 fallback 到相对路径
        import os
        alt = os.path.join(os.path.dirname(__file__), "../../config/agents.yaml")
        with open(alt) as f:
            cfg = yaml.safe_load(f)

    global_cfg = cfg.get("global", {})
    agents = {}
    for entry in cfg.get("agents", []):
        agent_id = entry["id"]
        class_path = entry["class"]   # e.g. "financial.FedAgent"
        module_name, class_name = class_path.rsplit(".", 1)
        mod = importlib.import_module(f"core.agents.{module_name}")
        cls = getattr(mod, class_name)

        params = AgentParams.from_dict(entry.get("params", {}))

        # soul 文件加载（可选）：agents.yaml 中配置 soul_file 路径时加载
        soul = {}
        soul_file = entry.get("soul_file")
        if soul_file:
            import os
            souls_dir = os.path.join(os.path.dirname(config_path), "..", "souls")
            soul_path = os.path.join(souls_dir, soul_file)
            if not os.path.isabs(soul_file):
                soul_path = os.path.normpath(soul_path)
            try:
                with open(soul_path, encoding="utf-8") as sf:
                    soul = yaml.safe_load(sf) or {}
            except FileNotFoundError:
                pass  # soul 文件可选，不存在不报错

        agent = cls(
            agent_id=agent_id,
            role=entry["role"],
            info_delay=entry["info_delay"],
            activation_prob=entry["activation_prob"],
            params=params,
            transmission_coefficients=entry.get("transmission_coefficients", {}),
            soul=soul,
        )
        agents[agent_id] = agent
    return agents, global_cfg


# ── GM 规则层 ─────────────────────────────────────────────

def gm_resolve_rules(
    actions: dict,
    world: MacroWorldState,
    agents: dict,
    global_cfg: dict = None,
) -> dict:
    """
    将 12 个 Agent 的行动转换为内生变量 delta。
    每个 delta 乘以对应 Agent 的 magnitude 参数。
    返回 delta dict，由 MacroSimModel 统一 apply。

    D1 fix: 传导矩阵改为 per-agent delta 追踪，避免全量 delta 叠加导致
    N 个 Agent 激活时传导强度 = 单 Agent 的 N 倍。
    """
    # D1 fix: per-agent delta 记录，key = agent_id
    per_agent_delta: dict[str, dict] = {}
    delta = {}

    def mag(agent_id: str) -> float:
        return agents[agent_id].params.magnitude if agent_id in agents else 1.0

    def add(agent_id: str, key: str, val: float):
        """同时写入全局 delta 和该 agent 的 per-agent delta"""
        delta[key] = delta.get(key, 0.0) + val
        if agent_id not in per_agent_delta:
            per_agent_delta[agent_id] = {}
        per_agent_delta[agent_id][key] = per_agent_delta[agent_id].get(key, 0.0) + val

    # ── A1 美联储 ─────────────────────────────────────────
    a1 = actions.get("A1", "HOLD")
    if a1 == "CUT_50BP":
        m = mag("A1")
        add("A1", "fed_rate_change",        -50)
        add("A1", "market_sentiment",         0.35 * m)
        add("A1", "bank_credit_tightening",  -0.15 * m)
    elif a1 == "CUT_25BP":
        m = mag("A1")
        add("A1", "fed_rate_change",        -25)
        # P1-1（v2.0.30，arch 终局）：+0.20→+0.30——sentiment 贴 floor 根因是负写者
        # 每步主导（A3 SHORT -0.18×1.0 + A10 PANIC -0.10），增强正写打破钉死。
        # 不动 A3 决策分支（08-06 修过 path diversity），只降其 activation（见 agents.yaml）。
        add("A1", "market_sentiment",         0.30 * m)
        add("A1", "bank_credit_tightening",  -0.08 * m)
    elif a1 == "VERBAL_INTERVENTION":
        add("A1", "market_sentiment",  0.12 * mag("A1"))
    elif a1 == "HIKE_25BP":
        m = mag("A1")
        add("A1", "fed_rate_change",        25)
        add("A1", "market_sentiment",       -0.12 * m)
        add("A1", "bank_credit_tightening",  0.10 * m)

    # ── A2 商业银行 ───────────────────────────────────────
    a2 = actions.get("A2", "HOLD")
    if a2 == "TIGHTEN_CREDIT":
        m = mag("A2")
        add("A2", "bank_credit_tightening",  0.25 * m)
        add("A2", "liquidity_premium",        0.12 * m)
        add("A2", "market_sentiment",        -0.08 * m)
    elif a2 == "EASE_CREDIT":
        m = mag("A2")
        # P0-2（v2.0.30）：幅度对称 -0.18→-0.25（+0.25/-0.25 对称，终局 issue ③）。
        # 原 +0.25 vs -0.18 + decay×0.97 → 恢复比收紧慢 ~3 倍，一旦收紧回不来。
        add("A2", "bank_credit_tightening", -0.25 * m)
        add("A2", "liquidity_premium",       -0.08 * m)
        # R4h ③-A（v2.0.38）：EASE 补写 market_sentiment 正向分量 +0.08×m（K=1.0），
        # 与 TIGHTEN 的 -0.08（L141）完全镜像。依据：负写者主导 3:1（EASE 不写 ×4 步
        # vs TIGHTEN -0.08 ×12 步）、grv_down reverse 0.727（sentiment 恒贴 floor →
        # 宽松不传导情绪回升）。clamp [-1,1] 由 apply_sentiment_delta 统一，damping 恒 1。
        add("A2", "market_sentiment",         0.08 * m)

    # ── A3 对冲基金 ───────────────────────────────────────
    a3 = actions.get("A3", "HOLD")
    if a3 == "SHORT_MARKET":
        m = mag("A3")
        add("A3", "market_sentiment",    -0.18 * m)
        add("A3", "liquidity_premium",    0.10 * m)
        add("A3", "fund_risk_appetite",  -0.15 * m)
    elif a3 == "DECREASE_RISK":
        m = mag("A3")
        add("A3", "market_sentiment",    -0.08 * m)
        add("A3", "fund_risk_appetite",  -0.08 * m)
    elif a3 == "INCREASE_RISK":
        m = mag("A3")
        add("A3", "market_sentiment",    0.10 * m)
        add("A3", "fund_risk_appetite",  0.10 * m)

    # ── A4 能源国（SovereignAgent，B+A/NOVEL）────────────────
    a4 = actions.get("A4", "HOLD")
    if a4 in ("CUT_SUPPLY", "CUT_OUTPUT"):
        # 减产：能源供给风险↑，市场情绪略↓（通胀压力）
        m = mag("A4")
        add("A4", "energy_supply_risk",  0.20 * m)
        add("A4", "market_sentiment",   -0.05 * m)
    elif a4 in ("INCREASE_SUPPLY", "INCREASE_OUTPUT"):
        # 增产：能源供给风险↓，市场情绪略↑
        m = mag("A4")
        add("A4", "energy_supply_risk", -0.10 * m)
        add("A4", "market_sentiment",    0.03 * m)
    elif a4 == "EMBARGO_SIGNAL":
        # 禁运信号：能源供给风险急升，流动性溢价上升
        m = mag("A4")
        add("A4", "energy_supply_risk",  0.35 * m)
        add("A4", "liquidity_premium",   0.10 * m)
        add("A4", "market_sentiment",   -0.12 * m)
    elif a4 == "DIPLOMATIC_OUTREACH":
        # 外交接触：能源供给风险略降，市场情绪改善
        m = mag("A4")
        add("A4", "energy_supply_risk", -0.05 * m)
        add("A4", "market_sentiment",    0.04 * m)

    # ── A5 机构投资者 ─────────────────────────────────────
    a5 = actions.get("A5", "HOLD")
    if a5 == "DECREASE_RISK":
        m = mag("A5")
        add("A5", "market_sentiment",   -0.06 * m)
        add("A5", "liquidity_premium",   0.05 * m)
    elif a5 == "INCREASE_RISK":
        add("A5", "market_sentiment",    0.06 * mag("A5"))

    # ── A13 保险/养老长线资金（08-17 逆周期稳定者）─────────
    a13 = actions.get("A13", "HOLD")
    if a13 == "INCREASE_RISK":
        # 逆向抄底：情绪回升（比 A5 强）+ 流动性溢价下降（提供对手盘）
        m = mag("A13")
        add("A13", "market_sentiment",   0.08 * m)
        add("A13", "liquidity_premium", -0.04 * m)
    elif a13 == "DECREASE_RISK":
        # 温和撤退：情绪略降（比 A5/A3 温和，长线不追涨杀跌）
        m = mag("A13")
        add("A13", "market_sentiment",  -0.03 * m)

    # ── A6 媒体 ───────────────────────────────────────────
    a6 = actions.get("A6", "HOLD")
    if a6 == "AMPLIFY_FEAR":
        m = mag("A6")
        add("A6", "market_sentiment", -0.15 * m)
        add("A6", "retail_panic",      0.20 * m)
    elif a6 == "AMPLIFY_OPTIMISM":
        m = mag("A6")
        add("A6", "market_sentiment",  0.10 * m)
        add("A6", "retail_panic",     -0.10 * m)

    # ── A7 新兴市场央行 ───────────────────────────────────
    a7 = actions.get("A7", "HOLD")
    if a7 == "CAPITAL_CONTROLS":
        m = mag("A7")
        add("A7", "em_capital_outflow",  0.25 * m)
        add("A7", "market_sentiment",   -0.05 * m)
    elif a7 == "RAISE_RATES":
        add("A7", "em_capital_outflow", -0.10 * mag("A7"))
    elif a7 == "CUT_25BP":
        add("A7", "market_sentiment",    0.05 * mag("A7"))

    # ── A8 中国央行/财政 ──────────────────────────────────
    a8 = actions.get("A8", "HOLD")
    if a8 == "CUT_RRR":
        m = mag("A8")
        add("A8", "china_credit_impulse",  0.20 * m)
        add("A8", "market_sentiment",       0.08 * m)
    elif a8 == "FISCAL_STIMULUS_CN":
        m = mag("A8")
        add("A8", "china_credit_impulse",  0.30 * m)
        add("A8", "market_sentiment",       0.12 * m)
    elif a8 == "CNY_INTERVENTION":
        add("A8", "em_capital_outflow",   -0.15 * mag("A8"))
    elif a8 == "TIGHTEN_CN":
        add("A8", "china_credit_impulse", -0.20 * mag("A8"))
    elif a8 == "CUT_LPR":
        add("A8", "china_credit_impulse",  0.15 * mag("A8"))

    # ── A9 美国财政部 ─────────────────────────────────────
    a9 = actions.get("A9", "HOLD")
    if a9 == "FISCAL_STIMULUS":
        m = mag("A9")
        add("A9", "market_sentiment",    0.15 * m)
        add("A9", "us_fiscal_pressure",  0.10 * m)
    elif a9 == "DEBT_CEILING_RISK":
        m = mag("A9")
        add("A9", "market_sentiment",    -0.12 * m)
        add("A9", "us_fiscal_pressure",   0.20 * m)
        add("A9", "credit_spread_delta",  15 * m)  # 债务上限危机直接冲击利差
    elif a9 == "FISCAL_TIGHTEN":
        m = mag("A9")
        add("A9", "market_sentiment",    -0.05 * m)
        add("A9", "us_fiscal_pressure",  -0.10 * m)

    # ── A10 散户 ──────────────────────────────────────────
    a10 = actions.get("A10", "HOLD")
    if a10 == "PANIC_SELL":
        m = mag("A10")
        add("A10", "market_sentiment",   -0.10 * m)
        add("A10", "retail_panic",        0.25 * m)
        add("A10", "liquidity_premium",   0.05 * m)
    elif a10 == "FOMO_BUY":
        m = mag("A10")
        add("A10", "market_sentiment",  0.08 * m)
        add("A10", "retail_panic",     -0.15 * m)

    # ── A11 欧洲央行 ──────────────────────────────────────
    a11 = actions.get("A11", "HOLD")
    if a11 == "CUT_25BP":
        m = mag("A11")
        add("A11", "market_sentiment",       0.08 * m)
        add("A11", "liquidity_premium",     -0.05 * m)
    elif a11 == "QE_EXPAND":
        m = mag("A11")
        add("A11", "market_sentiment",          0.10 * m)
        add("A11", "bank_credit_tightening",   -0.05 * m)
    elif a11 == "HIKE_25BP":
        m = mag("A11")
        add("A11", "market_sentiment",    -0.05 * m)
        add("A11", "em_capital_outflow",   0.05 * m)

    # ── A12 日本央行 ──────────────────────────────────────
    a12 = actions.get("A12", "HOLD")
    if a12 == "ABANDON_YCC":
        m = mag("A12")
        # 放弃YCC是非线性事件，直接冲击全球流动性
        add("A12", "yen_carry_risk",    0.50 * m)
        add("A12", "liquidity_premium", 0.20 * m)
        add("A12", "market_sentiment", -0.20 * m)
    elif a12 == "EMERGENCY_EASE":
        m = mag("A12")
        add("A12", "yen_carry_risk",   -0.20 * m)
        add("A12", "market_sentiment",  0.08 * m)
    elif a12 == "EASE_YCC":
        add("A12", "yen_carry_risk",    0.15 * mag("A12"))

    # ── S 类主权 Agent 分支（v2.2，A1/A4/D3/B3 修复）──────────────
    # 在传导矩阵之前执行：sovereign 的 sentiment delta 需参与传导（C3）。
    # 白名单动态聚合（已加载 soul 的 grv_impact_map key 并集 + HOLD/NO_ACTION），
    # 消灭两套白名单并存（代码 VALID_ACTIONS vs 旧设计 _SOVEREIGN_ACTIONS）。
    # GRV 维度 delta 直写 world.grv_dimensions（0-100 量纲，绕过 _apply_delta clamp(0,1)），
    # 同步同名 world_state 字段（sanctions_risk 等）→ 金融 Agent 下一轮 ctx 可见（B1 传导链）。
    _whitelist = {"HOLD", "NO_ACTION"}
    for _a in agents.values():
        if isinstance(_a, SovereignAgent) and _a.soul:
            _whitelist |= set(_a.soul.get("grv_impact_map", {}).keys())

    for agent_id, action in actions.items():
        if action in ("HOLD", "NO_ACTION"):
            continue
        agent = agents.get(agent_id)
        if agent is None or not isinstance(agent, SovereignAgent) or not agent.soul:
            continue
        # 1. 白名单检查（fail-loud：不在白名单的行动记日志跳过）
        if action not in _whitelist:
            print(f"[gm_resolve] S 类行动 {agent_id} {action} 不在白名单（{sorted(_whitelist)}），跳过")
            continue
        # 2. 行动必须定义于 soul（防幻觉 action）
        impacts = agent.get_grv_impact(action)
        if not impacts:
            print(f"[gm_resolve] S 类行动 {agent_id} {action} 无 grv_impact_map 定义，跳过（fail-loud）")
            continue
        m = mag(agent_id)
        # 3. GRV 维度 delta 直写（0-100 量纲）
        gd = getattr(world, "grv_dimensions", None)
        if gd is not None:
            for dim, val in impacts.items():
                cur = float(gd.get(dim, 0.0))
                new = max(0.0, min(100.0, cur + val * m))
                gd[dim] = new
                # 同步同名 world_state 字段（金融 Agent 感知；us_china_strategic → us_china_grv）
                if dim == "us_china_strategic":
                    world.us_china_grv = new
                elif hasattr(world, dim):
                    setattr(world, dim, new)
                # per-agent delta 记录（供传导矩阵/快照展示，不写 world 属性）
                add(agent_id, f"grv_dim.{dim}", val * m)
        # 4. sentiment 通用影响（v2.2 B3 试点系数，验证后回调 ±0.04-0.06）
        # 08-07 迭代：0.25 时 S 类单向下压过强（GRV80 std 反降至 0.05）→ 回调 0.20/0.15
        if action in ("IMPOSE_SANCTIONS", "MILITARY_DEPLOYMENT", "CUT_OUTPUT",
                      "EMBARGO_SIGNAL", "NUCLEAR_SIGNAL", "ENERGY_CUTOFF",
                      "TECH_RESTRICTION", "ALLIANCE_REINFORCE"):
            add(agent_id, "market_sentiment", -0.20 * m)
            _board_delta = 0.02   # 冲突行动 → Board 全关系对 push +偏离
        elif action in ("DIPLOMATIC_ENGAGE", "LIFT_SANCTIONS", "INCREASE_OUTPUT",
                        "CEASEFIRE_SIGNAL", "DIPLOMATIC_OUTREACH"):
            add(agent_id, "market_sentiment", 0.15 * m)
            _board_delta = -0.02  # 缓和行动 → 回落
        else:
            _board_delta = 0.0
        if _board_delta:
            try:
                from core.board_baseline import board_push_all
                board_push_all(agent_id, _board_delta)
            except Exception:
                pass  # Board 数据可选，缺失不阻断

    # ── 传导矩阵（第二轮）────────────────────────────────────
    # D1 fix: 每个 Agent 只传导自己产生的 per-agent delta，
    # 避免把全量累积 delta 乘以传导系数（原代码导致 N 个 Agent 激活时
    # 传导强度 = 单 Agent 的 N 倍）。
    attenuation = (global_cfg or {}).get("transmission_attenuation", 0.5)

    for src_id, action in actions.items():
        if action in ("HOLD", "NO_ACTION") or src_id not in agents:
            continue
        src_delta = per_agent_delta.get(src_id)
        if not src_delta:
            continue
        coefficients = agents[src_id].transmission_coefficients
        if not coefficients:
            continue
        for tgt_key, coeff in coefficients.items():
            if coeff <= 0:
                continue
            tgt_id = tgt_key[3:] if tgt_key.startswith("to_") else tgt_key
            if tgt_id not in agents:
                continue
            tgt_mag = agents[tgt_id].params.magnitude
            # 只传导该 Agent 自己产生的 delta（per_agent_delta），不跨 Agent 叠加
            for key, val in src_delta.items():
                if isinstance(val, float):
                    delta[key] = delta.get(key, 0.0) + val * coeff * attenuation * tgt_mag

    # ── 正反馈环 ──────────────────────────────────────────
    # 情绪持续崩溃 → 媒体激活概率上升
    if world.market_sentiment < -0.5:
        world.consecutive_negative_steps += 1
        if "A6" in agents:
            agents["A6"].activation_prob = min(1.0, agents["A6"].activation_prob + 0.2)
        if "A10" in agents:
            agents["A10"].activation_prob = min(1.0, agents["A10"].activation_prob + 0.15)
    else:
        world.consecutive_negative_steps = max(0, world.consecutive_negative_steps - 1)
        if "A6" in agents:
            agents["A6"].activation_prob = max(0.8, agents["A6"].activation_prob - 0.1)
        if "A10" in agents:
            agents["A10"].activation_prob = max(0.7, agents["A10"].activation_prob - 0.1)

    # 信贷收紧 → 能源融资断链
    if world.bank_credit_tightening > 0.6:
        delta["energy_supply_risk"] = delta.get("energy_supply_risk", 0) + 0.10

    # 连续3步负向 → 强制激活 A7 和 A12（H21 修复, 2026-08-16）
    # 原实现：counter>=3 触发后立即归零 → apply_bleed_rules 的出血1（VIX 恐慌放大，
    # 检查 counter >= vix_bleed_steps=3）永远看不到 >=3 → 结构性永不触发
    # （代码注释自证：'sentiment bleed +2.0 从未触发，delta 分布 0/5.0'）。
    # 修复：counter 不再归零（else 分支自然 -1 衰减，持续负向时单调累积使出血1
    # 持续生效直到 vix_bleed_max 封顶）；A7/A12 改用上升沿检测（_vix_panic_armed
    # 标记：2→3 跃迁触发一次，脱离负向区解除），避免每步重复强制激活。
    if world.consecutive_negative_steps >= 3:
        if not getattr(world, "_vix_panic_armed", False):
            world._vix_panic_armed = True
            for aid in ("A7", "A12"):
                if aid in agents:
                    agents[aid].forced_activate = True
    if world.market_sentiment >= -0.5:
        world._vix_panic_armed = False

    return delta


# ── 主仿真模型 ────────────────────────────────────────────

class MacroSimModel:

    def __init__(
        self,
        world: MacroWorldState,
        agents: dict[str, MacroAgent] = None,
        use_llm: bool = False,
        config_path: str = "/app/config/agents.yaml",
        bleed_params_override: dict = None,
        force_activate_all: bool = False,
    ):
        self.world   = world
        self.use_llm = use_llm
        self.bleed_params_override = bleed_params_override
        # 08-16 全激活试验开关：跳过 activation_prob 掷骰，每步都给所有 Agent 决策机会
        # （保留 info_delay 冷却，避免单 Agent 连续行动；阈值判定仍在 decide 内）
        self.force_activate_all = force_activate_all
        if agents is not None:
            self.agents = agents
            self.global_cfg = {}
        else:
            self.agents, self.global_cfg = load_agents(config_path)
        self.history: list[dict] = []
        # v3 阶段 1：每步 ActionDecision trace（decisions 骨架；落盘由结果层 v3 启用）
        self.decision_trace: list[dict] = []

        # action_history：用双端队列保存最近 max_delay 步的行动记录
        max_delay = max(a.info_delay for a in self.agents.values()) + 1
        self.action_history: deque = deque(maxlen=max_delay)

    def _build_visible_actions(self, agent: MacroAgent) -> dict:
        """
        按 Agent 的 info_delay 从历史队列里取对应步的行动。
        delay=0 → 看上一步（最近）；delay=4 → 看4步前。
        若历史不足则返回空（相当于什么都不知道）。
        """
        delay = agent.info_delay
        if len(self.action_history) <= delay:
            return {}
        # action_history[-1] 是最近一步，[-1-delay] 是 delay 步前
        idx = -(1 + delay)
        try:
            step_actions = self.action_history[idx]
        except IndexError:
            return {}

        # 把 agent_id 映射到 role 名，让规则里用 role 名查询
        role_map = {a.agent_id: a.role for a in self.agents.values()}
        return {role_map.get(aid, aid): action
                for aid, action in step_actions.items()
                if action != "NO_ACTION"}

    def step(self, inject_world: dict = None):
        """
        执行一步仿真。
        inject_world: 校准循环传入当月真实外生变量，覆盖仿真结果（用于保持历史轨迹真实）
        """
        # Phase 1: 每个 Agent 决策（v3 阶段 1：decide_with_decision 收集 trace，
        # 行为与 v2 的 decide() 完全一致——decide() 即取 .action）
        step_actions: dict[str, str] = {}
        step_decisions: dict[str, dict] = {}
        for agent_id, agent in self.agents.items():
            if agent.forced_activate:
                agent.forced_activate = False
                ctx = self.world.get_agent_context(agent.role, soul=getattr(agent, "soul", None))
                ctx["visible_actions"] = self._build_visible_actions(agent)
                self._inject_board_ctx(ctx, agent)
                decision = agent.decide_with_decision(ctx, self.use_llm)
                step_actions[agent_id] = decision.action
                step_decisions[agent_id] = decision.to_dict()
            elif agent.activation_countdown > 0:
                agent.activation_countdown -= 1
                step_actions[agent_id] = "NO_ACTION"
            elif ((self.force_activate_all and agent.activation_prob > 0)
                  or random.random() < agent.activation_prob):
                # 全激活模式：跳过掷骰但尊重 activation_prob==0 的"挂起"语义
                # （A4 能源国挂起、由 S5_saudi 接管——08-16 试验暴露 force 绕过挂起）
                ctx = self.world.get_agent_context(agent.role, soul=getattr(agent, "soul", None))
                ctx["visible_actions"] = self._build_visible_actions(agent)
                self._inject_board_ctx(ctx, agent)
                decision = agent.decide_with_decision(ctx, self.use_llm)
                step_actions[agent_id] = decision.action
                step_decisions[agent_id] = decision.to_dict()
                agent.activation_countdown = agent.info_delay  # 行动后冷却
            else:
                step_actions[agent_id] = "NO_ACTION"

        # Phase 2: GM 规则 → delta → apply
        delta = gm_resolve_rules(step_actions, self.world, self.agents,
                                 self.global_cfg)
        self._apply_delta(delta)
        apply_natural_decay(self.world)

        # Phase 3: 出血规则
        apply_bleed_rules(self.world, self.bleed_params_override)

        # Phase 4: 校准注入（覆盖外生变量为真实值）
        if inject_world:
            for key, val in inject_world.items():
                if hasattr(self.world, key):
                    setattr(self.world, key, val)

        # v2.2 A5：Board 每步向基线衰减（行动 push 的偏离逐步回落）
        try:
            from core.board_baseline import board_decay_step
            board_decay_step()
        except Exception:
            pass

        # 记录本步
        self.action_history.append(dict(step_actions))
        self.decision_trace.append(step_decisions)   # v3 阶段 1：trace 骨架（结果层 v3 落盘）
        snapshot = {
            **self.world.to_dict(),
            "actions": {aid: act for aid, act in step_actions.items() if act != "NO_ACTION"},
            "delta":   {k: round(v, 4) for k, v in delta.items()},
        }
        self.history.append(snapshot)
        self.world.cycle += 1
        return snapshot

    def _inject_board_ctx(self, ctx: dict, agent: MacroAgent):
        """v2.2 C1：向 ctx 注入 Board 数据（S 类主权 Agent 决策用）。
        board_baseline.py 提供 get_board_ctx；缺失时静默跳过（非 S 类或无 Board 场景）。"""
        try:
            from core.board_baseline import get_board_ctx
            ctx["board"] = get_board_ctx(agent.agent_id)
        except Exception:
            pass  # Board 数据可选，缺失不影响非 S 类 Agent

    def _apply_delta(self, delta: dict):
        # 月度步长衰减因子；设计值 0.25（=1/4，GM规则按日度感觉设计），
        # 实测 0.25 导致路径振荡，经验调至 0.12（见 CHANGELOG v2.0.1）。
        # 2026-08-08 D 修复（calib-fix-review 终局）：0.12→0.25。
        # 根因：MONTHLY_SCALE 只作用于 sentiment（apply_sentiment_delta 前乘），
        # credit/liquidity 走 else 分支不经缩放 → sentiment delta 尺度小 8 倍，三变量三种死法。
        # arch 拒 1.0（8 倍跳重演 v2.0.1 振荡史）；回退闸=预测回归振荡→回 0.12。
        MONTHLY_SCALE = 0.25
        for key, val in delta.items():
            if key == "market_sentiment":
                apply_sentiment_delta(self.world, val * MONTHLY_SCALE)
            elif key == "fed_rate_change":
                self.world.fed_rate_change += val
            elif key == "credit_spread_delta":
                self.world.credit_spread += val
            elif key in ("retail_panic", "china_credit_impulse",
                         "us_fiscal_pressure", "yen_carry_risk"):
                current = getattr(self.world, key, 0.0)
                # china_credit_impulse 可以是负数
                if key == "china_credit_impulse":
                    setattr(self.world, key, max(-1.0, min(1.0, current + val)))
                else:
                    setattr(self.world, key, max(0.0, min(1.0, current + val)))
            else:
                current = getattr(self.world, key, 0.0)
                # C3-3a（2026-08-08 终局裁决）：em_capital_outflow 对称 clamp。
                # 结构自锁根因：clamp[0,1] + target 可负（grv×0.4−t10y2y×0.3 范围 -0.7~0.7）
                # + CAPITAL_CONTROLS 自举阈值 0.5 不可达 → 负 target 月误差恒=|target|，LLM 永远修不好。
                # P0-3（v2.0.30，arch/QA/data 三方终局）：bank_credit/liquidity 同批对称化
                # [-1,1]——target 均可负（credit=cs×0.6 / lp=cs×0.4+t10y2y×0.3∈[-0.7,0.7]），
                # clamp[0,1] 结构性砍负半轴 → 负 target 不可测、cap 假收敛（探针 m_v=0 假死）。
                # 连带已核：decay ×0.97/×0.93 负区向 0 均值回归安全；下游 bleed 阈值全在正侧；
                # EASE 在负 credit 下更易触发（合理）。
                if key in ("em_capital_outflow", "bank_credit_tightening", "liquidity_premium"):
                    setattr(self.world, key, max(-1.0, min(1.0, current + val)))
                else:
                    setattr(self.world, key, max(0.0, min(1.0, current + val)))

    def run(self, inject_sequence: list[dict] = None) -> list[dict]:
        """
        inject_sequence：校准循环传入的历史真值列表，每步一条。
        None → 自由演化（预测循环）。
        """
        for i in range(self.world.total_cycles):
            inject = inject_sequence[i] if inject_sequence and i < len(inject_sequence) else None
            self.step(inject_world=inject)
        return self.history

    def get_first_cascade_step(self) -> Optional[int]:
        for snap in self.history:
            if snap.get("consecutive_negative_steps", 0) >= 3:
                return snap["cycle"]
        return None
