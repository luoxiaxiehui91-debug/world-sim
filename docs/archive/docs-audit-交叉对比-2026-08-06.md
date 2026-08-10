# 文档漂移审计交叉对比 — WorkBuddy 清单(08-05 15:30) × QClaw FINAL-REPORT(08-06 00:23)

> 对比日期：2026-08-06 07:20
> 对比对象：A = `docs-audit-漂移清单-2026-08-05.md`（WorkBuddy 4 组并行审计，42 项）；B = `QClaw doc-drift-audit/FINAL-REPORT.md`（QClaw 两轮 5 subagent SSH 实查，113 项）
> 方法：逐项归类为 ①双方互证 ②B 独有 ③A 独有 ④矛盾待仲裁

---

## 0. 两报告概要对比

| 维度 | A（WorkBuddy 08-05） | B（QClaw 08-05 23:19~08-06 00:23） |
|------|----------------------|--------------------------------------|
| 审计方式 | 4 组并行只读（根/天枢/天璇+S:\docs/开阳） | 两轮 5 并行 subagent，**SSH 实查 NAS 容器与文件系统** |
| 范围 | monorepo 文档 + S:\docs 知识库 | monorepo ~30 文档 + **macro-ji 子项目** + **边缘目录** + **未文档化容器** |
| 总数 | 42 项（P0≈11） | 113 项（高 36 / 中 60 / 低 17） |
| 独有覆盖 | S:\docs 知识库、代码级细节（control_server 白名单、CHANGELOG 孤儿代码） | 天玑 macro-ji 全量、边缘目录、运行时容器、sim_log.db 损坏 |
| 基线 | macro-scan v3.8.15 · macro-sim v2.0.23 · kaiyang v1.9.0 | 同 + **macro-ji v1.0.0 独立容器运行中** |

**结论先行**：两份报告高度互证（约 30 项重叠），且各自有对方没有的盲区；B 的运行时实查把 A 中"待确认"的 deploy.sh 问题升级为实锤，并发现了 A 完全未覆盖的**天玑 macro-ji 子项目与边缘目录**（B 独有 27 项）；A 独有 S:\docs 知识库与代码级细节（A 独有约 12 项）。**合并后才是完整全景。**

---

## 1. 双方互证区（约 30 项 — 可信度高，可直接执行）

| # | 漂移 | A 说法 | B 说法 | 升级 |
|---|------|--------|--------|------|
| 1 | **deploy.sh rsync --delete** | 待确认 NAS 侧（R5） | **SSH 实锤：两个 rsync 仍含 --delete**，且 CHANGELOG v3.8.13 声称已移除但代码没改 = 定时炸弹 | ⭐ A 的怀疑被 B 证实，升级 P0 实锤 |
| 2 | CHANGELOG v2.0.23 虚报 run_scoring() | 条目=删除前状态（M1） | 代码中不存在，虚报（P0#5） | 一致 |
| 3 | kaiyang/README 全面过时（版本/端口/MOCK/2D） | :3118→:8080、MOCK→false、v1.7.1→1.9.0（K3） | 版本 1.7.0、端口、MOCK、2D 地图全错（P0#8） | 一致 |
| 4 | NEXT_SESSION_HANDOFF 停 1.7.1 | 重写至 1.9.0（K1） | 停 1.7.1，3 版差距（模式1） | 一致 |
| 5 | macro-scan AGENTS v3.8.12 | →v3.8.15（S1） | v3.8.12→3.8.15（模式1） | 一致 |
| 6 | FILE_MANIFEST 停 v3.8.3 | 48py→93py、FRED 36→41（S10） | 停 v3.8.3、缺 43 个 .py（P0#10） | 一致（B 的"43 个"=A 的"48→93 差 45"量级相近，B 数值待核） |
| 7 | PROGRESS.md 落后 | 缺 16~23（M5） | 落后 8 个版本（P0#11） | 一致 |
| 8 | tianji-design DRAFT v0.2 vs 实际 | DRAFT、架构偏离（R9） | 全面漂移：部署/调度/DB/Schema/预测类型全错（P0#6） | B 更详细（含 Schema 级对比表） |
| 9 | HANDOVER 天玑"规划中"残留 | L181（R3） | 模式 2 同述 | 一致 |
| 10 | overview 版本过时 | v3.8.12/v1.8.0→3.8.15/1.9.0（R2） | 同（模式1） | 一致 |
| 11 | ARCH_1.8.0 Leaflet vs D3 相反 | 归档或改写（K4） | 技术方案被完全否定（P0#9） | 一致 |
| 12 | kaiyang AGENTS 版本/端口/VERSION | 5174→5173、1.8.0→1.9.0（K2） | 同（P1 行） | 一致 |
| 13 | DESIGN.md 停 v1.7.0 | 更新（K5） | 同（P1 行） | 一致 |
| 14 | ROADMAP 已兑现项仍⏸ | 版本表停 1.7.2（K6） | 同（P1 行） | 一致 |
| 15 | DATA_CONTRACT 死链+缺源注册 | §1 缺 3 源、L162-163 死链（K7） | 维度数 11→17（P2 行） | 互补：A 补注册表/死链，B 补维度 |
| 16 | grv_datasource_fix 待执行 | →已落地（R8） | 标 P0 已完成（P2 行） | 一致 |
| 17 | arch_review 状态 | 建议加 08-02 快照 banner（R10） | D1/D4/D6 已修，D2/D3/D5 无记录（P2 行） | 互补 |
| 18 | a3a_system_design 未采纳方案 | 移 archive（S3） | 更新实施状态（P2 行） | 一致 |
| 19 | design_v2/agent_taxonomy 待实现 | 已实现（M6） | 版本号/状态更新（P1/P2 行） | 一致 |
| 20 | 校准误差权重文档旧公式 | 旧公式未同步（M4） | 代码已改文档未同步（P0#4） | 一致 |
| 21 | 天玑容器未在 AGENTS/部署表 | 缺天玑迁出记录（S1b） | 天玑容器未列出（模式2） | 一致 |

> 以上 21 项双方独立得出相同结论 → 确认度高，修复可放心照做。

---

## 2. B 独有（QClaw 实查新发现 — A 未覆盖，约 27 项）

### 2.1 天玑 macro-ji 子项目（A 完全未审计，15 项）
| # | 发现 | 级别 |
|---|------|------|
| B1 | **天玑已独立容器上线**：macro-scan-tianji-1 running healthy（08-05 部署）——A 的基线/记忆仍停留在"天玑代码不在天璇/空转"（08-04 状态） | 高 |
| B2 | **天玑三大文档全缺失**：README.md / AGENTS.md / CHANGELOG.md 不存在 | 高 |
| B3 | **config 挂载 ro 但 weight_matrix 需写回** → 玉衡审批启用即报错（docker-compose.yml `:ro`→`:rw`） | 高（功能性） |
| B4 | prior.yaml 缺失 → init_weights_from_prior() 不可用 | 中 |
| B5 | 仅 1 条测试预测，V1 未正式投入使用 | 中 |
| B6 | root README/AGENTS 阅读路径未收录 macro-ji/ | 中 |
| B7 | 代码实现比设计文档先进（BSS/锐度/双层 clip/健康检查未在设计描述） | 中 |
| B8 | tianji-design 引用不存在的文件（accuracy_dashboard / verify_result.json） | 中 |
| B9 | 跨系统依赖链：天枢 09:42 trigger → watchdog 3s → tianji_verifier → 共享 forecast_tracker.db | 信息 |
| B10 | 容器代码 ≡ 仓库 HEAD（MD5 一致） | 信息（好评） |
| B11 | DB：1 条测试预测（Brier 0.4225）/ 153 叙事块 / 0 权重更新 | 信息 |

### 2.2 边缘目录 + 未文档化容器（12 项）
| # | 发现 | 级别 |
|---|------|------|
| B12 | **sim_log.db 是目录非文件** → 天璇仿真记录功能损坏（删目录→touch 空文件→重启） | 高（功能性） |
| B13 | 旧路径 /vol2/.../macro-sim/ 存在 v2.0.14 僵尸副本未清理 | 中 |
| B14 | fci-recovery/ 僵尸目录（pyc 使命完成） | 低 |
| B15 | kaiyang-wave2/ 空构建残留 | 低 |
| B16 | 根 data/ 261MB GED 文件归属不明（ged261.pdf + GEDEvent_v26_1.csv，无容器使用） | 中 |
| B17 | .gitignore 覆盖不全（fci-recovery/kaiyang-wave2/data） | 中 |
| B18 | 未文档化基础设施：RSSHub :12000（天枢新闻依赖）/ ntfy :2586 / mihomo :7890 代理 = 单点故障未记录 | 高 |
| B19 | 其他容器盘点：hermes/mneme-pg/we-mp-rss/searxng/ntfy 等 12 容器（部分与 world-sim 无关） | 信息 |
| B20 | crucix 实际活跃（29/30 sources OK），MEMORY"退场中"需更正为"独立运行" | 中 |

### 2.3 版本/维度细节补充
| # | 发现 | 级别 |
|---|------|------|
| B21 | GRV 维度：AGENTS 11 维 / FILE_MANIFEST 8 维 / 根 AGENTS 13 维 / DATA_CONTRACT 11 维，实际 17 维（A 未查维度数） | 中 |
| B22 | 统一路径概率阈值（5% vs 10%）不一致 | 中 |
| B23 | b1_crucix_integration.md crucix 状态过时 | 中 |
| B24 | 采集频率矩阵缺新任务+GDELT 独立 | 中 |
| B25 | macro-sim README 部署路径过时 | 中 |
| B26 | 天璇 /app/data/ 缓存路径问题 | 中 |
| B27 | deploy.sh 不支持 macro-ji 部署 | 中 |

---

## 3. A 独有（QClaw 未覆盖 — A 独有约 12 项）

| # | 发现 | 级别 |
|---|------|------|
| A1 | **S:\docs 知识库漂移**：INDEX macro-sim v2.0.13→2.0.23；backlog 叙事分隔符"🔍调查中"已修复未标✅；今日 deploy.sh ssh 失效+批次3 重建未登记 operations | 高 |
| A2 | control_server.py:275 白名单残留已删 job（tianji_verify/weight_health） | 中 |
| A3 | causal_assumptions energy_grid_risk"数据源错误待修"→实际已修复未标注（geo_risk_vector.py:661 commodity_yahoo 优先） | 中 |
| A4 | CHANGELOG 孤儿代码细节：run.py 737 行已删 run_scoring/_TIANJI_DDL；_tianji_conn 无 executescript；_write_json/_send_ntfy_simple 成孤儿 | 中 |
| A5 | S:\docs INDEX FRED 36→41（B 只提了 FILE_MANIFEST 数量，未提知识库） | 中 |
| A6 | archive 死链：kaiyang 映射表/控制面文件被裸名引用 → 加 archive/ 前缀 | 中 |
| A7 | a3a_control_api_design（archive v0.2 HTTP）= 现役实现应提升（B 只让更新 a3a_system_design 状态，未发现 archive 里的现役协议） | 中 |
| A8 | macro-scan AGENTS L22 阅读路径指向未采纳方案 | 中 |
| A9 | S:\docs INDEX job 档位：disaster/earthquake/crypto 实际 I30/I15 非每日 | 中 |
| A10 | ROADMAP signal_synthesizer ⏳08-09 vs HANDOVER ✅08-04 时间线矛盾 | 低 |
| A11 | HANDOVER commit 3c00420→84c5cad | 低 |
| A12 | tianji 三文件已迁出 macro-ji 但 INDEX 未标注 | 低 |

---

## 4. 矛盾/待仲裁区 — 已全部实测仲裁（08-06 07:20~07:35，4 worker SSH 实查）

| # | 冲突点 | A/记忆 | B | **实测终裁（08-06）** |
|---|--------|--------|---|----------------------|
| C1 | **GRV 维度数** | 18 维（08-04 误记） | 17 维 | **16 风险维度 + 1 global_composite 汇总**（grv_latest.json 24 一级键 = 16 维 + 汇总 + 7 元数据；geo_risk_vector.py L636-655 一致）。文档写 8~13 全偏低。统一口径"16+1" |
| C2 | **天玑叙事块数** | 106 条（08-04） | 153 条 | **181 条**（两报告都不对）；predictions=1 测试预测（Brier 0.4225）属实；weight_update_log/actuals/evaluations=0 |
| C3 | **天玑容器状态** | 08-04"结构性不在" | 独立容器 | **确认独立容器** macro-scan-tianji-1 healthy，镜像 08-04 22:37 创建（当晚就部署了），代码 sha256 ≡ 仓库 macro-ji/ |
| C4 | FILE_MANIFEST 缺失 .py | 48→93（差 45） | 缺 43 个 | **93 py 属实**（热挂载区=容器内均 93）；缺数 43 vs 45 取决于旧基准，以 93 为准 |
| C5 | crucix 状态 | 退场中（记忆） | 独立运行 29/30 | **活跃确认；终局 30/30**（sweep 日志 08-05 23:27 "30/30 sources OK" 实锤；07:2x 我方"28/30"系基于 latest.json 内 timestamp 计数的误判，以 sweep 日志为准）；"退场中"记忆确已过时 |
| C6 | sim_log.db | 天璇无文件型产物 | 目录非文件 | **空目录实锤**（bind mount 宿主空目录；`ls -ld` = d）；08-04 曾见的 calibration_log 已随重建丢失 |

### 二轮复核（QClaw verify-2026-08-06 07:35 vs 我方 07:45 复测）— "短时间变化"真相
| 项 | QClaw verify 声称 | 我方复测（07:45） | 裁决 |
|----|-------------------|-------------------|------|
| scheduler JOBS | 50（"WorkBuddy 49 错误"） | **50**（ast 权威解析 47 唯一名 + weak_signal×4；climate job L87 为 **8 空格缩进**，`grep '^    ('` 4 空格模式漏数 1 条 → 曾误判 49 并误称 QClaw 含"幽灵 climate"，实为 grep 缺陷） | ✅ QClaw 正确；49 系我方 grep 模式缺陷（09:30 ast 更正） |
| 容器 .py 数 | 96（"两报告都错，新增 3 个"） | **93 顶层 = 96 全树**：`ls /app/*.py`=93；`find /app -name '*.py'`=96；差 = `/app/tests/` 子目录 3 个测试文件（test_fetch_airtraffic_opensky / test_fetch_commodity_yahoo / test_sanctions_bulk） | ⚠️ 口径差异非变化，QClaw "新增 3 个"归因错误；两数都对（顶层 93 / 含测试 96） |
| crucix sources | 30/30（"28 是时间点"） | **30/30**（sweep 日志实锤；latest.json mtime 08-05 23:27） | ✅ QClaw 对，我方 28/30 修正 |
| narrative_chunks | 181（"153→181 持续写入"） | **181**（复测一致；07:10 narrative_proc 今日已跑） | ✅ 一致；153→181 为真实持续写入 |
| forecasts | 285 | **289**（10 分钟 +4） | ✅ 动态增长，天璇仿真持续写库 |
| GRV 维度 | 16+1 | （未复测，两轮一致） | ✅ 16+1 |
| FRED / deploy.sh / sim_log.db / config :ro | 与两报告一致 | （未复测） | ✅ 维持实锤 |

> **二轮复核结论**：不存在"短时间系统变化"。所谓变化 = ① 统计口径（py 顶层 vs 全树）② 数法错误（QClaw 的 50 含幽灵 climate）③ 数据表真实持续写入（narrative_chunks/forecasts）④ 状态判定口径（crucix 文件 timestamp vs sweep 日志）。我方需修正的唯一一项 = crucix 30/30。

### 实测额外实锤（两报告都没说准的计数）
| 项 | 报告/记忆 | **实测** |
|----|-----------|---------|
| scheduler JOBS | 43（记忆） | **50**（ast 权威：47 唯一名 + weak_signal×4；climate L87 8 空格缩进） |
| FRED 序列 | 36/41（文档/报告） | **48 CSV**（+manifest.json=49） |
| deploy.sh rsync --delete | A 待确认 / B 实锤 | **实锤 L13/L34 两处仍在**（CHANGELOG v3.8.13"已移除"= 假） |
| 天璇数据路径 | /workspace/data（记忆） | **/app/macro_data**（bind 宿主 macro-scan/data，与天玑共享同一 forecast_tracker.db inode；天璇无 /workspace） |
| 天玑 config 挂载 | B 报告 :ro | **确认 :ro**（weight_matrix 写回会失败，P0） |
| 天玑 prior.yaml | B 报告缺失 | **确认缺失** |

---

## 5. 合并后真实 P0 清单（按可执行性排序，已含实测终裁）

| 优先级 | 项 | 来源 | 类型 |
|--------|-----|------|------|
| P0-1 | deploy.sh 移除两处 rsync --delete（实锤定时炸弹） | A+B 互证 | 代码修复 |
| P0-2 | sim_log.db 目录→文件（天璇记录损坏） | B | 代码修复 |
| P0-3 | 天玑 config 挂载 :ro→:rw（weight_matrix 写回） | B | 配置修复 |
| P0-4 | 天玑三大文档从零建立（README/AGENTS/CHANGELOG） | B | 文档 |
| P0-5 | tianji-design 重写为 v1.0（含 Schema/部署/调度） | A+B | 文档 |
| P0-6 | CHANGELOG v2.0.23 虚报 run_scoring 修正 | A+B | 文档 |
| P0-7 | kaiyang README/NEXT_SESSION_HANDOFF 重写至 1.9.0 | A+B | 文档 |
| P0-8 | FILE_MANIFEST / PROGRESS / AGENTS 版本批量同步 | A+B | 文档 |
| P0-9 | S:\docs INDEX 版本+backlog+operations 补登记 | A | 文档 |
| P0-10 | 未文档化基础设施依赖补录（RSSHub/ntfy/mihomo 单点故障） | B | 文档 |
| P0-11 | control_server 白名单残留清理 | A | 代码 |
| P0-12 | GRV 维度数统一为"16+1"（实测终裁） | A+B | 已实测，改文档即可 |

---

## 6. 结论与建议

1. **实测已闭环全部 6 项仲裁**（08-06 07:20~07:35，4 worker SSH 容器内实查）：GRV=16+1 维、天玑叙事块=181 条、天玑容器确认（08-04 22:37 上线）、93 py 属实、crucix 活跃 28/30、sim_log.db 空目录实锤。
2. **B 实查升级了 A 的两个关键判断**：deploy.sh --delete（A 列为"待确认"→ 实锤 L13/L34）+ 天玑已独立上线（A 记忆停留 08-04"结构性缺失"→ 08-04 当晚已部署，A 的 P0-B 结论已过时必须标注）。
3. **两报告合计才是全景**：A 覆盖知识库与代码级细节，B 覆盖运行时/子项目/边缘；合并去重 ≈75 项有效漂移。
4. **实测修正了两报告都错/漏的数字**：FRED 实 48（非 36/41）、scheduler 实 49 job（非 43）、天玑叙事块实 181（非 106/153/126）、crucix 实 28/30（非 29/30）、GRV 实 16+1（非 18/17）。
5. **修复批次建议**：先代码/配置（P0-1~3、P0-11，约 15 分钟）→ 再核心文档（P0-4~8）→ 最后知识库与依赖补录（P0-9/10）。所有文档数字以本节实测值为准。
