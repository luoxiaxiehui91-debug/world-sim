#!/usr/bin/env python3
"""审计回归测试 (finding #17 HIGH correctness) — monte_carlo_v2.MonteCarloV2._summarize 衰退概率口径。

Bug: _summarize 里衰退判定为
        any_negative_gdp = (paths[:, :, gdp_j] < 0).sum(axis=1) >= 2
     即"整个预测期内 gdp<0 的【月度步】总数 >= 2"（可不相邻），
     但同行注释写的是"衰退：GDP持续2季度负增长"。
     二者语义不符：实现统计的是【离散计数】，而非【连续】的 2 个季度（技术性衰退口径）。
     该 any_negative_gdp 直接产出生产用的 recession 概率（result['probabilities']['recession']）。

期望(正确)行为：仅有 2 个【不相邻】月为负、其余全正的路径，在任何"连续"衰退定义下
     都不应判为衰退 → recession 概率应为 0.0。
当前实现按离散计数会判为衰退（概率 1.0），故用 xfail(strict=True) 标注：
  - bug 存在时 = xfail (CI 绿)
  - bug 被修复时（改为连续 run 检测）= xpass 触发 strict 失败，强制摘标 → 转为活体守卫。

说明：_summarize(self, paths, var_index) 是干净的 seam，只读 self.model/n_paths/horizon
（纯信息字段），可用轻量构造的 MonteCarloV2 实例调用，无需真跑蒙特卡洛模拟。
"""
import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import monte_carlo_v2 as mc2  # noqa: E402


def _build_paths_isolated_negatives():
    """构造 1 条路径：gdp 在两个【不相邻】月为负，其余月及其它变量全为正常正值。

    paths 形状 = [n_paths, horizon+1, n_vars]，与 _summarize 的期望一致。
    返回 (paths, var_index)。
    """
    var_index = {v: i for i, v in enumerate(mc2.VARIABLES)}
    n_vars = len(mc2.VARIABLES)
    n_paths = 1
    months = 12  # 含起点，共 12 个时间步

    # 其它变量给中性正常值，避免触发别的情景概率或除零
    paths = np.zeros((n_paths, months, n_vars))
    paths[:, :, var_index["gdp_growth"]] = 2.0        # 默认正增长
    paths[:, :, var_index["inflation"]] = 2.5
    paths[:, :, var_index["unemployment"]] = 4.0
    paths[:, :, var_index["vix"]] = 18.0
    if "fed_funds_rate" in var_index:
        paths[:, :, var_index["fed_funds_rate"]] = 3.0
    if "sp500_return" in var_index:
        paths[:, :, var_index["sp500_return"]] = 5.0
    if "china_gdp" in var_index:
        paths[:, :, var_index["china_gdp"]] = 5.0

    # 两个【不相邻】月为负（第 1 月与第 6 月），中间为正 → 无任何连续负增长段
    gdp_j = var_index["gdp_growth"]
    paths[0, 1, gdp_j] = -1.0
    paths[0, 6, gdp_j] = -1.0

    return paths, var_index


@pytest.mark.xfail(strict=True, reason="finding #17: 衰退判定用离散计数(sum>=2)而非注释宣称的'持续2季度'连续口径")
def test_isolated_negative_months_not_recession():
    paths, var_index = _build_paths_isolated_negatives()
    sim = mc2.MonteCarloV2(model="gbm", n_paths=paths.shape[0], horizon=paths.shape[1] - 1, seed=42)

    result = sim._summarize(paths, var_index)
    recession = result["probabilities"]["recession"]

    # 正确语义：2 个不相邻的负月不构成连续衰退 → 概率应为 0.0
    assert recession == 0.0, (
        f"两个不相邻负增长月被误判为衰退：recession={recession}。"
        f"注释宣称'持续2季度负增长'，但实现是 (gdp<0).sum(axis=1)>=2 的离散计数。"
    )
