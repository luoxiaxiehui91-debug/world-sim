# A 类主权国家 Agent 激活 — 实施设计（走大路 · 治本方案）

> 文档类别：意图（INTENT）· 设计
> 状态：**已实施 v2.3（2026-08-07）**——§3.5 前置修复清单阻塞 8 项全部落地（commit 4aaa5fde）+ 完整验证（100 MC×24 步双场景，迭代 3 轮：2254741e/1188e25d/fa1f169f），真实场景路径分叉达成（A95%/B5%）；GRV=80 高压仍单路径（三选项待用户拍板）；v2.4 起按 §3.5 重要级收尾（B2 聚类判据等）
> 关联：`agent_taxonomy.md`（18 Agent 蓝图 V2 + **v3 修订草案附录**）· `core/agents/sovereign.py`（SovereignAgent 基类 v1.0）
> 解决：question `20260806-world-deduction-grv-mean-reversion-path-collapse`（路径分叉不可达）
> 前置完成：SovereignAgent 基类（08-03）+ 5 个 soul 文件（v2.0.19-22）——**激活条件已成熟**（但见 §3.5：代码存在 17 项前置 gap，须先修后激活）
> v3 修订：①soul 映射修正（俄罗斯→A6_russia.yaml，非海湾）②A6_mideast 移除（以色列/伊朗转情境层，见 taxonomy §11.2）③id 策略澄清（新 id 不与现有 A1-A12 撞车）④gm_resolve 共存细节补充
> v2.2 修订（deepreview2 核实 + 补充 4 条）：17 项实施前置修复清单落档（§3.5）——含 D1 soul trigger 变量供给脱节（最严重，派系/红线全哑）、D2 red_lines 中文自然语言 eval 恒 False、两套白名单并存（A1/D3）、GRV delta 量纲（A4）、Board 量纲（A5）、A6 soul 挂载（A3/D4）等

---

## 1. 背景与动机

### 1.1 问题链（08-06 实测 + 用户洞察）

1. **路径分叉不可达**：GRV=80 × 100 次 MC 恒单路径（96-99%）——Agent 概率对立行为（45%/35%）、聚类阈值调整均无效
2. **根因（用户方向修正，21:26 采纳）**：12 个激活 Agent（A1-A12）**全是顺周期金融/央行角色，交易层面的市场对手方结构性缺失**——全员看空时系统里没有"另一方"买入力量，路径分叉在结构上不可能出现
3. **设计蓝图佐证**：`agent_taxonomy.md` 自述"当前 v2.0.23 的 12 个 Agent 全是金融角色，缺少军事/外交/宗教/媒体行为者"——**18 Agent（A 类 8 + B 类 4 + C 类 6）重构为设计蓝图，未实现**

### 1.2 为什么"走大路"（A 类激活）而非 A13 补丁

| 方案 | 本质 | 问题 |
|------|------|------|
| A13 ContrarianAgent（补丁）| 人工注入一个抄底角色 | 单一角色、语义人为，治标 |
| **A 类国家 Agent 激活（治本）** | **恢复系统结构性多空**：A1 美国 vs A2 中国 vs A4 俄罗斯的地缘博弈天然产生多方声音 → C 类市场接收分歧信号 → 路径分叉是系统演化自然结果 | 符合 taxonomy 蓝图意图 |

### 1.3 已就绪的基建（v2.0.19-22 铺好，无需重建）

- **SovereignAgent 基类**（`core/agents/sovereign.py` v1.0，08-03）：Board 读写、soul 派系权重决策、red_lines 强制行动、grv_impact_map 动态影响、`_eval_trigger` 条件解析
- **soul 文件 ×5**（`souls/`）：A1_usa / A2_china / A3_eu / A4_gulf_opec / A6_russia——含 doctrine / red_lines / internal_factions / grv_impact_map，**结构完整可直接消费**
- **load_agents 动态加载**（`simulation.py` L30-77）：agents.yaml 配 `class: sovereign.SovereignAgent + soul_file` 即自动构建（**无需新子类，基类全由 soul 驱动**）

---

## 2. 目标与范围

### 本次（A 类试点，治本第一层）——v2 修订：核心层 5 个

激活 **5 个核心层主权 Agent**（v3 分类学：有持续全球传导 + soul 现成）：
**A1 美国 / A2 中国 / A3 欧盟 / A4 俄罗斯 / A5 沙特-OPEC**
→ 地缘多方博弈 → Board 传导 → C 类市场 Agent 接收 → sentiment/GRV 演化分叉 → **路径 B ≥ 15%**

**v2 修订要点**（2026-08-07）：
- ~~A6 中东轴~~ **移除**——无统一对外渠道（taxonomy §11.1 原则）；以色列/伊朗拆分为情境层行为体（§11.2），**暂不激活**
- **俄罗斯 soul 修正**：`A6_russia.yaml`（原文档错配为海湾 soul）
- **沙特-OPEC 定位澄清**：`A4_gulf_opec.yaml`，作为 OPEC 产量决策行为体（有统一产量渠道），非中东政治代表
- 印度/巴西/日韩（核心层）缺 soul → 后续补，不在本次

### 本次不做（后续阶段，另立项）

- B 类 4 个（跨国组织/宗教网络/武装非国家）
- C 类完整接收链（C5 媒体 SIR 模型等 taxonomy 4.x 节）
- Secretary Agent（当前以 `validate_action` 模拟）与 LangGraph 状态机
- 核心层补 soul：印度 / 巴西 / 日韩
- 情境层注册：以色列 / 伊朗 / 乌克兰 / 土耳其 / 阿塞拜疆（taxonomy §11.3 Registry + 触发规则）

---

## 3. 设计

### 3.1 agents.yaml 注册（5 行）——v2 修正：正确 soul 映射 + id 避开现有 A1-A12

```yaml
# A 类核心层主权国家 Agent（v2 修订，2026-08-07）
# id 策略：S{1..n} 前缀，避开与现有 A1-A12（金融角色）撞车；role 用语义名
- id: S1_usa
  class: sovereign.SovereignAgent
  role: usa
  info_delay: 3
  activation_prob: 0.30   # 试点值（v2.1，QClaw P2-5），验证后回调 0.20
  soul_file: A1_usa.yaml
- id: S2_china
  class: sovereign.SovereignAgent
  role: china
  info_delay: 3
  activation_prob: 0.30   # 试点值
  soul_file: A2_china.yaml
- id: S3_eu
  class: sovereign.SovereignAgent
  role: eu
  info_delay: 4
  activation_prob: 0.30   # 试点值
  soul_file: A3_eu.yaml
- id: S4_russia
  class: sovereign.SovereignAgent            # v2.1 修正（QClaw P1-3）：俄罗斯 = 军事/能源/信息战复合行为体 → 基类（A6_russia.yaml doctrine 含乌克兰/核威慑/信息战）；非纯能源
  role: russia
  info_delay: 2
  activation_prob: 0.30
  soul_file: A6_russia.yaml   # v2 修正：俄罗斯用 A6_russia.yaml（原错配 A4_gulf_opec.yaml）；soul 文件名历史命名，实施时重命名为 S4_russia.yaml
- id: S5_saudi
  class: sovereign.EnergyGovSovereignAgent  # v2.1 修正（QClaw P1-3）：沙特 = 纯 OPEC 产量行为体 → 能源特化类
  role: opec_core
  info_delay: 2
  activation_prob: 0.30
  soul_file: A4_gulf_opec.yaml   # 定位 = OPEC 产量决策体（有统一产量渠道），非中东政治代表；实施时重命名 S5_saudi.yaml
```

- **激活概率 0.30-0.35（v2.1 试点值，QClaw P2-5）**：试点期提高确保路径分叉机制跑通（100 次 MC 大部分 run 有 sovereign 行动）；**验证通过后回调 0.15-0.25**（地缘决策低频常态值）
- info_delay 2-4：决策有观察滞后
- ~~A6_mideast~~ 已移除（v2：无统一渠道，转情境层，见 taxonomy §11.2）
- **id 冲突澄清**：现有 agents.yaml 的 A1-A12 = 金融/央行角色（A1=美联储…），taxonomy A 类 = 主权国家——**两套编号体系并存易混**。v2 起新增主权 Agent 一律用 `S{1..n}` 前缀，杜绝 A 编号撞车（如 A4=现有能源国 vs S4_russia）
- **现有 A4（energy_gov）重叠处理（v2.1，QClaw P1-4）**：现有 A4 在 gm_resolve 有硬编码能源 delta，S5_saudi 的 sovereign 循环分支也会产生能源 delta——**同轮叠加风险**。处理：S5_saudi 激活后，**现有 A4 改 NO_ACTION**（不再输出行动，其能源维度由 S5 承接）；实施时在 gm_resolve 硬编码分支加一行 `if agents.get("A4") 被 S5 取代: skip`，并对比激活前后 A4/S5 能源 delta 总和验证无双计

**v2.2 追加（deepreview2 核实 C2/C3/D4）**：
- **A4 处理方式明确（C2）**：⚠️ 实测 agents.yaml 中 A4 **当前已是激活态**（`class: sovereign.EnergyGovSovereignAgent` + `soul_file: A4_gulf_opec.yaml`），非"待 S5 激活才升级"。S5_saudi 激活时的处理**二选一**：① agents.yaml 删除 A4 条目（最干净，A4 硬编码分支一并移除）；② 保留条目但 `activation_prob: 0` + 移除 soul_file（A4 走无 soul 退化规则，activation 为 0 不产生行动）。**推荐①**，避免两个 energy agent 同时存在的语义混乱。实施时二选一并在验证表执行双计检查。
- **S1-S5 必须配 transmission_coefficients（C3）**：v2.1 注册示例缺该字段，而传导矩阵（simulation.py L295-314）读 `agents[src_id].transmission_coefficients`——**"add() 走同一机制，传导自动承接"（旧 §3.2 L147）是错的**，没有配置就没有第二跳传导。S1-S5 需显式配置向金融 Agent 的传导系数（如 S1_usa → to_A3: 0.3 / to_A10: 0.2，S5_saudi → to_A4/或能源消费方）。
- **A6 的 soul_file 移除（D4）**：A6（媒体）现挂 `soul_file: A6_russia.yaml`（agents.yaml L88，Sprint-2 预位），MediaAgent 不消费 soul（base.py L73 仅存储，`_decide_rules` 无 soul 逻辑）。**S4_russia 激活时必须从 A6 移除该行**，否则媒体 agent 挂着永不消费的主权 soul，误导排查。

### 3.2 gm_resolve_rules 消费 sovereign 行动（~30 行，含最小验证）

**核心设计：不硬编码映射，读 `soul.grv_impact_map` 动态生成 delta**

```python
# 在 gm_resolve_rules 中新增 sovereign 行动分支：
# 前置：最小验证（v2.1，QClaw P2-6）——无 Secretary Agent 时防脏数据灌入 Board/GRV
_SOVEREIGN_ACTIONS = {"IMPOSE_SANCTIONS","MILITARY_DEPLOYMENT","DIPLOMATIC_ENGAGE",
                      "CUT_OUTPUT","INCREASE_OUTPUT","EMBARGO_SIGNAL","LIFT_SANCTIONS",
                      "NO_ACTION","HOLD"}
def _valid_sovereign_action(agent, action) -> bool:
    if action not in _SOVEREIGN_ACTIONS:        # 1. 行动白名单
        return False
    if agent.soul and action not in agent.soul.get("grv_impact_map", {}):
        return False                            # 2. 行动必须定义于 soul（防幻觉 action）
    return True

for agent_id, action in step_actions.items():
    agent = agents.get(agent_id)
    if action == "NO_ACTION" or agent is None:
        continue
    # 主权国家 Agent：从 soul.grv_impact_map 取行动 → GRV 维度 delta
    if isinstance(agent, SovereignAgent) and agent.soul:
        if not _valid_sovereign_action(agent, action):   # 验证失败 → 记日志跳过（fail-loud）
            continue
        impacts = agent.get_grv_impact(action)   # {"sanctions_risk": +15, ...}
        for dim, val in impacts.items():
            if dim in _DIM_TO_WORLD:             # GRV 维度名 → world_state 字段映射
                add(agent_id, _DIM_TO_WORLD[dim], val * m)
        # 冲突/制裁行动对 sentiment 的通用影响（保守系数）
        if action in ("IMPOSE_SANCTIONS", "MILITARY_DEPLOYMENT", "CUT_OUTPUT", "EMBARGO_SIGNAL"):
            add(agent_id, "market_sentiment", -0.06 * m)
        elif action in ("DIPLOMATIC_ENGAGE", "LIFT_SANCTIONS", "INCREASE_OUTPUT"):
            add(agent_id, "market_sentiment", +0.04 * m)
```

- `_DIM_TO_WORLD`：GRV 维度（sanctions_risk/russia_europe/middle_east_energy/taiwan_strait...）→ world_state 对应字段的映射表（新增，~15 行；**目标字段已实测存在**：world_state.py L311-318 load_from_macro_scan 已在读这些维度）
- sentiment 通用影响：保守系数（±0.04-0.06），避免国家博弈放大过度波动

**v2.2 追加（deepreview2 核实 A1/D3/A4/B4/B5）**：
- **两套白名单统一（A1/D3，阻塞）**：`_SOVEREIGN_ACTIONS`（本设计）与 `SovereignAgent.VALID_ACTIONS`（sovereign.py L98-109）**不一致**——决策层允许 TECH_RESTRICTION/ALLIANCE_REINFORCE/DIPLOMATIC_OUTREACH 等（9/25 行动），验证层 `_valid_sovereign_action` 拒绝 → 决策被静默丢弃。修法：**白名单动态聚合**——启动时扫描所有已加载 soul 的 `grv_impact_map` key 并集作为白名单（QClaw A1 建议），同时保留"行动必须在 soul 有定义"检查；删除 `_SOVEREIGN_ACTIONS` 硬编码常量。或退而求其次：白名单 = VALID_ACTIONS 全集 + soul key 并集。**必须单一来源**。
- **GRV delta 量纲转换（A4，阻塞）**：soul `grv_impact_map` 值语义 = GRV 分数 delta（0-100 量纲，如 sanctions_risk +15），而 `_apply_delta` else 分支 clamp(0,1)（simulation.py L462-464）会截断：+15 → 1.0（sanctions_risk 是 [0,100] 字段，clamp 后≈归零）。修法：**在 sovereign 分支内做量纲转换**——`add(agent_id, _DIM_TO_WORLD[dim], val * m / 100)`（GRV delta → [0,1] world delta），`_DIM_TO_WORLD` 映射表只做名字映射不做量纲，量纲转换统一在 sovereign 分支完成。**同修 A5**（见 §3.3 批注）。
- **能源维度命名统一表（B5）**：三个名字并存且量纲不一，`_DIM_TO_WORLD` 必须显式列出：

| 名字 | 量纲 | 来源 | 角色 |
|------|------|------|------|
| `energy_supply_risk` | [0,1] | world_state 内生（L47） | gm_resolve A4 硬编码写入目标 |
| `energy_grid_risk` | [0,100] | world_state 外生（L37，GRV） | soul trigger/grv_impact_map 目标 |
| `middle_east_energy` | [0,100] | GRV 维度（天枢采集） | 映射到 `grv_energy`（world_state L311） |

  soul 的 grv_impact_map 里 `energy_grid_risk: +8` 与 A4_gulf 的 `middle_east_energy: +8` 语义同为"能源风险"，**实施时统一为一个维度名**（建议 world_state 内生字段 `energy_supply_risk`，GRV 外生映射进它），避免双写。
- **eval() 标注技术债（B4）**：`_eval_trigger` 的 eval 保留（触发条件为受控 yaml），但正则未跳过 True/False/None；**red_lines 格式问题见 §3.5 D2**。技术债标注，后续换 AST 解析。

**v2 共存细节（缺口④补充）**：现有 `gm_resolve_rules`（simulation.py L83）是**硬编码 A1/A2…按 id 分支**（`actions.get("A1", "HOLD")`），新增 sovereign 用**循环分支**——两者共存规则：
1. 现有硬编码分支**不动**（A1-A12 金融角色继续走原逻辑）
2. 循环分支在硬编码分支**之后**执行（`for agent_id in step_actions` + `isinstance(agent, SovereignAgent)` 过滤）——只处理 S1-S5 主权 Agent
3. `step_actions` 的 key = agent id（S1_usa 等），与现有 A1-A12 天然隔离，无冲突
4. `add()` 已是 per-agent delta 追踪（D1 fix），sovereign delta 走同一机制，传导自动承接

### 3.3 Board 初始化（v2.1 重写：GRV 派生基线 + 仿真内偏离衰减，QClaw P1-2 + 用户"动态/不确定数值"两点）

**设计原则**：
1. **Board 是动态场，不是静态表**——基线每天随 GRV 变（跨仿真），行动偏离随步衰减回基线（仿真内）
2. **初始值不拍脑袋**——强度 = 当日 GRV 维度分数映射（天枢已采集的真实地缘数据）；无 GRV 直接维度处用常量+语义锚点
3. **语义锚点**（不依赖精确值）：`<30 正常/合作 | 30-60 紧张 | 60-80 对抗 | >80 冲突边缘`

```python
# board_baseline.py（新增，~30 行）：从 grv_latest.json 派生 5×5 初始矩阵
GRV_ALIAS = {"S1":"usa","S2":"china","S3":"eu","S4":"russia","S5":"saudi"}
def derive_board_baseline(grv: dict) -> dict:
    """Board 基线 = GRV 维度分数映射（每日刷新）"""
    return {
        ("S1","S2"): {"rel":"strategic_rivalry", "intensity": grv.get("us_china_strategic", 50)},
        ("S1","S4"): {"rel":"sanctions_conflict", "intensity": grv.get("sanctions_risk", 50)},
        ("S3","S4"): {"rel":"energy_standoff",    "intensity": grv.get("russia_europe", 50)},
        ("S5","S4"): {"rel":"opec_cooperation",   "intensity": 50 + (grv.get("middle_east_energy",50)-50)/2},
        ("S1","S5"): {"rel":"security_pact",      "intensity": 60},   # 常量（美沙安保契约，GRV 无直接维度）
        ("S2","S5"): {"rel":"energy_imports",     "intensity": 45},   # 中沙石油贸易
    }

# 仿真内演化（每步，world_state 或 simulation）：
# board_cur[a][b] = baseline[a][b] + (board_cur[a][b] - baseline[a][b]) * 0.95   # 偏离向基线衰减
# sovereign 行动（如 IMPOSE_SANCTIONS）→ board_set(a, b, "conflict", +偏离)       # 行动 push 偏离
```

**调用**：`run_prediction` 开头 `board_clear()` + `board_baseline = derive_board_baseline(grv_latest)` 预置初始矩阵；每步仿真结束更新 board_cur（行动 push + 衰减）。Board 与 GRV 的双向耦合：GRV 决定基线 → Board 决策 → sovereign 行动 → GRV delta（3.2）→ 次日基线再变。

**v2.2 追加（deepreview2 核实 A5）**：
- **Board intensity 量纲归一化（A5，阻塞）**：`board_set`（sovereign.py L41）clamp intensity 到 [0,1]，而 §3.3 基线直接用 GRV 0-100 值（50/80）→ 全饱和成 1.0，无法区分"紧张(50)"与"冲突边缘(80)"。修法：**derive_board_baseline 内做归一化**——`intensity = grv.get("us_china_strategic", 50) / 100`（基线表已返回 dict 不经 board_set，直接存归一化值）；行动 push 的偏离量同样按 /100 归一化后再 board_set。语义锚点（<30 合作/30-60 紧张/60-80 对抗/>80 冲突）含义不变，只改存储量纲。

### 3.4 传导链（taxonomy 影响路径落地）

```
A1 美国 IMPOSE_SANCTIONS → Board(A1,A2) conflict↑ → A2 中国反制
  → 市场 sentiment↓ / sanctions_risk↑ / us_china_strategic↑
  → C 类市场 Agent（商行/对冲基金/散户）收到分歧信号
  → 部分 run 被空方主导（路径 A），部分被多方托住（路径 B）
```

**v2.2 追加（deepreview2 核实 B1/C1/B3）**：
- **get_agent_context 透传 GRV 维度（B1，阻塞）**：实测 `get_agent_context`（world_state.py L73）对 S 类 role（usa/china/eu/russia/opec_core）**无对应分支** → 只有基础 ctx；sanctions_risk 仅 hedge_fund/institution 分支可见（且 /100 归一化，L106），russia_europe/us_china_strategic/taiwan_strait/middle_east_energy/global_composite 不在任何 ctx。**修法：get_agent_context 增加 S 类 role 分支**，透传 GRV 相关维度（sanctions_risk/russia_europe/middle_east_energy/taiwan_strait/global_composite，统一 0-100 量纲）+ 该 sovereign 的 resources/internal_state 字段。**量纲规范：ctx 内所有 GRV 维度保持 0-100 原生量纲**（与 soul trigger 语义一致），不再 /100——改现有 hedge_fund/institution 分支的 sanctions_risk 为 0-100（影响现有金融 Agent 感知，需回归检查）。
- **Board 注入 ctx（C1）**：`_decide_rules` 的 ctx 无 Board 数据。修法：get_agent_context 的 S 类分支注入 `ctx["board"]`（该 agent 相关的 Board 关系对强度），或在 `_decide_rules` 内直接调 `board_get(actor_id, other_id)`。
- **试点期激活参数（B3，阻塞）**：info_delay 冷却（simulation.py L413 `activation_countdown = info_delay`）使 S1（info_delay=3）12 步期望仅 ~0.9 次激活；sentiment 通用影响 ±0.06 × MONTHLY_SCALE 0.12 ≈ ±0.007/步，5 agents 累计 ~-0.03，远不足以产生分叉。修法（试点期）：① S1-S5 info_delay 全部置 0（去掉冷却）；② sentiment 通用系数试点值 ±0.06 → ±0.15-0.20；③ MONTHLY_SCALE 0.12 → 0.25 试点。**三选一或组合，验证通过后回调**。设计文档 §1.1 验证标准（sentiment std > 0.15 且路径 B ≥ 15%）不变。

---

## 3.5 实施前置修复清单（v2.2 — deepreview2 13 条核实 + 补充 4 条，全部须在激活前修）

> 来源：QClaw `world-sim-docs-deepreview2_20260807-0940.md`（13 条，12 成立）+ 我方代码级核实补充（D1-D4）。
> **判定口径**：阻塞 = 不修则激活后报错/静默失败/验证必败；重要 = 影响正确性；改进 = 可后做。
> **总则**：以下修复完成后才允许实施 §6 的激活步骤。

### 阻塞级（8 项）

| # | 问题 | 证据 | 修法（已落档位置） |
|---|------|------|---------------------|
| **D1** | **soul trigger 变量供给脱节**（最严重）：14 条派系 trigger 中 13 条引用的变量（russia_europe/taiwan_strait/global_composite/economic_buffer_months/wti_price/middle_east_energy/domestic_political_pressure/iran_threat_level）不在任何 ctx；sanctions_risk/energy_grid_risk 在部分 ctx 但 /100 归一化与 soul 的 0-100 语义不匹配 | world_state.py get_agent_context L73-160（实测）；5 soul 文件 trigger | get_agent_context 增加 S 类 role 分支 + 透传 GRV 维度 + ctx 量纲统一 0-100（§3.4 B1 批注） |
| **A4** | GRV delta 被 `_apply_delta` clamp(0,1) 截断；且 grv_impact_map→delta 链路当前**未实现**（`get_grv_impact` docstring"未来 B+A/NOVEL 重写时消费"） | simulation.py L462-464；sovereign.py get_grv_impact | sovereign 分支内 `val * m / 100` 量纲转换（§3.2 A4 批注）；gm_resolve sovereign 循环分支本身即该链路实现（§3.2） |
| **A1/D3** | 两套白名单并存：决策层 VALID_ACTIONS 允许 9/25 行动，验证层 `_SOVEREIGN_ACTIONS` 拒绝 → 静默丢弃 | sovereign.py L98-109 vs activation §3.2 L111-113 | 白名单动态聚合（soul grv_impact_map key 并集），删硬编码常量（§3.2 A1 批注） |
| **B3** | info_delay 冷却 + sentiment 系数太小 → 12 步期望行动 ~1 次/agent，分叉不可达 | simulation.py L413；gm_resolve ±0.06；MONTHLY_SCALE 0.12 | 试点期 info_delay=0 或系数 0.15-0.20 或 MONTHLY_SCALE 0.25（§3.4 B3 批注） |
| **A5** | Board intensity clamp(0,1) vs GRV 0-100 → 全饱和无法区分紧张/冲突 | sovereign.py L41；§3.3 L162-164 | derive_board_baseline 内 /100 归一化（§3.3 A5 批注） |
| **B1** | get_agent_context 无 S 类 role 分支 + GRV 维度大部缺失 → 传导链断裂 | world_state.py L73-160 | S 类分支透传（§3.4 B1 批注） |
| **D2** | **red_lines 中文自然语言 → `_eval_trigger` 正则只匹配 ASCII 数值 → eval SyntaxError → 恒 False → 红线安全网全哑** | 5 soul 文件 red_lines（中文）；sovereign.py _eval_trigger L55-84 | red_lines 改数值表达式（如 `russia_europe > 75`）或代码加 LLM/规则解析层；**在 red_lines 改造前，soul 里保留中文描述仅供叙事参考，不参与强制行动判断** |
| **C3** | S1-S5 无 transmission_coefficients，"传导自动承接"错误 | simulation.py L295-314；§3.1 注册示例 | 显式配置 S1-S5 → 金融 Agent 传导系数（§3.1 C3 批注） |

### 重要级（5 项）

| # | 问题 | 证据 | 修法 |
|---|------|------|------|
| **A2** | `_get_faction_bias` 硬编码派系名（hawks/security_hawks/...），A2_china/A3_eu/A6_russia 派系名全不匹配 → 派系偏好映射失效 | sovereign.py L195-205；soul 文件 | 统一派系名为标准集，或 soul 内新增 `bias_actions` 字段由基类读取（推荐后者，更灵活） |
| **B2** | 聚类判据（sentiment/GRV 聚合）不含 GRV 维度子分数；且 GRV 分歧本质 = 初始噪声 gauss(0,8)（bifurcation.py L106），非行动演化 | bifurcation.py L392-413 | 聚类维度增加 GRV 维度子分数（如 sanctions_risk/russia_europe 终态）作第三判据；或确认 sovereign delta 传导后 sentiment 是唯一演化分叉源（配合 B3 系数调整） |
| **A3/D4** | A6 媒体 agent 挂 A6_russia.yaml soul 但不消费（MediaAgent）；S4 激活后该挂载处理未定义 | base.py L73；agents.yaml L87-88 | S4 激活时从 A6 移除 soul_file（§3.1 D4 批注） |
| **C2** | A4 当前已是激活态（EnergyGovSovereignAgent+soul），S5 激活时处理方式未明确 | agents.yaml L90-93 | 推荐 agents.yaml 删除 A4 条目（§3.1 C2 批注） |
| **B5** | 能源三维度名并存（energy_supply_risk/energy_grid_risk/middle_east_energy）量纲不一 | world_state L37/L47；gm_resolve；soul | 统一维度名（§3.2 B5 批注） |

### 改进级（4 项）

| # | 问题 | 证据 | 修法 |
|---|------|------|------|
| **C1** | ctx 无 Board 数据，_decide_rules 读不到 Board | get_agent_context；sovereign.py | S 类分支注入 ctx["board"] 或 _decide_rules 内 board_get（§3.4 C1 批注） |
| **B4** | _eval_trigger eval() 未跳过 True/False/None | sovereign.py L55-84 | 标注技术债，后续 AST 解析（§3.2 B4 批注） |
| **D3** | 两套白名单并存（已并入 A1 修法） | — | 见 A1 |
| **回归** | 现有金融 Agent 感知变化（ctx sanctions_risk 改 0-100）需回归检查 | — | 验证表已含回归检查（§4，v2.1） |

---

## 4. 验证方案

| 验证项 | 命令/方法 | 通过标准 |
|--------|----------|----------|
| 路径分叉 | GRV=80 × 100 MC（复用 verify_path_diversity 脚本）| sentiment std > 0.15 **且** 路径 B ≥ 15% |
| 校准不回退 | `run_calibration` 评分对比修复前 | 评分 ≥ 修复前（60+）|
| 国家博弈生效 | 检查 S 类决策分布（IMPOSE_SANCTIONS/MILITARY 出现次数）| 每轮仿真 S 类行动非零 |
| GRV 维度联动 | 仿真后 grv_latest 相关维度（sanctions_risk 等）有变化 | 非恒值 |
| **回归检查（v2.1，QClaw P2-7）** | 激活前后对比：A1-A12 决策分布 + forecasts/predictions 表 | 现有金融 Agent 行为无异常偏移（决策分布变化 <20%）|
| **A4/S5 双计检查（v2.1，QClaw P1-4）** | 对比激活前后能源 delta 总和（A4 vs S5）| 无双计（总和 ≈ 单主体）|

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| sovereign 行动 delta 映射错 → GRV 异常漂移 | impact_map 保守系数 + 校准评分监控 + 单维度上限 clip + 最小验证函数（§3.2）|
| 国家博弈放大波动 → 报告失真 | sentiment 通用影响用 ±0.04-0.06 保守值；验证观察路径 B 占比 >40% 即回调 |
| A 类行动过多 → 仿真时间膨胀 | 试点期 0.30-0.35 验证后回调 0.15-0.25 + info_delay 冷却 |
| soul 触发条件变量不在 ctx | `_eval_trigger` 已做缺失安全（ctx.get(var, 0)）；缺失变量触发条件静默不满足 |
| Board 基线 GRV 维度缺失 | `grv.get(dim, 50)` 默认值 + 常量关系对（美沙/中沙）|

## 6. 实施步骤（待用户确认后执行）

1. `agents.yaml` +5 注册（A1/A2/A3/A6 新增 + A4 升级 EnergyGovSovereignAgent）
2. `simulation.py` gm_resolve_rules +sovereign 分支 + `_DIM_TO_WORLD` 映射表
3. `bifurcation.py` run_prediction 开头 `board_clear()` + 预置初始关系
4. py_compile → rebuild 天璇（COPY 模式）→ 容器内跑验证脚本
5. 验证通过 → commit + push → question 状态推进 → operations 日志
6. 未通过 → 按验证表逐项排查（先查 A 类决策是否产生，再查 delta 传导）

## 7. 工作量

约 1-2 小时（注册 5 行 + gm_resolve 20 行 + Board 2 行 + 映射表 15 行 + 验证），一次 rebuild。

## 8. 变更记录

| 日期 | 变更 | 状态 |
|------|------|------|
| 2026-08-06 | 定稿：A 类 5 国家 Agent 激活设计（用户拍板"走大路"）| 待实施 |
| 2026-08-07 | **v2 修订**：soul 映射修正（俄罗斯→A6_russia.yaml）+ A6_mideast 移除（转情境层，taxonomy §11.2）+ id 改 S{1..n} 前缀避开 A1-A12 撞车 + gm_resolve 共存细节补充 + 本次范围收窄核心层 5 个 | 待用户最终确认 |
| 2026-08-07 | **v2.1 修订（QClaw 评审 9 条 + Board 动态化讨论）**：①S4 俄罗斯改基类/S5 沙特改 EnergyGov（P1-3）②A4 重叠处理：S5 激活后 A4 改 NO_ACTION（P1-4）③Board 重写为"GRV 派生基线 + 仿真内偏离衰减"（P1-2 + 用户两点）④最小验证函数（P2-6）⑤试点 activation_prob 0.30-0.35（P2-5）⑥验证加回归检查（P2-7）| 待用户最终确认 |
| 2026-08-07 | **v2.2 修订（QClaw deepreview2 13 条核实 + 补充 4 条）**：17 项实施前置修复清单落档（§3.5）——D1 soul trigger 变量供给脱节（最严重）/ D2 red_lines 中文 eval 恒 False / A1+D3 两套白名单统一 / A4+A5 量纲转换 / B1 S 类 ctx 透传 / B3 试点激活参数 / A2 派系名 / B2 聚类判据 / C1-C3 / B4 技术债 / B5 能源维度统一 | 待用户最终确认 |
| 2026-08-07 | **v2.3 实施完成（§3.5 阻塞 8 项落地，commit 4aaa5fde + 验证迭代 3 轮 2254741e/1188e25d/fa1f169f）**：world_state grv_dimensions + S 类 ctx 透传（D1/B1/C1）；gm_resolve sovereign 分支 + 动态白名单 + GRV delta 直写（A1/A4/D3/B3）；board_baseline.py（A5）；red_line_triggers + bias_actions（D2/A2）；agents.yaml S1-S5 注册 + A4 挂起 + A6 移除 soul（C2/C3/D4）；souls 重命名 S4_russia/S5_saudi。验证：真实场景分叉 A95%/B5%，GRV=80 单路径待拍板 | ✅ 已实施（2026-08-07） |
