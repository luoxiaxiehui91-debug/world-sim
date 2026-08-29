#!/usr/bin/env python3
"""审计回归测试 (finding #18 HIGH correctness) — c0_compute_weights.compute_weights。

Bug: compute_weights 先在同一 target_type 内按逆波动率归一(w = raw/tot, 和=1)，
     再对每个权重 clamp 到 [WEIGHT_FLOOR=0.05, WEIGHT_CEIL=5.00]（源码 353-368 行）。
     对大维度（如 global_composite ~39 个序列，归一后每个 ≈ 1/39 ≈ 0.026）所有权重
     都 < 0.05，全部被 floor 抬到 0.05 → sum 变成 39*0.05 = 1.95，破坏了 sum≈1 的归一
     不变量，大维度权重被塌平成同一值。

期望(正确)行为：同一 target_type 的派生权重之和 ≈ 1.0。
当前实现会破坏该不变量，故用 xfail(strict=True) 标注：
  - bug 存在时 = xfail (CI 绿)
  - bug 被修复时 = xpass 触发 strict 失败，强制摘标 → 转为活体守卫。
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import c0_compute_weights as c0  # noqa: E402


def _build_series_for_target(target_type, n):
    """构造 n 个都映射到 target_type 的 FRED 序列输入。

    compute_weights 消费 {source_id: [(as_of, value, data_vintage), ...]}。
    每个序列给一段有微小变化的历史值 → _score_series 返回正的 inv_cv、coverage=1，
    data_vintage=None → lag=0 → fresh=1 → raw>0，落入归一分支(而非等分兜底)。
    用 FRED_SEED 里真正映射到该 target_type 的 source_id，避免 'uncategorized' 兜底与 WARN。
    """
    sids = [sid for sid, tt in c0.FRED_SEED.items() if tt == target_type]
    assert len(sids) >= n, (
        f"FRED_SEED 中 target_type={target_type} 的序列只有 {len(sids)} 个，"
        f"不足以构造 {n} 个测试输入"
    )
    sids = sids[:n]
    series = {}
    for i, sid in enumerate(sids):
        # 每个序列略有不同的斜率，保证 raw 分数为正且不完全相同
        base = 100.0 + i
        pts = [(f"2020-01-{d:02d}", base + d * (1 + 0.01 * i), None)
               for d in range(1, 12)]
        series[sid] = pts
    return series


@pytest.mark.xfail(strict=True,
                   reason="审计发现 #18 HIGH correctness: compute_weights 归一后对每个"
                          "权重 clamp 到 [0.05,5.0]，大维度(~39 序列)归一值 <0.05 全被抬到"
                          "floor，sum 从 1.0 被破坏成 ~1.95")
def test_large_target_type_weights_sum_to_one():
    # global_composite 是生产里最大的维度（~39 个 FRED 序列）
    target = "global_composite"
    n = 39
    series = _build_series_for_target(target, n)

    rows = c0.compute_weights(series)

    # 只取该 target_type 的行
    weights = [w for sid, tt, w in rows if tt == target]
    assert len(weights) == n, f"期望 {n} 行 {target}，实际 {len(weights)}"

    total = sum(weights)
    # 正确行为：同一 target_type 内归一后权重之和 ≈ 1.0
    assert total == pytest.approx(1.0, abs=1e-3), (
        f"{target} 权重之和应 ≈1.0，实际={total:.5f}"
        f"（floor={c0.WEIGHT_FLOOR} 钳位破坏了归一不变量）"
    )
