## [3.8.33] - 2026-09-03

### Added（P3-3 / question l4-tail-scenario-modeling，方案 C 降级折中版，用户拍板）

- **L4 极端尾部烈度建模**：hypothesis_templates.yaml severity_params 新增 L4 节「崩坏/极端尾部」（vix_mult 2.5 / lambda_mult 6.0 / sigma_mult 3.5 / regime_force stress；calibration: expert-assumption 显式标注专家情景假设非历史校准；keywords 全多字词防误判——核战争/全球大流行/小行星撞击等）
- **历史类比禁用于 L4**：hypothesis_engine.get_historical_analogies 对 severity=="L4" 不做 percentile 系数外推（L4 无历史样本，外推属伪精确），改返回固定情景假设区间（spx -60/-45/-30、vix_delta 50/70/90、gdp -30/-20/-10），source 标注「L4情景假设（非历史校准）」；L1-L3 逻辑不变（整体收进 else）
- **永不升格🟢覆盖 L4**：置信度信号 no_green_triggers 分支 `sev == "L3"` → `in ("L3", "L4")`
- **ntfy 推演通道放行 L4**：ntfy_listener.py 烈度白名单 ("L1","L2","L3","L4") + sev_label 加「崩坏/极端尾部」
- **验证（容器内冒烟，零 LLM 调用）**：py_compile 过；parse「核战争/全球大流行」→L4、「台海紧张」→L2 不误判；L4 impacts=情景假设区间+标注；L3 source 仍=历史类比；三方 md5 一致（git 真源/运行区/容器）+ docker restart
- **后续完整版入 backlog**：概率型/情景型分组推演（L4 走独立情景分析模式，hermes-systemic 9.5 原方向）——用户拍板「早晚要完善，记的加进后续计划里」

### 关联
- questions/world-deduction/20260903-world-deduction-l4-tail-scenario-modeling.md（⚠️→✅→归档）
- decisions/world-deduction/0014-l4-tail-severity-modeling.md（ADR-0014）
- operations/CHG-20260903T125000-macro-scan.md

# macro-scan CHANGELOG — 天枢（数据采集/分析层）

> 文档类别：实录（RECORD）· CHANGELOG
> 版本锚点：`S:/world-sim/macro-scan/VERSION`

## [3.8.32] - 2026-09-03

### Fixed（P2-5 / question calibration-score-no-decay + 前置阻塞 bug）

- **propagation_paths.yaml 解析修复**：`atomic_paths:` 映射键打断顶层 list 致 ParserError，被 `_load_propagation_paths()` 的 `except Exception` 静默吞掉——25 条传导路径（20 主 + 5 原子）从未加载，维度2 恒兜底 0.2。现原子路径并入顶层 list（键无代码消费），实测加载 25 条
- **置信度时间衰减**：20 条主路径按 data_quality 历史锚点补 `last_verified`（12 条），`hypothesis_engine._cal_decay()` 应用 `max(0.5, 0.98^年数)` 衰减因子于维度2 加权（L563 avg_cal）；无锚不衰减。参数可调
- 注意：修复后维度2 从恒 0.2 变为真实计算，推演概率输出将变化（预期修复效果）；完整推演回归交由下次常规调度验证
- CHANGELOG: v3.8.24 停更的 TuiYan_CHANGELOG.md 已废弃（AGENTS 导航待更新，另案）

## v3.8.31 — 2026-09-03 天枢 news_ttl_cleanup 功能批次入库：PG news.articles 90 天 TTL 清理（08-30 已部署，本次补 git 记录）

### 变更
- 【commit c94978c — question 20260903-world-deduction-ttl-cleanup-uncommitted（P2）收编，用户拍板「按顺序来吧」】
  - 入库 “核心代码/news_ttl_cleanup.py”（3121B，08-30 建）：PG news.articles TTL 清理，保留 90 天（NEWS_TTL_DAYS env 参数化），更早行 DELETE
  - 入库 “核心代码/scheduler.py” +2：JOBS 注册 news_ttl_cleanup（每日 03:00，“1-7”）+ LOG_FILES 注册 news_ttl_cleanup.log
  - VERSION 3.8.30 → 3.8.31（git 真源 + 运行区双端；该文件经 grep 实证无代码消费、容器不挂载，属纯文档锚点）
  - ⚠️ 本次为补记录而非新部署：git 真源 / 运行区 / 容器三方 md5 全同（2afc1122…）实证功能 08-30 起已在运行，此前仅缺 git 记录（“部署先于入库”第三次，同 kaiyang D3 08-06 先例）

### 关联
- questions/world-deduction/20260903-world-deduction-ttl-cleanup-uncommitted.md（⚠️ → ✅ → 归档）

---
## v3.8.30 — 2026-09-03 P5 退役：天枢 verify 域三旧脚本退役（验证功能 2026-08-24 已迁天玑收编）

### 变更
- 【commit ea518a9 — question 20260824-world-deduction-verify-domain-consolidation / 20260823-world-deduction-verify-ownership-misplacement（P5 收尾，用户拍板执行）】
  - 删除 “核心代码/verify_geo_auto.py” / “verify_hypothesis.py” / “verify_predictions.py”（git 真源 + 运行区双端）——现行调度已在天玑 tianji_verify_cron（geo_auto 每日 09:30 / predictions 每月 1 日 09:00 / hypothesis 每月 1 日 09:15），天枢三文件为 2026-08-24 存量收编后的旧残留；宿主/容器 crontab、scheduler JOBS、ntfy 指令通道全入口 grep 核查无引用后删除
  - “核心代码/ntfy_listener.py”：退役 cmd_verify 指令通道（函数块/路由分支/help 行三处），防删文件后 ntfy verify 指令断链；py_compile 通过；运行区 md5 双端一致（b339f74f…）
  - “verify_reads_e0c.py” 保留（E0 审阅域与验证域独立）
  - VERSION 3.8.29 → 3.8.30
  - 已知过时待后续：tests/test_audit_scan_scheduler_verify.py 断言 scheduler JOBS 应含 verify_predictions（审计 #13 xfail 回归设计），随本退役语义反转，建议改为“JOBS 不应含”（不在本次范围）

### 关联
- questions/world-deduction/20260824-world-deduction-verify-domain-consolidation.md（⏸ → ✅ → 归档）
- questions/world-deduction/20260823-world-deduction-verify-ownership-misplacement.md（母题，归档）
- 背景：P4 月度对账（09-01 窗口 verify 两任务首次自动触发 + 43 条补跑）全维度通过后执行既定 P5 收尾

---
## v3.8.29 — 2026-09-03 开阳报告索引时序竞态修复：save_report() 落盘后就近刷新开阳数据源

### 变更
- 【commit 113410b — question 20260902-kaiyang-report-index-race（P2）修复，用户拍板方案 A】
  - “核心代码/run_macro_analysis.py” “save_report()”：ntfy 推送后、return 前新增 REINDEX 段——报告写盘成功后 subprocess 调同目录 “generate_reports_index.py”（timeout 180s），即写即刷新 “data/reports_index.json” + “data/reports/”，解耦索引重建与调度时序；触发失败仅 [WARN] 打印，不阻塞报告保存/ntfy 推送
  - “scheduler.py” 07:35（工作日）/20:35（每天）定时重建保留作幂等兜底（不删）
  - VERSION 3.8.28 → 3.8.29

### 关联
- question “questions/world-deduction/20260902-world-deduction-kaiyang-report-index-race.md”（⚠️ 已定位待修复 → 修复完成）
- CHG-20260903T072540-world-deduction（Pre/Post 闭环）
- 背景：晨报 07:30 cron 启动、LLM ~07:36 完稿；scheduler 07:35 索引重建抢跑 → 报告落 07:36~20:35 空窗（ntfy 已推、开阳不显示）

---
：控制台 api_key 写入通道封死（密钥只走 .env，ADR-0013）

### 变更
- 【commit 94939af — question 20260902-llm-config-key-plaintext（P1）修复】
  - “核心代码/llm_usage.py” “set_usage”：非空 api_key 硬拒 → (False, “密钥禁止经控制台写入：请配置于 NAS macro-scan/.env …”)；entry.pop(“api_key”) 清历史残留——config 持久化永不带 key（docstring 同步）
  - “核心代码/control_server.py” PUT /api/v1/control/llm-usage/{usage_id}：docstring 更新（key 禁走此路，set_usage 兜底拒收并返回明确错误）；body 透传保留
  - 前端配套（kaiyang v1.11.36）：LlmConfig.tsx 删 key 输入框 + controlApi.ts updateLlmUsage 去 apiKey

### 关联
- question “questions/world-deduction/20260902-world-deduction-llm-config-key-plaintext.md” → ✅ resolved 归档
- ADR-0013 secret-injection-normalization（密钥只走 .env）
- 与 “20260822-llm-keys-plaintext-in-git”（compose 明文进 git）同源不同面，共同闭合 world-deduction 密钥注入规范

---

## v3.8.27 — 2026-09-02 LLM 平台收敛：mimo_plan/mimo_api 拆分 + openai_compat 模型固化 config + 移除预置 OpenAI 平台

### 变更
- 【commit eb47031 — mimo 平台拆分：mimo→mimo_plan + 新增 mimo_api】
  - `核心代码/llm_usage.py`：`PLATFORMS` 的 `mimo` 重命名 `mimo_plan`（显示名“小米 MiMo Plan”，token-plan 端点与 `OPENAI_COMPAT_KEY` 映射不变）；新增 `mimo_api`（显示名“小米 MiMo API”，base_url `https://api.xiaomimimo.com/v1`，env `MIMO_API_KEY`）；LLM_USAGES 引用 `platform:"mimo"` 的 3 处默认值同步 → `mimo_plan`；`env_name` 表同步 + 新增 `mimo_api→MIMO_API_KEY`
  - `核心代码/hybrid_llm.py`：`_PLATFORM_ENV_KEYS` 同步（`mimo_plan`）+ 新增 `mimo_api→MIMO_API_KEY`
  - `data/llm_config.json`（运行态）：`openai_compat.platform` `mimo`→`mimo_plan`
  - `docker-compose.yml`：env 段新增 `MIMO_API_KEY=${MIMO_API_KEY}`（`config --quiet` 通过）；`.env` 加 `MIMO_API_KEY=` 占位（待用户填 `ak-` key 后 `docker compose up -d` 生效）
- 【commit 368e3d6 — openai_compat 模型固化 config + 移除预置 OpenAI 平台】
- `data/llm_config.json`：`usages.openai_compat.model` 固化 `mimo-v2.5-pro`（原经 env `OPENAI_COMPAT_MODEL` 注入、开阳仅显示"（env 默认）"不可见不可改）→ 开阳 effective_models 直接显示真实生效模型、下拉可改
- `docker-compose.yml`：移除 env `OPENAI_COMPAT_MODEL=mimo-v2.5-pro`（隐藏开关，与 config 双源易漂移；`OPENAI_COMPAT_URL` 保留——`reason()` 无 usage 路径依赖它定 base_url）
- `核心代码/llm_usage.py`：`PLATFORMS` 移除预置 `openai`（api.openai.com，从未被任何 usage 引用、未配 key，初始脚手架残留）；`env_name` 表同步删除
- `核心代码/hybrid_llm.py`：`_PLATFORM_ENV_KEYS` 移除 `openai` 行（`reason()` 的 `mode=="openai"` 分支与 CLI `--reasoning` choices 保留——其语义为 OpenAI 兼容协议指向 MiMo，与 api.openai.com 平台无关）

### 关联
- 命名决议（用户拍板）与实施规划见 `decisions/world-deduction/20260902-world-deduction-add-mimo-api-provider.md`（status: planning → implemented）
- `morning.log`/`us_daily.log` 实证宏观分析经 `reason("auto")` → `call_openai_compat`（无 usage）→ env URL + config model 生效路径

---

## v3.8.26 — 2026-08-28 P2: PG news.articles TTL 清理

### 新增
- `核心代码/news_ttl_cleanup.py`：每日清理 `news.articles` 中超过 TTL_DAYS（默认 90 天）的行；timedelta 参数化、dry-run 计数先行、VACUUM ANALYZE 后置（失败不阻断）
- `scheduler.py`：`JOBS` 加 `news_ttl_cleanup`（每日 0300）+ `LOG_FILES` 对应条目

### 备注
pg_dump 备份已由 `/vol2/1000/software/worldsim-pg/backup-pg.sh`（每日 0400，保留 14 天）独立覆盖，无需重复注册。

---

## v3.8.25 — 2026-08-27 F1 commit 2: 天璇 GRV 轨迹 feed 导出

### 新增
- `核心代码/tianxuan_grv_export.py`：扫 `docs/仿真报告/*_grv_traj.json`，按 `generated_at` 幂等导出最新轨迹到 `data/tianxuan_grv.json`；M4 版本护栏、保留旧 feed + 告警（不静默写空）、M6 幂等跳过重写
- `scheduler.py`：`JOBS` 加 `tianxuan_grv`（I30）+ `LOG_FILES` 对应条目
- `silent_failure_probe.py`：新增 `check_tianxuan_grv()`（内容 `generated_at` 判据，非 mtime）
