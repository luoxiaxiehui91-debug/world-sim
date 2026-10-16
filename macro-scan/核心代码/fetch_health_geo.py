#!/usr/bin/env python3
"""
fetch_health_geo.py — GDELT GKG 卫生事件地理提取（开阳 health 卫生监视图层）

从 GDELT 2.0 GKG 增量（27 列 .gkg.csv.zip，V1Locations 含坐标）过滤卫生关键词，
提取带地理坐标的卫生事件（疫情/疾病爆发报道），落盘 health_geo.json。

数据源：GDELT 2.0（免费无 key，http://data.gdeltproject.org/gdeltv2/）
  - 每次拉「上次已处理 slot → 当前」之间的全部 15 分钟 slot（I60 时最多 4 个，
    每个约 2-4MB；卫生关键词过滤后保留量极小）
  - V1Locations 格式：`Count#FullName#CountryCode#ADM1Code#Lat#Lon#FID;...`（# 分列、; 分位置）
  - 卫生关键词用「爆发级」词表（outbreak/epidemic/pandemic + 具体疾病），
    避免 disease/health 泛词噪声（pandemic loan fraud 类误报实测存在）

输出契约：data/health_geo.json
  {
    "status": "ok",
    "source": "GDELT 2.0 GKG (health keyword filter)",
    "as_of": "2026-08-15T01:30:00Z",
    "scope": "global",
    "schema_version": "1.0",
    "events_count": 12,
    "events": [
      {"doc": "https://...", "date": "20260815013000", "lat": 38.8951, "lng": -77.0364,
       "loc_name": "White House, District Of Columbia, United States",
       "keywords": ["outbreak"], "title_hint": ""}
    ]
  }

调度：scheduler.py I60（卫生事件低频，60 分钟粒度足够；与 news_geo 同源同节奏）。
语义：卫生事件活动可视化（非风险评分）——前端 value null + 中性标签。
"""
import datetime
import html
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile

from fetcher_base import FetcherBase, Status

# ── 配置回退 ────────────────────────────────────────────
_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR", "PROXY_URL"],
    {
        "DATA_DIR": FetcherBase.default_data_dir(),
        "PROXY_URL": ("", "PROXY_URL"),
    },
)
DATA_DIR = _cfg["DATA_DIR"]
PROXY_URL = _cfg["PROXY_URL"]

OUTPUT_FILE = "health_geo.json"
RAW_FILE    = "health_geo_raw.json"  # v1.1.1：明细持久化（合并用），展示文件只存聚合
GKG_BASE = "http://data.gdeltproject.org/gdeltv2/"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

# 08-16 v3：标题抓取参数（绕开 DOC API 429——直接抓 doc URL 页面 <title>）
TITLE_BATCH = 20            # 每轮抓缺 title 事件数（I60 增量，268 存量 ≈ 14 轮）
TITLE_CONCURRENCY = 4       # 并发抓取
TITLE_FETCH_TIMEOUT = 12    # 单 URL 超时（s）
# 卫生关键词（爆发级，降噪）：全小写匹配
HEALTH_KEYWORDS = (
    "outbreak", "epidemic", "pandemic", "cholera", "ebola", "mpox", "monkeypox",
    "zika", "bird flu", "h5n1", "marburg", "lassa", "dengue", "polio", "measles",
    "cyclosporiasis", "whooping cough", "pertussis",
)
# 明确排除（实测噪声）：pandemic loan / pandemic relief 是金融诈骗不是卫生事件
EXCLUDE_SUBSTR = ("pandemic loan", "pandemic relief", "pandemic fraud", "pandemic stimulus")
# 保留最近 72h 事件（事件低频，累积窗口长一点）
MAX_EVENT_AGE_HOURS = 72

# 10-16（CHG-20261016T120806）：聚合页 / tag 页不是「事件」——目录页会把一个 tag 或
# 栏目下所有报道算成一条卫生事件（实测 3 条：newsroomamerica.com/tag/…、
# grandrapidsmn.com/around_the_web/…）。⚠️ 不含 "/category/"：freemalaysiatoday 等站
# 的分类路径下是真实文章，误剔会丢真事件。
AGGREGATOR_PATH_MARKS = ("/tag/", "/tags/", "/topics/", "around_the_web", "/author/")

# 10-16：关键词左边界约束。子串巧合会把非疫情报道混入——实测
# snowtown-james-vlassakis-serial-killer-parole-… 含 lassa ⇒ 杀手假释新闻当成拉沙热。
# 规则：关键词之前不得是字母或数字（- / _ / . / 空格 / 行首均放行），后随任意字符
# ⇒ 保住 outbreaks 复数、bird-flu 连字符、h5n1-2026 等同根写法。
_KW_RE = {k: re.compile(r"(?<![a-z0-9])" + re.escape(k)) for k in HEALTH_KEYWORDS}


def _story_slug(url: str) -> str:
    """故事身份 = URL path（剔除日期段，保留故事 ID 段）。

    同一篇通稿被几十家站点原样转载时 doc URL 各异、path slug 相同
    （实测 942 条 raw 中 406 条属 40 个故事的转载）⇒ 以 slug 作为
    「一个事件」的单位：否则同一事件在地图上炸成多点、count 虚高成转载数。

    只剔「年(19xx/20xx)+相邻月/日」与 ISO 日期段（YYYY-MM-DD）；
    **不剔纯数字故事 ID**（如 story/9367686/…、…/74123159），避免不同故事被误合。
    """
    try:
        segs = [s for s in (urllib.parse.urlsplit(url or "").path or "").split("/") if s]
    except Exception:
        return (url or "").lower()
    out, i = [], 0
    while i < len(segs):
        s = segs[i]
        if re.fullmatch(r"(?:19|20)\d{2}", s):
            j = i + 1
            if j < len(segs) and re.fullmatch(r"\d{1,2}", segs[j]):
                j += 1
                if j < len(segs) and re.fullmatch(r"\d{1,2}", segs[j]):
                    j += 1
            i = j
            continue
        if re.fullmatch(r"(?:19|20)\d{2}-\d{1,2}-\d{1,2}", s):
            i += 1
            continue
        out.append(s)
        i += 1
    return "/".join(out).lower()


def _is_aggregator_page(url: str) -> bool:
    """聚合页 / tag 页 / 栏目目录页判定（非文章，不应计为事件）。"""
    try:
        p = urllib.parse.urlsplit(url or "").path.lower()
    except Exception:
        return False
    return any(m in p for m in AGGREGATOR_PATH_MARKS)
STATE_FILE = "health_geo_state.json"  # 记录上次处理 slot
# 10-13（CHG-20261013T080315）：标题中译——复用 fetch_news_titles 同一条
# usage=translate_titles 配置链（模型/平台/密钥控制台可改），不新增硬编码模型名。
ZH_CACHE_FILE = "health_titles_zh.json"  # doc URL -> 中文标题缓存（避免每轮重翻）
ZH_BATCH = 30            # 每轮最多翻译条数（I60 实测每轮新增 7~18 条，30 留余量）
ZH_CACHE_MAX = 2000      # 缓存上限（FIFO 淘汰）


class HealthGeoFetcher(FetcherBase):
    """GDELT GKG 卫生事件地理提取器。"""

    name = "health_geo"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "I60"  # 60 分钟（卫生事件低频）

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self.proxies = None
        self.state_path = os.path.join(data_dir, STATE_FILE)
        self.events_path = os.path.join(data_dir, OUTPUT_FILE)
        self.zh_cache_path = os.path.join(data_dir, ZH_CACHE_FILE)

    # ── 网络出口：直连优先，失败回退代理 ────────────────────────
    def _download(self, url, timeout=60):
        req = urllib.request.Request(url, headers=UA)
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
            return r.read()
        except Exception:
            if PROXY_URL:
                proxy = urllib.request.ProxyHandler(
                    {"http": PROXY_URL, "https": PROXY_URL})
                opener = urllib.request.build_opener(proxy)
                try:
                    r = opener.open(req, timeout=timeout)
                    return r.read()
                except Exception:
                    return None
            return None

    # ── GKG slot 解析 ────────────────────────────────────────
    def _parse_slot(self, data):
        """解析单个 GKG zip → 卫生事件列表（含坐标）。"""
        events = []
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            text = z.read(z.namelist()[0]).decode("utf-8", "ignore")
        except Exception:
            return events
        for ln in text.splitlines():
            cols = ln.split("\t")
            if len(cols) < 25:
                continue
            if _is_aggregator_page(cols[4]):
                continue  # 目录页 / tag 页不是事件
            hay = (self._url_content(cols[4]) + " " + cols[11] + " " + cols[24]).lower()
            hits = [k for k in HEALTH_KEYWORDS if _KW_RE[k].search(hay)]
            if hits:
                if any(x in hay for x in EXCLUDE_SUBSTR):
                    continue
                loc = self._first_location(cols[9])
                if loc is None:
                    continue
                kw = sorted(hits)
                events.append({
                    "doc": cols[4],
                    "date": cols[1],
                    "lat": round(loc[1], 4),
                    "lng": round(loc[2], 4),
                    "loc_name": loc[0],
                    "keywords": kw,
                    # 08-16 补充：来源媒体域名（GKG cols[3] SourceCommonName，
                    # 实测确认；GKG 2.0 CSV 无标题列，媒体名是"新闻关联"的最佳可用信号）
                    "source_media": (cols[3] or "").strip() if len(cols) > 3 else "",
                })
        return events

    @staticmethod
    def _url_content(url: str) -> str:
        """URL 仅保留 path+query（剔除域名段）后参与关键词匹配。

        域名是站点标识、与事件内容无关（如 sentinelassam.com 含子串 'lassa'），
        并入 haystack 会引入域名碰撞面；path/query 是文章标识（含真事件 slug），保留。
        2026-10-13 修复；解析异常时回退原串（保守保留）。
        """
        try:
            sp = urllib.parse.urlsplit(url or "")
            if sp.netloc:
                return (sp.path or "") + " " + (sp.query or "")
        except Exception:
            pass
        return url or ""

    @staticmethod
    def _first_location(v1locs):
        """V1Locations → (name, lat, lon)；无合法坐标返回 None。"""
        if not v1locs:
            return None
        for part in v1locs.split(";"):
            f = part.split("#")
            if len(f) >= 6:
                try:
                    lat, lon = float(f[4]), float(f[5])
                except (ValueError, TypeError):
                    continue
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return (f[1] if len(f) > 1 else "", lat, lon)
        return None

    # ── 状态管理 ─────────────────────────────────────────────
    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_slot": None}

    def _save_state(self, last_slot):
        try:
            _tmp_177 = self.state_path + ".tmp"
            with open(_tmp_177, "w", encoding="utf-8") as f:
                json.dump({"last_slot": last_slot}, f)
            os.replace(_tmp_177, self.state_path)
        except Exception as e:
            self.logger.warning("[health_geo] state 落盘失败: %s", e)

    # ── 采集入口 ─────────────────────────────────────────────
    def collect(self):
        now = datetime.datetime.utcnow()
        # 08-16 v3：标题改抓 doc URL 页面 <title>（绕开 DOC API 429——NAS IP 被限流
        # 已持续 >7h；直接抓具体报道页面标题与 news_titles 同一已验证机制，走代理）
        # 对齐 15 分钟粒度，构造当前 slot
        cur_slot = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        state = self._load_state()
        last_slot = state.get("last_slot")
        # 回退窗口：无 state 时拉最近 8 slot（2h）
        slots = []
        if last_slot:
            t = datetime.datetime.strptime(last_slot, "%Y%m%d%H%M%S")
            while t < cur_slot:
                t += datetime.timedelta(minutes=15)
                slots.append(t)
        else:
            for m in range(0, 120, 15):
                slots.append(cur_slot - datetime.timedelta(minutes=m))
            slots.reverse()
        if not slots:
            self.logger.info("[health_geo] 无新 slot（已是最新）")
            # 08-16：无新事件也走回填 + 落盘（历史事件补 source_media / title）
            events = self._backfill_source_media(self._load_events())
            events = self._backfill_titles(events, self._fetch_pending_titles(events))
            events = self._backfill_title_zh(events, self._translate_pending(events))
            as_of = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            events = self._persist(events, as_of)
            return {"status": Status.OK, "new_events": 0, "slots_checked": 0, "events": events}

        new_events = []
        checked = 0
        for s in slots[-8:]:  # 最多拉 8 slot（2h），防长时间停机后一次拉爆
            url = f"{GKG_BASE}{s.strftime('%Y%m%d%H%M%S')}.gkg.csv.zip"
            data = self._download(url)
            checked += 1
            if data:
                parsed = self._parse_slot(data)
                new_events += parsed
                self.logger.info("[health_geo] slot %s: %d 条卫生事件",
                                 s.strftime("%H%M"), len(parsed))
            else:
                self.logger.warning("[health_geo] slot %s 下载失败", s.strftime("%H%M"))
        # 去重 + 合并历史（保留 72h）+ 标题回填（抓 doc URL 页面 <title>）
        events = self._merge_events(new_events)
        events = self._backfill_titles(events, self._fetch_pending_titles(events))
        events = self._backfill_title_zh(events, self._translate_pending(events))
        self._save_state(cur_slot.strftime("%Y%m%d%H%M%S"))
        as_of = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        events = self._persist(events, as_of)
        return {"status": Status.OK, "new_events": len(new_events), "slots_checked": checked, "events": events}

    # ── 合并/持久化 ──────────────────────────────────────────
    def _fetch_doc_titles(self):
        """⚠ 废弃（08-16 v3）：DOC API 对 NAS 出口 IP 持续 429（>7h 实测），
        标题改抓 doc URL 页面 <title>（_fetch_pending_titles，走代理，与
        news_titles 同一已验证机制）。此函数保留仅为兼容引用检查，不再调用。"""
        return {}

    def _extract_title(self, body: bytes) -> str:
        """从 HTML 提取 <title>（正则 + 实体解码 + 截断）。"""
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

    def _fetch_one_title(self, url: str) -> tuple:
        """抓单个 doc URL 页面标题（代理，12s 超时，只读 64KB）。"""
        try:
            req = urllib.request.Request(url, headers=UA)
            proxy = urllib.request.ProxyHandler({"http": PROXY_URL, "https": PROXY_URL})
            opener = urllib.request.build_opener(proxy)
            with opener.open(req, timeout=TITLE_FETCH_TIMEOUT) as r:
                body = r.read(65536)
            return url, self._extract_title(body)
        except Exception:
            return url, ""

    def _fetch_pending_titles(self, events):
        """抓缺 title 事件的 doc URL 页面标题（每轮 TITLE_BATCH 个，并发 4）。
        GKG 无标题列 + DOC API 429 → 直接抓具体报道页面 <title>（08-16 v3）。"""
        from concurrent.futures import ThreadPoolExecutor
        pending = [
            (e.get("doc") or "").strip()
            for e in events
            if not e.get("title") and (e.get("doc") or "").strip()
        ]
        # 去重 + 限批
        seen, urls = set(), []
        for u in pending:
            if u not in seen:
                seen.add(u)
                urls.append(u)
        urls = urls[:TITLE_BATCH]
        out = {}
        if urls:
            with ThreadPoolExecutor(max_workers=TITLE_CONCURRENCY) as ex:
                for url, title in ex.map(self._fetch_one_title, urls):
                    if title:
                        out[url] = title
            if out:
                self.logger.info("[health_geo] 抓取标题 %d/%d", len(out), len(urls))
        return out

    def _backfill_titles(self, events, title_map):
        """08-16：事件补新闻标题（DOC API url→title 映射匹配）。原地修改并返回。"""
        for e in events:
            if not e.get("title") and e.get("doc"):
                t = title_map.get(e["doc"].strip())
                if t:
                    e["title"] = t
        return events

    def _load_zh_cache(self):
        """10-13：中文标题缓存（doc URL -> 中文）。读失败视为空（不阻塞主流程）。"""
        try:
            with open(self.zh_cache_path, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save_zh_cache(self, cache):
        """10-13：缓存落盘（原子写 + FIFO 淘汰）。失败仅告警，不阻塞。"""
        try:
            if len(cache) > ZH_CACHE_MAX:
                for k in list(cache)[: len(cache) - ZH_CACHE_MAX]:
                    cache.pop(k, None)
            _tmp_zh = self.zh_cache_path + ".tmp"
            with open(_tmp_zh, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
            os.replace(_tmp_zh, self.zh_cache_path)
        except Exception as e:
            self.logger.warning("[health_geo] 中文标题缓存落盘失败: %s", e)

    def _translate_pending(self, events):
        """10-13：英文标题 -> 中文（复用 fetch_news_titles._translate_titles，
        与新闻图层同一条 usage=translate_titles 配置链）。
        只译「有 title 且缓存未命中」的条目，每轮上限 ZH_BATCH；失败保留英文。"""
        cache = self._load_zh_cache()
        todo = {}
        for e in events:
            doc = (e.get("doc") or "").strip()
            title = (e.get("title") or "").strip()
            if doc and title and doc not in cache and doc not in todo:
                todo[doc] = title
            if len(todo) >= ZH_BATCH:
                break
        if not todo:
            return cache
        try:
            from fetch_news_titles import _translate_titles
            zh = _translate_titles(todo) or {}
        except Exception as e:
            self.logger.warning("[health_geo] 中文翻译不可用（保留英文）: %s", str(e)[:80])
            return cache
        if zh:
            cache.update(zh)
            self._save_zh_cache(cache)
            self.logger.info("[health_geo] 标题中译 %d/%d", len(zh), len(todo))
        return cache

    def _backfill_title_zh(self, events, cache):
        """10-13：事件补 title_zh（仅缓存命中才写；缺失则前端回退英文 title）。"""
        for e in events:
            doc = (e.get("doc") or "").strip()
            z = cache.get(doc)
            if z:
                e["title_zh"] = z
        return events

    def _backfill_source_media(self, events):
        """08-16：旧事件补 source_media——历史事件无 cols[3] 原始值，
        从 doc URL 提取域名（urlparse.netloc）作为媒体名兜底。原地修改并返回。"""
        from urllib.parse import urlparse
        for e in events:
            if not e.get("source_media"):
                try:
                    host = urlparse(e.get("doc", "") or "").netloc
                    e["source_media"] = host or ""
                except Exception:
                    e["source_media"] = ""
        return events

    def _load_events(self):
        """v1.1.1：明细从 RAW_FILE 读（合并源）；无 raw 则回退展示文件（迁移，count 快照保留）。"""
        for name in (RAW_FILE, OUTPUT_FILE):
            try:
                with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
                    d = json.load(f)
                return d.get("events", [])
            except Exception:
                continue
        return []

    def _merge_events(self, new_events):
        old = self._backfill_source_media(self._load_events())
        seen = {e["doc"] for e in old}
        # 10-16：同一故事（path slug）只留一条——通稿被几十家站点原样转载时 doc URL
        # 各异，仅按 doc 去重形同虚设（实测 43% raw 是转载）。
        seen_slug = {_story_slug(e.get("doc") or "") for e in old}
        merged = list(old)
        for e in new_events:
            if e["doc"] in seen:
                continue
            slug = _story_slug(e.get("doc") or "")
            if slug in seen_slug:
                continue
            merged.append(e)
            seen.add(e["doc"])
            seen_slug.add(slug)
        # 保留最近 MAX_EVENT_AGE_HOURS（按 date 前缀截断排序）
        cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=MAX_EVENT_AGE_HOURS)).strftime("%Y%m%d%H%M%S")
        merged = [e for e in merged if e["date"] >= cutoff]
        merged.sort(key=lambda e: e["date"], reverse=True)
        return merged

    def _aggregate_by_location(self, events):
        """v1.1（08-22）：按 loc_name 同城聚合——一城一点 + count + 代表事件。
        明细保留在内存（标题回填用），落盘只写聚合结果（开阳 health 图层 2145→~340 点）。
        代表 = date 最新一条（title/关键词/坐标/原文 URL）。
        10-16（CHG-20261016T120806）：count 语义由「同 loc 的 raw 条数」改为
        「同 loc 的 distinct story 数」——原值把通稿转载数当事件数（实测 France 45→9、
        Macquarie Island 35→2），前端 note 直接显示「共 N 起卫生事件」故用户可见。"""
        groups = {}
        for e in events:
            loc = (e.get("loc_name") or "").strip()
            if not loc:
                continue  # 无地点不聚合（后端已过滤无坐标事件，理论为空）
            groups.setdefault(loc, []).append(e)
        out = []
        for loc, evs in groups.items():
            evs.sort(key=lambda e: str(e.get("date", "")), reverse=True)
            rep = evs[0]
            # v1.1.1：count = max(同 loc distinct story 数, 事件自带 count)——raw 迁移期
            # 保留旧快照，72h 滚动淘汰后自然回落到真实条数（避免迁移即 count 归 1）。
            _max_c = max((int(e.get("count") or 1) for e in evs), default=1)
            _stories = len({_story_slug(e.get("doc") or "") for e in evs})
            out.append({
                "loc_name": loc,
                "lat": rep.get("lat"),
                "lng": rep.get("lng"),
                "count": max(_stories, _max_c),
                "date": rep.get("date"),
                "title": rep.get("title") or "",
                "title_zh": rep.get("title_zh") or "",
                "keywords": rep.get("keywords") or [],
                "doc": rep.get("doc"),
                "source_media": rep.get("source_media"),
            })
        return out

    def _persist(self, events, as_of):
        raw_count = len(events)
        # v1.1.1：明细持久化到 RAW_FILE（合并/回填源），展示文件只存聚合
        raw_payload = {
            "status": Status.OK,
            "source": "GDELT 2.0 GKG (health keyword filter, raw)",
            "as_of": as_of,
            "scope": "global",
            "schema_version": "1.0",
            "events_count": raw_count,
            "events": events,
        }
        self.save_json(RAW_FILE, raw_payload)
        aggregated = self._aggregate_by_location(events)
        payload = {
            "status": Status.OK,
            "source": "GDELT 2.0 GKG (health keyword filter)",
            "as_of": as_of,
            "scope": "global",
            "schema_version": "1.1",
            "aggregated": True,
            "raw_count": raw_count,
            "events_count": len(aggregated),
            "events": aggregated,
        }
        self.save_json(OUTPUT_FILE, payload)
        self.logger.info("[health_geo] 落盘 %d 条（按 loc_name 聚合，原始 %d 条，72h 窗口）",
                         len(aggregated), raw_count)
        return aggregated


def main():
    fetcher = HealthGeoFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[health_geo] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == Status.OK:
        ev = result.get("events", [])
        n = len(ev) if isinstance(ev, list) else ev.get("events_count", 0)
        print(f"[health_geo] 完成 status=ok，new_events={result.get('new_events')}，"
              f"slots={result.get('slots_checked')}，累积={n}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[health_geo] 降级，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, {
                "status": Status.UNAVAILABLE,
                "source": "GDELT 2.0 GKG",
                "as_of": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scope": "global",
                "schema_version": "1.0",
                "events_count": 0,
                "events": [],
            })
            print("[health_geo] 降级，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
