# 校准引擎 R4f 评审终局裁决

> 日期：2026-08-09
> 评审团：arch-r4f（架构）/ qa-r4f（测试）/ data-r4f（数据）三轮独立评审 + 两轮修订（含 data 精确复算触发全团修订）
> 评审对象：天璇 macro-sim 校准引擎 A2 商业银行行为（EPS 校准，一致率评分体系）
> 评审议题：R4f 修复方案三选一/组合（① direction EASE tightening 0.5→0.65 ② activation 0.70→0.85 ③ grv_down A3/A10 独立处理）
> 上游：R4a→R4e 五轮迭代（详见 calib-R4f-评审简报-2026-08-09.md）
> 状态：**三案全部否决（不实施）· R4f 零引擎改动 · 产出=缺陷归档 + R4g 设计输入**

---

## 0. 一句话裁决

**R4f 无过闸方案。** ①杠杆 +0.001（噪声级，诊断基础为归因伪影）；②无法绕过 ease_signal 前置条件（无效行动）；③结构性不可达（grv_down reverse 惯性主导，单点调参现实上限 <0.40 目标）。三案合计乐观杠杆 +0.024 << 过闸缺口 +0.085，且均不触碰硬闸 1（逐 seed silence）的根因。**R4e 终态真实状态=硬闸 1 FAIL（非 partial），拒绝 partial 记录残留，转 R4g 结构性修 silence。**

---

## 1. 关键证据（三方复算一致，数字可复现）

### 1.1 R4e 终态真实状态 = 硬闸 1 FAIL（推翻简报 median 口径）

| 来源 | 逐 seed credit silence | 结论 |
|------|------------------------|------|
| data-r4f 复算 | 42=0.49 / **7=0.531** / **123=0.531** / 2024=0.469 / 777=0.49 | fail-fast 死在第 1 闸（per-seed silence >0.50） |
| qa-r4f 独立复算 | 同上，逐 seed 重建一致 | 实锤 |

- 落盘 acceptance_v2030c.json verdict=FAIL，failures[0] = seed7/123 silence_frac=0.531>0.50
- 简报"credit 入池（silence median 0.49≤0.50）"是 merged_eligible 的 **median 口径**，闸 1 是 **逐 seed 判定**——median 掩盖 2 个 seed 超线
- **R4e 终态 = 硬闸 FAIL，非 partial。partial 记录残留的前置条件（hard gate 全 PASS）不成立**

### 1.2 方案①杠杆 +0.001（诊断基础证伪）

| 复算项 | 结果 |
|--------|------|
| seed7 tightening∈[0.5,0.65) 步数 | 仅 3 步（0.612/0.593/0.576） |
| 其中被 grv_stress≥0.6 挡 | 2 步（grv 0.869/0.683） |
| **实际可转 EASE 步数** | **仅 1 步**（其余 4 seed 全 0；seed123 该区间完全无步） |
| 合并 p̂ | 0.5152 → 0.5162（Δ+0.0010，N=161.7） |
| CI 下限 | 0.439 → 0.440 |
| seed7 silence 修复后 | 0.531 → 0.510（仍超闸 1 的 0.50 线） |

- **"seed7 tightening 死锁"不成立**：tightening_ge_05=0.42 是 first-failure 归因伪影（先看 tighten 挡再看其他条件），真实主阻塞是 grv（R4e 简报已示 grv_ge_06 仍最大挡 0.21-0.65）
- 成本收益翻转：为解 1 步动 ease_signal 规则 + 3 处测试同步 + CACHE_VERSION bump + 引入 lp 风险通道，不值

### 1.3 方案③结构性不可达

| 复算项 | 结果 |
|--------|------|
| grv_down 桶 reverse（负向惯性）占比 | 59-76%（data）/ 59-73%（qa 独立复算） |
| S 类（惰性）占比 | ≈0 |
| A3=SHORT 占 reverse 步 | 仅 15-31%（DECREASE_RISK 15-44%，HOLD 步仍负向=A10/A6/A2 合力） |
| grv_down→0.34（A3 单点现实上限） | p̂→0.5226（qa）/ 0.528（data） |
| grv_down→0.40（结构性目标） | p̂→0.5374（qa）/ 0.538（data）——**统计上不可达** |
| **100% 修复 grv_down 桶（数学上限）** | **p̂=0.6668 但 CI_lower=0.5911 仍 <0.616 接受线** |
| ①+③ 组合上限 | p̂=0.5394 / CI 0.4626，闸 1（seed123 silence 0.531）不受影响 → **确定性 FAIL** |

- **方向质量杠杆数学上已尽**：grv_down 是结构性问题（reverse 主导），A3 单点调幅不够，需动写者结构或决策条件（R4g 重新设计）

### 1.4 硬闸 1 根因定位（qa-r4f 新增，R4g 第一嫌疑）

- credit S 类（target 非零但 d≈0）中 **rate_limit 冷却占 62.5-69.2%**（activation_gate 仅 19-46%）
- 即 2/3 的 target 非零步被 2 步冷却压成零行动（target 非零但 d≈0 占 5 seed 57.5-65%）
- ①③ 都不碰 rate_limit → 硬闸 1 确定性 FAIL
- **R4g 第一嫌疑：2 步冷却（R4b info_delay 2→1 后仍存的冷却）+ 与 R4d 删豁免的交互**

---

## 2. 三案裁决

| 方案 | 裁决 | 依据 |
|------|------|------|
| ① tightening 0.5→0.65 | **否决（不实施）** | 杠杆 +0.001 噪声级；仅 1 步可转；silence 仍超线；诊断基础为归因伪影；需动规则+测试+cache，成本收益翻转 |
| ② activation 0.70→0.85 | **维持否决** | 无法绕过 ease_signal 的 tightening/grv 条件（would_fire 转行动后仍被 tighten_ge_05 挡死=无效行动）；R4b 已证活性达标（act 0.388≥0.30），瓶颈是方向质量非激活频率；A2 高激活同步抬高 sentiment/lp 写者频率，全局风险污染归因 |
| ③ grv_down A3/A10 | **否决（本轮不实施）** | 结构性不可达（reverse 主导 59-73%，A3 单点 0.34<0.40）；100% 修复仍 CI_lower<0.616；R4e 教训（p=0.55 混合归因困难）→ 若做须 R4g 单独一轮 |

**R4f 零引擎改动 → CACHE_VERSION 保持 10，无需 bump。**

---

## 3. 归档动作（R4f 产出，不改代码）

### 3.1 设计约束归档（防未来踩坑）

**financial.py L96 tightening 条件：永久禁止全局放宽，只能 directional-only**（`tightening < (p.threshold*1.3 if directional_ease else p.threshold*1.0)` 为未来唯一合法形态）。data 风险确认：若全局放宽，neutral/tighten 方向 EASE 同步放宽 → 引入反向步，重演 R4e grv 回退。

### 3.2 lp WARN 监测线（新增，warn 级不阻塞）

- `lp consistency median ≥ R4e 落盘基线 − 0.10`，写入 acceptance 监测输出
- 理由：R4g 无论修哪条路径都会动写者频率，lp 是第二受影响变量（EASE 写 credit/lp −0.08 通道）
- warn 级而非 fail-fast：防隐性门槛争议（不把监测线变成新硬闸）

### 3.3 证据推翻记录（① 归因伪影）

- tightening_ge_05=0.42（seed7）是 first-failure 归因伪影：真实 [0.5,0.65) 区间仅 3 步、2 步被 grv≥0.6 挡、1 步可转
- 教训：**ease-block 归因必须按条件联合判定（grv∧spread∧tightening），单看 first-failure 会高估杠杆**（本次高估约 8 倍：简报 0.42 挡死假设 → 实际 1/8 可解）

### 3.4 R4f 终态定性修正

- R4e 终态 = **硬闸 1 FAIL**（逐 seed silence seed7/123=0.531>0.50），非 partial
- 简报 §2 "EASE ship 闸 5 seed 全 PASS；回退线无 revert" 仍成立，但**不改变闸 1 FAIL 事实**——闸 1 在 fail-fast 顺序最前

---

## 4. R4g 设计输入（下一轮，前置条件已就位）

### 4.1 第一步必须是 silence 归因拆分（禁止直接拍参数）

复刻 R4b 成功模式（rate_limit=0.815 归因先行 → info_delay 2→1 精准命中）：
- 拆分 credit silence 的 **activation_gate / cooldown / rule_hold 三类占比**（逐 seed）
- qa 已给线索：rate_limit 占 S 类 62.5-69.2%——**2 步冷却与 R4d 删豁免的交互是第一嫌疑**
- 归因产出后再定改哪条路径，禁止未归因先调参

### 4.2 候选路径（供设计，非本轮）

1. **A2 冷却结构**：2 步冷却是否过严 / 与 R4d 删豁免的交互（qa 定位）
2. **sentiment grv_down 写者结构**：A3 幅度不够（0.34 上限 <0.40），需动写者结构或决策条件（data 定位：reverse 主导，非 S 类惰性）；A10/A6 恐慌滞后 + A3 反弹路径（data 建议）
3. **A2 决策树灵敏度 vs 方向闸代价权衡**（arch 候选）

### 4.3 收敛判据预设（R4g 触发时生效）

- 若归因显示 **rule_hold 主导**（方向闸在 stress 窗口双挡 ease/tighten）→ silence 是 R4d 方向闸的**代价而非 bug** → 需重新审视方向闸与接受线的权衡，**此裁决超 arch 单方权限，须三方+总监，且不得在本轮触发（禁调门槛仍冻结）**
- 若归因显示 cooldown/activation 主导 → 属可修缺陷，按 R4g 正常路径

### 4.4 监测建议（data）

- per-seed credit consistency diff（123=0.500 / 2024=0.471 低点，跨 seed 极差 0.471-0.714，std≈0.10）
- per-seed silence（0.469-0.531 恰在 0.50 两侧 knife-edge）→ **R4g 前扩 seed≥7 验证**
- 新增 EASE 步方向一致率监测

---

## 5. 红线与反作弊门（维持）

- weighted 0.60 门槛冻结，禁调（调门槛=自证）；**不冻结 credit 权重**（改加权口径=隐性改门槛，踩 R1 红线；credit n_active 16 非死变量）
- EPS_TGT=0.03 冻结；tests 断言不降（guards 90+narrative 12=102）
- 验收证据只用新探针多 seed median，禁 calibration_cache 自证
- --read-only 验收只读落盘工件
- CACHE_VERSION 保持 10（R4f 零引擎改动；后续任何改动再 bump）

---

## 6. 处置建议

| 选项 | 建议 | 条件 |
|------|------|------|
| **转 R4g 结构性修 silence**（首选） | 推荐 | 唯一能同时解硬闸 1 与 p̂ 的方向；第一步归因拆分（§4.1） |
| 已知缺陷归档 + credit 权重冻结（备案） | 可并行备案 | 归档必须附明确声明"未达接受线、不 ship 商业生产"；权重冻结禁止作为绕过硬闸 1 的手段 |
| partial 记录残留 | **拒绝** | 前置条件（hard gate 1-5 全 PASS 含逐 seed silence≤0.50 ∧ 回退线无 revert ∧ median 可复现 ∧ p̂∈[0.55,0.616)）不满足 |

**引擎状态：冻结待观察（未达接受线，不 ship）。R4f 本轮价值=完整记录"R4e 硬闸 FAIL + 三方案杠杆不足 + ①归因伪影"证据链，为 R4g 提供归因先行起点。**

---

## 7. 评审过程记录

| 轮次 | 参与方 | 关键产出 |
|------|--------|----------|
| R1 | qa-r4f | ①+③ 有条件通过（3 blocking：断言冲突/CACHE bump/写者单测）；14 项验收清单 |
| R1 | arch-r4f | ① 有条件通过（4 blocking：directional-only/归因阈值/bump/lp 回退闸）；②否决；③ 建议单独 R4g |
| R1 | data-r4f | **fail：①③杠杆被高估**（复算 seed7 仅 1 步可转、R4e 终态=闸 1 硬 FAIL、组合 p̂ 0.5394 确定性 FAIL）；拒绝 partial |
| R2 | arch-r4f（修订） | 撤回①通过；R4f 零引擎改动→归档+R4g；L96 directional-only 归档约束；lp WARN 监测线（blocking 4 降级）；主矛盾重定义（阻塞=silence 非 EASE 可达性）；收敛判据预设 |
| R2 | qa-r4f（修订） | 独立复算全部成立；原"批准实施"与"partial 残留"正式收回；硬闸 1 FAIL 实锤；①③撤回；**新增 rate_limit 冷却根因定位**（S 类 62.5-69.2%）；E1 partial 判定加硬闸前置 |

**终裁（总监，08-09）：三案否决、零引擎改动、拒绝 partial、转 R4g 结构性修 silence（归因先行）、归档动作按 §3 执行。**
