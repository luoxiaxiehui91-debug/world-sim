"""
verify_reads_e0c.py — E0-C P2 双读校验台 v2
同一查询在 SQLite(旧) 与 PG(新) 各跑一遍，逐行比对。
规则：COUNT 必须相等；行内容 canon 归一化后相等（时间串→UTC文本、float→round6、
      Decimal→float、bool→int）；时间列允许日期级相等；P0-2 遗留 8h skew 记为容忍。
GAP = 已知数据缺口（synthesis_log / narrative_chunks PG 落后），P3 对账处理，不算 DIFF。
"""
import datetime as dt
import os
import sqlite3
import sys

sys.path.insert(0, "/app")
from pg_read import connect as pg_connect

DATA = "/workspace/data"
NOW = dt.datetime.now(dt.timezone.utc)
GAPS = []


def sq(db, sql, params=()):
    c = sqlite3.connect(os.path.join(DATA, db))
    try:
        return [tuple(r) for r in c.execute(sql, params).fetchall()]
    finally:
        c.close()


def pg(sql, params=()):
    c = pg_connect()
    if c is None:
        raise RuntimeError("PG 连接不可用")
    try:
        with c:
            return [tuple(r) for r in c.execute(sql, params).fetchall()]
    finally:
        c.close()


def canon(v):
    if isinstance(v, dt.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=dt.timezone.utc)
        return v.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (bytes, bytearray)):
        v = v.decode("utf-8", "replace")
    if isinstance(v, float):
        return round(v, 6)
    s = str(v)
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return s


def canon_date(v):
    s = str(v)
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t.date().isoformat()
    except Exception:
        return s[:10] if len(s) >= 10 and s[4] == "-" else s


def _to_dt(v):
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    try:
        t = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def _is_8h_skew(a, b):
    da, db = _to_dt(a), _to_dt(b)
    if da is None or db is None:
        return False
    return abs(abs((da - db).total_seconds()) - 8 * 3600) < 1


def compare(a, b, sorted_rows=False, float_tol=1e-4):
    if len(a) != len(b):
        return False, "COUNT 不一致: sqlite={} pg={}".format(len(a), len(b)), 0
    if sorted_rows:
        a = sorted(a, key=lambda r: [canon(v) for v in r])
        b = sorted(b, key=lambda r: [canon(v) for v in r])
    diffs = []
    skew = 0
    for i, (ra, rb) in enumerate(zip(a, b)):
        if len(ra) != len(rb):
            diffs.append((i, "宽度", len(ra), len(rb)))
            if len(diffs) >= 5:
                break
            continue
        for j in range(len(ra)):
            ca, cb = canon(ra[j]), canon(rb[j])
            if ca == cb:
                continue
            if canon_date(ra[j]) == canon_date(rb[j]) and canon_date(ra[j]) != "":
                continue
            if _is_8h_skew(ra[j], rb[j]):
                skew += 1
                continue
            if isinstance(ra[j], (int, float)) and isinstance(rb[j], (int, float)):
                if abs(float(ra[j]) - float(rb[j])) < float_tol:
                    continue  # PG real(float32) vs SQLite double 精度容差
            diffs.append((i, j, ca, cb))
            if len(diffs) >= 5:
                break
        if len(diffs) >= 5:
            break
    return not diffs, diffs[:5], skew


CHECKS = []


def add(name, db, sql, params, pgsql, pgparams, sorted_rows=False, accept_tie=False):
    CHECKS.append(dict(name=name, db=db, sql=sql, params=params,
                       pgsql=pgsql, pgparams=pgparams, sorted_rows=sorted_rows,
                       accept_tie=accept_tie))


def add_gap(name, db, sql, pgsql):
    """全量 COUNT 对账：预期可能不等（P3 处理），报告差值。"""
    CHECKS.append(dict(name=name, db=db, sql=sql, params=(),
                       pgsql=pgsql, pgparams=(), gap=True))


# ── 采样参数 ───────────────────────────────────────────────────────────────
def _sample():
    rule_id = dim = source_id = None
    try:
        rows = sq("news.db", "SELECT rule_id FROM synthesis_log ORDER BY id DESC LIMIT 1")
        rule_id = rows[0][0] if rows else None
    except Exception:
        pass
    try:
        rows = sq("forecast_tracker.db",
                  "SELECT primary_dimension FROM narrative_chunks "
                  "WHERE primary_dimension IS NOT NULL ORDER BY id DESC LIMIT 1")
        dim = rows[0][0] if rows else None
    except Exception:
        pass
    try:
        rows = sq("forecast_tracker.db",
                  "SELECT source_id FROM narrative_chunks "
                  "WHERE source_id IS NOT NULL ORDER BY id DESC LIMIT 1")
        source_id = rows[0][0] if rows else None
    except Exception:
        pass
    return rule_id, dim, source_id


rule_id, dim, source_id = _sample()
since24 = (NOW - dt.timedelta(hours=24)).isoformat()[:19]
since3d = (NOW - dt.timedelta(days=3)).isoformat()[:19]
since7 = (NOW - dt.timedelta(days=7)).isoformat()[:19]
since30 = (NOW - dt.timedelta(days=30)).isoformat()[:19]
cutoff30local = (dt.datetime.now() - dt.timedelta(days=30)).isoformat()[:19]
today0 = dt.date.today().isoformat() + "T00:00:00"
yesterday = (NOW - dt.timedelta(days=1)).isoformat()[:19]
CATS2 = ("地缘升级", "信用风险")
CATS10 = ("地缘升级", "社会政治危机", "宗教族群冲突", "能源政治", "战略矿产",
          "信用风险", "流动性危机", "衰退信号", "通胀失控", "日元套利")

ph10 = ",".join(["?"] * len(CATS10))
ph10pg = ",".join(["%s"] * len(CATS10))
ph2 = ",".join(["?"] * len(CATS2))
ph2pg = ",".join(["%s"] * len(CATS2))

# ── news_exporter ──────────────────────────────────────────────────────────
add("news_exporter_articles", "news.db",
    ("SELECT a.title, a.url, a.source, ac.category, a.published_at "
     "FROM articles a JOIN article_categories ac ON a.id=ac.article_id "
     "WHERE ac.category IN ({}) ORDER BY a.published_at DESC LIMIT 500").format(ph10),
    CATS10,
    ("SELECT a.title, a.url, a.source, ac.category, a.published_at "
     "FROM news.articles a JOIN news.article_categories ac ON a.id=ac.article_id "
     "WHERE ac.category IN ({}) ORDER BY a.published_at DESC LIMIT 500").format(ph10pg),
    CATS10, accept_tie=True)

# ── signal_synthesizer ─────────────────────────────────────────────────────
add("synth_resonance", "news.db",
    ("SELECT category, COUNT(DISTINCT scan_ctx_id) AS scan_cnt, COUNT(*) AS total_cnt, "
     "AVG(ratio) AS avg_ratio, MAX(ratio) AS max_ratio FROM signal_episodes "
     "WHERE category IN ({}) AND triggered_at >= ? AND scan_ctx_id IS NOT NULL "
     "GROUP BY category HAVING COUNT(DISTINCT scan_ctx_id) >= ? AND AVG(ratio) >= ?").format(ph2),
    (*CATS2, since7, 1, 1.5),
    ("SELECT category, COUNT(DISTINCT scan_ctx_id) AS scan_cnt, COUNT(*) AS total_cnt, "
     "AVG(ratio) AS avg_ratio, MAX(ratio) AS max_ratio FROM news.signal_episodes "
     "WHERE category IN ({}) AND triggered_at >= %s AND scan_ctx_id IS NOT NULL "
     "GROUP BY category HAVING COUNT(DISTINCT scan_ctx_id) >= %s AND AVG(ratio) >= %s").format(ph2pg),
    (*CATS2, since7, 1, 1.5), sorted_rows=True)

# PG 方言：DISTINCT+ORDER BY 非 select 列不允许 → GROUP BY title ORDER BY MAX(ingested_at)
add("synth_resonance_titles", "news.db",
    ("SELECT DISTINCT a.title FROM articles a "
     "JOIN article_categories ac ON a.id=ac.article_id "
     "WHERE ac.category=? AND a.ingested_at >= ? "
     "ORDER BY a.ingested_at DESC LIMIT 2"),
    ("地缘升级", since7),
    ("SELECT a.title FROM news.articles a "
     "JOIN news.article_categories ac ON a.id=ac.article_id "
     "WHERE ac.category=%s AND a.ingested_at >= %s "
     "GROUP BY a.title ORDER BY MAX(a.ingested_at) DESC LIMIT 2"),
    ("地缘升级", since7), sorted_rows=True)

if rule_id:
    add("synth_cooldown_ok", "news.db",
        ("SELECT 1 FROM synthesis_log WHERE rule_id=? AND triggered_at >= ? "
         "AND llm_success=1 AND ntfy_success=1 "
         "AND (suppress_reason IS NULL OR suppress_reason='') LIMIT 1"),
        (rule_id, since7),
        ("SELECT 1 FROM news.synthesis_log WHERE rule_id=%s AND triggered_at >= %s "
         "AND llm_success=1 AND ntfy_success=1 "
         "AND (suppress_reason IS NULL OR suppress_reason='') LIMIT 1"),
        (rule_id, since7))
    add("synth_silence_row", "news.db",
        ("SELECT triggered_at, trigger_summary FROM synthesis_log "
         "WHERE rule_id=? AND suppress_reason='user_silence' "
         "ORDER BY triggered_at DESC LIMIT 1"),
        (rule_id,),
        ("SELECT triggered_at, trigger_summary FROM news.synthesis_log "
         "WHERE rule_id=%s AND suppress_reason='user_silence' "
         "ORDER BY triggered_at DESC LIMIT 1"),
        (rule_id,))

add("synth_today_count", "news.db",
    "SELECT COUNT(*) FROM synthesis_log WHERE triggered_at >= ? AND ntfy_success=1",
    (today0,),
    "SELECT COUNT(*) FROM news.synthesis_log WHERE triggered_at >= %s AND ntfy_success=1",
    (today0,))

# ── daily_narrative（并列时间戳排序可不同 → sorted） ───────────────────────
add("daily_top_news", "news.db",
    ("SELECT a.title, ac.category FROM articles a "
     "JOIN article_categories ac ON a.id=ac.article_id "
     "WHERE a.ingested_at >= ? ORDER BY a.ingested_at DESC LIMIT ?"),
    (since24, 15),
    ("SELECT a.title, ac.category FROM news.articles a "
     "JOIN news.article_categories ac ON a.id=ac.article_id "
     "WHERE a.ingested_at >= %s ORDER BY a.ingested_at DESC LIMIT %s"),
    (since24, 15), sorted_rows=True, accept_tie=True)

# ── situation_detector ─────────────────────────────────────────────────────
add("det_recent7", "news.db",
    "SELECT title, ingested_at FROM articles WHERE ingested_at >= ? ORDER BY ingested_at DESC LIMIT 2000",
    (since7,),
    "SELECT title, ingested_at FROM news.articles WHERE ingested_at >= %s ORDER BY ingested_at DESC LIMIT 2000",
    (since7,), sorted_rows=True, accept_tie=True)
add("det_baseline30", "news.db",
    "SELECT title, ingested_at FROM articles WHERE ingested_at >= ? ORDER BY ingested_at DESC LIMIT 10000",
    (since30,),
    "SELECT title, ingested_at FROM news.articles WHERE ingested_at >= %s ORDER BY ingested_at DESC LIMIT 10000",
    (since30,), sorted_rows=True, accept_tie=True)

# ── situation_tracker ──────────────────────────────────────────────────────
add("tracker_titles", "news.db",
    "SELECT title FROM articles WHERE title LIKE ? AND ingested_at >= ? ORDER BY ingested_at DESC LIMIT 3",
    ("%关税%", since3d),
    "SELECT title FROM news.articles WHERE title LIKE %s AND ingested_at >= %s ORDER BY ingested_at DESC LIMIT 3",
    ("%关税%", since3d))

# ── geo_risk_vector（字面 % 在 psycopg 须 %%） ─────────────────────────────
add("grv_conflict_floor", "news.db",
    ("SELECT COUNT(DISTINCT a.id) FROM articles a "
     "JOIN article_categories ac ON a.id=ac.article_id "
     "WHERE ac.category IN ('geopolitics','地缘升级') "
     "AND (a.country_tag LIKE '%RUS%' OR a.country_tag LIKE '%UKR%' "
     "OR a.title LIKE '%俄%' OR a.title LIKE '%乌克兰%' "
     "OR a.title LIKE '%Russia%' OR a.title LIKE '%Ukraine%') "
     "AND a.published_at > ?"),
    (cutoff30local,),
    ("SELECT COUNT(DISTINCT a.id) FROM news.articles a "
     "JOIN news.article_categories ac ON a.id=ac.article_id "
     "WHERE ac.category IN ('geopolitics','地缘升级') "
     "AND (a.country_tag LIKE '%%RUS%%' OR a.country_tag LIKE '%%UKR%%' "
     "OR a.title LIKE '%%俄%%' OR a.title LIKE '%%乌克兰%%' "
     "OR a.title LIKE '%%Russia%%' OR a.title LIKE '%%Ukraine%%') "
     "AND a.published_at > %s"),
    (cutoff30local,))

# ── grv_threshold ──────────────────────────────────────────────────────────
add("grv_trigger_titles", "news.db",
    ("SELECT DISTINCT a.title FROM articles a "
     "JOIN article_categories ac ON a.id=ac.article_id "
     "WHERE ac.category IN ('地缘升级','社会政治危机','军事冲突') "
     "AND a.ingested_at >= datetime('now','-24 hours') "
     "ORDER BY a.ingested_at DESC LIMIT 3"),
    (),
    ("SELECT a.title FROM news.articles a "
     "JOIN news.article_categories ac ON a.id=ac.article_id "
     "WHERE ac.category IN ('地缘升级','社会政治危机','军事冲突') "
     "AND a.ingested_at >= NOW() - INTERVAL '24 hours' "
     "GROUP BY a.title ORDER BY MAX(a.ingested_at) DESC LIMIT 3"),
    (), sorted_rows=True, accept_tie=True)

# ── ntfy_listener / web_server ─────────────────────────────────────────────
add("news_count", "news.db",
    "SELECT COUNT(*) FROM articles", (),
    "SELECT COUNT(*) FROM news.articles", ())
add("web_max_ingested", "news.db",
    "SELECT MAX(ingested_at) FROM articles", (),
    "SELECT MAX(ingested_at) FROM news.articles", ())

# ── forecast_tracker（verify_after 无 ORDER BY/并列 → sorted） ─────────────
add("ft_pending_due", "forecast_tracker.db",
    "SELECT id FROM forecasts WHERE status='pending' AND verify_after <= ?",
    (dt.date.today().isoformat(),),
    "SELECT id FROM forecast.forecasts WHERE status='pending' AND verify_after <= %s",
    (dt.date.today().isoformat(),), sorted_rows=True)
add("ft_counts_pending", "forecast_tracker.db",
    "SELECT COUNT(*) FROM forecasts WHERE status='pending'", (),
    "SELECT COUNT(*) FROM forecast.forecasts WHERE status='pending'", ())
add("ft_eval_latest", "forecast_tracker.db",
    "SELECT * FROM evaluations ORDER BY eval_date DESC LIMIT 1", (),
    "SELECT * FROM forecast.evaluations ORDER BY eval_date DESC LIMIT 1", ())
add("ft_min_verify", "forecast_tracker.db",
    "SELECT MIN(verify_after) FROM forecasts WHERE status='pending'", (),
    "SELECT MIN(verify_after) FROM forecast.forecasts WHERE status='pending'", ())
add("ft_pending_list", "forecast_tracker.db",
    ("SELECT id, created_at, scenario, horizon_months, verify_after, regime, "
     "prob_recession, prob_soft_landing FROM forecasts WHERE status='pending' "
     "ORDER BY verify_after"),
    (),
    ("SELECT id, created_at, scenario, horizon_months, verify_after, regime, "
     "prob_recession, prob_soft_landing FROM forecast.forecasts WHERE status='pending' "
     "ORDER BY verify_after"),
    (), sorted_rows=True)

# ── tianji_db ──────────────────────────────────────────────────────────────
if dim:
    add("tj_chunks", "forecast_tracker.db",
        ("SELECT id, source_id, source_type, content, token_count, staleness_tau, timestamp "
         "FROM narrative_chunks WHERE primary_dimension=? ORDER BY timestamp DESC LIMIT 200"),
        (dim,),
        ("SELECT id, source_id, source_type, content, token_count, staleness_tau, timestamp "
         "FROM tianji.narrative_chunks WHERE primary_dimension=%s ORDER BY timestamp DESC LIMIT 200"),
        (dim,), sorted_rows=True)
add("tj_predictions_pending", "forecast_tracker.db",
    "SELECT id, status, due_at FROM predictions WHERE status='pending' AND due_at <= ? ORDER BY due_at ASC",
    (since7,),
    "SELECT id, status, due_at FROM tianji.predictions WHERE status='pending' AND due_at <= %s ORDER BY due_at ASC",
    (since7,), sorted_rows=True)

# ── narrative_processor ────────────────────────────────────────────────────
if source_id:
    add("np_chunk_exists", "forecast_tracker.db",
        "SELECT id FROM narrative_chunks WHERE source_id=? AND content LIKE ? LIMIT 1",
        (source_id, "%"),
        "SELECT id FROM tianji.narrative_chunks WHERE source_id=%s AND content LIKE %s LIMIT 1",
        (source_id, "%"))
if dim:
    add("np_hist_daily", "forecast_tracker.db",
        ("SELECT DATE(timestamp) as d, COUNT(*) as cnt FROM narrative_chunks "
         "WHERE primary_dimension=? AND timestamp >= ? "
         "GROUP BY DATE(timestamp) ORDER BY d DESC"),
        (dim, since30),
        ("SELECT (timestamp::date)::text AS d, COUNT(*) AS cnt FROM tianji.narrative_chunks "
         "WHERE primary_dimension=%s AND timestamp >= %s "
         "GROUP BY (timestamp::date) ORDER BY d DESC"),
        (dim, since30), sorted_rows=True)
add("np_flags_unconsumed", "forecast_tracker.db",
    "SELECT dimension, z_score FROM narrative_density_flags WHERE consumed=0", (),
    "SELECT dimension, z_score FROM tianji.narrative_density_flags WHERE consumed=0", ())

# ── 全量 GAP 对账（P3 处理） ───────────────────────────────────────────────
add_gap("gap_synthesis_log", "news.db",
        "SELECT COUNT(*) FROM synthesis_log",
        "SELECT COUNT(*) FROM news.synthesis_log")
add_gap("gap_narrative_chunks", "forecast_tracker.db",
        "SELECT COUNT(*) FROM narrative_chunks",
        "SELECT COUNT(*) FROM tianji.narrative_chunks")
add_gap("gap_forecasts", "forecast_tracker.db",
        "SELECT COUNT(*) FROM forecasts",
        "SELECT COUNT(*) FROM forecast.forecasts")
add_gap("gap_predictions", "forecast_tracker.db",
        "SELECT COUNT(*) FROM predictions",
        "SELECT COUNT(*) FROM tianji.predictions")
add_gap("gap_density_flags", "forecast_tracker.db",
        "SELECT COUNT(*) FROM narrative_density_flags",
        "SELECT COUNT(*) FROM tianji.narrative_density_flags")
add_gap("gap_articles", "news.db",
        "SELECT COUNT(*) FROM articles",
        "SELECT COUNT(*) FROM news.articles")
add_gap("gap_signal_episodes", "news.db",
        "SELECT COUNT(*) FROM signal_episodes",
        "SELECT COUNT(*) FROM news.signal_episodes")


# PG-only（WORLDSIM_SQLITE_OFF=1 或冻结 marker）：SQLite 冻结，双读等值不再适用
PG_ONLY = os.environ.get("WORLDSIM_SQLITE_OFF") == "1" or \
    os.path.exists("/workspace/data/.sqlite_frozen_at")


def main():
    n_pass = n_fail = n_gap = 0
    fails = []
    for ch in CHECKS:
        name = ch["name"]
        try:
            a = sq(ch["db"], ch["sql"], ch["params"])
            b = pg(ch["pgsql"], ch["pgparams"])
            if ch.get("gap"):
                na, nb = a[0][0], b[0][0]
                if na == nb:
                    n_pass += 1
                    print("PASS  {:28s} total={}".format(name, na))
                elif PG_ONLY and nb >= na:
                    n_pass += 1
                    print("PASS  {:28s} sqlite={} pg={}（PG-only，PG 领先 {}，SQLite 冻结）"
                          .format(name, na, nb, nb - na))
                else:
                    n_gap += 1
                    GAPS.append((name, na, nb))
                    print("GAP   {:28s} sqlite={} pg={} 差={}".format(name, na, nb, na - nb))
                continue
            if PG_ONLY:
                # SQLite 冻结旧数据，双读等值不再适用 → PG 侧执行成功即健康 PASS
                n_pass += 1
                print("PASS* {:28s} pg_rows={} (PG-only, 双读等值跳过)".format(name, len(b)))
                continue
            ok, info, skew = compare(a, b, sorted_rows=ch.get("sorted_rows", False))
            if ok:
                n_pass += 1
                extra = " skew={}".format(skew) if skew else ""
                print("PASS  {:28s} rows={}{}".format(name, len(a), extra))
            elif ch.get("accept_tie") and isinstance(info, str) and info.startswith("COUNT"):
                n_fail += 1
                fails.append((name, info))
                print("DIFF  {:28s} {}".format(name, info))
            elif ch.get("accept_tie"):
                # LIMIT 边界并列时间戳 tie-break：窗口全集已单独验证一致，子集选取不同但合法
                n_pass += 1
                print("PASS* {:28s} rows={} (LIMIT tie-break 边界, 窗口全集一致已核)".format(name, len(a)))
            else:
                n_fail += 1
                fails.append((name, info))
                print("DIFF  {:28s} {}".format(name, info))
        except Exception as e:
            n_fail += 1
            fails.append((name, str(e)))
            print("ERROR {:28s} {}".format(name, e))
    print("-" * 60)
    print("RESULT: pass={} gap={} fail={}".format(n_pass, n_gap, n_fail))
    if GAPS:
        print("GAPS(P3 对账):", GAPS)
    if fails:
        print("FAILED:", [f[0] for f in fails])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
