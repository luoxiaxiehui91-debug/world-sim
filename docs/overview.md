# 世界推演系统 · 总览

> macro-scan v3.8.69（天枢）· macro-sim **v2.0.51**（天璇）· kaiyang v1.11.44（开阳）· macro-ji v1.0.0（天玑）· as-of 2026-10-10
>
> ⏱ 本行只是快照（不断言版本）；权威版本记录 = 各子系统 `VERSION` 文件与 CHANGELOG。
>
> **当前状态与待部署事项** → 见 [`handover-history.md`](archive/handover-history.md)
> **权威版本记录** → 各子系统 CHANGELOG（本行仅总览快照，不断言版本；文档分治规范见 `docs/governance/document-governance.md`）

---

## 一、这是什么

跑在家用 NAS（<主机地址>）上的宏观情报 + 仿真系统。每天自动拉取全球宏观/地缘数据、写分析报告、推手机；GRV 告警时自动触发 12-Agent Monte Carlo 仿真，预测未来 24 个月概率路径。开阳（kaiyang）是只读可视化操作面板，展示天枢产出数据。

---

## 二、系统架构

```
FRED / GPR / GDELT / 新闻（RSSHub :12000；crucix 已于 2026-08-12 退场：G1 停容器，天枢不连 :3117，gscpi 改 NY Fed CSV 唯一源）
              │  62个调度任务（I15/I30/日档/月档）〔as-of 2026-10-10 · 复核: 容器内 `python3 -c "import scheduler; print(len(scheduler.JOBS))"`〕
              ▼
        ┌─────────────┐
        │  macro-scan  │  观测层（天枢）v3.8.69
        │              │  采集 → GRV向量 → LLM分析报告 → ntfy手机
        └──────┬──────┘
               │ GRV告警时写 sim_trigger.json
               ▼
        ┌─────────────┐
        │  macro-sim  │  仿真层（天璇）v2.0.51
        │              │  Monte Carlo×100 → 概率路径树 → ntfy手机
        └─────────────┘
               │ 落盘 data/*.json（只读契约文件）
               ▼
        ┌─────────────┐
        │   kaiyang   │  可视化操作面板（开阳）v1.11.44
        │              │  3D地球 + 经济面板 + 控制抽屉（:8080）
        └─────────────┘
               │ 落盘 data/*.json（只读契约文件）
               ▼
        ┌─────────────┐
        │  macro-ji   │  验证层（天玑）v1.0.0
        │             │  预测事后验证与校准（独立容器）
        └─────────────┘
```

| 子系统 | 别称 | 定位 | 容器模式 | 端口 | 详细文档 |
|--------|------|------|----------|------|---------|
| macro-scan | 天枢 | 观测层 | 热挂载（改代码即生效；改 `scheduler.py`/`control_server.py` 需 restart） | :8899 Web UI / :8900 Control API | `macro-scan/AGENTS.md` |
| macro-sim | 天璇 | 仿真层 | COPY模式（改代码需重建镜像） | — | `macro-sim/AGENTS.md` |
| kaiyang | 开阳 | 可视化面板 | nginx静态站 | :8080 | `kaiyang/AGENTS.md` |
| macro-ji | 天玑 | 验证层 | 独立容器 `macro-scan-tianji-1` + `macro-scan-tianji-cron-1`（同镜像，cron 跑 verify 定时任务） | — | `docs/tianji-design.md` |
| worldsim-pg | — | 数据底座 | 独立容器（pgvector/pgvector:pg16） | 5432（内网） | — |

---

## 三、日常使用

**手机订阅**：ntfy 客户端订阅 `$NTFY_TOPIC` 接收报告。

**最常用指令**（向 `$NTFY_CMD_TOPIC` 发送，格式 `1900 <指令>`）：

| 指令 | 效果 |
|------|------|
| `1900 narrative` | 立即生成今日世界摘要 |
| `1900 both` | 立即生成中美全球报告 |
| `1900 hypothesis 台海 L2` | 触发假设推演 |
| `1900 status` | 系统运行状态摘要 |
| `1900 situations` | 查看追踪事件状态 |
| `1900 ask 你的问题` | 自由问答（约30秒） |

**Web UI**：`http://<主机地址>:8899`（天枢）· `http://<主机地址>:8080`（开阳面板）

---

## 四、文档导航

| 文档 | 路径 | 适合谁读 |
|------|------|---------|
| **当前状态 + 待部署** | `docs/archive/handover-history.md` | 每次维护必读，动态快照 |
| **时间门控路线图** | `docs/roadmap.md` | 下一步要做什么 |
| **本文件** | `docs/overview.md` | 任何人，架构说明（稳定部分）|
| 天枢变更日志 | `macro-scan/CHANGELOG.md`（v3.8.25 起）／`macro-scan/TuiYan_CHANGELOG.md`（v3.8.24 及更早） | 追查具体变更 |
| 天璇变更日志 | `macro-sim/CHANGELOG.md` | 追查具体变更 |
| AI 工作入口 | `AGENTS.md` | AI agent 用 |

---

## 五、快速运维

```bash
# SSH 连接 NAS
ssh TSX@<主机地址>

# 查看容器状态
docker ps | grep -E "macro-scan|macro-sim|kaiyang"

# macro-scan 日志
docker exec macro-scan-macro-scan-1 tail -20 /var/log/macro-scan/scheduler.log

# macro-sim 日志
docker logs macro-sim --tail 50

# 重新部署（NAS 上执行）—— ⚠️ 按部署型区分，不能混用；原 `/s/world-sim/deploy.sh` 路径已不存在
# 天枢（bind mount 型）：rsync 到运行区即生效（改 scheduler.py/control_server.py 才需 restart）
cd /vol2/1000/software/macro-scan && bash deploy.sh

# 天璇（COPY 型，无 deploy.sh）：tag 备份 → docker cp 新码 → commit → recreate
cd /vol2/1000/software/world-sim/macro-sim && docker compose up -d --force-recreate

# 天玑（COPY 型 + build 段）：先 build（Dockerfile COPY 须列出新文件）再 recreate
cd /vol2/1000/software/world-sim/macro-ji && docker compose build && docker compose up -d --force-recreate

# 开阳（前端构建）：唯一路径
bash /vol2/1000/software/kaiyang/deploy.sh
```

**出问题先看**：
1. `docker ps` — 容器是否在线
2. scheduler.log / docker logs — 最近错误
3. `docs/archive/handover-history.md` 已知问题节

---

## 六、模型配置（2026-10-09 / 10-10 重构后）

**模型名只写配置** —— `data/llm_config.json`（开阳控制台可改）是唯一真源，代码中不再有参与取值的模型字面量。

四个子系统共用同一份配置：天枢经 `核心代码/llm_usage.py`、天璇与天玑经各自 `llm_cfg.py`（同一文件的两个跨容器副本）解析。
取值链为**四层兜底：主配置 → `.bak` 快照 → git 模板 → env（过渡）**，回落全程留痕（`[FALLBACK]` 日志 + `config_source` 字段）。
共 **9 个使用点**；每日 08:10 由 `scripts/check_llm_config.py` 巡检九项（含全仓模型字面量对拍、来源报警、模型可用性哨兵、跨容器副本一致）。
