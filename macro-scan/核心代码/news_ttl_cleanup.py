# -*- coding: utf-8 -*-
"""news_ttl_cleanup.py — news.articles TTL 清理（P2）

保留最近 TTL_DAYS 天的新闻；更早的行删除，防止 PG 无限增长。
由 scheduler 每日 03:00 触发。失败仅记日志不阻断。

设计：
  - TTL_DAYS = 90（约 3 个月，涵盖当前最长分析窗口）
  - DELETE ... WHERE published_at < NOW() - INTERVAL '90 days'
  - 执行前打印将删行数（dry-run log），执行后确认实删数
  - VACUUM ANALYZE 后跑（可选，不阻断）
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TTL_DAYS = int(os.environ.get("NEWS_TTL_DAYS", "90"))

_TAG = "[news_ttl_cleanup]"


def _connect_write():
    import psycopg
    from psycopg.rows import dict_row
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        raise RuntimeError("WORLDSIM_APP_PW 未注入")
    return psycopg.connect(
        host="worldsim-pg", port=5432, dbname="worldsim",
        user="worldsim_app", password=pw,
        row_factory=dict_row,
        options="-c search_path=news,public",
    )


def run():
    start = datetime.now()
    print(f"{_TAG} 开始 TTL 清理，保留最近 {TTL_DAYS} 天，{start.isoformat(timespec='seconds')}", flush=True)
    try:
        conn = _connect_write()
    except Exception as e:
        print(f"{_TAG} PG 连接失败，跳过清理：{e}", flush=True)
        return

    try:
        cutoff = timedelta(days=TTL_DAYS)

        # dry-run count
        r = conn.execute(
            "SELECT COUNT(*) AS cnt FROM articles WHERE published_at < NOW() - %s",
            (cutoff,),
        ).fetchone()
        to_delete = r["cnt"] if r else 0
        print(f"{_TAG} 将删除 {to_delete} 行（published_at < NOW() - {TTL_DAYS}d）", flush=True)

        if to_delete == 0:
            print(f"{_TAG} 无需清理，退出。", flush=True)
            return

        # DELETE
        cur = conn.execute(
            "DELETE FROM articles WHERE published_at < NOW() - %s",
            (cutoff,),
        )
        deleted = cur.rowcount
        conn.commit()
        print(f"{_TAG} 已删除 {deleted} 行。", flush=True)

        # 剩余行数
        r2 = conn.execute("SELECT COUNT(*) AS cnt FROM articles").fetchone()
        print(f"{_TAG} articles 剩余：{r2['cnt']} 行。", flush=True)

        # 尝试 VACUUM ANALYZE（失败不阻断）
        try:
            conn.autocommit = True
            conn.execute("VACUUM ANALYZE articles")
            print(f"{_TAG} VACUUM ANALYZE 完成。", flush=True)
        except Exception as ve:
            print(f"{_TAG} VACUUM ANALYZE 跳过（{ve}）。", flush=True)

    except Exception as e:
        print(f"{_TAG} 清理失败：{e}", flush=True)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    elapsed = (datetime.now() - start).total_seconds()
    print(f"{_TAG} 完成，耗时 {elapsed:.1f}s。", flush=True)


if __name__ == "__main__":
    run()
