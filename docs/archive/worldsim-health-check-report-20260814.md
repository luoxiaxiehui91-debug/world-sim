# 世界推演系统全量健康检查报告（A-G 24 项）

> 检查日期：2026-08-14 09:00-09:45 CST
> 检查团队：MVP 开发专家团（架构师高见远 / QA严过关 / DevOps卜宕机，总监大湾区靓仔编排）
> 依据：`full-check-prompt-20260814.md`（24 项 A-G 组）
> 结论：**22 PASS + 2 FAIL（文档滞后）+ 1 P0（SQLite 定时复生）→ P0 已修复闭环，系统健康**

---

## 一、总体结论

| 维度 | 结果 |
|------|------|
| 代码真漂移（git 真源 vs 运行区 vs 容器） | **零差异**（所有被跟踪 .py 字节一致，sha256 三源相同） |
| PG-only 架构 | **修复后全链路成立**（写路径 6 守卫 + 初始化/读门已补） |
| 数据健康 | 五表稳定（articles=32665 ≥ 阈值）、探针 OK、心跳新鲜、验收 14/14 |
| 备份/恢复 | 每日 04:00 自动备份正常，dump 可读（TOC 85 entries），marker 5h 前 |
| 文档一致性 | **修复后统一**（STATUS/AGENTS P6 口径已同步） |
| 遗留风险 | 2 项 P2 手动工具 + 1 项功能静默降级（均非调度、非阻塞） |

**一句话**：系统处于 E0-C（P1-P6）闭环后的健康状态，本次检查发现并拆除了 1 枚"定时炸弹"（news.db 12:00 复生），零数据影响。

---

## 二、检查矩阵（24 项）

### A 组 拓扑与 PG-only 零残留（DevOps）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| A1 | 容器拓扑 | PASS | macro-scan-tianji-1 (healthy) / worldsim-pg / macro-scan 全 Up |
| A2 | 双源码漂移 | WARN→PASS | 无任何 `Files differ` 行；运行区仅多 17 个 .bak* / NDH6SA~M / qa_result.txt / sql/（部署机制允许） |
| A3 | git 状态 | PASS | status 干净、无未推送 commit |
| A4 | 运行时路径残留 | PASS | software/worldsim 仅命中历史决策文档 |
| A5 | WORLDSIM_SQLITE_OFF | PASS | =1 |
| A6 | 冻结 marker | PASS | .sqlite_frozen_at 存在（08-13 21:37） |
| A7 | 活 .db 残留 | PASS | data/*.db 无文件 |
| A8 | sqlite3.connect 审计 | **FAIL→PASS** | 见第三节 P0 详情 |

### B 组 日志与进程（DevOps）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| B17 | 日志健康 | PASS | 近 12h 无 traceback/error（过滤已知噪声后空） |
| B18 | 心跳 | PASS | mtime 37s 前 < 5min |
| B19 | watchdog | PASS | tianji PID1=verify_watchdog.py state S 非僵尸（/proc 验证，容器无 ps） |

### C 组 数据健康（QA）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| C9 | 五表数据 | PASS | articles=32665 ≥ 32600（日频摄入，非停滞） |
| C10 | forecasts 无 naive | PASS | naive 计数=0；synthesis_log 时区 aware |
| C11 | 探针 | PASS | `OK 0`（22 项全 OK） |
| C13 | market 数据 | PASS | commodity_yahoo 3.5min 前；csi300 -0.57%（真实值）；VIX=14.55 |
| C14 | GDELT 校准 | PASS | gdelt_calib 32min 前；GRV P95 动态值读配置（≠1.243 fallback） |
| C15 | 天玑校准器 | PASS | tianji_verifier 正确调用 run_calibration |
| C16 | news_export | PASS | 09:00 生成，articles=40 |

### D 组 验收工具可信度（QA）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| D20 | final_acceptance | PASS | `FINAL: pass=14 fail=0`；跑后复查无 .db 复生 |
| D21 | verify_reads | PASS | `RESULT: pass=26 gap=0 fail=0`；mode=ro 防复活已生效 |

### E 组 备份与恢复（DevOps + QA 交叉）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| E12 | PG 备份 | PASS | marker 5h 前（<25h）；dump 23M 可读 TOC 85 entries；crontab 04:00 正常 |

### F 组 文档一致性（架构师）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| F22 | STATUS.md | **FAIL→PASS** | 3 处"待观察窗/待删"口径 + item5/item6 自相矛盾 → 已统一"P1-P6 全闭环 + 删库 08-14 08:39" |
| F23 | AGENTS.md | **FAIL→PASS** | 数据架构现状节滞后"待 P6 删 3 库" → 已更新"SQLite 已删（P6 08-14 闭环）" |
| F24 | 探针覆盖 | PASS | PG-only 分支对 SQLite 缺失优雅处理（附 1 加固 WARN：分支条件建议兼容 env 标记） |

### G 组 深度解读（架构师独立实测）

| 解读项 | 结果 | 要点 |
|--------|------|------|
| 双源码漂移 | PASS | 无代码真漂移 |
| SQLite 引用（11 处） | **PASS→FAIL→PASS** | 初判"写路径全守卫"漏检初始化/读门路径 → DevOps 反证成立 → 修复后全链路闭环 |

---

## 三、P0 详情：news.db 定时复生（检查8）

### 问题
P6 删库（08-14 08:39）后，`sqlite3.connect` 对不存在路径**自动创建空文件**。两处无守卫路径被定时任务触发：

| 复生路径 | 代码 | 触发 |
|----------|------|------|
| 路径 A | `scan_weak_signals.py:1502` 无条件调用 `news_db.init_db` → `sqlite3.connect` + `executescript(_SCHEMA)` → **带完整 DDL 的 news.db** | scheduler 每 6h（0000/0600/1200/1800），**12:00 必触发** |
| 路径 B | `signal_synthesizer._check_data_maturity` 直接 `_conn` → `sqlite3.connect` | 每次合成运行（staging 也执行） |

**为什么 08:39 没抓到**：P6 删库时只审计了写函数（news_db 6 处 `if _PG_ONLY` + _write_log/update 守卫齐全），漏了初始化路径（init_db）和读门路径（_check_data_maturity）。且 07:23 弱信号在删库前运行（打开已存在文件，非复生），掩盖了风险。**P0 是"定时炸弹"，12:00 引爆前被拆除，零数据影响。**

### 修复（commit d2d86b0，Fix1-5，已推送）

| Fix | 位置 | 改法 |
|-----|------|------|
| Fix 1 | news_db.py init_db | 顶部 `if _PG_ONLY: return`（早退不创建） |
| Fix 2 | signal_synthesizer._check_data_maturity | 双轨：PG-only 走 pg_read 查 `news.signal_episodes`（EXTRACT(EPOCH)/86400）；非 PG-only 保留原 SQLite |
| Fix 3 | signal_synthesizer._check_resonance | 删 `os.path.exists(db_path)` 历史残留守卫（该函数已只读 PG，存在性守卫导致 PG-only 下共振永久 False） |
| Fix 4 | news_db._conn | fail-fast `raise RuntimeError("PG-only: 禁止 sqlite3.connect，读路径走 pg_read")`（纵深防御） |
| Fix 5 | scan_weak_signals.run_scan | 顶部 PG-only 日志审计 |
| 文档 | STATUS.md / AGENTS.md | P6 口径统一（消除 G22/G23 FAIL） |

### 独立复测（QA 防自证，全部通过）

- `init_db('/tmp/qa_news.db')` → `exists= False`（文件未创建）
- 直接 `_conn('/tmp/qa_news2.db')` → RuntimeError（fail-fast 生效）
- 真实 DATA_DIR 模拟 scan 初始化段 → `.db 列表=[]`（未复生）
- 验收无回归：`FINAL: pass=14 fail=0` + `RESULT: pass=26 gap=0 fail=0` + 跑后复查无 .db
- 12:00 调度路径：scheduler 以 `subprocess.Popen` 独立子进程加载磁盘代码 → 12:00 必然用修后代码（sha 三源一致 1a1d6462/7751844c/3328f538）

---

## 四、遗留项（P2，非阻塞）

| 项 | 位置 | 风险 | 建议 |
|----|------|------|------|
| reconcile 工具守卫 | reconcile_synthesis.py:37 / reconcile_backfill.py:23 | 手动触发即 FileNotFoundError 或复活空库（非调度） | 补 mode=ro + PG-only 早退（参照 verify_reads） |
| daily_narrative 存在性依赖 | daily_narrative.py:25 | 缺失时 `_query_top_news` 静默 return [] 不读 PG（功能降级，不复活文件） | 改直连 PG，去存在性依赖 |
| 探针分支加固 | silent_failure_probe.py | marker 丢失（容器重建/人工清理）时假 CRIT | 分支条件兼容 `WORLDSIM_SQLITE_OFF==1 or marker 存在` |
| 备份残留策略 | data/news.db.bak-c1(25M) / chroma_db_backup(38M) | 与"零 SQLite 残留"字面冲突 | 明确保留策略 |
| 运行区清理 | 17 个 .bak* / NDH6SA~M / qa_result.txt | diff 噪音 | rsync 后清理 |

---

## 五、方法论教训（已沉淀 memory + pitfalls.jsonl）

1. **删库类收尾必须做"全路径守卫审计"**，不只查写函数——初始化（init_db/schema 建表）、读门（_check_data_maturity/_check_resonance 存在性检查）、验收工具（verify_reads）三条路径都可能是复生点。
2. **`sqlite3.connect` 对不存在路径自动建文件是根因**——所有 SQLite 工具类/验收类连接一律 `file:?mode=ro`。
3. **定时调度是复生放大器**——单点漏守卫 + 6h 调度 = 定时炸弹；删库后应加"无活 .db"持续断言（探针/验收脚本自动化守护，不靠人肉）。
4. **防自证**：架构师 PASS 的"写路径守卫"与 DevOps FAIL 的"初始化路径"互补，交叉验证抓到了单方漏检。

---

## 六、团队裁决记录

| 时间 | 事件 | 裁决 |
|------|------|------|
| 09:05 | DevOps 检查8 FAIL（SQLite 复生） | 要求架构师复核（不采信单方证据） |
| 09:10 | 架构师复核：反证成立，结论 PASS→FAIL | 采纳 Fix1-5，派 DevOps 实施 |
| 09:35 | DevOps 修复完成（d2d86b0）+ 自测 5 项 | 派 QA 独立复测（防自证） |
| 09:45 | QA 独立复测全过 | **P0 闭环，系统健康** |
