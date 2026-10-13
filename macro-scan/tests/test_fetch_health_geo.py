#!/usr/bin/env python3
"""离线验收：fetch_health_geo.HealthGeoFetcher._parse_slot（不触网）。

v3.8.74 起：关键词 haystack 剔除 URL 域名段（path/query 保留）——
修复 sentinelassam.com 域名含子串 lassa 导致的域名碰撞误报
（CHG-20261013T183000-health-geo-url-collision-fix）。

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

from fetch_health_geo import HealthGeoFetcher  # noqa: E402

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


if __name__ == "__main__":
    test_domain_collision_not_matched()
    test_domain_collision_variants()
    test_real_event_by_amounts_kept()
    test_path_keyword_kept()
    test_domain_collision_with_real_kw()
    test_exclude_phrase_still_works()
    test_no_location_skipped()
    test_persons_column_still_matched()
    print(f"\n断言失败数: {_fails}")
    sys.exit(1 if _fails else 0)
