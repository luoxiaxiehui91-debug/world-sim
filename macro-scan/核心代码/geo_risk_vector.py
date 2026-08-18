"""
geo_risk_vector.py — 地缘风险向量（GRV）聚合器
M1-2：将 GDELT 分数 + GPR 指数聚合为标准化 GRV 向量，写入 data/grv_latest.json

每日 06:10 由 scheduler.py 触发（GDELT 扫描 06:00 之后）。
读取：
  - data/gdelt_scores.json   （scan_weak_signals.py 每6h写入）
  - data/fred_history/GPRC_TWN.csv 等  （fetch_fred_history.py 每日05:30写入）
输出：
  - data/grv_latest.json

运行：python3 /app/geo_risk_vector.py
"""

import os
import json
import logging
import datetime
import pandas as pd

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    _ws = os.environ.get("OPENCLAW_WORKSPACE",
                         os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR  = os.path.join(_ws, "data")
    WORKSPACE = _ws

LOG_DIR  = "/var/log/macro-scan"
LOG_FILE = os.path.join(LOG_DIR, "grv.log")

GDELT_FILE   = os.path.join(DATA_DIR, "gdelt_scores.json")
GDELT_HIST   = os.path.join(DATA_DIR, "gdelt_history.jsonl")   # 08-18 #77：GDELT 日频历史（scan_weak_signals 每 6h 追加）
FRED_DIR     = os.path.join(DATA_DIR, "fred_history")
GRV_OUTPUT   = os.path.join(DATA_DIR, "grv_latest.json")
GRV_HISTORY  = os.path.join(DATA_DIR, "grv_history.jsonl")
GED_CSV      = os.path.join(DATA_DIR, "ged", "ged_agg_country_month.csv")

# 08-18 #77：GDELT 全球日频紧张度的风险语义维度（coop 正向排除；social_stress/cultural_friction 已有独立透传）
RISK_GDELT_DIMS = ("military", "tension", "sanction", "protest", "religious_conflict", "regime_change")

# GPR 系列历史分位数（滚动10年 P10-P95 归一化）
# p95 代替 p90，避免极端事件（如2026-03关税战峰值331）把天花板压得过低导致长期触顶
_GPR_FALLBACK_RANGE = {"p10": 50, "p95": 220}  # 历史 GPR 大致区间

# GDELT 原始分归一化基准（gdelt_history.jsonl 实测 p95，2026-05-21~2026-07-08，211条）
# 公式：score_norm = min(raw / p95_ref * 100, 100)
# 0 基点保持物理含义（无事件=0），p95 作上限而非 p10-p95 区间，避免负值
# P1-C（2026-08-04）：改为运行时从 gdelt_history.jsonl 动态计算；
#   样本 <100 条时 fallback 到此硬编码值（当前基于 165 条实测）
_GDELT_P95_FALLBACK = {
    "russia_europe": 1.243,
    "taiwan_strait": 0.620,
    "us_china":      9.790,
    "mideast":       2.533,
}

# 动态 P95 缓存（每次进程启动时计算一次）
_GDELT_P95: dict = {}


def _compute_gdelt_p95_dynamic() -> dict:
    """
    从 gdelt_calib.json 读取各热点 GDELT 组合分的 P95（天玑 tianji_calibrator.py 产出）。

    热点组合与 _gdelt_country_score 保持一致（mil+sanc 平均）：
      russia_europe / taiwan_strait / us_china / mideast
    样本量 <100 或配置缺失时 fallback 到 _GDELT_P95_FALLBACK（硬编码值）。
    E0-C/V3（2026-08-14）：原进程内自算逻辑退役，统一读天玑校准配置（单一事实源）。
    """
    global _GDELT_P95
    calib_path = os.path.join(DATA_DIR, "gdelt_calib.json")
    if not os.path.exists(calib_path):
        _GDELT_P95 = dict(_GDELT_P95_FALLBACK)
        return _GDELT_P95
    try:
        import json as _json
        with open(calib_path, encoding="utf-8") as f:
            d = _json.load(f)
        hp = (d or {}).get("hotspot_p95") or {}
        if (d or {}).get("sample_count", 0) < 100 or not isinstance(hp, dict) or not hp:
            _get_logger().info("[GRV] gdelt_calib 样本不足/无配置，使用硬编码 P95 fallback")
            _GDELT_P95 = dict(_GDELT_P95_FALLBACK)
            return _GDELT_P95
        merged = dict(_GDELT_P95_FALLBACK)
        merged.update({k: float(v) for k, v in hp.items() if v})
        _GDELT_P95 = merged
        _get_logger().info(
            "[GRV] GDELT P95 从天玑校准配置加载（%d条样本）: %s",
            d.get("sample_count"), merged,
        )
        return _GDELT_P95
    except Exception as _e:
        _get_logger().warning("[GRV] gdelt_calib 读取失败（%s），使用硬编码 P95 fallback", _e)
        _GDELT_P95 = dict(_GDELT_P95_FALLBACK)
        return _GDELT_P95

# ===== C01 修复（2026-08-15）：af752ea「GDELT 校准器落地」误删的 5 个模块常量，按 f6142dd 版原样补回 =====
_CONFLICT_FLOOR = {
    "russia_europe": 35.0,
}
_CONFLICT_FLOOR_MIN_ARTICLES = 5  # 触发 floor 所需的近30天冲突文章数


# GED P95 基准锚点（ged_agg_country_month.csv，1989-2024，地区月度聚合，state+one-sided）
# 多 agent 辩论结论（地缘政治理论+数据科学+怀疑者，2026-08-04）：
#   P95 = 3570 死亡/地区/月；log1p(3570) ≈ 8.18
#   权重：GED×0.30 + GDELT×0.70（保守起步，3个月后校准）
#   适用维度：russia_europe（Europe）/ middle_east_energy（Middle East）
#   不适用：taiwan_strait / us_china_strategic（威慑型风险，死亡数无意义）
_GED_P95_ANCHOR = 3570.0
_GED_REGION_MAP = {
    "russia_europe":    "Europe",
    "middle_east_energy": "Middle East",
}
_GED_STALE_MONTHS = 18  # 超过此月数无数据则权重自动降为 0

def _load_ged_conflict_signal(dimension: str) -> float | None:
    """
    读取 GED v26.1 月度聚合数据，为指定 GRV 维度计算冲突死亡信号（0-100）。

    设计依据（多 agent 辩论，2026-08-04）：
    - 归一化：log1p(deaths_12m_rolling) / log1p(P95_anchor) × 100，clip [0,100]
    - P95 anchor = 3570（地区月度聚合，1989-2024 实测）
    - 只统计 type_of_violence in (1=state-based, 3=one-sided)
    - GED 冻结到 2024 年末；若最新可用数据 > 18 个月前，返回 None（权重退化为 0）
    - Richardson (1960) log 量级框架；UCDP/PRIO 理论基础
    - 非阻断：任何异常返回 None，上层融合自动退化为 GDELT-only
    """
    region = _GED_REGION_MAP.get(dimension)
    if not region:
        return None
    if not os.path.exists(GED_CSV):
        return None
    try:
        import csv as _csv
        import math as _math

        # Schema 断言：必需字段存在
        _REQUIRED = {"region", "year_month", "type_of_violence", "deaths_best"}
        cutoff_ym = (
            datetime.datetime.now() - datetime.timedelta(days=_GED_STALE_MONTHS * 30)
        ).strftime("%Y-%m")
        window_start = (
            datetime.datetime.now() - datetime.timedelta(days=365)
        ).strftime("%Y-%m")

        total_deaths = 0.0
        latest_ym = ""
        row_count = 0
        with open(GED_CSV, newline="", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            if not _REQUIRED.issubset(set(reader.fieldnames or [])):
                _get_logger().error("[GED] CSV schema 断言失败，缺少必需字段: %s",
                                    _REQUIRED - set(reader.fieldnames or []))
                return None
            for row in reader:
                if row.get("region") != region:
                    continue
                tov = row.get("type_of_violence", "")
                if tov not in ("1", "3"):
                    continue
                ym = row.get("year_month", "")
                if ym < window_start:
                    continue
                row_count += 1
                if ym > latest_ym:
                    latest_ym = ym
                try:
                    total_deaths += float(row.get("deaths_best") or 0)
                except (ValueError, TypeError):
                    pass

        if not latest_ym or latest_ym < cutoff_ym:
            _get_logger().warning(
                "[GED] %s 数据过期（最新=%s 阈值=%s），GED 权重退化为 0",
                dimension, latest_ym or "无", cutoff_ym,
            )
            return None

        if row_count == 0:
            return None

        score = min(100.0, _math.log1p(total_deaths) / _math.log1p(_GED_P95_ANCHOR) * 100)
        _get_logger().info(
            "[GED] %s region=%s deaths_12m=%.0f latest=%s → score=%.1f",
            dimension, region, total_deaths, latest_ym, score,
        )
        return round(score, 1)
    except Exception as _e:
        _get_logger().warning("[GED] %s 读取失败（非阻断）: %s", dimension, _e)
        return None


def _get_logger():
    logger = logging.getLogger("grv")
    if not logger.handlers:
        os.makedirs(LOG_DIR, exist_ok=True)
        h = logging.FileHandler(LOG_FILE, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger


def _load_gdelt() -> dict:
    """读取 GDELT 分数缓存，返回 scores 子字典。缺失返回空 dict。"""
    try:
        with open(GDELT_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("scores", {}), data.get("updated", "N/A")
    except Exception:
        return {}, "N/A"


def _compute_gdelt_risk_daily() -> float | None:
    """GDELT 全球日频紧张度（0-100）——08-18 #77 global_composite 混入用。

    方法：6 个风险语义维度（RISK_GDELT_DIMS）各自全球均值 → 每维在自身历史中
    的百分位（0-100）→ 等权平均 = 当日紧张度。历史不足 30 天返回 None（容错）。

    数据：gdelt_history.jsonl（scan_weak_signals 每 6h 追加，每天多条 → 按天去重
    取最后一条）。88 天旁路验证：min 15.7 / p50 52.5 / p90 73.6 / max 99.4。
    """
    try:
        by_date: dict[str, dict] = {}
        with open(GDELT_HIST, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("date"):
                    by_date[d["date"]] = d   # 后写覆盖 = 每天取最后一条
        if len(by_date) < 30:
            return None
        hist = sorted(by_date.items(), key=lambda x: x[0])
        n = len(hist)
        series: dict[str, list[float]] = {}
        for dim in RISK_GDELT_DIMS:
            out: list[float] = []
            for _dt, d in hist:
                s = d.get("scores", {}).get(dim, {})
                vals = [v for v in s.values() if isinstance(v, (int, float))]
                out.append(sum(vals) / len(vals) if vals else 0.0)
            series[dim] = out
        daily = [0.0] * n
        for dim in RISK_GDELT_DIMS:
            vals = series[dim]
            for i in range(n):
                rank = sum(1 for v in vals if v <= vals[i]) - 1
                daily[i] += rank / max(1, n - 1) * 100 / len(RISK_GDELT_DIMS)
        return round(daily[-1], 1)
    except Exception as _e:
        logger.warning(f"[GRV] gdelt_risk_daily 计算失败（非阻断，退旧公式）: {_e}")
        return None


def _load_gpr(series_id: str) -> tuple[float | None, str | None]:
    """读取 GPR CSV 最新值。返回 (value, date)。"""
    path = os.path.join(FRED_DIR, f"{series_id}.csv")
    if not os.path.exists(path):
        return None, None
    try:
        df = pd.read_csv(path).dropna(subset=["value"]).sort_values("date")
        if df.empty:
            return None, None
        last = df.iloc[-1]
        return float(last["value"]), str(last["date"])
    except Exception:
        return None, None


def _normalize_gpr(raw: float | None, series_id: str) -> float | None:
    """
    用滚动10年 P10-P95 分位数把 GPR 原始值映射到 [0-100]。
    使用 p95 而非 p90，避免极端事件（如2026-03关税战峰值）导致长期触顶。
    若历史数据不足 120 个月，退回固定兜底区间。
    """
    if raw is None:
        return None
    path = os.path.join(FRED_DIR, f"{series_id}.csv")
    try:
        df = pd.read_csv(path).dropna(subset=["value"]).sort_values("date")
        if len(df) >= 24:
            tail = df.tail(120)  # 最近10年（月度=120条）
            p10 = float(tail["value"].quantile(0.10))
            p95 = float(tail["value"].quantile(0.95))
        else:
            p10 = _GPR_FALLBACK_RANGE["p10"]
            p95 = _GPR_FALLBACK_RANGE["p95"]
    except Exception:
        p10 = _GPR_FALLBACK_RANGE["p10"]
        p95 = _GPR_FALLBACK_RANGE["p95"]

    if p95 <= p10:
        _get_logger().warning(
            f"[GRV] {series_id} 归一化退化：p95({p95:.1f}) <= p10({p10:.1f})，"
            f"数据可能不足或过度集中，回退为 50.0"
        )
        return 50.0
    normalized = (raw - p10) / (p95 - p10) * 100
    return round(min(max(normalized, 0.0), 100.0), 1)


def _gdelt_country_score(scores: dict, countries: list[str]) -> float | None:
    """取多个国家的 GDELT 军事/制裁分数均值，作为该热点的 GDELT 信号。"""
    logger = _get_logger()
    vals = []
    for c in countries:
        mil = scores.get("military", {}).get(c, 0) or 0
        sanc = scores.get("sanction", {}).get(c, 0) or 0
        vals.append((mil + sanc) / 2)
    if not vals:
        return None
    result = round(sum(vals) / len(vals), 1)
    if result == 0.0:
        logger.warning("[GRV] GDELT 全0信号 countries=%s — 视为无信号（可能是API采集失败或无事件）", countries)
    return result


def _normalize_gdelt_score(raw: float | None, hotspot_key: str) -> float | None:
    """
    将 GDELT 原始分（量纲 0~12）归一化到 0–100，与 GPR 归一化值量纲对齐。
    基准：_GDELT_P95[hotspot_key] = gdelt_history.jsonl 实测 p95（211条，2026-05-21~07-08）
    公式：min(raw / p95_ref * 100, 100)，0 基点保持"无事件=0"的物理含义。
    """
    if raw is None:
        return None
    p95 = _GDELT_P95.get(hotspot_key)
    if not p95:
        return None  # 无基准则返回 None，让 _blend 走 GPR-only 路径，避免量纲不匹配
    return round(min(raw / p95 * 100, 100.0), 1)


def _apply_conflict_floor(value: float | None, dimension: str) -> float | None:
    """
    持续冲突 floor：若 news.db 中近30天存在足够多的冲突相关文章，
    对应维度的 GRV 值不低于 _CONFLICT_FLOOR 设定的下限。
    防止 GPR/GDELT 因媒体疲劳（战争常态化）导致维度虚低。
    数据库不可用时非阻断跳过，直接返回原值。
    """
    floor = _CONFLICT_FLOOR.get(dimension)
    if floor is None or value is None:
        return value
    try:
        import pg_read as _pg
        conn = _pg.connect()
        if conn is None:
            return value
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
        (count,) = conn.execute("""
            SELECT COUNT(DISTINCT a.id)
            FROM news.articles a
            JOIN news.article_categories ac ON a.id = ac.article_id
            WHERE ac.category IN ('geopolitics', '地缘升级')
              AND (a.country_tag LIKE '%%RUS%%' OR a.country_tag LIKE '%%UKR%%'
                   OR a.title LIKE '%%俄%%' OR a.title LIKE '%%乌克兰%%'
                   OR a.title LIKE '%%Russia%%' OR a.title LIKE '%%Ukraine%%')
              AND a.published_at > %s
        """, (cutoff,)).fetchone()
        conn.close()
        if count >= _CONFLICT_FLOOR_MIN_ARTICLES:
            if value < floor:
                _get_logger().info(
                    f"[GRV] {dimension} floor触发: "
                    f"raw={value:.1f} → floor={floor}（近30天冲突文章={count}）"
                )
            return max(value, floor)
    except Exception as _e:
        _get_logger().warning(f"[GRV] {dimension} floor检测失败（非阻断）: {_e}")
    return value


def _compute_japan_monetary() -> float | None:
    """
    日元货币压力指数（japan_monetary），0–100。

    两个子信号各50%权重：

    1. USD/JPY 水位（日频，DEXJPUS）：
       衡量套利仓位堆积程度。
       公式：min(max((usdjpy - 120) / (165 - 120) × 100, 0), 100)
       120 = 历史正常下限；165 = 2024年历史顶部

    2. 日本10Y收益率3个月变化速度（月频，IRLTLT01JPM156N）：
       BOJ 政策转向前兆，3M涨幅>25bp 是历史套利平仓触发线。
       公式：min(max(chg_3m_bp / 100 × 100, 0), 100)
       100bp 映射到 100分；下跌时为 0

    任一数据缺失时，只用有效的那个。两者均缺失返回 None。
    """
    usdjpy_score = None
    jgb_score    = None

    # ── 子信号1：USD/JPY 水位 ─────────────────────────────────
    try:
        path = os.path.join(FRED_DIR, "DEXJPUS.csv")
        if os.path.exists(path):
            df = pd.read_csv(path).dropna(subset=["value"]).sort_values("date")
            if not df.empty:
                usdjpy = float(df.iloc[-1]["value"])
                usdjpy_score = round(min(max((usdjpy - 120) / (165 - 120) * 100, 0.0), 100.0), 1)
    except Exception:
        pass

    # ── 子信号2：JGB 10Y 收益率3月变化速度 ───────────────────
    try:
        path = os.path.join(FRED_DIR, "IRLTLT01JPM156N.csv")
        if os.path.exists(path):
            df = pd.read_csv(path).dropna(subset=["value"]).sort_values("date")
            if len(df) >= 4:
                latest  = float(df.iloc[-1]["value"])
                prev_3m = float(df.iloc[-4]["value"])   # 月频，-4行≈3个月前
                chg_bp  = (latest - prev_3m) * 100      # % → bp
                jgb_score = round(min(max(chg_bp / 100 * 100, 0.0), 100.0), 1)
    except Exception:
        pass

    # ── 合成 ──────────────────────────────────────────────────
    if usdjpy_score is None and jgb_score is None:
        return None
    if usdjpy_score is None:
        return jgb_score
    if jgb_score is None:
        return usdjpy_score
    return round(usdjpy_score * 0.5 + jgb_score * 0.5, 1)


def compute_grv() -> dict:
    """
    计算 GRV 向量。
    结构：
      taiwan_strait      = GDELT×0.4 + GPR_TWN×0.6（若 GPR 不可用则纯 GDELT）
      us_china_strategic = GDELT×0.5 + GPR_CHN×0.5
      russia_europe      = GDELT×0.4 + GPR_RUS×0.6
      middle_east_energy = GDELT×0.6 + GPR 伊朗/沙特×0.4
      global_composite   = GPR 全球指数归一化
    """
    # ── 推导维度辅助函数（定义在函数顶层，确保 try 块内可见）──────
    def _d_sf(fd, c):
        """安全取单国分数，缺失返回 None。"""
        v = fd.get(c) if isinstance(fd, dict) else None
        return float(v) if v is not None else None

    def _d_norm(fd, c, scale):
        """取单国分数并归一化到 [0,100]。"""
        v = _d_sf(fd, c)
        return min(100.0, v * scale) if v is not None else None

    def _d_ws(pairs):
        """加权均值，过滤 None 后归一化权重。"""
        valid = [(v, w) for v, w in pairs if v is not None]
        if not valid:
            return None
        tw = sum(w for _, w in valid)
        return sum(v * (w / tw) for v, w in valid)

    def _d_rb(scores, weights=None):
        """0.6·max + 0.4·加权均值，有效值<1时返回None。"""
        pairs = [(s, (weights[i] if weights else 1.0)) for i, s in enumerate(scores) if s is not None]
        if not pairs:
            return None
        vals = [s for s, _ in pairs]
        tw = sum(w for _, w in pairs)
        wmean = sum(s * (w / tw) for s, w in pairs)
        return round(0.6 * max(vals) + 0.4 * wmean, 1)
    logger = _get_logger()
    # P1-C：每次运行前动态更新 GDELT P95 基准（样本 <100 时用硬编码 fallback）
    _compute_gdelt_p95_dynamic()
    gdelt_scores, gdelt_updated = _load_gdelt()

    # ── GDELT 各热点分数 ──────────────────────────────────────
    gdelt_taiwan   = _gdelt_country_score(gdelt_scores, ["TWN", "CHN"])
    gdelt_uschina  = _gdelt_country_score(gdelt_scores, ["USA", "CHN"])
    gdelt_russia   = _gdelt_country_score(gdelt_scores, ["RUS", "DEU", "UKR"])
    gdelt_mideast  = _gdelt_country_score(gdelt_scores, ["IRN", "SAU", "ISR"])

    # ── GDELT 归一化（原始分量纲 0~12 → 0–100，与 GPR 对齐）──
    gdelt_taiwan_n  = _normalize_gdelt_score(gdelt_taiwan,  "taiwan_strait")
    gdelt_uschina_n = _normalize_gdelt_score(gdelt_uschina, "us_china")
    gdelt_russia_n  = _normalize_gdelt_score(gdelt_russia,  "russia_europe")
    gdelt_mideast_n = _normalize_gdelt_score(gdelt_mideast, "mideast")

    # ── GPR 最新归一化值 ──────────────────────────────────────
    gpr_twn_raw, gpr_twn_date = _load_gpr("GPRC_TWN")
    gpr_chn_raw, _            = _load_gpr("GPRC_CHN")
    gpr_rus_raw, _            = _load_gpr("GPRC_RUS")
    gpr_global_raw, _         = _load_gpr("GPR")
    # CFG-1: 中东无专项 GPR 系列（GPRC_IRN/GPRC_SAU 官方未发布），
    # middle_east_energy 的 GPR 成分不再借用 gpr_global（会导致与 global_composite 相关性虚高）
    # 改为纯 GDELT 驱动，GPR 成分留空（_blend 自动走 gdelt_only 路径）

    gpr_twn    = _normalize_gpr(gpr_twn_raw, "GPRC_TWN")
    gpr_chn    = _normalize_gpr(gpr_chn_raw, "GPRC_CHN")
    gpr_rus    = _normalize_gpr(gpr_rus_raw, "GPRC_RUS")
    gpr_global = _normalize_gpr(gpr_global_raw, "GPR")

    # ── 合成各维度 ────────────────────────────────────────────
    def _blend(gdelt_val, gpr_val, w_gdelt, w_gpr):
        if gdelt_val is None and gpr_val is None:
            return None
        if gpr_val is None:
            return round(float(gdelt_val), 1)
        if gdelt_val is None:
            return round(float(gpr_val), 1)
        return round(gdelt_val * w_gdelt + gpr_val * w_gpr, 1)

    taiwan_strait      = _blend(gdelt_taiwan_n,  gpr_twn,    0.4, 0.6)
    us_china_strategic = _blend(gdelt_uschina_n, gpr_chn,    0.5, 0.5)

    # russia_europe：GDELT×0.7 + GED×0.3（GED 不可用时退化为纯 GDELT+GPR）
    # 多 agent 辩论结论（2026-08-04）：europe 有 GED 覆盖，GED 为低频校准锚点
    ged_russia = _load_ged_conflict_signal("russia_europe")
    if ged_russia is not None:
        gdelt_russia_blended = (
            (gdelt_russia_n or 0.0) * 0.70 + ged_russia * 0.30
            if gdelt_russia_n is not None else ged_russia
        )
        russia_europe = _blend(gdelt_russia_blended, gpr_rus, 0.4, 0.6)
    else:
        russia_europe  = _blend(gdelt_russia_n,  gpr_rus,    0.4, 0.6)

    # middle_east_energy：先 GDELT×0.7 + GED×0.3 融合，再接 WTI 油价（P0 修复）
    ged_mideast = _load_ged_conflict_signal("middle_east_energy")
    if ged_mideast is not None:
        gdelt_mideast_blended = (
            (gdelt_mideast_n or 0.0) * 0.70 + ged_mideast * 0.30
            if gdelt_mideast_n is not None else ged_mideast
        )
        middle_east_energy = _blend(gdelt_mideast_blended, None, 1.0, 0.0)
    else:
        middle_east_energy = _blend(gdelt_mideast_n, None,       1.0, 0.0)  # CFG-1: 纯GDELT，无中东专项GPR

    # ── 接入 WTI 油价补强 middle_east_energy（P0修复，2026-08-03）──
    # 理论依据：Smith & Pinchetti (2024, Bank of England) 证明中东冲突主要通过
    # Channel B（能源供应中断→油价→通胀）传导，纯 GDELT 驱动是方法论错误。
    # 目标权重：GDELT×0.45 + WTI_signal×0.40 + Channel_B_激活×0.15
    # 油价归一化：[60, 120] USD/bbl → [0, 100]
    try:
        cy_path = os.path.join(DATA_DIR, "commodity_yahoo.json")
        if os.path.exists(cy_path):
            with open(cy_path, encoding="utf-8") as _cy2:
                _cy2d = json.load(_cy2)
            if _cy2d.get("status") in ("ok", "partial"):
                _wti = _cy2d.get("commodities", {}).get("wti")
                if _wti and isinstance(_wti.get("price"), (int, float)):
                    wti_price = float(_wti["price"])
                    wti_signal = min(100.0, max(0.0, (wti_price - 60.0) / (120.0 - 60.0) * 100))
                    # Channel B 激活：WTI > 95 USD/bbl 时额外加权
                    channel_b_bonus = 15.0 if wti_price > 95.0 else 0.0
                    if middle_east_energy is not None:
                        middle_east_energy = round(
                            middle_east_energy * 0.45 + wti_signal * 0.40 + channel_b_bonus,
                            1
                        )
                    else:
                        middle_east_energy = round(wti_signal * 0.40 + channel_b_bonus, 1)
                    logger.info(
                        "[GRV] middle_east_energy + WTI=%.1f → wti_signal=%.1f channel_b=%s → %.1f",
                        wti_price, wti_signal, "ON" if wti_price > 95 else "off", middle_east_energy
                    )
    except Exception as _mee:
        logger.warning(f"[GRV] WTI 接入 middle_east_energy 失败（非阻断，维持纯GDELT）: {_mee}")

    # ── 持续冲突 floor（防媒体疲劳导致维度虚低）────────────────
    russia_europe = _apply_conflict_floor(russia_europe, "russia_europe")

    # 数据来源质量标记
    has_gpr    = gpr_twn is not None
    has_gdelt  = bool(gdelt_scores)
    if has_gpr and has_gdelt:
        source_quality = "gdelt+gpr"
    elif has_gdelt:
        source_quality = "gdelt_only"
    elif has_gpr:
        source_quality = "gpr_only"
    else:
        source_quality = "stub"

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    # ── 接入气候信号（climate_risk）────────────────────────────
    climate_risk = None
    try:
        climate_path = os.path.join(DATA_DIR, "climate_signals.json")
        if os.path.exists(climate_path):
            with open(climate_path, encoding="utf-8") as _cf:
                _cd = json.load(_cf)
            climate_risk = _cd.get("climate_risk_score")
    except Exception:
        pass

    # ── 接入灾害信号（disaster_risk）───────────────────────────
    disaster_risk = None
    try:
        disaster_path = os.path.join(DATA_DIR, "disaster_signals.json")
        if os.path.exists(disaster_path):
            with open(disaster_path, encoding="utf-8") as _df:
                _dd = json.load(_df)
            disaster_risk = _dd.get("disaster_risk_score")
    except Exception:
        pass

    # ── 接入制裁信号（sanctions_risk）──────────────────────────
    # 来源：fetch_sanctions.py 用 OpenSanctions bulk data（sanctions 数据集
    # targets.simple.csv）做国别制裁暴露聚合，写出 data/sanctions_risk.json。
    # 这里直接消费其全局基线 global_sanctions_risk（0–100，长期持久基线）。
    sanctions_risk = None
    try:
        sanc_path = os.path.join(DATA_DIR, "sanctions_risk.json")
        if os.path.exists(sanc_path):
            with open(sanc_path, encoding="utf-8") as _sf:
                _sd = json.load(_sf)
            if _sd.get("status") == "ok":
                g = _sd.get("global_sanctions_risk")
                if isinstance(g, (int, float)):
                    sanctions_risk = round(float(g), 1)
                else:
                    logger.warning("[GRV] sanctions_risk 全局值缺失/类型异常，留空")
            else:
                logger.info("[GRV] 制裁数据 status=%s，sanctions_risk 留空", _sd.get("status"))
    except Exception as _e:
        logger.warning(f"[GRV] 制裁信号读取失败（非阻断）: {_e}")

    # ── 接入地震压力（seismic_risk）──────────────────────────
    # 来源：fetch_earthquake.py（USGS Earthquake feed，全局地震压力指数 0–100）。
    # 与 fetch_disaster_signals.py 的 disaster_risk（事件级告警）互补：
    # 此处为全局结构性压力基线，喂 GRV 的 energy/grid 外生冲击维度。
    seismic_risk = None
    try:
        eq_path = os.path.join(DATA_DIR, "earthquake_risk.json")
        if os.path.exists(eq_path):
            with open(eq_path, encoding="utf-8") as _eq:
                _ed = json.load(_eq)
            if _ed.get("status") == "ok":
                s = _ed.get("seismic_risk")
                if isinstance(s, (int, float)):
                    seismic_risk = round(float(s), 1)
                else:
                    logger.warning("[GRV] seismic_risk 全局值缺失/类型异常，留空")
            else:
                logger.info("[GRV] 地震数据 status=%s，seismic_risk 留空", _ed.get("status"))
    except Exception as _e:
        logger.warning(f"[GRV] 地震信号读取失败（非阻断）: {_e}")

    # ── 接入能源/电网压力（energy_grid_risk）──────────────────
    # 优先天然气（NG，USD/MMBtu）；不存在时依次回退 Brent → WTI（USD/bbl）。
    # Brent/WTI 归一化：[50, 110] → [0, 100]；天然气：[2, 8] → [0, 100]。
    energy_grid_risk = None
    try:
        cy_path = os.path.join(DATA_DIR, "commodity_yahoo.json")
        if os.path.exists(cy_path):
            with open(cy_path, encoding="utf-8") as _cy:
                _cyd = json.load(_cy)
            if _cyd.get("status") in ("ok", "partial"):
                commodities = _cyd.get("commodities", {})
                _energy = (commodities.get("natural_gas") or commodities.get("ng")
                           or commodities.get("brent") or commodities.get("wti"))
                if _energy and isinstance(_energy.get("price"), (int, float)):
                    e_price = float(_energy["price"])
                    unit    = _energy.get("unit", "USD/bbl")
                    if "MMBtu" in unit:
                        energy_grid_risk = round(min(100.0, max(0.0, (e_price - 2.0) / 6.0 * 100)), 1)
                    else:
                        energy_grid_risk = round(min(100.0, max(0.0, (e_price - 50.0) / 60.0 * 100)), 1)
                    logger.info("[GRV] energy_grid_risk from %s=%.2f %s → %.1f",
                                _energy.get("symbol", "?"), e_price, unit, energy_grid_risk)
                else:
                    logger.warning("[GRV] commodity_yahoo 无可用能源价格，energy_grid_risk 留空")
            else:
                logger.info("[GRV] commodity_yahoo status=%s，energy_grid_risk 留空",
                            _cyd.get("status"))
        else:
            en_path = os.path.join(DATA_DIR, "energy_risk.json")
            if os.path.exists(en_path):
                with open(en_path, encoding="utf-8") as _en:
                    _end = json.load(_en)
                if _end.get("status") in ("ok", "partial"):
                    g = _end.get("grid_carbon_risk")
                    if isinstance(g, (int, float)):
                        energy_grid_risk = round(float(g), 1)
                        logger.warning("[GRV] energy_grid_risk 降级使用 UK Carbon Intensity")
    except Exception as _e:
        logger.warning(f"[GRV] 能源信号读取失败（非阻断）: {_e}")

    # ── 日元货币压力（japan_monetary）─────────────────────────
    japan_monetary = _compute_japan_monetary()

    # global_composite：GPR 全球指数 85% + japan_monetary 15%
    # japan_monetary 后期新增维度，反映日元套息平仓风险对全球流动性的影响
    if gpr_global is not None and japan_monetary is not None:
        global_composite = round(gpr_global * 0.85 + japan_monetary * 0.15, 1)
    else:
        global_composite = gpr_global  # 任一缺失时退回纯 GPR

    # 08-18 #77：混入 GDELT 日频紧张度——GPR 月频基准 + GDELT 日频增量修正。
    # 权重 0.7/0.3 经 88 天旁路验证（gdelt_history）：日 std 0→6.1（月频阶梯→日频灵敏）；
    # 分布 p50 58.0 / p90 64.3（旧 60.3 恒值）。⚠️ delta 触发阈值已同步 6→12
    # （grv_threshold.py：|Δ|≥6 触发率 27.6% 过频 → ≥12 降至 5.7%，台海 abs 68 不受影响）。
    # GDELT 数据缺失/历史不足时 _compute_gdelt_risk_daily 返回 None → 自动退化旧公式。
    _gdelt_daily = _compute_gdelt_risk_daily()
    if _gdelt_daily is not None and global_composite is not None:
        global_composite = round(global_composite * 0.7 + _gdelt_daily * 0.3, 1)

    # ── 社会压力/文化摩擦（R09/R10，来自 gdelt_scores.json）───────
    # social_stress 在 gdelt_scores 中是 {country: score} 字典，取均值作为全局标量
    # cultural_friction 已经是 [0,100] 标量
    # 两者不经过 GRV 聚合层，直接透传到 grv_latest.json 供天璇读取
    social_stress_val = None
    cultural_friction_val = None
    try:
        if gdelt_scores:
            ss = gdelt_scores.get("social_stress", {})
            if isinstance(ss, dict) and ss:
                social_stress_val = round(sum(ss.values()) / len(ss), 1)
            elif isinstance(ss, (int, float)):
                social_stress_val = round(float(ss), 1)
            cf = gdelt_scores.get("cultural_friction")
            if cf is not None:
                if isinstance(cf, dict) and cf:
                    cultural_friction_val = round(sum(cf.values()) / len(cf), 1)
                elif isinstance(cf, (int, float)):
                    cultural_friction_val = round(float(cf), 1)
    except Exception as _e:
        logger.warning(f"[GRV] social_stress/cultural_friction 读取失败（非阻断）: {_e}")

    # ── 推导地缘维度（四个无 GPR 数据源的区域，2026-08-03）──────────
    # 来源：多角色论证（地缘政治+数据科学+怀疑者+工程师），详见 docs/grv_datasource_fix.md
    # 这四个维度是 GDELT 国别分数的加权聚合推导值，不使用 GPR 混合。
    # 设计原则：信号正交性优先，刻意选择与实测维度不重叠的 GDELT 字段。
    # 置信度说明：south_china_sea=0.50（VNM/PHL/IDN缺失）/ korean_peninsula=0.65（KOR缺失，PRK稀疏）
    #             india_pacific=0.70 / global_south=0.60（概念操作化有根本限制）
    _derived_dims = {}
    try:
        def _sf(field_dict, country):
            """安全取单国分数，缺失返回 None（不用0填充），归一化到 [0, 100]。"""
            v = field_dict.get(country) if isinstance(field_dict, dict) else None
            return float(v) if v is not None else None

        def _norm(field_dict, country, scale):
            """取单国分数并乘以 scale 归一化到 [0, 100]，结果 clip 到上限。"""
            v = _sf(field_dict, country)
            return min(100.0, v * scale) if v is not None else None

        # gdelt_scores 字段解包
        _gdelt = gdelt_scores or {}
        _mil   = _gdelt.get("military", {})
        _sanc  = _gdelt.get("sanction", {})
        _tens  = _gdelt.get("tension", {})
        _soc   = _gdelt.get("social_stress", {})   # 注意：social_stress 是 {country: score} 字典
        _reg   = _gdelt.get("regime_change", {})
        _prot  = _gdelt.get("protest", {})
        _relig = _gdelt.get("religious_conflict", {})
        _cult  = _gdelt.get("cultural_friction", {})

        def _m(c):  return _norm(_mil,   c, 10.0)
        def _s(c):  return _norm(_sanc,  c, 10.0)
        def _t(c):  return _norm(_tens,  c, 100.0)
        def _so(c): return _sf(_soc,     c)
        def _r(c):  return _norm(_reg,   c, 100.0)
        def _p(c):  return _norm(_prot,  c, 20.0)
        def _re(c): return _norm(_relig, c, 100.0)
        def _cf(c): return _norm(_cult,  c, 2.0)
        _ws = _d_ws   # 别名，指向外层函数
        _rb = _d_rb

        # 1. south_china_sea（南海）
        # 不用 CHN sanction（已被 taiwan_strait 主用），改用 tension 保证正交性
        _scs_chn = _ws([(_m("CHN"), 0.65), (_t("CHN"), 0.35)])
        _scs_ext = _ws([(_t("USA"), 0.55), (_t("JPN"), 0.45)])
        _scs_twn = _t("TWN")
        _scs_val = None
        if _scs_chn is not None or _scs_ext is not None:
            _scs_wmean = _ws([(_scs_chn, 0.55), (_scs_ext, 0.30), (_scs_twn, 0.15)])
            _scs_maxv  = max(v for v in [_scs_chn, _scs_ext] if v is not None)
            _scs_val   = round(0.6 * _scs_maxv + 0.4 * (_scs_wmean or 0), 1)
        _used_scs = [c for c, v in [("CHN", _scs_chn), ("TWN", _scs_twn),
                                     ("USA", _t("USA")), ("JPN", _t("JPN"))] if v is not None]
        _derived_dims["south_china_sea"] = {
            "value": _scs_val, "confidence": round(len(_used_scs) / 7 * 0.50, 2),
            "missing": ["VNM", "PHL", "IDN"],
            "note": "CHN maritime+tension (excl sanction for orthogonality) + USA/JPN external response"
        }

        # 2. korean_peninsula（朝鲜半岛）
        # PRK 分数来自稀疏媒体报道，尖刺分布，置信度受限；JPN 是最可靠的响应代理
        _kp_prk = _ws([(_m("PRK"), 0.50), (_t("PRK"), 0.50)])
        _kp_jpn = _ws([(_t("JPN"), 0.65), (_m("JPN"), 0.35)])
        _kp_usa = _ws([(_t("USA"), 0.55), (_m("USA"), 0.45)])
        _kp_val = _rb([_kp_prk, _kp_jpn, _kp_usa], weights=[0.50, 0.30, 0.20])
        _used_kp = [c for c, v in [("PRK", _kp_prk), ("JPN", _kp_jpn), ("USA", _kp_usa)] if v is not None]
        _derived_dims["korean_peninsula"] = {
            "value": _kp_val, "confidence": round(len(_used_kp) / 4 * 0.65, 2),
            "missing": ["KOR"],
            "note": "PRK launch activity + JPN regional response + USA forward presence (KOR absent from watch list)"
        }

        # 3. india_pacific（印太）
        # 排除 CHN military/sanction（避免与 us_china_strategic 共线），改用 cultural_friction
        _ip_chn = _ws([(_t("CHN"), 0.55), (_cf("CHN"), 0.45)])
        _ip_ind = _ws([(_m("IND"), 0.45), (_t("IND"), 0.40), (_s("IND"), 0.15)])
        _ip_jpn = _ws([(_t("JPN"), 0.70), (_s("JPN"), 0.30)])
        _ip_pak = _ws([(_m("PAK"), 0.50), (_t("PAK"), 0.35), (_r("PAK"), 0.15)])
        _ip_main = [v for v in [_ip_chn, _ip_ind, _ip_jpn] if v is not None]
        _ip_val = None
        if _ip_main:
            _ip_wmean = _ws([(_ip_chn, 0.30), (_ip_ind, 0.35), (_ip_jpn, 0.20), (_ip_pak, 0.15)])
            _ip_val = round(0.6 * max(_ip_main) + 0.4 * (_ip_wmean or 0), 1)
        _used_ip = [c for c, v in [("CHN", _ip_chn), ("IND", _ip_ind), ("JPN", _ip_jpn), ("PAK", _ip_pak)] if v is not None]
        _derived_dims["india_pacific"] = {
            "value": _ip_val, "confidence": round(len(_used_ip) / 6 * 0.70, 2),
            "missing": ["AUS", "IDN"],
            "note": "CHN diplomatic/cultural pressure (NOT military, orthogonal to us_china) + IND border + JPN East Sea + PAK South Asia"
        }

        # 4. global_south（全球南方）
        # 注意：实际度量的是新兴市场政治不稳定性，不是全球南方外交团结
        _gs_ind = _ws([(_so("IND"), 0.50), (_r("IND"), 0.30), (_p("IND"), 0.20)])
        _gs_nga = _ws([(_re("NGA"), 0.40), (_r("NGA"), 0.35), (_so("NGA"), 0.25)])
        _gs_egy = _ws([(_r("EGY"), 0.45), (_so("EGY"), 0.35), (_p("EGY"), 0.20)])
        _gs_tur = _ws([(_so("TUR"), 0.40), (_t("TUR"), 0.35), (_r("TUR"), 0.25)])
        _gs_vals = [v for v in [_gs_ind, _gs_nga, _gs_egy, _gs_tur] if v is not None]
        _gs_val = round(sum(_gs_vals) / len(_gs_vals), 1) if _gs_vals else None
        _used_gs = [c for c, v in [("IND", _gs_ind), ("NGA", _gs_nga), ("EGY", _gs_egy), ("TUR", _gs_tur)] if v is not None]
        _derived_dims["global_south"] = {
            "value": _gs_val, "confidence": round(len(_used_gs) / 4 * 0.60, 2),
            "missing": ["BRA", "ZAF", "IDN"],
            "note": "Emerging market political instability (IND/NGA/EGY/TUR internal stress). NOT Global South diplomatic solidarity."
        }

        logger.info(
            "[GRV] 推导维度: scs=%.1f kp=%.1f ip=%.1f gs=%.1f",
            _derived_dims["south_china_sea"]["value"] or 0,
            _derived_dims["korean_peninsula"]["value"] or 0,
            _derived_dims["india_pacific"]["value"] or 0,
            _derived_dims["global_south"]["value"] or 0,
        )
    except Exception as _de:
        logger.warning(f"[GRV] 推导维度计算失败（非阻断）: {_de}")

    grv = {
        "_schema_version":    "1.0",
        "taiwan_strait":      taiwan_strait,
        "us_china_strategic": us_china_strategic,
        "russia_europe":      russia_europe,
        "middle_east_energy": middle_east_energy,
        "global_composite":   global_composite,
        "climate_risk":       climate_risk,
        "disaster_risk":      disaster_risk,
        "sanctions_risk":     sanctions_risk,
        "seismic_risk":       seismic_risk,
        "energy_grid_risk":   energy_grid_risk,
        "japan_monetary":     japan_monetary,
        "social_stress":      social_stress_val,      # R09：社会情绪压力（gdelt_scores 聚合均值）
        "cultural_friction":  cultural_friction_val,  # R10：文化摩擦（gdelt_scores 标量）
        # ── 推导维度（无 GPR 数据源，GDELT 国别分数加权聚合，置信度有限）──
        "south_china_sea":    _derived_dims.get("south_china_sea", {}).get("value"),
        "korean_peninsula":   _derived_dims.get("korean_peninsula", {}).get("value"),
        "india_pacific":      _derived_dims.get("india_pacific", {}).get("value"),
        "global_south":       _derived_dims.get("global_south", {}).get("value"),
        # 推导维度元数据（confidence/missing/note）
        "_derived_meta": {k: {mk: mv for mk, mv in v.items() if mk != "value"}
                          for k, v in _derived_dims.items()} if _derived_dims else {},
        "updated":            now,
        "gdelt_updated":      gdelt_updated,
        "gpr_twn_raw":        gpr_twn_raw,
        "gpr_twn_date":       gpr_twn_date,
        "source_quality":     source_quality,
    }

    logger.info(
        f"GRV 计算完成 | source={source_quality} | "
        f"taiwan={taiwan_strait} us_china={us_china_strategic} "
        f"russia={russia_europe} mideast={middle_east_energy}"
    )
    return grv


def save_grv(grv: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = GRV_OUTPUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(grv, f, ensure_ascii=False, indent=2)
    os.replace(tmp, GRV_OUTPUT)


def append_grv_history(grv: dict) -> None:
    """追加一条 GRV 快照到 grv_history.jsonl（每行一个 JSON 对象）。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    today = grv.get("updated", "")[:10]  # YYYY-MM-DD
    if today and os.path.exists(GRV_HISTORY):
        try:
            with open(GRV_HISTORY, "rb") as f:
                # 读最后一行（最新记录）判断日期是否重复
                f.seek(0, 2)
                size = f.tell()
                if size > 0:
                    end = size - 1
                    while end > 0 and f.read(1) == b"\n":
                        end -= 1
                        f.seek(end)
                    f.seek(max(end - 2048, 0))
                    last_line = f.read().decode("utf-8", errors="ignore").rstrip().rsplit("\n", 1)[-1]
                    last_record = json.loads(last_line)
                    if last_record.get("updated", "")[:10] == today:
                        _get_logger().info(f"[GRV] grv_history 当日记录已存在（{today}），跳过追加")
                        return
        except Exception:
            pass
    record = {k: grv[k] for k in grv}
    line = json.dumps(record, ensure_ascii=False) + "\n"
    tmp = GRV_HISTORY + ".tmp"
    try:
        # 原子追加：先把现有内容 + 新行写入 .tmp，再 replace
        # 与 save_grv 保持一致，防止进程崩溃时留下半行 JSON
        existing = b""
        if os.path.exists(GRV_HISTORY):
            with open(GRV_HISTORY, "rb") as f:
                existing = f.read()
        with open(tmp, "wb") as f:
            f.write(existing)
            f.write(line.encode("utf-8"))
        os.replace(tmp, GRV_HISTORY)
    except Exception as _e:
        # 回退到直接追加，至少不丢数据
        _get_logger().warning(f"[GRV] grv_history 原子写失败，回退直接追加: {_e}")
        with open(GRV_HISTORY, "a", encoding="utf-8") as f:
            f.write(line)


def main():
    logger = _get_logger()
    logger.info("geo_risk_vector.py 启动")

    # B线：写入前先读旧值，用于 delta 计算
    prev_grv = {}
    try:
        if os.path.exists(GRV_OUTPUT):
            with open(GRV_OUTPUT, encoding="utf-8") as _f:
                prev_grv = json.load(_f)
    except Exception:
        pass

    grv = compute_grv()
    save_grv(grv)
    append_grv_history(grv)
    print(f"[GRV] 已写入 {GRV_OUTPUT}")
    print(f"  台海:      {grv['taiwan_strait']}")
    print(f"  中美战略:  {grv['us_china_strategic']}")
    print(f"  俄欧:      {grv['russia_europe']}")
    print(f"  中东能源:  {grv['middle_east_energy']}")
    print(f"  全球综合:  {grv['global_composite']}")
    print(f"  气候风险:  {grv['climate_risk']}")
    print(f"  灾害风险:  {grv['disaster_risk']}")
    print(f"  制裁风险:  {grv['sanctions_risk']}")
    print(f"  地震压力:  {grv['seismic_risk']}")
    print(f"  能源电网:  {grv['energy_grid_risk']}")
    print(f"  日元压力:  {grv['japan_monetary']}")
    print(f"  社会压力:  {grv['social_stress']}")
    print(f"  文化摩擦:  {grv['cultural_friction']}")
    print(f"  数据质量:  {grv['source_quality']}")
    logger.info(f"geo_risk_vector.py 完成，写入 {GRV_OUTPUT}")

    # B线：写完 GRV 后触发阈值检测（非阻断）
    try:
        from grv_threshold import check_and_trigger
        check_and_trigger(grv, prev_grv)
    except Exception as _e:
        print(f"  [B线] 非阻断失败: {_e}")


if __name__ == "__main__":
    main()
