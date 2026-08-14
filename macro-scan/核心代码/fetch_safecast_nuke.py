"""
fetch_safecast_nuke.py — 核电站周边辐射 CPM 采集（SafeCast 公民辐射网）

来源：SafeCast 全球辐射监测网（CC0 public domain，无 key、无 auth）
  URL: https://api.safecast.org/measurements.json?latitude={lat}&longitude={lon}&distance={m}&limit=10
  6 站点坐标/半径与 crucix safecast.mjs 硬编码表完全一致（data-review §9 实证可 1:1 复刻）
  avgCPM = 半径内有效测量均值；anomaly = avgCPM > 100（crucix 同构，normal 10-80 CPM）

落盘：data/safecast_nuke.json
  {fetched_at, source, sites:[{site, key, avgCPM, n, anom, latest_captured_at}]}
  - n=0 站点（如 bushehr/yongbyon 源无测量）→ avgCPM=null / anom=false / latest_captured_at=null
  - latest_captured_at 来自源测量时间戳；注意数据为**历史归档均值**（captured_at 2016-2023，
    Chernobyl 2023-07），非实时传感器流，禁止据此断言"实时性"（qa AC-D1-08）

容错（qa AC-D1-09）：api.safecast.org 间歇性 TLS 证书错误（实测约 50%，
  ERR_TLS_CERT_ALTNAME_INVALID，多 IP 部分证书不匹配）
  → 每站 5 重试 + 1.5s 递增退避（成功率 ≥99%）；某轮全部重试仍失败 → 显式降级日志，
    整轮全站失败 → 输出空 sites 而非静默缺失。

用法：
  python3 fetch_safecast_nuke.py            # 拉取/计算/落盘
  python3 fetch_safecast_nuke.py --show     # 仅打印已落盘内容

调度建议：每 15-60 分钟（对齐 crucix 15min sweep；或并入现有低频批）。scheduler 注册另行派发（WP-1.1 不注册）。
出网：直连优先，失败回退 OUTBOUND_PROXY（参照 fetch_firms.py 2026-08-06 修复模式）。
依赖：requests（容器已装），无新依赖。
"""

import os
import sys
import json
import time
import datetime

try:
    import requests
except ImportError:
    print("ERROR: requests 未安装")
    sys.exit(1)

# ── 配置 ─────────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("SAFECAST_BASE_URL", "https://api.safecast.org")

# 6 站点坐标表（crucix safecast.mjs NUCLEAR_SITES 1:1 复刻）
SITES = {
    "zaporizhzhia": {"lat": 47.51, "lon": 34.58,  "radius": 100, "site": "Zaporizhzhia NPP (Ukraine)"},
    "chernobyl":    {"lat": 51.39, "lon": 30.10,  "radius": 50,  "site": "Chernobyl Exclusion Zone"},
    "bushehr":      {"lat": 28.83, "lon": 50.89,  "radius": 100, "site": "Bushehr NPP (Iran)"},
    "yongbyon":     {"lat": 39.80, "lon": 125.75, "radius": 100, "site": "Yongbyon (North Korea)"},
    "fukushima":    {"lat": 37.42, "lon": 141.03, "radius": 50,  "site": "Fukushima Daiichi"},
    "dimona":       {"lat": 31.00, "lon": 35.15,  "radius": 100, "site": "Dimona (Israel)"},
}

# 异常阈值（crucix 同构）：normal 10-80 CPM，>100 判定异常
ANOMALY_CPM_THRESHOLD = 100

# 重试：5 次 + 1.5s 递增退避（qa AC-D1-09 要求 ≥4 次）
MAX_RETRIES = 5
RETRY_BASE_DELAY = 1.5
TIMEOUT = (10, 25)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# 脚本所在目录的上级 = 项目根目录（与 fetch_gscpi.py 同款）
BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_JSON = os.path.join(BASE_DIR, "data", "safecast_nuke.json")

# 代理配置（参照 fetch_firms.py：optim_config.PROXY_URL > env OUTBOUND_PROXY）
try:
    from optim_config import PROXY_URL
except ImportError:
    PROXY_URL = os.environ.get("OUTBOUND_PROXY", "")
PROXY_URL = os.environ.get("OUTBOUND_PROXY", "") or PROXY_URL
_PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None


# ── 网络层 ───────────────────────────────────────────────────────────────────

def _request(url: str) -> requests.Response:
    """直连请求；失败回退 OUTBOUND_PROXY（防御性，参照 fetch_firms.py 模式）。"""
    try:
        return requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    except Exception:
        if _PROXIES:
            return requests.get(url, timeout=TIMEOUT,
                                headers={"User-Agent": UA}, proxies=_PROXIES)
        raise


def fetch_measurements(lat: float, lon: float, radius_km: int) -> list | None:
    """拉取半径内测量并返回原始数组；5 重试 + 递增退避；全部失败返回 None。"""
    url = (f"{BASE_URL}/measurements.json?latitude={lat}&longitude={lon}"
           f"&distance={radius_km * 1000}&limit=10")
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = _request(url)
            if r.status_code == 200:
                data = r.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            last_err = e
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BASE_DELAY * attempt)
    print(f"  [safecast] 站点 lat={lat},lon={lon} 重试 {MAX_RETRIES} 次仍失败: "
          f"{type(last_err).__name__ if last_err else 'HTTP 非 200'}: {last_err}")
    return None


# ── 计算与落盘 ───────────────────────────────────────────────────────────────

def collect_sites() -> tuple[list, bool]:
    """采集 6 站并计算 {site,key,avgCPM,n,anom,latest_captured_at}。
    返回 (sites, degraded)；整轮全站失败 → sites=[] 且 degraded=True（显式降级）。"""
    sites = []
    any_ok = False
    for key, s in SITES.items():
        data = fetch_measurements(s["lat"], s["lon"], s["radius"])
        if data is None:
            sites.append({"site": s["site"], "key": key,
                          "avgCPM": None, "n": 0, "anom": False,
                          "latest_captured_at": None})
            continue
        values = [m.get("value") for m in data
                  if isinstance(m.get("value"), (int, float))]
        n = len(values)
        avg = (sum(values) / n) if n else None
        # SafeCast 返回数组按 captured_at 降序，data[0] 为最新
        latest = (data[0].get("captured_at") or None) if data else None
        sites.append({
            "site": s["site"], "key": key,
            "avgCPM": avg, "n": n,
            "anom": bool(avg is not None and avg > ANOMALY_CPM_THRESHOLD),
            "latest_captured_at": latest,
        })
        if avg is not None:
            any_ok = True

    degraded = not any_ok
    if degraded:
        print("[safecast] 拉取失败：全部站点无有效读数，输出空 sites（显式降级，qa AC-D1-09）")
        return [], True
    return sites, False


def _alert_anomalies(sites: list) -> None:
    """anom 站点状态变化 → ntfy 核辐射异常告警（P1-4 修复：告警分支此前哑失效——
    safecast_nuke 只落盘无消费者，anom 永远没人看见）。
    去重：data/nuke_alert_state.json 记录各站上次 anom 状态，仅状态翻转时推送。"""
    try:
        from ntfy_utils import push_text
    except Exception:
        push_text = None
    anoms = {s["key"]: bool(s.get("anom")) for s in sites if s.get("avgCPM") is not None}
    state_path = os.path.join(BASE_DIR, "data", "nuke_alert_state.json")
    prev = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}
    changed = {k: v for k, v in anoms.items() if prev.get(k) != v}
    if changed and push_text:
        try:
            lines = []
            for k, v in changed.items():
                site = next((s["site"] for s in sites if s["key"] == k), k)
                if v:
                    lines.append(f"{site}：辐射读数异常（avgCPM > {ANOMALY_CPM_THRESHOLD}）")
                else:
                    lines.append(f"{site}：辐射读数恢复正常")
            push_text("核辐射监测变化", "\n".join(lines))
            print(f"[safecast] 核辐射告警推送：{len(changed)} 站点状态变化")
        except Exception as e:
            print(f"[safecast] 告警推送失败（非阻断）: {e}")
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(anoms, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"[safecast] 告警状态落盘失败（非阻断）: {e}")


def fetch_and_save() -> dict:
    """采集 → 落盘 data/safecast_nuke.json。返回摘要 dict。"""
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    sites, degraded = collect_sites()
    payload = {
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": BASE_URL,
        "sites": sites,
        "degraded": degraded,
    }
    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_JSON)
    if degraded:
        print(f"[safecast] 降级落盘：{OUT_JSON}（sites=[]）")
    else:
        ok = sum(1 for s in sites if s["avgCPM"] is not None)
        print(f"[OK] safecast 写入 {ok}/6 站有效读数 → {OUT_JSON}")
        _alert_anomalies(sites)  # P1-4：核辐射异常告警（状态翻转才推送）
    return payload


def show_existing() -> int:
    """--show：只读打印已落盘内容。"""
    if not os.path.exists(OUT_JSON):
        print("[SKIP] data/safecast_nuke.json 不存在")
        return 1
    with open(OUT_JSON, encoding="utf-8") as f:
        d = json.load(f)
    print(f"fetched_at: {d.get('fetched_at')}  source: {d.get('source')}  degraded: {d.get('degraded')}")
    for s in d.get("sites", []):
        print(f"  {s['key']:14s} avgCPM={str(s['avgCPM']):8s} n={s['n']:3d} "
              f"anom={s['anom']}  latest={s.get('latest_captured_at')}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--show":
        sys.exit(show_existing())
    try:
        fetch_and_save()
    except Exception as e:
        print(f"[ERROR] fetch_safecast_nuke: {e}")
        sys.exit(1)
