# ROADMAP

> 工作区摘要版（2026-08-10，08-11 更新）：repo 权威完整版见 `/vol2/1000/software/world-sim/ROADMAP.md`（时间门控任务/迁移状态/天玑路线图全量）。本文件为 R4 系列 + crucix 退场 + 开阳补全的摘要，状态与 repo 版同步。
> 最后更新：2026-08-11

## Sprint-0 已完成

| 模块 | 产出 |
|------|------|
| Probit 止血线 | 13.92%，调度 05:40 |
| FCI | fci-1.1 双轨 PCA，vs NFCI +0.828 |
| FIRMS 直连 | 替代 crucix 火点，调度 09:08 |
| 采集频率矩阵 | 24 源审核，地震 I15/灾害 I30/加密 I15 |
| GDELT geo feed | T01 设计→T04 聚合，197 clusters / 643 events |
| FT/BBC 路由 | fetch_rss_news.py v1.1 |
| A1 日档回填 | RetryOnMissingMixin + world_macro 试点 |
| I1 Pydantic | contracts.py |

## 天璇校准引擎 R4 系列（08-07→08-10，已结案）

| 批次 | 状态 | 版本 |
|------|:--:|------|
| R4a-e | 归因/方向闸/豁免五轮迭代 | ✅ | — |
| R4f | 三案否决 | ✅ | — |
| R4g | 归因修正 + 冷却证伪回滚 | ✅ | v2.0.37 |
| R4h ③ sentiment 写者 | 已验收 | ✅ | v2.0.38 |
| R4h ② vix 豁免治理 | 已验收 | ✅ | v2.0.39 |
| R4h ① ease_ok 方向闸 | **收编 EASE 治理** | ✅ | v2.0.40 |
| silence 治理（credit 回池/p̂/S2） | 挂起待立项 | 🔲 | — |

## crucix 退场（08-10 论证 → 08-11 实施闭合，观察窗中）

| 阶段 | 状态 | 内容 |
|------|:--:|------|
| 论证（round1 四视角 + R2） | ✅ | gscpi 唯一硬依赖 / nuke SafeCast 复刻 / sdr KiwiSDR 接入 / D3 死配置 / news RSS-only（ADR-01~10） |
| 实施（14 commit 闭合至 ab8b1f7） | ✅ | climate 恢复 / gscpi fetcher+调度 / safecast / kiwisdr / 兜底删 / RSS-only / air 删 / G2 防护 / firms 补偿重试 / 时区修复 |
| 观察窗 | 🔄 | **G0 判 08-12 / G1 判 08-15**（gscpi 05:32 双轨 5 天）；news_geo 48h 判定 08-13（自动化） |
| WP-2.1b/2.2 | 🔲 | gscpi 切换 + nuke 改读 `_safecast.nuke`（G1 后） |
| WP-3.1/3.2 | 🔲 | D3 映射删 + `_crucix` 残留整体清（门禁后） |
| WP-4.x | 🔲 | crucix 容器停用（devops A/B/C/D，P3 后） |

## 开阳补全（08-10 规划 → 08-11 实施，v1.9.0→v1.10.8）

| 批 | 内容 | 状态 |
|----|------|:--:|
| 第一批：报告中心 / FCI+GSCPI / 风险面板 / dashboard 停 / news_export I15 | ✅ | 45 份报告双触发、6 风险 feed、FCI 日频+参考带 |
| M-1：news_geo 事件图层（路线 A：GDELT jsonl 派生） | ✅ | 137B→527 事件，CAMEO event_code，XSS 双保险；验收观察窗中（08-13 48h 判定） |
| 视觉系列：crucix 化 / 缩放半补偿 / 事件弹框 / 同新闻合并 / Top-80 降噪 / **同地点聚合** | ✅ | v1.10.1~1.10.8，628→208 点一城一点 |
| 第二批：地图深化（M-2 chokepoints / M-3 conflict 层） | 🔲 | M-3 conflict 已随 M-1 附带；M-2 待排 |
| 航班走廊线（air 图层 B 完整版） | 🔲 待拍板 | 天枢区域级航班统计 + 开阳区域走廊线 |
| 第三批：控制面（天璇/天玑/玉衡 tab） | 🔲 | 后端控制 API 扩展，crucix 退场后 |

## 待做

| # | 任务 | 状态 |
|---|------|:--:|
| 1 | **silence 治理**（credit 回池 / p̂ 过 0.55 / S2≤0.60；seed123 残余弱项） | 🔲 |
| 2 | news_geo 浏览器复核 17 项（主理人，清单见 arg-map-qa-acceptance） | ⏳ |
| 3 | FRED 上游停更根因（BAA10Y/DTWEXBGS） | 🔍 |
| 4 | 天璇 sim_log.db 仿真记录修复（P0） | 🔴 |
| 5 | 时区 OPEN 3 条（news.db 展示层 / grv-history 边界 / 纯日期键） | 🔲 |
| 6 | 航班走廊线（air 图层）拍板 + 排期 | 🔲 |

## 延后

- 天璇预测引擎（本 Sprint 不建，未来整体重做）
- 天玑/玉衡（天玑已上线 healthy，权重矩阵/审批待深化）
- 开阳第三批控制面（天璇/天玑/玉衡 tab，crucix 退场收尾后）
