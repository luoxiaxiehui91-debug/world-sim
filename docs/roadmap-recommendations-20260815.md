# world-sim 未来规划建议（Track B）

- **对象**：`S:\world-sim`（北斗七星：天枢 macro-scan / 天璇 macro-sim / 开阳 kaiyang / 天玑 macro-ji + 玉衡 / 数据层 PG）
- **日期**：2026-08-15
- **方式**：多 Agent 多轮论证 —— 4 个不同立场独立提案（稳定性优先 / 能力扩展优先 / 数据科学闭环优先 / 运维单人可维护性优先），每组 5 提案 → 对抗式批评 judge 逐条评审（可行性 / ROI / 单人维护成本 / 是否与架构裁定冲突 / 过度设计标记）→ 主 Agent 综合。
- **性质**：**只读产出**。本建议仅新增本文件，未修改任何项目代码/配置/数据。所有引用的 `file:line`、字段名、函数名均来自 Track A 审查（`code-review-20260815.md`）与已读文档，未臆造任何对象名。
- **输入**：Track A 79 条发现（Critical 4 / High 22 / Medium 34 / Low 19）+ `docs/arch_review_20260802.md` 裁定 + `docs/tianji-design.md` + §7.3 未上线组件就绪度专节。
- **并发**：论证阶段 Workflow 编排，严格 ≤12 并发（用户约束 ≤15 留余量）。

> ⚠️ **与 Track A 同一条硬约束**：本文件位于会 `git push` 到 GitHub 的仓库内。在 Track A 列出的密钥（GitHub PAT / FRED / LLM / EIA 等）**全部轮换作废之前，请勿推送本仓库**。P0-A（密钥治理）本身就是解除该约束的前置。

---

## 0. 核心判断与优先级一览

**四个独立视角高度收敛于同一结论**：本系统当前的瓶颈**不是"缺能力"，而是"已有能力空转 + 故障静默腐化"**。玉衡的"评分→校准→权重反馈"闭环代码就绪却数月空转，根因是三重锁：① 上游 GRV 每日 06:10 崩溃（C01）令全链吃陈旧地缘数据；② 天璇 `predictions` 表无真实数据（`MIN_TRIGGER_N=8` 从未触达）；③ 健康巡检口径错位，使前两者"数月无人察觉"。因此**任何"扩数据源 / 加 Agent / 落因果公式"在闭环跑通前边际价值≈0**（与 `arch_review_20260802` 附录 A 结论一致），必须门控到后期。

规划总纲：**先止血（可见崩溃 + 主动爆破的安全面）→ 让已有监控名副其实（观测口径纠偏）→ 打通闭环最小可行链路（predictions 落表 + 验证层去污染）→ 迁移收尾与静默失败根治 → 最后才在天玑 V2 / 天枢框架内做真正的科学扩展**。所有建议均**不新增星、不新增容器、不新增独立进程**，与既有裁定（玉衡并入天玑 V2、瑶光/天权永久关闭独立立项）完全同向。

| 优先级 | 建议项 | 关联 Track A | 对齐裁定 | 批评共识 |
|---|---|---|---|---|
| **P0-A** | 密钥一次性轮换 + compose 明文清理（解除 push 封印）| C04·H07·H14·H16·M29·M32 | 铁律5（控制面演示）| 4 视角一致 ENDORSE |
| **P0-B** | C01 GRV 崩溃止血 + `compute_grv` 调用链 fail-loud（先容器复核）| C01·H19 | 天枢 P0=grv 稳定产出 | 稳定性 ENDORSE，无 OE |
| **P0-C** | 观测口径纠偏 + 预测链探针补齐（= arch P0-2，约 2h）| H09·H10·M26 | 瑶光裁定框架内 | 3 视角 ENDORSE P0 |
| **P0-D** | 天璇 `predictions` 真实落表（修正 arch P0-1 判断）| H20*·M31·H22 | arch P0-1（需修正）| 科学 ENDORSE_W_CHANGES |
| **P1-A** | 验证层 Brier/BSS 去污染（门控在 P0-D 之后）| H03·H04·H05·M08·L03 | arch D-系列 | 科学 ENDORSE P1 |
| **P1-B** | 系统性静默失败 → fail-loud + 接线 `set_alert_hook` | H12·M26·M11·M19·H08·H11 | 铁律（不新建系统）| 稳定性 ENDORSE，高 ROI |
| **P1-C** | E0-C 迁移收尾（低风险即时项）| H13·（pg_synced_at 漂移·P6 守卫）| E0-C 收尾 | 2 视角 ENDORSE_W_CHANGES |
| **P1-D** | 运控控制平面深度收敛 + 冻结评估 | C02·C03·H15·H17·H01·H02 | 铁律5 | 运维 ENDORSE_W_CHANGES |
| **P1-E** | `causal_assumptions.md` 补全（= arch P0-3，纯文档 1 天）| §7.3 天权 | arch P0-3 | 低成本前置 |
| **P2** | 闭环验收门 / 玉衡 V2 通数据 / 天权公式落地 / 新数据源 / 新 Agent / 契约 schema 单一化 | 见 §4 | 门控到 D1-D6 关闭后 | 多标记 OE，重度门控 |

> `*` H20 为 **PLAUSIBLE**（非既成事实），执行前须在运行容器内复核部署版本，详见 P0-D。

---

## 1. 多 Agent 论证过程与交叉验证

### 1.1 编排

| 阶段 | 做什么 | Agent / 编排 |
|---|---|---|
| **B1 提案** | 4 个立场各异的提案 agent 独立产出规划（稳定性 / 能力扩展 / 数据科学闭环 / 运维可维护性），每组 5 条，含动机·依赖·风险·工作量粗估·与 roadmap 关系 | 4 并行（分批 ≤12）|
| **B2 对抗批评** | judge 对每条提案独立评审：关联 ID 是否属实、严重度是否匹配、是否与架构裁定冲突、是否过度设计（OE），给 ENDORSE / ENDORSE_WITH_CHANGES / REJECT + 调整后优先级 | pipeline，逐提案 |
| **B3 综合** | 主 Agent 跨视角去重、按收敛度定档、显式关联 Track A 发现、纠正批评发现的事实性偏差 | 主 Agent |

### 1.2 过程中如实修复的一处偏差

- **稳定性视角首轮退化为占位提案**（proposal title="t"、motivation="m" 的空壳"测试"视角）：其对应 judge 已正确判 `REJECT→DROP`。为不静默丢失"稳定性"这一维度，另起专门的 stability-only Workflow（提案→批评）补齐，得到 5 条扎实提案（C01 止血 / 安全止血 / 迁移收尾 / 静默失败 / 观测口径），全部 ENDORSE 且无 OE。本报告 P0/P1 主干即由该补齐轮 + 其余 3 视角交叉支撑。

### 1.3 批评采纳汇总（20 提案）

- **ENDORSE（无条件采纳）7 条**：C01 止血、安全止血、观测口径纠偏（×2 视角）、Brier 去污染、静默失败 fail-loud、预测链探针。
- **ENDORSE_WITH_CHANGES（采纳但降级/收窄）11 条**：predictions 落表（判断修正）、迁移收尾（降 P0→P1）、控制平面收敛（降 P0→P1）、密钥治理（收窄范围）、玉衡 V2 / 天权公式 / 新数据源 / 新 Agent / 反馈前置数据 / 契约 schema（全部门控到 P2）、闭环验收门（收窄）。
- **REJECT（丢弃）1 条**：占位"测试"空壳提案。
- **过度设计（OE=true）标记 6 条**：天权因果公式扩展、新数据源接入、新 Agent 阵容、`prior.yaml`/`gci`/`baseline_snapshot` 预造、全量 schema 治理层、"闭环稳定性护栏"的过度打包 —— 均门控到 P2 并要求先关闭 D1-D6。

---

## 2. P0 —— 止血与解封（先做，互相基本独立可并行）

### P0-A　密钥一次性轮换 + compose 明文清理（解除 push 封印）

- **动机**：Track A C04（`.git/config` 内嵌 live GitHub PAT）+ 多个 tracked `docker-compose.yml`/源码内明文 key，构成**活跃泄露面**且是本仓库能否安全 push 的硬闸。凡对 NAS 共享有读权限者 `cat .git/config` 即得写凭证。
- **关联 Track A**：C04、H07、H14、H16、M29、M32（及散落的 FRED/LLM/EIA key）。
- **内部 ROI 排序**（批评采纳稳定性 judge 建议）：**先密钥后控制面**。PAT（C04）与 tracked 明文 key（H16/H07/M32）最高——任何 NAS 读权限者即得凭证；控制面 LAN 暴露（并入 P1-D）在单人家用 NAS 威胁模型下略低。
- **依赖**：无（最前置）。**必须一次做完**：轮换全部 key + `git history` 重写清除历史泄露，否则残留即失效。
- **风险**：history 重写会改写提交哈希（单人单远程可控）；轮换后需同步更新运行环境的注入方式（`${VAR}` + 单一未 tracked env）。
- **工作量**（粗估，assumption）：0.5–1 天（轮换 + 清理 + history 重写 + 验证 push 前无残留）。
- **对齐**：铁律5（控制面永久 MOCK / 开阳不连真实后端）不受影响；这是纯安全收尾。

### P0-B　C01 GRV 崩溃止血 + `compute_grv` 调用链 fail-loud

- **动机**：C01 是**全系统单一断路点**（GRV→情势检测→叙事→推演触发→前端全链）。5 个模块常量只引用未定义，`geo_risk_vector.py:106`/`:276` 在 `try` 之外、`main():869` 无兜底 → 每日 06:10 `NameError` → `grv_latest.json` 永不更新 → 全链吃陈旧数据。修复本体小、ROI 极高。
- **关联 Track A**：C01（Critical/CONFIRMED，双 skeptic + 主 Agent 源码级复核）；联动 H19（`world_state.py:558` 对 5 核心 GRV 维缺 None 守卫）——修好 C01 后 GRV 降级为 stub/partial 时 `None` 会流入天璇算术再崩，须联动加守卫。
- **⚠️ 强制前置（批评核心判断）**：`arch_review`（08-02 快照）明写"`grv_latest.json` 每日产出稳定"，而 C01（08-15 磁盘源）显示每日崩溃——**两者矛盾，强烈暗示线上镜像与磁盘源码不一致，或崩溃是 08-02 后引入**。因此**必须先在运行容器内复核部署版本**，再决定改法：若容器跑的是旧版（无此 bug），则本项转为"对齐磁盘/镜像 + 加 fail-loud"；若容器确在崩，则为紧急止血。
- **依赖**：容器复核（前置）。**不依赖** P0-A。
- **风险**：低（补常量定义/导入 + 把调用移入 try + 异常保留上一版 grv 并推 ntfy）。
- **工作量**（粗估）：容器复核 0.5 天 + 修复 0.5 天。
- **对齐**：天枢 P0 = "`grv_latest.json` 每日稳定产出"，本项是维护而非新增能力，完全对齐。

### P0-C　观测口径纠偏 + 预测链探针补齐（= arch P0-2，约 2h）

- **动机**：健康巡检**口径错位**是"闭环空转数月无人察觉"的直接原因。`observability.py` 的 `daily_health_push()` 走 **PG schema `tianji.predictions`** 查行数，而天玑实际用 **SQLite `forecast_tracker.db`**（据 `tianji-design.md` 为权威库）→ PG 未同步 schema 时显示 0 触发**误报"数据链断路"**，PG 可用但无新行时又显示健康。`arch_review` 怀疑者原话即指出"数月空转根因正是 predictions 是否有新行从未纳入健康检查"。
- **关联 Track A**：H09（`silent_failure_probe` 对 prediction/forecast 链零覆盖，PLAUSIBLE）、H10（forecast 验证 PG-only 返回 `[]` 看似健康，PLAUSIBLE）、M26（`pg_read` 无法区分 PG 宕机 vs 无数据）。
- **诚实性纠正（批评发现）**：
  - "observability PG/SQLite 口径错位"是 **§7.3 瑶光就绪度专节 + 风险热点记录**，**不是编号发现**；某提案将其硬挂 **M09** 有误 —— M09 实为 `weight_matrix` Herfindahl 集中度因缺 `baseline_snapshot` 恒 no-op，是另一回事。本报告据实标注来源。
  - H10 证据最弱（skeptic2=REJECTED，仅 skeptic1=PLAUSIBLE），执行时以 H09 为主、H10 作次要验证点。
- **依赖**：无强前置；但**权威库选择须认清 E0-C 终态权威库是 PG**——迁移收尾（P1-C）定稿后再固化数据源，避免又指错库。分档告警：天璇 hotfix（P0-D）前保守提示、hotfix 后升 CRIT，防告警疲劳。
- **风险**：极低（只读健康查询改指向 + 加 predictions 行数增量检查）。
- **工作量**：arch_review 已估 **约 2h**（本报告沿用该估）。
- **对齐**：瑶光裁定 `observability.py` 三数字 ntfy = 完整实现、独立立项永久关闭；本项是**修正该实现的口径 bug 使第三个数字（predictions 行数）可信**，完全落在裁定框架内，不新建 SRE 系统。

### P0-D　天璇 `predictions` 真实落表（修正 arch P0-1 的过时判断）

- **动机**：闭环的第二重锁。`predictions` 表仅测试数据、`MIN_TRIGGER_N=8` 从未触达，玉衡权重反馈永远不启动。让天璇每轮推演的预测真实归档，是"从 idle 到产出首个可校准结论"的最小必要一步。
- **关联 Track A**：H20（PLAUSIBLE）、M31（archival uuid4）、H22（sim 侧）。
- **⚠️ 对 arch P0-1 的事实性修正（批评核心）**：`arch_review` P0-1 判断天璇落表"仅遗漏函数调用"。Track A **H20 推翻此判断**——不是简单漏调一个函数，涉及静默存档失败路径。但 **H20 本身为 PLAUSIBLE 非 CONFIRMED**，且属 macro-sim 容器侧，**执行前必须在运行容器内复核**实际存档路径，再确定修法。
- **诚实性纠正**：某提案关联的 **M33 标签有误** —— M33 实为 bifurcation `n_clusters==1` 的 bug，**不是** target_metric 不匹配；真正的 target_metric 对齐问题是 `arch_review` 的 **D12**，落表修复时应一并核对 D12 而非 M33。
- **依赖**：容器复核（前置，与 P0-B 的复核可合并一次进容器）；落表后 P0-C 的第三个数字才有真实增量、P1-A 才有样本。
- **风险**：中（涉及存档路径与目标变量对齐；须原子写避免半截记录，见 P1-B）。
- **工作量**（粗估）：容器复核合并计 + 修复 1–2 天。
- **对齐**：孙 arch P0-1（修正版）；玉衡"数据未通"的直接解锁项，仍在天玑 V2 边界内、不独立成星。

---

## 3. P1 —— 打通与根治（P0 之后，部分可并行）

### P1-A　验证层 Brier/BSS 统计去污染

- **动机**：即使 predictions 落了表，若验证层统计本身会污染 Brier，反馈出的权重就是错的。这是闭环"可信"而非仅"能跑"的保证。
- **关联 Track A**：H03、H04、H05、M08、L03（outcome=0.5 未隔离 / 气候基准应改观测 base-rate / 样本门控对齐）。
- **依赖**：**门控在 P0-D 之后**——predictions 未落表前无样本，做了也无从验证。
- **风险**：中（统计口径修改需与 `tianji-design` 定义逐条对齐）。
- **工作量**（粗估）：2–3 天。
- **对齐**：arch D-系列；天玑 V2 校准正确性前置。

### P1-B　系统性静默失败 → fail-loud + 接线已存在却零 caller 的告警 hook

- **动机**：Track A 三大系统性主题之首（"静默降级/静默失败"）。**最高 ROI 动作 = 接线 `set_alert_hook`**——基础设施已建、全仓零 caller，只差一个 caller 就能让所有失败可感知。
- **关联 Track A**：H12（`set_alert_hook` 全仓零 caller，CONFIRMED）、M26（`pg_read` 无法区分宕机 vs 无数据）、M11（`log_weight_update` 的 `try/except:pass`）、M19（`reason()` 返回占位串）、H08（`fetch_gpr` 非原子清空 CSV）、H11（`predictions_log.json` 非原子写，PLAUSIBLE）、L08。
- **分阶段（批评采纳）**：先接 hook（最高 ROI）→ 原子写复用 `fetcher_base` 现成 `.tmp`+`os.replace` → 最后改 `pg_read` 多消费方契约（风险最大放最后）。须设阈值/去抖防告警噪音。
- **依赖**：H12 接线与 P0-C 协同（告警通道统一）；`pg_read` 契约变更放在 P1-C 迁移收尾定稿后。
- **风险**：低→中（契约变更影响多消费方，故放最后）。
- **工作量**（粗估）：接 hook 0.5 天 + 原子写 1 天 + 契约变更 1 天。
- **对齐**：既有模块健壮性加固，不新建系统，符合瑶光"不新建独立系统"裁定。
- **注**：批评指出 H12 在两个提案（静默失败 / 迁移收尾）中重复出现——**统一归本项 P1-B**，迁移收尾（P1-C）不再计 H12。

### P1-C　E0-C PG-only 迁移收尾（低风险即时项优先）

- **动机**：迁移双轨是建图明确的"当前最大架构复杂度来源"。收尾消除 schema 漂移与新环境部署即崩风险。
- **关联 Track A**：**H13（PG 缺 UNIQUE 约束，CONFIRMED——当前 PG-only 运行下即产生静默重复，是唯一干净匹配且现行有效的隐患）**；风险热点项：`synthesis_log.pg_synced_at` schema 漂移（代码 INSERT 有、DDL 缺）、`macro-ji/tianji_db.py` 缺 P6 守卫可静默复活 SQLite、`WORLDSIM_SQLITE_OFF` 模块加载时固化（热重载失效）、`signal_synthesizer` 无守卫。
- **降级理由（批评采纳，P0→P1）**：`pg_synced_at` 列已靠生产环境**手工 `ALTER TABLE` 加入**，现网实际可跑；只有"新环境执行 DDL"或"P6 删库后"才失败。单人单一生产环境，新环境部署非临近事件，不构成 P0。
- **诚实性纠正**：这 4 个头号项来自 Track A **"数据层风险热点/备注"**（报告称 `pg_synced_at` 为"最高优先级 schema 漂移"、macro-ji 守卫为"第二优先级"），**非编号 C/H/M/L 发现**；H20（macro-sim 侧）/M31（archival uuid4）不属本项，已归 P0-D。
- **依赖**：无强前置；**删双写死路径须放最后**（P0 全稳后），DDL 回写/UNIQUE 约束/P6 守卫可即时做。
- **风险**：低（DDL 补齐、加约束、加守卫均为增量）；删双写为不可逆，延后。
- **工作量**（粗估）：即时项 1 天；双写删除延后单列。
- **对齐**：纯 E0-C 收尾，不碰星职责。

### P1-D　运控控制平面深度收敛 + 冻结/下线评估

- **动机**：C02（`CONTROL_TOKEN` 默认空串 fail-open）+ C03（`0.0.0.0:8900` + CORS `*`）叠加 = 任意可达 8900 的 LAN 主机零凭证 pause/rerun/改调度。P0-A 已轮换凭证，此处收敛控制面本身。
- **关联 Track A**：C02、C03、H15、H17、H01、H02、M27、M28。
- **诚实性纠正**：**C03 与 H17 均指向 `control_server.py:382`（冗余）**，收敛为一处处理。主 Agent 已用"全仓 compose 均未设 `CONTROL_TOKEN`"源码证据推翻 skeptic"内网可信"下调建议，维持 Critical。
- **降级理由（批评采纳，P0→P1）**：单人家用 NAS 威胁模型下，控制面 LAN 暴露比"凭证明文泄露"（P0-A）略低一档；且铁律5 = 控制 API 永久 MOCK、开阳不连真实后端，故 fail-closed + 绑 `127.0.0.1` + 收窄 CORS **不影响前端演示**。可进一步**评估直接冻结/下线该服务**（既然永久 MOCK）。
- **依赖**：P0-A 之后。
- **风险**：低（收窄监听面 + fail-closed 默认）。
- **工作量**（粗估）：0.5–1 天。
- **对齐**：铁律5 正向一致。

### P1-E　`causal_assumptions.md` 补全（= arch P0-3，纯文档）

- **动机**：天权降级为文档，现状"初稿，尚未经天玑校准"。所有混合权重（如 GDELT×0.4 + GPR×0.6）标注 `[经验假设]`，天玑 V2 校准启动前无实证依据。**先把假设写全**是零代码成本的科学前置，也是后续 P2 天权公式落地的输入。
- **关联 Track A**：§7.3 天权就绪度专节。
- **依赖**：无。
- **风险**：无（纯文档）。
- **工作量**：arch P0-3 已估 **约 1 天**。
- **对齐**：arch P0-3；天权不独立立项，仅补文档。

---

## 4. P2 —— 科学扩展（重度门控：D1–D6 关闭前边际价值≈0）

> **统一门控条件**：以下各项**必须**在"闭环跑通"（P0-B/C/D + P1-A 完成，天璇 predictions 稳定落表、Brier 去污染、`MIN_TRIGGER_N` 可触达）**之后**才启动。`arch_review` 附录 A 已明确：D1–D6 未修前，提升数据质量或增加 Agent 的边际价值接近于零。批评对以下多项标记 **OE（过度设计）**，故全部延后。

| P2 项 | 关联 / 门控 | 批评 | 对齐裁定 |
|---|---|---|---|
| **闭环端到端冒烟验收门** | 定义"闭环跑通"的可测门：predictions 落表→验证产出 Brier→权重反馈触发一次 | ENDORSE_W_CHANGES（原提 P1，收窄去 OE）| —— |
| **玉衡 V2 通真实数据** | 门控在验收门之后；双层 clip（±25% 速率 + [0.05,5.0] 绝对）+ 审批队列代码已就绪 | ENDORSE_W_CHANGES | **并入天玑 V2，不独立成星** |
| **天权因果公式落地**（GRV_T/A 双层衰减、social_stress 三成分、middle_east_energy WTI Channel B 等）| 门控到 arch **P2-1（B+A/NOVEL 重写，承重墙 3–5 周）**；输入 = P1-E 补全的假设文档 | OE=true，重度门控 | 作为天枢代码，不独立立项 |
| **接入闲置数据源**（已采集未使用）| D1–D6 未关前边际≈0 | OE=true | 天枢框架内 |
| **扩充 Agent 阵容**（地缘/供应链传导，突破"金融压力模拟器"定位）| 门控到 P2-1 之后 | OE=true，最重门控 | 天璇框架内 |
| **反馈前置数据补齐**（`baseline_snapshot` + `prior.yaml` + `gci` 结构错位 + 审计日志硬化）| 关联 M09（Herfindahl no-op）、`init_weights_from_prior()` 不可用；门控到天玑 V2 解冻 | OE=true（预造） | arch **P2-2（天玑 V1 条件门控）** |
| **跨系统契约 schema 单一化** | 关联 M17（WTI Channel B）等；**收敛到约 4 个真实契约文件**，勿建全量 schema 治理层 | OE=true（过度治理）| —— |

> **注**：`prior.yaml` 在仓库中完全缺失、`slow_variables_weights.gci` 节下 65+ 情景权重挂错读取路径被当默认值忽略——这些是 P2"反馈前置"的具体待办，但**不应在闭环跑通前预造**（预造 = 无验证依据的空转数据），故门控。

---

## 5. Track A 高危发现 → 规划项映射

| Track A 发现 | 严重度 | 规划项 |
|---|---|---|
| C01（GRV 常量未定义崩溃）| Critical | **P0-B** |
| C02（CONTROL_TOKEN fail-open）| Critical | **P1-D** |
| C03（0.0.0.0:8900 + CORS*）| Critical | **P1-D**（与 H17 收敛）|
| C04（.git/config 内嵌 PAT）| Critical | **P0-A** |
| H07/H14/H16/M29/M32（明文 key）| High/Med | **P0-A** |
| H09/H10（探针不覆盖预测链）| High | **P0-C** |
| M26（pg_read 无法区分宕机/无数据）| Med | **P0-C + P1-B** |
| H20/M31/H22（predictions 落表）| High/Med | **P0-D** |
| H03/H04/H05/M08/L03（Brier 污染）| High/Med | **P1-A** |
| H12（set_alert_hook 零 caller）| High | **P1-B** |
| M11/M19/H08/H11/L08（静默失败/非原子写）| High/Med | **P1-B** |
| H13（PG 缺 UNIQUE）| High | **P1-C** |
| H15/H17/H01/H02/M27/M28（控制面）| High/Med | **P1-D** |
| H19（GRV 维 None 守卫）| High | **P0-B**（联动）|
| M09（Herfindahl no-op）| Med | **P2**（反馈前置）|
| M17（WTI Channel B 契约）| Med | **P2**（契约单一化）|

> 未列入的 Medium/Low 多为局部健壮性项，随所属规划项顺带处理或维持记录。

---

## 6. 依赖与时间门控（文字版 DAG）

```
容器复核（一次进容器，服务 P0-B + P0-D）
        │
   ┌────┴─────────────────────────────┐
P0-B GRV 止血                    P0-D predictions 落表
        │                               │
P0-A 密钥轮换（独立，最前，解 push 封印）  │
        │                               │
P0-C 观测口径纠偏（权威库待 P1-C 定稿）    │
        │                               │
        └───────────┬───────────────────┘
                    │
        P1-A Brier 去污染（依赖 P0-D）
        P1-B 静默失败 fail-loud（H12 接线，pg_read 契约放最后）
        P1-C 迁移收尾（即时项先，删双写最后）
        P1-D 控制面收敛（依赖 P0-A）
        P1-E causal_assumptions.md（无依赖，随时）
                    │
        ── 闭环验收门（定义"跑通"）──
                    │
        P2（玉衡 V2 通数据 / 天权公式=门控 P2-1 / 新数据源 / 新 Agent / 反馈前置 / 契约 schema）
```

**关键门控**：① P0-A 是 push 解封前置；② 一次容器复核服务 P0-B/P0-D，因 arch(08-02) 与 Track A(08-15) 对"GRV 是否稳定产出"存在矛盾，复核是所有触碰运行时判断的强制前置；③ P2 全部门控到闭环验收门之后，D1–D6 未关前不铺任何新能力。

---

## 7. 论证过程中纠正的事实性偏差（诚实性专节）

为符合 facts-vs-assumptions 铁律，以下是本轮多 Agent 论证中**批评环节发现、综合环节已修正**的偏差，一并披露：

1. **M33 误挂**：某提案把天璇落表关联到 M33（target_metric 不匹配）——M33 实为 bifurcation `n_clusters==1` 的 bug；真正的 target_metric 问题是 `arch_review` **D12**。已在 P0-D 更正。
2. **M09 误挂**：某提案把"observability PG/SQLite 口径错位"挂到 M09——M09 实为 `weight_matrix` Herfindahl 集中度因缺 `baseline_snapshot` 恒 no-op。口径错位实为 **§7.3 就绪度专节 + 风险热点记录，无独立编号**。已在 P0-C 据实标注。
3. **H20 / M20 为 PLAUSIBLE 非既成事实**：predictions 落表（H20）执行前须容器复核，不能当作确定 bug 直接改。已在 P0-D 标注。
4. **H10 证据最弱**：skeptic2 判 REJECTED，仅 skeptic1 PLAUSIBLE；P0-C 以 H09 为主。
5. **C03 与 H17 冗余**：同指 `control_server.py:382`，P1-D 收敛为一处。
6. **H12 跨提案重复**：静默失败与迁移收尾两提案都含 H12，统一归 P1-B。
7. **迁移收尾 4 头号项非编号发现**：来自"数据层风险热点/备注"，唯一干净的编号匹配是 H13。已在 P1-C 标注来源。

---

*本报告为只读产出，未修改任何项目代码/配置/数据。所有 `file:line`、字段、函数名均来自 Track A（`code-review-20260815.md`）与已读文档；工作量为粗估（assumption），执行前以运行容器实证为准。*
