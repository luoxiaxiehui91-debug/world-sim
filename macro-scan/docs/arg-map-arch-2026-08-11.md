# 开阳第二批地图深化 · 架构论证（arch-map）

> 作者：arch-map（首席架构师）｜日期：2026-08-11｜状态：**论证稿 v1.0（仅只读核实，未改动任何代码/数据）**
> 依据：`fetch_gdelt_geo.py` 全文（937 行）+ `news_geo_feed.py` 全文 + `scheduler.py` 注册表 + 开阳前端 `newsGeoAdapter.ts` / `FlatMapPanel.tsx` / `WorldPanel.tsx` / `dataSources.ts` / `layerCategories.ts` / `useFeed.ts` / `mapData.ts` / `strategicSites.ts` + `DATA_CONTRACT.md §2.7` + `docs/archive/fetch_gdelt_geo_design.md`（08-01 设计稿）
> 联动：`docs/arg-map-data-2026-08-11.md`（data-map 实证，本稿结论与其一致并在其上作架构决策）
> 红线合规：全程只读，未改任何代码与数据文件。

---

## 0. 结论先行（架构定调）

1. **路线 A（news_geo_feed.py 改为直接消费 `news_geo.jsonl`）为推荐方案**。jsonl 是当前 GDELT 地理数据的**唯一活数据源**（124,499 事件 / 57MB / I15 增量 / state 连续 820 slots 无失败），坐标、国家、强度、URL 全部达标（data-map §6 实证）。
2. **`gdelt_geo_cache.json` 从未有任何代码写入**（全 repo grep 仅"读取 + 文档声称"，声称的写入者 `geo_risk_vector.py` 实际零引用）——NER 路径是**断链**，不是缺缓存文件。**路线 B 需要在无写入方的前提下新建 cache writer + 重建缓存，且收益仅覆盖 40 篇中文财经 RSS 标题，不推荐作为主线**。
3. **开阳前端 `newsGeoAdapter` 已同时支持 `events[]` 与 `articles[]` 双结构**（§2.7 契约），写 `news_geo.json` 的 `events[]` **不需要改适配层**；只需补 `refreshMs` 轮询即可实现 I15 实时。这是"最小改动"的强依据。
4. **jsonl 缺 CAMEO 事件码**：现 jsonl 的 `type` 字段是 `ActionGeo_Type`（地理精度枚举 0-4），**不是** CAMEO 事件类型；`_map_event` 未导出 `EventCode`(col 26) / `EventRootCode`(col 28)。→ 契约 §2.7 的 `event_type`（conflict/protest/political）与 M-3 冲突筛选**必须先在 fetch_gdelt_geo.py 补两个字段**（小改，见 ADR-map-2）。
5. **M-2（chokepoints/regions）纯前端已完成**：`STRATEGIC_SITES`（8 要地，琥珀金星标）已渲染、`regions.ts` + `RegionTabs` 已实现、`chokepoint` 类别已登记（feed:null）——**无 NAS 数据依赖**。
6. **M-3（conflictData）不新建 feed**：用 jsonl 按 CAMEO root ∈ {15,18,19,20} 筛出 `event_type='conflict'` 子集，落在 `news_geo.json` 同一契约里；前端把 `event_type='conflict'` 的点映射到已登记的 `conflict` 类别色即可，零新增后端产物。
7. **XSS 为最高风险项**：前端 `pointTooltipHtml` 直接拼 HTML 且经 `dangerouslySetInnerHTML` 渲染、无转义；GDELT `full_name`/`source_url` 原样入串有注入面。必须**后端输出转义 + 前端适配层消毒双保险**。

---

## 1. 现状复核（精读结论，佐证 data-map）

### 1.1 两条管线的实况

| 管线 | 代码 | 调度 | 产物 | 状态 |
|---|---|---|---|---|
| 新闻 NER（P3-A） | `news_geo_feed.py`（07:15） | 每日 07:15 | `news_geo.json`（`articles[]`） | ❌ 空壳：`articles:[]` 137B（08-10 23:25 实锤） |
| GDELT 事件（P1） | `fetch_gdelt_geo.py --incremental` | **I15** | `news_geo.jsonl`（124,499 行 57MB）+ `news_geo_state.json` | ✅ 活跃：state last_slot=20260810163000，run_count=697，consecutive_fail=0 |
| GDELT 聚类（T04） | `fetch_gdelt_geo.py --aggregate` | **从未调度** | `news_geo_clusters.json` | ❌ 停更 08-01 19:11（scheduler 仅注册 `--incremental`） |

### 1.2 空渲染根因（证据链）

```
news_geo_feed.py 依赖 gdelt_geo_cache.json（地名→坐标）
  → 全 repo 无任何写入方（geo_risk_vector.py 从未写它，注释是遗留声称）
  → 文件永不存在 → _load_geo_cache() 返回 {} → geo_cache 条目数=0
  → 0/40 篇有坐标 → news_geo.json articles=[] 空壳
  → 开阳 dataSources.ts:90 读 news_geo.json → 空渲染
```

### 1.3 jsonl 字段全集（15 字段，已实测）

```
lat, lng, type(ActionGeo_Type 0-4), country_iso(ISO-3), full_name,
intensity(Goldstein -10~+10), mentions, sources, event_id, sql_date(YYYYMMDD),
actor1_code, actor2_code, source_url, schema_version, fetched_at(+seen_slot 新行)
```

**三个关键缺口/注意**：
1. **无 CAMEO `event_code`/`root_code`**（0/124,499 行有）→ 无法直接产出契约要求的 `event_type`。
2. `type` 字段语义是**地理精度**（1=国家质心 14.6% / 2=ADM1 / 3=ADM2 / 4=已知地点），不是事件类型。
3. `seen_slot` 仅较新行有（早期行缺），时间窗过滤需 `fetched_at` 兜底。

### 1.4 前端消费面（关键）

- `newsGeoAdapter.adaptNewsGeo`：先看 `articles[]`（非空则早退，**忽略 events**），否则走 `events[]` → `NewsGeoEvent` → `RiskPoint`（id 前缀 `newsgeo:`）。**两结构均容错，空数组不抛异常**。
- `NewsGeoRaw` 契约：`{ schema_version?, updated?, events: NewsGeoEvent[] }`。
- `FlatMapPanel`：D3/SVG **逐点渲染**（每点 1-3 个 circle + 事件绑定），`points` 变化时全量重建；无聚类。
- `GlobePanel`（3D globe.gl）与 2D 共用 `allPoints`。
- `capPointsPerLayer`：每类别上限 `MAX_POINTS_PER_LAYER=2000`，超出静默截断 + console.warn（下策）。
- `useFeed('news_geo')`：**无 `refreshMs`** → 仅挂载拉一次，不做 I15 轮询。
- `pointTooltipHtml`：`label/group/rawMetric/note` 原样拼入 HTML → `dangerouslySetInnerHTML`，**无转义（XSS 面）**。

---

## 2. 三条技术路线对比矩阵

| 维度 | **路线 A**：jsonl 直供事件层 | 路线 B：重建 geo_cache 修 NER | 路线 C：双轨合并 |
|---|---|---|---|
| 数据新鲜度 | ✅ **I15**（与 gdelt_geo 同拍） | ⚠️ 日更（07:15，news_export 依赖） | ✅ I15（A 轨）/ 日更（B 轨） |
| 事件量级 | ✅ 可控：24h≈1.2 万原始 → 过滤后 **~400-500 点** | ⚠️ 仅 40 篇/日，且多为中文财经（沪股通/龙虎榜），地理语义弱 | 混合，量级由 A 轨决定 |
| 坐标质量 | ✅ 100% 非空 + 范围校验（data-map §1.4） | ⚠️ NER 中文地名 vs GDELT 英文 full_name **几乎无法匹配** | 同 A（B 轨命中率≈0） |
| `event_type` 质量 | ✅ 补 root_code 后按设计稿 §5.2 映射 | ❌ 产不出（无 CAMEO 上下文） | ✅ 同 A |
| 契约兼容（§2.7） | ✅ `events[]` 直出，适配器零改动 | ⚠️ `articles[]` 结构，适配器已兼容但强度缺失（value=null） | ⚠️ 需改适配器合并（当前 articles 早退会遮蔽 events） |
| 地图渲染负载 | ✅ 后端 cap 1800 + 前端 2000 双护栏 | ✅ 点极少 | ✅ 同 A |
| 开发成本 | **低**：改 `_map_event` 加 2 字段 + 导出段（A1）或改 `news_geo_feed.py`（A2） | 中：需新写 cache writer + 建索引 + 匹配器 | **高**：B + A + 前端适配器合并改造 |
| 运维风险 | 低（零新增外网请求，读本地 jsonl） | 中（cache 重建 + 中文/英文匹配不确定性） | 高（双管线 + 前端合并语义） |
| 顺带收益 | 复活 `--aggregate` 或废弃 clusters；M-3 冲突层同源 | 无 | — |

**裁决**：**路线 A**。理由：数据质量、新鲜度、契约兼容、开发成本全面占优；B 的核心假设（中文 NER 地名 × GDELT 英文坐标缓存）在实证上不成立；C 的双轨收益（40 篇财经新闻点）远低于其成本。C 仅在未来接入**中文地理新闻源**时再评估。

---

## 3. ADR 式决策条目

### ADR-map-1：news_geo.json 数据源切换为 news_geo.jsonl（路线 A）

- **背景**：`news_geo_feed.py` NER 管线因 `gdelt_geo_cache.json` 无写入方而恒空；而 `news_geo.jsonl`（I15 活跃）拥有事件级坐标/强度/国家全量数据却从未被开阳消费。
- **决策**：`news_geo.json` 改为由 jsonl 派生的事件数组（`events[]`），废弃 NER 空转链（`news_geo_feed.py` 退役或改读 jsonl）。
- **后果**：✅ 空渲染根治；新鲜度 07:15→I15；点质量从"0 条"到"数百条"。⚠️ 需补 `event_code/root_code` 字段（ADR-map-2）；地图点无 headline 文本（GDELT 事件表限制，契约 §2.7 已如实声明）。

### ADR-map-2：fetch_gdelt_geo.py 落盘事件补 CAMEO 事件码

- **背景**：`_parse_export` 已解出 `EventCode`(col 26) 但 `_map_event` **未导出**；jsonl 无任何 CAMEO 上下文，`event_type` 与 M-3 冲突筛选无从谈起。
- **决策**：`_map_event` 输出新增 `event_code`(col 26) + `root_code`(col 28，2 位)，schema_version 不变（向后兼容新增字段）。
- **后果**：✅ 新事件具备类型判定能力；✅ 与设计稿 §4.2/§5.2 对齐。⚠️ **旧行不被回填**（`_merge_jsonl` 按 event_id 去重保留首见行）→ 过渡期旧行 `event_type='unknown'`，随窗口滑动 24-48h 内自然换新；若需即时质量可一次性重建 jsonl（降文件+state 重拉，需评估代理水位）。

### ADR-map-3：news_geo.json 输出 events[]（§2.7 契约），调度 I15，前端只补 refreshMs

- **背景**：契约 §2.7 明确顶层 `{schema_version, updated, events[]}` 且期望 I15；前端 `NewsGeoRaw` 与该结构一一对应，`newsGeoAdapter` 已实现 `events[]` 分支。
- **决策**：输出结构 = `{ "schema_version":"1.0", "updated":<+08:00 ISO>, "events":[...] }`；生成频率 I15（与 gdelt_geo 同拍，见 §5 两种落位）；前端 `dataSources.ts` news_geo 补 `refreshMs: 60_000`。
- **后果**：✅ 适配层零改动，前端最小改动；✅ 状态条新鲜度自动正确（`updated` 顶层字段）。⚠️ 契约 §2.7 标注 I15，当前实现 0715 属契约未兑现，本决策补兑现。

### ADR-map-4：过滤默认档 24h + mentions≥15 + 排除地理精度 type=1

- **背景**：实测 24h 窗口 14,534 原始事件；排除 type=1（国家质心，占 14.6%）后 12,286；mentions≥15 → **436 点**，≥20 → 272 点；7d 窗口 mentions≥20 → 1,867 点（略超 1800）。
- **决策**：默认 `WINDOW=24h`、`MIN_MENTIONS=15` → ~400-500 点，远低于双护栏；7d"趋势"档用 `MIN_MENTIONS=30`（≈526 点）或 20+聚合。全部阈值走环境变量。
- **后果**：✅ SVG 逐点渲染无压力；✅ 前端 2000 截断几乎不会触发。⚠️ 强信号点可能因 mentions 低被过滤（可接受，噪声压制优先）。

### ADR-map-5：M-3 冲突层复用 event_type='conflict'，不新建 feed

- **背景**：契约 §2.6.1 项 2 的 ACLED 已放弃；jsonl 的 Goldstein 负值 + actor 码已有冲突语义雏形，但权威判定需 CAMEO root。
- **决策**：冲突事件 = jsonl 中 `root_code ∈ {15,18,19,20}` 的子集，随 `news_geo.json` 的 `event_type='conflict'` 输出；前端 `newsGeoAdapter` 将 `event_type==='conflict'` 的点归入已登记的 `conflict` 类别色（红）。旧行（无 root_code）以启发式 `intensity≤-5 && mentions≥5` 兜底并标注非权威。
- **后果**：✅ 零新增后端产物/feed；✅ 前端仅一行类别映射。⚠️ 与"颜色=类别"既有语义需在 LayerTree 中确保 conflict 类别可独立开关。

### ADR-map-6：M-2 纯前端，无 NAS 数据依赖

- **背景**：战略要冲（chokepoints）与地区（regions）在 crucix 中本就是前端硬编码；开阳已实现 `STRATEGIC_SITES`（8 要地）+ `regions.ts` 6 区 bbox + `RegionTabs`。
- **决策**：M-2 维持"前端硬编码 + 前端过滤"不动后端；如需扩充要冲清单直接改 `strategicSites.ts`。
- **后果**：✅ 零后端改动；✅ 已基本交付（需验收 LayerTree 开关联动）。

---

## 4. 改造设计（路线 A，A1 为推荐落位）

### 4.1 方案落位：A1（并入 fetch_gdelt_geo.py）vs A2（保留 news_geo_feed.py）

| 对比 | **A1（推荐）**：`run_incremental` 末尾生成 news_geo.json | A2：`news_geo_feed.py` 改读 jsonl |
|---|---|---|
| 读性能 | ✅ **零边际成本**：`_merge_jsonl` 已把全量行载入内存，过滤/映射/聚合在内存完成 | ⚠️ 每次读 57MB/124k 行（约 1-2s），I15 下浪费 |
| 新鲜度 | ✅ 与增量同拍（slot 合并后立即导出） | ✅ 同拍（改 I15 调度） |
| 职责边界 | 一个 job 干两件事（落 jsonl + 导出 json） | 导出职责独立，便于单独调试/降级 |
| 运维 | scheduler 少一个 job | 多一个 I15 job（读大文件） |
| 退役 | `news_geo_feed.py` 退役或删调度 | 保留文件改语义 |

> **裁决**：A1。`run_incremental` 末尾追加"从合并后内存行生成 news_geo.json"一段；`news_geo_feed.py` 停止调度（保留文件备查或直接删除）。若团队偏好职责分离，A2 亦可，性能可接受（57MB 全量读 ~1-2s，I15 下 CPU 占用可忽略），但属次优。

### 4.2 输入过滤条件（news_geo.json 生成段）

按顺序执行（先便宜后昂贵）：

| # | 过滤器 | 规则 | 默认 | 环境变量 |
|:--:|---|---|:--:|---|
| 1 | 坐标有效 | lat/lng 有限数 + 在域内（上游已保证，复核兜底） | — | — |
| 2 | **地理精度** | 排除 `type ∈ {0,1}`（国家质心/无效） | 保留 2,3,4 | `NEWS_GEO_ALLOW_TYPES` |
| 3 | **时间窗** | `seen_slot ≥ now-W`（新行）或 `fetched_at ≥ now-W`（旧行兜底）；均转 UTC 时间戳比较 | **24h** | `NEWS_GEO_WINDOW_HOURS` |
| 4 | **提及阈值** | `mentions ≥ M`（上游 MIN_MENTIONS=5 已过，这里再收紧） | **15** | `NEWS_GEO_MIN_MENTIONS` |
| 5 | 事件类型 | `root_code` 存在 → 设计稿 §5.2 映射表；缺失 → `'unknown'` | — | — |
| 6 | 容量护栏 | 结果 > `MAX_EVENTS` 时按 intensity 降序截断 + `WARNING` 日志（不静默） | **1800** | `NEWS_GEO_MAX_EVENTS` |
| 7 | 聚合（可选） | 仍超限时按 `(round(lat,2), round(lng,2), event_type)` 聚合：intensity=max / mention_count=sum / id=代表事件 / event_date=max | 关 | `NEWS_GEO_AGGREGATE` |

> 默认档实测产出 ~436 点（ADR-map-4），聚合档通常不会触发，保留作为防爆兜底。

### 4.3 字段映射表（jsonl → NewsGeoEvent）

| NewsGeoEvent（§2.7） | jsonl 字段 | 处理规则 |
|---|---|---|
| `id` | `event_id` | `gdelt-<event_id>`（文件内唯一，适配器再加 `newsgeo:` 前缀） |
| `lat` / `lng` | `lat` / `lng` | 原样透传（已 4 位小数）；非有限/越界整条丢弃 |
| `event_type` | `root_code`（**新增**） | 设计稿 §5.2 映射：root 14→`protest`，15/18/19/20→`conflict`，其余→`political`；缺失→`unknown`。**本 feed 不产 `disaster`**（CAMEO 无灾害根码，§5.3） |
| `intensity` | `intensity`(Goldstein) + `mentions` | 设计稿 §5.4 公式 → 整数 1-100（见 4.4） |
| `country` | `country_iso` | 原样透传（已 FIPS→ISO-3 映射，契约例 `IRN` 一致） |
| `mention_count` | `mentions` | 原样透传（可选字段） |
| `theme` | — | **省略**（需 GKG 表关联，不在范围，契约 §3.2 允许） |
| `location_name` | `full_name` | 原样透传 + **HTML 转义**（XSS，见 §7） |
| `event_date` | `sql_date` | `YYYYMMDD` → `YYYY-MM-DD`（契约 ISO 日期） |
| 顶层 `schema_version` | — | 固定 `"1.0"`（breaking change 才 bump） |
| 顶层 `updated` | — | `datetime.now().astimezone()` 带 `+08:00`（与现有 `news_geo_feed.py`/STATUS 时间戳契约一致；设计稿的 `Z` 后缀在实现中未采用，维持现状避免契约漂移） |

### 4.4 intensity 合成口径（沿用设计稿 §5.4，0-100 整数）

```
g   = min(abs(Goldstein), 10) / 10            # 0..1 事件烈度
m   = min(log1p(mentions) / log1p(50), 1.0)   # 0..1 传播广度，M_REF=50
raw = 0.6 * g + 0.4 * m
intensity = clamp(round(raw * 100), 1, 100)   # 下限 1，避免 0 被前端判缺失
```

> 语义澄清（必须同步开阳）：intensity 是**事件显著度**（烈度×传播），**不是风险度**；方向由 `event_type` 表达，配色按类型区分，勿只看数值判"危险"（设计稿 §5.4）。

### 4.5 调度建议

- **A1**：`fetch_gdelt_geo.py --incremental`（I15）末尾自动生成 news_geo.json；**无需改 scheduler**（沿用现有 I15 注册行）。
- **A2**：`news_geo_feed` job 由 `0715` 改 `I15`，`scheduler.py` 改动必须 `docker restart macro-scan-macro-scan-1` 生效。
- **顺带**：`news_geo_clusters.json` 若需复活，scheduler 在 `--incremental` 后追加 `--aggregate`；否则删除该产物并更新 scheduler 注释（当前注释声称"产出 news_geo.jsonl + news_geo_clusters.json"与事实不符）。

### 4.6 性能控制

| 环节 | 现状 | 措施 |
|---|---|---|
| jsonl 读取 | 57MB/124k 行，`_merge_jsonl` 每 15min 全读 | A1 复用内存行零边际成本；长期建议滚动窗口/分区（见 §7） |
| news_geo.json 体积 | ~400 点 × ~200B ≈ **80KB** | 默认档无需压缩；必要时 `separators` 紧凑 + `ensure_ascii=False` |
| 地图渲染 | SVG 逐点（每点 3 circle + handler） | 后端 cap 1800 + 前端 2000 双护栏；默认 436 点无压力；7d 档用 ≥30 或聚合 |

---

## 5. M-2 chokepoints / regions 数据源评估

| 图层 | P1 登记 | 数据源结论 | 现状 |
|---|---|---|---|
| 战略要冲 chokepoints | `layerCategories.ts` `'chokepoint'`（feed:null，diamond，琥珀色） | **纯前端硬编码，无 NAS 数据**：`data/strategicSites.ts` `STRATEGIC_SITES` 8 处（霍尔木兹/苏伊士/博斯普鲁斯/直布罗陀/马六甲等，琥珀金星标 + 中文常驻标签 + tooltip） | ✅ 已实现并渲染（`FlatMapPanel` 的 `sites` prop，`WorldPanel.tsx:194` 传 `validStrategicSites(...).filter(inRegion)`） |
| 地区 regions | `RegionTabs`（P1） | **纯前端 bbox 常量**：`config/regions.ts` 6 区（全球/美洲/欧洲/中东/亚太/非洲），`RegionTabs.tsx` 已实现 | ✅ 已实现（含跨 180° 经线与极区变形 N6 防护） |

**结论**：M-2 无后端数据接入点，**不涉及天枢**。验收重点 = LayerTree 开关联动 + 图例计数 + 与事件层的层级关系（要冲在最上、不淹没核读数菱形）。

---

## 6. M-3 conflictData 字段映射

**数据源**：`news_geo.jsonl`（ADR-map-5，不新建 feed）。

| 冲突事件字段 | jsonl 字段 | 处理 |
|---|---|---|
| `lat` / `lng` | `lat` / `lng` | 原样 |
| `event_type` | `root_code`（新增） | root ∈ {15,18,19,20} → `'conflict'`（设计稿 §5.2：Exhibit Force / Assault / Fight / Unconventional Mass Violence） |
| `intensity` | `intensity`(Goldstein)+`mentions` | §5.4 公式（冲突事件 Goldstein 为负 → 烈度高 → 显著度高，语义正确） |
| `country` | `country_iso` | 原样 |
| `location_name` | `full_name` | 原样 + HTML 转义 |
| `event_date` | `sql_date` | `YYYYMMDD`→`YYYY-MM-DD` |
| `mention_count` | `mentions` | 原样 |
| 行为体 | `actor1_code` / `actor2_code` | 可选：tooltip 展示（如 `COP`=警察 / `MIL`=军事，`actor1` 非空率 87.8% / `actor2` 60.9%） |
| 出处 | `source_url` | tooltip/点击跳转（**必须转义**，见 §7） |
| 旧行兜底（无 root_code） | `intensity` + `mentions` | 启发式 `Goldstein ≤ -5 && mentions ≥ 5` → 标记冲突但**非权威**（data-map §5.2 抽样该档样本语义合理） |

**前端落位**：`newsGeoAdapter` 对 `event_type==='conflict'` 的点赋 `category:'conflict'`（已登记类别色，`layerCategories.ts:112`），其余事件走 `category:'news'`；`conflict` 类别可独立开关（LayerTree 既有机制）。**不改 `FlatMapPanel` 渲染器**（类别色由构建层预计算，K6 不变）。

---

## 7. 风险登记

| # | 风险 | 等级 | 影响 | 缓解措施 |
|:--:|---|---|---|---|
| R1 | **XSS：`full_name`/`source_url` 原样入 tooltip HTML** | **H** | `pointTooltipHtml` 无转义 + `dangerouslySetInnerHTML` 渲染；恶意地名/URL 可注入脚本 | ① 后端生成 news_geo.json 时对 `location_name`/`source_url` 做 HTML 实体转义（`&<>"'`）；② 前端 `newsGeoAdapter` 对 `location_name`/`theme`/`rawMetric` 消毒（双保险，防后端遗漏） |
| R2 | 契约破坏（结构/字段漂移） | M | 开阳 `NewsGeoRaw`/`NewsGeoEvent` 校验告警 | 输出严格对齐 §2.7：顶层 `schema_version`/`updated`/`events`；breaking change 必须 bump `schema_version`；前端 `useFeed` 已有版本比对告警 |
| R3 | 旧 jsonl 行无 `root_code` → `event_type='unknown'` 过渡期 | M | 过渡期 24-48h 内冲突/政治点显中性色 | 接受过渡（窗口滑动自然换新）；`_merge_jsonl` 去重保首见 → **不会回填**，若需即时质量一次性重建 jsonl（降文件+state 重拉，须先评估代理水位，见 ADR-map-2） |
| R4 | jsonl 读取性能（57MB 全量） | L | A2 方案每次 I15 读 57MB 约 1-2s | A1 复用 `_merge_jsonl` 内存行，零边际成本（推荐）；长期给 jsonl 加滚动窗口/按月分区，防无限增长（30d 内占比 98.9%，当前可控） |
| R5 | 地图渲染性能（SVG 逐点） | M | 数万点会卡帧 | 后端 cap 1800 + 前端 `MAX_POINTS_PER_LAYER=2000` 双护栏；默认档 ~436 点；7d 档用 `MIN_MENTIONS=30` 或聚合（ADR-map-4） |
| R6 | 新鲜度语义（sql_date 滞后 ~1 天） | M | "最近 24h"实际是昨日全天 | 时间窗主键用 `seen_slot`/`fetched_at`（GDELT 抓取时刻）而非 `sql_date`；`sql_date` 仅用于 event_date 展示与 7d 趋势档 |
| R7 | `gdelt_geo_cache` 重建（路线 B 依赖） | L | Route A 完全绕开；B 需新写 cache writer + 匹配器 | 不采纳 B；删除 `news_geo_feed.py` 对 cache 的引用，避免误导后续接手者 |
| R8 | clusters 停更/注释误导 | L | scheduler 注释声称产出 clusters 与实际不符 | 复活 `--aggregate`（一行）或删除产物并更正注释 |
| R9 | 代理/流量 | L | Route A 零新增外网请求（读本地 jsonl） | 无新增预算；若走 jsonl 一次性重建才涉及重拉（评估后再动） |
| R10 | 前端轮询缺失（news_geo 无 refreshMs） | M | I15 数据不轮询 = 页面不刷新 | `dataSources.ts` news_geo 加 `refreshMs: 60_000`（与 market_quotes 同模式） |

---

## 8. 建议实施顺序（供 team-lead 排期）

1. **后端（天枢，1 个 commit）**：`fetch_gdelt_geo.py` —— ① `_map_event` 补 `event_code`/`root_code`；② `run_incremental` 末尾生成 `news_geo.json`（§4 过滤 + §4.3 映射 + §4.4 强度 + HTML 转义）。scheduler 无需改（A1 沿用 I15）。`news_geo_feed.py` 停止调度。
2. **前端（开阳，1 个 commit）**：`dataSources.ts` news_geo 加 `refreshMs`；`newsGeoAdapter` 加 conflict 类别映射 + 输入消毒；可选 `pointTooltipHtml` 转义。
3. **验收**：容器实测 `news_geo.json` events 非空 + 数量 ≈ 400-500；开阳地图出现彩色事件点；状态条新鲜度 I15；`npm test` 全绿；`schema_version` 比对无告警。
4. **可选**：复活 `--aggregate`（clusters）或删除产物；7d 趋势档环境变量调优。

---

## 附：证据清单（文件:行）

| 证据 | 位置 |
|---|---|
| scheduler 仅注册 `--incremental` | `macro-scan/核心代码/scheduler.py:64` |
| news_geo_feed 07:15 注册 | `scheduler.py:98` |
| jsonl 缺 event_code（0/124,499） | `fetch_gdelt_geo.py` `_map_event`（不导 col 26/28）+ data 实测 |
| `type`=ActionGeo_Type 而非 CAMEO | `fetch_gdelt_geo.py:276-278`（`_map_event` 的 `type` 取自 ActionGeo_Type）+ `_filter_row` 允许 {0,1,2,3,4} |
| 适配器双结构支持 | `kaiyang/src/lib/newsGeoAdapter.ts`（articles 早退分支 + events 分支） |
| NewsGeoRaw 契约 | `kaiyang/src/types/contracts.ts:206-233` |
| 渲染无聚类 | `kaiyang/src/components/FlatMapPanel.tsx` `buildPoints`（逐点 append + 全量重建） |
| 2000 上限 | `kaiyang/src/config/layerCategories.ts:215` + `WorldPanel.tsx:99` |
| 无 refreshMs | `kaiyang/src/config/dataSources.ts:88-93` |
| tooltip 无转义 | `kaiyang/src/lib/mapData.ts` `pointTooltipHtml` + `FlatMapPanel.tsx` `dangerouslySetInnerHTML` |
| §2.7 契约 | `kaiyang/docs/DATA_CONTRACT.md:277-315` |
| CAMEO 映射/强度/护栏 | `macro-scan/docs/archive/fetch_gdelt_geo_design.md §5.2/§5.4/§6` |
| cache 无写入方 | data-map §3（全 repo grep 空）+ `geo_risk_vector.py` 0 引用 |
| 24h/7d 过滤量实测 | 本稿 §1.3/ADR-map-4（443/436/272、1867/526 等） |
