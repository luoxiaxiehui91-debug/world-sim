# 世界推演系统 · 总览

> macro-scan v3.8.17（天枢）· macro-sim **v2.0.40**（天璇）· kaiyang v1.10.8（开阳）· macro-ji v1.0.0（天玑）· as-of 2026-08-12
>
> **当前状态与待部署事项** → 见 [`handover-history.md`](archive/handover-history.md)
> **权威版本记录** → 各子系统 CHANGELOG（本行仅总览快照，不断言版本；文档分治规范见 `docs/governance/document-governance.md`）

---

## 一、这是什么

跑在家用 NAS（192.168.31.108）上的宏观情报 + 仿真系统。每天自动拉取全球宏观/地缘数据、写分析报告、推手机；GRV 告警时自动触发 12-Agent Monte Carlo 仿真，预测未来 24 个月概率路径。开阳（kaiyang）是只读可视化操作面板，展示天枢产出数据。

---

## 二、系统架构

```
FRED / GPR / GDELT / 新闻（RSSHub :12000；crucix 已于 2026-08-12 退场：G1 停容器，天枢不连 :3117，gscpi 改 NY Fed CSV 唯一源）
              │  49个调度任务（I15/I30/日档/月档）
              ▼
        ┌─────────────┐
        │  macro-scan  │  观测层（天枢）v3.8.15
        │              │  采集 → GRV向量 → LLM分析报告 → ntfy手机
        └──────┬──────┘
               │ GRV告警时写 sim_trigger.json
               ▼
        ┌─────────────┐
        │  macro-sim  │  仿真层（天璇）v2.0.24
        │              │  Monte Carlo×100 → 概率路径树 → ntfy手机
        └─────────────┘
               │ 落盘 data/*.json（只读契约文件）
               ▼
        ┌─────────────┐
        │   kaiyang   │  可视化操作面板（开阳）v1.9.0
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
| macro-scan | 天枢 | 观测层 | 热挂载（改代码即生效） | :8899 | `macro-scan/AGENTS.md` |
| macro-sim | 天璇 | 仿真层 | COPY模式（改代码需重建镜像） | — | `macro-sim/AGENTS.md` |
| kaiyang | 开阳 | 可视化面板 | nginx静态站 | :8080 | `kaiyang/AGENTS.md` |
| macro-ji | 天玑 | 验证层 | 独立容器 `macro-scan-tianji-1`（healthy） | — | `docs/tianji-design.md` |

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

**Web UI**：`http://192.168.31.108:8899`（天枢）· `http://192.168.31.108:8080`（开阳面板）

---

## 四、文档导航

| 文档 | 路径 | 适合谁读 |
|------|------|---------|
| **当前状态 + 待部署** | `docs/archive/handover-history.md` | 每次维护必读，动态快照 |
| **时间门控路线图** | `ROADMAP.md` | 下一步要做什么 |
| **本文件** | `docs/overview.md` | 任何人，架构说明（稳定部分）|
| 天枢变更日志 | `macro-scan/TuiYan_CHANGELOG.md` | 追查具体变更 |
| 天璇变更日志 | `macro-sim/CHANGELOG.md` | 追查具体变更 |
| AI 工作入口 | `AGENTS.md` | AI agent 用 |

---

## 五、快速运维

```bash
# SSH 连接 NAS
ssh TSX@192.168.31.108

# 查看容器状态
docker ps | grep -E "macro-scan|macro-sim|kaiyang"

# macro-scan 日志
docker exec macro-scan-macro-scan-1 tail -20 /var/log/macro-scan/scheduler.log

# macro-sim 日志
docker logs macro-sim --tail 50

# 重新部署（NAS 上执行）
bash /s/world-sim/deploy.sh macro-scan   # rsync + restart
bash /s/world-sim/deploy.sh macro-sim    # rsync + rebuild + restart
```

**出问题先看**：
1. `docker ps` — 容器是否在线
2. scheduler.log / docker logs — 最近错误
3. `docs/archive/handover-history.md` 已知问题节
