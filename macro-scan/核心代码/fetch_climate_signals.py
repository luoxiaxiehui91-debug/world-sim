"""
fetch_climate_signals.py — 自然环境信号采集（Phase 2A）

数据源：
  - NOAA CPC 厄尔尼诺指数（ONI，月度）
  - NOAA GISS 全球温度异常（年度）
  - FIRMS 卫星火点（已由 Crucix 接入，本模块汇总统计）

输出：data/climate_signals.json
      含 oni（厄尔尼诺指数）/ temp_anomaly / fire_hotspot_summary

调用：每月1日 09:15（scheduler.py 加入后生效）
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
    _REQ_OK = True
except ImportError:
    _REQ_OK = False

try:
    from optim_config import DATA_DIR, WORKSPACE, CRUCIX_REMOTE_URL
except ImportError:
    WORKSPACE = Path(__file__).parent.parent
    DATA_DIR = str(Path(WORKSPACE) / "data")
    CRUCIX_REMOTE_URL = os.environ.get("CRUCIX_REMOTE_URL", "http://192.168.31.108:3117/api/data")

CLIMATE_OUTPUT = os.path.join(DATA_DIR, "climate_signals.json")
FRED_PROXY = os.environ.get("FRED_PROXY", "")

_PROXIES = {"http": FRED_PROXY, "https": FRED_PROXY} if FRED_PROXY else None

# ── ONI 厄尔尼诺指数 ──────────────────────────────────────────────────────────
# NOAA CPC 提供 ONI 月度数据（3个月滑动均值的 ENSO 指数）
# > 0.5: 厄尔尼诺  < -0.5: 拉尼娜  之间: 中性
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"


def _fetch_oni() -> dict:
    """拉取 ONI 指数最新3个月均值。返回 {value, status, date, interpretation}。"""
    if not _REQ_OK:
        return {}
    try:
        resp = requests.get(ONI_URL, timeout=15, proxies=_PROXIES)
        resp.raise_for_status()
        lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
        # 格式：SEAS YR TOTAL ANOM
        # 找最后一个有效行
        last_oni = None
        last_date = None
        for line in reversed(lines):
            parts = line.split()
            if len(parts) >= 4 and parts[0] not in ("SEAS",):
                try:
                    oni_val = float(parts[3])
                    yr = parts[1]
                    seas = parts[0]
                    last_oni = oni_val
                    last_date = f"{yr}-{seas}"
                    break
                except (ValueError, IndexError):
                    pass

        if last_oni is None:
            return {}

        if last_oni >= 1.5:
            status = "强厄尔尼诺"
        elif last_oni >= 0.5:
            status = "厄尔尼诺"
        elif last_oni <= -1.5:
            status = "强拉尼娜"
        elif last_oni <= -0.5:
            status = "拉尼娜"
        else:
            status = "中性"

        interpretation = {
            "强厄尔尼诺": "全球粮食产区异常风险高，印度/澳洲干旱，南美洪涝，影响粮价",
            "厄尔尼诺":   "农业产区天气扰动，新兴市场粮食通胀压力上升",
            "拉尼娜":     "北美偏冷，能源需求可能上升；部分产区降水偏多",
            "强拉尼娜":   "北美严寒，暖冬概率低，LNG/煤炭需求上升",
            "中性":       "ENSO中性，无明显气候扰动",
        }.get(status, "")

        print(f"  [climate] ONI={last_oni} ({last_date}) → {status}")
        return {"value": last_oni, "status": status, "date": last_date,
                "interpretation": interpretation}
    except Exception as e:
        print(f"  [climate] ONI拉取失败: {e}")
        return {}


# ── FIRMS 火点汇总（从 Crucix 读取）────────────────────────────────────────
def _fetch_firms_summary() -> dict:
    """从 Crucix API 读取卫星火点汇总统计。"""
    if not _REQ_OK:
        return {}
    try:
        resp = requests.get(CRUCIX_REMOTE_URL, timeout=8)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        thermal = data.get("thermal", [])
        if not thermal:
            return {}

        total_hotspots = sum(t.get("hotspots", 0) for t in thermal)
        high_frp_count = sum(t.get("high_confidence", 0) for t in thermal)
        regions = [t.get("region", "unknown") for t in thermal if t.get("hotspots", 0) > 500]

        summary = {
            "total_hotspots": total_hotspots,
            "high_confidence": high_frp_count,
            "active_fire_regions": regions,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        print(f"  [climate] FIRMS: 总热点={total_hotspots}, 高置信={high_frp_count}, 活跃区域={regions}")
        return summary
    except Exception as e:
        print(f"  [climate] FIRMS读取失败: {e}")
        return {}


# ── 气候风险评分 ─────────────────────────────────────────────────────────────
def _compute_climate_risk_score(oni: dict, firms: dict) -> float:
    """
    综合计算气候风险分数（0-100）。
    ONI 极端值 → 粮食/社会传导路径风险
    FIRMS 火点异常 → 直接环境损失
    """
    score = 0.0

    # ONI 贡献（0-60分）
    oni_val = oni.get("value")
    if oni_val is not None:
        if abs(oni_val) >= 2.0:
            score += 60
        elif abs(oni_val) >= 1.5:
            score += 45
        elif abs(oni_val) >= 1.0:
            score += 30
        elif abs(oni_val) >= 0.5:
            score += 15

    # FIRMS 贡献（0-40分）
    total = firms.get("total_hotspots", 0)
    if total >= 20000:
        score += 40
    elif total >= 10000:
        score += 25
    elif total >= 5000:
        score += 15
    elif total >= 2000:
        score += 8

    return min(score, 100.0)


# ── 主入口 ───────────────────────────────────────────────────────────────────
def fetch_and_save() -> dict:
    """采集所有气候信号，保存到 climate_signals.json，返回数据字典。"""
    print("[fetch_climate_signals] 开始采集气候信号...")

    oni    = _fetch_oni()
    firms  = _fetch_firms_summary()
    risk_score = _compute_climate_risk_score(oni, firms)

    result = {
        "fetched_at": datetime.now().isoformat()[:19],
        "oni": oni,
        "firms": firms,
        "climate_risk_score": round(risk_score, 1),
        "risk_level": (
            "高" if risk_score >= 50 else
            "中" if risk_score >= 25 else "低"
        ),
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CLIMATE_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[fetch_climate_signals] 完成：risk_score={risk_score:.1f} "
          f"ONI={oni.get('value','N/A')} FIRMS={firms.get('total_hotspots','N/A')}")
    return result


def get_context() -> str:
    """返回气候信号的摘要字符串，供 LLM prompt 注入。"""
    if not os.path.exists(CLIMATE_OUTPUT):
        return ""
    try:
        with open(CLIMATE_OUTPUT, encoding="utf-8") as f:
            data = json.load(f)
        oni = data.get("oni", {})
        risk = data.get("climate_risk_score", 0)
        level = data.get("risk_level", "低")
        if risk < 15:
            return ""  # 低风险不注入
        lines = [f"[自然环境] 气候风险={level}（{risk:.0f}/100）"]
        if oni:
            lines.append(f"  厄尔尼诺指数 ONI={oni.get('value','N/A')} ({oni.get('status','')})")
            if oni.get("interpretation"):
                lines.append(f"  {oni['interpretation']}")
        return "\n".join(lines)
    except Exception:
        return ""


if __name__ == "__main__":
    result = fetch_and_save()
    print("\n--- 气候信号摘要 ---")
    print(get_context() or "风险较低，无需特别关注")
