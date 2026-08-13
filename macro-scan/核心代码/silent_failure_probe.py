"""
silent_failure_probe.py — 静默失败探针（P0 修复配套，2026-08-13）

设计前提（重要，勿删）：
  C3 双写硬化的 _STATS / set_alert_hook 是**进程内**内存计数，而双写实际发生在
  scheduler 派生的各个子进程（fetch_news.py / scan_weak_signals.py / news_exporter.py …），
  因此在 scheduler 主进程注册 alert hook 无法覆盖任何真实写入路径。
  本探针因此改用**状态差**而非事件流做兜底：直接比对 PG 与 SQLite 的行数/主键差集，
  无论哪个子进程漏写、无论异常是否被吞，都能事后发现。C3 的 logging.error 负责留痕，
  本探针负责主动发现 —— 两者互补，不重复。

三类检查：
  1. dualwrite  news 五表 PG vs SQLite 主键差集（P0-1 双写静默丢数复发监控）
  2. heartbeat  data/.scheduler_heartbeat mtime 新鲜度（调度停摆监控，P0-3 复发监控）
  3. artifacts  关键产物 mtime 超时（grv_latest.json / news_export.json / observability_*.json）

性能：dualwrite 走快路径 —— 先比 count(*)，相等即跳过差集计算；仅 count 不等时才拉主键
      集合定位缺口，并把缺口清单落 data/dualwrite_gap.json 供人工触发 reconcile_backfill.py。

告警：ntfy（ntfy_utils.push_text_with_priority），阈值见 CHECKS 常量。
退出码：0 = 全绿或仅 INFO；1 = 存在 WARN/CRIT。
用法：python silent_failure_probe.py [--dry]      --dry 只打印不推送
"""
import json
import logging
import os
import sqlite3
import sys
import time

try:
    from optim_config import DATA_DIR
except Exception:
    DATA_DIR = "/workspace/data"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [probe] %(levelname)s %(message)s")

DRY = "--dry" in sys.argv
SQLITE_PATH = os.path.join(DATA_DIR, "news.db")
GAP_REPORT = os.path.join(DATA_DIR, "dualwrite_gap.json")

PG_DSN = dict(host="worldsim-pg", port=5432, dbname="worldsim",
              user="worldsim_app", password=os.environ.get("WORLDSIM_APP_PW", ""))

# (pg_table, sqlite_table, pk_cols)
DUALWRITE_TABLES = [
    ("news.articles",           "articles",           ["id"]),
    ("news.scan_contexts",      "scan_contexts",      ["id"]),
    ("news.signal_episodes",    "signal_episodes",    ["id"]),
    ("news.episode_articles",   "episode_articles",   ["episode_id", "article_id"]),
    ("news.article_categories", "article_categories", ["article_id", "category"]),
]

# 双写行数差水位：<=GRACE 视为写入时序竞态（SQLite 先写、PG 后写），仅 INFO
DUALWRITE_GRACE = 3

# (相对 DATA_DIR 的路径, WARN 秒, CRIT 秒, 说明)
ARTIFACTS = [
    (".scheduler_heartbeat", 10 * 60, 20 * 60, "调度器心跳（每 30s 应刷新）"),
    ("grv_latest.json",      30 * 3600, 40 * 3600, "GRV 向量（grv_update 06:10 日频）"),
    ("news_export.json",     2 * 3600, 6 * 3600, "macro-sim 消费契约（news_export I15）"),
]

CRIT, WARN, INFO, OK = "CRIT", "WARN", "INFO", "OK"
_RANK = {OK: 0, INFO: 1, WARN: 2, CRIT: 3}


def _fmt_age(sec: float) -> str:
    if sec < 90:
        return f"{int(sec)}s"
    if sec < 5400:
        return f"{sec / 60:.0f}min"
    return f"{sec / 3600:.1f}h"


def check_dualwrite() -> list:
    """比对 news 五表 PG vs SQLite。返回 [(level, msg), ...]。"""
    out = []
    if not os.path.exists(SQLITE_PATH):
        return [(CRIT, f"dualwrite: SQLite 源不存在 {SQLITE_PATH}")]
    try:
        import psycopg
    except Exception as e:
        return [(WARN, f"dualwrite: psycopg 不可用，跳过（{e}）")]

    gaps = {}
    try:
        s = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
        p = psycopg.connect(**PG_DSN)
    except Exception as e:
        return [(CRIT, f"dualwrite: 连接失败 {e}")]

    try:
        for pg_tbl, sq_tbl, pk in DUALWRITE_TABLES:
            sc = s.execute(f"SELECT count(*) FROM {sq_tbl}").fetchone()[0]
            with p.cursor() as c:
                c.execute(f"SELECT count(*) FROM {pg_tbl}")
                pc = c.fetchone()[0]
            diff = sc - pc
            if diff == 0:
                out.append((OK, f"dualwrite {sq_tbl}: {sc} == {pc}"))
                continue
            # 慢路径：count 不等，拉主键集合定位真实缺口
            pk_sel = ", ".join(pk)
            with p.cursor() as c:
                c.execute(f"SELECT {pk_sel} FROM {pg_tbl}")
                pgset = set(c.fetchall())
            sqset = set(s.execute(f"SELECT {pk_sel} FROM {sq_tbl}").fetchall())
            only_sq = sqset - pgset
            only_pg = pgset - sqset
            n = len(only_sq)
            if n == 0:
                lvl = INFO if not only_pg else WARN
                out.append((lvl, f"dualwrite {sq_tbl}: count 差 {diff} 但 PG 无缺口"
                                 f"（only_pg={len(only_pg)}）"))
                continue
            gaps[sq_tbl] = {"pk_cols": pk, "missing_in_pg": n,
                            "sample": [list(x) for x in list(only_sq)[:20]]}
            lvl = INFO if n <= DUALWRITE_GRACE else CRIT
            out.append((lvl, f"dualwrite {sq_tbl}: PG 缺 {n} 行"
                             f"（sqlite={sc} pg={pc}）"))
    finally:
        try:
            s.close()
        except Exception:
            pass
        try:
            p.close()
        except Exception:
            pass

    if gaps:
        try:
            with open(GAP_REPORT, "w", encoding="utf-8") as f:
                json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                           "gaps": gaps}, f, ensure_ascii=False, indent=2)
            logging.info(f"缺口清单已落 {GAP_REPORT}")
        except Exception as e:
            logging.warning(f"缺口清单写入失败: {e}")
    return out


def check_artifacts() -> list:
    """关键产物 mtime 新鲜度。"""
    out = []
    now = time.time()
    for rel, warn_s, crit_s, desc in ARTIFACTS:
        path = os.path.join(DATA_DIR, rel)
        if not os.path.exists(path):
            out.append((CRIT, f"artifact {rel}: 文件不存在 — {desc}"))
            continue
        age = now - os.path.getmtime(path)
        if age >= crit_s:
            out.append((CRIT, f"artifact {rel}: 陈旧 {_fmt_age(age)}"
                              f"（CRIT 阈值 {_fmt_age(crit_s)}）— {desc}"))
        elif age >= warn_s:
            out.append((WARN, f"artifact {rel}: 陈旧 {_fmt_age(age)}"
                              f"（WARN 阈值 {_fmt_age(warn_s)}）— {desc}"))
        else:
            out.append((OK, f"artifact {rel}: {_fmt_age(age)} 前更新"))

    # 当日 observability 快照
    day = time.strftime("%Y-%m-%d")
    obs = os.path.join(DATA_DIR, f"observability_{day}.json")
    if not os.path.exists(obs):
        out.append((WARN, f"artifact observability_{day}.json: 当日快照缺失"))
    else:
        out.append((OK, f"artifact observability_{day}.json: 存在"))
    return out


def run_probe(alert: bool = True) -> tuple:
    """执行全部检查。返回 (worst_level, results)。"""
    results = []
    for fn in (check_dualwrite, check_artifacts):
        try:
            results.extend(fn())
        except Exception as e:
            results.append((CRIT, f"{fn.__name__} 自身异常: {e}"))

    worst = OK
    for lvl, _ in results:
        if _RANK[lvl] > _RANK[worst]:
            worst = lvl

    for lvl, msg in results:
        (logging.error if lvl == CRIT else
         logging.warning if lvl == WARN else logging.info)(f"[{lvl}] {msg}")

    if alert and _RANK[worst] >= _RANK[WARN]:
        bad = [f"[{l}] {m}" for l, m in results if _RANK[l] >= _RANK[WARN]]
        title = f"天枢静默失败探针 {worst}"
        body = "\n".join(bad) + f"\n\n（共 {len(results)} 项检查，{len(bad)} 项异常）"
        try:
            from ntfy_utils import push_text_with_priority
            push_text_with_priority(title, body, priority=5 if worst == CRIT else 4)
            logging.info("ntfy 已推送")
        except Exception as e:
            logging.error(f"ntfy 推送失败: {e}")
    return worst, results


def main():
    worst, results = run_probe(alert=not DRY)
    n_bad = sum(1 for l, _ in results if _RANK[l] >= _RANK[WARN])
    print(f"PROBE verdict={worst} checks={len(results)} bad={n_bad}"
          f"{' (dry)' if DRY else ''}")
    sys.exit(1 if _RANK[worst] >= _RANK[WARN] else 0)


if __name__ == "__main__":
    main()
