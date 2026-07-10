#!/usr/bin/env python3
"""Python cron replacement for macro-scan container.
Avoids seccomp/fork restrictions that break cron daemon.
Run as: python3 /app/scheduler.py >> /var/log/macro-scan/scheduler.log 2>&1

## 任务隐式依赖关系（CON-6）
时间间隔已足够保证正确顺序，无需额外同步：
  disaster (05:25) → [无依赖]
  fred_fetch (05:30) → [无依赖]
  gpr_fetch (05:40) → [无依赖，与 fred_fetch 同类，30s 后]
  china_fetch (05:45) → [无依赖]
  grv_update (06:10) → 依赖 gpr_fetch (05:40) + fred_fetch (05:30)，预留 30min
  weak_signal (06:00) → 依赖 gpr_fetch (05:40)，预留 20min
  situation_detect (06:30) → 依赖 weak_signal (06:00)，预留 30min
  daily_narrative (07:00) → 依赖 grv_update (06:10) + situation_detect (06:30)
  morning (07:30) → 依赖 daily_narrative (07:00)，预留 30min
  us_daily/china_daily (20:00/20:15) → 独立，不依赖白天任务
所有任务通过 subprocess.Popen 后台非阻塞启动，调度线程不等待完成。
"""
import subprocess, time, sys, os, datetime

WORKDIR = "/app"
PYTHON  = "/usr/local/bin/python3"
LOG_DIR = "/var/log/macro-scan"

JOBS = [
    # name,         hhmm,   weekdays(1-5=Mon-Fri, 1-7=all), dom(day-of-month, None=any), command
    ("disaster",    "0525", "1-7", None, [PYTHON, "fetch_disaster_signals.py"]),  # 自然灾害信号（最早）
    ("fred_fetch",  "0530", "1-7", None, [PYTHON, "fetch_fred_history.py"]),
    ("gpr_fetch",   "0540", "1-7", None, [PYTHON, "fetch_gpr.py"]),
    ("china_fetch", "0545", "1-7", None, [PYTHON, "fetch_china_data.py"]),
    ("weak_signal", "0000", "1-7", None, [PYTHON, "scan_weak_signals.py"]),
    ("weak_signal", "0600", "1-7", None, [PYTHON, "scan_weak_signals.py"]),
    ("weak_signal", "1200", "1-7", None, [PYTHON, "scan_weak_signals.py"]),
    ("weak_signal", "1800", "1-7", None, [PYTHON, "scan_weak_signals.py"]),
    ("grv_update",  "0610", "1-7", None, [PYTHON, "geo_risk_vector.py"]),
    ("morning",     "0730", "1-5", None, [PYTHON, "run_macro_analysis.py", "--country", "both", "--depth", "quick"]),
    ("us_daily",    "2000", "1-5", None, [PYTHON, "run_macro_analysis.py", "--country", "us", "--depth", "standard"]),
    ("china_daily", "2015", "1-5", None, [PYTHON, "run_macro_analysis.py", "--country", "china", "--depth", "standard"]),
    ("verify",      "0900", "1-7", 1,    [PYTHON, "verify_predictions.py"]),
    ("kb_update",   "0905", "1-7", 1,    [PYTHON, "update_kb_numbers.py"]),
    ("climate",     "0910", "1-7", 1,    [PYTHON, "fetch_climate_signals.py"]),
    ("daily_narrative", "0700", "1-7", None, [PYTHON, "daily_narrative.py"]),
    ("news_export",  "0705", "1-7", None, [PYTHON, "news_exporter.py"]),         # macro-sim JSON 导出
    ("situation_detect", "0630", "1-7", None, [PYTHON, "situation_detector.py"]),
    ("weekly_synthesis", "2000", "5",  None, [PYTHON, "weekly_synthesis.py"]),       # 周五20:00
    ("dashboard",    "2030", "1-5", None, [PYTHON, "dashboard.py"]),                  # us_daily+china_daily 结束后刷新
    ("verify_auto", "0915", "1-7", 1,   [PYTHON, "verify_hypothesis.py", "--commit", "--update-weights"]),  # 每月1日
    ("news_prune",  "0920", "1-7", 1,   [PYTHON, "-c",
        "import sys; sys.path.insert(0,'.'); import news_db; "
        "from optim_config import DATA_DIR; import os; "
        "db=os.path.join(DATA_DIR,'news.db'); "
        "n=news_db.prune_old_articles(db,90); print(f'[prune] 删除 {n} 篇旧文章')"
    ]),  # 每月1日，保留90天滚动窗口
]

LOG_FILES = {
    "fred_fetch":  f"{LOG_DIR}/fred.log",
    "gpr_fetch":   f"{LOG_DIR}/gpr_fetch.log",
    "china_fetch": f"{LOG_DIR}/china.log",
    "weak_signal": f"{LOG_DIR}/scan.log",
    "morning":     f"{LOG_DIR}/morning.log",
    "us_daily":    f"{LOG_DIR}/us_daily.log",
    "china_daily": f"{LOG_DIR}/china_daily.log",
    "verify":      f"{LOG_DIR}/verify.log",
    "kb_update":   f"{LOG_DIR}/kb_update.log",
    "grv_update":  f"{LOG_DIR}/grv.log",
    "daily_narrative": f"{LOG_DIR}/daily_narrative.log",
    "climate":     f"{LOG_DIR}/climate.log",
    "situation_detect": f"{LOG_DIR}/situation_detect.log",
    "disaster":    f"{LOG_DIR}/disaster.log",
    "weekly_synthesis": f"{LOG_DIR}/weekly_synthesis.log",
    "dashboard":    f"{LOG_DIR}/dashboard.log",
    "verify_auto": f"{LOG_DIR}/verify_auto.log",
    "news_prune":  f"{LOG_DIR}/news_prune.log",
    "news_export": f"{LOG_DIR}/news_export.log",
}

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[SCHED] {ts} {msg}"
    print(line, flush=True)

def job_log(name, msg):
    log_file = LOG_FILES.get(name, f"{LOG_DIR}/{name}.log")
    try:
        with open(log_file, "a") as f:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[SCHED] {ts} {msg}\n")
    except Exception as e:
        log(f"Cannot write {log_file}: {e}")

def get_hhmm_wd():
    now = datetime.datetime.now()
    return now.strftime("%H%M"), now.isoweekday(), now.day  # Mon=1 Sun=7

def should_run(sched_hhmm, sched_wd, sched_dom=None):
    hhmm, wd, dom = get_hhmm_wd()
    if hhmm != sched_hhmm:
        return False
    # day-of-month 检查（仅在指定时生效）
    if sched_dom is not None and dom != sched_dom:
        return False
    if sched_wd == "1-7":
        return True
    parts = sched_wd.split(",")
    for part in parts:
        if "-" in part:
            try:
                start, end = int(part.split("-")[0]), int(part.split("-")[1])
                if start <= wd <= end:
                    return True
            except (ValueError, IndexError):
                pass
        elif str(wd) == part.strip():
            return True
    return False

last_run = {}  # (job_name, sched_hhmm) -> last_run_ts

def main():
    log("Python scheduler started (seccomp-free)")
    
    while True:
        for job_name, sched_hhmm, sched_wd, sched_dom, cmd in JOBS:
            key = (job_name, sched_hhmm)
            now_ts = datetime.datetime.now().timestamp()

            # Rate limit: skip if already ran within 50 minutes
            if key in last_run:
                if now_ts - last_run[key] < 3000:
                    continue

            if not should_run(sched_hhmm, sched_wd, sched_dom):
                continue
            
            log(f"FIRING: {job_name} ({' '.join(cmd[1:])})")
            last_run[key] = now_ts
            job_log(job_name, f"=== Job started: {' '.join(cmd[1:])} ===")
            
            # Spawn job in background
            log_file = LOG_FILES.get(job_name, f"{LOG_DIR}/{job_name}.log")
            try:
                with open(log_file, "a") as lf:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=WORKDIR,
                        stdout=lf,
                        stderr=subprocess.STDOUT
                    )
                    log(f"Job spawned PID={proc.pid}: {job_name}")
                    job_log(job_name, f"Job PID={proc.pid}")
            except Exception as e:
                log(f"Job spawn failed: {job_name} {e}")
                job_log(job_name, f"Job spawn ERROR: {e}")
        
        time.sleep(30)

if __name__ == "__main__":
    main()
