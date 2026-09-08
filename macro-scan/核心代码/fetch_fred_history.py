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
from datetime import date, datetime, timedelta, timezone
from typing import Optional

try:
    from fredapi import Fred
except ImportError:
    print("ERROR: fredapi 未安装，请运行: pip install fredapi")
    sys.exit(1)

# ── B1 双写模块（旁路，导入失败则降级为 no-op，不影响 CSV 落库）──────────────
try:
    from pg_write_indicators import upsert_indicator_rows
except Exception as _imp_e:
    upsert_indicator_rows = None
    print(f"WARN: pg_write_indicators 模块不可用，PG 双写将跳过: {_imp_e}", file=sys.stderr)

import pandas as pd

# ── 配置 ─────────────────────────────────────────────────────────────────────

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# 脚本所在目录的上级 = 项目根目录
BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST_DIR = os.path.join(BASE_DIR, "data", "fred_history")

# 核心历史序列：(series_id, 名称, 最早可用年份说明, 频率)
# P0-D/data-freshness 修复：恢复 DGS3MO/T10Y3M/T5YIE/NFCI（旧 pyc SERIES 中存在，
# 08-03 源码被裁导致 DGS3MO 停止更新——这是「DGS3MO 卡 Aug1」的直接根因）。
SERIES = [
    # 利率 & 货币政策
    ("DFF",          "联邦基金利率",         "1954",   "daily"),
    ("DGS10",        "10年期国债收益率",      "1962",   "daily"),
    ("DGS2",         "2年期国债收益率",       "1976",   "daily"),
    ("DGS3MO",       "3M 国库券收益率",       "1982",   "daily"),
    ("T10Y2Y",       "收益率曲线(10Y-2Y)",    "1976",   "daily"),
    ("T10Y3M",       "10Y-3M 期限利差",      "1982",   "daily"),
    # 通胀
    ("CPIAUCSL",     "CPI(城市所有项目)",     "1947",   "monthly"),
    ("T5YIE",        "5Y 盈亏平衡通胀率",     "2003",   "daily"),
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
    ("NFCI",         "芝加哥联储金融条件指数", "1971",   "weekly"),
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
    mode="a": 追加（增量更新）—— 2026-09-08 起先与旧 CSV 合并、按 date 去重后
              全量写回，杜绝 FRED 在无新数据时仍返回末行观测导致的重复追加
              （日债 IRLTLT01JPM156N 曾累计 155 行同日重复）。
    返回新增行数。
    """
    path = csv_path(series_id)
    os.makedirs(HIST_DIR, exist_ok=True)
    if df.empty:
        return 0
    new_rows = len(df)
    if mode == "a" and os.path.exists(path):
        try:
            merged = pd.concat([pd.read_csv(path), df], ignore_index=True)
        except Exception:
            merged = df          # 旧文件不可读 → 回退原追加语义
    else:
        merged = df
    if "date" in merged.columns:
        merged = merged.assign(date=merged["date"].astype(str))
        merged = merged.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    _tmp = path + ".tmp"
    merged.to_csv(_tmp, index=False, header=True)
    os.replace(_tmp, path)      # data 为目录挂载，原子替换容器内外一致可见
    return new_rows


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

        # ── B1 双写 worldsim-pg.indicators（旁路，失败不影响 CSV 落库）────────
        pg_written = (0, 0)
        if upsert_indicator_rows is not None:
            try:
                pg_rows = []
                _vintage = date.today()
                _created = datetime.now(timezone.utc)   # 时区契约：必须 aware UTC（带 +00:00）
                for _, row in df.iterrows():
                    pg_rows.append({
                        "indicator_key": series_id,
                        "as_of": str(row["date"]),
                        "data_vintage": _vintage,
                        "horizon": "actual",
                        "value": float(row["value"]),
                        "ci_low": None,
                        "ci_high": None,
                        "model_ver": f"fred-{series_id}",
                        "created_at": _created,
                        "schema_version": "1.0",
                        "status": "ok",
                    })
                pg_written = upsert_indicator_rows(pg_rows)
            except Exception as _pg_e:
                print(f"WARN [fetch_fred_history] PG 双写失败（不影响 CSV 落库）: {_pg_e}",
                      file=sys.stderr)
                pg_written = (0, 0)

        return {
            "series_id": series_id,
            "name": name,
            "status": "OK",
            "rows": rows,
            "fetch": fetch_desc,
            "date_range": f"{df['date'].min()} ~ {df['date'].max()}",
            "pg_written": pg_written,
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
        # data-freshness：失败 symbol 重试 3 次（Spec 3.4 步骤 1）
        # 仅对真实错误（ERROR/全NaN）重试；"空数据"=已拉齐到源最新，非失败不重试
        attempt = 1
        while result["status"] in ("ERROR", "全NaN") and attempt < 3:
            time.sleep(3)
            attempt += 1
            print(f"\n  [{series_id}] 重试 {attempt}/3 ...", end=" ", flush=True)
            result = fetch_and_save(fred, series_id, name, force=args.force)
        results.append(result)
        status = result["status"]
        if status == "OK":
            print(f"{result['rows']} 行  {result['date_range']}  [{result['fetch']}]")
        elif status == "空数据":
            print("空数据（已拉齐到源最新，非失败）")
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

    # P0 修复（fred-manifest-orphan）：manifest.json 生成器——
    # 读现有 manifest（元数据模板）→ 更新 updated（astimezone 带 +08:00）→ 原子写回。
    # 模板缺失时跳过（不伪造元数据），首次需人工初始化（可 cp 历史 manifest）。
    try:
        import datetime as _dt
        _mp = os.path.join(BASE_DIR, "data", "fred_history", "manifest.json")
        if os.path.exists(_mp):
            with open(_mp, encoding="utf-8") as _f:
                _m = json.load(_f)
            _m["updated"] = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
            _m["schema_version"] = _m.get("schema_version", "1.0")
            _tmp = _mp + ".tmp"
            with open(_tmp, "w", encoding="utf-8") as _f:
                json.dump(_m, _f, ensure_ascii=False, indent=2)
            os.chmod(_tmp, 0o644)  # 2026-08-06 P0 修复（fred-manifest-403 防再生）：原写入继承 ACL/umask 致 0660+，nginx(www-data) 403
            os.replace(_tmp, _mp)
            print(f"[fetch_fred_history] manifest updated={_m['updated']}")
        else:
            print("WARN: manifest 模板不存在，跳过生成（首次需人工初始化）", file=sys.stderr)
    except Exception as _e:
        print(f"WARN: manifest 生成失败: {_e}", file=sys.stderr)

    # data-freshness：拉取一致性闸（Spec 3.4 步骤 2）
    # 任一 freshness symbol 失败/落后超容差 → gate_ok=false → compute_fci 不落库冻结值 + ntfy 告警
    try:
        from fred_freshness import run_gate
        gate_ok, _ = run_gate(alert=True)
        print(f"\n{'='*60}")
        print(f"[data-freshness] 拉取一致性闸: {'PASS' if gate_ok else 'FAIL'}"
              f"（gate 状态: {os.path.join(BASE_DIR, 'data', 'fred_gate_status.json')}）")
        if not gate_ok:
            # fail-loud：让调度层感知本次拉取未通过闸（留痕，不静默）
            sys.exit(2)
    except ImportError:
        print("WARN: fred_freshness 模块缺失，跳过拉取一致性闸（请先部署 fred_freshness.py）", file=sys.stderr)


if __name__ == "__main__":
    main()
