"""
brier_calc.py — Brier Score / BSS / 锐度计算

供天玑 V1 验证层调用。与 tianji_db.py 的 update_prediction_verified() 配合使用：
    from brier_calc import compute_brier_score, compute_bss, compute_sharpness
    bs  = compute_brier_score(predicted_prob=0.7, outcome=1)
    bss = compute_bss(brier_score=bs, climatology_prob=0.3)

函数说明：
  compute_brier_score(predicted_prob, outcome)
      → Brier Score = (f - o)²，越小越好，完美=0，无技术=0.25（随机猜测时均值）

  compute_bss(brier_score, climatology_prob)
      → BSS = 1 - BS / BS_climatology，>0 优于气候学基准，=0 等于基准，<0 更差

  compute_sharpness(prob_list)
      → 锐度 = 预测概率落在 [0.3, 0.7] 以外的比例，越高越锐利
      → arch_review 要求 sharpness > 0.4 为达标

  batch_score(records)
      → 批量计算，records 格式：[{"prob": float, "outcome": int}, ...]
      → 返回 {"mean_bs": float, "bss": float, "sharpness": float, "n": int}
"""

from __future__ import annotations
import math


def compute_brier_score(predicted_prob: float, outcome: int) -> float:
    """
    单条预测的 Brier Score。
    predicted_prob: 预测概率 [0, 1]
    outcome: 实际结果，1=发生，0=未发生
    """
    if not (0.0 <= predicted_prob <= 1.0):
        raise ValueError(f"predicted_prob 必须在 [0,1]，得到 {predicted_prob}")
    if outcome not in (0, 1):
        raise ValueError(f"outcome 必须是 0 或 1，得到 {outcome}")
    return (predicted_prob - outcome) ** 2


def compute_bss(brier_score: float, climatology_prob: float = 0.5) -> float:
    """
    Brier Skill Score = 1 - BS / BS_climatology。
    climatology_prob: 基准概率（历史发生率）。
        - 无先验信息时用 0.5（最大熵，最保守基准）
        - 有历史数据时传入该事件类型的历史发生频率
    返回值：>0 优于基准，=0 等于基准，<0 比随机猜测更差。
    """
    if not (0.0 < climatology_prob < 1.0):
        raise ValueError(f"climatology_prob 必须在 (0,1)，得到 {climatology_prob}")
    bs_clim = climatology_prob * (1.0 - climatology_prob)
    if bs_clim == 0.0:
        return 0.0
    return 1.0 - brier_score / bs_clim


def compute_sharpness(prob_list: list[float]) -> float:
    """
    锐度 = 预测概率在 (0, 0.3) ∪ (0.7, 1) 范围内的比例。
    arch_review 基准：sharpness > 0.4 为达标。
    空列表返回 0.0。
    """
    if not prob_list:
        return 0.0
    sharp_count = sum(1 for p in prob_list if p < 0.3 or p > 0.7)
    return sharp_count / len(prob_list)


def batch_score(
    records: list[dict],
    climatology_prob: float = 0.5,
) -> dict:
    """
    批量计算一组预测的评分摘要。
    records: [{"prob": float, "outcome": int}, ...]
    outcome 为 None 的记录自动跳过（待验证）。

    返回：
    {
        "n": int,               # 有效记录数
        "mean_bs": float,       # 平均 Brier Score
        "bss": float,           # Brier Skill Score（基于 climatology_prob）
        "sharpness": float,     # 锐度
        "calibration_error": float,  # 平均预测概率与实际发生率之差（绝对值）
    }
    """
    valid = [r for r in records if r.get("outcome") is not None]
    if not valid:
        return {"n": 0, "mean_bs": None, "bss": None, "sharpness": None,
                "calibration_error": None}

    bs_list   = [compute_brier_score(r["prob"], r["outcome"]) for r in valid]
    prob_list = [r["prob"] for r in valid]
    outcomes  = [r["outcome"] for r in valid]

    mean_bs   = sum(bs_list) / len(bs_list)
    bss       = compute_bss(mean_bs, climatology_prob)
    sharpness = compute_sharpness(prob_list)

    mean_pred    = sum(prob_list) / len(prob_list)
    actual_rate  = sum(outcomes) / len(outcomes)
    calib_error  = abs(mean_pred - actual_rate)

    return {
        "n":                len(valid),
        "mean_bs":          round(mean_bs, 6),
        "bss":              round(bss, 6),
        "sharpness":        round(sharpness, 4),
        "calibration_error": round(calib_error, 4),
    }


def score_grv_prediction(
    predicted_prob: float,
    predicted_direction: str,
    actual_grv_change: float,
    threshold: float = 5.0,
    climatology_prob: float = 0.3,
) -> dict:
    """
    专门用于 GRV 方向性预测（quantitative 类型）的验证。

    predicted_direction: "up" / "down" / "neutral"
    actual_grv_change: 验证窗口内 global_composite 实际变化量（正=上升）
    threshold: ±5 为方向变化阈值（与 _archive_to_tianji 一致）

    返回 brier_score, brier_skill_score, outcome（0/1），供写入 predictions 表。
    """
    # 将实际变化量转为二元 outcome
    if predicted_direction == "up":
        outcome = 1 if actual_grv_change > threshold else 0
    elif predicted_direction == "down":
        outcome = 1 if actual_grv_change < -threshold else 0
    else:  # neutral
        outcome = 1 if abs(actual_grv_change) <= threshold else 0

    bs  = compute_brier_score(predicted_prob, outcome)
    bss = compute_bss(bs, climatology_prob)

    return {
        "outcome":           outcome,
        "brier_score":       round(bs, 6),
        "brier_skill_score": round(bss, 6),
        "actual_grv_change": round(actual_grv_change, 2),
    }


if __name__ == "__main__":
    # 简单自测
    print("=== brier_calc 自测 ===")
    bs = compute_brier_score(0.8, 1)
    print(f"BS(0.8, 1) = {bs:.4f}  期望 0.04")
    bs2 = compute_brier_score(0.3, 0)
    print(f"BS(0.3, 0) = {bs2:.4f}  期望 0.09")
    bss = compute_bss(0.04, climatology_prob=0.3)
    print(f"BSS(0.04, clim=0.3) = {bss:.4f}  期望 ~0.81")
    sh = compute_sharpness([0.1, 0.8, 0.5, 0.9, 0.2])
    print(f"Sharpness([0.1,0.8,0.5,0.9,0.2]) = {sh:.2f}  期望 0.8")
    result = batch_score([
        {"prob": 0.7, "outcome": 1},
        {"prob": 0.3, "outcome": 0},
        {"prob": 0.9, "outcome": 1},
        {"prob": 0.4, "outcome": None},  # 待验证，跳过
    ])
    print(f"batch_score = {result}")
    grv_r = score_grv_prediction(0.65, "up", actual_grv_change=8.3)
    print(f"score_grv_prediction(0.65, up, +8.3) = {grv_r}")
    print("=== 自测完成 ===")
