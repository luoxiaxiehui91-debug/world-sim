#!/usr/bin/env bash
# delete_sqlite_e0c.sh — E0-C/P6 删除 3 个业务 SQLite + 2 个僵尸（PG-only 确认后执行）
#
# 门禁（全部通过才删）：
#   1. .sqlite_frozen_at marker 存在（PG-only 已切换）
#   2. 容器 env WORLDSIM_SQLITE_OFF=1 生效
#   3. 探针 VERDICT=OK（PG 五表健康 + SQLite 冻结确认）
#   4. P4 备份目录存在（backups/e0c-p4-20260813/）
# 动作：先 cp 快照到 backups/e0c-p6-<ts>/，再 rm 原路径 4 个 .db，最后验证无残留 + PG 计数。
# 回滚：WORLDSIM_SQLITE_OFF 去掉 + rm marker + up -d；SQLite 由写路径自动重建（空库，读全 PG 不受影响）。
#
# 用法：bash delete_sqlite_e0c.sh [--dry-run]
set -euo pipefail

DATA=/vol2/1000/software/macro-scan/data
BK=/vol2/1000/software/worldsim/backups
TS=$(date +%Y%m%d-%H%M%S)
DRY=${1:-}

echo "== E0-C/P6 删除 SQLite 门禁检查 =="
[ -f "$DATA/.sqlite_frozen_at" ] || { echo "FAIL: marker .sqlite_frozen_at 缺失（未切换 PG-only？）"; exit 1; }
echo "  [ok] marker 存在 ($(cat "$DATA/.sqlite_frozen_at"))"
env_v=$(docker exec macro-scan-macro-scan-1 printenv WORLDSIM_SQLITE_OFF 2>/dev/null || echo "")
[ "$env_v" = "1" ] || { echo "FAIL: 容器 WORLDSIM_SQLITE_OFF=$env_v（期望 1）"; exit 1; }
echo "  [ok] env WORLDSIM_SQLITE_OFF=1"
docker exec macro-scan-macro-scan-1 python -c "
import sys; sys.path.insert(0, '/app')
from silent_failure_probe import run_probe
v, rs = run_probe(alert=False)
print('  probe:', v)
bad = [m for l, m in rs if l == 'CRIT']
sys.exit(1 if v != 'OK' or bad else 0)
" || { echo "FAIL: 探针非 OK（PG 不健康或 SQLite 未冻结）"; exit 1; }
echo "  [ok] 探针 OK"
[ -d "$BK/e0c-p4-20260813" ] || { echo "FAIL: 备份目录 $BK/e0c-p4-20260813 缺失"; exit 1; }
echo "  [ok] P4 备份存在"

echo "== 快照 =="
DEST="$BK/e0c-p6-$TS"
mkdir -p "$DEST"
for f in news.db forecast_tracker.db narrative.db tianji.db; do
  if [ -f "$DATA/$f" ]; then
    cp "$DATA/$f" "$DEST/$f"
    echo "  [ok] 快照 $f -> $DEST/"
  else
    echo "  [warn] $f 原路径已不存在（跳过）"
  fi
done

if [ "$DRY" = "--dry-run" ]; then
  echo "== dry-run：未删除 =="
  exit 0
fi

echo "== 删除 =="
for f in news.db forecast_tracker.db narrative.db tianji.db; do
  if [ -f "$DATA/$f" ]; then
    rm -f "$DATA/$f" && echo "  [del] $f"
  fi
done

echo "== 验证 =="
left=$(ls "$DATA"/*.db 2>/dev/null || true)
if [ -n "$left" ]; then
  echo "FAIL: 原路径仍有 .db: $left"
  exit 1
fi
echo "  [ok] 原路径无 .db"
docker exec macro-scan-macro-scan-1 python -c "
import sys; sys.path.insert(0, '/app')
from silent_failure_probe import run_probe
v, rs = run_probe(alert=False)
print('  探针(删后):', v)
sys.exit(0 if v == 'OK' else 1)
" && echo "  [ok] PG 读路径健康（探针 OK）"
echo "== P6 删除完成：快照在 $DEST =="
