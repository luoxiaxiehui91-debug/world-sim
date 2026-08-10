# R4h ① 三批合并验收 RoleVerdict（qa-r4h3）

> 执行方式标注：**重算核验（非独立跑探针）**——本会话 Bash/PowerShell 执行层故障（所有命令含 echo/printf/SSH 返回空 stdout，exit 0 但无输出；沙箱内外均无效），无法 SSH 独立跑探针/断言/git show。以下结论基于 data-r4h3 容器实测 raw JSON（r4h_v2033_all.json + v2040_a76c17 工件）做**独立重算核验**（逐 seed 加总、median 排序、与 arch 工件交叉比对），非我在容器内独立跑出的原始数据。
> 验收对象：v2.0.40 / CACHE 14 / ARTIFACT v2033（①-A ease_ok + ①-B act_prob 0.76 + ①-C cap 17）
> 基线：v2.0.39 ② 终版（commit bc32f9d，qa-r4h2 实测）
> 日期：2026-08-10

---

## 0. 部署 commit hash 核验状态

- **commit（team-lead 提供，部署已完成）**：引擎 e636c0c（v2.0.40 / CACHE 14 / ARTIFACT v2033）+ docs aac8639（变更8 登记）+ d11a89b（实测段落修正）
- **git show e636c0c 核验**：❌ **未执行**——工具执行层故障无法 SSH。**标注：commit hash 由 team-lead 提供，未经我独立 git show 核验**（工具恢复后立即补）。
- **部署生效间接核验**（data-r4h3 容器实测 note + Part4 文档 §0）✅：CACHE_VERSION=14、VERSION=v2.0.40、financial.py L97-106 有 ease_ok 方向闸、world_state.py L544 cap 19→17、agents.yaml L40 activation_prob=0.76、simulation.py L152 EASE +0.08 保留。**容器部署与 ① 规格一致（间接证据，非我独立 SSH 核验）。**

---

## 0b. 最终口径更新（data-r4h3 E 项决定性证据，2026-08-10 已独立核验）

**arch 声称的"credit 回池 + p_hat 0.5729"判定为假复现**——根因已由 data-r4h3 E 项隔离实验锁定：
- arch verify 脚本把 config 放 **/tmp** → A3 soul 加载路径解析到不存在的 `/souls` → **A3 soul={} 空，回退旧 if-else 决策**（无 45% 超卖反弹派系）
- 容器真实部署 **/app/config/agents.yaml**（soul 完整加载）→ 同一 config（md5 完全相同 17bba346）读 /tmp 得 0.5729、读 /app 得 **0.4626**
- 隔离实验（monkeypatch / random.seed 前置）均不影响结果 → **不是随机分叉，是 config 路径导致 soul 加载差异**
- **E 项容器真实实测（A2=0.80+A3=0.80）**：p_hat **0.4626** / CI 0.3808 / M6 **20**（反弹）/ sil 4/5 超 0.51 / S2 0.65——**0.80 也无收益，未回池**
- **结论：验收以容器真实部署实测为准；arch 工件（v2040_a76c17 / acceptance_v2032.json 0.5729）标注为"无 A3 soul 环境产物"，不可作为验收依据。**

> **环境状态留档（data-r4h3 确认，2026-08-10）**：E 项探针期间容器 config 曾被临时改 0.80/0.80，**已恢复定稿**（md5 5048c4fd，A2=0.76/A3=0.75，CACHE 14，v2033 状态），当前容器环境干净无残留污染。后续补跑独立探针可直接在定稿状态执行（工具恢复后）。

---

## 0c. 用户最终裁决（team-lead 转达，2026-08-10）

**R4h ① 裁决 = 收编 EASE 治理**（用户已确认）：
- ✅ ease_ok 机制**确认收编**（EASE wrong 8→0）
- ❌ credit 回池 / p̂ / S2 **不通过**，挂起为后续 silence 治理目标
- ✅ **保持 v2.0.40 部署**（不回退）

## 0d. 工具恢复后 4 项补测结果（2026-08-10，独立执行）

| 补测项 | 结果 | 证据 |
|---|---|---|
| git show e636c0c 核验 | ✅ **通过** | commit e636c0c030967c0caa012e78f8b8beca594e1465 存在：标题 "R4h ① A2 决策级治理——ease_ok 方向闸 + act_prob 0.76 + cap 17 + CACHE 14 (v2.0.40)"，diff 含 financial.py ease_ok（+6）、agents.yaml 0.70→0.76、world_state.py cap 17、test_calibrator_guards.py（+52 行） |
| 断言 **130** 重跑 | ✅ **45/45 全绿** | 容器内运行：test_calibrator_guards.py **34 组全过**（含新增 ease_ok 3 态 + M4 flip 4 测试）、test_narrative_format.py **11 组全过**；断言数核实：基线 bc32f9d=120（108+12）→ ① e636c0c=**130**（118+12，+10） |
| 反作弊门（git diff） | ✅ **5/5 通过** | ① 无测试文件删除 ② 无 skip/xfail/.only 新增 ③ 无框架配置篡改 ④ 断言数 120→130 **上升**（未下降）⑤ 新增为真实行为断言（ease_ok 方向闸 3 态 + M4 flip，非硬编码实现输出） |
| P0 sentiment>-0.3 扫描 | ✅ **未命中** | 5 seed level_mean=-0.735~-0.918、level_median=-0.995~-1.000，**无任何 >-0.3 尖峰**；S1 桶≥0.5 全 0（③ 回归保持） |

**补测结论：4 项全部通过，与"重算核验"判定一致，无出入。RoleVerdict 主判定不变（FAIL 容器口径 + EASE 治理收编）。**

## 1. 参数规格核实（回应 team-lead 疑点）

**无出入**：任务描述 act_prob 0.76 + cap 17 = **验收规格（① 后应变）**；我预置锚定的 0.70/19.0 是**部署前基线**（② 终版 v2.0.39）。Runbook（C:\tmp\r4h_data\R4H_QA_执行Runbook_①_v2033.md）"基线→①后应变为"两列明确。基线 0.70/19.0 → ① 目标 0.76/17.0，无任何规格冲突。

## 2. 独立重算核验结果（容器实测口径，5 seed）

### 2.1 逐 seed 加总自洽性验证 ✅
- **EASE wrong 合计**：逐 seed 42:0/7:0/123:0/2024:0/777:0 → Σ=0 ✅；EASE correct Σ=16（42:3/7:0/123:3/2024:5/777:5）✅
- **M6 TIGHTEN wrong 合计**：逐 seed 42:1/7:4/123:2/2024:2/777:4 → Σ=13 ✅（≥17 不成立）
- **credit silence median**：逐 seed 0.531/0.551/0.633/0.490/0.510 → 排序 [0.490,0.510,0.531,0.551,0.633] → median=**0.531** ✅
- **S2 grv_down reverse median**：逐 seed 0.636/0.636/0.762/0.591/0.727 → 排序 → median=**0.636** ✅
- **merged p̂**：0.4894，N=134.25，K=65.7，CI 下限 0.4063，pool=[sent, lp]（2 变量）✅ 与 K/N 自洽

### 2.2 七判据裁决（容器实测）
| 判据 | 容器实测 | 验收规格 | 判定 |
|---|---|---|---|
| ① EASE wrong 专项 | 0（16/0/0 rate 1.000）| ≤4（减半）| ✅ **PASS**（核心目标达成）|
| ② 两线联合 | M6=13 ≤17 ✅；credit silence 0.531 > 0.50 ❌ | M6≤17 ∧ silence≤0.50 同立 | ❌ **FAIL**（silence 线未过）|
| ③ credit 回池 | median 0.531 > 0.50，未回池 | ≤0.50 回池（3 变量）| ❌ **FAIL** |
| ④ S2 | 0.636 > 0.60（v204x 0.682 → -0.046）| ≤0.60 | ❌ 未达标（有改善）|
| ⑤ ③② 回归 | 5/6 保持；vix reclaim 4/5（seed42 未回吐）| 全保持 | ⚠️ 基本保持 |
| ⑥ 交互 | A1 CUT ±1、credit n_active median 14、sentiment 不更负；A3 seed2024 -5 | 基本一致 | ⚠️ 基本无泄漏 |
| ⑦ p̂ 敏感性 | 0.4894 < 0.55（2 变量池）| ≥0.55 partial | ❌ **未达成** |

### 2.3 arch 工件交叉核验（关键佐证）
读 arch 工件 v2040_a76c17\acceptance_v2032.json 全貌：
- **arch 工件自身 verdict = FAIL，failures = 2 条**（seed7 silence 0.51 + seed123 silence 0.53）——**即使按 arch 本地工件口径，silence 硬闸也是 2/5 FAIL**，不是 arch 消息声称的"4/5 达标（仅 seed7 超）"
- arch 工件 merged p_hat=0.5729 / CI 0.4877 / N 131.95 / credit_median silence_frac=0.4898（回池）——**容器未复现**（p_hat 0.4894 / CI 0.4063 / N 134.25 / silence 0.531）
- r4d_rollback 中 arch 工件 credit_n_active=16 也是 **warn**（未达 target ≥18）

## 3. verdict（整体）

**FAIL（① 三批合并验收整体不通过，容器口径）**——但机制层面部分成功：
- ✅ **EASE wrong 治理真实生效**（容器）：8→0 全消失（rate 1.000）、M6 TIGHTEN wrong 13≤17、vix>1.0 步 median 18、vix peak 51.3（cap17 生效）、S2 0.682→0.636 改善
- ❌ **arch 声称的"credit 回池（silence 0.490）+ p_hat 0.5729 + S2 0.529 达标"在容器未复现**：credit silence 0.531>0.50 未回池、p_hat 0.4894（2 变量池）未过 partial、S2 0.636>0.60

## 4. blocking（2 条）

1. **arch 本地工件与容器部署实测系统性不一致（根因已锁定：A3 soul 缺失假复现）**：arch 声称的 credit 回池/p_hat 0.5729/S2 0.529 是 arch verify 脚本 config 放 /tmp 导致 A3 soul 加载失败（/souls 不存在）的**假复现**，容器真实部署（/app/config，soul 完整）实测 p_hat 0.4894（0.76）/ 0.4626（0.80）、credit 均未回池。**验收必须以容器真实部署实测为准；arch 工件不可作为验收依据。**
2. **credit silence 绝对线未过（容器口径）**：median 0.531 > 0.50（4/5 seed 超：42/7/123/777；seed123 0.633 最差）。① 的 act_prob 0.76 在容器未补偿成功，两线冲突未解开；**且 E 项证实 0.80 也未回池（sil 4/5 超），改参数不是出路**。

## 5. advisory（3 条）

1. **① 的 EASE wrong 治理本身成功**（8→0、M6 13≤17、vix 收敛、credit consistency 0.538→0.750），建议作为"决策质量修复"确认收编，但**单独不构成"credit 回池"验收通过**——credit 未回池是容器口径的硬事实。
2. **seed123 是容器环境残余弱项**：silence 0.633、n_active 9（<12）双差。arch 本地工件 seed123 是 0.531/14——环境分叉集中暴露在 seed123。
3. **CI 下限 0.55 结构性不可达**（0.4063）：与 Part 1/3 结论一致，sentiment/lp consistency 拖累，超出 ① 范围。建议按"p_hat 0.4894 未过 partial（2 变量池）+ CI advisory"记录。

## 6. 执行方式与未执行项（测试完整性如实声明）

| 项 | 状态 | 说明 |
|---|---|---|
| 部署 commit 核验（git show e636c0c）| ✅ **已补测通过**（2026-08-10）| commit e636c0c030967c0caa012e78f8b8beca594e1465 存在，标题/diff 与 ① 规格一致（详见 §0d）|
| P0 sentiment>-0.3 扫描 | ✅ **已补测通过**（未命中）| 5 seed level_mean=-0.735~-0.918、level_median=-0.995~-1.000，无 >-0.3 尖峰；S1 桶≥0.5 全 0（详见 §0d）|
| 断言 130 独立重跑 | ✅ **已补测通过**（45/45）| 容器内 test_calibrator_guards 34 组 + test_narrative_format 11 组全绿；基线 120 → ① 130（详见 §0d）|
| run_probe_acceptance 5 seed | ⚠️ 重算核验 | 基于 data-r4h3 容器实测 raw JSON 独立加总/median/交叉核验，非容器内独立跑 |
| 五闸 + 反作弊门（git diff 检测）| ✅ **已补测通过**（5/5）| 无删除/无 skip/无配置篡改/断言数上升/新增真实行为断言（详见 §0d）|

**测试完整性声明**：FAIL 判定基于容器实测证据重算核验 + 工具恢复后独立补测双重确认；已明确标注各证据来源（重算/独立执行/间接）。**不伪造独立执行结果。**

## 7. evidence

- 容器实测 raw JSON：C:\tmp\r4h_data2\r4h_v2033_all.json（定稿 0.76，CACHE 14 / v2.0.40，5 seed）+ **r4h_v2033_a80_all.json（E 项 0.80 容器真实实测，p_hat 0.4626，已独立核验）**
- arch 工件：C:\tmp\r4h_data2\v2040_a76c17\acceptance_v2032.json（verdict=FAIL，failures=2，**无 A3 soul 假复现产物**）+ calib_probe_seed*.json
- data-r4h3 前后对比：C:\tmp\r4h_data2\R4h_Part4_前后对比.md、R4h_①_交叉参考.md、**R4h_E项_容器复现验证.md（A3 soul 缺失根因锁定）**
- 我预置的 Runbook：C:\tmp\r4h_data\R4H_QA_执行Runbook_①_v2033.md

## 8. 给 team-lead 的裁决输入建议

- ① 的 **EASE wrong 治理应确认收编**（机制真实生效，容器证实）
- ① 的 **credit 回池/p_hat/S2 验收不通过（容器口径）**——arch"方案预期全过"为假复现（A3 soul 缺失环境产物，其自身工件也是 FAIL/failures=2）
- **E 项已排除"改 0.80"出路**：A2=0.80+A3=0.80 容器实测 p_hat 0.4626 更低、M6 20 反弹、sil 4/5 超——0.80 无收益。裁决点应聚焦"收编 EASE 治理" vs "回退"，改 0.80 不再作为选项

## 9. 最终状态（用户裁决后）

**用户最终裁决：收编 EASE 治理，保持 v2.0.40 部署**（详见 §0c）。工具恢复后 4 项补测全部通过（§0d），无出入。**本 RoleVerdict 最终判定与用户裁决一致，验收闭环。**
