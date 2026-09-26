# 开阳（Kaiyang）操作面板 — AI 工作入口

> **如在 monorepo 中工作，先读根目录 [`../AGENTS.md`](../AGENTS.md)（系统全貌 + 阅读路径入口）。**
> **跨项目知识库入口**：中央知识库 = `S:\docs\`（NAS 侧 `/vol2/1000/software/docs/`）；规则真源 = `S:\docs\AGENTS.md`（问题流程 / CHG 变更日志 / 文档写作规范）。改代码 / 部署后**必须按文末「中央知识库同步（CHG 五步）」同步中央知识库**（2026-08-30 CHG 体系）。

## 当前状态快照

**版本**：v1.11.34（2026-08-18）  
**主要变更（08-16→08-18）**：审查 B0-B4 全清（H18 sim_trigger 契约 / H01 randomUUID / H02 token 外泄 / H08+H11 原子写）；卫生+地区新闻图层功能链齐；**LLM 配置面板（v1.11.26-27）**；报告中心全开/全关+近期过滤（v1.11.28）；**控制面三 tab：天璇只读版（推演记录+触发状态，v1.11.29）/ 政权更迭事件可视化卡片（v1.11.30）/ 天玑只读版 + 人工验证界面化 [发生/部分/未发生] 点选（v1.11.31-32）**；字号/判据显示修复（v1.11.33-34）
**已完成**：2D 地图 D3 geoNaturalEarth1 重写（1.8.0）+ react-grid-layout；A3a 控制 API（1.7.2）；实时化（1.9.0）；事件弹框+聚合（1.10.5-8）
**待处理**：`docs/DECISION_MATRIX.md` D2（前端 bbox 聚类，点位超阈值时触发）；P2 图层逐类接入（等天枢 feed）；玉衡 tab（等 verify_auto 每月 1 日权重数据）
**下一里程碑**：P2 门控等数据（自动化每月 13 日检查）；天璇控制台写操作（触发/调参，控制面二期）

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
| **⛔ 构建必带 token** | `VITE_CONTROL_API_TOKEN=<compose 的 CONTROL_TOKEN> npm run build`（v1.11.15+，控制台开箱即用；不带 → 前端无内置 token → 控制台 401；token 轮换同步更新，见 `docs/DEPLOYMENT.md` §1） |
| **LLM 配置面板** | 控制台 TokenSetup 下方「LLM 使用点 N 个 · 配置」——7 使用点 × 2 平台（MiMo Plan/SiliconFlow）可换平台+模型+API key（后端 `llm_usage.py`，写 `data/llm_config.json` 原子写；key 不回显明文）；改动后端 `llm_usage.py` / `hybrid_llm.py` 后须重启 control_server（:8900）并 curl 验证新路由生效 |
| **d3 事件 + React 重渲染** | 在 d3 元素挂 click 且 handler 触发 setState → 节点重建 → 冒泡到祖先时 target detached → closest 误判。**子元素 handler 有副作用必须 `event.stopPropagation()`**（v1.11.24→25 血泪）；验证用真实鼠标序列（dispatchEvent 会假通过） |

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
| `docs/DATA_CONTRACT.md` | 数据契约权威标准（字段/路径/schema_version，含 §2.12 news_titles / §2.13 llm_config） | 消费新数据源时 |
| `docs/A3a-控制API-开阳对接文档.md` | 控制 API 对接规范（HTTP REST :8900 / 命令格式 / news-title / llm-usage 端点） | 改控制面逻辑时 |
| `docs/DEPLOYMENT.md` | 部署规范（构建必带 VITE_CONTROL_API_TOKEN / scp 覆盖 / 清理规则） | 构建部署时 |
| `docs/NEXT_SESSION_HANDOFF.md` | **接手快照**（版本链 / 重点 / gotcha，比本文档更细） | 新 session 必读 |
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
├── VERSION                 ← 当前版本号（1.11.27）
├── CHANGELOG.md            ← 变更记录
├── src/
│   ├── config/             ← dataSources / layerCategories / theme / regions / controlConfig
│   ├── components/         ← WorldPanel / GlobePanel / FlatMapPanel / EventPopup / StatusBar …
│   ├── control/            ← ControlDrawer / TianshuTab / FetcherCard / TokenSetup / LlmConfig / TabBar
│   ├── hooks/              ← useFeed / useControlApi / useOperationPolling …
│   ├── lib/                ← adaptGrv / nuclearData / newsGeoAdapter / geoAggregate / healthAdapter / controlApi / uuid …
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

## 中央知识库同步（CHG 五步，2026-08-30 起）

任何非只读变更（改代码 / 改配置 / 部署 / 归档 / 文档修改）都要走中央 CHG 生命周期（格式真源 = `S:\docs\AGENTS.md` §operations/ 系统日志）：

1. **实施前**：建 `S:\docs\operations\CHG-<YYYYMMDDTHHmmss>-kaiyang.md`（9 字段 frontmatter + `## Pre-Change` 写完冻结）
2. **实施**：改代码 + 按版本同步清单更新（kaiyang 清单 = `VERSION` + `package.json` + `CHANGELOG.md` + `S:\docs\INDEX.md` 版本状态表）
3. **同步**：更新 `S:\docs\INDEX.md` 版本状态行（版本号 + 日期 + 一行摘要）+ `S:\docs\questions\world-deduction\` 相关 question 状态
4. **收尾**：CHG 追加 `## Post-Change`（完成时间 / 实施摘要 / 验证），frontmatter status 改 `completed`
5. **边界**：纯报问题建档（question doc + INDEX 加行）**不建 CHG**——CHG 只覆盖实施变更，不覆盖记录「发现」

NAS 侧路径等价：`/vol2/1000/software/docs/`。问题归属统一建在 `questions/world-deduction/`。
