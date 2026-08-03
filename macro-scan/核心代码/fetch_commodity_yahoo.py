#!/usr/bin/env python3
"""
fetch_commodity_yahoo.py — Yahoo Finance v8 chart API 商品/股市/贵金属实时价 + 历史 CSV

扩展（2026-08-03）：
  - 新增股市指数：SPY(标普500)、QQQ(纳斯达克)、HSI(恒生)
  - 新增贵金属：GC=F(黄金)、SI=F(白银)
  - 新增额外能源：NG=F(天然气)
  - 每日采集时同步追加历史 CSV（data/commodity_history/{key}.csv），
    供 FRED manifest 注册后在经济面板展示历史趋势
  - 历史 CSV 格式与 fred_history/*.csv 兼容：date,value

输出契约：data/commodity_yahoo.json（实时快照，不变）
历史 CSV：data/commodity_history/{key}.csv（日频追加）
"""
import csv
import os
import json
import logging
import datetime
from datetime import timezone

import requests
from fetcher_base import FetcherBase, Status

_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR", "PROXY_URL"],
    {
        "DATA_DIR": FetcherBase.default_data_dir(),
        "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
    },
)
DATA_DIR = _cfg["DATA_DIR"]
PROXY_URL = _cfg["PROXY_URL"]

OUTPUT_FILE = "commodity_yahoo.json"
HIST_DIR_NAME = "commodity_history"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# (symbol, 逻辑键, 中文名, 单位, 类别)
SYMBOLS = [
    ("CL=F",    "wti",      "WTI原油",     "USD/bbl", "能源"),
    ("BZ=F",    "brent",    "Brent原油",   "USD/bbl", "能源"),
    ("NG=F",    "nat_gas",  "天然气",      "USD/MMBtu","能源"),
    ("HG=F",    "copper",   "铜",          "USD/lb",  "金属"),
    ("GC=F",    "gold",     "黄金",        "USD/oz",  "贵金属"),
    ("SI=F",    "silver",   "白银",        "USD/oz",  "贵金属"),
    ("SPY",     "sp500",    "标普500 ETF", "USD",     "股市"),
    ("QQQ",     "nasdaq",   "纳斯达克100", "USD",     "股市"),
    ("^HSI",    "hsi",      "恒生指数",    "HKD",     "股市"),
]
_SYMBOL_KEYS = [s[1] for s in SYMBOLS]


class CommodityYahooFetcher(FetcherBase):
    """Yahoo 商品实时价采集器：逐 symbol 拉取 chart，单 symbol 失败隔离。"""

    name = "commodity_yahoo"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0626"

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        # 直连优先；直连失败再回退代理（与 fetch_fao._get 模式一致）
        self.proxies = None

    # ── 网络出口：直连优先，失败回退代理 ────────────────────────
    def _get(self, url, params=None, headers=None, timeout=20):
        r = self.request(url, params=params, headers=headers, timeout=timeout)
        if r is not None:
            return r
        if PROXY_URL:
            self.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            return self.request(url, params=params, headers=headers, timeout=timeout)
        return None

    # ── 单 symbol 抓取 ─────────────────────────────────────────
    def _fetch_one(self, symbol, name, unit):
        """拉取单个 symbol 的 chart。

        返回 {symbol,name,unit,price,as_of,status=ok}；请求失败/404/解析缺失 → None。
        """
        url = YAHOO_CHART_URL.format(symbol=symbol)
        r = self._get(url, params={"range": "1y", "interval": "1d"}, headers=HEADERS)
        if r is None:
            self.logger.warning("[commodity_yahoo] %s 请求失败/404，标记 unavailable", symbol)
            return None
        try:
            payload = r.json()
        except Exception as e:
            self.logger.warning("[commodity_yahoo] %s 响应非 JSON: %s", symbol, e)
            return None
        return self._parse_chart(payload, symbol, name, unit)

    def _parse_chart(self, payload, symbol, name, unit):
        try:
            result = payload["chart"]["result"]
            if not result:
                return None
            meta = result[0]["meta"]
        except (KeyError, IndexError, TypeError):
            self.logger.warning("[commodity_yahoo] %s chart.result[0].meta 缺失", symbol)
            return None
        price = meta.get("regularMarketPrice")
        if price is None:
            self.logger.warning("[commodity_yahoo] %s regularMarketPrice 缺失", symbol)
            return None
        rmt = meta.get("regularMarketTime")
        as_of = (
            datetime.datetime.fromtimestamp(rmt, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if isinstance(rmt, (int, float)) else
            datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        return {
            "symbol": symbol,
            "name": name,
            "unit": unit,
            "price": float(price),
            "as_of": as_of,
            "status": Status.OK,
        }

    def _append_history(self, key: str, date_str: str, price: float):
        """把当日价格追加到历史 CSV（date,value 格式，与 fred_history 兼容）。
        幂等：同一日期已存在则跳过。
        """
        hist_dir = os.path.join(DATA_DIR, HIST_DIR_NAME)
        os.makedirs(hist_dir, exist_ok=True)
        csv_path = os.path.join(hist_dir, f"{key}.csv")

        # 读取已有数据
        existing_dates = set()
        rows = []
        if os.path.exists(csv_path):
            try:
                with open(csv_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        existing_dates.add(row["date"])
                        rows.append(row)
            except Exception:
                pass

        if date_str in existing_dates:
            return  # 幂等，今天已经追加过

        rows.append({"date": date_str, "value": str(round(price, 4))})
        rows.sort(key=lambda r: r["date"])

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "value"])
            writer.writeheader()
            writer.writerows(rows)

    def collect(self):
        commodities = {}
        unavailable_symbols = []
        as_of_list = []
        today = datetime.date.today().isoformat()

        for symbol, key, name, unit, _category in SYMBOLS:
            one = self._fetch_one(symbol, name, unit)
            if one is None:
                unavailable_symbols.append(symbol)
                continue
            commodities[key] = one
            as_of_list.append(one["as_of"])
            # 历史追加
            try:
                self._append_history(key, today, one["price"])
            except Exception as e:
                self.logger.warning("[commodity_yahoo] %s 历史追加失败: %s", key, e)

        if not commodities:
            self.logger.warning("[commodity_yahoo] 全部 symbol 拉取失败")
            return None

        status = Status.PARTIAL if unavailable_symbols else Status.OK
        overall_as_of = (
            as_of_list[0] if as_of_list else
            datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        return {
            "status": status,
            "source": "Yahoo Finance v8 chart API",
            "as_of": overall_as_of,
            "commodities": commodities,
            "unavailable_symbols": unavailable_symbols,
            "notes": "",
        }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    fetcher = CommodityYahooFetcher(DATA_DIR)
    fetcher.run()


    # _is_good 采用基类默认 ok-only；partial 由 main() 显式落盘，无需覆写。


def _make_unavailable():
    """首跑无良值时写的 unavailable 标记。"""
    return {
        "status": Status.UNAVAILABLE,
        "source": "Yahoo Finance v8 chart API (query1.finance.yahoo.com/v8/finance/chart)",
        "as_of": datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commodities": {},
        "unavailable_symbols": [s[0] for s in SYMBOLS],
        "notes": "首跑无良值，全部标记为 unavailable（网络/源不可达）。",
    }


def main():
    fetcher = CommodityYahooFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        # 全失败：保留上次良值（不覆盖）；首跑无良值则写 unavailable 标记
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[commodity_yahoo] 全部 symbol 失败，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, _make_unavailable())
            print("[commodity_yahoo] 全部 symbol 失败，无历史良值，写 unavailable 标记")
        return
    if result.get("status") in (Status.OK, Status.PARTIAL):
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[commodity_yahoo] 完成 status={result.get('status')}，"
              f"symbols={list(result.get('commodities', {}).keys())}，"
              f"unavailable={result.get('unavailable_symbols')}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[commodity_yahoo] 降级，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, _make_unavailable())
            print("[commodity_yahoo] 降级，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
