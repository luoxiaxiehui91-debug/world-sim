#!/usr/bin/env python3
"""
fetch_world_macro.py — 国际宏观快照（World Bank 升格主源 + Statistics of the World 匿名档）

填补天枢最大缺口：FRED 只美国、AkShare 只中国，全球推演缺"世界其余"。
- World Bank API：真免key、无公开限流、CC BY 4.0。多国核心指标（GDP增速/通胀/失业/经常账户/政府债）。
- Statistics of the World：匿名 1000 req/天免key（https://statisticsoftheworld.com/api/v2）。
  补充 GDP 绝对值等关键量。

输出：data/world_history/world_macro.json
  { updated, source, countries: { "US": {gdp_growth:{value,year}, inflation:{...}, ...}, ... } }

非商用内部系统：来源标注即可（礼貌规范）。
调度：scheduler.py 05:50 每日（World Bank 年度刷新、SotW 周级，日频冗余无害）。
"""
import os
import json
import argparse
import datetime
from typing import Optional

try:
    from optim_config import DATA_DIR, PROXY_URL
except ImportError:
    _cfg = FetcherBase.load_config_with_fallback(
        ["DATA_DIR", "PROXY_URL"],
        {
            "DATA_DIR": FetcherBase.default_data_dir(),
            "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
        },
    )
    DATA_DIR = _cfg["DATA_DIR"]
    PROXY_URL = _cfg["PROXY_URL"]

from fetcher_base import FetcherBase, RetryOnMissingMixin

HIST_DIR = os.path.join(DATA_DIR, "world_history")

# 重点跟踪国家（ISO3，World Bank 与 SotW 均用 ISO3 id）
COUNTRIES = ["USA", "CHN", "DEU", "JPN", "GBR", "FRA", "IND", "BRA", "RUS",
             "ZAF", "MEX", "KOR", "CAN", "AUS", "ITA", "ESP", "IDN", "TUR", "SAU", "IRN"]

# World Bank 指标（id, 本地键, 频率）
WB_INDICATORS = [
    ("NY.GDP.MKTP.KD.ZG",   "gdp_growth",             "annual"),
    ("FP.CPI.TOTL.ZG",      "inflation",              "annual"),
    ("SL.UEM.TOTL.ZS",      "unemployment",           "annual"),
    ("NE.RSB.GNFS.ZS",      "current_account_pct_gdp","annual"),
    ("GC.DOD.TOTL.GD.ZS",   "gov_debt_pct_gdp",       "annual"),
]
WB_BASE = "https://api.worldbank.org/v2/country/{iso}/indicator/{ind}?format=json&date=2015:2026&per_page=100"

# Statistics of the World 补充指标（SotW indicator id, 本地键）
SOTW_BASE = "https://statisticsoftheworld.com/api/v2"
SOTW_INDICATORS = [
    ("IMF.NGDPD", "gdp_usd"),                 # GDP 当前美元
    ("NY.GDP.MKTP.KD.ZG", "gdp_growth_sotw"), # SotW 交叉验证 GDP 增速
]


class WorldMacroFetcher(RetryOnMissingMixin, FetcherBase):
    name = "world_macro"
    rate_interval = 1.0   # World Bank 无公开限流但保守 1s；SotW 匿名1000/天日频足够
    output_file = "world_macro.json"
    feeds_grv = False
    schedule = "0550"

    def _fetch_wb(self, iso):
        out = {}
        for ind_id, key, _freq in WB_INDICATORS:
            url = WB_BASE.format(iso=iso, ind=ind_id)
            r = self.request(url, headers={"User-Agent": "macro-scan/1.0"})
            if r is None:
                continue
            try:
                data = r.json()
                obs = data[1] if isinstance(data, list) and len(data) > 1 else None
                if not obs:
                    continue
                latest = None
                for row in obs:
                    if row.get("value") is not None:
                        latest = row
                        break
                if latest:
                    out[key] = {"value": float(latest["value"]), "year": latest.get("date")}
            except Exception as e:
                self.logger.warning(f"[world_macro] WB {iso}/{ind_id} 解析失败: {e}")
        return out

    def _fetch_sotw_country(self, iso):
        out = {}
        url = f"{SOTW_BASE}/country/{iso}"
        r = self.request(url)
        if r is None:
            return out
        try:
            data = r.json()
            indicators = data.get("indicators", []) if isinstance(data, dict) else []
            by_id = {i.get("id"): i for i in indicators}
            for ind_id, key in SOTW_INDICATORS:
                item = by_id.get(ind_id)
                if item and item.get("value") is not None:
                    out[key] = {"value": item["value"], "year": item.get("year")}
        except Exception as e:
            self.logger.warning(f"[world_macro] SotW {iso} 解析失败: {e}")
        return out

    def collect(self):
        countries = {}
        for iso in COUNTRIES:
            wb = self._fetch_wb(iso)
            if wb:
                countries[iso] = wb
        for iso in COUNTRIES:
            sotw = self._fetch_sotw_country(iso)
            if sotw:
                countries.setdefault(iso, {}).update(sotw)
        return {
            "status": "ok",
            "source": "world_bank + statisticsoftheworld",
            "countries": countries,
        }


def main():
    parser = argparse.ArgumentParser(description="国际宏观快照拉取（World Bank + SotW）")
    parser.parse_args()
    fetcher = WorldMacroFetcher(HIST_DIR)
    result = fetcher.run()
    if result:
        fetcher.save_json("world_macro.json", result)
        print(f"[world_macro] 完成，覆盖 {len(result['countries'])} 国")
    else:
        print("[world_macro] 失败或空，无写入")


if __name__ == "__main__":
    main()
