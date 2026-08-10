# STATUS — world-sim 实时交接文件

> 冷启动：先读 `项目导航.md`，再读本文件。最后更新：2026-08-10 08:30 GMT+8。

## 当前状态

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

- 版本现状：macro-scan **v3.8.15** / macro-sim **v2.0.40**（CACHE 14 / ARTIFACT v2033）/ macro-ji v1.0.0 / kaiyang **v1.9.0**

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
2. **news_geo 图层空渲染（架构遗留，非 bug）**：news_geo_feed（P3-A，spaCy NER 未装）07:15 写空 articles 覆盖；GDELT events（jsonl I15 活跃）从不进 news_geo.json——拆文件/补 NER 属 P3-A 架构工作另行规划
3. **FRED 上游源停更（观察中）**：DCOILWTICO 卡 07-27 / ICSA 07-25（经代理实测，非本地问题）；fresh=False 已暴露 + ntfy 告警覆盖；BAA10Y/DTWEXBGS 卡 07-31 根因待查
4. **kaiyang/public 静态 manifest** 冻 06-28，待同步运行区生成版
5. **天璇 deploy.sh macro-sim 目标内部 ssh 密码验证失败**：重建改手动 docker build（脚本本身无 bug，NAS 自身 ssh 配置问题）
6. **天玑 weight_update_log 仍 0 为正常**：MIN_TRIGGER_N=8，当前 predictions=1，链路已验证可跑
7. **工作区历史遗留 M**：多为 CRLF 幻影，判脏须 `git diff --ignore-all-space`
8. **天璇 sim_log.db 空目录**（bind 宿主空目录，仿真记录功能损坏，P0 未修）；天璇 /app/output 校准产物随重建丢失（已知）

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
- 目录 bind mount + mv 换 inode = 容器锁旧 inode——部署 dist 禁 mv 原目录，须 restart
- scp 部署静态产物后必须 chmod -R a+rX（640 → nginx 403）
- 清旧 bundle 排除名单必须动态取自 index.html 实际引用，禁硬编码 hash（误删 CSS 白底事故）
- 收尾必查三件套：两子系统各自 CHANGELOG + 两树 VERSION bump + npm test 绿
- 删 INDEX 行时 targets 别匹配更新记录行
