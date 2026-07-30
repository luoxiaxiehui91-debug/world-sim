# 开阳（Kaiyang）展示层

世界推演系统下的**纯展示层**：把天枢 / 天璇 / 天玑 / macro-sim 已发布的契约数据，**好看地摆出来**。

- **获取 vs 展示分离**：信息**获取**归天枢（macro-scan），开阳只做**展示**。开阳**永不**直接调用数据源 / 爬虫 / 外部 API，唯一数据来源是只读契约文件。
- **独立子项目**：位于 `S:\world-sim\kaiyang`，与 `macro-scan` / `macro-sim` 平级，纳入 world-sim monorepo。代码层与天枢 / 天璇 / 天玑 / crucix **完全隔离**（用户硬性铁律）。

> 设计总纲见 [`docs/DESIGN.md`](./docs/DESIGN.md)；数据契约权威标准见 [`docs/DATA_CONTRACT.md`](./docs/DATA_CONTRACT.md)；AI 协作者入口见 [`AGENTS.md`](./AGENTS.md)；变更记录见 [`CHANGELOG.md`](./CHANGELOG.md)。

---

## 技术栈

React + Vite + TypeScript + Tailwind CSS ＋ globe.gl（3D 地球，MIT）＋ ECharts（图表，Apache-2.0）。玻璃拟态 + 青绿主色 + 扫描线视觉，全中文 UI，无 i18n。产物为**纯静态站点**，无后端。

## 快速开始

```bash
npm install
npm run dev        # http://localhost:5173 ，开箱即跑（内置 public/data 开发快照）
npm run build      # 产出 dist/
npm run preview    # 预览构建产物
```

## 部署（纯静态，端口 :3118）

1. `npm install && npm run build` → 生成 `dist/`。
2. 将天枢 `data/` 以**只读**挂载到容器路径（如 `/mnt/tianshu-data/`）。
3. 任意静态服务器（nginx / caddy / `npx serve dist`）服务 `dist/`。
4. 在 `dist/index.html` 的 `<div id="root">` 前注入数据根：
   ```html
   <script>window.__KAIYANG_DATA_BASE_URL__ = "/mnt/tianshu-data/";</script>
   ```
   或构建期 `VITE_DATA_BASE_URL=/mnt/tianshu-data/ npm run build`。

> 数据由天枢侧更新文件即可刷新；开阳无需后端。详见 [`docs/DATA_CONTRACT.md`](./docs/DATA_CONTRACT.md) §4。

## 当前状态

- **Wave 1（已完成，构建通过）**：3D 地球 + GRV + 经济 + 新闻四面板，基于天枢现有数据。
- **Wave 2（待启动）**：接入天璇 / 天玑 / macro-sim 新格式输出，新增面板 = 只加注册项，不改布局。
