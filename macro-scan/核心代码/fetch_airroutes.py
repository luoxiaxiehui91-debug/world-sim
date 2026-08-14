#!/usr/bin/env python3
"""
fetch_airroutes.py — OpenFlights 全球航线网（airports.dat + routes.dat）

拉全球公开航线数据，聚合「主要航线走廊」供开阳 air 图层画航线网
（08-14 主理人拍板：air 图层从 6182 实时飞机点改为静态全球航线网——
OpenSky ADS-B 在非洲/中国/俄罗斯内陆接收器稀疏，实时点有覆盖盲区；
航线网是结构数据，全球主要航线（含上述区域上空国际干线）完整无盲区）。

数据源（OpenFlights，CC BY-SA 4.0；数据约 2014 年冻结，全球主要航线结构稳定）：
  - airports.dat（约 7 千机场）: id,name,city,country,IATA,ICAO,lat,lng,alt,tz,dst,tzdb
  - routes.dat（约 6.7 万航线）: airline,airline_id,src,src_id,dst,dst_id,codeshare,stops,equip

实现要点：
  - 复用 FetcherBase：request/save_json/load_config_with_fallback。
  - 直连优先，失败回退代理（fetch_airtraffic_opensky._get 模式）。
  - _aggregate()：
      1) airports.dat 全量解析 id → (iata, lat, lng)；"\\N" 缺失值容错
      2) routes.dat 过滤直飞（stops==0）+ 非 codeshare，按机场对聚合频次
      3) 双向合并（PEK↔JFK 同一条航线），key = 排序后的机场 id 对
      4) 按频次取 top 500 主要航线（含两端 IATA + 坐标）
  - as_of = 生成时刻 ISO UTC+Z。

输出契约：data/airroutes.json
  {
    "status": "ok",
    "source": "OpenFlights airports.dat + routes.dat (CC BY-SA 4.0, ~2014)",
    "as_of": "2026-08-14T07:10:00Z",
    "scope": "global",
    "schema_version": 1,
    "routes_count": 500,
    "routes": [
      {"from": "PEK", "from_lat": 40.08, "from_lng": 116.58,
       "to": "JFK", "to_lat": 40.64, "to_lng": -73.78, "flights": 12},
      ...
    ]
  }

调度：scheduler.py 0950 日档（航线结构以年为单位稳定，日更已远超所需）。
feeds_grv=False，仅落盘供下游消费。
"""
import csv
import io
import datetime
from datetime import timezone
from collections import defaultdict

from fetcher_base import FetcherBase, Status

# ── 配置回退（统一取代重复 ImportError 块）────────────────────
_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR", "PROXY_URL"],
    {
        "DATA_DIR": FetcherBase.default_data_dir(),
        "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
    },
)
DATA_DIR = _cfg["DATA_DIR"]
PROXY_URL = _cfg["PROXY_URL"]

OUTPUT_FILE = "airroutes.json"
AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
ROUTES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/plain",
}

TOP_ROUTES = 500  # 前端 2D/3D 弧渲染的合理密度；可调


class AirRoutesFetcher(FetcherBase):
    """OpenFlights 全球航线网采集器：拉 airports+routes 并聚合主要航线。"""

    name = "airroutes"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0950"  # 日档（结构数据，日更已远超所需）

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        # 直连优先；直连失败再回退代理（与 fetch_airtraffic_opensky._get 模式一致）
        self.proxies = None

    # ── 网络出口：直连优先，失败回退代理 ────────────────────────
    def _get_text(self, url, timeout=30):
        r = self.request(url, headers=HEADERS, timeout=timeout)
        if r is not None:
            return r.text
        if PROXY_URL:
            self.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            r = self.request(url, headers=HEADERS, timeout=timeout)
            if r is not None:
                return r.text
        return None

    # ── 解析 airports.dat → id → (iata, lat, lng) ─────────────
    def _parse_airports(self, text):
        airports = {}
        for row in csv.reader(io.StringIO(text)):
            if len(row) < 8:
                continue
            try:
                aid = int(row[0])
                iata = row[4] if len(row) > 4 and row[4] and row[4] != "\\N" else ""
                lat = float(row[6])
                lng = float(row[7])
            except (ValueError, IndexError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                continue
            airports[aid] = (iata, lat, lng)
        return airports

    # ── 解析 routes.dat → 聚合主要航线 ─────────────────────────
    def _aggregate_routes(self, text, airports):
        freq = defaultdict(int)
        endpoints = {}  # (a_id, b_id) → (from_code, to_code, from_lat, from_lng, to_lat, to_lng)
        for row in csv.reader(io.StringIO(text)):
            if len(row) < 9:
                continue
            src_id, dst_id = row[3], row[5]
            codeshare = row[6] if len(row) > 6 else ""
            stops = row[7] if len(row) > 7 else ""
            try:
                a_id, b_id = int(src_id), int(dst_id)
                stops_n = int(stops) if stops else 0
            except ValueError:
                continue
            if codeshare or stops_n != 0:
                continue
            if a_id not in airports or b_id not in airports or a_id == b_id:
                continue
            key = (a_id, b_id) if a_id < b_id else (b_id, a_id)
            freq[key] += 1
            if key not in endpoints:
                a_iata, a_lat, a_lng = airports[a_id]
                b_iata, b_lat, b_lng = airports[b_id]
                endpoints[key] = (a_iata, b_iata, a_lat, a_lng, b_lat, b_lng)

        routes = []
        for key, flights in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:TOP_ROUTES]:
            a_iata, b_iata, a_lat, a_lng, b_lat, b_lng = endpoints[key]
            routes.append({
                "from": a_iata or str(key[0]),
                "from_lat": round(a_lat, 4),
                "from_lng": round(a_lng, 4),
                "to": b_iata or str(key[1]),
                "to_lat": round(b_lat, 4),
                "to_lng": round(b_lng, 4),
                "flights": flights,
            })
        return routes

    # ── 采集入口 ──────────────────────────────────────────────
    def collect(self):
        ap_text = self._get_text(AIRPORTS_URL, timeout=30)
        if not ap_text:
            self.logger.warning("[airroutes] airports.dat 请求失败，降级")
            return None
        airports = self._parse_airports(ap_text)
        if len(airports) < 1000:
            self.logger.warning("[airroutes] airports 解析异常（<1000），降级: %d", len(airports))
            return None

        rt_text = self._get_text(ROUTES_URL, timeout=30)
        if not rt_text:
            self.logger.warning("[airroutes] routes.dat 请求失败，降级")
            return None
        routes = self._aggregate_routes(rt_text, airports)
        if len(routes) < 100:
            self.logger.warning("[airroutes] routes 聚合异常（<100），降级: %d", len(routes))
            return None

        as_of = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "status": Status.OK,
            "source": "OpenFlights airports.dat + routes.dat (CC BY-SA 4.0, ~2014)",
            "as_of": as_of,
            "scope": "global",
            "schema_version": "1",
            "routes_count": len(routes),
            "airports_indexed": len(airports),
            "routes": routes,
        }


def _make_unavailable():
    """首跑无良值时写的 unavailable 标记。"""
    return {
        "status": Status.UNAVAILABLE,
        "source": "OpenFlights airports.dat + routes.dat (CC BY-SA 4.0, ~2014)",
        "as_of": datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "global",
        "schema_version": "1",
        "routes_count": 0,
        "airports_indexed": 0,
        "routes": [],
    }


def main():
    fetcher = AirRoutesFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[airroutes] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == Status.OK:
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[airroutes] 完成 status=ok，routes_count="
              f"{result.get('routes_count')}，airports_indexed={result.get('airports_indexed')}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[airroutes] 降级，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, _make_unavailable())
            print("[airroutes] 降级，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()

