"""
bleed_sensitivity.py — 出血规则参数敏感性分析

对 4 个核心出血参数各取 3 个水平（× 0.5 / × 1.0 / × 1.5 基准值），
共 3^4 = 81 组配置，每组跑 100 次 MC，记录终态 GRV 均值和标准差。

运行：
    cd S:/world-sim/macro-sim
    python scripts/bleed_sensitivity.py

输出：
    scripts/bleed_sensitivity_results.json  （原始结果）
    scripts/bleed_sensitivity_report.txt    （主效应摘要）

预计耗时：5-10 分钟（81 组 × 100 次 MC × 24 步）
"""
import sys
import os
import copy
import itertools
import json

import numpy as np

# 加入项目根路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.world_state import BLEED_PARAMS
from core.bifurcation import run_prediction
from core.world_state import load_from_macro_scan

# ── 配置 ──────────────────────────────────────────────────
KEY_PARAMS = [
    "grv_bleed_rate",
    "vix_bleed_rate",
    "credit_spread_bleed_rate",
    "yen_carry_vix_impact",
]
LEVELS = [0.5, 1.0, 1.5]
N_RUNS = 100

GRV_PATH        = "/app/macro_data/grv_history.jsonl"
FRED_PATH       = "/app/macro_data/fred_history"
CONFIG_PATH     = "/app/config/agents.yaml"
OUTPUT_JSON     = os.path.join(os.path.dirname(__file__), "bleed_sensitivity_results.json")
OUTPUT_REPORT   = os.path.join(os.path.dirname(__file__), "bleed_sensitivity_report.txt")


def main():
    print("[bleed_sensitivity] 加载初始世界状态...")
    try:
        world = load_from_macro_scan(
            grv_path="/app/macro_data/grv_latest.json",
            fred_path=FRED_PATH,
        )
        world.total_cycles = 24
    except Exception as e:
        print(f"[bleed_sensitivity] 加载世界状态失败: {e}")
        print("  提示：此脚本需在 NAS 容器内运行，或确保 /app/macro_data/ 路径可达")
        sys.exit(1)

    # 校准参数用默认值（不校准，只测 bleed 参数的敏感性）
    calibrated_params = {}

    combos = list(itertools.product(LEVELS, repeat=len(KEY_PARAMS)))
    total  = len(combos)
    results = []

    print(f"[bleed_sensitivity] 开始 sweep：{total} 组 × {N_RUNS} 次 MC")
    for i, multipliers in enumerate(combos):
        params_override = copy.copy(BLEED_PARAMS)
        for key, mult in zip(KEY_PARAMS, multipliers):
            params_override[key] = BLEED_PARAMS[key] * mult

        try:
            paths = run_prediction(
                initial_world=world,
                calibrated_agent_params=calibrated_params,
                n_runs=N_RUNS,
                predict_steps=24,
                config_path=CONFIG_PATH,
                bleed_params_override=params_override,
            )
            final_grv = [p.monthly_grv[-1] for p in paths if p and p.monthly_grv]
            grv_mean  = round(float(np.mean(final_grv)), 2) if final_grv else None
            grv_std   = round(float(np.std(final_grv)),  2) if final_grv else None
        except Exception as e:
            print(f"  [!] 第 {i+1} 组失败: {e}")
            grv_mean = grv_std = None

        entry = {
            "multipliers": dict(zip(KEY_PARAMS, multipliers)),
            "params":      {k: round(params_override[k], 4) for k in KEY_PARAMS},
            "grv_mean":    grv_mean,
            "grv_std":     grv_std,
        }
        results.append(entry)
        print(f"  [{i+1:02d}/{total}] ×{multipliers} → GRV mean={grv_mean} std={grv_std}")

    # 保存原始结果
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[bleed_sensitivity] 原始结果已写入 {OUTPUT_JSON}")

    # 主效应摘要（每个参数单独看，平均其他参数）
    lines = ["=== 出血规则参数主效应分析 ===\n"]
    lines.append(f"基准值：")
    for k in KEY_PARAMS:
        lines.append(f"  {k} = {BLEED_PARAMS[k]}")
    lines.append("")

    for ki, key in enumerate(KEY_PARAMS):
        lines.append(f"[{key}]")
        for lv in LEVELS:
            subset = [r for r in results if r["multipliers"][key] == lv and r["grv_mean"] is not None]
            if not subset:
                continue
            avg_mean = round(np.mean([r["grv_mean"] for r in subset]), 2)
            avg_std  = round(np.mean([r["grv_std"]  for r in subset]), 2)
            actual   = round(BLEED_PARAMS[key] * lv, 4)
            lines.append(f"  ×{lv:.1f} ({key}={actual}): GRV_mean={avg_mean}  GRV_std={avg_std}")
        lines.append("")

    report = "\n".join(lines)
    print(report)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[bleed_sensitivity] 摘要报告已写入 {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()
