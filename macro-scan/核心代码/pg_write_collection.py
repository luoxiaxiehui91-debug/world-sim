"""
pg_write_collection.py — world-sim 天枢 macro-scan 双写模块 (E0-A)

职责：在原有「SQLite 落库」之外，把采集结果双写到 worldsim-pg 的
news / forecast / tianji 三个 schema。本模块是「旁路双写」——任何连接/写入
异常都必须被捕获并不向上抛异常，绝不阻断原 SQLite 流程。

目标 schema（详见 sql/03_b0_schema.sql，由 B0 建）：
    news.*    : scan_contexts, articles, article_categories, signal_episodes,
                episode_articles
                （signal_outcomes / synthesis_log 非本模块运行时覆盖，留 C 阶段）
    forecast.*: forecasts, actuals, evaluations
    tianji.*  : predictions, reasoning_trace, weight_update_log,
                narrative_chunks, narrative_density_flags

连接：环境变量 WORLDSIM_APP_PW；host=worldsim-pg port=5432
      dbname=worldsim user=worldsim_app（容器间 worldsim_default 子网）。
依赖：psycopg 3.x（macro-scan 镜像 v8 已装）。

实现要点（对齐 B1 pg_write_indicators.py）：
- 主键策略：pg 表与 SQLite 复用同一 id（SQLite lastrowid 透传），保证外键关联
  一致（episode_articles.article_id→articles.id 等）。BIGSERIAL 表显式 INSERT id，
  序列不推进无碍（双写是 pg 唯一写方，永远带 id）。
- 无 caller-id 的 BIGSERIAL 表（evaluations / reasoning_trace / weight_update_log /
  narrative_chunks）：INSERT 前先 SELECT COALESCE(MAX(id),0)+1 续 id，
  ON CONFLICT(id) DO NOTHING，避免与 B0 回填 id 冲突（单容器顺序写，无并发竞争）。
- 全部 try/except 兜底，异常只打印 ERROR，绝不抛。
"""

import os
from datetime import datetime, timezone

_PG_HOST = "worldsim-pg"
_PG_PORT = 5432
_PG_DB = "worldsim"
_PG_USER = "worldsim_app"
_SEARCH_PATH = "news,forecast,tianji,public"


def _conn():
    """返回 worldsim-pg 连接；不可用时返回 None（调用方自行吞掉）。"""
    try:
        import psycopg
    except Exception as e:
        print(f"ERROR [pg_write_collection] psycopg 不可用，跳过双写: {e}")
        return None
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        print("ERROR [pg_write_collection] WORLDSIM_APP_PW 未设置，跳过双写")
        return None
    try:
        return psycopg.connect(
            host=_PG_HOST, port=_PG_PORT, dbname=_PG_DB, user=_PG_USER,
            password=pw, connect_timeout=10,
            options=f"-c search_path={_SEARCH_PATH}",
        )
    except Exception as e:
        print(f"ERROR [pg_write_collection] 连接 worldsim-pg 失败（不影响原流程）: {e}")
        return None


def _next_id(cur, table: str) -> int:
    """取某 BIGSERIAL 表下一个 id（用于无 caller-id 的追加表）。"""
    cur.execute(f"SELECT COALESCE(MAX(id),0)+1 FROM {table}")
    return cur.fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# news.schema
# ─────────────────────────────────────────────────────────────────────────────

def upsert_news_scan_context(ctx_id, scan_time, vix, t10y2y, baa10y, dff,
                              regime, vix_regime, data_quality):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO news.scan_contexts
                       (id, scan_time, vix, t10y2y, baa10y, dff, regime, vix_regime, data_quality)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET
                         scan_time=EXCLUDED.scan_time, vix=EXCLUDED.vix,
                         t10y2y=EXCLUDED.t10y2y, baa10y=EXCLUDED.baa10y,
                         dff=EXCLUDED.dff, regime=EXCLUDED.regime,
                         vix_regime=EXCLUDED.vix_regime, data_quality=EXCLUDED.data_quality""",
                    (ctx_id, scan_time, vix, t10y2y, baa10y, dff,
                     regime, vix_regime, data_quality),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] scan_contexts 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_news_article(aid, url, content_hash, title, source, published_at,
                         ingested_at, country_tag, ingest_ctx_id, pub_ctx_id):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO news.articles
                       (id, url, content_hash, title, source, published_at, ingested_at,
                        country_tag, ingest_ctx_id, pub_ctx_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET
                         url=EXCLUDED.url, content_hash=EXCLUDED.content_hash,
                         title=EXCLUDED.title, source=EXCLUDED.source,
                         published_at=EXCLUDED.published_at, ingested_at=EXCLUDED.ingested_at,
                         country_tag=EXCLUDED.country_tag,
                         ingest_ctx_id=EXCLUDED.ingest_ctx_id, pub_ctx_id=EXCLUDED.pub_ctx_id""",
                    (aid, url, content_hash, title, source, published_at, ingested_at,
                     country_tag, ingest_ctx_id, pub_ctx_id),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] articles 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_news_article_category(article_id, category):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO news.article_categories (article_id, category)
                       VALUES (%s,%s)
                       ON CONFLICT (article_id, category) DO NOTHING""",
                    (article_id, category),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] article_categories 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_news_signal_episode(ep_id, category, triggered_at, ratio, level, scan_ctx_id):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO news.signal_episodes
                       (id, category, triggered_at, ratio, level, scan_ctx_id)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET
                         category=EXCLUDED.category, triggered_at=EXCLUDED.triggered_at,
                         ratio=EXCLUDED.ratio, level=EXCLUDED.level,
                         scan_ctx_id=EXCLUDED.scan_ctx_id""",
                    (ep_id, category, triggered_at, ratio, level, scan_ctx_id),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] signal_episodes 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_news_episode_article(episode_id, article_id):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO news.episode_articles (episode_id, article_id)
                       VALUES (%s,%s)
                       ON CONFLICT (episode_id, article_id) DO NOTHING""",
                    (episode_id, article_id),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] episode_articles 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def delete_news_articles(old_ids: list) -> None:
    """prune 同步：按 id 批量删 articles 及其关联（article_categories/episode_articles）。"""
    if not old_ids:
        return
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                batch = 200
                for i in range(0, len(old_ids), batch):
                    chunk = old_ids[i:i + batch]
                    ph = ",".join(["%s"] * len(chunk))
                    cur.execute(
                        f"DELETE FROM news.article_categories WHERE article_id IN ({ph})", chunk)
                    cur.execute(
                        f"DELETE FROM news.episode_articles WHERE article_id IN ({ph})", chunk)
                    cur.execute(
                        f"DELETE FROM news.articles WHERE id IN ({ph})", chunk)
    except Exception as e:
        print(f"ERROR [pg_write_collection] articles prune 双写失败: {e}")
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# forecast.schema
# ─────────────────────────────────────────────────────────────────────────────

def upsert_forecast(fid, created_at, scenario, horizon_months, verify_after, country,
                    status, regime, stress_signals, prob_recession, prob_deep_recession,
                    prob_soft_landing, prob_stagflation, prob_crisis_vix,
                    gdp_p10, gdp_p50, gdp_p90, unrate_p50, cpi_yoy_p50,
                    input_json, notes):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO forecast.forecasts
                       (id, created_at, scenario, horizon_months, verify_after, country,
                        status, regime, stress_signals,
                        prob_recession, prob_deep_recession, prob_soft_landing,
                        prob_stagflation, prob_crisis_vix,
                        gdp_p10, gdp_p50, gdp_p90, unrate_p50, cpi_yoy_p50,
                        input_json, notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET
                         created_at=EXCLUDED.created_at, scenario=EXCLUDED.scenario,
                         horizon_months=EXCLUDED.horizon_months, verify_after=EXCLUDED.verify_after,
                         country=EXCLUDED.country, status=EXCLUDED.status, regime=EXCLUDED.regime,
                         stress_signals=EXCLUDED.stress_signals,
                         prob_recession=EXCLUDED.prob_recession,
                         prob_deep_recession=EXCLUDED.prob_deep_recession,
                         prob_soft_landing=EXCLUDED.prob_soft_landing,
                         prob_stagflation=EXCLUDED.prob_stagflation,
                         prob_crisis_vix=EXCLUDED.prob_crisis_vix,
                         gdp_p10=EXCLUDED.gdp_p10, gdp_p50=EXCLUDED.gdp_p50,
                         gdp_p90=EXCLUDED.gdp_p90, unrate_p50=EXCLUDED.unrate_p50,
                         cpi_yoy_p50=EXCLUDED.cpi_yoy_p50, input_json=EXCLUDED.input_json,
                         notes=EXCLUDED.notes""",
                    (fid, created_at, scenario, horizon_months, verify_after, country,
                     status, regime, stress_signals, prob_recession, prob_deep_recession,
                     prob_soft_landing, prob_stagflation, prob_crisis_vix,
                     gdp_p10, gdp_p50, gdp_p90, unrate_p50, cpi_yoy_p50,
                     input_json, notes),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] forecasts 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def update_forecast_status(fid, status):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE forecast.forecasts SET status=%s WHERE id=%s", (status, fid))
    except Exception as e:
        print(f"ERROR [pg_write_collection] forecasts status 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_actual(period, actual_regime, gdp_growth, unemployment, cpi_yoy,
                  labeled_at, label_source, notes=""):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO forecast.actuals
                       (period, actual_regime, gdp_growth, unemployment, cpi_yoy,
                        labeled_at, label_source, notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (period) DO UPDATE SET
                         actual_regime=EXCLUDED.actual_regime, gdp_growth=EXCLUDED.gdp_growth,
                         unemployment=EXCLUDED.unemployment, cpi_yoy=EXCLUDED.cpi_yoy,
                         labeled_at=EXCLUDED.labeled_at, label_source=EXCLUDED.label_source,
                         notes=EXCLUDED.notes""",
                    (period, actual_regime, gdp_growth, unemployment, cpi_yoy,
                     labeled_at, label_source, notes),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] actuals 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_evaluation(eval_date, n_samples, brier_score, brier_skill,
                      recession_brier, soft_landing_brier):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                nid = _next_id(cur, "forecast.evaluations")
                cur.execute(
                    """INSERT INTO forecast.evaluations
                       (id, eval_date, n_samples, brier_score, brier_skill,
                        recession_brier, soft_landing_brier)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO NOTHING""",
                    (nid, eval_date, n_samples, brier_score, brier_skill,
                     recession_brier, soft_landing_brier),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] evaluations 双写失败: {e}")
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# tianji.schema
# ─────────────────────────────────────────────────────────────────────────────

def upsert_tianji_prediction(pred: dict) -> None:
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO tianji.predictions
                       (id, created_at, due_at, scenario_id, type, prediction_target_type,
                        content, outcome_definition, target_metric, target_direction,
                        target_threshold, b_prob, b_sample_count, b_max_similarity,
                        llm_adj, final_prob, prob_low, prob_high, confidence_tier,
                        time_horizon, status, outcome_value, brier_score,
                        brier_skill_score, verified_at, verified_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                               %s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET
                         created_at=EXCLUDED.created_at, due_at=EXCLUDED.due_at,
                         scenario_id=EXCLUDED.scenario_id, type=EXCLUDED.type,
                         prediction_target_type=EXCLUDED.prediction_target_type,
                         content=EXCLUDED.content, outcome_definition=EXCLUDED.outcome_definition,
                         target_metric=EXCLUDED.target_metric, target_direction=EXCLUDED.target_direction,
                         target_threshold=EXCLUDED.target_threshold, b_prob=EXCLUDED.b_prob,
                         b_sample_count=EXCLUDED.b_sample_count, b_max_similarity=EXCLUDED.b_max_similarity,
                         llm_adj=EXCLUDED.llm_adj, final_prob=EXCLUDED.final_prob,
                         prob_low=EXCLUDED.prob_low, prob_high=EXCLUDED.prob_high,
                         confidence_tier=EXCLUDED.confidence_tier, time_horizon=EXCLUDED.time_horizon,
                         status=EXCLUDED.status, outcome_value=EXCLUDED.outcome_value,
                         brier_score=EXCLUDED.brier_score, brier_skill_score=EXCLUDED.brier_skill_score,
                         verified_at=EXCLUDED.verified_at, verified_by=EXCLUDED.verified_by""",
                    (pred.get("id"),
                     pred.get("created_at", datetime.now(timezone.utc).isoformat()),
                     pred.get("due_at"), pred.get("scenario_id"),
                     pred.get("type"), pred.get("prediction_target_type"),
                     pred.get("content"), pred.get("outcome_definition"),
                     pred.get("target_metric"), pred.get("target_direction"),
                     pred.get("target_threshold"), pred.get("b_prob"),
                     pred.get("b_sample_count"), pred.get("b_max_similarity"),
                     pred.get("llm_adj"), pred.get("final_prob"),
                     pred.get("prob_low"), pred.get("prob_high"),
                     pred.get("confidence_tier", "HIGH"), pred.get("time_horizon", "monthly"),
                     pred.get("status", "pending"), pred.get("outcome_value"),
                     pred.get("brier_score"), pred.get("brier_skill_score"),
                     pred.get("verified_at"), pred.get("verified_by")),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] predictions 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def update_tianji_prediction_verified(prediction_id, outcome_value, brier_score,
                                       brier_skill_score=None, verified_by="auto"):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tianji.predictions SET
                         status='verified', outcome_value=%s, brier_score=%s,
                         brier_skill_score=%s, verified_at=now(), verified_by=%s
                       WHERE id=%s""",
                    (outcome_value, brier_score, brier_skill_score, verified_by, prediction_id))
    except Exception as e:
        print(f"ERROR [pg_write_collection] predictions verified 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_tianji_reasoning_trace(trace: dict) -> None:
    conn = _conn()
    if conn is None:
        return
    import json as _json
    try:
        with conn:
            with conn.cursor() as cur:
                nid = _next_id(cur, "tianji.reasoning_trace")
                cur.execute(
                    """INSERT INTO tianji.reasoning_trace
                       (id, prediction_id, agent_id, input_signals, historical_match,
                        confidence_basis, llm_adjustment, causal_chains, reasoning)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO NOTHING""",
                    (nid, trace.get("prediction_id"), trace.get("agent_id"),
                     _json.dumps(trace.get("input_signals", []), ensure_ascii=False),
                     trace.get("historical_match"),
                     trace.get("confidence_basis", "historical_freq"),
                     trace.get("llm_adjustment"),
                     _json.dumps(trace.get("causal_chains", []), ensure_ascii=False),
                     trace.get("reasoning")),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] reasoning_trace 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_tianji_weight_update_log(entry: dict) -> None:
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                nid = _next_id(cur, "tianji.weight_update_log")
                cur.execute(
                    """INSERT INTO tianji.weight_update_log
                       (id, updated_at, prediction_id, signal_name, target_type,
                        weight_before, weight_after, reason, notes)
                       VALUES (%s, now(), %s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO NOTHING""",
                    (nid, entry.get("prediction_id"), entry.get("signal_name"),
                     entry.get("target_type"), entry.get("weight_before"),
                     entry.get("weight_after"), entry.get("reason", "自动校准"),
                     entry.get("notes")),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] weight_update_log 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_tianji_narrative_chunk(chunk: dict) -> None:
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                nid = _next_id(cur, "tianji.narrative_chunks")
                cur.execute(
                    """INSERT INTO tianji.narrative_chunks
                       (id, source_id, source_type, primary_dimension, secondary_dimension,
                        timestamp, content, token_count, staleness_tau, embedding, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NULL, now())
                       ON CONFLICT (id) DO NOTHING""",
                    (nid, chunk.get("source_id"), chunk.get("source_type"),
                     chunk.get("primary_dimension"), chunk.get("secondary_dimension"),
                     chunk.get("timestamp"), chunk.get("content"),
                     chunk.get("token_count"), chunk.get("staleness_tau", 72)),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] narrative_chunks 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def upsert_tianji_narrative_density_flag(dimension, flagged_at, z_score, consumed=0):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO tianji.narrative_density_flags
                       (dimension, flagged_at, z_score, consumed)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (dimension) DO UPDATE SET
                         flagged_at=EXCLUDED.flagged_at, z_score=EXCLUDED.z_score,
                         consumed=EXCLUDED.consumed""",
                    (dimension, flagged_at, z_score, consumed),
                )
    except Exception as e:
        print(f"ERROR [pg_write_collection] narrative_density_flags 双写失败: {e}")
    finally:
        if conn:
            conn.close()


def delete_tianji_narrative_density_flag(dimension):
    """density_flags 清除同步（对应 SQLite DELETE FROM narrative_density_flags）。"""
    conn = _conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tianji.narrative_density_flags WHERE dimension=%s",
                    (dimension,))
    except Exception as e:
        print(f"ERROR [pg_write_collection] narrative_density_flags 删除双写失败: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    # 自测入口：仅探测连通性
    c = _conn()
    if c is None:
        print("worldsim-pg 不可达/未配置（双写将被跳过，不影响主流程）")
    else:
        with c.cursor() as cur:
            cur.execute("SELECT 1")
        c.close()
        print("worldsim-pg 可达，双写模块就绪")
