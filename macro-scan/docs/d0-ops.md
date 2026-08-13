# D0 运维手册 · chroma → pgvector 迁移

> 落码依据：`docs/discussion/d0-chroma-to-pgvector-round2.md`
> 实测：collection=macro_kb, 4156 emb, dim=1024 (bge-m3), cosine, HNSW
> 状态：已落地（容器内部实测验收 PASS）

## 1. 架构

```
chroma (python 库 + sqlite 文件, /workspace/data/chroma_db)
        │  D0 一次性迁移
        ▼
worldsim-pg.rag.embeddings (vector(1024), HNSW cosine)
        ▲
        │  rag_engine.py 默认读（RAG_BACKEND=pgvector）
        └─ 回滚读（RAG_BACKEND=chroma，观察期）
```

- pgvector 扩展：v0.8.2，**需 superuser 创建**（worldsim_app 非超级用户，容器内 `worldsim_admin` 本地免密可建）
- rag schema：`AUTHORIZATION worldsim_app` + GRANT（沿用 B0 模式）

## 2. 部署步骤（已执行）

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

## 3. 回滚（三件套一体，观察期用）

| 组件 | 观察期（cutover 后 ~至 9/1 月度 rebuild 跑通）| 之后 |
|------|------------------------------------------|------|
| `chroma.sqlite3` | 保留，**chmod 444 只读** | 删除 |
| `chromadb` 依赖 | 保留（rag_engine/build_index chroma 分支）| 镜像重建时移除 |
| `RAG_BACKEND` 开关 + chroma 读分支 | 保留（`=chroma` 可回滚）| 删开关 + 删分支 |

切回 chroma 读：`RAG_BACKEND=chroma python ...`
切回 pg 读（默认）：`RAG_BACKEND=pgvector`（或不设）

**铁律**：删 chroma 文件当天即清 chromadb 依赖 + RAG_BACKEND 开关代码，不留半截空开关。

## 4. 演练 0 干扰验证（已做）

- 主理人容器内独立验收 PASS：count=4156、top-10 重叠率 1.0、top-5 仅同距离 tie 噪声（0.90~0.93，非误差）、RAG_BACKEND=chroma 回滚路径实跑通过、`_rag_query_pg` 坏连接失败计数 +1 不再静默降级。
- scheduler.py / contracts.py / fetcher_base.py 未改（D0 只动 rag 检索层）。
- chroma.sqlite3 原样保留（只读）。

## 5. 已知约束

- 容器未装 `pgvector` python 包：向量参数用手拼 `'[...]'` 字符串 + `::vector` 显式 cast（零外部依赖）；metadata 用 `json.dumps` + `::jsonb`。
- cosine 非逐位一致：top-5 集合因同距离并列可能重排，验收以 top-10 召回为准。
- 安全窗口：scheduler 每月 1 日 09:05 跑 `rebuild_rag_index()`；9/1 前必须完成 cutover 且观察无异常后再删三件套。
- 重建脚本 `build_rag_index.py` 已改 `TRUNCATE+INSERT` 单事务原子（修 chroma 旧毁新残 bug）。

## 6. 回滚命令速查

```bash
# 临时回滚到 chroma 读
RAG_BACKEND=chroma python your_script.py

# 观察期结束，确认 pg 稳定后清理
chmod 644 /vol2/1000/software/macro-scan/data/chroma_db/chroma.sqlite3   # 先恢复写权限（若需）
rm -f   /vol2/1000/software/macro-scan/data/chroma_db/chroma.sqlite3
# 后续：从镜像/requirements 移除 chromadb，删除 rag_engine 中 chroma 分支 + RAG_BACKEND 开关
```
