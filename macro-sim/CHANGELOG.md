# Changelog

> 文档类别：实录（RECORD）· CHANGELOG（每条绑定 commit hash，写后即验）
> 最后核对时间：2026-08-08（记录类文档随部署持续更新）

本文档遵循 [Keep a Changelog](https://keepachangelog.com/) 规范。  
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## v2.0.30 — 2026-08-08 (by WorkBuddy)

**修改理由**：P0——校准接受线未达修复批次（calib-eps-act-review R1 三方终局 + audit 复核，2026-08-08）。加权一致率 0.51-0.55 < 60%：sentiment/liquidity 贴边假死（post-clamp 测量盲区 + clamp[0,1] 砍负半轴 + 正写者主导）+ EASE 决策层永假（ease_signal 过严）+ target_scale key bug。裁决：**修引擎，禁调门槛**。依据：`calib-eps-act-review-R1-综合评审-2026-08-08.md` §4/§7（commit 45d6ed390）。

### 修改

- **`core/calibrator.py`**
  - **P0-1 测量层（QA R1 裁决）**：
    - 新增 `clamp_frac` 指标（贴边 |level|≥0.999 步数占比）——区分"饱和（引擎疯狂驱动被 clamp 吃掉）" vs "真无写者"（post-clamp 世界差值在边界处恒 0，m_v=0 可能是饱和而非死）
    - **dead 改判**：`m_v < DEAD_M_V ∧ clamp_frac < 0.3`（原 m_v<0.002 单点 knife-edge，把 cap 饱和误标"真死"）
    - 新增 `MIN_N_ACTIVE = 20` 样本门槛：n_active<20 的变量不算 pass/fail（insufficient sample），不计入加权一致率（死变量 0.25 权重用 ~10 噪声样本投票=加权自证）
    - `run_probe` 新增 `seed` 参数（canonical 42）——探针有 activation 随机性，单次不可信，验收须多 seed 取 median
    - 新增 `weighted_consistency`（仅计 sufficient 变量）
  - **P1-2（data 终局裁决）**：`_load_target_scales` **显式禁用**（恒返回 {}）——key bug（写 nested 读顶层从未生效）+ T_v=2·m_v 公式自指退化（sentiment m_v≈0.005 → target≈0.01<EPS_TGT → 样本掏空 = 改门槛自证）
  - **CACHE_VERSION 3→4**（引擎动力学改变，旧缓存失效）
- **`core/agents/financial.py`**（CommercialBankAgent._decide_rules）
  - **P0-2 EASE 决策层**：ease_signal 阈值放宽 `spread<250 ∧ tightening<threshold×1.0 ∧ grv_stress<threshold×0.5`（原 200/×0.3/×0.3——tightening<0.15 一旦收紧回不来，探针实测锁死 0.97，EASE 决策层结构性不可达）。与 tighten_signal 无重叠冲突（grv 触发线 0.8、spread 触发线 400、visible 挡死保留）
  - **P0-2 EASE 后 2 步冷却**防 flip-flop（v2.0.1 振荡史）：EASE 后冷却期跳过 TIGHTEN 分支（允许继续 EASE 或 HOLD）
- **`core/simulation.py`**
  - **P0-2 幅度对称**：EASE `-0.18→-0.25`（+0.25/-0.25 对称；原恢复比收紧慢 ~3 倍，一旦收紧回不来）
  - **P0-3 clamp 对称 [-1,1]**：bank_credit_tightening / liquidity_premium 纳入对称 clamp（照 em_capital_outflow 模式）——target 均可负（credit=cs×0.6 / lp=cs×0.4+t10y2y×0.3∈[-0.7,0.7]），clamp[0,1] 结构性砍负半轴 → 负 target 不可测、cap 假收敛（探针 m_v=0 假死）。连带已核：decay ×0.97/×0.93 负区向 0 回归安全；下游 bleed 阈值全在正侧；EASE 在负 credit 下更易触发（合理）
  - **P1-1 写者结构**：A1 CUT_25BP sentiment `+0.20→+0.30`（正写增强打破负写垄断）
- **`config/agents.yaml`**
  - **P1-1**：A3 SHORT activation `1.00→0.75`（降负写频率；A3 决策分支不动保 08-06 path diversity 修复）

### 探针复测（v2.0.30，固定 seed 协议 42/7/123 三探针 median）

| 变量 | consistency median | n_active median | sufficient | m_v median | clamp_frac | dead | 判定 |
|------|-------------------|-----------------|------------|------------|-----------|------|------|
| market_sentiment | 0.567 | 18 | ❌(<20) | 0.0 | 0.57 | False | 未达（seed 敏感：0.333-0.727） |
| bank_credit_tightening | 0.55 | 40 | ✅ | 0.028 | 0.0 | False | 未达（seed42 0.725 亮点） |
| liquidity_premium | 0.471 | 17 | ❌(<20) | 0.0 | 0.57 | **False** | 未达（饱和非死，P0-1 修正生效） |

- **EASE ship 闸：三 seed 全 PASS**（QA R1 两级能力验证重构）——①合成 ctx 决策层全返回 EASE_CREDIT；②宽松窗口写层落地 13/15、13/14、13/15（~87-93%）。原压力窗口 FAIL 是环境挡死（visible hf SHORT）非引擎能力缺失（构造自证），已按 QA 裁决重构为合成宽松窗口能力验证
- **加权一致率（sufficient-only）**：seed42 0.641 / seed7 0.55 / seed123 0.521 → **median 0.55 < 0.60 未达**
- **dead 判定修正核心成果**：liquidity 三 seed 全 dead=False（clamp_frac 0.53-0.88 揭示"cap 饱和"真相）——不再误判真死，不被 C3 移除，保留校准价值
- **rho sentiment↔liquidity**：-0.164 / -0.492 / -0.124（seed42/123 达标，seed7 超 |0.3| 线）
- **残留（第 2 轮候选）**：sentiment seed 敏感（A3 激活路径贴边）；liquidity 仍钉 cap（压力窗口 EASE 不可达→无负写者，arch"clamp 对称必要非充分"应验）；credit 0.55 假健康改善中。候选方案 = arch P0-1b pre-clamp 引擎意图 delta 测量（snapshot 已有 delta 字段，一行切换，需三方确认口径）

### 探针复测 v2.0.30b（P0-1b pre-clamp 测量，commit f7a78c249，seed 42/7/123 median）

**arch P0-1"测量盲区是根"完全应验**——post-clamp 世界差值在 cap/floor 处恒 0 掩盖真相，pre-clamp 意图揭示：

| 变量 | consistency median | n_active | m_v median | act_frac | silence | dead | 解读 |
|------|-------------------|----------|------------|----------|---------|------|------|
| market_sentiment | **0.538** | 39-43 ✅ | 0.078 | 80-88% | 2-10% | False | **一直有驱动**（post-clamp 假死实锤），方向一致率仍 <60% |
| bank_credit_tightening | 0.467 | 13-15 ❌ | **0.0** | 26-31% | 51-55% | **True** | **A2 压力窗口真失活**（pre-clamp 意图=0，非 decay 抖动；post-clamp"假健康"=decay 0.97 伪装） |
| liquidity_premium | 0.474 | 38-40 ✅ | 0.18 | 78-82% | 12-16% | False | 有驱动但方向一致率低 |

- **加权一致率（sufficient-only）**：0.513 / 0.493 / 0.555 → **median 0.513 < 0.60 未达**（比 post-clamp 更真实——不是测量假象）
- **rho sentiment↔liquidity**：-0.655 / -0.731 / -0.691 → **三 seed 全超 |0.3|**（pre-clamp 揭示强负共驱动，post-clamp 掩盖）
- **新暴露真问题（第 3 轮候选）**：
  1. **A2 压力窗口失活**——credit pre-clamp 意图=0（A3 activation 0.75 后 visible hf SHORT 触发减少 + A2 activation 0.70/info_delay 2 → TIGHTEN 极少触发），credit 校准无写者可依
  2. **写者方向 vs target 系统性偏差**——sentiment/liquidity 有驱动但一致率 0.47-0.54：A1 CUT_25BP +0.30 sentiment 正写（P1-1 增强）与 target -0.5×grv 负期望**方向冲突**（政策对冲 vs 压力推低，target 只捕捉单方向），需引擎语义审计
  3. **rho 强负**——sentiment/liquidity 共写者（A3/A12）反向运动与 target 结构冲突
- **结论**：测量口径修正达成目标（真相揭示）；引擎真实动力学不达标，第 3 轮需先调查（A2 失活 + 写者方向审计）再修。按评审"无样本不验收"（credit dead）→ 保持 ship 阻塞状态，不调接受线



**修改理由**：P1——引擎行为失衡修复（A+D 修复批次，calib-fix-review 终局 2026-08-08）。探针实证三变量三种死法（sentiment 钉死 -1.0 / liquidity cap 假收敛 / bank_credit 单向漂移），修复 damping 双压与 MONTHLY_SCALE 尺度失衡。

### 修改

- **`core/world_state.py`**（apply_sentiment_delta）
  - **A 修复：damping 下限**。原 `1/(1+3|s|)` 在 s=-1 时压到 0.25 → 与 MONTHLY_SCALE 双压，sentiment 欠响应钉死 floor 根因。初版 floor 0.5 实测仍不足（贴边 54%>50%、正 delta 18%<20%），按终局裁决授权升 **A=1.0**（damping 恒 1，恢复不受压缩）
- **`core/simulation.py`**（_apply_delta）
  - **D 修复：MONTHLY_SCALE 0.12→0.25**。根因：MONTHLY_SCALE 只作用于 sentiment（apply_sentiment_delta 前乘），credit/liquidity 走 else 分支不经缩放 → sentiment delta 尺度小 8 倍。arch 拒 1.0（8 倍跳重演 v2.0.1 振荡史）；回退闸=预测回归振荡→回 0.12
- **`core/calibrator.py`**
  - **A2 写者补丁**：ERROR_VAR_WRITERS market_sentiment 清单补 A2（simulation.py:138 EASE_CREDIT 写 -0.08*m，原清单漏——守卫 B 判定不受影响但清单必须与 gm 规则一致）
  - **EASE 定向探针两级（ship 闸）**：新增 `_run_ease_probe`——独立子探针强制初始 bank_credit_tightening=0.3（[0,1] clamp 吃 0 起步写入测不出落地），测 ①决策层 EASE_CREDIT 可达性 ②写层负 delta |Δ|≥0.005 落地；PASS=两级全过，FAIL=ship 阻塞（校准不阻塞）
  - **探针增强**：per_var 加 `silence_frac`（S 类占比，D 触发条件 ①）；新增 `_print_d_trigger_check` 对照打印 D 触发条件（silence>50% / act<30% / m_v<0.005 死线 / 0.025-0.05 参考线）
- **`VERSION`**：v2.0.27 → v2.0.29（补 v2.0.28 遗漏：v2.0.28 提交时未更新 VERSION/CHANGELOG，实际内容见 v2.0.28 条目下方 commit 32cb21586）

### 验证

- ✅ 本地 ast.parse 三文件语法 + import 冒烟（A2 写者补丁生效）
- ✅ 容器 md5 三文件双端一致 + container import OK
- ✅ 50 步探针复测（seed 42/7/123 三轮）：sentiment 一致率 0.385→~0.55（大幅改善）；bank_credit 0.55-0.61 边缘；liquidity 仍死（cap 假收敛，OPEN-DECISIONS 已登记引擎驱动链复核）；EASE ship 闸 FAIL（tightening 锁 0.97，实证另立 issue ③ TIGHTEN vs EASE 不对称）
- ⚠️ **接受线未达**：加权一致率 0.51-0.55 < 60% → 按回退阶梯上报 ε_act 团队决议（见 OPEN-DECISIONS）

## v2.0.28 — 2026-08-08 (by WorkBuddy) — 补录

**修改理由**：P1——校准 C1-1a/C3-3a 改造（终局裁决 2026-08-07，commit 32cb21586）。此条目补录：原提交未更新 VERSION/CHANGELOG。

### 修改

- **`core/calibrator.py`**：delta 口径（sim_delta=now-last 比 target）、per-var 相对触发 |e|/|t|>0.5+限流 2 步、一致性率评分 score=100×Σw×rate、_step_eligibility 四类（N/U/S/T）、三守卫（A 活跃/B 塌缩/C 调参带）、run_probe 探针（写 calib_probe.json + target_scale 系数重标定）、趋势比率制、error_history 双口径字段、CACHE_VERSION=2
- **`core/simulation.py`**：em_capital_outflow 对称 clamp（C3-3a，L551-553）
- **`VERSION`**：应为 v2.0.28（本次补录时已升至 v2.0.29，见上）

### 验证

- ✅ 50 步探针实证：liquidity_premium 死变量（m_v=0, dead=True）；一致率全 <60%（0.44/0.48/0.50）；sentiment target_scale=0.053 实证系数无尺度依据；rho sentiment↔liquidity 负相关 -0.586
- ✅ 部署：docker build macro-sim:latest → compose up --force-recreate → 容器内验证 import OK + 探针跑通

## v2.0.27 — 2026-08-08 (by WorkBuddy)

**修改理由**：P1——校准 score=0 根因修复（S 类主权 Agent 扰动校准循环，question `20260808-world-deduction-calibration-s-class-disturbance`）。

### 修改

- **`core/calibrator.py`**（run_calibration）
  - **校准期 S 类主权 Agent activation_prob 置 0**：校准是 50 个月历史拟合（2022-06→2026-07），S 类主权行为 08-07 才激活（A 类激活），历史期本不该有它们参与；校准循环 model.step() 让 S 类按 0.35 激活并写 grv_dimensions/sentiment 扰动内生变量（实测 3 步 6 次激活 → score 0，A/B 双组 0.70/0.67 一致证明与 3 soul 试点无关）
  - **仅校准期生效**：预测期 run_prediction 独立 load_agents（bifurcation.py L363），重新拿原始 activation_prob=0.35，不受影响
- **`VERSION`**：v2.0.26 → v2.0.27

### 验证

- ✅ 本地：校准期挂起后 3 步仿真 S 类激活 0 次（修复前 6 次）
- ✅ 预测期隔离：run_prediction 独立 load_agents 确认
- 待：容器内完整校准回归（nohup 分离），验证 score 恢复（≥ 历史 80×0.95=76）

## v2.0.26 — 2026-08-07 (by WorkBuddy)

**修改理由**：天璇 v3 soul 化重构 **阶段 2**（试点 3 soul + 校准扩展）——设计文档 §4.1/4.3/4.5 + §5.5 A 路；历史事件回放方向校验通过。

### 修改

- **`souls/A1_fed.yaml`（新增）**：A1 美联储试点 soul——dove_emergency/dove/neutral/hawk 4 派系（设计 §4.1，[T-1993] Taylor Rule 锚点）；red_line_triggers 用 **dict 格式**（`market_sentiment < -0.6 → CUT_50BP`，金融 soul 指定强制行动）；hawk trigger 保留 market_sentiment 代理通胀【代理】（v1.2 P0-1，天枢 CPI 落地后切换）
- **`souls/A3_hedge_fund.yaml`（新增）**：A3 对冲基金试点 soul——risk_off/risk_reduce/contrarian/risk_on/neutral 5 派系（设计 §4.3，[DT-1985] 过度反应/[S-2016] VIX）；**旧 OVERSOLD_BOUNCE_PROB=0.45 → contrarian 派系权重承接**（概率参数化进 soul）
- **`souls/A6_media.yaml`（新增）**：A6 媒体试点 soul——fear/fear_from_actions/optimism/saturation/neutral 5 派系（设计 §4.5，[S-2019] 叙事经济学）；saturation 派系防单向推到底
- **`config/agents.yaml`**：A1/A3/A6 挂 soul_file（无 soul 时自动 fallback 旧 if-else）
- **`core/agents/base.py`**：
  - `_eval_trigger` 支持 **dict 格式 red_line_triggers**（{trigger: action}，金融 soul 指定强制行动）
  - 新增 `_derive_soul_flags()`：flag_* 布尔从 visible_actions 派生（v1.2 P2-1，走 info_delay 分层）
  - **修复 `_eval_trigger` 内置函数 bug**：abs() 等函数名被当作 ctx 变量替换 → `0.0(market_sentiment)` SyntaxWarning 恒 False（A6 neutral trigger 暴露，阶段 1 遗留）
  - `apply_param_adjustment` 支持 `internal_factions.{faction}.weight` 路径（§5.5 A 路）
- **`core/calibrator.py`**：LLM 调参支持派系权重路径（`internal_factions.<派系>.weight`，区间 0.01~0.9，保持总权重≈1 提示）；prompt 说明 A1/A3/A6 可调派系权重
- **`smoke_v3_phase2.py`（新增）**：阶段 2 验收（6 项）
- **`VERSION`**：v2.0.25 → v2.0.26

### 验收（smoke_v3_phase2.py 本地全过 + 阶段 1 回归）

- ✅ 3 试点 soul 加载（A1 4 派系 / A3 5 派系 / A6 5 派系）
- ✅ **历史事件回放方向校验（§5.5 C 路）**：2022 加息→A1 hawk 方向正确（HIKE 显著产出 7/30）+ 权重敏感性验证（hawk=0.45 → 22/60 HIKE 主导，证明默认 0.20 待校准）；2023 SVB→A3 risk_off 主导（SHORT+DECREASE 16/30）
- ✅ flag_* 布尔注入（visible_actions 派生 + A1 delay=4 分层不被破坏）
- ✅ A1 red_line dict 格式（深恐慌 → CUT_50BP source=red_line）
- ✅ 派系权重调参路径（apply_param_adjustment internal_factions.hawk.weight 0.2→0.3）
- ✅ 阶段 1 回归全过（S 类行为不变、9 个无 soul 金融 Agent 一致性保持）

## v2.0.25 — 2026-08-07 (by WorkBuddy)

**修改理由**：天璇 v3 soul 化重构 **阶段 1**（统一决策框架）——设计文档 `docs/tianxuan-v3-soul-redesign.md` v1.3 §3/§8.1；行为零变化（无 soul Agent 逐行动与 v2 一致）。

### 修改

- **`core/agents/base.py`**
  - **新增 `ActionDecision` dataclass**（§3.2）：action/reason/evidence/faction/confidence/source，统一决策输出（决策理由可校验，需求①）
  - **`_eval_trigger` 从 sovereign.py 上移** + missing_strategy 支持（v1.3 R-P1 语义：optimistic=缺失归 0 不触发 / conservative=按最坏情况触发 / neutral=归 0.5）
  - **`decide()` 兼容入口保留**（返回 str，行为与 v2 完全一致）；**新增 `decide_with_decision()` 统一出口**（有 soul → `_decide_soul()` 统一管线；无 soul → `_decide_rules()` 包一层 fallback）
  - **新增 `_decide_soul()` 统一 soul 管线**（§3.3）：red_line_triggers → 派系权重（weight×boost×sensitivity）→ 加权抽样（decision_temperature 支持，0=argmax）→ bias_actions 选行动；含 `_snapshot_signals`/`_escalation_action`/`_faction_to_action`/`_soul_faction_bias` 通用版
- **`core/agents/sovereign.py`**
  - soul 决策逻辑上移 base（`SovereignAgent._decide_rules` 仅剩无 soul fallback HOLD；`EnergyGovSovereignAgent` 保留无 soul 能源退化规则）
  - `_eval_trigger` 改为从 base import（兼容导出）
  - 保留 `_faction_to_action`/`_get_faction_bias`/`_escalation_action` 特化版（S 类行为与 v2.2 完全一致，含 impact_map 过滤与硬编码 bias fallback）
- **`core/simulation.py`**
  - step() Phase 1 改用 `decide_with_decision()`（行为等价——decide() 即取 .action）；**新增 `decision_trace` 收集**（每步每激活 Agent 的 ActionDecision.to_dict()，trace 落盘骨架，结果层 v3 启用）
- **`VERSION`**：v2.0.24 → v2.0.25

### 验收（smoke_v3_phase1.py 本地全过）

- ✅ 无 soul Agent **240 次**逐行动对比（20 ctx × 12 金融 Agent，同 seed 序列）mismatch=0 —— 行为与 v2 完全一致（含随机消耗模式）
- ✅ ActionDecision schema 完整性；✅ S 类统一 soul 管线产出正常（GRV=80 高压：S1 MILITARY 4/5、S4 NUCLEAR 5/5 等符合 v2.2 验证行为）
- ✅ decision_trace 3 步仿真收集；✅ missing_strategy 三态语义（optimistic 不触发 / conservative 最坏情况触发）

## v2.0.24 — 2026-08-07 (by WorkBuddy)

**修改理由**：P1——calibrator.py 新旧两份代码并存（D2/D3 fix 被旧版覆盖静默失效，红线 #8）。question：`20260807-world-deduction-calibrator-duplicate-code`。

### 修改

- **`core/calibrator.py`**（680 → 384 行）
  - **删除 L356-679 旧版完整副本**：旧版（外生变量误差 ERROR_WEIGHTS={grv/credit_spread/t10y2y/dff}）定义在后，Python 后定义覆盖前定义 → D2/D3 fix（2026-08-03 声称已修的内生变量误差）实际从未生效
  - **恢复生效**：ERROR_WEIGHTS 现为内生变量版（market_sentiment 0.35 / bank_credit_tightening 0.30 / liquidity_premium 0.20 / em_capital_outflow 0.15）
  - **D6 校准缓存读取逻辑从旧版移植**（新版原只有写入无读取）：<7 天命中缓存跳过 50 步校准
- **`VERSION`**：v2.0.23 → v2.0.24

## v2.0.23 — 2026-08-04 (by Claude Code)

**修改理由**：P4——天玑 V1 验证链路迁移。评分/建表职责迁出天璇：天玑已独立为容器 macro-ji v1.0.0（T2 watchdog 接管验证链路），天璇不再内嵌 Brier 评分与 tianji 建表；同时标注迁移后残留的孤儿代码。

### 修改

- **`run.py`**
  - **删除 `run_scoring()`**：原"从 `forecast_tracker.db` 读到期预测、算 Brier/BSS/锐度、写 `brier_latest.json`"的评分逻辑整体移除——天玑已迁出为独立容器 macro-ji v1.0.0（T2 watchdog 接管验证），天璇内不再需要评分入口
  - **删除 `_TIANJI_DDL`**：幂等建表（predictions + reasoning_trace）移除，`_tianji_conn()` 不再执行 executescript，schema 由天玑侧维护
  - **保留 `_archive_to_tianji()` 归档链**：仿真完成后仍将可验证预测写入共享 `forecast_tracker.db`（`/app/macro_data`，与天玑共享同一 DB），`run_simulation()`/`run_predict_only()` 中归档调用不变
  - **`_write_json()` / `_send_ntfy_simple()` 标注为孤儿代码**：原为 run_scoring 服务，现无任何调用方，暂保留待后续清理
  - `run_simulation()` / `run_predict_only()` 中原 run_scoring 调用点移除

- **`VERSION`**：v2.0.22 → v2.0.23


## v2.0.22 — 2026-08-04 (by Claude Code)

**修改理由**：B+A/NOVEL Sprint-2——A2/A3/A6 soul 文件在位激活；慢变量 irp/ucri/gci 注入 MacroWorldState；D6 校准缓存实现。

### 修改

- **`config/agents.yaml`**（Sprint-2 soul 预位）
  - A2 加 `soul_file: A2_china.yaml`（注释：B+A/NOVEL 重写后将成为中国主权 Agent）
  - A3 加 `soul_file: A3_eu.yaml`（注释：B+A/NOVEL 重写后将成为欧盟主权 Agent）
  - A6 加 `soul_file: A6_russia.yaml`（注释：B+A/NOVEL 重写后将成为俄罗斯主权 Agent）
  - soul 文件由 load_agents() 加载到 agent.soul 字段，当前 MacroAgent 基类接收但不激活派系决策（只有 SovereignAgent 子类使用）

- **`core/world_state.py`**（慢变量注入）
  - `MacroWorldState` 新增字段：`irp: float = 0.0` / `ucri: float = 0.0` / `gci: float = 0.0`
  - `load_from_macro_scan()` 末尾读取 `/app/macro_data/slow_variables.json`，注入 irp/ucri/gci，文件不存在时安全默认 0.0

- **`core/calibrator.py`**（D6 校准缓存）
  - 两个 `run_calibration()` 函数均加入：
    - **入口**：读 `/app/data/calibration_cache.json`，时间戳 <7 天时直接加载参数，返回 `_from_cache: True`，跳过50步校准
    - **出口**：校准完成后写缓存（含 timestamp / score / agents 参数）

- **`VERSION`**：v2.0.21 → v2.0.22



## 2026-08-03 [2.0.21] B+A/NOVEL Sprint-1：SovereignAgent 基类 + Board + 3个主权 soul 文件（by Claude Code）

**修改者**：Claude Code  
**修改理由**：agent_taxonomy.md 蓝图落地第一步——实现 SovereignAgent 基类和 Board 关系矩阵，让 A4（能源国/OPEC+）成为第一个由 soul 文件驱动决策的真实地缘 Agent。

### 新增文件

- **`core/agents/sovereign.py`**（新建）
  - `SovereignAgent` 基类：继承 MacroAgent，重写 `_decide_rules`
  - 派系权重决策：读取 `self.soul.internal_factions`，按触发条件动态调整权重，加权抽样选派系
  - Red Line 检查：触发时强制返回最高影响行动
  - `_eval_trigger()`：解析 soul 文件中的条件字符串（支持 `>/<` + `AND/OR`）
  - `_faction_to_action()`：派系 → 行动映射，优先从 `grv_impact_map` 选择
  - `get_grv_impact()`：返回行动预期对 GRV 各维度的影响（供 B+A/NOVEL 引擎消费）
  - `Board` 全局关系矩阵：`board_get/board_set/board_clear()` 三个函数，存储 Actor 间联盟/制裁/冲突关系
  - `EnergyGovSovereignAgent`：A4 的具体子类，覆盖 VALID_ACTIONS 和派系偏好映射

- **`souls/A2_china.yaml`**（新建，设计文档，未激活）
  - 中国主权 Agent：doctrine（斗而不破）、4条 red_lines、3个派系（民族主义/务实派/稳定派）、cultural_prior（Hofstede PDI=80）、grv_impact_map

- **`souls/A3_eu.yaml`**（新建，设计文档，未激活）
  - 欧盟集体主权 Agent：doctrine（规范性权力）、3条 red_lines、3个派系（大西洋派/战略自主/紧缩派）、grv_impact_map（含 ENERGY_INDEPENDENCE 行动）

- **`souls/A6_russia.yaml`**（新建，设计文档，未激活）
  - 俄罗斯主权 Agent：doctrine（战略纵深）、4条 red_lines、3个派系（强硬派/务实派/寡头）、grv_impact_map（含 NUCLEAR_SIGNAL 行动）

### 修改文件

- **`core/simulation.py`**
  - A4 GM 规则段扩展：原 `CUT_SUPPLY`/`INCREASE_SUPPLY` 扩展为5个新行动
    - `CUT_OUTPUT`：能源供给风险↑ + 市场情绪↓
    - `INCREASE_OUTPUT`：能源供给风险↓ + 市场情绪↑
    - `EMBARGO_SIGNAL`：能源供给风险大幅↑ + 流动性溢价↑ + 市场情绪↓（强度最高）
    - `DIPLOMATIC_OUTREACH`：能源供给风险略↓ + 市场情绪略↑
    - 旧 `CUT_SUPPLY`/`INCREASE_SUPPLY` 保留为别名（向后兼容）

- **`config/agents.yaml`**
  - A4 `class` 从 `geopolitical.EnergyGovAgent` 改为 `sovereign.EnergyGovSovereignAgent`
  - A4 `soul_file: A4_gulf_opec.yaml` 已配置

- **`core/agents/base.py`**（上个版本已改）
  - `MacroAgent` 新增 `soul: dict` 字段

- **`core/simulation.py`**（上个版本已改）
  - `load_agents()` 新增 soul 文件加载逻辑

- **`VERSION`**：2.0.20 → 2.0.21

### 验证

```bash
docker exec macro-sim python3 -c "
from core.simulation import load_agents
from core.agents.sovereign import SovereignAgent, BOARD, board_set
agents, cfg = load_agents()
a4 = agents['A4']
print('A4 类型:', type(a4).__name__)
print('A4 soul 派系:', list(a4.soul.get('internal_factions', {}).keys()))
# 模拟一次决策
ctx = {'energy_tension': 0.6, 'grv_stress': 0.8, 'middle_east_energy': 72.0}
action = a4.decide(ctx)
print('A4 决策:', action)
print('Board 当前状态:', BOARD)
"
```

### 未动（下一 Sprint）

- A2/A3/A6 soul 文件尚未在 agents.yaml 中激活（等 SovereignAgent 基类验证稳定后）
- Board 目前只有读写 API，尚无自动更新逻辑（行动→Board 状态变更需在 Step 函数中实现）
- Secretary Agent 验证层尚未实现



**修改者**：Claude Code  
**修改理由**：arch_review D2/D3 缺陷——原误差函数测量 grv(0.4)/credit_spread(0.3)/t10y2y(0.2)/dff(0.1) 四个外生变量，但 Agent 行动物理上无法直接改变 GRV，LLM 调参时看到 GRV 偏差就调整无关参数，形成系统性错误的参数调整方向。

### 核心改动（`core/calibrator.py` 完整重写）

**ERROR_WEIGHTS 替换：**
- 原：`grv×0.4 + credit_spread×0.3 + t10y2y×0.2 + dff×0.1`（全是外生变量）
- 新：`market_sentiment×0.35 + bank_credit_tightening×0.30 + liquidity_premium×0.20 + em_capital_outflow×0.15`（全是内生变量，直接由 Agent 行动驱动）

**软目标（soft target）机制（新增 `_derive_endogenous_targets()`）：**
历史数据中没有内生变量真实记录，改为从相邻两月外生变量变化推导期望方向：
- GRV↑ → market_sentiment 应↓（负相关）
- credit_spread↑ → bank_credit_tightening 应↑
- GRV↑ + credit_spread↑ → liquidity_premium 应↑
- GRV↑ + t10y2y↓ → em_capital_outflow 应↑（避险逃离新兴市场）

**方向惩罚误差（新增）：**
- 方向相反（仿真值与期望方向异号）时误差 ×1.5 惩罚
- 鼓励方向正确优先于幅度准确

**Teacher Forcing 修复（D3 同步修复）：**
- 原：每步结束后注入 grv/credit_spread/t10y2y/dff，同时也覆盖内生变量（行为未定义）
- 新：Teacher Forcing 只注入 `EXOGENOUS_VARS`（grv/credit_spread/t10y2y/dff/grv_energy/us_china_grv/vix），**不覆盖内生变量**，让内生变量在校准期自由演化

**LLM prompt 更新：**
- 偏差描述改为"仿真值 vs 期望方向 [✓同向/✗反向]"
- 明确列出每个内生变量的主要驱动 Agent，引导 LLM 调参方向准确

**`build_history_range()` 简化：**
- 内生变量无历史真值，统一使用 [-1, 1] 标准范围，不再从数据计算

- **`VERSION`**：2.0.19 → 2.0.20

### 预期效果

校准循环中 LLM 的调参目标从"让仿真 GRV 更接近真实 GRV"变为"让情绪/信贷/流动性等内生变量在正确方向演化"。参数调整方向与实际因果链对齐，校准结果对后续预测有实际参考价值。



**修改者**：Claude Code  
**修改理由**：为 B+A/NOVEL 天璇重写铺设最小可运行骨架——soul 文件机制向后兼容（不配置 soul_file 的 Agent 行为完全不变），同时让 A4（能源国/OPEC+）立即获得 doctrine/red_lines/factions 结构。

### 改动

- **`core/agents/base.py`**
  - `MacroAgent` 新增 `soul: dict = field(default_factory=dict)` 字段
  - 文档注释补充 soul 文件设计说明（doctrine/red_lines/internal_factions/cultural_prior 字段说明）

- **`core/simulation.py`**
  - `load_agents()` 新增 soul 文件加载逻辑：
    - 读取 agents.yaml 中可选的 `soul_file` 字段
    - 从 `config/../souls/{soul_file}` 路径加载 YAML
    - 加载失败（文件不存在）时静默跳过，`soul={}` 保持现有行为
    - 加载成功后通过 `soul=soul` 传入 Agent 构造函数

- **新建 `souls/A4_gulf_opec.yaml`**（立即激活）
  - 海湾国家/OPEC+ 主权 Agent soul 文件
  - 包含：doctrine（石油定价+地区外交策略）、red_lines（4条）、resources、cultural_prior（Hofstede UAI/PDI）、internal_factions（财政鹰派/现代化派/安全鹰派）、grv_impact_map（5个行动→GRV影响方向）

- **新建 `souls/A1_usa.yaml`**（设计文档，未激活）
  - 美国主权 Agent 原型，为 B+A/NOVEL SovereignAgent 基类准备
  - 当前 agents.yaml 中 A1 仍是美联储，B+A/NOVEL Sprint 创建 SovereignAgent 后激活

- **`config/agents.yaml`**
  - A4 条目新增 `soul_file: A4_gulf_opec.yaml`

- **`VERSION`**：2.0.18 → 2.0.19

### 验证

```bash
docker exec macro-sim python3 -c "
from core.simulation import load_agents
agents, cfg = load_agents()
a4 = agents['A4']
print('A4 soul keys:', list(a4.soul.keys()))
print('doctrine:', a4.soul.get('doctrine', '')[:50])
print('red_lines:', len(a4.soul.get('red_lines', [])), '条')
print('factions:', list(a4.soul.get('internal_factions', {}).keys()))
"
# 预期输出：
# A4 soul keys: ['actor_id', 'actor_type', 'name', 'layer', 'doctrine', ...]
# red_lines: 4 条
# factions: ['fiscal_hawks', 'modernization_wing', 'security_hawks']
```

### 未动

- A4 的 `_decide_rules` 尚未读取 soul 字段，soul 加载后不影响当前仿真输出
- SovereignAgent 基类尚未创建（B+A/NOVEL Sprint 核心任务）



**修改者**：Claude Code  
**修改理由**：arch_review D14 缺陷——`make_world_from_history_row`（校准期历史行构建）中 `ecb_rate` 和 `usd_cny` 硬编码为默认值 3.0/7.1，导致欧央行/中国央行相关 Agent 在整个校准期基于假数据决策。

### 改动

- **`core/world_state.py`**
  - `load_monthly_history()`：新增 `read_fred_csv("ECBDFR.csv", "ecb_rate")` 和 `read_fred_csv("DEXCHUS.csv", "usd_cny")` 两行
  - `load_monthly_history()` result 列表：补入 `"ecb_rate"` 和 `"usd_cny"` 字段（fallback 3.0/7.1）
  - `make_world_from_history_row()`：`dff` 改为 `row.get("dff")` 防 KeyError；补入 `ecb_rate` 和 `usd_cny` 从历史行读取
- **`VERSION`**：2.0.17 → 2.0.18

### 效果

校准期 50 步中，欧央行（A3 内部派系）和中国央行（A2 内部派系）将使用真实历史汇率/利率数据，而非固定假值。历史数据无 ECBDFR/DEXCHUS 字段时 fallback 不变，向后兼容。



**修改者**：Claude Code  
**修改理由**：D7 修复续集——v2.0.16 补了6个来自 grv_latest.json 的维度，但 social_stress/cultural_friction 存在 gdelt_scores.json 而非 grv_latest.json，需由 geo_risk_vector.py 聚合后透传。

### 改动

- **`core/world_state.py`**
  - `MacroWorldState` 新增 `social_stress` / `cultural_friction` 两个字段（默认 0.0）
  - `load_from_macro_scan()` 从 grv_latest.json 读取（由天枢 geo_risk_vector 聚合写入）
  - `to_dict()` 输出包含新字段
  - `get_agent_context()` 中 `media` 角色新增 `social_stress` / `cultural_friction`（媒体放大社会压力的核心驱动）
- **`VERSION`**：2.0.16 → 2.0.17


## 2026-08-03 [2.0.16] D7 fix：MacroWorldState 接入 6 个新 GRV 维度（by Claude Code）

**修改者**：Claude Code  
**修改理由**：D7 缺陷——天枢 geo_risk_vector 产出 11 维 GRV，但 MacroWorldState 只读取 5 维，导致 climate_risk/disaster_risk/sanctions_risk/seismic_risk/energy_grid_risk/japan_monetary 被仿真引擎完全忽略。

### 改动

- **`core/world_state.py`**
  - `MacroWorldState` 新增 6 个外生变量字段（均有默认值 0.0，向后兼容）：
    `climate_risk` / `disaster_risk` / `sanctions_risk` / `seismic_risk` / `energy_grid_risk` / `japan_monetary`
  - `load_from_macro_scan()` 从 `grv_latest.json` 读取这 6 个字段（`or 0.0` 防 None）
  - `to_dict()` 输出包含 6 个新字段
  - `get_agent_context()` 三处增强：
    - `energy_gov` 角色新增 `energy_grid_risk` / `climate_risk`
    - `hedge_fund` / `institution` 角色新增 `sanctions_risk` / `disaster_risk` / `seismic_risk`
    - `boj` 角色新增 `japan_monetary`（直接驱动 BOJ 决策的天枢信号）
- **`VERSION`**：2.0.15 → 2.0.16

### 注意

- `social_stress` / `cultural_friction` 两个维度来自 `gdelt_scores.json` 而非 `grv_latest.json`，读取路径不同，本次未处理，留待 B+A/NOVEL 重写 Sprint
- 6 个新字段全部有 `= 0.0` 默认值，calibrator.py / bifurcation.py 等调用处无需修改


## 2026-08-03 [2.0.15] D1/D4/D12 P0 bug 修复（by Claude Code）

**修改者**：Claude Code  
**修改理由**：arch_review_20260802 裁定的三个 P0 代码缺陷，导致仿真输出数值不可信。

### 改动

- **`core/simulation.py`**（D1 fix）：传导矩阵全量 delta 叠加 → per-agent delta 追踪
  - 引入 `per_agent_delta: dict[str, dict]` 和 `add(agent_id, key, val)` 辅助函数
  - 每个 Agent 只传导自己产生的 delta，不再把全量累积 delta 乘以传导系数
  - 修复前：N 个 Agent 激活时传导强度 = 单 Agent 的 N 倍；修复后：各 Agent 独立传导
  - 移除原 `active_count` 除法（该除法是对该 bug 的错误补偿）

- **`core/world_state.py`**（D4 fix）：`apply_natural_decay` 补充 4 个遗漏变量
  - 新增月度衰减：`fund_risk_appetite *= 0.90`、`em_capital_outflow *= 0.93`、
    `us_fiscal_pressure *= 0.97`、`china_credit_impulse *= 0.92`
  - 修复前：这 4 个变量无衰减，100 步内单调漂移至边界后锁死

- **`run.py`**（D12 fix）：`_archive_to_tianji` content 与 target_metric 对齐
  - `content` 从 "GRV taiwan_strait 预计..." 改为 "GRV global_composite 预计..."
  - 与 `target_metric = "global_composite"` 和 `outcome_definition` 三者一致
  - 修复前：验证时实际测量 global_composite，但 content 描述的是 taiwan_strait，Brier 分评的是错误变量

### 验证

```bash
docker exec macro-sim python -c "from core.simulation import gm_resolve_rules; print('D1 OK')"
docker exec macro-sim python -c "from core.world_state import apply_natural_decay; print('D4 OK')"
```



**修改者**：Claude Code  
**修改理由**：天璇仿真引擎从未向 `forecast_tracker.db` 的 `predictions` 表写入任何真实预测数据，导致天玑验证层和校准闭环完全空转。根本原因：旧 `_archive_to_tianji` 通过动态 import `tianji_db.py` 写入，但该路径（`/workspace/核心代码/tianji_db.py`）在容器内不存在且未挂载，每次都静默走 `except` 分支失败。

### 改动

- **`run.py`**：重写 `_archive_to_tianji` 函数
  - 移除对 `tianji_db.py` 的动态 import 依赖，改为直接用 `sqlite3` 写入
  - 新增 `_TIANJI_DB_PATH`：默认 `/app/macro_data/forecast_tracker.db`（可通过环境变量 `TIANJI_DB_PATH` 覆盖），对应容器内已挂载的 `macro-scan/data/` rw 目录
  - 新增 `_TIANJI_DDL`：幂等建表（predictions + reasoning_trace），无需依赖外部 schema 文件
  - 新增 `_tianji_conn()` 辅助函数：打开连接 + 执行 DDL + 开启 WAL
  - 写入格式改为概率分布（非点估计），符合架构裁定：
    - GRV 方向预测：`prediction_target_type = "grv_direction"`，`due_at = 3个月`，direction 基于 ±5 阈值（up/down/neutral），`confidence_tier` 按 probability 自动判断
    - 地缘事件：`prediction_target_type = "geopolitical_event"`，`status = "awaiting_human"`，`due_at = 6个月`
  - 失败时打印完整 traceback，不再静默降级
- **`run.py:run_predict_only()`**：补加 `_archive_to_tianji` 调用（原来缺失）
- **`VERSION`**：2.0.14 → 2.0.15

### 验证

- 仿真完成后控制台打印 `[tianji] ✅ 存档 N 条预测 → /app/macro_data/forecast_tracker.db`
- `sqlite3 forecast_tracker.db "SELECT COUNT(*) FROM predictions"` 应返回非零

### 不动

- 报告输出格式、ntfy 推送、校准逻辑、bifurcation.py 均未变动
- `tianji_db.py`（天枢侧）未改动，两边独立维护 schema，幂等 DDL 保证兼容

---

## 2026-07-31 [2.0.14] P0 修复：sim_trigger 单文件 bind mount inode 断链（by WorkBuddy/齐活林）

**修改者**：WorkBuddy（齐活林）
**修改理由**：三探针实测（P3）发现 P0 级未爆弹——scan 侧 `grv_threshold.py` 用 `os.replace()` 原子写 `sim_trigger.json`（更换 inode），而 macro-sim 以 **single-file bind mount** 挂载该文件，原子写换 inode 后容器内挂载锁死在旧 inode，scan 新触发信号永远进不了天璇（隔离容器实验实证：单文件挂载断链、目录挂载正常）。现存文件已 0 字节停更 Jul25。若不修，下次 GRV>=68 触发时天璇永久失联且全程静默。

### 改动（修法 A：目录挂载，保留 scan 原子写）
- `docker-compose.yml`：删除单文件挂载 `.../data/sim_trigger.json:/app/sim_trigger.json`，将 `.../macro-scan/data:/app/macro_data` 由 `:ro` 改 `:rw`（sim 消费后需原地清空触发文件）
- `run.py` L22：`TRIGGER_PATH = Path("/app/sim_trigger.json")` -> `Path("/app/macro_data/sim_trigger.json")`

### 验证
- 重建镜像 + 从部署目录 `/vol2/1000/software/macro-sim` recreate 容器，挂载核验：单文件挂载消失、macro_data RW=True
- 端到端实测：scan 容器 `os.replace` 写测试文件 -> sim 容器经目录挂载立即读到新内容（断链根治）
- daemon 正常启动，轮询新路径 `/app/macro_data/sim_trigger.json`；现存 0 字节触发文件不会误触发（st_size>0 条件）

### 不动
- scan 侧 `grv_threshold.py` 零改动（os.replace 在目录挂载下安全）；schema 契约不变

## 2026-07-29 接口兼容确认：macro-scan v3.6.5 GRV 新增字段（by WorkBuddy, 无代码变更）

**修改者**：WorkBuddy
**修改理由**：macro-scan v3.6.5 `grv_latest.json` 新增 `sanctions_risk` / `seismic_risk` / `energy_grid_risk` 三个扩展维度（v3.6.4 引入，v3.6.5 全量验证产出）。macro-sim 当前只读前 5 维 + `japan_monetary`，JSON 有额外键不影响解析。本条目仅记录接口 schema 变更，无代码改动。

### 不动
- macro-sim 代码、CHANGELOG、VERSION 均未动，本次仅文档同步。


## 2026-07-28 [2.0.13] P3：叙事美化逻辑抽取为纯函数 format_narrative + 回归测试（by WorkBuddy/齐活林）

**修改者**：WorkBuddy（齐活林）
**修改理由**：v2.0.12 已在 run.py 内联完成 `**`→`【】` 归一化 + 美化分支修复（B1 第一次修复）。本次为可测性/可维护性二次改造：将 run.py L304–321 内联美化逻辑（含 `import re as _re`）抽取为纯函数 `core/narrative_format.format_narrative(raw: str) -> list[str]`，消除 run.py 局部 import、便于单元测试，行为逐字节等价（14 组样例 diff 全 `==`，IS_PASS: YES）。

### 修改
- **新增 `core/narrative_format.py`**：纯函数 `format_narrative(raw)` 封装归一化（`**label**`→`【label】`）+ `【】` 拆分 + 多段美化 / 兜底逻辑；仅依赖标准库 `re`，无循环 import。
- **`run.py:304-306`**：原 L304–321 整段替换为 `if path.narrative: from core.narrative_format import format_narrative; lines += format_narrative(path.narrative)`；删除原局部 `import re as _re`（grep 确认无残留引用）。
- **新增 `tests/test_narrative_format.py`**：自包含纯 Python 回归测试（不依赖 pytest），11 用例 ALL PASSED，锁定三类 `**label**` 主场景美化 + 空串/纯文本/数字前缀/单标签等边界。

### 不动
- 对外渲染格式（`**label**：content`）、仿真核心、数据流、跨子系统接口契约未变，向后兼容。
- 未改 `core/bifurcation.py` 的叙事 prompt（保持 v2.0.12 的诚实化 `**` 分隔符）。

### 已知边界（非主要场景，已固化测试，非阻塞）
- 单标签（如 `**只一个标签**\n内容`）走 else 分支不美化，保留 `【label】内容` 形态（换行被 bold 正则 `\s*` 吞掉）。
- 数字前缀列表首行（`1. **情景定性**\n内容`）因 `_DIGIT_PREFIX_RE` 仅匹配「\n数字.」、且单 label 走 else，输出 `1. 【情景定性】内容`，首行数字前缀未清理、不美化。GLM 实测稳定输出三类齐全的 `**label**：` 形态，上述边界在真实数据流极低频。

### 关联 question 文档
- B1: `docs/questions/world-deduction/20260718-world-deduction-report-narrative-separator-fragile.md`

---

## 2026-07-28 [2.0.12] P3：叙事分隔符兼容 GLM 真实 `**` 输出（by WorkBuddy/齐活林）

**修改者**：WorkBuddy（齐活林）
**修改理由**：B1 question 复查发现，叙事 prompt 要求 GLM 输出 `【情景定性】` 等方括号分隔符，但 GLM-Z1-9B（SiliconFlow，免费模型）实测稳定输出 `**情景定性**`（Markdown 加粗）。run.py 的叙事美化分支（`re.split/findall(r'【[^】]+】')`）只认 `【】`，导致 `findall` 永远空、美化逻辑死代码、报告始终走 else 原样兜底——"清晰"纯靠 `**` 被 MD 查看器碰巧加粗的侥幸，长期脆弱（见 B1 question 20260718）。

### 修改

- **`run.py:307` 后新增 1 行归一化**：`narrative = _re.sub(r'\*\*(.+?)\*\*\s*', r'【\1】', narrative)`
  - 把 GLM 真实输出 `**label**` 统一归一成约定 `【label】`，下方既有 `【】` 拆分/标签提取逻辑无需改动即可正确命中美化分支，三段规范化为 `**label**：content`。
  - 双兼容：GLM 未来吐回 `【】` 也照样生效；最坏情形（归一化未命中）仍落 else 兜底，不会比改动前更差。
- **`core/bifurcation.py:299-302` prompt 诚实化**：叙事结构指令由 `【情景定性】/【核心传导链】/【对你的影响】` 改为 `**情景定性**/**核心传导链**/**对你的影响**`，使 prompt 与 GLM 真实行为一致，消灭"生产者-消费者"契约错位（B1 方案 E）。

### 不动

- 美化分支下游输出格式（`**label**：content`）与改动前渲染一致，无视觉回归。
- 仿真核心 / 数据流 / 跨子系统接口契约未变，向后兼容。

### 关联 question 文档

- B1: `docs/questions/world-deduction/20260718-world-deduction-report-narrative-separator-fragile.md`

---

## 2026-07-25 [2.0.11] P0：GRV 历史 None 值防御（by Hermes）

**修改者**：Hermes
**修改理由**：v2.0.10 引入的 GRV 3 个月移动平均平滑代码对 JSON null 缺防御，`grv_history.jsonl` 中 `middle_east_energy` 维度大量历史 null（522 条中 498 条；2022-06 至今 73 个月中 49 条 null）触发 `TypeError: unsupported operand type(s) for +: int and NoneType`，整个仿真流水线立即崩溃，校准循环无法启动（详见 P0 question 20260725）。

### 修改

- **`core/world_state.py:271-275`**：将 `d.get(k, default)` 统一改为 `d.get(k) or default`：
  - 271: `grv` (`global_composite`) default 50.0
  - 272: `grv_energy` (`middle_east_energy`) default 0.0
  - 273: `grv_military` (`russia_europe` + `taiwan_strait`) 两路都加 `or 0` 兜底再除 200
  - 274: `grv_trade` (`us_china_strategic`) default 0
  - 275: `us_china_grv` (`us_china_strategic`) default 50.0
  - 防御模式：`dict.get(k, default)` 仅在 key 缺失时返回 default，对 value=None 不生效；改用 `... or default` 同时兜底两种情形
- **`core/world_state.py:320` 平滑列表推导**：增加 `w[k] is not None` 过滤
  - 原：`vals = [w[k] for w in window if k in w]`
  - 新：`vals = [w[k] for w in window if k in w and w[k] is not None]`

### 不动

- `data/grv_history.jsonl` 的 498 条历史 null **不回填 0**，由代码层防御吸收（保留原始数据、改动最小）
- 章节顺序/接口签名/下游数据流未变，向后兼容

### 关联 question 文档

- P0: `docs/questions/world-deduction/20260725-world-deduction-sim-2.0.10-grv-null-crash.md`

---

## 2026-07-24 [2.0.10] 校准质量改进：GRV平滑 + LLM误差趋势摘要（by Claude）

**修改者**：Claude Code  
**修改理由**：校准评分约70/100，根因是GRV历史2022-2026月度±30剧烈波动，仿真难以追随；同时LLM调参时无全局视角，参数反复横跳（见 macro-sim PROGRESS.md）。

### 修改

- **`core/world_state.py:load_monthly_history()`**：
  - 在合并结果之前，对所有GRV维度字段（grv/grv_energy/grv_military/grv_trade/us_china_grv）做3个月滑动窗口平均
  - 第1个月取自身，第2个月取前1+当月均值，第3个月起取前2+当月均值
  - 向后兼容：仅影响历史加载数据，不改接口签名
- **`core/calibrator.py:llm_suggest_adjustments()`**：
  - `error_history` 描述末尾新增趋势摘要行：前半段均值 vs 近半段均值，自动判断⬆上升/⬇下降/➡震荡并附说明
  - 帮助LLM识别"调参效果持续变差"vs"有效收敛"vs"参数反复横跳"三种模式

---

## 2026-07-15 [2.0.9] Q6：路径树节点归因标注（by Claude）

**修改者**：Claude Code  
**修改理由**：路径树关键事件只有事件名和频率，看不出是哪个 Agent 驱动的，调试和向决策者解释时无从下手。

### 修改

- **`core/bifurcation.py:_extract_key_events()`**：
  - 函数内新增 `AGENT_NAMES` 字典（12 个 Agent ID → 简短中文角色名）
  - 每条 `key_events` 记录新增三个字段：`agent_id`（如 `"A3"`）、`agent_name`（如 `"对冲基金"`）、`action`（原始 action 字符串）
  - 向后兼容：原有 `event` 字段不变，旧代码读取不受影响
- **`run.py:_write_report()`**：
  - 对比表"主要驱动"行：从 `事件名` 改为 `Agent名·简短动词`（如 `对冲基金·大规模做空`）
  - 传导链代码块：每行在事件名前加 `[Agent名]` 标注（如 `[对冲基金] 大规模做空（85%）`）
  - 月度演化进度条：同步加 `[Agent名]` 标注

### 关联 question 文档

- Q6: `docs/questions/world-deduction/20260714-world-deduction-path-tree-no-drivers.md`

---

## 2026-07-14 [2.0.8] Q3：跨 Agent 一致性校验（by Claude）

**修改者**：Claude Code  
**修改理由**：12 个 Agent 并行输出后直接进路径树，形式逻辑矛盾和经济学机制矛盾不被任何环节拦截，路径节点置信度失去意义。基于 IS-LM / Taylor Rule / Mundell-Fleming 三元悖论研究结论，建立两层校验机制。

### 修改

- **`core/consistency_validator.py`**（新建）：
  - Layer 1 规则表（10 条）：同一 Agent 工具方向相反（单工具单调性）+ 同一美国金融体系内部机制矛盾（Fed加息+银行放贷 / 散户情绪与媒体情绪对立）
  - Layer 2 LLM 校验（默认关闭）：Layer 1 命中且 `use_llm=True` 时调用，区分真矛盾与跨经济体合理分歧
  - 跨经济体政策分歧（Fed vs PBOC/ECB/BOJ）白名单化，永远不触发
- **`core/bifurcation.py`**：
  - `PathResult` 新增 `consistency_warning: str` 字段
  - `run_prediction()` 每个 run 结束后调用 `validate_run_actions(history)`，矛盾标注到 history 末尾
  - 路径构造时汇总：>30% 的 run 有矛盾则在 `path.consistency_warning` 写入统计

### 设计约束

- MC 阶段 `use_llm=False`（默认），Layer 2 不触发，零额外 API 成本
- 不丢弃任何 run，路径树概率数字不变，只加透明度标注
- 规则表保守：宁可漏报，不误报

### 关联 question 文档

- Q3: `docs/questions/world-deduction/20260714-world-deduction-no-cross-agent-validator.md`

---

## 2026-07-14 [2.0.7] Q9/Q10 修复：bleed 敏感性接口 + LLM 叙事打通（by Claude）

**修改者**：Claude Code  
**修改理由**：Q9 需要 bleed_params_override 接口才能做参数 sweep；Q10 将 daily_narrative 叙事接入 Agent 文本输入，打通之前独立的两条管道。

### 修改

- **`core/simulation.py`**：
  - `MacroSimModel.__init__()` 新增 `bleed_params_override: dict = None` 参数
  - `step()` 将 `bleed_params_override` 透传给 `apply_bleed_rules()`
  - `_apply_delta()` 注释修正（MONTHLY_SCALE 0.12 设计值 vs 实测值说明，即 Q8）
- **`core/bifurcation.py`**：`run_prediction()` 新增 `bleed_params_override` 参数并透传给 `MacroSimModel`
- **`core/world_state.py`**：`load_from_macro_scan()` 读取 `news_export.json` 后追加读 `daily_digest.json`（当日叙事 bullets 注入 `recent_news`，非阻断）
- **`scripts/bleed_sensitivity.py`**（新建）：3^4=81 组参数 × 100 次 MC sweep，输出主效应分析报告

### 关联 question 文档

- Q8: `docs/questions/world-deduction/20260714-world-deduction-monthly-scale-magic-number.md`
- Q9: `docs/questions/world-deduction/20260714-world-deduction-bleed-rules-no-sensitivity.md`
- Q10: `docs/questions/world-deduction/20260714-world-deduction-llm-narrative-not-in-sim.md`

---

：transmission_coefficients 接线 + 校准器滑动窗口 + japan_monetary 合成（by Claude）

**修改者**：Claude Code  
**修改理由**：WorkBuddy 审计（Q1/Q2/Q5）发现三个结构性缺陷：传导矩阵定义了但代码从未消费；校准器无跨步上下文导致 LLM 调参反复横跳；japan_monetary 维度采集了但未进入 global_composite 合成。

### 修改

- **`core/agents/base.py`**：`MacroAgent` 新增 `transmission_coefficients: dict` 字段，`load_agents()` 加载时从 yaml 读取，不再静默丢弃
- **`core/simulation.py`**：
  - `load_agents()` 返回签名改为 `tuple[dict, dict]`（agents, global_cfg），透传 yaml global 段
  - `gm_resolve_rules()` 增加第二轮传导循环：主 Agent 触发 delta 后按 `transmission_coefficients × transmission_attenuation × tgt_magnitude` 扩散给下游 Agent
  - `MacroSimModel.__init__()` 适配新签名，将 `global_cfg` 存为实例属性传给 GM 规则层
- **`config/agents.yaml`**：顶部新增 `global.transmission_attenuation: 0.5`（传导衰减系数，可配置）
- **`core/calibrator.py`**：
  - import 补 `from collections import deque`
  - `_call_llm_for_adjustment()` 新增 `error_history` 参数（最近5步误差序列），prompt 中加入方向信息和 overshoot 识别规则
  - 主循环新增 `error_history: deque(maxlen=5)`，每步记录 `{step, error, grv_delta, credit_delta}` 并传入 LLM
  - `load_agents()` 调用处适配新返回签名（解包两值）
- **`core/bifurcation.py`**：`load_agents()` 调用处适配新返回签名

### 关联 question 文档

- Q1: `docs/questions/world-deduction/20260714-world-deduction-calibrator-stepwise-llm-bias.md`
- Q2: `docs/questions/world-deduction/20260714-world-deduction-transmission-coefficients-unused.md`

---



**修改者**：Claude Code  
**修改理由**：报告路径详情只有聚合终态和离散事件列表，读者看不出"第几个月发生了什么、为什么发生"，缺乏时间感和因果感。

### 修改

- **`core/bifurcation.py`**：`PathResult` 新增 `monthly_grv` 和 `monthly_sentiment` 两个字段（`list[float]`）；`run_prediction()` 中已计算的 `grv_vals_path` 和新计算的 `sent_vals_path` 存入 PathResult
- **`run.py`**：`_write_report()` 新增"三、月度演化进度条"节，每步显示 GRV 变化方向箭头 + 情绪值 + 当月关键事件 + 触发原因；自动计算分叉点并标注；原"三、校准说明"顺移为"四"

---



**修改者**：Claude Code  
**修改理由**：健康检查发现 AGENTS.md 第167行"新 session 快速继续"节写"看 CHANGELOG.md 最新条目"，与第52行阅读路径表格"前 50 行"描述不一致，存在歧义。

### 修改

- **`AGENTS.md` 第167行**：将"新 session 快速继续"节代码块改为 `读 CHANGELOG.md 前 50 行`（与阅读路径表格保持一致），同时调整步骤顺序为先读 CHANGELOG 再按需读 design_v2.md

---

## 2026-07-11 [2.0.3] 联动矩阵缺口修复（by Claude）

**修改者**：Claude Code  
**修改理由**：入口文档走查发现 macro-sim 联动矩阵缺少两条规则，导致版本变更时 `macro-sim_人类说明文档.md` 和 `世界推演系统_总览.md` 无强制更新链。

### 修改

- **`macro-sim_人类说明文档.md`**：头部版本号 `v2.0.2` → `v2.0.3`（漏更新修正）
- **`AGENTS.md` 联动矩阵**：新增两条——版本变更时 → `macro-sim_人类说明文档.md` 文件头版本号；版本变更时 → `S:\world-sim\世界推演系统_总览.md` 头部版本行 + 架构图版本号

---

## 2026-07-09 [2.0.3-hotfix] 叙事格式改进（by Claude）

**修改者**：Claude Code  
**修改理由**：路径详情看不出"为什么做空""之后怎么了""整体是什么情景"。

### 修改

- **`core/bifurcation.py`**：`_generate_narrative()` prompt 重写
  - 每个关键事件附带触发原因（例："对冲基金做空——因为GRV=80超过高压阈值"）
  - 要求LLM按三段结构输出：【情景定性】【核心传导链】【对你的影响】
  - prompt 不再使用复杂 f-string 嵌套（修复行截断 SyntaxError）
- **`run.py`**：叙事解析用 `re.split` 按【标签】分段显示，清理 LLM 多余数字前缀

---



## 2026-07-09 [2.0.2] 报告格式完整重写（by Claude）

**修改者**：Claude Code  
**修改理由**：报告结论埋在最后，数字无参照，路径间无对比，传导链因果不清楚。

### 修改

- **`run.py`**：完整重写 `_write_report()`
  - 结构调整为：核心结论（含路径对比表）→ 路径详情 → 校准说明（放最后）
  - 对比表：GRV 终值含方向箭头（↑↓→）和定性标签（高压区/中等/低压），情绪含语义标签（深度压力/温和压力/基本中性/乐观），信用利差含方向箭头
  - 传导链：`↳` 缩进表示因果触发，旁注触发来源
  - 关键驱动去重（之前重复显示同一事件）
  - 路径起点 GRV 用该路径真实起点（扰动后），不再用全局 world.grv
- **`core/bifurcation.py`**：PathResult 加 `initial_grv_mean` 字段，记录各路径真实起点 GRV；action_labels 补全所有 Action 的中文翻译

---

## 2026-07-09 [2.0.1] 单位换算修复 + 路径分叉调参（by Claude）

**修改者**：Claude Code  
**修改理由**：FRED T10Y2Y/BAA10Y 数据单位是 %，代码直接当 bp 用，导致报告显示 t10y2y=0.3bp/credit_spread=2bp；同时 Agent 规则参数按日度设计在月度时间步长下过强，情绪6步触底，路径无差异。

### Bug 修复

- **`core/world_state.py`**：
  - `load_from_macro_scan()`：T10Y2Y 和 BAA10Y 读取后 ×100 转 bps
  - `load_monthly_history()`：月度历史数据同样 ×100 转 bps
  - `apply_natural_decay()`：market_sentiment 衰减从 0.97/步改为 0.995/步（月度步长）
  - `BLEED_PARAMS.grv_bleed_rate`：从 3.0 降到 0.5，去掉 GRV 上限截断

### 路径分叉调参

- **`core/simulation.py`**：`_apply_delta()` 加 `MONTHLY_SCALE=0.12`，所有 market_sentiment delta × 0.12（月度折减）
- **`core/agents/financial.py`**：HedgeFundAgent 止动阈值从 -0.8 改为 -0.4（充分做空后不追空）
- **`core/agents/social.py`**：MediaAgent 情绪低于 -0.5 时停止 AMPLIFY_FEAR（避免单向压底）
- **`core/bifurcation.py`**：
  - 路径分叉用 sentiment 聚类（比 GRV 更能区分方向）
  - `MIN_PATH_PROBABILITY`：0.10 → 0.05
  - 预测步数：50 → 24（2年）
  - 关键事件过滤掉 HOLD
  - 外生变量初始扰动：GRV ±8点、t10y2y ±15bp、credit_spread ±15bp
- **`run.py`**：报告标题更新为"预测24个月"

---


## 2026-07-09 [2.0.0] 完整重设计：校准+预测双循环，12 Agent，路径树输出（by Claude）

**修改者**：Claude Code  
**修改理由**：v1.x 仿真结果毫无意义（std=0，情绪全为0或全-0.76，100次结果完全相同），根本原因是设计跑偏——把精力花在管道建设上，核心 ABM 的演化机制从未真正实现。v2 回归正轨。

### 核心设计变化

**时间步长**：每步 = 1个月（GRV 历史数据月度可用，日度只有8天）  
**运行方式**：前50步拟合历史（≈4年），后50步预测未来（≈4年）  
**输出**：概率路径树（最多3条主路径，低于10%的不展开）

### 新增文件

- **`core/agents/base.py`**：MacroAgent 基类 + AgentParams（sensitivity/threshold/magnitude 三参数接口）
- **`core/agents/financial.py`**：A1美联储/A2商业银行/A3对冲基金/A5机构/A9美财政部/A11欧央行/A12日央行
- **`core/agents/geopolitical.py`**：A4能源国/A7新兴市场央行/A8中国央行财政
- **`core/agents/social.py`**：A6媒体/A10散户羊群
- **`config/agents.yaml`**：12个Agent配置（热更新，新增角色无需改代码）
- **`core/calibrator.py`**：前50步校准循环（逐月对比真实数据，误差>0.15触发GLM自动调参）
- **`core/bifurcation.py`**：路径分叉检测 + Monte Carlo × 100 + 每条路径叙事

### 重写文件

- **`core/world_state.py`**：新增内生变量（retail_panic/china_credit_impulse/us_fiscal_pressure/yen_carry_risk），月度历史数据加载接口
- **`core/simulation.py`**：action_history 队列实现延迟可见，12 Agent GM 规则，从 agents.yaml 动态加载
- **`run.py`**：新入口（--daemon/--run/--predict-only），完整报告格式含路径树
- **`Dockerfile`**：加 config/ + VERSION COPY，pyyaml 依赖

### 关键修复

- **Agent 互相可见**：每个 Agent 按 info_delay 看到历史行动，不再是各自盲目读世界状态
- **随机性有意义**：初始内生变量加高斯扰动，100次 Monte Carlo 会产生真正不同的路径
- **时间刻度正确**：每步=1个月，100步≈8年（50校准+50预测），与 GRV 月度数据对齐

---



## 2026-07-09 [0.5.1] 规则 Agent 纳入绝对压力信号（by Claude）

**修改者**：Claude Code  
**修改理由**：规则版 Agent 触发条件只看相对 delta，导致 GRV=80 的高压环境下 7 个 Agent 全 HOLD，情绪永远是 0，仿真结果毫无参考价值。

### 根因

`get_agent_context()` 输出的 `external_pressure_shift = (vix_shift + grv_shift) / 2`，其中 vix_baseline 和 vix 均由同一个 GRV 公式估算，所以 vix_shift ≈ 0；grv_shift = (grv - grv_baseline) / 100，baseline 是历史均值，GRV=80 时 delta 也很小。触发阈值 `ext > 0.15` 在正常运行时几乎永远达不到。

### 修改

- **`core/world_state.py:get_agent_context()`**：
  - 新增 `grv_stress`：`max(0, (grv - 50) / 50)`，GRV=80 时输出 0.6
  - 新增 `vix_stress`：`max(0, (vix - 18) / 30)`，VIX=27 时输出 0.3
  - 新增 `yield_inverted`：t10y2y < -20bp 时为 1
  - `energy_tension` 纳入 `grv_energy / 100` 绝对分量

- **`core/simulation.py`**：7 个 Agent 的 `_decide_rules()` 全部加上绝对压力判断：
  - HedgeFund：`grv_stress > 0.4` 或 `vix_stress > 0.3` → SHORT_MARKET
  - CommercialBank：`grv_stress > 0.5` 或 `vix_stress > 0.4` → TIGHTEN_CREDIT
  - Media：`grv_stress > 0.5` 或 `vix_stress > 0.4` → AMPLIFY_FEAR
  - Fed：`vix_stress > 0.5` → CUT_50BP；`grv_stress > 0.4 且情绪尚可` → VERBAL_INTERVENTION
  - EnergyGov：`grv_stress > 0.6` → CUT_SUPPLY
  - Institution：`grv_stress > 0.4` 或 `yield_inverted` → DECREASE_RISK
  - EMCentralBank：`grv_stress > 0.5 且 vix_stress > 0.3` → RAISE_RATES

- **`run.py`**：`<think>` 标签过滤（MiniMax-M3 推理模型输出处理）

---

## 2026-07-09 [0.5.0] 报告生成 + daemon 守护模式 + P4-B 自动触发（by Claude）

**修改者**：Claude Code  
**修改理由**：仿真结果不可读，容器跑完即退出导致无限重启；补全 P4-B 自动触发。

### 修改

- **`run.py`**：
  - 新增 `_write_report()`：仿真完成后生成 Markdown 报告，写入挂载的 `/app/reports/`（即 macro-scan `docs/仿真报告/`），文件名格式 `YYYY-MM-DD_HH-MM_仿真_L{level}.md`
  - 报告内容：核心结论 / 仿真参数 / 结果表格 / 传导路径解读 / 预测记录，格式与 macro-scan 分析报告保持一致
  - `_send_ntfy()` 加 `report_path` 参数，ntfy 消息末尾追加报告文件名
  - 新增 `--daemon` 模式：容器常驻，每分钟轮询 `/app/sim_trigger.json`，检测到触发文件后自动运行仿真、删除触发文件、继续等待；执行失败时推送 ntfy 告警
  - `_read_version()`：从 VERSION 文件读取版本号，写入报告尾部

- **`docker-compose.yml`**：
  - 启动命令从 `--live --mc --runs 100`（单次跑完即退）改为 `--daemon`（常驻守护）
  - 新增环境变量 `REPORT_DIR=/app/reports`
  - 新增 volume：`macro-scan/docs/仿真报告` → `/app/reports`（报告输出目录）
  - 新增 volume：`macro-scan/data/sim_trigger.json` → `/app/sim_trigger.json`（触发文件，读写权限）

- **`VERSION`**：v0.4.1 → v0.5.0

### 工作流（完整闭环）

```
macro-scan 检测 GRV 告警 / 信号共振
    → 写 /workspace/data/sim_trigger.json
    → macro-sim daemon 检测到（最多1分钟延迟）
    → 读取 grv_latest.json / news_export.json
    → 运行 Monte Carlo × 100
    → 写 docs/仿真报告/YYYY-MM-DD_HH-MM_仿真_L{level}.md
    → 推送 ntfy（含结论摘要 + 报告文件名）
    → 写 sim_log.db
    → 删除 sim_trigger.json，继续等待
```

### 部署注意
- 首次部署前 NAS 上须执行：
  ```bash
  touch /vol2/1000/software/macro-scan/data/sim_trigger.json
  mkdir -p /vol2/1000/software/macro-scan/docs/仿真报告
  touch /vol2/1000/software/macro-sim/sim_log.db
  ```
- `sim_trigger.json` 必须预先存在（空文件），否则 Docker 单文件挂载会将其创建为目录

---

## 2026-07-09 [0.4.2] 接口版本校验 + make_test_world() 修复（by Claude）

**修改者**：Claude Code  
**修改理由**：与 macro-scan 建立双向接口版本保护机制；修复 world_state.py 中悬空代码 bug。

### 修改

- **`core/world_state.py`**：
  - 新增常量 `_GRV_SCHEMA_VERSION = "1.0"` 和 `_NEWS_SCHEMA_VERSION = "1.0"`
  - `load_from_macro_scan()` 读取 `grv_latest.json` 后校验 `_schema_version`，不一致则 `RuntimeError` 拒绝启动
  - `load_from_macro_scan()` 读取 `news_export.json` 后同样校验版本；`RuntimeError` 显式 re-raise，不被 fallback 的 `except Exception` 吞掉
  - 修复：`load_from_snapshot()` 结束后有一段孤立的模块级悬空代码（`make_test_world()` 函数体缺少 `def` 声明行），现已补全 `def make_test_world(label, sentiment_init)` 函数定义，代码结构恢复正确

- **`AGENTS.md`：接口契约节**：
  - 新增「接口变更三步走」、「版本兼容表」、「版本校验行为」说明
  - `grv_latest.json` 和 `news_export.json` 字段表各加 `_schema_version` 行

### 接口版本兼容

| macro-scan | macro-sim | 接口 schema |
|:-----------|:----------|:------------|
| v3.5.41+   | v0.4.2+   | grv v1.0 / news v1.0（含 japan_monetary 字段）|

### 部署注意
- 升级顺序：先 macro-scan（输出带版本字段）→ 再 macro-sim（启用校验）
- 若只升 macro-sim 而 macro-scan 仍是旧版，`--live` 模式会因 `_schema_version` 字段缺失立即报错
