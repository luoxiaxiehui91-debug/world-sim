#!/usr/bin/env python3
"""离线验收：fetch_bdi.BdiFetcher（本地 CSV 读取，不触网）。

运行：python tests/test_fetch_bdi.py
退出码：0 = 全 PASS，1 = 存在失败断言。

v3.6.1 起 fetcher 改为读取本地预置 CSV（data/bdi_history.csv），不再触网。
覆盖：
  1) 正常路径：Stooq 格式 CSV（Date,Open,High,Low,Close）→ collect 返回 ok，
     bdi_index=末行 Close，series 非空，落盘含 _schema_version+status。
  2) 列识别：Date,Value 两列格式 → 同样正确取末值。
  3) 缺失 CSV：collect 返回 None（不崩，保留旧值）。
"""
import os
import sys
import json
import tempfile

# 将「核心代码」加入 path，使 import fetcher_base / fetch_bdi 可用
_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from fetcher_base import Status  # noqa: E402
from fetch_bdi import BdiFetcher  # noqa: E402


# Stooq 日线 CSV（末行 Close = 1923.8）
SAMPLE_STOOQ_CSV = """Date,Open,High,Low,Close,Volume
2026-07-20,1800.0,1850.0,1780.0,1820.5,000
2026-07-21,1820.0,1880.0,1810.0,1860.3,000
2026-07-22,1860.0,1900.0,1840.0,1888.7,000
2026-07-23,1880.0,1920.0,1870.0,1905.2,000
2026-07-24,1900.0,1950.0,1890.0,1923.8,000
"""

# 极简 Date,Value 格式（末值 = 1500.0）
SAMPLE_VALUE_CSV = """Date,Value
2026-07-22,1400.0
2026-07-23,1450.0
2026-07-24,1500.0
"""


_fails = 0


def check(cond: bool, msg: str) -> None:
    global _fails
    if cond:
        print(f"  PASS: {msg}")
    else:
        _fails += 1
        print(f"  FAIL: {msg}")


def test_normal_stooq() -> None:
    print("[test] BDI 正常路径（Stooq 格式 CSV，取 Close）")
    tmp = tempfile.mkdtemp()
    csv_path = os.path.join(tmp, "bdi_history.csv")
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write(SAMPLE_STOOQ_CSV)
    f = BdiFetcher(tmp)
    result = f.collect()

    check(result is not None, "collect 返回非 None")
    check(result.get("status") == Status.OK, "status == ok")
    check(isinstance(result.get("bdi_index"), float), "bdi_index 是 float")
    check(result["bdi_index"] == 1923.8, "bdi_index == 末行 Close (1923.8)")
    check(isinstance(result.get("series"), list) and len(result["series"]) > 0,
          "series 非空")
    check(all(set(p.keys()) == {"date", "value"} for p in result["series"]),
          "series 每项含 date+value")
    check(result.get("source") == "local_csv", "source == local_csv")

    f.save_json(f.output_file, result)
    with open(os.path.join(tmp, f.output_file), encoding="utf-8") as fh:
        data = json.load(fh)
    check("_schema_version" in data, "落盘含 _schema_version")
    check(data.get("status") == "ok", "落盘含 status=ok")


def test_value_format() -> None:
    print("[test] BDI 列识别（Date,Value 两列）")
    tmp = tempfile.mkdtemp()
    csv_path = os.path.join(tmp, "bdi_history.csv")
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write(SAMPLE_VALUE_CSV)
    f = BdiFetcher(tmp)
    result = f.collect()
    check(result is not None, "collect 返回非 None")
    check(result["bdi_index"] == 1500.0, "bdi_index == 末行 Value (1500.0)")
    check(len(result["series"]) == 3, "series 含 3 点")


def test_missing_csv() -> None:
    print("[test] BDI 缺失 CSV（返回 None，不崩）")
    tmp = tempfile.mkdtemp()  # 无 bdi_history.csv
    f = BdiFetcher(tmp)
    result = f.collect()
    check(result is None, "缺失 CSV 时 collect 返回 None（不崩）")


if __name__ == "__main__":
    test_normal_stooq()
    test_value_format()
    test_missing_csv()
    print(f"\n断言失败数: {_fails}")
    sys.exit(1 if _fails else 0)
