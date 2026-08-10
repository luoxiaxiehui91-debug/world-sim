# R4h ①②③ 三批合并验收清单（qa-r4h2，2026-08-09 v4）

> 状态：**待触发**（arch ① 定稿 cap17 + act_prob 0.76 部署 v2033 后，team-lead 通知开始执行）
> 用户裁决：① 批次（A2 决策级 EASE wrong 治理）；② 保持现状不回退；③ 已并入保留
> **① 定稿参数：cap 19→17（①-C）+ activation_prob 0.70→0.76（①-B）+ ease_ok 方向闸（①-A）**
> ① 方案交叉参考：C:\tmp\r4h_data\R4H_QA_交叉参考_①方案.md（qa 建议放行有条件）
>
> ⚠ **假复现更正（2026-08-10）**：本文 L16-33"① 定稿预期"及 qa 裁决段基于 A3 soul 缺失环境（config 放 /tmp → load_agents soul 路径 dirname(config)/../souls 解析失败 → A3 soul={} 回退旧决策），容器真实部署不可复现。权威结论见 C:\tmp\r4h_data2\R4h_Part4_前后对比.md §5。**容器实测（v2.0.40/CACHE 14/v2033）：EASE correct 16 / M6 13 / silence 4/5 超（median 0.531，seed123 0.633 最差）/ credit 未回池 / p̂ 0.4894（CI 0.4063）/ S2 0.636 / consistency 0.750。**
> ② 终版记录：C:\tmp\r4h_data\R4H_QA_RoleVerdict_②A.md（M6 清闸 PASS 但整体 FAIL，合并验收引用）
> 环境：SSH nas + `docker exec macro-sim`，前台同步，**禁 TaskOutput**，--read-only，output/ 不落盘 v2033

---

## 0. ② 终版基线（v2.0.39） vs ① 容器实测（v2.0.40）

> ⚠️ ① 验收对比基线 = **v2.0.39（② 终版）**。③ 并入保留、② 保持现状不回退，① 不得破坏 ③② 已达成状态。
> ⚠ **本表"① 容器实测"列为 2026-08-10 容器真实部署数值（A3 soul 完整）**。原 v4 阶段"① 定稿预期"（EASE 18/M6 12/silence 2/5/credit 回池/p̂ 0.5729/S2 0.529/cons 0.789）已被证伪为假复现（A3 soul 缺失，config 放 /tmp），见头部更正块。

| 指标 | ② 终版（v2.0.39） | **① 容器实测（v2.0.40/v2033）** | 判定 |
|------|------------------|-------------------------------|------|
| EASE correct | 15 | **16** | ✓ 防伪线 PASS（假复现预期曾为 18） |
| EASE wrong | 8 | **0** | ✓ 真实达成（ease_ok 方向闸收编） |
| M6 TIGHTEN wrong | 16 | **13** | ✓ ≤17（假复现预期曾为 12） |
| M4 flip | 0 | 0 | ✓ |
| silence 超线 seed 数 | 4/5 | **4/5 超**（median 0.531，seed123 0.633 最差） | ⚠ 未达 ≤2/5（假复现预期 2/5） |
| credit 回池 | 出池（2 变量） | **未回池（2 变量）** | ⚠ 未达成（假复现预期回池 3 变量） |
| merged p̂ / CI | 0.4948 / 0.4118 | **0.4894 / 0.4063** | ⚠ 未过 partial 0.55（假复现预期 0.5729） |
| S2 reverse median | 0.682 | **0.636** | ⚠ 未达 ≤0.60（假复现预期 0.529） |
| credit consistency | 0.538 | **0.750** | ✓ 改善 |

### qa 已裁决的 ① 口径（v4 更新）——⚠ 全部基于假复现预期，已更正
> **2026-08-10 更正**：以下 v4 裁决（seed7 噪声豁免、seed123 按硬线 ≤2/5 达标、p̂ partial 点估、EASE correct 18、S2 达标）均基于假复现工件，**容器实测不成立**。实际裁决：收编 EASE wrong 治理（8→0 真实有效）、credit 回池/p̂/S2 三项不通过、挂起转后续 silence 治理（见 R4h_Part4_前后对比.md §5）。原文保留如下，仅作历史实录——
- **seed7 silence 0.51**：边界噪声豁免（±0.02 噪声带，超线 seed 在 42/7/777 漂移）~~（假复现；容器实测 silence 4/5 超，median 0.531）~~
- **seed123 silence 0.531**：**按硬线 ≤2/5 达标**（seed7+seed123=2/5）~~（假复现；容器实测 seed123 0.633，为最差 seed）~~
- **N 132（161→132，降 18%）CI 口径**：**接受"p̂ partial 点估验收 + CI advisory"**~~（假复现；容器实测 credit 未回池，p̂ 0.4894/CI 0.4063 未过 0.55）~~
- **EASE correct 18 ≥15**：防伪线 PASS~~（假复现；容器实测 16）~~
- **S2 0.529 ≤0.60 达标**~~（假复现；容器实测 0.636，未达 ≤0.60）~~

---

## 0. ② 终版基线（v2.0.39，qa-r4h2 独立实测，① 验收的 diff 基准）

> ⚠️ ① 验收对比基线 = **v2.0.39（② 终版）**。③ 并入保留、② 保持现状不回退，① 不得破坏 ③② 已达成状态。

| 项 | ② 终版基线（v2.0.39） | ① 后应变为 |
|----|----------------------|-----------|
| CACHE_VERSION | 13 | **14**（① 引擎动力学变更 → 反作弊 bump） |
| ARTIFACT_TAG | v2032 | **v2033** |
| VERSION | v2.0.39 | **v2.0.40** |
| world_state.py vix 均值回归 | 0.80/0.20（L351） | 保留不变（② 不回退） |
| world_state.py yen_carry cap | 19.0（L267+出血5） | **17.0（①-C 生效，v2.0.40 已部署）**；L47 旧文"保留不变"为残留，应以 L5 "cap 19→17" 为准 |
| simulation.py EASE sentiment | +0.08×m（③ 保留） | 保留不变（③ 不回退） |
| calibrator.py a2_action 落盘 | L738 | 保留存在 |
| **simulation.py A2 决策逻辑** | 未涉改（② 未动） | **① 核心改动（EASE wrong 治理）** |
| 断言数 | 120 | **≥120 + ① 新增** |
| **② P2 修复** | CACHE 注释参数过期 + commit message 数字 | **① 应回填修正** |

### ② 终版实测关键数据（v2.0.39，QA 独立跑 5 seed）
- **credit 四指标**：silence 0.510/0.571/0.551/0.510/0.490（**median 0.510，4/5 超 0.50**）；n_active 15/12/13/15/16；act 0.306/0.245/0.265/0.306/0.327；consistency 0.533/0.583/0.538/0.533/0.688（median 0.538）
- **merged p̂=0.4948**（③ 后 0.5094，-0.0146）；Wilson CI 下限 **0.4118**；**N=135.0（credit 出池，eligible 池=['market_sentiment','liquidity_premium']）**
- **M6 TIGHTEN wrong=16 合计**（42:4/7:5/123:3/2024:3/777:1），≤17 清闸；**exempt_pct 仍 100%、非豁免 wrong=0**；vix>48 步 21-36
- **S2 grv_down reverse**：42:0.682/7:0.591/123:0.762/2024:0.619/777:0.714，**median 0.682**（warn 档，未达 ≤0.60）
- **M1 EASE wrong=8**（A2 决策级 c/w/n=15/8/0，rate median 0.714；v2.0.37 基线 rate 0.652）
- **M2 silence diff（vs ③-A）**：+0.020/+0.040/+0.020/+0.041/0.000 全 ≤+0.05 PASS
- **M4 flip=0**；**M5 credit consistency median 0.538**
- **S1 sentiment（主探针）**：floor_frac median 0.66；level_mean median -0.861；n_active 42-44；**ge05 全 0（无 ≥0.5 尖峰）**
- **vix**：峰值 53.28-53.38（③-A 后 162-238）；vix_stress>1.0 步 21-36；vix_last<vix_max（存量回吐）
- **tsf**：4/3/5/6/5 全非零；**a2_action 落盘 L738 仍在**

---

## Phase 1 — 核验 arch ① 改动（trust but verify，git show 逐行）

- [ ] `git show` 逐行核对 ① A2 决策级改动范围（simulation.py gm_resolve 决策逻辑？核心）
- [ ] **P0 阻断项保留**：grep `sentiment>-0.3` 前提（发现即阻断）；③ EASE +0.08×m 保留（simulation.py L152）；② vix 均值回归 0.80/0.20（world_state.py L351）+ yen_carry cap **17.0**（L267+出血5，①-C 生效后；L71 旧文 "cap 19" 为残留）保留；world_state.py 涉改范围不扩散（① 若涉改须声明且不破坏 vix 治理）
- [ ] ① 是否触及 a2_action 落盘（calibrator.py L738 不得移除）
- [ ] CACHE_VERSION=14（或按 arch bump 声明核验）；VERSION=v2.0.40；ARTIFACT_TAG=v2033
- [ ] 断言 ≥120 + ① 新增单测（A2 决策级 EASE wrong 触发条件 + 与 ③② 共存回归）实质有效
- [ ] `git diff --stat` 改动面确认（无测试文件删除/断言弱化）
- [ ] **② P2 修复确认**：CACHE bump 注释参数（0.85/0.15、<12 → 应改为 0.80/0.20、<19）是否回填；commit message 数字（seed42 silence +0.061 → +0.020）是否修正

## Phase 2 — 反作弊门（P3）

- [ ] 验收全程 `--read-only`（只读已落盘 v2033 工件，禁重跑覆盖，禁 calibration_cache 自证）
- [ ] 容器 grep CACHE_VERSION 生效确认（docker exec grep）
- [ ] 禁 calibration_cache 复用 v13 缓存（检查缓存命中/生成日志，确认 v14 新缓存）
- [ ] 断言数不降（≥120），grep 无新增 skip/.only/xfail/focus
- [ ] 测试文件删除检测：`git diff --name-status HEAD~1 -- tests/ | grep '^D'`（应空）

## Phase 3 — 全量断言独立重跑

- [ ] pytest 全量（禁 skip/.only），≥120 全绿（0 fail 0 error）
- [ ] 记录运行时间/环境，独立于 arch 自检

## Phase 4 — 三批合并五闸（ARTIFACT_TAG=v2033 落盘 /tmp）

### 主闸（任一 FAIL → 整体 FAIL）
- [ ] ① **绝对 silence 逐 seed ≤0.50（关键裁决）**：② 后 0.510/0.571/0.551/0.510/0.490（4/5 超线）→ ① 后应拉回 **≤2/5 超线或全过**（① 治理 EASE wrong 是否顺带改善 credit 沉默？）；超线 seed 数不减 → ① 未达核心
- [ ] ② CI 下限 ≥0.55（② 后 0.4118）
- [ ] ③ p̂ ≥0.60（② 后 0.4948）
- [ ] ④ per-seed weighted ≥0.50（② 后 42:0.443/7:0.530/123:0.458/2024:0.540/777:0.486）
- [ ] ⑤ 回退线 5 条（credit_consistency target 0.60/revert 0.40；grv_down target 0.40/revert 0.20；merged_p target 0.55/revert 0.43；credit_n_active target 18；credit_silence target 0.50）

### 硬闸（任一 FAIL → 整体 FAIL）
- [ ] **M6 ≤17（① 后不得反弹）**：② 后 16，① 动 A2 决策 → 防 TIGHTEN wrong 反弹 >17
- [ ] **M4 flip==0**：EASE 后 2 步内 TIGHTEN 决策步数（a2_action 决策级）
- [ ] **M5 credit consistency median ≥0.45**（② 后 0.538）
- [ ] **S2 grv_down reverse 不反弹 >0.70**：② 后 0.682，① 治理 EASE wrong 若改变 sentiment 写者 → 防 S2 反弹（>0.70 FAIL）
- [ ] **EASE wrong 专项（① 核心目标）**：② 后 wrong 8（rate 0.714；v2.0.37 基线 rate 0.652）→ ① 后 wrong 应**下降**（rate 提升）；wrong 不降或上升 → ① 未达核心（专项 FAIL 线：wrong ≥8 即未改善？以 arch 方案承诺目标为准交叉核验）

### 前置 P1-P4
- [ ] **P1** a2_acted：HOLD 归 tsf 非 acted_other（机读 + 人工抽 3-5 步）
- [ ] **P2** 归因双报：S 类口径 + 完整 steps 口径两表并存（对比 ② 后 seed42 act_gate 0.5）
- [ ] **P3** 反作弊门（见 Phase 2）
- [ ] **P4** ARTIFACT_TAG=v2033 落盘 /tmp（非 output/，红线）

## Phase 5 — ③② 回归确认（① 不得破坏 ③② 已达成状态）

> ① 只许治 A2 EASE wrong，不许回退 ③（sentiment 写者）②（vix 治理）。

- [ ] **S1 桶无 ≥0.5 尖峰**（② 后主探针 ge05 全 0）
- [ ] **tsf 非零**（② 后 4/3/5/6/5）
- [ ] **a2_action 落盘仍在**（calibrator.py L738）
- [ ] **EASE +0.08×m 保留**（simulation.py L152，③ 核心）
- [ ] **yen_carry cap 生效**（world_state.py vix_delta<**17**，①-C 生效后；L121 旧文 "vix_delta<19" 为残留）；vix 峰值不反弹 >60（② 后 53.28）
- [ ] **EASE 决策语义未破坏**（① 治理 wrong 同时不得误伤 correct EASE——EASE correct 不降）

## Phase 6 — ① 专项（A2 EASE wrong 治理效果）

- [ ] **EASE wrong 逐 seed 明细**：② 后 42:2/7:1/123:3/2024:1/777:2（合计 8）→ ① 后 wrong 分布（c/w/n 三列，rate 逐 seed）
- [ ] **EASE wrong 步的上下文**：wrong 步 cs_delta>2.5 时 A2 决策为何 EASE（方向闸/冷却/激活条件？）——① 治理后这些步的处置
- [ ] **两线冲突解法可证伪性**：arch 方案落盘后交叉参考——① 的 A2 决策改动若与 ② 的 vix 触发线/③ 的 sentiment 写者有交互，须可证伪（单测锁定）
- [ ] **EASE correct 不降**：correct EASE 步数（② 后 15）不得下降（防"一刀切禁 EASE"伪治理）

## Phase 7 — M7 观察（无硬闸，记录）

- [ ] A1/A3 action 分布前后对比（① 后 vs ② 后；A1 CUT 5-6 步、A3 INC/SHORT 均衡不破坏）
- [ ] vix 存量轨迹：vix 峰值、vix>48 步数、vix_stress_final（① 动 A2 决策 → 防 vix 治理回退）

## Phase 8 — p̂ 合并落档 + 统计显著性评估

- [ ] **p̂ 落档**：≥0.616 accept / ≥0.55 partial / <0.55 未过（② 后 0.4948）
- [ ] **统计显著性评估（关键新增）**：credit 出池后 eligible 池=2 变量、N=135（② 后）——Wilson CI 下限 0.4118、宽度 ±0.083；评估：① 后若 credit 回池（silence 拉回）N 恢复 → p̂ 比较口径须注明；若 credit 仍出池，N≈135 时 p̂ 是否统计上可判定（CI 宽度 vs 0.55 线距离）
- [ ] 合并验收对比链：v2.0.37（0.5152）→ ③（0.5094）→ ②（0.4948）→ ①（?）——三批合并后 p̂ 趋势 + 结构性变化（credit 出池/回池）

## Phase 9 — RoleVerdict 输出（回传 team-lead）

- [ ] verdict：pass / fail（+ 依据）
- [ ] **① 是否清 EASE wrong 闸**（wrong 下降 + rate 提升）
- [ ] **① 是否拉回绝对 silence**（4/5 超线 → ≤2/5 或全过）
- [ ] 三批合并五闸逐 seed 表（silence/n_active/act/consistency/weighted/CI/p̂）
- [ ] ③② 回归确认表 + ① 专项表 + M1-M7 表
- [ ] p̂ 合并落档 + 统计显著性评估（N 135 口径）
- [ ] ② P2 修复确认（CACHE 注释/commit message）
- [ ] 交付文件：RoleVerdict 文本 + 判定表 + 证据路径

---

## 执行入口命令（arch ① 部署 v2033 后）

```bash
# 容器内
cd /app
grep -n "CACHE_VERSION = " core/calibrator.py            # 期望 14（或按 arch 声明）
grep -n "ARTIFACT_TAG = " scripts/run_probe_acceptance.py # 期望 v2033
grep -rn "sentiment" core/ --include='*.py' | grep -- "-0.3"  # 期望空（P0）
sed -n '150,154p' core/simulation.py                      # EASE +0.08×m 保留（③）
grep -n "world.vix = world.vix" core/world_state.py       # vix 回归保留（②）
grep -n "vix_yen_carry_bleed_max" core/world_state.py     # cap 17 生效（①-C，v2.0.40；旧文 "cap 19 保留" 为残留）
grep -n "a2_action" core/calibrator.py                    # 落盘仍在
# 断言重跑（本地 repo 同 commit，容器为生产镜像无 pytest）
python tests/test_calibrator_guards.py && python tests/test_narrative_format.py   # ≥120
# 三批合并五闸：全量 5 seed 探针落 /tmp/r4h_qa_v2033（不落 output/）
python scripts/run_probe_acceptance.py --out-dir /tmp/r4h_qa_v2033 --data-root /app/macro_data
# 只读判定同源
python scripts/run_probe_acceptance.py --out-dir /tmp/r4h_qa_v2033 --data-root /app/macro_data --read-only
```
