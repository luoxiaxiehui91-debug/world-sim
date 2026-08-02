#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gdelt_country_map.py — GDELT FIPS 10-4 ↔ ISO 3166 双向映射（动态派生版）

设计文档：design/fetch_gdelt_geo_design.md §5.1

职责
----
为 GDELT v2 export 中 ActionGeo_CountryCode（FIPS 两字码）与天枢关注国家
（alert_config._WATCH_COUNTRIES，ISO 三字码）之间提供双向映射。

T01 阶段只交付映射表、派生逻辑、selftest；fetcher 集成在 T02 阶段。

**唯一硬编码区域**：FIPS_TO_ISO 字典字面 key/value。除此之外，本文件
任何位置（注释、日志、test name、path 等）**禁止出现国家名**——映射表本身
就是协议级标准字典，不解释哪个码对应哪个国家。
"""

from __future__ import annotations

import logging
import sys
from typing import Dict, FrozenSet, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [gdelt_country_map] %(message)s",
)
log = logging.getLogger("gdelt_country_map")


# ── 协议级 FIPS 10-4 → ISO 3166 映射（唯一硬编码区）───────────────────────
# 来源：GDELT Event Codebook V2.0 官方文档附录。
# 本字典为协议级标准字面映射；禁止在字典外出现任何国家名/政治描述。

FIPS_TO_ISO: Dict[str, str] = {
    "CH": "CHN", "RU": "RUS", "IR": "IRN", "US": "USA", "TW": "TWN",
    "JA": "JPN", "KP": "PRK", "KS": "KOR", "UK": "GBR", "IN": "IND",
    "FR": "FRA", "GM": "DEU", "BR": "BRA", "SF": "ZAF", "EG": "EGY",
    "IS": "ISR", "PK": "PAK", "AU": "AUS", "CA": "CAN", "MX": "MEX",
    "IT": "ITA", "SP": "ESP", "NL": "NLD", "SW": "SWE", "NO": "NOR",
    "FI": "FIN", "PL": "POL", "TU": "TUR", "AG": "DZA", "SU": "SUN",
    "NI": "NGA", "SA": "SAU", "UP": "UKR",
}

# 反向映射（运行时派生，禁止硬编码）。
ISO_TO_FIPS: Dict[str, str] = {iso: fips for fips, iso in FIPS_TO_ISO.items()}


def iso_for_fips(fips: str) -> Optional[str]:
    """FIPS 两字码 → ISO 三字码。命中失败返回 None。"""
    return FIPS_TO_ISO.get(fips)


def fips_for_iso(iso: str) -> Optional[str]:
    """ISO 三字码 → FIPS 两字码。命中失败返回 None。"""
    return ISO_TO_FIPS.get(iso)


# ── 关注国家清单派生（运行时从 alert_config 拉）───────────────────────────
# 单一真相源：alert_config._WATCH_COUNTRIES（ISO 三字码 set）。
# 本模块不复制该 set，避免双处漂移。

def _load_watch_set() -> FrozenSet[str]:
    """从 alert_config 加载 _WATCH_COUNTRIES（ISO 三字码 frozenset）。

    alert_config 不可导入时回退为空集合并 WARNING（设计文档 §5.1：fail-loud，
    不静默放行全球事件）。
    """
    try:
        import alert_config  # type: ignore
        watch = getattr(alert_config, "_WATCH_COUNTRIES", None)
        if isinstance(watch, (set, frozenset, tuple, list)):
            return frozenset(str(x) for x in watch)
        log.warning(
            "alert_config._WATCH_COUNTRIES 缺失或类型非法（%r），回退空集合",
            type(watch).__name__ if watch is not None else "None",
        )
        return frozenset()
    except ImportError:
        log.warning("alert_config 不可导入，回退空集合（设计文档 §5.1）")
        return frozenset()


_WATCH: FrozenSet[str] = _load_watch_set()
_WATCH_MISSING: list = [
    x for x in sorted(_WATCH)
    if x not in ISO_TO_FIPS and not (isinstance(x, str) and len(x) == 3 and x.isalpha() and x == x.upper())
]
# 更精确：缺映射 = x not in ISO_TO_FIPS（ISO_TO_FIPS 的 key 才是合法 ISO 三字码）。
_WATCH_MISSING = [x for x in sorted(_WATCH) if x not in ISO_TO_FIPS]

WATCH_FIPS: FrozenSet[str] = frozenset(
    fips for x in _WATCH
    for fips in [fips_for_iso(x)]
    if fips is not None
)

if _WATCH_MISSING:
    log.warning(
        "CRITICAL: _WATCH_COUNTRIES 中 %d 项未在 FIPS_TO_ISO 中找到映射，将被静默丢弃：%s",
        len(_WATCH_MISSING), _WATCH_MISSING,
    )


# ── selftest（动态断言；不依赖硬编码 watch 列表）───────────────────────────


def selftest() -> int:
    """8 项动态断言（设计文档 §5.1 + 本任务书）。"""
    results = []

    # 断言 1：双向一致（|ISO_TO_FIPS| == |FIPS_TO_ISO|）
    results.append((
        "01 双向一致（FIPS_TO_ISO 与 ISO_TO_FIPS 大小相等）",
        len(FIPS_TO_ISO) > 0 and len(ISO_TO_FIPS) == len(FIPS_TO_ISO),
    ))

    # 断言 2：所有 value 都是 ISO 三字码格式（3 个大写字母）
    all_iso_valid = all(
        isinstance(v, str) and len(v) == 3 and v.isalpha() and v == v.upper()
        for v in FIPS_TO_ISO.values()
    )
    results.append(("02 FIPS_TO_ISO value 全部为 3 位大写字母", all_iso_valid))

    # 断言 3：所有 key 都是 FIPS 两字码格式（2 个大写字母）
    all_fips_valid = all(
        isinstance(k, str) and len(k) == 2 and k.isalpha() and k == k.upper()
        for k in FIPS_TO_ISO.keys()
    )
    results.append(("03 FIPS_TO_ISO key 全部为 2 位大写字母", all_fips_valid))

    # 断言 4：_WATCH_MISSING 为空（若非空 selftest 不挂，但记 WARNING）
    results.append((
        "04 _WATCH_MISSING 为空（关注国家全部可映射）",
        len(_WATCH_MISSING) == 0,
    ))

    # 断言 5：WATCH_FIPS 大小 = _WATCH 中能在 ISO_TO_FIPS 找到的数量
    expected_count = sum(1 for x in _WATCH if x in ISO_TO_FIPS)
    results.append((
        "05 WATCH_FIPS 大小与可映射的 _WATCH 项数一致",
        len(WATCH_FIPS) == expected_count,
    ))

    # 断言 6：抽样测试（从字典前 3 项派生，避免硬编码国码字符串）
    sample_keys = list(FIPS_TO_ISO.keys())[:3]
    sample_results = [iso_for_fips(k) for k in sample_keys]
    expected_values = [FIPS_TO_ISO[k] for k in sample_keys]
    results.append((
        "06 iso_for_fips 抽样（前 3 个 dict key）正确",
        sample_results == expected_values,
    ))

    # 断言 7：反向映射（任挑一个 dict value 作为反查输入）
    pivot_value = next(iter(FIPS_TO_ISO.values()))
    pivot_key = next(k for k, v in FIPS_TO_ISO.items() if v == pivot_value)
    results.append((
        "07 fips_for_iso 反向映射与字典一致",
        fips_for_iso(pivot_value) == pivot_key,
    ))

    # 断言 8：未知码返回 None（取一个不可能在字典里的两字大写组合）
    unknown_code = "ZZ"
    while unknown_code in FIPS_TO_ISO:
        unknown_code += "Z"
    results.append((
        f"08 iso_for_fips({unknown_code!r}) == None",
        iso_for_fips(unknown_code) is None,
    ))

    passed = 0
    total = len(results)
    for name, ok in results:
        flag = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f"  [{flag}] {name}")

    print(f"\n=== gdelt_country_map.py selftest: {passed}/{total} PASS ===")
    if _WATCH_MISSING:
        print(f"  [WARN] _WATCH_MISSING（不影响 selftest 通过）：{len(_WATCH_MISSING)} 项")
    return 0 if passed == total else 1


# ── CLI（仅 T01 占位）───────────────────────────────────────────────────────


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="GDELT FIPS ↔ ISO 双向映射（selftest）")
    ap.add_argument("--selftest", action="store_true", help="跑 selftest")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


__all__ = [
    "FIPS_TO_ISO",
    "ISO_TO_FIPS",
    "WATCH_FIPS",
    "iso_for_fips",
    "fips_for_iso",
    "selftest",
]