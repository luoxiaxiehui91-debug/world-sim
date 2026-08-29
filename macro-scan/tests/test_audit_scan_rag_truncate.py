#!/usr/bin/env python3
"""审计回归测试 — scan-rag-truncate (审计发现 #12 HIGH correctness)。

被测：macro-scan/核心代码/rag_engine.py :: _build_index_pg (约 192-227 行)。

问题：重建索引分支执行
    cur.execute("TRUNCATE rag.embeddings WHERE collection_name = %s", (COLLECTION_NAME,))
PostgreSQL 的 TRUNCATE 语句既不支持 WHERE 子句、也不接受绑定参数，
是一条语法错误 SQL。任何真正的重建调用都会在 execute 时抛错，
被 _build_index_pg 的 except 捕获 → 返回 0，索引重建路径必然失败。
正确写法应为按 collection 删除旧行：DELETE FROM rag.embeddings WHERE collection_name = %s。

策略：不连接 PG（test_hint）。用 inspect.getsource 取 _build_index_pg 的源码，
断言其重建语句【不】使用非法的 `TRUNCATE ... WHERE` 组合。
这是【已确认但尚未修复】的 bug，故断言【正确】行为并加 xfail(strict=True)：
  - bug 存在 → 断言失败 → xfail（CI 绿）
  - bug 修复（改用 DELETE ... WHERE 或无 WHERE 的 TRUNCATE）→ xpass 触发 strict 失败，
    强制有人摘掉标记，测试转为活体守卫。
"""
import os
import re
import sys
import inspect

import pytest

# 将「核心代码」加入 path，使 import rag_engine 可用（与现有测试一致）
_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import rag_engine  # noqa: E402


@pytest.mark.xfail(
    strict=True,
    reason="审计发现 #12 HIGH correctness: _build_index_pg 用非法的 "
           "`TRUNCATE ... WHERE`（PG 不支持 WHERE/绑定参数），应改为 DELETE ... WHERE。",
)
def test_build_index_pg_no_illegal_truncate_where():
    """重建索引不得使用非法的 TRUNCATE ... WHERE（PG 不支持）。"""
    src = inspect.getsource(rag_engine._build_index_pg)

    # 匹配同一条语句中 TRUNCATE 后跟 WHERE（跨换行），大小写不敏感。
    illegal = re.search(r"TRUNCATE\b[\s\S]{0,200}?\bWHERE\b", src, re.IGNORECASE)

    assert illegal is None, (
        "重建索引使用了非法 SQL `TRUNCATE ... WHERE`（PostgreSQL 的 TRUNCATE "
        "不支持 WHERE 子句/绑定参数，会抛语法错误使重建返回 0）。"
        "正确写法应为 `DELETE FROM rag.embeddings WHERE collection_name = %s`。"
        f" 命中片段: {illegal.group(0)!r}" if illegal else ""
    )
