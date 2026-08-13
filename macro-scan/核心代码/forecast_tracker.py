"""
forecast_tracker.py — 预测追踪与回测评估系统

功能：
  1. SQLite 持久化存储每次 MC 预测（完整概率分布 + 快照）
  2. 从现有 predictions_log.json 自动导入历史记录
  3. verify_after 到期后，从 FRED 拉取真实数据，规则打标签（RECESSION/SOFT_LANDING等）
  4. Brier Score + Brier Skill Score 评估
  5. 供 run_macro_analysis.py 调用

用法：
  from forecast_tracker import ForecastTracker
  tracker = ForecastTracker()
  tracker.log_forecast(probs, predictions, input_state, scenario="baseline", ...)
  tracker.run_evaluation()          # verify_after 到期后评估
  tracker.summary()                 # 打印当前状态
  tracker.brier_report()            # 打印 Brier Score 报告
"""

import os
import sqlite3
import json
import math
import sys
from datetime import datetime, date, timezone
from optim_config import now_iso_utc
from pathlib import Path
from typing import Optional
# E0-A: 旁路双写 worldsim-pg（非阻断，异常自吞，绝不阻断 SQLite 主流程）
from pg_write_collection import (
    upsert_forecast, update_forecast_status, upsert_actual, upsert_evaluation,
)
try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    raise ImportError("请先安装: pip install python-dateutil")

try:
    from optim_config import FRED_API_KEY
except ImportError:
    FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH  = os.path.join(DATA_DIR, "forecast_tracker.db")
JSON_LOG = os.path.join(DATA_DIR, "predictions_log.json")

REGIMES = ["recession", "deep_recession", "soft_landing", "stagflation", "crisis_vix"]


# ── 数据库初始化 ──────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS forecasts (
    id                  TEXT PRIMARY KEY,
    created_at          TEXT NOT NULL,
    scenario            TEXT NOT NULL DEFAULT 'baseline',
    horizon_months      INTEGER NOT NULL DEFAULT 3,
    verify_after        TEXT NOT NULL,
    country             TEXT NOT NULL DEFAULT 'us',
    status              TEXT NOT NULL DEFAULT 'pending',
    regime              TEXT,
    stress_signals      INTEGER DEFAULT 0,
    prob_recession      REAL,
    prob_deep_recession REAL,
    prob_soft_landing   REAL,
    prob_stagflation    REAL,
    prob_crisis_vix     REAL,
    gdp_p10             REAL,
    gdp_p50             REAL,
    gdp_p90             REAL,
    unrate_p50          REAL,
    cpi_yoy_p50         REAL,
    input_json          TEXT,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS actuals (
    period       TEXT PRIMARY KEY,
    actual_regime TEXT,
    gdp_growth   REAL,
    unemployment REAL,
    cpi_yoy      REAL,
    labeled_at   TEXT,
    label_source TEXT DEFAULT 'RULE',
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS evaluations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    eval_date        TEXT NOT NULL,
    horizon_months   INTEGER,
    n_samples        INTEGER,
    brier_score      REAL,
    brier_skill      REAL,
    recession_brier  REAL,
    soft_landing_brier REAL,
    notes            TEXT
);
"""


_PG_ONLY = os.environ.get("WORLDSIM_SQLITE_OFF", "0") == "1"


class _NoopConn:
    """PG-only 模式下的 SQLite 连接桩：写语句空操作（PG 写路径照常，双写退化为纯 PG）。"""
    row_factory = None

    def execute(self, *a, **k):
        return self

    def executemany(self, *a, **k):
        return self

    def executescript(self, *a, **k):
        return self

    def commit(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def _connect() -> sqlite3.Connection:
    """创建并返回 SQLite 连接，首次运行时自动执行 DDL 建表（forecasts/actuals/evaluations）。"""
    if _PG_ONLY:
        return _NoopConn()
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    conn.commit()
    return conn


# ── E0-C 只读助手（forecast 读路径 → worldsim-pg） ─────────────────────────────

def _pg_fetch(sql, params=()):
    """只读 PG；不可用时返回空列表（多为打印/报告，非阻断）。"""
    import pg_read
    conn = pg_read.connect()
    if conn is None:
        return []
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _pg_fetchone(sql, params=()):
    """只读 PG 单行；不可用时返回 None。"""
    import pg_read
    conn = pg_read.connect()
    if conn is None:
        return None
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


# ── 主类 ──────────────────────────────────────────────────────────────────────

class ForecastTracker:

    def __init__(self):
        self.conn = _connect()
        self._import_json_if_needed()

    # ── 写入 ──────────────────────────────────────────────────────────────────

    def log_forecast(
        self,
        probs: dict,           # {"recession": 0.35, "soft_landing": 0.45, ...}
        predictions: dict,     # {"gdp_p50": 1.4, "unrate_p50": 4.3, ...}
        input_state: dict,     # 输入快照
        scenario: str          = "baseline",
        horizon_months: int    = 3,
        country: str           = "us",
        regime: str            = "normal",
        stress_signals: int    = 0,
        notes: str             = "",
        forecast_id: Optional[str] = None,
    ) -> str:
        """记录一条预测，返回 id"""
        import uuid
        fid = forecast_id or str(uuid.uuid4())[:8]
        now = now_iso_utc()

        # 计算 verify_after（horizon_months 个月后）
        today = date.today()
        if today.month + horizon_months > 12:
            year  = today.year + (today.month + horizon_months - 1) // 12
            month = (today.month + horizon_months - 1) % 12 + 1
        else:
            year  = today.year
            month = today.month + horizon_months
        verify_after = f"{year}-{month:02d}-01"

        # 归一化概率（确保总和=1）
        total = sum(probs.get(r, 0) for r in REGIMES)
        if total > 0 and abs(total - 1.0) > 0.01:
            probs = {r: probs.get(r, 0) / total for r in REGIMES}

        self.conn.execute("""
            INSERT OR IGNORE INTO forecasts
            (id, created_at, scenario, horizon_months, verify_after, country,
             status, regime, stress_signals,
             prob_recession, prob_deep_recession, prob_soft_landing,
             prob_stagflation, prob_crisis_vix,
             gdp_p10, gdp_p50, gdp_p90, unrate_p50, cpi_yoy_p50,
             input_json, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            fid, now, scenario, horizon_months, verify_after, country,
            "pending", regime, stress_signals,
            probs.get("recession"),
            probs.get("deep_recession"),
            probs.get("soft_landing"),
            probs.get("stagflation"),
            probs.get("crisis_vix"),
            predictions.get("gdp_p10"),
            predictions.get("gdp_p50"),
            predictions.get("gdp_p90"),
            predictions.get("unrate_p50"),
            predictions.get("cpi_yoy_p50"),
            json.dumps(input_state, ensure_ascii=False),
            notes,
        ))
        self.conn.commit()
        upsert_forecast(fid, now, scenario, horizon_months, verify_after, country,
                        "pending", regime, stress_signals,
                        probs.get("recession"), probs.get("deep_recession"),
                        probs.get("soft_landing"), probs.get("stagflation"),
                        probs.get("crisis_vix"),
                        predictions.get("gdp_p10"), predictions.get("gdp_p50"),
                        predictions.get("gdp_p90"), predictions.get("unrate_p50"),
                        predictions.get("cpi_yoy_p50"),
                        json.dumps(input_state, ensure_ascii=False), notes)
        return fid

    # ── 从 JSON 日志导入 ──────────────────────────────────────────────────────

    def _import_json_if_needed(self) -> int:
        """首次或有新记录时，从 predictions_log.json 导入到 SQLite"""
        if not os.path.exists(JSON_LOG):
            return 0
        try:
            with open(JSON_LOG, encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            return 0

        imported = 0
        for e in entries:
            fid = e.get("id", "")
            if not fid:
                continue
            cur = _pg_fetchone(
                "SELECT 1 FROM forecast.forecasts WHERE id=%s", (fid,)
            )
            if cur:
                continue  # 已存在

            preds = e.get("predictions", {})
            # 旧格式只有 recession_prob_pct，需推算完整分布（保守假设）
            rec_pct = preds.get("recession_prob_pct", 0)
            rec = rec_pct / 100 if rec_pct > 1 else rec_pct
            probs = {
                "recession":      rec,
                "deep_recession": rec * 0.3,   # 旧格式无法区分，用经验比例
                "soft_landing":   max(0, 1 - rec - 0.1),
                "stagflation":    0.08,
                "crisis_vix":     0.02,
            }
            # 归一化
            t = sum(probs.values())
            probs = {k: v / t for k, v in probs.items()}

            input_snap = e.get("input_snapshot", {})
            self.conn.execute("""
                INSERT OR IGNORE INTO forecasts
                (id, created_at, scenario, horizon_months, verify_after, country,
                 status, regime, stress_signals,
                 prob_recession, prob_deep_recession, prob_soft_landing,
                 prob_stagflation, prob_crisis_vix,
                 gdp_p10, gdp_p50, gdp_p90, unrate_p50, cpi_yoy_p50,
                 input_json, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                fid,
                e.get("created_at", ""),
                e.get("scenario", "baseline"),
                e.get("horizon_months", 3),
                e.get("verify_after", ""),
                "us",
                e.get("status", "pending"),
                e.get("regime", ""),
                e.get("stress_signals", 0),
                probs["recession"],
                probs["deep_recession"],
                probs["soft_landing"],
                probs["stagflation"],
                probs["crisis_vix"],
                preds.get("gdp_p10"),
                preds.get("gdp_p50"),
                preds.get("gdp_p90"),
                preds.get("unrate_p50"),
                preds.get("cpi_yoy_p50"),
                json.dumps(input_snap, ensure_ascii=False),
                "从predictions_log.json导入",
            ))
            upsert_forecast(
                fid, e.get("created_at", ""), e.get("scenario", "baseline"),
                e.get("horizon_months", 3), e.get("verify_after", ""), "us",
                e.get("status", "pending"), e.get("regime", ""), e.get("stress_signals", 0),
                probs["recession"], probs["deep_recession"], probs["soft_landing"],
                probs["stagflation"], probs["crisis_vix"],
                preds.get("gdp_p10"), preds.get("gdp_p50"), preds.get("gdp_p90"),
                preds.get("unrate_p50"), preds.get("cpi_yoy_p50"),
                json.dumps(input_snap, ensure_ascii=False), "从predictions_log.json导入")
            imported += 1

        self.conn.commit()
        return imported

    # ── 评估 ──────────────────────────────────────────────────────────────────

    def run_evaluation(self) -> dict:
        """
        检查所有 verify_after <= 今日 且 status=pending 的记录，
        从 FRED 拉取真实数据，打标签，计算 Brier Score。
        """
        today_str = date.today().isoformat()
        rows = _pg_fetch("""
            SELECT * FROM forecast.forecasts
            WHERE status = 'pending' AND verify_after <= %s
        """, (today_str,))

        if not rows:
            print("  [Tracker] 暂无到期预测记录（verify_after 未到）")
            return {}

        print(f"  [Tracker] 发现 {len(rows)} 条到期预测，开始获取真实数据...")
        evaluated = []

        for row in rows:
            rid = row["id"]
            verify_date = row["verify_after"]
            actual = self._get_actual_regime(verify_date, row["country"])
            if actual is None:
                print(f"    [{rid}] FRED 数据未发布或不足，跳过")
                continue

            # 写入 actuals 表
            self.conn.execute("""
                INSERT OR REPLACE INTO actuals
                (period, actual_regime, gdp_growth, unemployment, cpi_yoy,
                 labeled_at, label_source)
                VALUES (?,?,?,?,?,?,?)
            """, (
                verify_date,
                actual["regime"],
                actual.get("gdp"),
                actual.get("unrate"),
                actual.get("cpi"),
                now_iso_utc(),
                "RULE_FRED",
            ))

            # 更新 forecasts 状态
            self.conn.execute("""
                UPDATE forecasts
                SET status = 'evaluated'
                WHERE id = ?
            """, (rid,))
            upsert_actual(
                verify_date, actual["regime"], actual.get("gdp"),
                actual.get("unrate"), actual.get("cpi"),
                now_iso_utc(), "RULE_FRED")
            update_forecast_status(rid, "evaluated")

            evaluated.append({
                "id": rid,
                "forecast": {r: row[f"prob_{r}"] or 0 for r in REGIMES},
                "actual": actual["regime"],
            })

        self.conn.commit()

        if not evaluated:
            return {}

        # 计算 Brier Score
        scores = self._compute_brier(evaluated)
        self._save_evaluation(scores, len(evaluated))
        return scores

    def _get_actual_regime(self, period: str, country: str) -> Optional[dict]:
        """
        从 FRED 拉取 period 前后季度真实数据，规则打标签。
        返回 {"regime": str, "gdp": float, "unrate": float, "cpi": float}
        """
        import concurrent.futures

        def _do_fetch():
            sys.path.insert(0, os.path.dirname(__file__))
            from fredapi import Fred
            fred = Fred(api_key=FRED_API_KEY)

            from datetime import timedelta
            p_dt = datetime.strptime(period, "%Y-%m-%d")
            start = (p_dt.replace(day=1) -
                     relativedelta(months=3)).strftime("%Y-%m-%d")
            end = period

            gdp_s    = fred.get_series("GDPC1",    observation_start=start,
                                        observation_end=end)
            unrate_s = fred.get_series("UNRATE",   observation_start=start,
                                        observation_end=end)
            cpi_s    = fred.get_series("CPIAUCSL", observation_start=start,
                                        observation_end=end)
            hy_s     = fred.get_series("BAMLH0A0HYM2",
                                        observation_start=start,
                                        observation_end=end)

            if gdp_s.empty or unrate_s.empty or cpi_s.empty:
                return None

            # 计算 GDP 同比
            gdp_now = gdp_s.dropna().iloc[-1]
            gdp_yr_start = (p_dt.replace(day=1) -
                            relativedelta(months=12)).strftime("%Y-%m-%d")
            gdp_yr_s = fred.get_series("GDPC1",
                                        observation_start=gdp_yr_start,
                                        observation_end=gdp_yr_start)
            gdp_yoy = None
            if not gdp_yr_s.empty:
                gdp_yoy = (gdp_now / gdp_yr_s.dropna().iloc[-1] - 1) * 100

            unrate = unrate_s.dropna().iloc[-1]
            cpi    = cpi_s.dropna()
            cpi_yoy = None
            if len(cpi) >= 12:
                cpi_yoy = (cpi.iloc[-1] / cpi.iloc[-13] - 1) * 100

            hy_spread = hy_s.dropna().iloc[-1] if not hy_s.empty else None

            # 规则打标签
            regime = self._label_regime(gdp_yoy, unrate, cpi_yoy, hy_spread)
            return {
                "regime": regime,
                "gdp":    round(gdp_yoy, 2)  if gdp_yoy  else None,
                "unrate": round(unrate, 2),
                "cpi":    round(cpi_yoy, 2)  if cpi_yoy  else None,
            }

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(_do_fetch)
                return future.result(timeout=15)
        except concurrent.futures.TimeoutError:
            print(f"    [Tracker] FRED 请求超时（>15s），跳过 {period}")
            return None
        except Exception as e:
            print(f"    [Tracker] FRED 获取失败: {e}")
            return None

    @staticmethod
    def _label_regime(gdp_yoy, unrate, cpi_yoy, hy_spread) -> str:
        """
        简单规则打标签。优先级：危机 > 深度衰退 > 滞胀 > 衰退 > 软着陆
        这些规则是近似，缺乏 NBER 权威性，但对于评估是合理的起点。
        """
        hy = hy_spread or 0
        gdp = gdp_yoy or 0
        cpi = cpi_yoy or 0

        if hy > 800 or (gdp < -5 and unrate > 8):
            return "crisis_vix"
        if gdp < -2.5 or (gdp < 0 and unrate > 6.5):
            return "deep_recession"
        if cpi > 5.0 and gdp < 1.0:
            return "stagflation"
        if gdp < 0 or (gdp < 0.5 and unrate > 5.5):
            return "recession"
        return "soft_landing"

    # ── Brier Score ───────────────────────────────────────────────────────────

    @staticmethod
    def _compute_brier(evaluated: list) -> dict:
        """
        多分类 Brier Score。
        evaluated: [{"id":..., "forecast":{regime:prob}, "actual": regime_str}]
        """
        n = len(evaluated)
        if n == 0:
            return {}

        # 各体制 Brier Score
        scores_by_regime = {r: [] for r in REGIMES}
        for e in evaluated:
            for r in REGIMES:
                p = e["forecast"].get(r, 0) or 0
                o = 1.0 if e["actual"] == r else 0.0
                scores_by_regime[r].append((p - o) ** 2)

        by_regime = {r: round(sum(v) / n, 4) for r, v in scores_by_regime.items()}

        # 总 Brier Score（各体制之和的均值）
        overall = round(
            sum(sum(scores_by_regime[r][i] for r in REGIMES) for i in range(n)) / n,
            4
        )

        # 历史频率基准（naive baseline）
        freq = {}
        for r in REGIMES:
            freq[r] = sum(1 for e in evaluated if e["actual"] == r) / n
        brier_ref = sum(
            sum((freq[r] - (1 if e["actual"] == r else 0)) ** 2 for r in REGIMES)
            for e in evaluated
        ) / n

        skill = round(1 - overall / brier_ref, 4) if brier_ref > 0 else None

        return {
            "n": n,
            "overall_brier": overall,
            "brier_skill_score": skill,
            "by_regime": by_regime,
            "reference_brier": round(brier_ref, 4),
        }

    def _save_evaluation(self, scores: dict, n: int) -> None:
        """将本次 Brier Score 评估结果写入 evaluations 表。"""
        self.conn.execute("""
            INSERT INTO evaluations
            (eval_date, n_samples, brier_score, brier_skill, recession_brier,
             soft_landing_brier)
            VALUES (?,?,?,?,?,?)
        """, (
            date.today().isoformat(),
            n,
            scores.get("overall_brier"),
            scores.get("brier_skill_score"),
            scores.get("by_regime", {}).get("recession"),
            scores.get("by_regime", {}).get("soft_landing"),
        ))
        self.conn.commit()
        upsert_evaluation(
            date.today().isoformat(), n, scores.get("overall_brier"),
            scores.get("brier_skill_score"),
            scores.get("by_regime", {}).get("recession"),
            scores.get("by_regime", {}).get("soft_landing"),
        )

    # ── 摘要报告 ──────────────────────────────────────────────────────────────

    def summary(self) -> None:
        """打印预测追踪状态摘要：总记录、待验证/已到期/已评估数量、最新 Brier Score。"""
        total    = (_pg_fetchone("SELECT COUNT(*) FROM forecast.forecasts") or (0,))[0]
        pending  = (_pg_fetchone(
            "SELECT COUNT(*) FROM forecast.forecasts WHERE status='pending'") or (0,))[0]
        today_str = date.today().isoformat()
        due = (_pg_fetchone(
            "SELECT COUNT(*) FROM forecast.forecasts WHERE status='pending' AND verify_after<=%s",
            (today_str,)
        ) or (0,))[0]
        evaluated = (_pg_fetchone(
            "SELECT COUNT(*) FROM forecast.forecasts WHERE status='evaluated'") or (0,))[0]
        latest_eval = _pg_fetchone(
            "SELECT * FROM forecast.evaluations ORDER BY eval_date DESC LIMIT 1"
        )

        sep = "─" * 50
        print(f"\n{sep}")
        print("  预测追踪状态")
        print(sep)
        print(f"  总记录:   {total}")
        print(f"  待验证:   {pending}  |  已到期: {due}  |  已评估: {evaluated}")
        if due > 0:
            print(f"  ⚠  有 {due} 条到期未评估，运行 tracker.run_evaluation() 处理")
        if latest_eval:
            print(f"\n  最新评估（{latest_eval['eval_date']}）:")
            print(f"    样本数:        {latest_eval['n_samples']}")
            print(f"    Brier Score:   {latest_eval['brier_score']}")
            bs = latest_eval['brier_skill']
            if bs is not None:
                status = "✓ 优于基准" if bs > 0 else "✗ 不如基准"
                print(f"    Brier Skill:   {bs}  {status}")
        else:
            print(f"\n  尚无评估记录（verify_after: "
                  f"{self._next_verify_date()}）")
        print(sep + "\n")

    def _next_verify_date(self) -> str:
        """返回最近一条 pending 预测的 verify_after 日期（无记录时返回'—'）。"""
        row = _pg_fetchone(
            "SELECT MIN(verify_after) FROM forecast.forecasts WHERE status='pending'"
        )
        return row[0] if row and row[0] else "—"

    def brier_report(self) -> None:
        """打印最近10次 Brier Score 评估历史表格（含 Skill Score 和衰退体制 Brier）。"""
        rows = _pg_fetch(
            "SELECT * FROM forecast.evaluations ORDER BY eval_date DESC LIMIT 10"
        )
        if not rows:
            print("  尚无评估记录")
            return
        print(f"\n{'日期':12s} {'样本':>5s} {'Brier':>8s} {'Skill':>8s} {'衰退Brier':>10s}")
        print("-" * 50)
        for r in rows:
            skill_str = f"{r['brier_skill']:+.4f}" if r['brier_skill'] else "   —"
            print(f"{r['eval_date']:12s} {r['n_samples']:>5d} "
                  f"{r['brier_score']:>8.4f} {skill_str:>8s} "
                  f"{r['recession_brier']:>10.4f}")

    def pending_list(self) -> None:
        """打印所有 status=pending 的预测记录（ID/创建日/情景/验证期/体制/概率）。"""
        rows = _pg_fetch("""
            SELECT id, created_at, scenario, horizon_months, verify_after,
                   regime, prob_recession, prob_soft_landing
            FROM forecast.forecasts WHERE status='pending'
            ORDER BY verify_after
        """)
        if not rows:
            print("  无待验证记录")
            return
        print(f"\n{'ID':10s} {'创建日':12s} {'情景':10s} {'验证期':12s} "
              f"{'体制':8s} {'衰退%':>7s} {'软着陆%':>8s}")
        print("-" * 72)
        for r in rows:
            rec = f"{(r['prob_recession'] or 0)*100:.1f}%"
            sl  = f"{(r['prob_soft_landing'] or 0)*100:.1f}%"
            print(f"{r['id']:10s} {r['created_at'][:10]:12s} "
                  f"{r['scenario']:10s} {r['verify_after']:12s} "
                  f"{(r['regime'] or '—'):8s} {rec:>7s} {sl:>8s}")


# ── 命令行入口 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="预测追踪工具")
    parser.add_argument("--summary",  action="store_true", help="显示状态摘要")
    parser.add_argument("--eval",     action="store_true", help="运行评估（到期记录）")
    parser.add_argument("--brier",    action="store_true", help="显示 Brier Score 历史")
    parser.add_argument("--list",     action="store_true", help="列出待验证记录")
    args = parser.parse_args()

    tracker = ForecastTracker()

    if args.eval:
        scores = tracker.run_evaluation()
        if scores:
            print(f"\nBrier Score: {scores['overall_brier']}")
            print(f"Skill Score: {scores['brier_skill_score']}")
    if args.brier:
        tracker.brier_report()
    if args.list:
        tracker.pending_list()
    if args.summary or not any(vars(args).values()):
        tracker.summary()
