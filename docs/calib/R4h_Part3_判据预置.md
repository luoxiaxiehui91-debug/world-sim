# R4h Part 3 判据（② vix 治理批次，data-r4h2 预置，2026-08-09）

> 状态：**预置**（arch 正在设计/实施 ②，部署后按本文档执行前后对比，产出留痕 C:\tmp\r4h_data2\）
> 对比链：基线 v2.0.37（③ 前）→ v2031 v2.0.38（③ 已上）→ **v204x（③+②，待部署）**
> 已有证据：C:\tmp\r4h_data\（基线全套）、C:\tmp\r4h_data2\（v2031 全套 + probe_v2031.py 复算脚本）
> 判定原则：与 Part 1/2 同口径（同探针脚本逻辑 / 同 acceptance 统计 / 同 EASE c/w/n 统一口径），只读 /tmp 不污染 output/

---

## 0. arch 可能改动的代码面（对照基准）

team-lead 提醒：② 治理涉及 vix，arch 大概率改 **world_state.py**（可能 + financial.py 豁免前提）。

### world_state.py 当前 vix 机制（v2.0.38 已核实）
| 锚点 | 现状 | ② 候选改动面 |
|---|---|---|
| `apply_natural_decay` L316-327 | **vix 不在衰减列表**（sentiment/credit/liquidity/energy/retail/yen/fund/em_capital/fiscal/china/grv 都有，独缺 vix） | **vix decay / 均值回归**（候选一） |
| `apply_bleed_rules` L277-280 | 出血1：`sentiment<-0.5 ∧ 连续3步 ∧ vix_delta_total<20` → `vix += 2.0` | **bleed 上限/速率**（候选三） |
| L297 | 出血5 yen_carry：`yen_carry_risk>0.7` → `vix += 5.0` | 同上（若改 vix 增量全局） |
| financial.py L78 | 豁免：`tighten_ok = (target_dir != "ease") or vix_stress > threshold*2.0`（vix>1.0 恒豁免） | **豁免非连续/额外前提**（候选二） |

### 交互风险（Part 3 对比时专门盯）
1. **vix decay 牵一发动全身**：vix 同时是 A1（L38/L41）、A2（L62/L78/L82）、A3（L122）、M6 豁免（L78）、bleed 触发（L278）的输入。加 decay 后：
   - vix 峰值下降 → vix>1.0 步数降 → **TIGHTEN wrong 中豁免部分转非豁免** → 若 wrong 总数仍 >17 需确认是否因"豁免变少→收紧被挡死→HOLD"而 wrong 反而降（方向对）还是因 cs 回落仍收紧但无豁免 → **wrong 计数不变/升**（方向错）。
   - A3 高压抄底（OVERSOLD_BOUNCE_PROB=0.45，financial.py:123）随 vix 下降 → INCREASE_RISK 减少 → 正写减少 → **sentiment 可能更负**（需 S1 桶复核，防 ③ 效果被倒灌）。
2. **豁免非连续前提**：若 arch 用 `vix>1.0 ∧ 连续N步` 或 `∧ sentiment>-0.3`——**我 Part 2 advisory 4 已警告 sentiment>-0.3 前提无效**（实测 sentiment 中位 -0.86，前提恒不满足→豁免全关→TIGHTEN wrong 可能反升或 credit 沉默回归）。Part 3 必须验证：豁免前提改后 **TIGHTEN wrong 不升** 且 **credit n_active/silence 不恶化**。
3. **bleed 上限**：只压 vix 增速不改决策 → vix 峰值降但 vix_stress_final 可能仍高（存量不吐）；若上限过低 → vix 峰值<48 → **豁免永不触发** → 同候选二风险。

---

## 1. 六项验收判据（② 部署后逐项裁决）

### 判据① M6 裁决闸（硬闸，首要）
| 指标 | 基线 | v2031 | ② 目标 |
|---|---|---|---|
| TIGHTEN wrong 合计 | 17 | **18**（seed42 4→5） | **≤17** |
| 逐 seed | 42:4/7:3/123:4/2024:5/777:1 | 42:5/7:3/123:4/2024:5/777:1 | 42 项须回落 1 |

**判定**：② 后 TIGHTEN wrong ≤17 → ② 达标（M6 闭环）；仍 >17 → ② 不达标，回退评审。
**注意**：需同时看豁免占比（判据③）区分"wrong 降因豁免收紧→HOLD"（真达标）vs "wrong 降因 cs 回落时收紧被挡死→HOLD"（同样是降，但要确认 n_active 不塌）。

### 判据② vix 存量（M7 口径）
| 指标 | 基线 | v2031 | ② 目标 |
|---|---|---|---|
| vix>1.0 步数（median） | 24（25/38/23/24/23） | 24（24/38/23/24/23） | **≤24（不恶化）且显著下降（<20 更佳）** |
| vix_stress_final（median） | 4.99 | 4.99 | **回落（<4.99，越接近 0 越好）** |
| vix_last == vix_max | 全 True（168/238/163/168/163） | 全 True | **≥1 seed 出现 False（存量回吐）** |
| vix 峰值（median） | 168 | 168 | **下降（若 arch 上 decay）** |

**判定**：① vix>1.0 步数 median ≤24 且 ≤ v2031 逐 seed（不恶化）；② vix_stress_final 回落（至少 seed7 的 7.33 要降）；③ `vix_last==vix_max` 不再全 True（**存量回吐是 ② 的核心证据**，若 decay 上了这个必变）。
**解释**：vix 当前无 decay（apply_natural_decay 缺 vix），所以 last==max 恒 True。② 若真治理存量，此判据必须翻绿。

### 判据③ 豁免占比（Part 1 Q3c 口径）
| 指标 | 基线 | v2031 | ② 目标 |
|---|---|---|---|
| TIGHTEN wrong 中豁免占比 | 100% | 100% | **<100%** |
| TIGHTEN wrong 明细 | 17 步全豁免 | 18 步全豁免 | 非豁免步出现 |

**判定**：② 后 TIGHTEN wrong 中出现 **非豁免步**（vix_stress≤1.0 的 cs 回落收紧被挡死 → HOLD）→ 豁免机制被约束。结合判据①：
- 豁免占比 <100% 且 wrong ≤17 → ② 达标（豁免约束有效，wrong 回落）
- 豁免占比仍 100% → ② 未触达豁免逻辑（可能改错位置或 decay 量不足）→ 不达标

### 判据④ S2（grv_down reverse）
| 指标 | 基线 | v2031 | ② 预期 |
|---|---|---|---|
| grv_down reverse（median） | 0.727 | 0.682 | **≤0.682 且不反弹 >0.70** |

**判定**：② 后 grv_down reverse 不反弹（≤0.682）→ ③ 效果保留；若 <0.682 继续改善 → ② 状态层治理确实突破 ③ 直接剂量上限（**验证 Part 1 advisory 1 的"反馈链上界 0.52-0.62"论**——② 是状态层治理，理论可突破直接剂量上限，值得关注）。若反弹 >0.70 → ② 干扰 ③，回归失败。
**预期**：不预设必须 ≤0.60；vix 下降 → A2/A3 决策输入变 → sentiment 反馈链改变 → reverse 可能改善。但 vix 降同时 A3 抄底减少（正写少）→ 也可能无改善。**实测裁决**。

### 判据⑤ merged p̂（合并验收目标）
| 指标 | 基线 | v2031 | ② 预期 |
|---|---|---|---|
| p̂ | 0.5152 | 0.5094 | **>0.5094（扭转 ③ 稀释）** |
| CI 下限 | 0.4387 | 0.4330 | **>0.4330** |
| partial 0.55 CI 目标 | — | 差 0.117 | 单批仍不可达（Part 1 Q1 已定论，需 ①②③ 合并） |

**判定**：② 后 p̂ >0.5094 且 CI >0.4330 → ② 扭转 ③ 稀释（credit consistency 回升）；**partial 0.55 CI 不列为 ② 单批闸**（合并验收再判），但 p̂ 必须不跌。
**注意**：vix decay 若压低 A2 收紧 → TIGHTEN 步降 → **credit n_active 可能降**（T 类样本变少）→ 需同步看 n_active（判据⑥-回归）。

### 判据⑥ ③+② 组合回归（防过冲/沉默/归因退化）
| 指标 | v2031 | ② 后须保持 |
|---|---|---|
| S1 桶：≥0.5 尖峰 | 全 0 | **保持全 0**（过冲不因 ② 重演） |
| A1 HIKE | 1（seed42） | **不新增**（≤1） |
| M2 silence diff | 0（credit silence 全 seed diff=0） | **保持 0**（vix 降→A2 收紧变少→silence 可能升，须盯） |
| credit n_active | 16/14/14/17/16 | **不塌方**（≥14/seed，若 decay 过度压低收紧可能塌） |
| tsf（tighten_signal_false） | seed7=0.038 等非零 | **保持非零**（归因分布不变形） |
| EASE wrong（M1） | 15/9/0 | **不增**（② 若动 A2 冷却/豁免需复测） |

**判定**：六项全保持 → ③+② 组合无回归；任一项恶化 → ② 设计引入副作用，回退评审。

---

## 2. 裁决矩阵（② 部署后直接套用）

| 情形 | 判定 |
|---|---|
| ①≤17 ∧ ②vix 回吐 ∧ ③豁免<100% ∧ ④不反弹 ∧ ⑤p̂升 ∧ ⑥全保持 | **② PASS**，合并 ③+② 验收 |
| ①≤17 但 ②③ 未动（vix 存量仍不回吐、豁免仍 100%） | ② **假达标**（wrong 降可能因 A2 决策链偶然），需查明 |
| ①≤17 ∧ ②③ 达标 但 ④反弹>0.70 | ② PASS 但 **③ 效果被破坏**，需评估取舍 |
| ①仍 >17 | ② **FAIL**（M6 未闭环），回退评审 |
| ①≤17 但 ⑥ n_active 塌 / silence 升 >0.05 / 尖峰出现 | ② **FAIL**（副作用），回退评审 |

---

## 3. Part 3 执行计划（arch 部署回传后立即跑）

1. **探针**：复用 `probe_v2031.py`（C:\tmp\r4h_data2\），仅改 `OUT=/tmp/r4h_v204x_all.json` + PROBE_PATH 前缀 → 上传容器跑 5 seed（同 CACHE 全新跑，注意 CACHE_VERSION 若 arch 又 bump 需确认）。
2. **world_state.py 改动 diff**：`docker exec macro-sim diff <(git show HEAD~1:core/world_state.py) core/world_state.py`（若 arch 留 git 历史）或人工核对 L316-327/L277-297 三处 + financial.py L78 豁免行——**确认 ② 到底改了哪个候选**，与判据预期方向对照。
3. **六判据逐项裁决** → 前后对比表（基线/v2031/v204x 三列）→ RoleVerdict 回传 team-lead。
4. **留痕**：C:\tmp\r4h_data2\R4h_Part3_前后对比.md + r4h_v204x_all.json + v204x_seed*.json。

### 预生成探针脚本（arch 部署前先备好，部署后只改版本号即可跑）

```python
# probe_v204x.py —— 复制 probe_v2031.py，改动点：
#   OUT = "/tmp/r4h_v204x_all.json"
#   cal.PROBE_PATH = Path(f"/tmp/r4h_v204x_seed{seed}.json")
#   version_check 增加 world_state 改动标记字段（比对 vix 相关行 hash）
```

（已随本文件留痕：`C:\tmp\r4h_data2\probe_v2031.py` 即为模板，改 2 处输出名即可复用。）

---

## 证据清单（现状锚点，② 部署前固化）

- **world_state.py v2.0.38**：apply_natural_decay L316-327 **缺 vix decay**；apply_bleed_rules L277-280（vix_bleed_threshold=-0.5/steps=3/rate=2.0/max=20.0）、L297（yen_carry vix+5.0）
- **financial.py v2.0.38**：L78 豁免 `vix_stress>1.0`；L101-108 EASE 后 2 步冷却
- **基线 v2.0.37**：vix>1.0=25/38/23/24/23（med 24）、vix_s_final med 4.99、last==max 全 True、TIGHTEN wrong 17（100% 豁免）
- **v2031 v2.0.38**：vix>1.0=24/38/23/24/23、vix_s_final med 4.99、last==max 全 True、TIGHTEN wrong 18（100% 豁免）、merged p̂=0.5094
- **留痕文件**：C:\tmp\r4h_data2\（本文件 + probe_v2031.py + r4h_v2031_all.json + v2031_seed*.json）
