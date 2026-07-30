# Changelog · 开阳（Kaiyang）展示层

本文件记录开阳的每次变更，遵循 Keep a Changelog 精神，版本号与 `VERSION` 绑定（SemVer 取向）。

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
- 完整 Vite + React + TS + Tailwind 静态站，纯展示层，只读天枢契约文件。
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
