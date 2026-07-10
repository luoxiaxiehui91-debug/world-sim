"""
social.py — 社会/舆论类 Agent（A6/A10）
"""

from core.agents.base import MacroAgent, AgentParams
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class MediaAgent(MacroAgent):
    """A6：媒体/舆论 — 1个月延迟，高激活频率"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "AMPLIFY_FEAR", "NEUTRAL_REPORT", "HOLD", "AMPLIFY_OPTIMISM"
    ]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        sentiment  = ctx.get("market_sentiment", 0)
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        vix_stress = ctx.get("vix_stress", 0) * p.sensitivity
        visible    = ctx.get("visible_actions", {})
        # 对冲基金做空是媒体的好题材
        hf_short   = visible.get("hedge_fund") == "SHORT_MARKET"
        # 散户恐慌也会被放大报道
        retail_panic = visible.get("retail") == "PANIC_SELL"

        # 情绪已充分恐慌时不继续放大（避免单向推到底）
        if sentiment < -0.5:
            return "HOLD"
        if sentiment < -(p.threshold * 0.7) or grv_stress > p.threshold * 1.0:
            return "AMPLIFY_FEAR"
        if hf_short and sentiment < -(p.threshold * 0.4):
            return "AMPLIFY_FEAR"
        if retail_panic and sentiment < -(p.threshold * 0.4):
            return "AMPLIFY_FEAR"
        if sentiment > p.threshold * 0.6 and grv_stress < p.threshold * 0.2:
            return "AMPLIFY_OPTIMISM"
        if abs(sentiment) < p.threshold * 0.2:
            return "NEUTRAL_REPORT"
        return "HOLD"


@dataclass
class RetailAgent(MacroAgent):
    """A10：散户/羊群 — 0延迟，高激活频率，跟随媒体和机构放大波动"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "PANIC_SELL", "HOLD", "FOMO_BUY"
    ]

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        sentiment  = ctx.get("market_sentiment", 0)
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        visible    = ctx.get("visible_actions", {})
        # 散户直接受媒体报道驱动
        media_fear     = visible.get("media") == "AMPLIFY_FEAR"
        media_optimism = visible.get("media") == "AMPLIFY_OPTIMISM"
        hf_short       = visible.get("hedge_fund") == "SHORT_MARKET"

        # 媒体放大恐慌 + 对冲基金做空 → 散户跟风抛售
        if media_fear or (hf_short and sentiment < -(p.threshold * 0.3)):
            return "PANIC_SELL"
        # 媒体乐观 + 市场情绪好 → 追涨
        if media_optimism and sentiment > p.threshold * 0.4:
            return "FOMO_BUY"
        return "HOLD"
