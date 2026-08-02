# causal_assumptions.md — GRV 权重理论来源文档

> 创建日期：2026-08-02  
> 依据：arch_review_20260802.md 天权裁定（第5条铁律）  
> 归属：天枢运维文档，与天权独立立项无关  
> 维护规则：每次 grv_weights.yaml 或 geo_risk_vector.py 混合权重发生变更时，必须同步更新本文档对应维度的"当前权重"节

**文档目的**：grv_weights.yaml 的权重矩阵和 geo_risk_vector.py 的混合比例均为人工初始拍定的假设，从未经过系统性校准。本文档记录每个维度权重的理论依据、数据来源、预期因果方向，以及在天玑 V2 权重写回时不得逾越的逻辑边界。异常权重出现时，本文档是 RCA 的起点。

**权重层级说明**：  
- **混合权重**（geo_risk_vector.py 中硬编码）：各数据源在维度内的信号合成比例  
- **事件敏感度**（grv_weights.yaml 中）：情景事件对各 fetcher 的敏感度，用于天璇仿真时的事件打分

---

## 1. taiwan_strait（台海紧张指数）

### 理论来源
Caldara & Iacoviello (2022) "Measuring Geopolitical Risk"（NBER WP 26483）提供了 GPRC_TWN 台湾专项 GPR 指数的方法论基础：通过 11 家国际主流报纸中"台湾""军事""紧张"等关键词的共现频率构建，直接捕捉国际市场对台海军事升级的预期。RAND (2022) 台海冲突研究将台积电+亚太航运的集中暴露定性为当前全球价值链最大单点地缘断裂风险。GDELT 的军事/制裁双维度捕捉实际行动报告与政治压力升级信号，与 GPR 形成互补。

### 数据源
- **GDELT**：TWN（台湾）+ CHN（中国大陆）国别事件分数，军事+制裁均值，p95 归一化（_GDELT_P95["taiwan_strait"] = 0.65）
- **FRED GPRC_TWN**：Caldara & Iacoviello 台湾专项 GPR，滚动10年 P10-P95 归一化

### 当前权重
- **混合比例**：`GDELT × 0.4 + GPRC_TWN × 0.6`
- **grv_weights.yaml 中代表性事件敏感度（GDELT fetcher）**：
  - 台海军事演习：0.25
  - 台海封锁：0.20
  - 台海直接军事冲突：0.25
  - 美军直接介入台海：0.20
  - 台湾内部政治危机：0.20
- **grv_weights.yaml 中代表性事件敏感度（GPR fetcher）**：
  - 台海军事演习：0.35
  - 台海封锁：0.35
  - 台海直接军事冲突：0.35
  - 美军直接介入台海：0.30

### 预期更新方向
**推高**：PLA 军演频率增加、台湾内部政治紧张（选举争议）、美国对台军售升级、GPRC_TWN 连续3个月高于 P75  
**推低**：两岸官方接触恢复、PLA 演习降频、高层外交互访恢复（如海上危机热线建立）

### 禁止方向
- **禁止**在两岸经贸数据好转时单独推低此维度——贸易往来与军事升级历史上多次脱钩（2022–2023 年贸易逆势期间台海局势持续紧张即为反例）
- **禁止**将"台湾内部民主健康度上升"等同于台海整体风险下降——两岸结构性紧张源于大陆政策，非台湾内部变量

---

## 2. us_china_strategic（中美战略对抗指数）

### 理论来源
Organski & Kugler (1980) 权力转移理论：当挑战国 GDP 接近主导国约 80% 时，体系摩擦显著加剧，贸易、技术、军事领域同步出现摩擦信号。Allison (2017) 修昔底德陷阱框架将此结构性紧张系统化。GPRC_CHN 在 Caldara 框架下捕捉贸易战、科技脱钩、金融制裁等非军事冲突的新闻频率，是比汇率或股市更领先的政治风险代理。

### 数据源
- **GDELT**：USA + CHN 组合事件分数，p95 归一化（_GDELT_P95["us_china"] = 9.85）
- **FRED GPRC_CHN**：Caldara & Iacoviello 中国专项 GPR，滚动10年 P10-P95 归一化

### 当前权重
- **混合比例**：`GDELT × 0.5 + GPRC_CHN × 0.5`
- **grv_weights.yaml 中代表性事件敏感度（GDELT fetcher）**：
  - 中美贸易战升级：0.20
  - 半导体出口管制重大升级：0.20
  - 全球贸易体系碎片化：0.15
  - 美国大选政策剧烈转向：0.15
- **grv_weights.yaml 中代表性事件敏感度（OpenSanctions fetcher）**：
  - 半导体出口管制重大升级：0.40
  - 中美贸易战升级：0.25

### 预期更新方向
**推高**：实体清单扩大至关键 AI 芯片、金融制裁升级、南海/台海军事对抗交叉升温、人民币汇率干预引发市场恐慌  
**推低**：正式贸易谈判达成框架协议、关税显著下调、高层外交互访恢复常态

### 禁止方向
- **禁止**将中国国内经济问题（房地产危机、内需疲软）单独推高此维度——内部经济压力与对外战略摩擦方向可反向（内部压力有时导致对外缓和以争取外资）
- **禁止**仅凭媒体舆论热度推高维度——GDELT p95 归一化已剔除舆论噪音，需实际事件频率超过历史 P95 才构成真实上行信号

---

## 3. russia_europe（俄乌/俄欧紧张指数）

### 理论来源
Caldara & Iacoviello (2022) GPRC_RUS 俄罗斯专项 GPR 直接采集俄罗斯军事威胁相关新闻频率。Mueller (1973) 战时公众厌战效应在媒体报道上的体现（随战争持续，新闻报道量下降但实际冲突强度未变），导致 GPR 出现系统性低估，因此引入 conflict_floor 校正机制。Morrow (1989) 代理人冲突的持续性建模提供了 floor 设计的理论依据：持续冲突中媒体疲劳不等于风险消退。

### 数据源
- **GDELT**：RUS + DEU + UKR 组合，p95 归一化（_GDELT_P95["russia_europe"] = 1.42）
- **FRED GPRC_RUS**：Caldara 俄罗斯专项 GPR，滚动10年 P10-P95 归一化
- **news.db（持续冲突 floor）**：近30天俄/乌相关文章数 ≥ 5 时，维度下限不低于 35.0

### 当前权重
- **混合比例**：`GDELT × 0.4 + GPRC_RUS × 0.6`；持续冲突 floor = 35.0
- **grv_weights.yaml 中代表性事件敏感度（Defense_RSS fetcher）**：
  - 乌克兰战场重大转折：0.35
  - 俄罗斯核威慑升级：0.35
  - 北约直接介入乌克兰：0.25
  - 俄罗斯政权更迭：0.20
- **grv_weights.yaml 中代表性事件敏感度（GPR fetcher）**：
  - 乌克兰战场重大转折：0.35
  - 俄罗斯核威慑升级：0.35
  - 俄罗斯内部政治动荡：0.25

### 预期更新方向
**推高**：战线发生重大突破（任一方控制区改变显著）、俄罗斯核武器战略调动信号、北约成员国直接参战、天然气/石油供应链再度被武器化  
**推低**：正式停火协议达成且经多方核实、俄欧能源协议重启、占领区实质冻结且烈度连续下降超过90天

### 禁止方向
- **禁止**在 conflict_floor 触发期间人工推低此维度——floor 的存在逻辑是：媒体报道频率下降 ≠ 战争风险消退，是媒体疲劳的系统性校正
- **禁止**仅凭俄罗斯外交姿态（提出和平倡议、宣布局部停火）推低——历史上此类信号多次与地面行动方向相反（2022年3月伊斯坦布尔谈判期间同步发生布查事件）

---

## 4. middle_east_energy（中东能源地缘压力）

### 理论来源
Hamilton (1983) "Oil and the macroeconomy since World War II"：中东地区紧张对石油供给的影响具有非线性传导特征，地缘事件导致的供给中断幅度与宏观冲击幅度不成比例。中东无专项 GPR 系列（GPRC_IRN/GPRC_SAU 官方未发布），设计决策 CFG-1 选择纯 GDELT 驱动，原因是借用 GPR 全球指数会导致与 global_composite 相关性虚高，破坏 GRV 向量的信号独立性。GDELT 军事+制裁双维度同时捕捉能源生产区（IRN/SAU）和运输通道（ISR/也门）压力。

### 数据源
- **纯 GDELT**：IRN（伊朗）+ SAU（沙特）+ ISR（以色列）组合，军事+制裁均值，p95 归一化（_GDELT_P95["mideast"] = 2.50）
- **无 GPR 成分**（设计决策 CFG-1，防止与 global_composite 相关性虚高）

### 当前权重
- **混合比例**：`GDELT × 1.0`（纯 GDELT，无 GPR）
- **grv_weights.yaml 中代表性事件敏感度（EIA fetcher）**：
  - 伊朗制裁升级：0.25
  - 海湾航运通道威胁：0.25
  - 天然气危机：0.35
  - 油价超预期暴涨：0.40
  - 沙特伊朗直接对抗：0.10

### 预期更新方向
**推高**：伊朗制裁扩大至截断霍尔木兹石油运输、沙特-伊朗直接军事对抗、以色列军事行动扩大至伊朗本土、也门胡塞武装攻击升级（红海航运受阻）  
**推低**：JCPOA 协议实质性恢复（伊朗石油重返市场）、沙伊外交正常化持续、区域停火协议有效执行

### 禁止方向
- **禁止**补入 GPR 全球指数作为中东代理信号——CFG-1 的存在理由是防止 middle_east_energy 与 global_composite 虚高相关性，一旦引入 GPR 全球成分，两个维度的独立性即被破坏
- **禁止**因以巴冲突（ISR 信号上行）直接等同于霍尔木兹通道风险——ISR 是地区政治压力信号，能源通道风险来自 IRN/SAU 动态，两者相关但不等价

---

## 5. global_composite（全球地缘综合指数）

### 理论来源
Caldara & Iacoviello (2022) 通过 11 家主要报纸的战争/恐怖主义/地缘紧张关键词构建 GPR 全球指数，具有跨国系统性风险捕捉能力，已成为国际货币基金和联储研究中的标准地缘风险代理变量。BIS (2023) "The global consequences of Japanese yen carry trades" 记录了日元套息平仓与全球风险资产同步抛售的统计显著正相关，支持将 japan_monetary 作为 global_composite 的流动性放大成分（权重 15%）而非主驱动成分。

### 数据源
- **FRED GPR**：Caldara & Iacoviello 全球 GPR 指数，滚动10年 P10-P95 归一化
- **japan_monetary 子指数**（见维度11）：USD/JPY 水位 + JGB 收益率3月变速

### 当前权重
- **混合比例**：`GPR × 0.85 + japan_monetary × 0.15`（japan_monetary 不可用时退回纯 GPR）
- **grv_weights.yaml 中代表性事件敏感度（GPR fetcher）**：
  - 乌克兰战场重大转折：0.35
  - 台海直接军事冲突：0.35
  - 俄罗斯核威慑升级：0.35
  - 以色列巴勒斯坦冲突升级：0.30
  - 台海封锁：0.35

### 预期更新方向
**推高**：多地区危机同时叠加、GPR 全球指数连续3个月高于 P75、日元快速升值（美元/日元单月跌幅 > 5%）、JGB 收益率3月涨幅 > 50bp  
**推低**：多区域冲突烈度同步下降、GPR 全球指数回落至 P25 以下

### 禁止方向
- **禁止**在单一地区冲突缓解时全面推低此维度——全球 GPR 反映多区域综合，单一区域缓解可能被其他区域上行对冲
- **禁止**将 japan_monetary 权重提升至 0.30 以上——日元是系统流动性放大器而非地缘风险主因，过高权重会导致货币事件（如 BOJ 政策会议）与真实地缘风险信号混淆，削弱 GRV 向量的地缘解释力

---

## 6. climate_risk（气候风险指数）

### 理论来源
IPCC AR6 (2022) 气候风险框架将极端气候事件（热浪、洪水、干旱）定义为"复合型风险"，直接冲击农业生产力和能源系统，与地缘政治稳定存在有据可查的因果链接。Hsiang et al. (2013) "Quantifying the Influence of Climate on Human Conflict"（Science）：跨研究元分析显示气温异常与武装冲突频率存在统计显著正相关（β ≈ 0.14/σ）。WEF Global Risks Report 将气候行动失败和极端天气持续列为全球长周期系统性风险首位，支持其作为 GRV 独立维度而非其他维度的附属信号。

### 数据源
- **climate_signals.json**（fetch_climate_signals.py 写入，climate_risk_score 字段，0–100）

### 当前权重
- **混合比例**：直接映射（无混合），climate_risk_score 即为维度值
- **grv_weights.yaml 中代表性事件敏感度（GDACS fetcher）**：
  - 极端气候冲击粮食能源生产：0.40
  - 气候难民潮冲击地区稳定：0.20
  - 粮食出口禁令危机：0.25

### 预期更新方向
**推高**：北半球夏季出现同步极端热浪、主粮产区（巴西/印度/美国中西部）重大干旱或洪涝、厄尔尼诺强度超过历史均值  
**推低**：拉尼娜年开始、主粮产区气候条件持续正常化

### 禁止方向
- **禁止**以"全球平均气温趋势上升"推高此维度——GRV 关注极端事件冲击（方差），非趋势值（均值），趋势类信号应纳入长周期分析
- **禁止**将 climate_risk 和 disaster_risk 互为触发条件——两者可同时为高，但不应双向联动推高（正反馈爆炸风险，且两个信号本身已有重叠）

---

## 7. disaster_risk（灾害风险指数）

### 理论来源
GDACS（Global Disaster Alert and Coordination System）事件分级方法论：橙色/红色警报对应影响人口 > 100 万的重大灾害，评分综合灾害强度与人口暴露。UNDRR 仙台框架（2015–2030）将灾害风险量化为经济损失 + 人口脆弱性的综合函数，是 fetch_disaster_signals.py 采集 GDACS 数据的理论基础。Noy (2009) "The macroeconomic consequences of disasters"：核心经济体的重大灾害对 GDP 的短期冲击幅度与灾害强度呈非线性关系，支持将此维度作为 GRV 的尾部事件捕捉工具。

### 数据源
- **disaster_signals.json**（fetch_disaster_signals.py + GDACS 事件 API，disaster_risk_score 字段，0–100）

### 当前权重
- **混合比例**：直接映射（无混合），disaster_risk_score 即为维度值
- **grv_weights.yaml 中代表性事件敏感度（GDACS fetcher）**：
  - 重大地震海啸冲击核心经济体：0.15
  - 极端气候冲击粮食能源生产：0.40
  - 新型传染病全球爆发：0.08
  - 气候难民潮冲击地区稳定：0.20

### 预期更新方向
**推高**：GDACS 橙色/红色警报数量显著增加、日本/美国西海岸/台湾发生 M7.5+ 地震、主要港口城市洪涝导致贸易中断  
**推低**：GDACS 无活跃红色警报持续 > 30 天、灾害影响人口数量回落至历史基线

### 禁止方向
- **禁止**将全球传染病信号（新型肺炎爆发）归入本维度——传染病不属于 GDACS 事件分类，应通过 global_composite 的 GPR 信号捕捉（COVID-19 的 GPR 上行已充分体现）
- **禁止**在灾区为非核心经济体时大幅推高——GDACS 本身已按 ALERT_SCORE 加权人口暴露，fetch_disaster_signals.py 消费的是已加权后的 disaster_risk_score

---

## 8. sanctions_risk（制裁风险指数）

### 理论来源
Hufbauer, Schott & Elliott (1990) 经济制裁全球数据库（GSC）：制裁有效性与制裁对象国在国际贸易体系中的依存度正相关，全球制裁覆盖面本身是国际秩序碎片化程度的量化代理。OpenSanctions 方法论：汇总 OFAC（美国财政部）、EU Consolidated List、UN Sanctions 等全球 100+ 制裁名单，生成实体级暴露数据，是当前公开可用的最宽覆盖制裁数据库。BIS AML/CFT 风险框架：全球制裁网络密度的上升是国际金融体系去全球化压力的结构性指标，与 GRV 的地缘风险定义高度对齐。

### 数据源
- **sanctions_risk.json**（fetch_sanctions.py + OpenSanctions bulk data，targets.simple.csv，国别暴露聚合，global_sanctions_risk 字段，0–100）

### 当前权重
- **混合比例**：直接映射（无混合），global_sanctions_risk 即为维度值
- **grv_weights.yaml 中代表性事件敏感度（OpenSanctions fetcher）**：
  - 伊朗制裁升级：0.40
  - 半导体出口管制重大升级：0.40
  - 俄罗斯对欧能源武器化：0.30
  - 中美贸易战升级：0.25

### 预期更新方向
**推高**：OFAC 新增系统重要性国家/机构、G7 协调扩大制裁范围、OpenSanctions 目标实体数量单季度增加 > 5%、新的多边制裁协调机制建立  
**推低**：制裁正式解除（如 JCPOA 恢复后伊朗制裁移除）、双边谈判达成协议并落实解除措施

### 禁止方向
- **禁止**将关税/贸易限制措施等同于制裁——关税是经济工具（可谈判撤销），制裁是法律/政治工具（涉及实体清单和金融隔离），两者信号路径和政策逆转难度不同
- **禁止**仅凭媒体"制裁威胁"或政治声明推高——OpenSanctions 数据反映**已实施**制裁，不是意图信号；未落地的威胁应通过 global_composite 的 GPR 路径捕捉

---

## 9. seismic_risk（全球地震压力指数）

### 理论来源
USGS PAGER（Prompt Assessment of Global Earthquakes for Response）系统通过近实时地震目录评估全球地震暴露，是当前同类中唯一覆盖全球、延迟 < 30 分钟的公开数据源。Cavallo & Noy (2011) "Natural Disasters and the Economy"：地震对核心经济体造成的直接资本损失是最具量化确定性的外生冲击之一，尤其是核电站/港口/半导体工厂集中区域。本维度定位于"能源/电网外生冲击的结构性基线"，区别于 disaster_risk 的单事件告警：全球地震活跃度分布变化是 GRV 基线上移的长期信号，而非单次事件触发器。

### 数据源
- **earthquake_risk.json**（fetch_earthquake.py + USGS Earthquake feed，seismic_risk 字段，0–100）

### 当前权重
- **混合比例**：直接映射（无混合），seismic_risk 即为维度值
- **grv_weights.yaml 中代表性事件敏感度（USGS fetcher）**：
  - 重大地震海啸冲击核心经济体：0.40
  - 极端气候冲击粮食能源生产：0.10
  - 能源基础设施攻击：0.05

### 预期更新方向
**推高**：全球 M6.0+ 地震频率高于30年基线 > 1.5×、核心经济体（日本/美国/台湾/土耳其）M7.0+ 连续发生、太平洋火环带活跃度进入统计异常区间  
**推低**：全球地震活跃度低于历史均值持续 > 90 天

### 禁止方向
- **禁止**与 disaster_risk 耦合推高——seismic_risk 是结构性频率基线（全球地震活跃度分布），disaster_risk 是单事件告警（GDACS 红色警报），两者独立，单次重大地震应在 disaster_risk 体现，不应直接拉高 seismic_risk
- **禁止**用单次历史性大地震数值（如 2011 东日本 M9.1）写死权重——此维度反映滚动期的全球频率分布，不是单事件峰值

---

## 10. energy_grid_risk（能源/电网压力指数）

### 理论来源
UK National Grid ESO Carbon Intensity API 官方方法论：碳强度（gCO2/kWh）反映电网对化石燃料的实时依赖程度，化石燃料依赖越高，暴露于能源地缘风险（如天然气断供、油价飙升）的脆弱性越强。MacKay (2008) "Sustainable Energy Without the Hot Air"：化石能源在电网中的占比是能源安全的结构性脆弱指标，而非周期性变量。IEA Energy Security Framework：能源供给集中度和化石能源占比共同构成地缘能源风险的量化基础，支持将电网碳强度作为能源地缘风险的结构性代理。

### 数据源
- **energy_risk.json**（fetch_energy.py + UK Carbon Intensity API，grid_carbon_risk 字段，0–100）

### 当前权重
- **混合比例**：直接映射（无混合），grid_carbon_risk 即为维度值
- **grv_weights.yaml 中代表性事件敏感度（EIA fetcher）**：
  - 天然气危机：0.35
  - 油价超预期暴涨：0.40
  - 俄罗斯对欧能源武器化：0.30
  - 清洁能源转型加速：0.25
  - 能源基础设施攻击：0.20

### 预期更新方向
**推高**：欧洲电网化石燃料占比回升（清洁转型逆转）、天然气价格飙升导致燃气发电增加、核电站关闭冲击基荷供给  
**推低**：可再生能源装机持续提升导致碳强度下降、LNG 终端扩充降低能源集中依赖

### 禁止方向
- **禁止**用国际油价直接替代此维度——油价反映全球供需（需求侧），grid_carbon_risk 反映电网结构性化石依赖（供给侧脆弱性），两者相关但逻辑路径不同（油价下跌时电网化石依赖可能不变）
- **禁止**在 UK Carbon Intensity API 不可用时用其他国家（如德国、法国）电网数据替代——数据源已定，代理源会引入系统性偏差，缺失时应记录 None 并告警，不应填入估算值

---

## 11. japan_monetary（日元货币压力指数）

### 理论来源
Ito & Mishkin (2006) "Two Decades of Japanese Monetary Policy and the Deflation Problem"：BOJ 超宽松政策创造的套息交易（carry trade）规模是全球流动性的隐性杠杆，规模在2020年代初估计超过 4 万亿美元。BIS Working Paper (2023) "The rise and fall of carry trades"：日元升值时全球套息平仓与风险资产同步抛售存在统计显著正相关，2022–2023 年多次市场波动均有日元套息平仓成分。Obstfeld, Shambaugh & Taylor (2005) "The Trilemma in History"：BOJ 退出 YCC 是固定汇率/资本自由+独立货币政策不可兼得的政策极限点，是 japan_monetary 上行的触发条件之一。此维度在 global_composite 中占 15% 权重，作为流动性放大信号而非地缘风险主驱动。

### 数据源
- **FRED DEXJPUS**（USD/JPY 日汇率，日频）：水位信号，公式 `min(max((usdjpy - 120) / (165 - 120) × 100, 0), 100)`
  - 120 = 历史正常下限（BOJ 宽松前均值附近）
  - 165 = 2024 年历史顶部（日元最弱水位）
- **FRED IRLTLT01JPM156N**（日本10Y国债收益率，月频）：3月变速信号，公式 `min(max(chg_3m_bp / 100 × 100, 0), 100)`；100bp/3M 映射到满分

### 当前权重
- **内部混合比例**：`USD/JPY 水位 × 0.5 + JGB 收益率3月变速 × 0.5`
- **在 global_composite 中的权重**：`japan_monetary × 0.15`（global_composite = GPR × 0.85 + japan_monetary × 0.15）
- **grv_weights.yaml 中代表性事件敏感度（FRED fetcher）**：
  - 日本央行YCC退出：0.20
  - 美联储超预期加息：0.40
  - 多央行政策分化：0.25
  - 通缩风险：0.35
- **grv_weights.yaml 中代表性事件敏感度（Yahoo_FX fetcher）**：
  - 日本央行YCC退出：0.35
  - 多央行政策分化：0.35
  - 人民币大幅贬值：0.40

### 预期更新方向
**推高**：美元/日元升破 155（历史 BOJ 干预警戒区间）、JGB 10Y 收益率3月涨幅超 50bp、BOJ 宣布 YCC 范围再次收窄或完全退出  
**推低**：BOJ 加息后美日利差收窄（套息交易成本上升，促使平仓减压）、美联储降息周期开始（美日利差缩小）、美元/日元跌回 130 以下

### 禁止方向
- **禁止**在 global_composite 中将 japan_monetary 权重调整超过 0.30——日元是全球流动性放大器而非地缘风险主驱动，过高权重会导致货币政策会议（BOJ 公告日）与地缘冲突信号混淆，削弱 GRV 向量的地缘解释力
- **禁止**将日本股市表现（日经指数）作为此维度的替代指标——日经反映日本经济/企业预期，不直接反映套息交易压力（日元升值时日经下跌，但 japan_monetary 同时也下降，两者方向一致但逻辑不同）

---

## 附录：权重层级关系图

```
grv_latest.json（11维 GRV 向量，0–100）
│
├── taiwan_strait      ← GDELT(TWN+CHN)×0.4 + GPRC_TWN×0.6
├── us_china_strategic ← GDELT(USA+CHN)×0.5 + GPRC_CHN×0.5
├── russia_europe      ← GDELT(RUS+DEU+UKR)×0.4 + GPRC_RUS×0.6 [+ floor=35]
├── middle_east_energy ← GDELT(IRN+SAU+ISR)×1.0 [无GPR，CFG-1]
├── global_composite   ← GPR(全球)×0.85 + japan_monetary×0.15
├── climate_risk       ← climate_signals.json（直接映射）
├── disaster_risk      ← disaster_signals.json（直接映射）
├── sanctions_risk     ← sanctions_risk.json（直接映射）
├── seismic_risk       ← earthquake_risk.json（直接映射）
├── energy_grid_risk   ← energy_risk.json（直接映射）
└── japan_monetary     ← DEXJPUS×0.5 + IRLTLT01JPM156N(3m变速)×0.5
                          （同时作为 global_composite 子成分）

grv_weights.yaml（情景评分权重矩阵，与上述混合权重独立）
  → 结构：{fetcher名称: {情景事件: 敏感度权重(0–1)}}
  → 用途：天璇仿真时计算情景事件对各数据源的冲击分数
  → 写回：由天玑V2校准后，经 pending_weight_adjustments.json → 天枢月度调度器审核 → 写回
```

---

*文档由 Claude Code 根据 arch_review_20260802.md 天权裁定创建（2026-08-02）*  
*下次必须更新时机：geo_risk_vector.py 混合权重变更 / grv_weights.yaml 版本升级 / 新增 GRV 维度*
