#!/usr/bin/env python3
"""
tianji_verify_cron.py — 天玑验证域定时器（2026-08-24 存量收编二期）

与 verify_watchdog.py（事件驱动：轮询 trigger.json）职责分离——本进程只做
「到点执行定时验证任务」。任务表内嵌，POLL_INTERVAL=60s 粒度到分钟。

任务（自天枢 scheduler 迁入，频率保持不变）：
  - 每日 09:30  verify_geo_auto.py        （L1 地缘预测自动判定）
  - 每月 1 日 09:00  verify_predictions.py（宏观预测命中核验）
  - 每月 1 日 09:15  verify_hypothesis.py --commit --update-weights（假设校准）

幂等性：三脚本天然可重跑（UPDATE 已 verified 不重匹配 / 输出 json 覆盖写）。
日志：/app/macro_data/logs/tianji_verify.log（data 卷持久化）。
"""
import os
import subprocess
import sys
import time
from datetime import datetime

APP = "/app"
LOG_DIR = "/app/macro_data/logs"
POLL_INTERVAL = 60  # 秒

# (month_day: None=每日 或 1=每月1日, hour, minute, argv)
TASKS = [
    (None, 9, 30, [sys.executable, "verify_geo_auto.py"]),
    (1,    9, 0,  [sys.executable, "verify_predictions.py"]),
    (1,    9, 15, [sys.executable, "verify_hypothesis.py", "--commit", "--update-weights"]),
]


def _log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "tianji_verify.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _due(now: datetime, mday: int, hh: int, mm: int) -> bool:
    if now.hour != hh or now.minute != mm:
        return False
    return mday is None or now.day == mday


def main() -> int:
    _log(f"tianji_verify_cron 启动，{len(TASKS)} 个任务："
         + "; ".join(f"{m or '每日'} {h:02d}:{mm:02d} {argv[-1]}" for m, h, mm, argv in TASKS))
    last_fired = {}  # (mday,hh,mm) -> "YYYY-MM-DD HH:MM" 防同一分钟内重复触发
    while True:
        now = datetime.now()
        key_now = now.strftime("%Y-%m-%d %H:%M")
        for mday, hh, mm, argv in TASKS:
            k = (mday, hh, mm)
            if _due(now, mday, hh, mm) and last_fired.get(k) != key_now:
                last_fired[k] = key_now
                _log(f"FIRING: {' '.join(argv)}")
                try:
                    r = subprocess.run(argv, cwd=APP, capture_output=True, text=True, timeout=3600)
                    tail = (r.stdout or r.stderr).strip().splitlines()
                    _log(f"DONE rc={r.returncode}: {(tail[-1] if tail else '(无输出)')[:160]}")
                except Exception as e:
                    _log(f"ERROR: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
