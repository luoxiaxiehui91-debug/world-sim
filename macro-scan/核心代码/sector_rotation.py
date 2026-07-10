"""
sector_rotation.py — 行业轮动数据模块
部署路径：/app/sector_rotation.py
依赖：akshare（已在容器内安装）

对外接口：
  get_sector_rotation_context() -> str | None
    返回格式化的行业轮动文字摘要，供注入 LLM prompt；
    若数据拉取失败（网络/akshare异常）返回 None。
"""

import time
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────

SECTOR_ETFS = {
    "XLK":  "科技",
    "XLF":  "金融",
    "XLE":  "能源",
    "XLV":  "医疗",
    "XLI":  "工业",
    "XLY":  "可选消费",
    "XLP":  "必选消费",
    "XLU":  "公用事业",
    "XLRE": "房地产",
    "XLB":  "材料",
    "XLC":  "通信",
}

LOOKBACKS = {
    "1M": 21,   # 约1个月交易日
    "3M": 63,   # 约3个月交易日
}

_FETCH_DELAY = 0.5      # 请求间隔（秒），避免 akshare 限流
_MIN_ROWS    = 80       # 有效数据最少行数


# ── 内部工具函数 ───────────────────────────────────────────────────────────────

def _fetch_etf(symbol: str) -> pd.Series | None:
    """拉取美股ETF日线，返回收盘价 Series（index=DatetimeIndex）"""
    try:
        import akshare as ak
        df = ak.stock_us_daily(symbol=symbol, adjust="qfq")
        if df is None or df.empty or len(df) < _MIN_ROWS:
            logger.warning(f"[SR] {symbol} 数据不足（行数={len(df) if df is not None else 0}）")
            return None
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").set_index("date")
        return df["close"].astype(float)
    except Exception as e:
        logger.warning(f"[SR] {symbol} 拉取失败: {e}")
        return None


def _calc_momentum(series: pd.Series, days: int) -> float | None:
    """计算 N 日价格动量（最新收盘价 / N日前收盘价 - 1），数据不足返回 None。"""
    if series is None or len(series) < days + 2:
        return None
    return float(series.iloc[-1] / series.iloc[-days - 1] - 1)


# ── 核心数据拉取 ────────────────────────────────────────────────────────────────

def fetch_sector_rotation_data() -> tuple[pd.DataFrame | None, dict | None, str | None]:
    """
    拉取全部 ETF 并计算动量排名。

    Returns:
        (df_ranked, spy_moms, data_date)
          df_ranked : 按 rel_3M 排序的 DataFrame，列含 ticker/name/close/r_1M/r_3M/rel_1M/rel_3M/rank_3M
          spy_moms  : {"1M": float, "3M": float}
          data_date : 最新数据日期字符串 "YYYY-MM-DD"
        若 SPY 数据缺失，三项均返回 None。
    """
    all_tickers = {"SPY": "S&P500基准", **SECTOR_ETFS}
    closes: dict[str, pd.Series] = {}

    for ticker in all_tickers:
        s = _fetch_etf(ticker)
        if s is not None:
            closes[ticker] = s
            logger.info(f"[SR] {ticker} ✓ {len(s)}行，最新 {s.index[-1].strftime('%Y-%m-%d')}，收盘 {s.iloc[-1]:.2f}")
        time.sleep(_FETCH_DELAY)

    logger.info(f"[SR] 获取 {len(closes)}/{len(all_tickers)} 个 ticker")

    if "SPY" not in closes:
        logger.error("[SR] SPY 基准缺失，终止")
        return None, None, None

    spy = closes["SPY"]
    spy_moms = {lb: _calc_momentum(spy, days) for lb, days in LOOKBACKS.items()}
    data_date = spy.index[-1].strftime("%Y-%m-%d")

    rows = []
    for ticker, name in SECTOR_ETFS.items():
        if ticker not in closes:
            continue
        s = closes[ticker]
        moms   = {lb: _calc_momentum(s, days) for lb, days in LOOKBACKS.items()}
        rel    = {
            lb: (moms[lb] - spy_moms[lb])
            if moms[lb] is not None and spy_moms[lb] is not None
            else None
            for lb in LOOKBACKS
        }
        rows.append({
            "ticker": ticker,
            "name":   name,
            "close":  float(s.iloc[-1]),
            "r_1M":   moms["1M"],
            "r_3M":   moms["3M"],
            "rel_1M": rel["1M"],
            "rel_3M": rel["3M"],
        })

    if not rows:
        logger.error("[SR] 无可用行业 ETF 数据")
        return None, None, None

    df = pd.DataFrame(rows).sort_values("rel_3M", ascending=False, na_position="last").reset_index(drop=True)
    df["rank_3M"] = range(1, len(df) + 1)

    return df, spy_moms, data_date


# ── 格式化输出 ──────────────────────────────────────────────────────────────────

def format_sector_rotation_context(
    df: pd.DataFrame,
    spy_moms: dict,
    data_date: str,
) -> str:
    """
    将动量排名 DataFrame 转换为 LLM 可读的文字摘要。
    格式与 sector_rotation_analysis.md SKILL.md 的输出规范对齐。
    """
    def _pct(v):
        return f"{v:+.1%}" if v is not None else "N/A"

    lines = []
    lines.append(f"【行业轮动数据 — 数据至 {data_date}】")
    lines.append(
        f"SPY基准：1M={_pct(spy_moms.get('1M'))}  3M={_pct(spy_moms.get('3M'))}"
    )
    lines.append("")

    # 排名明细表
    header = f"{'排名':<4} {'Ticker':<6} {'名称':<10} {'1M绝对':<9} {'3M绝对':<9} {'1M超额':<9} {'3M超额':<9}"
    lines.append(header)
    lines.append("-" * 60)
    for _, row in df.iterrows():
        lines.append(
            f"#{int(row['rank_3M']):<3} {row['ticker']:<6} {row['name']:<10} "
            f"{_pct(row['r_1M']):<9} {_pct(row['r_3M']):<9} "
            f"{_pct(row['rel_1M']):<9} {_pct(row['rel_3M']):<9}"
        )

    lines.append("")

    # 信号摘要（供报告直接引用）
    top3 = df.head(3)["ticker"].tolist()
    bot3 = df.tail(3)["ticker"].tolist()

    top3_detail = " / ".join(
        f"{r['ticker']}({_pct(r['rel_3M'])})"
        for _, r in df.head(3).iterrows()
    )
    bot3_detail = " / ".join(
        f"{r['ticker']}({_pct(r['rel_3M'])})"
        for _, r in df.tail(3).iterrows()
    )

    lines.append(f"领涨行业（3M超额前3）: {top3_detail}")
    lines.append(f"滞涨行业（3M超额末3）: {bot3_detail}")

    # 1M与3M方向一致性检查
    top3_1m_tickers = set(df[df["rel_1M"].notna()].nlargest(3, "rel_1M")["ticker"].tolist())
    top3_3m_tickers = set(top3)
    if not top3_1m_tickers.intersection(top3_3m_tickers):
        lines.append("⚠️  1M超额前3与3M超额前3无重叠，近期出现轮动方向反转，请在报告中注明。")

    # 异常信号检测（对应 SKILL.md Step 3）
    anomalies = _detect_anomalies(df)
    if anomalies:
        lines.append("")
        lines.append("【异常信号】")
        lines.extend(anomalies)

    return "\n".join(lines)


def _detect_anomalies(df: pd.DataFrame) -> list[str]:
    """检测 SKILL.md Step 3 定义的5种异常组合（仅有数据时触发）"""
    alerts = []

    # 获取各 ticker 的 rel_1M/rel_3M 映射
    rel3  = dict(zip(df["ticker"], df["rel_3M"]))
    rel1  = dict(zip(df["ticker"], df["rel_1M"]))

    top3 = df.head(3)["ticker"].tolist()
    bot3 = df.tail(3)["ticker"].tolist()

    # ① 全防御领涨（XLU/XLP/XLV 同时在 Top3）
    defensive = {"XLU", "XLP", "XLV"}
    if defensive.issubset(set(top3)):
        alerts.append("⚠️  XLU/XLP/XLV 三大防御全部领涨 → 强防御轮动信号，通常领先 risk-off/stress 4–8周。")

    # ② XLE+XLB 同时领涨
    if "XLE" in top3 and "XLB" in top3:
        alerts.append("⚠️  XLE+XLB 同时领涨 → 能源+材料驱动，注意区分通胀驱动与全面经济复苏；若PMI<50则为滞胀信号。")

    # ③ XLK 1M超额 > +8%（VIX 需外部数据，此处仅触发提示）
    xlk_1m = rel1.get("XLK")
    if xlk_1m is not None and xlk_1m > 0.08:
        alerts.append(f"⚠️  XLK 1M超额={xlk_1m:+.1%} > +8% → 需核查 VIX；若VIX>25则存在集中度风险（AI/少数个股驱动），非广泛risk-on。")

    # ④ 所有行业超额绝对值均 < 2%
    valid_rel3 = [v for v in rel3.values() if v is not None]
    if valid_rel3 and max(abs(v) for v in valid_rel3) < 0.02:
        alerts.append("⚠️  所有行业3M超额绝对值均 < 2% → 行业离散度极低，市场处于等待模式，不宜过度解读。")

    return alerts


# ── 对外主入口 ──────────────────────────────────────────────────────────────────

def get_sector_rotation_context() -> str | None:
    """
    主入口：拉取数据 + 计算 + 格式化。
    供 run_macro_analysis.py 调用，返回可直接注入 LLM prompt 的字符串。
    失败时返回 None（调用方降级处理）。
    """
    logger.info("[SR] 开始获取行业轮动数据...")
    try:
        df, spy_moms, data_date = fetch_sector_rotation_data()
        if df is None:
            return None
        ctx = format_sector_rotation_context(df, spy_moms, data_date)
        logger.info(f"[SR] 行业轮动数据就绪，数据至 {data_date}")
        return ctx
    except Exception as e:
        logger.error(f"[SR] get_sector_rotation_context 异常: {e}")
        return None


# ── 本地调试入口 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    result = get_sector_rotation_context()
    if result:
        print(result)
    else:
        print("数据获取失败", file=sys.stderr)
        sys.exit(1)
