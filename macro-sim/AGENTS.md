# macro-sim（天璇）— Agent 工作指南

> **如在 monorepo 中工作，先读根目录 [`../AGENTS.md`](../AGENTS.md)（系统全貌 + 阅读路径入口）。**

## 项目概览

世界推演系统仿真层（天璇）：**20个宏观角色**（13 金融 A1-A13 + 7 主权 S1-S7，08-18 扩展）在月度时间步长上互动演化，输出概率路径树。

**定位**：macro-scan（天枢）发现信号 → macro-sim（天璇）演化未来（不是推理，是演化）

**当前版本**：**v2.0.41**（2026-08-18）  
**主要变更**（08-17/18 大版本，详见 CHANGELOG v2.0.41）：
- **soul 政权分片**：`_resolve_soul_by_month`（simulation.py）——soul `regimes:` 时间片按历史月切换"当时政权风格"；5 主权红线阈值按 GRV 实测分布校准
- **政权更迭引擎**：`core/governance.py` 内生事件（民主换届 / 长期执政继承 / 政变，`_gov_done` 一次性锁定）；`--as-of YYYY-MM` 情景开关
- **A13 长线资金 + S6/S7 日韩主权**：逆周期稳定者 / 准一党制 / 单任期强制轮替；A2 hybrid soul 化、A10 散户三派系
- **预测描述清晰化**：`bifurcation.py` 模块级 `_ACTION_LABELS`/`_ACTION_CRITERIA` + `label_to_action_key`；geo 预测带路径 GRV 上下文 + 现实判定标准
- **人工验证渠道**：`verify_human.py` CLI + `backfill_criteria.py`（历史判据/action_key 回填）

---

## 目录结构

```
macro-sim/                ← 本地工作目录（S:\world-sim\macro-sim\，git 仓库子目录）
├── core/
│   ├── agents/
│   │   ├── base.py         # MacroAgent 基类 + AgentParams（三参数接口）+ _decide_soul hybrid 分支 + red_line 冷却
│   │   ├── financial.py    # A1/A2/A3/A5/A9/A11/A12 + A13 LongTermCapitalAgent（逆周期稳定者）
│   │   ├── geopolitical.py # A7/A8（A4 已改由 sovereign.EnergyGovSovereignAgent 承担）
│   │   ├── social.py       # A6/A10（A10 已 soul 化：恐慌/FOMO/观望）
│   │   └── sovereign.py    # SovereignAgent 基类 + EnergyGovSovereignAgent（S5_saudi）+ 派系 60/40 概率选择
│   ├── world_state.py      # MacroWorldState + 出血规则 + 月度数据加载
│   ├── simulation.py       # 主调度器（action_history 队列 + 延迟可见）+ _resolve_soul_by_month + 政权分片
│   ├── calibrator.py       # 前50步校准循环（每步按历史月份切 regime）
│   ├── bifurcation.py      # 路径分叉检测 + Monte Carlo × 100 + _ACTION_LABELS/_ACTION_CRITERIA（模块级）
│   ├── governance.py       # 08-17 政权更迭引擎（election/succession/coup 内生事件）
│   ├── llm_client.py       # LLM 调用封装（开阳统一配置 llm_config.json，60s TTL）
│   └── sim_log.py          # sim_log.db 持久化
├── config/
│   └── agents.yaml         # 20个 Agent 配置（A1-A13 金融 + S1-S7 主权，热更新）
├── souls/                  # soul 文件：A1_usa/A2_china/A3_eu/S4_russia/S5_saudi + A10_retail/A2_bank + S6_japan/S7_korea
├── docs/
│   ├── design_v2.md        # v2 架构设计（已确认）
│   └── PROGRESS.md         # 开发进度
├── output/                 # 仿真输出（不在 git 里）
├── run.py                  # 入口（--daemon / --run / --predict-only / --force-activate-all / --as-of）
├── verify_human.py         # 08-17 人工验证 CLI（--list / --verify <id> --outcome 0|0.5|1 [--note]）
├── backfill_criteria.py    # 08-18 历史预测判据/action_key 回填（--dry-run）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── AGENTS.md               # 本文件
├── CHANGELOG.md
└── VERSION
```

---

## 天璇 LLM 推演重设计（2026-08-24~26，设计收官，GRV 锚定待修）

> 设计阶段已收官（蓝图 v6 五轮评审定稿），但**仿真引擎 GRV 锚定机制**是当前唯一 active 卡点，接手 agent 从「修复 GRV 聚合回写」起步。完整交接见中央知识库 `S:\docs\decisions\world-deduction\0012a-tianji-sim-redesign-blueprint.md`（蓝图 v6）+ `0012-math-mc-kernel-over-llm-agents.md`（ADR-0012）。

**为什么做**：原天璇是纯数学 MC 引擎（soul 规则），LLM 仅做叙事。重设计把 LLM 升为「事件响应 / what-if 决策玩家」双内核之一（数学 MC 仍是常态基线），目标是在外生冲击下让 LLM 主权/市场 agent 真正改变推演路径。

**四阶段实施现状（截至 2026-08-26）**：
- 阶段0 验证标尺 ✅ 入库：`core/backtest_eval.py`（commit 07e2a77d9），裸推基线 vol_ratio=0.001 存档 gate_baseline.json。
- 阶段1 决策质量 ◐ 部分入库：`core/agents/llm_pilot.py`（v3，max_tokens=1024 + TPM 令牌桶，commit 30dbf474b）；checkpoint 编排推迟。
- 阶段2 外生事件注入层 ◐ 工作树完成未提交：`core/exogenous_events.py`（118 行，三通道 + 传导告警 + 窗口过滤 457→49 事件月）。
- 阶段3 S 类 LLM 灰度 ◐ 工作树完成未提交：`core/agents/sovereign.py`（七国动态 persona + 挂 mixin，M）、`core/agents/llm_pilot.py`（v4 动态 persona dict，M）。

**门控实验结论（v4/v5 均已跑，关键发现）**：
- v4（事件注入 + A 类试点集）：corr=0.207 / dir_rate=20% / **vol_ratio=0.001 与裸推完全相同**。根因 = S 类无 mixin 且活跃概率 0.2，事件到不了 GRV 驱动者。
- v5（事件 + S 类全 LLM）：corr=0.207 / dir_rate=20% / **vol_ratio=0.001 仍不变**。根因 = 更深层的 GRV 锚定机制（见下）。
- 结论：事件与 LLM 决策对「被度量的标量 GRV」零可观测影响 → **根因锁定在仿真引擎 GRV 锚定/阻尼机制，不在事件注入或 LLM 决策层**。

**⚠️ 当前卡点：GRV 锚定机制根因（只读调查，未改码，待用户拍板修复）**：
- 现象：标量 `world.grv`（backtest_eval 度量对象，0-100 全球综合风险）无论注入多少事件/LLM 主权决策，恒向自身 baseline 收敛 → vol_ratio=0.001。
- 代码实证：
  ① `world.grv` 全库**仅一处被改写**：`core/world_state.py:345` `apply_natural_decay` 的均值回归 `world.grv = world.grv*0.97 + world.grv_baseline*0.03`；
  ② `step()` 每步还有 `board_decay_step` + `apply_bleed_rules` 两道阻尼，合力把 GRV 拉回 baseline；
  ③ LLM/S 类决策只写**并行 dict `grv_dimensions`**，该 dict **从不回聚到标量 `world.grv`** → agent 决策与「被度量的标量」彻底解耦；
  ④ `grv_baseline` 由历史 GRV 初始化后随机游走，不受任何 agent 决策影响。
- 本质：**标量 GRV 是封闭均值回归环，agent 决策通道是旁路字典**，故 vol_ratio 恒 0.001。
- 修复方向（待独立阶段 + 用户拍板 + git + rebuild）：`step()` 末增加 `grv_dimensions → world.grv` 聚合回写，须先对齐「数学 MC GRV（官方口径）vs LLM 沙盘 GRV（推演标注）」双内核语义（蓝图 v6 已声明区分，但回写实现须此前提）。

**⚠️ 部署态警示（交接阻断项）**：
- 阶段 2/3 代码 `exogenous_events.py`(untracked) / `sovereign.py`(M) / `llm_pilot.py`(v4, M) **尚未 commit**；容器靠 docker cp 临时注入、镜像不含 → **rebuild 即丢失**。
- 接手第一动作建议：`git add` + commit 捕获现状（单 commit 标注「阶段2/3 事件注入 + S 类 LLM 工作树」），再择机 rebuild 烘焙进镜像 + 按阶段 1 回归清单重测。rebuild 前勿依赖容器现有注入态。

**权威文档**：
- 蓝图 v6（设计终态）：`S:\docs\decisions\world-deduction\0012a-tianji-sim-redesign-blueprint.md`
- ADR-0012（架构取舍，proposed；蓝图 v6 实际推翻其「LLM 退居叙事层」选项，以蓝图 v6 为准）：同目录 `0012-math-mc-kernel-over-llm-agents.md`
- 中央 KB 根 INDEX：`S:\docs\decisions\world-deduction\INDEX.md`

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
# macro-sim 是 COPY 模式，改代码后需重建镜像。deploy.sh 依赖 SSH 密码，现已失效，
# 需在 NAS 上手动重建（下面"手动 docker build"流程）：
# 1. 本机 rsync 同步代码到 NAS（或用 S:\ 映射直接改 NAS 文件）
#    rsync -av --exclude='.git' --exclude='output/' --exclude='sim_log.db' \
#          --exclude='__pycache__/' --exclude='*.pyc' macro-sim/ \
#          TSX@192.168.31.108:/vol2/1000/software/world-sim/macro-sim/
# 2. SSH 登录 NAS 后重建容器（macro-sim 为 COPY 模式镜像，必须重新 docker build）：
#    ssh nas
#    cd /vol2/1000/software/world-sim/macro-sim
#    docker build -t macro-sim:latest .
#    docker compose up -d --force-recreate
# 3. 若 deploy.sh 的 SSH 通道恢复（密码更新），仍可一键执行：
bash /s/world-sim/deploy.sh macro-sim

# push 到 GitHub（在 S:\world-sim\ 执行）
git -C /s/world-sim add macro-sim/
git -C /s/world-sim commit -m "..."
git -C /s/world-sim -c http.proxy=http://192.168.31.108:7890 push origin main
```

---

## 维护铁律

1. 改动后必须 bump `VERSION` + 追加 `CHANGELOG.md`
2. `config/agents.yaml` 通过 `COPY` 打包进镜像，**修改后需重新部署**（NAS 手动 docker build，见"修改工作流"）
3. FRED 数据读取后需 ×100 转 bp（T10Y2Y / BAA10Y）
4. 校准期误差计算权重（v2.0.20 起为**内生变量**权重）：market_sentiment×0.35 + bank_credit_tightening×0.30 + liquidity_premium×0.20 + em_capital_outflow×0.15（旧外生权重 grv×0.4+credit_spread×0.3+t10y2y×0.2+dff×0.1 已废弃）
5. **部署铁律（08-21 教训）**：改 `run.py` / `config/` 等 **COPY 进镜像**的文件后，**必须**在 git 真源执行 `cd /vol2/1000/software/world-sim/macro-sim && docker build -t macro-sim:latest . && docker compose up -d --force-recreate`，否则改动不生效（容器跑旧代码）。**验收**：`docker inspect -f "{{.State.StartedAt}}" macro-sim` 晚于代码提交时间。改 git 不重建容器 = 未部署。
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
| macro-scan `data/` | `/app/macro_data:rw` | GRV/FRED/news，读写（v2.0.20+ 改 rw，sim_trigger 同目录挂载）|
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
- `grv_latest.json`：当前 GRV，需含 `_schema_version: "1.0"`。完整 16+1 维（16 个风险子维度 + 1 个合成 global_composite；D7 fix 后全部接入 MacroWorldState）：taiwan_strait / us_china_strategic / russia_europe / middle_east_energy / global_composite / climate_risk / disaster_risk / sanctions_risk / seismic_risk / energy_grid_risk / japan_monetary / social_stress / cultural_friction / global_south / india_pacific / korean_peninsula / south_china_sea。social_stress / cultural_friction 由 geo_risk_vector.py 从 gdelt_scores 聚合后写入此文件
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
