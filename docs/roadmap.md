# ROADMAP（路线图）

> 2026-08-12 从根迁至 `docs/roadmap.md`。产品功能路线图：天璇校准 R4 / crucix 退场 / 开阳补全。
> 迁移/运维类进展（P0 修复、E0-C PG-only、P6 删库等）见 `docs/decisions/` 与 `STATUS.md`。
> 最后更新：2026-09-12（补记 08-18 后产品功能里程碑）

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

## crucix 退场（08-10 论证 → 08-11 实施闭合 → 08-12 全闭环 G0+G1）

| 阶段 | 状态 | 内容 |
|------|:--:|------|
| 论证（round1 四视角 + R2） | ✅ | gscpi 唯一硬依赖 / nuke SafeCast 复刻 / sdr KiwiSDR 接入 / D3 死配置 / news RSS-only（ADR-01~10） |
| 实施（14 commit 闭合至 ab8b1f7） | ✅ | climate 恢复 / gscpi fetcher+调度 / safecast / kiwisdr / 兜底删 / RSS-only / air 删 / G2 防护 / firms 补偿重试 / 时区修复 |
| 观察窗 | ✅ | **G0 判 08-12 PASS / G1 判 08-12 已停容器**（gscpi 05:32 双轨 5 天）；news_geo 48h 判定 08-13（自动化） |
| WP-2.1b/2.2 | 🟡 部分 | gscpi 切换 ✅（D1，NY Fed CSV 唯一源）；nuke 改读 `_safecast.nuke` 未做（下游零消费暂挂） |
| WP-3.1/3.2 | 🟡 部分 | D3 死配置已删（D1）；`_crucix` 残留保留 gscpi.value 契约（有意保留，未整体清） |
| WP-4.x | ✅ | crucix 容器停用（G1 08-12 `docker stop crucix-crucix-1` → Exited 137） |

## 开阳补全（08-10 规划 → 08-11 实施，v1.9.0→v1.10.8）

| 批 | 内容 | 状态 |
|----|------|:--:|
| 第一批：报告中心 / FCI+GSCPI / 风险面板 / dashboard 停 / news_export I15 | ✅ | 45 份报告双触发、6 风险 feed、FCI 日频+参考带 |
| M-1：news_geo 事件图层（路线 A：GDELT jsonl 派生） | ✅ | 137B→527 事件，CAMEO event_code，XSS 双保险；验收观察窗中（08-13 48h 判定） |
| 视觉系列：crucix 化 / 缩放半补偿 / 事件弹框 / 同新闻合并 / Top-80 降噪 / **同地点聚合** | ✅ | v1.10.1~1.10.8，628→208 点一城一点 |
| 第二批：地图深化（M-2 chokepoints / M-3 conflict 层） | 🔲 | M-3 conflict 已随 M-1 附带；M-2 待排 |
| 航班走廊线（air 图层 B 完整版） | 🔲 待拍板 | 天枢区域级航班统计 + 开阳区域走廊线 |
| 第三批：控制面（天璇/天玑/玉衡 tab） | 🟡 进行中 | **天璇 Tab 只读版 ✅（v1.11.29）+ 天玑 Tab 只读版 ✅（v1.11.31）+ 人工验证界面化 ✅（v1.11.32）**；玉衡 tab 待权重数据（verify_auto 每月 1 日） |

## 天璇模型线（08-17/18 启动，v2.0.41）

| 项 | 状态 | 内容 |
|----|:--:|------|
| soul 政权分片（`regimes:` 时间片） | ✅ `b6914799` | 校准期按历史月切换"当时政权风格"；5 主权红线阈值按 GRV 实测分布校准 |
| 政权更迭引擎（`core/governance.py`） | ✅ `46382625` | 民主换届 / 长期执政继承 / 政变内生事件；`--as-of` 情景开关 `1bdc5ccb` |
| 逆周期力量 A13 长线资金 | ✅ | 普通模式首现双路径分叉（sentiment std 0.275） |
| 日韩主权 S6/S7 | ✅ `169d2967` | 准一党制 vs 单任期强制轮替——政权光谱两端 |
| 预测描述清晰化 | ✅ `10fdf202` | `_ACTION_CRITERIA` 30+ 动作现实判据 + 路径 GRV 上下文 |
| 人工验证渠道（开阳界面 + CLI） | ✅ `defc5e31`/`8a69868b` | 天玑 Tab 点选 [发生/部分/未发生] |
| 自动验证 L1/L2（`verify_geo_auto.py`） | ✅ `0ced51c9`+`4d22e6e2` | L1 FRED 判定器 + L2 新闻关键词（只做发生确认）；2027-02 首轮触发 |
| **新增角色规划**：印度/东南亚/拉美主权（S8+） | 🔲 远期 | 核心 5+2 稳定后按需扩；接口已预留（soul + agents.yaml + 映射 4 处） |
| 政权更迭可视化接入开阳报告面板 | ✅ `9240d8f1` | 政权更迭事件卡片（报告面板 + 天璇 Tab） |

## 08-18 后产品功能里程碑（补记于 2026-09-12）

> 只记产品能力里程碑；运维/开源/CI 类进展见 `docs/decisions/` 与 `operations/CHG-*`（本文件不复制版本流水）。

| 日期 | 里程碑 | 指针 |
|---|---|---|
| 08-14 | **GDELT scale 校准器落地**：天玑 `tianji_calibrator` 9 维 P95 反推原始计数 + tone_base + hotspot_p95；`geo_risk_vector` / `scan_weak_signals` 统一读 `gdelt_calib.json`；天玑 verifier 每日顺带触发（09-12 实测 v2、样本 568） | commit `cf095a5` |
| 09-08 | **日债 10Y 接入 MOF 日频源**（`fetch_mof_jgb` current+all 双源并集）：滞后 99 天 → 1 天 | v3.8.39 / CHG-20260908T203337 |
| 09-08 | **宇宙监视可信度**：spacetrack 登录校验（看响应体）+ 失败态 + limit 截断修复（total_active 30000→35048） | v3.8.38 / CHG-20260908T192626 |
| 09-12 | **观测层非 root 可移植**：`fetcher_base` 日志目录可配置（`MACRO_SCAN_LOG_DIR`）+ 不可写回退 + WARNING 留痕 | v3.8.52 / commit `61433e9` |
