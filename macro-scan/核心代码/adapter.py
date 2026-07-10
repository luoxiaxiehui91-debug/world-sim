"""
适配层：将 run_macro_analysis.py 的输出格式
转换为优化模块期望的格式

为什么需要这个文件？
  - 原脚本的 mc_results 格式：{'gdp': {'mean': 2.1, 'p5': -0.5, 'p95': 3.8}}
  - 预测日志期望的格式：{'gdp_p50': 2.1, 'gdp_p10': -0.5, 'gdp_p90': 3.8}
  - 两者不匹配，需要转换

设计原则：
  - 不修改原脚本的任何函数
  - 所有适配逻辑集中在这个文件
  - 如果原脚本升级，只需更新这个文件

本地化修改（2026-05-18）：
  - 适配 run_macro_analysis.py 的实际输出格式
  - CPI 暂不模拟，cpi_p50 返回 None
"""

import math


def map_mc_results(mc_results):
    """
    将蒙特卡洛结果映射到预测日志期望的格式
    
    参数：
        mc_results: run_macro_analysis.py 返回的字典
                    格式：{'recession_prob': 45.2,
                           'gdp': {'mean': 2.1, 'p5': -0.5, 'p95': 3.8},
                           'unrate': {'mean': 4.2, 'p5': 3.8, 'p95': 5.5}}
    
    返回：
        预测日志期望的字典
        格式：{'recession_prob': 45.2,
               'gdp_p50': 2.1,
               'gdp_p10': -0.5,  # 注意：用 p5 代替 p10
               'gdp_p90': 3.8,   # 注意：用 p95 代替 p90
               'unrate_p50': 4.2,
               'cpi_p50': None}   # CPI暂不模拟
    """
    if mc_results is None:
        return None
    
    return {
        'recession_prob': mc_results.get('recession_prob'),
        'gdp_p50': _clean_value(mc_results.get('gdp', {}).get('mean')),
        'gdp_p10': _clean_value(mc_results.get('gdp', {}).get('p5')),   # p5 ≈ p10
        'gdp_p90': _clean_value(mc_results.get('gdp', {}).get('p95')),  # p95 ≈ p90
        'unrate_p50': _clean_value(mc_results.get('unrate', {}).get('mean')),
        'cpi_p50': _clean_value(mc_results.get('cpi', {}).get('mean')),  # MC CPI均值
    }


def map_risk_scores(recession, inflation):
    """
    将 (风险等级, 分数, 信号列表) 元组转换为预测日志期望的字典格式
    
    参数：
        recession: (str, int, list) 元组，如 ('中', 45, [('信号1', 1.2), ...])
        inflation: (str, int, list) 元组
    
    返回：
        {'recession': 45, 'inflation': 30, 'overall': 45}
    """
    # 注意：元组的格式是 (风险等级, 分数, 信号列表)
    # recession[0] = 风险等级 ('低'/'中'/'高')
    # recession[1] = 分数 (0-100)
    # recession[2] = 信号列表
    rec_score = recession[1] if recession and isinstance(recession, (list, tuple)) and len(recession) > 1 else None
    inf_score = inflation[1] if inflation and isinstance(inflation, (list, tuple)) and len(inflation) > 1 else None
    
    return {
        'recession': rec_score,
        'inflation': inf_score,
        'overall': max(rec_score or 0, inf_score or 0),
    }


def map_indicators(indicators):
    """
    清理指标快照，移除NaN值
    
    参数：
        indicators: {'FEDFUNDS': 4.33, 'UNRATE': 4.1, ...}
    
    返回：
        清理后的字典（NaN → None）
    """
    if not indicators:
        return {}
    
    cleaned = {}
    for k, v in indicators.items():
        cleaned[k] = _clean_value(v)
    
    return cleaned


def _clean_value(v):
    """
    清理单个值：None → None, NaN → None, float → round(4)
    """
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, float):
        return round(v, 4)
    return v


import json

# ── 测试代码 ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 测试 map_mc_results
    test_mc = {
        'recession_prob': 45.2,
        'gdp': {'mean': 2.1, 'p5': -0.5, 'p95': 3.8},
        'unrate': {'mean': 4.2, 'p5': 3.8, 'p95': 5.5},
    }
    
    mapped = map_mc_results(test_mc)
    print("测试 map_mc_results:")
    print(json.dumps(mapped, indent=2, ensure_ascii=False))
    
    # 测试 map_risk_scores
    test_recession = (45, ["信号1", "信号2"])
    test_inflation = (30, ["信号A"])
    
    risk = map_risk_scores(test_recession, test_inflation)
    print("\n测试 map_risk_scores:")
    print(json.dumps(risk, indent=2, ensure_ascii=False))
    
    print("\n[OK] adapter.py 测试通过")
