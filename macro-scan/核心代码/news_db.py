"""
news_db.py — 新闻库持久化模块（N1 第一阶段）

职责：
  - 维护 news.db（SQLite），包含 scan_contexts / articles /
    article_categories / signal_episodes / episode_articles / signal_outcomes
  - 全量归档天枢自采新闻文章（RSS / defense_rss 源，url 或 content_hash 去重；crucix 已非新闻源）
  - 给每篇文章打关键词类别标签
  - 记录信号触发事件（signal_episodes）及关联文章
  - 提供"触发文章标题"查询接口（供 latest_news.json 增强使用）

第二阶段（N2，数据积累 ≥180 天后）将在此基础上加入反向宏观查询。
第三阶段（N3，≥1 年后）加入 signal_outcomes 月度校验写入。
"""

import email.utils
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta

# E0-A: 旁路双写 worldsim-pg（非阻断，异常自吞，绝不阻断 SQLite 主流程）
from pg_write_collection import (
    upsert_news_scan_context, upsert_news_article, upsert_news_article_category,
    upsert_news_signal_episode, upsert_news_episode_article, delete_news_articles,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_contexts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_time    TEXT NOT NULL,
    vix          REAL,
    t10y2y       REAL,
    baa10y       REAL,
    dff          REAL,
    regime       TEXT,
    vix_regime   TEXT,
    data_quality TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT,
    content_hash  TEXT,
    title         TEXT NOT NULL,
    source        TEXT,
    published_at  TEXT,
    ingested_at   TEXT NOT NULL,
    country_tag   TEXT,
    ingest_ctx_id INTEGER REFERENCES scan_contexts(id),
    pub_ctx_id    INTEGER REFERENCES scan_contexts(id)
);

CREATE TABLE IF NOT EXISTS article_categories (
    article_id INTEGER NOT NULL REFERENCES articles(id),
    category   TEXT    NOT NULL,
    PRIMARY KEY (article_id, category)
);

CREATE TABLE IF NOT EXISTS signal_episodes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT NOT NULL,
    triggered_at TEXT NOT NULL,
    ratio        REAL,
    level        TEXT,
    scan_ctx_id  INTEGER REFERENCES scan_contexts(id)
);

CREATE TABLE IF NOT EXISTS episode_articles (
    episode_id INTEGER NOT NULL REFERENCES signal_episodes(id),
    article_id INTEGER NOT NULL REFERENCES articles(id),
    PRIMARY KEY (episode_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_scan_contexts_time ON scan_contexts(scan_time DESC);
CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_articles_ingested ON articles(ingested_at DESC);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id     INTEGER REFERENCES signal_episodes(id),
    check_date     TEXT,
    check_horizon  TEXT,
    spx_return     REAL,
    dgs10_change   REAL,
    vix_change     REAL,
    usdx_change    REAL,
    outcome_regime TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url
    ON articles(url) WHERE url IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_hash
    ON articles(content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_pub
    ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_ingest_ctx
    ON articles(ingest_ctx_id);
CREATE INDEX IF NOT EXISTS idx_articles_pub_ctx
    ON articles(pub_ctx_id);
CREATE INDEX IF NOT EXISTS idx_ac_category
    ON article_categories(category);
CREATE INDEX IF NOT EXISTS idx_episodes_cat
    ON signal_episodes(category, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_ea_episode
    ON episode_articles(episode_id);
CREATE INDEX IF NOT EXISTS idx_ea_article
    ON episode_articles(article_id);

CREATE TABLE IF NOT EXISTS synthesis_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id         TEXT    NOT NULL,
    triggered_at    TEXT    NOT NULL,
    scan_ctx_id     INTEGER REFERENCES scan_contexts(id),
    trigger_summary TEXT,
    hypothesis_text TEXT,
    llm_success     INTEGER DEFAULT 0,
    ntfy_success    INTEGER DEFAULT 0,
    suppress_reason TEXT,
    report_excerpt  TEXT
);
CREATE INDEX IF NOT EXISTS idx_synthesis_log_rule
    ON synthesis_log(rule_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_synthesis_log_date
    ON synthesis_log(triggered_at DESC);
"""


# ── 连接 ──────────────────────────────────────────────────────────────────────

def _conn(db_path: str) -> sqlite3.Connection:
    """打开 SQLite 连接，启用 WAL 模式（支持读写并发），超时15s。"""
    c = sqlite3.connect(db_path, timeout=15)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")
    c.row_factory = sqlite3.Row
    return c


# ── 初始化 ────────────────────────────────────────────────────────────────────

def init_db(db_path: str) -> None:
    """创建 news.db 并执行 DDL 建表（幂等，已存在则跳过）。"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    c = _conn(db_path)
    with c:
        c.executescript(_SCHEMA)
    c.close()


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _normalize_dt(raw: str) -> str | None:
    """将 RFC822 / ISO 日期统一规整为 UTC aware ISO（带 +00:00 后缀）。

    来源时间多为北京时间(+08:00)且缺时区后缀，按北京时间解释后转 UTC，
    遵守时区契约（落盘必须带显式后缀）。解析彻底失败返回 None（不落垃圾）。
    """
    if not raw:
        return None
    s = raw.strip()
    dt = None
    # 先试 ISO（含可能的 Z / +00:00）
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    # 再试 RFC822（email.utils，能感知 GMT/UTC 等时区后缀）
    if dt is None:
        try:
            dt = email.utils.parsedate_to_datetime(s)
        except Exception:
            dt = None
    if dt is None:
        return None
    # naive（缺时区）→ 当作北京时间 +08:00 解释（实测 22017 行冲突根因）
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _article_hash(art: dict) -> str:
    """用 title + source + 发布日期前10位 生成内容指纹，用于去重。"""
    title  = (art.get("title") or "").strip().lower()
    source = (art.get("source") or art.get("channel") or "").strip().lower()
    pub    = (_normalize_dt(
        art.get("published_at") or art.get("pubDate") or art.get("date") or ""
    ) or "")[:10]
    return hashlib.sha256(f"{title}|{source}|{pub}".encode()).hexdigest()


def _find_pub_ctx(c: sqlite3.Connection, published_at: str | None) -> int | None:
    """按文章发布时间，在 scan_contexts 历史里找最近一条快照 ID。"""
    if not published_at:
        return None
    try:
        row = c.execute(
            "SELECT id FROM scan_contexts WHERE scan_time <= ? ORDER BY scan_time DESC LIMIT 1",
            (published_at,)
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


# ── scan_contexts ─────────────────────────────────────────────────────────────

def write_scan_context(db_path: str, *,
                       vix: float | None = None,
                       t10y2y: float | None = None,
                       baa10y: float | None = None,
                       dff: float | None = None,
                       regime: str | None = None,
                       vix_regime: str | None = None,
                       data_quality: dict | None = None) -> int:
    """写入一条扫描快照，返回新行 ID（供文章关联使用）。"""
    now = datetime.now(timezone.utc).isoformat()
    c = _conn(db_path)
    with c:
        cur = c.execute(
            """INSERT INTO scan_contexts
               (scan_time, vix, t10y2y, baa10y, dff, regime, vix_regime, data_quality)
               VALUES (?,?,?,?,?,?,?,?)""",
            (now, vix, t10y2y, baa10y, dff, regime, vix_regime,
             json.dumps(data_quality) if data_quality else None)
        )
        ctx_id = cur.lastrowid
    upsert_news_scan_context(ctx_id, now, vix, t10y2y, baa10y, dff, regime,
                             vix_regime, json.dumps(data_quality) if data_quality else None)
    c.close()
    return ctx_id


# ── articles ──────────────────────────────────────────────────────────────────

def insert_articles(db_path: str,
                    articles: list[dict],
                    ingest_ctx_id: int) -> dict[str, int]:
    """
    全量入库，url 或 content_hash 去重（INSERT OR IGNORE）。
    返回 {content_hash: article_id}，供 tag_articles 使用。
    """
    if not articles:
        return {}
    now = datetime.now(timezone.utc).isoformat()
    c = _conn(db_path)
    result: dict[str, int] = {}
    with c:
        for art in articles:
            title = (art.get("title") or "").strip()
            if not title:
                continue
            url    = art.get("url") or None
            source = art.get("source") or art.get("channel") or ""
            h      = _article_hash(art)
            pub    = _normalize_dt(
                art.get("published_at") or art.get("pubDate") or art.get("date")
            )
            pub_ctx_id = _find_pub_ctx(c, pub)

            # 已存在则直接返回 id
            existing = None
            if url:
                row = c.execute("SELECT id FROM articles WHERE url=?", (url,)).fetchone()
                if row:
                    existing = row[0]
            if existing is None:
                row = c.execute("SELECT id FROM articles WHERE content_hash=?", (h,)).fetchone()
                if row:
                    existing = row[0]
            if existing is not None:
                result[h] = existing
                continue

            cur = c.execute(
                """INSERT OR IGNORE INTO articles
                   (url, content_hash, title, source, published_at, ingested_at,
                    country_tag, ingest_ctx_id, pub_ctx_id)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (url, h, title, source, pub, now, None, ingest_ctx_id, pub_ctx_id)
            )
            aid = cur.lastrowid
            if not aid:
                row = c.execute("SELECT id FROM articles WHERE content_hash=?", (h,)).fetchone()
                aid = row[0] if row else None
            if aid:
                upsert_news_article(aid, url, h, title, source, pub, now, None,
                                    ingest_ctx_id, pub_ctx_id)
                result[h] = aid
    c.close()
    return result


# ── article_categories ────────────────────────────────────────────────────────

def tag_articles(db_path: str,
                 hash_to_id: dict[str, int],
                 articles: list[dict],
                 alert_keywords: dict[str, list[str]]) -> dict[str, list[int]]:
    """
    对每篇文章按 alert_keywords 打类别标签。
    返回 {category: [article_id, ...]}，供 link_episode_articles 使用。
    """
    if not hash_to_id or not articles:
        return {}
    cat_to_ids: dict[str, list[int]] = {}
    c = _conn(db_path)
    with c:
        for art in articles:
            h   = _article_hash(art)
            aid = hash_to_id.get(h)
            if not aid:
                continue
            text = (art.get("title", "") + " " + art.get("content", "")).lower()
            for cat, kws in alert_keywords.items():
                if any(kw.lower() in text for kw in kws):
                    try:
                        c.execute(
                            "INSERT OR IGNORE INTO article_categories (article_id, category) VALUES (?,?)",
                            (aid, cat)
                        )
                        upsert_news_article_category(aid, cat)
                        cat_to_ids.setdefault(cat, []).append(aid)
                    except Exception:
                        pass
    c.close()
    return cat_to_ids


# ── signal_episodes ───────────────────────────────────────────────────────────

def insert_signal_episode(db_path: str,
                          category: str,
                          ratio: float,
                          level: str,
                          scan_ctx_id: int) -> int:
    """记录一次信号触发事件，返回 episode_id（供 link_episode_articles 关联文章）。"""
    now = datetime.now(timezone.utc).isoformat()
    c = _conn(db_path)
    with c:
        cur = c.execute(
            """INSERT INTO signal_episodes (category, triggered_at, ratio, level, scan_ctx_id)
               VALUES (?,?,?,?,?)""",
            (category, now, ratio, level, scan_ctx_id)
        )
        ep_id = cur.lastrowid
    upsert_news_signal_episode(ep_id, category, now, ratio, level, scan_ctx_id)
    c.close()
    return ep_id


def link_episode_articles(db_path: str,
                          episode_id: int,
                          article_ids: list[int]) -> None:
    """将文章 ID 列表关联到信号事件（INSERT OR IGNORE，防重复）。"""
    if not article_ids:
        return
    c = _conn(db_path)
    with c:
        for aid in article_ids:
            c.execute(
                "INSERT OR IGNORE INTO episode_articles (episode_id, article_id) VALUES (?,?)",
                (episode_id, aid)
            )
            upsert_news_episode_article(episode_id, aid)
    c.close()


# ── 查询接口 ──────────────────────────────────────────────────────────────────

def get_trigger_titles(db_path: str,
                       category: str,
                       ingest_ctx_id: int,
                       limit: int = 3) -> list[str]:
    """
    返回本次扫描中触发 category 的前 N 篇文章标题（按发布时间倒序）。
    供 latest_news.json 的 trigger_titles 字段使用。
    """
    c = _conn(db_path)
    rows = c.execute(
        """SELECT a.title FROM articles a
           JOIN article_categories ac ON a.id = ac.article_id
           WHERE ac.category = ? AND a.ingest_ctx_id = ?
           ORDER BY a.published_at DESC
           LIMIT ?""",
        (category, ingest_ctx_id, limit)
    ).fetchall()
    c.close()
    return [r[0] for r in rows]


# ── 维护接口 ──────────────────────────────────────────────────────────────────

def prune_old_articles(db_path: str, days: int = 90) -> int:
    """
    删除 ingested_at 超过 days 天的 articles 及关联的 article_categories。
    不删除 signal_episodes（保留信号历史供回测）。
    返回删除的文章行数。
    """
    c = _conn(db_path)
    cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    # SQLite datetime 运算：取 ingested_at < now - N days
    rows = c.execute(
        """SELECT id FROM articles
           WHERE ingested_at < datetime(?, ?)""",
        (cutoff, f"-{days} days")
    ).fetchall()
    if not rows:
        c.close()
        return 0

    old_ids = [r[0] for r in rows]
    delete_news_articles(old_ids)   # E0-A 双写镜像删除
    # 分批删除避免 SQLite 变量上限（999）
    batch = 200
    deleted = 0
    for i in range(0, len(old_ids), batch):
        chunk = old_ids[i:i + batch]
        placeholders = ",".join("?" * len(chunk))
        c.execute(f"DELETE FROM article_categories WHERE article_id IN ({placeholders})", chunk)
        c.execute(f"DELETE FROM episode_articles WHERE article_id IN ({placeholders})", chunk)
        c.execute(f"DELETE FROM articles WHERE id IN ({placeholders})", chunk)
        deleted += len(chunk)
    c.commit()
    c.close()
    return deleted
