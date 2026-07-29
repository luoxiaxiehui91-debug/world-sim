"""
fetch_fred_history.py — FRED 核心序列历史数据全量拉取 & 增量更新

用法：
  python fetch_fred_history.py          # 全量/增量（自动判断）
  python fetch_fred_history.py --force  # 强制全量重拉
  python fetch_fred_history.py --summary # 仅显示各序列覆盖情况

数据保存：data/fred_history/{series_id}.csv
  格式：date,value（date = YYYY-MM-DD）
"""

import os
import sys
import csv
import json
import time
import math
import argparse
from datetime import date, datetime, timedelta
from typing import Optional

try:
    from fredapi import Fred
except ImportError:
    print("ERROR: fredapi 未安装，请运行: pip install fredapi")
    sys.exit(1)

import pandas as pd

# ── 配置 ─────────────────────────────────────────────────────────────────────

FRED_API_KEY = os.environ.get("FRED_API_KEY", "REDACTED_FRED_KEY")

# 脚本所在目录的上级 = 项目根目录
BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST_DIR = os.path.join(BASE_DIR, "data", "fred_history")

# 核心历史序列：(series_id, 名称, 最早可用年份说明, 频率)
SERIES = [
    # 利率 & 货币政策
    ("DFF",          "联邦基金利率",         "1954",   "daily"),
    ("DGS10",        "10年期国债收益率",      "1962",   "daily"),
    ("DGS2",         "2年期国债收益率",       "1976",   "daily"),
    ("T10Y2Y",       "收益率曲线(10Y-2Y)",    "1976",   "daily"),
    # 通胀
    ("CPIAUCSL",     "CPI(城市所有项目)",     "1947",   "monthly"),
    ("PCEPI",        "核心PCE",              "1959",   "monthly"),
    ("PPIACO",       "PPI(所有商品)",         "1913",   "monthly"),
    # 经济增长 & 就业
    ("GDPC1",        "实际GDP",              "1947",   "quarterly"),
    ("UNRATE",       "失业率",               "1948",   "monthly"),
    ("PAYEMS",       "非农就业(千人)",        "1939",   "monthly"),
    ("INDPRO",       "工业产出指数",          "1919",   "monthly"),
    # 资产 & 商品
    ("SP500",        "标普500",              "1927",   "daily"),
    ("VIXCLS",       "VIX恐慌指数",          "1990",   "daily"),   # R08 相关性突变监测用
    ("DCOILWTICO",   "WTI原油",              "1986",   "daily"),
    ("DTWEXBGS",     "贸易加权美元指数",      "2006",   "daily"),
    # 信用 & 金融压力
    ("BAA10Y",       "BAA-10Y信用利差",       "1986",   "daily"),
    ("BAMLH0A0HYM2", "高收益债利差",          "1996",   "daily"),
    ("M2SL",         "M2货币供应",            "1959",   "monthly"),
    # 领先指标
    ("UMCSENT",      "消费者信心",            "1952",   "monthly"),
    ("HOUST",        "新屋开工(千套)",         "1959",   "monthly"),
    ("PERMIT",       "建筑许可(千套)",         "1960",   "monthly"),
    # 欧洲 & 日本（国际环境参考）
    ("ECBDFR",             "ECB存款利率",          "1999",   "daily"),
    ("IRLTLT01EZM156N",    "欧元区10Y国债收益率",  "1993",   "monthly"),
    ("CP0000EZ19M086NEST", "欧元区HICP指数",       "1996",   "monthly"),
    ("CLVMNACSCAB1GQEA19", "欧元区实际GDP",        "1995",   "quarterly"),
    ("IRLTLT01JPM156N",    "日本10Y国债收益率",    "1966",   "monthly"),
    ("LRUNTTTTJPM156S",    "日本失业率",            "1953",   "monthly"),
    ("DEXJPUS",            "美元/日元汇率",         "1971",   "daily"),    # 日元套利风险监测
    ("IRLTLT01GBM156N",    "英国10Y国债收益率",    "1957",   "monthly"),
    ("CPALTT01GBM659N",    "英国CPI同比",          "1956",   "monthly"),
    ("LRHUTTTTGBM156S",    "英国失业率",            "1971",   "monthly"),
    # ── 新增数据源（Phase 1E）────────────────────────────────────────────────
    # 离岸人民币汇率（美元/人民币，资本外流压力信号）
    ("DEXCHUS",            "美元/离岸人民币汇率",   "2010",   "daily"),
    # 铜价（全球工业需求领先指标，"铜博士"）
    ("PCOPPUSDM",          "铜价(美元/磅，月度)",   "1990",   "monthly"),
    # 美国TGA财政部账户余额（流动性抽水/注水信号，周度）
    ("WDTGAL",             "财政部TGA账户余额(十亿美元)", "2005", "weekly"),
    # 初请失业金（已有ICSA日频，补充季调后周度历史）
    ("ICSA",               "初请失业金(千人，季调)", "1967",   "weekly"),
    # ── 新增数据源（Phase 2，气候+社会信号）────────────────────────────────────
    # 小麦价格（IMF商品价格指数，气候→粮食最直接价格信号）
    ("PWHEAMTUSDM",        "小麦价格(美元/吨，IMF月度)", "1990", "monthly"),
    # 玉米价格（与小麦互证，厄尔尼诺南美产区指标）
    ("PMAIZMTUSDM",        "玉米价格(美元/吨，IMF月度)", "1990", "monthly"),
]

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def csv_path(series_id: str) -> str:
    """返回序列本地 CSV 文件的完整路径。"""
    return os.path.join(HIST_DIR, f"{series_id}.csv")


def load_last_date(series_id: str) -> Optional[str]:
    """从已有 CSV 读取最后一条记录的日期"""
    path = csv_path(series_id)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        if df.empty or "date" not in df.columns:
            return None
        return df["date"].max()
    except Exception:
        return None


def save_series(series_id: str, df: pd.DataFrame, mode: str = "w") -> int:
    """
    保存序列到 CSV。
    mode="w": 全量写（覆盖）
    mode="a": 追加（增量更新）
    返回写入行数。
    """
    path = csv_path(series_id)
    os.makedirs(HIST_DIR, exist_ok=True)
    if df.empty:
        return 0
    write_header = (mode == "w") or not os.path.exists(path)
    df.to_csv(path, mode=mode, index=False, header=write_header)
    return len(df)


def fetch_and_save(fred: Fred, series_id: str, name: str, force: bool = False) -> dict:
    """
    拉取单个序列的历史数据并保存。
    - force=True 或本地无文件：全量拉取
    - 否则：增量拉取（从 last_date+1 天开始）
    返回结果摘要 dict。
    """
    last_date = None if force else load_last_date(series_id)

    if last_date:
        # 增量：从最后一条日期的次日开始
        next_day = (datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        mode = "a"
        fetch_desc = f"增量 since {next_day}"
    else:
        next_day = None
        mode = "w"
        fetch_desc = "全量"

    try:
        kwargs = {"observation_start": next_day} if next_day else {}
        s = fred.get_series(series_id, **kwargs)
        if s is None or s.empty:
            return {"series_id": series_id, "name": name, "status": "空数据", "rows": 0}

        # 过滤 NaN
        s = s.dropna()
        if s.empty:
            return {"series_id": series_id, "name": name, "status": "全NaN", "rows": 0}

        df = pd.DataFrame({"date": s.index.strftime("%Y-%m-%d"), "value": s.values})
        rows = save_series(series_id, df, mode=mode)

        return {
            "series_id": series_id,
            "name": name,
            "status": "OK",
            "rows": rows,
            "fetch": fetch_desc,
            "date_range": f"{df['date'].min()} ~ {df['date'].max()}",
        }
    except Exception as e:
        return {"series_id": series_id, "name": name, "status": f"ERROR: {e}", "rows": 0}


def show_summary() -> None:
    """显示已存本地的各序列覆盖情况"""
    print(f"\n{'序列ID':20s} {'名称':18s} {'起始':12s} {'截止':12s} {'行数':>8s}")
    print("-" * 78)
    for series_id, name, *_ in SERIES:
        path = csv_path(series_id)
        if not os.path.exists(path):
            print(f"{series_id:20s} {name:18s}  {'-- 无本地文件 --'}")
            continue
        try:
            df = pd.read_csv(path)
            if df.empty:
                print(f"{series_id:20s} {name:18s}  {'-- 空文件 --'}")
            else:
                start = df["date"].min()
                end = df["date"].max()
                print(f"{series_id:20s} {name:18s}  {start:12s} {end:12s} {len(df):>8,}")
        except Exception as e:
            print(f"{series_id:20s} {name:18s}  ERROR: {e}")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    """CLI 入口：解析 --force/--summary 参数，执行全量或增量 FRED 数据拉取。"""
    parser = argparse.ArgumentParser(description="FRED 历史数据拉取工具")
    parser.add_argument("--force",   action="store_true", help="强制全量重拉（覆盖现有文件）")
    parser.add_argument("--summary", action="store_true", help="仅显示覆盖情况，不拉取数据")
    args = parser.parse_args()

    if args.summary:
        show_summary()
        return

    fred = Fred(api_key=FRED_API_KEY)
    os.makedirs(HIST_DIR, exist_ok=True)

    print(f"{'='*60}")
    print(f"FRED 历史数据拉取  {'（全量重拉）' if args.force else '（增量更新）'}")
    print(f"保存目录: {HIST_DIR}")
    print(f"{'='*60}\n")

    results = []
    for series_id, name, earliest_note, freq in SERIES:
        print(f"  [{series_id}] {name} ({freq})...", end=" ", flush=True)
        result = fetch_and_save(fred, series_id, name, force=args.force)
        results.append(result)
        status = result["status"]
        if status == "OK":
            print(f"{result['rows']} 行  {result['date_range']}  [{result['fetch']}]")
        else:
            print(f"⚠ {status}")
        time.sleep(1.2)  # FRED API 限速（官方约1 req/s）

    # 汇总
    ok = [r for r in results if r["status"] == "OK"]
    err = [r for r in results if r["status"] != "OK"]
    print(f"\n{'='*60}")
    print(f"完成：{len(ok)}/{len(SERIES)} 序列成功，{len(err)} 个失败")
    if err:
        print("失败序列：")
        for r in err:
            print(f"  {r['series_id']}: {r['status']}")

    print("\n最终覆盖情况：")
    show_summary()


if __name__ == "__main__":
    main()
