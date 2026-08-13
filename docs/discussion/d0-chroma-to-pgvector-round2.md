# D0（chroma → pgvector）落码设计 · Round 2

> **作者**：主理人（基于 round1 三路收敛 + 实测勘误）
> **日期**：2026-08-13
> **状态**：DRAFT · round2 · 待 user 终审 → 落码
> **前置**：round1 已收敛（见 `d0-chroma-to-pgvector-round1.md` §4）；本文件是 round1 的落码级细化。

---

## 0. 前置实测结论（round1 → round2 之间已查证，去伪存真）

| 项 | 实测 | 影响 |
|----|------|------|
| pgvector 是否装 | `installed=NO`，`available=vector` v**0.8.2**（trusted），PG **16.14** | **Step 0 必须 `CREATE EXTENSION vector`**；v0.8.2 同时支持 hnsw+ivfflat，D-D1 成立 |
| tianji.embedding 类型 | `bytea`（非 vector）| 印证 B0 未启用 vector 扩展，C7 理论成立 → D0 是 worldsim-pg 首次真正用 vector |
| worldsim_app 权限 | 非 superuser（`rolcreaterole=f`）| vector 为 trusted 扩展，worldsim_app 对自身 `rag` schema 有 CREATE 即可安装；若环境判定非 trusted，改 `worldsim_admin`(super) 执行 |
| 安全窗口 | scheduler 每月 1 日 09:05 跑 `rebuild_rag_index()` | **今天 8/13，9/1 前必须 cutover 完**，别跨月触发两边不一致 |

---

## 1. 决策收敛表（round1 §4.1，落码依据）

| # | 决策 | 采用 | 落码含义 |
|---|------|------|----------|
| D-D1 | 索引 HNSW | ✓ | `USING hnsw (embedding vector_cosine_ops)` WITH (m=16, ef_construction=64) |
| D-D2 | 距离族 vector_cosine_ops | ✓ | 查询用 `embedding <=> $1`，阈值 SCORE_THRESHOLD 不变；**非逐位一致，验收用 top-5 重叠率** |
| D-D3 | 单表 rag.embeddings | ✓ | `rag` schema 单表，PK(collection_name, id) |
| D-D4 | 不双写 | ✓ | 一次性 backfill + RAG_BACKEND 切换，无实时双写 |
| D-D5+D-D7 | 回滚三件套一体 | ✓ | chroma.sqlite3(只读) + chromadb 依赖 + RAG_BACKEND 双读，观察 1 周后同删 |
| D-D6 | TEXT(128) 保 c{N} | ✓ | id 列 TEXT，不外键消费 |
| D-D8 | v1 不上全文 | ✓ | document 存 TEXT，全文检索留 v2（tsvector/pg_trgm） |

---

## 2. DDL：`sql/04_d0_schema.sql`

```sql
-- Step 0: 启用 pgvector（trusted 扩展，worldsim_app 对自有 schema 有 CREATE 即可；
--         若报权限不足，改由 worldsim_admin 执行此句）
CREATE EXTENSION IF NOT EXISTS vector;

-- rag schema（沿用 B0 的 AUTHORIZATION + GRANT 模式）
CREATE SCHEMA IF NOT EXISTS rag AUTHORIZATION worldsim_app;
GRANT ALL ON SCHEMA rag TO worldsim_app;
GRANT USAGE ON SCHEMA rag TO worldsim_ro;

CREATE TABLE IF NOT EXISTS rag.embeddings (
    collection_name text     NOT NULL,
    id              text     NOT NULL,
    document        text,
    metadata        jsonb,
    embedding       vector(1024),
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_name, id)
);

-- HNSW cosine 索引（chroma 原即 HNSW+cosine，零重训）
CREATE INDEX IF NOT EXISTS rag_embeddings_embedding_idx
    ON rag.embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- collection 过滤加速（单表多 collection 场景）
CREATE INDEX IF NOT EXISTS rag_embeddings_collection_idx
    ON rag.embeddings (collection_name);

GRANT SELECT, INSERT, UPDATE, DELETE ON rag.embeddings TO worldsim_app;
GRANT SELECT ON rag.embeddings TO worldsim_ro;
```

**注意**：`vector(1024)` 维度硬锁，与实测 bge-m3 1024-dim 对齐（非 STATUS.md 旧记 1536）。

---

## 3. 迁移脚本：`核心代码/d0_migrate_rag.py`（自包含，mirror b0_migrate.py）

复用 B0 的 psycopg3 + 子命令结构（`--apply-schema / --backfill / --verify / --dump-sql`）。

```python
# 关键逻辑（伪代码，落码时补完整 + 类型标注 + 日志）
def backfill(chroma_dir, collection, pg_dsn):
    import chromadb, psycopg
    client = chromadb.PersistentClient(path=chroma_dir)
    col = client.get_collection(collection)
    total = col.count()
    data = col.get(include=['embeddings', 'documents', 'metadatas'])
    ids, embs, docs, metas = data['ids'], data['embeddings'], data['documents'], data['metadatas']
    ins = sk = 0
    with psycopg.connect(pg_dsn) as pg:
        with pg.cursor() as cur:
            for i in range(total):
                cur.execute(
                    """INSERT INTO rag.embeddings (collection_name, id, document, metadata, embedding)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (collection_name, id)
                       DO UPDATE SET document=EXCLUDED.document,
                                     metadata=EXCLUDED.metadata,
                                     embedding=EXCLUDED.embedding,
                                     created_at=now()""",
                    (collection, ids[i], docs[i], psycopg.Json(metas[i]), embs[i]))
                if cur.rowcount == 1: ins += 1
                else: sk += 1
    return ins, sk
```

**C6 幂等反噬修复**：用 `ON CONFLICT DO UPDATE`（覆盖），**不照抄 B0 的 `DO NOTHING`**——RAG 重建是删旧建新，KB 改动后同 id 内容已变，`DO NOTHING` 会静默保留旧向量。

**verify 子命令**（C5 验收闸门）：
1. `SELECT count(*) FROM rag.embeddings WHERE collection_name='macro_kb'` == 4156
2. 取 N=20 条随机 chroma 向量作 query，分别查 chroma 与 pg，比对 **top-5 id 集合重叠率 ≥ 0.95**（非 count 等价）
3. 距离值口径一致性抽查（cosine，1-cos）

**连接**：优先读 `WORLDSIM_PG_DSN` env；容器内默认 `worldsim-pg:5432`，NAS 侧回退 `127.0.0.1:5434`。密码走 `WORLDSIM_APP_PW`。

---

## 4. `rag_engine.py` 重构（RAG_BACKEND 双读 + 失败计数）

```python
# 新增 env 开关，默认 pgvector
RAG_BACKEND = os.getenv('RAG_BACKEND', 'pgvector').lower()

def _get_pg_conn():
    return psycopg.connect(os.getenv('WORLDSIM_PG_DSN'),
                            options='-c search_path=rag,public')

def rag_query_vec(query_vec, n_results=5, chroma_dir=None):
    if RAG_BACKEND == 'chroma':
        return _rag_query_chroma(query_vec, n_results, chroma_dir)  # 旧路径，观察期 fallback
    try:
        with _get_pg_conn() as pg:
            with pg.cursor() as cur:
                cur.execute(
                    """SELECT id, document, metadata, embedding <=> %s AS dist
                       FROM rag.embeddings
                       WHERE collection_name = %s
                       ORDER BY embedding <=> %s, id
                       LIMIT %s""",
                    (query_vec, COLLECTION_NAME, query_vec, n_results))
                rows = cur.fetchall()
        # 阈值过滤（SCORE_THRESHOLD 不变）
        return [_fmt(r) for r in rows if r.dist <= SCORE_THRESHOLD]
    except Exception as e:
        metrics.inc('rag_pg_fail')          # C9 静默降级致盲修复：加失败计数
        logger.error(f'rag pg query failed, fallback TF-IDF: {e}')
        return []                            # 仍转 TF-IDF，但已记录
```

- 签名向后兼容：`chroma_dir` 参数保留（pg 路径忽略，chroma fallback 用）
- 返回值格式 `List["【文件名】\n片段"]` 不变（D1 行为不变性）
- **C9**：异常不再静默 `return []`，先 `metrics.inc` + `logger.error` 再 fallback

---

## 5. `build_rag_index.py` 重构（影子 swap，修 delete-then-build bug）

现行 `build_index` 先 `delete_collection` 再 `add`——embedding API 中途失败 = 旧毁新残。PG 事务版天然原子：

```python
def build_index(kb_dir, chroma_dir=None):
    chunks = _collect_chunks(kb_dir)              # 读 .md → 切块
    embs = _embed(chunks)                          # SiliconFlow bge-m3
    if RAG_BACKEND == 'chroma':
        _build_chroma(chunks, embs, chroma_dir)    # 旧路径（观察期）
    else:
        with _get_pg_conn() as pg:                  # 原子重建：TRUNCATE+INSERT 同事务
            with pg.transaction():
                with pg.cursor() as cur:
                    cur.execute("TRUNCATE rag.embeddings WHERE collection_name = %s", (COLLECTION_NAME,))
                    for c, e in zip(chunks, embs):
                        cur.execute("INSERT INTO rag.embeddings (collection_name,id,document,metadata,embedding) VALUES (%s,%s,%s,%s,%s)",
                                    (COLLECTION_NAME, c['id'], c['text'], psycopg.Json(c['meta']), e))
```

- **C6 修复**：`TRUNCATE + INSERT` 在单事务内 = 原子，杜绝「旧毁新残」
- 重建语义保持「清空 + 重建」（D4），但安全

---

## 6. 回滚三件套（C4，合并 D-D5+D-D7）

| 组件 | 观察期（cutover 后 1 周）| 1 周后 |
|------|--------------------------|--------|
| `chroma.sqlite3` | 保留，**chmod 444 只读**防误写 | 删除 |
| `chromadb` 依赖 | 保留（rag_engine/build_index chroma 分支仍在）| 从 requirements 移除 + 镜像重建 |
| `RAG_BACKEND` 开关 + chroma 读分支 | 保留（`=chroma` 可回滚）| 删开关 + 删 chroma 分支代码 |

**铁律**：删文件当天即清依赖 + 开关代码，不留半截空开关（D-D7 单独不构成回滚）。

---

## 7. 验收闸门（C5，主理人容器内独立验收）

1. `SELECT count(*) FROM rag.embeddings WHERE collection_name='macro_kb'` == **4156**
2. top-5 集合重叠率（pg vs chroma，N=20 抽样）**≥ 0.95**
3. `rag_query_vec` 返回格式 + `SCORE_THRESHOLD` 行为不变
4. `RAG_BACKEND=chroma` 仍可回滚（fallback 路径实跑通过）
5. scheduler.py / contracts.py / fetcher_base.py **未改**
6. chroma.sqlite3 原样保留（只读），pg 实测查询延迟 < chroma（4k 行无压力）

---

## 8. 迁移序列（9/1 前窗口）

| 步 | 动作 | 命令/文件 |
|----|------|-----------|
| 0 | 启用 vector 扩展 + 建 rag schema | `04_d0_schema.sql`（worldsim_app 或 admin）|
| 1 | 迁 4156 条 | `d0_migrate_rag.py --backfill` |
| 2 | 切读路径 | 改 `rag_engine.py` / `build_rag_index.py`（RAG_BACKEND 默认 pgvector）|
| 3 | 容器热挂载即效（rag_engine 在 /app，不需 restart）| — |
| 4 | 验收闸门 | `d0_migrate_rag.py --verify` + 手动 gate 4/5 |
| 5 | 观察 1 周（chroma 只读）| chmod 444 |
| 6 | 9/1 前 cutover；1 周后删三件套 | 见 §6 |

---

## 9. 风险登记（round1 §4.3 闭环）

- **C6 幂等反噬** → `DO UPDATE` 覆盖，非 `DO NOTHING`
- **C7 pgvector 未装** → Step 0 `CREATE EXTENSION vector`（已确认 v0.8.2 available）
- **C8 安全窗口** → 9/1 前 cutover
- **C9 静默降级致盲** → `metrics.inc('rag_pg_fail')` + `logger.error`
- **C10 c{N} 非稳定键** → 下游不得当稳定 id 依赖（保留 TEXT 无害）

---

## 10. 落码文件清单

| 文件 | 动作 |
|------|------|
| `sql/04_d0_schema.sql` | 新增 |
| `核心代码/d0_migrate_rag.py` | 新增（自包含 apply/backfill/verify/dump）|
| `核心代码/rag_engine.py` | 改（RAG_BACKEND 双读 + 失败计数）|
| `核心代码/build_rag_index.py` | 改（TRUNCATE+INSERT 原子重建）|
| `docs/d0-ops.md` | 新增（mirror b0 模式，非 b0-ops.md）|
| `docs/discussion/d0-chroma-to-pgvector-round1.md` | 设计讨论（已收敛）|
| `docs/discussion/d0-chroma-to-pgvector-round2.md` | 本文件 |

---

## 11. 未决 / 待 user 终审

- [ ] Step 0 用 worldsim_app 还是 worldsim_admin 装扩展（取决于环境 trusted 判定，已确认 v0.8.2 trusted，worldsim_app 可装）
- [ ] 观察期 1 周是否够（建议保留到下次 scheduler 月度重建 9/1 后观察无异常再删）
- [ ] 是否连带回写 STATUS.md 的 `vector(1536)`/`ivfflat` 旧记（建议落码 commit 时一并修）
