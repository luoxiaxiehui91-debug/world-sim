# 验证命令注册表（Direction C：Confirmation 验证机制）

**项目**：world-sim（world-deduction）
**创建**：2026-08-06 14:45 UTC+8 by qa-governance（严过关）；**v2 对齐 A 表**：2026-08-06 14:55
**基线**：repo HEAD `6ba35ab` / macro-scan v3.8.15 / GRV `_schema_version=1.0`
**状态**：✅ 8/8 实跑通过（A 表 14:42 + 本表 14:44 独立复跑一致）

> **与 A 表的关系（v2 对齐）**：A 表 `source-of-truth-registry.md` 已产出（14:42，8 真源 + 8 命令全部 SSH 实测）。按团队约定，**本表命令列直接引用 A 表 §2.2 命令列，不重写命令全文**——避免同一对象出现两个命令版本的新漂移。
> - A 表 = 对象→真源位置→命令（真源仲裁）；本表 = 命令→期望值→哈希→抽测（反作弊）+ 触发规则 + 报告模板。
> - 本表**增量**：① 每条命令 sha256 哈希（防篡改）；② C2b/C7 两条 A 未覆盖的补充命令（内层 deploy.sh 陷阱、scheduler_state 新鲜度）；③ QA 抽测审计条款；④ 触发规则与巡检报告模板。

---

## 1. 核心注册表（命令引用 A §2.2；哈希绑定 A §2.2 命令全文）

| ID | 对象 | 命令（引用 A 表 §2.2-N，不重写；C 增量见 §2） | 期望值（契约，独立于实现） | 口径版本 | 命令哈希 sha256(前12) | 提取源（真源代码+行号） | 负责人 | 上次运行 | 结果 |
|----|------|------|------|------|------|------|------|------|:----:|
| C1 | scheduler.py JOBS 计数 | A§2.2-1（ast 权威解析，禁 grep 缩进正则） | 元组 **50** = 唯一名 **47** + weak_signal×4 | scheduler.py@6ba35ab（容器 md5 ec636bff ≡ 仓库） | `71c93c603035` | 核心代码/scheduler.py **L41-109** | devops 维护 / QA 审计 | 2026-08-06 14:42(A)/14:44(复跑) | ✅ |
| C2 | monorepo deploy.sh rsync 标志 | A§2.2-2（grep monorepo 根 deploy.sh） | `--delete` 计数 **0**；`rsync -av` 计数 **2**（L13/L34） | world-sim/deploy.sh@6ba35ab | `16a32111c44c` | /s/world-sim/deploy.sh **L13/L34** | devops / QA | 14:42/14:44 | ✅ |
| C2b | **内层** macro-scan deploy.sh rsync 标志（A 未覆盖，C 补充） | §2 命令全文（匹配实际调用行，避开 L26 注释假阳性） | 实际调用仅 L28 `rsync -a`，**无 --delete**（L26 注释提及 --delete 是历史说明，非标志） | macro-scan/deploy.sh@6ba35ab | `3198ac18a306` | macro-scan/deploy.sh **L28**（注释 L26） | devops / QA | 14:44 | ✅ |
| C3 | grv_latest.json 键数/维度/新鲜度 | A§2.2-3（jq，期望独立于实现） | 顶层键 **24**；维度分数键 **17**（16 维度 + global_composite）；`updated` = 当日 | GRV `_schema_version=1.0`（口径 v1 对齐 A） | `ccaf3fe3095d` | 核心代码/geo_risk_vector.py **L832-848** | devops / QA | 14:42/14:44（updated=2026-08-06T06:10:18, composite=60.3） | ✅ |
| C4 | forecast_tracker.db 表计数/行数 | A§2.2-4（容器内 sqlite，天璇/天玑共享同 inode） | 业务表 **8**（+sqlite_sequence=9）；行数 actuals/evaluations/weight_update_log=0 **属预期**（唯一预测已 auto-verified），非空转 | 建表契约（forecast_tracker.py 3 表 + tianji_db.py 5 表） | `d3f874e8adec` | 核心代码/forecast_tracker.py **L50/74/85**；tianji_db.py **L29/60/73/86/107** | devops / QA | 14:42/14:44（9 表 / predictions=1 forecasts=289 narrative_chunks=181） | ✅ |
| C5 | tianji_trigger.json processed 状态 | A§2.2-6（jq + inode 双端一致） | `processed`=**true**；`last_result.exit`=**0**；`date`=**当日**；宿主与天玑容器 inode 一致（同文件禁双份） | schema v1（6ba35ab dom=None 修复后） | `c7f8a79751cd` | 核心代码/write_tianji_trigger.py **L21-28** | devops / QA | 14:42/14:44（batch=2026-08-06 processed=True，triggered_at 14:32:15） | ✅ |
| C6 | FCI 产物新鲜度 | A§2.2-7（stat + jq） | fci_daily.csv >100KB 且 mtime=**当日**；fci_latest.json `schema_version`=**fci-1.1**、`sanity_vs_nfci.status`=**PASS**、`as_of`=当日 | schema fci-1.1 | `6d5b11d15753` | 核心代码/compute_fci.py（scheduler.py L45 调度） | devops / QA | 14:42/14:44（109334B / 08-06 05:35 / fci-1.1 / PASS） | ✅ |
| C7 | scheduler_state.json 新鲜度（A 未覆盖，C 补充） | §2 命令全文（updated + heartbeat 年龄） | updated=**当日**；heartbeat_age **<300s**（调度器存活） | P0-D 契约（DATA_DIR 单点 + 真实健康探测） | `b661deed46e1` | 核心代码/scheduler.py **L220**；control_server.py **L183** | devops / QA | 14:44（updated=2026-08-06T14:42:43 heartbeat_age=27s） | ✅* |
| C8 | control_server.py last_ok 逻辑 | A§2.2-5（grep 天枢运行区） | L183 真实健康探测存在（`last_ok = scheduler_alive and bool(...)`）；硬编码 `last_ok = True` 计数 **0** | 口径 v1（案例4 P0-D 修复） | `f0489e2d4acf` | 核心代码/control_server.py **L183** | devops / QA | 14:42 | ✅ |
| C9 | 开阳 kaiyang dist | A§2.2-8（ls 运行区静态产物） | index.html 存在；assets/ 存在；data/ mtime 近期（当日或近 2 日） | 开阳运行区 dist | `403424e9b700` | /vol2/1000/software/kaiyang/dist/ | devops / QA | 14:42（data/ 08-06 11:12） | ✅ |

> *C7 advisory：调度器重启清空 in-memory `_last_run_ts`，job 级 last_run_ts=None 属正常（本次 tianji_trigger/grv_update 均 None，因 14:31 重启后未到触发槽）。**本命令只断言调度器存活（updated/heartbeat），不断言单 job 记录**；建议后续把 last_run 落盘持久化，否则无法区分"从未运行"与"重启过"。
>
> **口径对齐说明（v2）**：初版 C3 计"16 维（不含 global_composite）"，A 表口径为"17 维度分数键（16 维度 + global_composite）"。**已对齐 A 口径**（A 为真源仲裁权威）。两套口径并存即产生新漂移——这正是本表要消灭的病，特此记录。

---

## 2. C 增量命令全文（A §2.2 未覆盖的两条；命令哈希 = sha256(命令文本) 前 12 位）

A §2.2-1..8 命令全文以 **A 表 `source-of-truth-registry.md` §2.2 为唯一真源**（本表引用不重写，哈希已绑定 A 命令文本）。

```bash
# C2b — 内层 macro-scan deploy.sh 实际 rsync 调用行（A§2.2-2 只覆盖 monorepo 根；本命令补内层，避开 L26 注释假阳性）
grep -nE '"rsync -a[^"#]*' /vol2/1000/software/macro-scan/deploy.sh
```

```bash
# C7 — scheduler_state.json 新鲜度（updated 今日 + heartbeat 年龄 <300s）
docker exec macro-scan-macro-scan-1 python3 -c "import json,time; d=json.load(open('/workspace/data/scheduler_state.json')); print('updated=%s heartbeat_age_s=%.0f'%(d['updated'],time.time()-d['heartbeat']))"
```

---

## 3. 反作弊审查条款（QA 抽测清单）

1. **命令从真源代码提取（禁手写）**：每条命令"提取源"标注文件+行号；抽测时核对命令逻辑与代码结构一致（如 C1 ast 解析器对应 scheduler.py JOBS 列表）。
2. **命令唯一真源（防双命令漂移）**：本表命令一律引用 A 表 §2.2，**禁止在 C 表重写命令全文**；C2b/C7 为 A 未覆盖的补充命令，其全文仅存在于本表 §2，A 表如后续纳入须回写 A 并同步哈希。
3. **期望值独立于实现**：期望值取自代码常量/契约，**禁止用实现返回值当期望**（同义验证反模式）。例：C1 期望 47 唯一名来自 ast 解析语义（weak_signal×4 同一名），非 scheduler.py 字面量；C4 期望 8 表来自建表契约。
4. **部署一致性**：命令须在容器/部署目标实跑；采信前核对容器代码与仓库一致（实测 scheduler.py 容器 md5 `ec636bff` ≡ 仓库，方可采信 C1）。
5. **无输出即失败**：命令无 stdout 或非零退出 = 失败，禁止"空输出视为通过"。
6. **命令失真陷阱（实证）**：C2b 内层 deploy.sh 中 `--delete` 出现在注释 L26（历史说明）而非调用行——naive `grep rsync.*--delete` 会**误报 1 命中**；命令已改为只匹配实际调用行 `"rsync -a[^"#]*`。抽测必须能识别此类假阳性。
7. **哈希防篡改**：命令哈希覆盖命令全文；任何人改动命令必须同步更新哈希并重新抽测，否则判定该行失真。
8. **QA 随机抽测**：每周巡检中 QA 随机抽 ≥2 条命令在 NAS 实跑复核，与注册表比对；不一致 → 标记失真并回退该行。

---

## 4. 触发规则（与 A 表 §5 一致）

- **diff 触发（变更后必跑）**：任何真源对象变更（部署、代码改、数据写入）→ 立即跑对应命令，实测 = 期望才允许合入/宣告完成；不一致先按 A 表 §3 仲裁（文档过期/部署漂移），禁止静默。
- **每周巡检全量**：每周一全量跑全部 10 条（A§2.2-1..8 + C2b + C7），任一失败即 T2 级 stale 标记 + 转缺陷单；结果记入 `docs/governance/verification-log.md`（append-only，格式：日期｜对象｜命令｜实测｜判定），附 as-of 时间戳。
- **关键命令进部署门禁**：C1/C2/C2b（JOBS 结构、rsync 无 --delete）、C5（trigger 闭环）纳入部署后校验，不符即回滚（对接方向 D `deploy-channels.md`）。

---

## 5. 验证报告模板（巡检产出入 operations/）

```markdown
# 验证巡检报告 YYYY-MM-DD
- 巡检人 / 基线 commit / 巡检时间
| ID | 对象 | 期望值 | 实测值 | 通过/失败 | 差距说明 |
- 差距处理：任一失败 → 转缺陷单（关联 question/YYYYMMDD-...）
- QA 抽测记录：抽测命令 ID / 实跑输出 / 与注册表是否一致
- 签名：巡检人 + QA 审计人
```

---

## 6. 关联

- **A 表**：`source-of-truth-registry.md`（真源仲裁权威，本表命令列引用其 §2.2，不重写）
- **D 表**：`deploy-channels.md`（部署通道收敛，门禁对接）
- **B 表**：`document-governance.md`（文档分治，实录绑定验证命令 = 引用本表）
- **记忆降级**：`memory-demotion.md`（T2 级 stale 标记对接）
- **问题单**：`S:\docs\questions\world-deduction\20260806-world-deduction-four-direction-governance.md`
- **ADR**：`0009-cross-agent-consistency-validation`（本表即"每条 ADR 一命令"的推广）

---

## 附：首轮实测记录（2026-08-06 14:42 A 表 / 14:44 本表独立复跑 C1-C7，SSH TSX@192.168.31.108）

| ID | 实测输出（真实） | 判定 |
|----|------|:----:|
| C1 | `JOBS 元组数: 50` / `唯一 job 名: 47` / `重复名: ['weak_signal']` | ✅ |
| C2 | monorepo deploy.sh：`--delete`=0 / `rsync -av`=2（L13/L34） | ✅ |
| C2b | 内层 deploy.sh：`28: ssh "$NAS_HOST" "rsync -a \`（无 --delete；L26 仅注释提及） | ✅ |
| C3 | `top_keys=24 dims_present=17 missing=[]`；`updated=2026-08-06T06:10:18`、`global_composite=60.3` | ✅ |
| C4 | `表数: 9`（8 业务表 + sqlite_sequence）；predictions=1 forecasts=289 narrative_chunks=181 actuals/evaluations/weight_update_log=0（预期） | ✅ |
| C5 | `true / 0 / 2026-08-06`；inode 宿主 3241454 ≡ 天玑容器 3241454 | ✅ |
| C6 | `2026-08-06 05:35:19 ... 109334 fci_daily.csv`；`fci-1.1 / PASS` | ✅ |
| C7 | `updated=2026-08-06T14:42:43 heartbeat_age_s=27`（advisory：job last_run_ts 重启清空） | ✅* |
| C8 | `183: last_ok = scheduler_alive and bool(job_state.get("last_ok", False))` / 硬编码 `last_ok = True` 计数 0 | ✅ |
| C9 | index.html 846B（08-05 15:22）、assets/（08-05 15:22）、data/（08-06 11:12） | ✅ |

> 注：C3 复跑时按 A 口径补计 global_composite（17 维度分数键）；A 表实测 24/17/updated 与本表一致。
