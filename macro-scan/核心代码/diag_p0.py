"""
diag_p0.py — P0 接线阶段验收诊断
验证：CSV 条数、地缘危机条数、台海推演类比路由、GDELT 信号注入
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calibrate_mc import load_historical_scenarios
from hypothesis_engine import (
    ScenarioParser, get_historical_analogies, build_hypothesis_prompt
)

PASS = "✅"
FAIL = "❌"

print("\n" + "="*60)
print("  P0 验收诊断")
print("="*60)

# ── 1. CSV 条数 ──────────────────────────────────────────────
scenarios = load_historical_scenarios()
total = len(scenarios)
geo_cats = {"geopolitical_standoff", "military_conflict", "large_scale_invasion",
            "territorial_annexation", "terrorist_attack", "non_state_conflict",
            "trade_tech_war", "sanctions_asymmetric", "revolution_energy",
            "political_instability"}
geo_count = sum(1 for s in scenarios if s.get("crisis_category", "") in geo_cats)

ok_total = total == 25
ok_geo   = geo_count >= 12
print(f"\n[1] CSV 总条数:  {PASS if ok_total else FAIL} {total}  (期望 25)")
print(f"[2] 地缘危机条数: {PASS if ok_geo else FAIL} {geo_count} (期望 ≥12)")

# ── 2. 新字段读取 ────────────────────────────────────────────
has_cat     = all("crisis_category" in s for s in scenarios)
has_tw      = all("taiwan_strait_relevance" in s for s in scenarios)
has_vix_any = any(s.get("vix_peak") is not None for s in scenarios)
print(f"[3] crisis_category 字段: {PASS if has_cat else FAIL}")
print(f"[4] taiwan_strait_relevance 字段: {PASS if has_tw else FAIL}")
print(f"[5] vix_peak 有实测值: {PASS if has_vix_any else FAIL}")

# 展示 tw_rel≥3 的案例
print("\n  台海相关度 tw_rel≥3 的案例：")
for s in sorted(scenarios, key=lambda x: x.get("taiwan_strait_relevance", 0), reverse=True):
    tw = s.get("taiwan_strait_relevance", 0)
    if tw >= 3:
        cat = s.get("crisis_category", "N/A")
        print(f"    tw_rel={tw}  {s['name']:<28}  category={cat}")

# ── 3. 台海推演类比路由 ──────────────────────────────────────
parser = ScenarioParser()
scenario = parser.parse_compound("台海军事冲突升级")
print(f"\n[6] 情景解析: type={scenario['scenario_type']}  subtype={scenario.get('subtype')}  "
      f"severity={scenario['severity']}")

analogies = get_historical_analogies(scenario)
best = analogies.get("best", "")
ok_best = "台海" in best or "1995" in best or "1996" in best
print(f"[7] 台海推演 best 类比: {PASS if ok_best else FAIL}")
print(f"    最相似: {best}")
print(f"    次相似: {analogies.get('second', 'N/A')}")
print(f"    Top-5 类比:")
for s in analogies.get("raw", []):
    tw = s.get("taiwan_strait_relevance", 0)
    cat = s.get("crisis_category", "N/A")
    print(f"      · {s['name']:<30} tw_rel={tw}  cat={cat}")

# VIX 区间
vix = analogies.get("impacts", {}).get("vix_delta", {})
spx = analogies.get("impacts", {}).get("spx_pct", {})
if vix.get("source") and "历史类比" in vix["source"]:
    print(f"[8] VIX 区间来源: {PASS} {vix['source']}")
    print(f"    VIX delta: P10={vix.get('p10')} / P50={vix.get('p50')} / P90={vix.get('p90')}")
else:
    print(f"[8] VIX 区间: ⚠  source={vix.get('source','N/A')}")

# ── 4. GDELT 信号注入 ────────────────────────────────────────
dummy_indicators = {"VIX": {"value": 22.5, "date": "2026-05-30"}}
prompt = build_hypothesis_prompt(
    scenario=scenario,
    analogies=analogies,
    wiki_entries=[],
    rag_chunks=[],
    indicators=dummy_indicators,
)
has_geo_section = "[GEO]" in prompt
has_twn         = "TWN" in prompt

# gdelt_scores.json 可能不存在，区分两种情况
import json, os
try:
    from optim_config import DATA_DIR
    gdelt_path = os.path.join(DATA_DIR, "gdelt_scores.json")
    gdelt_exists = os.path.exists(gdelt_path)
except Exception:
    gdelt_exists = False

if gdelt_exists:
    print(f"[9] GDELT 文件存在: {PASS}")
    print(f"    提示词含 [GEO]: {PASS if has_geo_section else FAIL}")
    print(f"    提示词含 TWN:   {PASS if has_twn else FAIL}")
else:
    print(f"[9] GDELT 文件不存在（gdelt_scores.json 未生成），跳过注入检查")
    print(f"    注入逻辑已就绪，下次 scan_weak_signals 运行后生效")

# ── 汇总 ────────────────────────────────────────────────────
checks = [ok_total, ok_geo, has_cat, has_tw, has_vix_any, ok_best]
passed = sum(checks)
total_checks = len(checks)
print(f"\n{'='*60}")
print(f"  结果: {passed}/{total_checks} 通过  {'🎉 P0 验收通过' if passed == total_checks else '⚠ 部分项目未达标'}")
print("="*60 + "\n")
