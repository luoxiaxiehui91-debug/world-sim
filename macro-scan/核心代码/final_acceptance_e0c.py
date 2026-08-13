# -*- coding: utf-8 -*-
"""final_acceptance_e0c.py — E0-C P1-P3 全量验收（只读，不写数据、不推 ntfy）。
覆盖：全量 import / scheduler JOBS / 心跳 / 探针(alert=False) / harness /
      pg_read 行边界归一化 / 关键读函数真实数据 / news_export.json / 探针缺口文件 / 当日产物。
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/app")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("{}  {}{}".format("PASS" if cond else "FAIL", name, (" | " + str(detail) if detail else "")))


# 1. 全量 import（改过的 14 模块 + 探针 + pg 双写）
mods = ["pg_read", "pg_write_collection", "news_exporter", "ntfy_listener",
        "geo_risk_vector", "grv_threshold", "daily_narrative", "situation_detector",
        "situation_tracker", "signal_synthesizer", "observability", "web_server",
        "forecast_tracker", "tianji_db", "narrative_processor", "silent_failure_probe"]
imp_err = []
for m in mods:
    try:
        __import__(m)
    except Exception as e:
        imp_err.append((m, repr(e)))
check("import_16_mods", not imp_err, "; ".join("{}:{}".format(m, e) for m, e in imp_err[:3]))

# 2. scheduler JOBS
try:
    import scheduler
    jobs = scheduler.JOBS
    check("scheduler_JOBS_54", len(jobs) == 54, "JOBS={}".format(len(jobs)))
    check("probe_in_jobs", any("silent_probe" in str(j[0]) for j in jobs))
except Exception as e:
    check("scheduler_JOBS_54", False, repr(e))
    check("probe_in_jobs", False, "")

# 3. 心跳
hb = "/workspace/data/.scheduler_heartbeat"
try:
    hb_age = time.time() - os.path.getmtime(hb)
    check("heartbeat_<600s", 0 <= hb_age < 600, "age={:.0f}s".format(hb_age))
except Exception as e:
    check("heartbeat_<600s", False, repr(e))

# 4. 探针（alert=False，不推 ntfy）— run_probe 返回 (verdict, [(status, detail), ...])
try:
    from silent_failure_probe import run_probe
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        probe = run_probe(alert=False)
    if isinstance(probe, tuple) and len(probe) == 2:
        verdict = probe[0]
        n_ok = sum(1 for s, _ in probe[1] if s == "OK")
        n_all = len(probe[1])
        ok = verdict in ("OK", "WARN") and n_ok == n_all
        check("probe_alert_off", ok, "verdict={} {}/{} OK".format(verdict, n_ok, n_all))
    else:
        check("probe_alert_off", False, "unexpected return: {!r}".format(probe))
except Exception as e:
    check("probe_alert_off", False, repr(e))

# 5. harness 全绿
try:
    r = subprocess.run([sys.executable, "/app/verify_reads_e0c.py"],
                       capture_output=True, text=True, timeout=300)
    tail = [l for l in r.stdout.splitlines() if "RESULT" in l or "FAILED" in l or "GAPS" in l]
    check("harness_no_fail", "fail=0" in r.stdout, tail)
except Exception as e:
    check("harness_31_0_0", False, repr(e))

# 6. pg_read 行边界归一化
try:
    from pg_read import connect
    c = connect()
    with c:
        sample = c.execute("SELECT published_at FROM news.articles ORDER BY id DESC LIMIT 1").fetchone()[0]
    check("pg_norm_utc_text", isinstance(sample, str) and "T" in sample and "+" not in sample, repr(sample))
except Exception as e:
    check("pg_norm_utc_text", False, repr(e))

# 7. 关键读函数真实数据
try:
    import situation_tracker as st
    import grv_threshold as gt
    import daily_narrative as dn
    import observability as obs
    t = st._query_recent_articles(["关税"], 3)
    check("tracker_pg_read", len(t) == 3, "n={}".format(len(t)))
    g = gt._get_trigger_titles_from_news()
    check("grv_pg_read", len(g) >= 1, "n={}".format(len(g)))
    d = dn._query_top_news(3)
    check("daily_pg_read", len(d) >= 1, "n={}".format(len(d)))
    s = obs.read_synthesizer_stats()
    check("obs_stats_real", s["rules_evaluated"] > 0, json.dumps(s, ensure_ascii=False))
except Exception as e:
    check("reader_funcs", False, repr(e))

# 8. news_export.json（news_exporter 已切 PG 产出）
try:
    with open("/workspace/data/news_export.json", encoding="utf-8") as f:
        payload = json.load(f)
    arts = payload.get("articles", [])
    check("export_json", payload.get("_schema_version") == "1.0" and len(arts) > 0,
          "articles={} updated={}".format(len(arts), payload.get("updated")))
except Exception as e:
    check("export_json", False, repr(e))

# 9. 探针缺口文件（无缺口则不存在）
check("no_dualwrite_gap_file", not os.path.exists("/workspace/data/dualwrite_gap.json"))

# 10. 当日 observability 产物
check("obs_file_today", os.path.exists("/workspace/data/observability_2026-08-13.json"))

print("=" * 60)
print("FINAL: pass={} fail={}".format(len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", FAIL)
sys.exit(1 if FAIL else 0)
