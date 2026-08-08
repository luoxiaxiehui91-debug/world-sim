# R4c-B：A2 方向对齐设计（level 基 → delta 基）

> 文档类别：设计（DESIGN）· R4c 步骤 B（纯文档，无引擎代码改动）
> 作者：arch-r2 · 日期：2026-08-08 · 状态：待三方会签后实施
> 关联：R4b FAIL（credit consistency 0.476）+ R4c-A dead 语义修正（已落地，credit 入合并池后 p̂=0.477 仍 <0.60）

## 0. 问题定位（数据实证）

R4b 把 A2 info_delay 2→1 后，credit **行动频率达标**（act 0.388 ≥0.30、silence 0.429 ≤0.50、n_active 19），
但暴露真正的达标瓶颈——**方向质量**：

| 变量 | consistency median | grv_up | grv_down | 解读 |
|------|-------------------|--------|----------|------|
| market_sentiment | 0.500 | 0.773 ✓ | **0.273 ✗** | 恢复方向错配（R3 已发现，未修） |
| bank_credit_tightening | **0.476** | 0.429 | 0.500 | 收紧方向错配（本设计目标） |
| liquidity_premium | 0.390 | 0.364 | 0.474 | 跟随 credit 传导错配 |

**根因（rule-vs-target 语义错配）**：
- target（`_derive_endogenous_targets`）是 **delta 语义**：`bank_credit_tightening = cs_signal×0.6`，
  `cs_signal = clamp(cs_delta/50)` —— **credit 目标只由 credit_spread 变化量驱动**，且可正可负
- A2 `_decide_rules` 是 **level 语义**：`tighten_signal = spread>325 OR grv_stress>0.4 OR vix>0.35 OR
  hf SHORT OR retail PANIC` —— 全是**水平/压力信号**，不含方向
- 后果：`cs_delta<0`（利差回落，target 期望 EASE）时，A2 仍可能因 `grv_stress>0.4` 收紧 →
  **方向相反的高频行动**（R4b 行动频率翻倍后集中显形）→ credit consistency 0.476

## 1. 改造方案：A2 收紧与 cs_delta 方向对齐

### 1.1 机制：cs_delta 进 ctx

`get_agent_context` 目前只暴露水平量（credit_spread/grv_stress/vix_stress）。需新增 `credit_spread_delta`：

- `MacroWorldState` 新增属性 `credit_spread_delta`（默认 0.0）
- 校准循环（run_probe / run_calibration）在注入外生前设置
  `model.world.credit_spread_delta = cs_delta_i`（prev_row vs curr_row，与 `_derive_endogenous_targets` 同源）
- `get_agent_context` 输出 `ctx["credit_spread_delta"]`
- 非校准运行（daemon 仿真）默认 0.0 → 行为与现状一致（**不破坏生产路径**）

### 1.2 `_decide_rules` 改写（伪代码）

```python
# 新增：delta 方向（target 语义对齐）
cs_delta = ctx.get("credit_spread_delta", 0.0)
# |target|≥EPS_TGT 对应 |cs_delta|≥2.5bp（0.03/0.6×50）；±2.5bp 内视为中性（target≈0）
target_dir = "ease" if cs_delta < -2.5 else ("tighten" if cs_delta > 2.5 else "neutral")

# 方向闸：cs 回落（target 期望 EASE）时收紧需危机级信号
# （vix 紧急 / 可见 hf SHORT / retail PANIC = 实时压力，不受月度 cs_delta 覆盖）
tighten_ok = (target_dir != "ease") \
    or vix_stress > p.threshold * 1.0 \
    or hf_action == "SHORT_MARKET" \
    or retail_act == "PANIC_SELL"
tighten_signal = (
    spread > 250 + p.threshold * 150
    or grv_stress > p.threshold * 0.8
    or vix_stress > p.threshold * 0.7
    or hf_action == "SHORT_MARKET"
    or retail_act == "PANIC_SELL"
) and tighten_ok

# 方向 EASE：cs 回落时 EASE 更易触发（spread 阈值 250→350、grv 限制 0.25→0.4）
directional_ease = target_dir == "ease"
ease_signal = (
    spread < (350 if directional_ease else 250)
    and tightening < p.threshold * 1.0
    and grv_stress < (p.threshold * 0.8 if directional_ease else p.threshold * 0.5)
)
```

### 1.3 关键设计决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | 方向闸只挡 `cs_delta<0` 的收紧；`cs_delta>0` 不变 | target 只由 cs 驱动；cs 上行时收紧=正确方向，不动 |
| D2 | 危机豁免：vix>0.5 / hf SHORT / retail PANIC 仍可收紧 | 实时压力信号是 level 语义的合法例外，防极端尾部失效 |
| D3 | 方向 EASE：cs 回落时 spread 阈值放宽至 350 | 把"错误收紧步"转为"正确 EASE 步"——保 n_active 不降 + 提 consistency（关键：防 HOLD→S 类→silence 回升） |
| D4 | EPS 中性带 ±2.5bp | 与 `EPS_TGT=0.03`（credit target=cs×0.6）同口径，零幅不误触发 |
| D5 | layer-1 EASE ctx 无 cs_delta → 默认 0 → 非方向路径 | **EASE ship 闸不变**（见 §3） |

## 2. 回退触发线（Step B 验收）

| 指标 | R4c 现状 | 目标 | 回退触发（revert） |
|------|---------|------|-------------------|
| credit consistency（5 seed median） | 0.476 | **≥0.60** | <0.40（0.476−0.08） |
| sentiment grv_down（5 seed median） | 0.273 | **≥0.40** | <0.20 |
| merged p̂（闸③） | 0.477 | **≥0.55** | <0.43（且 5e 回退闸 baseline−0.10 恒查） |
| credit n_active（median） | 19 | ≥18（不因方向闸显著下降） | <15 |
| credit silence（median） | 0.43 | ≤0.50（方向 EASE 保底） | >0.55 |

回退执行：单行改回 `_decide_rules`（git revert 该 commit）+ 重跑验收。

## 3. 连带影响评估

### 3.1 EASE ship 闸（gate 5d）
- layer-1 合成 ctx（spread=150/tightening=0.3/grv=0.1/vix=0.1/无 visible）无 `credit_spread_delta`
  → 默认 0.0 → `target_dir=neutral` → 非方向路径 → ease_signal 与现状**逐字节相同** → ship 闸 PASS 保持
- ②写层宽松窗口：合成行 `credit_spread=150` 恒值 → cs_delta=0 → 非方向路径 → 不受影响

### 3.2 A2 × A3/A10/A12 同源压力行动
- A3 SHORT_MARKET（sentiment −0.18）/ A10 PANIC（−0.10）在 cs 回落月仍写负 → sentiment grv_down
  改善**有限**（A2 收紧 −0.08 只是负写者之一）——预期 grv_down 0.273→0.35-0.45，不承诺 >0.60
- A3 OVERSOLD_BOUNCE（INCREASE_RISK +0.10，45% 概率）在 cs 回落月不受影响（A3 不看 cs_delta）
- 相互作用净效应：A2 在 cs 回落月少收紧 → 少写 sentiment −0.08 与 lp +0.12 → sentiment/lp
  恢复方向压力减轻 → **grv_down 桶与 lp consistency 间接改善**（机制自洽）

### 3.3 [0,1] clamp 行为
- credit 少在 cs 回落月收紧 → `bank_credit_tightening` 水平更少钉高压 → EASE 空间更大 →
  对称振荡替代单向钉死 → credit clamp_frac 下降（水平回摆），lp 同理
- 注意：tightening 水平下降可能使 `tightening < threshold×1.0` 更常满足 → EASE 更易触发 →
  潜在 EASE 频率上升——由既有 2 步冷却兜底，不新增振荡风险

## 4. 预期数值（验收目标）

| 指标 | R4c 实测 | R4c-B 预期 | 依据 |
|------|---------|-----------|------|
| credit consistency | 0.476 | **≥0.60** | 错误方向 T 步转 EASE/HOLD，剩余正确 |
| sentiment grv_down | 0.273 | **0.35-0.45** | A2 负写减少（间接，有限） |
| liquidity consistency | 0.390 | **0.45-0.55** | lp 跟随 credit 传导改善 |
| merged p̂ | 0.477 | **0.52-0.58** | 三变量方向改善加权 |
| credit n_active | 19 | 18-21 | 方向 EASE 保底不降 |
| EASE gate | PASS | PASS | layer-1 不受影响 |

**诚实声明**：merged p̂ 预期 0.52-0.58，**仍可能 <0.60 接受线**（sentiment grv_down 0.35-0.45
不足以单独撑到 p̂≥0.60）。若 R4c-B 后 p̂∈[0.52,0.58)，剩余差距需组合
（activation 0.70→0.90 推 n_active/act 或 sentiment 恢复行为修复）——R4d 再议，禁调门槛。

## 4a. 补验结果（data-r2 R4c-B 评审条件，commit b605a5666 持久化 vix 后实测）

### 补验① 方向闸危机豁免占比（vix_stress>0.5，5 seed 合计）

冲突步（credit d>0 且 cs_delta<0）共 **53 步**，vix_stress>0.5 豁免 **33 步 = 62%**。
per-seed 敏感性（乐观投影=非豁免冲突步全部转正确 EASE）：

| seed | T | 冲突 | vix>0.5 豁免 | 现一致率 | 投影@0.5 | 投影@1.0 |
|------|---|------|-------------|---------|---------|---------|
| 42 | 21 | 9 | 5 (56%) | 0.476 | 0.667 | 0.714 |
| 7 | 18 | 9 | 8 (89%) | 0.500 | 0.556 | 0.667 |
| 123 | 16 | 8 | 4 (50%) | 0.500 | 0.750 | 0.750 |
| 2024 | 19 | 10 | 5 (50%) | 0.263 | 0.526 | 0.526 |
| 777 | 19 | 8 | 2 (25%) | 0.474 | 0.789 | 0.842 |
| median | — | — | 50% | 0.476 | **0.667** | **0.714** |

**结论**：
- vix>0.5 阈值下豁免 62%>50%——data-r2 预警成立：credit 0.60 **per-seed 不完全可达**
  （seed7=0.556 / seed2024=0.526 不过，2/5 seed）
- vix 经 bleed 漂移远超 15+grv×0.15 基线（实测 vix_stress 最高 4.99 ≈ vix 168）——"危机"
  豁免在仿真中频繁触发，方向闸被架空
- **修正建议**：危机豁免阈值调高至 **vix_stress>1.0（vix>48）** 或删除豁免（全转换）：
  - @1.0：seed42=0.714 / 7=0.667 / 123=0.750 / 2024=0.526 / 777=0.842 → median 0.714，1/5 seed 不过
  - 删除豁免：42=0.905 / 7=1.0 / 123=1.0 / 2024=0.789 / 777=0.895 → **全 seed ≥0.60**
  - seed2024 结构性困难（52% T 步是冲突步），豁免阈值无法单独解决——建议 R4d 删除豁免
    或对 vix>2.0 的极端月才豁免（其冲突步 vix 分布 0.32×5 / 1.33-4.99×5）
- **注意**：投影为乐观值（假设非豁免冲突步全转 EASE）；若 directional_ease 不触发→HOLD→
  S 类→T 计数缩减→一致率低于投影。directional_ease 实际触发率需 R4d 实测（spread/tightening/
  grv level 需持久化）

### 补验② EPS 中性带 ±2.5bp 对 n_active 影响

- credit T 类 5 seed 合计 93 步，**|cs_delta|<2.5bp 出现 0 次**（0%）
- 全步 |cs_delta|<2.5bp 共 45/245（18%），全部是 N/U 类（target |t|<0.03，本就不计入 n_active）
- **同步性验证成立**（t=cs_signal×0.6 与 cs_delta 同步构造）→ 中性带对 n_active **零影响**，
  回退线 n_active≥18 无中性带过敏感问题（data-r2 担忧解除）

### 回退线建议（data-r2）
- n_active≥18 保留（中性带无影响，见补验②）；真实 n_active 风险 = directional_ease 触发率
  （HOLD 转换→S 类），建议 R4d 一并实测 spread/tightening/grv level
- 过闸实际要求：合并 CI 下限≥0.55 在 N≈230 下等效 p̂≥**0.616**（非名义 0.60）——诚实预期
  p̂ 0.52-0.58 大概率仍 FAIL 闸②，partial 接受线建议 p̂≥0.55（需团队裁决）

## 5. 实施边界（给后续实施者）

- 只改 `core/agents/financial.py`（_decide_rules）+ `core/world_state.py`（credit_spread_delta 属性 +
  get_agent_context 输出）+ `core/calibrator.py`（run_probe/run_calibration 注入前设置 delta）
- **不动**：target 系数、EPS_TGT、activation、info_delay、EASE 冷却、A1/A3/A10 写者结构
- CACHE_VERSION 8→9（引擎决策规则改变，动力学改变 → 反作弊门必须 bump）
- 测试新增：方向闸单测（cs_delta<0 且 grv 高压 → 不收紧 / 方向 EASE 触发）+ 回退触发线常量

## 6. R4d 实施记录（v2.0.34，commit 待填）

| 项 | 实施 | 说明 |
|----|------|------|
| 方向闸 | ✅ 已实施 | `cs_delta<-2.5` 时收紧挡死；**危机豁免按终裁删除**（vix/hf/retail 不再例外） |
| 方向 EASE | ✅ 已实施 | cs 回落时 spread 250→350、grv 0.25→0.4 |
| EPS 中性带 | ✅ 已实施 | ±2.5bp（补验②已证对 n_active 零影响） |
| cs_delta 进 ctx | ✅ 已实施 | world.credit_spread_delta 属性 + get_agent_context 输出；校准循环 step 前设置；非校准默认 0.0 |
| layer-1 ctx 锁定 | ✅ 已实施 | 手写合成 dict，源码检查断言不得走 get_agent_context / 不得含 cs_delta |
| 回退线机读化 | ✅ 已实施 | R4D_ROLLBACK_LINES 5 条入验收脚本（revert 记 FAIL / warn 记 WARN） |
| 必测项持久化 | ✅ 已实施 | step_record 新增 spread/tightening/grv level（directional_ease 触发率复算用） |
| CACHE_VERSION | 8→9 | 已 bump |
| 实测结果 | 见 R4d 回传 | directional_ease 触发率 + 5 seed 关键表 + 回退线判定 |
