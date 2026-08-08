"""
financial.py — 金融类 Agent（A1/A2/A3/A5/A9/A11/A12）

规则设计原则：
- 每个条件先乘以 sensitivity，再和 threshold 比较
- 每个行动产生的 delta 乘以 magnitude
- visible_actions 让 Agent 能感知到其他 Agent 的上步行动

2026-08-06 路径多样性修复（question 20260714-low-path-diversity）：
- 高 GRV 下 A3/A5 规则单调（压力越大越做空/降险）→ 100 次 MC 98% 走压力路径、路径 B 仅 5%
- 修复：A3 高压分支加 25% 概率 INCREASE_RISK（超卖反弹抄底）、A5 高压降险分支加 20% 概率 HOLD（中性避险再平衡）
- 用现有动作表达对立行为（零 VALID_ACTIONS 改动、simulation 价格逻辑天然兼容）
- 概率为类常量，后续如需调参可移至 agents.yaml（from_yaml 预留接口）
"""

from core.agents.base import MacroAgent, AgentParams
from dataclasses import dataclass, field
from typing import ClassVar
import random


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
    """A2：商业银行风控 — 1个月延迟（R4b info_delay 2→1）"""
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
        # R4d：cs_delta 经 world 属性进 ctx（校准循环设置；非校准默认 0.0 → 生产路径不变）
        cs_delta   = ctx.get("credit_spread_delta", 0.0)

        # R4d 方向对齐（docs/r4c-b-a2-direction-alignment.md §1.2 + 终裁回退预案）：
        # |cs_delta|≥2.5bp 对应 credit target |t|=|cs_signal×0.6|≥EPS_TGT(0.03)（同口径）。
        # target_dir = ease：cs 回落（target 期望 EASE）→ 收紧即错，方向闸挡死。
        # R4d v1 曾删除危机豁免（终裁），实测 directional_ease 触发率仅 0.21-0.29 → 70-80%
        # cs 回落步转 HOLD→S 类→silence 0.57>0.50 超线 → 按终裁回退预案启用 vix>1.0 极端豁免：
        # cs 回落时收紧仅限 vix_stress>1.0（vix>48）极端危机；非极端 cs 回落仍挡死。
        # （vix 经 bleed 漂移可达 vix≈168，极端豁免仍会触发，但占比可控）
        target_dir = "ease" if cs_delta < -2.5 else ("tighten" if cs_delta > 2.5 else "neutral")
        tighten_ok = (target_dir != "ease") or vix_stress > p.threshold * 2.0  # vix_stress>1.0
        tighten_signal = (
            spread > 250 + p.threshold * 150
            or grv_stress > p.threshold * 0.8
            or vix_stress > p.threshold * 0.7
            or hf_action == "SHORT_MARKET"
            or retail_act == "PANIC_SELL"
        ) and tighten_ok

        # P0-2（v2.0.30）+ R4d 方向 EASE：cs 回落（target_dir=="ease"）时 EASE 更易触发
        # （spread 250→350、grv_stress 0.25→0.4）——把"错误收紧步"转"正确 EASE 步"保 n_active。
        # 中性/收紧方向沿用 P0-2 原阈值；layer-1 合成 ctx 无 cs_delta → 中性 → 与 P0-2 逐字节同。
        directional_ease = target_dir == "ease"
        ease_signal = (
            spread < (350 if directional_ease else 250)
            and tightening < p.threshold * 1.0
            and grv_stress < (p.threshold * 0.8 if directional_ease else p.threshold * 0.5)
        )

        # P0-2：EASE 后 2 步冷却防 flip-flop（v2.0.1 振荡史）。EASE 一步后
        # tightening 刚降回 <0.5，若 spread/grv 仍高压，下一步又 TIGHTEN →
        # EASE/TIGHTEN 交替振荡。冷却期跳过 TIGHTEN 分支（允许继续 EASE 或 HOLD）。
        ease_cooldown = getattr(self, "_ease_cooldown", 0)

        if tighten_signal and ease_cooldown == 0:
            return "TIGHTEN_CREDIT"
        if ease_signal:
            setattr(self, "_ease_cooldown", 2)
            return "EASE_CREDIT"
        if ease_cooldown > 0:
            setattr(self, "_ease_cooldown", ease_cooldown - 1)
        return "HOLD"


@dataclass
class HedgeFundAgent(MacroAgent):
    """A3：对冲基金 — 0延迟，每步必激活，最灵敏"""
    VALID_ACTIONS: ClassVar[list[str]] = [
        "SHORT_MARKET", "DECREASE_RISK", "HOLD", "INCREASE_RISK"
    ]
    # 2026-08-06 路径多样性修复：高 GRV 下超卖反弹概率（45%，初版 25% 实测不足以对抗
    # A2/A4/A6 等持续负向合力，sentiment 终值仍坍缩单路径；45% 接近公平博弈）
    OVERSOLD_BOUNCE_PROB: ClassVar[float] = 0.45

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        grv_stress   = ctx.get("grv_stress", 0) * p.sensitivity
        vix_stress   = ctx.get("vix_stress", 0) * p.sensitivity
        ext_shift    = ctx.get("external_pressure_shift", 0) * p.sensitivity
        sentiment    = ctx.get("market_sentiment", 0)
        yield_inv    = ctx.get("yield_inverted", 0)
        sp500_change = ctx.get("sp500_change", 0.0)
        visible      = ctx.get("visible_actions", {})
        media_fear   = visible.get("media") == "AMPLIFY_FEAR"

        # 已充分定价（情绪低于-0.4）→ 止盈观望，不追空
        if sentiment < -0.4:
            return "HOLD"
        # 标普6个月跌幅超10% → 趋势性做空
        if sp500_change < -0.10:
            return "SHORT_MARKET"
        # 高压信号 → 做空；但 25% 概率触发超卖反弹抄底（多空博弈，2026-08-06 路径多样性修复）
        if grv_stress > p.threshold * 0.8 or vix_stress > p.threshold * 0.6 or media_fear:
            if grv_stress > p.threshold * 0.8 and random.random() < self.OVERSOLD_BOUNCE_PROB:
                return "INCREASE_RISK"
            return "SHORT_MARKET"
        # 中等压力 → 降险
        if ext_shift > p.threshold * 0.5 or yield_inv or sp500_change < -0.05:
            return "DECREASE_RISK"
        # 环境改善 → 加仓
        if grv_stress < p.threshold * 0.2 and vix_stress < p.threshold * 0.2 and sentiment > 0.1:
            return "INCREASE_RISK"
        return "HOLD"


@dataclass
class InstitutionAgent(MacroAgent):
    """A5：机构投资者（养老金/主权基金）— 2个月延迟，保守"""
    VALID_ACTIONS: ClassVar[list[str]] = ["DECREASE_RISK", "HOLD", "INCREASE_RISK"]
    # 2026-08-06 路径多样性修复：高 GRV 下中性避险概率（35%，初版 20% 实测不足以形成路径分叉）
    SAFE_HAVEN_PROB: ClassVar[float] = 0.35

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        grv_stress   = ctx.get("grv_stress", 0) * p.sensitivity
        vix_stress   = ctx.get("vix_stress", 0) * p.sensitivity
        yield_inv    = ctx.get("yield_inverted", 0)
        sp500_change = ctx.get("sp500_change", 0.0)
        visible      = ctx.get("visible_actions", {})
        # 看到对冲基金已做空2步 → 跟进降险
        hf_shorted = visible.get("hedge_fund") == "SHORT_MARKET"

        # 标普6个月跌幅超10% → 强制降险（机构保本属性）
        if sp500_change < -0.10:
            return "DECREASE_RISK"
        if grv_stress > p.threshold * 0.9 or vix_stress > p.threshold * 0.8 or yield_inv:
            # 20% 概率选择中性避险再平衡（不追随单边，2026-08-06 路径多样性修复）
            if random.random() < self.SAFE_HAVEN_PROB:
                return "HOLD"
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
        ecb_rate   = ctx.get("ecb_rate", 3.0)
        visible    = ctx.get("visible_actions", {})
        # 欧央行通常滞后美联储1-2步
        fed_cut  = visible.get("fed") in ("CUT_25BP", "CUT_50BP")
        fed_hike = visible.get("fed") == "HIKE_25BP"

        if sentiment < -(p.threshold * 0.6) or (fed_cut and grv_stress > p.threshold * 0.4):
            return "CUT_25BP"
        # 实际利率偏高（>3.5%）且经济压力上升 → 倾向降息
        if ecb_rate > 3.5 and grv_stress > p.threshold * 0.3 and sentiment < 0:
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
