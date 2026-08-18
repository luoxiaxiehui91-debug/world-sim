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
