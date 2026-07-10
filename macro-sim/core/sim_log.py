"""
sim_log.py — P4-A
sim_log.db 持久化：每次 Monte Carlo 结束后写入预测记录，供事后校准。
"""

import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "sim_log.db"


def _get_conn(db_path: Path = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = None):
    """建表（幂等，若表已存在则跳过）"""
    conn = _get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sim_runs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            sim_id           TEXT    NOT NULL,
            run_date         TEXT    NOT NULL,
            grv_at_t0        REAL,
            vix_at_t0        REAL,
            situation_level  INTEGER,
            trigger_event    TEXT,
            n_runs           INTEGER,
            sentiment_mean   REAL,
            sentiment_std    REAL,
            sentiment_p10    REAL,
            sentiment_p90    REAL,
            vix_bleed_mean   REAL,
            vix_bleed_p90    REAL,
            cascade_rate     REAL,
            stress_label     TEXT,
            grv_forecast     TEXT,
            verify_in_days   INTEGER,
            actual_grv_change REAL,
            verified         INTEGER DEFAULT 0,
            created_at       TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_sim_runs_date ON sim_runs(run_date);
        CREATE INDEX IF NOT EXISTS idx_sim_runs_verified ON sim_runs(verified);
    """)
    conn.commit()
    conn.close()


def insert_run(forecast: dict, mc_result: dict, world, db_path: Path = None):
    """
    写入一条仿真记录。
    forecast: make_forecast_record() 返回的字典
    mc_result: run_monte_carlo() 返回的字典
    world: MacroWorldState（取 vix_at_t0 / situation_level）
    """
    if not forecast:
        return

    init_db(db_path)
    conn = _get_conn(db_path)
    conn.execute("""
        INSERT INTO sim_runs (
            sim_id, run_date, grv_at_t0, vix_at_t0, situation_level,
            trigger_event, n_runs,
            sentiment_mean, sentiment_std, sentiment_p10, sentiment_p90,
            vix_bleed_mean, vix_bleed_p90, cascade_rate,
            stress_label, grv_forecast, verify_in_days,
            actual_grv_change, verified
        ) VALUES (
            :sim_id, :run_date, :grv_at_t0, :vix_at_t0, :situation_level,
            :trigger_event, :n_runs,
            :sentiment_mean, :sentiment_std, :sentiment_p10, :sentiment_p90,
            :vix_bleed_mean, :vix_bleed_p90, :cascade_rate,
            :stress_label, :grv_forecast, :verify_in_days,
            NULL, 0
        )
    """, {
        "sim_id":           forecast.get("sim_id", ""),
        "run_date":         forecast.get("run_date", ""),
        "grv_at_t0":        forecast.get("grv_at_t0"),
        "vix_at_t0":        getattr(world, "vix_baseline", None),
        "situation_level":  getattr(world, "situation_level", None),
        "trigger_event":    getattr(world, "trigger_event", ""),
        "n_runs":           mc_result.get("n_runs"),
        "sentiment_mean":   mc_result.get("sentiment_mean"),
        "sentiment_std":    mc_result.get("sentiment_std"),
        "sentiment_p10":    mc_result.get("sentiment_p10"),
        "sentiment_p90":    mc_result.get("sentiment_p90"),
        "vix_bleed_mean":   mc_result.get("vix_bleed_mean"),
        "vix_bleed_p90":    mc_result.get("vix_bleed_p90"),
        "cascade_rate":     mc_result.get("cascade_rate"),
        "stress_label":     forecast.get("stress_label"),
        "grv_forecast":     forecast.get("grv_forecast"),
        "verify_in_days":   forecast.get("verify_in_days"),
    })
    conn.commit()
    conn.close()


def mark_verified(sim_id: str, actual_grv_change: float, db_path: Path = None):
    """
    事后校准：填入实际 GRV 变化并标记 verified=1。
    actual_grv_change = GRV_actual - GRV_at_t0（正=上升，负=下降）
    """
    conn = _get_conn(db_path)
    conn.execute("""
        UPDATE sim_runs
           SET actual_grv_change = ?, verified = 1
         WHERE sim_id = ? AND verified = 0
    """, (actual_grv_change, sim_id))
    conn.commit()
    conn.close()


def list_unverified(db_path: Path = None) -> list[dict]:
    """返回所有尚未校准、且 verify_in_days 不为 NULL 的记录"""
    conn = _get_conn(db_path)
    rows = conn.execute("""
        SELECT sim_id, run_date, grv_at_t0, stress_label,
               grv_forecast, verify_in_days, sentiment_mean
          FROM sim_runs
         WHERE verified = 0
           AND verify_in_days IS NOT NULL
         ORDER BY run_date ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
