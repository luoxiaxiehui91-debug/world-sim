# 开阳 1.7.0 交互体验升级 · PRD

> 版本：v1.7.0 ｜ 日期：2026-08-04 ｜ 作者：许清楚（产品经理）
> 关联文档：`system_design.md`（Wave 2 系统设计） / `PRD_CONTROL_PANEL.md`（控制面板 PRD）
> 当前版本：1.6.0（297 测试通过）

---

## 1. 项目信息

| 项 | 值 |
|---|---|
| Language | 中文（无 i18n） |
| Programming Language | React + Vite + TypeScript + Tailwind CSS |
| Project Name | `kaiyang_wave2` |
| 原始需求 | 两个交互短板修复：(A) 2D 平面地图缺乏 zoom/pan 交互，仅静态 Equirectangular 投影；(B) 面板布局为固定 12 栅格 Grid，无法拖拽调整大小或位置。对标 crucix 的 Leaflet 交互体验和 IDE 式可拖拽面板布局。 |

---

## 2. 产品定义

### 2.1 产品目标

1. **2D 地图可达交互**：将 2D 平面地图从「静态投影片」升级为「可缩放、可平移、可复位」的交互式地图，使 operator 能够在地理维度上自由探索风险分布，体验对标 crucix 的 Leaflet 瓦片地图，同时保持与 3D 地球完全一致的数据契约与视觉体系。
2. **面板布局可定制**：将 8 个面板从「固定栅格」升级为「可拖拽重排 + 可调整大小 + localStorage 记忆」的 IDE 式布局，让 operator 根据自己的监控重点自由排列面板位置与尺寸。

### 2.2 用户故事

| # | 用户故事 |
|---|---|
| US1 | 作为 operator，我希望在 2D 平面地图上**滚轮缩放 + 拖拽平移**，以便在关注亚太地区时放大查看东海/南海周边的风险点位细节，而不是只能看一张缩略全球图。 |
| US2 | 作为 operator，我希望**拖拽调整面板位置和大小**，比如把「核设施监视」面板拖到第一行放大显示，把不常用的面板缩小或移到底部，以适应我当前的监控任务重点。 |
| US3 | 作为 operator，我关闭浏览器再打开时，**面板布局应保持我上次的排列**，不需要每次都重新拖一遍。 |

---

## 3. 技术规范

### 3.1 需求池

#### P0 — 必须实现

| ID | 需求 | 描述 |
|---|---|---|
| P0-1 | **Leaflet 瓦片地图底图** | 将 `FlatMapPanel.tsx` 从 d3-geo + SVG 迁移到 Leaflet，使用 CartoDB Dark Matter 暗色瓦片（`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`，免费无需 API key）。移除对 `d3-geo` / `topojson-client` / `world-atlas` / `geojson` / `topojson-specification` 的依赖（仅 FlatMapPanel 上下文），新增 `leaflet` + `@types/leaflet`（MIT，~42KB gzip）。Leaflet CSS 需引入。 |
| P0-2 | **Leaflet 缩放/平移/复位** | wheel 缩放、drag 平移、双击复位到世界视角（`world` region 的 fitBounds）。地区切换（RegionTabs）改用 `map.flyTo()` 平滑过渡到目标 bbox，替代当前的 d3 `fitExtent` 重算投影。 |
| P0-3 | **风险点位渲染层迁移** | 将 RiskPoint 点位（颜色/形状/大小/脉冲动画/Hover tooltip）、RiskArc 弧线（渐变色）、战略要地星标**完整迁移**到 Leaflet 原生渲染层（CircleMarker / Polyline / DivIcon 等），保持与 3D GlobePanel 完全一致的视觉观感。数据契约（`RiskPoint` / `RiskArc` 类型）、图层颜色体系（`theme.ts` / `layerCategories.ts`）、渲染器只读约定（K6）全部不动。 |
| P0-4 | **react-grid-layout 面板布局** | 将 `App.tsx` 的 `<main>` 从 Tailwind CSS Grid（`grid grid-cols-1 lg:grid-cols-12`）迁移到 `react-grid-layout`（MIT）。新增依赖 `react-grid-layout` + `@types/react-grid-layout`。8 个面板可拖拽调整位置、从右下角拖拽调整大小。 |
| P0-5 | **布局 localStorage 持久化** | 面板位置与大小变化后自动保存到 `localStorage`（key: `kaiyang.panelLayout`），页面刷新/重开时恢复。`panelRegistry` 的 `PanelRegistration` 结构保持兼容，仅 `className`（col-span）字段不再作为布局源，改为初始布局的推导参考。 |
| P0-6 | **3D GlobePanel 零改动** | 3D 地球视图完全不受影响，`GlobePanel.tsx` 不涉及任何迁移，仍使用 globe.gl。 |

#### P1 — 应该实现

| ID | 需求 | 描述 |
|---|---|---|
| P1-1 | **Leaflet 缩放级别指示器** | 地图左下角显示当前缩放级别（如 `z=5`），帮助 operator 感知缩放深度。 |
| P1-2 | **面板布局重置按钮** | 提供「重置布局」按钮，一键恢复到默认 12 栅格排列。 |
| P1-3 | **Leaflet CSS 暗色主题适配** | Leaflet 默认控件（zoom control、attribution）样式覆盖为暗色主题，与现有玻璃拟态风格一致。 |
| P1-4 | **响应式布局兼容** | `react-grid-layout` 在窄屏（<lg）降级为单列堆叠，避免 8 个面板在小屏上挤成一团。 |

### 3.2 UI 交互说明

#### A. Leaflet 2D 地图操作

```
┌─────────────────────────────────────────────────────────┐
│ 🗺️ 全球风险平面图                       [🌐 3D] [🗺️ 平面] │
│                                                         │
│  地区：[全球] [东亚] [中东] [欧洲] [北美] ...            │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │                                                 │    │
│  │              Leaflet 暗色瓦片地图                  │    │
│  │              CartoDB Dark Matter                 │    │
│  │                                                 │    │
│  │    ● 风险点位（颜色/形状/脉冲/Hover tooltip）      │    │
│  │    ── 弧线（渐变色流动）                          │    │
│  │    ★ 战略要地星标                                │    │
│  │                                                 │    │
│  │              [+] 缩放控件（暗色主题）              │    │
│  │              [z=5] 缩放级别                      │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  拖拽平移 · 滚轮缩放 · 双击复位 · 点击点位聚焦            │
└─────────────────────────────────────────────────────────┘
```

| 交互 | 行为 | 备注 |
|---|---|---|
| **滚轮缩放** | 鼠标滚轮上下 → 地图以鼠标位置为中心缩放 | Leaflet 默认行为，zoom 范围 2~8 |
| **拖拽平移** | 鼠标按住拖拽 → 地图平移 | Leaflet 默认行为 |
| **双击地图** | 双击 → 复位到全球视角（`world` bbox） | 等价于 RegionTabs 点击「全球」 |
| **地区切换** | 点击 RegionTab（如「东亚」）→ `map.flyTo(regionBbox, { duration: 0.8 })` 平滑飞入 | 替换当前 d3 `fitExtent` 重算 |
| **点位 Hover** | 鼠标悬停点位 → tooltip 弹出（复用现有 hover 卡片） | 绑定在 CircleMarker 的 mouseover/mouseout |
| **点位点击** | 点击点位 → 触发 `onPointClick` 回调，双向聚焦 | 与现有 `SelectionContext` 联动 |
| **缩放指示器** | 左下角显示当前 zoom level（如 `z=5`） | P1-1，Leaflet `zoomend` 事件 |

#### B. 面板拖拽交互

```
┌──────────────────────────────────────────────────────────┐
│ ■ 风险摘要    │ ■■■ 世界视图（3D/平面）■■■ │ ■ 最新信号流  │
│ (可拖拽移动)  │   (可拖拽四角调整大小)     │               │
│               │                           │               │
├──────────────────────────────────────────────────────────┤
│ ■■■■■ GRV 维度 ■■■■■ │ ■■■■■■■ 经济面板 ■■■■■■■ │
│                        │                            │
├──────────────────────────────────────────────────────────┤
│ ■■■ 数据状态 │ ■■■■■■■■■ 新闻面板 ■■■■■■■■■ │
├──────────────────────────────────────────────────────────┤
│ ■■■■ 核设施监视 ■■■■ │                             │
└──────────────────────────────────────────────────────────┘

交互规则：
- 拖拽标题栏 → 移动面板位置（其他面板自动重排）
- 拖拽右下角 → 调整面板大小（宽高按 grid 单位吸附）
- 布局变更 → 自动保存到 localStorage
- 「重置布局」按钮 → 恢复默认排列（P1-2）
```

| 交互 | 行为 | 备注 |
|---|---|---|
| **拖拽移动** | 按住面板标题栏拖拽 → 面板与其他面板交换位置 | `react-grid-layout` 默认行为 |
| **调整大小** | 拖拽面板右下角 handle → 宽度/高度按 grid 单位吸附 | `react-grid-layout` resize handle |
| **布局记忆** | 每次 layout change → `localStorage.setItem('kaiyang.panelLayout', JSON.stringify(layout))` | onLayoutChange 回调 |
| **布局恢复** | 页面加载 → 从 localStorage 读取布局 → 应用到 grid；若读取失败回退默认布局 | mount 时执行 |
| **重置布局** | 点击「重置布局」按钮 → 清除 localStorage → 恢复默认 12 栅格排列 | P1-2 |
| **窄屏降级** | <lg 断点 → 面板堆叠为单列，禁用拖拽 | P1-4，`breakpoint` 配置 |

### 3.3 数据契约不变清单

以下接口与约定**本次不修改**，确保迁移前后风险：

| 契约 | 范围 | 保证 |
|---|---|---|
| `RiskPoint` 类型 | `src/lib/mapData.ts` | 字段不变，渲染器只读 `color/weight/shape/status` |
| `RiskArc` 类型 | `src/lib/mapData.ts` | `startLng/startLat/endLng/endLat/intensity/color` 不变 |
| `StrategicSite` 类型 | `src/data/strategicSites.ts` | 固定琥珀金 `#fbbf24`、星形符号不变 |
| `MAP_THEME` / `PALETTE` | `src/config/theme.ts` | 所有色值不变，Leaflet 层直接引用 |
| `layerCategories` | `src/config/layerCategories.ts` | 类别→色/形映射不变 |
| K6 渲染器只读约定 | 全局 | FlatMapPanel 不 import `layerCategories`，只读预计算字段 |
| GlobePanel | `src/components/GlobePanel.tsx` | 完全不涉及迁移，保持 globe.gl |
| WorldPanel | `src/components/WorldPanel.tsx` | 只改 FlatMapPanel 的 props 传递（若 leaflet 容器尺寸获取方式不同），不改业务逻辑 |
| panelRegistry | `src/panels/registry.ts` | `PanelRegistration` 接口保持兼容，`className` 字段转为初始布局参考 |

---

## 4. 依赖变更

| 操作 | 包名 | 许可证 | 大小 | 说明 |
|---|---|---|---|---|
| **新增** | `leaflet` | 自定义（BSD-like） | ~42KB gzip | 交互式地图库 |
| **新增** | `@types/leaflet` | MIT | 类型定义 | Leaflet TypeScript 类型 |
| **新增** | `react-grid-layout` | MIT | ~18KB gzip | 可拖拽网格布局 |
| **新增** | `@types/react-grid-layout` | MIT | 类型定义 | react-grid-layout TypeScript 类型 |
| **移除** | `d3-geo` | ISC | — | 仅 FlatMapPanel 上下文移除（项目中可能还有其他引用则保留） |
| **移除** | `topojson-client` | ISC | — | 仅 FlatMapPanel 不再需要 country-110m |
| **移除** | `world-atlas` | 自定义 | — | countries-110m.json 不再需要 |
| **保留** | `geojson` / `topojson-specification` | — | — | 若仅 FlatMapPanel 使用则可移除，否则保留 |

---

## 5. 待确认问题

| # | 问题 | 影响范围 |
|---|---|---|
| Q1 | Leaflet 的 CSS 是否通过 npm 包导入（`import 'leaflet/dist/leaflet.css'`）还是通过 CDN link 标签？推荐 npm 导入以保持离线可用。 | FlatMapPanel / index.css |
| Q2 | `react-grid-layout` 的 grid 单位（每格像素）设为多少？建议与当前 12 栅格对齐：`cols=12`，`rowHeight=80px`，面板最小宽 2 格、最小高 2 行。 | App.tsx 布局参数 |
| Q3 | 移除 `d3-geo` / `topojson-client` / `world-atlas` 后，项目中是否还有其他地方引用这些包？若 GlobePanel 或其他组件不依赖，可直接 `npm uninstall`。 | package.json 依赖清理 |
| Q4 | 2D 地图 zoom 范围建议 2~8：zoom=2 时全球可见（与当前静态图视野一致），zoom=8 时约等于城市级。是否有更细或更粗的缩放需求？ | Leaflet minZoom/maxZoom |
| Q5 | 面板布局 localStorage key 是否需要版本号前缀（如 `kaiyang.v1.panelLayout`），以便未来布局结构变更时做迁移？ | 布局持久化策略 |
| Q6 | `react-grid-layout` 在面板数量变化时（如未来新增第 9 个面板）如何处理布局冲突？当前方案：新面板追加到布局末尾，用户自行拖拽调整。 | 扩展兼容性 |
