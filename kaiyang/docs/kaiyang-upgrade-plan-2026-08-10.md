# 开阳补全规划（2026-08-10）

> 类别：意图（INTENT）· 状态标记（规划/进行中/已交付）
> 基于：DESIGN.md（v1.9.0 Wave 规划）+ CRUCIX_UPGRADE_DESIGN.md（P1/P2 路线图）+ PRD_CONTROL_PANEL.md + 08-10 现状盘点
> 触发：用户"开阳缺了很多功能，最起码报告没进去；控制台基本没实现；信息源同步；新闻事件地图；团队残留"

---

## 一、已有规划盘点（先对齐，不重复造）

### 已完成（Wave 1 + Wave 2 双线 P0）
| 线 | 内容 | 版本 |
|----|------|------|
| Wave 1 | 3D 地球 GRV + GRV 面板 + 经济面板（FRED）+ 新闻/叙事面板 + 状态条 + 事件触发告警柱 | v1.0.x |
| 线 a 控制面 P0 | 右侧抽屉 + 天枢运维 Tab（重跑/暂停/调频）+ 五 Tab 导航 + 进度反馈 + 操作日志；**天璇/天玑/玉衡为「建设中」占位**（PlaceholderTab，等后端 P1+） | v1.1.0，1.7.2 起接 A3a 真实 API |
| 线 b 分类图层 P0 | 分类图层地基 + 核设施图层 + Nuclear Watch 面板；news_geo/market_quotes/spacetrack 已上线 | v1.2.0→v1.9.0 |

### 已登记路线图（CRUCIX_UPGRADE §4.2，P1/P2 未实现）
- P1：chokepoints/regions/RegionTabs/SignalStream/StatusBar KPI + **newsGeo.ts（新闻坐标→RiskPoint，后端须先补坐标）** + conflictData（冲突图层）
- P2：LayerTree/pointCluster + 7 类图层（air/thermal/maritime/space/health/osint/sdr）+ MarketTicker/RiskGauge/NewsTicker 底部信息带

### 卡点（08-06 记，08-10 复核）
- 剩余 P2 图层待天枢 feed（空域/热异常/海上/太空/卫生/SDR）——**SDR 今天已补**（fetch_kiwisdr.py + sdr_summary.json）
- **GSCPI 待天枢补 —— 今天已补**（fetch_gscpi.py，GSCPI.csv 尾行 0.805）
- **news_geo 坐标（P3-A NER）未落地 → 新闻/事件地图空渲染**（用户点名）

---

## 二、用户需求 × 已有规划映射

| 用户点 | 已有规划？ | 结论 |
|--------|-----------|------|
| 报告没进开阳 | **无**（Wave/P1/P2 均无报告模块） | **全新需求**，新建 ReportsPanel |
| 控制台只有天枢拉取 | 有（线 a P0 已交付，天璇/天玑/玉衡是有意识占位"等后端 P1+"） | 属 Wave 2 后续"写侧受控指令协议"，大工程，后置 |
| 信息源同步 | 部分（P2 图层路线图覆盖 air/thermal/sdr 等；FCI/风险信号面板未在路线图） | 补 FCI/GSCPI + 风险信号 feed 面板 |
| 新闻/事件地图 | 有（P1 newsGeo.ts + news_geo feed 已注册） | **卡在 NER（P3-A）**，推进即可 |

---

## 三、补全三批规划

### 第一批：信息展示补全（低风险，前端为主，推荐先做）
| 任务 | 内容 | 依赖 |
|------|------|------|
| R-1 ReportsPanel | 报告模块（**全新**）：按类型分组列表（宏观分析/月度简报/假设推演/演化仿真/预测追踪），markdown 渲染 + 最新置顶；数据源 = 天枢生成 reports_index.json（morning 链路扫描分析报告/仿真报告目录）+ nginx/只读挂载暴露报告文件 | 天枢加 reports_index 生成（小） |
| R-2 macro_dashboard 处置 | 停 20:30 dashboard job（用户确认没人看）；预测追踪数据若有人用并入 R-1 | scheduler 一行 |
| R-3 FCI/GSCPI feed | 开阳登记 fci_latest + GSCPI feed（经济面板扩展或新面板） | 无（数据已就绪） |
| R-4 风险信号面板 | climate_signals/disaster_signals/earthquake_risk/energy_risk/hdx_risk/news_risk 入 panelRegistry（事件触发告警柱复用 Wave1 机制） | 无（数据已就绪） |

### 第二批：地图深化（依赖后端 NER）
| 任务 | 内容 | 依赖 |
|------|------|------|
| M-1 news_geo NER（P3-A） | 天枢 news_geo_feed.py 补 spaCy NER，让 GDELT/news 事件有坐标 | 天枢（前端 P1 newsGeo.ts 已登记） |
| M-2 P1 图层 | RegionTabs/chokepoints/regions（CRUCIX_UPGRADE P1 已登记） | M-1 或独立 |
| M-3 conflictData | 冲突事件图层（P1 已登记，ACLED 已放弃 → 用 GDELT 事件替代源） | 天枢 GDELT 事件 feed 就绪 |

### 第三批：控制面扩展（大工程，后端先行）
| 任务 | 内容 | 依赖 |
|------|------|------|
| C-1 写侧控制协议 | 端点/鉴权/权限分级（Wave 2 后续已登记） | 后端控制 API 扩展 |
| C-2 天璇控制 tab | 触发仿真/推演 + 参数（替代 PlaceholderTab） | C-1 + 天璇控制 API |
| C-3 天玑/玉衡控制 tab | 验证触发 / 权重审批 | C-1 + 天玑/玉衡 API |

---

## 四、与 crucix 退场衔接

- 第一批 R-1/R-2 与 crucix 退场正交（报告来自天枢/天璇产物，与 crucix 无关），**可立即启动**
- R-3/R-4 依赖的新 feed（GSCPI/safecast/kiwisdr）今日已上线，数据就绪
- M-1（NER）是天枢工作，可与 crucix 观察窗并行（不冲突）
- 第三批控制面依赖后端 API，建议排在 crucix 退场收尾（WP-4.x）之后

---

## 五、建议执行顺序

1. **第一批（信息展示）**：R-1 报告模块 + R-2 dashboard 停 + R-3/R-4 feed 面板——前端 1-2 个 worker + 天枢 reports_index 小改
2. **M-1 NER**（天枢，与第一批并行）
3. **第二批 P1 图层**（M-2/M-3，依赖 M-1 坐标）
4. **第三批控制面**（crucix 退场收尾后，后端 API 先行）

> 状态记录：2026-08-10 制定。第一批启动前需用户确认范围（全做 or 先报告模块）。
