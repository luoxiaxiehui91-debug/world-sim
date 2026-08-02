# 增量 PRD：接入 BDI 与 FAO 数据源（macro-scan 观测层扩展）

| 项 | 内容 |
|----|------|
| 文档类型 | 增量 PRD（仅描述变更部分，不重写既有 PRD） |
| 日期 | 2026-07-28 |
| 作者角色 | 产品经理（software-product-manager） |
| 当前基线 | VERSION 3.5.65，fetcher_base 适配层收口完成 |
| 目标版本 | 3.6.0（建议，待架构师确认） |
| 关联规划 | `docs/archive/IMPROVEMENT_PLAN.md` §1E（已确认 CNH/铜/TGA 实测已接入，本次只差 BDI、FAO） |

## 0. 变更范围与基线（事实锚点，非臆测）

- **基线能力（v3.5.65）**：`核心代码/fetcher_base.py` 的 `FetcherBase` 提供 `Status` 枚举、`_SCHEMA_VERSION`、`feeds_grv`/`schedule`/`output_file` 类属性、`_is_good()` 默认谓词（ok-only）、`load_previous_good()`、`load_config_with_fallback()`、`save_json`（自动注入 `_schema_version` 与 `updated`，缺 `status` 兜底 `unavailable`）。新 fetcher 必须继承 `FetcherBase` 复用样板，不得再写重复的 `ImportError` 块与 `_load_previous_good`。
- **本 PRD 范围**：仅描述新增 BDI、FAO 两数据源的接入变更。
- **已落地事实（实测）**：`核心代码/fetch_fred_history.py` 的 `SERIES` 列表第 81–85 行已含 `DEXCHUS`(CNH)、`PCOPPUSDM`(铜)、`WDTGAL`(TGA)；Phase 2 还已通过 FRED 接入小麦 `PWHEAMTUSDM`、玉米 `PMAIZMTUSDM` 作为粮食价格代理。故本次 **仅差 BDI 与 FAO**。
- **影响文件（工程实现时）**：新增 `核心代码/fetch_bdi.py`、`核心代码/fetch_fao.py`；修改 `核心代码/scheduler.py` 与 `crontab`（追加调度行）。

## 1. 本次产品目标

补齐天枢在全球贸易实物流量（BDI）与粮食价格（FAO）两条传导链上的观测缺口；其中 FAO 官方食品价格指数（总指数 + 分项）是对既有 FRED 小麦/玉米单一商品代理的权威补充，覆盖 cereals/oils/sugar/meat/dairy 全分项。

## 2. 用户故事（天枢视角）

- 作为世界推演观测层，我希望持续获取 BDI 与 FAO 两个信号，以便在 GRV/宏观叙事中纳入「贸易实物流量」与「粮食价格 → 社会稳定」两条领先/滞后传导。
- 作为世界推演观测层，我希望新源在拉取失败时安全降级、保留上次良值，以免影响每日观测管线的稳定性。
- 作为世界推演观测层，我希望新源复用既有的 `FetcherBase` 样板（状态枚举/契约版本/降级保留良值），避免每个源重复样板代码。

## 3. 需求池

### P0（Must have）
- BDI 数据源接入并落盘。
- FAO 数据源接入并落盘。

### P1（Should have）
- 调度接入：FAO 月度（每月 1 日）；BDI 日频（随新 `fetch_bdi.py` 自有调度槽，错峰在 `grv_update` 06:10 之后或与日频 fetcher 同段）。
- 新 fetcher 必须继承 `FetcherBase`，复用 `load_config_with_fallback`（不得再写重复的 `ImportError` 块）、`save_json`（自动注入 `_schema_version` + `updated`）、`load_previous_good`。

### P2（Nice to have / 决策点）
- 确认 `geo_risk_vector` 是否消费这两源以增强 GRV（`feeds_grv` 判定）；若消费，需要独立的 GRV 维度扩展工作（见 §4 Q3），不在本 PRD 实现范围。

## 4. 待确认问题（需架构师/工程拍板，未自行下结论）

### Q1. BDI 落点：并入 `fetch_fred_history.py` 还是独立 `fetch_bdi.py`？
- **事实**：`fetch_fred_history.py` 当前走 `fredapi` + **CSV 输出**（`data/fred_history/{id}.csv`，格式 `date,value`），**不继承 `FetcherBase`**，无 `save_json`/`_schema_version`/`load_previous_good` 机制；而本 PRD 验收要求「符合 `fetcher_base` 规范的 JSON（含 `_schema_version` 与 `status`）」。
- **建议（基于三原则）**：独立新建 `fetch_bdi.py` 继承 `FetcherBase`。理由：
  1. **复用 fetcher_base 样板**：并入 `fetch_fred_history.py` 要么让 BDI 沿用 CSV（直接违背验收 JSON 契约），要么在该文件里混入 `FetcherBase` 调用（破坏单一职责）；独立模块一行样板都不写。
  2. **落盘格式统一**：v3.5.65 之后所有新增 fetcher（earthquake/energy/crypto_extra/news/hdx）均输出 `data/*.json` 含 `_schema_version`+`status`；`fetch_fred_history.py` 的 CSV 是遗留旧范式。BDI 归入 FetcherBase JSON 才「格式统一」。
  3. **调度清晰**：`fetch_fred_history.py` 是 05:30 批量刷 FRED 全量/增量；BDI 是 Stooq 外部源，频率与失败模式不同，独立模块可自有调度槽、互不拖累。
- **若架构师坚持并入 `fetch_fred_history.py`**：则必须明确放宽验收标准（BDI 走 CSV，并另行约定下游消费方式）——请拍板。

### Q2. FAO 开放 API 的端点、字段、鉴权与限流（工程前必须实测确认）
- FAO 食品价格指数（FSI）的具体 REST 端点（已知在 `api.fao.org` / `faostat.fao.org` 体系内，但确切路径需实测）。
- 返回结构：总指数 + 分项（meat / dairy / cereals / vegetable oils / sugar，部分含 fisheries），需确认字段名与单位（指数基期 2014–2016=100）。
- 是否需要 API key / 限流阈值（FAO 部分 API 免 key，部分数据集需注册）。
- 月度数据发布时点（通常每月上旬发布上月值），影响调度时刻是否合理。

### Q3. BDI / FAO 是否进 GRV（`feeds_grv`）？
- **事实**：`geo_risk_vector.py` 当前 **不读取 `feeds_grv` 属性**，而是对每个源**硬编码 loader + 维度字段**（如 `climate_risk`/`disaster_risk`/`sanctions_risk`/`seismic_risk`/`energy_grid_risk`）；仅把 fetcher 设 `feeds_grv=True` 不会自动进 GRV。要让 BDI/FAO 进 GRV，需在 `geo_risk_vector.py` 新增（a）读对应 JSON + `status` 判定的 loader 块、（b）新维度字段（如 `trade_flow_risk` / `food_price_risk`）、（c）重新校准权重与 `_blend`——属 GRV 模型变更，超出本 PRD 范围。
- **建议**：本次默认 `feeds_grv=False`，两源先作为历史观测序列落盘，供下游 `macro-sim` / `scan_weak_signals` / 叙事消费；待 1–2 个月确认噪声与可用性后，再单独开「GRV 维度扩展」PRD。理由：BDI=贸易实物流量领先指标、FAO=粮食价格→社会稳定滞后传导，与现有 GRV「地缘冲突压力」语义属不同维度，盲目并入会稀释现有向量含义。
- 最终是否 `feeds_grv=True` 由架构师拍板；若为真，请同步评估 GRV 权重再校准的工作量归属。

### Q4. 落盘文件名与字段命名约定（遵循现有 `fetch_*.py` 风格 + `_schema_version`）
- **现有约定（实测）**：喂 GRV 的 fetcher 输出 `data/<name>_risk.json`（energy_risk.json / earthquake_risk.json / sanctions_risk.json）；不喂 GRV 的输出 `data/<name>_signals.json`（climate_signals.json / disaster_signals.json）。顶层必有 `status`，`save_json` 自动注入 `_schema_version` 与 `updated`。
- **建议（因 Q3 建议 `feeds_grv=False`）**：BDI 用 `data/bdi.json`、FAO 用 `data/fao_food_price.json`（或 `fao.json`）——以 `_risk` 之外的命名明确示意为「原始观测序列」而非「已归为 0–100 的风险分」。
- 字段建议（参考 `fetch_energy.py` 输出结构）：
  - BDI：`status` + 主信号 `bdi_index`（最新值）+ `series`（近期 date/value 数组或最新 N 点）+ `source`。
  - FAO：`status` + `fao_food_price_index`（总指数）+ `sub_indices`（分项 dict）+ `source`。
- 类名：`BdiFetcher(FetcherBase)` / `FaoFetcher(FetcherBase)`，`name="bdi"/"fao"`，`schedule="HHMM"` 字符串。
- 最终命名由工程拍板，但须保持与现有 `data/*.json` + `_schema_version` + `status` 契约一致。

### 补充发现（调度碰撞，需协调）
- `scheduler.py` 第 58 行已存在 **每月 1 日 09:10** 的 `fetch_climate_signals.py` 月度任务。IMPROVEMENT_PLAN 规划的 FAO 09:10 槽与之**碰撞**。
- 建议：FAO 挪到下一个空档（现有月任务占 0900/0905/0910/0915/0920，可放 **09:25**），遵循项目「错峰/不碰撞」约定。若坚持 09:10 与 climate 并发：调度器后台非阻塞可并发，但需确认日志与下游读取无竞争。请架构师定夺时刻。

## 5. 验收标准

1. **落盘合规**：两源数据可成功拉取并落盘为符合 `FetcherBase` 规范的 JSON——顶层必含 `status` 与 `_schema_version`（由 `save_json` 注入），字段命名遵循 §4 Q4 约定。
2. **调度如期触发**：BDI 按日频自有槽触发；FAO 在每月 1 日（建议 09:25，以 §4 补充发现拍板为准）触发；不与其他月任务碰撞。
3. **失败降级**：`collect` 异常 / 请求最终失败 → 返回 `None`/空，不抛、不阻断调度；本地有上次良值则 `load_previous_good` 保留、不覆盖；无良值则写 `status=unavailable` 标记（`save_json` 兜底）。
4. **样板复用**：新 fetcher 继承 `FetcherBase`，复用 `load_config_with_fallback`（无重复 `ImportError` 块）、`save_json`、`load_previous_good`。
5. **变更隔离**：仅新增 `fetch_bdi.py` / `fetch_fao.py` 与 `scheduler.py`/`crontab` 调度行，不改动既有 fetcher 逻辑（BDI 不污染 `fetch_fred_history.py` 的 FRED 批拉）。
