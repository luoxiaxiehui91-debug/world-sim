# -*- coding: utf-8 -*-
"""
test_audit_scan_splitbrain.py — 分叉漂移守卫（审计发现 #19 HIGH architecture）

背景
----
`tianji_db.py` 与 `weight_matrix.py` 在 macro-scan 与 macro-ji 两处各存一份独立实现。
两份源码顶部的维护契约要求："改一份必须同步另一份，两份接口签名应保持一致"。
审计确认该契约已破（scan 版 tianji_db.py 437 行 vs ji 版 308 行等）。

本守卫比对两处同名文件的【公开函数接口签名】（函数名 + 位置参数名列表；
下划线私有 helper 允许差异，因契约约束的是 interface 签名而非内部实现）。

生命周期
--------
- bug 存在（接口已漂移）→ 断言失败 → xfail（CI 绿）。
- 有人重新同步两份接口 → xpass → strict xfail 触发失败 → 强制摘掉本标记，
  测试转为活体守卫，此后任何再次漂移都会红。

设计约束：纯文件读 + ast 解析，不 import 被测模块（避免 psycopg/网络等副作用），
任意 cwd 可运行；不输出中文到 stdout（Windows cp1252 崩溃）。
"""
import ast
from pathlib import Path

import pytest

# 本文件位于 <world-sim>/macro-ji/tests/ ，向上两级即 world-sim 根
_WS_ROOT = Path(__file__).resolve().parent.parent.parent

# 需保持接口一致的同名文件对：(逻辑名, scan 侧路径, ji 侧路径)
_FILE_PAIRS = [
    (
        "tianji_db",
        _WS_ROOT / "macro-scan" / "核心代码" / "tianji_db.py",
        _WS_ROOT / "macro-ji" / "tianji_db.py",
    ),
    (
        "weight_matrix",
        _WS_ROOT / "macro-scan" / "核心代码" / "weight_matrix.py",
        _WS_ROOT / "macro-ji" / "weight_matrix.py",
    ),
]


def _public_signatures(path: Path) -> dict:
    """返回 {函数名: [位置参数名...]}，仅顶层公开函数（不以 _ 开头）。"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            out[node.name] = [a.arg for a in node.args.args]
    return out


@pytest.mark.xfail(
    strict=True,
    reason="审计发现 #19 HIGH architecture: tianji_db/weight_matrix 在 macro-scan 与 "
    "macro-ji 两份已分叉，公开接口签名不一致（如 update_prediction_verified 参数漂移），"
    "违反源码顶部'两份接口签名应保持一致'契约",
)
def test_shared_files_have_matching_public_interface():
    # 前置：四个文件都必须存在，否则守卫本身失效
    for _name, scan_path, ji_path in _FILE_PAIRS:
        assert scan_path.is_file(), f"missing scan-side file: {scan_path}"
        assert ji_path.is_file(), f"missing ji-side file: {ji_path}"

    divergences = []
    for name, scan_path, ji_path in _FILE_PAIRS:
        scan_sigs = _public_signatures(scan_path)
        ji_sigs = _public_signatures(ji_path)

        only_scan = sorted(set(scan_sigs) - set(ji_sigs))
        only_ji = sorted(set(ji_sigs) - set(scan_sigs))
        arg_diffs = {
            fn: (scan_sigs[fn], ji_sigs[fn])
            for fn in (set(scan_sigs) & set(ji_sigs))
            if scan_sigs[fn] != ji_sigs[fn]
        }
        if only_scan or only_ji or arg_diffs:
            divergences.append(
                f"[{name}] only_scan={only_scan} only_ji={only_ji} arg_diffs={arg_diffs}"
            )

    # 期望（正确）行为：两处公开接口完全一致，无任何漂移
    assert not divergences, "public interface drift detected:\n" + "\n".join(divergences)
