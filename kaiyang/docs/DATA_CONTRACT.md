# 开阳 Wave 1 · 数据契约（DATA_CONTRACT）

> 世界推演系统「开阳」是**前端操作面板（展示 + 控制双职能）**，即整套推演系统的**人工操作台**：
> - **读侧**：只读契约文件（`grv_latest.json` / `news_export.json` / `fred_history/*` / `sim_trigger.json`），经 `DATA_BASE_URL` 加载，做可视化呈现。
> - **写侧（受控指令通道）**：代表人类 operator，经各后端**正规控制通道**向自家后端下发操作指令，由对应后端执行。控制范围覆盖全系统：
>   - **天璇推演层**：触发 macro-sim 推演、切换 / 加载推演场景、调参后提交推演、确认 / 驳回 `sim_trigger`；
>   - **天枢观测层**：重跑某个 fetcher、暂停 / 恢复采集源、调整采集频率等观测层运维操作；
>   - **天玑校验层 / 玉衡审批层**：提交校验任务、转交 / 接收审批结论等。
>   - 写侧**协议（端点 / 文件流向 / 鉴权 / 权限分级）**：现役 = 天枢 **HTTP REST 控制 API（:8900）**（见 [`A3a-控制API-开阳对接文档.md`](./A3a-控制API-开阳对接文档.md) §0）；文件投递协议未采纳。天璇 / 玉衡等后端闭环搭起后再定各自协议；**控制范围现已钉定**（见上），以防范围蔓延。
> - **隔离铁律（精确版）**：开阳**永不自行**调用任何第三方数据源 / 爬虫 / 外部 API 做采集（FRED、GDELT、RSS 等被明确排除）；但开阳**可以**向自家后端下发操作指令、由后端执行。二者性质不同——「不爬第三方数据源」≠「不能和自家后端通信」。
> - 开阳只「读契约 + 发指令」，绝不「自行实现业务逻辑 / 自行采集数据」。数据缺失一律降级渲染（占位 + 状态条告警）。
>
> 本文件是后续扩展（天璇 D.hypothesis / macro-sim D.sim / 天玑 D.verification）接入的**权威标准**。

---

## 0. 数据根（DATA_BASE_URL）

所有读取均基于可配置的数据根，默认 `./data/`（相对构建产物）。可通过以下方式覆盖：

| 方式 | 变量 / 字段 | 说明 |
| --- | --- | --- |
| 构建期环境变量 | `VITE_DATA_BASE_URL` | 如 `VITE_DATA_BASE_URL=/mnt/tianshu-data/ npm run build` |
| 运行时全局 | `window.__KAIYANG_DATA_BASE_URL__` | 部署时在 `index.html` 前置 `<script>` 注入，便于 NAS 只读挂载 |
| 默认 | `./data/` | 开发 / 通用静态托管 |

读取层会确保结尾带 `/`，再拼接待 `path`。

---

## 1. Feed 注册表

| feed 名 | 文件（相对 DATA_BASE_URL） | 类型 | schema_version | 说明 |
| --- | --- | --- | --- | --- |
| `grv` | `grv_latest.json` | json | `1.0` | GRV 风险状态（**天枢产出 16+1 维**=16 风险维度+`global_composite`；开阳 `grvDimensions.ts` 展示 **11 维子集**，缺 6 维不展示但保留在数据中） |
| `news` | `news_export.json` | json | `1.0` | 新闻 / 叙事导出 |
| `simTrigger` | `sim_trigger.json` | json | `1.0` | 推演触发状态（**可选**；亦为开阳写侧指令通道候选载体） |
| `fred` | `fred_history/manifest.json` | json | `1.0` | FRED 序列清单（再按 manifest 取各 CSV） |
| `nuclearSites` | `nuclear_sites.json` | json | `1.0` | 核设施站点与辐射读数（**可选**；缺失时回落前端静态种子，见 2.5） |
| `news_geo` | `news_geo.json` | json | `1.0` | GDELT 地理新闻事件（**已上线**，见 §2.7） |
| `market_quotes` | `market_quotes.json` | json | `1.0` | 底部行情报价（**已上线**，前端 60s 轮询） |
| `spacetrack` | `spacetrack.json` | json | `1.0` | 太空活动 / 空间目标（**已注册上线**） |
| `reports_index` | `reports_index.json` | json | `1.0` | 开阳报告索引（R-1，见 §2.8；天枢 `generate_reports_index.py` 产物） |
| `fci_latest` | `fci_latest.json` | json | `fci-1.1` | 金融条件指数 FCI（R-3，见 §2.9；`compute_fci.py` 产物） |
| `gscpi` | `fred_history/GSCPI.csv` | csv | `1.0` | 纽约联储全球供应链压力指数 GSCPI（R-3，月度 CSV；`fetch_gscpi.py` 产物） |
| `climate_signals` | `climate_signals.json` | json | `1.0` | 气候风险信号（R-4，见 §2.10） |
| `disaster_signals` | `disaster_signals.json` | json | `1.0` | 自然灾害风险信号（R-4，见 §2.10） |
| `earthquake_risk` | `earthquake_risk.json` | json | `1.0` | 地震风险信号（R-4，见 §2.10） |
| `energy_risk` | `energy_risk.json` | json | `1.0` | 能源 / 电网风险信号（R-4，见 §2.10） |
| `hdx_risk` | `hdx_risk.json` | json | `1.0` | 人道危机风险信号（R-4，见 §2.10） |
| `news_risk` | `news_risk.json` | json | `1.0` | 新闻风险信号（R-4，见 §2.10） |

> 新增 feed：仅在 `src/config/dataSources.ts` 的 `FEEDS` 登记一项，读取层（`useFeed` / `readLayer`）**无需改动**。

---

## 2. 字段定义

### 2.1 `grv_latest.json`（对象）
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | 当前 `1.0` |
| `updated` | string(ISO) | ✅ | 数据时间戳（状态条显示） |
| `gdelt_updated` | string(ISO) | ⬜ | GDELT 来源时间戳 |
| `source_quality` | string | ⬜ | 来源质量标签 |
| `*_risk` / 维度键 | number \| null | ⬜ | 各维度数值；`null` 表示缺失 |
| `global_composite` | number | ⬜ | 综合指数（0–100） |
| `events` | GrvEvent[] | ⬜ | **可选**。气候 / 灾害事件触发地图告警柱的数据源，平时可缺省（缺省 / 空数组时地图不画任何事件柱）。由上游事件 feed 提供 |

**GrvEvent**（`src/types/contracts.ts`）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | ✅ | 事件唯一 ID（如 `evt-tr-earthquake`） |
| `type` | `'climate'` \| `'disaster'` | ✅ | 事件类别：气候 / 自然灾害 |
| `label` | string | ✅ | 事件名称（地图标签 / tooltip 标题） |
| `lat` / `lng` | number | ✅ | 事件发生地坐标（告警柱画在此处） |
| `value` | number | ✅ | 事件严重度 0–100，决定柱高与配色 |
| `note` | string | ⬜ | 补充说明（如"7.8级地震 / 季风洪涝"） |

> 自 1.0.3 起，`climate_risk` / `disaster_risk` 两维度**不再画常驻地图柱**（`renderBar:false`，标量值仍在 GRV 面板展示），其地图呈现改由 `events[]` 事件触发式告警柱承担。

**开阳展示的 11 维子集内部锚点**（`src/config/grvDimensions.ts`，上游无坐标时使用）：
台海、南海、美中战略、中东能源、俄乌/东欧、朝鲜半岛、印太、全球综合、气候风险、自然灾害、全球南方。
（天枢实际产出 **16+1 维**，见 §2.6；开阳 `grvDimensions.ts` 只配置其中 11 维用于展示，其余 6 维——`sanctions_risk / seismic_risk / energy_grid_risk / japan_monetary / social_stress / cultural_friction`——存在于数据中但不在开阳默认展示集。）

> ⚠ **坐标偏差说明**：上游 `grv_latest.json` **含全部 16+1 维键，但无 lat/lng、无不确定区间字段**。开阳适配层（`src/lib/grvAdapter.ts`）会：
> - 缺失维度 → `status:'missing'`，地球点位显示灰色、GRV 面板显示「数据缺失」、状态条记录告警；
> - 不确定区间 → 按数值 8% 估算并标记 `uncertaintyEstimated:true`（后续上游提供该字段后自动采用真实值）。
> - 实测（08-06）：`/workspace/data/grv_latest.json` = 24 顶层键（17 业务维度 + `_schema_version/_derived_meta/updated/gdelt_updated/gpr_twn_raw/gpr_twn_date/source_quality`），`global_composite=60.3`。

### 2.2 `news_export.json`（对象，含数组）
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | `1.0` |
| `updated` | string | ⬜ | 导出时间 |
| `items` | NewsItem[] | ✅ | 新闻 / 叙事条目 |

**NewsItem（字段宽松，缺失即降级）**：`date, source, indicator, series_id, title, category, level, direction, alert_type, current, baseline, ratio, z_score, details, risk_note, trigger_titles[]`。

> ⚠ **Wave1 实际偏差**：上游实际文件名为 `latest_news.json`（纯数组）。本仓库快照已包装为 `{schema_version, updated, items}` 以统一契约；读取层兼容「纯数组」与「包装对象」两种形态。

### 2.3 `sim_trigger.json`（对象，**可选**）
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | `1.0` |
| `triggered` | boolean | ⬜ | 是否触发推演 |
| `level` | string | ⬜ | 触发等级 |
| `reason` | string | ⬜ | 触发原因 |
| `updated` | string | ⬜ | 时间戳 |

> 文件缺失不报错，状态条显示「推演未触发」。
>
> ⚠ **双角色说明**：`sim_trigger.json` 既作为开阳**读入**的推演状态（展示"是否已触发"），也是开阳**写侧**指令通道的候选载体（写入以触发 macro-sim 推演 / 切换场景）。写侧协议（端点 / 文件流向 / 鉴权）**暂缓设计**，待天璇 / 玉衡等后端闭环搭起后再定，沿用上方隔离铁律——开阳只发指令、绝不自连数据源。

### 2.4 `fred_history/manifest.json` + `*.csv`
| manifest 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | string | `1.0` |
| `updated` | string | 导出时间 |
| `series[]` | FredSeriesMeta[] | 序列清单 |

**FredSeriesMeta**：`id, label, unit?, file(相对 DATA_BASE_URL), color?, category?`。
**CSV 格式**：首行表头 `date,value`，其后每行一条观测；末列为数值列。

> 新增 FRED 序列：仅在 `manifest.json` 的 `series` 增加一项并放入对应 CSV，经济面板**无需改动**。

### 2.5 `nuclear_sites.json`（对象，**可选**，1.2.0 新增）

核设施图层（`category:'nuclear'`）与「核设施监视」面板的数据源。**整个文件可以不存在**：缺失时前端回落 `src/config/nuclearSites.ts` 的静态站点种子，读数全部显示「—」，地图上呈灰色虚线菱形。

| 顶层字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | 当前 `1.0` |
| `updated` | string(ISO) \| null | ⬜ | 本文件导出时间 |
| `sites` | NuclearSite[] | ⬜ | 站点清单。**非空时完全覆盖**前端种子；缺失 / 空数组 ⇒ 回落种子 |
| `readings` | NuclearWatchReading[] | ⬜ | 辐射读数。缺失 / 空数组 ⇒ 各站读数为 `null`（合法业务态，不告警） |

**NuclearSite**（`src/types/contracts.ts`）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | ✅ | 站点唯一 id（英文 kebab，如 `zaporizhzhia`）。地图点位 id 为 `nuclear:<id>` |
| `name` | string | ✅ | 中文站名（地图标签 / 表格首列） |
| `name_en` | string | ⬜ | 英文 / 原文名 |
| `country` | string | ✅ | 国家 / 地区中文名 |
| `lat` / `lng` | number | ✅ | 坐标，**小数 4 位**（≈11m）。非有限数或超出 ±90 / ±180 的记录会被整条丢弃，不会画到 (0,0) |
| `type` | `'npp'` \| `'monitor'` \| `'legacy'` | ⬜ | 核电站 / 监测站 / 事故遗址 |
| `note` | string | ⬜ | 补充说明 |

**NuclearWatchReading**（按 `site_id` 与 `sites[]` join；找不到对应站点的读数会被丢弃，**不凭空造站**）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `site_id` | string | ✅ | 关联 `NuclearSite.id` |
| `reading` | number \| null | ✅ | 读数原值；`null` / 非有限数 ⇒ 面板显示「—」 |
| `unit` | string | ⬜ | 单位，如 `µSv/h` / `nSv/h` / `CPM`。缺失时不显示单位 |
| `baseline` | number \| null | ⬜ | 本底参考值，用于 `level` 缺失时推断倍数；`<=0` 视为不可用 |
| `updated` | string(ISO) | ⬜ | 该读数的观测时间 |
| `level` | `'normal'` \| `'elevated'` \| `'alert'` \| `'unknown'` | ⬜ | **后端分级优先**。缺失时前端兜底推断（见下） |

**严重度归一化（0–100 统一量纲）**，实现见 `src/lib/nuclearData.ts` 的 `readingToValue`：

1. 后端给了合法 `level` 且非 `unknown` ⇒ `normal=20` / `elevated=55` / `alert=85`；
2. 否则 `reading` 与 `baseline` 齐全且 `baseline > 0` ⇒ `value = clamp(20 + (reading/baseline - 1) * 40, 0, 100)`；
3. 否则 ⇒ `value = null`，点位判为**数据缺失**（灰 + 虚线 + 无光环 + 无常驻标签）。

> ⚠ **领域判断归属**：辐射分级阈值应由后端 `level` 给出，前端只负责展示。上面第 2 条的倍数推断仅是后端未给 `level` 时的兜底，**不构成开阳沉淀领域逻辑**。
>
> ⚠ **前端永不编造读数**：`src/config/nuclearSites.ts` 的静态种子只含站点静态属性（名称 / 国家 / 坐标 / 类型），**不含任何 `reading`**，避免占位数字被误读成真实监测值。仓库内的 `public/data/nuclear_sites.json` 开发快照同理：`sites` 齐全、`readings` 为空数组。

### 2.6 后端 feed 状态（13 项，天枢实查回填 2026-08-01）

> **状态：已回填。** 天枢（macro-scan）已于 2026-08-01 完成 NAS 实查逐项核查并回填《现有 fetcher × crucix 源》映射表。本小节据此由原「预览」升级为**正式状态清单 + 字段级转正 / 缺口清单**：逐项标注天枢现状（① 已有 / ② 部分 / ③ 没有）与开阳侧动作，并在末尾给出「可排期 / 暂不排期」分栏。
>
> - 回填原件（13 项逐项结论 + 新闻端规划 + 排期建议）：[`archive/天枢-fetcher×crucix-映射表-回复.md`](./archive/天枢-fetcher×crucix-映射表-回复.md)
> - 原问询件（三选一回填表）：[`archive/天枢-fetcher×crucix-映射表-询问.md`](./archive/天枢-fetcher×crucix-映射表-询问.md)
> - 需求出处（逐项显示需求与缺口分析）：[`CRUCIX_LAYER_REQUIREMENTS.md`](./CRUCIX_LAYER_REQUIREMENTS.md) §7
> - **转正规则不变**：任何一项要被当作既定契约去实现，必须先在本文档补出字段级定义。当前已完成字段级定稿的：第 1 项 `nuclear_sites.json`（§2.5，1.2.0 定稿）、第 10 项 `news_geo.json`（§2.7，**已上线**）、第 13 项 `market_quotes.json`（§1 注册表，**已上线**）。其余各项仍**只有名称 / 数据源 / 优先级 / 现状**，不得据此开工。

#### 2.6.0 回填总览

| 维度 | 天枢实查结论 |
|---|---|
| 三个重点校正源 | **ACLED ❌**（天枢未接，`fetch_hdx.py` 只是危机数据集更新数 INDEX，非事件）；**OpenSky ✅**（`fetch_airtraffic_opensky.py` → `airtraffic_opensky.json` 在跑）；**FIRMS ✅**（`fetch_firms.py` → `firms_fire.json` 在跑，含原始 `lat` / `lng`） |
| 天枢比开阳假设**更完整**的 4 项 | ④ `air_activity` / ⑤ `thermal_spikes` / ⑪ `fred_history` / ⑬ `market_quotes`——均判「② 部分」，采集底座已在运行，缺的是字段整形与序列补齐，不是从零对接 |
| 天枢**完全空白**的 9 项 | ① ② ③ ⑥ ⑦ ⑧ ⑨ ⑩ ⑫——均判「③ 没有」（其中 ⑧ 为合规否决、⑨ 为双方同意搁置） |
| Item 10 前提**被推翻** | `news_export.json` 实际仅 40 条 RSS 文章，字段只有 `title` / `category` / `date`，`source=None`，**0 条带 `lat` / `lng`**；`source:"Crucix新闻"` 实际出现在 `weak_signal_log.json`，是对 crucix API 新闻做的**关键词频率告警**（`indicator` / `current` / `baseline` / `ratio` / `level`），**不是可定位的地理文章**。天枢当前产出 **0 条带坐标新闻** |
| 地理新闻上图**真解** | **新建 GDELT geo feed（方法 B：GDELT Actor Geo）**。天枢已在每 15 分钟下载 GDELT v2 export，事件级 `ActionGeo_Lat` / `ActionGeo_Long` / `FullName` / `CountryCode` 在原始行中已存在，只是被国别聚合（`gdelt_scores.json`）丢弃——「数据下全了，只差导出」。字段契约见 §2.7（**已上线**） |
| 新闻端**诚实边界** | GDELT 事件表**无 headline 文本**，地图点只能标「地点 + 事件类型 + 强度」（如「德黑兰 — 军事冲突」）；真标题需关联 GKG / Mentions 表，不在本期范围。crucix 独有的 **LLM 多源叙事**天枢不重做——「退场 crucix」= **部分退场**（geo + RSS 覆盖，LLM 叙事不覆盖）。RSS 新闻仍为纯文本无 geo，只进新闻面板、不上图 |

#### 2.6.1 新建 feed（9 项）

| # | 对应展示元素 | 建议 feed 名 | 建议数据源 | 优先级 | 天枢现状（实查） | 开阳侧动作 / 待办 | 备注 |
|:--:|---|---|---|:--:|:--:|---|---|
| 1 | 核设施图层 + 核设施监视面板 | `nuclear_sites.json` | Safecast + EPA RadNet | **P0** | ③ 没有<br>（无 Safecast / RadNet fetcher，仅 SIPRI 军备 backdrop 与 disaster 关键词） | **维持现状**：字段契约已定稿 §2.5，前端已上线并等真实读数；6 站静态种子继续生效，读数一律显示「—」，**不因后端缺数做任何回退改造** | **字段契约已定稿（§2.5）**，前端已上线并等真实读数 |
| 2 | 冲突事件图层 | `conflict_events.json` | ACLED | P1 | ③ 没有<br>（**ACLED ❌**，无授权无 fetcher） | **暂不排期**：保留 `conflict` 类别定义与渲染能力，不实现数据接入；做法 A / B 均待天枢有源后再定 | 或改扩 `grv_latest.json` 的 `events[].type` 增 `'conflict'` |
| 3 | 海上监视（AIS 实况） | `maritime_watch.json` | AIS | P2 | ③ 没有<br>（无 AIS / maritime fetcher） | **暂不排期**：9 要冲静态地标为前端硬编码，可独立上线、不依赖后端；AIS 实况部分挂起 | 9 个战略要冲**地标由前端硬编码**，不需后端提供 |
| 4 | 空域活动 | `air_activity.json` | OpenSky + ADS-B Exchange | P2 | ② 部分<br>（`airtraffic_opensky.json` 已在跑，仅聚合计数 / 均高，如「9535 架在飞 + top 来源国」；**无逐机 `lat` / `lng`、无战区分组**） | **可排期**：等天枢补逐机 `lat` / `lng` + `theater` 分组后再转正字段契约。在此之前只能做**计数型**展示（面板数字），**不上图** | 可选航迹弧端点 |
| 5 | 热异常火点 | `thermal_spikes.json` | NASA FIRMS (VIIRS) | P2 | ② 部分<br>（`firms_fire.json` 已在跑，有原始 `lat` / `lng` 点 + 10° 带聚合） | **可排期**：天枢确认开阳的预聚合请求可行，将改为网格 `count` / `confidence_avg`。字段转正待天枢定网格粒度；`MAX_POINTS_PER_LAYER=2000` 护栏保留（截断为下策，聚合为正解） | ⚠ 量级达数千点，**已请后端评估预聚合**；前端已预埋 `MAX_POINTS_PER_LAYER=2000` 护栏 |
| 6 | 太空活动 | `space_activity.json` | CelesTrak | P2 | ③ 没有<br>（无 CelesTrak fetcher） | **暂不排期** | 本轮只要静态点位（发射场 / 星下点），不做轨道动画 |
| 7 | 卫生监视 | `health_watch.json` | WHO + NOAA | P2 | ③ 没有<br>（无 WHO fetcher；HDX 只是 INDEX） | **暂不排期** | 告警若只有国家名，需后端做国家→坐标映射 |
| 8 | 开源情报 | `osint_feed.json` | Telegram + Bluesky + Reddit | P2 | ③ 没有 —— **合规否决**<br>（天枢不做社媒抓取；crucix 做但天枢不接） | **永久取消**：开阳删除 osint 图层定义（清单见下方脚注），`CATEGORY_PALETTE` 同步收窄，**待工程师执行** | ⚠ 合规评估结论为**不通过**，按原约定本图层永久取消，不再追问 |
| 9 | SDR 测站覆盖 | `sdr_coverage.json` | KiwiSDR 等测站网 | P2 | ③ 可搁置<br>（无 KiwiSDR fetcher，天枢同意开阳判断、直接否决） | **暂不排期 / 搁置**：与第 8 项不同，**不做前端删除动作**，类别定义暂留但不实现 | 展示价值最低，双方一致否决 |

> **第 8 项 osint 图层删除清单（待工程师执行）**：天枢合规否决为终局结论，开阳按原约定**永久删除**该图层定义——
>
> | # | 文件 | 删除内容 |
> |:--:|---|---|
> | 1 | `src/config/theme.ts` | `CATEGORY_PALETTE` 中的 `osint: '#f472b6'` 一项（调色板由 13 类**同步收窄**为 12 类） |
> | 2 | `src/config/layerCategories.ts` | `RiskCategory` 联合类型中的 `'osint'` 取值 + `LAYER_CATEGORIES` 中 `key:'osint'` 的图例项 |
> | 3 | `src/index.css` | CSS 变量 `--ky-cat-osint` |
> | 4 | `src/config/layerCategories.test.ts` | `categoryColor('osint')` 相关断言 |
>
> 删除后需保持三者一一对应：`CATEGORY_PALETTE` 键集合 = 图例项 `key` 集合 = `--ky-cat-*` 变量集合（均为 12 类）。

#### 2.6.2 改既有 feed（3 项，成本更低）

> ⚠ 第 10 项经天枢实查后**已由「改既有」转为「新建」**（原前提不成立，见 §2.6.0），本表保留其编号与位置以便与问询件对照。

| # | 对应展示元素 | 改动 | 数据源 | 优先级 | 天枢现状（实查） | 开阳侧动作 / 待办 |
|:--:|---|---|---|:--:|:--:|---|
| 10 | 新闻地理化上图 | ~~既有 `news_export.json` 的 Crucix 条目补 `lat` / `lng`~~ → **新建 `news_geo.json`**（GDELT Actor Geo）：天枢新建 `fetch_gdelt_geo.py`，复用现有 GDELT 下载，提取 `ActionGeo` `lat` / `lng` + 事件类型 + 强度，按关注国家 / 高提及过滤，**I15 调度（每 15 分钟）** | GDELT v2 export（天枢已在下载） | **P1**（后端已有 GDELT 基础，性价比最高） | ✅ **已上线（1.9.0）**：`news_geo_feed.py` + scheduler 注册 | **字段级契约已定稿：§2.7**，前端已上线上图。`news_export.json` **保持现状**（纯文本 RSS，只进新闻面板不上图），不做任何字段改造 |
| 11 | 底部风险仪表 | 既有 `fred_history/manifest.json` 的 `series[]` **增 3 条序列**：VIX / 高收益债利差 / 供应链压力 GSCPI。经济面板无需改动 | FRED + EIA + 纽约联储 | P2 | ✅ **manifest 已上线**（VIX `VIXCLS.csv` 与高收益利差 `BAMLH0A0HYM2.csv` 已存在）；**GSCPI ❌**（属纽约联储非 FRED 原生，天枢待补） | **已兑现大部分**：开阳 `useFRED` 已容错——`manifest` 为 `null` 时降级为空序列并在状态条 / 面板告警，不白屏。VIX 与高收益利差两格**零改动有数**；GSCPI 格在天枢取到前保持留空 |
| 12 | 信号流 sweep delta | 既有 feed 条目增 `delta` 字段（`new`/`escalated`/`deescalated`/`unchanged`），或新建 `signal_delta.json` | 后端 sweep 比对 | P2 | ③ 没有<br>（天枢采集全为覆盖写 / 聚合，无「上轮 vs 本轮」比对机制） | **暂不排期**：开阳**不实现**比对逻辑（铁律，不沉淀后端业务逻辑）；信号流继续按静态快照展示 |

> 第 10 项原独立需求文档 [`archive/开阳Crucix新闻地理坐标需求-给后端.md`](./archive/开阳Crucix新闻地理坐标需求-给后端.md) 的前提（「Crucix 新闻条目只差补 `lat` / `lng`」）经实查**不成立，该文档已作废**，不再作为需求依据；其中的坐标定法 A / B / C 之争亦已收敛为**方法 B（引擎直出，从 GDELT 提取 Actor Geo）**。
> 第 12 项明确：**delta 由后端算好推来，开阳只展示**——开阳不实现比对逻辑（不沉淀后端业务逻辑）。

#### 2.6.3 独立新建（1 项，受铁律硬约束）

| # | 对应展示元素 | 建议 feed 名 | 说明 | 优先级 | 天枢现状（实查） | 开阳侧动作 / 待办 |
|:--:|---|---|---|:--:|:--:|---|
| 13 | 底部市场行情带 | `market_quotes.json` | crucix 原型用 Yahoo Finance。⚠ **开阳禁自连 Yahoo 等任何第三方行情接口**，必须由后端代取落盘，否则该展示位永久留空 | P2 | ✅ **已上线（1.9.0）**：`market_quotes.json` 已注册 + 行情面板 60s 轮询 | **已兑现**：行情带面板已上线，Nasdaq 序列是否补齐以实际数据为准 |

#### 2.6.4 对所有新 feed 的统一要求（无例外）

沿用 §3 扩展标准，落到 feed 层面即：

| # | 要求 |
|:--:|---|
| 1 | 在 `src/config/dataSources.ts` 的 `FEEDS` **登记一项**（开阳侧动作，读取层 `useFeed` / `readLayer` 无需改动） |
| 2 | 在本文档 **补字段定义**（由 §2.6 状态清单转正为 §2.x 正式契约；如第 10 项 → §2.7） |
| 3 | 携带 **`schema_version`**（首版 `"1.0"`，breaking change 必须 bump，读取层比对并告警） |
| 4 | **点位类 feed 必须带 `lat` / `lng`**，统一**小数 4 位**（≈11m）。非有限数或超出 ±90 / ±180 的记录，开阳整条丢弃而**不画到 (0,0)** |
| 5 | 支持**空数组 / 文件缺失**——空数组是合法业务态（如"今日 0 起冲突事件"），开阳按铁律降级：图层不渲染 + 面板「数据缺失」占位 + 状态条告警，**不白屏** |

> **文件粒度口径（D3）**：倾向**每类一个文件**，与天枢 fetcher 一一对应——单类采集失败只影响单个图层，不拖垮整张图。
> **路径口径**：一律使用相对 data 根的相对路径，**禁止任何 NAS / SMB 绝对路径**；开阳侧靠只读挂载 + `DATA_BASE_URL` 指向（见 §0 与 §4）。

#### 2.6.5 排期分栏（据天枢 2026-08-01 回填结论；⑩⑬⑪ 已于 1.9.0 兑现）

**可排期（天枢侧有基础、风险可控）**

| # | feed | 天枢侧动作 | 开阳侧转正条件 |
|:--:|---|---|---|
| ④ | `air_activity.json` | 在既有 OpenSky 采集上补逐机 `lat` / `lng`、按战区（theater）分组 | 拿到逐机坐标后补 §2.x 字段契约；在此之前只做计数型展示 |
| ⑤ | `thermal_spikes.json` | 由 10° 带聚合改为网格 `count` / `confidence_avg`（满足开阳预聚合请求） | 天枢定下网格粒度后补 §2.x 字段契约 |
| ⑩ | **新建** `news_geo.json` | 新建 `fetch_gdelt_geo.py`，提取 GDELT `ActionGeo` 坐标，I15 调度 | ✅ **已兑现（1.9.0）**：`news_geo_feed.py` 上线 + scheduler 注册；§2.7 契约定稿；前端已上线上图 |
| ⑪ | `fred_history` 增强 | 补 `manifest.json`、补 GSCPI 序列 | ✅ **manifest 已到位**（§2.4 契约不变）；GSCPI 序列待天枢补 |
| ⑬ | `market_quotes.json` | 补 Nasdaq 序列，统一落成单文件行情 feed | ✅ **已兑现（1.9.0）**：`market_quotes.json` 已注册 + 行情面板 60s 轮询上线 |

**暂不排期（天枢无基础 / 已否决 / 需另行决策）**

| # | feed | 原因 | 开阳处置 |
|:--:|---|---|---|
| ① | `nuclear_sites.json` | 天枢无 Safecast / RadNet fetcher | **维持前端静态种子 6 站**，读数「—」；§2.5 契约不动，等供数 |
| ② | `conflict_events.json` | **ACLED ❌**，天枢未接 | 保留类别定义，不实现接入 |
| ③ | `maritime_watch.json` | 无 AIS / maritime fetcher | 仅前端 9 要冲静态地标，可独立上线 |
| ⑥ | `space_activity.json` | 无 CelesTrak fetcher | 挂起 |
| ⑦ | `health_watch.json` | 无 WHO fetcher，HDX 仅 INDEX | 挂起 |
| ⑧ | `osint_feed.json` | **天枢合规否决**（不做社媒抓取） | **永久删除图层定义**（清单见 §2.6.1 脚注），待工程师执行 |
| ⑨ | `sdr_coverage.json` | 无 KiwiSDR fetcher，双方一致否决 | 搁置，不做删除动作 |
| ⑫ | delta / `signal_delta.json` | 天枢全为覆盖写，无上轮 / 本轮比对 | 开阳不实现比对逻辑（铁律） |

### 2.7 `news_geo.json`（GDELT 地理事件，**已定稿上线**）

> **状态：已上线（1.9.0）。** 天枢 `news_geo_feed.py` 已产出，scheduler 已注册；开阳读取层已接线上图。本小节字段即正式契约。
>
> **历史**：本小节原为 §2.6 第 10 项的**字段级转正雏形**（1.0 草案）；天枢首产后已按实际字段定稿并摘除「草案」标记。
>
> **结构兼容**：`newsGeoAdapter.adaptNewsGeo` 同时兼容 `events[]` 结构（GDELT 专属）与 `articles[]` 结构（`news_geo_feed.py` P3-A 新闻地理点的 title/url/lat/lng/source/published_at——spaCy NER 未落地前恒为空数组）。adapter 对两结构均容错，空数组不抛异常、不白屏。
>
> **能力边界（照录天枢回复，避免空头支票）**：
> - GDELT 事件表**无 headline 文本** —— 本 feed 的点只能标「地点 + 事件类型 + 强度」（如「德黑兰 — 军事冲突」）。要真标题需关联 GKG / Mentions 表，**不在本期范围**，开阳不得据此规划「新闻标题上图」。
> - crucix 独有的 **LLM 多源叙事**（Reddit / Bluesky / 36kr / ReliefWeb + LLM 综合简报）天枢不重做——「退场 crucix」为**部分退场**。
> - RSS 新闻（`news_export.json`）仍为纯文本无 geo，**只作新闻面板源、不上图**，与本 feed 互不替代。

| 顶层字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | 首版 `1.0`；breaking change 必须 bump（读取层比对并告警） |
| `updated` | string(ISO) | ✅ | 本次导出时间。调度 **I15（每 15 分钟）**，状态条据此显示数据新鲜度 |
| `events` | NewsGeoEvent[] | ✅ | 地理事件点清单。**空数组是合法业务态**（窗口内无满足过滤条件的事件），开阳按铁律降级：图层不渲染 + 面板「数据缺失」+ 状态条告警，**不白屏** |

**NewsGeoEvent**：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | ✅ | 事件唯一 id，建议直接用 GDELT `GLOBALEVENTID`（如 `gdelt-1234567890`）。开阳地图点位 id 为 `newsgeo:<id>` |
| `lat` / `lng` | number | ✅ | 取自 `ActionGeo_Lat` / `ActionGeo_Long`，**统一小数 4 位**（≈11m）。非有限数或超出 ±90 / ±180 的记录，开阳**整条丢弃**而不画到 (0,0)（§2.6.4 第 4 条） |
| `event_type` | string | ✅ | 事件类别。建议枚举 `'conflict'`（冲突 / 军事）\| `'protest'`（抗议 / 骚乱）\| `'disaster'`（灾害 / 事故）\| `'political'`（政治 / 外交）。**CAMEO 事件码 → 四类的映射属领域判断，由天枢完成**；开阳对未知取值降级为中性色，不猜语义 |
| `intensity` | number | ✅ | 强度 **0–100** 归一化，与 §2.5 严重度同量纲（决定点径 / 柱高与配色）。**归一口径由天枢给定**（如基于 `GoldsteinScale` / `AvgTone` / `NumMentions` 合成），开阳不自行折算 |
| `country` | string | ✅ | 国家 / 地区，建议用 `ActionGeo_CountryCode`（如 `IRN`）。用于筛选、分组与 tooltip |
| `mention_count` | number | ⬜ | 该事件被提及次数（GDELT `NumMentions`），可作二级权重与排序依据；缺失不影响渲染 |
| `theme` | string | ⬜ | GKG 主题标签（如 `TAX_FNCACT`）。可选，天枢若未关联 GKG 表则整字段省略 |
| `location_name` | string | ⬜ | **已拍板保留（2026-08-01）**：`ActionGeo_FullName` 地名文本（如 `Tehran, Iran`），用于地图标签与 tooltip 首行。GDELT 原始行已含该列（`FullName=38`），导出成本近似为零；缺失时开阳回落显示 `country` |
| `event_date` | string(ISO) \| string(YYYYMMDD) | ⬜ | **已拍板保留（2026-08-01）**：事件日期（GDELT `SQLDATE`），用于时间窗筛选与「近 N 小时」口径；缺失时开阳一律按 `updated` 处理 |

**统一要求**：本 feed 沿用 §2.6.4 全部 5 条（`FEEDS` 登记 / 本文档补字段 / 带 `schema_version` / 点位 4 位小数 / 空数组与文件缺失合法降级），**无例外**。文件路径为相对 data 根的 `news_geo.json`，禁止绝对路径。

> **待天枢确认的三点**（不影响开阳先行准备，但定稿前需回答）：
> 1. `event_type` 四类枚举是否够用？CAMEO `EventRootCode` → 四类的映射表由天枢维护并在回填时附出。
> 2. `intensity` 0–100 的合成公式与分级口径（属领域判断，开阳不代定）。
> 3. 过滤条件：关注国家清单 + 高提及阈值，直接决定单次落盘条数量级；若可能超过 2000 条，请沿用第 5 项的预聚合思路，否则开阳 `MAX_POINTS_PER_LAYER=2000` 护栏会触发截断（截断为下策）。

---

### 2.8 `reports_index.json`（报告索引，R-1 **已上线**）

> **状态：已上线（1.10.0）。** 天枢 `generate_reports_index.py` 产出（扫描 `docs/分析报告` + `docs/仿真报告`，复制 .md 到 `data/reports/`，nginx 容器只读挂载 `macro-scan/data` → `/usr/share/nginx/html/data`，开阳浏览器可直接 fetch）。

| 顶层字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | `1.0` |
| `updated` | string(ISO) | ✅ | 索引生成时间（状态条显示数据新鲜度） |
| `reports` | ReportMeta[] | ✅ | 报告清单，**最新置顶**（按日期降序） |

**ReportMeta**：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | ✅ | 唯一 id（天枢按源路径 sha1 派生） |
| `type` | string | ✅ | 报告类型：`宏观分析` \| `月度简报` \| `假设推演` \| `演化仿真` \| `预测追踪` |
| `title` | string | ✅ | 展示标题（天枢从文件名派生） |
| `filename` | string | ✅ | 原文件名（含 `.md`） |
| `path` | string | ✅ | **相对 DATA_BASE_URL 的 markdown 路径**（如 `reports/xxx.md`），开阳据此 fetch 正文 |
| `updated` | string | ✅ | 报告日期 `YYYY-MM-DD`（从文件名 / mtime 派生） |

> 面板按 `type` 分组展示（固定顺序），组内最新置顶；点击条目 fetch `path` 渲染 markdown。
> 天枢侧调度：scheduler 07:35（晨报后）/ 20:35（晚报后）各跑一次。

### 2.9 金融条件（FCI / GSCPI，R-3 **已上线**）

`fci_latest.json` 顶层字段（天枢 `compute_fci.py` 产物）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | `fci-1.1` |
| `date` | string | ✅ | 数据日期 `YYYY-MM-DD` |
| `as_of` / `data_vintage` | string | ⬜ | 生成时间 / 底层数据谱系 |
| `fci_revised` | number | ✅ | 全样本重估 FCI（标准差，**越高 = 金融条件越紧**；含 look-ahead，仅可 nowcast/dashboard） |
| `fci_pit` | number | ⬜ | 扩展窗 FCI（无 look-ahead，可 backtest/verification） |
| `interpretation` / `components[]` / `sanity_vs_nfci` | - | ⬜ | 说明 / 成分分解 / 与 Chicago NFCI 一致性校验 |

`fred_history/GSCPI.csv`：`date,value` 月度 CSV（`fetch_gscpi.py` 产物，尾行 = 最新值）。

> 开阳 FinancialPanel 另直接读取 `fci_daily.csv`（`date,fci_revised,fci_pit,...` 日频）绘制 FCI 趋势；
> 该文件列为非常规（多列），不经 FEEDS 注册表，面板内 `fetchText` + 本地解析。

### 2.10 风险信号（六类，R-4 **已上线**）

六类信号文件均带 `_schema_version`（`1.0`）与 `updated`；`status` 取值 `ok` / `unavailable`。开阳 RiskSignalsPanel 逐卡展示评分条 + 事件告警行；**缺失 / 不可用一律降级占位，不白屏**。

| feed | 文件 | 关键字段 |
| --- | --- | --- |
| `climate_signals` | `climate_signals.json` | `climate_risk_score`(0-100) / `risk_level` / `oni{value,status,date,interpretation}`（厄尔尼诺指数） / `firms{total_hotspots,high_confidence}` |
| `disaster_signals` | `disaster_signals.json` | `disaster_risk_score`(0-100) / `risk_level` / `event_count_24h` / `alerts[]` |
| `earthquake_risk` | `earthquake_risk.json` | `seismic_risk`(0-100) / `event_count_24h` / `count_m45|m55|m65` / `max_mag` / `top_events[]{magnitude,place,time_utc}` |
| `energy_risk` | `energy_risk.json` | `grid_carbon_risk`(0-100) / `uk_grid{intensity_forecast,intensity_index,fossil_share_pct}` |
| `hdx_risk` | `hdx_risk.json` | `status`（常为 unavailable）+ `reason` |
| `news_risk` | `news_risk.json` | `status`（常为 unavailable，缺 API key）+ `reason` |

> 地震 `top_events` 以「震级 → 0-100」归一化着色（M4→0，M8→100），复用 Wave1 `events[]` 告警柱色阶语义。

---

## 3. 扩展标准（用户硬性要求，已预埋）
1. **统一读取层** `useFeed(feedName)`：`src/hooks/useFeed.ts` + `src/lib/readLayer.ts`。所有数据经此层；新增 feed 不改读取层。
2. **面板注册表** `panelRegistry`：`src/panels/registry.ts`。每面板 = 组件 + 注册项（`id/title/feed/order/visible/className`）；新增面板只加注册项，布局（App.tsx 网格）无需改动。
3. **字段容错**：缺失字段降级渲染（「数据缺失」占位，不白屏/不崩），缺失项记入顶部状态条。
4. **schema 版本**：每个 feed JSON 带 `schema_version`（Wave1 = `1.0`）；breaking change 须 bump，读取层会比对并告警。
5. **本文件** `DATA_CONTRACT.md`：各 feed 文件名 / 路径 / 字段 / schema_version 的权威标准。

---

## 4. NAS 部署说明

开阳为纯静态站点，`vite build` 产出 `dist/`。

1. **构建**：`npm install && npm run build` → 生成 `dist/`。
2. **数据挂盘**：将天枢 `data/` 目录以**只读**方式挂载到容器某路径（如 `/mnt/tianshu-data/`）。
3. **serve dist**：任意静态服务器（nginx / caddy / `npx serve dist`）服务 `dist/`。
4. **注入数据根**：在 `dist/index.html` 顶部 `<div id="root">` 前加入：
   ```html
   <script>window.__KAIYANG_DATA_BASE_URL__ = "/mnt/tianshu-data/";</script>
   ```
   或将 `DATA_BASE_URL` 指向挂载路径。
5. **定时刷新**：数据由天枢侧更新；开阳无需后端，浏览器按 `fetch` 拉取最新快照（可配合 CDN/缓存策略）。

> SSE / 实时推送等留待后续 Wave；Wave1 为静态 + 前端加载。

---

## 5. 本地开发预览

```bash
npm install
npm run dev        # http://localhost:5173 ，开箱即跑（已内置 public/data 快照）
npm run build      # 产出 dist/
npm run preview    # 预览构建产物
```
