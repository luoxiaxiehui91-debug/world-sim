#!/usr/bin/env python3
"""
fetch_airtraffic_opensky.py — OpenSky Network 全球在飞航班快照（/api/states/all）

不限定 bbox，拉全球实时 states（主理人拍板 Q2）；聚合在飞航班数、平均气压高度/速度、
起飞机场国 Top5。

实现要点（详见架构设计 §1.2 / §3.3 / §7）：
  - 复用 FetcherBase：request/save_json/load_previous_good/load_config_with_fallback。
  - collect() → request(GET /api/states/all) → response.json()["states"]（17 字段数组）。
  - _aggregate()：过滤 on_ground==false（索引8）得在飞；计算指标。
  - 直连优先，失败回退代理（fetch_fao._get 模式）。
  - as_of 来自 response.json()["time"]（Unix 秒 → ISO UTC+Z）。scope 固定 "global"。
  - 带单位字段明确标注：高度 m、速度 m/s。

输出契约：data/airtraffic_opensky.json
  {
    "status":            "ok",
    "source":            "OpenSky Network /api/states/all",
    "as_of":             "2026-07-28T14:00:00Z",
    "scope":             "global",
    "flights_in_air":    int,
    "avg_altitude_m":    float|null,
    "avg_velocity_ms":   float|null,
    "top_origin_countries": [{"country":..., "count":..., "pct":...}],
    "total_states":      int,
    "sample_limited":    false
  }

调度：scheduler.py 06:28（日频，错峰）。feeds_grv=False，仅落盘供下游消费。
"""
import os
import logging
import datetime
from datetime import timezone
from collections import Counter

import requests
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

OUTPUT_FILE = "airtraffic_opensky.json"
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# OpenSky state 17 字段顺序索引（详见架构设计附录）
IDX_ORIGIN_COUNTRY = 2   # origin_country
IDX_BARO_ALT = 7         # baro_altitude
IDX_ON_GROUND = 8        # on_ground
IDX_VELOCITY = 9         # velocity


class AirTrafficOpenSkyFetcher(FetcherBase):
    """OpenSky 全球在飞航班快照采集器：拉全球 states 并聚合。"""

    name = "airtraffic_opensky"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0628"

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        # 直连优先；直连失败再回退代理（与 fetch_fao._get 模式一致）
        self.proxies = None

    # ── 网络出口：直连优先，失败回退代理 ────────────────────────
    def _get(self, url, params=None, headers=None, timeout=30):
        r = self.request(url, params=params, headers=headers, timeout=timeout)
        if r is not None:
            return r
        if PROXY_URL:
            self.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            return self.request(url, params=params, headers=headers, timeout=timeout)
        return None

    # ── 聚合 states → 输出 dict ───────────────────────────────
    def _aggregate(self, states, as_of):
        """聚合 states → 输出 dict（status=ok）。states 已校验非空。"""
        total_states = len(states)

        # 在飞：on_ground == false（索引8）
        in_air = [
            s for s in states
            if len(s) > IDX_ON_GROUND and s[IDX_ON_GROUND] is False
        ]
        flights_in_air = len(in_air)

        # 平均气压高度（排除 None / 地面）
        alts = [
            s[IDX_BARO_ALT] for s in in_air
            if len(s) > IDX_BARO_ALT and s[IDX_BARO_ALT] is not None
        ]
        avg_altitude_m = (sum(alts) / len(alts)) if alts else None

        # 平均速度（排除 None）
        vels = [
            s[IDX_VELOCITY] for s in in_air
            if len(s) > IDX_VELOCITY and s[IDX_VELOCITY] is not None
        ]
        avg_velocity_ms = (sum(vels) / len(vels)) if vels else None

        # 起飞机场国计数 Top5 + pct
        countries = [
            s[IDX_ORIGIN_COUNTRY] for s in in_air
            if len(s) > IDX_ORIGIN_COUNTRY and s[IDX_ORIGIN_COUNTRY]
        ]
        top_origin_countries = []
        if countries:
            counter = Counter(countries)
            total_in_air = len(countries)
            for country, count in counter.most_common(5):
                pct = round(count / total_in_air * 100, 2)
                top_origin_countries.append({
                    "country": country,
                    "count": count,
                    "pct": pct,
                })

        return {
            "status": Status.OK,
            "source": "OpenSky Network /api/states/all",
            "as_of": as_of,
            "scope": "global",
            "flights_in_air": flights_in_air,
            "avg_altitude_m": avg_altitude_m,
            "avg_velocity_ms": avg_velocity_ms,
            "top_origin_countries": top_origin_countries,
            "total_states": total_states,
            "sample_limited": False,
        }

    # ── 采集入口 ──────────────────────────────────────────────
    def collect(self):
        r = self._get(OPENSKY_STATES_URL, headers=HEADERS, timeout=30)
        if r is None:
            self.logger.warning("[airtraffic_opensky] 请求失败，降级")
            return None
        try:
            data = r.json()
        except Exception as e:
            self.logger.warning("[airtraffic_opensky] 响应非 JSON: %s", e)
            return None
        states = data.get("states")
        if not isinstance(states, list) or len(states) == 0:
            self.logger.warning("[airtraffic_opensky] states 缺失/空，降级")
            return None
        ts = data.get("time")
        as_of = (
            datetime.datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if isinstance(ts, (int, float)) else
            datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        return self._aggregate(states, as_of)

    # _is_good 采用基类默认 ok-only，无需覆写。


def _make_unavailable():
    """首跑无良值时写的 unavailable 标记。"""
    return {
        "status": Status.UNAVAILABLE,
        "source": "OpenSky Network /api/states/all",
        "as_of": datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "global",
        "flights_in_air": None,
        "avg_altitude_m": None,
        "avg_velocity_ms": None,
        "top_origin_countries": [],
        "total_states": 0,
        "sample_limited": False,
    }


def main():
    fetcher = AirTrafficOpenSkyFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[airtraffic_opensky] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == Status.OK:
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[airtraffic_opensky] 完成 status=ok，flights_in_air="
              f"{result.get('flights_in_air')}，total_states={result.get('total_states')}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[airtraffic_opensky] 降级，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, _make_unavailable())
            print("[airtraffic_opensky] 降级，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
