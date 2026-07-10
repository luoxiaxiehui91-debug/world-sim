"""
P1: Merge all individual FRED series CSVs into one comprehensive database
"""
import os
import pandas as pd

BASE = r"C:\Users\luoxi\.qclaw\workspace-knjrc5n1o4zjzm5o\docs\财经知识库\01_核心变量因果链"

# Metadata: series_id -> (display_name, unit, category)
META = {
    "DFF":        ("Fed Funds Rate",         "%",    "利率"),
    "DGS2":       ("2Y Treasury Yield",       "%",    "利率"),
    "DGS5":       ("5Y Treasury Yield",       "%",    "利率"),
    "DGS10":      ("10Y Treasury Yield",      "%",    "利率"),
    "DGS30":      ("30Y Treasury Yield",       "%",    "利率"),
    "T10Y2Y":     ("10Y-2Y Spread",           "%",   "利率"),
    "T10Y3M":     ("10Y-3M Spread",           "%",    "利率"),
    "MORTGAGE30US":("30Y Mortgage Rate",       "%",   "利率"),
    "BAA10Y":     ("BAA Corporate Spread",    "%",    "利差"),
    "AAA10Y":     ("AAA Corporate Spread",    "%",    "利差"),

    "GDPC1":      ("Real GDP",               "十亿美元", "增长"),
    "GDPPOT":     ("Potential GDP",          "十亿美元", "增长"),

    "CPIAUCSL":   ("CPI All Items",          "2017=100","通胀"),
    "PCECTPI":    ("PCE Price Index",        "2017=100","通胀"),
    "PPIFIS":     ("PPI Final Demand",       "1982=100","通胀"),
    "MICH":       ("Inflation Expectations", "%",      "通胀"),
    "PCEC":       ("Core PCE",               "2017=100","通胀"),

    "UNRATE":     ("Unemployment Rate",      "%",     "就业"),
    "PAYEMS":     ("Nonfarm Payrolls",       "千人",   "就业"),
    "ICSA":       ("Initial Jobless Claims", "千人/周","就业"),
    "JTSJOL":     ("Job Openings",           "千",     "就业"),
    "AWHMAN":     ("Avg Weekly Hours Mfg",   "小时",   "就业"),

    "M2SL":       ("M2 Money Supply",        "十亿美元","货币"),
    "TOTALSL":    ("Total Consumer Credit",  "十亿美元","信贷"),
    "BUSLOANS":   ("Commercial Bank Loans",  "十亿美元","信贷"),

    "SP500":      ("S&P 500",                "指数",  "资产"),
    "CSUSHPINSA": ("Case-Shiller HPI",       "2000=100","资产"),
    "DCOILWTICO":("WTI Crude Oil",          "$/桶",   "大宗"),

    "PCE":        ("Personal Consumption",   "十亿美元","消费"),
    "UMCSENT":    ("Consumer Sentiment",     "1966Q1=100","消费"),
    "RSXFS":      ("Retail Sales",           "百万美元","消费"),

    "MANEMP":     ("ISM Manufacturing PMI", "指数",  "PMI"),
    "INDPRO":     ("Industrial Production", "2017=100","PMI"),

    "HOUST":      ("Housing Starts",         "千套",   "房屋"),
    "PERMIT":     ("Building Permits",       "千套",   "房屋"),

    "DEXCHUS":    ("USD/CNY Exchange Rate", "CNY",   "汇率"),
    "DEXUSEU":    ("USD/EUR Exchange Rate", "EUR",   "汇率"),
    "DEXJPUS":    ("USD/JPY Exchange Rate", "JPY",   "汇率"),
    "DTWEXBGS":   ("USD Broad Trade-Weighted Index","指数","汇率"),
}

# Load all series
series_files = sorted([f for f in os.listdir(BASE) if f.startswith("series_") and f.endswith(".csv")])

all_data = {}
summary = []

for fname in series_files:
    sid = fname.replace("series_", "").replace(".csv", "")
    path = os.path.join(BASE, fname)
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    col = df.columns[0]  # the series column
    all_data[sid] = df[col]
    
    meta = META.get(sid, ("Unknown", "?", "?"))
    summary.append({
        "series_id": sid,
        "name_en": meta[0],
        "unit": meta[1],
        "category": meta[2],
        "obs_count": len(df),
        "start": df.index.min().strftime("%Y-%m-%d"),
        "end": df.index.max().strftime("%Y-%m-%d"),
        "latest": round(float(df[col].iloc[-1]), 3) if pd.notna(df[col].iloc[-1]) else "",
        "latest_date": df.index[-1].strftime("%Y-%m-%d"),
    })

# Merge all into wide format
combined = pd.DataFrame(all_data)
combined.index.name = "date"
combined = combined.sort_index()

# Save combined database
db_path = f"{BASE}/时序数据库_USA_宏观.csv"
combined.to_csv(db_path)
print(f"Combined database: {len(combined)} rows x {len(combined.columns)} columns")
print(f"Saved to: {db_path}")

# Save summary
sum_df = pd.DataFrame(summary).sort_values("category")
sum_path = f"{BASE}/时序数据库_USA_摘要.csv"
sum_df.to_csv(sum_path, index=False)
print(f"Summary saved to: {sum_path}")

# Print summary by category
for cat in ["利率", "利差", "增长", "通胀", "就业", "货币", "信贷", "资产", "大宗", "消费", "PMI", "房屋", "汇率"]:
    subset = sum_df[sum_df["category"] == cat]
    if not subset.empty:
        print(f"\n=== {cat} ===")
        for _, row in subset.iterrows():
            print(f"  {row['series_id']:20s} {row['name_en']:30s} {row['obs_count']:6d} obs  "
                  f"[{row['start'][:4]} - {row['end'][:4]}]  最新: {row['latest']} ({row['latest_date']})")
