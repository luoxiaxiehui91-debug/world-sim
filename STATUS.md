# STATUS — world-sim 实时交接文件（新 session 冷启动第一入口）

## 新 session 冷启动（3 分钟，防迷路）

> 任何新会话先读本区块，再读 `项目导航.md`（结构/待办概览）与 `.workbuddy/memory/MEMORY.md`（长期红线/部署拓扑）。最后更新：2026-08-11 15:25 GMT+8。

**项目是什么**：world-sim 世界推演系统——个人内部宏观推演系统（非商业产品）。逻辑 5 层：天枢（观测采集）→ 天璇（仿真，17 Agent）→ 天玑（验证）→ 玉衡（权重，未运转）→ 开阳（展示）；横切 crucix 信号总线（AGPL，退场实施中）+ 摇光 SRE。

**项目位置**（防迷路，全部关键路径）：
- WorkBuddy 工作区（本文档 + 项目导航 + calib 评审权威）：`C:\Users\luoxi\WorkBuddy\世界推演系统\`
- **NAS Git repo = 真相**：`/vol2/1000/software/world-sim/` → GitHub `luoxiaxiehui91-debug/world-sim`（push 走代理 `http://192.168.31.108:7890`）
- **`S:\world-sim` = NAS repo 的 SMB 挂载视角**（`\\192.168.31.108\software\world-sim`，与 `/vol2/1000/software/world-sim` 同一份文件、同一 git 树）：仅作 Windows 侧浏览参考，**读写都不可信**（展示过期幻影/写不到容器）——判脏/部署/同步一律 `ssh nas` + `docker exec`
- NAS 运行区：天枢热挂载 `/vol2/1000/software/macro-scan/核心代码/`（改 .py 即生效，scheduler.py 需 docker restart）；开阳 `/vol2/1000/software/kaiyang/dist`；crucix `/vol2/1000/software/Crucix/`（禁抄源码，AGPL）
- 容器：`macro-scan-macro-scan-1`（天枢）/ `macro-sim`（天璇，COPY 模式）/ `macro-scan-tianji-1`（天玑）/ `macro-scan-kaiyang-1`（开阳 :8080）
- SSH：`ssh nas`（**必须 Git 自带 ssh，Windows OpenSSH 已坏**）；NAS 操作走 SSH + docker exec，**禁信 SMB 挂载**

**当前主线（08-11）**：
1. **crucix 退场**——论证+实施 14 commit 全闭合（eff0d8c 为止），**观察窗中**：G0 判 08-12 / G1 判 08-15（自动化）；之后 WP-2.1b gscpi 切换 → WP-3.x 清理 → WP-4.x 停容器
2. **开阳补全**——v1.9.0→v1.10.8（报告中心/FCI/风险面板/news_geo 事件图层/视觉 crucix 化/同地点聚合），news_geo 验收观察窗（08-13 06:35 自动化判定）
3. 挂起待拍板：**航班走廊线（air 图层 B 完整版）**

**必读顺序**：本文件 → 项目导航.md → .workbuddy/memory/MEMORY.md（红线）→ 按需 worldsim-review-synthesis.md（架构设计）；详细待办见下文「待做/已知遗留」节。

---

## 当前状态

**08-11：crucix 退场实施全部闭合（观察窗中）+ 开阳大规模补全（v1.9.0→v1.10.8）+ 时区统一修复**：
- **crucix 退场实施（08-10 晚启动，全 commit 闭合至 ab8b1f7）**：G0 climate 恢复（a65c998）/ gscpi fetcher+调度（100e544/b29c8da，NY Fed xlsx 尾行 0.805）/ ADR-08 死代码删（a8ffb34）/ climate 兜底删+firms 加固（7ac6b48）/ safecast nuke 6 站 MATCH（611cc6b）/ kiwisdr 接线（c38a2b0）/ 双调度注册（260a173）/ RSS-only articles 断供排除（5bba73e）/ air 删+ gscpi_warn None 防护（65666b8）/ firms 补偿重试（77f6711）/ 时区修复 10 处显式后缀（a7c6e42）
- **观察窗（等门禁，自动化接管）**：gscpi 05:32 / kiwisdr 06:02 / climate 09:10 已首跑；**G0 判 08-12 / G1 判 08-15** → WP-2.1b gscpi 切换 + WP-2.2 nuke 改读 → WP-3.x 清理 → WP-4.x 停容器（crucix 容器独立运行中，等门禁）
- **开阳补全（v1.9.0→v1.10.8）**：第一批报告中心（45 份）+ FCI/GSCPI 面板 + 风险信号面板 + dashboard 停生成（2dff1a6）+ news_export 提频 I15（3c30723）；**M-1 news_geo 事件图层**（8e6aaf3/a86fbbe/ddb17b0：137B 空壳→527 事件，CAMEO event_code 落盘，XSS 双保险）→ 视觉 crucix 化（a63bd65）→ 缩放半补偿（da464f5）→ 事件弹框+原文链接（84464dd）→ 同新闻合并+unknown 清零（c4659f4）→ 视觉降噪 Top-80 标签（a3b0561）→ **同地点聚合 v1.10.8（ab8b1f7：628→208 点，一城一点+计数徽标）**
- **news_geo 验收**：数据侧 9/9 + qa 16 PASS + XSS 实测不可注入；48h 判定 08-13 06:35 自动化（unknown<5%）；浏览器复核 17 项待主理人
- **事故治本（37dda5a）**：开阳部署触发嵌套挂载断链（mv dist 换 inode → html/data 子挂载丢失 + 删 dist/data 容器起不来）→ data 挂载独立到 `/usr/share/nginx/data` + nginx alias（嵌套挂载红线升级，见坑节）
- 时区：全系统落盘时间戳统一显式后缀（UTC→Z / 本地→+08:00），前端 parseTs 契约无后缀=北京时间，10 处修复 + OPEN 3 条（news.db 展示层 / grv-history 边界 / 纯日期键）

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
- deploy.sh 两处 rsync --delete 实修（commit 18d3962，CHANGELOG 曾声称已移除=假）；FCI 产物日更恢复；crucix 实测仍活跃独立运行 30/30（"退场中"说法过时，应为独立运行过渡期共存）

**08-07~08-10：天璇校准引擎 R4a→R4h 八轮治理（主线，见下节 R4 系列）**：
- 版本线：v2.0.37（R4g 收尾，引擎回 R4e 基线+归因测量修复）→ v2.0.38（R4h ③ sentiment 写者，CACHE 12/v2031）→ v2.0.39（R4h ② vix 豁免治理，CACHE 13/v2032）→ **v2.0.40（R4h ① ease_ok 方向闸收编，CACHE 14/v2033）**
- 08-10 R4h ① 结案：**收编 EASE 治理**（EASE wrong 8→0 真实有效）；credit 回池/p̂ 0.4894/S2 0.636 不通过、挂起转 silence 治理；方案预期 0.5729 系假复现（A3 soul 缺失），见下节红线

- 版本现状：macro-scan **v3.8.17** / macro-sim **v2.0.40**（CACHE 14 / ARTIFACT v2033）/ macro-ji v1.0.0 / kaiyang **v1.10.8**

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
6. **天玑 weight_update_log 仍 0 为正常**：MIN_TRIGGER_N=8，当前 predictions=1，链路已验证可跑
7. **工作区历史遗留 M**：多为 CRLF 幻影，判脏须 `git diff --ignore-all-space`
8. **天璇 sim_log.db 空目录**（bind 宿主空目录，仿真记录功能损坏，P0 未修）；天璇 /app/output 校准产物随重建丢失（已知）
9. **时区 OPEN 3 条**：news.db ingested_at/last_scan 展示层未统一（web_server /status）；web_server.py:530 /grv-history 本地↔UTC 混合比较边界差 8h；gdelt_history.date 纯日期键维持 UTC 语义（低优先）
10. **firms 09:08 连续 0 行需人工介入（08-11 晨检发现）**：补偿重试（77f6711）未救回；19:08 手动触发 39993 热点=源活 → 疑 09:08 调度时段源端/网络持续异常，建议改调度时间或查该时段出网（qa midcheck P1#2 延伸）

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
