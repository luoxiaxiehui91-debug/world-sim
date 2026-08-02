# 开阳（Kaiyang）操作面板 — ROADMAP

> 此文件是开阳项目内权威 todo，与源代码同行。
> 版本参考：`VERSION`（当前 1.7.0）
> 跨项目视角：`S:\docs\backlog\world-deduction.md`
> AI 工作入口：`AGENTS.md`

---

## 已完成

| 版本 | 日期 | 交付 |
|------|------|------|
| 1.0.0 | 2026-07-30 | Wave 1：3D 地球 + GRV + 经济 + 新闻 + 状态条 |
| 1.1.0 | 2026-08-01 | 控制面 P0：右侧抽屉 + 天枢运维 Tab + Mock 自闭环 |
| 1.2.0 | 2026-08-01 | crucix 分类图层 P0：12 类 + 核设施图层 |
| 1.3.0 | 2026-08-01 | 战略要地标签 + osint 删除 |
| 1.4.0 | 2026-08-01 | 地区 Tab + 顶栏 KPI + 信号联动 |
| 1.5.0 | 2026-08-01 | 左侧指标树 LayerTreePanel |
| 1.6.0 | 2026-08-01 | §4.5 清扫 + news_geo 骨架 + 决策矩阵 |
| **1.7.0** | **2026-08-02** | BugFix（NaN 崩溃 + 抽屉关闭）+ ErrorBoundary + 2D 移除 |

---

## 时间门控任务

| 状态 | 预估时间 | 任务 | 前置条件 |
|------|---------|------|---------|
| ⏸ | 待天枢产出 | **news_geo 上图** | 天枢 GDELT geo feed 到位（读取层骨架已在 1.6.0 完成，免改代码） |
| ⏸ | 待天枢产出 | **market_quotes 面板** | 天枢产出 `market_quotes.json`（类型+FEEDS 已在 1.6.0 预埋） |
| ⏸ | 待天枢产出 | **FRED 经济面板恢复** | 天枢产出 `fred_history` manifest.json（当前面板为空） |
| ⏸ | 待控制面后端 | **控制面切真实 API** | 后端 A3a 文件投递协议实现 + 前端 adapter 层 |
| ⏸ | 待自建 tileserver | **2D 平面地图恢复** | 自建 tileserver-gl + OSM 矢量数据（CartoDB/ESRI/OSM/Voyager 四家已证实不可用） |
| ⏸ | 待后端 feed | **P1/P2 图层接入**（空域/热异常/海上/太空/卫生/SDR） | 天枢产出对应 feed（④空域⑤热异常已有基础可优先） |

---

## 积压（无时间门控）

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P1 | **底部行情带** | 6 格风险仪表（VIX/利差/GSCPI 等），需 fred manifest 补序列 |
| P1 | **信号流 sweep delta** | 前后两期信号变化量展示，等后端算好推送 |
| P2 | **聚类标签**（Ukraine 71 式） | 前端 1°×1° bbox 聚合兜底（<200 点），详见 DECISION_MATRIX D2 |
| P2 | **新闻面板补地理坐标** | 等天枢 news_export 带 lat/lng |
| P2 | **2D 平面地图增强** | 自建 tileserver 后恢复：地区 fitExtent、鼠标 pan/zoom、离线瓦片 |

---

## 决策矩阵（待拍板）

> 详见 [`docs/DECISION_MATRIX.md`](./docs/DECISION_MATRIX.md)

| # | 决策 | 推荐 | 阻塞 |
|---|------|------|:--:|
| D2 | 聚类：前端 bbox vs 后端预聚合 | 折中：后端预留 reader + 前端 1°×1° bbox 兜底 | 否 |
| D3 | feed 粒度：每类一文件 vs 聚合 | 每类一文件（已写进契约） | 否 |
| D4 | SSE 实时推送 | 不做（日/周频无意义） | 否 |
| D5 | 解锁 Leaflet/MapLibre 新依赖 | 不解锁（路线 A 已证可走） | 否 |

---

## 活跃问题

| 编号 | 状态 | 问题 | 说明 |
|------|------|------|------|
| — | ✅ 已修 (1.7.0) | **Leaflet NaN 崩溃** | FlatMapPanel flyToBounds 在容器 0 高度时算 NaN; 已加 size 检查 + isNaN 防护 |
| — | ✅ 已修 (1.7.0) | **控制抽屉不能关** | prevOpen 赋值在 return 后永远不执行; 已移入分支内 |
| — | ✅ 已修 (1.7.0) | **2D 瓦片全覆盖不可接受** | CartoDB/ESRI/OSM/Voyager 实测均不可用; 2D 视图已移除备恢复 |
| — | ⏸ | **控制面 REST≠文件投递** | 前端用 REST API，后端文档定义文件 IPC，需写 adapter |

---

## 较大工程（需外部资源）

| 项目 | 前置条件 | 说明 |
|------|---------|------|
| **自建 tileserver-gl** | NAS 部署 tileserver-gl + OSM 矢量数据 | 解决 2D 瓦片依赖第三方问题 |
| **ACLED 武装冲突数据** | 申请 `acleddata.com` API key | 接入后大幅提升冲突维度信号质量 |
