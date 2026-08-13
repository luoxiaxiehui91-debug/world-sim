# E0-C 操作日志：读路径重写 + 删 3 个 SQLite

> 项目：world-sim（世界推演系统）· 天枢 macro-scan
> 启动时间：2026-08-13 19:42 GMT+8
> 授权：用户 19:42 拍板「接着推 + 做好操作日志」
> 前置条件：P0-1 / P0-2 / P0-3 全部 RESOLVED，PG 数据完整（见 audit-2026-08-13-risk-register.md，容器内 10/10 验收）
> 纪律（重型 SOP）：设计讨论 + 交叉质询收敛 → 用户拍板 → 落码。落码前不做任何破坏性动作。
> 红线：
>   1. 删 SQLite 前必须确认 PG 读路径等价 + 已备份 + 可回滚
>   2. 禁止「单文件 bind mount + 原子写」跨容器契约（既有跨容器坑）
>   3. 部署 = rsync + 必要 up -d；改调度/新增 import 须 docker restart

## 一、范围（设计阶段待确认）
- 目标：删除 3 个残留 SQLite，读路径统一走 worldsim-pg
- 待查：① 哪 3 个 SQLite？② 各自被哪些读路径消费？③ PG 等价表/视图是否已存在？④ 回滚方案
- 注：news 五表（scan_contexts / signal_episodes / articles / article_categories / episode_articles）已双写 PG，不属本次 3 个

## 二、操作记录（每动作追加：时间 / 动作 / 证据 / 结论）
（调查与设计并见下方追加）

## 三、设计调查结论（2026-08-13 19:4x GMT+8）

### 3.1 磁盘实际 4 个 .db → 3 业务库 + 1 僵尸
- **news.db**：scan_contexts / signal_episodes / articles / article_categories / episode_articles + synthesis_log。5 新闻表已双写 PG(news.*)；synthesis_log 仅 b0_migrate 静态迁入 PG(news.synthesis_log)，运行时未双写（留 C 阶段）。
- **forecast_tracker.db**：forecasts / actuals / evaluations + 天玑表(predictions / reasoning_trace / narrative_chunks / weight_update_log)。已 E0-A 旁路双写 PG(forecast.* / tianji.*)。
- **narrative.db**：narrative_chunks / narrative_density_flags / weight_update_log。已双写 PG(tianji.*)。
- **tianji.db**：0 字节僵尸（b0_migrate.py:3 明证"所有天玑表都在 forecast_tracker.db 内"）。无任何读路径 → 删除零风险，不属 3 业务库。
→ **E0-C 删 3 业务库 = news.db / forecast_tracker.db / narrative.db；tianji.db 僵尸顺手清。**

### 3.2 读路径消费者清单（须改写的）
- news.db 读：daily_narrative / geo_risk_vector / grv_threshold / news_exporter(→news_export.json 喂 macro-sim) / ntfy_listener(计数) / observability(synthesis_log) / signal_synthesizer(signal_episodes+synthesis_log) / situation_detector / situation_tracker / scan_weak_signals(主写) / scheduler(状态) / web_server(UI)
- forecast_tracker.db 读：forecast_tracker(评估) / tianji_db(预测) / run_macro_analysis
- narrative.db 读：narrative_processor

### 3.3 交叉质询 catches（C0 模式）
- **R1 synthesis_log PG/SQLite 差 10 行**（既有 ticket）：切读 PG 前须对账/补行，否则 cooldown 计数轻微漂移。
- **R2 写路径切换是硬骨头**：scan_weak_signals→news_db.py 现写 SQLite。删库前必须让 writer 改写 PG（或翻转双写方向）。最危险一步。
- **R3 macro-sim 绝缘性**：macro-sim 消费 news_export.json（预导出）非直连 news.db；保持 news_exporter 从 PG 产出同构 JSON 即可。forecast/narrative 消费路径须确认。
- **R4 tianji.db 僵尸**：无读，删除零风险。

### 3.4 分阶段落码方案（每阶段可回滚）
- **P1【纯新增·可逆】** 建 PG 读层封装（pg_read_news 等），不改任何现有读路径。
- **P2【可逆】** 逐 reader 切到 PG 读层；并行双读（SQLite vs PG）diff 输出校验一致。
- **P3【可逆】** synthesis_log 对账（补 10 行或书面确认可忽略）。
- **P4【破坏性·需二次拍板】** writer 切 PG-primary（news_db / forecast_tracker / narrative_processor 改写 PG，停 SQLite 写）。
- **P5【可逆】** 备份 3 .db → backups/；停 SQLite 写；观察窗口。
- **P6【破坏性·需二次拍板】** 删 3 .db + tianji.db 僵尸；更新调度/文档；git 收编。
- **建议**：先落 P1-P3（读切+校验，SQLite 仍写），观察无误后再拍板 P4-P6。

### 3.5 待用户拍板
- 范围确认：删 news.db / forecast_tracker.db / narrative.db + 僵尸 tianji.db（4 个文件）。
- 开工方式：先 P1-P3（推荐，可逆） / 一步到位 P1-P6 / 仅定稿设计不动码。

## 四、操作记录（按时间倒序，每动作含 时间/动作/证据/结论）

### 2026-08-13 20:4x P2 完成 + P3 synthesis_log 对账闭环
- **P2 全部 reader 切 PG**：第一批 news_exporter/ntfy_listener/geo_risk_vector/grv_threshold/daily_narrative/situation_detector/situation_tracker（c8d7588）；第二批 signal_synthesizer/observability/web_server；第三批 forecast_tracker/tianji_db/narrative_processor（47a5f72）。news.db 读侧零 sqlite 残留（仅注释/常量/写路径）。每批 rsync → py_compile → import 冒烟 → 函数级实测（真实 PG 数据）。
- **关键修复（pg_read 行边界归一化）**：PG 时间列 timestamptz 返回 datetime，consumer 大量 `r[1][:10]`/字符串比较会崩——news_exporter 首次运行 `TypeError: datetime not subscriptable` 实证。修复：_Row 构造时 datetime→UTC 文本"YYYY-MM-DDTHH:MM:SS"、Decimal→float、bool→int、bytes→str。
- **observability 顺带修复**：log_time/resonance_ok 列在 SQLite 本就不存在（历史统计恒零）→ PG 移植改用 triggered_at → 今日统计恢复真实值（25 条 staging）。
- **P3 synthesis_log 对账**：reconcile_synthesis.py 回填 25 行（id 1143-1167，全为今日 staging），INSERTED 25 → PG=1167，双向零差集 VERDICT PASS。
- **P3 关键 catch（C0）**：读已切 PG 而写还在 SQLite → cooldown read-after-write 断裂（staging 潜伏、生产必炸）。补救：pg_write_collection 新增 `upsert_synthesis_log`（复用 C3 连接缓存/有界重试/告警），signal_synthesizer._write_log + ntfy_listener.cmd_silence 补 PG 双写（非阻断）。
- **最终双读校验台**：31 PASS / 0 GAP / 0 FAIL（synthesis_log gap 归零）。
- 观察点：P2-P3 后 synthesis_log 为双写（SQLite+PG）；停 SQLite 写与删 3 库属 P4-P6（需二次拍板）。narrative.db/tianji.db 为 0 字节僵尸。

### 2026-08-13 20:1x P2 — 双读校验台全绿（30 PASS / 1 GAP / 0 FAIL）
- 动作：建 `verify_reads_e0c.py`（27 条查询对 + 7 条全量 GAP 对账，SQLite vs PG 逐行比对），容器内跑通，固化到 git 树 + /app 供 E0-C 全程复用。
- 数据层验证：7d/30d 文章窗口 id/标题/ingested_at 全量一致（0 差集、0 值差）；narrative_chunks(419)/forecasts(314)/predictions(7)/density_flags(1)/articles(32476)/signal_episodes(2022) 全量对等。
- 唯一 GAP：synthesis_log SQLite=1167 vs PG=1142，差 25 行 → P3 对账（PG 侧运行时未双写 synthesis_log，静态迁入后持续落后）。
- 方言坑（已解，可复用）：
  1. `",".join("%s" * N)` 是字符级 join → 产出 "%,%,..." 报错；须 `",".join(["%s"]*N)`。
  2. psycopg 带参时字面 % 必须 %%；`LIKE '%RUS%'` → `LIKE '%%RUS%%'`。
  3. PG 禁 DISTINCT + ORDER BY 非 select 列 → `GROUP BY a.title ORDER BY MAX(a.ingested_at) DESC`。
  4. `DATE(x)` → `(x::date)::text`；`datetime('now','-24 hours')` → `NOW() - INTERVAL '24 hours'`；`sqlite_master` → information_schema。
  5. PG real(float32) vs SQLite double：ft_pending_list 6 位小数差（0.726044 vs 0.726043）→ 容差 1e-4；hygiene 项可 ALTER 列改 double。
  6. 并列时间戳 LIMIT 边界 tie-break 不同（同秒批量入库，SQLite 按 rowid / PG 按 pk）→ LIMIT 子集不同但合法；窗口全集一致已核。
  7. P0-2 遗留：forecasts.created_at SQLite naive 北京 vs PG UTC → 113 行 8h skew（PG 正确），已容忍；SQLite 侧未回填属预期。
- 观察点：observability 的 log_time/resonance_ok 在 SQLite 本就不存在（统计一直是零）→ PG 移植改用 triggered_at，顺带修复。
- 结论：SQL 移植语义全部验证等价，P2 翻 reader 有绿灯。下一步逐模块切 PG 读层。

### 2026-08-13 19:5x P1 — 建 PG 读层 pg_read.py（纯新增·可逆）
- 动作：新建 `pg_read.py`（只读 worldsim-pg），rsync 进运行区 /app（新文件，无需 docker restart）。
- 设计：worldsim_app 只读（仅 SELECT）；自定义 _Row 行工厂同时支持 row["col"] 与 row[0]（等价 sqlite3.Row），使 P2 翻 reader 仅「换 connect + ?→%s」；每次 connect 新建连接（避 `with c:` 关连接踩缓存）；search_path=news,forecast,tianji,public；占位符 %s。
- 踩坑：psycopg3 row_factory 协议是 `row_factory(cursor)` 返回逐行 maker，首版写成两参直接调用 → 容器内 smoke 报 missing 'raw'；修正为返回 `_make(raw)` 后通过。
- 证据：容器内 `docker exec macro-scan-macro-scan-1 python /app/pg_read.py` → {"ok":true,"articles":32476,"signal_episodes":2022,"synthesis_log":1142}；py_compile 通过。
- 结论：P1 完成，读层可用。未改任何 consumer，SQLite 仍写。下一步 P2 逐 reader 切 PG + 双读校验。
