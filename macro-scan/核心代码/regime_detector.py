"""
体制检测模块 v2 — 滚动Z-score版
=============================================
基于5年滚动窗口的动态阈值，自适应不同时代宏观环境。

改进（对比v1绝对阈值）：
- VIX/BAA/T10Y2Y用滚动Z-score替代固定阈值
- 持续期条件：需连续两季度触发才报压力
- NBER衰退期作硬锚，最低STRESS，Z-score极端才CRISIS
- 历史季度数据持久化到JSON，重启不丢失

调用方式：
  from regime_detector import detect_regime, get_coefficients, get_regime_info
  regime, stress_signals = detect_regime(indicators)
  coeffs = get_coefficients(regime)
  info = get_regime_info()  # 含详细信号值和Z-score
"""

import json
import math
import os
from datetime import date
from typing import Optional

# ── 依赖 ──────────────────────────────────────────────────────────────────────
try:
    from fredapi import Fred
except ImportError:
    raise ImportError("请先安装: pip install fredapi")

from optim_config import FRED_API_KEY

# ── Z-score参数 ────────────────────────────────────────────────────────────────
ZSCORE_WINDOW = 20         # 滚动窗口：20个季度≈5年
ZSCORE_WARN = 1.0         # Z-score > 1.0 → STRESS信号
ZSCORE_CRISIS = 1.5       # Z-score > 1.5 → CRISIS（NBER衰退期内）
UNRATE_DELTA_WARN = 0.5   # 失业率3个月变化超0.5pp → 信号
PERSISTENCE = 2           # 需连续2季度触发才报STRESS（非NBER期）

# ── NBER衰退期（硬锚）──────────────────────────────────────────────────────────
# CFG-8: 此列表仅用于历史标注（回测和硬锚判断），不实时联网查询。
# NBER 宣布新衰退后须手动追加季度，最后更新：2026-06-29（截止 2020Q2）
# 下次需更新时参考：https://www.nber.org/research/business-cycle-dating
NBER_RECESSIONS = [
    "2001Q1", "2001Q2", "2001Q3", "2001Q4",
    "2007Q4", "2008Q1", "2008Q2", "2008Q3", "2008Q4",
    "2009Q1", "2009Q2", "2009Q3", "2009Q4",
    "2020Q1", "2020Q2"
]

# 陈旧检测：若最后条目超过3年未更新，启动时发出 UserWarning 提醒手动追加
_last_nber_year = int(NBER_RECESSIONS[-1][:4])
import datetime as _nber_dt
if _nber_dt.date.today().year - _last_nber_year > 3:
    import warnings as _nber_warnings
    _nber_warnings.warn(
        f"NBER_RECESSIONS 最后条目为 {NBER_RECESSIONS[-1]}，已超过3年未更新。"
        " 若 NBER 已宣布新衰退，请在 regime_detector.py 手动追加季度。"
        " 参考: https://www.nber.org/research/business-cycle-dating",
        stacklevel=2,
    )
del _last_nber_year, _nber_dt

# ── 体制系数（双体制 + crisis 专属）─────────────────────────────────────────
REGIME_COEFFICIENTS = {
    "normal": {
        "rate_gdp_impact":       -0.30,
        "inflation_persistence":  0.65,
        "credit_multiplier":      1.2,
        "recession_threshold":   -0.5,
        "unemployment_lag":      6,
        "description": "常态体制（滚动Z-score校准，自适应大缓和/后危机时代）",
    },
    "stress": {
        "rate_gdp_impact":       -0.80,
        "inflation_persistence":  0.80,
        "credit_multiplier":      2.5,
        "recession_threshold":   -0.2,
        "unemployment_lag":       3,
        "description": "压力体制（滚动Z-score校准，危机期自动切换）",
    },
    "crisis": {
        # CFG-5: 危机体制专属系数，比 stress 更极端
        # 触发条件：NBER 衰退期 + VIX/BAA Z-score > 1.5
        "rate_gdp_impact":       -1.50,   # 加息对GDP冲击翻倍（参考2008/2020）
        "inflation_persistence":  0.90,   # 通胀粘性更强（供给链断裂叠加需求崩塌）
        "credit_multiplier":      4.0,    # 信用收缩乘数（银行惜贷+流动性危机）
        "recession_threshold":   -0.1,    # 轻微负增长即触发衰退判定
        "unemployment_lag":       2,      # 失业率更快上升（参考2020Q1→Q2跳升）
        "description": "危机体制（NBER衰退+Z-score极端，尾部风险最大化）",
    },
}

# ── 季度数据持久化路径 ────────────────────────────────────────────────────────
_BASE_DIR = os.environ.get(
    "OPENCLAW_WORKSPACE",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_REGIME_CACHE = os.path.join(_BASE_DIR, "data", "regime_history.json")

# ── 历史状态（运行时内存）─────────────────────────────────────────────────────
_history: list[dict] = []        # 每条：{quarter, vix, baa10y, t10y2y, unrate_3m, vix_z, baa_z, t10_z}
_prev_regime: Optional[str] = None

# ── 辅助函数 ─────────────────────────────────────────────────────────────────
MONTH_MAP = {1: "01", 2: "04", 3: "07", 4: "10"}

def current_quarter() -> str:
    """返回今年当前季度字符串，如 '2026Q2'。"""
    m = (date.today().month - 1) // 3 + 1
    return f"{date.today().year}Q{m}"

def _load_history() -> list[dict]:
    """从JSON文件加载历史季度数据。"""
    if os.path.exists(_REGIME_CACHE):
        try:
            with open(_REGIME_CACHE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []

def _save_history(history: list[dict]):
    """保存历史季度数据到JSON（原子写入，防止并发损坏）。"""
    cache_dir = os.path.dirname(_REGIME_CACHE)
    os.makedirs(cache_dir, exist_ok=True)
    tmp = _REGIME_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history[-50:], f, ensure_ascii=False, indent=2)  # 只保留最近50季度
    os.replace(tmp, _REGIME_CACHE)

def _quarter_key(year: int, month: int) -> str:
    """从年/月得到季度字符串。"""
    q = (month - 1) // 3 + 1
    return f"{year}Q{q}"

def _get_unrate_3m() -> Optional[float]:
    """从FRED拉取失业率3个月变化（当前季度末 vs 3个月前）。"""
    if not FRED_API_KEY:
        return None
    try:
        fred = Fred(api_key=FRED_API_KEY)
        today = date.today()
        q = (today.month - 1) // 3 + 1
        cur_month = f"{today.year}-{MONTH_MAP[q]}"
        m = today.month - 3
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        prev_month = f"{y}-{m:02d}"
        s = fred.get_series("UNRATE", observation_start=prev_month,
                            observation_end=cur_month)
        if s is None or len(s) < 2:
            return None
        vals = [float(v) for v in s.values if not math.isnan(v)]
        if len(vals) >= 2:
            return round(vals[-1] - vals[0], 3)
        return None
    except Exception:
        return None

def _compute_zscore(current: float, history: list[float]) -> Optional[float]:
    """计算滚动Z-score。CFG-7: std 加下限保护，防止冷启动期 std≈0 时 Z-score 爆炸。"""
    if current is None or len(history) < 5:
        return None
    n = len(history)
    mu = sum(history) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in history) / (n - 1))
    # 冷启动保护：std 不得低于均值的 5%（或绝对值 0.1），防止极小分母放大噪声
    sd_floor = max(abs(mu) * 0.05, 0.1)
    sd = max(sd, sd_floor)
    return (current - mu) / sd

def _rolling_z_from_history(history: list[dict], key: str) -> list[float]:
    """从历史记录提取指标值列表（用于Z-score计算）。"""
    return [h[key] for h in history if h.get(key) is not None]

# ── 核心检测逻辑 ──────────────────────────────────────────────────────────────
def _detect(row: dict, prev_row: Optional[dict]) -> str:
    """给定当前季度指标和上一季度，判断体制。"""
    # NBER衰退期 → 硬锚
    if row["quarter"] in NBER_RECESSIONS:
        return "crisis" if (row.get("vix_z", -999) > ZSCORE_CRISIS or
                           row.get("baa_z", -999) > ZSCORE_CRISIS) else "stress"

    # 非衰退期：持续期条件
    def has_stress(r: dict) -> bool:
        """当前/前期行是否触发任意一项压力阈值（VIX/信用利差/收益率曲线/失业率跳升）。"""
        if r is None: return False
        return ((r.get("vix_z") or -999) > ZSCORE_WARN or
                (r.get("baa_z") or -999) > ZSCORE_WARN or
                (r.get("t10_z") or 999) < -ZSCORE_WARN or
                (r.get("unrate_3m") or 0) > UNRATE_DELTA_WARN)

    if has_stress(row) and has_stress(prev_row):
        return "stress"
    return "normal"

# ── 对外接口 ──────────────────────────────────────────────────────────────────
def detect_regime(indicators: dict) -> tuple[str, int]:
    """
    根据当前指标判断体制（支持v2 Z-score逻辑）。

    Parameters
    ----------
    indicators : 当前指标快照
                 必须包含：VIXCLS{value}, BAMLH0A0HYM2{value}, T10Y2Y{value}, UNRATE{value}
                 可选包含：DRCCLACBS{value}（信用卡违约率）

    Returns
    -------
    (regime, stress_signals)
      regime        : "normal" | "stress" | "crisis"（注意：crisis对应历史双体制的stress）
                     注意：返回 "crisis" 会自动映射到蒙特卡洛的 stress 系数
      stress_signals: Z-score触发计数（满分4：vix/baa/t10/unrate）
    """
    global _prev_regime

    history = _load_history()

    # 从indicators提取当前季度值
    vix = (indicators.get("VIXCLS") or indicators.get("VIX") or {}).get("value")
    baa = indicators.get("BAMLH0A0HYM2", {}).get("value")   # 年化利率差(bp)，转%
    t10y2y = indicators.get("T10Y2Y", {}).get("value")
    unrate = indicators.get("UNRATE", {}).get("value")
    # 可选：信用卡违约率
    default_rate = indicators.get("DRCCLACBS", {}).get("value")

    # BAA从bp转%，FRED是年化利率差(Percent)
    # 注意：BAMLH0A0HYM2 本身就是Percent单位（如3.5表示3.5%）

    # 当前季度键
    q = current_quarter()

    # 构建当前行
    row = {
        "quarter": q,
        "vix": vix,
        "baa10y": baa,      # BAMLH0A0HYM2即BAA-10Y利差（%）
        "t10y2y": t10y2y,   # 10Y-2Y利差（%）
        "unrate_3m": _get_unrate_3m(),  # 实时从FRED算
    }

    # 计算Z-score（如果历史足够）
    if history:
        vix_hist = _rolling_z_from_history(history, "vix")
        baa_hist = _rolling_z_from_history(history, "baa10y")
        t10_hist = _rolling_z_from_history(history, "t10y2y")
        row["vix_z"] = _compute_zscore(vix, vix_hist)
        row["baa_z"] = _compute_zscore(baa, baa_hist)
        row["t10_z"] = _compute_zscore(t10y2y, t10_hist)
    else:
        row["vix_z"] = None
        row["baa_z"] = None
        row["t10_z"] = None

    prev_row = history[-1] if history else None

    # 检测
    raw_regime = _detect(row, prev_row)

    # 压力信号计数（4个金融信号 + 3个通胀信号 = 最高7）
    signals = 0
    # --- 金融市场信号 ---
    if row.get("vix_z") is not None and row["vix_z"] > ZSCORE_WARN: signals += 1
    if row.get("baa_z") is not None and row["baa_z"] > ZSCORE_WARN: signals += 1
    if row.get("t10_z") is not None and row["t10_z"] < -ZSCORE_WARN: signals += 1
    if row.get("unrate_3m") is not None and row["unrate_3m"] > UNRATE_DELTA_WARN: signals += 1
    # --- 通胀/能源信号（绝对阈值，历史均值的1.5倍附近）---
    ppi = indicators.get("PPIACO", {}).get("value")
    cpi = indicators.get("CPIAUCSL", {}).get("value")
    oil = indicators.get("DCOILWTICO", {}).get("value")
    if ppi is not None and ppi > 7.0: signals += 1   # PPI同比>7%
    if cpi is not None and cpi > 3.5: signals += 1   # CPI同比>3.5%
    if oil is not None and oil > 90.0: signals += 1  # WTI原油>90美元

    # GSCPI（全球供应链压力指数，来自 _crucix）
    # CFG-4: 纳入 signals 计数，>1.5 标准差为供应链压力信号
    _gscpi = (indicators.get("_crucix") or {}).get("gscpi") or {}
    gscpi_val = _gscpi.get("value") if isinstance(_gscpi, dict) else None
    if gscpi_val is not None and gscpi_val > 1.5:
        signals += 1   # 供应链压力极高（2021-2022类危机前兆）

    # 更新历史
    # 避免同一季度重复写入
    if not history or history[-1]["quarter"] != q:
        history.append(row)
        _save_history(history)

    _prev_regime = raw_regime
    return raw_regime, signals

def get_coefficients(regime: str) -> dict:
    """返回指定体制的系数字典。
    CFG-5: crisis 现有专属条目，不再静默借用 stress 系数。
    """
    return REGIME_COEFFICIENTS.get(regime, REGIME_COEFFICIENTS["normal"])

def get_regime_info(indicators: dict) -> dict:
    """
    返回当前体制的详细信息（含Z-score、信号触发情况）。
    用于日志和调试。
    """
    regime, signals = detect_regime(indicators)
    history = _load_history()
    row = history[-1] if history else {}

    # 信号详情
    signal_detail = {
        "vix_z": row.get("vix_z"),
        "baa_z": row.get("baa_z"),
        "t10_z": row.get("t10_z"),
        "unrate_3m": row.get("unrate_3m"),
        "vix_abs": row.get("vix"),
        "baa_abs": row.get("baa10y"),
        "t10y2y_abs": row.get("t10y2y"),
    }

    # 滚动窗口信息
    n = len(history)
    window_desc = f"基于最近{min(n, ZSCORE_WINDOW)}季度"

    return {
        "regime": regime,
        "stress_signals": signals,
        "max_signals": 8,  # 4个金融信号 + 3个通胀信号 + 1个GSCPI供应链信号
        "signals_detail": signal_detail,
        "data_window": window_desc,
        "history_quarters": n,
        "is_nber_recession": current_quarter() in NBER_RECESSIONS,
        "coefficients": get_coefficients(regime),
        "gscpi_warn": ((indicators.get("_crucix") or {}).get("gscpi") or {}).get("value", 0) > 1.5,
        "gscpi_value": ((indicators.get("_crucix") or {}).get("gscpi") or {}).get("value"),
    }

def get_current_zscores() -> dict:
    """返回当前最新Z-score值（供外部日志使用）。"""
    history = _load_history()
    if not history:
        return {}
    row = history[-1]
    return {
        "quarter": row.get("quarter"),
        "vix": row.get("vix"),
        "vix_z": row.get("vix_z"),
        "baa10y": row.get("baa10y"),
        "baa_z": row.get("baa_z"),
        "t10y2y": row.get("t10y2y"),
        "t10_z": row.get("t10_z"),
        "unrate_3m": row.get("unrate_3m"),
    }