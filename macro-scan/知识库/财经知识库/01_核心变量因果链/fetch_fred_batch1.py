"""
P1: 结构化时序数据 - 分批获取FRED数据
Batch 1: 利率 + 利差
"""
import fredapi
import pandas as pd
import sys

FRED_API_KEY = "a3f1dc8fca52b0a45e320ea0383bbac7"
fa = fredapi.Fred(api_key=FRED_API_KEY)

BASE = "C:/Users/luoxi/.qclaw/workspace-knjrc5n1o4zjzm5o/docs/财经知识库/01_核心变量因果链"

BATCH1 = {
    "DFF":       ("Fed Funds Rate",      "%"),
    "DGS2":      ("2Y Treasury",        "%"),
    "DGS5":      ("5Y Treasury",        "%"),
    "DGS10":     ("10Y Treasury",       "%"),
    "DGS30":     ("30Y Treasury",       "%"),
    "T10Y2Y":    ("10Y-2Y Spread",      "%"),
    "T10Y3M":    ("10Y-3M Spread",      "%"),
    "MORTGAGE30US": ("30Y Mortgage",   "%"),
    "BAA10Y":    ("BAA Spread",         "%"),
    "AAA10Y":    ("AAA Spread",         "%"),
}

results = {}
for sid, (name, unit) in BATCH1.items():
    print(f"{sid}...", end=" ", flush=True)
    try:
        df = fa.get_series(sid)
        if df is not None and len(df) > 0:
            results[sid] = df
            print(f"OK({len(df)})")
        else:
            print("EMPTY")
    except Exception as e:
        print(f"ERR: {e}")

if results:
    combined = pd.DataFrame(results)
    combined.index.name = "date"
    path = f"{BASE}/batch1_rates.csv"
    combined.to_csv(path)
    print(f"\nSaved {len(results)} series to {path}")
else:
    print("No data fetched")
