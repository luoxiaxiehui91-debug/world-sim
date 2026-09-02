"""
模块02（v2）：自动验证引擎
修复：
  - accuracy key 统一为 gdp_hit / unrate_hit / cpi_hit（与模块01/06一致）
  - 新增 CPI YoY 计算（CPIAUCSL 月环比→同比）
  - FRED 数据加时效校验（超过 FRED_MAX_LAG_DAYS 不验证）
  - 防止重复验证（已 verified 的记录跳过）
  - 推送改用 push_utils
  - baseline_cn 场景使用中国专属 FRED 系列（CHNCPIALLMINMEI / LRUNTTTTCNM156S）
"""
import json
import math
import os
from datetime import date, datetime, timedelta

try:
    from fredapi import Fred
except ImportError:
    raise ImportError("请先安装: pip install fredapi")

from optim_config import (PREDICTIONS_LOG, FRED_API_KEY, FRED_MAX_LAG_DAYS,
                    GDP_HIT_TOLERANCE, UNRATE_HIT_TOLERANCE, CPI_HIT_TOLERANCE)

# 中国 FRED 系列映射
# CHNCPIALLMINMEI: 中国 CPI 月度（指数值，需自行计算 YoY）
# LRUNTTTTCNM156S: 中国协调失业率（月度，NBS季调）
_CN_SERIES = {
    "cpi_index": "CHNCPIALLMINMEI",
    "unrate":    "LRUNTTTTCNM156S",
}


def fetch_series(series_id: str, fred: "Fred", start: str) -> list[tuple]:
    """
    返回 [(date, value), ...] 列表，已去除 NaN，按日期升序。
    """
    try:
        s = fred.get_series(series_id, observation_start=start)
        if s is None or len(s) == 0:
            return []
        return [(d.date(), float(v))
                for d, v in s.items()
                if not math.isnan(v)]
    except Exception as e:
        print(f"  [FRED] {series_id} 获取失败: {e}")
        return []


def closest_value(series: list[tuple], target: date) -> tuple[float | None, int]:
    """
    找最接近 target 的数据点，返回 (value, lag_days)。
    lag_days > FRED_MAX_LAG_DAYS 表示数据太旧，不可信。
    """
    if not series:
        return None, 9999
    closest = min(series, key=lambda x: abs((x[0] - target).days))
    lag = abs((closest[0] - target).days)
    return closest[1], lag


def compute_cpi_yoy(fred: "Fred", target: date) -> float | None:
    """
    从 CPIAUCSL 月度数据计算 target 日期附近的 YoY 同比（%）。
    """
    start = (target.replace(year=target.year - 2)).isoformat()
    series = fetch_series("CPIAUCSL", fred, start)
    if len(series) < 13:
        return None
    # 找 target 附近的值，和12个月前的值
    val_now, lag_now = closest_value(series, target)
    val_12m, lag_12m = closest_value(series, date(target.year - 1, target.month, 1))
    if val_now is None or val_12m is None or val_12m == 0:
        return None
    if lag_now > FRED_MAX_LAG_DAYS or lag_12m > FRED_MAX_LAG_DAYS:
        return None
    return round((val_now / val_12m - 1) * 100, 3)


def compute_china_cpi_yoy(fred: "Fred", target: date) -> float | None:
    """
    从 CHNCPIALLMINMEI 月度指数计算中国 CPI YoY（%）。
    """
    start = (target.replace(year=target.year - 2)).isoformat()
    series = fetch_series(_CN_SERIES["cpi_index"], fred, start)
    if len(series) < 13:
        return None
    val_now, lag_now = closest_value(series, target)
    val_12m, lag_12m = closest_value(series, date(target.year - 1, target.month, 1))
    if val_now is None or val_12m is None or val_12m == 0:
        return None
    if lag_now > FRED_MAX_LAG_DAYS or lag_12m > FRED_MAX_LAG_DAYS:
        return None
    return round((val_now / val_12m - 1) * 100, 3)


def verify_one(entry: dict, fred: "Fred") -> dict:
    """
    对单条预测记录执行验证，返回填入 actuals 和 accuracy 后的 entry。
    根据 scenario 字段自动切换 US / China 数据源。
    """
    if entry.get("status") == "verified":
        return entry   # 已验证，跳过

    scenario = entry.get("scenario", "baseline")
    is_china = scenario in ("baseline_cn",)

    target = datetime.strptime(entry["verify_after"], "%Y-%m-%d").date()
    pred = entry.get("predictions", {})
    start = (target - timedelta(days=90)).isoformat()

    actuals = {}
    accuracy = {}

    if is_china:
        # ── 中国：CPI YoY ────────────────────────────────────────────────────
        cn_cpi = compute_china_cpi_yoy(fred, target)
        if cn_cpi is not None:
            actuals["cpi_yoy"] = cn_cpi
            p = pred.get("cpi_yoy_p50")
            if p is not None:
                err = cn_cpi - p
                accuracy["cpi_error"] = round(err, 3)
                accuracy["cpi_hit"] = abs(err) <= CPI_HIT_TOLERANCE
        # ── 中国：失业率（协调，LRUNTTTTCNM156S）───────────────────────────
        cn_unrate_series = fetch_series(_CN_SERIES["unrate"], fred, start)
        cn_unrate, cn_unrate_lag = closest_value(cn_unrate_series, target)
        if cn_unrate is not None and cn_unrate_lag <= FRED_MAX_LAG_DAYS:
            actuals["unemployment"] = round(cn_unrate, 3)
            p = pred.get("unrate_p50")
            if p is not None:
                err = cn_unrate - p
                accuracy["unrate_error"] = round(err, 3)
                accuracy["unrate_hit"] = abs(err) <= UNRATE_HIT_TOLERANCE
        # 中国 GDP（年度，FRED无季度数据）— 跳过，标记为不可验证
        actuals["gdp_note"] = "中国GDP为年度数据，3个月验证期内通常不可用"
    else:
        # ── GDP 增速 ──────────────────────────────────────────────────────────
        gdp_series = fetch_series("A191RL1Q225SBEA", fred, start)
        gdp_val, gdp_lag = closest_value(gdp_series, target)
        if gdp_val is not None and gdp_lag <= FRED_MAX_LAG_DAYS:
            actuals["gdp_growth"] = round(gdp_val, 3)
            p = pred.get("gdp_p50")
            if p is not None:
                err = gdp_val - p
                accuracy["gdp_error"] = round(err, 3)
                accuracy["gdp_abs_error"] = round(abs(err), 3)
                accuracy["gdp_hit"] = abs(err) <= GDP_HIT_TOLERANCE
                accuracy["gdp_in_range"] = (
                    (pred.get("gdp_p10") or -999) <= gdp_val <= (pred.get("gdp_p90") or 999)
                )
        else:
            print(f"  GDP 数据滞后 {gdp_lag}天，超过阈值，跳过验证。")

        # ── 失业率 ────────────────────────────────────────────────────────────
        unrate_series = fetch_series("UNRATE", fred, start)
        unrate_val, unrate_lag = closest_value(unrate_series, target)
        if unrate_val is not None and unrate_lag <= FRED_MAX_LAG_DAYS:
            actuals["unemployment"] = round(unrate_val, 3)
            p = pred.get("unrate_p50")
            if p is not None:
                err = unrate_val - p
                accuracy["unrate_error"] = round(err, 3)
                accuracy["unrate_hit"] = abs(err) <= UNRATE_HIT_TOLERANCE

        # ── CPI YoY ───────────────────────────────────────────────────────────
        cpi_yoy = compute_cpi_yoy(fred, target)
        if cpi_yoy is not None:
            actuals["cpi_yoy"] = cpi_yoy
            p = pred.get("cpi_yoy_p50")
            if p is not None:
                err = cpi_yoy - p
                accuracy["cpi_error"] = round(err, 3)
                accuracy["cpi_hit"] = abs(err) <= CPI_HIT_TOLERANCE

    entry["actuals"] = actuals
    entry["accuracy"] = accuracy
    # gdp_note 是纯注释字段，不算真实数据；需至少一个真实指标才视为已验证
    has_real_data = any(k != "gdp_note" for k in actuals)
    entry["status"] = "verified" if has_real_data else "data_unavailable"
    entry["verified_at"] = datetime.now().isoformat()
    return entry


def compute_aggregate_metrics(verified: list[dict]) -> str:
    """
    计算全部已验证记录的聚合精度指标：
      - MAE / RMSE：GDP、CPI、失业率
      - 方向准确率：预测高于/低于当前值的方向是否正确
      - Brier Score：衰退概率预测校准（0=完美，0.25=随机，越低越好）
    """
    import math

    gdp_errors, cpi_errors, unrate_errors = [], [], []
    gdp_dir_correct, gdp_dir_total = 0, 0
    brier_sum, brier_n = 0.0, 0

    for r in verified:
        p   = r.get("predictions", {})
        a   = r.get("actuals", {})
        acc = r.get("accuracy", {})

        # GDP MAE/RMSE
        gdp_err = acc.get("gdp_error")
        if gdp_err is not None:
            gdp_errors.append(abs(gdp_err))

        # 方向准确率（预测P50 vs 当前快照 vs 实际值）
        gdp_p50    = p.get("gdp_p50")
        gdp_actual = a.get("gdp_growth")
        gdp_snap   = p.get("gdp_snapshot_current")
        if gdp_p50 is not None and gdp_actual is not None and gdp_snap is not None:
            pred_dir   = 1 if gdp_p50 > gdp_snap else -1
            actual_dir = 1 if gdp_actual > gdp_snap else -1
            gdp_dir_total += 1
            if pred_dir == actual_dir:
                gdp_dir_correct += 1

        # CPI MAE
        cpi_err = acc.get("cpi_error")
        if cpi_err is not None:
            cpi_errors.append(abs(cpi_err))

        # 失业率 MAE
        unrate_err = acc.get("unrate_error")
        if unrate_err is not None:
            unrate_errors.append(abs(unrate_err))

        # Brier Score（只对有衰退实际结果的条目：需要 realized_recession 字段）
        rec_prob = p.get("recession_prob_pct")
        realized = a.get("realized_recession")  # 1.0=实际发生衰退, 0.0=未发生
        if rec_prob is not None and realized is not None:
            f = rec_prob / 100.0
            brier_sum += (f - realized) ** 2
            brier_n   += 1

    def _mae(errs): return sum(errs) / len(errs) if errs else None
    def _rmse(errs): return math.sqrt(sum(x**2 for x in errs) / len(errs)) if errs else None

    gdp_mae   = _mae(gdp_errors)
    gdp_rmse  = _rmse(gdp_errors)
    cpi_mae   = _mae(cpi_errors)
    unrate_mae = _mae(unrate_errors)
    brier     = brier_sum / brier_n if brier_n > 0 else None
    dir_acc   = gdp_dir_correct / gdp_dir_total * 100 if gdp_dir_total > 0 else None

    n = len(verified)
    lines = [
        f"\n**聚合精度指标**（基于 {n} 条验证记录）",
        "",
        "| 指标 | 数值 | 说明 |",
        "|:----|:---:|:-----|",
        f"| GDP MAE    | {f'{gdp_mae:.3f}ppt' if gdp_mae is not None else '—'} | 绝对误差均值 |",
        f"| GDP RMSE   | {f'{gdp_rmse:.3f}ppt' if gdp_rmse is not None else '—'} | 均方根误差（惩罚大偏差）|",
        f"| CPI MAE    | {f'{cpi_mae:.3f}ppt' if cpi_mae is not None else '—'} | — |",
        f"| 失业率 MAE | {f'{unrate_mae:.3f}ppt' if unrate_mae is not None else '—'} | — |",
        f"| GDP方向准确率 | {f'{dir_acc:.0f}%（{gdp_dir_correct}/{gdp_dir_total}）' if dir_acc is not None else '—'} | 预测方向正确占比 |",
        f"| Brier Score | {f'{brier:.4f}' if brier is not None else '—'} | 衰退概率校准（0=完美，0.25=随机）|",
    ]
    return "\n".join(lines)


def build_report(results: list[dict]) -> str:
    """将本轮验证结果格式化为 Markdown 报告文本（含命中率、聚合指标、逐条明细）。"""
    verified = [r for r in results if r.get("status") == "verified"]
    if not verified:
        return "本月到期预测均无可用 FRED 数据，暂无验证结果。"

    # 区分美国和中国记录（中国无 GDP hit 指标）
    us_verified = [r for r in verified if r.get("scenario") not in ("baseline_cn",)]
    cn_verified = [r for r in verified if r.get("scenario") in ("baseline_cn",)]

    gdp_hits = [r for r in us_verified if r.get("accuracy", {}).get("gdp_hit") is True]
    gdp_tried = [r for r in us_verified if r.get("accuracy", {}).get("gdp_hit") is not None]
    hit_rate = len(gdp_hits) / len(gdp_tried) * 100 if gdp_tried else 0

    agg_metrics = compute_aggregate_metrics(us_verified)

    lines = [f"📊 **预测验证报告** {date.today().isoformat()}", "",
             f"到期：{len(results)} 条（美国{len(us_verified)} | 中国{len(cn_verified)}）"
             f" | 美国GDP命中率：{hit_rate:.0f}% （±{GDP_HIT_TOLERANCE}ppt）",
             agg_metrics, ""]

    for r in us_verified:
        p, a, acc = r["predictions"], r.get("actuals", {}), r.get("accuracy", {})
        icon = "✅" if acc.get("gdp_hit") else "❌" if acc.get("gdp_hit") is False else "❓"
        lines.append(f"▸ {r['created_at'][:10]} [美国/{r['scenario']}] {icon}")
        if a.get("gdp_growth") is not None:
            lines.append(f"  GDP 预测:{p.get('gdp_p50')}% 实际:{a['gdp_growth']}%"
                         f" 误差:{acc.get('gdp_error'):+.2f}ppt")
        if a.get("unemployment") is not None:
            lines.append(f"  失业率 预测:{p.get('unrate_p50')}% 实际:{a['unemployment']}%")
        if a.get("cpi_yoy") is not None:
            lines.append(f"  CPI YoY 预测:{p.get('cpi_yoy_p50')}% 实际:{a['cpi_yoy']}%")
        lines.append("")

    for r in cn_verified:
        p, a, acc = r["predictions"], r.get("actuals", {}), r.get("accuracy", {})
        cpi_icon = "✅" if acc.get("cpi_hit") else "❌" if acc.get("cpi_hit") is False else "❓"
        lines.append(f"▸ {r['created_at'][:10]} [中国/{r['scenario']}] CPI:{cpi_icon}")
        if a.get("cpi_yoy") is not None:
            lines.append(f"  CPI YoY 预测:{p.get('cpi_yoy_p50')}% 实际:{a['cpi_yoy']}%"
                         f" 误差:{acc.get('cpi_error', 0):+.2f}ppt")
        if a.get("unemployment") is not None:
            lines.append(f"  失业率 预测:{p.get('unrate_p50')}% 实际:{a['unemployment']}%")
        if a.get("gdp_note"):
            lines.append(f"  GDP: {a['gdp_note']}")
        lines.append("")

    return "\n".join(lines)


def run_verification(dry_run: bool = False):
    """读取 predictions_log.json，对所有已到期的 pending 记录执行 FRED 数据验证并写回。
    dry_run=True 时只打印不写文件（用于调试）。"""
    if not os.path.exists(PREDICTIONS_LOG):
        print("预测日志不存在，无需验证。")
        return

    with open(PREDICTIONS_LOG, "r", encoding="utf-8") as f:
        log = json.load(f)

    today = date.today().isoformat()
    pending = [e for e in log
               if e.get("status") == "pending" and e.get("verify_after", "") <= today]

    if not pending:
        print(f"无到期预测（今日：{today}）。")
        return

    if not FRED_API_KEY:
        print("[错误] 未设置 FRED_API_KEY 环境变量。")
        return

    print(f"发现 {len(pending)} 条待验证预测，拉取 FRED 数据...")
    fred = Fred(api_key=FRED_API_KEY)

    results = []
    for entry in pending:
        print(f"  验证 {entry['id'][:8]}… 场景:{entry['scenario']} 期:{entry['verify_after']}")
        entry = verify_one(entry, fred)
        results.append(entry)

    # 2026-09-03 修复 dry-run 假实现（question 20260903-verify-predictions-dryrun-noop）：
    # dry_run 此前从未被消费，写回段无条件执行——docstring 声称「只打印不写文件」实际照常落盘
    # （09-03 P4 补跑 --dry-run 即改 43 条生产数据实证）。守卫：dry_run=True 打印预览后直接返回。
    if dry_run:
        print(f"[dry-run] 预览 {len(results)} 条验证结果（不写盘）：")
        for _e in results:
            _n = _e.get("human_note") or _e.get("note") or ""
            print(f"  - {_e['id'][:12]}… 状态 → {_e.get('status')} | outcome={_e.get('outcome')} | {_n}")
        print("[dry-run] 未写文件（predictions_log.json 不变）")
        return

    # 写回日志（只更新已验证的条目）
    # H11 (2026-08-16, 全量审查): 原子写——原直接 open("w") 写目标文件，
    # 写一半崩溃留半截 JSON（下游 JSON.load 损坏）。tmp + os.replace 保证
    # 读者永远看到完整文件（prediction_logger.py 已原子写，此处补齐）。
    id_map = {e["id"]: e for e in results}
    for i, e in enumerate(log):
        if e["id"] in id_map:
            log[i] = id_map[e["id"]]
    tmp = PREDICTIONS_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PREDICTIONS_LOG)
    print(f"已更新 {len(results)} 条记录。")

    report = build_report(results)
    print(report)
    print("\n[验证] 推送功能已禁用（使用 print 输出）")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="只打印不写盘（预览）")
    args = p.parse_args()
    run_verification(dry_run=args.dry_run)
