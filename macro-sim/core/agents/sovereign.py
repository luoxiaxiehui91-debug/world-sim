"""
sovereign.py — SovereignAgent 基类（B+A/NOVEL 框架核心）

设计：
- 继承 MacroAgent，复用三参数接口（sensitivity/threshold/magnitude）
- 通过 self.soul 读取 doctrine/red_lines/internal_factions/grv_impact_map
- 基于当前世界状态动态计算派系权重，决定本步倾向
- red_lines 触发时强制输出升级行动
- 输出行动对应 soul.grv_impact_map 中定义的 GRV 影响方向

Board（全局联盟/制裁/冲突状态矩阵）：
- 模块级单例 dict，各 SovereignAgent 读写
- 键：(actor_a, actor_b) → 关系状态 {"type": "sanction|alliance|conflict", "intensity": 0~1}
- 每步由 SecretaryAgent（暂用 validate_action 模拟）验证行动一致性

版本：v1.0（2026-08-03）
"""

import random
from dataclasses import dataclass, field
from typing import ClassVar

from core.agents.base import MacroAgent, AgentParams, ActionDecision, _eval_trigger


# ── Board：全局关系矩阵（单例）─────────────────────────────────
# 键：(actor_id_a, actor_id_b)，小写字母序排列
# 值：{"type": str, "intensity": float, "since": int}
BOARD: dict = {}


def board_get(a: str, b: str) -> dict:
    """获取两个 Actor 之间的关系状态。"""
    key = tuple(sorted([a, b]))
    return BOARD.get(key, {"type": "neutral", "intensity": 0.0})


def board_set(a: str, b: str, rel_type: str, intensity: float, since: int = 0):
    """更新两个 Actor 之间的关系状态。"""
    key = tuple(sorted([a, b]))
    BOARD[key] = {"type": rel_type, "intensity": min(1.0, max(0.0, intensity)), "since": since}


def board_clear():
    """重置 Board（每次仿真开始时调用）。"""
    BOARD.clear()


# ── 辅助：解析 soul 中的触发条件字符串 ──────────────────────────
def _eval_trigger(trigger_str: str, ctx: dict) -> bool:
    """
    简单解析 soul 文件中的触发条件字符串。
    支持：变量名 > 数值、变量名 < 数值、AND、OR
    示例："russia_europe > 70 OR taiwan_strait > 75"
    不支持复杂嵌套；解析失败返回 False。
    """
    if not trigger_str:
        return False
    try:
        # 用安全的方式解析：只允许 ctx 中的数值变量和简单比较
        # 将条件字符串转换为可求值表达式
        expr = trigger_str
        # 替换变量名为 ctx.get("var", 0)
        import re
        # 找出所有变量名（字母/数字/下划线，不以数字开头）
        vars_in_expr = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', expr)
        for var in vars_in_expr:
            if var in ("AND", "OR", "NOT", "and", "or", "not"):
                continue
            val = ctx.get(var, 0.0)
            if isinstance(val, (int, float)):
                expr = re.sub(r'\b' + var + r'\b', str(float(val)), expr)
        # 替换 AND/OR
        expr = expr.replace(" AND ", " and ").replace(" OR ", " or ")
        return bool(eval(expr))  # noqa: S307 — 已限制为数值比较，无注入风险
    except Exception:
        return False


# ── SovereignAgent 基类 ─────────────────────────────────────────
@dataclass
class SovereignAgent(MacroAgent):
    """
    主权国家/集团 Agent 基类。

    v3 阶段 1：soul 决策逻辑已上移至 MacroAgent._decide_soul()（base.py），
    本类 _decide_rules 仅作为"无 soul 时"的 fallback（HOLD）。
    Board 读写（联盟/制裁/冲突关系）保留。
    """

    # 默认行动空间（子类按 soul 中 action_space 字段覆盖或扩展）
    VALID_ACTIONS: ClassVar[list[str]] = [
        "HOLD",
        "IMPOSE_SANCTIONS",
        "LIFT_SANCTIONS",
        "MILITARY_DEPLOYMENT",
        "DIPLOMATIC_ENGAGE",
        "TECH_RESTRICTION",
        "ALLIANCE_REINFORCE",
        "CUT_OUTPUT",
        "INCREASE_OUTPUT",
        "EMBARGO_SIGNAL",
        # v2.2：俄罗斯特色行动（S4_russia soul grv_impact_map 定义，加入合法空间；
        # S1-S3 的 soul 未定义 → 实际不会产生，无副作用）
        "NUCLEAR_SIGNAL",
        "ENERGY_CUTOFF",
        "CEASEFIRE_SIGNAL",
    ]

    def _decide_rules(self, ctx: dict) -> str:
        """
        v3 阶段 1：soul 决策已由 MacroAgent.decide_with_decision() → _decide_soul()
        统一处理（red_line → 派系权重 → 抽样 → bias_actions）。
        本方法仅在"无 soul"时被调用（fallback）——主权 Agent 无 soul 一律 HOLD。
        """
        return "HOLD"

    def _faction_to_action(self, faction_name: str, ctx: dict) -> str:
        """
        将激活的派系映射到具体行动。
        优先使用 soul.grv_impact_map 中定义的行动，回退到硬编码映射。
        子类可覆盖以提供更精确的映射。
        """
        # 从 grv_impact_map 获取所有可用行动
        impact_map = self.soul.get("grv_impact_map", {})
        available_actions = [a for a in impact_map.keys() if a in self.VALID_ACTIONS]

        # 派系倾向映射（通用规则）
        faction_bias = self._get_faction_bias()
        biased_actions = faction_bias.get(faction_name, [])

        # 优先选择该派系有偏好且在 impact_map 中的行动
        preferred = [a for a in biased_actions if a in available_actions]
        if preferred:
            return preferred[0]

        # 其次从 impact_map 中随机选（有行动意愿）
        if available_actions and random.random() < self.params.threshold:
            return random.choice(available_actions)

        return "HOLD"

    def _get_faction_bias(self) -> dict:
        """
        返回各派系的行动偏好映射。
        v2.2 A2 修复：优先从 soul.internal_factions.{faction}.bias_actions 读取
        （soul 可自定义派系名与偏好，不再依赖硬编码表名——A2_china/A3_eu/A6_russia 的
        nationalists/pragmatists/atlanticists/strategic_autonomy 等派系名不再被拒）；
        无 bias_actions 时 fallback 硬编码通用表。
        格式：{faction_name: [preferred_action1, preferred_action2, ...]}
        """
        bias = self._soul_faction_bias()
        if bias:
            return bias
        return {
            # 鹰派：倾向强制手段
            "hawks":           ["MILITARY_DEPLOYMENT", "IMPOSE_SANCTIONS", "TECH_RESTRICTION"],
            "security_hawks":  ["MILITARY_DEPLOYMENT", "EMBARGO_SIGNAL", "IMPOSE_SANCTIONS"],
            "fiscal_hawks":    ["CUT_OUTPUT", "EMBARGO_SIGNAL"],
            # 鸽派：倾向外交/经济
            "doves":           ["DIPLOMATIC_ENGAGE", "LIFT_SANCTIONS", "HOLD"],
            # 经济/现代化派
            "domestic_lobby":  ["HOLD", "DIPLOMATIC_ENGAGE"],
            "modernization_wing": ["INCREASE_OUTPUT", "DIPLOMATIC_ENGAGE"],
        }

    def _soul_faction_bias(self) -> dict:
        """A2 修复：从 soul.internal_factions.{faction}.bias_actions 读派系偏好（仅保留 VALID_ACTIONS 内行动）。"""
        bias = {}
        factions = (self.soul or {}).get("internal_factions", {})
        for fname, fdata in factions.items():
            ba = fdata.get("bias_actions")
            if ba:
                bias[fname] = [a for a in ba if a in self.VALID_ACTIONS]
        return bias

    def _escalation_action(self, ctx: dict) -> str:
        """
        Red Line 触发时的强制升级行动。
        基于 soul.grv_impact_map 选择影响最大的行动。
        子类可覆盖。
        """
        impact_map = self.soul.get("grv_impact_map", {})
        # 选择 impact_map 中影响幅度最大的行动
        best_action = "HOLD"
        best_score = 0.0
        for action, impacts in impact_map.items():
            if action not in self.VALID_ACTIONS:
                continue
            # 计算行动的总绝对影响（所有 GRV 维度变化之和）
            score = sum(abs(v) for v in impacts.values() if isinstance(v, (int, float)))
            if score > best_score:
                best_score = score
                best_action = action
        return best_action

    def get_grv_impact(self, action: str) -> dict:
        """
        返回指定行动对 GRV 各维度的预期影响。
        供仿真引擎（未来 B+A/NOVEL 重写时）消费。
        """
        impact_map = self.soul.get("grv_impact_map", {})
        return impact_map.get(action, {})


# ── EnergyGovSovereignAgent：A4 升级版 ─────────────────────────
@dataclass
class EnergyGovSovereignAgent(SovereignAgent):
    """
    A4（能源国/OPEC+）的 SovereignAgent 版本。
    继承 SovereignAgent，覆盖行动空间和派系偏好。
    与 EnergyGovAgent（geopolitical.py）向后兼容：
    - 无 soul 时行为退化为 HOLD（不调用旧规则以避免双重逻辑）
    - soul 加载后使用派系权重决策
    """
    VALID_ACTIONS: ClassVar[list[str]] = [
        "HOLD",
        "CUT_OUTPUT",
        "INCREASE_OUTPUT",
        "EMBARGO_SIGNAL",
        "DIPLOMATIC_OUTREACH",
        "MILITARY_DEPLOYMENT",
    ]

    def _get_faction_bias(self) -> dict:
        bias = self._soul_faction_bias()
        if bias:
            return bias
        return {
            "fiscal_hawks":       ["CUT_OUTPUT", "EMBARGO_SIGNAL"],
            "modernization_wing": ["INCREASE_OUTPUT", "DIPLOMATIC_OUTREACH"],
            "security_hawks":     ["MILITARY_DEPLOYMENT", "EMBARGO_SIGNAL"],
        }

    def _decide_rules(self, ctx: dict) -> str:
        """
        v3 阶段 1：有 soul 时走 MacroAgent.decide_with_decision() → _decide_soul()
        （base 统一管线，不经过本方法）；本方法仅为"无 soul"fallback：
        能源紧张→减产，否则 HOLD（向后兼容 A4 挂起态）。
        """
        # 无 soul 的简单规则（向后兼容；A4 挂起 activation=0 实际不调用）
        energy_tension = ctx.get("energy_tension", 0) * self.params.sensitivity
        if energy_tension > self.params.threshold * 0.8:
            return "CUT_OUTPUT"
        return "HOLD"
