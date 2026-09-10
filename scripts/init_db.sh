#!/usr/bin/env bash
#
# init_db.sh — 数据库初始化（一条命令完成）
#
# 做四件事：
#   1. 准备数据库目录与密钥文件（$WORLDSIM_PG_DIR，默认 <repo>/.pgdata）
#   2. 调用 infra/pg/deploy-pg.sh：起 pgvector 容器、建库与角色、配置跨网 ACL
#   3. 按序执行建表 SQL（4 个文件，覆盖 public / news / forecast / tianji / rag）
#   4. 校验创建结果
#
# 幂等：可安全重跑；不 DROP 任何对象、不覆盖已有密钥文件。
#
# 前置条件：
#   - Docker 已安装且当前用户可用
#   - <repo>/macro-scan/.env 中的 WORLDSIM_APP_PW 已填写
#     （应用角色密码的唯一来源，避免多处定义不一致）
#
# 用法：
#   bash scripts/init_db.sh
#   WORLDSIM_PG_DIR=/data/pg bash scripts/init_db.sh     # 自定义数据目录

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PGDIR="${WORLDSIM_PG_DIR:-$REPO/.pgdata}"
PG_CONTAINER=worldsim-pg
PG_SUPER=worldsim_admin
PG_DB=worldsim

say() { printf '%s\n' "$*"; }
die() { printf '\n错误：%s\n' "$*" >&2; exit 1; }

say "======================================================"
say " 数据库初始化"
say "======================================================"
say " 仓库根:   $REPO"
say " 数据目录: $PGDIR"
say ""

# ── 0. 前置检查 ─────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "未找到 docker 命令，请先安装 Docker。"
docker info >/dev/null 2>&1 || die "docker 不可用（未运行，或当前用户无权限）。"

# ── 1. 读取应用密码 ─────────────────────────────────────────
ENV_SCAN="$REPO/macro-scan/.env"
if [ ! -f "$ENV_SCAN" ]; then
  die "未找到 $ENV_SCAN
      请先执行：cp macro-scan/.env.example macro-scan/.env
      然后在其中填写 WORLDSIM_APP_PW（数据库应用账号密码，自定义即可）。"
fi
APP_PW="$(grep -E '^WORLDSIM_APP_PW=' "$ENV_SCAN" | head -1 | cut -d= -f2- || true)"
if [ -z "${APP_PW:-}" ]; then
  die "$ENV_SCAN 中的 WORLDSIM_APP_PW 为空。
      请填写一个自定义密码后重跑本脚本（该值将用于创建 worldsim_app 角色）。"
fi

# ── 2. 准备数据目录与密钥文件 ───────────────────────────────
mkdir -p "$PGDIR"

gen_pw() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets;print(secrets.token_urlsafe(24))'
  else
    openssl rand -base64 32 | tr -d '/+=' | head -c 32
  fi
}

say "[1/4] 准备密钥文件"
if [ ! -f "$PGDIR/.env" ]; then
  cat > "$PGDIR/.env" <<EOF
POSTGRES_USER=$PG_SUPER
POSTGRES_PASSWORD=$(gen_pw)
POSTGRES_DB=$PG_DB
EOF
  chmod 600 "$PGDIR/.env"
  say "      新建 $PGDIR/.env（容器初始化用；超级用户密码已随机生成）"
else
  say "      沿用已有 $PGDIR/.env"
fi

if [ ! -f "$PGDIR/connection.env" ]; then
  RO_PW="$(gen_pw)"
  cat > "$PGDIR/connection.env" <<EOF
WORLDSIM_APP_PW=$APP_PW
WORLDSIM_RO_PW=$RO_PW
DSN=postgresql://worldsim_app:$APP_PW@127.0.0.1:5434/$PG_DB
EOF
  chmod 600 "$PGDIR/connection.env"
  say "      新建 $PGDIR/connection.env（应用/只读角色密码）"
else
  say "      沿用已有 $PGDIR/connection.env"
  CUR="$(grep -E '^WORLDSIM_APP_PW=' "$PGDIR/connection.env" | cut -d= -f2- || true)"
  if [ "${CUR:-}" != "$APP_PW" ]; then
    say "      ⚠️ 注意：connection.env 中的密码与 macro-scan/.env 不一致"
    say "         （角色密码以数据库为准；若应用连不上，请核对两者）"
  fi
fi
say ""

# ── 3. 部署容器 / 建库 / 建角色 ─────────────────────────────
say "[2/4] 部署 PostgreSQL 容器（调用 infra/pg/deploy-pg.sh）"
WORLDSIM_PG_DIR="$PGDIR" bash "$REPO/infra/pg/deploy-pg.sh"
say ""

# ── 4. 执行建表 SQL ─────────────────────────────────────────
SQLS=(
  "$REPO/sql/01_indicators.sql"
  "$REPO/macro-scan/sql/02_indicator_weights.sql"
  "$REPO/macro-scan/sql/03_b0_schema.sql"
  "$REPO/macro-scan/sql/04_d0_schema.sql"
)
say "[3/4] 执行建表 SQL（${#SQLS[@]} 个）"
for f in "${SQLS[@]}"; do
  [ -f "$f" ] || die "SQL 文件缺失：$f"
  say "      → $(basename "$f")"
  # 04 含 CREATE EXTENSION vector，需超级用户执行
  docker exec -i "$PG_CONTAINER" \
    psql -U "$PG_SUPER" -d "$PG_DB" -v ON_ERROR_STOP=1 -q -f - < "$f"
done
say ""

# ── 5. 校验 ─────────────────────────────────────────────────
say "[4/4] 校验"
docker exec "$PG_CONTAINER" psql -U "$PG_SUPER" -d "$PG_DB" -t -A -c "
SELECT '  schema  ' || rpad(nspname, 10) || (SELECT count(*)::text FROM pg_tables t
         WHERE t.schemaname = n.nspname) || ' 张表'
  FROM pg_namespace n
 WHERE nspname IN ('public','news','forecast','tianji','rag')
 ORDER BY 1;
SELECT '  vector 扩展: ' || COALESCE((SELECT extversion FROM pg_extension WHERE extname='vector'), '❌ 未安装');
SELECT '  合计表数: ' || count(*)::text FROM pg_tables
 WHERE schemaname NOT IN ('pg_catalog','information_schema');
"
say ""
say "======================================================"
say " 完成"
say "======================================================"
say " 下一步："
say "   1. 构建镜像"
say "        docker build -t macro-scan:v8 macro-scan/"
say "        docker build -t macro-tianji:latest macro-ji/"
say "        docker build -t macro-sim:latest macro-sim/"
say "   2. 确认 .env 已就绪（含 MACRO_SCAN_DIR / KAIYANG_DIR 等插值变量）"
say "   3. 启动"
say "        docker compose -f macro-scan/docker-compose.yml up -d"
say "        docker compose -f macro-ji/docker-compose.yml up -d"
say "        docker compose -f macro-sim/docker-compose.yml up -d"
say ""
say " 查看日志：docker logs -f macro-scan-macro-scan-1"
say ""
