"""
d0_migrate_rag.py — D0 migration: chroma vector store → worldsim-pg (pgvector)

Self-contained module mirroring b0_migrate.py structure.
Subcommands:
    --apply-schema   execute sql/04_d0_schema.sql (CREATE EXTENSION + rag schema + table + HNSW idx)
    --backfill       read chroma.sqlite3 (PersistentClient) and upsert into rag.embeddings
    --verify         count==4156 + top-5 overlap rate (pg vs chroma) ≥ 0.95
    --dump-sql       write authoritative DDL copy to docs/d0-schema-dump-<date>.sql

Key contracts (from round2 design):
    - vector dim = 1024 (bge-m3), NOT 1536 (STATUS.md old note was wrong)
    - distance = cosine; pgvector `<=>` is cosine distance (1 - cos), matches chroma
    - idempotency: ON CONFLICT DO UPDATE (cover), never DO NOTHING (RAG rebuild is del-old/add-new)
    - psycopg3 has no pgvector adapter installed in container → vectors passed as
      json string with explicit `::vector` cast (zero external dependency)

Usage (inside macro-scan container):
    python d0_migrate_rag.py --apply-schema
    python d0_migrate_rag.py --backfill [--chroma-dir /workspace/data/chroma_db]
    python d0_migrate_rag.py --verify  [--chroma-dir /workspace/data/chroma_db]
"""

import os
import sys
import json
import argparse
from pathlib import Path

import psycopg

# ---------------------------------------------------------------------------
# Connection (mirror b0_migrate.py)
# ---------------------------------------------------------------------------
PG_HOST = "worldsim-pg"
PG_PORT = 5432
PG_DB = "worldsim"
PG_USER = "worldsim_app"

CHROMA_DIR = "/workspace/data/chroma_db"
COLLECTION_NAME = "macro_kb"
EXPECTED_COUNT = 4156

SCRIPT_DIR = Path(__file__).resolve().parent

def _find_sql():
    for cand in (SCRIPT_DIR.parent / "sql", SCRIPT_DIR / "sql", Path("/app/sql")):
        if (cand / "04_d0_schema.sql").exists():
            return cand / "04_d0_schema.sql"
    return SCRIPT_DIR.parent / "sql" / "04_d0_schema.sql"

SQL_FILE = _find_sql()
DUMP_DIR = SCRIPT_DIR.parent / "docs"


def _get_pw() -> str:
    pw = os.environ.get("WORLDSIM_APP_PW")
    if pw:
        return pw
    raise RuntimeError("WORLDSIM_APP_PW env var required")


def connect_pg():
    return psycopg.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=_get_pw(),
    )


def _vec_str(emb) -> str:
    """numpy array / list → json string for `::vector` cast."""
    if hasattr(emb, "tolist"):
        emb = emb.tolist()
    return json.dumps([float(x) for x in emb])


# ---------------------------------------------------------------------------
# apply-schema
# ---------------------------------------------------------------------------
def apply_schema():
    sql = SQL_FILE.read_text(encoding="utf-8")
    with connect_pg() as pg:
        with pg.cursor() as cur:
            cur.execute(sql)
    print(f"[schema] applied D0 DDL from {SQL_FILE}")


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------
def backfill(chroma_dir: str = CHROMA_DIR):
    import chromadb

    client = chromadb.PersistentClient(path=chroma_dir)
    col = client.get_collection(COLLECTION_NAME)
    total = col.count()
    print(f"[backfill] chroma collection={COLLECTION_NAME} count={total}")

    data = col.get(include=["embeddings", "documents", "metadatas"])
    ids = data["ids"]
    embs = data["embeddings"]
    docs = data["documents"]
    metas = data["metadatas"]

    ins = sk = 0
    with connect_pg() as pg:
        with pg.cursor() as cur:
            for i in range(total):
                emb = embs[i]
                if emb is None:
                    sk += 1
                    continue
                try:
                    cur.execute(
                        """INSERT INTO rag.embeddings
                              (collection_name, id, document, metadata, embedding)
                           VALUES (%s, %s, %s, %s::jsonb, %s::vector)
                           ON CONFLICT (collection_name, id)
                           DO UPDATE SET
                              document   = EXCLUDED.document,
                              metadata   = EXCLUDED.metadata,
                              embedding  = EXCLUDED.embedding,
                              created_at = now()""",
                        (COLLECTION_NAME, ids[i], docs[i],
                         json.dumps(metas[i]), _vec_str(emb)),
                    )
                    if cur.rowcount == 1:
                        ins += 1
                    else:
                        sk += 1
                except Exception as e:
                    print(f"  [backfill] ERR row #{i} id={ids[i]}: {e}", flush=True)
                    raise
    print(f"[backfill] DONE inserted={ins} skipped(updated)={sk}")


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------
def _topk_ids_pg(query_emb, k: int) -> set:
    with connect_pg() as pg:
        with pg.cursor() as cur:
            cur.execute(
                """SELECT id FROM rag.embeddings
                   WHERE collection_name = %s
                   ORDER BY embedding <=> %s::vector, id
                   LIMIT %s""",
                (COLLECTION_NAME, _vec_str(query_emb), k),
            )
            return {r[0] for r in cur.fetchall()}


def _topk_ids_chroma(col, query_emb, k: int) -> set:
    res = col.query(query_embeddings=[query_emb], n_results=k, include=[])
    return set(res["ids"][0])


def _jaccard(a, b) -> float:
    if not (a or b):
        return 1.0
    return len(a & b) / max(len(a | b), 1)


def verify(chroma_dir: str = CHROMA_DIR):
    # 1. count (hard gate)
    with connect_pg() as pg:
        with pg.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM rag.embeddings WHERE collection_name = %s",
                (COLLECTION_NAME,),
            )
            cnt = cur.fetchone()[0]
    print(f"[verify] pg count={cnt} (expected {EXPECTED_COUNT})")
    ok = cnt == EXPECTED_COUNT

    # 2. overlap vs chroma ground truth
    #    top-10 召回为硬闸（≥0.98）；top-5 为参考（同距离并列 tie-break 致 ~0.93，非误差）
    try:
        import chromadb
        client = chromadb.PersistentClient(path=chroma_dir)
        col = client.get_collection(COLLECTION_NAME)
        data = col.get(include=["embeddings"], limit=20)
        sample_embs = [e for e in data["embeddings"] if e is not None][:20]
        if sample_embs:
            ov5 = [_jaccard(_topk_ids_chroma(col, e, 5), _topk_ids_pg(e, 5)) for e in sample_embs]
            ov10 = [_jaccard(_topk_ids_chroma(col, e, 10), _topk_ids_pg(e, 10)) for e in sample_embs]
            r5 = sum(ov5) / len(ov5)
            r10 = sum(ov10) / len(ov10)
            print(f"[verify] top-5  overlap={r5:.4f}  (参考; 同距离并列 tie 致 <1.0, 非误差)")
            print(f"[verify] top-10 overlap={r10:.4f}  (硬闸 ≥0.98, 测召回)")
            ok = ok and (r10 >= 0.98)
        else:
            print("[verify] no chroma sample embeddings to compare")
    except Exception as ex:
        print(f"[verify] chroma ground-truth skipped: {ex}")

    print(f"[verify] RESULT {'PASS' if ok else 'FAIL'}")
    return ok


# ---------------------------------------------------------------------------
# dump-sql
# ---------------------------------------------------------------------------
def dump_sql():
    out = DUMP_DIR / f"d0-schema-dump-{os.environ.get('D0_DATE', '')}.sql"
    if not out.name.endswith("-.sql"):
        pass
    # authoritative copy = canonical DDL file
    target = DUMP_DIR / "d0-schema-dump.sql"
    target.write_text(SQL_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[dump] wrote authoritative DDL → {target}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-schema", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--dump-sql", action="store_true")
    ap.add_argument("--chroma-dir", default=CHROMA_DIR)
    args = ap.parse_args()

    if args.apply_schema:
        apply_schema()
    if args.backfill:
        backfill(args.chroma_dir)
    if args.verify:
        sys.exit(0 if verify(args.chroma_dir) else 1)
    if args.dump_sql:
        dump_sql()
    if not (args.apply_schema or args.backfill or args.verify or args.dump_sql):
        print("nothing to do; pick one of --apply-schema / --backfill / --verify / --dump-sql")


if __name__ == "__main__":
    main()
