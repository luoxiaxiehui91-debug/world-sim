# 开阳第二批地图深化 · Lead 汇总裁决（team-lead）

> 作者：team-lead（大湾区靓仔）｜日期：2026-08-11｜状态：**论证闭合，待用户确认进入实施**
> 依据：data-map `docs/arg-map-data-2026-08-11.md` + arch-map `docs/arg-map-arch-2026-08-11.md`（本地副本同源）+ qa-map `docs/arg-map-qa-2026-08-11.md`（本地副本同源）
> 三份文档均为**只读论证**，未改动任何代码/数据。本文件是三方交叉核对 + 裁决，是实施排期的唯一依据。

---

## 1. 三方证据链闭合结论

| 结论 | data-map | arch-map | qa-map | 一致性 |
|------|----------|----------|--------|:---:|
| `gdelt_geo_cache.json` 全 repo 无任何写入方（NER 路径是断链非缺文件） | 全 repo grep 无写入逻辑 | `geo_risk_vector.py` 0 引用，注释是遗留声称 | B12 文件不存在 + news_geo_feed 依赖它 | ✅ 三方一致 |
| jsonl 是 GDELT 地理数据唯一活数据源 | 124,244 行/57.9MB/I15 活跃 | 124,499 行/state 连续 820 slots 无失败 | 124,499 行基线（差 255=一个槽位增量，合理） | ✅ 三方一致 |
| jsonl 缺 CAMEO EventCode（`type` 实为 ActionGeo_Type 地理精度 1-4） | 发现无 title（source_url 代替） | 0/124,499 行有 root_code，需补字段 | RSK-1 = **最大阻塞**，须先补 EventCode | ✅ 三方一致 |
| intensity 为 Goldstein(-10~10)，非契约 0-100 | min -10/max +10 全覆盖 | §4.4 归一公式已定稿 | B5 实测 + AC-M1-04 验收分布 | ✅ 三方一致 |
| 点数远超前端 2000 护栏，feed 必须过滤 | 24h≈1.1~1.5 万条 | 过滤实测：24h 排除 type=1 → 12,286 → mentions≥15 → **436 点** | 24h=14,534 / 7d=118,461，须时间窗+聚合 | ✅ 三方一致（arch 用 mentions 阈值达成，qa 聚合作防爆兜底） |
| 旧 `news_geo_feed.py` 空转链必须退役（单一写者） | 07:15 写空 articles 覆写 | ADR-map-1 废弃空转链 | RSK-7 每日闪断，收敛单一写者 | ✅ 三方一致 |

## 2. arch-map 已拍板 qa-map 的 6 个未决问题

| qa 未决项 | arch 裁决 | 采纳 |
|-----------|-----------|:---:|
| 1. 调度口径（I15 vs 0715） | ADR-map-3：**I15**，A1 并入 `run_incremental` 末尾，scheduler 不改 | ✅ |
| 2. EventCode 持久化 | ADR-map-2：**本轮补** `event_code`/`root_code`，旧行不回填（过渡期 unknown） | ✅ |
| 3. intensity 归一公式 | §4.4：`0.6*g + 0.4*m`（g=Goldstein 烈度 0..1，m=log1p mentions 广度）→ 1-100 整数 | ✅ |
| 4. 聚合策略 | §4.2 过滤链第 7 步：默认档 436 点无需聚合，聚合作 env 开关防爆兜底 | ✅ |
| 5. M-2/M-3 范围 | ADR-map-6：M-2 纯前端已实现；ADR-map-5：M-3 复用 `event_type='conflict'`（root 15/18/19/20）零新 feed | ✅ |
| 6. 旧 feed 去留 | ADR-map-1 + §4.1：**停止调度退役**，scheduler 注释同步更正 | ✅ |

## 3. Lead 裁决（三方分歧点）

### 裁决 1：输出文件名——直接改 `news_geo.json`，不建 `news_geo_latest.json`（data 建议不采纳）

data-map 建议"fetch 侧落 news_geo_latest.json（24h 过滤 + title 注入）供开阳直读"。
**裁决**：采纳 arch 的落位——直接写现有 `news_geo.json`（`events[]` 结构）。理由：
- 开阳 `dataSources.ts:88-93` 已指向 `news_geo.json`，新文件需改前端 path + nginx 挂载 + 状态条拾取，纯增成本；
- 契约 §2.7 顶层即 `{schema_version, updated, events[]}`，`NewsGeoRaw`/`newsGeoAdapter` 双结构已兼容 events 分支，**零适配改动**；
- data 的核心关切（24h 过滤 + 字段注入）在 arch §4.2 过滤链 + §4.3 字段映射中已完整覆盖。

### 裁决 2：title 注入——不落地（无数据源），用 `full_name` 作 `location_name`

data 发现 jsonl 无 title（仅 source_url）。arch 明确：**GDELT 事件表本身无 headline 字段**，契约 §2.7 的 `location_name` 为可选。
**裁决**：接受 arch 方案——`location_name` = `full_name`（非空率 100% 实测），`source_url` 进 tooltip/点击跳转（HTML 转义后）。title 注入需要抓取 URL 标题，对 124k 行不现实且引入外部请求，**不做**。契约已知限制如实声明（arch 已做）。

### 裁决 3：`event_type` 过渡期输出域——arch 的 'unknown' 与 qa AC-M1-05 冲突，折中裁定

**冲突**：arch §4.3 规定缺失 root_code → `'unknown'`；qa AC-M1-05/G-M4 要求输出域 ⊆ 四枚举（unknown 不在内），会 FAIL。
**裁定**：接受 arch 的 unknown 兜底，但**微调验收口径**——AC-M1-05 放宽为：
- 输出域 ⊆ `{conflict, protest, disaster, political, unknown}`；
- **部署 48h 后（窗口滑动自然换新）`unknown` 比例 < 5%**；48h 内过渡期 unknown 允许（新行已带 root_code，旧行随 24h 窗口滑出）。
- 理由：jsonl 只累积 10 天，补字段部署后 24h 窗口内旧行比例随时间递减，48h 后理论为 0；不做 jsonl 一次性重建（省代理流量，RSK-9 已评估）。
- **同步动作**：qa-map 需在实施阶段把 AC-M1-05 断言改为上述口径（含 unknown 白名单 + 48h 阈值）。

### 裁决 4：clusters 复活——本轮不复活，删除产物 + 更正注释（data 顺带建议降级）

data 建议"顺带 scheduler 追加 --aggregate 复活 clusters"。arch 列为顺带项（R8）。
**裁决**：本轮**不复活**。`news_geo_clusters.json` 停更 08-01 且无消费方；复活 = 每 I15 多一次全量聚合，收益为零。动作 = **删除该产物 + 更正 scheduler.py:64 注释**（当前注释声称"产出 jsonl + clusters"与事实不符，误导接手者）。若未来地图要聚类视图，再从 `--aggregate` 一行复活。

## 4. 最终实施方案（实施阶段依据，两步两 commit）

### 后端（天枢，1 commit）
1. `fetch_gdelt_geo.py` `_map_event` 补 `event_code`(col 26) + `root_code`(col 28)，schema_version 不变（向后兼容新增字段）；
2. `run_incremental` 末尾追加 news_geo.json 生成段：§4.2 过滤链（坐标有效 → 排除 type∈{0,1} → 24h 时间窗[seen_slot/fetched_at 兜底] → mentions≥15 → root_code 映射四枚举 → MAX_EVENTS=1800 护栏 → 可选聚合 env 开关）+ §4.3 字段映射 + §4.4 intensity 公式 + **HTML 转义**（location_name/source_url，XSS 双保险之一）；
3. 原子写：tmp + os.replace（沿用现有模式），失败保留旧文件；
4. `news_geo_feed.py` 停止调度（scheduler.py:98），更正 scheduler.py:64 注释；删除 news_geo_clusters.json。
5. **scheduler.py 改动须 `docker restart macro-scan-macro-scan-1` 生效**（项目红线）；天枢热挂载 `*.py` 改动即生效，但 scheduler 注册表变更必须重启。

### 前端（开阳，1 commit）
1. `dataSources.ts:88-93` news_geo 补 `refreshMs: 60_000`（I15 轮询，与 market_quotes 同模式）；
2. `newsGeoAdapter`：`event_type==='conflict'` 点归入已登记 `conflict` 类别色（layerCategories.ts:112），其余走 `news`；
3. 输入消毒：`location_name`/`theme`/`rawMetric` 消毒（XSS 双保险之二）；
4. 可选：`pointTooltipHtml` 转义。

### 验收（qa-map 牵头，按 G-M1~G-M5）
- 前置：部署后先跑基线重采（qa §0），再按门禁逐条过；
- G-M1（连续 3 天 100≤N≤2000）、G-M2（波动 ±50%）、G-M3（浏览器截图）、G-M4（契约字段 7 断言）、G-M5（updated 当日）；
- **注意**：G-M1 的"连续 3 天"从部署 48h 后起算（裁决 3 的过渡期）；AC-M1-05 按裁决 3 微调后执行；
- 前端 `npm test`（297+ 用例基线全绿，AC-R-05）。

## 5. 遗留 OPEN 项（不阻塞实施）

| # | 项 | 当前倾向 | 解决时机 |
|---|----|----------|----------|
| O-1 | jsonl 一次性重建（补 EventCode 后重拉全量，即时消灭 unknown） | 不做（省代理流量），窗口滑动自然换新 | 若 48h 后 unknown>5% 再评估 |
| O-2 | 7d 趋势档阈值调优（env：WINDOW=168 / MIN_MENTIONS=30 或聚合） | 默认 24h 档先上线，7d 档观察期调优 | 上线观察后 |
| O-3 | 中文地理新闻源（路线 C 的激活条件） | 不做，未来有中文地理源再评估 | 未来 |

## 6. 风险 Top3（实施时随身）

1. **XSS**（arch R1，H 级）：后端转义 + 前端消毒双保险，缺一不可——验收含 tooltip 注入用例；
2. **断供空覆写**（qa RSK-5）：失败保留旧文件逻辑必须有，禁止空 events[] 覆写——验收含断供模拟；
3. **scheduler 重启生效**（项目红线）：scheduler.py 改动后必须 docker restart，否则调度不生效且静默——部署清单第一条。

---
*本文件为 lead 汇总裁决，三方论证文档为过程证据；实施阶段以本文件为排期依据。*
