# 世界推演系统 · 完善方案（IMPROVEMENT_PLAN）

> ⚠️ **已归档**：所有 Phase 1~3 均已完成（2026-06-10 制定，2026-06-27 全部落地），见 `TuiYan_CHANGELOG.md`。本文件保留仅供设计背景参考。


**制定者：** Claude  
**目标：** 将系统从"经济金融雷达"升级为"世界运转理解系统"——自动采集多域信息、持续推演可能发生的事、主动提醒关键变化、并能回答用户的自由提问。

---

## 现状诊断

### 当前能力
- 经济金融：FRED 50+指标、中国宏观、供应链压力（GSCPI）✅ 完整
- 地缘政治：GDELT + GPR 地缘向量（GRV 5维）🟡 粗粒度
- 社会信号：GDELT 抗议/宗教维度（刚上线，数据积累中）🟡
- 弱信号扫描：7条共振规则（Staging 模式，2026-07-10 切 Live）✅
- 主动推演：B线 GRV 阈值触发、C线 共振触发（Staging）🟡
- Q&A：只能用预设 ntfy 指令，不支持自由提问 ❌

### 核心缺口
1. 没有"正在演化的事件"持久状态（每次扫描都是独立快照）
2. 自然环境、科技产业信号完全缺失
3. 政治日历（选举/央行会议/峰会）未注入推演上下文
4. Q&A 只能触发预设流程，不能自由提问
5. 每日推送是"有触发才推"，没有主动的"今天世界3件事"

---

## Phase 1 — 基础能力补全（目标：2-3周）

### 1A · Q&A 入口（ntfy 自由提问）

**目标：** 用手机发任意问题，系统理解问题意图并作答，不只限于预设指令。

**实现方式：**
- `ntfy_listener.py` 新增 `cmd_ask()` 函数
- 当消息不匹配已知指令时，路由到 `cmd_ask()`
- `cmd_ask()` 构建 prompt：注入当前快照（GRV + 体制 + 最新信号）+ 用户问题
- 调用 `hybrid_llm.reason()` → 推送回答

**触发格式：**
```
1900 ask 现在最值得担心的3件事是什么？
1900 ask 台海最近有没有新动向？
1900 ask 美联储下次会议大概会怎么决策？
```

**新增文件：** `核心代码/ntfy_listener.py`（在已有文件修改，新增约40行）

**注意事项：**
- ask 指令使用 standard 深度的 context（不触发完整分析流程，仅快速 QA）
- 响应时间目标：30s 以内
- 无法回答时明确说明缺乏数据，不捏造

---

### 1B · 每日叙事推送（daily_narrative.py）

**目标：** 每天 07:00 自动生成"今天世界3件最值得关注的事"，ntfy 主动推送，不需要用户触发。

**实现方式：**
- 新建 `核心代码/daily_narrative.py`
- 输入：读取昨日/今日早上的最新数据快照 + 弱信号日志 + GRV + situation_tracker（见1C）
- 输出逻辑：
  1. 找出过去24h 内**变化最显著**的指标（Z-score 最大的3个）
  2. 找出正在演化的事件中**状态有更新**的（情境记忆，见1C）
  3. 找出**即将发生**的重要时间节点（政治日历，见Phase 2C，本阶段可以占位）
- 调用 LLM 把以上3类素材合成1段150字左右的中文叙事
- ntfy 推送，标题：`📡 今日世界摘要 [日期]`

**新增文件：** `核心代码/daily_narrative.py`（约150行）

**调度：**
```python
# scheduler.py 新增
("daily_narrative", "0700", "1-7", None, [PYTHON, "daily_narrative.py"]),
```

**关键设计原则：**
- 即使所有指标都平稳，也要推送（"今天没有异常，当前最需要关注的是……"）
- 不重复昨天的内容（与上次推送做 diff）
- 字数严格控制，手机端友好

---

### 1C · 情境记忆（situation_tracker.py）

**目标：** 追踪正在演化的事件，让推演有持续的上下文而不是独立快照。

**实现方式：**
- 新建 `核心代码/situation_tracker.py`
- 新建 `data/situations.yaml`，每条事件结构：

```yaml
situations:
  - id: trade_war_2025
    name: "2025美中关税战"
    category: TRADE
    status: escalating  # calm / watching / escalating / de-escalating / resolved
    started: 2025-02-01
    last_updated: 2026-06-10
    signal_keywords: ["关税", "tariff", "贸易战", "trade war", "145%"]
    linked_indicators: ["global_trade_tension", "GPRC_CHN"]
    recent_signals: []  # 自动填入，最近3条匹配标题
    notes: "日内瓦峰会90天暂停，2026-07 到期"

  - id: taiwan_strait_2026
    name: "台海紧张态势"
    category: GEO
    status: watching
    ...
```

- `situation_tracker.update()` 每次弱信号扫描后自动调用：
  - 遍历 situations.yaml 中的事件
  - 从 news.db 查找匹配 signal_keywords 的新文章
  - 更新 recent_signals + last_updated
  - 如果信号强度变化 > 阈值，标记 status 变化
- `situation_tracker.get_context()` 供 daily_narrative / hypothesis_engine / ask 调用，返回当前所有 watching/escalating 事件的摘要

**接入点：**
- `scan_weak_signals.py` 末尾调用 `situation_tracker.update()`
- `daily_narrative.py` 调用 `situation_tracker.get_context()`
- `hypothesis_engine.py` 的 `[DATA]` 节末尾注入 situation 上下文
- `cmd_ask()` 注入 situation 上下文

**初始预设事件（人工维护，通过 ntfy 指令可扩展）：**
- 2025美中关税战
- 台海紧张态势
- 美联储降息周期
- 中国经济再平衡
- 俄乌冲突
- AI监管演进

**新增 ntfy 指令：**
```
1900 situations          # 列出所有正在追踪的事件
1900 add_situation <名称> <类别>   # 添加新事件
```

---

### 1D · 异常组合检测（signal_synthesizer 升级）

**目标：** 检测"平时低相关的指标突然同向变化"，比单个阈值更早感知"有什么不对劲"。

**实现方式：**
- 在 `signal_synthesizer.py` 新增规则 R08：
  - 计算30日滚动相关系数 vs 90日基准相关系数
  - 检测"原本不相关的指标对"是否突然出现高度相关（|Δcorr| > 0.4）
  - 例：黄金与债券同时上涨（避险共振），原油与VIX同时上涨（供给危机信号）
- 数据来自 `data/fred_history/*.csv`，滑动窗口计算，无需新增数据源
- 检测到异常对后，写入 synthesis_log，Staging 期间仅记录不推演

**新增规则：**
```yaml
# synthesis_rules.yaml 追加
- rule_id: R08
  name: 跨资产相关性突变
  enabled: true
  trigger:
    type: correlation_shift
    asset_pairs:
      - [VIX, DGS10]       # 恐慌+长债同升：避险共振
      - [DCOILWTICO, VIX]  # 油价+恐慌同升：供给危机
      - [BAA10Y, T10Y2Y]   # 信用利差+曲线倒挂：银行系统压力
    delta_threshold: 0.4   # 30d vs 90d 相关系数变化
    window_short: 30
    window_long: 90
  cooldown_days: 7
  priority: 2
```

---

### 1E · 补数据源

**目标：** 填补当前经济之外最直接相关的数据缺口。

| 数据 | 来源 | 接入方式 | 意义 |
|------|------|--------|------|
| 波罗的海干散货指数 BDI | Stooq（免费，CSV直下）| `fetch_fred_history.py` 新增自定义源 | 全球贸易实物流量，领先指标 |
| 离岸人民币 USD/CNH | FRED: DEXCHUS | 同上 | 中国资本外流压力、人民币贬值信号 |
| 铜价 | FRED: PCOPPUSDM | 同上 | 中国需求领先指标（铜博士）|
| FAO 粮食价格指数 | FAO 开放 API | 新建 `fetch_fao.py`（月度）| 社会稳定传导路径，尤其新兴市场 |
| 美国 TGA 财政部账户余额 | FRED: WDTGAL | `fetch_fred_history.py` 追加 | 流动性抽水/注水信号 |

**新增文件：** `核心代码/fetch_fao.py`（约60行）  
**修改文件：** `核心代码/fetch_fred_history.py`（SERIES 列表追加4个）  
**调度：** FAO 为月度数据，加入每月1日 09:10 拉取任务

---

## Phase 2 — 多域覆盖（目标：1个月）

### 2A · 自然环境信号（fetch_climate_signals.py）

**目标：** 接入气候异常、极端天气、厄尔尼诺数据，建立"自然环境→粮食→通胀→社会稳定"传导路径。

**数据源：**
- **NOAA 气候异常**：`https://www.ncei.noaa.gov/access/monitoring/monthly-report/` 开放 API，全球温度异常
- **厄尔尼诺 ONI 指数**：NOAA CPC 月度，ONI > 0.5 = 厄尔尼诺（影响农业产量）
- **FIRMS 卫星热点已有**：Crucix 已接入6区域火点数据，可直接利用 → 新增到 GRV 气候维度

**新增文件：** `核心代码/fetch_climate_signals.py`（约120行）

**新增 GRV 维度：** `climate_risk`（ONI 指数 + 极端天气频率指数）

**新增传导路径：**
```yaml
- id: climate_food_inflation
  scenario: CLIMATE
  calibration_score: 0.65
  causal_chain:
    - step: 厄尔尼诺/极端天气 → 主产区减产
      delay_months: 3-6
    - step: 粮食价格上涨 → 新兴市场通胀
      delay_months: 1-3
    - step: 食品通胀 → 社会不稳定风险
      delay_months: 3-12
```

**调度：** 每月1日拉取（ONI 为月度数据）

---

### 2B · 社会信号深化

**目标：** 在现有 GDELT 抗议/宗教维度基础上，增加更有预测力的"早期社会压力"指标。

**新增数据：**
- **基尼系数/贫富差距**：世界银行 API（年度，注入结构先验）
- **失业率不满指数**：青年失业率（各国 FRED 系列，已有部分）+ 社交媒体情绪（GDELT Tone 字段）
- **GDELT Tone 平均值**：全球新闻情绪均值，持续负值 = 社会悲观情绪积累

**新增弱信号维度：**
```python
# scan_weak_signals.py 新增维度
"social_stress_index": {
    "gdelt_tone_30d_avg": ...,   # GDELT Tone 30日均值（越负越差）
    "youth_unemployment": ...,   # 青年失业率 Z-score
}
```

**新增 synthesis 规则 R09：**
```yaml
- rule_id: R09
  name: 社会压力指数突破
  trigger:
    categories: ["社会政治危机"]
    min_scan_count: 3
    min_avg_ratio: 2.0
  gdelt_dimension: social_stress_index
  cooldown_days: 14
```

---

### 2C · 政治日历（political_calendar.yaml）

**目标：** 将已知的重要政治节点注入推演上下文，让 daily_narrative 和 Q&A 能感知"接下来30天会发生什么"。

**新建文件：** `知识库/political_calendar.yaml`

```yaml
# 格式
events:
  - date: 2026-07-15
    name: "美国 Q2 GDP 初值"
    category: MACRO
    importance: HIGH
    notes: "首次确认经济是否陷入技术性衰退"
    related_indicators: [GDPC1, UNRATE]

  - date: 2026-07-29
    name: "美联储 FOMC 会议"
    category: MACRO
    importance: HIGH
    notes: "市场预期不变，关注声明措辞是否暗示降息时间表"

  - date: 2026-11-xx
    name: "美国中期选举"
    category: POLITICAL
    importance: HIGH
    ...
```

**接入方式：**
- `daily_narrative.py`：每天检查未来30天内的高重要性事件，注入"即将发生"段落
- `hypothesis_engine.py`：推演前注入 `[CALENDAR]` 节（未来14天事件背景）
- `cmd_ask()` 的 context 包含即将发生的事件

**维护方式：**
- 人工维护：通过编辑 `political_calendar.yaml`（热挂载，立即生效）
- ntfy 指令查询：`1900 ask 未来30天有什么重要事件？` → 系统读取 calendar 回答

---

### 2D · 文化信号（贸易摩擦中的文化因素追踪）

**目标：** 捕捉"消费者抵制"、"软实力冲突"等文化层面信号，这类信号对科技/消费品跨国公司有直接影响。

**实现方式：**
- 在 `ALERT_KEYWORDS` 追加文化摩擦类关键词：
  - "消费者抵制", "boycott", "cultural tension", "soft power", "新疆", "人权", "文化冲突"
- 新增 GDELT 维度 `cultural_friction`（Actor 含 EDU/MED 类型的摩擦事件）
- 新增传导路径 `cultural_trade_boycott`（已在社会信号扩展中加入 cal=0.55）
- 在 GRV 结构新增 `cultural_friction` 维度（权重低，作为参考信号）

**新增 synthesis 规则 R10（初期 disabled）：**
```yaml
- rule_id: R10
  name: 文化贸易摩擦共振
  enabled: false  # 数据积累后开启
  trigger:
    categories: ["地缘升级", "社会政治危机"]
    gdelt_dimension: cultural_friction
    gdelt_threshold: 30
  cooldown_days: 21
```

---

## Phase 3 — 智能深化（目标：2-3个月）

### 3A · Web 对话界面（FastAPI）

**目标：** 提供比 ntfy 更好的 Q&A 体验，支持历史查询和自由对话。

**技术方案：**
- FastAPI + 简单 HTML 前端（无框架依赖）
- 接口：
  - `POST /ask` — 自由提问，流式返回
  - `GET /status` — 系统状态 JSON
  - `GET /grv` — GRV 向量时序
  - `GET /situations` — 当前追踪事件列表
  - `GET /reports` — 最近报告列表
- NAS 上暴露端口（如 8899），局域网访问
- ntfy 继续保留，Web 是补充

**新增文件：** `核心代码/web_server.py`（约200行）  
**部署：** `entrypoint.sh` 追加启动 `python3 web_server.py &`

---

### 3B · 多步推理链

**目标：** 对复杂跨域情景（如"台海升级→半导体断供→全球工业链重组→哪些国家经济受益"）实现分步推理而非一次性注入。

**实现方式：**
- `hypothesis_engine.py` 新增 `multi_step_reason()` 模式
- 第一轮：LLM 识别情景的"关键不确定因素"（返回结构化 JSON）
- 第二轮：对每个不确定因素分别估计概率区间（并行）
- 第三轮：综合各因素，输出情景概率树和最终推演

**触发方式：**
```
1900 hypothesis 台海封锁 L3 deep   # deep 参数触发多步推理
```

---

### 3C · 因果图持久化（自适应权重）

**目标：** 系统从历史预测命中/失败中学习传导路径的真实可靠性，动态调整推演权重。

**实现方式：**
- 扩展 `verify_hypothesis.py`：每次 verified:true 时，对命中的传导路径的 `calibration_score` 按贝叶斯更新
  - 命中：`score = score * 0.9 + 0.1 * 1.0`（向1靠拢）
  - 失败：`score = score * 0.9 + 0.1 * 0.0`（向0靠拢）
- 更新写入 `propagation_paths.yaml`（自动）
- 月度报告：哪些路径预测力在上升，哪些在下降

---

## 实施顺序与时间节点

```
2026-06-10 开始
  │
  ├─ Week 1
  │   ├─ Phase 1A：Q&A 入口（2天）
  │   └─ Phase 1B：daily_narrative（2天）
  │
  ├─ Week 2
  │   ├─ Phase 1C：situation_tracker（3天）
  │   └─ Phase 1E：补数据源（1天）
  │
  ├─ Week 3
  │   └─ Phase 1D：异常组合检测（2天）
  │
  ├─ Week 4-6（2026-07）
  │   ├─ Phase 2A：自然环境信号
  │   └─ Phase 2B：社会信号深化
  │
  ├─ Week 7-8（2026-07）
  │   ├─ Phase 2C：政治日历
  │   └─ Phase 2D：文化信号
  │
  └─ 2026-08 ～ 2026-09
      ├─ Phase 3A：Web 界面
      ├─ Phase 3B：多步推理链
      └─ Phase 3C：因果图持久化
```

---

## 关键设计原则

1. **每次改动前必须读 TuiYan_CHANGELOG.md，改完必须追加记录**
2. **新增数据源先验证可用性再写入调度**（避免 ACLED 那种情况）
3. **所有新模块对主流程非阻断**（try/except 保护，失败降级而不是崩溃）
4. **Phase 1 改动全部热挂载可用**（不需要重建镜像）
5. **推送内容要"手机友好"**：短、有重点、不堆砌数字

---

## 文件变更汇总

### Phase 1 新增文件
- `核心代码/daily_narrative.py`
- `核心代码/situation_tracker.py`
- `核心代码/fetch_fao.py`
- `data/situations.yaml`（初始预设6个事件）

### Phase 1 修改文件
- `核心代码/ntfy_listener.py`（新增 cmd_ask, cmd_situations）
- `核心代码/fetch_fred_history.py`（新增 BDI/CNH/铜价/TGA）
- `核心代码/scan_weak_signals.py`（接入 situation_tracker.update）
- `核心代码/signal_synthesizer.py`（新增 R08 相关性突变规则）
- `核心代码/synthesis_rules.yaml`（新增 R08）
- `核心代码/scheduler.py`（新增 daily_narrative 07:00 任务）
- `核心代码/hypothesis_engine.py`（注入 situation context）

### Phase 2 新增文件
- `核心代码/fetch_climate_signals.py`
- `知识库/political_calendar.yaml`

### Phase 2 修改文件
- `核心代码/geo_risk_vector.py`（新增 climate_risk 维度）
- `核心代码/scan_weak_signals.py`（新增社会压力维度）
- `核心代码/synthesis_rules.yaml`（新增 R09、R10）
- `知识库/财经知识库/02_分析框架/propagation_paths.yaml`（新增气候路径）

### Phase 3 新增文件
- `核心代码/web_server.py`

---

*本方案由 Claude 制定于 2026-06-10，实施前每个 Phase 重新确认技术细节。*
