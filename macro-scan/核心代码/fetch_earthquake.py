#!/usr/bin/env python3
"""
fetch_earthquake.py — 全球地震压力指数（USGS Earthquake，P0 真免key）

P0 源：USGS Earthquake Hazards Program 实时 GeoJSON feed。
  - 真免key、无公开限流（单次 ≤20000 条）、带 time 时间戳（毫秒 epoch）。
  - 对 Energy / GRV 外生冲击价值高（地震 → 能源 / 电网 / 供应链外生冲击）。

与既有 fetch_disaster_signals.py 的关系（避免重复理解偏差）：
  fetch_disaster_signals.py 已用 USGS feed 产出「事件级」disaster_risk（含关键供应链
  节点 / 核电区告警），并接入 GRV。本模块提供**独立、FetcherBase 适配层**的
  **全局地震压力指数**视角，直接喂 GRV 的 energy/grid 外生冲击维度（seismic_risk）。
  两者互补：一个是单事件告警，一个是全局压力基线，不冲突。

输出契约：data/earthquake_risk.json
  {
    "status":            "ok" | "unavailable",
    "seismic_risk":      0–100,   # 全局地震压力指数（GRV 直接消费）
    "event_count_24h":   int,
    "count_m45"/"count_m55"/"count_m65": int,
    "max_mag":           float,
    "window_hours":      24,
    "top_events":        [ {magnitude, place, time_utc}, ... ],
    "source":            "USGS Earthquake feed",
    "updated":           as-of 时间戳（fetcher_base.save_json 注入）
  }
  geo_risk_vector.py 直接读 seismic_risk 填 grv_latest.json 的 seismic_risk。

降级：拉取 / 解析失败 → status=unavailable；若本地有上次良值则保留、不覆盖、绝不 crash。

网络出口：直连优先，失败回退代理，仍失败降级 unavailable（USGS 实测出口见交付报告）。
调度：scheduler.py 06:06（grv_update 06:10 前完成）；另 12:06 / 18:06 / 00:06 日内刷新。
"""
import os
import json
import datetime

try:
    from optim_config import DATA_DIR, USGS_EARTHQUAKE_URL, PROXY_URL
except ImportError:
    _cfg = FetcherBase.load_config_with_fallback(
        ["DATA_DIR", "USGS_EARTHQUAKE_URL", "PROXY_URL"],
        {
            "DATA_DIR": FetcherBase.default_data_dir(),
            "USGS_EARTHQUAKE_URL": (
                "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson",
                "USGS_EARTHQUAKE_URL",
            ),
            "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
        },
    )
    DATA_DIR = _cfg["DATA_DIR"]
    USGS_EARTHQUAKE_URL = _cfg["USGS_EARTHQUAKE_URL"]
    PROXY_URL = _cfg["PROXY_URL"]

from fetcher_base import FetcherBase

OUTPUT_FILE = "earthquake_risk.json"
WINDOW_HOURS = 24
# raw(地震压力原始分) -> 0–100 映射系数（见 _seismic_risk 说明）
SEISMIC_SCALE = 2.0


class EarthquakeFetcher(FetcherBase):
    name = "earthquake"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = True
    schedule = "0606"

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self.proxies = None   # 直连优先；collect 内按 direct→proxy 回退

    # ── 网络出口：直连优先，失败回退代理 ────────────────────────
    def _ensure_egress(self):
        r = self.request(USGS_EARTHQUAKE_URL, timeout=20)
        if r is not None:
            return r
        if PROXY_URL:
            self.logger.warning("[earthquake] 直连失败，回退代理 %s", PROXY_URL)
            self.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            return self.request(USGS_EARTHQUAKE_URL, timeout=20)
        return None

    @staticmethod
    def _seismic_risk(count_45: int, count_55: int, count_65: int, max_mag: float) -> float:
        """全局地震压力指数（0–100），启发式：

            raw = count_45*1 + count_55*6 + count_65*20 + max(0, max_mag-6)*15
            seismic_risk = min(100, raw * SEISMIC_SCALE)

        量级参考（全球日均，USGS feed 经验）：
          - 数条 M4.5+、约 1 条 M5+、偶发 M6+。
          - 平静日  -> raw 小 -> 低分；
          - 活跃日（多次强震 / 大班达海震群）-> raw 大 -> 趋近 100。
        该函数只依赖过去 24h 窗口计数，稳定、结构性，不受单条新闻驱动。
        """
        raw = (count_45 * 1 + count_55 * 6 + count_65 * 20
               + max(0.0, max_mag - 6.0) * 15.0)
        return round(min(100.0, raw * SEISMIC_SCALE), 1)

    def collect(self):
        r = self._ensure_egress()
        if r is None:
            return {"status": "unavailable", "reason": "usgs_unreachable",
                    "source": "USGS Earthquake feed"}
        try:
            data = r.json()
            features = data.get("features", []) or []
        except Exception as e:
            self.logger.error("[earthquake] JSON 解析失败: %s", e)
            return {"status": "unavailable", "reason": "parse_error",
                    "source": "USGS Earthquake feed"}

        now_ms = datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000.0
        cutoff = now_ms - WINDOW_HOURS * 3600 * 1000
        count_45 = count_55 = count_65 = 0
        max_mag = 0.0
        recent = []
        for f in features:
            props = f.get("properties", {}) or {}
            t = props.get("time")
            mag = props.get("mag") or 0.0
            if t is None or t < cutoff:
                continue
            if mag >= 4.5:
                count_45 += 1
            if mag >= 5.5:
                count_55 += 1
            if mag >= 6.5:
                count_65 += 1
            if mag > max_mag:
                max_mag = mag
            recent.append((mag, props.get("place", ""), t))

        recent.sort(key=lambda x: -x[0])
        seismic_risk = self._seismic_risk(count_45, count_55, count_65, max_mag)
        top = [{
            "magnitude": round(m, 1),
            "place": p,
            "time_utc": datetime.datetime.fromtimestamp(
                t / 1000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        } for m, p, t in recent[:5]]

        self.logger.info(
            "[earthquake] 24h: n=%d m45=%d m55=%d m65=%d max=%.1f -> risk=%.1f",
            len(recent), count_45, count_55, count_65, max_mag, seismic_risk,
        )
        return {
            "status": "ok",
            "seismic_risk": seismic_risk,
            "event_count_24h": len(recent),
            "count_m45": count_45,
            "count_m55": count_55,
            "count_m65": count_65,
            "max_mag": round(max_mag, 1),
            "window_hours": WINDOW_HOURS,
            "top_events": top,
            "source": "USGS Earthquake feed",
        }

def main():
    fetcher = EarthquakeFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[earthquake] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == "ok":
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[earthquake] 完成 status=ok，seismic_risk={result.get('seismic_risk')}"
              f"，events_24h={result.get('event_count_24h')}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[earthquake] 降级 unavailable，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, result)
            print("[earthquake] 降级 unavailable，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
