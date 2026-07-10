"""
P1: 结构化时序数据 - 美国宏观经济指标
从 FRED 获取关键历史数据，输出为 CSV
"""
import fredapi
import pandas as pd

# FRED API Key
FRED_API_KEY = "a3f1dc8fca52b0a45e320ea0383bbac7"
fa = fredapi.Fred(api_key=FRED_API_KEY)

# 指标定义：(series_id, 名称, 单位, 频率)
INDICATORS = {
    # 增长
    "GDPPOT":    ("Real Potential GDP",         "十亿美元",    "q"),
    "GDPC1":     ("Real GDP",                   "十亿美元",    "q"),
    "CPAGR":     ("GDP Growth Rate",            "%",           "q"),

    # 通胀
    "CPIAUCSL":  ("CPI",                       "2017=100",    "m"),
    "PCECTPI":   ("PCE Price Index",           "2017=100",    "m"),
    "PPIACO":    ("PPI All Commodities",        "1982=100",    "m"),
    "CORESTICK": ("Core PCE",                  "2017=100",    "m"),

    # 就业
    "UNRATE":    ("Unemployment Rate",         "%",           "m"),
    "PAYEMS":    ("Nonfarm Payrolls",          "千人",         "m"),
    "ICSA":      ("Initial Jobless Claims",    "千人/周",      "w"),
    "JTSJOL":    ("Job Openings",              "千",           "m"),
    "LHUR":      ("Duration of Unemployment",  "周",           "m"),
    "AWHMAN":    ("Average Weekly Hours",       "小时",         "m"),
    "CES0500000003": ("Avg Hourly Earnings",  "$",            "m"),

    # 利率
    "DFF":       ("Fed Funds Rate",            "%",            "d"),
    "DGS2":      ("2Y Treasury",               "%",            "d"),
    "DGS5":      ("5Y Treasury",               "%",            "d"),
    "DGS10":     ("10Y Treasury",              "%",            "d"),
    "DGS30":     ("30Y Treasury",              "%",            "d"),
    "T10Y2Y":    ("10Y-2Y Spread",              "%",            "d"),
    "T10Y3M":    ("10Y-3M Spread",              "%",           "d"),

    # 货币与信贷
    "M2SL":      ("M2 Money Supply",            "十亿美元",    "w"),
    "TOTALSL":   ("Total Consumer Credit",     "十亿美元",    "m"),
    "BUSLOANS":  ("Commercial Bank Loans",      "十亿美元",    "m"),
    "MORTGAGE30US": ("30Y Mortgage Rate",      "%",            "w"),

    # 信用利差
    "BAA10Y":    ("BAA Corp Spread",           "%",            "d"),
    "AAA10Y":    ("AAA Corp Spread",           "%",            "d"),

    # 资产价格
    "SP500":     ("S&P 500",                   "指数",          "d"),
    "WILL5000PR":("Wilshire 5000",              "指数",          "d"),
    "CSUSHPINSA":("Case-Shiller Home Price",   "2000=100",    "m"),
    "DCOILWTICO":("WTI Oil Price",             "$/桶",          "d"),
    "GOLDAMGBD228NLBM": ("Gold Price",         "$/盎司",        "d"),

    # 消费与信心
    "PCE":       ("Personal Consumption",       "十亿美元",    "m"),
    "UMCSENT":   ("Consumer Sentiment",         "1966Q1=100",  "m"),
    "RSXFS":     ("Retail Sales",               "百万美元",    "m"),

    # 制造业
    "MANEMP":    ("ISM Manufacturing PMI",      "指数",          "m"),
    "INDPRO":    ("Industrial Production",       "2017=100",    "m"),

    # 房屋
    "HOUST":     ("Housing Starts",             "千套",           "m"),
    "PERMIT":    ("Building Permits",           "千套",           "m"),

    # 国际
    "DEXCHUS":   ("USD/CNY",                   "人民币",         "d"),
    "DEXUSEU":   ("USD/EUR",                   "欧元",           "d"),
    "DXY":       ("US Dollar Index",            "指数",           "d"),
    "DEXJPUS":   ("USD/JPY",                   "日元",           "d"),
}


def fetch_series(series_id):
    """获取单个序列数据"""
    try:
        df = fa.get_series(series_id)
        df.name = series_id
        return df
    except Exception as e:
        print(f"  ERROR {series_id}: {e}")
        return None


def main():
    results = {}

    for sid, (name, unit, freq) in INDICATORS.items():
        print(f"Fetching {sid} ({name})...", end=" ", flush=True)
        df = fetch_series(sid)
        if df is not None and len(df) > 0:
            results[sid] = (name, unit, freq, df)
            print(f"OK ({len(df)} obs, {df.index.min().strftime('%Y')} - {df.index.max().strftime('%Y')})")
        else:
            print(f"FAILED")

    if not results:
        print("No data fetched!")
        return

    # 合并所有序列到宽表
    combined = pd.DataFrame()
    for sid, (name, unit, freq, df) in results.items():
        if combined.empty:
            combined = df.to_frame(name=sid)
        else:
            combined = combined.join(df.to_frame(name=sid), how="outer")

    combined.index.name = "date"

    # 保存主数据文件
    base = "C:/Users/luoxi/.qclaw/workspace-knjrc5n1o4zjzm5o/docs/财经知识库/01_核心变量因果链"
    data_path = f"{base}/时序数据_USA_宏观.csv"
    combined.to_csv(data_path)
    print(f"\n数据已保存: {data_path} ({len(combined)}行 x {len(combined.columns)}列)")

    # 摘要统计
    summary = []
    for sid, (name, unit, freq, df) in results.items():
        summary.append({
            "series_id": sid,
            "name": name,
            "unit": unit,
            "freq": freq,
            "obs_count": len(df),
            "start": df.index.min().strftime("%Y-%m-%d"),
            "end": df.index.max().strftime("%Y-%m-%d"),
            "latest": round(float(df.iloc[-1]), 3) if pd.notna(df.iloc[-1]) else "",
            "latest_date": df.index[-1].strftime("%Y-%m-%d"),
            "min": round(float(df.min()), 3) if pd.notna(df.min()) else "",
            "max": round(float(df.max()), 3) if pd.notna(df.max()) else "",
        })

    summary_df = pd.DataFrame(summary)
    summary_path = f"{base}/时序数据_USA_摘要.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"摘要已保存: {summary_path}")

    print(f"\n成功获取 {len(results)}/{len(INDICATORS)} 个指标")
    print("完成时间:", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
