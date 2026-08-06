#!/usr/bin/env python3
"""
news_geo_feed.py — 新闻坐标提取器（P3-A）

依赖 P2（spaCy zh_core_web_sm）：
  1. 读取 data/news_export.json 的 articles（每日 07:05 更新）
  2. 用 zh_core_web_sm 对 title 做 NER，提取 GPE/LOC 实体（地名）
  3. 查 data/gdelt_geo_cache.json 获取坐标（geo_risk_vector.py 顺带写入）
  4. 过滤掉 lat/lng 为 null 的条目
  5. 写出 data/news_geo.json，供 kaiyang 地理新闻图层读取

输出格式：
{
  "_schema_version": "1.0",
  "generated_at": "...",
  "articles": [
    {"title": "...", "url": null, "lat": 31.2, "lng": 121.5,
     "source": "...", "published_at": "...", "category": "..."}
  ]
}

调度：07:15（news_export 07:05 之后，spaCy 模型冷启动约 5s）
"""
import json
import os
import logging
import datetime
from pathlib import Path

try:
    from optim_config import DATA_DIR
except ImportError:
    DATA_DIR = os.path.join(
        os.environ.get("OPENCLAW_WORKSPACE",
                       os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
    )

NEWS_EXPORT_FILE  = os.path.join(DATA_DIR, "news_export.json")
GEO_CACHE_FILE    = os.path.join(DATA_DIR, "gdelt_geo_cache.json")
OUTPUT_FILE       = os.path.join(DATA_DIR, "news_geo.json")

LOG_DIR  = "/var/log/macro-scan"


def _get_logger():
    logger = logging.getLogger("news_geo_feed")
    if not logger.handlers:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            h = logging.FileHandler(os.path.join(LOG_DIR, "news_geo_feed.log"),
                                    encoding="utf-8")
        except OSError:
            h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger


def _load_geo_cache() -> dict:
    """读取 gdelt_geo_cache.json，格式 {"地名": [lat, lng]}。"""
    if not os.path.exists(GEO_CACHE_FILE):
        return {}
    try:
        with open(GEO_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_spacy_model():
    """加载 zh_core_web_sm，失败时 raise（红线 #8：禁静默降级；2026-08-06 news-geo-empty 修复）。"""
    try:
        import spacy
        return spacy.load("zh_core_web_sm")
    except Exception as e:
        _get_logger().error("[news_geo] spaCy 加载失败（阻断，需镜像含 spacy+zh_core_web_sm）: %s", e)
        raise


def _extract_geo_entities(nlp, text: str) -> list[str]:
    """用 spaCy NER 提取 GPE/LOC 实体（地名）。"""
    if not nlp or not text:
        return []
    try:
        doc = nlp(text[:200])  # 限制长度，避免慢推理
        return [ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC")]
    except Exception:
        return []


def _lookup_coords(geo_names: list[str], cache: dict) -> tuple[float, float] | tuple[None, None]:
    """在缓存中查第一个有坐标的地名，返回 (lat, lng) 或 (None, None)。"""
    for name in geo_names:
        coords = cache.get(name)
        if coords and len(coords) >= 2:
            try:
                lat, lng = float(coords[0]), float(coords[1])
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return lat, lng
            except (TypeError, ValueError):
                pass
    return None, None


def run():
    logger = _get_logger()
    logger.info("[news_geo] 开始生成 news_geo.json")

    # 1. 读取 news_export.json
    if not os.path.exists(NEWS_EXPORT_FILE):
        logger.warning("[news_geo] news_export.json 不存在，跳过")
        return

    try:
        with open(NEWS_EXPORT_FILE, encoding="utf-8") as f:
            news_data = json.load(f)
    except Exception as e:
        logger.error("[news_geo] 读取 news_export.json 失败: %s", e)
        return

    articles_in = news_data.get("articles", [])
    if not articles_in:
        logger.info("[news_geo] news_export.json 无文章，跳过")
        return

    # 2. 加载依赖
    geo_cache = _load_geo_cache()
    nlp = _load_spacy_model()
    logger.info("[news_geo] geo_cache 条目数=%d  spaCy=%s",
                len(geo_cache), "OK" if nlp else "UNAVAILABLE")

    # 3. 处理每篇文章
    geo_articles = []
    for art in articles_in:
        title = art.get("title", "")
        if not title:
            continue

        geo_names = _extract_geo_entities(nlp, title) if nlp else []

        lat, lng = _lookup_coords(geo_names, geo_cache)
        if lat is None or lng is None:
            continue  # 无坐标 → 过滤掉

        geo_articles.append({
            "title":        title,
            "url":          art.get("url"),
            "lat":          lat,
            "lng":          lng,
            "source":       art.get("source"),
            "published_at": art.get("date") or art.get("published_at"),
            "category":     art.get("category"),
        })

    logger.info("[news_geo] 处理完成：%d/%d 篇有坐标", len(geo_articles), len(articles_in))

    # 4. 写出 news_geo.json
    output = {
        "_schema_version": "1.0",
        "generated_at":    datetime.datetime.now().isoformat(timespec="seconds"),
        # P2 修复（news-geo-contract-drift）：顶层 updated 供 useFeed.ts:62 拾取时间戳
        "updated":         datetime.datetime.now().isoformat(timespec="seconds"),
        "articles":        geo_articles,
    }
    tmp = OUTPUT_FILE + ".tmp"
    try:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        os.replace(tmp, OUTPUT_FILE)
        logger.info("[news_geo] 写出 %s（%d 条）", OUTPUT_FILE, len(geo_articles))
    except Exception as e:
        logger.error("[news_geo] 写出失败: %s", e)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [news_geo] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    run()
