# GDELT 地缘政治维度接入指南

> 本文档记录 GDELT（Global Database of Events, Language, and Tone）数据源的技术接入方案、CAMEO 事件码分类、维度评分逻辑，以及如何将地缘政治信号注入 Monte Carlo 模拟参数。

---

## 一、什么是 GDELT

GDELT 是迄今覆盖范围最广的全球新闻事件数据库：

- **覆盖**：100+ 语言、每15分钟更新
- **历史深度**：1979年至今全量数据
- **体量**：每天约 30-50 万条事件记录
- **费用**：完全免费，无需 API key
- **编码标准**：CAMEO（Conflict and Mediation Event Observations）

GDELT 将每一条新闻报道转化为结构化事件：**谁对谁做了什么**，并打上冲突强度分（GoldsteinScale）。

---

## 二、数据格式

### 2.1 文件下载地址

```
单文件（15分钟间隔）：
  http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.export.CSV.zip

例：
  http://data.gdeltproject.org/gdeltv2/20260521153000.export.CSV.zip
```

每个 ZIP 解压后是一个 tab 分隔的 CSV，无表头，61 列。

### 2.2 关键列（0-indexed）

| 列号 | 字段 | 含义 |
|:---:|:---|:---|
| 7  | Actor1CountryCode | 行为方国家（3位 ISO，如 `CHN`） |
| 17 | Actor2CountryCode | 被作用方国家 |
| 26 | EventCode | CAMEO 事件码（如 `190`） |
| 30 | GoldsteinScale | 冲突强度 -10（战争）至 +10（合作） |
| 31 | NumMentions | 事件被提及次数（热度权重） |
| 60 | SOURCEURL | 来源 URL |

### 2.3 CAMEO root code（取 EventCode 前2位）

| Root | 含义 | 本系统分类 |
|:---:|:---|:---|
| 03–06 | 外交合作/磋商/援助 | `coop`（正向） |
| 13 | 威胁 | `tension` |
| 14 | 抗议/示威 | `protest` |
| 15 | 武力展示 | `tension` |
| 16 | 断绝关系 | `tension` |
| 17 | 胁迫（制裁/封锁） | `sanction` |
| 18 | 武装攻击 | `military` |
| 19 | 战斗 | `military` |
| 20 | 大规模暴力 | `military` |

---

## 三、本系统实现

### 3.1 关注国家（`_WATCH_COUNTRIES`）

```python
{"USA", "CHN", "RUS", "IRN", "PRK", "ISR",
 "UKR", "TWN", "SAU", "DEU", "FRA", "JPN"}
```

### 3.2 维度评分逻辑

每条 GDELT 事件行按以下规则累积：

```
military[country]  += NumMentions × (1 + max(0, -GoldsteinScale) / 5)
tension[country]   += NumMentions
protest[country]   += NumMentions
sanction[country]  += NumMentions × (1 + |GoldsteinScale| / 5)
coop[country]      += NumMentions × GoldsteinScale   (仅 goldstein > 0)
```

归一化基准（scale 值）：

| 维度 | 归一化基准 | 含义 |
|:---|:---:|:---|
| military | 15000 | 高强度军事事件基线 |
| tension  | 10000 | 威胁/武力展示基线 |
| protest  | 8000  | 抗议事件基线 |
| sanction | 6000  | 制裁/胁迫基线 |
| coop     | 20000 | 外交合作基线（分越高越好） |

最终每个维度每个国家输出 0-100 分。

### 3.3 预警阈值

| 维度 | [注意] | [警报] |
|:---|:---:|:---:|
| military | ≥ 30 | ≥ 55 |
| sanction | ≥ 20 | — |
| protest  | ≥ 25 | — |
| 多点同步（military ≥ 30 的国家数） | — | ≥ 3 |

### 3.4 MC 参数调制（`get_gdelt_geo_modifier()`）

```
中东军事（伊朗/沙特/以色列）→ oil_shock_bias     最大 +2σ
美中制裁互动              → trade_tension_boost 最大 +15pt
西方社会动荡（美/德/法）   → umcsent_drag        最大 -8pt
亚太军事（台湾/朝鲜）     → tail_risk_boost     最大 +20pt
俄乌战事                  → recession_boost     最大 +10pt
```

调制系数存入 `data/gdelt_scores.json`，`run_macro_analysis.py` 启动时读取。

---

## 四、使用方式

### 4.1 通过弱信号扫描器运行

```bash
python scan_weak_signals.py
```

GDELT 扫描自动包含在 `run_scan()` 中，每次扫描同时更新 `gdelt_scores.json`。

### 4.2 单独扫描 GDELT

```python
from scan_weak_signals import scan_gdelt_dimension, get_gdelt_geo_modifier

alerts, scores = scan_gdelt_dimension(hours=24)
print(scores)  # {'military': {'RUS': 68.2, ...}, ...}

mod = get_gdelt_geo_modifier(scores)
print(mod)  # {'oil_shock_bias': 1.2, 'recession_boost': 6.8, ...}
```

### 4.3 在 run_macro_analysis.py 中读取调制系数

```python
from scan_weak_signals import get_gdelt_geo_modifier

geo_mod = get_gdelt_geo_modifier()  # 从缓存文件读取

# 在 run_monte_carlo() 参数设置阶段：
oil_shock_mean  += geo_mod.get("oil_shock_bias", 0)
trade_tension   += geo_mod.get("trade_tension_boost", 0)
recession_prob  += geo_mod.get("recession_boost", 0) / 100
```

---

## 五、企业网络代理配置

SAP 内网访问 GDELT 公网地址需要通过代理：

```python
_GDELT_PROXY = {
    "http":  os.environ.get("HTTP_PROXY",  "http://proxy.sin.sap.corp:8080"),
    "https": os.environ.get("HTTPS_PROXY", "http://proxy.sin.sap.corp:8080"),
}
```

如在家（VPN 模式）运行，代理地址可能不同，通过环境变量覆盖：

```bash
export HTTP_PROXY=http://proxy.xxx:8080
python scan_weak_signals.py
```

---

## 六、性能与局限

| 项目 | 说明 |
|:---|:---|
| 下载速度 | 约 48 文件 × 3-5秒 = 3-4分钟（企业代理） |
| 数据延迟 | 最新文件约有 15-30 分钟延迟 |
| 语言偏差 | 英语来源占 60%+，中文/阿拉伯语事件可能低估 |
| 事件准确率 | NLP 自动抽取，误码率约 5-10%（高频事件误差可平均化） |
| 规模归一化 | 当前基准值基于直觉校定，需积累历史数据后调整 |

### 当前主要局限

1. **归一化基准未实证校准**：`scale=15000` 等值是估算，需用历史峰值（如 2022 年俄乌开战当天）反算实际分布后调整
2. **无历史对比**：当前只看绝对分值，未来可加「较30日均值的偏差」检测短期激增
3. **MC 调制系数未回测**：`+2σ` 等值需与 FRED 实际数据对比验证

---

## 七、未来改进方向

1. **历史数据回溯**：下载2022-01-01 至今数据，建立各维度的历史分布，替换固定 scale 参数
2. **Z-score 化**：用历史均值/标准差计算 Z-score，替代绝对分值阈值
3. **ACLED 补充**：ACLED（武装冲突地点和事件数据）专注实际暴力事件，精度高于 GDELT，可作交叉验证
4. **EPU 指数接入**：`USEPUINDXD`（FRED 上有）= 经济政策不确定性，补充政策维度
5. **情感维度**：GDELT 的 `AvgTone`（列35）是平均语气，负值 = 负面报道情绪，可加入情感信号层

---

*最后更新：2026-05-21 | 关联代码：scan_weak_signals.py::scan_gdelt_dimension() / get_gdelt_geo_modifier()*
