# 天璇推演引擎 — Agent交互协议 v1.0

> 时间：2026-07-30
> 状态：已确定，可作为macro-sim重写的设计规范
> 上级文档：`16_世界推演系统_架构总文档_v1.0.md`

---

## 一、Agent列表

### 1.1 硬编码常驻（每次推演都激活）

| 类型 | Agent ID |
|------|---------|
| 国家政府 | US_GOV / CN_GOV / EU_GOV / JP_GOV / UK_GOV |
| 央行 | FED / ECB / PBOC / BOJ / BOE |
| 能源组织 | OPEC |

### 1.2 规则激活（触发条件明确）

| 触发情景 | 激活Agent |
|---------|---------|
| 任何军事情景 | 对应国家军队（US_MIL / CN_MIL等，与政府并行，可有分歧）|
| 台海类 | KR_GOV / TW_GOV |
| 中东类 | SA_GOV / IR_GOV / IL_GOV |
| 地缘冲突类 | RU_GOV / RU_MIL |
| 南亚/供应链类 | IN_GOV / IN_CB |
| 货币政策溢出类 | 其他相关央行（LLM判断） |
| 各类情景 | 对应区域舆论/媒体（MEDIA_US / MEDIA_CN / MEDIA_EU等）|
| 失效国家特殊情景 | 武装派系/地区势力 |

### 1.3 LLM按需激活（不预设）

- IMF、世界银行、WTO、联合国
- WHO、IAEA等专项组织
- 其他国际机构

LLM在每轮开始时根据当前情景判断是否需要激活，并给出激活理由。

---

## 二、Agent输出格式

### 2.1 通用字段（所有Agent必须包含）

```json
{
  "agent_id": "FED",
  "round": 3,
  "responding_to": [
    { "agent_id": "US_GOV", "round": 2, "action_ref": "新关税公告" }
  ],
  "action": "维持利率5.25%不变，措辞偏鸽",
  "causal_chains": [
    {
      "id": "chain_001",
      "nodes": ["台海紧张↑", "能源价格↑", "通胀上行压力"],
      "confidence": 0.7,
      "source": "historical_match"
    },
    {
      "id": "chain_002",
      "nodes": ["金融市场避险↑", "经济下行风险↑", "降息压力"],
      "confidence": 0.6,
      "source": "llm_reasoning"
    }
  ],
  "expected_state_changes": [
    { "variable": "us_10y_yield", "direction": "down", "magnitude": "5-10bp", "horizon": "1w" },
    { "variable": "usd_index",    "direction": "up",   "magnitude": "0.3-0.5%", "horizon": "1w" }
  ],
  "constraints": ["通胀授权限制降息空间", "劳动力市场仍强"],
  "key_uncertainties": ["中国是否报复性降汇率", "油价是否进一步上涨"],
  "confidence": 0.65,
  "time_horizon": "4w"
}
```

### 2.2 类型专属字段

**央行类（FED / ECB / PBOC / BOJ / BOE / 其他央行）：**
```json
{
  "rate_direction": "hold",        // raise / cut / hold
  "rate_magnitude": 0,             // bps，hold时为0
  "forward_guidance": "data_dependent_dovish"
}
```

**政府类（US_GOV / CN_GOV / EU_GOV等）：**
```json
{
  "policy_action": "新增关税25%覆盖半导体设备",
  "diplomatic_stance": "confrontational", // cooperative / neutral / confrontational
  "escalation_intent": 0.3        // 0=降级意愿强，1=升级意愿强
}
```

**军队类（US_MIL / CN_MIL / RU_MIL等）：**
```json
{
  "readiness_level": "elevated",   // normal / elevated / high / maximum
  "deployment_change": "航母战斗群进入第一岛链",
  "action_intent": "deterrence"    // deterrence / defensive / offensive
}
```

**舆论/媒体类（MEDIA_US / MEDIA_CN等）：**
```json
{
  "narrative_frame": "escalation_risk",  // 主导叙事框架
  "intensity": 0.75,              // 0=平静，1=极度紧张
  "geographic_scope": ["US", "TW", "CN"]
}
```

**国际组织类（IMF / WHO / IAEA等）：**
```json
{
  "intervention_type": "emergency_consultation",
  "conditions": ["停火协议", "人道主义通道"],
  "affected_parties": ["CN_GOV", "TW_GOV", "US_GOV"]
}
```

---

## 三、轮次协议

### 3.1 时间单位

| 情景类型 | 一轮=时间单位 |
|---------|------------|
| 金融市场冲击 | 1周 |
| 地缘军事事件 | 1个月 |
| 结构性地缘转变 | 1个季度 |

### 3.2 单轮执行流程

```
轮次开始
    ↓
① 读取当前世界状态
   慢变量分数（UCRI/IRP/GCI）
   快变量GRV 11维（带不确定度）
   上一轮价格（利率/汇率/大宗商品/情绪指数）
   上一轮所有agent输出
    ↓
② 激活Agent子集
   常驻agent全部激活
   规则触发agent按情景激活
   LLM判断是否需要激活国际组织（给出理由）
    ↓
③ Agent分批执行
   批次内：同步（所有agent同时读取状态，互相看不到本轮其他agent输出）
   批次间：顺序（后批能看到前批的完整输出）

   第一批（政策制定层，最慢）：所有政府类
   第二批（响应层）：所有央行类 + 军队类（如已激活）
   第三批（协调层）：国际组织类（如已激活）
   第四批（舆论层）：舆论/媒体类
    ↓
④ 价格更新（非Agent，确定性计算）
   汇总所有agent的expected_state_changes
   加权计算各价格变量净变化方向和幅度
   更新：利率/债券收益率、汇率、大宗商品、市场情绪指数
    ↓
⑤ 检查停止条件（满足任一则停止）
   概率树过于发散（所有路径概率 < 阈值）
   已到时间边界（按情景类型动态判断）
   状态收敛（所有路径指向同一稳定状态）
    ↓
⑥ 未停止 → 进入下一轮，回到①
   已停止 → 提取关键转折点，整理三种输出
```

### 3.3 价格更新权重规则

不同Agent对不同价格变量的影响权重不同：

| 价格变量 | 主导Agent | 次要Agent |
|---------|---------|---------|
| 利率/债券收益率 | 央行类 | 政府类（财政政策溢出）|
| 汇率 | 央行类（直接干预）| 政府类（贸易政策）|
| 大宗商品 | OPEC | 地缘冲突相关政府/军队 |
| 市场情绪指数 | 舆论/媒体类 | 军队类（升级信号）|

价格更新公式（初始版，可被玉衡校准调整）：
```
价格变化 = Σ(agent_weight × agent_expected_magnitude × direction_sign)
```

### 3.4 校准阶段 vs 推演阶段

**校准阶段（内部，不输出给用户）：**
- 用历史数据回放N轮
- 每轮结束后对比agent输出的expected_state_changes与历史真实价格变化
- 调整agent的causal_chain置信度直到误差收敛
- 收敛条件驱动，不固定轮数

**推演阶段（输出给用户）：**
- 基于校准后的agent参数向前推演
- 满足停止条件后输出三种结果

---

## 四、天玑溯源接口

每轮结束后，以下数据写入reasoning_trace表供天玑使用：

```json
{
  "round": 3,
  "scenario_id": "taiwan_strait_20260730",
  "agent_outputs": [...],          // 本轮所有agent完整输出
  "price_updates": {...},          // 本轮价格更新结果
  "active_causal_chains": [        // 本轮实际激活的因果链
    {
      "chain_id": "chain_001",
      "from_agent": "FED",
      "nodes": ["台海紧张↑", "能源价格↑", "通胀上行压力"],
      "contributed_to_prediction": "pred_042"  // 关联预测ID
    }
  ]
}
```

天玑验证时，可以精确追溯到：
- 哪个Agent的哪条因果链导致了哪条预测
- 因果链的哪个节点之间的传导判断失效了

---

## 五、待解决问题

| 编号 | 问题 | 优先级 |
|------|------|--------|
| A1 | 价格更新的具体权重如何冷启动？初始值怎么填？ | 阶段二 |
| A2 | 校准阶段收敛的具体判断标准（误差阈值）如何设定？ | 阶段二 |
| A3 | 同一情景下多个军队agent同时激活时，军队之间是否需要直接交互？ | 阶段三 |
| A4 | LLM激活国际组织的判断逻辑如何防止过度激活（每轮都激活IMF）？ | 阶段二 |
