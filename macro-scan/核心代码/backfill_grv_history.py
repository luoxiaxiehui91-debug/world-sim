"""
backfill_grv_history.py — GRV 历史回填工具

用途：
  将 fred_history/ 下已有的 GPR CSV（498个月，约1996起）
  回放归一化逻辑，生成带时间戳的 grv_history.jsonl 历史序列。

说明：
  - 只能回填有 GPR 数据的维度；GDELT 历史已不可追，混合维度标记 source=gpr_only
  - 回填记录的 updated 字段使用 GPR 数据对应月份的月末日期（YYYY-MM-01 格式即原始日期）
  - 执行后会在 grv_history.jsonl 中追加，建议在文件不存在或已备份时运行
  - 已存在记录不会去重，请勿重复执行（或先删除 grv_history.jsonl 再执行）

运行：
  python3 /app/backfill_grv_history.py
  # 或加 --dry-run 只打印不写入
"""

import os
import sys
import json
import argparse
import pandas as pd

try:
    from optim_config import DATA_DIR
except ImportError:
    _ws = os.environ.get("OPENCLAW_WORKSPACE",
                         os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR = os.path.join(_ws, "data")

FRED_DIR    = os.path.join(DATA_DIR, "fred_history")
GRV_HISTORY = os.path.join(DATA_DIR, "grv_history.jsonl")

_FALLBACK_P10 = 50.0
_FALLBACK_P95 = 220.0


def _load_series(series_id: str) -> pd.DataFrame | None:
    path = os.path.join(FRED_DIR, series_id + ".csv")
    if not os.path.exists(path):
        print(f"  [WARN] {series_id}.csv 不存在，跳过")
        return None
    df = pd.read_csv(path).dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
    return df


def _normalize_at(df: pd.DataFrame, idx: int) -> float:
    """在第 idx 条记录处，用该时点之前最多120条数据计算滚动 p10/p95 并归一化。"""
    raw = float(df.iloc[idx]["value"])
    # 用截至当前的历史（防止未来数据泄露）
    tail = df.iloc[max(0, idx - 119): idx + 1]
    if len(tail) >= 24:
        p10 = float(tail["value"].quantile(0.10))
        p95 = float(tail["value"].quantile(0.95))
    else:
        p10 = _FALLBACK_P10
        p95 = _FALLBACK_P95
    if p95 <= p10:
        return 50.0
    normalized = (raw - p10) / (p95 - p10) * 100
    return round(min(max(normalized, 0.0), 100.0), 1)


def _normalize_at_date(df: pd.DataFrame, date_str: str) -> float | None:
    """按 date 字符串查找对应行，再调用 _normalize_at。找不到返回 None。"""
    if df is None:
        return None
    # df 已按 date 升序排列，date 列为字符串
    match = df.index[df["date"] == date_str].tolist()
    if not match:
        return None
    idx = match[0]
    return _normalize_at(df, idx)


def backfill(dry_run: bool = False) -> int:
    print(f"[backfill] 读取 FRED 数据目录: {FRED_DIR}")

    gpr_df     = _load_series("GPR")
    twn_df     = _load_series("GPRC_TWN")
    chn_df     = _load_series("GPRC_CHN")
    rus_df     = _load_series("GPRC_RUS")

    if gpr_df is None:
        print("[ERROR] GPR.csv 缺失，无法回填")
        return 0

    # 以 GPR 的时间轴为主线，各国别系列按 date 列对齐（起始年份不同，不能用位置索引）
    records = []
    for idx, row in gpr_df.iterrows():
        date_str = str(row["date"])  # e.g. "2026-06-01"

        gpr_global_norm = _normalize_at(gpr_df, idx)

        gpr_twn_norm = _normalize_at_date(twn_df, date_str)
        gpr_chn_norm = _normalize_at_date(chn_df, date_str)
        gpr_rus_norm = _normalize_at_date(rus_df, date_str)

        # gpr_twn_raw：从 twn_df 按 date 查找原始值
        gpr_twn_raw = None
        if twn_df is not None:
            twn_match = twn_df.index[twn_df["date"] == date_str].tolist()
            if twn_match:
                gpr_twn_raw = float(twn_df.iloc[twn_match[0]]["value"])

        # 混合维度无 GDELT，仅 GPR 分量
        taiwan_strait      = gpr_twn_norm   # GDELT×0.4 + GPR×0.6 → 无GDELT时退化为纯GPR
        us_china_strategic = gpr_chn_norm
        russia_europe      = gpr_rus_norm

        record = {
            "taiwan_strait":      taiwan_strait,
            "us_china_strategic": us_china_strategic,
            "russia_europe":      russia_europe,
            "middle_east_energy": None,          # GDELT-only，历史无法回填
            "global_composite":   gpr_global_norm,
            "climate_risk":       None,
            "disaster_risk":      None,
            "updated":            date_str + "T00:00:00",
            "gdelt_updated":      None,
            "gpr_twn_raw":        gpr_twn_raw,
            "gpr_twn_date":       date_str,
            "source_quality":     "gpr_only",    # 回填记录标记，区别于实时的 gdelt+gpr
        }
        records.append(record)

    print(f"[backfill] 共 {len(records)} 条记录（{records[0]['updated'][:7]} ~ {records[-1]['updated'][:7]}）")

    if dry_run:
        print("[dry-run] 前3条预览：")
        for r in records[:3]:
            print(" ", r)
        print("[dry-run] 未写入文件")
        return len(records)

    # 检查目标文件是否已有内容，有则直接退出防止重复追加
    if os.path.exists(GRV_HISTORY):
        with open(GRV_HISTORY, encoding="utf-8") as f:
            existing = sum(1 for _ in f)
        if existing > 0:
            print(f"[ERROR] {GRV_HISTORY} 已有 {existing} 条记录，拒绝执行。")
            print("        如需重新回填，请先手动删除该文件：")
            print(f"        rm {GRV_HISTORY}")
            import sys
            sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(GRV_HISTORY, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[backfill] 已写入 {len(records)} 条到 {GRV_HISTORY}")
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="回填 GRV 历史序列")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
