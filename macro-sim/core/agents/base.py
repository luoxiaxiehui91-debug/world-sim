"""
base.py — MacroAgent 基类 + AgentParams

设计：
- 每个 Agent 暴露三个可调参数（sensitivity/threshold/magnitude）
- 参数由校准循环自动调整，变更记录到 calibration_log.jsonl
- Agent 决策时可见上一步其他 Agent 的行动（按信息延迟档）
- 预留接口：from_yaml() 支持从 agents.yaml 加载
"""

from dataclasses import dataclass, field
from typing import ClassVar, Optional


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
    """
    agent_id:        str
    role:            str
    info_delay:      int    # 看到其他 Agent 行动的延迟（步数）
    activation_prob: float  # 每步被调度到的概率
    params:          AgentParams = field(default_factory=AgentParams)

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
