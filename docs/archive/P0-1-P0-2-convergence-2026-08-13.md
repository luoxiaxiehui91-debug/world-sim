# P0-1 / P0-2 修复设计收敛报告
> worldsim-fix-2 · Round1 三路只读调研 + 主理人交叉质询
> 生成：2026-08-13 · 状态：设计收敛，**未落码**（守"仅调查不修复"铁律）
> 成员：fix-arch-2（P0-1 根因/治本）/ fix-domain-2（P0-1·P0-2 历史回填设计）/ fix-ops-2（P0-2 代码修复/全仓时区反模式/部署验证/静默探针）

---

## 一、事实层（三路独立实测，已交叉复核）

### P0-1 双写静默丢数
- **真实缺口 = 124 行 / 5 表**（纠正本日志 line200「93行/其他表差集0」初判；亦非审计初判 134）：
  - news.articles 缺 32201–32293 连续 **93** 行
  - news.scan_contexts 缺 id=399（**1** 行）
  - news.signal_episodes 缺 1989–1995（**7** 行）
  - news.article_categories 缺 article_id∈{32228,32246}（**2** 行，级联孤儿）
  - news.episode_articles 缺 **21** 行（episode_id 全∈1989–1995，其中 8 行 article_id∈32201–32293，级联孤儿）
- 五表**无强制 FK**（pg_constraint 查询 = NONE）。
- **根因锁定 `pg_write_collection.py`**（fix-arch-2 实测排除 `b0_migrate.backfill`：b0_migrate 单连接贯穿 + 遇错 re-raise，不可能静默掉 93 行）：
  - `pg_write_collection.py:40 _conn()` 每次 `psycopg.connect` 逐条建连（连接风暴）
  - `:72+` upsert 家族 `except print` 静默吞异常（丢数根因）
- **时序铁证**：articles 32201–32293 的 `ingested_at` 全 = `2026-08-13T04:05:00.629545+00:00`（微秒级同批，运行时双写路径，非 B0 拷贝）→ 04:05 实时批次因瞬时 PG 故障被连接风暴放大、被 except 静默吞 → 124 行掉。
- 源真值 = SQLite news.db（双写 Primary，完整死副本）。

### P0-2 forecast.forecasts 时区 +8h 漂移
- 120 行（id 长度 36，`prediction_logger.py:72 datetime.now()` 无 tz = 北京本地）被 PG timestamptz 当 UTC 存 → 相对真 UTC **+8h 污染**。
- 193 行（id 长度 8，`forecast_tracker.py` 真 UTC）正确不动。
- **方向锁定 −8h（铁证）**：len36 样例存 `06:36:31`、len8 样例存 `22:36:33`（同刻）→ −8h 后 len36=`22:36:31` 与 len8 对齐。真值只能由时区契约反推，外部日志非真值源。
- PG == SQLite 两库**一致地错**（都存同一个北京墙钟串），故"PG 比 SQLite 多8h"比法测不出——判据是 id 长度。

---

## 二、方案层（收敛结论）

### P0-1 治本（C3）
- 只改 `pg_write_collection.py` 内部：连接池复用 + 重试 + 失败计数 + ntfy 告警；**签名冻结，调用方零改动**。与 `b0_migrate.py` 零重叠。

### P0-1 历史回填（124 行）
- **推荐：新建独立脚本 `reconcile_backfill.py`**（复用 b0_migrate 的 `TABLES` 映射 + `INSERT...ON CONFLICT DO NOTHING` 模式），**不改迁移工具**（零回归、可 `--dry-run` 首跑）。fix-ops-2 拥有 b0_migrate 改动权但同意此更优解。
- 源 = SQLite news.db；幂等（DO NOTHING，rowcount=0 跳过已存在）；顺序父先于子防御；逐表 `_bak` + EXCEPT 对账（应全 0）。
- synthesis_log 10 行（B0 残留）排除出 P0-1，另立 ticket。

### P0-2 代码修复（7 个 P0 naive 站点，file:line）
| # | 文件:行 | 现状 | 落盘字段 |
|---|---------|------|----------|
| 1 | prediction_logger.py:72 | naive 北京 | predictions_log.created_at |
| 2 | forecast_tracker.py:139 | aware 截断 `[:19]` | forecasts.created_at |
| 3 | forecast_tracker.py:318 | 同 | actuals.labeled_at |
| 4 | forecast_tracker.py:331 | 同 | PG forecast.actuals.labeled_at |
| 5 | scheduler.py:256 | naive+截断 `[:19]` | scheduler_state.json.updated |
| 6 | fetch_firms.py:149 & :185 | naive 北京 | fetched_at（两处） |
| 7 | data_fetcher.py:123 | naive 北京 | cache._meta.last_update |

- 修复：`optim_config.py` 新增 `now_iso_utc()`(aware +00:00 不截断) / `now_iso_local()`(aware +08:00)；7 站改调；forecast_tracker 3 处删 `[:19]` 保留 tz。`contracts.py:145 _require_aware()` 印证 tz-aware 契约。
- 部署：核心代码 bind `/app` → rsync + `docker compose up -d`（restart 不重载 env/新 import）。

### P0-2 历史回填（120 行 −8h）
- **回填骨架**：账本表 `_tzfix_ledger` 存污染原值（幂等重跑）→ 分批 UPDATE ~30 id（`created_at = old - interval '8 hours'`）→ 金标准校验（修正前/后应差 8h，计数 0）。
- len8(193 行) WHERE 不命中，绝不动。用 SQL 算术，不依赖代码状态。

### P0-2 重放 loader 实测（关键去险）
- `forecast_tracker.py:_import_json_if_needed()`(:196) 读 predictions_log.json，但 `:206-209` 先 SELECT 已存在 id 则 `continue` 跳过，**不调 upsert_forecast** → 已导入行 PG created_at **不会被回灌覆盖**。
- 结论：**P0-2 回填直接 UPDATE PG 安全，冻结窗口为软预防（非硬阻塞）**。
- loader 随 `ForecastTracker()` 构造触发（run_macro_analysis.py:2919 嵌 morning/us_daily/china_daily，scheduler 周一至周五 07:30/20:00/20:15）；无 env 开关，暂停 = 3 job 名写入 scheduler control_pause.json 或 docker stop。

### 统一约定 + 全仓清扫
- created_at 统一 = UTC+Z（aware UTC）（fix-domain-2 定；**待拍板**：fetch/采集侧显示字段是否用 +08:00）。
- now_iso 与 C3 边界：C3 = pg_write_collection 内部；now_iso = 调用方值层。只要 P0-2 不改 pg_write_collection 签名，零冲突。
- 全仓时区反模式分级：P0×7 / P1×5 / P2。
- 静默失败探针（fix-ops-2）：双写行数差水位 / 心跳新鲜度 / 关键产物 mtime 超时，走 ntfy。

---

## 三、推荐执行序
1. 部署 P0-2 代码修复（bind-mount，rsync + up -d）。
2. （可选）暂停 3 个每日 job 保绝对干净 → 跑 P0-2 回填（−8h）→ 恢复。
3. P0-1：先 C3 治本（pg_write_collection 硬化）→ 再 `reconcile_backfill.py` 回填 124 行。
4. 部署全仓时区探针（ntfy）。

---

## 四、待用户拍板
1. **created_at 统一 UTC+Z，还是 fetch/采集侧（fetch_firms / data_fetcher / scheduler_state）保留 +08:00？**（建议统一 UTC+Z）
2. **P0-1 回填用新脚本 `reconcile_backfill.py`，还是改 `b0_migrate`？（推荐新脚本）**
3. **synthesis_log 10 行是否另立 ticket（不在 P0-1 范围）？**
4. **P0-2 冻结窗口是否启用（建议软预防即可，不必硬冻结）？**
5. **是否开修复阶段落码？（当前铁律 = 仅调查不修复，待你授权）**

---

## 五、证据索引（实测）
- P0-1 缺口：PG vs SQLite 集合差（五表 id 区间）；pg_constraint 无 FK。
- `pg_write_collection.py:40 _conn()` 逐条 connect；`:72+` upsert `except print`。
- `b0_migrate.py:392` 单 cursor 复用；`:409-411` except...raise（排除元凶）。
- SQLite 只读：articles 32201–32293 ingested_at 全 `04:05:00.629545Z`。
- `forecast.forecasts` PG length(id) 分布 (8,193)/(36,120)；len36 `06:36:31` vs len8 `22:36:33` 同刻。
- `forecast_tracker.py:196 _import_json_if_needed`；`:206-209` 已存在 id continue。
- 7 站 file:line 见上；`contracts.py:145 _require_aware()`。

---

## 六、实现就绪规格（三路最终交付，待授权落码）

> 以下为 fix-arch-2 / fix-domain-2 在 Round1 收尾交付给 fix-ops-2 的**冻结规格**，设计态已定，未获用户授权前 fix-ops-2 不得写入 NAS/git（主理人已下 HOLD）。

### 6.1 C3 双写硬化冻结契约（fix-arch-2 → fix-ops-2，仅 pg_write_collection.py）
**4 条不可妥协：**
1. **连接缓存复用**：去掉逐条 `_conn()`+`conn.close()`，改模块级单条缓存连接（`_PG_CONN`+锁），惰性建立、失效重连。
2. **有界重试+退避**：单次写入遇瞬时故障重试（默认 3 次，退避 0.1/0.3/0.7s），重试期间重连。
3. **失败计数+告警（绝不静默）**：耗尽重试后递增模块计数器 `_STATS` 并 `logging.error`（含 table/pk/sqlstate/err），替换裸 print；**绝不 raise 到调用方**；保留「连不上则跳过双写」契约（`_get_conn` 返回 None）。
4. **公开函数签名冻结**：所有 `upsert_*`/`update_*`/`delete_*` 签名不变 → 调用方零改动。

**核心机制**：`_get_conn()`（缓存+失效重连，重连带退避）；`_write(sql,params,*,table,pk_repr)->bool`（逐 write 独立事务 `with conn:` commit/rollback）；`_classify`+`_TRANSIENT`（仅 OperationalError/InterfaceError + 连接/死锁/停库类 sqlstate 重试，永久异常 Programming/Data/Integrity 不重试、记失败+告警）；`set_alert_hook(fn)`（默认 logging，零外部依赖）+ `get_pg_write_stats()` 供 ops 健康读；`_next_id` 改用缓存连接。
**实现落点**：~18 个 `_conn()` 点全部并入（`_PG_CONN/_PG_LOCK/_get_conn/_write/_classify/_TRANSIENT/_record_*/_STATS/set_alert_hook/get_pg_write_stats`）；news×5、forecast×4（含 upsert_forecast:223 / update_forecast_status:270）、tianji×6、delete/prune×2（:192/:522）及内部 helper（:196/:398/:524）改写走 `_write()`、删各自 `finally: conn.close()`。
**冻结不改**：SQL 文本与 `ON CONFLICT` 语义、表/列映射、search_path、连接参数、公开签名/返回值、不引新依赖。
**验收**：单测（注入瞬时/永久/断连）+ 集成（瞬时断连 auto-recover、`retry`>0、`fail`=0）+ 幂等重跑安全。fix-arch-2 保留 review 合规权。

### 6.2 P0-1 方案B WHERE 谓词（fix-domain-2 → fix-ops-2，拥有 b0_migrate 改动）
**5 表 PK 范围谓词（实测 src_read==insert==missing==124，无超集无遗漏，ON CONFLICT DO NOTHING 插数==where 读集==124 可硬校验）：**
| 表 | WHERE 谓词 | 缺行 |
|----|-----------|------|
| news.articles | `id BETWEEN 32201 AND 32293` | 93 |
| news.scan_contexts | `id = 399` | 1 |
| news.signal_episodes | `id BETWEEN 1989 AND 1995` | 7 |
| news.article_categories | `article_id IN (32228, 32246)` | 2 |
| news.episode_articles | `episode_id BETWEEN 1989 AND 1995` | 21 |

- **排除 tz 谓词**：P0-1 是行存在性缺口（124 行不在 PG），tz 由 norm_ts 写入时归一，与 where 无关；−8h 仅属 P0-2。
- **顺序**（父先子后，五表无 FK）：scan_contexts → signal_episodes → articles → article_categories → episode_articles。
- **验证断言**：每表 insert rowcount 对齐上表；回填后 PG==SQLite（articles 32345 / scan_contexts 400 / signal_episodes 2002 / episode_articles 8293 / article_categories 差集消除）。
- **落点**：ops 给 `b0_migrate.backfill(pg, only=None)` 加 `where: str|None` 形参拼源 SELECT（与 `only` 正交），保留 DO NOTHING 幂等与 norm_ts；或新建 `reconcile_backfill.py` 复用映射（二选一，待拍板点2）。fix-domain-2 按断言 review 实现与遗漏行。

### 6.3 三路零冲突复核结论
- C3 = pg_write_collection 内部（签名冻结）；P0-1 回填 = b0_migrate/新脚本（ops 拥有）；P0-2 now_iso = 调用方值层（optim_config.now_iso_utc/local + forecast_tracker 三处删 `[:19]` 保留 tz + prediction_logger:72→now_iso_utc + fetch_firms:149/:185 & data_fetcher:123→now_iso_local）。
- 只要 P0-2 不改 pg_write_collection 签名，三者零文件/零签名重叠。全仓时区反模式 P0×7 / P1×5 / P2。
