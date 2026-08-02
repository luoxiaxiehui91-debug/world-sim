# 开阳（Kaiyang）操作面板 — AI 工作入口

**系统定位**：世界推演系统的前端操作面板，展示 + 控制双职能。读侧只读天枢契约文件做可视化，写侧代表人类 operator 向各后端下发操作指令（只发令、后端执行）。

---

## 新 session 阅读路径

按顺序读完，每步只需几分钟：

1. **本文件**（根 `AGENTS.md`）— 了解约束和关键文件
2. **`VERSION`**（1 行，当前版本号）
3. **`CHANGELOG.md` 前 80 行** — 了解最新版本变更
4. **`docs/NEXT_SESSION_HANDOFF.md`**（约 200 行）— 60 秒全貌快照
5. **`docs/DESIGN.md` §2.1** — 进度总览表
6. 按任务分支：
   - 改代码 → 先读「扩展标准」（下面三入口表）
   - 加 feed → `src/config/dataSources.ts`
   - 加面板 → `src/panels/registry.ts`
   - 加类别 → `src/config/layerCategories.ts` + `theme.ts`
   - 控制面 → `docs/A3a-控制API-开阳对接文档.md`

---

## 关键操作约束

| 约束 | 说明 |
|:-----|:-----|
| **铁律三条** | ① 永不自行调第三方数据源/爬虫 ② 严禁硬编码 NAS/SMB 绝对路径 ③ 数据缺失一律降级不白屏 |
| **three 版本钉死** | `three: 0.185.1`（精确，不加 `^`）；降版 → `Matrix4.determinantAffine()` 缺失 → 地球空白 |
| **开发端口** | `:3118`（vite dev 5x73），`localhost` 测试 |
| **React StrictMode** | 开发态 reducer 跑两遍，别误以为 bug |
| **useFeed 不缓存** | 两个组件调 `useFeed('grv')` 会发两次请求，共享数据走 props 下传 |
| **改后必做** | bump `VERSION` + `package.json` → 追加 `CHANGELOG.md` → 同步 `docs/` → `npm run build` 绿 + `npm test` 全过 |
| **CHANGELOG 承诺 ≠ 落盘** | 每次 bump 逐条 grep 源码核实，不凭计划/计划预设 |
| **错误边界** | `main.tsx` 有 `ErrorBoundary`，组件崩溃不白屏 |
| **`??` 挡不住哨兵值** | 枚举 fallback 必须显式排除 `'unknown'`/`''` 等哨兵；案例见 `nuclearData.ts:199` |

---

## 技术栈

| 项目 | 选型 |
|------|------|
| 框架 | React + Vite + TypeScript |
| 样式 | Tailwind CSS（玻璃拟态 + 青绿主色 + 扫描线） |
| 3D 地球 | globe.gl（MIT，three 0.185.1） |
| 图表 | ECharts（Apache-2.0） |
| 2D 地图 | Leaflet（已移除 1.7.0，组件保留备恢复） |
| 测试 | Vitest |
| 语言 | 全中文 UI，无 i18n |
| 依赖包 | 零新依赖（1.7.0 vs 1.6.0 unchanged） |

---

## 扩展标准（改代码记住三条入口）

| 操作 | 只改一个文件 | 例 |
|------|-------------|-----|
| 加新 feed | `src/config/dataSources.ts` `FEEDS` 登记一项 | `news_geo`、`market_quotes` 均如此 |
| 加新面板 | `src/panels/registry.ts` `panelRegistry` 加一项 | NuclearWatchPanel |
| 加新类别 | `src/config/layerCategories.ts` 加一项 + `theme.ts` 加色 | — |

---

## 项目结构

```
kaiyang-wave2/
├── AGENTS.md               ← 本文件
├── ROADMAP.md               ← 项目内权威 todo
├── README.md                ← 项目概述
├── VERSION                  ← 当前版本号（1.7.0）
├── CHANGELOG.md             ← 变更记录
├── package.json
├── src/
│   ├── main.tsx             ← ErrorBoundary 入口
│   ├── App.tsx              ← grid-layout + 面板注册表
│   ├── config/              ← dataSources / layerCategories / theme / regions / controlConfig
│   ├── components/          ← WorldPanel / GlobePanel / FlatMapPanel(备) / LayerTreePanel …
│   ├── control/             ← ControlDrawer / TianshuTab / FetcherCard …
│   ├── hooks/               ← useFeed / useControlApi / useOperationPolling …
│   ├── lib/                 ← adaptGrv / nuclearData / newsGeoAdapter / controlApi …
│   ├── panels/              ← registry.ts（面板注册表）+ 各面板组件
│   ├── state/               ← ControlContext / SelectionContext / StatusContext
│   └── types/               ← contracts.ts / control.ts
├── docs/                    ← DESIGN / DATA_CONTRACT / HANDOFF / DECISION_MATRIX / PRD …
├── public/
│   └── data/                ← 开发快照（grv_latest.json / fred_history / nuclear_sites.json …）
└── dist/                    ← 构建产物
```

---

## 数据契约

- 权威标准：`docs/DATA_CONTRACT.md`
- feed 统一入口：`src/config/dataSources.ts` → `useFeed()` 自动读取
- 字段容错降级：`null` / 缺失 → 空数组 / fallback 值，不白屏
- `schema_version`：读取层比对告警，不阻塞渲染

---

## 测试

```bash
npm test          # 297 passed（1.6.0 基线，1.7.0 未改测试）
```

## 部署

纯静态前端，端口 `:3118`：

```bash
npm install && npm run build
# 产物在 dist/，任意静态服务器挂载即可
```
