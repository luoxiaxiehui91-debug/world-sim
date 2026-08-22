"""
tianji_db.py — 天玑数据库基础操作（P0-D2 转 PG：直连 worldsim-pg tianji schema）

核心表（schema 由 03_b0_schema.sql 持有，本模块不再建表/迁移）：
  predictions             — 预测主张存档（outcome_definition 预测时填写不可改）
  reasoning_trace         — 推理溯源（因果链 + 信号 + agent）
  weight_update_log       — 权重更新日志
  narrative_chunks        — 叙事预处理存储
  narrative_density_flags — 叙事密度监测
"""

import os
from datetime import datetime, timezone, timezone

try:
    import psycopg
    from psycopg.rows import dict_row
    _PG_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PG_AVAILABLE = False

BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 天玑独立容器：TIANJI_DATA_DIR 显式指向挂载卷 /app/macro_data（FRED/GRV 读依赖）
DATA_DIR = os.environ.get("TIANJI_DATA_DIR", os.path.join(BASE_DIR, "data"))


def _norm_row(row: dict) -> dict:
    """PG 行归一化：timestamptz(datetime) → UTC naive ISO 文本。

    下游（tianji_verifier 等）大量用 [:10] 切片 / 与 naive datetime 比较；与旧 SQLite
    存文本（"YYYY-MM-DDTHH:MM:SS" UTC）行为保持一致，对齐 pg_read._norm 口径。
    """
    out = dict(row)
    for k, v in out.items():
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            out[k] = v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return out


def get_connection():
    """返回 worldsim-pg tianji schema 连接（psycopg3，row_factory=dict_row）。

    _PG_ONLY（P0-D2 转 PG 完成）：psycopg 未安装或 WORLDSIM_APP_PW 缺失
    → raise RuntimeError（明确报错，不静默；不再有任何 SQLite 回退）。
    """
    if not _PG_AVAILABLE:
        raise RuntimeError("psycopg 未安装，天玑需 psycopg[binary]>=3.1 才能连 worldsim-pg（_PG_ONLY）")
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        raise RuntimeError("WORLDSIM_APP_PW 未注入，无法连接 worldsim-pg（_PG_ONLY，不静默）")
    return psycopg.connect(
        host="worldsim-pg",
        port=5432,
        dbname="worldsim",
        user="worldsim_app",
        password=pw,
        row_factory=dict_row,
        options="-c search_path=tianji,public",
    )


def run_migration():
    """PG 模式无需 SQLite 迁移：schema 由 03_b0_schema.sql 持有（PG 无 CHECK 约束、无 DDL 需容器维护）。"""
    print("[tianji_db] PG 模式无需 SQLite 迁移（schema 由 03_b0_schema.sql 持有）")


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
            INSERT INTO predictions
              (id, created_at, due_at, scenario_id, type, prediction_target_type,
               content, outcome_definition, target_metric, target_direction,
               target_threshold, b_prob, b_sample_count, b_max_similarity,
               llm_adj, final_prob, prob_low, prob_high, confidence_tier,
               time_horizon, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (
            pred["id"],
            pred.get("created_at", datetime.now(timezone.utc).isoformat()),
            pred["due_at"],
            pred.get("scenario_id"),
            pred["type"],
            pred["prediction_target_type"],
            pred["content"],
            pred["outcome_definition"],
            pred.get("target_metric"),
            pred.get("target_direction"),
            pred.get("target_threshold"),
            pred.get("b_prob"),
            pred.get("b_sample_count"),
            pred.get("b_max_similarity"),
            pred.get("llm_adj"),
            pred["final_prob"],
            pred.get("prob_low"),
            pred.get("prob_high"),
            pred.get("confidence_tier", "HIGH"),
            pred.get("time_horizon", "monthly"),
            "pending",
        ))
        conn.commit()
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
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
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
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
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

    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, source_id, source_type, content, token_count,
                   staleness_tau, timestamp
            FROM narrative_chunks
            WHERE primary_dimension = %s
            ORDER BY timestamp DESC
            LIMIT 200
        """, (dimension,)).fetchall()
    finally:
        conn.close()

    now_dt = datetime.fromisoformat(now_ts.replace("Z",""))
    scored = []
    for row in rows:
        row = _norm_row(dict(row))
        try:
            ts = datetime.fromisoformat(str(row["timestamp"]).replace("Z",""))
            hours_age = (now_dt - ts).total_seconds() / 3600
        except Exception:
            hours_age = 999
        tau = row["staleness_tau"] or 72
        score = math.exp(-hours_age / tau)
        scored.append((score, row))

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
    """取所有到期且未验证的预测。

    as_of 默认 timezone-aware UTC ISO（防 naive 按容器 TZ 解释差 8h）。
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM predictions
            WHERE status = 'pending' AND due_at <= %s
            ORDER BY due_at ASC
        """, (as_of,)).fetchall()
        return [_norm_row(dict(r)) for r in rows]
    finally:
        conn.close()


def update_prediction_verified(
    prediction_id: str,
    outcome_value: float,
    brier_score: float,
    brier_skill_score: float = None,
    verified_by: str = "auto",
    human_note: str = None,
):
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE predictions SET
                status = 'verified',
                outcome_value = %s,
                brier_score = %s,
                brier_skill_score = %s,
                verified_at = CURRENT_TIMESTAMP,
                verified_by = %s,
                human_note = %s
            WHERE id = %s
        """, (outcome_value, brier_score, brier_skill_score, verified_by, human_note, prediction_id))
        conn.commit()
    finally:
        conn.close()


def log_weight_update(entry: dict):
    conn = get_connection()
    try:
        # 08-18 P1-5：补 updated_at 写入（此前 NULL，玉衡审计排序退化）
        conn.execute("""
            INSERT INTO weight_update_log
              (prediction_id, signal_name, target_type,
               weight_before, weight_after, reason, notes, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            entry.get("prediction_id"),
            entry["signal_name"],
            entry["target_type"],
            entry.get("weight_before"),
            entry.get("weight_after"),
            entry.get("reason", "自动校准"),
            entry.get("notes"),
            entry.get("updated_at", datetime.now(timezone.utc).isoformat()),
        ))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
    print("天玑数据库初始化完成。")
    conn = get_connection()
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'tianji' ORDER BY table_name"
    ).fetchall()
    print("当前表：", [t["table_name"] for t in tables])
    conn.close()
