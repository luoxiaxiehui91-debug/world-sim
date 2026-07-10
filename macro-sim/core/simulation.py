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


# ── Agent 工厂：从 agents.yaml 加载 ──────────────────────

def load_agents(config_path: str = "/app/config/agents.yaml") -> dict[str, MacroAgent]:
    """从 agents.yaml 构建 Agent 字典，key = agent_id"""
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        # 容器外开发时 fallback 到相对路径
        import os
        alt = os.path.join(os.path.dirname(__file__), "../../config/agents.yaml")
        with open(alt) as f:
            cfg = yaml.safe_load(f)

    agents = {}
    for entry in cfg.get("agents", []):
        agent_id = entry["id"]
        class_path = entry["class"]   # e.g. "financial.FedAgent"
        module_name, class_name = class_path.rsplit(".", 1)
        mod = importlib.import_module(f"core.agents.{module_name}")
        cls = getattr(mod, class_name)

        params = AgentParams.from_dict(entry.get("params", {}))
        agent = cls(
            agent_id=agent_id,
            role=entry["role"],
            info_delay=entry["info_delay"],
            activation_prob=entry["activation_prob"],
            params=params,
        )
        agents[agent_id] = agent
    return agents


# ── GM 规则层 ─────────────────────────────────────────────

def gm_resolve_rules(
    actions: dict,
    world: MacroWorldState,
    agents: dict,
) -> dict:
    """
    将 12 个 Agent 的行动转换为内生变量 delta。
    每个 delta 乘以对应 Agent 的 magnitude 参数。
    返回 delta dict，由 MacroSimModel 统一 apply。
    """
    delta = {}

    def mag(agent_id: str) -> float:
        return agents[agent_id].params.magnitude if agent_id in agents else 1.0

    # ── A1 美联储 ─────────────────────────────────────────
    a1 = actions.get("A1", "HOLD")
    if a1 == "CUT_50BP":
        m = mag("A1")
        delta["fed_rate_change"]      = -50
        delta["market_sentiment"]     = delta.get("market_sentiment", 0) + 0.35 * m
        delta["bank_credit_tightening"] = delta.get("bank_credit_tightening", 0) - 0.15 * m
    elif a1 == "CUT_25BP":
        m = mag("A1")
        delta["fed_rate_change"]      = -25
        delta["market_sentiment"]     = delta.get("market_sentiment", 0) + 0.20 * m
        delta["bank_credit_tightening"] = delta.get("bank_credit_tightening", 0) - 0.08 * m
    elif a1 == "VERBAL_INTERVENTION":
        delta["market_sentiment"]     = delta.get("market_sentiment", 0) + 0.12 * mag("A1")
    elif a1 == "HIKE_25BP":
        m = mag("A1")
        delta["fed_rate_change"]      = 25
        delta["market_sentiment"]     = delta.get("market_sentiment", 0) - 0.12 * m
        delta["bank_credit_tightening"] = delta.get("bank_credit_tightening", 0) + 0.10 * m

    # ── A2 商业银行 ───────────────────────────────────────
    a2 = actions.get("A2", "HOLD")
    if a2 == "TIGHTEN_CREDIT":
        m = mag("A2")
        delta["bank_credit_tightening"] = delta.get("bank_credit_tightening", 0) + 0.25 * m
        delta["liquidity_premium"]      = delta.get("liquidity_premium", 0)      + 0.12 * m
        delta["market_sentiment"]       = delta.get("market_sentiment", 0)       - 0.08 * m
    elif a2 == "EASE_CREDIT":
        m = mag("A2")
        delta["bank_credit_tightening"] = delta.get("bank_credit_tightening", 0) - 0.18 * m
        delta["liquidity_premium"]      = delta.get("liquidity_premium", 0)      - 0.08 * m

    # ── A3 对冲基金 ───────────────────────────────────────
    a3 = actions.get("A3", "HOLD")
    if a3 == "SHORT_MARKET":
        m = mag("A3")
        delta["market_sentiment"]  = delta.get("market_sentiment", 0)  - 0.18 * m
        delta["liquidity_premium"] = delta.get("liquidity_premium", 0) + 0.10 * m
        delta["fund_risk_appetite"] = -0.15 * m
    elif a3 == "DECREASE_RISK":
        m = mag("A3")
        delta["market_sentiment"]  = delta.get("market_sentiment", 0)  - 0.08 * m
        delta["fund_risk_appetite"] = -0.08 * m
    elif a3 == "INCREASE_RISK":
        m = mag("A3")
        delta["market_sentiment"]  = delta.get("market_sentiment", 0)  + 0.10 * m
        delta["fund_risk_appetite"] = 0.10 * m

    # ── A4 能源国 ─────────────────────────────────────────
    a4 = actions.get("A4", "HOLD")
    if a4 == "CUT_SUPPLY":
        delta["energy_supply_risk"] = delta.get("energy_supply_risk", 0) + 0.20 * mag("A4")
    elif a4 == "INCREASE_SUPPLY":
        delta["energy_supply_risk"] = delta.get("energy_supply_risk", 0) - 0.10 * mag("A4")

    # ── A5 机构投资者 ─────────────────────────────────────
    a5 = actions.get("A5", "HOLD")
    if a5 == "DECREASE_RISK":
        m = mag("A5")
        delta["market_sentiment"]  = delta.get("market_sentiment", 0)  - 0.06 * m
        delta["liquidity_premium"] = delta.get("liquidity_premium", 0) + 0.05 * m
    elif a5 == "INCREASE_RISK":
        delta["market_sentiment"]  = delta.get("market_sentiment", 0) + 0.06 * mag("A5")

    # ── A6 媒体 ───────────────────────────────────────────
    a6 = actions.get("A6", "HOLD")
    if a6 == "AMPLIFY_FEAR":
        m = mag("A6")
        delta["market_sentiment"] = delta.get("market_sentiment", 0) - 0.15 * m
        delta["retail_panic"]     = delta.get("retail_panic", 0)     + 0.20 * m
    elif a6 == "AMPLIFY_OPTIMISM":
        m = mag("A6")
        delta["market_sentiment"] = delta.get("market_sentiment", 0) + 0.10 * m
        delta["retail_panic"]     = delta.get("retail_panic", 0)     - 0.10 * m

    # ── A7 新兴市场央行 ───────────────────────────────────
    a7 = actions.get("A7", "HOLD")
    if a7 == "CAPITAL_CONTROLS":
        m = mag("A7")
        delta["em_capital_outflow"]  = delta.get("em_capital_outflow", 0) + 0.25 * m
        delta["market_sentiment"]    = delta.get("market_sentiment", 0)   - 0.05 * m
    elif a7 == "RAISE_RATES":
        delta["em_capital_outflow"]  = delta.get("em_capital_outflow", 0) - 0.10 * mag("A7")
    elif a7 == "CUT_25BP":
        delta["market_sentiment"]    = delta.get("market_sentiment", 0)   + 0.05 * mag("A7")

    # ── A8 中国央行/财政 ──────────────────────────────────
    a8 = actions.get("A8", "HOLD")
    if a8 == "CUT_RRR":
        m = mag("A8")
        delta["china_credit_impulse"] = delta.get("china_credit_impulse", 0) + 0.20 * m
        delta["market_sentiment"]     = delta.get("market_sentiment", 0)     + 0.08 * m
    elif a8 == "FISCAL_STIMULUS_CN":
        m = mag("A8")
        delta["china_credit_impulse"] = delta.get("china_credit_impulse", 0) + 0.30 * m
        delta["market_sentiment"]     = delta.get("market_sentiment", 0)     + 0.12 * m
    elif a8 == "CNY_INTERVENTION":
        delta["em_capital_outflow"]   = delta.get("em_capital_outflow", 0)   - 0.15 * mag("A8")
    elif a8 == "TIGHTEN_CN":
        delta["china_credit_impulse"] = delta.get("china_credit_impulse", 0) - 0.20 * mag("A8")
    elif a8 == "CUT_LPR":
        delta["china_credit_impulse"] = delta.get("china_credit_impulse", 0) + 0.15 * mag("A8")

    # ── A9 美国财政部 ─────────────────────────────────────
    a9 = actions.get("A9", "HOLD")
    if a9 == "FISCAL_STIMULUS":
        m = mag("A9")
        delta["market_sentiment"]   = delta.get("market_sentiment", 0)   + 0.15 * m
        delta["us_fiscal_pressure"] = delta.get("us_fiscal_pressure", 0) + 0.10 * m
    elif a9 == "DEBT_CEILING_RISK":
        m = mag("A9")
        delta["market_sentiment"]   = delta.get("market_sentiment", 0)   - 0.12 * m
        delta["us_fiscal_pressure"] = delta.get("us_fiscal_pressure", 0) + 0.20 * m
        delta["credit_spread_delta"] = 15 * m   # 债务上限危机直接冲击利差
    elif a9 == "FISCAL_TIGHTEN":
        m = mag("A9")
        delta["market_sentiment"]   = delta.get("market_sentiment", 0)   - 0.05 * m
        delta["us_fiscal_pressure"] = delta.get("us_fiscal_pressure", 0) - 0.10 * m

    # ── A10 散户 ──────────────────────────────────────────
    a10 = actions.get("A10", "HOLD")
    if a10 == "PANIC_SELL":
        m = mag("A10")
        delta["market_sentiment"]  = delta.get("market_sentiment", 0)  - 0.10 * m
        delta["retail_panic"]      = delta.get("retail_panic", 0)      + 0.25 * m
        delta["liquidity_premium"] = delta.get("liquidity_premium", 0) + 0.05 * m
    elif a10 == "FOMO_BUY":
        m = mag("A10")
        delta["market_sentiment"]  = delta.get("market_sentiment", 0) + 0.08 * m
        delta["retail_panic"]      = delta.get("retail_panic", 0)     - 0.15 * m

    # ── A11 欧洲央行 ──────────────────────────────────────
    a11 = actions.get("A11", "HOLD")
    if a11 == "CUT_25BP":
        m = mag("A11")
        delta["market_sentiment"]     = delta.get("market_sentiment", 0)     + 0.08 * m
        delta["liquidity_premium"]    = delta.get("liquidity_premium", 0)    - 0.05 * m
    elif a11 == "QE_EXPAND":
        m = mag("A11")
        delta["market_sentiment"]     = delta.get("market_sentiment", 0)     + 0.10 * m
        delta["bank_credit_tightening"] = delta.get("bank_credit_tightening", 0) - 0.05 * m
    elif a11 == "HIKE_25BP":
        m = mag("A11")
        delta["market_sentiment"]     = delta.get("market_sentiment", 0)     - 0.05 * m
        delta["em_capital_outflow"]   = delta.get("em_capital_outflow", 0)   + 0.05 * m

    # ── A12 日本央行 ──────────────────────────────────────
    a12 = actions.get("A12", "HOLD")
    if a12 == "ABANDON_YCC":
        m = mag("A12")
        # 放弃YCC是非线性事件，直接冲击全球流动性
        delta["yen_carry_risk"]    = delta.get("yen_carry_risk", 0)    + 0.50 * m
        delta["liquidity_premium"] = delta.get("liquidity_premium", 0) + 0.20 * m
        delta["market_sentiment"]  = delta.get("market_sentiment", 0)  - 0.20 * m
    elif a12 == "EMERGENCY_EASE":
        m = mag("A12")
        delta["yen_carry_risk"]    = delta.get("yen_carry_risk", 0)    - 0.20 * m
        delta["market_sentiment"]  = delta.get("market_sentiment", 0)  + 0.08 * m
    elif a12 == "EASE_YCC":
        delta["yen_carry_risk"]    = delta.get("yen_carry_risk", 0)    + 0.15 * mag("A12")

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

    # 连续3步负向 → 强制激活 A7 和 A12
    if world.consecutive_negative_steps >= 3:
        for aid in ("A7", "A12"):
            if aid in agents:
                agents[aid].forced_activate = True
        world.consecutive_negative_steps = 0

    return delta


# ── 主仿真模型 ────────────────────────────────────────────

class MacroSimModel:

    def __init__(
        self,
        world: MacroWorldState,
        agents: dict[str, MacroAgent] = None,
        use_llm: bool = False,
        config_path: str = "/app/config/agents.yaml",
    ):
        self.world   = world
        self.use_llm = use_llm
        self.agents  = agents or load_agents(config_path)
        self.history: list[dict] = []

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
        # Phase 1: 每个 Agent 决策
        step_actions: dict[str, str] = {}
        for agent_id, agent in self.agents.items():
            if agent.forced_activate:
                agent.forced_activate = False
                ctx = self.world.get_agent_context(agent.role)
                ctx["visible_actions"] = self._build_visible_actions(agent)
                step_actions[agent_id] = agent.decide(ctx, self.use_llm)
            elif agent.activation_countdown > 0:
                agent.activation_countdown -= 1
                step_actions[agent_id] = "NO_ACTION"
            elif random.random() < agent.activation_prob:
                ctx = self.world.get_agent_context(agent.role)
                ctx["visible_actions"] = self._build_visible_actions(agent)
                step_actions[agent_id] = agent.decide(ctx, self.use_llm)
                agent.activation_countdown = agent.info_delay  # 行动后冷却
            else:
                step_actions[agent_id] = "NO_ACTION"

        # Phase 2: GM 规则 → delta → apply
        delta = gm_resolve_rules(step_actions, self.world, self.agents)
        self._apply_delta(delta)
        apply_natural_decay(self.world)

        # Phase 3: 出血规则
        apply_bleed_rules(self.world)

        # Phase 4: 校准注入（覆盖外生变量为真实值）
        if inject_world:
            for key, val in inject_world.items():
                if hasattr(self.world, key):
                    setattr(self.world, key, val)

        # 记录本步
        self.action_history.append(dict(step_actions))
        snapshot = {
            **self.world.to_dict(),
            "actions": {aid: act for aid, act in step_actions.items() if act != "NO_ACTION"},
            "delta":   {k: round(v, 4) for k, v in delta.items()},
        }
        self.history.append(snapshot)
        self.world.cycle += 1
        return snapshot

    def _apply_delta(self, delta: dict):
        # 月度时间步长折减：GM规则按日度感觉设计，月度缩小到1/4
        MONTHLY_SCALE = 0.12
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
