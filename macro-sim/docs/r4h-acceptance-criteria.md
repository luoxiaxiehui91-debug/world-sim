# R4h 验收口径定稿（qa-r4g · 机读可执行）

> 文档类别：验收口径定稿（ACCEPTANCE CRITERIA FINAL）· 由 qa-r4g 产出
> 基线：v2.0.37（R4e 引擎 + 归因映射①，R4g 收尾态）；对照工件：`output/r4e_backup_v2030c/`
> 状态：**设计轮定稿，不跑验收**（引擎未改）；待 arch 实施 R4h 增长点①-③后由 qa 按本文档全量验收
> 前置提交依赖：`docs/r4g-spec-change-registry.md`（R4g 规格）、`docs/r4h-design-draft.md`（arch 方案）

---

## 0. 铁律（沿用 R3-R4g + R4g 教训固化）

1. **验收证据只用新探针 5 seed median**（禁 calibration_cache；禁散文/CHANGELOG 作判定输入）
2. **判定只读落盘工件**：`output/calib_probe_seed{seed}_v2031.json` + `output/acceptance_v2031.json`（R4h 新 tag，见 §6）
3. **fail-fast**：任一硬闸 FAIL → 整体 FAIL，输出 p̂/CI/违规 seed/变量/监控项
4. **冻结常量（禁调）**：partial 接受线 0.55、weighted 目标 0.60、EPS_TGT=0.03、5 seed={42,7,123,2024,777}
5. **归因双报为强制项**（R4g 教训①，见 P2）：S 类口径 + 完整 steps 口径必须同时落盘，禁只报一种
6. **「放宽换活性损质量」为硬闸**（R4g 教训⑤，见 M5）：任何 seed consistency 跌破底线 → FAIL

---

## 1. 前置检查（判定前必过；任一 FAIL → 终止，不进入闸序）

### P1 · a2_acted 映射语义正确性（R4g 教训②）
- 目的：确认新引擎落盘归因仍符合 R4g 修复①语义（HOLD 决策步 → `tighten_signal_false`，**不得**归 `acted_other`）
- 机读断言（对 5 seed 新工件逐条）：
  ```python
  assert all(rec["a2_state"] != "acted_other"
             or rec["a2_action"] in ("EASE_CREDIT", "TIGHTEN_CREDIT", "SHORT_CREDIT")
             for sd in seeds for rec in probes[sd]["raw"]["steps"])
  # 即：a2_state=='acted_other' 的步必须有实质行动；HOLD 决策步必须归 tighten_signal_false
  ```
- 人工抽查：任取 1 seed，抽 3-5 个 `a2_state=='tighten_signal_false'` 步，核对 A2 决策确为 HOLD（非 EASE/TIGHTEN）
- **前置依赖（arch）**：`core/calibrator.py` step_record 增加 `a2_action` 字段（snapshot actions 的 A2 原值；测量层，不改引擎决策、无 CACHE bump 必要）。当前工件无此字段 → P1 需在 arch 落盘后执行

### P2 · 归因双报强制（R4g 教训①）
- S 类口径：`|t|≥EPS_TGT ∧ |d|<EPS_ACT` 步，按 a2_state 四分类占比（`per_var.s_class_attribution` 已落盘）
- 完整 steps 口径：**全部步**按 a2_state 四分类占比（从 steps 重算，`steps` 已落盘 a2_state）
- 两者必须都进 `acceptance_v2031.json` summary；**只报一种 → P2 FAIL**
- 依据：R4g 教训——只报 S 类会高估 rule_hold（S 类 tsf 0.105-0.296 vs 完整 0.041-0.163），只报完整会低估方向闸代价；双报才可判「rate_limit 占比前后」的真伪

### P3 · 反作弊门（沿用 R4g）
- 断言总数 ≥ 110 且**不降**（guards 98 + narrative 12 为 R4g 基线）；测试 diff 禁删断言/加 skip/xfail/.only/focus
- 引擎改动必须 bump `CACHE_VERSION`（当前 11 → 12）与 `VERSION`（当前 v2.0.37 → v2.0.38+）
- 规格变更登记必须存在且覆盖本次全部改动（含 revert/新增）
- 验收首轮必须全量新探针（非 `--read-only` 复用旧工件）

### P4 · ARTIFACT_TAG 必须 = `v2031`
- 禁复用 v2030c（R4g 教训④：v2030c 在 R4g 实验期/收尾期复用造成 era 混淆）
- 新工件命名：`calib_probe_seed{seed}_v2031.json`、`acceptance_v2031.json`
- 对照基线：`output/r4e_backup_v2030c/`（R4e 五 seed 工件完好，M2/M5/S2 全部对照它）

---

## 2. 主闸序（沿用 R3-R4g，fail-fast）

> 代码路径：`scripts/run_probe_acceptance.py` `evaluate()` L330-462 + `main()` L551-615（R4h 版）

| 闸 | 判定 | 代码路径（现行） |
|---|---|---|
| ① dead/silence 硬闸 | 逐 seed 逐 var：`dead=True` 或 `silence_frac>0.50` → FAIL | `evaluate()` L355-366 |
| ② 合并 CI 下限 | Wilson 95% `ci_lower ≥ 0.55` | L368-371 |
| ③ 合并点估 | `p_hat ≥ 0.60` | L373-376 |
| ④ per-seed weighted | 5 seed 全 `weighted ≥ 0.50` | L378-383 |
| ⑤ 其余项 | 5a grv↑/↓ 桶≥0.60(n≥5) · 5b credit 复活四指标 · 5c 守卫 A/B · 5d EASE gate=PASS · 5e 回退闸(weighted≥baseline−0.10) · 5f rho 符号一致 | L385-461 |

- eligible 池与 N 无条件先算（FAIL 也带证据）
- 硬闸短路：①→②→③→④ 任一 FAIL 即返回；⑤ 内 5a-5f 全须过

---

## 3. R4g 教训固化——M1-M5 机读监测（全部落盘；标「硬闸」的 FAIL 即整体 FAIL）

### M1 · EASE/TIGHTEN 方向一致率逐 seed（报告+观察，非闸）
- 定义：**A2 决策级**（`a2_action=="EASE_CREDIT"` / `=="TIGHTEN_CREDIT"`，需 arch 落盘后精确机读）；**方向规则为动作相关**：
  - EASE：correct = t<0（内生 target 期望放松）、wrong = t>0（期望收紧却放松）
  - TIGHTEN：correct = t>0（期望收紧时收紧）、wrong = t<0（期望放松却收紧）
  - neutral = |t|<EPS_TGT（方向未定义步不计入 rate）
- **基线（③ 前，v2.0.37，data-r4h 决策级补采已复核）**：
  - EASE c/w/n=15/9/0，rate=0.625（**wrong=9**）；TIGHTEN c/w/n=21/17/15，rate=0.553
  - 逐 seed：42(2/2/0, 4/4/4) 7(3/1/0, 5/3/3) 123(2/3/0, 4/4/5) 2024(3/1/0, 4/5/3) 777(5/2/0, 4/1/0)
  - credit_t 与 cs_delta 方向区（|cs|>2.5 ∧ |t|≥EPS）同号率 62/62（0 mismatch）——方向判据无歧义
- **废弃口径**：net credit `d<0` 落地（多写者净效果）——实测 wrong=15（R4e），偏高且非 A2 专属，**禁作 M4 对比基准**
- 落盘：`monitoring.M1.ease_direction_consistency[seed]{c,w,n}` + `monitoring.M1.tighten_direction_consistency[seed]{c,w,n}`（a2_action 落盘后按决策级；未落盘前用代理并标注）
- 用途：③ 实施后 EASE wrong 是 M4 对比项；**前后对比必须同口径（A2 决策级）**——data 已用决策级（monkeypatch 捕获 snapshot A2 action）补采 ③ 前基线，arch 落盘 step_record.a2_action 后可复核（预期数值不变）

### M6 · TIGHTEN wrong + vix 豁免步数（growth ② 专属监测，**硬闸**）
- 定义：`n_tighten_wrong = Σ[ cs_delta<-2.5 ∧ credit d>0 ]`（期望 ease 却收紧落地）；`n_exempt = 其中 vix_stress>1.0 的步数`（豁免放行占比）
- **基线（③ 前，v2.0.37）**：17 步（7:3 / 42:4 / 123:4 / 777:1 / 2024:5），**100% 豁免**（R4g 实验期 v2.0.36 曾为 26 步——阶段二中间态，非当前基线；26 弃用）
- **闸：`n_tighten_wrong > 17`（基线）→ FAIL**（方向闸/豁免治理后不应更多方向违规）
- 达标观察：豁免占比下降（目标 <100%，向"仅真危机放行"收敛）
- 落盘：`monitoring.M6.tighten_wrong[seed]{n, n_exempt}`（vix_stress 已落盘 step_record，现即可机读）

### M7 · A1/A3 行动分布 + vix 存量轨迹（观察项，非闸；讨论 1/3 提议，待裁决）
- 目的：补验收矩阵盲区——③ 过冲（sentiment 写者）可能改变 sentiment 驱动 agent（A1/A3/A6/A10）行动频次分布；质量影响已有 5a/S1/M5/merged 捕获，但「纯分布漂移不损质量」现行矩阵无直接观测
- 定义：
  - `a1/a3 行动分布`：step_record 已落 a1/a3 action，前后对比各 action（HOLD/SHORT/CUT/NO_ACTION）占比（跨 seed median）
  - `vix 存量轨迹`：step_record 已落 vix，前后对比 vix median/末值 + vix_stress>1.0 步数（基线 median=24）——支撑「③ 后残留根因=vix 存量」判定与 ② 治理范围量化
- 落盘：`monitoring.M7.a1a3_action_dist[seed]`、`monitoring.M7.vix_trajectory[seed]{median,max,gt1_count}`
- 状态：讨论 1/3 由 qa 提议（零成本，step_record 字段已齐），待 team-lead 裁决后纳入定稿

### M2 · per-seed silence diff vs R4e（**硬闸**）
- 定义：`Δsilence[seed] = silence_new[seed] − silence_R4e[seed]`（R4e 取自 `output/r4e_backup_v2030c/` 同 seed 工件）
- **闸：任一 seed `Δsilence > +0.05` → FAIL**（silence 恶化红牌）
- 依据：R4g 实验期 seed42 +0.061 / seed2024 +0.062 恰被此线拦截；seed7 −0.143 / seed123 −0.041 为改善不计
- 落盘：`monitoring.M2.silence_diff_vs_r4e[seed]`

### M3 · rate_limit 占比前后（报告+观察，非闸）
- 定义：S 类口径与完整 steps 口径各报 `rate_limit / activation_gate / tighten_signal_false / acted_other` 四占比（跨 seed median）
- 落盘：`monitoring.M3.attribution[seed]{s_class, full_steps}`
- 用途：验证「声称降 rate_limit 的改动」是否真降（R4g 教训：HOLD 不锁步只把 rate_limit 微降 0.388→0.367 且 silence 转移）；同时报 rule_hold(tsf) 变化（修复①后已可测）

### M4 · flip-flop 振荡（**硬闸，A2 决策级**）
- 定义：`n_flip_win2 = Σ_i [ A2_action(i)==TIGHTEN_CREDIT ∧ ∃j∈{1,2}: A2_action(i−j)==EASE_CREDIT ]`
- **闸：任一 seed `n_flip_win2 > 0` → FAIL**
- 依据：R4e/R4g 收尾（EASE 冷却=2）下 A2 决策级 flip 结构上为 0（TIGHTEN 被冷却挡 2 步）；R4g 实验期（冷却=1）才出现
- **禁止用 d-series 代理作闸**：实测 R4e 基线 d-series 代理 0.0-0.375 与 R4g 实验期 0.111-0.667 重叠，不可区分（credit d 含多写者，非 A2 专属）——这正是必须落盘 `a2_action` 的原因（P1 前置依赖）
- 若 R4h 有意放松冷却：须先改本闸阈值并经三方+总监批准（放松冷却本身即触发「放宽换活性」审查）
- 落盘：`monitoring.M4.flip_win2[seed]`、`monitoring.M4.n_ease_decision[seed]`（观察）

### M5 · 「放宽换活性损质量」（**硬闸**）
- M5a：**任一 seed credit consistency < 0.45 → FAIL**（R4e 全 seed ≥0.471；R4g 实验期 seed7=0.429 / seed123=0.438 恰被拦截）
- M5b：**credit median consistency < 0.45 → FAIL**（绝对底线；兼容 R4e median 0.5625 × 0.8 = 0.45）
- 观察：median vs R4e(0.5625) 的 Δ 报告；逐 seed consistency 全部落盘
- 与既有回退线关系：本闸(0.45) 严于 revert 线(0.40)，松于 target 线(0.60)
- 落盘：`monitoring.M5.consistency[seed]`、`monitoring.M5.median_consistency`

---

## 4. 回退线 5 条（沿用 R4d，机读）

> 代码路径：`R4D_ROLLBACK_LINES` L80-91 + `rollback_check()` L155-185

| 线 | target（达标） | revert（红牌） | worse |
|---|---|---|---|
| credit_consistency | median ≥0.60 | <0.40 | lt |
| grv_down | median ≥0.40 | <0.20 | lt |
| merged_p | ≥0.55 | <0.43 | lt |
| credit_n_active | median ≥18 | — | lt |
| credit_silence | median ≤0.50 | — | gt |

- revert 红牌 → 记入 verdict FAIL（带 value/desc）；warn 黄牌 → 仅警告

---

## 5. sentiment 写者专属监测（R4h 增长点③）

### S1 · sentiment 桶分布前后（报告）
- 定义：探针 steps 中 sentiment level 分桶占比（`<−0.5`(floor 区) / `[−0.5,0)` / `[0,0.5)` / `≥0.5`），跨 seed median
- 落盘：`monitoring.S1.sentiment_bucket[seed]`
- 用途：验证写者是否把 sentiment 从恒贴 floor 抬起（R4h 增长点③预期）

### S2 · grv_down reverse 占比（**硬闸**）
- 定义：`reverse_share[seed] = 1 − consistency_grv_down[seed]`（market_sentiment；grv 下行步中 d 与 grv_delta 异号占比，`consistency_grv_down` 已落盘）
- **闸：`median(reverse_share) ≥ R4e_baseline_median` → FAIL**（R4e 基线 median≈0.727，由 backup 工件实时复算，不硬编码；R4f 参考 0.685 落在 R4e 区间内）
- 达标观察：`≤0.60`（写者生效、反向收敛）；`0.60~baseline` → warn
- 依据：sentiment 写者若生效，reverse 应**下降**；不降反升 → 写者未生效或反向 → FAIL
- 落盘：`monitoring.S2.grv_down_reverse[seed]`、`monitoring.S2.median_reverse`

---

## 6. ARTIFACT_TAG bump 说明（R4g 教训④）

- **R4h 强制 `ARTIFACT_TAG = "v2031"`**（`scripts/run_probe_acceptance.py` L69 由 v2030c → v2031）
- 原因：R4g 全程复用 v2030c（实验期 v2.0.36 覆盖 output/ 根，收尾期 v2.0.37 另落 qa_revert_spotcheck/），造成 era 混淆与「同名不同代」风险；R4h 起每代引擎专用 tag
- 对照基线不动：`output/r4e_backup_v2030c/`（R4e 五 seed 工件）永久保留作 M2/M5/S2 对照
- 旧工件清理建议（P2，不阻塞）：output/ 根下 v2030c 实验期工件可归档，防误读

---

## 7. 判定代码路径映射（R4h 版验收脚本新增/改动清单）

| 闸/项 | 实现位置 | 说明 |
|---|---|---|
| P1 a2_acted 前置 | `calibrator.py` step_record + `a2_action`；`run_probe_acceptance.py` 新增 precheck | arch 落盘字段后机读 |
| P2 归因双报 | `var_stats()` 增 full-steps 四分类；summary 增 `attribution_dual` | 从 steps 重算 |
| M1 | 新增 `ease_direction_consistency()` 读 `a2_action`（未落盘用 acted_other∧d<0 代理） | A2 决策级；基线 wrong=9 |
| M2 | 新增 baseline 对照（读 `r4e_backup_v2030c/`） | 逐 seed diff |
| M3 | 复用 s_class_attribution + 新增 full-steps | 双口径 |
| M4 | 新增 `flip_win2()` 读 `a2_action` | 决策级 |
| M5 | 新增 consistency 底线闸（0.45） | 逐 seed + median |
| M6 | 新增 `tighten_wrong_exempt()`（读 steps cs_delta/d/vix_stress） | 基线 17 / 100% 豁免；>17 FAIL |
| S1/S2 | 新增 sentiment 桶 + reverse 计算 | 读 per_var |
| 主闸序①-⑤ | 沿用 `evaluate()` | 不动 |
| 回退线 5 条 | 沿用 `rollback_check()` | 不动 |

**R4h 前置依赖（arch，实施期）**：① step_record 落盘 `a2_action`（同时服务 P1/M4）；② `ARTIFACT_TAG=v2031`；③ CACHE_VERSION 11→12 + VERSION bump；④ 断言 ≥110 增不降 + 规格变更登记；⑤ 任一增长点改动均需 5 seed 独立验收 + data 归因前后对比（arch draft §末尾已列）。

---

## 8. 附：R4g 全程数据锚（本文档阈值依据，禁止改动）

| 量 | R4e 基线 | R4g 实验期(v2.0.36) | 用途 |
|---|---|---|---|
| credit median consistency | 0.5625 | 0.500 | M5b 依据（×0.8=0.45） |
| credit per-seed consistency | 42:0.562 7:0.714 123:0.500 2024:0.471 777:0.688 | 42:0.692 7:0.429 123:0.438 2024:0.500 777:0.688 | M5a 依据（全 seed≥0.471 vs 实验期 0.429/0.438） |
| credit per-seed silence | 42:0.49 7:0.531 123:0.531 2024:0.469 777:0.49 | 42:0.551 7:0.388 123:0.49 2024:0.531 777:0.49 | M2 依据（Δ>+0.05 拦截 42/2024） |
| sentiment grv_down reverse | median≈0.727（per-seed 0.591-0.762；pooled 0.679） | median≈0.65 | S2 依据（红牌=≥baseline 0.727；data 复核同值） |
| TIGHTEN wrong 步数 | **17（7:3/42:4/123:4/777:1/2024:5），100% vix>1.0 豁免** | 26（阶段二中间态，弃用） | M6 基线（>17 FAIL） |
| EASE wrong（A2 决策级） | **9 步**（data 决策级补采 c/w/n=15/9/0 rate 0.625，qa 已复核） | M1/M4 ③ 前基线（同口径对比） |
| TIGHTEN 方向（A2 决策级） | **c/w/n=21/17/15 rate 0.553**（逐 seed 见 §M1） | M1 ② 观察锚 |
| M4 d-series 代理 | 0.0-0.375 | 0.111-0.667 | 禁作闸（重叠不可分） |
| merged p̂ | 0.5152 | 0.5115 | 现状锚（未达 partial，R4h 目标提升） |

---

*定稿人：qa-r4g · 设计轮产出，不执行验收。待 arch 实施后按本文档全量执行（5 seed 新探针 + M1-M5/S1-S2 机读落盘 + 反作弊门）。*
