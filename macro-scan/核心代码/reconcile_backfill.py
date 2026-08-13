import os, sys, sqlite3, psycopg

try:
    from optim_config import DATA_DIR
except Exception:
    DATA_DIR = "/workspace/data"

DRY = "--dry-run" in sys.argv
SQLITE = os.path.join(DATA_DIR, "news.db")
PG = dict(host="worldsim-pg", port=5432, dbname="worldsim", user="worldsim_app",
          password=os.environ.get("WORLDSIM_APP_PW", ""))

# (pg_table, sqlite_table, pk_predicate, expected_missing)
TABLES = [
    ("news.scan_contexts",   "scan_contexts",   "id = 399",                       1),
    ("news.signal_episodes", "signal_episodes", "id BETWEEN 1989 AND 1995",       7),
    ("news.articles",        "articles",        "id BETWEEN 32201 AND 32293",    93),
    ("news.article_categories", "article_categories", "article_id IN (32228, 32246)", 2),
    ("news.episode_articles", "episode_articles", "episode_id BETWEEN 1989 AND 1995", 21),
]

def main():
    sconn = sqlite3.connect(SQLITE)
    sconn.row_factory = sqlite3.Row
    pconn = psycopg.connect(**PG)
    total = 0
    for pg_tbl, sq_tbl, pred, exp in TABLES:
        cols = [r["name"] for r in sconn.execute(f"PRAGMA table_info({sq_tbl})")]
        rows = sconn.execute(f"SELECT * FROM {sq_tbl} WHERE {pred}").fetchall()
        print(f"[{sq_tbl}] src={len(rows)} expected={exp} cols={len(cols)}")
        if len(rows) != exp:
            print(f"  WARN src count {len(rows)} != expected {exp}")
        if DRY:
            continue
        with pconn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s",
                (pg_tbl.split('.')[0], pg_tbl.split('.')[1]))
            pg_cols = {r[0] for r in cur.fetchall()}
            missing = [c for c in cols if c not in pg_cols]
            if missing:
                raise SystemExit(f"PG {pg_tbl} missing cols {missing}")
            col_list = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))
            inserted = 0
            for row in rows:
                cur.execute(
                    f"INSERT INTO {pg_tbl} ({col_list}) VALUES ({placeholders}) "
                    f"ON CONFLICT DO NOTHING",
                    tuple(row[c] for c in cols))
                inserted += cur.rowcount
            pconn.commit()
            print(f"  INSERTED {inserted} (expected {exp})")
            total += inserted
            if inserted != exp:
                print(f"  WARN inserted {inserted} != expected {exp}")
    print("DONE total_inserted=", total)

if __name__ == "__main__":
    main()
