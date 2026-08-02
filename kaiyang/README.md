# 开阳（Kaiyang）操作面板

世界推演系统下的**独立前端操作面板**：既读取天枢 / 天璇 / 天玑 / macro-sim 已发布的契约数据做可视化呈现，也代表人类 operator 经各后端正规控制通道**下发操作指令**（触发推演 / 重跑采集 / 调参 / 审批等），指令由后端执行。

- **展示 + 控制双职能**：① 展示侧只读契约文件；② 控制侧经受控指令通道下发操作，开阳自身不执行业务逻辑。
- **永不自行获取**：开阳**永不**直接调用数据源 / 爬虫 / 外部 API，唯一数据来源是只读契约文件（部署经 `DATA_BASE_URL` 只读挂载）。
- **独立子项目**：位于 `S:\world-sim\kaiyang`，与 `macro-scan` / `macro-sim` 平级，纳入 world-sim monorepo。代码层与天枢 / 天璇 / 天玑 / crucix **完全隔离**（用户硬性铁律）。

> 设计总纲见 [`docs/DESIGN.md`](./docs/DESIGN.md)；数据契约权威标准见 [`docs/DATA_CONTRACT.md`](./docs/DATA_CONTRACT.md)；AI 协作者入口见 [`AGENTS.md`](./AGENTS.md)；变更记录见 [`CHANGELOG.md`](./CHANGELOG.md)；任务路线图见 [`ROADMAP.md`](./ROADMAP.md)。

---

## 技术栈

React + Vite + TypeScript + Tailwind CSS ＋ globe.gl（3D 地球，MIT）＋ ECharts（图表，Apache-2.0）。玻璃拟态 + 青绿主色 + 扫描线视觉，全中文 UI，无 i18n。产物为**纯静态前端站点**；开阳自身无业务逻辑后端，操作指令经各后端正规控制通道下发、由后端执行。

## 快速开始

```bash
npm install
npm run dev        # http://localhost:5173 ，开箱即跑（内置 public/data 开发快照）
npm run build      # 产出 dist/
npm run preview    # 预览构建产物
```

## 部署（纯静态前端，端口 :3118）

1. `npm install && npm run build` → 生成 `dist/`。
2. 将天枢 `data/` 以**只读**挂载到容器路径（如 `/mnt/tianshu-data/`）。
3. 任意静态服务器（nginx / caddy / `npx serve dist`）服务 `dist/`。
4. 在 `dist/index.html` 的 `<div id="root">` 前注入数据根：
   ```html
   <script>window.__KAIYANG_DATA_BASE_URL__ = "/mnt/tianshu-data/";</script>
   ```
   或构建期 `VITE_DATA_BASE_URL=/mnt/tianshu-data/ npm run build`。

> 读取侧由天枢侧更新文件即可刷新，开阳无需后端读取服务；控制侧指令通道协议由后端闭环定义（暂缓，待各模块闭环搭起）。详见 [`docs/DATA_CONTRACT.md`](./docs/DATA_CONTRACT.md) §4。

## 当前状态

**`VERSION = 1.7.0`**（2026-08-02），297 测试通过。

```
Wave1 ✅ | Wave2 P0 ✅（控制面 + crucix 分类图层+核设施 139/139）
         | Wave2 P1 ✅（战略要地 → 地区Tab/KPI/信号 → 指标树）
         | 1.6.0  ✅（§4.5 清扫 + news_geo 骨架 + 决策矩阵）
         | 1.7.0  ✅（NaN 崩溃修复 + 抽屉关闭 + ErrorBoundary + 2D 移除）
         | 剩余 P1/P2 ⏸ 卡在后端 feed
```

- **分类图层 12 类**（osint 已删），D1 颜色编码方案 A 永久锁定
- **3D 地球**正常工作，**2D 平面地图已移除**（CartoDB/ESRI/OSM/Voyager 瓦片全覆盖不可接受，组件备恢复）
- **news_geo 读取层骨架**已就绪（1.6.0），等天枢 GDELT geo feed 到位后免改代码自动上图
- **控制面** Mock 自闭环（`MOCK_ENABLED=true`），后端 API 就绪后改一行切真实
