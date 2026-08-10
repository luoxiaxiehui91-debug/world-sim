# R4h ③-A 独立验收清单（qa-r4h2，2026-08-09）

> 状态：**待触发**（arch 部署 CACHE_VERSION=12 / v2.0.38 / ARTIFACT_TAG=v2031 / 断言 113 后，team-lead 通知开始执行）
> 验收口径来源：calib-R4h-评审简报 §5（docs/r4h-acceptance-criteria.md 不存在，按简报 §5 执行）
> 环境：SSH nas + `docker exec macro-sim`，前台同步，**禁 TaskOutput**，--read-only

---

## 0. before 快照（v2.0.37 基线，已实测确认，供 diff 对比）

| 项 | 基线值 | ③ 后应变为 |
|----|--------|-----------|
| CACHE_VERSION（calibrator.py:128） | 11 | **12** |
| ARTIFACT_TAG（run_probe_acceptance.py:69） | v2030c | **v2031** |
| VERSION | v2.0.37 | **v2.0.38** |
| simulation.py EASE 分支（L142-147） | 只写 bank_credit_tightening -0.25×m + liquidity_premium -0.08×m，**无 sentiment 写** | L147 后插入 `add("A2","market_sentiment",+K*m)`，K=1.0 → **+0.08×m**（与 TIGHTEN -0.08×m 完全镜像） |
| calibrator.py step_record（L725-739） | 无 a2_action 字段（有 a1/a3/a2_state/vix/vix_stress/credit_spread/bank_credit_tightening/grv_level/per_var） | 加 `"a2_action": snapshot.get("actions",{}).get("A2","HOLD")`（纯测量层，**无额外 CACHE bump**） |
| 断言数 | 110 | **113**（新增 test_a2_ease_writes_sentiment / test_a2_ease_sentiment_symmetry / test_a2_ease_sentiment_t_class，须实质有效不充数） |

## 基线数据（data-r4h 实测，v2.0.37）

- **credit 四指标（逐 seed）**：silence 42:0.490/7:0.531/123:0.531/2024:0.469/777:0.490（median 0.490）；n_active 16/14/14/17/16；act 0.327/0.286/0.286/0.347/0.327；consistency 0.562/0.714/0.500/0.471/0.688（median 0.562）
- **merged p̂=0.5152**，Wilson CI 下限 0.4387
- **S2 grv_down reverse**：42:0.727/7:0.591/123:0.762/2024:0.619/777:0.727，**median 0.727**（达标 ≤0.60，warn 0.60-0.727，≥0.727 FAIL）；全 T 0.488；grv_up 0.227
- **M6 TIGHTEN wrong=17 合计**（42:4/7:3/123:4/2024:5/777:1），100% vix_stress>1.0 豁免；vix_stress>1.0 步 23-38/seed；vix 峰值 162-238（无 decay）
- **M1 EASE wrong=9**（A2 决策级 c/w/n=15/9/0，rate 0.625）
- **M5 credit consistency** 0.562/0.714/0.500/0.471/0.688（median 0.562；硬闸 <0.45 FAIL）
- **S1 sentiment**：floor_frac median 0.694（42:0.531/7:0.633/123:0.694/2024:0.755/777:0.714）；level_mean median -0.880；clamp_frac 0.388-0.653
- **A2 写者**：TIGHTEN 12 步/seed vs EASE 4 步/seed（3:1 负写者主导）

---

## Phase 1 — 核验 arch 改动（trust but verify，git show 逐行）

- [ ] `git show` 逐行核对 simulation.py EASE 分支新增行：`add("A2", "market_sentiment", +K * m)`（K=1.0 → +0.08×m，与 TIGHTEN L141 -0.08×m 完全镜像）
- [ ] 核对传导路径未破坏：clamp [-1,1] 统一走 apply_sentiment_delta；damping 恒 1（A=1.0）；A2→A3(to_A3=0.40)/A10(to_A10=0.35) 衰减 0.5 → 每步 K×0.34375
- [ ] calibrator.py step_record 加 a2_action（纯测量层，无额外 CACHE bump）
- [ ] CACHE_VERSION=12（calibrator.py:128）
- [ ] VERSION=v2.0.38
- [ ] ARTIFACT_TAG=v2031（run_probe_acceptance.py:69）
- [ ] 断言 110→113：新增 3 项须实质有效（非空断言、非 skip、非硬编码实现输出）
- [ ] `git diff --stat` 改动面确认（无测试文件删除/断言弱化）

## Phase 2 — 反作弊门（P3）

- [ ] 验收全程 `--read-only`（只读已落盘工件，禁重跑覆盖，禁 calibration_cache 自证）
- [ ] 容器 grep CACHE_VERSION=12 生效确认（docker exec grep）
- [ ] 禁 calibration_cache 复用 v11 缓存（检查缓存命中/生成日志，确认 v12 新缓存）
- [ ] 断言数不降（113），grep 无新增 skip/.only/xfail/focus
- [ ] 测试文件删除检测：`git diff --name-status HEAD~1 -- tests/ | grep '^D'`（应空）

## Phase 3 — 全量断言 113 独立重跑

- [ ] pytest 全量（禁 skip/.only），113 全绿（0 fail 0 error）
- [ ] 记录运行时间/环境，独立于 arch 自检

## Phase 4 — run_probe_acceptance 5 seed 正式验收（ARTIFACT_TAG=v2031 落盘）

### 主闸①-⑤（fail-fast，任一 FAIL → 整体 FAIL）
- [ ] ① silence 逐 seed ≤0.50（基线 42:0.490/7:0.531/123:0.531/2024:0.469/777:0.490）；**M2 硬闸：任一 seed Δsilence>+0.05 → FAIL（方向闸/豁免问题）**
- [ ] ② CI 下限 ≥0.55
- [ ] ③ p̂ ≥0.60
- [ ] ④ per-seed weighted ≥0.50（5 seed 全过）
- [ ] ⑤ 回退线 5 条（R4D_ROLLBACK_LINES：credit_consistency target 0.60/revert 0.40；grv_down target 0.40/revert 0.20；merged_p target 0.55/revert 0.43；credit_n_active target 18；credit_silence target 0.50）

### 硬闸（任一 FAIL → 整体 FAIL）
- [ ] **M4** flip==0：EASE 后 2 步内 TIGHTEN 决策步数（a2_action 字段，决策级；基线冷却机制应防 flip）
- [ ] **M5** credit consistency median ≥0.45（<0.45 FAIL）
- [ ] **M6** TIGHTEN wrong ≤17（>17 FAIL；基线 17 且 100% 豁免；③ 后若 EASE 写 sentiment → vix bleed 停 → 新涨停止但存量不回吐 → wrong 应≤17）
- [ ] **S2** grv_down reverse：达标 ≤0.60；warn 0.60-0.727；**≥0.727 FAIL**（③ 核心目标：抬离 floor 后 grv_down 方向一致率应改善）

### 前置 P1-P4
- [ ] **P1** a2_acted 前置检查：HOLD 归 tighten_signal_false（tsf）非 acted_other（机读核对 attribution 映射 + 人工抽 3-5 步核对 step_record）
- [ ] **P2** 归因双报：S 类口径（rate_limit/activation_gate/tsf/acted_other）+ 完整 steps 口径，两表并存
- [ ] **P3** 反作弊门（见 Phase 2）
- [ ] **P4** ARTIFACT_TAG=v2031 落盘（output/calib_probe_seed{seed}_v2031.json 存在 + md5 双端一致）

## Phase 5 — M1 EASE wrong 同口径对比

- [ ] 基线：A2 决策级 c/w/n=15/9/0，wrong=9，rate 0.625 → ③ 后 ?（同口径：EASE 决策步 |cs_delta|>2.5 方向区，c=一致/w=wrong/n=neutral）
- [ ] 对比 R4g 口径差说明（data 基线快照 §5：EASE wrong 9 vs R4g 6 的口径差异已记录，复核保持同口径）

## Phase 6 — ③ 专项 3 项（裁决 ② 必要性输入）

- [ ] **① M6 残差**：③ 后 TIGHTEN wrong ≤17 → ② 可轻量或不做；残差高（>17）→ ② 候选三选一单独裁决（vix decay / 豁免非连续前提 / bleed 上限）
- [ ] **② M2 silence diff**：逐 seed Δsilence 与基线比，>+0.05 任一 → FAIL（防豁免关闭重演 R4d 沉默）
- [ ] **③ S1 sentiment 桶**：floor_frac（0.694→? 应下降）、level_mean（-0.880→? 应抬升）、clamp_frac；**抬离 floor 但无 ≥0.5 尖峰**（尖峰=过冲信号）

## Phase 7 — M7 观察（无硬闸，记录）

- [ ] A1/A3 action 分布前后对比（step_record 已落 a1/a3；A3 -0.4 边界复激活预期）
- [ ] vix 存量轨迹：vix_stress>1.0 步数、TIGHTEN wrong、vix 峰值、有无 decay（③ 后 bleed 停但存量不回吐 → ② 部分收敛证据）

## Phase 8 — RoleVerdict 输出（回传 team-lead）

- [ ] verdict：pass / fail（+ 依据）
- [ ] 五闸逐 seed 表（silence/n_active/act/consistency/weighted/CI/p̂）
- [ ] M1-M7 表
- [ ] ③ 专项 3 项结论
- [ ] p̂ 落档判定：**≥0.616 accept / ≥0.55 partial / <0.55 未过**
- [ ] 特别标注：① S2 reverse 是否达标（③ 核心目标）② M6 残差（② 裁决输入）③ M2 silence 是否超线（方向闸/豁免问题）
- [ ] 交付文件：RoleVerdict 文本 + 判定表 + 证据路径（容器内工件 + 本地副本）

---

## 执行入口命令（部署后）

```bash
# 容器内
cd /app
grep -n "CACHE_VERSION = " core/calibrator.py          # 期望 12
grep -n "ARTIFACT_TAG = " scripts/run_probe_acceptance.py  # 期望 v2031
sed -n '140,150p' core/simulation.py                    # EASE sentiment +0.08×m
grep -n "a2_action" core/calibrator.py                  # 期望存在（1+ 处）
pytest tests/ -q                                        # 期望 113 passed（禁 skip/.only）
python scripts/run_probe_acceptance.py --read-only      # 只读判定 v2031 工件
# 或（需新跑时）：
python scripts/run_probe_acceptance.py                  # 全量 5 seed（确认 ARTIFACT_TAG=v2031 后）
```
