"""
tianji_verifier.py — 天玑 V1 月度验证运行器

每月1日由 scheduler.py 调用。
功能：
  1. 取所有 due_at <= 今天 且 status=pending 的预测
  2. 量化预测：自动拉 FRED/GRV 历史数据，计算 Brier Score
  3. 地缘预测：推送 ntfy 请求人工确认
  4. 计算 Brier Skill Score（BSS）和锐度
  5. 触发反哺检查：连续N条同类信源+同类目标 Brier 差 → 生成待审批建议

用法：
  python tianji_verifier.py          # 月度验证
  python tianji_verifier.py --report # 打印当前准确率报告
  python tianji_verifier.py --status # 打印待验证数量
"""

import os
import sys
import json
import math
import argparse
from datetime import datetime, date
from typing import Optional

try:
    from optim_config import DATA_DIR, WORKSPACE, FRED_API_KEY
except ImportError:
    WORKSPACE    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR     = os.path.join(WORKSPACE, "data")
    FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

from tianji_db import (
    get_connection, get_pending_predictions,
    update_prediction_verified, log_weight_update,
)

NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh/***REMOVED***")
GRV_HISTORY_PATH = os.path.join(DATA_DIR, "grv_history.jsonl")

# 触发反哺的最小样本量
MIN_TRIGGER_N = 8


# ── FRED 数据拉取 ─────────────────────────────────────────────────────────────

def _fetch_fred_value(series_id: str, as_of_date: str) -> Optional[float]:
    """
    从本地 FRED CSV 取 as_of_date 时的值（最近可用值）。
    as_of_date: YYYY-MM-DD
    """
    path = os.path.join(DATA_DIR, "fred_history", f"{series_id}.csv")
    if not os.path.exists(path):
        return None
    try:
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("DATE") or line.startswith("#"):
                    continue
                parts = line.split(",")
                if len(parts) >= 2:
                    try:
                        rows.append((parts[0].strip(), float(parts[1].strip())))
                    except ValueError:
                        continue
        # 找 as_of_date 之前最近的值
        candidates = [(dt, v) for dt, v in rows if dt <= as_of_date and not math.isnan(v)]
        if candidates:
            return candidates[-1][1]
    except Exception:
        pass
    return None


def _fetch_grv_value(dimension: str, as_of_date: str) -> Optional[float]:
    """从 grv_history.jsonl 取指定维度在 as_of_date 时的值。"""
    if not os.path.exists(GRV_HISTORY_PATH):
        return None
    try:
        candidates = []
        with open(GRV_HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    dt = entry.get("date", entry.get("updated", ""))[:10]
                    if dt <= as_of_date:
                        val = entry.get(dimension)
                        if val is not None:
                            candidates.append((dt, float(val)))
                except Exception:
                    continue
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[-1][1]
    except Exception:
        pass
    return None


# ── Brier Score 计算 ──────────────────────────────────────────────────────────

def _compute_brier_score(predicted_prob: float, outcome: float) -> float:
    """
    Brier Score = (prob - outcome)^2
    outcome: 1.0 = 事件发生，0.0 = 事件未发生
    对于量化预测（连续值），先转换为二值：实际方向是否符合预测。
    """
    return round((predicted_prob - outcome) ** 2, 6)


def _compute_bss(brier_scores: list[float]) -> Optional[float]:
    """
    Brier Skill Score = 1 - BS / BS_climatology
    BS_climatology = 平均 Brier Score（用历史基准频率0.5计算）
    BSS > 0 表示有增量价值。
    """
    if len(brier_scores) < 5:
        return None
    bs_mean = sum(brier_scores) / len(brier_scores)
    # 气候基准：所有预测都说 0.5
    bs_clim = 0.25
    if bs_clim == 0:
        return None
    return round(1.0 - bs_mean / bs_clim, 4)


def _compute_sharpness(final_probs: list[float]) -> float:
    """
    锐度：预测落在 (30%, 70%) 以外的比例。目标 > 40%。
    """
    if not final_probs:
        return 0.0
    sharp_count = sum(1 for p in final_probs if p < 0.3 or p > 0.7)
    return round(sharp_count / len(final_probs), 4)


# ── 量化预测验证 ──────────────────────────────────────────────────────────────

def verify_quantitative(pred: dict) -> Optional[dict]:
    """
    自动验证量化预测。
    pred 需要有 target_metric, target_direction, target_threshold, final_prob, due_at。
    返回 {outcome_value, brier_score} 或 None（数据不可用）。
    """
    metric    = pred.get("target_metric", "")
    direction = pred.get("target_direction", "")
    threshold = pred.get("target_threshold")
    prob      = pred.get("final_prob", 0.5)
    due_at    = pred.get("due_at", "")[:10]

    # 从 FRED 或 GRV 取实际值
    actual_val = None

    # GRV 维度
    grv_dims = [
        "taiwan_strait", "us_china_strategic", "russia_europe",
        "middle_east_energy", "global_composite", "climate_risk",
        "disaster_risk", "sanctions_risk", "seismic_risk",
        "energy_grid_risk", "japan_monetary",
    ]
    if metric in grv_dims:
        actual_val = _fetch_grv_value(metric, due_at)
    elif metric:
        actual_val = _fetch_fred_value(metric, due_at)

    if actual_val is None:
        return None

    # 将实际值转为二值 outcome
    outcome = 0.0
    if direction == "up" and threshold is not None:
        outcome = 1.0 if actual_val > threshold else 0.0
    elif direction == "down" and threshold is not None:
        outcome = 1.0 if actual_val < threshold else 0.0
    elif direction == "above" and threshold is not None:
        outcome = 1.0 if actual_val >= threshold else 0.0
    elif direction == "below" and threshold is not None:
        outcome = 1.0 if actual_val <= threshold else 0.0
    else:
        # 无阈值：方向性预测（与起始值比较）
        outcome = 0.5  # 无法判断

    brier = _compute_brier_score(prob, outcome)
    return {"outcome_value": actual_val, "brier_score": brier}


# ── ntfy 推送地缘预测确认请求 ─────────────────────────────────────────────────

def _push_geopolitical_verify_request(pred: dict):
    """向 ntfy 推送人工确认请求。"""
    try:
        import urllib.request
        msg = (
            f"🔮 天玑验证请求\n"
            f"预测：{pred.get('content', '')[:100]}\n"
            f"概率：{pred.get('final_prob', 0):.0%}\n"
            f"到期：{pred.get('due_at', '')[:10]}\n"
            f"验证ID：{pred.get('id', '')}\n"
            f"请回复 'verify {pred.get('id', '')} 1' (发生) 或 'verify {pred.get('id', '')} 0' (未发生)"
        )
        req = urllib.request.Request(
            NTFY_URL,
            data=msg.encode("utf-8"),
            headers={
                "Title": "天玑人工验证请求",
                "Priority": "default",
                "Tags": "crystal_ball",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[tianji_verifier] ntfy 推送失败: {e}")


# ── 反哺检查 ──────────────────────────────────────────────────────────────────

def check_and_generate_reweight_suggestions():
    """
    检查是否有信源应该触发降权建议。
    触发条件：连续 N=8 条同信源+同预测目标类型，Brier 均值 < 全体均值 × 80%。
    """
    conn = get_connection()
    try:
        # 取所有已验证预测（有 brier_score）
        rows = conn.execute("""
            SELECT p.id, p.prediction_target_type, p.brier_score, p.final_prob,
                   r.agent_id, r.input_signals
            FROM predictions p
            LEFT JOIN reasoning_trace r ON r.prediction_id = p.id
            WHERE p.status = 'verified' AND p.brier_score IS NOT NULL
            ORDER BY p.verified_at DESC
        """).fetchall()
    finally:
        conn.close()

    if len(rows) < MIN_TRIGGER_N:
        return []

    # 按 (signal_source, target_type) 分组
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for row in rows:
        signals = []
        try:
            signals = json.loads(row["input_signals"] or "[]")
        except Exception:
            pass
        target_type = row["prediction_target_type"] or "unknown"
        for sig in signals:
            src = sig.get("signal_name", sig.get("source", ""))
            if src:
                groups[(src, target_type)].append(row["brier_score"])

    # 全体平均 Brier
    all_briers = [row["brier_score"] for row in rows if row["brier_score"] is not None]
    global_mean = sum(all_briers) / len(all_briers) if all_briers else 0.25

    suggestions = []
    for (src, tgt), briers in groups.items():
        if len(briers) < MIN_TRIGGER_N:
            continue
        group_mean = sum(briers[-MIN_TRIGGER_N:]) / MIN_TRIGGER_N
        if group_mean > global_mean * 0.8:  # 差于全体均值 80%
            continue
        # 读取当前权重
        current_weight = _read_current_weight(src, tgt)
        suggestions.append({
            "signal_name":    src,
            "target_type":    tgt,
            "sample_count":   len(briers),
            "group_brier":    round(group_mean, 4),
            "global_brier":   round(global_mean, 4),
            "ratio":          round(group_mean / global_mean, 3) if global_mean > 0 else 1.0,
            "weight_before":  current_weight,
            "weight_after":   round(max(0.05, current_weight * 0.85), 4),
            "reason":         f"连续{MIN_TRIGGER_N}条 Brier={group_mean:.3f}，差于全体均值({global_mean:.3f})的80%",
        })

    if suggestions:
        # 写入待审批文件
        pending_path = os.path.join(DATA_DIR, "pending_weight_adjustments.json")
        existing = []
        if os.path.exists(pending_path):
            try:
                with open(pending_path, encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

        # 去重：同 signal+target 只保留最新
        existing_keys = {(s["signal_name"], s["target_type"]) for s in existing}
        new_entries = [s for s in suggestions
                       if (s["signal_name"], s["target_type"]) not in existing_keys]

        if new_entries:
            existing.extend(new_entries)
            with open(pending_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            print(f"[tianji_verifier] 生成 {len(new_entries)} 条待审批降权建议 → {pending_path}")

            # 推送 ntfy
            try:
                import urllib.request
                msg = f"🎯 玉衡：{len(new_entries)} 条权重调整建议待审批\n"
                for s in new_entries[:3]:
                    msg += f"  {s['signal_name']} → {s['target_type']}: {s['weight_before']:.3f}→{s['weight_after']:.3f}\n"
                req = urllib.request.Request(
                    NTFY_URL,
                    data=msg.encode("utf-8"),
                    headers={"Title": "玉衡权重调整建议", "Tags": "scales"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass

    return suggestions


def _read_current_weight(signal_name: str, target_type: str) -> float:
    """从 grv_weights.yaml 读取当前权重，不存在时返回默认值。"""
    weights_path = os.path.join(WORKSPACE, "config", "grv_weights.yaml")
    if not os.path.exists(weights_path):
        return 0.20
    try:
        import yaml
        with open(weights_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        weights = data.get("weights", {})
        source_weights = weights.get(signal_name, {})
        return float(source_weights.get(target_type, 0.20))
    except Exception:
        return 0.20


# ── 准确率报告 ────────────────────────────────────────────────────────────────

def print_accuracy_report():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT status, COUNT(*) as cnt FROM predictions GROUP BY status
        """).fetchall()
        status_counts = {r["status"]: r["cnt"] for r in rows}

        verified = conn.execute("""
            SELECT brier_score, final_prob FROM predictions
            WHERE status='verified' AND brier_score IS NOT NULL
        """).fetchall()
    finally:
        conn.close()

    total = sum(status_counts.values())
    v_count = status_counts.get("verified", 0)

    print("\n" + "="*50)
    print("天玑 — 预测准确率报告")
    print("="*50)
    print(f"总预测数：{total}")
    print(f"  待验证：{status_counts.get('pending', 0)}")
    print(f"  已验证：{v_count}")
    print(f"  人工确认中：{status_counts.get('awaiting_human', 0)}")

    if v_count < 5:
        print(f"\n已验证样本 < 5，统计指标尚无意义（需 ≥ 20 条才计算 BSS）")
        return

    briers = [r["brier_score"] for r in verified]
    probs  = [r["final_prob"] for r in verified]
    bs_mean = sum(briers) / len(briers)
    bss = _compute_bss(briers)
    sharpness = _compute_sharpness(probs)

    print(f"\nBrier Score 均值：{bs_mean:.4f}（越低越好，随机猜=0.25）")
    if bss is not None:
        bss_str = f"{bss:+.4f}"
        trend = "✅ 有增量价值" if bss > 0 else "❌ 不如随机猜"
        print(f"Brier Skill Score：{bss_str} {trend}")
    else:
        print(f"Brier Skill Score：样本不足（需 ≥ 5）")
    print(f"锐度（>30%或<70%比例）：{sharpness:.1%}（目标 >40%）")
    print("="*50)


# ── 月度验证主流程 ────────────────────────────────────────────────────────────

def run_monthly_verification():
    print(f"\n[tianji_verifier] 月度验证开始 {datetime.utcnow().isoformat()[:10]}")

    pending = get_pending_predictions()
    print(f"[tianji_verifier] 找到 {len(pending)} 条待验证预测")

    auto_verified = 0
    human_requested = 0
    skipped = 0

    for pred in pending:
        pred_type = pred.get("type", "")

        if pred_type == "quantitative":
            result = verify_quantitative(pred)
            if result:
                update_prediction_verified(
                    prediction_id=pred["id"],
                    outcome_value=result["outcome_value"],
                    brier_score=result["brier_score"],
                    verified_by="auto",
                )
                auto_verified += 1
            else:
                skipped += 1

        elif pred_type == "geopolitical":
            # 更新状态为等待人工确认
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE predictions SET status='awaiting_human' WHERE id=?",
                    (pred["id"],)
                )
                conn.commit()
            finally:
                conn.close()
            _push_geopolitical_verify_request(pred)
            human_requested += 1

    print(f"[tianji_verifier] 自动验证={auto_verified}，人工确认请求={human_requested}，跳过={skipped}")

    # 反哺检查
    suggestions = check_and_generate_reweight_suggestions()
    if suggestions:
        print(f"[tianji_verifier] 生成 {len(suggestions)} 条权重调整建议")

    # 打印简要报告
    print_accuracy_report()
    print(f"[tianji_verifier] 月度验证完成")


# ── 人工确认接口 ──────────────────────────────────────────────────────────────

def confirm_geopolitical(prediction_id: str, occurred: bool):
    """
    维护者收到 ntfy 通知后调用，确认地缘事件是否发生。
    occurred: True = 发生了，False = 未发生
    """
    outcome = 1.0 if occurred else 0.0
    conn = get_connection()
    try:
        pred = conn.execute(
            "SELECT final_prob FROM predictions WHERE id=?", (prediction_id,)
        ).fetchone()
    finally:
        conn.close()

    if not pred:
        print(f"[tianji_verifier] 预测 {prediction_id} 不存在")
        return

    brier = _compute_brier_score(pred["final_prob"], outcome)
    update_prediction_verified(
        prediction_id=prediction_id,
        outcome_value=outcome,
        brier_score=brier,
        verified_by="human",
    )
    print(f"[tianji_verifier] 地缘预测 {prediction_id} 已确认 "
          f"({'发生' if occurred else '未发生'})，Brier={brier:.4f}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="打印准确率报告")
    parser.add_argument("--status", action="store_true", help="打印待验证数量")
    parser.add_argument("--confirm", nargs=2, metavar=("PRED_ID", "0_or_1"),
                        help="人工确认地缘预测")
    args = parser.parse_args()

    if args.report:
        print_accuracy_report()
    elif args.status:
        pending = get_pending_predictions()
        print(f"待验证预测：{len(pending)} 条")
    elif args.confirm:
        pred_id, result = args.confirm
        confirm_geopolitical(pred_id, result == "1")
    else:
        run_monthly_verification()
