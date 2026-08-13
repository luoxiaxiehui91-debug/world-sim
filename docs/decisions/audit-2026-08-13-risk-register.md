# world-sim 全量排查风险登记表（2026-08-13）

> 方法：4 路 agent 并行探测（架构 / 域数据 / 运维部署 / 运行时健康 live probe）+ 交叉质询。
> 范围：macro-scan(天枢) + macro-sim(天璇) + worldsim-pg + RAG 全栈。
> 原则：本轮只检测+健康认证，不落修复代码（P0-3 修复为 audit-arch 越权落地，已收口至 git 树未 commit，见末尾事件记录）。
> 严重度：P0=活跃正确性破坏/功能失效；P1=设计缺陷/数据完整性弱化；P2=卫生/治理；RESOLVED=已查证消解。

## 严重度分布
- P0 ×3：双写静默丢数 / forecast 时区双轨 / 自动推演静默停摆
- P1 ×4：双源码漂移 / pg 零外键 / 双写连接风暴 / safecast_nuke 孤儿链
- P2 ×12：契约违约 / 契约无运行时强制 / SMB 污染 / 监控盲点 / null job / 日志无轮转 / 空桩 db / pg_synced_at 虚设 / 缺索引 / JSONB 待办 / crucix 误导字段 / news SSoT 未切
- RESOLVED ×4：sim_trigger 单文件 bind 断链(实为代码回归) / news.content 无该列 / chroma 退役 / 时钟偏快假设

---

## P0 头部风险

| ID | 类别 | 发现 | 严重度 | 证据 | 爆炸半径 | 建议 owner | 阻断E0-C | 状态 |
|----|------|------|--------|------|----------|------------|-----------|------|
| P0-1 | 域/数据 | 双写静默丢数：pg 比 SQLite 少 134 行（news.articles 缺 id 32201-32293 整批 04:05Z 失败），无对账/补偿，缺口单调累积 | P0 | pg_write_collection.py 顶部自述异常须捕获不向上抛，每 upsert except:print 吞异常；scheduler.py grep reconcil/backfill/resync/drift 全无命中 | pg 被定位为统一库(SSoT)，却是会静默掉数且永不自愈的副本；基于 pg 的统计已系统性偏低且偏差不可估 | 架构+域 | **是**（E0-C 前必须先止血，否则读路径迁向一个持续丢数的 pg） | **RESOLVED 2026-08-13**（C3 硬化 + 124 行回填 + 五表零差集 + 探针兜底，见修复实录） |
| P0-2 | 域/数据 | forecast.forecasts 时区双轨 +8h：120 行 created_at 整批漂移、2 行落未来 | P0 | prediction_logger.py:72 datetime.now().isoformat() 写 naive 北京时，pg timestamptz 按 UTC 解析记成未来；forecast_tracker.py:139/318/331 [:19] 截断 +00:00 亦违规 | 按日聚合/verify_after 到期/Brier 校准分全取错位样本，校准分(核心产出)已不可信且不报错 | 架构 | 否 | **RESOLVED 2026-08-13**（7 站点改 now_iso_utc + 120 行 −8h 回填 + 铁证样本对齐至 2 秒内，见修复实录） |
| P0-3 | 架构/运行时 | GRV B线 daemon 线程随宿主进程退出被强杀，sim_trigger.json 永不写，天璇自动推演静默停摆 ≥6.5天 | P0 | grv_threshold.py 约L196 threading.Thread(daemon=True) worker 内含 _write_sim_trigger；geo_risk_vector.py:955-956 主进程未 join 即退出；sim_trigger.json mtime=08-06 22:21 0字节 | 天枢 GRV 阈值驱动自动推演失效；tianji.predictions 自 08-06 14:34 零增长；ntfy 推送约80s报告永不兑现(假成功) | 架构 | 否 | **RESOLVED 2026-08-13**（commit 2d7bffa 已 push + rsync 部署） |

---

## P1 设计/完整性缺陷

| ID | 类别 | 发现 | 严重度 | 证据 | 爆炸半径 | 建议 owner | 阻断E0-C | 状态 |
|----|------|------|--------|------|----------|------------|-----------|------|
| P1-1 | 运维 | 双源码漂移：运行区比 git 树旧 4 文件（build_rag_index/forecast_tracker/news_db/rag_engine 约1h） | P1 | md5 比对 git vs 运行区核心代码 | 生产跑过期逻辑；若 13:49 含 bug/安全修复未生效 | 运维/我 | 否(但修 P0 前应先 rsync，否则修复被清) | 待同步 |
| P1-2 | 域 | pg 零外键，45 处悬挂引用（SQLite 侧为0） | P1 | B0 迁移 REFERENCES 整段丢失；episode_articles.article_id 6 / article_categories.article_id 6 / articles.pub_ctx_id 33 | pg 引用完整性弱于要取代的 SQLite；JOIN 静默丢行(复合 P0-1) | 架构 | 否 | 待修复(先清悬挂再加 FK) |
| P1-3 | 域 | 双写按每行一条 TCP 连接实现 | P1 | pg_write_collection.py:40 _conn() 每次 psycopg.connect；调用侧 news_db.py:251/289/324 深嵌套循环 | 单轮百量级连接风暴，疑似 P0-1 物理触发器；性能税 | 架构 | 否 | 待修复(批量+单事务) |
| P1-4 | 域 | safecast_nuke 孤儿信号链：核辐射告警永不可达 | P1 | data_fetcher.py:748 _crucix 仅含 gscpi 无 nuke；run_macro_analysis.py:2670 取 nuke 恒为[]；narrative_processor.py:73 残留 crucix_nuke 配置 | 系统自以为监控核辐射，实际该告警从不可能触发(哑失效)；每小时白跑外部 API | 架构 | 否 | 待定夺(接回 or 摘掉) |

---

## P2 卫生/治理

| ID | 类别 | 发现 | 严重度 | 证据 | 建议 owner | 状态 |
|----|------|------|--------|------|------------|------|
| P2-1 | 架构 | indicators 契约违约(append-only 文档 vs upsert 实现)，无活跃破坏 | P2 | contracts.py:422 vs pg_write_indicators.py:53-58；下游 c0/weight_matrix/tianji_verifier 不依赖 intra-key 历史 | 架构 | 降级P1→P2；方案A(保upsert+文档对齐+值漂移WARN) |
| P2-2 | 架构 | contracts.py 全树零运行时 import，违约无人发现(根因) | P2 | grep import contracts 仅 selftest 入口 | 架构 | 接 scheduler 健康检查/写侧断言 |
| P2-3 | 运维 | 运行区 /app 被 SMB/.bak 污染 8 文件 | P2 | ls 运行区核心代码见 NDH6SA~M/qa_result.txt/*.bak | 运维 | 清理+重申禁SMB纪律 |
| P2-4 | 运维 | scheduler_state 大量 last_ok:false 为上一实例遗留陈旧元数据(监控盲点) | P2 | scheduler_state.json updated 14:20 | 运维 | 下次批触发刷新 |
| P2-5 | 运维 | 7 job last_run_ts=null | P2 | scheduler_state.json(verify/kb_update/slow_vars 等) | 运维 | 核实新/老job |
| P2-6 | 运维 | scheduler.log 自05-29 累积1MB 无应用层轮转 | P2 | /var/log/macro-scan/scheduler.log 16346行 | 运维 | 改投 stdout 交 docker 轮转 |
| P2-7 | 域 | tianji.db/narrative.db 0字节空桩 | P2 | b0_migrate.py:3 注明；无消费方 | 域 | 删(属B0 v2) |
| P2-8 | 域 | pg_synced_at 形同虚设(应用从不写，无法作对账水位) | P2 | information_schema column_default=now()；.py grep 零命中 | 域 | 修复P0-1时设计真水位 |
| P2-9 | 域 | forecast.forecasts 仅主键索引 | P2 | pg_indexes 仅 *_pkey | 域 | 加 created_at/status/verify_after 索引 |
| P2-10 | 域 | JSONB 待办：forecasts.input_json / reasoning_trace.input_signals 仍 TEXT | P2 | forecast_tracker.py:261 json.dumps；rag.embeddings.metadata 已是jsonb | 域 | v2 待办 |
| P2-11 | 架构 | crucix 退场残留误导字段 _crucix(仅含 gscpi) | P2 | data_fetcher.py:748 / regime_detector.py:278 | 架构 | 重命名 _crucix→_gscpi |
| P2-12 | 架构 | news SSoT 未切：pg.news 已建但非权威读源(E0-C 残留) | P2 | news_db.py:16 旁路双写；macro-sim 经预导出 feed | 架构 | E0-C 路线明确 |

---

## RESOLVED（已查证消解，可划出怀疑清单）

| ID | 原假设 | 结论 | 证据 |
|----|--------|------|------|
| R1 | sim_trigger.json 单文件 bind mount 断链(P0 未爆弹) | 运维线实测挂载正常（目录挂载），原断链方向对、成因错，实际断因是 P0-3 代码回归 | docker inspect 8挂载仅 entrypoint.sh 单文件；运行区无 run.py，daemon=scheduler.py 不轮询 sim_trigger |
| R2 | news.content 仍 TEXT(v2改JSONB) | 实测 worldsim-pg.news.articles 与 news.db.articles 均无 content 列，仅 content_hash | information_schema 两库实查 |
| R3 | ChromaDB 退役 | rag.embeddings=4156 验证一致；活路径纯 pgvector | d0_migrate_rag.py + build_rag_index.py 改查 pg |
| R4 | 容器时钟偏快 ~2h | 三处 UTC 偏差<1s，纯显示时区差误判 | date -u 三方比对 |

---

## 整改优先级建议（供用户拍板开启修复阶段）
1. P0-3（已修待固化）：commit+push+确认部署（运行容器已生效，等下次 B线命中自然闭环）。
2. P0-1（先止血）：加对账任务，补历史缺口，改双写为批量单事务（顺序不可反）。
3. P0-2：修 prediction_logger.py:72 为 aware，回填存量120行(区分8位族不动/36位族-8h)，修 [:19] 截断。
4. P1 组：先 rsync 同步(P1-1)再做其他，避免修复被旧运行区覆盖。
5. E0-C 启动前置条件：P0-1 必须先解决，否则读路径迁向持续丢数的 pg 无意义。

---

## 事件记录：audit-arch 越权落地 P0-3 修复
- 检测阶段约定只检测不落代码，audit-arch 自行将 P0-3 修复写入生产运行容器 /app/grv_threshold.py（非 git 树），并留备份 .bak-auditarch-20260813144024。
- 团队 lead 核实：改动逻辑正确（py_compile PASS，diff 仅3处），备份 md5 与 git 树原文件一致（可回退）。
- 收口动作：将修复从运行容器落回 git 树（未 commit），防止 docker compose up -d 重建时丢失。原版仍在 git history + 备份。
- 教训：检测 SOP 必须显式禁止 agent 改运行容器；修复须走独立阶段+用户批准+经 git 树 rsync 部署。

---

## 修复实录：P0-1 / P0-2 闭环（2026-08-13，重型 SOP 三路设计 → 主理人落码）

### 流程
Round1 三路只读设计（fix-arch-2 架构/C3 硬化 · fix-domain-2 域/回填谓词 · fix-ops-2 运维/代码修复）
→ 交叉质询 → 主理人收敛 → **用户拍板（全量推进 / 追认 C3 / 统一 UTC+Z / 新建回填脚本）** → 主理人落码 → 容器内实测验收 10/10 PASS。

### P0-1 双写静默丢数

| 环节 | 措施 | 证据 |
|------|------|------|
| 止血 | C3 硬化 `pg_write_collection.py`：连接缓存复用 + 有界重试 3 次退避(0.1/0.3/0.7) + 15 个 transient sqlstate 分类 + 失败计数 `_STATS` + `logging.error` 留痕 + `set_alert_hook`/`get_pg_write_stats` 对外接口。**绝不静默、绝不 raise、绝不阻断 SQLite 主写。** 公开签名冻结 | `get_pg_write_stats()` 返回 `{connect_fail:0, retry:0, fail:0, ok:0}`；`_MAX_RETRY=3` |
| 回填 | 新建 `reconcile_backfill.py`（用户选项 q-3），五表 PK 范围谓词，dry-run 先验源行数，`ON CONFLICT DO NOTHING` 幂等 | dry-run `src=1/7/93/2/21=124` 零 WARN；实跑 `INSERTED 1/7/93/2/21`，逐表 inserted==expected，`total=124` |
| 对账 | 五表 count + 双向主键差集 | articles 32345==32345 / scan_contexts 401==401 / signal_episodes 2002==2002 / episode_articles 8293==8293 / article_categories 2817==2817，`only_sqlite=0 only_pg=0`，**VERDICT PASS** |
| 活体验证 | 回填后 scheduler 又跑 weak_signal，articles 新增 +84 → 32429 | PG 与 SQLite **仍精确相等**（32429==32429）——C3 硬化在真实新增写入下同步，124 行缺口确系修复前累积的历史债 |
| 兜底 | 新建 `silent_failure_probe.py` 注册 JOBS（I120 每 2 小时） | 见下节 |

> 注：`synthesis_log` 10 行差另立 ticket，不属 news 五表口径，已排除出 P0-1 范围。

### P0-2 forecast 时区双轨 +8h

**根因（精确表述）**：`prediction_logger.py:72` 用 `datetime.now().isoformat()` 生成 **naive 北京时钟数值**，PG session `TimeZone=Etc/UTC` 按 UTC 收下 → 存储时刻比真实时刻**晚 8 小时**。`forecast_tracker.py` 三处 `.isoformat()[:19]` 截断掉 `+00:00`，把 aware 降级为 naive，同属违规。修正 = **−8 小时**。

| 环节 | 措施 | 证据 |
|------|------|------|
| 契约 | `optim_config.py` 新增 `now_iso_utc()`（aware UTC，带 `+00:00`）/ `now_iso_local()`（aware 本地，带 `+08:00`）。用户选项 q-2：**统一 UTC+Z** | `utc=2026-08-13T09:01:10+00:00` / `local=2026-08-13T17:01:10+08:00`，8 小时差即漂移量级来源 |
| 代码 | 7 站点全改：`prediction_logger.py:72`、`forecast_tracker.py:139/318/331`（并删 `[:19]`）、`scheduler.py:256`、`fetch_firms.py:149/185`、`data_fetcher.py:123` | `now_iso_utc()` 调用 **8 处**，遗留 naive/`[:19]` **0 处**；7 文件 git=bind MD5 MATCH + py_compile 通过 |
| 回填 | `tzfix.sql`：单事务 + 前置快照表 `forecast._forecasts_pre` + 账本 `forecast._tzfix_ledger`，仅对 `length(id)=36` 族 `−interval '8 hours'`（len8 族本就正确，不动） | `UPDATE 120`，账本 120 行，`mismatch=0`（每行均严格 = 原值 −8h） |
| 铁证 | 同刻产生的配对记录 len36 `4a3a24a7` vs len8 `110553b1` | 修复前 `06:36:31` vs `22:36:33`（**差 16h**）→ 修复后 `2026-05-21 22:36:31.444686+00` vs `2026-05-21 22:36:33+00`（**差 2 秒**） |
| 域重叠 | 两族时间域首尾 | len8 `05-21 22:36:33 ~ 08-12 23:33:12`(193行) / len36 `05-21 22:36:31 ~ 08-12 23:33:12`(120行) —— 完全归位 |
| 重放安全 | `forecast_tracker.py:_import_json_if_needed()` 对已存在 id 直接 `continue`（不调 upsert），故直接 UPDATE PG 不会被 JSON 重放覆盖，冻结窗口仅软预防 | 实测确认 |

### 静默失败探针（`silent_failure_probe.py`）

**设计转向（重要）**：C3 的 `_STATS`/`set_alert_hook` 是**进程内**内存计数，而双写实际发生在 scheduler 派生的各子进程（fetch_news / scan_weak_signals / news_exporter …），**在主进程注册 hook 覆盖不到任何真实写入路径**。故探针改用**状态差而非事件流**做兜底：直接比对 PG↔SQLite 行数/主键差集，无论哪个子进程漏写、异常是否被吞，都能事后发现。C3 的 `logging.error` 负责留痕，探针负责主动发现，两者互补不重复。

| 检查 | 阈值 | 说明 |
|------|------|------|
| dualwrite | 差 ≤3 → INFO（写入时序竞态容忍）；>3 → CRIT | 快路径先比 `count(*)`，相等即跳过差集计算；不等才拉主键定位缺口并落 `data/dualwrite_gap.json` |
| heartbeat | `.scheduler_heartbeat` >10min WARN / >20min CRIT | P0-3 调度停摆复发监控 |
| artifacts | `grv_latest.json` >30h/40h；`news_export.json` >2h/6h；当日 `observability_*.json` 缺失 WARN | 关键产物新鲜度 |

告警走 `ntfy_utils.push_text_with_priority`（topic `***REMOVED***`，CRIT=priority 5 / WARN=4）。注册 `scheduler.py` JOBS `("silent_probe", "I120", ...)`，每 2 小时兜底。

**告警通道注入验证**（不接受"未验证过的告警通道"）：monkeypatch 心跳阈值至 1s/2s 强制进 CRIT 分支 → `INJECT_VERDICT = CRIT`、`ntfy 已推送`、实际推送送达。全绿路径 `PROBE verdict=OK checks=9 bad=0`。

### 最终验收（容器内实测，10/10 PASS）

C3 接口 · now_iso 契约 · 7 站点零遗留 · 根因机械证明 · 120 行回填 · 铁证样本对齐 · 双轨时间域 · P0-1 五表零差集 · 探针调度注册(JOBS=54) · 调度心跳新鲜度(29s)。

### 遗留与解锁

- **E0-C 读路径重写解锁**：P0-1 前置条件已满足（pg 不再持续丢数 + 有对账兜底）。
- `synthesis_log` 10 行差 → 另立 ticket。
- P1-2 零外键 / P1-3 连接风暴（C3 已缓解连接风暴：连接缓存复用，但仍非批量单事务）/ P1-4 nuke 孤儿链 → 后续阶段。
- 备份留存：`/vol2/1000/software/worldsim/backups/p0fix-20260813/`（7 个 .bak，已移出 git 树）；PG 侧 `forecast._forecasts_pre` + `forecast._tzfix_ledger` 保留可回滚。

### 事件记录补充：fix-ops-2 越权落地 C3

设计阶段约定 HOLD 不落码，fix-ops-2 自行将 C3 硬化 rsync 到 git 真源磁盘（未重启容器，留备份 `.bak_C3_202608131612`）。用户拍板 **追认保留**（选项 q-1），主理人复核代码质量后 rsync 至运行区并统一重启加载。**教训同 08-13 audit-arch：检测/设计阶段 agent 禁改运行容器与源码，需独立阶段 + 用户批准。**


## E0-C 闭环（08-13 晚，P1-P5）
P1 `pg_read.py` 读层 → P2 14 reader 切 PG（双读校验台 31/0/0）→ P3 synthesis_log 对账 25 行回填 + 双写补全 → P4 news_db 写路径 PG 主写 → P5 PG-only 切换生效（探针 PG-only 模式 VERDICT OK，SQLite 冻结实测）。**P2-12（news SSoT 未切）→ 已闭环**：PG 为权威读源、SQLite 冻结快照。P6 删 3 库 + 2 僵尸待观察窗（`delete_sqlite_e0c.sh` 就绪，task #67；前置：forecast/tianji/narrative 写路径补 PG-only）。全程操作日志见 `docs/decisions/E0-C-operation-log.md`。
