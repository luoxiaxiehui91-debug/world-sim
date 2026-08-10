# calib-eps-act-review R1 综合评审报告

> 日期：2026-08-08
> 评审团队：arch-review（架构）/ qa-review（QA）/ data-review（数据）三方独立评审 + 项目总监交叉验证
> 评审对象：macro-sim 校准引擎（core/calibrator.py · core/simulation.py · core/agents/financial.py · core/world_state.py · config/agents.yaml）
> 结论状态：**接受线未达，ship 阻塞。三方一致：继续修引擎，禁改门槛。**
> 本报告为综合裁决文档；QA 独立细节见 `calib-eps-act-review-qa-R1-2026-08-08.md`。

---

## 0. 执行摘要（一页）

三个议题的裁决：

| 议题 | 裁决 | 根因定位 | 修复方向 |
|------|------|----------|----------|
| ① 接受线未达（加权 0.51-0.55<60%） | **FAIL 硬失败** | sentiment 贴 floor 假死 + liquidity 贴 cap 假死 + credit 贴顶假健康（三变量两个贴边一个抖动） | 测量层 + 写者结构，**禁调门槛** |
| ② liquidity 死变量（m_v=0 全 seed dead） | **FAIL 无样本不验收** | `dead=m_v<0.002` 把 cap 饱和误标"真死"；clamp[0,1] 砍负半轴 + 正写者 7 处主导 → 钉 +1.0 → post-clamp delta=0 | clamp_frac 指标 + clamp 对称 + 写者结构 |
| ③ EASE 不对称（ship 闸 FAIL） | **阻塞成立但诊断过载** | ease_signal 三条件过严 + tighten 先判挡死（决策层主因）；幅度不对称/decay 为次因 | 决策层阈值放宽 + 冷却 + 幅度对称 |

**三方一致硬规则（新增，防自证）**：
1. 接受线不可调（调门槛=自证）；EPS_TGT=0.03 冻结；验收证据只用新探针 `calib_probe.json`，禁用 calibration_cache 分数。
2. consistency 必须带最小有效样本：`n_active<20` 的变量不算 pass/fail，算 **insufficient sample**，不得计入加权。
3. 固定 seed 协议：canonical seed 42 + ≥5 seed 取 median（当前 run_probe 无 seed 参数，单次结果跨线摆动不可信）。
4. dead 判定升级：`m_v<0.002 ∧ clamp_frac<0.3` 才算死（clamp_frac 区分"饱和 vs 无写者"）。
5. target_scale 重标定**当前从未生效**（key bug），且 T_v=2·m_v 公式自指退化 → **禁启用**。

---

## 1. 议题① 接受线未达

### 三方判定
- **QA**：FAIL 硬失败区（sentiment 0.54-0.57 / liquidity 0.33-0.57 / 加权 0.51-0.55）。分层 [0.60,0.65) 边缘只作过线后风险分档。接受线缺陷：consistency 无最小样本下限 → n_active 仅 6-20 时一致率是噪声不是证据。
- **arch**：根因混合型——sentiment/liquidity 是"引擎动力学+测量口径"双重问题；bank_credit 是"相位滞后口径噪声"。**继续放大 A/D 无效**：A=1.0 已 damping 恒 1（world_state.py:307），D=0.25 均匀放大正负双方，不改变"钉边界→post-clamp delta=0"的假死机制。
- **data**：score 只依赖方向与 target 幅度无关 → target_scale 不影响 score，只改步分类构成。**target_scale 从未生效**：run_probe L593 写 nested `per_var[v].target_scale`，`_load_target_scales` L175 读顶层 `"target_scale"` → key 不匹配恒 `{}` → scale 恒 1.0（结构性 bug）。

### 交叉验证（实测核实）
- ✅ target_scale key bug 实锤（calibrator.py:593 写 nested / :175 读顶层）。
- ✅ A=1.0 damping 恒 1 实锤（world_state.py:307 `max(1.0, 1/(1+3|s|))`）。
- ✅ credit m_v=0.027-0.028 ≈ decay 0.97×0.97≈0.029 天花板平衡抖动 → "唯一健康"是假健康（data/arch 共识）。
- ✅ sentiment m_v≈0-0.005 且 silence 53-71%>50% → A/D 改善一致率但活性未根治。

### 裁决
- **不调接受线**；分层线保留但当前是结构问题非边缘态。
- **不做**：放大 A/D（已到 A=1.0 上限）、启用 2·m_v 公式、C3 移除。
- **做**：测量口径（clamp_frac / pre-clamp delta 可选）+ 写者结构 + 对称 clamp（见修复计划）。

---

## 2. 议题② liquidity 死变量

### 三方判定
- **QA**：m_v=0.0 全 seed dead，守卫 A 不过（active 0.12-0.41<30%）。根因确认：simulation.py L555-565 仅 em_capital_outflow 对称 clamp；liquidity target 可负（cs×0.4+t10y2y×0.3）→ 负 target 月误差恒=|target|，cap 假收敛。修复裁决：优先对称 clamp（照抄 L562-563 模式）；dead 判定 m_v<0.002 是单点 knife-edge → 改输出 m_v 分布/CI。
- **arch**：clamp(0,1) 砍负半轴只是表象。**即使对称 [-1,1]，正写者仍主导**（正写者 7 处：A2+0.12/A3+0.10/A4+0.10/A5+0.05/A10+0.05/A12+0.20/bleed+0.2 vs 负写者仅 EASE-0.08 永假+A11-0.05 弱）→ 仍钉 +1.0 → m_v=0 → 误判 dead → C3 移除 → 永久失去校准价值。**测量盲区是根**：probe 用 post-clamp 世界差值（calibrator.py:550/578），cap 处恒 0。
- **data**：dead 判定仅 m_v<0.002 → 把 cap 饱和误标"真死"，C3 移除决策走错原因。target∈[-0.7,0.7] vs clamp[0,1] → 负半轴不可测=失配实锤。**方案顺序**：①先加 clamp_frac 指标区分"饱和 vs 无写者"（否则修复不可验证）②clamp 对称化 ③应力单向窗口下 +1.0 饱和仍使 m_v=0，需同步控饱和或窗口混 regime。

### 交叉验证（实测核实）
- ✅ simulation.py L562-563 em_capital_outflow 已对称化（C3-3a 08-08 终局）；L560 注释明确 bank_credit/liquidity 保持 [0,1] 是**有意决策**（OPEN-DECISIONS 跟踪）→ 对称化需更新既有终局裁决记录。
- ✅ calibrator.py L550 sim_delta 用 post-clamp 世界差值 → cap 处恒 0。
- ✅ world_state.py L312-313 decay：credit×0.97 / lp×0.93。

### 裁决
- **不做 C3 移除**（三方一致反对：隐藏驱动链断裂）。
- **做**：clamp 对称 [-1,1]（bank_credit+liquidity 同批，同病同医）+ clamp_frac 指标先行（修复可验证前提）+ 写者结构同步（防对称后仍钉 +1.0）。
- **验证口径**：对称化后若 m_v 仍 0 勿断言已修，须以负半轴 T-pair 数与 clamp_frac 验证。

---

## 3. 议题③ EASE 不对称

### 三方判定
- **QA**：ship 阻塞成立，但**诊断过载**——EASE 探针初始 credit=0.3 与 ease_signal 条件 tightening<threshold×0.3（threshold 0.5→0.15）结构冲突，起步即违反①前提 → FAIL 是探针构造自证，不能推出"ease_signal 永假"。需两级拆分：①决策层用规则单测/合成 ctx 验证可达性；②写层才用 credit=0.3 仿真验证落地。对称化裁决：+0.25 vs -0.18 不对称 + decay×0.97 锁 0.97 → 恢复比收紧慢 ~3 倍成立。
- **arch**：决策层是主阻塞（ease_signal 三条件过严：tightening<0.15 ∧ spread<200 ∧ grv<0.15，financial.py:75-79）+ tighten 先判 + visible hf SHORT 挡死 → EASE=0。写层 clamp 截断是次阻塞。**衰减 ×0.97 不是敌人**——它是唯一让 bank_credit 不死的机制；恢复慢是 EASE=0 的后果，不是衰减的错。
- **data**：主因 clamp[0,1] 吃负写入；ease_signal 恒 tight>0.3×threshold 不满足是决策层死因；幅度+衰减为次因。只改幅度不改 clamp → EASE 仍贴 0 不落地。反证：ease_signal 放宽需验与 tighten 同窗口冲突（if-elif tighten 先判挡死 reachability）。

### 交叉验证（实测核实）
- ✅ financial.py L68-85：tighten 先判（if-elif），ease_signal 三条件 `spread<200 ∧ tightening<0.15 ∧ grv_stress<0.15`（threshold=0.5）。**EASE 探针初始 credit=0.3>0.15 → 探针自证成立（QA 抓得准）**。
- ✅ simulation.py L134-141：TIGHTEN +0.25×m / EASE -0.18×m 不对称。
- ✅ A2 params threshold=0.5（agents.yaml L38）。

### 裁决
- **ship 闸 FAIL 判定正确**（EASE 未落地 → 阻塞 ship，但不阻塞校准其他变量；单方向可信度须记录）。
- **EASE 探针拆分两级**：①决策层规则单测/合成 ctx 验证可达性（直接构造满足 ease_signal 的输入调 A2 决策函数）；②写层仿真验证落地。
- **修复**：决策层阈值放宽（tightening<0.5、spread<250、grv<0.25）+ TIGHTEN 后 2 步冷却防 flip-flop（v2.0.1 史）+ 幅度对称 -0.18→-0.25。
- **decay 0.97 不改**（分歧点终裁：采纳 arch——decay 是 bank_credit 不死机制，恢复慢是 EASE=0 的后果；QA 的 0.97→0.985 建议不采纳，避免伤保护机制）。
- **修后 ship 闸两级 PASS**（①≥1 且 ②≥1）。

---

## 4. 修复计划（评审通过，待启动）

按杠杆排序，含回退闸。**用户拍板"先不修"，本计划为后续启动依据。**

| 优先级 | 改动 | 位置 | 回退闸 |
|--------|------|------|--------|
| **P0-1** | 测量层：加 clamp_frac 指标 + dead 改判 `m_v<0.002 ∧ clamp_frac<0.3` + n_active≥20 样本门槛 + 固定 seed 协议（canonical 42 + 5-seed median） | calibrator.py | 还原代码即可 |
| **P0-2** | EASE 决策层：阈值放宽（tightening<0.5/spread<250/grv<0.25）+ TIGHTEN 后 2 步冷却 + 幅度 -0.18→-0.25 | financial.py + simulation.py L141 | 探针 bank_credit std>0.15 即回调 |
| **P0-3** | clamp 对称 [-1,1]（bank_credit+liquidity，照抄 L562-563 em_capital_outflow 模式）| simulation.py L556-565 | 改后 50 步冒烟；对比 liquidity m_v 防锁边 |
| **P1-1** | sentiment 写者结构：A3 SHORT activation 1.0→0.75 或 A1 CUT_25BP +0.20→+0.30（打破负压每步主导 → 不再钉 -1.0）| agents.yaml L47 + simulation.py L122 | 还原参数（注意 08-06 修过 A3 path diversity） |
| **P1-2** | target_scale：修 key bug 或显式禁用；死变量跳过 scale 应用；**不启用 2·m_v 公式** | calibrator.py L163-175/593 | 禁用即回退 |
| **守门** | EPS_TGT=0.03 冻结；验收证据只用新探针 calib_probe.json（禁 calibration_cache）；CACHE_VERSION bump（clamp 对称化/EASE 修复需 bump 4）；每次修复后 git diff 校验测试/断言数不降 | — | — |

### 修复后复测判定口径（验收标准）
1. 固定 seed 协议：探针前 seed RNG 并记录 seed；≥5 seed，取 median 判定。
2. per-var median consistency≥0.60 且 n_active≥20；加权≥60%（死变量不计入加权）；守卫 A/B/C 全过；ρ<|0.3| 自动闸；EASE ship 闸 PASS；CACHE_VERSION bump。
3. 无样本不验收：任一变量 n_active<20 或 m_v<0.002（且 clamp_frac<0.3）→ 不验收，整体不可 ship。
4. 回退闸：预测回归 std>0.15 / 路径B≥15% / 振荡 → D 回 0.12；clamp 对称化后对比 liquidity m_v 防锁边；EASE 修复后验证 tightening 不再锁死 0.97。
5. 反作弊门：每次修复后 git diff 校验测试/断言数不降。

---

## 5. 明确不做（三方一致）

- 不调接受线 / 分层线（调门槛=自证；QA/arch/data 一致）。
- 不放大 A/D（A 已到 1.0 上限 damping 恒 1，D 均匀放大不改变假死机制）。
- 不做 C3 移除 liquidity（隐藏驱动链断裂，永久失去校准价值）。
- 不改 decay 0.97→0.985（decay 是 bank_credit 不死的保护机制）。
- 不启用 T_v=2·m_v 重标定公式（自指退化：sentiment m_v≈0.005 → target≈0.01<EPS_TGT → 步全转 N/U → active 崩、silence 逃逸守卫 A=改门槛自证）。
- 不启用 target_scale 当前实现（key bug 从未生效，修 key 或显式禁用二选一）。

---

## 6. 证据索引（代码基准：macro-sim/core/）

| 证据 | 位置 |
|------|------|
| target_scale 写 nested（唯一写点） | calibrator.py L593-594 |
| target_scale 读顶层 → key 不匹配恒 {} | calibrator.py L169-178 |
| scale 应用点读回恒 1.0 | calibrator.py L163-165 |
| m_v/consistency 仅 T-pairs；active_rate 分母全步 | calibrator.py L578-582 |
| dead=m_v<0.002 无 clamp_frac | calibrator.py L592 |
| EPS_TGT=0.03/EPS_ACT=0.005/DELTA_DEAD=0.05 | calibrator.py L89-93 |
| damping=max(1.0, 1/(1+3|s|)) A 修复 | world_state.py L307-308 |
| decay credit×0.97/lp×0.93 → credit m_v≈0.027=天花板抖动 | world_state.py L313-315 |
| MONTHLY_SCALE=0.25 仅作用于 sentiment | simulation.py L536-539 |
| clamp else 分支 [0,1]；仅 em_capital_outflow 对称化 | simulation.py L556-565 |
| TIGHTEN +0.25×m / EASE -0.18×m 不对称 | simulation.py L134-141 |
| tighten 先判 + ease_signal 三条件（0.15 门槛） | financial.py L68-85 |
| target 推导：sentiment -0.5grv / credit 0.6cs / liquidity 0.4cs+0.3t10y2y∈[-0.7,0.7] | calibrator.py L127-166 |
| snapshot 带 pre-clamp "delta" 字段 | simulation.py L517 |
| A2 threshold=0.5 | config/agents.yaml L38 |
| 旧探针 sentiment target_scale=0.053，"实证系数无尺度依据" | CHANGELOG.md L44 |

---

## 7. R1 后置 Audit 复核纪要（2026-08-08 15:20 追加）

> 审计对象：`~/.qclaw/workspace-knjrc5n1o4zjzm5o/calib-eps-act-review-R1-audit_20260808.md`（Claude/OpenClaw 对本报导的独立审核）
> 审核方式：对照容器内 v2.0.29 实际代码逐条核实（容器=源码区 HEAD，diff=0）
> 本纪要结论：**audit 的代码核实为有效资产（13 项代码事实全部独立确认成立）；但 4 处论断需纠正，其中 A/C 两条不予采纳，防止带偏后续 session。**

### 7.1 Audit 成立项（采纳）

1. **13 项代码证据独立复核全部成立**——target_scale key bug（L175 读顶层 vs L593 写 nested）/ dead 无 clamp_frac / EASE 0.15 门槛 / clamp 仅 outflow 对称 / A3 activation 仍 1.00 / run_probe 无 seed / CACHE_VERSION=3 等。符合"容器内实测、勿信 SMB"铁律。
2. **§0"继续修引擎" vs §4"先不修"表述歧义真实存在**——诊断裁决（引擎需修）与执行决策（本次不启动修复）语义不同但并列易误读。本纪要明确边界：**裁决结论 = 引擎必须修（禁调门槛）；执行状态 = 修复计划冻结待启动；已做 = v2.0.27 S 类挂起 + v2.0.28 C1-1a/C3-3a + v2.0.29 A+D；待做 = P0-1/P0-2/P0-3/P1-1/P1-2**。
3. **N4 rho 观察有价值**——当前 rho sentiment↔liquidity ≈ -0.392 已超 |0.3| 自动闸（v2.0.28 时 -0.586，改善但仍超线）。修复后自动闸可能仍触发，需预案（观测多 seed 分布而非单轮）。
4. **N3 CACHE_VERSION 现值 3** 确认——下次修复 bump 4，方向与报告守门项一致。

### 7.2 Audit 纠正项（4 处）

| # | Audit 论断 | 实测事实 | 处置 |
|---|-----------|----------|------|
| A | "报告基于 v2.0.28 早期代码，当前 v2.0.29 已落地 A/D 修复——报告与代码演进脱节" | **版本搞反**。报告评审的正是 v2.0.29 A+D 修复后的复测（sentiment 0.385→0.54-0.57，seed 42/7/123 三轮）；audit 引用的"05:49 探针 sentiment 0.647"是 v2.0.28 时代旧数据 | **不予采纳** |
| B | 用 05:49 单轮探针数据（sentiment 0.647）作"当前状态"复核 | 违反评审裁决第 3 条：探针有随机性、单次不可信、须多 seed 取 median。单轮 0.647 不能作为状态证据 | **方法学错误，不予采纳** |
| C | "修复前先定是否接受 0.60 门槛，否则修完仍可能 FAIL" | 接受线 0.60 **已冻结**（三方一致：调门槛=自证，EPS_TGT=0.03 冻结）。"是否接受"早已定案=接受并冻结，修引擎达标 | **与终局裁决相悖，明确否定** |
| D | N1"QA 独立报告 NAS 上不存在" | 文件在 WorkBuddy 本地：`C:\Users\luoxi\WorkBuddy\世界推演系统\calib-eps-act-review-qa-R1-2026-08-08.md`（13:52，5881B）。评审文档按既有约定放本地工作区（calib-c1c3-review 终局裁决同样在本地），audit 只在 NAS find 找不到即断言缺失=查找位置错误 | **定位错误，非文件缺失** |

### 7.3 版本边界（防后续 session 误判）

- **已落地**：v2.0.27（S 类挂起）→ v2.0.28（C1-1a delta 口径 + C3-3a outflow 移除 + 三守卫 + run_probe 探针 + target_scale 重标定框架）→ v2.0.29（A=1.0 damping + D=MONTHLY_SCALE 0.25 + A2 写者补丁 + EASE 定向探针 + silence_frac，CACHE_VERSION 2→3）。
- **待启动**（§4 计划）：P0-1 测量层（clamp_frac + dead 改判 + n_active≥20 + 固定 seed）→ P0-2 EASE 决策层（阈值放宽 + 冷却 + 幅度对称）→ P0-3 clamp 对称 [-1,1] → P1-1 sentiment 写者结构 → P1-2 target_scale 修 key/禁用。
- **OPEN-DECISIONS 待决**：EASE ship 闸 FAIL（issue ③，blocked by 对称化修复）+ 接受线未达（blocked by ε_act 团队决议）。ε_act=0.005 已有 C1-1a 评审裁决在先，启动 P0 前应关闭此未决项。
