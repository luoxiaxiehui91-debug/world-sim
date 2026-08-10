# R4h 数据票（data-r4h2，2026-08-09）——③-A 参数/批次实证

> 上游：R4h 评审简报 v1 §6.1（补 data 票）。本票全部基于 v2.0.37 容器实测数据 + 只读探针重放，未改任何源码/落盘工件。
> 数据源：容器 /tmp/r4h_probe_seed{seed}.json（5 seed 主探针）+ r4h_sent_impact.json / r4h_sent_detail.json / r4h_a1a3_dist.json（上一会话产物，本次已拉回本地核对 md5 一致性）+ r4h_detail.json（逐 delta 步）。
> 本地副本：C:\tmp\r4h_data\（全套）+ C:\tmp\r4h_data2\（本票证据子集）。

---

## 0. 数据可信性自检

- ✅ 容器 = v2.0.37：CACHE_VERSION=11，探针路径与基线快照 per-seed 逐项一致（p̂=0.5152/CI=0.4387）。
- ✅ merged 敏感性重建：用 probe json 的 per_var n_active/consistency_rate 重建 p̂=0.5152、N=161.7、K=83.3、CI=0.4388，与 baseline2 完全一致（diff<0.001）。
- ✅ 剂量口径确认：simulation.py:544 MONTHLY_SCALE=0.25 只作用于 market_sentiment（apply_sentiment_delta 前乘），credit/liquidity 不乘——**探针脚本的 ×0.25 假设与真实引擎一致**（脚本模拟对）。
- ⚠️ 探针产物 r4h_sent_impact.json 原本地为 0 字节（上会话未回传），本次已从容器拉回（md5 一致），以下数字全部来自容器内实际运行产物。

---

## Q1. A vs B：merged p̂ 影响估算

### 1a. 纯敏感性（sentiment consistency +Δ，n_active 不变，weight 0.40）

用基线 per_var 重建，sentiment cons +Δ 全局施加：

| sentiment cons +Δ | merged p̂ | Δp̂ | CI 下限 | 距 partial 0.55 |
|---|---|---|---|---|
| +0.00 | 0.5152 | — | 0.4388 | +0.111 |
| +0.05 | 0.5418 | +0.027 | 0.4650 | +0.085 |
| **+0.10** | **0.5684** | **+0.053** | **0.4914** | **+0.059** |
| +0.15 | 0.5950 | +0.080 | 0.5180 | +0.032 |

**accept 线 p̂≥0.616**：需要 sentiment cons +0.19（外推），CI 下限 ≥0.55 需要 sentiment cons +0.28——**现实不可达**。**partial 点估 0.55 需要 sentiment cons +0.082**（可及），**CI 下限 0.55 不可达**。

### 1b. S→T 转移稀释（sentiment n_active 变化）

探针反事实（cons +0.10 同时 n 增）：

| n_active 变化 | merged p̂ | CI 下限 |
|---|---|---|
| n 不变 | 0.5684 | 0.4914 |
| n+5% | 0.5702 | 0.4941 |
| n+10% | 0.5720 | 0.4967 |

**稀释 <0.002**，可忽略。原因：merged 公式分子分母同乘（weight×n 同变，cons 不变），结构上自抵消。eligible 池扩大不稀释。

### 1c. 实际可达性（③-A 写者注入 → consistency 改善）

**关键反事实（本票核心）**：沿基线路径逐步重放 EASE 写者注入 +0.08（MONTHLY_SCALE 后实际 +0.02/步），统计 EASE 步 sentiment d/t 方向翻转：

- 基线 EASE 步 sentiment 方向：ok=14 / wrong=8 / neu=2（24 步，5 seed 合计）
- 注入 +0.02 后：ok=13 / wrong=9 / neu=2（**翻转 1 步且为负向**：seed123 i=15，d=-0.0095→+0.0105，由 OK 变 wrong）
- **结论：③-A 的 EASE 直接写 sentiment 对 sentiment consistency 的边际贡献 ≈0（甚至 -1 步）**。reverse 改善不来自 EASE 步本身的方向一致性，而是来自**间接链**：EASE 写 sentiment → level 抬升 → 后续步 A3/A1 决策输入改变 → 其他写者行为变化。

因此 arch 简报中 "EASE 写 +0.08 → grv_down 桶一致性直接改善" 的**机制表述需要修正**：直接注入的 T 类贡献可忽略，改善全部依赖状态反馈链（重放无法验证，需实施后实测）。

### 1d. S2 达标 → merged p̂ 推算

S2 目标 grv_down reverse ≤0.60 → grv_down cons 0.273→0.40（seed42/7/123/2024/777 基线 cons_grv_down = 0.273/0.409/0.238/0.381/0.273）。若 ③ 真能把 grv_down cons 全部推到 0.40：

- 全 T sentiment cons 提升（按 n_up:n_down≈22:21 加权）：仅 **+0.066**（seed42 +0.067 / seed7 -0.004 / seed123 +0.079 / seed2024 +0.009 / seed777 +0.065，median +0.065）
- 映射到 merged：**p̂ ≈ 0.538~0.550，CI 下限 ≈ 0.461~0.475**
- **仍不达 partial 0.55 的 CI 闸**（0.461~0.475 < 0.55），点估 0.538~0.550 也仅在 partial 点估边缘。

**结论**：单靠 ③ 无法过 partial 0.55 CI。**merged 提升必须 ①+②+③ 三管齐下**（③ 治 grv_down + ② 治 TIGHTEN wrong + ① 治 EASE wrong）。A vs B 在 merged 层面的差异 <0.003（sentiment 权重分子主导），**参数选择不改变 merged 结论**。

---

## Q2. A 过冲触发概率（验证 arch 断言）

### 2a. 剂量澄清（推翻 "EASE 累积 +0.14-0.19" 毛算）

EASE 写 +0.08 经 **MONTHLY_SCALE=0.25** 后实际生效 **+0.02/步**（damping 恒 1）。4-7 步/seed × 0.02 = **+0.08~+0.14/seed 累积**（含传导后 +0.11-0.15）。team-lead 给的 "+0.14-0.19" 漏乘 0.25。

### 2b. 重放结果（A vs B vs 基线，5 seed median）

| 方案 | sentiment mean（median） | floor_frac（median） | A1 HIKE 触发 | A3 INCREASE_RISK(sent>0.1 路径) |
|---|---|---|---|---|
| 基线 | -0.842 | 0.652 | 0 步 | 0 步 |
| **A K=1.0** | **-0.768** | **0.024** | **0 步** | **0 步** |
| B k=0.75 | -0.787 | 0.028 | 0 步 | 0 步 |

- sentiment 从 -0.88 起，A 抬到 -0.77、B 抬到 -0.79。**A1 HIKE 阈值 >0.5：差 1.3（A）/1.29（B）**；**A3 INCREASE_RISK(sent>0.1) 阈值：差 0.87（A）/0.89（B）**。5 seed 全 0 触发。安全边际 ~5 倍。
- **arch 断言 "A1 HIKE>0.5 概率≈0" 验证通过**（分布数据支持：sentiment 全 T 分布无任何 ≥0.5 尖峰，见 2c）。
- **arch 断言 "A3 -0.4 边界复激活是主要行为变化" 验证成立**：floor_frac 0.694 → 0.024（A），~97% 步脱离 floor 冻结区；sentiment>-0.4 步数从 median 6 步显著增加 → A3 SHORT/DECREASE/INCREASE 分支重新激活。方向正确（sentiment 抬离 -0.4 后 A3 从被动 HOLD 恢复响应）。
- ⚠️ 但需注意：A3 INCREASE_RISK 全分布 baseline 为 15/15/12/15/13（步），**绝大多数由 OVERSOLD_BOUNCE_PROB=0.45 高压抄底路径触发**（financial.py:123，注意实测 0.45 ≠ 注释 25%），与 sentiment>0.1 无关（sent_gt_0.1 实测全 0）。**② 豁免前提方案（vix>1.0 ∧ sentiment>-0.3）注意：A3 在高压下仍会抄底，sentiment 抬升不会压死 A3 负写**。

### 2c. A 方案 sentiment 分布（S1 监测口径，重放）

| seed | <−0.5 | [−0.5,0) | [0,0.5) | ≥0.5 |
|---|---|---|---|---|
| 42 | 36 | 13 | 1 | 0 |
| 7 | 47 | 3 | 0 | 0 |
| 123 | 42 | 3 | 5 | 0 |
| 2024 | 46 | 3 | 1 | 0 |
| 777 | 43 | 6 | 1 | 0 |
| median | 43 | 3 | 1 | **0** |

- **无 ≥0.5 尖峰**（S1 监测项：抬离 floor 但无 ≥0.5 尖峰 → 通过）。
- 多数步仍在 <−0.5 区（median 43/50），说明 EASE 写者只把 floor 松开，未把 sentiment 拉到中性以上——**这与 S2 期望方向一致**（抬离 floor 让负压松动）但**未引发 A1 HIKE**。

### 2d. A1/A3 行动分布基线（M7 观察项前置）

| seed | A1 CUT_50BP | A1 CUT_25BP | A1 HIKE | A3 SHORT | A3 INCREASE | A3 DECREASE | A3 HOLD |
|---|---|---|---|---|---|---|---|
| 42 | 7 | 1 | 0 | 11 | 15 | 8 | 3 |
| 7 | 6 | 1 | 0 | 12 | 15 | 8 | 3 |
| 123 | 6 | 1 | 0 | 12 | 12 | 8 | 8 |
| 2024 | 6 | 0 | 0 | 10 | 15 | 7 | 5 |
| 777 | 5 | 2 | 0 | 12 | 13 | 13 | 4 |

- **A1 HIKE 5 seed 合计 1 次**（seed42 的 HIKE_25BP=1；snapshot 决策后 sent>0.5=0 因 A1 用决策前 ctx、快照为决策后状态回落）。重放注入后 HIKE 仍 0 → **过冲风险不存在**，但记录 seed42 基线存在 1 次决策级 HIKE（M7 观察项注意：③ 后需确认 A1 HIKE 不新增）。
- A1 CUT 高发（sentiment<-0.4 触发）——③ 抬离 floor 后 A1 CUT 会减少，这是 ③ 的另一正反馈（减少 -0.12~-0.30 负写）。**但注意 A1 CUT_25BP 写 +0.30 是正写**（读 simulation.py:125），CUT_50BP 写 +0.35 也是正写——A1 CUT 减少实际是**减少正写**，方向需实测确认（可能部分抵消 EASE 效果）。

---

## Q3. ③② 分步的 vix_stress 收敛判据（机读）

### 3a. 基线

vix_stress>1.0 步数 25/38/23/24/23（median 24）；TIGHTEN wrong 17 步 100% 豁免；vix 峰值 162-238（无 decay，存量不回吐）。

### 3b. ③ 单独对 vix 的影响（探针重放）

- **bleed 触发步数（sentiment<-0.5 连续 3 步）**：基线 median 41（35/45/40/44/41），A 方案 **34/45/40/44/41（median 40，Δ-1）**——③ 几乎不动 bleed。
- ⚠️ 口径注：r4h_sent_detail.json 中 vix_gt1 字段全 0 是探针捕获 bug（snap 顶层无 vix_stress），**真实 vix_stress>1.0 步数以 r4h_probe_seed*.json 顶层为准 = 25/38/23/24/23**，与基线快照一致。
- **根因**：vix bleed 触发条件 `sentiment<-0.5 ∧ 连续 3 步`（world_state.py:277-280）。A 方案 sentiment 抬到 -0.77 仍 < -0.5 → **bleed 条件继续满足** → vix 存量继续涨、不回吐。
- **③ 单独不会降 vix_stress>1.0 步数**（预计 23-38 → 接近不变），② 是治理豁免的唯一手段。

### 3c. 机读判据（建议，③② 分步后分别设）

- **③ 后（sentiment 收敛闸，S2 补充）**：
  - `vix_stress>1.0 步数 ≤ 基线 median 24`（**不增长 = 存量不恶化**；因 ③ 结构上不降存量，此闸只防恶化）
  - 更严：`bleed 触发步数 ≤ 基线 × 0.5`（若想验证 ③ 对 bleed 的间接效果）
- **② 后（豁免治理闸，M6 补充）**：
  - `TIGHTEN wrong 中豁免占比 < 100%`（豁免开始被约束）
  - `n_tighten_wrong ≤ 17`（沿用 M6 硬闸）
  - 理想：vix_stress>1.0 步数**下降**（② 加 decay/回吐时）
- **② 裁决闸 = M6 残差**：③ 后 TIGHTEN wrong 实测 ≤17 → ② 可轻量或不做；>17 → ② 必做。

---

## Q4. 明确推荐

### 参数：**A（K=1.0，+0.08）** ✅（与 qa/arch 一致）

数据论据：
1. **过冲风险不存在**（重放：A1 HIKE 0/0/0/0/0，A3 sent>0.1 路径 0/0/0/0/0；sentiment 最乐观 -0.675，离 0.5 差 1.2+）
2. **A 抬升效果优于 B**（mean Δ +0.074 vs +0.055；floor 0.024 vs 0.028），差异虽小但方向明确
3. **与 TIGHTEN -0.08 完全镜像**（arch 设计语义），无保险成本
4. B 的 k=0.75 是为防不存在的过冲打折，**无数据收益**

### 批次：**③ 先（独立验收），② 紧随（同批或下一批），① 独立并行** ✅（与 qa/arch 一致）

数据论据：
1. **③ 先上不破坏 M6**：TIGHTEN wrong 17 步基线，③ 只动 EASE 写 sentiment，不碰 TIGHTEN 豁免逻辑 → ③ 后 M6 仍 17 步（≈不变），**不触发 >17 FAIL**
2. **② 必须随后**：③ 单独不降 vix_stress（bleed 仍触发、存量不回吐），M6 豁免占比仍 100% → ② 是唯一治理豁免的手段
3. **① 独立并行**：仅 A2 规则层，不碰 sentiment/vix，可与 ③ 同批或独立批
4. **merged 现实**：③ 单批 p̂≈0.538-0.55（CI 0.461-0.475），**不达 partial 0.55 CI**；要过闸必须 ①②③ 全落地后 5 seed 实测

### ⚠️ Advisory（请 team-lead 转达 qa/arch）

1. **arch 简报 "EASE 写 sentiment → grv_down 桶一致性直接改善" 机制表述需修正**：反事实显示 EASE 步直接注入对 sentiment 方向一致性贡献 ≈0（24 步仅 1 步翻转且为负）。③ 的 reverse 改善**只能靠状态反馈链**（sentiment 抬升 → A1/A3 决策改变 → 其他写者行为变化），此链重放无法验证，**实施后 S2 实测是唯一裁决**。预期 grv_down reverse 0.52-0.62 应视为"反馈链上界"，若实测只到 0.62-0.68 属正常范围（直接剂量不够）。
2. **A3 OVERSOLD_BOUNCE_PROB 实测 0.45 ≠ 注释 25%**（financial.py:123）。A3 INCREASE_RISK 大量由高压抄底路径触发（15 步/seed 级别），与 sentiment>0.1 无关。② 豁免前提（vix>1.0 ∧ sentiment>-0.3）设计时勿假设 A3 正写会随 sentiment 抬升增加。
3. **A1 CUT_25BP/CUT_50BP 是正写**（+0.30/+0.35，simulation.py:125/117）。③ 抬离 floor 后 A1 CUT 减少 = 正写减少，可能部分抵消 EASE 正写。M2 silence 与 S2 需一起看，防 R4d 沉默回归（A1 减负写过多 → 其他步 sentiment 响应不足）。
4. **partial 0.55 CI 单批不可达**（0.461-0.475 < 0.55）。建议 team-lead 明确 R4h 是否接受"多批累计过闸"（③+②+① 全部落地后合并验收），否则请调整预期。

---

## 证据清单

- 容器内（只读 /tmp 探针，未污染 output/）：`/tmp/r4h_probe_seed{42,7,123,2024,777}.json`、`/tmp/r4h_sent_impact.json`、`/tmp/r4h_sent_detail.json`、`/tmp/r4h_a1a3_dist.json`、`/tmp/r4h_baseline2.json`
- 本地：`C:\tmp\r4h_data2\`（本票 + 3 个证据 json 副本）、`C:\tmp\r4h_data\`（全套基线 + 探针脚本）
- 复算脚本：`probe_merged_sens.py` / `probe_sent_impact.py` / `probe_sent_detail.py` / `probe_a1a3_dist.py`（C:\tmp\r4h_data\，本地 Python3.12 复算一致）
- 代码锚点：simulation.py:117/125/141/147/544（写者 + MONTHLY_SCALE）、world_state.py:277-280/305-313（bleed + apply_sentiment_delta）、financial.py:38-48/137-152（A1/A3 阈值）、agents.yaml:21-23/43-45（A2 传导 to_A3=0.40/to_A10=0.35）
