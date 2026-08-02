#!/usr/bin/env python3
"""离线验收：fetch_fao.FaoFetcher（不触网，mock requests + 本地样本 CSV）。

运行：python tests/test_fetch_fao.py
退出码：0 = 全 PASS，1 = 存在失败断言。

风格参照主理人 _now_smoke.py：伪造 requests / 类级断言 / sys.exit 退出码。
覆盖：
  1) _parse_csv 直接解析本地样本 → 断言 fao_food_price_index 与 5 项 sub_indices。
  2) collect（mock requests 返回样本）→ 断言落盘 fao_food_price.json 含 _schema_version+status。
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
from fetch_fao import FaoFetcher  # noqa: E402

_FIXTURE = os.path.join(_HERE, "fixtures", "fao_ffpi_sample.csv")
with open(_FIXTURE, encoding="utf-8") as _fh:
    SAMPLE_CSV = _fh.read()


class FakeResp:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


_fails = 0


def check(cond: bool, msg: str) -> None:
    global _fails
    if cond:
        print(f"  PASS: {msg}")
    else:
        _fails += 1
        print(f"  FAIL: {msg}")


def test_parse_csv() -> None:
    print("[test] FAO _parse_csv 直接解析样本")
    f = FaoFetcher(tempfile.mkdtemp())
    parsed = f._parse_csv(SAMPLE_CSV)

    check(parsed is not None, "_parse_csv 返回非 None")
    check(parsed["fao_food_price_index"] == 128.7,
          "fao_food_price_index == 末行 128.7")
    subs = parsed["sub_indices"]
    check(set(subs.keys()) == {"meat", "dairy", "cereals", "vegetable_oils", "sugar"},
          "sub_indices 含 5 项（meat/dairy/cereals/vegetable_oils/sugar）")
    check(subs["meat"] == 115.8, "meat == 115.8")
    check(subs["dairy"] == 150.1, "dairy == 150.1")
    check(subs["cereals"] == 139.2, "cereals == 139.2")
    check(subs["vegetable_oils"] == 156.3, "vegetable_oils == 156.3")
    check(subs["sugar"] == 128.4, "sugar == 128.4")


def test_collect() -> None:
    print("[test] FAO collect（mock requests 返回样本 CSV）")
    tmp = tempfile.mkdtemp()
    f = FaoFetcher(tmp)
    fake = FakeResp(SAMPLE_CSV)

    with patch("requests.get") as mock_get:
        mock_get.return_value = fake
        # 跳过 HTML token 解析，直接给定版本化 URL
        with patch.object(FaoFetcher, "_resolve_csv_url",
                          return_value=("https://www.fao.org/worldfoodsituation/"
                                        "foodpricesindex/food_price_indices_data.csv"
                                        "?sfvrsn=testtoken")):
            result = f.collect()

    check(result is not None, "collect 返回非 None")
    check(result.get("status") == Status.OK, "status == ok")
    check(result["fao_food_price_index"] == 128.7,
          "fao_food_price_index == 128.7")
    check(set(result["sub_indices"].keys()) ==
          {"meat", "dairy", "cereals", "vegetable_oils", "sugar"},
          "sub_indices 含 5 项")

    f.save_json(f.output_file, result)
    with open(os.path.join(tmp, f.output_file), encoding="utf-8") as fh:
        data = json.load(fh)
    check("_schema_version" in data, "落盘含 _schema_version")
    check(data.get("status") == "ok", "落盘含 status=ok")


if __name__ == "__main__":
    test_parse_csv()
    test_collect()
    print(f"\n断言失败数: {_fails}")
    sys.exit(1 if _fails else 0)
