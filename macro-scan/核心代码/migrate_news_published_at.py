#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_news_published_at.py — C1 时区抢救迁移脚本

背景（实测根因，2026-08-12）：
  news.db.articles.published_at 中 9790 行 RFC822 naive + 部分 ISO naive 串，
  实际语义是北京时间(+08:00)存储但缺时区后缀，ingested_at 是真 UTC(+00:00)。
  两者时区基准不一致导致 22017/32092 (68.6%) 行 published_at > ingested_at 虚假逻辑矛盾。
  实测：把 naive published_at 当作北京时间解释后转 UTC，冲突归零（0/32092）。

修复策略：
  逐行重解析 published_at：
    - ISO / RFC822 均可解析；naive（缺时区）一律按北京时间 +08:00 解释 → 转 UTC → 存 +00:00 后缀 ISO。
    - 真不可解析（理论上 0 行）：计数 quarantine，保持原值不破坏（下游另行处理）。
  遵守时区契约（落盘必须带显式后缀）。

用法：
  python migrate_news_published_at.py --dry     # 仅统计，不改库
  python migrate_news_published_at.py           # 真实执行 UPDATE
"""
import sys
import sqlite3
import email.utils
from datetime import datetime, timezone, timedelta

DB = "/workspace/data/news.db"
BJ = timezone(timedelta(hours=8))
DRY = "--dry" in sys.argv


def _parse(raw: str):
    s = raw.strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    try:
        return email.utils.parsedate_to_datetime(s)
    except Exception:
        return None


def main():
    c = sqlite3.connect(DB)
    c.execute("PRAGMA busy_timeout=30000")
    updated = quarantined = skipped = 0
    for aid, pa in c.execute("SELECT id, published_at FROM articles").fetchall():
        if not pa:
            skipped += 1
            continue
        dt = _parse(pa)
        if dt is None:
            quarantined += 1
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BJ)
        nv = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        if nv != pa:
            updated += 1
            if not DRY:
                c.execute("UPDATE articles SET published_at=? WHERE id=?", (nv, aid))
    if not DRY:
        c.commit()
    conf = c.execute(
        "SELECT COUNT(*) FROM articles a WHERE a.published_at > a.ingested_at"
    ).fetchone()[0]
    print(f"DRY={DRY} updated={updated} quarantined={quarantined} "
          f"skipped={skipped} remaining_conflict={conf}")
    c.close()


if __name__ == "__main__":
    main()
