#!/usr/bin/env python3
"""
fetch_energy_eia.py — EIA 能源数据（美国能源信息署 API v2）

数据源：EIA Open Data API v2（需免费注册 key）
限速：官方 FAQ ~9000次/小时、5次/秒突发；本模块每日 6 次请求，远低于限额。
无需 requests.get 代理——EIA 可通过 NAS 出网代理正常访问。

抓取 6 个系列（均已在容器内实测验证 HTTP 200）：

  1. WTI 现货价           — /petroleum/pri/spt  series=RWTC       日频
  2. 美国原油库存(週报)   — /petroleum/stoc/wstk series=WCRSTUS1  週频
  3. 美国炼厂开工率       — /petroleum/pnp/wiup                   週频
  4. 天然气总库存(L48)    — /natural-gas/stor/wkly series=NW2_EPG0_SWO_R48_BCF  週频
  5. 美国汽油零售价       — /petroleum/pri/gnd  product=EPM0/NUS  週频
  6. 美国净发电量         — /electricity/electric-power-operational-data  月频

输出契约：data/energy_eia.json
  {
    "status":   "ok" | "partial" | "unavailable",
    "source":   "EIA v2",
    "as_of":    ISO8601 UTC,
    "series": {
      "wti_spot_price":        {"value", "unit", "period", "status"},
      "crude_inventory_mbbl":  {"value", "unit", "period", "status"},
      "refinery_utilization":  {"value", "unit", "period", "status"},
      "natgas_storage_bcf":    {"value", "unit", "period", "status"},
      "gasoline_retail_price": {"value", "unit", "period", "status"},
      "us_net_generation_gwh": {"value", "unit", "period", "status"}
    },
    "_schema_version": "1.0",
    "updated": ...
  }

调度：scheduler.py 06:30（错峰现有 06:08 energy / 06:26 commodity_yahoo）。
feeds_grv=False（落盘供下游交叉验证；进 GRV 需单独 PRD）。
"""
import datetime
import logging
from datetime import timezone

import requests

from fetcher_base import FetcherBase, Status

_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR", "PROXY_URL", "EIA_API_KEY"],
    {
        "DATA_DIR":    FetcherBase.default_data_dir(),
        "PROXY_URL":   ("http://192.168.31.108:7890", "PROXY_URL"),
        "EIA_API_KEY": ("", "EIA_API_KEY"),
    },
)
DATA_DIR    = _cfg["DATA_DIR"]
PROXY_URL   = _cfg["PROXY_URL"]
EIA_API_KEY = _cfg["EIA_API_KEY"]

EIA_BASE   = "https://api.eia.gov/v2"
OUTPUT_FILE = "energy_eia.json"

logger = logging.getLogger("fetcher.energy_eia")

# ── 各系列抓取规格 ────────────────────────────────────────────────────────────
# (key, label, unit, endpoint, extra_params)
_SERIES = [
    (
        "wti_spot_price",
        "WTI原油现货价",
        "$/BBL",
        "/petroleum/pri/spt/data/",
        {"frequency": "daily", "facets[series][]": "RWTC"},
    ),
    (
        "crude_inventory_mbbl",
        "美国商业原油库存",
        "千桶",
        "/petroleum/stoc/wstk/data/",
        {"frequency": "weekly",
         "facets[duoarea][]": "NUS", "facets[product][]": "EPC0",
         "facets[process][]": "SAE"},
    ),
    (
        "refinery_utilization",
        "美国炼厂开工率",
        "千桶/日",
        "/petroleum/pnp/wiup/data/",
        {"frequency": "weekly", "facets[duoarea][]": "NUS"},
    ),
    (
        "natgas_storage_bcf",
        "美国天然气总库存(L48)",
        "BCF",
        "/natural-gas/stor/wkly/data/",
        {"frequency": "weekly",
         "facets[series][]": "NW2_EPG0_SWO_R48_BCF"},
    ),
    (
        "gasoline_retail_price",
        "美国汽油零售价",
        "$/加仑",
        "/petroleum/pri/gnd/data/",
        {"frequency": "weekly",
         "facets[duoarea][]": "NUS", "facets[product][]": "EPM0"},
    ),
    (
        "us_net_generation_gwh",
        "美国净发电量",
        "千兆瓦时",
        "/electricity/electric-power-operational-data/data/",
        {"frequency": "monthly",
         "data[0]": "generation",
         "facets[location][]": "US", "facets[sectorid][]": "99"},
    ),
]


def _now_utc() -> str:
    return datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_one(session, key, endpoint, extra_params, proxies):
    """抓单个系列，返回 (value, unit, period) 或抛异常。"""
    params = {
        "api_key": EIA_API_KEY,
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 1,
    }
    # 发电量端点用 generation 字段
    if "generation" in extra_params.get("data[0]", ""):
        params["data[0]"] = "generation"
    params.update(extra_params)
    # 移除重复的 data[0] 覆盖（extra_params 可能含 data[0]）
    if "data[0]" in extra_params:
        params["data[0]"] = extra_params["data[0]"]

    url = EIA_BASE + endpoint
    r = session.get(url, params=params, proxies=proxies, timeout=15)
    if r.status_code != 200:
        raise ValueError("HTTP %d" % r.status_code)
    d = r.json()
    err = d.get("error")
    if err:
        raise ValueError("API error: %s" % str(err)[:100])
    rows = d.get("response", {}).get("data", [])
    if not rows:
        raise ValueError("empty data")
    row = rows[0]
    # 发电量字段名是 generation，其余是 value
    val = row.get("value") or row.get("generation")
    if val is None:
        raise ValueError("null value")
    return float(val), row.get("units", ""), row.get("period", "")


class EiaEnergyFetcher(FetcherBase):
    name = "energy_eia"
    rate_interval = 1.0   # 1秒/请求，远低于EIA 5次/秒限制
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0630"

    def _is_good(self, data: dict) -> bool:
        return data.get("status") in (Status.OK, Status.PARTIAL)

    def collect(self) -> dict | None:
        if not EIA_API_KEY:
            logger.warning("[energy_eia] EIA_API_KEY 未配置，跳过")
            return None

        as_of = _now_utc()
        proxies = {"https": PROXY_URL, "http": PROXY_URL} if PROXY_URL else None
        session = requests.Session()

        series_out = {}
        ok_count = 0
        fail_count = 0

        for s_key, label, unit, endpoint, extra in _SERIES:
            import time
            time.sleep(self.rate_interval)
            try:
                val, api_unit, period = _fetch_one(session, s_key, endpoint, extra, proxies)
                series_out[s_key] = {
                    "name":   label,
                    "value":  val,
                    "unit":   api_unit or unit,
                    "period": period,
                    "status": Status.OK,
                }
                ok_count += 1
                logger.info("[energy_eia] %s: %s %s (%s)", s_key, val, unit, period)
            except Exception as e:
                logger.warning("[energy_eia] %s 失败: %s", s_key, e)
                series_out[s_key] = {
                    "name":   label,
                    "value":  None,
                    "unit":   unit,
                    "period": None,
                    "status": Status.UNAVAILABLE,
                }
                fail_count += 1

        if ok_count == 0:
            return None
        status = Status.OK if fail_count == 0 else Status.PARTIAL

        return {
            "status":   status,
            "source":   "EIA v2",
            "as_of":    as_of,
            "series":   series_out,
            "ok_count": ok_count,
            "fail_count": fail_count,
        }


def main():
    fetcher = EiaEnergyFetcher(DATA_DIR)
    result = fetcher.run()
    if result is None:
        prev = fetcher.load_previous_good()
        if prev is None:
            placeholder = {
                "status": Status.UNAVAILABLE,
                "source": "EIA v2",
                "as_of":  _now_utc(),
                "series": {},
                "notes":  "key_missing 或全部请求失败",
            }
            fetcher.save_json(OUTPUT_FILE, placeholder)
            print("[energy_eia] 无法获取数据，写 unavailable")
        else:
            print("[energy_eia] 失败，保留上次良值")
        return

    fetcher.save_json(OUTPUT_FILE, result)
    print("[energy_eia] 完成 status=%s ok=%d fail=%d" % (
        result["status"], result.get("ok_count", 0), result.get("fail_count", 0)))
    for k, v in result.get("series", {}).items():
        print("  %s: %s %s (%s) [%s]" % (
            k, v.get("value"), v.get("unit"), v.get("period"), v.get("status")))


if __name__ == "__main__":
    main()
