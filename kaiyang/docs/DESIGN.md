# 开阳（Kaiyang）操作面板 · 设计文档

> 版本：Wave 1 · v1.0.3 对齐版 ｜ 更新日期：2026-07-31
> 配套数据权威标准：同目录 [`DATA_CONTRACT.md`](./DATA_CONTRACT.md)

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
  - 写侧**协议（端点 / 文件流向 / 鉴权 / 权限分级）暂缓设计**，待后端闭环搭起后再定；但**控制范围不蔓延**。
- **隔离铁律（精确版，用户硬性）**：代码层与天枢 / 天璇 / 天玑 / crucix **完全隔离**（禁止 `import` / 拷贝其它项目源码）；开阳**永不自行**调用任何第三方数据源 / 爬虫 / 外部 API 做采集（FRED、GDELT、RSS 等被明确排除）——但开阳**可以**向自家后端下发操作指令、由后端执行。二者性质不同：**「不爬第三方数据源」≠「不能和自家后端通信」**。禁止硬编码 NAS / SMB 绝对路径（如 `S:\...`），部署靠外部只读挂载 + 改 `DATA_BASE_URL`。

## 2. crucix 复刻策略

- **为什么复刻**：① 开源协议 AGPL-3.0（不可直接改后分发）；② 项目语言问题（UI 英文→中文；采集器 JS→Python 归天枢）。
- **展示半边** → 开阳 **clean-room 重写**：用 MIT / Apache 库（globe.gl / ECharts），不抄 AGPL 代码，全中文 UI，视觉继承 crucix 的玻璃拟态 + 青绿酷感。
- **采集半边** → 天枢 **Python 重实现**（用户：先不急，属天枢范围）。
- **控制半边** → 开阳**操作面板职能**（本设计新增）：面向全系统的受控指令下发，协议暂缓（见 §1）。

## 3. 技术栈（已定，不改动）

- React + Vite + TypeScript + Tailwind CSS
- 3D 地球：**globe.gl**（MIT）
- 图表：**ECharts**（Apache-2.0）
- 视觉：玻璃拟态 + 青绿主色 + 扫描线（全中文 UI，无 i18n）
- 产物：**纯前端静态站点**（`vite build` 输出 `dist/`）——自身**无业务后端**；控制指令经受控通道下发至各后端执行（开阳只发令、后端执行）。

## 4. Wave 规划

- **Wave 1（已完成，构建通过）** —— 仅天枢现有数据可喂的：
  - 3D 地球（globe.gl）：11 维 GRV 风险点 + 地缘联动弧线
  - GRV 面板（ECharts）：各维度数值 + 不确定区间（如 52.7±8，渲染为误差带 / 扇形）
  - 经济面板（ECharts）：FRED 关键序列
  - 新闻 / 叙事面板：`news_export` 条目列表
  - 顶部状态条：数据时间戳 + 缺失字段告警
  - **v1.0.3 增强**：气候风险 / 自然灾害维度**不再画常驻地图柱**，改为 `events[]` **事件触发式告警柱**（有事件才在事发地画 ⚠ 柱，缺省不渲染）。
- **Wave 2（待启动）** —— 接入天璇（D.hypothesis）/ macro-sim（D.sim）/ 天玑（D.verification）新格式输出；新增面板 = 只加 `panelRegistry` 注册项，不改布局。同时落地写侧受控指令协议（端点 / 鉴权 / 权限分级）。

## 5. 扩展标准（预埋，新增信息只加注册项、不改布局）

1. **统一读取层** `useFeed(feedName)`：所有数据经 `src/hooks/useFeed.ts` + `src/lib/readLayer.ts`；新增 feed 只在 `src/config/dataSources.ts` 的 `FEEDS` 登记一项。
2. **面板注册表** `panelRegistry`（`src/panels/registry.ts`）：每面板 = 组件 + 注册项（`id/title/feed/order/visible/className`）；新增面板只加一项。
3. **字段容错**：缺失 → 「数据缺失」占位 + 状态条告警，不白屏 / 不崩。
4. **schema 版本**：每个 feed JSON 带 `schema_version`（Wave1 = `1.0`）；breaking change 须 bump，读取层比对并告警。
5. **数据契约权威文档** `DATA_CONTRACT.md`：各 feed 文件名 / 路径 / 字段 / schema_version / 部署。

## 6. 数据契约（摘要，详见 DATA_CONTRACT.md）

- 读取根 `DATA_BASE_URL`，默认 `./data/`（含 `public/data` 开发快照），部署改指向 NAS 只读挂载。
- 4 个 feed：`grv` / `news` / `fred` / `simTrigger`，schema 均 `1.0`。
- **事件触发告警柱**：`grv_latest.json` 可选 `events[]`（`GrvEvent`：id / type / label / lat / lng / value / note）。气候 / 灾害类维度（`renderBar:false`）的地图呈现改由 `events[]` 承担，平时缺省不渲染。
- 当前上游真实文件与文档契约存在偏差（上游缺 lat/lng、缺不确定区间、news 实为 `latest_news.json`），已由适配层 + 状态条降级渲染，不破、不白屏。

## 7. 部署

- 独立静态站，端口 **:3118**（沿用复现方案）。
- 只读挂载天枢 `data` 目录 → 容器路径（如 `/mnt/tianshu-data/`）；构建 / 运行时注入 `DATA_BASE_URL`（`window.__KAIYANG_DATA_BASE_URL__` 或 `VITE_DATA_BASE_URL`）。
- **读侧**：无业务后端，浏览器按契约 `fetch` 拉取只读快照（可配合 CDN / 缓存策略，数据刷新由天枢侧更新文件即可）。
- **写侧**：控制指令经受控通道下发至各后端执行（协议暂缓，详见 `DATA_CONTRACT.md` §2.3）。
- 详见 `DATA_CONTRACT.md` §4。

## 8. 当前交付状态（2026-07-31 · v1.0.3）

- 源码已落地 `S:\world-sim\kaiyang`（A 同步：commit `519f1d6`，已 push main）。
- 本次对齐：将本设计文档由旧「纯展示层」定位改写为「操作面板（展示 + 控制双职能）」，与 `DATA_CONTRACT.md` 完全对齐；修正 §1 / §3 / §7 中「无后端 / 纯展示」等滞后措辞。
- S 盘侧需重建：`npm install && npm run build`（建议 NAS 主机本地路径执行，避免 SMB 上 symlink 问题）。
- 开发期预览：WorkBuddy 副本 `kaiyang-wave1/`（与 NAS 同源，待用户确认是否保留）仍可 `npm run dev`（:5173）/ `npm run preview`（:4173）。

## 9. 目录结构

```
kaiyang/
├── index.html
├── package.json
├── vite.config.ts / tsconfig*.json / tailwind.config.js / postcss.config.js
├── DATA_CONTRACT.md          ← 数据契约权威标准
├── DESIGN.md                 ← 本设计文档（操作面板 · 设计总纲）
├── src/
│   ├── main.tsx / App.tsx / index.css
│   ├── components/  (EChart / GlobePanel / GrvPanel / EconomyPanel / NewsPanel / StatusBar / WorldPanel / FlatMapPanel)
│   ├── config/      (dataSources: DATA_BASE_URL+FEEDS / grvDimensions: 11维坐标+弧线+renderBar)
│   ├── hooks/       (useFeed 统一读取层 / useFRED)
│   ├── lib/         (readLayer fetchJson/fetchCsv / grvAdapter 适配容错 / mapData buildRiskPoints/buildEventBars / format)
│   ├── panels/      (registry: panelRegistry)
│   ├── state/       (StatusContext: 时间戳/告警/schema版本)
│   └── types/       (contracts: GrvRaw / GrvEvent / NewsItem / FredSeriesMeta)
└── public/data/     ← 开发快照（grv_latest.json / news_export.json / sim_trigger.json / fred_history/*）
```
