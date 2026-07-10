"""
P2: Extract key macro data around major historical crises from the timeseries database
"""
import pandas as pd
import os

BASE = r"C:\Users\luoxi\.qclaw\workspace-knjrc5n1o4zjzm5o\docs\财经知识库\01_核心变量因果链"
DB_PATH = f"{BASE}/时序数据库_USA_宏观.csv"

df = pd.read_csv(DB_PATH, index_col="date", parse_dates=True)

# Crisis windows (date range to look at)
# We want to capture: pre-crisis peak, crisis trough, recovery
CRISIS_WINDOWS = {
    "1929大萧条":         ("1928-01-01", "1939-12-31"),
    "1987黑色星期一":      ("1985-01-01", "1992-12-31"),
    "2000科网泡沫":       ("1998-01-01", "2003-12-31"),
    "2008金融海啸":       ("2005-01-01", "2012-12-31"),
    "2010欧债危机":       ("2008-01-01", "2014-12-31"),
    "2015A股股灾":        ("2013-01-01", "2017-12-31"),
    "2020新冠冲击":       ("2019-01-01", "2022-12-31"),
    "2022美联储急加息":   ("2021-01-01", "2024-12-31"),
}

# For each crisis, find the key metrics
def get_annual(series, year):
    """Get annual average or year-end value for a series"""
    if series not in df.columns:
        return None
    s = df[series].dropna()
    # Get annual average
    annual = s.resample("YE").mean()
    if year in annual.index:
        return round(annual[year], 3)
    return None

def get_peak_trough(series, window_start, window_end, metric="min"):
    """Get peak or trough value in a window"""
    if series not in df.columns:
        return None, None
    s = df[series].dropna()
    window = s[window_start:window_end]
    if len(window) == 0:
        return None, None
    if metric == "min":
        val = window.min()
    else:
        val = window.max()
    date = window.idxmin() if metric == "min" else window.idxmax()
    return round(val, 3), date.strftime("%Y-%m-%d")

# Key series for analysis
SERIES_MAP = {
    "GDPC1":   "实际GDP(十亿)",
    "UNRATE":  "失业率(%)",
    "CPIAUCSL":"CPI指数",
    "DGS10":   "10Y国债收益率(%)",
    "DGS2":    "2Y国债收益率(%)",
    "SP500":   "S&P500指数",
    "T10Y2Y":  "10Y-2Y利差(%)",
    "M2SL":    "M2货币供应(十亿)",
    "INDPRO":  "工业产出指数",
    "PAYEMS":  "非农就业(千)",
}

print("=" * 80)
print("P2: Major Historical Crises - Key Macro Data")
print("=" * 80)

results = {}
for crisis, (start, end) in CRISIS_WINDOWS.items():
    print(f"\n{'='*60}")
    print(f"Crisis: {crisis}")
    print(f"Window: {start} ~ {end}")
    print("-" * 60)
    
    data = {}
    for sid, desc in SERIES_MAP.items():
        if sid not in df.columns:
            print(f"  {desc}: NO DATA")
            continue
        s = df[sid].dropna()
        window = s[start:end]
        if len(window) == 0:
            print(f"  {desc}: NO DATA IN WINDOW")
            continue
        
        min_val, min_date = get_peak_trough(sid, start, end, "min")
        max_val, max_date = get_peak_trough(sid, start, end, "max")
        
        # Get pre-crisis level (first year average)
        pre = s[start:end].iloc[0]
        # Get crisis trough
        trough = min_val
        # Get end level
        end_val = s[start:end].iloc[-1]
        
        print(f"  {desc}:")
        print(f"    Pre-crisis:  {round(pre, 3) if pd.notna(pre) else 'N/A'}")
        print(f"    Trough(Min): {min_val} ({min_date})")
        print(f"    Peak(Max):   {max_val} ({max_date})")
        print(f"    End:         {round(end_val, 3) if pd.notna(end_val) else 'N/A'}")
        
        data[sid] = {
            "pre": round(pre, 3) if pd.notna(pre) else None,
            "trough": min_val,
            "trough_date": min_date,
            "peak": max_val,
            "peak_date": max_date,
            "end": round(end_val, 3) if pd.notna(end_val) else None,
        }
    
    results[crisis] = data

print("\n" + "=" * 80)
print("Summary Table")
print("=" * 80)
