"""
base.py — MacroAgent 基类 + AgentParams

设计：
- 每个 Agent 暴露三个可调参数（sensitivity/threshold/magnitude）
- 参数由校准循环自动调整，变更记录到 calibration_log.jsonl
- Agent 决策时可见上一步其他 Agent 的行动（按信息延迟档）
- 预留接口：from_yaml() 支持从 agents.yaml 加载

v3 新增：
- decide_with_trace() 返回结构化输出（含因果链、expected_state_changes）
- AgentOutput dataclass 统一输出格式
- 供天玑推理溯源存档使用
"""

from dataclasses import dataclass, field
from typing import ClassVar, Optional, List, Dict, Any


@dataclass
class AgentParams:
    """三个可调参数，校准期由 LLM 自动调整"""
    sensitivity: float = 1.0   # 对信号的反应灵敏度，范围 0.1~2.0
    threshold:   float = 0.5   # 触发行动的最低信号强度，范围 0.0~1.0
    magnitude:   float = 1.0   # 行动对世界状态的影响幅度，范围 0.1~2.0

    def clamp(self):
        self.sensitivity = max(0.1, min(2.0, self.sensitivity))
        self.threshold   = max(0.0, min(1.0, self.threshold))
        self.magnitude   = max(0.1, min(2.0, self.magnitude))

    def to_dict(self) -> dict:
        return {
            "sensitivity": round(self.sensitivity, 3),
            "threshold":   round(self.threshold, 3),
            "magnitude":   round(self.magnitude, 3),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgentParams":
        return cls(
            sensitivity=d.get("sensitivity", 1.0),
            threshold=d.get("threshold", 0.5),
            magnitude=d.get("magnitude", 1.0),
        )


@dataclass
class MacroAgent:
    """
    所有宏观 Agent 的基类。

    信息延迟：
      info_delay = 0  → 即时可见（对冲基金、散户）
      info_delay = 1  → 1个月延迟（媒体、商业银行）
      info_delay = 2  → 2个月延迟（机构投资者）
      info_delay = 3  → 3个月延迟（各国央行）
      info_delay = 4  → 4个月延迟（美联储、财政部、欧央行、日央行）
      info_delay = 5  → 5个月延迟（能源国）

    soul 文件（可选）：
      agent_taxonomy.md 中定义的 soul 文件，通过 agents.yaml 的 soul_file 字段加载。
      加载后存储在 self.soul（dict），_decide_rules 可读取 doctrine / red_lines /
      internal_factions / cultural_prior 等字段影响决策。
      未配置 soul_file 时 self.soul 为 {}，不影响任何现有行为。
    """
    agent_id:                  str
    role:                      str
    info_delay:                int
    activation_prob:           float
    params:                    AgentParams = field(default_factory=AgentParams)
    transmission_coefficients: dict = field(default_factory=dict)
    soul:                      dict = field(default_factory=dict)   # soul 文件内容，可选

    # 运行时状态（不参与构造）
    activation_countdown: int = field(init=False, default=0)
    forced_activate:      bool = field(init=False, default=False)

    # 子类声明自己的合法动作列表
    VALID_ACTIONS: ClassVar[list[str]] = ["HOLD"]

    def __post_init__(self):
        self.activation_countdown = 0

    # ── 决策入口 ──────────────────────────────────────────

    def decide(self, ctx: dict, use_llm: bool = False) -> str:
        """
        ctx 包含：
          - 世界状态字段（来自 world.get_agent_context）
          - visible_actions：该 Agent 按延迟档能看到的其他 Agent 上步行动
        """
        if use_llm and hasattr(self, "_decide_llm"):
            action = self._decide_llm(ctx)
        else:
            action = self._decide_rules(ctx)

        if action not in self.VALID_ACTIONS:
            action = "HOLD"
        return action

    def decide_with_trace(self, ctx: dict, round_num: int = 0, use_llm: bool = False) -> "AgentOutput":
        """
        v3 新增：返回结构化 AgentOutput，包含因果链和预期状态变化。
        子类可覆盖 _build_output() 提供详细因果链。
        默认实现：调用 decide() 并构建最简 AgentOutput。
        """
        action = self.decide(ctx, use_llm=use_llm)
        output = AgentOutput(
            agent_id=self.agent_id,
            round=round_num,
            action=action,
        )
        # 子类可覆盖此方法填充因果链
        if hasattr(self, "_build_output"):
            output = self._build_output(ctx, action, round_num)
        return output

    def _decide_rules(self, ctx: dict) -> str:
        """子类覆盖。基类默认 HOLD。"""
        return "HOLD"

    # ── 参数调整接口（校准循环调用）──────────────────────

    def apply_param_adjustment(self, param: str, new_value: float):
        """校准循环调用，更新单个参数并 clamp。"""
        if param in ("sensitivity", "threshold", "magnitude"):
            setattr(self.params, param, new_value)
            self.params.clamp()

    # ── 序列化接口（预留）────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "agent_id":   self.agent_id,
            "role":       self.role,
            "info_delay": self.info_delay,
            "params":     self.params.to_dict(),
        }

    @classmethod
    def from_yaml(cls, cfg: dict) -> "MacroAgent":
        """预留接口：从 agents.yaml 的一条配置构建 Agent。子类覆盖以注入正确类型。"""
        raise NotImplementedError


# ── 结构化输出（v3 新增）────────────────────────────────────────────────────

@dataclass
class CausalChain:
    """一条因果链（用于天玑推理溯源）。"""
    chain_id:   str
    nodes:      List[str]          # ["台海紧张↑", "能源价格↑", "通胀压力↑"]
    confidence: float = 0.5
    source:     str = "rules"      # "rules" / "historical_match" / "llm_reasoning"

    def to_dict(self) -> dict:
        return {
            "chain_id":   self.chain_id,
            "nodes":      self.nodes,
            "confidence": round(self.confidence, 3),
            "source":     self.source,
        }


@dataclass
class StateChangePrediction:
    """Agent 预期会引发的世界状态变化。"""
    variable:  str    # e.g. "us_10y_yield", "usd_cny", "oil_price"
    direction: str    # "up" / "down" / "stable"
    magnitude: str    # e.g. "10-20bp", "0.5-1%", "small"
    horizon:   str    # e.g. "1w", "1m", "3m"

    def to_dict(self) -> dict:
        return {
            "variable":  self.variable,
            "direction": self.direction,
            "magnitude": self.magnitude,
            "horizon":   self.horizon,
        }


@dataclass
class AgentOutput:
    """
    Agent 一轮决策的完整结构化输出。
    用于：天玑推理溯源存档 + 价格更新机制输入 + 叙事生成。
    """
    agent_id:               str
    round:                  int
    action:                 str
    causal_chains:          List[CausalChain] = field(default_factory=list)
    expected_state_changes: List[StateChangePrediction] = field(default_factory=list)
    responding_to:          List[Dict[str, Any]] = field(default_factory=list)
    constraints:            List[str] = field(default_factory=list)
    key_uncertainties:      List[str] = field(default_factory=list)
    confidence:             float = 0.5
    time_horizon:           str = "1m"
    # 类型专属字段（各子类填充）
    type_specific:          Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent_id":               self.agent_id,
            "round":                  self.round,
            "action":                 self.action,
            "causal_chains":          [c.to_dict() for c in self.causal_chains],
            "expected_state_changes": [s.to_dict() for s in self.expected_state_changes],
            "responding_to":          self.responding_to,
            "constraints":            self.constraints,
            "key_uncertainties":      self.key_uncertainties,
            "confidence":             round(self.confidence, 3),
            "time_horizon":           self.time_horizon,
            "type_specific":          self.type_specific,
        }

