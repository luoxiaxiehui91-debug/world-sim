# 验证命令注册表（Direction C：Confirmation 验证机制）

**项目**：world-sim（world-deduction）
**创建**：2026-08-06 14:45 UTC+8 by qa-governance（严过关）
**基线**：repo HEAD `6ba35ab`（天玑 dom 修复后）/ macro-scan v3.8.15 / GRV `_schema_version=1.0`
**状态**：✅ 首轮 8 条命令全部在 NAS 实跑通过

> **与 A 表的关系**：架构师 A 表（`source-of-truth-registry.md`）= 对象→真源位置→命令；本表（C）= 命令→期望值→哈希→抽测。**A 表产出后，本表命令列直接引用 A 表命令列，不重写**。本表当前独立成立（A 表尚未产出）。

---

## 1. 核心注册表

| ID | 对象 | 验证命令（全文见 §2，哈希绑定 §2 全文） | 期望值（独立于实现，取自契约） | 口径版本 | 命令哈希 sha256(前12) | 提取源（真源代码+行号） | 负责人 | 上次运行 | 结果 |
|----|------|------|------|------|------|------|------|------|:----:|
| C1 | scheduler JOBS 计数 | ast 解析 scheduler.py JOBS 列表，输出元组数与唯一名数 | tuples=**50**，unique_names=**47**（weak_signal×4 同一名计 1） | scheduler.py@6ba35ab（容器 md5 ec636bff ≡ 仓库） | `60a0a174e9f6` | 核心代码/scheduler.py **L41-109** | devops 维护 / QA 审计 | 2026-08-06 14:44 | ✅ |
| C2a | 天璇/天枢 monorepo deploy.sh rsync 标志 | grep 实际 rsync 调用行 | 仅 L13/L34 `rsync -av`，**无 --delete** | world-sim/deploy.sh@6ba35ab | `212e1b74f75f` | /s/world-sim/deploy.sh **L13/L34** | devops / QA | 2026-08-06 14:44 | ✅ |
| C2b | 内层 macro-scan deploy.sh rsync 标志 | grep 实际 rsync 调用行（`"rsync -a[^"#]*`） | 仅 L28 `rsync -a`，**无 --delete**（L26 注释提及 --delete 是历史说明，非标志） | macro-scan/deploy.sh@6ba35ab | `3198ac18a306` | macro-scan/deploy.sh **L28**（注释 L26） | devops / QA | 2026-08-06 14:44 | ✅ |
| C3 | GRV 键数 / 维度数 | 读 grv_latest.json，校验 24 顶层键 + 16 维契约名全在 | top_keys=**24**，dims_present=**16**，missing=**[]**（16 维 + _derived_meta 派生元数据 = "16+1 维/24 顶层键"） | GRV `_schema_version=1.0` | `f6d89797c17b` | 核心代码/geo_risk_vector.py **L832-848** | devops / QA | 2026-08-06 14:44 | ✅ |
| C4 | forecast_tracker.db 表计数 | sqlite_master 查业务表（排除 sqlite_sequence） | business_tables=**8**：forecasts/actuals/evaluations + predictions/reasoning_trace/weight_update_log/narrative_chunks/narrative_density_flags | 建表契约（当前） | `e553921de9b1` | 核心代码/forecast_tracker.py **L50/74/85**；tianji_db.py **L29/60/73/86/107** | devops / QA | 2026-08-06 14:44 | ✅ |
| C5 | tianji_trigger processed 状态 | 读天玑容器 trigger 文件 | batch=**今日(2026-08-06)**，processed=**True**（watchdog 已消费，闭环） | write_tianji_trigger.py（dom=None 修复后） | `68becf6b72d6` | 核心代码/write_tianji_trigger.py **L21-28** | devops / QA | 2026-08-06 14:44 | ✅ |
| C6 | FCI 产物新鲜度 | stat fci_daily.csv mtime | 日期=**今日**（compute_fci 每日 05:35 产出） | compute_fci.py（每日 05:35） | `a2084b84f3d8` | 核心代码/compute_fci.py（scheduler.py L45 调度） | devops / QA | 2026-08-06 14:44 | ✅ |
| C7 | scheduler_state.json 新鲜度 | 读 state，输出 updated + heartbeat 年龄 | updated=**今日**，heartbeat_age **<300s**（调度器存活） | P0-D 契约（DATA_DIR 单点 + 真实健康探测） | `b661deed46e1` | 核心代码/scheduler.py **L220**；control_server.py **L183** | devops / QA | 2026-08-06 14:44 | ✅* |

> *C7 附 advisory：调度器重启后 in-memory `_last_run_ts` 清空，job 级 last_run_ts=None 属正常（本次实测 tianji_trigger/grv_update 均 None，因 14:31 重启后未到各自触发槽）。**本命令只断言调度器存活（updated/heartbeat），不断言单 job 运行记录**。

---

## 2. 命令全文（可复制执行；命令哈希 = sha256(下方命令文本) 前 12 位）

```bash
# C1 — scheduler JOBS 计数（ast 解析，禁 grep 缩进正则——案例6方法论）
docker exec macro-scan-macro-scan-1 python3 -c "import ast; t=ast.parse(open('/app/scheduler.py').read()); jobs=[n for n in t.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='JOBS' for x in n.targets)][0].value; names=[e.elts[0].value for e in jobs.elts]; print('tuples=%d unique_names=%d'%(len(jobs.elts),len(set(names))))"
```

```bash
# C2a — monorepo deploy.sh 实际 rsync 调用行（期望无 --delete）
grep -nE '^[[:space:]]*rsync ' /vol2/1000/software/world-sim/deploy.sh
```

```bash
# C2b — 内层 macro-scan deploy.sh 实际 rsync 调用行（期望无 --delete；避开 L26 注释假阳性）
grep -nE '"rsync -a[^"#]*' /vol2/1000/software/macro-scan/deploy.sh
```

```bash
# C3 — GRV 键数/维度数（16 维契约名来自 geo_risk_vector.py L832-848）
docker exec macro-scan-macro-scan-1 python3 -c "import json; d=json.load(open('/workspace/data/grv_latest.json')); dims=['climate_risk','cultural_friction','disaster_risk','energy_grid_risk','global_south','india_pacific','japan_monetary','korean_peninsula','middle_east_energy','russia_europe','sanctions_risk','seismic_risk','social_stress','south_china_sea','taiwan_strait','us_china_strategic']; missing=[x for x in dims if x not in d]; print('top_keys=%d dims_present=%d missing=%s'%(len(d),len(dims)-len(missing),missing))"
```

```bash
# C4 — forecast_tracker.db 业务表计数（排除 SQLite 内部表 sqlite_sequence）
docker exec macro-scan-macro-scan-1 python3 -c "import sqlite3; con=sqlite3.connect('/workspace/data/forecast_tracker.db'); tabs=[r[0] for r in con.execute(\"select name from sqlite_master where type='table' and name!='sqlite_sequence' order by name\")]; print('business_tables=%d'%len(tabs)); print(tabs)"
```

```bash
# C5 — tianji_trigger processed 状态（天玑容器）
docker exec macro-scan-tianji-1 python3 -c "import json; d=json.load(open('/app/macro_data/tianji_trigger.json')); print('batch=%s processed=%s'%(d['batch_id'],d['processed']))"
```

```bash
# C6 — FCI 产物新鲜度（mtime 今日）
docker exec macro-scan-macro-scan-1 stat -c '%y %n' /workspace/data/fci_daily.csv
```

```bash
# C7 — scheduler_state.json 新鲜度（updated 今日 + heartbeat 年龄 <300s）
docker exec macro-scan-macro-scan-1 python3 -c "import json,time; d=json.load(open('/workspace/data/scheduler_state.json')); print('updated=%s heartbeat_age_s=%.0f'%(d['updated'],time.time()-d['heartbeat']))"
```

---

## 3. 反作弊审查条款（QA 抽测清单）

1. **命令从真源代码提取（禁手写）**：每条命令"提取源"标注文件+行号；抽测时核对命令逻辑与代码结构一致（如 C1 ast 解析器对应 scheduler.py JOBS 列表）。
2. **期望值独立于实现**：期望值取自代码常量/契约，**禁止用实现返回值当期望**（同义验证反模式）。例：C1 期望 47 唯一名来自 ast 解析语义（weak_signal×4 同一名），非 scheduler.py 中任何字面量；C4 期望 8 表来自建表契约。
3. **部署一致性**：命令须在容器/部署目标实跑；采信前核对容器代码与仓库一致（实测 scheduler.py 容器 md5 `ec636bff` ≡ 仓库，方可采信 C1）。
4. **无输出即失败**：命令无 stdout 或非零退出 = 失败，禁止"空输出视为通过"。
5. **命令失真陷阱（实证）**：C2b 内层 deploy.sh 中 `--delete` 出现在注释 L26（历史说明）而非调用行——naive `grep rsync.*--delete` 会**误报 1 命中**。本表命令只匹配实际调用行 `"rsync -a[^"#]*`。抽测必须能识别此类假阳性。
6. **哈希防篡改**：命令哈希覆盖命令全文（§2）；任何人改动命令必须同步更新哈希并重新抽测，否则判定该行失真。
7. **QA 随机抽测**：每周巡检中 QA 随机抽 ≥2 条命令在 NAS 实跑复核，与注册表比对；不一致 → 标记失真并回退该行。

---

## 4. 触发规则

- **diff 触发（变更后必跑）**：git diff 涉及 scheduler.py / deploy.sh / geo_risk_vector.py / *_db.py / docker-compose / 部署产物时，对应行命令必须重跑。
- **每周巡检全量**：每周固定时间跑全部 8 条，产出验证报告入 `operations/`。
- **关键命令进部署门禁**：C1（JOBS 结构）、C2a/C2b（rsync 无 --delete）、C5（trigger 闭环）纳入部署后校验，不符即回滚（对接方向 D 部署通道收敛）。

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

- **A 表**：`source-of-truth-registry.md`（架构师并行产出中；产出后本表命令列引用 A 不重写）
- **D 表**：部署通道收敛（门禁对接，C1/C2/C5 进部署门禁）
- **问题单**：`S:\docs\questions\world-deduction\20260806-world-deduction-four-direction-governance.md`
- **ADR**：`0009-cross-agent-consistency-validation`（本表即"每条 ADR 一命令"的推广）

---

## 附：首轮实测记录（2026-08-06 14:44 UTC+8，SSH TSX@192.168.31.108 实跑）

| ID | 实测输出（真实） | 判定 |
|----|------|:----:|
| C1 | `tuples=50 unique_names=47` | ✅ |
| C2a | `13: rsync -av \` / `34: rsync -av \`（无 --delete） | ✅ |
| C2b | `28: ssh "$NAS_HOST" "rsync -a \`（无 --delete；L26 仅注释提及） | ✅ |
| C3 | `top_keys=24 dims_present=16 missing=[]`；`updated=2026-08-06T06:10:18 global_composite=60.3` | ✅ |
| C4 | `business_tables=8 ['actuals','evaluations','forecasts','narrative_chunks','narrative_density_flags','predictions','reasoning_trace','weight_update_log']` | ✅ |
| C5 | `batch=2026-08-06 processed=True`（triggered_at=14:32:15） | ✅ |
| C6 | `2026-08-06 05:35:19 ... fci_daily.csv`（今日） | ✅ |
| C7 | `updated=2026-08-06T14:42:43 heartbeat_age_s=27`（advisory：job last_run_ts 重启清空，见 §1） | ✅* |
