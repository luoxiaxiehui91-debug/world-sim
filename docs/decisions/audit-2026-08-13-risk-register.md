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
| P0-1 | 域/数据 | 双写静默丢数：pg 比 SQLite 少 134 行（news.articles 缺 id 32201-32293 整批 04:05Z 失败），无对账/补偿，缺口单调累积 | P0 | pg_write_collection.py 顶部自述异常须捕获不向上抛，每 upsert except:print 吞异常；scheduler.py grep reconcil/backfill/resync/drift 全无命中 | pg 被定位为统一库(SSoT)，却是会静默掉数且永不自愈的副本；基于 pg 的统计已系统性偏低且偏差不可估 | 架构+域 | **是**（E0-C 前必须先止血，否则读路径迁向一个持续丢数的 pg） | 待修复阶段 |
| P0-2 | 域/数据 | forecast.forecasts 时区双轨 +8h：120 行 created_at 整批漂移、2 行落未来 | P0 | prediction_logger.py:72 datetime.now().isoformat() 写 naive 北京时，pg timestamptz 按 UTC 解析记成未来；forecast_tracker.py:139/318/331 [:19] 截断 +00:00 亦违规 | 按日聚合/verify_after 到期/Brier 校准分全取错位样本，校准分(核心产出)已不可信且不报错 | 架构 | 否 | 待修复阶段(需回填历史120行) |
| P0-3 | 架构/运行时 | GRV B线 daemon 线程随宿主进程退出被强杀，sim_trigger.json 永不写，天璇自动推演静默停摆 ≥6.5天 | P0 | grv_threshold.py 约L196 threading.Thread(daemon=True) worker 内含 _write_sim_trigger；geo_risk_vector.py:955-956 主进程未 join 即退出；sim_trigger.json mtime=08-06 22:21 0字节 | 天枢 GRV 阈值驱动自动推演失效；tianji.predictions 自 08-06 14:34 零增长；ntfy 推送约80s报告永不兑现(假成功) | 架构 | 否 | **修复已落运行容器+git树(未commit)** |

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
