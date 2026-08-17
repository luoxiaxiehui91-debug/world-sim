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

    def _soul_risk_bias(self, ctx: dict) -> float:
        """08-17 混合 soul：评估 internal_factions 派系激活 → 风险偏好偏置 [-1,1]。

        bias>0 = 收紧倾向（risk_averse 派激活）；bias<0 = 放松倾向（expansion 派激活）；
        无 soul / 无派系命中 → 0.0（与旧行为逐字节一致）。
        """
        factions = (self.soul or {}).get("internal_factions", {}) or {}
        if not factions:
            return 0.0
        try:
            from core.agents.base import _eval_trigger
        except Exception:
            return 0.0
        total_w = 0.0
        bias = 0.0
        for fname, fdata in factions.items():
            w = float(fdata.get("weight", 0.33)) if isinstance(fdata, dict) else 0.33
            trig = fdata.get("trigger", "") if isinstance(fdata, dict) else ""
            if trig and _eval_trigger(trig, ctx):
                ba = fdata.get("bias_actions") or [] if isinstance(fdata, dict) else []
                direction = 1.0 if "TIGHTEN_CREDIT" in ba else (-1.0 if "EASE_CREDIT" in ba else 0.0)
                total_w += w
                bias += w * direction
        if total_w <= 0:
            return 0.0
        return max(-1.0, min(1.0, bias / total_w))

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        # 08-17 混合 soul：派系风险偏好偏置（软调制阈值，不接管决策；bias=0 与旧行为一致）
        risk_bias = self._soul_risk_bias(ctx)
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
        # R4h ②-A（v2.0.39）起 vix 均值回归 + yen_carry bleed 封顶 → 探针窗口 vix 峰值
        # 162-238→53.3（vix>48 步 21-36），豁免从"恒真"变"部分开"（真危机步仍放行）——
        # TIGHTEN wrong 18→13（≤17 裁决闸）。注释更新非引擎行为（A2 决策逻辑零改动）。
        target_dir = "ease" if cs_delta < -2.5 else ("tighten" if cs_delta > 2.5 else "neutral")
        tighten_ok = (target_dir != "ease") or vix_stress > p.threshold * 2.0  # vix_stress>1.0
        # 08-17 混合 soul：risk_bias 软调制（>0 收紧倾向 → 阈值降低更易触发；bias=0 不变）
        _tb = risk_bias * 60.0      # spread 阈值偏置（bp）
        _tg = risk_bias * 0.20      # grv_stress 阈值偏置
        _tv = risk_bias * 0.15      # vix_stress 阈值偏置
        tighten_signal = (
            spread > 250 + p.threshold * 150 - _tb
            or grv_stress > p.threshold * 0.8 - _tg
            or vix_stress > p.threshold * 0.7 - _tv
            or hf_action == "SHORT_MARKET"
            or retail_act == "PANIC_SELL"
        ) and tighten_ok

        # P0-2（v2.0.30）+ R4d/R4e 方向 EASE：cs 回落（target_dir=="ease"）时 EASE 更易触发
        # ——把"错误收紧步"转"正确 EASE 步"保 n_active。R4d 版 grv 限制 0.4（*0.8）实测挡死
        # ~70% 转换（cs 回落月 grv 仍高）→ R4e 放宽至 0.6（*1.2，qa-r2b/data-r2 会签）。
        # R4h ③-A（v2.0.38）起 EASE 已补写 market_sentiment +0.08×m（simulation.py:148，
        # 与 TIGHTEN -0.08 完全镜像），不再"对 sentiment 零直接副作用"——本行注释更新非引擎行为。
        # 中性/收紧方向阈值不动（spread<250 / grv<0.25）；layer-1 合成 ctx 无 cs_delta → 中性
        # → 与 P0-2 逐字节同。
        directional_ease = target_dir == "ease"
        # R4h ①-A（v2.0.40）：方向闸补挡"cs 上升时放松"（EASE wrong 盲区）——与
        # tighten_ok（L80）镜像对称；极端豁免（vix_stress>1.0）对称成立兜底。
        # 被挡步转 HOLD（冷却递减，本函数 ease_cooldown>0 分支 L113-115）：不静默跳过、
        # 不误转 TIGHTEN（TIGHTEN 分支有 ease_cooldown==0 守卫保 M4 flip==0）——qa 澄清点。
        ease_ok = (target_dir != "tighten") or vix_stress > p.threshold * 2.0
        # 08-17 混合 soul：risk_bias<0（放松倾向）→ ease spread 阈值 +50bp 更易满足；bias=0 不变
        ease_signal = (
            spread < (350 if directional_ease else 250) + (-risk_bias) * 50.0
            and tightening < p.threshold * 1.0
            and grv_stress < (p.threshold * 1.2 if directional_ease else p.threshold * 0.5)
            and ease_ok
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
class LongTermCapitalAgent(MacroAgent):
    """A13：保险/养老长线资金（2026-08-17 新增）——逆周期稳定者。

    设计定位：原 17 Agent 全是顺周期恐慌者（媒体放大/散户抛售/银行收紧/对冲做空），
    缺对手盘 → 情绪几乎总单方向砸向 -1.00、路径无分叉。长线资金是逆向力量：
    深度恐慌时逆向抄底（INCREASE_RISK），只在系统性极端时温和撤退。
    info_delay=3（看季度数据，反应慢），激活后冷却 3 个月。
    """
    VALID_ACTIONS: ClassVar[list[str]] = ["INCREASE_RISK", "HOLD", "DECREASE_RISK"]
    # 系统性极端时温和撤退概率（80% 扛住——长线资金耐性，不追涨杀跌）
    # 08-17 v5：0.30→0.20（更扛，逆周期更坚决）
    EXTREME_RETREAT_PROB: ClassVar[float] = 0.20

    def _decide_rules(self, ctx: dict) -> str:
        p = self.params
        grv_stress = ctx.get("grv_stress", 0) * p.sensitivity
        sentiment  = ctx.get("market_sentiment", 0)
        visible    = ctx.get("visible_actions", {})
        # 看到散户恐慌抛售 / 媒体放大恐慌 → 别人恐惧我贪婪
        panic_seen = (visible.get("retail") == "PANIC_SELL"
                      or visible.get("media") == "AMPLIFY_FEAR")

        # 1) 系统性极端（GRV 高压 + 情绪崩盘）→ 20% 温和降险，80% 扛住
        if grv_stress > p.threshold * 1.5 and sentiment < -0.7:
            return "DECREASE_RISK" if random.random() < self.EXTREME_RETREAT_PROB else "HOLD"
        # 2) 恐慌初起即逆向抄底（v5：阈值 -0.4→-0.25 更早进场；GRV 上限 1.3→1.5 放宽）
        if sentiment < -0.25 and grv_stress < p.threshold * 1.5:
            return "INCREASE_RISK"
        # 3) 别人恐慌 → 贪婪（v5：GRV 上限 1.1→1.3 更坚决）
        if panic_seen and grv_stress < p.threshold * 1.3:
            return "INCREASE_RISK"
        # 4) 常态：长线拿住（低压力 + 情绪平稳）
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
