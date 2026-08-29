#!/usr/bin/env python3
"""审计回归测试 (#15 HIGH correctness) — narrative_processor.update_density_flags 冷启动分支缩进错误。

Bug: 在冷启动分支 (len(hist_rows) < 7) 中，SQLite 的 INSERT 密度标记位于
`if today_count > avg_7 * 1.5:` 条件内（有条件），但紧随其后的 PG 镜像写
`upsert_tianji_narrative_density_flag(...)` 缩进为 20 空格，与 `if today_count`
同级 → 变成【无条件】执行（只要 len(hist_rows) >= 1）。
结果：当 today_count NOT > avg*1.5 时，SQLite 不写 flag，但 PG 仍被写入 →
两库发散，向下游引擎持续注入虚假的密度突增标记。

正确行为：PG upsert 应与 SQLite INSERT 受同一条件约束——当阈值未触发时【不应】被调用。

当前代码有该 bug，故本测试对未修复代码会失败，用 xfail(strict=True) 标注：
  bug 存在 = xfail(CI 绿)；bug 修复后 = xpass 触发 strict 失败，强制摘标记转为活体守卫。

真实源码核对 (narrative_processor.py):
  - update_density_flags(window_days=30) 定义于第 244 行。
  - 冷启动分支 `if len(hist_rows) < 7:` 第 280 行；内层 `if len(hist_rows) >= 1:` 第 282。
  - `if today_count > avg_7 * 1.5:` 第 284 行 (20 空格缩进)。
  - SQLite `conn.execute(INSERT OR REPLACE ...)` 第 285-289 (条件内)。
  - `upsert_tianji_narrative_density_flag(dim, now.isoformat(), 1.6, 0)` 第 290 行
    (20 空格缩进 = 与 line 284 同级，无条件)。
  - 依赖：get_connection() 来自 tianji_db；PG 连接通过函数内 `import pg_read as _pg; _pg.connect()`；
    upsert_tianji_narrative_density_flag 来自 pg_write_collection（模块级 import 到 narrative_processor 命名空间）。
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import narrative_processor as np  # noqa: E402
import pg_read as _pg_read_mod  # noqa: E402


class _RecordingSqliteConn:
    """伪 SQLite 连接：记录所有 execute 的 SQL，commit/close 无副作用。"""

    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append(sql)
        return self

    def commit(self):
        pass

    def close(self):
        pass


class _FakePGResult:
    def __init__(self, one=None, all_=None):
        self._one = one
        self._all = all_

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class _FakePGConn:
    """伪 PG 只读连接：COUNT 查询走 fetchone()，GROUP BY 历史查询走 fetchall()。"""

    def __init__(self, today_count, hist_rows):
        self._today_count = today_count
        self._hist_rows = hist_rows

    def execute(self, sql, params=None):
        if "GROUP BY" in sql:
            return _FakePGResult(all_=self._hist_rows)
        # 第一个 execute 是 SELECT COUNT(*) ... → fetchone()[0]
        return _FakePGResult(one=(self._today_count,))

    def close(self):
        pass


@pytest.mark.xfail(
    strict=True,
    reason="审计发现 #15 HIGH correctness: 冷启动分支 PG upsert 缩进错误变成无条件执行，"
    "阈值未触发时仍写 PG → 与 SQLite 发散，注入虚假密度突增。",
)
def test_cold_start_pg_upsert_respects_threshold(monkeypatch):
    # 场景：冷启动 (len(hist_rows)=3, 即 1<=n<7)，且 today_count NOT > avg*1.5。
    #   hist_rows 三天各 2 篇 → avg=2 → 阈值=3；today_count=2 未超阈值。
    #   正确：SQLite 与 PG 都不应写 flag。
    hist_rows = [("2026-08-01", 2), ("2026-08-02", 2), ("2026-08-03", 2)]
    today_count = 2  # 2 NOT > 2 * 1.5 (=3.0)

    rec_conn = _RecordingSqliteConn()
    monkeypatch.setattr(np, "get_connection", lambda: rec_conn)

    # 函数内 `import pg_read as _pg` 会命中已缓存模块，故补丁其 connect。
    monkeypatch.setattr(
        _pg_read_mod, "connect", lambda: _FakePGConn(today_count, hist_rows)
    )

    # 只跑单一维度，缩小范围。
    monkeypatch.setattr(np, "GRV_DIMENSIONS", ["test_dim"])

    upsert_calls = []
    monkeypatch.setattr(
        np,
        "upsert_tianji_narrative_density_flag",
        lambda *a, **k: upsert_calls.append((a, k)),
    )
    # delete 分支在冷启动 continue 前不会走到，但仍防御性打桩。
    monkeypatch.setattr(
        np, "delete_tianji_narrative_density_flag", lambda *a, **k: None
    )

    np.update_density_flags()

    # 正确行为：阈值未触发 → SQLite 未写 INSERT flag。
    sqlite_wrote_flag = any(
        "narrative_density_flags" in sql and "INSERT" in sql.upper()
        for sql in rec_conn.executed
    )
    assert not sqlite_wrote_flag, (
        "SQLite 在阈值未触发时不应写 narrative_density_flags"
    )

    # 核心断言：PG upsert 应与 SQLite 同受阈值约束 → 阈值未触发时不应被调用。
    assert upsert_calls == [], (
        "阈值未触发时 PG upsert_tianji_narrative_density_flag 不应被调用"
        f"（实际被调用 {len(upsert_calls)} 次），当前缩进 bug 使其无条件执行。"
    )
