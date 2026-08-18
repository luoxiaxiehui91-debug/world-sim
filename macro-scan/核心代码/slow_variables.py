"""
slow_variables.py — 慢变量计算模块

三个慢变量：
  IRP  (Inflation Regime Probability) — 通胀体制概率 P(高通胀) [0,1]
  UCRI (US-China Rivalry Index)       — 中美博弈强度 [0,1]  （部分数据待新fetcher，当前用可用分量）
  GCI  (Geopolitical Configuration Index) — 地缘格局指数 [0,1]

全程连续分数，离散标签仅用于显示。
月频更新，写入 data/slow_variables.json。

依赖：
  - FRED 历史 CSV (fetch_fred_history.py 输出)
  - GRV 当前值 (grv_latest.json)
  - GDELT 事件数据 (gdelt_history.jsonl)
  - sklearn (IRP 逻辑回归)
"""

import os
import json
import math
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Optional

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR  = os.path.join(WORKSPACE, "data")

SLOW_VAR_PATH = os.path.join(DATA_DIR, "slow_variables.json")
FRED_HIST_DIR = os.path.join(DATA_DIR, "fred_history")

_WEIGHTS_YAML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "grv_weights.yaml",
)


def _load_slow_weights() -> dict:
    """从 grv_weights.yaml 读取 slow_variables_weights 节。缺失则返回硬编码默认值（向后兼容）。"""
    defaults = {
        "ucri": {"diplomatic_confrontation": 0.20, "trade_tension": 0.20,
                 "tech_control": 0.20, "tariff_rate": 0.20, "bis_entity_list": 0.20},
        "gci":  {"great_power_confrontation": 0.40, "nuclear_posture": 0.35,
                 "multilateral_lack": 0.25},
    }
    try:
        import yaml
        with open(_WEIGHTS_YAML, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        sv = cfg.get("slow_variables_weights", {})
        if sv:
            return sv
    except Exception as e:
        print(f"[slow_variables] 权重 YAML 读取失败，使用默认值: {e}")
    return defaults


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _load_fred_series(series_id: str) -> list[tuple[str, float]]:
    """加载 FRED CSV，返回 [(date_str, value), ...] 按日期升序。"""
    path = os.path.join(FRED_HIST_DIR, f"{series_id}.csv")
    if not os.path.exists(path):
        return []
    rows = []
    try:
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
    except Exception:
        pass
    rows.sort(key=lambda x: x[0])
    return rows


def _latest_value(series: list[tuple[str, float]]) -> Optional[float]:
    for dt, val in reversed(series):
        if not math.isnan(val):
            return val
    return None


def _slope_12m(series: list[tuple[str, float]]) -> Optional[float]:
    """计算最近12个月的线性斜率（每月变化量）。"""
    recent = [(dt, v) for dt, v in series if not math.isnan(v)][-13:]
    if len(recent) < 6:
        return None
    x = list(range(len(recent)))
    y = [v for _, v in recent]
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den = sum((xi - mean_x) ** 2 for xi in x)
    return num / den if den != 0 else 0.0


def _normalize_01(value: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


# ── IRP：通胀体制概率 ────────────────────────────────────────────────────────

# 历史体制标注（人工）
IRP_LABELS = [
    # (start, end, label)  1=高通胀, 0=低通胀/正常
    ("1973-01", "1975-12", 1),
    ("1979-01", "1983-12", 1),
    ("2021-03", "2023-12", 1),
    ("1985-01", "2000-12", 0),
    ("2010-01", "2019-12", 0),
]


def compute_irp() -> dict:
    """
    计算 IRP。
    特征：CPI 12m 斜率、PCE 水平、Fed funds、5y5y 通胀预期。
    冷启动：若 sklearn 不可用，使用简单规则。
    """
    cpi    = _load_fred_series("CPIAUCSL")
    pce    = _load_fred_series("PCEPI")
    fed    = _load_fred_series("DFF")          # 实际文件名是 DFF
    be5y5y = (_load_fred_series("T5YIFR")
               or _load_fred_series("T10YIE")
               or _load_fred_series("T10Y2Y"))  # fallback：收益率曲线斜率

    cpi_slope = _slope_12m(cpi)
    pce_level = _latest_value(pce)
    fed_rate  = _latest_value(fed)
    be_rate   = _latest_value(be5y5y)

    if any(v is None for v in [cpi_slope, pce_level, fed_rate, be_rate]):
        return {
            "irp": 0.5,
            "label": "unknown",
            "confidence": "low",
            "note": "FRED 数据不完整，使用默认值 0.5",
        }

    # 尝试用逻辑回归
    try:
        from sklearn.linear_model import LogisticRegression
        import numpy as np

        # 构建训练集
        X_train, y_train = [], []
        for start, end, label in IRP_LABELS:
            cpi_s = [(dt, v) for dt, v in cpi if start <= dt[:7] <= end]
            pce_s = [(dt, v) for dt, v in pce if start <= dt[:7] <= end]
            fed_s = [(dt, v) for dt, v in fed if start <= dt[:7] <= end]
            be_s  = [(dt, v) for dt, v in be5y5y if start <= dt[:7] <= end]
            if len(cpi_s) < 3:
                continue
            slope = _slope_12m(cpi_s) or 0.0
            pce_v = _latest_value(pce_s) or 100.0
            fed_v = _latest_value(fed_s) or 2.0
            be_v  = _latest_value(be_s)  or 2.0
            X_train.append([slope, pce_v, fed_v, be_v])
            y_train.append(label)

        if len(X_train) < 4:
            raise ValueError("训练样本不足")

        model = LogisticRegression(max_iter=500, C=1.0)
        model.fit(np.array(X_train), np.array(y_train))
        x_now = np.array([[cpi_slope, pce_level, fed_rate, be_rate]])
        irp = float(model.predict_proba(x_now)[0][1])
        method = "logistic_regression"

    except Exception:
        # 简单规则 fallback
        score = 0.0
        if cpi_slope > 0.15:  score += 0.35
        elif cpi_slope > 0.05: score += 0.15
        if fed_rate > 4.0:     score += 0.25
        elif fed_rate > 2.5:   score += 0.10
        if be_rate > 2.5:      score += 0.25
        elif be_rate > 2.0:    score += 0.10
        irp = min(1.0, score)
        method = "rule_fallback"
    if irp > 0.7:
        label = "高通胀期"
    elif irp < 0.3:
        label = "低通胀期"
    else:
        label = "转型期"

    return {
        "irp": round(irp, 4),
        "label": label,
        "method": method,
        "inputs": {
            "cpi_12m_slope": round(cpi_slope, 4),
            "pce_level":     round(pce_level, 2),
            "fed_rate":      round(fed_rate, 2),
            "be_5y5y":       round(be_rate, 2),
        },
    }


# ── UCRI：中美博弈强度 ────────────────────────────────────────────────────────

def compute_ucri(grv_latest: dict = None) -> dict:
    """
    当前可用分量（新 fetcher 待建时的近似值）：
      - 外交对抗事件指数：来自 GRV us_china_strategic 维度（已有）
      - 中美贸易趋势：来自 FRED 贸易差额数据（间接）
      - 科技管制强度：手工评估（当月未提交则用上月值）
    缺失分量（Peterson/BIS 新 fetcher）：填 0.3 默认中位，待接入后替换。

    注：此计算为近似值，待新数据源接入后重算。
    """
    weights = _load_slow_weights().get("ucri", {})
    w_dipl  = weights.get("diplomatic_confrontation", 0.20)
    w_trade = weights.get("trade_tension",            0.20)
    w_tech  = weights.get("tech_control",             0.20)
    w_tarif = weights.get("tariff_rate",              0.20)
    w_bis   = weights.get("bis_entity_list",          0.20)

    # 分量 1：外交对抗（来自 GRV）
    us_china_grv = 0.0
    if grv_latest:
        us_china_grv_raw = grv_latest.get("us_china_strategic", 50.0)
        us_china_grv = _normalize_01(us_china_grv_raw, 20.0, 90.0)

    # 分量 2：贸易趋势（FRED 贸易差额，负值大 = 对抗性强）
    trade_score = 0.3  # 默认，待 UN Comtrade fetcher 接入
    fred_trade = _load_fred_series("BOPGSTB")  # 美国货物贸易差额
    if fred_trade:
        recent_trade = [v for _, v in fred_trade[-12:] if not math.isnan(v)]
        if recent_trade:
            avg = sum(recent_trade) / len(recent_trade)
            trade_score = _normalize_01(-avg, -100000, 0)

    # 分量 3：科技管制（手工评估，读缓存）
    tech_score = _load_manual_score("tech_control_intensity", default=0.3)

    # 分量 4：关税率（Peterson 待接入，用默认）
    tariff_score = 0.4  # 待 Peterson fetcher 接入

    # 分量 5：BIS 实体清单（待接入，用默认）
    bis_score = 0.3

    # 加权合成（权重从 grv_weights.yaml slow_variables_weights.ucri 读取）
    ucri = (w_dipl  * us_china_grv
          + w_trade * trade_score
          + w_tech  * tech_score
          + w_tarif * tariff_score
          + w_bis   * bis_score)

    if ucri > 0.65:
        label = "高度对抗"
    elif ucri < 0.35:
        label = "相对缓和"
    else:
        label = "结构性竞争"

    return {
        "ucri": round(ucri, 4),
        "label": label,
        "components": {
            "diplomatic_confrontation": round(us_china_grv, 3),
            "trade_tension":            round(trade_score, 3),
            "tech_control":             round(tech_score, 3),
            "tariff_rate":              round(tariff_score, 3),  # 待接入
            "bis_entity_list":          round(bis_score, 3),     # 待接入
        },
        "note": "tariff_rate/bis_entity_list 为待接入 fetcher 占位值",
    }


# ── GCI：地缘格局指数 ─────────────────────────────────────────────────────────

def compute_gci(grv_latest: dict = None) -> dict:
    """
    三分量：
      - 大国对抗：GDELT 冲突事件（ACLED 放弃，使用 GDELT 近似）
      - 核威慑：手工评估
      - 多边合作：用 sanctions_risk GRV 维度反向代理（制裁多=合作少）

    面效度历史锚点（6个，Europe/MiddleEast/Asia state-based 冲突烈度）：
      已生成：data/ged/gci_anchors.json（generate_gci_anchors.py，GED v26.1）
      验证状态：PASS（高期均值=0.847 > 低期均值=0.665）
      待实现：check_gci_validity() 函数（天玑 V1 任务）消费该锚点做月度相关性校验
    """
    weights = _load_slow_weights().get("gci", {})
    w_conf  = weights.get("great_power_confrontation", 0.40)
    w_nuke  = weights.get("nuclear_posture",           0.35)
    w_multi = weights.get("multilateral_lack",         0.25)

    # 分量 1：大国对抗（GDELT 近似，来自 GRV 多维度均值）
    confrontation_score = 0.3
    if grv_latest:
        dims = ["russia_europe", "taiwan_strait", "middle_east_energy"]
        vals = [_normalize_01(grv_latest.get(d, 50), 20, 90) for d in dims]
        confrontation_score = sum(vals) / len(vals)

    # 分量 2：核威慑（手工评估 -1/0/+1 → 映射到 [0,1]）
    nuke_raw = _load_manual_score("nuclear_posture", default=0.0)  # -1/0/+1
    nuke_score = _normalize_01(nuke_raw, -1.0, 1.0)

    # 分量 3：多边合作（sanctions_risk 反向代理，制裁高=合作低）
    multilateral_score = 0.5
    if grv_latest:
        sanctions_raw = grv_latest.get("sanctions_risk", 50.0)
        sanctions_norm = _normalize_01(sanctions_raw, 20.0, 100.0)
        multilateral_score = 1.0 - sanctions_norm

    # 加权合成（权重从 grv_weights.yaml slow_variables_weights.gci 读取）
    # w_multi 对应"多边合作缺失"程度 = (1 - multilateral_score)
    gci = (w_conf  * confrontation_score
         + w_nuke  * nuke_score
         + w_multi * (1.0 - multilateral_score))
    gci = max(0.0, min(1.0, gci))

    if gci > 0.65:
        label = "高度分裂"
    elif gci < 0.35:
        label = "相对稳定"
    else:
        label = "竞争均衡"

    return {
        "gci": round(gci, 4),
        "label": label,
        "components": {
            "great_power_confrontation": round(confrontation_score, 3),
            "nuclear_posture":           round(nuke_score, 3),
            "multilateral_cooperation":  round(multilateral_score, 3),
        },
        "note": "大国对抗使用 GDELT 近似（ACLED 不可用）",
    }


# ── 手工评估分数读取 ──────────────────────────────────────────────────────────

def _load_manual_score(key: str, default: float = 0.0) -> float:
    """
    从 data/manual_scores.json 读取手工评估分数。
    当月未填时：查找上月 entry 的历史值（不使用 default 参数），
    并在 _last_manual_score_stale 集合中记录该 key 供 compute_all() 标注警告。
    """
    path = os.path.join(DATA_DIR, "manual_scores.json")
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        entry = data.get(key, {})
        if isinstance(entry, (int, float)):
            return float(entry)
        val = entry.get("value")
        if val is not None:
            # 检查是否当月已更新
            updated_at = entry.get("updated_at", "")
            current_month = datetime.now(timezone.utc).isoformat()[:7]
            if updated_at[:7] != current_month:
                _manual_score_stale.add(key)
            else:
                _manual_score_stale.discard(key)
            return float(val)
        return default
    except Exception:
        return default


# 记录本次 compute_all 中哪些手工评估未当月更新
_manual_score_stale: set = set()


def save_manual_score(key: str, value: float, note: str = ""):
    """维护者每月调用，更新手工评估分数。"""
    path = os.path.join(DATA_DIR, "manual_scores.json")
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        data[key] = {
            "value":      value,
            "updated_at": datetime.now(timezone.utc).isoformat()[:10],
            "note":       note,
        }
        _tmp_399 = path + ".tmp"
        with open(_tmp_399, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(_tmp_399, path)
    except Exception as e:
        print(f"[slow_variables] 手工评估写入失败: {e}")


# ── 主入口 ────────────────────────────────────────────────────────────────────

def compute_all(grv_path: str = None, force: bool = False) -> dict:
    """计算三个慢变量，写入 slow_variables.json。

    月频幂等保护：若 slow_variables.json 已存在且 updated_at 在本月，
    跳过重算直接返回缓存值（除非 force=True）。
    """
    current_month = datetime.now(timezone.utc).isoformat()[:7]

    # ── cron 幂等：本月已算则跳过 ────────────────────────────
    if not force and os.path.exists(SLOW_VAR_PATH):
        try:
            with open(SLOW_VAR_PATH, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("updated_at", "")[:7] == current_month:
                print(f"[slow_variables] 本月已计算（{cached['updated_at'][:10]}），跳过重算。传 force=True 强制重算。")
                return cached
        except Exception:
            pass

    # 加载 GRV
    _manual_score_stale.clear()
    grv_latest = {}
    grv_file = grv_path or os.path.join(DATA_DIR, "grv_latest.json")
    if os.path.exists(grv_file):
        try:
            with open(grv_file, encoding="utf-8") as f:
                grv_latest = json.load(f)
        except Exception:
            pass

    irp_result  = compute_irp()
    ucri_result = compute_ucri(grv_latest)
    gci_result  = compute_gci(grv_latest)

    # 手工评估未当月更新的警告
    stale_keys = list(_manual_score_stale)

    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "irp":        irp_result["irp"],
        "ucri":       ucri_result["ucri"],
        "gci":        gci_result["gci"],
        "irp_label":  irp_result["label"],
        "ucri_label": ucri_result["label"],
        "gci_label":  gci_result["label"],
        "detail": {
            "irp":  irp_result,
            "ucri": ucri_result,
            "gci":  gci_result,
        },
        # 转型期检测（任意慢变量处于转型区间）
        "in_transition": (
            0.3 <= irp_result["irp"] <= 0.7
            or 0.35 <= ucri_result["ucri"] <= 0.65
            or 0.35 <= gci_result["gci"] <= 0.65
        ),
        "manual_score_stale": stale_keys,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    _tmp_467 = SLOW_VAR_PATH + ".tmp"
    with open(_tmp_467, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(_tmp_467, SLOW_VAR_PATH)

    print(f"[slow_variables] IRP={result['irp']:.3f}({result['irp_label']}) "
          f"UCRI={result['ucri']:.3f}({result['ucri_label']}) "
          f"GCI={result['gci']:.3f}({result['gci_label']})")
    if result["in_transition"]:
        print("[slow_variables] ⚠️ 慢变量处于转型期，天璇推演置信区间将自动扩宽1.5倍")
    if stale_keys:
        print(f"[slow_variables] ⚠️ 手工评估未当月更新: {stale_keys}  → 请运行 save_manual_score() 更新")

    return result


def load_slow_variables() -> dict:
    """供天枢/天璇读取最新慢变量值。"""
    if not os.path.exists(SLOW_VAR_PATH):
        return {"irp": 0.5, "ucri": 0.5, "gci": 0.5, "in_transition": False}
    try:
        with open(SLOW_VAR_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"irp": 0.5, "ucri": 0.5, "gci": 0.5, "in_transition": False}


if __name__ == "__main__":
    result = compute_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))
