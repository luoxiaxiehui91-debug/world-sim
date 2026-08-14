"""
reconcile_synthesis.py — E0-C/P3: synthesis_log 对账（SQLite → PG 补齐缺口）

背景：PG news.synthesis_log 仅 b0_migrate 静态迁入（pg_write_collection 双写不含该表），
运行时写入只落 SQLite → PG 持续落后（08-13 实测差 25 行）。P2 读路径已切 PG，须先补平。

用法：python reconcile_synthesis.py [--dry-run]
容器内跑（/workspace/data/news.db + worldsim-pg + WORLDSIM_APP_PW）。
"""
import argparse
import os
import sqlite3
import sys

import psycopg

DATA = os.environ.get("DATA_DIR", "/workspace/data")
PG_HOST = "worldsim-pg"
PG_PORT = 5432
PG_DB = "worldsim"
PG_USER = "worldsim_app"


def get_pg():
    return psycopg.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=os.environ["WORLDSIM_APP_PW"],
        options="-c search_path=news,forecast,tianji,public",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    _sq_path = os.path.join(DATA, "news.db")
    if not os.path.exists(_sq_path):
        raise FileNotFoundError("news.db 已退役（P6 删库 08-14）: 对账请基于 worldsim-pg")
    sq = sqlite3.connect(f"file:{_sq_path}?mode=ro", uri=True)
    sq.row_factory = sqlite3.Row
    rows = sq.execute(
        "SELECT id, rule_id, triggered_at, scan_ctx_id, trigger_summary, "
        "hypothesis_text, llm_success, ntfy_success, suppress_reason, report_excerpt "
        "FROM synthesis_log ORDER BY id"
    ).fetchall()
    sq.close()

    conn = get_pg()
    with conn:
        pg_ids = {r[0] for r in conn.execute("SELECT id FROM news.synthesis_log").fetchall()}
    conn.close()

    missing = [dict(r) for r in rows if r["id"] not in pg_ids]
    extra_pg = pg_ids - {r["id"] for r in rows}
    print("SQLite={} PG={} missing={} extra_pg={}".format(len(rows), len(pg_ids), len(missing), len(extra_pg)))
    if extra_pg:
        print("  WARN PG 侧多出 id:", sorted(extra_pg)[:10])
    if not missing:
        print("无缺口，对账完成")
        return 0

    print("待补行（SQLite 有 PG 无）:")
    for m in missing[:10]:
        print("  id={} rule={} ts={} suppress={}".format(m["id"], m["rule_id"], m["triggered_at"], m["suppress_reason"]))
    if len(missing) > 10:
        print("  ... 共 {} 行".format(len(missing)))

    if args.dry_run:
        print("[dry-run] 未写入")
        return 0

    sql = (
        "INSERT INTO news.synthesis_log "
        "(id, rule_id, triggered_at, scan_ctx_id, trigger_summary, "
        " hypothesis_text, llm_success, ntfy_success, suppress_reason, "
        " report_excerpt, pg_synced_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) "
        "ON CONFLICT DO NOTHING"
    )
    conn = get_pg()
    with conn:
        cur = conn.cursor()
        for m in missing:
            cur.execute(sql, (m["id"], m["rule_id"], m["triggered_at"], m["scan_ctx_id"],
                              m["trigger_summary"], m["hypothesis_text"], m["llm_success"],
                              m["ntfy_success"], m["suppress_reason"], m["report_excerpt"]))
    conn.close()

    # 验证：双向差集
    conn2 = get_pg()
    with conn2:
        pg2 = {r[0] for r in conn2.execute("SELECT id FROM news.synthesis_log").fetchall()}
    conn2.close()
    only_sqlite = {r["id"] for r in rows} - pg2
    only_pg = pg2 - {r["id"] for r in rows}
    print("INSERTED {} → 验证 PG={} only_sqlite={} only_pg={}".format(
        len(missing), len(pg2), len(only_sqlite), len(only_pg)))
    print("VERDICT", "PASS" if not only_sqlite and not only_pg else "FAIL")
    return 0 if not only_sqlite and not only_pg else 1


if __name__ == "__main__":
    sys.exit(main())
