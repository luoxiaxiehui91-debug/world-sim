"""
fetch_gpr.py — GPR 地缘政治风险指数下载器
数据来源：Caldara & Iacoviello (2022), American Economic Review
官网：https://www.matteoiacoviello.com/gpr.htm
XLS：https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls

包含：
  GPR       全球 GPR（1985-今，月度）
  GPRA      全球 GPR 行动子指数
  GPRT      全球 GPR 威胁子指数
  GPRC_USA  美国 GPR
  GPRC_CHN  中国 GPR（约 2000 起）
  GPRC_TWN  台湾 GPR（约 2000 起）
  GPRC_RUS  俄罗斯 GPR（约 2000 起）

输出：data/fred_history/{series_id}.csv  （与 fetch_fred_history.py 同格式）
调度：scheduler.py  fred_fetch 任务（05:30）之后运行，或单独加一条 gpr_fetch 06:00
"""

import os
import sys
import io
import logging

import requests
import pandas as pd

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    _ws = os.environ.get("OPENCLAW_WORKSPACE",
                         os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR  = os.path.join(_ws, "data")
    WORKSPACE = _ws

HIST_DIR = os.path.join(DATA_DIR, "fred_history")
GPR_URL  = "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls"
GPR_URL_BACKUP = None  # 暂无可靠备用源

# XLS 列名 → 本地 series_id 映射（以实际列名为准，下载后自动对齐）
COL_MAP = {
    "GPRC_USA": ["GPRC_USA", "GPR_USA", "gpr_usa"],
    "GPRC_CHN": ["GPRC_CHN", "GPR_CHN", "gpr_china", "GPR_China"],
    "GPRC_TWN": ["GPRC_TWN", "GPR_TWN", "gpr_taiwan", "GPR_Taiwan"],
    "GPRC_RUS": ["GPRC_RUS", "GPR_RUS", "gpr_russia", "GPR_Russia"],
    "GPR":      ["GPR", "gpr_index", "GPR_index"],
    "GPRA":     ["GPRA", "GPR_ACT", "gpr_act"],
    "GPRT":     ["GPRT", "GPR_THREAT", "gpr_threat"],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_gpr")


def _find_col(df_cols: list, candidates: list) -> str | None:
    """在 df.columns 里找第一个匹配的候选列名（不区分大小写）。"""
    lower_cols = {c.lower(): c for c in df_cols}
    for cand in candidates:
        if cand.lower() in lower_cols:
            return lower_cols[cand.lower()]
    return None


def download_gpr() -> pd.DataFrame | None:
    """下载 GPR XLS，超时设 5 分钟（官网服务器较慢）。"""
    urls = [(GPR_URL, "官网")]
    if GPR_URL_BACKUP:
        urls.append((GPR_URL_BACKUP, "备用"))
    for url, label in urls:
        log.info(f"下载 GPR XLS ({label}): {url}")
        try:
            r = requests.get(url, timeout=300)
            r.raise_for_status()
            df = pd.read_excel(io.BytesIO(r.content), sheet_name=0)
            log.info(f"XLS 已读取，列名: {list(df.columns)}")
            return df
        except Exception as e:
            log.warning(f"[{label}] 失败: {e}")
    log.error("所有数据源均失败")
    return None


def _parse_date_col(df: pd.DataFrame) -> pd.DataFrame:
    """尝试解析日期列（可能是 year/month 两列，也可能是 date 字符串列）。"""
    cols_lower = {c.lower(): c for c in df.columns}

    if "year" in cols_lower and "month" in cols_lower:
        yr = df[cols_lower["year"]].astype(int)
        mo = df[cols_lower["month"]].astype(int)
        df["date"] = pd.to_datetime({"year": yr, "month": mo, "day": 1})
        return df

    for name in ["date", "Date", "DATE", "period"]:
        if name in df.columns:
            df["date"] = pd.to_datetime(df[name])
            return df

    # 第一列当 date 试试
    try:
        df["date"] = pd.to_datetime(df.iloc[:, 0])
        return df
    except Exception:
        pass

    raise ValueError(f"找不到日期列，现有列: {list(df.columns)}")


def save_series(series_id: str, dates: pd.Series, values: pd.Series) -> int:
    """写入 CSV，与 fetch_fred_history.py 格式一致（date,value）。"""
    os.makedirs(HIST_DIR, exist_ok=True)
    out = pd.DataFrame({
        "date":  dates.dt.strftime("%Y-%m-%d"),
        "value": values.round(3),
    }).dropna()
    path = os.path.join(HIST_DIR, f"{series_id}.csv")
    # H08 (2026-08-16, 全量审查): 原子写——原直接 to_csv(path) 写目标文件，
    # 写一半崩溃留半截 CSV（下游 pandas 读取损坏）。tmp + os.replace 保证
    # 读者永远看到完整文件。
    tmp = path + ".tmp"
    out.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return len(out)


def main():
    df_raw = download_gpr()
    if df_raw is None:
        log.error("无法获取 GPR 数据，退出")
        sys.exit(1)

    try:
        df_raw = _parse_date_col(df_raw)
    except ValueError as e:
        log.error(e)
        sys.exit(1)

    print(f"\nGPR XLS 列名: {list(df_raw.columns)}\n")

    results = {}
    for series_id, candidates in COL_MAP.items():
        col = _find_col(list(df_raw.columns), candidates)
        if col is None:
            log.warning(f"[{series_id}] 未找到对应列（候选: {candidates}）")
            results[series_id] = "未找到列"
            continue
        try:
            vals = pd.to_numeric(df_raw[col], errors="coerce")
            rows = save_series(series_id, df_raw["date"], vals)
            log.info(f"[{series_id}] ✅ 已写入 {rows} 行（列: {col}）")
            results[series_id] = f"OK {rows}行"
        except Exception as e:
            log.error(f"[{series_id}] 写入失败: {e}")
            results[series_id] = f"ERROR: {e}"

    print("\n── GPR 下载结果 ──")
    for sid, status in results.items():
        print(f"  {sid:<12} {status}")

    ok = sum(1 for s in results.values() if s.startswith("OK"))
    print(f"\n{ok}/{len(COL_MAP)} 系列成功写入 {HIST_DIR}")


if __name__ == "__main__":
    main()
