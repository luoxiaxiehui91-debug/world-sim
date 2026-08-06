# A 类主权国家 Agent 激活 — 实施设计（走大路 · 治本方案）

> 文档类别：意图（INTENT）· 设计
> 状态：**已定稿待实施**（2026-08-06，用户拍板"走大路"）
> 关联：`agent_taxonomy.md`（18 Agent 蓝图 V2）· `core/agents/sovereign.py`（SovereignAgent 基类 v1.0）
> 解决：question `20260806-world-deduction-grv-mean-reversion-path-collapse`（路径分叉不可达）
> 前置完成：SovereignAgent 基类（08-03）+ 5 个 soul 文件（v2.0.19-22）——**激活条件已成熟**

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

### 本次（A 类试点，治本第一层）

激活 **5 个已有 soul 的主权国家 Agent**：A1 美国 / A2 中国 / A3 欧盟 / A4 俄罗斯（升级 EnergyGov） / A6 中东轴
→ 地缘多方博弈 → Board 传导 → C 类市场 Agent 接收 → sentiment/GRV 演化分叉 → **路径 B ≥ 15%**

### 本次不做（后续阶段，另立项）

- B 类 4 个（跨国组织/宗教网络/武装非国家）
- C 类完整接收链（C5 媒体 SIR 模型等 taxonomy 4.x 节）
- Secretary Agent（当前以 `validate_action` 模拟）与 LangGraph 状态机
- A5 海湾 / A7 日韩 / A8 全球南方（缺 soul 文件，需先补）

---

## 3. 设计

### 3.1 agents.yaml 注册（5 行）

```yaml
# A 类主权国家 Agent（2026-08-06 激活，治本方案）
- id: A1_usa
  class: sovereign.SovereignAgent
  role: usa
  info_delay: 3
  activation_prob: 0.20
  soul_file: A1_usa.yaml
- id: A2_china
  class: sovereign.SovereignAgent
  role: china
  info_delay: 3
  activation_prob: 0.20
  soul_file: A2_china.yaml
- id: A3_eu
  class: sovereign.SovereignAgent
  role: eu
  info_delay: 4
  activation_prob: 0.15
  soul_file: A3_eu.yaml
- id: A6_mideast
  class: sovereign.SovereignAgent
  role: mideast_axis
  info_delay: 2
  activation_prob: 0.15
  soul_file: A6_russia.yaml   # A6 中东轴 soul 文件（当前文件名沿用 A6_russia）
- id: A4_russia
  class: sovereign.EnergyGovSovereignAgent   # 升级现有 energy_gov 为 soul 驱动
  role: energy_gov
  info_delay: 2
  activation_prob: 0.20
  soul_file: A4_gulf_opec.yaml
```

- 激活概率 0.15-0.25：地缘决策低频（不是每月都有军事/制裁行动）
- info_delay 2-4：决策有观察滞后

### 3.2 gm_resolve_rules 消费 sovereign 行动（~20 行）

**核心设计：不硬编码映射，读 `soul.grv_impact_map` 动态生成 delta**

```python
# 在 gm_resolve_rules 中新增 sovereign 行动分支：
for agent_id, action in step_actions.items():
    agent = agents.get(agent_id)
    if action == "NO_ACTION" or agent is None:
        continue
    # 主权国家 Agent：从 soul.grv_impact_map 取行动 → GRV 维度 delta
    if isinstance(agent, SovereignAgent) and agent.soul:
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

- `_DIM_TO_WORLD`：GRV 维度（sanctions_risk/russia_europe/middle_east_energy/taiwan_strait...）→ world_state 对应字段的映射表（新增，~15 行）
- sentiment 通用影响：保守系数（±0.04-0.06），避免国家博弈放大过度波动

### 3.3 Board 初始化（2 行）

`run_prediction` 开头（`simulation.py` 或 `bifurcation.py`）调用 `board_clear()`，每轮仿真重置全局关系矩阵；可预置初始关系（如 A1-A2 台海紧张、A1-A4 制裁中）供第一轮决策参考。

### 3.4 传导链（taxonomy 影响路径落地）

```
A1 美国 IMPOSE_SANCTIONS → Board(A1,A2) conflict↑ → A2 中国反制
  → 市场 sentiment↓ / sanctions_risk↑ / us_china_strategic↑
  → C 类市场 Agent（商行/对冲基金/散户）收到分歧信号
  → 部分 run 被空方主导（路径 A），部分被多方托住（路径 B）
```

---

## 4. 验证方案

| 验证项 | 命令/方法 | 通过标准 |
|--------|----------|----------|
| 路径分叉 | GRV=80 × 100 MC（复用 verify_path_diversity 脚本）| sentiment std > 0.15 **且** 路径 B ≥ 15% |
| 校准不回退 | `run_calibration` 评分对比修复前 | 评分 ≥ 修复前（60+）|
| 国家博弈生效 | 检查 A 类决策分布（IMPOSE_SANCTIONS/MILITARY 出现次数）| 每轮仿真 A 类行动非零 |
| GRV 维度联动 | 仿真后 grv_latest 相关维度（sanctions_risk 等）有变化 | 非恒值 |

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| sovereign 行动 delta 映射错 → GRV 异常漂移 | impact_map 保守系数 + 校准评分监控 + 单维度上限 clip |
| 国家博弈放大波动 → 报告失真 | sentiment 通用影响用 ±0.04-0.06 保守值；验证观察路径 B 占比 >40% 即回调 |
| A 类行动过多 → 仿真时间膨胀 | activation_prob 低频（0.15-0.25）+ info_delay 冷却 |
| soul 触发条件变量不在 ctx | `_eval_trigger` 已做缺失安全（ctx.get(var, 0)）；缺失变量触发条件静默不满足 |

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
