# macro-scan CHANGELOG — 天枢（数据采集/分析层）

> 文档类别：实录（RECORD）· CHANGELOG
> 版本锚点：`S:/world-sim/macro-scan/VERSION`

---

## v3.8.28 — 2026-09-03 密钥治理：控制台 api_key 写入通道封死（密钥只走 .env，ADR-0013）

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
