# agent_taxonomy.md — 天璇 Agent 分类体系 V2（+ V3 修订草案附录）

**路径：** `macro-sim/docs/agent_taxonomy.md`  
**适用版本：** macro-sim v2.1.0（当前 v2.0.24 的升级目标；08-07 已部分实现：核心层 S1-S5 已激活）  
**最后更新：** 2026-08-07  
**状态：** 设计蓝图，**部分落地**。v2.0.19-22 已落地：soul 文件机制 + SovereignAgent 基类 + Board 关系矩阵 + EnergyGovSovereignAgent（A4 激活、A2/A3/A6 预位）。18 Agent 重构成 A/B/C 三类、Secretary Agent、LangGraph 状态机仍为设计（待实现）。**v3 修订草案见文末附录 §11（分类学第一原则 / 三层结构 / 生命周期）**。

---

## 0. 设计原则

**问题：** 原 v2.0.23 的 12 个 Agent（A1-A12）全是金融角色，缺少军事/外交/宗教/媒体行为者，无法模拟地缘冲突→经济的完整传导路径。（08-07 已部分缓解：S1-S5 主权 Agent 激活，军事/外交/能源行为入仿真）

**现状 vs 目标（gap 对照，2026-08-07 补，QClaw P3-9）：**

| 维度 | 现状（v2.0.24）| 目标（V2 蓝图 / V3 草案）| 差距 |
|------|---------------|------------------------|------|
| 激活 Agent 数 | 12（A1-A12 全金融）| 18 蓝图（A8+B4+C6）→ v3 核心层 8 + 情境层动态 | 缺地缘行为体（6+）|
| 主权国家 Agent | 0（无 A 类落地，仅 A4 energy_gov）| 核心层 8：美/中/欧/俄/沙特-OPEC/印/巴/日韩 | 8 个待激活（5 个 soul 现成）|
| 非国家行为者 | 0 | B 类 4（主权基金/国际机构/宗教网络/武装组织）| 4 个未建 |
| 市场传导链 | 12 金融角色 | C 类 6（含 C5 叙事 SIR）| C5/C6 未建 |
| 动态增减机制 | 无（固定清单）| v3 Registry + 四态生命周期（DORMANT→ACTIVE→SUSPENDED→RETIRED）| 未建 |
| Board 关系矩阵 | 基类已实现 | GRV 派生基线 + 仿真内偏离衰减 | 未接线 |

**设计参照：**
- **WarAgent**（agiresearch/WarAgent，Hua et al. 2023）：Country Agent + Secretary Agent 双层架构，Apache 2.0
- **Peakstone Hormuz Sandbox**：Markdown+YAML soul 文件定义 doctrine，国家内部派系 Agent 辩论后合成决策
- **RAND ROMANCER**（Mignano et al. 2025）：非国家行为者作为独立 Agent 类型，与国家 Agent 同框交互
- **Geopol Modeller**（Danielrosehill）：38 个 Actor + 6 视角分析委员会，LangGraph 状态机实现
- **IQTLabs Snow Globe**：AI/人类混合 wargame，LLM adjudicator 裁定行动后果

**目标：** 18 个 Agent（A 类 8 + B 类 4 + C 类 6），比当前 17 个（12 金融 + 5 主权，08-07）多 1 个，新增角色以地缘/政治为主。

---

## 1. Agent 分类框架

### 1.1 两层结构

借鉴 WarAgent 设计，每个"国家集团 Agent"由两层构成：

```
国家层 Agent（State Agent）
│  └── 对外输出：联盟表态、贸易制裁、军事部署信号
│  └── 信息可见性：Board（全局关系矩阵）+ 本国 GRV 向量
│
└── 派系层 Agent（Faction Agent，内嵌于 State Agent soul 文件）
       └── 驱动国内决策过程：鹰派/鸽派辩论 → 合成统一立场
       └── 信息可见性：本国 Stick（私有内部状态）
```

**实现方式：** 不增加独立 Faction Agent 对象，而是在 soul 文件中定义 `internal_factions` 字段，由 State Agent 的 system prompt 驱动内部辩论逻辑。保持代码复杂度可控。

### 1.2 三大类 Agent

| 类别 | 数量 | 描述 |
|------|------|------|
| **A 类：主权国家/集团 Agent** | 8 个 | 主要地缘政治行为者，有领土、军事力量、外交能力 |
| **B 类：非国家行为者 Agent** | 4 个 | 跨国组织、宗教/意识形态网络、武装非国家组织 |
| **C 类：市场/功能性 Agent** | 6 个 | 金融市场、能源市场、媒体/叙事、技术供应链 |

**总计：18 个 Agent**

---

## 2. A 类：主权国家/集团 Agent（8 个）

每个 A 类 Agent 对应一个 soul 文件（`macro-sim/souls/A{n}.yaml`），字段规范见第 5 节。

| ID | Actor | 主要角色 | GRV 维度关联 |
|----|-------|---------|------------|
| A1 | 美国 | 全球金融霸权 + 军事部署决策 | us_china_strategic, taiwan_strait, global_composite |
| A2 | 中国 | 大宗商品需求 + 制造业 + 台海博弈 | taiwan_strait, us_china_strategic, sanctions_risk |
| A3 | 欧盟（集体） | 能源依赖 + 制裁协调 + 汇率 | russia_europe, sanctions_risk, energy_grid_risk |
| A4 | 俄罗斯 | 能源供给 + 军事行动 + 信息战 | russia_europe, energy_grid_risk |
| A5 | 海湾国家（OPEC+ 核心） | 石油定价 + 中东稳定 | middle_east_energy, global_composite |
| A6 | 以色列/伊朗（中东紧张轴） | 区域冲突触发者 + 核威胁信号 | middle_east_energy, seismic_risk（比喻）|
| A7 | 日本/韩国（东亚同盟） | 台海前沿 + 日元套利 + 半导体 | taiwan_strait, japan_monetary |
| A8 | 全球南方代理（印度/巴西/沙特联合）| 不结盟博弈 + 大宗商品 | global_composite, middle_east_energy |

**决策逻辑（共同）：**
1. 读取 Board（全局联盟/制裁/冲突状态）
2. 读取本国 GRV 子集 + Stick（私有内部状态：国内政治压力、经济缓冲月数）
3. 内部派系辩论（soul 文件中 `internal_factions` 字段驱动）
4. 输出行动方案（格式：CAMEO 事件代码 + 目标 Actor + 强度 1-10）
5. Secretary Agent 验证格式/逻辑一致性

**影响路径：**
A 类 → Board 状态更新 → 其他 A 类重新决策 → C 类市场 Agent 接收信号 → 更新经济状态变量

---

## 3. B 类：非国家行为者 Agent（4 个）

借鉴 RAND ROMANCER：非国家行为者使用与国家 Agent 相同的接口，通过参数差异化属性。

| ID | Actor | 主要角色 | 区别于国家 Agent |
|----|-------|---------|--------------|
| B1 | 全球主权基金（GCC/挪威/中投）| 跨境资本流动 + 外汇储备部署 | 无领土，仅有金融影响力 |
| B2 | 国际机构（IMF/WTO/BIS 联合）| 规则约束 + 危机协调 + 制裁合法性 | 无主动攻击能力；行动空间仅为"声明/建议/制裁授权" |
| B3 | 宗教/意识形态跨国网络（伊斯兰/基督教/民族主义）| 叙事传播 + 社会压力积累 + 政权合法性挑战 | 见 3.1 节，不直接操控经济 |
| B4 | 武装非国家组织（胡塞/哈马斯/瓦格纳类）| 不对称冲突 + 供应链中断 + 地区升级触发 | 无正式外交能力；行动空间含"军事袭击/绑架/封锁"类 CAMEO |

### 3.1 宗教/文化如何作为 B3 参数而非独立驱动因素

**核心设计决策：** 宗教/文化是 Agent 的 Belief Prior 向量，不是独立 Agent 的决策目标。

B3 的 soul 文件示例：

```yaml
actor_id: B3
actor_type: non_state_transnational
name: "伊斯兰世界舆论网络（示例）"

cultural_prior:
  conservatism_index: 0.78
  nationalism_intensity: 0.55
  religious_influence_coeff: 0.82
  opinion_epsilon: 0.28           # 低 epsilon = 叙事难以跨越文化边界

action_space:
  - narrative_amplification       # 放大特定事件的媒体叙事
  - social_mobilization           # 触发 A 类内部 Stick 的国内压力累积
  - diplomatic_framing            # 重新诠释事件（影响 Board 上的事件标签）

constraints:
  - 不能直接修改 Board 的联盟/战争状态
  - 不能独立触发军事行动（只能通过 social_mobilization 间接施压 A 类）
```

**B3 的影响路径：**
```
B3 narrative_amplification
  → 触发 C5（媒体叙事 Agent）的叙事 SIR 传播
  → C5 输出 narrative_contagion_index 上升
  → social_stress 上升（公式见 causal_assumptions.md 第 2.10 节）
  → A 类 Stick 中 domestic_political_pressure 上升
  → A 类决策向鹰派方向偏移（soul 文件 internal_factions 权重变化）
```

---

## 4. C 类：市场/功能性 Agent（6 个）

参照 Peakstone Hormuz 的专项分析 Agent 设计：每个关键传导变量设置独立市场 Agent，接收 A/B 类行动作为输入，输出量化经济状态变量。

| ID | Actor | 主要角色 | 输入信号 | 输出变量 |
|----|-------|---------|---------|---------|
| C1 | 美联储/美国货币当局 | 利率决策 + 美元流动性 | GDP增长/通胀/就业 GRV | 联邦基金利率目标；美元指数方向 |
| C2 | 全球股票/债券市场 | 市场情绪 + 风险溢价 | GRV global_composite + A 类行动 | VIX 代理；信用利差；股债相关性 |
| C3 | 大宗商品/能源市场 | 油价 + 粮食价格 | middle_east_energy + A4/A5/B4 行动 | WTI 价格；Channel B 传导激活状态 |
| C4 | 全球供应链/贸易网络 | 贸易流 + 供应链中断 | sanctions_risk + A 类制裁行动 | 贸易量变化 %; 供应链中断指数 |
| C5 | 媒体/叙事 Agent | 叙事传播 + 舆论压力计算 | GDELT TONE/NUMMENTIONS + B3 行动 | narrative_contagion_index；各国 social_stress 更新值 |
| C6 | 技术/半导体供应链 | 科技脱钩 + 出口管制 | us_china_strategic + A1/A2 行动 | 芯片供应约束指数；技术依赖度矩阵变化 |

### 4.1 C5 媒体/叙事 Agent 设计（重点）

**升级目标：** 当前 social_stress 直读 GDELT 分数，缺少叙事传播动力学。C5 引入 Shiller SIR 模型。

**C5 接收的输入：**
1. GDELT TONE 滚动均值 + 方差（均值反映情绪方向，方差反映叙事分歧程度）
2. A/B 类 Agent 本轮行动（重大事件触发 SIR 传播计算）
3. 各国 `cultural_prior.opinion_epsilon`（决定叙事跨境传播衰减系数）
4. `cultural_prior.religious_influence_coeff`（宗教叙事的基础传染率放大因子）

**C5 输出：**
1. 各国 `narrative_contagion_index(c, t)`
2. 各重大事件的叙事"半衰期"预测（影响 GRV_A 衰减参数设定）
3. 媒体集中度高的国家触发"强制影响者效应"警告（参照 Arxiv 2501.12198，2025 年有界置信模型中媒体操控者研究）

---

## 5. Soul 文件规范（统一格式）

参照 Peakstone Hormuz 的 `presets.json` 和 Snow Globe 的 Markdown soul 文件设计，统一采用 YAML 格式：

```yaml
# macro-sim/souls/A1.yaml 示例

actor_id: A1
actor_type: sovereign_state          # sovereign_state / non_state_transnational / market_functional
name: "美国"
layer: state_agent

# 战略原则（文本，影响 LLM 决策生成）
doctrine: |
  优先维护美元霸权和海上通道安全。
  对盟友安全承诺（北约第五条、台湾关系法）优先于经济成本考量。
  避免与核大国直接军事冲突，优先使用经济制裁和代理施压。

# 红线（触发条件列表）
red_lines:
  - "台湾被武力封锁超过 72 小时"
  - "北约成员国领土遭受直接军事攻击"
  - "美元结算系统被规模性绕过（超过 20% 全球贸易份额）"

# 资源参数（影响行动能力判断）
resources:
  military_capacity: 0.95
  economic_buffer_months: 18
  alliance_score: 0.88

# 文化/宗教背景常量（背景约束，非独立驱动）
cultural_prior:
  conservatism_index: 0.42
  nationalism_intensity: 0.55
  religious_influence_coeff: 0.35
  uncertainty_avoidance: 46          # Hofstede UAI
  power_distance: 40                 # Hofstede PDI
  opinion_epsilon: 0.48

# 内部派系（驱动国内决策过程，不对外可见）
internal_factions:
  hawks:
    weight: 0.45
    trigger: "russia_europe > 70 OR taiwan_strait > 75"
    bias: "倾向军事威慑和制裁升级"
  doves:
    weight: 0.35
    trigger: "global_composite < 40 AND economic_buffer_months > 12"
    bias: "倾向外交谈判和成本控制"
  domestic_lobby:
    weight: 0.20
    bias: "优先国内经济指标，反对高代价军事干预"

# 当前 Sprint 状态（Stick，每轮更新）
internal_state:
  domestic_political_pressure: 0.0
  economic_buffer_months: 18
  active_commitments: []
```

---

## 6. 地缘路径完整传导链

**军事升级 → 制裁 → 供应链 → 金融**

```
第 0 轮：
  B4（武装非国家组织）攻击红海航线
  ↓
第 1 轮：
  A6（以色列/伊朗紧张轴）Stick 军事压力上升
  middle_east_energy GRV 上升（Channel B 激活）
  C3（大宗商品市场）: WTI 价格上涨 8-15%
  ↓
第 2 轮：
  A5（OPEC+）内部派系：鹰派触发"减产防御性操作"
  C4（供应链）：霍尔木兹运输量下降信号
  C5（媒体叙事）：GDELT TONE 转负，narrative_contagion_index 上升
  ↓
第 3 轮：
  A1（美国）鹰派权重上升（domestic_political_pressure + 能源价格冲击）
  A1 输出：对 B4 关联国家制裁声明 → Board 制裁关系矩阵更新
  sanctions_risk 维度上升
  ↓
第 4-6 轮：
  C4（供应链）：全球贸易量下降 %
  C2（金融市场）：VIX 上升，信用利差扩大（Channel A 激活）
  C1（美联储）：应对通胀压力（Channel B）vs 增长下行（Channel A）的政策冲突
  A3（欧盟）：能源依赖暴露，制裁参与意愿下降
  ↓
第 8-12 轮：
  social_stress 在中东和欧洲累积（C5 叙事传播 + FSI 凝聚力下降）
  A6 内部鹰派权重超过 0.7 → red_line 触发风险升高
  global_composite 上升 → 仿真输出高风险警告
```

---

## 7. 与现有 A1-A12 的映射关系

| 旧 ID | 旧角色描述 | 新映射 | 操作 |
|-------|---------|-------|-----|
| A1 | 美联储 | C1（货币当局 Agent）| 保留，重分类为 C 类 |
| A2 | 欧央行 | 并入 A3 soul 文件的货币政策派系 | 降级为 A3 内部派系 |
| A3 | 美国国债市场 | C2（金融市场 Agent）子信号 | 合并 |
| A4 | OPEC+ | A5（海湾国家/OPEC+）| 升级为完整 A 类国家 Agent |
| A5 | 人民币/中国央行 | 并入 A2 soul 文件 | 降级为 A2 内部派系 |
| A6 | 日元套利 | 并入 A7（日本/韩国）+ 保留 japan_monetary GRV 维度 | 升级 |
| A7 | 加密货币/稳定币 | C2（金融市场）子信号，降低权重 | 合并降权 |
| A8 | 黄金/大宗商品 | C3（大宗商品市场 Agent）| 合并升级 |
| A9 | 科技股/纳指 | C2（金融市场）子信号 | 合并 |
| A10 | 能源转型/ESG 资本 | C3 + climate_risk 维度接入后扩展 | 暂挂起 |
| A11 | 新兴市场资本流动 | A8（全球南方代理）+ C2 | 拆分重组 |
| A12 | 信用市场/CDS | C2（金融市场）子信号 | 合并 |

**合并逻辑：** 多个旧金融 Agent 合并进 C2（金融市场 Agent），C2 内部维护子信号矩阵，对外输出统一的"市场风险溢价向量"。这减少了重复的金融 Agent 数量，为地缘类 Agent 让出位置。

---

## 8. Secretary Agent 验证层（待实现）

参照 WarAgent 的 Secretary Agent 设计：

```python
class SecretaryAgent:
    """
    验证 State Agent / Non-State Agent 输出的行动合法性
    防止 LLM 输出破坏仿真循环的非法格式
    """
    def validate(self, action: AgentAction) -> bool:
        checks = [
            self.check_cameo_code_valid(action),
            self.check_target_actor_exists(action),
            self.check_intensity_range(action),
            self.check_red_line_not_bypassed(action),
            self.check_resource_sufficient(action),
        ]
        return all(checks)
```

---

## 9. LangGraph 状态机（推荐工程实现）

参照 Geopol Modeller 的 LangGraph 实现（支持 checkpointing/暂停/回放）：

```
节点流程：
Round_Start
  → Board_Broadcast（向所有 Agent 广播当前 Board 状态）
  → State_Deliberation（A 类 + B 类 Agent 并行决策）
  → Secretary_Validation（验证每个 Agent 输出）
  → Market_Update（C 类 Agent 接收行动信号，更新经济变量）
  → Social_Stress_Update（C5 计算新一轮 social_stress）
  → World_State_Commit（更新 Board + 各 Actor Stick）
  → Narrative_Propagation（SIR 传播推进一步）
  → Round_End（写入 predictions 表，触发天玑检查点）

条件边：
  Secretary_Validation → 若验证失败 → 重新调用该 Agent（最多 3 次）
  World_State_Commit → 若 red_line 触发概率 > 0.8 → 发出升级警告
  Round_End → 若轮次 >= 12 → 终止仿真
```

---

## 10. 与 agents.yaml 的兼容性

**当前 agents.yaml 中三参数接口（sensitivity/threshold/magnitude）保持不变。**

新增字段通过可选键追加，不破坏现有 Agent 加载逻辑：
- `soul_file: "souls/A1.yaml"` — 指向 soul 文件路径（可选，无则用默认行为）
- `faction_weights` — 内部派系初始权重（可选，soul 文件中定义）

B+A/NOVEL 重写与现有 agents.yaml 完全向后兼容，可渐进迁移。

---

## 参考框架

- WarAgent: https://github.com/agiresearch/WarAgent （Hua et al. 2023）
- IQTLabs Snow Globe: https://github.com/IQTLabs/snowglobe
- Peakstone-Labs Hormuz Sandbox: https://github.com/Peakstone-Labs/hormuz-agent-sandbox
- Geopol Modeller: https://github.com/danielrosehill/geopol-modeller
- RAND ROMANCER: Mignano et al. (2025)
- Project Sid: Altera AI (2024) — 1000+ agents persistent simulation

---

# 附：v3 修订草案（2026-08-07，设计讨论定稿，待用户最终确认）

> 触发：用户对 V2 蓝图的两处聚合体（A6 以色列/伊朗、A8 全球南方代理）提出质疑——"没有统一对外渠道的聚合体 = 人造意志"；并提出局部冲突/经济特例的动态纳入问题。
> 状态：**修订方向已定，未实施**。V2 仍为现行蓝图；本附录为 v3 演进方向。

## 11.1 分类学第一原则（V3 核心）

> **Agent = 有统一对外决策渠道的行为单元。没有统一渠道的聚合体 = 人造意志，一律不建。**

按此原则 V2 需修正：
- ❌ A6「以色列/伊朗（中东紧张轴）」→ **拆分**：以色列、伊朗各自独立（敌对双方无统一渠道）
- ❌ A8「全球南方代理（印度/巴西/沙特联合）」→ **拆分**：印度、巴西各自独立（沙特并入中东/OPEC 维度）
- ✅ A3 欧盟（委员会/理事会渠道）、A5 海湾-OPEC（产量决策渠道）保留——有真实统一渠道

## 11.2 三层结构（替代固定 18 个）

| 层 | 机制 | 行为体 |
|----|------|--------|
| **核心层**（常驻）| 有**持续**全球传导，soul 精雕 | 美国 / 中国 / 欧盟 / 俄罗斯 / 沙特-OPEC / 印度 / 巴西 / 日韩 |
| **情境层**（事件驱动）| 脉冲式冲突，冲突强度超阈值才激活；模板 soul 快速实例化 | **以色列 / 伊朗** / 乌克兰 / 土耳其 / 阿塞拜疆 / 非洲政变带 |
| **经济参数层**（不建 Agent）| 纯经济 shock 用 C 类（C2/C4）参数冲击表达 | 阿根廷（米莱休克）/ 土耳其里拉危机类 |

## 11.3 生命周期管理（Registry + 监控器 + 四态状态机）

**目的**：全量候选（195 国 + 非国家）不可能全部建模，也不能固定清单漏掉突发重要行为体——靠监控器自动决定。

- **Agent Registry**（`agents_registry.yaml`）：全量候选池，每行 = 模板 + 状态 + 触发规则；休眠模板不参与仿真
- **五态**（v3.1，QClaw P3-8 补 warm_up）：`DORMANT`（休眠池）→ `WARM_UP`（激活预热，**仅低级行动**：外交接触/经济合作，禁军事/制裁类——防新激活 Agent 一步跳入危机）→ `ACTIVE`（参与仿真）→ `SUSPENDED`（暂停，保留状态）→ `RETIRED`（退役归档）；ACTIVE 内可 UPDATE（soul 参数随现实调整）
- **触发判据**（天枢现成数据，自动评估 + 人工确认）：
  - 添加：GDELT 冲突强度超阈值 / GRV 维度连续波动 / 市场异动 → 先入 WARM_UP（N 步后转 ACTIVE）
  - 更新：政权更迭 / 政策转向 / 战争爆发（soul 重写）
  - 停止：冲突结束 / 影响回落持续 N 月
- **容量上限**：同时激活 A 类 ≤ 12-15；超限按"传导影响评分"排序，最低者自动休眠（标普成分股式动态名额竞争）
- **工程**：`agent_watchdog.py`（天枢 scheduler 每日评估，输出 add/update/suspend 建议）——**自动建议 + 人工确认**

## 11.4 用户例子的归属（V3 判例）

| 行为体 | 层 | 理由 |
|--------|----|------|
| 乌克兰 | 情境（长期激活）| 2022 起持续冲突主体，近核心 |
| 伊朗 / 以色列 | 情境 | 脉冲式冲突，事件驱动 |
| 土耳其 | 情境（高优先级）| 三向摇摆大国，低频激活 |
| 阿塞拜疆 | 情境 | 纳卡脉冲，现休眠 |
| 阿根廷 | 经济参数 | 米莱 shock 用 C2/C4 表达，不建 Agent |
| 澳大利亚/菲律宾/越南/加拿大等 | 休眠池 | registry 一行，等触发信号 |

## 11.5 与 V2 的关系

- V2（18 Agent 蓝图）= 核心层的精细化设计 + 传导链骨架，仍有效
- V3 = 分类粒度原则 + 生命周期机制，解决"聚合体捏造"与"动态增减"两个 V2 未覆盖的问题
- 实施路径：V3 原则先行（Registry + 分层），V2 的 C 类/Soul 规范继续沿用

### v3 修订变更记录

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-08-07 | 追加 §11.1-11.5（分类学第一原则 / 三层结构 / 生命周期 / 判例 / 与 V2 关系）| 用户洞察（统一渠道 / 动态增减）|
| 2026-08-07 | §0 补 gap 对照表；§11.3 四态 → 五态（+ WARM_UP 预热态）| QClaw 评审 P3-8/P3-9 |
