# 开阳（Kaiyang）操作面板 — ROADMAP

> 此文件是开阳项目内权威 todo，与源代码同行。
> 版本参考：`VERSION`（当前 1.11.27）
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
| 1.7.1 | 2026-08-03 | 控制抽屉 MOCK 横幅（MOCK_ENABLED=true 时琥珀色警告） |
| **1.7.2** | **2026-08-03** | A3a 控制 API 接入（MOCK_ENABLED=false，HTTP REST :8900） |
| **1.8.0** | **2026-08-04** | ✅ 2D 地图 D3 geoNaturalEarth1 重写（Leaflet 方案废弃）；✅ react-grid-layout 可拖拽布局 |
| **1.9.0** | **2026-08-06** | ✅ 实时化收尾：market_quotes 行情面板 60s 轮询；news_geo GDELT geo feed 上线上图；控制面真实 REST 链路 |
| **1.10.5-8** | **2026-08-10~15** | ✅ 事件弹框 + 同地点聚合（bbox + 拼写变体合并） |
| **1.11.12-15** | **2026-08-16** | ✅ footer 盖层 + Token 配置 UI + H18 sim_trigger 契约 + schema_version 统一 + H01 randomUUID + H02 token 外泄 + 内置 CONTROL_TOKEN |
| **1.11.16-18** | **2026-08-16** | ✅ 卫生图层功能链：source_media 媒体名 + 点击弹框 + DISEASE_ZH 中文疾病名 + DOC API 标题回填 |
| **1.11.19-23** | **2026-08-16** | ✅ 地区新闻标题真实化：URL slug（废弃）→ 按需抓取（/news-title）→ 预抓缓存（news_titles.json I120）→ LLM 中文翻译（titles_zh） |
| **1.11.24-25** | **2026-08-16** | ✅ 地图交互：点击空白/关闭弹框取消选中（v1.11.24）→ 回归修复（点位 click 阻断冒泡，v1.11.25） |
| **1.11.26-27** | **2026-08-16** | ✅ LLM 配置体系：使用点清单 + 控制台改模型（v1.11.26）→ 平台化（平台/模型/API key 统一切换，v1.11.27）；翻译模型 mimo-v2.5 |

---

## 时间门控任务

| 状态 | 预估时间 | 任务 | 前置条件 |
|------|---------|------|---------|
| ✅ | 2026-08-04 | **2D 地图换 D3 geoNaturalEarth1** | **已兑现**：FlatMapPanel 用 d3-geo geoNaturalEarth1 + SVG 重写，根治子午线伪线；Leaflet 方案未实施 |
| ✅ | 2026-08-06 | **news_geo 上图** | **已兑现**：天枢 GDELT geo feed（news_geo_feed.py）上线 + scheduler 注册，前端免改代码自动上图 |
| ✅ | 2026-08-06 | **market_quotes 面板** | **已兑现**：`market_quotes.json` 已注册 + 行情面板 60s 轮询 |
| ✅ | 2026-08-06 | **FRED 经济面板恢复** | **已兑现**：fred manifest 已上线（VIX/高收益利差已存在；GSCPI 待天枢补） |
| ✅ | 2026-08-03 | **控制面切真实 API** | **已兑现**：A3a 后端为 HTTP REST control_server（:8900），非文件投递；MOCK=false |
| ⏸ | 待天枢产出 | **P1/P2 图层接入**（空域/热异常/海上/太空/卫生/SDR） | 天枢产出对应 feed（④空域⑤热异常已有基础可优先） |

---

## 积压（无时间门控）

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P1 | **底部风险仪表增强** | 行情带已上线（1.9.0）；VIX/利差序列已就绪，GSCPI 等 fred manifest 补序列 |
| P1 | **信号流 sweep delta** | 前后两期信号变化量展示，等后端算好推送 |
| P2 | **聚类标签**（Ukraine 71 式） | 前端 1°×1° bbox 聚合兜底（<200 点），详见 DECISION_MATRIX D2 |
| P2 | **2D 地图增强** | D3 版已上线（1.8.0）；后续可加地区 fitExtent、鼠标 pan/zoom |

---

## 决策矩阵（已文档化）

> 详见 [`docs/DECISION_MATRIX.md`](./docs/DECISION_MATRIX.md)

| # | 决策 | 推荐 | 状态 |
|---|------|------|:--:|
| D2 | 聚类：前端 bbox vs 后端预聚合 | 折中：后端预留 reader + 前端 1°×1° bbox 兜底 | 待触发 |
| D3 | feed 粒度：每类一文件 vs 聚合 | 每类一文件（已写进契约） | ✅ 已隐含采纳 |
| D4 | SSE 实时推送 | 不做（日/周频无意义） | ✅ 已隐含采纳 |
| D5 | 解锁 Leaflet/MapLibre 新依赖 | 不解锁（已改 D3 geoNaturalEarth1 方案） | ✅ 已定案 |

---

## 活跃问题

| 编号 | 状态 | 问题 | 说明 |
|------|------|------|------|
| — | ✅ 已修 (1.7.0) | **Leaflet NaN 崩溃** | FlatMapPanel flyToBounds 在容器 0 高度时算 NaN; 已加 size 检查 + isNaN 防护 |
| — | ✅ 已修 (1.7.0) | **控制抽屉不能关** | prevOpen 赋值在 return 后永远不执行; 已移入分支内 |
| — | ✅ 已修 (1.7.0) | **2D 瓦片全覆盖不可接受** | CartoDB/ESRI/OSM/Voyager 实测均不可用; 1.8.0 改 D3 geoNaturalEarth1 + SVG 重写 |
| — | ✅ 已解决 (1.7.2) | **控制面 REST≠文件投递** | 实测后端为 HTTP REST control_server（:8900）非文件投递；前端 controlApi.ts 已按 REST 对接，MOCK=false |

---

## 较大工程（需外部资源）

| 项目 | 前置条件 | 说明 |
|------|---------|------|
| **ACLED 武装冲突数据** | 申请 `acleddata.com` API key | 接入后大幅提升冲突维度信号质量 |
