# world-sim v1.1 / v2.0.13 评审合成与实施决策备忘（**最终版 v3**）

**主理人：齐活林（Qi）· 交付总监**
**团队：software-worldsim-review（PM 许清楚 / 架构 高见远 / 工程 寇豆码 / QA 严过关）**
**状态：Round 1 四份评审 + Round 2 四项定稿 + Live SSH 真源复核 + `_archive` 五份文档吸收 + 用户四项拍板 + 三探针实测（2026-07-31）**

> **🔴 本轮探针新增一个 P0**：`sim_trigger.json` 跨容器 inode 断链未爆弹 —— 见 §三 P0-NEW 与 §十七 P3。
>
> **📌 时效指针（2026-08-10）**：本文为 07-31 架构评审快照（v1.1/v2.0.13 时代），顶层架构结论（5 主层+2 横切、GED 冻结、ACLED 弃用等）仍然有效。**校准引擎 R4 系列治理（08-07→08-10，v2.0.37→v2.0.40）是架构内迭代，决策记录不在本文**——见 `STATUS.md` R4 系列章节 + `macro-sim/docs/r4g-spec-change-registry.md`（变更 1-8）。R4h ① 于 08-10 结案：收编 ease_ok 方向闸，credit 回池/p̂/S2 挂起转 silence 治理。

---

## v3 相对 v2 的实质变更（先看这里）

| # | v2 结论 | v3 修订 | 依据 |
|---|---------|---------|------|
| 1 | 天璇 `predictions` 是唯一闭环起点，MVT 首发 | **闭环起点改为财经 L1 FCI + L3 probit 先行**；天璇仍是唯一承重墙但不再阻塞首个价值交付 | PM Round1-A / 架构 Round1-C |
| 2 | prior.yaml 被列为 Top1 输入侧问题 | **降级 P2，移出关键路径**——运行路径实读 `grv_weights.yaml`，prior 损坏被自然避开；仅在维护窗口顺手修格式 + 打 tombstone 注记 | `_archive` 问题清单 + 架构 Round1-B 自纠 |
| 3 | GED 列为"待补数据源缺口" | **已落 NAS 资产**（417,968 事件 × 49 列，1989–2025）；且是**年度冻结快照**，只能做回测金标准/B 基线，**禁止当当前信号** | QA 实测 + 架构 Round2-3 |
| 4 | I4 慢变量"08-01 死线紧迫" | **本月已填**（07-30，tech=0.65 / nuke=0.5，带 updated_at），死线已满足；真缺口是 loader 忽略 updated_at | Live SSH 复核 |
| 5 | ACLED 列入推荐补强源 | **彻底剔除**（需 edu/org 邮箱，团队 B5 已判"已放弃"，用户确认接不进） | research/ 信息源手册 + 用户确认 |
| 6 | 三流 = A 天璇 / B 天枢韧性 / C 天玑运营化 | 内涵重定义：**B 流 → "天枢韧性 + 即时价值"**（纳入 L1/L3）；**C 流 → "方法学与验证流"**（纳入 OECD 十步法 + ViEWS 消融 + GED 回测）；**新增 D4 绑定模块为 A 流第一任务** | 架构 Round1-A/D |
| 7 | 契约冻结对象含"修好的 prior.yaml" | 输入侧冻结对象改为 **per-target 绑定 schema（Pydantic）+ grv_weights.yaml（运行时真文件）** | 架构 Round2-2 |

---

## 问题定性（总评）

原方向（砍范围 / 最小闭环 / B+A 重写 / N13）成立，但本质不是"进度问题"而是**校准链完整性问题**：`predictions` 表缺失 → 天玑 Brier / 玉衡审批 / 回写闭环全部空转。

v3 补一层定性：系统同时存在**"死数据"病**——FX/加密/商品/BDI 等库存已采集但无消费引擎。财经 L1/L3 先行既止血校准链空转的信誉损失，又把库存变现。

---

## 一、范围

- 65 目标 → **核心 10 个（进校准）+ 观察名单（不进校准）**。
- 切法 = **可判定性 + 数据地板双约束**（PM Round2）：分辨期短、结果可客观结算、**且源已接且新鲜度达标**。不为地理平衡而平衡。
- **扩展位激活四条件（全满足才开新目标）**：
  1. 源已接且新鲜度达标（数据地板）
  2. 消费引擎就绪（防再造预采集库存 = 防新增死数据）
  3. owner 周耗时有余量
  4. **GED 回测认证欠账未逾期**（见九·限期认证）
- 观察名单 → 核心 10 晋升同规则。

## 二、顺序 / 承重墙

- **天璇 `predictions` 表仍是 MVT 承重墙**（B+A / NOVEL / 写 predictions 全为 0%），承重墙地位不因财经先行而降级。
- **但首个可演示价值不是天璇**：天璇 0% 进度 + 验证周期以月计，拿不出"校准的不确定性"。首演示 = **FCI 日报 + probit 衰退概率卡片**（有外部权威基准可对照，验证周期以天计）。
- 闸门 = 先冻结天枢→天璇接口契约；天璇可用 **mock 慢变量**先跑通。
- ⚠️ **纪要硬性注记**：FCI/probit 是止血不是主线。天璇 B+A / NOVEL / predictions 表进度**须单独周报**，防"演示光环掩盖天璇 0%"。

## 三、优先级总排序（QA Round1-D 修订版）

> QA 关键纠偏：真凶是**静默降级**——`call_llm` 失败 `return ""` → `parse_action` `return "HOLD"` → 蒙特卡洛照跑出"外观正常"的假结果流进天玑污染校准。挂死看得见，假结果看不见。

```
P0 失败可见性  >  P0-NEW sim_trigger inode 断链  >  N13 HTTP 超时  >  I1 Pydantic 契约
   >  record/replay  >  I4 元信息化  >  B 基线回测（+GED 历史标签）  >  vintage(P2)  >  消融(P3)
```

> **🔴 P0-NEW（探针 P3 于 2026-07-31 实测发现，详见 §十七）**：`sim_trigger.json` 采用 **single-file bind mount**，而 scan 侧 `_write_sim_trigger()` 用 `os.replace()` 原子写会**更换 inode** → macro-sim 挂载锁死在旧 inode，**下一次 GRV L3 触发时天璇将永久收不到信号，且完全静默**（scan 照常打印"已写入"、ntfy 照常推送"推演已启动"）。
> 已用隔离容器实验证实（单文件挂载读到 OLD / 目录挂载读到 NEW）。推荐修复 = 改目录挂载（2 行 + 重启）。这是**静默降级病族的第四例，也是唯一跨容器的一例**，故与 P0 同级。

**I1 插到 record/replay 之前的理由（采纳）**：I1 与静默降级是同一病两端——LLM 失败静默 / 数据非法静默；且先立契约再录回放，否则录下来的是未校验样本。成本 ~1h，低于 record/replay。

逐项：
- **P0 失败可见性**：`call_llm` 改返回 `(text, ok, reason)`，禁空串冒充结果；单次运行统计 `llm_fail_rate` + `truncated_rate`，>5% 整份推演打 `degraded=true` 并**拒写天玑**。
- **P0 加 timeout**：OpenAI 客户端层 `timeout=(connect, read)`（弃用 threading+join(600) 自杀式写法）。挂在天璇第一段（纯基线）内做——那里才是重灾区。
- **P0/I1 Pydantic 契约**：见六·输入侧契约。
- **P1 record/replay 夹具**：`temperature=0.4` 无 seed，同输入两次结果不同 → 必须 LLM record/replay 快照，CI 跑 replay 模式。
- **P1 I4 元信息化（紧迫性已修正）**：`manual_scores.json` 本月已填（07-30，带 updated_at），"08-01 死线"已满足。真缺口是 `_load_manual_score` **完全忽略 updated_at**，异常一律 `return default`（nuclear_posture 默认 0.0 = 恰好"稳定"）。改：返回 `{value, source: fresh|stale|neutral, age_days}`；陈旧 >45 天降级；非 fresh 冒泡报告头；降级月天玑单标不混入 Brier。
- **P1 B 基线回测**：历史相似度库覆盖/质量无人验证，B 是垃圾则 A 白调。**GED 1989–2025 提供 n≫8 的历史标签，把它从"不可测"变"可延后测"——GED 落地抬高了 B 基线的优先级价值。**
- **P2 退避/熔断/降级链**：指数退避 + jitter（区分 4xx/5xx/429，4xx 不重试）；连续 N 次失败停轮；Qwen3.5-27B→GLM 备选链，记实际模型到 sim_log。
- **P2 BSS 最小样本闸门**：n≥20 才展示 BSS，否则原始 Brier + "样本不足"。
- **P2 vintage 快照**：**FRED vintage 与 GED 版本快照并成一个机制**（append-only + 三日期），一次设计两处受益。不升 P1——当前没有回测在跑，价值是"将来可回测"而非"今天防错"。
- **P2 prior.yaml（降级）**：维护窗口顺手修格式 + tombstone 注记休眠风险，不占排期。
- **P2 文档 SSOT + 契约冻结**：tianji_db.py 为 SSOT，schema 加版本号；旧文档要么按代码重生成要么删，**禁"留着参考"**。执行形式采用 `_archive` 的"🟢已验证 / 🟡规划未验"标注，作为 **LLM prompt 上下文卫生的强制项**。
- **P3 SMB→git+SSH 开发循环 / 容器重建代理注入 / 影子运行回滚 / 消融**（n<100 用 VIF + 相关矩阵，不提前上 SHAP）。

## 四、架构三风险 → MVT 验收项（不变）

1. **有界调整在线监控**：baseline vs adjusted 分歧度指标。
2. **权重版本化**：玉衡改权重须快照版本，predictions 记 `weight_version`，Brier 按 `schema_version` + `weight_version` 分桶，禁跨版本混算。
3. **B 基线质量**：MVT 前先做一次历史相似度库基线回测（现可用 GED 历史标签）。

## 五、验收门（MVT 必过）

- Brier 平均 ≤ 0.25（暂定，待天玑回测校准后修订），≤0.20 为优秀。
- baseline-vs-adjusted 分歧度在线监控。
- predictions 记 weight_version、Brier 按版本分桶禁混算。
- 双读期同批历史新旧两路 Brier 一致才切流。
- **新增（PM Round2-3）**：天璇首版预测发布后 **4 周内**必须交付 **GED 回测报告**（BSS 对基线、按地区分层）。定位为"发布后限期认证"而非发布前门槛；未通过则**冻结扩展位晋升**（= 扩展位第四否决条件）。

---

## 六、数据契约冻结清单

### 6.1 输出侧 —— predictions（既有，additive-only 冻结）

**现有真实 schema（live tianji_db.py v1.1）**：
```
predictions: id(PK) | scenario_id | type(q/geo) | prediction_target_type(NOT NULL)
  | content | outcome_definition | target_metric | target_direction | target_threshold
  | b_prob(B基线) | b_sample_count | b_max_similarity | llm_adj(A调整量) | final_prob
  | prob_low | prob_high | confidence_tier(HIGH/LOW/VERY_LOW/NOVEL)
  | time_horizon(weekly/monthly/quarterly/yearly) | status(default 'pending')
  | outcome_value | brier_score | brier_skill_score | verified_by
reasoning_trace: id | prediction_id(FK) | agent_id | input_signals(JSON)
  | historical_match | confidence_basis | llm_adjustment | causal_chains(JSON) | reasoning
weight_update_log: id | prediction_id | signal_name | target_type
  | weight_before | weight_after | reason | notes
narrative_chunks: id | source_id | source_type | primary_dimension | secondary_dimension
  | content | token_count | staleness_tau(default 72) | embedding(BLOB)
narrative_density_flags: dimension(PK) | z_score | consumed
```
**须 add（additive-only，全 nullable 或带默认值）**：
- predictions：`target_id` / `run_id` / `weight_version` / `schema_version` / `created_at` / `resolve_by` / `resolved_at` / `outcome`(布尔)
- reasoning_trace：`trace_format_version`
- narrative_chunks：`created_at` / `ts`
- weight_update_log：`approved_by` / `approved_at`
- 命名映射：`baseline_prob`↔`b_prob`、`adjusted_prob`↔`final_prob`
- 冻结原则：已有字段禁改名/改语义/改类型；新增必须 nullable/带默认。

**迁移 expand-contract 三阶段**：双写 → 双读按 schema_version 分流（Brier 分桶）→ 旧预测全 resolve 后下线旧路径。

### 6.2 输出侧 —— indicators 宽表（**工程 Round2-3 定稿，天璇直接复用**）

```sql
indicator_key(text) | as_of(date, 决策时点) | data_vintage(date, 上游数据版次)
  | horizon(text, 如 12M/nowcast) | value(real)
  | ci_low(real, 可空) | ci_high(real, 可空)
  | model_ver(text) | created_at(timestamp, 写入时间)
UNIQUE(indicator_key, as_of, horizon, model_ver, data_vintage)
```
约束：**只 INSERT，不 UPDATE/DELETE**；修正 = 新 `data_vintage` 重发。ci 拆 low/high 两列（比单字段可查询）。
**此即最终版，天璇重写照此写入。** L1/L3 先落地定型此 schema，等于用低风险模块替天璇试错，避免后期返工。

### 6.3 输入侧 —— I1 / D4 绑定契约（架构 Round2-2 裁定：**I1 = D4.0，同一任务两阶段**）

| 阶段 | 回答的问题 | 内容 | 排期 |
|------|-----------|------|------|
| **I1** | "**这份产出形状对不对**" | 记录级 Pydantic 模型、必填字段、时间戳、`schema_version`、加载期 fail-loud | Sprint-0，record/replay **之前** |
| **D4** | "**这个源喂给哪个目标**" | 源→表征→目标 Link、per-target 绑定、registry、跨引用一致性校验 | A 流第一任务 |

**强约束**：D4 必须复用 I1 的 Pydantic 基类与 `schema_version` 字段约定，禁止另起炉灶；I1 不够用走 **expand（加字段）不走重写**。

**D4 粒度（架构 Round2-4 + 工程 Round2-4，两方一致）**：
- **人写层**：`bindings/<target_id>.yaml`，per-target 小文件。理由——热挂载友好（改一个 target 只动一个小文件，秒级生效可单独 review）；git 冲突面小（D4 是未来最高频改动区，单 registry 必成 merge 冲突磁铁）。
- **机器层**：`apply` 期编译 `registry.json`（机器产物、带 content hash、**禁手改**），提供单一真相源与构建期 schema mismatch 报错（Feast 范式）。
- **apply 期三类冲突检测**：同源被多目标引用 / 循环引用 / **孤儿源（有源无消费者——这正是"死数据"的可自动发现形式）**。
- 工程附加：加载器对"目录里存在未被引用的孤儿文件"也 fail-loud，防写了没生效的静默漏挂。
- 不可让步的是"**人写分片、机器聚合、构建期校验**"三段结构；registry 产出格式可让步。
- 反对纯单 registry：会原样复现 prior.yaml 巨型手写矩阵的腐化失败模式。

### 6.4 scan→sim 契约（schema v1.0，顶层带 schema_version）

- `grv_latest.json`：variables[]{id,value,unit,confidence,stale}；stale 超阈值 → sim fallback + 告警，**禁静默用旧值**。
- `fred_history/*.csv`：固定列 date,series_id,value；缺值写 NaN 不留空串，日期 ISO 8601。
- `news_export.json`：chunk_id,ts,source,text,tags[]，单次导出设条数上限。
- `sim_trigger.json`：trigger_type(manual/cron/event)、requested_targets[]、dry_run。
  **v3 新增（架构 Round2-1）**：允许 L1/L3 写 sim_trigger，但**仅以 additive 方式新增 `trigger_reason` 枚举值**（`fci_stress` / `recession_prob`），不改结构、不改字段——落在 expand-contract 的 expand 阶段内，与 additive-only 冻结自洽。degraded 时整份降级且**不写** sim_trigger。
- sim 启动做版本握手，不匹配即拒跑不降级猜测。
- 契约文档从代码/JSON Schema 生成并附 fixture 样例，手写必分叉。

---

## 七、Sprint-0：财经 L1/L3 + GED + I1（**v3 新增主线**）

### 7.1 定位（架构 Round2-1 裁定）

- **形态**：独立 `indicators` 表/文件（`fci_daily`、`recession_prob`）为**唯一真相源**，日报只是它的一个消费者。
- **节奏**：GRV 市场维列**阶段 B**。**否决现在加 GRV 第 12 维**——GRV 尚未过 OECD 外壳（无理论框架 / 无 Cronbach's α / 无 Monte Carlo），此刻加维等于在未治的"任意权重"反模式上再叠一层，且立即触发权重版本化风险项。先让 L1/L3 以独立指标跑满一个观察周期，拿到与 GRV 的相关性/增量证据，再决定"进 GRV"还是"永久单列"（WTM 范式下单列本身是合法终态）。
- **契约含义**：`schema_version` 挂在 indicators 输出文件本身，**不挂 GRV**，GRV 契约零改动。

### 7.2 L3 probit 衰退概率

- **自变量口径（QA Round1-G1，工程 Round2-1 接受）**：必须用 **T10Y3M（DGS10 − DGS3MO）**，与 Estrella-Trubin (2006) 系数 **α = −0.5333 / β = −0.5984** 同源。沿用系统现有 T10Y2Y 套该系数 = **系统性偏**。
- **实测数据地板（工程 SSH 复核）**：`data/fred_history/` 现有 44 个 series，**DGS10 / DGS2 / T10Y2Y 在，无任何 3M 相关**。采集脚本容器内路径 `/app/fetch_fred_history.py`（宿主 `核心代码/fetch_fred_history.py`，热挂载），series 清单是文件内 **L41 `SERIES` tuple 数组**。
- **✅ 探针 P2 实测（2026-07-31）**：FRED API 现场拉取成功 —— `T10Y3M` n=41 最新 **2026-07-29 = 0.84**；`DGS3MO` n=40 最新 **2026-07-28 = 3.90**。交叉校验 `DGS10(4.61) − DGS3MO(3.90) = 0.71`，与 FRED 官方 T10Y3M 同日值一致。**加采无阻碍。**
- **加采成本 ≈ 10 分钟**：SERIES 列表加行 + 跑一次全量回填，走完全相同的 `fetch_and_save` 路径。这**不破"不新增采集器"前提**——采集器 = fetcher 脚本/调度单元，series 只是配置项。
  **建议同时加 `DGS3MO` 和 FRED 现成的 `T10Y3M` 价差序列**（两行，成本相同）：直接用 T10Y3M 做自变量最省事，DGS3MO 留作交叉校验。
- **黄金回归值（写成单测，±0.05pp，过不了不算完成）**：
  | 利差 | 12M 衰退概率 |
  |------|-------------|
  | −100 bp | **52.60%** |
  | 0 | **29.69%** |
  | +100 bp | **12.89%** |
- **工期：0.5–1 人日**（拉取 + 拟合 + 历史回填 + 单测）。
- 演示文案须明示"**非 T10Y2Y**"避免误读。

### 7.3 L1 FCI（金融条件指数）

> **⚠️ 探针 P1 修正（2026-07-31 实测）**：原设计"消费闲置 FX / 加密 / 商品 / BDI 库存"**不可行**——这些源在磁盘上**只有当日快照（`fx_latest.json` / `crypto_latest.json` / `commodity_yahoo.json`），没有历史序列**，滚动 PCA 无面板可用。
> **替代路径（更优）**：FCI 五个标准成分**全部已在 `fred_history/` 内，且是长序列**，零采集成本：

| 成分 | series | 行数 | 最新 |
|------|--------|------|------|
| 期限利差 | `T10Y2Y` / `DGS10` | 12,537 / 16,128 | 2026-07-29 / 07-28 |
| 投资级信用利差 | `BAA10Y` | 10,143 | 2026-07-28 |
| 高收益利差 | `BAMLH0A0HYM2` | 837 | 2026-07-28 |
| 波动率 | `VIXCLS` | 9,240 | 2026-07-28 |
| 美元广义指数 | `DTWEXBGS` | 5,155 | 2026-07-24 |

- 方法（**fci-1.1 终版，2026-07-31 实测定稿**）：**双轨 PCA**，输入为 5 个 FRED 长序列；FX/加密/商品快照降级为日报展示层，不进 PCA。
  - **`fci_revised`**：全样本 PCA，每次运行整条重估 → 与 NFCI 可比的水平指数（含 look-ahead，历史会被修订）。
  - **`fci_pit`**：扩展窗 PCA（burn-in=504 交易日，只用 ≤ t 数据）→ 无 look-ahead，供回测 / Brier 打分。
  - **符号锁定锚**：从"载荷总和"升级为**信用利差块 `[BAA10Y, BAMLH0A0HYM2]` 的载荷和**（全样本载荷 0.552 / 0.637，最稳；VIX/美元载荷常在 0 附近，做总和锚会抖）。
- **工期：实际 0.5 人日落地**（面板同目录同格式，对齐零成本；难点确为符号翻转 + 缺失处理，已用 G2/G3 闸门兜住）。原估 3–5 人日偏保守。
- 注意 `BAMLH0A0HYM2` 仅 837 行（约 3 年）——它是 PCA 窗口长度的**实际约束项**，已在 G3 覆盖率闸显式处理（面板 ≥252 行且成分 ≥4/5）。
- sanity 锚：与 **Chicago NFCI** 的相关性（**NFCI 已加采**：`fetch_fred_history.py` SERIES 40→41，2,899 行落盘 `fred_history/NFCI.csv`，周频 1971~2026-07-24）。

#### 实施结论（2026-07-31，compute_fci.py · schema fci-1.1）

> **⚠️ 关键方法论发现 —— 滚动去趋势会破坏水平可比性**：初版用「滚动 504 日窗口 + 窗口内 z-score」，方向与符号都对（诊断证明全样本静态 PCA 与 NFCI 水平相关 **+0.832**），但**滚动标准化把水平信息当趋势去掉了**——每个点拿自己前 504 天做基准，指数被强制去趋势，而 NFCI 是有慢趋势的水平指数。实测滚动版与 NFCI 水平相关仅 **+0.065**，sanity 不过。
> **修正 = 双轨设计**（见方法）。revised 全样本标准化后水平相关 **+0.828**（PASS，阈值 0.6）；pit 扩展窗水平相关 +0.467（参考值，不作闸门）。
> **look-ahead 是此类指数的固有性质**——Chicago Fed 自己的 NFCI 也每周全样本重估、整条历史被修订。故 revised 轨**必须字段级硬标注用途**：✅ 当期/日报/仪表盘/与 NFCI 对照；❌ 禁止任何回测/预测验证/Brier 打分。pit 轨反之。这与 **§7.5 GED「年度冻结快照禁当当前信号」是同一条铁律的镜像面**：那边是"拿陈旧数据冒充实时"，这边是"拿修订数据冒充当时可得"——两者都 fail-loud。

- **实测产出**：面板 840 行（2023-05-22 ~ 2026-07-30，约束项 `BAMLH0A0HYM2` 837 行）；PC1 解释方差 42.3%；载荷 T10Y2Y +0.436 / BAA10Y +0.552 / BAMLH0A0HYM2 +0.637 / VIXCLS −0.001 / DTWEXBGS −0.316；最新 2026-07-30 `fci_revised=−0.942`（负值=宽松，与 NFCI 负号同向）。
- **落盘**：`fci_daily.csv`（revised 每次全量重写 + pit 值稳定）、`fci_vintage_log.csv`（append-only 版本轨迹）、`fci_latest.json`（最新读数 + `usage_policy` 用途硬标注 + `method` 溯源）。
- **调度**：已注册 `scheduler.py` `compute_fci` @ **05:35**（fred_fetch 05:30 之后，刷新 fred_history 后计算），容器已重启加载。
- **G2/G3/G4 全部落实**：G2 禁 fillna(0)（仅 limit=5 前向填充节假日错位，填不上即剔除计数）；G3 成分<4/5 或样本<252 → exit 2 不写任何输出；G4 `as_of`/`data_vintage`/`schema_version` + append-only 版本日志。

### 7.4 财经线四条质量闸门（QA Round1-A，全部采纳）

| 闸门 | 内容 |
|------|------|
| **G1 口径断言** | probit 自变量必须是 T10Y3M；系数用 α=−0.5333 / β=−0.5984 |
| **G2 禁 `fillna(0)`** | z-score 里 0 = 常态，缺列补零 = 静默捏造"无压力" —— **静默降级在财经线的同构复发**，必须 raise |
| **G3 覆盖率闸** | 参与 PCA 成分 <80% 或窗口样本不足 → 整份 degraded、**不写 sim_trigger**（复用 P0 同一套 degraded 通道） |
| **G4 输出溯源** | 带 `as_of` + `data_vintage`，追加不覆盖 |

vintage 只取**输出侧 append-only**（不改现有 fetcher，零回归风险）；输入侧 ALFRED vintage 留 P2。

### 7.5 GED 接入（**实施 Sprint-0，逻辑归 C 流**）

**资产事实**：`GEDEvent_v26_1.csv`（UCDP GED v26.1，417,968 事件 × **49 列**（团队批1 索引旧值 48 已纠正），1989–2025，262 MB，CC BY 4.0），**已落 NAS**。

**QA 实测三处新发现 + 闸门（工程全部吸收）**：

| # | 实测发现 | 闸门实现 |
|---|---------|---------|
| 1 | **5,075 行（1.21%）违反 `low ≤ best ≤ high`**（low>best 1,419 / high<best 3,691）→ 批1"用 best/high/low 做 M8 区间化样板"的假设**不成立**，直接取 [low,high] 会出**负宽区间** | clamp 带计数器，输出 `validation_report`（clamp_low_cnt / clamp_high_cnt / 比例）；比例超阈值（建议 2%）**ETL 失败退出**，绝不静默 clamp |
| 2 | **`year_max = 2025`，2026 事件 = 0** → 这是**年度冻结快照**，非准实时源 | 聚合表元数据加 `snapshot_year=2025, frozen=true`；读取层对"当日风险"类查询**硬断言拒收**（`assert 消费场景 ∈ {backtest, baseline}`）；接线处硬断言 `max(year) < 当前年` |
| 3 | 月度 lead-lag 聚合有偏：`date_prec=4/5`（仅月/年精度）**12,206 条**、跨月事件 **7,184 条** | 月度聚合限 `date_prec ≤ 3`，并在报告输出**排除行数/比例** |

**架构追加硬闸门（Round2-3）**：GED 聚合产物必须带 `as_of=2025 / frozen=true`，**代码层禁止被日更 scan 路径读取（读到即 fail-loud）**。理由：年度冻结快照混入当前信号，是 **point-in-time 泄漏的镜像错误**（拿陈旧数据冒充实时），**比缺数据更危险**。

**工程实现红线**：
- 解析：强制 `csv` 模块或 pandas 带 `quotechar` 的默认 C engine，**绝不 `split(',')`**（`source_headline`/`article` 内嵌换行）；**记录数以 `len(df)` 为准，不按行数**。
- 体积：一次性 ETL 成 `country × year × type` 聚合表（几万行，<10 MB），**原始 CSV 不进服务进程**；线上只读聚合结果。
- 口径：跨年事件按 `date_start` 归属年并**显式记录口径**；年度快照 → 幂等全量重跑，不做增量 diff。
- `code_status` 全为 Clear → 文件内无修订标记，修订只体现在 release 之间 → **vintage 必须做在版本快照层**（v26.1 冻结只读，v27 另存）。
- **工期：2–3 人日**（含三闸门 +0.5 人日，仍在 3 人日封顶内），独立于天璇；天璇建好后直接查聚合表，不需改动。

### 7.6 Sprint-0 前置铁门槛（PM）— ✅ **已于 2026-07-31 执行完毕**

三探针实测结论见 **§十七**。摘要：**P1 不通过（已给替代路径）/ P2 全绿 / P3 抓到 P0 级未爆弹**。

### 7.7 Sprint-0 工期与红线汇总

| 任务 | 人日 | 归属流 | 状态 |
|------|------|--------|------|
| L3 probit（含 T10Y3M/DGS3MO 加采 + 黄金值单测） | 0.5–1 | B | 🔲 待落地 |
| L1 FCI（含符号锁定 + NFCI 加采 + 双轨 PCA） | **实际 0.5**（原估 3–5 偏保守） | B | ✅ **已完成（2026-07-31，fci-1.1，sanity +0.828 PASS）** |
| GED ETL（含三闸门） | 2–3 | C（实施在 Sprint-0） | 🔲 待实施 |
| I1 Pydantic 契约 | ~0.5 | 横切 | 🔲 待实施 |
| 联调 / 展示 | — | — | — |
| **合计已消耗** | **约 0.5 人日（FCI）+ 核心10健康度 + P0修复** | | |

**红线（工程 Round1-B）**：**不要**为"复用"把 L1/L3 塞进 sim pipeline —— 那会把秒级热挂载退化成 COPY 重建。
**独立点亮三前提**：① 只读 FRED + scan 现有字段，不新增采集器脚本；② 走 scan 既有写库路径，只 INSERT 新 `indicator_key`，不新建表引擎；③ **不 import 任何 sim 侧包**（依赖串味会强制重建镜像）。
**共享面**：只共用两件东西——**DB 写入 adapter + IndicatorPoint dataclass**。FCI 是 numpy/scipy 滚动 PCA，probit 是单变量拟合，与天璇 LLM 编排零耦合。

---

## 八、开发策略（3 流拆法 · v3 内涵重定义）

**不一把梭串行，也不拆独立 repo**——留在现有单仓库，按契约边界拆 3 条并行流。

```
Sprint-0（1.5 周，scan 侧即时价值）
  └ L3 probit / L1 FCI / GED ETL / I1 Pydantic 契约
  └ 顺带跑通 predictions 契约 + git+SSH 推送重载链路 = 给 MVT 做低成本演练

Sprint-1~3（3–5 周）
流 A  天璇 B+A 重写（MVT · 唯一承重墙 · 三段切：纯基线 → 叠 LLM 调整 → NOVEL）
      └ 第一任务 = D4 绑定模块（输入契约前置件，复用 I1 基类）
      └ 改造对象 = run.py(run_full_simulation) + agents.yaml(12 固定 Agent 重定义为真实行为主体)
      └ N13 HTTP timeout 修复挂在第一段（纯基线）内做
      └ 可先用 mock 慢变量跑通
      └ ⚠️ macro-sim 为 COPY 重建模式，每次改码须 docker build + force-recreate

流 B  天枢韧性 + 即时价值（更名）
      └ 失败可见性 P0 / N13 / S1 sim_trigger / I4 loader 元信息化 / doc SSOT
      └ 【新】L1 FCI + L3 probit 先导交付
      └ 天枢热挂载，改码即生效，迭代快

流 C  方法学与验证流（升格）
      └ 天玑/玉衡运营化 + 校准闭环
      └ 【新】GRV 的 OECD 十步法外壳（理论框架 + Cronbach's α + Monte Carlo）
      └ 【新】天玑 ViEWS 特征消融 + 模型批评→下代迭代闭环
      └ 【新】GED 回测金标准 / B 基线回测（资产归 C，实施在 Sprint-0）
      └ 前置：GRV 权重先把"硬编码常量 vs grv_weights.yaml"收敛为单一真相源，再谈加权优化（等权也是合法选项，先文档化）
      └ WTM「慢变量严格单列不并入」= C 流方法学规范、B 流落地
```

**并行性判定（架构 Round1-C）**：L1/L3 与天璇**依赖面零交集**（不碰天璇契约、不写 predictions）；资源面 probit 几行、FCI 几十行，不挤占重写人力。唯一闸门：L1/L3 输出同样挂 `schema_version` + Pydantic 契约，避免未来接入天璇二次返工。

**资源切分（工程 Round1-D）**：
- **单人**：严格串行，Sprint-0 → 天璇三段切，不并行。
- **双人**：A 管 scan 侧（L1/L3/GED），B 管 sim 侧（天璇纯基线段），交界只有 schema，周同步一次。

治理：同仓库 + CI 契约测试（用 fixture 样例）+ sim 启动版本握手。
开发循环（已核实）：编辑 `world-sim/` git 树 → `bash deploy.sh [macro-scan|macro-sim]` → 天枢 rsync+restart（热）、天璇 rsync+build+recreate（重建）。

## 九、产品 KPI 与成功定义（PM Round1-C/D · 锚定外部基准）

- **owner 周耗时**为核心指标（硬上限不变），手动步骤摩擦超阈值即触发简化。撤销 prior 修复工时，预算重分配至三探针 + L1/L3 实施。
- 价值锚点 = **校准的不确定性**，输出须突出概率校准。
- **成功定义从"自定 Brier 线"升级为锚定外部基准**：
  | 线 | 外部锚 |
  |----|--------|
  | L3 probit | 复现 Estrella-Trubin 基准 **AUC ≥ 0.85** + 三个黄金回归值 |
  | L1 FCI | 与 **Chicago NFCI** 的相关性（sanity 锚） |
  | GED 线 | 覆盖率 + 年度认证对账一致率 |
  | 偏斜目标 | **BSS 对 naive 基线** |
- **限期认证机制**：天璇首版预测发布后 4 周内交付 GED 回测报告；逾期或未过 → 冻结扩展位晋升。

## 十、不可测边界（诚实标注）

- 校准质量本身、`MIN_TRIGGER_N=8` 阈值合理性、regime 标注准确率——无法自动化测。
- **修订**：`MIN_TRIGGER_N=8` / 校准质量因 GED 1989–2025 历史标签（n≫8）从"不可测"降级为"**可延后测**"。
- 消融：n<100 用 **VIF + 相关矩阵**，不提前上 SHAP。

---

## 十一、Live SSH 真源复核（2026-07-30 23:00–23:30）

> 评审类任务应直接 SSH 真源起步，不依赖 SMB 推断。

- **SSH 接法**：`ssh nas`（config：Host nas / User TSX / IdentityFile id_rsa / 192.168.31.108）。`luoxi@192.168.31.108` 会被拒。
- **真容器名**：天枢 = `macro-scan-macro-scan-1`(macro-scan:v7)；天璇 = `macro-sim`(macro-sim:latest)。
- **真部署路径**：`/vol2/1000/software/macro-scan/`（核心代码 bind→/app 热挂载）；平行副本 `world-sim/macro-scan` 核心代码 **byte-identical（diff=0）** → world-sim 是 git 真源，deploy.sh 单向同步。
- **逐项复核**：tianji_db v1.1 schema ✅ / N13 无超时 ✅ / S1 无 sim_trigger 写入 ✅ / scheduler 两 job 已排 ✅ / 数据空转 ✅ / llm_client 静默降级 ✅ / N14 两容器 data 同源 ✅ / manual_scores.json 已填且带 updated_at ✅ / run.py 写报告不写 predictions 表 ✅ / **fred_history 44 series，无 3M 相关** ✅（Round2 工程复核）。

## 十二、Live 代码 Concrete 层（文件级实施蓝图）

### 12.1 天玑库（tianji_db.py，live /app）
- v1.1 schema 已落地，五表齐全，`reasoning_trace` 含 `causal_chains` 扩展。契约冻结按 6.1 additive-only。

### 12.2 天璇 LLM 客户端（core/llm_client.py）— P0 修复点定位
| 位置 | 现状 | 修复 |
|------|------|------|
| `_load_key` L40 | fallback 硬编码 `/vol2/1000/software/macro-scan/key.txt`（sim 容器内不存在） | 改为仅读环境变量，fallback 指向 sim 本地或留空 |
| `call_llm` L62-92 | `max_retries=2` / `temperature=0.4` / `max_tokens=256` / **无 timeout** / 失败 `return ""` | ① 返回 `(text, ok, reason)`；② 加 `timeout=(connect,read)`；③ 指数退避+jitter，区分 4xx/5xx/429 |
| `parse_action` L106 | 找不到 ACTION → `return "HOLD"`（静默降级） | 返回哨兵（None），调用方显式降级并打标 |
| `test_connection` L116 | 测 GLM-Z1-9B + Qwen3-8B，但实际调 **Qwen3.5-27B** → 假绿灯 | 必须测实际使用的模型 |
| 运行聚合 | 无 | `llm_fail_rate` + `truncated_rate`，>5% → `degraded=true` 拒写天玑 |

### 12.3 慢变量 / I4（slow_variables.py）— 紧迫性已修正
- `manual_scores.json` 已存在且自带 `updated_at`（07-30：tech=0.65 / nuke=0.5）。
- `_load_manual_score(key, default=0.0)` L306 忽略 `updated_at`，异常一律 `return default`（nuclear_posture 默认 0.0 = 恰好"稳定"）。
- 修复：返回 `{value, source, age_days}`；>45 天降级标 stale；缺失用中性值标 neutral；非 fresh 冒泡报告头；降级月天玑单标不混入 Brier。
- `save_manual_score` L325 已写 `updated_at` → 数据结构就绪，只差 loader 消费。

### 12.4 天璇推演主程序（run.py）— 流 A 重写依据
- `run_full_simulation` L27：Monte Carlo × 100（L59/63），预测未来 50 个月；循环 L373/L399。
- 读 `config/agents.yaml`（12 固定 Agent）、`calibrated_agent_params`。
- 输出经 `_write_report` L120 + `_send_ntfy` L461 → **只写报告，不写 predictions 表**。
- **结论**：保留 Monte Carlo 引擎 + agents.yaml 机制，新增 **B（历史相似度基线）+ A（有界 LLM 调整）+ NOVEL 区间**模块，输出改写到 `predictions` + `reasoning_trace` + `indicators`（按 6.2 schema）。

### 12.5 天璇 Agent 定义（config/agents.yaml）— 流 A 重定义对象
- 12 固定 Agent（A1-A12），含 `info_delay` / `activation_prob` / `transmission_coefficients` / `params`，数据驱动可热改。
- 流 A 将其**语义重定义为"真实行为主体"**，保留 yaml 热改机制。

### 12.6 部署模型（deploy.sh）— 迭代成本
- `deploy_scan`：rsync + `docker compose restart`（**热挂载，秒级**）。
- `deploy_sim`：rsync + `docker build` + `up -d --force-recreate`（**COPY 重建，慢**）。
- → 流 A 迭代成本高于流 B，排期须预留 build 时间；首次 build 前确认 pip 代理注入。

### 12.7 S1 触发（geo_risk_vector.py）— 流 B 任务
- 已算 `global_composite`（L413-423/518），但 **grep 无任何 sim_trigger 写入** → 未做。
- 插入点：`global_composite` 计算末尾补 `≥68 → 写 sim_trigger.json`（含 `trigger_reason`，见 6.4）。

---

## 十三、核心 10 目标清单（**v3 地理重排版，待用户最终确认**）

**筛选原则（PM Round2-B）**：**可判定性 + 数据地板双约束，不为平衡而平衡**。
- **保留美国利率双锚**：FRED 是 L1/L3 的数据地板 + 全球定价锚，**动不得**。
- 美国本土其余 2 席让位 → 补 1 个中国目标 + 1 个非西方冲突目标。
- RSSHub 中日欧作**叙事层平衡进观察名单**，暂不占核心席（可判定性弱）。

| # | 目标 | 数据源 | 分辨期 | 耦合 | v3 变更 |
|---|------|--------|--------|------|---------|
| 1 | FOMC 利率决议方向 | FRED + FOMC 日程 | 1–2 月 | IRP | 保（利率锚1） |
| 2 | **美债 T10Y3M 利差季度末状态（倒挂/转正）** | FRED（新加 DGS3MO/T10Y3M） | 1 季 | IRP / 衰退 | **口径由 T10Y2Y 改 T10Y3M** |
| 3 | WTI 原油季度均价区间 | Yahoo 商品期货（已接） | 1 季 | IRP / 能源 | 保 |
| 4 | 黄金季度均价涨跌方向 | Yahoo 商品（已接） | 1 季 | 避险 | 保 |
| 5 | BDI 季度方向（±15%） | 项目自有 CSV | 1 季 | 贸易 | 保（零采集成本） |
| 6 | VIX 季度均值 > 20 | FRED / CBOE | 1 季 | GPR | 保 |
| 7 | 欧元区季度 GDP 技术性衰退判定 | WB（现）/ Eurostat（待接） | 1 季 | — | 保 |
| 8 | ECB 或 BOJ 当季政策转向 | 央行日程公开 | 事件型 | — | 保 |
| 9 | **中国制造业 PMI 季度方向** | **AkShare（已接）** | 1 季 | 中观 | **新增（腾席）** |
| 10 | **非西方冲突目标：某热点地区月度冲突强度方向** | **GDELT（运行信号）+ GED（认证金标准）** | 月度判定 / 年度认证 | GCI / UCRI | **新增（腾席）+ 双层重构** |

**移出核心 10**：原 #3「DXY 美元指数」、原「美元兑主要货币方向」→ 降入观察名单（O6）。

> **⚠️ 事实更正（探针 P1，2026-07-31）**：此前判定"系统无 DXY"**是错的**。`fred_history/DTWEXBGS.csv`（贸易加权美元广义指数，5,155 行，2006 至今）**一直在采**，它就是 DXY 的官方等价物（覆盖面更广）。
> 移出 #3 的**理由因此改变**：不是"没数据"，而是"美元方向与 #1/#2 利率锚高度共线，占席性价比低"，且它已被吸收为 **L1 FCI 的第五个 PCA 成分**（§7.3）——即该信息未丢失，只是从"考题"变成"指标成分"。

### 13.1 目标 #10 的双层设计（PM Round2-1a/1b，**关键**）

GED 是年度冻结快照，接进日报当"当前信号"是口径错误（PM 已收回 Round1 说法）。修订后：

| 层 | 用什么 | 节奏 | 判定 |
|----|--------|------|------|
| **运行信号** | **GDELT**（已接、准实时）聚合降噪指标：月度窗口聚合 + 事件类型/Goldstein 阈值过滤压噪声；**单条 GDELT 事件永不直接触发判定** | 月度 | 方向性预测（升级/降级/持平），月末即判，计入 **BSS**（对 naive 持平基线） |
| **认证金标准** | **GED 年度快照回测校准**（v27 落地后对上年预测做对账审计） | 年度 | 月度判定与 GED 事件实况的**一致率**，此为该目标的 Brier/BSS **权威口径** |
| **叙事佐证** | RSSHub / Defense RSS | — | **不参与判定**，进观察名单 |

两个闸门**分数分开报，不混算**；月度分数须标注"**待 GED 认证**"水位。
设计合理性：GDELT + GED 双层恰好是"**运行闸 / 认证闸解耦**"在数据侧的对应物——运行用 GDELT，认证用 GED。

**观察名单（不进校准，保留扩展位；激活见一·四条件）**：
- O1 核威慑态势显性升级（GCI 相关，结算偏主观）
- O2 科技管制进一步加码（I4 输入，政策时点难判定）
- O3 全球粮食危机指数突破阈值（FAO，阈值主观）
- O4 特定海域航运中断事件（事件型，分辨期不定）
- O5 主要经济体主权债务危机预警（客观但分辨期长）
- O6 美元兑 EUR/JPY/CNY 季度方向（Frankfurter 已接，从核心 10 降入）
- O7 中日欧叙事情绪指标（RSSHub 8 路由，可判定性弱）

## 十四、Brier 达标线（**v3：分层 + 外部基准锚定**，待用户确认）

Brier ∈ [0,1]，0=完美，0.5=随机。

**陷阱**：
- **基率偏斜**：正例基率 80% 时全猜"否"即得 Brier≈0.16，裸 0.25 线偏松 → 偏斜目标（基率 <20% 或 >80%）**强制用 BSS**（相对 climatology / naive 基线）。
- **样本阈值**：n<20 不展示 BSS（n=1 时 skill=None 失真），仅原始 Brier + "样本不足"。
- **分桶校准误差**：NOVEL 输出是概率区间，须看 reliability diagram，不只点值。

**分层达标线（暂定，待天玑回测校准后修订）**：
| 阶段 | 样本量 | 达标线 |
|------|--------|--------|
| 阶段 0 | n<20（前 ~6 个月） | 不考核，累积样本，仅展示原始 Brier |
| 阶段 1 | 20 ≤ n < 50 | Brier ≤ 0.25 达标；BSS > 0（优于气候态）即合格 |
| 阶段 2 | n ≥ 50 | Brier ≤ 0.20 优秀；分桶校准误差（按预测概率 10% 区间）≤ 0.05 |
| 偏斜目标 | 基率 <20% 或 >80% | 强制 BSS；输出突出概率校准曲线而非点预测 |

**v3 新增外部基准层（不替代上表，是并行的即时可验 KPI）**：
- L3 probit：AUC ≥ 0.85（Estrella-Trubin 基准）+ 三黄金回归值 ±0.05pp
- L1 FCI：与 Chicago NFCI 相关性达 sanity 阈
- 目标 #10：年度 GED 认证一致率（首年建基线，次年起设线）

---

## 十五、非西方 / 多边数据源盘点（2026-07-30 二次修订，v3 沿用）

> **重大更正记录**：本节初版基于凭空 WebSearch、未读团队既有调研，造成两处实质错误：① ACLED 已放弃（需 edu/org/gov 邮箱，团队 B5 决策 + 用户确认）→ 彻底剔除；② World Bank / ECB 汇率 / SotW / AkShare 中国 / UCDP GED 全部已接入或已落盘，初版当"缺口"是重复造轮子。

### 真实状态表
| 区域 | 源 | 现状 | 备注 |
|------|-----|------|------|
| 全球多国 | **World Bank API** | ✅ 已接入 | `fetch_world_macro.py`；AkShare 中国亦走 WB API |
| 全球多国 | **SotW** | ✅ 已接入 | 实测调 `statisticsoftheworld.com/api/v2` |
| 欧元区货币 | **ECB 汇率 (Frankfurter)** | ✅ 已接入 | `fetch_fx.py`；**系统无 DXY**（仅货币对） |
| 中国宏观 | **AkShare 中国** | ✅ 已接入 | 7 指标 + 中观（**PMI** / 二手房 / 企业景气）→ 目标 #9 零成本 |
| 全球冲突真相 | **UCDP GED v26.1** | ✅ 已落 NAS | 417,968 事件 × 49 列，1989–2025，CC BY 4.0；**年度冻结快照，仅回测/基线** |
| 中欧日财经新闻 | RSSHub（财新/一财/FT/BBC/Reuters/日经 等 8 路由） | ✅ 已接入 | 自建容器，补西方媒体偏见 |
| 军事/地缘 | Defense RSS + SIPRI | ✅ v3.7.0 | `fetch_defense_rss.py` / `fetch_sipri_backdrop.py`，走代理 |
| 美债 3M | **DGS3MO / T10Y3M** | ⚠️ **待加（10 分钟）** | Sprint-0 L3 前置，SERIES 列表加两行 |
| 全球多国 | **IMF SDMX（WEO/BOP/IFS）** | ❌ 真缺口 | 190+ 国官方，免费无 auth |
| 欧盟 | **Eurostat** | ❌ 真缺口 | 7000+ 数据集 / 27 国 / SDMX 2.1 |
| 日本 | **BOJ (bojdata)** | ❌ 真缺口 | FRED 兼容 API / 无 key |
| 全球冲突 | ~~ACLED~~ | 🚫 已放弃 | 团队 B5 + 用户确认 |

### 诚实的局限（须在输出标注）
1. **机构出身仍西方**：WB/IMF（华盛顿）、ECB/Eurostat（欧盟）本质西方多边机构；真正非西方一手宏观源仅中（AkShare/NBS/PBOC）+ 日（BOJ/e-Stat）；第三世界宏观主要经 WB/SotW 聚合流入。
2. **SotW 商业存续不确定**：应逐步用官方 SDMX（Eurostat/IMF）替代其覆盖部分，而非新增依赖。
3. **出网可达性**：新源须先实测直连 vs 代理（项目铁律）。
4. **GDELT 西方偏见**：靠英语关键词 + 西方媒体，对非西方事件系统性欠覆盖 → 由 GED 年度认证反向校验 lead-lag 命中率（目标 #10 双层设计的第二个理由）。

---

## 十六、拍板事项 — ✅ **已定稿（2026-07-31，用户确认）**

| # | 事项 | 决议 |
|---|------|------|
| 1 | **核心 10 清单**（十三） | ✅ **采纳 v3 地理重排版**：保美国利率双锚、腾 2 席给中国 PMI + 非西方冲突双层目标 |
| 2 | **Brier 达标线**（十四） | ✅ **采纳分层表 + 外部基准并行层** |
| 3 | **人力配置** | ✅ **单人严格串行**：Sprint-0 (1.5 周) → 天璇 (3–5 周)，总 5–7 周，不并行 |
| 4 | **三探针** | ✅ **先跑** —— 已于当日执行完毕，结论见 §十七 |

其余（契约冻结 / 优先级 / 3 流拆法 / Concrete 修复点 / 数据源地图 / 全部质量闸门）已全部落定，可直接排期。

---

## 十七、三探针实测报告（2026-07-31 00:30–01:10，SSH 真源 + 隔离实验）

> 执行方式：`ssh nas` → `docker exec`，全部一手实测，无推测。

### P1 · 闲置 series 新鲜度 —— ❌ **不通过，但找到更优替代**

| 检查项 | 结果 | 判定 |
|--------|------|------|
| `fx_history/` | **仅** `fx_latest.json`（427 B，Frankfurter，as_of 07-29） | ⚠️ 无历史序列 |
| `crypto_history/` | **仅** `crypto_latest.json` + `crypto_extra_latest.json`（CoinGecko，`as_of: null`） | ⚠️ 无历史序列，且 as_of 为 null |
| `commodity_yahoo.json` | 单快照，as_of 07-29，WTI 84.32 / Brent 90.40 / 铜 6.3625 | ⚠️ 活着但无历史 |
| `bdi_history.csv` | 有历史，末行 **2026-07-28**（滞后 2–3 天） | 🟡 可用 |
| `fred_history/` | **44 series，全部长历史 CSV** | ✅ |

**结论**：PM Round-1 的「消费闲置 FX/加密/商品/BDI 库存做 FCI」叙事 **不成立** —— 这些是**快照不是序列**，滚动 PCA 无面板可用。
**但这不阻塞 L1**：FCI 五个标准成分全在 `fred_history/` 且是长序列（见 §7.3 表），**改用 FRED 面板后风险反而更低**（同目录同格式，对齐成本下降）。
**副产品**：`DTWEXBGS`（美元广义指数）被发现一直在采 → 更正了 §十三"系统无 DXY"的错判。

### P2 · probit 试算 —— ✅ **全绿**

| 子项 | 结果 |
|------|------|
| 公式复现（本地） | α=−0.5333 / β=−0.5984，Φ(α+β·spread)：−100bp→**52.5953%** / 0→**29.6913%** / +100bp→**12.8880%**，三值**全部 PASS**（误差 <0.005 pp，远优于 ±0.05 容差） |
| FRED 实拉 `T10Y3M` | ✅ n=41，最新 **2026-07-29 = 0.84** |
| FRED 实拉 `DGS3MO` | ✅ n=40，最新 **2026-07-28 = 3.90** |
| 交叉校验 | `DGS10(4.61) − DGS3MO(3.90) = 0.71`，与 FRED 官方同日 T10Y3M 一致 ✅ |
| **当前真实衰退概率** | 正确口径 T10Y3M=0.84 → **15.01%** |
| **口径错误代价实测** | 误用 T10Y2Y=0.45 → 21.11%，**偏高 6.10 个百分点** |

→ QA 的 T10Y3M 纠正**价值实锤**：不改口径，系统上线第一天就系统性高估衰退风险 6 个点。

### P3 · sim_trigger schema —— 🔴 **抓到 P0 级未爆弹**

原探针问题（"能否 additive 加 `trigger_reason` 枚举"）答案是**能**（payload 为 dict 直接 `json.dump`，加 key 零成本；实测 schema 仅 `level` / `event` / `triggered_at`，**注意：此文件没有 `schema_version`**，与 §6.4 描述有出入）。

**但探针挖出了一个更严重的问题：**

| 事实 | 证据 |
|------|------|
| `sim_trigger.json` **0 字节，停更于 Jul 25 18:14** | `ls -la` 实测 |
| scan 写入用 `os.replace(tmp, path)` 原子写 | `grv_threshold.py` L227–247 |
| sim 消费后 `TRIGGER_PATH.write_text("")` 清空 | `run.py` L517（**这解释了 0 字节 + mtime 完全对上**） |
| 两容器 inode 相同 = 1903810，链路**当前是通的** | `stat` 双向核对 |
| **挂载方式是 single-file bind mount** | `/vol2/.../data/sim_trigger.json → /app/sim_trigger.json (rw)` |

**隔离实验实证（新建临时容器，零风险）**：

| 挂载方式 | 宿主 `os.replace` 后 inode | 容器内读到 |
|---------|--------------------------|-----------|
| **单文件挂载** | 1048964 → 1048965 | **仍是 OLD**，容器 inode 锁死在 1048964 ❌ |
| **目录挂载** | 同样换 inode | **立刻是 NEW** ✅（路径解析，不锁 inode） |

**⚠️ 结论 —— 未爆弹的完整形态**：
> 天璇的触发链路**只能用一次**。Jul 25 那次消费成功（`write_text("")` 是原地截断，inode 不变，所以没炸）。但**下一次 GRV 触发 L3 时**，scan 的 `os.replace` 会换掉 inode → macro-sim 的单文件挂载永远指向被 unlink 的旧 inode → **天璇再也收不到任何触发**。
> 且失败**完全静默**：scan 侧照常打印 `[B线] sim_trigger.json 已写入（L3）`，ntfy 照常推送"自动推演已启动"，而天璇那头一片死寂。
> **这是"静默降级"病族的第四例**（前三例：`call_llm` 返回 ""、`parse_action` 静默 HOLD、财经线 `fillna(0)`），且是唯一一个**跨容器**的。

**修复选项（列入 Sprint-0，需团队定夺）**：

| 方案 | 改动 | 代价 |
|------|------|------|
| **A（推荐）** | compose 把 `/app/macro_data` 从 ro 改 rw + `run.py` L22 改指 `/app/macro_data/sim_trigger.json`，删掉单文件 mount | **2 行 + 重启**；目录挂载天然规避 inode 问题（已实证） |
| B | scan 侧改原地截断写（不用 `os.replace`） | 1 行，但失去原子性，读者可能读到半截 JSON，需 flock 补偿 |
| C | 改 `data/triggers/<ts>.json` 目录轮转，sim 扫目录、消费后改名 `.done` | 最健壮、天然带审计轨迹，但改动最大 |

**附加**：修复后应补一条 QA 断言 —— **触发写入后必须由消费侧回 ack**（写 `.ack` 或回填 `consumed_at`），否则"写了没人收"这类静默失效无法被发现。这正是 P0"失败可见性"在跨容器边界上的延伸。
