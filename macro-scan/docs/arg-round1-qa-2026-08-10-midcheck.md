# crucix 退场 · 实施中期全量检查报告（9 commit 独立验收）

- **检查者**：qa-review（未参与实施，独立只读视角）
- **日期**：2026-08-10 18:20-18:40 CST（容器内实测）
- **范围**：9 个实施 commit（a8ffb34 ADR-08 → 5bba73e WP-1.4），7 大检查面
- **红线**：P0 只读核实，未改任何代码/配置/数据
- **结论速览**：**P0 问题 0，P1 问题 2，P2 问题 6**；9 commit 部署一致性与 WP-1.3/WP-1.4 摘除效果验证全部通过

---

## 一、代码一致性（部署纪律） ✅

### 1.1 部署链路
- git repo：`/vol2/1000/software/world-sim`（宏扫代码在 `macro-scan/核心代码/`）
- 生产部署：`/vol2/1000/software/macro-scan/核心代码`（`docker-compose.yml` 挂载为容器 `/app`）
- 部署机制：`deploy.sh` → `rsync -a`（排除 .git/data/logs/__pycache__），git 工作区干净（`git status` 无未提交改动）

### 1.2 md5 一致性（git HEAD == repo == 生产 == 容器 /app）
8 个改动文件全部 **MATCH**：`scheduler.py / fetch_gscpi.py / narrative_processor.py / fetch_climate_signals.py / fetch_firms.py / fetch_safecast_nuke.py / fetch_kiwisdr.py / scan_weak_signals.py`

### 1.3 py_compile
8 个文件容器内 `python3 -m py_compile` **全部 OK**。

### 1.4 备份文件
| 期望 | 实测 | 结论 |
|---|---|---|
| scheduler.py.bak-g0-20260810 | ✅ 存在 | OK |
| scheduler.py.bak-wp02-20260810 | ✅ 存在 | OK |
| scheduler.py.bak-sched-20260810 | ✅ 存在 | OK |
| fetch_climate_signals.py.bak-wp13-20260810 | ✅ 存在 | OK |
| fetch_firms.py.bak-wp13-20260810 | ✅ 存在 | OK |
| **.bak.adr08** | ❌ **缺失** | **P2**（见问题清单 #1） |

> narrative_processor.py 被改动 2 次（ADR-08 删死代码、WP-1.2 接 kiwisdr），但均无 .bak 备份。

---

## 二、crucix 残留扫描（预期 / 意外 / 文档） 

### 2.1 预期残留（已排期，WP 计划覆盖）—— 符合预期
| 文件:行 | 内容 | 排期 |
|---|---|---|
| data_fetcher.py L732-754 | `_crucix` 注入（含 CRUCIX_REMOTE_URL 请求） | WP-2.2 / 3.2 删 |
| regime_detector.py L278-334 | `_crucix.gscpi` 读取 + gscpi_warn/gscpi_value | WP-2.1 改 |
| run_macro_analysis.py L613-2967 | crucix_context 注入 prompt（11 处） | WP-3.2 删 |
| narrative_processor.py L66-70 | crucix_gscpi/nuke/air/sdr 死映射 | AC-D3-01 摘除 |
| source_dimension_map.yaml L80-92 | crucix_* 4 条目 | 随 D3 摘除 |
| optim_config.py L109-110 | CRUCIX_REMOTE_URL 常量 | 随 data_fetcher 摘除 |
| prior.yaml L138 / grv_weights.yaml L143 | `Crucix:` 事件分组标签（语义命名，非功能依赖） | 可选改名（P3） |

### 2.2 意外残留（漏删）—— 仅 1 处 UI 文本（P2）
- `dashboard.py:364`：`数据源：FRED + NeoData + Crucix`（HTML 展示文本）——非功能依赖，WP 未覆盖，摘除后数据源说明不准确。

### 2.3 文档/注释引用（OK，不计残留）
fetch_safecast_nuke.py（复刻依据注释×5）、fetch_kiwisdr.py（零改动声明×2）、fetch_climate_signals.py（D6 摘除说明×2）、fetch_firms.py（替代说明×3）、fetch_rss_news.py:3、news_db.py:7、scheduler.py:88（firms 注释）、scan_weak_signals.py:5（RSS-only 说明）、`.bak-*` 旧版快照×5。

### 2.4 专项验证（WP 摘除效果）
- **WP-1.4（scan_weak_signals）** ✅：当前版**零 crucix 代码**；18:00 扫描（WP-1.4 后首次）走 RSS-only，`[news.db] 文章入库 194 篇，打标签 31 条`，**无任何 crucix 新闻拉取**。
- **WP-1.3（fetch_climate_signals）** ✅：当前版**无 crucix 请求代码**（仅 2 处说明注释）；firms_fire.json 为唯一源。

---

## 三、JOBS 对账（ast 口径） ✅

- **口径**：`ast` 解析 `JOBS` 顶层元组（`name, hhmm, dow, dom, cmd`），非全树遍历。
- **总数 = 53**（与 team-lead 预期一致）。
- **缺脚本 job：无**（53 个 job 引用的 .py 脚本全部存在）。
- **幽灵 job：无**（`weak_signal` 出现 4 次 = 0000/0600/1200/1800 每日 4 扫，同一脚本，正常；无同名指向不同脚本的情况）。
- **关键 job 调度**：
  - `gscpi` → fetch_gscpi.py，0532 每日 ✅（WP-0.2）
  - `safecast_nuke` → fetch_safecast_nuke.py，I60 间隔 ✅（WP-1.2 调度）
  - `kiwisdr` → fetch_kiwisdr.py，0602 每日 ✅
  - `climate` → fetch_climate_signals.py，**dom=None** ✅（G0 修复生效，每日 0910）
  - `firms` → fetch_firms.py，0908（先于 climate 0910）

---

## 四、产物落盘与结构（按 AC 验证）

| 产物 | 位置 | 验收点 | 实测 | 结论 |
|---|---|---|---|---|
| GSCPI.csv | data/fred_history/GSCPI.csv | 尾行 2026-07-31 | **尾行 = `2026-07-31,0.805`** | ✅ 与预期完全一致 |
| safecast_nuke.json | data/ | AC-D1-05/06/07/08/09 | fetched_at=2026-08-10T10:01Z（当日）；6 站全字段；chernobyl 123.96/anom=true；bushehr&yongbyon null/n=0；latest_captured_at 非 None 站点全有 | ✅ 全过（AC-D1-05/07/08 实证通过） |
| sdr_summary.json | data/ | total 839±10% + zones + zones_rule | total=839 online=839（恰好 100% 在线）；zones_rule 含 Taiwan Strait/South China Sea/Ukraine/Baltic bbox；articles=7 条 | ✅ |
| firms_fire.json | data/ | 当日 + 失败态语义 | fetched_at 2026-08-10T09:08、date 当日、total=0、source=NASA FIRMS 直连 | ✅ 结构对（0 值疑义见 P1 #2） |
| climate_signals.json | data/ | ONI + firms 透传 | oni={1.39, 厄尔尼诺, 2026-MJJ}；firms={0, date 当日}；risk 30/中 | ✅ |

- **safecast 6 站数值与 data-review §9.2 MATCH 基线 1:1 一致**（38.28/123.96/null/28.53/29.52），anom 判定 `>100` 语义复现正确。
- **历史归档语义确认**：captured_at 分布 2016-2023（fukushima 2016、dimona 2018、zaporizhzhia 2023-06、chernobyl 2023-07）→ AC-D1-08 已约定不作实时性断言，符合。

---

## 五、调度与运行状态

### 5.1 scheduler_state.json（53 键，与 53 job 对应）
| job | last_ok | last_run_ts | 解读 |
|---|---|---|---|
| safecast_nuke | ✅ True | 08-10 18:00:07 | 当前进程内 I60 触发，**已跑通**（产物 18:01） |
| weak_signal(18:00) | ✅ True | 08-10 18:00:07 | 当前进程内触发 |
| gscpi / kiwisdr / climate | False / None | None | **待明晨首跑**（0532/0602/0910 调度，注册后未到点）——预期 |
| firms / morning / narrative_proc / grv_update / news 等 | False | 今晨有 ts | **重启失真假象**（见下） |

> ⚠️ **last_ok 机制局限（P2 #4）**：`_last_run_ok` 为内存 dict，scheduler 今日 **16:30/16:36/16:55 重启 3 次**（部署 commit 所致），重启前触发的 job 在 dump 时 last_ok 均回退 False。**判定 job 成败必须以 job 日志为准**，不可依赖 state 的 last_ok。

### 5.2 日志实况（关键 job 今日实际成败）
- **morning（07:30）** ✅ 正常运行（输出 GDP 冲击矩阵）——双轨期 crucix 注入符合预期：`[OK] Crucix: gscpi=0.79, nuke=6, sdr=True`，gscpi=0.79<1.5（RSK-1 无触发样本）
- **grv_update（06:10）** ✅ GRV 健康：grv_latest.json updated=当日，17 维度全有值，source_quality=gdelt+gpr
- **scan_weak_signals（00/06/12/18）** ✅ 4 次运行无 Traceback；18:00 起 RSS-only
- **narrative_proc（07:10）** ⚠️ `news.db 读取失败: no such column: summary` → 新闻 0 条（**B7 已知现存 bug**，非 9 commit 引入，见 P2 #6）
- **firms（09:08）** ⚠️ 连续 5 天 0 行（见 P1 #2）
- **news（06:16）** ⚠️ 三方 API key 缺失 → 连续 unavailable（见 P2 #3）

### 5.3 运行噪声（非摘除相关，记录）
- Yahoo 期货 HG=F/GC=F `RateLimited`（市场数据源限流，既有）
- NeoData localhost:28789 Connection refused → 走 FRED 二级回退正常（回退逻辑工作）

---

## 六、QA 门禁预检

### 6.1 G2（gscpi_warn 桩回归）—— **预检 FAIL（P1 #1）**
对 `regime_detector.py:333` 当前逻辑 `((_crucix or {}).get("gscpi") or {}).get("value", 0) > 1.5` 回放：
| 输入 | 预期 | 实测 |
|---|---|---|
| value=1.6 | True | ✅ True |
| value=1.4 | False | ✅ False |
| **value=None** | **False** | ❌ **TypeError**（`None > 1.5`） |
| 缺 gscpi 键 | False | ✅ False |
| 缺 _crucix | False | ✅ False |

> 根因：`.get("value", 0)` 默认值只在**键缺失**时生效；键存在但 value=None 时返回 None → 比较抛异常。当前双轨期 gscpi 有值未触发，但 **WP-2.1 改读 GSCPI.csv 时必须修复（None→False 防护）+ 补回归用例**，否则 G2 门禁 FAIL。

### 6.2 G0（climate 恢复）—— **待观察窗（08-12 后可判）**
- climate job 已恢复（dom=None，0910 每日），scheduler_state 注册确认 ✅
- last_run_ts=None（明晨 09:10 首跑），08-11 晨后复核首跑结果

### 6.3 G1（替代源 5 天完整）—— **待观察窗（08-15 后可判）**
- gscpi：明晨 05:32 首跑；GSCPI.csv 已有尾行 2026-07-31,0.805（开发验证产出）
- safecast：I60 已跑通（18:00 产物），结构验证通过
- kiwisdr：明晨 06:02 首跑

### 6.4 G6（弱信号无 Crucix新闻 新源）
- weak_signal_log 中 08-10 的 `Crucix新闻` 8 条**全部产生于 WP-1.4（17:05）之前**（文件 mtime=16:43，18:00 扫描无新增）
- 自 18:00 起 RSS-only，"连续 4 次扫描无新 Crucix新闻"需等 **08-11 00:00 扫描后**统计

---

## 七、静默降级检查（红线） ✅

| fetcher | 降级路径 | 结论 |
|---|---|---|
| safecast | 每站 5 重试+1.5s 退避；单站失败打日志；**整轮全站失败 → 空 sites + 显式降级日志 + 降级落盘日志**（AC-D1-09） | ✅ |
| kiwisdr | 3 重试+退避；拉取失败/解析失败 → **显式降级日志 + 空结构输出** | ✅ |
| gscpi | 直连失败回退 OUTBOUND_PROXY；CSV 不存在打 `[SKIP]`；异常捕获 | ✅ |
| firms | 全源失败 → **落 0 值失败文件（status=failed）+ ntfy fail-loud 告警**（D6 加固） | ✅ |
| climate | ONI 失败打日志；firms_fire.json 失败态**透传**（status=failed，非静默缺文件） | ✅ |

---

## 八、问题清单（P0 / P1 / P2）

### P1（2 项，需处理）
1. **G2 预检 FAIL：regime_detector gscpi_warn 对 value=None 抛 TypeError**
   - 证据：桩回归回放 `None > 1.5` → TypeError；`regime_detector.py:333`
   - 影响：WP-2.1 改读 GSCPI.csv 后 G2 门禁 FAIL（若 CSV 行值缺失/None 即崩溃）
   - 建议：WP-2.1 实现时 `get("value", 0)` 改为 `(v or 0) > 1.5` 或显式 None 分支；补 1.6/1.4/None 回归用例
2. **fetch_firms 连续 5 天（08-06~08-10）下载 0 行，疑非"真无火点"**
   - 证据：firms.log 5 天均为 `VIIRS_SNPP_NRT: 0 行 / VIIRS_NOAA20_NRT: 0 行 → total=0`；firms_fire.json 无 status=failed（未走全源失败路径）
   - 影响：G7（climate 当日产出）以 firms 为唯一源，若源端持续 0 行则门禁与真实火点信号双重受损；RSK-4 已预见"全球 CSV 下载慢问题待修"
   - 建议：data-review 核实 NASA FIRMS 下载 0 行根因（空响应/代理拦截/格式），区分"真无火点"与"下载失败"；必要时修下载逻辑

### P2（6 项，记录/跟进）
1. **`.bak.adr08` 备份缺失**（narrative_processor.py 改动 2 次均无 .bak）——git 可完整恢复，属纪律瑕疵
2. **dashboard.py:364 展示文本残留** `数据源：FRED + NeoData + Crucix`——UI 文本，WP 未覆盖，建议 WP-3.x 顺带清理
3. **fetch_news.py 三 API key 缺失**（MarketAux/Currents/Sugra）→ news_risk.json 连续 unavailable——既存配置缺口，非 9 commit 引入，新闻主链路走 RSS 不受影响
4. **scheduler_state last_ok 重启失真**（内存态，重启 3 次后历史 job 显示 False）——判定须以 job 日志为准
5. **sdr zones 维度与 narrative 映射不一致**：zones_rule 中 Taiwan Strait→taiwan_strait，narrative 中 kiwisdr_sdr→global_composite——独立增强项，观察（OB-SDR）
6. **narrative_proc news.db `no such column: summary`（B7 已知）**——narrative 新闻 0 条，D3 验收基线不干净，建议摘除实施时顺带修复（跟随项）

### 非问题（预期行为）
- morning 双轨期 crucix 注入（gscpi=0.79/nuke=6/sdr=True）——WP-2.x 前预期
- 08-10 弱信号中 Crucix新闻 8 条——WP-1.4（17:05）前扫描产生，18:00 起已无
- prior.yaml / grv_weights.yaml `Crucix:` 分组标签——事件语义命名，非功能依赖

---

## 九、验证通过项汇总

- ✅ 8 文件 md5 三源一致（git==repo==生产==容器）+ py_compile 全过
- ✅ JOBS=53（ast 顶层口径），无缺脚本、无幽灵 job、climate dom=None 恢复
- ✅ GSCPI.csv 尾行 2026-07-31,0.805
- ✅ safecast_nuke.json 6 站全字段 + MATCH 基线复现 + latest_captured_at 全有
- ✅ sdr_summary.json total=839/online=839 + zones_rule + articles（narrative 接线 SOURCE_MAP L71 / json_sources L390 已确认）
- ✅ firms/climate 产物结构当日、失败态语义明确
- ✅ WP-1.3（climate 无 crucix 代码）、WP-1.4（scan 18:00 RSS-only 无 crucix 新闻）实证通过
- ✅ 静默降级：5 个 fetcher 全部有显式降级日志/失败文件
- ✅ GRV 健康（updated 当日、17 维度、source_quality gdelt+gpr）
- ✅ news.db 31229 篇，近 1 天 3972 篇，日增量无骤降（G3 风险低）
- ✅ scan_weak_signals 今日 4 次运行无 Traceback

---

## 十、后续观察点（08-11 晨复核）
1. gscpi 0532 首跑 → GSCPI.csv 更新、scheduler_state last_ok 变 True
2. kiwisdr 0602 首跑 → sdr_summary.json fetched_at 更新
3. climate 0910 首跑（G0 修复后首次）→ climate_signals.json ONI 刷新
4. firms 0908 → 确认 0 行是否为源端问题（P1 #2 跟进）
5. 00:00 扫描后统计：弱信号连续扫描无新 Crucix新闻（G6 起点）
