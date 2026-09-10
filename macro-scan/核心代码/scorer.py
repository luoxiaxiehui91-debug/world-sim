"""
评分函数模块 — 从 run_macro_analysis.py 提取
包含：
  - score_recession_risk       美国衰退风险评分
  - score_inflation_risk       美国通胀风险评分
  - score_china_recession_risk 中国衰退风险评分
  - score_china_inflation_risk 中国价格风险评分
  - match_china_crisis         中国历史危机匹配
  - _parse_pct                 百分比字符串解析（内部辅助）
  - match_crisis               美国历史危机匹配（依赖 CRISIS_CSV）

所有函数均为纯函数（接受 Dict 参数），不调用 run_macro_analysis.py 中的其他函数。
"""

import os
import pandas as pd
from typing import Dict, List, Tuple, Optional

# =========================
# CRISIS_CSV 路径配置
# =========================
# 与 run_macro_analysis.py 保持一致：
#   BASE_DIR → 知识库/财经知识库 → 02_核心变量因果链 → 历史情景_量化指标.csv
BASE_DIR = os.environ.get(
    "OPENCLAW_WORKSPACE",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
KB_ROOT    = os.environ.get("KB_ROOT") or os.path.join(BASE_DIR, "知识库")
KB_DIR     = os.path.join(KB_ROOT, "财经知识库")
CRISIS_CSV = os.path.join(KB_DIR, "02_核心变量因果链", "历史情景_量化指标.csv")


# =========================
# 美国风险评分
# =========================

def score_recession_risk(indicators: Dict) -> Tuple[str, int, List[Tuple[str, float]]]:
    """
    衰退风险评分（0-100），加权连续评分（LEI框架）。

    权重分配参考 Conference Board LEI：
      利率曲线倒挂   25pt  — 最强预测信号，领先6-18个月
      信用利差扩张   20pt  — 金融条件收紧
      萨姆规则       20pt  — 近实时衰退确认，历史100%命中
      初请失业金     15pt  — 劳动力市场领先2周
      LEI周工时/许可 10pt  — 制造业+建筑双通道
      GDP/消费信心   10pt  — 同步/短期先行
    """
    signals = []
    score = 0

    # ── 1. 利率曲线倒挂（权重25pt）──────────────────────────────────────────
    t10y2y = indicators.get("T10Y2Y", {}).get("value")
    if t10y2y is not None:
        if t10y2y < -1.0:
            score += 25; signals.append(("利差极深倒挂", f"{t10y2y:.2f}%"))
        elif t10y2y < -0.5:
            score += 20; signals.append(("利差深度倒挂", f"{t10y2y:.2f}%"))
        elif t10y2y < 0:
            score += 12; signals.append(("利差倒挂", f"{t10y2y:.2f}%"))
        elif t10y2y < 0.3:
            score += 4;  signals.append(("利差偏平（接近倒挂）", f"{t10y2y:.2f}%"))

    # ── 2. 信用利差扩张（权重20pt）──────────────────────────────────────────
    baa10y = indicators.get("BAA10Y", {}).get("value")
    if baa10y is not None:
        if baa10y > 4.0:
            score += 20; signals.append(("信用利差极度扩张", f"{baa10y:.1f}%"))
        elif baa10y > 3.0:
            score += 15; signals.append(("信用利差显著扩张", f"{baa10y:.1f}%"))
        elif baa10y > 2.0:
            score += 8;  signals.append(("信用利差扩大", f"{baa10y:.1f}%"))

    # ── 3. 萨姆规则（权重20pt）──────────────────────────────────────────────
    sahm = indicators.get("SAHM_RULE", {}).get("value")
    if sahm is not None:
        if sahm >= 0.5:
            score += 20; signals.append(("萨姆规则触发（衰退确认）", f"{sahm:.3f}≥0.5"))
        elif sahm >= 0.3:
            score += 10; signals.append(("萨姆规则接近阈值", f"{sahm:.3f}（阈值0.5）"))
        elif sahm >= 0.15:
            score += 4;  signals.append(("萨姆指标上升", f"{sahm:.3f}"))

    # ── 4. 初请失业金（权重15pt）────────────────────────────────────────────
    icsa = indicators.get("ICSA", {}).get("value")
    if icsa is not None:
        if icsa > 350000:
            score += 15; signals.append(("初请严重高位", f"{icsa/10000:.0f}万人"))
        elif icsa > 280000:
            score += 10; signals.append(("初请高位", f"{icsa/10000:.0f}万人"))
        elif icsa > 240000:
            score += 5;  signals.append(("初请偏高", f"{icsa/10000:.0f}万人"))

    # ── 5. LEI周工时 + 建筑许可（合计权重10pt）──────────────────────────────
    awhman = indicators.get("AWHMAN", {}).get("value")
    if awhman is not None:
        if awhman < 40.0:
            score += 5; signals.append(("制造业周工时偏低", f"{awhman:.1f}h（<40h警戒）"))
        elif awhman < 40.5:
            score += 2; signals.append(("制造业周工时收缩", f"{awhman:.1f}h"))

    permit = indicators.get("PERMIT", {}).get("value")  # 千套，SAAR
    if permit is not None:
        if permit < 1200:
            score += 5; signals.append(("建筑许可低迷", f"{permit:.0f}千套（<120万警戒）"))
        elif permit < 1400:
            score += 2; signals.append(("建筑许可偏弱", f"{permit:.0f}千套"))

    # ── 6. GDP增速 + 消费信心（权重10pt）────────────────────────────────────
    gdp = indicators.get("GDPC1", {}).get("value")
    if gdp is not None:
        if gdp < 0:
            score += 8;  signals.append(("GDP负增长", f"{gdp:.1f}%"))
        elif gdp < 1.0:
            score += 5;  signals.append(("GDP极度低迷", f"{gdp:.1f}%"))
        elif gdp < 1.5:
            score += 3;  signals.append(("GDP增速低迷", f"{gdp:.1f}%"))

    umcsent = indicators.get("UMCSENT", {}).get("value")
    if umcsent is not None:
        if umcsent < 55:
            score += 4; signals.append(("消费者信心极低", f"{umcsent:.0f}"))
        elif umcsent < 65:
            score += 2; signals.append(("消费者信心偏低", f"{umcsent:.0f}"))

    # ── 修正上限 ────────────────────────────────────────────────────────────
    score = min(score, 100)

    if score >= 80:   label = "极端"
    elif score >= 65: label = "严重"
    elif score >= 50: label = "高"
    elif score >= 35: label = "较高"
    elif score >= 20: label = "中等"
    elif score >= 8:  label = "低"
    else:             label = "极低"

    return label, score, signals


def score_inflation_risk(indicators: Dict) -> Tuple[str, int, List[Tuple[str, float]]]:
    """通胀风险评分（0-100），信号计数法（每个信号+1）。

    信号触发阈值：
      CPI同比 > 3%（偏高）/ > 5%（高位）
      核心PCE > 3%
      油价 > 100美元/桶
      M2同比 > 7%（货币超发，领先通胀约12个月）
      PPI-CPI利差 > 5ppt（上游通胀压力尚未传导至消费端）
      10Y实际利率 < 0（货币政策实质宽松，无法压制通胀）

    评分映射：0信号→5分，6+信号→95分（线性近似）
    """
    signals = []

    # CPI同比
    cpi = indicators.get("CPIAUCSL", {}).get("value")
    if cpi is not None:
        if cpi > 5:
            signals.append(("CPI高位", cpi))
        elif cpi > 3:
            signals.append(("CPI偏高", cpi))

    # 核心PCE（同比）
    pce = indicators.get("PCEPI", {}).get("value")
    if pce is not None and pce > 3:
        signals.append(("核心PCE偏高", f"{pce:.1f}%"))

    # 油价
    oil = indicators.get("DCOILWTICO", {}).get("value")
    if oil is not None and oil > 100:
        signals.append(("油价高企", oil))

    # M2同比：超过7%意味着货币超发，通胀压力积聚
    m2 = indicators.get("M2SL", {}).get("value")
    if m2 is not None and m2 > 7:
        signals.append(("M2超速扩张", f"{m2:.1f}%"))

    # PPI-CPI利差异常（PPI比CPI高5ppt以上表示上游压力未传导）
    ppi = indicators.get("PPIACO", {}).get("value")
    if ppi is not None and cpi is not None and (ppi - cpi) > 5:
        signals.append(("PPI-CPI利差过大", f"{ppi-cpi:.1f}ppt（待传导）"))

    # 10Y实际利率（负实际利率→货币政策实质宽松→通胀压力无对冲）
    dfii10 = indicators.get("DFII10", {}).get("value")
    dff = indicators.get("DFF", {}).get("value") or indicators.get("FEDFUNDS", {}).get("value")
    if dfii10 is not None:
        if dfii10 < 0:
            signals.append(("实际利率为负（货币政策宽松）", f"DFII10={dfii10:.2f}%"))
    elif dff is not None and cpi is not None:
        implied_real = dff - cpi
        if implied_real < 0:
            signals.append(("实际利率为负（名义）", f"FFR{dff:.2f}%-CPI{cpi:.2f}%={implied_real:+.2f}ppt"))

    n = len(signals)
    # HYP-9: 不用 min(n,6) 截断，显式处理 n>6 以便未来扩展信号时能正确区分
    risk_map = {
        0: ("极低", 5),
        1: ("低", 15),
        2: ("中等", 35),
        3: ("较高", 55),
        4: ("高", 75),
        5: ("严重", 90),
        6: ("极度严重", 95),
    }
    label, score = risk_map.get(n, ("极端", 98))
    return label, score, signals


# =========================
# 中国风险评分
# =========================

def score_china_recession_risk(indicators: Dict) -> Tuple[str, int, List[Tuple[str, float]]]:
    """
    中国经济衰退风险评分（0-100）v2。
    改为加权评分系统（各维度权重不同），新增PPI通缩、泰勒缺口信号。
    """
    signals = []
    score = 0
    max_score = 0

    # 1. 制造业PMI（前瞻性最强，权重最高）
    pmi = indicators.get("pmi_mfg", {}).get("value")
    max_score += 20
    if pmi is not None:
        if pmi < 47:
            score += 20; signals.append(("PMI深度收缩", f"{pmi:.1f}"))
        elif pmi < 48.5:
            score += 14; signals.append(("PMI明显收缩", f"{pmi:.1f}"))
        elif pmi < 50:
            score += 7;  signals.append(("PMI轻度收缩", f"{pmi:.1f}"))

    # 2. 综合PMI（服务业+制造业合成）
    pmi_c = indicators.get("pmi_composite", {}).get("value")
    max_score += 8
    if pmi_c is not None and pmi_c < 50:
        score += 8; signals.append(("综合PMI收缩", f"{pmi_c:.1f}"))

    # 3. GDP增速（与5%目标对比）
    gdp = indicators.get("gdp_growth", {}).get("value")
    max_score += 20
    if gdp is not None:
        if gdp < 3.5:
            score += 20; signals.append(("GDP严重低于目标", f"{gdp:.1f}%"))
        elif gdp < 4.0:
            score += 14; signals.append(("GDP显著低于目标", f"{gdp:.1f}%"))
        elif gdp < 4.5:
            score += 8;  signals.append(("GDP低于目标", f"{gdp:.1f}%"))

    # 4. CPI通缩/接近零（需求不足信号）
    cpi = indicators.get("cpi", {}).get("value")
    max_score += 12
    if cpi is not None:
        if cpi < -1.0:
            score += 12; signals.append(("CPI严重通缩", f"{cpi:.1f}%"))
        elif cpi < 0:
            score += 8;  signals.append(("CPI通缩", f"{cpi:.1f}%"))
        elif cpi < 0.5:
            score += 4;  signals.append(("CPI接近通缩", f"{cpi:.1f}%"))

    # 5. PPI深度通缩（企业盈利压缩，债务通缩前兆）
    ppi = indicators.get("ppi", {}).get("value")
    max_score += 12
    if ppi is not None:
        if ppi < -3:
            score += 12; signals.append(("PPI深度通缩", f"{ppi:.1f}%"))
        elif ppi < -1:
            score += 8;  signals.append(("PPI通缩", f"{ppi:.1f}%"))
        elif ppi < 0:
            score += 4;  signals.append(("PPI负增长", f"{ppi:.1f}%"))

    # 6. M2增速（信贷脉冲代理）
    m2 = indicators.get("m2_growth", {}).get("value")
    max_score += 10
    if m2 is not None:
        if m2 < 5:
            score += 10; signals.append(("M2增速极低(<5%)", f"{m2:.1f}%"))
        elif m2 < 7:
            score += 6;  signals.append(("M2增速偏低", f"{m2:.1f}%"))

    # 7. 工业增加值（实体经济同步指标）
    iva = indicators.get("industrial_va", {}).get("value")
    max_score += 10
    if iva is not None:
        if iva < 1.0:
            score += 10; signals.append(("工业增加值衰退", f"{iva:.1f}%"))
        elif iva < 3.0:
            score += 6;  signals.append(("工业增加值低迷", f"{iva:.1f}%"))

    # 8. 泰勒规则缺口（货币政策相对过紧信号）
    # HYP-7: cn_lpr_proxy 从 indicators 读取，默认 3.10（2024年基准），注意 LPR 每次调整后需更新默认值
    if cpi is not None and gdp is not None:
        cn_lpr_proxy = indicators.get("cn_lpr", {}).get("value") or 3.10  # fallback=3.10（2024-05基准）
        cn_taylor = 2.5 + 1.5 * (cpi - 2.0) + 0.5 * (gdp - 5.0)
        taylor_gap = cn_lpr_proxy - cn_taylor
        max_score += 8
        if taylor_gap > 3.0:
            score += 8;  signals.append(("泰勒缺口极大(货币过紧)", f"+{taylor_gap:.1f}ppt"))
        elif taylor_gap > 1.5:
            score += 5;  signals.append(("泰勒缺口较大(货币偏紧)", f"+{taylor_gap:.1f}ppt"))

    # 标准化到0-100
    final_score = int(score / max_score * 100) if max_score > 0 else 5
    final_score = min(final_score, 100)

    if final_score >= 80:   label = "极高"
    elif final_score >= 65: label = "高"
    elif final_score >= 50: label = "较高"
    elif final_score >= 35: label = "中等"
    elif final_score >= 20: label = "较低"
    elif final_score >= 10: label = "低"
    else:                   label = "极低"

    return label, final_score, signals


def score_china_inflation_risk(indicators: Dict) -> Tuple[str, int, List[Tuple[str, float]]]:
    """
    中国价格风险评分（0-100）v2：通胀+通缩双向评估，加权评分系统。
    新增：PPI-CPI剪刀差分析、M2-通胀背离信号。
    """
    cpi = indicators.get("cpi", {}).get("value")
    ppi = indicators.get("ppi", {}).get("value")
    m2  = indicators.get("m2_growth", {}).get("value")
    gdp = indicators.get("gdp_growth", {}).get("value")

    # ── 通胀信号（供给推动/需求拉动）───────────────────────────────────────
    inf_score = 0
    inf_max = 0
    inf_signals = []

    inf_max += 15
    if cpi is not None:
        if cpi > 5:
            inf_score += 15; inf_signals.append(("CPI高位", f"{cpi:.1f}%"))
        elif cpi > 3:
            inf_score += 10; inf_signals.append(("CPI偏高", f"{cpi:.1f}%"))
        elif cpi > 2.5:
            inf_score += 5

    inf_max += 15
    if ppi is not None:
        if ppi > 8:
            inf_score += 15; inf_signals.append(("PPI严重通胀", f"{ppi:.1f}%"))
        elif ppi > 5:
            inf_score += 10; inf_signals.append(("PPI高通胀", f"{ppi:.1f}%"))
        elif ppi > 3:
            inf_score += 5; inf_signals.append(("PPI偏高", f"{ppi:.1f}%"))

    inf_max += 10
    if m2 is not None and m2 > 12:
        inf_score += 10; inf_signals.append(("M2过高", f"{m2:.1f}%"))
    elif m2 is not None and m2 > 10:
        inf_score += 5

    # PPI-CPI剪刀差（PPI>CPI+5：上游通胀将向下游传导）
    inf_max += 10
    if ppi is not None and cpi is not None and ppi > cpi + 5:
        inf_score += 10; inf_signals.append(("PPI-CPI剪刀差", f"PPI{ppi:.1f}% vs CPI{cpi:.1f}%"))
    elif ppi is not None and cpi is not None and ppi > cpi + 3:
        inf_score += 5; inf_signals.append(("PPI-CPI差扩大", f"差{ppi-cpi:.1f}ppt"))

    # ── 通缩信号（需求不足/债务通缩）────────────────────────────────────────
    def_score = 0
    def_max = 0
    def_signals = []

    def_max += 20
    if cpi is not None:
        if cpi < -1.5:
            def_score += 20; def_signals.append(("CPI严重通缩", f"{cpi:.1f}%"))
        elif cpi < 0:
            def_score += 14; def_signals.append(("CPI通缩", f"{cpi:.1f}%"))
        elif cpi < 1.0:
            def_score += 7;  def_signals.append(("CPI接近通缩", f"{cpi:.1f}%"))

    def_max += 18
    if ppi is not None:
        if ppi < -4:
            def_score += 18; def_signals.append(("PPI深度通缩", f"{ppi:.1f}%"))
        elif ppi < -2:
            def_score += 12; def_signals.append(("PPI通缩", f"{ppi:.1f}%"))
        elif ppi < 0:
            def_score += 6;  def_signals.append(("PPI负增长", f"{ppi:.1f}%"))

    def_max += 12
    if m2 is not None and m2 < 7:
        def_score += 12; def_signals.append(("M2增速极低", f"{m2:.1f}%"))
    elif m2 is not None and m2 < 9:
        def_score += 6;  def_signals.append(("M2增速偏低", f"{m2:.1f}%"))

    # GDP低于目标时叠加通缩信号（需求驱动）
    def_max += 10
    if gdp is not None and gdp < 4.0 and cpi is not None and cpi < 1:
        def_score += 10; def_signals.append(("低增长+低通胀(类日本化)", f"GDP{gdp:.1f}%+CPI{cpi:.1f}%"))

    # ── 选择风险方向 ──────────────────────────────────────────────────────
    inf_pct = (inf_score / inf_max * 100) if inf_max > 0 else 0
    def_pct = (def_score / def_max * 100) if def_max > 0 else 0

    if def_pct > inf_pct:
        final_score = int(def_pct)
        signals = def_signals
        risk_type = "通缩"
    else:
        final_score = int(inf_pct)
        signals = inf_signals
        risk_type = "通胀"

    final_score = min(final_score, 100)

    if final_score >= 80:   label = "极高"
    elif final_score >= 65: label = "高"
    elif final_score >= 50: label = "较高"
    elif final_score >= 35: label = "中等"
    elif final_score >= 20: label = "较低"
    elif final_score >= 10: label = "低"
    else:                   label = "极低"

    if risk_type == "通缩" and final_score >= 10:
        label = f"通缩{label}"
    elif risk_type == "通胀" and final_score >= 10:
        label = f"通胀{label}"

    return label, final_score, signals


# =========================
# 中国历史危机数据
# =========================

CHINA_CRISES = [
    {"name": "2015A股股灾", "year": 2015,
     "gdp_growth": 7.0, "cpi": 1.4, "pmi_mfg": 49.8, "m2_growth": 13.3, "ppi": -4.8,
     "trigger": "杠杆资金出清 + 估值泡沫"},
    {"name": "2018去杠杆", "year": 2018,
     "gdp_growth": 6.7, "cpi": 2.1, "pmi_mfg": 50.0, "m2_growth": 8.1, "ppi": 3.5,
     "trigger": "资管新规 + 信用收缩"},
    {"name": "2020新冠疫情", "year": 2020,
     "gdp_growth": 2.3, "cpi": 2.5, "pmi_mfg": 51.9, "m2_growth": 10.1, "ppi": -1.8,
     "trigger": "疫情冲击 + 供应链断裂"},
    {"name": "2022房地产危机", "year": 2022,
     "gdp_growth": 3.0, "cpi": 2.0, "pmi_mfg": 49.0, "m2_growth": 11.8, "ppi": 4.1,
     "trigger": "房企违约 + 封控叠加"},
    {"name": "2023后疫情通缩", "year": 2023,
     "gdp_growth": 5.2, "cpi": 0.2, "pmi_mfg": 49.4, "m2_growth": 9.7, "ppi": -3.0,
     "trigger": "内需不足 + PPI持续通缩 + 房地产后遗症"},
    {"name": "2026通缩滞缓", "year": 2026,
     "gdp_growth": 4.6, "cpi": -0.1, "pmi_mfg": 49.5, "m2_growth": 7.0, "ppi": -1.5,
     "trigger": "外需压制（关税）+ 内需不振 + 货币政策传导失效"},
]


def match_china_crisis(indicators: Dict) -> List[Tuple[str, float]]:
    """
    匹配中国历史危机情景 v2。
    新增PPI维度，对GDP和PMI给予更高权重（更前瞻）。
    """
    # 各维度权重（总和 = 1.0）
    WEIGHTS = {
        "gdp_growth": 0.30,
        "pmi_mfg":    0.25,
        "cpi":        0.20,
        "ppi":        0.15,
        "m2_growth":  0.10,
    }
    matches = []
    for crisis in CHINA_CRISES:
        weighted_score = 0.0
        weight_used = 0.0
        for key, wt in WEIGHTS.items():
            current = indicators.get(key, {}).get("value")
            hist = crisis.get(key)
            if current is None or hist is None:
                continue
            diff = abs(current - hist)
            # 渐进相似度（1.0 = 完全一致，0.0 = 差距≥6）
            similarity = max(0.0, 1.0 - diff / 6.0)
            weighted_score += similarity * wt
            weight_used += wt
        if weight_used > 0:
            pct = weighted_score / weight_used * 100
            matches.append((crisis["name"], round(pct, 1), crisis["trigger"]))
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches


# =========================
# 美国历史危机匹配（依赖 CRISIS_CSV）
# =========================

def _parse_pct(val) -> Optional[float]:
    """解析百分比字符串，如'~-30%', '24.9%@1933Q2', '22.6%@1天' → 提取数字"""
    if pd.isna(val):
        return None
    s = str(val).strip()
    # 去掉前缀 ~
    s = s.lstrip('~')
    # 提取@前面的数字部分
    if '@' in s:
        s = s.split('@')[0]
    # 去掉%号
    s = s.replace('%', '')
    try:
        return float(s)
    except ValueError:
        return None


def match_crisis(indicators: Dict) -> List[Tuple[str, float, str]]:
    """根据当前指标数值匹配最接近的历史危机（多维度相似度评分）"""
    try:
        df = pd.read_csv(CRISIS_CSV)

        # 提取当前指标
        unrate = indicators.get("UNRATE", {}).get("value")
        gdp_yoy = indicators.get("GDPC1", {}).get("value")  # 已经是YoY%
        sp500 = indicators.get("SP500", {}).get("value")
        t10y2y = indicators.get("T10Y2Y", {}).get("value")
        cpi_yoy = indicators.get("CPIAUCSL", {}).get("value")  # 已经是YoY%
        ppi_yoy = indicators.get("PPIACO", {}).get("value")    # PPI同比%
        oil = indicators.get("DCOILWTICO", {}).get("value")
        baa10y = indicators.get("BAA10Y", {}).get("value")

        scores = []
        for _, row in df.iterrows():
            total_score = 0
            max_score = 0
            reasons = []

            # === 1. 失业率维度 (权重25) ===
            crisis_unemp = _parse_pct(row.get("unemp_peak_pct"))
            if unrate is not None and crisis_unemp is not None:
                max_score += 25
                if unrate > 6:
                    closeness = max(0, 1 - abs(unrate - crisis_unemp) / crisis_unemp)
                    total_score += 25 * closeness
                    if closeness > 0.5:
                        reasons.append(f"失业率{unrate:.1f}%接近{row['crisis']}峰值{crisis_unemp:.1f}%")
                elif unrate > 4.5 and crisis_unemp > 6:
                    # 失业率偏高但危机峰值更高→部分匹配（早期阶段）
                    total_score += 8
                    reasons.append(f"失业率{unrate:.1f}%偏高，{row['crisis']}峰值{crisis_unemp:.1f}%")
                else:
                    # HYP-8: 低失业率不代表无风险（危机初期常见），按反向接近度给基础分
                    # 当前失业率越低，越接近"繁荣期埋雷"型危机的起始状态
                    low_unemp_closeness = max(0, 1 - unrate / max(crisis_unemp, 1))
                    if low_unemp_closeness > 0.3 and crisis_unemp <= 5:
                        total_score += 5 * low_unemp_closeness
                        reasons.append(f"失业率{unrate:.1f}%低位，类似{row['crisis']}爆发前状态")

            # === 2. GDP维度 (权重25) ===
            crisis_gdp = _parse_pct(row.get("gdp_peak_trough_pct"))
            if gdp_yoy is not None and crisis_gdp is not None:
                max_score += 25
                # GDP增速低/负→匹配深度衰退危机
                if gdp_yoy < 1:
                    # 接近衰退，匹配GDP跌幅大的危机
                    severity = min(abs(crisis_gdp) / 30, 1.0)  # 30%为最严重
                    total_score += 25 * severity
                    reasons.append(f"GDP增速{gdp_yoy:.1f}%低迷，{row['crisis']}曾跌{crisis_gdp:.0f}%")
                elif gdp_yoy < 3:
                    # 增长放缓→匹配中等衰退危机
                    severity = min(abs(crisis_gdp) / 30, 1.0) * 0.3
                    total_score += 25 * severity

            # === 3. 股市维度 (权重20) ===
            crisis_sp = _parse_pct(row.get("sp500_drawdown_pct"))
            if sp500 is not None and crisis_sp is not None:
                max_score += 20
                # S&P500处于高位时，匹配有大幅回撤的危机（泡沫特征）
                if sp500 > 5000 and crisis_sp > 40:
                    total_score += 12
                    reasons.append(f"标普高位{sp500:.0f}，{row['crisis']}曾回撤{crisis_sp:.0f}%")

            # === 4. 利差/信用维度 (权重15) ===
            if t10y2y is not None and crisis_gdp is not None:
                max_score += 15
                # 利差倒挂→匹配衰退型危机（T10Y2Y单位：%，倒挂为负值）
                if t10y2y < 0:
                    severity = min(abs(crisis_gdp) / 30, 1.0)
                    total_score += 15 * severity
                    reasons.append(f"利差倒挂{t10y2y:.2f}%，衰退前兆")
                elif t10y2y < 0.5:
                    # 利差极窄（<50bp），衰退早期预警
                    total_score += 5

            # === 5. 通胀维度 (权重15) ===
            crisis_type = str(row.get("type", ""))
            if cpi_yoy is not None:
                max_score += 15
                # 高通胀→匹配滞胀型危机（2022急加息/2026油价财政双压）
                if cpi_yoy > 5 and "滞胀" in crisis_type:
                    total_score += 15
                    reasons.append(f"CPI {cpi_yoy:.1f}%高通胀，匹配{row['crisis']}滞胀特征")
                elif cpi_yoy > 3 and "滞胀" in crisis_type:
                    total_score += 8
                    reasons.append(f"CPI {cpi_yoy:.1f}%偏高，类似{row['crisis']}早期")

            # === 5.5 PPI维度 (权重8) — 上游价格压力，强化滞胀匹配 ===
            if ppi_yoy is not None and cpi_yoy is not None:
                max_score += 8
                if ppi_yoy > 8 and "滞胀" in crisis_type:
                    # PPI极高（>8%）且滞胀类型 → 强烈上游价格冲击，最大得分
                    total_score += 8
                    reasons.append(f"PPI {ppi_yoy:.1f}%极高，上游通胀压力待传导")
                elif ppi_yoy > 5 and "滞胀" in crisis_type:
                    total_score += 5
                    reasons.append(f"PPI {ppi_yoy:.1f}%偏高，供给侧成本压力")
                elif ppi_yoy > 3 and cpi_yoy < ppi_yoy - 3 and "滞胀" in crisis_type:
                    # PPI-CPI剪刀差大→传导延迟压力
                    total_score += 3

            # === 5.8 油价维度 (权重8) — 能源供给冲击 ===
            if oil is not None:
                max_score += 8
                if oil > 100 and ("滞胀" in crisis_type or "供给" in crisis_type):
                    # 油价>100 + 滞胀/供给冲击类型 → 强匹配
                    intensity = min((oil - 100) / 30, 1.0)  # 100→0, 130→满分
                    total_score += 8 * intensity
                    if oil > 110:
                        reasons.append(f"WTI {oil:.0f}$/桶，能源供给冲击叠加")
                elif oil > 80 and "供给" in crisis_type:
                    total_score += 3

            # === 6. 信用利差 ===
            if baa10y is not None:
                max_score += 10
                if baa10y > 3 and crisis_gdp is not None and abs(crisis_gdp) > 10:
                    total_score += 10
                    reasons.append(f"信用利差{baa10y:.1f}%扩大，类似{row['crisis']}")
                elif baa10y > 2 and crisis_gdp is not None and abs(crisis_gdp) > 5:
                    total_score += 4

            # 归一化得分（0-100）
            normalized = (total_score / max_score * 100) if max_score > 0 else 0
            scores.append((row.get("crisis", "未知"), round(normalized, 1), "; ".join(reasons) or "无显著匹配"))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:3]  # 返回前3个最匹配的

    except Exception as e:
        print(f"  [危机匹配] 失败: {e}")
        return []
