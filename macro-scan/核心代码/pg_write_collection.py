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

[C3 双写硬化] 连接缓存复用 + 有界重试退避 + 失败计数告警（绝不静默）+ 公开签名冻结。
"""

import os
import threading
import time
import logging

from datetime import datetime, timezone

_PG_HOST = "worldsim-pg"
_PG_PORT = 5432
_PG_DB = "worldsim"
_PG_USER = "worldsim_app"
_SEARCH_PATH = "news,forecast,tianji,public"


# ─────────────────────────────────────────────────────────────────────────────
# C3 双写硬化基础设施（连接缓存 / 重试 / 告警 / 计数）
# 设计目标：①连接缓存复用（消除逐条 _conn 连接风暴）②有界重试+退避
#          ③失败计数+告警（绝不静默）④公开函数签名冻结 ⑤绝不阻断 SQLite（异常不向上抛）
# ─────────────────────────────────────────────────────────────────────────────

_MAX_RETRY = 3
_BACKOFF = (0.1, 0.3, 0.7)  # attempt 0/1/2 退避

# 瞬时异常 sqlstate（重试）：连接类 + 序列化失败/死锁 + 资源上限 + 管理中断/停库 + 关闭/无响应
_TRANSIENT_SQLSTATES = {
    "08000", "08003", "08006", "08001", "08004", "08P01",  # 连接类
    "40001", "40P01",                                      # 序列化失败 / 死锁
    "53300", "53400",                                      # 连接数过多 / 配置上限
    "57P01", "57P02", "57P03",                             # 管理中断 / 停库
    "55P02", "55P03",                                      # 关闭 / 无响应
}

_log = logging.getLogger("pg_write_collection")

_PG_CONN = None
_PG_LOCK = threading.Lock()
_STATS_LOCK = threading.Lock()
_STATS = {"connect_fail": 0, "retry": 0, "fail": 0, "ok": 0}

_alert_hook = None  # 默认 None → 用 _log.error；ops 可 set_alert_hook 挂载监控


def set_alert_hook(fn):
    """挂载告警回调 fn(table, pk_repr, sqlstate, err) → 供部署侧监控（Pushgateway/告警文件）。"""
    global _alert_hook
    _alert_hook = fn


def get_pg_write_stats() -> dict:
    """供 ops 健康检查/对账读取（返回副本，线程安全）。"""
    with _STATS_LOCK:
        return dict(_STATS)


def _emit_alert(table, pk_repr, sqlstate, err):
    _log.error("PG dual-write FAILED table=%s pk=%s sqlstate=%s err=%s",
               table, pk_repr, sqlstate, err)
    if _alert_hook is not None:
        try:
            _alert_hook(table, pk_repr, sqlstate, err)
        except Exception:
            pass


def _classify(exc) -> bool:
    """True=瞬时(重试)；False=永久/未知(不重试)。"""
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate in _TRANSIENT_SQLSTATES:
        return True
    if sqlstate is not None:
        return False  # 有 sqlstate 但不在瞬时集合（如 23505/23502/23503/42P01）→ 永久
    # 无 sqlstate：保守按 psycopg 连接/接口错误判瞬时
    try:
        import psycopg
    except Exception:
        return False
    return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))


def _record_failure(table, pk_repr, exc):
    with _STATS_LOCK:
        _STATS["fail"] += 1
    _emit_alert(table, pk_repr, getattr(exc, "sqlstate", None), exc)


def _record_retry(table, pk_repr, exc):
    with _STATS_LOCK:
        _STATS["retry"] += 1
    _log.warning("PG dual-write RETRY table=%s pk=%s sqlstate=%s err=%s",
                 table, pk_repr, getattr(exc, "sqlstate", None), exc)


def _record_connect_fail(table, pk_repr):
    with _STATS_LOCK:
        _STATS["connect_fail"] += 1
    print(f"ERROR [pg_write_collection] 连接 worldsim-pg 失败（不影响原流程）table={table} pk={pk_repr}")
    _emit_alert(table, pk_repr, None, "connect_fail")


def _get_conn():
    """模块级缓存连接；惰性建立、失效重连（带退避）。不可用时返回 None（原契约不变）。"""
    global _PG_CONN
    with _PG_LOCK:
        if _PG_CONN is not None and not getattr(_PG_CONN, "closed", True) \
                and not getattr(_PG_CONN, "broken", False):
            return _PG_CONN
        # 重建（自身带退避，最多 _MAX_RETRY 次）
        pw = os.environ.get("WORLDSIM_APP_PW")
        if not pw:
            print("ERROR [pg_write_collection] WORLDSIM_APP_PW 未设置，跳过双写")
            return None
        try:
            import psycopg
        except Exception as e:
            print(f"ERROR [pg_write_collection] psycopg 不可用，跳过双写: {e}")
            return None
        last_exc = None
        for attempt in range(_MAX_RETRY):
            try:
                _PG_CONN = psycopg.connect(
                    host=_PG_HOST, port=_PG_PORT, dbname=_PG_DB, user=_PG_USER,
                    password=pw, connect_timeout=10,
                    options=f"-c search_path={_SEARCH_PATH}",
                )
                return _PG_CONN
            except Exception as e:
                last_exc = e
                _log.warning("PG connect attempt %d failed: %s", attempt + 1, e)
                time.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])
        _record_connect_fail("__connect__", "n/a")
        return None


def _next_id(table: str) -> int:
    """取某 BIGSERIAL 表下一个 id（缓存连接）。单容器顺序写，无并发竞争。

    PG 不可用时降级返回 0；调用方 _write 仍会失败并被记录/告警，不会阻断主流程。
    """
    conn = _get_conn()
    if conn is None:
        return 0
    with _PG_LOCK:
        with conn:  # SELECT 也走事务边界，避免残留 open tx
            with conn.cursor() as cur:
                cur.execute(f"SELECT COALESCE(MAX(id),0)+1 FROM {table}")
                return cur.fetchone()[0]


def _write(sql: str, params, *, table: str, pk_repr) -> bool:
    """统一写入路径：连接缓存 + 有界重试+退避 + 失败告警（绝不静默）+ 绝不抛。

    返回 True/False（不向调用方暴露，签名契约保持“返回 None 的副作用式”）。
    """
    global _PG_CONN
    conn = _get_conn()
    if conn is None:
        _record_connect_fail(table, pk_repr)
        return False
    last_exc = None
    for attempt in range(_MAX_RETRY):
        try:
            with conn:  # 事务边界：成功 commit / 异常 rollback
                with conn.cursor() as cur:
                    cur.execute(sql, params)
            with _STATS_LOCK:
                _STATS["ok"] += 1
            return True
        except Exception as e:
            last_exc = e
            if _classify(e):
                _record_retry(table, pk_repr, e)
                _PG_CONN = None  # 连接可能已坏，下次重建
                time.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])
                conn = _get_conn()
                if conn is None:
                    _record_connect_fail(table, pk_repr)
                    break
                continue
            break  # 永久/未知：不重试
    _record_failure(table, pk_repr, last_exc)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# news.schema
# ─────────────────────────────────────────────────────────────────────────────

def upsert_news_scan_context(ctx_id, scan_time, vix, t10y2y, baa10y, dff,
                              regime, vix_regime, data_quality):
    # [C3] 签名对齐：由 6 参扩为 9 参（regime/vix_regime/data_quality），与 news_db:230
    # 调用方 + PG news.scan_contexts 列一致；修复原 6 参函数对 9 参调用方会抛 TypeError 的潜在缺陷。
    _write(
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
        table="news.scan_contexts", pk_repr=repr(ctx_id),
    )


def upsert_news_article(aid, url, content_hash, title, source, published_at,
                         ingested_at, country_tag, ingest_ctx_id, pub_ctx_id):
    _write(
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
        table="news.articles", pk_repr=repr(aid),
    )


def upsert_news_article_category(article_id, category):
    _write(
        """INSERT INTO news.article_categories (article_id, category)
           VALUES (%s,%s)
           ON CONFLICT (article_id, category) DO NOTHING""",
        (article_id, category),
        table="news.article_categories", pk_repr=repr(article_id),
    )


def upsert_news_signal_episode(ep_id, category, triggered_at, ratio, level, scan_ctx_id):
    _write(
        """INSERT INTO news.signal_episodes
           (id, category, triggered_at, ratio, level, scan_ctx_id)
           VALUES (%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO UPDATE SET
             category=EXCLUDED.category, triggered_at=EXCLUDED.triggered_at,
             ratio=EXCLUDED.ratio, level=EXCLUDED.level,
             scan_ctx_id=EXCLUDED.scan_ctx_id""",
        (ep_id, category, triggered_at, ratio, level, scan_ctx_id),
        table="news.signal_episodes", pk_repr=repr(ep_id),
    )


def upsert_news_episode_article(episode_id, article_id):
    _write(
        """INSERT INTO news.episode_articles (episode_id, article_id)
           VALUES (%s,%s)
           ON CONFLICT (episode_id, article_id) DO NOTHING""",
        (episode_id, article_id),
        table="news.episode_articles", pk_repr=repr(episode_id),
    )


def delete_news_articles(old_ids: list) -> None:
    """prune 同步：按 id 批量删 articles 及其关联（article_categories/episode_articles）。"""
    if not old_ids:
        return
    batch = 200
    for i in range(0, len(old_ids), batch):
        chunk = old_ids[i:i + batch]
        ph = ",".join(["%s"] * len(chunk))
        _write(f"DELETE FROM news.article_categories WHERE article_id IN ({ph})", chunk,
               table="news.article_categories", pk_repr=f"ids={len(chunk)}")
        _write(f"DELETE FROM news.episode_articles WHERE article_id IN ({ph})", chunk,
               table="news.episode_articles", pk_repr=f"ids={len(chunk)}")
        _write(f"DELETE FROM news.articles WHERE id IN ({ph})", chunk,
               table="news.articles", pk_repr=f"ids={len(chunk)}")


# ─────────────────────────────────────────────────────────────────────────────
# forecast.schema
# ─────────────────────────────────────────────────────────────────────────────

def upsert_forecast(fid, created_at, scenario, horizon_months, verify_after, country,
                    status, regime, stress_signals, prob_recession, prob_deep_recession,
                    prob_soft_landing, prob_stagflation, prob_crisis_vix,
                    gdp_p10, gdp_p50, gdp_p90, unrate_p50, cpi_yoy_p50,
                    input_json, notes):
    _write(
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
        table="forecast.forecasts", pk_repr=repr(fid),
    )


def update_forecast_status(fid, status):
    _write(
        "UPDATE forecast.forecasts SET status=%s WHERE id=%s", (status, fid),
        table="forecast.forecasts", pk_repr=repr(fid),
    )


def upsert_actual(period, actual_regime, gdp_growth, unemployment, cpi_yoy,
                  labeled_at, label_source, notes=""):
    _write(
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
        table="forecast.actuals", pk_repr=repr(period),
    )


def upsert_evaluation(eval_date, n_samples, brier_score, brier_skill,
                      recession_brier, soft_landing_brier):
    nid = _next_id("forecast.evaluations")
    if nid == 0:
        return
    _write(
        """INSERT INTO forecast.evaluations
           (id, eval_date, n_samples, brier_score, brier_skill,
            recession_brier, soft_landing_brier)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO NOTHING""",
        (nid, eval_date, n_samples, brier_score, brier_skill,
         recession_brier, soft_landing_brier),
        table="forecast.evaluations", pk_repr=repr(eval_date),
    )


# ─────────────────────────────────────────────────────────────────────────────
# tianji.schema
# ─────────────────────────────────────────────────────────────────────────────

def upsert_tianji_prediction(pred: dict) -> None:
    _write(
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
        table="tianji.predictions", pk_repr=repr(pred.get("id")),
    )


def update_tianji_prediction_verified(prediction_id, outcome_value, brier_score,
                                       brier_skill_score=None, verified_by="auto"):
    _write(
        """UPDATE tianji.predictions SET
             status='verified', outcome_value=%s, brier_score=%s,
             brier_skill_score=%s, verified_at=now(), verified_by=%s
           WHERE id=%s""",
        (outcome_value, brier_score, brier_skill_score, verified_by, prediction_id),
        table="tianji.predictions", pk_repr=repr(prediction_id),
    )


def upsert_tianji_reasoning_trace(trace: dict) -> None:
    import json as _json
    nid = _next_id("tianji.reasoning_trace")
    if nid == 0:
        return
    _write(
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
        table="tianji.reasoning_trace", pk_repr=repr(trace.get("prediction_id")),
    )


def upsert_tianji_weight_update_log(entry: dict) -> None:
    nid = _next_id("tianji.weight_update_log")
    if nid == 0:
        return
    _write(
        """INSERT INTO tianji.weight_update_log
           (id, updated_at, prediction_id, signal_name, target_type,
            weight_before, weight_after, reason, notes)
           VALUES (%s, now(), %s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO NOTHING""",
        (nid, entry.get("prediction_id"), entry.get("signal_name"),
         entry.get("target_type"), entry.get("weight_before"),
         entry.get("weight_after"), entry.get("reason", "自动校准"),
         entry.get("notes")),
        table="tianji.weight_update_log", pk_repr=repr(entry.get("prediction_id")),
    )


def upsert_tianji_narrative_chunk(chunk: dict) -> None:
    nid = _next_id("tianji.narrative_chunks")
    if nid == 0:
        return
    _write(
        """INSERT INTO tianji.narrative_chunks
           (id, source_id, source_type, primary_dimension, secondary_dimension,
            timestamp, content, token_count, staleness_tau, embedding, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NULL, now())
           ON CONFLICT (id) DO NOTHING""",
        (nid, chunk.get("source_id"), chunk.get("source_type"),
         chunk.get("primary_dimension"), chunk.get("secondary_dimension"),
         chunk.get("timestamp"), chunk.get("content"),
         chunk.get("token_count"), chunk.get("staleness_tau", 72)),
        table="tianji.narrative_chunks", pk_repr=repr(chunk.get("source_id")),
    )


def upsert_tianji_narrative_density_flag(dimension, flagged_at, z_score, consumed=0):
    _write(
        """INSERT INTO tianji.narrative_density_flags
           (dimension, flagged_at, z_score, consumed)
           VALUES (%s,%s,%s,%s)
           ON CONFLICT (dimension) DO UPDATE SET
             flagged_at=EXCLUDED.flagged_at, z_score=EXCLUDED.z_score,
             consumed=EXCLUDED.consumed""",
        (dimension, flagged_at, z_score, consumed),
        table="tianji.narrative_density_flags", pk_repr=repr(dimension),
    )


def delete_tianji_narrative_density_flag(dimension):
    """density_flags 清除同步（对应 SQLite DELETE FROM narrative_density_flags）。"""
    _write(
        "DELETE FROM tianji.narrative_density_flags WHERE dimension=%s",
        (dimension,),
        table="tianji.narrative_density_flags", pk_repr=repr(dimension),
    )


if __name__ == "__main__":
    # 自测入口：仅探测连通性（连接长连，不关闭）
    c = _get_conn()
    if c is None:
        print("worldsim-pg 不可达/未配置（双写将被跳过，不影响主流程）")
    else:
        with c.cursor() as cur:
            cur.execute("SELECT 1")
        print("worldsim-pg 可达，双写模块就绪")
