#!/bin/bash
set -e

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
