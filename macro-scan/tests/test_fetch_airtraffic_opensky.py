#!/usr/bin/env python3
"""离线验收：fetch_airtraffic_opensky.AirTrafficOpenSkyFetcher（不触网，mock requests）。

运行：python tests/test_fetch_airtraffic_opensky.py
退出码：0 = 全 PASS，1 = 存在失败断言。

风格参照主理人 _now_smoke.py / test_fetch_fao.py：伪造 requests / 类级断言 / sys.exit。
覆盖：
  flights_in_air / avg_altitude_m / avg_velocity_ms / top_origin_countries Top5 /
  total_states / scope="global" 计算正确（含在飞/地面混合、None 高度）。
"""
import os
import sys
import json
import tempfile
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import requests  # noqa: E402
from fetcher_base import Status  # noqa: E402
import fetch_airtraffic_opensky as omod  # noqa: E402
from fetch_airtraffic_opensky import AirTrafficOpenSkyFetcher  # noqa: E402

omod.AirTrafficOpenSkyFetcher.rate_interval = 0.0  # 测试不 sleep

_FIXTURE = os.path.join(_HERE, "fixtures", "opensky_states_sample.json")
with open(_FIXTURE, encoding="utf-8") as _fh:
    FIXTURE = json.load(_fh)


class FakeResp:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def json(self):
        return json.loads(self.text)


_fails = 0


def check(cond: bool, msg: str) -> None:
    global _fails
    if cond:
        print(f"  PASS: {msg}")
    else:
        _fails += 1
        print(f"  FAIL: {msg}")


def _expected_top5():
    return [
        {"country": "United States", "count": 6, "pct": 30.0},
        {"country": "China", "count": 5, "pct": 25.0},
        {"country": "Germany", "count": 4, "pct": 20.0},
        {"country": "United Kingdom", "count": 3, "pct": 15.0},
        {"country": "France", "count": 2, "pct": 10.0},
    ]


def test_aggregate() -> None:
    print("[test] OpenSky _aggregate 聚合计算")
    f = AirTrafficOpenSkyFetcher(tempfile.mkdtemp())
    as_of = "2026-07-28T14:00:00Z"
    r = f._aggregate(FIXTURE["states"], as_of)

    check(r is not None, "_aggregate 返回非 None")
    check(r["status"] == Status.OK, "status == ok")
    check(r["scope"] == "global", 'scope == "global"')
    check(r["as_of"] == as_of, "as_of 透传正确")
    check(r["flights_in_air"] == 20, "flights_in_air == 20（20 在飞）")
    check(r["total_states"] == 30, "total_states == 30")
    check(r["avg_altitude_m"] == 10500.0, "avg_altitude_m == 10500.0（排除 None 高度均值）")
    check(r["avg_velocity_ms"] == 220.0, "avg_velocity_ms == 220.0（排除 None 速度均值）")
    check(r["sample_limited"] is False, "sample_limited == false")

    top = r["top_origin_countries"]
    exp = _expected_top5()
    check(len(top) == 5, "top_origin_countries 长度 == 5")
    ok = True
    for got, want in zip(top, exp):
        if got.get("country") != want["country"] or got.get("count") != want["count"] \
                or abs(got.get("pct", 0) - want["pct"]) > 1e-6:
            ok = False
            break
    check(ok, "top_origin_countries 国家/计数/pct 与预期一致（US6/China5/Germany4/UK3/France2）")


def test_collect() -> None:
    print("[test] OpenSky collect（mock requests 返回 states 样本）")
    tmp = tempfile.mkdtemp()
    f = AirTrafficOpenSkyFetcher(tmp)
    fake = FakeResp(json.dumps(FIXTURE))
    with patch("requests.get") as mock_get:
        mock_get.return_value = fake
        result = f.collect()

    check(result is not None, "collect 返回非 None")
    check(result["status"] == Status.OK, "status == ok")
    check(result["flights_in_air"] == 20, "collect flights_in_air == 20")
    check(result["total_states"] == 30, "collect total_states == 30")
    check(result["scope"] == "global", 'collect scope == "global"')
    check(result["avg_altitude_m"] == 10500.0, "collect avg_altitude_m == 10500.0")
    check(result["avg_velocity_ms"] == 220.0, "collect avg_velocity_ms == 220.0")
    check(result["as_of"].endswith("Z"), "as_of 为 ISO UTC+Z")

    f.save_json(f.output_file, result)
    with open(os.path.join(tmp, f.output_file), encoding="utf-8") as fh:
        data = json.load(fh)
    check("_schema_version" in data, "落盘含 _schema_version")
    check(data.get("status") == "ok", "落盘含 status=ok")


if __name__ == "__main__":
    test_aggregate()
    test_collect()
    print(f"\n断言失败数: {_fails}")
    sys.exit(1 if _fails else 0)
