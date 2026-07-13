# Changelog

本文档遵循 [Keep a Changelog](https://keepachangelog.com/) 规范。  
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。


## 2026-07-13 [2.0.4] 文档修正：新 session 阅读路径统一（by Claude）

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
