"""
fetch_rss_news.py — 从 RSSHub + 官方 RSS 拉取新闻
返回与 Crucix 文章格式兼容的 dict 列表，供 scan_weak_signals.py 合并入库。

v1.1 (2026-08-01): FT/BBC 路由从 RSSHub 切到官方 RSS（因 RSSHub /ft/myft、/bbc/world
返回 HTML 而非 RSS），其余 6 路保留 RSSHub。
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

logger = logging.getLogger(__name__)

RSSHUB_BASE = os.environ.get("RSSHUB_URL", "")
NAS_PROXY_URL = os.environ.get("NAS_PROXY_URL", "")

# (路径, 来源名, country_tag, 保留天数)
# 路径以 http:// 或 https:// 开头 = 外部直连 URL（不走 RSSHub），其余走 RSSHUB_BASE
RSS_ROUTES = [
    ("/caixin/k",                              "财新一线",      "CN",     3),
    ("/yicai/brief",                           "第一财经",      "CN",     3),
    ("/wallstreetcn/news/global",              "华尔街见闻",    "GLOBAL", 7),
    ("/eastmoney/report/strategyreport",       "东方财富研报",  "CN",    14),
    # ── EU/JP 信源（FT/BBC 切官方 RSS，其余保留 RSSHub）─────────────────────
    ("https://www.ft.com/world?format=rss",    "FT",            "EU",     3),
    ("http://feeds.bbci.co.uk/news/world/rss.xml", "BBC World", "EU",     3),
    ("/reuters/business",                      "Reuters Biz",   "GLOBAL", 3),
    ("/nikkei/news/category/markets",          "日経 Markets",  "JP",     3),
]


def _parse_date(entry) -> str | None:
    """从 feedparser entry 解析发布时间，返回 ISO 格式字符串或 None。"""
    # feedparser 已解析的 time_struct（UTC）
    if entry.get("published_parsed"):
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass
    # 原始字符串 fallback
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass
    return None


def _fetch_route(path: str, source: str, country_tag: str, days: int) -> list[dict]:
    """拉取单条 RSS 路由。

    path 以 http:// 或 https:// 开头时作为完整 URL（外部源，需代理）；
    否则拼 RSSHUB_BASE + path（内网 RSSHub）。
    """
    is_external = path.startswith("http://") or path.startswith("https://")
    url = path if is_external else f"{RSSHUB_BASE}{path}"

    # 外部源需要代理（容器内直连不可达）
    if is_external:
        os.environ.setdefault("http_proxy", NAS_PROXY_URL)
        os.environ.setdefault("https_proxy", NAS_PROXY_URL)

    cutoff = datetime.now(tz=timezone(timedelta(hours=8))) - timedelta(days=days)
    articles = []

    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            logger.warning("[RSS] %s parse error: %s", source, feed.bozo_exception)
            return []

        for entry in feed.entries:
            title = (entry.get("title") or "").strip()
            if not title:
                continue

            content = ""
            if entry.get("summary"):
                content = entry.summary.strip()
            elif entry.get("content"):
                content = entry.content[0].get("value", "").strip()

            pub_str = _parse_date(entry)
            if pub_str:
                pub_dt = datetime.fromisoformat(pub_str).replace(
                    tzinfo=timezone(timedelta(hours=8))
                )
                if pub_dt < cutoff:
                    continue

            link = entry.get("link") or entry.get("id") or ""

            articles.append({
                "title":        title,
                "content":      content,
                "url":          link,
                "published_at": pub_str,
                "source":       source,
                "country_tag":  country_tag,
            })

        logger.info("[RSS] %s: %d 篇", source, len(articles))

    except Exception as e:
        logger.warning("[RSS] %s 拉取失败: %s", source, e)

    return articles


def fetch_rss_news() -> list[dict]:
    """拉取所有 RSS 路由，返回合并后的文章列表。"""
    all_articles = []
    for path, source, country_tag, days in RSS_ROUTES:
        try:
            items = _fetch_route(path, source, country_tag, days)
            all_articles.extend(items)
        except Exception as e:
            logger.warning("[RSS] %s 跳过: %s", source, e)
    logger.info("[RSS] 合计 %d 篇", len(all_articles))
    return all_articles
