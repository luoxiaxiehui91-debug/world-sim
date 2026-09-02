# macro-scan CHANGELOG — 天枢（数据采集/分析层）

> 文档类别：实录（RECORD）· CHANGELOG
> 版本锚点：`S:/world-sim/macro-scan/VERSION`

---

## v3.8.27 — 2026-09-02 LLM 平台收敛：openai_compat 模型固化 config + 移除预置 OpenAI 平台

### 变更
- `data/llm_config.json`：`usages.openai_compat.model` 固化 `mimo-v2.5-pro`（原经 env `OPENAI_COMPAT_MODEL` 注入、开阳仅显示"（env 默认）"不可见不可改）→ 开阳 effective_models 直接显示真实生效模型、下拉可改
- `docker-compose.yml`：移除 env `OPENAI_COMPAT_MODEL=mimo-v2.5-pro`（隐藏开关，与 config 双源易漂移；`OPENAI_COMPAT_URL` 保留——`reason()` 无 usage 路径依赖它定 base_url）
- `核心代码/llm_usage.py`：`PLATFORMS` 移除预置 `openai`（api.openai.com，从未被任何 usage 引用、未配 key，初始脚手架残留）；`env_name` 表同步删除
- `核心代码/hybrid_llm.py`：`_PLATFORM_ENV_KEYS` 移除 `openai` 行（`reason()` 的 `mode=="openai"` 分支与 CLI `--reasoning` choices 保留——其语义为 OpenAI 兼容协议指向 MiMo，与 api.openai.com 平台无关）

### 关联
- 延续 commit eb47031（mimo_plan/mimo_api 平台拆分）：平台列表收敛为 mimo_plan / mimo_api / siliconflow 三家
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
