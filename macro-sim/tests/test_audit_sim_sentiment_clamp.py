# -*- coding: utf-8 -*-
"""
回归测试（审计发现 #9 HIGH correctness）：market_sentiment 语义域应为 [-1, 1]，
但 bifurcation._add_initial_noise 的 else 分支用 max(0.0, min(1.0, ...)) 把它钳到 [0, 1]，
抹掉悲观起点并注入正偏置。

被测真实代码
-----------
core/bifurcation.py  _add_initial_noise (line ~211)
    noise_config 中 market_sentiment scale=0.15，非 china_credit_impulse 分支执行
    setattr(w, var, max(0.0, min(1.0, current + noise)))  → 域被钳成 [0,1]。
core/world_state.py  apply_sentiment_delta (line ~327)
    world.market_sentiment = max(-1.0, min(1.0, s + raw_delta * damping))  → 权威语义域 [-1,1]。

设计
----
构造 market_sentiment = -0.5（明确的悲观起点）的最小真实 world，
跑 _add_initial_noise 多个种子。正确行为：域 [-1,1]，-0.5 + N(0,0.15) 绝大多数仍为负，
均值应贴近 -0.5、最小值应 < 0。当前 bug 把负值钳到 0.0 → 均值≈0、最小值≥0。

因为这是【已确认但尚未修复的 bug】，对当前代码该测试会失败，
故用 @pytest.mark.xfail(strict=True) 断言【正确】行为：bug 存在时=xfail(CI绿)；
被修复后=xpass 触发 strict 失败，强制摘标记 → 转为活体守卫。

运行
----
    cd /s/world-sim/macro-sim && python -m pytest tests/test_audit_sim_sentiment_clamp.py -q
顶部自注入 sys.path，使 `core` 包可解析（与本模块其他测试一致）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.world_state import MacroWorldState
from core.bifurcation import _add_initial_noise


def _mk_world(sentiment: float) -> MacroWorldState:
    """最小真实 MacroWorldState（补齐所有无默认字段），仅关心 market_sentiment。"""
    w = MacroWorldState(
        vix=20.0, vix_baseline=20.0,
        grv=60.0, grv_baseline=60.0,
        grv_energy=20.0, grv_energy_baseline=20.0,
        grv_military=30.0, grv_trade=30.0,
        us_china_grv=50.0, t10y2y=-10.0,
        credit_spread=200.0, dff=5.0, situation_level=2,
    )
    w.market_sentiment = sentiment
    return w


@pytest.mark.xfail(
    strict=True,
    reason="审计发现 #9 HIGH correctness: _add_initial_noise else 分支把 market_sentiment "
           "钳到 [0,1] 而非语义域 [-1,1]，抹掉悲观起点并注入正偏置",
)
def test_initial_noise_preserves_negative_sentiment_domain():
    start = -0.5
    perturbed = [
        _add_initial_noise(_mk_world(start), seed).market_sentiment
        for seed in range(200)
    ]

    # 语义域 [-1,1] 下：start=-0.5 + N(0,0.15)，绝大多数仍为负。
    assert min(perturbed) < 0.0, (
        "扰动后没有任何一次保持负值 —— 悲观起点被钳到 [0,1] 抹掉了 "
        "(min={:.4f})".format(min(perturbed))
    )
    mean = sum(perturbed) / len(perturbed)
    assert mean < 0.0, (
        "扰动后均值非负 (mean={:.4f})，说明 -0.5 的悲观起点被折叠成正偏置".format(mean)
    )
    # 域下界不应被 0.0 截断
    assert all(v >= -1.0 for v in perturbed), "不得越过语义下界 -1.0"
