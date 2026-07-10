"""
P1: FRED data fetcher - 每次获取1个序列，立即保存CSV
每次只运行3个系列，避免超时
"""
import fredapi
import pandas as pd
import os
import sys

FRED_API_KEY = "a3f1dc8fca52b0a45e320ea0383bbac7"
fa = fredapi.Fred(api_key=FRED_API_KEY)
BASE = "C:/Users/luoxi/.qclaw/workspace-knjrc5n1o4zjzm5o/docs/财经知识库/01_核心变量因果链"

SERIES = [
    ("DFF",  "Fed Funds Rate",          "%"),
    ("DGS2", "2Y Treasury",             "%"),
    ("DGS5", "5Y Treasury",             "%"),
    ("DGS10","10Y Treasury",            "%"),
    ("DGS30","30Y Treasury",            "%"),
    ("T10Y2Y","10Y-2Y Spread",          "%"),
    ("T10Y3M","10Y-3M Spread",          "%"),
    ("MORTGAGE30US","30Y Mortgage",     "%"),
    ("BAA10Y","BAA Spread",             "%"),
    ("AAA10Y","AAA Spread",             "%"),
    ("GDPC1","Real GDP",               "十亿美元"),
    ("GDPPOT","Potential GDP",         "十亿美元"),
    ("CPIAUCSL","CPI",                 "2017=100"),
    ("PCECTPI","PCE Price Index",      "2017=100"),
    ("PPIFIS","PPI Final Demand",      "1982=100"),
    ("MICH","Inflation Expectation",   "%"),
    ("PCEC","Core PCE",               "2017=100"),
    ("UNRATE","Unemployment Rate",     "%"),
    ("PAYEMS","Nonfarm Payrolls",      "千人"),
    ("ICSA","Initial Jobless Claims",  "千人/周"),
    ("JTSJOL","Job Openings",         "千"),
    ("AWHMAN","Avg Weekly Hours",      "小时"),
    ("M2SL","M2 Money Supply",         "十亿美元"),
    ("TOTALSL","Total Consumer Credit","十亿美元"),
    ("BUSLOANS","Commercial Loans",   "十亿美元"),
    ("SP500","S&P 500",               "指数"),
    ("CSUSHPINSA","Case-Shiller HPI", "2000=100"),
    ("DCOILWTICO","WTI Oil",         "$/桶"),
    ("GOLDAMGBD228NLBM","Gold",       "$/盎司"),
    ("PCE","Personal Consumption",    "十亿美元"),
    ("UMCSENT","Consumer Sentiment", "1966Q1=100"),
    ("RSXFS","Retail Sales",         "百万美元"),
    ("MANEMP","ISM Mfg PMI",         "指数"),
    ("INDPRO","Industrial Production","2017=100"),
    ("HOUST","Housing Starts",       "千套"),
    ("PERMIT","Building Permits",    "千套"),
    ("DEXCHUS","USD/CNY",           "人民币"),
    ("DEXUSEU","USD/EUR",           "欧元"),
    ("DXY","USD Index",             "指数"),
    ("DEXJPUS","USD/JPY",           "日元"),
]

if len(sys.argv) > 1:
    idx = int(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 3
else:
    print("Usage: python fetch_fred.py <start_idx> <count>")
    print("Example: python fetch_fred.py 0 3  (fetch first 3 series)")
    sys.exit(0)

start = idx
end = min(idx + size, len(SERIES))
results = {}

for i in range(start, end):
    sid, name, unit = SERIES[i]
    csv_path = f"{BASE}/series_{sid}.csv"
    if os.path.exists(csv_path):
        print(f"{sid}... ALREADY EXISTS (skip)")
        continue
    print(f"{sid}...", end=" ", flush=True)
    try:
        df = fa.get_series(sid)
        if df is not None and len(df) > 0:
            results[sid] = df
            # 立即保存
            df_out = df.to_frame(name=sid)
            df_out.index.name = "date"
            df_out.to_csv(csv_path)
            print(f"OK({len(df)}) saved to series_{sid}.csv")
        else:
            print("EMPTY")
    except Exception as e:
        print(f"ERR: {e}")

print(f"\nBatch {start}-{end}: fetched {len(results)} series")
