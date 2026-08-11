# 停用 crucix 方案论证 — R1 QA 验收标准与质量门禁（2026-08-10）

> **作者**：qa-review（世界推演系统 QA 负责人）
> **用途**：多 agent 论证"停用 crucix"第一轮产出之一。本文档只定义**验收标准与质量门禁**（红线 P0：不实施改动，全部核实为容器内只读）。
> **依据**：`crucix-dependency-analysis-2026-08-10.md`（依赖全景）＋ `b1_crucix_integration.md`（对照清单）＋ 天枢容器内代码/日志/数据实测。
> **格式**：验收标准采用 **EARS**（While/When/If + 系统 + 必须/应该 + 行为），每条附**可执行验证命令**。
> **核对基线**：2026-08-10 14:30-15:00 容器 `macro-scan-macro-scan-1` 实测。
> **R2 复核（2026-08-10 16:xx）**：nuke 处置变更（SafeCast 复刻供给，推翻"空输入"结论，AC-D1-04 重写、新增 AC-D1-05~09/RSK-8/9）；sdr 定案为独立增强项（不进 G0-G8，见 §5/§6）。

---

## 0. 实测基线（2026-08-10，验收判定的对照锚点）

> 所有验收标准的"通过/失败"都相对本节基线判定。**摘除前先跑一次基线采集**，再按 §3 门禁对比。

| # | 观测项 | 实测值（08-10） | 命令 |
|---|--------|----------------|------|
| B1 | news.db articles 总量 | 31,039 篇 / 24 源 | `docker exec macro-scan-macro-scan-1 python3 -c "import sqlite3;print(sqlite3.connect('/workspace/data/news.db').execute('SELECT COUNT(*) FROM articles').fetchone())"` |
| B2 | articles 日增量（ingested_at） | 07-25 起 230→736→…→07-31 440 / 08-01 348 / 08-02 349 / 08-03 587 / 08-04 603 / 08-05 645 / 08-06 577 / 08-07 530 / 08-08 318 / 08-09 311 / 08-10 114（采样时段截断） | `SELECT substr(ingested_at,1,10) d,COUNT(*) FROM articles WHERE ingested_at>='2026-07-25' GROUP BY d ORDER BY d` |
| B3 | scan_contexts / signal_episodes | 375 / 1,824 | 同上库 |
| B4 | 弱信号扫描频率 | 4 次/日（0000/0600/1200/1800） | scheduler_state.json `weak_signal`；scan.log 尾部有 synthesizer 完成记录 |
| B5 | D5 crucix 新闻拉取锚点 | scan.log 每次扫描 `[Crucix] 获取 50 篇文章（最近90天）` | `grep -n "Crucix" /var/log/macro-scan/scan.log \| tail` |
| B6 | D1 crucix 注入锚点 | morning.log `[OK] Crucix: gscpi=1.249401668, nuke=6, sdr=True`；gscpi 历史值 0.79 / 1.25 **均 < 1.5（当前无 gscpi_warn 触发样本）** | `grep -n "Crucix" /var/log/macro-scan/morning.log \| tail` |
| B7 | D3 叙事桶现状 | `[narrative_processor] 完成：新闻0条，JSON0条`；**ingest_from_news_db 因 articles 无 summary 列恒失败（现存 bug）**；crucix_* 桶当前已是空桶（死映射，news.db 无 source 含 crucix 的文章） | `tail /var/log/macro-scan/narrative_proc.log` |
| B8 | GRV 产出 | grv_latest.json updated 08-10T06:10：global_composite=60.3 / taiwan_strait=32.4 / sanctions_risk=82.8 / climate_risk=15.0 | `cat /workspace/data/grv_latest.json` |
| B9 | D6 climate job | **climate_signals.json 停于 08-01**；scheduler_state `climate.last_run_ts=null, last_ok=false`（08-01 后未成功运行）；firms_fire.json 08-10T09:08 更新但 `total_hotspots=0` | `cat /workspace/data/climate_signals.json`；`cat /workspace/data/firms_fire.json` |
| B10 | news_export 新鲜度 | news_export.json exported_at 08-10T07:05 | `cat /workspace/data/news_export.json \| head -c 300` |
| B11 | weak_signal_log 中 crucix 新闻源告警 | 存在 `source:"Crucix新闻"` 条目（关键词：信用风险 ratio=12.9 [警报]） | `grep -c "Crucix" /workspace/data/weak_signal_log.json` |

**基线要点**：
- 当前 gscpi（0.79/1.25）**未触发** gscpi_warn（>1.5）→ D2 验收不能依赖"实时触发样本"，须用桩/历史窗口重算（见 AC-D2）。
- D3 的 crucix_* 叙事桶**当前已为空**（summary bug + 死映射双重）→ 摘除后"空桶被显式接受"是现状延续，不是新增风险，但 GRV 数值漂移必须盯（见 AC-D3 / RSK-3）。
- D6 climate job **本身 08-01 后未运行**，摘除兜底前必须先修复 climate job 注册（前置门禁，见 §4 G0）。

---

## 1. 每依赖点摘除后的等价性验收标准（EARS）

> 通用前置：每条 AC 执行前，系统必须处于"该依赖点已按 arch-review 方案摘除、代码已部署、调度器已重启"状态；每条 AC 的判定按 §4 门禁汇总。

### D1 — data_fetcher `_crucix` 快照摘除（硬）

- **[AC-D1-01]** When data_fetcher 完成一次完整快照且 crucix 依赖已摘除，系统 **必须** 不再向 `CRUCIX_REMOTE_URL` 发起任何 HTTP 请求，且快照中不再出现 `_crucix` 键（或按方案改名为替代源键）。
  验证：`docker exec macro-scan-macro-scan-1 sh -c "grep -c 'Crucix' /var/log/macro-scan/morning.log"` → 摘除后连续 3 次运行计数为 0；`docker exec macro-scan-macro-scan-1 sh -c "grep -n 'GET.*3117' /var/log/macro-scan/morning.log | tail"` → 无匹配。

- **[AC-D1-02]** When 替代 gscpi 源（NY Fed，月度）已接入快照，系统 **必须** 以与旧 `_crucix.gscpi` 同构的 `{"name","date","value"}` 键形态填充 gscpi，且 `date` 不得早于快照日期 45 天（月度源可容忍一个发布滞后周期）。
  验证：morning.log `grep 'gscpi='`；或快照产物 grep `"gscpi"` 看 value/date 字段结构。**基线**：旧值 gscpi=1.249 / 0.79。

- **[AC-D1-03]** If 替代源拉取失败，系统 **必须** 在快照中填充 `gscpi: {}`（空 dict，与 `_crucix={}` 同语义），**应该** 打印 `[SKIP] gscpi:` 降级行，且 **必须** 不中断快照其余部分。
  验证：`grep 'gscpi' /var/log/macro-scan/morning.log | tail -5` 可见 `[SKIP]` 或 `[OK]`，且 `run_macro_analysis` 全流程 exit 0（`docker exec macro-scan-macro-scan-1 python3 run_macro_analysis.py --country us --dry-run` 或观察 morning job last_ok=true）。

- **[AC-D1-04]** When nuke 由 SafeCast 复刻供给、sdr 由 KiwiSDR 独立增强接入（data-review 定案，见 data 文档 §8/§9），data_fetcher 快照 **必须** 不再从 crucix API 拉取 nuke/sdr，此前 R1 草案的"nuke/sdr 空输入+降级登记"路径**作废**；sdr 为**独立增强项（非退场前置）**，其验收走 sdr 专项，**不进**退场门禁 G0-G8。
  验证：`grep -c 'Crucix' /var/log/macro-scan/morning.log`（D1 摘除后连续 3 次运行为 0）；`grep -rn '3117' /var/log/macro-scan/morning.log | tail`（无 GET）。

> **nuke 复刻供给（SafeCast）新增验收**（依据 data-review §9：无 key/CC0、6 站坐标表、`avgCPM>100⇒anom`、TLS 间歇错误需重试≥4 次、数据为历史归档均值）：
>
> - **[AC-D1-05]** When `fetch_safecast_nuke.py` 已接入调度且完成一次运行，系统 **必须** 产出 `data/safecast_nuke.json`，且其 `sites` 数组 **必须** 含且仅含 6 个 key（`zaporizhzhia / chernobyl / bushehr / yongbyon / fukushima / dimona`），每项含 `{site, key, avgCPM, n, anom, latest_captured_at}` 全字段。
>   验证：`docker exec macro-scan-macro-scan-1 python3 -c "import json; d=json.load(open('/workspace/data/safecast_nuke.json')); print([s['key'] for s in d['sites']]); print([(s['key'],s['avgCPM'],s['n'],s['anom'],s.get('latest_captured_at')) for s in d['sites']])"` → keys 恰为 6 站集合、无缺字段。
>
> - **[AC-D1-06]** When 快照消费 safecast 数据，系统 **必须** 保持 crucix 同构注入形态 `nuke: [{site, anom, cpm, n}]`（保键名，cpm=avgCPM），并 **必须** 以 `data/safecast_nuke.json` 为唯一 nuke 输入（不再读 crucix API）。
>   验证：morning.log `grep 'nuke=' | tail`；或快照 grep `"anom"`/`"cpm"` 字段结构比对基线 B6（crucix 旧形态 `nuke=6`）。
>
> - **[AC-D1-07]** When 复刻计算逻辑经容器内回放，系统 **必须** 复现 `anomaly = avgCPM > 100` 的判定语义；对 6 站基线读数回放 **必须** 与 crucix 实测 MATCH（zaporizhzhia 38.28 / chernobyl 123.96 anom=true / bushehr null n=0 / yongbyon null n=0 / fukushima 28.53 / dimona 29.52，data-review §9.2）。
>   验证：`docker exec macro-scan-macro-scan-1 python3 fetch_safecast_nuke.py && python3 -c "import json; d=json.load(open('/workspace/data/safecast_nuke.json')); c={s['key']:(s['avgCPM'],s['anom'],s['n']) for s in d['sites']}; print(c['chernobyl']); assert c['chernobyl'][1] is True"`（anom 判定可回归）。
>
> - **[AC-D1-08]** When safecast 输出写入，系统 **必须** 为每个站点填充 `latest_captured_at`（复刻自源测量时间戳），**必须** 不以该字段做"实时性"断言——数据为历史归档均值（captured_at 2016-2023，如 Chernobyl 2023-07），QA 只验字段存在与格式，不验新鲜度。
>   验证：`python3 -c "import json; d=json.load(open('/workspace/data/safecast_nuke.json')); print(all(s.get('latest_captured_at') for s in d['sites']))"` → True；并确认输出中任一站点 captured_at 非当日仍为通过（历史归档语义）。
>
> - **[AC-D1-09]** When api.safecast.org 出现间歇性 TLS 证书错误（实测约 50%，`ERR_TLS_CERT_ALTNAME_INVALID`），系统 **必须** 实现重试 ≥4 次（复刻方案 5 重试 + 1.5s 退避）使最终成功率≥99%；若某轮全部重试仍失败，系统 **必须** 打印显式降级日志（如 `[safecast] 拉取失败`）并输出空 `sites` 而非静默缺失。
>   验证：`grep -c 'safecast' /var/log/macro-scan/firms.log /var/log/macro-scan/*.log 2>/dev/null | grep -v ':0' | head`；观测窗内连续失败≥2 轮即告警（判据见 RSK-8）。

### D2 — regime_detector gscpi_warn 消费摘除（硬）

- **[AC-D2-01]** When 摘除 `_crucix.gscpi` 后，regime_detector **必须** 从替代 gscpi 键读取供应链压力值，且触发语义保持：**"value > 1.5 ⇒ signals += 1 且 gscpi_warn=true"不变**。
  验证：`docker exec macro-scan-macro-scan-1 python3 -c "import regime_detector; print(regime_detector.get_regime_info({'gscpi':{'value':1.6}}))"` → 期望 `gscpi_warn=True, stress_signals>=1`；同法传 1.4 → `gscpi_warn=False`。

- **[AC-D2-02]** When 替代源为月度粒度，系统 **必须** 在 gscpi_warn 判定中保留"最新可得值"语义（无实时 tick 时用最近月值），**应该** 在 `get_regime_info` 输出的 `gscpi_value/gscpi_date` 中透出数据时点，避免把"月度旧值"误当实时。
  验证：`python3 -c "from regime_detector import get_regime_info; import json; print(json.dumps(get_regime_info({}), ensure_ascii=False))"` 观察字段完整、不抛异常。

- **[AC-D2-03]** If 替代 gscpi 长期缺数（>60 天无新值），系统 **必须** 将 gscpi_warn 判定为不触发（信号静默丢失的已知接受面），且 **应该** 在 stress_signals 明细中标注 `gscpi=stale` 以便观测。
  验证：`grep 'gscpi' /var/log/macro-scan/morning.log /var/log/macro-scan/situation_detect.log | tail`。

- **[AC-D2-04]** While 不存在实时 gscpi_warn 触发样本（基线 B6 当前值<1.5），系统 **必须** 提供桩回归：以 gscpi∈{1.4,1.6,2.0,None} 构造 indicators，断言 warn 布尔与 signals 计数与旧实现一致（**旧实现留存为对照桩，不删除**）。
  验证：`python3 -c "from regime_detector import detect_regime; print([(v, detect_regime({'gscpi':{'value':v}}) ) for v in [1.4,1.6,2.0,None]])"` 比对旧行为记录（摘除前先行记录）。

### D3 — narrative_processor 4 映射摘除（硬）

> 基线 B7：crucix_* 桶当前已是空桶（summary bug 致 news 路径恒 0）。D3 验收重点是 **GRV 不崩 + 数值不漂移**，而非"桶有输入"。

- **[AC-D3-01]** When 摘除 crucix_gscpi/crucix_nuke/crucix_air/crucix_sdr 四个 SOURCE_MAP 条目后，系统 **必须** 在 `load_source_map()` 中不再返回任何 crucix_* 源映射，且 `narrative_processor.py` 完整运行不抛 KeyError。注：nuke 复刻（safecast）为 data_fetcher 层面供给；`crucix_nuke→taiwan_strait` 本就为未激活死映射（data-review §7.4），叙事桶无实际输入变化。
  验证：`docker exec macro-scan-macro-scan-1 python3 -c "import narrative_processor as n; m=n.load_source_map(); print([k for k in m if 'crucix' in k.lower()])"` → `[]`。
  - **[AC-D3-05（可选，arch-review 决定接线才生效）]** If arch-review 方案将 safecast/kiwisdr 数据源接入叙事 json_sources（如 `safecast_nuke.json → taiwan_strait`），系统 **必须** 使该源在 `load_source_map()` 中可见且摄取后 narrative_chunks 无 KeyError，**应该** 在 narrative_proc.log 中打印该源摄取计数。
  验证：`tail /var/log/macro-scan/narrative_proc.log`（JSON 摄取计数含新源）；`python3 -c "import narrative_processor as n; print([k for k in n.load_source_map() if 'safecast' in k or 'kiwisdr' in k])"` 非空。

- **[AC-D3-02]** When 三个受影响 GRV 维度（global_composite / taiwan_strait / sanctions_risk）失去 crucix 输入（实为空桶延续），系统 **必须** 在 grv_update 后产出完整 grv_latest.json（11+ 维度全有值、`updated` 时间戳为当日），**必须** 不因缺桶报错中止。
  验证：`docker exec macro-scan-macro-scan-1 sh -c "cat /workspace/data/grv_latest.json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len([k for k in d if k not in d.get(\"_derived_meta\",{}) and not k.startswith(\"_\")]), d.get(\"updated\"))'"` → 维度数 ≥ 11 且 updated 为当日。

- **[AC-D3-03]** If GRV 某受影响维度与其他源的贡献发生抵消/叠加变化，系统 **必须** 在 grv.log 中可观测数值漂移，且 **应该** 由 daily_narrative/慢变量链路自然传导（非空桶硬错误）。判定以 **相对摘除前 7 日均值的偏差 ≤ ±15%** 为阈值（阈值可商榷，见 RSK-3）。
  验证：`docker exec macro-scan-macro-scan-1 python3 -c "import json; d=[json.loads(l) for l in open('/workspace/data/grv_history.jsonl')]; import statistics; import datetime; recent=[x for x in d if str(x.get('updated','')).startswith('2026-08')]; print({k: round(statistics.mean([x.get(k,0) for x in recent]),1) for k in ['global_composite','taiwan_strait','sanctions_risk']})"` 记录摘除前基线。

- **[AC-D3-04]** While narrative_proc 的 news.db 路径因 summary 列缺失恒 0（现存 bug，**非本次摘除引入**），系统 **必须** 将该问题记为独立缺陷（跟随摘除顺手修复或单独立项），摘除验收 **不得** 以"新闻0条"为通过依据——通过依据为 JSON 路径摄取（sanctions_risk/energy/disaster/hdx/climate JSON）与 GRV 连续性。
  验证：`tail /var/log/macro-scan/narrative_proc.log` 中 `JSON<N>条`，N≥1 且摘除前后数量级一致。

### D4 — news_db 归档 crucix 文章摘除（软）

- **[AC-D4-01]** When 摘除 crucix 新闻归档路径后，news.db articles 表 **必须** 仍持续入库（RSS 三源独立），日增量 **必须** ≥ 基线 B2 的 70% 分位（即 08-04~08-10 的 ~530 篇/日；可放宽到 ≥ 300 篇/日作为下限）。
  验证：`SELECT substr(ingested_at,1,10) d,COUNT(*) FROM articles WHERE ingested_at>=date('now','-7 day') GROUP BY d`。

- **[AC-D4-02]** When crucix 摘除后，系统 **必须** 在归档路径中不再出现任何由 `fetch_crucix_news` 产生的写入（无 crucix source 标记，按 scan.log 的 `[Crucix] 获取` 日志行数=0 判定），且 **必须** 保持 url/content_hash 去重幂等不报错。
  验证：`grep -c "Crucix" /var/log/macro-scan/scan.log` 连续 4 次扫描为 0；news_db.prune_old_articles 正常执行（`grep prune /var/log/macro-scan/scan.log | tail`）。

- **[AC-D4-03]** If 摘除后 articles 日增量跌破下限（<300/日），系统 **必须** 在 QA 回归窗内判定为"候选源容量不足"，**应该** 触发 RSS 源扩充评估，而非直接回滚 crucix。

### D5 — scan_weak_signals 新闻频率（软）

- **[AC-D5-01]** When 摘除 `fetch_crucix_news(days=90)` 后，弱信号扫描 **必须** 以 GDELT/RSS 独立源完成新闻频率告警，scan.log 中 "Crucix地缘(GDELT降级)" 兜底分支 **必须** 不再出现。
  验证：`grep -nE "Crucix|GDELT降级" /var/log/macro-scan/scan.log | tail -5` → 仅剩 GDELT 主路径，无 crucix 引用。

- **[AC-D5-02]** When 摘除后，系统 **必须** 仍产出 weak_signal_log.json 条目（≥ 基线 B11 的 50% 频次），且新告警条目 source 字段不再出现 `"Crucix新闻"`。
  验证：`grep -c "Crucix新闻" /workspace/data/weak_signal_log.json` → 摘除后新增条目为 0（历史条目保留）。

- **[AC-D5-03]** If GDELT 源故障导致新闻频率维度空窗，系统 **必须** 显式降级（打印 `[GDELT] 降级` 类日志）而非静默 0 告警，QA 回归窗内允许该维度缺失 ≤ 连续 4 次扫描。
  验证：`grep -c "GDELT" /var/log/macro-scan/scan.log | tail`。

- **[AC-D5-04]** While scan.log 的 `[Crucix] 获取 50 篇文章（最近90天）` 为 D5 摘除前的唯一观测锚点，系统 **必须** 在摘除后将该行替换为等价的独立源拉取日志行（如 `[News] 获取 N 篇`），供自动化断言。
  验证：`grep -cE "获取 .* 篇文章" /var/log/macro-scan/scan.log` 摘除后 >0。

### D6 — fetch_climate_signals 火点兜底摘除（软，现状最弱）

> 基线 B9：climate job 08-01 后未成功运行；firms_fire.json 直连产出 total_hotspots=0。D6 摘除验收 **受前置门禁 G0 阻塞**。

- **[AC-D6-01]** When climate job 恢复运行且 crucix thermal 兜底已摘除，fetch_climate_signals **必须** 只消费 `firms_fire.json`（fetch_firms 直连产物），**必须** 不再向 crucix API 请求 thermal。
  验证：`docker exec macro-scan-macro-scan-1 python3 fetch_climate_signals.py` 输出行 `[climate] FIRMS(直连):` 且无 `[climate] FIRMS(crucix):`；`grep '3117' /var/log/macro-scan/climate.log` → 无。

- **[AC-D6-02]** When FIRMS 直连成功产出非 0 火点，climate_signals.json 的 `firms.total_hotspots` **必须** 与 firms_fire.json 一致且 `date` 为当日；firms_fire.json 文件 mtime **必须** 为当日（fetch_firms 日档 0908）。
  验证：`docker exec macro-scan-macro-scan-1 python3 -c "import json; a=json.load(open('/workspace/data/climate_signals.json'))['firms']; b=json.load(open('/workspace/data/firms_fire.json')); print(a['total_hotspots']==b['total_hotspots'], a['date'])"` → `True True`。

- **[AC-D6-03]** If FIRMS 直连返回 0（含"真无火点"与"下载失败"两种可能），系统 **必须** 区分两者：firms.log 显示 `0 行`（CSV 下载成功但无记录）与显示 `超时/下载失败`（异常）**不得** 同值处理；QA 判定 **应该** 以 firms.log 的 fetch 成功行数为准，而非单纯看 total_hotspots。
  验证：`tail /var/log/macro-scan/firms.log` 检查有无异常栈。

- **[AC-D6-04]** While climate job 08-01 后未运行（B9），系统 **必须** 将"恢复 climate job 运行"列为摘除 D6 的**前置**，未恢复前 **不得** 判定 D6 验收，避免把"job 未跑"误报为"摘除故障"。

---

## 2. 整体门禁清单（crucix 停用前的最终门禁，全过才可停用）

> 执行方式：在容器内逐条跑命令，全部 PASS 才允许停用 crucix（或先摘除全部依赖点、停用容器前再跑一次）。

| 门禁 | 判定规则 | 验证命令（容器内） |
|------|---------|-------------------|
| **G0** | climate job 已恢复运行（08-01 后首次成功），否则 D6 验收无效 | `docker exec macro-scan-macro-scan-1 sh -c "grep -n 'Job started: fetch_climate_signals' /var/log/macro-scan/climate.log \| tail -3"` 最近一次为当日 |
| **G1** | 连续 **5 天**替代源数据完整（gscpi 有值且 date 滞后 ≤45 天；nuke 由 `data/safecast_nuke.json` 供给，6 站结构完整、fetched_at 当日、无连续拉取失败≥2 轮）。**sdr 为独立增强项，不进本门禁**（G0-G8 均不含 sdr，避免范围混淆） | `grep 'gscpi' /var/log/macro-scan/morning.log \| tail -5` 5 行均为 `[OK]`；`python3 -c "import json; d=json.load(open('/workspace/data/safecast_nuke.json')); print(len(d['sites']), d['fetched_at'])"` 6 站且当日 |
| **G2** | gscpi_warn 有触发样本（桩回归通过：1.6→True / 1.4→False / None→False） | `python3 -c "from regime_detector import detect_regime; print([detect_regime({'gscpi':{'value':v}})[1] for v in [1.6,1.4,None]])"` 输出含 1 与 0 的差异序列（如 [1,0,0] 或含 +1 计数差异） |
| **G3** | news 日增量达标：最近 5 天每日 ≥300 篇（RSS 三源独立容量验证） | `sqlite3 news.db "SELECT substr(ingested_at,1,10),COUNT(*) FROM articles WHERE ingested_at>=date('now','-5 day') GROUP BY 1"`（容器无 sqlite3 则用 python3 -c） |
| **G4** | 无 _crucix 相关降级日志：morning.log 连续 5 次运行无 `[SKIP] Crucix:` 且无 `GET 3117` | `grep -cE "SKIP.*Crucix|3117" /var/log/macro-scan/morning.log` → 0 |
| **G5** | GRV 数值漂移可控：grv_latest.json 三维度相对摘除前 7 日均值偏差 ≤ ±15% 且 updated 为当日 | `python3 -c "import json; print(json.load(open('/workspace/data/grv_latest.json')).get('updated'))"` |
| **G6** | weak_signal_log 连续 4 次扫描新增条目仍产出（≥ 基线频次 50%），无 `Crucix新闻` 新源 | `grep -c '"source": "Crucix新闻"' /workspace/data/weak_signal_log.json` 新条目 0 |
| **G7** | climate_signals.json 连续 **3 天** 当日产出（firms 字段当日 date），且 FIRMS 直连 fetch 成功（允许 total=0，但不允许异常栈） | `cat /workspace/data/climate_signals.json` 看 `firms.date`；`tail /var/log/macro-scan/firms.log` 无 Traceback |
| **G8** | 全链路健康：scheduler_state.json 中 weak_signal / morning / grv_update / narrative_proc / news / firms 全部 `last_ok=true` | `docker exec macro-scan-macro-scan-1 python3 -c "import json; s=json.load(open('/workspace/data/scheduler_state.json')); [print(k, s[k].get('last_ok'), s[k].get('last_run_ts')) for k in ['weak_signal','morning','grv_update','narrative_proc','news','firms']]"` |

> 门禁判定约定：G0 为硬前置（不满足不开测）；G1-G8 任一 FAIL → 停用**阻塞**，转 arch-review/data-review 定位；全部 PASS → 允许进入"观察期停用"（§3）。

---

## 3. 回归方案（停用后 24h / 7d 观察窗监控指标）

> 停用 crucix 容器/摘除最后依赖点后，按以下频次采集指标。24h 为快速回滚窗，7d 为稳态确认窗。

| 指标 | 采集频次 | 告警阈值（超阈值→回滚/人工介入） | 命令 |
|------|---------|-------------------------------|------|
| M1 弱信号扫描日志 scan.log 新鲜度 | 每 6h（每轮扫描后） | 连续 2 轮无新 `Job started: scan_weak_signals` | `docker exec macro-scan-macro-scan-1 sh -c "grep -n 'Job started: scan_weak_signals' /var/log/macro-scan/scan.log \| tail -3"` |
| M2 data_fetcher 运行日志 morning.log | 每日 08:00 | 出现 `[SKIP] gscpi:` 或 `Traceback` 或 exit≠0 | `grep -nE "SKIP.*gscpi|Traceback|FATAL" /var/log/macro-scan/morning.log \| tail` |
| M3 news_export.json 新鲜度 | 每日 | exported_at 早于 2 天前 | `stat -c %y /workspace/data/news_export.json`（容器内） |
| M4 articles 日增量 | 每日 | 单日 < 300 | §G3 查询 |
| M5 grv_latest.json updated | 每日 | updated 非当日 | `python3 -c "import json;print(json.load(open('/workspace/data/grv_latest.json'))['updated'])"` |
| M6 weak_signal_log 新增条目数 | 每日 | 当日新增为 0 | `grep -c '"date": "2026-08-XX"' /workspace/data/weak_signal_log.json` |
| M7 climate_signals.json firms.date | 每日 | 非当日且 firms.log 有异常 | §G7 |
| M8 出站请求：容器内无任何 192.168.31.108:3117 请求 | 每日 | 命中一次即告警 | `docker exec macro-scan-macro-scan-1 sh -c "grep -rn '3117' /var/log/macro-scan/ \| tail"`（停用后应为空） |
| M9 safecast_nuke.json 产出（nuke 替代源，R2 新增） | 每日（每轮 safecast job 后） | fetched_at 非当日 或 连续 ≥2 轮拉取失败 或 6 站缺站 | `python3 -c "import json; d=json.load(open('/workspace/data/safecast_nuke.json')); print(d['fetched_at'], [s['key'] for s in d['sites']])"` |

**观察窗结论规则**：
- 24h 窗：M1/M2/M8 任一告警 → 立即回滚（devops-review 预案），QA 记录为"摘除实现缺陷"。
- 7d 窗：M3-M7 任一告警 → 按 RSK 分类定位（替代源问题 vs 实现问题），不自动回滚，先隔离归因；M9（safecast nuke）告警 → 按 RSK-8 归因（重试≤4 次失败=实现问题；重试达标仍连续失败=替代源问题），同样不自动回滚。

---

## 4. 风险登记（验收点可能 fail 的判定与归因）

| ID | 风险 | 可能 FAIL 的验收点 | 判定"替代源问题 vs 摘除实现问题" |
|----|------|-------------------|-------------------------------|
| RSK-1 | **gscpi 当前无 >1.5 触发样本**（基线 B6=1.249/0.79），"触发回归"只能靠桩 | AC-D2-04 / G2 | **实现问题**：桩回归 1.6→False 或 None 抛异常 ⇒ 判定实现缺陷。**替代源问题**：桩回归全过但真实月度值长期 <1.5 ⇒ 属数据语义漂移（阈值>1.5 是否仍适用月度粒度），需 data-review 重定阈值，**非回滚项** |
| RSK-2 | **news 日增量下降无法归因 crucix**（crucix 无独立 source 标记，D4） | AC-D4-01 / G3 / M4 | 用 scan.log `[Crucix] 获取` 行数=0 确认摘除生效后，若日增量 <300 ⇒ **替代源问题**（RSS 容量不足），查 news.log 三源 fetch 成功率；若三源成功但总量仍低 ⇒ 判定**源容量结构性下降**，需扩容评估 |
| RSK-3 | **GRV 数值漂移误判**：crucix_* 桶摘除前后实际均为空（B7），漂移若发生来自其他链路而非摘除 | AC-D3-03 / G5 | 摘除前后 grv_history.jsonl 同窗口对比；漂移 >15% 时**先查非 crucix 输入**（opensanctions/akshare/gdelt 是否同日变化）归因；无法归因到其他源时定为"摘除暴露的既有方差"，需加长基线窗 |
| RSK-4 | **D6 climate job 未运行被误报为摘除故障**（B9 现存） | AC-D6-* / G0 / G7 | **判据：看 scheduler_state.climate.last_run_ts**。last_run_ts=null ⇒ 是既有 job 注册问题（非摘除引入）；last_run_ts=当日且 firms 为 0 ⇒ 再看 firms.log 区分"0 行"（真无火点，可接受）vs"下载失败"（替代源问题，fetch_firms 慢下载待修） |
| RSK-5 | **D5 GDELT 兜底语义变化**：原"GDELT 不可用时 crucix 兜底"摘除后失去兜底 | AC-D5-03 / M1 | 摘除后 GDELT 故障窗内新闻频率告警缺失 ≤4 次扫描为**接受面**；若 GDELT 本身 24h 内无数据 ⇒ **替代源问题**（GDELT 源不稳定），非实现缺陷 |
| RSK-6 | **弱信号告警数量骤降被误判为"扫描坏了"**（crucix 新闻频率告警消失，如信用风险 12.9 类条目） | AC-D5-02 / M6 | 看 scan.log synthesizer 完成行 + weak_signal_log 中 FRED/GDELT 源条目数；FRED/GDELT 条目正常而仅 crucix 类消失 ⇒ **预期行为**（摘除生效）；全部条目消失 ⇒ 实现问题 |
| RSK-7 | **回归窗内依赖残留**：某进程仍持有 CRUCIX_REMOTE_URL 配置（optim_config.py L110 常量） | AC-D1-01 / M8 / G4 | 容器内全局 grep `3117` 命中 ⇒ **实现问题**（漏摘），按 G4 计数归零为通过标准 |
| RSK-8 | **SafeCast TLS 间歇错误（约 50% ERR_TLS_CERT_ALTNAME_INVALID）导致 nuke 拉取失败**：重试不足则 6 站偶发空输出 | AC-D1-05/09 / G1 | **判据：看失败日志形态**。日志为 `ERR_TLS_CERT_ALTNAME_INVALID` 且重试 ≤4 次 ⇒ **实现问题**（重试逻辑不达标，data-review 复刻 5 重试+1.5s 退避为标准）；重试 ≥5 次仍失败（观测窗连续 ≥2 轮）⇒ **替代源问题**（api.safecast.org 多 IP 证书问题恶化），降级为 nuke 缺省并登记，非回滚项 |
| RSK-9 | **nuke"实时告警"误读**：SafeCast 数据为历史归档均值（captured_at 2016-2023，如 Chernobyl 123.96 实为 2023-07 数据），Chernobyl anom=true 是长期背景非突发 | AC-D1-07/08 | **判定为预期行为**（历史归档语义，data-review §9.2 注）；任何人若以"当日新鲜度"或"实时告警"断言 nuke ⇒ 判据无效，须改用"latest_captured_at 字段存在 + 结构正确"标准。**不构成回滚理由** |

---

## 5. 交付边界与未决问题

- **本文件只读核实**：未改动任何代码/配置/数据（红线 P0 遵守）。所有命令为容器内只读或 dry-run。
- **R2 复核变更（2026-08-10 16:xx）**：
  - nuke 处置变更：data-review §9 挖出 crucix nuke = SafeCast 公开 API（CC0/无 key/直连 200），6 站复刻 MATCH×6 → 原"nuke 空输入+降级登记"作废，本文件 AC-D1-04 重写、新增 AC-D1-05~09（SafeCast 供给验收），G1 更新，新增 RSK-8/9。
  - sdr 已定案接入（KiwiSDR）：为**独立增强项，非退场前置**，已确认**不进**退场验收门禁 G0-G8（G1 措辞已排除 sdr），其验收走 sdr 专项（data-review §8），本文件仅在 §6 给观察性建议。
- **需 arch-review 澄清**：① safecast 数据是否接入叙事映射（决定 AC-D3-05 是否生效）；② fetch_safecast_nuke.py 调度频率（15-60min，对齐 crucix 15min sweep 或并入低频批）。
- **需 data-review 澄清**：① gscpi 月度粒度下阈值 >1.5 是否保留；② firms_fire.json 产出 0 的"真无火点 vs 下载失败"历史分布，支撑 RSK-4。
- **跟随项**：narrative_processor 的 `no such column: summary` bug（B7）与 climate job 未运行（B9）为**现存缺陷**，建议在摘除实施时顺带修复，否则 D3/D6 验收基线不干净。

---

## 6. 独立增强项观察性建议（sdr / KiwiSDR，不进退场门禁）

> team-lead 指示：sdr 为独立增强项，仅需确认不进入 G0-G8 + 可选观察建议。以下为**建议性**指标，不阻塞退场。

- **[OB-SDR-01]** When `fetch_kiwisdr.py` 接入并日频运行后，系统 **应该** 产出 `data/sdr_summary.json` 且结构含 `{total, online, zones}`（对齐 crucix sdr 结构），`total` 与源目录实测（839 台接收器）偏差 **应该** ≤ ±10%（KiwiSDR 目录日更 1-2 次）。
  验证：`python3 -c "import json; d=json.load(open('/workspace/data/sdr_summary.json')); print(d.get('total'), d.get('online'), len(d.get('zones',[])))"`。
- **[OB-SDR-02]** When sdr 接入 narrative 弱信号（json_sources 接线）后，系统 **应该** 在连续 24h 观察窗内监测 weak_signal_log.json 是否产生 sdr/KiwiSDR 来源的告警条目；若出现 **Z-score 密度突增**（≥3 倍基线），**应该** 人工核对是否由"接收器在线数波动"（839 台动态上下线）触发，而非真实信号变化。
  验证：`grep -c 'KiwiSDR\|sdr' /workspace/data/weak_signal_log.json` 对比接入前基线。
- **[OB-SDR-03]** While sdr 为独立增强，若其接入导致 narrative_proc 或弱信号扫描异常（非 crucix 退场引入），系统 **应该** 按独立缺陷处理（回退 fetch_kiwisdr 接线），**不得** 计入退场验收 FAIL。
