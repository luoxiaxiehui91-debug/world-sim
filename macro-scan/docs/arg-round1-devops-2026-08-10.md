# crucix 优雅停用 —— 运维操作方案 / 回滚预案 / 监控方案（第一轮论证）

- 日期：2026-08-10
- 作者：devops-review（SRE/运维视角）
- 范围：**仅"如何下线 crucix 容器"**，不涉及依赖摘除的实现细节（由 arch-review / data-review / qa-review 覆盖）
- 红线遵守：本文档不读取 crucix 源码（AGPL-3.0）；只做只读核实（docker inspect/ps/logs/日志 grep），不执行任何停用操作
- 验收落盘：本文档为第一轮产出物

---

## 0. 现状核实基线（2026-08-10 实证）

### 0.1 crucix 容器（下线对象）

| 项 | 实测值 |
|---|---|
| 容器 | `crucix-crucix-1`，状态 `Up 3 hours (healthy)` |
| 网络 | host 网络（`NetworkMode: host`），监听 `*:3117` |
| 端口 | `3117/tcp` → `3117`（compose port 绑定） |
| 进程 | PID 4157825 `node --max-old-space-size=512 server.mjs`（11:58 启动） |
| 健康检查 | `wget -qO- http://localhost:3117/api/health`，间隔 60s，超时 10s，重试 3 次 |
| 重启策略 | `unless-stopped` |
| compose | 项目 `crucix`，文件 `/vol2/1000/software/Crucix/docker-compose.yml`，工作目录同 |
| 挂载 | 全部为 **rw bind mount** 自 `/vol2/1000/software/Crucix/`（含 server.mjs、lib、sources、memory、runs、apis、dashboard 等 14 项） |
| 数据落盘 | memory/、runs/、apis/ 等目录本身在 NAS 持久卷上（bind 自 `/vol2/1000/software/Crucix/`），**容器删除不丢数据** |

> 关键结论：`docker stop` 即可优雅停服务；`docker rm` 不删除 `/vol2/1000/software/Crucix/` 任何文件（bind mount 数据在宿主机）。这是低风险下线的硬件前提。

### 0.2 天枢（唯一数据中枢）对 crucix 的消费活跃度

| 消费模块 | 调度时间（scheduler.py） | 调用方式 | 降级行为 |
|---|---|---|---|
| `scan_weak_signals.py`（weak_signal） | 0000 / 0600 / 1200 / 1800 每日 4 次 | `fetch_crucix_news(days=90)` → GET 3117 | 失败打印「跳过新闻扫描」，**继续扫描** |
| `run_macro_analysis.py` → `data_fetcher.py`（morning/us_daily/china_daily） | 0730 / 2000 / 2015 | `snapshot["_crucix"]` 注入（gscpi/nuke/sdr/air/markets） | 失败置 `{}`，打印 `[SKIP] Crucix:`，**不阻断** |
| `fetch_climate_signals.py`（climate） | 0910 | GET 3117（兜底） | 失败走自有兜底 |
| `narrative_processor.py` / `news_db` 归档 | 0710 / 逐次 | 间接（依赖 scan 产物） | 见 arch-review |

**调用频次实测**：
- `scan.log` 中「拉取 Crucix 新闻」共 **369 次**（历史累计），每天 4 次弱信号扫描均触发；
- 最近一次成功拉取：`[Crucix] 获取 50 篇文章（最近90天）`（08-10 多次，最后一次 scan.log 时间戳 12:00:18，对应 1200 档）；
- `news.db`（24MB）最近写入 08-10 12:07（1200 档弱信号扫描产物）。

**天枢对 crucix 失败的既有降级证据（历史实证）**：
`scan.log` 第 11474 行（2026-07-05）：
```
[Crucix] 获取失败: HTTPConnectionPool(host='192.168.31.108', port=3117): Max retries exceeded ... Connection refused，跳过新闻扫描。
[news.db] 文章入库 139 篇，打标签 26 条   ← 后续任务照常执行
```
> 即：**3117 拒绝连接时，天枢已验证可优雅降级、非阻断**。这是 Phase C/D 可行性的核心证据。

### 0.3 端口 / 依赖唯一性核实（P0）

- 全 NAS 容器中 **仅 `crucix-crucix-1` 映射/监听 3117**；宿主机 `*:3117` 监听者即 crucix 的 node 进程；
- crontab / systemd / `/opt` `/usr/local/bin` 下**无**任何对 3117 的引用；
- `/vol2/1000/software/` 全量精确搜索 `http://...:3117` / `:3117/api`：
  - **唯一命中**：`claude-config-backup/settings.local.json:89` 中一条 Chrome 启动命令 `--remote-debugging-port=9222 ... "http://192.168.31.108:3117"` —— 这是手动用浏览器打开 crucix dashboard 的本地工具配置，**非程序化 API 消费**，不构成依赖（已登记风险 R4）；
  - 其余命中均为无关文件（CHECKSUMS、Crypto 库、freetype、benchmark 等误报，已排除）。
- **注意区分**：`7890` 是 NAS 出站代理（天枢 `OUTBOUND_PROXY=http://192.168.31.108:7890`），**不是 crucix 端口**。`scan.log` 中 `port=7890 Read timed out` 是代理超时，与 crucix 下线无关。

> 结论：crucix 3117 的消费方**只有天枢**，无第三方项目共享受害面。

---

## 1. 下线阶段设计（4 阶段，与 arch 摘除顺序衔接）

前置前提（由 arch-review / data-review 完成，本方案默认成立）：
- arch 摘除顺序 = 先摘数据消费（scan_weak_signals 新闻频率、data_fetcher._crucix 注入、narrative_processor 4 映射、news_db 归档、regime_detector gscpi_warn、climate thermal 兜底），后动容器。

### Phase A — 观测基线（第 0 天，不碰任何东西）

**目标**：记录"停用前"的正常基线，供后续对比。

| 动作 | 命令 / 对象 | 产出 |
|---|---|---|
| A1 容器健康基线 | `docker ps --filter name=crucix-crucix-1` | healthy 确认 |
| A2 API 调用频次基线 | `grep -c '拉取 Crucix 新闻' scan.log` + `grep -c '\[OK\] Crucix:' morning.log us_daily.log` | 计数（当前 369 / 每档 1 次） |
| A3 降级日志基线 | `grep -iE 'SKIP.*Crucix|Crucix.*获取失败' logs/*.log` | 记录现存失败数（当前 07-05 一条 + 7890 代理超时若干） |
| A4 关键产物时间戳基线 | `ls -l data/news.db data/latest_news.json data/weak_signal_log.json data/news_export.json` | 记录各文件 mtime |
| A5 网络拓扑快照 | `docker inspect crucix-crucix-1 --format '{{.NetworkSettings.Networks}}'` + `ss -tlnp | grep 3117` | 确认 host 网络 + PID 记录 |
| A6 天枢健康确认 | `docker ps --filter name=macro-scan-macro-scan-1` + `docker logs ... --tail 5` | 天枢 Up，scheduler 正常 |

**完成判据**：A1-A6 全部记录到本文件附录（见 §5），形成可对比的基线快照。

---

### Phase B — 依赖摘除后观察窗（第 N 天，arch 完成摘除后，crucix 仍在跑）

**目标**：验证"天枢已无消费"——crucix 仍健康运行，但天枢不再请求它，此时观察天枢是否完全正常。

前置：arch-review 的摘除改动已合入并 `docker restart macro-scan-macro-scan-1`。

| 观察项 | 判定"摘干净"的信号 | 判定"没摘干净"的信号 |
|---|---|---|
| B1 调用消亡 | `docker logs crucix-crucix-1 --since 24h` 无新增访问日志（若有访问日志）；或抓包/连接计数归零 | 仍见 crucix 侧请求 / 天枢日志仍出现 `[OK] Crucix:` |
| B2 天枢日志无 crucix 关键词 | `grep -icE 'crucix|_crucix' logs/*.log`（观察窗内）应为 0 或仅历史 | 新出现 `拉取 Crucix 新闻` / `[OK] Crucix:` |
| B3 天枢各模块产物正常 | news_export.json / news.db / latest_news.json / weak_signal_log.json 按各自周期正常更新时间戳 | 某文件停更 / 报错 |
| B4 天枢无新增 SKIP/错误 | 观察窗内无 `[SKIP] Crucix:` 新记录 | 出现新的 crucix 相关 SKIP |

**观察窗时长建议**：≥ 2 个完整调度日（覆盖 0000/0600/1200/1800 弱信号 4 档 + 0730 morning + 2000/2015 宏观 + 0910 climate + 0710 narrative_proc），即 ≥ 48h，建议 72h。

**完成判据**：B1-B4 全部通过 —— 天枢全模块无 crucix 消费且健康。

---

### Phase C — 停 crucix API 服务（最小风险操作，容器不删）

**目标**：用**可逆性最强**的方式让 3117 不再响应，观察天枢在"依赖已摘除"前提下是否零报错。

**推荐操作（C1 主方案）：`docker stop crucix-crucix-1`（或 compose: `docker compose -f /vol2/1000/software/Crucix/docker-compose.yml stop`）**

理由（对比其它方案）：
- 改端口（改 compose port 映射 + recreate）→ 改动配置、需 recreate，回滚要再改回，且 host 网络下端口由 server.mjs 固定 3117，改端口要动配置；
- 防火墙（iptables DROP 3117）→ 与 host 网络 + 现有防火墙规则耦合，误操作风险高，且回滚依赖清理规则；
- `docker stop` → 一条命令，`docker start` 即完整回滚，**零配置改动**，符合"最小风险"。

**降级观察（C 期，预计 24-48h）**：
1. 天枢日志应**不再**出现任何 crucix 关键词（因 B 期已摘除）；如仍出现，说明摘除不彻底 → 回滚到 B 期，通知 arch-review；
2. 天枢全模块产物时间戳按各自周期正常推进；
3. `ss -tlnp | grep 3117` 应无输出；`docker ps` 中 crucix 状态为 `Exited (0)`。

**验证命令清单**：
```bash
# 天枢侧：观察窗内零 crucix 新日志
grep -icE 'crucix|_crucix' /vol2/1000/software/macro-scan/logs/*.log   # 期望仅历史或 0
# 产物新鲜度
ls -l /vol2/1000/software/macro-scan/data/news_export.json /vol2/1000/software/macro-scan/data/latest_news.json
# 端口已释放
ss -tlnp | grep 3117    # 期望无输出
```

**完成判据**：观察窗（建议 ≥ 2 个调度日）内天枢日志零 crucix 报错、全部产物正常更新、3117 无监听。

---

### Phase D — 停容器 + 资源回收（最终态）

前置：C 期观察通过，且经过 qa-review 验收门禁（arg-round1-qa 文档）放行。

| 步骤 | 操作 | 说明 |
|---|---|---|
| D1 | `docker stop crucix-crucix-1` | 若 C 期已 stop 则跳过；`docker start` 即回滚 |
| D2 | 冷备数据库/运行数据 | `cp -a /vol2/1000/software/Crucix/memory /vol2/1000/software/Crucix/memory.bak-20260810`（先 df 确认空间），如 data-review 判定需留存样本 |
| D3 | `docker rm crucix-crucix-1` | **仅删容器层**，bind mount 数据在宿主机不受影响；`--volumes` 不要加（本容器无命名卷，加了也无害，但明确不加） |
| D4 | 保留 compose 文件与代码目录 | `/vol2/1000/software/Crucix/` **整体保留不删**（含 docker-compose.yml），保证可一键重建回滚 |
| D5 | 镜像处理（可选，建议暂留） | 不删镜像 `crucix-crucix:latest`（sha256:3888...）；建议 ≥ 1 个月观察后再决定 `docker rmi` |
| D6 | 天枢 scheduler.py 清理 | 检查 scheduler.py 中是否有 crucix 相关注释/待办/占位（已核实：**无直接调用**，仅有注释提及 CRUCIX_REMOTE_URL 的模块，由 arch 摘除时清理）；改 scheduler 后需 `docker restart macro-scan-macro-scan-1` |
| D7 | 端口/网络收尾 | `ss -tlnp | grep 3117` 确认无监听；无防火墙残留（本方案未用防火墙，故无残留） |
| D8 | 公告/文档更新 | 更新 world-sim 文档中 3117 引用、`claude-config-backup/settings.local.json:89` 中的 dashboard URL（R4） |

**最终态确认**：
```bash
docker ps -a --filter name=crucix   # 无 crucix-crucix-1 或显示 Removed
ss -tlnp | grep 3117                # 无输出
docker ps --filter name=macro-scan-macro-scan-1   # 天枢仍 healthy/Up
grep -ricE 'crucix' /vol2/1000/software/macro-scan/logs/*.log  # 计数不再增长
```

---

## 2. 回滚预案（每阶段可回滚点）

| 阶段 | 可回滚点 | 回滚操作 | 回滚判定信号 |
|---|---|---|---|
| Phase A | 无变更，天然可回滚 | — | — |
| Phase B | B 期发现天枢异常（非 crucix 引起） | 天枢侧回滚由 arch-review 负责（revert 摘除改动 + `docker restart macro-scan-macro-scan-1`）；crucix 侧无需动 | 天枢恢复 4 档弱信号 + morning 正常输出 |
| Phase C | C1 stop 之后、D 之前，**任意时刻** | `docker start crucix-crucix-1`（或 `docker compose start`）→ 等待健康检查转 healthy（≤3 次×60s ≈ 3min） | `docker ps` healthy；`wget -qO- localhost:3117/api/health` 返回 200；天枢如还有旧依赖则日志恢复 `[OK] Crucix:` |
| Phase D | D3 `docker rm` 之后、D4 前（保留代码目录时） | `cd /vol2/1000/software/Crucix && docker compose up -d`（重建容器，重新 bind 现有数据） | 同上：healthy + health API 200 + 数据目录可见（memory/runs 均在） |
| Phase D | D5 镜像删除之后 | **不可通过镜像回滚** → 需从镜像仓库/备份恢复；故 D5 设为可选并强烈建议延后 | — |

**回滚总原则**：
1. 数据（memory/runs/apis）始终在 NAS 持久卷，**任何阶段回滚都不丢数据**；
2. D 之前回滚全部是「秒级 + 零配置」，D3 之后回滚是「compose up -d 一键重建」；
3. 回滚后必须跑 §3 监控确认，再决定是否重新进入下线流程。

---

## 3. 监控与告警（停用期间盯什么）

### 3.1 天枢日志关键词（首要监控）

| 关键词 | 正常（摘除后） | 异常信号 | 动作 |
|---|---|---|---|
| `_crucix` / `[OK] Crucix:` | 不应再出现 | 仍出现 → 摘除不彻底 | 通知 arch-review |
| `[SKIP] Crucix:` / `Crucix.*获取失败` | 不应新增 | 新增 → 有残留调用 | 通知 arch-review；视严重度回滚 C |
| `fetch_crucix_news`（弱信号新闻频率） | 不再有拉取 | 仍有 → 残留 | 同上 |
| `gscpi_warn`（regime_detector） | 不再引用 crucix 数据 | 引用 → 残留 | 同上 |

监控方式：观察窗内每 6h 执行一次 `grep -icE 'crucix|_crucix' logs/*.log` 并与 A3 基线对比；建议写入 crontab（只读，不落盘到 NAS 之外）。

### 3.2 产物新鲜度（数据链路健康）

| 文件 | 周期 | 停用后应保持的更新时间 |
|---|---|---|
| `data/news.db` | 弱信号每档 | 每 6h 有更新 |
| `data/latest_news.json` | 弱信号每档 | 每 6h 有更新 |
| `data/weak_signal_log.json` | 弱信号每档 | 每 6h 有更新 |
| `data/news_export.json` | news_export 0705 | 每日 07:05 后更新 |
| `data/climate_signals.json` | climate 0910 | 每日 09:10 后更新 |
| `logs/morning.log` / `logs/us_daily.log` | 工作日 | 按周期出现 `[OK]`/分析完成行 |
| `data/scheduler_state.json` | 持续 | mtime 持续前进（调度器存活） |

### 3.3 ntfy 告警规则（现有 ntfy 容器，topic 配置见天枢）

- 现有机制：天枢通过 `ntfy_listener.py` 推送（8080 前端 / ntfy 容器）；
- 停用期间**新增建议**（低侵入，只读）：
  - 天枢 down / restart：`docker ps` 状态变化告警（若 NAS 有 watchtower/监控，确认已覆盖）；
  - news_export.json 连续 2 日未更新 → ntfy 告警（数据链路中断信号）；
  - `[SKIP] Crucix:` 计数非零增长 → 告警（残留调用信号）；
  - 3117 端口重新出现监听（`ss -tlnp | grep 3117`）→ 告警（意外恢复，需调查）。

### 3.4 停用期间不可接受的指标

1. 天枢容器重启/退出；
2. 任一核心产物（news_export / news.db / weak_signal_log / climate_signals）停更超期；
3. 天枢日志出现非 crucix 的新的 `Connection refused`（可能误伤其他依赖）；
4. 3117 端口状态与预期不符（C 期后应为无监听）。

---

## 4. 风险登记（下线操作本身的风险）

| ID | 风险 | 等级 | 缓解措施 |
|---|---|---|---|
| R1 | **误停**：在依赖未摘除时 stop crucix | P0 | 门禁：Phase B 观察窗通过前禁止 C/D 操作；操作前 `grep -icE 'crucix' logs/*.log` 复核为 0；操作单由 qa-review 验收放行 |
| R2 | **依赖未清干净**：某个模块仍请求 3117 | P0 | §0.3 已核实仅天枢消费；B 期 48h+ 观察 + C 期 24h+ 观察双重验证；残留即回滚 |
| R3 | **端口冲突/意外恢复**：3117 被其他服务占用或 crucix 自启 | P1 | C/D 后 `ss -tlnp | grep 3117` 确认；unless-stopped 策略已被 stop 覆盖（stop 不触发重启）；如需防自启可 `docker update --restart no crucix-crucix-1`（可选，先问 team-lead） |
| R4 | **其他项目引用**：claude-config-backup settings.local.json 手动打开 dashboard 的 URL | P2 | 已核实为手动浏览器命令，非程序化依赖；D 期更新该文件 URL 或标注失效 |
| R5 | **数据丢失**：担心 rm 容器丢数据 | P0 | bind mount 数据在 `/vol2/1000/software/Crucix/`，rm 仅删容器层；D2 冷备 memory；D4 保留代码目录可一键重建 |
| R6 | **镜像删除后不可回滚** | P2 | D5 明确可选 + 延后 ≥1 个月；删除前确认镜像在 registry 有副本 |
| R7 | **scheduler 改动引发天枢重启故障** | P1 | scheduler.py 改动由 arch 完成并经 qa 验收；`docker restart` 前先 `docker exec` 内 `python -c "import ast; ast.parse(open('scheduler.py').read())"` 语法检查 |
| R8 | **代理(7890)误伤**：停用期间天枢外网抓取因代理波动报错，被误判为 crucix 下线所致 | P2 | 监控时区分关键词 `port=7890`（代理）vs `port=3117`（crucix）；见 §0.3 提示 |
| R9 | **观察窗过短漏检**：48h 未覆盖全部调度档 | P2 | 至少覆盖 2 个完整调度日；C 期观察到弱信号 0000 档（深夜）通过 |
| R10 | **AGPL 合规风险**：运维过程中误触 crucix 源码 | P0 | 全程只读不读源码；所有验证基于 docker 元数据/日志/天枢侧代码；不在文档引用 crucix 源码内容 |

---

## 5. 附录：Phase A 基线快照（2026-08-10 实测）

```
docker ps:
  crucix-crucix-1          Up 3 hours (healthy)
  macro-scan-macro-scan-1  Up 3 days
  macro-scan-tianji-1      Up 4 days (healthy)

crucix inspect:
  NetworkMode=host, Ports=3117/tcp, RestartPolicy=unless-stopped
  Healthcheck=wget localhost:3117/api/health (60s/10s/3)
  Compose=/vol2/1000/software/Crucix/docker-compose.yml
  Mounts=14 项 rw bind from /vol2/1000/software/Crucix/

3117 listener: PID 4157825 node --max-old-space-size=512 server.mjs (11:58)

消费统计（基线）:
  scan.log 拉取 Crucix 新闻 = 369 次（历史累计）
  最近成功拉取 = 50 篇文章（最近90天），08-10 多次
  news.db 24MB mtime=08-10 12:07
  news_export.json mtime=08-10 07:05
  weak_signal_log.json mtime=08-10 12:07
  scheduler_state.json mtime=08-10 15:04

既有降级证据:
  scan.log:11474（2026-07-05）[Crucix] 获取失败 ... Connection refused，跳过新闻扫描 → 后续任务照常

第三方消费核实:
  仅 crucix-crucix-1 监听 3117；无 crontab/systemd 引用；
  claude-config-backup/settings.local.json:89 有一条手动打开 dashboard 的 Chrome 命令（非程序化）
  7890 = 出站代理（OUTBOUND_PROXY），非 crucix
```

---

## 6. 结论

1. **可行且低风险**：天枢对 crucix 失败已有 2026-07-05 的降级实证（Connection refused → 跳过新闻扫描 → 任务继续），且依赖摘除后 crucix 不再被消费，`docker stop` 是最小风险的下线操作；
2. **数据安全**：crucix 数据全量在 NAS 持久卷 bind mount，容器删除不丢数据，可一键重建回滚；
3. **唯一消费方**：已核实 3117 仅天枢消费，无第三方共享受害面；
4. **严格门禁**：Phase A→B→C→D 顺序不可跳；B/C 观察窗为硬性门禁；qa-review 验收放行后才可进入 D。

（本方案与 arch-review 的摘除顺序、qa-review 的验收门禁互为衔接；停用操作待团队决议后另行执行。）
