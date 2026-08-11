#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_data_map.py — 部署后数据抽查脚本（data-map / kaiyang-map-arg）
=====================================================================

背景
----
arch-map 改造 fetch_gdelt_geo.py：① _map_event 补 event_code/root_code；
② run_incremental 末尾生成 news_geo.json（events[]，§2.7 契约）。
本脚本验证 jsonl → news_geo.json 派生正确性，供 QA AC-M1-01~12 数据侧抽查。

运行方式（容器内只读，不改任何代码/数据）
----------------------------------------
    # 方式一（推荐，不经宿主机落盘）：
    ssh nas "docker exec -i macro-scan-macro-scan-1 python3 -" < verify_data_map.py

    # 方式二（若脚本已 cp 进容器）：
    ssh nas "docker exec macro-scan-macro-scan-1 python3 /workspace/docs/qa-scripts/verify_data_map.py"

检查项
------
  A1  jsonl 尾部新行含 event_code/root_code（部署后新写入行，非旧行；GDELT 断供
      窗口 AC-R-03 时降级 WARN 不误判派生 bug）
  B1  news_geo.json 顶层结构 {schema_version, updated, events[]}
  B2  id 唯一（AC-M1-07）
  B3  lat/lng 4 位小数且合法范围（AC-M1-02/03）
  B4  country 非空率 >= 99%（AC-M1-06）
  B5  event_type 仅契约五枚举之一（conflict/protest/disaster/political/unknown，
      48h 过渡期） + 分布打印（AC-M1-05）
  B6  intensity 0-100、无负值、max<=100、max>=60、P90>=40（AC-M1-04）
  C1  时间窗口径可推断：fetched_at/seen_slot（采集口径）或 sql_date（事件日口径）
      二者至少一种覆盖 24h 窗口（AC-M1-10）
  D1  点数 100 <= N <= 2000（AC-M1-01）

退出码：0 = 无 FAIL（WARN 允许）；1 = 任一 FAIL；2 = 数据缺失/无法判断。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── 默认路径（容器内）──────────────────────────────────────────────────────
DEFAULT_DATA_DIR = "/workspace/data"
DEFAULT_JSONL = os.path.join(DEFAULT_DATA_DIR, "news_geo.jsonl")
DEFAULT_JSON = os.path.join(DEFAULT_DATA_DIR, "news_geo.json")

# B5 断言域：五枚举（含 unknown 48h 过渡期；lead 裁决放宽，qa-map 协调）。
# 部署满 48h 后 unknown<5% 由 qa-map verify_data.py --enforce-unknown 管，本脚本不判比例。
ALLOWED_EVENT_TYPES = {"conflict", "protest", "disaster", "political", "unknown"}
ID_PREFIX = "gdelt-"          # arch §4.3：id = f"gdelt-<event_id>"
REQUIRED_TOP = {"schema_version", "updated", "events"}
STALL_HOURS = 0.75            # 断供判定：数据落后 >45min（>2×I15）视为 GDELT 间歇断供窗口


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="部署后数据抽查：jsonl→news_geo.json 派生正确性")
    ap.add_argument("--jsonl", default=DEFAULT_JSONL, help="news_geo.jsonl 路径")
    ap.add_argument("--json", default=DEFAULT_JSON, help="news_geo.json 路径")
    ap.add_argument("--window-hours", type=float, default=24.0, help="时间窗（默认 24h）")
    ap.add_argument("--tail-n", type=int, default=200,
                    help="A1 检查 jsonl 尾部 N 行（部署后新行近似；默认 200）")
    ap.add_argument("--deploy-ts", type=float, default=None,
                    help="可选：部署完成 Unix 时间戳，A1 只检查 fetched_at >= 该值的行")
    ap.add_argument("--min-tail-ratio", type=float, default=0.99,
                    help="A1 判定阈值：尾部新行含 event_code/root_code 的最低比例")
    return ap.parse_args()


# ── 工具函数 ───────────────────────────────────────────────────────────────

def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def container_cmd(args: List[str]) -> Tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def file_evidence(path: str) -> str:
    """容器内证据：ls -la / wc -l / sha256sum（与 QA B 行口径一致）。"""
    lines = []
    lines.append(f"$ ls -la {path}")
    _, out = container_cmd(["ls", "-la", path])
    lines.append(out.strip())
    lines.append(f"$ wc -l {path}")
    _, out = container_cmd(["wc", "-l", path])
    lines.append(out.strip())
    lines.append(f"$ sha256sum {path}")
    _, out = container_cmd(["sha256sum", path])
    lines.append(out.strip())
    return "\n".join(lines)


def load_jsonl(path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """读 jsonl：返回 (全部行, event_id → 行索引)。"""
    rows: List[Dict[str, Any]] = []
    index: Dict[str, Dict[str, Any]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(d)
            eid = d.get("event_id")
            if eid is not None:
                index.setdefault(str(eid), d)   # 去重保首见（与 _merge_jsonl 一致）
    return rows, index


def load_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def is_4decimal(v: float) -> bool:
    return abs(round(v, 4) - v) < 1e-9 and abs(v * 10000 - round(v * 10000)) < 1e-6


# ── 检查实现 ───────────────────────────────────────────────────────────────

def check_tail_has_codes(rows: List[Dict[str, Any]], tail_n: int,
                         deploy_ts: Optional[float],
                         min_ratio: float,
                         stall: Optional[float] = None,
                         now: Optional[datetime] = None,
                         json_updated: Optional[str] = None,
                         json_events: Optional[List[Any]] = None) -> Tuple[str, str]:
    """A1：部署后新行（tail / fetched_at>=deploy_ts）必须含 event_code/root_code。

    返回 (判定, 明细)，判定 ∈ {"PASS","FAIL","WARN"}：
    - WARN 断供：数据处于 GDELT 间歇断供窗口（jsonl fetched_at 与 news_geo.json
      updated 双双停滞 >STALL_HOURS，qa-map 冒烟 10/80 行 all_failed，AC-R-03）。
    - WARN 待增量：派生逻辑已部署生效（news_geo.json events 非空且 updated 新鲜），
      但 jsonl 尚无带码新行——部署后首个 I15 增量（≤15min）未到，属过渡态而非 bug。
    """
    if deploy_ts is not None:
        cands = [r for r in rows if (r.get("fetched_at") or 0) >= deploy_ts]
        desc = f"fetched_at >= {datetime.fromtimestamp(deploy_ts).isoformat()}"
    else:
        cands = rows[-tail_n:]
        desc = f"尾部 {tail_n} 行"
    n = len(cands)
    stall_h = stall if stall is not None else STALL_HOURS
    now = now or datetime.now(timezone.utc)

    def _fresh_ts(ts_str: str, fallback_utc: bool = True) -> Optional[datetime]:
        try:
            t = datetime.fromisoformat(ts_str)
        except (TypeError, ValueError):
            return None
        if t.tzinfo is None and fallback_utc:
            t = t.replace(tzinfo=timezone.utc)
        return t

    def _stalled():
        if not rows or json_updated is None:
            return False
        fts = [r.get("fetched_at") for r in rows if isinstance(r.get("fetched_at"), (int, float))]
        if not fts:
            return False
        max_fetched = max(fts)
        up_ts = _fresh_ts(json_updated)
        if up_ts is None:
            return False
        gap = (now - datetime.fromtimestamp(max_fetched, tz=timezone.utc)).total_seconds() \
              > stall_h * 3600 and \
              (now - up_ts).total_seconds() > stall_h * 3600
        if gap:
            return f"数据停滞: jsonl 最新 fetched_at={datetime.fromtimestamp(max_fetched).isoformat()} " \
                   f"news_geo.json updated={json_updated}（均 >{stall_h*60:.0f}min）→ 疑 GDELT 断供（AC-R-03）"
        return False

    def _deployed_pending_incremental():
        """派生逻辑已生效、但 jsonl 尚无带码行（等 I15 增量）→ 返回提示文本或 False。"""
        if json_updated is None or not json_events:
            return False
        up_ts = _fresh_ts(json_updated)
        if up_ts is None or (now - up_ts).total_seconds() > stall_h * 3600:
            return False  # updated 陈旧：无最近成功生成
        fts = [r.get("fetched_at") for r in rows if isinstance(r.get("fetched_at"), (int, float))]
        max_fetched = max(fts) if fts else None
        code_rows = sum(1 for r in rows if r.get("event_code") or r.get("root_code"))
        hint = f"news_geo.json 已生成（events={len(json_events)} updated={json_updated}），" \
               f"但全 jsonl 带码行={code_rows}"
        if max_fetched is not None:
            hint += f"；最新 fetched_at={datetime.fromtimestamp(max_fetched).isoformat()}"
        hint += " → 部署后首个 I15 增量未到（≤15min/周期），待增量后复查"
        return hint

    if n == 0:
        warn = _stalled()
        if warn:
            return "WARN", f"A1 WARN: {desc} 无候选行，且 {warn} → 非派生 bug，断供恢复后复查"
        pend = _deployed_pending_incremental()
        if pend:
            return "WARN", f"A1 WARN: {desc} 无候选行；{pend}"
        return "FAIL", f"A1 FAIL: {desc} 无候选行（部署未生效？或 fetched_at 均 < deploy_ts）"

    # tail 模式（未给 --deploy-ts）且候选行混合新旧批次时，
    # 取"最新 fetched_at 增量批次"判定（避免把旧行无码误判为派生 bug）。
    mode_note = ""
    cands_check = cands
    if deploy_ts is None and cands:
        fts2 = [r.get("fetched_at") for r in cands
                if isinstance(r.get("fetched_at"), (int, float))]
        if fts2:
            mx = max(fts2)
            batch = [r for r in cands if r.get("fetched_at") == mx]
            if len(batch) >= max(1, int(n * 0.1)):
                cands_check = batch
                mode_note = (f"（最新增量批次 fetched_at="
                             f"{datetime.fromtimestamp(mx).isoformat()} n={len(batch)}）")
    ec = sum(1 for r in cands_check if r.get("event_code"))
    rc = sum(1 for r in cands_check if r.get("root_code"))
    nn = len(cands_check)
    ok = (nn > 0 and ec >= min_ratio * nn and rc >= min_ratio * nn)
    verdict = "PASS" if ok else "FAIL"
    extra = None
    if not ok:
        warn = _stalled()
        if warn:
            verdict = "WARN"
            extra = warn
        else:
            pend = _deployed_pending_incremental()
            if pend:
                verdict = "WARN"
                extra = pend
    thr = f"{min_ratio*100:.0f}%" if min_ratio != 1.0 else "100%"
    detail = (f"A1 {verdict}: 候选={desc}{mode_note} n={nn} "
              f"event_code={pct(ec, nn)} root_code={pct(rc, nn)} (阈值 {thr})")
    if ok and nn:
        ft = [cands_check[i].get("fetched_at") for i in (0, nn // 2, nn - 1) if i < nn]
        detail += " | 批次 fetched_at 抽样=" + ", ".join(
            datetime.fromtimestamp(t).isoformat() for t in ft if t)
    if verdict == "WARN" and extra:
        detail += " | " + str(extra)
    return verdict, detail


def check_top_level(doc: Dict[str, Any]) -> Tuple[bool, str]:
    """B1：顶层 {schema_version, updated, events[]}，schema_version="1.0"（AC-M1-01/08）。"""
    if not isinstance(doc, dict):
        return False, f"B1 FAIL: 顶层非 dict（{type(doc)}）"
    missing = REQUIRED_TOP - set(doc.keys())
    if missing:
        return False, f"B1 FAIL: 缺顶层键 {sorted(missing)}"
    sv = doc.get("schema_version")
    upd = doc.get("updated")
    if sv != "1.0":
        return False, f"B1 FAIL: schema_version={sv!r}（契约要求 '1.0'）"
    evs = doc.get("events")
    if not isinstance(evs, list):
        return False, f"B1 FAIL: events 非数组（{type(evs)}）"
    if "_schema_version" in doc or "generated_at" in doc:
        return False, "B1 FAIL: 出现旧 feed 的 _schema_version/generated_at 双键（契约漂移）"
    return True, (f"B1 PASS: schema_version={sv!r} updated={upd} events={len(evs)} 条")


def check_id_unique(evs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """B2：events[] 内 id 全局唯一（AC-M1-07）。"""
    ids = [e.get("id") for e in evs]
    dup = {x for x in ids if x is not None and ids.count(x) > 1}
    miss = [i for i, x in enumerate(ids) if not x]
    if dup or miss:
        return False, f"B2 FAIL: 重复 id={sorted(dup)[:5]} 缺失 id 条数={len(miss)}"
    return True, f"B2 PASS: {len(ids)} 个 id 全部唯一"


def check_coords(evs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """B3：lat/lng 4 位小数且合法（AC-M1-02/03）。"""
    bad = []
    for e in evs:
        lat, lng = e.get("lat"), e.get("lng")
        if not (isinstance(lat, (int, float)) and isinstance(lng, (int, float))):
            bad.append((e.get("id"), "非数值", lat, lng))
            continue
        if not (math.isfinite(lat) and math.isfinite(lng)):
            bad.append((e.get("id"), "非有限", lat, lng))
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            bad.append((e.get("id"), "越界", lat, lng))
            continue
        if not (is_4decimal(lat) and is_4decimal(lng)):
            bad.append((e.get("id"), "非4位小数", lat, lng))
            continue
    if bad:
        return False, f"B3 FAIL: 非法坐标 {len(bad)} 条，样例={bad[:3]}"
    return True, f"B3 PASS: {len(evs)} 条坐标均合法且 4 位小数"


def check_country(evs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """B4：country 非空率 >= 99%（AC-M1-06）。"""
    n = len(evs)
    miss = sum(1 for e in evs if not e.get("country"))
    rate = (n - miss) / n if n else 0.0
    ok = rate >= 0.99
    return ok, f"B4 {'PASS' if ok else 'FAIL'}: country 非空率 {pct(n - miss, n)}（阈值 99.0%，缺失 {miss} 条）"


def check_event_type(evs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """B5：event_type 仅契约五枚举之一 + 分布打印（AC-M1-05，含 unknown 48h 过渡期）。
    枚举：conflict / protest / disaster / political / unknown（unknown 由 qa-map
    verify_data.py --enforce-unknown 在部署满 48h 后以 <5% 门槛把关，本脚本不判比例）。"""
    from collections import Counter
    c = Counter(e.get("event_type", "") for e in evs)
    bad = {k: v for k, v in c.items() if k not in ALLOWED_EVENT_TYPES}
    ok = not bad
    detail = (f"B5 {'PASS' if ok else 'FAIL'}: event_type 分布=" +
              dict(c).__str__())
    if bad:
        detail += f" | 非法枚举={bad}"
    else:
        unk = c.get("unknown", 0)
        if unk:
            detail += f" | unknown={pct(unk, len(evs))}（48h 过渡期内允许，之后交 verify_data.py 把关）"
    return ok, detail


def _p90(sorted_vals: List[float]) -> float:
    """P90 口径与 QA AC-M1-04 一致：v[int(len(v)*0.9)]。"""
    if not sorted_vals:
        return float("nan")
    return sorted_vals[int(len(sorted_vals) * 0.9)]


def check_intensity(evs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """B6：intensity 0-100、无负值、max<=100、max>=60、P90>=40（AC-M1-04）。"""
    vals = []
    bad = []
    for e in evs:
        v = e.get("intensity")
        if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
            bad.append((e.get("id"), "非数值", v))
            continue
        if v < 0 or v > 100:
            bad.append((e.get("id"), "越界", v))
            continue
        vals.append(float(v))
    if bad:
        return False, f"B6 FAIL: intensity 非法 {len(bad)} 条，样例={bad[:3]}"
    sv = sorted(vals)
    mx = sv[-1] if sv else float("nan")
    p50 = sv[len(sv) // 2] if sv else float("nan")
    p90 = _p90(sv)
    p99 = sv[min(int(len(sv) * 0.99), len(sv) - 1)] if sv else float("nan")
    ok = (len(sv) > 0 and mx <= 100 and mx >= 60 and p90 >= 40)
    detail = (f"B6 {'PASS' if ok else 'FAIL'}: intensity 0-100, 无负值, "
              f"min={sv[0] if sv else 'n/a'} P50={p50:.1f} P90={p90:.1f} "
              f"P99={p99:.1f} max={mx:.1f}（要求 max>=60 且 P90>=40）")
    return ok, detail


def check_window(evs: List[Dict[str, Any]], index: Dict[str, Dict[str, Any]],
                 window_h: float, now: datetime) -> Tuple[bool, str]:
    """C1：时间窗口径可推断——fetched_at/seen_slot（采集）或 sql_date（事件日），
    至少一种覆盖 window_h 窗口（AC-M1-10，禁止混用/全量回填）。"""
    if not evs:
        return False, "C1 FAIL: 无事件可查窗口"
    w = timedelta(hours=window_h)

    # 口径 1：采集时间（fetched_at，Unix UTC 秒）；seen_slot 兜底解析
    def slot_to_ts(slot: str) -> Optional[float]:
        try:
            return datetime.strptime(slot, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None

    n_in_collect, n_total = 0, 0
    n_in_event, n_total_event = 0, 0
    for e in evs:
        eid = str(e.get("id", "")).removeprefix(ID_PREFIX)
        src = index.get(eid)
        # 采集口径
        ft = src.get("fetched_at") if src else None
        if ft is None and src:
            ft = slot_to_ts(str(src.get("seen_slot") or ""))
        if ft is not None:
            n_total += 1
            if (now.timestamp() - ft) <= w.total_seconds():
                n_in_collect += 1
        # 事件日口径
        sd = src.get("sql_date") if src else None
        if sd:
            n_total_event += 1
            try:
                ed = datetime.strptime(str(sd), "%Y%m%d").replace(tzinfo=timezone.utc)
                if (now - ed) <= w:
                    n_in_event += 1
            except ValueError:
                pass

    collect_ok = n_total > 0 and n_in_collect / n_total >= 0.99
    event_ok = n_total_event > 0 and n_in_event / n_total_event >= 0.99
    detail = (f"C1 窗口={window_h:.0f}h now={now.isoformat()} | "
              f"采集口径(fetched_at/seen_slot) {pct(n_in_collect, n_total)} "
              f"{'PASS' if collect_ok else 'FAIL'} | "
              f"事件日口径(sql_date) {pct(n_in_event, n_total_event)} "
              f"{'PASS' if event_ok else 'FAIL'}（AC-M1-10：至少一径可推断且同量级）")
    if collect_ok and event_ok:
        return True, detail + " | 两径均通过（混用风险低）"
    if collect_ok:
        return True, detail + " | 以采集口径为准"
    if event_ok:
        return True, detail + " | 以事件日口径为准（注意 sql_date 滞后 ~1 天）"
    return False, detail + " | 两径均未达 99% 覆盖"


def check_count(evs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """D1：100 <= N <= 2000（AC-M1-01）。"""
    n = len(evs)
    ok = 100 <= n <= 2000
    return ok, f"D1 {'PASS' if ok else 'FAIL'}: 事件数 N={n}（要求 100<=N<=2000）"


def main() -> int:
    args = _parse_args()
    results: List[Tuple[str, str, str]] = []

    # ── 证据块 ─────────────────────────────────────────────────────────────
    print("=" * 76)
    print("VERIFY_DATA_MAP 部署后数据抽查")
    print(f"  时间: {datetime.now().astimezone().isoformat()}")
    print(f"  jsonl: {args.jsonl}   json: {args.json}   窗口: {args.window_hours}h")
    print("=" * 76)

    print("\n[容器内证据]")
    print(file_evidence(args.jsonl))
    print(file_evidence(args.json))
    _, out = container_cmd(["cat", args.jsonl.replace(".jsonl", "_state.json")])
    if out.strip():
        print(f"$ cat {args.jsonl.replace('.jsonl','_state.json')}\n{out.strip()}")

    if not os.path.exists(args.jsonl):
        print(f"\nFATAL: jsonl 不存在 {args.jsonl}")
        return 2
    rows, index = load_jsonl(args.jsonl)
    print(f"\n[jsonl] 共 {len(rows)} 行，event_id 索引 {len(index)} 个")
    if not os.path.exists(args.json):
        print(f"FATAL: news_geo.json 不存在 {args.json}（部署未生效？）")
        return 2
    doc = load_json(args.json)
    if doc is None:
        print(f"FATAL: news_geo.json 解析失败（{args.json}）")
        return 2

    # 旧空壳检测
    evs = doc.get("events") if isinstance(doc, dict) else None
    if not isinstance(evs, list):
        print(f"FATAL: 顶层无 events 数组（仍是旧结构 articles? 见下）")
        if isinstance(doc, dict) and "articles" in doc:
            print(f"  检出旧 feed 空壳结构：articles={len(doc.get('articles', []))} 条。"
                  f"部署未生效或仍指向旧产物。")
        return 2

    now = datetime.now(timezone.utc)

    # ── A1 尾部新行含 event_code/root_code（断供/待增量 WARN，qa-map 协调 AC-R-03）──
    verdict, detail = check_tail_has_codes(rows, args.tail_n, args.deploy_ts,
                                           args.min_tail_ratio, now=now,
                                           json_updated=doc.get("updated"),
                                           json_events=evs)
    results.append(("A1", verdict, detail))

    # ── B 组 news_geo.json 字段映射 ───────────────────────────────────────
    for name, fn in [("B1", check_top_level), ("B2", check_id_unique),
                     ("B3", check_coords), ("B4", check_country),
                     ("B5", check_event_type), ("B6", check_intensity)]:
        ok, detail = fn(doc if name == "B1" else evs)
        results.append((name, "PASS" if ok else "FAIL", detail))

    # ── C1 时间窗 ─────────────────────────────────────────────────────────
    ok, detail = check_window(evs, index, args.window_hours, now)
    results.append(("C1", "PASS" if ok else "FAIL", detail))

    # ── D1 点数 ───────────────────────────────────────────────────────────
    ok, detail = check_count(evs)
    results.append(("D1", "PASS" if ok else "FAIL", detail))

    # ── 汇总 ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 76)
    print("抽查结果汇总")
    print("=" * 76)
    n_pass = n_warn = n_fail = 0
    for name, verdict, detail in results:
        print(f"[{verdict}] {name}: {detail}")
        n_pass += verdict == "PASS"
        n_warn += verdict == "WARN"
        n_fail += verdict == "FAIL"
    print("-" * 76)
    total = len(results)
    print(f"SUMMARY: PASS={n_pass} WARN={n_warn} FAIL={n_fail} / {total}")
    if n_warn:
        print("注: WARN 为提示性判定（如 GDELT 断供窗口 AC-R-03），不计 FAIL，但需关注。")
    if n_fail == 0:
        print("判定: 无 FAIL ✅ — 数据侧 AC-M1 抽查达标（WARN 项按提示跟进）")
        return 0
    print("判定: 存在 FAIL ❌ — 见上方明细")
    return 1


if __name__ == "__main__":
    sys.exit(main())
