# fetch_gdelt_geo.py 设计文档（天枢 · GDELT 地理事件点 feed）

> **文件**：`design/fetch_gdelt_geo_design.md`
> **状态**：设计先行稿 v1.0（待架构师高见远评审 → 工程师寇豆码实现 → QA 严过关回归）
> **执笔**：产品经理 许清楚（Xu）· 2026-08-01
> **上游依据**：开阳 `kaiyang-wave2/docs/DATA_CONTRACT.md` §2.6 第 10 项 + §2.7（1.0 草案）
> **交付定位**：本文件是 `fetch_gdelt_geo.py` 实现的**唯一依据**。凡本文件与 STATUS.md / MEMORY.md 旧记载冲突处，**以本文件为准**（冲突点已在 §4.1、§2.2 显式列出）。

---

## 1. 目标与范围

### 1.1 目标

新建天枢 fetcher `fetch_gdelt_geo.py`，从**天枢已在下载**的 GDELT v2 export 原始行中提取事件级 `ActionGeo` 坐标，按关注国家与提及量过滤后落盘 `news_geo.json`，并在 `scheduler.py` 注册 I15（每 15 分钟）调度。

一句话：**「数据下全了，只差导出」——把已经下载但被国别聚合丢弃的坐标导出来。**

### 1.2 交付价值

| 维度 | 说明 |
|---|---|
| 解开阳依赖 | 直接解锁开阳 P1「新闻地理化上图」（DATA_CONTRACT Item 10，**方法 B：GDELT Actor Geo**） |
| crucix 退场 | 等价于 crucix 地理新闻能力的 Python **纯重写**实现（守 AGPL-3.0 边界，零代码继承） |
| 成本 | 下载链路已存在、解析逻辑已验证，属低风险增量 |

### 1.3 范围内（In Scope）

1. 新增单文件 `fetch_gdelt_geo.py`（不改动任何既有 fetcher）。
2. 独立实现 GDELT v2 export 的 URL 生成 / 下载 / zip 解压 / tab 解析（逻辑参照 `scan_weak_signals.py` 的 `_gdelt_urls_last_hours` 与 `_parse_gdelt_zip`，**不 import** 该模块）。
3. ActionGeo 坐标 + CAMEO 类型 + 强度提取，关注国家 / 提及量过滤，同坐标聚合。
4. 落盘 `news_geo.json`（相对 data 根），带 `schema_version`。
5. `scheduler.py` 注册 I15 + `LOG_FILES` 登记。
6. `--selftest` / `--demo` 自测入口。

### 1.4 明确不在范围（Out of Scope · 不向开阳承诺）

| # | 不做 | 原因 |
|:--:|---|---|
| 1 | **地图点带新闻标题文本** | GDELT **事件表无 headline 字段**。要真标题须关联 GKG / Mentions 表，本期不做。地图点只能标「地点 + 事件类型 + 强度」（如「德黑兰 — 军事冲突」） |
| 2 | **crucix LLM 多源叙事重做** | Reddit / Bluesky / 36kr / ReliefWeb + LLM 综合简报，天枢不重做。「退场 crucix」= **部分退场**（geo + RSS 覆盖，LLM 叙事不覆盖） |
| 3 | **RSS 新闻上图** | `news_export.json` 为纯文本 RSS（40 条，无 geo），**只进新闻面板不上图**，与本 feed 互不替代、不做字段改造 |
| 4 | **改动 `scan_weak_signals.py`** | 既有跑通模块，改动有回归风险。本期新 fetcher 自带精简解析（见 §2.3 对 STATUS「抽共享 helper」计划的偏离说明） |
| 5 | **`disaster` 类事件点** | CAMEO 无自然灾害根码，本 feed 结构上产不出 `disaster`。灾害点由 `firms_fire.json` / 地震 feed 负责（见 §5.3 诚实说明） |
| 6 | **上轮 vs 本轮 delta 比对** | 天枢全为覆盖写，对应 DATA_CONTRACT Item 12，已判暂不排期 |

### 1.5 空态即合法

坐标过滤后窗口内无满足条件的事件 → 输出 `"events": []`，**这是合法业务态不是故障**。开阳按铁律降级（图层不渲染 + 面板「数据缺失」+ 状态条告警，**不白屏**）。fetcher 此时**正常退出码 0**，不得 raise、不得跳过落盘。

---

## 2. 数据源现状与复用策略

### 2.1 现状（实查结论，2026-08-01）

| 事实 | 说明 |
|---|---|
| 下载已存在 | `scan_weak_signals.py::_fetch_gdelt_recent()` 已在拉取 GDELT v2 export（`.export.CSV.zip`，tab 分隔） |
| 坐标已到手 | 原始行中 `ActionGeo_FullName` / `ActionGeo_CountryCode` / `ActionGeo_Lat` / `ActionGeo_Long` **均已随文件下载** |
| 坐标被丢弃 | `_compute_gdelt_scores()` 只按 CAMEO 集合聚合成**国别分** `gdelt_scores.json`，事件级坐标在聚合后被丢弃 |
| 天枢现状 | **0 条带坐标新闻**（已实查，开阳 Item 10 原前提「Crucix 新闻只差补 lat/lng」不成立，该需求文档已作废） |
| 可复用逻辑 | `_gdelt_urls_last_hours()`（URL 生成）+ `_parse_gdelt_zip()`（zip → tab 行）+ `_GDELT_PROXY`（出网代理）+ `_CAMEO_*` 集合（类型映射） |

### 2.2 ⚠️ 现有 GDELT 拉取频率**三处记载不一致**（实现前必须实查）

| 出处 | 记载的 GDELT 拉取频率 |
|---|---|
| 本任务书 | 「已**每 15 分钟**下载」 |
| `STATUS.md` L85 | 「weak_signal **00/06/12/18**」（日 4 次） |
| `采集频率矩阵.md` | 「GDELT 聚合 = **周档 1/周**」 |

**影响**：直接决定新 fetcher 上线后 GDELT 出口流量的放大倍数（若现状是日 4 次，I15 = 96 次/日，放大 **24×**，触及红线③「代理 IP 集中限额」）。

**动作（P0，阻塞实现）**：工程师开工第一步 `ssh nas` 实查 `scheduler.py` 中 `scan_weak_signals` 的 JOBS 行与 `_gdelt_urls_last_hours` 的默认 hours，把真实频率回填本节，再据 §7 定采集窗口。

### 2.3 复用策略：**逻辑复用，代码独立**

- 新 fetcher **不 `import scan_weak_signals`**——该模块 import 即执行的副作用（全局初始化 / 网络调用）不可控，且 I15 高频调用会放大副作用。
- 采取「照抄逻辑 + 独立常量」：URL 生成、zip 解析、CAMEO 集合在新文件内**独立定义一份**。
- ⚠️ **对既有计划的偏离**：`STATUS.md` 下一步第 3 条与 `项目导航.md` 曾写「抽到共享 helper 防重复下载」。本设计**不抽 helper**，理由：抽 helper 必须改 `scan_weak_signals.py`（既有跑通模块 + 属核心资产），回归风险 > 收益。**改为**：待未来出现第三个 GDELT 消费方时再抽 `gdelt_common.py`。此偏离已记录，请架构师复核确认。

---

## 3. 输出契约 `news_geo.json`

### 3.1 顶层结构

| 字段 | 类型 | 必填 | 值 / 说明 |
|---|---|:--:|---|
| `schema_version` | string | ✅ | 首版固定 `"1.0"`；breaking change 必须 bump（开阳读取层比对并告警） |
| `updated` | string(ISO) | ✅ | 本次导出时间，**UTC + `Z` 后缀**，如 `2026-08-01T14:30:00Z`。开阳状态条据此显示新鲜度 |
| `events` | NewsGeoEvent[] | ✅ | 地理事件点清单；**空数组合法**（§1.5） |

### 3.2 NewsGeoEvent 字段

| 字段 | 类型 | 必填 | 来源 | 规则 |
|---|---|:--:|---|---|
| `id` | string | ✅ | `GLOBALEVENTID` | 格式 `gdelt-<GLOBALEVENTID>`，如 `gdelt-1234567890`。**文件内必须唯一**（开阳点位 id = `newsgeo:<id>`）。聚合后取该点「贡献 max intensity」那条事件的 id 作代表 |
| `lat` | number | ✅ | `ActionGeo_Lat` | **统一保留 4 位小数**（≈11m）。非有限数 / 超出 ±90 → **整条丢弃**（不画到 (0,0)） |
| `lng` | number | ✅ | `ActionGeo_Long` | 同上，超出 ±180 → **整条丢弃** |
| `country` | string | ✅ | `ActionGeo_CountryCode` | 原样透传（如 `IRN`）。⚠ GDELT 用 **FIPS 10-4** 编码而非 ISO 3166（见 §12 待确认 Q3） |
| `type` | string | ✅ | CAMEO root code 映射 | 取值见 §5.2 枚举。⚠ 字段命名与开阳草案有出入，见 §3.4 |
| `intensity` | number | ✅ | 合成 | 整数 **1–100**（下限取 1，避免 0 被前端误判为缺失）。口径见 §5.4 |
| `mention_count` | number | ⬜ | `NumMentions` | 聚合时取 **sum**。缺失则整字段省略 |
| `location_name` | string | ⬜ | `ActionGeo_FullName` | **已拍板保留**。如 `Tehran, Iran`；空串则整字段省略（开阳回落显示 `country`） |
| `event_date` | string | ⬜ | `SQLDATE` | **已拍板保留**。输出 ISO 日期 `YYYY-MM-DD`（由 `SQLDATE` 的 `YYYYMMDD` 转换）。聚合时取**最新** |
| ~~`theme`~~ | — | ❌ | — | **本期不产出**（需关联 GKG 表，不在范围）。按草案「天枢若未关联 GKG 则整字段省略」执行 |

### 3.3 样例输出

```json
{
  "schema_version": "1.0",
  "updated": "2026-08-01T14:30:00Z",
  "events": [
    {
      "id": "gdelt-1234567890",
      "lat": 35.6944,
      "lng": 51.4215,
      "country": "IR",
      "type": "military",
      "intensity": 78,
      "mention_count": 42,
      "location_name": "Tehran, Tehran, Iran",
      "event_date": "2026-08-01"
    }
  ]
}
```

空态样例（合法）：

```json
{ "schema_version": "1.0", "updated": "2026-08-01T14:30:00Z", "events": [] }
```

### 3.4 ⚠️ 契约对齐差异：`type` vs `event_type`（P0 待开阳确认）

| 维度 | 本任务书（天枢侧） | 开阳 DATA_CONTRACT §2.7 草案 |
|---|---|---|
| 字段名 | `type` | **`event_type`** |
| 取值枚举 | `military` / `tension` / `protest` / `sanction` / `coop` 等（CAMEO root 细类） | `conflict` / `protest` / `disaster` / `political`（四类） |

**PM 处置建议（本设计采纳，待开阳回签）**：**双写兼容**——同一条事件同时输出两个键，语义各自明确、成本近似为零：

| 键 | 值域 | 消费方 |
|---|---|---|
| `event_type` | 开阳四类枚举（`conflict` / `protest` / `political`；本 feed 不产 `disaster`） | 开阳渲染 / 配色，**§2.7 草案零改动生效** |
| `type` | 天枢五细类（`military` / `tension` / `protest` / `sanction` / `coop` / `other`） | tooltip 细分、天枢内部筛选与后续分析 |

过渡期结束（开阳首产回签定稿）后删其一。若架构师判定「冗余字段不可接受」，**优先保 `event_type`**（因为开阳文档已写死、前端已按此规划降级配色），`type` 降为可选。

---

## 4. GDELT 列映射（⚠️ 全文最关键章节）

### 4.1 先纠错：两份现存记载**都不可信**

| 来源 | 记载 | 判定 |
|---|---|:--:|
| `MEMORY.md` L52 / `STATUS.md` L20 / `项目导航.md` L123 | ActionGeo `FullName=38` / `CountryCode=39` / `Lat=42` / `Long=43` | ❌ **错误**。这组偏移落在 **Actor1Geo / Actor2Geo 区块**，不是 ActionGeo |
| 本任务书 | ActionGeo 块在 **48–53**（Type=48 / FullName=49 / CountryCode=50 / ADM1=51 / Lat=52 / Long=53） | ❌ **同样不正确**。该假设隐含「每个 Geo 块 6 字段」，而 GDELT 1.0 的 Geo 块为 **7 字段**（含 FeatureID）、2.0 为 **8 字段**（含 ADM2Code + FeatureID）——6 字段块在两个版本中**都不存在** |

> **根因**：GDELT 1.0（日档）与 2.0（15 分钟档）列布局不同，历史记载混用了 1.0 偏移并进一步串位。天枢下载的是 **v2 export**，必须用 2.0 布局。

### 4.2 权威列表（GDELT 2.0 Events export · **61 列**，0-based）

> 依据：GDELT Event Codebook V2.0（官方）+ 两份独立 schema 实现（`gdelttools` / `gdeltPyR`）交叉验证，2026-08-01 核对。

**本 fetcher 需要用到的列**：

| 0-based 列号 | 字段名 | 用途 |
|:---:|---|---|
| **0** | `GLOBALEVENTID` | → `id`（`gdelt-<v>`） |
| **1** | `SQLDATE`（YYYYMMDD） | → `event_date` |
| **26** | `EventCode` | sanction 等细类精确匹配 |
| **28** | `EventRootCode` | → `type` / `event_type` 主映射 |
| **29** | `QuadClass` | 备用校验（1 言语合作 / 2 物质合作 / 3 言语冲突 / 4 物质冲突） |
| **30** | `GoldsteinScale` | → `intensity` 分量（−10 ~ +10） |
| **31** | `NumMentions` | → `mention_count` + `intensity` 分量 + 噪声过滤阈值 |
| **51** | `ActionGeo_Type` | 精度过滤（排除国家质心，见 §5.1） |
| **52** | `ActionGeo_FullName` | → `location_name` |
| **53** | `ActionGeo_CountryCode` | → `country` + 关注国家过滤 |
| **56** | `ActionGeo_Lat` | → `lat` |
| **57** | `ActionGeo_Long` | → `lng` |

**三个 Geo 区块完整对照（各 8 字段）**：

| 区块 | Type | FullName | CountryCode | ADM1Code | ADM2Code | Lat | Long | FeatureID |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Actor1Geo | 35 | 36 | 37 | 38 | 39 | 40 | 41 | 42 |
| Actor2Geo | 43 | 44 | 45 | 46 | 47 | 48 | 49 | 50 |
| **ActionGeo** | **51** | **52** | **53** | **54** | **55** | **56** | **57** | **58** |

尾部：`DATEADDED` = 59，`SOURCEURL` = 60。**总列数 = 61**。

> 对照 §4.1：MEMORY 记的 38/39/42/43 恰好落在 Actor1Geo 的 ADM1Code / ADM2Code / Long / FeatureID —— 用它取坐标会拿到 Actor1 而非 Action 的位置（甚至拿到非坐标字段），是**静默错误**（不报错、坐标看似合理但语义错），故必须靠 §4.3 的运行时闸拦截。

### 4.3 🚦 运行时列断言闸（强制卡点，不可省略）

**禁止直接硬编码任何列号后就正式使用**。fetcher 内必须实现列自检，通过后方可解析：

| # | 断言项 | 判定标准 | 不通过时行为 |
|:--:|---|---|---|
| A1 | 列宽 | `len(cols) == 61` | 该行计入 `bad_width` 并跳过 |
| A2 | 事件 ID | `cols[0]` 可 `int()` | 该行跳过 |
| A3 | 坐标可解析 | `cols[56]` / `cols[57]` 为空串（合法，无地理）或可 `float()` | 空 → 跳过；不可解析 → 计入 `bad_geo` 并跳过 |
| A4 | 坐标域 | `-90 ≤ lat ≤ 90` 且 `-180 ≤ lng ≤ 180` 且均为有限数 | **整条丢弃** |
| A5 | 地名形态 | `cols[52]` 非空时应含字母；`cols[53]` 长度 ≤ 3 且非纯数字 | 计入 `bad_geo` 并跳过 |
| A6 | root code | `cols[28]` 为 2 位数字字符串（`"01"`~`"20"`） | 归 `other` |
| **A7** | **批级熔断** | 单批中「成功解析出合法坐标的行数 / 总行数」**< 1%**，或 `bad_width` 占比 **> 5%** | **不落盘**、日志 `CRITICAL`、**退出码非 0**——防止列漂移后静默产出整篇垃圾坐标覆盖掉上一版好数据 |

> A7 是本设计对「列号错了怎么办」的兜底：宁可保留上一版旧数据 + 报警，也不接受用错列静默覆盖。

**首次上线额外要求（一次性）**：工程师须 `ssh nas` 取**一行真实 GDELT v2 export 样本**，人工核对 `cols[52] / cols[53] / cols[56] / cols[57]` 分别是地名文本 / 国家码 / 纬度 / 经度，并把该样本行**固化为 selftest fixture**（§11）。核对结果回填本文档 §4.4。

### 4.4 实测回填区（工程师首跑后填写）

```
样本 URL      ：（待填，如 http://data.gdeltproject.org/gdeltv2/20260801143000.export.CSV.zip）
样本行列数    ：（待填，期望 61）
cols[52]      ：（待填，期望形如 "Tehran, Tehran, Iran"）
cols[53]      ：（待填，期望形如 "IR"）
cols[56]/[57] ：（待填，期望可 float 且在域内）
结论          ：□ 与 §4.2 一致  □ 不一致（须停工并回改本文档）
```

---

## 5. 过滤、类型映射与强度口径

### 5.1 过滤链（顺序执行，先便宜后昂贵）

| 序 | 过滤器 | 规则 | 可配项（环境变量） |
|:--:|---|---|---|
| 1 | 列宽 / ID | §4.3 A1–A2 | — |
| 2 | 坐标有效 | §4.3 A3–A4；空坐标行直接跳过 | — |
| 3 | **关注国家** | `ActionGeo_CountryCode ∈ _WATCH_COUNTRIES` | 见下方说明 |
| 4 | **地理精度** | 排除 `ActionGeo_Type == 1`（国家质心）——否则一国所有事件堆叠在国家中心点，是**假精度**且视觉污染 | `GDELT_GEO_ALLOW_TYPES`，默认 `2,3,4,5` |
| 5 | **提及阈值** | `NumMentions >= MIN_MENTIONS`，噪声压制 | `GDELT_GEO_MIN_MENTIONS`，默认 **5**（首产实测后调） |
| 6 | 事件去重 | 同 `GLOBALEVENTID` 只保留一条（跨槽位文件可能重复） | — |

**关注国家清单口径（硬要求）**：必须**运行时从 `alert_config` 读取 `_WATCH_COUNTRIES`**（单一真相源），**禁止在新 fetcher 内硬编码国家清单**——否则两处清单漂移会造成「弱信号有分、地图无点」的诡异不一致。若 `alert_config` 不可导入，fallback 到空集合并 **`WARNING` 日志 + 输出空 events**（fail-loud，不静默放行全球事件）。

> ⚠ 编码制式风险：`_WATCH_COUNTRIES` 若存的是 ISO 3166 三字码（`IRN`），而 GDELT `ActionGeo_CountryCode` 是 **FIPS 10-4 两字码**（`IR`），直接比对将**恒为空**。实现时必须核对两侧制式，必要时加一层 FIPS↔ISO 映射表。**这是本 feed 最可能"跑通但 0 条"的坑**，selftest 须覆盖（§11 用例 ⑤）。

### 5.2 CAMEO root code → 事件类型映射

| root | CAMEO 含义 | 天枢 `type` | 开阳 `event_type` |
|:--:|---|---|---|
| 01 | Make Public Statement | `other` | `political` |
| 02 | Appeal | `coop` | `political` |
| 03 | Express Intent to Cooperate | `coop` | `political` |
| 04 | Consult | `coop` | `political` |
| 05 | Engage in Diplomatic Cooperation | `coop` | `political` |
| 06 | Engage in Material Cooperation | `coop` | `political` |
| 07 | Provide Aid | `coop` | `political` |
| 08 | Yield | `coop` | `political` |
| 09 | Investigate | `other` | `political` |
| 10 | Demand | `tension` | `political` |
| 11 | Disapprove | `tension` | `political` |
| 12 | Reject | `tension` | `political` |
| 13 | Threaten | `tension` | `political` |
| **14** | **Protest** | `protest` | **`protest`** |
| 15 | Exhibit Force Posture | `military` | `conflict` |
| **16** | **Reduce Relations** | `sanction`※ | `political` |
| 17 | Coerce | `tension` | `political` |
| **18** | **Assault** | `military` | `conflict` |
| **19** | **Fight** | `military` | `conflict` |
| **20** | **Use Unconventional Mass Violence** | `military` | `conflict` |

※ **sanction 精确化**：制裁在 CAMEO 中是 root 16 下的具体码（如 `163` 施加禁运/制裁、`1031`/`1033` 相关要求）。实现顺序为 **先按 `EventCode`(列 26) 精确匹配 sanction 码集 → 未命中再按 root code 映射**。

> **强制对齐要求**：上表是设计基线。工程师实现时须把 `scan_weak_signals.py` 内既有的 `_CAMEO_MILITARY` / `_CAMEO_TENSION` / `_CAMEO_PROTEST` / `_CAMEO_SANCTION` / `_CAMEO_COOP` 集合**逐一比对**（只读、不 import），**差异处以既有集合为准**并回填本表——保证同一事件在 `gdelt_scores.json` 与 `news_geo.json` 中类型判定一致。比对结果记入 §12 待确认表。

### 5.3 关于 `disaster`（诚实说明）

开阳四类枚举中的 `disaster` **本 feed 结构上产不出**：CAMEO 编码体系针对政治/社会**行为体动作**，无自然灾害根码。灾害点位由 `firms_fire.json`（热异常）与地震 feed 承担。请开阳不要期待本 feed 出现 `disaster` 取值。

### 5.4 `intensity` 合成口径（0–100，天枢给定，开阳不自行折算）

```
g   = min(abs(GoldsteinScale), 10) / 10            # 0..1  事件烈度（绝对值）
m   = min(log1p(NumMentions) / log1p(M_REF), 1.0)  # 0..1  传播广度，M_REF = 50
raw = W_G * g + W_M * m                            # W_G = 0.6, W_M = 0.4
intensity = clamp(round(raw * 100), 1, 100)        # 整数，下限 1
```

| 项 | 取值 | 说明 |
|---|---|---|
| `M_REF` | 50 | 提及量参考基准，环境变量 `GDELT_GEO_MENTION_REF` 可调 |
| `W_G` / `W_M` | 0.6 / 0.4 | 烈度权重优先于传播权重 |
| 缺失处理 | `GoldsteinScale` 缺 → `g=0`；`NumMentions` 缺 → `m=0` | 两者皆缺 → `intensity = 1`（保留点，不丢） |

> ⚠️ **语义澄清（必须同步开阳）**：`intensity` 是**事件显著度**（烈度 × 传播广度），**不是风险度**。高 Goldstein 正值的合作类事件（如重大和平协议）也会得到高 intensity。**方向由 `type` / `event_type` 表达，配色应按类型区分方向，不能只看 intensity 高低推断"危险"**。

---

## 6. 聚合与规模控制

### 6.1 同坐标聚合

- **聚合键**：`(round(lat,4), round(lng,4), type)`
- **合并规则**：

| 字段 | 规则 |
|---|---|
| `intensity` | **max** |
| `mention_count` | **sum** |
| `id` | 取贡献 max intensity 的那条事件的 `gdelt-<GLOBALEVENTID>`（并列时取 `NumMentions` 更大者，再并列取 ID 较小者，保证**确定性**） |
| `location_name` / `country` | 取代表事件的值 |
| `event_date` | 取组内**最新**日期 |

- **唯一性断言**：聚合后 `id` 在文件内必须唯一（selftest 覆盖）。
- 合并条数不单独输出字段（契约无此项）；合并信息体现在 `mention_count` 求和。是否需要 `merged_count` 列入 §12 Q4。

### 6.2 规模护栏

开阳 `MAX_POINTS_PER_LAYER = 2000`，超限会触发前端截断（下策）。天枢侧主动控制：

| 层级 | 措施 |
|---|---|
| 预期量级 | 单个 15 分钟槽位全球约 1.5k–3k 条事件；经「关注国家 + 精度≥州省级 + NumMentions≥5」三重过滤后，**预计每槽位剩余个位数~数十条**，6 小时窗口聚合后应远低于 2000（**首产必须实测回填**，见 §12 Q5） |
| 硬上限 | `MAX_EVENTS = 1800`（留 10% 余量）。超出时按 `intensity` 降序截断 |
| 截断可观测 | 触发截断必须 `WARNING` 日志记录「截断前/后条数」，并在 STATUS.md 记一笔；**不静默截断** |

---

## 7. 采集窗口与流量预算（需架构师拍板）

I15 调度下「每次抓多长窗口」直接决定代理出口流量（红线③：多源共享 `192.168.31.108:7890`，按代理 IP 总流量算水位）。

| 方案 | 做法 | 每日 zip 下载数 | 有状态 | 地图点密度 | 评价 |
|:--:|---|:--:|:--:|---|---|
| **A** | 每次下最近 `N` 小时全部槽位（N=2 → 8 个 zip） | ~768 | 否（幂等） | 好 | 实现最简，**流量最重**，不推荐 |
| **B**（推荐） | 每次只下**最近 1–2 个槽位**（覆盖上游延迟），维护滚动窗口 state 文件 `_state/gdelt_geo_window.json`（保留近 `W` 小时事件，默认 W=6），输出为窗口内全量 | ~96–192 | 是 | 好 | 流量与 GDELT 更新节奏 1:1 对齐，**推荐** |
| C | 每次只下 1 个槽位，输出仅含最近 15 分钟事件 | ~96 | 否 | **差**（点太稀，过滤后常为空） | 展示效果不可接受 |
| D | 复用 `scan_weak_signals` 下载缓存，零额外流量 | 0 | 是 | 取决于 sws 频率 | **与 I15 新鲜度目标冲突**（若 sws 是 00/06/12/18，缓存最多 6 小时更一次），且需改 sws。列为**后续优化**，不在本期 |

**PM 建议**：采用 **方案 B**，`W`（窗口小时数）与 `GDELT_GEO_SLOTS`（每次回看槽位数，默认 2）均走环境变量。state 文件同样落 `DATA_DIR/_state/` 并用 tmp→rename 原子写；state 损坏 / 缺失时自动重建为空窗口（不 crash）。

**若架构师判定 state 复杂度不可接受** → 退方案 A 但把 N 降到 1（4 个 zip/次），并在首周实测代理水位后复评。

**流量红线**：上线后 24 小时内必须实测代理出口增量；若触及水位告警，立即降频（I15 → I30）或切方案 D。

---

## 8. 落盘与 DATA_DIR 红线

### 8.1 DATA_DIR 解析（🚨 P0 红线，踩过的坑）

```
优先级：os.environ["DATA_DIR"]  →  optim_config.DATA_DIR  →  "/workspace/data"
```

| 规则 | 说明 |
|---|---|
| ✅ 允许 | `from optim_config import DATA_DIR, WORKSPACE`（**import 白名单，仅此两项**） |
| ❌ **严禁** | `from optim_config import FRED_PROXY` —— `optim_config` **无该变量**，会整条 `ImportError` 走 fallback，导致 `DATA_DIR` 落到**非持久卷 `/data`，容器重启即丢** |
| ✅ 代理读法 | `FRED_PROXY = os.environ.get("FRED_PROXY", "")`；GDELT 出网沿用 `_GDELT_PROXY` 口径，默认 `http://192.168.31.108:7890`，可由 `GDELT_PROXY` 环境变量覆盖 |
| ✅ 环境变量优先 | 支持 `DATA_DIR` 覆盖，供 QA 影子跑（`/workspace/qa_shadow`）隔离验证 |
| ✅ 启动断言 | 启动时打印实际 `DATA_DIR`；生产部署基线校验须断言 `DATA_DIR == /workspace/data`（SOP 部署卡点） |

### 8.2 写盘方式

| 项 | 规则 |
|---|---|
| 路径 | `os.path.join(DATA_DIR, "news_geo.json")` —— **相对 data 根，禁止任何 NAS / SMB 绝对路径** |
| 原子性 | **同目录内** tmp 文件 → `os.rename`。⚠ 红线①：绝不可与单文件 bind mount 组合（`news_geo.json` 位于目录挂载的 `/workspace/data` 下，符合要求；交付须过**静态闸二**扫描确认 compose 无文件级 volume） |
| 编码 | UTF-8，`ensure_ascii=False`（地名含非 ASCII），`separators` 紧凑 |
| 失败语义 | 上游全部下载失败 → **不覆盖**已有 `news_geo.json`，`ERROR` 日志 + 非 0 退出；「下载成功但过滤后 0 条」→ **正常覆盖为空 events**（这是业务态不是故障） |

---

## 9. 调度注册

### 9.1 `scheduler.py` 改动（两处）

```python
# JOBS 列表追加（放在 earthquake / energy 同区域）
("gdelt_geo", "I15", "1-7", None, [PYTHON, "fetch_gdelt_geo.py"]),
```

```python
# LOG_FILES 追加
"gdelt_geo": f"{LOG_DIR}/gdelt_geo.log",
```

### 9.2 生效方式（🚨 易踩）

> **`scheduler.py` 改动必须 `docker restart macro-scan-macro-scan-1` 才生效。**
> 代码热挂载只对普通 `*.py` 生效，**对 scheduler 不适用**。改完不重启 = 看起来改了实际没跑。

### 9.3 并发与令牌

- `scheduler.py` 属 **SOP 核心文件独占令牌**范围：同一时段仅一个 agent 可改，须先向 lead（齐活林）申领令牌。
- 建议与 STATUS 第 8 项「修 FT/BBC 路由」**并入同一轮 scheduler 变更 + 一次 restart**，减少重启次数。
- 错峰：`I<min>` 语法无相位参数。因 `scan_weak_signals` 与本 job 下载的是**不同 URL 集、写不同文件**，无写冲突；首版**不做人为错峰**，实测若出现 CPU / 代理争抢再加固定启动延迟。

---

## 10. 诚实边界（对开阳的对外口径，逐条照录）

1. **无新闻标题**：GDELT 事件表无 headline 文本，地图点只能标「地点 + 事件类型 + 强度」（如「德黑兰 — 军事冲突」）。真标题需关联 GKG / Mentions 表，**不在本期范围**，开阳不得据此规划「新闻标题上图」。
2. **crucix 部分退场**：LLM 多源叙事（Reddit / Bluesky / 36kr / ReliefWeb + LLM 简报）天枢不重做；「退场 crucix」= **部分退场**（geo + RSS 覆盖，LLM 叙事不覆盖）。
3. **RSS 不上图**：`news_export.json` 纯文本无 geo，只作新闻面板源，与本 feed 互不替代，**不做字段改造**。
4. **空数组合法**：过滤后无事件 → `events: []`，开阳按铁律降级不白屏。
5. **无 `disaster` 类**：见 §5.3。
6. **`intensity` ≠ 风险度**：见 §5.4 语义澄清。
7. **`country` 为 FIPS 10-4 而非 ISO 3166**（待 §12 Q3 确认后定稿）：开阳若按 ISO 三字码做映射会对不上。

---

## 11. QA 策略

### 11.1 `--selftest`（内置 fixture，无网络依赖，必须 5/5 PASS）

| # | 用例 | 断言 |
|:--:|---|---|
| ① | **字段提取正确** | 用固化的真实 GDELT 样本行，断言 `id` == `gdelt-<GLOBALEVENTID>`、`lat`/`lng`/`country`/`type`/`intensity` 全部正确；且 `id` 在输出内唯一 |
| ② | **坐标越界整条丢弃** | 构造 `lat=91` / `lng=-181` / `lat=NaN` / `lat=""` / `lat="abc"` 五种坏行 → 输出 `events` 中**均不出现**，且**不出现 (0,0) 点** |
| ③ | **4 位小数** | 输入 `35.694400123` → 输出恰为 `35.6944`；断言所有 `lat`/`lng` 小数位 ≤ 4 |
| ④ | **空数组合法** | 全部行被过滤 → 输出 `events: []`，文件结构完整（含 `schema_version` / `updated`），**退出码 0** |
| ⑤ | **关注国家过滤生效** | 构造关注国 + 非关注国各若干行 → 仅关注国事件出现；**并额外断言 FIPS/ISO 制式匹配**（防「跑通但 0 条」，见 §5.1 风险） |

**建议追加（非任务书要求，PM 认为必要）**：

| # | 用例 | 断言 |
|:--:|---|---|
| ⑥ | 列宽熔断 | 喂入 61 列以外的行占比 > 5% → **不落盘 + 非 0 退出**（验证 §4.3 A7） |
| ⑦ | 同坐标聚合 | 同点两条事件 → 合并为 1 条，`intensity` = max、`mention_count` = sum、`id` 确定性 |
| ⑧ | 类型映射 | root 14 → `protest`/`protest`；root 19 → `military`/`conflict`；EventCode 163 → `sanction`/`political` |

### 11.2 容器内冒烟（部署后）

```bash
# 1) 编译
docker exec macro-scan-macro-scan-1 python3 -c "import py_compile;py_compile.compile('/app/fetch_gdelt_geo.py',doraise=True)"
# 2) import 冒烟（无副作用）
docker exec macro-scan-macro-scan-1 python3 -c "import fetch_gdelt_geo; print('OK')"
# 3) DATA_DIR 断言
docker exec macro-scan-macro-scan-1 python3 -c "import fetch_gdelt_geo as m; assert m.DATA_DIR=='/workspace/data', m.DATA_DIR; print('DATA_DIR OK')"
# 4) selftest
docker exec macro-scan-macro-scan-1 python3 /app/fetch_gdelt_geo.py --selftest
# 5) demo（合法 JSON，不写生产文件）
docker exec macro-scan-macro-scan-1 python3 /app/fetch_gdelt_geo.py --demo
# 6) 真实跑 + 落盘路径校验（必须在 /workspace/data，不在 /data）
docker exec macro-scan-macro-scan-1 python3 /app/fetch_gdelt_geo.py
docker exec macro-scan-macro-scan-1 sh -c 'ls -l /workspace/data/news_geo.json && head -c 400 /workspace/data/news_geo.json'
docker exec macro-scan-macro-scan-1 sh -c 'ls /data/news_geo.json 2>&1'   # 期望 No such file
```

### 11.3 验收卡点（AC，逐条勾选后方可交付）

- [ ] **AC-1** §4.4 实测回填区已填，样本行确认列 52/53/56/57 语义正确
- [ ] **AC-2** 代码内**无**裸硬编码列号即用（A1–A7 断言闸齐全，A7 熔断可触发）
- [ ] **AC-3** `--selftest` **8/8 PASS**（①–⑤ 必需 + ⑥–⑧ 建议）
- [ ] **AC-4** `py_compile` PASS + `import` 冒烟无副作用
- [ ] **AC-5** 落盘确认在 `/workspace/data/news_geo.json`，`/data/` 下**无**同名文件
- [ ] **AC-6** **静态闸一**（import 白名单：无 `from optim_config import FRED_PROXY`）通过
- [ ] **AC-7** **静态闸二**（compose 无单文件 bind mount）通过
- [ ] **AC-8** scheduler JOBS + LOG_FILES 已加，`docker restart` 后日志确认 job 已加载且首次触发
- [ ] **AC-9** 首产 `news_geo.json` 条数 / 类型分布 / country 分布回填 §12 Q5，并同步开阳
- [ ] **AC-10** 24 小时后代理出口流量水位复查无告警（§7）
- [ ] **AC-11** 输出经开阳 §2.7 契约逐字段比对（含 §3.4 `type`/`event_type` 双写决议）
- [ ] **AC-12** STATUS.md / `采集频率矩阵.md` / 当日 memory 已更新；`MEMORY.md` L52 的**错误列号已订正**

---

## 12. 风险与待确认

### 12.1 风险登记

| # | 风险 | 等级 | 缓解 |
|:--:|---|:--:|---|
| R1 | **列索引错误导致静默错数据**（历史记载已两次出错） | 🔴 P0 | §4.3 A1–A7 断言闸 + A7 批级熔断 + §4.4 人工核对回填 |
| R2 | **FIPS vs ISO 国家码制式不匹配 → 跑通但恒 0 条** | 🔴 P0 | §5.1 制式核对 + selftest ⑤ + 首产条数回填 |
| R3 | **GDELT 出口流量放大**（现状频率三处记载不一，见 §2.2） | 🟠 P1 | §2.2 先实查真实频率 → §7 方案 B + 24h 水位复查 + 可降频 |
| R4 | GDELT 出网直连 vs 代理 | 🟡 P2 | 沿用 `_GDELT_PROXY`（容器已实证可达），实现前 `curl` 实测一次直连/代理二选一 |
| R5 | `_WATCH_COUNTRIES` 覆盖不足开阳想上图区域 | 🟡 P2 | 首产后把实际 country 分布同步开阳；若缺口大，讨论是否为本 feed 单设更宽的地图关注集 |
| R6 | `scheduler.py` 并发改动冲突 | 🟡 P2 | SOP 独占令牌 + 与 FT/BBC 路由改动合并一轮 restart |
| R7 | 上游 GDELT 槽位延迟 / 偶发 404 | 🟢 P3 | 回看 2 个槽位；单槽位 404 不算失败，全部失败才 fail |
| R8 | 点数超 2000 触发开阳截断 | 🟢 P3 | §6.2 天枢侧 1800 硬上限 + 告警 |

### 12.2 待确认清单（回签后本文档转正为定稿）

| # | 问题 | 对象 | 阻塞开工？ |
|:--:|---|---|:--:|
| Q1 | `type` vs `event_type` 命名与枚举：接受 §3.4 **双写兼容**方案？ | 开阳 | 否（双写已兜底） |
| Q2 | `scan_weak_signals` 现有 GDELT 拉取真实频率（§2.2 三处记载不一） | 天枢工程师实查 | **是** |
| Q3 | `country` 采用 GDELT 原生 **FIPS 10-4** 两字码，还是天枢侧转 ISO 3166 三字码？ | 开阳 + 天枢 | **是**（影响 §5.1 过滤是否有效） |
| Q4 | 是否需要 `merged_count` 可选字段暴露同点合并条数？ | 开阳 | 否 |
| Q5 | 首产实际条数 / 类型分布 / country 分布（决定 `MIN_MENTIONS` 与护栏是否需调） | 天枢首产回填 | 否 |
| Q6 | §5.2 映射表与既有 `_CAMEO_*` 集合的差异 | 天枢工程师比对回填 | 否 |
| Q7 | §7 采集窗口方案 A / B 定夺 | 架构师 | **是** |
| Q8 | §2.3「不抽共享 helper」偏离既有 STATUS 计划，是否认可？ | 架构师 | 否 |

---

## 13. 交付物清单

| # | 交付物 | 责任人 | 说明 |
|:--:|---|---|---|
| 1 | 本设计文档（评审通过 + 待确认项回填） | PM 许清楚 | 唯一实现依据 |
| 2 | 任务拆解 + §7 / §12 阻塞项裁决 | 架构师 高见远 | 含 Q3 / Q7 拍板 |
| 3 | `fetch_gdelt_geo.py`（含 `--selftest` / `--demo`） | 工程师 寇豆码 | 走 scp 单文件 + 基线校验部署通道 |
| 4 | `scheduler.py` 两处改动 + `docker restart` | 工程师（持令牌） | 与 FT/BBC 改动合并一轮 |
| 5 | QA 回归报告（AC-1 ~ AC-12） | QA 严过关 | 独立验证，可用 `/workspace/qa_shadow` 影子跑 |
| 6 | 开阳同步件：首产样本 + §12 Q1/Q3/Q5 回签 | PM 许清楚 | 触发开阳 §2.7 摘除「草案」标记并在 `FEEDS` 登记 `newsGeo` |
| 7 | 文档固化：STATUS.md / 采集频率矩阵 / memory / **MEMORY.md L52 列号订正** | 全员 | AC-12 |

---

**修订记录**

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-08-01 | 初稿。纠正 GDELT 列映射（MEMORY 38/39/42/43 与任务书 48–53 **均不正确**，权威值 ActionGeo Lat=56 / Long=57 / FullName=52 / CountryCode=53，共 61 列）；新增运行时断言闸 A1–A7、采集窗口流量方案对比、FIPS/ISO 制式风险、`type`/`event_type` 双写兼容方案 |
