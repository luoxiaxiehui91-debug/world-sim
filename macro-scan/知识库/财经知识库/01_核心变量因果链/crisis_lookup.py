"""
历史情景快速检索脚本 - 从CSV数据库直接读取关键数据
用法: python crisis_lookup.py [危机关键词]
"""
import sys
import pandas as pd
import os

BASE = r"C:\Users\luoxi\.qclaw\workspace-knjrc5n1o4zjzm5o\docs\财经知识库\01_核心变量因果链"
SUMMARY_PATH = f"{BASE}/时序数据库_USA_摘要.csv"
CRISIS_PATH = f"{BASE}/历史情景_量化指标.csv"

def load_crisis_data():
    df = pd.read_csv(CRISIS_PATH)
    return df

def load_summary():
    df = pd.read_csv(SUMMARY_PATH)
    return df

def search_crisis(query):
    df = load_crisis_data()
    q = query.lower()
    
    results = df[df.apply(lambda row: q in str(row.values).lower(), axis=1)]
    
    if results.empty:
        print(f"未找到包含'{query}'的历史情景")
        print("\n可用情景:")
        for _, row in df.iterrows():
            print(f"  - {row['crisis']}")
        return
    
    print(f"\n找到 {len(results)} 个匹配的历史情景:\n")
    for _, row in results.iterrows():
        print("=" * 70)
        print(f"危机: {row['crisis']}")
        print(f"时间: {row['start_date']} ~ {row['end_date']}")
        print(f"类型: {row['type']}")
        print(f"严重程度: {row['severity']}")
        print("-" * 70)
        print(f"  GDP跌幅:      {row['gdp_peak_trough_pct']}")
        print(f"  失业率峰值:   {row['unemp_peak_pct']}")
        print(f"  S&P500最大回撤: {row['sp500_drawdown_pct']}")
        print(f"  10Y国债低点:  {row['pct_10y_trough']}")
        print(f"  政策利率:     {row['policy_key_rate_cut']}")
        print(f"  QE/非常规政策: {row['policy_qe']}")
        print(f"  复苏耗时:     {row['recovery_years']}")
        print("-" * 70)
        print(f"  关键教训: {row['key_lessons']}")
        print()

def list_all():
    df = load_crisis_data()
    print("\n可用历史情景对照表:")
    print("-" * 60)
    for _, row in df.iterrows():
        print(f"  {row['crisis']:15s} | {row['type']:12s} | {row['start_date']} | 严重程度: {row['severity']}")
    print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        list_all()
    else:
        search_crisis(sys.argv[1])
