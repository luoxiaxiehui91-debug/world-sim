"""
P1: Batch 2 - 增长 + 通胀
"""
import fredapi
import pandas as pd

FRED_API_KEY = "a3f1dc8fca52b0a45e320ea0383bbac7"
fa = fredapi.Fred(api_key=FRED_API_KEY)
BASE = "C:/Users/luoxi/.qclaw/workspace-knjrc5n1o4zjzm5o/docs/财经知识库/02_核心变量因果链"

BATCH2 = {
    "GDPC1":    ("Real GDP",            "十亿美元"),
    "GDPPOT":   ("Potential GDP",       "十亿美元"),
    "CPIAUCSL": ("CPI",                "2017=100"),
    "PCECTPI":  ("PCE Price Index",    "2017=100"),
    "PPIFIS":   ("PPI Final Demand",   "1982=100"),
    "MICH":     ("Inflation Expectation", "%"),
    "PCEC":     ("Core PCE",           "2017=100"),
}

results = {}
for sid, (name, unit) in BATCH2.items():
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
    path = f"{BASE}/batch2_growth_inflation.csv"
    combined.to_csv(path)
    print(f"\nSaved {len(results)} series to {path}")
else:
    print("No data fetched")
