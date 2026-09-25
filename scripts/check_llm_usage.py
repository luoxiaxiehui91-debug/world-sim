#!/usr/bin/env python3
"""LLM token 用量飙升巡检（CHG-20260926T001031）。

规则：今日（北京时间）total_tokens > 前 BASELINE_DAYS 日同口径日均 × THRESHOLD → 告警。
数据源：视图 `public.llm_token_usage_daily`（日界已按 Asia/Shanghai 归一）。
冷却：同一自然日只推一次（状态文件 `llm_usage_alert.json`）。

用法（在容器内，PG 凭据与主机名现成）：
    docker exec macro-scan-macro-scan-1 python3 <scripts>/check_llm_usage.py
    docker exec ... python3 <scripts>/check_llm_usage.py --heartbeat   # 无论是否超阈值都推摘要

退出码：超阈值=1，正常=0，PG 不可用=1。
依赖 env：NTFY_TOPIC / NTFY_BASE_URL（ntfy_utils）、WORLDSIM_APP_PW（pg_read）。
可调：LLM_USAGE_BASELINE_DAYS（默认 7）、LLM_USAGE_SPIKE_THRESHOLD（默认 2.0）。
"""
import datetime
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in ("/app", os.path.join(_HERE, "..", "macro-scan", "核心代码")):
    if os.path.isdir(_cand):
        sys.path.insert(0, _cand)

DATA_DIR = os.environ.get("MACRO_SCAN_DATA_DIR", "/workspace/data")
STATE_FILE = os.path.join(DATA_DIR, "llm_usage_alert.json")
BASELINE_DAYS = int(os.environ.get("LLM_USAGE_BASELINE_DAYS", "7"))
THRESHOLD = float(os.environ.get("LLM_USAGE_SPIKE_THRESHOLD", "2.0"))
CST = datetime.timezone(datetime.timedelta(hours=8))


def _rows(conn, sql, params=()):
    cur = conn.execute(sql, params)
    cols = [c.name for c in cur.description] if cur.description else []
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _alerted_today(today):
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, encoding="utf-8") as f:
                if json.load(f).get("last_alert_date") == today:
                    return True
    except Exception:
        pass
    return False


def _mark_alerted(today):
    try:
        os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_alert_date": today}, f)
    except Exception as e:
        print(f"[check_llm_usage] 状态文件写入失败: {e}")


def _push(title, msg):
    """发起 ntfy 推送。

    ⚠️ ntfy_utils.push_text 内部 `except Exception: logging.warning` **吞掉异常且无返回值**，
    调用方因此**无法判断**是否真的送达（topic 为空时更是静默 return）。
    故日志只能写「已发起」，绝不能写「已推送」——后者会给出假的送达确认。
    """
    try:
        if not os.environ.get("NTFY_TOPIC"):
            print("[check_llm_usage] NTFY_TOPIC 未配置，跳过推送（仅本地判定）")
            return
        from ntfy_utils import push_text
        push_text(title, msg)
        print(f"[check_llm_usage] ntfy 推送已发起：{title}（送达与否以实际收到为准）")
    except Exception as e:
        print(f"[check_llm_usage] ntfy 推送异常（不影响判定）: {type(e).__name__}: {str(e)[:120]}")


def main():
    heartbeat = "--heartbeat" in sys.argv
    today = datetime.datetime.now(CST).date()

    try:
        from pg_read import connect
        conn = connect()
    except Exception as e:
        print(f"[check_llm_usage] pg_read 不可用: {type(e).__name__}: {str(e)[:120]}")
        return 1
    if conn is None:
        print("[check_llm_usage] PG 连接失败")
        return 1

    try:
        rows = _rows(conn,
                     "SELECT d, SUM(calls) AS calls, SUM(total_tokens) AS tok,"
                     " SUM(failures) AS failures FROM public.llm_token_usage_daily"
                     " WHERE d BETWEEN (%s::date - %s) AND %s::date"
                     " GROUP BY d ORDER BY d",
                     (today, BASELINE_DAYS, today))
        by_usage = _rows(conn,
                         "SELECT usage_id, SUM(total_tokens) AS tok"
                         " FROM public.llm_token_usage_daily WHERE d = %s::date"
                         " GROUP BY 1 ORDER BY 2 DESC", (today,))
    finally:
        try:
            conn.close()
        except Exception:
            pass

    t = str(today)
    today_row = next((r for r in rows if str(r.get("d")) == t), None)
    today_tok = int((today_row or {}).get("tok") or 0)
    today_calls = int((today_row or {}).get("calls") or 0)
    today_fail = int((today_row or {}).get("failures") or 0)

    hist = [int(r.get("tok") or 0) for r in rows if str(r.get("d")) != t]
    baseline = (sum(hist) / len(hist)) if hist else 0
    top = ", ".join(f"{r.get('usage_id')}={int(r.get('tok') or 0)}" for r in by_usage[:3]) or "无"

    if heartbeat:
        _push("LLM 用量心跳",
              f"{t} 调用 {today_calls} 次 / {today_tok} tokens"
              f"（基线 {baseline:.0f}）；Top: {top}")
        return 0

    if baseline > 0 and today_tok > baseline * THRESHOLD:
        ratio = today_tok / baseline
        msg = (f"{t} token 用量飙升：{today_tok}（基线 {baseline:.0f}，"
               f"{ratio:.2f}×，阈值 {THRESHOLD}×）\n"
               f"调用 {today_calls} 次，失败 {today_fail} 次\nTop: {top}")
        if not _alerted_today(t):
            _push("LLM token 用量飙升", msg)
            _mark_alerted(t)
        else:
            print("[check_llm_usage] 今日已告警，冷却中（不重复推送）")
        print("[check_llm_usage] " + msg.replace("\n", " | "))
        return 1

    print(f"[check_llm_usage] 正常：{t} {today_tok} tokens（基线 {baseline:.0f}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
