"""
B0 migration: news.db + forecast_tracker.db  →  worldsim-pg
tianji.db 是 0 字节空文件,所有天玑表都在 forecast_tracker.db 内。
时区契约:naive UTC ISO 串追加 "+00:00";已有 TZ 直接使用。synthesis_log / predictions / narrative_* 的 DATETIME 戳均为 UTC 但存为 naive。
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import psycopg

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PG_HOST = "worldsim-pg"
PG_PORT = 5432
PG_DB = "worldsim"
PG_USER = "worldsim_app"
DATA_DIR = "/workspace/data"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_pw() -> str:
    pw = os.environ.get("WORLDSIM_APP_PW")
    if pw:
        return pw
    # Fallback: read from well-known NAS path (only via ops path, not here)
    raise RuntimeError("WORLDSIM_APP_PW env var required")


def norm_ts(val):
    """Naive ISO → append +00:00; TZ-aware ISO → keep; None → None."""
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        # already has +HH:MM or Z?
        if s.endswith("Z") or "+" in s[10:] or s.endswith("+00:00"):
            return s
        # naive ISO → assume UTC
        # handle "YYYY-MM-DD HH:MM:SS[.fff]"
        s = s.replace(" ", "T")
        if "+00:00" not in s and not s.endswith("Z"):
            s = s + "+00:00"
        return s
    return val


def _sqlite_conn(dbfile):
    return sqlite3.connect(os.path.join(DATA_DIR, dbfile))


def connect_pg():
    return psycopg.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=_get_pw(),
    )


# ---------------------------------------------------------------------------
# DDL — explicit per-table CREATE TABLE based on PRAGMA table_info dumps
# ---------------------------------------------------------------------------
DDL = """
-- news schema ------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS news AUTHORIZATION worldsim_app;
GRANT ALL ON SCHEMA news TO worldsim_app;

CREATE TABLE IF NOT EXISTS news.scan_contexts (
    id              BIGSERIAL PRIMARY KEY,
    scan_time       TIMESTAMPTZ,
    vix             DOUBLE PRECISION,
    t10y2y          DOUBLE PRECISION,
    baa10y          DOUBLE PRECISION,
    dff             DOUBLE PRECISION,
    regime          TEXT,
    vix_regime      TEXT,
    data_quality    TEXT
);

CREATE TABLE IF NOT EXISTS news.articles (
    id              BIGSERIAL PRIMARY KEY,
    url             TEXT,
    content_hash    TEXT,
    title           TEXT,
    source          TEXT,
    published_at    TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ,
    country_tag     TEXT,
    ingest_ctx_id   BIGINT,
    pub_ctx_id      BIGINT
);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON news.articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON news.articles (source);
CREATE UNIQUE INDEX IF NOT EXISTS news_uq_articles_hash ON news.articles (content_hash) WHERE content_hash IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS news_uq_articles_url ON news.articles (url) WHERE url IS NOT NULL;

CREATE TABLE IF NOT EXISTS news.article_categories (
    article_id      BIGINT NOT NULL,
    category        TEXT NOT NULL,
    PRIMARY KEY (article_id, category)
);
CREATE INDEX IF NOT EXISTS idx_article_categories_category ON news.article_categories (category);

CREATE TABLE IF NOT EXISTS news.signal_episodes (
    id              BIGSERIAL PRIMARY KEY,
    category        TEXT,
    triggered_at    TIMESTAMPTZ,
    ratio           DOUBLE PRECISION,
    level           TEXT,
    scan_ctx_id     BIGINT
);
CREATE INDEX IF NOT EXISTS idx_signal_episodes_triggered ON news.signal_episodes (triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_episodes_category ON news.signal_episodes (category);

CREATE TABLE IF NOT EXISTS news.episode_articles (
    episode_id      BIGINT NOT NULL,
    article_id      BIGINT NOT NULL,
    PRIMARY KEY (episode_id, article_id)
);

CREATE TABLE IF NOT EXISTS news.signal_outcomes (
    id              BIGSERIAL PRIMARY KEY,
    episode_id      BIGINT,
    check_date      TIMESTAMPTZ,
    check_horizon   TEXT,
    spx_return      DOUBLE PRECISION,
    dgs10_change    DOUBLE PRECISION,
    vix_change      DOUBLE PRECISION,
    usdx_change     DOUBLE PRECISION,
    outcome_regime  TEXT
);

CREATE TABLE IF NOT EXISTS news.synthesis_log (
    id              BIGSERIAL PRIMARY KEY,
    rule_id         TEXT,
    triggered_at    TIMESTAMPTZ,
    scan_ctx_id     BIGINT,
    trigger_summary TEXT,
    hypothesis_text TEXT,
    llm_success     INTEGER,
    ntfy_success    INTEGER,
    suppress_reason TEXT,
    report_excerpt  TEXT,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_synthesis_log_triggered ON news.synthesis_log (triggered_at DESC);

-- forecast schema --------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS forecast AUTHORIZATION worldsim_app;
GRANT ALL ON SCHEMA forecast TO worldsim_app;

CREATE TABLE IF NOT EXISTS forecast.forecasts (
    id                  TEXT PRIMARY KEY,
    created_at          TIMESTAMPTZ,
    scenario            TEXT,
    horizon_months      INTEGER,
    verify_after        TIMESTAMPTZ,
    country             TEXT,
    status              TEXT,
    regime              TEXT,
    stress_signals      INTEGER,
    prob_recession      DOUBLE PRECISION,
    prob_deep_recession DOUBLE PRECISION,
    prob_soft_landing   DOUBLE PRECISION,
    prob_stagflation    DOUBLE PRECISION,
    prob_crisis_vix     DOUBLE PRECISION,
    gdp_p10             DOUBLE PRECISION,
    gdp_p50             DOUBLE PRECISION,
    gdp_p90             DOUBLE PRECISION,
    unrate_p50          DOUBLE PRECISION,
    cpi_yoy_p50         DOUBLE PRECISION,
    input_json          TEXT,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS forecast.actuals (
    period          TEXT PRIMARY KEY,
    actual_regime   TEXT,
    gdp_growth      DOUBLE PRECISION,
    unemployment    DOUBLE PRECISION,
    cpi_yoy         DOUBLE PRECISION,
    labeled_at      TIMESTAMPTZ,
    label_source    TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS forecast.evaluations (
    id                  BIGSERIAL PRIMARY KEY,
    eval_date           TIMESTAMPTZ,
    horizon_months      INTEGER,
    n_samples           INTEGER,
    brier_score         DOUBLE PRECISION,
    brier_skill         DOUBLE PRECISION,
    recession_brier     DOUBLE PRECISION,
    soft_landing_brier  DOUBLE PRECISION,
    notes               TEXT
);

-- tianji schema ----------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS tianji AUTHORIZATION worldsim_app;
GRANT ALL ON SCHEMA tianji TO worldsim_app;

CREATE TABLE IF NOT EXISTS tianji.predictions (
    id                      TEXT PRIMARY KEY,
    created_at              TIMESTAMPTZ,
    due_at                  TIMESTAMPTZ,
    scenario_id             TEXT,
    type                    TEXT,
    prediction_target_type  TEXT,
    content                 TEXT,
    outcome_definition      TEXT,
    target_metric           TEXT,
    target_direction        TEXT,
    target_threshold        DOUBLE PRECISION,
    b_prob                  DOUBLE PRECISION,
    b_sample_count          INTEGER,
    b_max_similarity        DOUBLE PRECISION,
    llm_adj                 DOUBLE PRECISION,
    final_prob              DOUBLE PRECISION,
    prob_low                DOUBLE PRECISION,
    prob_high               DOUBLE PRECISION,
    confidence_tier         TEXT,
    time_horizon            TEXT,
    status                  TEXT,
    outcome_value           DOUBLE PRECISION,
    brier_score             DOUBLE PRECISION,
    brier_skill_score       DOUBLE PRECISION,
    verified_at             TIMESTAMPTZ,
    verified_by             TEXT,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());

CREATE TABLE IF NOT EXISTS tianji.reasoning_trace (
    id                  BIGSERIAL PRIMARY KEY,
    prediction_id       TEXT,
    agent_id            TEXT,
    input_signals       TEXT,
    historical_match    TEXT,
    confidence_basis    TEXT,
    llm_adjustment      DOUBLE PRECISION,
    causal_chains       TEXT,
    reasoning           TEXT,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());

CREATE TABLE IF NOT EXISTS tianji.weight_update_log (
    id                  BIGSERIAL PRIMARY KEY,
    updated_at          TIMESTAMPTZ,
    prediction_id       TEXT,
    signal_name         TEXT,
    target_type         TEXT,
    weight_before       DOUBLE PRECISION,
    weight_after        DOUBLE PRECISION,
    reason              TEXT,
    notes               TEXT,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());

CREATE TABLE IF NOT EXISTS tianji.narrative_chunks (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT,
    source_type         TEXT,
    primary_dimension   TEXT,
    secondary_dimension TEXT,
    timestamp           TIMESTAMPTZ,
    content             TEXT,
    token_count         INTEGER,
    staleness_tau       INTEGER,
    embedding           BYTEA,
    created_at          TIMESTAMPTZ,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_narrative_chunks_dim ON tianji.narrative_chunks (primary_dimension, secondary_dimension);

CREATE TABLE IF NOT EXISTS tianji.narrative_density_flags (
    dimension       TEXT PRIMARY KEY,
    flagged_at      TIMESTAMPTZ,
    z_score         DOUBLE PRECISION,
    consumed        INTEGER,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());
"""

# ---------------------------------------------------------------------------
# Table mapping (sqlite_db, sqlite_table, pg_table, pk_cols, ts_cols)
# ---------------------------------------------------------------------------
TABLES = [
    # news.db → news.*
    ("news.db", "scan_contexts",     "news.scan_contexts",     ["id"], ["scan_time"]),
    ("news.db", "articles",          "news.articles",         ["id"], ["published_at", "ingested_at"]),
    ("news.db", "article_categories","news.article_categories", ["article_id", "category"], []),
    ("news.db", "signal_episodes",   "news.signal_episodes",  ["id"], ["triggered_at"]),
    ("news.db", "episode_articles",  "news.episode_articles", ["episode_id", "article_id"], []),
    ("news.db", "signal_outcomes",   "news.signal_outcomes",  ["id"], ["check_date"]),
    ("news.db", "synthesis_log",     "news.synthesis_log",    ["id"], ["triggered_at"]),

    # forecast_tracker.db → forecast.*
    ("forecast_tracker.db", "forecasts",    "forecast.forecasts",    ["id"], ["created_at", "verify_after"]),
    ("forecast_tracker.db", "actuals",      "forecast.actuals",      ["period"], ["labeled_at"]),
    ("forecast_tracker.db", "evaluations",  "forecast.evaluations",  ["id"], ["eval_date"]),

    # forecast_tracker.db → tianji.*  (NOT tianji.db)
    ("forecast_tracker.db", "predictions",            "tianji.predictions",            ["id"], ["created_at", "due_at", "verified_at"]),
    ("forecast_tracker.db", "reasoning_trace",        "tianji.reasoning_trace",        ["id"], []),
    ("forecast_tracker.db", "weight_update_log",      "tianji.weight_update_log",      ["id"], ["updated_at"]),
    ("forecast_tracker.db", "narrative_chunks",       "tianji.narrative_chunks",       ["id"], ["timestamp", "created_at"]),
    ("forecast_tracker.db", "narrative_density_flags","tianji.narrative_density_flags",["dimension"], ["flagged_at"]),
]

# Columns known to need TZ normalization (TIMESTAMPTZ target)
TS_COLS_BY_TABLE = {pt: tcs for _, _, pt, _, tcs in TABLES}
PK_COLS_BY_TABLE = {pt: pks for _, _, pt, pks, _ in TABLES}
SRC_BY_TABLE     = {pt: (db, tbl) for db, tbl, pt, _, _ in TABLES}

# Columns that hold BLOB (raw binary) — need special handling
BLOB_COLS_BY_TABLE = {
    "tianji.narrative_chunks": ["embedding"],
}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def apply_schema(pg):
    with pg.cursor() as cur:
        cur.execute(DDL)
    pg.commit()
    print("[schema] all DDL applied", flush=True)


def dump_sql(out_path: str):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(DDL, encoding="utf-8")
    print(f"[dump] wrote {out_path}", flush=True)


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------
def backfill(pg, only: list[str] | None = None):
    total = {"ins": 0, "sk": 0}
    for dbfile, sqlt, pgt, pks, tscols in TABLES:
        if only and pgt not in only:
            continue
        pkcols = PK_COLS_BY_TABLE[pgt]
        blobcols = BLOB_COLS_BY_TABLE.get(pgt, [])
        scon = _sqlite_conn(dbfile)
        scur = scon.cursor()
        try:
            # Order matters: get count FIRST so the SELECT * result set below
            # is not clobbered by a second execute().
            n_src = scur.execute(f"SELECT COUNT(*) FROM {sqlt}").fetchone()[0]
            scur.execute(f"SELECT * FROM {sqlt}")
            col_names = [d[0] for d in scur.description]
        except Exception as e:
            print(f"  {pgt}: ERR sqlite open {e}", flush=True)
            scon.close()
            continue

        if n_src == 0:
            print(f"  {pgt}: 0 rows in sqlite (skipped)", flush=True)
            scon.close()
            continue

        ts_set = set(tscols)
        # Build INSERT with proper cast for BYTEA and TIMESTAMPTZ
        placeholders = []
        sql_cols = []
        for c in col_names:
            sql_cols.append(c)
            if c in ts_set:
                placeholders.append("%s::timestamptz")
            else:
                placeholders.append("%s")
        # RETURNING so psycopg3 cursor.rowcount is meaningful.
        # For composite PKs, RETURNING pk1, pk2 (PG doesn't accept RETURNING (pk1,pk2)).
        if len(pkcols) == 1:
            returning = pkcols[0]
        else:
            returning = ", ".join(pkcols)
        ins_sql = (
            f"INSERT INTO {pgt} ({','.join(sql_cols)}) "
            f"VALUES ({','.join(placeholders)}) "
            f"ON CONFLICT ({','.join(pkcols)}) DO NOTHING "
            f"RETURNING {returning}"
        )

        ins_n = sk_n = 0
        with pg.cursor() as pcur:
            for ix, row in enumerate(scur):
                vals = []
                for c, v in zip(col_names, row):
                    if c in ts_set:
                        vals.append(norm_ts(v))
                    elif c in blobcols:
                        vals.append(psycopg.Binary(v) if v is not None else None)
                    else:
                        vals.append(v)
                try:
                    pcur.execute(ins_sql, vals)
                    rc = pcur.rowcount
                    if rc == 1:
                        ins_n += 1
                    else:
                        sk_n += 1
                except Exception as e:
                    print(f"  {pgt}: ERR row #{ix} {row[:3]}...: {e}", flush=True)
                    raise
        pg.commit()
        total["ins"] += ins_n
        total["sk"]  += sk_n
        print(f"  {pgt}: inserted {ins_n} / {n_src} (skipped {sk_n})", flush=True)
        scon.close()
    print(f"[backfill] DONE total inserted={total['ins']} skipped={total['sk']}", flush=True)


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
def verify(pg):
    print("[verify] row counts in PG vs sqlite", flush=True)
    with pg.cursor() as cur:
        for _, _, pgt, _, _ in TABLES:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {pgt}")
                pg_cnt = cur.fetchone()[0]
            except Exception as e:
                print(f"  {pgt}: ERR {e}", flush=True)
                continue
            db, tbl = SRC_BY_TABLE[pgt]
            scon = _sqlite_conn(db)
            sq_cnt = scon.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            scon.close()
            ok = "OK" if pg_cnt == sq_cnt else "MISMATCH"
            print(f"  {pgt}: pg={pg_cnt} sqlite={sq_cnt} {ok}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-schema", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--dump-sql", metavar="PATH")
    ap.add_argument("--only", nargs="+", metavar="PG_TABLE", help="e.g. tianji.predictions")
    ap.add_argument("--all", action="store_true", help="apply-schema + backfill + verify")
    args = ap.parse_args()

    if args.dump_sql:
        dump_sql(args.dump_sql)
    if args.apply_schema or args.all:
        with connect_pg() as pg:
            apply_schema(pg)
    if args.backfill or args.all:
        only = args.only
        with connect_pg() as pg:
            backfill(pg, only=only)
    if args.verify or args.all:
        with connect_pg() as pg:
            verify(pg)


if __name__ == "__main__":
    main()
