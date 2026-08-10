# R4h Part 4 判据（① EASE wrong 治理批次 v2033，data-r4h2 预置，2026-08-09）

> 状态：**预置**（arch 正在产 ① 方案设计，部署 v2033 后按本文档跑 Part 4 前后对比）
> 对比链：基线 v2.0.37 → v2031（③）→ v204x v2.0.39（③+②）→ **v2033（③+②+①，待部署）**
> 已有证据：C:\tmp\r4h_data\（基线）、C:\tmp\r4h_data2\（v2031/v204x 全套 + probe_v204x.py + ease_wrong_feat.json）
> 判定原则：与 Part 2/3 同口径（同探针逻辑 / 同 acceptance 统计 / 同 EASE c/w/n 口径），只读 /tmp

---

## 0. ① 的现状锚点（v204x，② 后基线）

### EASE wrong 专项（核心靶点）
| seed | EASE c/w/n | rate | n_ease | TIGHTEN c/w/n |
|---|---|---|---|---|
| 42 | 3/2/0 | 0.600 | 5 | 1/4/3 |
| 7 | 0/0/0 | — | **0** | 6/5/5 |
| 123 | 3/3/0 | 0.500 | 6 | 3/3/4 |
| 2024 | 4/1/0 | 0.800 | 5 | 3/3/3 |
| 777 | 5/2/0 | 0.714 | 7 | 4/1/0 |
| **合计** | **15/8/0** | **0.652** | **23** | **17/16/15** |

### EASE wrong 步特征（8 步，ease_wrong_feat.json 已采集）
- **8/8 步全部 cs_delta > +2.5（target_dir=tighten）**！即"cs 转正（收紧方向）时仍触发 EASE"——这是 EASE wrong 的统一根因。
- cs_delta 分布：+6/+7/+21/+8/+7/+6/+21/+8（42:2 步、123:3 步、2024:1 步、777:2 步）
- 当时 vix≈29（vix_stress≈0.37-0.38，**远未到 vix>48 豁免区**）
- spread 183-216、grv 48-59、tightening 已深度为负（-0.52~-0.97）
- t 值全部 >EPS_TGT（+0.072~+0.252）→ wrong 确认

**机制解读**：EASE 决策只有 `ease_signal`（spread<250 ∧ tightening<threshold ∧ grv<threshold），**无对称方向守卫**（TIGHTEN 有 `tighten_ok = (target_dir != "ease") or vix>1.0`，EASE 没有 `ease_ok = (target_dir != "tighten") or ...`）。cs_delta 转正时 credit target 期望收紧，但 spread/grv 仍满足 ease_signal → A2 错误 EASE。**arch ① 方案若用"对称方向守卫"（cs_delta>+2.5 时禁 EASE 或转 HOLD），则 8 步 wrong 应全部消失。**

---

## 1. 六项验收判据（① 部署后逐项裁决）

### 判据① EASE wrong 专项（核心）
| 指标 | v204x | ① 目标 |
|---|---|---|
| EASE wrong 合计 | 8（15/8/0） | **≤4（减半）** |
| rate | 0.652 | **≥0.75** |
| 逐 seed wrong | 42:2/7:0/123:3/2024:1/777:2 | 42/123/777 须降 |
| wrong 步 cs_dir 分布 | 8/8 = tighten | **tighten 方向 wrong 显著减少（若 arch 上方向守卫）** |

**判定**：
- wrong ≤4 → ① 达标（EASE 决策级治理生效）
- wrong 5-8 但 cs_dir 分布从"全 tighten"变为"mixed/ease"→ 部分达标（wrong 结构变化，需结合 ② 归因看）
- wrong 仍 8 且全 tighten → ① 未触达根因（方向守卫未上）→ 不达标

### 判据② 两线联合裁决（① 的核心证伪点）
| 线 | v204x | ① 目标 |
|---|---|---|
| M6 TIGHTEN wrong | 16 | **≤17（不反弹）** |
| credit silence 绝对中位 | **0.510（FAIL）** | **≤0.50（回池线）** |
| credit silence 逐 seed | 0.510/0.571/0.551/0.510/0.490 | ≤0.50（至少中位） |

**判定**（arch 方案的"两线冲突解法"可证伪点）：
- **M6 ≤17 ∧ 绝对 silence ≤0.50 同时成立** → ① 方案解开了 Part 3 blocking，PASS
- M6 ≤17 但 silence 仍 >0.50 → 两线仍冲突，① 方案判伪
- M6 反弹 >17 且 silence 仍超 → ① 方案失败
- **特别注意**：EASE wrong 治理（如方向守卫）→ EASE 步转 HOLD → **credit silence 可能进一步上升**（EASE 也计活性，转 HOLD = 更多 S 类沉默）→ 两线更冲突。arch 必须用"wrong 转 correct EASE"而非"wrong 转 HOLD"来降 wrong 同时保活性。**这是 ① 方案设计的关键分叉**。

### 判据③ credit eligible 回池
| 指标 | v204x | ① 目标 |
|---|---|---|
| merged eligible pool | [sent, lp]（credit 出池） | **credit 回池（3 变量）** |
| N | 135.0 | **回到 ~160（credit 入池）** |
| merged p̂（回池口径） | 0.4948（2变量） | **≥0.5077（三变量同池基线）** |

**判定**：① 后 credit silence 降回 ≤0.50 → credit 重新 eligible → 三批合并 p̂ 用回池口径（N≈160）。**三批合并验收必须用回池后口径**，否则结构性低估。

### 判据④ ③② 回归
| 项 | v204x | ① 后须保持 |
|---|---|---|
| S1 桶 ≥0.5 尖峰 | 全 0 | **全 0**（过冲不重演） |
| A1 HIKE | 1（seed42） | **≤1** |
| tsf（tighten_signal_false） | 0.040/0.107/0.148/0.200/0.125 | **非零保持** |
| EASE +0.08 写 sentiment | simulation.py:152 保留 | **保留**（③ 不因 ① 回退） |
| vix 均值回归 0.80/0.20 | world_state.py:351 保留 | **保留**（vix_last<max 保持） |
| vix>1.0 步数 | 21-36 | **不恶化**（≤36） |

**判定**：六项全保持 → ③② 不受 ① 干扰。

### 判据⑤ 交互（A2 决策改动的连锁）
| 观察项 | v204x | ① 后盯 |
|---|---|---|
| A3 高压抄底（INCREASE_RISK） | 42:14/7:16/123:12/2024:15/777:13 | **不显著减少**（① 动 A2 不改 A3） |
| A1 CUT | 42:7/7:7/123:7/2024:6/777:7 | **不显著减少**（防正写抵消 → sentiment 更负） |
| A3 SHORT | 42:14/7:12/123:12/2024:10/777:14 | 不显著增加 |
| credit n_active | 15/12/13/15/16（median 15） | **≥12/seed（不塌）** |
| sentiment level_mean | -0.733~-0.899 | **不更负**（A1/A3 正写不消失） |

**判定**：A1/A3 分布与 v204x 基本一致（±1 步）→ ① 是纯 A2 决策级改动，无跨 agent 泄漏；若 A3/A1 显著变化 → ① 动到了共享状态（如 sentiment 写者），需查。

### 判据⑥ p̂ 敏感性更新（新池口径 135 / 回池 ~160）
> ⚠ **2026-08-10 注记**：下表为基于 v204x 基线的**场景模拟推演，非容器实测，未经验证**。容器真实部署（v2.0.40/v2033）后：credit **未回池**、p̂ **0.4894**（CI 0.4063）——"credit 回池结构性回升（0.5077）"与"+cons → 点估过 0.55（0.5692/0.5770）"等场景**均未兑现**。权威结论见 R4h_Part4_前后对比.md §5。
v204x 三变量强制池基线：**p̂=0.5077，CI=0.4309，N=159.8**（Part 1 Q1 方法在新池口径重跑）。

| 场景 | p̂ | CI 下限 | 判定 |
|---|---|---|---|
| 现状（credit 出池 2 变量） | 0.4948 | 0.4118 | — |
| ① 后 credit 回池（3 变量，cons 不变） | 0.5077 | 0.4309 | 结构性回升 |
| ① 治 EASE wrong → credit cons +0.05 | 0.5154 | 0.4385 | 改善 |
| + sentiment cons +0.05 | 0.5423 | 0.4650 | 接近 |
| + sentiment cons +0.10 | 0.5692 | 0.4917 | **点估过 0.55** |
| ① 治 EASE wrong → credit cons +0.10 | 0.5232 | 0.4461 | 改善 |
| + sentiment cons +0.10 | 0.5770 | 0.4995 | **点估过 0.55** |
| 全变量 cons +0.08 | 0.5877 | — | — |

**结论**：
- **credit 回池本身就是结构性 p̂ 提升**（0.4948→0.5077，Δ+0.013）——① 治 silence 的价值被低估。
- **CI 下限 0.55 仍不可达**（0.4917 最高模拟），与 Part 1 Q1 结论一致（③②① 三管齐下点估可过 0.55，CI 下限需全变量 +0.10 以上）。
- **① 单独对 p̂ 的贡献 = credit cons +Δ（0.0155/0.05，0.0311/0.10）**，权重 0.35 限制其杠杆——**① 主要价值是回池 + 清 EASE wrong 闸，不是 merged 提升器**。

---

## 2. 裁决矩阵（① 部署后直接套用）

| 情形 | 判定 |
|---|---|
| ①EASE wrong ≤4 ∧ ②两线同立 ∧ ③credit 回池 ∧ ④全回归 ∧ ⑤无泄漏 | **① PASS**，三批合并验收 |
| ①EASE wrong 降至 ≤4 但 ②silence 仍 >0.50 | ① 部分达标（EASE 治理生效），**② 两线仍冲突 → 方案判伪需回退评审** |
| ①EASE wrong 降但 wrong 转 HOLD（n_active 塌 / silence 升） | ① **假达标**（wrong 被沉默吸收非治理） |
| ①EASE wrong 不降（仍 8 且全 tighten） | ① **FAIL**（方向守卫未上） |
| ①达标但 ④A3/A1 显著变 / ⑤n_active<12 | ① **FAIL**（跨 agent 泄漏） |

---

## 3. Part 4 执行计划（arch 部署回传后立即跑）

1. **探针**：`probe_v2033.py`（已预生成 C:\tmp\r4h_data2\，语法校验 OK）上传容器跑 5 seed（CACHE 全新，确认 arch 是否 bump）。
2. **world_state/financial/simulation diff**：`world_state_v2039.py`/`financial_v2039.py`（已存档）vs 容器当前——确认 ① 改的 A2 决策位置（期望：financial.py ease_signal 加方向守卫或 EASE 前加 `ease_ok`）。
3. **六判据逐项裁决** → 前后对比表（基线/v2031/v204x/v2033 四列）→ RoleVerdict 回传 team-lead。
4. **留痕**：C:\tmp\r4h_data2\R4h_Part4_前后对比.md + r4h_v2033_all.json + v2033_seed*.json。

---

## 证据清单（现状锚点，① 部署前固化）

- **EASE wrong 8 步特征**：C:\tmp\r4h_data2\ease_wrong_feat.json（全 tighten cs_dir、vix≈29、spread 183-216）
- **v204x 锚点**：EASE wrong 8、M6=16、silence median 0.510、vix reclaim 5/5、merged 2变量 0.4948 / 3变量 0.5077
- **文件 md5（v2039 基准）**：financial.py c1003529、world_state.py 97c9a9d0、simulation.py 26e9c8cc
- **留痕文件**：C:\tmp\r4h_data2\（本文件 + probe_v2033.py + probe_v204x.py + r4h_v204x_all.json + ease_wrong_feat.json + v204x_seed*.json + world_state/financial_v2039.py）
