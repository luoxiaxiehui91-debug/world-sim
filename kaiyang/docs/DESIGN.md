# 开阳（Kaiyang）操作面板 · 设计文档

> 版本：Wave 2 · v1.9.0 对齐版 ｜ 更新日期：2026-08-06
> 配套数据权威标准：同目录 [`DATA_CONTRACT.md`](./DATA_CONTRACT.md)
> 接手快照：同目录 [`NEXT_SESSION_HANDOFF.md`](./NEXT_SESSION_HANDOFF.md)

---

## 1. 定位与边界（核心设计决策）

- **独立子项目**：世界推演系统下的**操作面板（展示 + 控制双职能）**，正式位置 `S:\world-sim\kaiyang`，与 `macro-scan` / `macro-sim` 平级，纳入 world-sim monorepo。
- **获取 / 展示 / 控制 三分**（本项目的根本架构原则）：
  - **信息获取** → 天枢（macro-scan, Python）负责采集、聚合、产出契约文件；
  - **信息展示** → 开阳负责把已发布的数据**好看地摆出来**（3D 地球 + GRV / 经济 / 新闻面板 + 状态条）；
  - **控制指令** → 开阳作为**人工操作台**，代表人类 operator 向各后端**下发操作指令**，由对应后端执行（开阳只发令、后端执行）。
- **双耦合面**（详见 `DATA_CONTRACT.md`）：
  - **读侧** = 只读契约文件（`grv_latest.json` / `fred_history/*` / `news_export.json` / `sim_trigger.json` + 天璇 / 天玑 / macro-sim 输出），经 `DATA_BASE_URL` 加载。
  - **写侧（受控指令通道）** = 经各后端**正规控制通道**下发操作指令。控制范围现已钉定，覆盖：
    - **天璇推演层**：触发 macro-sim 推演、切换 / 加载推演场景、调参后提交推演、确认 / 驳回 `sim_trigger`；
    - **天枢观测层**：重跑某个 fetcher、暂停 / 恢复采集源、调整采集频率等观测层运维操作；
    - **天玑校验层 / 玉衡审批层**：提交校验任务、转交 / 接收审批结论等。
  - 写侧**协议（端点 / 文件流向 / 鉴权 / 权限分级）**：现役 = 天枢 **HTTP REST 控制 API（:8900）**，命令信封见 [`A3a-控制API-开阳对接文档.md`](./A3a-控制API-开阳对接文档.md)（文件投递协议未采纳，仅历史参考）。但**控制范围不蔓延**。
- **隔离铁律（精确版，用户硬性）**：代码层与天枢 / 天璇 / 天玑 / crucix **完全隔离**（禁止 `import` / 拷贝其它项目源码）；开阳**永不自行**调用任何第三方数据源 / 爬虫 / 外部 API 做采集（FRED、GDELT、RSS 等被明确排除）——但开阳**可以**向自家后端下发操作指令、由后端执行。二者性质不同：**「不爬第三方数据源」≠「不能和自家后端通信」**。禁止硬编码 NAS / SMB 绝对路径（如 `S:\...`），部署靠外部只读挂载 + 改 `DATA_BASE_URL`。

## 2. crucix 复刻策略

- **为什么复刻**：① 开源协议 AGPL-3.0（不可直接改后分发）；② 项目语言问题（UI 英文→中文；采集器 JS→Python 归天枢）。
- **展示半边** → 开阳 **clean-room 重写**：用 MIT / Apache 库（globe.gl / ECharts），不抄 AGPL 代码，全中文 UI，视觉继承 crucix 的玻璃拟态 + 青绿酷感。
- **采集半边** → 天枢 **Python 重实现**（用户：先不急，属天枢范围）。
- **控制半边** → 开阳**操作面板职能**（本设计新增）：面向全系统的受控指令下发，协议现役 = 天枢 HTTP REST 控制 API（:8900，见 §1）。

### 2.1 复刻进度（2026-08-06 · v1.9.0）

「对标 CRUCIX MONITOR 升级」= **继续执行本节既定的复刻策略**，把开阳从"只复刻 GRV 一类投影"推进到 crucix 的多类别图层形态，**不是新方向、不是竞品**。身份定性与 27 源反推详见 [`CRUCIX_ANALYSIS.md`](./CRUCIX_ANALYSIS.md)，逐项显示需求详见 [`CRUCIX_LAYER_REQUIREMENTS.md`](./CRUCIX_LAYER_REQUIREMENTS.md)。

| 复刻项 | 状态 |
|---|---|
| 3D 地球 + 2D 平面图双视图 | ✅ 已有（Wave1 · v1.0.2；2D 于 1.8.0 换用 D3 geoNaturalEarth1 + SVG 重写） |
| 右侧信号流 / 顶栏状态条 / 多面板大屏骨架 | ✅ 已有（面板 1.8.0 起可拖拽 react-grid-layout） |
| **P0-① 分类图层地基**（`RiskPoint.category` + 按类着色 + 类别图例 + 逐类开关） | ✅ **已交付（v1.2.0）** |
| **P0-② 核设施图层 + 核设施监视面板壳**（6 站静态种子，读数降级「—」） | ✅ **已交付（v1.2.0）** |
| P1：战略要地标签（1.3.0✅）/ 菱形符号推广（核设施已用✅）/ 地区 Tab（1.4.0✅）/ 顶栏 KPI 计数（1.4.0✅）/ 信号编号与点击联动（1.4.0✅） / 左侧指标树（1.5.0✅） | 纯前端批已全部完成 |
| P1：新闻地理化上图 / 冲突事件图层 | 新闻地理化 ✅ **已上线（1.9.0，news_geo GDELT geo feed）**；冲突事件 ⏸ 等 ACLED |
| **§4.5 清扫**（GrvPanel 硬编码色 / P2 死代码删除 / Tab 镜像标注） | ✅ **已交付（v1.6.0）** |
| **news_geo 读取层骨架 + 决策矩阵** | ✅ **已交付（v1.6.0）→ 1.9.0 已上线上图** |
| **2D 地图 D3 重写 + react-grid-layout** | ✅ **已交付（v1.8.0）：D3 geoNaturalEarth1 + SVG（Leaflet 方案废弃）；8 面板可拖拽 + localStorage 记忆** |
| **实时化收尾** | ✅ **已交付（v1.9.0）：market_quotes 行情面板 60s 轮询；news_geo 上线；控制面真实 REST** |
| P2：空域 / 热异常 / 海上 / 太空 / 卫生 / SDR 图层、风险仪表、sweep delta | ⏸ 待后端新建 feed（④空域⑤热异常天枢已有基础可优先） |

**已拍板的关键设计决策 · D1 颜色编码 = 方案 A**：**色相编码"类别"，严重度改由尺寸 + 光环脉冲 + 亮度表达**。理由是贴近 crucix 原型，且既有 `HIGHLIGHT_THRESHOLD` 光环 / 常驻标签机制可直接承接严重度表达。派生约束（已在代码中固化）：

- `value`(0–100) 是唯一严重度数值，`weight`(0–1) 是唯一强度驱动源，`severity`（字符串）**仅作展示标签**，禁止参与着色 / 尺寸数学；
- `status==='missing'` / `value===null` ⇒ **强制**灰 + 虚线 + 无光晕 + 无常驻标签，任何类别色不得覆盖；
- 类别图例与既有 `SEVERITY_LEGEND` **并存两栏**；
- 类别枚举唯一真源 `src/config/layerCategories.ts`，色值唯一真源 `src/config/theme.ts` 的 `CATEGORY_PALETTE`；渲染器保持只读，换算前移到 `src/lib/`。

**升级路线**：主线走**路线 A（在现有双视图上加分类图层体系，零新依赖）**；路线 B（引入 Leaflet / MapLibre）**已定案不采用**——2D 地图实际用 D3 `geoNaturalEarth1` + 纯 SVG 重写上线（1.8.0），不引入 Leaflet/MapLibre；路线 C（全量大屏重构）留作后端多 feed 就绪后的独立 Wave。

## 3. 技术栈（已定，不改动）

- React + Vite + TypeScript + Tailwind CSS
- 3D 地球：**globe.gl**（MIT）
- 图表：**ECharts**（Apache-2.0）
- 视觉：玻璃拟态 + 青绿主色 + 扫描线（全中文 UI，无 i18n）
- 产物：**纯前端静态站点**（`vite build` 输出 `dist/`）——自身**无业务后端**；控制指令经受控通道下发至各后端执行（开阳只发令、后端执行）。

## 4. Wave 规划

- **Wave 1（已完成，构建通过）** —— 仅天枢现有数据可喂的：
  - 3D 地球（globe.gl）：GRV 风险点 + 地缘联动弧线（天枢产出 **16+1 维**，开阳展示 **11 维子集**，见 `DATA_CONTRACT.md` §2.1）
  - GRV 面板（ECharts）：各维度数值 + 不确定区间（如 52.7±8，渲染为误差带 / 扇形）
  - 经济面板（ECharts）：FRED 关键序列
  - 新闻 / 叙事面板：`news_export` 条目列表
  - 顶部状态条：数据时间戳 + 缺失字段告警
  - **v1.0.3 增强**：气候风险 / 自然灾害维度**不再画常驻地图柱**，改为 `events[]` **事件触发式告警柱**（有事件才在事发地画 ⚠ 柱，缺省不渲染）。
- **Wave 2（进行中 · 双线并行，两条 P0 均已交付）**

  | 线 | 内容 | 状态 |
  |---|---|---|
  | **a. 控制面第一版** | 右侧 380px 玻璃拟态抽屉 + 天枢运维 Tab（重跑 fetcher / 暂停恢复采集源 / 调采集频率）+ 五 Tab 导航 + 三层进度反馈 + 操作日志。天璇 / 天玑 / 玉衡为「建设中」占位 | **P0（T01-T03）已交付 · v1.1.0**，复盘 0 缺陷。**1.7.2 起 A3a 真实控制 API（HTTP REST :8900）接入，`MOCK_ENABLED=false`** |
  | **b. crucix 复刻分类图层** | P0-① 分类图层地基 + P0-② 核设施图层与面板壳（见 §2.1） | **已交付 · v1.2.0**，QA 双轮独立验证 139/139 + `tsc` 干净 + `vite build` 绿。**news_geo / market_quotes 已于 1.9.0 上线上图** |

  两条线**互不阻塞**，均以 Mock / 静态种子自闭环起步，后端就绪后切换即可（1.7.2 起控制面已切真实 API；1.9.0 起行情/新闻 feed 已上线）。
  **历史卡点**：《现有 fetcher × crucix 源》映射表已于 2026-08-01 实查回填并吸收进 `DATA_CONTRACT.md` §2.6。P1 后端小改批（news_geo / market_quotes / fred manifest）均已**上线兑现**；剩余 P2 图层逐类接入待天枢 feed。

- **Wave 2 后续** —— 接入天璇（D.hypothesis）/ macro-sim（D.sim）/ 天玑（D.verification）新格式输出；新增面板 = 只加 `panelRegistry` 注册项，不改布局。同时落地写侧受控指令协议（端点 / 鉴权 / 权限分级）。

## 5. 扩展标准（预埋，新增信息只加注册项、不改布局）

1. **统一读取层** `useFeed(feedName)`：所有数据经 `src/hooks/useFeed.ts` + `src/lib/readLayer.ts`；新增 feed 只在 `src/config/dataSources.ts` 的 `FEEDS` 登记一项。
2. **面板注册表** `panelRegistry`（`src/panels/registry.ts`）：每面板 = 组件 + 注册项（`id/title/feed/order/visible/className`）；新增面板只加一项。
3. **字段容错**：缺失 → 「数据缺失」占位 + 状态条告警，不白屏 / 不崩。
4. **schema 版本**：每个 feed JSON 带 `schema_version`（Wave1 = `1.0`）；breaking change 须 bump，读取层比对并告警。
5. **数据契约权威文档** `DATA_CONTRACT.md`：各 feed 文件名 / 路径 / 字段 / schema_version / 部署。

## 6. 数据契约（摘要，详见 DATA_CONTRACT.md）

- 读取根 `DATA_BASE_URL`，默认 `./data/`（含 `public/data` 开发快照），部署改指向 NAS 只读挂载。
- 17 个 feed 注册于 `src/config/dataSources.ts` 的 `FEEDS`：`grv` / `news` / `simTrigger` / `fred` / `nuclearSites` / `news_geo` / `market_quotes` / `spacetrack` / `reports_index` / `fci_latest` / `gscpi` / `climate_signals` / `disaster_signals` / `earthquake_risk` / `energy_risk` / `hdx_risk` / `news_risk`，schema 均 `1.0`（FCI 为 `fci-1.1`，详见 DATA_CONTRACT.md §1 注册表）。
- **事件触发告警柱**：`grv_latest.json` 可选 `events[]`（`GrvEvent`：id / type / label / lat / lng / value / note）。气候 / 灾害类维度（`renderBar:false`）的地图呈现改由 `events[]` 承担，平时缺省不渲染。R-4 风险信号面板沿用该色阶语义渲染事件告警行。
- **R-1 报告模块（1.10.0）**：`ReportsPanel` 按类型分组（宏观分析/月度简报/假设推演/演化仿真/预测追踪）展示天枢报告清单，点击阅读 markdown（`src/lib/markdown.ts` 轻量渲染器，先转义后排版）。
- **R-3 金融条件（1.10.0）**：`FinancialPanel` 展示 FCI（`fci_latest.json` + `fci_daily.csv` 趋势）+ GSCPI（月度 CSV）。
- 当前上游真实文件与文档契约存在偏差（上游缺 lat/lng、缺不确定区间、news 实为 `latest_news.json`），已由适配层 + 状态条降级渲染，不破、不白屏。

## 7. 部署

- 独立静态站，端口 **:8080**（kaiyang 现役容器 nginx，`0.0.0.0:8080->80`）。
- 只读挂载天枢 `data` 目录 → 容器路径（如 `/mnt/tianshu-data/`）；构建 / 运行时注入 `DATA_BASE_URL`（`window.__KAIYANG_DATA_BASE_URL__` 或 `VITE_DATA_BASE_URL`）。
- **读侧**：无业务后端，浏览器按契约 `fetch` 拉取只读快照（可配合 CDN / 缓存策略，数据刷新由天枢侧更新文件即可）。
- **写侧**：控制指令经受控通道下发至各后端执行——**现役 = 天枢 HTTP REST 控制 API（:8900，见 `DATA_CONTRACT.md` §2.3 与 `A3a-控制API-开阳对接文档.md` §0）**。
- 详见 `DATA_CONTRACT.md` §4。

## 8. 当前交付状态（2026-08-06 · v1.9.0）

**Wave 2 双线 P0 均已交付并通过独立 QA 验证（GO）；实时化已收尾（v1.9.0）**：

- **线 a 控制面 P0（v1.1.0）**：T01-T03 实现完毕，组队复盘 P0=0 / P1=0 / P2=7（仅死代码），`tsc --noEmit` 零错误，Mock 模式自闭环。**1.6.0 增补** A2（控制面 P2 死代码 7 处清扫）+ A3（5 Tab 镜像「已评:保留镜像」标注）。**1.7.2 起接入 A3a 真实控制 API（HTTP REST :8900），`MOCK_ENABLED=false`**。
- **线 b 分类图层 P0（v1.2.0）**：P0-①② 实现完毕，**QA 双轮独立验证 139/139 单测通过** + `tsc` 干净 + `vite build` 绿。期间修复一处源码 Bug（`src/lib/nuclearData.ts:199` 的 `level:'unknown'` 分支状态不自洽），已补回归用例钉死；修复后为**零源码缺陷干净版**。
- **产品决策已闭环**：D1 颜色编码定为**方案 A**（见 §2.1）；D5 已定案走 **D3 geoNaturalEarth1**（2D 地图 1.8.0 上线）；代码与 QA 均按此口径。
- **1.8.0（交互升级）**：2D 地图 **D3 geoNaturalEarth1 + 纯 SVG 重写**（Leaflet 迁移方案未实施，见 `ARCH_1.8.0.md` ARCHIVED 标注）；**react-grid-layout 8 面板可拖拽** + localStorage 记忆（key `kaiyang.v1.panelLayout`）。
- **1.9.0（实时化收尾）**：`market_quotes` 行情面板 60s 轮询；`news_geo` GDELT geo feed 上线上图（`news_geo_feed.py`，scheduler 已注册）；控制面真实 REST 链路。**`news_geo` / `market_quotes` / `spacetrack` 已注册上线**。
- **待办与卡点**：剩余 P2 图层（空域 / 热异常 / 海上 / 太空 / 卫生 / SDR）与冲突事件（ACLED）待天枢 feed；GSCPI 序列待天枢补。完整接手快照见 [`NEXT_SESSION_HANDOFF.md`](./NEXT_SESSION_HANDOFF.md)。
- **不阻塞的可选清理**：`src/components/GrvPanel.tsx:118` 散落连线色 `#e2e8f0`；`src/index.css` 手工镜像 `CATEGORY_PALETTE` 的 `--ky-cat-*` 变量（已有漂移守卫测试兜底）。

**工程环境**：

- 工作区为 `kaiyang-wave2/`（`kaiyang-wave1` 已备份下线）；正式位置仍为 world-sim monorepo 下的 `kaiyang`。
- NAS 侧重建：`npm install && npm run build`（建议在 NAS 主机本地路径执行，避免 SMB 上 symlink 问题）。
- 本地预览：`npm run dev`（:5173）/ `npm run preview`（:4173）/ `npm test`（基线以当前代码为准——`src/` 下 13 个测试文件，历史快照 297/297 为 1.6.0 基线）。
- ⚠ **依赖版本钉死不可动**：`three` 与 `@types/three` 精确 `0.185.1`、`globe.gl ^2.46.1`。降版会导致 `three-globe` 调用 `Matrix4.determinantAffine()` 缺失、地球渲染循环异步抛错且被 React 静默吞掉（表现为容器空白无报错）。

## 9. 目录结构

```
kaiyang/
├── index.html
├── package.json
├── vite.config.ts / tsconfig*.json / tailwind.config.js / postcss.config.js
├── docs/
│   ├── DESIGN.md                 ← 本设计文档（操作面板 · 设计总纲）
│   ├── DATA_CONTRACT.md          ← 数据契约权威标准
│   ├── NEXT_SESSION_HANDOFF.md   ← 下个 session 接手快照
│   ├── CRUCIX_ANALYSIS.md        ← 对标 crucix 竞品/参考分析
│   ├── CRUCIX_LAYER_REQUIREMENTS.md ← 前端显示需求清单（§7 派生后端 feed 清单）
│   ├── CRUCIX_UPGRADE_DESIGN.md  ← 升级技术设计
│   ├── 天枢-fetcher×crucix-映射表-询问.md ← 给后端的问题单（当前卡点）
│   └── archive/开阳Crucix新闻地理坐标需求-给后端.md
├── src/
│   ├── main.tsx / App.tsx / index.css
│   ├── components/  (EChart / GlobePanel / FlatMapPanel / WorldPanel / GrvPanel / EconomyPanel / NewsPanel / StatusBar
│   │                 / LayerLegend 类别图例与开关 / NuclearWatchPanel 核设施监视 / 控制抽屉与天枢运维 Tab)
│   ├── config/      (dataSources: DATA_BASE_URL+FEEDS / grvDimensions: 11维展示子集坐标+弧线+renderBar
│   │                 / layerCategories: 图层类别唯一真源 / theme: CATEGORY_PALETTE 色值唯一真源 / nuclearSites: 6站静态种子)
│   ├── hooks/       (useFeed 统一读取层 / useFRED)
│   ├── lib/         (readLayer fetchJson/fetchCsv / grvAdapter 适配容错 / mapData buildRiskPoints/buildEventBars
│   │                 / nuclearData readingToValue 归一化 / format)
│   ├── panels/      (registry: panelRegistry)
│   ├── state/       (StatusContext: 时间戳/告警/schema版本)
│   └── types/       (contracts: GrvRaw / GrvEvent / NewsItem / FredSeriesMeta / NuclearSite / NuclearWatchReading)
└── public/data/     ← 开发快照（grv_latest.json / news_export.json / sim_trigger.json / nuclear_sites.json / fred_history/*）
```
