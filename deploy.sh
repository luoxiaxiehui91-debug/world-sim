#!/bin/bash
# 统一部署脚本 — world-sim monorepo
# 用法：bash deploy.sh [macro-scan|macro-sim|all]
# 默认：all

set -e

NAS="TSX@192.168.31.108"
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
    "${SCRIPT_DIR}/macro-scan/" "${NAS}:/vol2/1000/software/macro-scan/"
  ssh "${NAS}" "cd /vol2/1000/software/macro-scan && docker compose restart"
  echo "==> macro-scan 部署完成"
}

deploy_sim() {
  echo "==> 部署 macro-sim..."
  rsync -av \
    --exclude='.git' \
    --exclude='output/' \
    --exclude='sim_log.db' \
    --exclude='.env' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "${SCRIPT_DIR}/macro-sim/" "${NAS}:/vol2/1000/software/macro-sim/"
  ssh "${NAS}" "cd /vol2/1000/software/macro-sim && docker build -t macro-sim:latest . && docker compose up -d --force-recreate"
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
