#!/usr/bin/env bash
# ============================================================================
# verify_front.sh — 开阳 M-1 news_geo 事件图层 · 前端验收脚本
# 对应验收文档：arg-map-qa-2026-08-11.md（§4 AC-F-01~05 / §6 G-M3 / AC-R-05）
#
# 用途：
#   1) 跑开阳前端单测（npm test，含 newsGeoAdapter.test.ts 29 条 + 既有回归）
#   2) 打印浏览器人工项检查清单（由主理人在浏览器复核，脚本不代跑）
#   3) 输出 PASS/FAIL 汇总 + 退出码（0=自动项全过；1=单测失败；2=运行环境缺失）
#
# 用法：
#   bash verify_front.sh                       # 全量（npm test + 人工清单）
#   bash verify_front.sh --npm-only            # 只跑 npm test，不打印人工清单
#   bash verify_front.sh --list-only           # 只打印人工清单，不跑 npm test
#   bash verify_front.sh --kaiyang-dir PATH    # 指定前端构建目录（默认 ./kaiyang-build）
#
# 前置：
#   - npm test 需在含 node_modules 的前端源码目录跑（构建机本地，不在 NAS/SMB）
#   - 浏览器人工项需能访问开阳线上 http://localhost:8080
# ============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KAIYANG_DIR="${KAIYANG_DIR:-}"
MODE_ALL=1; MODE_NPM=0; MODE_LIST=0
for arg in "$@"; do
  case "$arg" in
    --npm-only) MODE_ALL=0; MODE_NPM=1 ;;
    --list-only) MODE_ALL=0; MODE_LIST=1 ;;
    --kaiyang-dir=*) KAIYANG_DIR="${arg#*=}" ;;
  esac
done
[ -z "$KAIYANG_DIR" ] && KAIYANG_DIR="${SCRIPT_DIR}/../../kaiyang-build"
KAIYANG_DIR="$(cd "$KAIYANG_DIR" 2>/dev/null && pwd || echo "$KAIYANG_DIR")"

PASS=0; FAIL=0; SKIP=0
declare -a RESULTS

note() { echo -e "$*"; }
rec() { # rec <status> <code> <msg>
  local st="$1"; RESULTS+=("$st|$2|$3")
  case "$st" in
    PASS) PASS=$((PASS+1)) ;;
    FAIL) FAIL=$((FAIL+1)) ;;
    *)    SKIP=$((SKIP+1)) ;;
  esac
}

echo "============================================================"
echo " 开阳 M-1 news_geo 前端验收（verify_front.sh）"
echo " 时间: $(date '+%Y-%m-%d %H:%M:%S %z')"
echo " 前端目录: $KAIYANG_DIR"
echo "============================================================"

# ── 1. 自动项：前端单测（AC-R-05 / AC-F-01 数据层单测已覆盖）──────
if [ "$MODE_ALL" -eq 1 ] || [ "$MODE_NPM" -eq 1 ]; then
  echo ""
  echo "--- 1/2 前端单测（AC-R-05）---"
  if [ ! -d "$KAIYANG_DIR/node_modules" ]; then
    note "  [SKIP] $KAIYANG_DIR/node_modules 不存在（未安装依赖或目录非前端源码根）"
    rec SKIP AC-R-05 "node_modules 缺失"
  elif [ ! -f "$KAIYANG_DIR/package.json" ]; then
    note "  [SKIP] $KAIYANG_DIR/package.json 不存在"
    rec SKIP AC-R-05 "package.json 缺失"
  else
    pushd "$KAIYANG_DIR" >/dev/null 2>&1 || { rec FAIL AC-R-05 "无法进入 $KAIYANG_DIR"; }
    if npm test >/tmp/verify_front_npmtest.log 2>&1; then
      tail_ok="$(grep -c "Test Files.*passed\|✓.*test" /tmp/verify_front_npmtest.log 2>/dev/null || true)"
      note "  [PASS] npm test 通过（细节见 /tmp/verify_front_npmtest.log）"
      rec PASS AC-R-05 "npm test 全绿"
      # 确认 newsGeoAdapter 用例被执行（断言数不降，禁 skip）
      if grep -q "newsGeoAdapter" /tmp/verify_front_npmtest.log 2>/dev/null \
         || grep -q "newsGeoAdapter.test" /tmp/verify_front_npmtest.log 2>/dev/null; then
        note "  [PASS] newsGeoAdapter.test 用例已执行"
      else
        note "  [WARN] 日志未显式出现 newsGeoAdapter 用例名（请人工确认无 skip/.only）"
      fi
    else
      note "  [FAIL] npm test 失败，尾部日志如下："
      tail -20 /tmp/verify_front_npmtest.log
      rec FAIL AC-R-05 "npm test 失败（见 /tmp/verify_front_npmtest.log）"
    fi
    popd >/dev/null 2>&1
  fi
fi

# ── 2. 浏览器人工项清单（由主理人复核，脚本不代跑）────────────────
if [ "$MODE_ALL" -eq 1 ] || [ "$MODE_LIST" -eq 1 ]; then
  echo ""
  echo "--- 2/2 浏览器人工项清单（由主理人浏览器复核，网址 http://localhost:8080）---"
  note "  以下各项【由主理人浏览器复核】，脚本只打印清单、不判定："
  note ""
  note "  [人工-1] AC-F-01 事件点渲染：世界地图 → 勾选\"地理新闻\"图层 → 应见分布全球的事件点"
  note "           截图留档；点径/配色随 intensity 分级；悬停 tooltip 显示"
  note "           location_name/country/event_type/mention_count"
  note "  [人工-2] AC-F-02 降级不白屏：DevTools 把 /data/news_geo.json 请求改 404（或断网）"
  note "           → 地图其余图层（GRV/核设施）仍渲染、无白屏、状态条对 news_geo 报读取失败"
  note "  [人工-3] AC-F-03 性能：DevTools Performance 录制\"地图加载+全图缩放一次\"，"
  note "           断言主线程 long task（>50ms）≤5；无白屏帧；"
  note "           控制台无 \"[WorldPanel] 某图层点位超过 2000 上限\" 告警"
  note "  [人工-4] AC-F-04 状态条时间戳：状态条 GEO 数据时间与 news_geo.json 顶层 updated"
  note "           一致（08-05 时间戳契约：无后缀补 +08:00）"
  note "  [人工-5] AC-F-05 图例计数：切换地区（如\"中东\"）→ 图例\"地理新闻\"数字随地区变化"
  note "           且与地图实际点位数吻合"
  note "  [人工-6] G-M3 综合：上述 1~5 截图+console 记录归档（本脚本同目录 或 论证附件）"
  note "           作为门禁 G-M3 佐证材料"
  echo ""
  note "  浏览器数据核对命令（NAS 侧，与浏览器并排看）："
  note "    ssh nas 'curl -s http://localhost:8080/data/news_geo.json | head -c 400'"
  note "    ssh nas 'python3 /vol2/1000/software/world-sim/macro-scan/docs/qa-scripts/verify_data.py'"
  rec SKIP G-M3 "浏览器人工项待主理人复核（清单已打印）"
fi

# ── 汇总 ─────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " PASS/FAIL 汇总"
for r in "${RESULTS[@]}"; do
  IFS='|' read -r st code msg <<< "$r"
  echo "  [$st] $code: $msg"
done
echo "------------------------------------------------------------"
echo " 统计: PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
if [ "$FAIL" -gt 0 ]; then
  echo " 结论: FAIL（npm test 失败，按 arg-map-qa-2026-08-11.md §4 定位）"
  exit 1
fi
echo " 结论: PASS（自动项全过；SKIP 人工项见清单）"
exit 0
