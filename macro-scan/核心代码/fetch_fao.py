#!/usr/bin/env python3
"""
fetch_fao.py — FAO 粮食价格指数（Food Price Index，FAO 源）

通过 FAO 世界粮食形势页定位**版本化** CSV（端点需滚动 sfvrsn token），
下载后解析最新月 FFPI 与 5 个子指数（实测无 Fish）。

实现要点（详见架构设计 §1.2 难点 B）：
  - 复用 FetcherBase：request/save_json/load_previous_good/load_config_with_fallback。
  - _resolve_csv_url()：GET HTML 页 → 正则提取 `food_price_indices_data.csv?sfvrsn=<token>`
    的完整 URL；提取失败则复用上次成功 token（持久化到 data/.fao_sfvrsn）。
  - _parse_csv(text)：跳过前 2 行元数据、第 3 行表头、第 4 行空行；第 5 行起数据，取末行。
  - 默认 ok-only（_is_good 不覆写）。
  - 失败 / 解析失败 / 空 CSV → collect 返回 None，不抛、不阻断调度。

输出契约：data/fao_food_price.json
  {
    "status":                 "ok",
    "fao_food_price_index":   float,
    "sub_indices": {
        "meat":          float,
        "dairy":         float,
        "cereals":       float,
        "vegetable_oils":float,
        "sugar":         float
    },
    "source":                 "fao",
    "updated":                as-of,
    "_schema_version":        "1.0"
  }

调度：scheduler.py 09:25（每月 1 日，dom=1）。feeds_grv=False，仅落盘供下游消费。
"""
import os
import re
import time
import logging

import requests
from fetcher_base import FetcherBase, Status

# ── 配置回退（统一取代重复 ImportError 块）────────────────────
_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR", "PROXY_URL"],
    {
        "DATA_DIR": FetcherBase.default_data_dir(),
        "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
    },
)
DATA_DIR = _cfg["DATA_DIR"]
PROXY_URL = _cfg["PROXY_URL"]

OUTPUT_FILE = "fao_food_price.json"
PAGE_URL = "https://www.fao.org/worldfoodsituation/foodpricesindex/en/"
SFVRSN_FILE = ".fao_sfvrsn"        # 持久化上次成功 token，兜底复用
CSV_BASE = "https://www.fao.org/worldfoodsituation/foodpricesindex/"

# 实测 CSV 列索引：Date=0, Food Price Index=1, Meat=2, Dairy=3, Cereals=4, Oils=5, Sugar=6
SUB_INDEX_KEYS = ("meat", "dairy", "cereals", "vegetable_oils", "sugar")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
}


class FaoFetcher(FetcherBase):
    """FAO 粮食价格指数采集器：定位版本化 CSV 并解析最新月。"""

    name = "fao"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0925"

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        # 直连优先；直连失败再回退代理（与 fetch_energy/fetch_hdx 的 _get 模式一致）
        self.proxies = None

    # ── 网络出口：直连优先，失败回退代理 ────────────────────────
    def _get(self, url, params=None, headers=None, timeout=20):
        r = self.request(url, params=params, headers=headers, timeout=timeout)
        if r is not None:
            return r
        if PROXY_URL:
            self.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            return self.request(url, params=params, headers=headers, timeout=timeout)
        return None

    # ── 版本化 CSV URL 解析 + token 兜底 ──────────────────────
    def _resolve_csv_url(self) -> str | None:
        """GET HTML 页正则提取版本化 CSV URL；失败则用上次 token 兜底。"""
        r = self._get(PAGE_URL, headers=HEADERS)
        if r is not None:
            html = r.text or ""
            m = re.search(
                r'href=["\']([^"\']*food_price_indices_data\.csv\?sfvrsn=[^"\']+)["\']',
                html, re.IGNORECASE,
            )
            if m:
                href = m.group(1)
                url = href if href.startswith("http") else \
                    ("https://www.fao.org" + (href if href.startswith("/") else "/" + href))
                self._persist_sfvrsn(url)
                return url
            self.logger.warning("[fao] HTML 页未匹配到 sfvrsn CSV 链接，尝试 token 兜底")
        else:
            self.logger.warning("[fao] 访问 FAO 页面失败，尝试 token 兜底")
        return self._fallback_csv_url()

    def _fallback_csv_url(self) -> str | None:
        token = self._load_sfvrsn()
        if token:
            self.logger.info("[fao] 复用历史 sfvrsn token: %s", token)
            return f"{CSV_BASE}food_price_indices_data.csv?sfvrsn={token}"
        return None

    def _persist_sfvrsn(self, url: str) -> None:
        m = re.search(r"sfvrsn=([^&\"'\s]+)", url)
        if not m:
            return
        token = m.group(1)
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(os.path.join(self.data_dir, SFVRSN_FILE), "w", encoding="utf-8") as f:
                f.write(token)
        except Exception as e:
            self.logger.warning("[fao] 持久化 sfvrsn 失败: %s", e)

    def _load_sfvrsn(self) -> str | None:
        path = os.path.join(self.data_dir, SFVRSN_FILE)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip() or None
        except Exception:
            return None

    # ── CSV 解析 ──────────────────────────────────────────────
    def _parse_csv(self, text: str) -> dict | None:
        """跳过前 2 行元数据、第 3 行表头、第 4 行空行；第 5 行起数据，取末行。

        返回 {fao_food_price_index, sub_indices} 或 None。
        """
        if not text or not text.strip():
            return None
        data_lines = []
        for ln in text.splitlines():
            s = ln.strip()
            if not s:
                continue
            # 跳过标题行（FAO...）与表头行（Date,...）
            if s.startswith("FAO") or s.startswith("Date,"):
                continue
            # 仅保留 YYYY-MM 开头的数据行
            if re.match(r"^\d{4}-\d{2},", s):
                data_lines.append(s)
        if not data_lines:
            self.logger.warning("[fao] CSV 无有效数据行")
            return None
        parts = [p.strip() for p in data_lines[-1].split(",")]
        try:
            fao_food_price_index = float(parts[1])
            sub_indices = {key: float(parts[2 + i]) for i, key in enumerate(SUB_INDEX_KEYS)}
        except (IndexError, ValueError) as e:
            self.logger.warning("[fao] CSV 字段解析失败: %s", e)
            return None
        return {
            "fao_food_price_index": fao_food_price_index,
            "sub_indices": sub_indices,
        }

    # ── 采集入口 ──────────────────────────────────────────────
    def collect(self):
        url = self._resolve_csv_url()
        if not url:
            self.logger.warning("[fao] 无法解析 CSV URL 且无历史 token，降级")
            return None
        r = self._get(url, headers=HEADERS)
        if r is None:
            self.logger.warning("[fao] 下载 FAO CSV 失败，降级")
            return None
        text = r.text or ""
        if not text.strip():
            self.logger.warning("[fao] FAO CSV 为空，降级")
            return None
        parsed = self._parse_csv(text)
        if parsed is None:
            self.logger.warning("[fao] FAO CSV 解析失败，降级")
            return None
        return {
            "status": Status.OK,
            "fao_food_price_index": parsed["fao_food_price_index"],
            "sub_indices": parsed["sub_indices"],
            "source": "fao",
        }

    # _is_good 采用基类默认 ok-only（status == "ok"），无需覆写。


def main():
    fetcher = FaoFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[fao] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == Status.OK:
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[fao] 完成 status=ok，ffpi={result.get('fao_food_price_index')}，"
              f"子指数={list(result.get('sub_indices', {}).keys())}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[fao] 降级，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, result)
            print("[fao] 降级，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
