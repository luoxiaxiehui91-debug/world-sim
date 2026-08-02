#!/usr/bin/env python3
"""
fetch_china_meso.py — 中国中观指标（AkShare）

数据源：
  - 二手房价格指数：akshare.macro_china_new_house_price()
      列：「二手住宅价格指数-同比」/「-环比」
  - 制造业 PMI：akshare.macro_china_pmi_yearly()
      最新一行，取「制造业-指数」列
  - 企业景气指数：akshare.macro_china_enterprise_boom_index()
      最新一行，取「景气指数」列（备选，PMI 不可达时补充）

输出契约：data/china_meso.json
  {
    "status":     "ok" | "partial" | "unavailable",
    "source":     "AkShare",
    "as_of":      ISO8601 UTC,
    "indicators": {
      "second_hand_hpi_yoy":  {"name","value","unit","date","status"},
      "second_hand_hpi_mom":  {"name","value","unit","date","status"},
      "pmi_manufacturing":    {"name","value","unit","date","status"},
      "enterprise_boom":      {"name","value","unit","date","status"}
    },
    "_schema_version": "1.0",
    "updated": ...
  }

调度：scheduler.py 09:30（每月 1 日，dom=1）。feeds_grv=False。
"""
import datetime
import logging
from datetime import timezone

from fetcher_base import FetcherBase, Status

_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR", "PROXY_URL"],
    {
        "DATA_DIR": FetcherBase.default_data_dir(),
        "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
    },
)
DATA_DIR = _cfg["DATA_DIR"]

OUTPUT_FILE = "china_meso.json"

logger = logging.getLogger("fetcher.china_meso")


def _now_utc() -> str:
    return datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_second_hand_hpi() -> dict:
    """返回 {yoy: {value, date}, mom: {value, date}} 或抛异常。"""
    import akshare as ak
    df = ak.macro_china_new_house_price()
    # 列名：「日期」「新建住宅价格指数-同比」「新建住宅价格指数-环比」
    #       「二手住宅价格指数-同比」「二手住宅价格指数-环比」
    # 取最后一行非空
    df = df.dropna(subset=["二手住宅价格指数-同比", "二手住宅价格指数-环比"])
    if df.empty:
        raise ValueError("macro_china_new_house_price 返回空 DataFrame")
    row = df.iloc[-1]
    date_val = str(row.get("日期", ""))
    return {
        "yoy": {"value": float(row["二手住宅价格指数-同比"]), "date": date_val},
        "mom": {"value": float(row["二手住宅价格指数-环比"]), "date": date_val},
    }


def _fetch_pmi() -> dict:
    """返回 {value, date} 或抛异常。
    macro_china_pmi_yearly 列：['商品', '日期', '今值', '预测值', '前值']
    按 商品=='中国官方制造业PMI' 过滤，取最新行（按日期倒序取 iloc[0]）。
    """
    import akshare as ak
    df = ak.macro_china_pmi_yearly()
    # 过滤制造业PMI行
    if "商品" in df.columns:
        mfg = df[df["商品"].str.contains("制造业PMI", na=False)].copy()
    else:
        mfg = df.copy()
    mfg = mfg.dropna(subset=["今值"])
    if mfg.empty:
        raise ValueError(f"macro_china_pmi_yearly 无制造业PMI数据，列: {list(df.columns)}")
    # 按日期排序取最新
    if "日期" in mfg.columns:
        mfg = mfg.sort_values("日期", ascending=False)
    row = mfg.iloc[0]
    return {"value": float(row["今值"]), "date": str(row.get("日期", ""))}


def _fetch_enterprise_boom() -> dict:
    """返回 {value, date} 或抛异常。
    macro_china_enterprise_boom_index 列：['季度', '企业景气指数-指数', ...]
    数据按季度倒序（最新在 iloc[0]）。
    """
    import akshare as ak
    df = ak.macro_china_enterprise_boom_index()
    col = "企业景气指数-指数"
    if col not in df.columns:
        raise ValueError(f"macro_china_enterprise_boom_index 缺列 {col}，实际列: {list(df.columns)}")
    df_clean = df.dropna(subset=[col])
    if df_clean.empty:
        raise ValueError("macro_china_enterprise_boom_index 全为空")
    row = df_clean.iloc[0]  # 最新一行在头部
    date_col = df.columns[0]  # '季度'
    return {"value": float(row[col]), "date": str(row.get(date_col, ""))}


def _make_indicator(name, unit, result_dict, key) -> dict:
    """把抓取结果转成标准 indicator 结构，出错时标 unavailable。"""
    if result_dict is None:
        return {"name": name, "unit": unit, "value": None, "date": None, "status": Status.UNAVAILABLE}
    return {
        "name": name,
        "unit": unit,
        "value": result_dict.get("value"),
        "date": result_dict.get("date", ""),
        "status": Status.OK,
    }


class ChinaMesoFetcher(FetcherBase):
    name = "china_meso"
    rate_interval = 0.5
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0930"

    def _is_good(self, data: dict) -> bool:
        return data.get("status") in (Status.OK, Status.PARTIAL)

    def collect(self) -> dict | None:
        as_of = _now_utc()
        indicators = {}
        ok_count = 0
        fail_count = 0

        # ── 二手房价格指数 ──────────────────────────────────────
        try:
            hpi = _fetch_second_hand_hpi()
            indicators["second_hand_hpi_yoy"] = _make_indicator(
                "二手住宅价格指数-同比", "%", hpi["yoy"], "yoy")
            indicators["second_hand_hpi_mom"] = _make_indicator(
                "二手住宅价格指数-环比", "%", hpi["mom"], "mom")
            ok_count += 2
        except Exception as e:
            logger.warning(f"[china_meso] 二手房价格指数失败: {e}")
            indicators["second_hand_hpi_yoy"] = _make_indicator("二手住宅价格指数-同比", "%", None, None)
            indicators["second_hand_hpi_mom"] = _make_indicator("二手住宅价格指数-环比", "%", None, None)
            fail_count += 2

        # ── 制造业 PMI ──────────────────────────────────────────
        try:
            pmi = _fetch_pmi()
            indicators["pmi_manufacturing"] = _make_indicator(
                "制造业PMI", "指数", pmi, "pmi")
            ok_count += 1
        except Exception as e:
            logger.warning(f"[china_meso] PMI 失败: {e}")
            indicators["pmi_manufacturing"] = _make_indicator("制造业PMI", "指数", None, None)
            fail_count += 1

        # ── 企业景气指数 ────────────────────────────────────────
        try:
            boom = _fetch_enterprise_boom()
            indicators["enterprise_boom"] = _make_indicator(
                "企业景气指数", "指数", boom, "boom")
            ok_count += 1
        except Exception as e:
            logger.warning(f"[china_meso] 企业景气指数失败: {e}")
            indicators["enterprise_boom"] = _make_indicator("企业景气指数", "指数", None, None)
            fail_count += 1

        total = ok_count + fail_count
        if ok_count == 0:
            status = Status.UNAVAILABLE
        elif fail_count == 0:
            status = Status.OK
        else:
            status = Status.PARTIAL

        return {
            "status": status,
            "source": "AkShare",
            "as_of": as_of,
            "indicators": indicators,
            "ok_count": ok_count,
            "fail_count": fail_count,
        }


def main():
    import os
    fetcher = ChinaMesoFetcher(DATA_DIR)
    result = fetcher.run()
    if result is None:
        print("[china_meso] collect 返回空，保留旧值")
        return
    if result.get("status") in (Status.OK, Status.PARTIAL):
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[china_meso] 完成 status={result['status']} "
              f"ok={result.get('ok_count')} fail={result.get('fail_count')}")
        for k, v in result.get("indicators", {}).items():
            print(f"  {k}: {v.get('value')} ({v.get('date')}) [{v.get('status')}]")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[china_meso] 全失败，保留上次良值")
        else:
            fetcher.save_json(OUTPUT_FILE, result)
            print("[china_meso] 全失败，无历史良值，写 unavailable")


if __name__ == "__main__":
    main()
