# 开阳 · 下个 Session 接手文档（HANDOFF）

> 更新：2026-08-06 ｜ 对应版本 **`VERSION = 1.9.0`** ｜ 维护：齐活林（主理人）
> **权威状态源**：`../.workbuddy/memory/MEMORY.md`（项目记忆，若与本文档冲突以 MEMORY.md 为准）
> 本文档是给**下一个 AI session / 接手者**的 60 秒快照，不是设计文档。深入细节请走 §6 的文件指针。

---

## 1. 一句话定位

**开阳（kaiyang）= 世界推演系统的前端操作面板**，展示 + 控制双职能：读侧只读天枢契约文件做可视化，写侧代表人类 operator 向自家后端下发操作指令（**只发令、后端执行**）。当前对标开源 crucix 展示大屏做复刻升级。

工作区：`kaiyang-wave2/` ｜ 正式位置：world-sim monorepo 下的 `kaiyang`（与 macro-scan / macro-sim 平级）。

---

## 2. 当前进度一览

```
Wave1 ✅ 已完成（3D地球 + GRV + 经济 + 新闻 + 状态条）
   │
Wave2 ├─ 线 a：控制面 ──────────────────── P0 ✅（T01-T03），A3a 真实 API 已接入（MOCK=false）
      ├─ 线 b：crucix 分类图层 ── P0 (①②) ✅ GO
      │                             ├─ P1 纯前端批 ✅ 全部完成（1.3.0 → 1.4.0 → 1.5.0）
      │                             ├─ 1.6.0 ✅ §4.5 清扫 + news_geo 骨架 + 决策矩阵
      │                             ├─ 1.7.0 ✅ BugFix 批次（NaN 崩溃 + 抽屉关闭 + 2D 移除）
      │                             ├─ 1.7.1 ✅ MOCK 显式标注（控制抽屉顶部 ⚠ 横幅）
      │                             ├─ 1.7.2 ✅ A3a 控制 API 接入（MOCK_ENABLED=false，:8900）
      │                             ├─ 1.8.0 ✅ 2D 地图 D3 重写 + react-grid-layout 可拖拽布局
      │                             └─ 1.9.0 ✅ 实时化（market_quotes 轮询 / news_geo 上线 / 控制面 REST）
      └─ 剩余：P1/P2 ⏸ 少数 feed 未到位（见 §4）
```

| 里程碑 | 版本 | 核心交付 | 测试 |
|--------|------|----------|:----:|
| 控制面 P0 | 1.1.0 | 右侧抽屉 + 天枢运维 Tab + Mock 自闭环 | tsc 零错 |
| crucix 分类图层 | 1.2.0 | RiskPoint.category 12 类 + 核设施图层 Nuclear Watch | 139/139 |
| 战略要地 + osint 删 | 1.3.0 | 8 种子要地琥珀星标 + osint 图层清除 | 160/6 files |
| 地区 Tab / KPI / 信号联动 | 1.4.0 | 6 区 Tab + 三 chip KPI + SelectionContext | 243/11 files |
| 左侧指标树 | 1.5.0 | LayerTreePanel 三态灯 + 计数 | 269/12 files |
| **§4.5 清扫 + news_geo 骨架 + 决策矩阵** | **1.6.0** | GrvPanel 修色 + P2 死代码 + 9 处镜像注释 + news_geo 全链路 + DECISION_MATRIX | **297/13 files** |
| **BugFix + 2D 移除** | **1.7.0** | NaN 崩溃修复 + 控制抽屉关闭修复 + ErrorBoundary + 2D 平面地图移除（瓦片缺口无法修复） | **unchanged** |
| **MOCK 显式标注** | **1.7.1** | 控制抽屉顶部加琥珀色横幅「⚠ 控制功能未连接」；MOCK_ENABLED=false 时自动隐藏 | **297/297** |
| **A3a 控制 API 接入** | **1.7.2** | MOCK_ENABLED=false，接入天枢 control_server REST :8900 | 基线 |
| **2D 地图 D3 重写 + 可拖拽布局** | **1.8.0** | FlatMapPanel 换用 D3 geoNaturalEarth1 + SVG（根治 Leaflet 子午线伪线）；react-grid-layout 8 面板可拖拽 + localStorage 记忆 | 基线 |
| **实时化收尾** | **1.9.0** | market_quotes 行情面板实时化（60s 轮询）；news_geo GDELT geo feed 上线上图；控制面真实 REST 链路 | 基线 |

> 测试基线说明：旧文档中的「297 例 / 139 例 / 269 例」等历史数字为对应版本快照，无法逐版本核实时**以当前代码基线为准**（`src/` 下现有 **13 个测试文件**，`npm test` 全绿为验收标准，具体例数看测试运行输出）。

---

## 3. 已完成的重点（新 session 不用重新理解）

### 3.1 扩展体系（改代码前记住这三条）

- **加新 feed**：只在 `src/config/dataSources.ts` 的 `FEEDS` 登记一项 → `useFeed(feedName)` 自动生效
- **加新面板**：只在 `src/panels/registry.ts` 的 `panelRegistry` 加一项 → `App.tsx` 网格不动
- **加新类别**：只在 `src/config/layerCategories.ts` 加一项 + `theme.ts` 加色 → 图层体系自动继承

### 3.2 分类图层固化的关键约束

- **D1 颜色编码 = 方案 A（永久锁定）**：色相 = 类别，严重度 = 尺寸 + 光环脉冲
- `value`(0–100) 是唯一严重度数值，`weight`(0–1) 是唯一强度驱动源，`severity` 字符串**只是展示标签**
- `status==='missing'` / `value===null` ⇒ 强制灰 + 虚线，类别色不得覆盖（优先级最高）
- 渲染器保持只读：只读 `p.color / p.weight / p.shape / p.status`，换算全在 `src/lib/`
- 点位 id 命名空间：`${category}:${原始id}`（防撞车）
- 当前 **12 类**（osint 已于 1.3.0 因合规否决删除）

### 3.3 news_geo 已上线（1.9.0，不再等 feed）

- `src/config/dataSources.ts`：`news_geo` feed 已登记（`path: 'news_geo.json'`，`schemaVersion: '1.0'`）
- `src/types/contracts.ts`：`NewsGeoEvent` / `NewsGeoRaw` 类型（按 DATA_CONTRACT §2.7 定稿契约）
- `src/lib/newsGeoAdapter.ts`：`adaptNewsGeo()` 兼容 `events[]` 与 `articles[]` 两种结构（空数组不抛异常）
- `src/components/WorldPanel.tsx`：`useFeed('news_geo')` + `adaptNewsGeo` 已接线
- `src/lib/newsGeoAdapter.test.ts`：28 用例
- **天枢 GDELT geo feed（news_geo_feed.py）已上线**（scheduler 07:15 注册），前端免改代码自动上图

### 3.4 market_quotes 行情面板已上线（1.9.0）

- `MarketQuote` / `MarketQuotesRaw` 类型已注册
- `src/config/dataSources.ts` 已登记（`path: 'market_quotes.json'`）
- `WorldPanel.tsx` 消费 `marketRaw`
- **底部行情面板已实现** + 前端 60s 轮询实时刷新

### 3.5 2D 地图 = D3 geoNaturalEarth1 重写（1.8.0，Leaflet 方案废弃）

- **Leaflet 迁移方案从未实施，已废弃**（见 `docs/ARCH_1.8.0.md` ARCHIVED 标注）
- 实际实现：`FlatMapPanel.tsx` 用 **d3-geo `geoNaturalEarth1` 投影 + 纯 SVG** 重写，根治 Leaflet/瓦片子午线水平伪线与第三方瓦片覆盖不全问题
- `react-grid-layout` 已实现（非规划）：8 面板可拖拽重排 + resize + localStorage 记忆（key `kaiyang.v1.panelLayout`）

### 3.6 控制面 = HTTP REST :8900（1.7.2 / 1.9.0）

- **A3a 控制面真实协议 = HTTP REST**（天枢 `control_server.py`，FastAPI :8900），**非文件投递**
- 默认 API 地址 `http://192.168.31.108:8900/api/v1/control/`（`src/config/controlConfig.ts`）
- `MOCK_ENABLED=false`（默认关 mock 连真实 API；开发调试用 `VITE_CONTROL_MOCK=true` 恢复 mock）

### 3.7 1.7.0 变更速记（新 session 不用深入研究修复过程）

- **NaN 崩溃**：`FlatMapPanel` flyToBounds 加 size 零检查 + 各处坐标加 `isNaN` 防护 → 不崩
- **控制抽屉关闭**：`prevOpen.current` 改在 if/else 内赋值（原在 return 后永远不执行）→ 能关了
- **ErrorBoundary**：`main.tsx` 全局包裹，组件崩溃不再白屏
- **2D 平面地图已移除**：`WorldPanel` 只渲染 3D 地球。CartoDB/ESRI/OSM/Voyager 四家瓦片全覆盖不可接受（1.8.0 后以 D3 geoNaturalEarth1 SVG 重写回归）
- **Panel 注册表标题**「世界视图（3D/平面）」暂留——标题未改但只有 3D 切

---

## 4. 待办与决策点（新 session 从这里接）

### 4.1 P1 / P2 图层与后端依赖

| 优先级 | 图层 / 功能 | 状态 |
|:--:|---|:--:|
| **P1** | 新闻地理化上图 | ✅ **已上线**（1.9.0）：news_geo GDELT geo feed 已注册，market_quotes/news_geo/fred manifest 均已上线 |
| **P1** | 冲突事件图层 | ⏸ 等 ACLED feed（天枢无授权无 fetcher） |
| **P1** | 底部行情带 | ✅ **已上线**（1.9.0）：market_quotes.json 已注册 + 60s 轮询 |
| **P2** | 空域 / 热异常 / 海上 / 太空 / 卫生 / SDR | ⏸ 等后端新建 feed（④空域⑤热异常天枢已有基础可优先） |
| **P2** | 底部风险仪表（VIX / 利差 / GSCPI） | ⏸ fred manifest 已上线（VIX/利差已存在），GSCPI 待天枢补 |
| **P2** | 信号流 sweep delta | ⏸ 等后端算好推送 |
| **P2** | 聚类标签（Ukraine 71 式） | ⚠ 待定 D2（见 §4.2） |

### 4.2 决策矩阵现状（已文档化）

> 详见 [`DECISION_MATRIX.md`](./DECISION_MATRIX.md)。D2-D5 均已给出主理人推荐（折中 / 每类一文件 / 不做 SSE / 不解锁 Leaflet）。**D5 已实际落地为「改用 D3 geoNaturalEarth1 重写」**——2D 不依赖 Leaflet/MapLibre。

| # | 决策 | 主理人推荐 | 状态 |
|---|------|-----------|:--:|
| D2 | 聚类：前端 bbox vs 后端预聚合 | 折中：后端预留 reader + 前端 1°×1° bbox 兜底 (<200点) | 待触发（点位超阈值时） |
| D3 | feed 粒度：每类一文件 vs 聚合 | 每类一文件（已写进契约，实际落地） | ✅ 已隐含采纳 |
| D4 | SSE 实时推送 | 不做（日/周频无意义） | ✅ 已隐含采纳 |
| D5 | 解锁 Leaflet / MapLibre 新依赖 | 不解锁（实际已改走 D3 geoNaturalEarth1 方案） | ✅ 已定案 |

### 4.3 已做完无需再动的

- ✅ D1 颜色编码（方案 A，永久锁定）
- ✅ 天枢 fetcher×crucix 映射表（已回填，结论已吸收进 DATA_CONTRACT §2.6）
- ✅ P1 纯前端批全部完成（战略要地 1.3.0 / 地区 Tab+KPI+信号联动 1.4.0 / 左侧指标树 1.5.0）
- ✅ osint 图层删除（1.3.0，合规否决）
- ✅ P2 死代码清扫（1.6.0 §4.5 A2）
- ✅ Tab 镜像标注（1.6.0 §4.5 A3，9 处注释）
- ✅ GrvPanel 硬编码色修复（1.6.0 §4.5 A1，→PALETTE.axis）
- ✅ A3a 控制 API 接入（1.7.2，HTTP REST :8900，MOCK=false）
- ✅ 2D 地图 D3 重写 + react-grid-layout（1.8.0）
- ✅ 实时化收尾（1.9.0：market_quotes 轮询 / news_geo 上线）

---

## 5. 新 session 开场话术

> **「继续开阳 Wave2。VERSION 1.9.0，13 个测试文件全绿（基线以当前代码为准）。crucix P0 分类图层+核设施已 GO，P1 纯前端批全部完成。1.8.0 完成 2D 地图 D3 geoNaturalEarth1 重写 + react-grid-layout 可拖拽布局；1.9.0 完成实时化——market_quotes 面板 60s 轮询、news_geo GDELT geo feed 上线上图、控制面走真实 HTTP REST :8900（MOCK=false）。剩余 P2 图层等后端 feed。」**

---

## 6. 关键文件指针

### 6.1 必读（新 session 前五分钟）

| 文件 | 作用 |
|------|------|
| `../.workbuddy/memory/MEMORY.md` | **权威状态源**，比本文档更全 |
| [`DESIGN.md`](./DESIGN.md) | 设计总纲 §2.1 进度表 |
| [`DATA_CONTRACT.md`](./DATA_CONTRACT.md) | 数据契约（§1 注册表 / §2.6 后端 feed 状态 / §2.7 news_geo 契约） |
| [`../AGENTS.md`](../AGENTS.md) | AI session 入口，硬约束 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 变更记录 |

### 6.2 代码扩展锚点

| 路径 | 做什么 |
|------|--------|
| `src/config/dataSources.ts` | **加 feed 只改这里** |
| `src/config/layerCategories.ts` | 图层类别唯一真源（12 类） |
| `src/config/theme.ts` | 色值唯一真源 |
| `src/panels/registry.ts` | **加面板只加一项** |
| `src/lib/` | 数据→渲染换算层（渲染器只读，换算全在这） |
| `src/hooks/useFeed.ts` | 统一读取层（一般不用改） |
| `src/config/controlConfig.ts` | 控制 API Base URL + MOCK_ENABLED 开关 |

---

## 7. 关键 gotcha

### 7.1 ⛔ three 版本钉死

```jsonc
"three": "0.185.1",           // 精确版本，不要 ^
"@types/three": "0.185.1",    // 精确版本，不要 ^
"globe.gl": "^2.46.1"
```
`three` 过旧 ⇒ `Matrix4.determinantAffine()` 缺失 ⇒ 地球渲染空白（React 静默吞错）。**绝对不要降 three 或留 `^`**。

### 7.2 ⛔ 铁律三条

- 开阳**永不自连**第三方数据源 / 爬虫（FRED/GDELT/Yahoo 等）
- 严禁硬编码 NAS/SMB 绝对路径（部署靠外部挂载 + 改 `DATA_BASE_URL`）
- 数据缺失一律降级，**不白屏**（空数组是合法业务态）

### 7.3 ⚠ 语义约束（容易被后来者破坏）

- `severity` 字符串只是展示标签，禁止参与着色/数学
- 缺失态优先级最高（`status==='missing'` 强制灰+虚线）
- 渲染器只读 `p.color/p.weight/p.shape/p.status`，不 import layerCategories

### 7.4 ⚠ 改后必做

1. bump `VERSION` + `package.json` version
2. `CHANGELOG.md` 追加（改了什么 / 为什么 / **明确没改什么**）
3. 同步 `docs/DESIGN.md` + `docs/DATA_CONTRACT.md`
4. `npm run build` 绿 + `npm test` 全绿（基线 = `src/` 下 13 个测试文件，具体例数以运行输出为准）

### 7.5 ⚠ CHANGELOG 承诺 ≠ 代码实际落盘

工程师写的 CHANGELOG 可能声称"已做"但源码未兑现（1.6.0 A3 镜像注释是典型案例——CHANGELOG 说做了但 grep 零命中）。**每次 bump CHANGELOG 时逐条确认变更在源码实际存在**，不凭计划/意图预设。

---

## 8. 版本速查

| 版本 | 内容 | 测试数 |
|------|------|:----:|
| 1.1.0 | 控制面 P0 | tsc 零错 |
| 1.2.0 | crucix P0 分类图层+核设施 | 139 |
| 1.3.0 | 战略要地标签 + osint 删除 | 160 |
| 1.4.0 | 地区 Tab + KPI + 信号联动 | 243 |
| 1.5.0 | 左侧指标树 | 269 |
| **1.6.0** | **§4.5 清扫 + news_geo 骨架 + 决策矩阵** | **297** |
| **1.7.0** | **BugFix + ErrorBoundary + 2D 平面地图移除** | **unchanged** |
| **1.7.1** | **MOCK 显式标注横幅** | 297 |
| **1.7.2** | **A3a 控制 API 接入（HTTP REST :8900，MOCK=false）** | 基线 |
| **1.8.0** | **2D 地图 D3 geoNaturalEarth1 重写 + react-grid-layout 可拖拽** | 基线 |
| **1.9.0** | **实时化：market_quotes 60s 轮询 + news_geo 上线 + 控制面真实链路** | **以当前代码基线为准（src 下 13 个测试文件）** |
