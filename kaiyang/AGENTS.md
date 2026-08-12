# 开阳（Kaiyang）操作面板 — AI 工作入口

> **如在 monorepo 中工作，先读根目录 [`../AGENTS.md`](../AGENTS.md)（系统全貌 + 阅读路径入口）。**

## 当前状态快照

**版本**：v1.9.0（2026-08-06）  
**主要变更**：实时化收尾——market_quotes 行情面板 60s 轮询、news_geo GDELT geo feed 上线上图、控制面走真实 HTTP REST :8900（MOCK=false）  
**已完成**：2D 地图 D3 geoNaturalEarth1 重写（1.8.0，Leaflet 方案废弃）+ react-grid-layout 可拖拽布局（1.8.0，非规划）；A3a 控制 API 接入（1.7.2）  
**待处理**：`docs/DECISION_MATRIX.md` 决策矩阵 D2-D5 已文档化（D5 已改 D3 方案定案）  
**下一里程碑**：实时化已收尾，后续为 P2 图层逐类接入（等天枢 feed）

---

## 系统定位

世界推演系统的前端操作面板，展示 + 控制双职能。读侧只读天枢契约文件做可视化，写侧代表人类 operator 向各后端下发操作指令（只发令、后端执行）。

---

## 新 session 阅读路径

1. **本文件**（`AGENTS.md`）— 了解约束和当前状态
2. **`CHANGELOG.md` 前 80 行** — 了解最新版本变更
3. 按任务分支：
   - 改代码 → 先读「扩展标准」（下面三入口表）
   - 加 feed → `src/config/dataSources.ts`
   - 加面板 → `src/panels/registry.ts`
   - 加类别 → `src/config/layerCategories.ts` + `theme.ts`
   - 控制面 → `docs/A3a-控制API-开阳对接文档.md`
   - 深层架构 → `docs/DESIGN.md`
   - 决策记录 → `docs/DECISION_MATRIX.md`

---

## 关键操作约束

| 约束 | 说明 |
|:-----|:-----|
| **铁律三条** | ① 永不自行调第三方数据源/爬虫 ② 严禁硬编码 NAS/SMB 绝对路径 ③ 数据缺失一律降级不白屏 |
| **three 版本钉死** | `three: 0.185.1`（精确，不加 `^`）；降版 → `Matrix4.determinantAffine()` 缺失 → 地球空白 |
| **开发端口** | `:5173`（vite dev），`localhost` 测试 |
| **React StrictMode** | 开发态 reducer 跑两遍，别误以为 bug |
| **useFeed 不缓存** | 两个组件调 `useFeed('grv')` 会发两次请求，共享数据走 props 下传 |
| **改后必做** | bump `VERSION` + `package.json` → 追加 `CHANGELOG.md` → `npm run build` 绿 + `npm test` 全过 |
| **dist/ 不进 git** | 构建产物在 .gitignore，NAS 部署需手动 `npm run build` + scp |
| **MOCK_ENABLED** | 默认 `false`（v1.7.2+），连接真实控制 API（HTTP REST :8900）；调试时用 `VITE_CONTROL_MOCK=true` 恢复 mock |

---

## 技术栈

| 项目 | 选型 |
|------|------|
| 框架 | React + Vite + TypeScript |
| 样式 | Tailwind CSS（玻璃拟态 + 青绿主色 + 扫描线） |
| 3D 地球 | globe.gl（MIT，three 0.185.1） |
| 图表 | ECharts（Apache-2.0） |
| 2D 地图 | D3.js + geoNaturalEarth1 + SVG（world-atlas TopoJSON，离线，v1.8.0 换用）|
| 测试 | Vitest |
| 语言 | 全中文 UI，无 i18n |

---

## 扩展标准（改代码记住三条入口）

| 操作 | 只改一个文件 | 例 |
|------|-------------|-----|
| 加新 feed | `src/config/dataSources.ts` `FEEDS` 登记一项 | `news_geo`、`market_quotes` 均如此 |
| 加新面板 | `src/panels/registry.ts` `panelRegistry` 加一项 | NuclearWatchPanel |
| 加新类别 | `src/config/layerCategories.ts` 加一项 + `theme.ts` 加色 | — |

---

## 深入文档（按需读取）

| 文件 | 内容 | 何时读 |
|:-----|:-----|:-------|
| `docs/DATA_CONTRACT.md` | 数据契约权威标准（字段/路径/schema_version） | 消费新数据源时 |
| `docs/A3a-控制API-开阳对接文档.md` | 控制 API 对接规范（HTTP REST :8900 / 命令格式） | 改控制面逻辑时 |
| `docs/DESIGN.md` | 设计总纲（定位/边界/技术栈/Wave规划） | 做架构决策时 |
| `docs/ARCH_1.8.0.md` | v1.8.0 架构计划（**ARCHIVED**：Leaflet 迁移方案未实施，实际用 D3 geoNaturalEarth1 重写；react-grid-layout 已实现） | 规划下个版本时（先看 ARCHIVED 标注，勿按 Leaflet 方案执行） |
| `docs/CRUCIX_UPGRADE_DESIGN.md` | ~~P0 主设计：对标 crucix 升级系统设计~~ **DEPRECATED（crucix 08-12 退场）**，历史参考 | 做 crucix 相关工作时 |
| `docs/system_design.md` | 控制面 Tab 系统设计（状态机/Token鉴权） | 改控制面架构时 |
| `docs/DECISION_MATRIX.md` | **决策矩阵**（D2-D5 已文档化；D5 已改 D3 方案定案） | 遇到相关技术决策点时 |

---

## 项目结构

```
kaiyang/
├── AGENTS.md               ← 本文件（唯一 AI 工作入口）
├── CLAUDE.md               ← Claude Code 兼容层（指向本文件）
├── VERSION                 ← 当前版本号（1.9.0）
├── CHANGELOG.md            ← 变更记录
├── src/
│   ├── config/             ← dataSources / layerCategories / theme / regions / controlConfig
│   ├── components/         ← WorldPanel / GlobePanel / FlatMapPanel / LayerTreePanel …
│   ├── control/            ← ControlDrawer / TianshuTab / FetcherCard …
│   ├── hooks/              ← useFeed / useControlApi / useOperationPolling …
│   ├── lib/                ← adaptGrv / nuclearData / newsGeoAdapter / controlApi …
│   ├── panels/             ← registry.ts（面板注册表）+ 各面板组件
│   ├── state/              ← ControlContext / SelectionContext / StatusContext
│   └── types/              ← contracts.ts / control.ts
├── docs/                   ← 设计文档（DATA_CONTRACT/DESIGN/ARCH/PRD/…）
└── public/data/            ← 开发快照（grv_latest.json / fred_history / nuclear_sites.json）
```

---

## 数据契约

- 权威标准：`docs/DATA_CONTRACT.md`
- feed 统一入口：`src/config/dataSources.ts` → `useFeed()` 自动读取
- 字段容错降级：`null` / 缺失 → 空数组 / fallback 值，不白屏
- `schema_version`：读取层比对告警，不阻塞渲染

---

## 测试与部署

```bash
npm test              # Vitest 单元测试
npm run build         # 构建产物到 dist/（dist/ 不进 git）
```
