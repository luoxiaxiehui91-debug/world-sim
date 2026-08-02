#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_gdelt_geo.py — 天枢 · GDELT 地理事件点 feed

设计文档：design/fetch_gdelt_geo_design.md
schema_version: news-geo-1.0

职责
----
从 GDELT v2 export（最近 1-2 个 15 分钟槽位）中解析 ActionGeo 坐标，
按关注国家与提及量过滤后落盘 news_geo.jsonl。结构见设计文档 §3。

红线（设计文档 §2.3 / §8）
-------------------------
1. 不 import 既有 gdelt 消费模块（其 import 即执行的副作用不可控）。
2. 落盘路径 DATA_DIR/news_geo.jsonl，不接受任何 NAS/SMB 绝对路径。
3. 不引入新依赖（仅 stdlib + 已有的 requests + 同包 gdelt_country_map）。
4. 不硬编码国码字符串（除 gdelt_country_map.py 的字典字面）。
5. 不 `from optim_config import FRED_PROXY`（红线：会 ImportError → DATA_DIR 落非持久卷）。
6. GDELT URL 必须明文 http（https 会 SSL 失败）。

使用
----
    python fetch_gdelt_geo.py --selftest   # 跑自测
    python fetch_gdelt_geo.py --demo       # 真拉数据 demo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import math
import os
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

import requests

from gdelt_country_map import WATCH_FIPS, iso_for_fips

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [fetch_gdelt_geo] %(message)s",
)
log = logging.getLogger("fetch_gdelt_geo")


# ── 模块常量（设计文档 §3.1 + §4.2 + §5.1 + §6.2）─────────────────────────

SCHEMA_VERSION: str = "news-geo-1.0"

GDELT_BASE_URL: str = "http://data.gdeltproject.org"
GDELT_PROXY_URL: str = os.environ.get("GDELT_PROXY", "http://192.168.31.108:7890")
PROXIES: Dict[str, str] = {
    "http": GDELT_PROXY_URL,
    "https": GDELT_PROXY_URL,
}

# GDELT v2 Events export 列下标（0-based；权威值见设计文档 §4.2）。
LAT_COL: int = 56
LONG_COL: int = 57
ACTION_GEO_TYPE_COL: int = 51
ACTION_GEO_FULLNAME_COL: int = 52
ACTION_GEO_CC_COL: int = 53

EXPECTED_COLS: int = 61
COORD_DECIMALS: int = 4
MIN_MENTIONS: int = 5
BAD_WIDTH_THRESHOLD: float = 0.05
SUCCESS_RATE_THRESHOLD: float = 0.01

DATA_DIR: str = os.environ.get("DATA_DIR", "/workspace/data")
OUTPUT_PATH: str = os.path.join(DATA_DIR, "news_geo.jsonl")

FIXTURE_PATH: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "tests",
    "fixtures",
    "sample_gdelt_row.txt",
)


# ── 业务函数实现（T02）─────────────────────────────────────────────────────


def _fetch_gdelt_export(url: str, proxy_url: str, timeout: int = 30) -> Optional[bytes]:
    """下载 GDELT v2 export 原始 zip 流。

    设计文档：§2.3 复用逻辑 + §7 采集窗口方案。

    强制明文 http（架构点 ③）；proxies 同时挂 http/https（防 redirect 跳 https）。

    Args:
        url: GDELT v2 export zip 完整 URL（如 http://data.gdeltproject.org/...zip）
        proxy_url: 代理 URL（如 http://192.168.31.108:7890）
        timeout: 请求超时（秒）

    Returns:
        成功返回 bytes（zip 流）；非 200 / 网络异常 / 解码错误 → None + WARNING 日志
    """
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        resp = requests.get(url, proxies=proxies, timeout=timeout, stream=False)
    except requests.RequestException as exc:
        log.warning("GDELT 请求异常: url=%s exc=%r", url, exc)
        return None
    if resp.status_code != 200:
        log.warning("GDELT 非 200: url=%s status=%d", url, resp.status_code)
        return None
    try:
        return resp.content
    except Exception as exc:
        log.warning("GDELT 取 content 失败: url=%s exc=%r", url, exc)
        return None


def _parse_export(content: bytes) -> List[Dict[str, str]]:
    """解压 GDELT export zip → 行字典列表（设计文档 §4.2 列映射）。

    用 csv 模块（delimiter='\t'）+ quoting=csv.QUOTE_NONE 解析；
    列索引 → 字段名映射：GLOBALEVENTID=0, SQLDATE=1, Actor1Code=5, Actor2Code=15,
    EventCode=26, Goldstein=30, NumMentions=31, NumSources=32, ActionGeo_Type=51,
    ActionGeo_FullName=52, ActionGeo_CountryCode=53, Lat=56, Long=57, SOURCEURL=60。

    Returns:
        每行一个 dict（缺失字段为空串）；行数 < 1 → []
    """
    out: List[Dict[str, str]] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
        if not zf.namelist():
            return out
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            reader = csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE)
            for cols in reader:
                if not cols:
                    continue
                out.append({
                    "GLOBALEVENTID": cols[0] if len(cols) > 0 else "",
                    "SQLDATE": cols[1] if len(cols) > 1 else "",
                    "Actor1Code": cols[5] if len(cols) > 5 else "",
                    "Actor2Code": cols[15] if len(cols) > 15 else "",
                    "EventCode": cols[26] if len(cols) > 26 else "",
                    "Goldstein": cols[30] if len(cols) > 30 else "",
                    "NumMentions": cols[31] if len(cols) > 31 else "",
                    "NumSources": cols[32] if len(cols) > 32 else "",
                    "ActionGeo_Type": cols[ACTION_GEO_TYPE_COL] if len(cols) > ACTION_GEO_TYPE_COL else "",
                    "ActionGeo_FullName": cols[ACTION_GEO_FULLNAME_COL] if len(cols) > ACTION_GEO_FULLNAME_COL else "",
                    "ActionGeo_CountryCode": cols[ACTION_GEO_CC_COL] if len(cols) > ACTION_GEO_CC_COL else "",
                    "Lat": cols[LAT_COL] if len(cols) > LAT_COL else "",
                    "Long": cols[LONG_COL] if len(cols) > LONG_COL else "",
                    "SOURCEURL": cols[60] if len(cols) > 60 else "",
                })
    except (zipfile.BadZipFile, KeyError, IndexError) as exc:
        log.warning("GDELT 解析失败: exc=%r", exc)
        return out
    return out


def _validate_columns(rows: List[Mapping[str, str]]) -> Tuple[bool, List[str]]:
    """抽样 5 行检查关键字段非空（设计文档 §4.3 A1–A6 软版）。

    关键字段：Lat / Long / ActionGeo_CountryCode / ActionGeo_FullName / ActionGeo_Type。

    Returns:
        (ok, errors): errors 空列表表示通过；非空列表逐条说明失败原因。
    """
    if not rows:
        return False, ["empty rows"]
    sample = rows[:5]
    required = ("Lat", "Long", "ActionGeo_CountryCode", "ActionGeo_FullName", "ActionGeo_Type")
    errors: List[str] = []
    for i, row in enumerate(sample):
        for key in required:
            v = row.get(key, "")
            if v is None or not str(v).strip():
                errors.append(f"row[{i}].{key} empty")
    return (len(errors) == 0), errors


def _is_finite_coord(value: str) -> bool:
    """判断坐标字符串是否为有限实数（设计文档 §4.3 A3）。

    value 形如 "-31.1234" 或 "116.5678"（GDELT 协议浮点字符串）。
    用 math.isfinite(float(value))；解析异常 → False；空串 → False。
    """
    if not value or not str(value).strip():
        return False
    try:
        v = float(value)
    except (ValueError, TypeError):
        return False
    return math.isfinite(v)


def _filter_row(row: Mapping[str, str], watch_fips: Set[str]) -> bool:
    """单行过滤链（设计文档 §5.1 过滤链 2/3/4/5；任务书严禁 fallback 兜底）。

    三项必须全通过：
      1) 坐标有效（_is_finite_coord 双真 + 范围 lat ∈ [-90, 90] / lng ∈ [-180, 180]）
      2) ActionGeo_CountryCode ∈ watch_fips（**未命中直接 False**，不保留）
      3) NumMentions >= MIN_MENTIONS=5
      4) ActionGeo_Type ∈ {0, 1, 2, 3, 4}（其他枚举视为虚拟地点丢弃）
    """
    # 1. 坐标有效 + 范围
    lat_str = row.get("Lat", "")
    lng_str = row.get("Long", "")
    if not (_is_finite_coord(lat_str) and _is_finite_coord(lng_str)):
        return False
    try:
        lat = float(lat_str)
        lng = float(lng_str)
    except (ValueError, TypeError):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return False

    # 2. 国家在 watch list（FIPS 两字码）
    cc = str(row.get("ActionGeo_CountryCode", "")).strip()
    if not cc or cc not in watch_fips:
        return False  # 禁止 fallback 兜底

    # 3. 提及量
    raw_mentions = row.get("NumMentions", "")
    try:
        mentions = int(raw_mentions) if str(raw_mentions).strip() else 0
    except (ValueError, TypeError):
        mentions = 0
    if mentions < MIN_MENTIONS:
        return False

    # 4. ActionGeo_Type 合法枚举
    raw_type = row.get("ActionGeo_Type", "")
    try:
        geo_type = int(raw_type) if str(raw_type).strip() else 0
    except (ValueError, TypeError):
        geo_type = 0
    if geo_type not in (0, 1, 2, 3, 4):
        return False

    return True


def _map_event(row: Mapping[str, str]) -> Dict[str, Any]:
    """单事件映射：tab 字段 → NewsGeoEvent dict（设计文档 §3.2 / 任务书 schema）。

    字段：lat / lng / type / country_iso / full_name / intensity / mentions /
          sources / event_id / sql_date / actor1_code / actor2_code /
          source_url / schema_version / fetched_at
    """
    lat = round(float(row["Lat"]), COORD_DECIMALS)
    lng = round(float(row["Long"]), COORD_DECIMALS)
    raw_type = row.get("ActionGeo_Type", "")
    try:
        geo_type = int(raw_type) if str(raw_type).strip() else 0
    except (ValueError, TypeError):
        geo_type = 0
    fips = str(row.get("ActionGeo_CountryCode", "")).strip()
    iso = iso_for_fips(fips) or fips  # 兜底：未映射保留 FIPS 原值（不丢事件）

    raw_g = row.get("Goldstein", "")
    try:
        goldstein = float(raw_g) if str(raw_g).strip() else 0.0
    except (ValueError, TypeError):
        goldstein = 0.0

    raw_m = row.get("NumMentions", "")
    try:
        mentions = int(raw_m) if str(raw_m).strip() else 0
    except (ValueError, TypeError):
        mentions = 0

    raw_s = row.get("NumSources", "")
    try:
        sources = int(raw_s) if str(raw_s).strip() else 0
    except (ValueError, TypeError):
        sources = 0

    return {
        "lat": lat,
        "lng": lng,
        "type": geo_type,
        "country_iso": iso,
        "full_name": row.get("ActionGeo_FullName", ""),
        "intensity": goldstein,
        "mentions": mentions,
        "sources": sources,
        "event_id": row.get("GLOBALEVENTID", ""),
        "sql_date": row.get("SQLDATE", ""),
        "actor1_code": row.get("Actor1Code", ""),
        "actor2_code": row.get("Actor2Code", ""),
        "source_url": row.get("SOURCEURL", ""),
        "schema_version": SCHEMA_VERSION,
        "fetched_at": int(time.time()),
    }


# ── 落盘（T02 最小可用版）───────────────────────────────────────────────────


def _write_news_geo(events: List[Mapping[str, Any]]) -> str:
    """落盘 news_geo.jsonl 到 DATA_DIR（最小可用版）。

    容器内路径：`/workspace/data/news_geo.jsonl`（可由 DATA_DIR 环境变量覆盖）。
    目录不存在则自动创建；jsonl 格式（每行一条 json，UTF-8，ensure_ascii=False）。
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return OUTPUT_PATH


# ── T03 state 滚动窗口（增量拉取 + 断点续传）─────────────────────────────────

STATE_SCHEMA_VERSION = "news-geo-state-1.0"
STATE_KEY_LAST_SLOT = "last_success_slot_ts"
STATE_KEY_LAST_RUN_AT = "last_success_run_at"
STATE_KEY_TOTAL_SLOTS = "total_slots_pulled"
STATE_KEY_TOTAL_EVENTS = "total_events_persisted"
STATE_KEY_RUN_COUNT = "run_count"
STATE_KEY_SCHEMA = "schema_version"
STATE_KEY_FAIL_SLOTS = "consecutive_fail_slots"


def _utcnow_ts() -> int:
    """Unix 时间戳（秒，UTC）。"""
    return int(datetime.now(timezone.utc).timestamp())


def _slot_from_url(url: str) -> str:
    """从 GDELT export URL 抽出 14 位 slot 时间戳（如 '20260801081500'）。"""
    base = url.rstrip("/").split("/")[-1]
    return base.split(".")[0]


def _load_state(path: str) -> Dict[str, Any]:
    """读取 state 文件（json），不存在则返回空 state dict。

    返回的 dict 总包含 schema_version 字段（缺失时填 STATE_SCHEMA_VERSION）。
    文件损坏时返回空 state + WARNING（fail-loud，不静默）。
    """
    if not os.path.exists(path):
        return {STATE_KEY_SCHEMA: STATE_SCHEMA_VERSION}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("state 文件损坏或读取失败（%s: %s），回退空 state", type(exc).__name__, exc)
        return {STATE_KEY_SCHEMA: STATE_SCHEMA_VERSION}
    if not isinstance(data, dict):
        log.warning("state 顶层不是 dict（%s），回退空 state", type(data).__name__)
        return {STATE_KEY_SCHEMA: STATE_SCHEMA_VERSION}
    data.setdefault(STATE_KEY_SCHEMA, STATE_SCHEMA_VERSION)
    return data


def _save_state(path: str, state: Mapping[str, Any]) -> None:
    """原子写 state 文件（tmp + os.replace）。目录不存在则创建。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(state), f, ensure_ascii=False)
    os.replace(tmp, path)


def _compute_new_slots(state: Mapping[str, Any], now_slots: List[str]) -> List[str]:
    """从 now_slots 中过滤掉已成功的（小于等于 state.last_success_slot_ts 的）。

    Args:
        state: 现有 state dict（可为空 dict）。
        now_slots: 候选 slot 时间戳列表（倒序：最新在前）。

    Returns:
        仍需拉取的 slot 列表（保持原顺序）。
    """
    last = state.get(STATE_KEY_LAST_SLOT)
    if not last:
        return list(now_slots)
    return [s for s in now_slots if s > last]


def _merge_jsonl(path: str, new_events: List[Mapping[str, Any]], key: str = "event_id") -> Dict[str, int]:
    """加载现有 jsonl + 去重 + 追加新事件 + 原子写回。

    Returns:
        {"before": int, "added": int, "after": int, "deduped": int}
    """
    seen: set = set()
    rows: List[Mapping[str, Any]] = []
    before = 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                k = d.get(key)
                if k is None or k in seen:
                    continue
                seen.add(k)
                rows.append(d)
                before += 1
    added = 0
    deduped = 0
    for ev in new_events:
        k = ev.get(key)
        if k is None:
            continue
        if k in seen:
            deduped += 1
            continue
        seen.add(k)
        rows.append(ev)
        added += 1
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return {"before": before, "added": added, "after": len(rows), "deduped": deduped}


# ── T04 占位（聚合）─────────────────────────────────────────────────────────


def _aggregate(events: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """同坐标聚合（设计文档 §6.1）。T04 实现。

    聚合键：(round(lat, 3), round(lng, 3), country_iso)。
    每组输出一个 cluster dict，字段见设计文档 §6.1。

    边界处理：
      - 空输入 [] → 返回 []
      - lat/lng 为 None 的 event 跳过
      - tone（当前无此字段）/ goldstein（intensity 字段）容忍 None（不计入均值分母）
      - event_types 去重保序（当前无此字段，输出 []）
    """
    if not events:
        return []

    # ── 分桶 ──
    buckets: Dict[Tuple[float, float, str], List[Mapping[str, Any]]] = {}
    for ev in events:
        lat = ev.get("lat")
        lng = ev.get("lng")
        if lat is None or lng is None:
            continue
        try:
            lat = float(lat)
            lng = float(lng)
        except (ValueError, TypeError):
            continue
        key = (round(lat, 3), round(lng, 3), str(ev.get("country_iso", "")))
        buckets.setdefault(key, []).append(ev)

    # ── 聚合 ──
    clusters: List[Dict[str, Any]] = []
    for (lat_key, lng_key, cc), bucket in buckets.items():
        # cluster_id
        raw = f"{lat_key:.3f}|{lng_key:.3f}|{cc}"
        cluster_id = hashlib.sha256(raw.encode()).hexdigest()[:16]

        # 找 mention_count 最大的那条事件（用于 lat/lng/source_url）
        best = max(bucket, key=lambda e: e.get("mentions", 0))

        # mention_count = sum
        mention_sum = sum(e.get("mentions", 0) for e in bucket)

        # intensity = max mention_count（不是 Goldstein！）
        intensity_val = best.get("mentions", 0)

        # goldstein_avg：取 intensity 字段（Goldstein 分数），跳过 None
        goldstein_vals = [e.get("intensity") for e in bucket if e.get("intensity") is not None]
        goldstein_avg = sum(goldstein_vals) / len(goldstein_vals) if goldstein_vals else None

        # tone_avg：当前 _map_event 不输出 tone，恒为 None
        tone_avg = None

        # event_ids：去重保序
        event_ids = list(dict.fromkeys(e.get("event_id", "") for e in bucket if e.get("event_id")))

        # event_types：当前无事件类型字段，输出空列表
        event_types: List[str] = []

        # first_seen / last_seen：优先 seen_slot（YYYYMMDDHHmmss），回退 sql_date 补齐 14 位
        def _pad_slot(s: str) -> str:
            """seen_slot 或 sql_date → 统一 YYYYMMDDHHmmss"""
            if not s:
                return ""
            return s if len(s) == 14 else (s + "000000")  # sql_date → YYYYMMDD000000
        slots = [_pad_slot(e.get("seen_slot") or e.get("sql_date", "")) for e in bucket]
        slots = [s for s in slots if s]
        first_seen = min(slots) if slots else ""
        last_seen = max(slots) if slots else ""

        clusters.append({
            "cluster_id": cluster_id,
            "lat": best.get("lat"),
            "lng": best.get("lng"),
            "country_code": cc,
            "intensity": intensity_val,
            "mention_count": mention_sum,
            "event_count": len(bucket),
            "event_types": event_types,
            "tone_avg": tone_avg,
            "goldstein_avg": goldstein_avg,
            "top_source_url": best.get("source_url", ""),
            "first_seen_slot": first_seen,
            "last_seen_slot": last_seen,
            "event_ids": event_ids,
        })

    return clusters


def run_aggregate() -> Dict[str, Any]:
    """读取 news_geo.jsonl → _aggregate → 落盘 news_geo_clusters.json + 打印统计。

    Returns:
        {"clusters": N, "events_in": N, "path": "..."}
    """
    events: List[Dict[str, Any]] = []
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    clusters = _aggregate(events)
    cluster_path = os.path.join(DATA_DIR, "news_geo_clusters.json")
    with open(cluster_path, "w", encoding="utf-8") as f:
        json.dump(clusters, f, ensure_ascii=False, indent=2)
    result = {
        "clusters": len(clusters),
        "events_in": sum(c["event_count"] for c in clusters),
        "path": cluster_path,
    }
    print("aggregate=" + json.dumps(result, ensure_ascii=False, default=str))
    return result


def run_incremental(num_slots: int = 4) -> Dict[str, Any]:
    """T03 增量拉取入口：仅拉 last_success_slot_ts 之后的新槽 → 合并去重 → 更新 state。

    Args:
        num_slots: 候选槽位数（覆盖最近 num_slots × 15 分钟窗口）。

    Returns:
        dict: status/no_new/ok, slots_pulled, slots_failed, new_events,
              total_after_dedup, deduped, state_last_slot, state_path, jsonl_path,
              urls_attempted, urls_ok, fetched_kb
    """
    state_path = os.path.join(DATA_DIR, "news_geo_state.json")
    jsonl_path = OUTPUT_PATH
    state = _load_state(state_path)
    now = datetime.now(timezone.utc)
    urls = _gdelt_urls_last_slots(now, num_slots=num_slots)
    now_slots = [_slot_from_url(u) for u in urls]
    new_slots = _compute_new_slots(state, now_slots)

    if not new_slots:
        result = {
            "status": "no_new",
            "state_last_slot": state.get(STATE_KEY_LAST_SLOT),
            "state_path": state_path,
            "jsonl_path": jsonl_path,
        }
        log.info("run_incremental: no new slots (state.last=%s)", result["state_last_slot"])
        return result

    log.info("run_incremental: will pull %d new slots (last state=%s)",
             len(new_slots), state.get(STATE_KEY_LAST_SLOT))

    all_events: List[Dict[str, Any]] = []
    slots_ok: List[str] = []
    slots_failed: List[str] = []
    total_bytes = 0
    urls_ok = 0
    for url, slot_s in zip(urls, now_slots):
        if slot_s not in new_slots:
            continue
        log.info("fetching: %s", url)
        content = _fetch_gdelt_export(url, GDELT_PROXY_URL, timeout=30)
        if content is None:
            slots_failed.append(slot_s)
            continue
        urls_ok += 1
        total_bytes += len(content)
        rows = _parse_export(content)
        log.info("parsed %d rows from %s", len(rows), url)
        ok, _ = _validate_columns(rows)
        if not ok:
            log.warning("validate_columns 失败，跳过该槽 %s", slot_s)
            slots_failed.append(slot_s)
            continue
        for r in rows:
            if _filter_row(r, WATCH_FIPS):
                ev = _map_event(r)
                if ev is not None:
                    ev["seen_slot"] = slot_s  # YYYYMMDDHHmmss ISO-like
                    all_events.append(ev)
        slots_ok.append(slot_s)

    merge = _merge_jsonl(jsonl_path, all_events)

    state[STATE_KEY_LAST_SLOT] = slots_ok[-1] if slots_ok else state.get(STATE_KEY_LAST_SLOT)
    state[STATE_KEY_LAST_RUN_AT] = _utcnow_ts()
    state[STATE_KEY_TOTAL_SLOTS] = state.get(STATE_KEY_TOTAL_SLOTS, 0) + len(slots_ok)
    state[STATE_KEY_TOTAL_EVENTS] = merge["after"]
    state[STATE_KEY_RUN_COUNT] = state.get(STATE_KEY_RUN_COUNT, 0) + 1
    state[STATE_KEY_FAIL_SLOTS] = 0 if slots_ok else state.get(STATE_KEY_FAIL_SLOTS, 0) + len(slots_failed)
    state[STATE_KEY_SCHEMA] = STATE_SCHEMA_VERSION
    _save_state(state_path, state)

    result = {
        "status": "ok" if slots_ok else "all_failed",
        "slots_pulled": slots_ok,
        "slots_failed": slots_failed,
        "new_events": len(all_events),
        "total_after_dedup": merge["after"],
        "deduped": merge["deduped"],
        "before_count": merge["before"],
        "added_count": merge["added"],
        "state_last_slot": state[STATE_KEY_LAST_SLOT],
        "state_path": state_path,
        "jsonl_path": jsonl_path,
        "urls_attempted": len(new_slots),
        "urls_ok": urls_ok,
        "fetched_kb": total_bytes // 1024,
    }
    print("incremental=" + json.dumps(result, ensure_ascii=False, default=str))
    return result


# ── run_demo（真拉数据 demo）────────────────────────────────────────────────


def _gdelt_urls_last_slots(now: datetime, num_slots: int = 2) -> List[str]:
    """生成最近 num_slots 个 15 分钟槽位的 GDELT v2 export URL（设计文档 §7）。"""
    minute = (now.minute // 15) * 15
    base = now.replace(minute=minute, second=0, microsecond=0)
    urls: List[str] = []
    for offset_min in range(15, 15 * (num_slots + 1), 15):
        ts = (base - timedelta(minutes=offset_min)).strftime("%Y%m%d%H%M%S")
        urls.append(f"{GDELT_BASE_URL}/gdeltv2/{ts}.export.CSV.zip")
    return urls


def run_demo() -> Dict[str, Any]:
    """T02 demo：拉最近 2 个槽位 → 全链路 → 落盘 + 打印统计。

    Returns:
        dict with keys: fetched_kb, rows_parsed, rows_filtered, rows_mapped,
        rows_written, sample, path, urls_attempted, urls_ok
    """
    now = datetime.now(timezone.utc)
    urls = _gdelt_urls_last_slots(now, num_slots=2)
    log.info("run_demo: will fetch %d slots, first=%s", len(urls), urls[0])

    all_rows: List[Dict[str, str]] = []
    total_bytes = 0
    urls_ok = 0
    for url in urls:
        log.info("fetching: %s", url)
        content = _fetch_gdelt_export(url, GDELT_PROXY_URL, timeout=30)
        if content is None:
            continue
        urls_ok += 1
        total_bytes += len(content)
        rows = _parse_export(content)
        log.info("parsed %d rows from %s", len(rows), url)
        all_rows.extend(rows)

    ok, errs = _validate_columns(all_rows)
    if not ok and all_rows:
        log.warning("validate_columns: %d errors in first sample (continuing)", len(errs))
    elif not all_rows:
        log.warning("validate_columns: empty rows (no upstream data)")

    filtered = [r for r in all_rows if _filter_row(r, WATCH_FIPS)]
    mapped = []
    demo_slot = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for r in filtered:
        ev = _map_event(r)
        if ev is not None:
            ev["seen_slot"] = demo_slot
            mapped.append(ev)
    path = _write_news_geo(mapped)

    sample = mapped[0] if mapped else None
    result = {
        "fetched_kb": total_bytes // 1024,
        "rows_parsed": len(all_rows),
        "rows_filtered": len(filtered),
        "rows_mapped": len(mapped),
        "rows_written": len(mapped),
        "urls_attempted": len(urls),
        "urls_ok": urls_ok,
        "sample": sample,
        "path": path,
        "validate_ok": ok,
        "validate_errors": len(errs),
    }
    print("demo=" + json.dumps(result, ensure_ascii=False, default=str))
    return result


# ── run_selftest（含 fixture 行解析断言）────────────────────────────────────


def _load_fixture_row() -> Optional[Dict[str, str]]:
    """读取 sample_gdelt_row.txt 首行 tab 分隔 61 列 → dict。"""
    if not os.path.isfile(FIXTURE_PATH):
        return None
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        line = f.read().strip()
    if not line or line.startswith("#"):
        return None
    cols = next(csv.reader([line], delimiter="\t", quoting=csv.QUOTE_NONE))
    if len(cols) != EXPECTED_COLS:
        return None
    return {
        "GLOBALEVENTID": cols[0],
        "SQLDATE": cols[1],
        "Actor1Code": cols[5],
        "Actor2Code": cols[15],
        "EventCode": cols[26],
        "Goldstein": cols[30],
        "NumMentions": cols[31],
        "NumSources": cols[32],
        "ActionGeo_Type": cols[ACTION_GEO_TYPE_COL],
        "ActionGeo_FullName": cols[ACTION_GEO_FULLNAME_COL],
        "ActionGeo_CountryCode": cols[ACTION_GEO_CC_COL],
        "Lat": cols[LAT_COL],
        "Long": cols[LONG_COL],
        "SOURCEURL": cols[60],
    }


def run_selftest() -> int:
    """T02 selftest：模块常量 + 签名 + fixture 行解析断言（5/5 解析 + 坐标 + 过滤）。

    新增（vs T01）：fixture 行必须 _validate_columns 5/5 + _is_finite_coord True +
    _filter_row True（确保 fixture 是合法可解析样本）。
    """
    # 1. 模块常量
    assert SCHEMA_VERSION == "news-geo-1.0"
    assert GDELT_BASE_URL.startswith("http")
    assert EXPECTED_COLS == 61
    assert COORD_DECIMALS == 4
    assert MIN_MENTIONS == 5
    assert 0.0 < BAD_WIDTH_THRESHOLD < 1.0
    assert 0.0 < SUCCESS_RATE_THRESHOLD < 1.0
    assert 0 <= LAT_COL < EXPECTED_COLS
    assert 0 <= LONG_COL < EXPECTED_COLS
    assert 0 <= ACTION_GEO_TYPE_COL < EXPECTED_COLS
    assert 0 <= ACTION_GEO_FULLNAME_COL < EXPECTED_COLS
    assert 0 <= ACTION_GEO_CC_COL < EXPECTED_COLS

    # 2. 签名齐全
    required_signatures = [
        "_fetch_gdelt_export",
        "_parse_export",
        "_validate_columns",
        "_is_finite_coord",
        "_filter_row",
        "_map_event",
        "_aggregate",
        "run_aggregate",
        "_write_news_geo",
        "_load_state",
        "_save_state",
        "_compute_new_slots",
        "_merge_jsonl",
        "_utcnow_ts",
        "_slot_from_url",
        "main",
        "run_selftest",
        "run_demo",
        "run_incremental",
    ]
    for name in required_signatures:
        assert hasattr(sys.modules[__name__], name), f"缺少符号: {name}"

    # 3. T04 _aggregate 单元测试（AC-1 ~ AC-5）
    # AC-1: _aggregate([]) 返回 []
    assert _aggregate([]) == []

    # AC-2: 同坐标 3 条 events 聚合为 1 cluster
    events = [
        {"lat": 33.3167, "lng": 75.7667, "country_iso": "IND", "mentions": 5, "event_id": "e1", "source_url": "http://a", "intensity": -7.0, "sql_date": "20260801", "type": 3},
        {"lat": 33.3167, "lng": 75.7667, "country_iso": "IND", "mentions": 3, "event_id": "e2", "source_url": "http://b", "intensity": -3.0, "sql_date": "20260801", "type": 3},
        {"lat": 33.3167, "lng": 75.7667, "country_iso": "IND", "mentions": 2, "event_id": "e3", "source_url": "http://c", "intensity": -5.0, "sql_date": "20260801", "type": 4},
    ]
    clusters = _aggregate(events)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["event_count"] == 3
    assert c["mention_count"] == 10  # 5+3+2
    assert c["intensity"] == 5.0     # max mention_count
    assert c["goldstein_avg"] == (-7.0 - 3.0 - 5.0) / 3  # mean of intensity field
    assert len(c["event_ids"]) == 3

    # AC-3: cluster_id 确定性（同输入两次调用相同）
    clusters2 = _aggregate(events)
    assert clusters[0]["cluster_id"] == clusters2[0]["cluster_id"]

    # AC-4: goldstein_avg 跳过 None / tone_avg 为 None
    events_none = [
        {"lat": 33.316, "lng": 75.766, "country_iso": "IND", "mentions": 5, "event_id": "e1", "source_url": "http://a", "intensity": -7.0, "sql_date": "20260801", "type": 3},
        {"lat": 33.316, "lng": 75.766, "country_iso": "IND", "mentions": 3, "event_id": "e2", "source_url": "http://b", "intensity": None, "sql_date": "20260801", "type": 3},
        {"lat": 33.316, "lng": 75.766, "country_iso": "IND", "mentions": 2, "event_id": "e3", "source_url": "http://c", "intensity": -5.0, "sql_date": "20260801", "type": 3},
    ]
    c2 = _aggregate(events_none)[0]
    assert c2["goldstein_avg"] == (-7.0 - 5.0) / 2  # None 跳过
    assert c2["tone_avg"] is None  # 无 tone 字段

    # AC-5: lat/lng None 的 event 被跳过
    events_bad = [
        {"lat": None, "lng": 75.766, "country_iso": "IND", "mentions": 5, "event_id": "e1", "source_url": "http://a", "intensity": -7.0, "sql_date": "20260801", "type": 3},
        {"lat": 33.316, "lng": 75.766, "country_iso": "IND", "mentions": 3, "event_id": "e2", "source_url": "http://b", "intensity": -3.0, "sql_date": "20260801", "type": 3},
    ]
    c3 = _aggregate(events_bad)
    assert len(c3) == 1  # 只有 e2
    assert c3[0]["event_count"] == 1

    # 4. fixture 行解析断言（任务书 C.3）
    fixture_row = _load_fixture_row()
    assert fixture_row is not None, f"fixture 行不存在或列数 != {EXPECTED_COLS}: {FIXTURE_PATH}"
    ok, errs = _validate_columns([fixture_row])
    assert ok, f"fixture 行 _validate_columns 失败: {errs}"
    assert _is_finite_coord(fixture_row["Lat"]), f"fixture 行 Lat 不可解析: {fixture_row['Lat']!r}"
    assert _is_finite_coord(fixture_row["Long"]), f"fixture 行 Long 不可解析: {fixture_row['Long']!r}"
    if WATCH_FIPS:
        assert _filter_row(fixture_row, WATCH_FIPS), (
            f"fixture 行 _filter_row 失败: cc={fixture_row.get('ActionGeo_CountryCode')!r} "
            f"mentions={fixture_row.get('NumMentions')!r} type={fixture_row.get('ActionGeo_Type')!r} "
            f"(WATCH_FIPS size={len(WATCH_FIPS)})"
        )
        # 5. _map_event 单元：fixture 行 → 输出 dict 类型断言（需要 WATCH_FIPS 非空才能过 filter）
        mapped = _map_event(fixture_row)
        assert isinstance(mapped["lat"], float)
        assert isinstance(mapped["lng"], float)
        assert isinstance(mapped["type"], int)
        assert mapped["schema_version"] == SCHEMA_VERSION
    else:
        print("  [SKIP] fixture filter/map 断言（WATCH_FIPS 为空，alert_config 不可导入）")

    print("=== fetch_gdelt_geo.py selftest: PASS ===")
    print(f"  [FIXTURE] {FIXTURE_PATH}")
    print(f"  [WATCH_FIPS size] {len(WATCH_FIPS)}")
    if WATCH_FIPS:
        print(f"  [mapped sample lat/lng] {mapped['lat']}/{mapped['lng']}")
    return 0


# ── CLI ────────────────────────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口（--selftest / --demo）。"""
    ap = argparse.ArgumentParser(description="天枢 · GDELT 地理事件点 feed")
    ap.add_argument("--selftest", action="store_true", help="跑 selftest")
    ap.add_argument("--demo", action="store_true", help="真拉数据 demo（覆盖式）")
    ap.add_argument("--incremental", action="store_true", help="增量拉取（state 滚动窗口）")
    ap.add_argument("--aggregate", action="store_true", help="从 news_geo.jsonl 聚合并落盘 news_geo_clusters.json")
    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest()
    if args.demo:
        run_demo()
        return 0
    if args.incremental:
        run_incremental()
        return 0
    if args.aggregate:
        run_aggregate()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


__all__ = [
    "SCHEMA_VERSION",
    "GDELT_BASE_URL",
    "GDELT_PROXY_URL",
    "PROXIES",
    "LAT_COL",
    "LONG_COL",
    "ACTION_GEO_TYPE_COL",
    "ACTION_GEO_FULLNAME_COL",
    "ACTION_GEO_CC_COL",
    "EXPECTED_COLS",
    "COORD_DECIMALS",
    "MIN_MENTIONS",
    "BAD_WIDTH_THRESHOLD",
    "SUCCESS_RATE_THRESHOLD",
    "DATA_DIR",
    "OUTPUT_PATH",
    "FIXTURE_PATH",
    "_fetch_gdelt_export",
    "_parse_export",
    "_validate_columns",
    "_is_finite_coord",
    "_filter_row",
    "_map_event",
    "_aggregate",
    "run_aggregate",
    "_write_news_geo",
    "run_selftest",
    "run_demo",
    "run_incremental",
]
