"""
fetch_gscpi.py — GSCPI 全球供应链压力指数（NY Fed 官方 xlsx）采集

来源：NY Fed 官方 GSCPI Monthly Data xlsx（月度，每月第 4 个工作日发布）
  URL: https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx
  FRED API 无 GSCPI 序列（实测 400），NY Fed xlsx 为唯一官方免费源（ADR-01）。

落盘：data/fred_history/GSCPI.csv（date,value，与 GPR 系 CSV 同构，data_fetcher L712-725 同款读取）
  尾行 = 最新月度值（如 2026-07-31,0.805）。

用法：
  python3 fetch_gscpi.py            # 下载/解析/落盘
  python3 fetch_gscpi.py --check    # 仅校验本地 CSV 尾行，不下载

调度建议：日频（每月第 4 工作日发布新值，日频幂等检查即可），scheduler 挂 05:32。
出网：直连优先，失败回退 OUTBOUND_PROXY（参照 fetch_firms.py 2026-08-06 修复模式）。
依赖：requests + xlrd（容器已装 xlrd 2.0.2 / requests 2.33.1），无新依赖。
"""

import os
import sys
import csv
import datetime

try:
    import requests
except ImportError:
    print("ERROR: requests 未安装")
    sys.exit(1)

try:
    import xlrd
except ImportError:
    print("ERROR: xlrd 未安装（xlsx 老格式解析需要），请运行 pip install xlrd")
    sys.exit(1)

# ── 配置 ─────────────────────────────────────────────────────────────────────

GSCPI_URL = "https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx"
SHEET_NAME = "GSCPI Monthly Data"

# 脚本所在目录的上级 = 项目根目录（与 fetch_fred_history.py 同款）
BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST_DIR = os.path.join(BASE_DIR, "data", "fred_history")
OUT_CSV = os.path.join(HIST_DIR, "GSCPI.csv")

# 代理配置（参照 fetch_firms.py：optim_config.PROXY_URL > env OUTBOUND_PROXY）
try:
    from optim_config import PROXY_URL
except ImportError:
    PROXY_URL = os.environ.get("OUTBOUND_PROXY", "")
PROXY_URL = os.environ.get("OUTBOUND_PROXY", "") or PROXY_URL
_PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

TIMEOUT = (15, 60)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


# ── 工具函数 ────────────────────────────────────────────────────────────────

def _download() -> bytes:
    """直连下载 xlsx；失败回退 OUTBOUND_PROXY（防御性）。"""
    try:
        r = requests.get(GSCPI_URL, timeout=TIMEOUT, headers={"User-Agent": UA})
    except Exception:
        if _PROXIES:
            r = requests.get(GSCPI_URL, timeout=TIMEOUT,
                             headers={"User-Agent": UA}, proxies=_PROXIES)
        else:
            raise
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.content


def _parse(content: bytes) -> list[tuple[str, float]]:
    """xlrd 解析 GSCPI Monthly Data sheet → [(YYYY-MM-DD, value)]（升序）。"""
    wb = xlrd.open_workbook(file_contents=content)
    if SHEET_NAME in wb.sheet_names():
        sh = wb.sheet_by_name(SHEET_NAME)
    else:
        raise RuntimeError(f"sheet '{SHEET_NAME}' 不存在，实际: {wb.sheet_names()}")

    rows = []
    for r in range(sh.nrows):
        d = sh.cell_value(r, 0)
        v = sh.cell_value(r, 1)
        if not (isinstance(d, str) and d.strip() and isinstance(v, (int, float))):
            continue
        try:
            dt = datetime.datetime.strptime(d.strip(), "%d-%b-%Y")
        except ValueError:
            continue  # 跳过注释/说明行
        rows.append((dt.strftime("%Y-%m-%d"), round(float(v), 3)))

    rows.sort(key=lambda x: x[0])
    # 按 date 去重（同一月末只会有一个值）
    dedup = {}
    for d, v in rows:
        dedup[d] = v
    return sorted(dedup.items())


def _load_existing() -> dict:
    """读取已有 CSV → {date: value}。"""
    if not os.path.exists(OUT_CSV):
        return {}
    try:
        with open(OUT_CSV, encoding="utf-8") as f:
            rd = csv.reader(f)
            next(rd, None)  # header
            return {row[0]: float(row[1]) for row in rd
                    if row and row[0] and row[1] and row[0] != "date"}
    except Exception:
        return {}


# ── 主流程 ──────────────────────────────────────────────────────────────────

def fetch_and_save() -> dict:
    """下载/解析/落盘 GSCPI.csv。幂等：最新值不变不覆盖。"""
    os.makedirs(HIST_DIR, exist_ok=True)
    content = _download()
    new_rows = _parse(content)
    if not new_rows:
        raise RuntimeError("解析结果为空")
    last_date, last_value = new_rows[-1]

    existing = _load_existing()
    if existing and last_date in existing and abs(existing[last_date] - last_value) < 1e-9:
        print(f"[OK] GSCPI 幂等跳过（已有最新 {last_date} = {last_value:.3f}）")
        return {"date": last_date, "value": last_value, "updated": False}

    merged = dict(existing)
    merged.update(dict(new_rows))
    ordered = sorted(merged.items())

    tmp = OUT_CSV + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for d, v in ordered:
            w.writerow([d, v])
    os.replace(tmp, OUT_CSV)

    print(f"[OK] GSCPI 写入 {len(ordered)} 行，尾行 {last_date} = {last_value:.3f}")
    return {"date": last_date, "value": last_value, "updated": True, "rows": len(ordered)}


def check_existing() -> int:
    """--check：只读本地 CSV，输出尾行。返回 0=OK。"""
    existing = _load_existing()
    if not existing:
        print("[SKIP] GSCPI 本地 CSV 不存在")
        return 1
    last_date = max(existing)
    print(f"[CHECK] GSCPI 尾行 {last_date} = {existing[last_date]:.3f}（本地 {len(existing)} 行）")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="GSCPI 采集（NY Fed xlsx → data/fred_history/GSCPI.csv）")
    ap.add_argument("--check", action="store_true", help="仅校验本地 CSV，不下载")
    args = ap.parse_args()
    try:
        if args.check:
            sys.exit(check_existing())
        fetch_and_save()
    except Exception as e:
        print(f"[ERROR] fetch_gscpi: {e}")
        sys.exit(1)
