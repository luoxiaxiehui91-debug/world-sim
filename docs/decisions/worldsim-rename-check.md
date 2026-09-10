# worldsim → worldsim-pg 改名影响面检查记录

> 日期：2026-08-13 22:2x（GMT+8）
> 性质：**只查不改**（用户指令「建议仔细检查，发现问题做记录」）
> 范围：`/vol2/1000/software/worldsim`（无连字符，PG 基础设施目录）全部引用面

## 一、目录身份确认（避免混淆的基线）

| 路径 | 身份 | 大小 |
|------|------|------|
| `S:\world-sim` = `/vol2/1000/software/world-sim` | **git 代码仓库**（macro-scan/macro-sim/macro-ji/kaiyang + docs） | 491M |
| `S:\worldsim` = `/vol2/1000/software/worldsim` | **PG 基础设施**：pgdata 数据卷 / connection.env / deploy-pg.sh / backup-pg.sh / backups / sql | 423M |

本地 SMB：`S:` → `\\192.168.31.108\software`（**映射在 software 根**，改名子目录不影响映射本身）。

## 二、引用面全清单（grep 实测）

### 2.1 需要改路径的文件（6 处）

| # | 文件 | 引用 | 性质 |
|---|------|------|------|
| 1 | `worldsim/deploy-pg.sh` | `WORLD=/vol2/1000/software/worldsim` + `mkdir -p $WORLD/...` + `-v $WORLD/pgdata`（**PG 数据卷唯一挂载点**） | 脚本 |
| 2 | `worldsim/backup-pg.sh` | `WORLD=` + `OUT=` + `PGPASSWORD_FILE=` + `find $WORLD/backups`（约 4 处） | 脚本 |
| 3 | `macro-scan/核心代码/delete_sqlite_e0c.sh`（git 树） | `BK=/vol2/1000/software/worldsim/backups` | 脚本 |
| 4 | `/vol2/1000/software/macro-scan/核心代码/delete_sqlite_e0c.sh`（运行区副本） | 同上 | 脚本 |
| 5 | `STATUS.md` | 3 处文字（vol2 bind pgdata / 备份留存 / connection.env 固化位置） | 文档 |
| 6 | `docs/decisions/audit-2026-08-13-risk-register.md` + `E0-C-operation-log.md` | 备份路径文字 | 文档 |

### 2.2 不需要改（实测确认）

- **所有 compose**（macro-scan / macro-sim / macro-ji / kaiyang）：volumes / networks / environment **均不引用 worldsim 目录路径**。`worldsim_default` 是 Docker 网络名（与目录无关），`WORLDSIM_APP_PW` 是 env 值（非路径）。
- **代码**：`host=worldsim-pg` / `dbname=worldsim` 是 PG 连接参数，改了才断。
- **中央知识库 `S:\docs`**：grep 全部引用带连字符的 `world-sim`（代码仓库），**零条**引用无连字符 worldsim → 改名零影响。
- **mneme 备份链**：`mneme/pg/backup.sh` 备份 `mneme-pg`/`mneme` 库（独立），cron 03:00 与其无关。
- **本地 SMB 映射**：S: 在 software 根，改名后用户访问 `S:\worldsim\...` → `S:\worldsim-pg\...`（使用习惯更新，映射本身不动）。

## 三、检查中发现的问题（按严重度）

### 🔴 P0-1 worldsim-pg 当前零有效备份（改名最大阻断项）
- **根因链**：`backup-pg.sh` line 8 `docker exec ... > ""` 语法错误（重定向到空名）→ `set -e` 下每次必挂。cron `0 4 * * * bash backup-pg.sh` 每日 04:00 调用，**backup.log（79B）实证**：`line 8: : No such file or directory`。
- **唯一现存 dump 也损坏**：`worldsim-20260812-2049.dump`（2071B）`pg_restore` 报 `input file is too short (read 0, expected 5)`——非有效 custom-format dump（疑迁移早期空库/半成品产物）。
- **后果**：PG（E0-C 后唯一事实源，articles=32560）**无任何可用备份**。改名需重建 PG 容器（deploy-pg.sh 幂等重跑），窗口内无回滚数据 → **改名必须先修备份并跑通一次真实备份**，否则不得动。

### 🔴 P0-2 backup-pg.sh 硬编码密码已失效
- `PGPASSWORD="<redacted>"` 与 `connection.env` 的 WORLDSIM_APP_PW / WORLDSIM_RO_PW **均不匹配**（布尔比对 NO_MATCH，未打印值）→ 即使修好语法，pg_dump 认证也会失败。
- 且明文密码在脚本中 = 密钥泄露面（脚本非 git 树，无版本控制）。

### 🟠 P1-1 STAMP 硬编码 + OUT 未拼时间戳
- `STAMP=20260812-2048` 硬编码；`OUT=".../worldsim-.dump"` **文件名不含 STAMP** → 备份永远写同名文件互相覆盖（即使语法修好）。

### 🟠 P1-2 错误 env 变量
- `export PGPASSWORD_FILE=".../.env"`：非标准变量名（应 `PGPASSWORD` 或 `~/.pgpass`）；`.env` 是 POSTGRES_* 键（docker 初始化用），不含 PGPASSWORD。

### 🟠 P1-3 echo 引用空变量
- `echo "backup done:  ()"` 输出空 STAMP/OUT（确认脚本从未成功过一次）。

### 🟡 P2-1 密钥卫生（既有，本次记录）
- macro-scan compose `environment:` 明文 6+ API key（FRED/SILICONFLOW/OPENAI_COMPAT/MINIMAX/EIA）+ WORLDSIM_APP_PW；backup-pg.sh 明文（过期）密码。建议 compose 改 `${VAR}` 引用，密钥收敛 connection.env/密钥管理。

### 🟡 P2-2 worldsim 目录无版本控制
- deploy-pg.sh / backup-pg.sh 非 git 树，改动无审计。建议在 world-sim 仓库建 `infra/pg/` 镜像（或 md5 固化 + 文档记录）。

### 🟡 P2-3 macro-sim `sim_log.db` 相对路径（待核）
- macro-sim/docker-compose.yml：`./sim_log.db:/app/sim_log.db` 相对 compose 文件 → 实际在 git 真源 `/vol2/1000/software/world-sim/macro-sim/sim_log.db`；注释却写 `touch /vol2/1000/software/macro-sim/sim_log.db`（运行区）——**注释与实际路径不一致**，需核对（单文件 bind + 天璇 COPY 模式重建风险）。

### 🟡 P2-4 中央知识库 08-12/08-13 world-sim 大事件未登记（已知，之前已记录）

## 四、改名方案（建议执行序）

```
0. 【必须先做】修复 backup-pg.sh（P0-1/P0-2/P1-1/P1-2/P1-3 一并重写）→ 跑通一次真实备份 → 验证 pg_restore -l 可读
1. mv /vol2/1000/software/worldsim /vol2/1000/software/worldsim-pg   # 同文件系统 rename，pgdata 零搬迁
2. 改 deploy-pg.sh WORLD 变量（1 处）
3. 改 backup-pg.sh（重写时直接写新路径）
4. 改 delete_sqlite_e0c.sh（git 树 + 运行区 2 份）BK 变量
5. 重建 PG 容器：deploy-pg.sh 幂等重跑 → 挂新路径 pgdata → 验证数据完好（articles 32560+）
6. 改文档文字（STATUS.md ×3 / risk-register ×1 / E0-C-log ×1）
7. 跑一次备份验证新路径
回滚：mv 回去 + deploy-pg.sh 重跑（分钟级）
```

风险点：仅第 5 步 PG 容器重建 1-2min 不可用（天枢写 PG 有 C3 有界重试兜底 + 探针会短暂告警，可接受）。

## 五、结论

- **改名可行且改动量小**（6 处路径引用，无 compose/代码/中央知识库/SMB 映射牵连）。
- **但被 P0-1 阻断**：当前 PG 无有效备份，重建容器窗口无回滚保障。**执行顺序必须改为：先修备份 → 再改名**。
- 建议备份修复与改名一起做（一个变更单），或先单独修备份（低风险、可立即做）。
## 执行记录（2026-08-13 22:2x，用户拍板执行，P0 备份已先修）

改名 `worldsim` → `worldsim-pg` 全部落地，**数据零丢失**：

| 步骤 | 动作 | 验证 |
|------|------|------|
| 0 | backup-pg.sh 修复 + 真实备份 23M 通过（见 backup-pg-fix-20260813.md） | ✅ |
| 1 | `mv /vol2/1000/software/worldsim /vol2/1000/software/worldsim-pg`（同文件系统，pgdata 零搬迁） | ✅ 旧路径消失；mv 后容器内 count 不变 |
| 2 | 改 4 处脚本路径：deploy-pg.sh（WORLD 1 处）/ backup-pg.sh（1 处）/ delete_sqlite_e0c.sh×2（BK 各 1 处） | ✅ bash -n 全过 |
| 3 | **改 crontab**（2.1 表漏记的第 7 处引用）：`0 4 * * * bash .../worldsim-pg/backup-pg.sh >> .../worldsim-pg/backups/backup.log` | ✅ 无残留旧路径 |
| 4 | `docker rm -f worldsim-pg` + `bash deploy-pg.sh` 重建（幂等，挂新路径 pgdata） | ✅ 挂载 `/vol2/1000/software/worldsim-pg/pgdata -> /var/lib/postgresql/data` |
| 5 | 数据完好性对比基线 | ✅ 32560/404/2034/314/1177 **完全一致**；pgvector 扩展在；探针 VERDICT OK / NON_OK 0；心跳 22:28 新鲜 |
| 6 | 新路径跑一次真实备份 | ✅ `worldsim-20260813-2228.dump` 23M，pg_restore 可读（TOC 85 / CUSTOM / 19 TABLE DATA） |
| 7 | 文档文字（本文件 2.1 表 + STATUS.md×3 + risk-register×1 + E0C-log×1） | ✅ 本表已更新 |

### 2.1 表修正（执行时发现检查漏记 1 处）

| # | 文件 | 引用 | 性质 |
|---|------|------|------|
| 7 | **crontab（TSX 用户）** | `0 4 * * * bash .../worldsim/backup-pg.sh >> .../worldsim/backups/backup.log` | 定时任务 |

> 检查阶段只扫了文件系统（grep），没扫 crontab——执行时才发现。已改，并补充本记录。

### 遗留 / 建议

- **connection.env / .env 随 mv 迁移到新路径**（deploy-pg.sh `--env-file "$WORLD/.env"` 已指向新路径）——天枢容器 environment 的 `WORLDSIM_APP_PW` 是值注入，与路径无关，无需动。
- 旧路径 `worldsim` 全 NAS 已无引用（脚本/文档/crontab 全改）。
- 命名坑消除：`S:\world-sim`（代码，带连字符）vs `S:\worldsim-pg`（PG 基础设施，语义自明）。
- 建议后续把 deploy-pg.sh / backup-pg.sh 权威副本固化进 world-sim 仓库 `infra/pg/`（P2-2，worldsim 目录无 git）。
