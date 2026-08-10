# QA 独立评审 R1 — RoleVerdict（qa-review / 严过关）

> 日期：2026-08-08
> 评审对象：天璇 macro-sim 校准引擎 v2.0.29（commit 5d86784c6 + a366970ee）
> 角色：测试/验收独立评审（qa-review），与 arch/data 并行，不互通
> 输入：评审简报 + calibrator.py + financial.py + simulation.py L100-180/L500-582 + world_state.py L280-328

---

## verdict: **pass**（三议题均有可落地验收裁决；裁决结论=当前状态**不可验收**）

## blocking（当前状态违反接受线，须修复）

| # | 违反项 | 证据 | 期望 |
|---|--------|------|------|
| B1 | 逐变量 consistency<0.60（硬失败区） | sentiment 0.54-0.57、liquidity 0.33-0.57（简报 §0），接受线=逐变量≥0.60 | 修复引擎至 per-var median≥0.60 且 n_active≥20，禁改门槛 |
| B2 | 加权一致率 0.51-0.55<60% | 简报 §0；ERROR_WEIGHTS 0.40/0.35/0.25（calibrator.py L71-75） | 加权≥60%，且死变量不计入加权（无样本不验收） |
| B3 | 守卫 A 不过（liquidity 部分 seed） | liquidity active 0.12-0.41<30%、silence 0.53-0.82>50%（简报 §0；check_guards L416） | 修复 liquidity 驱动链，守卫 A 全变量过 |
| B4 | EASE ship 闸 FAIL 5/5 → ship 阻塞 | _run_ease_probe L708-719；决策层 EASE=0 | 修复 issue ③ 后 ship 闸两级 PASS（①≥1 且 ②≥1） |
| B5 | liquidity m_v=0.0 全 seed dead（无样本不验收） | 简报 §0；probe dead 判定 L592（m_v<0.002） | clamp 对称化或驱动链复核后重新探针，m_v>0 |

## advisory

| # | 建议 | 理由 |
|---|------|------|
| A1 | 接受线分层（≥0.65 稳健/[0.60,0.65)边缘/<0.60 硬失败）只作**过线后风险分档**，不改接受线本身 | 防"调门槛自证"；sentiment 0.54-0.57=硬失败，继续修引擎 |
| A2 | 探针固定 seed 协议 + 取 median 判定 | 无固定 seed（A3/A5 random），sentiment 跨 seed 0.33-0.57 摆动，单次不可信；建议 ≥5 seed，median 判线 |
| A3 | EASE 探针两级拆分：①决策层用规则单测/合成 ctx，②写层才用 credit=0.3 仿真 | 现探针初始 credit=0.3 与 ease_signal 条件 tightening<threshold×0.3（0.5→0.15）结构冲突，①=0 是探针构造自证，不能推出"ease_signal 永假" |
| A4 | ρ<\|0.3\| 加自动化闸 | probe 已算 rho（L597-614）但无闸，接受线含 ρ 但代码未 enforce |
| A5 | dead 判定弃二进制（m_v<0.002），改输出 m_v 分布/CI | sentiment m_v 0.0-0.005 跨线摆动，单点阈值 knife-edge 会导致标定/死变量政策跳变 |
| A6 | n_active<20 的变量一致性率不算 pass/fail，算 insufficient sample，且不得参与加权 | 加权 0.25 权重给 ~10 个噪声样本投票=加权自证 |
| A7 | 验收证据必须来自**新探针产物** calib_probe.json，禁用 calibration_cache 分数 | 防缓存自证（CACHE_VERSION=3 已防旧缓存，但验收口仍需显式约束） |

## evidence

- artifact_ref: calibrator.py / L71-75 — ERROR_WEIGHTS=0.40/0.35/0.25（加权分母）
- artifact_ref: calibrator.py / L578-595 — probe per-var m_v/consistency/active_rate/n_active/dead；n_active 无下限即参与一致率
- artifact_ref: calibrator.py / L592 — dead: m_v<0.002（单点 knife-edge 死线）
- artifact_ref: calibrator.py / L597-614 — ρ 相关矩阵计算但无闸
- artifact_ref: calibrator.py / L666-669 — ship 闸：①≥1 且 ②≥1 → PASS
- artifact_ref: calibrator.py / L684-686 + financial.py L75-79 — EASE 探针初始 credit=0.3 与 tightening<threshold×0.3 前提冲突（探针构造自证）
- artifact_ref: calibrator.py / L710-719 — ①=0 → FAIL 建议"ease_signal 永假"（诊断过载，应为"该窗口+该前提不可达"）
- artifact_ref: simulation.py / L134-141 — TIGHTEN +0.25×m / EASE -0.18×m（不对称）
- artifact_ref: simulation.py / L539 — MONTHLY_SCALE=0.25（D 修复已实施）
- artifact_ref: simulation.py / L555-565 — else 分支 clamp(0,1)，仅 em_capital_outflow 对称 [-1,1]；bank_credit/liquidity 仍 [0,1]
- artifact_ref: world_state.py / L307-308 — damping=max(1.0, 1/(1+3|s|))（A 修复已实施）
- artifact_ref: world_state.py / L311-315 — natural_decay：credit×0.97 / lp×0.93（恢复慢于收紧 ~3 倍）
- artifact_ref: 评审简报 §0 — 5 轮 seed 探针原始数据（sentiment 0.54-0.57 / credit 0.55-0.61 / liquidity 0.33-0.57 & m_v=0.0）

## 测试策略（修复后验证，可落地）

1. **探针协议**：run_probe 前 seed RNG 并写入 calib_probe.json（字段 `seed`）；固定 seed 可复现；≥5 seed（42/7/123/2026/99 沿用），判定取 median。
2. **判定标准**：per-var median consistency≥0.60 **且** n_active≥20；加权≥60%（死变量不计入）；守卫 A/B/C 全过；ρ<|0.3| 自动闸；EASE ship 闸 PASS；CACHE_VERSION bump（引擎任何动力学改动后必须 bump，本次 clamp 对称化/EASE 修复需 bump 4）。
3. **无样本不验收**：任一 ERROR_WEIGHTS 变量 n_active<20 或 m_v<0.002 → 该变量"不验收"，整体不可 ship，直到驱动链修复后 m_v>0 且有足够 T 类样本。
4. **回退闸触发条件**：预测回归 std>0.15 / 路径 B≥15% / 振荡 → D 回 0.12；clamp 对称化后验证无锁边（对称化前后 liquidity m_v 对比）；EASE 修复后验证 tightening 不再锁死 0.97（50 步尾部 credit 分布）。
5. **防作弊复核**（每次修复后必查）：git diff 校验测试/断言数不降（反作弊门）；EPS_TGT=0.03 冻结（禁 0.10 重分类缩分母）；接受线冻结；验收证据=新探针产物非缓存分数。

## 上线建议

**不通过** — 三议题当前均未达接受线（B1-B5），其中 B4/B5 为 ship 阻塞级；先修引擎（liquidity clamp 对称化 + EASE issue ③ + 探针两级拆分 + 固定 seed），再按上述测试策略复测，达标后方可 ship。
