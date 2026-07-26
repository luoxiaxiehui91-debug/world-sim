# Changelog

本文档遵循 [Keep a Changelog](https://keepachangelog.com/) 规范。  
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。


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
