# 宏观传导仿真系统设计草案 v0.3

> 基于 v0.2 用户决策（Q1/Q2/Q3）更新
> Q1：传导模拟器（外生变量不完全冻结，内生压力可反向推动VIX）
> Q2：LLM开关（use_llm参数，长期保留）
> Q3：可验证性占位符写入P0

---

## 关键设计决策总表

| 决策点 | v0.1 | v0.2 | v0.3（最终） | 原因 |
|--------|------|------|------------|------|
| 系统定位 | 传导仿真 | 受控实验室 | **传导模拟器** | 用户选择；需加出血规则联动外生变量 |
| 调度器 | Mesa StagedActivation | 手动四阶段 | **手动四阶段** | Mesa 2.2+移除了该API |
| LLM角色 | 核心功能 | 只读后处理 | **带开关的可选功能** | P1关闭调试，P2开启；长期保留开关 |
| 首要价值 | 单次叙事 | Monte Carlo分布 | **Monte Carlo分布** | 方差=脆弱度指标，ABM不可替代价值 |
| GM规则 | 4条单向 | 8-10条含反馈 | **8-10条+出血规则** | 传导模拟器需要外生↔内生双向联动 |
| sentiment更新 | 硬截断 | 对数阻尼 | **对数阻尼** | 防止2-3步触底后仿真作废 |
| 可验证性 | 无 | 无 | **P0写入占位符** | 格式锁定，长期积累校准数据 |
| 工期 | 3.5天 | 5-5.5天 | **5.5-6天** | 出血规则+LLM开关额外+0.5天 |

---

## 一、系统定位

**传导模拟器**：外生变量（VIX/GRV）不完全冻结，内生压力积累到阈值后会反向推动外生变量，形成完整的传导闭环。

**传导链示意**：
```
GRV上升（外生输入）
    → energy_supply_risk 内生上升（GM规则）
    → 对冲基金做空（Agent决策）
    → market_sentiment 下降（内生）
    → 触发出血规则：sentiment < -0.5 持续3步
    → vix 按参数化步长上调（外生变量解冻）
    → A3/A5 下一步感知到 vix_shift 上升
    → 进一步做空，形成正反馈
```

每次仿真报告头部声明：
> 本次仿真以 T0 快照为初始条件，外生变量在内生压力积累超过阈值后动态更新，模拟宏观传导完整闭环。

---

## 二、MacroWorldState（v0.3）

```python
@dataclass
class MacroWorldState:
    # === 外生变量（T0快照，可通过出血规则动态更新）===
    vix: float
    vix_baseline: float           # T0基准，不随仿真改变
    grv: float
    grv_baseline: float
    grv_energy: float
    grv_energy_baseline: float
    grv_military: float
    grv_trade: float
    t10y2y: float
    credit_spread: float
    dff: float
    situation_level: int

    # === 内生变量（Agent决策→GM规则→精确更新）===
    fed_rate_change: float = 0.0
    bank_credit_tightening: float = 0.0
    fund_risk_appetite: float = 0.0
    market_sentiment: float = 0.0
    energy_supply_risk: float = 0.0
    liquidity_premium: float = 0.0
    em_capital_outflow: float = 0.0
    consecutive_negative_steps: int = 0

    # === 仿真元数据 ===
    cycle: int = 0
    total_cycles: int = 20
    trigger_event: str = ""
    recent_news: list = field(default_factory=list)
    sim_id: str = ""

    def get_agent_context(self, agent_role: str) -> dict:
        """Agent读取的是相对T0的delta，而非绝对值——防止VIX平静但sentiment崩溃的语义矛盾"""
        vix_shift = (self.vix - self.vix_baseline) / max(self.vix_baseline, 1)
        grv_shift = (self.grv - self.grv_baseline) / 100.0
        energy_shift = (self.grv_energy - self.grv_energy_baseline) / 100.0

        base = {
            "external_pressure_shift": round((vix_shift + grv_shift) / 2, 3),
            "internal_stress": round(
                self.market_sentiment * -0.5 + self.bank_credit_tightening * 0.5, 3
            ),
            "liquidity_tension": round(self.liquidity_premium, 3),
        }
        # 信息不对称：不同角色看到不同字段
        if agent_role in ("hedge_fund", "institution"):
            base["vix_shift"] = round(vix_shift, 3)
            base["t10y2y"] = self.t10y2y
            base["fund_risk_appetite"] = self.fund_risk_appetite
        if agent_role == "central_bank":
            base["fed_rate_change"] = self.fed_rate_change
            base["credit_spread"] = self.credit_spread
            base["dff"] = self.dff
        if agent_role == "commercial_bank":
            base["credit_spread"] = self.credit_spread
            base["bank_credit_tightening"] = self.bank_credit_tightening
        if agent_role == "energy_gov":
            base["energy_tension"] = round(energy_shift + self.energy_supply_risk, 3)
        if agent_role == "media":
            base["market_sentiment"] = self.market_sentiment
            base["recent_news"] = self.recent_news[:3]
        if agent_role == "em_central_bank":
            base["em_capital_outflow"] = self.em_capital_outflow
            base["dff_shift"] = self.fed_rate_change / 100.0
        return base
```

---

## 三、出血规则（传导模拟器的核心新增）

出血规则让内生压力"溢出"回外生变量，完成传导闭环。
**参数化设计**，便于校准：

```python
# 出血规则参数（可调，初始值保守）
BLEED_PARAMS = {
    "vix_bleed_threshold": -0.5,      # sentiment低于此值触发VIX上升
    "vix_bleed_steps": 3,             # 持续几步才触发
    "vix_bleed_rate": 2.0,            # 每步VIX上升幅度
    "vix_bleed_max": 15.0,            # 单次仿真VIX最大上升幅度（防止失控）
    "grv_bleed_threshold": 0.6,       # energy_supply_risk高于此值触发GRV能源维度上升
    "grv_bleed_rate": 3.0,            # 每步GRV能源维度上升幅度
    "credit_spread_bleed_rate": 5.0,  # bank_credit_tightening>0.5时信用利差每步扩大bps
}

def apply_bleed_rules(world: MacroWorldState, params: dict = BLEED_PARAMS):
    """内生压力积累超过阈值后反向更新外生变量"""
    vix_delta_total = world.vix - world.vix_baseline

    # 出血1：情绪崩溃→VIX上升
    if (world.market_sentiment < params["vix_bleed_threshold"]
            and world.consecutive_negative_steps >= params["vix_bleed_steps"]
            and vix_delta_total < params["vix_bleed_max"]):
        world.vix += params["vix_bleed_rate"]

    # 出血2：能源供给风险→GRV能源维度上升
    if world.energy_supply_risk > params["grv_bleed_threshold"]:
        world.grv_energy = min(100.0, world.grv_energy + params["grv_bleed_rate"])
        # GRV综合也跟着小幅上升
        world.grv = min(100.0, world.grv + params["grv_bleed_rate"] * 0.3)

    # 出血3：信贷收紧→信用利差扩大
    if world.bank_credit_tightening > 0.5:
        world.credit_spread += params["credit_spread_bleed_rate"]

    # 出血4：资本外流→收益率曲线变平（新兴市场抛售美债）
    if world.em_capital_outflow > 0.4:
        world.t10y2y -= 5.0  # 收益率曲线进一步倒挂
```

**为什么参数化很重要**：
- 初期保守设置，避免仿真失控（VIX 一步涨 30）
- 积累历史数据后可校准（什么幅度的出血规则和真实市场最匹配）
- Monte Carlo 扫描参数空间，找到对结果最敏感的出血阈值

---

## 四、GM裁决系统（完整规则表）

```python
def gm_resolve_rules(actions: dict, world: MacroWorldState, agents: dict) -> dict:
    delta = {}

    # ── 负向规则 ──────────────────────────────────────────
    if actions.get("A1") in ["HIKE_25BP", "HIKE_50BP"]:
        bp = 25 if "25" in actions["A1"] else 50
        delta["fed_rate_change"] = bp
        delta["bank_credit_tightening"] = 0.15 + bp * 0.001
        delta["market_sentiment"] = -0.10 - bp * 0.001

    short_count = sum(1 for a in actions.values() if a == "SHORT_MARKET")
    if short_count >= 2:
        delta["market_sentiment"] = delta.get("market_sentiment", 0) - 0.1 * short_count
        delta["liquidity_premium"] = 0.1 * short_count

    if actions.get("A6") == "AMPLIFY_FEAR":
        delta["market_sentiment"] = delta.get("market_sentiment", 0) - 0.20

    if actions.get("A2") == "TIGHTEN_CREDIT":
        delta["bank_credit_tightening"] = delta.get("bank_credit_tightening", 0) + 0.30
        delta["liquidity_premium"] = delta.get("liquidity_premium", 0) + 0.15

    if actions.get("A4") == "CUT_SUPPLY":
        delta["energy_supply_risk"] = delta.get("energy_supply_risk", 0) + 0.25

    # ── 正向规则（均值回归）──────────────────────────────────
    if actions.get("A1") in ["CUT_25BP", "CUT_50BP"]:
        bp = 25 if "25" in actions["A1"] else 50
        delta["market_sentiment"] = delta.get("market_sentiment", 0) + 0.20 + bp * 0.001
        delta["bank_credit_tightening"] = delta.get("bank_credit_tightening", 0) - 0.10

    if actions.get("A1") == "VERBAL_INTERVENTION":
        delta["market_sentiment"] = delta.get("market_sentiment", 0) + 0.15

    if actions.get("A2") == "EASE_CREDIT":
        delta["bank_credit_tightening"] = delta.get("bank_credit_tightening", 0) - 0.20
        delta["liquidity_premium"] = delta.get("liquidity_premium", 0) - 0.10

    # ── 正反馈环（涌现的来源）────────────────────────────────
    # 反馈1：情绪崩溃→媒体激活概率临时升高
    if world.market_sentiment < -0.5:
        agents["A6"].activation_prob = min(1.0, agents["A6"].activation_prob + 0.3)
        world.consecutive_negative_steps += 1
    else:
        world.consecutive_negative_steps = max(0, world.consecutive_negative_steps - 1)
        agents["A6"].activation_prob = max(0.8, agents["A6"].activation_prob - 0.1)

    # 反馈2：信贷收紧→能源融资断链
    if world.bank_credit_tightening > 0.6:
        delta["energy_supply_risk"] = delta.get("energy_supply_risk", 0) + 0.20

    # 反馈3：传染阈值——连续3步负向解锁A7强制激活
    if world.consecutive_negative_steps >= 3:
        agents["A7"].forced_activate = True
        agents["A4"].activation_prob = min(1.0, agents["A4"].activation_prob * 2)
        world.consecutive_negative_steps = 0

    # 反馈4：A7资本外流压力
    if actions.get("A7") == "CAPITAL_CONTROLS":
        delta["em_capital_outflow"] = delta.get("em_capital_outflow", 0) + 0.30

    return delta
```

---

## 五、LLM 开关（use_llm 参数）

```python
class MacroAgent:
    def __init__(self, agent_id, role, activation_delay, activation_prob,
                 hardcoded_rules: dict, persona_prompt: str):
        self.agent_id = agent_id
        self.role = role
        self.activation_delay = activation_delay
        self.activation_prob = activation_prob
        self.activation_countdown = activation_delay
        self.forced_activate = False
        self._rules = hardcoded_rules      # use_llm=False 时使用
        self._persona = persona_prompt     # use_llm=True 时使用

    def decide(self, world: MacroWorldState, use_llm: bool = False) -> str:
        context = world.get_agent_context(self.role)

        if not use_llm:
            return self._decide_rules(context)
        else:
            return self._decide_llm(context)

    def _decide_rules(self, context: dict) -> str:
        """确定性规则决策，P1调试用，长期保留"""
        for condition, action in self._rules.items():
            if eval(condition, {"ctx": context}):  # 简单条件求值
                return action
        return "HOLD"

    def _decide_llm(self, context: dict) -> str:
        """LLM决策，P2启用，失败时自动fallback到规则"""
        prompt = self._persona + f"\n\n当前状态：{context}\n\n" + \
                 "请描述你的决策理由，最后必须以 ACTION: [动作] 结尾。"
        for attempt in range(2):  # 最多重试1次
            try:
                resp = ollama.generate(
                    model="qwen2.5:32b",
                    prompt=prompt,
                    options={"temperature": 0.3}
                )
                action = re.search(r"ACTION:\s*(\w+)", resp["response"], re.I)
                if action:
                    return action.group(1).upper()
            except Exception:
                pass
        # LLM失败→fallback规则，不崩溃
        return self._decide_rules(context)
```

**开关在 Model 层统一控制**：

```python
class MacroSimModel:
    def __init__(self, world, use_llm: bool = False):
        self.world = world
        self.use_llm = use_llm   # 单一开关，所有Agent继承

    def step(self):
        # Phase 1: Observe
        for agent in self.agents.values():
            agent.current_context = self.world.get_agent_context(agent.role)

        # Phase 2: Decide（传入开关）
        step_actions = {}
        for agent_id, agent in self.agents.items():
            if agent.forced_activate:
                agent.forced_activate = False
            elif agent.activation_countdown > 0:
                agent.activation_countdown -= 1
                step_actions[agent_id] = "NO_ACTION"
                continue
            elif random.random() >= agent.activation_prob:
                step_actions[agent_id] = "NO_ACTION"
                continue

            step_actions[agent_id] = agent.decide(self.world, use_llm=self.use_llm)
            agent.activation_countdown = agent.activation_delay  # 行动后重置

        # Phase 3: GM规则更新内生变量
        delta = gm_resolve_rules(step_actions, self.world, self.agents)
        self._apply_delta(delta)
        apply_natural_decay(self.world)

        # Phase 4: 出血规则更新外生变量（传导模拟器专有）
        apply_bleed_rules(self.world)

        self.world.cycle += 1
        self.log_step(step_actions, delta)
```

---

## 六、sentiment更新（对数阻尼，防饱和）

```python
def apply_sentiment_delta(world: MacroWorldState, raw_delta: float):
    s = world.market_sentiment
    damping = 1.0 / (1.0 + 3.0 * abs(s))
    world.market_sentiment = max(-1.0, min(1.0, s + raw_delta * damping))

def apply_natural_decay(world: MacroWorldState):
    """每步无条件均值回归"""
    world.market_sentiment *= 0.97
    world.bank_credit_tightening *= 0.98
    world.liquidity_premium *= 0.95
    world.energy_supply_risk *= 0.99
```

---

## 七、Agent 角色表（含 hardcoded_rules 示例）

| ID | 角色 | 时滞 | 概率 | 关键规则（use_llm=False时） |
|----|------|-----|------|--------------------------|
| A1 | 美联储 | 4步 | 0.3 | sentiment<-0.4→CUT_25BP；market_sentiment>0.3且fed_rate_change>0→HIKE_25BP |
| A2 | 商业银行 | 2步 | 0.7 | credit_tightening>0.4→TIGHTEN_CREDIT；liquidity<0.2→EASE_CREDIT |
| A3 | 对冲基金 | 0步 | 1.0 | external_pressure_shift>0.1→SHORT_MARKET；sentiment>0.2→INCREASE_RISK |
| A4 | 能源国 | 5步 | 0.2 | energy_tension>0.5→CUT_SUPPLY；energy_tension<0.1→HOLD |
| A5 | 机构投资者 | 2步 | 0.6 | internal_stress>0.3→DECREASE_RISK；vix_shift<-0.1→INCREASE_RISK |
| A6 | 媒体 | 1步 | 0.8 | sentiment<-0.3→AMPLIFY_FEAR；sentiment>0.1→NEUTRAL_REPORT |
| A7 | 新兴市场央行 | 3步 | 0.4 | em_capital_outflow>0.3→CAPITAL_CONTROLS；dff_shift>0.02→RAISE_RATES |

---

## 八、可验证性占位符（P0必须写入）

```python
# === P0阶段写入，格式锁定，阈值P3完成前校准 ===

SENTIMENT_TO_GRV_FORECAST = {
    # (sentiment均值下界, 上界): (描述, 预期GRV变化方向, 预期天数)
    (-1.0, -0.7): ("severe_stress",    "grv_up_strong",   14),  # +20~35点
    (-0.7, -0.4): ("moderate_stress",  "grv_up_moderate", 21),  # +10~20点
    (-0.4, -0.1): ("mild_stress",      "grv_up_mild",     30),  # +0~10点
    (-0.1, +0.1): ("neutral",          "no_change",       None),
    (+0.1, +1.0): ("stable",           "grv_stable",      None),
}

def record_simulation_forecast(sim_result: dict, world: MacroWorldState):
    """每次仿真结束后记录预测，用于事后校准"""
    mean_sentiment = sim_result["mean_sentiment"]
    for (lo, hi), (label, grv_forecast, days) in SENTIMENT_TO_GRV_FORECAST.items():
        if lo <= mean_sentiment < hi:
            return {
                "sim_id": world.sim_id,
                "run_date": world.trigger_date,
                "grv_at_t0": world.grv_baseline,
                "mean_sentiment": round(mean_sentiment, 3),
                "sentiment_std": round(sim_result["std"], 3),
                "stress_label": label,
                "grv_forecast_direction": grv_forecast,
                "verify_in_days": days,
                "verify_date": None,   # P3后填入
                "actual_grv_change": None,  # 事后填入
                "verified": False,
            }

# P4历史场景（格式锁定，场景TBD）
HISTORICAL_VALIDATION_SCENARIOS = [
    {
        "name": "2020-03 COVID冲击",
        "grv_snapshot_date": "2020-03-01",
        "grv_snapshot": None,    # P4填入
        "expected_cascade": "能源→信贷→情绪",
        "actual_outcome": None,  # P4填入
    },
    {
        "name": "2022-02 俄乌冲突",
        "grv_snapshot_date": "2022-02-24",
        "grv_snapshot": None,
        "expected_cascade": "能源→通胀→加息→信贷",
        "actual_outcome": None,
    },
]
```

---

## 九、Monte Carlo输出

```python
def run_monte_carlo(initial_state: MacroWorldState,
                    n_runs: int = 100,
                    use_llm: bool = False) -> dict:
    results = []
    for seed in range(n_runs):
        random.seed(seed)
        world = copy.deepcopy(initial_state)
        world.sim_id = f"mc_{seed}"
        model = MacroSimModel(world, use_llm=use_llm)
        for _ in range(world.total_cycles):
            model.step()
        results.append({
            "seed": seed,
            "final_sentiment": world.market_sentiment,
            "final_credit": world.bank_credit_tightening,
            "final_vix": world.vix,                    # 出血后的VIX（传导模拟器专有）
            "vix_bleed": world.vix - world.vix_baseline,  # VIX实际上升了多少
            "cascade_step": model.get_first_cascade_step(),
        })

    sentiments = [r["final_sentiment"] for r in results]
    vix_bleeds = [r["vix_bleed"] for r in results]

    return {
        "sentiment_mean": statistics.mean(sentiments),
        "sentiment_std": statistics.stdev(sentiments),   # 脆弱度
        "vix_bleed_mean": statistics.mean(vix_bleeds),   # 平均VIX上升幅度
        "vix_bleed_p90": sorted(vix_bleeds)[int(n_runs * 0.9)],  # 极端情景
        "cascade_rate": sum(1 for r in results if r["cascade_step"]) / n_runs,
        "p10_sentiment": sorted(sentiments)[int(n_runs * 0.1)],
        "p90_sentiment": sorted(sentiments)[int(n_runs * 0.9)],
    }
```

**指标解读**：
- `sentiment_std > 0.4`：系统处于临界态，小扰动导致截然不同结果
- `vix_bleed_mean > 5`：内生压力已足以推动VIX显著上升
- `cascade_rate > 0.7`：高概率触发正反馈传染

---

## 十、数据接口

```python
def load_initial_state(news_db_path: str, grv_path: str, fred_path: str) -> MacroWorldState:
    # news.db 只读连接，不抢写锁
    conn = sqlite3.connect(f"file:{news_db_path}?mode=ro", uri=True)
    articles = conn.execute("""
        SELECT a.title, a.summary, a.published_at
        FROM articles a
        JOIN article_categories ac ON a.id = ac.article_id
        WHERE a.published_at > datetime('now', '-7 days')
          AND ac.category IN ('geopolitics','finance','macro','energy')
        GROUP BY a.id
        ORDER BY a.published_at DESC LIMIT 40
    """).fetchall()

    grv = load_latest_grv_snapshot(grv_path)
    fred = load_latest_fred_values(fred_path)
    vix = fred["vix"]
    grv_val = grv["composite"]
    grv_energy = grv["energy"]

    return MacroWorldState(
        vix=vix,             vix_baseline=vix,
        grv=grv_val,         grv_baseline=grv_val,
        grv_energy=grv_energy, grv_energy_baseline=grv_energy,
        grv_military=grv["military"],
        grv_trade=grv["trade"],
        t10y2y=fred["t10y2y"],
        credit_spread=fred["baa10y"],
        dff=fred["dff"],
        situation_level=fred.get("situation_level", 1),
        trigger_event=articles[0][0] if articles else "",
        recent_news=[a[0] for a in articles[:5]],
    )
```

---

## 十一、技术栈

```
语言：Python 3.11
调度：手动四阶段（不依赖Mesa调度API）
LLM：Ollama @ 192.168.31.56:11434，模型 qwen2.5:32b
      use_llm=False 时完全不调用
数据来源：news.db（只读URI）+ GRV快照 + FRED数据
存储：sim_log.db（独立，不与news.db共用）+ JSON每步快照
可视化：matplotlib（sentiment轨迹/credit折线/VIX出血/MC分布）
部署：192.168.31.62 开发，NAS定时运行
```

---

## 十二、开发路线图（最终版）

| 阶段 | 内容 | 工期 | 验收标准 | 门禁 |
|------|------|-----|---------|------|
| **P0** | MacroWorldState+baseline字段+news.db只读接口+可验证性占位符 | 0.5天 | 手动赋值打印state_dict，占位符写入sim_log.db | 无 |
| **P1** | 3个Agent(A3/A2/A6)+8条GM规则+出血规则+手动四阶段+matplotlib | 1天 | **use_llm=False**；改变初始±0.3，观察路径分叉；VIX出血规则触发 | P1门禁：路径无分叉→不推进P2 |
| **P2** | 全部7个Agent+use_llm=True开关+叙事后处理+信息不对称 | 1.5-2天 | LLM失败不崩溃；use_llm=False模式仍可正常运行 | 无 |
| **P3** | 接入真实macro-scan数据+L3+自动触发+MC×100+ntfy推送 | 1天 | 输出sentiment_std+vix_bleed_mean；预测记录写入sim_log.db | 无 |
| **P4** | 历史场景回测+校准SENTIMENT_TO_GRV_FORECAST | 待定 | 格式已锁定，场景确定后实施 | 无 |

**总工期：5.5-6天**

---

## 十三、本版本三个核心变化（v0.2→v0.3）

1. **出血规则**：4条规则让内生压力反向推动VIX/GRV/信用利差，完成传导闭环
2. **LLM开关**：`use_llm` 参数贯穿全系统，P1关闭调试，P2开启，LLM失败自动fallback规则
3. **可验证性占位符**：`SENTIMENT_TO_GRV_FORECAST` + `record_simulation_forecast()`，P0写入格式，P3后积累校准数据

---

*v0.3 by Claude Code，2026-07-07*
*基于三轮三角辩论(v0.1→v0.2) + 用户Q1/Q2/Q3决策(v0.2→v0.3)*

---

## 十四、架构演进方向（2026-07-08 确定）

> 本节记录今日架构讨论结论，指导后续迭代方向。当前代码是金融域的第一个实现，未来向此方向扩展。

### 目标输出：路径树

系统的目标输出不是单一故事，不只是概率数字，而是**结构性路径树**：

```
当前状态
    ├─ 路径A（60%）：旧秩序整合
    │      ├─ A1（40%）稳定
    │      └─ A2（60%）内战
    └─ 路径B（40%）：外部介入
           ├─ B1（70%）代理人战争
           └─ B2（30%）直接占领
```

每个分叉点的概率由 Monte Carlo 跑出，不是人工设定。

### 三层结构

```
输入层   → 初始世界状态（从文本/数据抽取）
仿真层   → ABM × Monte Carlo + 分叉点检测 → 路径树
叙事层   → LLM 给每条路径写因果解释
```

**铁律：数据流单向。** 仿真层状态 JSON → 叙事层，到此截止，叙事不反写回仿真层。

### 注入接口（下一个要实现的功能）

每步循环之间加一个外生事件注入口：

```python
def step(self, inject: dict = None):
    # ... 现有四阶段 ...
    if inject:
        self._apply_injection(inject)
```

注入来源三种：
- **预设时间表**：已知历史事件在固定步数触发
- **阈值触发**：内生变量超阈值自动触发（出血规则已是此类）
- **手动输入**：用户在仿真中途插入外生冲击

### 分叉点检测原理

跑100次 Monte Carlo，在每步检测结果分布形状：
- 单峰（正态）→ 不分叉，继续
- 双峰 → 是分叉点，把两群分开继续跑

20步里真正分叉点约2-3个，最终路径数约8条，不是指数爆炸。

### 实现顺序

```
① 注入接口        ← 地基，改 step() 加 inject 参数
② 分叉点检测      ← 依赖①，输出从数字变路径树
③ WorldState 泛化 ← 依赖②，支持金融以外的领域（历史/地缘/小说）
```

### 系统定位

**假设压力测试器，不是预测机。** 每次输出必须标注置信区间和假设前提。ABM 给概率，LLM 给叙事，两者不形成闭环。

*架构方向由三角辩论（架构师/怀疑者/工程师 × 2轮）+ 用户确认，2026-07-08*
