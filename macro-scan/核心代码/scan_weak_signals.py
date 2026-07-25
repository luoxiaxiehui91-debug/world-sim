"""
模块03（v2）：弱信号扫描器
修复：
  - 路径改用 config.py，推送改用 push_utils
  - 新增 Crucix API 集成（通过 Gateway，与 neodata skill 同一模式）
  - 预警去重：同一指标同一天只记录一次
  - FRED 调用加速：一次性拉所有历史，减少 API 轮次
  - Z-score 计算缺数据时优雅降级（不报错）
"""
import csv
import io
import json
import math
import os
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

try:
    from fredapi import Fred
    import requests
except ImportError:
    raise ImportError("请先安装: pip install fredapi requests")

from optim_config import (WEAK_SIGNAL_LOG, FRED_API_KEY,
                    ZSCORE_WARN_THRESHOLD, ZSCORE_ALERT_THRESHOLD,
                    NEWS_FREQ_WARN_RATIO, NEWS_FREQ_ALERT_RATIO,
                    AUTH_GATEWAY_PORT, CRUCIX_REMOTE_URL)
from alert_config import ALERT_KEYWORDS, _WATCH_COUNTRIES, _ACTOR_REL_ETH, _ACTOR_REGIME, _ACTOR_CULTURE

# ── 监控指标 ──────────────────────────────────────────────────────────────────
# (FRED代码, 中文名称, 触发方向: "up"=偏高危险 / "down"=偏低危险 / "both", [Z-score窗口=24])
# 日频数据（VIX/EPU/DCOILWTICO等）建议使用更长窗口（60-90）以避免噪声触发
INDICATORS = [
    # 美国
    ("FEDFUNDS",        "联邦基金利率",          "up"),
    ("DGS10",           "10年期美债收益率",       "both"),
    ("T10Y2Y",          "收益率曲线(10Y-2Y)",     "down"),
    ("BAMLH0A0HYM2",    "高收益债利差(美国)",      "up"),
    ("BAMLHE00EHY0EY",  "高收益债利差(欧洲)",      "up",  60),  # EU HY spread
    ("BAMLEMHBHYCRPIOAS","高收益债利差(新兴市场)",  "up",  60),  # EM HY spread
    ("VIXCLS",          "VIX恐慌指数",            "up",  60),  # 日频，60日窗口
    ("UNRATE",          "美国失业率",             "up"),
    ("ICSA",            "初请失业金",             "up"),
    ("CPIAUCSL",        "美国CPI",               "up"),
    ("PPIACO",          "美国PPI",               "up"),
    ("DRCCLACBS",       "信用卡违约率",           "up"),
    ("INDPRO",          "工业生产指数",           "down"),
    ("UMCSENT",         "消费者信心",             "down"),
    ("HOUST",           "新屋开工",              "down"),
    ("DCOILWTICO",      "WTI原油",               "up",  60),  # 日频，60日窗口
    # 政策不确定性（Baker-Bloom-Davis EPU，日频）
    ("USEPUINDXD",      "经济政策不确定性(EPU)",  "up",  90),  # 90日窗口，历史均值~100，危机峰值250+
    # 中国（FRED 有限，主要用 NeoData 补充）
    ("XTIMVA01CNM657S", "中国出口额",             "down"),
    # 日本/汇率（套利平仓风险监测）
    ("DEXJPUS",         "美元/日元汇率",          "both"),   # 极高=套利堆积; 急跌=套利平仓
    ("IRLTLT01JPM156N", "日本10Y国债收益率",       "up"),     # 上行=BOJ政策转向→套利成本上升
    # 银行信贷标准（SLOOS，季度；正值=收紧，高于历史均值为压力信号）
    ("DRTSCIS",         "SLOOS贷款标准(工商业)",  "up"),     # Senior Loan Officer Survey: C&I loans
]

# 新闻关键词、GDELT Actor 类型代码、关注国家 — 已迁至 alert_config.py


# ── FRED 数据获取 ─────────────────────────────────────────────────────────────

def _load_local_history(series_id: str) -> list[float] | None:
    """
    从 data/fred_history/{series_id}.csv 加载完整历史值列表（时间升序）。
    返回 None 表示文件不存在或数据点不足 30 条。
    """
    try:
        import pandas as pd
        from optim_config import DATA_DIR
        path = os.path.join(DATA_DIR, "fred_history", f"{series_id}.csv")
        if not os.path.exists(path):
            return None
        df = pd.read_csv(path).dropna(subset=["value"]).sort_values("date")
        vals = df["value"].tolist()
        return vals if len(vals) >= 30 else None
    except Exception:
        return None


def _load_china_local_history(indicator_id: str, min_points: int = 20) -> list[float] | None:
    """
    从 data/china_history/{indicator_id}.csv 加载历史值列表（时间升序）。
    返回 None 表示文件不存在或数据点不足 min_points 条。
    """
    try:
        import pandas as pd
        from optim_config import DATA_DIR
        path = os.path.join(DATA_DIR, "china_history", f"{indicator_id}.csv")
        if not os.path.exists(path):
            return None
        df = pd.read_csv(path).dropna(subset=["value"]).sort_values("date")
        vals = df["value"].tolist()
        return vals if len(vals) >= min_points else None
    except Exception:
        return None


def _long_window(n: int, default: int) -> int:
    """
    根据本地历史数据点数自动选择 Z-score 基线窗口。
    - 日频（n>5000）：1260 交易日 ≈ 5 年
    - 月频（n>100）：120 个月 = 10 年
    - 季频（n<=100）：40 个季度 = 10 年
    最终不低于原始默认窗口。
    """
    if n > 5000:
        w = 1260
    elif n > 100:
        w = 120
    else:
        w = 40
    return max(w, default)


def scan_fred(fred: "Fred") -> list[dict]:
    """扫描所有 FRED 指标，计算 Z-score，触发阈值时生成预警记录。

    数据优先级：本地历史 CSV（长窗口） → FRED API 拉 800 天（短窗口）。
    每个指标休眠 0.2s 避免 FRED API 限速（120次/分钟）。
    返回 alerts 列表，每条含 date/source/indicator/current/z_score/direction/level。
    """
    alerts = []
    today = date.today().isoformat()
    short_start = (date.today() - timedelta(days=800)).isoformat()
    recent_start = (date.today() - timedelta(days=14)).isoformat()

    for series_id, name, direction, *extra in INDICATORS:
        zscore_window = extra[0] if extra else 24
        try:
            hist = _load_local_history(series_id)
            if hist and len(hist) >= zscore_window + 10:
                # 本地历史足够：只取最近 14 天获取当前最新值
                s_latest = fred.get_series(series_id, observation_start=recent_start)
                if s_latest is not None and not s_latest.empty:
                    latest = [float(v) for v in s_latest.dropna().values]
                    values = hist + latest
                else:
                    values = hist
                zscore_window = _long_window(len(hist), zscore_window)
            else:
                # 回退：从 FRED 拉 800 天
                s = fred.get_series(series_id, observation_start=short_start)
                if s is None or len(s) < 6:
                    continue
                values = [float(v) for v in s.values if not math.isnan(v)]
        except Exception:
            continue

        z = _zscore(values, window=zscore_window)
        if z is None:
            continue

        if not _triggered(z, direction):
            continue

        level = "[警报]" if abs(z) >= ZSCORE_ALERT_THRESHOLD else "[注意]"
        alert = {
            "date": today,
            "source": "FRED",
            "indicator": name,
            "series_id": series_id,
            "current": round(values[-1], 3),
            "z_score": round(z, 2),
            "direction": "偏高" if z > 0 else "偏低",
            "level": level,
        }
        alerts.append(alert)
        print(f"  {level} {name}: 值={values[-1]:.2f}, Z={z:.2f}  (基线窗口={zscore_window})")

        time.sleep(0.2)  # 避免 FRED API 限速

    return alerts


def _zscore(values: list[float], window: int = 24) -> float | None:
    """基于滑动窗口基线计算 Z-score。

    基线 = values[-(window+1):-1]（最近 window 个历史点，排除最新值）
    返回 None 表示数据不足，返回 0.0 表示 std 近零（常数序列）。
    """
    if len(values) < window + 2:
        return None
    baseline = values[-(window + 1):-1]
    mean = sum(baseline) / len(baseline)
    var = sum((x - mean) ** 2 for x in baseline) / len(baseline)
    std = math.sqrt(var)
    return (values[-1] - mean) / std if std > 1e-9 else 0.0


def _triggered(z: float, direction: str) -> bool:
    """判断 Z-score 是否越过预警阈值（ZSCORE_WARN_THRESHOLD，默认2.0）。"""
    if direction == "up":
        return z >= ZSCORE_WARN_THRESHOLD
    if direction == "down":
        return z <= -ZSCORE_WARN_THRESHOLD
    return abs(z) >= ZSCORE_WARN_THRESHOLD


# ── 中国指标（NeoData）───────────────────────────────────────────────────────

# 中国指标阈值（基于最新值判断，不需要历史序列）
CHINA_THRESHOLDS = {
    # (指标名, 阈值, 方向, 说明)
    "gdp_growth":     (5.0, "down", "GDP增速低于5%"),
    "industrial_output": (5.0, "down", "工业增加值低于5%"),
    "cpi":           (3.0, "up", "CPI高于3%"),
    "ppi":           (-2.0, "down", "PPI通缩低于-2%"),
    "pmi_manufacturing": (50.0, "down", "制造业PMI低于50（收缩）"),
    "pmi_composite":  (50.0, "down", "综合PMI低于50（收缩）"),
    # m2_yoy 已移除：回测F1=0.17，预警效果极差（社融已覆盖该信号）
}

# 查询映射（NeoData自然语言查询）
CHINA_QUERY_MAP = {
    "gdp_growth": "中国GDP增速",
    "industrial_output": "中国工业增加值",
    "cpi": "中国CPI",
    "ppi": "中国PPI",
    "pmi_manufacturing": "中国制造业PMI",
    "pmi_composite": "中国综合PMI",
    # m2_yoy 已移除
}


def fetch_china_indicator_value(query_text: str) -> tuple[float | None, str | None]:
    """从NeoData获取单个中国指标的最新值"""
    try:
        import uuid
        import re
        
        neodata_host = os.environ.get("NEODATA_HOST", "localhost")
        port = AUTH_GATEWAY_PORT
        url = f"http://{neodata_host}:{port}/proxy/api"
        headers = {
            "Content-Type": "application/json",
            "Remote-URL": "https://jprx.m.qq.com/aizone/skillserver/v1/proxy/teamrouter_neodata/query"
        }
        
        payload = {
            "channel": "neodata",
            "sub_channel": "qclaw",
            "query": query_text,
            "request_id": str(uuid.uuid4()),
            "data_type": "api",
        }
        
        resp = requests.post(url, json=payload, headers=headers, timeout=5)
        if resp.status_code != 200:
            return None, None
        
        data = resp.json()
        if not data.get("suc"):
            return None, None
        
        # 解析NeoData返回
        api_data = data.get("data", {}).get("apiData", {})
        api_recall = api_data.get("apiRecall", [])
        
        for item in api_recall:
            content = item.get("content", "")
            if not content:
                continue
            
            # 从content中提取数值
            # NeoData返回格式如 "CPI同比上涨0.1%" 或 "PMI为49.5"
            # 优先匹配百分比或小数（排除日期格式如20260511）
            
            # 匹配百分比（如 0.1%）
            pct_match = re.search(r'([\d.]+)\s*%', content)
            if pct_match:
                try:
                    return float(pct_match.group(1)), content[:100]
                except:
                    pass
            
            # 匹配"为X.X"或"是X.X"格式
            val_match = re.search(r'(?:为|是|等于)\s*([\d.]+)', content)
            if val_match:
                try:
                    v = float(val_match.group(1))
                    # 排除明显是日期的值
                    if v < 10000:  # 合理的指标值范围
                        return v, content[:100]
                except:
                    pass
            
            # 最后匹配普通小数（排除日期格式）
            numbers = re.findall(r'(?<!\d)(\d+\.\d+)(?!\d)', content)
            for num_str in numbers:
                try:
                    v = float(num_str)
                    if v < 10000:  # 排除日期
                        return v, content[:100]
                except:
                    continue
        
        return None, None
    except Exception as e:
        print(f"    [NeoData查询失败] {query_text}: {e}")
        return None, None


def _fetch_china_fred_fallback() -> dict:
    """
    FRED 二级回退：从 FRED OECD 系列获取中国指标。
    返回 {code: value} 字典（仅包含成功获取的值）。
    仅在 NeoData 完全失败时调用。
    """
    _cn_fred = {
        "cpi":             "CHNCPIALLMINMEI",   # CPI Index monthly
        "pmi_manufacturing": "CHNPMIMANMISMEI",  # NBS Manufacturing PMI
    }
    result = {}
    if not FRED_API_KEY:
        return result
    for code, sid in _cn_fred.items():
        try:
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={sid}&api_key={FRED_API_KEY}"
                f"&file_type=json&sort_order=desc&limit=14"
            )
            resp = requests.get(url, timeout=8)
            if resp.status_code != 200:
                continue
            obs = resp.json().get("observations", [])
            valid = [(o["date"], float(o["value"])) for o in obs if o.get("value", ".") not in (".", "")]
            if not valid:
                continue
            if code == "cpi" and len(valid) >= 13:
                # CHNCPIALLMINMEI is an index, compute YoY manually
                _, v_now = valid[0]
                _, v_12m = valid[12]
                if v_12m > 0:
                    result[code] = round((v_now / v_12m - 1) * 100, 2)
            else:
                result[code] = round(valid[0][1], 2)
        except Exception:
            pass
    if result:
        print(f"  [FRED-CN fallback] 获取到: {result}")
    return result


# 中国指标 → 本地历史文件 ID 映射（fetch_china_data.py 生成）
# 有本地历史的指标优先用 Z-score；否则降级为阈值判断
_CHINA_LOCAL_MAP = {
    "gdp_growth":        "gdp_growth",    # WB年度，≈30点，Z-score窗口20
    "cpi":               "cpi_yoy",       # 衍生月频，Z-score窗口60
    "pmi_manufacturing": "pmi_mfg",       # AkShare NBS月频，Z-score窗口60
    "unemployment":      "unemployment",  # WB年度，Z-score窗口20
    "ppi":               "ppi_yoy",       # AkShare NBS月频，Z-score窗口60
    "industrial_output": "industrial_output",  # AkShare NBS月频，Z-score窗口60
}


def scan_china() -> list[dict]:
    """
    扫描中国指标异常。

    检测策略（优先级降序）：
      1. 本地历史（fetch_china_data.py）→ Z-score（与 FRED 指标一致）
      2. NeoData 实时值 → 阈值判断（原有逻辑）
      3. FRED 二级回退 → 阈值判断
    """
    alerts = []
    today = date.today().isoformat()

    # ── 第一步：对有本地历史的指标做 Z-score ──────────────────────────────────
    zscore_covered: set[str] = set()

    for code, local_id in _CHINA_LOCAL_MAP.items():
        if code not in CHINA_THRESHOLDS:
            continue
        hist = _load_china_local_history(local_id)
        if hist is None:
            continue  # 无本地数据，降级到 NeoData/阈值

        # 月频用60期窗口；年度（gdp_growth，通常≤40点）用全部减1
        window = 20 if local_id == "gdp_growth" else 60
        z = _zscore(hist, window=min(window, len(hist) - 2))
        if z is None:
            continue

        _, direction, desc = CHINA_THRESHOLDS[code]
        if not _triggered(z, direction):
            zscore_covered.add(code)  # 已检测，无异常，不重复阈值检测
            continue

        level = "[警报]" if abs(z) >= ZSCORE_ALERT_THRESHOLD else "[注意]"
        alert = {
            "date":      today,
            "source":    "china_history",
            "indicator": CHINA_QUERY_MAP.get(code, code),
            "series_id": code,
            "current":   round(hist[-1], 2),
            "z_score":   round(z, 2),
            "direction": "偏高" if z > 0 else "偏低",
            "level":     level,
            "desc":      desc,
        }
        alerts.append(alert)
        zscore_covered.add(code)
        print(f"    {level} {CHINA_QUERY_MAP.get(code, code)}: 值={hist[-1]:.2f}, Z={z:.2f}  [Z-score]")

    # ── 第二步：NeoData 实时值（仅对 Z-score 未覆盖的指标） ────────────────────
    print("  查询NeoData...")
    neodata_values: dict = {}

    for code, query_text in CHINA_QUERY_MAP.items():
        if code not in CHINA_THRESHOLDS or code in zscore_covered:
            continue
        value, raw_text = fetch_china_indicator_value(query_text)
        if value is not None:
            neodata_values[code] = value

    # FRED 二级回退：当 NeoData 全部失败且仍有未覆盖指标时
    uncovered_remaining = [c for c in CHINA_THRESHOLDS if c not in zscore_covered and c not in neodata_values]
    if uncovered_remaining and not neodata_values:
        print("  NeoData无响应，启动FRED二级回退...")
        neodata_values.update(_fetch_china_fred_fallback())

    # ── 第三步：对 NeoData/FRED 值做阈值判断 ───────────────────────────────────
    for code, value in neodata_values.items():
        if code not in CHINA_THRESHOLDS:
            continue
        threshold, direction, desc = CHINA_THRESHOLDS[code]

        triggered = False
        if direction == "up"   and value >= threshold:
            triggered = True
        elif direction == "down" and value <= threshold:
            triggered = True

        if not triggered:
            continue

        gap      = abs(value - threshold)
        is_alert = gap >= abs(threshold) * 0.1
        level    = "[警报]" if is_alert else "[注意]"
        source   = "NeoData" if code in neodata_values else "FRED"
        alert = {
            "date":      today,
            "source":    source,
            "indicator": CHINA_QUERY_MAP.get(code, code),
            "series_id": code,
            "current":   round(value, 2),
            "threshold": threshold,
            "direction": "高于" if direction == "up" else "低于",
            "level":     level,
            "desc":      desc,
        }
        alerts.append(alert)
        print(f"    {level} {CHINA_QUERY_MAP.get(code, code)}: {value:.2f} ({desc})  [阈值]")

    return alerts


# ── 铜金比率跨市场信号 ────────────────────────────────────────────────────────
def scan_copper_gold_ratio() -> list[dict]:
    """
    铜金比率（Cu/Au）跨市场景气信号。

    铜（工业需求）/ 黄金（避险需求）的比率是领先于股票市场的景气温度计：
      比率上行 → 工业需求旺盛，风险偏好高
      比率下行 → 避险情绪主导，经济预期恶化

    使用 yfinance 获取日频数据（HG=F 铜期货 / GC=F 黄金期货）。
    Z-score 窗口：252 个交易日（约 1 年）。
    阈值：Z < -1.5 → [注意]；Z < -2.5 → [警报]
    """
    today = date.today().isoformat()
    alerts = []

    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np

        copper = yf.download("HG=F", period="2y", interval="1d", progress=False, auto_adjust=True)
        gold   = yf.download("GC=F", period="2y", interval="1d", progress=False, auto_adjust=True)

        if copper.empty or gold.empty:
            print("  [铜金比率] 数据拉取失败（市场休市或网络问题），跳过。")
            return alerts

        c_close = copper["Close"].dropna()
        g_close = gold["Close"].dropna()

        # 对齐到共同日期
        ratio = (c_close / g_close).dropna()
        if len(ratio) < 60:
            print(f"  [铜金比率] 数据点不足（{len(ratio)}），跳过。")
            return alerts

        window = min(252, len(ratio) - 1)
        recent = ratio.iloc[-window:]
        current_ratio = float(ratio.iloc[-1])
        mean_r  = float(recent.mean())
        std_r   = float(recent.std())

        if std_r < 1e-9:
            return alerts

        z = (current_ratio - mean_r) / std_r

        cu_latest = float(c_close.iloc[-1])
        au_latest = float(g_close.iloc[-1])

        print(f"  [铜金比率] Cu={cu_latest:.2f} Au={au_latest:.0f} 比率={current_ratio:.4f} Z={z:.2f}")

        if z < -1.5:
            level = "[警报]" if z < -2.5 else "[注意]"
            pct_from_mean = (current_ratio - mean_r) / mean_r * 100
            alert = {
                "date":      today,
                "source":    "yfinance",
                "indicator": "铜金比率（景气温度计）",
                "series_id": "CUGOLD_RATIO",
                "current":   round(current_ratio, 4),
                "z_score":   round(z, 2),
                "direction": "下行",
                "level":     level,
                "desc":      f"比率偏低 {pct_from_mean:.1f}%，Z={z:.2f}（避险情绪主导）",
            }
            alerts.append(alert)
            print(f"  {level} 铜金比率异常低位：{alert['desc']}")

    except ImportError:
        print("  [铜金比率] yfinance 未安装，跳过。运行: pip install yfinance")
    except Exception as e:
        print(f"  [铜金比率] 扫描失败: {e}")

    return alerts


# ── 日元套利平仓风险扫描 ──────────────────────────────────────────────────────────
def scan_japan_carry_risk(fred: "Fred") -> list[dict]:
    """
    日元套利交易平仓风险检测（基于规则，不用Z-score）。

    三阶段监测：
      1. 套利堆积（风险累积）：USD/JPY > 150 → 套利仓位处于极端水平
      2. 平仓触发信号：30日内USD/JPY跌幅 > 5% → 套利快速平仓
      3. BOJ政策转向：日本10Y国债收益率近3M上行 > 25bp → 利差缩窄触发平仓

    全部条件满足时发出 [警报]；任意一项满足发出 [注意]。
    """
    today = date.today().isoformat()
    alerts = []
    start = (date.today() - timedelta(days=400)).isoformat()

    # 1. 获取 USD/JPY（DEXJPUS：高=日元弱）
    usdjpy_val    = None
    usdjpy_30d_chg = None
    try:
        s = fred.get_series("DEXJPUS", observation_start=start)
        if s is not None and len(s) >= 30:
            vals = [float(v) for v in s.values if not math.isnan(v)]
            if len(vals) >= 22:
                usdjpy_val = vals[-1]
                prev_30d   = vals[-22] if len(vals) >= 22 else vals[0]
                usdjpy_30d_chg = (usdjpy_val - prev_30d) / prev_30d * 100
    except Exception:
        pass

    # 2. 获取日本10Y国债收益率（IRLTLT01JPM156N）
    jgb10y_val    = None
    jgb10y_3m_chg = None
    try:
        s = fred.get_series("IRLTLT01JPM156N", observation_start=start)
        if s is not None and len(s) >= 3:
            vals = [float(v) for v in s.values if not math.isnan(v)]
            if len(vals) >= 3:
                jgb10y_val = vals[-1]
                prev_3m    = vals[-4] if len(vals) >= 4 else vals[0]
                jgb10y_3m_chg = (jgb10y_val - prev_3m) * 100  # 转为bp
    except Exception:
        pass

    # 3. 规则判断
    buildup   = usdjpy_val    is not None and usdjpy_val    > 150
    unwind    = usdjpy_30d_chg is not None and usdjpy_30d_chg < -5.0
    boj_shift = jgb10y_3m_chg is not None and jgb10y_3m_chg > 25

    triggered_conditions = []
    if buildup:
        triggered_conditions.append(f"USD/JPY={usdjpy_val:.1f}（>150，套利仓位极端）")
    if unwind:
        triggered_conditions.append(f"USD/JPY 30日变化={usdjpy_30d_chg:.1f}%（<-5%，平仓信号）")
    if boj_shift:
        triggered_conditions.append(f"JGB 10Y 3M变化=+{jgb10y_3m_chg:.0f}bp（>25bp，BOJ转向）")

    if not triggered_conditions:
        return alerts

    # 三项全中 → 警报；任意一项 → 注意
    is_alert = sum([buildup, unwind, boj_shift]) >= 2
    level    = "[警报]" if is_alert else "[注意]"

    alert = {
        "date": today,
        "source": "FRED",
        "indicator": "日元套利平仓风险",
        "series_id": "DEXJPUS+IRLTLT01JPM156N",
        "current": usdjpy_val or 0.0,
        "details": "；".join(triggered_conditions),
        "direction": "平仓触发" if unwind else "堆积中",
        "level": level,
        "risk_note": (
            "若日银意外大幅加息或VIX>35，全球约4万亿美元套利仓位可能快速平仓，"
            "引发风险资产全面抛售（参考2024-08-05冲击：日经-12%，标普-3%，一日内）"
        ),
    }
    alerts.append(alert)
    print(f"  {level} 日元套利风险：{' | '.join(triggered_conditions)}")
    return alerts


# ── 全球跨资产同步压力检测 ─────────────────────────────────────────────────────
# 各 FRED series 所属"资产类别"（用于聚合判断）
_ASSET_CLASS_MAP = {
    "VIXCLS":             "equity",       # 美股波动率
    "BAMLH0A0HYM2":       "credit_us",    # 美国信用
    "DRCCLACBS":          "credit_us",
    "BAMLHE00EHY0EY":     "credit_eu",    # 欧洲信用
    "BAMLEMHBHYCRPIOAS":  "credit_em",    # 新兴市场信用
    "UNRATE":             "macro",        # 美国宏观
    "ICSA":               "macro",
    "DEXJPUS":            "fx",           # 外汇/套利
    "DCOILWTICO":         "commodity",    # 大宗商品
    "USEPUINDXD":         "policy",       # 政策不确定性
    "DRTSCIS":            "credit_us",    # SLOOS 银行贷款标准
}


def detect_global_stress(all_alerts: list) -> list:
    """
    从已生成的预警列表中检测跨资产类别同步压力。

    当 3+ 个不同资产类别同日触发预警时，视为全局风险规避信号：
      3 类别 → [注意]（跨资产传染初现）
      4+ 类别 → [警报]（全球同步去风险）
    """
    today = date.today().isoformat()

    triggered_classes: set = set()
    triggered_names: list = []
    for a in all_alerts:
        sid = a.get("series_id", "")
        cls = _ASSET_CLASS_MAP.get(sid)
        if cls and a.get("date") == today:
            triggered_classes.add(cls)
            triggered_names.append(a.get("indicator", sid))

    if len(triggered_classes) < 3:
        return []

    n = len(triggered_classes)
    level = "[警报]" if n >= 4 else "[注意]"
    class_labels = {
        "equity": "股权", "credit_us": "美国信用", "credit_eu": "欧洲信用",
        "credit_em": "新兴市场信用", "macro": "宏观就业", "fx": "外汇",
        "commodity": "大宗商品", "policy": "政策不确定性",
    }
    class_str = "、".join(class_labels.get(c, c) for c in sorted(triggered_classes))

    print(f"  {level} 跨资产同步压力：{n} 个类别同时触发（{class_str}）")
    return [{
        "date": today,
        "source": "跨资产分析",
        "indicator": "全球跨资产同步压力",
        "series_id": "CROSS_ASSET_STRESS",
        "current": float(n),
        "level": level,
        "desc": f"{n} 个资产类别同步预警（{class_str}）；涉及: {'; '.join(triggered_names[:6])}",
    }]


# ── GDELT 地缘政治维度扫描 ────────────────────────────────────────────────────
# 有 HTTP_PROXY 环境变量则使用（SAP 企业网络），否则直连（家庭/NAS 环境）
_http_proxy  = os.environ.get("HTTP_PROXY")
_https_proxy = os.environ.get("HTTPS_PROXY")
_GDELT_PROXY = {"http": _http_proxy, "https": _https_proxy} if (_http_proxy or _https_proxy) else None

# CAMEO root code（前2位）→ 维度分类
_CAMEO_MILITARY = {"18", "19", "20"}   # 实际战斗/暴力
_CAMEO_TENSION  = {"13", "15", "16"}   # 威胁/武力展示/断绝关系
_CAMEO_PROTEST  = {"14"}               # 抗议/示威
_CAMEO_SANCTION = {"17"}               # 胁迫（制裁/封锁/boycott）
_CAMEO_COOP     = {"03", "04", "05", "06"}  # 外交合作（正向）

# Actor 类型代码和关注国家 — 已迁至 alert_config.py


def _gdelt_urls_last_hours(hours: int = 24) -> list:
    """生成过去 hours 小时内 GDELT v2 export 文件 URL（每15分钟一个）"""
    urls = []
    now = datetime.now(timezone.utc)
    minute = (now.minute // 15) * 15
    current = now.replace(minute=minute, second=0, microsecond=0)
    cutoff = current - timedelta(hours=hours)
    t = current
    while t > cutoff:
        ts = t.strftime("%Y%m%d%H%M%S")
        urls.append(f"http://data.gdeltproject.org/gdeltv2/{ts}.export.CSV.zip")
        t -= timedelta(minutes=15)
    return urls


def _parse_gdelt_zip(content: bytes) -> list:
    """解析 GDELT zip → 行列表（tab 分隔）"""
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
        csv_name = z.namelist()[0]
        with z.open(csv_name) as f:
            reader = csv.reader(
                io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
                delimiter="\t",
            )
            return list(reader)
    except Exception:
        return []


def _fetch_gdelt_recent(hours: int = 24, max_files: int = 48) -> list:
    """
    下载最近 hours 小时的 GDELT 事件（最多 max_files 个文件）。
    默认 24h / 48文件 ≈ 12小时窗口，足够检测信号峰值。
    """
    urls = _gdelt_urls_last_hours(hours)[:max_files]
    all_rows = []
    ok = failed = 0
    for url in urls:
        try:
            r = requests.get(url, proxies=_GDELT_PROXY, timeout=12)
            if r.status_code == 200:
                all_rows.extend(_parse_gdelt_zip(r.content))
                ok += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    print(f"  [GDELT] {ok}/{len(urls)} 文件成功，{len(all_rows)} 条事件，失败 {failed}")
    return all_rows


def _compute_gdelt_scores(rows: list) -> dict:
    """
    聚合 GDELT 行 → 各维度压力分（0-100）。

    GDELT v2 export 关键列（0-indexed，tab 分隔）:
      7  = Actor1CountryCode
      15 = Actor1Type1Code  (REL/GOV/MIL/ETH/OPP/REB/SEP/CVL 等)  ← 新增
      17 = Actor2CountryCode
      25 = Actor2Type1Code  (同上)                                   ← 新增
      26 = EventCode (CAMEO，取前2位作 root code)
      30 = GoldsteinScale (-10 冲突 ~ +10 合作)
      31 = NumMentions (事件热度权重)
    """
    military  = defaultdict(float)
    tension   = defaultdict(float)
    protest   = defaultdict(float)
    sanction  = defaultdict(float)
    coop      = defaultdict(float)
    rel_eth   = defaultdict(float)   # 新增：宗教/族群冲突
    regime_ch = defaultdict(float)   # 新增：政权不稳/叛乱
    # Phase 2B 新增：社会情绪（Tone 均值，越负越悲观）
    tone_sum  = defaultdict(float)
    tone_cnt  = defaultdict(int)
    # Phase 2D 新增：文化摩擦（EDU/MED Actor 参与的摩擦事件）
    cultural  = defaultdict(float)

    for row in rows:
        if len(row) < 35:
            continue
        try:
            root        = row[26].strip()[:2]
            actor1      = row[7].strip()
            actor1_type = row[15].strip() if len(row) > 15 else ""   # 新增
            actor2      = row[17].strip()
            actor2_type = row[25].strip() if len(row) > 25 else ""   # 新增
            goldstein   = float(row[30]) if row[30].strip() else 0.0
            mentions    = int(row[31])   if row[31].strip() else 1
        except (ValueError, IndexError):
            continue

        countries   = {c for c in [actor1, actor2] if c in _WATCH_COUNTRIES}
        actor_types = {actor1_type, actor2_type}
        if not countries:
            continue

        for c in countries:
            if root in _CAMEO_MILITARY:
                military[c] += mentions * (1 + max(0.0, -goldstein) / 5)
            if root in _CAMEO_TENSION:
                tension[c]  += mentions
            if root in _CAMEO_PROTEST:
                protest[c]  += mentions
            if root in _CAMEO_SANCTION:
                sanction[c] += mentions * (1 + abs(goldstein) / 5)
            if root in _CAMEO_COOP and goldstein > 0:
                coop[c]     += mentions * goldstein

            # 宗教/族群冲突：REL/ETH/SEP 参与的军事/紧张/抗议事件
            if actor_types & _ACTOR_REL_ETH and root in (_CAMEO_MILITARY | _CAMEO_TENSION | _CAMEO_PROTEST):
                rel_eth[c]  += mentions

            # 政权不稳：REB/OPP 参与的暴力或威胁事件
            if actor_types & _ACTOR_REGIME and root in (_CAMEO_MILITARY | _CAMEO_TENSION):
                regime_ch[c] += mentions

            # Phase 2B：社会情绪 — 只对冲突类事件计算 Goldstein 均值（排除合作事件干扰）
            # GoldsteinScale: -10(冲突) ~ +10(合作)，负值越大说明该国事件越冲突
            if root in (_CAMEO_MILITARY | _CAMEO_TENSION | _CAMEO_PROTEST):
                tone_sum[c] += goldstein * mentions
                tone_cnt[c] += mentions

            # Phase 2D：文化摩擦 — EDU/MED/IGO/NGO 参与的制裁/紧张/抗议事件
            if actor_types & _ACTOR_CULTURE and root in (_CAMEO_SANCTION | _CAMEO_TENSION | _CAMEO_PROTEST):
                cultural[c] += mentions

    def _norm(d, scale):
        return {k: round(min(100.0, v / scale * 100), 1) for k, v in d.items() if v > 0}

    # Phase 2B：社会压力指数（0-100，越高说明该国新闻情绪越负面）
    # Tone 均值 = tone_sum / tone_cnt，越负说明越多冲突事件
    # 归一化：-5.0 = 50分（中度悲观），-10.0 = 100分（极度悲观）
    def _tone_to_score(c: str) -> float:
        if tone_cnt[c] < 10:  # 样本不足跳过
            return 0.0
        mean_tone = tone_sum[c] / tone_cnt[c]
        if mean_tone >= 0:  # 正向情绪，不触发
            return 0.0
        return round(min(100.0, abs(mean_tone) / 10.0 * 100), 1)

    social_stress = {}
    for _c in tone_cnt:
        _s = _tone_to_score(_c)
        if _s >= 20:
            social_stress[_c] = _s

    # 归一化基准：以 2022-02-24 俄乌开战日为各维度绝对峰值，scale = 峰值 / 0.9
    # religious_conflict / regime_change 无实测峰值，使用保守估算值
    # ⚠️ 运行 3 个月后用 gdelt_history.jsonl 校准这两个维度的 scale
    return {
        "military":           _norm(military, 135000),
        "tension":            _norm(tension,  220000),
        "protest":            _norm(protest,   14000),
        "sanction":           _norm(sanction,  45000),
        "coop":               _norm(coop,     900000),
        "religious_conflict": _norm(rel_eth,    8000),   # 新增，估算基准
        "regime_change":      _norm(regime_ch,  5000),   # 新增，估算基准
        "social_stress":      social_stress,             # Phase 2B：社会情绪压力
        "cultural_friction":  _norm(cultural,    200),  # Phase 2D：文化摩擦（实测校准，原 3000 严重高估）
    }


def _save_gdelt_scores(scores: dict) -> None:
    """持久化维度分数，供 run_macro_analysis.py 读取调制 MC 参数"""
    try:
        from optim_config import DATA_DIR
        path = os.path.join(DATA_DIR, "gdelt_scores.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"updated": datetime.now(timezone.utc).isoformat()[:19], "scores": scores},
                f, ensure_ascii=False, indent=2,
            )
        print(f"  [GDELT] 分数已存 gdelt_scores.json")
        # 追加历史时序（JSONL：每次运行一行，日积月累形成时序）
        hist_path = os.path.join(DATA_DIR, "gdelt_history.jsonl")
        with open(hist_path, "a", encoding="utf-8") as hf:
            hf.write(json.dumps(
                {"date": datetime.now(timezone.utc).isoformat()[:10], "scores": scores},
                ensure_ascii=False,
            ) + "\n")
    except Exception as e:
        print(f"  [GDELT] 分数保存失败: {e}")


def scan_gdelt_dimension(hours: int = 24) -> tuple:
    """
    扫描 GDELT 地缘政治维度。

    返回 (alerts, dimension_scores)：
      alerts          — 格式同 scan_fred()，可直接传入 dedupe_and_save()
      dimension_scores — dict，供 get_gdelt_geo_modifier() 使用
    """
    today = date.today().isoformat()
    alerts = []

    rows = _fetch_gdelt_recent(hours=hours)
    if not rows:
        return alerts, {}

    scores = _compute_gdelt_scores(rows)

    MIL_WARN,  MIL_ALERT  = 30, 55
    SANC_WARN, PROT_WARN  = 20, 25

    for country, s in scores.get("military", {}).items():
        if s < MIL_WARN:
            continue
        lvl = "[警报]" if s >= MIL_ALERT else "[注意]"
        alerts.append({
            "date": today, "source": "GDELT",
            "indicator": f"地缘-军事事件：{country}",
            "series_id": f"GDELT_MIL_{country}",
            "current": s, "level": lvl,
            "desc": f"过去{hours}h军事压力分={s:.0f}/100",
        })
        print(f"  {lvl} GDELT军事[{country}]: {s:.0f}/100")

    for country, s in scores.get("sanction", {}).items():
        if s < SANC_WARN:
            continue
        alerts.append({
            "date": today, "source": "GDELT",
            "indicator": f"地缘-制裁/胁迫：{country}",
            "series_id": f"GDELT_SANC_{country}",
            "current": s, "level": "[注意]",
            "desc": f"过去{hours}h制裁压力分={s:.0f}/100",
        })
        print(f"  [注意] GDELT制裁[{country}]: {s:.0f}/100")

    for country, s in scores.get("protest", {}).items():
        if s < PROT_WARN:
            continue
        alerts.append({
            "date": today, "source": "GDELT",
            "indicator": f"地缘-社会动荡：{country}",
            "series_id": f"GDELT_PROT_{country}",
            "current": s, "level": "[注意]",
            "desc": f"过去{hours}h社会压力分={s:.0f}/100",
        })
        print(f"  [注意] GDELT社会[{country}]: {s:.0f}/100")

    # 宗教/族群冲突告警（新增）
    REL_WARN, REL_ALERT = 25, 50
    for country, s in scores.get("religious_conflict", {}).items():
        if s < REL_WARN:
            continue
        lvl = "[警报]" if s >= REL_ALERT else "[注意]"
        alerts.append({
            "date": today, "source": "GDELT",
            "indicator": f"地缘-宗教族群冲突：{country}",
            "series_id": f"GDELT_REL_{country}",
            "current": s, "level": lvl,
            "desc": f"过去{hours}h宗教/族群冲突压力分={s:.0f}/100",
        })
        print(f"  {lvl} GDELT宗教族群[{country}]: {s:.0f}/100")

    # 政权不稳/叛乱告警（新增）
    REGIME_WARN = 20
    for country, s in scores.get("regime_change", {}).items():
        if s < REGIME_WARN:
            continue
        alerts.append({
            "date": today, "source": "GDELT",
            "indicator": f"地缘-政权不稳：{country}",
            "series_id": f"GDELT_REGIME_{country}",
            "current": s, "level": "[注意]",
            "desc": f"过去{hours}h政权不稳/叛乱压力分={s:.0f}/100",
        })
        print(f"  [注意] GDELT政权不稳[{country}]: {s:.0f}/100")

    # 多点同步军事升温预警
    hot_spots = [c for c, s in scores.get("military", {}).items() if s >= MIL_WARN]
    if len(hot_spots) >= 3:
        alerts.append({
            "date": today, "source": "GDELT",
            "indicator": "地缘-全球多点军事升温",
            "series_id": "GDELT_MIL_GLOBAL",
            "current": float(len(hot_spots)), "level": "[警报]",
            "desc": f"{len(hot_spots)} 个关注区域同时升温: {', '.join(sorted(hot_spots))}",
        })
        print(f"  [警报] GDELT全球多点军事：{', '.join(sorted(hot_spots))}")

    # Phase 2B：社会压力指数告警
    STRESS_WARN, STRESS_ALERT = 35, 60
    for country, s in scores.get("social_stress", {}).items():
        if s < STRESS_WARN:
            continue
        lvl = "[警报]" if s >= STRESS_ALERT else "[注意]"
        alerts.append({
            "date": today, "source": "GDELT",
            "indicator": f"社会情绪-压力指数：{country}",
            "series_id": f"GDELT_STRESS_{country}",
            "current": s, "level": lvl,
            "desc": f"过去{hours}h社会情绪压力分={s:.0f}/100（Goldstein均值偏负）",
        })
        print(f"  {lvl} GDELT社会压力[{country}]: {s:.0f}/100")

    # Phase 2D：文化摩擦告警
    CULTURE_WARN = 20
    for country, s in scores.get("cultural_friction", {}).items():
        if s < CULTURE_WARN:
            continue
        alerts.append({
            "date": today, "source": "GDELT",
            "indicator": f"文化贸易摩擦：{country}",
            "series_id": f"GDELT_CULT_{country}",
            "current": s, "level": "[注意]",
            "desc": f"过去{hours}h文化摩擦压力分={s:.0f}/100（媒体/教育/NGO参与）",
        })
        print(f"  [注意] GDELT文化摩擦[{country}]: {s:.0f}/100")

    return alerts, scores


def get_gdelt_geo_modifier(scores: dict = None) -> dict:
    """
    将 GDELT 维度分数转换为 Monte Carlo 参数调制系数。

    若 scores=None，从 gdelt_scores.json 缓存读取；无缓存则返回 {}。

    返回键（均为数值，可直接叠加到 MC 参数）：
      oil_shock_bias       — 原油冲击均值偏移（σ，+向上）
      trade_tension_boost  — 贸易紧张度加分（pt）
      umcsent_drag         — 消费信心拖累（负值 pt）
      tail_risk_boost      — 亚太极端尾风险加分（pt）
      recession_boost      — 衰退概率加分（pt，俄乌/能源通道）
    """
    if scores is None:
        try:
            from optim_config import DATA_DIR
            path = os.path.join(DATA_DIR, "gdelt_scores.json")
            if os.path.exists(path):
                import time as _t
                age_days = (_t.time() - os.path.getmtime(path)) / 86400
                if age_days > 7:
                    print(f"  [GDELT] cache 已 {age_days:.0f} 天未更新，跳过地缘调制")
                else:
                    with open(path, encoding="utf-8") as f:
                        scores = json.load(f).get("scores", {})
        except Exception:
            pass
    if not scores:
        return {}

    mil  = scores.get("military",  {})
    sanc = scores.get("sanction",  {})
    prot = scores.get("protest",   {})

    mod = {}

    # 中东军事 → 油价冲击偏移
    mid_east = max(mil.get("IRN", 0), mil.get("SAU", 0), mil.get("ISR", 0))
    if mid_east:
        mod["oil_shock_bias"] = round(mid_east / 100 * 2.0, 2)

    # 美中制裁互动 → 贸易张力
    us_cn = max(sanc.get("USA", 0), sanc.get("CHN", 0))
    if us_cn:
        mod["trade_tension_boost"] = round(us_cn / 100 * 15, 1)

    # 西方社会动荡 → 消费信心拖累
    social = max(prot.get("USA", 0), prot.get("DEU", 0), prot.get("FRA", 0))
    if social:
        mod["umcsent_drag"] = round(-social / 100 * 8, 1)

    # 亚太军事（台海/朝鲜）→ 极端尾风险
    apac = max(mil.get("TWN", 0), mil.get("PRK", 0))
    if apac:
        mod["tail_risk_boost"] = round(apac / 100 * 20, 1)

    # 俄乌战事 → 衰退概率（能源/粮食冲击路径）
    ru_ua = max(mil.get("RUS", 0), mil.get("UKR", 0))
    if ru_ua:
        mod["recession_boost"] = round(ru_ua / 100 * 10, 1)

    return mod


# ── GDELT 降级备份：从 Crucix 新闻提取地缘信号 ───────────────────────────────
_GEO_FALLBACK_KWS = {
    "地缘-军事冲突": [
        "war", "invasion", "airstrike", "military strike", "missile attack",
        "troops deployed", "military offensive", "armed conflict", "bombardment",
        "战争", "军事冲突", "武装冲突", "轰炸", "空袭", "导弹袭击",
    ],
    "地缘-制裁升级": [
        "sanctions", "export ban", "trade embargo", "asset freeze", "blacklist",
        "export controls", "technology ban",
        "制裁", "出口禁令", "贸易制裁", "资产冻结", "技术封锁",
    ],
    "地缘-紧张局势": [
        "escalation", "geopolitical tension", "confrontation", "military buildup",
        "security crisis", "standoff", "brinkmanship",
        "台海", "南海", "台湾海峡", "地缘紧张", "紧张局势",
    ],
    "地缘-政治动荡": [
        "coup", "uprising", "political crisis", "regime change", "civil unrest",
        "政变", "骚乱", "政治危机", "社会动乱",
    ],
}


def _gdelt_fallback_from_news(articles: list) -> list:
    """GDELT 失败时，用 Crucix 新闻关键词频率生成地缘预警（降级备份）。

    算法与 scan_news() 相同（7天/90天频率比），但使用专门的地缘关键词，
    并在 alert source 中标注降级来源，区别于正常 GDELT 分数。
    """
    if not articles:
        print("  [GDELT降级] Crucix 新闻为空，无法备份地缘扫描")
        return []

    today = date.today()
    counts_7d: dict = defaultdict(int)
    counts_90d: dict = defaultdict(int)

    for art in articles:
        text = (art.get("title", "") + " " + art.get("content", "")).lower()
        try:
            d = art.get("published_at") or art.get("pubDate") or art.get("date")
            if not d:
                continue
            if "," in d and " " in d:
                d_clean = d.split(",")[1].strip()
                pub = datetime.strptime(d_clean[:25], "%d %b %Y %H:%M:%S").date()
            else:
                pub = datetime.fromisoformat(d).date()
        except Exception:
            continue
        delta = (today - pub).days

        for cat, kws in _GEO_FALLBACK_KWS.items():
            if any(kw.lower() in text for kw in kws):
                if delta <= 7:
                    counts_7d[cat] += 1
                if delta <= 90:
                    counts_90d[cat] += 1

    alerts = []
    for cat in _GEO_FALLBACK_KWS:
        c7, c90 = counts_7d.get(cat, 0), counts_90d.get(cat, 0)
        if c90 == 0 or c7 == 0:
            continue
        ratio = (c7 / 7) / (c90 / 90)
        if ratio < NEWS_FREQ_WARN_RATIO:
            continue
        level = "[警报]" if ratio >= NEWS_FREQ_ALERT_RATIO else "[注意]"
        alerts.append({
            "date": today.isoformat(),
            "source": "Crucix地缘(GDELT降级)",
            "indicator": cat,
            "current": round(c7 / 7, 2),
            "baseline": round(c90 / 90, 2),
            "ratio": round(ratio, 1),
            "level": level,
            "desc": f"GDELT不可用，Crucix新闻频率是基线的{ratio:.1f}倍",
        })
        print(f"  {level} {cat}（Crucix备份）: 频率是基线的{ratio:.1f}倍")

    if not alerts:
        print("  [GDELT降级] Crucix新闻未检测到地缘关键词异常")
    return alerts


# ── Crucix 新闻获取 ───────────────────────────────────────────────────────────
def fetch_crucix_news(days: int = 90) -> list[dict]:
    """
    直接拉取 Crucix 最新新闻（与 run_macro_analysis.py 相同模式）。
    若失败则返回空列表，让扫描器继续运行（新闻部分降级）。
    """
    try:
        resp = requests.get(CRUCIX_REMOTE_URL, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            # Crucix 返回 'news' 或 'newsFeed' 字段
            articles = data.get("news") or data.get("newsFeed") or []
            # 截取最近N天
            if days:
                cutoff = date.today() - timedelta(days=days)
                filtered = []
                for art in articles:
                    try:
                        d = art.get("date", "")
                        if d:
                            # 解析 RFC 格式日期 (e.g., "Sun, 17 May 2026 13:48:00 GMT")
                            d_clean = d.split(",")[1].strip() if "," in d else d
                            pub_date = datetime.strptime(d_clean[:25], "%d %b %Y %H:%M:%S")
                            if pub_date.date() >= cutoff:
                                filtered.append(art)
                    except:
                        filtered.append(art)  # 解析失败的也保留
                articles = filtered
            print(f"  [Crucix] 获取 {len(articles)} 篇文章（最近{days}天）")
            return articles
        else:
            print(f"  [Crucix] API 返回 {resp.status_code}，跳过新闻扫描。")
    except Exception as e:
        print(f"  [Crucix] 获取失败: {e}，跳过新闻扫描。")
    return []


def scan_news(articles: list[dict]) -> list[dict]:
    """扫描新闻文章关键词频次，生成新闻类预警。

    统计维度：7天高频（突发）和 90天基线（趋势）。
    触发逻辑：
      7天频次 / 90天均频 ≥ NEWS_FREQ_ALERT_RATIO → [警报]
      7天频次 / 90天均频 ≥ NEWS_FREQ_WARN_RATIO  → [注意]
    分类来自 ALERT_KEYWORDS 字典（信用风险/衰退信号/通胀失控/地缘升级等）。
    """
    if not articles:
        return []

    alerts = []
    today = date.today()
    counts_7d = defaultdict(int)
    counts_90d = defaultdict(int)

    for art in articles:
        text = (art.get("title", "") + " " + art.get("content", "")).lower()
        try:
            # 优先解析 published_at / pubDate (ISO format)
            d = art.get("published_at") or art.get("pubDate") or art.get("date")
            if not d:
                continue
            # RFC format: "Sun, 17 May 2026 13:48:00 GMT"
            if "," in d and " " in d:
                d_clean = d.split(",")[1].strip()
                pub = datetime.strptime(d_clean[:25], "%d %b %Y %H:%M:%S").date()
            else:
                pub = datetime.fromisoformat(d).date()
        except Exception:
            continue
        delta = (today - pub).days

        for cat, kws in ALERT_KEYWORDS.items():
            if any(kw.lower() in text for kw in kws):
                if delta <= 7:
                    counts_7d[cat] += 1
                if delta <= 90:
                    counts_90d[cat] += 1

    for cat in ALERT_KEYWORDS:
        c7, c90 = counts_7d.get(cat, 0), counts_90d.get(cat, 0)
        if c90 == 0:
            continue
        ratio = (c7 / 7) / (c90 / 90)
        if ratio < NEWS_FREQ_WARN_RATIO:
            continue
        level = "[警报]" if ratio >= NEWS_FREQ_ALERT_RATIO else "[注意]"
        alerts.append({
            "date": today.isoformat(),
            "source": "Crucix新闻",
            "indicator": f"关键词：{cat}",
            "current": round(c7 / 7, 2),
            "baseline": round(c90 / 90, 2),
            "ratio": round(ratio, 1),
            "level": level,
        })
        print(f"  {level} 新闻「{cat}」: 频率是基线的{ratio:.1f}倍")
    return alerts


# ── 去重 & 持久化 ─────────────────────────────────────────────────────────────
def dedupe_and_save(alerts: list[dict]):
    """当天同一指标只保留一条，然后追加到日志。"""
    today = date.today().isoformat()
    existing = _load_signal_log()
    existing_keys = {
        (e["date"], e["indicator"])
        for e in existing if e.get("date") == today
    }

    new_alerts = [a for a in alerts
                  if (a["date"], a["indicator"]) not in existing_keys]
    if not new_alerts:
        print("  所有预警今日已记录，无新增。")
        return

    existing.extend(new_alerts)
    # 只保留最近 180 天
    cutoff = (date.today() - timedelta(days=180)).isoformat()
    existing = [e for e in existing if e.get("date", "") >= cutoff]
    os.makedirs(os.path.dirname(WEAK_SIGNAL_LOG), exist_ok=True)
    with open(WEAK_SIGNAL_LOG, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"  新增 {len(new_alerts)} 条预警记录。")


def _load_signal_log() -> list:
    """从 WEAK_SIGNAL_LOG 加载历史预警记录（JSON数组），文件不存在或损坏返回空列表。"""
    if not os.path.exists(WEAK_SIGNAL_LOG):
        return []
    with open(WEAK_SIGNAL_LOG, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"  [WARN] weak_signal_log.json 损坏，重置为空: {e}")
            return []


# ── 推送消息 ──────────────────────────────────────────────────────────────────
def build_message(alerts: list[dict]) -> str:
    """将预警列表格式化为 ntfy 推送文本（按高级警报/关注事项分组，附分析入口提示）。"""
    high = [a for a in alerts if "警报" in a["level"]]
    mid  = [a for a in alerts if "注意" in a["level"]]
    lines = [f"[弱信号预警] {date.today().isoformat()}", ""]

    def fmt(a):
        if "z_score" in a:
            return f"- {a['indicator']}（{a['direction']}） Z={a['z_score']}"
        elif "threshold" in a:
            return f"- {a['indicator']}: {a['current']} ({a['desc']})"
        elif "details" in a:
            return f"- {a['indicator']}: {a['details']}"
        elif "desc" in a:
            return f"- {a['indicator']}: {a['current']} ({a['desc']})"
        return f"- {a['indicator']} 频率={a.get('ratio', '?')}x"

    if high:
        lines.append(f"[高级警报] ({len(high)}项)")
        lines.extend(f"  {fmt(a)}" for a in high)
        lines.append("")
    if mid:
        lines.append(f"[关注事项] ({len(mid)}项)")
        lines.extend(f"  {fmt(a)}" for a in mid)
        lines.append("")

    lines.append("→ 运行 `python run_macro_analysis.py --country both` 获取详细分析")
    return "\n".join(lines)


# ── 主入口 ────────────────────────────────────────────────────────────────────
# ── 新闻归档 ────────────────────────────────────────────────────────────────
def archive_news(articles: list[dict], news_alerts: list[dict]):
    """将触发预警的新闻归档到新闻知识库。"""
    matched = []
    if not articles or not news_alerts:
        return matched
    
    # 提取触发预警的类别
    triggered_cats = set()
    for a in news_alerts:
        ind = a.get("indicator", "")
        if ind.startswith("关键词："):
            triggered_cats.add(ind.replace("关键词：", ""))
    
    if not triggered_cats:
        return matched
    
    # 收集最近7天匹配的articles
    today = date.today()
    matched = []
    for art in articles:
        text = (art.get("title", "") + " " + art.get("content", "")).lower()
        try:
            d = art.get("published_at") or art.get("pubDate") or art.get("date")
            if not d:
                continue
            if "," in d and " " in d:
                d_clean = d.split(",")[1].strip()
                pub = datetime.strptime(d_clean[:25], "%d %b %Y %H:%M:%S").date()
            else:
                pub = datetime.fromisoformat(d).date()
        except Exception:
            continue
        
        delta = (today - pub).days
        if delta > 7:
            continue
        
        for cat in triggered_cats:
            kws = ALERT_KEYWORDS.get(cat, [])
            if any(kw.lower() in text for kw in kws):
                matched.append({
                    "date": pub.isoformat(),
                    "title": art.get("title", "无标题"),
                    "content": art.get("content", "")[:300],
                    "url": art.get("url", ""),
                    "category": cat,
                })
                break  # 一篇文章只归一个类别
    
    if not matched:
        return matched
    
    # 保存到新闻库
    try:
        from optim_config import WORKSPACE as _WORKSPACE
        news_kb_dir = os.path.join(_WORKSPACE, "docs", "新闻库")
        os.makedirs(news_kb_dir, exist_ok=True)
        today_str = date.today().isoformat()
        news_file = os.path.join(news_kb_dir, f"{today_str}_重要新闻.md")
        
        lines = [f"# 预警新闻归档 - {today_str}", ""]
        lines.append(f"触发类别：{', '.join(triggered_cats)}")
        lines.append(f"共 {len(matched)} 条\n")
        lines.append("---")
        
        for i, art in enumerate(matched, 1):
            lines.append(f"\n## [{i}] {art['title']}")
            lines.append(f"日期：{art['date']} | 类别：{art['category']}")
            if art['url']:
                lines.append(f"链接：{art['url']}")
            lines.append(f"\n{art['content']}")
        
        with open(news_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  [KB] 新闻已归档：{news_file}")
        return matched
    except Exception as e:
        print(f"  [WARN] 新闻归档失败：{e}")
    return matched


def save_latest_news_json(all_alerts: list, json_path: str = None) -> None:
    """保存所有预警（指标+新闻）到 latest_news.json，供 run_macro_analysis.py 注入 prompt"""
    if not all_alerts:
        return
    if json_path is None:
        from optim_config import DATA_DIR as _DATA_DIR
        json_path = os.path.join(_DATA_DIR, "latest_news.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    
    # 过滤30天内的预警
    cutoff = datetime.now() - timedelta(days=30)
    filtered = []
    for a in all_alerts:
        try:
            ad = datetime.fromisoformat(a.get("date", "2099-01-01")[:10])
            if ad >= cutoff:
                filtered.append(a)
        except:
            filtered.append(a)  # 日期解析失败则保留
    
    # 确保每条预警都有 alert_type 字段
    def get_alert_type(cat: str) -> str:
        """根据预警类别关键词映射 alert_type：CRISIS / STRESS / WARNING（供 latest_news.json 消费）。"""
        cat_l = cat.lower()
        if any(k in cat_l for k in ["衰退", "危机", "崩盘", "crisis", "recession", "crash"]):
            return "CRISIS"
        if any(k in cat_l for k in ["压力", "违约", "stress", "default"]):
            return "STRESS"
        return "WARNING"
    
    for a in filtered:
        # 补全 title 字段（format_news_for_prompt 依赖）
        if "title" not in a:
            a["title"] = a.get("indicator", a.get("name", "预警"))
        # 补全 category 字段（format_news_for_prompt 依赖）
        if "category" not in a:
            a["category"] = a.get("level", a.get("source", ""))
        if "alert_type" not in a:
            a["alert_type"] = get_alert_type(a.get("category", ""))
    
    # 按 alert_type 排序：CRISIS > STRESS > WARNING
    type_order = {"CRISIS": 0, "STRESS": 1, "WARNING": 2}
    filtered.sort(key=lambda x: type_order.get(x.get("alert_type", "WARNING"), 3))
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)
    print(f"  [JSON] 已保存 {len(filtered)} 条全部预警到 latest_news.json")


def run_scan():
    """主扫描入口，汇总所有子扫描器结果并推送预警。

    扫描顺序：FRED指标 → 日元套利 → 铜金比率 → 中国指标 → GDELT地缘 → 新闻关键词
    → 跨资产同步压力检测 → 去重保存 → ntfy 推送 → 更新 latest_news.json
    """
    from optim_config import ensure_dirs, DATA_DIR as _DATA_DIR
    ensure_dirs()
    print(f"[弱信号扫描] {date.today().isoformat()}")

    fred_alerts = []
    japan_alerts = []
    if FRED_API_KEY:
        fred = Fred(api_key=FRED_API_KEY)
        print("扫描美国指标(FRED)...")
        fred_alerts = scan_fred(fred)
        print("扫描日元套利风险(FRED)...")
        try:
            japan_alerts = scan_japan_carry_risk(fred)
        except Exception as e:
            print(f"  [警告] 日元套利扫描失败: {e}")
    else:
        print("[警告] 未设置 FRED_API_KEY，跳过 FRED 扫描。")

    print("扫描铜金比率（跨市场景气）...")
    copper_gold_alerts = []
    try:
        copper_gold_alerts = scan_copper_gold_ratio()
    except Exception as e:
        print(f"  [警告] 铜金比率扫描失败: {e}")

    print("扫描中国指标(NeoData)...")
    china_alerts = scan_china()

    # ── news.db：初始化 + 写入宏观快照 ──────────────────────────────────────
    _db_ctx_id = None
    _db_hash_to_id: dict = {}
    _db_cat_to_ids: dict = {}
    try:
        import os as _os
        from news_db import (init_db as _ndb_init, write_scan_context as _ndb_ctx,
                             insert_articles as _ndb_art, tag_articles as _ndb_tag,
                             insert_signal_episode as _ndb_ep, link_episode_articles as _ndb_link,
                             get_trigger_titles as _ndb_titles)
        _db_path = _os.path.join(_DATA_DIR, "news.db")
        _ndb_init(_db_path)
        _vix    = ((_load_local_history("VIXCLS")        or [None]))[-1]
        _t10y2y = ((_load_local_history("T10Y2Y")        or [None]))[-1]
        _baa10y = ((_load_local_history("BAMLH0A0HYM2")  or [None]))[-1]
        _dff    = ((_load_local_history("DFF")            or [None]))[-1]
        _vix_regime = (
            "crisis" if (_vix or 0) >= 30 else ("elevated" if (_vix or 0) >= 20 else "normal")
        ) if _vix else None
        _dq = {k: "missing" for k, v in
               {"vix": _vix, "t10y2y": _t10y2y, "baa10y": _baa10y, "dff": _dff}.items()
               if v is None}
        _db_ctx_id = _ndb_ctx(_db_path, vix=_vix, t10y2y=_t10y2y, baa10y=_baa10y, dff=_dff,
                               vix_regime=_vix_regime, data_quality=_dq or None)
        print(f"  [news.db] scan_context 写入完成 (id={_db_ctx_id}, vix={_vix})")
    except Exception as _e:
        print(f"  [news.db] 初始化/宏观快照写入失败（非阻断）: {_e}")
    # ─────────────────────────────────────────────────────────────────────────

    print("拉取 Crucix 新闻...")
    articles = fetch_crucix_news(days=90)

    from fetch_rss_news import fetch_rss_news
    rss_articles = fetch_rss_news()
    articles = articles + rss_articles

    # ── news.db：文章入库 + 打标签 ───────────────────────────────────────────
    if _db_ctx_id is not None and articles:
        try:
            _db_hash_to_id = _ndb_art(_db_path, articles, _db_ctx_id)
            _db_cat_to_ids = _ndb_tag(_db_path, _db_hash_to_id, articles, ALERT_KEYWORDS)
            print(f"  [news.db] 文章入库 {len(_db_hash_to_id)} 篇，打标签 {sum(len(v) for v in _db_cat_to_ids.values())} 条")
        except Exception as _e:
            print(f"  [news.db] 文章入库/打标签失败（非阻断）: {_e}")
    # ─────────────────────────────────────────────────────────────────────────

    print("扫描 GDELT 地缘政治维度...")
    gdelt_alerts = []
    gdelt_scores = {}
    try:
        gdelt_alerts, gdelt_scores = scan_gdelt_dimension(hours=24)
        if gdelt_scores:
            _save_gdelt_scores(gdelt_scores)
    except Exception as e:
        print(f"  [警告] GDELT 扫描失败: {e}，切换 Crucix 地缘关键词备份扫描")
        gdelt_alerts = _gdelt_fallback_from_news(articles)

    news_alerts = scan_news(articles)

    # ── news.db：信号事件写入 + 触发标题注入 ────────────────────────────────
    if _db_ctx_id is not None:
        for _alert in news_alerts:
            try:
                _cat = _alert.get("indicator", "").replace("关键词：", "")
                if not _cat:
                    continue
                _titles = _ndb_titles(_db_path, _cat, _db_ctx_id, limit=3)
                if _titles:
                    _alert["trigger_titles"] = _titles
                _ep_id = _ndb_ep(_db_path, _cat, _alert.get("ratio", 0),
                                  _alert.get("level", ""), _db_ctx_id)
                _ndb_link(_db_path, _ep_id, _db_cat_to_ids.get(_cat, []))
            except Exception as _e:
                print(f"  [news.db] 信号事件写入失败（非阻断）: {_e}")
    # ─────────────────────────────────────────────────────────────────────────

    all_alerts = fred_alerts + japan_alerts + copper_gold_alerts + china_alerts + gdelt_alerts + news_alerts

    # 跨资产同步压力复合检测（基于上面已生成的 alerts）
    stress_alerts = detect_global_stress(all_alerts)
    all_alerts = all_alerts + stress_alerts

    print(f"扫描完成：{len(all_alerts)} 条预警（GDELT {len(gdelt_alerts)}，日元套利 {len(japan_alerts)}，铜金比率 {len(copper_gold_alerts)}，跨资产 {len(stress_alerts)} 条）")

    if all_alerts:
        dedupe_and_save(all_alerts)
        if news_alerts:
            matched = archive_news(articles, news_alerts)
        save_latest_news_json(all_alerts)

        print(build_message(all_alerts))
    else:
        print("无异常信号，静默。")

    # ── signal_synthesizer：弱信号共振推演（非阻断子进程）────────────────────
    try:
        import sys as _sys
        _synth = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_synthesizer.py")
        if os.path.exists(_synth) and _db_ctx_id is not None:
            import subprocess as _sp
            _sp.Popen(
                [_sys.executable, _synth, "--scan-ctx-id", str(_db_ctx_id),
                 "--db-path", _db_path],
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            print(f"  [synthesizer] 子进程已启动（scan_ctx_id={_db_ctx_id}）")
    except Exception as _syn_e:
        print(f"  [synthesizer] 启动失败（非阻断）: {_syn_e}")
    # ──────────────────────────────────────────────────────────────────────────

    # ── situation_tracker：更新正在演化的事件状态（非阻断）───────────────────
    try:
        import sys as _sys
        _app_dir = os.path.dirname(os.path.abspath(__file__))
        if _app_dir not in _sys.path:
            _sys.path.insert(0, _app_dir)
        from situation_tracker import update as _st_update
        _st_update()
        print("  [situation_tracker] 事件状态已更新")
    except Exception as _st_e:
        print(f"  [situation_tracker] 更新失败（非阻断）: {_st_e}")
    # ──────────────────────────────────────────────────────────────────────────

    return all_alerts


if __name__ == "__main__":
    run_scan()
