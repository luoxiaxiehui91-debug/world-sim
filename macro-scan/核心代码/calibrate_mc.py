"""
calibrate_mc.py — MC 历史校准脚本

将 MonteCarloV2 的预测与 13 条历史危机数据比对，检验模型参数合理性。

策略：
  1. 按严重程度将 13 条历史情景分为 4 档（极端/严重/中等/当前）
  2. 对每档构造代表性"危机前预警期"初始状态
  3. 运行 MC（12个月视野，5000条路径），记录衰退/深度衰退概率
  4. 与历史实际比对，输出校准表
  5. 给出参数调整建议

运行方式：
  python calibrate_mc.py          # 输出校准报告（控制台）
  python calibrate_mc.py --json   # 同时输出 data/mc_calibration.json
"""

import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monte_carlo_v2 import MonteCarloV2

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    _ws = os.environ.get("OPENCLAW_WORKSPACE",
                         os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR  = os.path.join(_ws, "data")
    WORKSPACE = _ws

KB_ROOT = os.environ.get("KB_ROOT") or os.path.join(WORKSPACE, "知识库")
CRISIS_CSV = os.path.join(
    KB_ROOT, "财经知识库",
    "02_核心变量因果链", "历史情景_量化指标.csv"
)


# ── 初始状态：代表"危机警示期"（危机开始前3-6个月的压力信号状态）─────────────────
STRESS_INITIAL_STATES = {
    "extreme": {
        # 1929大萧条 / 2008金融海啸 — 系统性危机开端
        "gdp_growth":    1.0,   # GDP减速但仍正增长
        "inflation":     4.5,   # 通胀已上行
        "unemployment":  6.5,   # 失业率初步抬升
        "fed_funds_rate":2.5,   # 利率仍高位或开始降
        "vix":          42.0,   # 恐慌情绪飙升
        "sp500_return": -15.0,  # 市场已大跌
        "china_gdp":     4.0,   # 中国受波及
    },
    "severe": {
        # 1973石油危机 / 1979沃尔克冲击 / 2020新冠 / 2000科网 / 2010欧债
        "gdp_growth":    0.8,
        "inflation":     5.5,
        "unemployment":  5.8,
        "fed_funds_rate":3.5,
        "vix":          32.0,
        "sp500_return":  -8.0,
        "china_gdp":     3.5,
    },
    "moderate": {
        # 1987黑色星期一 / 1998俄罗斯/LTCM / 2022急加息
        "gdp_growth":    1.8,
        "inflation":     3.5,
        "unemployment":  5.2,
        "fed_funds_rate":4.0,
        "vix":          26.0,
        "sp500_return":  -5.0,
        "china_gdp":     4.5,
    },
    "current": {
        # 2026油价财政双压 — 当前基准
        "gdp_growth":    2.0,
        "inflation":     3.7,
        "unemployment":  4.2,
        "fed_funds_rate":4.5,
        "vix":          20.0,
        "sp500_return":   5.0,
        "china_gdp":     4.8,
    },
}

# 按历史频率推算各档应有的衰退概率区间（基于 13 条数据的粗略基准）
EXPECTED_RECESSION_PROB = {
    "extreme":  (0.85, 1.00),  # 2/2 为最严重危机，应>85%
    "severe":   (0.65, 0.90),  # 7条严重危机，应65-90%
    "moderate": (0.30, 0.60),  # 3条中等/短暂，应30-60%
    "current":  (0.15, 0.45),  # 当前仍属压力积累期
}


def _parse_float(text: str) -> float | None:
    """从'~-3.2%@1974'这类文本中提取第一个数值（含负号和小数）"""
    if not text or text.strip() in ("-", "N/A", ""):
        return None
    m = re.search(r"-?\d+\.?\d*", text)
    return float(m.group()) if m else None


def _severity_bucket(sev: str) -> str:
    """将中文严重程度映射到 4 档"""
    if "最严重" in sev:
        return "extreme"
    if "区域" in sev:
        return "severe"
    if "严重" in sev and "短暂" not in sev:
        return "severe"
    if "V型" in sev:
        return "severe"
    if "短暂" in sev or "急加息" in sev:
        return "moderate"
    if "软着陆" in sev or "压力积累" in sev:
        return "current"
    return "moderate"


def load_historical_scenarios() -> list[dict]:
    """从 crisis_scenarios.csv 加载历史危机数据，按严重度分桶后返回结构化列表。"""
    rows = []
    with open(CRISIS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gdp   = _parse_float(row.get("gdp_peak_trough_pct", ""))
            unemp = _parse_float(row.get("unemp_peak_pct", ""))
            sp500 = _parse_float(row.get("sp500_drawdown_pct", ""))
            infl  = _parse_float(row.get("inflation_peak_pct", ""))
            rows.append({
                "name":     row["crisis"],
                "sev_raw":  row["severity"],
                "bucket":   _severity_bucket(row["severity"]),
                "gdp_drop": gdp,       # 实际 GDP 最大跌幅（%）
                "unemp":    unemp,     # 失业率峰值
                "sp500":    sp500,     # 股市最大回撤（%）
                "infl":     infl,      # 通胀峰值
                "lessons":  row.get("key_lessons", ""),
                "crisis_category":         row.get("crisis_category", ""),
                "taiwan_strait_relevance": int(row.get("taiwan_strait_relevance", 0) or 0),
                "vix_peak": _parse_float(row.get("vix_peak", "")),
            })
    return rows


def run_calibration(n_paths: int = 5000, horizon: int = 12) -> dict:
    """对 extreme/severe/moderate/current 四个压力档运行 MC 模拟，返回各档概率与 GDP 分布。"""
    mc = MonteCarloV2(model="garch_jump", n_paths=n_paths, horizon=horizon, seed=42)

    results = {}
    for bucket, state in STRESS_INITIAL_STATES.items():
        r = mc.run(state)
        probs = r["probabilities"]
        results[bucket] = {
            "initial_state":       state,
            "mc_recession":        round(probs["recession"], 3),
            "mc_deep_recession":   round(probs["deep_recession"], 3),
            "mc_soft_landing":     round(probs["soft_landing"], 3),
            "mc_stagflation":      round(probs["stagflation"], 3),
            "mc_crisis_vix":       round(probs["crisis_vix"], 3),
            "gdp_median":          round(r["gdp_growth"]["median"], 2),
            "gdp_p10":             round(r["gdp_growth"]["p10"], 2),
            "gdp_p90":             round(r["gdp_growth"]["p90"], 2),
            "unemp_median":        round(r["unemployment"]["median"], 2),
        }
    return results


def _in_range(val: float, lo: float, hi: float) -> str:
    """检查 val 是否在 [lo, hi] 区间，返回含箭头和实测值的格式化字符串（✓/↑高/↓低）。"""
    if val < lo:
        return f"↓低  (期望{lo:.0%}-{hi:.0%}, 实测{val:.0%})"
    if val > hi:
        return f"↑高  (期望{lo:.0%}-{hi:.0%}, 实测{val:.0%})"
    return f"✓    (期望{lo:.0%}-{hi:.0%}, 实测{val:.0%})"


def _calibration_diagnostics(mc_results: dict) -> list[str]:
    """识别需要关注的参数并给出建议"""
    from monte_carlo_v2 import PARAMS

    notes = []
    buckets = ["extreme", "severe", "moderate", "current"]
    probs = [mc_results[b]["mc_recession"] for b in buckets]

    # 1. 核心单位错误检测：跳跃参数与变量单位不一致
    unit_errors = []
    for var, threshold in [("gdp_growth", 0.1), ("unemployment", 0.1),
                            ("inflation", 0.1), ("china_gdp", 0.1)]:
        p = PARAMS[var]
        if abs(p["mu_jump"]) < threshold and abs(p["mu"]) > 1.0:
            unit_errors.append(
                f"    {var}: mu_jump={p['mu_jump']}（变量单位=%，应为~±{abs(p['mu_jump'])*100:.1f}%）"
            )
    if unit_errors:
        notes.append(
            "⛔ 【严重】跳跃参数单位错误 — mu_jump/sigma_jump 使用了小数，"
            "但变量以百分比表示（如 gdp_growth mu=2.2 表示2.2%）。\n"
            "  受影响变量（当前值 → 建议修正值）：\n"
            + "\n".join(unit_errors) + "\n"
            "  修复方法（在 monte_carlo_v2.py 中调整 PARAMS）：\n"
            "    gdp_growth:  mu_jump -0.025 → -2.5,  sigma_jump 0.020 → 2.0\n"
            "    unemployment: mu_jump +0.025 → +2.5,  sigma_jump 0.015 → 1.5\n"
            "    inflation:   mu_jump +0.015 → +1.5,  sigma_jump 0.010 → 1.0\n"
            "    china_gdp:   mu_jump -0.030 → -3.0,  sigma_jump 0.020 → 2.0\n"
            "  此错误导致跳跃项幅度约为应有值的 1/100，是衰退概率严重低估的主因。"
        )

    # 2. 单调性检验
    if not (probs[0] > probs[1] > probs[2]):
        notes.append(f"⚠ 衰退概率单调性违反（极端{probs[0]:.0%} / 严重{probs[1]:.0%} / "
                     f"中等{probs[2]:.0%}），修复跳跃参数后应自动改善。")

    # 3. 整体水平检验（修复后才有意义）
    if not unit_errors:
        if probs[0] < 0.80:
            notes.append(f"⚠ extreme 档衰退概率仍偏低({probs[0]:.0%})，"
                         "可进一步增大 lambda_jump（当前=0.10）至 0.15。")
        if probs[2] > 0.65:
            notes.append(f"⚠ moderate 档衰退概率偏高({probs[2]:.0%})，"
                         "考虑降低 sigma 或 lambda_jump。")
        if probs[3] > 0.40:
            notes.append(f"⚠ 当前档衰退概率偏高({probs[3]:.0%})，检查当前初始状态设置。")

    if not notes:
        notes.append("✓ 所有诊断通过，模型参数与历史基准一致。")
    return notes


def print_report(mc_results: dict, scenarios: list[dict]) -> None:
    """打印完整校准报告：压力档位对比表、历史情景分组、参数诊断建议、PARAMS 当前值。"""
    sep = "═" * 66
    thin = "─" * 66

    print(f"\n{sep}")
    print("  蒙特卡洛历史校准报告")
    print(f"  模型：GARCH + 跳跃扩散 | 路径数：5000 | 视野：12个月")
    print(sep)

    # ── 压力档位校准表 ──────────────────────────────────────────
    print("\n【1】压力档位 MC 输出 vs 历史期望")
    print(f"  {'档位':<10} {'衰退概率':>9} {'深度衰退':>9} {'软着陆':>9} {'GDP中位':>9} {'GDP P10':>9}")
    print(f"  {thin}")
    bucket_zh = {"extreme":"极端", "severe":"严重", "moderate":"中等", "current":"当前"}
    for b in ["extreme", "severe", "moderate", "current"]:
        r = mc_results[b]
        lo, hi = EXPECTED_RECESSION_PROB[b]
        mark = "✓" if lo <= r["mc_recession"] <= hi else "⚠"
        print(f"  {bucket_zh[b]:<8}{mark}  {r['mc_recession']:>8.1%}  "
              f"{r['mc_deep_recession']:>8.1%}  {r['mc_soft_landing']:>8.1%}  "
              f"{r['gdp_median']:>8.1f}%  {r['gdp_p10']:>8.1f}%")

    print(f"\n  期望衰退概率区间：")
    for b in ["extreme", "severe", "moderate", "current"]:
        lo, hi = EXPECTED_RECESSION_PROB[b]
        print(f"    {bucket_zh[b]:<6} {lo:.0%}–{hi:.0%}  "
              f"→ {_in_range(mc_results[b]['mc_recession'], lo, hi)}")

    # ── 历史情景分组 ──────────────────────────────────────────────
    print(f"\n{thin}")
    print("\n【2】历史情景分组（GDP 实际最大跌幅）")
    for b in ["extreme", "severe", "moderate", "current"]:
        bucket_scens = [s for s in scenarios if s["bucket"] == b]
        if not bucket_scens:
            continue
        mc_rec = mc_results[b]["mc_recession"]
        mc_p10 = mc_results[b]["gdp_p10"]
        print(f"\n  [{bucket_zh[b]}档  衰退概率={mc_rec:.0%}  GDP P10={mc_p10:.1f}%]")
        for s in bucket_scens:
            gdp_str  = f"{s['gdp_drop']:+.1f}%" if s['gdp_drop'] is not None else "   N/A"
            sp_str   = f"{s['sp500']:+.1f}%"   if s['sp500'] is not None    else "   N/A"
            unemp_str= f"{s['unemp']:.1f}%"    if s['unemp'] is not None    else "  N/A"
            # 检查MC是否覆盖实际GDP跌幅
            cover = ""
            if s['gdp_drop'] is not None and mc_p10 is not None:
                cover = " ✓" if mc_p10 <= s['gdp_drop'] else " ⚠未覆盖"
            print(f"    · {s['name'][:16]:<18} GDP:{gdp_str:<9}"
                  f"失业:{unemp_str:<8}SP500:{sp_str}{cover}")

    # ── 诊断建议 ─────────────────────────────────────────────────
    print(f"\n{thin}")
    print("\n【3】参数校准诊断")
    for note in _calibration_diagnostics(mc_results):
        print(f"  {note}")

    # ── 参数参考表 ────────────────────────────────────────────────
    print(f"\n{thin}")
    print("\n【4】关键参数参考（PARAMS 当前值）")
    from monte_carlo_v2 import PARAMS
    for var in ["gdp_growth", "unemployment", "vix", "sp500_return"]:
        p = PARAMS[var]
        print(f"  {var:<18} mu={p['mu']:5.1f}  sigma={p['sigma']:5.2f}  "
              f"lambda_jump={p['lambda_jump']:.2f}  mu_jump={p['mu_jump']:+.4f}")

    print(f"\n{sep}\n")


def main():
    """CLI 入口：运行 MC 校准并打印报告，--json 可同时输出 JSON 文件。"""
    parser = argparse.ArgumentParser(description="MC 历史校准")
    parser.add_argument("--json", action="store_true", help="同时输出 JSON 报告")
    parser.add_argument("--paths", type=int, default=5000, help="MC 路径数（默认5000）")
    args = parser.parse_args()

    scenarios   = load_historical_scenarios()
    mc_results  = run_calibration(n_paths=args.paths)
    print_report(mc_results, scenarios)

    if args.json:
        out = {
            "mc_results": mc_results,
            "scenarios":  scenarios,
            "diagnostics": _calibration_diagnostics(mc_results),
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        out_path = os.path.join(DATA_DIR, "mc_calibration.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"[校准] JSON 已写入 {out_path}")


if __name__ == "__main__":
    main()
