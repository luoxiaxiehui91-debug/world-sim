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


### 2026-08-13 21:4x P6 准备 — 删除脚本就绪 + synthesis_log 写路径收尾
- 发现：P5 后探针 WARN「SQLite 仍被写」——synthesis_log 写路径（signal_synthesizer._write_log 与 Live 模式 UPDATE）未加 PG-only 分支，仍写 SQLite news.db（21:32 mtime 证据）。
- 修复：①`_write_log` 加 PG-only 分支（`_next_id` + upsert_synthesis_log）；②ntfy_listener.cmd_silence 加分支；③pg_write_collection 新增 `update_synthesis_log_success`（Live 模式 llm/ntfy 成功后 PG 更新）+ signal_synthesizer UPDATE 分支。
- 验证：直接激活 `_write_log`（PG-only）→ PG 写入、SQLite synthesis_log 1172→1172 冻结；探针 NON_OK=0。
- 重打 marker（1786628269，所有 news.db 写路径 PG-only 确认后）→ 探针 VERDICT OK，SQLite 冻结确认。
- 删除脚本 `delete_sqlite_e0c.sh`（git 树）：门禁（marker / env=1 / 探针 OK / P4 备份存在）→ 快照 backups/e0c-p6-<ts>/ → rm 4 个 .db → 验证无残留 + 探针 OK。**dry-run 门禁 4/4 全绿**。
- 观察点：PG 计数持续增长（articles=32560 / ctx=404 / ep=2034）——切换后系统正常运转，写全走 PG。
- **P6 执行前置待办**：forecast_tracker / tianji_db / narrative_processor 写路径尚无 PG-only 分支 → P6 删 forecast_tracker.db 后会复生（功能无影响——读全 PG，探针不查这些文件；但物理删不彻底）。观察窗口期间补齐后 P6 才"真删干净"。


### 2026-08-13 21:3x P5 — PG-only 切换生效（WORLDSIM_SQLITE_OFF=1 + up -d）
- 前置：探针 dualwrite 加 PG-only 分支（`.sqlite_frozen_at` marker 存在 → 验证 SQLite 冻结 + PG 五表健康），避免 SQLite 停写后 count 差被探针误报 CRIT（切换前必须解决，否则 2h 后误告警）。
- 动作：运行区 compose `environment:` 加 `WORLDSIM_SQLITE_OFF=1`；touch `data/.sqlite_frozen_at`（epoch 1786627625）；`docker compose up -d macro-scan`（容器 Recreate→Started）。
- 验证：容器内 `printenv WORLDSIM_SQLITE_OFF=1`；探针 VERDICT=OK（五表 PG 健康 + **SQLite 冻结确认** + 心跳 24s + 产物新鲜）；count 基线 PG articles=32476 / scan_contexts=402 / episodes=2022 vs SQLite 32476 / 403 / 2022（冻结快照；ctx 差 1 行为历史遗留，读全 PG 无影响）。
- **直接激活测试（21:3x）**：真实容器 env（WORLDSIM_SQLITE_OFF=1）+ scheduler 同款 news_db 写函数，写 ctx id=405 → PG vix=999.99 存在、SQLite scan_contexts 403→403 冻结、清理残留 0（5 秒级验证）。
- **真实采集验证**：手动 `scan_weak_signals.py` 一轮（2min，零 ERROR/Traceback）→ PG scan_contexts 402→**403**（写路径生效）、SQLite 冻结 403 不变；articles/episodes/cats 无变化（本轮无新文章）；日志干净。
- **结论**：PG-only 切换完全生效。观察窗口 12-24h，之后拍板 P6。
- 回滚：去掉 compose 的 WORLDSIM_SQLITE_OFF + rm marker + up -d，即回双写。
- 观察窗口：切换后 scheduler 心跳正常、探针 I120 在线；建议 12-24h 观察后再拍板 P6（删 3 库 + 僵尸）。


### 2026-08-13 21:2x P4 — news_db 写路径 PG 主写支持（WORLDSIM_SQLITE_OFF 开关，默认关=双写现状）
- 改造：news_db.py 6 写函数（write_scan_context / insert_articles / tag_articles / insert_signal_episode / link_episode_articles / prune_old_articles）加 PG-only 分支 + get_trigger_titles（news_db 内残留 SQLite 读）直接切 PG。
- 设计：`WORLDSIM_SQLITE_OFF=1` → PG 主写（id 用 pg_write_collection._next_id MAX+1 生成、url/content_hash 查重与 pub_ctx 走 PG、删老文章走 delete_news_articles）；默认不设 → 双写现状（线上零变化）。单容器顺序写无 id 并发竞争。
- 验证（容器内隔离，测试数据全清）：**A PG-only 完整链路** ctx404→article32477→category→ep2023→episode_article 全写 PG、SQLite 零文件；**B 默认双写** SQLite+PG 各 1 行回归通过；**C get_trigger_titles** 真实 ctx=401 返回 2 条地缘标题。
- 踩坑（可复用）：
  1. 函数内 `from X import f` 把 f 声明为局部变量 → 后续分支用模块级同名 f 报 UnboundLocalError；改用 `import X as _x; _x.f()`。
  2. psycopg 传空元组 () 参数也会扫描占位符 → 字面 % 报错；无参用 `c.execute(sql)` 不传 params。
  3. pg_read._row_factory 在 DML（cursor.description=None）会崩 → 修复为空 cols（row_factory 兼容无结果集）。
  4. news.scan_contexts.data_quality 是 text 列（非 jsonb），jsonb 参数化比较报 operator does not exist。
- 备份：4 个 .db 已 cp 至 /vol2/1000/software/worldsim/backups/e0c-p4-20260813/（news/forecast_tracker/narrative/tianji）。
- 状态：P4 代码就绪、**默认关（线上双写不变）**。P5 切换 = 运行区 compose 加 `WORLDSIM_SQLITE_OFF=1` + up -d + 验证 SQLite 停写 + 观察窗；P6 删 3 库 + 僵尸待 P5 观察后拍板。

### 2026-08-13 20:3x 全量验收（E0-C P1-P3 闭卷最后一道门，14/14 PASS）
- 动作：固化 `final_acceptance_e0c.py` 到 /app（只读、不推 ntfy，供后续回归复用），容器内全量验收。
- 结果（14/14）：import 16 模块 / scheduler JOBS=54 + silent_probe 在列 / 心跳 22s / 探针 alert=False 9/9 OK（五表双写全等 32476/403/2022/8356/2826，heartbeat 22s，grv 14.4h，news_export 73s，observability 存在）/ harness 31 PASS 0 GAP 0 FAIL / pg 行边界归一化（published_at="2026-08-13T08:26:43" UTC 文本）/ tracker(3) grv(207) daily(3) 真实数据 / obs_stats 25 evaluated+25 triggered+25 staging（恢复真实值）/ news_export.json 40 篇 updated 新鲜 / 无 dualwrite_gap 文件 / 当日 observability 产物存在。
- 容器日志近 3h 错误扫描：零（无 P2/P3 相关 traceback）。
- 小修正：run_probe(alert=False) 实际返回 (verdict, [(status, detail)...]) 元组而非 dict，验收判定已适配。
- 结论：E0-C P1-P3 全绿闭卷。建议观察窗口 12-24h 后再拍板 P4-P6（writer 切 PG-primary / 备份 / 删 3 库 + 2 僵尸）。

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
