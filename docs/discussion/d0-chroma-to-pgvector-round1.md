# D0（chroma → pgvector）设计讨论 · Round 1

> **作者**：主理人 self-as-3-roles（架构 / 域 / 运维）
> **日期**：2026-08-13（自写, 待 user grill）
> **状态**：DRAFT · round1 · 待三轮交叉质询收敛
> **范围**：把 chromadb 单机 PersistentClient sqlite → worldsim-pg pgvector，向量查询路径全部走 PG。chroma 文件保留过渡期,最终删除。

---

## 0. 现实勘误（重型 SOP 第一功）

**STATUS.md 旧记**：「D0（迁 chroma 向量 4156 emb, pgvector vector(1536)+ivfflat）」
**实测**（容器内 probe，c0 样本 + count()）：

| 字段 | 旧记 | 实测 |
|------|------|------|
| 向量数 | 4156 | **4156** ✓ |
| 维度 | 1536 | **1024** ✗（勘误） |
| 距离函数 | 隐含 | **cosine**（`hnsw:space: cosine`）|
| 集合名 | 隐含 | **macro_kb** |
| ID 格式 | 隐含 | **c{global_i}** 字符串（c0/c1/...）|
| Metadata | 隐含 | **JSON `{source, chunk}`** |
| Document | 隐含 | **TEXT（chunk 文本，~257 字/chunk）**|
| 嵌入模型 | 隐含 | **SiliconFlow BAAI/bge-m3**（1024-dim native）|

**勘误结论**：`vector(1536)` 必须改为 `vector(1024)`；`ivfflat` 改成 `hnsw`（chroma 原即 HNSW，距离 cosine，保一致性无重训）；idx 算子族用 `vector_cosine_ops`。**不验证直接照旧记写代码 → 维度错 + 索引类型错 → 重建失败概率 100%**。

---

## 1. 三路初始立场（round1 self-as-3-roles）

### 1.1 架构（架构师）

- **A1** schema：`rag.embeddings(collection_name text, id text, document text, metadata jsonb, embedding vector(1024))`, PRIMARY KEY(collection_name, id), HNSW 索引 `USING hnsw (embedding vector_cosine_ops)`, AUTHORIZATION worldsim_app
- **A2** 单表通用：未来加 collection（不只是 macro_kb）不动 schema
- **A3** 不分 schema：单一 `rag` schema，B0 是 per-source（news/forecast/tianji 各占一），D0 是 per-collection 不合理（collection 是逻辑概念，会随 KB 演进而增减）
- **A4** 索引参数：`m=16, ef_construction=64`（pgvector 默认；4156 行无需调优）
- **A5** 元数据 JSONB：保持 chroma 原结构不变，仅 KEY 透传；不在 PG 侧做拆列（拆了就破坏 chroma 原查询语义）
- **A6** ID 类型 TEXT：保 c{N} 直通，不引入 BIGSERIAL（破坏 caller 预期）

### 1.2 域（RAG 消费方）

- **D1** 调用入口：`rag_engine.py` 的 `rag_query_vec()` + `build_index()` —— 全天枢 RAG 唯一读写口（hypothesis_engine.py 是 keyword M0 兜底,不消费 chroma）
- **D2** 行为不变性：返回值格式 `List["【文件名】\n片段"]` 不变；查询接口签名 `(query, n_results, chroma_dir)` 中的 `chroma_dir` 参数需重新解释（向后兼容: 保留参数名但内容改为 pg conn string 或 None）
- **D3** 阈值不变：`SCORE_THRESHOLD` 继续生效（distance > SCORE_THRESHOLD 过滤）
- **D4** 重建语义：`build_index()` 当前是「清空旧索引重建」。PG 版要不要保留「清空 + 重建」？建议 **是**（TRUNCATE rag.embeddings WHERE collection_name=$1 + 重建），避免历史 chunk 残留
- **D5** dual-write 取舍：**不要**（理由见 §2 决策项）
- **D6** 检索质量：cosine distance 数值范围 [0, 2]，chroma 同口径，`SCORE_THRESHOLD` 不需重校

### 1.3 运维（部署 / 回滚 / 监控）

- **O1** chroma 数据在哪：`/vol2/1000/software/macro-scan/data/chroma_db/chroma.sqlite3`（38MB, 容器 bind 源）
- **O2** chromadb 不是容器 —— 是 python 库 + sqlite 文件，迁移 = 改代码不涉及 docker compose
- **O3** 部署步骤：① `sql/04_d0_schema.sql` apply-schema（`CREATE EXTENSION IF NOT EXISTS vector` + CREATE TABLE + CREATE INDEX）② `python b0_migrate.py --only d0-rag` 或新脚本 `d0_migrate_rag.py` ③ 改 `rag_engine.py` 读写 PG ④ 改 `build_rag_index.py` 写 PG ⑤ 容器热挂载即生效（rag_engine.py 是 /app 下，改了不需 restart）；**但 build_rag_index.py 也走 /app 热挂载**——不需要 restart。
- **O4** 回滚：保留 chroma.sqlite3 文件 + chromadb 库；部署脚本留 `RAG_BACKEND=chroma` 环境变量开关（默认 `pgvector`）；回滚 = 改环境变量 + 重启容器（or 直接挂回旧版 rag_engine.py）。**注意** chroma.sqlite3 不能被覆盖写 —— D0 重建时禁止再写 chroma。
- **O5** 监控：4156 → 重建后 pg `SELECT count(*) FROM rag.embeddings WHERE collection_name='macro_kb'` 应 ≥4156；chroma 端 `col.count()` 应保持 4156 不变（只读 fallback）；二者相等 = 成功。
- **O6** 双容器（macro-scan + macro-sim）是否都消费 chroma？**否** —— macro-sim 是仿真层，不直接查 RAG。但 macro-sim 的 `world_deduction` 路径可能间接通过 macro-scan 输出消费，**不是 chroma 直读**。所以本次 D0 只动 macro-scan 容器。

---

## 2. 决策项（待 user 拍板）

| # | 决策项 | 我的推荐 | 反对意见（自洽反方） |
|---|--------|----------|----------------------|
| D-D1 | 索引类型 | **HNSW**（保 chroma 原 + cosine 无训练）| IVFFlat: 小数据集训练快，但 cosine + 4156 行优势不明显 |
| D-D2 | 距离函数族 | **vector_cosine_ops** | L2/inner product 不改（语义与 chroma cosine 不同）|
| D-D3 | Schema 设计 | **单表 rag.embeddings** + collection_name | 多表 per-collection (未来加 collection 改 schema 麻烦)|
| D-D4 | Dual-write？ | **不要**（重建低频 + 单次 cutover）| 要：但「B0 双写先例」不成立——全库搜不到 NEWS_PG_DUALWRITE 常量，B0 实际是一次性 backfill（b0_migrate.py），双写仅存在于 C0 指标路径。RAG 重建是手动低频 cutover，双写是实时流需求，此处无必要 |
| D-D5 | Chroma 何时删？ | **D0 +1 周观察期后** | D0 即删（不留历史包袱）|
| D-D6 | ID 类型 | **TEXT(128)** 保 c{N} | BIGSERIAL (破坏 caller 期望,反对) |
| D-D7 | 回滚开关 | **RAG_BACKEND=chroma\|pgvector env** | 不留开关（一旦验证即全切,不留 fallback）|
| D-D8 | Document 全文搜索 | **v1 不上**（TEXT 占位） | 顺便上 tsvector + pg_trgm（scope creep,反对）|

---

## 3. 风险 / 反方（自洽反驳）

- **R1**：chroma 是 HNSW，pgvector HNSW 在小数据集（4k 行）查询性能是否一致？→ pgvector HNSW 是 C 扩展实现，4k 行 << pgvector 文档建议的 1M+，余量足够
- **R2**：cosine 距离口径一致（chroma 与 pgvector `vector_cosine_ops` 都是 1-cos），SCORE_THRESHOLD 阈值无需重校；**但浮点/归一化次序不同，top-k 边界可能重排，非逐位一致**——验收不能用 count=4156 等价判据，要 `ORDER BY embedding <=> $1, id` 确定性 tiebreak + top-5 集合重叠率当闸门（见 §4 勘误 C5）
- **R3**：单 collection 后续可加，但 `WHERE collection_name=$1` 必有过滤——是开销吗？4156 行 + B-tree on (collection_name,id) + HNSW on embedding，OK
- **R4**：文档全文搜索缺位——现在 chroma 也不做全文（用 TF-IDF rag_query 兜底），不是回归
- **R5**：chroma.sqlite3 文件保留 = 仍占磁盘 38MB，但 chromadb 库仍 `pip install` 占用镜像层——如果 D0+1 周真的删，镜像也要重建。**回滚成本**：删 chroma 后想回滚只能从 git 老 commit 拉 `rag_engine.py` 还原 + chromadb 库得重装。**建议**：D0 完成 + 1 周观察期后，明确删 chroma 文件 + chromadb 库（macro-scan 镜像重建——这是 v2 工作）

---

## 4. 多 agent round1 论证结论 + 勘误（重型 SOP 立功）

> 架构/域/运维三路并行论证（各自读实际代码），8 项决策全收敛。以下为论证中暴露、会致「照旧写代码直接翻车」的勘误与盲点；原 round1 草稿 3 处错误（C1~C3）已就地更正。

### 4.1 三路对 8 决策项的收敛结论

| # | 决策 | 结论 | 一致度 |
|---|------|------|--------|
| D-D1 | HNSW | 采用 | 3/3 |
| D-D2 | vector_cosine_ops(`<=>`) | 采用（非逐位一致，见 C5）| 3/3 |
| D-D3 | 单表 rag.embeddings | 采用 | 3/3 |
| D-D4 | 不双写 | 采用（前提修正见 C2）| 3/3 |
| D-D5+D-D7 | 回滚三件套（合并，见 C4）| 采用 | 合并拍板 |
| D-D6 | TEXT(128) 保 c{N} | 采用 | 3/3 |
| D-D8 | v1 不上全文 | 采用（域+运维 2/1 反对架构「顺上」）| 2/1 |

### 4.2 round1 草稿 3 处错误更正（C1~C3）

- **C1 `b0-ops.md` 不存在**：§4 步骤⑤引用 `docs/d0-ops.md` 沿用 B0 ops 模板——实际 B0 无独立 ops 文档，运维真身是 `b0_migrate.py` + `sql/03_b0_schema.sql`。已更正引用。
- **C2 双写前提假**：§2 D-D4 反对意见写「B0 NEWS_PG_DUALWRITE 用过」——全库搜不到该常量，B0 实为一次性 backfill，双写仅存在于 C0 指标路径。D-D4 理由已重写。
- **C3 cosine 逐位一致误判**：§3 R2 原写「一致，SCORE_THRESHOLD 不需重校」隐含逐位一致——实际浮点/归一化次序不同，top-k 边界可能重排。已更正为「口径一致但非逐位一致」，验收改 top-5 重叠率。

### 4.3 论证新发现盲点（重型 SOP 立功，不论证必翻车）

- **C4 回滚三件套必须合并**：D-D5（chroma 删除时机）与 D-D7（RAG_BACKEND 开关）不能分两条拍——env 开关单独不构成回滚能力，真回滚锚点是 `chroma.sqlite3` 文件 + `chromadb` 依赖 + 双读代码三件套。删文件当天开关即变空开关。决策：观察 1 周后三件套**一体删除**（删文件当天即清依赖+开关代码，不留半截空开关）。
- **C5 cosine 非逐位一致（验收闸门）**：top-k 边界可能重排。验收 = `ORDER BY embedding <=> $1, id` 确定性 tiebreak + **top-5 集合重叠率 ≥ 阈值**（如 ≥0.95），不能只看 count=4156。
- **C6 幂等反噬（关键）**：**不能照抄 B0 的 `ON CONFLICT DO NOTHING`**——RAG 重建是「删旧建新」，KB 改一个文件后所有 `c{N}` 语义整体漂移，同 id 内容已变，`DO NOTHING` 会静默保留旧向量。必须 `DO UPDATE`（覆盖）或影子表原子 swap。现行 `build_index` 先 `delete_collection` 再建，embedding API 中途失败 = 旧毁新残，此 bug 不可搬进 PG（用影子表 + `TRUNCATE WHERE collection_name=$1` 安全重建或 rename swap）。
- **C7 pgvector 大概率未装（最致命）**：B0 把 `tianji.narrative_chunks.embedding` 存成 **BYTEA 而非 vector**——说明 worldsim-pg 至今未启用 vector 扩展。D0 step 0 必须 `worldsim_admin` 跑 `CREATE EXTENSION vector`，否则 `vector(1024)` 列建不了。这是 B0 埋的雷。**round2 落码前必须先验证 + 装扩展。**
- **C8 安全窗口**：scheduler 每月 1 日 09:05 跑 `rebuild_rag_index()`（`update_kb_numbers.py:361 → rebuild_rag_index`）。今天 8/13，**9/1 前必须 cutover 完**，别跨月触发导致两边不一致。
- **C9 静默降级致盲**：`rag_engine.py` 任何异常都 `return []` 转 TF-IDF，PG 挂了监控看不见。改 PG 读路径时须加失败计数/告警。
- **C10 `c{N}` 是遍历序号非稳定键**：改动 KB 后序号整体漂移，不能作为稳定业务键（保留 TEXT 类型无害，但别在下游当稳定 id 依赖）。

## 5. 下一步（user 拍板后）

1. user 对 §2 决策项逐条表态（OK / 改 X / 反方 R-N 哪条说服你）
2. 我根据反馈收敛为 v2 round2 草稿
3. round2 → round3 → 收敛
4. 落码：
   - `sql/04_d0_schema.sql`（CREATE EXTENSION vector + CREATE TABLE rag.embeddings + CREATE INDEX HNSW cosine + GRANT）
   - `核心代码/d0_migrate_rag.py`（自包含 apply-schema/backfill/verify 三子命令，复用 B0 的 psycopg3 + norm_ts 模式）
   - 改 `核心代码/rag_engine.py`（_get_collection 改 pg conn；rag_query_vec 改 pg 查询；签名保留 `chroma_dir` 参数名但解释为 `pg_connstr`，环境变量 `RAG_BACKEND=pgvector|chroma` 默认 pgvector）
   - 改 `核心代码/build_rag_index.py`（build_index 改 pg INSERT + chunk 写入，TRUNCATE collection 后重建）
   - 容器内实测 4156 → PG 一次性迁完
   - 部署 / 回滚脚本 `docs/d0-ops.md`（沿用 B0 模式：自包含 `b0_migrate.py` + `sql/03_b0_schema.sql` 的 apply-schema/backfill/verify 子命令结构；**注：B0 无独立 b0-ops.md 文档，运维真身即 b0_migrate.py**）
5. 主理人容器内独立验收：① PG `SELECT count(*) = 4156` ② 相似度查询对比 chroma vs pgvector top-5（结果集应一致） ③ 重建脚本 idempotent ④ `RAG_BACKEND=chroma` 回滚开关可读 ⑤ scheduler/contracts/fetcher_base 未改 ⑥ chroma.sqlite3 文件原样保留（只读）

---

## 6. 未决项 / 留待 round2/3

- D-D1~D8 拍板结果
- **rollback retention window**：1 周 vs 2 周 vs 永久（默认 1 周观察期后删 chroma.sqlite3）
- **是否删除 chromadb pip 依赖**（镜像层减少 80MB+）—— 同上窗口决定
- **是否回写 STATUS.md / docs/overview.md / docs/roadmap.md 的 1536/ivfflat 勘误**（commit 时连带修）