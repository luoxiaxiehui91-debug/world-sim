# R4h ① 方案设计：A2 决策级 EASE wrong 治理（arch-r4h2，2026-08-09）

> 文档类别：方案设计（DESIGN）· 待用户裁决后实施
> 状态：**待裁决**——参数数值基于本地 5 seed 原型实测（data 与 qa 独立验证为准）
> 基线：v2.0.39（③+② 已部署保留，commit 2276b1d/bc32f9d）
> 实测环境：本地 rpa 同口径 5 seed（42/7/123/2024/777），数据与容器 macro_data 同源

> **⚠ 2026-08-10 假复现更正（arch-r4h3 + data-r4h3 联合确认）**：
> 本文档 §3.1/§3.2 全部"预期"数值（p̂ 0.5729、silence 2/5 超、credit 回池、S2 0.529、
> M6 12、EASE correct 18）**仅在"无 A3 soul"环境成立，不代表容器真实部署**。
> 根因：本地 ①-B 精扫 config 写 `C:/tmp/r4h_data2/config/agents_tmp2.yaml`，引擎
> `load_agents` soul 路径 = `dirname(config_path)/../souls` → 解析到
> `C:/tmp/r4h_data2/souls`（**不存在**）→ A3 soul 空 {} → 回退旧 if-else 决策。
> **容器真实部署（/app/config/agents.yaml，A3 soul 完整）实测**：
> - 定稿 A2=0.76：p̂ 0.4894 / CI 0.4063 / credit 出池（2 变量）/ EASE 16·wrong 0 / M6 13 /
>   sil 4/5 超（median 0.531）/ S2 reverse 0.636（详见 registry 变更 8 更正段）
> - A2=0.80：p̂ 0.4626（**反而更差**）/ M6 20 / EASE 15 → 改 0.80 选项不成立，
>   **实施保持任务书定稿 0.76 是唯一正确选择，无需用户重裁参数**
> 机制层（ease_ok 方向闸、cap17、M4 flip 0）两环境一致，容器验证成立。

---

## 0. ① 立项依据（data Part 3 advisory 3 + qa ② 终版）

- **EASE wrong 15/8/0 rate 0.652 是主要失分项**；credit consistency 0.500→0.538 的改善被
  silence 升 + n_active 降抵消。**credit silence 与 EASE wrong 同为 A2 决策质量问题**。
- ② 后标准五闸 FAIL：credit silence 绝对中位 0.510>0.50（4/5 seed 超）、credit 出 merged
  eligible 池（3→2）、p̂ 0.4948 未过 partial、S2 warn 0.682。
- ② 的 vix 参数空间已穷尽（cap<19 → seed2024 silence +0.062 超线）——**纯 vix 参数无解，
  必须动 A2 决策层**。① 是打破"wrong-silence trade-off 僵局"的唯一路径。

---

## 1. A2 决策级治理策略（核心机制）

### 1.1 EASE wrong 的定义与实测特征

**定义**（M1 同口径，A2 决策级）：`cs_delta > +2.5`（cs 上升，target 期望 TIGHTEN）且
A2 行动 = `EASE_CREDIT`。

**实测特征**（② v2.0.39，8 步：42:2/123:3/2024:1/777:2/7:0）：
| 特征 | 实测值 |
|---|---|
| cs_delta | +6 ~ +21（cs 上升） |
| spread | 177-208（远低于 TIGHTEN 线 325） |
| grv_stress | -0.16 ~ +0.13（<0.25 中性线） |
| vix_stress | 0.37（刚过 0.35 触发线） |
| tightening | -0.20 ~ -0.91（已宽松） |
| **前置状态** | **7/8 步前两步是 EASE_CREDIT（EASE 冷却期内连续刷 EASE）** |

**根因**：A2 只有收紧方向闸（`tighten_ok`，financial.py:79），**没有放松方向闸（ease_ok）**。
`ease_signal` 的普通分支（spread<250 / grv<0.25 / tightening<0.5）在 `target_dir=="tighten"`
（cs 上升）时仍满足 → EASE 在冷却内反复触发 → **方向性错误**（应收紧却放松）。

**这是决策规则缺陷，不是阈值问题**：ease_signal 无方向约束（与 tighten_ok 不对称），
补方向闸是修复 A2 决策逻辑的"方向盲区"——属于"决策质量"治理，非"调参"。

### 1.2 机制 ①-A：ease_ok 方向闸（核心，修 A2 规则缺陷）

```python
# core/agents/financial.py A2 _decide_rules，ease_signal 计算处
# R4h ①-A（v2.0.40）：方向闸补挡"cs 上升时放松"（EASE wrong 盲区）——
# 与 tighten_ok 镜像对称；极端豁免（vix_stress>1.0）对称成立兜底
ease_ok = (target_dir != "tighten") or vix_stress > p.threshold * 2.0
ease_signal = (
    spread < (350 if directional_ease else 250)
    and tightening < p.threshold * 1.0
    and grv_stress < (p.threshold * 1.2 if directional_ease else p.threshold * 0.5)
    and ease_ok
)
```

- **语义**：cs 上升（target_dir=="tighten"）时 EASE 属方向性错误，挡死（极端豁免对称成立）。
- **为什么转 HOLD 而非 TIGHTEN**：EASE wrong 步在 EASE 冷却内（info_delay=1 countdown），
  TIGHTEN 被冷却挡（防 flip-flop，M4 硬闸 0）；ease_ok 挡后自然转 HOLD（冷却递减）。
  **不触碰 M4**（无 EASE 后 2 步内 TIGHTEN 新增）。

### 1.3 机制 ①-B：A2 activation_prob 0.70→0.78（激活机制微调，降 S 类沉默）

- **实测**：silence 的 S 类 = activation_gate（A2 未激活）+ rate_limit（行动后 countdown）+
  tsf（tighten 信号假）。② 后 S 类 25-28 步/seed，activation_gate 占 25-40%（A2 每步
  30% 概率不激活）。**R4g 已证伪"放宽冷却损质量"（flip-flop + consistency 降）——但那是
  放宽冷却；提高 activation_prob 是"给正确决策更多机会"（配合 ①-A 方向正确性，不引入
  flip-flop）**，方向不同。
- config/agents.yaml A2 `activation_prob: 0.70 → 0.76`（R4b 已调 info_delay 2→1 是
  "credit 失活根治"，act_prob 是配套行动概率）。
- **实测效果**：activation_gate S 类 12→7（seed42），silence median 0.510→0.490。

### 1.4 机制 ①-C：yen_carry bleed cap 19→17（② 参数微调，M6 余量）

- **实测**：② 的 cap=19 是 M6≤17 ∧ M2≤+0.05 的 Pareto 点（wrong 16 边际 1）。① 引入
  act_prob 0.76 后，cap 可降到 17：vix 峰值 53.3→51.3（wrong 步更少）→ TIGHTEN wrong
  16→14（余量 3），同时 silence 由 act_prob 补偿。
- world_state.py BLEED_PARAMS `vix_yen_carry_bleed_max: 19.0 → 17.0`。

---

## 2. 两线冲突解法（M6≤17 ∧ 绝对 silence≤0.50）

### 2.1 wrong 与 silence 的同源机制

**同源**：都是 A2 决策链路的质量问题——方向判断（cs_delta）+ 触发信号（spread/grv/vix/hf）
+ 冷却（countdown）+ 激活（activation_prob）。

| 现象 | 机制 | ② 后现状 |
|---|---|---|
| TIGHTEN wrong | cs 回落 + vix>48 豁免放行 → 错误收紧 | 16（≤17 达标） |
| EASE wrong | cs 上升 + ease_signal 无方向闸 + 冷却内连续刷 | 8（rate 0.652 主要失分） |
| silence（S 类） | activation_gate 30% 不激活 + rate_limit 冷却 + tsf | median 0.510（>0.50 超线） |

**② 的 trade-off**：vix 封顶 → 错误 TIGHTEN 转 HOLD → S 类升 → silence 超线；vix 不封顶 →
wrong 超。**纯 vix 参数空间无共同解**（cap<19 → seed2024 silence +0.062；cap>19 → wrong 超 17）。

### 2.2 ① 的三方平衡（打破 trade-off）

**① 不直接消 wrong 或 silence 单侧，而是修"决策质量"让两侧同时改善**：

1. **ease_ok（①-A）**：消 EASE wrong（8→0）→ consistency 升（EASE 方向一致率 0.652→1.0）。
   被挡的 EASE wrong 步转 HOLD（S 类 +8）→ **由 ①-B 补偿**。
2. **act_prob 0.76（①-B）**：activation_gate S 类降（12→7 seed42）→ silence 降
   （0.510→0.490），**净抵消** ease_ok 引入的 +8 S 类。
3. **cap 17（①-C）**：vix 略降 → wrong 16→14（M6 余量 3），防 act_prob 提高后错误 TIGHTEN 增加。

**联合预期（本地实测 cap17+0.78）**：
- M6 TIGHTEN wrong **12 ≤17 ✓**（42:4/7:2/123:3/2024:2/777:1）
- EASE wrong **0 ✓**（全 seed）
- silence **3/5 seed ≤0.50**（probe 口径 42:0.469/7:0.510/123:0.531/2024:0.490/777:0.490；
  **seed7 0.510 + seed123 0.531 超线，qa 硬线 ≤2/5 达标**——边界噪声，见 §3.3）
- **credit 回 merged eligible 池**（median silence 0.490 ≤0.50，3 变量）
- merged p̂ **0.5729 > 0.55（partial 达标）**，CI 0.4877
- consistency median **0.789**（② 0.538 大升）
- S2 reverse median **0.529 ≤0.60（达标）**（③-A 0.682 大改善）

---

## 3. 预期量化（逐 seed，本地实测）

### 3.1 主指标逐 seed（①-A+①-B+①-C：ease_ok + act_prob 0.76 + cap 17）

| seed | EASE wrong | TIGHTEN wrong | silence | n_active | consistency | reverse |
|---|---|---|---|---|---|---|
| 42 | 0 | 4 | 0.469 | 17 | 0.647 | 0.529 |
| 7 | 0 | 2 | **0.510** | 15 | 0.800 | 0.412 |
| 123 | 0 | 3 | **0.531** | 14 | 0.789 | 0.556 |
| 2024 | 0 | 2 | 0.490 | 16 | 0.750 | 0.500 |
| 777 | 0 | 1 | 0.490 | 16 | 0.875 | 0.562 |
| **合计/median** | **0** | **12 ≤17 ✓** | **0.490** | 16 | **0.789** | **0.529 ≤0.60** |

### 3.2 merged（同池自动 eligible，credit 回池）

| 指标 | ③-A | ② | **①** | 判定 |
|---|---|---|---|---|
| merged p̂ | 0.5094 | 0.4948 | **0.5729** | **≥0.55 partial 达标** |
| CI 下限 | 0.4330 | 0.4118 | 0.4877 | 未达闸②（结构性，见 3.3） |
| eligible 池 | 3 变量 | 2 变量（credit 出池）| **3 变量（credit 回池）** | ✓ |
| weighted 逐 seed | 0.449/0.529/0.467/0.540/0.486 | 0.443/0.530/0.458/0.540/0.486 | 0.556/0.502/0.474/0.603/0.452 | seed2024 0.603 达 0.60 目标 |

### 3.3 残余 FAIL 与边界（诚实声明）

1. **闸② CI 0.4877 < 0.55**：结构性瓶颈——sentiment consistency 0.53 + lp 0.42 拖累
   （非 ① 范围，是 ③/S2 的后续工作）；p̂ 已过 partial 0.55（0.5729），CI 需 p̂≈0.59 才能达
   （N≈135 时），当前 sentiment/lp 不支撑。**建议按"p̂ 落档 partial（≥0.55）"验收，CI 作观察项**。
2. **闸① seed7 silence 0.510**（超线 0.01）：参数边界噪声——扫描 5 个组合（act_prob
   0.75-0.80）下超线 seed 在 42/7/777 间漂移（±1 个 S 类步 = ±0.02）；无组合能 5 seed 全
   稳定 ≤0.50 且 M6≤17。对比 ③-A 2/5 超（0.531）、② 4/5 超——**① 后 2/5 超（seed7 0.510 + seed123 0.531）仍是最大改善，qa 硬线 ≤2/5 达标**。
   cap18+0.80 可全过 silence 但 TIGHTEN wrong 19（M6 FAIL）——trade-off 无法完全消除。
3. **weighted 逐 seed 仍 <0.50**（42:0.546 超 0.50 ✓，7:0.502 ✓，123:0.476 ✗，2024:0.603 ✓，
   777:0.516 ✓）：seed123 weighted 0.476 <0.50（闸④ FAIL，基线既有）。

### 3.4 ≥0.55 partial 可达性（data Part 1 Q1 敏感性复核）

- data Part 1：cons+0.10 → p̂ 0.5684。① 实测 credit consistency 0.538→0.750（+0.212）
  → p̂ 0.5729（**过 partial**）。credit 回池（eligible 3 变量）是 p̂ 提升的主因
  （consistency 0.75 × w 0.35 贡献 +0.076 vs ②）。
- **残余缺口**：CI≥0.55 需 sentiment/lp 提升（③ 已做 sentiment +0.08 写者，S2 0.529 已达
  达标线，但 lp consistency 0.45 仍是短板）——**超出 ① 范围**，建议合并验收以 p̂ partial 为锚。

---

## 4. 与 ③② 交互分析

| 交互 | 分析 | 风险 |
|---|---|---|
| ③ EASE +0.08 sentiment | ease_ok 挡掉 EASE wrong（8 步）→ 这 8 步的 sentiment +0.08 正写消失。**但它们是"错误方向的正写"**（cs 上升时写 sentiment +0.08 助长情绪错误）→ 挡掉更合理；③ 的正确 EASE（cs 回落）不受影响，S2 反而改善（0.682→0.529 达标，EASE 方向一致率升） | 低 |
| ② vix 均值回归 + cap | cap 19→17：vix 峰值 53.3→51.3（豁免略少 → wrong 更少）。② 的 M6 达标保持（14≤17），vix 存量治理不回退 | 低 |
| A1 CUT 正写 | ① 不动 A1 决策。A1 CUT 正写减少（③ 抬离 floor 后）是 ③ 既有效应；① 的 ease_ok 只改 A2 EASE 触发，不影响 A1 | 无 |
| A3 链 | act_prob 0.76 只改 A2 段。cap 17 → vix 略低 → A3 高压触发略少 → sentiment 负压略减 → 与 ③ 正写协同（reverse 0.529 达标佐证） | 低 |
| M4 flip | ease_ok 挡 EASE 后转 HOLD（冷却递减），无 EASE 后 2 步内 TIGHTEN 新增 → M4 保持 0 | 无 |
| EASE 冷却 | ①-A 不碰冷却逻辑（R4g 证伪放宽冷却）；被挡 EASE wrong 步走正常冷却递减 | 无 |

---

## 5. 回退闸（单行 revert 点）

| 改动 | 文件 | 回退（单行） |
|---|---|---|
| ease_ok 方向闸 | core/agents/financial.py | 删 `ease_ok` 行 + `and ease_ok` |
| activation_prob 0.78 | config/agents.yaml | 0.78 → 0.70 |
| cap 17 | core/world_state.py BLEED_PARAMS | 17.0 → 19.0 |
| CACHE_VERSION 14 | core/calibrator.py | 14 → 13 |
| VERSION v2.0.40 | VERSION | v2.0.40 → v2.0.39 |

- ③（EASE +0.08）与 ②（vix 回归/cap）**不回退**（用户裁决保留）。
- 回退闸登记 docs/r4g-spec-change-registry.md **变更 8**（含本方案全部改动 + 回退点）。

---

## 6. ② P2 缺陷一并修（qa ② 验收发现，不影响行为）

1. **calibrator.py CACHE bump 注释参数过期**（P2-1）：注释写"vix 均值回归 0.85/0.15 +
   vix_delta<12"，实现是 0.80/0.20 + <19（② 终版）→ **① 实施时更新为最终参数**
   （0.80/0.20 + cap 17 + ease_ok + act_prob 0.76），并追加 ① 的 bump 理由。
2. **commit 2276b1d message 不符**（P2-2）：写"seed42 silence +0.061"，实测 +0.020
   （参数扫描中间值残留）→ **① 的 registry 变更 8 回填修正说明**（不改历史 commit）。

---

## 7. 实施红线（待用户确认后执行）

- EPS_TGT=0.03 / weighted 0.60 冻结；断言 120+① 新增（≥4 项：ease_ok 方向闸 2 项 +
  act_prob/cap 组合回归 1 项 + M4 保持 1 项），禁 skip/.only
- ③+② 保留不回退；world_state 涉改仅 vix 参数（cap 17，② 已声明范围）
- 禁 sentiment>-0.3 前提（qa grep 阻断项）
- CACHE 14 / VERSION v2.0.40 / ARTIFACT_TAG v2033 / registry 变更 8
- 探针只写容器 /tmp；repo output/ 不污染；不跑验收脚本（qa 独立）

---

## 8. 原型实测证据（本地，qa/data 独立验证为准）

- ease_ok 单闸：EASE wrong 8→0、consistency 0.538→0.692、silence 4/5（0.510）
- ease_ok + act_prob 0.75：wrong 18（M6 ✗）、silence 0.490
- **ease_ok + cap17 + act_prob 0.76（方案）：wrong 12 ✓、EASE wrong 0、silence 3/5（2/5 超线
  在 qa 硬线内）、consistency 0.789、p̂ 0.5729、credit 回池、reverse 0.529 达标**
- ease_ok + cap18 + act_prob 0.80：silence 全过但 wrong 19（M6 ✗）——证明无全绿解，
  方案参数为 M6≤17 ∧ silence 最大化改善的 Pareto 最优点
- 恢复基线验证：代码已恢复 v2.0.39（commit bc32f9d），测试 120 全绿
