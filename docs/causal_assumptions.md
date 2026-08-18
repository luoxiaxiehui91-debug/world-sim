# causal_assumptions.md — 系统因果假设登记（P1-E）

> 文档类别：契约（CONTRACT）· 天权公式（P2 门控）输入
> 目的：显式化天枢/天璇分析链中**藏在代码里的因果假设**——换 LLM 模型、调参、扩展数据源时，先查本表确认"系统为什么这么推演"。
> 维护约定：**任何改动本表涉及的权重/阈值/公式，必须同步更新本表对应条目**（改假设不登记 = 违反契约）。
> 最后更新：2026-08-18（P1-E 补全）

---

## 一、GRV 维度推导假设（`geo_risk_vector.py`）

> 通用算子：`_ws` = 加权和（缺失项剔除后权重归一）；`_rb` = 鲁棒合并；`_norm` = 按固定上限归一。
> **核心假设**：国别 GDELT 分数（military/tension/protest/sanction/cultural）经加权组合 → 区域维度；组合权重视领域经验校准，非统计拟合。

| 维度 | 因果假设链 | 权重/参数 | 关键设计决策 |
|------|-----------|-----------|-------------|
| south_china_sea | CHN 军事+紧张（**不含制裁**，保正交）+ USA/JPN 外部响应 | CHN(m0.65+t0.35)/EXT(USA0.55+JPN0.45)/TWN 直取；合成 0.6×max+0.4×wmean | 制裁归 taiwan 用，避免共线 |
| korean_peninsula | PRK 发射活动+紧张 → 区域风险；JPN 是最可靠响应代理 | PRK(m0.5+t0.5)/JPN(t0.65+m0.35)/USA(t0.55+m0.45)，_rb 权重 0.5/0.3/0.2 | PRK 尖刺分布置信度受限 |
| india_pacific | CHN 外交/文化压力（**非军事**）+ IND 边境 + JPN 东海 + PAK 南亚 | CHN(t0.55+cf0.45)/IND(m0.45+t0.4+s0.15)/JPN(t0.7+s0.3)/PAK(m0.5+t0.35+r0.15)；0.6×max+0.4×wmean | 排除 CHN 军事制裁防共线 |
| taiwan_strait | CHN 军事+制裁（**含制裁**，与南海互补）+ USA 响应 | 同类加权组合 | 制裁主用此维度 |
| us_china_strategic | 中美军事/制裁/紧张双边互动 | 双边组合 | 与印太/南海正交性设计 |
| russia_europe | RUS 军事/紧张/制裁 + 欧洲响应 | 加权组合 + **GED 补强（当前 None）** | GED CSV 未部署，补强恒 None（P2 门控） |
| middle_east_energy | 中东军事/紧张 + 能源国互动 | 加权组合 + **GED 补强（当前 None）** | 同 russia_europe |
| global_composite | 全部维度汇总 | 加权合成 | 综合风险水位 |

**假设强度**：权重为经验校准（08-04 接入时按领域判断设定），**未做统计回测**——天权公式上线前，这些权重是"专家先验"而非"拟合参数"。

**08-18 GRV 分数语义总表（#134 批次，回答"分数高是啥意思"）**：
| 分数 | 语义 | 常态区间 | 备注 |
|------|------|---------|------|
| global_composite | 综合风险水位 | 50-65 | 日频灵敏（#77）；红线/告警依赖 |
| 台海/半岛/南海等推导维度 | 区域风险 | 20-60 | GDELT scale 修复后恢复（8/14 前语义） |
| sanction_risk | **持久制裁基线**（非当日信号） | 75-85 | 设计如此：全球制裁存量 7.2 万实体、RUS 2.2 万 → 基线恒高是现实 |
| energy_grid_risk | 能源价格压力 | 45-70 | [50,110] 映射：油价 80+ 常态 → 55-65 分如实 |
| social_stress / cultural_friction | **新闻情绪**（非风险） | 40-55 / 10-20 | tone 派生，48-54=全球新闻轻微偏负 |
| climate_risk | 气候风险 | 35-60 | #134 修后：ONI 30 + FIRMS 常态 20；50 万火点才 40 |
| seismic_risk | 地震压力 | 8-35 | #134 修后：平静 8-24 / M6+ 40-70 / M7+ 90+ |
| disaster_risk | 灾害活跃度 | 10-36 | 正常 |
| news_geo intensity | **显著度非风险**（UI 上色） | mean 52 | 事件被报道强度，非世界危险度 |

**校准原则（#134 批次）**：常态 20-40、活跃 50-70、极端 90+；绝对阈值必须对照真实常态分布校准（gdelt P95 / FIRMS 2万 / seismic scale 2.0 三个教训）。

**⛔ 08-18 GDELT scale 语义登记（校准器事故）**：`gdelt_calib.json` scales 现 = SCALE_REF 透传（v2），
语义 = "2022-02-24 俄乌开战峰值/0.9"极端事件基准——常态 0-20 分、俄乌级极端 ≈100 分。
v1"P95 反推"（常态当分母）已废弃：8/14-8/18 曾致 gdelt_scores 全线虚高 9-28 倍、
推导维度 scs 25→93/kor 53→89、global_composite 71（虚高），8/18 修复恢复。
**改 scale 语义必须同步重算 gdelt_history/gdelt_scores 口径并重跑 #77 旁路验证。**

**⛔ 08-18 #77 公式变更登记**：`global_composite = (gpr_global×0.85 + japan_monetary×0.15) × 0.7 + gdelt_risk_daily × 0.3`
- gdelt_risk_daily = 6 个 GDELT 风险维度（military/tension/sanction/protest/religious_conflict/regime_change）全球均值 → 各维自历史百分位 → 等权平均（0-100，88 天窗口滚动）
- 依据：88 天旁路验证（日 std 0→6.1，p50 58.0/p90 64.3）；GDELT 数据缺失时自动退化旧公式
- **连带重校准**：`grv_threshold.py` GRV_DELTA_THRESHOLD 6→12（global_composite 日频化后 |Δ|≥6 触发率 27.6% 过频；12 = p95 上沿，降至 5.7%）；台海 abs 68 不受影响（独立维度）
- 若换 GDELT 维度定义/权重 → 须重跑旁路分布对比

## 二、衰退概率（`compute_probit.py`）

| 假设 | 参数 | 依据 |
|------|------|------|
| **T10Y3M 利差 → 未来 12 个月衰退概率**（probit） | α=−0.5333，β=−0.5984 | Estrella-Trubin 经典参数，**冻结禁调**（R4 治理红线） |
| 利差转负 = 衰退信号增强 | z=α+β·spread → norm.cdf(z) | 模型假设 |
| 数据源：FRED T10Y3M（月频） | 滞后容差 90 天 | 探针 fred 滞后检查 |

## 三、金融条件（`compute_fci.py`）

| 假设 | 内容 |
|------|------|
| **FCI 双轨 PCA**：全球轨 + 美国轨 | 多序列主成分压缩 → 条件指数 |
| 与 NFCI 相关性目标 ≥ +0.8 | 验收基准（实测 +0.828） |
| **符号锁定锚**：BAA10Y/BAMLH0A0HYM2 方向 | 信用利差升 = 收紧（方向语义红线） |
| 缺失处理：**禁 fillna(0)**，仅 ffill limit=5 | 防伪信号 |

## 四、慢变量（`slow_variables.py`）

| 变量 | 因果假设 | 说明 |
|------|---------|------|
| IRP（机构风险偏好） | 风险偏好 → 市场波动传导 | 月频慢变量 |
| UCRI（地缘风险指数） | 地缘 → 经济不确定 → 资产价格 | Caldara-Iacoviello 系 |
| GCI（全球冲突指数） | 冲突强度 → 风险溢价 | 补充维度 |

## 五、GED 补强假设（`geo_risk_vector.py` GED 段）

> **当前失效**：`data/ged/` 未部署（etl_ged.py 从未跑），GED 补强恒 None——russia_europe/middle_east_energy 的 GED 权重实际为 0。
> 假设链（设计意图）：GED 武装冲突事件频次 → 区域维度补强。**补数据 = P2 门控（Q4）**。

## 六、LLM 分析框架假设（`system_prompt.md`）

> 系统提示词显式要求"传导路径"（如：房地产下滑→地方财政收入减少→基建投资放缓→GDP 拖累），
> **核心假设：LLM 输出的传导链默认可信**（未做事实核查层）。

| 假设 | 影响 |
|------|------|
| 情景分析基准概率 ≤70% | 防乐观偏差（prompt 约束） |
| 知识库因果链数据 = 分析输入 | `知识库/财经知识库/` 为 LLM 事实源 |
| 模型可替换（开阳 LLM 配置面板） | **换模型须复查本表假设是否仍适用** |

## 七、天璇行为假设（`macro-sim/`）

| 假设 | 位置 | 说明 |
|------|------|------|
| GRV 维度 > 主权红线 → 强制行动 | `souls/*.yaml` red_line_triggers | 阈值按 GRV 实测 p90 校准（08-17） |
| 派系权重 → 决策倾向（bias_actions） | souls factions | 权重经验设定 |
| 政权更迭 transition_prob → 风格切换 | `core/governance.py` | 民主 0.15-0.70 谱系 |
| 央行独立（A12 ≠ S6） | souls/S6_japan + A12 | 货币政策与国家战略分离 |
| 媒体情绪 = VIX 分位代理 | `verify_geo_auto.py` L1 | 自动验证用 VIX 近似（GDELT tone 未接） |

---

## 待补（已知缺假设文档的模块）

- `scan_weak_signals.py` 弱信号 → 预警阈值（各信号触发线经验值）
- `narrative_processor.py` 11 维叙事桶的维度定义映射
- `situation_detector.py` 情景检测的触发规则
- 天枢告警链（ntfy 阈值/去抖参数）

## 变更登记

| 日期 | 变更 | 影响模块 |
|------|------|---------|
| 2026-08-18 | 文档创建（P1-E 补全） | 全系统 |
