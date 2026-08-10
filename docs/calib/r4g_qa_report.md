# R4g 阶段一 · QA 评审交付（qa-r4g）
归因拆分可验证性评审 + R4g 验收口径草案 + 改冷却反作弊风险 + 断言核对表 + 归因→决策闸门

> 只读调研（未改任何源码/工件）；复算脚本在临时目录 C:\tmp\r4g_qa\（不入库）。
> 数字口径：除注明外均来自 output/calib_probe_seed*_v2030c.json 落盘工件复算（与 acceptance_v2030c.json 逐位一致）。

---

## RoleVerdict

**verdict**：归因拆分方向正确（必须先归因后决策），但**当前落盘的 S 类三分类归因不可直接采信**——存在字段-代码映射缺陷（决策层 HOLD 被误标 acted_other，rule_hold 结构性不可达），导致「改冷却 vs 改结构」的证据链不闭合。R4g 阶段一必须先修归因映射 + 补完整 steps 口径，再谈阶段二。

**blocking**（3 项，P0 级，阶段一验收前必须解决）：
1. **归因映射缺陷**：`simulation.py:521` snapshot["actions"] 只滤 NO_ACTION、**保留 "HOLD"**；`calibrator.py:699` `a2_acted=bool(actions["A2"])` 对 HOLD 决策为 True → classify_a2_state 把「过激活门但决策 HOLD」误标 acted_other，`tighten_signal_false`（rule_hold）**结构性不可达**，五 seed 恒报 0.0。已实证：credit S 类 acted_other 步 10/10 的 d==0（必为 HOLD）。修正后 rule_hold = 0.0–0.13（median 0.115），**非 0.0**。
2. **口径缺口**：现有 s_class_attribution 只在 S 类子集（|t|≥EPS_TGT ∧ |d|<EPS_ACT）上算占比，R4g 要求的完整 steps 三类占比未落盘。S 类口径高估 rate_limit：full-step median 0.388 vs S 类 median 0.652（**高估 +0.264**）——R4f 归因伪影警告量化确认。
3. **act 天花板现实**：credit per-seed n_active 全 seed <20（16/14/14/17/16）→ 闸④ per-seed 口径下 credit 全 seed 不入池（per-seed weighted 实际只含 sentiment+lp）。info_delay=1 下 act 理论上限 ≈0.41（=0.70/(1+0.70)），实测 0.33 已接近；仅靠 EASE 冷却 2→1 无法把 per-seed n_active 抬到 ≥20，**须同时动 info_delay 或 activation**——这触碰 test_a2_info_delay_r4b 锁定断言，属规格变更登记，非反作弊违规，但必须事前声明。

**advisory**：当前证据下 rule_hold（修正后 median 0.115）**不主导**，不触发「升级三方+总监」分支；但这是基于 R4e 工件 + 我修正映射后的估计，正式结论以 R4g 阶段一修正归因后的完整 steps 占比为准。若修正后 rule_hold 主导 → 按 R4f 终裁 §4.3 升级，QA 姿态见 §5。

**evidence**：见 §1.1（复算表）、§1.2（映射缺陷实证）、§1.3（口径对比）、§4（断言清单）。

---

## 1. 归因拆分可验证性标准

### 1.1 我复算的基线（判定证据，全部与落盘工件一致）

| seed | credit silence | credit cons | credit n_active | credit act | per-seed weighted |
|---|---|---|---|---|---|
| 42 | 0.49 | 0.562 | 16 | 0.327 | 0.4560 |
| 7 | **0.531** | 0.714 | 14 | 0.286 | 0.5345 |
| 123 | **0.531** | 0.500 | 14 | 0.286 | 0.4809 |
| 2024 | 0.469 | 0.471 | 17 | 0.347 | 0.5403 |
| 777 | 0.49 | 0.688 | 16 | 0.327 | 0.4783 |

merged：p̂=0.5152，N=161.7，K=83.3，CI 下限=0.4387，eligible 池=3 变量。闸 1 硬 FAIL：seed7/123 silence 0.531>0.50。

### 1.2 归因结论可信的验收标准（阶段一必须全部满足）

1. **字段-代码映射闭合**：`a2_state` 字段 → `classify_a2_state` 纯函数 → step_record 落盘 → 验收脚本读取，四环语义一致，且 **a2_acted 必须排除 HOLD**（`a2_acted = actions.get("A2") not in (None, "HOLD", "NO_ACTION")`）。验收方法：对 credit S 类 acted_other 步断言 d==0 占比=100%（当前即此现象，但被当成"写其他 var"，实为 HOLD）→ 修映射后 acted_other 对 credit 应≈0，HOLD 步归 rule_hold。
2. **逐 seed 三类占比可复现**：三类占比必须逐 seed 落盘（非仅 median），且验收脚本可从 steps 重算得到同值（当前 s_class_table 即逐 seed，可复现——保持该模式）。
3. **口径注明**：必须同时给出两种分母并显式标注：
   - **S 类口径**（现状，=silence 子集）：rate_limit/activation_gate/rule_hold 占 S 类步比例；
   - **完整 steps 口径**（R4g 新增）：三类占全部 delta 步比例 + 单独报「已行动（写 credit）」占比。
   不得只报一种，防止 S 类高估 rate_limit（+0.264）误导「改冷却」杠杆。
4. **EASE 方向一致率有数字**：每 seed 报 EASE 决策步中 d_credit<0（方向正确）占比、tighten_fail（方向闸后仍收紧）占比、EASE→TIGHTEN 振荡率。当前 directional_ease_trigger 只报触发率（0.125–0.292），未报 EASE 步方向正确率——补。
5. **rule_hold 不再恒 0**：修正映射后 rule_hold 必须可测（我修正后 0.0–0.13），若仍恒 0 说明映射未修或 HOLD 决策计数仍有漏。

### 1.3 打回标准（阶段一结论不足以支撑「改冷却/改结构」决策时）

任一命中即打回 data-r4g/arch-r4g 重做归因：
- A. a2_acted 语义未排除 HOLD（rule_hold 仍结构性不可达 / acted_other 仍含 HOLD 步）；
- B. 完整 steps 口径未落盘（只有 S 类占比）——无法回答「全步中冷却占比多少」；
- C. 三类占比未逐 seed（只有 median）——重演 R4f「median 掩盖 per-seed 硬闸」教训；
- D. EASE 方向一致率无数字——无法判断改冷却是否损方向质量；
- E. 归因结论与步骤数据不一致（验收脚本重算 ≠ 报告数字）。

---

## 2. R4g 验收口径草案（阶段二实施修复后）

**沿用 5 seed fail-fast（42/7/123/2024/777），闸序不变；partial 线 0.55 维持；weighted 0.60 冻结禁调；不冻结 credit 权重；EPS_TGT 0.03 冻结；断言数 102 不降；CACHE_VERSION 10→11（改引擎必 bump）；--read-only 只读验收；禁 calibration_cache 自证。**

闸序（同现状 + 归因联合判定）：
1. dead/silence 硬闸：逐 seed silence≤0.50（seed7/123 现 0.531，修复后必须 ≤0.50）→ 硬 FAIL
2. 合并 CI 下限 ≥0.55（partial，维持）
3. 合并点估 p̂≥0.60（达标线，冻结）
4. per-seed weighted ≥0.50（credit 需先入 per-seed 池：n_active≥20，见 §1.1 天花板）
5. 回退线 5 条：credit_consistency ≥0.60（<0.40 revert）/ grv_down ≥0.40（<0.20）/ merged_p ≥0.55（<0.43）/ credit_n_active ≥18 / credit_silence ≤0.50

**新增监测（机读落盘，禁散文）**：
- M1 EASE 步方向一致率（逐 seed）：EASE 决策中 d_credit<0 占比 / tighten_fail 占比 / EASE→TIGHTEN 振荡率
- M2 per-seed silence diff vs R4e（Δ 逐 seed，非 median）
- M3 rate_limit 占比前后对比（完整 steps 口径、修正映射后）：改冷却前 vs 后
- M4 flip-flop 监测：EASE 后冷却窗口内出现 TIGHTEN 的步数（防「放宽换活性损质量」重演）
- M5 credit consistency 逐 seed（R4e 教训：median 0.562 掩盖 0.471–0.714 方差）

**p̂ 预期区间（诚实估计）**：仅冷却类放宽（不改一致性结构）→ p̂ 大概率 0.53–0.57，**仍 <0.616 达标线**，可能刚过 0.55 partial。参照：R4b info_delay 2→1 曾 +0.12 活性但暴露方向冲突；R4d→R4e merged p̂ 0.477→0.5152。**结论：冷却修复主要解「闸 1 silence + n_active」，不足以独立解「接受线」；若 p̂ 仍 <0.616，须接受 partial 或另立结构性方案，不得调门槛。**

---

## 3. 「改冷却」反作弊风险

**两个候选冷却，风险不同：**

| 候选 | 触碰断言 | 风险 |
|---|---|---|
| A. info_delay 1→0（activation_countdown 行动后=info_delay） | **FAIL test_a2_info_delay_r4b**（锁定 info_delay==1） | 高：①act 上限 0.41→0.70，silence 大降但 EASE/TIGHTEN 频率翻倍，flip-flop/方向冲突风险↑；②info_delay=0 违背 base.py:158 taxonomy（0=即时=对冲基金/散户，商业银行=1）；③visible_actions 感知延迟变 0 → 收紧触发大增，方向闸压力↑ |
| B. EASE 冷却 `_ease_cooldown` 2→1 或条件化（financial.py:108） | **不 FAIL 任何现有断言**（无直接锁定该值） | 中：EASE 后 flip-flop 保护减弱（P0-2 振荡史 v2.0.1），若改条件化（如仅高压下冷却）会改 `_decide_rules` 分支序 → **可能 FAIL test_directional_ease/test_direction_gate/test_ease_layer1_ctx**（共享 a2 实例内 _ease_cooldown 状态残留，需逐条重验） |

**「放宽换活性损质量」重演风险（R4e 教训：grv 放宽 consistency 0.643→0.562）**：冷却放宽换 silence/n_active 下降，极可能重演「活性↑ 一致率↓」。事前防护：
1. 修复前后必须同窗口对比 credit_consistency（逐 seed + median），回退线 credit_consistency <0.40 立即 revert（机读已具备）；
2. 新增 M4 flip-flop 监测（EASE→TIGHTEN 振荡）作为阶段二新回退线候选（target=0，revert>某阈值）；
3. 任何冷却改动 = 引擎动力学改变 → **CACHE_VERSION 10→11 强制**，禁复用 v10 缓存；
4. 断言更新走**规格变更登记**（非反作弊违规），但断言总数 90+12=102 不得下降；禁加 skip/.only。

---

## 4. 断言与测试现状核对（tests/test_calibrator_guards.py = 90 断言；test_narrative_format.py = 12；合计 102）

| 测试函数 | 断言数 | 与 R4g 相关度 | 若改冷却/ease 会怎样 |
|---|---|---|---|
| test_eligibility_classes | 6 | 低（EPS 边界） | 不受影响 |
| test_extract_preclamp_delta | 5 | 低 | 不受影响 |
| test_eligible_for_weighted | 4 | 中（silence≤0.50 入池） | 不受影响 |
| test_weighted_exclusion_math | 1 | 中 | 不受影响 |
| test_guard_a_pass_and_fail | 3 | 低 | 不受影响 |
| test_guard_b_collapse | 4 | 低 | 不受影响 |
| test_guard_c_bands | 3 | 低 | 不受影响 |
| test_a2_grv_trigger_contract_line | 3 | 中（决策规则） | 改 _decide_rules 分支序时需重验 |
| test_a2_spread_trigger_unchanged | 1 | 中 | 同上 |
| test_ease_layer1_ctx | 1 | **高**（EASE 可达性） | 改 EASE 冷却条件化需重验 |
| test_classify_a2_state | 5 | **高**（三分类语义） | **改 a2_acted 映射（排除 HOLD）必须同步改此测试的输入语义**——规格变更登记 |
| test_s_class_attribution_mapping | 4 | **高**（S 类计数） | 同上，映射修复后重验 |
| test_a2_info_delay_r4b | 3 | **最高**（锁定 info_delay=1/activation 0.70/threshold 0.5） | **改 info_delay 或 activation → 必 FAIL，需规格变更登记** |
| test_dead_new_semantics | 7 | 低 | 不受影响 |
| test_activity_band | 5 | 低 | 不受影响 |
| test_merged_eligible | 3 | 中 | 不受影响 |
| test_direction_gate | 8 | **高**（方向闸） | 改 _decide_rules 分支序需重验 |
| test_directional_ease | 9 | **高**（方向 EASE 阈值） | 改 EASE 分支需重验（共享 a2 实例 _ease_cooldown 残留，注意） |
| test_ease_block_reason | 5 | 中 | 改挡死条件需重验 |
| test_rollback_line_constants | 6 | 中 | 不动 |
| test_layer1_ctx_handwritten_constraint | 4 | 中 | 不动 |

**关键结论**：
- `_ease_cooldown=2`（financial.py:108）**无任何测试直接锁定** → EASE 冷却 2→1 不 FAIL 现有断言；
- `info_delay=1` 被 test_a2_info_delay_r4b **直接锁定** → info_delay 改动必须规格变更登记（同步改断言，计数不降）；
- **归因映射修复（a2_acted 排除 HOLD）会改变 test_classify_a2_state / test_s_class_attribution_mapping 的输入语义**——这是 R4g 阶段一必改项，属规格变更登记范畴，非反作弊违规，但必须事前声明 + 断言数不降。

---

## 5. 归因→决策闸门定义（决策树草案）

```
R4g 阶段一归因产出（修正映射 + 完整 steps 口径 + 逐 seed + EASE 方向一致率）
        │
        ├─ 可验证性检查（§1.2 五条）不满足 ──────────→ 打回 data/arch 重做归因（不进入阶段二）
        │
        ▼ 满足
  完整 steps 三分类占比（修正后）+ EASE 方向一致率
        │
        ├─ 分支 A：rule_hold（决策层 HOLD）主导 ──→ 【升级裁决】三方+总监重新审视
        │     （如 rule_hold ≥ S 类 50% 或完整口径 ≥ 40%，机读阈值待 data/arch 定稿）
        │      QA 姿态：不阻塞升级本身（裁决权事件）；要求①裁决以机读证据落盘非散文
        │      ②评审期间 weighted 0.60 冻结、禁止临时放宽③若裁决方向闸改动，先重跑归因再进阶段二
        │
        ├─ 分支 B：rate_limit（冷却）主导 ─────────→ 阶段二候选①：EASE 冷却 2→1/条件化
        │     反作弊预检：断言不降（90+12）·CACHE_VERSION 11·规格变更登记（如有）
        │     → 阶段二验收（§2 口径 + M1-M5）→ p̂≥0.616 达标 / ≥0.55 partial / 否则继续
        │
        └─ 分支 C：activation_gate（随机门）主导 ──→ 阶段二候选②：activation_prob 上调
             （触碰 test_a2_info_delay_r4b activation 0.70 断言 → 规格变更登记）
             同验收口径；注意 activation 改动 = 隐性「调参数」风险，须附 EASE 方向一致率证据
```

**收敛判据落点**：当前证据（修正后 rule_hold median 0.115，rate_limit 0.652 S 类 / 0.388 全步）指向分支 B（冷却主导），**不触发升级**；但以 R4g 阶段一修正映射后的完整 steps 占比为准。若分支 A 触发，QA 建议验收姿态：阶段二暂停，只做裁决证据整理，不先行改冷却。

---

## 附：复算脚本（临时目录，已执行）

- C:\tmp\r4g_qa\r4g_attribution_analysis.py —— 口径对比（S 类 vs 完整 steps）
- C:\tmp\r4g_qa\r4g_mapping_verify.py —— 映射缺陷实证 + 修正归因
- 复算 merged/per-seed 数值与 acceptance_v2030c.json 逐位一致（p̂=0.5152 / N=161.7 / CI=0.4387 / per-seed weighted 全对）
