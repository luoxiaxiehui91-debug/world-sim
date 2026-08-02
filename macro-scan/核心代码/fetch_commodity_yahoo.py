#!/usr/bin/env python3
"""
fetch_commodity_yahoo.py — Yahoo Finance v8 chart API 商品实时价
（CL=F WTI 原油 / BZ=F Brent 原油 / HG=F 铜，单位 USD/bbl、USD/bbl、USD/lb）

通过 query1.finance.yahoo.com/v8/finance/chart/{sym} 拉取日频序列，取
meta.regularMarketPrice 作实时价，meta.regularMarketTime（Unix 秒）转 ISO UTC+Z 作报价时间。

实现要点（详见架构设计 §1.2 / §3.2 / §7）：
  - 复用 FetcherBase：request/save_json/load_previous_good/load_config_with_fallback。
  - 每个 symbol 独立请求：单 symbol 404/失败 → 该 symbol status=unavailable 入
    unavailable_symbols，整体 partial；全失败 → collect() 返回 None。
  - 直连优先，失败回退代理（fetch_fao._get 模式），因容器内出网可能受限。
  - 铜单位为「美元/磅」（USD/lb），非吨，下游消费务必注意。
  - as_of 一律 ISO 8601 UTC + Z。

输出契约：data/commodity_yahoo.json
  {
    "status":            "ok" | "partial" | "unavailable",
    "source":            "Yahoo Finance v8 chart API (query1.finance.yahoo.com/v8/finance/chart)",
    "as_of":             "2026-07-28T14:30:00Z",
    "commodities": {
        "wti":   {"symbol":"CL=F","name":"WTI原油","unit":"USD/bbl","price":79.47,"as_of":...,"status":"ok"},
        "brent": {"symbol":"BZ=F","name":"Brent原油","unit":"USD/bbl","price":83.12,"as_of":...,"status":"ok"},
        "copper": {"symbol":"HG=F","name":"铜","unit":"USD/lb","price":4.52,"as_of":...,"status":"ok"}
    },
    "unavailable_symbols": ["AH=F"],
    "notes":  "铝(AH=F) Yahoo 端返回 404，已标记 unavailable；如需铝可经 LME 代理获取（不在本期范围）"
  }

调度：scheduler.py 06:26（日频，错峰 bdi 0625）。feeds_grv=False，仅落盘供下游消费。
"""
import os
import json
import logging
import datetime
from datetime import timezone

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

OUTPUT_FILE = "commodity_yahoo.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# 逻辑名键（与 commodities 的键对应）→ (symbol, 中文名, 单位)
# 注意：铜单位 USD/lb（美元/磅），并非吨。
SYMBOLS = [
    ("CL=F", "WTI原油", "USD/bbl"),
    ("BZ=F", "Brent原油", "USD/bbl"),
    ("HG=F", "铜", "USD/lb"),
]
_SYMBOL_KEYS = ["wti", "brent", "copper"]


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

    # ── chart JSON 解析 ───────────────────────────────────────
    def _parse_chart(self, payload, symbol, name, unit):
        """解析 Yahoo chart JSON → dict（status=ok）或 None（数据缺失）。

        路径（探针实测确认）：
          chart.result[0].meta.regularMarketPrice  → 实时价
          chart.result[0].meta.regularMarketTime   → Unix 秒（报价时间）
        """
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

    # ── 采集入口 ──────────────────────────────────────────────
    def collect(self):
        commodities = {}
        unavailable_symbols = []
        as_of_list = []
        for (symbol, name, unit), key in zip(SYMBOLS, _SYMBOL_KEYS):
            one = self._fetch_one(symbol, name, unit)
            if one is None:
                unavailable_symbols.append(symbol)
                continue
            commodities[key] = one
            as_of_list.append(one["as_of"])

        # 全失败 → 返回 None（main 保留上次良值 / 首跑写 unavailable）
        if not commodities:
            self.logger.warning("[commodity_yahoo] 全部 symbol 拉取失败")
            return None

        status = Status.PARTIAL if unavailable_symbols else Status.OK
        overall_as_of = (
            as_of_list[0]
            if as_of_list else
            datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        notes = (
            "铝(AH=F) Yahoo 端返回 404，已标记 unavailable；"
            "如需铝可经 LME 代理获取（不在本期范围）。"
            if unavailable_symbols else ""
        )
        return {
            "status": status,
            "source": "Yahoo Finance v8 chart API (query1.finance.yahoo.com/v8/finance/chart)",
            "as_of": overall_as_of,
            "commodities": commodities,
            "unavailable_symbols": unavailable_symbols,
            "notes": notes,
        }

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
