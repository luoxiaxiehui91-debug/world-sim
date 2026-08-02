"""
observability.py — 可观测性计数器（T1-2）

纯只读日志模块，不改任何决策数据。所有写操作强隔离：出错只跳过自己，绝不阻断调用方。

功能：
  Heartbeat  — 写入 .scheduler_heartbeat，外部脚本可据此判断调度器存活
  Job 计数   — 按任务名累计当日触发次数
  合成器统计 — 触发次数 / LLM消耗 / ntfy发送 / 抑制原因（从 synthesis_log.db 读取）
  日终清洗   — 写入 data/observability_YYYY-MM-DD.json

使用：
  from observability import observe
  observe.heartbeat()
  observe.job_fired("grv_update")
"""

import os
import json
import time
import datetime
import sqlite3
import threading

# ══════════════════════════════════════════════════════════════════════════════
# 配置常量
# ══════════════════════════════════════════════════════════════════════════════
try:
    from optim_config import DATA_DIR
except ImportError:
    DATA_DIR = os.environ.get("DATA_DIR", "/workspace/data")

HEARTBEAT_FILE = os.path.join(DATA_DIR, ".scheduler_heartbeat")
OBS_PREFIX     = os.path.join(DATA_DIR, "observability")
SYNTHESIS_DB   = os.path.join(DATA_DIR, "news.db")  # synthesis_log 表在 news.db 中
FLUSH_INTERVAL = 60  # 每 60 秒刷盘一次


# ══════════════════════════════════════════════════════════════════════════════
# Observability 单例
# ══════════════════════════════════════════════════════════════════════════════
class _Observability:
    """零风险计数器。所有方法 try/except 包裹，绝不抛异常到调用方。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._today = ""
        self._jobs = {}        # job_name -> count
        self._last_flush = 0

    # ── 心跳 ────────────────────────────────────────────────────────────────
    def heartbeat(self) -> None:
        """写入当前时间戳到心跳文件。外部脚本可检测文件 age > 5min → 调度器异常。"""
        try:
            ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(ts + "\n")
            self._auto_flush()
        except Exception:
            pass

    # ── 任务计数 ────────────────────────────────────────────────────────────
    def job_fired(self, job_name: str) -> None:
        """记录一次任务触发。线程安全。"""
        try:
            with self._lock:
                self._jobs[job_name] = self._jobs.get(job_name, 0) + 1
            self._auto_flush()
        except Exception:
            pass

    # ── 刷盘 ────────────────────────────────────────────────────────────────
    def _auto_flush(self) -> None:
        """节流刷盘：距上次 FLUSH_INTERVAL 秒内不重复写。"""
        now = time.time()
        if now - self._last_flush < FLUSH_INTERVAL:
            return
        self._last_flush = now
        self._flush()

    def _flush(self) -> None:
        """写入当日 observability JSON（覆盖写，因为本质是计数器快照）。"""
        try:
            today = datetime.date.today().isoformat()
            path = f"{OBS_PREFIX}_{today}.json"

            with self._lock:
                jobs_copy = dict(self._jobs)

            record = {
                "date": today,
                "updated": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "scheduler": {
                    "heartbeat_ok": True,
                    "total_jobs_fired": sum(jobs_copy.values()),
                    "by_job": jobs_copy,
                },
            }

            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# 公共接口：读取合成器统计（从 synthesis_log 表，纯只读）
# ══════════════════════════════════════════════════════════════════════════════
def read_synthesizer_stats(today: str = None) -> dict:
    """
    从 synthesis_log 表读取当日合成器统计。纯读，不改任何数据。

    返回：
      {
        "staging_mode": true/false/null,
        "rules_evaluated": N,
        "rules_triggered": N,
        "llm_calls": N,
        "ntfy_sends": N,
        "suppressed_by_staging": N,
        "suppressed_by_limit": N,
        "suppressed_by_cooldown": N,
      }
    若 news.db 不存在或表不存在，返回零计数字典。
    """
    if today is None:
        today = datetime.date.today().isoformat()

    empty = {
        "staging_mode": None,
        "rules_evaluated": 0,
        "rules_triggered": 0,
        "llm_calls": 0,
        "ntfy_sends": 0,
        "suppressed_by_staging": 0,
        "suppressed_by_limit": 0,
        "suppressed_by_cooldown": 0,
    }

    try:
        if not os.path.exists(SYNTHESIS_DB):
            return empty

        conn = sqlite3.connect(f"file:{SYNTHESIS_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        # 检查 synthesis_log 表是否存在
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='synthesis_log'"
        )
        if not cur.fetchone():
            conn.close()
            return empty

        # 当日评估数
        cur = conn.execute(
            "SELECT COUNT(*) as n FROM synthesis_log WHERE date(log_time) = ?",
            (today,)
        )
        evaluated = cur.fetchone()["n"]

        # 触发数（共振通过）
        cur = conn.execute(
            "SELECT COUNT(*) as n FROM synthesis_log "
            "WHERE date(log_time) = ? AND resonance_ok = 1",
            (today,)
        )
        triggered = cur.fetchone()["n"]

        # LLM 调用数
        cur = conn.execute(
            "SELECT COUNT(*) as n FROM synthesis_log "
            "WHERE date(log_time) = ? AND llm_success = 1",
            (today,)
        )
        llm_calls = cur.fetchone()["n"]

        # ntfy 发送数
        cur = conn.execute(
            "SELECT COUNT(*) as n FROM synthesis_log "
            "WHERE date(log_time) = ? AND ntfy_success = 1",
            (today,)
        )
        ntfy_sends = cur.fetchone()["n"]

        # 各抑制原因计数
        suppress = {}
        cur = conn.execute(
            "SELECT suppress_reason, COUNT(*) as n FROM synthesis_log "
            "WHERE date(log_time) = ? AND suppress_reason IS NOT NULL "
            "GROUP BY suppress_reason",
            (today,)
        )
        for row in cur:
            suppress[row["suppress_reason"]] = row["n"]

        # 读取 STAGING_MODE（从 signal_synthesizer.py 的环境变量或常量推断）
        staging = None
        try:
            from signal_synthesizer import STAGING_MODE
            staging = STAGING_MODE
        except Exception:
            try:
                staging = os.environ.get("STAGING_MODE", "true").lower() in ("true", "1", "yes")
            except Exception:
                pass

        conn.close()
        return {
            "staging_mode": staging,
            "rules_evaluated": evaluated,
            "rules_triggered": triggered,
            "llm_calls": llm_calls,
            "ntfy_sends": ntfy_sends,
            "suppressed_by_staging": suppress.get("staging", 0),
            "suppressed_by_limit": suppress.get("daily_limit", 0),
            "suppressed_by_cooldown": suppress.get("cooldown", 0),
        }

    except Exception:
        return empty


# ══════════════════════════════════════════════════════════════════════════════
# 公共接口：读取心跳状态
# ══════════════════════════════════════════════════════════════════════════════
def check_heartbeat(max_age_seconds: int = 300) -> dict:
    """
    读取心跳文件，返回 {"alive": bool, "last_beat": str, "age_seconds": int}
    max_age_seconds: 超过此秒数判定为"可能异常"
    """
    try:
        if not os.path.exists(HEARTBEAT_FILE):
            return {"alive": False, "last_beat": None, "age_seconds": -1}
        with open(HEARTBEAT_FILE) as f:
            last_beat = f.readline().strip()
        last_dt = datetime.datetime.strptime(last_beat, "%Y-%m-%dT%H:%M:%S")
        age = (datetime.datetime.now() - last_dt).total_seconds()
        return {
            "alive": age <= max_age_seconds,
            "last_beat": last_beat,
            "age_seconds": round(age),
        }
    except Exception:
        return {"alive": False, "last_beat": None, "age_seconds": -1}


# ══════════════════════════════════════════════════════════════════════════════
# 单例
# ══════════════════════════════════════════════════════════════════════════════
observe = _Observability()
