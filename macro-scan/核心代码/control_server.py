"""
control_server.py — 天枢控制 API（A3a）

供开阳控制面板调用。端口 8900，独立进程，由 entrypoint.sh 或 scheduler.py 启动。

端点：
  GET  /api/v1/control/fetchers                   — 列出所有采集源状态
  GET  /api/v1/control/fetchers/{id}/logs          — 查采集源日志尾部
  GET  /api/v1/control/fetchers/{id}/allowed-schedules — 查可用频率
  POST /api/v1/control/fetchers/rerun              — 立即重跑
  POST /api/v1/control/fetchers/{id}/pause         — 暂停
  POST /api/v1/control/fetchers/{id}/resume        — 恢复
  PUT  /api/v1/control/fetchers/{id}/schedule      — 调整频率
  GET  /api/v1/control/operations/{id}             — 查操作状态

鉴权：Bearer Token（CONTROL_TOKEN 环境变量，未设置则跳过鉴权）
"""
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, Depends, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("[control_server] 需要 fastapi + uvicorn: pip install fastapi uvicorn")
    raise

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = os.environ.get("OPENCLAW_WORKSPACE",
                               os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR = os.path.join(WORKSPACE, "data")

PYTHON     = "python3"
WORKDIR    = os.path.join(WORKSPACE, "核心代码")
LOG_DIR    = "/var/log/macro-scan"
STATE_FILE = os.path.join(DATA_DIR, "scheduler_state.json")
PAUSE_FILE = os.path.join(DATA_DIR, "control_pause.json")
GRV_WEIGHTS_PATH = os.path.join(WORKSPACE, "config", "grv_weights.yaml")
CONTROL_TOKEN = os.environ.get("CONTROL_TOKEN", "")

# 操作状态缓存（in-memory，进程重启丢失，可接受）
_operations: dict = {}

app = FastAPI(title="天枢控制 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 鉴权 ──────────────────────────────────────────────────────
def _check_token(request: Request):
    if not CONTROL_TOKEN:
        return  # 未配置 token 则跳过鉴权（开发环境）
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != CONTROL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── 工具函数 ──────────────────────────────────────────────────
def _load_state() -> dict:
    """读取 scheduler 落盘的状态快照。"""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_paused() -> set:
    """读取已暂停的 job 集合。"""
    try:
        with open(PAUSE_FILE, encoding="utf-8") as f:
            return set(json.load(f).get("paused", []))
    except Exception:
        return set()


def _save_paused(paused: set):
    """写回暂停状态。"""
    tmp = PAUSE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"paused": sorted(paused), "updated": datetime.now(timezone.utc).isoformat()[:19]}, f)
    os.replace(tmp, PAUSE_FILE)


def _make_op(op_type: str, fetcher_ids: list, idempotency_key: str = "") -> dict:
    op_id = f"op_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()[:19]
    op = {
        "operation_id": op_id,
        "command_id": f"cmd-{uuid.uuid4().hex[:8]}",
        "idempotency_key": idempotency_key,
        "type": op_type,
        "status": "accepted",
        "progress": 0,
        "progress_message": "指令已接收，写入执行队列",
        "affected_fetchers": fetcher_ids,
        "result": None,
        "error": None,
        "created_at": now,
        "completed_at": None,
    }
    _operations[op_id] = op
    return op


def _finish_op(op_id: str, success: bool, msg: str = ""):
    op = _operations.get(op_id)
    if not op:
        return
    op["status"] = "completed" if success else "failed"
    op["progress"] = 100
    op["progress_message"] = msg or ("执行完成" if success else "执行失败")
    op["completed_at"] = datetime.now(timezone.utc).isoformat()[:19]
    op["result"] = {"success": success}


def _job_to_fetcher(job_name: str, state: dict, paused: set) -> dict:
    """把 scheduler JOBS 的一行转成开阳期待的 Fetcher 对象。"""
    job_state = state.get(job_name, {})
    last_ts = job_state.get("last_run_ts")
    last_ok = job_state.get("last_ok", True)
    sched   = job_state.get("schedule", "")
    return {
        "id":          job_name,
        "name":        job_name.replace("_", " ").title(),
        "status":      "paused" if job_name in paused else ("error" if not last_ok else "running"),
        "schedule":    sched,
        "last_run_at": datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat() if last_ts else None,
        "last_status": "failed" if not last_ok else "success",
        "next_run_at": None,  # scheduler 不预算下次时间
        "enabled":     job_name not in paused,
    }


# ── 端点 ──────────────────────────────────────────────────────

@app.get("/api/v1/control/fetchers")
def list_fetchers(request: Request):
    _check_token(request)
    state  = _load_state()
    paused = _load_paused()
    jobs   = state.get("jobs", list(state.keys()))
    if not jobs:
        # state 文件尚未生成时返回空列表（不报错）
        return {"fetchers": [], "total": 0, "generated_at": datetime.now(timezone.utc).isoformat()[:19]}
    fetchers = [_job_to_fetcher(j, state, paused) for j in jobs]
    return {"fetchers": fetchers, "total": len(fetchers),
            "generated_at": datetime.now(timezone.utc).isoformat()[:19]}


@app.get("/api/v1/control/fetchers/{fetcher_id}/logs")
def get_logs(fetcher_id: str, request: Request, lines: int = 50):
    _check_token(request)
    log_file = os.path.join(LOG_DIR, f"{fetcher_id}.log")
    # 尝试常见别名
    aliases = {
        "fred_fetch": "fred", "gpr_fetch": "gpr_fetch", "china_fetch": "china",
        "grv_update": "grv", "weak_signal": "scan",
    }
    if fetcher_id in aliases:
        log_file = os.path.join(LOG_DIR, f"{aliases[fetcher_id]}.log")
    if not os.path.exists(log_file):
        return {"lines": [], "log_file": log_file, "note": "log file not found"}
    try:
        with open(log_file, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = [l.rstrip() for l in all_lines[-lines:]]
        return {"lines": tail, "log_file": log_file, "total_lines": len(all_lines)}
    except Exception as e:
        return {"lines": [], "error": str(e)}


@app.get("/api/v1/control/fetchers/{fetcher_id}/allowed-schedules")
def allowed_schedules(fetcher_id: str, request: Request):
    _check_token(request)
    state = _load_state()
    current = state.get(fetcher_id, {}).get("schedule", "I15")
    return {
        "current": current,
        "options": [
            {"label": "每15分钟", "value": "I15",  "description": "≤50% 安全水位"},
            {"label": "每小时",   "value": "I60",  "description": "≤50% 安全水位"},
            {"label": "每6小时",  "value": "H6",   "description": "≤50% 安全水位"},
            {"label": "每12小时", "value": "H12",  "description": "≤50% 安全水位"},
            {"label": "每天",     "value": "H24",  "description": "日频采集"},
        ],
    }


@app.post("/api/v1/control/fetchers/rerun")
async def rerun_fetchers(request: Request):
    _check_token(request)
    body = await request.json()
    fetcher_ids  = body.get("fetcher_ids", [])
    idempotency  = body.get("idempotency_key", "")
    if not fetcher_ids:
        raise HTTPException(status_code=400, detail="fetcher_ids required")

    op = _make_op("rerun", fetcher_ids, idempotency)
    op_id = op["operation_id"]

    # 异步后台执行
    import threading
    def _run():
        errors = []
        for fid in fetcher_ids:
            script = f"{fid}.py"
            path   = os.path.join(WORKDIR, script)
            if not os.path.exists(path):
                errors.append(f"{fid}: script not found")
                continue
            try:
                log_file = os.path.join(LOG_DIR, f"{fid}.log")
                with open(log_file, "a") as lf:
                    subprocess.Popen([PYTHON, path], cwd=WORKDIR, stdout=lf, stderr=subprocess.STDOUT)
            except Exception as e:
                errors.append(f"{fid}: {e}")
        _finish_op(op_id, success=not errors,
                   msg="执行完成" if not errors else f"部分失败: {'; '.join(errors)}")

    threading.Thread(target=_run, daemon=True).start()
    op["status"] = "running"
    op["progress"] = 10
    op["progress_message"] = "正在启动采集进程..."
    return {"operation_id": op_id, "status": "accepted", "affected_fetchers": fetcher_ids}


@app.post("/api/v1/control/fetchers/{fetcher_id}/pause")
def pause_fetcher(fetcher_id: str, request: Request):
    _check_token(request)
    paused = _load_paused()
    paused.add(fetcher_id)
    _save_paused(paused)
    op = _make_op("pause", [fetcher_id])
    _finish_op(op["operation_id"], True, f"{fetcher_id} 已暂停")
    return {"operation_id": op["operation_id"], "status": "completed",
            "affected_fetchers": [fetcher_id]}


@app.post("/api/v1/control/fetchers/{fetcher_id}/resume")
def resume_fetcher(fetcher_id: str, request: Request):
    _check_token(request)
    paused = _load_paused()
    paused.discard(fetcher_id)
    _save_paused(paused)
    op = _make_op("resume", [fetcher_id])
    _finish_op(op["operation_id"], True, f"{fetcher_id} 已恢复")
    return {"operation_id": op["operation_id"], "status": "completed",
            "affected_fetchers": [fetcher_id]}


@app.put("/api/v1/control/fetchers/{fetcher_id}/schedule")
async def update_schedule(fetcher_id: str, request: Request):
    """调整频率：写入 control_overrides.json，scheduler 下一轮读取。"""
    _check_token(request)
    body = await request.json()
    new_schedule = body.get("schedule")
    if not new_schedule:
        raise HTTPException(status_code=400, detail="schedule required")

    overrides_path = os.path.join(DATA_DIR, "control_overrides.json")
    try:
        overrides = json.load(open(overrides_path)) if os.path.exists(overrides_path) else {}
    except Exception:
        overrides = {}
    overrides.setdefault("schedules", {})[fetcher_id] = new_schedule
    overrides["updated"] = datetime.now(timezone.utc).isoformat()[:19]
    tmp = overrides_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(overrides, f, indent=2)
    os.replace(tmp, overrides_path)

    op = _make_op("schedule_update", [fetcher_id])
    _finish_op(op["operation_id"], True, f"{fetcher_id} 频率已更新为 {new_schedule}（下次触发生效）")
    return {"operation_id": op["operation_id"], "status": "completed",
            "fetcher_id": fetcher_id, "new_schedule": new_schedule}


@app.get("/api/v1/control/operations/{operation_id}")
def get_operation(operation_id: str, request: Request):
    _check_token(request)
    op = _operations.get(operation_id)
    if not op:
        raise HTTPException(status_code=404, detail="operation not found")
    return op


@app.get("/api/v1/control/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()[:19]}


if __name__ == "__main__":
    port = int(os.environ.get("CONTROL_PORT", "8900"))
    print(f"[control_server] 启动于 :{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
