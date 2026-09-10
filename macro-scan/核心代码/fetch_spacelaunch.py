#!/usr/bin/env python3
"""
fetch_spacelaunch.py — Next Spaceflight Launch Library 2 API 发射记录

拉全球航天发射记录（upcoming 未来计划 + previous 最近完成），输出带发射场
坐标的点位数据，供开阳 space 太空活动图层（08-14 P2 续接；容器实测可达，免费无 key）。

数据源：The Space Devs Launch Library 2（ll.thespacedevs.com，免费，**必须带浏览器 UA**）
  - /2.0.0/launch/upcoming/?limit=365  未来发射（约 365 个）
  - /2.0.0/launch/previous/?limit=30   最近完成发射
  发射场坐标在 pad.latitude / pad.longitude（字符串 → float）。

实现要点：
  - 复用 FetcherBase：request/save_json/load_config_with_fallback。
  - 直连优先，失败回退代理（fetch_airroutes._get 模式）。
  - 坐标缺失/非法记录丢弃（K4 双保险）。
  - as_of = 生成时刻 ISO UTC+Z。

输出契约：data/spacelaunch.json
  {
    "status": "ok",
    "source": "The Space Devs Launch Library 2 (Next Spaceflight)",
    "as_of": "2026-08-14T14:00:00Z",
    "scope": "global",
    "schema_version": "1.0",
    "launches_count": 395,
    "launches": [
      {"name": "Falcon 9 Block 5 | USSF-366", "net": "2026-08-20T05:00:00Z",
       "status": "Go", "rocket": "Falcon 9 Block 5", "provider": "SpaceX",
       "pad_name": "Space Launch Complex 4E", "lat": 34.632, "lng": -120.611,
       "type": "upcoming"},
      ...
    ]
  }

调度：scheduler.py 0705 日档（发射事件低频，日更已远超所需）。
feeds_grv=False，仅落盘供下游消费。
"""
import datetime
from datetime import timezone

from fetcher_base import FetcherBase, Status

# ── 配置回退（统一取代重复 ImportError 块）────────────────────
_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR", "PROXY_URL"],
    {
        "DATA_DIR": FetcherBase.default_data_dir(),
        "PROXY_URL": ("", "PROXY_URL"),
    },
)
DATA_DIR = _cfg["DATA_DIR"]
PROXY_URL = _cfg["PROXY_URL"]

OUTPUT_FILE = "spacelaunch.json"
UPCOMING_URL = "https://ll.thespacedevs.com/2.0.0/launch/upcoming/?limit=365"
PREVIOUS_URL = "https://ll.thespacedevs.com/2.0.0/launch/previous/?limit=30"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class SpaceLaunchFetcher(FetcherBase):
    """Next Spaceflight 发射记录采集器：拉 upcoming + previous 并聚合。"""

    name = "spacelaunch"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0705"  # 日档（发射事件低频，日更已远超所需）

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        # 直连优先；直连失败再回退代理（与 fetch_airroutes._get 模式一致）
        self.proxies = None

    # ── 网络出口：直连优先，失败回退代理 ────────────────────────
    def _get_json(self, url, timeout=30):
        r = self.request(url, headers=HEADERS, timeout=timeout)
        if r is not None and r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return None
        if PROXY_URL:
            self.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            r = self.request(url, headers=HEADERS, timeout=timeout)
            if r is not None and r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    return None
        return None

    # ── 解析 launches → 输出 dict ─────────────────────────────
    def _parse(self, results, launch_type):
        out = []
        for la in results:
            if not isinstance(la, dict):
                continue
            pad = la.get("pad") or {}
            try:
                lat = float(pad.get("latitude"))
                lng = float(pad.get("longitude"))
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                continue
            status = None
            if isinstance(la.get("status"), dict):
                status = la["status"].get("name")
            rocket = None
            if isinstance(la.get("rocket"), dict) and isinstance(la["rocket"].get("configuration"), dict):
                rocket = la["rocket"]["configuration"].get("name")
            provider = None
            if isinstance(la.get("launch_service_provider"), dict):
                provider = la["launch_service_provider"].get("name")
            out.append({
                "name": la.get("name"),
                "net": la.get("net"),
                "status": status,
                "rocket": rocket,
                "provider": provider,
                "pad_name": pad.get("name"),
                "lat": round(lat, 4),
                "lng": round(lng, 4),
                "type": launch_type,
            })
        return out

    # ── 采集入口 ──────────────────────────────────────────────
    def collect(self):
        up = self._get_json(UPCOMING_URL)
        prev = self._get_json(PREVIOUS_URL)
        launches = []
        if up and isinstance(up.get("results"), list):
            launches += self._parse(up["results"], "upcoming")
        if prev and isinstance(prev.get("results"), list):
            launches += self._parse(prev["results"], "previous")
        if not launches:
            self.logger.warning("[spacelaunch] 无有效发射记录（坐标缺失/API失败），降级")
            return None
        as_of = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "status": Status.OK,
            "source": "The Space Devs Launch Library 2 (Next Spaceflight)",
            "as_of": as_of,
            "scope": "global",
            "schema_version": "1.0",
            "launches_count": len(launches),
            "launches": launches,
        }


def _make_unavailable():
    """首跑无良值时写的 unavailable 标记。"""
    return {
        "status": Status.UNAVAILABLE,
        "source": "The Space Devs Launch Library 2 (Next Spaceflight)",
        "as_of": datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "global",
        "schema_version": "1.0",
        "launches_count": 0,
        "launches": [],
    }


def main():
    fetcher = SpaceLaunchFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[spacelaunch] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == Status.OK:
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[spacelaunch] 完成 status=ok，launches_count={result.get('launches_count')}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[spacelaunch] 降级，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, _make_unavailable())
            print("[spacelaunch] 降级，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
