# A3a 控制 API — 开阳对接文档

> 天枢（macro-scan）调度器控制接口

> **协议状态（2026-08-04 修正）**：本文档原定义「文件投递」协议为当前协议，但经实测核实——
> **该协议从未落地实现**（scheduler 无 control/in 轮询逻辑、开阳源码零 cmd_id 引用）。
> **实际当前协议 = HTTP REST 控制 API**（天枢 control_server.py，FastAPI :8900），见 §0。
> 「文件投递」章节保留作「未采纳设计备选（未实现）」，仅作历史参考，勿按此对接。

## 0. 实际当前协议：HTTP REST（:8900）

- 端点基础：`http://192.168.31.108:8900/api/v1/control/`（docker-compose 已暴露 8900:8900）
- 端点清单（FastAPI，详见天枢 control_server.py docstring）：
  - `GET  /api/v1/control/health` — 健康检查
  - `GET  /api/v1/control/fetchers` — 采集源列表（含 last_ok 真实健康探测）
  - `POST /api/v1/control/fetchers/{id}/pause` — 暂停（返回 fetcher_id/updated_at/affected_fetchers）
  - `POST /api/v1/control/fetchers/{id}/resume` — 恢复（同上）
  - `PUT  /api/v1/control/fetchers/{id}/schedule` — 调整频率
  - `GET  /api/v1/control/fetchers/{id}/logs?lines=N` — 日志
  - `GET  /api/v1/control/operations/{op_id}` — 操作状态轮询
- 鉴权：Bearer Token（`CONTROL_TOKEN` 环境变量；未设置则跳过鉴权——生产建议设置）
- CORS：已内置 allow_origins=["*"]（开阳纯静态直连可用；如需收敛可改 allowlist）
- 开阳侧客户端：`kaiyang/src/lib/controlApi.ts` + `src/config/controlConfig.ts`
- **与 ntfy 命令通道的关系**：ntfy 命令通道（ntfy_listener.py，远程发令 topic=NTFY_CMD_TOPIC）面向
  外部设备远程触发（生成报告/verify/ask）；开阳控制 API 面向面板内采集源控制（LIST/PAUSE/RESUME/RERUN/schedule）。
  两者并存、职责不同、不互斥。

---

## 1. 通信方式（未采纳设计备选——文件投递，未实现）

**以下为历史设计备选，从未落地，勿按此对接。**

**文件投递，零网络依赖**（原设计）。

开阳写命令 JSON 到天枢容器内目录 `/workspace/data/control/in/`，scheduler 每 2 秒轮询处理，
完成后写响应到 `/workspace/data/control/out/{cmd_id}.json`，原命令归档到 `processed/`。

```
/workspace/data/control/
├── in/                    # 开阳写命令。命名：{uuid}.json
├── out/                   # 天枢写响应。命名：与命令 id 字段一致
└── processed/             # 已处理命令归档
```

**文件写入规则**（原子写，防半读）：

```bash
# ① 先写临时文件
echo '{"id":"abc","ts":"...","cmd":"LIST","params":{}}' > /workspace/data/control/in/abc.tmp
# ② 原子重命名
mv /workspace/data/control/in/abc.tmp /workspace/data/control/in/abc.json
```

---

## 2. 命令格式（Command Envelope）

> **⚑ 未采纳标注（2026-08-06）**：本节及 §3-§6 的命令信封 / 响应格式 / 状态枚举 / 幂等规则均属于**文件投递协议（未采纳、未实现）**，**现役协议 = HTTP REST（见 §0）**。本节内容仅作历史设计参考，**勿按此对接**。若需命令语义对照，见 §0 REST 端点清单与天枢 `control_server.py` docstring。

```jsonc
{
  "id": "550e8400-e29b-41d4-a716-446655440000",   // UUID v4，唯一标识，响应文件以此命名
  "ts": "2026-08-01T14:30:00Z",                     // ISO 8601 发起时间
  "cmd": "LIST",                                    // 命令动词（见下表）
  "params": {                                       // 参数（按命令而异）
    "task": "fred_fetch",                           // 目标任务名
    "n": 20                                         // LOG 返回条数
  }
}
```

### 命令一览

| cmd | 需要 params.task | 说明 |
|-----|:---:|------|
| `LIST` | ❌ | 列出所有任务状态 |
| `PAUSE` | ✅ | 暂停任务（跳过后续定时触发，不终止运行中实例） |
| `RESUME` | ✅ | 恢复已暂停的任务 |
| `RERUN` | ✅ | 手动触发执行一次（运行中则拒绝） |
| `LOG` | ✅ | 返回最近 N 条执行日志（默认 20） |
| `RELOAD` | ❌ | 重新加载 jobs.json 配置 |

---

## 3. 响应格式

```jsonc
{
  "cmd_id": "550e8400-e29b-41d4-a716-446655440000",  // ⚠️ 字段名是 cmd_id，不是 id
  "cmd": "LIST",                                      // 回显命令动词
  "status": "OK",                                     // 见状态枚举
  "message": "共 27 个任务",                           // 人类可读消息（成功或错误说明）
  "completed_at": "2026-08-01T14:30:01.234+00:00",   // 天枢完成时间
  "data": { ... }                                     // 按命令而异（见各命令子节）
}
```

> ⚠️ **与旧 PRD 的差异**（开阳对接以本文档为准）：
> - status 全部**大写**（`OK`/`ERROR`/…），非 `"ok"`/`"error"`
> - 命令标识字段名是 `cmd_id`，非 `id`
> - 错误信息在 `message` 字段（扁平字符串），非嵌套 `error.code`
> - 多了 `cmd` 回显字段和 `completed_at` 时间戳

---

## 4. 状态枚举

| status | 含义 | 开阳建议处理 |
|--------|------|-------------|
| `OK` | 执行成功 | 正常展示 data |
| `ERROR` | 通用错误 | 展示 message |
| `NOT_FOUND` | 任务不存在 | 提示用户任务名有误，或引导补建 |
| `TASK_BUSY` | 任务正在运行 | 提示"请等当前运行结束" |
| `DUPLICATE` | 重复命令（相同 id 已执行过） | 忽略，不弹错误 |
| `RELOADED` | RELOAD 成功 | 展示重载统计 |

**开阳判断成功/失败**：

```javascript
// 推荐写法：大小写无关
if (response.status === "OK") {
  // 成功
} else if (response.status === "DUPLICATE") {
  // 忽略重复
} else {
  // 其他都是错误，展示 response.message
}
```

---

## 5. 各命令详细格式

### 5.1 LIST — 列出所有任务

**命令**：
```json
{"id": "u1", "ts": "2026-08-01T14:30:00Z", "cmd": "LIST", "params": {}}
```

**响应**：
```json
{
  "cmd_id": "u1",
  "cmd": "LIST",
  "status": "OK",
  "message": "共 27 个任务",
  "completed_at": "2026-08-01T14:30:01Z",
  "data": {
    "tasks": [
      {
        "name": "fred_fetch",
        "schedule": "0530",
        "script": "fetch_fred_history.py",
        "last_run_start": "2026-08-01T05:30:05",
        "last_run_end": "2026-08-01T05:31:22",
        "last_exit_code": 0,
        "run_count": 31,
        "error_count": 0,
        "paused": false,
        "enabled": true,
        "is_running": false
      }
    ]
  }
}
```

**task 字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 任务唯一标识 |
| `schedule` | string | `HHMM` 每日定时 或 `I{min}` 间隔 |
| `script` | string | 执行的脚本文件名 |
| `last_run_start` | string\|null | 最近启动时间（ISO 8601） |
| `last_run_end` | string\|null | 最近结束时间 |
| `last_exit_code` | int\|null | 最近退出码（0=正常） |
| `run_count` | int | 累计运行次数 |
| `error_count` | int | 累计异常次数 |
| `paused` | bool | 是否已暂停 |
| `enabled` | bool | 是否启用 |
| `is_running` | bool | 是否正在运行 |


### 5.2 PAUSE — 暂停任务

**命令**：
```json
{"id": "u2", "ts": "2026-08-01T14:31:00Z", "cmd": "PAUSE", "params": {"task": "fred_fetch"}}
```

**成功响应**：
```json
{"cmd_id": "u2", "cmd": "PAUSE", "status": "OK", "message": "已暂停: 'fred_fetch'", "data": null}
```

**失败响应**（任务不存在）：
```json
{"cmd_id": "u2", "cmd": "PAUSE", "status": "NOT_FOUND", "message": "任务不存在: 'fred_fetch'"}
```

> PAUSE 只跳过后续定时触发，**不终止**已经在运行的子进程。


### 5.3 RESUME — 恢复任务

**命令**：
```json
{"id": "u3", "ts": "2026-08-01T14:32:00Z", "cmd": "RESUME", "params": {"task": "fred_fetch"}}
```

**成功响应**：
```json
{"cmd_id": "u3", "cmd": "RESUME", "status": "OK", "message": "已恢复: 'fred_fetch'"}
```


### 5.4 RERUN — 手动触发

**命令**：
```json
{"id": "u4", "ts": "2026-08-01T14:33:00Z", "cmd": "RERUN", "params": {"task": "crypto"}}
```

**成功响应**：
```json
{"cmd_id": "u4", "cmd": "RERUN", "status": "OK", "message": "已触发: 'crypto' (PID=12345)"}
```

**失败响应**（正运行）：
```json
{"cmd_id": "u4", "cmd": "RERUN", "status": "TASK_BUSY", "message": "任务正在运行: 'crypto'"}
```

**失败响应**（不存在）：
```json
{"cmd_id": "u4", "cmd": "RERUN", "status": "NOT_FOUND", "message": "任务不存在: 'crypto'"}
```


### 5.5 LOG — 查询日志

**命令**：
```json
{"id": "u5", "ts": "2026-08-01T14:34:00Z", "cmd": "LOG", "params": {"task": "fred_fetch", "n": 10}}
```

**响应**：
```json
{
  "cmd_id": "u5",
  "cmd": "LOG",
  "status": "OK",
  "message": "查到 10 条日志",
  "data": {
    "entries": [
      {"ts": "2026-08-01 05:30:05", "type": "FIRING", "message": "FIRING: fred_fetch (fetch_fred_history.py)"},
      {"ts": "2026-08-01 05:30:05", "type": "SPAWNED", "message": "Job spawned PID=157: fred_fetch"},
      {"ts": "2026-08-01 05:31:22", "type": "COMPLETED", "message": "COMPLETED: fred_fetch PID=157 EXIT=0"}
    ]
  }
}
```

**日志类型**：
| type | 含义 |
|------|------|
| `FIRING` | 定时触发 |
| `SPAWNED` | 子进程已启动 |
| `COMPLETED` | 子进程已结束 |


### 5.6 RELOAD — 重载配置

**命令**：
```json
{"id": "u6", "ts": "2026-08-01T14:35:00Z", "cmd": "RELOAD", "params": {}}
```

**响应**：
```json
{
  "cmd_id": "u6",
  "cmd": "RELOAD",
  "status": "RELOADED",
  "message": "已重载配置: 新增 2 / 删除 1 / 保留 24"
}
```

---

## 6. 命令幂等

相同 `id` 的命令**只执行一次**。重复投递返回：

```json
{"cmd_id": "u6", "cmd": "RELOAD", "status": "DUPLICATE", "message": "命令已执行过，忽略"}
```

开阳可安全重试（网络超时重发不会导致重复执行）。

---

## 7. 任务名一览

当前可用任务名（共 27 个）：

```
fred_fetch, compute_fci, compute_probit,
world_macro, china_macro, china_pmi,
energy, commodity,
fx,
crypto, crypto_extra,
rss_news, gdelt_geo,
earthquake, disaster, firms, climate_signals,
gdelt_weak_signal, ged, sanctions, gpr,
opensky, bdi,
oni, fao_food, giss_temp, sipri
```

> 完整列表可通过 `LIST` 命令实时获取，此表仅供前端预填下拉框参考。

---

*文档版本：v1.0 · 2026-08-06（§0 HTTP REST 为现役协议；§1-§6 文件投递协议未采纳，保留作历史参考）*
