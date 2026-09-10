# -*- coding: utf-8 -*-
"""fetch_news.py — 新闻 / 市场情报聚合（P1 归并模块）

08-14 改造（源现状 + 用户拍板）：
  - 主源：GDELT DOC 2.0（免费无 key，英文新闻全文 + tone/goldstein 情感分数，
          每天 5000 请求；容器内 api.gdeltproject.org 直连可达）
  - 增强：MarketAux（金融 ticker 情绪 + 符号频率；需 apiKey，未配置时不影响主源，
          2026-08-14 实测其免费注册通道服务端报错，key 配置后自动启用）
  - 已摘除（保留历史说明）：
      Currents —— 2026-08 官网注册入口已消失（首页/FAQ/Docs 均无 Sign up），
                  且免费条款限制长期存储，新用户无法获取 key
      Sugra —— api.sugra.ai 域名 DNS 不存在（幽灵端点），配 key 也无用

输出 news_risk.json：
  {
    "status": "ok" | "unavailable",
    "updated": "...",
    "source": "GDELT DOC 2.0 / MarketAux",
    "gdelt":    {status, count, articles: [{title,url,domain,published_at,tone,goldstein}]},
    "marketaux": {status, ...},          # key_missing 时仅标注
    "articles": [...]                    # 前端便捷通道（top 聚合）
  }

降级：每子源独立 try/except；主源失败且本地有上次良值则保留、不覆盖、绝不 crash。
网络出口：直连优先，失败回退代理（_get 实现）。
"""

import datetime
import json
import os
import sys
from collections import Counter

from fetcher_base import FetcherBase, Status

try:
    from optim_config import (
        DATA_DIR, PROXY_URL,
        MARKETAUX_API_KEY, MARKETAUX_API_URL,
    )
except Exception:
    DATA_DIR = os.environ.get("DATA_DIR", "/workspace/data")
    PROXY_URL = os.environ.get("PROXY_URL", "")
    MARKETAUX_API_KEY = os.environ.get("MARKETAUX_API_KEY", "")
    MARKETAUX_API_URL = os.environ.get(
        "MARKETAUX_API_URL", "https://api.marketaux.com/v1/news/all"
    )

OUTPUT_FILE = "news_risk.json"

# GDELT DOC 2.0（免费无 key；每次请求 1 个 query，OR 关键词必须括号包裹）
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = (
    '(market OR finance OR economy OR "geopolitical risk" OR oil OR gold '
    'OR conflict OR war OR sanctions OR crisis)'
)
GDELT_MAXRECORDS = 15
GDELT_MIN_INTERVAL = 5.0  # GDELT DOC 2.0 限速：每 5 秒 1 请求（429 实测）


def _seendate_to_iso(seendate: str) -> str:
    """GDELT seendate 两种格式 → ISO 'YYYY-MM-DDTHH:MM:SSZ'（UTC）。

    artlist JSON 实测格式：'20260710T043000Z'；旧版也可能 'YYYYMMDDHHMMSS'。
    """
    s = str(seendate or "").strip()
    if len(s) >= 16 and s[8] == "T" and s.endswith("Z"):
        # '20260710T043000Z' → '2026-07-10T04:30:00Z'
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}Z"
    if len(s) >= 14 and s.isdigit():
        # '20260710043000' → '2026-07-10T04:30:00Z'
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:14]}Z"
    return ""


def _dt_ts(a: dict) -> float:
    """文章 published_at → epoch 秒（排序用；解析失败返回 0）。"""
    try:
        import datetime as _dt
        return _dt.datetime.fromisoformat(
            (a.get("published_at") or "").replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return 0.0


class NewsFetcher(FetcherBase):
    name = "news"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "I30"   # 30min：MarketAux 48/天≈48% 贴 50% 水位；GDELT 48/天≈0.96%（08-14 提频保实时）

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

    # ── GDELT DOC 2.0（主源，免费无 key）──────────────────────
    def _fetch_gdelt_doc(self) -> dict:
        import time as _time
        _time.sleep(GDELT_MIN_INTERVAL)  # 限速尊重（每 5 秒 1 请求）
        params = {
            "query": GDELT_QUERY,
            "mode": "artlist",
            "format": "json",
            "maxrecords": GDELT_MAXRECORDS,
            "timespan": "1d",          # 最近 24h（实测不带 timespan 会返回月前旧闻）
            "sourcelang": "eng",
        }
        try:
            r = self._get(GDELT_DOC_URL, params=params,
                          headers={"User-Agent": "Mozilla/5.0"})
        except Exception as e:
            return {"status": "unavailable", "reason": f"request_error:{e}"}
        if r is None:
            return {"status": "unavailable", "reason": "unreachable"}
        try:
            d = r.json()
            items = (d.get("articles") or [])[:GDELT_MAXRECORDS]
            arts = []
            for a in items:
                lang = (a.get("language") or "").lower()
                # 英文优先排序（sourcelang 参数实测不完全生效，客户端兜底）
                arts.append({
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "domain": a.get("domain"),
                    "source": a.get("domain"),
                    "published_at": _seendate_to_iso(a.get("seendate")),
                    "language": a.get("language"),
                    "sourcecountry": a.get("sourcecountry"),
                    "_eng": lang.startswith("english"),
                })
            arts.sort(key=lambda a: (0 if a.pop("_eng") else 1, -_dt_ts(a)))
            return {"status": "ok", "count": len(items), "articles": arts}
        except Exception as e:
            return {"status": "unavailable", "reason": f"parse_error:{e}"}

    # ── MarketAux（金融新闻 + ticker 情绪，apiKey；可选增强）────
    def _fetch_marketaux(self) -> dict:
        if not MARKETAUX_API_KEY:
            return {"status": "key_missing", "reason": "no_marketaux_key",
                    "note": "MarketAux 免费注册通道 2026-08 服务端异常，key 配置后自动启用"}
        try:
            r = self._get(MARKETAUX_API_URL, params={
                "api_token": MARKETAUX_API_KEY, "limit": 10,
                "languages": "en", "filter_entities": True,
            })
        except Exception as e:
            return {"status": "unavailable", "reason": f"request_error:{e}"}
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

    def collect(self):
        g = self._fetch_gdelt_doc()
        m = self._fetch_marketaux()
        if g.get("status") == "ok":
            overall = "ok"
        elif m.get("status") == "ok":
            overall = "partial"
        else:
            overall = "unavailable"
        return {
            "status": overall,
            "gdelt": g,
            "marketaux": m,
            "articles": (g.get("articles") or []) + (m.get("articles") or []),
            "source": "GDELT DOC 2.0 / MarketAux",
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
        detail = (f"gdelt={result['gdelt'].get('status')} "
                  f"marketaux={result['marketaux'].get('status')}")
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
