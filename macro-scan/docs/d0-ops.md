# D0 运维手册 · chroma → pgvector 迁移

> 落码依据：`docs/discussion/d0-chroma-to-pgvector-round2.md`
> 实测：collection=macro_kb, 4156 emb, dim=1024 (bge-m3), cosine, HNSW
> 状态：已落地（容器内部实测验收 PASS）
> **chroma 已于 2026-08-13 E0-B 退役**：rag_engine.py / build_rag_index.py 删除全部 chroma 分支 + RAG_BACKEND 开关；requirements.txt 移除 chromadb；chroma.sqlite3 备份至 `data/chroma_db_backup_2026-08-13.sqlite3` 后删除（36MB）。读路径现统一只读 worldsim-pg。

## 1. 架构（E0-B 后：pgvector 单后端）

```
worldsim-pg.rag.embeddings (vector(1024), HNSW cosine)
        ▲
        │  rag_engine.py 唯一读路径（pgvector，无 chroma 回滚）
        └─ build_rag_index.py 原子重建（TRUNCATE + INSERT 同事务）
```

- pgvector 扩展：v0.8.2，**需 superuser 创建**（worldsim_app 非超级用户，容器内 `worldsim_admin` 本地免密可建）
- rag schema：`AUTHORIZATION worldsim_app` + GRANT（沿用 B0 模式）
- RAG 向量检索：pgvector `<=>` cosine 距离 + `ORDER BY ... , id` 稳定排序；坏连接 `_RAG_FAIL_COUNT` 计数后转 TF-IDF（不再静默降级）

## 2. 部署步骤（已执行，可重跑）

```bash
# Step 0: 装扩展（worldsim_admin 本地免密）
docker exec worldsim-pg psql -U worldsim_admin -d worldsim -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Step 1: 建 schema + 表 + HNSW 索引
python d0_migrate_rag.py --apply-schema        # 需 WORLDSIM_APP_PW

# Step 2: 迁 4156 条（DO UPDATE 幂等，可重跑）
python d0_migrate_rag.py --backfill

# Step 4: 验收闸门
python d0_migrate_rag.py --verify              # count=4156 + top-10 召回≥0.98 → PASS
```

## 3. chroma 退役记录（E0-B，2026-08-13）

原「回滚三件套」已在 E0-B 一体删除（用户选择不等 9/1 观察期）：

| 组件 | 状态 |
|------|------|
| `chroma.sqlite3` | **已删**（备份 `data/chroma_db_backup_2026-08-13.sqlite3`，36MB）|
| `chromadb` 依赖 | **已移除**（requirements.txt 删除 `chromadb>=1.0.0`）|
| `RAG_BACKEND` 开关 + chroma 读分支 | **已删**（rag_engine.py / build_rag_index.py 不再含任何 chroma 代码）|

> 如需从 pg 回滚到 chroma：不可行（chroma 文件已删、依赖已卸）。pgvector 为唯一权威向量库。
> 历史回滚设计见 `docs/discussion/d0-chroma-to-pgvector-round1.md` §O4（仅作档案参考）。

## 4. 演练 0 干扰验证（已做，D0 时）

- 主理人容器内独立验收 PASS：count=4156、top-10 重叠率 1.0、top-5 仅同距离 tie 噪声（0.90~0.93，非误差）、RAG_BACKEND=chroma 回滚路径当时实跑通过、`_rag_query_pg` 坏连接失败计数 +1 不再静默降级。
- scheduler.py / contracts.py / fetcher_base.py 未改（D0 只动 rag 检索层）。
- chroma.sqlite3 已于 E0-B 备份后删除。

## 5. 已知约束

- 容器未装 `pgvector` python 包：向量参数用手拼 `'[...]'` 字符串 + `::vector` 显式 cast（零外部依赖）；metadata 用 `json.dumps` + `::jsonb`。
- cosine 非逐位一致：top-5 集合因同距离并列可能重排，验收以 top-10 召回为准。
- 重建脚本 `build_rag_index.py` 已改 `TRUNCATE+INSERT` 单事务原子（修 chroma 旧毁新残 bug）；E0-B 后验证改直查 `rag.embeddings` count。
- 月度 scheduler `rebuild_rag_index()` 现走 pgvector 单后端（无 chroma 依赖）。

## 6. 重建 / 验证命令速查

```bash
# 重建 pg 向量索引（原子）
docker exec -e WORLDSIM_APP_PW=... macro-scan-macro-scan-1 python /app/build_rag_index.py

# 验证向量块数
docker exec worldsim-pg psql -U worldsim_app -d worldsim -c "SELECT COUNT(*) FROM rag.embeddings WHERE collection_name='macro_kb';"
```
