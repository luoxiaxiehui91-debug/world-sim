#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计回归测试 #22 (scan-gdelt-slot) — fetch_gdelt_geo.run_incremental 记录的
last_success_slot_ts 应为本轮【最新】成功槽，而非最旧。

背景（已确认但尚未修复的 bug）
--------------------------------
_gdelt_urls_last_slots 生成的 URL 时间降序（最新在前）；run_incremental 顺序
遍历并 slots_ok.append(slot)，因此 slots_ok 也是降序（最新在前、最旧在后）。
第 955 行 `state[LAST_SLOT] = slots_ok[-1]` 取的是最后一个元素 = 本轮【最旧】
成功槽。_compute_new_slots 用 `s > last` 过滤，若 last 被设成最旧槽，下一轮会
重复拉取本轮已成功的较新槽（重复拉取 + 永远追不上最新）。

正确行为：state[LAST_SLOT] 应为本轮成功槽的最大值（最新槽）。
本测试断言【正确】行为，故对当前 buggy 代码会失败 → xfail(strict=True)。
bug 修复后会 xpass 触发 strict 失败，强制摘标记转为活体守卫。
"""
import os
import sys

import pytest

# 将「核心代码」加入 path（与该模块现有测试一致）
_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import fetch_gdelt_geo as m  # noqa: E402


# 三个降序（最新在前）的 15 分钟槽，YYYYMMDDHHmmss（字典序==时序）
_NEWEST = "20260828120000"
_MID = "20260828114500"
_OLDEST = "20260828113000"
_SLOTS_DESC = [_NEWEST, _MID, _OLDEST]


def _make_urls():
    base = getattr(m, "GDELT_BASE_URL", "http://data.gdeltproject.org")
    return [f"{base}/gdeltv2/{s}.export.CSV.zip" for s in _SLOTS_DESC]


@pytest.mark.xfail(
    strict=True,
    reason="审计发现 #22 HIGH correctness: run_incremental 用 slots_ok[-1] "
    "记成本轮最旧成功槽，应记最新槽(max)，否则下轮重复拉取已成功的较新槽。",
)
def test_run_incremental_records_newest_slot(tmp_path, monkeypatch):
    # DATA_DIR → tmp，state 文件（news_geo_state.json）落隔离目录，起点无 state
    monkeypatch.setattr(m, "DATA_DIR", str(tmp_path), raising=True)

    # 固定候选 URL（降序，最新在前）
    monkeypatch.setattr(m, "_gdelt_urls_last_slots", lambda now, num_slots=4: _make_urls())

    # 每个槽都拉取成功、校验通过、解析为空行（不触网、不落 jsonl）
    monkeypatch.setattr(m, "_fetch_gdelt_export", lambda url, proxy, timeout=30: b"dummy")
    monkeypatch.setattr(m, "_parse_export", lambda content: [])
    monkeypatch.setattr(m, "_validate_columns", lambda rows: (True, ""))

    # _merge_jsonl / news_geo.json 生成全部短路，避免真实文件 IO
    monkeypatch.setattr(
        m,
        "_merge_jsonl",
        lambda path, new_events, key="event_id": {
            "before": 0,
            "added": 0,
            "after": 0,
            "deduped": 0,
            "rows": [],
        },
    )
    monkeypatch.setattr(m, "_build_news_geo_events", lambda rows, now: [])
    monkeypatch.setattr(m, "_write_news_geo_json", lambda events: True)

    result = m.run_incremental(num_slots=len(_SLOTS_DESC))

    # 三槽全部成功
    assert set(result["slots_pulled"]) == set(_SLOTS_DESC)

    recorded = result["state_last_slot"]
    # 正确：记录最新槽（max）；当前 bug 记录最旧槽（min）→ 本断言在 buggy 代码下失败
    assert recorded == max(_SLOTS_DESC), (
        f"state.last_success_slot_ts 应为最新槽 {max(_SLOTS_DESC)}，"
        f"实际记录 {recorded}（本轮最旧成功槽），下轮会重复拉取较新槽"
    )
