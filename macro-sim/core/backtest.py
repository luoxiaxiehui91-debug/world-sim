"""
backtest.py — P4-C
历史场景回测：用 grv_history.jsonl 快照跑 Monte Carlo，
对比已知实际结果，校准 SENTIMENT_TO_GRV_FORECAST 映射。
"""

import json
import copy
from pathlib import Path

from core.world_state import load_from_snapshot, SENTIMENT_TO_GRV_FORECAST
from core.sim_log import insert_run, mark_verified


# ── 历史场景定义（已知事实，用于校准）────────────────────────
# actual_grv_change: T0 后 verify_in_days 天内 GRV 实际变化量（正=上升）
# 数据来源：GRV 历史均值估算（COVID 高峰期 global_composite 约+25，俄乌约+20）
HISTORICAL_SCENARIOS = [
    {
        "label":            "covid_2020_03",
        "trigger_date":     "2020-03-01",
        "trigger_event":    "COVID-19 全球疫情爆发，WHO 宣布大流行",
        "situation_level":  4,
        "grv_snapshot": {
            "global_composite":   72.0,
            "middle_east_energy": 45.0,
            "taiwan_strait":      30.0,
            "russia_europe":      25.0,
            "us_china_strategic": 55.0,
        },
        # 30天后实际：GRV 从 72 升至约 85（供应链断裂+金融市场恐慌）
        "actual_grv_change": +13.0,
        "verify_in_days":    30,
    },
    {
        "label":            "ukraine_2022_02",
        "trigger_date":     "2022-02-24",
        "trigger_event":    "俄罗斯全面入侵乌克兰，欧洲能源危机触发",
        "situation_level":  4,
        "grv_snapshot": {
            "global_composite":   78.0,
            "middle_east_energy": 60.0,
            "taiwan_strait":      35.0,
            "russia_europe":      85.0,
            "us_china_strategic": 50.0,
        },
        # 21天后实际：GRV 从 78 升至约 88（能源冲击+军事升级）
        "actual_grv_change": +10.0,
        "verify_in_days":    21,
    },
    {
        "label":            "svb_2023_03",
        "trigger_date":     "2023-03-10",
        "trigger_event":    "硅谷银行倒闭，美国银行业危机蔓延",
        "situation_level":  3,
        "grv_snapshot": {
            "global_composite":   58.0,
            "middle_east_energy": 50.0,
            "taiwan_strait":      40.0,
            "russia_europe":      65.0,
            "us_china_strategic": 52.0,
        },
        # 21天后实际：GRV 小幅回落（危机被快速遏制，约-3）
        "actual_grv_change": -3.0,
        "verify_in_days":    21,
    },
]


def run_backtest(
    n_runs: int = 100,
    grv_history_path: str = None,
    db_path: Path = None,
    skip_ntfy: bool = True,
) -> list[dict]:
    """
    对所有历史场景跑 Monte Carlo，写入 sim_log，填入实际结果，打印校准报告。
    grv_history_path: 可选，覆盖快照来源（传入则从 jsonl 里按日期找快照）
    """
    from run import run_monte_carlo

    results = []

    for scenario in HISTORICAL_SCENARIOS:
        label    = scenario["label"]
        snapshot = scenario["grv_snapshot"]

        # 若提供了 grv_history.jsonl，尝试从中找更精确的快照
        if grv_history_path:
            hist_snapshot = _find_snapshot_by_date(
                grv_history_path, scenario["trigger_date"]
            )
            if hist_snapshot:
                snapshot = hist_snapshot
                print(f"[{label}] 使用 grv_history.jsonl 快照（{scenario['trigger_date']}）")
            else:
                print(f"[{label}] jsonl 中未找到对应日期，使用内置快照")

        world = load_from_snapshot(
            snapshot,
            label=label,
            situation_level=scenario["situation_level"],
            trigger_event=scenario["trigger_event"],
            trigger_date=scenario["trigger_date"],
        )

        print(f"\n{'='*60}")
        print(f"场景：{label}")
        print(f"触发：{scenario['trigger_event']}")
        print(f"GRV={world.grv:.1f}  VIX={world.vix:.1f}  L{world.situation_level}")

        mc_result = run_monte_carlo(
            n_runs=n_runs,
            sentiment_init=0.0,
            use_llm=False,
            initial_world=copy.deepcopy(world),
        )

        # mark_verified：填入已知实际结果
        try:
            mark_verified(label, scenario["actual_grv_change"], db_path=db_path)
            print(f"已校准：实际 GRV 变化 = {scenario['actual_grv_change']:+.1f}")
        except Exception as e:
            print(f"[警告] mark_verified 失败：{e}")

        # 判读预测准确性
        accuracy = _evaluate_accuracy(mc_result, scenario)

        results.append({
            "label":             label,
            "mc_result":         mc_result,
            "actual_grv_change": scenario["actual_grv_change"],
            "accuracy":          accuracy,
        })

    _print_calibration_report(results)
    return results


def _find_snapshot_by_date(jsonl_path: str, target_date: str) -> dict | None:
    """在 grv_history.jsonl 里找最接近 target_date 的快照。"""
    try:
        with open(jsonl_path) as f:
            lines = f.readlines()
        target = target_date[:10]
        best = None
        for line in lines:
            try:
                obj = json.loads(line)
                ts = (obj.get("updated") or obj.get("gdelt_updated") or "")[:10]
                if ts <= target:
                    best = obj
            except Exception:
                continue
        return best
    except Exception:
        return None


def _evaluate_accuracy(mc_result: dict, scenario: dict) -> str:
    """
    对比仿真预测方向和实际 GRV 变化方向，返回 'correct' / 'wrong' / 'neutral'。
    """
    actual = scenario["actual_grv_change"]
    mean_s = mc_result["sentiment_mean"]

    # 从 SENTIMENT_TO_GRV_FORECAST 查预测方向
    predicted_direction = None
    for (lo, hi), (_, direction, _) in SENTIMENT_TO_GRV_FORECAST.items():
        if lo <= mean_s < hi:
            predicted_direction = direction
            break

    if predicted_direction is None:
        return "out_of_range"

    if predicted_direction in ("grv_up_strong", "grv_up_moderate", "grv_up_mild"):
        predicted_up = True
    elif predicted_direction == "grv_stable":
        predicted_up = False
    else:  # no_change
        return "neutral"

    actual_up = actual > 1.0   # >1 才算明显上升

    if predicted_up == actual_up:
        return "correct"
    return "wrong"


def _print_calibration_report(results: list[dict]):
    """打印校准汇总报告，标注 SENTIMENT_TO_GRV_FORECAST 映射准确率。"""
    print(f"\n{'='*60}")
    print("P4-C 历史场景回测校准报告")
    print(f"{'='*60}")
    print(f"{'场景':<22} {'情绪均值':>8} {'预测方向':<20} {'实际GRV变化':>10} {'准确性':>8}")
    print("-" * 70)

    correct = wrong = neutral = 0
    for r in results:
        mc   = r["mc_result"]
        mean = mc["sentiment_mean"]
        actual = r["actual_grv_change"]
        acc  = r["accuracy"]

        # 查预测方向标签
        direction = "N/A"
        for (lo, hi), (_, d, _) in SENTIMENT_TO_GRV_FORECAST.items():
            if lo <= mean < hi:
                direction = d
                break

        acc_icon = {"correct": "✅", "wrong": "❌", "neutral": "➖", "out_of_range": "⚠️"}.get(acc, "?")
        print(f"{r['label']:<22} {mean:>+8.3f} {direction:<20} {actual:>+10.1f} {acc_icon} {acc}")

        if acc == "correct":   correct += 1
        elif acc == "wrong":   wrong += 1
        else:                  neutral += 1

    total = correct + wrong
    print(f"\n方向准确率：{correct}/{total} = {correct/total:.0%}" if total else "\n无有效对比")
    print()

    # 校准建议
    if wrong > 0:
        print("⚠️  校准建议：以下映射区间方向预测有误，考虑调整 SENTIMENT_TO_GRV_FORECAST：")
        for r in results:
            if r["accuracy"] == "wrong":
                mean = r["mc_result"]["sentiment_mean"]
                print(f"   {r['label']}：sentiment_mean={mean:+.3f}，"
                      f"实际GRV变化={r['actual_grv_change']:+.1f}")
    else:
        print("✅ 所有场景方向预测正确，SENTIMENT_TO_GRV_FORECAST 映射暂无需调整。")
