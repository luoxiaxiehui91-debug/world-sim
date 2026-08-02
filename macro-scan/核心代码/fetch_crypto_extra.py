#!/usr/bin/env python3
"""
fetch_crypto_extra.py — 加密冗余行情（Binance / Kraken 公共端，P1）

与既有 fetch_crypto.py（CoinGecko）互补：交易所公共行情（撮合价 / 成交量），
作为 CoinGecko 快照的交叉验证与冗余源。两条源口径不同（交易所实时 vs 聚合市值），
并行保留可提升加密外生冲击信号的鲁棒性。

- Binance：/api/v3/ticker/24hr（公共端免key，全市场 24h 行情）
- Kraken：/0/public/Ticker（公共端免key，指定交易对）

各源独立 status；一方失败不影响另一方。

输出契约：data/crypto_history/crypto_extra_latest.json
  {
    "status":  "ok" | "unavailable",
    "binance": {status, count, tickers:[{symbol, price, change_pct_24h, quote_volume}]},
    "kraken":  {status, count, tickers:[{pair, symbol, price, vwap_24h, volume_24h}]},
    "source":  "Binance / Kraken public",
    "updated": as-of
  }
注：本源为冗余/交叉验证，暂不直接接入 GRV（列入"待接 GRV 字段"清单）。

降级：各源独立 try/except；整体不可用时若本地有上次良值则保留、不覆盖、绝不 crash。
网络出口：直连优先，失败回退代理，仍失败降级（交易所出口实测见交付报告）。
调度：scheduler.py 06:12（不依赖 GRV，落盘即可）。
"""
import os
import json

try:
    from optim_config import DATA_DIR, PROXY_URL, BINANCE_API_BASE, KRAKEN_API_BASE
except ImportError:
    _cfg = FetcherBase.load_config_with_fallback(
        ["DATA_DIR", "PROXY_URL", "BINANCE_API_BASE", "KRAKEN_API_BASE"],
        {
            "DATA_DIR": FetcherBase.default_data_dir(),
            "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
            "BINANCE_API_BASE": ("https://api.binance.com", "BINANCE_API_BASE"),
            "KRAKEN_API_BASE": ("https://api.kraken.com", "KRAKEN_API_BASE"),
        },
    )
    DATA_DIR = _cfg["DATA_DIR"]
    PROXY_URL = _cfg["PROXY_URL"]
    BINANCE_API_BASE = _cfg["BINANCE_API_BASE"]
    KRAKEN_API_BASE = _cfg["KRAKEN_API_BASE"]

from fetcher_base import FetcherBase

HIST_DIR = os.path.join(DATA_DIR, "crypto_history")
OUTPUT_FILE = "crypto_extra_latest.json"

# 关注的 Binance 交易对（USDT 报价）
_BINANCE_WATCH = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                  "ADAUSDT", "DOGEUSDT", "DOTUSDT"]
# 关注的 Kraken 交易对
_KRAKEN_PAIRS = ["XBTUSD", "ETHUSD", "ADAUSD", "SOLUSD", "DOTUSD", "XRPUSD", "DOGEUSD"]
# Kraken 交易对别名 -> 规范符号
_KRAKEN_ALIAS = {"XBTUSD": "BTC", "ETHUSD": "ETH", "ADAUSD": "ADA", "SOLUSD": "SOL",
                 "DOTUSD": "DOT", "XRPUSD": "XRP", "DOGEUSD": "DOGE"}


class CryptoExtraFetcher(FetcherBase):
    name = "crypto_extra"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0612"

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self.proxies = None

    def _get(self, url, params=None, headers=None, timeout=20):
        r = self.request(url, params=params, headers=headers, timeout=timeout)
        if r is not None:
            return r
        if PROXY_URL:
            self.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            return self.request(url, params=params, headers=headers, timeout=timeout)
        return None

    def _fetch_binance(self) -> dict:
        url = f"{BINANCE_API_BASE}/api/v3/ticker/24hr"
        r = self._get(url)
        if r is None:
            return {"status": "unavailable", "reason": "unreachable"}
        try:
            arr = r.json()
            by_sym = {x.get("symbol"): x for x in arr if isinstance(x, dict)}
            tickers = []
            for s in _BINANCE_WATCH:
                x = by_sym.get(s)
                if x:
                    tickers.append({
                        "symbol": s,
                        "price": x.get("lastPrice"),
                        "change_pct_24h": x.get("priceChangePercent"),
                        "quote_volume": x.get("quoteVolume"),
                    })
            return {"status": "ok", "count": len(tickers), "tickers": tickers}
        except Exception as e:
            return {"status": "unavailable", "reason": f"parse_error:{e}"}

    def _fetch_kraken(self) -> dict:
        url = f"{KRAKEN_API_BASE}/0/public/Ticker"
        r = self._get(url, params={"pair": ",".join(_KRAKEN_PAIRS)})
        if r is None:
            return {"status": "unavailable", "reason": "unreachable"}
        try:
            d = r.json()
            if d.get("error"):
                return {"status": "unavailable", "reason": str(d["error"])}
            res = d.get("result", {})
            tickers = []
            for p in _KRAKEN_PAIRS:
                x = res.get(p)
                if not x:
                    continue
                tickers.append({
                    "pair": p,
                    "symbol": _KRAKEN_ALIAS.get(p, p),
                    "price": (x.get("c") or [None])[0],
                    "vwap_24h": (x.get("p") or [None])[0],
                    "volume_24h": (x.get("v") or [None])[0],
                })
            return {"status": "ok", "count": len(tickers), "tickers": tickers}
        except Exception as e:
            return {"status": "unavailable", "reason": f"parse_error:{e}"}

    def collect(self):
        b = self._fetch_binance()
        k = self._fetch_kraken()
        ok = [s for s in (b.get("status"), k.get("status")) if s == "ok"]
        status = "ok" if ok else "unavailable"
        return {
            "status": status,
            "binance": b,
            "kraken": k,
            "source": "Binance / Kraken public",
        }

def main():
    fetcher = CryptoExtraFetcher(HIST_DIR)
    result = fetcher.run()
    if not result:
        print("[crypto_extra] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == "ok":
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[crypto_extra] 完成 status=ok，"
              f"binance={result['binance'].get('count')} kraken={result['kraken'].get('count')}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[crypto_extra] 降级 unavailable，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, result)
            print("[crypto_extra] 降级 unavailable，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
