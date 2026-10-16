#!/usr/bin/env python3
"""离线验收：fetch_health_geo.HealthGeoFetcher._parse_slot（不触网）。

v3.8.74 起：关键词 haystack 剔除 URL 域名段（path/query 保留）——
修复 sentinelassam.com 域名含子串 lassa 导致的域名碰撞误报
（CHG-20261013T183000-health-geo-url-collision-fix）。

v3.8.76 起：事件单位改为「故事（URL path slug）」——通稿转载不再重复计事件、
count 改 distinct story 数、剔聚合页/tag 页、关键词加左边界约束
（CHG-20261016T120806-health-geo-syndication-story-unit）。

运行：python tests/test_fetch_health_geo.py
退出码：0 = 全 PASS，1 = 存在失败断言。
"""
import io
import os
import sys
import tempfile
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from fetch_health_geo import HealthGeoFetcher, _story_slug, _is_aggregator_page  # noqa: E402

_fails = 0


def check(cond: bool, msg: str) -> None:
    global _fails
    if cond:
        print(f"  PASS: {msg}")
    else:
        _fails += 1
        print(f"  FAIL: {msg}")


def make_row(url, persons="", amounts="",
             loc="1#Testville#TC#TC01#10.5#20.5#TC01",
             date="20261013120000", source="example.com"):
    """构造一行 GKG 27 列 TSV（仅填被测相关列，其余置空）。"""
    cols = [""] * 27
    cols[0] = "20261013120000-0"
    cols[1] = date
    cols[3] = source
    cols[4] = url
    cols[9] = loc
    cols[11] = persons
    cols[24] = amounts
    return "\t".join(cols)


def make_zip(rows):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("20261013120000.gkg.csv", "\n".join(rows))
    return buf.getvalue()


def parse(rows):
    tmp = tempfile.mkdtemp()
    f = HealthGeoFetcher(tmp)
    return f._parse_slot(make_zip(rows))


def test_domain_collision_not_matched():
    print("[test] 域名撞不收录（sentinelassam × lassa）")
    rows = [make_row(
        "https://www.sentinelassam.com/north-east-india-news/assam-news/"
        "assam-cm-visits-grieving-family-of-accident-victims/")]
    check(parse(rows) == [],
          "域名段含 lassa、路径无词的报道 → 不收录（修复目标）")


def test_domain_collision_variants():
    print("[test] 域名撞变体（无 www / 大小写）")
    rows = [
        make_row("https://sentinelassam.com/breakingnews/zubeen-garg-case-bail-hearing-today/"),
        make_row("https://WWW.SentinelAssam.COM/more-news/international/india-denounces-attack/"),
    ]
    check(parse(rows) == [], "无 www / 大小写变体同样不收录")


def test_real_event_by_amounts_kept():
    print("[test] 真事件（Amounts 列命中）保留")
    rows = [make_row("https://example.com/news/story-123/",
                     amounts="6,ebola cases,123")]
    ev = parse(rows)
    check(len(ev) == 1, "1 条收录")
    check(bool(ev) and ev[0]["keywords"] == ["ebola"], "keywords == ['ebola']")


def test_path_keyword_kept():
    print("[test] 路径段含词保留（真事件 slug 场景）")
    rows = [make_row("https://example.com/news/lassa-fever-outbreak-in-nigeria-2026/")]
    ev = parse(rows)
    check(len(ev) == 1, "1 条收录")
    check(bool(ev) and {"lassa", "outbreak"} <= set(ev[0]["keywords"]),
          "keywords 含 lassa + outbreak")


def test_domain_collision_with_real_kw():
    print("[test] 域名撞 + 真词 → 收录且 kw 不含 lassa")
    rows = [make_row("https://www.sentinelassam.com/x/y/",
                     amounts="2,mpox cases,10")]
    ev = parse(rows)
    check(len(ev) == 1, "1 条收录")
    check(bool(ev) and ev[0]["keywords"] == ["mpox"],
          "keywords == ['mpox']（不含 lassa）")


def test_exclude_phrase_still_works():
    print("[test] EXCLUDE 短语（pandemic loan）仍排除")
    rows = [make_row("https://example.com/x/",
                     amounts="500,pandemic loan,10")]
    check(parse(rows) == [], "amounts 含 pandemic loan → 排除")


def test_no_location_skipped():
    print("[test] 无坐标事件跳过")
    rows = [make_row("https://example.com/news/lassa-fever-outbreak/", loc="")]
    check(parse(rows) == [], "无坐标 → 跳过")


def test_persons_column_still_matched():
    print("[test] Persons 列仍参与匹配（现状保持）")
    rows = [make_row("https://example.com/x/", persons="john ebola;jane doe")]
    ev = parse(rows)
    check(len(ev) == 1, "1 条收录")
    check(bool(ev) and ev[0]["keywords"] == ["ebola"], "keywords == ['ebola']")


def test_embedded_word_not_matched():
    print("[test] 嵌词巧合不收录（vlassakis × lassa）")
    rows = [make_row(
        "https://example.com/news/snowtown-james-vlassakis-serial-killer-parole-hearing/")]
    check(parse(rows) == [], "vlassakis 内含 lassa → 不收录（左边界约束）")


def test_plural_and_hyphen_still_matched():
    print("[test] 复数 / 连字符写法仍收录（左边界不误杀）")
    rows = [
        make_row("https://example.com/news/measles-outbreaks-reported-in-three-states/"),
        make_row("https://example.com/news/h5n1-detected-in-poultry/"),
    ]
    ev = parse(rows)
    check(len(ev) == 2, "2 条收录")
    kws = [set(e["keywords"]) for e in ev]
    check(any("outbreak" in k for k in kws), "outbreaks 命中 outbreak")
    check(any("h5n1" in k for k in kws), "h5n1- 连字符写法命中")


def test_aggregator_page_skipped():
    print("[test] 聚合页 / tag 页不计为事件")
    rows = [
        make_row("https://newsroomamerica.com/tag/foodborne_illness_outbreak",
                 amounts="3,outbreak cases,10"),
        make_row("https://www.grandrapidsmn.com/around_the_web/news/minnesota-measles/",
                 amounts="3,measles cases,10"),
    ]
    check(parse(rows) == [], "tag 页 / around_the_web 页 → 不收录")


def test_category_path_kept():
    print("[test] 分类路径下的真文章仍收录（不误剔 /category/）")
    rows = [make_row(
        "https://www.freemalaysiatoday.com/category/highlight/2026/10/14/"
        "dr-congo-ebola-outbreak-passes-9000-cases/")]
    ev = parse(rows)
    check(len(ev) == 1, "1 条收录")
    check(bool(ev) and "ebola" in ev[0]["keywords"], "keywords 含 ebola")


def test_story_slug_date_stripped():
    print("[test] _story_slug：剔日期段、保留故事 ID")
    s1 = _story_slug("https://x.com/news/2026/10/16/poultry-order-lifted-victoria/107")
    check(s1 == "news/poultry-order-lifted-victoria/107", f"日期段剔除: {s1}")
    s2 = _story_slug("https://www.abc.net.au/news/2026-10-16/poultry-order-lifted/107")
    check(s2 == "news/poultry-order-lifted/107", f"ISO 日期段剔除: {s2}")
    s3 = _story_slug("https://www.areanews.com.au/story/9367686/bedbug-outbreak-on-flight-to-perth")
    check(s3 == "story/9367686/bedbug-outbreak-on-flight-to-perth",
          f"故事 ID 保留: {s3}")


def test_merge_events_slug_dedupe():
    print("[test] _merge_events：同故事多域名转载只留一条")
    import datetime
    d = (datetime.datetime.utcnow() - datetime.timedelta(hours=1)).strftime("%Y%m%d%H%M%S")

    def mk(url):
        return {"doc": url, "date": d, "lat": -31.95, "lng": 115.86,
                "loc_name": "Perth, Western Australia, Australia",
                "keywords": ["outbreak"], "source_media": "x"}

    rows = [
        mk("https://www.areanews.com.au/story/9367686/bedbug-outbreak-on-flight-to-perth"),
        mk("https://www.bendigoadvertiser.com.au/story/9367686/bedbug-outbreak-on-flight-to-perth"),
        mk("https://www.camdencourier.com.au/story/9367686/bedbug-outbreak-on-flight-to-perth"),
    ]
    tmp = tempfile.mkdtemp()
    f = HealthGeoFetcher(tmp)
    f._load_events = lambda: []
    f._backfill_source_media = lambda x: x
    merged = f._merge_events(rows)
    check(len(merged) == 1, f"3 家转载 → 1 条（实际 {len(merged)}）")


def test_aggregate_count_distinct_stories():
    print("[test] _aggregate_by_location：count = distinct story 数")
    d = "20261016100000"

    def mk(url, kw):
        return {"doc": url, "date": d, "lat": 1.0, "lng": 2.0,
                "loc_name": "Perth, Australia", "keywords": [kw]}

    evs = [
        mk("https://a.com/story/1/bedbug-outbreak", "outbreak"),
        mk("https://b.com/story/1/bedbug-outbreak", "outbreak"),
        mk("https://c.com/story/2/measles-cases-spike", "measles"),
    ]
    tmp = tempfile.mkdtemp()
    f = HealthGeoFetcher(tmp)
    out = f._aggregate_by_location(evs)
    check(len(out) == 1, "1 个聚合点")
    check(out[0]["count"] == 2, f"count == 2（真实故事数，实际 {out[0]['count']}）")


if __name__ == "__main__":
    test_domain_collision_not_matched()
    test_domain_collision_variants()
    test_real_event_by_amounts_kept()
    test_path_keyword_kept()
    test_domain_collision_with_real_kw()
    test_exclude_phrase_still_works()
    test_no_location_skipped()
    test_persons_column_still_matched()
    test_embedded_word_not_matched()
    test_plural_and_hyphen_still_matched()
    test_aggregator_page_skipped()
    test_category_path_kept()
    test_story_slug_date_stripped()
    test_merge_events_slug_dedupe()
    test_aggregate_count_distinct_stories()
    print(f"\n断言失败数: {_fails}")
    sys.exit(1 if _fails else 0)
