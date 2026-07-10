import os
import sys
import json
import sqlite3
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from optim_config import DATA_DIR, NEWS_EXPORT_PATH

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

_PLACEHOLDERS = ",".join("?" * len(CATEGORY_MAP))
# 不用 SQLite datetime 过滤（旧格式行无法比较），多取后 Python 侧按日期过滤
SQL = (
    "SELECT a.title, ac.category, a.published_at "
    "FROM articles a "
    "JOIN article_categories ac ON a.id = ac.article_id "
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
    db_path = os.path.join(DATA_DIR, "news.db")
    if not os.path.exists(db_path):
        print(f"[news_exporter] news.db not found: {db_path}")
        return

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
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
                "category": CATEGORY_MAP[row["category"]],
                "date":     d,
            })
        if len(articles) >= MAX_ARTICLES:
            break

    payload = {
        "_schema_version": "1.0",
        "exported_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "articles":    articles,
    }

    os.makedirs(os.path.dirname(NEWS_EXPORT_PATH), exist_ok=True)
    with open(NEWS_EXPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[news_exporter] exported {len(articles)} articles -> {NEWS_EXPORT_PATH}")


if __name__ == "__main__":
    export_news_for_sim()
