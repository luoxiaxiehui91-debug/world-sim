#!/usr/bin/env bash
# worldsim-pg 每日逻辑备份 + 保留 14 天。由 crontab 调用（0 4 * * * bash .../backup-pg.sh >> .../backups/backup.log 2>&1）。
#
# 2026-08-13 22:2x 重写（修复 worldsim-rename-check.md 记录的问题）：
#   - P0-1: line 8 `> ""` 重定向到空名 → set -e 必挂，cron 每日备份 100% 失败（backup.log 实证）
#   - P0-2: 硬编码 PGPASSWORD=ZvR0... 已失效（与 connection.env 均不匹配）+ 明文密码泄露面
#   - P1-1: STAMP 硬编码、OUT 文件名未拼时间戳（固定 worldsim-.dump 互相覆盖）
#   - P1-2: PGPASSWORD_FILE 非标准变量（psql/pg_dump 不认识）
#   - P1-3: echo "backup done: ()" 引用空变量
# 认证方案：docker exec 容器内以 worldsim_admin 免密执行（deploy-pg.sh 同款），脚本内不落任何密码。
set -euo pipefail

WORLD=/vol2/1000/software/worldsim-pg
PG_CONTAINER=worldsim-pg
BACKUP_DIR="$WORLD/backups"
STAMP=$(date +%Y%m%d-%H%M)
OUT="$BACKUP_DIR/worldsim-$STAMP.dump"

mkdir -p "$BACKUP_DIR"

docker exec "$PG_CONTAINER" pg_dump -Fc -U worldsim_admin -h localhost -p 5432 -d worldsim > "$OUT"

# 清理 14 天前
find "$BACKUP_DIR" -name "worldsim-*.dump" -mtime +14 -delete

# 写备份成功 marker（供 silent_failure_probe 监控备份新鲜度，防 backup 再静默挂）
date +%s > /vol2/1000/software/macro-scan/data/.last_pg_backup

echo "backup done: $OUT ($(du -h "$OUT" | cut -f1))"
