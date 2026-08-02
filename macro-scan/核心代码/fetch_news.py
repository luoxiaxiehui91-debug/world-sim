#!/usr/bin/env python3
"""
fetch_news.py — 新闻 / 市场情报聚合（P1 归并模块：MarketAux + Currents + Sugra）

归并金融/综合新闻情报源（符合"新闻类聚合进一个 fetcher"的改造要求）：
  - MarketAux：金融新闻 / 市场情绪，结构化（apiKey）
  - Currents：综合多源新闻（apiKey）
  - Sugra：聚合「市场 + 经济 + 商品 + 气候 + 新闻」LLM-ready JSON（apiKey；端点本环境未核实）

三源均 apiKey；未配置 key 时对应子源 status=key_missing（非 crash）。
本模块为「待接 GRV 字段」源：先落盘，下游可经 news.db / LLM 上下文消费。

各子源独立 status，互不影响。

输出契约：data/news_risk.json
  {
    "status":  "ok" | "partial" | "unavailable",
    "marketaux": {status, count, articles:[...], top_symbols:[...]},
    "currents":  {status, count, articles:[...]},
    "sugra":     {status, observations?, note?},
    "source":  "MarketAux / Currents / Sugra",
    "updated": as-of
  }

降级：每子源独立 try/except（含 key 缺失）；整体不可用时若本地有上次良值则保留、不覆盖、绝不 crash。
网络出口：直连优先，失败回退代理，仍失败降级（各源出口实测见交付报告）。
调度：scheduler.py 06:16（不依赖 GRV，落盘即可）。
"""
import os
import json
from collections import Counter

try:
    from optim_config import (
        DATA_DIR, PROXY_URL,
        MARKETAUX_API_KEY, MARKETAUX_API_URL,
        CURRENTS_API_KEY, CURRENTS_API_URL,
        SUGRA_API_KEY, SUGRA_API_URL,
    )
except ImportError:
    _cfg = FetcherBase.load_config_with_fallback(
        ["DATA_DIR", "PROXY_URL", "MARKETAUX_API_KEY", "MARKETAUX_API_URL",
         "CURRENTS_API_KEY", "CURRENTS_API_URL", "SUGRA_API_KEY", "SUGRA_API_URL"],
        {
            "DATA_DIR": FetcherBase.default_data_dir(),
            "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
            "MARKETAUX_API_KEY": ("", "MARKETAUX_API_KEY"),
            "MARKETAUX_API_URL": ("https://api.marketaux.com/v1/news/all", "MARKETAUX_API_URL"),
            "CURRENTS_API_KEY": ("", "CURRENTS_API_KEY"),
            "CURRENTS_API_URL": ("https://api.currentsapi.services/v1/latest-news", "CURRENTS_API_URL"),
            "SUGRA_API_KEY": ("", "SUGRA_API_KEY"),
            "SUGRA_API_URL": ("https://api.sugra.ai/v1/observations", "SUGRA_API_URL"),
        },
    )
    DATA_DIR = _cfg["DATA_DIR"]
    PROXY_URL = _cfg["PROXY_URL"]
    MARKETAUX_API_KEY = _cfg["MARKETAUX_API_KEY"]
    MARKETAUX_API_URL = _cfg["MARKETAUX_API_URL"]
    CURRENTS_API_KEY = _cfg["CURRENTS_API_KEY"]
    CURRENTS_API_URL = _cfg["CURRENTS_API_URL"]
    SUGRA_API_KEY = _cfg["SUGRA_API_KEY"]
    SUGRA_API_URL = _cfg["SUGRA_API_URL"]

from fetcher_base import FetcherBase

OUTPUT_FILE = "news_risk.json"


class NewsFetcher(FetcherBase):
    name = "news"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0616"

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

    # ── MarketAux（金融新闻，apiKey）───────────────────────────
    def _fetch_marketaux(self) -> dict:
        if not MARKETAUX_API_KEY:
            return {"status": "key_missing", "reason": "no_marketaux_key"}
        r = self._get(MARKETAUX_API_URL, params={
            "api_token": MARKETAUX_API_KEY, "limit": 10,
            "languages": "en", "filter_entities": True,
        })
        if r is None:
            return {"status": "unavailable", "reason": "unreachable"}
        try:
            d = r.json()
            items = d.get("data", []) or []
            arts = [{
                "title": a.get("title"),
                "symbols": [s.get("symbol") for s in (a.get("symbols") or [])],
                "published_at": a.get("published_at"),
                "source": a.get("source"),
            } for a in items[:10]]
            freq = Counter()
            for a in items:
                for s in (a.get("symbols") or []):
                    if s.get("symbol"):
                        freq[s["symbol"]] += 1
            return {"status": "ok", "count": len(items),
                    "articles": arts, "top_symbols": freq.most_common(10)}
        except Exception as e:
            return {"status": "unavailable", "reason": f"parse_error:{e}"}

    # ── Currents（综合新闻，apiKey）────────────────────────────
    def _fetch_currents(self) -> dict:
        if not CURRENTS_API_KEY:
            return {"status": "key_missing", "reason": "no_currents_key"}
        r = self._get(CURRENTS_API_URL, params={
            "apiKey": CURRENTS_API_KEY, "language": "en", "limit": 10,
        })
        if r is None:
            return {"status": "unavailable", "reason": "unreachable"}
        try:
            d = r.json()
            items = d.get("news", []) or []
            arts = [{
                "title": a.get("title"),
                "url": a.get("url"),
                "published": a.get("published"),
                "author": a.get("author"),
            } for a in items[:10]]
            return {"status": "ok", "count": len(items), "articles": arts}
        except Exception as e:
            return {"status": "unavailable", "reason": f"parse_error:{e}"}

    # ── Sugra（聚合 LLM-ready，apiKey；端点本环境未核实）──────
    def _fetch_sugra(self) -> dict:
        if not SUGRA_API_KEY:
            return {"status": "key_missing", "reason": "no_sugra_key",
                    "note": "Sugra 端点/契约需在部署时确认（本环境无法核实）"}
        # 端点未在本环境核实；调用失败安全降级，绝不伪造成功
        r = self._get(SUGRA_API_URL, headers={"Authorization": f"Bearer {SUGRA_API_KEY}"})
        if r is None:
            return {"status": "unavailable", "reason": "unreachable"}
        try:
            return {"status": "ok", "observations": r.json()}
        except Exception as e:
            return {"status": "unavailable", "reason": f"parse_error:{e}"}

    def collect(self):
        m = self._fetch_marketaux()
        c = self._fetch_currents()
        s = self._fetch_sugra()
        if all(v.get("status") in ("unavailable", "key_missing") for v in (m, c, s)):
            overall = "unavailable"
        elif any(v.get("status") == "ok" for v in (m, c, s)):
            overall = "ok"
        else:
            overall = "partial"
        return {
            "status": overall,
            "marketaux": m,
            "currents": c,
            "sugra": s,
            "source": "MarketAux / Currents / Sugra",
        }

    def _is_good(self, data: dict) -> bool:
        return data.get("status") in ("ok", "partial")

def main():
    fetcher = NewsFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[news] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") in ("ok", "partial"):
        fetcher.save_json(OUTPUT_FILE, result)
        detail = (f"marketaux={result['marketaux'].get('status')} "
                  f"currents={result['currents'].get('status')} "
                  f"sugra={result['sugra'].get('status')}")
        print(f"[news] 完成 status={result.get('status')}，{detail}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[news] 降级 unavailable，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, result)
            print("[news] 降级 unavailable，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
