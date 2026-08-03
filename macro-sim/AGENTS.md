# macro-sim（天璇）— Agent 工作指南

> **如在 monorepo 中工作，先读根目录 [`../AGENTS.md`](../AGENTS.md)（系统全貌 + 阅读路径入口）。**

## 项目概览

世界推演系统仿真层（天璇）：12个宏观角色在月度时间步长上互动演化，输出概率路径树。

**定位**：macro-scan（天枢）发现信号 → macro-sim（天璇）演化未来（不是推理，是演化）

**当前版本**：v2.0.17（2026-08-03）  
**主要变更**：D1/D4/D7/D12 P0 bug 修复；GRV 13维全部接入 MacroWorldState（含 social_stress/cultural_friction）

---

## 目录结构

```
macro-sim/                ← 本地工作目录（S:\world-sim\macro-sim\，git 仓库子目录）
├── core/
│   ├── agents/
│   │   ├── base.py         # MacroAgent 基类 + AgentParams（三参数接口）
│   │   ├── financial.py    # A1/A2/A3/A5/A9/A11/A12
│   │   ├── geopolitical.py # A4/A7/A8
│   │   └── social.py       # A6/A10
│   ├── world_state.py      # MacroWorldState + 出血规则 + 月度数据加载
│   ├── simulation.py       # 主调度器（action_history 队列 + 延迟可见）
│   ├── calibrator.py       # 前50步校准循环
│   ├── bifurcation.py      # 路径分叉检测 + Monte Carlo × 100
│   ├── llm_client.py       # LLM 调用封装（GLM / MiniMax）
│   └── sim_log.py          # sim_log.db 持久化
├── config/
│   └── agents.yaml         # 12个 Agent 配置（热更新）
├── docs/
│   ├── design_v2.md        # v2 架构设计（已确认）
│   └── PROGRESS.md         # 开发进度
├── output/                 # 仿真输出（不在 git 里）
├── run.py                  # 入口（--daemon / --run / --predict-only）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── AGENTS.md               # 本文件
├── CHANGELOG.md
└── VERSION
```

---

## AI 阅读路径

| 文件 | 何时读 |
|---|---|
| `AGENTS.md`（本文件）| **每次 session 必读** |
| `CHANGELOG.md` 前 50 行 | **每次 session 必读**（了解最新改动，新版在前，读头部）|
| `docs/design_v2.md` | 涉及架构设计决策时 |
| `docs/PROGRESS.md` | 了解当前开发进度和各模块完成状态时 |
| `core/world_state.py` | 涉及状态变量或数据加载时 |
| `core/simulation.py` | 涉及 Agent 行为或 GM 规则时 |
| `core/calibrator.py` | 涉及校准逻辑时 |
| `core/bifurcation.py` | 涉及路径分叉 / 报告生成时 |
| `config/agents.yaml` | 涉及 Agent 参数 / 新增角色时 |

---

## 核心设计原则

1. **每步 = 1个月**，100步（前50校准 + 后50预测，实际预测24步）
2. **Agent 互相可见**：每个 Agent 按 `info_delay` 看到历史行动，对冲基金即时，美联储4个月后
3. **三参数接口**：每个 Agent 暴露 `sensitivity` / `threshold` / `magnitude`，校准期 LLM 自动调整
4. **新增角色只加 config**：`agents.yaml` 里加一条，代码无需改动
5. **数据单位**：FRED T10Y2Y / BAA10Y 单位是 `%`，存入 world_state 时需 ×100 转 bp

---

## 运行命令

```bash
# 守护模式（容器默认）
python run.py --daemon

# 完整仿真（校准50步 + 预测24步）
python run.py --run --level 2 --event "GRV告警"

# 快速预测（跳过校准）
python run.py --predict-only --level 2 --event "测试"
```

---

## 修改工作流

```bash
# macro-sim 是 COPY 模式，改代码后需重建镜像，用 deploy.sh 部署
# 在 world-sim monorepo 根目录执行：
bash /s/world-sim/deploy.sh macro-sim

# push 到 GitHub（在 S:\world-sim\ 执行）
git -C /s/world-sim add macro-sim/
git -C /s/world-sim commit -m "..."
git -C /s/world-sim -c http.proxy=http://192.168.31.108:7890 push origin main
```

---

## 维护铁律

1. 改动后必须 bump `VERSION` + 追加 `CHANGELOG.md`
2. `config/agents.yaml` 通过 `COPY` 打包进镜像，**修改后需重新部署**（`bash deploy.sh macro-sim`）
3. FRED 数据读取后需 ×100 转 bp（T10Y2Y / BAA10Y）
4. 校准期误差计算权重：GRV×0.4 + credit_spread×0.3 + t10y2y×0.2 + dff×0.1（测试后可调整）
5. 路径概率 <5% 的路径不展开推演

### 改代码后必须同步的文档

> **任务开始时**：用 TodoWrite 逐项列出本次涉及的每个文档更新目标（每个文件一条），不在收尾时回想。

**（改了左边 → 必须同时更新右边）**

| 改了什么 | 必须同时更新 |
|---|---|
| 任何 `core/*.py` | `VERSION`（PATCH）+ `CHANGELOG.md` |
| 任何 `core/*.py`（版本号变更时）| + `S:\docs\INDEX.md` 版本状态行（版本号 + 日期 + 一行摘要）|
| 任何 `core/*.py`（版本号变更时）| + `macro-sim_人类说明文档.md` 文件头版本号 |
| 任何 `core/*.py`（版本号变更时）| + `S:\world-sim\docs\overview.md` 头部版本行（`macro-sim vX.Y.Z`）+ 架构图版本号 |
| 任何 `core/*.py`（版本号变更时）| + `docs/PROGRESS.md`（版本号 + 版本历史表）|
| 任何 `core/*.py`（版本号变更时）| + `README.md`（天璇；当前动态引用"见 VERSION"，无静态版本号；纳入矩阵仅防未来漏改）|
| `core/world_state.py`（新增字段） | `docs/design_v2.md` |
| `config/agents.yaml`（新增 Agent）| `core/agents/` 对应子类 + README |
| 接口契约变更 | 两边 AGENTS.md 的接口契约节 + 两边 CHANGELOG |

---

## 路径架构（容器内）

| 宿主机路径 | 容器内路径 | 说明 |
|---|---|---|
| `output/` | `/app/output` | 仿真输出，volume mount |
| `sim_log.db` | `/app/sim_log.db` | 预测记录，volume mount |
| `config/agents.yaml` | `/app/config/agents.yaml` | Agent 配置 |
| macro-scan `data/` | `/app/macro_data:ro` | GRV/FRED/news，只读 |
| macro-scan `data/sim_trigger.json` | `/app/macro_data/sim_trigger.json` | 触发文件，读写（v2.0.14 改目录挂载，解决 inode 断链）|
| macro-scan `docs/仿真报告/` | `/app/reports` | 报告输出，读写 |

---

## 与 macro-scan 的接口契约

**版本兼容表：**

| macro-scan | macro-sim | 接口 schema |
|---|---|---|
| v3.8.5+   | v2.0.17+   | grv v1.0 / news v1.0 |

**接口变更三步走：**
1. 同时更新两边 AGENTS.md 的本节
2. 两边 CHANGELOG 各追加一条
3. 部署顺序：先升 macro-scan → 验证输出 → 再升 macro-sim

**macro-scan → macro-sim 数据文件：**

- `grv_history.jsonl`：GRV 快照序列（1985~2026-06 月频，2026-07 起日频），校准循环读取。⚠️ **读基线时应按日期范围（6个月前）查找，不应用行偏移 `lines[-N]`**
- `grv_latest.json`：当前 GRV，需含 `_schema_version: "1.0"`。完整 13 维（v2.0.16-17 D7 fix，全部接入 MacroWorldState）：taiwan_strait / us_china_strategic / russia_europe / middle_east_energy / global_composite / climate_risk / disaster_risk / sanctions_risk / seismic_risk / energy_grid_risk / japan_monetary / social_stress / cultural_friction。social_stress / cultural_friction 由 geo_risk_vector.py 从 gdelt_scores 聚合后写入此文件
- `fred_history/T10Y2Y.csv` / `BAA10Y.csv` / `DFF.csv`：FRED 日度数据，单位 `%`，读取后 ×100 转 bp
- `news_export.json`：近7天新闻，需含 `_schema_version: "1.0"`
- `sim_trigger.json`：触发文件，格式 `{"level":3,"event":"...","triggered_at":"..."}`

---

## 新 session 快速继续

> 如在 monorepo 中工作，先读根目录 `../AGENTS.md`（系统全貌 + 阅读路径入口）。此提示在文件头部已重复，请忽略本行。

```
读 AGENTS.md → 读 CHANGELOG.md 前 50 行 → 按需读 docs/design_v2.md
→ 确认当前版本和状态，然后开始工作
```
