#!/usr/bin/env python3
"""
蒙特卡洛/情景模拟引擎（MC Engine）

从 run_macro_analysis.py 提取的独立模块，包含：
  - FEEDBACK_LOOPS     反馈回路定义字典
  - SCENARIOS          压力情景定义字典
  - _load_vol_calibration  读取波动率校准参数
  - run_monte_carlo    美国主蒙特卡洛引擎（5000路径）
  - run_china_monte_carlo  中国蒙特卡洛引擎
  - apply_scenario_shock     施加压力情景冲击
  - run_stress_test          单情景压力测试
  - compare_all_scenarios    全情景对比汇总

设计约束：本模块不 import run_macro_analysis，避免循环导入。
run_macro_analysis.py 需在顶部加：
    from mc_engine import FEEDBACK_LOOPS, SCENARIOS, \
        run_china_monte_carlo, apply_scenario_shock, \
        run_stress_test, compare_all_scenarios
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from copy import deepcopy

# 体制检测模块
from regime_detector import detect_regime, get_coefficients

# =========================
# 路径常量（与 run_macro_analysis.py 保持一致）
# =========================
BASE_DIR = os.environ.get(
    "OPENCLAW_WORKSPACE",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
KB_ROOT = os.environ.get("KB_ROOT") or os.path.join(BASE_DIR, "知识库")
KB_DIR = os.path.join(KB_ROOT, "财经知识库")

# =========================
# 反馈回路定义
# =========================
FEEDBACK_LOOPS = {
    "F1_通胀工资螺旋": {
        "trigger": lambda s: s.get("UNRATE",{}).get("value",99) < 4 and s.get("CPIAUCSL",{}).get("value",0) > 5,
        "intensity": (2.0, 5.0),   # 放大倍数范围（均匀采样）
        "duration": 6,            # 持续月数
        "decay_type": "exponential",
        "decay_lambda": 1/3,     # 衰减率（每月乘以e^(-λ)）
        "targets": ["cpi_yoy", "unrate"],  # 影响的指标
    },
    "F2_债务通缩": {
        "trigger": lambda s: s.get("GDPC1",{}).get("value",99) < 0,
        "intensity": (3.0, 8.0),
        "duration": 15,
        "decay_type": "exponential",
        "decay_lambda": 1/6,
        "targets": ["gdp_yoy", "baa10y"],
    },
    "F3_银行挤兑": {
        "trigger": lambda s: s.get("BAA10Y",{}).get("value",0) > 3,
        "intensity": (5.0, 20.0),
        "duration": 6,
        "decay_type": "exponential",
        "decay_lambda": 1/2,
        "targets": ["baa10y", "sp500"],
    },
    "F4_新兴市场传染": {
        "trigger": lambda s: s.get("DCOILWTICO",{}).get("value",0) > 130,
        "intensity": (2.0, 4.0),
        "duration": 9,
        "decay_type": "linear",   # 每月衰减 rate=1/duration
        "decay_rate": 1/12,       # 线性衰减速率
        "targets": ["oil", "cpi_yoy", "sp500"],
    },
    "F5_保证金螺旋": {
        "trigger": lambda s: s.get("VIX",{}).get("value",0) > 35,
        "intensity": (2.0, 3.0),
        "duration": 4,
        "decay_type": "exponential",
        "decay_lambda": 1/2,
        "targets": ["sp500", "vix"],
    },
    "F6_美元流动性枯竭": {
        "trigger": lambda s: s.get("BAA10Y",{}).get("value",0) > 2.5 and s.get("T10Y2Y",{}).get("value",99) < -0.5,
        "intensity": (3.0, 5.0),
        "duration": 9,
        "decay_type": "exponential",
        "decay_lambda": 1/4,
        "targets": ["baa10y", "gdp_yoy"],
    },
    "F7_油价滞胀循环": {
        # WTI>100 + CPI>3% → 供给推通胀持续 → 联储无法降息 → 需求压制
        "trigger": lambda s: s.get("DCOILWTICO",{}).get("value",0) > 100 and s.get("CPIAUCSL",{}).get("value",0) > 3,
        "intensity": (1.5, 3.0),
        "duration": 9,
        "decay_type": "exponential",
        "decay_lambda": 1/4,
        "targets": ["cpi_yoy", "gdp_yoy"],
    },
    "F8_财政利率螺旋": {
        # 穆迪评级警告：高债务 → 信用溢价 → 利息支出上升 → 赤字扩大 → 评级压力循环
        "trigger": lambda s: s.get("DGS10",{}).get("value",0) > 4.5 and s.get("BAA10Y",{}).get("value",0) > 1.5,
        "intensity": (1.2, 2.5),
        "duration": 18,
        "decay_type": "linear",
        "decay_rate": 1/24,
        "targets": ["baa10y", "gdp_yoy"],
    },
}

# =========================
# 压力情景定义
# =========================
SCENARIOS = {
    "stress_energy": {
        "name": "能源冲击（霍尔木兹封锁）",
        "description": "WTI原油涨至$130，通胀再加速，联储两难",
        "shocks": {
            "DCOILWTICO":  {"delta": 30.0},   # 油价+30
            "CPIAUCSL":    {"delta": 1.5},    # CPI+1.5ppt（传导）
            "PCEPI":       {"delta": 1.2},    # PCE+1.2ppt
            "PPIACO":      {"delta": 5.0},    # PPI+5ppt
        }
    },
    "stress_recession": {
        "name": "需求衰退（信用收紧+消费崩溃）",
        "description": "消费信心大跌，失业率快速上升，GDP萎缩",
        "shocks": {
            "UNRATE":    {"delta": 1.5},      # 失业率+1.5ppt
            "UMCSENT":   {"delta": -20.0},    # 消费信心-20
            "GDPC1":     {"delta": -2.0},     # GDP-2ppt
            "ICSA":      {"delta": 80000},    # 初请失业金+8万
        }
    },
    "stress_credit": {
        "name": "信用危机（美债评级下调）",
        "description": "穆迪实际下调评级，长端利率飙升，信用利差扩大",
        "shocks": {
            "DGS10":       {"delta": 1.0},    # 10Y利率+100bp
            "BAA10Y":      {"delta": 1.5},    # 信用利差+150bp
            "BAMLH0A0HYM2":{"delta": 2.0},   # 高收益利差+200bp
            "GDPC1":       {"delta": -1.0},   # GDP-1ppt（金融条件收紧）
        }
    },
    # ── 中国专属压力情景 ───────────────────────────────────────────────────────
    "stress_cn_property": {
        "name": "中国地产崩塌（银行信贷紧缩）",
        "description": "房地产开发商违约潮蔓延，土地出让收入骤降，地方政府流动性危机",
        "target": "china",
        "shocks": {
            "gdp_growth":    {"delta": -1.5},   # GDP增速-1.5ppt
            "pmi_mfg":       {"delta": -3.0},   # PMI-3（收缩加深）
            "m2_growth":     {"delta": -2.0},   # M2增速-2ppt（信贷紧缩）
            "cpi":           {"delta": -0.8},   # CPI-0.8ppt（通缩加剧）
        }
    },
    "stress_cn_deflation": {
        "name": "中国深度通缩（需求萎缩+产能过剩）",
        "description": "PPI持续负增长，企业投资意愿崩溃，日本化风险上升",
        "target": "china",
        "shocks": {
            "gdp_growth":    {"delta": -2.0},   # GDP跌至2.5%
            "cpi":           {"delta": -1.5},   # CPI跌至-1.6%（深度通缩）
            "pmi_mfg":       {"delta": -4.0},   # PMI<46
            "industrial_va": {"delta": -3.0},   # 工业增加值骤降
            "m2_growth":     {"delta": -3.0},   # M2增速跌至5%
        }
    },
    "stress_global_stagflation": {
        "name": "全球滞胀叠加（中美同步承压）",
        "description": "WTI>130美元，美国通胀>5%，中国出口暴跌，全球需求塌陷",
        "target": "both",
        "shocks": {
            # 美国侧
            "DCOILWTICO":  {"delta": 25.0},   # WTI+25 → 137美元
            "CPIAUCSL":    {"delta": 1.8},    # CPI+1.8ppt → 5.6%
            "PPIACO":      {"delta": 4.0},    # PPI+4ppt → 13.8%
            "UNRATE":      {"delta": 0.8},    # 失业率+0.8ppt
            "BAA10Y":      {"delta": 1.0},    # 信用利差+100bp
            # 中国侧（同时施加）
            "gdp_growth":  {"delta": -1.2},   # GDP-1.2ppt
            "pmi_mfg":     {"delta": -3.5},   # PMI深度收缩
            "cpi":         {"delta": 0.5},    # 通胀稍微回升（输入型）
        }
    },
}


# =========================
# 函数
# =========================

def _load_vol_calibration() -> Dict:
    """加载波动率校准参数（从calibrate_volatility.py生成）"""
    cal_path = os.path.join(KB_DIR, "02_核心变量因果链", "波动率校准参数.json")
    try:
        if os.path.exists(cal_path):
            with open(cal_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def run_monte_carlo(indicators: Dict, coeffs: Dict = None, n_sim: int = 5000, n_months: int = 12) -> Dict:
    """蒙特卡洛模拟：基于当前指标运行概率推演（历史校准波动率）

    Parameters
    ----------
    indicators : 当前指标快照
    coeffs : 体制系数字典（来自 regime_detector）
    n_sim : 模拟次数
    n_months : 推演月数

    Returns:
        {recession_prob, gdp_dist, unrate_dist, sp500_dist, feedback_triggered, calibration}
    """
    import numpy as np
    np.random.seed(42)

    # 默认使用常态系数
    if coeffs is None:
        coeffs = {
            "rate_gdp_impact": -0.30,
            "inflation_persistence": 0.65,
            "credit_multiplier": 1.2,
            "recession_threshold": -0.5,
        }

    # 加载校准参数
    cal = _load_vol_calibration()
    mc_cal = cal.get("_mc_calibration", {})

    # 基线值
    bl = {
        "unrate": indicators.get("UNRATE", {}).get("value", 4.3),
        "gdp_yoy": indicators.get("GDPC1", {}).get("value", 2.5),
        "cpi_yoy": indicators.get("CPIAUCSL", {}).get("value", 3.0),
        "ffr": indicators.get("DFF", {}).get("value", 3.5),
        "dgs10": indicators.get("DGS10", {}).get("value", 4.0),
        "t10y2y": indicators.get("T10Y2Y", {}).get("value", 0.5),
        "sp500": indicators.get("SP500", {}).get("value", 7000),
        "baa10y": indicators.get("BAA10Y", {}).get("value", 1.5),
        "oil": indicators.get("DCOILWTICO", {}).get("value", 100),
    }

    # 波动率（月度标准差，历史校准）
    # 优先使用校准值，回退到固定估计
    vol = {
        "unrate": mc_cal.get("UNRATE_monthly_std", 0.15),
        "gdp_yoy": mc_cal.get("GDPC1_monthly_std", 0.011) * 30,  # level→YoY近似
        "cpi_yoy": mc_cal.get("CPIAUCSL_monthly_std", 0.003) * 30,
        "ffr": mc_cal.get("DFF_monthly_std", 0.14),
        "dgs10": mc_cal.get("DGS10_monthly_std", 0.058),
        "sp500": mc_cal.get("SP500_monthly_std", 0.011),  # 月度收益率标准差
        "baa10y": mc_cal.get("BAA10Y_monthly_std", 0.031),
        "oil": mc_cal.get("DCOILWTICO_monthly_std", 0.044),  # 月度收益率标准差
    }

    # 危机期波动率放大倍数
    crisis_mult = {
        "unrate": mc_cal.get("UNRATE_crisis_multiplier", 7.3),
        "gdp_yoy": mc_cal.get("GDPC1_crisis_multiplier", 2.3),
        "cpi_yoy": mc_cal.get("CPIAUCSL_crisis_multiplier", 2.1),
        "ffr": mc_cal.get("DFF_crisis_multiplier", 0.8),
        "dgs10": mc_cal.get("DGS10_crisis_multiplier", 1.4),
        "sp500": mc_cal.get("SP500_crisis_multiplier", 2.5),
        "baa10y": mc_cal.get("BAA10Y_crisis_multiplier", 1.8),
        "oil": mc_cal.get("DCOILWTICO_crisis_multiplier", 4.3),
    }

    # 传导系数（体制切换：常态 vs 危机态）
    # 常态系数基于P0量化表+跨国验证；危机系数基于P2历史危机实证
    # 危机时传导增强的路径：利率→失业（企业融资断裂→裁员加速）、
    # 股市→GDP（财富效应放大）、利率→GDP（信贷紧缩放大）
    # 危机时传导减弱的路径：利率→CPI（供给约束主导，需求端传导钝化）
    tx_normal = {
        "ffr_to_unrate": 0.10,    # FFR每升1%，失业率+0.10%
        "ffr_to_gdp": -0.30,     # FFR每升1%，GDP -0.30%
        "dgs10_to_cpi": -0.05,   # 10Y每升1%，CPI -0.05%（需求压制）
        "sp500_to_gdp": 0.02,    # SP500每涨10%，GDP +0.20%
        "oil_to_cpi": 0.03,      # 油价每涨10%，CPI +0.30%
        "baa10y_to_gdp": -0.50,  # 信用利差每扩1%，GDP -0.50%
    }
    tx_crisis = {
        "ffr_to_unrate": 0.25,    # 危机时2.5x（融资断裂→裁员加速）
        "ffr_to_gdp": -0.60,     # 危机时2x（信贷紧缩+信心崩溃）
        "dgs10_to_cpi": -0.02,   # 危机时0.4x（供给约束主导，利率传导钝化）
        "sp500_to_gdp": 0.05,    # 危机时2.5x（财富效应+保证金螺旋）
        "oil_to_cpi": 0.06,      # 危机时2x（成本推升+预期锚定）
        "baa10y_to_gdp": -1.20,  # 危机时2.4x（信用冻结→投资断崖）
    }

    # GDELT 地缘政治调制（读缓存文件，不发网络请求）
    try:
        from scan_weak_signals import get_gdelt_geo_modifier
        geo_mod = get_gdelt_geo_modifier()
    except Exception:
        geo_mod = {}
    # 亚太尾风险（台海/朝鲜）→ 危机概率上调，上限 45%
    _crisis_prob = min(0.45, 0.15 + geo_mod.get("tail_risk_boost", 0) / 100 * 0.20)

    # 结构层先验（季度慢变量）— 修改传导系数本身
    try:
        from assess_structural_dimensions import (
            load_structural_priors, compute_structural_mc_adjustments,
        )
        _struct_adj = compute_structural_mc_adjustments(load_structural_priors())
    except Exception:
        _struct_adj = {}
    # 政治脆弱 → 危机概率叠加
    _crisis_prob = min(0.45, _crisis_prob + _struct_adj.get("crisis_prob_adj", 0))
    # 结构调整后的传导系数（在循环外算一次）
    _oil_cpi_mult    = _struct_adj.get("oil_cpi_mult",       1.0)
    _unrate_sens     = _struct_adj.get("unrate_sensitivity",  1.0)
    _gdp_struct_drag = _struct_adj.get("gdp_drag_adj",        0.0)

    # 将结构先验叠加到传导系数（循环外）
    tx_normal_s = {**tx_normal,
        "oil_to_cpi":    tx_normal["oil_to_cpi"]    * _oil_cpi_mult,
        "ffr_to_unrate": tx_normal["ffr_to_unrate"] * _unrate_sens,
    }
    tx_crisis_s = {**tx_crisis,
        "oil_to_cpi":    tx_crisis["oil_to_cpi"]    * _oil_cpi_mult,
        "ffr_to_unrate": tx_crisis["ffr_to_unrate"] * _unrate_sens,
    }

    recession_count = 0
    feedback_counts = {k: 0 for k in FEEDBACK_LOOPS}
    gdp_finals, unrate_finals, sp500_rets = [], [], []
    crisis_count = 0  # 危机态模拟次数

    for _ in range(n_sim):
        # 危机概率 = 基线15% + GDELT亚太尾风险调制
        is_crisis = np.random.random() < _crisis_prob
        if is_crisis:
            crisis_count += 1

        # 体制切换传导系数（含结构先验调整）
        tx = tx_crisis_s if is_crisis else tx_normal_s

        # 应用波动率（危机态使用放大后的值）
        v = {}
        for k in vol:
            base_v = vol[k]
            if is_crisis:
                base_v *= crisis_mult.get(k, 2.0)
            v[k] = base_v

        # 简化模拟：12个月后终点值
        # FFR 随机游走
        ffr_end = bl["ffr"] + np.random.normal(0, v["ffr"] * np.sqrt(n_months))
        ffr_end = max(0, min(8, ffr_end))

        # 10Y
        dgs10_end = bl["dgs10"] + np.random.normal(0, v["dgs10"] * np.sqrt(n_months))
        dgs10_end = max(1, min(8, dgs10_end))

        # 利差
        t10y2y_end = dgs10_end - (ffr_end + 0.3)

        # 失业率（体制切换传导）
        ffr_effect = tx["ffr_to_unrate"] * (ffr_end - 3.5)
        unrate_end = bl["unrate"] + np.random.normal(0, v["unrate"] * np.sqrt(n_months)) + ffr_effect
        unrate_end = max(2, min(12, unrate_end))

        # GDP（体制切换传导 + 新增信用利差和油价路径）
        ffr_gdp = tx["ffr_to_gdp"] * (ffr_end - 3.5)
        sp500_ret = np.random.normal(-0.02 if is_crisis else 0.01, v["sp500"] * np.sqrt(n_months))
        sp500_gdp = tx["sp500_to_gdp"] * sp500_ret * 10
        baa10y_end = bl["baa10y"] + np.random.normal(0.3 if is_crisis else 0, v["baa10y"] * np.sqrt(n_months))
        baa10y_end = max(0.5, min(6, baa10y_end))
        credit_gdp = tx["baa10y_to_gdp"] * (baa10y_end - 1.5)  # 信用利差扩大→GDP受损
        _gdp_sentiment = geo_mod.get("umcsent_drag", 0) * 0.02  # 消费信心拖累→GDP（最大 -0.16%）
        gdp_end = bl["gdp_yoy"] + np.random.normal(-0.5 if is_crisis else 0, v["gdp_yoy"] * np.sqrt(n_months)) + ffr_gdp * 0.1 + sp500_gdp + credit_gdp * 0.1 + _gdp_sentiment - _gdp_struct_drag
        gdp_end = max(-5, min(8, gdp_end))

        # CPI（体制切换传导 + 新增油价路径）
        rate_cpi = tx["dgs10_to_cpi"] * (dgs10_end - 4)
        _oil_drift = (0.1 if is_crisis else 0) + geo_mod.get("oil_shock_bias", 0) * 0.15
        oil_end = bl["oil"] * (1 + np.random.normal(_oil_drift, v["oil"] * np.sqrt(n_months)))
        oil_end = max(30, min(250, oil_end))
        oil_cpi = tx["oil_to_cpi"] * ((oil_end / bl["oil"]) - 1) * 10  # 油价涨幅→CPI
        cpi_end = bl["cpi_yoy"] + np.random.normal(0.3 if is_crisis else 0, v["cpi_yoy"] * np.sqrt(n_months)) + rate_cpi + oil_cpi
        cpi_end = max(-2, min(10, cpi_end))

        # SP500
        sp500_end = bl["sp500"] * (1 + sp500_ret)
        sp500_end = max(2000, min(15000, sp500_end))

        # 检测衰退信号（至少2个）
        signals = 0
        if unrate_end - bl["unrate"] > 0.5: signals += 1  # Sahm-like
        if t10y2y_end < -0.5: signals += 1  # 利差倒挂
        if gdp_end < 0: signals += 1  # GDP负增长
        if sp500_end / bl["sp500"] - 1 < -0.2: signals += 1  # SP500崩盘

        # 使用体制系数的衰退阈值
        recession_threshold = coeffs.get("recession_threshold", -0.5)
        if signals >= 2 or gdp_end < recession_threshold:
            recession_count += 1

        # VIX模拟（简化：基于SP500波动推断）
        sp500_change = (sp500_end / bl["sp500"] - 1)
        vix_end = 18 * (1 + max(0, -sp500_change * 3))  # 股市跌→VIX升
        if is_crisis:
            vix_end *= np.random.uniform(1.5, 3.0)  # 危机时VIX可能飙升

        sim_snap = {
            "UNRATE": {"value": unrate_end},
            "GDPC1": {"value": gdp_end},
            "CPIAUCSL": {"value": cpi_end},
            "DFF": {"value": ffr_end},
            "DGS10": {"value": dgs10_end},
            "T10Y2Y": {"value": t10y2y_end},
            "SP500": {"value": sp500_end},
            "BAA10Y": {"value": baa10y_end},
            "DCOILWTICO": {"value": oil_end},
            "VIX": {"value": vix_end},
        }

        # 检测并应用反馈回路（量化版：强度+持续+衰减）
        for fname, floop in FEEDBACK_LOOPS.items():
            try:
                if floop["trigger"](sim_snap):
                    feedback_counts[fname] += 1
                    # 采样强度
                    lo, hi = floop["intensity"]
                    amp = np.random.uniform(lo, hi)
                    # 应用衰减（模拟12个月后的衰减效果）
                    dur = floop["duration"]
                    if floop["decay_type"] == "exponential":
                        decay = np.exp(-floop["decay_lambda"] * n_months)
                    else:  # linear
                        decay = max(0, 1 - floop.get("decay_rate", 1/dur) * n_months)
                    effective_amp = amp * decay
                    # 反馈回路放大尾部风险：对受影响指标施加额外偏离
                    for target in floop.get("targets", []):
                        if target == "gdp_yoy":
                            gdp_end -= effective_amp * 0.5  # GDP额外下滑
                        elif target == "unrate":
                            unrate_end += effective_amp * 0.3  # 失业率额外上升
                        elif target == "cpi_yoy":
                            cpi_end += effective_amp * 0.2  # 通胀额外上行
                        elif target == "sp500":
                            sp500_end *= (1 - effective_amp * 0.05)  # 股市额外下跌
                        elif target == "baa10y":
                            baa10y_end += effective_amp * 0.2  # 信用利差额外扩大
                        elif target == "oil":
                            oil_end *= (1 + effective_amp * 0.05)  # 油价额外上行
            except Exception as e:
                logging.debug(f"反馈回路应用失败: {e}")

        gdp_finals.append(gdp_end)
        unrate_finals.append(unrate_end)
        sp500_rets.append((sp500_end / bl["sp500"] - 1) * 100)

    # 汇总
    gdp_arr = np.array(gdp_finals)
    unrate_arr = np.array(unrate_finals)
    sp500_arr = np.array(sp500_rets)

    recession_prob = recession_count / n_sim * 100
    # GDELT 俄乌/能源路径直接加成（最大 +5ppt）
    if geo_mod.get("recession_boost"):
        recession_prob = min(99.0, recession_prob + geo_mod["recession_boost"] * 0.5)

    # 找出最可能触发的反馈回路
    active_feedback = [(k, v/n_sim*100) for k, v in feedback_counts.items() if v > n_sim * 0.01]
    active_feedback.sort(key=lambda x: -x[1])

    result = {
        "n_sim": n_sim,
        "n_months": n_months,
        "recession_prob": round(recession_prob, 1),
        "crisis_state_pct": round(crisis_count / n_sim * 100, 1),
        "gdelt_mod": geo_mod if geo_mod else None,
        "gdp": {"mean": round(float(np.mean(gdp_arr)),2), "p5": round(float(np.percentile(gdp_arr,5)),2), "p95": round(float(np.percentile(gdp_arr,95)),2)},
        "unrate": {"mean": round(float(np.mean(unrate_arr)),2), "p5": round(float(np.percentile(unrate_arr,5)),2), "p95": round(float(np.percentile(unrate_arr,95)),2)},
        "sp500": {"mean": round(float(np.mean(sp500_arr)),1), "p5": round(float(np.percentile(sp500_arr,5)),1), "p95": round(float(np.percentile(sp500_arr,95)),1)},
        "feedback": active_feedback,
        "calibrated": bool(mc_cal),
    }

    return result


def run_china_monte_carlo(indicators: Dict, n_sim: int = 3000, n_months: int = 12) -> dict:
    """
    中国宏观蒙特卡洛模拟，使用 monte_carlo_v2 的 MonteCarloV2 类。
    以中国指标为初始值，覆盖全局变量均值，返回与美国 MC 结构兼容的 dict。
    """
    try:
        import math
        import numpy as np
        from monte_carlo_v2 import MonteCarloV2

        # 从中国指标提取初始值（带降级）
        gdp0  = indicators.get("gdp_growth",  {}).get("value") or 5.0
        cpi0  = indicators.get("cpi",         {}).get("value") or 1.5
        pmi0  = indicators.get("pmi_mfg",     {}).get("value") or 50.0
        m2_0  = indicators.get("m2_growth",   {}).get("value") or 8.0

        # 使用 china_gdp 变量作为主模拟轴，其他变量用默认初始值
        initial = {
            "gdp_growth":     gdp0,
            "inflation":      cpi0,
            "unemployment":   5.2,     # 中国官方失业率（城镇调查）
            "fed_funds_rate": 3.5,     # 不直接相关，用全球无风险利率代替
            "vix":            18.0,
            "sp500_return":   6.0,
            "china_gdp":      gdp0,    # 专门的中国GDP变量
        }

        mc = MonteCarloV2(model="garch_jump", n_paths=n_sim, horizon=n_months, seed=42)
        result = mc.run(initial)

        # 从 china_gdp 路径提取结果
        cg = result.get("china_gdp", result.get("gdp_growth", {}))
        ci = result.get("inflation", {})
        probs = result.get("probabilities", {})

        # 中国衰退定义：GDP < 3%（严重）；< 4%（温和）
        # 用分布分位数反推正态参数，再用 CDF 计算概率
        cg_mean = cg.get("mean", gdp0)
        cg_p10  = cg.get("p10", gdp0 - 1.5)
        cg_p90  = cg.get("p90", gdp0 + 1.5)
        sigma_gdp = max((cg_p90 - cg_p10) / 2.563, 0.1)  # 2.563 = 2×Φ⁻¹(0.90)

        def _norm_cdf(x, mu, sigma):
            z = (x - mu) / sigma
            return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))

        prob_severe   = _norm_cdf(3.0, cg_mean, sigma_gdp) * 100  # GDP < 3%
        prob_mild     = _norm_cdf(4.0, cg_mean, sigma_gdp) * 100  # GDP < 4%
        recession_prob = prob_mild  # 使用温和定义（<4%）作为主衰退概率

        # 通缩概率：CPI < 0
        ci_mean  = ci.get("mean",  cpi0)
        ci_p10   = ci.get("p10",   cpi0 - 0.8)
        ci_p90   = ci.get("p90",   cpi0 + 0.8)
        sigma_cpi = max((ci_p90 - ci_p10) / 2.563, 0.1)
        deflation_prob = _norm_cdf(0.0, ci_mean, sigma_cpi) * 100

        return {
            "recession_prob":   round(recession_prob, 1),
            "recession_severe_prob": round(prob_severe, 1),
            "deflation_prob":   round(deflation_prob, 1),
            "crisis_state_pct": round(probs.get("deep_recession", 0) * 100, 1),
            "calibrated": False,
            "stress_signals": 0,
            "gdp":   {"mean": round(cg_mean, 2),
                      "p5":   round(cg_p10,  2),
                      "p95":  round(cg_p90,  2)},
            "cpi":   {"mean": round(ci_mean,  2),
                      "p5":   round(ci_p10,   2),
                      "p95":  round(ci_p90,   2)},
            "unrate":{"mean": round(5.5 - (cg_mean - 5.0) * 0.15, 2),
                      "p95":  6.0},
            "feedback": [],
        }
    except Exception as e:
        print(f"  [中国MC] 模拟失败: {e}")
        return None


def apply_scenario_shock(indicators: Dict, scenario_name: str) -> Tuple[Dict, str]:
    """
    对指标快照施加压力情景冲击，返回冲击后的指标副本和情景描述。
    """
    import copy
    scenario = SCENARIOS.get(scenario_name)
    if not scenario:
        return indicators, f"未知情景: {scenario_name}"

    shocked = copy.deepcopy(indicators)
    applied = []
    for sid, shock in scenario["shocks"].items():
        if sid in shocked and shocked[sid].get("value") is not None:
            orig = shocked[sid]["value"]
            delta = shock.get("delta", 0)
            shocked[sid]["value"] = round(orig + delta, 4)
            shocked[sid]["source"] = "scenario_shock"
            applied.append(f"{sid}: {orig:+.2f} → {shocked[sid]['value']:+.2f} (Δ{delta:+.2f})")
        else:
            # 指标不存在时插入虚拟条目
            shocked[sid] = {
                "value": shock.get("delta", 0),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "name": sid,
                "source": "scenario_shock"
            }
            applied.append(f"{sid}: 新增 {shock['delta']:+.2f}")

    desc = f"[压力测试] {scenario['name']}\n{scenario['description']}\n冲击详情:\n" + "\n".join(f"  {a}" for a in applied)
    return shocked, desc


def run_stress_test(base_indicators: Dict, scenario_name: str, n_sim: int = 3000) -> str:
    """
    对基准指标施加压力情景冲击，运行MC，返回对比摘要文本。
    """
    try:
        from monte_carlo_v2 import run_monte_carlo_compat
        shocked_ind, desc = apply_scenario_shock(base_indicators, scenario_name)
        scenario_info = SCENARIOS.get(scenario_name, {})

        # 基准MC
        regime_base, _ = detect_regime(base_indicators)
        coeffs_base = get_coefficients(regime_base)
        mc_base = run_monte_carlo_compat(base_indicators, coeffs_base)

        # 冲击后MC
        regime_shock, _ = detect_regime(shocked_ind)
        coeffs_shock = get_coefficients(regime_shock)
        mc_shock = run_monte_carlo_compat(shocked_ind, coeffs_shock)

        if not mc_base or not mc_shock:
            return f"{desc}\n[压力测试MC失败]"

        lines = [
            f"\n## 压力测试：{scenario_info.get('name', scenario_name)}",
            f"> {scenario_info.get('description', '')}",
            "",
            "| 指标 | 基准 | 冲击后 | 变化 |",
            "|:----|:---:|:-----:|:----:|",
            f"| 衰退概率 | {mc_base['recession_prob']}% | {mc_shock['recession_prob']}% | +{mc_shock['recession_prob']-mc_base['recession_prob']:.1f}ppt |",
            f"| GDP(12M均值) | {mc_base['gdp']['mean']}% | {mc_shock['gdp']['mean']}% | {mc_shock['gdp']['mean']-mc_base['gdp']['mean']:+.2f}ppt |",
            f"| GDP(P5) | {mc_base['gdp']['p5']}% | {mc_shock['gdp']['p5']}% | {mc_shock['gdp']['p5']-mc_base['gdp']['p5']:+.2f}ppt |",
            f"| 失业率(均值) | {mc_base['unrate']['mean']}% | {mc_shock['unrate']['mean']}% | {mc_shock['unrate']['mean']-mc_base['unrate']['mean']:+.2f}ppt |",
            f"| CPI(均值) | {mc_base['cpi'].get('mean','?')}% | {mc_shock['cpi'].get('mean','?')}% | — |",
            f"| 体制 | {regime_base} | {regime_shock} | — |",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"[压力测试失败] {e}"


def compare_all_scenarios(base_indicators: Dict, n_sim: int = 2000) -> str:
    """
    一次性运行所有压力情景并输出对比汇总表。
    衰退概率升幅 ≥ 20ppt → 🔴；≥ 10ppt → 🟡；其余 → 🟢
    """
    try:
        from monte_carlo_v2 import run_monte_carlo_compat

        regime_base, _ = detect_regime(base_indicators)
        coeffs_base    = get_coefficients(regime_base)
        mc_base        = run_monte_carlo_compat(base_indicators, coeffs_base, n_sim=n_sim)
        if not mc_base:
            return "[情景比较] 基准MC失败"

        base_rec  = mc_base["recession_prob"]
        base_gdp  = mc_base["gdp"]["mean"]
        base_gdpp5= mc_base["gdp"]["p5"]

        rows = [
            f"\n## 全情景衰退概率对比表（基准：{base_rec:.1f}%）",
            "",
            "| 情景 | 衰退概率 | Δ概率 | GDP均值 | GDP P5 | 体制 | 风险 |",
            "|:----|:-------:|:-----:|:------:|:------:|:----:|:----:|",
            f"| 基准（Baseline）| {base_rec:.1f}% | — | {base_gdp:.2f}% | {base_gdpp5:.2f}% | {regime_base} | — |",
        ]

        # US-targeted + both-targeted scenarios
        us_scenarios  = [s for s, v in SCENARIOS.items() if v.get("target", "us") in ("us", "both")]
        cn_scenarios  = [s for s, v in SCENARIOS.items() if v.get("target") == "china"]

        for sid in us_scenarios:
            try:
                shocked_ind, _ = apply_scenario_shock(base_indicators, sid)
                regime_s, _    = detect_regime(shocked_ind)
                coeffs_s       = get_coefficients(regime_s)
                mc_s           = run_monte_carlo_compat(shocked_ind, coeffs_s, n_sim=n_sim)
                if not mc_s:
                    continue
                rec_s  = mc_s["recession_prob"]
                gdp_s  = mc_s["gdp"]["mean"]
                gdpp5_s = mc_s["gdp"]["p5"]
                delta  = rec_s - base_rec
                icon   = "🔴" if delta >= 20 else ("🟡" if delta >= 10 else "🟢")
                name   = SCENARIOS[sid]["name"]
                rows.append(
                    f"| {name} | {rec_s:.1f}% | {delta:+.1f}ppt | "
                    f"{gdp_s:.2f}% | {gdpp5_s:.2f}% | {regime_s} | {icon} |"
                )
            except Exception:
                continue

        if cn_scenarios:
            rows.append(f"\n*中国专属情景（需 --country china/both）：{', '.join(cn_scenarios)}*")

        rows.append(f"\n> 模拟规模：n={n_sim} 路径/情景。排序按衰退概率升幅降序。")
        return "\n".join(rows)
    except Exception as e:
        return f"[情景比较失败] {e}"
