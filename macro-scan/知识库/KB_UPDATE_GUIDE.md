# 知识库维护操作手册（KB_UPDATE_GUIDE）

> 本文件供任何 AI 助手或人工维护者参考，说明每个知识库文件的更新方式、信息源和操作规范。
> 
> 自动更新（数值字段）：`docker exec macro-scan python /app/update_kb_numbers.py`  
> 人工/AI 更新（叙事 + 事件）：按本手册操作

---

## 文件清单与更新分工

| 文件 | 更新频率 | 自动更新 | 需要AI/人工 |
|:-----|:-------:|:-------:|:-----------:|
| `2026全球宏观基准情景.md` | 月度 | 数值字段 | 叙事/风险概率 |
| `央行决策框架.md` | 月度 | FFR/CPI数字 | 政策路径叙事 |
| `板块轮动与经济周期.md` | 月度 | 当前体制映射 | 一般不需要 |
| `跨资产危机阈值基准表.md` | 季度 | — | 阈值校准 |
| `大国博弈分析框架.md` | 事件驱动 | — | 全部 |
| `地缘事件日志.json` | 事件驱动 | last_checked时间戳 | 新增事件 |

---

## 一、2026全球宏观基准情景.md

**文件路径：** `知识库/财经知识库/21_专题报告/2026全球宏观基准情景.md`

### 数据源

| 指标 | 来源 | 查询方式 |
|:-----|:-----|:---------|
| FFR（联邦基金利率） | FRED: `DFF` | fredapi 或 fred.stlouisfed.org |
| CPI YoY | FRED: `CPIAUCSL`（算同比） | — |
| 核心 PCE | FRED: `PCEPILFE` | — |
| UNRATE | FRED: `UNRATE` | — |
| 萨姆规则 | FRED: `SAHMREALTIME` | — |
| 10Y-2Y 利差 | FRED: `DGS10` - `DGS2` | — |
| WTI 原油 | FRED: `DCOILWTICO` | — |
| GDP 季度折年 | FRED: `GDPC1` | BEA 季度公布 |

### 需要 AI 更新的内容

1. **尾部风险概率**（如"二次通胀概率：约25-35%"）  
   触发条件：CPI 连续两月超预期 / 萨姆规则突破 0.3 / WTI 突破 $120  
   操作：根据最新数据判断是否调整概率区间，修改对应文字

2. **联储政策路径描述**（"基准路径/鹰派路径/鸽派路径"三段）  
   触发条件：FOMC 会议后、重大通胀数据发布后  
   信息源：Fed 官网声明 `federalreserve.gov/monetarypolicy`、FOMC 纪要

3. **"关键时间节点"表格**  
   触发条件：每季度末审阅，将已过去的事件标记 ✅，补充新的

4. **GEO_BASELINE 代码块**（文件末尾的 Python 字典）  
   触发条件：地缘事件日志有重大变更时同步更新

---

## 二、央行决策框架.md

**文件路径：** `知识库/财经知识库/04_分析框架/央行决策框架.md`

### 数据源

| 央行 | 信息源 |
|:-----|:------|
| 美联储 | FRED `DFF`；federalreserve.gov 声明 |
| 欧洲央行 | ecb.europa.eu 货币政策决议 |
| 日本央行 | boj.or.jp 政策决定会议结果 |
| 中国央行 | pbc.gov.cn；7天逆回购利率公告 |

### 需要 AI 更新的内容

1. **泰勒规则隐含值**  
   公式：`r* = 2% + CPI + 0.5×(CPI-2%) + 0.5×output_gap`  
   用最新 CPI 代入重算，更新文件中的"泰勒规则隐含值约 X.X%"

2. **加息/降息周期表**（Section 7.1）  
   触发条件：有新的加息或降息动作  
   操作：在表格末行追加新记录

3. **BOJ 特殊说明**  
   触发条件：BOJ 有政策变化（YCC调整、加息）  
   信息源：boj.or.jp 英文页面

---

## 三、大国博弈分析框架.md

**文件路径：** `知识库/财经知识库/04_分析框架/大国博弈分析框架.md`

> 此文件几乎全部需要 AI/人工更新，无自动化部分。

### 信息源

| 内容 | 信息源 |
|:-----|:------|
| 关税变化 | USTR.gov；中国商务部 mofcom.gov.cn |
| 芯片管制 | BIS（commerce.gov/bis）；路透/FT |
| 峰会/外交事件 | 白宫声明 whitehouse.gov；新华网 |
| 情景概率 | 主观判断，参考主流投行报告 |

### 操作规范

1. **贸易战时间线**：按时间顺序追加，格式统一  
   `YYYY-MM：[事件描述]（关税率变化/影响）`

2. **情景矩阵概率**：更新时说明调整理由  
   四个情景合计必须 = 100%

3. **芯片战时间线**：追加新的管制措施，注明生效日期

---

## 四、地缘事件日志.json

**文件路径：** `知识库/财经知识库/02_核心变量因果链/地缘事件日志.json`

> ⚠️ 严格 JSON 格式，编辑后必须验证：
> ```bash
> python -c "import json; json.load(open('地缘事件日志.json', encoding='utf-8')); print('OK')"
> ```

### 触发条件（满足任一则新增事件）

- 重大央行政策变化（加息/降息/QE/QT）
- 关税或贸易摩擦重大变化（>10% 幅度）
- 地缘冲突升级（军事行动、制裁、峰会）
- 主权评级变化

### 新增事件模板

```json
{
  "id": "E007",
  "date": "YYYY-MM-DD",
  "event": "事件名称（简洁）",
  "summary": "2-3句话描述事件背景和影响",
  "key_signals": [
    "关键数据点或信号1",
    "关键数据点或信号2"
  ],
  "risk_impact": {
    "taiwan_strait":   {"before": 0, "after": 0, "change": 0, "reason": "说明"},
    "tech_decoupling": {"before": 0, "after": 0, "change": 0, "reason": "说明"},
    "global_trade":    {"before": 0, "after": 0, "change": 0, "reason": "说明"},
    "energy_shock":    {"before": 0, "after": 0, "change": 0, "reason": "说明"}
  },
  "transmission_paths": {
    "short_term": "传导路径描述",
    "mid_term": "中期影响",
    "key_watch": ["待观察指标1", "待观察指标2"]
  },
  "active": true
}
```

### 打分规则

- 分值范围：0–10（0=无影响，10=系统性危机）
- `before`：此事件发生前该维度的值（参考上一个影响该维度的事件的 `after`）
- `active`：近30天内或持续影响中为 true，否则改为 false

---

## 五、跨资产危机阈值基准表.md

**文件路径：** `知识库/财经知识库/04_分析框架/跨资产危机阈值基准表.md`

### 更新频率：季度（或危机期间随时）

### 需要更新的内容

1. **当前市场值**（如"当前 VIX = X.X"）  
   信息源：FRED `VIXCLS`；FRED `BAMLH0A0HYM2`（HY利差）

2. **阈值校准**（如警戒线 / 危机线数值）  
   触发条件：历史阈值在新的宏观背景下已不适用（如高利率环境下 HY 利差基准上移）  
   操作：参考最近2年均值重新锚定，注明调整日期和理由

---

## 六、板块轮动与经济周期.md

**文件路径：** `知识库/财经知识库/04_分析框架/板块轮动与经济周期.md`

> 历史统计数据（Section 二、三）基本不需要更新。

### 需要更新的内容

- **Section 五"当前体制映射"** — 由 `update_kb_numbers.py` 自动更新
- 若体制发生切换（如从 stagflation 进入 recession），需手动更新推荐/规避板块

---

## 七、执行清单（每月1日审阅）

```
[ ] 运行 update_kb_numbers.py（自动更新数值）
[ ] 查看 ntfy 通知，确认数值更新正常
[ ] 人工检查：本月是否有地缘事件需加入 地缘事件日志.json？
[ ] 人工检查：央行政策路径描述是否需要更新？
[ ] 人工检查：贸易战/芯片战时间线是否有新进展？
[ ] 如有更新 → xcopy 同步到 NAS → rebuild RAG 索引
[ ] 追加 TuiYan_CHANGELOG（修改者 + 修改理由）
```

---

## 八、给 AI 助手的指令模板

将以下内容连同相关 .md 文件内容一起发给 AI：

```
你是世界推演系统的知识库维护员。
今天日期：[DATE]
当前宏观数据：[从系统报告复制关键数字]

请根据以下最新信息，更新对应知识库文件：
[粘贴最新新闻/数据]

操作要求：
1. 只修改与新信息直接相关的段落
2. 保持原文件的格式和结构
3. 如修改地缘事件日志，严格遵守 JSON schema，修改后告知我需要运行验证命令
4. 说明每处修改的理由
5. 完成后列出：修改文件 / 修改内容摘要 / 建议追加到 TuiYan_CHANGELOG 的条目
```

---

## 九、scenario_wiki.md — 假设推演知识库

**文件路径：** `data/scenario_wiki.md`  
**维护方式：** 自动（每次假设推演后 daemon thread 异步追加）

### 条目结构

每个条目包含：情景类型/烈度/标签 / 传导路径（从报告中提取） / 输入时刻的实时指标快照 / `verified: false`（默认）/ `actual_outcome`（待事后填写）

### 人工维护项

| 操作 | 触发时机 | 方式 |
|:-----|:---------|:-----|
| 填写 `actual_outcome` | 推演后事件实际发生或已可判断方向 | 直接编辑 scenario_wiki.md，填写结果描述 |
| 将 `verified: false` 改为 `verified: true` | actual_outcome 已填写且方向可判断 | 编辑对应条目 |
| 标记 `status: deprecated` | 发现某条推演结论明显有误 | 加 `superseded_by: <新条目entry_id>` |

### 注意事项

- 不要删除条目（改为 deprecated，保留溯源）
- `falsifiability_type: counterfactual` 的条目（如台海冲突）无法事后精确验证，季度人工评估方向即可
- 条目 ≥ 60 条后建议将 `verified=true` 且 `ref_count=0` 的老条目移入 `data/scenario_wiki_archive.md`

### 每月审阅清单（追加到七、执行清单）

```
[ ] 查看 scenario_wiki.md 有无新条目需要填写 actual_outcome？
[ ] 已发生情景：将 verified 改为 true
[ ] 追加 TuiYan_CHANGELOG（修改者 + 修改理由）
```

---

## 十、propagation_paths.yaml — 传导路径知识库（M1-3）

**文件路径：** `知识库/财经知识库/04_分析框架/propagation_paths.yaml`  
**维护方式：** 热挂载，修改后立即生效，无需重启容器

### 字段说明

| 字段 | 说明 |
|:-----|:-----|
| `calibration_score` | 综合置信度 [0-1]，初始值基于历史数据质量判断 |
| `source` | `historical_data`/`supply_chain_analysis`/`llm_inference`/`empirically_calibrated` |
| `causal_chain[].lag_days` | 从上一步到本步的估算延迟（天） |
| `causal_chain[].confidence` | 该步置信度 [0-1] |

### 升格规则

| 条件 | 操作 |
|:-----|:-----|
| ≥3次真实事件验证某步骤准确 | `source: llm_inference` → `source: empirically_calibrated` |
| calibration_score 可提升时 | 人工审核后修改数值（通常 🔴 的步骤升为 🟡 对应 0.30→0.50） |
| 发现历史实例应补录 | 在 `historical_instances[]` 追加，`verified: true` |

### 新增路径模板

```yaml
- id: geo_taiwan_xxx               # 唯一标识，snake_case
  scenario_type: GEO               # GEO/FIN/ENERGY/TRADE/MACRO/CRISIS
  subtype: TAIWAN                  # 子类型
  label: 台海xxx → yyy → zzz      # 人可读名称
  calibration_score: 0.30          # 初始给低值，经验证后升格
  data_quality: 混合（无直接先例） # 描述数据来源质量
  causal_chain:
    - step: 1
      event: 触发事件描述
      lag_days: 0
      magnitude: {base: 5, range: [3, 10]}   # 百分比
      confidence: 0.70
      source: historical_data       # 或 llm_inference
  dampening_factors:
    - factor: 降温因素描述
      scale: 0.7                    # 乘以该系数（<1降温，>1放大）
  amplifying_factors:
    - factor: 放大因素描述
      scale: 1.5
  historical_instances:
    - event: 参考历史事件名称
      outcome: 实际结果描述
      verified: true
  notes: "额外说明"
```

### 每月审阅清单

```
[ ] verify_hypothesis.py 有无新校准结果？
[ ] 有无需要升格的 source: llm_inference 步骤？
[ ] 有无需要新增的路径（新情景类型）？
[ ] 追加 TuiYan_CHANGELOG（修改者 + 修改理由）
```

---

## 十一、grv_latest.json — GRV地缘风险向量（M1-2）

**文件路径：** `data/grv_latest.json`  
**维护方式：** 全自动，每日06:10由 `geo_risk_vector.py` 生成，无需人工维护

```json
{
  "taiwan_strait":      45.6,   // GDELT×0.4 + GPR_TWN×0.6，归一化[0-100]
  "us_china_strategic": 53.0,   // GDELT×0.5 + GPR_CHN×0.5
  "russia_europe":      37.4,   // GDELT×0.4 + GPR_RUS×0.6
  "middle_east_energy": 40.5,   // GDELT×0.6 + GPR全球×0.4
  "global_composite":   100.0,  // GPR全球指数归一化（当前历史高位）
  "source_quality":     "gdelt+gpr"  // gdelt+gpr / gdelt_only / stub
}
```

**GPR数据说明：**
- 数据来源：`data/fred_history/GPRC_TWN.csv` 等（由 fetch_gpr.py 每日05:40从官网下载）
- 归一化方法：用滚动10年（最近120条月度数据）P10-P90分位数映射到 [0-100]
- `global_composite=100` 表示当前全球GPR处于近10年历史高位（正常，反映2026年地缘环境）

如果 `source_quality` 停留在 `gdelt_only`，说明 GPR CSV 文件缺失——运行：
```bash
docker exec macro-scan-macro-scan-1 python3 /app/fetch_gpr.py
```

---

*维护人：世界推演系统运维 | 格式版本：2.0 | 更新：2026-05-30*
