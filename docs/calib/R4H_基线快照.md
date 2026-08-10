# R4h 基线数据快照（data-r4h，2026-08-09）

## RoleVerdict
- **verdict**: PASS（基线采集闭环：v2.0.37 行为与 R4e 基线逐 seed 完全一致；归因映射修复已确认——R4e 的 acted_other 全部迁移为 tighten_signal_false，数值 0.038/0.115/0.13/0.125 与团队预期完全吻合）
- **advisory**: ① team-lead 提到的 "R4g 实测 26 步全因豁免" 是 R4g 阶段二中间态（acceptance 05:11），当前 v2.0.37 基线为 **17 步**（4/3/4/5/1，100% 豁免）——勿混用；② sentiment grv_down 桶 reverse 基线实测 **0.727**（非 0.685），全 T 类 reverse 实测 **0.488**（0.456 实为 seed42 weighted 值）——建议以本快照实测为准；③ EASE 方向一致率实测 0.625（15/24），与 R4g 轮 0.643 存在口径差，TIGHTEN 0.396 完全一致
- **evidence**: 容器内 /tmp/r4h_baseline2.json + /tmp/r4h_probe_seed{seed}.json + /tmp/r4h_detail.json；本地 C:\tmp\r4h_data\ 全套副本

---

## 1. v2.0.37 主基线（credit 四指标，对照 R4e 基线 ✓ 逐 seed 一致）

| seed | silence | n_active | act_frac | consistency | weighted | R4e 对照（一致） |
|------|---------|----------|----------|--------------|----------|------------------|
| 42   | 0.490   | 16       | 0.327    | 0.562        | 0.456044 | 0.490/16/0.327/0.562 ✓ |
| 7    | 0.531   | 14       | 0.286    | 0.714        | 0.534466 | 0.531/14/0.286/0.714 ✓ |
| 123  | 0.531   | 14       | 0.286    | 0.500        | 0.480932 | 0.531/14/0.286/0.500 ✓ |
| 2024 | 0.469   | 17       | 0.347    | 0.471        | 0.540250 | 0.469/17/0.347/0.471 ✓ |
| 777  | 0.490   | 16       | 0.327    | 0.688        | 0.478309 | 0.490/16/0.327/0.688 ✓ |
| **median** | **0.490** | **16** | **0.327** | **0.562** | **0.481** | |

- **merged p̂ = 0.5152**（N=161.7, K=83.3, eligible 池=3 变量），**Wilson CI 下限 = 0.4387**
- 与 R4g revert_verify（/tmp/r4g_revert_verify/acceptance_v2030c.json）p̂/CI/weighted 完全一致 → 确认容器 = v2.0.37

## 2. sentiment 专属基线（③ 的对比基准）

### 2a. sentiment 各桶 reverse 占比（1−consistency，T 类口径）

| seed | reverse 全T | reverse grv_up | reverse grv_down | n_up/n_down |
|------|------------|----------------|------------------|-------------|
| 42   | 0.571      | 0.400          | 0.727            | 20/22       |
| 7    | 0.364      | 0.136          | 0.591            | 22/22       |
| 123  | 0.488      | 0.227          | 0.762            | 22/21       |
| 2024 | 0.372      | 0.136          | 0.619            | 22/21       |
| 777  | 0.488      | 0.238          | 0.727            | 21/22       |
| **median** | **0.488** | **0.227** | **0.727** | |

⚠ team-lead 给的 grv_down 基线 0.685 / 全T 0.456 与本实测（0.727/0.488）不符——0.456 实为 seed42 的 weighted_consistency_exact；建议以本快照 0.727/0.488 为准。

### 2b. A2 写 sentiment 分布（主探针 50 步窗口，A2 action 计数）

| seed | TIGHTEN（写 sentiment -0.08） | EASE（不写 sentiment） | HOLD | NO_ACTION |
|------|-------------------------------|------------------------|------|-----------|
| 42   | 13                            | 4                      | 2    | 31        |
| 7    | 12                            | 4                      | 4    | 30        |
| 123  | 14                            | 5                      | 3    | 28        |
| 2024 | 12                            | 4                      | 4    | 30        |
| 777  | 6                             | 7                      | 5    | 32        |
| **median** | **12**                    | **4**                  | 4    | 30        |

→ **确认负写者主导**：TIGHTEN 写者（-0.08/步）median 12 vs EASE 不写 sentiment（4/步），比值 3:1。sentiment 贴 floor 根因在负写者步数压倒正写者。

### 2c. sentiment 字段值分布（是否恒贴 floor=-1.0）

| seed | floor_frac（≤-0.98 占比） | level_mean |
|------|---------------------------|-----------|
| 42   | 0.531                     | -0.750    |
| 7    | 0.633                     | -0.901    |
| 123  | 0.694                     | -0.841    |
| 2024 | 0.755                     | -0.921    |
| 777  | 0.714                     | -0.880    |
| **median** | **0.694**            | **-0.880** |

→ **确认恒贴 floor**：median 69.4% 步数贴 floor，均值 -0.88。③ 实施前后对比的关键基线。

## 3. vix bleed 基线

| seed | vix_stress>1.0 步数 | target_dir=ease 步数 | TIGHTEN wrong 步数 | 其中豁免放行 |
|------|---------------------|----------------------|--------------------|--------------|
| 42   | 25                  | 24                   | 4                  | 4（100%）    |
| 7    | 38                  | 24                   | 3                  | 3（100%）    |
| 123  | 23                  | 24                   | 4                  | 4（100%）    |
| 2024 | 24                  | 24                   | 5                  | 5（100%）    |
| 777  | 23                  | 24                   | 1                  | 1（100%）    |
| **合计/median** | median 24 | 24               | **17 合计**        | **17/17 = 100% 豁免** |

⚠ **口径澄清**：team-lead 说 "R4g 实测 26 步全因豁免" 是 R4g 阶段二（v2.0.36 中间态，acceptance_v2030c.json 05:11 的 n_tighten_fail=4/7/6/5/4=26）。当前 **v2.0.37 基线为 17 步**（4/3/4/5/1），且 100% 由 vix_stress>1.0 极端豁免放行（与 /tmp/r4g_revert_verify 05:48 完全一致）。

## 4. 归因分布基线（修正映射后，credit S 类口径）

| seed | activation_gate | rate_limit | tighten_signal_false | acted_other | n_s |
|------|-----------------|------------|----------------------|-------------|-----|
| 42   | 0.375           | 0.625      | 0.000                | 0.000       | 24  |
| 7    | 0.269           | 0.692      | **0.038**            | 0.000       | 26  |
| 123  | 0.192           | 0.692      | **0.115**            | 0.000       | 26  |
| 2024 | 0.217           | 0.652      | **0.130**            | 0.000       | 23  |
| 777  | 0.458           | 0.417      | **0.125**            | 0.000       | 24  |

→ **归因映射修复确认**：R4e 基线 credit acted_other=0.0/0.038/0.115/0.13/0.125 → v2.0.37 全部迁移为 tighten_signal_false（0.0/0.038/0.115/0.13/0.125），**tsf 非零完全吻合 team-lead 预期**；act_gate/rate_limit 保持 R4e 值不变。

### 4b. 完整 steps a2_state 双口径（全部 49 delta 步分布，非仅 S 类）

| seed | rate_limit | activation_gate | acted_other | tighten_signal_false |
|------|------------|-----------------|-------------|----------------------|
| 42   | 18         | 13              | 16          | 2                    |
| 7    | 20         | 10              | 15          | 4                    |
| 123  | 21         | 7               | 18          | 3                    |
| 2024 | 19         | 10              | 16          | 4                    |
| 777  | 18         | 14              | 12          | 5                    |

（完整 steps 口径 acted_other 非零 = A2 行动写 lp 不写 credit/sentiment 的步，与 S 类口径语义不同）

## 5. EASE/TIGHTEN 方向一致率基线（A2 实际 action vs cs_delta 期望方向）

| seed | EASE c/w/n | EASE rate | TIGHTEN c/w/n | TIGHTEN rate(cw) | rate(含neutral) |
|------|------------|-----------|---------------|------------------|------------------|
| 42   | 2/2/0      | 0.500     | 4/4/4         | 0.500            | 0.333            |
| 7    | 3/1/0      | 0.750     | 5/3/3         | 0.625            | 0.455            |
| 123  | 2/3/0      | 0.400     | 4/4/5         | 0.500            | 0.308            |
| 2024 | 3/1/0      | 0.750     | 4/5/3         | 0.444            | 0.333            |
| 777  | 5/2/0      | 0.714     | 4/1/0         | 0.800            | 0.800            |
| **合计** | **15/9/0** | **0.625** | **21/17/15**  | **0.553**        | **0.396**        |

- **TIGHTEN rate(含 neutral)=0.396 与 R4g 实测完全一致** ✓（R4g 0.396）
- **EASE rate=0.625（15/24）**，R4g 实测 0.643、EASE wrong 6 步——本探针 wrong=9 步，存在口径差（R4g 可能用 credit target t 符号或阈值不同），建议 qa 复核 R4g 口径
- EASE 决策步全部落在 |cs_delta|>2.5 方向区（n=0 neutral），阈值 2.5/0.0/credit_t 三口径 EASE 结果一致

## 6. 方法（只读探针）
- 环境：SSH nas + `docker exec macro-sim`，前台同步，无后台轮询
- 探针：`cal.PROBE_PATH` monkeypatch 到 `/tmp/r4h_probe_seed{seed}.json`（未污染 output/ 根，未读 qa 正在写的 v2031 工件）
- 统计复用 `scripts/run_probe_acceptance.py` 的 `rebuild_samples/var_stats/merged_pooled/per_seed_weighted`（判定同源口径）
- A2 action / vix / sentiment level 经 `MacroSimModel.step` monkeypatch 逐步捕获，按 world.step_label 区分主探针 vs ease 子探针
- merged p̂=0.5152 / CI=0.4387 与 R4g revert_verify acceptance 完全一致 → 探针路径正确性交叉验证

## 7. 交付文件（本地副本 C:\tmp\r4h_data\）
- `r4h_baseline2.json`（主快照，per-seed 全指标 + median + merged）
- `r4h_baseline.json`（v1 快照，交叉验证用）
- `r4h_detail.json`（逐 delta 步明细：a2/cs_delta/vix/credit_t，41KB）
- `r4h_probe2.py` / `r4h_probe.py` / `r4h_detail.py` / `r4h_direction.py`（探针脚本）
- 容器内证据：`/tmp/r4h_probe_seed{42,7,123,2024,777}.json`、`/tmp/r4h_baseline2.json`（md5 72d210ce…）
