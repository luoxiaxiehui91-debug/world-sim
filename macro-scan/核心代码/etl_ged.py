#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""etl_ged.py — UCDP GED v26.1 离线 ETL（标准化 + 聚合 + 三道质量闸门）

设计文档：design/a2_ged_etl_design.md
schema_version: ged-etl-1.0 / dataset_version: UCDP GED v26.1

职责
----
把 UCDP GED 年度冻结快照 CSV（417,968 事件 × 49 列，1989–2025，约 262 MB）
标准化为不可变记录，过三道质量闸门，聚合成两张小表供上层（天玑校验 / B 基线回测）消费。

红线（worldsim-review-synthesis.md §7.5 + 架构 Round2-3）
------------------------------------------------------
1. 解析必须用 csv 模块（source_headline/article 内嵌换行与逗号），**绝不 split(',')**。
2. 记录数以累加计数为准，**绝不 wc -l**。
3. low<=best<=high 违规 clamp 必须带计数器；比例 > 2% → 失败退出，**绝不静默 clamp**。
4. 产物必带 snapshot_year / frozen / as_of / dataset_version。
5. 年度冻结快照**禁作当前信号**；被日更 scan 路径读取即 fail-loud。
6. 月度聚合限 date_prec <= 3，排除比例写入报告。
7. 幂等全量重跑，不做增量 diff。
8. 原始 CSV 不进服务进程，线上只读聚合产物。

隔离性
------
纯新文件。不 import 也不修改 scheduler.py / fetcher_base.py 等核心文件。
optim_config 为**可选**依赖（缺失时回退到环境变量），保证脱离部署树也能独立运行。

用法
----
    python etl_ged.py --ged-csv /path/to/GEDEvent_v26_1.csv \\
                      --data-dir S:/macro-scan/data
    python etl_ged.py --dry-run          # 只跑闸门，不写产物
    python etl_ged.py --limit 50000      # 抽样自测

退出码
------
    0  全部闸门通过，产物已写
    2  闸门失败（不写任何产物）—— 与 compute_fci.py G3 同约定
    3  输入不可用 / 冻结守卫触发
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# 常量与阈值
# --------------------------------------------------------------------------- #

SCHEMA_VERSION: str = "ged-etl-1.0"
DATASET_VERSION: str = "v26.1"
OUTPUT_SUBDIR: str = "ged"

EXIT_OK: int = 0
EXIT_GATE_FAILED: int = 2
EXIT_INPUT_ERROR: int = 3

STATUS_PASS: str = "PASS"
STATUS_WARN: str = "WARN"
STATUS_FAIL: str = "FAIL"
STATUS_INAPPLICABLE: str = "INAPPLICABLE"

# --- 闸门 A ---------------------------------------------------------------- #
REQUIRED_FIELDS: Tuple[str, ...] = (
    "id", "year", "country", "country_id", "region", "type_of_violence",
    "date_start", "date_end", "date_prec", "best", "low", "high",
)
QUARANTINE_FAIL_RATIO: float = 0.005          # 0.5%，实测基线 0.000%
NUMBER_OF_SOURCES_SENTINEL: int = -1          # 实测 97,496 行 (23.33%) 是哨兵不是计数

# --- 闸门 B ---------------------------------------------------------------- #
CLAMP_FAIL_RATIO: float = 0.02                # §7.5 指定 2%，实测基线 1.2142%
DEATHS_IDENTITY_FAIL_RATIO: float = 0.001     # 实测基线 0.000%（硬不变量）
VALID_TYPE_OF_VIOLENCE: frozenset = frozenset({1, 2, 3})
VALID_DATE_PREC: frozenset = frozenset({1, 2, 3, 4, 5})
VALID_WHERE_PREC: frozenset = frozenset({1, 2, 3, 4, 5, 6, 7})
MIN_YEAR: int = 1989
MONTHLY_MAX_DATE_PREC: int = 3                # §7.5：月度聚合限 date_prec <= 3

# --- 闸门 C ---------------------------------------------------------------- #
GATE_C_MIN_OVERLAP_MONTHS: int = 24
GATE_C_BASELINE_RHO: float = 0.1099           # 实测校准，非拍脑袋（见设计文档 §4.3）
GATE_C_DRIFT_BAND: float = 0.10
GPR_GLOBAL_SERIES: str = "GPR"
# GPR 仅覆盖 4 国，而 GED 在这 4 国事件量为 USA=33 / CHN=39 / TWN=0 / RUS=5157
# → 国家级配对统计上无效，显式关闭并把理由写进报告，防后人"好心"重开。
GATE_C_COUNTRY_LEVEL_ENABLED: bool = False
GATE_C_COUNTRY_LEVEL_REASON: str = (
    "GPR covers USA/CHN/TWN/RUS only; GED event counts are 33/39/0/5157 over 37 years "
    "-> 3 of 4 pairs statistically void. Global monthly comparison used instead."
)

# --- 冻结守卫 -------------------------------------------------------------- #
ALLOWED_CONSUMERS: frozenset = frozenset({"backtest", "baseline", "calibration"})
FORBIDDEN_CONSUMERS: frozenset = frozenset(
    {"daily_scan", "grv", "sim_trigger", "dashboard", "nowcast"}
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [etl_ged] %(message)s",
)
log = logging.getLogger("etl_ged")


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #

class GedEtlError(RuntimeError):
    """ETL 基础异常。"""


class FrozenSnapshotViolation(GedEtlError):
    """冻结快照被当作当前信号使用，或快照本身出现当年数据。"""


class GateFailure(GedEtlError):
    """质量闸门失败。"""


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GedEventRecord:
    """标准化后的单条 GED 事件（不可变）。

    质量标记（clamped_* / geo_missing / source_sentinel）随记录一路带到聚合层，
    使聚合表能回答"这一格里有多少行被修过"，而不是只给一个全局数字。

    待 I1 Pydantic 契约定稿后改为继承 I1 基类（走 expand 不走重写）。
    """

    event_id: int
    relid: str
    year: int
    date_start: str          # ISO YYYY-MM-DD（已截取前 10 位）
    date_end: str
    date_prec: int
    year_month: str          # date_start[:7]
    cross_month: bool
    country: str
    country_id: int
    region: str
    adm_1: Optional[str]
    where_prec: int
    latitude: Optional[float]
    longitude: Optional[float]
    geo_missing: bool
    type_of_violence: int
    conflict_new_id: int
    conflict_name: str
    side_a: str
    side_b: str
    deaths_best: int
    deaths_low: int          # clamp 后
    deaths_high: int         # clamp 后
    deaths_a: int
    deaths_b: int
    deaths_civilians: int
    deaths_unknown: int
    clamped_low: bool
    clamped_high: bool
    number_of_sources: Optional[int]
    source_sentinel: bool


@dataclass
class GateResult:
    """单个闸门的判定结果。"""

    name: str
    status: str = STATUS_PASS
    detail: Dict[str, object] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status == STATUS_FAIL

    def to_dict(self) -> Dict[str, object]:
        out: Dict[str, object] = {"status": self.status}
        out.update(self.detail)
        return out


@dataclass
class AggCell:
    """一个聚合格子的累加器。"""

    events: int = 0
    deaths_best: int = 0
    deaths_low: int = 0
    deaths_high: int = 0
    deaths_a: int = 0
    deaths_b: int = 0
    deaths_civilians: int = 0
    deaths_unknown: int = 0
    events_geolocated: int = 0
    clamped_rows: int = 0
    source_sentinel_rows: int = 0
    date_prec_1_3: int = 0
    date_prec_4_5: int = 0
    cross_month_rows: int = 0

    def add(self, rec: GedEventRecord) -> None:
        """累加一条记录。"""
        self.events += 1
        self.deaths_best += rec.deaths_best
        self.deaths_low += rec.deaths_low
        self.deaths_high += rec.deaths_high
        self.deaths_a += rec.deaths_a
        self.deaths_b += rec.deaths_b
        self.deaths_civilians += rec.deaths_civilians
        self.deaths_unknown += rec.deaths_unknown
        if not rec.geo_missing:
            self.events_geolocated += 1
        if rec.clamped_low or rec.clamped_high:
            self.clamped_rows += 1
        if rec.source_sentinel:
            self.source_sentinel_rows += 1
        if rec.date_prec <= MONTHLY_MAX_DATE_PREC:
            self.date_prec_1_3 += 1
        else:
            self.date_prec_4_5 += 1
        if rec.cross_month:
            self.cross_month_rows += 1


# --------------------------------------------------------------------------- #
# 解析工具
# --------------------------------------------------------------------------- #

def _s(raw: Dict[str, str], key: str) -> str:
    """安全取字符串并 strip；None 视为空串。"""
    value = raw.get(key)
    return value.strip() if isinstance(value, str) else ""


def _to_int(raw: Dict[str, str], key: str) -> Optional[int]:
    """转 int；空串或不可解析返回 None。**绝不返回 0 兜底**。"""
    text = _s(raw, key)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            # UCDP 偶有 "3.0" 形态的整数
            as_float = float(text)
        except ValueError:
            return None
        if as_float.is_integer():
            return int(as_float)
        return None


def _to_float(raw: Dict[str, str], key: str) -> Optional[float]:
    """转 float；空串或不可解析返回 None。"""
    text = _s(raw, key)
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _iso_date(raw: Dict[str, str], key: str) -> str:
    """取 ISO 日期前 10 位。

    GED 的 date_start 形如 '1992-03-17 00:00:00.000'，必须截断，
    不能整串丢给日期解析器。
    """
    text = _s(raw, key)
    if len(text) < 10:
        return ""
    head = text[:10]
    if head[4] != "-" or head[7] != "-":
        return ""
    return head


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Spearman 秩相关系数（并列取平均秩）。

    不依赖 scipy，保持零新增依赖。样本 < 3 或方差为 0 时返回 None。
    """
    n = len(xs)
    if n != len(ys) or n < 3:
        return None

    def ranks(values: Sequence[float]) -> List[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = avg_rank
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    var_x = sum((a - mx) ** 2 for a in rx)
    var_y = sum((b - my) ** 2 for b in ry)
    if var_x <= 0.0 or var_y <= 0.0:
        return None
    return cov / math.sqrt(var_x * var_y)


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    """计算文件 sha256（供 vintage 追溯与幂等校验）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# 冻结快照守卫（供下游消费方 import）
# --------------------------------------------------------------------------- #

def assert_backtest_only(consumer: str) -> None:
    """消费侧守卫：GED 聚合产物只允许回测/基线/校准场景读取。

    §7.5 + 架构 Round2-3 硬闸门：年度冻结快照混入当前信号是 point-in-time
    泄漏的镜像错误（拿陈旧数据冒充实时），比缺数据更危险。

    Args:
        consumer: 消费场景标识，如 'backtest' / 'daily_scan'。

    Raises:
        FrozenSnapshotViolation: consumer 不在白名单内。
    """
    key = (consumer or "").strip().lower()
    if key in ALLOWED_CONSUMERS:
        return
    hint = "（该场景在禁用名单内）" if key in FORBIDDEN_CONSUMERS else "（未知场景，默认拒绝）"
    raise FrozenSnapshotViolation(
        f"GED v{DATASET_VERSION} 是年度冻结快照（snapshot_year=2025），"
        f"禁止被 consumer='{consumer}' 读取{hint}。"
        f"允许的场景：{sorted(ALLOWED_CONSUMERS)}。"
    )


def load_ged_aggregate(data_dir: str, consumer: str, granularity: str = "year") -> List[Dict[str, str]]:
    """读取 GED 聚合产物（**唯一推荐的下游入口**）。

    强制经过 assert_backtest_only，避免下游绕过守卫直接读 CSV。

    Args:
        data_dir: macro-scan 的 data 目录。
        consumer: 消费场景标识，见 assert_backtest_only。
        granularity: 'year' 或 'month'。

    Returns:
        聚合行的 dict 列表。

    Raises:
        FrozenSnapshotViolation: consumer 非法。
        GedEtlError: granularity 非法或产物缺失。
    """
    assert_backtest_only(consumer)
    if granularity not in ("year", "month"):
        raise GedEtlError(f"granularity 必须是 'year' 或 'month'，收到 {granularity!r}")
    path = os.path.join(data_dir, OUTPUT_SUBDIR, f"ged_agg_country_{granularity}.csv")
    if not os.path.isfile(path):
        raise GedEtlError(f"GED 聚合产物不存在：{path}（请先跑一次 etl_ged.py）")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #

def resolve_data_dir(cli_value: Optional[str]) -> str:
    """定位 data 目录。

    优先级：CLI > 环境变量 GED_DATA_DIR > optim_config.DATA_DIR
            > OPENCLAW_WORKSPACE/data > 脚本上级/data
    optim_config 为可选依赖，缺失时不报错（保证脱离部署树可独立运行）。
    """
    if cli_value:
        return os.path.abspath(cli_value)
    env_dir = os.environ.get("GED_DATA_DIR")
    if env_dir:
        return os.path.abspath(env_dir)
    try:
        from optim_config import DATA_DIR  # type: ignore
        return os.path.abspath(str(DATA_DIR))
    except Exception:
        workspace = os.environ.get(
            "OPENCLAW_WORKSPACE",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        return os.path.abspath(os.path.join(workspace, "data"))


def resolve_ged_csv(cli_value: Optional[str], data_dir: str) -> str:
    """定位 GED 原始 CSV。

    Raises:
        GedEtlError: 所有候选路径均不存在。
    """
    candidates: List[str] = []
    if cli_value:
        candidates.append(cli_value)
    env_path = os.environ.get("GED_CSV_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.extend([
        os.path.join(data_dir, "ged_raw", f"GEDEvent_{DATASET_VERSION.replace('.', '_')}.csv"),
        os.path.join(data_dir, "GEDEvent_v26_1.csv"),
        # 可由 GED_CSV_PATH 覆盖（空串会被 os.path.isfile 跳过）
        os.environ.get("GED_CSV_PATH", ""),
    ])
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    raise GedEtlError(
        "找不到 GED 原始 CSV。请用 --ged-csv 指定，或设置 GED_CSV_PATH。"
        f" 已尝试：{candidates}"
    )


# --------------------------------------------------------------------------- #
# ETL 主体
# --------------------------------------------------------------------------- #

class GedEtl:
    """UCDP GED 离线 ETL 管道。

    生命周期：run() -> 流式标准化(闸门A/B) -> 终判 -> 聚合 -> 闸门C -> 落盘。
    幂等：无内部状态依赖，全量重跑结果一致。
    """

    def __init__(
        self,
        ged_csv: str,
        data_dir: str,
        dry_run: bool = False,
        limit: Optional[int] = None,
    ) -> None:
        self.ged_csv: str = ged_csv
        self.data_dir: str = data_dir
        self.out_dir: str = os.path.join(data_dir, OUTPUT_SUBDIR)
        self.dry_run: bool = dry_run
        self.limit: Optional[int] = limit

        # 计数器
        self.total_rows: int = 0
        self.accepted: int = 0
        self.quarantined: int = 0
        self.quarantine_reasons: Counter = Counter()
        self.quarantine_samples: List[Dict[str, str]] = []
        self.clamp_low_cnt: int = 0
        self.clamp_high_cnt: int = 0
        self.clamp_both_cnt: int = 0
        self.clamp_rows: int = 0
        self.deaths_identity_mismatch: int = 0
        self.sentinel_sources: int = 0
        self.geo_missing_cnt: int = 0
        self.cross_month_events: int = 0
        self.cross_year_events: int = 0
        self.date_prec_dist: Counter = Counter()
        self.snapshot_year: int = 0

        # 聚合容器
        self.agg_year: Dict[Tuple[str, int, int], AggCell] = defaultdict(AggCell)
        self.agg_month: Dict[Tuple[str, str, int], AggCell] = defaultdict(AggCell)
        self.country_meta: Dict[str, Tuple[int, str]] = {}
        self.global_month_deaths: Counter = Counter()

        self.gates: Dict[str, GateResult] = {}

    # ---------------------------------------------------------------- #
    # 入口
    # ---------------------------------------------------------------- #

    def run(self) -> int:
        """执行完整 ETL，返回进程退出码。"""
        log.info("GED ETL 启动 | csv=%s", self.ged_csv)
        log.info("输出目录 = %s | dry_run=%s", self.out_dir, self.dry_run)

        self._stream_and_normalize()

        if self.total_rows == 0:
            log.error("CSV 无数据行，中止")
            return EXIT_INPUT_ERROR

        self._assert_frozen_snapshot()

        gate_a = self._gate_a_completeness()
        gate_b = self._gate_b_range()
        self.gates["A_completeness"] = gate_a
        self.gates["B_range"] = gate_b

        if gate_a.failed or gate_b.failed:
            log.error("闸门 A/B 失败 → 不写任何产物（exit %d）", EXIT_GATE_FAILED)
            self._log_gate(gate_a)
            self._log_gate(gate_b)
            return EXIT_GATE_FAILED

        gate_c = self._gate_c_cross_source()
        self.gates["C_cross_source"] = gate_c

        for gate in (gate_a, gate_b, gate_c):
            self._log_gate(gate)

        if gate_c.failed:
            log.error("闸门 C 失败（跨源符号翻转/接线错）→ 不写产物（exit %d）", EXIT_GATE_FAILED)
            return EXIT_GATE_FAILED

        if self.dry_run:
            log.info("dry-run：闸门全过，跳过落盘")
            return EXIT_OK

        self._write_outputs()
        log.info("GED ETL 完成 ✅")
        return EXIT_OK

    # ---------------------------------------------------------------- #
    # 步骤 1：流式标准化（内嵌闸门 A / B 的逐行判定）
    # ---------------------------------------------------------------- #

    def _stream_and_normalize(self) -> None:
        """流式扫描 CSV 并标准化。

        必须用 csv 模块 + newline=''：source_headline / source_article
        内嵌换行与逗号，split(',') 会把一条事件拆成多条垃圾。
        记录数以累加计数为准，不用 wc -l。
        """
        # 单字段可能很长（source_article 全文），放宽上限
        csv.field_size_limit(1 << 30)

        with open(self.ged_csv, "r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise GedEtlError("CSV 无表头")
            missing = [c for c in REQUIRED_FIELDS if c not in reader.fieldnames]
            if missing:
                raise GedEtlError(f"CSV 缺少必需列：{missing}（真实列名核对：date_prec 非 date_precision）")
            log.info("表头列数 = %d", len(reader.fieldnames))

            for raw in reader:
                self.total_rows += 1
                if self.limit is not None and self.total_rows > self.limit:
                    self.total_rows -= 1
                    break

                record, reason = self._normalize_event(raw)
                if record is None:
                    self.quarantined += 1
                    self.quarantine_reasons[reason or "unknown"] += 1
                    if len(self.quarantine_samples) < 50:
                        self.quarantine_samples.append(
                            {"id": _s(raw, "id"), "reason": reason or "unknown"}
                        )
                    continue

                self.accepted += 1
                self._accumulate(record)

                if self.total_rows % 100_000 == 0:
                    log.info("已处理 %d 行…", self.total_rows)

        log.info("扫描完成：总行 %d / 接受 %d / 隔离 %d", self.total_rows, self.accepted, self.quarantined)

    def _normalize_event(self, raw: Dict[str, str]) -> Tuple[Optional[GedEventRecord], Optional[str]]:
        """把一行原始 dict 标准化为 GedEventRecord。

        Returns:
            (record, None) 成功；(None, reason) 被隔离。
        """
        # ---- 闸门 A：必填字段 ----
        event_id = _to_int(raw, "id")
        year = _to_int(raw, "year")
        country = _s(raw, "country")
        country_id = _to_int(raw, "country_id")
        region = _s(raw, "region")
        tov = _to_int(raw, "type_of_violence")
        date_start = _iso_date(raw, "date_start")
        date_end = _iso_date(raw, "date_end")
        date_prec = _to_int(raw, "date_prec")
        best = _to_int(raw, "best")
        low = _to_int(raw, "low")
        high = _to_int(raw, "high")

        for name, value in (
            ("id", event_id), ("year", year), ("country_id", country_id),
            ("type_of_violence", tov), ("date_prec", date_prec),
            ("best", best), ("low", low), ("high", high),
        ):
            if value is None:
                return None, f"A_missing:{name}"
        if not country:
            return None, "A_missing:country"
        if not region:
            return None, "A_missing:region"
        if not date_start:
            return None, "A_missing:date_start"
        if not date_end:
            return None, "A_missing:date_end"

        # 供类型检查器收窄（上面已逐一排除 None）
        assert event_id is not None and year is not None and country_id is not None
        assert tov is not None and date_prec is not None
        assert best is not None and low is not None and high is not None

        deaths_a = _to_int(raw, "deaths_a")
        deaths_b = _to_int(raw, "deaths_b")
        deaths_civ = _to_int(raw, "deaths_civilians")
        deaths_unk = _to_int(raw, "deaths_unknown")
        for name, value in (
            ("deaths_a", deaths_a), ("deaths_b", deaths_b),
            ("deaths_civilians", deaths_civ), ("deaths_unknown", deaths_unk),
        ):
            if value is None:
                return None, f"A_missing:{name}"
        assert deaths_a is not None and deaths_b is not None
        assert deaths_civ is not None and deaths_unk is not None

        # ---- 闸门 B：取值范围 ----
        if not (MIN_YEAR <= year <= datetime.now(timezone.utc).year):
            return None, "B1_year_out_of_range"
        if tov not in VALID_TYPE_OF_VIOLENCE:
            return None, "B2_bad_type_of_violence"
        if date_prec not in VALID_DATE_PREC:
            return None, "B3_bad_date_prec"

        where_prec = _to_int(raw, "where_prec")
        if where_prec is None or where_prec not in VALID_WHERE_PREC:
            return None, "B3_bad_where_prec"

        if min(best, low, high, deaths_a, deaths_b, deaths_civ, deaths_unk) < 0:
            return None, "B4_negative_deaths"

        # B7 硬不变量：实测 417,968 行 0 例外。列错位/编码损坏会立刻打破它。
        if deaths_a + deaths_b + deaths_civ + deaths_unk != best:
            self.deaths_identity_mismatch += 1
            return None, "B7_deaths_identity_broken"

        # B6 区间自洽：clamp + 计数，绝不静默
        clamped_low = low > best
        clamped_high = high < best
        if clamped_low:
            low = best
            self.clamp_low_cnt += 1
        if clamped_high:
            high = best
            self.clamp_high_cnt += 1
        if clamped_low and clamped_high:
            self.clamp_both_cnt += 1
        if clamped_low or clamped_high:
            self.clamp_rows += 1

        # B5 经纬度：越界或 (0,0) 视为缺失，不隔离
        latitude = _to_float(raw, "latitude")
        longitude = _to_float(raw, "longitude")
        geo_missing = False
        if latitude is None or longitude is None:
            geo_missing = True
        elif not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            geo_missing = True
        elif latitude == 0.0 and longitude == 0.0:
            geo_missing = True
        if geo_missing:
            latitude, longitude = None, None
            self.geo_missing_cnt += 1

        # number_of_sources == -1 是缺失哨兵（实测 23.33%），不是计数
        raw_sources = _to_int(raw, "number_of_sources")
        source_sentinel = raw_sources is not None and raw_sources == NUMBER_OF_SOURCES_SENTINEL
        number_of_sources: Optional[int] = None
        if raw_sources is not None and raw_sources >= 0:
            number_of_sources = raw_sources
        if source_sentinel:
            self.sentinel_sources += 1

        cross_month = date_start[:7] != date_end[:7]
        cross_year = date_start[:4] != date_end[:4]
        if cross_month:
            self.cross_month_events += 1
        if cross_year:
            # 实测 v26.1 为 0 行。v27 若出现，必须显式暴露而非沿用旧规则静默处理。
            self.cross_year_events += 1

        self.date_prec_dist[date_prec] += 1
        self.snapshot_year = max(self.snapshot_year, year)

        return GedEventRecord(
            event_id=event_id,
            relid=_s(raw, "relid"),
            year=year,
            date_start=date_start,
            date_end=date_end,
            date_prec=date_prec,
            year_month=date_start[:7],
            cross_month=cross_month,
            country=country,
            country_id=country_id,
            region=region,
            adm_1=_s(raw, "adm_1") or None,
            where_prec=where_prec,
            latitude=latitude,
            longitude=longitude,
            geo_missing=geo_missing,
            type_of_violence=tov,
            conflict_new_id=_to_int(raw, "conflict_new_id") or 0,
            conflict_name=_s(raw, "conflict_name"),
            side_a=_s(raw, "side_a"),
            side_b=_s(raw, "side_b"),
            deaths_best=best,
            deaths_low=low,
            deaths_high=high,
            deaths_a=deaths_a,
            deaths_b=deaths_b,
            deaths_civilians=deaths_civ,
            deaths_unknown=deaths_unk,
            clamped_low=clamped_low,
            clamped_high=clamped_high,
            number_of_sources=number_of_sources,
            source_sentinel=source_sentinel,
        ), None

    def _accumulate(self, rec: GedEventRecord) -> None:
        """把标准化记录累加进两张聚合表。

        时间归属口径：一律按 date_start（跨月事件全额计入起始月，不按日摊分）。
        月度表仅收 date_prec <= 3（§7.5）。
        """
        self.country_meta[rec.country] = (rec.country_id, rec.region)

        self.agg_year[(rec.country, rec.year, rec.type_of_violence)].add(rec)

        if rec.date_prec <= MONTHLY_MAX_DATE_PREC:
            self.agg_month[(rec.country, rec.year_month, rec.type_of_violence)].add(rec)
            self.global_month_deaths[rec.year_month] += rec.deaths_best

    # ---------------------------------------------------------------- #
    # 步骤 2：冻结守卫
    # ---------------------------------------------------------------- #

    def _assert_frozen_snapshot(self) -> None:
        """断言快照确实是"过去年份的冻结物"。

        Raises:
            FrozenSnapshotViolation: 出现当年或未来年份数据。
        """
        current_year = datetime.now(timezone.utc).year
        if self.snapshot_year >= current_year:
            raise FrozenSnapshotViolation(
                f"GED 快照 max(year)={self.snapshot_year} >= 当前年 {current_year}。"
                "该文件疑似被替换为准实时源；冻结快照语义已破坏，拒绝继续。"
            )
        log.info("冻结守卫通过：snapshot_year=%d < 当前年 %d", self.snapshot_year, current_year)

    # ---------------------------------------------------------------- #
    # 步骤 3：闸门终判
    # ---------------------------------------------------------------- #

    def _gate_a_completeness(self) -> GateResult:
        """闸门 A · 缺失值闸门终判。"""
        ratio = self.quarantined / self.total_rows if self.total_rows else 0.0
        status = STATUS_FAIL if ratio > QUARANTINE_FAIL_RATIO else STATUS_PASS
        return GateResult(
            name="A_completeness",
            status=status,
            detail={
                "quarantined": self.quarantined,
                "ratio": round(ratio, 6),
                "threshold": QUARANTINE_FAIL_RATIO,
                "reasons": dict(self.quarantine_reasons),
                "samples": self.quarantine_samples,
                "sentinel_number_of_sources": self.sentinel_sources,
                "geo_missing": self.geo_missing_cnt,
                "note": "number_of_sources==-1 是缺失哨兵（实测 23.33%），映射为 None，不计缺失、不参与任何数值聚合",
            },
        )

    def _gate_b_range(self) -> GateResult:
        """闸门 B · 取值范围闸门终判（含 clamp 比例与死亡恒等式）。"""
        clamp_ratio = self.clamp_rows / self.total_rows if self.total_rows else 0.0
        ident_ratio = self.deaths_identity_mismatch / self.total_rows if self.total_rows else 0.0

        status = STATUS_PASS
        if clamp_ratio > CLAMP_FAIL_RATIO:
            status = STATUS_FAIL
        if ident_ratio > DEATHS_IDENTITY_FAIL_RATIO:
            status = STATUS_FAIL

        return GateResult(
            name="B_range",
            status=status,
            detail={
                # 四个数分开输出：1419 + 3691 = 5110 != 5075，差额 35 是同时违反两条的行
                "clamp_low_cnt": self.clamp_low_cnt,
                "clamp_high_cnt": self.clamp_high_cnt,
                "clamp_both_cnt": self.clamp_both_cnt,
                "clamp_rows": self.clamp_rows,
                "clamp_ratio": round(clamp_ratio, 6),
                "clamp_threshold": CLAMP_FAIL_RATIO,
                "clamp_headroom_pp": round((CLAMP_FAIL_RATIO - clamp_ratio) * 100, 4),
                "deaths_identity_mismatch": self.deaths_identity_mismatch,
                "deaths_identity_ratio": round(ident_ratio, 6),
                "deaths_identity_threshold": DEATHS_IDENTITY_FAIL_RATIO,
                "date_prec_dist": {str(k): v for k, v in sorted(self.date_prec_dist.items())},
                "note": "clamp 规则 low>best->low=best, high<best->high=best；绝不静默，每次运行输出计数",
            },
        )

    def _gate_c_cross_source(self) -> GateResult:
        """闸门 C · 跨源一致性闸门。

        设计要点：先判**对照源可用性**，再判一致性。
        「无数据可比」必须返回 INAPPLICABLE，**绝不能返回 PASS**
        —— 那是静默降级病族在质量闸层的复发形态。
        """
        partners: Dict[str, Dict[str, object]] = {}
        statuses: List[str] = []

        gpr_result = self._check_partner_gpr()
        partners["GPR"] = gpr_result
        statuses.append(str(gpr_result["status"]))

        gdelt_result = self._check_partner_gdelt()
        partners["GDELT"] = gdelt_result
        statuses.append(str(gdelt_result["status"]))

        self._assert_not_fake_pass(partners)

        if STATUS_FAIL in statuses:
            overall = STATUS_FAIL
        elif STATUS_WARN in statuses:
            overall = STATUS_WARN
        elif STATUS_PASS in statuses:
            overall = STATUS_PASS
        else:
            # 所有对照源都不可用 → 整体不可判定，而非通过
            overall = STATUS_INAPPLICABLE

        return GateResult(
            name="C_cross_source",
            status=overall,
            detail={
                "partners": partners,
                "country_level": {
                    "enabled": GATE_C_COUNTRY_LEVEL_ENABLED,
                    "reason": GATE_C_COUNTRY_LEVEL_REASON,
                },
                "scope_note": (
                    "本闸门检测接线错误（符号翻转/时间轴错位/单位错配），非科学验证。"
                    "rho≈0.11 不可解读为『GPR 验证了 GED』；目标 #10 权威口径仍是 GED 年度认证。"
                ),
            },
        )

    def _check_partner_gpr(self) -> Dict[str, object]:
        """GED 全球月度死亡数 vs GPR 全球月度指数的秩相关。"""
        gpr_path = os.path.join(self.data_dir, "fred_history", f"{GPR_GLOBAL_SERIES}.csv")
        if not os.path.isfile(gpr_path):
            return {
                "status": STATUS_INAPPLICABLE,
                "reason": f"GPR series not found at {gpr_path}",
                "overlap_months": 0,
            }

        gpr_monthly: Dict[str, float] = {}
        with open(gpr_path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                date_text = (row.get("date") or "").strip()
                value_text = (row.get("value") or "").strip()
                if len(date_text) < 7 or not value_text:
                    continue
                try:
                    gpr_monthly[date_text[:7]] = float(value_text)
                except ValueError:
                    continue

        common = sorted(set(self.global_month_deaths) & set(gpr_monthly))
        overlap = len(common)
        if overlap < GATE_C_MIN_OVERLAP_MONTHS:
            return {
                "status": STATUS_INAPPLICABLE,
                "reason": f"overlap {overlap} months < required {GATE_C_MIN_OVERLAP_MONTHS}",
                "overlap_months": overlap,
            }

        xs = [float(self.global_month_deaths[m]) for m in common]
        ys = [gpr_monthly[m] for m in common]
        rho = spearman(xs, ys)
        if rho is None:
            return {
                "status": STATUS_INAPPLICABLE,
                "reason": "degenerate series (zero variance)",
                "overlap_months": overlap,
            }

        drift = abs(rho - GATE_C_BASELINE_RHO)
        if rho <= 0.0:
            status = STATUS_FAIL       # 符号翻转 = 接线错 / 时间轴错位
        elif drift > GATE_C_DRIFT_BAND:
            status = STATUS_WARN       # 某一源口径变了
        else:
            status = STATUS_PASS

        return {
            "status": status,
            "granularity": "global_monthly",
            "overlap_months": overlap,
            "window": f"{common[0]}..{common[-1]}",
            "spearman_rho": round(rho, 4),
            "baseline_rho": GATE_C_BASELINE_RHO,
            "drift": round(drift, 4),
            "drift_band": GATE_C_DRIFT_BAND,
        }

    def _check_partner_gdelt(self) -> Dict[str, object]:
        """GDELT 对照可用性检查。

        实测：GED 止于 2025-12-31，GDELT 本地历史始于 2026-05-21 → 重叠 0 天。
        故当前**必然** INAPPLICABLE。待 GDELT 攒满 24 个月后自动转 ENABLED，无需改码。
        """
        path = os.path.join(self.data_dir, "gdelt_history.jsonl")
        if not os.path.isfile(path):
            return {
                "status": STATUS_INAPPLICABLE,
                "reason": f"gdelt_history.jsonl not found at {path}",
                "overlap_months": 0,
            }

        months: set = set()
        raw_lines = 0
        unique_dates: set = set()
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                raw_lines += 1
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                date_text = str(payload.get("date") or "")
                if len(date_text) >= 7:
                    unique_dates.add(date_text[:10])
                    months.add(date_text[:7])

        overlap_months = len(months & set(self.global_month_deaths))
        result: Dict[str, object] = {
            "raw_lines": raw_lines,
            "unique_dates": len(unique_dates),
            "dedup_note": "同日重复追加，消费前须按 date 去重取末条",
            "gdelt_range": f"{min(unique_dates)}..{max(unique_dates)}" if unique_dates else "empty",
            "overlap_months": overlap_months,
        }

        if overlap_months < GATE_C_MIN_OVERLAP_MONTHS:
            result["status"] = STATUS_INAPPLICABLE
            result["reason"] = (
                f"overlap {overlap_months} months < required {GATE_C_MIN_OVERLAP_MONTHS}. "
                "GED ends 2025-12-31; GDELT local history starts 2026-05-21 -> disjoint. "
                "NOT a pass; will auto-enable once GDELT accumulates enough history."
            )
            return result

        # 重叠足够时才做真正比较（未来 GDELT 攒够历史后自动生效）
        gdelt_monthly: Dict[str, float] = defaultdict(float)
        with open(path, "r", encoding="utf-8") as handle:
            latest_per_date: Dict[str, dict] = {}
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                date_text = str(payload.get("date") or "")
                if len(date_text) >= 10:
                    latest_per_date[date_text[:10]] = payload   # 同日后写覆盖 = 取末条
            for date_text, payload in latest_per_date.items():
                scores = payload.get("scores") or {}
                military = scores.get("military") or {}
                total = sum(float(v) for v in military.values() if isinstance(v, (int, float)))
                gdelt_monthly[date_text[:7]] += total

        common = sorted(set(gdelt_monthly) & set(self.global_month_deaths))
        xs = [float(self.global_month_deaths[m]) for m in common]
        ys = [gdelt_monthly[m] for m in common]
        rho = spearman(xs, ys)
        if rho is None:
            result["status"] = STATUS_INAPPLICABLE
            result["reason"] = "degenerate series"
            return result
        result["spearman_rho"] = round(rho, 4)
        result["granularity"] = "global_monthly_military"
        result["status"] = STATUS_FAIL if rho <= 0.0 else STATUS_PASS
        result["baseline_note"] = "首次转 ENABLED 时人工确认基线后写死"
        return result

    @staticmethod
    def _assert_not_fake_pass(partners: Dict[str, Dict[str, object]]) -> None:
        """守卫：重叠不足的对照源绝不允许标成 PASS。

        Raises:
            GateFailure: 检测到"无数据可比却判通过"的假绿灯。
        """
        for name, info in partners.items():
            overlap = info.get("overlap_months", 0)
            if not isinstance(overlap, int):
                continue
            if overlap < GATE_C_MIN_OVERLAP_MONTHS and info.get("status") == STATUS_PASS:
                raise GateFailure(
                    f"闸门 C 内部一致性错误：对照源 {name} 重叠仅 {overlap} 个月却被标为 PASS。"
                    "『无数据可比 ⇒ 通过』是静默降级，必须是 INAPPLICABLE。"
                )

    @staticmethod
    def _log_gate(gate: GateResult) -> None:
        """打印闸门判定摘要。"""
        icon = {
            STATUS_PASS: "✅", STATUS_WARN: "🟡",
            STATUS_FAIL: "🔴", STATUS_INAPPLICABLE: "⚪",
        }.get(gate.status, "?")
        log.info("%s 闸门 %s = %s", icon, gate.name, gate.status)

    # ---------------------------------------------------------------- #
    # 步骤 4：落盘
    # ---------------------------------------------------------------- #

    def _common_meta(self) -> Dict[str, object]:
        """所有产物共享的溯源元数据。"""
        return {
            "snapshot_year": self.snapshot_year,
            "frozen": "true",
            "dataset_version": DATASET_VERSION,
            "schema_version": SCHEMA_VERSION,
            "as_of": f"{self.snapshot_year}-12-31",
            "data_vintage": DATASET_VERSION,
        }

    def _write_outputs(self) -> None:
        """写四份产物：年度表 / 月度表 / 校验报告 / manifest。"""
        os.makedirs(self.out_dir, exist_ok=True)
        meta = self._common_meta()

        year_path = os.path.join(self.out_dir, "ged_agg_country_year.csv")
        month_path = os.path.join(self.out_dir, "ged_agg_country_month.csv")
        report_path = os.path.join(self.out_dir, "ged_etl_report.json")
        manifest_path = os.path.join(self.out_dir, "ged_manifest.json")

        self._write_year_table(year_path, meta)
        self._write_month_table(month_path, meta)
        report = self._build_report()
        self._write_json(report_path, report)

        manifest = {
            "dataset_version": DATASET_VERSION,
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "path": self.ged_csv,
                "size_bytes": os.path.getsize(self.ged_csv),
                "sha256": sha256_file(self.ged_csv),
                "row_count": self.total_rows,
            },
            "artifacts": [
                {"file": os.path.basename(p), "sha256": sha256_file(p),
                 "size_bytes": os.path.getsize(p)}
                for p in (year_path, month_path, report_path)
            ],
            "usage_policy": {
                "allowed": sorted(ALLOWED_CONSUMERS),
                "forbidden": sorted(FORBIDDEN_CONSUMERS),
                "note": "年度冻结快照，禁作当前信号（§7.5 / 架构 Round2-3 硬闸门）",
            },
            "vintage_note": "v26.1 冻结只读；v27 另存新目录，绝不原地覆盖",
        }
        self._write_json(manifest_path, manifest)

        log.info("产物已写入 %s", self.out_dir)
        log.info("  年度表 %d 行 / 月度表 %d 行", len(self.agg_year), len(self.agg_month))

    def _write_year_table(self, path: str, meta: Dict[str, object]) -> None:
        """写 country × year × type_of_violence 年度聚合表。"""
        columns = [
            "country", "country_id", "region", "year", "type_of_violence",
            "events", "deaths_best", "deaths_low", "deaths_high",
            "deaths_a", "deaths_b", "deaths_civilians", "deaths_unknown",
            "events_geolocated", "clamped_rows", "source_sentinel_rows",
            "date_prec_1_3", "date_prec_4_5",
            "snapshot_year", "frozen", "dataset_version", "schema_version",
            "as_of", "data_vintage",
        ]
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            for (country, year, tov) in sorted(self.agg_year.keys()):
                cell = self.agg_year[(country, year, tov)]
                country_id, region = self.country_meta.get(country, (0, ""))
                writer.writerow([
                    country, country_id, region, year, tov,
                    cell.events, cell.deaths_best, cell.deaths_low, cell.deaths_high,
                    cell.deaths_a, cell.deaths_b, cell.deaths_civilians, cell.deaths_unknown,
                    cell.events_geolocated, cell.clamped_rows, cell.source_sentinel_rows,
                    cell.date_prec_1_3, cell.date_prec_4_5,
                    meta["snapshot_year"], meta["frozen"], meta["dataset_version"],
                    meta["schema_version"], meta["as_of"], meta["data_vintage"],
                ])

    def _write_month_table(self, path: str, meta: Dict[str, object]) -> None:
        """写 country × year_month × type_of_violence 月度聚合表（date_prec <= 3）。"""
        columns = [
            "country", "country_id", "region", "year_month", "type_of_violence",
            "events", "deaths_best", "deaths_low", "deaths_high",
            "deaths_a", "deaths_b", "deaths_civilians", "deaths_unknown",
            "events_geolocated", "clamped_rows", "source_sentinel_rows",
            "cross_month_rows",
            "snapshot_year", "frozen", "dataset_version", "schema_version",
            "as_of", "data_vintage",
        ]
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            for (country, year_month, tov) in sorted(self.agg_month.keys()):
                cell = self.agg_month[(country, year_month, tov)]
                country_id, region = self.country_meta.get(country, (0, ""))
                writer.writerow([
                    country, country_id, region, year_month, tov,
                    cell.events, cell.deaths_best, cell.deaths_low, cell.deaths_high,
                    cell.deaths_a, cell.deaths_b, cell.deaths_civilians, cell.deaths_unknown,
                    cell.events_geolocated, cell.clamped_rows, cell.source_sentinel_rows,
                    cell.cross_month_rows,
                    meta["snapshot_year"], meta["frozen"], meta["dataset_version"],
                    meta["schema_version"], meta["as_of"], meta["data_vintage"],
                ])

    def _build_report(self) -> Dict[str, object]:
        """构造 validation_report。"""
        excluded = sum(v for k, v in self.date_prec_dist.items() if k > MONTHLY_MAX_DATE_PREC)
        total = self.total_rows or 1
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_version": DATASET_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "path": self.ged_csv,
                "size_bytes": os.path.getsize(self.ged_csv),
            },
            "counts": {
                "total_rows": self.total_rows,
                "accepted": self.accepted,
                "quarantined": self.quarantined,
                "agg_year_rows": len(self.agg_year),
                "agg_month_rows": len(self.agg_month),
                "countries": len(self.country_meta),
            },
            "gates": {name: gate.to_dict() for name, gate in self.gates.items()},
            "coverage": {
                "cross_month_events": self.cross_month_events,
                "cross_month_ratio": round(self.cross_month_events / total, 6),
                "cross_year_events": self.cross_year_events,
                "cross_year_note": (
                    "v26.1 实测 0 行；若 v27 出现非零值，需复核年度归属口径而非沿用旧规则"
                ),
                "date_prec_4_5_excluded_from_monthly": excluded,
                "date_prec_4_5_ratio": round(excluded / total, 6),
                "attribution": "跨月事件全额计入 date_start 所在月，不按日摊分",
            },
            "snapshot": {
                "snapshot_year": self.snapshot_year,
                "frozen": True,
                "as_of": f"{self.snapshot_year}-12-31",
            },
            "usage_policy": {
                "allowed": sorted(ALLOWED_CONSUMERS),
                "forbidden": sorted(FORBIDDEN_CONSUMERS),
                "note": "年度冻结快照，禁作当前信号（§7.5 / 架构 Round2-3 硬闸门）",
            },
            "interval_semantics_warning": (
                "deaths_low/high 是各事件 UCDP 单事件区间的**求和**，"
                "不构成聚合层统计置信区间，禁止直接映射为 indicators 宽表的 ci_low/ci_high。"
            ),
        }

    @staticmethod
    def _write_json(path: str, payload: Dict[str, object]) -> None:
        """原子写 JSON（先写 tmp 再 replace）。"""
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_arg_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="UCDP GED v26.1 离线 ETL（标准化 + 聚合 + 三道质量闸门）"
    )
    parser.add_argument("--ged-csv", default=None, help="GED 原始 CSV 路径")
    parser.add_argument("--data-dir", default=None, help="macro-scan data 目录")
    parser.add_argument("--dry-run", action="store_true", help="只跑闸门，不写产物")
    parser.add_argument("--limit", type=int, default=None, help="仅处理前 N 行（自测用）")
    parser.add_argument("--verbose", action="store_true", help="DEBUG 日志")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """程序入口。

    Returns:
        进程退出码：0 成功 / 2 闸门失败 / 3 输入错误。
    """
    args = build_arg_parser().parse_args(argv)
    if args.verbose:
        log.setLevel(logging.DEBUG)

    try:
        data_dir = resolve_data_dir(args.data_dir)
        ged_csv = resolve_ged_csv(args.ged_csv, data_dir)
    except GedEtlError as exc:
        log.error("输入定位失败：%s", exc)
        return EXIT_INPUT_ERROR

    etl = GedEtl(
        ged_csv=ged_csv,
        data_dir=data_dir,
        dry_run=args.dry_run,
        limit=args.limit,
    )

    try:
        return etl.run()
    except FrozenSnapshotViolation as exc:
        log.error("冻结快照守卫触发：%s", exc)
        return EXIT_INPUT_ERROR
    except GateFailure as exc:
        log.error("闸门自检失败：%s", exc)
        return EXIT_GATE_FAILED
    except GedEtlError as exc:
        log.error("ETL 失败：%s", exc)
        return EXIT_INPUT_ERROR


if __name__ == "__main__":
    sys.exit(main())
