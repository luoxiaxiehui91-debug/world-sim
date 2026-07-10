"""
P1: FRED data fetcher - 使用 requests 而非 fredapi
每次获取1个序列，立即保存CSV
"""
import requests
import pandas as pd
import os
import sys
import time
import urllib.parse

FRED_API_KEY = "a3f1dc8fca52b0a45e320ea0383bbac7"
MAX_RETRIES = 3
RETRY_DELAY = 5
BASE = "C:/Users/luoxi/.qclaw/workspace-knjrc5n1o4zjzm5o/docs/财经知识库/02_核心变量因果链"

SERIES = [
    ("DFF",  "Fed Funds Rate",          "%"),
    ("DGS2", "2Y Treasury",             "%"),
    ("DGS5", "5Y Treasury",             "%"),
    ("DGS10","10Y Treasury",            "%"),
    ("DGS30","30Y Treasury",            "%"),
    ("T10Y2Y","10Y-2Y Spread",         "%"),
    ("T10Y3M","10Y-3M Spread",         "%"),
    ("MORTGAGE30US","30Y Mortgage",     "%"),
    ("BAA10Y","BAA Spread",            "%"),
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
    ("ICSA","Initial Jobless Claims",   "千人/周"),
    ("JTSJOL","Job Openings",         "千"),
    ("AWHMAN","Avg Weekly Hours",       "小时"),
    ("M2SL","M2 Money Supply",        "十亿美元"),
    ("TOTALSL","Total Consumer Credit", "十亿美元"),
    ("BUSLOANS","Commercial Loans",    "十亿美元"),
    ("SP500","S&P 500",                "指数"),
    ("CSUSHPINSA","Case-Shiller HPI", "2000=100"),
    ("DCOILWTICO","WTI Oil",          "$/桶"),
    ("GOLDAMGBD228NLBM","Gold",       "$/盎司"),
    ("PCE","Personal Consumption",    "十亿美元"),
    ("UMCSENT","Consumer Sentiment",   "1966Q1=100"),
    ("RSXFS","Retail Sales",           "百万美元"),
    ("MANEMP","ISM Mfg PMI",           "指数"),
    ("INDPRO","Industrial Production",  "2017=100"),
    ("HOUST","Housing Starts",         "千套"),
    ("PERMIT","Building Permits",      "千套"),
    ("DEXCHUS","USD/CNY",             "人民币"),
    ("DEXUSEU","USD/EUR",             "欧元"),
    ("DXY","USD Index",                "指数"),
    ("DEXJPUS","USD/JPY",             "日元"),
]

def fetch_fred(series_id, limit=100000):
    encoded_id = urllib.parse.quote(series_id)
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={encoded_id}&api_key={FRED_API_KEY}"
           f"&file_type=json&limit={limit}")
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 429:
                # Rate limited - retry after delay
                wait = RETRY_DELAY * (attempt + 1)
                print(f"(rate limited, wait {wait}s...)", end=" ", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            obs = data.get("observations", [])
            if not obs:
                return None
            df = pd.DataFrame(obs)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").drop(columns=["realtime_start", "realtime_end"])
            # Handle period in series_id (pandas splits 'DGS10' into 'DGS'.'10')
            col_to_use = series_id if series_id in df.columns else df.columns[0]
            df[series_id] = pd.to_numeric(df[col_to_use], errors="coerce")
            return df[series_id]
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise
    return None


if len(sys.argv) > 1:
    idx = int(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 3
else:
    print("Usage: python fetch_fred_req.py <start_idx> <count>")
    sys.exit(0)

start = idx
end = min(idx + size, len(SERIES))
ok_count = 0

for i in range(start, end):
    sid, name, unit = SERIES[i]
    csv_path = f"{BASE}/series_{sid}.csv"
    if os.path.exists(csv_path):
        print(f"{sid}... ALREADY EXISTS")
        continue
    print(f"{sid} ({name})...", end=" ", flush=True)
    try:
        df = fetch_fred(sid)
        if df is not None and len(df) > 0:
            df_out = df.to_frame(name=sid)
            df_out.index.name = "date"
            df_out.to_csv(csv_path)
            print(f"OK {len(df)} obs -> series_{sid}.csv")
            ok_count += 1
        else:
            print("EMPTY")
    except Exception as e:
        print(f"ERR: {e}")
    time.sleep(0.3)  # Rate limit protection

print(f"\nBatch {start}-{end}: fetched {ok_count} series")
