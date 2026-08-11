# 停用 crucix 具体方案 — 架构视角依赖摘除设计（Round 1）

> 作者：arch-review（首席架构师）｜日期：2026-08-10｜状态：**设计稿 v1.2（仅只读核实，未实施任何改动）**
> 前置依据：`docs/crucix-dependency-analysis-2026-08-10.md`（全量 grep 实证 6 个依赖点）+ `docs/arg-round1-data-2026-08-10.md`（data-review 实证；v1.2 起含 §9 SafeCast 复刻 nuke、§8 KiwiSDR 接入落地）
> 红线合规：未读取/复制 crucix 源码；全部设计基于天枢侧代码实况与公开数据源。
> **v1.2 变更摘要**：① nuke A 层由「空输入+降级登记」改为「新增 `fetch_safecast_nuke.py` 复刻保留」（data-review §9 实证 SafeCast 可 1:1 复刻，round1 空输入结论作废）；② sdr 接入获用户拍板，由「删除不引入」改为「独立产物 + narrative 弱信号」正式设计（data-review §8）；③ ADR-03/04 按实证修正，新增 ADR-09。

---

## 0. 结论先行（架构定调）

1. **D1/D2 是唯一"实时硬依赖"**：gscpi 走 `_crucix` 注入，无天枢侧对等生产者。替代源已实证可行（NY Fed 官方 xlsx 直连 200，**FRED 无此序列**）。
2. **D3 是"死配置"而非"硬依赖"**（本轮实证修正）：`narrative_chunks` 实库 **0 条 crucix_*** 记录，唯一 `ingest_article` 调用者是 `fetch_defense_rss.py`，`run_daily_narrative_processing` 的 json_sources 仅 5 个 fetcher 无 crucix。DEFAULT_SOURCE_MAP / source_dimension_map.yaml 中 4 条 crucix 映射**从未有数据流**，属预留/残留配置。摘除 = 删配置，**对 GRV 零影响**。
3. **nuke/sdr/air 处置（v1.2 修订，据 data-review §8/§9 实证）**：
   - **sdr = KiwiSDR 无线电接收器网络**（非制裁、非特殊提款权）。用户已拍板**接入**：新增独立产物 `data/sdr_summary.json` + narrative 弱信号摄取（复用 `ingest_from_json_file` 管道），**GRV/regime/data_fetcher 零改动**，区域规则按天枢语义定稿（见 §4.1）；
   - **nuke = 6 站点辐射 CPM，A 层可 1:1 复刻**（data-review 从 crucix 源码挖出数据源 = SafeCast 公开 API，6 站点全 MATCH）→ **新增 `fetch_safecast_nuke.py` 复刻保留**（P1 并行上线）；B 层（台海地缘）由 `GPRC_TWN` + `defense_rss` 既有覆盖，无需新映射；
   - **air**：已有独立 `fetch_airtraffic_opensky`，crucix 侧自身已 fallback → 直接删除消费。
4. **摘除顺序（v1.2）**：Phase0/1 新增 fetcher 并行（GSCPI / SafeCast nuke / KiwiSDR sdr）→ Phase1 软依赖（D4/D5/D6）→ Phase2 gscpi 切换 + nuke 改源（D1/D2/D3'）→ Phase3 配置清理（D3 死映射 + prompt 残留）→ Phase4 停用（删 URL 配置 + 停容器，devops 主导）。

---

## 1. 代码实况复核（本轮精读确认）

| 依赖点 | 文件:行 | 实况确认 | 备注 |
|--------|---------|----------|------|
| D1 | `data_fetcher.py` L732-754 | GET `CRUCIX_REMOTE_URL` → `snapshot["_crucix"]={gscpi,nuke,sdr,air,markets.vix}`，失败静默 `{}` | 与既有 GPR 读取模式（L712-725，读 `fred_history/{id}.csv` 末行）**结构完全同构** |
| D2 | `regime_detector.py` L278-333 | `_crucix.gscpi.value > 1.5` → `signals+1`；`get_regime_info` 返回 `gscpi_warn/gscpi_value` | `max_signals=8` 含 GSCPI 1 位 |
| D3 | `narrative_processor.py` L66-70 + `config/source_dimension_map.yaml` L80-95 | 4 条 crucix_* 映射；**实库 0 条记录** | **死配置**（见 §3） |
| D3' | `run_macro_analysis.py` L2649-2682 | `_crucix` 的 gscpi/nuke/air → `crucix_context` 注入 LLM prompt | D1 的第二消费方，需一并改造 |
| D4 | `news_db.py` L7 + `scan_weak_signals.py` L1541 | crucix 新闻经 `insert_articles` 归档（url/content_hash 去重），source 保留原始来源名 | 摘除后 news.db 少一路聚合输入 |
| D5 | `scan_weak_signals.py` L1178-1212 / L1541 | `fetch_crucix_news(days=90)` → `scan_news` 7d/90d 关键词频率 | 与 GDELT 扫描（L897 起）**独立** |
| D6 | `fetch_climate_signals.py` L100-147 | `firms_fire.json` 为空 → crucix thermal（det/hc）兜底 | `fetch_firms.py` 已改 stream 分块下载（timeout=(15,300)），scheduler firms 0908 先于 climate 0910 |

**额外发现（D3'）**：`run_macro_analysis.py` 是 crucix 数据的**第三入口**（prompt 注入），既有依赖分析文档未单列，但归属 D1 消费面，方案中归入 Phase2 一并处理。

---

## 2. D1-D2 硬依赖摘除设计：gscpi

### 2.1 替代源实证（本轮验证）

| 项 | 结果 |
|----|------|
| FRED `series_id=GSCPI` | ❌ 不存在（API 返回 400 "series does not exist"；FRED search "supply chain pressure" 空结果） |
| NY Fed 官方 xlsx | ✅ `https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx` 直连 200，105,984 bytes，`application/vnd.ms-excel`；月度，更新于每月第 4 个工作日 10:00 ET；数据自 1997-09 |
| 语义一致性 | NY Fed GSCPI 单位 = 标准差（0=历史均值），与 `regime_detector` 阈值 1.5（">1.5 个标准差"）**同构**，阈值可沿用 |

> ⚠️ **联动 data-review（已闭合）**：data-review 实测 2026-08-10 时 crucix 侧 `gscpi=null`（已失效），NY Fed 官方最新 2026-07 = 0.805，2026 年 1-7 月数据完整 → **"替换"实为"恢复"**，无需与 crucix 数值对比；门禁重定义为"NY Fed 值正确性 + 阈值边界 + 无 regime 突变"（见 §6 P2）。

### 2.2 新 fetcher 设计：`fetch_gscpi.py`

**参照模式**：`fetch_fred_history.py`（BASE_DIR 探测 + `data/fred_history/{id}.csv` 落盘 + 增量更新），但 **FRED_API_KEY 不可用于 GSCPI**（FRED 无此序列），改用 NY Fed 官方 xlsx 直连。

```
接口：GET https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx
字段：xlsx 首列 = 月末日期（YYYY-MM-DD），次列 = GSCPI 值
频率：月度（每月第 4 个工作日发布，scheduler 建议 05:35 与 fred_fetch 同槽位或独立 05:32）
落盘：data/fred_history/GSCPI.csv，格式 date,value（与既有 GPR 系 CSV 完全一致，复用读取方）
解析：pandas.read_excel 或 openpyxl（requirements.txt 需确认 openpyxl 已在镜像内——或改用官方 gscpi_data.csv 变体）
失败行为：与 fetch_fred_history 一致——保留上次好数据，告警不中断
```

**读取接入（data_fetcher.py）**：完全复用现有 GPR 读取块（L712-725）模式：
```python
# 替换 L732-754 crucix 块中的 gscpi 部分：
_snap["GSCPI"] = {"name": "全球供应链压力指数", "date": <csv末行date>, "value": <csv末行value>}
```
不再向 `_crucix` 写入 gscpi。

**D2 接入（regime_detector.py）**：L291-296 改为 `indicators.get("GSCPI", {}).get("value")`，`get_regime_info` 的 `gscpi_warn/gscpi_value` 同源。`max_signals` 保持 8 不变。

**D3' 接入（run_macro_analysis.py）**：L2665-2670 的 gscpi 段改读 `indicators.get("GSCPI")`；nuke 段改读本地 `safecast_nuke.json`（保 `{site,anom,cpm,n}` 结构）；air 段删除（见 §4.3）。

### 2.3 设计要点
- **失败降级**：CSV 缺失/过期 → `snapshot["GSCPI"]` 缺省，D2 信号静默（与现状 `_crucix={}` 一致）。
- **新鲜度**：建议在 `fred_freshness.py` 增加 GSCPI 新鲜度探针（月度序列 tolerance ≥ 35 天），或沿用现有 `fred_freshness --all` 机制。

---

## 3. D3 叙事映射摘除：死配置实证与处理

### 3.1 实证（本轮新增，修订既有定性的关键）

- `forecast_tracker.db::narrative_chunks` 实查：仅 `aljazeera(251)/war_on_rocks(26)/defense_one(23)/rsshub_reuters(1)`，**crucix_* 为 0 条**。
- 全库 grep：`ingest_article` 唯一外部调用者 = `fetch_defense_rss.py`；`run_daily_narrative_processing`（L424-440）仅摄取 news.db + 5 个 JSON（sanctions/energy/disaster/hdx/climate）。
- 结论：DEFAULT_SOURCE_MAP 与 source_dimension_map.yaml 的 4 条 crucix_* 映射**无生产路径写入**，为"预留/残留"配置。

### 3.2 摘除动作（低风险）

1. 删 `narrative_processor.py` L67-70 四条 crucix_* 条目（含 DEFAULT_SOURCE_MAP）。
2. 删 `config/source_dimension_map.yaml` L80-95 四条 crucix_* 条目。
3. **GRV 影响 = 0**：GRV 各维度由 `geo_risk_vector.py` 直接读 GDELT/GPR/GED + JSON fetcher（sanctions_risk.json 等）计算，不经 narrative_chunks；叙事桶仅影响 LLM 叙事上下文（`get_narrative_context_for_trigger`），删后上下文少一类 source 而已。
4. 若未来要恢复"实时专信号 → 叙事桶"，在 Phase2 后以新 fetcher 产物（如 `snapshot["GSCPI"]`）建立 `gscpi`（非 crucix_*）映射即可——**架构上不依赖 crucix**。

---

## 4. nuke / sdr / air 替代方案评估（v1.2 修正：依据 data-review §8/§9 实证）

> 本节 v1.2 修订：**nuke A 层由"空输入"改为"SafeCast 复刻保留"**（data-review §9：挖出 crucix nuke 数据源 = SafeCast，6 站全 MATCH，round1"空输入"结论作废）；**sdr 由"删除"改为"用户已拍板接入"**（data-review §8 落地设计）。

### 4.1 sdr —— **已定案接入（用户拍板）：独立产物 + narrative 弱信号，GRV/regime/data_fetcher 零改动**

**实证结论（data-review §8）**：
- crucix `sdr` 键 = **KiwiSDR 全球软件定义无线电接收器网络**：`{"total":780, "online":780, "zones":[{region,count,receivers:[{name,lat,lon}]}]}`（8 区）。**不是 IMF 特殊提款权，也不是制裁相关**。
- 替代源 `rx.skywavelinux.com/kiwisdr_com.js` 实测容器内代理 200、839 台、含 gps/loc/grid 字段，可 1:1 重构 crucix 结构；JS 尾逗号需清洗（`re.sub(r',\s*\]', ']', ...)`）。
- FRED/World Bank 的 "SDR" 序列（TRESEG*/CCUSSP* 等）是外汇储备/汇率，**语义不相关，作废**。

**接入设计（正式定案，与 crucix 退场完全解耦）**：
1. **新增 `fetch_kiwisdr.py`**（data-review §8.1 设计）：输出 `data/sdr_summary.json` = `{fetched_at, source, total, online, offline, zones:[{region,count,receivers}], receivers:[全量明细], zones_rule}`。调度日频 06:00（或 6h 一次，KiwiSDR 目录日更 1-2 次）。出网：**直连优先 + 失败回退 OUTBOUND_PROXY**（复用 fetch_defense_rss 代理切换模式）。
2. **Narrative 弱信号摄取（消费方）**：`run_daily_narrative_processing` 的 `json_sources` 加 1 行 `(sdr_summary.json, "kiwisdr_sdr", "description")`；`source_dimension_map.yaml` 加 `kiwisdr_sdr → 按 zone→dimension 规则`。经 `ingest_from_json_file` 摄取为叙事文章 → 24h Z-score 密度突增监测（zone 掉线异常会触发 density flag）。**这是"无线电网络在线分布变化 → 地缘弱信号告警"的消费路径。**
3. **不做 GRV 数值维度**：8 区样本极小（Taiwan Strait 12 / Middle East 3 / Iran 2），语义是"信息空间可用性"非"冲突强度"，归一化噪声 > 信号，会污染 grv_history 基线。sdr 不进 `grv_latest.json`。
4. **`_crucix` 键与 data_fetcher 零改动**：sdr 不再住 `_crucix`，走独立 json 文件 + narrative 摄取，避免退场时二次拆除。**D3 的 `crucix_sdr → sanctions_risk` 死映射仍删**（sanctions_risk 叙事由 OpenSanctions JSON 供给，已存在）。

**zone→dimension 映射规则定稿（arch 定案，写死在 fetcher `zones_rule`）**：

| KiwiSDR zone | 天枢 primary_dimension | 依据 |
|---|---|---|
| Taiwan Strait | taiwan_strait | 同名映射，最高价值热点 |
| South China Sea | taiwan_strait | 西太同桶（GRV 无 scs 独立维度，avoid over-fragmentation） |
| Ukraine / Eastern Europe | russia_europe | 同名地缘桶 |
| Baltic Region | russia_europe | 与俄欧同桶（NATO 东翼） |
| Middle East | middle_east_energy | 同名地缘桶 |
| Iran | middle_east_energy | 中东能源风险核心 |
| Korean Peninsula | us_china_strategic | 朝核为中美战略博弈子集，GRV 无 kp 独立维度 |
| Sahel / West Africa | global_composite | 兜底维度（无专属热点） |

> ⚠️ **区域边界注意（data-review §8.4 实测）**：crucix 的 8 区边界未知，粗矩形复现不完全匹配（Middle East 3=3 ✓ / Taiwan Strait 6≠12 ✗）。**以本表 zone→dimension 规则为准**（天枢语义正确性优先），区域计数校准在 fetcher 验收时对齐 crucix 快照（total=780/online=780）即可，不必 1:1 复刻其 zone 内接收器归属。

### 4.2 nuke —— **v1.2：A 层（辐射读数）新增 SafeCast 复刻保留 + B 层（台海地缘）既有源覆盖**

**实证结论（data-review §9，v1.2 新增）**：
- 已从 crucix 源码挖出 nuke 数据源实现：`Crucix/apis/sources/safecast.mjs`，BASE=`https://api.safecast.org`，端点 `measurements.json?latitude=&longitude=&distance=&limit=10`。
- **数据源 = SafeCast**（全球公民辐射监测网，150M+ 读数，CC0 公共领域，无 key 无 auth），6 站点坐标表硬编码（zaporizhzhia 47.51/34.58 r100 / chernobyl 51.39/30.10 r50 / bushehr 28.83/50.89 r100 / yongbyon 39.80/125.75 r100 / fukushima 37.42/141.03 r50 / dimona 31.00/35.15 r100）。
- 计算逻辑：每站点拉半径内测量 → avg(CPM) → `anom = avgCPM > 100` → `n = readings.length`。**复刻结果 6 站全 MATCH**（Zaporizhzhia 38.28/n25、Chernobyl 123.96/anom、Fukushima 28.53/n25 等）。
- 容器内**直连 200**（无需代理）；`limit=10` 实际返回 25（解释 n=25）。
- **风险**：① 间歇性 TLS 证书错误（约 50% 报 `ERR_TLS_CERT_ALTNAME_INVALID`，多 IP 部分证书不匹配）→ 需 **≥4 次重试 + 退避**；② 数据是**历史归档均值非实时流**（captured_at：Zaporizhzhia 2023-06/Chernobyl 2023-07/Fukushima 2016）→ 输出必须保留 `latest_captured_at` 避免误导。

**接入设计（v1.2 正式定案）**：
1. **新增 `fetch_safecast_nuke.py`**（~120 行，requests 即可）：
   - 6 站点坐标表照抄（上表）；URL 模板同 crucix。
   - 输出：`data/safecast_nuke.json` = `{fetched_at, source, sites:[{site, key, avgCPM, n, anom, latest_captured_at}]}`。
   - 调度：15-60 分钟（对齐 crucix 15min sweep；或与 scheduler 低频批合并）。
   - 出网：直连优先 + 失败回退 OUTBOUND_PROXY（防御性，实测直连通）。
   - **重试 ≥4 次 + 退避**（应对 TLS 间歇证书错误；data-review 复刻脚本 5 重试+1.5s 退避全成功）。
   - **必留 `latest_captured_at`**（历史归档均值，非实时流，防误导下游）。
2. **A 层消费恢复（原空输入作废）**：**新增独立键 `snapshot["_safecast"]["nuke"]`（data_fetcher 读本地 `safecast_nuke.json`），run_macro 的 nuke prompt 段改读 `_safecast.nuke`**（保 `{site,anom,cpm,n}` 结构），核辐射异常告警**保留**。与 `_crucix` 完全解耦（P3 删 `_crucix` 时无二次拆除）。注意 Chernobyl anom=true（123.96，2023-07 历史）为长期背景而非突发，下游解读需知悉。
3. **B 层（台海地缘）不变**：`taiwan_strait` 已由 GPRC_TWN（GRV 数值层 L431）+ defense_rss（叙事层）双重覆盖，`crucix_nuke → taiwan_strait` 死映射仍删（P3），不新建 nuke 代理映射。

### 4.3 air —— **推荐：删除消费（已有独立 OpenSky 主源）**

- 实证：crucix 侧 air 已自身 fallback（`airMeta.fallback=true, liveTotal=0`，用 06-06 历史文件）。
- 天枢已有独立 `fetch_airtraffic_opensky.py`（scheduler 06:28 日频）→ 已充分独立。
- 语义差：OpenSky 为全球航班统计，crucix air 为区域架次聚合，不直接等价，但 air 无 GRV 维度。
- **决策**：删除 `run_macro_analysis.py` L2674-2676 air prompt 段 + data_fetcher 注入 + 死映射。如需区域航空活动高频信号，另立 OpenSky 区域过滤增强项（非退场前置）。

---

## 5. D4-D6 软依赖摘除

### 5.1 D5 新闻频率分析降级评估（`scan_weak_signals.py`）

- 现状：`articles = fetch_crucix_news(days=90) + fetch_rss_news()`（L1541-1543），`scan_news` 消费全部文章做 7d/90d 关键词频率。
- 摘除后：`articles = fetch_rss_news()`（RSS 三源独立）——news.db 归档少一路、scan_news 样本减量。
- **降级评估**：关键词频率告警（credit/recession/inflation/geopolitics 等）在 RSS 源仍可运行；crucix 聚合 90 天历史使基线更稳，摘除后 7d/90d 比值在 RSS 冷启动期（<90 天数据）可能不触发告警。建议：
  - 保留 `scan_news` 算法不变，仅改输入源；
  - cold-start 保护：`counts_90d==0` 时已跳过（L1252 `if c90 == 0: continue`），天然安全；
  - 可选增强：将 `fetch_rss_news` 结果每日落盘 90 天滚动窗口（维护 `data/rss_news_history.json`），补回基线稳定性（独立增强项，非退场前置）。

### 5.2 D4 news_db 去 crucix 归档

- 摘 `fetch_crucix_news` 后 news_db 自然不再接收 crucix 聚合文章（source 保留原始来源名，无 crucix 专属标记，**无需数据清理**——历史 31,039 篇保留，来源名本身是"第一财经/NYT/BBC"等，非 crucix）。
- `news_db.py` 仅注释/文档提及 crucix，无强制引用；确认 L7 docstring 更新即可。

### 5.3 D6 climate thermal 兜底删除（`fetch_climate_signals.py`）

- 删 `_fetch_firms_summary` 路径 2（crucix thermal 分支，L118-147），保留路径 1（`firms_fire.json`）。
- **前置依赖**：`fetch_firms.py` 直连下载可靠性。实证：已改 stream 分块下载 + `timeout=(15,300)`；scheduler `firms 0908 → climate 0910` 顺序正确（firms 先落盘）。
- **风险**：若 FIRMS 直连失败且无 crucix 兜底，climate_signals.json 的 firms 部分恒 0 → GRV climate_risk 仍由 ONI 供给（`_fetch_oni` 独立），firms 仅影响火点细节分。可接受。
- **建议加固（Phase1 一并做）**：`fetch_firms.py` 失败时在 `firms_fire.json` 写入 `fetched_at + total_hotspots:0` 并留 `_PROXIES` 回退（当前直连异常仅 `except: 回退代理`，代理也失败则 raise——确认 main 捕获后是否留 0 文件）。

---

## 6. 摘除顺序与风险矩阵

### 阶段划分

| Phase | 内容 | 涉及文件 | 风险 | 回滚点 | 验证点 |
|-------|------|----------|------|--------|--------|
| **P0 准备** | 新增 `fetch_gscpi.py` + 落盘 GSCPI.csv（**不删任何 crucix 逻辑**，双轨并存） | 新增文件；requirements.txt（如缺 openpyxl） | 🟢 极低（纯新增） | 删除新文件即可 | GSCPI.csv 有值；`fred_freshness` 不报新错 |
| **P1 软依赖 + 专信号并行上线** | D6 删 crucix thermal 兜底；D5/D4 摘 `fetch_crucix_news`（scan_news 改 RSS-only）；**新增 `fetch_safecast_nuke.py`（复刻 nuke A 层）**；**新增 `fetch_kiwisdr.py`（sdr 接入，独立产物）** | fetch_climate_signals.py / scan_weak_signals.py / 新增 fetch_safecast_nuke.py / 新增 fetch_kiwisdr.py | 🟢 低（降级路径 + 纯新增） | git revert 单文件 | climate_signals.json 正常（ONI+firms）；scan.log 无 crucix 拉取、告警仍触发；safecast_nuke.json 6 站点与 crucix 快照 MATCH；sdr_summary.json zones 与 crucix 快照对齐（total=780） |
| **P2 gscpi 切换** | D1 改读 GSCPI.csv；D2 改 `indicators["GSCPI"]`；D3' prompt gscpi 段改源、air 段删除、nuke 段改读本地 `safecast_nuke.json` | data_fetcher.py / regime_detector.py / run_macro_analysis.py | 🟡 中（门禁见右侧验证点） | 保留 `_crucix` 读取代码 1 个版本周期 | **门禁（v1.1 修订）**：① GSCPI.csv 尾行 = 2026-07-31,0.805（与 NY Fed 官方一致）；② `snapshot["GSCPI"]` 形态正确（{name,date,value}）；③ 阈值边界：gscpi_warn 在 2026-05（1.81>1.5 触发）与 2026-07（0.805 不触发）行为正确；④ 观察 1-2 周无 regime 突变 |
| **P3 配置清理** | 删 D3 死映射（py+yaml，含 crucix_nuke/crucix_sdr/crucix_air/crucix_gscpi）；删 `_crucix` 全量残留（SKIP_DISPLAY_KEYS/日志清理）；删 air 消费（data_fetcher 注入、run_macro prompt 段、regime 无引用） | narrative_processor.py / source_dimension_map.yaml / run_macro_analysis.py / data_fetcher.py | 🟢 低（死配置+展示清理） | git revert | 全库 grep `crucix` 仅剩文档引用；sdr/nuke 已有本地替代（safecast_nuke.json / sdr_summary.json） |
| **P4 停用** | 删 `optim_config.py CRUCIX_REMOTE_URL`；停 crucix 容器；更新 deploy 与 docs | optim_config.py / docker-compose / docs | 🟡 中（运维侧，devops 主导） | 容器重启 + 恢复 URL 配置 | 天枢 24h 全链路无 crucix 错误；news.db 正常增长；GRV 正常 |

### 关键风险 TOP3

1. **gscpi 阈值边界**（P2，🟡）：crucix 侧 gscpi 已 null（data-review 实测），P2 为"恢复信号"而非"切换数值"，无对比风险；但阈值 1.5 与 NY Fed 官方值（2026-07=0.805，2026-05=1.81）的触发边界需用历史回放验证。**门禁**：阈值边界 + 无 regime 突变（见 §6 P2 验证点）。
2. **SafeCast TLS 间歇证书错误**（P1，🟡）：api.safecast.org 解析到多 IP 部分证书不匹配，约 50% 请求报 `ERR_TLS_CERT_ALTNAME_INVALID`。**缓解**：`fetch_safecast_nuke.py` 重试 ≥4 次 + 退避（data-review 复刻脚本 5 重试+1.5s 全成功）；直连失败回退 OUTBOUND_PROXY。
3. **D3' prompt 注入丢失**（P2，🟢）：air 段删除后 LLM 少一类实时信号；nuke 段改读本地文件（保信号）。缓解：prompt 系统性说明"专信号类已由 GDELT/GPR/defense_rss + 本地 fetcher 覆盖"。
4. **D5 新闻频率冷启动**（P1，🟢→🟡）：RSS-only 后 7d/90d 基线在冷启动期偏弱。缓解：RSS 历史滚动落盘增强项（data-review 实测 RSS 8 路由可达，覆盖充分）。

---

## 7. 架构决策记录（ADR）

### ADR-01：GSCPI 替代源用 NY Fed 官方 xlsx，而非 FRED
- **背景**：D2 需要 gscpi 实时值；直觉优先考虑 FRED（已有 API key 与 fetcher 模式）。
- **决策**：实测 FRED `series_id=GSCPI` 不存在（400），FRED search 无 "supply chain pressure"；NY Fed 官方 xlsx 直连 200 且月度更新。落盘 `data/fred_history/GSCPI.csv` 复用 GPR 系读取模式。
- **后果**：新增 xlsx 解析依赖（pandas.openpyxl）与一个新下载源；阈值语义（标准差）与 crucix 推断一致，需 data-review 实证数值对齐。

### ADR-02：D3 crucix_* 叙事映射按"死配置"删除，而非改源
- **背景**：既有分析将 D3 定性为硬依赖（4 映射驱动 GRV 叙事桶）。
- **决策**：实库 `narrative_chunks` 0 条 crucix_* 记录、无任何写入路径，定性修正为**死配置**。直接删除（py+yaml），不设计替代映射。
- **后果**：D3 摘除成本从"重验 GRV 一致性"降为"删配置零影响"；GRV 不受影响。

### ADR-03：nuke 拆两层——A 层辐射读数由 SafeCast 复刻保留，B 层台海地缘由既有源覆盖（v1.2 修订）
- **背景**：crucix nuke 为 6 站点辐射 CPM 数组（Zaporizhzhia/Chernobyl 等），映射 taiwan_strait 叙事维度。
- **v1.1 决策（已作废）**：A 层"无低成本开源实时等价 → 接受空输入"——**该结论被 data-review §9 实证推翻**（v1.0/v1.1 推断修正声明：当时未挖出 crucix 数据源，误判无开源源）。
- **v1.2 决策**：A 层（辐射传感器读数）**新增 `fetch_safecast_nuke.py` 复刻保留**——数据源 = SafeCast 公开 API（CC0 无 key），6 站全 MATCH，P1 并行上线；B 层（台海地缘代理）**不新建 nuke 代理映射**——`taiwan_strait` 已由 GPRC_TWN（GRV 数值层，L431）+ defense_rss（叙事层，narrative_chunks 已有 300 条）双重独立覆盖。
- **后果**：核辐射异常告警**保留**（需知悉数据为历史归档均值，Chernobyl 123.96 为 2023-07 长期背景非突发）；台海地缘维度不受影响。B 层如需"核态势专叙事源"，评估 GPRC_TWN 摄入（独立增强项，非退场前置）。

### ADR-04：sdr 接入定案——独立产物 + narrative 弱信号，不与 `_crucix` 耦合（用户已拍板）
- **背景**：data-review 实测 crucix sdr = **KiwiSDR 无线电接收器网络**（`{total,online,zones}`），非制裁、非 IMF 特殊提款权；替代源 `rx.skywavelinux.com/kiwisdr_com.js` 可达（839 台）。用户对 sdr 有兴趣，主动要求接入。
- **v1.1 决策（已作废）**："sdr 无活跃消费者 → 删除全部消费路径，不引入 fetch_kiwisdr"——用户拍板后撤销，改为接入。
- **v1.2 决策（正式定案）**：**新增独立产物 `data/sdr_summary.json` + narrative 弱信号摄取**（zone→dimension 映射见 §4.1 表），**GRV/regime/data_fetcher 零改动**，与 crucix 退场完全解耦（不依赖 `_crucix` 键）。D3 的 `crucix_sdr → sanctions_risk` 死映射仍删（sanctions_risk 由 OpenSanctions 独立供给）。
- **后果**：sdr 从"注入即弃"变为"有消费方的地缘弱信号"（zone 掉线异常 → density flag 告警）；不污染 GRV 数值基线。
- **原方案修正声明**：v1.0 中"sdr↔制裁/opensanctions 关联"为**推断**（基于键名 crucix_sdr→sanctions_risk 的映射猜测），经 data-review 实证为 KiwiSDR 后已推翻。

### ADR-05：air 删除，OpenSky 语义不等价不强行顶替
- **背景**：crucix air 为区域架次聚合（Taiwan Strait 等），已自身 fallback（liveTotal=0）；OpenSky 为全球航班统计。
- **决策**：删除 crucix air 消费路径；不将 OpenSky 声明为等价替代（避免数据语义漂移污染 prompt）。
- **后果**：prompt 少区域航空信息；GRV 无 air 维度，无影响。台海活动如需高频信号，另立 OpenSky 区域过滤增强项。

### ADR-06：D6 兜底删除前先加固 fetch_firms 直连
- **背景**：D6 依赖 firms_fire.json 直连产物；crucix thermal 为兜底。
- **决策**：Phase1 先确认/加固 `fetch_firms.py` 失败时落 0 文件 + 代理回退，再删 climate 兜底分支。
- **后果**：climate_signals 火点字段在 FIRMS 故障期恒 0（有 ONI 主信号兜底，GRV climate_risk 不中断）；消除对 crucix 的隐性运行期依赖。

### ADR-07：分阶段双轨并存，P2 前不删 `_crucix` 读取
- **背景**：gscpi 阈值一致性未实证，直接切源有 regime 突变风险。
- **决策**：P0-P1 保留 crucix 读取逻辑与 `_crucix` 键，新 fetcher 并行产出；P2 经数据侧实证对齐后再切换；P3 才清理残留。
- **后果**：每个 Phase 可独立回滚；crucix 停用前最长双轨运行周期 = P0→P2 验证期。
- **v1.1 修订**：data-review 实测 crucix 侧 `gscpi=null`（已失效）→ P2 门禁不再要求"crucix↔NYFed 数值对比"，改为"NY Fed 值正确性 + 阈值边界 + 无 regime 突变"（见 §6 P2 验证点），双轨窗口可缩短。

### ADR-08：ingest_from_news_db 的 summary 列 bug 登记为独立待修项，不随 D3 删除
- **背景**：qa-review 发现 `narrative_processor.ingest_from_news_db`（L217 `SELECT source,title,summary,published_at FROM articles`）因 **articles 表无 summary 列**（实查 schema：`id,url,content_hash,title,source,published_at,ingested_at,country_tag,ingest_ctx_id,pub_ctx_id`）恒报 `no such column: summary`。arch 复核确认：**该 bug 与 D3 死配置完全独立**（D3 是 crucix 映射无数据流；此 bug 是 news.db → narrative 摄取通道自身失效）。
- **决策**：登记为独立待修项（修复 = 改 `summary` 为现有列或 `COALESCE`），**不并入 D3 删除动作**，避免"死配置清理"与"功能修复"混在单次变更中。
- **后果**：当前 narrative_chunks 仅含 defense_rss 三源（aljazeera/defense_one/war_on_rocks）+ rsshub_reuters 1 条，news.db 新闻（31,039 篇）**从未进入叙事桶**；修复后可恢复新闻 → 叙事桶摄取，需 qa-review 补回归用例（news.db → narrative_chunks 链路）。

### ADR-09：nuke A 层改用 SafeCast 公开 API 复刻，替代"空输入"方案
- **背景**：round1 论证认定 nuke（6 站点辐射 CPM）无低成本开源等价 → 空输入 + 降级登记。data-review 深入 crucix 容器挖出实现（`Crucix/apis/sources/safecast.mjs`）：数据源 = **SafeCast**（`api.safecast.org/measurements.json`，CC0 公共领域，无 key 无 auth），6 站点坐标 + 计算逻辑（avg CPM / anom>100 / n）可完整复刻，实测 **6 站全 MATCH**。
- **决策**：新增 `fetch_safecast_nuke.py`（P1 与 fetch_gscpi 同类并行），输出 `data/safecast_nuke.json`，下游（data_fetcher/run_macro prompt）改读本地文件保 `{site,anom,cpm,n}` 结构；空输入方案作废。**技术要点**：① TLS 间歇证书错误 → 重试 ≥4 次 + 退避；② 数据为历史归档均值非实时流 → 必留 `latest_captured_at`；③ 直连优先 + OUTBOUND_PROXY 回退（防御性）。
- **后果**：核辐射异常告警保留（比空输入方案优）；新增 ~120 行 fetcher + 1 处读取改造；需 qa-review 补"6 站点与 crucix 快照 MATCH"验收基线。Chernobyl anom=true 为历史背景，下游解读需知悉。

### ADR-10：sdr 区域规则以天枢语义为准定稿（zone→dimension），不追求 1:1 复刻 crucix zone 归属
- **背景**：data-review 实测 crucix 8 区边界未知（粗矩形复现：Middle East 3=3 ✓ / Taiwan Strait 6≠12 ✗），无法精确复刻 crucix 的 zone 内接收器归属。
- **决策**：**以 arch 定稿的 zone→dimension 映射为准**（§4.1 表：Taiwan Strait/South China Sea→taiwan_strait，Ukraine/Baltic→russia_europe，Middle East/Iran→middle_east_energy，Korean Peninsula→us_china_strategic，Sahel→global_composite），规则写死在 `fetch_kiwisdr.py` 的 `zones_rule`（loc 国家关键词 + gps bbox 双层判定）；验收基线 = 全局 total/online 对齐（780/839），不要求 zone 内计数与 crucix 一致。
- **后果**：区域计数与 crucix 有偏差（可接受，天枢语义正确性优先）；`zones_rule` 字段保留判定规则供追溯与后续校准。

---

## 8. 交付清单与依赖

### 本方案产出的代码改动（待实施，本次未动）
| 新增/修改 | 文件 | 归属 |
|-----------|------|------|
| 新增 | `fetch_gscpi.py` | P0 |
| 新增 | `fetch_safecast_nuke.py`（6 站点坐标 + avgCPM/anom/n + 重试≥4 次 + latest_captured_at） | P1 |
| 新增 | `fetch_kiwisdr.py`（JS 容错解析 + zones_rule 区域判定 + 直连/代理回退） | P1 |
| 修改 | `data_fetcher.py`（L732-754 → GSCPI 读取 + 新增 `_safecast.nuke` 读本地文件；P3 清 `_crucix`） | P2/P3 |
| 修改 | `regime_detector.py`（L291-296 gscpi 改源；L331-332 gscpi_warn） | P2 |
| 修改 | `run_macro_analysis.py`（L2665-2682 gscpi 改源、air 段删、nuke 段改读本地 `safecast_nuke.json`） | P2/P3 |
| 修改 | `scan_weak_signals.py`（L1178-1212 fetch_crucix_news 删、L1541 改 RSS-only） | P1 |
| 修改 | `fetch_climate_signals.py`（L118-147 兜底删） | P1 |
| 修改 | `narrative_processor.py` / `source_dimension_map.yaml`（4 条 crucix 死映射删 + 新增 `kiwisdr_sdr` 弱信号映射） | P3 / P1 |
| 修改 | `narrative_processor.py` `json_sources` 加 `sdr_summary.json → kiwisdr_sdr` | P1 |
| 修改 | `optim_config.py`（L110 CRUCIX_REMOTE_URL 删）+ deploy/docker-compose | P4 |
| 修改 | `news_db.py` docstring / `fred_freshness.py`（GSCPI 探针） | P1/P4 |
| **独立待修** | `narrative_processor.py` L217 `summary` 列 bug（articles 表无此列，恒报错；修复 = 改列名或 COALESCE） | 独立项（ADR-08） |

### 跨角色联动
- **data-review**：① 实证 crucix gscpi.value ↔ NY Fed 官方值数值/相位一致性（P2 门禁）；② 确认 RSS 三源 90 天历史可得性（P1 冷启动评估）；③ nuke SafeCast 复刻脚本原型（6 站 MATCH 已实证，L9）；④ KiwiSDR fetcher 解析/区域规则实现细节（§8）。
- **qa-review**：P1 新增 fetcher 验收基线（safecast_nuke.json 6 站 MATCH / sdr_summary.json zones 对齐 total=780）；P2 回归门禁（regime 稳定性对比、GSCPI 新鲜度探针）；P4 停用后全链路健康检查用例。
- **devops-review**：P4 容器停用与回滚脚本；部署清单同步（deploy.sh/docker-compose 去 crucix 引用）；新增 2 个 fetcher 的 scheduler 注册与日志轮转。

---

*文档结束。arch-review 已完成只读核实与设计，未修改任何运行代码。*
