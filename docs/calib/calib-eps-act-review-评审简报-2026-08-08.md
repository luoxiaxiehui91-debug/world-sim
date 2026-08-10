# ε_act 团队决议 — 三合一评审简报（输入材料）

> 日期：2026-08-08 13:48
> 评审对象：天璇 macro-sim 校准引擎（v2.0.29，commit 5d86784c6 + a366970ee）
> 评审议题：①接受线未达 ②liquidity 驱动链 ③EASE issue ③——三合一
> 输入材料：A+D 修复批次实施结果 + 5 轮 seed 探针复测数据 + 逐步诊断实证

---

## 0. 评审输入数据（容器内 50 步探针，5 轮 seed 汇总）

| 变量 | consistency 范围 | active 范围 | silence 范围 | m_v 范围 | 死变量? |
|------|-----------------|-------------|--------------|----------|---------|
| market_sentiment | 0.54-0.57 | 0.18-0.49 | 0.53-0.71 | 0.0-0.005 | 部分 seed dead |
| bank_credit_tightening | 0.55-0.61 | 0.78-0.82 | ~0.0 | 0.027-0.028 | 否（唯一健康） |
| liquidity_premium | 0.33-0.57 | 0.12-0.41 | 0.53-0.82 | **0.0（全死）** | **全部 seed dead** |

- 加权一致率（w=0.40/0.35/0.25）：**0.51-0.55 < 60% 接受线**
- EASE 定向探针 ship 闸：**5 轮全 FAIL**（决策层 EASE=0，初始 credit=0.3）

## 1. 议题①：接受线未达（加权 0.51-0.55 < 60%）

### 现状
- A+D 修复（v2.0.29）已实施：sentiment 一致率 0.385→~0.55（大幅改善），但未过 0.60
- bank_credit 0.55-0.61 边缘（部分 seed 过线）
- liquidity 0.33-0.57 仍死（cap 假收敛）
- 决策树指向：新一致率也 <60% → 禁动 compute_error，查假收敛/阻尼——但 A+D 已修 damping/MONTHLY_SCALE，仍未达

### 需要裁决
1. 继续调引擎（A 更高？D 更高？）还是接受边缘状态（记录残留风险）？
2. target 系数是否应按新探针重标定（T_v=α·m_v）？当前探针 target_scale 输出是什么？
3. 一致率分层：≥0.65 稳健 / [0.60,0.65) 边缘+记录 / <0.60 硬失败——sentiment 0.54-0.57 在硬失败区，怎么办？
4. 是否调接受线本身？——QA 已裁决"改门槛=自证陷阱"（死仿真自证同一病），须防

## 2. 议题②：liquidity_premium 死变量（cap 假收敛）

### 现状（实证）
- 探针 m_v=0.0（5/5 seed dead），active 0.12-0.41，silence 0.53-0.82
- 根因诊断（v2.0.28 探针）：liquidity 从 0.15 冲到 +1.0 cap（29/50 步），cap 处 post-clamp=0 → m_v=0（cap 假收敛，非无驱动）
- A/D 修复不覆盖：liquidity 走 _apply_delta else 分支（不经 MONTHLY_SCALE），A 只作用于 sentiment damping
- 终局裁决曾判：clamp 对称化是"必要修复"（arch 08-08 核实：bank_credit/liquidity/outflow 全走 clamp(0,1) 负半轴被砍）——但 v2.0.28 只对称化了 em_capital_outflow（L551-553），**bank_credit/liquidity 的 clamp(0,1) 未动**

### 需要裁决
1. liquidity 的 [0,1] clamp 是否对称化到 [-1,1]？连带影响（natural_decay ×0.93 负区、阻尼锁区重标）
2. 还是放大负向驱动（A2/A3/A5 等对 liquidity 的负写者）？
3. 还是 C3 式移除 liquidity 出 ERROR_WEIGHTS（治标，但失去该变量校准价值）？
4. 驱动链复核结论：谁在写 liquidity、写多少、cap 后还剩什么

## 3. 议题③：EASE issue ③（TIGHTEN vs EASE 不对称）

### 现状（实证）
- EASE 定向探针 5 轮全 FAIL：决策层 EASE=0 次
- 逐步诊断实锤：bank_credit_tightening 从 step 3 冲上 0.825 后锁死 0.970
  - TIGHTEN_CREDIT 写 +0.25×m（simulation.py:134-137）
  - EASE_CREDIT 写 -0.18×m（simulation.py:139-141）
  - [0,1] clamp 截断负半轴（simulation.py:553 默认分支）
  - natural_decay ×0.97（world_state.py:309-316）——恢复比收紧慢 ~3 倍
- ease_signal 三条件（financial.py:75-79）：spread<200 ∧ tightening<threshold×0.3 ∧ grv_stress<threshold×0.3——tightening 恒 >0.3 不满足
- 终局评审已另立 issue ③

### 需要裁决
1. TIGHTEN/EASE 对称化方案：改幅度（+0.25 vs -0.18 → 对称）？改 clamp（[-1,1]）？改衰减？改 ease_signal 阈值？
2. 优先级：EASE issue ③ 是否阻塞校准 ship？（EASE 定向探针 ship 闸 FAIL = ship 阻塞，校准不阻塞）
3. 修复范围：独立 issue 还是并入本批次？

## 4. 约束与红线（必须遵守）

- **接受线**（终局裁决）：逐变量 consistency≥0.60 + 加权≥60% + 守卫 A/B/C 全过 + ρ<|0.3|
- **回退阶梯**：A(floor)→探针→Guard A 失败→D=0.25→预测回归闸(std>0.15/路径B≥15%)→振荡回 0.12→仍败→上报 ε_act 团队决议（当前在此）
- **反剧场**：无产物不设席位；结论必须规格化可落地（给出具体文件/行/参数值）
- **禁改门槛自证**：不允许"调接受线让结果通过"（死仿真自证陷阱）
- **Bounded**：打回-重做 ≤3 轮，收敛即止
- **P0**：禁止 emoji 图标/紫粉渐变/AI 模板味（评审文档输出遵守）

## 5. 相关代码位置速查

| 文件 | 位置 | 内容 |
|------|------|------|
| core/world_state.py | L300-304 | apply_sentiment_delta damping（v2.0.29 A 修复 = max(1.0, 1/(1+3\|s\|))） |
| core/world_state.py | L309-316 | apply_natural_decay（credit×0.97 / lp×0.93 / outflow×0.93） |
| core/simulation.py | L532-553 | _apply_delta（MONTHLY_SCALE=0.25 / sentiment 前乘 / else 分支 clamp(0,1)） |
| core/simulation.py | L134-141 | TIGHTEN_CREDIT +0.25×m / EASE_CREDIT -0.18×m |
| core/agents/financial.py | L68-85 | A2 决策：tighten_signal / ease_signal（if-elif 先判） |
| core/calibrator.py | L71-75 | ERROR_WEIGHTS（0.40/0.35/0.25） |
| core/calibrator.py | L490-644 | run_probe + _run_ease_probe（ship 闸） |
| core/calibrator.py | L180-200 | _step_eligibility 四类（N/U/S/T） |
