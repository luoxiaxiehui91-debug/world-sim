"""
pg_write_indicators.py — world-sim 天枢 macro-scan 双写模块 (B1)

职责：在原有「SQLite/CSV 落库」之外，把指标行双写到 worldsim-pg 的
indicators 宽表。本模块是「旁路双写」——任何连接/写入异常都必须被捕获
并以 (0,0) 返回，绝不向上抛异常阻断原 CSV/SQLite 流程。

目标表 indicators（11 列，UNIQUE 五元组）：
    indicator_key, as_of, data_vintage, horizon, value,
    ci_low, ci_high, model_ver, created_at, schema_version, status
唯一约束：uq_indicators_identity
    (indicator_key, as_of, horizon, model_ver, data_vintage)

连接：环境变量 WORLDSIM_APP_PW；host=worldsim-pg port=5432
      dbname=worldsim user=worldsim_app（容器间 worldsim_default 子网）。

依赖：psycopg 3.x（macro-scan 镜像 v8 已装）。

实现要点（计数正确性）：
- 用单条 `INSERT ... SELECT unnest(各列数组) ... ON CONFLICT ... RETURNING (xmax=0)`
  一次性批量写入并取回每一行的插入/更新判定。
- 注意 psycopg 3 的 `executemany(returning=True)` 只会返回【最后一条】语句的
  RETURNING 行，无法逐行统计；故改用 unnest 数组 + 单条语句，RETURNING 才完整。
- (xmax = 0) 为真 => 新插入行；为假 => 命中唯一约束被 UPDATE 的行。
"""

import os
from datetime import date, datetime, timezone

# indicators 列顺序（INSERT 列清单、unnest 参数顺序、数组拼接顺序必须三者一致）
_COLUMNS = (
    "indicator_key", "as_of", "data_vintage", "horizon", "value",
    "ci_low", "ci_high", "model_ver", "created_at", "schema_version", "status",
)

_INSERT_SQL = """
INSERT INTO indicators
    (indicator_key, as_of, data_vintage, horizon, value,
     ci_low, ci_high, model_ver, created_at, schema_version, status)
SELECT * FROM unnest(
    %(indicator_key)s::varchar[],
    %(as_of)s::date[],
    %(data_vintage)s::date[],
    %(horizon)s::varchar[],
    %(value)s::double precision[],
    %(ci_low)s::double precision[],
    %(ci_high)s::double precision[],
    %(model_ver)s::varchar[],
    %(created_at)s::timestamptz[],
    %(schema_version)s::varchar[],
    %(status)s::varchar[]
)
ON CONFLICT (indicator_key, as_of, horizon, model_ver, data_vintage)
DO UPDATE SET
    value = EXCLUDED.value,
    created_at = EXCLUDED.created_at,
    status = EXCLUDED.status
RETURNING (xmax = 0) AS did_insert
"""


def _coerce_date(v):
    """把 as_of / data_vintage 统一为 date 对象（容忍字符串或已为 date）。"""
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    raise ValueError(f"无法识别的日期值: {v!r}")


def _build_arrays(rows: list) -> dict:
    """
    把行 dict 列表转成 {列名: 数组} 供 unnest 使用。
    数组顺序严格对应 _COLUMNS。
    """
    arrays = {k: [] for k in _COLUMNS}
    for r in rows:
        arrays["indicator_key"].append(r["indicator_key"])
        arrays["as_of"].append(_coerce_date(r["as_of"]))
        arrays["data_vintage"].append(_coerce_date(r["data_vintage"]))
        arrays["horizon"].append(r["horizon"])
        arrays["value"].append(None if r.get("value") is None else float(r["value"]))
        arrays["ci_low"].append(None if r.get("ci_low") is None else float(r["ci_low"]))
        arrays["ci_high"].append(None if r.get("ci_high") is None else float(r["ci_high"]))
        arrays["model_ver"].append(r["model_ver"])
        arrays["created_at"].append(r["created_at"])
        arrays["schema_version"].append(r["schema_version"])
        arrays["status"].append(r["status"])
    return arrays


def upsert_indicator_rows(rows: list) -> tuple:
    """
    双写 worldsim-pg.indicators。

    参数 rows: 每行 dict 须含 indicators 全部 11 列：
        indicator_key, as_of, data_vintage, horizon, value,
        ci_low, ci_high, model_ver, created_at, schema_version, status
        - as_of / data_vintage: 'YYYY-MM-DD' 字符串或 date 对象
        - created_at: 必须 aware（带时区，建议 UTC，带 +00:00 后缀）
        - value / ci_low / ci_high: float 或 None

    返回 (inserted, updated)。
    - 空输入直接返回 (0,0)。
    - 任何连接/写入/导入异常都捕获并打印 ERROR，返回 (0,0)，不抛异常。
    """
    if not rows:
        return (0, 0)

    try:
        import psycopg
    except Exception as e:
        print(f"ERROR [pg_write_indicators] psycopg 不可用，跳过双写: {e}")
        return (0, 0)

    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        print("ERROR [pg_write_indicators] 环境变量 WORLDSIM_APP_PW 未设置，跳过双写")
        return (0, 0)

    try:
        arrays = _build_arrays(rows)
    except Exception as e:
        print(f"ERROR [pg_write_indicators] 行数据不规范，放弃本次双写: {e}")
        return (0, 0)

    conninfo = "host=worldsim-pg port=5432 dbname=worldsim user=worldsim_app"
    inserted = 0
    updated = 0
    try:
        with psycopg.connect(conninfo, password=pw, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(_INSERT_SQL, arrays)
                for rec in cur:
                    if rec[0]:          # did_insert = True（新插入）
                        inserted += 1
                    else:               # 命中唯一约束被 UPDATE
                        updated += 1
        return (inserted, updated)
    except Exception as e:
        print(f"ERROR [pg_write_indicators] 双写 worldsim-pg 失败（不影响原流程）: {e}")
        return (0, 0)


def health_check() -> bool:
    """探测 worldsim-pg 是否可达（供自测/运维使用，不阻断主流程）。"""
    try:
        import psycopg
    except Exception:
        return False
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        return False
    try:
        with psycopg.connect(
            "host=worldsim-pg port=5432 dbname=worldsim user=worldsim_app",
            password=pw, connect_timeout=10,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM indicators LIMIT 1")
        return True
    except Exception as e:
        print(f"ERROR [pg_write_indicators] health_check 失败: {e}")
        return False


if __name__ == "__main__":
    # 自测入口：直接 python pg_write_indicators.py 仅做连通性探测
    ok = health_check()
    print("worldsim-pg 可达:" if ok else "worldsim-pg 不可达/未配置", ok)
