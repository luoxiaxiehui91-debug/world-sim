# -*- coding: utf-8 -*-
"""
回归测试：core.narrative_format.format_narrative (macro-sim · 天璇)

目的
----
锁定 B1 bug 修复后 `format_narrative` 的真实行为，防止未来回退。
本文件是**自包含纯 Python 脚本**，不依赖 pytest（macro-sim 未安装 pytest）。

运行方式
--------
    cd /s/world-sim/macro-sim && python tests/test_narrative_format.py

也可在 macro-sim 根目录下直接执行 `python tests/test_narrative_format.py`。
文件顶部已把 macro-sim 根目录加入 sys.path，因此 `from core.narrative_format
import format_narrative` 在从 tests/ 目录或根目录运行时均可解析。

断言原则
--------
所有期望值均来自对真实源码实际运行结果的固化（先跑一遍确认，再写入断言），
不凭空臆测。其中有两个用例的真实输出与主理人原始描述不一致，已在用例 docstring
中标注（见 test_single_label / test_digit_prefix_with_content），并在测试
报告里作为发现项提示。
"""

import os
import sys

# 将 macro-sim 根目录加入 sys.path，使 `core` 包可被导入。
# __file__ 位于 <root>/tests/test_narrative_format.py，向上两级即 <root>。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.narrative_format import format_narrative  # noqa: E402


# --------------------------------------------------------------------------- #
# 测试用例（每个函数以 test_ 开头，由底部 runner 自动收集并逐一执行）
# --------------------------------------------------------------------------- #

def test_empty_string_returns_empty_list():
    """空串守卫：if not raw -> []。"""
    actual = format_narrative("")
    expected = []
    assert actual == expected, f"空串应返回 []，实际 {actual!r}"


def test_three_labels_no_content_bold():
    """三个 bold label 均无内容 -> ['', '']（空 content 跳过，只留首尾空串）。"""
    raw = "**情景定性**\n**核心传导链**\n**对你的影响**"
    actual = format_narrative(raw)
    expected = ["", ""]
    assert actual == expected, f"三空 label 应返回 ['', '']，实际 {actual!r}"


def test_convention_brackets_format():
    """约定分隔符【label】content -> 三段结构化并美化为 **label**：content。"""
    raw = "【情景定性】内容A【核心传导链】内容B【对你的影响】内容C"
    actual = format_narrative(raw)
    expected = [
        "",
        "**情景定性**：内容A",
        "**核心传导链**：内容B",
        "**对你的影响**：内容C",
        "",
    ]
    assert actual == expected, f"约定格式应美化，实际 {actual!r}"


def test_plain_text_no_separator():
    """无分隔符纯文本 -> ['', <文本>, '']（走 else 分支）。"""
    raw = "这是一段普通叙事"
    actual = format_narrative(raw)
    expected = ["", "这是一段普通叙事", ""]
    assert actual == expected, f"纯文本应 ['', text, '']，实际 {actual!r}"


def test_digit_prefix_no_content():
    """数字前缀 + 无内容：'1. **a**\\n2. **b**' -> ['', '']。

    注意：_DIGIT_PREFIX_RE 仅匹配「\\n数字.」前缀，故行首的 '1. ' 未被清理，
    但其内容落在 parts[0]（多段分支不使用 parts[0]），'a'/'b' 内容均为空被跳过，
    最终得到 ['', '']。"""
    raw = "1. **a**\n2. **b**"
    actual = format_narrative(raw)
    expected = ["", ""]
    assert actual == expected, f"数字前缀无内容应 ['', '']，实际 {actual!r}"


def test_b1_real_sample():
    """真实 B1 样例（模拟 GLM 实跑输出）：三段结构化，且不残留【】。"""
    raw = "**情景定性**：慢性高压\n**核心传导链**：从财政…\n**对你的影响**：警惕…"
    actual = format_narrative(raw)
    expected = [
        "",
        "**情景定性**：慢性高压",
        "**核心传导链**：从财政…",
        "**对你的影响**：警惕…",
        "",
    ]
    assert actual == expected, f"B1 样例结构不符，实际 {actual!r}"
    # 固化 B1 修复核心：归一化后不应再残留【】分隔符
    assert "【" not in "".join(actual), f"B1 修复后不应残留【】，实际 {actual!r}"


def test_single_label():
    """单标签走 else 分支 -> ['', <归一化文本>, '']。

    注意（与原始描述差异）：真实实现中 else 分支**不做**标签美化，
    返回的是归一化后的【label】形式（且 bold 正则的 \\s* 吞掉了标签后的换行）。
    真实输出为 ['', '【只一个标签】内容', '']，而非 '**只一个标签**：内容'。
    此处断言以真实代码输出为准。"""
    raw = "**只一个标签**\n内容"
    actual = format_narrative(raw)
    expected = ["", "【只一个标签】内容", ""]
    assert actual == expected, f"单标签 else 分支真实输出不符，实际 {actual!r}"


def test_digit_prefix_with_content():
    """数字前缀 + 有内容：'1. **情景定性**\\n这是内容'。

    注意（与原始描述差异）：原始描述期望走美化分支得到
    ['', '**情景定性**：这是内容', '']；但真实实现中：
      (1) _DIGIT_PREFIX_RE 仅匹配「\\n数字.」前缀，行首 '1. ' 不会被清理；
      (2) 该输入仅含 1 个 label，触发 else 分支（不美化、保留【】与数字前缀）。
    真实输出为 ['', '1. 【情景定性】这是内容', '']。此处断言以真实代码输出为准，
    并作为发现项提示主理人：若期望美化分支，源码数字前缀清理与多段判定需调整。"""
    raw = "1. **情景定性**\n这是内容"
    actual = format_narrative(raw)
    expected = ["", "1. 【情景定性】这是内容", ""]
    assert actual == expected, f"数字前缀有内容真实输出不符，实际 {actual!r}"


def test_mixed_empty_labels_skipped():
    """混合：'**a**\\nfoo\\n**b**\\n**c**'（b/c 后无内容）-> ['', '**a**：foo', '']。"""
    raw = "**a**\nfoo\n**b**\n**c**"
    actual = format_narrative(raw)
    expected = ["", "**a**：foo", ""]
    assert actual == expected, f"混合空 label 跳过不符，实际 {actual!r}"


# --------------------------------------------------------------------------- #
# 额外边界用例（非主理人必填清单，补充锁定可疑边界）
# --------------------------------------------------------------------------- #

def test_whitespace_only_not_empty():
    """纯空白输入：'   \\n  ' 非真空 -> ['', '', '']（仅真空串才返回 []）。"""
    raw = "   \n  "
    actual = format_narrative(raw)
    expected = ["", "", ""]
    assert actual == expected, f"纯空白应 ['', '', '']，实际 {actual!r}"


def test_digit_prefix_after_leading_newline_cleaned():
    """前导换行后的数字前缀被清理：'\\n1. **a**\\n2. **b**' -> ['', '']。"""
    raw = "\n1. **a**\n2. **b**"
    actual = format_narrative(raw)
    expected = ["", ""]
    assert actual == expected, f"前导换行数字前缀应清理并得 ['', '']，实际 {actual!r}"


# --------------------------------------------------------------------------- #
# 自包含 runner
# --------------------------------------------------------------------------- #

def _collect_test_funcs():
    funcs = []
    for name in sorted(globals()):
        if name.startswith("test_") and callable(globals()[name]):
            funcs.append((name, globals()[name]))
    return funcs


def main():
    tests = _collect_test_funcs()
    passed = 0
    failed = 0
    print(f"== running {len(tests)} tests for format_narrative ==")
    for name, func in tests:
        try:
            func()
            passed += 1
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name} (exception): {type(e).__name__}: {e}")
    print("-" * 40)
    if failed == 0:
        print(f"ALL PASSED ({passed})")
        sys.exit(0)
    else:
        print(f"FAILED ({failed}/{passed + failed})")
        sys.exit(1)


if __name__ == "__main__":
    main()
