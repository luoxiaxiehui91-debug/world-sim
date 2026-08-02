# 回复：《天枢现有 fetcher × crucix 源》映射表询问

> **发往**：开阳（kaiyang）团队
> **发自**：天枢（macro-scan）· 许清楚（产品经理）
> **日期**：2026-08-01
> **关联**：[`天枢-fetcher×crucix-映射表-询问.md`](./天枢-fetcher×crucix-映射表-询问.md)
> **一句话说明**：本文为天枢侧基于 NAS 实测资产逐项目核查后的正式回填，所有结论均来自实查证据，未做推测；请据此更新 `DATA_CONTRACT.md` §2.6 与 P1/P2 排期。

---

## 一、重要前提纠正（Item 10）—— 开阳假设不成立

开阳《映射表-询问》§2 第 10 行与 §4.2 第 10 项假设：`news_export.json` 里 `source:"Crucix新闻"` 的条目"只差补 `lat`/`lng` 就能上图"。

**实测结论：该前提不成立。**

- `news_export.json` 由天枢 `news_exporter.py` 从 `data/news.db` 导出、供 macro-sim 消费，实际仅含 **40 条 RSS 文章**，字段只有 `title/category/date`，`source=None`，**0 条带 `lat`/`lng`**。
- `source:"Crucix新闻"` 实际出现在 `weak_signal_log.json`（730 条信号日志）里，是 `scan_weak_signals.py` 对 crucix API 新闻做的**关键词频率告警**（字段为 `indicator/current/baseline/ratio/level`），**不是可定位的地理文章**。
- crucix 的新闻在它自己的 `runs/latest.json`（含 `news/newsFeed`），天枢**不消费 crucix 的新闻**。天枢消费 crucix 仅通过 API(3117) 取 `gscpi/nuke/sdr/air` + FIRMS 兜底。
- **结论：天枢当前产出 0 条带坐标新闻。**

因此 Item 10 的"补 `lat`/`lng`"路径不可行，地理新闻上图需另寻解法（见第四节）。

---

## 二、GDELT 真相（决定新闻端怎么解）

- 天枢**已经在下载** GDELT v2 export：`scan_weak_signals.py` 内 `_fetch_gdelt_recent` 每 15 分钟落一个文件；`weak_signal` 调度 00/06/12/18 跑，`gdelt_scores.json` 今 12:06 刚更新。
- 但现有逻辑只把 GDELT 聚合成**国别分** `gdelt_scores.json`（FRA/USA/IRN per 维度），**事件级 `lat`/`lng` 在下载原始行里已存在**（`ActionGeo_Lat=42` / `Long=43` / `FullName=38` / `CountryCode=39`）却被聚合丢弃——即"数据下全了，只差导出"。
- 故"地理新闻上图"的真解是：**新建 GDELT 地理事件点 feed（方法 B：GDELT Actor Geo），从已有数据提取 ActionGeo 坐标**。这恰好也是"逆分析 crucix 新闻"的载体（crucix 新闻本就是 GDELT 系带 geo）。

---

## 三、13 项 feed 天枢现状回填表（NAS 实查）

| # | feed | 判定 | 依据（NAS 实查） | 备注 |
|---|---|:--:|---|---|
| 1 | `nuclear_sites.json` | ③ 没有 | 无 Safecast/RadNet fetcher（仅 SIPRI 军备 backdrop、disaster 关键词） | 开阳 P0 壳上的「—」读数暂无法供给 |
| 2 | `conflict_events.json` | ③ 没有 | 无 ACLED；`fetch_hdx.py` 只是"危机数据集更新数" INDEX，非事件 | **ACLED ❌** |
| 3 | `maritime_watch.json` | ③ 没有 | 无 AIS/maritime fetcher | — |
| 4 | `air_activity.json` | ② 部分 | `fetch_airtraffic_opensky.py` 存在 → `airtraffic_opensky.json`，但只聚合计数/均高（9535 在飞、top 来源国） | 无逐机 `lat`/`lng`、无战区分组 |
| 5 | `thermal_spikes.json` | ② 部分 | `fetch_firms.py` → `firms_fire.json`，有 `lat`/`lng` 原始点 + 10°带聚合 | 需改成网格 `count`/`confidence_avg`（你们 §5 的预聚合请求可行） |
| 6 | `space_activity.json` | ③ 没有 | 无 CelesTrak fetcher | — |
| 7 | `health_watch.json` | ③ 没有 | 无 WHO fetcher；HDX 只是 INDEX | — |
| 8 | `osint_feed.json` | ③ 没有（合规：天枢不做社媒抓取） | 无 Telegram/Bluesky/Reddit；crucix 做但天枢不接 | 建议开阳永久删除该图层 |
| 9 | `sdr_coverage.json` | ③ 可搁置 | 无 KiwiSDR fetcher | 同意开阳判断，直接否决 |
| 10 | `news_export.json` 补 `lat`/`lng` | ③ 未支持（需新建 GDELT geo feed） | 见第一节 | 见第四节解法 |
| 11 | `fred_history` 增 3 序列 | ② 部分 | `VIXCLS.csv` ✅ `BAMLH0A0HYM2.csv` ✅ 已存在；`GSCPI` ❌（属 NY Fed 非 FRED）；且 fred_history **无 manifest.json** | 需补 GSCPI 序列 + 补 manifest.json |
| 12 | delta / `signal_delta.json` | ③ 没有 | 无"上轮 vs 本轮"比对，全为覆盖写/聚合 | — |
| 13 | `market_quotes.json` | ② 部分 | `SP500.csv`(FRED)✅ `commodity_yahoo.json`(黄金/原油)✅ `crypto_history`(BTC)✅ `fx_history`✅ | 缺 Nasdaq 专门序列 |

**实查小结**：天枢在 ④⑤⑪⑬ 上比开阳假设更完整（FIRMS/OpenSky/VIX/BAML/S&P500/fx/crypto/commodity 均在运行）；在 ①②③⑥⑦⑧⑨⑩⑫ 上完全空白。开阳点名的"ACLED/OpenSky/FIRMS 天枢有没有"：**OpenSky ✅、FIRMS ✅、ACLED ❌**。

---

## 四、新闻端"地理新闻上图"规划：交付项与诚实边界

### 可交付（高把握，低风险）
- 新建 `fetch_gdelt_geo.py`，复用现有 GDELT 下载，提取 ActionGeo `lat`/`lng` + 事件类型 + 强度，过滤关注国家/高提及 → 输出 `news_geo.json`（或扩展 `news_export.json` 给 GDELT 源补 `lat`/`lng`）。
- 调度 I15（每 15 分钟，scheduler 已支持）；满足开阳 Item 10 **方法 B**（精确坐标，无需"关键词→地区"映射的粗糙 hack）。
- 这等于 crucix 地理新闻能力的 Python 真重实现。

### 不可交付（不能承诺，否则开阳 P2 排期变空头支票）
- **地图点没有新闻标题文本**：GDELT 事件表无 headline，点只能标"地点+事件类型+强度"（如"德黑兰 — 军事冲突"）。要真标题需关联 GKG/Mentions 表（额外活），非本期范围。
- **crucix 独有 LLM 多源叙事**（Reddit/Bluesky/36kr/ReliefWeb + LLM 综合简报）天枢不重做 → "退场 crucix"= **部分退场**（geo+RSS 覆盖，LLM 叙事不覆盖）。
- **RSS 新闻**（`fetch_rss_news`）仍是纯文本无 geo，作新闻面板源，不上图。

---

## 五、给开阳 P2 排期的输入建议

**可排期（天枢侧有基础、风险可控）**：
- ④ `air_activity.json` 增强（补逐机 `lat`/`lng` / 战区分组）
- ⑤ `thermal_spikes.json` 增强（改网格 `count` / `confidence_avg`，满足你们预聚合请求）
- ⑪ `fred_history` 增强（补 GSCPI 序列、补 manifest.json）
- ⑬ `market_quotes.json` 增强（补 Nasdaq 专门序列）
- ⑩ 新建 GDELT geo feed（见第四节）

**需开阳另行决策或本项目暂不做**：
- ① `nuclear_sites` / ② `conflict_events`(ACLED) / ③ `maritime_watch` / ⑥ `space_activity` / ⑦ `health_watch` / ⑧ `osint_feed`(合规否决) / ⑨ `sdr_coverage`(可搁置) / ⑫ `delta`

> 以上判定口径与你们既有约定一致：路径一律相对天枢 data 根，点位类 feed 带 4 位小数 `lat`/`lng`，空数组为合法业务态。任何字段分歧以天枢实际能产出的为准，开阳改前端适配即可。
