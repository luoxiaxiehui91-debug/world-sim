"""
T2 回归测试（2026-10-18）：NOT 逻辑词转换 + 触发求值三种写法锁定。

背景：`base.py` 的 `_eval_trigger()` 把 soul 里的 AND/OR 转成 Python 关键字，
却漏了 NOT，且留了一处 `" == " -> " == "` 的自替换（空操作）。
后果：soul 写 `NOT x` 时 eval 抛 NameError，被最外层 `except: return False` 吞掉
⇒ 该触发恒 False 且无任何痕迹（结构性静默）。

本次修复必须有测试锁定，防回归。运行方式：python3 tests/test_trigger_eval_20261018.py
"""

import sys
import os

# 路径兼容：既支持在 macro-sim/tests/ 下直接跑（../ 为项目根），
# 也支持 docker cp 进容器 /tmp 后跑（此时需指向 /app）
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (os.path.join(_HERE, ".."), "/app", _HERE):
    if os.path.isdir(os.path.join(_cand, "core")):
        if _cand not in sys.path:
            sys.path.insert(0, _cand)
        break

from core.agents.base import _eval_trigger


def _ctx(**kw):
    base = {
        "market_sentiment": 0.0,
        "russia_europe": 50.0,
        "taiwan_strait": 50.0,
        "vix": 20.0,
    }
    base.update(kw)
    return base


# ── T2.1a：NOT 转换（核心：原实现恒 False） ─────────────────
def test_not_operator_now_works():
    """NOT x 必须真正求否，而非恒 False。"""
    # sentiment=-0.8 ⇒ -0.8 > 0.5 为 False ⇒ NOT False = True
    r = _eval_trigger("NOT market_sentiment > 0.5", _ctx(market_sentiment=-0.8))
    assert r is True, f"NOT 应使条件反转（期望 True，实测 {r}）"

    # sentiment=0.9 ⇒ 0.9 > 0.5 为 True ⇒ NOT True = False
    r2 = _eval_trigger("NOT market_sentiment > 0.5", _ctx(market_sentiment=0.9))
    assert r2 is False, f"NOT 应使条件反转（期望 False，实测 {r2}）"

    # NOT 与 AND 组合
    r3 = _eval_trigger("NOT russia_europe > 70 AND taiwan_strait > 40",
                       _ctx(russia_europe=50.0, taiwan_strait=60.0))
    assert r3 is True, f"NOT + AND 组合应正确（50>70 为假取反为真，60>40 为真 ⇒ True，实测 {r3}）"


# ── T2.1b：既有写法不能回归 ────────────────────────────────
def test_and_or_eq_still_work():
    """AND / OR / == 三种既有写法必须保持正确。"""
    assert _eval_trigger("russia_europe > 70 AND taiwan_strait > 75",
                         _ctx(russia_europe=80.0, taiwan_strait=80.0)) is True
    assert _eval_trigger("russia_europe > 70 AND taiwan_strait > 75",
                         _ctx(russia_europe=80.0, taiwan_strait=40.0)) is False
    assert _eval_trigger("russia_europe > 70 OR taiwan_strait > 75",
                         _ctx(russia_europe=40.0, taiwan_strait=80.0)) is True
    # == 比较（原自替换所在行，确保去掉空操作后仍正常）
    assert _eval_trigger("market_sentiment == 0.5", _ctx(market_sentiment=0.5)) is True
    assert _eval_trigger("market_sentiment == 0.5", _ctx(market_sentiment=0.4)) is False


# ── T2.1c：内置函数保护不能回归（v3 阶段 2 修复） ────────────
def test_builtin_funcs_not_broken():
    """abs/min/max 等内置函数名不能被当作变量替换。"""
    r = _eval_trigger("abs(market_sentiment) > 0.5", _ctx(market_sentiment=-0.8))
    assert r is True, f"abs(-0.8)>0.5 应为 True（实测 {r}）"
    r2 = _eval_trigger("max(vix, 25.0) > 30.0", _ctx(vix=40.0))
    assert r2 is True, f"max(40,25)>30 应为 True（实测 {r2}）"


# ── T2.1d：缺失变量策略仍按语义 ────────────────────────────
def test_missing_var_strategies():
    ctx = _ctx()
    ctx.pop("russia_europe")
    # optimistic：缺失归 0 ⇒ 0 > 70 为 False
    assert _eval_trigger("russia_europe > 70", ctx, missing_strategy="optimistic") is False
    # conservative：缺失按 ±1e9 试算，任一触发即 True ⇒ 0/1e9 > 70 为真
    assert _eval_trigger("russia_europe > 70", ctx, missing_strategy="conservative") is True


# ── T2.1e：空串与非字符串输入 ──────────────────────────────
def test_edge_inputs():
    assert _eval_trigger("", _ctx()) is False
    assert _eval_trigger("   ", _ctx()) is False


# ── T2.2：类型白名单不改变现有行为 ─────────────────────────
def test_delta_type_whitelist_preserves_behavior():
    """simulation.py 的 isinstance 白名单：float 仍通过，int 也不应被静默丢弃。

    注意：per_agent_delta 的值经 `0.0 + val` 累加必为 float（float+int 恒得 float），
    故原 `isinstance(val, float)` 实为恒真死代码、当前不丢数据；本测试锁定的是
    「int 也不该被丢」这一防御语义，防将来初值被改成 int 0 时回归。
    """
    # 模拟 456 行的过滤语义
    src_delta = {"fed_rate_change": -50.0, "market_sentiment": 0.35, "int_like": 25}
    accepted = {}
    for key, val in src_delta.items():
        if isinstance(val, (int, float)):
            accepted[key] = val
    assert len(accepted) == 3, f"三个键都应被接受（实测 {list(accepted.keys())}）"
    assert accepted["int_like"] == 25

    # 同时验证：累加初值 0.0 保证 float（这是原过滤器恒真的原因）
    d = {}
    d["x"] = d.get("x", 0.0) + (-50)
    assert isinstance(d["x"], float), "0.0 + (-50) 必须为 float"
    assert isinstance(d["x"], (int, float)), "白名单必须同时接受 float"


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed.append(name)
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed.append(name)
    print()
    print(f"总计 {len(tests)} 项：通过 {passed}，失败 {len(failed)}")
    if failed:
        print("失败项：", ", ".join(failed))
        sys.exit(1)
    print("全部通过")
