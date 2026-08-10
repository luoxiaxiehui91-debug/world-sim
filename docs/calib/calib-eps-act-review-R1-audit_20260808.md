# calib-eps-act-review R1 综合评审报告 — 详细审核

> ⚠️ **§7 修正声明（2026-08-08 15:20，R1 后置 Audit 复核纪要落档）**
> 本 audit 的 **13 项代码事实独立核实为有效资产**（全部成立，第三方背书）；但以下论断已被 R1 纪要 §7 纠正，**后续任何 session 引用本 audit 时以 §7 为准**：
> - **A（版本论断）不予采纳**：audit 称"报告基于 v2.0.28 早期代码、与 v2.0.29 演进脱节"——版本搞反。报告评审的正是 v2.0.29 A+D 修复后的复测（sentiment 0.385→0.54-0.57，seed 42/7/123 三轮）；audit 引用的"05:49 探针 sentiment 0.647"是 v2.0.28 时代旧数据。
> - **B（单轮数据）方法学错误**：用 05:49 单轮探针数据作"当前状态"复核，违反评审裁决第 3 条（探针有随机性、单次不可信、须多 seed 取 median）。
> - **C（门槛论断）与终局裁决相悖，明确否定**：audit 称"修复前先定是否接受 0.60 门槛"——接受线 0.60 **已冻结**（三方一致：调门槛=自证，EPS_TGT=0.03 冻结），早已定案=接受并冻结，修引擎达标。
> - **D（QA 报告缺失）定位错误**：文件在 WorkBuddy 本地 `C:\Users\luoxi\WorkBuddy\世界推演系统\calib-eps-act-review-qa-R1-2026-08-08.md`（13:52，5881B），audit 只在 NAS find 找不到即断言缺失=查找位置错误。
>
> 版本边界（§7.3）：已落地 = v2.0.27（S 类挂起）/ v2.0.28（C1-1a+C3-3a）/ v2.0.29（A+D，CACHE_VERSION 2→3）；待启动 = P0-1/P0-2/P0-3/P1-1/P1-2（§4 计划冻结）；OPEN-DECISIONS 待决 = EASE ship 闸 + 接受线未达。

---

> 审核时间：2026-08-08 15:30 UTC+8
> 审核对象：`calib-eps-act-review-R1-综合评审-2026-08-08.md`（arch/qa/data 三方评审 + 项目总监交叉验证）
> 审核方式：对照容器内 macro-sim v2.0.29 实际代码逐条核实（容器 = 源码区 HEAD，diff=0）
> 审核人：Claude（OpenClaw）

---

## 0. 总评

**报告质量：高（8/10）**。三方独立评审 + 交叉验证的机制是亮点，核心诊断（sentiment/liquidity 贴边假死、EASE 不对称、target_scale key bug）经代码核实**基本全部成立**。但存在 3 个问题：

| # | 问题 | 严重度 | 处置 |
|---|------|--------|------|
| 1 | QA 独立报告文件位置：audit 初版称 NAS 上**不存在**（§0 声称存在）| 中 | **§7-D 定位错误**：文件在 WorkBuddy 本地，非缺失 |
| 2 | 修复计划 §4 标注"用户拍板先不修"，但 v2.0.29 已落地 A/D 修复——audit 初版称**报告与代码演进脱节** | 高 | **§7-A 版本搞反**：报告评审的正是 v2.0.29 A+D 复测；"继续修引擎" vs "先不修"表述歧义真实存在（§7.1-2 采纳），边界以 §7.3 为准 |
| 3 | §5"明确不做"里 target_scale 相关判断与实测有偏差：报告说"修 key 或禁用二选一"，但实测 key bug 仍在（L175 读顶层 vs L593 写 nested），且探针已产出 target_scale 值但读回恒 1.0 | 中（准确性）| **保留**（此条未被 §7 纠正）|

---

## 1. 代码基准核实（容器 v2.0.29，全部实测）

**容器 = 源码区 HEAD**（calibrator.py / simulation.py diff=0）✅

| 报告论断 | 实测核实 | 结论 |
|----------|----------|------|
| target_scale 写 nested（L593-594）| ✅ L593 写 `probe["per_var"][v]["target_scale"]`（nested）| 成立 |
| target_scale 读顶层 → key 不匹配恒 {}（L175）| ✅ L175 `data.get("target_scale", {})` 读顶层 | 成立 |
| scale 应用点读回恒 1.0（L163-165）| ✅ L163-165 `scales.get(var, 1.0)` → 恒 1.0 | 成立 |
| m_v/consistency 仅 T-pairs；active_rate 分母全步（L578-582）| ✅ 实测 `len(pairs)/len(ds)` | 成立 |
| dead=m_v<0.002 无 clamp_frac（L592）| ✅ 实测 `dead: m_v < 0.002`（**仍无 clamp_frac**）| 成立（P0-1 未实施）|
| EPS_TGT=0.03/EPS_ACT=0.005/DELTA_DEAD=0.05（L89-93）| ✅ 实测一致 | 成立 |
| damping=max(1.0, 1/(1+3|s|))（world_state.py L307）| ✅ 实测一致（v2.0.29 A 修复已落地）| 成立 |
| decay credit×0.97/lp×0.93（world_state.py L313-315）| ✅ 实测一致 | 成立 |
| MONTHLY_SCALE=0.25 仅作用于 sentiment（simulation.py L536-539）| ✅ 实测一致（v2.0.29 D 修复已落地）| 成立 |
| clamp else 分支 [0,1]；仅 em_capital_outflow 对称（L556-565）| ✅ 实测：L558-562 em_capital_outflow 对称，bank_credit/liquidity 仍 [0,1]（注释明确"有意决策"）| 成立 |
| TIGHTEN +0.25×m / EASE -0.18×m 不对称（simulation.py L134-141）| ✅ 实测一致 | 成立 |
| tighten 先判 + ease_signal 三条件（financial.py L68-85）| ✅ 实测：`spread<200 ∧ tightening<threshold×0.3 ∧ grv_stress<threshold×0.3`（threshold=0.5）| 成立 |
| A2 threshold=0.5（agents.yaml L38）| ✅ 实测一致（实际多个 agent 都是 0.5）| 成立 |
| EASE 探针初始 credit=0.3 与 ease_signal 条件冲突（QA 抓的自证）| ✅ 实测：ease_probe initial_credit=0.3，但 ease_signal 要求 tightening<0.15——**起步即违反** | 成立 |

**结论：报告引用的所有代码事实全部核实无误**，行号有轻微偏移（报告基于 v2.0.28 早期代码，当前 v2.0.29 行号略变）但不影响论断。

---

## 2. 三方判定逐条审核

### 议题① 接受线未达 — 裁决正确 ✅

- **QA 判定"FAIL 硬失败"** ✅ 裁决正确。⚠️ 注意：audit 引用的"sentiment 0.647 / credit 0.5 / liquidity 0.4（05:49 探针）"为 v2.0.28 时代**单轮**数据，已被 §7-B 判定方法学错误（探针有随机性、单次不可信、须多 seed 取 median）——它不能作为"当前状态"证据，但 QA"FAIL 硬失败"结论本身与报告多 seed 复测（0.51-0.55 加权）一致，裁决成立。
- **arch 根因"引擎动力学+测量口径双重问题"** ✅ 代码核实：damping 恒 1（A=1.0）+ MONTHLY_SCALE 只作用于 sentiment + clamp 砍负半轴 → 三变量三种死法成立
- **data 判定"target_scale 从未生效"** ✅ 实锤（L175 读顶层 vs L593 写 nested）
- **"继续放大 A/D 无效"** ✅ 逻辑成立（A=1.0 已到上限 damping 恒 1，D 均匀放大不改变钉边界机制）
- **裁决"不调接受线"** ✅ 正确——当前是结构问题（写者/测量口径），不是边缘态，调门槛=自证

### 议题② liquidity 死变量 — 裁决正确 ✅

- **QA 根因"clamp[0,1] + 负 target"** ✅ 实测 target 推导：`liquidity_premium = cs×0.4 + t10y2y×0.3`，range [-0.7, 0.7] 可负；clamp[0,1] 砍负半轴
- **arch"正写者 7 处主导 → 仍钉 +1.0"** ✅ 逻辑成立（A2+0.12/A3+0.10/A4+0.10/A5+0.05/A10+0.05/A12+0.20/bleed+0.2 vs EASE-0.08+A11-0.05）
- **arch"测量盲区是根：probe 用 post-clamp 世界差值（L550/578）"** ✅ 实测 calibrator.py L550 `sim_delta = simulated_values[v] - prev_simulated[v]`（post-clamp 世界差值）
- **data"dead 判定把 cap 饱和误标真死"** ✅ 实测当前 probe：liquidity m_v=0.0 dead=true，但 std_delta=0.063（有波动，非真死）
- **"不做 C3 移除"** ✅ 三方一致正确（隐藏驱动链断裂，永久失去校准价值）
- **修复方向"clamp 对称 [-1,1] + clamp_frac 先行 + 写者结构"** ✅ 合理

### 议题③ EASE 不对称 — 裁决基本正确，但有个亮点被低估 ⚠️

- **QA"诊断过载 + 探针自证"** ✅ 抓得准——EASE 探针初始 credit=0.3 > ease_signal 要求 0.15，起步即违反，FAIL 不能推出"ease_signal 永假"
- **arch"决策层主阻塞 + decay 0.97 不是敌人"** ✅ 逻辑正确（decay 是 bank_credit 不死的保护机制；恢复慢是 EASE=0 的后果）
- **data"主因 clamp[0,1] 吃负写入"** ✅ 成立
- **裁决"decay 0.97 不改（分歧点终裁采纳 arch）"** ✅ 正确决策
- **修复"决策层阈值放宽 + 2 步冷却 + 幅度对称"** ✅ 合理
- **但**：报告把 EASE 探针 FAIL 完全归因于"探针自证"，低估了 arch 指出的**真实决策层不可达**（tighten 先判 + tightening 锁 0.97）——即使探针初始值正确，EASE 也可能因 tightening 恒高而不可达。这点在 OPEN-DECISIONS 已有登记（"tightening 锁 0.97 为主障碍"），报告 §3 也提到了，但裁决偏重"探针自证"，稍显失衡。

### 交叉验证 — 全部成立 ✅

报告的 5 条交叉验证（target_scale key bug / A=1.0 / credit 假健康 / sentiment 假死 / EASE 探针自证）经实测全部确认。

---

## 3. 修复计划审核（§4）

**现状核对**：

| 优先级 | 改动 | 实测状态 |
|--------|------|----------|
| P0-1 | clamp_frac + dead 改判 + n_active≥20 + seed 协议 | ❌ 未实施（dead 仍 m_v<0.002，run_probe 无 seed 参数）|
| P0-2 | EASE 决策层阈值放宽 + 冷却 + 幅度对称 | ❌ 未实施（financial.py 三条件仍 0.15 门槛）|
| P0-3 | clamp 对称 [-1,1]（bank_credit+liquidity）| ❌ 未实施（仅 em_capital_outflow 对称）|
| P1-1 | sentiment 写者结构（A3 activation 1.0→0.75）| ❌ 未实施（agents.yaml L47 activation 仍 1.00）|
| P1-2 | target_scale 修 key bug / 显式禁用 | ❌ 未实施（key bug 仍在）|

**已落地**：A 修复（damping floor 1.0）+ D 修复（MONTHLY_SCALE 0.25）+ A2 写者补丁 + EASE 定向探针（v2.0.29）+ C1-1a delta 口径 + C3-3a outflow 移除（v2.0.28）+ S 类挂起（v2.0.27）。

**问题**：报告 §4 写"用户拍板'先不修'，本计划为后续启动依据"——v2.0.27/28/29 已做 3 批修复（S 类挂起 / C1-1a+C3-3a / A+D），"先不修"的范围是 **§4 的 5 项**。§0"继续修引擎，禁调门槛"与 §4"先不修"表述歧义真实存在（§7.1-2 采纳）——**裁决结论 = 引擎必须修（禁调门槛）；执行状态 = 修复计划冻结待启动**。边界已明确，后续 session 以 §7.3 为准。

---

## 4. 发现的新问题（报告未覆盖）

### N1. QA 独立报告位置（已更正 §7-D）
报告 §0 声称"QA 独立细节见 `calib-eps-act-review-qa-R1-2026-08-08.md`"。audit 初版称"NAS 上找不到"——**定位错误**：文件在 WorkBuddy 本地 `C:\Users\luoxi\WorkBuddy\世界推演系统\calib-eps-act-review-qa-R1-2026-08-08.md`（13:52，5881B），评审文档按既有约定放本地工作区（calib-c1c3-review 终局裁决同样在本地）。非文件缺失。

### N2. calib_probe.json 的 silence_frac 字段（已对齐 §7-A）
当前 probe 含 `silence_frac`（v2.0.29 新增，A+D 修复批次引入）。报告 §1 提到"silence 53-71%>50%"与 v2.0.29 复测一致（audit 初版推断"报告基于 v2.0.28 此字段可能没有"——已被 §7-A 推翻，报告评审的就是 v2.0.29）。无实质影响。

### N3. CACHE_VERSION 已是 3（轻微）
报告守门项说"CACHE_VERSION bump（clamp 对称化/EASE 修复需 bump 4）"——当前已是 3（v2.0.29 bump 2→3）。报告写的守门项未反映当前值。后续修复需 bump 4，报告方向正确。

### N4. rho 相关性已改善但仍有问题（观察）
当前 probe：rho sentiment↔liquidity = -0.392（v2.0.28 时 -0.586，改善但仍在 |0.3| 自动闸边缘）。报告 §4 验收标准 ρ<|0.3| 自动闸——当前 -0.392 已超闸。**说明即使修复后也可能触发自动闸**，需注意。

---

## 5. 结论

> ⚠️ 本节论断 A/B/C 已被 R1 纪要 §7 纠正，以 §7 为准（见文件头）。保留原文供对照，不再作为有效结论。

**报告总体可信，诊断扎实，裁决合理**。三处需修正：

1. ~~时效性~~ **（§7-A 不予采纳）**：~~明确报告基于 v2.0.28 早期代码，当前容器 v2.0.29 已落地 A/D 修复~~——实际报告评审的正是 v2.0.29 A+D 复测；§0"继续修引擎"与 §4"先不修"的表述歧义真实存在，边界已由 §7.1-2 明确（裁决=引擎必须修禁调门槛；执行=修复计划冻结待启动）。
2. ~~完整性：补 QA 独立报告（NAS 上缺失）~~ **（§7-D 定位错误）**：QA 报告在 WorkBuddy 本地 `C:\Users\luoxi\WorkBuddy\世界推演系统\calib-eps-act-review-qa-R1-2026-08-08.md`，非缺失。
3. **一致性**：守门项 CACHE_VERSION 已 3（报告写 bump 4 方向对但未反映现值）；rho 自动闸当前已超线（§7.1-3 采纳：需观测多 seed 分布而非单轮）。

**建议下一步**（§7.3 待启动）：按报告 §4 计划推进 P0-1（测量层）→ P0-2（EASE）→ P0-3（clamp 对称），每步跑探针验证。接受线 0.60 已冻结（§7-C），无需再议；ε_act=0.005 已有 C1-1a 评审裁决在先，启动 P0 前应关闭 OPEN-DECISIONS 对应未决项。

---

## 6. 证据索引

| 证据 | 位置 |
|------|------|
| 容器版本 v2.0.29 / 容器=源码区 HEAD（diff=0）| docker exec macro-sim cat /app/VERSION；diff calibrator.py |
| 05:49 单轮 probe（v2.0.28 时代，§7-B 不可作状态证据）| /app/data/calib_probe.json（sentiment 0.647/credit 0.5/liquidity 0.4，加权 0.2526 avg_error）|
| target_scale key bug | calibrator.py L175 读顶层 vs L593 写 nested |
| dead 无 clamp_frac | calibrator.py L592 `m_v < 0.002` |
| run_probe 无 seed | calibrator.py L493 签名（仅 grv/fred/steps/config）|
| EASE 三条件仍 0.15 | financial.py L75-79 |
| clamp 仅 outflow 对称 | simulation.py L556-565 |
| A3 activation 仍 1.00 | agents.yaml L47 |
| OPEN-DECISIONS 4 项 OPEN | macro-sim/docs/decisions/OPEN-DECISIONS.md |
| git HEAD（v2.0.29，a366970ee）| S:\world-sim git log |
