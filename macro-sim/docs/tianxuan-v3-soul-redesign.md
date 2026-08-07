# 天璇 v3 重构设计：12 金融 Agent 全量 Soul 化 + 决策可校验 + 过程叙事

**路径：** `macro-sim/docs/tianxuan-v3-soul-redesign.md`
**适用版本：** macro-sim v2.x → v3（重构目标）
**文档状态：** 设计稿 v1.0（待用户拍板）
**最后更新：** 2026-08-07
**作者：** 天璇仿真层架构（world-sim 项目）

---

## 0. 阅读导引（可追溯性声明）

本文档每个设计决策都标注了对应需求来源，用编号引用：

| 需求编号 | 内容 | 对应章节 |
|---------|------|---------|
| ① | 决策理由可校验（reason + evidence） | §3、§6 |
| ② | 过程叙述（逐月发生了什么→为什么→连锁→拐点） | §6 |
| ③ | if-else 全部 soul 化，未来新增 Agent 一律 soul 模式 | §3、§4、§8 |
| ④ | 行为论文锚点（文献 + 参数区间，不拍脑袋阈值） | §4、§5 |

---

## 1. 背景与需求

### 1.1 系统定位

world-sim 三层流水线：

```
天枢 macro-scan（观测层）
  └─ 采集全球宏观信号，产出 GRV 地缘风险向量（论文基础：Estrella-Trubin probit 类）
天璇 macro-sim（仿真层）★ 本文档作用域
  └─ 17 个 Agent 月度时间步长互动演化，Monte Carlo × 100 输出未来 24 个月路径树
天玑（验证层）→ 开阳（展示层）
```

### 1.2 现状缺陷（触发本次重构）

已实测核实（2026-08-07 代码盘点）：

1. **决策黑箱**：12 个金融 Agent 走 `_decide_rules` 硬编码 if-else，每步只返回一个行动字符串，**无理由、无触发信号值、无派系归属**。无法校验"这次降息是否符合 Taylor 规则 / 该 Agent 的 soul / 当时世界状态"。
2. **结果无过程**：`run.py::_write_report` 只产路径表 + 传导链（事件列表）+ LLM 情景定性（3 句总结），**无逐月过程叙述、无决策理由**。
3. **两套决策机制并存**：
   - 金融 Agent（A1-A3/A5-A12）= if-else 确定性规则引擎；
   - 主权 Agent（S1-S5）= soul 驱动派系决策（`internal_factions` 加权抽样）。
   同类行为不同实现，校准、验证、叙事的接口无法统一。
4. **死行动**：
   - `A11 ECBAgent.VALID_ACTIONS` 含 `QE_TIGHTEN`，但 `_decide_rules` 永不产出，`gm_resolve` 也无 `QE_TIGHTEN` delta 分支 —— **完全死行动**；
   - `A8 ChinaPBOCAgent.VALID_ACTIONS` 含 `CUT_LPR`，`gm_resolve` 有 delta 分支（`china_credit_impulse +0.15`），但 `_decide_rules` 永不产出 —— **规则死行动**。
5. **无论文锚点**：所有阈值（sentiment < -0.4、credit_spread > 250+150×threshold 等）均为经验值，无文献来源标注，无法回答"为什么是这个阈值"。

### 1.3 需求清单

1. **决策理由可校验**：每个 Agent 每步必须交代"为什么选这个行动"——`reason + evidence`（触发信号值、命中规则/派系、权重）。否则无法校验决策是否符合 soul / 参数 / 世界状态。
2. **过程叙述**：结果不能只有终态聚合。要有"逐月发生了什么 → 为什么 → 连锁 → 拐点"的完整过程叙事（LLM 生成，基于决策 trace）。
3. **if-else 全部 soul 化**：12 个金融 Agent 行为规则改为 soul 驱动（同 S1-S5 模式）；**未来新增 Agent 一律 soul 模式**（if-else 仅保留为无 soul 时的 fallback）。
4. **行为论文锚点**：天枢有论文基础（Estrella-Trubin），天璇 Agent 行为也必须有——每个行为规则可追溯学术文献，参数有文献区间。

---

## 2. 现状盘点（代码级核实）

> 本节省略改动时可直接对照 `core/agents/*.py`、`core/world_state.py::get_agent_context`、`config/agents.yaml`。

### 2.1 Agent 清单与行动空间（VALID_ACTIONS 实录）

| Agent | 角色 | info_delay | activation_prob | VALID_ACTIONS |
|-------|------|-----------|-----------------|---------------|
| A1 | Fed | 4 | 0.30 | `CUT_50BP` `CUT_25BP` `HOLD` `HIKE_25BP` `VERBAL_INTERVENTION` |
| A2 | 商业银行 | 2 | 0.70 | `TIGHTEN_CREDIT` `HOLD` `EASE_CREDIT` |
| A3 | 对冲基金 | 0 | 1.00 | `SHORT_MARKET` `DECREASE_RISK` `HOLD` `INCREASE_RISK` |
| A4 | 能源国(OPEC+) | 5 | **0（挂起）** | `CUT_SUPPLY` `HOLD` `INCREASE_SUPPLY`（已由 S5_saudi 接管） |
| A5 | 机构投资者 | 2 | 0.60 | `DECREASE_RISK` `HOLD` `INCREASE_RISK` |
| A6 | 媒体/舆论 | 1 | 0.80 | `AMPLIFY_FEAR` `NEUTRAL_REPORT` `HOLD` `AMPLIFY_OPTIMISM` |
| A7 | 新兴市场央行 | 3 | 0.40 | `CAPITAL_CONTROLS` `RAISE_RATES` `HOLD` `CUT_25BP` |
| A8 | 中国央行/财政 | 3 | 0.50 | `CUT_RRR` `CUT_LPR` `FISCAL_STIMULUS_CN` `HOLD` `CNY_INTERVENTION` `TIGHTEN_CN` |
| A9 | 美国财政部 | 4 | 0.30 | `FISCAL_STIMULUS` `HOLD` `FISCAL_TIGHTEN` `DEBT_CEILING_RISK` |
| A10 | 散户/羊群 | 0 | 0.90 | `PANIC_SELL` `HOLD` `FOMO_BUY` |
| A11 | 欧洲央行 | 4 | 0.30 | `CUT_25BP` `HOLD` `HIKE_25BP` `QE_EXPAND` `QE_TIGHTEN` ⚠️死 |
| A12 | 日本央行 | 4 | 0.25 | `HOLD` `ABANDON_YCC` `EASE_YCC` `EMERGENCY_EASE` |
| S1-S5 | 主权国家 | 0 | 0.35 | `HOLD` `IMPOSE_SANCTIONS` `LIFT_SANCTIONS` `MILITARY_DEPLOYMENT` `DIPLOMATIC_ENGAGE` `TECH_RESTRICTION` `ALLIANCE_REINFORCE` `CUT_OUTPUT` `INCREASE_OUTPUT` `EMBARGO_SIGNAL` `NUCLEAR_SIGNAL` `ENERGY_CUTOFF` `CEASEFIRE_SIGNAL`（S5 另含 `DIPLOMATIC_OUTREACH`） |

**死行动核验：**

| 死行动 | VALID_ACTIONS | _decide_rules 产出 | gm_resolve delta |
|--------|:---:|:---:|:---:|
| A11 `QE_TIGHTEN` | ✅ | ❌ 无分支 | ❌ 无分支（完全死） |
| A8 `CUT_LPR` | ✅ | ❌ 无分支 | ✅ 有分支（规则死） |

### 2.2 ctx 字段清单（`get_agent_context` 实录，soul trigger 只能引用这些）

**基础字段（所有 Agent）：**
`external_pressure_shift` `internal_stress` `liquidity_tension` `grv_stress`（0~1，(grv-50)/50）`vix_stress`（0~1，(vix-18)/30）`yield_inverted`（0/1）`market_sentiment`（-1~1）`cycle` `visible_actions`（按 info_delay 注入的 dict）

**角色专属字段：**

| 角色 | 专属 ctx 字段 |
|------|--------------|
| fed (A1) | `fed_rate_change` `credit_spread` `dff` |
| commercial_bank (A2) | `credit_spread` `bank_credit_tightening` `liquidity_premium` |
| hedge_fund (A3) | `vix_shift` `t10y2y` `fund_risk_appetite` `credit_tightening` `sanctions_risk` `disaster_risk` `seismic_risk` `sp500_change` |
| institution (A5) | 同 hedge_fund + `sp500_change` |
| media (A6) | `recent_news` `social_stress` `cultural_friction` |
| em_central_bank (A7) | `em_capital_outflow` `dff_shift` |
| china_pboc (A8) | `china_credit_impulse` `us_china_grv` `usd_cny` |
| us_treasury (A9) | `us_fiscal_pressure` |
| retail (A10) | `retail_panic` |
| ecb (A11) | `ecb_rate` |
| boj (A12) | `yen_carry_risk` `japan_monetary` |
| energy_gov / opec_core | `energy_tension` `energy_grid_risk` `climate_risk` `wti_price` |
| S 类主权 | `russia_europe` `taiwan_strait` `us_china_strategic` `global_composite` `middle_east_energy` `sanctions_risk` `energy_grid_risk` `climate_risk` `social_stress` `domestic_political_pressure` `economic_buffer_months` `board` |

> ⚠️ **字段名陷阱**：A3/A5 的 ctx 里信贷收紧字段叫 `credit_tightening`，A2 的叫 `bank_credit_tightening`——同名不同值来源。soul trigger 书写时必须按 Agent 角色选对字段。

### 2.3 现有 soul 机制（S1-S5，v2.2 已落地，v3 复用）

`core/agents/sovereign.py::_decide_rules` 管线（实测逻辑）：

```
① red_line_triggers（数值表达式，_eval_trigger）→ 命中 → _escalation_action()
   （选 grv_impact_map 中 |影响| 最大的行动）
② internal_factions：weight × (1.3 if trigger 命中) × params.sensitivity → 加权
③ random 加权抽样选派系 → _faction_to_action（bias_actions 优先 → impact_map 随机）
④ 结果不在 VALID_ACTIONS → HOLD
```

关键参数：`boost = 1.3`（v2.2 由 1.5 回调，给约束派留分歧空间）；`_eval_trigger` 支持 `> <` 数值比较、`AND OR`；`ctx.get(var, 0.0)` 兜底缺失变量为 0。

### 2.4 校准 / 报告 / 校验现状

| 模块 | 现状 | v3 缺口 |
|------|------|---------|
| `calibrator.py` | 前 50 步历史拟合，LLM（GLM-Z1-9B）调 sensitivity/threshold/magnitude，评分 0~100 | soul 参数（派系权重/boost）未纳入调参空间 |
| `run.py::_write_report` | 路径表 + 传导链 + 月度进度条 + 校准说明 | 无决策理由表、无逐月过程叙事、`_ACTION_VERB` 无 S 类中文映射 |
| `bifurcation.py::_generate_narrative` | 3 句定性（情景/传导链/影响），原因来自**静态表**（TRIGGER_REASONS） | 静态原因表是拍脑袋的，应改为 trace 驱动 |
| `consistency_validator.py` | Layer1 规则表 + Layer2 LLM 经济学机制校验 | 只用行动对，不看决策理由/信号值 |
| 天玑 `reasoning_trace` | `agent_id="macro-sim"`（汇总级），input_signals 只含 grv/credit_spread/t10y2y | 未下沉到 Agent 决策级 |

---

## 3. 统一决策框架（base.py 重构）

### 3.1 目标

**所有 Agent（金融 + 主权 + 未来新增）走同一条 soul 决策管线**，输出统一的 `ActionDecision`。if-else 只作为"无 soul 时"的 fallback（渐进迁移，行为兼容）。

### 3.2 ActionDecision dataclass（接口签名）

```python
@dataclass
class ActionDecision:
    action: str                 # VALID_ACTIONS 内行动，必填
    reason: str                 # 自然语言理由，中文，如"dove 派系命中：market_sentiment=-0.42 < -0.4"
    evidence: dict              # 结构化证据：见下方 schema
    alternative: str | None     # 次优行动（加权抽样第二候选），无则 None
    faction: str | None         # 选中派系（soul 模式）或 "legacy_rules"（fallback）
    confidence: float           # 0~1，= 选中派系归一化权重（fallback 时为规则确定性 1.0）
    source: str                 # "soul" | "legacy_rules" | "red_line"
```

`evidence` schema（JSON 友好，直接落 JSONL）：

```json
{
  "signals": {"market_sentiment": -0.42, "vix_stress": 0.31},
  "trigger_hit": "market_sentiment < -0.4",
  "faction_weights": {"dove": 0.455, "neutral": 0.4, "hawk": 0.25},
  "selected_faction": "dove",
  "bias_actions": ["CUT_50BP", "CUT_25BP"],
  "red_line_hit": null
}
```

### 3.3 soul 决策管线（统一 `decide(ctx) → ActionDecision`）

伪代码（接口级，非实现）：

```
def decide(ctx) -> ActionDecision:
    if not self.soul:
        # fallback：现有 if-else 包一层
        a = self._decide_rules(ctx)
        return ActionDecision(a, reason="legacy_rules", source="legacy_rules",
                              evidence={"signals": snapshot_signals(ctx)}, ...)

    # ① red_line_triggers：命中 → 强制行动（source="red_line"）
    for rl in soul.red_line_triggers:
        if eval_trigger(rl, ctx):
            return ActionDecision(
                action=escalation_action(ctx),
                reason=f"red_line 触发：{rl}",
                evidence={"trigger_hit": rl, "signals": snapshot_signals(ctx)},
                source="red_line", ...)

    # ② 派系权重：base_weight × boost(trigger命中) × sensitivity
    weights = {}
    for fname, f in soul.internal_factions.items():
        hit = eval_trigger(f.trigger, ctx)
        weights[fname] = f.weight * (FACTION_BOOST if hit else 1.0) * params.sensitivity

    # ③ 加权抽样选派系 → bias_actions 选行动
    faction = weighted_sample(weights)          # 记录 alternative = 次优派系
    action = pick_action(faction, ctx)          # bias_actions 优先序，HOLD 兜底

    # ④ 组装 ActionDecision（confidence = 选中派系归一化权重）
    return ActionDecision(action, reason=f"{faction} 派系命中：{hit_trigger_str}",
                          evidence={...}, faction=faction,
                          alternative=alt_action, source="soul", ...)
```

### 3.4 关键设计决策

| 决策点 | 设计 | 理由 |
|--------|------|------|
| `FACTION_BOOST` | 默认 1.3，配置化（soul 级可覆盖），文献区间见 §5.5 | 沿用 v2.2 验证过的值，避免回归；可校准 |
| 派系权重合成 | `weight × boost × sensitivity`，最终**归一化**后抽样 | 与现有 sovereign 逻辑一致；归一化让 confidence 有界 [0,1] |
| bias_actions 内选行动 | 按列表顺序取第一个在 VALID_ACTIONS 中的；若想表达偏好强度，bias_actions 可带权重映射（v3.1 可选） | 与现有 `_faction_to_action` 兼容，零行为破坏 |
| fallback 语义 | 无 soul → 原 if-else；有 soul 但有派系未命中 → 所有派系权重×1 后照常抽样（neutral 派系天然承接） | 渐进迁移，阶段 1/2 不改变任何行为 |
| red_line 对金融 Agent 开放 | A1/A12 等可配 red_line_triggers（紧急降息/放弃 YCC 属强制响应） | 统一"强制行动"语义，与 S 类一致 |
| `_eval_trigger` 扩展 | 保持数值表达式；**另加 `visible(...)` 语法** 或保留在 bias/trigger 前由管线注入布尔变量 `flag_media_fear`/`flag_hf_short` 等（见 §7.2） | 现有 eval 不支持字符串比较；用布尔注入最小改动 |

### 3.5 可追溯性对照（需求 ①②③）

- ① 每个决策必含 `reason + evidence`，evidence 含触发信号值、命中 trigger、派系权重、alternative；
- ③ 决策管线唯一化：新增 Agent 只需提供 soul YAML，无需写 if-else。

---

## 4. 12 个金融 Soul 设计表

> 通用约定：
> - `weight` 为基线权重（无 trigger 命中时），trigger 命中 × 1.3（FACTION_BOOST）；
> - bias_actions 内行动必须存在于该 Agent 的 VALID_ACTIONS（§2.1）；
> - 触发表达式变量名全部来自 §2.2 的该角色 ctx 字段；
> - 每个派系的文献锚点在 §5 统一引用，本节只放引用 ID（如 [T-1993]）；
> - 所有阈值默认取 threshold=0.5、sensitivity=1.0 换算后的值（校准后可变）。

### 4.0 参数换算基准

现有代码的 `threshold × k` 逻辑：`sentiment` 无缩放直接比（±1 量纲），`vix_stress/grv_stress` 乘以 sensitivity 后比（0~1 量纲）。设计文档统一用**绝对信号值**表达 trigger（不含 params 缩放），把"是否缩放"下沉为引擎约定：

> **约定**：soul trigger 表达式内的变量按 ctx 原始值参与 eval；`params.sensitivity` 只作用于派系权重合成（`weight × boost × sensitivity`），不再作用于阈值本身。这样 trigger 字面量即文档语义（如 `market_sentiment < -0.4` 就是 -0.4），避免 "threshold×0.8" 这类不可读写法。

### 4.1 A1 美联储 — dove / hawk / neutral

| 字段 | 设计 |
|------|------|
| 派系 | `dove_emergency` / `dove` / `neutral` / `hawk` |
| red_line_triggers | `"market_sentiment < -0.6"` → `CUT_50BP`（市场深度恐慌强制大幅降息） |
| **dove_emergency** | weight 0.30；trigger `"market_sentiment < -0.4 OR vix_stress > 0.6"`；bias_actions `["CUT_50BP", "CUT_25BP"]` |
| **dove** | weight 0.25；trigger `"market_sentiment < -0.25 OR vix_stress > 0.4"`；bias_actions `["CUT_25BP", "VERBAL_INTERVENTION"]` |
| **neutral** | weight 0.25；trigger `"grv_stress > 0.4 AND market_sentiment > -0.2"`；bias_actions `["VERBAL_INTERVENTION", "HOLD"]` |
| **hawk** | weight 0.20；trigger `"market_sentiment > 0.5 AND fed_rate_change < 0"`；bias_actions `["HIKE_25BP", "HOLD"]` |
| 对应旧规则 | 旧 5 条 if-else 全部覆盖（CUT_50BP/CUT_25BP/VERBAL/HIKE/HOLD），无行为缺口 |
| 论文锚点 | [T-1993]（0.5/0.5 反应系数）；[CGG-2000]（平滑化）；[O-2003]（实时数据稳健性） |
| 参数说明 | dove 两档总权重 0.55 > hawk 0.20，反映"市场压力响应优先于过热响应"的 Fed 实际不对称性；**文献无直接派系权重，区间待校准**（§5.5 P1） |

**新增能力**：`fed_rate_change` 参与 hawk trigger（加息只在已降息过的环境中触发——原代码 `fed_change < 0` 语义保留）。

### 4.2 A2 商业银行 — risk_off / risk_on

| 字段 | 设计 |
|------|------|
| 派系 | `risk_off` / `risk_on` / `neutral` |
| red_line_triggers | 无（银行无强制响应行动；挤兑由 A10 传导表达） |
| **risk_off** | weight 0.40；trigger `"credit_spread > 300 OR grv_stress > 0.4 OR vix_stress > 0.35 OR flag_hf_short OR flag_retail_panic"`；bias_actions `["TIGHTEN_CREDIT"]` |
| **risk_on** | weight 0.25；trigger `"credit_spread < 200 AND bank_credit_tightening < 0.15 AND grv_stress < 0.15"`；bias_actions `["EASE_CREDIT"]` |
| **neutral** | weight 0.35；无 trigger；bias_actions `["HOLD"]` |
| 对应旧规则 | 旧 `tighten_signal`（5 个 OR 条件）+ `ease_signal`（3 个 AND）全覆盖 |
| 论文锚点 | [BGG-1999]（外部融资溢价/资产负债表渠道）；[D-D-1983]（挤兑：retail_panic 收紧）；[BB-1988]（信贷渠道） |
| 参数说明 | `credit_spread > 300` 对应 BAA-10Y 历史高压（p85 约 300bp）；`credit_spread < 200` 对应正常态；**文献区间见 §5.4 R2** |

> `flag_hf_short` / `flag_retail_panic` 为管线注入的布尔 ctx 字段（来自 `visible_actions.hedge_fund == "SHORT_MARKET"` 等），见 §3.4 与 §7.2。

### 4.3 A3 对冲基金 — risk_off / risk_reduce / contrarian / risk_on / neutral

| 字段 | 设计 |
|------|------|
| 派系 | `risk_off` / `risk_reduce` / `contrarian` / `risk_on` / `neutral` |
| red_line_triggers | 无 |
| **risk_off**（高压做空） | weight 0.30；trigger `"grv_stress > 0.4 OR vix_stress > 0.3 OR flag_media_fear OR sp500_change < -0.10"`；bias_actions `["SHORT_MARKET", "DECREASE_RISK"]` |
| **risk_reduce**（中等降险） | weight 0.20；trigger `"external_pressure_shift > 0.25 OR yield_inverted == 1 OR sp500_change < -0.05"`；bias_actions `["DECREASE_RISK", "HOLD"]` |
| **contrarian**（超卖反弹） | weight 0.20；trigger `"grv_stress > 0.4 AND market_sentiment < -0.4"`；bias_actions `["INCREASE_RISK", "HOLD"]` |
| **risk_on** | weight 0.20；trigger `"grv_stress < 0.1 AND vix_stress < 0.1 AND market_sentiment > 0.1"`；bias_actions `["INCREASE_RISK"]` |
| **neutral** | weight 0.10；无 trigger；bias_actions `["HOLD"]` |
| 对应旧规则 | 全覆盖（四档：深度恐慌 HOLD / 趋势做空 sp500<-0.10 / 高压做空 / 中等降险 / 环境改善加仓）。**旧 `OVERSOLD_BOUNCE_PROB=0.45` 类常量 → 由 contrarian 派系权重承接**（概率参数化进 soul，不再硬编码类常量）；旧 `sentiment < -0.4 → HOLD`（已充分定价不追空）由 contrarian/neutral 在深恐慌时竞争表达 |
| 论文锚点 | [DT-1985]（过度反应/逆向交易）；[B-B-1988]；[S-2016]（VIX 驱动 risk-on/off） |
| 参数说明 | 旧代码 `sentiment < -0.4 → HOLD`（已充分定价不追空）语义由 contrarian 派系"不参与 risk_off"天然表达：deep 恐慌时 contrarian 与 risk_off 同时命中，抽样落在 contrarian 则加仓/观望，落在 risk_off 则做空 —— **正是旧 45% 抄底概率的结构化版** |

### 4.4 A5 机构投资者 — risk_off / neutral(避险再平衡) / risk_on

| 字段 | 设计 |
|------|------|
| 派系 | `risk_off` / `safe_haven` / `risk_on` / `neutral` |
| red_line_triggers | 无 |
| **risk_off** | weight 0.35；trigger `"sp500_change < -0.10 OR grv_stress > 0.45 OR vix_stress > 0.4 OR yield_inverted == 1"`；bias_actions `["DECREASE_RISK"]` |
| **safe_haven**（中性避险再平衡） | weight 0.20；trigger `"grv_stress > 0.45 OR vix_stress > 0.4"`；bias_actions `["HOLD"]` |
| **hf_follower** | weight 0.15；trigger `"flag_hf_short AND grv_stress > 0.25"`；bias_actions `["DECREASE_RISK"]` |
| **risk_on** | weight 0.15；trigger `"grv_stress < 0.1 AND vix_stress < 0.1"`；bias_actions `["INCREASE_RISK"]` |
| **neutral** | weight 0.15；无 trigger；bias_actions `["HOLD"]` |
| 对应旧规则 | 全覆盖。**旧 `SAFE_HAVEN_PROB=0.35` → safe_haven 派系权重承接** |
| 论文锚点 | [S-2016]（flight-to-quality）；[Barsky-1989]（避险资本流动）；[B-P-2009]（流动性螺旋） |
| 参数说明 | safe_haven 权重 0.20 ≈ 旧 35% 概率在"高压全命中"场景下的抽样占比（0.35+0.2+0.15=0.70 分母 → 0.2/0.7≈0.29，接近 35%）；**精确值待校准回归** |

### 4.5 A6 媒体 — fear / optimism / neutral / saturation

| 字段 | 设计 |
|------|------|
| 派系 | `fear` / `fear_from_actions` / `optimism` / `saturation` / `neutral` |
| red_line_triggers | 无 |
| **fear** | weight 0.35；trigger `"market_sentiment < -0.35 OR grv_stress > 0.5 OR social_stress > 0.5"`；bias_actions `["AMPLIFY_FEAR"]` |
| **fear_from_actions**（外部信号放大） | weight 0.20；trigger `"(flag_hf_short OR flag_retail_panic) AND market_sentiment < -0.2"`；bias_actions `["AMPLIFY_FEAR"]` |
| **optimism** | weight 0.20；trigger `"market_sentiment > 0.3 AND grv_stress < 0.1"`；bias_actions `["AMPLIFY_OPTIMISM"]` |
| **saturation**（防单向推到底） | weight 0.15；trigger `"market_sentiment < -0.5"`；bias_actions `["HOLD", "NEUTRAL_REPORT"]` |
| **neutral** | weight 0.10；trigger `"abs(market_sentiment) < 0.1"`；bias_actions `["NEUTRAL_REPORT"]` |
| 对应旧规则 | 全覆盖（含 `sentiment < -0.5 → HOLD` 饱和规则、hf_short/retail_panic 两个放大器分支） |
| 论文锚点 | [S-2019]（叙事经济学/SIR 传染）；[K-M-1927]（SIR 模型）；[BO-2008]（注意力驱动的买入行为） |
| 参数说明 | `social_stress > 0.5` 是 v3 新增信号来源（R09 社会压力，原代码已注入 media ctx，旧规则没用上）；saturation 派系保证深度恐慌时媒体不再放大 —— 保路径多样性 |

### 4.6 A7 新兴市场央行 — defensive / dovish / neutral

| 字段 | 设计 |
|------|------|
| 派系 | `defensive_controls` / `defensive_rates` / `dovish` / `neutral` |
| red_line_triggers | 无 |
| **defensive_controls** | weight 0.30；trigger `"em_capital_outflow > 0.5 OR (flag_fed_hike AND em_capital_outflow > 0.25)"`；bias_actions `["CAPITAL_CONTROLS"]` |
| **defensive_rates** | weight 0.25；trigger `"grv_stress > 0.35 AND vix_stress > 0.25"`；bias_actions `["RAISE_RATES"]` |
| **dovish** | weight 0.20；trigger `"flag_fed_cut AND em_capital_outflow < 0.1"`；bias_actions `["CUT_25BP"]` |
| **neutral** | weight 0.25；无 trigger；bias_actions `["HOLD"]` |
| 对应旧规则 | 全覆盖（资本管制/预防性加息/跟进降息三条） |
| 论文锚点 | [CR-2002]（fear of floating）；[C-1998]（sudden stop）；[O-R-1995]（汇率制度困境/三元悖论） |
| 参数说明 | `em_capital_outflow > 0.5` 为突然停滞压力阈值（0~1 量纲内 p85 经验，**待校准**）；`flag_fed_hike`/`flag_fed_cut` 为 visible_actions 注入布尔 |

### 4.7 A8 中国央行/财政 — stimulus / fx_defense / countercyclical / tight / neutral

| 字段 | 设计 |
|------|------|
| 派系 | `stimulus_rrr` / `stimulus_lpr` / `fx_defense` / `countercyclical` / `tight` / `neutral` |
| red_line_triggers | `"usd_cny > 7.5"` → `CNY_INTERVENTION`（汇率失控强制干预） |
| **stimulus_rrr** | weight 0.25；trigger `"china_credit_impulse < -0.3"`；bias_actions `["CUT_RRR"]` |
| **stimulus_lpr** ⭐复活死行动 | weight 0.15；trigger `"china_credit_impulse < -0.2 AND market_sentiment < -0.2"`；bias_actions `["CUT_LPR", "FISCAL_STIMULUS_CN"]` |
| **fx_defense** | weight 0.25；trigger `"usd_cny > 7.3 OR (us_china_grv > 0.4 AND flag_fed_hike)"`；bias_actions `["CNY_INTERVENTION"]` |
| **countercyclical** | weight 0.20；trigger `"grv_stress > 0.5 AND market_sentiment < -0.25"`；bias_actions `["FISCAL_STIMULUS_CN"]` |
| **tight** | weight 0.15；trigger `"china_credit_impulse > 0.4"`；bias_actions `["TIGHTEN_CN"]` |
| **neutral** | weight 0.10；无 trigger；bias_actions `["HOLD"]` |
| 对应旧规则 | 全覆盖 + **复活 CUT_LPR**（旧规则永不产出，gm_resolve 已有 delta 分支） |
| 论文锚点 | [CGG-2000]（新兴市场央行反应函数）；逆周期调节（LPR 定价改革文献）；[CR-2002]（汇率干预） |
| 参数说明 | `usd_cny > 7.3` 沿用旧代码阈值（干预点）；`china_credit_impulse < -0.3` 为信用脉冲收缩带（**待校准**） |

> **⭐ 死行动复活**：`CUT_LPR` 在 v3 由 `stimulus_lpr` 派系产出，gm_resolve 分支已存在（`china_credit_impulse +0.15`），无需新增引擎分支。`QE_TIGHTEN` 不同——需要新增 gm_resolve 分支，见 §7.3。

### 4.8 A9 美国财政部 — stimulus / crisis / tighten / neutral

| 字段 | 设计 |
|------|------|
| 派系 | `stimulus` / `crisis_debt` / `tighten` / `neutral` |
| red_line_triggers | 无 |
| **stimulus** | weight 0.30；trigger `"market_sentiment < -0.4 AND flag_fed_cut"`；bias_actions `["FISCAL_STIMULUS"]` |
| **crisis_debt** | weight 0.25；trigger `"us_fiscal_pressure > 0.6"`；bias_actions `["DEBT_CEILING_RISK"]` |
| **tighten** | weight 0.20；trigger `"market_sentiment > 0.45 AND us_fiscal_pressure < 0.15"`；bias_actions `["FISCAL_TIGHTEN"]` |
| **neutral** | weight 0.25；无 trigger；bias_actions `["HOLD"]` |
| 对应旧规则 | 全覆盖 |
| 论文锚点 | [AG-2012]（财政乘数，衰退期 > 扩张期）；[BL-2013]（紧缩乘数估计） |
| 参数说明 | `market_sentiment < -0.4 AND flag_fed_cut` = "危机配合美联储"（原代码 `sentiment < -(threshold*0.8) and fed_cut`）；乘数文献决定 stimulus 的 gm_resolve magnitude 调参方向 |

### 4.9 A10 散户 — panic / fomo / neutral

| 字段 | 设计 |
|------|------|
| 派系 | `panic` / `fomo` / `neutral` |
| red_line_triggers | 无 |
| **panic** | weight 0.40；trigger `"flag_media_fear OR (flag_hf_short AND market_sentiment < -0.15)"`；bias_actions `["PANIC_SELL"]` |
| **fomo** | weight 0.30；trigger `"flag_media_optimism AND market_sentiment > 0.2"`；bias_actions `["FOMO_BUY"]` |
| **neutral** | weight 0.30；无 trigger；bias_actions `["HOLD"]` |
| 对应旧规则 | 全覆盖 |
| 论文锚点 | [DT-1985]（过度反应）；[BO-2008]（注意力/新闻驱动买入）；[LSV-1992]（机构羊群，散户跟随）；[S-2019]（叙事传染到散户行为） |
| 参数说明 | `flag_media_fear` 单条件即 PANIC_SELL（媒体是散户第一驱动，与 transmission_coefficients to_A10=0.70 一致） |

### 4.10 A11 欧洲央行 — dove / hawk / qe（含 QE_TIGHTEN 复活）

| 字段 | 设计 |
|------|------|
| 派系 | `dove_cut` / `dove_rate_level` / `dove_qe` / `hawk` / `qe_tighten` / `neutral` |
| red_line_triggers | 无 |
| **dove_cut** | weight 0.25；trigger `"market_sentiment < -0.3 OR (flag_fed_cut AND grv_stress > 0.2)"`；bias_actions `["CUT_25BP"]` |
| **dove_rate_level** | weight 0.15；trigger `"ecb_rate > 3.5 AND grv_stress > 0.15 AND market_sentiment < 0"`；bias_actions `["CUT_25BP"]` |
| **dove_qe** | weight 0.20；trigger `"grv_stress > 0.5"`；bias_actions `["QE_EXPAND"]` |
| **hawk** | weight 0.15；trigger `"flag_fed_hike AND market_sentiment > 0"`；bias_actions `["HIKE_25BP"]` |
| **qe_tighten** ⭐复活死行动 | weight 0.15；trigger `"ecb_rate < 2.0 AND grv_stress < 0.1 AND market_sentiment > 0.3"`；bias_actions `["QE_TIGHTEN", "HOLD"]` |
| **neutral** | weight 0.10；无 trigger；bias_actions `["HOLD"]` |
| 对应旧规则 | 全覆盖 + 复活 QE_TIGHTEN（**需新增 gm_resolve 分支**，§7.3） |
| 论文锚点 | [ACM-2015]（APP 对收益率 30-50bp 影响，QE 传导）；[P-2018]（再投资 ~100bp 下压）；[BRS-2004]（零下界工具） |
| 参数说明 | `ecb_rate < 2.0 AND 低压力 AND 情绪转好` = "危机结束、政策回归常态、回收 QE"的场景——文献上 QE 退出有明确时滞与条件（[ACM-2015] 事件研究），此 trigger 为**行为设计推断，参数待校准** |

### 4.11 A12 日本央行 — extreme / easing / neutral

| 字段 | 设计 |
|------|------|
| 派系 | `extreme` / `easing_emergency` / `easing_ycc` / `neutral` |
| red_line_triggers | `"yen_carry_risk > 0.8"` → `ABANDON_YCC`（套息危机强制弃 YCC） |
| **extreme** | weight 0.30；trigger `"yen_carry_risk > 0.5 OR (flag_fed_hike AND yen_carry_risk > 0.3)"`；bias_actions `["ABANDON_YCC"]` |
| **easing_emergency** | weight 0.20；trigger `"vix_stress > 0.55"`；bias_actions `["EMERGENCY_EASE"]` |
| **easing_ycc** | weight 0.25；trigger `"grv_stress > 0.35 OR japan_monetary > 0.5"`；bias_actions `["EASE_YCC"]` |
| **neutral** | weight 0.25；无 trigger；bias_actions `["HOLD"]` |
| 对应旧规则 | 全覆盖 + 新增 `japan_monetary` 信号（D7 已注入 ctx，旧规则未用） |
| 论文锚点 | [BNP-2009]（carry trade 崩盘风险，VIX 高时资金货币急升）；[U-2007]（BOJ 2001-2006 QE 综述）；[S-2016]（VIX 与风险偏好） |
| 参数说明 | `yen_carry_risk > 0.8` 为 red_line（强制弃 YCC），`> 0.5` 为派系触发带；**阈值待校准**（历史 1998/2007/2024 三轮平仓的 VIX/利差读数可作参照系） |

### 4.12 S1-S5 说明（不重构，仅补中文映射）

S1-S5 已走 soul 管线，v3 不动其决策逻辑。仅补 `run.py::_ACTION_VERB` 的 S 类中文映射（§6.3）与天玑 trace 下沉（§6.5）。

---

## 5. 论文锚点体系

### 5.1 references 字段规范（soul YAML 内嵌）

每个 soul 文件顶层增加 `references` 字段；每个派系可选 `reference_ids` 标注其行为来源：

```yaml
references:
  - id: T-1993
    cite: "Taylor, J.B. (1993). Discretion versus Policy Rules in Practice. Carnegie-Rochester Conference Series on Public Policy, 39, 195-214."
    params:
      inflation_gap_coef: "0.5（原文）"
      output_gap_coef: "0.5（原文）"
    note: "0.5/0.5 为原文标定；合通胀系数 1.5 满足 Taylor 原理（>1 才稳）"
  - id: CGG-2000
    cite: "Clarida, R., Gali, J., Gertler, M. (2000). Monetary Policy Rules and Macroeconomic Stability: Evidence and Some Theory. QJE, 115(1), 147-180."
    params:
      interest_rate_smoothing: "0.79（美，样本内估计区间 0.5~0.95）"
```

**校验规则（新 Agent 准入）**：
1. 每个派系的每个 `trigger` 数值阈值必须能在其 `reference_ids` 或 soul `references` 中找到出处（参数区间或"待校准"标注）；
2. 无文献参数的阈值必须在 `references.note` 或参数表里显式标 `【待校准】`；
3. 违反以上任一条 → soul schema 校验失败（可进 DORMANT 池，不可进 ACTIVE）。

### 5.2 文献清单（本次联网调研核实，真实文献）

| ID | 文献 | 用途（锚定哪些 soul） | 可提取参数 |
|----|------|---------------------|-----------|
| T-1993 | Taylor (1993), *Discretion versus Policy Rules in Practice*, Carnegie-Rochester Conf. 39 | A1 利率反应 | 通胀缺口系数 0.5；产出缺口系数 0.5；r\*=2%、π\*=2% |
| CGG-2000 | Clarida, Gali & Gertler (2000), *Monetary Policy Rules and Macroeconomic Stability*, QJE 115(1) | A1/A7 前瞻性反应、利率平滑 | 平滑系数估计 ~0.79（美） |
| O-2003 | Orphanides (2003), *Historical Monetary Policy Analysis and the Taylor Rule*, JME | A1 实时数据稳健性（警示系数会被高估） | 实时 vs 事后估计差可达 0.5+（警示） |
| BGG-1999 | Bernanke, Gertler & Gilchrist (1999), *The Financial Accelerator in a Quantitative Business Cycle Framework*, Handbook of Macroeconomics | A2/A3/A5 信贷与外部融资溢价 | EFP 与借款人净值负相关；放大冲击 |
| GOZ-2009 | Gilchrist, Ortiz & Zakrajšek (2009), *Credit Risk and the Macroeconomy*, FRB/JMCB | A2 信贷收紧的宏观放大 | 信用利差代理 EFP，估计中"显著且持久" |
| BB-1988 | Bernanke & Blinder (1988), *Credit, Money, and Aggregate Demand*, AER 78 | A2 银行信贷渠道 | 信贷渠道存在性 |
| DD-1983 | Diamond & Dybvig (1983), *Bank Runs, Deposit Insurance, and Liquidity*, JPE 91 | A2 挤兑（retail_panic → 收紧） | 多重均衡，恐慌自实现 |
| S-2016 | Smales (2016), *Risk-on/Risk-off: Financial Market Response to Investor Fear*, Research in Int'l Business & Finance | A3/A5 flight-to-quality；A12 | VIX↑ → 股市↓/债市↓/高息货币贬、美元升；危机期敏感度 +85% |
| Barsky-1989 | Barsky (1989), *Why Don't the Prices of Stocks and Bonds Move Together?*, AER 79 | A5 避险资本流动 | 恐惧期资本从风险资产→安全资产 |
| BP-2009 | Brunnermeier & Pedersen (2009), *Market Liquidity and Funding Liquidity*, RFS 22 | A3/A5 流动性螺旋 | 保证金螺旋/价格螺旋 |
| S-2019 | Shiller (2019), *Narrative Economics*, Princeton UP | A6 媒体；A10 散户 | 叙事传染；SIR 动力学 |
| KM-1927 | Kermack & McKendrick (1927), *A Contribution to the Mathematical Theory of Epidemics* | A6 媒体放大建模 | SIR；Shiller 演讲示例 c=0.28/r=0.14 |
| BO-2008 | Barber & Odean (2008), *All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors*, RFS 21 | A10 散户 FOMO；A6 | 注意力驱动的买入，散户追涨 |
| DT-1985 | De Bondt & Thaler (1985), *Does the Stock Market Overreact?*, JF 40 | A3 contrarian；A10 羊群 | 输家组合 36 个月超额 ~24.6%；过度反应 |
| LSV-1992 | Lakonishok, Shleifer & Vishny (1992), *The Impact of Institutional Trading on Stock Prices*, JFE 32 | A10 羊群跟随 | 机构羊群的存在性证据 |
| CR-2002 | Calvo & Reinhart (2002), *Fear of Floating*, QJE 117(2) | A7/A8 汇率干预 | 自认浮动国 ~76% 实际干预；月度汇率变化 ±2.5% 带内概率 EM 77.4% vs US 58.7% |
| C-1998 | Calvo (1998), *Capital Flows and Capital-Market Crises: The Simple Economics of Sudden Stops*, J. Applied Econ. | A7 sudden stop | 突然停滞由资本账户崩溃触发 |
| OR-1995 | Obstfeld & Rogoff (1995), *The Mirage of Fixed Exchange Rates*, JEP 9 | A7/A8 三元悖论 | 汇率制度困境 |
| BNP-2009 | Brunnermeier, Nagel & Pedersen (2009), *Carry Trades and Currency Crashes*, NBER Macro Annual | A12 套息平仓 | 高息货币负偏；VIX 上升 → 资金货币（日元）急升；1998 年一周 +17% |
| U-2007 | Ugai (2007), *Effects of the Quantitative Easing Policy: A Survey of Empirical Analyses*, Monetary & Econ. Studies | A12 BOJ QE | 2001-2006 QE 有效性综述 |
| ACM-2015 | Altavilla, Carboni & Motto (2015), *Asset Purchase Programmes and Financial Markets*, ECB WP 1864 | A11 QE | 10Y 收益率 -30~-50bp；意大利/西班牙约翻倍 |
| P-2018 | Praet (2018), *Assessment of Quantitative Easing*, ECB 演讲 | A11 QE 存量影响 | APP 存量下压长端 ~100bp（含再投资预期） |
| BRS-2004 | Bernanke, Reinhart & Sack (2004), *Monetary Policy Alternatives at the Zero Bound*, Brookings | A11/A12 非常规工具 | 零下界三类工具（前瞻指引/QE/组合调整） |
| AG-2012 | Auerbach & Gorodnichenko (2012), *Measuring the Output Responses to Fiscal Policy*, AEJ:EP 4(2) | A9 财政刺激幅度 | 扩张期乘数 0.57 vs 衰退期 2.45（状态依赖） |
| BL-2013 | Blanchard & Leigh (2013), *Growth Forecast Errors and Fiscal Multipliers*, AER P&P 103 | A9 财政收紧 | 紧缩乘数 >1（零下界附近） |
| A-1971 | Allison (1971), *Essence of Decision*, Little Brown | S 类主权 soul 框架 | 派系决策结构（Model III 政府政治） |
| Kahn-1965 | Kahn (1965), *On Escalation: Metaphors and Scenarios* | S 类冲突升级 | 升级阶梯（13 级） |
| Schelling-1966 | Schelling (1966), *Arms and Influence*, Yale UP | S 类威慑/边缘政策 | 威胁可信度；升级作为信号 |
| DFR-2010 | Dosi, Fagiolo & Roventini (2010), *Schumpeter Meeting Keynes*, JEDC 34 | 整体 ABM 方法论 | 内生波动；复现 14 个 OECD 周期特征 |

**调研说明**：以上 29 条为本次 WebSearch 核实的真实文献（作者/年份/期刊/可提取参数均已从权威来源验证，如 Fed Reserve 文档、REPEC、ECB WP、原论文 PDF）。其中 25 条用于 12 金融 soul 行为锚定，3 条（A-1971/Kahn/Schelling）支撑 S 类主权框架（现状已落地），1 条（DFR-2010）支撑整体 ABM 方法论。

### 5.3 参数区间表（文献 → soul 参数映射）

> 用法：`来源` 列 = 文献 ID（§5.2）；`取值依据` 列区分「原文/文献区间」vs「设计推断待校准」。

| 参数 | 本 soul 值 | 文献来源 | 文献区间/依据 |
|------|-----------|---------|--------------|
| A1 通胀缺口反应系数 | 0.5 | T-1993 | 原文 0.5；Taylor 原理要求合系数 >1（1+0.5=1.5 满足） |
| A1 产出缺口反应系数 | 0.5 | T-1993 | 原文 0.5 |
| A1 利率平滑（dove 降息惯性） | 隐含 | CGG-2000 | 估计 0.79；区间 0.5~0.95 → 校准上限参考 |
| A1 反应系数稳健下限 | — | O-2003 | 实时数据下系数可能被高估，校准取中值 |
| A2 收紧触发 `credit_spread > 300bp` | 300 | GOZ-2009 | 利差>300bp ≈ 信用周期高压力段（BAA-10Y p85） |
| A2 放松触发 `credit_spread < 200bp` | 200 | BB-1988 | 正常利差基准 ~150-200bp |
| A2 挤兑传导 `flag_retail_panic → TIGHTEN` | 布尔 | DD-1983 | 恐慌自实现（多重均衡） |
| A3 过度反应反转窗口 | 36 个月 | DT-1985 | 输家组合 3 年反转超额 ~24.6%；月频模型映射到 contrarian 派系 |
| A3 contrarian 权重 | 0.20 | DT-1985（定性） | 文献无权重，**【待校准】** |
| A3 VIX 驱动 risk-off | vix_stress>0.3（VIX>27） | S-2016 | 危机期市场对 VIX 敏感度 +85%；VIX 阈值见 S-2016/实践 20/30 带 |
| A5 flight-to-quality 触发 `vix_stress>0.4`（VIX>30） | 0.4 | S-2016 / Barsky-1989 | VIX>30 危机带（实践经验，非原文精确值，**【待校准】**） |
| A6 媒体放大触发 `social_stress>0.5` | 0.5 | S-2019 / KM-1927 | 社会压力为叙事传染输入；传染率/恢复率比值决定放大与否（c/r 示例 0.28/0.14） |
| A6 饱和阈值 `market_sentiment<-0.5` | -0.5 | S-2019 | 叙事饱和=易感人群枯竭（S→0，传染自然衰减） |
| A7 突然停滞触发 `em_capital_outflow>0.5` | 0.5 | C-1998 | 突然停滞定义=资本流入骤停；0.5 为 0~1 量纲 p85 经验，**【待校准】** |
| A7/A8 汇率干预阈值 | usd_cny>7.3 | CR-2002 | fear of floating：干预比声明的浮动更普遍（~76% 自认浮动国实际干预）；具体点位为设计值，**【待校准】** |
| A11 QE 收益率影响量级 | gm 分支 0.10 | ACM-2015 | 10Y -30~-50bp / 高风险国 -80bp；映射到 market_sentiment/bank_credit_tightening 的 magnitude 校准基准 |
| A11 QE 存量效应 | gm 分支 | P-2018 | 含再投资预期下压 ~100bp → 支持 QE_EXPAND 显著降 bank_credit_tightening |
| A12 套息平仓触发 `yen_carry_risk>0.5` | 0.5 | BNP-2009 | 1998 年日元一周 +17%；VIX 高时平仓加速；0.5 阈值 **【待校准】** |
| A9 财政乘数状态依赖 | 扩张 0.57 / 衰退 2.45 | AG-2012 | 衰退期财政刺激乘数是扩张期 4 倍 → stimulus 派系 magnitude 建议 > tighten |
| 派系 boost | 1.3 | 无直接文献 | Allison-1971 派系博弈定性支持；1.3 为 v2.2 验证值，**【待校准区间 1.1~1.8】** |
| 派系权重 | 各 soul | 无直接文献 | 由校准 LLM 拟合；当前值为设计初始值，**【全部待校准】** |

### 5.4 标注策略

- **`原文/文献区间`** = 参数可直接引用文献数值（如 0.5/0.5、30-50bp、76%），评审/审计时可溯源；
- **`【待校准】`** = 无文献直接给出，为行为设计推断，须在 v3 阶段 2/3 校准回归中重新拟合，拟合后回填区间。

---

## 6. 结果层 v3

### 6.1 决策 trace 落盘

**格式**：JSONL，每激活 Agent 每步一条；文件 `output/trace/{sim_id}/{run_id}.jsonl`（预测 run 全量落盘；校准期可只落盘抽样或汇总）。

```json
{
  "sim_id": "mc_42",
  "run_id": "mc_42",
  "cycle": 7,
  "month": "2026-03",
  "agent_id": "A3",
  "agent_role": "hedge_fund",
  "action": "SHORT_MARKET",
  "reason": "risk_off 派系命中：grv_stress=0.52>0.4 且 sp500_change=-0.08<-0.05",
  "source": "soul",
  "faction": "risk_off",
  "confidence": 0.58,
  "alternative": "DECREASE_RISK",
  "evidence": {
    "signals": {"grv_stress": 0.52, "vix_stress": 0.31, "sp500_change": -0.08, "market_sentiment": -0.22},
    "trigger_hit": "grv_stress > 0.4",
    "faction_weights": {"risk_off": 0.455, "contrarian": 0.2, "risk_on": 0.25, "neutral": 0.2},
    "bias_actions": ["SHORT_MARKET", "DECREASE_RISK"]
  },
  "params": {"sensitivity": 1.0, "threshold": 0.5, "magnitude": 1.0},
  "world_subset": {"grv": 76.0, "market_sentiment": -0.22, "vix": 31.2, "credit_spread": 285.0}
}
```

**保留策略**：每条路径（=一个 run）全量落盘；100 runs × 24 步 × ≤17 Agent ≈ 最多 4 万条/次仿真（每条约 0.8KB → ~32MB），可接受。报告/叙事只消费**代表 run**（各路径中心 run）的 trace，全量 trace 留作审计/离线分析。

### 6.2 报告 v3 结构（`run.py::_write_report` 升级）

```
一、核心结论            （保持 v2）
二、路径详情            （保持 v2 + 新增"关键决策理由表"）
   每路径下新增：
   ### 路径X — 关键决策理由表
   | 月 | Agent | 行动 | 理由（reason） | 关键信号值 | confidence |
   （取该路径每步置信度/影响最大的 1-2 条决策，最多 20 行）
三、月度演化进度条      （保持 v2，原因列改为 trace 驱动，不再用静态表）
四、逐月过程叙事        （新增，LLM 生成，§6.4）
五、校准说明            （保持 v2）
```

### 6.3 `_ACTION_VERB` S 类中文映射补全

`run.py::_ACTION_VERB` 现只覆盖 A1-A12。v3 补：

```python
"S1:IMPOSE_SANCTIONS": "实施制裁",   "S1:LIFT_SANCTIONS": "解除制裁",
"S1:MILITARY_DEPLOYMENT": "军事部署", "S1:DIPLOMATIC_ENGAGE": "外交接触",
"S1:TECH_RESTRICTION": "技术管制",    "S1:ALLIANCE_REINFORCE": "强化同盟",
"S4:NUCLEAR_SIGNAL": "核威慑信号",    "S4:ENERGY_CUTOFF": "能源断供",
"S4:CEASEFIRE_SIGNAL": "停火信号",    "S5:CUT_OUTPUT": "减产",
"S5:INCREASE_OUTPUT": "增产",        "S5:EMBARGO_SIGNAL": "禁运信号",
"S5:DIPLOMATIC_OUTREACH": "外交外联",
```

（S 类通用行动可按 actor_id 通配注册，避免逐个 S1-S5 重复。）

### 6.4 LLM 逐月过程叙事（需求②）

**输入**：代表 run 的 trace 全量（24 步 × 激活 Agent），按路径抽取。

**Prompt 设计要点**：

1. **事实约束**：所有数字必须来自 trace（evidence.signals / world_subset），LLM 不得编造信号值；叙事文本里数字若出现必须在 trace 中存在。
2. **结构强制**：输出分 4 段——【触发】第 1-3 个月谁先动、为什么 →【传导】逐月连锁（引用 agent/action/reason）→【拐点】路径分叉步的决策分歧 →【稳态】末 3 个月格局。
3. **因果只引用 trace 内**：传导链描述必须形如"对冲基金做空（grv_stress 0.52）→ 媒体放大恐慌（A6 fear 命中）→ 散户 PANIC_SELL"，禁止外推 trace 之外的因果。
4. **长度**：每路径 400-600 字；多路径间不得复读相同措辞。
5. **反幻觉校验**：生成后脚本级校验——抽取叙事中的关键数值，与 trace 比对，不一致则标注「叙事数字存疑」并回退到结构化表述。

**输出结构**：

```
### 路径B（23%）— 先升后降 — 逐月过程叙事

【触发】M1-M3：...
【传导】M4-M12：...
【拐点】M13：A3 contrarian 派系首次命中（market_sentiment=-0.41），...
【稳态】M22-M24：...
```

### 6.5 天玑 reasoning_trace 升级（需求①的纵向贯通）

现状：`_archive_to_tianji` 写 `reasoning_trace` 时 `agent_id="macro-sim"`，input_signals 只含 grv/credit_spread/t10y2y 三个汇总信号。

v3 变更：
1. `agent_id` 下沉为**具体 Agent**（如 `"A3"`），每条预测关联该路径 key_events 里主要驱动 Agent 的决策 trace；
2. `input_signals` 填充该 Agent evidence.signals（如 `grv_stress/vix_stress/sp500_change`）；
3. `causal_chains` 用 trace 的 reason/faction 构造（如 `nodes=["risk_off 派系命中", "SHORT_MARKET", "GRV上升"]`），`confidence_basis` 记 `confidence`；
4. 兼容：`agent_id="macro-sim"` 的旧汇总行保留（时间窗口预测），新增 Agent 级行。

---

## 7. 校验闭环

### 7.1 三角核对（死行动检测，需求③④）

对每个 VALID_ACTIONS 行动，三角核对三张表：

| 维度 | 来源 | 核对内容 |
|------|------|---------|
| 规则产出 | trace（或 soul 派系 bias_actions 遍历） | 该行动在 N 步内是否被任何派系/规则产出 |
| 行动空间 | `VALID_ACTIONS` | 行动是否声明合法 |
| 世界状态 | gm_resolve 分支 | 行动是否有 delta 分支（否则产出了也不生效） |

**检测规则**：三个条件缺一 → 告警/阻断：

```
行动 ∈ VALID_ACTIONS
  ∧ (存在派系 bias_actions 可产出 ∨ 历史 N 步产出率 > 0)
  ∧ (gm_resolve 有 delta 分支 ∨ 纯叙事行动白名单)
```

**首个用例**（迁移前基线统计，迁移后复核）：
- A11 `QE_TIGHTEN`：缺规则产出 + 缺 gm_resolve 分支 → 双缺口；
- A8 `CUT_LPR`：缺规则产出（gm_resolve 已有）→ 单缺口。

v3 落地后：`QE_TIGHTEN` 由 §4.10 `qe_tighten` 派系产出 + 新增 gm_resolve 分支（§7.3）；`CUT_LPR` 由 §4.7 `stimulus_lpr` 派系产出。

### 7.2 consistency_validator 升级（用 trace evidence）

现状 Layer 1 只做 `(agent_id_A, action_A) ↔ (agent_id_B, action_B)` 字符串匹配。v3 增强：

1. **决策级矛盾**：当 `(A1, HIKE_25BP) ↔ (A2, EASE_CREDIT)` 命中时，附带各自 trace 的 reason/evidence 进告警（Layer 2 LLM 可直接看到"为什么"）；
2. **信号值矛盾**：同一步内两个 Agent 引用相同信号但方向相反的行动（如 A6 AMPLIFY_FEAR 与 A10 FOMO_BUY 都引用 `market_sentiment` 且同一阈值带）→ 新增规则类 `SIGNAL_CONTRADICTION`；
3. **派系一致性**：S 类 red_line 已触发却产出缓和行动 → 校验失败（防 red_line 被 bias_actions 绕行）；
4. Layer 2 LLM prompt 注入决策理由，判断更准（现在只能看行动对）。

### 7.3 QE_TIGHTEN 复活所需的 gm_resolve 新增分支

```python
# gm_resolve_rules() 新增（A11 QE_TIGHTEN，暂定传导系数，待校准）
elif a11 == "QE_TIGHTEN":
    m = mag("A11")
    add("A11", "bank_credit_tightening",  0.05 * m)   # 回收流动性 → 信贷边际收紧
    add("A11", "market_sentiment",       -0.04 * m)   # 政策边际转鹰
    add("A11", "liquidity_premium",       0.03 * m)
```

**注意**：这是本次重构中唯一触碰仿真引擎 `gm_resolve` 的行为变更，会影响校准基线 → 须在阶段 3 独立跑一次校准回归，确认评分不劣化（§9 验收）。

### 7.4 校验范围与 fail-loud 原则

- 死行动检测、派系与 VALID_ACTIONS 不一致、trigger 引用未知 ctx 变量 → 启动时 fail-loud（参照 `calibrator.py::_self_check` 的 ADR-0011 自检模式），不允许静默降级；
- MC 阶段不启用 LLM 校验（保持性能），决策级矛盾只标记不丢 run（沿用 v2 原则）。

---

## 8. 迁移策略与风险

### 8.1 三阶段迁移（延续用户骨架）

| 阶段 | 内容 | 交付物 | 验收门槛 |
|------|------|--------|---------|
| **阶段 1**：统一框架 | base.py 新增 ActionDecision + soul 管线 `decide()→ActionDecision`；现有 `_decide_rules` 包一层 fallback；trace 落盘骨架 | 决策管线 v0、ActionDecision schema、trace JSONL 空实现 | 回归测试：**无 soul 时每个 Agent 输出与 v2 逐行动一致**（`decide()` 返回 action 字符串不变的兼容层） |
| **阶段 2**：试点 3 个 soul | A1 Fed、A3 对冲基金、A6 媒体（行为最核心、覆盖 dove/hawk、risk-off/on、fear/optimism 三类结构） | 3 个 soul YAML + 派系触发/权重 + 校准扩展（权重纳入 LLM 调参空间） | 试点 Agent 校准评分 ≥ v2 同 Agent 评分 × 0.95；死行动检测跑通；trace 理由可读 |
| **阶段 3**：剩余 9 个 + 死行动清理 | A2/A5/A7/A8/A9/A10/A11/A12 全部 soul 化；QE_TIGHTEN 复活 + gm_resolve 新分支；CUT_LPR 复活 | 12 个金融 soul 全量、gm_resolve 变更 | 全量校准评分回归对比；死行动双清零；`_ACTION_VERB` S 类补全 |

### 8.2 关键风险与缓解

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| R1 | **soul 概率化 vs if-else 确定性**：派系加权抽样引入随机性，单 run 可复现性下降；校准评分可能短期劣化 | 校准需重新拟合；回归测试脆弱 | ①阶段 2 以"校准评分回归对比"为硬门槛；②抽样增加 seed 注入（run_id 驱动），同一 run 可复现；③评分劣化 >10% 时回退该 Agent 到 fallback 模式（渐进迁移的保险丝） |
| R2 | **派系权重/boost 无文献直接支撑**：30 条文献只覆盖触发阈值方向，权重是设计推断 | 权重可能偏离真实行为分布 | 权重全标【待校准】；校准 LLM 的调参空间扩展为 `weight/boost/trigger阈值`；校准日志留档回填 §5.3 区间 |
| R3 | **QE_TIGHTEN gm_resolve 新分支触碰引擎**：影响传导矩阵与校准基线 | 全量评分漂移 | 独立分支 + 独立校准回归；若劣化明显则 QE_TIGHTEN 的 delta 系数从 0.5× 起始逐步上调 |
| R4 | **LLM 逐月叙事幻觉**：叙事可能编造 trace 外的数字/因果 | 报告可信度受损（违反需求①） | §6.4 反幻觉校验（数值比对 + 标记回退）；叙事 prompt 强制"只引用 trace 内信号" |
| R5 | **_eval_trigger 语法扩展**：`visible_actions` 字符串条件不在现有 eval 支持范围 | trigger 无法直接表达"看到对冲基金做空" | 用管线注入布尔 ctx（`flag_hf_short`/`flag_media_fear`/`flag_fed_cut` 等），trigger 只写 `flag_hf_short == 1`——零语法扩展，最小改动（§3.4） |
| R6 | 校准缓存（7 天）掩盖新行为：v3 上线后旧缓存带旧参数跑 | 误判 v3 效果 | 上线时按版本号失效 calibration_cache（cache key 加 `soul_version`） |
| R7 | 12 个 soul YAML 维护量与校准维度爆炸 | 后期维护成本 | soul schema 校验（§5.1）+ 默认值完备（缺字段用中性值）+ 校准只调"差异显著"参数 |

### 8.3 上线顺序建议

阶段 1（框架）→ 阶段 2（试点）→ **同时**推进结果层 v3（trace 落盘已就绪，报告/叙事依赖 trace）→ 阶段 3（全量 + 死行动）。结果层与阶段 2 并行，因为 trace 是叙事的前提，而叙事是验收的一部分。

---

## 9. 工作量估计与验收标准

### 9.1 工作量估计（人日，含测试与文档）

| 工作项 | 人日 | 依赖 |
|--------|------|------|
| 阶段 1：ActionDecision + soul 管线 + fallback 兼容层 + 回归测试 | 3 | — |
| 阶段 2：A1/A3/A6 三个 soul YAML + 校准扩展 | 3 | 阶段 1 |
| 结果层：trace 落盘 + 报告 v3 + 叙事 prompt + 反幻觉校验 | 4 | 阶段 1 |
| 阶段 3：剩余 9 个 soul + QE_TIGHTEN/CUT_LPR 复活 + gm_resolve 分支 | 5 | 阶段 2 |
| 校验闭环：死行动检测 + validator 升级 + 天玑 trace 下沉 | 2.5 | 阶段 1/2 |
| 校准回归与调参（含 R1 兜底回退） | 2.5 | 阶段 3 |
| **合计** | **≈ 20 人日** | |

### 9.2 验收标准（可量化）

1. **决策可校验**：预测 run 中 100% 激活 Agent 决策含 `reason + evidence`（evidence 含 signals/trigger_hit/faction_weights/alternative）；trace 文件可被脚本解析且字段完整。
2. **行为兼容**：无 soul 模式下，`decide()` 返回行动与 v2 逐行动一致（阶段 1 回归套件全绿）。
3. **校准回归**：阶段 3 全量校准评分 ≥ v2 评分，或平均误差劣化 <10%；若 >10% 触发 R1 回退机制并书面说明。
4. **死行动清零**：`QE_TIGHTEN`、`CUT_LPR` 在 24 步预测内产出率 > 0；死行动检测脚本零告警。
5. **过程叙事**：每条路径报告含 400-600 字逐月叙事，且叙事中所有数字可回溯到 trace（反幻觉校验通过率 100%）。
6. **论文锚点**：12 个金融 soul 的每个派系 trigger 阈值都有 §5.3 参数表出处或【待校准】标注；soul schema 校验通过。
7. **S 类中文映射**：`_ACTION_VERB` 覆盖 S1-S5 全部行动。

---

## 10. 变更记录

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-08-07 | v1.0 初稿：统一决策框架、12 金融 soul 设计表、论文锚点体系（30 条文献）、结果层 v3、校验闭环、三阶段迁移 | 用户需求①②③④ + 代码盘点 + 联网文献调研 |
| 待定 | （阶段实施后回填） | — |

---

## 附录 A：实施时先读的文件清单

| 文件 | 作用 |
|------|------|
| `core/agents/base.py` | MacroAgent 基类、AgentParams、AgentOutput —— 阶段 1 主要改动点 |
| `core/agents/sovereign.py` | soul 管线参考实现（_decide_rules / _eval_trigger / _faction_to_action） |
| `core/agents/financial.py` / `social.py` / `geopolitical.py` | 12 个 if-else 规则 —— 阶段 2/3 替换为 soul |
| `core/world_state.py::get_agent_context` | ctx 字段权威清单（soul trigger 变量名以此为准） |
| `core/simulation.py::gm_resolve_rules` | delta 分支权威清单 + QE_TIGHTEN 新增点 |
| `core/calibrator.py` | 校准循环（权重纳入调参空间的改动点） |
| `run.py::_write_report` / `_archive_to_tianji` | 报告 v3 + S 类映射 + 天玑 trace 下沉 |
| `core/consistency_validator.py` | 决策级校验升级 |
| `config/agents.yaml` | 12 金融 Agent 的 `soul_file` 字段挂接点 |
