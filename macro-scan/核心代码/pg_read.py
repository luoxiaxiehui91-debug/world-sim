"""
pg_read.py — E0-C 只读层（worldsim-pg）

目标：为 consumer 模块提供与 SQLite 等价的只读连接，替代直接 sqlite3.connect(news.db /
forecast_tracker.db / narrative.db)，把读路径统一到 worldsim-pg。最终删除 SQLite 的前提。

设计要点（对齐重型 SOP + C0 交叉质询）：
- 只读：使用 worldsim_app（容器已注入 WORLDSIM_APP_PW），仅 SELECT，绝不写。
- 行工厂 _Row：同时支持 row["col"]（dict）与 row[0]（索引），等价 sqlite3.Row，
  使 consumer 翻读层时几乎只需「换 connect + ?→%s」，无需改取值代码。
- 每次 connect() 新建连接（不缓存）：consumer 多为 scheduler 子进程，且部分用 `with c:` 会关闭
  连接；无缓存避免共享连接被关后复用失效。读为低频定时任务，连接开销可忽略。
- search_path = news,forecast,tianji,public，表名可省略 schema 前缀。
- 占位符：PG 用 %s（SQLite 用 ?）。翻 reader 时把 SQL 的 ? 改 %s 即可。

P2 翻 reader 模板：
    # 旧: conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True); conn.row_factory = sqlite3.Row
    # 新: conn = pg_read.connect()
    rows = conn.execute("SELECT ... WHERE x IN (%s,%s) AND y >= %s", (a, b, y)).fetchall()
    # row["col"] / row[0] 行为不变；conn.close() 不变

部署：本文件 rsync 进运行区即生效（新文件，无需 docker restart）。
"""

import os
import logging

import psycopg

_PG_HOST = "worldsim-pg"
_PG_PORT = 5432
_PG_DB = "worldsim"
_PG_USER = "worldsim_app"
_SEARCH_PATH = "news,forecast,tianji,public"

_log = logging.getLogger("pg_read")


class _Row:
    """等价 sqlite3.Row：支持下标(列名或索引)双访问。"""

    __slots__ = ("_d", "_t")

    def __init__(self, cols, vals):
        self._d = dict(zip(cols, vals))
        self._t = tuple(vals)

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._t[k]
        return self._d[k]

    def __iter__(self):
        return iter(self._t)

    def __len__(self):
        return len(self._t)

    def __contains__(self, k):
        return k in self._d

    def keys(self):
        return self._d.keys()

    def items(self):
        return self._d.items()

    def __repr__(self):
        return "_Row({!r})".format(self._d)


def _row_factory(cursor):
    # psycopg 3 协议：row_factory(cursor) 返回一个逐行 maker(raw_tuple) -> Row
    cols = [d.name for d in cursor.description]

    def _make(raw):
        return _Row(cols, raw)

    return _make


def connect():
    """返回只读 PG 连接（_Row 行工厂）。失败返回 None（调用方应保留 SQLite 兜底或报错）。"""
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        _log.error("WORLDSIM_APP_PW 未注入，PG 读连接不可用")
        return None
    try:
        conn = psycopg.connect(
            host=_PG_HOST,
            port=_PG_PORT,
            dbname=_PG_DB,
            user=_PG_USER,
            password=pw,
            row_factory=_row_factory,
            autocommit=True,
            options="-c search_path={}".format(_SEARCH_PATH),
        )
        return conn
    except Exception as e:
        _log.error("PG 读连接失败: %s", e)
        return None


def exec_read(sql, params=()):
    """便捷：执行只读查询，返回 _Row 列表；连接/查询失败返回空列表（不抛）。"""
    conn = connect()
    if conn is None:
        return []
    try:
        with conn:
            cur = conn.execute(sql, params)
            return cur.fetchall()
    except Exception as e:
        _log.error("PG 读查询失败: %s | sql=%s", e, sql)
        return []


def smoke_test():
    """容器内自检：连通 + 抽样 news 三表行数。需 WORLDSIM_APP_PW。返回 dict。"""
    conn = connect()
    if conn is None:
        return {"ok": False, "reason": "no_conn"}
    try:
        with conn:
            n_articles = conn.execute("SELECT COUNT(*) FROM news.articles").fetchone()[0]
            n_sig = conn.execute("SELECT COUNT(*) FROM news.signal_episodes").fetchone()[0]
            n_syn = conn.execute("SELECT COUNT(*) FROM news.synthesis_log").fetchone()[0]
        return {
            "ok": True,
            "articles": n_articles,
            "signal_episodes": n_sig,
            "synthesis_log": n_syn,
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)}


if __name__ == "__main__":
    import json

    print(json.dumps(smoke_test(), ensure_ascii=False))
