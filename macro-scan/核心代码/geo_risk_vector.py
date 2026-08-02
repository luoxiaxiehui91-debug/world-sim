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
FRED_DIR     = os.path.join(DATA_DIR, "fred_history")
GRV_OUTPUT   = os.path.join(DATA_DIR, "grv_latest.json")
GRV_HISTORY  = os.path.join(DATA_DIR, "grv_history.jsonl")

# GPR 系列历史分位数（滚动10年 P10-P95 归一化）
# p95 代替 p90，避免极端事件（如2026-03关税战峰值331）把天花板压得过低导致长期触顶
_GPR_FALLBACK_RANGE = {"p10": 50, "p95": 220}  # 历史 GPR 大致区间

# GDELT 原始分归一化基准（gdelt_history.jsonl 实测 p95，2026-05-21~2026-07-08，211条）
# 公式：score_norm = min(raw / p95_ref * 100, 100)
# 0 基点保持物理含义（无事件=0），p95 作上限而非 p10-p95 区间，避免负值
_GDELT_P95 = {
    "russia_europe": 1.42,   # RUS+DEU+UKR 组合
    "taiwan_strait": 0.65,   # TWN+CHN 组合
    "us_china":      9.85,   # USA+CHN 组合
    "mideast":       2.50,   # IRN+SAU+ISR 组合
}

# 持续冲突 floor：news.db 确认冲突仍在进行时对应维度的 GRV 下限
# 防止 GPR 指数因媒体疲劳（战争常态化）导致维度虚低
_CONFLICT_FLOOR = {
    "russia_europe": 35.0,
}
_CONFLICT_FLOOR_MIN_ARTICLES = 5  # 触发 floor 所需的近30天冲突文章数


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
        import sqlite3 as _sql
        db_path = os.path.join(DATA_DIR, "news.db")
        if not os.path.exists(db_path):
            return value
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
        conn = _sql.connect(db_path)
        (count,) = conn.execute("""
            SELECT COUNT(DISTINCT a.id)
            FROM articles a
            JOIN article_categories ac ON a.id = ac.article_id
            WHERE ac.category IN ('geopolitics', '地缘升级')
              AND (a.country_tag LIKE '%RUS%' OR a.country_tag LIKE '%UKR%'
                   OR a.title LIKE '%俄%' OR a.title LIKE '%乌克兰%'
                   OR a.title LIKE '%Russia%' OR a.title LIKE '%Ukraine%')
              AND a.published_at > ?
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
    logger = _get_logger()
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
    russia_europe      = _blend(gdelt_russia_n,  gpr_rus,    0.4, 0.6)
    middle_east_energy = _blend(gdelt_mideast_n, None,       1.0, 0.0)  # CFG-1: 纯GDELT，无中东专项GPR

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

    now = datetime.datetime.now().isoformat(timespec="seconds")

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
    # 来源：fetch_energy.py（UK Carbon Intensity API → grid_carbon_risk，0–100）。
    # 高值 = 电网更脏（化石占比高）/ 能源外生压力更大，喂 GRV 的 energy/grid 维度。
    energy_grid_risk = None
    try:
        en_path = os.path.join(DATA_DIR, "energy_risk.json")
        if os.path.exists(en_path):
            with open(en_path, encoding="utf-8") as _en:
                _end = json.load(_en)
            if _end.get("status") in ("ok", "partial"):
                g = _end.get("grid_carbon_risk")
                if isinstance(g, (int, float)):
                    energy_grid_risk = round(float(g), 1)
                else:
                    logger.warning("[GRV] grid_carbon_risk 缺失/类型异常，留空")
            else:
                logger.info("[GRV] 能源数据 status=%s，energy_grid_risk 留空", _end.get("status"))
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
                cultural_friction_val = round(float(cf), 1)
    except Exception as _e:
        logger.warning(f"[GRV] social_stress/cultural_friction 读取失败（非阻断）: {_e}")

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
