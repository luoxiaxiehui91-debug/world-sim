"""
geopolitical.py — 地缘政治类 Agent（A4/A7/A8）
"""

from core.agents.base import MacroAgent, AgentParams
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class EnergyGovAgent(MacroAgent):
    """A4：能源国(OPEC+) — 5个月延迟，低频，影响能源供给"""
    VALID_ACTIONS: ClassVar[list[str]] = ["CUT_SUPPLY", "HOLD", "INCREASE_SUPPLY"]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        energy_tension = ctx.get("energy_tension", 0) * p.sensitivity
        grv_stress     = ctx.get("grv_stress", 0) * p.sensitivity
        visible        = ctx.get("visible_actions", {})
        # 看到全球需求信号：机构降险 → 减产（油价保护）
        inst_decrease  = visible.get("institution") == "DECREASE_RISK"

        if energy_tension > p.threshold * 0.8 or grv_stress > p.threshold * 1.0:
            return "CUT_SUPPLY"
        if inst_decrease and energy_tension > p.threshold * 0.5:
            return "CUT_SUPPLY"
        if energy_tension < p.threshold * 0.2 and grv_stress < p.threshold * 0.2:
            return "INCREASE_SUPPLY"
        return "HOLD"


@dataclass
class EMCentralBankAgent(MacroAgent):
    """A7：新兴市场央行（代表性） — 3个月延迟"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "CAPITAL_CONTROLS", "RAISE_RATES", "HOLD", "CUT_25BP"
    ]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        outflow    = ctx.get("em_capital_outflow", 0) * p.sensitivity
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        vix_stress = ctx.get("vix_stress", 0) * p.sensitivity
        visible    = ctx.get("visible_actions", {})
        fed_hike   = visible.get("fed") == "HIKE_25BP"

        # 资本外流严重 → 资本管制
        if outflow > p.threshold * 1.0 or (fed_hike and outflow > p.threshold * 0.5):
            return "CAPITAL_CONTROLS"
        # 预防性加息
        if grv_stress > p.threshold * 0.7 and vix_stress > p.threshold * 0.5:
            return "RAISE_RATES"
        # 全球宽松 → 跟进降息
        fed_cut = visible.get("fed") in ("CUT_25BP", "CUT_50BP")
        if fed_cut and outflow < p.threshold * 0.2:
            return "CUT_25BP"
        return "HOLD"


@dataclass
class ChinaPBOCAgent(MacroAgent):
    """A8：中国央行/财政 — 3个月延迟，独立政策体系"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "CUT_RRR", "CUT_LPR", "FISCAL_STIMULUS_CN",
        "HOLD", "CNY_INTERVENTION", "TIGHTEN_CN"
    ]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        china_credit = ctx.get("china_credit_impulse", 0) * p.sensitivity
        grv_stress   = ctx.get("grv_stress", 0) * p.sensitivity
        sentiment    = ctx.get("market_sentiment", 0)
        usd_cny      = ctx.get("usd_cny", 7.1)
        visible      = ctx.get("visible_actions", {})
        # 中美战略维度上升 → 汇率干预
        us_china_grv = ctx.get("us_china_grv", 0) * p.sensitivity
        fed_hike     = visible.get("fed") == "HIKE_25BP"

        # 国内信用收缩 → 降准或财政刺激
        if china_credit < -(p.threshold * 0.6):
            return "CUT_RRR"
        if china_credit < -(p.threshold * 0.4) and sentiment < -0.2:
            return "FISCAL_STIMULUS_CN"
        # 人民币贬值压力大（>7.3）→ 汇率干预
        if usd_cny > 7.3:
            return "CNY_INTERVENTION"
        # 中美紧张 + 美联储加息 → 汇率干预
        if us_china_grv > p.threshold * 0.8 and fed_hike:
            return "CNY_INTERVENTION"
        # 全球危机时逆周期刺激
        if grv_stress > p.threshold * 1.0 and sentiment < -(p.threshold * 0.5):
            return "FISCAL_STIMULUS_CN"
        # 过热时收紧
        if china_credit > p.threshold * 0.8:
            return "TIGHTEN_CN"
        return "HOLD"
