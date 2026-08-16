"""
base.py — MacroAgent 基类 + AgentParams + ActionDecision（v3 统一决策框架）

设计：
- 每个 Agent 暴露三个可调参数（sensitivity/threshold/magnitude）
- 参数由校准循环自动调整，变更记录到 calibration_log.jsonl
- Agent 决策时可见上一步其他 Agent 的行动（按信息延迟档）
- 预留接口：from_yaml() 支持从 agents.yaml 加载

v3 新增（阶段 1，2026-08-07）：
- ActionDecision dataclass：统一决策输出（action/reason/evidence/faction/confidence/source）
- MacroAgent.decide() → ActionDecision：统一 soul 决策管线
  （red_line_triggers → 派系权重 → 加权抽样 → bias_actions），
  无 soul 时 fallback 到子类 _decide_rules（if-else 包一层，行为与 v2 一致）
- _eval_trigger 从 sovereign.py 上移（missing_strategy 支持，v1.3 语义）
- decision_temperature：soul 级可配（0=argmax 确定性 / 1=标准抽样）
- 设计文档：docs/tianxuan-v3-soul-redesign.md §3
"""

import re
import random
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


# ── 决策输出（v3 阶段 1）────────────────────────────────────────────────────

@dataclass
class ActionDecision:
    """
    统一决策输出（v3 阶段 1，设计文档 §3.2）。

    所有 Agent（金融 + 主权 + 未来新增）的 decide() 都返回此结构，
    让决策理由可校验（需求①）：action + reason + evidence 三要素。
    """
    action: str                 # VALID_ACTIONS 内行动，必填
    reason: str                 # 自然语言理由，中文
    evidence: dict              # 结构化证据：signals/trigger_hit/faction_weights/...
    alternative: Optional[str] = None   # 次优行动（加权抽样第二候选），无则 None
    faction: Optional[str] = None       # 选中派系（soul 模式）或 "legacy_rules"（fallback）
    confidence: float = 1.0     # 0~1，= 选中派系归一化权重（fallback 时规则确定性 1.0）
    source: str = "soul"        # "soul" | "legacy_rules" | "red_line" | "llm"

    def to_dict(self) -> dict:
        return {
            "action":       self.action,
            "reason":       self.reason,
            "evidence":     self.evidence,
            "alternative":  self.alternative,
            "faction":      self.faction,
            "confidence":   round(self.confidence, 3),
            "source":       self.source,
        }


# ── 触发条件解析（v3 阶段 1：从 sovereign.py 上移，供所有 soul Agent 使用）──

# v3 阶段 2：eval 表达式里允许的内置函数名（不当作 ctx 变量替换）
_BUILTIN_FUNCS = frozenset(
    "abs min max round int float len sum str bool pow".split()
)

def _eval_trigger(trigger_str: str, ctx: dict, missing_strategy: str = "optimistic") -> bool:
    """
    解析 soul 触发条件字符串（数值表达式）。
    支持：变量名 > 数值、变量名 < 数值、AND、OR、==
    示例："russia_europe > 70 OR taiwan_strait > 75"

    missing_strategy（v1.3 R-P1 语义修正）：
      - conservative = 按最坏情况求值（缺失变量按 ±∞ 双极试算，任一触发即 True）——防御导向
      - optimistic   = 缺失归 0（假设信号正常不触发）——与 v2 行为一致（默认）
      - neutral      = 缺失归中性值（0.5）——折中
    未知变量名（含中文）解析失败返回 False（fail-loud 由 §7.4 启动校验覆盖）。
    """
    if not trigger_str:
        return False
    try:
        expr = trigger_str
        vars_in_expr = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', expr)
        missing = []
        for var in vars_in_expr:
            if var in ("AND", "OR", "NOT", "and", "or", "not"):
                continue
            # v3 阶段 2 修复：内置函数名（abs/min/max/round 等）不当作变量替换，
            # 否则 abs(market_sentiment) 会变成 0.0(market_sentiment)（SyntaxWarning + 恒 False）
            if var in _BUILTIN_FUNCS:
                continue
            val = ctx.get(var, None)
            if val is None:
                missing.append(var)
                expr = re.sub(r'\b' + var + r'\b', "_MISSING_", expr)
            elif isinstance(val, (int, float)):
                expr = re.sub(r'\b' + var + r'\b', str(float(val)), expr)
        expr = expr.replace(" AND ", " and ").replace(" OR ", " or ").replace(" == ", " == ")

        if missing:
            if missing_strategy == "optimistic":
                # 缺失变量归 0（v2 行为：ctx.get(var, 0.0)）
                expr = expr.replace("_MISSING_", "0.0")
                return bool(eval(expr))  # noqa: S307
            elif missing_strategy == "neutral":
                expr = expr.replace("_MISSING_", "0.5")
                return bool(eval(expr))  # noqa: S307
            elif missing_strategy == "conservative":
                # 按最坏情况：缺失变量分别按 ±∞ 试算，任一触发即 True（防御导向）
                for extreme in ("1e9", "-1e9"):
                    e2 = expr.replace("_MISSING_", extreme)
                    try:
                        if eval(e2):  # noqa: S307
                            return True
                    except Exception:
                        continue
                return False
            # 未知 missing_strategy → 保守处理：按 optimistic 语义
            expr = expr.replace("_MISSING_", "0.0")
            return bool(eval(expr))  # noqa: S307

        return bool(eval(expr))  # noqa: S307 — 已限制为数值比较，无注入风险
    except Exception:
        return False


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
    # 08-17 主权降频：red_line 冷却（决策计数制——红线命中后冷却期内不重复强制升级，
    # 修复全激活试验暴露的每步 NUCLEAR_SIGNAL/MILITARY_DEPLOYMENT 高频失真）
    _decision_count:      int = field(init=False, default=0)
    _last_redline_count:  int = field(init=False, default=-999)

    # 子类声明自己的合法动作列表
    VALID_ACTIONS: ClassVar[list[str]] = ["HOLD"]

    def __post_init__(self):
        self.activation_countdown = 0

    # ── 决策入口 ──────────────────────────────────────────

    def decide(self, ctx: dict, use_llm: bool = False) -> str:
        """
        v2 兼容入口：返回行动字符串（行为与 v2 完全一致）。
        v3 阶段 1 起内部走 decide_with_decision()，取 .action。
        """
        return self.decide_with_decision(ctx, use_llm=use_llm).action

    def decide_with_decision(self, ctx: dict, use_llm: bool = False) -> ActionDecision:
        """
        v3 统一决策出口：返回 ActionDecision（action/reason/evidence/faction/confidence/source）。

        决策路径：
          1. use_llm=True 且子类有 _decide_llm → LLM 决策
          2. 有 soul → _decide_soul()（统一 soul 管线：red_line → 派系权重 → 抽样 → bias_actions）
          3. 无 soul → _decide_rules() 包一层（legacy_rules fallback，行为与 v2 一致）
        结果不在 VALID_ACTIONS → HOLD（fail-loud 记录 evidence）。
        """
        if use_llm and hasattr(self, "_decide_llm"):
            action = self._decide_llm(ctx)
            return ActionDecision(
                action=action if action in self.VALID_ACTIONS else "HOLD",
                reason="LLM 决策",
                evidence={"signals": self._snapshot_signals(ctx)},
                faction="llm",
                source="llm",
            )

        if self.soul:
            return self._decide_soul(ctx)

        # fallback：无 soul → 原 if-else 包一层（行为兼容）
        action = self._decide_rules(ctx)
        if action not in self.VALID_ACTIONS:
            action = "HOLD"
        return ActionDecision(
            action=action,
            reason="legacy_rules（if-else 规则）",
            evidence={"signals": self._snapshot_signals(ctx)},
            faction="legacy_rules",
            confidence=1.0,
            source="legacy_rules",
        )

    def _decide_soul(self, ctx: dict) -> ActionDecision:
        """
        统一 soul 决策管线（v3 阶段 1，设计文档 §3.3）：
          ① red_line_triggers 命中 → 强制行动（source="red_line"）
          ② 派系权重 = base_weight × boost(trigger命中) × params.sensitivity
          ③ 加权抽样选派系（decision_temperature=0 → argmax 确定性）
          ④ 派系 bias_actions 选行动（HOLD 兜底）
        soul 缺失字段用中性默认值；无派系 → HOLD（reason 记录）。
        """
        missing_strategy = (self.soul or {}).get("missing_strategy", "optimistic")
        # flag_* 布尔派生（v1.2 P2-1：从 visible_actions 派生，走 info_delay 分层）
        ctx = self._derive_soul_flags(ctx)

        # 08-17 主权降频：red_line 冷却期判定（决策计数制）
        self._decision_count += 1
        # 主权类（VALID_ACTIONS 含核信号/军事）冷却 6 次决策，其余 2 次
        rl_cooldown = 6 if "NUCLEAR_SIGNAL" in self.VALID_ACTIONS else 2
        rl_cooling = (self._decision_count - self._last_redline_count) < rl_cooldown

        # ① red_line_triggers（v2.2 D2：数值表达式；red_lines 中文仅叙事）
        # 支持两种格式：list[str]（走 _escalation_action，S 类格式）/
        #               dict{trigger: action}（金融 soul 格式，指定强制行动）
        rl_spec = self.soul.get("red_line_triggers", []) or []
        rl_items = rl_spec.items() if isinstance(rl_spec, dict) else [(x, None) for x in rl_spec]
        for rl, rl_action in rl_items:
            if rl_cooling:
                break  # 冷却期内红线不生效，走正常派系决策
            if _eval_trigger(rl, ctx, missing_strategy=missing_strategy):
                if rl_action:
                    esc = rl_action if rl_action in self.VALID_ACTIONS else "HOLD"
                else:
                    esc = self._escalation_action(ctx)
                    if esc not in self.VALID_ACTIONS:
                        esc = "HOLD"
                self._last_redline_count = self._decision_count
                return ActionDecision(
                    action=esc,
                    reason=f"red_line 触发：{rl}",
                    evidence={
                        "trigger_hit": rl,
                        "signals": self._snapshot_signals(ctx),
                        "red_line_hit": rl,
                    },
                    faction=self._escalation_faction(),
                    confidence=1.0,
                    source="red_line",
                )

        # ② 派系权重
        factions = self.soul.get("internal_factions", {}) or {}
        if not factions:
            return ActionDecision(
                action="HOLD",
                reason="soul 无 internal_factions，HOLD",
                evidence={"signals": self._snapshot_signals(ctx)},
                faction=None,
                confidence=1.0,
                source="soul",
            )

        temperature = float(self.soul.get("decision_temperature", 1.0))
        boost = float(self.soul.get("faction_boost", 1.3))
        weighted = {}
        trigger_hits = {}
        for fname, fdata in factions.items():
            base_weight = float(fdata.get("weight", 0.33) if isinstance(fdata, dict) else 0.33)
            trigger = fdata.get("trigger", "") if isinstance(fdata, dict) else ""
            hit = _eval_trigger(trigger, ctx, missing_strategy=missing_strategy) if trigger else False
            trigger_hits[fname] = hit
            weighted[fname] = base_weight * (boost if hit else 1.0) * self.params.sensitivity
        total = sum(weighted.values())
        if total <= 0:
            return ActionDecision(
                action="HOLD",
                reason="派系权重合计为 0，HOLD",
                evidence={"signals": self._snapshot_signals(ctx), "faction_weights": weighted},
                faction=None,
                confidence=1.0,
                source="soul",
            )
        norm = {k: v / total for k, v in weighted.items()}

        # ③ 抽样选派系（temperature=0 → argmax 确定性）
        if temperature <= 0:
            chosen = max(norm, key=norm.get)
            chosen_weight = norm[chosen]
        else:
            r = random.random() * total
            cumulative = 0.0
            chosen = list(weighted.keys())[0]
            for fname, w in weighted.items():
                cumulative += w
                if r <= cumulative:
                    chosen = fname
                    break
            chosen_weight = norm[chosen]

        # alternative = 次优派系的 bias 首行动（纯查表，不调 _faction_to_action ——
        # 避免额外消耗 random 序列导致 S 类 MC 结果与 v2.2 定稿参数错位）
        sorted_factions = sorted(norm, key=norm.get, reverse=True)
        alt_faction = sorted_factions[1] if len(sorted_factions) > 1 else None
        alt_action = None
        if alt_faction:
            alt_bias = self._soul_faction_bias().get(alt_faction, [])
            alt_action = alt_bias[0] if alt_bias else None

        # ④ 派系行动
        action = self._faction_to_action(chosen, ctx)
        if action not in self.VALID_ACTIONS:
            action = "HOLD"
        hit_str = " | ".join(f"{k}:{v}" for k, v in trigger_hits.items() if v) or "无命中"
        return ActionDecision(
            action=action,
            reason=f"{chosen} 派系选中（权重 {chosen_weight:.2f}；trigger 命中：{hit_str}）",
            evidence={
                "signals": self._snapshot_signals(ctx),
                "trigger_hit": next((k for k, v in trigger_hits.items() if v), None),
                "faction_weights": {k: round(v, 3) for k, v in norm.items()},
                "selected_faction": chosen,
                "bias_actions": self._soul_faction_bias().get(chosen, []),
                "red_line_hit": None,
            },
            alternative=alt_action,
            faction=chosen,
            confidence=round(chosen_weight, 3),
            source="soul",
        )

    # ── soul 管线辅助（v3 阶段 1：从 sovereign.py 上移通用版本）───────────

    def _derive_soul_flags(self, ctx: dict) -> dict:
        """
        v1.2 P2-1：从 visible_actions 派生 flag_* 布尔 ctx 字段（走 info_delay 分层——
        visible_actions 已按 Agent 的 info_delay 延迟注入，禁止从当前步直接取行动）。
        返回浅拷贝 ctx + flag 字段；无 visible_actions 时原样返回。
        支持：flag_hf_short / flag_media_fear / flag_retail_panic / flag_fed_cut / flag_fed_hike。
        """
        visible = ctx.get("visible_actions")
        if not isinstance(visible, dict):
            return ctx
        flags = {
            "flag_hf_short":     1.0 if visible.get("hedge_fund") == "SHORT_MARKET" else 0.0,
            "flag_media_fear":   1.0 if visible.get("media") == "AMPLIFY_FEAR" else 0.0,
            "flag_retail_panic": 1.0 if visible.get("retail") == "PANIC_SELL" else 0.0,
            "flag_fed_cut":      1.0 if visible.get("fed") in ("CUT_25BP", "CUT_50BP") else 0.0,
            "flag_fed_hike":     1.0 if visible.get("fed") == "HIKE_25BP" else 0.0,
        }
        new_ctx = dict(ctx)
        new_ctx.update(flags)
        return new_ctx

    def _snapshot_signals(self, ctx: dict) -> dict:
        """采集 ctx 中的数值信号快照（trace evidence 用，限制规模防爆炸）。"""
        signals = {}
        for k, v in ctx.items():
            if isinstance(v, (int, float)) and k not in ("cycle",):
                signals[k] = round(float(v), 3)
            if len(signals) >= 24:
                break
        return signals

    def _escalation_faction(self) -> Optional[str]:
        """red_line 触发的派系标注（子类可覆盖）。默认 None。"""
        return "red_line"

    def _escalation_action(self, ctx: dict) -> str:
        """
        Red Line 触发时的强制升级行动。
        基于 soul.grv_impact_map 选择影响绝对值最大的行动；无 map 时取 VALID_ACTIONS 最后一个（含升级语义），再兜底 HOLD。
        子类可覆盖。
        """
        impact_map = (self.soul or {}).get("grv_impact_map", {})
        best_action = "HOLD"
        best_score = 0.0
        for action, impacts in impact_map.items():
            if action not in self.VALID_ACTIONS:
                continue
            score = sum(abs(v) for v in impacts.values() if isinstance(v, (int, float)))
            if score > best_score:
                best_score = score
                best_action = action
        if best_action == "HOLD" and self.VALID_ACTIONS:
            # 无 impact_map 定义时：取行动空间中语义最强的（非 HOLD 的最后一个）
            candidates = [a for a in self.VALID_ACTIONS if a != "HOLD"]
            if candidates:
                return candidates[-1]
        return best_action

    def _faction_to_action(self, faction_name: str, ctx: dict) -> str:
        """
        将激活派系映射到具体行动。
        优先 soul.internal_factions.{faction}.bias_actions（按列表序取第一个在 VALID_ACTIONS 的），
        其次 grv_impact_map 随机（threshold 概率），兜底 HOLD。
        子类可覆盖（如 EnergyGovSovereignAgent）。
        """
        bias = self._soul_faction_bias()
        preferred = bias.get(faction_name, [])
        if preferred:
            return preferred[0]
        # 无 bias_actions 时：从 grv_impact_map 中按 threshold 概率随机
        impact_map = (self.soul or {}).get("grv_impact_map", {})
        available = [a for a in impact_map.keys() if a in self.VALID_ACTIONS]
        if available and random.random() < self.params.threshold:
            return random.choice(available)
        return "HOLD"

    def _soul_faction_bias(self) -> dict:
        """从 soul.internal_factions.{faction}.bias_actions 读派系偏好（仅保留 VALID_ACTIONS 内行动）。"""
        bias = {}
        factions = (self.soul or {}).get("internal_factions", {}) or {}
        for fname, fdata in factions.items():
            if isinstance(fdata, dict):
                ba = fdata.get("bias_actions")
                if ba:
                    bias[fname] = [a for a in ba if a in self.VALID_ACTIONS]
        return bias

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
        """
        校准循环调用，更新单个参数并 clamp。
        v3 §5.5 A 路：支持 soul 派系权重路径 `internal_factions.{faction}.weight`
        （试点 soul 的 calib_ranges 区间约束由校准 prompt 表达）。
        """
        if param in ("sensitivity", "threshold", "magnitude"):
            setattr(self.params, param, new_value)
            self.params.clamp()
        elif param.startswith("internal_factions.") and param.endswith(".weight"):
            # v3：派系权重调参（soul 内 internal_factions.{faction}.weight）
            fname = param.split(".")[1]
            factions = (self.soul or {}).get("internal_factions", {}) or {}
            fdata = factions.get(fname)
            if isinstance(fdata, dict):
                fdata["weight"] = max(0.01, min(0.9, float(new_value)))
            elif self.soul:
                raise ValueError(f"soul 无派系 {fname}（{self.agent_id}）")
            else:
                # v3 阶段 2 防御：无 soul Agent 收到派系权重指令 → fail-loud 打印但跳过，
                # 不抛异常终止整个校准（校准 LLM 可能幻觉派系名/误判可调参数，如对照组的"看涨派系"）
                print(f"[calibrator] ⚠️ {self.agent_id} 无 soul，忽略派系权重指令 {param}（LLM 幻觉或误判，跳过）")
        else:
            raise ValueError(f"不支持的参数路径：{param}")

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

