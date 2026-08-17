"""
tianji_db.py — 天玑数据库 schema 与基础操作

⛔ 08-17 维护警示（审查 M 项）：本文件与 `macro-ji/tianji_db.py` 是**两份独立实现**——
本文件 = SQLite 主写 + PG 旁路（生产 _PG_ONLY 下 SQLite 为 Noop，PG 旁路生效）；
macro-ji 版 = 纯 PG（psycopg 直连，无 SQLite 回退）。
**改本文件必须同步 macro-ji 版**（或反之），两份接口签名应保持一致；
长期方向 = 合并为单一 PG 实现（已登记 review-todo-20260816.md P2）。

新架构三张核心表：
  predictions        — 预测主张存档（outcome_definition 预测时填写不可改）
  reasoning_trace    — 推理溯源（因果链 + 信号 + agent）
  weight_update_log  — 权重更新日志

附加表：
  narrative_chunks       — 叙事预处理存储
  narrative_density_flags — 叙事密度监测

兼容：forecast_tracker.db 同一个 SQLite 文件
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
# E0-A: 旁路双写 worldsim-pg（非阻断，异常自吞，绝不阻断 SQLite 主流程）
from pg_write_collection import (
    upsert_tianji_prediction, update_tianji_prediction_verified,
    upsert_tianji_reasoning_trace, upsert_tianji_weight_update_log,
    upsert_tianji_narrative_chunk,
)

BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH  = os.path.join(DATA_DIR, "forecast_tracker.db")

TIANJI_DDL = """

-- ── 预测主张表 ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS predictions (
    id                    TEXT PRIMARY KEY,
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_at                DATETIME NOT NULL,
    scenario_id           TEXT,
    type                  TEXT NOT NULL CHECK(type IN ('quantitative','geopolitical')),
    prediction_target_type TEXT NOT NULL,
    content               TEXT NOT NULL,
    outcome_definition    TEXT NOT NULL,   -- 预测时填写，不可修改
    target_metric         TEXT,            -- FRED序列名 / GRV维度
    target_direction      TEXT,            -- 'up'/'down'/'above'/'below'
    target_threshold      REAL,
    b_prob                REAL,            -- B模块历史频率概率
    b_sample_count        INTEGER,
    b_max_similarity      REAL,
    llm_adj               REAL,            -- A模块调整量
    final_prob            REAL,
    prob_low              REAL,            -- NOVEL模式区间下界
    prob_high             REAL,            -- NOVEL模式区间上界
    confidence_tier       TEXT CHECK(confidence_tier IN ('HIGH','LOW','VERY_LOW','NOVEL')),
    time_horizon          TEXT CHECK(time_horizon IN ('weekly','monthly','quarterly','yearly')),
    status                TEXT NOT NULL DEFAULT 'pending'
                              CHECK(status IN ('pending','verified','awaiting_human')),
    outcome_value         REAL,
    brier_score           REAL,
    brier_skill_score     REAL,
    verified_at           DATETIME,
    verified_by           TEXT             -- 'auto' / 'human:<name>'
);

-- ── 推理溯源表（与 predictions 一对一） ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS reasoning_trace (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id       TEXT NOT NULL REFERENCES predictions(id),
    agent_id            TEXT,
    input_signals       TEXT,   -- JSON: [{signal_name, value, weight}, ...]
    historical_match    TEXT,   -- B阶段匹配到的历史时期描述
    confidence_basis    TEXT CHECK(confidence_basis IN ('historical_freq','llm_adjusted','llm_primary','novel')),
    llm_adjustment      REAL,
    causal_chains       TEXT,   -- JSON: [{id, nodes, confidence, source}, ...]
    reasoning           TEXT    -- NOVEL模式完整推理链文本
);

-- ── 权重更新日志 ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS weight_update_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    prediction_id   TEXT REFERENCES predictions(id),
    signal_name     TEXT NOT NULL,
    target_type     TEXT NOT NULL,
    weight_before   REAL,
    weight_after    REAL,
    reason          TEXT,   -- '自动校准' / '人工干预' / '重置'
    notes           TEXT    -- 同方向连续4次时强制填写
);

-- ── 叙事块存储 ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS narrative_chunks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id           TEXT NOT NULL,
    source_type         TEXT NOT NULL,
    primary_dimension   TEXT NOT NULL,
    secondary_dimension TEXT,
    timestamp           DATETIME NOT NULL,
    content             TEXT NOT NULL,
    token_count         INTEGER,
    staleness_tau       INTEGER NOT NULL DEFAULT 72,  -- 半衰期小时数
    embedding           BLOB,                          -- 阶段二填充
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dim_time
    ON narrative_chunks(primary_dimension, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_narrative_source
    ON narrative_chunks(source_id, primary_dimension);

-- ── 叙事密度监测 ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS narrative_density_flags (
    dimension   TEXT PRIMARY KEY,
    flagged_at  DATETIME,
    z_score     REAL,
    consumed    INTEGER NOT NULL DEFAULT 0
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


def get_connection() -> sqlite3.Connection:
    if _PG_ONLY:
        return _NoopConn()
    if not os.path.exists(DB_PATH):
        # P6 删库后（08-14）：SQLite 已退役，禁止自动创建（sqlite3.connect 会建空库）
        raise RuntimeError(
            "SQLite 已退役（P6 删库）: %s 不存在，读路径走 pg_read；如需双写回归请先恢复备份" % DB_PATH)
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def run_migration():
    """幂等执行：已存在的表不重建。"""
    conn = get_connection()
    try:
        conn.executescript(TIANJI_DDL)
        conn.commit()
        print(f"[tianji_db] migration OK → {DB_PATH}")
    finally:
        conn.close()


# ── 预测存档 ─────────────────────────────────────────────────────────────────

def save_prediction(pred: dict) -> str:
    """
    存档一条预测。pred 必须包含：
      id, due_at, type, prediction_target_type, content, outcome_definition, final_prob
    返回 prediction_id。
    """
    required = ["id", "due_at", "type", "prediction_target_type",
                "content", "outcome_definition", "final_prob"]
    for k in required:
        if k not in pred:
            raise ValueError(f"save_prediction: 缺少必填字段 '{k}'")

    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO predictions
              (id, created_at, due_at, scenario_id, type, prediction_target_type,
               content, outcome_definition, target_metric, target_direction,
               target_threshold, b_prob, b_sample_count, b_max_similarity,
               llm_adj, final_prob, prob_low, prob_high, confidence_tier,
               time_horizon, status)
            VALUES
              (:id, :created_at, :due_at, :scenario_id, :type, :prediction_target_type,
               :content, :outcome_definition, :target_metric, :target_direction,
               :target_threshold, :b_prob, :b_sample_count, :b_max_similarity,
               :llm_adj, :final_prob, :prob_low, :prob_high, :confidence_tier,
               :time_horizon, 'pending')
        """, {
            "id":                    pred["id"],
            "created_at":            pred.get("created_at", datetime.now(timezone.utc).isoformat()),
            "due_at":                pred["due_at"],
            "scenario_id":           pred.get("scenario_id"),
            "type":                  pred["type"],
            "prediction_target_type": pred["prediction_target_type"],
            "content":               pred["content"],
            "outcome_definition":    pred["outcome_definition"],
            "target_metric":         pred.get("target_metric"),
            "target_direction":      pred.get("target_direction"),
            "target_threshold":      pred.get("target_threshold"),
            "b_prob":                pred.get("b_prob"),
            "b_sample_count":        pred.get("b_sample_count"),
            "b_max_similarity":      pred.get("b_max_similarity"),
            "llm_adj":               pred.get("llm_adj"),
            "final_prob":            pred["final_prob"],
            "prob_low":              pred.get("prob_low"),
            "prob_high":             pred.get("prob_high"),
            "confidence_tier":       pred.get("confidence_tier", "HIGH"),
            "time_horizon":          pred.get("time_horizon", "monthly"),
        })
        conn.commit()
        upsert_tianji_prediction(pred)
        return pred["id"]
    finally:
        conn.close()


def save_reasoning_trace(trace: dict):
    """存档推理溯源，与 prediction_id 关联。"""
    conn = get_connection()
    try:
        import json as _json
        conn.execute("""
            INSERT INTO reasoning_trace
              (prediction_id, agent_id, input_signals, historical_match,
               confidence_basis, llm_adjustment, causal_chains, reasoning)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            trace["prediction_id"],
            trace.get("agent_id"),
            _json.dumps(trace.get("input_signals", []), ensure_ascii=False),
            trace.get("historical_match"),
            trace.get("confidence_basis", "historical_freq"),
            trace.get("llm_adjustment"),
            _json.dumps(trace.get("causal_chains", []), ensure_ascii=False),
            trace.get("reasoning"),
        ))
        conn.commit()
        upsert_tianji_reasoning_trace(trace)
    finally:
        conn.close()


# ── 叙事块操作 ──────────────────────────────────────────────────────────────

def save_narrative_chunk(chunk: dict):
    """存储一条叙事块，同维度相似内容由调用方去重后再写入。"""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO narrative_chunks
              (source_id, source_type, primary_dimension, secondary_dimension,
               timestamp, content, token_count, staleness_tau)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            chunk["source_id"],
            chunk["source_type"],
            chunk["primary_dimension"],
            chunk.get("secondary_dimension"),
            chunk["timestamp"],
            chunk["content"],
            chunk.get("token_count"),
            chunk.get("staleness_tau", 72),
        ))
        conn.commit()
        upsert_tianji_narrative_chunk(chunk)
    finally:
        conn.close()


def get_narrative_chunks_for_dimension(
    dimension: str,
    max_tokens: int = 2000,
    now_ts: str = None,
) -> list[dict]:
    """
    按 staleness 分数排序取 top-N 条叙事块，直到填满 token 配额。
    staleness_score = exp(-hours_age / tau)
    """
    import math
    if now_ts is None:
        now_ts = datetime.now(timezone.utc).isoformat()

    import pg_read as _pg
    conn = _pg.connect()
    if conn is None:
        return []
    try:
        rows = conn.execute("""
            SELECT id, source_id, source_type, content, token_count,
                   staleness_tau, timestamp
            FROM tianji.narrative_chunks
            WHERE primary_dimension = %s
            ORDER BY timestamp DESC
            LIMIT 200
        """, (dimension,)).fetchall()
    finally:
        conn.close()

    now_dt = datetime.fromisoformat(now_ts.replace("Z",""))
    scored = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(str(row["timestamp"]).replace("Z",""))
            hours_age = (now_dt - ts).total_seconds() / 3600
        except Exception:
            hours_age = 999
        tau = row["staleness_tau"] or 72
        score = math.exp(-hours_age / tau)
        scored.append((score, dict(row)))

    scored.sort(reverse=True)

    result = []
    used_tokens = 0
    for score, row in scored:
        tc = row.get("token_count") or len(row["content"]) // 4
        if used_tokens + tc > max_tokens:
            break
        result.append(row)
        used_tokens += tc

    return result


# ── 月度验证 ─────────────────────────────────────────────────────────────────

def get_pending_predictions(as_of: str = None) -> list[dict]:
    """取所有到期且未验证的预测。"""
    if as_of is None:
        as_of = datetime.now(timezone.utc).isoformat()
    import pg_read as _pg
    conn = _pg.connect()
    if conn is None:
        return []
    try:
        rows = conn.execute("""
            SELECT * FROM tianji.predictions
            WHERE status = 'pending' AND due_at <= %s
            ORDER BY due_at ASC
        """, (as_of,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_prediction_verified(
    prediction_id: str,
    outcome_value: float,
    brier_score: float,
    brier_skill_score: float = None,
    verified_by: str = "auto",
):
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE predictions SET
                status = 'verified',
                outcome_value = ?,
                brier_score = ?,
                brier_skill_score = ?,
                verified_at = CURRENT_TIMESTAMP,
                verified_by = ?
            WHERE id = ?
        """, (outcome_value, brier_score, brier_skill_score, verified_by, prediction_id))
        conn.commit()
        update_tianji_prediction_verified(prediction_id, outcome_value, brier_score,
                                          brier_skill_score, verified_by)
    finally:
        conn.close()


def log_weight_update(entry: dict):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO weight_update_log
              (prediction_id, signal_name, target_type,
               weight_before, weight_after, reason, notes)
            VALUES (?,?,?,?,?,?,?)
        """, (
            entry.get("prediction_id"),
            entry["signal_name"],
            entry["target_type"],
            entry.get("weight_before"),
            entry.get("weight_after"),
            entry.get("reason", "自动校准"),
            entry.get("notes"),
        ))
        conn.commit()
        upsert_tianji_weight_update_log(entry)
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
    print("天玑数据库初始化完成。")
    import pg_read as _pg
    conn = _pg.connect()
    if conn is not None:
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='tianji' ORDER BY table_name"
        ).fetchall()
        print("当前表：", [t[0] for t in tables])
        conn.close()
