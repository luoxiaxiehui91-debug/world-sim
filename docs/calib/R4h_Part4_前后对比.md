# R4h Part 4 前后对比（① EASE wrong 治理批次，data-r4h3，2026-08-10）

> 引擎：v2.0.40 / CACHE_VERSION 14 / VERSION v2.0.40 / v2040（③+②+①）
> 对比链：基线 v2.0.37 → v2031 v2.0.38（③-A）→ v204x v2.0.39（③+②）→ **v2040 v2.0.40（③+②+①）**
> 探针：probe_v2033.py（独立跑，只读 monkeypatch PROBE_PATH=/tmp，5 seed，CACHE=14 全新跑，未污染 output/）
> 部署确认：CACHE_VERSION=14、VERSION=v2.0.40、financial.py 有 ease_ok 方向闸（L97-106）、world_state.py cap 19→17（L544）、agents.yaml activation_prob 0.76（L40）、simulation.py EASE +0.08 写者保留（L152）

---

## 0. 部署验证 + 重大差异发现（容器实测 vs arch 本地工件）

### 部署确认（三处 ① 改动全部在容器生效）
- ✅ financial.py ease_ok 方向闸（L97-106：`ease_ok = (target_dir != "tighten") or vix_stress > p.threshold * 2.0` + `and ease_ok`）
- ✅ world_state.py `vix_yen_carry_bleed_max: 19.0 → 17.0`
- ✅ agents.yaml A2 activation_prob = 0.76（commercial_bank）
- ✅ CACHE_VERSION 13→14、VERSION v2.0.39→v2.0.40
- ✅ ③ EASE +0.08 写者保留（simulation.py:152）、② vix 回归 0.80/0.20 保留（world_state.py:628）

### ⚠️ 重大差异：arch 本地工件 vs 容器部署实测系统性不一致
用**同一统计函数**（容器内 scripts/run_probe_acceptance）分别重算 arch 工件与容器实测：

| 指标 | arch 工件（本地 rpa） | 容器实测（部署后） | 差异 |
|---|---|---|---|
| EASE wrong 合计 | 0 | **0** | ✅ 一致（核心目标达成） |
| EASE total | 18/0/0 | **16/0/0** | 步数不同（16 vs 18） |
| TIGHTEN wrong 合计 | 12 | **13** | 接近（≤17 均达标） |
| credit silence median | 0.490（回池） | **0.531（未回池）** | ❌ 相反 |
| credit n_active median | 16 | **14** | 略低 |
| credit consistency median | 0.786 | **0.750** | 接近 |
| merged p_hat | 0.5729 | **0.4894** | ❌ 差异大 |
| merged CI 下限 | 0.4877 | **0.4063** | ❌ |
| merged eligible pool | 3 变量（credit 回池） | **2 变量（credit 出池）** | ❌ 相反 |
| N | 131.95 | **134.25** | 不同 |
| S2 grv_down reverse median | 0.529（≤0.60 达标） | **0.636（>0.60 未达标）** | ❌ 相反 |
| vix reclaim | 5/5 | **4/5** | ⚠️ seed42 未回吐 |

**根因**：arch 工件是**本地 rpa 环境**跑的（方案设计 §0："实测环境：本地 rpa 同口径 5 seed，数据与容器 macro_data 同源"），**不是容器**。容器部署后实测为验收基准。两环境随机序列从第 1 步即分叉（arch seed42 step1: a3=SHORT_MARKET / sentiment d=-0.04197；容器 seed42 step1: a3=INCREASE_RISK / sentiment d=0.07633）→ 路径分叉 → 下游指标不同。

**结论：验收必须以容器部署后实测为准。arch 声称的"credit 回池 + p_hat 0.5729 + S2 0.529 达标"在容器环境未复现。**

---

## 1. 六判据逐项裁决（基于容器实测）

### 判据① EASE wrong 专项 ✅ PASS（核心目标达成）
| 指标 | v204x | v2040 容器实测 | 判定 |
|---|---|---|---|
| EASE wrong 合计 | 8 | **0** | ✅ 8→0 全消失 |
| EASE total c/w/n | 15/8/0 | **16/0/0** | ✅ |
| EASE rate | 0.652 | **1.000** | ✅ |
| 逐 seed wrong | 42:2/7:0/123:3/2024:1/777:2 | 42:0/7:0/123:0/2024:0/777:0 | ✅ 全 0 |
| wrong 步 cs_dir 分布 | 8/8 = tighten | **空（0 步）** | ✅ |
| EASE correct 合计 | 15 | **16**（≥15 防伪） | ✅ |

**ease_ok 方向闸在容器真实生效**，8 步 EASE wrong 全部消失。

### 判据② 两线联合裁决（核心证伪点）❌ FAIL（容器环境）
| 线 | v204x | v2040 容器实测 | 判定 |
|---|---|---|---|
| M6 TIGHTEN wrong | 16 | **13** | ✅ ≤17 达标 |
| M6 逐 seed | 42:4/7:5/123:3/2024:3/777:1 | 42:1/7:4/123:2/2024:2/777:4 | ✅ ≤17 |
| credit silence 绝对中位 | 0.510 | **0.531** | ❌ >0.50 超线 |
| credit silence 逐 seed | 0.510/0.571/0.551/0.510/0.490 | **0.531/0.551/0.633/0.490/0.510** | ❌ 4/5 超 |

**M6 达标但 silence 绝对线未过**——两线在容器环境仍冲突。① 的 act_prob 0.76 补偿在容器未达到 arch 本地效果（silence 未降回 ≤0.50）。**① 方案"两线同立"证伪（容器口径）。**

### 判据③ credit 回池 ❌ FAIL
- median silence 0.531 > 0.50 → **credit 未回池**（merged eligible pool 仍 2 变量）
- N=134.25（非 arch 声称 131.95）
- **credit 回池不成立（容器口径）**

### 判据④ S2 ❌ 未达标（但相对 v204x 有改善）
- grv_down reverse median **0.636** > 0.60
- 逐 seed: 42:0.636/7:0.636/123:0.762/2024:0.591/777:0.727
- v204x 是 0.682 → ① 后 0.636（-0.046 改善）但仍未达 ≤0.60
- arch 声称 0.529 达标——**容器未复现**

### 判据⑤ ③② 回归 ⚠️ 基本保持（1 项微降）
| 项 | v204x | v2040 容器实测 | 判定 |
|---|---|---|---|
| S1 桶 ≥0.5 尖峰 | 全 0 | 全 0 | ✅ |
| A1 HIKE | 1（seed42） | 1（seed42） | ✅ ≤1 |
| tsf | 非零 | 非零（0.115/0.111/0.258/0.250/0.240） | ✅ |
| EASE +0.08 写者 | simulation.py:152 | 保留 | ✅ |
| vix 回归 | 5/5 reclaim | **4/5**（seed42 last=peak 未回吐） | ⚠️ 微降 |
| vix>1.0 步数 | 21-36 | 18/29/17/19/17（median 18） | ✅ ≤36 |
| vix peak | 53 | **51.3** | ✅ cap17 生效 |

### 判据⑥ 交互 ⚠️ 基本无泄漏（A3 seed2024 有变化）
| 观察项 | v204x | v2040 容器实测 | 判定 |
|---|---|---|---|
| A3 INCREASE_RISK | 42:14/7:16/123:12/2024:15/777:13 | 42:15/7:17/123:12/**2024:10**/777:12 | ⚠️ seed2024 -5 |
| A3 SHORT | 42:14/7:12/123:12/2024:10/777:14 | 42:16/7:11/123:12/2024:15/777:11 | ⚠️ 分布微变 |
| A1 CUT | 42:7/7:7/123:7/2024:6/777:7 | 42:6/7:6/123:7/2024:7/777:7 | ✅ ±1 |
| credit n_active | 15/12/13/15/16 | **14/13/9/16/15** | ⚠️ median 14 不塌；seed123=9 <12 |
| sentiment level_mean | -0.733~-0.899 | **-0.745/-0.890/-0.818/-0.911/-0.861** | ✅ 不更负 |

### 判据⑦ p̂ 敏感性（新池口径）❌ 未达成
| 指标 | v204x（2变量） | arch 工件（3变量回池） | v2040 容器实测（2变量） |
|---|---|---|---|
| p_hat | 0.4948 | 0.5729 | **0.4894** |
| CI 下限 | 0.4118 | 0.4877 | **0.4063** |
| N | 135.0 | 131.95 | **134.25** |
| eligible pool | 2 变量 | 3 变量 | **2 变量（credit 出池）** |

- 容器实测 p_hat 0.4894 < 0.55（未过 partial），CI 0.4063 < 0.4877
- **credit 未回池 → 3 变量口径不成立**。arch 声称的 0.5729 依赖 credit 回池，容器未复现。
- 与 Part 4 预置一致：CI 下限 0.55 不可达（结构性）。

---

## 2. 三列对比表（基线 v2.0.37 / v204x ② / v2040 ① 容器实测）

| 指标 | v2.0.37 基线 | v204x（②） | v2040（① 容器实测） |
|---|---|---|---|
| M6 TIGHTEN wrong | 17 | 16 | **13** |
| EASE wrong / rate | — | 8 / 0.652 | **0 / 1.000** |
| credit silence median | 0.490 | 0.510 | **0.531** |
| credit n_active median | 16 | 15 | **14** |
| credit consistency median | 0.562 | 0.538 | **0.750** |
| merged p_hat | 0.5152 | 0.4948 | **0.4894** |
| merged CI 下限 | 0.4387 | 0.4118 | **0.4063** |
| eligible pool | 3 变量 | 2 变量 | **2 变量** |
| S2 grv_down reverse | 0.727 | 0.682 | **0.636** |
| vix peak | 168 | 53 | **51.3** |
| vix>1.0 步 median | 24 | 22 | **18** |
| vix reclaim | 0/5 | 5/5 | **4/5** |
| A1 HIKE | — | 1 | **1** |
| sentiment level_mean | — | -0.733~-0.899 | **-0.745~-0.911** |

---

## 3. 裁决矩阵

| 判据 | 容器实测 | 判定 |
|---|---|---|
| ① EASE wrong 专项 | 0（16/0/0 rate 1.000） | ✅ **PASS**（核心目标达成） |
| ② 两线联合 | M6=13 ≤17 ✅；silence 0.531 > 0.50 ❌ | ❌ **FAIL**（silence 线未过） |
| ③ credit 回池 | median 0.531 > 0.50 | ❌ **FAIL** |
| ④ S2 | 0.636 > 0.60 | ❌ 未达标（但较 v204x 0.682 改善） |
| ⑤ ③② 回归 | 六项中 5 项保持，vix reclaim 4/5 | ⚠️ 基本保持 |
| ⑥ 交互 | A1 CUT ±1、n_active median 14、sentiment 不更负；A3 seed2024 -5 | ⚠️ 基本无泄漏 |
| ⑦ p̂ 敏感性 | 0.4894 < 0.55（2 变量池） | ❌ 未达成 |

---

## 4. verdict

**① 的核心机制（ease_ok 方向闸）在容器部署后真实生效：EASE wrong 8→0 全消失（rate 1.000）、M6 TIGHTEN wrong 13≤17 达标、vix>1.0 步数降至 median 18、vix peak 51.3（cap17 生效）、S2 0.682→0.636 有改善。但 arch 声称的"credit 回池（silence 0.490）+ p_hat 0.5729 + S2 0.529 达标"在容器环境未复现：credit silence 0.531>0.50 未回池、p_hat 0.4894（2 变量池）未过 partial。**

### blocking（2 条）
1. **arch 本地工件与容器部署实测系统性不一致**（已用同一统计函数在容器内双向重算证实）：credit 回池/出池相反、p_hat 0.5729 vs 0.4894、S2 0.529 vs 0.636。**根因：arch 工件来自本地 rpa 环境而非容器**。验收必须以容器实测为准；arch 声称的"credit 回池 + p_hat 0.5729"不可作为 ① 的验收依据。
2. **credit silence 绝对线未过（容器口径）**：median 0.531 > 0.50（4/5 seed 超，seed123 0.633 最差）。① 的 act_prob 0.76 在容器未补偿成功，两线冲突未解开。

### advisory（3 条）
1. **① 的 EASE wrong 治理本身成功**（8→0、M6 13≤17、vix 收敛），建议将其作为"决策质量修复"确认收编，但**单独不构成"credit 回池"验收通过**——credit 未回池是容器口径的硬事实。
2. **seed123 是容器环境的残余弱项**：silence 0.633、n_active 9（<12）双差。arch 本地工件的 seed123 是 0.531/14——环境分叉集中暴露在 seed123。
3. **CI 下限 0.55 结构性不可达**（0.4063）：与 Part 1/3 结论一致，sentiment/lp consistency 拖累，超出 ① 范围。建议按"p_hat 0.4894 未过 partial（2 变量池）+ CI advisory"记录。

### evidence
- 容器实测：`/tmp/r4h_v2033_all.json`、`/tmp/r4h_v2033_seed{42,7,123,2024,777}.json`（CACHE 14 全新跑）
- arch 工件交叉重算：`/tmp/arch_seed{42,7,123,2024,777}.json`（容器内同一统计函数重算，可复现 0.5729/0.490）
- 本地留痕：`C:\tmp\r4h_data2\R4h_Part4_前后对比.md`、`r4h_v2033_all.json`、`probe_v2033.py`、`R4h_①_交叉参考.md`
- 代码锚点：financial.py L97-106（ease_ok）、world_state.py L544（cap 17）、agents.yaml L40（act_prob 0.76）、simulation.py L152（EASE +0.08）

---

## 5. 最终裁决确认（2026-08-10，用户已采纳，R4h ① 结案）

> 用户最终裁决：**收编 EASE 治理**——ease_ok 机制收编（EASE wrong 8→0 真实有效、两环境一致）；credit 回池/p̂/S2 不通过、挂起为后续 silence 治理目标；**保持 v2.0.40 / CACHE 14 / v2033 部署**。

### 5.1 假复现根因定论（E 项补做，决定性证据）
- arch 声称的"容器复现 0.5729 / credit 回池"确系**假复现**，根因 = **A3 soul 加载路径差异**：
  - `load_agents`（core/simulation.py:58）soul 路径 = `os.path.dirname(config_path)/../souls`
  - arch verify 脚本 config 写 `/tmp` → soul 找 `/souls`（不存在）→ A3 soul={} 空，回退旧 if-else 决策
  - 容器真实 `/app/config/agents.yaml` → soul 找 `/app/souls`（存在，含 A3_hedge_fund.yaml）→ A3 soul 完整加载
- **决定性实验**：同一 config 文件（md5 完全相同 17bba346，A2/A3=0.80/0.80），读 `/tmp` 路径 → p̂ 0.5729；读 `/app` 路径 → p̂ 0.4626。隔离实验排除 monkeypatch（iso3）、random.seed 前置（iso4）干扰，唯一变量 = config 路径 → A3 soul 加载。
- arch 本地工件（v2040_a76c17）同因：param_scan_1b 本地 config 写 `C:/tmp/r4h_data2/config/agents_tmp2.yaml` → souls_dir 解析到 `C:/tmp/r4h_data2/souls`（不存在）→ **无 A3 soul 环境产物**，不作为验收依据。
- **A2=0.80 选项排除**：容器真实环境（A3 soul 完整）实测 p̂ 0.4626 < 定稿 0.76 的 0.4894、M6 20 > 13、EASE 15 < 16 → 0.80 反而更差，**保持定稿 0.76 是唯一正确选择，无需用户重裁参数**。

### 5.2 最终实测矩阵（容器真实部署 /app config，A3 soul 完整）
| 配置 | p_hat | CI | pool | EASE | M6 | sil 超线 | S2 |
|---|---|---|---|---|---|---|---|
| 定稿 0.76/0.75 | **0.4894** | 0.4063 | 2 变量出池 | 16/0/0 | 13 | 4/5（0.531） | 0.636 |
| 0.80/0.80（临时） | 0.4626 | 0.3808 | 2 变量出池 | 15/0/0 | 20 | 4/5（0.51） | 0.65 |
| arch 工件（假复现） | 0.5729 | 0.4877 | 3 变量回池 | 18/0/0 | 12 | 2/5 | 0.529 |

### 5.3 定稿结论
- **机制层收编**（两环境一致 ✅）：ease_ok（EASE wrong 8→0，rate 1.000）、M6 TIGHTEN wrong 13≤17、vix peak 51.3（cap17 生效）、M4 flip 0、credit consistency 0.538→0.750
- **验收数值层不通过**（容器口径 ❌）：credit silence 0.531>0.50 未回池、p̂ 0.4894<0.55 未过 partial、S2 0.636>0.60
- **留痕定稿**：本文件 + `r4h_v2033_all.json`（定稿 0.76）+ `r4h_v2033_a80_all.json`（0.80 临时）+ `R4h_E项_容器复现验证.md`；容器已恢复定稿（config md5 5048c4fd = A2=0.76/A3=0.75、CACHE 14、v2.0.40），无残留实验配置。
