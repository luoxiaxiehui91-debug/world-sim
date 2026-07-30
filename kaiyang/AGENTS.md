# AGENTS.md · 开阳（Kaiyang）展示层

AI 协作者的 session 入口。改动前先读本文档 + [`docs/DATA_CONTRACT.md`](./docs/DATA_CONTRACT.md) + [`docs/DESIGN.md`](./docs/DESIGN.md)。

---

## 1. 项目角色与边界（硬约束）

- **纯展示层**：世界推演系统下独立子项目，正式位置 `S:\world-sim\kaiyang`，与 `macro-scan` / `macro-sim` 平级。
- **获取 / 展示分离**：信息**获取**归天枢（macro-scan, Python）；开阳只读契约文件，**永不直接调用数据源 / 爬虫 / 外部 API**。
- **隔离铁律（用户硬性）**：
  - 禁止 `import` / 拷贝 macro-scan / macro-sim / 天玑 / crucix 任何源码。
  - 禁止硬编码 NAS / SMB 绝对路径（如 `S:\...` / `192.168.x`）；部署靠外部只读挂载 + 改 `DATA_BASE_URL`。
  - 唯一外部耦合 = `DATA_BASE_URL` 只读契约文件（见 §3）。

## 2. 目录结构

```
kaiyang/
├── README.md              ← 人类概览
├── AGENTS.md              ← 本文件（AI 入口）
├── CHANGELOG.md           ← 变更记录
├── VERSION                ← 版本号（与 CHANGELOG 头一致）
├── index.html / package.json / vite.config.ts / tsconfig*.json
├── tailwind.config.js / postcss.config.js / .gitignore
├── docs/
│   ├── DESIGN.md          ← 设计总纲（定位/技术栈/Wave/扩展标准）
│   └── DATA_CONTRACT.md   ← 数据契约权威标准（feed/字段/schema_version/部署）
├── src/
│   ├── App.tsx / main.tsx / index.css
│   ├── components/  (EChart / GlobePanel / GrvPanel / EconomyPanel / NewsPanel / StatusBar)
│   ├── config/      (dataSources: DATA_BASE_URL+FEEDS / grvDimensions: 11维坐标+弧线)
│   ├── hooks/       (useFeed 统一读取层 / useFRED)
│   ├── lib/         (readLayer fetchJson/fetchCsv / grvAdapter 适配容错 / format)
│   ├── panels/      (registry: panelRegistry)
│   ├── state/       (StatusContext: 时间戳/告警/schema版本)
│   └── types/       (contracts)
└── public/data/     ← 开发快照（grv_latest.json / news_export.json / sim_trigger.json / fred_history/*）
```

## 3. 数据接口契约（只读）

- 读取根 `DATA_BASE_URL`，默认 `./data/`（含 `public/data` 开发快照），部署改指向 NAS 只读挂载。
- 4 个 feed：`grv` / `news` / `fred` / `simTrigger`，schema 均 `1.0`。
- 字段定义、CSV 格式、扩展方式、部署细节 → **权威标准见 [`docs/DATA_CONTRACT.md`](./docs/DATA_CONTRACT.md)**。

## 4. 扩展标准（新增信息只加注册项、不改布局）

1. **统一读取层** `useFeed(feedName)`：`src/hooks/useFeed.ts` + `src/lib/readLayer.ts`。新增 feed 只在 `src/config/dataSources.ts` 的 `FEEDS` 登记一项，读取层不动。
2. **面板注册表** `panelRegistry`（`src/panels/registry.ts`）：每面板 = 组件 + 注册项（`id/title/feed/order/visible/className`）。新增面板只加一项，`App.tsx` 网格布局不变。
3. **字段容错**：缺失 → 「数据缺失」占位 + 状态条告警，不白屏 / 不崩。
4. **schema 版本**：每个 feed JSON 带 `schema_version`（Wave1 = `1.0`）；breaking change 须 bump，读取层比对并告警。
5. **数据契约权威文档** `docs/DATA_CONTRACT.md`：后续扩展的唯一标准。

### 加一个新面板

1. 在 `src/components/` 写组件，用 `useFeed` 取数；
2. 在 `src/panels/registry.ts` 加一条注册项（`id/title/feed/order/visible`）。完成——布局无需改动。

### 加一个新 feed

1. 在 `src/config/dataSources.ts` 的 `FEEDS` 登记一项（文件名 / schema_version / 解析器）；
2. 同步更新 `docs/DATA_CONTRACT.md` 的 Feed 注册表与字段定义。读取层无需改动。

## 5. 维护铁律

- **改前必读**：`AGENTS.md` + `docs/DATA_CONTRACT.md` + `docs/DESIGN.md`。
- **改后必记**：① bump `VERSION`；② 在 `CHANGELOG.md` 追加一条（改了什么 / 为什么 / 不动什么）；③ 若接口或架构变动，同步更新 `docs/` 两份文档。
- **禁止**：把获取逻辑写进开阳（爬虫 / fetcher / 外部 API）；把其它项目源码带入；硬编码部署路径。
- **构建验证**：提交前 `npm run build` 必须绿（tsc --noEmit + vite build）。

## 6. 阅读顺序建议

`README.md` → `docs/DESIGN.md`（定位与边界）→ `docs/DATA_CONTRACT.md`（数据接口）→ `src/config/dataSources.ts` + `src/panels/registry.ts`（扩展锚点）→ `src/lib/readLayer.ts` + `src/hooks/useFeed.ts`（读取层）。
