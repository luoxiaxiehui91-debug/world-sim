# 开阳 M-1 news_geo 事件图层 — 过渡期验收报告（部署后 0-48h）

> **作者**：qa-map（世界推演系统 QA 负责人）
> **日期**：2026-08-11（部署生效日，06:45 首批带码增量进入）
> **对象**：前端 commit `a86fbbe`（v1.10.0：`dataSources.ts` refreshMs:60_000 + `newsGeoAdapter` conflict→conflict 类别色 + `sanitizeText` 消毒 + `mapData.ts` `pointTooltipHtml` 统一 HTML 转义）+ 天枢路线 A（`fetch_gdelt_geo.py` 补 `event_code/root_code` 并派生 `news_geo.json`）
> **依据**：`docs/arg-map-qa-2026-08-11.md`（验收标准）+ `docs/qa-scripts/verify_data.py` / `verify_front.sh`（可执行断言）+ 前端源码审查（`newsGeoAdapter.ts` / `mapData.ts` / `layerCategories.ts` / `dataSources.ts`）
> **阶段**：**48h 过渡期**（部署满 48h 前，`unknown` 允许占位；满 48h 后按 `--enforce-unknown` 硬判 `unknown<5%`）。本报告不替代最终门禁判定，只固化过渡期状态与后续判定计划。

---

## 0. 结论摘要

| 区块 | 结果 |
|---|---|
| 数据层自动断言（verify_data.py） | **PASS=16 FAIL=0**（AC-M1-01~12 + AC-R-03/04，过渡期口径） |
| 前端单测（verify_front.sh → npm test） | **14 files / 311 tests 全绿**（含 newsGeoAdapter 33 例 + mapData 38 例 + layerCategories 31 例） |
| XSS 消毒专项（聚焦跑 5 例） | **全 PASS**（`<img onerror>` 类 payload 转义验证） |
| conflict 类别色映射（代码审查） | 通过（`newsGeoAdapter.ts:192` + `layerCategories.ts:112`，独立显隐） |
| 视觉重构回归（a63bd65 v1.10.1） | 代码级+部署级全确认（§4.5）；观感项由主理人复核（§7 人工-8~12） |
| 三项修复回归（b5852d8 v1.10.2） | 代码级+部署级全确认（§4.6）；交互项由主理人复核（§7 人工-13~15） |
| 参数微调回归（eefd2da v1.10.3） | 代码级+部署级全确认（§4.7）；观感对比由主理人复核（§7 人工-16~17） |
| G-M1/G-M2 连续观测 | **day 1/3**（2026-08-11 N=527 已落盘 qa-history.json） |
| 浏览器人工项（AC-F-01~05 / G-M3 / 视觉回归 / 三项修复 / 参数微调） | 未自动判定，**由主理人浏览器复核**（§7 清单，共 17 项） |
| 48h 判定点 | 估 **2026-08-13 06:35** 起跑 `verify_data.py --gate --enforce-unknown` |

**过渡期关键状态**：`event_type` 分布 `{'unknown': 516, 'political': 8, 'conflict': 3}`，unknown=**97.91%** —— 属 48h 过渡期**预期**（旧 10 天 jsonl 无 EventCode 均映射 unknown，随窗口滑动自然下降），不以 FAIL 计。带码增量 182 行已进入（516→527），四枚举映射链已产出 `political`/`conflict` 实证。

---

## 1. 数据层自动断言（verify_data.py --gate，06:54 重跑）

| 项 | 结果 | 关键数值 |
|---|---|---|
| AC-M1-01 非空与结构 | PASS | events=527（须 100≤N≤2000） |
| AC-M1-02 必填字段 | PASS | 缺字段=0 |
| AC-M1-03 坐标 | PASS | 越界=0 超4位小数=0 |
| AC-M1-04 intensity | PASS | min=28 max=100 P50=53 **P90=89** P99=96 |
| AC-M1-05 event_type 域 | PASS（过渡期） | 分布 `{'unknown':516,'political':8,'conflict':3}`；unknown=97.91%（域校验过；48h 后须 <5%） |
| AC-M1-06 country | PASS | 缺失率=0.00%（<1%） |
| AC-M1-07 id 唯一 | PASS | 527/527 |
| AC-M1-08 schema_version | PASS | `"1.0"` + updated `2026-08-11T06:45:34+08:00` |
| AC-M1-09 updated 新鲜度 | PASS | 距采样 0.15h（≤36h 口径） |
| AC-M1-10 时间窗 | PASS | 窗口外=0（7d 口径），event_date 缺失=0 |
| AC-M1-11 聚合参考 | PASS（参考） | 527 → 去重桶 192（3 位小数聚合生效） |
| AC-M1-12 原子写 | PASS | 无 `.tmp` 残留 |
| AC-R-03 断供降级 | PASS（观察项） | gdelt_geo.log 近 80 行 10 条 fail 标记，news_geo.json 仍非空 |
| AC-R-04 单一写者 | PASS | events=527 articles=0 |
| G-M5 updated 当日 | PASS | 0.15h |
| G-M1 连续 3 天 | **未决**（day 1/3） | N=527 已记录，需累计 3 天 |
| G-M2 日波动 | **未决**（<2 天） | 待第 2 天 |

退出码说明：`--gate` 模式因 G-M1/G-M2 未到观测窗返回 1，属**未决**而非数据 FAIL；`--snapshot` 每日累积，第 3 天后正常判定。

---

## 2. 前端自动验收（verify_front.sh 完整跑，06:53）

```
Test Files  14 passed (14)
Tests       311 passed (311)
```

- `newsGeoAdapter.test.ts` **33 例**（含新增 XSS 消毒：超长截断、控制字符剥离、theme 空白降级、`<img onerror>` 原文保留待渲染层转义）
- `mapData.test.ts` **38 例**（含新增"XSS 防线三"：`pointTooltipHtml` 对 `label/group/rawMetric/note` 的 `&lt;`/`&gt;`/`&amp;` 转义断言）
- `layerCategories.test.ts` **31 例**（含 conflict 类别注册/图例/可见性）
- AC-R-05：**断言数不降**（newsGeoAdapter 33 例在案，无 skip/.only 迹象）

**XSS 专项聚焦跑**（vitest `-t "XSS|消毒|转义"`，独立复跑非依赖 arch 自验）：`5 passed | 66 skipped`，全绿。

---

## 3. XSS 消毒与 tooltip 转义 — 代码审查结论（防线二 + 防线三）

| 层 | 机制 | 位置 | 审查结论 |
|---|---|---|---|
| 适配层消毒（防线二） | `sanitizeText`：trim + 剥离 C0/C1 控制字符 + 长度上限（默认 120） | `newsGeoAdapter.ts:41-48` | 外部字段 `location_name/theme/country/event_type/event_date` 全部经此清洗；故意**不做 HTML 转义**避免双重转义 |
| 渲染层转义（防线三） | `escapeHtml`：`& < > " '` 五字符实体化 | `mapData.ts:187-201` | tooltip 唯一转义点；`pointTooltipHtml` 对 `label/group/rawMetric/note/severity/unc/categoryLabel` 统一转义 |
| 危险字符不可达面 | `value/color` 为数值/内部调色板 | `mapData.ts` | intensity 经 `Number.isFinite` 守卫；color 恒取 `categoryColor()` 内部值，非外部输入 |
| 弧线文案 | `arcTooltipHtml` 的 `fromLabel/toLabel` **未转义** | `mapData.ts:257` | **arch-map 判定依据（2026-08-11 确认归档）**：值仅来自 `config/grvDimensions.ts` 静态配置（`GRV_ARCS` 硬编码维度 label，构建期常量，**无 feed 写入路径，注入面为零**），与 `pointTooltipHtml` 的外部输入性质不同；若未来弧线数据 feed 化，在同一文件内复用私有 `escapeHtml` 即可，无需新增防线 |

**payload 实测**（来自测试套件，独立运行通过）：
```
label:  '<img src=x onerror=alert(1)>'   → 输出 &lt;img src=x ...（无原始序列）
group:  '"><script>alert(2)</script>'    → 输出 &lt;script&gt;alert(2)...（无 script 标签）
note:   '<b>note</b>'                    → 输出 &lt;b&gt;note&lt;/b&gt;
rawMetric: "x' & y"                      → 输出 x&#39; &amp; y
```

**结论：XSS 用例实际验证通过，`<img onerror>` 类 payload 无法在 tooltip 注入执行。** 未发现需打回 arch-map 的前端缺陷。

---

## 4. conflict 类别色映射 — 代码审查结论

| 检查点 | 结论 | 证据 |
|---|---|---|
| `event_type='conflict'` 点走 conflict 类别 | 通过 | `newsGeoAdapter.ts:192`：`category = norm.event_type === 'conflict' ? 'conflict' : 'news'` |
| conflict 类别已登记（layerCategories.ts:112） | 通过 | `LAYER_CATEGORIES` 含 `{key:'conflict', label:'冲突事件', color:CATEGORY_PALETTE.conflict, shape:'circle', phase:'P1', feed:null}` |
| 图层可独立显隐 | 通过 | conflict 与 news 是独立 `LayerCategory`，图例/图层树按 `ALL_CATEGORIES` 开关；`parseLayerVisibility` 支持持久化 |
| AC-M3-03 id 命名空间隔离 | 通过 | 事件点 id 前缀 `newsgeo:`（`newsGeoAdapter.ts:195`）；news 与 conflict 同 feed 共享前缀但底层 GDELT id 唯一，无撞车；与 `geo:`/`event:`/`nuclear:`/`news:`（articles）前缀互斥 |
| 数据源刷新 | 通过 | `dataSources.ts:90-95`：`news_geo` feed `refreshMs:60_000` + `schemaVersion:'1.0'` |

当前数据中有 3 个 `conflict` 事件点（06:45 增量映射实证），颜色将走 conflict 红系，与地理新闻（news）类别色区分。

---

## 4.5 视觉重构回归（commit `a63bd65` v1.10.1，08-11 部署）

**代码级参数核对（对 a63bd65 源码 + 部署 bundle 双轨验证）**：

| 改动项 | arch-map 描述 | 源码证据 | 部署 bundle 证据 |
|---|---|---|---|
| 2D 事件点中心 | `clamp(3,9, 3+weight×6)`（旧最大≈18px → 9px） | `FlatMapPanel.tsx:404` `Math.min(9, Math.max(3, 3+p.weight*6))` | — |
| 外侧薄描边环 | `r=core×2.2`，w1.2，op0.6 | `FlatMapPanel.tsx:439-444` | — |
| 内层淡光晕 | op0.10 | `FlatMapPanel.tsx:449-452`（r=core×1.35, fill-op 0.10） | — |
| 中心 fill-opacity | 0.75 | `FlatMapPanel.tsx:459` | — |
| 脉冲 | 只动外环：opacity 0.4↔0.9 + 环宽 1.0↔1.8，中心稳定 | `FlatMapPanel.css:61-64` `fm-ring-breathe` | CSS bundle 含 `stroke-width:1.8` |
| 点击聚焦环 2D | 46px → 24px | `FlatMapPanel.tsx:548-549` `focusR=max(core*2.4, 12)` | — |
| 3D FOCUS_ALTITUDE | 1.2 → 1.8 | `GlobePanel.tsx:60` `=1.8` | — |
| 3D 聚焦环基径 | 6.5 → 3.5 | `GlobePanel.tsx:347` `(isFocus?3.5:2.2)+weight*2.2` | — |
| 3D 聚焦 speed | 2.6 → 1.8 | `GlobePanel.tsx:349` `isFocus?1.8:...` | — |
| 菱形核设施点 | 无回归（保持原呼吸） | `FlatMapPanel.tsx:418-433` 菱形分支保留 + `.fm-point-pulse` 0.85↔1 | — |

**部署状态**：index.html 引用 `assets/index-Cuu3f83h.js` + `index-rAzF3Foj.css`；bundle 内含 `fm-ring-breathe`/`stroke-width:1.8`/`refreshMs:6e4` 标记；dist **无 data/ 子目录**（防嵌套挂载）；**18/18 feed 200**（含 `fred_history/GSCPI.csv`）+ index.html 200；npm test 独立复跑 **311 全绿**（对 a63bd65 源码，AC-R-05 不降）。

**结论**：代码级与部署级均确认 a63bd65 视觉重构已生效，无尺寸/逻辑回归。观感验证见 §6 人工-8~12（由主理人浏览器复核）。

---

## 4.6 三项修复回归（commit `b5852d8` v1.10.2，08-11 部署）

| 修复项 | 源码证据 | 部署 bundle 证据 |
|---|---|---|
| ① flat 缩放后切分类点尺寸恒定 | `FlatMapPanel.tsx:150-168` `applyPointInvScale`（invScale=1/k，施加到点组/聚焦环 transform + 星标字号）；**三个调用点**：zoom 事件 `:214`、buildPoints 重建后 `:490`、聚焦环重建后 `:577` | 活动 bundle `index-C5O0u3uk.js` 含 `fm-point-group` 反向缩放选择器 |
| ② globe 点击点不飞相机 | `GlobePanel.tsx:270-271` 注释明确"v1.10.2 起不再飞相机（点击只标记不飞）"；单点聚焦由 rings 表达（`isFocus ? 3.5 : 2.2` + weight*2.2，`:331`）；region 切换保留 `pointOfView(regionCamera(region))` 属预期 | bundle 含 `aria-expanded`/ring 逻辑 |
| ③ 报告中心分类折叠 | `ReportsPanel.tsx:72` `collapsedTypes`（默认空 Set=全展开）；`:190` `typeOpen`；`:194-211` 组头按钮 `aria-expanded` + `▾/▸` 指示（`:203`）+ 数量徽标常驻（`:210` `g.items.length`，折叠不消失） | bundle 含 `aria-expanded`（2 处） |

**部署状态**：index.html 引用 `assets/index-C5O0u3uk.js` + `index-ITF8Jrwl.css`（v1.10.2 活动 bundle）；CSS 含 `fm-ring-breathe`；feed 抽查 200（news_geo/grv_latest/nuclear_sites/reports_index）；npm test 独立复跑 **311 全绿**。

**结论**：三项修复代码级全部确认到位，与 v1.10.1 视觉重构无冲突。交互观感见 §6 人工-13~15（由主理人浏览器复核）。

**部署卫生观察项**：`dist/assets/` 累积 8 个 index-* bundle（活动 v1.10.2 + 回滚候选 v1.10.1/v1.10.0 + 2 个最旧残留 index-Bt_hmYiG.js/index-cRvpZC8e.css）。arch-map 评估清理方案（仅删 2 个最旧残留、保留 3 版本供回滚）后，因项目红线"dist 只覆盖不清理"**不擅自 rm 共享运行区，已转 team-lead 定夺**（2026-08-11）。批准后 arch-map 执行并验证；不批准则维持现状（不影响运行）。

---

## 4.7 参数微调回归（commit `eefd2da` v1.10.3，08-11 部署，纯观感参数）

| 改动项 | arch-map 描述 | 源码证据 | 部署 bundle 证据 |
|---|---|---|---|
| ① 地缘要地星标 +20% | 2D `SITE_STAR_FONT` 14→**16.8**、3D 精灵 3.2→**3.84**（importance 1/2/3 → 16.8/21/25.2px） | `FlatMapPanel.tsx:29` `=16.8`（×`siteScale` :515）；`GlobePanel.tsx:359` `3.84 * siteScale`；`siteScale` 1→1.0/2→1.25/3→1.5（`strategicSites.ts:190`） | 活动 bundle `index-H9wpMDHi.js` 含 `16.8` |
| ② 事件点弧光收窄 | 外环 r core×2.2→**1.8**、描边 1.2→**1.0**、透明度 0.6→**0.5**、脉冲环宽 1.0↔1.8→**0.8↔1.4**；内层光晕不变 | `FlatMapPanel.tsx:451` r=core×1.8、`:453` withAlpha 0.5、`:454` stroke-width 1.0、`:461` 内层 core×1.35 op0.10 不变；`FlatMapPanel.css:62-63` 0.8↔1.4 | CSS `index-DiS3fCd9.css` 含 `stroke-width:.8` |

**部署状态**：index.html 引用 `assets/index-H9wpMDHi.js` + `index-DiS3fCd9.css`；npm test 独立复跑 **311 全绿**；feed 抽查 200。

**结论**：两处参数微调代码级全部确认到位。观感对比见 §6 人工-16~17（由主理人浏览器复核）。

---

## 5. G-M1/G-M2 连续观测（day 1/3）

`qa-history.json`（NAS docs/qa-scripts/）：

```json
{ "days": [ { "date": "2026-08-11", "N": 527, "updated": "2026-08-11T06:45:34+08:00" } ] }
```

- 每日 `verify_data.py --snapshot` 累积；第 3 天后 `--gate` 正常判定 G-M1（连续 3 天非空）与 G-M2（日波动 ≤50%）。

---

## 6. 浏览器人工项复核清单（由主理人浏览器复核，网址 http://localhost:8080）

> 以下各项**由主理人浏览器复核**，QA 不代跑；逐项给操作步骤 + 预期，完成截图/console 记录后归档为 G-M3 佐证。

| # | 项 | 操作步骤 | 预期 |
|---|---|---|---|
| 人工-1 | **AC-F-01 事件点渲染** | 打开 localhost:8080 → 世界地图 → 图层树勾选"地理新闻"与"冲突事件" | 应见全球分布事件点（news 类别色 + conflict 红系分开）；点径随 intensity 分级；悬停 tooltip 显示 location_name/country/event_type/mention_count；**截图留档** |
| 人工-2 | **AC-F-03 性能** | DevTools Performance 录制"地图加载 + 全图缩放一次" | 主线程 long task（>50ms）≤5；无白屏帧；控制台**无** `[WorldPanel] 某图层点位超过 2000 上限` 告警 |
| 人工-3 | **XSS 注入用例（tooltip）** | 临时把 `news_geo.json` 某事件 `location_name` 改为 `<img src=x onerror=alert(1)>`（只读测试副本或浏览器改响应），刷新后悬停该点 | tooltip 显示纯文本 `&lt;img src=x onerror=alert(1)&gt;`，**不触发 alert**、不加载图片；检查 console 无报错 |
| 人工-4 | **AC-F-04 状态条时间戳** | 看状态条 GEO 数据时间 | 与 `news_geo.json` 顶层 `updated`（当前 06:45:34）一致；无时区后缀缺失（契约 +08:00） |
| 人工-5 | **AC-F-05 图例计数** | 切换地区（如"中东"）观察图例"地理新闻"数字 | 数字随地区切换变化，且与地图实际点位数吻合 |
| 人工-6 | **AC-F-02 降级不白屏** | DevTools Network 将 `/data/news_geo.json` 请求改 404（或断网）后刷新 | 地图其余图层（GRV/核设施）仍渲染、无白屏；状态条对 news_geo 报读取失败（降级提示） |
| 人工-7 | **G-M3 综合** | 汇总人工-1~6 的截图 + console 记录 | 归档至本报告同目录（或论证附件），作为 G-M3 门禁佐证 |
| 人工-8 | **视觉回归① 事件点形态** | 2D 地图勾选"地理新闻/冲突事件"，放大到城市级观察单个事件点 | 应为"小实体（≤9px）+ 薄描边弧光贴附（r≈2.2×core）"，**不再是旧版大实心圆×2 叠圈**；内层淡光晕隐约可见；**截图留档** |
| 人工-9 | **视觉回归② 外环呼吸** | 盯住任一高 intensity 事件点 3-4 秒 | 只有外侧薄环在呼吸（opacity/环宽 0.4↔0.9、1.0↔1.8），**中心实体稳定不动** |
| 人工-10 | **视觉回归③ 点击聚焦收敛** | 点击一个事件点：2D 看聚焦环 + 3D 切球体看相机高度 | 2D 聚焦环收敛（≤24px 级，不再 46px 大圈）；3D 相机高度适度（FOCUS_ALTITUDE 1.8，**不再贴脸放大**），聚焦环基径收窄（3.5），有"明显收敛"观感 |
| 人工-11 | **视觉回归④ 类别色清晰** | 同屏对比 news（地理新闻）与 conflict（冲突事件）点 | 两类点颜色可一眼区分（conflict 红系 vs news 类别色），互不混淆；图例计数仍正确 |
| 人工-12 | **视觉回归⑤ 菱形核设施无回归** | 勾选"核设施"图层，观察菱形点 | 菱形形状/呼吸（opacity 0.85↔1）/缺失态虚线与重构前一致，无尺寸爆大或形状变形；**截图留档** |
| 人工-13 | **修复① flat 缩放切分类尺寸恒定** | 2D 地图放大（滚轮 k>1）→ 切换图层/分类 → 观察事件点与星标字号 | 点/聚焦环视觉尺寸**保持恒定**（不再按 k 倍放大）；点位移正常不漂移 |
| 人工-14 | **修复② globe 点击不飞相机** | 3D 球体点击任一事件点 | 只出现 ring 聚焦标记（基径收窄 3.5），**相机不飞近**；再点 region 切换仍正常定位（属预期） |
| 人工-15 | **修复③ 报告中心分类折叠** | 左侧报告中心点击任一 type 组头（宏观分析等） | 可折叠/展开：`▾/▸` 指示随状态切换、`aria-expanded` 同步、**折叠后数量徽标仍显示**；默认全展开；5 个组头均可用 |
| 人工-16 | **v1.10.3① 地缘星标加大** | 对比 v1.10.2 截图（或 2D 放大/3D 球体看战略要地 ★） | 星标**明显更大**（+20%）：2D 16.8/21/25.2px 三级可辨，3D 精灵同步放大；**截图留档** |
| 人工-17 | **v1.10.3② 弧光收窄** | 对比 v1.10.2 截图，看任一事件点外环 | 外环**更贴附更细更淡**（r 1.8×core、线宽 1.0、op 0.5）；脉冲环宽 0.8↔1.4 呼吸仍清晰；conflict/news 类别色不受影响；**截图留档** |

数据核对命令（NAS 侧，与浏览器并排看）：
```bash
ssh nas 'curl -s http://localhost:8080/data/news_geo.json | head -c 400'
ssh nas 'python3 /vol2/1000/software/world-sim/macro-scan/docs/qa-scripts/verify_data.py'
```

---

## 7. 48h 判定点计划

| 时间点 | 动作 | 判定 |
|---|---|---|
| 2026-08-11 部署生效（06:35） | 过渡期快照（本报告） | 数据层 16 PASS、前端 311 全绿、XSS 过 |
| 每日（含 08-12/08-13） | `verify_data.py --snapshot` | 累积 G-M1/G-M2 连续天数 |
| **2026-08-13 06:35 起（满 48h）** | `verify_data.py --gate --enforce-unknown` | **硬判 `unknown<5%`** + G-M1/G-M2/G-M4/G-M5 汇总 |
| 前端 commit 已落地（a86fbbe + a63bd65 + b5852d8 + eefd2da） | `verify_front.sh`（主理人跑人工清单：AC-F/视觉回归人工-8~12 + 三项修复人工-13~15 + 参数微调人工-16~17） | G-M3 截图归档后汇总最终门禁 |

**unknown 下降机制**：jsonl 只累积 10 天，补 EventCode 后新窗口自然换新；06:45 起带码增量进入，unknown 占比预期随窗口滑动从 97.91% 逐步下降。**若满 48h 后 unknown 仍 ≥5% 且带码行占比已高 → 按 RSK-1 标记映射实现缺陷**（打回 arch-map/data）。

---

## 8. 未决与观察项

1. **GDELT 源间歇失败**：`gdelt_geo.log` 近 80 行含 10 条 `all_failed/slots_failed` 标记（AC-R-03 观察项）。当前 news_geo.json 非空、updated 新鲜，未受影响；若 G-M1 观测窗内断供，updated 将停滞 → 按 RSK-5 归因（保留旧数据=预期降级，非实现问题）。
2. **`arcTooltipHtml` 未转义 fromLabel/toLabel**：**非缺陷**（arch-map 确认：值仅来自 `grvDimensions.ts` 静态配置，构建期常量，无 feed 写入路径，注入面为零）。若未来弧线数据 feed 化，在接入点复用 `mapData.ts` 私有 `escapeHtml` 即可。
3. **unknown 97.91%**：过渡期预期状态，非缺陷；以 48h 判定点为准。
4. **AC-M1-09 新鲜度口径**：当前按日频 36h 阈值通过；若调度切 I15，需以 `--max-age-hours 1` 复核。

---

## 9. 48h 过渡期硬判定观测日志（2026-08-13 06:35）

| 判定时间 | 命令 | unknown% | N | event_type 分布 | 判定 |
|---|---|---|---|---|---|
| 2026-08-13 06:35 | verify_data.py --gate --enforce-unknown | **0.00%** | 604 | political=536 (88.7%) / conflict=64 (10.6%) / protest=4 (0.7%) | **PASS** |

**结论：PASS** — unknown=0.00% < 5% 硬判定通过，过渡期结束，CAMEO root_code 映射全量生效，四枚举输出达标（unknown 由部署时 97.91% → 0.00%）。

佐证（容器内 docker exec 实测）：
- jsonl 带码行：news_geo.jsonl total=168777 行，带 event_code/root_code=38813 行（占比 23.0%，10 天窗口内带码增量已滑入；产物层兜底映射使 unknown 归零）。
- 数据层 17 项检查全 PASS（含 AC-M1-05 unknown 硬判定、AC-R-04 无 articles 混入、AC-M1-08 schema/时区、AC-M1-09 updated=06:30:51 距判 0.08h）。
- 唯一未过项 G-M1（连续非空天数=2<3）属独立观测窗天数累积门禁，08-14 第三次 --snapshot 后自动闭合，与本硬判定无关。

*生成：qa-map · verify_data.py / verify_front.sh / 源码审查 · 2026-08-11 06:55，修订 07:30（§4.5 + 人工-8~12），修订 08:10（§4.6 + 人工-13~15），修订 08:25（§4.7 + 人工-16~17，v1.10.3）(Asia/Shanghai)*
| 2026-08-13 06:55 | verify_data.py --snapshot | 0.00% | 602 | political=534 / conflict=64 / protest=4 | updated=2026-08-13T06:45:51+08:00 当日 PASS（I15 滞后0周期）；G-M1 连续非空天数=2/3，相对前日 527 波动 +14.2% |
