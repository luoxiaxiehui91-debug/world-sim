# world-sim — AI 工作入口

**系统定位**：macro-scan 持续观测全球宏观信号 → macro-sim 演化未来路径（不是推理，是演化）。

---

## 两个子系统

| 子系统 | 定位 | 容器模式 | 版本文件 | NAS 运行目录 |
|:-------|:-----|:---------|:---------|:-------------|
| `macro-scan` | 数据观测层：实时抓取 FRED/GPR/新闻/地缘信号，生成 GRV 向量 | **热挂载**（改代码即生效，无需 restart） | `macro-scan/VERSION` | `/vol2/1000/software/macro-scan` |
| `macro-sim`  | 仿真引擎层：12个 Agent，Monte Carlo×100，月度时间步长 | **COPY 模式**（改代码需 rebuild 镜像） | `macro-sim/VERSION` | `/vol2/1000/software/macro-sim` |

**关系**：macro-scan 每日写入数据文件（`data/grv_latest.json`、`data/fred_history/*.csv`、`data/news_export.json`）→ macro-sim 以只读方式挂载同一 `data/` 目录消费这些文件。

---

## 新 session 阅读路径

按顺序读取，每步均需完整阅读：

1. **本文件**（根 `AGENTS.md`）— 了解系统全貌和操作约束
2. **`macro-scan/TuiYan_CHANGELOG.md` 最后 20 行** — 了解 macro-scan 最新变更状态
3. **`macro-sim/CHANGELOG.md` 最后 20 行** — 了解 macro-sim 最新变更状态
4. 按任务分支：
   - 处理 macro-scan 任务 → 读 `macro-scan/AGENTS.md`（完整工作指南）
   - 处理 macro-sim 任务 → 读 `macro-sim/AGENTS.md`（完整工作指南）

---

## 关键操作约束

| 约束 | 说明 |
|:-----|:-----|
| NAS 挂载 | `S:\world-sim\` 是 NAS 网络挂载（`\\192.168.31.108\software\`），不是本地磁盘，删除文件前必须二次确认 |
| git 路径 | 所有 git 命令用 `git -C /s/world-sim`，不能 `cd` 进去 |
| push 走代理 | `git -C /s/world-sim -c http.proxy=http://192.168.31.108:7890 push origin main` |
| macro-scan 热挂载 | 改 `S:\world-sim\macro-scan\核心代码\*.py` 立即生效，**不**需要 restart |
| macro-sim COPY | 改代码后必须重建镜像：`bash /s/world-sim/deploy.sh macro-sim` |
| deploy.sh macro-scan | 只做 rsync + `docker compose restart`（不重建镜像） |
| 改前必读 | 改任何文件前先读对应子系统的 CHANGELOG（两个系统都有各自铁律） |
| 改后必追加 | 追加 CHANGELOG + bump VERSION + 按联动矩阵更新联动文档 |
| `S:\docs\INDEX.md` | 版本变更时同步更新版本状态行（版本号 + 日期 + 一行摘要） |

---

## 数据接口契约（摘要）

macro-scan 每日按时写入，macro-sim 只读消费：

| 文件 | 写入时间 | 说明 |
|:-----|:---------|:-----|
| `data/grv_latest.json` | 06:10 | GRV 地缘风险向量（8维，含 `japan_monetary`），schema v1.0 |
| `data/fred_history/*.csv` | 05:30 | FRED 宏观指标（T10Y2Y / BAA10Y / DFF），值单位 `%`，读取后需 ×100 转 bp |
| `data/news_export.json` | 07:05 | 近7天新闻摘要（40条，6类），schema v1.0 |
| `data/sim_trigger.json` | 触发时 | L3+ 情境检测后写入，触发 macro-sim 仿真（**P4-B 计划中，尚未实现**） |

**当前接口兼容版本**：macro-scan v3.5.41+ ↔ macro-sim v2.0.2+（grv v1.0 / news v1.0）

接口 schema 变更规则：同时改两边 AGENTS.md 的接口契约节 → 两边 CHANGELOG 各追加 → 先升 macro-scan 验证输出 → 再升 macro-sim。

---

## 子系统详细指南

- **macro-scan 完整工作指南** → [`macro-scan/AGENTS.md`](macro-scan/AGENTS.md)
- **macro-sim 完整工作指南** → [`macro-sim/AGENTS.md`](macro-sim/AGENTS.md)
