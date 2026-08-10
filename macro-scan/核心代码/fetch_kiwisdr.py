"""
fetch_kiwisdr.py — KiwiSDR 全球无线电接收器网络目录采集（sdr 弱信号源）

来源：rx.skywavelinux.com/kiwisdr_com.js（官方目录自动生成，日更 1-2 次）
  容器内实测：直连失败（DNS 不可达），OUTBOUND_PROXY 200 / 890,320B / 839 台接收器
  每台含 gps"(lat, lon)" / loc(国家文本) / grid(Maidenhead) / status / users 等 30+ 字段

解析坑（data-review §8 实测）：非纯 JSON
  1. 文件头注释行 + `var kiwisdr_com = [...]` 前缀 → regex 截取数组体
  2. 数组含尾逗号 → `re.sub(r",\s*\]", "]", ...)` 清洗后 json.loads

区域判定（arch ADR-10 定稿）：zones_rule 写死留痕（loc 国家关键词 + gps bbox 双层）
  zone→dimension 映射见 ZONES_RULE（天枢语义优先，不追求 1:1 复刻 crucix 归属）

落盘：data/sdr_summary.json
  {fetched_at, source, total, online, offline,
   zones:[{region,count,receivers:[{name,lat,lon}],dimension}],
   receivers:[839 台全量明细], zones_rule, articles}   # articles 供 narrative 弱信号摄取

消费方（arch ADR-04/10）：run_daily_narrative_processing json_sources
  + (sdr_summary.json, "kiwisdr_sdr", "description") → narrative_chunks 弱信号
  GRV/regime/data_fetcher 零改动（sdr 不进 _crucix，独立产物）

用法：
  python3 fetch_kiwisdr.py            # 拉取/解析/落盘
  python3 fetch_kiwisdr.py --show     # 仅打印已落盘内容

调度建议：日频 06:00 或每 6h（目录日更 1-2 次）。scheduler 注册另行派发（WP-1.2 不注册）。
出网：直连优先，失败回退 OUTBOUND_PROXY（参照 fetch_firms.py 2026-08-06 修复模式）。
依赖：requests（容器已装），无新依赖。
"""

import os
import sys
import re
import json
import time
import datetime

try:
    import requests
except ImportError:
    print("ERROR: requests 未安装")
    sys.exit(1)

# ── 配置 ─────────────────────────────────────────────────────────────────────

KIWISDR_URL = "https://rx.skywavelinux.com/kiwisdr_com.js"
MAX_RETRIES = 3          # 目录拉取低频，3 重试足够（非 TLS 间歇类源，但防御代理抖动）
RETRY_BASE_DELAY = 2.0
TIMEOUT = (15, 60)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_JSON = os.path.join(BASE_DIR, "data", "sdr_summary.json")

try:
    from optim_config import PROXY_URL
except ImportError:
    PROXY_URL = os.environ.get("OUTBOUND_PROXY", "")
PROXY_URL = os.environ.get("OUTBOUND_PROXY", "") or PROXY_URL
_PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None


# ── 区域规则（arch ADR-10 定稿，写死留痕） ──────────────────────────────────

# 判定优先级：先 loc 关键词（更精确），再 gps bbox（兜底，具体区先判避免重叠区误归）
ZONES_RULE = {
    "Taiwan Strait": {
        "dimension": "taiwan_strait",
        "loc_keywords": ["taiwan", "taoyuan", "kaohsiung", "taichung", "tainan", "hsinchu", "formosa"],
        "bbox": (21, 27, 119, 122.5),      # (lat_min, lat_max, lon_min, lon_max)
    },
    "South China Sea": {
        "dimension": "taiwan_strait",      # 西太同桶（GRV 无 scs 独立维度）
        "loc_keywords": ["vietnam", "philippines", "malaysia", "brunei", "singapore",
                         "hanoi", "manila", "kuala lumpur", "saigon", "ho chi minh"],
        "bbox": (3, 22, 105, 120),
    },
    "Ukraine / Eastern Europe": {
        "dimension": "russia_europe",
        "loc_keywords": ["ukraine", "kyiv", "kiev", "kharkiv", "odesa", "lviv", "dnipro",
                         "poland", "romania", "moldova", "hungary", "slovakia"],
        "bbox": (44, 54, 22, 40),
    },
    "Baltic Region": {
        "dimension": "russia_europe",      # 与俄欧同桶（NATO 东翼）
        "loc_keywords": ["estonia", "latvia", "lithuania", "tallinn", "riga", "vilnius",
                         "kaliningrad"],
        "bbox": (53, 61, 18, 29),
    },
    "Middle East": {
        "dimension": "middle_east_energy",
        "loc_keywords": ["israel", "jordan", "lebanon", "syria", "iraq", "saudi", "kuwait",
                         "qatar", "bahrain", "oman", "yemen", "emirates", "dubai",
                         "jerusalem", "tel aviv", "amman", "beirut", "damascus", "baghdad"],
        "bbox": (25, 40, 34, 60),
    },
    "Iran": {
        "dimension": "middle_east_energy",  # 中东能源风险核心
        "loc_keywords": ["iran", "persia", "tehran", "mashhad", "isfahan", "shiraz"],
        "bbox": (25, 40, 44, 63),
    },
    "Korean Peninsula": {
        "dimension": "us_china_strategic",  # 朝核为中美战略博弈子集
        "loc_keywords": ["korea", "seoul", "busan", "incheon", "pyongyang"],
        "bbox": (33, 43, 124, 130),
    },
    "Sahel / West Africa": {
        "dimension": "global_composite",    # 兜底维度（无专属热点）
        "loc_keywords": ["mali", "niger", "chad", "mauritania", "senegal", "guinea",
                         "ghana", "nigeria", "benin", "burkina", "cote d", "cameroon",
                         "dakar", "bamako", "niamey", "lagos", "abidjan"],
        "bbox": (8, 20, -18, 15),
    },
}
# 重叠区判定顺序（bbox 兜底时具体区优先，避免 Iran 被 Middle East 吞、Taiwan 被 SCS 吞）
_BBOX_ORDER = ["Iran", "Taiwan Strait", "Baltic Region", "Ukraine / Eastern Europe",
               "Korean Peninsula", "South China Sea", "Middle East", "Sahel / West Africa"]


def _in_bbox(lat: float, lon: float, bbox: tuple) -> bool:
    lat_min, lat_max, lon_min, lon_max = bbox
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def classify_zone(loc: str, lat: float, lon: float) -> str | None:
    """loc 关键词优先，gps bbox 兜底 → zone 名（无归属返回 None）。"""
    loc_lower = (loc or "").lower()
    if loc_lower:
        for zone, rule in ZONES_RULE.items():
            if any(kw in loc_lower for kw in rule["loc_keywords"]):
                return zone
    if lat is not None and lon is not None:
        for zone in _BBOX_ORDER:
            if _in_bbox(lat, lon, ZONES_RULE[zone]["bbox"]):
                return zone
    return None


def _parse_gps(gps: str) -> tuple:
    m = re.match(r"\(([-\d.]+),\s*([-\d.]+)\)", gps or "")
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


# ── 网络层 ───────────────────────────────────────────────────────────────────

def _request(url: str) -> requests.Response:
    """直连请求；失败回退 OUTBOUND_PROXY（防御性，KiwiSDR 容器内直连不可达）。"""
    try:
        return requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    except Exception:
        if _PROXIES:
            return requests.get(url, timeout=TIMEOUT,
                                headers={"User-Agent": UA}, proxies=_PROXIES)
        raise


def fetch_js() -> str | None:
    """拉取 kiwisdr_com.js 全文；3 重试 + 递增退避；全部失败返回 None。"""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = _request(KIWISDR_URL)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            last_err = e
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BASE_DELAY * attempt)
    print(f"[kiwisdr] 拉取失败（{MAX_RETRIES} 重试耗尽）: "
          f"{type(last_err).__name__ if last_err else 'HTTP 非 200'}: {last_err}")
    return None


# ── 解析 ─────────────────────────────────────────────────────────────────────

def parse_js(text: str) -> list | None:
    """JS 容错解析：regex 截取数组 + 尾逗号清洗 + json.loads。失败返回 None。"""
    m = re.search(r"var\s+kiwisdr_com\s*=\s*(\[.*)\]", text, re.S)
    if not m:
        print("[kiwisdr] JS 结构异常：未匹配到 kiwisdr_com 数组")
        return None
    cleaned = re.sub(r",\s*\]", "]", m.group(1) + "]")
    try:
        data = json.loads(cleaned)
    except Exception as e:
        print(f"[kiwisdr] JSON 解析失败: {e}")
        return None
    return data if isinstance(data, list) else None


# ── 组装与落盘 ───────────────────────────────────────────────────────────────

def build_summary(data: list) -> dict:
    """839 台 → sdr_summary.json（含 zones/receivers/articles）。"""
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    total = len(data)
    online = sum(1 for r in data if str(r.get("status", "")).lower() == "active"
                 or str(r.get("offline", "")).lower() == "no")
    offline = total - online

    zones = []
    receivers_detail = []
    for r in data:
        lat, lon = _parse_gps(r.get("gps"))
        receivers_detail.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "lat": lat, "lon": lon,
            "loc": r.get("loc"),
            "grid": r.get("grid"),
            "status": r.get("status"),
            "users": r.get("users"),
            "updated": r.get("updated"),
        })

    # 按 zone 分组（接收器可能无 gps/loc → 不归属任何区，仍保留在 receivers 明细）
    zone_counts = {z: [] for z in ZONES_RULE}
    for r, detail in zip(data, receivers_detail):
        lat, lon = detail["lat"], detail["lon"]
        zone = classify_zone(detail["loc"], lat, lon)
        if zone:
            zone_counts[zone].append({
                "name": detail["name"],
                "lat": lat, "lon": lon,
            })

    for zone, rule in ZONES_RULE.items():
        recv = zone_counts[zone]
        zones.append({
            "region": zone,
            "count": len(recv),
            "receivers": recv,
            "dimension": rule["dimension"],
        })

    # narrative 弱信号摄取视图（arch ADR-04：zone 在线分布变化 → 地缘弱信号）
    articles = []
    for z in zones:
        if z["count"] > 0:
            articles.append({
                "title": f"[kiwisdr] {z['region']}",
                "description": (f"KiwiSDR 无线电网络 {z['region']} 区 {z['count']} 台在线"
                                f"（全球 {online}/{total} 台，dimension={z['dimension']}）"),
                "published_at": fetched_at,
            })

    return {
        "fetched_at": fetched_at,
        "source": KIWISDR_URL,
        "total": total,
        "online": online,
        "offline": offline,
        "zones": zones,
        "receivers": receivers_detail,
        "zones_rule": {z: {"dimension": r["dimension"], "bbox": r["bbox"]}
                       for z, r in ZONES_RULE.items()},
        "articles": articles,
    }


def _write(payload: dict) -> None:
    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_JSON)


def _degraded_payload() -> dict:
    return {
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": KIWISDR_URL,
        "total": 0, "online": 0, "offline": 0,
        "zones": [], "receivers": [],
        "zones_rule": {z: {"dimension": r["dimension"], "bbox": r["bbox"]}
                       for z, r in ZONES_RULE.items()},
        "articles": [], "degraded": True,
    }


def fetch_and_save() -> dict:
    """拉取 → 解析 → 落盘 data/sdr_summary.json。返回摘要 dict。"""
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    text = fetch_js()
    if text is None:
        print("[kiwisdr] 拉取失败：输出空结构（显式降级，禁止静默缺失）")
        payload = _degraded_payload()
        _write(payload)
        return payload

    data = parse_js(text)
    if data is None:
        print("[kiwisdr] 解析失败：输出空结构（显式降级，禁止静默缺失）")
        payload = _degraded_payload()
        _write(payload)
        return payload

    payload = build_summary(data)
    _write(payload)
    ok_zones = sum(1 for z in payload["zones"] if z["count"] > 0)
    print(f"[OK] kiwisdr 写入 {payload['total']} 台（online={payload['online']}），"
          f"{ok_zones}/{len(ZONES_RULE)} 区有接收器 → {OUT_JSON}")
    return payload


def show_existing() -> int:
    """--show：只读打印已落盘内容。"""
    if not os.path.exists(OUT_JSON):
        print("[SKIP] data/sdr_summary.json 不存在")
        return 1
    with open(OUT_JSON, encoding="utf-8") as f:
        d = json.load(f)
    print(f"fetched_at: {d.get('fetched_at')}  source: {d.get('source')}")
    print(f"total={d.get('total')} online={d.get('online')} offline={d.get('offline')} "
          f"degraded={d.get('degraded', False)}")
    for z in d.get("zones", []):
        print(f"  {z['region']:26s} count={z['count']:4d}  dim={z['dimension']}")
    print(f"articles: {len(d.get('articles', []))} 条弱信号视图")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--show":
        sys.exit(show_existing())
    try:
        fetch_and_save()
    except Exception as e:
        print(f"[ERROR] fetch_kiwisdr: {e}")
        sys.exit(1)
