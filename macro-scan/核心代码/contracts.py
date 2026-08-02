"""
contracts.py — world-sim 天枢 · 跨指标统一数据契约（I1，横切件）

━━ 这个模块回答一个问题：「这份指标产出的形状对不对」━━━━━━━━━━━━━━━━━━━━━━━

它**不**回答「这个源喂给哪个目标」（那是 D4，A 流第一任务，必须复用本模块的
基类与 schema_version 约定，不得另起炉灶；不够用走 expand 加字段，不走重写）。

设计契约（方案 v3 §6.2 / §6.3 / §7.4）：

  1. extra="forbid"    未知字段直接 ValidationError。脏数据混进生产的成本，
                       远高于「多一个字段先收下」的便利。

  2. 非平凡哨兵         NaN / Inf 在任何数值字段上都是非法的；缺失**不能**用
                       裸 None 或 0 表达，必须走 status 枚举 + 必填 reason。
                       ——「0」在 z-score 语境里 = 常态，补零 = 静默捏造
                       「无压力」观测（§7.4 G2 铁律的类型系统化身）。

  3. schema_version    **契约版本**（这份记录的形状），当前 "1.0"，Literal 锁死。
     model_ver         **模型版本**（算出这个数的算法），如 "fci-1.1"/"probit-1.0"。
                       两者独立演进：换模型不动契约，改契约不动模型。
                       ⚠️ 现网 fci_latest.json 把 "fci-1.1" 写进 schema_version，
                       这是**语义错位**，本契约的直接动因之一（见 §FCI 兼容）。

  4. 默认拒绝的用途白名单  usage_policy.allow 是白名单，未列出即禁止。
                       fci_revised 含 look-ahead → deny backtest/brier；
                       fci_pit 无 look-ahead → allow。这是本项目最贵的一条
                       经验（§7.3），提升为契约一等公民，而不是散在注释里。

运行环境：Python 3.11 + pydantic 2.x（NAS 容器实测 3.11.15 / pydantic 2.13.4）

自检：
    python contracts.py --selftest     # 跑全部断言用例，任一失败 exit 1
    python contracts.py --demo         # 打印 FCI / probit 契约实例 JSON
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Final, Literal, Mapping, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# ── 契约版本 ──────────────────────────────────────────────────────────────────
# 只在**记录形状**变化时才动（加/删/改字段语义）。换模型、改系数、调窗口
# 一律不动这里，动 model_ver。
CONTRACT_VERSION: Final[str] = "1.0"

__all__ = [
    "CONTRACT_VERSION",
    "ValueStatus",
    "Unit",
    "Purpose",
    "UsagePolicy",
    "IndicatorPoint",
    "IndicatorEnvelope",
    "UsageViolation",
    "build_point",
    "missing_point",
    "dump_envelope",
    "normalize_legacy_fci",
]


# ── 异常 ─────────────────────────────────────────────────────────────────────


class UsageViolation(RuntimeError):
    """消费方拿一个指标点去做它被禁止的用途。fail-loud，不降级不警告。"""


# ── 枚举 ─────────────────────────────────────────────────────────────────────


class ValueStatus(str, Enum):
    """
    非平凡哨兵。**这是本契约的核心**——「缺失」不是一个数值，是一个状态。

    OK          value 是真实的、有限的、可消费的读数
    MISSING     上游没有数据（序列断档 / 未采集 / ffill 超 limit 被剔除）
    DEGRADED    算出来了，但质量闸门没过（§7.4 G3：成分 <4/5 或样本不足）
                → 保留 status_reason 供诊断，但**任何人不得消费**
    SUPPRESSED  算出来了、质量也够，但用途策略主动扣发（如 revised 轨被请求
                做 Brier 打分时，产出侧直接不给值，而不是给了再指望下游自觉）
    """

    OK = "ok"
    MISSING = "missing"
    DEGRADED = "degraded"
    SUPPRESSED = "suppressed"


class Unit(str, Enum):
    """
    闭集。加新单位必须改这里 = 强制一次 code review，防「unit: '标准差'」
    和「unit: 'sd'」这类同义异名在库里并存。
    """

    ZSCORE = "zscore"  # 标准差单位（FCI）
    PROBABILITY = "probability"  # [0,1] 概率（probit）——注意不是百分数
    PERCENT = "percent"  # 0-100 百分数
    BP = "bp"  # 基点
    INDEX = "index"  # 无量纲指数
    RATIO = "ratio"  # 比值
    COUNT = "count"  # 计数（火点数、事件数）
    USD = "usd"


class Purpose(str, Enum):
    """
    消费用途。取值与现网 fci_latest.json.usage_policy 完全一致（零迁移成本），
    额外补 SIM_TRIGGER（§6.4 v3：允许 L1/L3 additive 写 trigger_reason）。
    """

    NOWCAST = "nowcast"  # 当期读数
    DASHBOARD = "dashboard"  # 日报 / 仪表盘展示
    ALERTING = "alerting"  # 阈值告警
    SIM_TRIGGER = "sim_trigger"  # 触发天璇推演
    BACKTEST = "backtest"  # 历史回测
    VERIFICATION = "verification"  # 预测验证
    BRIER = "brier"  # Brier 打分（天玑校准）


# ── 正则约束 ─────────────────────────────────────────────────────────────────

_KEY_RE: Final = r"^[a-z][a-z0-9_]{2,63}$"
_MODEL_VER_RE: Final = r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*-\d+\.\d+$"
_SOURCE_RE: Final = r"^[a-z][a-z0-9_.\-]{1,31}$"
_HORIZON_RE: Final = r"^(nowcast|\d{1,3}[DWMQY])$"
_PRODUCER_RE: Final = r"^[a-z_][a-z0-9_]*\.py$"


def _require_aware(dt: datetime, field: str) -> datetime:
    """时区裸奔的 datetime 一律拒收——跨容器 / 跨时区比时间是经典静默错源。"""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field} 必须带时区（tz-aware），拒收 naive datetime")
    return dt


# ── 用途策略 ─────────────────────────────────────────────────────────────────


class UsagePolicy(BaseModel):
    """
    **默认拒绝**的用途白名单。

    语义：`purpose in allow` 才准用。既不在 allow 也不在 deny 的用途 = 禁止。
    deny 存在的意义不是「补集」，而是**显式记录一条被认真讨论过的红线**，
    让 code review 能看见「这里曾经有人想干这事，被否了」。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    allow: frozenset[Purpose] = Field(default_factory=frozenset)
    deny: frozenset[Purpose] = Field(default_factory=frozenset)
    note: str = Field(min_length=8, max_length=600)

    @model_validator(mode="after")
    def _no_overlap(self) -> "UsagePolicy":
        both = self.allow & self.deny
        if both:
            raise ValueError(
                f"usage_policy.allow 与 deny 交叉，语义自相矛盾: "
                f"{sorted(p.value for p in both)}"
            )
        return self

    def permits(self, purpose: "Purpose | str") -> bool:
        return Purpose(purpose) in self.allow

    def assert_permits(
        self, purpose: "Purpose | str", *, indicator_key: str = "<unknown>"
    ) -> None:
        p = Purpose(purpose)
        if p in self.allow:
            return
        why = "显式 deny" if p in self.deny else "未在 allow 白名单内（默认拒绝）"
        raise UsageViolation(
            f"[{indicator_key}] 禁止用途 '{p.value}'：{why}。"
            f"allow={sorted(x.value for x in self.allow)} "
            f"deny={sorted(x.value for x in self.deny)}。策略说明：{self.note}"
        )


# ── 指标点（记录级契约）──────────────────────────────────────────────────────


class IndicatorPoint(BaseModel):
    """
    一个指标在一个时点上的一次读数。**天枢所有指标产出的唯一记录形状。**

    字段与 §6.2 indicators 宽表一一对应，
    UNIQUE(indicator_key, as_of, horizon, model_ver, data_vintage) = identity_key()
    """

    model_config = ConfigDict(
        extra="forbid",  # ← 硬要求 1：未知字段炸
        frozen=True,  # 构造即定型，下游不得就地改
        allow_inf_nan=False,  # ← 硬要求 2 之一：pydantic 层直接拒 NaN/Inf
        str_strip_whitespace=True,
        validate_default=True,
        protected_namespaces=(),  # 允许 model_ver / model_params 用 model_ 前缀
    )

    # ── 契约与模型版本（硬要求 3：两个独立字段）──────────────────────────
    schema_version: Literal["1.0"] = Field(
        description="契约版本 = 这条记录的形状版本。与算法无关。"
    )
    model_ver: str = Field(
        pattern=_MODEL_VER_RE,
        description="模型版本 = 算出这个数的算法版本，如 fci-1.1 / probit-1.0。",
    )

    # ── 身份 ────────────────────────────────────────────────────────────
    indicator_key: str = Field(
        pattern=_KEY_RE, description="指标唯一键，snake_case，如 fci_revised。"
    )
    as_of: date = Field(
        description="决策时点 / 观测日期：这个读数**描述的是哪一天**。"
    )
    horizon: str = Field(
        pattern=_HORIZON_RE, description="预测视野：nowcast / 12M / 30D …"
    )

    # ── 取值 + 哨兵（硬要求 2）──────────────────────────────────────────
    status: ValueStatus
    value: Optional[float] = Field(
        default=None,
        description="status==OK 时必须为有限实数；否则必须为 None。禁 NaN。",
    )
    unit: Unit
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    status_reason: Optional[str] = Field(
        default=None,
        max_length=300,
        description="status!=OK 时必填且 ≥8 字符——挡住 'n/a' / '-' 这类敷衍。",
    )

    # ── 溯源 ────────────────────────────────────────────────────────────
    source: str = Field(
        pattern=_SOURCE_RE,
        description="落盘层来源标识，如 fred_history / nasa_firms / ucdp_ged。",
    )
    inputs: tuple[str, ...] = Field(
        default=(), description="输入序列 / 字段清单，status==OK 时必须非空。"
    )
    data_vintage: date = Field(
        description=(
            "上游数据实际新鲜度 = 各输入序列**最新真实观测日**的最小值（保守下界）。"
            "ffill 补出来的日子不算数（§7.4 G2 / 坑⑤）。"
        )
    )
    created_at: datetime = Field(description="本条记录的写入时间，必须 tz-aware。")

    # ── 用途策略（硬要求 4）─────────────────────────────────────────────
    usage_policy: UsagePolicy

    # ── 可选：可复现性与诊断 ────────────────────────────────────────────
    model_params: Optional[Mapping[str, float]] = Field(
        default=None,
        description="复现该读数所需的数值参数（probit 的 alpha/beta、FCI 的载荷）。只收 float。",
    )
    diagnostics: Optional[Mapping[str, Any]] = Field(
        default=None,
        description=(
            "自由诊断信息（面板行数、sanity 相关性…）。"
            "⚠️ 契约红线：**任何生产消费方不得读 diagnostics 做决策**，"
            "它只给人看。需要机器读的字段必须走 expand 提升为一等字段。"
        ),
    )

    # ── 字段级校验 ──────────────────────────────────────────────────────

    @field_validator("value", "ci_low", "ci_high")
    @classmethod
    def _reject_nonfinite(cls, v: Optional[float]) -> Optional[float]:
        """allow_inf_nan=False 的兜底：直接构造（非 validate）路径也拦住。"""
        if v is None:
            return v
        if math.isnan(v) or math.isinf(v):
            raise ValueError(
                "NaN/Inf 非法：缺失必须用 status 哨兵显式表达，"
                "禁止用 NaN 冒充数据、禁止用 0 冒充缺失"
            )
        return v

    @field_validator("inputs")
    @classmethod
    def _clean_inputs(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for s in v:
            if not s or s != s.strip():
                raise ValueError(f"inputs 含空串或带空白的项: {s!r}")
        if len(set(v)) != len(v):
            raise ValueError(f"inputs 存在重复项: {v}")
        return v

    @field_validator("created_at")
    @classmethod
    def _created_at_aware(cls, v: datetime) -> datetime:
        return _require_aware(v, "created_at")

    @field_validator("model_params")
    @classmethod
    def _params_finite(
        cls, v: Optional[Mapping[str, float]]
    ) -> Optional[Mapping[str, float]]:
        if v is None:
            return v
        for k, x in v.items():
            if not isinstance(x, (int, float)) or isinstance(x, bool):
                raise ValueError(f"model_params[{k!r}] 必须是数值，收到 {type(x).__name__}")
            if math.isnan(float(x)) or math.isinf(float(x)):
                raise ValueError(f"model_params[{k!r}] 为 NaN/Inf，非法")
        return v

    # ── 跨字段校验 ──────────────────────────────────────────────────────

    @model_validator(mode="after")
    def _sentinel_contract(self) -> "IndicatorPoint":
        """哨兵铁律：status 与 value 必须严格互锁，不留「看起来有值」的灰区。"""
        if self.status is ValueStatus.OK:
            if self.value is None:
                raise ValueError("status=ok 但 value 为 None：要么给值，要么改 status")
            if self.status_reason is not None:
                raise ValueError("status=ok 不得带 status_reason（无事可说）")
            if not self.inputs:
                raise ValueError("status=ok 必须声明 inputs（溯源不可省）")
            if not self.usage_policy.allow:
                raise ValueError(
                    "status=ok 但 usage_policy.allow 为空 = 这个点没有任何合法消费方，"
                    "即死数据；请显式声明用途或不要产出"
                )
        else:
            if self.value is not None:
                raise ValueError(
                    f"status={self.status.value} 但 value={self.value!r}："
                    "缺失/降级的点绝不允许携带数值（防下游误读）"
                )
            if self.ci_low is not None or self.ci_high is not None:
                raise ValueError(f"status={self.status.value} 不得携带置信区间")
            if not self.status_reason or len(self.status_reason.strip()) < 8:
                raise ValueError(
                    f"status={self.status.value} 必须给 ≥8 字符的 status_reason，"
                    "说明为什么没有值"
                )
            if self.usage_policy.allow:
                raise ValueError(
                    f"status={self.status.value} 的点不可被任何用途消费，"
                    f"usage_policy.allow 必须为空，实收 "
                    f"{sorted(p.value for p in self.usage_policy.allow)}"
                )
        return self

    @model_validator(mode="after")
    def _unit_domain(self) -> "IndicatorPoint":
        """单位定义域。probability 越界最常见的成因是把 15.01(%) 当成概率写进来。"""
        if self.unit is Unit.PROBABILITY and self.value is not None:
            if not (0.0 <= self.value <= 1.0):
                raise ValueError(
                    f"unit=probability 但 value={self.value} 不在 [0,1]："
                    "是不是把百分数（0-100）当概率了？百分数请用 unit=percent"
                )
        if self.unit is Unit.COUNT and self.value is not None:
            if self.value < 0 or self.value != int(self.value):
                raise ValueError(f"unit=count 要求非负整数，收到 {self.value}")
        return self

    @model_validator(mode="after")
    def _ci_bounds(self) -> "IndicatorPoint":
        lo, hi = self.ci_low, self.ci_high
        if (lo is None) != (hi is None):
            raise ValueError("ci_low / ci_high 必须成对出现（§6.2 拆两列）")
        if lo is not None and hi is not None:
            if lo > hi:
                raise ValueError(f"ci_low({lo}) > ci_high({hi})")
            if self.value is not None and not (lo <= self.value <= hi):
                raise ValueError(f"value({self.value}) 落在 [{lo}, {hi}] 之外")
        return self

    @model_validator(mode="after")
    def _time_order(self) -> "IndicatorPoint":
        """时间序不可倒置——倒置几乎总意味着字段被填错了位置。"""
        if self.data_vintage > self.as_of:
            raise ValueError(
                f"data_vintage({self.data_vintage}) > as_of({self.as_of})："
                "上游数据不可能来自未来"
            )
        created_day = self.created_at.astimezone(timezone.utc).date()
        if created_day < self.as_of - timedelta(days=1):
            raise ValueError(
                f"created_at({created_day}) 早于 as_of({self.as_of})："
                "疑似把运行时间戳与观测日期填反了（现网 FCI 正是此错）"
            )
        return self

    # ── 便利方法 ────────────────────────────────────────────────────────

    def identity_key(self) -> tuple[str, date, str, str, date]:
        """§6.2 UNIQUE(indicator_key, as_of, horizon, model_ver, data_vintage)"""
        return (
            self.indicator_key,
            self.as_of,
            self.horizon,
            self.model_ver,
            self.data_vintage,
        )

    def to_row(self) -> dict[str, Any]:
        """展平成 §6.2 indicators 宽表的一行（只 INSERT，不 UPDATE/DELETE）。"""
        return {
            "indicator_key": self.indicator_key,
            "as_of": self.as_of.isoformat(),
            "data_vintage": self.data_vintage.isoformat(),
            "horizon": self.horizon,
            "value": self.value,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "model_ver": self.model_ver,
            "created_at": self.created_at.isoformat(),
            "schema_version": self.schema_version,
            "status": self.status.value,
        }

    def assert_usable_for(self, purpose: "Purpose | str") -> "IndicatorPoint":
        """消费入口。天玑/开阳/日报统一走这里取值，别直接摸 .value。"""
        if self.status is not ValueStatus.OK:
            raise UsageViolation(
                f"[{self.indicator_key}] status={self.status.value}，不可消费："
                f"{self.status_reason}"
            )
        self.usage_policy.assert_permits(purpose, indicator_key=self.indicator_key)
        return self


# ── 文件级信封 ───────────────────────────────────────────────────────────────


class IndicatorEnvelope(BaseModel):
    """
    一个 *_latest.json 文件的顶层形状。加载期 fail-loud 的落点。
    """

    model_config = ConfigDict(
        extra="forbid", frozen=True, protected_namespaces=(), str_strip_whitespace=True
    )

    schema_version: Literal["1.0"]
    producer: str = Field(pattern=_PRODUCER_RE, description="产出脚本文件名。")
    generated_at: datetime
    points: tuple[IndicatorPoint, ...] = Field(min_length=1)
    diagnostics: Optional[Mapping[str, Any]] = None

    @field_validator("generated_at")
    @classmethod
    def _gen_aware(cls, v: datetime) -> datetime:
        return _require_aware(v, "generated_at")

    @model_validator(mode="after")
    def _consistency(self) -> "IndicatorEnvelope":
        seen: set[tuple] = set()
        for p in self.points:
            if p.schema_version != self.schema_version:
                raise ValueError(
                    f"点 {p.indicator_key} 的 schema_version={p.schema_version} "
                    f"与信封 {self.schema_version} 不一致"
                )
            k = p.identity_key()
            if k in seen:
                raise ValueError(f"同一文件内 identity_key 重复（§6.2 UNIQUE 违约）: {k}")
            seen.add(k)
        return self

    def get(self, indicator_key: str) -> IndicatorPoint:
        for p in self.points:
            if p.indicator_key == indicator_key:
                return p
        raise KeyError(
            f"信封内无 {indicator_key!r}；现有: {[p.indicator_key for p in self.points]}"
        )


# ── 构造助手 ─────────────────────────────────────────────────────────────────


def build_point(**kwargs: Any) -> IndicatorPoint:
    """schema_version 自动填当前契约版本，其余透传。"""
    kwargs.setdefault("schema_version", CONTRACT_VERSION)
    kwargs.setdefault("status", ValueStatus.OK)
    return IndicatorPoint(**kwargs)


def missing_point(
    *,
    indicator_key: str,
    as_of: date,
    horizon: str,
    unit: Unit,
    source: str,
    data_vintage: date,
    model_ver: str,
    created_at: datetime,
    reason: str,
    status: ValueStatus = ValueStatus.MISSING,
) -> IndicatorPoint:
    """构造一个「显式缺口」——这是 fillna(0) 的正确替代物。"""
    return IndicatorPoint(
        schema_version=CONTRACT_VERSION,
        indicator_key=indicator_key,
        as_of=as_of,
        horizon=horizon,
        status=status,
        value=None,
        unit=unit,
        status_reason=reason,
        source=source,
        inputs=(),
        data_vintage=data_vintage,
        model_ver=model_ver,
        created_at=created_at,
        usage_policy=UsagePolicy(
            allow=frozenset(), deny=frozenset(Purpose), note=f"无值点，禁止一切消费：{reason}"
        ),
    )


def dump_envelope(env: IndicatorEnvelope, path: str) -> None:
    """
    落盘。`allow_nan=False` 是关键——Python 的 json 默认会把 NaN 写成裸 `NaN`
    （非法 JSON），下游解析器行为各异，是典型静默污染源。
    """
    payload = env.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)


def normalize_legacy_fci(rec: Mapping[str, Any]) -> dict[str, Any]:
    """
    读旧 FCI 记录（含 fci_vintage_log.csv 中切换前的行）时的兼容层。

    旧写法把模型版本塞进了 schema_version：`schema_version="fci-1.1"`。
    识别规则：schema_version 不是 `\\d+\\.\\d+` 形状 → 它其实是 model_ver，
    该记录属于「前契约期」，schema_version 记为 "0"。
    """
    out = dict(rec)
    sv = str(out.get("schema_version", "")).strip()
    if sv and not sv.replace(".", "", 1).isdigit():
        out["model_ver"] = sv
        out["schema_version"] = "0"
        out["_legacy"] = True
    return out


# ── 契约实例示例（同时充当 QA fixture）────────────────────────────────────────

_FCI_INPUTS = ("T10Y2Y", "BAA10Y", "BAMLH0A0HYM2", "VIXCLS", "DTWEXBGS")
_FCI_LOADINGS = {
    "load_T10Y2Y": 0.4361,
    "load_BAA10Y": 0.5516,
    "load_BAMLH0A0HYM2": 0.6369,
    "load_VIXCLS": -0.0013,
    "load_DTWEXBGS": -0.3162,
    "pc1_var_ratio": 0.4234,
}
_RUN_AT = datetime.fromisoformat("2026-07-31T07:59:21+08:00")


def example_fci_points() -> tuple[IndicatorPoint, IndicatorPoint]:
    """现网 fci_latest.json（2026-07-31 实测值）套用本契约后的样子。"""
    common = dict(
        as_of=date(2026, 7, 30),  # ← 原 payload 的 "date"
        horizon="nowcast",
        unit=Unit.ZSCORE,
        source="fred_history",
        inputs=_FCI_INPUTS,
        data_vintage=date(2026, 7, 24),
        model_ver="fci-1.1",
        created_at=_RUN_AT,  # ← 原 payload 的 "as_of"（其实是运行时间戳）
        model_params=_FCI_LOADINGS,
    )
    revised = build_point(
        indicator_key="fci_revised",
        value=-0.942287,
        usage_policy=UsagePolicy(
            allow={Purpose.NOWCAST, Purpose.DASHBOARD, Purpose.ALERTING},
            deny={Purpose.BACKTEST, Purpose.VERIFICATION, Purpose.BRIER},
            note="全样本 PCA 重估，含 look-ahead，历史会被修订；越高=金融条件越紧。",
        ),
        diagnostics={
            "panel_rows": 840,
            "panel_range": "2023-05-22 ~ 2026-07-30",
            "sanity_vs_nfci_corr_level": 0.8284,
            "sanity_status": "PASS",
        },
        **common,
    )
    pit = build_point(
        indicator_key="fci_pit",
        value=-0.942287,
        usage_policy=UsagePolicy(
            allow={
                Purpose.NOWCAST,
                Purpose.BACKTEST,
                Purpose.VERIFICATION,
                Purpose.BRIER,
            },
            deny=frozenset(),
            note="扩展窗 PCA，仅用 <= t 数据，无 look-ahead；burn-in=504 交易日。",
        ),
        diagnostics={"pit_burnin": 504, "sanity_vs_nfci_corr_level": 0.4672},
        **common,
    )
    return revised, pit


def example_probit_point() -> IndicatorPoint:
    """计划落地的 probit_latest.json（2026-07-29 T10Y3M=0.84 → 15.01%）。"""
    return build_point(
        indicator_key="recession_prob",
        as_of=date(2026, 7, 29),
        horizon="12M",
        value=0.150147,
        unit=Unit.PROBABILITY,
        source="fred_history",
        inputs=("T10Y3M",),
        data_vintage=date(2026, 7, 29),
        model_ver="probit-1.0",
        created_at=datetime.fromisoformat("2026-08-01T05:40:00+08:00"),
        model_params={"alpha": -0.5333, "beta": -0.5984, "t10y3m": 0.84},
        usage_policy=UsagePolicy(
            allow={
                Purpose.NOWCAST,
                Purpose.DASHBOARD,
                Purpose.ALERTING,
                Purpose.BACKTEST,
                Purpose.VERIFICATION,
                Purpose.BRIER,
            },
            deny=frozenset(),
            note=(
                "闭式 Phi(alpha+beta*T10Y3M)，系数取 Estrella-Trubin(2006) 固定值、"
                "不做本地拟合，故无本地 look-ahead，允许回测。"
                "⚠️ 对 <=2006 样本打分存在文献 in-sample 偏，Brier 建议限 2007 之后。"
            ),
        ),
        diagnostics={"formula": "Phi(alpha + beta * T10Y3M)", "gate": "G1 口径断言=T10Y3M"},
    )


def example_envelope() -> IndicatorEnvelope:
    r, p = example_fci_points()
    return IndicatorEnvelope(
        schema_version=CONTRACT_VERSION,
        producer="compute_fci.py",
        generated_at=_RUN_AT,
        points=(r, p),
        diagnostics={"note": "机读禁区，仅供人眼诊断"},
    )


# ── QA 断言用例（spec-first；QA 可直接扩充本表）────────────────────────────────


def _expect_reject(name: str, fn, must_mention: str = "") -> tuple[str, bool, str]:
    try:
        fn()
    except (ValidationError, ValueError, TypeError, UsageViolation) as e:
        msg = str(e)
        if must_mention and must_mention not in msg:
            return (name, False, f"拒收了但理由不含 {must_mention!r}: {msg[:120]}")
        return (name, True, "")
    return (name, False, "本应拒收，却通过了")


def _expect_accept(name: str, fn) -> tuple[str, bool, str]:
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        return (name, False, f"本应通过，却报错: {type(e).__name__}: {str(e)[:160]}")
    return (name, True, "")


def run_selftest() -> int:
    ok_fci, pit_fci = example_fci_points()
    base = ok_fci.model_dump()

    def mutate(**over):
        d = dict(base)
        d.update(over)
        return lambda: IndicatorPoint(**d)

    results: list[tuple[str, bool, str]] = []
    R = results.append

    # ── A. extra=forbid ────────────────────────────────────────────────
    R(_expect_reject("A1 未知字段被拦截", mutate(fci_revsed=-0.94), "fci_revsed"))
    R(_expect_reject("A2 拼写错的已知字段也拦（vintage vs data_vintage）",
                     mutate(vintage="2026-07-24")))
    R(_expect_reject("A3 信封层同样 forbid", lambda: IndicatorEnvelope(
        schema_version=CONTRACT_VERSION, producer="compute_fci.py",
        generated_at=_RUN_AT, points=(ok_fci,), extra_key=1)))

    # ── B. schema_version 与 model_ver 独立 ────────────────────────────
    R(_expect_reject("B1 把 model_ver 写进 schema_version 被拒",
                     mutate(schema_version="fci-1.1")))
    R(_expect_reject("B2 把契约版本写进 model_ver 被拒（缺前缀）",
                     mutate(model_ver="1.0")))
    R(_expect_accept("B3 同契约版本可换模型版本",
                     mutate(model_ver="fci-2.0")))
    R(("B4 两字段确为独立取值",
       ok_fci.schema_version == "1.0" and ok_fci.model_ver == "fci-1.1", ""))
    R(_expect_reject("B5 未知契约版本被拒（Literal 锁死）",
                     mutate(schema_version="1.1")))
    R(_expect_reject("B6 model_ver 大小写/格式不合规被拒",
                     mutate(model_ver="FCI-1.1")))

    # ── C. 非平凡哨兵 ──────────────────────────────────────────────────
    R(_expect_reject("C1 value=NaN 被拒", mutate(value=float("nan"))))
    R(_expect_reject("C2 value=+Inf 被拒", mutate(value=float("inf"))))
    R(_expect_reject("C3 status=ok 但 value=None 被拒", mutate(value=None)))
    R(_expect_reject("C4 status=missing 却带值被拒",
                     mutate(status="missing", status_reason="上游 DTWEXBGS 断档超 ffill limit")))
    R(_expect_reject("C5 status=degraded 且无 reason 被拒",
                     mutate(status="degraded", value=None)))
    R(_expect_reject("C6 status!=ok 的 reason 太短（'n/a'）被拒",
                     mutate(status="missing", value=None, status_reason="n/a")))
    R(_expect_accept("C7 合法缺口点可构造", lambda: missing_point(
        indicator_key="fci_revised", as_of=date(2026, 7, 30), horizon="nowcast",
        unit=Unit.ZSCORE, source="fred_history", data_vintage=date(2026, 7, 24),
        model_ver="fci-1.1", created_at=_RUN_AT,
        reason="G3 覆盖率闸未过：可用成分 3/5 < 4")))
    R(("C8 缺口点的 value 确为 None 而非 0",
       missing_point(indicator_key="fci_revised", as_of=date(2026, 7, 30),
                     horizon="nowcast", unit=Unit.ZSCORE, source="fred_history",
                     data_vintage=date(2026, 7, 24), model_ver="fci-1.1",
                     created_at=_RUN_AT, reason="G3 覆盖率闸未过").value is None, ""))
    R(_expect_accept("C9 合法的 0 值不被误判为缺失", mutate(value=0.0)))
    R(_expect_reject("C10 model_params 含 NaN 被拒",
                     mutate(model_params={"alpha": float("nan")})))

    # ── D. 单位定义域 ──────────────────────────────────────────────────
    R(_expect_reject("D1 probability 收到百分数 15.01 被拒",
                     mutate(unit="probability", value=15.01), "0,1"))
    R(_expect_accept("D2 probability 收到 0.1501 通过",
                     mutate(unit="probability", value=0.1501)))
    R(_expect_reject("D3 未知单位被拒", mutate(unit="标准差")))
    R(_expect_reject("D4 count 收到负数被拒", mutate(unit="count", value=-3.0)))

    # ── E. 时间序 ──────────────────────────────────────────────────────
    R(_expect_reject("E1 data_vintage 晚于 as_of 被拒",
                     mutate(data_vintage=date(2026, 8, 5))))
    R(_expect_reject("E2 created_at 早于 as_of 被拒（as_of/created_at 填反）",
                     mutate(created_at=datetime.fromisoformat("2026-01-01T00:00:00+08:00"))))
    R(_expect_reject("E3 naive datetime 被拒",
                     mutate(created_at=datetime(2026, 7, 31, 7, 59, 21))))

    # ── F. 用途策略（默认拒绝）─────────────────────────────────────────
    R(("F1 fci_revised 禁止 backtest", not ok_fci.usage_policy.permits("backtest"), ""))
    R(("F2 fci_pit 允许 backtest", pit_fci.usage_policy.permits("backtest"), ""))
    R(_expect_reject("F3 消费 revised 做 Brier 抛 UsageViolation",
                     lambda: ok_fci.assert_usable_for(Purpose.BRIER), "禁止用途"))
    R(_expect_accept("F4 消费 revised 做 dashboard 通过",
                     lambda: ok_fci.assert_usable_for(Purpose.DASHBOARD)))
    R(_expect_reject("F5 未列出的用途默认拒绝（sim_trigger）",
                     lambda: ok_fci.assert_usable_for(Purpose.SIM_TRIGGER), "默认拒绝"))
    R(_expect_reject("F6 allow 与 deny 交叉被拒", lambda: UsagePolicy(
        allow={Purpose.BRIER}, deny={Purpose.BRIER}, note="自相矛盾的策略")))
    R(_expect_reject("F7 status=ok 但 allow 为空（死数据）被拒", mutate(
        usage_policy=UsagePolicy(allow=frozenset(), deny=frozenset(),
                                 note="没有任何合法消费方"))))
    R(_expect_reject("F8 缺口点带 allow 被拒", mutate(
        status="missing", value=None, status_reason="上游断档超过 ffill limit")))
    R(_expect_reject("F9 degraded 点不得被 sim_trigger 消费", lambda: missing_point(
        indicator_key="fci_revised", as_of=date(2026, 7, 30), horizon="nowcast",
        unit=Unit.ZSCORE, source="fred_history", data_vintage=date(2026, 7, 24),
        model_ver="fci-1.1", created_at=_RUN_AT, status=ValueStatus.DEGRADED,
        reason="G3 覆盖率闸未过：可用成分 3/5").assert_usable_for(Purpose.SIM_TRIGGER)))

    # ── G. 溯源与身份 ──────────────────────────────────────────────────
    R(_expect_reject("G1 status=ok 但 inputs 为空被拒", mutate(inputs=())))
    R(_expect_reject("G2 inputs 重复项被拒", mutate(inputs=("T10Y3M", "T10Y3M"))))
    R(_expect_reject("G3 indicator_key 非 snake_case 被拒", mutate(indicator_key="FCI-Revised")))
    R(_expect_reject("G4 horizon 非法被拒", mutate(horizon="12m")))
    R(_expect_accept("G5 horizon=12M 合法", mutate(horizon="12M")))
    R(("G6 identity_key 与 §6.2 UNIQUE 五元组一致",
       ok_fci.identity_key() == ("fci_revised", date(2026, 7, 30), "nowcast",
                                 "fci-1.1", date(2026, 7, 24)), ""))
    R(_expect_reject("G7 信封内 identity_key 重复被拒", lambda: IndicatorEnvelope(
        schema_version=CONTRACT_VERSION, producer="compute_fci.py",
        generated_at=_RUN_AT, points=(ok_fci, ok_fci))))
    R(_expect_reject("G8 信封与点的 schema_version 不一致被拒",
                     lambda: IndicatorEnvelope.model_validate(
                         {**example_envelope().model_dump(mode="json"),
                          "schema_version": "1.0",
                          "points": [{**ok_fci.model_dump(mode="json"),
                                      "schema_version": "9.9"}]})))
    R(_expect_reject("G9 空信封被拒", lambda: IndicatorEnvelope(
        schema_version=CONTRACT_VERSION, producer="compute_fci.py",
        generated_at=_RUN_AT, points=())))

    # ── H. 置信区间 ────────────────────────────────────────────────────
    R(_expect_reject("H1 ci 单边出现被拒", mutate(ci_low=-1.2)))
    R(_expect_reject("H2 value 落在 ci 之外被拒", mutate(ci_low=0.1, ci_high=0.5)))
    R(_expect_accept("H3 合法 ci 通过", mutate(ci_low=-1.5, ci_high=-0.4)))

    # ── I. 序列化 / 往返 / 兼容 ────────────────────────────────────────
    env = example_envelope()
    R(_expect_accept("I1 信封 JSON 往返一致", lambda: (
        IndicatorEnvelope.model_validate_json(env.model_dump_json()) == env
    ) or (_ for _ in ()).throw(AssertionError("往返不等"))))
    R(_expect_accept("I2 落盘 JSON 严格合法（allow_nan=False）",
                     lambda: json.dumps(env.model_dump(mode="json"), allow_nan=False)))
    R(("I3 legacy FCI 记录被正确归一",
       normalize_legacy_fci({"schema_version": "fci-1.1"})
       == {"schema_version": "0", "model_ver": "fci-1.1", "_legacy": True}, ""))
    R(("I4 新记录不被 legacy 归一误伤",
       normalize_legacy_fci({"schema_version": "1.0", "model_ver": "fci-1.1"})
       == {"schema_version": "1.0", "model_ver": "fci-1.1"}, ""))
    R(_expect_accept("I5 probit 契约实例可构造", example_probit_point))
    R(("I6 probit 概率 = 15.01%",
       abs(example_probit_point().value - 0.1501) < 5e-5, ""))
    R(_expect_accept("I7 to_row() 可落 §6.2 宽表", ok_fci.to_row))
    R(("I8 frozen：构造后不可就地改",
       _expect_reject("_", lambda: setattr(ok_fci, "value", 0.0))[1], ""))

    # ── 汇总 ────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, why in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  << {why}" if why else ""))
    print(f"\n=== contracts.py selftest: {passed}/{total} PASS ===")
    return 0 if passed == total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="I1 指标契约（IndicatorPoint）")
    ap.add_argument("--selftest", action="store_true", help="跑 QA 断言用例")
    ap.add_argument("--demo", action="store_true", help="打印契约实例 JSON")
    args = ap.parse_args()
    if args.demo:
        print("── FCI 信封（套用契约后）" + "─" * 40)
        print(example_envelope().model_dump_json(indent=2))
        print("\n── probit 指标点" + "─" * 46)
        print(example_probit_point().model_dump_json(indent=2))
        return 0
    if args.selftest:
        return run_selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
