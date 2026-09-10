#!/usr/bin/env python3
"""
fetch_crypto.py — 加密资产快照（CoinGecko Demo 免费 key）

作资产压力 / 散户情绪代理。Demo 档 100 RPM / ~1万月免key。
输出：data/crypto_history/crypto_latest.json
  { source, as_of, coins:[{id, symbol, market_cap, market_cap_rank, total_volume, price_change_24h_pct}], updated }
非商用内部系统：来源标注即可。
调度：scheduler.py 06:00 每日（或更低频）。
"""
import os

try:
    from optim_config import DATA_DIR, COINGECKO_API_KEY, PROXY_URL
except ImportError:
    _cfg = FetcherBase.load_config_with_fallback(
        ["DATA_DIR", "COINGECKO_API_KEY", "PROXY_URL"],
        {
            "DATA_DIR": FetcherBase.default_data_dir(),
            "COINGECKO_API_KEY": ("", "COINGECKO_API_KEY"),
            "PROXY_URL": ("", "PROXY_URL"),
        },
    )
    DATA_DIR = _cfg["DATA_DIR"]
    COINGECKO_API_KEY = _cfg["COINGECKO_API_KEY"]
    PROXY_URL = _cfg["PROXY_URL"]

from fetcher_base import FetcherBase

HIST_DIR = os.path.join(DATA_DIR, "crypto_history")
CG_BASE = "https://api.coingecko.com/api/v3/coins/markets"
COIN_IDS = ("bitcoin,ethereum,tether,binancecoin,solana,ripple,usd-coin,cardano,dogecoin,"
            "avalanche-2,tron,chainlink,polkadot,matic-network,litecoin,bitcoin-cash,"
            "uniswap,stellar,cosmos,monero")


class CryptoFetcher(FetcherBase):
    name = "crypto"
    rate_interval = 1.2  # Demo 100 RPM 宽松，保守限速
    output_file = "crypto_latest.json"
    feeds_grv = False
    schedule = "0600"

    def __init__(self, data_dir):
        super().__init__(data_dir)
        # NAS 直连 api.coingecko.com 不可达，统一走出站代理（与 FRED 代理一致）
        self.proxies = {"https": PROXY_URL, "http": PROXY_URL} if PROXY_URL else None

    def collect(self):
        params = {
            "vs_currency": "usd",
            "ids": COIN_IDS,
            "order": "market_cap_desc",
            "per_page": 20,
            "page": 1,
            "price_change_percentage": "24h",
        }
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
        r = self.request(CG_BASE, params=params, headers=headers)
        if r is None:
            return None
        try:
            arr = r.json()
            coins = []
            for c in arr:
                coins.append({
                    "id": c.get("id"),
                    "symbol": c.get("symbol"),
                    "name": c.get("name"),
                    "price": c.get("current_price"),
                    "market_cap": c.get("market_cap"),
                    "market_cap_rank": c.get("market_cap_rank"),
                    "total_volume": c.get("total_volume"),
                    "price_change_24h_pct": c.get("price_change_percentage_24h"),
                })
            return {"status": "ok", "source": "CoinGecko", "as_of": None, "coins": coins}
        except Exception as e:
            self.logger.error(f"[crypto] 解析失败: {e}")
            return None


def main():
    fetcher = CryptoFetcher(HIST_DIR)
    result = fetcher.run()
    if result:
        fetcher.save_json("crypto_latest.json", result)
        print(f"[crypto] 完成，{len(result['coins'])} 币种")
    else:
        print("[crypto] 失败或空")


if __name__ == "__main__":
    main()
