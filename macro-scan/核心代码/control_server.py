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
import html
import ipaddress
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
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
WORKDIR    = os.path.dirname(os.path.abspath(__file__))  # 容器内 = /app（volume mount 路径）
LOG_DIR    = "/var/log/macro-scan"
STATE_FILE = os.path.join(DATA_DIR, "scheduler_state.json")
PAUSE_FILE = os.path.join(DATA_DIR, "control_pause.json")
GRV_WEIGHTS_PATH = os.path.join(WORKSPACE, "config", "grv_weights.yaml")
CONTROL_TOKEN = os.environ.get("CONTROL_TOKEN", "")

# P0-D：调度器心跳新鲜度阈值（scheduler 每 60s 落盘 + 循环 sleep 30s，正常 <120s）
# 超阈值视为调度器失联 → 面板 last_ok 全 False（真实健康探测，非硬编码 True）
SCHEDULER_STALE_SECONDS = 240

# 操作状态缓存（in-memory，进程重启丢失，可接受）
_operations: dict = {}

app = FastAPI(title="天枢控制 API", version="1.1.0")
# P1-D (2026-08-15, 审查 C03/H15): CORS 收窄——从 allow_origins=["*"] 改为开阳面板实际来源，
# 阻止任意网站跨域驱动控制 API（配合 fail-closed token）。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in [
        os.environ.get("KAIYANG_ORIGIN", ""),  # 开阳面板来源（部署时按需配置，如 http://<你的主机>:8080）
        "http://localhost:8080",               # 本地开发
        "http://127.0.0.1:8080",
    ] if o],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 鉴权 ──────────────────────────────────────────────────────
def _check_token(request: Request):
    if not CONTROL_TOKEN:
        # P1-D (2026-08-15, 审查 C02): fail-closed——未配置 token 时拒绝所有控制操作，
        # 不再"跳过鉴权"。原 fail-open 使生产环境运控 API 零鉴权（全仓 compose 均未设
        # 该变量）。若需启用控制 API：运行区 compose environment 设 CONTROL_TOKEN +
        # 开阳面板填同值 token。
        raise HTTPException(status_code=503, detail="CONTROL_TOKEN 未配置，控制 API 已禁用（fail-closed）")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != CONTROL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── 工具函数 ──────────────────────────────────────────────────
def _scheduler_alive() -> bool:
    """P0-D 真实健康探测：state 文件 mtime/心跳新鲜度 + scheduler 进程存活。

    返回 True 仅当：STATE_FILE 存在、mtime 在 SCHEDULER_STALE_SECONDS 内、
    state.heartbeat 时间戳新鲜、且 scheduler.py 进程在跑（/proc cmdline 探测）。
    任一项失守 → False。容器无 ps 命令，故用 /proc 扫描（不可用则退化为心跳判活）。
    """
    try:
        if not os.path.exists(STATE_FILE):
            return False
        mtime_age = time.time() - os.path.getmtime(STATE_FILE)
        if mtime_age > SCHEDULER_STALE_SECONDS:
            return False
        state = _load_state()
        hb = state.get("heartbeat")
        if hb is None or (time.time() - float(hb)) > SCHEDULER_STALE_SECONDS:
            return False
        # scheduler 进程存活探测（容器无 ps，走 /proc/*/cmdline；失败退化为心跳判活）
        try:
            import glob
            alive = False
            for cmd_path in glob.glob("/proc/[0-9]*/cmdline"):
                try:
                    with open(cmd_path, "rb") as f:
                        cmd = f.read().decode("utf-8", errors="ignore")
                    if "scheduler.py" in cmd:
                        alive = True
                        break
                except Exception:
                    continue
            if not alive:
                return False
        except Exception:
            pass  # /proc 不可用时仅凭心跳判活（留痕：见注释）
        return True
    except Exception:
        return False


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
        json.dump({"paused": sorted(paused), "updated": datetime.now().astimezone().isoformat(timespec="seconds")}, f)
    os.replace(tmp, PAUSE_FILE)


def _make_op(op_type: str, fetcher_ids: list, idempotency_key: str = "") -> dict:
    op_id = f"op_{uuid.uuid4().hex[:8]}"
    now = datetime.now().astimezone().isoformat(timespec="seconds")
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
    op["completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    op["result"] = {"success": success}


def _job_to_fetcher(job_name: str, state: dict, paused: set, scheduler_alive: bool) -> dict:
    """把 scheduler JOBS 的一行转成开阳期待的 Fetcher 对象。

    P0-D：last_ok 不再读硬编码默认 True，改用真实健康探测——
    scheduler 失联（state 过期/心跳过期/进程消失）时该 job 一律置 False；
    scheduler 存活时取 scheduler 落盘的真实 spawn 结果。
    """
    job_state = state.get(job_name, {})
    last_ts = job_state.get("last_run_ts")
    # 真实健康探测：scheduler 失联 → 该 job 视为不健康（非硬编码 True）
    last_ok = scheduler_alive and bool(job_state.get("last_ok", False))
    sched   = job_state.get("schedule", "")
    return {
        "id":          job_name,
        "name":        job_name.replace("_", " ").title(),
        "status":      "paused" if job_name in paused else ("error" if not last_ok else "running"),
        "schedule":    sched,
        "last_run_at": datetime.fromtimestamp(last_ts).astimezone().isoformat() if last_ts else None,
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
    scheduler_alive = _scheduler_alive()
    jobs   = state.get("jobs", list(state.keys()))
    if not jobs:
        # state 文件尚未生成时返回空列表（不报错）
        return {"fetchers": [], "total": 0, "scheduler_alive": scheduler_alive,
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    fetchers = [_job_to_fetcher(j, state, paused, scheduler_alive) for j in jobs]
    return {"fetchers": fetchers, "total": len(fetchers),
            "scheduler_alive": scheduler_alive,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds")}


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

    # 白名单：仅允许 scheduler.py JOBS 中已知的 fetcher 名称，防路径遍历
    _KNOWN_FETCHER_IDS = {
        "fred_fetch", "compute_fci", "compute_probit", "gpr_fetch", "china_fetch",
        "world_macro", "fx_fetch", "crypto", "weak_signal", "sanctions", "earthquake",
        "gdelt_geo", "energy", "crypto_extra", "news", "hdx", "bdi", "fao",
        "commodity_yahoo", "airtraffic_opensky", "energy_eia", "china_meso",
        "grv_update", "morning", "us_daily", "china_daily", "verify", "kb_update",
        "firms", "climate", "daily_narrative", "news_export", "narrative_proc",
        "defense_rss", "slow_vars",
        "situation_detect", "disaster", "dashboard", "verify_auto", "news_prune",
        "weekly_synthesis", "health_push",
        "market_quotes", "news_geo_feed", "fred_freshness", "tianji_trigger",
    }
    unknown = [fid for fid in fetcher_ids if fid not in _KNOWN_FETCHER_IDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知 fetcher_id，拒绝执行: {unknown}")

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
            "affected_fetchers": [fetcher_id],
            "fetcher_id": fetcher_id,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds")}


@app.post("/api/v1/control/fetchers/{fetcher_id}/resume")
def resume_fetcher(fetcher_id: str, request: Request):
    _check_token(request)
    paused = _load_paused()
    paused.discard(fetcher_id)
    _save_paused(paused)
    op = _make_op("resume", [fetcher_id])
    _finish_op(op["operation_id"], True, f"{fetcher_id} 已恢复")
    return {"operation_id": op["operation_id"], "status": "completed",
            "affected_fetchers": [fetcher_id],
            "fetcher_id": fetcher_id,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds")}


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
    overrides["updated"] = datetime.now().astimezone().isoformat(timespec="seconds")
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
    return {"status": "ok", "time": datetime.now().astimezone().isoformat(timespec="seconds")}


# ── 新闻标题按需抓取（08-16，开阳弹框显示真实新闻标题）─────────────────────
# GDELT GKG 事件无 title 字段；DOC API 标题回填被 429 限流。此端点按需抓取
# 用户点击的新闻 URL 页面 <title>——比 URL slug 伪标题（v1.11.19 实测无意义）
# 可靠得多。前端点击时调用 + localStorage 缓存，量小。
_NEWS_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
# 天枢容器直连外网不可达（实测 Network unreachable）——抓标题必须走 NAS 代理
_NEWS_PROXY_URL = os.environ.get("PROXY_URL", "")


def _is_public_url(url: str) -> bool:
    """SSRF 防护：仅放行公网 http/https（拒绝内网/回环/链路本地/保留地址）。"""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname
        if not host:
            return False
        # 域名类直接放行（DNS 后可能指向内网，但那是页面自身内容，非本服务内网探测）
        ip = None
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return True  # 域名，非字面 IP
        return not (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_multicast or ip.is_reserved or ip.is_unspecified)
    except Exception:
        return False


def _extract_title(body: bytes) -> str:
    """从 HTML 提取 <title>（正则 + 实体解码 + 截断）。"""
    try:
        text = body.decode("utf-8", "ignore")
    except Exception:
        text = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    title = re.sub(r"<[^>]+>", "", m.group(1))
    title = html.unescape(title).strip()
    title = re.sub(r"\s+", " ", title)
    return title[:200]


@app.get("/api/v1/control/news-title")
def news_title(url: str = "", request: Request = None):
    """按需抓取新闻 URL 页面 <title>。返回 {"title": "..."}，失败/不可信返回空。
    超时 6s + 只读前 64KB + SSRF 公网校验。"""
    _check_token(request)
    if not url or not _is_public_url(url):
        return {"title": ""}
    req = urllib.request.Request(url, headers=_NEWS_UA)
    # 天枢容器直连外网不可达 → 走 NAS 代理（与 fetch_* 一致）；失败静默返回空
    # ⚠ 超时 6s → 15s（08-16 实测：globalsecurity.org 经代理抓取 >6s 会超时
    #   → 用户弹框"标题：加载中…"后消失。点击是按需单次抓取，15s 可接受）
    try:
        proxy = urllib.request.ProxyHandler(
            {"http": _NEWS_PROXY_URL, "https": _NEWS_PROXY_URL})
        opener = urllib.request.build_opener(proxy)
        with opener.open(req, timeout=15) as r:
            body = r.read(65536)
        return {"title": _extract_title(body)}
    except Exception:
        return {"title": ""}


# ── LLM 使用点配置（08-16：开阳控制台统一修改模型）─────────────────────
@app.get("/api/v1/control/platform-models")
def platform_models(request: Request = None):
    """实时拉取指定平台可用模型全集（上游 /models 端点，服务端 1h 缓存）。
    失败返回 ok=False（前端回落静态清单）。"""
    _check_token(request)
    pid = (request.query_params.get("platform") or "").strip()
    if not pid:
        return {"ok": False, "error": "缺少 platform 参数"}
    try:
        from llm_usage import fetch_platform_models
        return {"ok": True, "platform": pid, "models": fetch_platform_models(pid)}
    except Exception as e:
        return {"ok": False, "platform": pid, "error": str(e)}


@app.get("/api/v1/control/llm-usage")
def llm_usage_list(request: Request = None):
    """LLM 使用点清单 + 当前生效配置 + 平台选项（开阳 LLM 配置面板数据源）。"""
    _check_token(request)
    try:
        from llm_usage import effective_models, platform_options
        return {"usages": effective_models(), "platforms": platform_options()}
    except Exception as e:
        return {"error": str(e)}


@app.put("/api/v1/control/llm-usage/{usage_id}")
async def llm_usage_update(usage_id: str, request: Request):
    """修改 LLM 使用点（平台 + 模型；写 data/llm_config.json，原子写+模板自动再生）。
    API key 禁走此通道：set_usage 对非空 key 硬拒报错（config 永不带 key，ADR-0013）；
    密钥走 POST /llm-secret 专用通道（write-only 写 config/.env，ADR-0015）。"""
    _check_token(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    platform = (body.get("platform") or "").strip()
    model = (body.get("model") or "").strip()
    api_key = body.get("api_key")
    try:
        from llm_usage import set_usage
        ok, msg = set_usage(usage_id, platform, model, api_key)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not ok:
        return {"ok": False, "error": msg}
    return {"ok": True, "usage_id": usage_id, "platform": platform, "model": model}


@app.post("/api/v1/control/llm-secret")
async def llm_secret_update(request: Request):
    """控制台密钥写入（write-only，09-03 ADR-0015）：{platform, api_key} → 校验后
    原子写 config/.env（0600，双 gitignore 覆盖），mtime 热读取即时生效、免 recreate。
    响应只回掩码，永不回明文；llm_config.json 永不带 key 不变量保持。"""
    _check_token(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    platform = (body.get("platform") or "").strip()
    api_key = body.get("api_key") or ""
    try:
        from llm_usage import set_platform_secret
        ok, msg = set_platform_secret(platform, api_key)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not ok:
        return {"ok": False, "error": msg}
    return {"ok": True, "message": msg}


@app.get("/api/v1/control/llm-secrets")
def llm_secrets_status(request: Request = None):
    """各平台密钥状态（仅掩码 + 来源，开阳面板展示；永不回明文）。"""
    _check_token(request)
    try:
        from llm_usage import secret_status
        return {"ok": True, "secrets": secret_status()}
    except Exception as e:
        return {"ok": False, "error": str(e), "secrets": []}


# ── 人工验证（08-17：开阳天玑 Tab 点选验证，补齐"待人工"渠道）────────────────

def _pg_exec(sql, params=()):
    """天枢侧 PG 执行（复用 pg_read.connect——autocommit + worldsim_app rw）。"""
    try:
        from pg_read import connect
    except ImportError:
        raise HTTPException(status_code=500, detail="pg_read 不可用")
    conn = connect()
    if conn is None:
        raise HTTPException(status_code=503, detail="PG 连接失败")
    return conn.execute(sql, params)


@app.get("/api/v1/control/predictions/human-pending")
def human_pending(request: Request, limit: int = 100):
    """列出全部待人工验证的地缘预测（awaiting_human，按验证截止排序）。"""
    _check_token(request)
    try:
        cur = _pg_exec(
            "SELECT id, created_at, due_at, scenario_id, final_prob, confidence_tier, "
            "content, outcome_definition, human_note "
            "FROM predictions WHERE status = 'awaiting_human' "
            "ORDER BY due_at ASC, created_at DESC LIMIT %s", (limit,))
        cols = [d.name for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")
    return {"predictions": rows, "total": len(rows)}


@app.post("/api/v1/control/predictions/verify")
async def verify_prediction(request: Request):
    """人工验证一条地缘预测：outcome 0|0.5|1（0=未发生 1=发生 0.5=部分/不确定）。
    幂等：仅 awaiting_human 可验证（已 verified 返回 409）。"""
    _check_token(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON body required")
    pred_id = (body.get("prediction_id") or "").strip()
    outcome = body.get("outcome")
    note = (body.get("note") or "").strip() or None
    if not pred_id or outcome not in (0, 0.5, 1):
        raise HTTPException(status_code=400, detail="prediction_id + outcome(0|0.5|1) 必填")
    try:
        cur = _pg_exec(
            "SELECT final_prob FROM predictions "
            "WHERE id = %s AND status = 'awaiting_human'", (pred_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=409, detail="预测不存在或已验证（仅 awaiting_human 可验证）")
        final_prob = float(row[0])
        brier = round((final_prob - float(outcome)) ** 2, 4)
        cur = _pg_exec(
            "UPDATE predictions SET status = 'verified', outcome_value = %s, "
            "brier_score = %s, verified_at = CURRENT_TIMESTAMP, "
            "verified_by = 'human', human_note = %s "
            "WHERE id = %s AND status = 'awaiting_human'",   # 08-18 P1-8：UPDATE 加 status 守卫（防 SELECT/UPDATE 间 TOCTOU 连点）
            (float(outcome), brier, note, pred_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=409, detail="更新失败（可能已并发验证）")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"验证失败: {e}")
    # 验证成功 → 同步刷新 tianji_summary.json（开阳统计立即更新，不等 I30 定时导出）
    try:
        _exporter = os.path.join(WORKDIR, "tianji_summary_export.py")
        if os.path.exists(_exporter):
            subprocess.Popen([PYTHON, _exporter], cwd=WORKDIR,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    return {"ok": True, "updated": cur.rowcount, "outcome": outcome, "brier": brier, "note": note}


if __name__ == "__main__":
    port = int(os.environ.get("CONTROL_PORT", "8900"))
    print(f"[control_server] 启动于 :{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
