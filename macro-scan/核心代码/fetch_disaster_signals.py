"""
fetch_disaster_signals.py — 自然灾害实时信号采集

数据源：
  - USGS Earthquake Hazards Program（免费公开 API）
    https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.geojson
    提供过去24小时 M≥5.0 的地震事件
  - Smithsonian GVP（火山，周度，仅人工更新时有数据）
  - GDELT 已包含 Tier1 灾害事件，作为补充检索通道

输出：data/disaster_signals.json

调度：每日 05:25（FRED 数据拉取前，早于弱信号扫描）
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
    _REQ_OK = True
except ImportError:
    _REQ_OK = False

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = Path(__file__).parent.parent
    DATA_DIR  = str(Path(WORKSPACE) / "data")

DISASTER_OUTPUT = os.path.join(DATA_DIR, "disaster_signals.json")

# USGS 实时地震 Feed（过去24小时重大事件，M≥2.5）
USGS_SIGNIFICANT_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.geojson"
USGS_M25_URL         = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"

# 全球关键供应链节点（震中在此范围内，风险等级自动提升）
_CRITICAL_ZONES = [
    # (lat_min, lat_max, lon_min, lon_max, name, risk_mult)
    (21.0, 26.5, 119.0, 122.5, "台湾（半导体核心区）", 2.5),
    (34.0, 45.0, 129.0, 145.0, "日本本州（汽车/半导体）", 2.0),
    (37.0, 38.5, 126.5, 129.5, "韩国（半导体/钢铁）", 1.8),
    (5.0,  7.5, 125.0, 127.0, "菲律宾（马六甲近端）", 1.3),
    (50.0, 53.0,   4.0,   5.0, "荷兰（鹿特丹港）", 1.5),
    (8.5,  9.5,  -80.0, -79.0, "巴拿马（运河区）", 1.8),
    (1.0,  2.0, 103.5, 104.5, "新加坡（马六甲出口）", 1.5),
    (24.0, 26.0, 120.0, 122.0, "台湾北部（台北/新竹科技走廊）", 2.5),
]

# 已知核电密集区域（震中在此范围，叠加核风险警告）
_NUCLEAR_ZONES = [
    (34.0, 45.0, 129.0, 145.0, "日本（核电再启动地区）"),
    (34.0, 38.5, 125.0, 130.0, "韩国（核电占比29%）"),
    (43.0, 50.0,   0.0,   8.0, "法国（核电占比70%）"),
    (45.0, 52.0,  14.0,  22.0, "中欧核电带"),
]


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _in_zone(lat: float, lon: float, zones: list) -> list[str]:
    """返回震中所在的关键区域名称列表。"""
    return [name for lat_min, lat_max, lon_min, lon_max, name, *_ in
            [(*z,) for z in zones]
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max]


def _risk_multiplier(lat: float, lon: float) -> float:
    """根据震中位置返回风险放大系数。"""
    for lat_min, lat_max, lon_min, lon_max, name, mult in _CRITICAL_ZONES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return mult
    return 1.0


def _compute_event_risk(mag: float, depth_km: float, lat: float, lon: float) -> dict:
    """
    综合震级、震深、区位计算单次地震的风险评分（0-100）和等级。

    评分逻辑：
      - 基础分 = (mag - 5.0) / 4.0 * 60    （M5→0分，M9→60分）
      - 浅源加成 = max(0, (30 - depth_km) / 30) * 15  （<30km浅源加最多15分）
      - 区位乘数 = risk_multiplier（关键节点最高×2.5）
    """
    if mag < 5.0:
        return {"score": 0, "level": "low", "critical_zones": [], "nuclear_zones": []}

    base = min(60.0, (mag - 5.0) / 4.0 * 60)
    shallow_bonus = max(0, (30 - min(depth_km, 30)) / 30) * 15
    raw = base + shallow_bonus

    mult = _risk_multiplier(lat, lon)
    score = min(100.0, round(raw * mult, 1))

    if score >= 70:
        level = "critical"
    elif score >= 45:
        level = "high"
    elif score >= 25:
        level = "moderate"
    else:
        level = "low"

    cz = _in_zone(lat, lon, _CRITICAL_ZONES)
    nz = _in_zone(lat, lon, _NUCLEAR_ZONES)

    return {"score": score, "level": level,
            "critical_zones": cz, "nuclear_zones": nz,
            "risk_multiplier": mult}


# ── USGS 数据获取 ────────────────────────────────────────────────────────────

def _fetch_usgs(url: str, timeout: int = 15) -> list[dict]:
    """拉取 USGS GeoJSON，返回标准化事件列表。"""
    if not _REQ_OK:
        return []
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        events = []
        for f in features:
            props = f.get("properties", {})
            coords = f.get("geometry", {}).get("coordinates", [None, None, None])
            lon, lat, depth = coords[0], coords[1], coords[2] or 0
            mag = props.get("mag", 0) or 0
            if lat is None or lon is None:
                continue
            risk = _compute_event_risk(mag, depth, lat, lon)
            events.append({
                "id":         f.get("id", ""),
                "time_utc":   datetime.fromtimestamp(
                                props.get("time", 0) / 1000, tz=timezone.utc
                              ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "magnitude":  round(mag, 1),
                "depth_km":   round(depth, 1),
                "lat":        round(lat, 3),
                "lon":        round(lon, 3),
                "location":   props.get("place", "Unknown"),
                "url":        props.get("url", ""),
                **risk,
            })
        return events
    except Exception as e:
        print(f"  [disaster] USGS 拉取失败: {e}")
        return []


# ── 风险汇总 ─────────────────────────────────────────────────────────────────

def _summarize(events: list[dict]) -> dict:
    """汇总当日地震事件，生成 disaster_risk_score 和关键预警。"""
    if not events:
        return {
            "disaster_risk_score": 0,
            "risk_level": "low",
            "event_count_24h": 0,
            "significant_events": [],
            "alerts": [],
        }

    # 取风险分最高的5条
    sorted_events = sorted(events, key=lambda x: -x["score"])
    top_score = sorted_events[0]["score"] if sorted_events else 0

    # 汇总风险
    alerts = []
    significant = []
    for ev in sorted_events[:5]:
        if ev["score"] >= 25:
            significant.append({
                "magnitude":    ev["magnitude"],
                "location":     ev["location"],
                "time_utc":     ev["time_utc"],
                "score":        ev["score"],
                "level":        ev["level"],
                "critical_zones": ev["critical_zones"],
                "nuclear_zones":  ev["nuclear_zones"],
            })
        if ev["critical_zones"]:
            alerts.append(
                f"M{ev['magnitude']} 震中位于关键供应链区域：{', '.join(ev['critical_zones'])}"
            )
        if ev["nuclear_zones"]:
            alerts.append(
                f"M{ev['magnitude']} 震中位于核电密集区：{', '.join(ev['nuclear_zones'])} ⚠️"
            )

    if top_score >= 70:
        risk_level = "critical"
    elif top_score >= 45:
        risk_level = "high"
    elif top_score >= 25:
        risk_level = "moderate"
    else:
        risk_level = "low"

    return {
        "disaster_risk_score": round(top_score, 1),
        "risk_level":          risk_level,
        "event_count_24h":     len(events),
        "significant_events":  significant,
        "alerts":              list(dict.fromkeys(alerts)),  # 去重
    }


# ── 主入口 ───────────────────────────────────────────────────────────────────

def fetch_and_save() -> dict:
    """采集地震信号，保存到 disaster_signals.json，返回数据字典。"""
    print("[fetch_disaster_signals] 开始采集地震信号...")

    # 拉取重大事件（M≥5.0级别）
    events = _fetch_usgs(USGS_M25_URL)
    print(f"  USGS: 获取到 {len(events)} 条地震事件（过去24h）")

    summary = _summarize(events)

    result = {
        "fetched_at":          datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disaster_risk_score": summary["disaster_risk_score"],
        "risk_level":          summary["risk_level"],
        "event_count_24h":     summary["event_count_24h"],
        "significant_events":  summary["significant_events"],
        "alerts":              summary["alerts"],
        "_schema_version":     "1.0",  # 开阳 R-4 契约：feed 需带 schema_version
        "latest_significant":  summary["significant_events"][0]
                               if summary["significant_events"] else None,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DISASTER_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    level = result["risk_level"]
    score = result["disaster_risk_score"]
    print(f"[fetch_disaster_signals] 完成：risk={level}（{score}）"
          f" 事件数={result['event_count_24h']}"
          f" 告警={len(result['alerts'])}条")

    if result["alerts"]:
        for a in result["alerts"]:
            print(f"  ⚠ {a}")

    return result


def get_context() -> str:
    """返回灾害信号摘要字符串，供 LLM prompt 注入。"""
    if not os.path.exists(DISASTER_OUTPUT):
        return ""
    try:
        with open(DISASTER_OUTPUT, encoding="utf-8") as f:
            data = json.load(f)
        score = data.get("disaster_risk_score", 0)
        if score < 25:
            return ""  # 低风险不注入
        level = data.get("risk_level", "low")
        alerts = data.get("alerts", [])
        sig = data.get("significant_events", [])

        lines = [f"[自然灾害信号] 风险等级={level}（{score}/100）"]
        for ev in sig[:2]:
            cz_str = f"，位于{', '.join(ev['critical_zones'])}" if ev["critical_zones"] else ""
            nz_str = " ⚠️核电区" if ev["nuclear_zones"] else ""
            lines.append(
                f"  M{ev['magnitude']} {ev['location'][:40]}{cz_str}{nz_str}"
            )
        if alerts:
            lines.append(f"  预警：{alerts[0]}")
        return "\n".join(lines)
    except Exception:
        return ""


if __name__ == "__main__":
    result = fetch_and_save()
    print("\n--- 灾害信号摘要 ---")
    ctx = get_context()
    print(ctx if ctx else "当前无显著地震风险（score < 25）")
