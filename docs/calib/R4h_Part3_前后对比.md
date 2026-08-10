# R4h Part 3 前后对比（② vix 治理批次，data-r4h2，2026-08-09）

> 引擎：v2.0.39 / CACHE_VERSION 13 / commit 2276b1d / 容器 image c25df8907519（③+② 已部署）
> 对比链：基线 v2.0.37（③ 前）→ v2031 v2.0.38（③-A）→ **v204x v2.0.39（③+②）**
> 探针：独立跑 probe_v204x.py（只读 monkeypatch /tmp，5 seed，未污染 output/），CACHE=13 全新跑
> ② 机制（arch 说明 + 代码核实）：**vix 均值回归 0.80/0.20**（world_state.py:351，D4 fix 遗漏变量）+ **yen_carry bleed 封顶 19**（world_state.py:266 `vix_yen_carry_bleed_max=19.0`，原出血5 无上限 +5.0/步）

---

## 0. 部署验证 + arch 锚点核对

- ✅ v2.0.39 / CACHE_VERSION=13 / world_state.py 双改动确认（L351 回归 + L266 封顶）
- ✅ arch 工件核对（我的独立探针 vs arch 落盘）：
  | 指标 | arch 报 | 我的独立探针 | 判定 |
  |---|---|---|---|
  | M6 TIGHTEN wrong | 16（42:4/7:5/123:3/2024:3/777:1） | 16（同） | ✅ 一致 |
  | vix 峰值 | 53.2-53.4 | 53.2-53.4 | ✅ 一致 |
  | vix>48 步 | 21-36 | 21-36 | ✅ 一致 |
  | vix_stress_final | 1.13-1.18 | 1.08-1.15 | ✅ 一致 |
  | M2 silence diff | 全 ≤+0.041 | +0.020/+0.040/+0.020/+0.041/0.000 | ✅ 一致 |
  | credit consistency median | 0.500→0.538 | 0.538 | ✅ 一致 |
  | merged p̂ | 0.5094→0.4948 | 0.4948 | ⚠️ 见判据⑤（池结构变化） |

---

## 1. 六判据逐项裁决

### 判据① M6 裁决闸 ✅ PASS
| 指标 | 基线 | v2031 | v204x |
|---|---|---|---|
| TIGHTEN wrong 合计 | 17 | 18 | **16**（≤17 达标） |
| 逐 seed | 42:4/7:3/123:4/2024:5/777:1 | 42:5/7:3/123:4/2024:5/777:1 | 42:4/7:5/123:3/2024:3/777:1 |
- **18→16，seed42 回落 1**，M6 闭环 ✅
- wrong 明细全豁免（16/16，vix_stress_before 1.017-1.176 全 >1.0）——详见判据③
- **但注意**：vix 峰值 53 > 48 → vix_stress>1.0 豁免条件仍恒触发，wrong 步仍 100% 豁免。M6 达标靠的是 **vix 降 → cs 回落步 tighten_signal 的 vix 分量不满足 → 转 HOLD**（wrong 减少），而非豁免被约束。

### 判据② vix 存量 ✅ PASS（核心达标项）
| 指标 | 基线 | v2031 | v204x |
|---|---|---|---|
| vix>1.0 步数（median） | 24 | 24 | **22**（21-36） |
| vix_stress_final（median） | 4.99 | 4.99 | **1.13**（1.08-1.15） |
| vix_last==vix_max | 5/5 True | 5/5 True | **0/5 True（全 False）** |
| vix 峰值 | 168 | 168 | **53**（53.2-53.4） |
| vix reclaim（last<peak） | 0/5 | 0/5 | **5/5** |
- **存量回吐 5/5、vix 峰值 162-238→53、vix_stress_final 4.99→1.13** —— ② 的核心证据全部翻绿 ✅
- 均值回归 0.80/0.20 生效，apply_natural_decay 缺 vix 的根因被修复
- **注意**：vix 53 > 48 仍 >1.0 豁免线，但存量已回吐（不再单调锁边）

### 判据③ 豁免占比 ⚠️ 未达标（仍 100%）
| 指标 | v2031 | v204x |
|---|---|---|
| TIGHTEN wrong 豁免占比 | 100% | **100%**（16/16） |
- **豁免占比未降**。原因：vix 峰值 53 > 48 → vix_stress>1.0 豁免条件在 cs 回落步仍恒满足。
- **但 M6 已达标**（16≤17）。豁免占比判据是"更严观察项"，实际机制是"vix 降 → 收紧信号分量消失 → wrong 步转 HOLD"，而非"豁免被约束"。
- 结论：判据③ 名义未达标，但 M6 达标 + vix 存量治理达标 → ② 的核心目标（M6 残差）已达成，豁免占比作为次级观察项记录。

### 判据④ S2 ✅ PASS（③ 效果保留）
| 指标 | 基线 | v2031 | v204x |
|---|---|---|---|
| grv_down reverse（median） | 0.727 | 0.682 | **0.682**（42:0.682/7:0.591/123:0.762/2024:0.619/777:0.714） |
- **不反弹**（0.682 持平），③ 的 S2 改善被保留 ✅
- **无进一步改善**：② 未突破"反馈链上界 0.62-0.68"区间（Part 1 advisory 1 预测验证）

### 判据⑤ merged p̂ ⚠️ 需同池对比（池结构变化）
| 指标 | 基线 | v2031 | v204x |
|---|---|---|---|
| p̂（自动 eligible） | 0.5152 | 0.5094 | **0.4948** |
| CI 下限 | 0.4387 | 0.4330 | **0.4118** |
| N / K | 161.7/83.3 | 161.6/82.3 | **135.0/66.8** |
| eligible pool | 3 变量 | 3 变量 | **2 变量（credit 出池！）** |
- **关键发现**：v204x 的 merged eligible 池 **bank_credit_tightening 出池**（3→2 变量）！因为 **credit silence median 0.510 > 0.50**（merged_eligible 要求 med_sil≤0.50）。
- p̂ 表面下降（0.5094→0.4948）**主因是池结构变化**（credit 剔除），非一致性恶化。
- **同池对比（强制 3 变量）**：
  | | v2031 | v204x | Δ |
  |---|---|---|---|
  | 强制全部3变量 | 0.5094 | **0.5077** | -0.0017 |
  | 强制 sent+lp | 0.4970 | **0.4948** | -0.0022 |
- **结论：② 在 credit 保留时 merged 基本持平（-0.002），一致性未恶化**。但 credit 因 silence 超线出池，是 ② 引入的结构性副作用。

### 判据⑥ ③+② 组合回归 ⚠️ 一项恶化（silence 绝对超线）
| 项 | v2031 | v204x | 判定 |
|---|---|---|---|
| S1 桶 ≥0.5 尖峰 | 全 0 | 全 0 | ✅ |
| A1 HIKE | 1（seed42） | 1（seed42） | ✅ 不新增 |
| A3 SHORT | 42:14/7:12/123:12/2024:10/777:12 | 42:14/7:12/123:12/2024:10/777:14 | ✅ 微变 |
| credit n_active | 16/14/14/17/16 | **15/12/13/15/16** | ⚠️ 微降（未塌，median 16→15） |
| **M2 silence diff（相对）** | — | +0.020/+0.040/+0.020/+0.041/0.000 | ✅ 均 ≤+0.05 |
| **credit silence 绝对中位** | 0.490 | **0.510** | ⚠️ **>0.50 硬闸 FAIL（4/5 seed）+ credit 出 merged 池** |
| tsf | 非零 | 0.040/0.107/0.148/0.200/0.125 | ✅ 保持非零 |
| EASE wrong | 15/9/0 | **15/8/0** | ✅ 改善（-1 wrong，rate 0.652） |
- **credit silence 0.490→0.510（中位）跨过 0.50 线**：相对 diff ≤+0.05 达标（arch 口径 M2 PASS），但**绝对 0.50 线被突破**，触发 acceptance 1-dead/silence 硬闸 FAIL（arch 自己的 acceptance_v2032.json failures 就是 4 条 silence>0.50）+ credit 出 merged eligible 池。
- 这是 ② 引入的**主要新副作用**：vix 降 → A2 tighten 步降 → TIGHTEN 转 HOLD → credit silence 升。

---

## 2. 归因 / EASE / 其余

### EASE·TIGHTEN c/w/n（统一口径）
| | EASE c/w/n | rate | TIGHTEN c/w/n | rate |
|---|---|---|---|---|
| v2031 | 15/9/0 | 0.625 | 19/18/15 | 0.514 |
| v204x | **15/8/0** | **0.652** | **17/16/15** | **0.515** |
- EASE wrong 9→8（改善）；TIGHTEN wrong 18→16（达标）✅

### 归因分布（credit S 类）
| seed | rate_limit b/v2031/v204x | activation_gate | tsf |
|---|---|---|---|
| 42 | 0.500→0.480 | 0.500→0.480 | 0.000→0.040 |
| 7 | 0.692→0.643 | 0.269→0.250 | 0.038→0.107 |
| 123 | 0.692→0.667 | 0.192→0.185 | 0.115→0.148 |
| 2024 | 0.652→0.600 | 0.217→0.200 | 0.130→0.200 |
| 777 | 0.417→0.417 | 0.458→0.458 | 0.125→0.125 |
- tsf 全面上升（0.000→0.040 等）——silence 升高后 tighten_signal 分量相对更多被 HOLD 吸收，归因向 tsf 转移

---

## 3. 裁决矩阵

| 判据 | 结果 | 判定 |
|---|---|---|
| ① M6 ≤17 | 16 | ✅ PASS |
| ② vix 存量回吐 | 5/5 reclaim、峰值 53、vix_stress_final 1.13 | ✅ PASS |
| ③ 豁免占比 <100% | 仍 100% | ⚠️ 名义未达标（M6 已达标，次级项） |
| ④ S2 不反弹 | 0.682 持平 | ✅ PASS |
| ⑤ merged 同池持平 | -0.002 | ✅ 基本持平（但 credit 出池） |
| ⑥ 回归 | S1/HIKE/tsf/EASE 全过；**credit silence 绝对超线** | ⚠️ 1 项恶化 |

## 4. verdict

**② vix 治理核心目标达成（M6 18→16 达标 + vix 存量回吐 5/5 + vix_stress_final 4.99→1.13），但引入一项新副作用：credit silence 绝对中位跨过 0.50 线（0.490→0.510），触发 dead/silence 硬闸 FAIL（4/5 seed）并使 merged eligible 池剔除 credit。**

### blocking（1 条）
1. **credit silence 绝对超线**：median 0.510 > 0.50（seed42:0.510/7:0.571/123:0.551/2024:0.510/777:0.490，4/5 超）。arch 的 acceptance_v2032.json 自己就判了 4 条 1-dead/silence FAIL + credit 出 merged 池。**arch 报的 "M2 silence diff ≤+0.041" 是相对基线 diff 口径（达标），但验收硬闸是绝对 0.50 线（FAIL）——口径需澄清。** ② 单独不可过验收。

### advisory（4 条，供 team-lead/qa/arch 裁决）
1. **M2 口径矛盾需澄清**：arch 用"相对 diff ≤+0.05"报达标，但 acceptance 硬闸与 merged_eligible 用"绝对 silence ≤0.50"。credit silence 中位 0.490→0.510，绝对线被破。**请 team-lead 明确 ② 验收用哪个口径**：若绝对线，② 需继续调参（cap<19 试过但 seed2024 silence diff +0.062 超 M2 相对线 → 两线冲突，需要找新的 Pareto 点或接受 ③② 合并 batch 内降 silence）。
2. **② 未突破 S2**：grv_down reverse 0.682 持平，仍在"反馈链上界 0.62-0.68"区间（Part 1 advisory 1 验证）。② 是状态层治理，但实测未改善 sentiment 反馈链——vix 降 → A3 抄底（INCREASE_RISK）未见明显增多（seed7 15→16 微增），sentiment level 几乎不变（-0.733 等）。
3. **③+② 组合的 merged 基本持平**（同池 -0.002）：credit consistency 0.500→0.538 改善被 silence 升高 + n_active 微降抵消。**①（EASE wrong 治理）仍是 merged 提升的关键缺口**——EASE wrong 15/8/0 rate 0.652 仍是主要失分项。
4. **豁免占比 100% 需明确预期**：vix 峰值 53 > 48 → vix_stress>1.0 豁免在 cs 回落步恒触发。若 ② 目标是"豁免占比 <100%"，需 vix 峰值压到 ≤48（cap 进一步降低），但 arch 扫描显示 cap<19 会 silence 超线——**豁免占比与 silence 是 trade-off**，建议明确以 M6 ≤17 + 绝对 silence ≤0.50 为准（豁免占比作观察项）。

---

## 证据清单

- 容器内：`/tmp/r4h_v204x_all.json`、`/tmp/r4h_v204x_seed{seed}.json`、`/tmp/probe_v204x.py`、`/tmp/locate_tw39.py`、`/tmp/loc39_seed{seed}.json`、arch 工件 `/tmp/r4h_arch_v2032b/`（acceptance_v2032.json + 5 个 probe）
- 本地：`C:\tmp\r4h_data2\`（r4h_v204x_all.json + v204x_seed*.json + probe_v204x.py + acceptance_v2032.json + R4h_Part3_前后对比.md）
- 基线：`C:\tmp\r4h_data\`（r4h_baseline2.json + r4h_probe_seed*.json + r4h_ease_unified.json）
- 代码锚点：world_state.py L351（vix 回归 0.80/0.20）、L266（yen_carry bleed cap 19）、apply_natural_decay L316-327（原缺 vix decay，② 修复）
