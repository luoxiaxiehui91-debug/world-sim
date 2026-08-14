# -*- coding: utf-8 -*-
"""
tianji_calibrator.py — 天玑 · GDELT 分数校准器（T2 机制扩展）

职责：读 gdelt_history.jsonl → 计算 GDELT 分数体系校准配置 → 写 gdelt_calib.json。
     天枢消费方（scan_weak_signals.py / geo_risk_vector.py）统一读取该配置，
     替代硬编码的 scale / tone 基准（消除 9 维度归一化整体失准问题，
     见 docs/decisions/gdelt-scores-audit-20260814.md）。

设计：docs/decisions/gdelt-calibrator-design-20260814.md
触发：tianji_verifier.py __main__ 顺带调用 run_calibration()（函数级独立，可拆独立 trigger）
回滚：删除 gdelt_calib.json → 消费方 fallback 硬编码自动生效（零代码回滚）

输出 schema（gdelt_calib.json）：
{
  "generated_at": ISO8601 UTC,
  "sample_count": int,           # 参与计算的 history 记录数
  "min_sample": 100,             # 消费方低于此样本数走 fallback（与 GRV 规则一致）
  "scales": {dim: p95},          # 8 个计数类维度 P95（_norm 用，0 基点物理含义）
  "tone_base": float,            # social_stress 基准线（-7.97，源码注释实测值）
  "hotspot_p95": {hotspot: p95}, # GRV 4 热点组合 P95（mil+sanc 平均）
  "source": "gdelt_history.jsonl",
  "version": 1
}
"""

import json
import os
from datetime import datetime, timezone

TIANJI_DATA_DIR = os.environ.get("TIANJI_DATA_DIR", "/app/macro_data")
HISTORY_PATH = os.path.join(TIANJI_DATA_DIR, "gdelt_history.jsonl")
CALIB_PATH = os.path.join(TIANJI_DATA_DIR, "gdelt_calib.json")

MIN_SAMPLE = 100          # 样本 <100 时消费方 fallback 硬编码（与 GRV 现有规则一致）
DIM_MIN_VALS = 50         # 单维度有效值 <50 时 scale 记 0.01（防零除，消费方偏高见注释）
HOTSPOT_MIN_VALS = 50     # GRV 原逻辑：每热点 <50 个有效值 fallback

# 8 个计数类维度（social_stress 是 tone 派生，不走 _norm，用 tone_base）
DIM_SCALES_KEYS = [
    "military", "tension", "protest", "sanction",
    "coop", "religious_conflict", "regime_change", "cultural_friction",
]

# GRV 热点组合定义（与 geo_risk_vector.py _gdelt_country_score 一致）
HOTSPOT_COUNTRIES = {
    "russia_europe": ["RUS", "DEU", "UKR"],
    "taiwan_strait": ["TWN", "CHN"],
    "us_china":      ["USA", "CHN"],
    "mideast":       ["IRN", "SAU", "ISR"],
}

# GRV 硬编码 fallback（geo_risk_vector.py _GDELT_P95_FALLBACK 同源）
HOTSPOT_FALLBACK = {
    "russia_europe": 1.243,
    "taiwan_strait": 0.620,
    "us_china":      9.790,
    "mideast":       2.533,
}

# 各维度当前硬编码 scale（scan_weak_signals.py 现状值，用于从归一化分数反推原始计数）
# 关键：gdelt_history.jsonl 存的是归一化分数（0-100）而非原始计数，
# 反推原始计数 v_est = score/100 * old_scale，再对 v_est 算 P95 作为新 scale。
SCALE_REF = {
    "military":           135000,
    "tension":            220000,
    "protest":            14000,
    "sanction":           45000,
    "coop":               900000,
    "religious_conflict": 8000,
    "regime_change":      5000,
    "cultural_friction":  200,   # 已修过一次（原 3000 严重高估）
}

# tone 基准：scan_weak_signals.py 注释实测值（"实测约 -7.97"）。
# 限制：gdelt_history.jsonl 只存 >=20 的截断分数，反推 mean_tone 不可靠（截断致中位偏高），
# 故直接用注释实测值；仅当分布异常（截断分数中位 >60）时打日志提示人工核查。
TONE_BASE_REF = -7.97
TONE_MED_WARN = 60.0


def _load_history() -> list:
    records = []
    if not os.path.exists(HISTORY_PATH):
        return records
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    try:
                        records.append(json.loads(ln))
                    except Exception:
                        pass
    except Exception as e:
        print(f"[CALIB] 读取 history 失败: {e}")
    return records


def _percentile(vals: list, q: float = 0.95) -> float:
    if not vals:
        return 0.0
    sv = sorted(vals)
    idx = min(int(len(sv) * q), len(sv) - 1)
    return sv[idx]


def _compute_dim_scales(records: list) -> dict:
    """8 个计数类维度：归一化分数 P95 反推原始计数 P95 = P95(score)*old_scale/100。

    注：history 存的是分数（0-100），直接拿分数 P95 当 scale 会双重归一化（分数/分数P95×100
    把普通值全冲 100）。反推回原始计数量级后再算 P95，语义 = "原始计数 P95 作归一化上限"。
    """
    result = {}
    for dim in DIM_SCALES_KEYS:
        vals = []
        for r in records:
            d = (r.get("scores") or {}).get(dim)
            if isinstance(d, dict):
                vals.extend(float(v) for v in d.values() if v is not None)
        old_scale = SCALE_REF.get(dim, 100.0)
        p95_score = _percentile(vals) if len(vals) >= DIM_MIN_VALS else 0.0
        # 反推原始计数 P95：score = v/old_scale*100 → v_p95 = p95_score/100*old_scale
        raw_p95 = p95_score * old_scale / 100.0
        result[dim] = round(max(raw_p95, 0.01), 4)
    return result


def _compute_tone_base(records: list) -> float:
    """social_stress 基准线：直接用源码注释实测值 -7.97（截断分数反推不可靠，见模块注释）。"""
    base = TONE_BASE_REF
    scores = []
    for r in records:
        d = (r.get("scores") or {}).get("social_stress")
        if isinstance(d, dict):
            scores.extend(float(v) for v in d.values() if v is not None)
    if len(scores) >= DIM_MIN_VALS:
        med = _percentile(scores, 0.5)
        if med > TONE_MED_WARN:
            print(f"[CALIB] 警告: social_stress 截断分数中位 {med:.1f} 异常高（>{TONE_MED_WARN}），"
                  f"tone_base 维持 {base}，建议人工核查分数体系")
    return round(base, 4)


def _compute_hotspot_p95(records: list) -> dict:
    """GRV 4 热点组合 P95（mil+sanc 平均；逻辑与 geo_risk_vector 原实现一致）。"""
    result = {}
    for key, countries in HOTSPOT_COUNTRIES.items():
        vals = []
        for r in records:
            scores = r.get("scores", {})
            row_vals = []
            for c in countries:
                mil = float((scores.get("military") or {}).get(c) or 0)
                sanc = float((scores.get("sanction") or {}).get(c) or 0)
                row_vals.append((mil + sanc) / 2)
            if row_vals:
                vals.append(sum(row_vals) / len(row_vals))
        if len(vals) >= HOTSPOT_MIN_VALS:
            result[key] = round(max(_percentile(vals), 0.01), 3)
        else:
            result[key] = HOTSPOT_FALLBACK.get(key, 1.0)
    return result


def run_calibration() -> dict:
    """入口：跑全部计算并原子写 gdelt_calib.json。返回配置 dict（失败/无样本返回 {}）。"""
    records = _load_history()
    if not records:
        print("[CALIB] history 无记录，跳过（消费方 fallback 硬编码）")
        return {}
    calib = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample_count": len(records),
        "min_sample": MIN_SAMPLE,
        "scales": _compute_dim_scales(records),
        "tone_base": _compute_tone_base(records),
        "hotspot_p95": _compute_hotspot_p95(records),
        "source": os.path.basename(HISTORY_PATH),
        "version": 1,
    }
    try:
        tmp = CALIB_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(calib, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CALIB_PATH)  # 原子写（目录挂载内安全），消费方不会读到半成品
        print(f"[CALIB] 校准配置已写 {CALIB_PATH}（{len(records)} 条样本）")
        return calib
    except Exception as e:
        print(f"[CALIB] 写配置失败: {e}")
        return {}


if __name__ == "__main__":
    run_calibration()
