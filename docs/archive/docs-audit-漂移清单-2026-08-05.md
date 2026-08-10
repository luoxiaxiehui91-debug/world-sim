# world-sim 文档漂移统一清单（4 组审计合并）

> 审计日期：2026-08-05｜审计组：root(仓库根) / scan(天枢 macro-scan) / sim-kb(天璇 macro-sim + S:\docs) / kaiyang(开阳)
> 真源依据：scheduler.py JOBS / 核心代码 93 py / macro-sim 运行态 / kaiyang src+nginx
> 已确认无漂移：AGENTS.md 根规则、macro-scan CLAUDE.md、scenario_wiki（运行时产物正常）、archive/ 历史档案保留合理

---

## 1. 根文档（world-sim 仓库根）— 10 项

### P0（5）
| # | 文件 | 过时说法 | 现役事实 | 动作 |
|---|------|----------|----------|------|
| R1 | README L38/L15 | kaiyang MOCK_ENABLED=true；v1.7.1 | A3a 已接入，MOCK=false；v1.9.0 | 改 |
| R2 | overview L3/22/34/44 | v3.8.12 / v1.8.0 / 08-04；天玑"规划中/DRAFT" | v3.8.15 / v1.9.0 / 08-05；天玑已独立容器上线 | 改 |
| R3 | HANDOVER L181 | 天玑（规划中）残留 | 运行中 | 改 |
| R3b | HANDOVER L16 | commit 3c00420 | 84c5cad | 改 |
| R4 | ROADMAP L19/L36 | narrative_chunks "3行" | 126 条（目标≥50 已达成，标✅） | 改 |
| R4b | ROADMAP L17/L112 | signal_synthesizer ⏳08-09 与 HANDOVER✅(08-04) 矛盾 | 统一时间线 | 改 |
| R4c | ROADMAP L98 | P0 GRV 源修复 | WTI/NG/fetch_fx 已落地（代码核实），仅剩 BDI | 改 |
| R5 | deploy.sh L13/L34 | HEAD 仍含 rsync --delete | 与"已去 --delete"矛盾 | **需确认 NAS 侧是否同步** |

### P1（4）
| # | 文件 | 过时说法 | 现役事实 | 动作 |
|---|------|----------|----------|------|
| R6 | HANDOVER L124/L131-137 | 死引用 nas-deploy-prompt.md（已移 archive-v3.8.6）；NAS 清单仍 v3.8.6/补端口 | 更新引用+清单 | 改 |
| R7 | ROADMAP L100/L114 | P95 校准待办；慢变量未接入 | v3.8.11 运行时动态化取代；v2.0.22 已✅ | 改 |
| R8 | grv_datasource_fix | 状态"待执行" | P0 全落地；§4/§5 表过时 | 改 |
| R9 | tianji-design | 仍 DRAFT；"无需新容器"设计 vs 独立容器实现偏离；verification.db vs prediction_ledger.db 不一致 | 更新状态+注记差异 | 改 |

### P2（1）
| # | 文件 | 说明 | 动作 |
|---|------|------|------|
| R10 | arch_review | 建议加"08-02 时点快照"banner（11维 vs 现役13维注记），决策内容保留 | 加注 |

---

## 2. macro-scan（天枢）— 13 项

### P0（4）
| # | 文件 | 过时说法 | 现役事实 | 动作 |
|---|------|----------|----------|------|
| S1 | AGENTS.md L7-8 | v3.8.12(08-04) | VERSION=v3.8.15 | 更新版本+08-04/05 变更 |
| S1b | AGENTS.md L187-94 | 无 :8900/control_server、无天玑迁出 | control_server.py:8900 已上线；tianji 三内核迁 macro-ji | 补部署表 |
| S2 | AGENTS.md L22 | 阅读路径指 a3a_system_design 为"现役设计" | 该文档为**未采纳**的文件投递方案 | 换指 archive v0.2 |
| S3 | a3a_system_design.md L13-24 | "文件投递替代 HTTP"（现役位置） | 实现为 HTTP REST :8900；task_state/command_handler/jobs.json 未建 | **移 archive + 标注反案** |
| S3b | archive/a3a_control_api_design.md | v0.2 HTTP 写侧协议（archive） | = 现役实现（契约/白名单/健康探测） | **提升为现役文档** |
| S4 | control_server.py L275 | 白名单含 tianji_verify/weight_health | job 已删 | 清白名单残留 |

### P1（6）
| # | 文件 | 过时说法 | 现役事实 | 动作 |
|---|------|----------|----------|------|
| S5 | INDEX.md L21-59 | job 表缺 11 新 job（compute_fci 0535/fred_freshness 0540/compute_probit/tianji_trigger 0942/firms 0908/narrative_proc 0710/defense_rss 0712/news_geo_feed 0715/slow_vars 0935/spacetrack 0615/market_quotes I15） | scheduler 已有 | 跑 gen_docs 刷新 |
| S6 | INDEX.md L21/30/32/33 | disaster 05:25、earthquake 06:06、crypto 06:00、crypto_extra 06:12 = 每日 | 实际均 I30/I15 事件档 | 改档位 |
| S7 | INDEX.md L111-15 | tianji_db/verifier/weight_matrix 在列 | 已迁出 macro-ji（文件残留） | 标注迁出 |
| S8 | INDEX.md L67 | FRED 36 序列 | 实际 41 | 改数 |
| S9 | causal_assumptions.md L164-68 | energy_grid_risk"数据源错误待修" | geo_risk_vector.py:661 已优先 commodity_yahoo 能源价（NG2-8/WTI50-110） | 改标已修复 |
| S10 | FILE_MANIFEST/README L47/23 | v3.8.3、48 py、FRED 29/36 | 93 py、FRED 41；缺 compute_fci/fred_freshness/write_tianji_trigger/news_geo_feed/market_quotes/sipri 条目 | 刷新 |

### P2（2）
| # | 文件 | 说明 | 动作 |
|---|------|------|------|
| S11 | archive/a2_ged_etl_design.md L15/57 | GED=全球经济数据库、FRED 48 series | etl_ged.py 实为 UCDP 冲突数据；FRED 实 41 | 标注命名冲突 |
| S12 | archive/fetch_gdelt_geo_design L32 | news_geo.json | 实际 news_geo.jsonl + clusters | 微校正 |

---

## 3. macro-sim（天璇）+ S:\docs 知识库 — 8 项

### P0（2）
| # | 文件 | 过时说法 | 现役事实 | 动作 |
|---|------|----------|----------|------|
| M1 | macro-sim CHANGELOG.md L6-20 | v2.0.23 条目写"新增 run_scoring()+Brier 接线" | run.py 737 行已删 run_scoring/_TIANJI_DDL；_tianji_conn 无 executescript（_write_json/_send_ntfy_simple 成孤儿代码）｜★v2.0.23 即 08-04 那次，条目描述的是批次3 删除前状态 | **改写条目或补登删除** |
| M2 | S:\docs\INDEX.md 版本行 | macro-sim v2.0.13/07-28 | 实 v2.0.23/08-04 | 更新（活跃3问题+ADR9 一致✓） |

### P1（6）
| # | 文件 | 过时说法 | 现役事实 | 动作 |
|---|------|----------|----------|------|
| M3 | macro-sim AGENTS.md L12/L96/L141 | "run_scoring() 接线"、deploy.sh 可用、macro_data:ro | 已删；ssh 密码失败需手动 docker build；实 rw | 改 |
| M4 | 人类说明文档 L31/L269 | 旧误差权重、平滑/误差趋势列未实施 | v2.0.20 已改内生权重、v2.0.10 已完成 | 改 |
| M5 | docs/PROGRESS.md 头部 | v2.0.15、版本表止 15 | 缺 16~23 | 补 |
| M6 | design_v2.md/agent_taxonomy.md | "待实现"、v2.0.17 未落地 | 已实现；Sprint1-2 已落地 | 改状态 |
| M7 | S:\docs backlog/world-deduction.md | 叙事分隔符"🔍调查中" | 已修复 | 改✅ |
| M8 | 今日 operations | deploy.sh ssh 失效 + 批次3 重建未登记（仅 scan 侧 6 件） | 补登记 | 补 |

---

## 4. kaiyang（开阳）— 11 项

### P0（3）
| # | 文件 | 过时说法 | 现役事实 | 动作 |
|---|------|----------|----------|------|
| K1 | NEXT_SESSION_HANDOFF.md | 全文停 1.7.1：§3/§5 版本与开场话术 1.7.0、§4.1"等后端 feed"（market_quotes/news_geo/fred manifest 均已上线）、§7.4 测试基线 | 1.9.0 功能全部落盘 | **重写至 1.9.0** |
| K2 | AGENTS.md | v1.8.0→1.9.0（L7）；"下一里程碑 1.9.0 可拖拽"过期（1.9.0=实时化，拖拽 1.7 已实现）；端口 5174→实 5173；VERSION 1.7.2→1.9.0；L79 A3a 仍写"文件投递" | 改 |
| K3 | README.md | :3118→:8080；1.7.0/297 测试→1.9.0；MOCK_ENABLED=true→false | 改 |

### P1（8）
| # | 文件 | 过时说法 | 现役事实 | 动作 |
|---|------|----------|----------|------|
| K4 | ARCH_1.8.0.md/PRD_1.8.0.md | 标题 1.7.0 vs 文件名 1.8.0；"已规划尚未实现" | Leaflet 线已废弃（1.8.0 改 D3 geoNaturalEarth1）；react-grid-layout 已实现 | 归档或改写 |
| K5 | DESIGN.md | 停 v1.7.0/MOCK=true/:3118/进度 1.6.0 | 更新 |
| K6 | ROADMAP.md | 版本表停 1.7.2；2D-D3、market_quotes 面板、FRED manifest、控制面 REST 均已兑现仍列⏸；"REST≠文件投递"已解决 | 更新 |
| K7 | DATA_CONTRACT.md | §1 注册表缺 news_geo/market_quotes/spacetrack；§2.2 news.updated 已必现；§2.7 仍"1.0 草案"（news_geo_feed 已上线 articles 结构，adapter 兼容）；§2.6.5 ⑩⑬⑪ 已兑现；L162-163 死链（映射表文件已入 archive/） | 更新+摘除草案+修链 |
| K8 | system_design.md L531 | 默认 API localhost:8900 | 实 192.168.31.108:8900 | 改 |
| K9 | A3a-控制API文档 | §0/§1 已标 REST，但 §2-6 命令信封仍为文件投递协议未标"未采纳"；文尾 v1.0 未 bump | 标注+补版本 | 改 |
| K10 | docs/README 索引 | 停 1.7.0；缺 A3a/ARCH_1.8.0/PRD_1.8.0 条目；L23-41 引 archive 文件无前缀（死链） | 补条目+修链 |
| K11 | DECISION_MATRIX.md | D5"不解锁Leaflet"与已装依赖矛盾；D2-D5 长期"待拍板"；L48 死链 | 改 |

---

## 5. 交叉/全局问题

| # | 问题 | 建议动作 |
|---|------|----------|
| X1 | archive 死链：kaiyang 映射表询问/回复、控制面询问/回复 仅因归置 archive 被多文档裸名引用 | 统一加 archive/ 前缀 或 保留副本 |
| X2 | deploy.sh rsync --delete：根仓库 HEAD 与"已去 --delete"事实矛盾 | **先确认 NAS 侧实际内容再动**（涉及部署脚本，须经 lead 受控） |

---

## 修复计划（建议分批）

| 批次 | 范围 | 内容 |
|------|------|------|
| **P0 批** | 版本/状态类 | R1-R5、S1-S4、M1-M2、K1-K3（README×2、overview、HANDOVER、ROADMAP、AGENTS×3、NEXT_SESSION_HANDOFF 重写、CHANGELOG 改写、S:\docs INDEX） |
| **P1 批** | 文档细化 | R6-R9、S5-S10、M3-M8、K4-K11（INDEX 刷新/档位/FILE_MANIFEST/DATA_CONTRACT/DESIGN/ROADMAP-kaiyang/A3a 标注/死链） |
| **归档批** | 文档归置 | S3 反案移 archive；S3b v0.2 提升现役；K4 ARCH/PRD_1.8.0 归档或改写；R10 快照 banner |
| **死链批** | 交叉修复 | X1 引用加前缀 |
| **需确认** | 部署脚本 | X2 deploy.sh NAS 侧同步确认（lead 受控） |

> 备注：所有"改"动作均以真源（代码/运行态）为准；文档修订后无需构建/重启（纯文档变更）。
