## [3.8.47] - 2026-09-11

### Changed（开源收尾，全量检查发现项清理，CHG-20260911T104000-world-deduction）

- **3 处 Windows 路径注释脱敏**（阶段 2/4 路径参数化的遗漏）：`fetch_bdi.py:16` `S:\world-sim\macro-scan\data\` → `<仓库根>/macro-scan/data/`；`fetch_spacetrack.py:4,40` `S:\KEY\Space-Track*.txt` → `<你的密钥文件>`。**后两处暴露密钥文件存放位置**，优先级最高。
- `docs/check-doc-links.py` 的 `S:\docs\INDEX.md` **保留不改** —— 它属 `BAD_TOKENS` 坏链接检测规则本身，非路径引用，改动会使脚本失效；且不含用户名与凭证。
- 删除阶段 5「从零 clone 实测」目录 `_fresh_clone_test`（133 MB）—— 其中 3 份 `.env` 在步骤 8 注入了**生产真实凭证**（未入库、未进历史，但属散落的凭证副本，与「凭证唯一来源」纪律相悖）。

### 验收

- `git grep` HEAD 代码/配置中 Windows 路径与内网信息命中：改前 **4 处** → 改后 **1 处**（仅上述检测规则）
- 两个改动文件 `py_compile` 通过；**注释级改动，无逻辑变化**，不影响运行区（该目录为 git 真源，运行区经 rsync 同步，本次无需同步）
- 测试目录已删，磁盘回收 133 MB

### 已知限制

- **`.git` 130.67 MiB 未 gc**：force push 后 `git fetch` 将旧历史对象一并拉回本地（2 个 pack / 10640 对象），gc 可回收约 66 MB，但会失去本地旧历史副本。**刻意保留** —— 回滚仍有 `_backup_worldsim_20260911T093827`（552 MB）整仓备份兜底。

## [3.8.46] - 2026-09-11

### Fixed（从零 clone 实测，开源实施计划 阶段 5，CHG-20260911T081125-world-deduction）

- **`macro-scan/Dockerfile` pip 源 tuna → aliyun**：`mirrors.tuna.tsinghua.edu.cn` 在本网络不可达，`requests==2.33.1` 报 `No matching distribution found`，导致 `docker build macro-scan/` 必然失败（同批 macro-ji / macro-sim 用 aliyun 源均成功，容器内已装 2.33.1、PyPI 官方源亦有）。`ARG PIP_INDEX_URL` 默认值形式不变，海外仍可 `--build-arg` 覆盖。
- **补两处 compose 插值变量到 `.env.example`**：`macro-scan` 补 `SILICONFLOW_API_KEY`，`macro-ji` 补 `KAIYANG_ORIGIN`。修复前 `compose config` 报 2 条 `variable is not set`，会让从零使用者误判配置错误。
- 根 `README.md`：补 pip 源 / 基础镜像覆盖说明与实测环境提示。

### 验收（干净目录从零 clone 实测，目录 `_fresh_clone_test/world-sim`，HEAD=94bc47e）

| 步骤 | 结果 |
|---|---|
| clone 盘点 | 21 个关键文件到位；`.env` / `知识库/` / `data/` / `kaiyang/dist` 均不存在（阶段 3 隔离性生效） |
| 2 知识库骨架 | `scripts/init_kb.py` ✅ 14 文件 |
| 3 环境变量 | 三份 `.env` 生成；生产有值键 20 个、`.env.example` 覆盖 19，`MACRO_SCAN_DIR` 仅 macro-ji 需要且已在其 example 中，**非缺口** |
| 4 数据库 | `scripts/init_db.sh` 退出 0，21 张表，`vector 0.8.2` |
| 5 前端构建 | `npm ci` 42s + build 96s，dist 11 文件 6.2M（需把 node 所在目录加入 PATH，属本机环境问题） |
| 6 镜像构建 | macro-ji ✅ / macro-sim ✅ / **macro-scan ✅（本次修复后复验通过）**，`requests 2.33.1` 装上 |
| 7 compose config | 三份 exit 0 且 **0 警告**（修复前 2 条 `variable is not set`） |
| 8 启动 | 依赖冒烟 DEPS OK；Web 控制台 200、Control API `/docs` 200、uvicorn 启动完成 |

### 已知限制

- 步骤 8 用 `!override` 改隔离端口 18999/18900 且**只起 web/control、未启 scheduler**（生产占用 8899/8900，起第二份 scheduler 会重复跑定时任务并写生产库）→ 「完整 `docker compose up -d` + 跑一次采集/分析」尚未实测。
- 注入层不完整（55/77 变量未在 compose `environment:` 声明）仍为独立 backlog，改 `env_file` 属行为变更，待单独评估。
- 46 MB wheel `zh_core_web_sm-3.8.0` 仍在仓库；知识库 618 文件与研报仍在 git 历史中 → 阶段 6（filter-repo）待拍板。

## [3.8.45] - 2026-09-11

### Added（可运行性，开源实施计划 阶段 4，CHG-20260911T004121-world-deduction）

- **新增 `scripts/init_db.sh`**：数据库初始化统一入口。一条命令完成：创建 Docker 网络 → 启动 `pgvector/pgvector:pg16` → 建库与角色 → 按序执行 4 个建表 SQL（覆盖 `public` / `news` / `forecast` / `tianji` / `rag` 五个 schema）→ 校验。幂等，不覆盖已有密钥文件；应用密码唯一来源为 `macro-scan/.env`。

### Changed

- **根 `README.md` 重写为开源版**：项目简介 / 能力表 / 组件表 / 架构图（mermaid）/ **8 步 Quick Start** / 配置参考 / 知识库说明 / 文档导航 / 免责声明。移除全部私有环境信息（内网 IP、NAS 绝对路径、Windows 路径、`private` 标注，实测命中 0）；版本号不再硬编码。
- **3 个 Dockerfile 参数化**：新增 `ARG BASE_IMAGE`（默认 `docker.1ms.run/library/python:3.11-slim`）与 `ARG PIP_INDEX_URL`（默认国内加速源），**默认值不变**；海外使用者可用 `--build-arg` 切回官方源。
- **补 3 份 `.env.example` 缺失的 compose 插值变量**：`macro-scan` 加 `KAIYANG_DIR`，`macro-ji` / `macro-sim` 加 `MACRO_SCAN_DIR`（阶段 2 参数化 compose 时遗漏说明，会导致从零 clone 启动失败）。
- 子项目 `README.md` ×4 与 `docs/overview.md` 的私有环境信息通用化（26 处 → `<主机地址>` / `<部署目录>` / `<仓库根>` / `<你的密钥文件>`）。

### 验收（实测）

- 根 README 私有信息命中 **0**；引用的 8 个文件全部存在；mermaid 块闭合
- `init_db.sh` `bash -n` 通过，行尾 LF
- Dockerfile 复验：3 个文件的 `ARG` 声明与变量引用齐全，未参数化的 pip 行 **0**；实测 `docker build macro-ji/` 成功
- 全仓库代码/配置（`*.py` / `*.sh` / `*.yml` / `*.ts` / `*.tsx`）内网信息命中 **0**（保持阶段 2 成果）

### 已知限制

- `docs/` 与子项目的历史文档（CHANGELOG / 审查 / 决策记录，共 70 个文件）仍含内网事实，属审计链原貌，未改动。
- 天玑容器内的 `verify_hypothesis.py` 为 `docker cp` 注入，未持久化进镜像（默认路径不变，功能正常）。
- 本版本 Quick Start 尚未经「从零 clone」实测（属阶段 5），可能存在与实际不符的步骤。

## [3.8.44] - 2026-09-10

### Changed（知识库外置，开源实施计划 阶段 3，CHG-20260910T234442-world-deduction）

- **知识库移出 git 追踪**（617 文件 / 22 MB）。原因：内含 4 个文件为券商研报全文（16 家机构、含免责声明与「未经授权不得复制或引用」条款），属第三方版权内容。`git rm -r --cached` + `.gitignore`，**磁盘文件完整保留**（实测 617 个仍在，运行区 702 个未受影响）。
- **12 处 KB 路径支持 `KB_ROOT` 环境变量**：形式为 `os.environ.get("KB_ROOT") or <原默认表达式>`，未设时取值与改造前**完全一致**。涉及 `build_rag_index` / `mc_engine` / `optim_config` / `run_macro_analysis` / `scorer` / `update_kb_numbers` / `assess_structural_dimensions` / `calibrate_mc` / `monte_carlo_v2` / `daily_narrative` / `weekly_synthesis` / `macro-ji·verify_hypothesis`。
- **缺失引导**：`build_rag_index.py` 与 `assess_structural_dimensions.py` 的缺失分支由静默降级升级为明确提示（指向 bootstrap 脚本与文档）。
- **新增 `scripts/init_kb.py`**：生成知识库骨架（14 个示例文件，**零第三方内容**），支持 `--dest` / `--force` / `--list`。
- **新增 `docs/KB_SETUP.md`**：目录约定、各文件格式要求（含 CSV 21 列顺序）、`KB_ROOT` 用法、RAG 索引构建、缺失降级说明。
- `macro-scan/.env.example` 补 `KB_ROOT` 与 `OPENCLAW_WORKSPACE` 说明。
- `tests/test_audit_scan_secrets_guard.py`：对知识库内文件加存在性跳过（未初始化知识库时属预期情况，不再判失败）。

### 验收（实测）

- `git ls-files` 中知识库命中 **0**；磁盘 617 文件、运行区 702 文件均完好
- 容器内默认路径解析 = `/workspace/知识库/财经知识库`，目录与文件均存在
- **功能零退化**：`mc_engine._load_vol_calibration()` 读到 11 个条目；`scorer.CRISIS_CSV` 读到 41 行
- `KB_ROOT` 覆盖生效；指向不存在路径时输出 bootstrap 引导并以退出码 **1** 结束
- `init_kb.py` 生成 14 文件；CSV 21 列、JSON/YAML 均可解析；8 个 `.md` 可进 RAG 索引
- `py_compile` **14/14** 通过

### 已知限制

- **git 历史中仍有知识库内容**，需 filter-repo 清理（另行 CHG）。
- 天玑（macro-ji）容器内 `verify_hypothesis.py` 未同步（默认路径不变，功能正常），下次重建时生效。
- 知识库自身存在新旧编号目录并存（8 对目录内容高度重叠），属使用者个人资产整理，不在本次范围。

## [3.8.43] - 2026-09-10

### Changed（路径参数化，开源实施计划 阶段 2，CHG-20260910T232600-world-deduction）

- **compose 挂载去硬编码**：同目录挂载改相对路径 `./`（Docker 以 compose 文件所在目录为基准，与原绝对路径**等价**，外部使用者 clone 后零配置即可）；跨项目引用改 `${MACRO_SCAN_DIR}` / `${KAIYANG_DIR}`；`RSSHUB_URL` / `OUTBOUND_PROXY` 由字面量改 `${VAR}`。
- **代理默认值去内网**（19 处）：`PROXY_URL` / `NAS_PROXY_URL` / `GDELT_PROXY` 的默认值 `http://192.168.x.x:7890` → 空串（含 5 处 `os.environ.get` 与 18 处 `except ImportError` 降级表）。真值改由运行区 `.env` 提供，并补齐 compose 注入（此前这些变量**未在 environment 段声明**，配了 `.env` 也进不去容器）。
- **代码路径常量**：`etl_ged` / `ged_analysis`（GED CSV 路径）、`llm_usage`（数据目录）、`macro-sim/llm_client`（key 文件）、`scripts/check_llm_config`（仓库/运行区定位）、`verify_data` / `delete_sqlite_e0c.sh` / `ged_codebook_extract`（含 `C:/Users` 本机路径）。
- **开阳前端**：`DEFAULT_API_BASE_URL` 由写死内网 IP 改为按当前访问主机推导；**信任来源白名单机制保留**（仍为 Set 白名单，仅将静态内网 IP 改为动态取当前 hostname，未退化为通配）。
- **部署脚本归置**：作者环境专用脚本（含 NAS 地址与 `ssh nas`）移入 `scripts/dev/` 并参数化；通用基础设施脚本（`infra/pg/`）参数化后保留原位。

### 验收（实测）

- 非知识库的代码/配置内 `/vol2/1000`、`192.168.31.108`、`C:/Users`、`S:/2026` 命中 **0**（知识库内 10 处随阶段 3 数据外置一并消失）
- 容器 `up -d --force-recreate` 后：挂载 **5/5 实证生效**（容器内可见宿主文件）、control API / web server / 开阳面板均 **HTTP 200**、`py_compile` 与 `bash -n` 全通过
- 代理链路保持（真值落入运行区 `.env` 并成功注入容器）

### 已知限制

- `MACRO_SCAN_DIR` / `KAIYANG_DIR` 仅用于 compose 的 volumes 插值，**不注入容器**（属正常，非缺陷）。
- 发现仍有 **55 个变量代码读取但 compose 未注入**（本阶段只补齐代理类 4 个），属独立的注入层完整性问题，另行处理。

## [3.8.42] - 2026-09-10

### Security（ntfy 主题名轮换 + 注入层环境变量化，开源前置，CHG-20260910T181638-world-deduction）

- **ntfy 两个主题名轮换为 32 位随机串**（告警 / 命令频道各一个）。原主题名长期硬编码在 6 个被跟踪文件中，且代码走 `https://ntfy.sh/` 公共服（匿名可读可写，实测匿名 GET 即返回真实推送正文）→ 主题名一旦随开源公开，任何人可订阅告警、可向命令频道发指令。轮换后旧名自动作废。
- **主题名改为环境变量注入**：`NTFY_TOPIC` / `NTFY_CMD_TOPIC` / `NTFY_URL` 三个 compose 项由字面量改为 `${VAR}`，真值落运行区 untracked `.env`（600）→ **新主题名零字符入库**（提交前 `git grep -lF` 校验命中 0）。与既有 `NTFY_CMD_SECRET` 的注入方式对齐。
- **去掉 5 个 .py 中的硬编码默认值**：`macro-scan/核心代码/observability.py`、`macro-scan/核心代码/weight_matrix.py`、`macro-ji/tianji_verifier.py`、`macro-ji/weight_matrix.py` 的 `os.environ.get("NTFY_URL", "https://ntfy.sh/<旧名>")` → 默认空串；`macro-sim/run.py` 的纯字面量赋值 → `os.environ.get("NTFY_URL", "")`。并给 `macro-sim/docker-compose.yml` 补 `NTFY_URL=${NTFY_URL}` 注入（该文件原本既无 env_file 也无该变量，否则改造后天璇推送为空值）。
- **16 个 md/html 文档中的旧主题名 → `$NTFY_TOPIC` / `$NTFY_CMD_TOPIC` 占位符**（合计 34 处）：文档只描述机制，不再含具体频道名。
- **`.env.example` 补 `NTFY_TOPIC=` / `NTFY_CMD_TOPIC=` 空值模板**。

### 实测

- 运行区 `.env` 写入后复核 3 处全 OK（权限 600）；`docker compose up -d --force-recreate` 后容器内 `NTFY_TOPIC` / `NTFY_CMD_TOPIC` / `NTFY_URL` 均为新值（非旧名）。
- 双频道直连 POST 均 HTTP 200（`event=message`），告警频道 GET 可读。
- ⚠️ **代理对 ntfy.sh 的 HTTPS 不稳定**：经 `192.168.31.108:7890` 的 POST/GET 实测返回 000（`SSL_ERROR_SYSCALL`），直连正常 —— 与 `ntfy_listener.py` 既有注释一致，非本次引入。

### 已知限制

- 手机端 ntfy App 需手动删除旧频道、订阅新告警频道；命令频道改为向新频道发送。
- `macro-sim`（天璇）为 COPY 型部署，**本次未重建镜像**，其 `run.py` 改动待下次自然重建方生效；当前容器内仍是旧代码（纯硬编码）→ 天璇 ntfy 推送暂用旧主题名（旧名仍可用，不中断）。

## [3.8.41] - 2026-09-09

### Fixed（展望简报索引刷新遗漏，v3.8.40 晨间首验发现，CHG-20260909T080058-macro-scan）

- **展望简报落盘后就近刷新开阳报告索引**。v3.8.29 引入的「报告落盘后就近触发 `generate_reports_index.py`」机制（修 07:35 索引抢跑导致当日报告空窗）**原本只覆盖 `save_report`（宏观分析报告）**；而展望简报在主流程中于 `save_report` **之后**才落盘，落盘后无任何刷新动作 → 当日简报最长卡在 **07:35 → 20:35 约 13 小时空窗**、开阳报告中心「30天展望」分组看不到当天份。
- 修法：把该机制抽成模块级函数 `_refresh_kaiyang_reports_index()`（行为不变：subprocess 调 `generate_reports_index.py`、`timeout=180`、失败仅 WARN 不阻断），`save_report` 与**展望简报落盘后**两处共用（DRY）。
- 实测：`reports_index.json` 175 → **176** 条，类型 `30天展望` 65 → **66**，今日 `30天展望简报_20260909_both.md` 即时入库；import 模块无副作用（函数体正确缩进，未退化为模块级执行）。

### 晨间首验（v3.8.40 上线后第一个调度周期）

- 03:10 `reports_ttl_cleanup` 首次真实调度跑通：`分析报告 130 份 / 仿真报告 43 份，超期 0`，无异常（90 天窗口内本就不会删，首次真实删除预计 2026-11 中下旬）。
- 07:30 晨间宏观分析产出 `30天展望简报_20260909_both.md`，新命名生效，源目录旧名残留 **0**。
- 近 12 小时 macro-scan 日志**零** traceback / ERROR / fail；容器 RestartCount **0**。
## [3.8.40] - 2026-09-08

### Added（P3 / question monthly-outlook-daily-and-no-ttl 方案C「改名 + 报告TTL」，CHG-20260908T232303-macro-scan）

- **新增 `reports_ttl_cleanup.py`：报告文件 TTL 清理**。扫**源目录** `docs/分析报告` + `docs/仿真报告`，删除超期 `.md`，默认保留 **90 天**（与 news TTL 同口径，`REPORTS_TTL_DAYS` 可覆盖），支持 `--dry-run`；日期判定「文件名日期优先（`YYYY-MM-DD` / 紧凑 `YYYYMMDD`）→ mtime 兜底」，异常仅记日志不阻断。调度每日 **03:10**（错开 `news_ttl_cleanup` 03:00）。副本 `data/reports/` 与 `reports_index.json` 由既有 `reports_index` 任务（0735/2035）自行同步，TTL 脚本不重复负责。

### Changed

- **「月度简报」改名「30天展望简报」**（`月度简报_{YYYYMMDD}_{country}.md` → `30天展望简报_{YYYYMMDD}_{country}.md`）：产物语义本就是滚动 30 天展望（警戒级别 / 指标快照 / 反馈回路 TOP3 / 地缘快照 / 阈值红绿灯 / 30 天观察日历），但生成动作挂在每次宏观分析末尾（每工作日 3 次：07:30 both / 20:00 us / 20:15 china），「月度」命名与日频×3 的实际严重错配。改动点：`run_macro_analysis.py`（文件名模板 + 日志标签 + 正文 H1）、`generate_reports_index.py`（类型改 `30天展望`，关键词保留 `月度简报` 兜底）、`dashboard.py`（glob pattern + 卡片标题）。
- **一次性数据迁移：历史 65 份 `月度简报_*` 重命名为 `30天展望简报_*`**（脚本执行，残留旧名 0，副本由 `generate_reports_index` 同步清理）。历史文件**正文不改**（保留原貌，随 TTL 自然淘汰）。

### 已知限制

- 90 天窗口内不会出现实际删除（现有报告最早 2026-08-10），首次真实清理预计 2026-11 中下旬触发。
- 历史简报正文 H1 仍为「月度宏观简报（Executive Briefing）」（新产出已改为「30天展望简报（Executive Briefing）」）；dashboard 卡片标题与正文 H1 重复属既存行为，本次未改。
## [3.8.39] - 2026-09-08

### Added（P2 / question fred-japan-jgb-lag-probe-spam 解法A「MOF 日频源治本」，CHG-20260908T203337-macro-scan）

- **新增 `fetch_mof_jgb.py`：日本 10Y 国债日频源（日本财务省 MOF）**。FRED 上 `IRLTLT01JPM156N` 仅有 OECD 月/季/年系列（无日频版本，2026-09-03 频率筛选已核实），官方最新长期滞留在 `2026-06-01`（滞后约 99 天）。MOF 提供**公开无鉴权** CSV：`jgbcme.csv`（Current，仅当月）+ `historical/jgbcme_all.csv`（1974~，全量日频 1.2MB / 13k 行）。**每次两源都拉并取并集**（同日期 current 覆盖 all），规避 current 月度文件跨月重置导致的丢数风险。解析按表头名定位 `10Y`（不硬编码列下标）、日期 `YYYY/M/D` 补零规整、跳过休市空行与 `-` 值。
- **写入范围只补本地末行之后**：既有 450 行 FRED 月度历史（1989~2026-06）保持不变，MOF 仅追加 `2026-06-02` 起的新日期 —— 避免把月频历史改写为日频而污染回测与窗口语义。**口径切换点 = `2026-06-02`**（此前 OECD/FRED 月频，此后 MOF 日频，口径略有差异，跨期对比需注明）。
- **失败语义（沿用 spacetrack 教训）**：HTTP/解析失败 → 单源失败降级继续（另一源仍可用）、双源均失败 `raise` 并非零退出，**保留上次成功值、不写 0**；写前自动备份 `IRLTLT01JPM156N.csv.bak-<时间戳>`，按 date 去重（keep=last）+ 排序 + `tmp → os.replace` 原子写回。
- **调度**：`scheduler.py` JOBS 新增 `mof_jgb` 日档 **05:38**（排在 `fred_fetch` 05:30 之后、`fred_freshness` 05:40 与每 2h 的 `silent_probe` 之前）。
- **探针条目**：`silent_failure_probe.FRED_LAG_WATCH` 日债条目备注 `日债 10Y(月)` → `日债 10Y(MOF日频)`，`max_lag` **90 → 10**（保留 90 会让「数据又停滞 3 个月」再次静默 3 个月才告警 —— 这正是本次要治的病）。

### 验收

- 语法 + 容器内实跑：`450 → 518 行`，新增 68 行（`2026-06-02` ~ `2026-09-07`，末值 `2.935`）；**二次连跑 0 新增**（去重生效，行数不变）
- 失败态（容器内 mock）：单源坏 → 降级由另一源完成；双源坏 → `BOTH_FAIL_RAISE_OK`，CSV 行数与末行**不变**（519 / `2026-09-07`），不写 0
- 探针 dry：`[OK] fred 日债 10Y(MOF日频): 最新 2026-09-07，滞后 1 天（阈值 10）`（切换前为滞后 99 天告警）
- 部署：commit `0675631` → rsync → md5 真源=运行区一致（`ad739cae…` / `df4d2746…`）→ `docker restart` → Up；`JOBS` 含 `mof_jgb`（05:38），`OUTBOUND_PROXY` 未丢

### 注意

- 每日拉全量 1.2MB（低频、无鉴权），对 MOF 无实质压力；容器内**直连即通**（代理仅作回退兜底）。
- `scan_weak_signals.scan_japan_carry_risk` 仍**实时调 FRED**（第 578 行，不读本地 CSV），本次换源后该信号仍用 OECD 滞后值 → 转 backlog（改动需评估月频+日频混合序列下 `vals[-4]` 的「3 个月」窗口语义漂移）。

## [3.8.38] - 2026-09-08

### Fixed（P2 / backlog「fetch_spacetrack 登录校验与失败态（开阳清零掩盖层）」，CHG-20260908T192626-macro-scan）

- **`_get_session` 登录校验响应体**：Space-Track 对错误凭证返回 **HTTP 200 + `{"Login":"Failed"}`**（非 4xx），旧逻辑仅判断 `status_code != 200` 会误判登录成功，错误推迟到下游查询才以 401 暴露——这正是开阳宇宙监视静默清零 10 天 / 40 次 401 零告警的直接掩盖层。现增加响应体校验：body 解析为 JSON 且含 `Login` 键即 `raise RuntimeError` 并附 body 前 200 字符。登录成功时 body 为空串，不受影响。
- **`collect()` 失败态（禁止粉饰）**：`"status"` 由硬编码 `Status.OK` 改为按查询结果判定——核心查询 `all_active is None` → `Status.UNAVAILABLE`；核心成功但子查询有 `None` → `Status.PARTIAL`；全部成功 → `Status.OK`。新增 `error` 字段记录失败摘要；**非 OK 时沿用上次成功值**（读旧 JSON 的数值字段），避免面板显示 0 造成"清零"式误导；无旧文件时才写 0。
- **`limit` 截断修正（数值口径变化）**：实测 `all_active` 原 `limit=30000` 返回恰好 30000（= limit，截断）、`starlink` 原 `limit=10000` 返回恰好 10000（截断），OneWeb 654 未触顶。现 `all_active` → `limit=100000`（`_query` 新增 `timeout` 参数，该调用设 120s）、`starlink`/`oneweb` → `limit=30000`。**面板数值修正为真实值：`total_active` 30000 → 35048、`starlink` 10000 → 11083**（`by_type` 与 `military_large_payload` 同步变化）。
- **探针新增 `check_feed_status`**：独立复核 `data/spacetrack.json` 的 `status` 字段，`unavailable` → CRIT、其余非 ok → WARN，并进 ntfy。**复用 `check_fred_lag` 的 notified-state 冷却**（同一 state 文件、key 前缀 `feed:`），状态指纹未变则降级 INFO 不重复推送，恢复 ok 后自动清标记。已注册进 `run_probe`。

### 验收

- `python3 -m py_compile fetch_spacetrack.py silent_failure_probe.py` → `SYNTAX_OK`
- **登录校验（容器内 mock）**：HTTP 200 + `{"Login":"Failed"}` → `raise`（旧代码会误判成功）；HTTP 200 + 空 body / `{}` → 正常通过未误伤；HTTP 500 → 仍拦截
- **探针冷却（隔离环境）**：`status=unavailable` 三连跑 → `CRIT` / `INFO`（已通知过，状态未变）/ `INFO`；置回 `ok` → `OK` 且 state 键清除；`status=partial` → `WARN`
- **生产实跑 `fetch_spacetrack.py`**：`写入 ... active=35048`，落盘 `status=ok` / `error=null` / `starlink=11083` / `oneweb=654` / `payload=19434` / `debris=12521`（对比备份旧值 `active=30000` / `starlink=10000`）
- **探针 dry**：新增 `feed 开阳宇宙监视(spacetrack): status=ok`，`checks=34`（新增 1 项）
- **部署**：commit `ab117e0`（改码）→ rsync → md5 真源=运行区一致（`540d3912…` / `36bc5c80…`）→ `docker restart` → Up

### 注意（数值口径）

本次为**修正为真实值**，非故障：`total_active`、`starlink` 及派生的 `by_type`、`military_large_payload` 均会上升，开阳宇宙监视面板数字将出现一次性跳变。

## [3.8.37] - 2026-09-08

### Fixed（P2 / question kaiyang-spacewatch-spacetrack-zeroed，CHG-20260908T130113-macro-scan）

- **Space-Track 凭证转义污染修正（开阳「宇宙监视」清零根因）**：`macro-scan/.env` 第 11 行 `SPACETRACK_PASS` 实际值为 16 字符，比 `S:\KEY\Space-Track KEY.txt` 正确值**多一个反斜杠** —— 写入时 `!` 被转义为 `\!`。该错误值经 compose 注入容器，导致自 2026-08-30 起连续 10 天（40 次）SATCAT 查询返回 401，开阳面板全 0。**修正**：Python 精确替换（不经 shell）+ 备份 `.env.bak-20260908T130113`（600）+ `docker compose up -d --force-recreate` 重新注入 env。
- 根因更正：此前判断的「Space-Track 外部账号/凭证失效」**不成立**，Space-Track 账号与本地 KEY 均有效，纯属我方配置写入污染。

### 验收

- 三方非明文对拍：本地 KEY `len=15 sha16=6b8ad45ee4b93922` vs `.env` `len=16 sha16=ff500d0f24c6a028`；字符类别序列定位到 index 2 多插入一个符号
- 实测两套凭证：`LOCAL_KEY` 登录 body=`""` → 查询 HTTP **200**；`.env` 登录 body=`{"Login":"Failed"}` → 查询 HTTP **401**
- 修正后容器内 `printenv SPACETRACK_PASS` → `len=15`；关键 env 抽查 `WORLDSIM_APP_PW`/`CONTROL_TOKEN`/`FIRMS_MAP_KEY` 3/3 未丢
- 实跑 `fetch_spacetrack.py`：首次 `Read timed out`（容器刚 force-recreate 网络未稳，偶发），重试两次均成功 `active=30000 payload=14837 debris=12321 starlink=10000 new30d=268`，与 08-29 末次成功值吻合
- 落盘 `data/spacetrack.json`：`total_active=30000`、`updated=2026-09-08T05:05:29Z`、`status="ok"`

### 遗留

- 脚本健壮性缺陷**未修**：`_get_session` 只校验 HTTP 状态码、不校验登录响应体（Space-Track 对错误凭证返回 200 + `{"Login":"Failed"}`）；`collect()` 查询失败仍写 `status:"ok"` + 全 0。二者叠加使本次配置错误**静默 10 天无告警**，已转 backlog 待另立 CHG。
- Starlink `limit=10000` 截断精度 bug 仍在（本次实测 `starlink=10000` 即上限值）。

## [3.8.36] - 2026-09-08

### Fixed（P2 / question fred-japan-jgb-lag-probe-spam 解法B，CHG-20260908T111550-macro-scan）

- **静默失败探针 FRED 滞后告警冷却**：`silent_failure_probe.check_fred_lag` 新增 notified-state（`.probe_fredlag_notified`，机制严格参照既有 `GED_NOTIFY_STATE`）——WARN/CRIT 以「序列 + 末行日期」为指纹，指纹未变则降级 INFO 不重复推送。修复日债 `IRLTLT01JPM156N` 滞后期间 ntfy 每 2h 刷屏（09-03~09-08 累计约 60 条）；末行日期前进或恢复健康后自动清标记并恢复推送能力。
- **FRED 增量写入去重**：`fetch_fred_history.save_series` 增量路径（mode="a"）改为「读旧 CSV → 合并 → 按 date 去重（keep=last）→ 排序 → tmp+os.replace 全量写回」。根因：FRED 在 `observation_start=last+1` 无新数据时仍返回末行观测，旧逻辑无去重地 append，导致日债累计 155 行同日重复（696 行 vs 官方 450 行）。读旧 CSV 失败时回退原追加语义。
- **数据清理**：`data/fred_history/IRLTLT01JPM156N.csv` 一次性去重（先备份 `.bak`），696 → 450 行，与 FRED 官方 450 数据行完全吻合，末行真值 `2026-06-01,2.67` 保留。

### 验收

- 容器内连跑两次 `silent_failure_probe.py --dry`：首次 `WARN`（推送）、第二次 `INFO`（已通知过，不重复告警），state 文件 `data/.probe_fredlag_notified` 正确落盘
- 容器内 `save_series` 去重冒烟：同一行 3 次增量追加 + 1 条新值 → 结果仅 2 行数据，表头与排序正确
- 清理后 CSV 450 数据行 = FRED 官方 450 数据行；改动文件 rsync 后 md5 真源=运行区一致（1ffd9b41… / bce0e88f…）
- commit `b7045ad`；容器 restart 后状态 Up 正常

## [3.8.35] - 2026-09-03

### Added（P2 / question llm-key-ui-write-path + llm-config-doc-drift Enforcement，CHG-20260903T164000，ADR-0015）

- **密钥控制台 write-only 通道**（恢复 v3.8.28 误删的 UI 填写，且不明文入库）：`llm_usage.py` 新增 `get_secret`（mtime 缓存热读取）/`set_platform_secret`（原子写 `config/.env` 0600）/`secret_status`（掩码+来源）；`control_server.py` 新增 `POST /control/llm-secret`（write-only）+ `GET /control/llm-secrets`（掩码）；key 解析次序统一「config/.env 优先 → 进程 env 兜底」，**保存即热生效免 recreate**；存量密钥服务端迁入 `config/.env`（untracked + `**/.env` 双 gitignore）
- **兜底模板自动再生钩子**：`set_usage` 成功路径自动再生 `config/llm_config.default.json`——UI 改模型后模板结构性不可能漂移（五联第②联自动化）
- **巡检脚本 `scripts/check_llm_config.py`**：五检查（真源=模板 / 运行区模板=git 模板 / 活跃文档旧模型名[历史叙述+archive+CHANGELOG 豁免] / .env 安全面 / pre-commit hook），TSX crontab 每日 08:10 + 周一 08:20 心跳，失败 ntfy 告警（内容无密钥值）；SSH 手改真源等钩子盲区由此兜底
- **pre-commit hook**：拒绝任何 `.env` 入库（防密钥上 GitHub 末道闸）
- **开阳前端 v1.11.37**：`LlmConfig.tsx` 恢复密钥框（password write-only + 掩码状态展示）；`controlApi.ts` `getLlmSecrets`/`setLlmSecret`；`control.ts` `LlmSecretStatus`

### Fixed（Enforcement 首跑揪出）

- `hybrid_llm.py` 残留 `os.environ.get("OPENAI_COMPAT_MODEL")` 死兜底删除（compose 已删该变量，杜绝双源复活）
- `llm_usage.py` L98 注释措辞更新（去旧 env 引用）；AGENTS.md compose 示例块密钥指引 key.txt → config/.env
- 巡检脚本自修复：archive 目录名级跳过（原 `docs/archive` 前缀不匹配 `macro-scan/docs/archive`）、TuiYan_CHANGELOG 前缀豁免、git 侧 check-ignore 改 repo 内路径、脚本不扫自身

### 验收

- 容器冒烟：get_secret 热生效 / 写后掩码 / 0600 / 模板再生一致；密钥值 grep 无 git 跟踪命中
- 巡检脚本 EXIT 0 全绿；模板运行区=git 真源 md5 一致；开阳 tsc+vite build 通过 + dist 同步 8080 就绪
## [3.8.34] - 2026-09-03

### Fixed（P1 / question llm-config-doc-drift，CHG-20260903T151756，用户路由清扫）

- **LLM 配置/文档漂移清扫（ADR-0010 未落地实证）**：运行区 `data/llm_config.json`（09-02 固化）为唯一真源，但默认模板 + 13 份文档/代码 docstring 停留在收敛前旧栈（MiniMax-M3 / Qwen3.5-27B 叙事 / mimo-v2.5），全量扫描后逐一同步：
  - 默认模板 `config/llm_config.default.json` 5 使用点对齐运行区（translate→Hunyuan-MT-7B / sim_narrative→DeepSeek-V4-Flash / openai_compat→mimo_plan+mimo-v2.5-pro / 删 sim_minimax / platform `mimo`→`mimo_plan`）
  - `docker-compose.yml` 移除残留 `OPENAI_COMPAT_MODEL=mimo-v2.5`（与 v3.8.27 声明一致，消除错误模型兜底）；`docker-compose.example.yml` 清 `MINIMAX_*`、改 `SILICONFLOW_MODEL`→DeepSeek-V4-Flash
  - 文档同步：macro-scan AGENTS.md / INDEX.md / FILE_MANIFEST.md / 世界推演系统_人类说明文档.md / 根 AGENTS.md / STATUS.md / kaiyang AGENTS.md / DATA_CONTRACT.md / NEXT_SESSION_HANDOFF.md / macro-sim_人类说明文档.md — 降级链统一为 MiMo v2.5-pro → DeepSeek-V4-Flash → 纯数据报告；翻译 Hunyuan-MT-7B
  - 代码 docstring/静态清单：`hybrid_llm.py` / `run_macro_analysis.py` 降级链；`llm_usage.py` PLATFORMS 模型列表 + LLM_USAGES 默认（translate→siliconflow/Hunyuan-MT-7B）/`fetch_news_titles.py` 翻译注释
- **加固 ADR-0010 Enforcement**：macro-scan/AGENTS.md 补「模型变更五联同步」强制 checklist（运行区配置 + 默认模板 + compose + 文档 + 代码静态清单），杜绝换模型只更 1 处的再次漂移
- **验收**：默认模板 diff 与运行区一致；grep 全仓无活跃 MiniMax-M3 / Qwen3.5-27B / 非 pro `mimo-v2.5` / `OPENAI_COMPAT_MODEL=mimo-v2.5`；历史文档（CHANGELOG/archive/reviews/ROADMAP）未改动

### 关联
- questions/world-deduction/20260903-world-deduction-llm-config-doc-drift.md（⚠️→✅ resolved 待归档）
- operations/CHG-20260903T151756-world-deduction.md
- decisions/world-deduction/0010（ADR-0010 文档漂移治理，本次补 Enforcement）

## [3.8.33] - 2026-09-03

### Added（P3-3 / question l4-tail-scenario-modeling，方案 C 降级折中版，用户拍板）

- **L4 极端尾部烈度建模**：hypothesis_templates.yaml severity_params 新增 L4 节「崩坏/极端尾部」（vix_mult 2.5 / lambda_mult 6.0 / sigma_mult 3.5 / regime_force stress；calibration: expert-assumption 显式标注专家情景假设非历史校准；keywords 全多字词防误判——核战争/全球大流行/小行星撞击等）
- **历史类比禁用于 L4**：hypothesis_engine.get_historical_analogies 对 severity=="L4" 不做 percentile 系数外推（L4 无历史样本，外推属伪精确），改返回固定情景假设区间（spx -60/-45/-30、vix_delta 50/70/90、gdp -30/-20/-10），source 标注「L4情景假设（非历史校准）」；L1-L3 逻辑不变（整体收进 else）
- **永不升格🟢覆盖 L4**：置信度信号 no_green_triggers 分支 `sev == "L3"` → `in ("L3", "L4")`
- **ntfy 推演通道放行 L4**：ntfy_listener.py 烈度白名单 ("L1","L2","L3","L4") + sev_label 加「崩坏/极端尾部」
- **验证（容器内冒烟，零 LLM 调用）**：py_compile 过；parse「核战争/全球大流行」→L4、「台海紧张」→L2 不误判；L4 impacts=情景假设区间+标注；L3 source 仍=历史类比；三方 md5 一致（git 真源/运行区/容器）+ docker restart
- **后续完整版入 backlog**：概率型/情景型分组推演（L4 走独立情景分析模式，hermes-systemic 9.5 原方向）——用户拍板「早晚要完善，记的加进后续计划里」

### 关联
- questions/world-deduction/20260903-world-deduction-l4-tail-scenario-modeling.md（⚠️→✅→归档）
- decisions/world-deduction/0014-l4-tail-severity-modeling.md（ADR-0014）
- operations/CHG-20260903T125000-macro-scan.md

# macro-scan CHANGELOG — 天枢（数据采集/分析层）

> 文档类别：实录（RECORD）· CHANGELOG
> 版本锚点：`S:/world-sim/macro-scan/VERSION`

## [3.8.32] - 2026-09-03

### Fixed（P2-5 / question calibration-score-no-decay + 前置阻塞 bug）

- **propagation_paths.yaml 解析修复**：`atomic_paths:` 映射键打断顶层 list 致 ParserError，被 `_load_propagation_paths()` 的 `except Exception` 静默吞掉——25 条传导路径（20 主 + 5 原子）从未加载，维度2 恒兜底 0.2。现原子路径并入顶层 list（键无代码消费），实测加载 25 条
- **置信度时间衰减**：20 条主路径按 data_quality 历史锚点补 `last_verified`（12 条），`hypothesis_engine._cal_decay()` 应用 `max(0.5, 0.98^年数)` 衰减因子于维度2 加权（L563 avg_cal）；无锚不衰减。参数可调
- 注意：修复后维度2 从恒 0.2 变为真实计算，推演概率输出将变化（预期修复效果）；完整推演回归交由下次常规调度验证
- CHANGELOG: v3.8.24 停更的 TuiYan_CHANGELOG.md 已废弃（AGENTS 导航待更新，另案）

## v3.8.31 — 2026-09-03 天枢 news_ttl_cleanup 功能批次入库：PG news.articles 90 天 TTL 清理（08-30 已部署，本次补 git 记录）

### 变更
- 【commit c94978c — question 20260903-world-deduction-ttl-cleanup-uncommitted（P2）收编，用户拍板「按顺序来吧」】
  - 入库 “核心代码/news_ttl_cleanup.py”（3121B，08-30 建）：PG news.articles TTL 清理，保留 90 天（NEWS_TTL_DAYS env 参数化），更早行 DELETE
  - 入库 “核心代码/scheduler.py” +2：JOBS 注册 news_ttl_cleanup（每日 03:00，“1-7”）+ LOG_FILES 注册 news_ttl_cleanup.log
  - VERSION 3.8.30 → 3.8.31（git 真源 + 运行区双端；该文件经 grep 实证无代码消费、容器不挂载，属纯文档锚点）
  - ⚠️ 本次为补记录而非新部署：git 真源 / 运行区 / 容器三方 md5 全同（2afc1122…）实证功能 08-30 起已在运行，此前仅缺 git 记录（“部署先于入库”第三次，同 kaiyang D3 08-06 先例）

### 关联
- questions/world-deduction/20260903-world-deduction-ttl-cleanup-uncommitted.md（⚠️ → ✅ → 归档）

---
## v3.8.30 — 2026-09-03 P5 退役：天枢 verify 域三旧脚本退役（验证功能 2026-08-24 已迁天玑收编）

### 变更
- 【commit ea518a9 — question 20260824-world-deduction-verify-domain-consolidation / 20260823-world-deduction-verify-ownership-misplacement（P5 收尾，用户拍板执行）】
  - 删除 “核心代码/verify_geo_auto.py” / “verify_hypothesis.py” / “verify_predictions.py”（git 真源 + 运行区双端）——现行调度已在天玑 tianji_verify_cron（geo_auto 每日 09:30 / predictions 每月 1 日 09:00 / hypothesis 每月 1 日 09:15），天枢三文件为 2026-08-24 存量收编后的旧残留；宿主/容器 crontab、scheduler JOBS、ntfy 指令通道全入口 grep 核查无引用后删除
  - “核心代码/ntfy_listener.py”：退役 cmd_verify 指令通道（函数块/路由分支/help 行三处），防删文件后 ntfy verify 指令断链；py_compile 通过；运行区 md5 双端一致（b339f74f…）
  - “verify_reads_e0c.py” 保留（E0 审阅域与验证域独立）
  - VERSION 3.8.29 → 3.8.30
  - 已知过时待后续：tests/test_audit_scan_scheduler_verify.py 断言 scheduler JOBS 应含 verify_predictions（审计 #13 xfail 回归设计），随本退役语义反转，建议改为“JOBS 不应含”（不在本次范围）

### 关联
- questions/world-deduction/20260824-world-deduction-verify-domain-consolidation.md（⏸ → ✅ → 归档）
- questions/world-deduction/20260823-world-deduction-verify-ownership-misplacement.md（母题，归档）
- 背景：P4 月度对账（09-01 窗口 verify 两任务首次自动触发 + 43 条补跑）全维度通过后执行既定 P5 收尾

---
## v3.8.29 — 2026-09-03 开阳报告索引时序竞态修复：save_report() 落盘后就近刷新开阳数据源

### 变更
- 【commit 113410b — question 20260902-kaiyang-report-index-race（P2）修复，用户拍板方案 A】
  - “核心代码/run_macro_analysis.py” “save_report()”：ntfy 推送后、return 前新增 REINDEX 段——报告写盘成功后 subprocess 调同目录 “generate_reports_index.py”（timeout 180s），即写即刷新 “data/reports_index.json” + “data/reports/”，解耦索引重建与调度时序；触发失败仅 [WARN] 打印，不阻塞报告保存/ntfy 推送
  - “scheduler.py” 07:35（工作日）/20:35（每天）定时重建保留作幂等兜底（不删）
  - VERSION 3.8.28 → 3.8.29

### 关联
- question “questions/world-deduction/20260902-world-deduction-kaiyang-report-index-race.md”（⚠️ 已定位待修复 → 修复完成）
- CHG-20260903T072540-world-deduction（Pre/Post 闭环）
- 背景：晨报 07:30 cron 启动、LLM ~07:36 完稿；scheduler 07:35 索引重建抢跑 → 报告落 07:36~20:35 空窗（ntfy 已推、开阳不显示）

---
：控制台 api_key 写入通道封死（密钥只走 .env，ADR-0013）

### 变更
- 【commit 94939af — question 20260902-llm-config-key-plaintext（P1）修复】
  - “核心代码/llm_usage.py” “set_usage”：非空 api_key 硬拒 → (False, “密钥禁止经控制台写入：请配置于 NAS macro-scan/.env …”)；entry.pop(“api_key”) 清历史残留——config 持久化永不带 key（docstring 同步）
  - “核心代码/control_server.py” PUT /api/v1/control/llm-usage/{usage_id}：docstring 更新（key 禁走此路，set_usage 兜底拒收并返回明确错误）；body 透传保留
  - 前端配套（kaiyang v1.11.36）：LlmConfig.tsx 删 key 输入框 + controlApi.ts updateLlmUsage 去 apiKey

### 关联
- question “questions/world-deduction/20260902-world-deduction-llm-config-key-plaintext.md” → ✅ resolved 归档
- ADR-0013 secret-injection-normalization（密钥只走 .env）
- 与 “20260822-llm-keys-plaintext-in-git”（compose 明文进 git）同源不同面，共同闭合 world-deduction 密钥注入规范

---

## v3.8.27 — 2026-09-02 LLM 平台收敛：mimo_plan/mimo_api 拆分 + openai_compat 模型固化 config + 移除预置 OpenAI 平台

### 变更
- 【commit eb47031 — mimo 平台拆分：mimo→mimo_plan + 新增 mimo_api】
  - `核心代码/llm_usage.py`：`PLATFORMS` 的 `mimo` 重命名 `mimo_plan`（显示名“小米 MiMo Plan”，token-plan 端点与 `OPENAI_COMPAT_KEY` 映射不变）；新增 `mimo_api`（显示名“小米 MiMo API”，base_url `https://api.xiaomimimo.com/v1`，env `MIMO_API_KEY`）；LLM_USAGES 引用 `platform:"mimo"` 的 3 处默认值同步 → `mimo_plan`；`env_name` 表同步 + 新增 `mimo_api→MIMO_API_KEY`
  - `核心代码/hybrid_llm.py`：`_PLATFORM_ENV_KEYS` 同步（`mimo_plan`）+ 新增 `mimo_api→MIMO_API_KEY`
  - `data/llm_config.json`（运行态）：`openai_compat.platform` `mimo`→`mimo_plan`
  - `docker-compose.yml`：env 段新增 `MIMO_API_KEY=${MIMO_API_KEY}`（`config --quiet` 通过）；`.env` 加 `MIMO_API_KEY=` 占位（待用户填 `ak-` key 后 `docker compose up -d` 生效）
- 【commit 368e3d6 — openai_compat 模型固化 config + 移除预置 OpenAI 平台】
- `data/llm_config.json`：`usages.openai_compat.model` 固化 `mimo-v2.5-pro`（原经 env `OPENAI_COMPAT_MODEL` 注入、开阳仅显示"（env 默认）"不可见不可改）→ 开阳 effective_models 直接显示真实生效模型、下拉可改
- `docker-compose.yml`：移除 env `OPENAI_COMPAT_MODEL=mimo-v2.5-pro`（隐藏开关，与 config 双源易漂移；`OPENAI_COMPAT_URL` 保留——`reason()` 无 usage 路径依赖它定 base_url）
- `核心代码/llm_usage.py`：`PLATFORMS` 移除预置 `openai`（api.openai.com，从未被任何 usage 引用、未配 key，初始脚手架残留）；`env_name` 表同步删除
- `核心代码/hybrid_llm.py`：`_PLATFORM_ENV_KEYS` 移除 `openai` 行（`reason()` 的 `mode=="openai"` 分支与 CLI `--reasoning` choices 保留——其语义为 OpenAI 兼容协议指向 MiMo，与 api.openai.com 平台无关）

### 关联
- 命名决议（用户拍板）与实施规划见 `decisions/world-deduction/20260902-world-deduction-add-mimo-api-provider.md`（status: planning → implemented）
- `morning.log`/`us_daily.log` 实证宏观分析经 `reason("auto")` → `call_openai_compat`（无 usage）→ env URL + config model 生效路径

---

## v3.8.26 — 2026-08-28 P2: PG news.articles TTL 清理

### 新增
- `核心代码/news_ttl_cleanup.py`：每日清理 `news.articles` 中超过 TTL_DAYS（默认 90 天）的行；timedelta 参数化、dry-run 计数先行、VACUUM ANALYZE 后置（失败不阻断）
- `scheduler.py`：`JOBS` 加 `news_ttl_cleanup`（每日 0300）+ `LOG_FILES` 对应条目

### 备注
pg_dump 备份已由 `/vol2/1000/software/worldsim-pg/backup-pg.sh`（每日 0400，保留 14 天）独立覆盖，无需重复注册。

---

## v3.8.25 — 2026-08-27 F1 commit 2: 天璇 GRV 轨迹 feed 导出

### 新增
- `核心代码/tianxuan_grv_export.py`：扫 `docs/仿真报告/*_grv_traj.json`，按 `generated_at` 幂等导出最新轨迹到 `data/tianxuan_grv.json`；M4 版本护栏、保留旧 feed + 告警（不静默写空）、M6 幂等跳过重写
- `scheduler.py`：`JOBS` 加 `tianxuan_grv`（I30）+ `LOG_FILES` 对应条目
- `silent_failure_probe.py`：新增 `check_tianxuan_grv()`（内容 `generated_at` 判据，非 mtime）
