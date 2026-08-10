# R4h ③+② 组合验收清单（qa-r4h2，2026-08-09 v2）

> 状态：**待触发**（arch ② vix 治理部署回传后，team-lead 通知开始执行）
> 用户裁决：③ 并入 ② 批次（**③ 保留不回退**）；② 候选三选一：vix decay / 豁免非连续 / bleed 上限
> **硬约束：勿用 sentiment>-0.3 前提**（实测 sentiment median -0.859，>-0.3 前提恒不满足 = 无效机制）
> ③-A 终版记录：C:\tmp\r4h_data\R4H_QA_RoleVerdict_③A.md（FAIL 但无回归，作为 ② 验收基线引用）
> 环境：SSH nas + `docker exec macro-sim`，前台同步，**禁 TaskOutput**，--read-only，output/ 不落盘 v2032

---

## 0. ③-A 实测基线（v2.0.38，qa-r4h2 独立实测，② 验收的 diff 基准）

> ⚠️ ② 验收对比基线 = **v2.0.38（③-A 后）**，不是 v2.0.37（③-A 前）。③ 已并入保留，② 不得破坏 ③ 已达成状态。

| 项 | ③-A 后基线（v2.0.38） | ② 后应变为 |
|----|----------------------|-----------|
| CACHE_VERSION | 12 | **13**（② 引擎动力学变更 → 反作弊 bump） |
| ARTIFACT_TAG | v2031 | **v2032** |
| VERSION | v2.0.38 | **v2.0.39** |
| simulation.py EASE sentiment | +0.08×m（③ 保留） | 保留不变 |
| calibrator.py a2_action 落盘 | 存在（L735） | 保留存在 |
| world_state.py | 未涉改（③ 未动） | **若 ② 涉改 → 重点核验** |
| 断言数 | 113 | **≥113 + ② 新增单测** |

### ③-A 实测关键数据（v2.0.38，QA 独立跑 5 seed）
- **credit 四指标**：silence 0.490/0.531/0.531/0.469/0.490（median 0.490）；n_active 16/14/14/17/16；act 0.327/0.286/0.286/0.347/0.327；consistency **0.500**/0.714/0.500/0.471/0.688（median 0.500）
- **merged p̂=0.5094**（基 v2.0.37 0.5152，-0.006 结构性稀释）；Wilson CI 下限 **0.4330**
- **S2 grv_down reverse**：42:0.682/7:0.591/123:0.762/2024:0.619/777:0.714，**median 0.682**（consistency_grv_down 0.318/0.409/0.238/0.381/0.286）；warn 档（未达 ≤0.60，未触发 ≥0.727 FAIL）
- **M6 TIGHTEN wrong=18 合计**（42:5/7:3/123:4/2024:5/777:1），100% vix_stress>1.0 豁免；vix_stress>1.0 步 24/38/23/24/23；vix 峰值 162-238（vix_last=vix_max 无 decay）
- **M1 EASE wrong=9**（A2 决策级 c/w/n=15/9/0，rate median 0.714）
- **M2 silence diff**：全 0.000（③ 未超线）
- **M4 flip=0**（全 seed，a2_action 决策级）
- **S1 sentiment（主探针）**：floor_frac 0.54/0.62/0.66/0.72/0.70（median **0.66**）；level_mean -0.733/-0.886/-0.816/-0.899/-0.859（median **-0.859**）；n_active 43/43/43/43/42；act 0.878；silence 0.02-0.041；**无 ≥0.5 尖峰**（max<0.22）
- **a2_action 分布**：TIGHTEN 11/11/13/12/5；EASE 4/4/5/4/7；HOLD 34/34/31/33/37
- **P1**：HOLD 从不归 acted_other；tsf 2/4/3/4/5 非零 ✅
- **P2**：归因双报 seed42 微变（act_gate 0.375→0.5），其余 seed 与基线逐值一致

---

## Phase 1 — 核验 arch ② 改动（trust but verify，git show 逐行）

- [ ] `git show` 逐行核对 ② 候选机制实现（vix decay / 豁免非连续 / bleed 上限 三选一或组合）
- [ ] **重点：核验"勿用 sentiment>-0.3 前提"硬约束**——grep ② 改动中 sentiment 相关前提条件，若出现 `sentiment > -0.3` / `market_sentiment > -0.3` 类判断 → **P0 阻断**（实测 sentiment median -0.859，该前提恒满足 = 机制恒激活 = 伪治理）
- [ ] world_state.py 若涉改：核验 vix 状态字段（vix / vix_stress / bleed 相关）语义不破坏
- [ ] ③ 保留确认：simulation.py EASE sentiment +0.08×m 未被回退；calibrator.py a2_action 落盘仍在
- [ ] CACHE_VERSION=13（或按 arch bump 声明核验）
- [ ] VERSION=v2.0.39；ARTIFACT_TAG=v2032
- [ ] 断言 ≥113 + ② 新增单测（新机制触发条件 + **M6 残差收敛断言** + 与 ③ 共存回归）实质有效
- [ ] `git diff --stat` 改动面确认（无测试文件删除/断言弱化）

## Phase 2 — 反作弊门（P3）

- [ ] 验收全程 `--read-only`（只读已落盘 v2032 工件，禁重跑覆盖，禁 calibration_cache 自证）
- [ ] 容器 grep CACHE_VERSION 生效确认（docker exec grep）
- [ ] 禁 calibration_cache 复用 v12 缓存（检查缓存命中/生成日志，确认 v13 新缓存）
- [ ] 断言数不降（≥113），grep 无新增 skip/.only/xfail/focus
- [ ] 测试文件删除检测：`git diff --name-status HEAD~1 -- tests/ | grep '^D'`（应空）

## Phase 3 — 全量断言独立重跑

- [ ] pytest 全量（禁 skip/.only），≥113 全绿（0 fail 0 error）
- [ ] 记录运行时间/环境，独立于 arch 自检

## Phase 4 — run_probe_acceptance 5 seed 正式验收（ARTIFACT_TAG=v2032 落盘 /tmp）

### 主闸①-⑤（fail-fast，任一 FAIL → 整体 FAIL）
- [ ] ① silence 逐 seed ≤0.50（③-A 后 0.490/0.531/0.531/0.469/0.490）；**M2 硬闸：任一 seed Δsilence>+0.05 → FAIL**
- [ ] ② CI 下限 ≥0.55（③-A 后 0.4330，② 后看组合提升）
- [ ] ③ p̂ ≥0.60（③-A 后 0.5094）
- [ ] ④ per-seed weighted ≥0.50（③-A 后 42:0.449/7:0.529/123:0.467/2024:0.540/777:0.486）
- [ ] ⑤ 回退线 5 条（credit_consistency target 0.60/revert 0.40；grv_down target 0.40/revert 0.20；merged_p target 0.55/revert 0.43；credit_n_active target 18；credit_silence target 0.50）

### 硬闸（任一 FAIL → 整体 FAIL）
- [ ] **M4** flip==0：EASE 后 2 步内 TIGHTEN 决策步数（a2_action 决策级）
- [ ] **M5** credit consistency median ≥0.45（③-A 后 0.500）
- [ ] **M6 TIGHTEN wrong 总数 ≤17（② 裁决闸，唯一 FAIL 线）**：5 seed 合计，>17 → FAIL（② 未清闸）；③-A 后 18（seed42 +1 残差），② 必须清回 ≤17
  - **豁免占比下降 ≠ FAIL**：vix decay 后 vix>1.0 步数减少 → wrong 步豁免占比从 100% 下降是 ② 生效预期证据（wrong 步"现形"），计入 advisory 报告，不触发 FAIL
  - **非豁免 wrong 单独统计**（advisory 报告，不设独立 FAIL 线）；若非豁免 wrong ≥3 步且集中单 seed → 请 arch 解释根因（区分"vix 存量问题已治" vs "TIGHTEN 决策质量问题仍在"——后者即使总数 ≤17 也在 advisory 标注，供合并验收参考）
- [ ] **S2** grv_down reverse：③-A 后 median 0.682（warn），② 后看是否突破 ≤0.60 达标线

### 前置 P1-P4
- [ ] **P1** a2_acted：HOLD 归 tsf 非 acted_other（机读 + 人工抽 3-5 步）
- [ ] **P2** 归因双报：S 类口径 + 完整 steps 口径两表并存（对比 ③-A 后 seed42 act_gate 0.5）
- [ ] **P3** 反作弊门（见 Phase 2）
- [ ] **P4** ARTIFACT_TAG=v2032 落盘 /tmp（非 output/，红线）

## Phase 5 — ③ 回归确认（③ 保留前提下 ② 不得破坏）

> ② 只许治 vix，不许回退 ③ 已达成状态。

- [ ] **S1 桶无 ≥0.5 尖峰**（③-A 后主探针 max<0.22）——② 后不得引入过冲
- [ ] **EASE wrong 9 持平**（③-A 后 15/9/0）——② 后 wrong 不得增加
- [ ] **tsf 非零**（③-A 后 2/4/3/4/5）——② 后不得归零（P1 前置）
- [ ] **a2_action 落盘仍在**（calibrator.py L735）——② 后不得移除
- [ ] EASE sentiment +0.08×m 保留（simulation.py）——③ 核心机制不破坏

## Phase 6 — ② 专项（vix 治理效果，② 独有的验收）

- [ ] **豁免占比 <100%（② 生效预期证据，非 FAIL 线）**：③-A 后 M6 wrong 100% vix_stress>1.0 豁免 → ② 后豁免占比下降 = vix decay 生效（wrong 步"现形"），计入 advisory；**不触发 FAIL**（M6 唯一 FAIL 线 = 总数 ≤17）
- [ ] **非豁免 wrong 单独统计**：② 后 wrong 步中 vix_stress≤1.0 的步数（advisory 报告）；若 ≥3 步且集中单 seed → 请 arch 解释根因（vix 存量已治 vs TIGHTEN 决策质量仍在）
- [ ] **vix>1.0 步数 ≤24（不恶化）**：③-A 后 42:24/7:38/123:23/2024:24/777:23 → ② 后各 seed 不得高于 ③-A 后（尤其 seed7=38 观察是否回落）
- [ ] **vix_stress_final 回落**：vix 存量轨迹（vix_last vs vix_max）——② 若 vix decay：vix_last < vix_max（存量回吐）；若 bleed 上限：峰值封顶
- [ ] **bleed 判据**（若 arch 采用 bleed 上限机制）：bleed 上限生效步数、sentiment 不再恒贴 floor 的改善、与 EASE 写者交互无过冲
- [ ] **vix 峰值**：③-A 后 162-238 → ② 后峰值应下降或封顶（若 vix decay/bleed 上限生效）

## Phase 7 — M7 观察（无硬闸，记录）

- [ ] A1/A3 action 分布前后对比（② 后 vs ③-A 后；A1 CUT 5-6 步、A3 INC/SHORT 均衡不破坏）
- [ ] vix 存量轨迹：vix_stress>1.0 步数、TIGHTEN wrong、vix 峰值、有无 decay（② 核心收敛证据）

## Phase 8 — RoleVerdict 输出（回传 team-lead）

- [ ] verdict：pass / fail（+ 依据）
- [ ] **② 是否清 M6 闸的独立判定**（唯一 FAIL 线：TIGHTEN wrong 总数 ≤17；豁免占比下降 ≠ FAIL 但计入 advisory；非豁免 wrong 单独统计，≥3 步集中单 seed → arch 解释根因）
- [ ] 五闸逐 seed 表（silence/n_active/act/consistency/weighted/CI/p̂）
- [ ] M1-M7 表 + ③ 回归确认表 + ② 专项表
- [ ] p̂ 落档判定：**≥0.616 accept / ≥0.55 partial / <0.55 未过**（合并验收目标 partial 0.55 CI；data Part1 已证明 ③ 单独不可达，② 后看组合效果）
- [ ] 特别标注：① ② 是否清 M6（裁决闸）② 豁免占比/vix 收敛证据 ③ ③ 回归是否被破坏
- [ ] 交付文件：RoleVerdict 文本 + 判定表 + 证据路径（容器内工件 + 本地副本）

---

## 执行入口命令（arch ② 部署后）

```bash
# 容器内
cd /app
grep -n "CACHE_VERSION = " core/calibrator.py            # 期望 13（或按 arch 声明）
grep -n "ARTIFACT_TAG = " scripts/run_probe_acceptance.py # 期望 v2032
grep -n "sentiment" core/simulation.py core/world_state.py 2>/dev/null | grep -i "> -0.3\|> -0\.3"  # 期望空（勿用 sentiment 前提）
sed -n '140,155p' core/simulation.py                      # EASE sentiment +0.08×m 保留
grep -n "a2_action" core/calibrator.py                    # a2_action 落盘仍在
# 断言重跑（本地 repo 同 commit，容器为生产镜像无 pytest）
python tests/test_calibrator_guards.py && python tests/test_narrative_format.py   # ≥113
# 五闸 + 硬闸 + ② 专项：全量 5 seed 探针落 /tmp/r4h_qa_v2032（不落 output/）
python scripts/run_probe_acceptance.py --out-dir /tmp/r4h_qa_v2032 --data-root /app/macro_data
# 只读判定同源
python scripts/run_probe_acceptance.py --out-dir /tmp/r4h_qa_v2032 --data-root /app/macro_data --read-only
```
