#!/usr/bin/env python3
"""
fetch_hdx.py — 人道 / 危机冲击事件源（HDX，P1）

Humanitarian Data Exchange（HDX，CKAN API，读端点免 token；429 限流无公开次数）。
报告定位：metadata 时间戳非观测值，适合做「冲击事件源」而非时序指标。
本模块以「近 30 天更新的危机/人道数据集数量」构建 crisis_activity_index，
作为全球人道/冲突冲击活跃度的代理信号。

输出契约：data/hdx_risk.json
  {
    "status":                "ok" | "unavailable",
    "crisis_activity_index":  0–100,  # 近30天更新危机数据集数 ×4 封顶
    "datasets_updated_30d":  int,
    "total_searched":        int,
    "recent":                [ {name, title, organization, metadata_modified}, ... ],
    "source":                "HDX CKAN",
    "updated":               as-of
  }
注：本源为「待接 GRV 字段」源：先落盘，下游可经 humanitarian_risk 维度接入 GRV。

降级：拉取 / 解析失败 → status=unavailable；若本地有上次良值则保留、不覆盖、绝不 crash。
网络出口：直连优先，失败回退代理，仍失败降级（HDX 出口实测见交付报告）。
调度：scheduler.py 06:20（不依赖 GRV，落盘即可）。
"""
import os
import json
import datetime

try:
    from optim_config import DATA_DIR, PROXY_URL, HDX_API_BASE, HDX_QUERY
except ImportError:
    _cfg = FetcherBase.load_config_with_fallback(
        ["DATA_DIR", "PROXY_URL", "HDX_API_BASE", "HDX_QUERY"],
        {
            "DATA_DIR": FetcherBase.default_data_dir(),
            "PROXY_URL": ("", "PROXY_URL"),
            "HDX_API_BASE": ("https://data.humdata.org/api/3/action", "HDX_API_BASE"),
            "HDX_QUERY": ("humanitarian OR conflict OR crisis", "HDX_QUERY"),
        },
    )
    DATA_DIR = _cfg["DATA_DIR"]
    PROXY_URL = _cfg["PROXY_URL"]
    HDX_API_BASE = _cfg["HDX_API_BASE"]
    HDX_QUERY = _cfg["HDX_QUERY"]

from fetcher_base import FetcherBase

OUTPUT_FILE = "hdx_risk.json"
RECENT_DAYS = 30


class HdxFetcher(FetcherBase):
    name = "hdx"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0620"

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self.proxies = None

    def _get(self, url, params=None, headers=None, timeout=20):
        r = self.request(url, params=params, headers=headers, timeout=timeout)
        if r is not None:
            return r
        if PROXY_URL:
            self.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            return self.request(url, params=params, headers=headers, timeout=timeout)
        return None

    def collect(self):
        url = f"{HDX_API_BASE}/package_search"
        r = self._get(url, params={"q": HDX_QUERY, "rows": 25,
                                   "sort": "metadata_modified desc"})
        if r is None:
            return {"status": "unavailable", "reason": "unreachable",
                    "source": "HDX CKAN"}
        try:
            d = r.json()
            res = (d.get("result") or {})
            results = res.get("results", []) or []
            now = datetime.datetime.now(datetime.timezone.utc)
            cutoff = now - datetime.timedelta(days=RECENT_DAYS)
            recent = []
            for ds in results:
                mm = ds.get("metadata_modified")
                if not mm:
                    continue
                try:
                    dt = datetime.datetime.fromisoformat(mm.replace("Z", "+00:00"))
                except Exception:
                    continue
                if dt >= cutoff:
                    recent.append({
                        "name": ds.get("name"),
                        "title": ds.get("title"),
                        "organization": (ds.get("organization") or {}).get("name"),
                        "metadata_modified": mm,
                    })
            # 每有 1 个近30天更新的危机数据集 +4 分，封顶 100
            activity = min(100, len(recent) * 4)
            return {
                "status": "ok",
                "crisis_activity_index": activity,
                "datasets_updated_30d": len(recent),
                "total_searched": len(results),
                "recent": recent[:10],
                "source": "HDX CKAN",
            }
        except Exception as e:
            self.logger.error("[hdx] 解析失败: %s", e)
            return {"status": "unavailable", "reason": "parse_error",
                    "source": "HDX CKAN"}

def main():
    fetcher = HdxFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[hdx] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == "ok":
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[hdx] 完成 status=ok，activity={result.get('crisis_activity_index')}"
              f"，updated_30d={result.get('datasets_updated_30d')}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[hdx] 降级 unavailable，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, result)
            print("[hdx] 降级 unavailable，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
