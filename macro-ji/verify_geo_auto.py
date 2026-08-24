# -*- coding: utf-8 -*-
"""verify_geo_auto.py — 地缘预测自动验证（L1 FRED 官方数据，08-18 批次1）

到期（due_at 已过）的 awaiting_human geo 预测，按 action_key 分派到自动判定器：

  A1:CUT_*/HIKE_*   → 联邦基金利率方向（DFF.csv）
  A2:TIGHTEN/EASE   → 信贷利差走阔/收窄（BAA10Y − DGS10）
  A3:SHORT_MARKET   → 恐慌做空环境（VIXCLS 历史分位）
  A6:AMPLIFY_FEAR / NEUTRAL_REPORT / AMPLIFY_OPTIMISM → 媒体情绪（VIXCLS 分位代理；
                      后续批次接 GDELT tone 精确化）

判定成功 → UPDATE predictions SET status='verified', outcome_value, brier_score,
verified_by='auto', human_note='【自动】…依据…'（与人工 verified_by='human' 区分）。
幂等：仅 awaiting_human；L2/L3 动作（无判定器）跳过保留人工。
--dry-run：只计算打印不写库（测试用）。

用法：python3 verify_geo_auto.py [--dry-run] [--grace-days 30]
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta

DATA_DIR = os.environ.get("OPENCLAW_WORKSPACE", "/workspace") + "/data"
FRED_DIR = os.path.join(DATA_DIR, "fred_history")
GRACE_DAYS = 30      # due_at 后缓冲天数（数据滞后容差）
AUTO_VERIFIED_BY = "auto"
# L1 判定器分派（action_key 前缀 → 判定函数）
L1_PREFIXES = ("A1:", "A2:", "A3:", "A6:")

# ── L2 新闻关键词判定器（08-18 批次2）────────────────────────
# action_key → 关键词组列表：每组内 AND、组间 OR；标题命中任一组 → 发生确认（1）。
# 设计：L2 只做"发生确认"（新闻命中是强证据）；未命中 → None 保留人工
# （新闻源覆盖有限，未命中不能断言未发生）。
L2_KEYWORDS: dict[str, list[list[str]]] = {
    "A12:ABANDON_YCC":    [["日本央行", "YCC"], ["BOJ", "YCC"], ["yield curve control", "japan"]],
    "A12:EASE_YCC":       [["日本央行", "YCC"], ["BOJ", "YCC"]],
    "A12:EMERGENCY_EASE": [["日本央行", "宽松"], ["BOJ", "ease"]],
    "A8:CUT_RRR":         [["央行", "降准"], ["人民银行", "降准"], ["reserve requirement", "cut", "china"]],
    "A8:CUT_LPR":         [["LPR", "下调"], ["LPR", "降"], ["loan prime rate", "cut"]],
    "A8:FISCAL_STIMULUS_CN": [["财政刺激"], ["fiscal stimulus", "china"]],
    "A8:CNY_INTERVENTION":   [["人民币", "干预"], ["yuan", "intervention"]],
    "A4:CUT_OUTPUT":      [["OPEC", "减产"], ["OPEC", "cut"]],
    "A4:CUT_SUPPLY":      [["OPEC", "减产"], ["OPEC", "cut"]],
    "A4:INCREASE_OUTPUT": [["OPEC", "增产"], ["OPEC", "increase"]],
    "A4:INCREASE_SUPPLY": [["OPEC", "增产"], ["OPEC", "increase"]],
    "A9:DEBT_CEILING_RISK": [["债务上限"], ["debt ceiling"]],
    "A9:FISCAL_STIMULUS":   [["财政刺激"], ["fiscal stimulus"]],
    "A7:CAPITAL_CONTROLS":  [["资本管制"], ["capital control"]],
    "S1_usa:IMPOSE_SANCTIONS": [["美国", "制裁"], ["US", "sanctions"]],
    "S2_china:IMPOSE_SANCTIONS": [["中国", "制裁"], ["China", "sanctions"]],
    "S3_eu:IMPOSE_SANCTIONS":   [["欧盟", "制裁"], ["EU", "sanctions"]],
    "S4_russia:IMPOSE_SANCTIONS": [["俄罗斯", "制裁"], ["Russia", "sanctions"]],
    "S5_saudi:EMBARGO_SIGNAL":  [["沙特", "封锁"], ["Saudi", "embargo"]],
    "S4_russia:NUCLEAR_SIGNAL": [["核威慑"], ["nuclear", "drill"]],
    "S4_russia:ENERGY_CUTOFF":  [["俄罗斯", "断供"], ["Russia", "gas cut"]],
}
L2_CONFIRM_CONFIDENCE = 0.6


def _load_news(start: datetime, end: datetime) -> list[dict]:
    """查 PG news.articles（90 天保留，08-18 实测 3.4 万篇覆盖 3 个月）。

    比 news_all.json 快照（仅当天）完整得多——L2 验证窗口（due_at 起 30 天）
    到期时查，窗口内文章必然在保留期内。缓存按窗口 key。
    """
    cache_key = (start.date().isoformat(), end.date().isoformat())
    if cache_key in _news_cache:
        return _news_cache[cache_key]
    rows: list[dict] = []
    try:
        from pg_read import connect
        conn = connect()
        if conn is not None:
            try:
                cur = conn.execute(
                    "SELECT title, source FROM news.articles "
                    "WHERE published_at >= %s AND published_at < %s "
                    "ORDER BY published_at DESC LIMIT 8000",
                    (start.isoformat(), end.isoformat()))
                for r in cur.fetchall():
                    rows.append({"title": r[0] or "", "source": r[1] or ""})
            finally:
                conn.close()
    except Exception:
        pass
    _news_cache[cache_key] = rows
    return rows


_news_cache: dict[tuple[str, str], list[dict]] = {}


def _pg_conn():
    import psycopg
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        sys.exit("[verify_geo_auto] WORLDSIM_APP_PW 未注入（fail-fast）")
    last_err = None
    for attempt in range(3):
        try:
            return psycopg.connect(
                host="worldsim-pg", port=5432, dbname="worldsim", user="worldsim_app",
                password=pw, options="-c search_path=tianji,public")
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    sys.exit(f"[verify_geo_auto] 连接失败：{last_err}")


# ── FRED 序列加载 ────────────────────────────────────────────

_series_cache: dict[str, list[tuple[datetime, float]]] = {}


def _load_series(series_id: str) -> list[tuple[datetime, float]]:
    """加载 fred_history/{id}.csv → [(date, value)] 升序。缓存。"""
    if series_id in _series_cache:
        return _series_cache[series_id]
    path = os.path.join(FRED_DIR, f"{series_id}.csv")
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in csv.reader(f):
                if len(line) < 2 or line[0] == "date":
                    continue
                try:
                    rows.append((datetime.strptime(line[0], "%Y-%m-%d"), float(line[1])))
                except (ValueError, IndexError):
                    continue
    rows.sort(key=lambda r: r[0])
    _series_cache[series_id] = rows
    return rows


def _window_mean(series: list[tuple[datetime, float]], start: datetime, end: datetime) -> float | None:
    """序列在 [start, end) 的均值；无数据返回 None。"""
    vals = [v for d, v in series if start <= d < end]
    return sum(vals) / len(vals) if vals else None


def _value_at(series: list[tuple[datetime, float]], at: datetime) -> float | None:
    """<= at 的最近一个值（无未来函数）。"""
    last = None
    for d, v in series:
        if d <= at:
            last = v
        else:
            break
    return last


def _percentile_hist(series: list[tuple[datetime, float]], before: datetime, pct: float) -> float | None:
    """before 之前 5 年的 pct 分位（历史基准，防未来函数）。"""
    cutoff = before - timedelta(days=365 * 5)
    vals = sorted(v for d, v in series if cutoff <= d <= before)
    if not vals:
        return None
    idx = int((len(vals) - 1) * pct)
    return vals[idx]


# ── 判定器（返回 outcome/置信度/依据；None outcome = 无法判定）──────────

def _judge_rate(action: str, base_dff: float, win_dff: float) -> tuple[float, str]:
    """利率方向判定：CUT=窗口低于 base；HIKE=高于 base。"""
    if "CUT" in action:
        if win_dff < base_dff - 0.10:
            return 1.0, f"实际利率 {win_dff:.2f}% < 预测日 {base_dff:.2f}%（降息落地）"
        if win_dff > base_dff + 0.10:
            return 0.0, f"实际利率 {win_dff:.2f}% > 预测日 {base_dff:.2f}%（未降息）"
        return 0.5, f"利率基本持平（{base_dff:.2f}%→{win_dff:.2f}%）"
    if "HIKE" in action:
        if win_dff > base_dff + 0.10:
            return 1.0, f"实际利率 {win_dff:.2f}% > 预测日 {base_dff:.2f}%（加息落地）"
        if win_dff < base_dff - 0.10:
            return 0.0, f"实际利率 {win_dff:.2f}% < 预测日 {base_dff:.2f}%（未加息）"
        return 0.5, f"利率基本持平（{base_dff:.2f}%→{win_dff:.2f}%）"
    return None, "无利率方向判定器"


def _judge_spread(action: str, base_sp: float, win_sp: float) -> tuple[float, str]:
    """信贷利差判定（bp）。"""
    base_bp, win_bp = base_sp * 100, win_sp * 100
    if "TIGHTEN" in action:
        if win_bp > base_bp + 15:
            return 1.0, f"利差走阔 {base_bp:.0f}→{win_bp:.0f}bp（信贷收紧）"
        if win_bp < base_bp - 15:
            return 0.0, f"利差收窄 {base_bp:.0f}→{win_bp:.0f}bp（未收紧）"
        return 0.5, f"利差基本持平（{base_bp:.0f}→{win_bp:.0f}bp）"
    if "EASE" in action:
        if win_bp < base_bp - 15:
            return 1.0, f"利差收窄 {base_bp:.0f}→{win_bp:.0f}bp（信贷放松）"
        if win_bp > base_bp + 15:
            return 0.0, f"利差走阔 {base_bp:.0f}→{win_bp:.0f}bp（未放松）"
        return 0.5, f"利差基本持平（{base_bp:.0f}→{win_bp:.0f}bp）"
    return None, "无利差判定器"


def _judge_vix_pct(action: str, win_vix: float, p90: float, p70: float, p60: float, p40: float) -> tuple[float, str]:
    """VIX 分位判定（恐慌/中性/乐观）。"""
    if "AMPLIFY_FEAR" in action:
        if win_vix > p90:
            return 1.0, f"VIX 窗口均值 {win_vix:.1f} > 历史90分位 {p90:.1f}（恐慌环境）"
        if win_vix < p70:
            return 0.0, f"VIX 窗口均值 {win_vix:.1f} < 历史70分位 {p70:.1f}（未恐慌）"
        return 0.5, f"VIX 窗口均值 {win_vix:.1f}（介于70-90分位）"
    if "NEUTRAL_REPORT" in action:
        if win_vix < p60:
            return 1.0, f"VIX 窗口均值 {win_vix:.1f} < 历史60分位 {p60:.1f}（情绪中性）"
        if win_vix > p90:
            return 0.0, f"VIX 窗口均值 {win_vix:.1f} > 历史90分位 {p90:.1f}（非中性）"
        return 0.5, f"VIX 窗口均值 {win_vix:.1f}（60-90 分位之间）"
    if "AMPLIFY_OPTIMISM" in action:
        if win_vix < p40:
            return 1.0, f"VIX 窗口均值 {win_vix:.1f} < 历史40分位 {p40:.1f}（低波动乐观）"
        if win_vix > p70:
            return 0.0, f"VIX 窗口均值 {win_vix:.1f} > 历史70分位 {p70:.1f}（非乐观）"
        return 0.5, f"VIX 窗口均值 {win_vix:.1f}（40-70 分位之间）"
    if "SHORT_MARKET" in action:
        if win_vix > p90:
            return 1.0, f"VIX 窗口均值 {win_vix:.1f} > 历史90分位 {p90:.1f}（恐慌做空环境）"
        if win_vix < p70:
            return 0.0, f"VIX 窗口均值 {win_vix:.1f} < 历史70分位 {p70:.1f}（非恐慌）"
        return 0.5, f"VIX 窗口均值 {win_vix:.1f}（70-90 分位之间）"
    return None, "无 VIX 判定器"


# ── 主流程 ────────────────────────────────────────────────────

def judge(action_key: str, created_at: datetime, due_at: datetime) -> tuple[float | None, float, str]:
    """按 action_key 分派 L1 判定器。返回 (outcome, confidence, note)；outcome=None 跳过。"""
    prefix = action_key.split(":", 1)[0] + ":"
    win_start = due_at
    win_end = due_at + timedelta(days=GRACE_DAYS)

    if prefix == "A1:":
        dff = _load_series("DFF")
        base = _value_at(dff, created_at)
        win = _window_mean(dff, win_start, win_end)
        if base is None or win is None:
            return None, 0.0, "DFF 数据不足"
        out, note = _judge_rate(action_key, base, win)
        return out, 0.8, note

    if prefix == "A2:":
        baa = _load_series("BAA10Y")
        d10 = _load_series("DGS10")
        base_b = _value_at(baa, created_at)
        base_d = _value_at(d10, created_at)
        win_b = _window_mean(baa, win_start, win_end)
        win_d = _window_mean(d10, win_start, win_end)
        if None in (base_b, base_d, win_b, win_d):
            return None, 0.0, "利差数据不足"
        out, note = _judge_spread(action_key, base_b - base_d, win_b - win_d)
        return out, 0.8, note

    if prefix in ("A3:", "A6:"):
        vix = _load_series("VIXCLS")
        win = _window_mean(vix, win_start, win_end)
        p90 = _percentile_hist(vix, created_at, 0.90)
        p70 = _percentile_hist(vix, created_at, 0.70)
        p60 = _percentile_hist(vix, created_at, 0.60)
        p40 = _percentile_hist(vix, created_at, 0.40)
        if win is None or p90 is None:
            return None, 0.0, "VIX 数据不足"
        out, note = _judge_vix_pct(action_key, win, p90, p70, p60, p40)
        return out, 0.8, note

    # ── L2 新闻关键词（08-18 批次2）：命中 → 1（发生确认）；未命中 → None（人工兜底）
    if action_key in L2_KEYWORDS:
        arts = _load_news(win_start, win_end)
        if not arts:
            return None, 0.0, "新闻数据不足（窗口内无文章）"
        for art in arts:
            text = f"{art.get('title') or ''} {art.get('source') or ''}"
            tl = text.lower()
            for group in L2_KEYWORDS[action_key]:
                if all(kw.lower() in tl for kw in group):
                    return 1.0, L2_CONFIRM_CONFIDENCE, f"新闻命中：{art.get('title', '')[:60]}"
        return None, 0.0, "新闻未命中（L2 仅单向确认，未命中保留人工）"

    return None, 0.0, "无判定器（L3 人工）"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="只计算打印不写库")
    p.add_argument("--grace-days", type=int, default=GRACE_DAYS)
    args = p.parse_args()

    conn = _pg_conn()
    cur = conn.execute(
        "SELECT id, action_key, created_at, due_at, final_prob, content "
        "FROM predictions WHERE status = 'awaiting_human' AND action_key IS NOT NULL "
        "AND due_at IS NOT NULL")
    rows = [dict(zip([d.name for d in cur.description], r)) for r in cur.fetchall()]
    now = datetime.now().astimezone()
    due_cutoff = now - timedelta(days=args.grace_days)
    due_rows = [r for r in rows
                if isinstance(r["due_at"], datetime) and r["due_at"] <= due_cutoff]
    print(f"[verify_geo_auto] 待人工 {len(rows)} 条，已到期（含 {args.grace_days} 天缓冲）{len(due_rows)} 条")

    auto_ok = auto_skip = 0
    for r in due_rows:
        key = r["action_key"] or ""
        # 08-18 修复 P1-1：此前只放行 L1_PREFIXES，L2 键（A12:/A8:/A4:/A9:/A7:/S*）全被
        # continue 跳过 → L2 判定器永不达（审计 world-sim-audit-20260818 实锤）
        if not (key.startswith(L1_PREFIXES) or key in L2_KEYWORDS):
            auto_skip += 1
            continue
        outcome, conf, note = judge(key, r["created_at"], r["due_at"])
        if outcome is None:
            auto_skip += 1
            continue
        brier = round((r["final_prob"] - outcome) ** 2, 4)
        if args.dry_run:
            print(f"  [dry] {r['id'][:12]}… {key} | outcome={outcome} | {note}")
            continue
        with conn:
            conn.execute(
                "UPDATE predictions SET status='verified', outcome_value=%s, brier_score=%s, "
                "verified_at=CURRENT_TIMESTAMP, verified_by='auto', human_note=%s WHERE id=%s",
                (outcome, brier, f"【自动】{note}", r["id"]))
        print(f"  [auto] {r['id'][:12]}… {key} | outcome={outcome} brier={brier} | {note}")
        auto_ok += 1

    print(f"[verify_geo_auto] 自动验证 {auto_ok} 条，跳过（L2/L3/数据不足）{auto_skip} 条"
          f"{'（dry-run 未写库）' if args.dry_run else '（已写库）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
