# 真源注册表（Source of Truth Registry）— world-sim

> 文档类别：实录（RECORD）· 注册表（本表每条可验证，非意图声明）
> 状态：已实施 v1.1（2026-08-06 14:48 CST；初版 14:42 8/8 实测跑通；v1.1 纳入 C 表补充命令 C2b/C7 至 §2.2-2b/7b，10/10 实测跑通）
> 依据：四方向治理论证（docs/governance/四方向治理论证.md）· 方向 A「单一真源 + 记忆降级」P0
> 联动：方向 C Confirmation 验证命令（本表即 C 的验证清单，QA 抽测反作弊）；方向 D 部署通道（docs/governance/deploy-channels.md）；方向 B 文档分治（docs/governance/document-governance.md）；记忆降级（docs/governance/memory-demotion.md）
> 验证通道：**仅 SSH + docker exec（禁 SMB 读/写参与仲裁，案例 8）**；命令全部从真源可执行，期望值独立于实现。

---

## 1. 真相树定位（仲裁前必须先定位，禁跳步）

| 子系统 | 部署模式 | 真相树位置 | 容器名 | 数据挂载（容器内） |
|--------|----------|------------|--------|--------------------|
| 天枢 macro-scan | 热挂载（改 py 即生效，scheduler 改动须 docker restart） | `/vol2/1000/software/macro-scan/核心代码/` | macro-scan-macro-scan-1 | `核心代码`→`/app` (rw)；`data`→`/workspace/data` (rw) |
| 天璇 macro-sim | COPY（真相 = 容器 ≡ 仓库 HEAD；宿主运行区为僵尸副本） | 容器内 `/app/macro_data` ≡ 仓库 `/vol2/1000/software/world-sim` | macro-sim | `data`→`/app/macro_data` (rw) |
| 天玑 macro-tianji | COPY（仓库 build → compose up） | 容器内 `/app/macro_data` | macro-scan-tianji-1 | `data`→`/app/macro_data` (rw)；`config`→`/app/config` (rw) |
| 开阳 kaiyang | nginx 静态（真相 = 运行区 dist） | `/vol2/1000/software/kaiyang/dist/` | macro-scan-kaiyang-1 | 静态目录（scp 覆盖，不清理） |
| 仓库 world-sim | 源码真相（GitHub 单 repo；NAS `/vol2/1000/software/world-sim` 为部署拉取副本） | `/vol2/1000/software/world-sim`，HEAD=`6ba35ab` | — | — |

**数据挂载分叉**：天枢数据在 `/workspace/data`（= 宿主 `macro-scan/data`）；天璇/天玑共享同一宿主文件 `macro-scan/data/forecast_tracker.db`（同 inode，见 §2.2-4/6 实测）。

---

## 2. 真源核心表

> **PG 演进映射（2026-08-06 标注，对接 backlog P2「worldsim-pg 共享状态库」）**：
> 共享状态类真源（#4/#6/#10 及未来 #3 的状态字段）未来迁入独立 `worldsim-pg` 后，真源路径变为 `worldsim-pg.<schema>.<table>`，验证命令存储层 `sqlite3 → psql`，对象/期望/契约不变（治理框架存储无关）。JSON/CSV 采集快照（#1/#2/#5/#7/#8/#9 代码与一次性数据）不迁移。

| # | 对象 | 真相树归属 | 真源路径 | 验证命令（明细见 §2.2） | 期望值 | 口径版本 | 负责人 | 上次验证 | 未来 PG 映射 |
|---|------|------------|----------|--------------------------|--------|----------|--------|----------|-------------|
| 1 | scheduler.py（JOBS 计数） | 天枢运行区 | `/vol2/1000/software/macro-scan/核心代码/scheduler.py`（容器 `/app/scheduler.py`） | ast 解析（§2.2-1） | 元组 50 = 唯一名 47 + weak_signal×4 | 口径 v1（案例6 方法论，2026-08-06） | devops-governance | 2026-08-06 14:42 实测 50 / 47 / weak_signal dup ✅ | 不迁移（代码真源） |
| 2 | deploy.sh（rsync 标志） | 仓库（天璇 COPY 真源 = repo） | `/vol2/1000/software/world-sim/deploy.sh` | grep（§2.2-2） | `--delete` 计数 0；`rsync -av` 计数 2 | 口径 v1（案例7 修复 18d3962） | devops-governance | 2026-08-06 14:42 实测 0 / 2 ✅ | 不迁移（代码真源） |
| 3 | grv_latest.json（键数/维度/新鲜度） | 天枢数据 | `/vol2/1000/software/macro-scan/data/grv_latest.json`（容器 `/workspace/data`） | jq（§2.2-3） | 顶层键 24；维度分数键 17；`updated` = 当日 | schema v1.0（`_schema_version`=1.0） | arch-governance | 2026-08-06 14:42 实测 24 / 17 / updated 2026-08-06T06:10:18 ✅ | 状态字段可选迁移 `worldsim-pg.grv.latest`（JSON 快照保留） |
| 4 | forecast_tracker.db（表计数/行数） | 数据文件（天璇/天玑共享同 inode） | `/vol2/1000/software/macro-scan/data/forecast_tracker.db`（容器 `/app/macro_data`） | docker exec sqlite（§2.2-4） | 业务表 8（+sqlite_sequence=9）；predictions=1、forecasts=289、narrative_chunks=181；actuals/evaluations/weight_update_log=0 **属预期**（唯一预测已 auto-verified，非空转） | schema v1 | arch-governance | 2026-08-06 14:42 实测 9 表 / rows 见 §2.2-4 ✅ | **首批迁移** `worldsim-pg.worldsim.{predictions,forecasts,actuals,evaluations,...}` |
| 5 | control_server.py（last_ok 逻辑） | 天枢运行区 | `/vol2/1000/software/macro-scan/核心代码/control_server.py` | grep（§2.2-5） | L183 真实健康探测存在；硬编码 `last_ok = True` 计数 0 | 口径 v1（案例4 修复） | devops-governance | 2026-08-06 14:42 实测 L183 / 0 ✅ | 不迁移（代码真源） |
| 6 | tianji_trigger.json（processed 状态） | 数据文件（天枢写 / 天玑消费，同 inode） | `/vol2/1000/software/macro-scan/data/tianji_trigger.json`（天玑 `/app/macro_data`） | jq + stat（§2.2-6） | `processed`=true；`last_result.exit`=0；`date`=当日；inode 双端一致 | schema v1（2026-08-06 修复 6ba35ab） | arch-governance | 2026-08-06 14:42 实测 true / 0 / date=2026-08-06 / inode 3241454 双端一致 ✅ | **可迁移** `worldsim-pg.worldsim.tianji_trigger`（触发状态） |
| 7 | FCI 产物（fci_latest.json / fci_daily.csv） | 天枢数据 | `/vol2/1000/software/macro-scan/data/fci_latest.json`、`fci_daily.csv` | stat + jq（§2.2-7） | fci_daily.csv >100KB 且 mtime=当日；fci_latest.json `schema_version`=fci-1.1、`sanity_vs_nfci.status`=PASS、`as_of`=当日 | schema fci-1.1 | arch-governance | 2026-08-06 14:42 实测 109334B / 08-06 05:35 / fci-1.1 / PASS ✅ | 不迁移（一次性数据快照） |
| 8 | 开阳 dist（index.html / data） | 开阳运行区 | `/vol2/1000/software/kaiyang/dist/` | ls（§2.2-8） | index.html 存在；assets/ 存在；data/ mtime 近期 | — | devops-governance | 2026-08-06 14:42 实测 index.html 846B（08-05 15:22）、assets/（08-05 15:22）、data/（08-06 11:12）✅ | 不迁移（前端产物） |
| 9 | 内层 macro-scan deploy.sh（rsync 标志，C2b 补充） | 天枢运行区（≡ 仓库 md5 一致，2026-08-06 实测 e997344b...） | `/vol2/1000/software/macro-scan/deploy.sh` | grep 实际调用行（§2.2-2b） | 实际调用仅 L28 `rsync -a`，**无 --delete**（L26 注释提及 --delete 是历史说明，非标志） | 口径 v1（P0-A 修复 2026-08-03） | devops-governance | 2026-08-06 14:47 实测 L28 `rsync -a`，无 --delete ✅ | 不迁移（代码真源） |
| 10 | scheduler_state.json（调度器存活新鲜度，C7 补充） | 天枢数据 | `/vol2/1000/software/macro-scan/data/scheduler_state.json`（容器 `/workspace/data`） | docker exec python3（§2.2-7b） | `updated`=当日；`heartbeat` 年龄 <300s（调度器存活） | P0-D 契约（DATA_DIR 单点 + 真实健康探测） | devops-governance | 2026-08-06 14:47 实测 updated=2026-08-06T14:47:43 heartbeat_age=33s ✅ | **可迁移** `worldsim-pg.worldsim.scheduler_state`（job 运行记录，配合 C7 落盘持久化） |

---

## 2.2 验证命令明细（全部已实跑，禁止伪命令；命令必须从真源可执行）

### 2.2-1 scheduler.py JOBS 计数（ast 权威解析，禁 grep 缩进正则）

```bash
ssh nas 'docker exec -i macro-scan-macro-scan-1 python3 -' <<'PYEOF'
import ast
p = "/app/scheduler.py"   # 天枢容器内 = 运行区真源（宿主 /vol2/1000/software/macro-scan/核心代码/scheduler.py）
src = open(p, encoding="utf-8").read()
tree = ast.parse(src)
jobs = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "JOBS":
                jobs = node.value
names = [e.elts[0].value for e in jobs.elts if isinstance(e, ast.Tuple) and isinstance(e.elts[0], ast.Constant)]
uniq = sorted(set(names))
print("JOBS 元组数:", len(jobs.elts))
print("唯一 job 名:", len(uniq))
print("重复名:", sorted({n for n in names if names.count(n) > 1}))
PYEOF
```

- 实测输出：`JOBS 元组数: 50` / `唯一 job 名: 47` / `重复名: ['weak_signal']`（weak_signal×4 → 47+4=50）✅
- 期望：元组 50 / 唯一名 47。口径 v1（案例6：ast 唯一名 47 + weak_signal×4 = 50 元组，非 grep 误判）。

### 2.2-2 deploy.sh rsync 标志（仓库真源）

```bash
ssh nas 'grep -c "rsync.*--delete" /vol2/1000/software/world-sim/deploy.sh; grep -c "rsync -av" /vol2/1000/software/world-sim/deploy.sh'
```

- 实测输出：`0` / `2` ✅（deploy_scan L13、deploy_sim L34 均为 `rsync -av`，无 `--delete`）
- 期望：`--delete` 计数 0；`rsync -av` 计数 2。口径 v1（案例7：CHANGELOG v3.8.13 声称已移除 --delete，commit 18d3962 实修）。
- **陷阱提示（QA 实证，C 表 §3.6）**：本命令只覆盖 monorepo 根 `world-sim/deploy.sh`。若对**内层** `/vol2/1000/software/macro-scan/deploy.sh` 跑 naive `grep 'rsync.*--delete'` 会**误报 1 命中**——因为 `--delete` 出现在注释 L26（历史说明"已移除 rsync --delete"），不是调用标志。内层文件的正确检查见 §2.2-2b（只匹配实际调用行）。命令文本未改动，C2 哈希 `16a32111c44c` 保持有效。

### 2.2-2b 内层 macro-scan deploy.sh rsync 标志（C2b 补充命令，命令全文与哈希 C2b 绑定）

```bash
grep -nE '"rsync -a[^"#]*' /vol2/1000/software/macro-scan/deploy.sh
```

- 实测输出：`28:  ssh "$NAS_HOST" "rsync -a \`（仅 L28 实际调用，无 `--delete`；L26 为注释）✅
- 期望：实际调用仅 L28 `rsync -a`，无 `--delete`。口径 v1（P0-A 修复 2026-08-03：曾用 --delete 抹掉未 git add 的 compute_fci.py，现为纯单向同步只增不删）。
- 真相树：天枢运行区 `/vol2/1000/software/macro-scan/deploy.sh`（2026-08-06 实测 md5 `e997344bec497acd06fc37b5a7da8550` ≡ 仓库 `world-sim/macro-scan/deploy.sh`）。
- 命令哈希：`3198ac18a306`（= C 表 C2b，命令全文唯一真源在本表；C 表引用不重写）。

### 2.2-3 grv_latest.json（jq，期望独立于实现）

```bash
ssh nas 'jq "keys | length" /vol2/1000/software/macro-scan/data/grv_latest.json; jq "[keys[] | select(test(\"^(taiwan_strait|us_china_strategic|russia_europe|middle_east_energy|climate_risk|disaster_risk|sanctions_risk|seismic_risk|energy_grid_risk|japan_monetary|social_stress|cultural_friction|south_china_sea|korean_peninsula|india_pacific|global_south|global_composite)$\"))] | length" /vol2/1000/software/macro-scan/data/grv_latest.json; jq -r .updated /vol2/1000/software/macro-scan/data/grv_latest.json'
```

- 实测输出：`24` / `17` / `2026-08-06T06:10:18` ✅
- 期望：顶层键 24（schema 1.0）；维度分数键 17（16 维度 + global_composite）；`updated` = 当日（巡检日 fresh，>24h 视为 stale）。口径 v1（`_schema_version`=1.0）。

### 2.2-4 forecast_tracker.db（容器内 sqlite，天璇/天玑共享同 inode）

```bash
ssh nas 'docker exec -i macro-sim python3 -' <<'PYEOF'
import sqlite3
con = sqlite3.connect("/app/macro_data/forecast_tracker.db")
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("表数:", len(tables))
print("表名:", tables)
for t in ["predictions","forecasts","actuals","evaluations","weight_update_log","narrative_chunks"]:
    print(f"{t}:", con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
con.close()
PYEOF
```

- 实测输出：`表数: 9` / 表名 = actuals, evaluations, forecasts, narrative_chunks, narrative_density_flags, predictions, reasoning_trace, sqlite_sequence, weight_update_log；行数 predictions=1、forecasts=289、actuals=0、evaluations=0、weight_update_log=0、narrative_chunks=181 ✅
- 期望：业务表 8（+sqlite_sequence=9）。**注意**：actuals/evaluations/weight_update_log=0 是**预期状态**（库内唯一 1 条 predictions 已 auto-verified，天玑 verifier 无待验证目标，见 20260806 治理 question 案例 2 修复闭环）；不得凭这三个 0 误报「天玑空转」。若 weight_update_log 在「有新预测且到验证周期」后仍为 0，才构成新事件。
- 口径 v1：表计数以容器内 sqlite_master 为准；行数以 COUNT(*) 为准。

### 2.2-5 control_server.py last_ok 逻辑（天枢运行区）

```bash
ssh nas 'grep -n "last_ok = scheduler_alive" /vol2/1000/software/macro-scan/核心代码/control_server.py; grep -c "last_ok = True" /vol2/1000/software/macro-scan/核心代码/control_server.py'
```

- 实测输出：`183: last_ok = scheduler_alive and bool(job_state.get("last_ok", False))` / `0` ✅
- 期望：L183 真实健康探测存在（`last_ok = scheduler_alive and bool(...)`）；硬编码 `last_ok = True` 计数 0。口径 v1（案例4：P0-D 修复，非硬编码 True）。

### 2.2-6 tianji_trigger.json processed 状态（天枢写 / 天玑消费，同 inode）

```bash
ssh nas 'jq -r ".processed, .last_result.exit, .date" /vol2/1000/software/macro-scan/data/tianji_trigger.json; stat -c "%i" /vol2/1000/software/macro-scan/data/tianji_trigger.json; docker exec macro-scan-tianji-1 stat -c "%i" /app/macro_data/tianji_trigger.json'
```

- 实测输出：`true` / `0` / `2026-08-06`；inode 宿主 `3241454` = 天玑容器 `3241454` ✅
- 期望：`processed`=true；`last_result.exit`=0；`date`=当日；宿主与天玑容器 inode 一致（同一文件，禁双份）。口径 v1（2026-08-06 修复 6ba35ab：scheduler.py tianji_trigger dom=1 → None，每日 09:42 触发；若 date 落后 >1 天即触发部署漂移事件）。

### 2.2-7 FCI 产物新鲜度（天枢数据）

```bash
ssh nas 'stat -c "%y %s %n" /vol2/1000/software/macro-scan/data/fci_daily.csv /vol2/1000/software/macro-scan/data/fci_latest.json; jq -r ".schema_version + \" / \" + .sanity_vs_nfci.status" /vol2/1000/software/macro-scan/data/fci_latest.json'
```

- 实测输出：`2026-08-06 05:35:19 ... 109334 fci_daily.csv`；`2026-08-06 05:35:19 ... 2782 fci_latest.json`；`fci-1.1 / PASS` ✅
- 期望：fci_daily.csv >100KB 且 mtime=当日（>24h 视为 FCI 冻结，案例1 复发信号）；fci_latest.json `schema_version`=fci-1.1、`sanity_vs_nfci.status`=PASS、`as_of`=当日。口径 v1（schema fci-1.1）。

### 2.2-7b scheduler_state.json 调度器存活新鲜度（C7 补充命令，命令全文与哈希 C7 绑定）

```bash
docker exec macro-scan-macro-scan-1 python3 -c "import json,time; d=json.load(open('/workspace/data/scheduler_state.json')); print('updated=%s heartbeat_age_s=%.0f'%(d['updated'],time.time()-d['heartbeat']))"
```

- 实测输出：`updated=2026-08-06T14:47:43 heartbeat_age_s=33` ✅（<300s，调度器存活）
- 期望：`updated`=当日；`heartbeat` 年龄 <300s。口径 v1（P0-D 契约：DATA_DIR 单点 + 真实健康探测）。
- **advisory（QA 实证）**：调度器重启清空 in-memory `_last_run_ts`，job 级 `last_run_ts=None` 属正常（本次 tianji_trigger/grv_update 均 None，因 14:31 重启后未到触发槽）。**本命令只断言调度器存活（updated/heartbeat），不断言单 job 记录**；后续建议把 last_run 落盘持久化，否则无法区分「从未运行」与「重启过」。
- 命令哈希：`b661deed46e1`（= C 表 C7，命令全文唯一真源在本表；C 表引用不重写）。

### 2.2-8 开阳 dist（运行区静态产物）

```bash
ssh nas 'ls -la /vol2/1000/software/kaiyang/dist/; ls -la /vol2/1000/software/kaiyang/dist/data/'
```

- 实测输出：`index.html` 846B（08-05 15:22）、`assets/`（08-05 15:22）、`data/`（08-06 11:12）✅
- 期望：index.html 存在；assets/ 存在；data/ mtime 近期（当日或近 2 日）。口径 v1（案例5：开阳 dist 为运行态真源，源码 commit 与 dist 不符时以 dist 为准判「部署超前」）。

---

## 3. 仲裁优先级表（落地版，引用四方向治理论证.md §方向A）

| 序 | 冲突 | 裁决 | 依据案例 |
|---|------|------|----------|
| 1 | 文档/记忆 vs 运行态 | **运行态赢**，文档判过期→触发记忆降级（memory-demotion.md） | 1/2/3/8 |
| 2 | 运行态 vs 代码真源 | 判**部署漂移事件**，走方向 D（deploy-channels.md） | 4/7 |
| 3 | 天枢 repo vs 运行区 | 运行区（热挂载）赢，repo 为归档 | 案例2 修法 |
| 4 | 天璇 repo vs 宿主运行区 | repo/容器赢，宿主运行区为僵尸副本 | COPY 模式 |
| 5 | 开阳 源码 commit vs dist | dist（运行态）赢，判「部署超前」 | 3/5 |
| 6 | 数据文件 | 容器内 inode 一致为准 | 案例8 / §2.2-6 |
| 7 | 计数类 | ast 权威解析为准，禁 grep 缩进正则 | 6 |
| 8 | SMB | **永不参与仲裁**（读亦不可信，仅 SSH + docker exec） | 8 |

**可执行决策树**：① 定位真相树（§1 表）→ ② 判对象类型（代码/数据/计数/状态）→ ③ 代码按上表 3/4/5 行取真源；数据/计数/状态一律 docker exec 容器内跑 §2.2 命令 → ④ 冲突按上表 1/2 行裁决，产出两类事件：「文档过期」（交 memory-demotion.md 降级）或「部署漂移」（交 deploy-channels.md 收敛）。

---

## 4. 记忆降级规则速查（细则见 docs/governance/memory-demotion.md）

| 层 | 触发降级条件 | 降级动作 | 执行者 |
|----|--------------|----------|--------|
| T1 设计权威 | 被 §2.2 Confirmation 证伪 / 被新 ADR 取代 | 标 `superseded` 指向新真源，降为「历史记录」 | 负责人人工走 PR，AI 仅起草 diff |
| T2 实时状态 | TTL 7 天未复验 / 任一 §2.2 命令失败 | 标 `as-of` 日期移入流水/归档，降为「历史快照」 | AI 自动执行（标 stale） |
| T3 append-only | 历史条目被证伪 | 追加「更正」条目（不删不改原文） | AI 执行 |
| MEMORY.md | 红线**永不降级**；硬事实被证伪 | AI 修订 + 负责人复核，留更正记录 | AI + 负责人 |

**铁律**：降级前必须先按 §3 仲裁表判定真源归属；不得直接凭记忆判文档过期（2026-08-06 治理文档初版即犯此错）。

---

## 5. 使用说明

1. **变更后必跑（diff 触发）**：任何真源对象变更（部署、代码改、数据写入）→ 立即跑 §2.2 对应命令，实测 = 期望才允许合入/宣告完成；不一致先按 §3 仲裁，产出「文档过期」或「部署漂移」事件，禁止静默。
2. **每周巡检（全量）**：每周一全量跑 §2.2 全部 10 条命令（§2.2-1..8 + 2b + 7b）；任一失败即 T2 级 stale 标记 + 转缺陷单。
3. **验证结果记录位置**：本次实测结果已记入本表「上次验证」列（2026-08-06 14:42 8/8、14:47 补 C2b/C7 达 10/10 ✅）。后续巡检结果记入 `docs/governance/verification-log.md`（新增，append-only，格式：日期｜对象｜命令｜实测｜判定），或复用现有 operations 流水；记录必须附 as-of 时间戳。
4. **反作弊**：命令必须从真源可执行、可复制实跑；禁伪命令（2026-08-06 已现虚构 weight_health job 先例）；注册表纳入版本库，QA（qa-governance）随机抽测审计命令真实性；命令与对象版本绑定（口径版本变更 → 命令同步更新，禁静默失败）。
5. **维护权**：注册表维护 = devops-governance；口径版本变更 = arch-governance 评审；抽测 = qa-governance。

---

## 6. 变更记录

| 日期 | 变更内容 | 原因 |
|------|----------|------|
| 2026-08-06 | 初版：真源注册表（8 真源）+ 仲裁优先级表（8 行）+ 记忆降级速查 + 使用说明；8 条验证命令全部 SSH 实测跑通 | 方向 A P0 落地（四方向治理论证 · 单一真源） |
| 2026-08-06 | v1.1：纳入 C 表补充命令 C2b/C7 至 §2.2-2b/7b（核心表 +2 真源行）；§2.2-2 补内层 deploy.sh 注释假阳性陷阱说明；命令哈希与 C 表绑定（3198ac18a306 / b661deed46e1） | 方向 C 联动对齐（QA 反馈：A 未覆盖两条命令 + naive grep 假阳性） |
