#!/usr/bin/env python3
"""离线验收：fetch_commodity_yahoo.CommodityYahooFetcher（不触网，mock requests）。

运行：python tests/test_fetch_commodity_yahoo.py
退出码：0 = 全 PASS，1 = 存在失败断言。

风格参照主理人 _now_smoke.py / test_fetch_fao.py：伪造 requests / 类级断言 / sys.exit。
覆盖：
  1) 正常路径：WTI/Brent/Copper 三个 symbol 解析正确、单位正确（铜 USD/lb）、as_of ISO+Z。
  2) 单 symbol 失败隔离：模拟铝 AH=F 404 → unavailable_symbols=["AH=F"]，整体 partial 不阻断。
  3) 全失败降级：所有 symbol 404 → collect 返回 None；main() 首跑写 unavailable（降级闭环）。
"""
import os
import sys
import json
import tempfile
from unittest.mock import patch

# 将「核心代码」加入 path，使 import fetcher_base / fetch_commodity_yahoo 可用
_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import requests  # noqa: E402
from fetcher_base import Status  # noqa: E402
import fetch_commodity_yahoo as ymod  # noqa: E402
from fetch_commodity_yahoo import CommodityYahooFetcher  # noqa: E402

ymod.CommodityYahooFetcher.rate_interval = 0.0  # 测试不 sleep

_FIXTURE = os.path.join(_HERE, "fixtures", "yahoo_chart_sample.json")
with open(_FIXTURE, encoding="utf-8") as _fh:
    FIXTURE = json.load(_fh)


class FakeResp:
    """极简伪造响应：提供 .text / .status_code / .json()。"""

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def json(self):
        return json.loads(self.text)


def _chart_response(symbol):
    """构造成功 symbol 的 Yahoo chart 响应体（200）。"""
    return FakeResp(
        json.dumps({"chart": {"result": [FIXTURE[symbol]], "error": None}}),
        status_code=200,
    )


def _fake_get(url, **kwargs):
    # url 形如 https://query1.finance.yahoo.com/v8/finance/chart/CL=F
    sym = url.rstrip("/").split("/")[-1]
    if sym == "AH=F":
        return FakeResp(json.dumps(FIXTURE["AH=F"]), status_code=404)
    return _chart_response(sym)


_fails = 0


def check(cond: bool, msg: str) -> None:
    global _fails
    if cond:
        print(f"  PASS: {msg}")
    else:
        _fails += 1
        print(f"  FAIL: {msg}")


def test_normal() -> None:
    print("[test] Yahoo 正常路径（WTI/Brent/Copper 三个 symbol）")
    tmp = tempfile.mkdtemp()
    f = CommodityYahooFetcher(tmp)
    with patch("requests.get") as mock_get:
        mock_get.side_effect = _fake_get
        result = f.collect()

    check(result is not None, "collect 返回非 None")
    check(result.get("status") == Status.OK, "status == ok（无失败 symbol）")
    check(result.get("unavailable_symbols") == [], "unavailable_symbols 为空")

    com = result.get("commodities", {})
    check(set(com.keys()) == {"wti", "brent", "copper"},
          "commodities 含 wti/brent/copper 三键")
    # 价格
    check(com["wti"]["price"] == 79.47, "WTI 价格 == 79.47")
    check(com["brent"]["price"] == 83.12, "Brent 价格 == 83.12")
    check(com["copper"]["price"] == 4.52, "Copper 价格 == 4.52")
    # 单位
    check(com["wti"]["unit"] == "USD/bbl", "WTI 单位 USD/bbl")
    check(com["brent"]["unit"] == "USD/bbl", "Brent 单位 USD/bbl")
    check(com["copper"]["unit"] == "USD/lb", "Copper 单位 USD/lb（美元/磅）")
    # symbol / name / status
    check(com["wti"]["symbol"] == "CL=F" and com["wti"]["name"] == "WTI原油",
          "WTI symbol/name 正确")
    check(com["copper"]["status"] == Status.OK, "Copper 子状态 ok")
    # as_of ISO UTC+Z
    for key in ("wti", "brent", "copper"):
        a = com[key]["as_of"]
        check(a.endswith("Z") and "T" in a, f"{key} as_of 为 ISO UTC+Z ({a})")
    check(result["as_of"].endswith("Z"), "顶层 as_of 为 ISO UTC+Z")

    f.save_json(f.output_file, result)
    with open(os.path.join(tmp, f.output_file), encoding="utf-8") as fh:
        data = json.load(fh)
    check("_schema_version" in data, "落盘含 _schema_version")
    check(data.get("status") == "ok", "落盘含 status=ok")


def test_partial_aluminum() -> None:
    print("[test] Yahoo 单 symbol 失败隔离（模拟铝 AH=F 404）")
    # 注入 AH=F 到 SYMBOLS，模拟架构设计 §3.2 铝 404 场景
    orig_sym = ymod.SYMBOLS
    orig_keys = ymod._SYMBOL_KEYS
    ymod.SYMBOLS = orig_sym + [("AH=F", "铝", "USD/lb")]
    ymod._SYMBOL_KEYS = orig_keys + ["aluminum"]
    try:
        tmp = tempfile.mkdtemp()
        f = CommodityYahooFetcher(tmp)
        with patch("requests.get") as mock_get:
            mock_get.side_effect = _fake_get
            result = f.collect()
    finally:
        ymod.SYMBOLS = orig_sym
        ymod._SYMBOL_KEYS = orig_keys

    check(result is not None, "collect 返回非 None（部分成功不阻断）")
    check(result.get("status") == Status.PARTIAL, "status == partial（部分 symbol 失败）")
    check(result.get("unavailable_symbols") == ["AH=F"],
          "unavailable_symbols == ['AH=F']")
    com = result.get("commodities", {})
    check(set(com.keys()) == {"wti", "brent", "copper"},
          "其余 WTI/Brent/Copper 正常解析（未被铝 404 阻断）")
    check(com["copper"]["unit"] == "USD/lb", "Copper 单位仍为 USD/lb")


def test_all_fail() -> None:
    print("[test] Yahoo 全失败降级（所有 symbol 404 → collect 返回 None）")
    tmp = tempfile.mkdtemp()
    f = CommodityYahooFetcher(tmp)
    with patch("requests.get") as mock_get:
        mock_get.return_value = FakeResp(json.dumps(FIXTURE["AH=F"]), status_code=404)
        result = f.collect()
    check(result is None, "全失败 collect 返回 None（不崩）")


def test_main_degrade_writes_unavailable() -> None:
    print("[test] Yahoo main() 全失败首跑写 unavailable（降级闭环）")
    tmp = tempfile.mkdtemp()
    orig_data_dir = ymod.DATA_DIR
    ymod.DATA_DIR = tmp  # 重定向落盘到临时目录，避免触碰真实 data
    try:
        with patch("requests.get") as mock_get:
            mock_get.return_value = FakeResp(json.dumps(FIXTURE["AH=F"]), status_code=404)
            ymod.main()
        path = os.path.join(tmp, ymod.OUTPUT_FILE)
        check(os.path.exists(path), "全失败首跑生成 commodity_yahoo.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        check(data.get("status") == "unavailable", "降级落盘 status=unavailable")
        check("_schema_version" in data, "降级落盘含 _schema_version")
    finally:
        ymod.DATA_DIR = orig_data_dir


if __name__ == "__main__":
    test_normal()
    test_partial_aluminum()
    test_all_fail()
    test_main_degrade_writes_unavailable()
    print(f"\n断言失败数: {_fails}")
    sys.exit(1 if _fails else 0)
