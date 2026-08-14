# STATUS — world-sim 实时交接文件（新 session 冷启动第一入口）

## 新 session 冷启动（3 分钟，防迷路）

> 任何新会话先读本区块，再读 `README.md`（结构/部署导航）与 `.workbuddy/memory/MEMORY.md`（长期红线/部署拓扑）。最后更新：2026-08-14 14:10 GMT+8。

**项目是什么**：world-sim 世界推演系统——个人内部宏观推演系统（非商业产品）。逻辑 5 层：天枢（观测采集）→ 天璇（仿真，17 Agent）→ 天玑（验证）→ 玉衡（权重，未运转）→ 开阳（展示）；横切 crucix 信号总线（AGPL，**已退场 2026-08-12 G1 停容器**）+ 摇光 SRE。

**项目位置**（防迷路，全部关键路径）：
- **`S:\world-sim` = 源码真相（git 工作树）**：`\\192.168.31.108\software\world-sim`（SMB 挂载）= NAS `/vol2/1000/software/world-sim`，**与 GitHub `luoxiaxiehui91-debug/world-sim` 同一 git 树**。改源码 → 在此编辑 → `git commit/push` 推 GitHub（push 走代理 `http://192.168.31.108:7890`）。**SMB 读取可靠（08-11 实测：STATUS.md / grv_latest.json 经 SMB 读出的 sha256 与 NAS 磁盘一致）**；唯一陷阱是「两条 macro-scan 目录」——运行时数据在仓库外 `S:\macro-scan\data`，勿与仓库内死副本 `S:\world-sim\macro-scan\data` 混淆。
- WorkBuddy 工作区（`C:\Users\luoxi\WorkBuddy\世界推演系统\`）= AI 编辑副本 / 过时镜像，**非真相**；源码修订以 `S:\world-sim` 为准，避免双副本漂移。
- NAS 运行区：天枢热挂载 `/vol2/1000/software/macro-scan/核心代码/`（改 .py 即生效，scheduler.py 需 docker restart）；开阳 `/vol2/1000/software/kaiyang/dist`；crucix `/vol2/1000/software/Crucix/`（**已退场 08-12 停容器，禁抄源码 AGPL，仅历史参考）
- 容器：`macro-scan-macro-scan-1`（天枢）/ `macro-sim`（天璇，COPY 模式）/ `macro-scan-tianji-1`（天玑）/ `macro-scan-kaiyang-1`（开阳 :8080）
- SSH：`ssh nas`（**必须 Git 自带 ssh，Windows OpenSSH 已坏**）；容器内部操作（docker exec / 读运行时数据极强实时性）走 SSH——非因 SMB 不可靠（SMB 本身可靠，仅容器刚写完即刻读时有 ~10s 客户端缓存滞后）

**当前主线（08-11）**：
1. **crucix 退场（已全闭环）**——论证+实施 14 commit 全闭合（eff0d8c 为止）；**G0（08-12）受控切断验证 PASS** + **D1(gascpi) wiring 完成（08-12，纯 NY Fed CSV 源，删 :3117 分支，commit f30bd2d）**；nuke/sdr/vix 经核实下游零消费无需 wiring；**G1（08-12 14:01）`docker stop crucix-crucix-1` 已执行（Exited 137）**，crucix 退场全链路收口（WP-3.x 废弃容器已停）
2. **开阳补全**——v1.9.0→v1.10.8（报告中心/FCI/风险面板/news_geo 事件图层/视觉 crucix 化/同地点聚合），news_geo 验收观察窗（08-13 06:35 自动化判定）
3. 挂起待拍板：**航班走廊线（air 图层 B 完整版）**
4. **worldsim-pg 统一采集库（08-12 晚 DB-first 地基，主线新增）**：独立 PostgreSQL 容器（`pgvector/pgvector:pg16`，端口 127.0.0.1:5434，vol2 bind `/vol2/1000/software/worldsim-pg/pgdata`），与 macro-scan / 天玑 跨 `worldsim_default` 网互联（A0 完成）。macro-scan 重建 v8 装 psycopg（A0.5 完成）。news.db 时区抢救（C1 完成：published_at 22017 行虚假冲突归零）。weight_matrix.py 补入 git 树 + 修 3 处 utcnow（C 方案完成）。部署脚本 deploy-pg.sh 修爆 + 固化 pg_hba（C 完成）。**锁定顺序**：A0→A0.5→C1→A1-min→B1(双写证通 ✅)→C0(加权 ✅)→**B0(迁 news.db+forecast ✅)**→D0(迁 chroma→pgvector ✅)→**E0(应用整合收尾 ✅：A 双写 worldsim-pg 证通 + B 退役 ChromaDB)**。详见「当前状态」worldsim-pg 段。

5. **全量审计 + 双 P0 修复（08-13，已闭环）**：worldsim-audit 4 路 × 3 round 全量审计产出 3 P0 / 4 P1 / 12 P2（登记表 `docs/decisions/audit-2026-08-13-risk-register.md`）。**P0-1 双写静默丢数**（C3 硬化 + 124 行回填 + 五表零差集 + `silent_failure_probe.py` I120 兜底）、**P0-2 forecast 时区 +8h**（7 站点改 `now_iso_utc()` + 120 行 −8h 回填，铁证样本对齐至 2 秒内）、**P0-3 自动推演停摆**（commit 2d7bffa）**三条全部 RESOLVED**，容器内实测验收 10/10 PASS。**→ E0-C 读路径重写已启动并全闭环（P1-P6：PG-only + SQLite 退役，见下条第 6 条）。**
7. **采集实时化（08-14，50% 水位×源更新速度双约束）**：commodity_yahoo 日频→I15（+ change_pct 基准错位修复 + spark5 迷你走势）；fetch_news 主源改 **GDELT DOC 2.0**（免费无 key）+ **MarketAux**（key 已配，双源并行），日频→I30（MarketAux 48/日=48% 贴线）；**7 源批量提频**（OpenSky 日→I30 航班实时 6242 架 / 地震 I5 / 灾害 I15 / 加密 I10=43% / 加密冗余 I5 / 防务 RSS I60 / 能源 I60）；前端新闻双轨（news_all 全量 + news_export 风险流）、conflict 图层接入 news_geo、新闻风险卡片 top5；探针扩至 26 项（check_news_risk 2h/4h + check_fred_lag + check_sqlite_gone 零残留断言）。
6. **E0-C 读路径重写 + PG-only（08-13 晚，P1-P6 全闭环）**：`pg_read.py` 只读层（行边界归一化 datetime→UTC 文本）→ 14 个 reader 全切 PG（双读校验台 `verify_reads_e0c.py` 31/0/0）→ synthesis_log 25 行对账 + 双写补全 → news_db 写路径 PG 主写（`WORLDSIM_SQLITE_OFF` 开关）→ **P5 切换生效**（运行区 compose 注入 `WORLDSIM_SQLITE_OFF=1` + `up -d`，探针 PG-only 模式 VERDICT OK，直接激活 + 真实采集验证 PG 写 / SQLite 冻结，删除脚本 `delete_sqlite_e0c.sh` 门禁 dry-run 4/4 全绿）。**P6 删 4 SQLite 已于 08-14 08:39 执行**（commit 1ba002a，快照 `e0c-p6-20260814-083910`，删后观察无复生 / 探针 OK）。

**必读顺序**：本文件 → README.md → .workbuddy/memory/MEMORY.md（红线）→ 按需 macro-sim/docs/calib/（校准评审权威）；详细待办见下文「待做/已知遗留」节。

---

## 当前状态

**08-14：采集实时化 + 前端图层接通（50% 水位×源更新速度双约束）**：commodity_yahoo 日频→I15（08-14 07:15）+ 修 change_pct 基准错位（Yahoo closes 对 A股最近 10 天全 None → 改上次良值推进，csi300=-0.57% 等全对）+ spark5 迷你走势；market_quotes 删幽灵 MORTGAGE30US + spark5 透传；fetch_news 主源 GDELT DOC 2.0（免费无 key，5s 限速 + 5000/天；OR 关键词括号、timespan=1d 防旧闻、seendate 解析）+ MarketAux key 配置（`S:\KEY\MarketAux-API.txt`，40 字符 key 第一行 + 邮箱第二行，注入运行区 compose），日频→**I30**（MarketAux 48/日≈48% 贴 50% 上限，15min=96% 破线禁）；**7 源提频**：OpenSky 日→I30（48/日=12%，airtraffic flights_in_air=6242 实时）、地震 I15→I5、灾害 I30→I15、加密 I15→I10（4320/月=43%）、加密冗余 I15→I5、防务 RSS 日→I60、能源日→I60；慢源（FRED/FX ECB 日更 16:00/FAO 月）维持（提频无意义）；前端：新闻面板双轨 C 方案（news_all.json 全量 100 篇含未分类 + news_export 风险流）、conflict 图层接入 news_geo（51→14 条真地缘冲突，美国枪击 38 条国内治安过滤 + intensity 相对烈度校准）、新闻风险卡片 top5 标题；GDELT 校准器（天玑 tianji_calibrator 9 维 P95 反推 + tone_base -7.97，scan/GRV 统一读 gdelt_calib.json）；探针扩至 **26 项**（check_news_risk 内容 updated 2h/4h、check_fred_lag 13 序列、check_sqlite_gone 零残留、check_backup 备份新鲜）；采集频率矩阵同步（07-31 建，08-14 更新 news + 7 源）。**air 图层收口（15:15）**：2D 只画航向箭头（PointShape 'arrow'，图例同步）不画圆点圈 + `UNCAPPED_LAYERS` 豁免 2000 护栏全量渲染（feed 实测 6182 点 / track 100%）；3D 球保持圆点（方向随相机失真）。commit `70e5f4e`，kaiyang v1.10.9。**air 图层重构（16:25，用户拍板）**：实时航班点覆盖盲区（OpenSky ADS-B 非洲/中国/俄罗斯内陆接收器稀疏，实测俄罗斯上空仅 11 点）→ air 改为**静态全球航线网**（新 fetcher `fetch_airroutes`：OpenFlights 500 条主要航线，实测中国枢纽 96 条/非洲 42 条无盲区，scheduler 0950 日档）；实时航班降级为独立 **aircraft** 子图层（默认关、desc 标注盲区、天蓝 #38bdf8、UNCAPPED 全量）；前端复用既有 RiskArc 弧渲染（零新渲染代码）；327 tests 全绿；kaiyang v1.11.0。**P2 续接 sdr + thermal（17:10）**：sdr 图层纯前端接入（sdr_summary.json 851 接收器，active→ok/offline→灰，非风险语义）；thermal 图层后端 fetch_firms 修复 + 输出 1° 网格聚合 hotspots（**date 修复：结束日期今天→昨天，FIRMS NRT 对今天返回 0 行——长期潜伏 bug 早上必 0**；152978 火点 → 4031 网格点，中国 321/非洲 1045/南美 553 格）；UNCAPPED + thermal；337 tests 全绿；kaiyang v1.11.1。**thermal 等级筛选防卡顿（19:5x）**：用户反馈「太占资源卡住了」→ 等级 = count 分档（极高≥500/高≥100/中≥50），`MIN_THERMAL_COUNT=50` 滤掉零星火点格（4031→527 格，87% 降量）；UNCAPPED 移除 thermal（护栏兜底）；338 tests 全绿；kaiyang v1.11.2。**2D 渲染防卡顿（20:0x）**：用户反馈「还是卡」→ ①tooltip mousemove rAF 节流（8000+ 点监听合并每帧 1 次 setTooltip）；②thermal/sdr 改 dot 简化渲染（省外环+光晕 2 元素/点）；338 tests 全绿；kaiyang v1.11.3。**2D aircraft 降采样护栏（20:4x）**：用户反馈「平面图非常卡」→ `downsampleLayer` flat 模式 aircraft 6182→1500（stride 均匀抽样），globe 3D 保持全量（WebGL 可扛）；341 tests 全绿；kaiyang v1.11.4。**P2 续接 space + P1-4 修复（22:4x）**：space 图层接入（Next Spaceflight 发射记录 130 条含 pad 坐标，需 UA 头，scheduler 0705 日档；air/thermal 教训复用 value null + 中性「太空」）；**P1-4 核告警孤儿链修复**（safecast_nuke 落盘但无消费者 → fetch_safecast_nuke 加 _alert_anomalies：anom 状态翻转 → ntfy 推送 + nuke_alert_state.json 去重，实测 chernobyl anom=true 告警送达）；health WHO RSS 404 / maritime 免费源覆盖受限暂缓；346 tests 全绿；kaiyang v1.11.8。

**08-13 晚：E0-C 读路径重写（P1-P6 全闭环，PG-only 生效）**：P1 `pg_read.py` 只读层（_Row 行边界归一化 datetime→UTC 文本 / Decimal→float / bool→int；DML row_factory 兼容）。P2 14 reader 切 PG（news_exporter/ntfy/geo_risk/grv/daily_narrative/detector/tracker/synth/obs/web/forecast_tracker/tianji_db/narrative_processor），双读校验台 31 PASS / 0 GAP / 0 FAIL。P3 synthesis_log 对账 25 行回填 + `upsert_synthesis_log` 双写（read-after-write 断裂 catch）。P4 news_db 写路径 PG 主写（`_next_id` 生成 id / 查重走 PG / get_trigger_titles 残留读切 PG）。P5 切换生效（compose `WORLDSIM_SQLITE_OFF=1` + `up -d` + `.sqlite_frozen_at` marker；探针 PG-only 分支防误报；直接激活测试 PG 写 / SQLite 冻结；真实采集 scan_weak_signals PG ctx 402→403）。全量验收 14/14 PASS，容器日志零错误。备份 4 db → `backups/e0c-p4-20260813/`。**P6 删库已于 08-14 08:39 执行**（commit 1ba002a，快照 `e0c-p6-20260814-083910`）：删 4 db + 观察无复生 / 探针 OK。
- **08-13：全量审计 + P0-1 / P0-2 双 P0 闭环（重型 SOP 三路设计 → 用户拍板 → 主理人落码 → 容器内实测）**：
- **审计**：worldsim-audit 4 路 × 3 round → 3 P0 / 4 P1 / 12 P2，登记表 `docs/decisions/audit-2026-08-13-risk-register.md`（含完整修复实录）。审计同时**推翻 3 条旧假设**：sim_trigger「单文件 bind 断链」实为目录挂载正常、真因是代码回归；news.content「仍 TEXT」两库均无该列（RESOLVED）；「时钟偏快 2h」三方 UTC 差 <1s（误判）。
- **P0-1 双写静默丢数 RESOLVED**：`pg_write_collection.py` C3 硬化（连接缓存复用 + 有界重试 3 次退避 + 15 个 transient sqlstate 分类 + 失败计数留痕 + `set_alert_hook`/`get_pg_write_stats`；**绝不静默、绝不 raise、绝不阻断 SQLite 主写**）；新建 `reconcile_backfill.py` 回填 124 行 / 5 表（articles 93 + episode_articles 21 + signal_episodes 7 + article_categories 2 + scan_contexts 1），dry-run 先验源行数再实跑，逐表 inserted==expected；**五表 count + 双向主键差集全零，VERDICT PASS**；回填后 scheduler 自然新增 +84 篇 articles（→32429）**PG 仍与 SQLite 精确相等**，证明 C3 在真实写入下同步。`synthesis_log` 10 行差另立 ticket（非 news 五表口径）。
- **P0-2 forecast 时区 +8h RESOLVED**：根因 = `prediction_logger.py:72` 用 `datetime.now()` 生成 **naive 北京时钟数值**，PG session `TimeZone=Etc/UTC` 按 UTC 收下 → 存储时刻**晚 8h**；`forecast_tracker.py` 三处 `.isoformat()[:19]` 截断 `+00:00` 把 aware 降级 naive。修复：`optim_config.py` 新增 `now_iso_utc()`/`now_iso_local()`，**7 站点全改**（prediction_logger:72 / forecast_tracker:139,318,331 / scheduler:256 / fetch_firms:149,185 / data_fetcher:123），`now_iso_utc()` 调用 8 处、遗留 naive+`[:19]` **0 处**；`tzfix.sql` 单事务 + 快照表 `forecast._forecasts_pre` + 账本 `forecast._tzfix_ledger`，仅 `length(id)=36` 族 `−8h`（len8 族本就正确不动），`UPDATE 120` / `mismatch=0`。**铁证**：同刻配对 len36 `4a3a24a7` vs len8 `110553b1` 修复前差 16h（06:36:31 vs 22:36:33）→ 修复后差 **2 秒**（22:36:31.444686 vs 22:36:33）。
- **静默失败探针（新增）**：`silent_failure_probe.py` 注册 JOBS `("silent_probe","I120",...)` 每 2 小时兜底。**设计转向（重要）**：C3 的 `_STATS`/`set_alert_hook` 是**进程内**内存计数，而双写发生在 scheduler 派生的各子进程（fetch_news / scan_weak_signals / news_exporter …），主进程注册 hook **覆盖不到任何真实写入路径** → 探针改用**状态差而非事件流**（直接比对 PG↔SQLite 行数/主键差集）。三类检查：dualwrite（差 ≤3 INFO 容忍写入竞态 / >3 CRIT，快路径先比 count 不等才拉差集，缺口落 `data/dualwrite_gap.json`）、heartbeat（`.scheduler_heartbeat` >10min WARN / >20min CRIT）、artifacts（`grv_latest.json` >30h、`news_export.json` >2h、当日 `observability_*.json`）。告警走 ntfy。**告警通道经注入式验证真实送达**（monkeypatch 阈值强制进 CRIT 分支 → `ntfy 已推送`），不接受未验证的告警通道。
- **验收**：容器内 `final_acceptance.py` **10/10 PASS**（C3 接口 / now_iso 契约 / 7 站点零遗留 / 根因机械证明 / 120 行回填 / 铁证样本 / 双轨时间域 / P0-1 五表零差集 / 探针注册 JOBS=54 / 心跳 29s）。
- **备份留存**：`/vol2/1000/software/worldsim-pg/backups/p0fix-20260813/`（7 个 .bak，已移出 git 树）；PG 侧 `forecast._forecasts_pre` + `forecast._tzfix_ledger` 保留可回滚。
- **事件记录**：fix-ops-2 违背 HOLD 越权把 C3 落磁盘（未重启容器、留备份），用户拍板**追认保留**，主理人复核后统一 rsync + restart 加载。**教训同 audit-arch：检测/设计阶段 agent 禁改运行容器与源码。**

**08-11：crucix 退场实施全部闭合（观察窗中）+ 开阳大规模补全（v1.9.0→v1.10.8）+ 时区统一修复**：
- **crucix 退场实施（08-10 晚启动，全 commit 闭合至 ab8b1f7）**：G0 climate 恢复（a65c998）/ gscpi fetcher+调度（100e544/b29c8da，NY Fed xlsx 尾行 0.805）/ ADR-08 死代码删（a8ffb34；注：本项目为单人研究系统，架构决策以 commit 形式记录于 git 历史，未单列 ADR 文档）/ climate 兜底删+firms 加固（7ac6b48）/ safecast nuke 6 站 MATCH（611cc6b）/ kiwisdr 接线（c38a2b0）/ 双调度注册（260a173）/ RSS-only articles 断供排除（5bba73e）/ air 删+ gscpi_warn None 防护（65666b8）/ firms 补偿重试（77f6711）/ 时区修复 10 处显式后缀（a7c6e42）
- **观察窗（已闭合）**：gscpi 05:32 / kiwisdr 06:02 / climate 09:10 已首跑；**G0 判 08-12 / G1 判 08-12** → crucix 退场收口（08-12）：G0 切断验证 PASS + D1(gascpi) 已切 NY Fed CSV 唯一源（删 :3117 分支，commit f30bd2d），nuke/sdr/vix 实测下游零消费无需 wiring；**G1 已于 08-12 14:01 执行（`docker stop crucix-crucix-1` → Exited 137），停后复核天枢无 :3117 连接日志**（新闻自采 RSS 不受 crucix 影响）
- **开阳补全（v1.9.0→v1.10.8）**：第一批报告中心（45 份）+ FCI/GSCPI 面板 + 风险信号面板 + dashboard 停生成（2dff1a6）+ news_export 提频 I15（3c30723）；**M-1 news_geo 事件图层**（8e6aaf3/a86fbbe/ddb17b0：137B 空壳→527 事件，CAMEO event_code 落盘，XSS 双保险）→ 视觉 crucix 化（a63bd65）→ 缩放半补偿（da464f5）→ 事件弹框+原文链接（84464dd）→ 同新闻合并+unknown 清零（c4659f4）→ 视觉降噪 Top-80 标签（a3b0561）→ **同地点聚合 v1.10.8（ab8b1f7：628→208 点，一城一点+计数徽标）**
- **news_geo 验收**：数据侧 9/9 + qa 16 PASS + XSS 实测不可注入；48h 判定 08-13 06:35 自动化（unknown<5%）；浏览器复核 17 项待主理人
- **事故治本（37dda5a）**：开阳部署触发嵌套挂载断链（mv dist 换 inode → html/data 子挂载丢失 + 删 dist/data 容器起不来）→ data 挂载独立到 `/usr/share/nginx/data` + nginx alias（嵌套挂载红线升级，见坑节）
- 时区：全系统落盘时间戳统一显式后缀（UTC→Z / 本地→+08:00），前端 parseTs 契约无后缀=北京时间，10 处修复 + OPEN 3 条（news.db 展示层 / grv-history 边界 / 纯日期键）

**08-12：全量审计收口（neat-freak 六面对账，08-11~08-12）**：文档滞后 11 处修订（版本标签口径/预测计数自相矛盾/目录结构/权威性口径/双 OPEN 册根索引/ADR 注释/sim_log 死代码定性/sim_trigger P0 过时降级/SOP 引用/package.json 版本）；清残留 F13-F18（kaiyang-wave2/STATUS.bak/fci-recovery/F17 垃圾/天枢 weight_matrix 副本已删；HANDOVER.md 因 AGENTS.md 引用保留；天枢停摆脚本留待人工判）；SMB 红线纠正（读可靠，陷阱=两条 macro-scan 目录）。报告 `全量审计报告-20260812.md`。

**08-12 晚：worldsim-pg 统一采集库主线（DB-first 地基）**：
- **A0 起容器**：`worldsim-pg`（pgvector/pgvector:pg16，127.0.0.1:5434），建 `worldsim_admin`(superuser)/`worldsim_app`(读写)/`worldsim_ro`(只读)三角色 + `REVOKE ALL ON DATABASE worldsim FROM PUBLIC`；macro-scan / 天玑跨 `worldsim_default` 网互联（compose external 持久化）；备份脚本 `backup-pg.sh`(pg_dump -Fc 14天) + crontab `0 4 * * *` + 真实 restore 演练通过。
- **A0.5 psycopg**：macro-scan 重建 `v8`（`requirements.txt` 加 `psycopg[binary]>=3.1.0`，v7 留作回滚）；v8 容器内 `worldsim_app` 角色建表/INSERT/SELECT/commit/DROP 写验证通过。顺带补 A0 漏配的 `pg_hba.conf` 跨网 ACL（172.29.0.0/16 + SIGHUP reload）。
- **C1 时区抢救**：`news_db._normalize_dt` 重写（RFC822/ISO 统一规整 UTC aware；naive 当北京+8 解释）；
  10 处 `datetime.utcnow()`→`datetime.now(timezone.utc)`（narrative/slow/tianji）；新增 `migrate_news_published_at.py`（已执行 `updated=32092 quarantined=0`，aware 重验 `conflict=0/32092`）。根因反转：非「截断垃圾」，而是 published_at 时区语义缺失（22017/32092 行 naive 当 BJ 转 UTC 后冲突归零）。
- **C 方案三件**：`weight_matrix.py`（玉衡，原游离运行区）补入 git 树 + 修 3 处 utcnow；`deploy-pg.sh` 实测全坏（变量空串/for 循环字面多行/DO 分隔符乱码 `79413`）重写 + 幂等固化 pg_hba 172.29.0.0/16 ACL。6 文件(py_compile/单测/sha 同步)全 PASS，commit+push GitHub。
- **A1-min 完成（21:5x）**：`indicators` 宽表已建（11 列，`UNIQUE(indicator_key, as_of, horizon, model_ver, data_vintage)` 对应 `contracts.py:to_row`，`worldsim_app` 建表+授权）；实测验证通过（INSERT 示例行 OK + 五元组重复插入被 UNIQUE 拒 + 11 列类型正确 `created_at=timestamptz`）+ 测试行已清理（remaining=0）。DDL 版本化 `sql/01_indicators.sql` 已 commit+push GitHub。为 B1 双写证通前置就绪。
- **B1 双写证通（22:1x）**：fetch_fred_history 增加 worldsim-pg.indicators 旁路双写——新增 `核心代码/pg_write_indicators.py`（`upsert_indicator_rows(rows)->(inserted,updated)`，单条 `unnest` 数组 + `ON CONFLICT(indicator_key,as_of,horizon,model_ver,data_vintage) DO UPDATE ... RETURNING (xmax=0)` 逐行统计 insert/update；连接/psycopg/环境变量/行数据异常全 try 捕获返 (0,0)，绝不阻断 CSV 落库）；`fetch_fred_history.fetch_and_save` 在 `save_series` 后转 indicators 行 dict 调 upsert，`created_at` 用 aware UTC（时区契约）；`scheduler.py/fetcher_base.py/contracts.py/news_db.py` 等核心文件未触碰（独占令牌纪律）。commit 735da92（2 files, +208/-1）+ push GitHub + 运行区 cp 同步（容器热挂载即时生效）。主理人独立验收（容器内真实 PG）：合成 3 行首跑 (3,0)/二跑 (0,3) 幂等无误翻倍；真实 DGS10（probit 输入）端到端 `pg_written=(16136,0)`，PG 实查 16136 = CSV 16136 行（CSV 未被破坏，范围 1962~2026-08-10）；测试行已清理回 0。坑：psycopg3 `executemany(returning=True)` 仅返末条 → 改 unnest 单语句；多 untyped 数组 `unnest(unknown)` 歧义 → 各参数显式 `::type[]`；运行时需 `WORLDSIM_APP_PW` 经 `docker exec -e` 注入（connection.env 已固化 NAS `/vol2/1000/software/worldsim-pg/`）。下一步转 C0（加权，见下条）。
- **C0 加权证通（08-13 08:1x）**：玉衡 weight_matrix 接线验证——新增 `sql/02_indicator_weights.sql`（grain(source_id,target_type)，IF NOT EXISTS + CHECK(weight∈[0.05,5.0]) + target 索引）+ `核心代码/c0_compute_weights.py`（一次性脚本，不接 scheduler）。从 indicators(fred-%) 读 49 FRED 序列，逆滚动波动率/变异系数派生权重，文档化种子 dict 映射 GRV 11 维（49 序列全覆盖、0 uncategorized），同 target_type 归一+clip[0.05,5.0]+round5，双写 indicator_weights(PG 权威)+grv_weights.yaml weights 子树（只动 weights、先备份、round5）+JSON 备份；unnest+ON CONFLICT(source_id,target_type) 幂等；撞键防护 GPR/GSCPI 加 `fred.` 前缀防污染既有 source 键；连接/psycopg/环境变量异常全 try 捕获返 (0,0) 不阻断。commit 87abae3（2 files +681）+ push GitHub + 运行区 cp 同步（sha256 与 git 树一致）。主理人独立验收（容器内真实 PG，重跑复现）：backfill 196217 行→派生 49 行；RUN1 (49,0)/幂等 RUN2 (0,49) count 稳 49；7 个 target_type 的 get_weights_for_target 读回与 PG 一致（mism=0）；yaml weights==PG（49 行 mism=0）；权重 upsert 零干扰 indicators（仅 backfill 补数）；测试数据已清理（DROP 表+TRUNCATE indicators 回 0+yaml 还原）。实时推演消费为后续工作。下一步 B0（迁 news.db+forecast）。
- **B0 news.db+forecast 迁移证通（08-13 10:0x）**：新增 `核心代码/b0_migrate.py`（469 行，自包含：DDL/apply-schema/backfill/verify/dump-sql/subcommand）+ `sql/03_b0_schema.sql`（212 行权威 DDL 版本化）。三源 SQLite → 三 schema PG（**真相**：原计划 tianji.db 为 0 字节空文件，5 个 tianji 表实挂 `forecast_tracker.db` —— 文件名误导但 tianji 特征明确）：`news.*`(7 表, 46825 行)/`forecast.*`(3 表, 313 行)/`tianji.*`(5 表, 430 行)，合计 15 表 47569 行（含 5 个 0 行表）。DDL 类型对齐：`BIGSERIAL` PK/`DOUBLE PRECISION`/`TIMESTAMPTZ`/`BYTEA`(embedding)+各 schema `AUTHORIZATION worldsim_app` + `GRANT ALL`。backfill 用 PG `ON CONFLICT(pk) DO NOTHING + RETURNING(pk)` + sqlite cursor reorder（先 COUNT 再 SELECT 全文，不混 sqlite 同 cursor 迭代前 count）。BLOB→bytea 用 `psycopg.Binary(v)`。TZ 契约：sqlite naive ISO 当 BJ+8 → UTC aware → PG `+00:00`；aware 直传。commit（提交时记录 sha）+ push GitHub + 运行区 cp 同步 + 容器 `/app/b0_migrate.py` 同步 cp 到位。主理人独立验收（容器内真实 PG，按子集重跑复现）：(1) 三个 tianji 简单表（reasoning_trace 3/weight_update_log 0/narrative_density_flags 1）首跑过；(2) tianji.narrative_chunks 419 行 BYTEA round-trip 成功；(3) 15 表全量 backfill DONE inserted=0 skipped=47529（幂等）；(4) verify 全 15 表 PG vs sqlite 行数完全一致（398/32200/2807/1988/8251/0/1142 + 313/0/0 + 7/3/0/419/1）；(5) TZ 抽查 8 列均 `tzinfo=zoneinfo.ZoneInfo(key='Etc/UTC')`；(6) debug 日志清理（`>>> loop start` + `row#{ix}`）→ 本地 py_compile + 容器内 py_compile 双过 → 幂等重跑（0 inserted/47529 skipped + verify 全 OK）。过渡 sqlite 直读 (`news_db/forecast_db/tianji_db`) 暂保留为只读伴读，下游读路径迁移留 D0/E0 推进时择机改写或退役。下一步 D0（迁 chroma）。
- **D0 chroma→pgvector 迁移证通（08-13）**：新增 `sql/04_d0_schema.sql`（rag schema + `rag.embeddings` 单表 PK(collection_name,id) + HNSW cosine 索引 `vector_cosine_ops` m=16/ef_construction=64）+ `核心代码/d0_migrate_rag.py`（自包含 apply-schema/backfill/verify/dump-sql/subcommand）+ `核心代码/rag_engine.py`（RAG_BACKEND 双读改造）+ `docs/d0-ops.md`（运维手册）。chroma `macro_kb` 4156 emb（dim=1024 bge-m3, cosine）→ pgvector `vector(1024)` HNSW。Step0 `CREATE EXTENSION vector` 由 `worldsim_admin` 装（worldsim_app 非超户、pgvector 非 trusted → InsufficientPrivilege，容器免密转 admin 成功，v0.8.2）。backfill `ON CONFLICT(collection_name,id) DO UPDATE` 幂等（4156/0）；verify 闸门 count=4156 + top-10 重叠率 jaccard=1.0000（≥0.98 PASS；top-5 因余弦等价距离 tie 重排仅 0.90~0.93 作参考，非误差 C5）。`rag_engine.py`：`_build_index_pg` 单事务 `TRUNCATE rag.embeddings WHERE collection_name=%s`+INSERT 循环（修旧 del-then-build 新残 bug C6）；`_rag_query_pg` 用 `<=>` 距离 + `ORDER BY ... , id` 稳定排序；`_RAG_FAIL_COUNT` 计数不静默降级（修 C9 盲点）；chroma 回滚路径实测可用（RAG_BACKEND=chroma）。commit f88a7fb + push GitHub + 运行区 cp 同步（sha256 与 git 树一致）。主理人独立验收：pg 读路径返 5 正确 chunk；坏连接 `_RAG_FAIL_COUNT` 递增返 []；chroma.sqlite3 chmod 444 只读观察期（9/1 月重建跑通后删三件套：chroma 文件+chromadb 依赖+RAG_BACKEND 开关）。下一步 E0（应用整合收尾）。**E0-B（08-13）ChromaDB 提前退役**：用户选择不等 9/1 观察期，rag_engine/build_rag_index 删全部 chroma 分支 + RAG_BACKEND 开关，requirements 移除 chromadb，chroma.sqlite3 已备份（data/chroma_db_backup_2026-08-13.sqlite3）并删除（36MB）。

**08-04：6 异常全量修复闭环**（P0-A/B/C/D + data-freshness + P1，验收 13/13，question 归档，活跃 9→3）。

**08-05：开阳全面实时化 + 时间审计 6 问题闭环**：
- 刷新频率：market_quotes 0630→**I15** + 前端 60s 轮询（ccbda94）
- 时区：parseTs 确定性解析 + fmtRelative + 数据层 UTC→北京（dbdbd48/35abcfc）
- 控制台分组/折叠 + 新闻倒序 + 信号流点击展开 + nginx no-cache（a20738e/60b0882/d1a1b39/fc411a3）
- 时间审计 6 问题（manifest 孤儿/news 假时刻/FCI 闸/sim_trigger 字段/news_geo 契约/freshness 语义）三批次修复（902c439/1b36800/2a3370c）
- 流程补漏：VERSION bump + kaiyang CHANGELOG + npm test 297 全绿（3c00420）

**08-06：治理四方向论证定稿 + 天玑/天璇修复**：
- 治理四方向全 pass（单一真源+记忆降级 / 文档分治 / 验证命令注册表 / 部署通道收敛），docs/governance/ 五份文档落地中（commit a63d866）
- 天玑 trigger 链路修复（scheduler tianji_trigger 每日 09:42，原 dom=1 笔误仅每月 1 号空转，commit 6ba35ab）；天玑 config 挂载改 rw + prior.yaml 生成
- deploy.sh 两处 rsync --delete 实修（commit 18d3962，CHANGELOG 曾声称已移除=假）；FCI 产物日更恢复；crucix 已于 08-12 退场（G0 切断验证 + D1 gscpi 改 NY Fed CSV + G1 停容器），此前 08-06 实测仍活跃独立运行 30/30（当时属独立运行过渡期共存）

**08-07~08-10：天璇校准引擎 R4a→R4h 八轮治理（主线，见下节 R4 系列）**：
- 版本线：v2.0.37（R4g 收尾，引擎回 R4e 基线+归因测量修复）→ v2.0.38（R4h ③ sentiment 写者，CACHE 12/v2031）→ v2.0.39（R4h ② vix 豁免治理，CACHE 13/v2032）→ **v2.0.40（R4h ① ease_ok 方向闸收编，CACHE 14/v2033）**
- 08-10 R4h ① 结案：**收编 EASE 治理**（EASE wrong 8→0 真实有效）；credit 回池/p̂ 0.4894/S2 0.636 不通过、挂起转 silence 治理；方案预期 0.5729 系假复现（A3 soul 缺失），见下节红线

- 版本现状：macro-scan **v3.8.17**（镜像标签 `macro-scan:v7`）/ macro-sim **v2.0.40**（CACHE 14 / ARTIFACT v2033）/ macro-ji v1.0.0（容器无 VERSION 文件）/ kaiyang **v1.10.8**（镜像 `nginx:alpine`）。文本版本为仓库语义版本，镜像标签为部署标签，二者口径不同不冲突。

## R4 系列（天璇校准引擎治理主线，08-07→08-10）

> 评审文档：`calib-*-review-终局裁决-*.md` / `calib-R4h-评审简报-2026-08-09.md` 于工作区根（本地 WorkBuddy）与 `docs/calib/`（repo 侧镜像，08-10 同步）；spec 变更登记 `macro-sim/docs/r4g-spec-change-registry.md`（变更 1-8）。

| 轮次 | 结果 | 版本 |
|------|------|------|
| R4a | grv 触发线回退 0.8 + S 类归因 + 验收基建 | — |
| R4b | info_delay 2→1（act 0.265→0.388，暴露方向冲突） | — |
| R4c | dead 判定 m_v_active + A2 方向对齐设计（credit 入池 p̂ 0.477） | — |
| R4d | 方向闸 + 方向 EASE + vix>1.0 豁免（consistency 0.643 达标，silence 回退） | — |
| R4e | grv 0.4→0.6 + ease-block 归因（credit 入池 p̂ 0.515） | — |
| R4f | 三案否决（+0.001 伪影 / activation 无效 / 结构性不可达），零改动 | — |
| R4g | 归因修正（rate_limit 高估 +0.264 / rule_hold 幻影 / tighten_signal_false 死代码实锤）+ 冷却修复证伪回滚 | v2.0.37 |
| R4h ③ | A2 EASE 写 sentiment（+0.08×m 对称 TIGHTEN），CACHE 12 | v2.0.38 |
| R4h ② | vix 豁免治理（回归 0.80/0.20 + bleed 上限），CACHE 13 | v2.0.39 |
| R4h ① | ease_ok 方向闸（financial.py）+ act_prob 0.70→0.76 + cap 19→17，**收编 EASE 治理**，CACHE 14 | **v2.0.40** |

**R4h ① 验收结论（2026-08-10，容器口径三方一致）**：EASE wrong 8→0（rate 1.000）/ M6 13≤17 / M4 flip 0 / 断言 130 全绿（+10）/ 反作弊 5/5 / P0 sentiment 未命中 → **收编**；credit 回池（silence 0.531>0.50）、p̂ 0.4894<0.55、S2 0.636>0.60 → **挂起转 silence 治理**（seed123 0.633 / n_active 9 为残余弱项；0.80 参数无收益 M6 20 更差）。commits：e636c0c（引擎）/ 08e1a65（假复现更正）/ bd4bb31（裁决登记）。

## 部署信息

- 容器四枚：`macro-scan-macro-scan-1`（天枢，热挂载，:8899 WebUI / :8900 Control API）/ `macro-sim`（天璇，COPY）/ `macro-scan-tianji-1`（天玑，COPY，无端口，healthy）/ `macro-scan-kaiyang-1`（开阳，nginx :8080）
- 天玑触发链路：天枢 scheduler `tianji_trigger` job（每日 09:42）写 `/workspace/data/tianji_trigger.json` → 天玑 watchdog 轮询执行验证
- Git repo：`/vol2/1000/software/world-sim/` → GitHub `luoxiaxiehui91-debug/world-sim`，push 走代理 `http://192.168.31.108:7890`（代理会抖，失败重试或 `git -c http.proxy=` 直连）
- compose 已挂载 entrypoint.sh（镜像旧版无 control_server 启动行——重建容器必须保持此挂载）
- kaiyang nginx 缓存策略：index.html no-cache + /assets/ immutable（nginx/default.conf 挂载）

## 时间戳契约（08-05 沉淀，防重踩）

> **天枢写端**：容器本地时间（TZ=Asia/Shanghai）无后缀 或 `astimezone()` 带 +08:00 后缀；**禁止 `utcnow`/`timezone.utc` 写无后缀时间戳**（08-05 已修 market_quotes/control_server/fred manifest/news_export 四处）。
> **前端读端**：parseTs 无后缀补 +08:00、纯日期补 T00:00:00+08:00（防 UTC 午夜假时刻）；useFeed 只读顶层 `updated`（后端写 updated 而非 exported_at/generated_at）。
> **freshness 语义**：fred_freshness `status=ok` 仅=本地vs源一致性；新鲜度看 `fresh`/`lag_days` 字段（DCOILWTICO 现 fresh=False lag=9）。

## 待做 / 已知遗留

1. **R4h ① 挂起项（转 silence 治理立项）**：credit 回池（silence 0.531>0.50）、p̂ 过 partial 0.55、S2≤0.60 三项未达成。seed123（silence 0.633 / n_active 9<12）为容器残余弱项；已证 0.80 参数无收益、方案预期 0.5729 为假复现（勿再引用）。qa/data 已表态可参与下一轮方案评审与验收预置
2. **news_geo 空渲染 ✅ 已解决（08-11 M-1）**：路线 A 落地——news_geo.json 由 fetch_gdelt_geo.py I15 派生（137B→527 事件），旧 NER 链退役；验收 48h 判定 08-13 自动化。**浏览器复核 17 项待主理人**（事件点渲染/性能/XSS/时间戳/图例/降级/聚合观感等，清单见 arg-map-qa-acceptance）
3. **FRED 上游源停更（观察中）**：DCOILWTICO 卡 07-27 / ICSA 07-25（经代理实测，非本地问题）；fresh=False 已暴露 + ntfy 告警覆盖；BAA10Y/DTWEXBGS 卡 07-31 根因待查
4. **航班走廊线（air 图层）待拍板**：P2 路线图已排（CRUCIX_UPGRADE air=空域活动三角+航迹弧）；天枢 airtraffic_opensky 日跑已有全球快照（8529 架），画 crucix 式区域走廊需天枢按战略区域加工（增量）；建议 news_geo 验收后做 B 完整版
5. **天璇 deploy.sh macro-sim 目标内部 ssh 密码验证失败**：重建改手动 docker build（脚本本身无 bug，NAS 自身 ssh 配置问题）
6. **天玑 weight_update_log 仍 0 为正常**：MIN_TRIGGER_N=8，当前 predictions=7（孤儿段实测 forecasts=304 / narrative_chunks=347），链路已验证可跑
7. **工作区历史遗留 M**：多为 CRLF 幻影，判脏须 `git diff --ignore-all-space`
8. **天璇 sim_log（死代码）**：`sim_log.py` 的 `insert_run` writer 全仓 0 调用（08-12 审计），空库为预期、非功能损坏，已从 P0 降级（见孤儿段 #4）；天璇 /app/output 校准产物随重建丢失（已知）
9. **时区 OPEN 3 条**：news.db ingested_at/last_scan 展示层未统一（web_server /status）；web_server.py:530 /grv-history 本地↔UTC 混合比较边界差 8h；gdelt_history.date 纯日期键维持 UTC 语义（低优先）
10. **firms 09:08 连续 0 行需人工介入（08-11 晨检发现）**：补偿重试（77f6711）未救回；19:08 手动触发 39993 热点=源活 → 疑 09:08 调度时段源端/网络持续异常，建议改调度时间或查该时段出网（qa midcheck P1#2 延伸）
11. **worldsim-pg 统一采集库后续（08-12 晚主线，顺序锁定）**：A0/A0.5/C1→C(方案)/A1-min/B1/C0/B0/D0 已完成 ✅（见「当前状态」worldsim-pg 段）。**E0 应用整合收尾 ✅（08-13）**：A 双写证通——新增 `pg_write_collection.py` 旁路双写（news/forecast/tianji 三 schema），挂钩 news_db/forecast_tracker/tianji_db/narrative_processor 落库后非阻塞双写；B chroma 退役——rag_engine/build_rag_index 删全部 chroma 分支 + RAG_BACKEND 开关、requirements 移除 chromadb、chroma.sqlite3 备份后删除（观察窗提前，用户选择不等 9/1）。D0 验收 top-10 重叠率 1.0000 通过。**C 读路径改写（天枢 SQLite reader → pg）+ 删 SQLite 文件（P6 已于 08-14 08:39 执行，commit 1ba002a）**。E0 代码已 commit+push（b0/news-forecast-pg, f574812）。**E0-A 已激活实测通过（08-13 13:xx，TSX@nas 直连容器）**：rsync 同步运行区 + 运行区 docker-compose.yml 注入 WORLDSIM_APP_PW + `docker compose up -d` 重建；探针 `pg.upsert_news_scan_context` 实测 `before=0 after_insert=1 OK`，4 写入模块 import 全过，调度器干净重启，双写链路已活，下次真实采集自然增量 pg。

## 关键决策

- 天玑 = 独立容器（macro-ji），不并入天璇；forecast_tracker.db 三写者共存（天枢 actuals/evaluations/narrative_chunks + 天璇 predictions + 天玑 weight_update_log，WAL + busy_timeout 5000）
- A3a 实际协议 = HTTP REST :8900（文件投递从未落地，文档已修正）
- 采集频率 ≤50% rate-limit 红线不变；整合/导出层提频零外部请求可自由提
- 部署 = scp 单文件 + 基线校验，禁 rsync --delete；前端构建禁在 SMB 跑（拷本地构建 + scp dist 只覆盖不清理 + chmod a+rX）
- **R4 治理红线（08-07~08-10 定稿）**：接受线不可调（调门槛=自证）；EPS_TGT=0.03 冻结；weighted 0.60 冻结禁调；验收证据只用探针工件禁 calibration_cache 自证 + --read-only；n_active<20 的变量算 insufficient sample 不入池；CACHE_VERSION 每轮独立 bump；断言数不降禁 skip/.only；验收以容器部署后实测为准
- **R4h ① 裁决（08-10）**：收编 ease_ok 方向闸；credit 回池/p̂/S2 挂起转 silence 治理；A2=0.76 为定稿参数（0.80 容器实测更差）

## 坑

- **load_agents soul 加载路径依赖 config 目录（08-10 R4h ① 教训，P0）**：`soul 路径 = dirname(config_path)/../souls`——config 放 /tmp（无 souls 目录）→ A3 soul 空 {} → 静默回退旧 if-else 决策（丢 contrarian 派系），实验结果完全不可比。**任何探针/实验 config 必须放容器真实目录（/app/config）**，或先验证 A3 soul 完整加载（soul_len>0）。同一 config md5 不同路径结果可差 0.11（0.5729 vs 0.4626）
- tianji_db.py 必须 TIANJI_DATA_DIR env 指向挂载卷（OPENCLAW_WORKSPACE 推导会落 /app/data 镜像内）
- 容器重建后 control_server 不自动拉起——compose 必须挂载运行区 entrypoint.sh（保持可执行位）
- pip 的 pycdc 是冒名包；真 pycdc 需 gcc+cmake 编译（容器 apt 可用，中科大源）
- **嵌套挂载红线（08-11 事故升级，P0）**：docker 嵌套 bind mount（子挂载点在父挂载源目录内，如 `dist→html:ro` + `data→html/data`）= 高危——父挂载源 mv/rm 丢子挂载；ro 父挂载内无法建挂载点（删 dist/data 容器起不来）；**治本 = 子挂载独立路径 + nginx alias（kaiyang 已按 37dda5a 修复）**；部署 dist 禁 mv 换 inode、禁 rm dist 子目录，只原地覆盖文件；部署后 `docker exec kaiyang ls -id /usr/share/nginx/data` == 宿主 `macro-scan/data` inode
- 目录 bind mount + mv 换 inode = 容器锁旧 inode——部署 dist 禁 mv 原目录，须 restart
- scp 部署静态产物后必须 chmod -R a+rX（640 → nginx 403）
- 清旧 bundle 排除名单必须动态取自 index.html 实际引用，禁硬编码 hash（误删 CSS 白底事故）
- 收尾必查三件套：两子系统各自 CHANGELOG + 两树 VERSION bump + npm test 绿
- 删 INDEX 行时 targets 别匹配更新记录行

## 已知孤儿/脚手架（2026-08-11 容器实测核实）
> 本节记录「设计里有、运行里没接通」的组件，避免接手者误判。全部以 `ssh nas` + `docker exec` 实测为准，非工作区副本推断。

1. **玉衡 weight_matrix.py（死代码，设计层未接线，但 08-12 晚已纳入版本控制）**
   - 证据：全仓 grep `weight_matrix` 仅有文件自身引用（print/定义），无任何调度或管道调用；只提供 `--init|--health|--pending` 手动 CLI，运行期无人调用。
   - 后果：`forecast_tracker.db.weight_update_log` 恒为 0（玉衡反哺从未触发）。与「玉衡未运转」互证。
   - 处置演进：**天枢副本原 08-12 审计清理删除（F12），但 08-12 晚 C 方案将其从运行区 cp 补入 git 树（版本化）+ 修 3 处 utcnow(L95/172/301）→ 已 commit GitHub**；现 git 树 + 运行区 + 容器 `/app` bind 三处一致。设计骨架仍不投产，仅纳入版本控制防游离（纠正旧 STATUS「已删」描述）；C0（08-13）新增 c0_compute_weights.py 一次性派生脚本 + indicator_weights 表，证明 get_weights_for_target 读回派生权重闭环（仍非调度常转，apply_weight_adjustment 审批路径未接）。

2. **tianji.db / narrative.db（0 字节空桩）**
   - 证据：天玑容器 `/app/macro_data/tianji.db`、`narrative.db` 均为 0 字节（Aug 10 15:00）。仓库全量 grep 显示无代码将 DB_PATH 指向这两个文件名；真实写库走 `tianji_db.py` → `forecast_tracker.db`（1.2MB 存活，narrative_chunks=347/predictions=7/forecasts=304）。
   - 处置：确认为遗留/重命名残桩，可删；或补 writer。

3. **crucix（已退场，08-12 全闭环）**
   - 证据（08-12 实测）：`data_fetcher.py` 已删 `CRUCIX_REMOTE_URL` 引用与 `GET :3117` 分支（commit f30bd2d），gscpi 改读 `DATA_DIR/fred_history/GSCPI.csv`（NY Fed 官方月频值，末行 2026-07-31=0.805）；`docker exec get_current_snapshot` 实测 `[OK] GSCPI (NY Fed CSV): 0.805`，`_crucix` 仍 POPULATED 且字段契约不变（`gscpi.value`）。
   - 后果：运行时宏扫**已不再连 :3117**（G0 切断验证 + wiring 双实锤）；nuke/sdr/vix 经核实下游零消费（`narrative_processor` 的 crucix_* 桶仅定义未灌数据），无需 wiring。
   - 退场动作（已完成）：**G1 已于 08-12 14:01 执行 `docker stop crucix-crucix-1` → Exited (137)**，独立容器，停后无影响；新闻自采 RSS 与 crucix 零关联。停后复核天枢 `docker logs` 无任何 `:3117`/crucix 连接痕迹。
   - crucix 设计文档保留为历史参考（kaiyang `CRUCIX_*.md` 已标 DEPRECATED，见 docs/crucix-closeout-audit.md）。

4. **sim_log（死代码，非 P0 功能损坏）**
   - 证据：0 字节（Aug 5 23:50）；`macro-sim/core/sim_log.py` 定义 `DB_PATH=.../sim_log.db` 与 `insert_run()` writer，但全仓 grep `insert_run` **0 调用点**（08-12 审计实测）——writer 从未被任何代码调用，属未接线死代码，空库为预期结果，非「功能损坏」。
   - 性质：死代码（设计层未接线），与玉衡 weight_matrix 同类。处置：要么接线 writer、要么删 `sim_log` 模块；已降级为非 P0（无运行影响）。

5. **文档/副本孤儿（工作区，非运行时）**
   - 仓库内 `kaiyang-wave2/`（旧 v1.7.0 实验副本）已于 08-12 审计清理删除（F13）；如再需历史对照，从 git 历史取。
   - `_tianji_docs/` 描述的天玑比运行实际更完整（运行仅 `forecast_tracker.db` 在产；tianji.db/narrative.db 为空桩，部分解释了文档与实现的落差）。

## 关于「17 Agent」的口径澄清（纠正旧误判）
- STATUS「天璇 17 Agent」**无误**。容器 `/app/config/agents.yaml` 定义 17 个 Agent：A1–A12（12 宏观）+ S1_usa / S2_china / S3_eu / S4_russia / S5_saudi（5 主权）= 17（grep `id:` = 17 实测）。
- `souls/` 目录含 8 个灵魂文件（人格复用库），绑定到其中 8 个 agent（A1/A3/A6/S1/S2/S3/S4/S5）；其余 9 个 agent 走旧 if-else fallback（无 soul_file）。
- 二者是「agent 数」与「人格库大小」两个不同口径，**非矛盾**。运行容器 config 在 `/app/config`，soul 解析正常，无缺失 soul 静默降级（P0 soul 路径坑仅在 config 放 /tmp 时触发，运行态不触发）。
