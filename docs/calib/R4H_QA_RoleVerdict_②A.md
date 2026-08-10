# R4h ② vix 治理独立验收 RoleVerdict（qa-r4h2，2026-08-09）

> 验收对象：macro-sim v2.0.39（R4h ②-A：vix 均值回归 0.80/0.20 + yen_carry bleed 封顶 19 + CACHE 13）
> commit: 2276b1d（+bc32f9d docs 回填）；ARTIFACT_TAG=v2032；断言 120
> 环境：SSH nas + docker exec macro-sim（镜像 c25df8907519，最新）；前台同步；探针落盘 /tmp/r4h_qa_v2032（**未污染 repo output/**）
> 对比基线：v2.0.38（③-A 后，qa-r4h2 实测，③ 已并入保留）
> 反作弊：--read-only 同源判定；CACHE=13 生效；断言 120 独立重跑全绿；无 skip/.only；output/ 无 v2032 落盘

## RoleVerdict

- **verdict: FAIL**
- 一句话：**② 裁决闸 M6 已清（16≤17 PASS），M2 防恶化线 PASS，③ 回归全确认——但标准五闸 FAIL（silence 4/5 超线，M2 容差内）+ p̂ 0.4948 未过 partial + S2 warn 0.682 未达达标线 → 整体仍未过合并验收**
- **"② 是否清 M6 闸"独立判定：PASS（TIGHTEN wrong 总数 16 ≤ 17）** ✅
- **p̂ 落档：未过（0.4948 < 0.55 partial 线）**；且较 ③-A 后 0.5094 再降 -0.015（credit 出池结构性代价，advisory）

## 一、git show 2276b1d 逐行核验（trust but verify）

| 项 | 结果 | 说明 |
|----|------|------|
| world_state.py L267 BLEED_PARAMS `vix_yen_carry_bleed_max: 19.0` | ✅ | 新增参数，注释含参数扫描论证（cap<19→M2 超 / cap>19→wrong 超 17） |
| world_state.py L301-309 出血5 封顶 `vix_delta_total < max` | ✅ | `vix_delta_total=world.vix-world.vix_baseline` 前置定义（L278），与出血1 同语义；yen_carry 真危机 +5.0 保留 |
| world_state.py L351 vix 均值回归 `vix*0.80 + baseline*0.20` | ✅ | 与 D4 其余变量同语义；注释完整 |
| **涉改范围：仅 vix 相关** | ✅ | apply_bleed_rules 只改出血5 条件、apply_natural_decay 只加 vix 回归、BLEED_PARAMS 只加参数——**未动 sentiment/credit/grv 其他变量**（arch 声明真实） |
| **P0：core/ 无 sentiment>-0.3 前提** | ✅ | grep 空（容器+本地双查） |
| calibrator.py CACHE_VERSION 12→13（L134） | ✅ | bump 理由正确（引擎动力学变更防 v12 缓存自证） |
| VERSION v2.0.38→v2.0.39 | ✅ | |
| run_probe_acceptance.py ARTIFACT_TAG v2031→v2032（L69）+ acceptance_v2032.json | ✅ | |
| tests +6 项（vix_decay_mean_reversion / no_drift_at_baseline / yen_carry_bleed_capped / active_below_cap / a2_tighten_exemption_gate / vix_stress_active_band） | ✅ | 实质断言（非空/非硬编码/非 skip），覆盖新机制触发条件 + 与 ③ 共存 |
| financial.py +2/-1 仅注释 | ✅ | A2 决策逻辑零改动 |
| ⚠️ **P2-1：CACHE bump 注释参数过期** | ⚠️ | calibrator.py L134 注释写"vix 均值回归 0.85/0.15 + vix_delta<12"，实现是 0.80/0.20 + <19——注释与实现不符（可能是参数扫描中间版本残留），记录 P2（不影响行为） |
| ⚠️ **P2-2：arch commit message 与最终实测不符** | ⚠️ | commit 注释"seed42 silence +0.061"，最终实测 +0.020（arch 自报探针也是 +0.020）——commit message 为参数扫描中间值，记录 P2 文档质量 |

## 二、断言 120 独立重跑（Phase 3）

- ✅ guards 30 组 / **108 assert** + narrative 11 组 / **12 assert** = **120 assert** 全绿（0 fail 0 error）
- ✅ 新增 6 项全部通过（vix_decay_mean_reversion ✓ / no_drift_at_baseline ✓ / yen_carry_bleed_capped ✓ / active_below_cap ✓ / a2_tighten_exemption_gate ✓ / vix_stress_active_band ✓）
- ✅ 无 skip/.only/xfail/focus 新增；断言 113→120 增加（非减少）

## 三、五闸逐 seed（② v2.0.39 vs ③-A 后 v2.0.38）

| seed | silence ③→② | n_active | act | consistency ③→② | weighted |
|------|------------|----------|-----|-----------------|----------|
| 42 | 0.490→**0.510** (+0.020) | 15 | 0.306 | 0.500→0.533 (+0.033) | 0.443 |
| 7 | 0.531→**0.571** (+0.040) | 12 | 0.245 | 0.714→0.583 (**-0.131**) | 0.530 |
| 123 | 0.531→**0.551** (+0.020) | 13 | 0.265 | 0.500→0.538 (+0.038) | 0.458 |
| 2024 | 0.469→**0.510** (+0.041) | 15 | 0.306 | 0.471→0.533 (+0.062) | 0.540 |
| 777 | 0.490→0.490 (0.000) | 16 | 0.327 | 0.688→0.688 (0.000) | 0.486 |
| **median** | **0.490→0.510** | 15 | 0.31 | **0.500→0.538** | 0.486 |

- **merged p̂=0.4948**（③-A 后 0.5094，-0.0146）；Wilson CI 下限 **0.4118**；N=135.0（③-A 后 161.55）
- **eligible 池 = ['market_sentiment','liquidity_premium']（credit 出池！）**——merged_eligible 判定（median silence≤0.50）：② 后 credit median silence 0.51 >0.50 → 出池
- 闸① silence：4/5 seed 超 0.50 → FAIL；闸② CI 0.4118 <0.55 → FAIL；闸③ p̂ 0.4948 <0.60 → FAIL；闸④ per-seed weighted 全 <0.50 → FAIL（基线既有）；闸⑤ 回退线 5 条全 warn（credit_consistency 0.5385 / grv_down 0.318 / merged_p 0.4948 / credit_n_active 15 / credit_silence 0.5102）

## 四、硬闸判定（② 裁决）

| 闸 | ③-A 后 | ② 后 | 判定 |
|----|--------|-------|------|
| **M2** silence diff（防恶化线 ≤+0.05） | 全 0.000 | **+0.020/+0.040/+0.020/+0.041/0.000 全 ≤+0.05** | ✅ **PASS**（[a] 判断：② 恶化但全在容差内，seed42/2024 升幅 +0.02/+0.041 均未超线） |
| **M4** flip | 0 | **0** | ✅ **PASS** |
| **M5** credit consistency | 0.500 | **0.538**（+0.038 改善） | ✅ **PASS**（≥0.45） |
| **M6** TIGHTEN wrong | 18 | **16（42:4/7:5/123:3/2024:3/777:1）** | ✅ **PASS（② 清闸，16 ≤ 17）** |
| **S2** grv_down reverse | 0.682 | **0.682（持平，未突破）** | ⚠️ warn（未达 ≤0.60 达标线，未触发 ≥0.727 FAIL） |

- **M6 逐 seed + 豁免明细**（[b]）：
  - 42: 4 步（i=34/36/42/47，vix 48.5-53.0，stress 1.02-1.17）全豁免
  - 7: 5 步（i=16/21/27/35/46，vix 50.98-53.27，stress 1.10-1.18）全豁免——**③-A 后 3 → 5（+2）**，seed 内转移
  - 123: 3 步（i=34/41/47，stress 1.09-1.15）全豁免（③-A 后 4 → 3）
  - 2024: 3 步（i=41/45/47，stress 1.02-1.15）全豁免（③-A 后 5 → 3）
  - 777: 1 步（i=36，stress 1.17）全豁免（持平）
  - **exempt_pct 仍 100%（16 步全 vix_stress>1.0 豁免）；非豁免 wrong = 0（全 seed）**——"部分开"体现在 vix>48 步数减少（23-38→21-36）而非 wrong 步豁免率下降；advisory 记录（按裁决口径不触发 FAIL）

## 五、② 专项（Phase 6）

| 项 | ③-A 后 | ② 后 | 判定 |
|----|--------|-------|------|
| 豁免占比 | 100% | **仍 100%**（wrong 步 vix_stress 1.02-1.18 全豁免） | advisory（"部分开"=vix>48 步数减少，非 wrong 豁免率下降） |
| 非豁免 wrong | — | **0（全 seed）** | advisory（无"现形"wrong） |
| vix>1.0 步数 | 中位 24（23-38） | **中位 22（21-36，seed7 38→36）** | ✅ 未恶化 |
| vix 峰值 | 162-238 | **53.28-53.38** | ✅ **大幅收敛** |
| vix_stress_final | vix_last=162-238 | **vix_last 50.56-52.42（< vix_max，有回落）** | ✅ 回落 |
| bleed 判据 | 无封顶，vix 存量锁边 | yen_carry 封顶生效（vix_delta<19），vix 在 baseline+19≈47-53 震荡（非清零） | ✅ 封顶生效；存量非零（yen_carry_risk 持续 >0.7 触发 bleed） |

## 六、③ 回归确认（Phase 5，③ 保留前提下 ② 不得破坏）

| 项 | ③-A 后 | ② 后 | 判定 |
|----|--------|-------|------|
| S1 桶无 ≥0.5 尖峰（主探针） | ge05 0（max<0.22） | **ge05 全 0（max<0.22，floor 0.66/mean -0.861 持平）** | ✅ 无破坏 |
| EASE wrong | 9 | **8（不增反降）** | ✅ 不增 |
| tsf 非零 | 2/4/3/4/5 | seed42 tsf 4、seed7 tsf 3（全 seed 非零） | ✅ 未归零 |
| a2_action 落盘仍在 | L735 | **L738 仍在** | ✅ |
| EASE +0.08×m 保留 | simulation.py L152 | **L152 保留** | ✅ |
| M4 flip | 0 | 0 | ✅ |

## 七、M7 观察（无硬闸）

- A1/A3 分布：与 ③-A 后基本一致（A1 CUT 5-6 步、A3 INC/SHORT/DEC/HOLD 均衡）——② 未破坏其他 agent 行为
- vix 存量：峰值 162-238→53.28；vix_stress>1.0 步 21-36；vix_last<vix_max（存量开始回吐，但幅度小）

## 八、p̂ 落档 + 结构性变化（[c] 独立判断）

- p̂=0.4948 < 0.55 partial → **未过**；CI 下限 0.4118
- **结构性变化：credit 出池**（eligible_pool 3→2、N 161.55→135.0）——② 后 credit silence 4/5 超 0.50 → merged_eligible（median silence≤0.50）不过 → credit 从测量池消失。这不是随机噪声，是 ② 的 wrong-silence trade-off 结构性代价（vix 封顶→A3 vix 触发减→hf SHORT 减→A2 行动减→credit silence 升）
- 判断：② 目标非 merged 提升（arch 声明）；p̂ 未过是**基线既有**（v2.0.37 起 0.5152→③ 0.5094→② 0.4948 全程未过 partial 0.55）+ **② 引入 credit 出池的结构性稀释**。按合并验收口径：不单批判 FAIL，但 advisory 标注结构性变化（credit 沉默 trade-off 需在后续方向闸治理中关注）

## 九、差异标注（与 arch 自报对比，实测为准）

| 项 | arch 自报 | qa-r4h2 实测 | 一致性 |
|----|-----------|-------------|--------|
| M6 总数 | 16（42:4/7:5/123:3/2024:3/777:1） | 16（同） | ✅ 一致 |
| M2 silence diff | +0.020/+0.040/+0.020/+0.041/0.000 | 同 | ✅ 一致 |
| vix 峰值 | 53.2-53.4 | 53.28-53.38 | ✅ 一致 |
| vix_stress_final | 1.13-1.18 | wrong 步 1.02-1.18 | ✅ 一致 |
| S2 reverse | 0.682 持平 | 0.682 持平 | ✅ 一致 |
| merged p̂ | 0.4948 | 0.4948 | ✅ 一致 |
| credit consistency median | 0.500→0.538 | 0.538 | ✅ 一致 |
| EASE wrong | 9→8 | 8 | ✅ 一致 |
| **arch 未强调：credit 出池** | 未提 | **eligible_pool 3→2、N 161.55→135.0** | ⚠️ 补充 |
| **arch 未强调：seed7 M6 +2** | 未提 | **seed7 wrong 3→5（seed 内转移，总 16 达标）** | ⚠️ 补充 |
| **arch 未强调：exempt_pct 仍 100%** | "豁免部分开" | **wrong 步仍 100% 豁免（非豁免=0）** | ⚠️ 补充（"部分开"=vix>48 步数减少，非 wrong 豁免率下降） |
| commit 注释 seed42 silence +0.061 | 中间值 | 实测 +0.020 | ⚠️ P2 文档 |

## 十、advisory（供 team-lead 合并验收）

- [1] **② 裁决闸达成**：M6 16 ≤17 清闸（核心目标），M2 防恶化线 PASS（全 ≤+0.05），③ 回归全确认（S1 无尖峰/EASE wrong 8 不增/tsf 非零/a2_action 在/EASE 保留）——**② 治理有效且未破坏 ③**
- [2] **S2 仍未达达标线（0.682 warn）**：② 治理对象是 vix（M6），非 sentiment（S2）；S2 reverse 0.682 持平 ③-A 后，仍 >0.60 达标线——③ 核心目标（sentiment 抬离 floor→grv_down 方向一致率）仍未达成，需方向闸治理单独跟进
- [3] **结构性代价**：credit 出池（silence 升→merged_eligible 不过）→ p̂ 0.4948、N 缩小 16%——② 用 credit 沉默（wrong-silence trade-off，arch 声明的最优点）换 M6 收敛；此 trade-off 使 merged p̂ 结构性下降，合并验收时需纳入（不能只看 p̂ 数值）
- [4] **seed7 M6 wrong 3→5（+2）**：wrong 在 seed 间转移（vix 轨迹变化）；总数 16 达标但 seed7 单 seed 恶化，advisory 标注（5 步全豁免）
- [5] **豁免占比仍 100%**：wrong 步 vix_stress 1.02-1.18 刚过 1.0 线（vix 48-53 震荡）——"豁免部分开"是时间占比（vix>48 步数减少）非 wrong 豁免率；若后续要更强收敛需降 vix 触发线或继续降 cap（但 cap<19 会 M2 超线，当前为 Pareto 最优点）
- [6] **P2 缺陷 2 项**：CACHE bump 注释参数过期（0.85/0.15、<12 vs 实现 0.80/0.20、<19）；commit message seed42 silence +0.061 vs 实测 +0.020——建议 arch 回填修正（不影响行为）

## 十一、evidence

- 容器：/tmp/r4h_qa_v2032/{calib_probe_seed{42,7,123,2024,777}_v2032.json, acceptance_v2032.json}；/tmp/r4h_qa_result2.txt；/tmp/r4h_qa_sent3_result.txt；/tmp/r4h_qa_analyze2.py；/tmp/r4h_qa_sent3.py
- 本地：C:\tmp\r4h_data\R4H_QA_RoleVerdict_②A.md；C:\tmp\r4h_data\R4H_QA验收清单_③②.md
- 基线对照：C:\tmp\r4h_data\R4H_QA_RoleVerdict_③A.md（③-A 后 v2.0.38，② 的 diff 基准）
- 代码核验：git show 2276b1d（world_state.py/calibrator.py/run_probe_acceptance.py/tests/VERSION/financial.py）
- 反作弊：容器镜像 c25df8907519（docker inspect 确认）；CACHE=13 grep；断言 120 本地重跑；output/ 无 v2032 落盘
