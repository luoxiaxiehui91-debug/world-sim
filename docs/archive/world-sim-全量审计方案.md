# world-sim 工作空间全量审计方案

> 目标：对 `S:\world-sim`（git 源码正根）+ 其实际部署（NAS 4 容器 + crucix）做全量健康检查，识别三类问题——① 文档未更新/文档间矛盾 ② 实际部署/代码与设计偏离 ③ 残留旧文件/死代码/孤儿未清理。
> 方法：neat-freak 治理收口（六事实面对账 + 当前事实矩阵）。
> 流程：先出本方案 → 用户评审 → 多 agent 多轮走 SOP（只读调查）→ 报告 → 评审后清理。

---

## 0. 背景与已有基线（避免重复劳动）

本 session 已完成的调查（结论已写入 MEMORY.md / 今日流水，本次**仍须用实时证据重验，不盲信记忆**）：

- STATUS.md 全量理解 + 12 处自相矛盾点已列（待本次逐条裁定 resolved / still-open）
- 线上状态核实（容器存活、crucix :3117 仍被 `data_fetcher.py:734` 消费）
- 12 盲点核查（全部用运行时证据闭环）
- SMB 可靠性纠正：早前「SMB 不靠谱」实为路径搞错（仓库内 `S:\world-sim\macro-scan\data` 是死副本，容器实时数据在仓库外 `S:\macro-scan\data`）
- 源码树死副本清理（commit `596780c` 已 push，main upstream 已设）
- 孤儿清单 5 项已核实写入 STATUS.md（玉衡死代码 / 天玑空桩 / crucix 退场未切 / sim_log 零产出 / kaiyang-wave2 副本）

本次范围：`S:\world-sim` 源码树 + NAS 实际部署。**Phase 1–4 纯只读调查，不改动任何文件；清理仅 Phase 6 且需评审确认。**

---

## 1. 六事实面对账框架（neat-freak）

对每面标定状态：`verified-current` / `changed-and-verified` / `pending` / `out-of-scope` / `not-applicable`。

| 事实面 | 要回答的问题 | 本项目的常见证据 |
|--------|--------------|------------------|
| 代码 | 现在真正实现了什么？ | 当前分支、schema、配置、目录结构、scheduler JOBS（ast 计数）、agents.yaml |
| 运行态 | 用户实际得到什么？ | 容器镜像版本、health、真实 API/页面、deploy marker、天玑 DB 行数 |
| 文档 | 人和下游看到的是不是现役答案？ | STATUS.md / SOP.md / 项目导航.md / ADR / OPEN-DECISIONS.md / 各子系统 README |
| 规则 | Agent 约束是否同源可执行无死引用？ | agents.yaml、AGENTS.md、optim_config、hooks、图标/渐变 P0 规则 |
| 记忆 | 快照是否仍准确？ | MEMORY.md / 今日流水 / 工作区 STATUS.md |
| 工作区 | 是否仍有未审计残留？ | .bak、backups/、*_old、*_v2、调试脚本、gitignored 化石、CRLF 幻影 |

核心产物 = **当前事实矩阵**：每条差异写 `source-of-truth → stale-surface → intended-action → verification`。未验证项标 `pending`，不写回权威层。

---

## 2. 调查维度与检查清单（映射到用户三类问题）

### 维度 A — 文档一致性（Docs Integrity）
- A1：STATUS.md 自相矛盾点（上轮 12 处），本次用实时证据逐条裁定 resolved / still-open
- A2：SOP.md / 项目导航.md 与 STATUS.md 口径是否冲突
- A3：ADR 文档是否被后续改动推翻却没登记
- A4：OPEN-DECISIONS.md 未决项是否还能关（上轮钉了 N 未决 + M 已决）
- A5：各子系统 README / 手把手文档（天枢/天璇/开阳）与代码现状是否对得上

### 维度 B — 设计↔实现对齐（Design↔Impl）
- B1：五层架构（天枢→天璇→天玑→玉衡→开阳 + crucix）实际模块结构 vs 架构文档
- B2：17 Agent（agents.yaml A1–A12 + S1–S5）是否都真实运行 / 有 soul / 有产物
- B3：API/契约（geopolitical risk vector、GRV 16 维度、indicators 宽表）实际字段 vs 文档契约
- B4：已知 P0 规则实际遵守情况（单文件 bind mount 断链、时区契约 +08:00、图标/渐变）

### 维度 C — 源码树健康（Source Hygiene）
- C1：死代码/孤儿（上轮 5 项：玉衡 weight_matrix 死代码、天玑空桩、kaiyang-wave2 副本、sim_log 零产出、crucix 退场未切）是否仍存在
- C2：残留旧文件（.bak、backups/、*_old、*_v2、调试脚本、PLAN/TODO）
- C3：git 卫生（未提交改动、CRLF 幻影、分支状态、ignored 化石）
- C4：重复逻辑/多份真相（docker inspect 确认的两条 macro-scan 目录是否还有别的分裂）

### 维度 D — 实际部署核实（Live Deployment，走 ssh nas）
- D1：4 容器 + crucix 存活 / 镜像版本 / health vs 文档宣称
- D2：deploy.sh 实际执行路径 vs 文档（是否 COPY 重建、是否 --delete 误删）
- D3：scheduler JOBS（ast 计数）vs 实际脚本存在性（幽灵 Job 三类）
- D4：crucix :3117 是否仍被 `data_fetcher.py:734` 消费（退场未切验证）

### 维度 E — 跨容器契约一致性（Cross-container Contracts）
- E1：sim_trigger.json 单文件 bind mount 断链 P0（实测是否已部署修复 v2.0.14）
- E2：grv_latest.json / fred_history / news_export 契约字段 vs 消费者
- E3：天玑共享 DB（narrative_chunks / forecasts / predictions）实际行数 vs 文档宣称

---

## 3. 多 Agent SOP 编排

**原则**：只读调查；信息经主理人中转；成员独立产出；逐 Phase 推进；每 Phase 汇总后再进下一 Phase。调查 agent 用 Explore / 通用 agent（只读指令），禁止代写产出。

### Phase 0 — 主理人建基线（我亲自做，不 spawn）
- 读 STATUS.md / SOP.md / 项目导航.md / OPEN-DECISIONS.md / MEMORY.md，提取「文档声称的事实面」作为 stale-surface 种子表。
- 产出：`审计种子表.md`（文档声称 vs 待验证清单）。

### Phase 1 — 静态源码审计（并行 spawn 5 agent，round 1）
| Agent | 负责 | 检查清单 |
|-------|------|----------|
| A-天枢 | macro-scan 核心代码 | B1、B2（天枢部分）、C1、C3、D3 |
| A-天璇 | macro-sim 仿真+校准 | B2（天璇 17 Agent）、C1、D2 |
| A-天玑玉衡 | 验证+权重 | B1、C1（玉衡死代码/天玑空桩）、E3 |
| A-开阳 | kaiyang 前端 | B1、C1（kaiyang-wave2 副本）、C4 |
| A-文档 | 全部 md 交叉 | A1–A5、记忆面 |

每个 agent 回传：发现清单（带证据路径/行号）+ 每条标 `pending` / `confirmed`。

### Phase 2 — 实际部署核实（并行 spawn 3 agent，round 1，走 ssh nas，只读）
| Agent | 负责 | 检查清单 |
|-------|------|----------|
| B-容器 | docker ps / inspect / health | D1、D2、D4 |
| B-契约 | 跨容器文件契约 | E1、E2 |
| B-数据 | 天玑共享 DB + GRV | E3、D4（数据侧） |

只读：`docker exec` / `ssh`，不改动任何运行态。

### Phase 3 — 设计↔实现裁决（主理人 + 按需 spawn 2 agent，round 2 深挖）
- 把 Phase 1/2 发现与 Phase 0 种子表交叉，构建**当前事实矩阵**。
- 对矛盾项做第二轮深挖（如文档说某 Agent 运行、实际没跑 → agent 进容器查日志/产物）。
- 锁定分类：文档滞后（改文档）/ 实现偏离设计（需决策）/ 残留该清（列删除候选）。

### Phase 4 — 汇总报告（我亲自汇编）
- 产出 `全量审计报告-YYYYMMDD.md`：六面状态表 + 当前事实矩阵 + 分级发现（P0/P1/P2）+ 删除候选清单 + 待决项。
- 按 neat-freak 两阶段汇报：影响 / 改动建议 / 待用户决定 / 遗留。

### Phase 5 — 评审（用户）
- 用户看报告，拍板：哪些改文档、哪些改代码、哪些清理、哪些留作待决。

### Phase 6 — 清理执行（评审后，多 agent 或直接）
- 仅执行用户确认项。文档改动落 `S:\world-sim` → commit / push；清理走确认制（先预览删除候选，用户确认后删）。
- 清场后重新审计，补汇报清场结果。

---

## 4. 证据标准（铁律）
- 任何「已运行 / 现役 / 已修复」结论必须用实时证据（docker exec / 容器文件 / API 实测 / git 状态），记忆仅作线索。
- 文件哈希 / 行号 / 容器 ID 作为证据锚点。
- 无法验证 → 标 `pending`，不写回权威文档。

## 5. 产出物
- `审计种子表.md`（Phase 0）
- `全量审计报告-YYYYMMDD.md`（Phase 4，主交付）
- 清理执行记录（Phase 6，若启动）

## 6. 边界与风险
- **只读优先**：Phase 1–4 不改动任何文件；改动仅 Phase 6 且需确认。
- **不扩大权限**：不碰范围外项目、不动密钥、不擅自停服。
- **SMB 红线**：读运行时数据走 `S:\macro-scan\data`，不走 `S:\world-sim\macro-scan\data`（死副本）。
- **ssh** 用 Git 自带 ssh（`C:\Program Files\Git\usr\bin\ssh.exe`），Windows OpenSSH 已坏。
- 已知前置发现直接复用，不重复劳动。

## 7. 轮次与体量预估
- 预计 3 轮（静态 → 部署 → 裁决），每轮并行 3–5 agent。
- 报告体量控制在可读范围，超预算 70% 才报读数。
- 清理阶段单列，不混入调查阶段。
