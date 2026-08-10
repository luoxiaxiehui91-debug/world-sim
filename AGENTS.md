# world-sim — AI 工作入口

**系统定位**：macro-scan 持续观测全球宏观信号 → macro-sim 演化未来路径（不是推理，是演化）→ kaiyang 只读可视化 + 控制台。

---

## 三个子系统

| 子系统 | 定位 | 容器模式 | 版本（as-of 2026-08-10） | NAS 运行目录 |
|:-------|:-----|:---------|:-----|:-------------|
| `macro-scan` | 数据观测层：实时抓取 FRED/GPR/新闻/地缘信号，生成 GRV 维度向量（18 项，含 global_composite 汇总 + 4 GDELT 国别推导维度 + gpr_twn_raw，08-07 实测） | **热挂载**（改代码即生效；scheduler.py 改动需 restart） | v3.8.16 · [CHANGELOG](macro-scan/TuiYan_CHANGELOG.md) | `/vol2/1000/software/macro-scan` |
| `macro-sim`  | 仿真引擎层：**17个 Agent**（12 金融 + 5 主权 S1-S5，08-07 A 类激活），Monte Carlo×100，月度时间步长 | **COPY 模式**（改代码需 rebuild 镜像；deploy.sh 仓库直构） | **v2.0.40** · [CHANGELOG](macro-sim/CHANGELOG.md) | `/vol2/1000/software/world-sim/macro-sim` |
| `macro-ji`   | 验证层（天玑）：读天枢 data 做推演验证/反哺（T2 共享触发文件驱动，2026-08-04 独立容器上线） | **COPY 模式**（macro-ji/ 目录 rebuild） | v1.0.0 · [CHANGELOG](macro-ji/CHANGELOG.md) | `/vol2/1000/software/world-sim/macro-ji` |
| `kaiyang`    | 可视化操作面板：只读展示天枢数据 + 控制台（:8080，control API :8900） | nginx 静态站（MOCK_ENABLED=false，A3a 已接入，index.html no-cache） | v1.9.0 · [CHANGELOG](kaiyang/CHANGELOG.md) | `/vol2/1000/software/kaiyang` |

**数据流**：macro-scan 每日写入 `data/*.json` → macro-sim 只读消费 → kaiyang 只读展示；天玑（macro-ji）读天枢 data（forecast_tracker.db 三写者共存 + WAL）做验证闭环。

---

## 新 session 阅读路径

按顺序读取，每步均需完整阅读：

1. **本文件**（根 `AGENTS.md`）— 了解系统全貌和操作约束
2. **`STATUS.md`**（repo 根）— 实时交接状态（部署拓扑/R4 主线/已知坑），08-10 起为实时交接权威（HANDOVER.md 为 08-07 历史快照）
3. **`S:\docs\INDEX.md` "活跃问题"节**（从"## 活跃问题"到"## Backlogs"之间，约30行）— 扫描当前所有 P1/P2 活跃问题；若 `S:\docs\` 不可达（非 NAS 环境），改读 `ROADMAP.md` 的时间门控任务表
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

**当前接口兼容版本**：macro-scan v3.8.16+ ↔ macro-sim **v2.0.40+**（grv v1.0 / news v1.0，as-of 2026-08-10）

接口 schema 变更规则：同时改两边 AGENTS.md 的接口契约节 → 两边 CHANGELOG 各追加 → 先升 macro-scan 验证输出 → 再升 macro-sim。

---

## 子系统详细指南

- **macro-scan 完整工作指南** → [`macro-scan/AGENTS.md`](macro-scan/AGENTS.md)
- **macro-sim 完整工作指南** → [`macro-sim/AGENTS.md`](macro-sim/AGENTS.md)
- **kaiyang 完整工作指南** → [`kaiyang/AGENTS.md`](kaiyang/AGENTS.md)

---

## 人类文档导航（非 AI 用）

- **系统总览**（推荐入口）→ [`docs/overview.md`](docs/overview.md)
- **实时交接状态** → [`STATUS.md`](STATUS.md)（08-10 起权威；[`HANDOVER.md`](HANDOVER.md) 为 08-07 历史快照）
- **时间门控路线图** → [`ROADMAP.md`](ROADMAP.md)
- **校准评审实录** → [`docs/calib/`](docs/calib/)（calib-*.md）+ 天璇操作日志 `macro-sim/docs/operations/`
- **架构裁定（2026-08-02）** → [`docs/arch_review_20260802.md`](docs/arch_review_20260802.md)
