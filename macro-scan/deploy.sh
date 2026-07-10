#!/bin/bash
# deploy.sh — macro-scan NAS 部署脚本
# 用法：bash deploy.sh [选项]
#   --sync       全量同步源码区到 NAS 运行区（改完代码必须先跑这个）
#   --build      重建 Docker 镜像（修改了 Dockerfile 或 entrypoint.sh 时使用）
#   --restart    仅重启容器（不重建镜像）
#   --check      检查容器运行状态（不执行部署）
#   --logs       查看最近 50 行 scheduler 日志
#   无参数        等同于 --sync（全量同步）

set -e

NAS_HOST="TSX@192.168.31.108"
NAS_SRC="/vol2/1000/software/macro-scan-src"
NAS_DIR="/vol2/1000/software/macro-scan"
CONTAINER="macro-scan-macro-scan-1"

# 读取 VERSION
VERSION=$(cat VERSION 2>/dev/null || echo "unknown")

_sync() {
  echo "=== 全量同步源码区 → 运行区 (v${VERSION}) ==="
  ssh "$NAS_HOST" "rsync -a --delete \
    --exclude='.git' \
    --exclude='data/' \
    --exclude='logs/' \
    --exclude='知识库/财经知识库/07_分析报告/' \
    --exclude='知识库/财经知识库/_update_tmp/' \
    --exclude='知识库/财经知识库/*/_raw/' \
    --exclude='docker-compose.yml' \
    --exclude='key.txt' \
    ${NAS_SRC}/ ${NAS_DIR}/"
  echo "=== 同步完成 ==="
}

_check() {
  echo "=== macro-scan 状态检查 (v${VERSION}) ==="
  ssh "$NAS_HOST" "
    echo '--- 容器状态 ---'
    docker ps --filter name=macro-scan --format 'image={{.Image}} status={{.Status}} ports={{.Ports}}'
    echo ''
    echo '--- 最近 scheduler 日志 ---'
    docker exec $CONTAINER tail -10 /var/log/macro-scan/scheduler.log 2>/dev/null || echo '容器未运行'
    echo ''
    echo '--- GRV 最新值 ---'
    docker exec $CONTAINER python3 -c \"
import json
d = json.load(open('/workspace/data/grv_latest.json'))
for k,v in d.items():
    if isinstance(v,(int,float)):
        print(f'  {k}: {round(v,2)}')
\" 2>/dev/null || echo '数据未就绪'
  "
}

_logs() {
  ssh "$NAS_HOST" "docker exec $CONTAINER tail -50 /var/log/macro-scan/scheduler.log"
}

_build() {
  echo "=== 重建镜像并部署 (v${VERSION}) ==="
  IMAGE_TAG=$(grep 'image:' docker-compose.example.yml | grep -o 'macro-scan:v[0-9]*' | head -1)
  echo "目标镜像: $IMAGE_TAG"
  ssh "$NAS_HOST" "cd $NAS_DIR && docker build -t $IMAGE_TAG . && docker compose up -d"
  echo "=== 部署完成 ==="
}

_up() {
  ssh "$NAS_HOST" "cd $NAS_DIR && docker compose up -d"
}

_restart() {
  echo "=== 重启容器 ==="
  ssh "$NAS_HOST" "cd $NAS_DIR && docker compose restart"
  echo "=== 完成 ==="
}

case "${1:-}" in
  --sync)    _sync ;;
  --check)   _check ;;
  --logs)    _logs ;;
  --build)   _sync && _build ;;
  --restart) _restart ;;
  "")        _sync ;;
  *)
    echo "未知选项: $1"
    echo "用法: bash deploy.sh [--sync|--build|--restart|--check|--logs]"
    exit 1
    ;;
esac

