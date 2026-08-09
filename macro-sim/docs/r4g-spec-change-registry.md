# R4g 规格变更登记（v2.0.36 · commit e1d1832）

> 文档类别：规格变更登记（REGISTRY）· 绑定 commit e1d1832
> 变更来源：R4g 阶段二实施 spec（team-lead 下发，三方裁决已确认）
> 归因基线：data-r4g 阶段一归因——S 类 92% 激活机制（cooldown 61.8% + activation_gate 30.1%）、rule_hold 仅 8.1%

---

## 变更 1：归因映射修复（可验证性①）

- **变更内容**：`core/calibrator.py` run_probe 循环内 `a2_acted` 判定
  - 旧：`a2_acted = bool(snapshot.get("actions", {}).get("A2"))`
  - 新：`a2_acted = snapshot.get("actions", {}).get("A2") not in (None, "HOLD", "NO_ACTION")`
- **原因**：simulation.py:521 `actions` 只过滤 NO_ACTION，HOLD 也入 actions → 旧 bool() 把 HOLD
  决策步判为 acted_other → tighten_signal_false 分支不可达（死代码恒 0），归因口径与语义不符。
  修复后 HOLD 决策步归 tighten_signal_false（规则层 HOLD），五 seed 该字段从恒 0 → 约 8%。
- **影响范围**：仅归因字段 `a2_state` 的语义（statistical attribution），不改变引擎决策、不改变
  silence_frac/s_class 定义。落盘 step_record 结构不变。
- **涉及断言**：`test_classify_a2_state`（+6 条 HOLD 语义断言）、`test_s_class_attribution_mapping`
  （+1 条 HOLD 步归属断言）；断言总数 102 → 110。

## 变更 2：activation_countdown 条件化（路径 A1，直击主因）

- **变更内容**：`core/simulation.py` step() 激活门分支
  - 旧：任何决策（含 HOLD）后 `agent.activation_countdown = agent.info_delay`
  - 新：仅 `decision.action != "HOLD"` 才设 countdown（HOLD 不触发冷却）
- **原因**：data 实证 96 个 rate_limit 步中 14 个前一步是 HOLD——HOLD 是"本步无信号"的决策，
  不应惩罚锁步。HOLD 后锁 1 步是 rate_limit 主因（61.8%）的组成部分。
- **影响范围**：全 agent 共享逻辑（simulation.py L487-494）。语义统一：HOLD 不再触发行动后冷却；
  实质行动（TIGHTEN/EASE/SHORT/CUT 等）冷却语义不变。flip-flop 主防仍在 A2 专属
  `_ease_cooldown`（EASE 后挡 TIGHTEN）。评估结论：影响面可控——HOLD 无 delta，仅释放后续
  决策机会；实质行动冷却保留，振荡防护链未断。
- **涉及断言**：`test_direction_gate`（8）、`test_directional_ease`（9）、`test_ease_layer1_ctx`
  （1）逐条重验通过（决策分支纯函数不受 step() 冷却逻辑影响）。

## 变更 3：EASE 冷却 2→1（辅助）

- **变更内容**：`core/agents/financial.py` `_ease_cooldown` 2 → 1
- **原因**：data 实证 EASE 后第 1 步 target 非零 d=0 占 63.4%、第 2 步 29.3%——activation_countdown
  是主冷却，_ease_cooldown 仅在冷却期抑制 TIGHTEN。2→1 把 TIGHTEN 挡期缩短 1 步，配合变更 2
  释放 EASE 后第 2 步的 TIGHTEN 机会。
- **影响范围**：仅 A2 规则层。EASE 后 TIGHTEN 挡期从 2 步缩至 1 步（允许继续 EASE/HOLD）。
- **风险与兜底**：v2.0.1 振荡史（EASE/TIGHTEN flip-flop）——M4 flip-flop 监测兜底，qa 验收观察。

## 变更 4：CACHE_VERSION 10→11 + VERSION v2.0.35→v2.0.36

- **变更内容**：`core/calibrator.py` CACHE_VERSION=11；`VERSION` v2.0.36
- **原因**：改引擎必 bump（反作弊门：防 <7 天命中旧缓存自证）。变更 2/3 改变引擎决策行为，
  变更 1 改变归因口径，均需失效旧缓存。

---

## 测试基线（自检，qa 独立验收）

| 测试文件 | 断言数（改前→改后） | 结果 |
|---|---|---|
| tests/test_calibrator_guards.py | 90 → 98 | 全绿（21 组） |
| tests/test_narrative_format.py | 12 → 12 | 全绿（11 组） |
| **合计** | **102 → 110** | **全绿** |

- py_compile：core/calibrator.py / core/simulation.py / core/agents/financial.py 通过
- import smoke：CACHE_VERSION=11、MacroSimModel、CommercialBankAgent 可导入
- 部署：docker build 成功（image 66e1bd66a5f0），容器重启后 docker exec 验证
  VERSION=v2.0.36、CACHE_VERSION=11、三处引擎改动行号均生效
- 未跑验收脚本（run_probe_acceptance 由 qa 独立执行）

---

## 变更 5：revert 引擎实验②③（commit 8180a8a · v2.0.37 · 收尾裁决）

- **裁决来源**：qa-r4g 独立验收 FAIL + 用户确认——revert ②③（引擎实验），保留①（归因映射修复）
- **变更内容**：
  - `core/simulation.py`：移除 `if decision.action != "HOLD"` 条件化 → 恢复决策后无条件
    `agent.activation_countdown = agent.info_delay`（R4e 行为，HOLD 也锁步）
  - `core/agents/financial.py`：`_ease_cooldown` 1 → 2（R4e 行为）
  - **保留**：`core/calibrator.py:704` a2_acted HOLD 语义、`CACHE_VERSION=11`、
    test_classify_a2_state 11 断言 + test_s_class_attribution_mapping 5 断言
  - `VERSION`：v2.0.36 → v2.0.37（版本只前进不后退）
- **原因（qa 验收数据）**：
  - 变更②：HOLD 不锁冷却释放"本步无信号"后的重复掷门机会，rate_limit 仅削 ~15%，却放大 A2
    决策抖动——seed42 silence 0.49→0.551、seed2024 0.469→0.531（超线转移非消除）、
    seed7 consistency 0.714→0.429 崩塌。收益/副作用比不成立。
  - 变更③：_ease_cooldown 2→1 直接打开 EASE 后第 2 步 TIGHTEN 窗口，v2.0.1 振荡史重演——
    M4 实测 EASE 后 1 步内 TIGHTEN 相邻振荡 2-4 次/seed，credit consistency median 0.5625→0.500。
- **影响范围**：引擎决策行为回到 R4e 基线；测量层（归因口径）保持 v2.0.36 修复态。
- **revert 验证（独立探针落盘 /tmp，5 seed）**：

| seed | silence R4e→rev | n_active R4e→rev | act R4e→rev | consistency R4e→rev | tsf R4e→rev | weighted R4e→rev |
|---|---|---|---|---|---|---|
| 42   | 0.49→0.49  | 16→16  | 0.327→0.327 | 0.562→0.562 | 0.0→0.0   | 0.456044→0.456044 |
| 7    | 0.531→0.531| 14→14  | 0.286→0.286 | 0.714→0.714 | 0.0→0.038 | 0.534466→0.534466 |
| 123  | 0.531→0.531| 14→14  | 0.286→0.286 | 0.5→0.5     | 0.0→0.115 | 0.480932→0.480932 |
| 2024 | 0.469→0.469| 17→17  | 0.347→0.347 | 0.471→0.471 | 0.0→0.13  | 0.54025→0.54025  |
| 777  | 0.49→0.49  | 16→16  | 0.327→0.327 | 0.688→0.688 | 0.0→0.125 | 0.47831→0.47831  |

  → 引擎行为逐位回到 R4e 基线；tighten_signal_false 保持非零（seed42 无 HOLD 决策步为 0，
  其余 seed 0.038-0.13）= 引擎回滚+测量保留的直接证据。
- **涉及断言**：无断言因回滚 FAIL（测试无 _ease_cooldown/activation_countdown 引用，全量 110 保持全绿）。
- **ARTIFACT_TAG 待办**：qa 提示 v2030c 复用问题，output/r4e_backup_v2030c/ 已存 R4e 备份；
  后续部署建议 bump tag（如 v2031）防 era 混淆。

---

## 变更 6：R4h ③-A sentiment 写者 + a2_action 落盘 + CACHE 12 + v2.0.38（commit aa29f6b）

- **裁决来源**：R4h 评审简报 §3 实施 spec（arch-r4h 定稿，qa/data 会签）——③-A 参数 K=1.0（EASE 写
  sentiment 对称 +0.08），与 TIGHTEN -0.08 完全镜像。② vix 治理本轮不做（M6 残差裁决后行）。
- **变更内容**：
  1. `core/simulation.py`（gm_resolve_rules EASE_CREDIT 分支，L148-152）：补写
     `add("A2", "market_sentiment", 0.08 * m)`（m=mag("A2")=1.0，K=1.0）。此前 EASE 只写
     credit/lp 不写 sentiment（负写者主导 3:1：TIGHTEN -0.08 ×12 步 vs EASE 不写 ×4 步，
     grv_down reverse 0.727 → sentiment 恒贴 floor）。clamp [-1,1] 由 apply_sentiment_delta
     统一；damping 恒 1。
  2. `core/calibrator.py`（step_record，L732 附近）：落盘 `"a2_action":
     snapshot.get("actions",{}).get("A2","HOLD")`——决策级 A2 行动（纯测量层，无额外 CACHE
     bump），服务 qa P1 a2_acted 检查 / M4 决策级 flip-flop / M1 EASE wrong 同口径。
  3. `core/calibrator.py`：CACHE_VERSION 11→12（sentiment 写者改变引擎动力学，反作弊门）。
  4. `VERSION`：v2.0.37 → v2.0.38。
  5. `scripts/run_probe_acceptance.py`：ARTIFACT_TAG v2030c → v2031（含 docstring/acceptance
     文件名同步），防 era 混淆（R4g 变更 5 待办落地）。
- **原因**：sentiment 长期贴 floor（level_mean -0.880 / floor_frac 0.694）根因之一是 EASE 对
  sentiment 零直接副作用——宽松不传导情绪回升。补对称正写者后：sentiment 抬离 floor →
  consecutive_negative_steps 重置 → vix bleed 停（③→② 传导路径），A3 -0.4 边界复激活，
  方向正确且被三向自限（arch 量化：EASE 正贡献仅占窗口负压总量 3-5%）。
- **影响范围**：market_sentiment 动力学（所有 sentiment 依赖 agent 决策、vix bleed、soul 层）；
  传导放大 A2→A3(to_A3=0.40)/A10(to_A10=0.35) 衰减 0.5 → 每步总效果 +0.0275/步 ≥EPS_ACT。
  S→T 转移：EASE 步 sentiment 意图 0 → +0.08×0.25=0.02（T 类），sentiment n_active 升、
  eligible 池变 → merged p̂ 结构变化（qa 独立验收 + data 前后对比）。
- **涉及断言**：新增 3 项（`test_a2_ease_writes_sentiment` / `test_a2_ease_sentiment_symmetry` /
  `test_a2_ease_sentiment_t_class`），110 → 113；既有 110 无 FAIL。禁 skip/.only。

---

## 测试基线（自检，qa 独立验收）

| 测试文件 | 断言数（改前→改后） | 结果 |
|---|---|---|
| tests/test_calibrator_guards.py | 98 → 101 | 全绿（24 组） |
| tests/test_narrative_format.py | 12 → 12 | 全绿（11 组） |
| **合计** | **110 → 113** | **全绿** |

- py_compile：core/calibrator.py / core/simulation.py / core/agents/financial.py /
  core/world_state.py / scripts/run_probe_acceptance.py / tests 通过
- import smoke：CACHE_VERSION=12、VERSION=v2.0.38、ARTIFACT_TAG=v2031、MacroSimModel /
  gm_resolve_rules / CommercialBankAgent 可导入
- 只读探针（monkeypatch 落 /tmp）：EASE 步 sentiment 意图>0（0.08）、TIGHTEN 对称 -0.08、
  intent×MONTHLY_SCALE=0.02 ≥EPS_ACT(0.005)、tsf 仍非零
- 未跑验收脚本（run_probe_acceptance 由 qa 独立执行）
- 部署：NAS docker build（image 待回填）+ compose up --force-recreate，容器内 grep 五处验证
  （simulation.py sentiment 写 / calibrator a2_action / CACHE_VERSION=12 / VERSION=v2.0.38 /
  ARTIFACT_TAG=v2031）
- **回退闸**：单行 revert（simulation.py 插入行）+ CACHE 12→11 + VERSION 回退 v2.0.37
