# macro-sim v2 设计方案

> 状态：**已确认，已实现**（v2.0.x 全量落地；本文件为设计蓝图，部分参数以代码为准）
> 起草：2026-07-09  
> 确认：2026-07-09  
> 更新：2026-08-07（同步 v2.0.24 现状；A 类激活后新增 S1-S5，详见 `a-class-sovereign-activation.md` 与 `tianxuan-v3-soul-redesign.md`）

---

## 一、核心定位（重新确认）

macro-scan = 推理机：拿已知数据沿逻辑链推一步  
macro-sim = 模拟机：把世界和 Agent 放进去，让它们按关系演化，结果从互动中涌现

**每步 = 1个月。共 100 步：前 50 步（约4年）拟合历史，后 50 步预测（实际预测 24 步，以代码为准）。**

步长选月度原因：GRV 可用的连续历史数据是月度（1985年至今），日度数据目前只有约8天不够校准。FRED 日度数据降采样到月度没有损失。每步1个月也更符合系统定位——预测未来4年的演化路径，是 macro-scan 完全做不到的时间跨度。

---

## 二、12 个 Agent

| ID | 角色 | 信息延迟 | 激活概率 | 主要行为 |
|---|---|---|---|---|
| A1 | 美联储 | 4步 | 0.30 | 加息/降息/口头干预 |
| A2 | 商业银行 | 2步 | 0.70 | 收紧/放松信贷 |
| A3 | 对冲基金 | 0步 | 1.00 | 做空/做多/降险 |
| A4 | 能源国(OPEC+) | 5步 | 0.20 | 减产/增产 |
| A5 | 机构投资者 | 2步 | 0.60 | 增/降风险敞口 |
| A6 | 媒体/舆论 | 1步 | 0.80 | 放大恐慌/中性报道 |
| A7 | 新兴市场央行 | 3步 | 0.40 | 资本管制/加息/降息 |
| A8 | 中国央行/财政 | 3步 | 0.50 | 降准/降息/专项债/汇率管控 |
| A9 | 美国财政部 | 4步 | 0.30 | 发债/财政刺激/债务上限 |
| A10 | 散户/羊群 | 0步 | 0.90 | 跟随媒体和机构，放大波动 |
| A11 | 欧洲央行 | 4步 | 0.30 | 欧元利率/QE/紧缩 |
| A12 | 日本央行 | 4步 | 0.25 | YCC调整/套息平仓触发流动性 |

**预留接口**：Agent 列表从 YAML 配置文件加载，后续增加角色只需加配置，不改代码。

---

## 三、每个 Agent 暴露三个可调参数

```python
@dataclass
class AgentParams:
    sensitivity: float  # 对信号的反应灵敏度，校准期主要调这个，范围 0.1~2.0
    threshold:   float  # 触发行动的最低信号强度，范围 0.0~1.0
    magnitude:   float  # 行动对世界状态的影响幅度，范围 0.1~2.0
```

默认值 sensitivity=1.0, threshold=0.5, magnitude=1.0（基准，无放大无缩小）。

校准期 LLM 输出调整指令，格式：
```json
{
  "agent": "A2",
  "param": "threshold",
  "old": 0.50,
  "new": 0.35,
  "reason": "现实中商业银行在GRV上升初期就收紧，阈值偏高"
}
```

参数变更历史全部记录在 `calibration_log.jsonl`，可回溯。

---

## 四、Agent 之间的可见性（信息延迟分层）

每步开始时，每个 Agent 除了读世界状态，还能看到其他 Agent **延迟后**的行动：

```
即时可见（0步延迟）：媒体报道、市场价格变动
1步延迟：对冲基金行动、散户行动（机构次日才看到）
2步延迟：商业银行信贷决策
3步延迟：各国央行政策（等官方声明）
```

具体实现：维护一个 `action_history` 队列，每个 Agent 按自己的延迟档读取：

```python
ctx["visible_actions"] = {
    "media":      action_history[-1].get("A6"),   # 昨天的媒体报道，即时可见
    "hedge_fund": action_history[-1].get("A3"),   # 昨天对冲基金动作，1步后可见
    "fed":        action_history[-3].get("A1"),   # 3天前美联储声明，4步后可见
    # ...按 Agent 的信息延迟档分配
}
```

---

## 五、世界状态变量

### 外生变量（有历史真值，用于校准）

| 变量 | 历史数据来源 | 说明 |
|---|---|---|
| `grv` | grv_history.jsonl | GRV综合指数 |
| `t10y2y` | fred_history/T10Y2Y.csv | 收益率曲线斜率 |
| `credit_spread` | fred_history/BAA10Y.csv | 信用利差 |
| `dff` | fred_history/DFF.csv | 联邦基金利率 |

### 内生变量（仿真中演化，无直接历史真值）

`market_sentiment`, `bank_credit_tightening`, `fund_risk_appetite`,  
`liquidity_premium`, `energy_supply_risk`, `em_capital_outflow`,  
`retail_panic`, `china_credit_impulse`, `us_fiscal_pressure`, `yen_carry_risk`

后四个是新增的，对应新增 Agent。

---

## 六、校准循环（前 50 步）

```
每步流程：
  1. 从历史数据读取当天的真实外生变量
  2. 运行仿真一步（12 Agent 决策 → GM规则 → 内生变量更新）
  3. 计算误差（v2.0.20 起为内生变量权重，以代码为准）：
       误差 = market_sentiment×0.35 + bank_credit_tightening×0.30
            + liquidity_premium×0.20 + em_capital_outflow×0.15
       （原设计 GRV×0.4+credit_spread×0.3+t10y2y×0.2+dff×0.1 外生权重已在 v2.0.20 废弃）
  4. 误差 > 阈值（内生变量阈值默认 0.20）？
       → LLM 分析偏差原因 → 输出参数调整指令 → 更新对应 Agent 参数
       （方向相反时误差 ×1.5 惩罚，鼓励方向正确优先于幅度）
  5. 记录本步误差、参数状态到 calibration_log.jsonl
```

50步结束后输出校准报告：
- 每个 Agent 的参数从初始值变化了多少
- 误差曲线（哪些步拟合好，哪些步差）
- 拟合质量评分（0~100）：评分 < 60 则警告"预测可信度低"

---

## 七、预测循环（后 24 步）

用校准后的 Agent 参数，从当前真实状态出发：

**Monte Carlo × 100**：每次给初始内生变量加微小随机扰动（从历史波动率采样），外生变量让仿真自由演化。

**路径分叉检测**：
- 每步检测 `grv` 和 `market_sentiment` 的分布形状
- 双峰检验（Hartigan's dip test 简化版：检查分布是否有两个明显聚类）
- 发现双峰 → 记录分叉点，把100次运行按所属峰值分成两群，分别继续

**最终输出**：

```
后24步演化结果（示例，步号/数值以代码为准）
├─ 路径A（58%，62次运行）
│   GRV: 80 → 92 → 趋势：持续上升
│   关键节点：
│     第15步：A3对冲基金大规模做空（触发：GRV>85）
│     第20步：A1美联储紧急降息（触发：sentiment<-0.5）
│     第24步：A12日本央行放弃YCC，套息平仓触发流动性危机
│   叙事：[LLM生成，3-5句话]
│
└─ 路径B（42%，38次运行）
    GRV: 80 → 74 → 趋势：回落
    关键节点：
      第13步：A8中国央行降准50bp（触发：china_credit_impulse<-0.3）
      第19步：A9美国财政部扩大刺激（触发：us_fiscal_pressure>0.6）
    叙事：[LLM生成，3-5句话]
```

---

## 八、报告格式

写入 `docs/仿真报告/YYYY-MM-DD_仿真_校准{score}.md`，包含：

1. **校准质量**：评分、误差曲线摘要、参数调整记录
2. **预测路径树**：A/B（甚至C）路径，各含概率、关键节点、GRV/VIX轨迹
3. **量化指标**：每条路径的 GRV终值、credit_spread终值、传染概率
4. **AI叙事**：每条路径一段，说清楚"为什么会走这条路"

ntfy 推送摘要（手机可读）：
```
🔮 宏观演化仿真完成（校准评分78/100）
路径A（58%）：GRV持续上升至92，日本套息危机引爆
路径B（42%）：中美双宽松托底，GRV回落至74
关键节点：第20步美联储降息 / 第24步日元套息平仓
```

---

## 九、文件结构变化

```
macro-sim-src/
├── core/
│   ├── world_state.py      # 扩展内生变量，保留接口
│   ├── agents/
│   │   ├── base.py         # MacroAgent基类，含三参数接口
│   │   ├── financial.py    # A1/A2/A3/A5/A9/A11/A12
│   │   ├── geopolitical.py # A4/A7/A8
│   │   └── social.py       # A6/A10
│   ├── simulation.py       # 主调度，含action_history队列
│   ├── calibrator.py       # 校准循环（新建）
│   ├── bifurcation.py      # 路径分叉检测（新建）
│   ├── llm_client.py       # 不变
│   └── sim_log.py          # 不变
├── config/
│   └── agents.yaml         # Agent配置（可热更新，预留接口）
├── run.py                  # 入口，保留--daemon
└── ...
```

---

## 十、与推演系统的同步接口（预留）

agents.yaml 里每个 Agent 对应推演系统里的经济体条目：

```yaml
- id: A8
  name: 中国央行/财政
  knowledge_base_ref: "知识库/财经知识库/02_按经济体/中国/"
  transmission_coefficients:
    to_A7: 0.48   # 中国冲击对新兴市场的传导系数（来自跨国联动矩阵）
    to_A3: 0.28   # 中国冲击对美国对冲基金的传导
```

后续增加角色时，只需在 agents.yaml 加一条，代码不变。

---

## 确认结果

✅ 每步 = 1个月，100步（前50校准≈4年，后50预测，实际预测24步，以代码为准）  
✅ 误差加权（v2.0.20 已改）：market_sentiment×0.35 + bank_credit_tightening×0.30 + liquidity_premium×0.20 + em_capital_outflow×0.15（内生变量，以代码为准）  
✅ 路径分叉：最多三条，低于10%概率的路径不展开推演  
✅ 校准期自动调参：GLM-Z1-9B（免费快）
