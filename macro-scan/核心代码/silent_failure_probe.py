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


FROZEN_MARKER = os.path.join(DATA_DIR, ".sqlite_frozen_at")
BACKUP_MARKER = os.path.join(DATA_DIR, ".last_pg_backup")

# FRED 关键序列滞后监控（V4c）：(相对 DATA_DIR 的 csv, 名称, max_lag_days)
# max_lag = 该序列正常发布节奏 + 缓冲；超 max_lag WARN、超 max_lag*2 CRIT
FRED_LAG_WATCH = [
    ("fred_history/VIXCLS.csv",          "VIX 恐慌指数",        5),
    ("fred_history/DTWEXBGS.csv",        "美元指数",             9),
    ("fred_history/BAA10Y.csv",          "HY 信用利差",          6),
    ("fred_history/T10Y2Y.csv",          "10Y-2Y 利差",          5),
    ("fred_history/DFF.csv",             "联邦基金利率",         6),
    ("fred_history/DGS10.csv",           "美债 10Y",             5),
    ("fred_history/DGS3MO.csv",          "美债 3M",              5),
    ("fred_history/DEXJPUS.csv",         "美元/日元",            9),
    ("fred_history/DCOILWTICO.csv",      "WTI 原油",             6),
    ("fred_history/BAMLH0A0HYM2.csv",    "HY 利差(BofA)",        6),
    ("fred_history/ICSA.csv",            "初请失业金(周)",      12),
    ("fred_history/IRLTLT01JPM156N.csv", "日债 10Y(月)",        90),
    ("fred_history/GSCPI.csv",           "GSCPI(月)",           45),
]


def check_dualwrite() -> list:
    """比对 news 五表 PG vs SQLite；PG-only（.sqlite_frozen_at 存在）时验证 SQLite 冻结 + PG 健康。"""
    out = []
    frozen_at = None
    if os.path.exists(FROZEN_MARKER):
        try:
            frozen_at = float(open(FROZEN_MARKER, encoding="utf-8").read().strip())
        except Exception:
            frozen_at = 0
    if frozen_at is not None:
        try:
            import psycopg
        except Exception as e:
            return [(WARN, f"dualwrite(pg-only): psycopg 不可用，跳过（{e}）")]
        try:
            p = psycopg.connect(**PG_DSN)
        except Exception as e:
            return [(CRIT, f"dualwrite(pg-only): PG 连接失败 {e}")]
        try:
            for pg_tbl, sq_tbl, pk in DUALWRITE_TABLES:
                with p.cursor() as c:
                    c.execute(f"SELECT count(*) FROM {pg_tbl}")
                    pc = c.fetchone()[0]
                lvl = CRIT if pc <= 0 else OK
                out.append((lvl, "dualwrite(pg-only) {}: PG={}（{}）".format(
                    sq_tbl, pc, "异常" if lvl == CRIT else "健康，SQLite 冻结")))
            sq_mtime = os.path.getmtime(SQLITE_PATH) if os.path.exists(SQLITE_PATH) else 0
            if sq_mtime > frozen_at + 60:
                out.append((WARN, "dualwrite(pg-only): SQLite 仍被写"
                                  "（mtime={:.0f} > frozen={:.0f}）".format(sq_mtime, frozen_at)))
            else:
                out.append((OK, "dualwrite(pg-only): SQLite 冻结确认"))
        finally:
            try:
                p.close()
            except Exception:
                pass
        return out
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


def check_backup() -> list:
    """PG 逻辑备份新鲜度（backup-pg.sh 成功后写 .last_pg_backup marker，cron 04:00 日频）。"""
    out = []
    if not os.path.exists(BACKUP_MARKER):
        out.append((WARN, "backup .last_pg_backup: marker 缺失（backup-pg.sh 尚未成功写）"))
        return out
    age = time.time() - os.path.getmtime(BACKUP_MARKER)
    if age >= 49 * 3600:
        out.append((CRIT, f"backup .last_pg_backup: 陈旧 {_fmt_age(age)}（CRIT 阈值 49h）"))
    elif age >= 25 * 3600:
        out.append((WARN, f"backup .last_pg_backup: 陈旧 {_fmt_age(age)}（WARN 阈值 25h）"))
    else:
        out.append((OK, f"backup .last_pg_backup: {_fmt_age(age)} 前成功"))
    return out


def check_news_risk() -> list:
    """新闻风险流新鲜度（fetch_news.py 日频 06:16 写 news_risk.json；08-14 起 GDELT DOC 2.0 主源）。

    判据基于内容 updated 字段（非 mtime——降级保留旧值时 mtime 不变，写 unavailable 时 mtime 变但内容旧）：
      - status=ok 且 <2h             → OK（健康）
      - status=ok 且 2-4h            → WARN（4-8 个 30min 周期未成功）
      - unavailable 且 <2h           → OK（短时降级容忍，如 GDELT 临时 429）
      - 任何状态 >=4h                → CRIT（8+ 周期未更新）
      - 文件缺失                      → CRIT（fetch_news 从未成功写过）
      阈值随调度频率：08-14 提频 I30 后由 25h/49h 收窄为 2h/4h。
    """
    out = []
    path = os.path.join(DATA_DIR, "news_risk.json")
    if not os.path.exists(path):
        out.append((CRIT, "news_risk.json: 缺失（fetch_news 从未成功写过）"))
        return out
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        out.append((CRIT, f"news_risk.json: 解析失败 {e}"))
        return out
    status = d.get("status") or "unknown"
    updated = d.get("updated") or ""
    try:
        # updated 形如 2026-08-14T13:07:58+08:00
        import datetime as _dt
        u = _dt.datetime.fromisoformat(updated)
        if u.tzinfo is None:
            u = u.replace(tzinfo=_dt.timezone.utc)
        age = time.time() - u.timestamp()
    except Exception:
        out.append((WARN, f"news_risk.json: updated 解析失败 '{updated}'"))
        return out
    if status == "ok" and age < 2 * 3600:
        out.append((OK, f"news_risk: {status}（{_fmt_age(age)} 前更新）"))
    elif age >= 4 * 3600:
        out.append((CRIT, f"news_risk: {status} 且陈旧 {_fmt_age(age)}（CRIT 阈值 4h）"))
    elif age >= 2 * 3600:
        out.append((WARN, f"news_risk: {status} 且陈旧 {_fmt_age(age)}（WARN 阈值 2h）"))
    else:
        out.append((OK, f"news_risk: {status}（短时降级容忍 <2h）"))
    return out


# P6 零残留断言（2026-08-16 恢复严格版）：P0-D 过渡期豁免已随 D2 转 PG + 删库
# （delete_sqlite_e0c.sh e0c-p6-20260816）移除——天璇/天玑已全 PG，任何 .db 复生 = 违规。

def check_sqlite_gone() -> list:
    """SQLite 零残留断言（P6 删库后自动化守护）：data 目录出现任何 .db = 某代码复活了它。
    发现即 CRIT（防定时炸弹：scheduler 任务或验收工具静默建文件）。"""
    out = []
    try:
        hits = [f for f in os.listdir(DATA_DIR) if f.endswith(".db")]
    except Exception as e:
        return [(CRIT, "sqlite_gone: 扫描 data 失败 %s" % e)]
    if hits:
        out.append((CRIT, "sqlite_gone: 检测到 SQLite 复生文件 %s（P6 已删库，某代码静默重建）" % hits))
    else:
        out.append((OK, "sqlite_gone: data 目录无 .db 残留"))
    return out


def check_feed_fresh() -> list:
    """新增数据源新鲜度/有效性监控（08-14 加：firms date bug 教训——NRT 源可能
    静默空数据/文件过期无人知；覆盖 firms/spacelaunch/safecast_nuke 三个 08-14 源）。"""
    from datetime import datetime as _dt, timezone as _tz
    import json as _json
    out = []
    now = _dt.now(_tz.utc)
    specs = [
        ("firms_fire.json", "firms 火点", 30, "total_hotspots", "FIRMS 0 火点（疑似 date bug/API 异常，08-14 教训）"),
        ("spacelaunch.json", "spacelaunch 发射", 30, "launches_count", "spacelaunch 空/无效"),
        ("safecast_nuke.json", "safecast 核辐射", 3, "sites", "safecast 无站点"),
    ]
    for fname, label, max_h, key, empty_warn in specs:
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            out.append((CRIT, f"{label}: 文件不存在 {fname}"))
            continue
        try:
            with open(path, encoding="utf-8") as f:
                d = _json.load(f)
            fetched = d.get("fetched_at") or d.get("as_of") or ""
            age_h = 999.0
            if fetched:
                try:
                    age_h = (now - _dt.fromisoformat(fetched.replace("Z", "+00:00"))).total_seconds() / 3600
                except ValueError:
                    age_h = 999.0
            val = d.get(key)
            empty = (val is None) or (isinstance(val, (int, float)) and val <= 0) or (isinstance(val, list) and len(val) == 0)
            if empty:
                out.append((CRIT, f"{label}: {empty_warn}（{fname}）"))
            elif age_h > max_h * 2:
                out.append((CRIT, f"{label}: 数据过期 {round(age_h,1)}h（CRIT 阈值 {max_h*2}h）"))
            elif age_h > max_h:
                out.append((WARN, f"{label}: 数据偏旧 {round(age_h,1)}h（WARN 阈值 {max_h}h）"))
            else:
                out.append((OK, f"{label}: ok（{round(age_h,1)}h 前更新）"))
        except Exception as e:
            out.append((WARN, f"{label}: 读取异常 {e}"))
    return out


# P0-C (2026-08-15, 全量审查 H09 盲区补齐): 预测链活动监测状态文件
PRED_COUNT_STATE = os.path.join(DATA_DIR, ".probe_pred_count.json")
PRED_CHAIN_WARN_DAYS = 14   # 天璇仿真落表是低频事件（GRV 阈值触发），14 天无新增 → WARN
PRED_CHAIN_CRIT_DAYS = 30   # 30 天无新增 → CRIT（链条断裂数月无人察觉的 H09 场景）


def check_predictions_chain() -> list:
    """预测链活动监测（H09 盲区补齐）：PG tianji.predictions 行数增量（P0-D2 转 PG）。

    设计：探针 2h 一次，state 文件记上次行数与变化时间；本次行数 > 上次 = 有新增预测
    （天璇落表/天玑验证都在写行）；连续 N 天无新增 = 预测生成或验证可能静默停止。
    PG 只读 COUNT（天枢已有 psycopg + WORLDSIM_APP_PW + worldsim_default 网络）。
    """
    from datetime import datetime as _dt, timezone as _tz
    out = []
    try:
        import psycopg
    except Exception as e:
        out.append((WARN, f"预测链: psycopg 不可用，跳过（{e}）"))
        return out
    try:
        p = psycopg.connect(**PG_DSN)
    except Exception as e:
        out.append((WARN, f"预测链: PG 连接失败 {e}"))
        return out
    try:
        with p.cursor() as c:
            c.execute("SELECT COUNT(*) FROM tianji.predictions")
            cnt = c.fetchone()[0]
    except Exception as e:
        out.append((WARN, f"预测链: tianji.predictions 读取失败 {e}"))
        return out
    finally:
        try:
            p.close()
        except Exception:
            pass
    state = {}
    try:
        with open(PRED_COUNT_STATE, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        pass
    now = _dt.now(_tz.utc).timestamp()
    last_cnt = int(state.get("count", 0))
    last_chg = float(state.get("changed_at", now))
    if cnt > last_cnt:
        state = {"count": cnt, "changed_at": now, "last_growth": cnt - last_cnt}
        try:
            with open(PRED_COUNT_STATE, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except Exception:
            pass
        out.append((OK, f"预测链: predictions {cnt} 行（较上次新增 {cnt - last_cnt}）"))
    else:
        days = (now - last_chg) / 86400.0
        if days >= PRED_CHAIN_CRIT_DAYS:
            out.append((CRIT, f"预测链: {days:.0f} 天无新增预测（{cnt} 行），链条可能静默断裂"))
        elif days >= PRED_CHAIN_WARN_DAYS:
            out.append((WARN, f"预测链: {days:.0f} 天无新增预测（{cnt} 行）"))
        else:
            out.append((OK, f"预测链: {cnt} 行，{days:.0f} 天无新增（正常窗口）"))
    return out


# P1-B (2026-08-15, 审查 GED 静默退化): GED 过期已通知标记（首次 WARN 推一次，后续 INFO 不刷屏）
GED_NOTIFY_STATE = os.path.join(DATA_DIR, ".probe_ged_notified")


def check_ged_stale() -> list:
    """GED v26.1 数据陈旧监控（P1-B, 2026-08-15）：GED 冻结在 2024-12，超
    _GED_STALE_MONTHS=18 个月窗口后 GRV 的 GED 权重退化为 0（russia_europe /
    middle_east_energy 补强失效）——此前该退化静默无人察觉（08-04 接入即超窗）。
    首次超窗 WARN 推送一次 + 落标记；后续同状态 INFO 不重复告警（防噪音）；
    GED 数据更新后自动恢复并清标记。"""
    from datetime import datetime as _dt
    import csv as _csv
    out = []
    path = os.path.join(DATA_DIR, "ged", "ged_agg_country_month.csv")
    if not os.path.exists(path):
        # 实测（2026-08-15）：GED CSV 从未部署到运行数据目录（git 树也只有 etl 脚本无数据），
        # GRV 的 GED 补强从未生效。首次 WARN 推送一次 + 落标记，后续 INFO 不刷屏；
        # 是否补 GED 数据是 P2 数据决策（审计方 Q4：刷数据/调窗 → P2 门控）。
        if os.path.exists(GED_NOTIFY_STATE):
            out.append((INFO, "GED: 数据文件未部署（已通知过，不重复告警；补数据= P2 决策）"))
        else:
            try:
                with open(GED_NOTIFY_STATE, "w", encoding="utf-8") as f:
                    f.write("missing")
            except Exception:
                pass
            out.append((WARN, "GED: 数据文件不存在（russia_europe/middle_east_energy GED 补强从未生效）"))
        return out
    try:
        latest = None
        with open(path, encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                ym = (row.get("year_month") or "").strip()
                if ym:
                    latest = ym
        if not latest:
            out.append((WARN, "GED: CSV 无 year_month 数据行"))
            return out
        y, m = int(latest[:4]), int(latest[5:7])
        now = _dt.now()
        months_stale = (now.year - y) * 12 + (now.month - m)
        if months_stale > 18:
            if os.path.exists(GED_NOTIFY_STATE):
                out.append((INFO, f"GED: 数据仍过期 {months_stale} 个月（已通知过，不重复告警）"))
            else:
                try:
                    with open(GED_NOTIFY_STATE, "w", encoding="utf-8") as f:
                        f.write(latest)
                except Exception:
                    pass
                out.append((WARN, f"GED: 数据冻结在 {latest}（{months_stale} 个月）超 18 个月窗，GRV GED 权重已退化 0"))
        else:
            if os.path.exists(GED_NOTIFY_STATE):
                try:
                    os.remove(GED_NOTIFY_STATE)
                except Exception:
                    pass
            out.append((OK, f"GED: 最新 {latest}（{months_stale} 个月前，窗内）"))
    except Exception as e:
        out.append((WARN, f"GED: 读取异常 {e}"))
    return out


def check_fred_lag() -> list:
    """FRED 关键序列最新数据日期滞后监控（源断更/停更时告警）。"""
    from datetime import datetime, date as _date
    out = []
    today = _date.today()
    for rel, name, max_lag in FRED_LAG_WATCH:
        path = os.path.join(DATA_DIR, rel)
        if not os.path.exists(path):
            out.append((CRIT, f"fred {name}: 文件不存在 {rel}"))
            continue
        try:
            last = None
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("date"):
                        continue
                    try:
                        last = datetime.strptime(line.split(",")[0], "%Y-%m-%d").date()
                    except ValueError:
                        continue
            if last is None:
                out.append((CRIT, f"fred {name}: CSV 无有效数据行"))
                continue
            lag = (today - last).days
            if lag > max_lag * 2:
                out.append((CRIT, f"fred {name}: 数据停在 {last}，滞后 {lag} 天"
                                  f"（CRIT 阈值 {max_lag * 2}）"))
            elif lag > max_lag:
                out.append((WARN, f"fred {name}: 数据停在 {last}，滞后 {lag} 天"
                                  f"（WARN 阈值 {max_lag}）"))
            else:
                out.append((OK, f"fred {name}: 最新 {last}，滞后 {lag} 天（阈值 {max_lag}）"))
        except Exception as e:
            out.append((WARN, f"fred {name}: 读取异常 {e}"))
    return out


def run_probe(alert: bool = True) -> tuple:
    """执行全部检查。返回 (worst_level, results)。"""
    results = []
    for fn in (check_dualwrite, check_artifacts, check_backup, check_fred_lag, check_news_risk, check_sqlite_gone, check_feed_fresh, check_predictions_chain, check_ged_stale):
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
