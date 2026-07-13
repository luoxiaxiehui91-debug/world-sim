# 宏观演化仿真系统（macro-sim）· 使用与维护手册

> 版本：v2.0.4 | 更新日期：2026-07-13

---

## 一、这是什么

macro-sim 是世界推演系统的**仿真引擎层**。它以 macro-scan（数据观测层）每日写入的宏观指标为输入，将12个角色各异的宏观 Agent 放进一个时间轴中，让它们按照各自的信息延迟和传导系数相互影响、演化，最终输出**未来24个月的概率路径树**，以及每条路径的 LLM 叙事说明。

macro-scan 负责"测量现实"，macro-sim 负责"模拟未来"。两者通过 `sim_trigger.json` 文件接口解耦，互不直接调用。

---

## 二、工作原理（简版）

### 数据来源

macro-sim 从以下路径读取数据（容器内挂载为 `/app/data/`，对应 NAS 路径 `/vol2/1000/software/macro-scan/data/`）：

- **触发文件**：`sim_trigger.json`——触发仿真的信号，由 macro-scan 在 GRV 告警时写入
- **月度历史数据**：macro-scan 历史写入的月度指标文件，供校准循环使用（`load_monthly_history()` 加载）
- **当前真实状态**：macro-scan 最新数据，作为预测循环的起点（`load_from_macro_scan()` 加载）

### 校准循环（前50步）

每步对应1个月，前50步覆盖约4年历史。每步流程：

1. 读取该月历史真值（grv / t10y2y / credit_spread / dff）
2. 用当前 Agent 参数仿真一步
3. 计算加权误差：`GRV×0.4 + credit_spread×0.3 + t10y2y×0.2 + dff×0.1`
4. 误差 > 0.15 时，调用 LLM（GLM-Z1-9B）自动调整 Agent 参数
5. 调参记录写入 `calibration_log.jsonl`

50步结束后输出校准评分（0~100）。评分 < 60 时，报告会标注"预测可信度低"。

### 预测循环（后24步）

1. 以 macro-scan 当前实时数据为起点，加载当前世界状态
2. Monte Carlo × 100：对初始内生变量加随机扰动，跑100次平行仿真
3. 路径分叉检测：对100条轨迹做双峰检验，发现明显分叉则聚类
4. 输出最多3条主路径（概率 ≥ 5%），每条路径含 GRV 轨迹、关键节点、LLM 叙事

### 输出

报告写入容器内 `/app/reports/`，文件名格式：

```
YYYY-MM-DD_仿真_校准{score}.md
```

NAS 上对应路径为 `/vol2/1000/software/macro-scan/docs/仿真报告/`，本机路径 `S:\world-sim\macro-scan\docs\仿真报告\`（报告写入 macro-scan 侧，非 macro-sim 侧）。

同时通过 ntfy 推送摘要到手机（`https://ntfy.sh/***REMOVED***`）。

---

## 三、如何触发

### 自动触发（正常运行路径）

macro-scan 在检测到 GRV 告警时，自动写入触发文件：

```json
{"level": 3, "event": "GRV告警"}
```

写入路径（NAS）：`/vol2/1000/software/macro-scan/data/sim_trigger.json`

macro-sim 在 daemon 模式下每分钟轮询此文件，发现后立即启动完整仿真，完成后删除该文件。

### 手动触发

SSH 登录 NAS 后执行：

```bash
echo '{"level":3,"event":"手动触发"}' > \
  /vol2/1000/software/macro-scan/data/sim_trigger.json
```

level 取值含义：1=低风险 / 2=中等 / 3=高风险告警。

### daemon 模式说明

容器默认启动命令为 `python run.py --daemon`，以1分钟间隔轮询 `sim_trigger.json`。守护进程不需要手动管理，容器重启后自动恢复。

---

## 四、查看报告

### 报告位置

| 访问方式 | 路径 |
|---|---|
| NAS 直接访问 | `/vol2/1000/software/macro-scan/docs/仿真报告/` |
| 本机挂载路径 | `S:\world-sim\macro-scan\docs\仿真报告\` |

### ntfy 推送内容

每次仿真完成后，手机会收到 ntfy 推送，包含：

- 触发事件和告警等级
- 校准评分
- 主要路径数量及概率
- 各路径 GRV 趋势摘要

### 报告结构说明

报告为 Markdown 格式，包含以下部分：

1. **校准质量**：评分、主要误差来源说明
2. **核心结论对比表**：各路径在关键指标上的预测值对比（grv / t10y2y / credit_spread / dff）
3. **路径传导链**：每条路径的因果箭头链（如"美联储降息 → 商业银行放贷 → 散户情绪改善"）
4. **LLM 叙事（三段结构）**：情景定性 / 传导链描述 / 投资影响分析
5. **校准说明**：本次调参过程的关键记录

---

## 五、运维操作

### 查容器状态

```bash
# SSH 登录 NAS
ssh TSX@192.168.31.108

# 查看容器运行状态
docker ps | grep macro-sim
```

### 查日志

```bash
# 实时日志（最近100行）
docker logs macro-sim --tail 100 -f

# 查看仿真记录数据库（在容器内）
docker exec macro-sim python -c "
from core.sim_log import SimLog
log = SimLog()
log.show_recent(10)
"
```

### 重建部署

代码采用 COPY 模式打包进镜像，修改代码后必须重建镜像。在本机执行：

```bash
bash /s/world-sim/deploy.sh macro-sim
```

该脚本会完成：构建新镜像 → 停止旧容器 → 启动新容器。

注意：`config/agents.yaml` 通过 Dockerfile `COPY config/` 打包进镜像，修改参数后同样需要重建镜像（见第七节）。

### 容器内手动跑一次仿真

```bash
# 进入容器
docker exec -it macro-sim bash

# 完整仿真（校准 + 预测）
python run.py --run --level 2 --event "手动测试"

# 快速预测（跳过校准，用于调试）
python run.py --predict-only --level 2 --event "快速测试"
```

---

## 六、当前已知问题与开发状态

### 模块完成状态

| 模块 | 文件 | 状态 |
|---|---|---|
| Agent 基类 + 三参数接口 | `core/agents/base.py` | ✅ 完成 |
| 12个 Agent 实现 | `core/agents/financial/geopolitical/social.py` | ✅ 完成 |
| Agent 配置热更新 | `config/agents.yaml` | ✅ 完成 |
| 世界状态（含内生变量） | `core/world_state.py` | ✅ 完成 |
| 主仿真调度 | `core/simulation.py` | ✅ 完成 |
| 月度历史数据加载 | `core/world_state.load_monthly_history()` | ✅ 完成 |
| 校准循环 | `core/calibrator.py` | ✅ 完成 |
| 路径分叉检测 | `core/bifurcation.py` | ✅ 完成 |
| 报告生成 + LLM 叙事 | `run.py` / `core/bifurcation.py` | ✅ 完成 |
| daemon 守护模式 | `run.py --daemon` | ✅ 完成 |
| ntfy 推送 | `run.py` | ✅ 完成 |
| 仿真记录 | `core/sim_log.py` | ✅ 完成 |

### 已知问题

**1. 校准质量偏低（优先级：中）**

当前校准评分约 70/100。主要原因是 GRV 历史数据在 2022–2026 期间月度波动剧烈（±30），仿真难以追随。

改进方向（尚未实施）：
- 对 GRV 历史做3个月移动平均平滑，降低噪声
- 给 LLM 提供最近5步误差趋势，避免参数反复横跳

**2. 路径多样性低（优先级：低，当前可接受）**

在 GRV=80 的高压环境下，约98%的路径走向压力区，路径B 概率仅5%。根本原因是高压环境下大多数 Agent 倾向收紧，没有明显分歧。这反映了当前宏观环境的真实特征，暂不视为缺陷。

**3. 校准参数与预测参数分离（优先级：低）**

校准期调参较激进，导致预测时系统偏保守、路径多样性下降。改进方向：预测时使用初始默认值与校准值的加权平均，而非直接沿用校准结果。

---

## 七、配置说明

### agents.yaml 修改说明

`config/agents.yaml` 通过 Dockerfile 的 `COPY config/ ./config/` 打包进镜像，**修改参数后必须重建镜像**：

```bash
bash /s/world-sim/deploy.sh macro-sim
```

可修改的内容：
- 各 Agent 的 `sensitivity` / `threshold` / `magnitude` 默认参数
- `activation_prob`（激活概率）
- `info_delay`（信息延迟步数）
- `transmission_coefficients`（传导系数）

新增 Agent 角色只需在 yaml 中追加一条配置，无需改动 Python 代码（接口已预留）。

文件位置：

| 访问方式 | 路径 |
|---|---|
| 本机 | `S:\world-sim\macro-sim\config\agents.yaml` |
| NAS | `/vol2/1000/software/macro-sim/config/agents.yaml` |

### 关键环境变量

以下变量在 docker-compose.yml 的 `environment` 段中配置：

| 变量名 | 说明 | 示例值 |
|---|---|---|
| `REPORT_DIR` | 报告输出目录（容器内路径） | `/app/reports` |
| `SILICONFLOW_API_KEY` | 硅基流动 API 凭证（LLM 降级链）| 见 docker-compose.yml |
| `MINIMAX_API_KEY` | MiniMax API 凭证（LLM 调用）| 见 docker-compose.yml |

其他环境变量待补充（需查阅 docker-compose.yml 完整内容）。

### 数据接口说明

macro-sim 消费的数据由 macro-scan 产出，当前使用的世界状态外生变量为：

| 变量 | 含义 | 单位 |
|---|---|---|
| `grv` | 全球风险值 | 0~100 |
| `t10y2y` | 10年-2年美债利差 | bps |
| `credit_spread` | 信用利差（BAA-10Y） | bps |
| `dff` | 联邦基金利率 | % |

内生变量（仿真演化，不依赖外部数据）共10个，含 `market_sentiment`、`bank_credit_tightening`、`retail_panic`、`china_credit_impulse`、`yen_carry_risk` 等，详见 `core/world_state.py`。

---

## 八、下一步计划

以下来自 PROGRESS.md 记录的待改进项，按优先级排列：

**中优先级：**

- [ ] 对 GRV 历史数据做3个月移动平均平滑，改善校准质量（目标：评分从70提升至80+）
- [ ] 给 LLM 调参时附带最近5步误差趋势，减少参数振荡

**低优先级：**

- [ ] 校准参数与预测参数分离：预测时使用初始值和校准值的加权平均，改善路径多样性
- [ ] 扩充 Agent 知识库引用（`knowledge_base_ref` 字段，A2/A3/A5/A7/A9/A10 尚未填充）

**预留接口（后续扩展）：**

- `transmission_coefficients` 跨国联动矩阵已在 agents.yaml 中定义，后续可接入推演系统同步
- 新增宏观 Agent 角色只需在 agents.yaml 追加配置，代码接口已预留
