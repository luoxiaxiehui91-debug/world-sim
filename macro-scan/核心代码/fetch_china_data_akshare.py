"""
fetch_china_data_akshare.py — 中国经济指标 akshare 数据源
替代已关闭的 NeoData 接口（腾讯 jprx.m.qq.com）。

对外接口：
    fetch_china_akshare(indicator_key) -> tuple[str, float] | tuple[None, None]

支持的 indicator_key（对应 CHINA_INDICATORS）：
    pmi_composite, pmi_mfg, cpi, ppi, gdp_growth, industrial_va, m2_growth
"""

import re
import pandas as pd
from typing import Optional, Tuple


def _parse_month(s) -> str:
    """'2026年04月份' / '2026年4月' → '2026-04-01'，用于排序和返回日期字符串"""
    m = re.match(r"(\d{4})年(\d{1,2})月份?", str(s))
    return f"{m.group(1)}-{m.group(2).zfill(2)}-01" if m else str(s)


def _first_valid(df: pd.DataFrame, date_col: str, value_col: str,
                 date_is_str_month: bool = True) -> Tuple[Optional[str], Optional[float]]:
    """取 DataFrame 中最新的非空数值行，返回 (date_str, float) 或 (None, None)"""
    try:
        df = df.dropna(subset=[value_col]).copy()
        if df.empty:
            return None, None
        if date_is_str_month:
            df["_sort"] = df[date_col].apply(_parse_month)
        else:
            df["_sort"] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.sort_values("_sort", ascending=False).reset_index(drop=True)
        row = df.iloc[0]
        date_str = _parse_month(row[date_col]) if date_is_str_month else str(row[date_col])[:10]
        return date_str, float(row[value_col])
    except Exception as e:
        print(f"    [AK] 数据解析失败: {e}")
        return None, None


# ── 各指标 fetch 函数 ──────────────────────────────────────────────────────────

def _fetch_pmi_composite() -> Tuple[Optional[str], Optional[float]]:
    """财新综合PMI — ak.index_pmi_com_cx()"""
    try:
        import akshare as ak
        df = ak.index_pmi_com_cx()
        if df is None or df.empty:
            return None, None
        df = df.sort_values("日期", ascending=False).reset_index(drop=True)
        val = float(df.loc[0, "综合PMI"])
        date_str = str(df.loc[0, "日期"])[:10]
        return date_str, val
    except Exception as e:
        print(f"    [AK] pmi_composite 失败: {e}")
        return None, None


def _fetch_pmi_mfg() -> Tuple[Optional[str], Optional[float]]:
    """官方制造业PMI — ak.macro_china_pmi()，取制造业-指数列"""
    try:
        import akshare as ak
        df = ak.macro_china_pmi()
        return _first_valid(df, "月份", "制造业-指数")
    except Exception as e:
        print(f"    [AK] pmi_mfg 失败: {e}")
        return None, None


def _fetch_cpi() -> Tuple[Optional[str], Optional[float]]:
    """CPI同比 — ak.macro_china_cpi()，取全国-同比增长列"""
    try:
        import akshare as ak
        df = ak.macro_china_cpi()
        return _first_valid(df, "月份", "全国-同比增长")
    except Exception as e:
        print(f"    [AK] cpi 失败: {e}")
        return None, None


def _fetch_ppi() -> Tuple[Optional[str], Optional[float]]:
    """PPI同比 — ak.macro_china_ppi()，取当月同比增长列"""
    try:
        import akshare as ak
        df = ak.macro_china_ppi()
        return _first_valid(df, "月份", "当月同比增长")
    except Exception as e:
        print(f"    [AK] ppi 失败: {e}")
        return None, None


def _fetch_gdp_growth() -> Tuple[Optional[str], Optional[float]]:
    """GDP增速 — ak.macro_china_gdp_yearly()，取今值列（年率，%）"""
    try:
        import akshare as ak
        df = ak.macro_china_gdp_yearly()
        return _first_valid(df, "日期", "今值", date_is_str_month=False)
    except Exception as e:
        print(f"    [AK] gdp_growth 失败: {e}")
        return None, None


def _fetch_industrial_va() -> Tuple[Optional[str], Optional[float]]:
    """工业增加值同比 — ak.macro_china_gyzjz()，取同比增长列"""
    try:
        import akshare as ak
        df = ak.macro_china_gyzjz()
        return _first_valid(df, "月份", "同比增长")
    except Exception as e:
        print(f"    [AK] industrial_va 失败: {e}")
        return None, None


def _fetch_m2_growth() -> Tuple[Optional[str], Optional[float]]:
    """M2同比 — ak.macro_china_money_supply()，取M2同比增长列"""
    try:
        import akshare as ak
        df = ak.macro_china_money_supply()
        return _first_valid(df, "月份", "货币和准货币(M2)-同比增长")
    except Exception as e:
        print(f"    [AK] m2_growth 失败: {e}")
        return None, None


def _fetch_cn_lpr() -> Tuple[Optional[str], Optional[float]]:
    """LPR 1年期 — ak.macro_china_lpr()，取1年期列（单位%）"""
    try:
        import akshare as ak
        df = ak.macro_china_lpr()
        if df is None or df.empty:
            return None, None
        # 优先取"1年期LPR"列，列名可能随 akshare 版本变动
        for col in ["1年期LPR(%)", "贷款市场报价利率(LPR):1年", "1年期", "lpr_1y"]:
            if col in df.columns:
                return _first_valid(df, "日期" if "日期" in df.columns else df.columns[0],
                                    col, date_is_str_month=False)
        # 兜底：取最后一个数值列
        num_cols = df.select_dtypes(include="number").columns.tolist()
        if num_cols:
            date_col = "日期" if "日期" in df.columns else df.columns[0]
            return _first_valid(df, date_col, num_cols[-1], date_is_str_month=False)
        return None, None
    except Exception as e:
        print(f"    [AK] cn_lpr 失败: {e}")
        return None, None


# ── 统一入口 ──────────────────────────────────────────────────────────────────

_DISPATCH = {
    "pmi_composite": _fetch_pmi_composite,
    "pmi_mfg":       _fetch_pmi_mfg,
    "cpi":           _fetch_cpi,
    "ppi":           _fetch_ppi,
    "gdp_growth":    _fetch_gdp_growth,
    "industrial_va": _fetch_industrial_va,
    "m2_growth":     _fetch_m2_growth,
    "cn_lpr":        _fetch_cn_lpr,
}


def fetch_china_akshare(indicator_key: str) -> Tuple[Optional[str], Optional[float]]:
    """
    统一入口：根据 indicator_key 调用对应 akshare 接口。
    akshare 失败时自动降级读取本地 CSV 最后一行（三层：akshare → CSV → None）。
    返回 (date_str, value) 或 (None, None)。
    """
    fn = _DISPATCH.get(indicator_key)
    if fn is None:
        return None, None
    date, value = fn()
    if value is not None:
        return date, value
    # 降级：读取本地历史 CSV 最后一行
    import os
    base_dir = os.environ.get("OPENCLAW_WORKSPACE",
                              os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    csv_path = os.path.join(base_dir, "data", "china_history", f"{indicator_key}.csv")
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path).dropna(subset=["value"])
            if not df.empty and "date" in df.columns:
                df = df.sort_values("date", ascending=False).reset_index(drop=True)
                row = df.iloc[0]
                print(f"    [AK→CSV] {indicator_key} akshare失败，使用本地CSV: {row['value']} ({row['date']})")
                return str(row["date"]), float(row["value"])
        except Exception as e:
            print(f"    [AK→CSV] {indicator_key} CSV回退失败: {e}")
    return None, None


# ── 独立运行测试 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    for key in _DISPATCH:
        print(f"\n[{key}]", end=" ")
        d, v = fetch_china_akshare(key)
        if v is not None:
            print(f"✓  {v}  ({d})")
        else:
            print("✗  无数据")
