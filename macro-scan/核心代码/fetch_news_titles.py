#!/usr/bin/env python3
"""
fetch_news_titles.py — 新闻标题预抓取（08-16，开阳地区新闻弹框真实标题）

背景：GDELT GKG events 无 title 字段；DOC API 429 限流；点击时按需抓取（control_server
/news-title）用户反馈"加载慢/超时"。此 fetcher **提前批量抓取** news_geo.json 全部
事件 source_url 的页面 <title>，写 news_titles.json（url→title 映射）——开阳前端
直接读静态文件（秒开、零 API 占用），点击兜底走 /news-title 接口。

增量策略（72h 窗口滚动，事件不断轮换）：
  - 读 news_geo.json events → 去重 URL 集合
  - 读已有 news_titles.json 缓存（不重抓已有）
  - 每轮只抓新增 URL（上限 NEW_MAX=20，并发 4，单 URL 12s 超时）
  - 写回 news_titles.json（保留 72h 内事件的标题）

输出契约：data/news_titles.json
  {"schema_version": "1.0", "fetched_at": "...", "total": N, "titles": {"<url>": "<title>"}}

调度：scheduler.py I120（2h；增量每轮 ~1-2 分钟）
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from fetcher_base import FetcherBase, Status

# ── 配置回退 ────────────────────────────────────────────
_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR", "PROXY_URL"],
    {
        "DATA_DIR": FetcherBase.default_data_dir(),
        "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
    },
)
DATA_DIR = _cfg["DATA_DIR"]
PROXY_URL = _cfg["PROXY_URL"]

NEWS_GEO_FILE = os.path.join(DATA_DIR, "news_geo.json")
OUT_FILE = os.path.join(DATA_DIR, "news_titles.json")
NEW_MAX = 20          # 每轮最多抓新增标题数（增量，防长时间停机后一次抓爆）
CONCURRENCY = 4       # 并发抓取数
TIMEOUT = 12          # 单 URL 超时（秒）
MAX_TITLES = 600      # 缓存上限（72h 窗口事件 ~300，留余量）

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _extract_title(body: bytes) -> str:
    try:
        text = body.decode("utf-8", "ignore")
    except Exception:
        text = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    title = re.sub(r"<[^>]+>", "", m.group(1))
    title = html.unescape(title).strip()
    title = re.sub(r"\s+", " ", title)
    return title[:200]


def _fetch_title(url: str) -> tuple:
    """抓单个 URL 标题（代理）。返回 (url, title)，失败 title=''。"""
    try:
        proxy = urllib.request.ProxyHandler({"http": PROXY_URL, "https": PROXY_URL})
        opener = urllib.request.build_opener(proxy)
        req = urllib.request.Request(url, headers=UA)
        with opener.open(req, timeout=TIMEOUT) as r:
            body = r.read(65536)
        return url, _extract_title(body)
    except Exception:
        return url, ""


def collect() -> dict:
    # 1. 读 news_geo.json 事件 URL
    urls = []
    try:
        with open(NEWS_GEO_FILE, encoding="utf-8") as f:
            d = json.load(f)
        seen = set()
        for e in (d.get("events") or []):
            u = (e.get("source_url") or "").strip()
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
    except Exception:
        pass
    if not urls:
        return {"status": Status.OK, "fetched": 0, "total": 0, "new": 0}

    # 2. 读已有缓存
    titles = {}
    try:
        with open(OUT_FILE, encoding="utf-8") as f:
            old = json.load(f)
        titles = old.get("titles") or {}
    except Exception:
        titles = {}

    # 3. 待抓 = 未缓存的 URL（限 NEW_MAX）
    pending = [u for u in urls if u not in titles][:NEW_MAX]
    new_count = 0
    if pending:
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            for url, title in ex.map(_fetch_title, pending):
                if title:
                    titles[url] = title
                    new_count += 1

    # 4. 裁剪：只保留当前 news_geo 事件 URL（72h 窗口滚动，旧标题清掉）
    keep = {u for u in urls}
    for k in list(titles):
        if k not in keep:
            del titles[k]
    if len(titles) > MAX_TITLES:
        for k in list(titles)[: len(titles) - MAX_TITLES]:
            del titles[k]

    # 5. 落盘（原子写）
    payload = {
        "schema_version": "1.0",
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total": len(urls),
        "covered": len(titles),
        "titles": titles,
    }
    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, OUT_FILE)
    return {"status": Status.OK, "total": len(urls), "fetched": len(pending), "new": new_count, "covered": len(titles)}


if __name__ == "__main__":
    r = collect()
    print(f"[fetch_news_titles] events={r.get('total', 0)} 已覆盖={r.get('covered', 0)} "
          f"本轮抓={r.get('fetched', 0)} 新增标题={r.get('new', 0)}")
