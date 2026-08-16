# Changelog · 开阳（Kaiyang）操作面板

> 文档类别：实录（RECORD）· CHANGELOG（每条绑定 commit hash，写后即验）
> 最后核对时间：2026-08-16（记录类文档随部署持续更新）

本文件记录开阳的每次变更，遵循 Keep a Changelog 精神，版本号与 `VERSION` 绑定（SemVer 取向）。

## [1.11.17] - 2026-08-16 · 卫生点点击弹框显示新闻（health 加入可弹框类别）

**修改理由**：用户反馈"点击卫生点没有新闻显示"。根因：`WorldPanel.handlePointClick` 只对 news/conflict 类别弹框（EventPopup），health 点点击只聚焦不弹。

### 修改

- **`components/WorldPanel.tsx`**：`isNewsPoint` 加入 `health`——卫生点点击弹出 EventPopup
- **`lib/healthAdapter.ts`**：填 `sourceUrl = e.doc`（GKG DocumentIdentifier 原文 URL）→ EventPopup 显示"查看新闻原文"链接 + note（类型/媒体/地点/时间）
- 基础设施（EventPopup 的 sourceUrl 链接）本已就绪，缺的只是类别放行

### 验证

- `npm test` 352 tests 全绿；vite build（`index-adinh1uk.js` / `index-1XkBUX4y.css`）

## [1.11.16] - 2026-08-16 · 卫生图层关联新闻（source_media 媒体名）

**修改理由**：用户反馈卫生检测没关联新闻。实测纠错（08-15 旧分析有误）：GKG 2.0 27 列实测确认 `cols[4]=URL`（doc 字段一直正确）、`cols[3]=SourceCommonName` 媒体域名、`cols[9]=V1Locations`；**GKG CSV 无标题列**（标题只在 DOC 2.0 API）——准确缺口是事件没有"哪个媒体报的"。

### 修改

- **`types/contracts.ts`**：`HealthEventRaw` 加 `source_media?`（媒体域名）
- **`lib/healthAdapter.ts`**：note 改为 `类型 {kw} · {media} 报道 · 地点 · 时间 · 原文 {doc URL}`——可读新闻关联 + 来源可信度标注（媒体提及非官方确认）
- 后端同批（fetch_health_geo）：事件加 `source_media`（cols[3]）+ 历史事件从 doc URL 提取域名回填（233/233 100% 带媒体名）

### 验证

- `npm test` 352 tests 全绿；vite build（`index-C9bmxCsP.js` / `index-1XkBUX4y.css`）；后端容器重跑 health fetcher 全量回填确认

## [1.11.15] - 2026-08-16 · 内置 CONTROL_TOKEN（控制台开箱即用）

**修改理由**：用户反馈控制台「缺 token」——服务端 token 正常（compose/容器 env/401 均验证），根因是前端 localStorage 无 token（未填过或被「重置布局」的 clearAllKaiyangStorage 清掉）。手动填流程不顺畅。

### 修改

- 构建时注入 `VITE_CONTROL_API_TOKEN`（**不进 git 源码**，构建参数传入）→ `getEnvToken()` 优先于 localStorage 读取 → **控制台开箱即用，无需手动填 token**
- 安全模型：token 与运行区 compose 明文同级（LAN 内部系统），且 H02 信任校验保证 token 只发往 `192.168.31.108`（非信任 host 不带）

### 验证

- playwright 实测：**清空 localStorage token → 刷新 → 控制台直接「API Token 已配置」+ 53 个 fetcher 加载正常**
- bundle `index-DnxoRcXI.js` 含注入 token；352 tests 绿

## [1.11.14] - 2026-08-16 · H01 randomUUID LAN 崩溃 + H02 token 外泄通道

**修改理由**：审查 H01/H02——① LAN HTTP（非安全上下文）下 `crypto.randomUUID()` 不可用（抛 TypeError），控制面板 showToast/addLog/重跑 idempotencyKey 7 处调用点按钮即崩；② localStorage 可覆盖 API 地址 + token 无条件自动附带 = token 外泄通道（恶意 URL 注入 → Bearer token 发往任意服务器）。

### 修改

- **新增 `lib/uuid.ts` `safeUuid()`**：优先 `crypto.randomUUID()`，不可用时 fallback RFC4122 v4 拼装（不依赖 crypto.getRandomValues——LAN HTTP 同样受限）；替换 7 处调用（FetcherCard ×3 / ControlContext ×2 / TianshuTab ×1 / controlApi mock ×1）
- **`lib/controlApi.ts` H02**：`buildHeaders()` 仅对**信任来源**（`192.168.31.108` / `localhost` / `127.0.0.1`）附带 Bearer token——localStorage 注入恶意 URL 时 token 不外泄（非信任 host 请求无 token → 后端 fail-closed 401）

### 验证

- `npm test` 352 tests 全绿；vite build（`index-BjI6VSDl.js` / `index-1XkBUX4y.css`）
- playwright 实测（LAN HTTP）：控制台打开 → 点「重跑」→ **无 pageerror** + "重跑已提交 · op_c7b759f5" toast 正常（H01 fallback 生效）；fetcher 列表加载正常（token 信任校验下请求成功，H02 未破坏正常路径）

## [1.11.13] - 2026-08-16 · H18 sim_trigger 三端契约（schema tile 读取失败清零）+ schema_version 显示

**修改理由**：审查 H18——sim_trigger.json 三方语义冲突：天枢写触发标志 → 天璇读后 `write_text("")` 清空（0 字节）→ 开阳当持久状态 fetch → `JSON.parse('')` 崩 → schema tile 显示「读取失败:sim_trigger.json」；另 schema tile 有 6 条版本告警（3 缺字段 + 3 写 "1"≠"1.0"）。

### 修改

- **`types/contracts.ts`**：`SimTriggerRaw` 对齐新契约——`level?: number`（天枢写 int）、`event/reason/consumed/consumed_at/triggered_at` 字段
- **`config/dataSources.ts`**：`FeedConfig` 加 `tolerateEmpty?`；simTrigger 配置启用（历史 0 字节残留静默 null）
- **`hooks/useFeed.ts`**：`tolerateEmpty` feed 解析失败 → 静默 null，不上报「读取失败」
- **`components/StatusBar.tsx`**：推演状态三态显示——触发（rose）/ 上次触发已消费（cyan，H18 新契约）/ 未触发（emerald）

### 验证

- `npm test` 352 tests 全绿；vite build（`index-Bqe4jC0L.js` / `index-1XkBUX4y.css`）
- playwright 实测：schema tile `读取失败:sim_trigger.json` 消失；simStatus=「推演未触发」；4 个 fetcher 手动重跑后 `airroutes:1.0 sdr:1.0 spacelaunch:1.0 safecast_nuke:1.0`（firms 等下次调度）

## [1.11.12] - 2026-08-16 · footer 滚动盖层修复 + 控制台 Token 配置 UI

**修改理由**：用户报两个问题——① 左下角「世界推演系统 · 开阳 Wave 2 v1.11.11 · 操作面板」滚动页面时跟着动、盖在正常界面上面；② 控制台天枢 tab 只显示「Token 无效」且无任何配置入口（P1-D fail-closed 后遗症）。

### 修改

- **footer 盖层修复（`App.tsx`）**：外层 `min-h-full` → `h-screen overflow-hidden` + main 加 `overflow-y-auto`。实测根因：ResponsiveGridLayout 面板超高（文档高 3783px = 视口 4 倍）撑破 `min-h-full` 外层，footer（z=1 高于 grid items）悬浮在面板内容中间随滚动移动盖住界面。修复后文档高度 = 视口，面板在 main 内部滚动，footer 常驻视口底部。
- **新增 `control/TokenSetup.tsx`**：折叠式 API Token 配置组件（状态行 → 展开输入 + 保存 + 清除），经 ControlContext.setToken 写入（同步 setApiToken + localStorage）。此前前端无任何 token 配置入口。
- **`ControlDrawer.tsx`**：TabBar 上方接入 TokenSetup（所有 tab 可见）。
- **`TianshuTab.tsx`**：401 错误态改为「API 鉴权失败：Token 无效或未配置」+ 内联 TokenSetup（onSaved 自动重试）。
- **`hooks/useControlApi.ts`**：useFetchers 依赖 token，配置/清除 token 后自动重新拉取，免手动重试。

### 验证

- `npm test` 352 tests 全绿；vite build 成功（`index-CTh5HUrs.js` / `index-BWF2WuTh.css`）
- playwright 实测：文档高度 966 = 视口（原 3783）、footer 贴底 y=921、面板 main 内滚动；控制台打开 → 填 token → 保存 → **自动重试加载 53 个 fetcher 全部分组**（宏观·FRED 8 / 地缘 2 / 新闻 / 市场 / 灾害 / 卫星 / 推演/验证），真实数据来自天枢 control API
- 部署 bundle `index-CTh5HUrs.js`，旧 bundle 已清理

## [1.11.11] - 2026-08-15 · 布局错乱自动修复 + 强制 remount + P0 emoji 清理

**修改理由**：用户报开阳排版「乱套了」——3D 地球被压成细条、左右面板挤压。根因判定为 localStorage 中持久化的拖拽布局异常（例如 world 面板 h 被缩到很小），react-grid-layout 直接恢复该异常尺寸；「重置布局」因组件未重新 mount 也可能不生效。

### 修改

- **`App.tsx` 布局健康检查 `isLayoutHealthy`**：
  - world 面板缺失或 h < minH（5）/ w < 4 时视为异常
  - 坐标/尺寸为非正数、NaN、超出 12 栅格时视为异常
  - 总高度 max(y+h) < 18 时视为异常
  - 检测到异常布局时自动删除 `kaiyang.v6.panelLayout` 并回退默认布局
- **`loadLayout` 加载时自动校验**： unhealthy persisted layout 不再被直接采用，避免异常布局复发
- **`onLayoutChange` 保存前校验**：拖拽/缩放产生的异常布局不写回 localStorage，防止用户误操作把面板压到不可见
- **重置/自动布局强制 remount**：新增 `layoutResetNonce`，重置时改变 `ResponsiveGridLayout` 的 `key`，强制 React 重新 mount，根治「点了重置但 grid 内部状态没刷新」
- **彻底清理 kaiyang 缓存**：`clearAllKaiyangStorage` 删除所有 `kaiyang.*` localStorage 键，避免 layerVisibility/region/strategicSites 等旧偏好交叉污染
- **按钮 emoji 替换为 SVG**：`⚡`/`↺` → 内联 `AutoLayoutIcon`/`ResetIcon`（P0 规则：禁止 emoji 作 UI 元素）
- **footer 版本号同步 `VERSION`**：`1.8.0` → `1.11.11`

### 验证

- `npm test` 20 files / 352 tests 全绿
- `vite build` 本地构建成功（新 bundle `index-Cf8Cz6sn.js` / `index-Zi8GR3W0.css`）
- scp 原地覆盖 `/vol2/1000/software/kaiyang/dist/` + `chmod -R a+rX`
- dist/assets 清理：动态核对 `index.html` 引用后删除 12 个最旧残留 bundle，保留最近 3 版 6 个 bundle
- NAS 本机验证：`http://127.0.0.1:8080/` 200；`index.html` 引用新 bundle；js/css 200
- 注：因 `index.html` 已被 nginx 配置为 no-cache，正常刷新即可拿到新布局修复；如仍异常请点底部「重置布局」或按 `Ctrl+Shift+R` 强制刷新

## [1.10.3] - 2026-08-11 · 视觉微调：地缘要地图标 +20% / 事件点弧光收窄（by arch-map）

**修改理由**：主理人浏览器复核后两项微调——①地缘（战略要地/chokepoint）星标图标偏小；②事件点弧光仍显"圈太大、太粗、太亮"，需更贴附中心。

### 修改

- **地缘要地图标加大 20%**（菱形/星形形态与类别色不变）：
  - 2D `FlatMapPanel.tsx`：`SITE_STAR_FONT` 14 → **16.8**（×1.2，乘 siteScale 后 importance 1/2/3 → 16.8/21/25.2px）
  - 3D `GlobePanel.tsx`：要地星标精灵 `3.2 → 3.84`（×1.2）
- **事件点弧光收窄**（`FlatMapPanel.tsx` / `FlatMapPanel.css`）：
  - 外环半径 `core×2.2 → core×1.8`（更贴附中心）
  - 描边 `stroke-width 1.2 → 1.0`、透明度 `opacity 0.6 → 0.5`
  - 脉冲环宽呼吸 `1.0↔1.8 → 0.8↔1.4`（幅度同步收窄）；内过渡层 1.35/0.10 保持不动

### 验证

- `npm test` 14 files / 311 tests 全绿；`vite build` 本地构建成功（新 bundle `index-H9wpMDHi.js` / `index-DiS3fCd9.css`）
- scp 原地覆盖 + `chmod -R a+rX`，dist 无 data/ 子目录；nginx 新 bundle js/css 200；18/18 feed 200
- 视觉项由主理人浏览器复核：地缘星标更大、事件点弧光贴附更细更淡

## [1.10.2] - 2026-08-11 · 三项修复：反向缩放丢失根治 / globe 点击不飞相机 / 报告分类折叠（by arch-map）

**修改理由**：主理人反馈 ①开关分类选项时所有图标放大（v1.10.1 视觉重构未触及、此前已存在的 bug）；②globe 点击点放大仍在；③宏观分析（报告中心）分类折叠未做。根因：invScale 反向缩放只在 zoom 事件施加，点组/聚焦环重建后丢失 → 缩放态切分类全部按 k 倍渲染；globe 点击点触发相机飞行；ReportsPanel 组头是静态 div 无折叠。

### 修改

- **`FlatMapPanel.tsx` 反向缩放根治**：抽 `applyPointInvScale()`（zoom 事件 + buildPoints 重建后 + 聚焦环重建后三调用点统一施加 `scale(1/k)` 于 `.fm-point-group`/`.fm-focus-ring`/`.fm-site-star`）。任意缩放态下切分类/点击点，点视觉尺寸恒定，无全分类放大、无超大聚焦环
- **`GlobePanel.tsx` 去点击飞相机**：删除聚焦点 `pointOfView({altitude})` 相机飞行（对齐 crucix：点击只标记不飞）；选中态由 rings 聚焦标记表达（isFocus 切换 ring 基径 2.2+2.2w → 3.5+2.2w 保留）；相机仅初始加载/region 切换定位；移除 `FOCUS_ALTITUDE` 常量
- **`ReportsPanel.tsx` 分类折叠**：新增 `collapsedTypes` state + 组头 div 改 button（`▾/▸` chevron + `aria-expanded`），点击切换该 type 报告列表折叠/展开，折叠保留数量徽标；默认全部展开；数据层零改动（groupReports 不动）

### 验证

- `npm test` 14 files / 311 tests 全绿；`vite build` 本地构建成功（新 bundle `index-C5O0u3uk.js` / `index-ITF8Jrwl.css`）
- scp 原地覆盖 + `chmod -R a+rX`，dist 无 data/ 子目录；nginx 新 bundle js/css 200；18/18 feed 200
- 视觉项由主理人浏览器复核：flat 模式缩放后切分类点不变大；globe 点击点不飞相机；报告中心宏观分析组可折叠

### 部署卫生（2026-08-11，无独立 commit）

- dist/assets 清理：动态核对 `index.html` 引用清单后删除 2 个最旧残留 `index-Bt_hmYiG.js` + `index-cRvpZC8e.css`（08-11 00:25 构建，已被取代），保留 v1.10.0/1.10.1/1.10.2 三版 6 个 bundle 供回滚；删后 index.html/活动 bundle/18 feed 全 200。
- 部署规范首次落地：新建 `docs/DEPLOYMENT.md`（构建禁 SMB / scp 原地覆盖禁 mv / dist 清理规则：保留 3 版、删前动态核对 index.html 引用、禁硬编码 hash、禁全量 rm）。

## [1.10.1] - 2026-08-11 · 事件点视觉重构（crucix 化）：中心实体 + 外侧薄弧光贴附（by arch-map）

**修改理由**：主理人反馈事件点图标"太大"、点击后放大倍率更大、实心+一大圈弧光不合理。参考 crucix（NAS `Crucix/dashboard/public/jarvis.html`，AGPL，仅参考视觉不抄代码）ACLED 冲突点形态重构——中心半透明小实体 + 外侧薄描边环贴附，严重度用中心大小区分，脉冲只动外环。详见调研纪要（arch-map 消息 2026-08-11）。

### 修改（`FlatMapPanel.tsx` / `FlatMapPanel.css` / `GlobePanel.tsx`）

- **中心大小收敛**：`core` 由 `(2.6+weight×3.4)×1.25×1.5`（事件点最大 ≈18px 半径）→ `clamp(3, 9, 3+weight×6)`，删除 ×1.25×1.5 双重放大（事件/高风险改由外环脉冲区分）
- **弧光薄环化**：删除旧两层实心大圆（`halo=core×3.2` op0.14 / `core×1.8` op0.22）→ 新三层：外环 `r=core×2.2` 薄描边 `stroke-width=1.2` op0.6（贴附外侧）；内层过渡 `r=core×1.35` 淡光晕 op0.10；中心 `fill-opacity 0.75`（"不太透明"）+ 白描边降为 0.35/0.5px
- **脉冲只动外环**：新增 `.fm-ring-pulse` 动画（opacity 0.4↔0.9 + stroke-width 1.0↔1.8 呼吸，周期随 weight），中心稳定；菱形点（核设施）保留原 `.fm-point-pulse` 整点呼吸
- **点击放大收敛**：2D 聚焦环 `halo×1.35≈46px` → `core×2.4≈24px`；3D `FOCUS_ALTITUDE 1.2→1.8`（避免贴脸）、聚焦环基径 `6.5+3w→3.5+2.2w`、传播速度 `2.6→1.8`；普通环基径 `3+3w→2.2+2.2w`、速度 `1.2→1.0`

### 验证

- `npm test` 14 files / 311 tests 全绿（渲染尺寸无测试覆盖面，无破坏）
- `vite build` 本地构建成功（新 bundle `index-Cuu3f83h.js` / `index-rAzF3Foj.css`）；scp 原地覆盖 + `chmod -R a+rX`，dist 无 data/ 子目录
- nginx：index.html 引用新 bundle 200；18/18 feed 全部 HTTP 200
- 视觉截图留档由主理人浏览器复核（实现侧无截图工具）

## [1.10.0] - 2026-08-11 · 地图深化路线 A——GDELT 事件图层实时化 + 冲突层 + XSS 双保险（by arch-map）

**修改理由**：① `news_geo_feed.py`（NER）空转链停用，天枢 `fetch_gdelt_geo.py --incremental`（I15）直接派生 `news_geo.json`（`events[]`，§2.7 契约），空渲染根治；② 地图新增事件实时刷新；③ 冲突事件（CAMEO root 15/18/19/20）归入已登记的 `conflict` 类别色，可独立开关；④ 地图点外部字段 XSS 消毒。详见 `macro-scan/docs/arg-map-arch-2026-08-11.md`。

### 新增

- **news_geo 实时刷新**：`dataSources.ts` news_geo 补 `refreshMs: 60_000`（与 market_quotes 同模式），I15 数据近实时上图
- **冲突事件层**：`newsGeoAdapter` 将 `event_type==='conflict'` 的点归入 `conflict` 类别（红，`CATEGORY_PALETTE.conflict`），可经 LayerTree 独立开关；其余事件走 `news`（青）
- **XSS 双保险**：适配层 `sanitizeText` 清洗外部文本（控制字符剥离 + 长度上限，防线二）；`pointTooltipHtml` 对 label/group/rawMetric/note 统一 HTML 实体转义（防线三，globe.gl 与平面地图共用）

### 修复

- 地理新闻图层空渲染根治（契约 §2.7 `events[]` 已由天枢产出；空数组合法降级不白屏）
- tooltip 注入面：`dangerouslySetInnerHTML` 上游一律转义，外部地名/URL 无法注入脚本

## [1.9.0] - 2026-08-05 · 开阳实时化 + 时间审计全量修复（by WorkBuddy）

**修改理由**：① 用户反馈"MACRO + MARKETS 一天一刷新不合理"→ 数据层 I15 + 前端轮询实时化；
② 时间戳时区语义审计（用户观察宏观面板 8-3）→ 6 问题全链路修复。详见
docs/operations/20260805-world-deduction-time-audit-fixed.md。

### 新增

- **实时化**：`useFeed` 支持 `refreshMs` 轮询重拉（market_quotes 配 60s）；scheduler market_quotes 0630→I15
- **时区确定性**：`format.ts` 新增 `parseTs()`（无后缀 ISO 补 +08:00 / 纯日期补 T00:00:00+08:00）+ `fmtRelative()`（相对时间）
- **控制台分组**：TianshuTab 48 采集源按类别分组 + 组头折叠（含全部展开/全部折叠）+ 组级 ⚠ 异常标记
- **信号流**：点击行内展开详情（完整标题/原文链接/risk_note/trigger_titles），div role=button 键盘可访问
- **nginx 缓存策略**：index.html no-cache + /assets/ immutable（根治浏览器缓存旧 bundle）
- **StatusBar**：GEO stamp（news_geo 时间戳）

### 修复

- 新闻乱序/假时刻：newsItemsOf 支持 {articles} 结构 + date 倒序；NewsPanel 时间戳改读顶层 updated/exported_at（修 StatusBar 显示插入序首条 7-31 / UTC 午夜假时刻）
- simTrigger 伪告警：KNOWN_STRUCTURAL_MISSING 过滤（与 StatusMiniPanel 一致）
- news_geo 契约漂移：adapter 支持 raw.articles 分支（normalizeArticlePoint，value=null 诚实标缺强度）
- 时间戳 UTC→北京：数据层 market_quotes/control_server 时区修复联动

## [1.8.0] - 2026-08-04 · 2D 平面地图换用 D3 geoNaturalEarth1，根治子午线水平伪线（by Claude Code）

> 版本递进：**1.7.2 → 1.8.0**。将 2D 地图渲染器从 Leaflet 完整替换为 D3.js + SVG，彻底消除 Russia/Alaska 跨 ±180° 子午线时产生的水平横线伪影。

**根本原因**：Leaflet 无法正确处理球面多边形的反子午线（antimeridian）截断；多次补丁（手工 `clipGeoJSON`、弧线分段）均无法根治。

**修改 — FlatMapPanel.tsx**（完整重写）
- 移除 Leaflet 全部依赖（`L.map`、`L.geoJSON`、`L.circleMarker`、`L.polyline` 等）
- 改用 `d3-geo` + `geoNaturalEarth1()` 投影 + 纯 SVG 渲染，D3 自动处理球面几何，无需任何 antimeridian 补丁
- 底图：海洋 Sphere 背景、陆地填充（`objects.land`）、国家边界（`objects.countries`）、经纬格线（`geoGraticule`）
- 缩放：`d3-zoom` 作用于 SVG `<g>` 容器，`scaleExtent [1, 12]`，双击重置
- 点位（圆形/菱形）、弧线（大圆分段）、战略要地（★ text）、聚焦光环：全部换为 SVG 元素；视觉参数与旧版完全一致
- Tooltip：改为 `position: fixed` 的 React state 驱动浮层，取代 Leaflet 内置 tooltip
- region 切换：改用 `d3-geo.fitExtent()` 重新投影并重置 zoom，取代 Leaflet `flyToBounds`
- 容器尺寸自适应：`ResizeObserver` 驱动 `fitSize` 重算投影，取代 Leaflet `invalidateSize`

**修改 — FlatMapPanel.css**
- 移除所有 `.leaflet-*` 选择器
- 新增 `.fm-arc`（流动虚线动画）、`.fm-point-pulse`（脉冲呼吸）、`.fm-tooltip`（暗色玻璃拟态浮层）
- 保留 `.leaflet-zoom-indicator`（缩放标签，功能不变）

**新增依赖**
- `d3-zoom@3.0.0`、`d3-selection@3.0.0`（已内置于 globe.gl，追加为直接依赖）
- `@types/d3-zoom`、`@types/d3-selection`（devDependencies）

**工程**
- 测试：297/297 通过（全部已有用例，无新用例；FlatMapPanel 无 JSDOM 单元测试）
- 构建：`npm run build` 绿（tsc --noEmit + vite build 均通过）

 · A3a 控制 API 接入，MOCK 模式关闭（by Claude Code）

> 版本递进：**1.7.1 → 1.7.2**。天枢 control_server.py（v3.8.5）上线，开阳切换到真实 API。

**修改 — controlConfig.ts**
- `DEFAULT_API_BASE_URL` 从 `localhost:8900` 改为 `192.168.31.108:8900`（指向 NAS 天枢控制服务）
- `MOCK_ENABLED` 默认值从 `true` 改为 `false`（开发时可通过 `VITE_CONTROL_MOCK=true` 恢复 mock）
- 原 ⚠ MOCK 横幅在 `MOCK_ENABLED=false` 时自动隐藏（无需改 ControlDrawer）

**部署说明**
- 需重新 `npm run build` 生成新 dist/
- NAS 须同时启动 `control_server.py`（见下方）



> 版本递进：**1.7.0 → 1.7.1**。架构裁定要求：`MOCK_ENABLED=true` 时控制抽屉须在 UI 层显式标注，防止演示时误以为控制功能已接入天枢侧后端。

**新增 — 控制抽屉 MOCK 横幅**

- `src/control/ControlDrawer.tsx`：导入 `MOCK_ENABLED`（来自 `controlConfig.ts`）；当 `MOCK_ENABLED=true` 时在 TabBar 上方渲染琥珀色横幅「⚠ 控制功能未连接（天枢侧 API 未实现）」，`MOCK_ENABLED=false` 时横幅自动隐藏，不影响生产接入后的 UI。
- 横幅样式：`--ky-amber` 色 + 半透明背景 + 底部分割线，与现有玻璃拟态风格一致；纯条件渲染，零新依赖。

**工程**

- 修改 1 文件：`src/control/ControlDrawer.tsx`（新增 `MOCK_ENABLED` import + 条件 banner）。
- 测试：297/297 通过（零新测试用例，banner 为纯条件渲染，无业务逻辑分支需覆盖）。

---

## [1.7.0] - 2026-08-02 · 运行时修复 + 控制抽屉关闭 + 2D 平面地图移除

> 版本递进：**1.6.0 → 1.7.0**。本条目为 1.6.0 上线后的紧急 BugFix + 架构清理批次：修复 Leaflet 2D 地图运行时崩溃（NaN LatLng）、修复控制抽屉关闭逻辑 bug（`prevOpen` 状态管理死循环）、全局错误边界（ErrorBoundary），以及因 CartoDB/ESRI/OSM/Voyager 四家第三方瓦片服务均存在数据缺口且无法弥补，**最终移除 2D 平面地图视图**，WorldPanel 永久锁定为 3D 地球模式。

**BugFix — `Invalid LatLng object: (NaN, NaN)`**

- **根因**：react-grid-layout 在面板初始化阶段给容器 0 高度时，Leaflet 的 `flyToBounds` 内部像素投影全算 NaN → 构造 `L.latLng(NaN, NaN)` → 抛异常 → 整页白屏。
- **修复**：FlatMapPanel 的 region→flyTo useEffect 加 `map.getSize()` 零尺寸检查（`size.x<=0 || size.y<=0`），为 0 时延迟 300ms 重试；各处坐标生成加 `isNaN` 防护（点位/弧线/要地/聚焦光环）；地图切换 active 态时双 rAF 后调 `map.invalidateSize()`。
- **验证**：Playwright headless Chromium 实测无错误。

**BugFix — 控制抽屉能开不能关**

- **根因**：`ControlDrawer` 的 `prevOpen.current = drawerOpen` 赋值在 `if-else` 条件分支的 `return` 语句之后，永远执行不到 → prevOpen 始终为 true → `!drawerOpen && prevOpen.current` 分支无法被进入 → 关闭动画从不触发。
- **修复**：将 `prevOpen.current = true/false` 移入对应的 if/else 分支内部；X 按钮改用 `onClick` 触发 StatusBar 的 🔧 按钮 DOM click（最可靠的 toggleDrawer 路径）。
- **验证**：Playwright 实测 → 点击 X 后抽屉从 DOM 消失。

**移除 — 2D 平面地图**

- CartoDB `dark_all`（zoom 2.5/3, 12/15 瓦片加载, 俄罗斯/中亚 3 瓦片持久缺口）、ESRI `World_Dark_Gray_Base`（0/15 加载, 全黑）、OSM `tile.openstreetmap.org`（0 加载）、CartoDB `voyager`（多处中断, 反更差）——四家瓦片服务经 Playwright 实测均不可接受。
- `WorldPanel` 移除 `FlatMapPanel` import 与渲染，3D/平面 toggle 按钮永久定为「🌐 3D 地球」。
- FlatMapPanel 组件文件保留在仓库中备用，等自建 tileserver 或可靠瓦片源出现后可恢复。
- `panelRegistry` 标题从「世界视图（3D/平面）」不变，但视图模式硬编码 `'globe'`。

**新增 — ErrorBoundary**

- `main.tsx` 新增 `ErrorBoundary` 类组件：任何子组件抛错时不再白屏，展示红色错误信息。

**工程**

- 未增删 npm 依赖。`package.json` 仅 `version` 1.6.0→1.7.0。
- 修改 6 文件：`VERSION`, `CHANGELOG.md`, `src/App.tsx`(footer 自动布局/重置布局按钮), `src/main.tsx`(ErrorBoundary), `src/components/StatusBar.tsx`(WAVE 2), `src/components/FlatMapPanel.tsx`(NaN 防护 + 瓦片切换), `src/components/WorldPanel.tsx`(移除 FlatMapPanel), `src/control/ControlDrawer.tsx`(prevOpen 修复 + X 按钮), `src/state/ControlContext.tsx`(CLOSE_DRAWER action), `src/types/control.ts`(closeDrawer 类型)。

## [1.6.0] - 2026-08-01 · 控制面 P2 死代码清扫（§4.5 A2）+ news_geo 读取层骨架（B）+ 市场行情读取预埋（C2）

> 版本递进：**1.5.0 → 1.6.0**。本条目属于「Wave2 第三批」的快进模式交付——**清扫既有死代码**（A2）+ **先行登记与搭建新闻地理化读取层骨架**（B，不含面板与可视层上线）+ **市场行情读取预埋**（C2），**不引入任何新架构决策**、**零新 npm 依赖**。代码改动严格在 `§3 扩展标准` 既有扩展点内（`FEEDS` 登记 + `useFeed` 复用 + `lib/` 适配器）。
>
> **本批 P1 后端小改批进度**：§2.6 第 ⑩ 项 `news_geo.json`、第 ⑬ 项 `market_quotes.json` 均已在开阳侧先行登记并搭建读取层骨架，**待天枢首次产出后回改定稿字段契约即可上图**。

**改了什么**

- **§4.5 A2 控制面 7 处 P2 死代码清除**：根据团队 P0=0 / P1=0 / P2=7 复盘结论，彻底删除控制面 P2 占位（天璇 / 天玑 / 玉衡 / 操作日志 / Token 设置）遗留在 `panels/registry.ts`、`hooks/useControlApi.ts`、`lib/controlApi.ts` 等处的 P2 死代码 7 处。控制抽屉本身与天枢运维 Tab（1.1.0）保留不动，本批**未引入任何新面板**，亦**未删减任何已交付能力**。
- **§4.5 A3 控制面 5 Tab 镜像标注**：5 个控制面 Tab（天枢 / 天璇 / 天玑 / 玉衡 / 操作日志）中其余 4 个「建设中」占位的镜像文案与路由条目增加**显式"已评：保留镜像，等待后端 P1+"注释**，明确「这是 P0 交付的镜像占位而非未规划」——避免后续维护者误判为遗漏。
- **B 节 news_geo 读取层骨架（§2.6 第 ⑩ 项先行登记）**：
  - `src/config/dataSources.ts` 登记 `news_geo` + `market_quotes` 两个新 feed 项（path / type / `schemaVersion: '1.0'`）。
  - `src/types/contracts.ts` 新增 `NewsGeoEvent` / `NewsGeoRaw`（§2.7 草案字段级 + `events: []` 必填 + 顶层 `schema_version` / `updated`）+ `MarketQuote` / `MarketQuotesRaw`（兜底预埋，无对应面板）。
  - 新增 `src/lib/newsGeoAdapter.ts`（与既有 `nuclearData.ts` 同构）：`adaptNewsGeo()` 把 `NewsGeoRaw` → `RiskPoint[]`，按 4 位小数 / 有限数 / ±90·±180 校验坐标、按 0–100 夹取并归整 `intensity`、按 `newsgeo:<id>` 命名空间组装 id（K2 防撞车）、`category='news'` 复用既有类别色（K6 只读契约）、`weight=intensity/100`（视觉双轴 D1）、缺失强度整条跳过不进 missing 通道、重复 id 取先。**K5 红线**：入参 nullish → 空数组，绝不抛异常。
  - `src/components/WorldPanel.tsx` 接线：复用既有 `useFeed<NewsGeoRaw>('news_geo')` + `useMemo(adaptNewsGeo)`，把 `newsGeoPoints` 合入 K7 层叠序列（海量点 → 常规点 → 事件点 → **地理新闻（1.6.0 新插入层）** → 固定设施）。`market_quotes` 仅 fetch 备查（`void marketRaw` 显式消费），**未上图**。
  - `LayerTreePanel` 计数**自动合并**：复用既有 `category='news'` 类计数通道，`news`（未来 RSS 上图）+ `news_geo`（本批）合并到同一行；选中态走既有 `SelectionContext`，`focusPointId` 由 id 命名空间自动路由。
- **B5 测试（+28，全量 297 通过）**：新增 `src/lib/newsGeoAdapter.test.ts` 28 用例，5 个 describe 块覆盖（入参降级 6 例 / 类别形状 id 4 例 / 字段容错 7 例 / 展示字段 8 例 / 与图层体系契约 3 例）。**零新依赖**，复用项目既有 vitest + `@/` 别名。
- **C1 useFRED 评估（不变）**：`src/hooks/useFRED.ts` 已满足 §2.6 第 ⑪ 项需求（`manifest` 为 null 时降级为空序列并告警；单序列 fail→空+状态条报告；`cancelled` 标志清理 effect），**零改动**。
- **C2 market_quotes 预埋**：`src/config/dataSources.ts` 登记 `market_quotes`（仅 fetch 备查）；`src/types/contracts.ts` 加 `MarketQuote` / `MarketQuotesRaw`（`symbol` / `name` / `price` / `change_pct` / `updated` / `category`）。**无面板、无上图**，待天枢定下文件形态后按 §2.6.3 回补字段契约再转正。
- **C3 useFRED 测试（跳过）**：评估需引入 `@testing-library/react-hooks`（或新方案如 `renderHook` 配 `jsdom`），**违反"零新依赖"约束**，本批跳过；既有 `useFRED` 测试覆盖由适配器层测试兜底（`fred_history` 序列适配逻辑已稳定）。
- **D 质量门（GO）**：`tsc --noEmit` 零错误（修复 newsGeoAdapter.test.ts 中 2 处类型断言）；`vitest run` **297/297 通过**（13 个测试文件，含本批 +28）；`vite build` 绿（10.84s，1066 modules）；`grep` 复查 `news_geo` / `newsgeo` / `NewsGeo` / `market_quotes` / `MarketQuotes` / `MarketQuote` 全部引用均为有意位置（contracts / dataSources / newsGeoAdapter / newsGeoAdapter.test / WorldPanel.tsx 接线 + SelectionContext/GlobePanel/SignalStreamPanel 旧注释"等天枢 GDELT news_geo feed 就绪"现可陆续清理，本批未动）。

**为什么这么改**

- **B 节为何「先行登记 + 仅读取层骨架，不上图」**：`docs/DATA_CONTRACT.md` §2.7 明确「待天枢首次产出后回改定稿字段」。但开阳侧的字段草案已经稳定（`NewsGeoEvent` 9 字段、强校验规则、4 位小数约定），等天枢首产再补会拖 1 个 sprint。本批以**读取层骨架预埋**形式把 `useFeed` 通路、`adaptNewsGeo` 适配器、WorldPanel 接线 + 图层体系接入全部建好，**图层面板**（独立「地理新闻」面板或归入既有信号流）留待天枢首产数据后再决策；天枢首产后只需把 §2.7「草案」标记摘除并按实际字段微调契约，**前端无需重构**。
- **K7 层叠把「地理新闻」插在事件点之后、固定设施之前**：新闻点位是「事件衍生的高频动态层」，视觉密度高于固定设施（核设施 / 战略要地），但与既有事件点同根（都是 GDELT / `grv_latest.events` 衍生）；把它放在事件点之后，让 3D/2D 双视图在大量新闻点位涌入时仍能保证战略要地不被覆盖。
- **C2 为何只 fetch 不上图**：§2.6 第 ⑬ 项明确「行情带 5 格中 4 格已有底数，待天枢把分散产物统一落成 `market_quotes.json`」；当前先读取不渲染，避免给用户展示「只有部分指数」的残缺面板。等天枢统一文件形态后，**适配器已就位、面板只是 `panelRegistry` 加一项**。
- **A2 死代码清除严格只删 P2 占位**：天枢 Tab 是 P0 核心交付（已通过组队复盘），其余 4 Tab 是「建设中」镜像占位（P2 占位但保留 UI 镜像）。本批只删其中**与 P0 实现毫无引用关系**的 7 处死代码，5 个 Tab 的 UI 镜像不动；A3 同步加注释说明「已评：保留镜像」避免维护者误判。

**明确没有改的（防误读）**

- ❌ **没有引入任何新 npm 依赖**（`package.json` 的 `dependencies` / `devDependencies` 与 1.5.0 完全一致，仅 `version` 行 1.5.0→1.6.0）。**未引入 jsdom / testing-library / @testing-library/react-hooks**。
- ❌ **没有做地理新闻的可视层**：未新增「地理新闻」面板，未改 LayerTreePanel 的 12 类清单（`category='news'` 走既有 12 类通路的同一行计数合并，未新增 13 类），未改 GlobePanel / FlatMapPanel 的渲染器（仍是只读 `p.color / p.weight / p.shape / p.status`）。**首产数据上线前地图上不会多出任何点位**（`useFeed` 拉不到文件 → 空数据流 → 适配器降级返回空数组 → 不渲染）。
- ❌ **没有改数据流**：`useFeed` / `adaptGrv` / `mapData` / `nuclearData` / `GlobePanel` / `FlatMapPanel` / `RegionTabs` / `StatusBar` / `SignalStreamPanel` / `LayerTreePanel` / `LayerLegend` 渲染器全部零改动；只增不删不减。
- ❌ **没有把 `news_geo` 接入「新闻面板」**：`news_export.json`（RSS 纯文本）仍是新闻面板的唯一源；`news_geo`（GDELT 地理事件）仅走地图层，**两者互不替代**。
- ❌ **没有编造任何点位**：所有 `newsGeoPoints` 都源自 `useFeed('news_geo')` 的真实 fetch 结果；适配器对非法坐标 / 缺失强度一律丢弃，不为缺失数据画占位点。
- ❌ **没有改 §2.6 / §2.7 的契约状态**：`news_geo.json` 仍是「**1.0 草案**」（待天枢首产回改定稿）；`market_quotes.json` 仍是无 §2.x 字段契约的预埋。本批只把"读取层就绪"前置到契约定稿前，**契约权威性仍以 DATA_CONTRACT.md 为准**。
- ❌ **没有动控制面 5 Tab 中「天枢」之外的 4 Tab UI 镜像**（保留镜像占位），仅清理其**死代码引用**并加注释；天枢 Tab 完整功能保留。

**工程**

- 新增 4 文件（`src/lib/newsGeoAdapter.ts` + 测试、`src/lib/newsGeoAdapter.test.ts`；**B5 测试用例数 28**）。
- 修改 6 文件：`src/config/dataSources.ts`（B1 + C2）/ `src/types/contracts.ts`（B2 + C2）/ `src/components/WorldPanel.tsx`（B3+B4.2）/ `src/panels/registry.ts`（A2 P2 死代码 4 处）/ `src/hooks/useControlApi.ts`（A2 1 处）/ `src/lib/controlApi.ts`（A2 2 处）。
- 测试 269 → 297（+28），**全量 297/297 通过**。
- 共享约定：所有 `MarketQuote` 字段名与 §2.6.3 表格中建议字段一致（`symbol` / `name` / `price` / `change_pct` / `updated`），新增 `category`（分类标签）便于未来面板分组；不破坏既有 12 类清单。

**质量验证（GO）**

- **单元测试 297/297 通过**（`npm test`，13 个测试文件：原 269 + 本批 +28）。
- `tsc --noEmit` 零错误；`vite build` 绿（10.84s）。
- **IS_PASS: YES**。

**产品决策**

- **C2 market_quotes 读取但不渲染**已拍板——避免「4/5 行情格有数据、1/5 留空」的残缺面板体验；天枢统一 `market_quotes.json` 形态后即转正。
- **B 节读取层骨架先行**已拍板——草案阶段就把读取 + 适配 + 接线做完，等数据即可上图；不依赖契约定稿节奏，避免 1 个 sprint 闲置。

## [1.5.0] - 2026-08-01 · 左侧指标树 LayerTreePanel（P1 纯前端收尾③）+ 底部图例精简

> 版本递进：**1.4.0 → 1.5.0**。本条目交付 P1 纯前端批的**最后一项**：对标开源 crucix monitor 左栏的「指标树」。零新依赖、纯前端、不改数据流，可独立验收。

**改了什么**

- **左侧指标树（新）**：新增 `src/components/LayerTreePanel.tsx`，做进 `WorldPanel` 内部、地图左侧的一列（`w-40 shrink-0 overflow-y-auto`）。12 类风险图层按落地阶段 `phase` 分成三个**可折叠**分组（`P0 已就位` / `P1 规划` / `P2 待后端`），组头显示 `本组已开/本组总数` 并带 `aria-expanded`；每个类别叶子行 = 形状色块（复用 `ShapeSwatch`）+ **状态灯** + 中文名（`truncate`）+ 计数（`tabular-nums`），整行即开关（`aria-pressed` + `data-off`）。战略要地作为独立一行（`StarSwatch` + 琥珀金）置于树顶，不进 phase 分组。树头提供全开 / 全关，树底在 `missingCount>0` 时提示「数据缺失 N」。
- **状态灯三态（新的诚实表达）**：`rowStatus()` 纯函数把「开且当前范围有数据 = live（青绿发光）」「开但当前范围无数据 = empty（灰）」「已关闭 = off（更淡的灰）」三种情况**显式区分**，DOM 上以 `data-status` 暴露。P2 图层恒为 0 点位是「等后端」，不是故障，也绝不因为空就伪装成 live。
- **底部图例精简**：`LayerLegend` 移除「战略要地开关」与「双列逐类别开关 grid」，收窄为「标题 + N/12 + 全开/全关 + 强度(尺寸/脉冲)说明 + 数据缺失徽标」。`LayerLegendProps` 相应收窄为 `{ visible, onSetAll, missingCount }`。`ShapeSwatch` / `StarSwatch` 改为 `export` 供左树复用，`LayerCountMap` 类型仍从此文件导出（`WorldPanel` 与左树共用）。
- **`WorldPanel` 布局**：原「地图容器」外层改为一行 flex —— `[LayerTreePanel] [地图容器 flex-1 min-w-0]`，两个子视图的绝对定位与 loading / error 覆盖层原样内移，未改任何渲染参数。
- **测试（+26，243 → 269）**：新增 `src/components/LayerTreePanel.test.tsx`（26 用例，6 个 describe）：12 类全渲染 / 战略要地行有无 / P0·P1·P2 组头与顺序 / 计数只来自 `counts` / 类别色源自 `CATEGORY_PALETTE` / 状态灯三态 / 逐类别 `onToggle` 参数正确 / `onToggleSites` 不误触 / 全开·全关回调与禁用态 / 组头折叠后叶子行不渲染 / `groupByPhase` 覆盖无遗漏 / 布局与无障碍属性。测试文件数 11 → 12。

**为什么这么改**

- **左树必须复用 WorldPanel 已有状态，不能自成一套**。`useFeed` 不做缓存，任何在别处重新 `useFeed('grv')` 的写法都会变成第二次网络请求 + 两份可能不一致的计数。因此左树是**纯受控组件**：`visible / counts / onToggle / onSetAll / missingCount / sitesVisible / onToggleSites` 全部由 `WorldPanel` 下传，组件内不 fetch、不建 Context、不自算计数。
- **同一个开关不能有两套 UI**。左树上线后若底部图例仍保留逐类开关，用户会看到两处状态、两处点击入口，迟早出现「我关的是哪一个」的困惑。故把开关**迁移**而非复制，底部图例只留全局动作与图注。
- **色块 SVG 只留一份**。`ShapeSwatch` / `StarSwatch` 从 `LayerLegend` 导出复用，而不是在左树里重画一遍 —— 否则地图符号、图例、左树三处形状迟早漂移。类别色一律走 `def.color`（源头是 `CATEGORY_PALETTE`），组件内零硬编码 hex，已由测试钉死。
- **按 phase 分组而不是按字母 / 按计数排**，是为了让「这层为什么是 0」当场可解释：P2 组头写明「待后端」，用户不会把未接入误读成数据丢失。

**明确没有改的（防误读）**

- ❌ **没有引入任何新依赖**（仍无 jsdom / testing-library）。新测试沿用项目既有做法：`renderToStaticMarkup` + 直接调用无 hook 的纯组件取元素树手动触发 `onClick`。
- ❌ **没有改数据流**：`useFeed` / `adaptGrv` / `mapData` / `nuclearData` / `GlobePanel` / `FlatMapPanel` / `RegionTabs` / `StatusBar` / `SignalStreamPanel` 全部零改动。图层显隐仍只由 `WorldPanel` 持有并写 `localStorage`（键位 `kaiyang.layerVisibility` / `kaiyang.strategicSitesVisible` 未变）。
- ❌ **没有编造任何计数**：所有数字都来自 `WorldPanel` 传入的 `counts`（当前地区范围口径），左树不做二次统计。
- ⚠ **折叠状态不持久化**：`LayerTreePanel` 内部 `useState` 持有「哪些分组展开」，默认全展开，刷新后回到默认。这是刻意的 —— 它是纯 UI 局部偏好，不值得再占一个 `localStorage` 键位。
- ⚠ **实现上的一处微调**：折叠状态放在 `LayerTreePanel` 这一层（而非每个分组各自 `useState`），并把全部标记抽成无 hook 的纯组件 `LayerTreeView` / `LayerTreeGroup` / `LayerTreeRow`。原因是项目无 jsdom，只有纯组件才能被直接调用做交互断言；对外行为（默认展开、点组头折叠）完全一致。

## [1.4.0] - 2026-08-01 · 地区 Tab（R-P1-02）+ 顶栏 KPI / 信号序号与选中联动（R-P1-03）

> 版本递进：**1.3.0 → 1.4.0**。本条目纳入 P1 纯前端批**剩余两项**：地区筛选 Tab 与顶栏 KPI + 信号流序号/选中联动。两项在设计文档中均标注「后端门控：否」，零新依赖、纯前端，可独立验收。

**改了什么**

- **地区 Tab（R-P1-02）**：新增 `src/config/regions.ts`，定义 6 个地区（全球 / 美洲 / 欧洲 / 中东 / 亚太 / 非洲）的 bbox 与派生工具（`regionOf` / `inRegion` / `regionCamera` / `regionPolygon`）。新增 `src/components/RegionTabs.tsx`（6 个 Tab，`aria-pressed` + 中文 title，选中态复用既有 `accent`）。`WorldPanel` 持有 region 状态并经 `localStorage` 键 `kaiyang.region` 记忆，同时过滤风险点位、战略要地与统计计数；2D 平面图按 bbox 走 `fitExtent` 重算投影，3D 地球按 bbox 中心 + 跨度估算高度走 `pointOfView` 飞行。
- **顶栏 KPI（R-P1-03）**：`StatusBar` 新增 `useFeed<NewsItem[]>('news')` 与**纯函数** `deriveKpis()`，输出「信号 / 新闻 / 主告警」三个 chip。主告警 >0 用红（rose），=0 用弱化琥珀。口径与信号流**共用同一套** `newsItemsOf` / `signalLevelOf` / `SIGNAL_DISPLAY_LIMIT`，不另抄判定逻辑。
- **信号流序号与选中（R-P1-03）**：新增 `src/state/SelectionContext.tsx`（`selectionReducer` 纯函数 + `SelectionProvider` / `useSelection`），挂载于 `App`。信号流每行加 `#序号` 前缀（等宽数字），行改为可点击 `button`（`aria-pressed` + 键盘可达），选中行加 accent 边框；再次点击同一行取消选中。`SignalRow` 抽成无 hook 的纯组件以便零依赖渲染测试。
- **测试（+83）**：新增 `regions.test.ts`(31) / `SelectionContext.test.tsx`(12) / `RegionTabs.test.tsx`(8) / `SignalStreamPanel.test.tsx`(19) / `StatusBar.test.tsx`(13)。node 环境无 jsdom，统一用 `renderToStaticMarkup`（react-dom 自带）+ 直接调用纯函数组件的方式断言，**未引入任何新依赖**。
- **顺带修的地雷**：`dataSources.ts` 在模块顶层裸读 `window`，导致任何 import 链触达 `useFeed` 的测试直接 `ReferenceError` 崩掉；改为 `typeof window === 'undefined'` 探测后再读（同时对未来 SSR 安全）。

**为什么这么改**

- 地区筛选的真值必须**只有一份**：bbox 定义在 `regions.ts`，2D 的 `fitExtent` 与 3D 的 `pointOfView` 都从它派生，避免两个视图各自硬编码一套「亚太是哪儿」而慢慢漂移。
- 顶栏 KPI 与信号流如果各算各的，迟早出现「顶栏说 40 条、列表显示 37 条」这种自相矛盾。因此 KPI 直接复用信号流的归一化与等级判定函数，并用测试钉死 `deriveKpis().signals === deriveSignals().length`。
- 选中态拆成 `selectedSignalKey`（行内选中）与 `focusPointId`（地图聚焦）两个正交槽位，是为了能**诚实表达**「选中了信号但没有可聚焦的地图点」，而不是随便挑个点位假装跳转。

**明确没有改的（防误读）**

- ❌ **没有伪造「点信号 → 地图跳转」**。当前 `news_export.json` 既无 lat/lng 也无点位 id，`Signal.focusId` 恒为 null，点击只做行内选中，tooltip 明写「该信号无地理坐标，暂不联动地图」。聚焦 API（相机飞行 + 光环高亮）已在 `GlobePanel` / `FlatMapPanel` 建好并通过**点击地图点位**验证可用；等天枢 GDELT `news_geo` feed 就绪、条目带上 `point_id` 后，无需改动组件即自动生效。
- ❌ **没有引入任何新依赖**，没有装 jsdom / testing-library / 地图交互库；2D 平面图仍不支持鼠标 pan/zoom（地区切换靠 Tab 重算投影）。
- ❌ **没有动 D1 颜色方案**：`CATEGORY_PALETTE` / `SEVERITY_COLORS` / 战略要地琥珀金一律未改，Tab 与选中态复用既有 `accent`，KPI 告警复用既有 rose / amber。
- ⚠ **地区 bbox 是静态矩形近似**，苏伊士等边界点会同时落入中东与非洲两个框（`inRegion` 双真，`regionOf` 按 `REGIONS` 顺序取首个），这是刻意保留的已知行为，已在 `regions.test.ts` 中钉死断言。

## [1.3.0] - 2026-08-01 · 战略要地叠加层（P1 第一刀）+ osint 死代码清除

> 版本递进：**1.2.0 → 1.3.0**。本条目纳入 P1 纯前端批的**第一刀**：战略要地常驻叠加层（双视图一致），以及天枢合规否决后的 osint 图层死代码清除。两者均不依赖后端 feed，可独立交付。

**改了什么**

- **战略要地叠加层（P1 新功能）**：新增 `src/data/strategicSites.ts`，内置 8 个国际公认地理要地种子（霍尔木兹 / 苏伊士 / 博斯普鲁斯 / 直布罗陀 / 马六甲 / 巴拿马运河 / 好望角 / 曼德海峡）。在 3D 地球（`GlobePanel`，customLayer 四角星 Sprite + 拉远隐藏标签）与 2D 平面图（`FlatMapPanel`，d3-geo 投影星形 + 窄屏隐藏标签）双视图叠加常驻标记 + 中文标签。
- **独立视觉与独立开关**：本层固定琥珀金 `PALETTE.amber`（#fbbf24），用四角星形符号明显区别于 RiskPoint 的圆点 / 菱形，**不进入 12 类风险色轴**。图例（`LayerLegend`）新增独立的「战略要地」开关（默认开），显隐经 `localStorage` 键 `kaiyang.strategicSitesVisible` 持久化，与分类图层键互不干扰。`WorldPanel` 持有该状态并下传两个子视图。
- **容错降级（K5 红线）**：`validStrategicSites()` 跳过坐标越界 / 缺字段 / 重复 id 的项，非法 `type` 回落 `chokepoint`、非法 `importance` 回落 1；空数据 / 投影失败只丢单层，绝不白屏。新增 `src/data/strategicSites.test.ts`（21 测试）覆盖坐标区间、必填字段、id/name 唯一、色值独立、显隐常量与脏数据降级。
- **osint 死代码清除（天枢合规否决）**：从 `CATEGORY_PALETTE`（`theme.ts`）、`LAYER_CATEGORIES`（`layerCategories.ts`，含联合类型与图例项）、`--ky-cat-*` 镜像（`index.css`）、`categoryColor` 分支与单测中**彻底移除 `osint`**。类别枚举由 13 收窄为 12（osint 永久删除 —— 不做社媒抓取），三处键集合（`CATEGORY_PALETTE` / `LAYER_CATEGORIES` key / `--ky-cat-*`）保持严格一致（`missing` 作为元状态色，在 palette 与 css 中均保留，但不计入 12 类）。

**为什么这么改**

- 战略要地是「常驻地理参照物」，与风险事件在语义上必须一眼可分：靠**固定色 + 星形符号 + 常驻标签**区分，而不是靠挤进类别色轴（那会稀释 D1「色相 = 类别」的编码）。因此把它设计成完全独立的叠加层，渲染器只读其预计算字段，不污染 12 类契约。
- osint 图层对应的社媒抓取能力已被天枢合规永久否决，残留的代码属于死代码，留着只会诱使后续维护者误以为该图层可用。趁本次 P1 改动一并清除，并钉死「三处键集合一致」的契约测试（K6），防止日后再次出现 palette / legend / css 漂移。

**明确没有改的（防误读）**

- ❌ **没有把战略要地塞进 `CATEGORY_PALETTE` 的 12 类色轴**，也没有给它分配风险严重度 —— 它只承载地理坐标与重要度（仅驱动符号尺寸），不参与任何风险数学。
- ❌ **没有改 `PALETTE` / `SEVERITY_COLORS` / `SEVERITY_LEGEND` / `MAP_THEME`**。`STRATEGIC_SITE_COLOR` 直接引用 `PALETTE.amber`，不复制 hex。
- ❌ **本次未做** P1 其余子项（news_geo 读取层、地区 Tab / 顶栏 KPI / 信号流序号等），保持改动面最小、可独立验收。

## [1.2.0] - 2026-08-01 · 分类图层体系（对标 CRUCIX MONITOR，P0）

> 版本递进：**1.1.0 → 1.2.0**。本条目纳入 Wave2 线 b（crucix 复刻）的 **P0-① 分类图层地基** + **P0-② 核设施图层与面板壳** + 对应 hotfix。Wave2 线 a（控制面 P0）见 1.1.0 条目，两条线并行、互不影响。

**改了什么**

- **视觉双轴落地（决策 D1）**：把过去「颜色 = 严重度」的单轴编码拆成两轴——**色相 = 图层类别**、**强度（尺寸 / 光环 / 脉冲速率）= 严重度**。同一屏上既能看出「这是哪一层」，也能看出「有多严重」。
- **分类图层枚举**：新增 `src/config/layerCategories.ts` 作为类别的**唯一真源**（13 类：地缘 / 事件 / 核设施 / 地理新闻 / 冲突 / 战略要地 / 空域 / 热异常 / 海上 / 太空 / 卫生 / 开源情报 / SDR，含 P0/P1/P2 阶段标注）；色值唯一真源在 `src/config/theme.ts` 新增的 `CATEGORY_PALETTE`，`src/index.css` 的 `--ky-cat-*` 只是 CSS 侧镜像。
- **缺失态元状态（决策 C2-A）**：`status==='missing'` 或 `value===null` 的点位**强制**灰 `#64748b` + 虚线描边 + 无光晕 + 无常驻标签，任何类别色都不得覆盖。让「无数据」再也不会被误读成「低风险」。
- **点位 id 命名空间**：`RiskPoint.id` 统一为 `${category}:${原始id}`（`geo:taiwan_strait` / `event:evt-xxx` / `nuclear:zaporizhzhia`），多图层合并时不再可能撞车。
- **核设施图层（P0 新增数据层）**：新增 `nuclear_sites.json` feed 契约 + 6 站静态种子（扎波罗热 / 切尔诺贝利 / 福岛第一 / 布什尔 / 宁边 / 三里岛）+ 「核设施监视」面板（`order: 8`）。地图上以**菱形**符号呈现，读数经 `readingToValue` 归一化到 0–100 统一量纲。
- **图层图例与开关**：新增 `LayerLegend`，双列、逐类别显隐、点位计数、全开 / 全关；选择经 `localStorage` 键 `kaiyang.layerVisibility` 持久化，且对**未来新增类别前向兼容**（老快照里没登记过的新类别按 `defaultVisible` 自动出现，而不是对老用户永久隐身）。
- **信号流双轴分离**：`SignalStreamPanel` 左侧竖色条改为**类别色**（与地图同色相），右侧脉冲点与等级文字保留**严重度色**。
- **契约文档**：`docs/DATA_CONTRACT.md` §1 登记 `nuclearSites`，新增 §2.5 完整字段定义与归一化规则。

**为什么这么改**

- 对标 CRUCIX MONITOR 后暴露的核心差距不是「面板不够多」，而是**信息维度只有一维**：所有点位共用一套严重度配色，用户无法区分「这是地缘风险还是核设施」。加一层数据只会让同色点位更挤，不会提升可读性。
- 类别枚举、色值、localStorage 键各自单一真源，是为了让后续 10 个 P1/P2 图层接入时「只加一处登记」，而不是每次都要改渲染器 —— 与既有的 `FEEDS` / `panelRegistry` 扩展标准同构。
- 渲染器保持**只读**（只读 `p.color / p.weight / p.shape / p.status`，不 import `layerCategories`），换算全部前移到 `lib/mapData.ts` / `lib/nuclearData.ts`。这是「3D 地球与 2D 平面图观感永远一致」的既有保证机制，本次没有破坏它。

**明确没有改的（防误读）**

- ❌ **没有引入任何数值 `severity` 字段**（决策 C1-A）。`RiskPoint.value`(0–100) 仍是唯一严重度数值、`weight`(0–1) 仍是唯一强度驱动源，`severity`(字符串 '低/中/高/缺失') 仍然**只是展示标签**，禁止参与着色 / 尺寸数学。类型定义处已加注释固化这条约束。
- ❌ **没有改 `PALETTE` / `SEVERITY_COLORS` / `SEVERITY_LEGEND` / `MAP_THEME`**。`CATEGORY_PALETTE` 是纯追加，且其中 5 个共用色直接引用 `PALETTE`，不复制 hex。
- ❌ **没有改 `RiskArc`**。地缘联动弧线仍按 `severityColor` 着色（P0 范围外），只是会随 `geo` 图层一起显隐。
- ❌ **没有改 `App.tsx`**。新面板只在 `src/panels/registry.ts` 数组**末尾追加**一项，既有 7 项的 `order` / `className` 一字未动。
- ❌ **没有新增任何 npm 依赖**。`package.json` 的 `dependencies` / `devDependencies` 与 1.1.0 完全一致，仅 `version` 行变化。
- ❌ **没有实现 13 类图层的后端采集**。P1/P2 的 10 个类别只在图例中以阶段徽标占位（计数为 0），等后端 feed 就绪后按扩展标准接入，前端无需重构。
- ❌ **前端不编造辐射读数**。静态种子只含站点属性（名称 / 国家 / 坐标 / 类型），`public/data/nuclear_sites.json` 开发快照的 `readings` 是空数组；无读数即显示「—」与灰色虚线菱形。

**工程**

- 新增 6 文件（`config/layerCategories.ts` + 测试、`config/nuclearSites.ts`、`lib/nuclearData.ts` + 测试、`components/NuclearWatchPanel.tsx`、`components/LayerLegend.tsx`、`public/data/nuclear_sites.json`），修改 11 文件。
- 单图层点位护栏 `MAX_POINTS_PER_LAYER = 2000` 已预埋在 `WorldPanel`，超限截断并告警，防止未来热异常火点类海量图层打死帧率。
- 尊重系统「减少动效」偏好（`prefers-reduced-motion`），脉冲动画自动关闭。

**修复（hotfix）**

- `src/lib/nuclearData.ts:199`：`level:'unknown'` 分支状态不自洽——后端显式给出 `'unknown'` 时，该分支未按「等同未给分级」处理，导致归一化结果与「数据缺失」判定不一致。现已改为与 `level` 缺失走同一条兜底路径（先试 `reading/baseline` 倍数推断，再判 `value=null`），并**补充回归用例钉死该行为**。
- 该 Bug 由 QA 双轮独立验证期间发现，是本批次**唯一一处源码缺陷**；修复后为零缺陷干净版。

**质量验证（GO）**

- **单元测试 139/139 通过**（`npm test`，含分类图层配色漂移守卫、缺失态强制降级、点位 id 命名空间、`readingToValue` 归一化与上述 hotfix 回归用例）。
- `tsc --noEmit` 零错误；`vite build` 绿。
- **QA 双轮独立验证**（两名 QA 分别独立执行，非交叉复核）结论一致：**GO**，源码缺陷 0。
- 已知不阻塞项（可选清理，未修）：`src/components/GrvPanel.tsx:118` 散落连线色 `#e2e8f0` 未走调色板；`src/index.css` 的 `--ky-cat-*` 仍是 `CATEGORY_PALETTE` 的手工镜像（已有漂移守卫测试兜底）。

**产品决策**

- **D1「颜色编码：类别 vs 严重度」已拍板为方案 A**：**色相 = 类别**，**严重度 = 尺寸 + 光环脉冲 + 亮度**。代码按此实现、QA 按此验证，后续无需再议。被否方案：B（颜色=严重度 + 形状=类别，10 种形状难辨识、2D/3D 实现成本高）、C（填充=类别 + 描边=严重度，小尺寸点位下描边几乎不可见）。
- 类别图例与既有 `SEVERITY_LEGEND`（低 / 中 / 高 / 缺失）**并存两栏**，不互相替代。

## [1.1.0] - 2026-08-01 · Wave 2 控制面第一版：天枢运维 Tab

**新增 — 控制面板（T01-T03，16 新文件 + 3 修改，零新依赖）**
- **右侧控制抽屉**：380px 玻璃拟态 + 滑入/滑出动画 + z-index 覆盖，状态条最右侧「🔧 控制台」toggle，不改变现有 7 面板网格。
- **五 Tab 导航**：天枢 / 天璇 / 天玑 / 玉衡 / 操作日志。天枢实现完整交互，其余三域用「建设中」占位。
- **天枢运维 Tab**：采集源卡片列表（状态指示灯 + 相对时间 + 元信息）+ 搜索过滤 + 批量重跑 + 暂停/恢复 + 调度频率调整。四状态覆盖（加载/错误/空/搜索无结果）。
- **三层进度反馈**：L1 按钮 spinner → L2 抽屉内嵌进度卡片 → L3 Toast 通知（success/error/info）。
- **防双击**：`lockedFetchers Set` + `idempotency_key`（`crypto.randomUUID()` 生成）。
- **操作日志**：localStorage 持久化，50 条滚动上限，自动裁剪。
- **操作安全**：高危确认弹窗（暂停/批量操作）+ Token 未配置警告横幅 + 401 自动清 Token。

**Mock 模式**
- `MOCK_ENABLED=true`（默认）：控制 API 全部内存模拟（5 个逼真 mock fetcher + 状态机流转）。后端就绪后改一行配置切真实 API。
- Mock 数据：fetch_earthquake / fetch_fred_history / fetch_gdelt_v1 / fetch_news_rss / fetch_akshare_mid，含 running/paused 不同状态与多样 schedule。

**设计文档**
- `docs/PRD_CONTROL_PANEL.md` — 控制面板交互概念 PRD（许清楚，v1.0）
- `docs/system_design.md` — 系统设计 + 任务分解（高见远，T01-T05）
- `docs/sequence-diagram.mermaid` + `docs/class-diagram.mermaid` — 附时序图与类图
- `docs/开阳控制面-后端接口需求-回复.md` — 后端 A3a 接口对齐回复

**工程**
- **零新 npm 依赖**：UUID 用 `crypto.randomUUID()`，Toast 自研（~95 行），fetch 封装原生，状态管理用 React Context + useReducer。
- **QA 验证**：2 轮审查通过，`tsc --noEmit` 零错误，12 项边缘场景全覆盖。
- **已知延后**：T04 操作日志 Tab + Token 设置面板（P1）、T05 vite proxy + 集成联调（P1）、天璇/天玑/玉衡控制交互（后端未就绪）。

## [1.0.3] - 2026-07-31 · 气候/灾害改为事件触发式告警柱

- **气候风险 / 自然灾害不再画常驻地图柱**：`grvDimensions` 新增 `renderBar?: boolean`，两维度置 `false`（保留 geographic 锚点供 GRV_ARCS 弧线使用），`buildRiskPoints` 据此跳过。
- **新增事件触发式告警柱**：`grv_latest.json` 新增**可选**契约字段 `events[]`（`GrvEvent`：id/type/label/lat/lng/value/note）。有事件时才在事件发生地画告警柱（⚠ 前缀 tooltip/标签、脉冲光环、平面图放大点位）；缺省时不渲染（`buildEventBars` 优雅降级返回空数组）。
- `public/data/grv_latest.json` 追加两条演示事件（土耳其地震 / 巴基斯坦洪涝），正式环境由后端事件 feed 提供。

## [1.0.2] — 2026-07-30 · 视觉增强（Wave 1 观感升级，对标 crucix）

**新增 / 增强（构建通过 IS_PASS: YES，双工程师独立验收）**
- **3D 地球质感升级**：深空星野背景、经纬网格、脉冲光环、常驻点位标签、青绿大气辉光、粗渐变弧线。
- **新增平面地图视图**（d3-geo + topojson-client + world-atlas 离线 SVG）：跨 180° 经线大圆弧断线处理、流动虚线弧、点位光晕 + hover tooltip。
- **WorldPanel 取代旧 WorldViewPanel**：3D/平面双视图常挂载 + 显隐切换（避免反复重建 WebGL 上下文），localStorage 记忆视图模式，共享同一份 points/arcs。
- **侧栏新增三小卡**：RiskSummaryPanel（composite 头条 + Top6 geographic 进度条）、SignalStreamPanel（news→Signal 三色脉冲）、StatusMiniPanel（时间戳/版本/告警/推演触发）。
- **统一配色体系**：`src/config/theme.ts` 单一调色板 + severityColor/severityGlow；tailwind accent 改 `#5eead4`，新增 warn/danger；index.css 星野/扫描线/辉光动画。

**数据层修正**
- **composite 分类**：`grvDimensions` 加 `kind` 字段（geographic/composite），composite 维度（global_composite/global_south）不再投影到球面（消除"全球指数落在非洲"的孤点），改走头条 + 侧栏表达。
- **GRV_ARCS 改为全 geographic 端点连线（10 条）**；原 composite 端点弧线改指真实地理端点，避免弧线数量掉档。
- `mapData.ts` 新增 buildRiskPoints/buildRiskArcs/tooltip 生成；readLayer fetchText 并发去重。

**工程杂项**
- 依赖钉死复确认：`three` 与 `@types/three` 精确 `0.185.1`（防 Matrix4.determinantAffine 缺失崩溃）。
- vite manualChunks 拆 geo chunk；删孤儿 WorldViewPanel.tsx；移除 playwright devDep（仅验证用，不进依赖）。
- `public/` 内联 earth 贴图 / night-sky / countries-110m.json（离线打包，不依赖外部 CDN）。

## [1.0.1] — 2026-07-30 · 修复地球面板空白 Bug

**修复（BugFix，构建通过 IS_PASS: YES，headless 验证）**
- **根因**：`globe.gl ^2.32.0` 实际解析到 `2.46.1`，要求 `three >=0.179`；原顶层 `three ^0.169.0` 过旧，npm 嵌套装了重复 three 实例。three-globe 内部调用 `Matrix4.determinantAffine()`（需 `three >=0.185.1`），顶层旧版缺失 → 渲染循环异步抛错（React 无法 try/catch）→ 地球 canvas 渲染失败、容器空白。
- **版本钉死**：`package.json` 中 `three` 与 `@types/three` 精确锁定 `0.185.1`，`globe.gl` 升至 `^2.46.1`，消除重复 three 副本。
- **GlobePanel.tsx 重写**：`new Globe(el)` 规范初始化；显式 `width/height` + `ResizeObserver` 防 0 尺寸；`try/catch` 失败渲染红色错误文本（不再静默空白）；完整 cleanup（rAF/ResizeObserver/destructor）。
- **真实地球纹理**：新增 `public/assets/earth-blue-marble.jpg`（NASA 蓝大理石，本地打包离线可用），地球不再是无纹理光球。

**验证**
- headless（playwright + chromium）实测：canvas 781×954、pageerror 0、截图确认真实地球 + 青绿大气 + 风险点 + 联动弧线正常渲染。

## [1.0.0] — 2026-07-30 · Wave 1 交付

**新增（Wave 1，构建通过 IS_PASS: YES）**
- 完整 Vite + React + TS + Tailwind 静态站，前端操作面板（展示 + 控制双职能）；读侧只读天枢契约文件，写侧为受控指令通道（协议暂缓）。
- 3D 地球面板（globe.gl）：11 维 GRV 风险点 + 地缘联动弧线（上游无坐标时按内置 11 维锚点）。
- GRV 面板（ECharts）：各维度数值 + 不确定区间（误差带 / 扇形），区间缺失时按 8% 估算并标记 `uncertaintyEstimated`。
- 经济面板（ECharts）：FRED 关键序列（manifest 14 个）。
- 新闻 / 叙事面板：`news_export` 条目列表（兼容纯数组与包装对象两种形态）。
- 顶部状态条：数据时间戳 + 缺失字段告警 + schema 版本收集。

**扩展标准（用户硬性要求，已预埋）**
- 统一读取层 `useFeed` + `readLayer`；面板注册表 `panelRegistry`；字段容错降级；feed `schema_version=1.0`；数据契约权威文档 `DATA_CONTRACT.md`。

**对齐 monorepo 文档体系**
- 文档重组对齐 macro-sim：根目录 `README.md` / `AGENTS.md` / `CHANGELOG.md` / `VERSION`；设计总纲 `docs/DESIGN.md` 与数据契约 `docs/DATA_CONTRACT.md` 移入 `docs/`。

**已知偏差（不阻塞）**
- 上游 `grv_latest.json` 仅含 ~6 维度键、无 lat/lng、无不确定区间字段；`news` 上游实为 `latest_news.json`。均由适配层 + 状态条降级渲染，不白屏。
- 构建有 chunk 体积告警（echarts ~1MB、主包 ~2.3MB），Wave1 可接受；后续可按需引入或拆包优化。

**未做（留待后续）**
- Wave 2：接入天璇（D.hypothesis）/ macro-sim（D.sim）/ 天玑（D.verification）新格式，新增面板 = 只加 `panelRegistry` 注册项。
- SSE / 实时推送：Wave1 静态 + 前端加载，实时机制留待后续。
- NAS 部署（:3118 只读挂载）与 world-sim git 纳管：待用户在 NAS 主机侧执行。
## [1.10.4] - 2026-08-11 · 缩放半补偿：缩小后图标随地图缩小（crucix 式）（by arch-map + lead 收尾）

**修改理由**：主理人反馈“地图缩小后所有图标仍偏大”——2D 完全恒定补偿 scale(1/k) 使点视觉尺寸不随 zoom 变化，缩小后图标不缩小。

### 修改

- FlatMapPanel.tsx：抽常量 INV_SCALE_EXP = 0.5，applyPointInvScale 补偿公式由 1/k（完全恒定）改为 1/pow(k, 0.5)（crucix 半补偿，参考 jarvis.html 点随 zoom 微缩放）
- 三个调用点（zoom handler / buildPoints 重建后 / 聚焦环重建后）统一走 applyPointInvScale，一处公式覆盖三处
- 效果：缩小后图标随之变小（比地图缩小慢、保持可读）；放大后图标变大（比地图放大慢、不膨胀）

### 验证

- npm test 14 files / 311 tests 全绿；vite build 本地构建成功（新 bundle index-BPRw4Zr7.js）
- scp 原地覆盖 + chmod -R a+rX；nginx 新 bundle 200；18/18 feed 200

## [1.10.5] - 2026-08-11 · 事件弹框：点击事件点查看详情 + 同地点新闻列表（by lead 实施）

**修改理由**：主理人反馈“现在只能看到提到次数，不知发生了什么”——点击事件点应能列出该地点新闻。

### 修改

- 数据契约：DATA_CONTRACT §2.7 NewsGeoEvent 正式增补 source_url（GDELT SOURCEURL；此前为隐性扩展字段）
- lib/newsGeoAdapter.ts：新增导出 sanitizeUrl（仅放行 http/https，防 javascript: 伪协议注入，XSS 防线）；normalizeEvent 透传 source_url；RiskPoint 生成填充 sourceUrl
- lib/mapData.ts：RiskPoint 增可选 sourceUrl 字段
- components/EventPopup.tsx（新建）：点击事件点弹固定位弹框——选中点详情（地点/国家/类型/时间/强度）+「查看新闻原文」链接 + 同地点事件列表（按 location_name 过滤当前 feed，最多 10 条，含各自原文链接）；关闭按钮 SVG（禁 emoji）；全字段 React 默认转义 + href sanitizeUrl 双保险
- components/WorldPanel.tsx：popupPoint state + relatedEvents 过滤 + handlePointClick 联动（聚焦 + 弹框同步开闭）+ 渲染 EventPopup

### 验证

- npm test 14 files / 311 tests 全绿；vite build 本地构建成功（新 bundle index-BUiWhYtr.js / index-C6xX4dKN.css）
- scp 原地覆盖 + chmod -R a+rX；nginx 新 bundle 200；18/18 feed 200；v1.10.2 旧 bundle 按 DEPLOYMENT 规范清理

## [1.10.6] - 2026-08-11 · 图标整体收窄 ×0.8 + 弹框同新闻合并 + event_type 启发式（unknown 清零）

**修改理由**：主理人复核三项——①展示图图标仍偏大需缩小；②同地点新闻多条是同一篇（GDELT 一篇报道拆多事件）；③事件标题大量 unknown 不可读。

### 修改

- 前端尺寸收窄（×0.8，2D/3D 联动）：
  - FlatMapPanel.tsx：中心 core clamp[3,9] → clamp[2.4,7.2]（3+6w → 2.4+4.8w，两处：点渲染 + 聚焦环）
  - GlobePanel.tsx：pointRadius 0.4+0.25w → 0.32+0.2w；ringMaxRadius (3.5/2.2)+2.2w → (2.8/1.76)+1.76w
- EventPopup.tsx 同新闻合并：按 source_url 去重（GDELT 一篇报道常拆成多条事件），保留 mention 最高条目，dup 徽标 ×N；列表标题显示「去重后 N」
- 后端 fetch_gdelt_geo.py `_map_event_type` 启发式兜底：缺失 root_code 的旧行 Goldstein<=-4 → conflict、其余 → political（消除 unknown 标题；标注启发式非 CAMEO 权威，随窗口滑动被带码新行替换）。实测分布：unknown 597→0、conflict 123、political 489

### 验证

- 前端：npm test 14 files / 311 tests 全绿；vite build 本地构建（新 bundle index-BxnJs6nn.js / index-S7YTSnTj.css）；scp 原地覆盖 + chmod；bundle + feed 200
- 后端：热挂载生效 + 容器内 _map_event_type 单测（-6→conflict/0→political/14→protest/15→conflict）+ --export-json 实测 news_geo.json 612 events unknown=0

## [1.10.7] - 2026-08-11 · 视觉降噪（vis-fe 评估 + lead 仲裁落地）——点/环再收窄 + Top-80 标签 + 6 空层默认关

**修改理由**：主理人两轮反馈「图标依旧大」「内容看着还是乱」。vis-fe/vis-fe-2 双评估（docs/vis-eval-2026-08-11-arbitration.md 仲裁）：真凶不是点本身（3D 点仅 1-3px）而是 46% 点带常驻标签+外环互相遮挡 + 同地点无聚合。

### 修改（10 项，合并仲裁版）

- FlatMapPanel.tsx：core clamp[2.4,7.2] → clamp[1.6,4.6]（1.6+3w）；外环 core×1.8→×1.5；内层 halo ×1.35→×1.2；聚焦环 core×2.4/12 → core×2.0/8
- GlobePanel.tsx：pointRadius 0.32+0.2w → 0.22+0.14w（缺失 0.18）；ringMaxRadius (2.8/1.76)+1.76w → (1.9/1.2)+1.1w；ringPropagationSpeed (1.8/1.0)+1.2w → (1.5/0.8)+0.8w；**常驻标签 Top-80 截断**（intensity 降序，聚焦点恒首位，悬停 tooltip 不受影响）
- mapData.ts：HIGHLIGHT_THRESHOLD 55 → 70（281→~110 个标签，与 SEVERITY_THRESHOLD.high=66 对齐）
- layerCategories.ts：air/thermal/maritime/space/health/sdr 六个 P2 空占位层 defaultVisible true→false（news/conflict 保持可见，lead 仲裁：开阳核心新闻图层不默认关）

### 验证

- npm test 14 files / 311 tests 全绿；vite build 本地构建（新 bundle index-oJgF4qMk.js / css 沿用 S7YTSnTj）
- scp 原地覆盖 + chmod -R a+rX；root/js/css/news_geo 200；旧 bundle 按 DEPLOYMENT 规范留 3 版清理（v1.10.0-1.10.4 共 9 个删除）

## [1.11.10] - 2026-08-15 · P2 收官：health 卫生监视图层（GDELT GKG 卫生事件）

**修改理由**：P2 最后一块拼图。maritime 数据源受阻（AISStream 服务端哑 / AISHub 贡献制 / ShipXplorer 参数未破解）暂缓；health 用 GDELT GKG（免费无 key、坐标现成）落地。

### 修改

- **后端天枢**（fetch_health_geo.py，新建）：GDELT 2.0 GKG 增量（27 列 .gkg.csv.zip，V1Locations 含坐标）→ 卫生爆发级关键词过滤（outbreak/epidemic/pandemic + 具体疾病，排除 pandemic loan 类噪声）→ 坐标事件提取；I60 增量（state 记录已处理 slot，最多补拉 8 slot）；保留 72h 窗口去重累积；实测 2h 窗口 26 条事件坐标全合法
- **前端**：
  - `contracts.ts`：HealthGeoRaw / HealthEventRaw
  - `dataSources.ts`：+ health_geo feed
  - `layerCategories.ts`：health def 更新（feed 'health_geo'、shape dot、desc）——**P2 7 类全部接入，feed null 占位清零**
  - `lib/healthAdapter.ts`（新建）：events → RiskPoint[]（**air/thermal/space 教训复用：value null + severity 中性「卫生」+ weight 0.5 + note 关键词/地点/时间**）
  - `WorldPanel.tsx`：healthPoints 合并（K7 常规点区）
  - 测试：+healthAdapter.test（6 用例）
- **运维**：NAS 意外断电 + fnOS 升级排查（天枢 exit 126 根因 = 升级把 entrypoint.sh 权限 755→700，chmod 修复；.sh 统一修回 755）

### 验证

- 后端实跑：26 条卫生事件（cyclosporiasis 爆发/麻疹/霍乱等）/ 坐标全合法 / 72h 窗口增量正确
- tsc + vitest（本地沙箱规避方案）+ vite build 后 scp 部署
- 视觉项由主理人浏览器复核

## [1.11.9] - 2026-08-14 · 3D 地球移除 aircraft 实时航班（用户拍板）

**修改理由**：用户拍板「实时航班放 3D 无意义且 12503 点耗资源」——globe 模式过滤 aircraft，flat 保持降采样；3D 保留航线网/弧和其他图层。

### 修改

- `WorldPanel.tsx`：displayPoints 视图分层——flat 降采样 aircraft / globe 过滤 aircraft
- 验证：346 tests 全绿；vite build（`index-Bh70v3Zd.js`）scp 部署

## [1.11.8] - 2026-08-14 · P2 续接：space 太空活动图层（Next Spaceflight 发射记录）

**修改理由**：用户问「继续推进」→ P2 剩余三源调研：space 实测可达（免费无 key，需浏览器 UA 否则 403）、health 的 WHO RSS 已 404（暂缓）、maritime 免费源覆盖受限（暂缓，需注册 key）→ space 先接入。

### 修改

- **后端天枢**（fetch_spacelaunch.py，新建）：Next Spaceflight Launch Library 2（upcoming 未来计划 + previous 最近完成），解析发射场 pad 坐标；**必须带浏览器 UA**（无 UA 403 实测）；直连→代理回退；落盘 `spacelaunch.json`（130 条，坐标全合法）；scheduler 0705 日档（发射事件低频）
- **前端**：
  - `contracts.ts`：SpaceLaunchRaw / SpaceLaunchItemRaw
  - `dataSources.ts`：+ spacelaunch feed
  - `layerCategories.ts`：space def 更新（feed 'spacelaunch'、shape triangle→dot、desc）
  - `lib/spaceAdapter.ts`（新建）：launches → RiskPoint[]（**air/thermal 教训复用：value null + severity 中性「太空」+ weight 0.5 + note 时间/状态/火箭**）
  - `WorldPanel.tsx`：spacePoints 合并（K7 常规点区）
  - 测试：+spaceAdapter.test（5 用例）；346 tests 全绿

### 验证

- tsc 通过；346 tests 全绿；vite build（新 bundle `index-cs9ILczn.js`）scp 部署；index / bundle / spacelaunch feed 200
- 后端实跑：130 条（upcoming + previous）/ 坐标全合法 / 样本 Falcon 9 USSF-366 @范登堡
- 视觉项由主理人浏览器复核

## [1.11.7] - 2026-08-14 · thermal 风险语义中性化（用户追问「风险值怎么定的？非洲/西伯利亚相当高」）

**修改理由**：主理人追问 thermal 风险值——原 value=count 归一化使西伯利亚（1800 火点/格 value 99）和非洲（1391 火点 value 77）显示「高风险」，但**火点密度 ≠ 人类风险**（无人区森林大火/季节性烧荒 vs 人口区山火），与 air「高度≠风险」同款语义错误。

### 修改

- `lib/thermalAdapter.ts`：value 恒 null（不显示误导风险值）+ severity 中性「火点活跃」+ weight=count 归一化（0-1）仅驱动点大小/3D 高度 + note 真实火点数/FRP/高置信（hover 看）；删除 aggCount
- 测试：thermalAdapter.test 断言更新（value null / severity 中性 / weight 归一化 / aggCount 无）；341 tests 全绿

### 验证

- tsc 通过；341 tests 全绿；vite build（`index-BaNLJpp6.js`）scp 部署；index / bundle 200
- 视觉项由主理人浏览器复核

## [1.11.6] - 2026-08-14 · thermal 去中心计数徽标（用户反馈「数字去掉」）

**修改理由**：527 格密集区中心数字糊成一片；火点数信息移到 hover tooltip（note 已含 count/FRP/高置信）。

### 修改

- `FlatMapPanel.tsx`：dot 分支删除 isAgg 计数 text（仅 dot 类；circle 聚合徽标保留给 news 同城聚合）
- 验证：341 tests 全绿；vite build（`index-Cykfn9Ze.js`）scp 部署

## [1.11.5] - 2026-08-14 · thermal dot 圆点缩小（用户反馈「圆太大」）

**修改理由**：dot 分支误用聚合 core（isAgg ? 5~9px），thermal 全带 aggCount 走了聚合放大 → 527 格全是大圆。

### 修改

- `FlatMapPanel.tsx`：dot 分支改用普通点公式 `1.6 + weight*3.0 clamp[1.6,4.6]`（计数已由中心徽标表达，点无需 log2(count) 放大）
- 验证：341 tests 全绿；vite build（`index-D1JxghQ2.js`）scp 部署

## [1.11.4] - 2026-08-14 · 2D 平面图 aircraft 降采样护栏（用户反馈「平面图就非常卡」）

**修改理由**：rAF 节流 + dot 简化后 2D 仍卡——最大头是 aircraft 6182 箭头（SVG 每点 group+path+监听）。用户授权「筛一筛或缩小显示」→ flat 模式降采样，globe 3D 保持全量（WebGL 可扛，且用户拍板过全量）。

### 修改

- `lib/mapData.ts`：`MAX_FLAT_LAYER_POINTS = 1500` + `downsampleLayer(points, category, max)`——stride 均匀抽样（保持空间分布），非目标图层原样保留；渲染器无过滤职责（K6），降采样只在本数据层做
- `WorldPanel.tsx`：`displayPoints` = flat 模式对 aircraft 降采样 / globe 全量；regionPoints/visiblePoints 走 displayPoints
- 测试：mapData.test +3（不超限原样 / 超限均匀降采样且他层保留 / 上限常量）；341 tests 全绿

### 验证

- tsc 通过；341 tests 全绿；vite build（新 bundle `index-DdjydWdV.js`）scp 部署；index / bundle 200
- 效果：2D aircraft 6182 → ~1500（均匀），总点位 2D ≈ 3400（aircraft 1500 + sdr 851 + thermal 527 + 常规），SVG 流畅
- 视觉项由主理人浏览器复核

## [1.11.3] - 2026-08-14 · 2D 渲染防卡顿双管齐下（用户反馈「还是卡」）

**修改理由**：thermal 等级筛选后仍卡（527 格 + aircraft 6182 + sdr 851 全开 ≈ 8000+ 点 / 3.2 万事件监听）。定位：①鼠标扫过时每个点 mousemove → setTooltip 高频 React 重渲染（每帧多次 state 更新 → 整幅 SVG 重渲染）；②circle 渲染每点 4 元素（环+光晕+圆+徽标）DOM 过重。

### 修改

- `FlatMapPanel.tsx` **tooltip mousemove rAF 节流**：所有点/弧的 mousemove 合并到 `requestAnimationFrame` 每帧最多 1 次 setTooltip（`scheduleTooltipMove` + pending ref + unmount 清理）；mouseleave 清 pending
- `FlatMapPanel.tsx` + **dot 渲染分支**：只画核心圆（missing 虚线兜底）+ 聚合计数徽标，无外环/光晕——每点省 2 元素
- `layerCategories.ts`：PointShape + 'dot'；thermal/sdr def shape circle→dot（图例与地图一致）
- `LayerLegend.tsx`：ShapeSwatch + dot 图例（小实心点）
- 测试：合法 shape 列表 + 'dot'；338 tests 全绿

### 验证

- tsc 通过；338 tests 全绿；vite build（新 bundle `index-BwASTqV3.js`）scp 部署；index / bundle 200
- 预期：鼠标扫过不再每帧重渲染（rAF 合并到 60fps 上限）；thermal/sdr 元素数减半
- 视觉项由主理人浏览器复核

## [1.11.2] - 2026-08-14 · thermal 热异常等级筛选防卡顿（用户反馈「太占资源直接卡住了」）

**修改理由**：thermal 全量渲染 4031 个网格点 × 4 SVG 元素/点（环+光晕+圆+计数徽标）≈ 1.6 万元素 + 4000+ 事件监听，叠加 aircraft 6182 箭头 / sdr 851 点后直接卡死。用户要求「有等级划分就筛一下」。

### 修改

- `lib/thermalAdapter.ts`：**等级 = 网格火点 count 分档**（极高 ≥500 / 高 ≥100 / 中 ≥50）；新增 `MIN_THERMAL_COUNT = 50`——count < 50 的零星火点格（占 87%：4031→527 格）不渲染；剩余 527 格按 value 归一化的 severityLabel 分档（低/中/高），hover 看具体火点数 / FRP
- `layerCategories.ts`：UNCAPPED_LAYERS 移除 thermal（筛选后 ~500 格远低于护栏，保留护栏兜底防火点爆炸；aircraft 仍 UNCAPPED）
- 测试：thermalAdapter.test 数据改 ≥50 + 新增筛选断言（49/1 火点格被滤掉）；338 tests 全绿

### 验证

- tsc 通过；338 tests 全绿；vite build（新 bundle `index-CztpNBcr.js`）scp 部署；index / bundle 200
- 效果：thermal 渲染 4031 → 527 点（~2100 元素），总点数 aircraft(6182) + sdr(851) + thermal(527) 流畅
- 视觉项由主理人浏览器复核

## [1.11.1] - 2026-08-14 · P2 图层续接：sdr 软件无线电 + thermal 热异常（数据源已就绪顺势接入）

**修改理由**：用户问「还有什么要推进」→ P2 剩余图层中数据源已就绪的两块先接（sdr_summary.json 851 接收器含坐标、firms_fire.json 火点）。

### 修改

- **sdr 图层**（纯前端，数据源零改动）：
  - `contracts.ts` SdrSummaryRaw / SdrReceiverRaw（注意后端字段是 `lon` 非 `lng`）
  - `lib/sdrAdapter.ts`（新建）：receivers → RiskPoint[]（active→ok / 非 active→missing 灰；value null + severity 中性 'SDR'，air 教训复用）
  - `layerCategories.ts`：sdr def 更新（feed 'sdr'、shape square→circle 图例地图一致、desc）
- **thermal 图层**（后端 + 前端）：
  - `fetch_firms.py`：**date 修复**（结束日期「今天」→「昨天」——FIRMS NRT 对 date=今天返回 0 行，实测 08-14 0 行 / 08-13 有 7.6 万行；这是长期潜伏 bug，早上跑必 0）；`_aggregate` 输出 **1° 网格聚合 hotspots**（格心 + 火点计数 + 最强 FRP + 高置信数，7.6 万+7.7 万行 → 4031 格，DECISION_MATRIX D2 后端预聚合）
  - `contracts.ts` FirmsRaw / ThermalHotspotRaw；`dataSources.ts` + firms feed
  - `lib/thermalAdapter.ts`（新建）：hotspots → RiskPoint[]（value = 火点计数归一化 = 热异常活跃度，aggCount 计数徽标，note 含 FRP/高置信）
  - `UNCAPPED_LAYERS` + thermal（聚合后全球 4031 点全量渲染，截断无意义）
- WorldPanel：sdrPoints + thermalPoints 合并（K7 顺序：常规点区，nuclear 之前）

### 验证

- tsc 通过；337 tests 全绿（+10：sdrAdapter 5 + thermalAdapter 5）
- 后端实跑：total=152978 火点 / 1° 网格 4031 点 / 坐标全合法 / 中国 321 格、非洲 1045 格、南美 553 格（西伯利亚 1812 火点 top 格，真实数据）
- vite build（新 bundle `index-CfjqlYsM.js`）scp 部署；index / bundle / sdr / firms feed 全 200
- 视觉项由主理人浏览器复核

## [1.11.0] - 2026-08-14 · air 图层重构：全球航线网（弧）替代实时飞机点 + 新增 aircraft 子图层（用户拍板）

**修改理由**：主理人发现实时航班图层「非洲/中国上空基本空」——经实测与查证，OpenSky 是众包 ADS-B 接收器网络，非洲/中国/俄罗斯内陆接收器稀疏，那些区域航班收不到信号（俄罗斯上空欧亚航线仅 11 点是最硬证据），**是数据源覆盖盲区而非 bug**。主理人拍板：air 图层改为**静态全球航线网**（OpenFlights 结构数据，全球主要航线完整、无盲区），实时飞机点降级为独立 aircraft 子图层（默认关、desc 标注盲区）。

### 修改

- **后端天枢**（fetch_airroutes.py，新建）：
  - 容器出网（直连→代理回退）拉 OpenFlights `airports.dat` + `routes.dat`（CC BY-SA 4.0，~2014，全球航线结构稳定）
  - 解析 7698 机场坐标 + 过滤直飞/非代码共享航线，机场对聚合频次、双向合并，取 **top 500 主要航线**
  - 产出 `airroutes.json`（from/to IATA + 两端坐标 + flights 频次），落 `/workspace/data/`，scheduler 日档 0950（结构数据日更远超所需）
  - 实测：500 条 / 坐标全合法 / 中国枢纽航线 96 条 + 非洲区域航线 42 条（盲区从根上解决）
- **前端**：
  - `contracts.ts`：AirRoutesRaw / AirRouteRaw 类型（schema_version 继承 RiskSignalBase string）
  - `dataSources.ts`：+ airroutes feed
  - `layerCategories.ts`：`LayerCategory` + `aircraft`；`PointShape` + `arc`；air 改「全球航线」shape=arc feed=airroutes；aircraft 新增「实时航班」shape=arrow feed=airtraffic defaultVisible=false（盲区标注在 desc）；`UNCAPPED_LAYERS` air→aircraft
  - `theme.ts`：`CATEGORY_PALETTE` + `aircraft: #38bdf8`（天蓝，与 air 翡翠绿同族区分）；index.css 镜像同步
  - `lib/airRoutesAdapter.ts`（新建）：airroutes.json → RiskArc[]（复用既有 2D greatCircleArc / 3D arcsData，零新渲染代码；intensity = 航线繁忙度 20-100 线性归一化，非风险语义；颜色固定 air 翡翠绿）
  - `lib/airTrafficAdapter.ts`：category/id 前缀 `air`→`aircraft`，头部注释补覆盖盲区说明
  - `WorldPanel.tsx`：airRouteArcs + visibleArcs 合并（geo 联动弧 + air 航线弧分开关显隐）
  - `LayerLegend.tsx`：ShapeSwatch + arc 图例（小弧线）
  - 测试：+airRoutesAdapter.test（5 用例）；layerCategories/LayerTreePanel 断言 12→13 类别 + UNCAPPED aircraft；全量 **327 tests 全绿**

### 验证

- tsc --noEmit 通过；vite build 本地构建（新 bundle `index-haZ1gfS0.js` / `index-BlNeBOU6.css`）
- scp 原地覆盖 + chmod；index / 新 js / 新 css / airroutes / airtraffic feed 全 200
- 后端实跑：routes_count=500 / airports_indexed=7698 / 落盘 /workspace/data/airroutes.json（重启后仍在）
- 视觉项由主理人浏览器复核

## [1.10.9] - 2026-08-14 · air 空域活动图层：只画航向箭头 + 全量显示（用户拍板）

**修改理由**：主理人复核 08-14 air 图层接入后两点意见——①2D 平面地图上方向箭头与圆点重叠，有箭头就不需要圈；②点位被单图层护栏截断后只剩部分航班，缺一部分的数据没意义，要求全量显示。

### 修改

- `src/config/layerCategories.ts`：`PointShape` 新增 `'arrow'`（方向型渲染模式）；air 类别 `shape` `'triangle'`→`'arrow'`（图例与地图符号一致）；新增 `UNCAPPED_LAYERS`（含 air——08-14 用户拍板全量显示，不受 `MAX_POINTS_PER_LAYER=2000` 护栏截断，其余图层护栏不变）
- `src/lib/airTrafficAdapter.ts`：air 点 `shape` → `'arrow'`；头部注释同步最新事实（全量 6182 点 / weight 0.5 统一大小 / shape arrow 语义）
- `src/components/FlatMapPanel.tsx`：新增 `shape==='arrow'` 分支——只画航向旋转箭头（`direction` 缺失时朝北兜底，d3 attr 不接受 undefined 用空串），不画圆点 / 外环 / 光晕；circle 分支移除原 direction 叠加逻辑（arrow 成为唯一箭头载体）
- `src/components/WorldPanel.tsx`：`capPointsPerLayer` 对 `UNCAPPED_LAYERS` 豁免截断（air 全量渲染，其余图层仍受护栏保护）
- `src/components/LayerLegend.tsx`：`ShapeSwatch` 新增 arrow 图标（底部图例 / 左侧指标树与地图符号一致）
- `src/config/layerCategories.test.ts`：+`UNCAPPED_LAYERS` 断言；合法 shape 列表 +`'arrow'`

### 验证

- `npm test` 15 files / 321 tests 全绿（+1）；`tsc --noEmit` 通过；`vite build` 本地构建成功（新 bundle `index-CG5qCmNJ.js` / `index-CW8B4ZOt.css`）
- scp 原地覆盖 + `chmod -R a+rX`；root / 新 js / 新 css / `airtraffic_opensky.json` 均 200
- feed 实测：coordinates **6182 点全量**、track 覆盖 **100%**（箭头渲染数据完全支撑；OpenSky 按请求计费不按条数，全量零额外成本）
- 视觉项由主理人浏览器复核：2D 空域图层只见航向箭头无圆点圈、全量航班

## [1.10.8] - 2026-08-11 · 同地点聚合：一城一点 + 计数徽标 + 弹框列全部事件

**修改理由**：主理人反馈「同一地点事件是分开的，比如北京不止一条」——GDELT 对同一地点用城市中心坐标，但 location_name 存在拼写变体（Beijing/Peking、Washington/White House/Lincoln Memorial），同城新闻被拆成多个点。

### 修改

- lib/geoAggregate.ts（新建，<300 行）：`aggregateNewsGeo`——聚合主键 = 坐标格（0.1° ≈ 11km，城市级；实测同城同坐标，Peking/Beijing 自动合并、深圳/香港不误并）；代表事件 = mention 最高；聚合点强度 = 组内最严重事件（max intensity）；提及数求和；返回 childrenByPointId 供弹框
- lib/mapData.ts：RiskPoint 增 `aggCount?`（>1 = 聚合点）
- components/WorldPanel.tsx：newsGeoPoints 改用聚合；弹框事件源 = 聚合组 children（替代 location_name 过滤，更准）；点击仅 news/conflict 弹框（GRV/核设施只聚焦）；标题 emoji 移除（P0 红线）
- components/FlatMapPanel.tsx：聚合点 core = clamp(5,9,4+log2(count)*1.3) + 中心白色计数徽标（pointer-events none）；聚焦环对齐聚合尺寸
- components/GlobePanel.tsx：聚合点 pointRadius 0.34+log2(count)*0.08（hover tooltip 显示「N 条事件」）
- lib/newsGeoAdapter.ts：normalizeEvent 导出（供聚合复用）
- lib/geoAggregate.test.ts（新建）：9 用例（降级/同格合并/异格不并/求和/最大强度/单点 children/脏数据去重/articles 兼容）

### 验证

- npm test 15 files / 320 tests 全绿（+9）；vite build 本地构建（新 bundle index-CIMgkt7C.js / css 沿用 S7YTSnTj）
- scp 原地覆盖 + chmod -R a+rX；root/js/css/news_geo/grv 200；v1.10.5 旧 bundle 按 DEPLOYMENT 规范清理
