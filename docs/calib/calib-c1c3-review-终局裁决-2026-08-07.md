# 校准模块批判性评审终局裁决 — C1-1a / C3-3a

> 日期：2026-08-07
> 评审团：arch-review（架构） / qa-review（测试） / data-review（数据） 两轮交叉质疑
> 评审对象：天璇 macro-sim 校准模块（calibrator.py / simulation.py / world_state.py / agents.yaml）
> 状态：**两案均通过（有条件），6 项必改 + 4 项建议 + 3 项守卫，全部规格化可落地**

---

## 0. 一句话裁决

- **C1-1a（绝对值 → delta 口径）**：方向正确（绝对值 vs 变化目标确是真 bug），但原设计漏了"幅度标定"——target 系数 0.5/0.6/0.4/0.3 无仿真尺度依据，只改口径不改系数 = 把"绝对水平错配"换成"变化尺度错配"。**有条件通过**。
- **C3-3a（移除 em_capital_outflow 目标）**：移除成立，证据是结构性自锁（clamp[0,1] + target 可负 + CAPITAL_CONTROLS 自举阈值 0.5 不可达）+ 校准日志实证（943 行中 148 次调 A7，141 次追 outflow，纯浪费）。**有条件通过**。

---

## 1. 六项必改（全部规格化）

### 必改 1：target 系数按仿真 delta 尺度重标定（arch）

探针 50 步（固定参数、禁调参、只记 error 序列不触发 LLM）测每变量 sim_delta 分布：

```
m_v = median|sim_delta_v|（探针期）
T_v = α·m_v, α∈[1.5,2.5]      # target 系数（stretch goal 但可达）
L_v = β·m_v, β∈[0.3,0.5]      # 活跃率下限
→ T_v > L_v 由 α > β 恒成立，结构性排除"target 比下限还小"
```

配套：目标侧去相关——lp 去掉共享的 grv×0.4（L112），改绑 `cs×0.4 + t10y2y×0.3`；sentiment 保持 `−grv×0.5`；每个外生信号至多进两个内生变量且驱动 Agent 集合不重叠。

### 必改 2：LLM 喂数真传 delta，不是改措辞（arch，含 error_history 改造定稿）

`dev_str`（L171-176）与 `error_history`（L359-360）仍喂绝对值——只改主循环不改喂数是空改。必须真传 `sim_delta`（本步快照值 − 上步快照值，快照即 L348 simulated_values）。

**error_history 改造定稿（arch 08-08 补充，data R4 比率制定稿）**：
- **字段集（data 定稿）**：`step / error_old / error_new / sim_delta_sentiment / target_sentiment / sim_delta_credit / target_credit`（lp 同构）。**error_old 只供探针段 1 决策树对比，error_new 供渲染与趋势**；error_* 存聚合标量，sim_delta_*/target_* 存逐变量原始值（**两层级，实现勿混数组**）。诊断决策后再定 compute_error 用哪个口径，探针期不重跑。
- **三处同步改造**（原错位值污染面）：
  1. L356-361 error_history 记录字段改名 + 存 sim_delta/target 分离
  2. L186-189 history_str 渲染改 `sim_delta − target`，LLM 看到真 delta 偏差
  3. L190-199 趋势分析改**比率制**（data R4，量纲无关）：`ratio = late_mean / early_mean`（均用 error_new），ratio>1.2 ⬆ / <0.8 ⬇ / else ➡；guard：两半段均值均 <0.01 → 持平（防除零）。与三段式触发同为相对量纲，架构一致，无需分位数重标定（原 ±0.03 是旧口径 0-1 量纲标定，不可迁移）
- **prev_levels**：段1诊断与段2标定共用同一滚动缓存（上一步 level）；段2调参改变 magnitude 后 level 序列偏离段1也无冲突——prev_levels 天然跟随新序列，零开销成立。
- **口径决策树（data R4，探针段 1 产出后执行）**：旧 score>76 ∧ 新一致率<60% → 改 delta 口径；新一致率也 <60% → 禁动 compute_error，查假收敛/阻尼；都 >60% → 原样只上相对触发。

### 必改 3：触发改 per-variable 相对度量 + 评分改一致性率（data，qa 对抗后确认）

- **主触发（L371）**：逐变量 `|e_i|/|target_i| > 0.5` 且该步未被排除 → 触发 LLM；每变量独立判取 any；限流 ≤1 次 LLM 调用/2 步。scale-free，从根上断"阈值与误差同尺度"的反馈失控。
- **评分（L410-411）**：`score = 100 × Σ_i w_i × consistency_rate_i`（w=0.40/0.35/0.25 纯重要性权重；consistency = 活跃样本中 sign(sim_delta)==sign(target) 占比）。旧 `100*(1−avg/0.5)` 废弃，分母 0.5 无意义。
- **fallback 副指标**（若保留绝对误差）：分母改探针 P90：`100*(1−avg_error_run/P90_probe)`。
- **聚合 θ 闸**（arch 的 θ∈(ε_good, Σw·T_v)）不单独作触发，作为一致性评分的配套校验；区间为空即 α 过大。

### 必改 4：样本过滤统一 ε_t 排除制（data，撤回自己的 sim deadband，qa 确认正交）

每步每变量经 `_step_eligibility(d, t)`（三处共用：compute_error L119-138 / 显示 L170-176 / 一致率统计，杜绝口径分叉）：

| 类 | 条件 | 处理 |
|----|------|------|
| N 中性怠工 | \|tgt\|<0.03 且 \|Δ\|<0.05 | score 记 0 误差；rate 排除 |
| U 中性乱动 | \|tgt\|<0.03 且 \|Δ\|≥0.05 | score 罚 \|Δ\|（不稳）；rate 排除 |
| S 有信号不响应 | \|tgt\|≥0.03 且 \|Δ\|<0.005 | score 罚 ≈\|tgt\|；rate 排除但计 silence_frac（守卫 A）——最危险类，双保险 |
| T 可测 | \|tgt\|≥0.03 且 \|Δ\|≥0.005 | score 全量 \|Δ−tgt\|（异号×1.5，沿用 L135-136）；rate 计入分母 |

执行顺序：deadband 走 score 路径（先），rate 排除走诊断路径（后），S 类单列。**δ_dead=0.05 是 score 轴宽恕阈值，ε_act=0.005 是诊断轴活性分类阈值，同轴不同角色不同量级，无冲突。** 关键：target≈0 排除；target≥ε_t 但 sim≈0 是欠响应真故障，**必须触发**（这就是撤回 sim deadband 的原因——它会误掩欠响应）。

### 必改 5：三守卫（qa，硬闸，score 单独不再作验收依据）

| 守卫 | 规则 | 防什么 |
|------|------|--------|
| A 活跃率 | 每变量 act_frac=#{|Δ|≥0.005}/49 ≥30%；silence_frac=#{|tgt|≥0.03 且 \|Δ\|<0.005}/49 ≤50%；任一违反 FAIL。ε_act=0.005 依据：最小单 Agent 行动 delta=0.12(MONTHLY_SCALE, simulation.py:535)×0.04(A4, L182)=0.0048 | 死仿真恒不动（dead sim 时 act_frac=0，直接否决"死仿真 96 分过闸"） |
| B 参数塌缩 | agent collapsed = 最终 sensitivity≤0.10 且 magnitude≤0.10（默认 1.0 一个量级下；校验下限允许 0.0, calibrator.py:245）；≥2 个"误差变量写者"塌缩 → FAIL。写者清单：sentiment←A1/**A2**/A3/A4/A5/A6/A7/A8/A9/A10/A11/A12；bank_credit←A1/A2/A11；liquidity←A2/A3/A4/A5/A10/A11/A12。A7 排除（C3 已移除）。**注（2026-08-08 A2 写者补丁）：sentiment 清单补 A2——simulation.py:138 EASE_CREDIT 写 -0.08\*m，原清单漏（守卫 B 判定不受影响，清单与 gm 规则必须一致）** | LLM 作弊：调 sensitivity/magnitude 向 0 双闸全过 |
| C 调参次数带 | applied=len(param_changes)（累计 append, calibrator.py:398-403）：<5 FAIL（没发生校准）；>50 FAIL（churn）；10-30 目标带；5-10/30-50 复核。历史 133/50=2.66/step（doc L21-22）已实证 churn | 阈值过紧每步触发 / 过松永不触发 |

职责分工：防恒反向 = 一致率≥80%（仅 T 类样本）；防恒不动 = 守卫 A+B（行为层+参数层双独立）；防追噪声 = 守卫 C。**系数重标定不防任何一项**，只让误差幅度诚实。

### 必改 6：C3 补丁清单（data，arch/qa 交叉确认）

- **simulation.py L551-553**：em_capital_outflow 对称 clamp（`max(-1.0, min(1.0, current+val))`），其余 else 分支保持 [0,1]；模式照抄 china_credit_impulse 负区间分支（L547-548）。**顺序：先改 clamp 再跑探针**（clamp 改变 A7 行动分布，探针必须测"最终语义"）。

**clamp 对称化升级为必要修复（arch 08-08 核实，非可选优化）**：_apply_delta（simulation.py:532-553）核实——market_sentiment 走 apply_sentiment_delta 对称 clamp[-1,1]（world_state.py:303），但 **bank_credit_tightening / liquidity_premium / em_capital_outflow 全走默认分支 clamp(0,1)**（L553），负半轴被砍。而 target 产出 [-1,1] 双向信号（outflow=grv×0.4−t10y2y×0.3、lp=grv×0.4+cs×0.3 均可负）→ **负 target 月期望全部落在 0 边界，误差恒=|target|、触发恒开，LLM 永远修不好**。现存实证：EASE_CREDIT 写 bank_credit_tightening −0.18×m（simulation.py:141），clamp(0,1) 直接截断——**当前代码里"宽松"动作对 credit level 完全无效**，只能靠 natural_decay 从上方回落。这比 level/delta 错位更深一层。

**clamp 对称化的三个连带（arch，并入裁决）**：
- a) 对称化后 GM 规则负向写入生效，EASE_CREDIT 从"无效"变"有效"，校准语义改变 → **段 1 诊断/段 2 标定必须重跑，不能复用对称化前数据**
- b) natural_decay 是乘法（bank_credit_tightening×0.97、lp×0.93、outflow×0.93，world_state.py:309-316），对称化后负值向 0 收敛方向正确，但需确认负区衰减速率无异常 → 探针加负区衰减段验证
- c) 阻尼锁区检测 |level|>0.7 阈值按新范围 [-1,1] 重标（对称化前 0-1 范围的下标定已失效）
- **calibrator.py L218**：静默删除 "em_capital_outflow 主要由 A7 驱动" 一行，**不新增任何说明**（LLM 是调参器，间接通道文案只提高无效指令概率）。
- **calibrator.py**：ERROR_WEIGHTS→3 变量（L44-49，注释改"一致性率评分权重"）；删 outflow target 行（L115）；compute_error 改相对口径+eligibility；显示加 relative（L170-176）；触发改 per-var 相对+限流（L371）；score 改一致率（L410-411）；_self_check _required 4→3（L452-453）；新增 `_step_eligibility` / `run_probe` / `calib_probe.json` / `calib_tuning_state.json`。
- **calib_tuning_state.json** 调参次数健康带第二道闸：N>30 → 阈值过紧（relative_trigger 0.5→0.65）；N<10 且一致率<60% → 过松（→0.35）；N<10 且一致率≥60% → 健康不动。
- **calib_probe.json**：σ/ρ/P90/active_rate/consistency_rate（50 步探针产出）。

---

## 2. 验收门槛（qa 裁决：选 (a) 重跑 v2 基线）

- 阶段 2 是正式项目门，宣布 76 为"新任意门槛"= 允许调门槛来通过，与死仿真自证同一病 → **必须重跑基线**。
- 做法：取当前 HEAD `macro-sim/config/agents.yaml` 删 S1-S5 条目（A1-A12 参数未被 S 引入改动；S 挂起代码 `_aid.startswith("S")` 对无 S 是 no-op）→ 跑当前 C1+C3 代码 50 步 → `v2_ref_new`。
- **gate = max(v2_ref_new×0.95, 60)**，且须同时过守卫 A/B/C，否则参考值本身不可信。
- 回退 (b) 仅当参考运行显示 metric 地板 >76 对所有配置成立（说明 gate 本身坏，不是没锚）。
- 注意：v2 基线 80 分是旧口径产物，80×0.95 与新口径不同尺，**不可直接比**。

---

## 3. 验收顺序（二段式，两段都禁开调参）

1. **诊断段 12-15 步**（固定参数不调参，快速）：产出死变量名单（m_v≈0 或一致率低）、sentiment/lp 双写相关矩阵、C3 触发决策。
2. **标定探针段 50 步**（固定参数不调参，只记 error 序列）：在 C3 后 3 变量上定量测 delta-error 稳态分布，产出 θ 分位数、T_v/L_v 联动数值、score 分母重锚。
3. 两段差别是变量集合与测量目标，不是步数；**禁开调参**否则分布被 LLM 污染。
4. 探针后先确认 C1-1a 语义风险：delta 语义下连续同向外生月会复合累加（level 收敛 vs delta 累积）——若探针发现一致率调完仍 <60%，**优先复查此语义而非继续调权重**。

---

## 4. 建议项（不阻塞）

- lp/outflow target 去相关（已并入必改 1）
- 2-3 步滚动 delta 抗振荡（delta 符号逐月随机翻转 → LLM 追噪声；守卫 C 已部分覆盖）
- 一致性率评分配合 L_v 下限的"每步乱动 50% 方向"漏洞：score 不带幅度项，但守卫 A 的 act_frac + 守卫 B 参数检查覆盖之，可加 average relative error 作副闸观察

## 4.1 data 第四轮增量（08-08，并入）

- **趋势判据比率制（量纲无关）**：L190-199 趋势分析重写——`ratio = late_mean / early_mean`（均用 error_new 新口径）；ratio>1.2 ⬆上升 / <0.8 ⬇下降 / else ➡持平；guard：两半段均值均<0.01 → 持平（防除零）。与三段式触发同为相对量纲，架构一致，无需分位数重标定。
- **error_history 字段集最终定**：`step/error_old/error_new/sim_delta_sentiment/target_sentiment/sim_delta_credit/target_credit`（lp 同构）。error_old 只供探针段1决策树对比，error_new 供渲染与趋势；**error_\* 存聚合标量，sim_delta_\*/target_\* 存逐变量原始值（两层级，实现勿混数组）**。history_str 渲染用 `sim_delta−target` 新口径进 LLM prompt。
- **决策树**（段 1 诊断产出后走）：
  - 旧 score>76 且 新一致率<60% → **改 delta 口径**
  - 新一致率也<60% → **禁动 compute_error**，查假收敛/阻尼
  - 两者都>60% → 原样，只上相对触发

## 5. Backlog 条目（data）

`| P2 | em_capital_outflow 校准-预测不对称 | C3-3a 移除根因=clamp[0,1]+target可负+CAPITAL_CONTROLS自举阈值0.5不可达；预测期 A11 HIKE→outflow↑→A7 CAPITAL_CONTROLS 连锁仍活跃。治本三步：①clamp 对称化（simulation.py L551-553 已改）②天枢接 EPFR/IIF 真实资本流做真 target（中期）③恢复条件：50 步探针 outflow 激活率>0.2 后再重进 ERROR_WEIGHTS。 |`

## 6. 评审过程记录

| 轮次 | 参与方 | 关键产出 |
|------|--------|----------|
| R1 | arch | C1 方向对但幅度标定缺失；4 处必改；新失效模式（衰减污染/振荡噪声/目标重复计数/死变量/口径泄漏） |
| R1 | qa | 死仿真自证陷阱（sim×tgt≥0 把 0 计同向 + 参数可调 0）；A7 覆盖丢失；阈值反馈失控；3 步诊断不可分 |
| R1 | data | C3 移除成立（结构自锁+日志 148 次浪费）；权重相关性（sentiment/liq_prem 负相关+尺度差 5 倍）；target=0 deadband |
| R2 | arch | 守卫+重标定自洽方程组（T_v/L_v/θ）；两层相关分开处理；prompt 只做减法；二段式定义 |
| R2 | data | per-var 相对触发主形态；放弃方差归一化做权重（欠响应反作用）；撤回 sim deadband 统一 ε_t；clamp 对称化+backlog；delta 语义复合累加风险 |
| R2 | qa | 三守卫可执行规格（A 活性/B 塌缩/C 调参带）；四类样本统一过滤（与 deadband 正交）；gate=max(v2_ref_new×0.95,60)；param_changes 可观测性（新增键纯增量不破坏消费方） |
| R3 | arch | error_history 改造定稿（双口径字段 + 三处同步 + prev_levels 共用零开销）；C1-1a 无遗留分歧 |
| R4 | arch | clamp 对称化核实升级：bank_credit/liquidity/outflow 全走 clamp(0,1) 负半轴被砍，EASE_CREDIT 对 credit 完全无效（simulation.py:141）→ 必要修复；三个连带（段1/段2重跑 / natural_decay 负区探针验证 / 阻尼锁区 \|level\|>0.7 重标） |
| R4 | data | 趋势比率制（ratio=late/early，guard 双<0.01 持平）；error_history 字段两层级定稿；口径决策树（旧>76∧新<60→改delta / 新也<60→查假收敛 / 都>60→只上相对触发）；可落地清单汇总 |
