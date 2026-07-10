"""
fetch_china_data.py — 中国宏观数据历史拉取 & 增量更新

数据来源（两级，均为免费公开接口）：
  1. FRED / OECD 月频序列（同 fetch_fred_history.py 架构，无限速问题）
  2. World Bank API 年度序列（GDP增速、M2增速、CPI通胀年率等）

衍生序列：
  cpi_yoy — 从 CHNCPIALLMINMEI 指数计算同比涨幅（月频）

数据保存：data/china_history/{indicator_id}.csv
  格式：date,value（date = YYYY-MM-DD）

用法：
  python fetch_china_data.py          # 全量/增量（自动判断）
  python fetch_china_data.py --force  # 强制全量重拉（覆盖）
  python fetch_china_data.py --summary # 仅显示覆盖情况
"""

import os
import sys
import time
import json
import math
import argparse
import requests
from datetime import date, datetime, timedelta
from typing import Optional

try:
    from fredapi import Fred
except ImportError:
    print("ERROR: fredapi 未安装，请运行: pip install fredapi")
    sys.exit(1)

import pandas as pd

try:
    import akshare as _ak
    _AKSHARE_OK = True
except ImportError:
    _ak = None  # type: ignore
    _AKSHARE_OK = False

# ── 配置 ─────────────────────────────────────────────────────────────────────

FRED_API_KEY = os.environ.get("FRED_API_KEY", "REDACTED_FRED_KEY")

BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST_DIR = os.path.join(BASE_DIR, "data", "china_history")

_outbound    = os.environ.get("OUTBOUND_PROXY")
_http_proxy  = os.environ.get("HTTP_PROXY")  or _outbound
_https_proxy = os.environ.get("HTTPS_PROXY") or _outbound
_PROXIES = {"http": _http_proxy, "https": _https_proxy} if (_http_proxy or _https_proxy) else None

# ── 数据源定义 ─────────────────────────────────────────────────────────────────

# FRED 中国 / OECD 序列（月频）
# (series_id, 名称, 频率, 本地文件ID)
# 注：FRED 没有中国 PMI 和失业率月频数据，已改用 World Bank 年度序列
FRED_SERIES = [
    ("CHNCPIALLMINMEI",  "CPI指数(OECD月频)",       "monthly",  "cpi_index"),
    ("XTIMVA01CNM657S",  "出口总值(月频)",            "monthly",  "exports"),
]

# World Bank API 年度指标
# (WB indicator code, 名称, 本地文件ID)
WB_INDICATORS = [
    ("NY.GDP.MKTP.KD.ZG", "GDP实际增速(%年)",         "gdp_growth"),
    ("FP.CPI.TOTL.ZG",    "CPI通胀率(%年,WB)",        "cpi_yoy_wb"),
    ("SL.UEM.TOTL.ZS",    "失业率(%年,WB)",            "unemployment"),
    ("FM.LBL.BMNY.CN",    "M2货币供应量(绝对值,LCU)", "m2_abs"),
    ("NE.EXP.GNFS.CD",    "出口总额(USD亿,现价)",      "exports_usd"),
]

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def csv_path(indicator_id: str) -> str:
    """返回指标本地 CSV 文件的完整路径。"""
    return os.path.join(HIST_DIR, f"{indicator_id}.csv")


def load_last_date(indicator_id: str) -> Optional[str]:
    """从已有 CSV 读取最后一条记录的日期（用于增量拉取起点）。"""
    path = csv_path(indicator_id)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        if df.empty or "date" not in df.columns:
            return None
        return df["date"].max()
    except Exception:
        return None


def save_df(indicator_id: str, df: pd.DataFrame, mode: str = "w") -> int:
    """保存 DataFrame 到 CSV；mode='a' 为追加（增量），mode='w' 为覆盖。返回写入行数。"""
    path = csv_path(indicator_id)
    os.makedirs(HIST_DIR, exist_ok=True)
    if df.empty:
        return 0
    write_header = (mode == "w") or not os.path.exists(path)
    df.to_csv(path, mode=mode, index=False, header=write_header)
    return len(df)


# ── FRED 拉取 ─────────────────────────────────────────────────────────────────

def fetch_fred_series(fred: Fred, series_id: str, indicator_id: str,
                      name: str, force: bool = False) -> dict:
    """拉取中国专项 FRED 序列，全量或增量写入 CSV，返回结果摘要 dict。"""
    last_date = None if force else load_last_date(indicator_id)

    if last_date:
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
            return {"id": indicator_id, "name": name, "status": "空数据", "rows": 0}

        s = s.dropna()
        if s.empty:
            return {"id": indicator_id, "name": name, "status": "全NaN", "rows": 0}

        df = pd.DataFrame({"date": s.index.strftime("%Y-%m-%d"), "value": s.values})
        rows = save_df(indicator_id, df, mode=mode)
        return {
            "id":    indicator_id,
            "name":  name,
            "status": "OK",
            "rows":  rows,
            "fetch": fetch_desc,
            "date_range": f"{df['date'].min()} ~ {df['date'].max()}",
        }
    except Exception as e:
        return {"id": indicator_id, "name": name, "status": f"ERROR: {e}", "rows": 0}


# ── 衍生序列：CPI 同比（月频） ────────────────────────────────────────────────

def derive_cpi_yoy(force: bool = False) -> dict:
    """
    从 cpi_index.csv（CHNCPIALLMINMEI 指数）计算 CPI 月度同比涨幅(%)，
    写入 cpi_yoy.csv。
    """
    src_path = csv_path("cpi_index")
    if not os.path.exists(src_path):
        return {"id": "cpi_yoy", "name": "CPI同比(衍生)", "status": "源文件缺失", "rows": 0}

    try:
        df = pd.read_csv(src_path).dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
        if len(df) < 13:
            return {"id": "cpi_yoy", "name": "CPI同比(衍生)", "status": "数据点不足(<13)", "rows": 0}

        # 计算同比：(当月 / 12个月前) - 1
        df["value_12m"] = df["value"].shift(12)
        yoy_df = df.dropna(subset=["value_12m"]).copy()
        yoy_df["value"] = ((yoy_df["value"] / yoy_df["value_12m"]) - 1) * 100
        yoy_df["value"] = yoy_df["value"].round(2)
        out_df = yoy_df[["date", "value"]]

        if not force and os.path.exists(csv_path("cpi_yoy")):
            last_date = load_last_date("cpi_yoy")
            if last_date:
                out_df = out_df[out_df["date"] > last_date]
                if out_df.empty:
                    return {"id": "cpi_yoy", "name": "CPI同比(衍生)", "status": "已最新", "rows": 0}
                rows = save_df("cpi_yoy", out_df, mode="a")
                return {"id": "cpi_yoy", "name": "CPI同比(衍生)", "status": "OK",
                        "rows": rows, "fetch": "增量"}

        rows = save_df("cpi_yoy", out_df, mode="w")
        return {"id": "cpi_yoy", "name": "CPI同比(衍生)", "status": "OK",
                "rows": rows, "fetch": "全量",
                "date_range": f"{out_df['date'].min()} ~ {out_df['date'].max()}"}
    except Exception as e:
        return {"id": "cpi_yoy", "name": "CPI同比(衍生)", "status": f"ERROR: {e}", "rows": 0}


# ── 衍生序列：M2 同比增速（年度） ─────────────────────────────────────────────

def derive_m2_yoy(force: bool = False) -> dict:
    """
    从 m2_abs.csv（FM.LBL.BMNY.CN 绝对值）计算 M2 年度同比增速(%)，
    写入 m2_growth.csv。
    """
    src_path = csv_path("m2_abs")
    if not os.path.exists(src_path):
        return {"id": "m2_growth", "name": "M2增速(衍生)", "status": "源文件缺失", "rows": 0}

    try:
        df = pd.read_csv(src_path).dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
        if len(df) < 2:
            return {"id": "m2_growth", "name": "M2增速(衍生)", "status": "数据点不足", "rows": 0}

        df["prev"] = df["value"].shift(1)
        yoy_df = df.dropna(subset=["prev"]).copy()
        yoy_df["value"] = ((yoy_df["value"] / yoy_df["prev"]) - 1) * 100
        yoy_df["value"] = yoy_df["value"].round(2)
        out_df = yoy_df[["date", "value"]]

        if not force and os.path.exists(csv_path("m2_growth")):
            last_date = load_last_date("m2_growth")
            if last_date:
                out_df = out_df[out_df["date"] > last_date]
                if out_df.empty:
                    return {"id": "m2_growth", "name": "M2增速(衍生)", "status": "已最新", "rows": 0}
                rows = save_df("m2_growth", out_df, mode="a")
                return {"id": "m2_growth", "name": "M2增速(衍生)", "status": "OK",
                        "rows": rows, "fetch": "增量"}

        rows = save_df("m2_growth", out_df, mode="w")
        return {"id": "m2_growth", "name": "M2增速(衍生)", "status": "OK",
                "rows": rows, "fetch": "全量",
                "date_range": f"{out_df['date'].min()} ~ {out_df['date'].max()}"}
    except Exception as e:
        return {"id": "m2_growth", "name": "M2增速(衍生)", "status": f"ERROR: {e}", "rows": 0}


# ── World Bank 拉取 ────────────────────────────────────────────────────────────

def fetch_wb_indicator(wb_code: str, indicator_id: str, name: str,
                       force: bool = False) -> dict:
    """
    通过 World Bank API 拉取中国年度数据（JSON 格式）。
    端点：https://api.worldbank.org/v2/country/CN/indicator/{code}?format=json&per_page=100&mrv=100
    年度日期统一存为 YYYY-12-31。
    """
    last_date = None if force else load_last_date(indicator_id)
    last_year = int(last_date[:4]) if last_date else None

    url = (
        f"https://api.worldbank.org/v2/country/CN/indicator/{wb_code}"
        f"?format=json&per_page=100&mrv=100"
    )
    try:
        resp = requests.get(url, proxies=_PROXIES, timeout=30)
        if resp.status_code != 200:
            return {"id": indicator_id, "name": name,
                    "status": f"HTTP {resp.status_code}", "rows": 0}

        payload = resp.json()
        if not isinstance(payload, list) or len(payload) < 2:
            return {"id": indicator_id, "name": name, "status": "响应格式异常", "rows": 0}

        records = payload[1]
        rows_data = []
        for rec in records:
            if rec.get("value") is None:
                continue
            year_str = rec.get("date", "")
            if not year_str.isdigit():
                continue
            year = int(year_str)
            if last_year and year <= last_year:
                continue
            rows_data.append({
                "date":  f"{year}-12-31",
                "value": round(float(rec["value"]), 3),
            })

        if not rows_data:
            return {"id": indicator_id, "name": name, "status": "无新数据", "rows": 0}

        df = pd.DataFrame(rows_data).sort_values("date").reset_index(drop=True)
        mode = "a" if (last_year and not force) else "w"
        rows = save_df(indicator_id, df, mode=mode)
        fetch_desc = f"增量 since {last_year+1}" if (last_year and not force) else "全量"
        return {
            "id":    indicator_id,
            "name":  name,
            "status": "OK",
            "rows":  rows,
            "fetch": fetch_desc,
            "date_range": f"{df['date'].min()} ~ {df['date'].max()}",
        }
    except Exception as e:
        return {"id": indicator_id, "name": name, "status": f"ERROR: {e}", "rows": 0}


# ── AkShare 月频序列定义 ──────────────────────────────────────────────────────
# 使用 _yearly 系列（格式固定：日期列='日期'，值列='今值'，按月发布）
# 版本锁：akshare==1.18.63；列名变更时函数会返回 ERROR 提示而非静默失败
_AK_YEARLY_SERIES = [
    ("pmi_mfg",          "macro_china_pmi_yearly",                "制造业PMI(NBS月频)"),
    ("ppi_yoy",          "macro_china_ppi_yearly",                "PPI年率(月频)"),
    ("industrial_output","macro_china_industrial_production_yoy", "工业增加值年率(月频)"),
    ("cn_lpr",           "macro_china_lpr",                       "LPR1年期(%，月频)"),
    # HYP-7: 供 scorer.py score_china_recession_risk 泰勒缺口计算使用
]


def fetch_akshare_yearly(indicator_id: str, ak_func_name: str, name: str,
                         min_rows: int = 24, force: bool = False) -> dict:
    """
    拉取 AkShare _yearly 系列数据并写入 CSV。

    安全护栏：
      • 行数校验（< min_rows 不覆盖 CSV，防止空数据覆盖已有历史）
      • 过滤 NaN 值和未来占位行（AkShare 有时提前插入当月 NaN 行）
      • 所有失败仅记录，不中断主流程
    """
    if not _AKSHARE_OK:
        return {"id": indicator_id, "name": name, "status": "SKIP:akshare未安装", "rows": 0}

    try:
        fn = getattr(_ak, ak_func_name)
        raw = fn()
    except Exception as e:
        return {"id": indicator_id, "name": name, "status": f"ERROR(fetch):{e}", "rows": 0}

    try:
        if "日期" not in raw.columns or "今值" not in raw.columns:
            return {"id": indicator_id, "name": name,
                    "status": f"ERROR(列名变更):实际列={list(raw.columns)}", "rows": 0}

        df = raw[["日期", "今值"]].copy()
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
    except Exception as e:
        return {"id": indicator_id, "name": name, "status": f"ERROR(parse):{e}", "rows": 0}

    if len(df) < min_rows:
        return {"id": indicator_id, "name": name,
                "status": f"ERROR(行数不足):{len(df)}<{min_rows}", "rows": 0}

    if not force:
        last_date = load_last_date(indicator_id)
        if last_date:
            new_df = df[df["date"] > last_date]
            if new_df.empty:
                return {"id": indicator_id, "name": name, "status": "已最新", "rows": 0}
            rows = save_df(indicator_id, new_df, mode="a")
            return {"id": indicator_id, "name": name, "status": "OK",
                    "rows": rows, "fetch": "增量"}

    rows = save_df(indicator_id, df, mode="w")
    return {
        "id":    indicator_id,
        "name":  name,
        "status": "OK",
        "rows":  rows,
        "fetch": "全量",
        "date_range": f"{df['date'].min()} ~ {df['date'].max()}",
    }


# ── 摘要显示 ──────────────────────────────────────────────────────────────────

ALL_INDICATORS = (
    [(fid, name) for _, name, _, fid in FRED_SERIES]
    + [("cpi_yoy",   "CPI同比(衍生,月频)")]
    + [(wid, name) for _, name, wid in WB_INDICATORS]
    + [("m2_growth", "M2增速(衍生,年度)")]
    + [(fid, name) for fid, _, name in _AK_YEARLY_SERIES]
)


def show_summary() -> None:
    """打印所有指标的本地 CSV 覆盖情况（起止日期与行数汇总表）。"""
    print(f"\n{'指标ID':25s} {'名称':22s} {'起始':12s} {'截止':12s} {'行数':>8s}")
    print("-" * 88)
    for indicator_id, name in ALL_INDICATORS:
        path = csv_path(indicator_id)
        if not os.path.exists(path):
            print(f"{indicator_id:25s} {name:22s}  {'-- 无本地文件 --'}")
            continue
        try:
            df = pd.read_csv(path)
            if df.empty:
                print(f"{indicator_id:25s} {name:22s}  {'-- 空文件 --'}")
            else:
                start = df["date"].min()
                end   = df["date"].max()
                print(f"{indicator_id:25s} {name:22s}  {start:12s} {end:12s} {len(df):>8,}")
        except Exception as e:
            print(f"{indicator_id:25s} {name:22s}  ERROR: {e}")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    """CLI 入口：按顺序拉取 FRED → 衍生CPI → WorldBank → 衍生M2 → AkShare，输出覆盖摘要。"""
    parser = argparse.ArgumentParser(description="中国宏观数据历史拉取工具")
    parser.add_argument("--force",   action="store_true", help="强制全量重拉（覆盖）")
    parser.add_argument("--summary", action="store_true", help="仅显示覆盖情况")
    args = parser.parse_args()

    if args.summary:
        show_summary()
        return

    os.makedirs(HIST_DIR, exist_ok=True)
    fred = Fred(api_key=FRED_API_KEY)

    print(f"{'='*60}")
    print(f"中国宏观数据拉取  {'（全量重拉）' if args.force else '（增量更新）'}")
    print(f"保存目录: {HIST_DIR}")
    print(f"{'='*60}\n")

    results = []

    # 第一步：FRED 序列
    print("── FRED / OECD 月频序列 ──")
    for series_id, name, freq, indicator_id in FRED_SERIES:
        print(f"  [{indicator_id}] {name} ...", end=" ", flush=True)
        r = fetch_fred_series(fred, series_id, indicator_id, name, force=args.force)
        results.append(r)
        if r["status"] == "OK":
            print(f"{r['rows']} 行  {r.get('date_range','')}  [{r['fetch']}]")
        else:
            print(f"  {r['status']}")
        time.sleep(1.2)  # FRED API 限速（官方约1 req/s）

    # 第二步：衍生 CPI 同比
    print("\n── 衍生序列 ──")
    print(f"  [cpi_yoy] CPI同比（从cpi_index计算）...", end=" ", flush=True)
    r = derive_cpi_yoy(force=args.force)
    results.append(r)
    if r["status"] in ("OK", "已最新"):
        print(f"{r['rows']} 行  [{r.get('fetch', '-')}]")
    else:
        print(f"  {r['status']}")

    # 第三步：World Bank 年度序列
    print("\n── World Bank 年度序列 ──")
    for wb_code, name, indicator_id in WB_INDICATORS:
        print(f"  [{indicator_id}] {name} ...", end=" ", flush=True)
        r = fetch_wb_indicator(wb_code, indicator_id, name, force=args.force)
        results.append(r)
        if r["status"] in ("OK", "无新数据"):
            print(f"{r['rows']} 行  {r.get('date_range','')}  [{r.get('fetch','-')}]")
        else:
            print(f"  {r['status']}")
        time.sleep(0.5)

    # 第四步：衍生 M2 同比
    print("\n── 衍生序列（续） ──")
    print(f"  [m2_growth] M2增速（从m2_abs计算）...", end=" ", flush=True)
    r = derive_m2_yoy(force=args.force)
    results.append(r)
    if r["status"] in ("OK", "已最新"):
        print(f"{r['rows']} 行  [{r.get('fetch', '-')}]")
    else:
        print(f"  {r['status']}")

    # 第五步：AkShare 月频序列（PMI / PPI / 工业增加值）
    print("\n── AkShare 月频序列 ──")
    if not _AKSHARE_OK:
        print("  [跳过] akshare 未安装，可运行: pip install akshare==1.18.63")
    else:
        for indicator_id, ak_func_name, name in _AK_YEARLY_SERIES:
            print(f"  [{indicator_id}] {name} ...", end=" ", flush=True)
            r = fetch_akshare_yearly(indicator_id, ak_func_name, name, force=args.force)
            results.append(r)
            if r["status"] in ("OK", "已最新"):
                print(f"{r['rows']} 行  {r.get('date_range','')}  [{r.get('fetch','-')}]")
            else:
                print(f"  {r['status']}")

    # 汇总
    ok  = [r for r in results if r["status"] == "OK"]
    err = [r for r in results if r["status"] not in ("OK", "无新数据", "已最新", "全NaN")]
    print(f"\n{'='*60}")
    print(f"完成：{len(ok)}/{len(results)} 序列成功，{len(err)} 个失败")
    if err:
        print("失败序列：")
        for r in err:
            print(f"  {r['id']}: {r['status']}")

    print("\n最终覆盖情况：")
    show_summary()


if __name__ == "__main__":
    main()
