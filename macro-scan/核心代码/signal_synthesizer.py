"""
signal_synthesizer.py — 弱信号共振检测器（v1.0）

Staging 阶段（STAGING_MODE=True）：只做共振检测+日志，不调LLM，不推ntfy。
Live 阶段：数据积累 >= 30天后，手动将 STAGING_MODE 改为 False。

架构：
  1. 读取 synthesis_rules.yaml 中所有 enabled=true 的规则
  2. 对每条规则：
     a. _check_resonance()      — 查 news.db signal_episodes，确认多类别共振
     b. _check_gdelt_condition() — 查 gdelt_scores.json，确认地缘维度超阈值（可选）
  3. 两个条件均满足 → 触发：Staging 模式只记录日志；Live 模式调 hypothesis + ntfy
  4. cooldown 机制：synthesis_log（news.db）冷却，llm_success=1 AND ntfy_success=1 才计入

调用时机：由 scan_weak_signals.run_scan() 在所有扫描完成后通过 subprocess.Popen 调用。
可用环境变量：
  STAGING_MODE=0   强制切换为 Live 模式（否则由代码内 STAGING_MODE 常量控制）
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

try:
    import yaml
except ImportError:
    raise ImportError("请先安装: pip install pyyaml")

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    _ws = os.environ.get("OPENCLAW_WORKSPACE",
                         os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR  = os.path.join(_ws, "data")
    WORKSPACE = _ws

# ── 模式控制 ──────────────────────────────────────────────────────────────────
# 改为 False 开启真实推演（需数据积累 >= 30 天）
STAGING_MODE = os.environ.get("STAGING_MODE", "1") != "0"

RULES_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synthesis_rules.yaml")
DB_PATH      = os.path.join(DATA_DIR, "news.db")
GRV_PATH     = os.path.join(DATA_DIR, "grv_latest.json")
GDELT_PATH   = os.path.join(DATA_DIR, "gdelt_scores.json")


# ── 连接工具 ──────────────────────────────────────────────────────────────────
def _conn(db_path: str) -> sqlite3.Connection:
    c = sqlite3.connect(db_path, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")
    c.row_factory = sqlite3.Row
    return c


# ── 规则加载（热加载） ────────────────────────────────────────────────────────
def _load_rules() -> tuple[list, dict]:
    if not os.path.exists(RULES_PATH):
        print(f"  [synthesizer] 规则文件不存在: {RULES_PATH}")
        return [], {}
    try:
        with open(RULES_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("rules", []), data.get("global_config", {})
    except Exception as e:
        print(f"  [synthesizer] 规则文件解析失败: {e}")
        return [], {}


# ── 数据成熟度守门 ────────────────────────────────────────────────────────────
def _check_data_maturity(db_path: str, required_days: int = 30) -> tuple[bool, int]:
    try:
        c = _conn(db_path)
        row = c.execute(
            "SELECT julianday('now') - julianday(MIN(triggered_at)) FROM signal_episodes"
        ).fetchone()
        c.close()
        if not row or row[0] is None:
            return False, 0
        age = int(row[0])
        return age >= required_days, age
    except Exception:
        return False, 0


# ── 共振检测 ──────────────────────────────────────────────────────────────────
def _check_resonance(rule: dict, db_path: str) -> tuple[bool, dict]:
    """
    查 news.db signal_episodes，检测多类别共振。
    返回 (triggered: bool, context: dict)
    """
    trigger    = rule.get("trigger", {})
    window     = trigger.get("window_days", 7)
    categories = trigger.get("categories", [])
    min_cats   = trigger.get("min_categories", len(categories))
    min_cnt    = trigger.get("min_scan_count", 1)
    min_ratio  = trigger.get("min_avg_ratio", 1.5)

    if not categories or not os.path.exists(db_path):
        return False, {}

    since = (datetime.now(timezone.utc) - timedelta(days=window)).isoformat()[:19]
    try:
        import pg_read as _pg
        c = _pg.connect()
        if c is None:
            return False, {}
        ph = ",".join(["%s"] * len(categories))
        rows = c.execute(f"""
            SELECT category,
                   COUNT(DISTINCT scan_ctx_id) AS scan_cnt,
                   COUNT(*)                    AS total_cnt,
                   AVG(ratio)                  AS avg_ratio,
                   MAX(ratio)                  AS max_ratio
            FROM news.signal_episodes
            WHERE category IN ({ph})
              AND triggered_at >= %s
              AND scan_ctx_id IS NOT NULL
            GROUP BY category
            HAVING COUNT(DISTINCT scan_ctx_id) >= %s
               AND AVG(ratio) >= %s
        """, (*categories, since, min_cnt, min_ratio)).fetchall()
        c.close()
    except Exception as e:
        print(f"  [synthesizer] news.db 查询失败: {e}")
        return False, {}

    triggered = [dict(r) for r in rows]
    if len(triggered) < min_cats:
        return False, {}

    # 取代表性标题
    titles = []
    try:
        import pg_read as _pg
        c = _pg.connect()
        if c is None:
            return False, {}
        for cat_row in triggered[:2]:
            cat = cat_row["category"]
            t_rows = c.execute("""
                SELECT a.title FROM news.articles a
                JOIN news.article_categories ac ON a.id = ac.article_id
                WHERE ac.category = %s
                  AND a.ingested_at >= %s
                GROUP BY a.title ORDER BY MAX(a.ingested_at) DESC LIMIT 2
            """, (cat, since)).fetchall()
            titles.extend(r[0] for r in t_rows if r[0])
        c.close()
    except Exception:
        pass

    avg_ratio = sum(r["avg_ratio"] for r in triggered) / len(triggered)
    ctx = {
        "triggered_categories": [r["category"] for r in triggered],
        "scan_count":  sum(r["scan_cnt"] for r in triggered),
        "avg_ratio":   round(avg_ratio, 1),
        "max_ratio":   max(r["max_ratio"] for r in triggered),
        "trigger_titles": titles[:3],
        "window_days": window,
    }
    return True, ctx


# ── GDELT 二次验证 ────────────────────────────────────────────────────────────
def _check_gdelt_condition(rule: dict) -> bool:
    """
    读 gdelt_scores.json，检查指定维度任意国家分数 >= 阈值。
    规则无 gdelt_dimension 字段 → 直接返回 True。
    """
    dimension = rule.get("gdelt_dimension")
    threshold = rule.get("gdelt_threshold", 0)
    if not dimension:
        return True

    if not os.path.exists(GDELT_PATH):
        print(f"  [synthesizer] gdelt_scores.json 不存在，跳过 GDELT 门槛")
        return False

    try:
        import time as _t
        age_days = (_t.time() - os.path.getmtime(GDELT_PATH)) / 86400
        if age_days > 7:
            print(f"  [synthesizer] gdelt_scores.json 已 {age_days:.0f} 天未更新，跳过 GDELT 门槛")
            return False

        with open(GDELT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        country_scores = data.get("scores", {}).get(dimension, {})
        if not country_scores:
            print(f"  [synthesizer] GDELT 维度 '{dimension}' 为空，等待数据积累")
            return False

        max_score = max(country_scores.values())
        if max_score >= threshold:
            top = max(country_scores, key=country_scores.get)
            print(f"  [synthesizer] GDELT '{dimension}' 满足：{top}={max_score:.0f} >= {threshold}")
            return True
        return False
    except Exception as e:
        print(f"  [synthesizer] GDELT 检查失败: {e}")
        return False


# ── 冷却检查 ──────────────────────────────────────────────────────────────────
def _is_in_cooldown(rule_id: str, cooldown_days: int, db_path: str) -> bool:
    """仅 llm_success=1 AND ntfy_success=1 的记录计入正常冷却。
    suppress_reason='user_silence' 的记录单独检查。"""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).isoformat()[:19]
        import pg_read as _pg
        c = _pg.connect()
        if c is None:
            return False
        # 正常推演冷却
        row = c.execute("""
            SELECT 1 FROM news.synthesis_log
            WHERE rule_id = %s AND triggered_at >= %s
              AND llm_success = 1 AND ntfy_success = 1
              AND (suppress_reason IS NULL OR suppress_reason = '')
            LIMIT 1
        """, (rule_id, cutoff)).fetchone()
        if row:
            c.close()
            return True
        # 用户静默：从 trigger_summary JSON 读 silence_days，按实际天数计算截止时间
        row2 = c.execute("""
            SELECT triggered_at, trigger_summary FROM news.synthesis_log
            WHERE rule_id = %s AND suppress_reason = 'user_silence'
            ORDER BY triggered_at DESC LIMIT 1
        """, (rule_id,)).fetchone()
        c.close()
        if row2:
            import json as _j
            silence_days = cooldown_days  # 默认回退
            try:
                summary = _j.loads(row2[1] or "{}")
                silence_days = int(summary.get("silence_days", cooldown_days))
            except Exception:
                pass
            silence_cutoff = (datetime.now(timezone.utc)
                              - timedelta(days=silence_days)).isoformat()[:19]
            return row2[0] >= silence_cutoff
        return False
    except Exception:
        return False


# ── 触发记录 ──────────────────────────────────────────────────────────────────
def _write_log(db_path: str, rule_id: str, scan_ctx_id,
               ctx: dict, hypothesis: str = "",
               llm_success: int = 0, ntfy_success: int = 0,
               suppress_reason: str = "") -> int:
    now = datetime.now(timezone.utc).isoformat()[:19]
    summary = json.dumps(ctx, ensure_ascii=False)
    c = _conn(db_path)
    with c:
        cur = c.execute("""
            INSERT INTO synthesis_log
            (rule_id, triggered_at, scan_ctx_id, trigger_summary,
             hypothesis_text, llm_success, ntfy_success, suppress_reason)
            VALUES (?,?,?,?,?,?,?,?)
        """, (rule_id, now, scan_ctx_id, summary,
              hypothesis, llm_success, ntfy_success, suppress_reason))
        log_id = cur.lastrowid
    c.close()
    return log_id


# ── 情景文本渲染 ──────────────────────────────────────────────────────────────
def _render_hypothesis(rule: dict, ctx: dict) -> str:
    template = rule.get("hypothesis_template", "")
    grv = {}
    try:
        with open(GRV_PATH, encoding="utf-8") as f:
            grv = json.load(f)
    except Exception:
        pass
    grv_taiwan   = grv.get("taiwan_strait", "N/A")
    grv_us_china = grv.get("us_china_strategic", "N/A")
    titles_str   = "；".join(ctx.get("trigger_titles", [])) or "（无）"
    cat_names    = "、".join(ctx.get("triggered_categories", []))
    return (template
            .replace("{category_names}",  cat_names)
            .replace("{window_days}",     str(ctx.get("window_days", "?")))
            .replace("{scan_count}",      str(ctx.get("scan_count", "?")))
            .replace("{trigger_titles}",  titles_str)
            .replace("{grv_taiwan}",      str(grv_taiwan))
            .replace("{grv_us_china}",    str(grv_us_china))
            .replace("{avg_ratio}",       str(ctx.get("avg_ratio", "?")))
            .strip())


# ── 每日上限检查 ──────────────────────────────────────────────────────────────
def _get_today_synthesis_count(db_path: str) -> int:
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        import pg_read as _pg
        c = _pg.connect()
        if c is None:
            return 0
        row = c.execute(
            "SELECT COUNT(*) FROM news.synthesis_log WHERE triggered_at >= %s AND ntfy_success = 1",
            (today + "T00:00:00",)
        ).fetchone()
        c.close()
        return row[0] if row else 0
    except Exception:
        return 0


# ── Phase 1D：跨资产相关性突变检测（R08）────────────────────────────────────
def _check_asset_correlation_shift(db_path: str = DB_PATH) -> dict:
    """
    检测"平时低相关的指标对"是否突然同向变化。
    使用 fred_history CSV，计算30日 vs 90日滚动相关系数差值。
    返回 {"triggered": bool, "shifts": list[dict]}
    """
    import csv as _csv
    _fred_dir = os.path.join(DATA_DIR, "fred_history")
    _PAIRS = [
        ("VIXCLS",       "DGS10",       "恐慌+长债同升（避险共振）"),
        ("DCOILWTICO",   "VIXCLS",      "油价+恐慌同升（供给危机）"),
        ("BAA10Y",       "T10Y2Y",      "信用利差+曲线倒挂（银行系统压力）"),
        ("DTWEXBGS",     "BAA10Y",      "美元升+信用压力（新兴市场资金外流）"),
    ]
    DELTA_THRESHOLD = 0.40  # 相关系数变化超过此值视为突变

    def _load_series(sid: str) -> list:
        """返回 [(date_str, float), ...] 按日期升序排列。"""
        path = os.path.join(_fred_dir, f"{sid}.csv")
        if not os.path.exists(path):
            # 尝试备用名
            path = os.path.join(_fred_dir, f"{sid.lower()}.csv")
        if not os.path.exists(path):
            return []
        try:
            rows = []
            with open(path, newline="", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    try:
                        v = float(row["value"])
                        rows.append((row["date"], v))
                    except (ValueError, KeyError):
                        pass
            rows.sort(key=lambda x: x[0])
            return rows
        except Exception:
            return []

    def _rolling_corr(a: list, b: list, window: int) -> float | None:
        """计算两个等长列表的相关系数（简单皮尔逊）。"""
        if len(a) < window or len(b) < window:
            return None
        xa, xb = a[-window:], b[-window:]
        n = window
        mean_a = sum(xa) / n
        mean_b = sum(xb) / n
        num = sum((xa[i] - mean_a) * (xb[i] - mean_b) for i in range(n))
        den_a = (sum((x - mean_a) ** 2 for x in xa)) ** 0.5
        den_b = (sum((x - mean_b) ** 2 for x in xb)) ** 0.5
        if den_a < 1e-9 or den_b < 1e-9:
            return None
        return num / (den_a * den_b)

    def _align_series(s1: list, s2: list, n: int) -> tuple[list, list]:
        """取两个序列共同最近 n 个交叉日期的值。"""
        d1 = {d: v for d, v in s1}
        d2 = {d: v for d, v in s2}
        common = sorted(set(d1) & set(d2), reverse=True)[:n * 2]
        common = sorted(common)[-n:]
        if len(common) < n:
            return [], []
        return [d1[d] for d in common], [d2[d] for d in common]

    shifts = []
    for sid_a, sid_b, label in _PAIRS:
        try:
            sa = _load_series(sid_a)
            sb = _load_series(sid_b)
            if not sa or not sb:
                continue
            vals_a_90, vals_b_90 = _align_series(sa, sb, 90)
            vals_a_30, vals_b_30 = vals_a_90[-30:], vals_b_90[-30:]
            corr_90 = _rolling_corr(vals_a_90, vals_b_90, 90)
            corr_30 = _rolling_corr(vals_a_30, vals_b_30, 30)
            if corr_90 is None or corr_30 is None:
                continue
            delta = abs(corr_30 - corr_90)
            if delta >= DELTA_THRESHOLD:
                shifts.append({
                    "pair": f"{sid_a}/{sid_b}",
                    "label": label,
                    "corr_30d": round(corr_30, 3),
                    "corr_90d": round(corr_90, 3),
                    "delta": round(delta, 3),
                })
                print(f"  [R08] 相关性突变：{label} "
                      f"corr_90={corr_90:.2f} → corr_30={corr_30:.2f} (Δ={delta:.2f})")
        except Exception as _e:
            print(f"  [R08] {sid_a}/{sid_b} 计算失败（非阻断）: {_e}")

    return {"triggered": len(shifts) > 0, "shifts": shifts}


# ── 主入口 ────────────────────────────────────────────────────────────────────
def evaluate_rules(rules_path: str = RULES_PATH,
                   db_path: str = DB_PATH,
                   scan_ctx_id=None,
                   force_rule: str = None) -> list[dict]:
    """
    遍历规则，检测共振并（在 Live 模式下）触发推演。
    force_rule: 强制触发指定 rule_id（跳过冷却），用于手动指令。
    返回触发的规则列表。
    """
    rules, gcfg = _load_rules()
    if not rules:
        return []

    daily_limit   = gcfg.get("daily_llm_limit", 2)
    min_data_days = gcfg.get("min_data_days", 30)

    # 数据成熟度守门（非强制触发时）
    if not force_rule:
        mature, age_days = _check_data_maturity(db_path, min_data_days)
        if not mature:
            print(f"  [synthesizer] 基线不足（{age_days}天，需{min_data_days}天），仅输出诊断")
            if not STAGING_MODE:
                return []

    triggered_rules = []

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        rule_id   = rule.get("rule_id", "unknown")
        rule_name = rule.get("name", rule_id)
        cooldown  = rule.get("cooldown_days", 7)

        # 强制触发模式：只处理指定规则
        if force_rule and rule_id != force_rule:
            continue

        # 冷却检查（强制触发时跳过）
        if not force_rule and _is_in_cooldown(rule_id, cooldown, db_path):
            print(f"  [synthesizer] {rule_id} 冷却中，跳过")
            continue

        # 共振检测
        resonance_ok, ctx = _check_resonance(rule, db_path)
        status = "触发" if resonance_ok else "未触发"
        print(f"  [synthesizer-{'staging' if STAGING_MODE else 'live'}] "
              f"{rule_id}: {status} | "
              f"categories={ctx.get('triggered_categories',[])} "
              f"avg_ratio={ctx.get('avg_ratio','N/A')}")

        if not resonance_ok and not force_rule:
            continue

        # 代表标题
        if resonance_ok:
            titles = ctx.get("trigger_titles", [])
            if titles:
                print(f"    代表标题: {titles[0][:60]}")

        if STAGING_MODE:
            # Staging：只记录，不调 LLM，不检查 GDELT 门槛（保留完整观测样本）
            _write_log(db_path, rule_id, scan_ctx_id, ctx,
                       suppress_reason="staging")
            print(f"  [synthesizer-staging] ★ {rule_name} — 已记录（Staging模式，未调LLM）")
            triggered_rules.append({"rule_id": rule_id, "name": rule_name, "ctx": ctx})
            continue

        # GDELT 二次验证（仅 Live 模式执行）
        gdelt_ok = _check_gdelt_condition(rule)
        if not gdelt_ok and not force_rule:
            print(f"  [synthesizer] {rule_id} GDELT 门槛未达，跳过")
            continue

        # ── Live 模式 ──────────────────────────────────────────────────────
        if _get_today_synthesis_count(db_path) >= daily_limit:
            print(f"  [synthesizer] 今日已达推送上限({daily_limit}条)，跳过 {rule_id}")
            _write_log(db_path, rule_id, scan_ctx_id, ctx,
                       suppress_reason="daily_limit")
            continue

        hypothesis = _render_hypothesis(rule, ctx)
        log_id = _write_log(db_path, rule_id, scan_ctx_id, ctx, hypothesis)

        prefix = rule.get("report_prefix", "[自动推演]")
        print(f"  [synthesizer] ★ 触发规则：{rule_name}")
        print(f"    Hypothesis（前120字）：{hypothesis[:120]}…")

        llm_ok = ntfy_ok = 0
        try:
            from hypothesis_engine import run_hypothesis_simple
            from ntfy_utils import push_text_with_priority
            run_hypothesis_simple(hypothesis)
            llm_ok = 1
            push_text_with_priority(
                f"{prefix} {rule_name}",
                f"触发强度：avg_ratio={ctx['avg_ratio']}x\n"
                f"代表信号：{'；'.join(ctx.get('trigger_titles',[]))[:200]}",
                priority=2,
            )
            ntfy_ok = 1
        except Exception as e:
            print(f"  [synthesizer] LLM/推送失败: {e}")

        # 更新日志
        try:
            c = _conn(db_path)
            with c:
                c.execute(
                    "UPDATE synthesis_log SET llm_success=?, ntfy_success=? WHERE id=?",
                    (llm_ok, ntfy_ok, log_id)
                )
            c.close()
        except Exception:
            pass

        triggered_rules.append({
            "rule_id": rule_id, "name": rule_name,
            "hypothesis": hypothesis, "ctx": ctx,
        })

    # ── R08：跨资产相关性突变检测（独立于规则体系，always-on）─────────────────
    try:
        r08 = _check_asset_correlation_shift(db_path)
        if r08["triggered"]:
            shifts = r08["shifts"]
            desc = "；".join(f"{s['label']}(Δ={s['delta']})" for s in shifts)
            print(f"  [synthesizer-R08] ★ 跨资产相关性突变：{desc}")
            r08_ctx = {"trigger_titles": [s["label"] for s in shifts],
                       "avg_ratio": max(s["delta"] for s in shifts)}
            if STAGING_MODE:
                _write_log(db_path, "R08", scan_ctx_id, r08_ctx,
                           suppress_reason="staging")
                print(f"  [synthesizer-R08-staging] 已记录至 synthesis_log，未推演")
            else:
                _write_log(db_path, "R08", scan_ctx_id, r08_ctx)
                try:
                    from ntfy_utils import push_text_with_priority
                    push_text_with_priority(
                        "[信号🟡] 跨资产相关性突变",
                        desc + "\n（相关性结构性变化，请结合其他信号判断）",
                        priority=2,
                    )
                except Exception as _pe:
                    print(f"  [R08] 推送失败: {_pe}")
            triggered_rules.append({
                "rule_id": "R08",
                "name": "跨资产相关性突变",
                "shifts": shifts,
            })
    except Exception as _r08e:
        print(f"  [synthesizer-R08] 检测失败（非阻断）: {_r08e}")

    return triggered_rules


def main():
    parser = argparse.ArgumentParser(description="弱信号共振检测器")
    parser.add_argument("--scan-ctx-id", type=int, default=None, help="当前扫描的 scan_ctx_id")
    parser.add_argument("--force-rule",  type=str, default=None, help="强制触发指定规则（跳过冷却）")
    parser.add_argument("--db-path",     type=str, default=DB_PATH)
    args = parser.parse_args()

    mode = "staging" if STAGING_MODE else "live"
    print(f"[signal_synthesizer] 启动（模式={mode}）")
    results = evaluate_rules(
        db_path=args.db_path,
        scan_ctx_id=args.scan_ctx_id,
        force_rule=args.force_rule,
    )
    print(f"[signal_synthesizer] 完成，触发规则 {len(results)} 条")


if __name__ == "__main__":
    main()
