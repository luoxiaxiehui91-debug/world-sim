# world-sim — AI 工作入口

**系统定位**：macro-scan 持续观测全球宏观信号 → macro-sim 演化未来路径（不是推理，是演化）→ kaiyang 只读可视化 + 控制台。

---

## 三个子系统

| 子系统 | 定位 | 容器模式 | 版本（as-of 2026-08-18） | NAS 运行目录 |
|:-------|:-----|:---------|:-----|:-------------|
| `macro-scan` | 数据观测层：实时抓取 FRED/GPR/新闻/地缘信号，生成 GRV 维度向量（18 项，含 global_composite 汇总 + 4 GDELT 国别推导维度 + gpr_twn_raw，08-07 实测）；**地缘预测自动验证（verify_geo_auto L1/L2，08-18）+ GRV 分数常态基准校准（#134，08-18）** | **热挂载**（改代码即生效；scheduler.py 改动需 restart） | **v3.8.20** · [CHANGELOG](macro-scan/TuiYan_CHANGELOG.md) | `/vol2/1000/software/macro-scan` |
| `macro-sim`  | 仿真引擎层：**20个 Agent**（13 金融 A1-A13 + 7 主权 S1-S7，08-18 实测），Monte Carlo×100，月度时间步长；**soul 政权分片 + 内生更迭引擎（08-17）** | **COPY 模式**（改代码需 rebuild 镜像；deploy.sh 仓库直构） | **v2.0.41** · [CHANGELOG](macro-sim/CHANGELOG.md) | `/vol2/1000/software/world-sim/macro-sim` |
| `macro-ji`   | 验证层（天玑）：读天枢 data 做推演验证/反哺（T2 共享触发文件驱动，2026-08-04 独立容器上线） | **COPY 模式**（macro-ji/ 目录 rebuild） | v1.0.0 · [CHANGELOG](macro-ji/CHANGELOG.md) | `/vol2/1000/software/world-sim/macro-ji` |
| `kaiyang`    | 可视化操作面板：只读展示天枢数据 + 控制台（:8080，control API :8900）；**控制面三 tab 中天璇/天玑已上线只读+人工验证（v1.11.29+）** | nginx 静态站（MOCK_ENABLED=false，A3a 已接入，index.html no-cache） | **v1.11.34** · [CHANGELOG](kaiyang/CHANGELOG.md) | `/vol2/1000/software/kaiyang` |

**数据流**：macro-scan 每日写入 `data/*.json` → macro-sim 只读消费 → kaiyang 只读展示；天玑（macro-ji）读天枢 data / worldsim-pg（E0-C 起读路径统一 PG）做验证闭环。

---

## 数据架构现状（E0-C + P0-D2，2026-08-15）

**读路径已统一 worldsim-pg**（`核心代码/pg_read.py` 只读层，行边界归一化 UTC 文本；14 个 reader 已切）。**写路径 PG 主写**（`WORLDSIM_SQLITE_OFF=1` 已生效：news_db 6 写函数 + synthesis_log 写路径 PG-only 分支；`data/.sqlite_frozen_at` marker 留存）。**天枢侧 SQLite 已删（P6 08-14 08:39 闭环，commit 1ba002a）——任何代码不得再 sqlite3.connect 创建 news.db，读走 pg_read。**

**⛔ 08-15 D2 预测链转 PG（`afe1311`+`f7cf689`）**：天璇 `macro-sim/run.py` `_archive_to_tianji` 与天玑 `macro-ji/tianji_db.py`/`tianji_verifier.py` 全部 psycopg 直连 worldsim-pg `tianji.predictions` + `reasoning_trace`（search_path=tianji,public）。**⛔ P6 已收官（08-16 `8905fa01`）**：forecast_tracker.db 已删除（快照 `backups/e0c-p6-20260816-092548/`），探针 `_SQLITE_GONE_EXEMPT` 豁免已移除——**全系统 PG-only，data 目录出现任何 .db 复生 = CRIT**。

**08-16 LLM 统一配置（`llm_usage.py` + `data/llm_config.json`）**：6 使用点（translate_titles / openai_compat / rag_embedding / sim_mc / sim_narrative / sim_minimax）× 4 平台（mimo / siliconflow / minimax / openai），开阳控制台「LLM 配置」面板可换平台/模型/API key（`GET/PUT /api/v1/control/llm-usage`）；配置优先于 env/代码常量，天枢热挂载即时、天璇读共享文件（`/app/macro_data/llm_config.json`，60s TTL 08-17 加）。翻译模型 mimo-v2.5；RAG 嵌入 bge-m3（`rag_engine.py`）。

**⛔ 08-17/18 天璇模型线（重大，详见 `macro-sim/CHANGELOG.md` v2.0.41）**：
- **soul 政权分片**：主权 soul `regimes:` 时间片（since/until）——校准期按历史月份切换"当时政权风格"，预测期默认现行路线；5 主权红线阈值按 GRV 实测分布校准
- **政权更迭引擎**：`core/governance.py` 内生事件——民主选举（到周期必换届 + transition_prob 切换）/ 长期执政继承 / 政变（succession_risk × 社会压力，一次性黑天鹅）；报告"政权更迭事件"节
- **日韩主权 S6/S7**：准一党制（transition 0.15）vs 单任期强制轮替（transition 0.70）——政权光谱两端
- **预测描述清晰化**：`bifurcation.py` `_ACTION_CRITERIA` 30+ 动作 → 现实判定标准；geo 预测 content 带路径 GRV 上下文 + outcome 判据
- **人工验证 + 自动验证闭环（验证对象 = 未来事件是否应验，非推理审阅）**：
  - 人工：开阳天玑 Tab 点选 [发生/部分/未发生]（control API）或 CLI `verify_human.py --list/--verify`；verified_by=human
  - 自动：天枢 `verify_geo_auto.py`（scheduler 0930）——L1 FRED 判定器（DFF/利差/VIX 分位）+ L2 新闻关键词判定器（PG news.articles 窗口，**只做发生确认**：命中→1，未命中→None 保留人工）；verified_by=auto + human_note 存依据
  - predictions 表 `action_key` 列 = 判定器分派键（不依赖中文名）；`human_note` 列 = 验证备注/自动依据

**⚠️ 运行区 compose 纪律（08-15 实测教训）**：必须显式含 `networks: worldsim_default(external)` + `WORLDSIM_APP_PW`/`WORLDSIM_SQLITE_OFF=1`——手动 `docker network connect` 在 `docker compose up -d` recreate 后即丢（PG 断连实测）；env 丢失会回归 SQLite 双写。控制 API（:8900）已 **fail-closed**（P1-D）：未配 CONTROL_TOKEN 一律 503/401，开阳面板需填 token。

涉及 P0/E0-C 排障先查 `docs/decisions/E0-C-operation-log.md` 与 `docs/decisions/ADR-00{1,2,3}.md`；对账/探针：`verify_reads_e0c.py`（双读校验台，PG-only 语义）/ `reconcile_synthesis.py` / `silent_failure_probe.py`（**32 项**，PG-only 模式 + check_predictions_chain + check_ged_stale + check_llm_config）。审查/实施记录：`docs/reviews/` + `docs/decisions/20260815-p0p1-implementation.md`。

## 新 session 阅读路径

按顺序读取，每步均需完整阅读：

1. **本文件**（根 `AGENTS.md`）— 了解系统全貌和操作约束
2. **`STATUS.md`**（repo 根）— 实时交接状态（部署拓扑/R4 主线/已知坑），08-10 起为实时交接权威（docs/archive/handover-history.md 为 08-07 历史快照）
3. **`STATUS.md`「待做/已知遗留」节** — 实时扫描当前所有 P1/P2 活跃问题与遗留项（权威源；历史快照见 docs/archive/handover-history.md，前瞻路线图见 docs/roadmap.md）
4. **`macro-scan/TuiYan_CHANGELOG.md` 前 80 行** — 了解 macro-scan 最新变更状态
5. **`macro-sim/CHANGELOG.md` 前 80 行** — 了解 macro-sim 最新变更状态
6. 按任务分支：
   - 处理 macro-scan / 天枢任务 → 读 `macro-scan/AGENTS.md`（完整工作指南）
   - 处理 macro-sim / 天璇任务 → 读 `macro-sim/AGENTS.md`（完整工作指南）
   - 处理 kaiyang / 开阳任务 → 读 `kaiyang/AGENTS.md`（完整工作指南）

---

## 关键操作约束

| 约束 | 说明 |
|:-----|:-----|
| NAS 挂载 | `S:\world-sim\` 是 NAS 网络挂载（`\\192.168.31.108\software\`），不是本地磁盘，删除文件前必须二次确认 |
| git 路径 | 所有 git 命令用 `git -C /s/world-sim`，不能 `cd` 进去 |
| push 走代理 | `git -C /s/world-sim -c http.proxy=http://192.168.31.108:7890 push origin main` |
| macro-scan 热挂载 | 改 `S:\world-sim\macro-scan\核心代码\*.py` 立即生效，**不**需要 restart |
| macro-sim COPY | 改代码后必须重建镜像：`bash /s/world-sim/deploy.sh macro-sim` |
| kaiyang 构建 | 改 src/ 后需 `npm run build`（在 kaiyang/ 目录），dist/ 不进 git，需手动 scp 到 NAS |
| deploy.sh macro-scan | 只做 rsync + `docker compose restart`（不重建镜像） |
| 改前必读 | 改任何文件前先读对应子系统的 CHANGELOG（两个系统都有各自铁律） |
| 改后必追加 | 追加 CHANGELOG + bump VERSION + 按联动矩阵更新联动文档 |
| R4 治理红线 | 校准引擎：接受线/EPS_TGT/weighted 0.60 冻结禁调；断言数不降禁 skip/.only；CACHE 每轮 bump；验收以容器实测为准 |
| soul 路径 P0 | 探针/实验 config 必须放容器真实目录 `/app/config`（`load_agents` 的 soul 路径 = `dirname(config_path)/../souls`，放 /tmp 会静默丢 A3 soul → 假复现，结果可差 0.11） |
| 校准评审实录 | `docs/calib/`（calib-*.md 评审/裁决/验收存档）+ `macro-sim/docs/operations/`（天璇操作日志，按日追加） |

---

## 数据接口契约（摘要）

macro-scan 每日按时写入，macro-sim 只读消费，kaiyang 只读展示：

| 文件 | 写入时间 | 说明 |
|:-----|:---------|:-----|
| `data/grv_latest.json` | 06:10 | GRV 地缘风险向量（18 项维度，含 global_composite 汇总 + korean_peninsula/south_china_sea/india_pacific/global_south/gpr_twn_raw，08-07 实测），schema v1.0 |
| `data/fred_history/*.csv` | 05:30 | FRED 宏观指标（T10Y2Y / BAA10Y / DFF），值单位 `%`，读取后需 ×100 转 bp |
| `data/news_export.json` | 07:05 | 近7天新闻摘要（40条，6类），schema v1.0；顶层 `updated`（=导出时刻，无后缀=北京）供开阳 useFeed 时间戳——2026-08-05 起写入 |
| `data/sim_trigger.json` | 触发时 | L3+ GRV 告警后写入，触发 macro-sim 仿真 |
| `data/scheduler_state.json` | 每60s | scheduler 运行状态落盘，control_server（:8900）读取 |

**当前接口兼容版本**：macro-scan v3.8.17+ ↔ macro-sim **v2.0.40+**（grv v1.0 / news v1.0，as-of 2026-08-12）

接口 schema 变更规则：同时改两边 AGENTS.md 的接口契约节 → 两边 CHANGELOG 各追加 → 先升 macro-scan 验证输出 → 再升 macro-sim。

---

## 子系统详细指南

- **macro-scan 完整工作指南** → [`macro-scan/AGENTS.md`](macro-scan/AGENTS.md)
- **macro-sim 完整工作指南** → [`macro-sim/AGENTS.md`](macro-sim/AGENTS.md)
- **kaiyang 完整工作指南** → [`kaiyang/AGENTS.md`](kaiyang/AGENTS.md)

---

## 人类文档导航（非 AI 用）

- **系统总览**（推荐入口）→ [`docs/overview.md`](docs/overview.md)
- **实时交接状态** → [`STATUS.md`](STATUS.md)（08-10 起权威；[docs/archive/handover-history.md](docs/archive/handover-history.md) 为 08-07 历史快照）
- **时间门控路线图** → [`docs/roadmap.md`](docs/roadmap.md)
- **校准评审实录** → [`docs/calib/`](docs/calib/)（calib-*.md）+ 天璇操作日志 `macro-sim/docs/operations/`
- **架构裁定（2026-08-02）** → [`docs/arch_review_20260802.md`](docs/arch_review_20260802.md)
