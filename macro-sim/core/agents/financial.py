"""
financial.py — 金融类 Agent（A1/A2/A3/A5/A9/A11/A12）

规则设计原则：
- 每个条件先乘以 sensitivity，再和 threshold 比较
- 每个行动产生的 delta 乘以 magnitude
- visible_actions 让 Agent 能感知到其他 Agent 的上步行动
"""

from core.agents.base import MacroAgent, AgentParams
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class FedAgent(MacroAgent):
    """A1：美联储 — 4个月延迟，低激活频率"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "CUT_50BP", "CUT_25BP", "HOLD", "HIKE_25BP", "VERBAL_INTERVENTION"
    ]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        sentiment  = ctx.get("market_sentiment", 0)
        vix_stress = ctx.get("vix_stress", 0) * p.sensitivity
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        spread     = ctx.get("credit_spread", 250)
        fed_change = ctx.get("fed_rate_change", 0)

        # 市场深度恐慌 → 大幅降息
        if sentiment < -(p.threshold * 0.8) or vix_stress > p.threshold * 1.2:
            return "CUT_50BP"
        # 压力上升 → 小幅降息或口头干预
        if sentiment < -(p.threshold * 0.5) or vix_stress > p.threshold * 0.8:
            return "CUT_25BP"
        # GRV高位但情绪尚可 → 口头安抚
        if grv_stress > p.threshold * 0.8 and sentiment > -0.2:
            return "VERBAL_INTERVENTION"
        # 经济过热 → 加息
        if sentiment > p.threshold * 1.0 and fed_change < 0:
            return "HIKE_25BP"
        return "HOLD"


@dataclass
class CommercialBankAgent(MacroAgent):
    """A2：商业银行风控 — 2个月延迟"""
    VALID_ACTIONS: ClassVar[list[str]] = ["TIGHTEN_CREDIT", "HOLD", "EASE_CREDIT"]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        spread     = ctx.get("credit_spread", 250)
        tightening = ctx.get("bank_credit_tightening", 0)
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        vix_stress = ctx.get("vix_stress", 0) * p.sensitivity
        # 看到对冲基金做空或散户恐慌 → 提前收紧
        visible    = ctx.get("visible_actions", {})
        hf_action  = visible.get("hedge_fund", "HOLD")
        retail_act = visible.get("retail", "HOLD")

        tighten_signal = (
            spread > 250 + p.threshold * 150
            or grv_stress > p.threshold * 0.8
            or vix_stress > p.threshold * 0.7
            or hf_action == "SHORT_MARKET"
            or retail_act == "PANIC_SELL"
        )
        ease_signal = (
            spread < 200
            and tightening < p.threshold * 0.3
            and grv_stress < p.threshold * 0.3
        )

        if tighten_signal:
            return "TIGHTEN_CREDIT"
        if ease_signal:
            return "EASE_CREDIT"
        return "HOLD"


@dataclass
class HedgeFundAgent(MacroAgent):
    """A3：对冲基金 — 0延迟，每步必激活，最灵敏"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "SHORT_MARKET", "DECREASE_RISK", "HOLD", "INCREASE_RISK"
    ]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        vix_stress = ctx.get("vix_stress", 0) * p.sensitivity
        ext_shift  = ctx.get("external_pressure_shift", 0) * p.sensitivity
        sentiment  = ctx.get("market_sentiment", 0)
        yield_inv  = ctx.get("yield_inverted", 0)
        visible    = ctx.get("visible_actions", {})
        media_fear = visible.get("media") == "AMPLIFY_FEAR"

        # 已充分定价（情绪低于-0.4）→ 止盈观望，不追空
        if sentiment < -0.4:
            return "HOLD"
        # 高压信号 → 做空
        if grv_stress > p.threshold * 0.8 or vix_stress > p.threshold * 0.6 or media_fear:
            return "SHORT_MARKET"
        # 中等压力 → 降险
        if ext_shift > p.threshold * 0.5 or yield_inv:
            return "DECREASE_RISK"
        # 环境改善 → 加仓
        if grv_stress < p.threshold * 0.2 and vix_stress < p.threshold * 0.2 and sentiment > 0.1:
            return "INCREASE_RISK"
        return "HOLD"


@dataclass
class InstitutionAgent(MacroAgent):
    """A5：机构投资者（养老金/主权基金）— 2个月延迟，保守"""
    VALID_ACTIONS: ClassVar[list[str]] = ["DECREASE_RISK", "HOLD", "INCREASE_RISK"]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        vix_stress = ctx.get("vix_stress", 0) * p.sensitivity
        yield_inv  = ctx.get("yield_inverted", 0)
        visible    = ctx.get("visible_actions", {})
        # 看到对冲基金已做空2步 → 跟进降险
        hf_shorted = visible.get("hedge_fund") == "SHORT_MARKET"

        if grv_stress > p.threshold * 0.9 or vix_stress > p.threshold * 0.8 or yield_inv:
            return "DECREASE_RISK"
        if hf_shorted and grv_stress > p.threshold * 0.5:
            return "DECREASE_RISK"
        if grv_stress < p.threshold * 0.2 and vix_stress < p.threshold * 0.2:
            return "INCREASE_RISK"
        return "HOLD"


@dataclass
class USTreasuryAgent(MacroAgent):
    """A9：美国财政部 — 4个月延迟，低频"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "FISCAL_STIMULUS", "HOLD", "FISCAL_TIGHTEN", "DEBT_CEILING_RISK"
    ]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        sentiment      = ctx.get("market_sentiment", 0)
        fiscal_pressure = ctx.get("us_fiscal_pressure", 0) * p.sensitivity
        vix_stress     = ctx.get("vix_stress", 0) * p.sensitivity
        visible        = ctx.get("visible_actions", {})
        fed_cut        = visible.get("fed") in ("CUT_25BP", "CUT_50BP")

        # 经济危机时配合美联储财政刺激
        if sentiment < -(p.threshold * 0.8) and fed_cut:
            return "FISCAL_STIMULUS"
        # 财政压力过大 → 债务上限风险信号
        if fiscal_pressure > p.threshold * 1.2:
            return "DEBT_CEILING_RISK"
        # 经济过热时收紧
        if sentiment > p.threshold * 0.9 and fiscal_pressure < p.threshold * 0.3:
            return "FISCAL_TIGHTEN"
        return "HOLD"


@dataclass
class ECBAgent(MacroAgent):
    """A11：欧洲央行 — 4个月延迟，跟随美联储但有时滞"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "CUT_25BP", "HOLD", "HIKE_25BP", "QE_EXPAND", "QE_TIGHTEN"
    ]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        sentiment  = ctx.get("market_sentiment", 0)
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        vix_stress = ctx.get("vix_stress", 0) * p.sensitivity
        visible    = ctx.get("visible_actions", {})
        # 欧央行通常滞后美联储1-2步
        fed_cut  = visible.get("fed") in ("CUT_25BP", "CUT_50BP")
        fed_hike = visible.get("fed") == "HIKE_25BP"

        if sentiment < -(p.threshold * 0.6) or (fed_cut and grv_stress > p.threshold * 0.4):
            return "CUT_25BP"
        if grv_stress > p.threshold * 1.0:
            return "QE_EXPAND"
        if fed_hike and sentiment > 0:
            return "HIKE_25BP"
        return "HOLD"


@dataclass
class BOJAgent(MacroAgent):
    """A12：日本央行 — 4个月延迟，YCC政策，套息平仓是关键风险"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "HOLD", "ABANDON_YCC", "EASE_YCC", "EMERGENCY_EASE"
    ]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        yen_carry  = ctx.get("yen_carry_risk", 0) * p.sensitivity
        vix_stress = ctx.get("vix_stress", 0) * p.sensitivity
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        visible    = ctx.get("visible_actions", {})
        fed_hike   = visible.get("fed") == "HIKE_25BP"

        # 套息平仓压力触发放弃YCC → 引爆全球流动性危机
        if yen_carry > p.threshold * 1.0 or (fed_hike and yen_carry > p.threshold * 0.6):
            return "ABANDON_YCC"
        # 市场危机时紧急宽松
        if vix_stress > p.threshold * 1.1:
            return "EMERGENCY_EASE"
        # 压力上升时放松YCC上限
        if grv_stress > p.threshold * 0.7:
            return "EASE_YCC"
        return "HOLD"
