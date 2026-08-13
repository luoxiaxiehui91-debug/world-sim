-- D0 schema: chroma → pgvector 迁移
-- 落码依据: docs/discussion/d0-chroma-to-pgvector-round2.md
-- 实测: collection=macro_kb, 4156 emb, dim=1024 (bge-m3), cosine, HNSW
-- pgvector v0.8.2 (trusted 扩展); worldsim_app 对自有 rag schema 有 CREATE 即可安装
-- 若 CREATE EXTENSION 报权限不足, 改由 worldsim_admin(super) 执行本文件.

-- Step 0: 启用 pgvector（D0 是 worldsim-pg 首次真正用 vector 扩展）
CREATE EXTENSION IF NOT EXISTS vector;

-- rag schema（沿用 B0 的 AUTHORIZATION + GRANT 模式）
CREATE SCHEMA IF NOT EXISTS rag AUTHORIZATION worldsim_app;
GRANT ALL ON SCHEMA rag TO worldsim_app;
GRANT USAGE ON SCHEMA rag TO worldsim_ro;

CREATE TABLE IF NOT EXISTS rag.embeddings (
    collection_name text        NOT NULL,
    id              text        NOT NULL,
    document        text,
    metadata        jsonb,
    embedding       vector(1024),
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_name, id)
);

-- HNSW cosine 索引（chroma 原即 HNSW+cosine, 零重训; pgvector v0.8.2 支持）
CREATE INDEX IF NOT EXISTS rag_embeddings_embedding_idx
    ON rag.embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- collection 过滤加速（单表多 collection 场景）
CREATE INDEX IF NOT EXISTS rag_embeddings_collection_idx
    ON rag.embeddings (collection_name);

GRANT SELECT, INSERT, UPDATE, DELETE ON rag.embeddings TO worldsim_app;
GRANT SELECT ON rag.embeddings TO worldsim_ro;
