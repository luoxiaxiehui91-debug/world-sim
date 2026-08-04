"""
weight_matrix.py — 权重矩阵基础设施

管理 config/grv_weights.yaml：
  - 从 prior.yaml 初始化权重矩阵
  - 读取当前权重（天枢/天璇用）
  - 玉衡审批后写回（带双层 clip 约束）
  - 月度健康检查（Herfindahl + 覆盖度）
"""

import os
import json
import math
from datetime import datetime
from typing import Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR  = os.path.join(WORKSPACE, "data")

CONFIG_DIR      = os.path.join(WORKSPACE, "config")
WEIGHTS_PATH    = os.path.join(CONFIG_DIR, "grv_weights.yaml")
PRIOR_PATH      = os.path.join(CONFIG_DIR, "prior.yaml")
PENDING_PATH    = os.path.join(DATA_DIR, "pending_weight_adjustments.json")

# 双层 clip 约束（代码层强制执行）
WEIGHT_MIN      = 0.05
WEIGHT_MAX      = 5.0
MAX_CHANGE_RATE = 0.25   # 单次调整不超过当前值的 ±25%

# 月度健康检查阈值
MIN_EFFECTIVE_SOURCES = 2   # 每个预测目标至少有效信源数
HERFINDAHL_WARN_RATIO = 3.0 # 集中度超过初始基线3倍触发警告
MIN_PARTICIPATION_RATE = 0.3 # 有效信源占总信源比例 < 30% 触发警告
EFFECTIVE_WEIGHT_THRESHOLD = 0.1  # 权重 > 0.1 算有效信源

NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh/macro-tsx-9005")


def _load_yaml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        if HAS_YAML:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        else:
            # 简单 fallback：只支持基本格式
            return {}
    except Exception as e:
        print(f"[weight_matrix] YAML 读取失败 {path}: {e}")
        return {}


def _save_yaml(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if HAS_YAML:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=True)
    else:
        # fallback：存 JSON
        json_path = path.replace(".yaml", ".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ── 初始化：从 prior.yaml 创建 grv_weights.yaml ──────────────────────────────

def init_weights_from_prior():
    """
    首次运行时从 prior.yaml 初始化 grv_weights.yaml。
    prior.yaml 中存的是 {weights: {source_id: {target_type: weight, ...}, ...}}。
    """
    if os.path.exists(WEIGHTS_PATH):
        print(f"[weight_matrix] grv_weights.yaml 已存在，跳过初始化")
        return

    prior = _load_yaml(PRIOR_PATH)
    weights_section = prior.get("weights", {})

    if not weights_section:
        print(f"[weight_matrix] prior.yaml 为空或不存在，创建空权重矩阵")
        weights_section = {}

    data = {
        "version":      1,
        "initialized_at": datetime.utcnow().isoformat()[:10],
        "weights":      weights_section,
        # 初始基线快照（用于健康检查 Herfindahl 基准）
        "baseline_snapshot": _compute_herfindahl_per_target(weights_section),
    }
    _save_yaml(WEIGHTS_PATH, data)
    print(f"[weight_matrix] 权重矩阵初始化完成 → {WEIGHTS_PATH}")
    print(f"  信源数：{len(weights_section)}")


# ── 读取权重 ──────────────────────────────────────────────────────────────────

def get_weight(source_id: str, target_type: str) -> float:
    """读取单个权重值，不存在时返回 0.10 默认值。"""
    data = _load_yaml(WEIGHTS_PATH)
    weights = data.get("weights", {})
    source_weights = weights.get(source_id, {})
    return float(source_weights.get(target_type, 0.10))


def get_all_weights() -> dict:
    """返回完整权重字典 {source_id: {target_type: weight}}。"""
    data = _load_yaml(WEIGHTS_PATH)
    return data.get("weights", {})


def get_weights_for_target(target_type: str) -> dict:
    """返回指定预测目标类型的所有信源权重 {source_id: weight}。"""
    all_weights = get_all_weights()
    result = {}
    for src, tgt_weights in all_weights.items():
        w = tgt_weights.get(target_type)
        if w is not None:
            result[src] = float(w)
    return result


# ── 玉衡写回（带约束） ────────────────────────────────────────────────────────

def apply_weight_adjustment(
    source_id: str,
    target_type: str,
    new_weight: float,
    reason: str = "玉衡审批",
    prediction_id: str = None,
    notes: str = None,
) -> dict:
    """
    玉衡审批后调用，写回权重。
    双层 clip 约束自动应用。
    返回 {status, weight_before, weight_after, clipped}。
    """
    data = _load_yaml(WEIGHTS_PATH)
    weights = data.get("weights", {})

    current = float(weights.get(source_id, {}).get(target_type, 0.10))

    # 层1：变化速率约束 ±25%
    max_change = current * MAX_CHANGE_RATE
    clipped_by_rate = abs(new_weight - current) > max_change
    if clipped_by_rate:
        if new_weight > current:
            new_weight = current + max_change
        else:
            new_weight = current - max_change

    # 层2：绝对值范围
    clipped_by_range = new_weight < WEIGHT_MIN or new_weight > WEIGHT_MAX
    new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, new_weight))

    clipped = clipped_by_rate or clipped_by_range

    # 写入
    if source_id not in weights:
        weights[source_id] = {}
    weights[source_id][target_type] = round(new_weight, 5)
    data["weights"] = weights
    data["last_updated"] = datetime.utcnow().isoformat()
    _save_yaml(WEIGHTS_PATH, data)

    # 记录日志
    try:
        from tianji_db import log_weight_update
        log_weight_update({
            "prediction_id": prediction_id,
            "signal_name":   source_id,
            "target_type":   target_type,
            "weight_before": current,
            "weight_after":  new_weight,
            "reason":        reason,
            "notes":         notes,
        })
    except Exception:
        pass

    # 检查连续方向（连续4次同方向警告）
    _check_consecutive_direction(source_id, target_type, new_weight > current)

    return {
        "status":       "ok",
        "weight_before": round(current, 5),
        "weight_after":  round(new_weight, 5),
        "clipped":       clipped,
    }


def _check_consecutive_direction(source_id: str, target_type: str, is_increase: bool):
    """连续4次同方向时输出警告（不阻止操作）。"""
    try:
        from tianji_db import get_connection
        conn = get_connection()
        rows = conn.execute("""
            SELECT weight_before, weight_after FROM weight_update_log
            WHERE signal_name=? AND target_type=?
            ORDER BY updated_at DESC LIMIT 4
        """, (source_id, target_type)).fetchall()
        conn.close()

        if len(rows) < 4:
            return
        directions = [r["weight_after"] > r["weight_before"] for r in rows]
        if all(d == is_increase for d in directions):
            direction_str = "上调" if is_increase else "下调"
            print(f"[weight_matrix] ⚠️ 警告：{source_id}/{target_type} 已连续4次{direction_str}，"
                  f"建议填写备注说明原因")
    except Exception:
        pass


# ── 月度健康检查 ──────────────────────────────────────────────────────────────

def _compute_herfindahl_per_target(weights: dict) -> dict:
    """计算每个预测目标类型的 Herfindahl 集中度指数。"""
    target_sums: dict = {}
    target_sq_sums: dict = {}

    for src, tgt_weights in weights.items():
        if not isinstance(tgt_weights, dict):
            continue
        for tgt, w in tgt_weights.items():
            w = float(w)
            target_sums[tgt] = target_sums.get(tgt, 0.0) + w
            target_sq_sums[tgt] = target_sq_sums.get(tgt, 0.0) + w * w

    result = {}
    for tgt, sq_sum in target_sq_sums.items():
        total = target_sums.get(tgt, 1.0)
        if total > 0:
            result[tgt] = round(sq_sum / (total * total), 4)
    return result


def run_health_check() -> dict:
    """
    月度权重矩阵健康检查。
    返回 {warnings: [...], level: 'ok'/'warn'/'critical'}。
    """
    data = _load_yaml(WEIGHTS_PATH)
    weights = data.get("weights", {})
    baseline = data.get("baseline_snapshot", {})

    if not weights:
        return {"warnings": ["权重矩阵为空"], "level": "critical"}

    all_targets = set()
    for tgt_weights in weights.values():
        if isinstance(tgt_weights, dict):
            all_targets.update(tgt_weights.keys())

    total_sources = len(weights)
    warnings = []

    # 指标A：每个预测目标有效信源数
    for tgt in all_targets:
        effective = sum(
            1 for src, tgt_w in weights.items()
            if isinstance(tgt_w, dict) and float(tgt_w.get(tgt, 0)) > EFFECTIVE_WEIGHT_THRESHOLD
        )
        if effective < MIN_EFFECTIVE_SOURCES:
            warnings.append(f"[孤立目标] {tgt} 有效信源数={effective}，低于最低要求{MIN_EFFECTIVE_SOURCES}")

    # 指标B：Herfindahl 集中度
    current_herf = _compute_herfindahl_per_target(weights)
    for tgt, herf in current_herf.items():
        base = baseline.get(tgt, herf)
        if base > 0 and herf / base > HERFINDAHL_WARN_RATIO:
            warnings.append(f"[过度集中] {tgt} 集中度={herf:.3f}，超过初始基线({base:.3f})的{HERFINDAHL_WARN_RATIO}倍")

    # 指标C：全局信源参与度
    effective_sources = 0
    for src, tgt_weights in weights.items():
        if not isinstance(tgt_weights, dict):
            continue
        if any(float(w) > EFFECTIVE_WEIGHT_THRESHOLD for w in tgt_weights.values()):
            effective_sources += 1
    participation = effective_sources / total_sources if total_sources > 0 else 0.0
    if participation < MIN_PARTICIPATION_RATE:
        warnings.append(f"[信源萎缩] 有效信源占比={participation:.1%}，低于{MIN_PARTICIPATION_RATE:.0%}")

    level = "ok"
    if len(warnings) >= 2:
        level = "critical"
    elif len(warnings) == 1:
        level = "warn"

    result = {
        "checked_at":       datetime.utcnow().isoformat(),
        "total_sources":    total_sources,
        "total_targets":    len(all_targets),
        "effective_sources": effective_sources,
        "participation":    round(participation, 3),
        "warnings":         warnings,
        "level":            level,
    }

    if level != "ok":
        print(f"[weight_matrix] 健康检查 {level.upper()}：{len(warnings)} 个警告")
        for w in warnings:
            print(f"  ⚠️  {w}")
        if level == "critical":
            _push_health_alert(warnings)
    else:
        print(f"[weight_matrix] 健康检查 OK，{total_sources} 个信源，{len(all_targets)} 个预测目标")

    return result


def _push_health_alert(warnings: list[str]):
    try:
        import urllib.request
        msg = f"⚠️ 权重矩阵健康检查异常（{len(warnings)} 项）\n"
        for w in warnings[:5]:
            msg += f"  • {w}\n"
        req = urllib.request.Request(
            NTFY_URL,
            data=msg.encode("utf-8"),
            headers={"Title": "玉衡健康检查警告", "Tags": "warning", "Priority": "high"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ── 待审批列表 ────────────────────────────────────────────────────────────────

def list_pending_adjustments() -> list[dict]:
    if not os.path.exists(PENDING_PATH):
        return []
    try:
        with open(PENDING_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def approve_adjustment(index: int, notes: str = "") -> dict:
    """
    批准第 index 条待审批建议（0-indexed）。
    """
    pending = list_pending_adjustments()
    if index >= len(pending):
        return {"status": "error", "msg": "索引越界"}

    entry = pending[index]
    result = apply_weight_adjustment(
        source_id=entry["signal_name"],
        target_type=entry["target_type"],
        new_weight=entry["weight_after"],
        reason="玉衡审批",
        notes=notes or entry.get("reason"),
    )

    # 移除已批准条目
    pending.pop(index)
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

    print(f"[weight_matrix] 已批准：{entry['signal_name']}/{entry['target_type']} "
          f"{result['weight_before']:.3f}→{result['weight_after']:.3f}")
    return result


def reject_adjustment(index: int, reason: str = ""):
    """拒绝第 index 条待审批建议，记录原因后移除。"""
    pending = list_pending_adjustments()
    if index >= len(pending):
        return
    entry = pending[index]
    # 记录拒绝日志
    try:
        from tianji_db import log_weight_update
        log_weight_update({
            "signal_name":   entry["signal_name"],
            "target_type":   entry["target_type"],
            "weight_before": entry.get("weight_before"),
            "weight_after":  entry.get("weight_before"),  # 不变
            "reason":        f"拒绝：{reason}",
        })
    except Exception:
        pass
    pending.pop(index)
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)
    print(f"[weight_matrix] 已拒绝：{entry['signal_name']}/{entry['target_type']} 原因：{reason}")


if __name__ == "__main__":
    import sys
    if "--init" in sys.argv:
        init_weights_from_prior()
    elif "--health" in sys.argv:
        run_health_check()
    elif "--pending" in sys.argv:
        items = list_pending_adjustments()
        print(f"待审批建议 {len(items)} 条：")
        for i, item in enumerate(items):
            print(f"  [{i}] {item['signal_name']}/{item['target_type']}: "
                  f"{item.get('weight_before',0):.3f}→{item.get('weight_after',0):.3f} ({item.get('reason','')})")
    else:
        print("用法：python weight_matrix.py --init | --health | --pending")
