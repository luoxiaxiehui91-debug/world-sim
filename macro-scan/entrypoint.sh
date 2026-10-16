#!/bin/bash
set -e

# ── 日志轮转（2026-10-17 全量代码审查修复）───────────────────────────────────
# 背景：下面各进程的输出均以 ">> xxx.log" 重定向到宿主机挂载卷内的**普通文件**，
#   而 docker-compose 的 logging driver(json-file, max-size 10m) 只作用于 stdout，
#   对这批重定向文件完全无效 ⇒ logs/ 无上界增长。
#   实测：102MB / 77 个文件 / 0 个轮转产物，最大 crypto_extra.log 达 26MB。
# 时机：本脚本在容器每次启动时执行；路由器每日 03:30-04:00 重启 ⇒ 近似每日轮转一次。
# 策略：超限文件 mv 保留 LOG_KEEP 份，超出份数直接删除；mv 发生在任何后台进程启动
#   之前，故不存在「进程持有旧 inode」问题（等价于 create 而非 copytruncate）。
LOG_DIR="${LOG_DIR:-/var/log/macro-scan}"
LOG_MAX_MB="${LOG_MAX_MB:-20}"
LOG_KEEP="${LOG_KEEP:-2}"
if [ -d "$LOG_DIR" ]; then
  rotated=0
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    # 依次后挪 .N → .(N+1)：最老的一份被 mv 覆盖，等价于丢弃
    i=$LOG_KEEP
    while [ "$i" -ge 1 ]; do
      prev=$((i - 1))
      if [ "$prev" -eq 0 ]; then src="$f"; else src="$f.$prev"; fi
      [ -f "$src" ] && mv -f "$src" "$f.$i" 2>/dev/null
      i=$((i - 1))
    done
    rotated=$((rotated + 1))
  done < <(find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' -size "+${LOG_MAX_MB}M" 2>/dev/null)
  [ "$rotated" -gt 0 ] && echo "[entrypoint] 日志轮转：已处理 $rotated 个超过 ${LOG_MAX_MB}MB 的日志文件"
fi

echo "[entrypoint] Starting macro-scan container $(date)"
echo "[entrypoint] WORKSPACE=${OPENCLAW_WORKSPACE}"

# Write crontab environment variables (cron does not inherit Docker env vars)
printenv | grep -E "FRED_API_KEY|ANTHROPIC_API_KEY|OPENCLAW_WORKSPACE|TZ|OUTBOUND_PROXY|OLLAMA_URL|NTFY_TOPIC|NTFY_CMD_TOPIC|NTFY_CMD_SECRET|OPENAI_COMPAT_URL|OPENAI_API_KEY|USE_EXTERNAL_LLM" \
    >> /etc/environment

# Start ntfy command listener (background)
if [ -n "${NTFY_CMD_TOPIC}" ]; then
    cd /app && python3 ntfy_listener.py >> /var/log/macro-scan/listener.log 2>&1 &
    echo "[entrypoint] ntfy listener started (topic=${NTFY_CMD_TOPIC})"
fi

# Start Web UI (Phase 3A, port 8899)
cd /app && python3 web_server.py >> /var/log/macro-scan/web.log 2>&1 &
echo "[entrypoint] web server started (http://0.0.0.0:8899)"

# Start Control API (A3a, port 8900)
cd /app && python3 control_server.py >> /var/log/macro-scan/control.log 2>&1 &
echo "[entrypoint] control server started (http://0.0.0.0:8900)"

# Start Python scheduler (replaces cron - seccomp blocks cron fork())
cd /app && python3 scheduler.py >> /var/log/macro-scan/scheduler.log 2>&1 &
SCHED_PID=$!

echo "[entrypoint] scheduler started (PID=${SCHED_PID}), replaces cron (seccomp blocks cron fork)"

# Run initial data fetch (first container start)
if [ "${RUN_ON_START:-true}" = "true" ]; then
    echo "[entrypoint] Running initial data fetch..."
    cd /app && python3 fetch_fred_history.py >> /var/log/macro-scan/fred.log 2>&1 || true
    cd /app && python3 fetch_china_data.py   >> /var/log/macro-scan/china.log 2>&1 || true
    cd /app && python3 scan_weak_signals.py  >> /var/log/macro-scan/scan.log  2>&1 || true
    echo "[entrypoint] Initial fetch complete"
fi

# Keep container running, wait for scheduler
wait $SCHED_PID
