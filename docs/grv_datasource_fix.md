# grv_datasource_fix.md — GRV 数据源修复方案

**路径：** `docs/grv_datasource_fix.md`  
**关联文件：** `macro-scan/config/source_dimension_map.yaml`、`macro-scan/核心代码/geo_risk_vector.py`  
**最后更新：** 2026-08-06  
**状态：** **P0 全落地 ✅（08-06 复核）**；剩余 P1（仅 BDI→sanctions_risk）+ P2/P3 未排期

---

## 0. 问题全景

当前 GRV 系统存在三类数据源问题：

| 类别 | 问题描述 | 数量 |
|------|---------|------|
| **死映射** | yaml 中声明了但对 GRV 计算贡献为零 | ~21 个 yaml 条目 |
| **死重量** | scheduler 采集了但既不在 yaml 也不在计算路径中 | 4 个数据源 |
| **数据源错误** | yaml 声明的数据源与代码实际读取的不一致 | 1 个（energy_eia） |

---

## 1. 死映射清单

### 1.1 RSShub 新闻源（~11 个）

yaml 中声明这些新闻源贡献 GRV，但 `geo_risk_vector.py` 只读取 `gdelt_scores.json`（独立 GDELT API 输出），完全不读取 `news.db`（RSShub 内容存储）。两套数据管道在架构上解耦，但 yaml 中错误地将 RSShub 源声明为 GRV 输入。

**修复方向（P1-P2）：**
- 方案 A（推荐）：将 RSShub 新闻标题送入 GDELT 同类分类器，输出归一化分数并入 `gdelt_scores.json`。约 1 天工程。
- 方案 B（最快）：更新 yaml，将这些条目的 `contribution` 字段改为 `news_db_only`，明确标注不参与 GRV 计算，仅用于 russia_europe conflict floor 检测。

### 1.2 Marketaux / Currents 新闻 API（2 个）

新闻文章内容不影响 GPR 指数（GPR 基于独立 FRED 序列）。

**修复方向（P2）：** 可作为独立新闻情绪信号接入 C5（媒体叙事 Agent），通过 GDELT TONE 兼容格式输入 `narrative_contagion_index`。

### 1.3 Crucix 私有信号（4 个，gscpi/nuke/air/sdr）

无接入路径，OSINT 信号格式未知。

**修复方向（P3）：** 确认信号格式和更新频率后，设计标准化接入接口。

### 1.4 AkShare 数据（2 个）

无接入路径。AkShare 可提供 A 股数据和中国经济指标，适合作为 `us_china_strategic` 的补充信号（A 股波动作为国内政治经济压力代理指标）。

**修复方向（P2）**

---

## 2. 死重量数据源（采集了但完全未使用）

### 2.1 BDI — 波罗的海干散货指数

**采集状态：** scheduler.py 有对应 fetcher，数据已写入  
**GRV 贡献：** 零  

**修复价值：** 高。BDI 是全球大宗商品贸易量的实时代理指标，与 `sanctions_risk` 高度相关。BDI 急跌 = 贸易受阻信号，优于 GDELT 事件计数。

**接入方案：**
```python
# 接入 sanctions_risk 作为第二信号
# BDI 越低，制裁/贸易中断风险越高
bdi_risk = 100 - normalize_linear(bdi_value, low=300, high=3500)

# 新合成公式：
# sanctions_risk = GDELT×0.5 + bdi_risk×0.5
# 理论依据：贸易量下降是制裁实际生效的量化验证（比新闻计数更直接）
```

**优先级：** P1（1天，数据已采集，仅需改 `geo_risk_vector.py`）

---

### 2.2 commodity_yahoo — 雅虎大宗商品价格

**采集状态：** scheduler.py 有对应 fetcher，数据已采  
**GRV 贡献：** 零  
**arch_review 原文：** "实际油价已采好但没用进去"（D14 盲区 2）

**修复价值：** 极高，P0 级别。这是当前系统最严重的浪费：
- WTI 油价是 `middle_east_energy` 最关键的实体信号（Smith & Pinchetti 2024 Channel B 路径）
- 当前维度纯靠 GDELT 文章计数替代油价，是方法论错误

**接入方案（补强 middle_east_energy 维度）：**
```python
# geo_risk_vector.py 中增加
wti_price = load_commodity_yahoo("WTI")  # 已有数据文件
wti_signal = normalize_linear(wti_price, low=60, high=120, clip=True)

# 霍尔木兹 Channel B 激活逻辑（参照 Smith & Pinchetti 2024）
channel_b_active = (wti_price > 95) or (middle_east_event_shock > 0.6)

# 新合成公式
middle_east_energy = (
    gdelt_signal * 0.35
  + wti_signal * 0.40
  + (channel_b_multiplier * 0.25 if channel_b_active else 0)
)
```

**优先级：** P0（半天，数据已采好，改 `geo_risk_vector.py`）

---

### 2.3 fetch_fx — 汇率数据（ecb_rate / usd_cny）

**采集状态：** 已采集  
**GRV 贡献：** 零  
**arch_review D14：** ecb_rate 和 usd_cny 在 `world_state.py` 中仍是硬编码假值 7.1/3.0

**修复价值：** P0 级别（半天）。A（欧央行/中国央行相关 Agent）当前基于假汇率做决策，等于盲目操作。

**修复方案：**
```python
# world_state.py 初始化部分
# 修复后（改 2 行）：
from 核心代码.fetch_fx import load_latest_fx  # 容器内路径视实际调整
fx_data = load_latest_fx()
ecb_rate = fx_data.get("ECB_DFR", 3.0)   # fallback 保留
usd_cny  = fx_data.get("USD_CNY", 7.1)    # fallback 保留
```

**不需要改 `geo_risk_vector.py`，只改 `world_state.py` 初始化。**  
**优先级：** P0

---

### 2.4 FAO — 食品价格指数

**采集状态：** scheduler.py 有对应 fetcher  
**GRV 贡献：** 零  

**修复价值：** 中等。FAO 食品价格与 `disaster_risk` 相关（极端天气→粮食价格→政治不稳定传导链），作为该维度的结构性背景信号（月度更新，慢变量）。  
**优先级：** P2

---

### 2.5 OpenSky — ADS-B 航班追踪

**采集状态：** scheduler.py 有对应 fetcher  
**GRV 贡献：** 零  

**修复价值：** 中等。航班取消/重新路由是地缘冲突的实时代理指标（红海危机期间苏伊士绕行是典型案例）。信号提取需要地理过滤逻辑（区分商业航班和军用航班）。  
**优先级：** P3

---

## 3. 数据源错误：energy_eia / energy_grid_risk

**问题描述：**
`source_dimension_map.yaml` 声明：`energy_eia → energy_grid_risk`  
代码实际读取：**UK Carbon Intensity API**（英国电网碳强度）

**UK Carbon Intensity API 的问题：**
1. 地理范围：仅代表英国电网，不反映全球能源基础设施风险
2. 信号含义：碳强度（gCO2/kWh）与能源供给安全几乎无关

**修复方案（推荐选项 B，工程成本最低，P0）：**

选项 B — 接入 commodity_yahoo 的天然气期货价格（NG），复用已有数据：
```python
ng_price = load_commodity_yahoo("NG")  # 亨利枢纽天然气，USD/MMBtu
energy_grid_risk = normalize_linear(ng_price, low=2.0, high=8.0)
```

选项 A — 接入 EIA 原油/天然气库存数据（与 yaml 声明对齐）：
```python
# API: https://api.eia.gov/v2/petroleum/stoc/wstk/data/
# 库存低 = 供给紧张 = energy_grid_risk 上升
energy_grid_risk = 100 - normalize_eia_inventory(current_inventory, 5year_avg=500)
```

---

## 4. GDELT P95 基准校准

**✅ 已解决（v3.8.11，运行时动态化取代静态基准）：**
> `_GDELT_P95` 已改为运行时动态计算（样本<100 fallback 硬编码），修复 D9 归一化失真（中美/台海 15 倍差距），无需再手动扩大静态基准窗口。

**原问题（历史记录）：**
`_GDELT_P95` 字典基于 211 条/7 周实测数据（2026-05-21 至 2026-07-08）。arch_review D9 指出：中美 vs 台海维度归一化后强度差距达 15 倍，说明基准严重失真。

**当时校准方案（P1，1天，已被 v3.8.11 动态化取代）：**
```python
# 步骤 1：读取 gdelt_history.jsonl 全部历史数据
import json, numpy as np
records = [json.loads(l) for l in open("data/gdelt_history.jsonl")]
# 检查：len(records) 应远超 211

# 步骤 2：按维度计算 P95
for dim in ["taiwan_strait", "us_china_strategic", "russia_europe", "middle_east_energy"]:
    values = [r[dim] for r in records if dim in r]
    p95 = np.percentile(values, 95)
    p10 = np.percentile(values, 10)
    print(f"{dim}: P10={p10:.1f}, P95={p95:.1f}, ratio={p95/p10:.1f}x")

# 步骤 3：更新 geo_risk_vector.py 的 _GDELT_P95 字典
# 同时改为"滚动 12 个月"动态更新，防止新事件将天花板压低
```

**理论依据：** 样本量不足 200 的情况下 P95 估计误差极大，应使用至少 1000 条数据后再锁定。

---

## 5. 各维度升级路线图

| 维度 | 当前逻辑（08-06） | 理论升级目标 | 优先级 |
|------|---------|------------|-------|
| taiwan_strait | GDELT×0.4 + GPR×0.6 | 同上 + 待天玑校准权重 | P1（校准）|
| us_china_strategic | GDELT×0.5 + GPR×0.5 | 引入 WUI 中国子指数作第三信号 | P2 |
| russia_europe | GDELT×0.4 + GPR×0.6 + floor 35 | floor 改为 ACLED 地理扩散动态计算 | P2 |
| middle_east_energy | ✅ GDELT×0.45 + WTI×0.40 + Channel B 激活 | 已接入 WTI（v3.8.10，GED v26.1 多 agent 权重）| **P0 ✅** |
| global_composite | GPR×0.85 + japan_monetary×0.15 | 引入 WUI 全球指数 | P2 |
| climate_risk | climate_signals.json 直读 | 保持，待 D7 修复后接入天璇 | P3 |
| disaster_risk | disaster_signals.json 直读 | + FAO 食品价格月度补充 | P2 |
| sanctions_risk | sanctions_risk.json 直读 | + BDI 作为制裁生效量化验证 | **P1（唯一待做）** |
| seismic_risk | earthquake_risk.json 直读 | 保持，待 D7 修复后接入天璇 | P3 |
| energy_grid_risk | ✅ 天然气期货（NG）| 已替换 UK Carbon Intensity（v3.8.10）| **P0 ✅** |
| japan_monetary | DEXJPUS×0.5 + JGB速度×0.5 | 归一化区间参照 BIS 日本银行干预历史阈值 | P2 |
| social_stress | gdelt_scores.json 直读 | FSI×0.35 + GPR_30d×0.40 + SIR指数×0.25 | P1 |
| cultural_friction | gdelt_scores.json 直读 | Hofstede UAI/PDI/IDV + WVS 两轴距离 | P2 |

---

## 6. 优先级执行清单

### P0（✅ 全落地，08-06 复核）

1. ✅ **接入 fetch_fx → world_state.py**（已修复）
   - 文件：`macro-sim/core/world_state.py`
   - 改动：2 行，读取 fetch_fx 输出替换硬编码 ecb_rate/usd_cny（D14，v2.0.18）
   - 价值：A 类欧元/人民币相关 Agent 从盲操变真实数据驱动

2. ✅ **接入 commodity_yahoo → middle_east_energy**（已落地）
   - 文件：`macro-scan/核心代码/geo_risk_vector.py`
   - 改动：增加 WTI 信号读取 + 新合成公式（v3.8.10，GED v26.1 接入，GDELT×0.45+WTI×0.40+Channel B）
   - 价值：修复方法论最严重缺陷，同时修复 A5 决策基础

3. ✅ **修复 energy_grid_risk 数据源错误**（已修复）
   - 文件：`macro-scan/核心代码/geo_risk_vector.py`
   - 改动：将 UK Carbon Intensity 替换为 commodity_yahoo 天然气价格（NG，v3.8.10）
   - 价值：消除最明显的数据源错误映射

### P1（约 2-3 天）

4. ✅ **扩大 GDELT P95 基准窗口** → **已被 v3.8.11 运行时动态化取代**（见 §4）
   - 文件：`macro-scan/核心代码/geo_risk_vector.py`（`_GDELT_P95` 字典）
   - 改动：运行时动态计算，修复 D9，消除中美/台海归一化差距 15 倍的扭曲

5. ⏳ **接入 BDI → sanctions_risk**（1天，**唯一剩余 P0/P1 项**）
   - 文件：`macro-scan/核心代码/geo_risk_vector.py`
   - 改动：读取 BDI 数据，计算 bdi_risk，加权 sanctions_risk
   - 状态：数据已采集，仅需改 geo_risk_vector.py

6. ✅ **完成 causal_assumptions.md**（已完成，写入 `macro-scan/config/`）

### P2（约 3-5 天）

7. 更新 source_dimension_map.yaml：将死映射条目标注 `status: dead_mapping`
8. 引入 WUI 作为 us_china_strategic 和 global_composite 第三信号
9. social_stress 接入 FSI 凝聚力维度
10. cultural_friction 接入 Hofstede CSV

### P3（需先修天璇 D1-D3）

11. 将 6 个新维度（climate/disaster/sanctions/seismic/energy_grid/japan_monetary）真正接入天璇 MacroWorldState 并驱动 Agent 行为

---

## 7. 修复后 GRV 向量预期质量提升

| 指标 | 当前状态（08-06） | P0 修复后 | P1 修复后 | P2 修复后 |
|------|---------|---------|---------|---------| 
| 有理论文献依据的维度数 | 2/13（P0 已落地）| 2/13 | 3/13（+BDI）| 10/13 |
| 死重量数据源接入数 | 2/4（fx+commodity，P0 已落地）| 2/4 | 3/4（+BDI）| 4/4（+FAO）|
| 归一化量纲一致性 | 良（P95 已动态化，v3.8.11）| 良 | 良 | 良 |
| 天璇实际消费维度数 | 5（仅地缘快变量）| 5 | 5 | 待 D7 修复 |
| A 类 Agent 数据盲区数 | 0（P0 已消除）| 0 | 0 | 0 |

**最高价值修复已完成：** P0 中的 commodity_yahoo → middle_east_energy 接入，同时消除方法论错误和数据浪费（v3.8.10）。
