"""
fetch_defense_rss.py — 防务/军事类 RSS 信源

接入三个防务媒体：
  - Al Jazeera English（中东/全球地缘）
  - Defense One（美国防务政策）
  - War on the Rocks（战略分析）

输出文章写入 narrative_processor 的 narrative_chunks 表，
同时以 list[dict] 返回供 scan_weak_signals.py 合并入库。

来源标记用于 source_dimension_map 分配 GRV 维度：
  aljazeera   → middle_east_energy
  defense_one → taiwan_strait
  war_on_rocks → russia_europe
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

logger = logging.getLogger(__name__)

PROXY = os.environ.get("OUTBOUND_PROXY", "")

DEFENSE_FEEDS = [
    # (url, source_id, 保留天数)
    ("https://www.aljazeera.com/xml/rss/all.xml",           "aljazeera",    3),
    ("https://www.defenseone.com/rss/all/",                 "defense_one",  3),
    ("https://warontherocks.com/feed/",                     "war_on_rocks", 5),
]


def _parse_date(entry) -> str:
    if entry.get("published_parsed"):
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.astimezone(timezone(timedelta(hours=8))).isoformat()
        except Exception:
            pass
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            return dt.astimezone(timezone(timedelta(hours=8))).isoformat()
        except Exception:
            pass
    return datetime.now().isoformat()


def _fetch_feed(url: str, source_id: str, days: int) -> list[dict]:
    cutoff = datetime.now(tz=timezone(timedelta(hours=8))) - timedelta(days=days)
    articles = []

    try:
        # 走代理（容器内需代理访问外网）
        if PROXY:
            os.environ["http_proxy"]  = PROXY
            os.environ["https_proxy"] = PROXY

        feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})

        if PROXY:
            os.environ.pop("http_proxy",  None)
            os.environ.pop("https_proxy", None)

        if feed.bozo and not feed.entries:
            logger.warning("[defense_rss] %s parse error: %s", source_id, feed.bozo_exception)
            return []

        for entry in feed.entries:
            pub = _parse_date(entry)
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone(timedelta(hours=8)))
                if pub_dt < cutoff:
                    continue
            except Exception:
                pass

            title   = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            # 去掉 HTML 标签
            import re
            summary = re.sub(r"<[^>]+>", " ", summary).strip()
            summary = re.sub(r"\s+", " ", summary)[:500]

            if not title:
                continue

            articles.append({
                "source":     source_id,
                "title":      title,
                "summary":    summary,
                "published_at": pub,
                "url":        entry.get("link", ""),
                "country_tag": _source_to_country(source_id),
            })

    except Exception as e:
        logger.warning("[defense_rss] %s fetch failed: %s", source_id, e)

    return articles


def _source_to_country(source_id: str) -> str:
    return {"aljazeera": "ME", "defense_one": "US", "war_on_rocks": "GLOBAL"}.get(source_id, "GLOBAL")


def fetch_defense_rss() -> list[dict]:
    """
    拉取所有防务 RSS，返回文章列表。
    同时写入 narrative_chunks 表（叙事预处理）。
    """
    all_articles = []
    for url, source_id, days in DEFENSE_FEEDS:
        articles = _fetch_feed(url, source_id, days)
        all_articles.extend(articles)
        if articles:
            print(f"[defense_rss] {source_id}: {len(articles)} 条")

    # 写入 narrative_chunks
    if all_articles:
        try:
            from narrative_processor import ingest_article, load_source_map
            source_map = load_source_map()
            ingested = 0
            for art in all_articles:
                content = f"{art['title']}\n{art['summary']}".strip()
                result = ingest_article(
                    source_id=art["source"],
                    content=content,
                    timestamp=art["published_at"],
                    source_map=source_map,
                )
                if result["status"] == "ok":
                    ingested += 1
            print(f"[defense_rss] 叙事预处理写入 {ingested} 条")
        except Exception as e:
            print(f"[defense_rss] 叙事预处理失败（非阻断）: {e}")

    return all_articles


if __name__ == "__main__":
    articles = fetch_defense_rss()
    print(f"\n共获取 {len(articles)} 条防务新闻")
    for a in articles[:3]:
        print(f"  [{a['source']}] {a['title'][:60]}")
