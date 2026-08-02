#!/usr/bin/env python3
"""
compute_probit.py — L1 衰退概率（Recession Probability，Φ-probit）

基于 Estrella-Trubin (2006) 模型的衰退概率计算。
使用 10Y-3M 期限利差（T10Y3M）作为单一自变量，
通过标准正态 CDF 映射为 12 个月衰退概率。

公式：recession_prob = Φ(α + β × T10Y3M)
  其中 α = -0.5333, β = -0.5984
  Φ = scipy.stats.norm.cdf

────────────────── 硬约束（Sprint-0 止血线） ──────────────────
  H1  禁直连 FRED：只读落盘文件 fred_history/T10Y3M.csv，不调用 fredapi
  H2  只算 Φ 不拟合：α/β 硬编码常量，不做任何回归拟合
  H3  ffill limit=5：前向填充最多连续 5 天；**严禁 fillna(0)**
  H4  不 import compute_fci：手工复制写盘模式
  H5  G1 口径断言（三重冗余）：列名断言 → exit(1) 报错 → assert 兜底
──────────────────────────────────────────────────────────────

输出（落盘到 DATA_DIR = /workspace/data）：
  data/probit_daily.csv     每日衰退概率（追加模式，去重）
  data/probit_vintage_log.csv  append-only 版本轨迹（每次运行追加一行）
  data/probit_latest.json    最新读数快照（供 GRV / 日报消费）

参考：Estrella & Trubin (2006), FRB NY Staff Report No. 258
"""

import os
import sys
import json
from datetime import datetime, timezone

import pandas as pd
from scipy.stats import norm

# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════

MODEL_VER = "probit-1.0"        # 模型版本（I1 model_ver）
SCHEMA_VERSION = "1.0.0"        # I1 数据契约版本（SemVer）

ALPHA = -0.5333                 # Estrella-Trubin 截距
BETA  = -0.5984                 # Estrella-Trubin 斜率

FFILL_LIMIT = 5                 # H3：前向填充上限（交易日）；超过即剔除

INPUT_VARIABLE = "T10Y3M"       # H5 G1：硬编码自变量名

REFERENCE = "Estrella & Trubin (2006), FRB NY Staff Report No. 258"
FORMULA_STR = "Φ(α + β × T10Y3M)"

# H5 黄金值（用于自检，确保公式正确）
GOLD_VALUES = {
    "m100bp": 0.525953,          # T10Y3M = -1.0（倒挂 100bp）
    "zero":   0.296913,          # T10Y3M =  0.0（平坦）
    "p100bp": 0.128880,          # T10Y3M = +1.0（正挂 100bp）
}
GOLD_TOLERANCE = 0.0005          # ε = ±0.0005

# ── DATA_DIR 解析（容器 vs 本地 dev）──────────────────────────────────────────

_data_dir_env = os.environ.get("DATA_DIR", "")
if _data_dir_env:
    # I1 落地闸：容器内 DATA_DIR 必须指向持久卷 /workspace/data，
    # 若指向容器根 /data（重启丢失）则直接 exit(2)
    if _data_dir_env != "/workspace/data":
        print(
            f"[probit][FATAL] DATA_DIR={_data_dir_env!r}，期望 '/workspace/data'。"
            f"落地卷错误——拒绝写数据。",
            file=sys.stderr,
        )
        sys.exit(2)
    DATA_DIR = _data_dir_env
else:
    # 本地 dev：回退到 OPENCLAW_WORKSPACE/data 或当前目录下的 data
    BASE_DIR = os.environ.get(
        "OPENCLAW_WORKSPACE",
        os.path.dirname(os.path.abspath(__file__)),
    )
    DATA_DIR = os.path.join(BASE_DIR, "data")

HIST_DIR  = os.path.join(DATA_DIR, "fred_history")
INPUT_CSV = os.path.join(HIST_DIR, "T10Y3M.csv")
OUT_CSV   = os.path.join(DATA_DIR, "probit_daily.csv")
OUT_LOG   = os.path.join(DATA_DIR, "probit_vintage_log.csv")
OUT_JSON  = os.path.join(DATA_DIR, "probit_latest.json")


# ═══════════════════════════════════════════════════════════════════════════════
# 核心计算
# ═══════════════════════════════════════════════════════════════════════════════

def _load_t10y3m() -> pd.Series:
    """读取 T10Y3M.csv，执行 G1 断言 + ffill，返回清洗后的 DatetimeIndex Series。

    G1 三重冗余口径断言：
      1. 列名必须包含 T10Y3M（若原始列为 value 则重命名）
      2. 若仍不匹配 → sys.exit(1) 并打印错误信息
      3. Python assert 兜底

    H3 ffill limit=5：前向填充最多 5 个连续缺失；超出即剔除，绝不补零。
    """
    if not os.path.exists(INPUT_CSV):
        raise FileNotFoundError(
            f"缺少输入文件: {INPUT_CSV}\n"
            f"  请确保 fred_fetch (05:30) 已成功采集 T10Y3M"
        )

    df = pd.read_csv(INPUT_CSV)

    # ── G1 口径断言 #1：列名检查 + 归一化 ──
    if "T10Y3M" not in df.columns:
        if "value" in df.columns and "date" in df.columns:
            # 原始 FRED 导出列名 "date,value" → 归一化为 "date,T10Y3M"
            df = df.rename(columns={"value": "T10Y3M"})
            print("[probit][G1] 检测到 'value' 列，已归一化为 'T10Y3M'")
        else:
            print(
                "G1 ASSERTION FAILED: T10Y3M not found\n"
                f"  文件: {INPUT_CSV}\n"
                f"  实际列名: {list(df.columns)}\n"
                "  G1 口径断言：probit 自变量必须为 T10Y3M（10Y-3M 利差）。\n"
                "  使用 T10Y2Y 或其他利差套同一系数 = 系统性偏误（上线首日高估 ~6pp）。",
                file=sys.stderr,
            )
            sys.exit(1)

    # ── G1 口径断言 #2：二次确认 ──
    if "T10Y3M" not in df.columns:
        print(
            f"G1 ASSERTION FAILED: T10Y3M not found in columns {list(df.columns)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── G1 口径断言 #3：assert 兜底 ──
    assert "T10Y3M" in df.columns, (
        f"G1 ASSERTION FAILED: T10Y3M not found. columns={list(df.columns)}"
    )

    # ── 解析 ──
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["T10Y3M"] = pd.to_numeric(df["T10Y3M"], errors="coerce")
    df = df.drop_duplicates(subset=["date"], keep="last")
    df = df.set_index("date").sort_index()

    s = df["T10Y3M"]

    # ── H3 ffill limit=5（严禁 fillna(0)）──
    before_na = int(s.isna().sum())
    s = s.ffill(limit=FFILL_LIMIT)
    s = s.dropna()
    dropped = before_na - (before_na - int(s.isna().sum()))
    # (ffill 后 dropna 的语义：仍为 NaN 的 = 超出 limit 的连续缺失，被剔除)

    if before_na > 0:
        print(
            f"[probit] T10Y3M 缺失处理: "
            f"原始 NaN={before_na} → ffill(limit={FFILL_LIMIT}) → "
            f"保留 {len(s)} 行"
        )

    return s


def compute_probit(spread: pd.Series) -> pd.Series:
    """计算衰退概率。

    Args:
        spread: T10Y3M 利差序列（百分比，如 0.84 表示 84bp）

    Returns:
        同 index 的 probit 概率序列 [0, 1]
    """
    z = ALPHA + BETA * spread
    prob = norm.cdf(z)
    return pd.Series(prob, index=spread.index, name="probit_value")


def _verify_gold_values() -> bool:
    """H5 黄金值自检：用三个锚点验证公式正确性。

    Returns:
        True 若全部通过（Δ ≤ 0.0005），否则 False
    """
    print("[probit][GOLD] 黄金值验证：")
    all_pass = True
    for label, spread, expected in [
        ("m100bp", -1.0, GOLD_VALUES["m100bp"]),
        ("zero",    0.0, GOLD_VALUES["zero"]),
        ("p100bp", +1.0, GOLD_VALUES["p100bp"]),
    ]:
        actual = float(norm.cdf(ALPHA + BETA * spread))
        delta = abs(actual - expected)
        ok = delta <= GOLD_TOLERANCE
        if not ok:
            all_pass = False
        status = "PASS" if ok else "FAIL"
        print(
            f"  [{status}]  T10Y3M={spread:+.1f}  "
            f"expected={expected:.6f}  actual={actual:.6f}  Δ={delta:.6f}"
        )
    return all_pass


# ═══════════════════════════════════════════════════════════════════════════════
# 落盘（手工复制 compute_fci.py 写盘模式，不 import）
# ═══════════════════════════════════════════════════════════════════════════════

def write_outputs(
    spread_series: pd.Series,
    probit_series: pd.Series,
    verbose: bool = True,
) -> int:
    """写 probit_daily.csv（追加+去重）、vintage_log.csv（追加）、latest.json。

    模式对齐 compute_fci.py：
      - daily CSV：追加模式 + 按 date 去重（probit 值确定，无需全量重写）
      - vintage log：append-only，header=not exists
      - latest JSON：全量覆写最新快照

    Returns:
        最终 daily CSV 行数
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    vintage = spread_series.index.max().strftime("%Y-%m-%d")

    # ── probit_daily.csv（追加模式 + 去重）────────────────────────────────
    new_df = pd.DataFrame({
        "date":           spread_series.index.strftime("%Y-%m-%d"),
        "probit_value":   probit_series.values.round(6),
        "t10y3m":         spread_series.values.round(6),
    })
    new_df["as_of"] = now
    new_df["data_vintage"] = vintage
    new_df["schema_version"] = MODEL_VER

    if os.path.exists(OUT_CSV):
        old_df = pd.read_csv(OUT_CSV)
        merged = pd.concat([old_df, new_df], ignore_index=True)
        # 去重：同 date 保留最新（= 后出现的行）
        merged = merged.drop_duplicates(subset=["date"], keep="last")
        merged = merged.sort_values("date").reset_index(drop=True)
    else:
        merged = new_df

    merged.to_csv(OUT_CSV, index=False)

    # ── probit_vintage_log.csv（append-only，对齐 fci_vintage_log.csv）────
    latest_date = spread_series.index[-1]
    latest_probit = float(probit_series.iloc[-1])
    latest_spread = float(spread_series.iloc[-1])

    log_row = pd.DataFrame([{
        "date":           latest_date.strftime("%Y-%m-%d"),
        "probit_value":   round(latest_probit, 6),
        "computed_at":    now,
        "T10Y3M_raw":     round(latest_spread, 6),
        "model_ver":      MODEL_VER,
        "schema_version": SCHEMA_VERSION,
    }])
    log_row.to_csv(
        OUT_LOG,
        mode="a",
        index=False,
        header=not os.path.exists(OUT_LOG),
    )

    # ── probit_latest.json（对齐 fci_latest.json + I1 §5.1）───────────────
    payload = {
        "schema_version": MODEL_VER,         # 对齐 FCI 模式：此处为 model_ver
        "as_of":          now,
        "data_vintage":   vintage,
        "date":           latest_date.strftime("%Y-%m-%d"),
        "probit_value":   round(latest_probit, 6),
        "input_variable": INPUT_VARIABLE,
        "input_value":    round(latest_spread, 6),
        "alpha":          ALPHA,
        "beta":           BETA,
        "gold_values":    GOLD_VALUES,
        "formula":        FORMULA_STR,
        "reference":      REFERENCE,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"[write] {OUT_CSV}  {len(merged)} 行（追加+去重）")
        print(f"[write] {OUT_LOG}  追加 1 行版本记录")
        print(
            f"[write] {OUT_JSON}  {latest_date.date()}  "
            f"T10Y3M={latest_spread:.2f}  probit={latest_probit:.4%}"
        )

    return len(merged)


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"=== L1 probit  model={MODEL_VER} ===")

    # ── H5 黄金值自检（运行前验证公式正确性）─────────────────────────────
    if not _verify_gold_values():
        print(
            "\n[probit][FATAL] 黄金值验证未通过——公式可能有误，拒绝运行。",
            file=sys.stderr,
        )
        sys.exit(2)

    # ── 加载 T10Y3M（含 G1 断言 + H3 ffill）───────────────────────────
    spread = _load_t10y3m()
    print(
        f"[probit] 加载 {INPUT_VARIABLE}: {len(spread)} 行  "
        f"{spread.index.min().date()} ~ {spread.index.max().date()}"
    )

    # ── 计算 probit ────────────────────────────────────────────────────
    probit = compute_probit(spread)

    # ── 落盘 ────────────────────────────────────────────────────────────
    write_outputs(spread, probit)

    # ── 最近 5 个交易日摘要 ─────────────────────────────────────────────
    print("\n最近 5 个交易日：")
    n = len(spread)
    for i in range(max(0, n - 5), n):
        d = spread.index[i]
        s = spread.iloc[i]
        p = probit.iloc[i]
        print(f"  {d.date()}  T10Y3M={s:+.2f}  probit={p:.4%}")

    # ── 当前值提示 ──────────────────────────────────────────────────────
    latest_spread = float(spread.iloc[-1])
    latest_probit = float(probit.iloc[-1])
    print(f"\n[probit] 最新: {spread.index[-1].date()}  "
          f"T10Y3M={latest_spread:+.2f}  →  probit={latest_probit:.4%}")

    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# 自测入口（本地开发用）
# ═══════════════════════════════════════════════════════════════════════════════

def _run_self_test():
    """用样本数据验证公式正确性，不依赖文件系统。"""
    print("=" * 60)
    print("  compute_probit.py · 自测（样本 DataFrame）")
    print("=" * 60)

    # 黄金值三点
    print("\n── 黄金值验证 ──")
    all_pass = True
    for label, spread, expected in [
        ("m100bp", -1.0, GOLD_VALUES["m100bp"]),
        ("zero",    0.0, GOLD_VALUES["zero"]),
        ("p100bp", +1.0, GOLD_VALUES["p100bp"]),
    ]:
        actual = float(norm.cdf(ALPHA + BETA * spread))
        delta = abs(actual - expected)
        ok = "PASS" if delta <= GOLD_TOLERANCE else "FAIL"
        if delta > GOLD_TOLERANCE:
            all_pass = False
        print(f"  [{ok}]  T10Y3M={spread:+.1f}  "
              f"expected={expected:.6f}  actual={actual:.6f}  Δ={delta:.6f}")

    # 当前值（2026-07-29, T10Y3M=0.84）验证
    print("\n── 当前值验证 ──")
    cur_spread = 0.84
    cur_probit = float(norm.cdf(ALPHA + BETA * cur_spread))
    print(f"  T10Y3M={cur_spread:+.2f}  →  probit={cur_probit:.4%}  "
          f"(预期约 15.01%)")

    # 虚构序列
    print("\n── 虚构序列计算 ──")
    dates = pd.date_range("2026-07-25", periods=7, freq="B")
    test_spreads = pd.Series(
        [0.73, 0.69, 0.71, 0.84, 0.86, 0.90, 0.50],
        index=dates,
        name="T10Y3M",
    )
    test_probits = compute_probit(test_spreads)
    for d, s, p in zip(dates, test_spreads, test_probits):
        print(f"  {d.date()}  T10Y3M={s:+.2f}  probit={p:.4%}")

    print("\n── ffill limit=5 测试 ──")
    # 构造含 NaN 序列
    ff_dates = pd.date_range("2026-07-01", periods=15, freq="B")
    ff_values = [
        float("nan"), float("nan"), float("nan"),  # 0-2: 无前值，剔除
        0.80, 0.82,                                  # 3-4: 有效
        float("nan"), float("nan"),                  # 5-6: ffill 可填 2 个
        0.85,                                        # 7: 有效
        float("nan"), float("nan"), float("nan"),    # 8-10: ffill 填 3 个
        float("nan"), float("nan"), float("nan"),    # 11-13: 前 2 填，13 剔除
        0.90,                                        # 14: 有效
    ]
    ff_series = pd.Series(ff_values, index=ff_dates, name="T10Y3M")
    before = len(ff_series)
    before_na = int(ff_series.isna().sum())
    ff_series = ff_series.ffill(limit=FFILL_LIMIT)
    ff_series = ff_series.dropna()
    after = len(ff_series)
    print(f"  输入 {before} 行 (含 NaN {before_na}) → ffill(5)+dropna → {after} 行")
    for d in ff_series.index:
        print(f"  {d.date()}  T10Y3M={ff_series[d]:+.2f}")

    print("\n" + "=" * 60)
    status = "PASS" if all_pass else "FAIL"
    print(f"  自测完成: {status}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="L1 衰退概率（Φ-probit, Estrella-Trubin 2006）"
    )
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="本地自测：用样本 DataFrame 验证公式+黄金值+ffill，不读写文件",
    )
    args = ap.parse_args()

    if args.self_test:
        _run_self_test()
    else:
        sys.exit(main())
