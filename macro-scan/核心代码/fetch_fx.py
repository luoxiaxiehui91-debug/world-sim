#!/usr/bin/env python3
"""
fetch_fx.py — 汇率快照（Frankfurter / ECB，真免key）

填补 FRED 汇率覆盖不足。ECB 每日参考汇率，历史至1948。
输出：data/fx_history/fx_latest.json { base, date(as-of), rates:{...}, updated }
非商用内部系统：来源标注（ECB attribution）即可。
调度：scheduler.py 05:55 每日。
"""
import os

try:
    from optim_config import DATA_DIR, PROXY_URL
except ImportError:
    _cfg = FetcherBase.load_config_with_fallback(
        ["DATA_DIR", "PROXY_URL"],
        {
            "DATA_DIR": FetcherBase.default_data_dir(),
            "PROXY_URL": ("", "PROXY_URL"),
        },
    )
    DATA_DIR = _cfg["DATA_DIR"]
    PROXY_URL = _cfg["PROXY_URL"]

from fetcher_base import FetcherBase

HIST_DIR = os.path.join(DATA_DIR, "fx_history")
FX_BASE = "https://api.frankfurter.dev/v1/latest"
SYMBOLS = "EUR,JPY,GBP,CHF,CNY,RUB,INR,BRL,ZAR,MXN,KRW,CAD,AUD,TRY"


class FxFetcher(FetcherBase):
    name = "fx"
    rate_interval = 1.0
    output_file = "fx_latest.json"
    feeds_grv = False
    schedule = "0555"

    def __init__(self, data_dir):
        super().__init__(data_dir)
        # 容器直连外网 DNS 间歇性失败，统一走 NAS 出站代理（与 FRED/CoinGecko 一致）
        self.proxies = {"https": PROXY_URL, "http": PROXY_URL} if PROXY_URL else None

    def collect(self):
        url = f"{FX_BASE}?base=USD&symbols={SYMBOLS}"
        r = self.request(url)
        if r is None:
            return None
        try:
            data = r.json()
            return {
                "status": "ok",
                "base": data.get("base", "USD"),
                "as_of": data.get("date"),   # ECB 观测日，真 as-of
                "rates": data.get("rates", {}),
                "source": "Frankfurter (ECB)",
            }
        except Exception as e:
            self.logger.error(f"[fx] 解析失败: {e}")
            return None


def main():
    fetcher = FxFetcher(HIST_DIR)
    result = fetcher.run()
    if result:
        fetcher.save_json("fx_latest.json", result)
        print(f"[fx] 完成，as_of={result.get('as_of')}，{len(result.get('rates', {}))} 货币")
    else:
        print("[fx] 失败或空")


if __name__ == "__main__":
    main()
