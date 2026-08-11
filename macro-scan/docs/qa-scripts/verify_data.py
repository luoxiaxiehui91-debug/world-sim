#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_data.py — 开阳 M-1 news_geo 事件图层 · 数据层验收脚本

对应验收文档：arg-map-qa-2026-08-11.md（§1 AC-M1-01~12 / §5 AC-R-01~04 / §6 门禁 G-M1~M5）
输入：/vol2/1000/software/macro-scan/data/news_geo.json（可 --data-dir 覆盖）

用法（NAS 侧，ssh nas 后直接跑；或 ssh nas 'python3 docs/qa-scripts/verify_data.py ...'）：
    python3 verify_data.py                  # 默认模式：AC-M1-01~12 + AC-R-04 + G-M4（event_type 域校验）
    python3 verify_data.py --enforce-unknown   # 部署满 48h 后：强制 event_type unknown 占比 < 5%（lead 裁决）
    python3 verify_data.py --snapshot       # 记录当日 N/updated 到历史文件 qa-history.json（G-M1/G-M2 连续 3 天观测）
    python3 verify_data.py --gate           # 门禁模式：G-M1/G-M2/G-M4/G-M5 汇总判定（配合 --snapshot 累积）
    python3 verify_data.py --bench-jsonl    # 基准：测 news_geo.jsonl 全扫耗时（AC-R-01 参考，判定 <=60s）
    python3 verify_data.py --baseline       # 基线重采：打印并落盘 qa-baseline-<date>.json（部署后先跑）
    python3 verify_data.py --data-dir DIR   # 覆盖 data 目录（默认 /vol2/1000/software/macro-scan/data）
    python3 verify_data.py --window-hours N # 时间窗小时数（默认 168=7d；arch 定稿 24h 窗时传 24）
    python3 verify_data.py --max-age-hours N# updated 新鲜度阈值（默认 36h 覆盖日频；I15 调度传 1）

退出码：全 PASS = 0；任一 FAIL 或门禁未决 = 1。
输出：逐项 [AC-xx] PASS/FAIL/WARN + 末尾 PASS/FAIL 汇总表。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import datetime
import statistics

# ── 常量 ────────────────────────────────────────────────────────────────
DEFAULT_DATA_DIR = "/vol2/1000/software/macro-scan/data"
REQUIRED_FIELDS = {"id", "lat", "lng", "event_type", "intensity", "country"}
EVENT_TYPE_DOMAIN = {"conflict", "protest", "disaster", "political", "unknown"}
FOUR_ENUM = {"conflict", "protest", "disaster", "political"}
N_MIN, N_MAX = 100, 2000                     # AC-M1-01
INTENSITY_MAX, INTENSITY_P90 = 60, 40        # AC-M1-04
COUNTRY_MISS_RATE_MAX = 0.01                 # AC-M1-06
UNKNOWN_RATE_MAX = 0.05                      # AC-M1-05 --enforce-unknown
PARSE_BUDGET_S = 60.0                        # AC-R-01
GATE_DAYS = 3                                # G-M1 连续天数
GATE_DAILY_DRIFT = 0.50                      # G-M2 日波动 ±50%

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(HERE, "qa-history.json")


# ── 工具 ─────────────────────────────────────────────────────────────────
def now_dt():
    return datetime.datetime.now().astimezone()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def secs_to_ts(s):
    return datetime.datetime.fromtimestamp(s).astimezone().strftime("%Y-%m-%d %H:%M:%S%z")


class Verdict:
    """逐项判定记录。PASS/FAIL 硬判定；WARN 仅供参考不改变退出码。"""

    def __init__(self):
        self.rows = []

    def add(self, code, ok, msg, hard=True):
        self.rows.append((code, "PASS" if ok else ("FAIL" if hard else "WARN"), msg))
        return ok

    def failed(self):
        return [r for r in self.rows if r[1] == "FAIL"]

    def summary(self):
        n_pass = sum(1 for r in self.rows if r[1] == "PASS")
        n_fail = len(self.failed())
        n_warn = sum(1 for r in self.rows if r[1] == "WARN")
        return n_pass, n_fail, n_warn


# ── 数据加载 ─────────────────────────────────────────────────────────────
def load_data(data_dir):
    news_geo_path = os.path.join(data_dir, "news_geo.json")
    d = load_json(news_geo_path)
    events = d.get("events", [])
    return news_geo_path, d, events


# ── 各项验收 ─────────────────────────────────────────────────────────────
def run_checks(args, v: Verdict):
    data_dir = args.data_dir
    news_geo_path, d, events = load_data(data_dir)
    N = len(events)

    # ── AC-M1-01 非空与总体结构 ──
    ok_struct = isinstance(d, dict) and all(k in d for k in ("schema_version", "updated", "events"))
    ok_n = N_MIN <= N <= N_MAX
    v.add("AC-M1-01", ok_struct and ok_n,
          f"顶层结构={ok_struct} events={N}（须 {N_MIN}≤N≤{N_MAX}）")

    if not events:
        v.add("AC-M1-02", False, "events 为空，后续字段断言跳过", hard=False)
        return v

    # ── AC-M1-02 必填字段 ──
    missing = [e["id"] for e in events if not REQUIRED_FIELDS.issubset(e)]
    v.add("AC-M1-02", not missing, f"缺必填字段事件数={len(missing)}（须为 0）")

    # ── AC-M1-03 坐标范围 + ≤4 位小数 ──
    bad_coord = [e["id"] for e in events
                 if not (-90 <= e["lat"] <= 90 and -180 <= e["lng"] <= 180
                         and math.isfinite(e["lat"]) and math.isfinite(e["lng"]))]
    bad_dec = [e["id"] for e in events
               if abs(e["lat"] * 1e4 - round(e["lat"] * 1e4)) > 1e-6
               or abs(e["lng"] * 1e4 - round(e["lng"] * 1e4)) > 1e-6]
    v.add("AC-M1-03", not bad_coord and not bad_dec,
          f"越界={len(bad_coord)} 超4位小数={len(bad_dec)}（均须为 0）")

    # ── AC-M1-04 intensity 0-100 归一分布 ──
    inten = sorted(e["intensity"] for e in events)
    i_min, i_max = inten[0], inten[-1]
    i_p50, i_p90, i_p99 = (inten[int(len(inten) * 0.5)], inten[int(len(inten) * 0.9)],
                           inten[min(int(len(inten) * 0.99), len(inten) - 1)])
    ok_i = (i_min >= 0 and i_max <= 100 and i_max >= INTENSITY_MAX and i_p90 >= INTENSITY_P90)
    v.add("AC-M1-04", ok_i,
          f"intensity min={i_min} max={i_max} P50={i_p50} P90={i_p90} P99={i_p99} "
          f"（须 0-100 且 max≥{INTENSITY_MAX} P90≥{INTENSITY_P90}）")

    # ── AC-M1-05 event_type 域 + unknown 占比 ──
    from collections import Counter
    c = Counter(e.get("event_type") for e in events)
    unknown_ratio = c.get("unknown", 0) / N if N else 1.0
    bad_types = set(c) - EVENT_TYPE_DOMAIN
    ok_domain = not bad_types
    if not ok_domain:
        v.add("AC-M1-05", False, f"越枚举类型={sorted(bad_types)}（输出域须⊆五枚举）")
    elif args.enforce_unknown:
        v.add("AC-M1-05", unknown_ratio < UNKNOWN_RATE_MAX,
              f"分布={dict(c)} unknown占比={unknown_ratio*100:.2f}% "
              f"（--enforce-unknown：须 <{UNKNOWN_RATE_MAX*100:.0f}%）")
    else:
        v.add("AC-M1-05", True,
              f"分布={dict(c)} unknown占比={unknown_ratio*100:.2f}% "
              f"（默认模式：仅域校验；部署满48h后请加 --enforce-unknown 复核）")

    # ── AC-M1-06 country 非空率 ──
    miss_c = [e["id"] for e in events if not str(e.get("country") or "").strip()]
    ratio_c = len(miss_c) / N
    v.add("AC-M1-06", ratio_c < COUNTRY_MISS_RATE_MAX,
          f"country 缺失率={ratio_c*100:.2f}%（须 <{COUNTRY_MISS_RATE_MAX*100:.0f}%）")

    # ── AC-M1-07 id 唯一 ──
    ids = [e["id"] for e in events]
    v.add("AC-M1-07", len(set(ids)) == len(ids), f"id 唯一率={len(set(ids))}/{len(ids)}")

    # ── AC-M1-08 schema_version / updated ──
    sv = d.get("schema_version")
    up = d.get("updated", "")
    v.add("AC-M1-08", sv == "1.0" and isinstance(up, str) and "T" in up,
          f"schema_version={sv!r} updated={up!r}（须 1.0 + ISO 带 T）")

    # ── AC-M1-09 updated 新鲜度 ──
    age_h = None
    try:
        up_dt = datetime.datetime.fromisoformat(up) if isinstance(up, str) else None
        age_h = (now_dt() - up_dt).total_seconds() / 3600
    except Exception:
        pass
    ok_fresh = age_h is not None and 0 <= age_h <= args.max_age_hours
    v.add("AC-M1-09", ok_fresh,
          f"updated 距现在={age_h if age_h is not None else 'N/A'}h "
          f"（须 ≤{args.max_age_hours}h；日频36/I15用1）")

    # ── AC-M1-10 时间窗过滤 ──
    win_days = args.window_hours / 24.0
    miss_date = 0
    out_window = []
    up_date = datetime.datetime.fromisoformat(up).date() if isinstance(up, str) else now_dt().date()
    cutoff = up_date - datetime.timedelta(days=win_days)
    for e in events:
        ed = e.get("event_date")
        if not ed:
            miss_date += 1
            continue  # 前端按 updated 兜底，不算窗口外
        ed_s = str(ed)[:8]
        if len(ed_s) == 8 and ed_s.isdigit():
            try:
                if datetime.datetime.strptime(ed_s, "%Y%m%d").date() < cutoff:
                    out_window.append(e["id"])
            except ValueError:
                pass
    v.add("AC-M1-10", not out_window,
          f"窗口外事件={len(out_window)}（须为 0；窗口={win_days:g}d 截止{cutoff}），"
          f"event_date 缺失={miss_date}（按 updated 兜底，参考）")

    # ── AC-M1-11 聚合充分性（参考，不判 FAIL）──
    buckets = set((round(e["lat"], 3), round(e["lng"], 3), e.get("country")) for e in events)
    v.add("AC-M1-11", True,
          f"事件数={N} 去重桶(3位小数)数={len(buckets)}"
          f"（参考：若 N>1000 且桶≈N 提示聚合不充分，不强制）", hard=False)

    # ── AC-R-04 单一写者（events 结构未被 articles 覆写）──
    articles = d.get("articles", [])
    v.add("AC-R-04", N > 0 and len(articles) == 0,
          f"events={N} articles={len(articles)}（须 events 结构非空且无 articles 混入；"
          f"07:15 槽位后采样应保持）")

    return v


# ── AC-M1-12 原子写 + AC-R-03 断供降级（文件系统/日志静态检查）──────────
def run_fs_checks(args, v: Verdict):
    data_dir = args.data_dir
    logs_dir = os.path.join(os.path.dirname(data_dir.rstrip("/")), "logs")

    # AC-M1-12 无 .tmp 残留
    tmp = os.path.join(data_dir, "news_geo.json.tmp")
    v.add("AC-M1-12", not os.path.exists(tmp), f".tmp 残留={os.path.exists(tmp)}（须无残留）")

    # AC-R-03 GDELT 断供降级（条件判定）
    gdelt_log = os.path.join(logs_dir, "gdelt_geo.log")
    feed_log = os.path.join(logs_dir, "news_geo_feed.log")
    recent_fail = 0
    if os.path.exists(gdelt_log):
        try:
            lines = [l for l in open(gdelt_log, encoding="utf-8", errors="replace") if l.strip()]
            recent_fail = sum(1 for l in lines[-80:] if "all_failed" in l or "slots_failed" in l)
        except Exception:
            recent_fail = -1  # 读取异常
    v.add("AC-R-03", True,
          f"最近80行 gdelt_geo.log 失败标记={recent_fail if recent_fail >= 0 else '读取异常'} "
          f"（观察项：若断供且 news_geo.json 仍非空=预期降级；被清空=实现问题，按 AC-M1-01 拦截）",
          hard=False)
    if os.path.exists(feed_log):
        try:
            tail = [l for l in open(feed_log, encoding="utf-8", errors="replace") if l.strip()][-5:]
            v.add("AC-R-03b", True, "news_geo_feed.log 尾部（人工核对写出条数）:\n" + "\n".join(tail),
                  hard=False)
        except Exception:
            pass
    return v


# ── AC-R-01 jsonl 性能基准 ──────────────────────────────────────────────
def bench_jsonl(data_dir):
    path = os.path.join(data_dir, "news_geo.jsonl")
    if not os.path.exists(path):
        return None, None, None
    t0 = time.time()
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    t1 = time.time()
    t0b = time.time()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                json.loads(line)
    t2 = time.time()
    return n, t1 - t0, t2 - t0b


# ── 门禁 G-M1/G-M2/G-M5（基于 qa-history.json 连续观测）──────────────────
def gate_checks(args, v: Verdict):
    data_dir = args.data_dir
    _, d, events = load_data(data_dir)
    N = len(events)
    today = now_dt().date().isoformat()
    hist = []
    if os.path.exists(HISTORY_FILE):
        try:
            hist = load_json(HISTORY_FILE).get("days", [])
        except Exception:
            hist = []

    if args.snapshot or args.gate:
        rec = {"date": today, "N": N, "updated": d.get("updated")}
        hist = [h for h in hist if h.get("date") != today] + [rec]
        hist = sorted(hist, key=lambda h: h["date"])[-GATE_DAYS * 2:]
        os.makedirs(HERE, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"updated": now_dt().isoformat(), "days": hist}, f, ensure_ascii=False,
                      indent=2)

    days = [h for h in hist if h.get("N", 0) > 0]
    # G-M1 连续 3 天非空
    if len(days) >= GATE_DAYS:
        v.add("G-M1", True, f"近{GATE_DAYS}天记录均非空 N={[h['N'] for h in days[-GATE_DAYS:]]}")
    else:
        v.add("G-M1", False,
              f"连续非空天数={len(days)}<{GATE_DAYS}（未到观测窗，今日 N={N} 已记录；"
              f"需连续 {GATE_DAYS} 天 --snapshot）")

    # G-M2 日波动 ±50%
    if len(days) >= 2:
        p, q = days[-2]["N"], days[-1]["N"]
        drift = abs(q - p) / p if p else float("inf")
        v.add("G-M2", drift <= GATE_DAILY_DRIFT,
              f"前日 N={p} 今日 N={q} 波动={drift*100:.1f}%（须 ≤{GATE_DAILY_DRIFT*100:.0f}%）")
    else:
        v.add("G-M2", False, f"历史记录不足 2 天（当前 {len(days)} 天），无法判波动")

    # G-M5 updated 当日/当次（复用 AC-M1-09 逻辑）
    up = d.get("updated", "")
    try:
        age_h = (now_dt() - datetime.datetime.fromisoformat(up)).total_seconds() / 3600
    except Exception:
        age_h = None
    v.add("G-M5", age_h is not None and 0 <= age_h <= args.max_age_hours,
          f"updated 距现在={age_h if age_h is not None else 'N/A'}h（须 ≤{args.max_age_hours}h）")
    return v


# ── 基线重采 ─────────────────────────────────────────────────────────────
def run_baseline(args):
    data_dir = args.data_dir
    logs_dir = os.path.join(os.path.dirname(data_dir.rstrip("/")), "logs")
    bl = {"captured_at": now_dt().isoformat()}

    # jsonl
    jsonl = os.path.join(data_dir, "news_geo.jsonl")
    if os.path.exists(jsonl):
        n, t1, t2 = bench_jsonl(data_dir)
        bl["jsonl"] = {"path": jsonl, "size_bytes": os.path.getsize(jsonl),
                       "rows": n, "line_count_s": round(t1, 3), "parse_s": round(t2, 3)}
        # fetched_at / sql_date 窗口
        fts, sqs = [], []
        with open(jsonl, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("fetched_at"):
                    fts.append(r["fetched_at"])
                if r.get("sql_date"):
                    sqs.append(r["sql_date"])
        if fts:
            bl["jsonl"]["fetched_at_window"] = [secs_to_ts(min(fts)), secs_to_ts(max(fts))]
            bl["jsonl"]["last24h"] = sum(1 for t in fts if time.time() - t <= 86400)
            bl["jsonl"]["last7d"] = sum(1 for t in fts if time.time() - t <= 86400 * 7)
        if sqs:
            bl["jsonl"]["sql_date_window"] = [min(sqs), max(sqs)]

    # news_geo.json
    jp = os.path.join(data_dir, "news_geo.json")
    if os.path.exists(jp):
        d = load_json(jp)
        bl["news_geo_json"] = {"size_bytes": os.path.getsize(jp), "updated": d.get("updated"),
                               "events": len(d.get("events", [])),
                               "articles": len(d.get("articles", []))}

    # scheduler_state
    sp = os.path.join(data_dir, "scheduler_state.json")
    if os.path.exists(sp):
        try:
            s = load_json(sp)
            bl["scheduler"] = {k: {"last_ok": s[k].get("last_ok"),
                                   "last_run_ts": s[k].get("last_run_ts"),
                                   "last_run_at": (secs_to_ts(s[k]["last_run_ts"])
                                                   if s[k].get("last_run_ts") else None)}
                               for k in ("gdelt_geo", "news_geo_feed") if k in s}
        except Exception:
            pass

    # gdelt 日志最近失败
    gdelt_log = os.path.join(logs_dir, "gdelt_geo.log")
    if os.path.exists(gdelt_log):
        lines = [l for l in open(gdelt_log, encoding="utf-8", errors="replace") if l.strip()]
        bl["gdelt_geo_log"] = {"last80_fail_flags": sum(1 for l in lines[-80:]
                                                        if "all_failed" in l or "slots_failed" in l)}

    out = os.path.join(HERE, f"qa-baseline-{now_dt().date().isoformat()}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bl, f, ensure_ascii=False, indent=2)
    print("=== 基线重采（§0，部署后先跑）===")
    print(json.dumps(bl, ensure_ascii=False, indent=2))
    print(f"已落盘: {out}")
    return 0


# ── main ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="开阳 M-1 news_geo 数据层验收")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    ap.add_argument("--enforce-unknown", action="store_true",
                    help="部署满48h后强制 event_type unknown<5%")
    ap.add_argument("--snapshot", action="store_true", help="记录今日 N/updated 到历史文件")
    ap.add_argument("--gate", action="store_true", help="门禁模式（G-M1/G-M2/G-M4/G-M5）")
    ap.add_argument("--bench-jsonl", action="store_true", help="基准：jsonl 全扫耗时")
    ap.add_argument("--baseline", action="store_true", help="基线重采并落盘")
    ap.add_argument("--window-hours", type=int, default=168,
                    help="时间窗小时数（默认168=7d；24h窗传24）")
    ap.add_argument("--max-age-hours", type=int, default=36,
                    help="updated 新鲜度阈值（默认36h；I15调度传1）")
    args = ap.parse_args()

    if args.baseline:
        return run_baseline(args)

    v = Verdict()

    if args.bench_jsonl:
        n, t1, t2 = bench_jsonl(args.data_dir)
        if n is None:
            v.add("AC-R-01", False, "jsonl 不存在，无法基准")
        else:
            v.add("AC-R-01", t2 <= PARSE_BUDGET_S,
                  f"jsonl 行数={n} 逐行计数={t1:.2f}s 完整parse={t2:.2f}s"
                  f"（须 ≤{PARSE_BUDGET_S:.0f}s；参考生成总耗时以 feed 日志为准）")

    try:
        run_checks(args, v)
    except FileNotFoundError as e:
        v.add("LOAD", False, f"数据文件缺失: {e}（确认 --data-dir 与 news_geo.json 已生成）")
    except json.JSONDecodeError as e:
        v.add("LOAD", False, f"news_geo.json 解析失败: {e}（文件损坏？）")

    run_fs_checks(args, v)

    if args.gate or args.snapshot:
        try:
            gate_checks(args, v)
        except Exception as e:
            v.add("GATE", False, f"门禁检查异常: {e}")

    # ── 汇总表 ──
    n_pass, n_fail, n_warn = v.summary()
    print("\n=== PASS/FAIL 汇总 ===")
    for code, status, msg in v.rows:
        print(f"[{status}] {code}: {msg}")
    print(f"\n统计: PASS={n_pass} FAIL={n_fail} WARN={n_warn}")
    if n_fail:
        print("结论: FAIL（存在未过项，按 arg-map-qa-2026-08-11.md §7 RSK 归因定位）")
        return 1
    print("结论: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
