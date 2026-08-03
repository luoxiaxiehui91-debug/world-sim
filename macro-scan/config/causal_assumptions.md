# causal_assumptions.md — GRV 因果假设文档（天权）

**路径：** `macro-scan/config/causal_assumptions.md`  
**维护者：** 天权（玉衡 V2 反馈入口）  
**创建：** 2026-08-02（arch_review 铁律第5条）  
**最后更新：** 2026-08-03（补充理论文献、玉衡约束、双层衰减架构）  
**状态：** 初稿，尚未经天玑校准  

> **维护规则：** 每次 `geo_risk_vector.py` 混合权重或 `grv_weights.yaml` 发生变更时，必须同步更新本文档对应维度的"当前权重"节。天玑启动后，所有权重调整必须在此留下修改记录。

**格式约定：**
- `[已实现]` = 代码中已有对应逻辑
- `[待实现]` = 本文档定义的目标状态，尚未在代码中落地
- `[经验假设]` = 无文献来源，人工拍定，需标注日期和操作者

---

## 0. 文档目的

本文档是 GRV 向量所有权重和参数的"来源账本"。凡是 `geo_risk_vector.py` 和 `grv_weights.yaml` 中出现的数值，必须在此找到理论来源或明确标注为待校准的经验假设。异常权重出现时，本文档是 RCA 的起点。

**权重层级说明：**
- **混合权重**（`geo_risk_vector.py` 中硬编码）：各数据源在维度内的信号合成比例
- **事件敏感度**（`grv_weights.yaml` 中）：情景事件对各 fetcher 的敏感度，用于天璇仿真时的事件打分

---

## 1. GRV 向量结构总览

| 层级 | 维度 | 驱动信号 | 状态 |
|------|------|---------|------|
| **地缘层（快变量）** | taiwan_strait | GDELT + GPRC_TWN | [已实现] |
| | us_china_strategic | GDELT + GPRC_CHN | [已实现] |
| | russia_europe | GDELT + GPRC_RUS + conflict floor | [已实现] |
| | middle_east_energy | GDELT（无 GPR 补强）| [已实现，有缺陷，见第4节] |
| | global_composite | GPR + japan_monetary | [已实现] |
| **专项层（半透传）** | climate_risk | climate_signals.json | [已实现，天璇不读] |
| | disaster_risk | disaster_signals.json | [已实现，天璇不读] |
| | sanctions_risk | sanctions_risk.json | [已实现，天璇不读] |
| | seismic_risk | earthquake_risk.json | [已实现，天璇不读] |
| | energy_grid_risk | UK Carbon Intensity API | [已实现，数据源错误，见第10节] |
| | japan_monetary | DEXJPUS + IRLTLT01JPM156N | [已实现] |
| **文化层（慢变量）** | social_stress | gdelt_scores.json 直读 | [已实现，公式未文献化] |
| | cultural_friction | gdelt_scores.json 直读 | [已实现，公式未文献化] |

---

## 2. taiwan_strait（台海紧张指数）

**理论依据：**
Caldara & Iacoviello (2022) GPRC_TWN 台湾专项 GPR 指数：通过 11 家国际主流报纸中"台湾""军事""紧张"等关键词共现频率构建，直接捕捉国际市场对台海军事升级的预期。RAND (2022) 台海冲突研究将台积电+亚太航运集中暴露定性为全球价值链最大单点地缘断裂风险。GDELT 军事+制裁双维度与 GPR 形成互补。

**当前权重：** `GDELT × 0.4 + GPRC_TWN × 0.6` [经验假设，2026-05 拍定]  
**grv_weights.yaml 代表性事件敏感度（GDELT fetcher）：** 台海军事演习 0.25 / 台海封锁 0.20 / 台海直接军事冲突 0.25 / 美军直接介入台海 0.20  
**grv_weights.yaml 代表性事件敏感度（GPR fetcher）：** 台海军事演习 0.35 / 台海封锁 0.35 / 台海直接军事冲突 0.35 / 美军直接介入台海 0.30

**上升触发事件：** 解放军军演/海峡中线突破（GPRC_TWN 高值）、美台军售声明（GDELT CAMEO Code 20-22 区段）、台湾政权更迭期（选举前后 3 个月）  
**下降触发事件：** 两岸对话重启声明、美中元首峰会后冷却期（历史均值回归约 6-8 周）

**禁止调整（玉衡）：**
- 禁止将权重调整为负值
- 禁止在两岸经贸好转时单独推低——贸易往来与军事升级历史上多次脱钩（2022-2023 年贸易逆势期间台海局势持续紧张）

---

## 3. us_china_strategic（中美战略对抗指数）

**理论依据：**
Organski & Kugler (1980) 权力转移理论：当挑战国 GDP 接近主导国约 80% 时体系摩擦显著加剧，贸易、技术、军事领域同步出现摩擦信号。BBVA SGR（2025）ESGR 框架：大国竞争风险溢出通过"地理距离×意识形态距离"加权传导，中美间 WVS Inglehart-Welzel 两轴距离显著，结构性底值高于双边贸易额可解释的范围。

**当前权重：** `GDELT × 0.5 + GPRC_CHN × 0.5` [经验假设]  
**理论建议（待实现）：** 引入 WUI（Ahir, Bloom & Furceri 2022）中国子指数作为第三信号，三信号加权可区分"结构性竞争"和"战术摩擦"。

**上升触发事件：** 关税/制裁升级声明、军事技术出口管制扩大、南海 UNCLOS 争端激化  
**下降触发事件：** 双边贸易协定落地、峰会联合声明（效果持续约 4-8 周，均值回归快）

**禁止调整（玉衡）：**
- 禁止将中国国内经济问题（房地产危机）单独推高——内部经济压力与对外战略摩擦方向可反向
- 禁止仅凭媒体舆论热度推高——需实际事件频率超过历史 P95 才构成真实上行信号

---

## 4. russia_europe（俄欧冲突）

**理论依据：**
BIS Working Paper 1348（2025）"Geopolitical risk in the euro area"：俄乌冲突对欧元区传导路径验证为 Channel B（能源供应中断）为主，而非 Channel A（需求收缩）。Mueller (1973) 战时公众厌战效应导致 GPR 系统性低估，conflict_floor 是媒体疲劳的系统性校正。ACLED Conflict Severity Index Geographic Diffusion 维度表明俄乌冲突地理扩散已稳定（低 Fragmentation），长期风险不会降到"和平"水平。

**当前权重：** `GDELT × 0.4 + GPRC_RUS × 0.6`；持续冲突 floor = 35.0（触发条件：news.db 近 30 天冲突文章 ≥5 篇）[经验假设，2026 拍定]  
**GED 接入（v3.8.10，2026-08-04）：** GDELT 子信号先与 GED 融合：`GDELT_sub = GDELT×0.70 + GED_europe×0.30`，再按原公式与 GPR 混合。多 agent 辩论（地缘政治理论+数据科学+怀疑者）结论：GED 0.30 保守起步，3 个月后校准。P95_anchor=3570（1989-2024 地区月度 P95）。GED >18 个月无数据时权重自动退化为 0。  
**Floor 理论建议（待实现）：** 改为基于 ACLED 地理扩散半径动态校准，而非硬编码 35.0。

**上升触发事件：** 冲突线扩大到新州/地区、北约成员国军事直接介入、核威胁信号（GPRC_RUS 核子类激活）  
**下降触发事件：** 停火协议签署（GPR 均值回归约 8-12 周，下降速度慢于上升）

**禁止调整（玉衡）：**
- **禁止**将 russia_europe 的 conflict floor 降为 0
- 任何 floor 修改需人工审核
- 禁止在 conflict_floor 触发期间人工推低——媒体报道频率下降 ≠ 战争风险消退

---

## 5. middle_east_energy（中东能源地缘压力）

**理论依据：**
Smith & Pinchetti（2024，Bank of England）：中东冲突主要通过 Channel B（能源供应中断→油价→通胀）传导，而非 Channel A（需求收缩）。这意味着 middle_east_energy 必须有实际油价信号作为输入，**纯 GDELT 驱动是方法论错误**。Hamilton (1983)："Oil and the macroeconomy since World War II"：供给中断幅度与宏观冲击幅度不成比例，支持非线性 Channel B 激活设计。

**当前权重：** `GDELT × 1.0`（纯 GDELT，设计决策 CFG-1——防止与 global_composite 相关性虚高）[已知缺陷]  
**GED 接入（v3.8.10，2026-08-04）：** GDELT 子信号先与 GED 融合：`GDELT_sub = GDELT×0.70 + GED_mideast×0.30`，再接入 WTI Channel B。同 russia_europe：GED >18 个月无数据时自动退化。  
**目标权重（待实现）：** `GDELT × 0.35 + WTI_oil_price_signal × 0.40 + 霍尔木兹_Channel_B_激活 × 0.25`

油价信号归一化：WTI 60-120 USD/bbl 映射到 0-100，超过 120 触发 Channel B 激活乘数（参照 BIS 1348 阈值研究）。数据来源：commodity_yahoo（已采集，未接入）。

**上升触发事件：** 霍尔木兹海峡封锁威胁或实际事件、以伊战争升级（GDELT 伊朗/以色列 CAMEO 激活）、胡塞武装攻击红海运输线  
**下降触发事件：** OPEC+ 增产协议、沙特-伊朗外交正常化进展

**禁止调整（玉衡）：**
- **禁止**将 Channel B 乘数降至 1.0 以下（即不得将能源传导关闭）
- 禁止因 GDELT 美化（媒体正面报道沙伊关系）直接推低——需实际石油供给变化佐证

---

## 6. global_composite（全球地缘综合指数）

**理论依据：**
Caldara & Iacoviello (2022)：GPR 全球指数通过 11 家主要报纸关键词构建，已成为 IMF 和美联储研究的标准地缘风险代理变量。BIS (2023) "The rise and fall of carry trades"：日元套息平仓与全球风险资产同步抛售存在统计显著正相关（2022-2023 年多次市场波动均有日元套息成分），支持将 japan_monetary 作为流动性放大成分（权重 15%）而非主驱动。

**当前权重：** `GPR × 0.85 + japan_monetary × 0.15`（japan_monetary 不可用时退回纯 GPR）[经验假设]  
**理论建议（待实现）：** 引入 WUI 全球指数（Ahir et al. 2022）：`GPR × 0.6 + japan_monetary × 0.1 + WUI × 0.3`。WUI 捕捉政策/政治不确定性，与 GPR 互补（r≈0.4-0.6）。

**禁止调整（玉衡）：**
- 禁止将 japan_monetary 权重提升至 0.30 以上——过高权重会导致 BOJ 政策会议与真实地缘风险信号混淆

---

## 7. climate_risk / disaster_risk / seismic_risk

**理论依据：** IPCC AR6 (2022) / UNDRR 仙台框架（2015-2030）/ Hsiang et al. (2013) "Quantifying the Influence of Climate on Human Conflict"

**当前状态：** [已实现，但天璇不读——完整断路]  
**修复优先级：** P3（需先修天璇 D1-D3，接入 MacroWorldState）

**天权约束：**
- 这三个维度是纯事件驱动型信号（对应 GPRA 行为层），不应有结构性 floor
- 禁止 climate_risk 和 disaster_risk 互为触发条件（正反馈爆炸风险）

---

## 8. sanctions_risk（制裁风险指数）

**理论依据：**
Hufbauer, Schott & Elliott (1990) 经济制裁全球数据库（GSC）：制裁有效性与制裁对象国国际贸易依存度正相关，全球制裁覆盖面本身是国际秩序碎片化程度的量化代理。OpenSanctions 方法论：汇总 OFAC、EU Consolidated List、UN Sanctions 等全球 100+ 制裁名单。

**当前权重：** 直接映射，global_sanctions_risk 即为维度值  
**理论建议（待实现）：** 接入 BDI 作为制裁生效的量化验证信号（BDI 越低 = 贸易受阻 = 制裁真实生效），合成公式 `sanctions_json × 0.5 + bdi_risk × 0.5`。

**禁止调整（玉衡）：**
- 禁止将关税措施等同于制裁——关税可谈判撤销，制裁涉及实体清单和金融隔离，逆转难度不同
- 禁止仅凭媒体"制裁威胁"推高——OpenSanctions 反映已实施制裁，不是意图信号

---

## 9. energy_grid_risk

**当前状态：** [已实现，数据源严重错误]

**问题：** `source_dimension_map.yaml` 声明数据源为 `energy_eia`，但代码实际读取 UK Carbon Intensity API（英国电网碳强度）——代表英国电网碳强度，不反映全球能源基础设施风险。

**修复目标（待实现，P0）：** 接入 commodity_yahoo 的天然气期货价格（NG），公式：`energy_grid_risk = normalize_linear(ng_price, low=2.0, high=8.0)`（USD/MMBtu）。

---

## 10. japan_monetary（日元货币压力指数）

**理论依据：**
Ito & Mishkin (2006)：BOJ 超宽松政策创造的套息交易（carry trade）规模超 4 万亿美元，是全球流动性的隐性杠杆。BIS Working Paper (2023)：日元升值时全球套息平仓与风险资产同步抛售存在统计显著正相关。

**当前权重：** `DEXJPUS_水位 × 0.5 + JGB_10Y_3M_变化速度 × 0.5`  
- DEXJPUS：[120, 165] → [0, 100] [经验假设，"历史正常下限"和"2024年历史顶部"]
- JGB 速度阈值：25bp/月 = 25 分，100bp/月 = 100 分 [经验假设]

**理论建议：** 归一化区间应参照 BIS 季度报告中日本银行外汇干预阈值（历史上 145-150 区间多次干预），而非简单线性映射。

**禁止调整（玉衡）：**
- 禁止在 global_composite 中将 japan_monetary 权重调整超过 0.30
- 禁止将日本股市表现（日经指数）作为此维度的替代指标

---

## 11. social_stress（社会压力）

**当前状态：** 从 `gdelt_scores.json` 直读，无明确合成公式 [公式未文献化]

**目标公式（待实现）：**

```
social_stress(c, t) =
    0.35 * FSI_cohesion_normalized(c)        # 结构性底噪
  + 0.40 * GPR_rolling_30d(c, t)             # 媒体驱动短期冲击
  + 0.25 * narrative_contagion_index(c, t)   # 叙事传染效应

narrative_contagion_index =
    GDELT_TONE_abs * log(1 + NUMMENTIONS) / baseline_NUMMENTIONS
```

**理论依据：**
- FSI 社会凝聚力维度（Fund for Peace，年度）：捕捉群体仇恨、精英派系化、人口外逃等结构性指标
- GPR 滚动30日：Caldara & Iacoviello (2022)
- 叙事传染：Shiller (2019) 叙事经济学 SIR 模型
- 响应函数：基于 Goldstone 政治不稳定研究，超过阈值后应使用 sigmoid 而非线性权重

**禁止调整（玉衡）：**
- 禁止将 FSI 项的权重降至 0（结构性底噪不可消除）

---

## 12. cultural_friction（文化摩擦系数）

**当前状态：** 从 `gdelt_scores.json` 直读，作为背景常量使用

**理论定位（重要）：**
文化摩擦不是独立的 GRV 维度，而是其他维度的**传导系数乘数**。参照 BBVA SGR（2025）的 ESGR 外部风险计算：
```
EGRV(B←A) = GRV(A) × (1 / geo_distance(A,B)) × cultural_proximity_decay(A,B)
```

**参数化方案（待实现）：**
```python
cultural_friction(A, B) = (
    euclidean_distance(hofstede_normalized_A, hofstede_normalized_B)  # Hofstede UAI/PDI/IDV 三维
  * wvs_axis_gap(A, B)                                                 # WVS Inglehart-Welzel 两轴距离
)  # 归一化到 [0, 1]
```

数据来源：Hofstede 六维矩阵 (https://geerthofstede.com/research-and-vsm/dimension-data-matrix/)；WVS Wave 7 (https://www.worldvaluessurvey.org/)

**禁止调整（玉衡）：** 不得纳入自动权重反馈——是背景常量，天玑验证不适用

---

## 13. 宗教/文化作为背景常量的参数化方案

**设计原则（来源：RAND ROMANCER，Mignano et al. 2025）：**
文化/宗教约束应抽离为可替换的"认知模型"输入参数，而非硬编码到 Agent 行为逻辑中。

**具体实现（待实现）：**

每个 Actor 的 soul 文件包含 `cultural_prior` 字段：

```yaml
cultural_prior:
  conservatism_index: 0.72       # WVS "宗教重要性" 归一化
  nationalism_intensity: 0.65    # WVS "民族主义情感"
  religious_influence_coeff: 0.45 # WVS "宗教在政治中的作用"
  uncertainty_avoidance: 68      # Hofstede UAI
  power_distance: 80             # Hofstede PDI
  opinion_epsilon: 0.32          # = base_epsilon × (1 - UAI/100) × press_freedom_score
```

`opinion_epsilon` 越小，社会在相同外部冲击下积累 social_stress 越快（Deffuant-Weisbuch BCM，2000；Hegselmann-Krause，2002）。

---

## 14. GRV_T / GRV_A 双层衰减架构（待实现）

**理论依据：** Caldara & Iacoviello (2022) GPR 分类中，GPRT（威胁层）和 GPRA（行为层）具有不同的均值回归速度。

```python
# 威胁层：慢衰减（半衰期 3-6 个月）
GRV_T[dim] *= exp(-Δt / 120)  # τ = 120 天

# 行为层：快衰减（半衰期 2-4 周）
GRV_A[dim] *= exp(-Δt / 21)   # τ = 21 天

# 合并
GRV[dim] = 0.6 * GRV_T[dim] + 0.4 * GRV_A[dim]
# α=0.6 初值来自 Caldara 论文中 GPRT 对 GDP 的更强预测力
```

---

## 15. 维度间因果关系图

```
上游信号（外生输入）：
  GDELT 事件 ──────────────────────► GRV_A 行为层（快变量）
  FRED GPR 系列 ────────────────────► GRV_T 威胁层（慢变量）
  FSI 社会凝聚力 ───────────────────► social_stress（结构底噪）
  Hofstede/WVS 文化参数 ────────────► cultural_friction（背景常量）

地缘快变量（相互影响）：
  us_china_strategic ──────────────► taiwan_strait（台海是中美竞争子集）
  middle_east_energy ──────────────► global_composite（能源冲击传导全球）
  russia_europe ───────────────────► sanctions_risk（俄乌驱动制裁升级）
  taiwan_strait / us_china_strategic ► sanctions_risk（大国竞争驱动制裁）

中游传导（行为层输出）：
  sanctions_risk ──────────────────► energy_grid_risk（制裁影响能源贸易）
  energy_grid_risk ────────────────► middle_east_energy（双向反馈）
  middle_east_energy ──────────────► japan_monetary（能源价格影响日元）

下游结果（天璇消费）：
  social_stress ────────────────────────► Agent 国内政治压力
  global_composite ────────────────────► Agent 全局市场情绪
  cultural_friction ───────────────────► Agent 间传导系数乘数
```

---

## 16. 禁止调整汇总表（玉衡约束）

| 维度/参数 | 禁止操作 | 理由 |
|---------|---------|------|
| russia_europe conflict floor | 不得降为 0 | ACLED 证明冲突持续，归零代表无冲突假设错误 |
| middle_east_energy Channel B 乘数 | 不得降至 1.0 以下 | 能源传导路径有 BIS/BoE 文献实证 |
| social_stress FSI 项权重 | 不得降至 0 | 结构性底噪不可消除 |
| cultural_friction | 不得纳入自动权重反馈 | 是背景常量，天玑验证不适用 |
| global_composite japan_monetary 权重 | 不得超过 0.30 | 货币事件会掩盖地缘信号 |
| 任意维度权重 | 不得调整为负值 | GRV 定义为非负风险分数 |

---

## 17. 待校准参数清单（天玑 V2 输入）

天玑月度 Brier 验证启动后应纳入自动校准：

1. GDELT/GPR 各维度混合权重（当前全部经验拍定）
2. GRV_T / GRV_A 分层后的 α 权重（建议初值 0.6）
3. social_stress 三成分权重（0.35/0.40/0.25 是理论建议初值）
4. narrative SIR 模型的 β 基础传染率（按事件类型分类）
5. russia_europe conflict floor（建议改为基于 ACLED 地理扩散动态计算）

---

## 附录 A：权重层级关系图

```
grv_latest.json（13维 GRV 向量，0–100）
│
├── taiwan_strait      ← GDELT(TWN+CHN)×0.4 + GPRC_TWN×0.6
├── us_china_strategic ← GDELT(USA+CHN)×0.5 + GPRC_CHN×0.5
├── russia_europe      ← GDELT(RUS+DEU+UKR)×0.4 + GPRC_RUS×0.6 [+ floor=35]
├── middle_east_energy ← GDELT(IRN+SAU+ISR)×1.0 [无GPR，CFG-1，待修复]
├── global_composite   ← GPR(全球)×0.85 + japan_monetary×0.15
├── climate_risk       ← climate_signals.json（直接映射）
├── disaster_risk      ← disaster_signals.json（直接映射）
├── sanctions_risk     ← sanctions_risk.json（直接映射，待+BDI）
├── seismic_risk       ← earthquake_risk.json（直接映射）
├── energy_grid_risk   ← energy_risk.json（当前数据源错误，待修复）
├── japan_monetary     ← DEXJPUS×0.5 + IRLTLT01JPM156N(3m变速)×0.5
├── social_stress      ← gdelt_scores.json（公式待文献化）
└── cultural_friction  ← gdelt_scores.json（待接入 Hofstede/WVS）

grv_weights.yaml（情景评分权重矩阵，与上述混合权重独立）
  → 结构：{fetcher名称: {情景事件: 敏感度权重(0–1)}}
  → 写回：天玑V2 → pending_weight_adjustments.json → 天枢月度调度器审核 → 写回
```

---

## 参考文献

- Caldara, D. & Iacoviello, M. (2022). *Measuring Geopolitical Risk*. American Economic Review.
- Caldara, D., Conlisk, S., Iacoviello, M. & Penn, M. (2023). *The Effect of the War in Ukraine on Global Activity and Inflation*. IMF.
- Ahir, H., Bloom, N. & Furceri, D. (2022). *The World Uncertainty Index*. NBER Working Paper.
- Smith, A. & Pinchetti, F. (2024). *Geopolitical Shocks and Financial Stability*. Bank of England, Bank Underground.
- BIS Working Paper 1348 (2025). *Geopolitical Risk in the Euro Area*.
- BBVA Research (2025). *Structural Geopolitical Risk (SGR) Index Methodology*.
- Shiller, R. (2019). *Narrative Economics*. Princeton University Press.
- Hegselmann, R. & Krause, U. (2002). *Opinion Dynamics and Bounded Confidence*. JASSS.
- Deffuant, G. et al. (2000). *Mixing beliefs among interacting agents*. Advances in Complex Systems.
- Mignano, A. et al. (2025). *ROMANCER: A Framework for Role-Playing Agent Simulations*. RAND Corporation.
- Goldstone, J. et al. (2010). *A Global Model for Forecasting Political Instability*. American Journal of Political Science.
- Hofstede, G. et al. (2010). *Cultures and Organizations: Software of the Mind*. McGraw-Hill.
- World Values Survey Wave 7 (2017-2022). https://www.worldvaluessurvey.org/
- Organski, A.F.K. & Kugler, J. (1980). *The War Ledger*. University of Chicago Press.
- Hamilton, J.D. (1983). *Oil and the Macroeconomy since World War II*. Journal of Political Economy.
- IPCC AR6 (2022). *Sixth Assessment Report*. Intergovernmental Panel on Climate Change.
- Hsiang, S. et al. (2013). *Quantifying the Influence of Climate on Human Conflict*. Science.

---

*初版由 Claude Code 根据 arch_review_20260802.md 天权裁定创建（2026-08-02）*  
*v2 更新：补充文献引用、玉衡禁止调整清单、双层衰减架构、social_stress/cultural_friction 参数化方案（2026-08-03）*  
*v3 更新：GED v26.1 接入 russia_europe / middle_east_energy（多 agent 辩论结论，2026-08-04）*  
