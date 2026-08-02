# 开阳（kaiyang）文档索引

> 本文件是 `docs/` 的总导航。所有文档已统一收归 `docs/` 目录（项目根不再散落）。
> 文档间以**裸文件名**互相引用（归档区 `docs/archive/` 除外），请勿随意改名或移入其他子文件夹，以免断链。
> 最后整理：2026-08-01（VERSION 1.6.0——§4.5 清扫 + news_geo 读取层骨架 + 决策矩阵）。

---

## 一、设计权威（先读这两份，其余文档都引用它们）

| 文件 | 一句话 | 状态 |
|------|--------|------|
| `DESIGN.md` | 开阳设计总纲：定位/边界/技术栈/Wave 规划/扩展标准/部署/状态/目录，含 §2.1 crucix 复刻进度 + Wave2 双线表 | 持续维护 |
| `DATA_CONTRACT.md` | 数据契约权威标准：feed 文件名/路径/字段/`schema_version`/部署/扩展，含 §2.5 `nuclear_sites.json` + §2.6 后端 feed 状态（已回填转正）+ §2.7 `news_geo.json` 草案 | 持续维护 |
| `DECISION_MATRIX.md` | D2-D5 四条悬而未决决策的对比分析 + 主理人推荐倾向（1.6.0 产出） | 待用户拍板 |

## 二、控制面线（Wave2 右侧抽屉 + 天枢运维 Tab）

| 文件 | 一句话 | 状态 |
|------|--------|------|
| `PRD_CONTROL_PANEL.md` | 控制面 PRD：需求池 / 范围 / 12 接口形状 / P0·P1·P2 分级 | 已交付（P0=T01-T03 已复盘 0 缺陷） |
| `system_design.md` | 控制面架构设计 + 任务分解 T01-T05（零新依赖） | 已交付 |
| `开阳控制面-后端接口需求询问.md` | 发后端的 20 题询问单（确认天枢/天璇等接口形态） | 已发出 |
| `开阳控制面-后端接口需求-回复.md` | 后端回复：天枢 A3a 就绪，天璇/天玑/玉衡延后占位 | 已回填 |

## 三、crucix 复刻线（对标 CRUCIX MONITOR 多图层大屏）

| 文件 | 一句话 | 状态 |
|------|--------|------|
| `CRUCIX_ANALYSIS.md` | 开源 crucix 竞品拆解 + 身份定性（=开源 calesthio/Crucix，开阳 clean-room 复刻对象）+ 升级路线 A/B/C | 已交付 |
| `CRUCIX_LAYER_REQUIREMENTS.md` | 24 项显示需求主表（10 类指标 + 5 类地图符号 + 9 项面板），现状/缺口/补法/优先级/后端依赖五列 | 已交付 |
| `CRUCIX_UPGRADE_DESIGN.md` | P0 架构设计 + 任务分解 T-U01~T-U05（含 3 张 mermaid 图），已锁定 P0 范围 | 已交付（P0 已 GO） |
| `archive/开阳Crucix新闻地理坐标需求-给后端.md` | 给后端的 Crucix 新闻 `lat/lng` 需求 | **已作废**（天枢回填证伪前提：news_export 无坐标新闻；改由新建 GDELT geo feed 承担，见回复件 + §2.6/§2.7） |
| `archive/CRUCIX_BENCHMARK_OPEN_QUESTIONS.md` | 初期待明确清单（8 大类），已被 `CRUCIX_ANALYSIS.md` 回填 | 历史备查（见下方备注） |

## 四、给后端 / 外部团队的询问文档

| 文件 | 一句话 | 状态 |
|------|--------|------|
| `天枢-fetcher×crucix-映射表-询问.md` | 发天枢（macro-scan）的 13 项 feed 三选一勾选表 + crucix 源→天枢 fetcher 反推映射 + 一页纸回填表 | 已发出（2026-08-01） |
| `天枢-fetcher×crucix-映射表-回复.md` | **天枢实查回填**：13 项逐项结论 + 新闻端规划 + P2 排期建议 | **已回填（2026-08-01）** |

## 五、接手 / 会话衔接

| 文件 | 一句话 | 状态 |
|------|--------|------|
| `NEXT_SESSION_HANDOFF.md` | 给下个 session 的 60 秒接手快照：双线进度 / 已完成 / 待办决策 / 开场话术 / 文件指针 / gotcha | 持续维护 |

## 六、图示（被 `CRUCIX_UPGRADE_DESIGN.md` 引用）

- `class-diagram.mermaid` — 分类图层类图
- `sequence-diagram.mermaid` — 主流程 + Nuclear Watch 面板时序图
- `dependency-graph.mermaid` — 任务依赖图

---

## 备注：已归档的冗余文档（不影响运行）

以下两份内容已被后续文档覆盖，已移入 `docs/archive/`（不删内容，仅归档；各引用处路径已同步更新为 `archive/xxx.md`）：

1. `archive/CRUCIX_BENCHMARK_OPEN_QUESTIONS.md` — 初版「待明确清单」，结论已并入 `CRUCIX_ANALYSIS.md`。
2. `archive/开阳Crucix新闻地理坐标需求-给后端.md` — 早期新闻坐标需求，**前提已被天枢回填证伪**（`news_export.json` 实际 0 条带坐标新闻、`source:"Crucix新闻"` 为关键词频率告警非地理文章），**已作废**；地理新闻上图改由新建 GDELT geo feed 承担（见回复件第四节 + `DATA_CONTRACT.md` §2.6/§2.7）。
