#!/bin/bash
# 统一部署脚本 — world-sim monorepo
# 用法：bash deploy.sh [macro-scan|macro-sim|all]
# 默认：all

set -e

NAS="${NAS_HOST:?错误：请先设置 NAS_HOST 环境变量，格式 user@host}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

deploy_scan() {
  echo "==> 部署 macro-scan..."
  rsync -av \
    --exclude='.git' \
    --exclude='data/' \
    --exclude='logs/' \
    --exclude='知识库/财经知识库/07_分析报告/' \
    --exclude='知识库/财经知识库/_update_tmp/' \
    --exclude='知识库/财经知识库/*/_raw/' \
    --exclude='docker-compose.yml' \
    --exclude='key.txt' \
    --exclude='docs/分析报告/' \
    --exclude='docs/新闻库/' \
    --exclude='docs/macro_dashboard.html' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "${SCRIPT_DIR}/macro-scan/" "${NAS}:${NAS_DIR:-/opt/macro-scan}/"
  ssh "${NAS}" "cd ${NAS_DIR:-/opt/macro-scan} && docker compose restart"
  echo "==> macro-scan 部署完成"
}

deploy_sim() {
  echo "==> 部署 macro-sim（方案 A：仓库直构，2026-08-06 天璇双通道收敛）..."
  ssh "${NAS}" "cd ${NAS_REPO_DIR:-/opt/world-sim}/macro-sim && docker build -t macro-sim:latest . && docker compose up -d --force-recreate"
  echo "==> macro-sim 部署完成"
}

case "${1:-all}" in
  macro-scan) deploy_scan ;;
  macro-sim)  deploy_sim ;;
  all)        deploy_scan && deploy_sim ;;
  *)
    echo "用法：bash deploy.sh [macro-scan|macro-sim|all]"
    exit 1
    ;;
esac
