# 增量 PRD：接入 Yahoo 商品期货 / OpenSky 航空 / AkShare 中国中观（macro-scan 观测层扩展）

| 项 | 内容 |
|----|------|
| 文档类型 | 增量 PRD（简单 PRD，仅描述变更部分，不做完整竞品分析） |
| 日期 | 2026-07-28 |
| 作者角色 | 产品经理「许清楚」（software-product-manager） |
| 当前基线 | VERSION 3.5.65，fetcher_base 适配层收口完成（Status 枚举 / `_SCHEMA_VERSION="1.0"` / `feeds_grv` `schedule` `output_file` 类属性 / `save_json` 自动注入 `_schema_version`+`updated`+`status` 兜底 / `load_previous_good` 降级保留良值） |
| 目标版本 | 3.6.x（建议，待架构师确认） |
| 关联 | 延续 `PRD_bdi_fao_2026-07-28.md` 的「先落盘交叉验证、再决定是否进 GRV」决策 |

## 0. 变更范围与基线（事实锚点，非臆测）

- **本次新增三源**（均为主理人探针在本环境实测可达、免费）：
  1. **Yahoo Finance 商品期货公开 API**（`query1.finance.yahoo.com/v8/finance/chart`，沙箱实测 HTTP 200+JSON）：WTI `CL=F`(~79.47)、Brent `BZ=F`(~84.58)、铜 `HG=F`(~6.35，单位美元/磅)。注意铝 `AH=F` 在该端点 **404**（无标准符号）。
  2. **OpenSky Network 航班实时位置 API**（`/api/states/all`，匿名免费限 400 次/天，沙箱实测返回 states 数组 226 条）。
  3. **AkShare 中国中观数据**（免费开源库，容器内 `fetch_china_data.py` 已在用；沙箱无 akshare，具体函数名由工程阶段确认）。
- **范围**：仅描述三源接入并落盘为观测层交叉验证（默认 `feeds_grv=False`），不改动既有 16 源逻辑。
- **影响文件（工程实现时）**：新增 `核心代码/fetch_yahoo.py`、`fetch_opensky.py`、`fetch_china_meso.py`；修改 `核心代码/scheduler.py`（追加 JOBS + LOG_FILES）。
- **命名约定（建议）**：`fetch_{源}.py` → 输出 `data/{源}.json`，建议 `commodity_yahoo.json` / `airtraffic_opensky.json` / `china_meso.json`（以非 `_risk` 命名明确示意为「原始观测序列」而非「0–100 风险分」）。

## 1. 产品目标

为天枢宏观扫描观测层补三类**独立、免费、可达**的交叉验证信号，提升现有观测的鲁棒性与覆盖：

1. **商品期货价格三角验证（Yahoo）**：与既有 `fetch_energy`（电网碳强度/能源冲击）、FRED 铜(`PCOPPUSDM`)、BDI（贸易实物流量）形成「实物商品—能源—贸易实物流」交叉校验。Yahoo 提供更高频、更直接的市场报价（WTI/Brent/Copper），可作为 FRED/BDI 的价格冗余源，在单一源异常/缺失时仍能校正油价叙事。
2. **航空活动密度代理（OpenSky）**：现有 16 源**无航空维度**。日频聚合「在飞航班数 / 平均高度 / 主要起飞机场国 Top5」作为**实体经济活动与地缘流动代理**——空域关闭、制裁绕飞、重大事件对实体流动的影响，可由此直接观测。
3. **中国中观景气（AkShare）**：弥补天枢对「中国中观颗粒度」的缺口。既有 `fetch_china_data.py` 走 FRED/WB/AkShare yearly 宏观（PMI/PPI/工业增加值/LPR）；本源聚焦更细的中观指标（二手房价格指数、行业景气度），为中国情景推演提供更细颗粒度数据。

**交叉验证价值**：三源默认不喂 GRV，作为「冗余/交叉验证层」落盘。延续 BDI/FAO PRD 决策——先落盘 1–2 月观察噪声与可用性，再单独评估是否部分信号进 GRV。

## 2. 用户故事（天枢视角）

- 作为世界推演观测层，我希望接入 Yahoo 商品、OpenSky 航空、AkShare 中观三源并落盘，以便对现有能源/贸易/中国宏观观测形成交叉验证与冗余。
- 作为观测层，我希望三源遵循 `FetcherBase` 契约（`status`/`_schema_version`/降级保留良值），拉取失败时安全降级、保留上次良值，不影响每日观测管线稳定性。
- 作为下游 `macro-sim` / `scan_weak_signals` / 叙事消费方，我希望三源以统一 JSON 契约落盘（`data/*.json` + `status`），便于非阻断读取与跨源比对。
- （可选，未来）作为情景推演分析师，我希望在观察噪声后，可选择性将部分信号（如油价、航空密度）喂入 GRV 以捕捉「能源冲击 / 实体流动中断」维度——但需先观察、单独开 PRD。

## 3. 需求池

### P0（Must have）
- 三源接入并落盘：`commodity_yahoo.json` / `airtraffic_opensky.json` / `china_meso.json`，均继承 `FetcherBase`，`feeds_grv=False`。
- **Yahoo**：拉取 `CL=F`(WTI) / `BZ=F`(Brent) / `HG=F`(Copper) 实时价并落盘；铝 `AH=F` 404 须优雅标为 unavailable、不阻断其余。
- **OpenSky**：日频聚合「在飞航班数 / 平均高度 / 主要起飞机场国 Top5」并落盘。
- **AkShare 中观**：至少落盘「二手房价格指数」+「行业景气度」（具体 AkShare 函数名工程确认）；环境须可达（容器内已用 akshare）。

### P1（Should have）
- **字段完整性**：每源输出含 `status` + `source` + `as_of` + 数据主体 + 子源级 `status`；缺 `status` 时由 `save_json` 兜底 `unavailable`。
- **异常处理**：单 symbol/单子源失败不阻断整体（Yahoo 某合约 404→该 symbol 标 `unavailable`，其余正常；AkShare 某函数列名变更→该 indicator 标 `ERROR` 不覆盖历史）；OpenSky 限流/超时→保留良值。
- **降级保留良值**：`_is_good` 默认 ok-only 生效（若需 ok/partial 再覆写）。
- **调度接入**：`scheduler.py` + `LOG_FILES` 追加三源调度行（时刻见 §5）。

### P2（Nice to have / 决策点）
- **铝 LME 代理**：`AH=F` 在 Yahoo 404，铝改走 AkShare LME 代理（如 `macro_lme_*`）补缺口（属本源或 china_meso 扩展，待定）。
- **原油期限结构近远月价差**：远月合约符号表（如 `CLZ26`）拉取，算近远月价差（contango/back）。
- **AkShare 中观扩面**：更多行业景气、区域房价指数。
- **GRV 维度扩展**：观察 1–2 月后评估是否部分信号进 GRV（独立 PRD，超出本范围）。

## 4. 各源数据结构稿（输出 JSON 字段定义）

> 约定：`_schema_version`（="1.0"）与 `updated`（ISO 时间戳）由 `save_json` 自动注入；`status` 由 `collect` 设置、缺失兜底 `unavailable`。以下 `as_of` 为数据本身时间（非落盘时间），来自源返回时间戳。

### 4.1 Yahoo 商品期货 → `data/commodity_yahoo.json`

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `status` | str | `ok`/`partial`/`unavailable`（部分 symbol 失败时 `partial`） | `ok` |
| `source` | str | 数据来源端点 | `Yahoo Finance v8 chart API` |
| `as_of` | str | 报价时间（meta.regularMarketTime，ISO） | `2026-07-28T14:30:00Z` |
| `commodities` | obj | 以逻辑名(键)索引的各商品对象 | — |
| `commodities.{wti,brent,copper}` | obj | 每个含 `symbol`/`name`/`unit`/`price`/`as_of`/`status` | — |
| `commodities.*.symbol` | str | Yahoo 符号 | `CL=F` |
| `commodities.*.name` | str | 中文名 | `WTI原油` |
| `commodities.*.unit` | str | 计价单位 | `USD/bbl`、`USD/lb` |
| `commodities.*.price` | float | 最新价（regularMarketPrice） | `79.47` |
| `commodities.*.status` | str | 该 symbol 子状态 | `ok`/`unavailable` |
| `unavailable_symbols` | list | 拉取失败/404 的符号（如铝） | `["AH=F"]` |
| `notes` | str | 备注（如铝走 LME 代理） | — |

```json
{
  "status": "ok",
  "source": "Yahoo Finance v8 chart API (query1.finance.yahoo.com/v8/finance/chart)",
  "as_of": "2026-07-28T14:30:00Z",
  "commodities": {
    "wti":    { "symbol": "CL=F", "name": "WTI原油",  "unit": "USD/bbl", "price": 79.47, "as_of": "2026-07-28T14:30:00Z", "status": "ok" },
    "brent":  { "symbol": "BZ=F", "name": "Brent原油","unit": "USD/bbl", "price": 84.58, "as_of": "2026-07-28T14:30:00Z", "status": "ok" },
    "copper": { "symbol": "HG=F", "name": "铜",       "unit": "USD/lb",  "price": 6.35,  "as_of": "2026-07-28T14:30:00Z", "status": "ok" }
  },
  "unavailable_symbols": ["AH=F"],
  "notes": "铝 AH=F 在 Yahoo 返回 404，铝改走 AkShare LME 代理（见 china_meso P2）。"
}
```

### 4.2 OpenSky 航空活动 → `data/airtraffic_opensky.json`

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `status` | str | `ok`/`partial`/`unavailable` | `ok` |
| `source` | str | `OpenSky Network /api/states/all` | — |
| `as_of` | str | 查询时间（ISO） | — |
| `scope` | str | 范围：`global` 或 `bbox:lamin,lomin,lamax,lomax`（待确认 Q2） | `global` |
| `flights_in_air` | int | `on_ground=false` 的 state 数 | `180` |
| `avg_altitude_m` | float\|null | 在飞航班平均气压高度（排除 None/地面） | `10500.0` |
| `avg_velocity_ms` | float\|null | 在飞航班平均速度 | `220.5` |
| `top_origin_countries` | list | 起飞机场国 Top5：`[{country,count,pct}]` | `[{"country":"United States","count":40,"pct":17.5}]` |
| `total_states` | int | 原始返回 state 条数（探针 226） | `226` |
| `sample_limited` | bool | 是否触及匿名 400/天限额/采样 | `false` |

```json
{
  "status": "ok",
  "source": "OpenSky Network /api/states/all",
  "as_of": "2026-07-28T14:00:00Z",
  "scope": "global",
  "flights_in_air": 180,
  "avg_altitude_m": 10500.0,
  "avg_velocity_ms": 220.5,
  "top_origin_countries": [
    { "country": "United States", "count": 40, "pct": 17.5 },
    { "country": "China",         "count": 28, "pct": 12.3 }
  ],
  "total_states": 226,
  "sample_limited": false
}
```

### 4.3 AkShare 中国中观 → `data/china_meso.json`

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `status` | str | `ok`/`partial`/`unavailable` | `ok` |
| `source` | str | `AkShare (akshare==1.18.63, macro_china_*)` | — |
| `as_of` | str | 拉取时间（ISO） | — |
| `indicators` | obj | 以指标 id(键)索引 | — |
| `indicators.{id}` | obj | 含 `name`/`value`/`date`/`unit`/`ak_func`/`status` | — |
| `indicators.*.ak_func` | str | 实际调用的 AkShare 函数名（**工程确认**） | `macro_china_second_hand_house_price_index`(待定) |
| `indicators.*.value` | float\|null | 最新值 | `—` |
| `indicators.*.date` | str | 数据日期（YYYY-MM） | `2026-06` |
| `indicators.*.unit` | str | 单位 | `指数`/`%` |
| `indicators.*.status` | str | 该指标子状态（`ok`/`unavailable`/`error_col_change`） | `ok` |

**候选中观字段（PRD 仅定义「要哪些」，函数名工程确认）**：
- `second_hand_hpi` — 二手房价格指数（AkShare 函数名待容器内 python 验证）
- `industry_prosperity` — 行业景气度（同上）
- （可选复用现有 AkShare yearly：）`pmi_mfg` / `ppi_yoy` / `industrial_output`（已在 `fetch_china_data.py` 落 CSV；本源若需 JSON 统一契约可纳入）

```json
{
  "status": "ok",
  "source": "AkShare (akshare==1.18.63, macro_china_*)",
  "as_of": "2026-07-28T15:00:00Z",
  "indicators": {
    "second_hand_hpi":      { "name": "二手房价格指数", "ak_func": "TBD", "value": null, "date": "2026-06", "unit": "指数", "status": "unavailable" },
    "industry_prosperity":  { "name": "行业景气度",     "ak_func": "TBD", "value": null, "date": "2026-06", "unit": "—",    "status": "unavailable" }
  }
}
```
> 注：示例 `value:null` 仅表示函数名未确认前的占位；工程确认后填实值。

## 5. 调度频率建议

| 源 | 建议频率 | 建议时刻(hhmm) | 理由 / 错峰依据 |
|----|----------|----------------|------------------|
| Yahoo 商品 | 日频 | **0626** | 落盘不喂 GRV，但早于 `situation_detect`(0630) 与 `daily_narrative`(0700) 以便下游消费；错峰 `bdi`(0625)。3 符号×1 请求，Yahoo 限频安全。 |
| OpenSky 航空 | 日频 | **0628** | 日频 1 次 << 匿名 400/天限额；早于 0630 下游消费；错峰 `bdi`(0625)/`situation_detect`(0630)。 |
| AkShare 中观 | 月频（每月 1 日） | **0930**（dom=1） | 中观指标多按月发布；月频调用省 AkShare 额度。错峰 `fao`(0925) 月任务。部分高频指标可改**周频（周一）**，待工程确认后定。 |

- 同槽并发：scheduler 同 `hhmm` 多源 `subprocess.Popen` 非阻塞并发、各写独立 `<name>.log`，故 0626/0628 若需可并入相邻槽；但遵循项目「错峰/不碰撞」约定，仍给独立分钟。
- 以上时刻为建议值，最终以架构师拍板为准（见 §6 Q7）。

## 6. 待确认问题（需架构 / 工程拍板，未自行下结论）

### Q1. AkShare 具体接口名（工程须在容器内 python 验证）
- 二手房价格指数、行业景气度的**准确 AkShare 函数名**（`akshare` 列名易随版本变更，现有 `fetch_china_data.py` 已踩过 `cn_lpr` 列名变更坑）。
- 沙箱无 akshare，无法现验；PRD 仅定义「要哪些中观字段 + 输出契约」，函数名与列映射由工程在容器内确认并回填 `ak_func`。

### Q2. OpenSky 是否限定区域 bbox
- 全量 `/states/all`（探针 226 条）vs `bbox=lamin/lomin/lamax/lomax` 限定（如中国/欧亚）。
- 影响「主要起飞机场国 Top5」语义与调用预算；匿名 **400/天** 限额下日频 1 次均够，但 bbox 可进一步降噪/提速。需定 `scope` 取值。

### Q3. 三源是否喂 GRV（`feeds_grv`）
- **事实**：`geo_risk_vector.py` 当前不读 `feeds_grv` 属性，而是逐维硬编码 loader；仅设 `feeds_grv=True` **不会**自动进 GRV。要让信号进 GRV 需新增（a）reader 块、（b）维度字段、（c）权重再校准——属 GRV 模型变更，超出本 PRD。
- **建议**：本次默认 `feeds_grv=False`，三源先落盘交叉验证；观察 1–2 月噪声后单独开「GRV 维度扩展」PRD。最终是否改 `True` 由架构师拍板。

### Q4. 铝代理方案（`AH=F` 404）
- Yahoo 铝 `AH=F` 404 → 铝改走 **AkShare LME 代理**（如 `macro_lme_*`）。需确认具体函数、单位换算（LME 吨 vs Yahoo 磅），并决定归入 `china_meso`（P2）还是独立处理。

### Q5. 原油期限结构（P2）
- 远月合约符号表（如 `CLZ26`）是否拉取以算近远月价差（contango/back）。Yahoo chart 单端点只给即时价，远月需不同符号；需确认符号表与性价比。

### Q6. 落盘命名与契约一致性
- 建议 `commodity_yahoo.json` / `airtraffic_opensky.json` / `china_meso.json`（非 `_risk` 命名，明示「原始观测序列」）。
- 须确认三文件遵循现有 `data/*.json` + `_schema_version` + `status` 契约（`fetcher_base` v3.5.65+ 已强制），与既有 `energy_risk.json`/`bdi.json` 风格一致。

### Q7. 调度时刻碰撞确认
- 建议 0626(Yahoo)/0628(OpenSky)/0930(china_meso, dom=1) 与现有 06:xx 槽（bdi 0625、situation_detect 0630）及月任务（fao 0925）错峰。需架构确认最终时刻，避免与未来新增源挤占。

## 7. 验收标准

1. **落盘合规**：三源均继承 `FetcherBase`，输出符合契约的 JSON——顶层必含 `status`、`source`、`as_of`、数据主体；`_schema_version` 与 `updated` 由 `save_json` 注入；字段命名遵循 §4。
2. **调度如期触发**：Yahoo/OpenSky 日频自有槽触发；china_meso 在每月 1 日（建议 0930）触发；不与既有任务碰撞。
3. **失败降级**：任一 symbol/子源失败 → 该单元标 `unavailable`/`error`，整体不抛、不阻断；本地有上次良值则 `load_previous_good` 保留、不覆盖；无良值则写 `status=unavailable` 标记。
4. **样板复用**：三 fetcher 复用 `save_json` / `load_previous_good` / `load_config_with_fallback`，不重复 `ImportError` 回退块。
5. **变更隔离**：仅新增三个 `fetch_*.py` 与 `scheduler.py`/`crontab` 调度行，不改动既有 16 源逻辑。
6. **默认不喂 GRV**：三源 `feeds_grv=False`，不影响现有 GRV 向量语义（Q3）。
