import os
import sys
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from optim_config import DATA_DIR, NEWS_EXPORT_PATH
import pg_read  # E0-C: 读路径切 PG（原 sqlite3 news.db）

# DB 中文类别 → 导出英文标签（未列入的类别不导出）
# 注：「文化贸易摩擦」「科技竞争」「自然灾害」暂无 macro-sim handler，
# 待 macro-sim 侧增加对应接收端后再补充映射（backlog）
CATEGORY_MAP = {
    "地缘升级":     "geopolitics",
    "社会政治危机": "geopolitics",
    "宗教族群冲突": "geopolitics",
    "能源政治":     "energy",
    "战略矿产":     "energy",
    "信用风险":     "finance",
    "流动性危机":   "finance",
    "衰退信号":     "macro",
    "通胀失控":     "macro",
    "日元套利":     "monetary",
}

MAX_ARTICLES = 40
DAYS_BACK = 7

# 10-13（CHG-20261013T093037）：news_all 英文标题中译（FT / BBC 官方源）。
# 复用 fetch_news_titles._translate_titles（同一 usage=translate_titles 配置链，守 G1）。
# 仅作用于 export_all_news（开阳新闻面板，人看）；export_news_for_sim（news_export.json，
# 喂 macro-sim AI 推演）不翻——原文对推演更准，避免误伤下游。
ZH_CACHE_FILE = "news_zh_titles.json"   # url -> 中文标题缓存
ZH_BATCH = 50            # 每轮最多翻译条数（news_all 上限 100 篇，英文约 30）
ZH_CACHE_MAX = 5000      # 缓存上限（FIFO 淘汰）
ZH_CACHE_PATH = os.path.join(DATA_DIR, ZH_CACHE_FILE)

# E0-C: PG 占位符 %s（原 SQLite ?）；news. 前缀显式 schema
_PLACEHOLDERS = ",".join(["%s"] * len(CATEGORY_MAP))
# 全量新闻通道（08-14 C 方案：开阳新闻面板读 news_all.json，含未分类文章；news_export.json 保持风险信号流）
NEWS_ALL_PATH = os.path.join(DATA_DIR, "news_all.json")
SQL_ALL = (
    "SELECT a.title, a.url, a.source, a.published_at "
    "FROM news.articles a "
    "ORDER BY a.published_at DESC "
    "LIMIT 100"
)

SQL = (
    "SELECT a.title, a.url, a.source, ac.category, a.published_at "
    "FROM news.articles a "
    "JOIN news.article_categories ac ON a.id = ac.article_id "
    "WHERE ac.category IN ({ph}) "
    "ORDER BY a.published_at DESC "
    "LIMIT 500"
).format(ph=_PLACEHOLDERS)


def _parse_date(pub: str) -> str:
    """把 published_at 统一转成 YYYY-MM-DD，兼容 ISO 和 RFC-style 两种格式。"""
    if not pub:
        return ""
    if pub[0].isdigit() and len(pub) >= 10 and pub[4] == "-":
        return pub[:10]
    try:
        import email.utils
        t = email.utils.parsedate(pub)
        if t:
            return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"
    except Exception:
        pass
    return pub[:10]


def export_news_for_sim():
    conn = pg_read.connect()
    if conn is None:
        print("[news_exporter] PG 读连接不可用（worldsim-pg），跳过导出")
        return
    try:
        rows = conn.execute(SQL, tuple(CATEGORY_MAP.keys())).fetchall()
    finally:
        conn.close()

    articles = []
    cutoff = (datetime.date.today() - datetime.timedelta(days=DAYS_BACK)).isoformat()
    for row in rows:
        d = _parse_date(row["published_at"])
        if d and d >= cutoff:
            articles.append({
                "title":    row["title"],
                "url":      row["url"] or None,
                "source":   row["source"] or None,
                "category": CATEGORY_MAP[row["category"]],
                "date":     d,
            })
        if len(articles) >= MAX_ARTICLES:
            break

    payload = {
        "_schema_version": "1.0",
        "exported_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        # P0 修复（news-fake-timestamp）：顶层 updated 对齐前端 useFeed.ts:62 读取字段
        "updated":     datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "articles":    articles,
    }

    os.makedirs(os.path.dirname(NEWS_EXPORT_PATH), exist_ok=True)
    _tmp_100 = NEWS_EXPORT_PATH + ".tmp"
    with open(_tmp_100, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(_tmp_100, NEWS_EXPORT_PATH)

    print(f"[news_exporter] exported {len(articles)} articles -> {NEWS_EXPORT_PATH}")


def _load_zh_cache() -> dict:
    """10-13：中文标题缓存（url -> 中文）。读失败视为空。"""
    try:
        with open(ZH_CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_zh_cache(cache: dict) -> None:
    """10-13：缓存落盘（原子写 + FIFO 淘汰）。失败仅告警，不阻塞导出。"""
    try:
        if len(cache) > ZH_CACHE_MAX:
            for k in list(cache)[: len(cache) - ZH_CACHE_MAX]:
                cache.pop(k, None)
        _tmp_zh = ZH_CACHE_PATH + ".tmp"
        with open(_tmp_zh, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(_tmp_zh, ZH_CACHE_PATH)
    except Exception as e:
        print(f"[news_exporter] 中文标题缓存落盘失败: {e}")


def _translate_zh(articles: list) -> None:
    """10-13：给英文标题文章补 title_zh（原地修改）。仅「无中文且缓存未命中」才翻；
    失败保留英文，不阻塞导出。"""
    import re
    cache = _load_zh_cache()
    todo = {}
    for a in articles:
        url = (a.get("url") or "").strip()
        title = (a.get("title") or "").strip()
        if (url and title and not re.search("[一-龥]", title)
                and url not in cache and url not in todo):
            todo[url] = title
        if len(todo) >= ZH_BATCH:
            break
    if not todo:
        return
    try:
        from fetch_news_titles import _translate_titles
        zh = _translate_titles(todo) or {}
    except Exception as e:
        print(f"[news_exporter] 中文翻译不可用（保留英文）: {str(e)[:80]}")
        return
    if zh:
        cache.update(zh)
        _save_zh_cache(cache)
        print(f"[news_exporter] 标题中译 {len(zh)}/{len(todo)}")
    for a in articles:
        url = (a.get("url") or "").strip()
        if url in cache:
            a["title_zh"] = cache[url]


def export_all_news() -> None:
    """全量新闻导出（08-14 C 方案）：最新 100 篇含未分类，供开阳新闻面板（news_all.json）。"""
    conn = pg_read.connect()
    if conn is None:
        print("[news_exporter] PG 读连接不可用（worldsim-pg），跳过全量导出")
        return
    try:
        rows = conn.execute(SQL_ALL).fetchall()
    finally:
        conn.close()

    articles = []
    cutoff = (datetime.date.today() - datetime.timedelta(days=DAYS_BACK)).isoformat()
    for row in rows:
        d = _parse_date(row["published_at"])
        if d and d >= cutoff:
            articles.append({
                "title":    row["title"],
                "url":      row["url"] or None,
                "source":   row["source"] or None,
                "category": None,   # 未分类/全量：category 交给前端兜底
                "date":     d,
            })

    _translate_zh(articles)

    payload = {
        "_schema_version": "1.0",
        "exported_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated":     datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "articles":    articles,
    }
    os.makedirs(os.path.dirname(NEWS_ALL_PATH), exist_ok=True)
    _tmp_137 = NEWS_ALL_PATH + ".tmp"
    with open(_tmp_137, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(_tmp_137, NEWS_ALL_PATH)
    print(f"[news_exporter] exported {len(articles)} all-news -> {NEWS_ALL_PATH}")


if __name__ == "__main__":
    export_news_for_sim()
    export_all_news()
