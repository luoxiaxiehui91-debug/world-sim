#!/usr/bin/env bash
# worldsim-pg 部署/重建固化脚本（A0，C 方案修复）。幂等，可安全重跑。
# 仅限 NAS 本机执行。依赖已存在的 worldsim_default 网络。
set -euo pipefail
WORLD=/vol2/1000/software/worldsim-pg
PG_CONTAINER=worldsim-pg
PG_NET=worldsim_default
PG_HBA="$WORLD/pgdata/pg_hba.conf"

mkdir -p "$WORLD/pgdata" "$WORLD/sql" "$WORLD/backups"

# 1) 网络（已存在则跳过）
docker network create "$PG_NET" 2>/dev/null || true

# 2) 容器（已存在则跳过）
if ! docker ps -a --format "{{.Names}}" | grep -qx "$PG_CONTAINER"; then
  docker run -d --name "$PG_CONTAINER" --restart unless-stopped \
    --network "$PG_NET" \
    --env-file "$WORLD/.env" \
    -v "$WORLD/pgdata:/var/lib/postgresql/data" \
    -p 127.0.0.1:5434:5432 \
    pgvector/pgvector:pg16
  # 等待就绪
  for i in $(seq 1 60); do
    docker exec "$PG_CONTAINER" pg_isready -h localhost -p 5432 >/dev/null 2>&1 && break
    sleep 1
  done
  # glibc 字符序不匹配（pgvector 镜像基于 2.41，fnOS 主机 2.36）——刷新记录后建库
  docker exec "$PG_CONTAINER" psql -U worldsim_admin -d postgres -c "ALTER DATABASE postgres REFRESH COLLATION VERSION;" 2>/dev/null || true
  docker exec "$PG_CONTAINER" psql -U worldsim_admin -d postgres -c "ALTER DATABASE template1 REFRESH COLLATION VERSION;" 2>/dev/null || true
  docker exec "$PG_CONTAINER" psql -U worldsim_admin -d postgres -c "CREATE DATABASE worldsim OWNER worldsim_admin;" 2>/dev/null || true
  # 角色（幂等）
  set -a; . "$WORLD/connection.env"; set +a
  python3 - <<PY | docker exec -i "$PG_CONTAINER" psql -U worldsim_admin -d worldsim -f - || true
import os
app=os.environ["WORLDSIM_APP_PW"]; ro=os.environ["WORLDSIM_RO_PW"]
sql=f"""DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='worldsim_app') THEN
    CREATE ROLE worldsim_app LOGIN PASSWORD {app!r};
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='worldsim_ro') THEN
    CREATE ROLE worldsim_ro LOGIN PASSWORD {ro!r};
  END IF;
END \$\$;
REVOKE ALL ON DATABASE worldsim FROM PUBLIC;
GRANT CONNECT ON DATABASE worldsim TO worldsim_app, worldsim_ro;
GRANT CREATE, USAGE ON SCHEMA public TO worldsim_app;
GRANT USAGE ON SCHEMA public TO worldsim_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO worldsim_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO worldsim_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO worldsim_app;
"""
import sys; sys.stdout.write(sql)
PY
fi

# 3) pg_hba 跨网 ACL 固化（幂等，A0.5 补：macro-scan 容器在 worldsim_default 子网 172.29.0.0/16）
ACL_LINE="host worldsim all 172.29.0.0/16 scram-sha-256"
if [ -f "$PG_HBA" ] && ! grep -qF "$ACL_LINE" "$PG_HBA"; then
  printf '%s\n' "$ACL_LINE" >> "$PG_HBA"
  docker kill -s HUP "$PG_CONTAINER" 2>/dev/null || true
  echo "[deploy-pg] pg_hba ACL appended + reloaded: $ACL_LINE"
else
  echo "[deploy-pg] pg_hba ACL already present (idempotent)"
fi

# 4) 互联 macro-scan / tianji（运行时；持久化由各 compose 的 networks 块负责）
docker network connect "$PG_NET" macro-scan-macro-scan-1 2>/dev/null || true
docker network connect "$PG_NET" macro-scan-tianji-1 2>/dev/null || true

echo "deploy-pg done: container=$PG_CONTAINER net=$PG_NET"
