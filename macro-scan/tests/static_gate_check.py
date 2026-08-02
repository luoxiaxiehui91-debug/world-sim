#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
static_gate_check.py — 设计 P0 静态闸门扫描（fetch_gdelt_geo + gdelt_country_map）

设计文档：design/fetch_gdelt_geo_design.md §8 + 任务书红线

职责
----
扫两个文件，拦截以下 P0 违规：
  a) `from optim_config import FRED_PROXY`（红线：optim_config 无该变量 → ImportError → DATA_DIR 回落非持久卷）
  b) `import scan_weak_signals`（任何形式；既有模块 import 即执行的副作用不可控）
  c) 单文件 bind mount 关键词（`/etc/...`、`docker run -v <single-file>`）
  d) 源码硬编码国码字符串：
     - FIPS 两字码：CH/RU/IR/US/TW/JA/KP/KS/UK/IN/FR/GM/BR/SF/EG/IS/PK/AU/CA/MX/IT/SP/NL/SW/NO/FI/PL/TU/AG/SU
       （仅在 FIPS_TO_ISO 字典字面 key/value 位置允许）
     - ISO 三字码：CHN/RUS/IRN/USA/TWN/JPN/PRK/KOR/GBR/IND/FRA/DEU/BRA/ZAF/EGY/ISR/PAK/AUS/CAN/MEX/ITA/ESP/NLD/SWE/NOR/FIN/POL/TUR/DZA
       （任何位置出现都拦截）

退出码
------
  0  无 P0 违规
  1  发现 ≥1 个 P0 违规
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

# ── 路径 ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_DIR = REPO_ROOT / "design"
FETCHER_PATH = DESIGN_DIR / "fetch_gdelt_geo.py"
COUNTRY_MAP_PATH = DESIGN_DIR / "gdelt_country_map.py"


# ── 拦截项 ────────────────────────────────────────────────────────────────

# 红线 a：optim_config 唯一允许导入是 DATA_DIR / WORKSPACE，FRED_PROXY 严禁。
REDLINE_FRED_PROXY = re.compile(r"from\s+optim_config\s+import\s+.*\bFRED_PROXY\b")
REDLINE_SCAN_WEAK_SIGNALS = re.compile(r"\bimport\s+scan_weak_signals\b|from\s+scan_weak_signals\s+import\b")

# 红线 c：单文件 bind mount 关键词（容错写法：`docker run -v /workspace/data/foo.json:/x`）
REDLINE_BIND_MOUNT = re.compile(
    r"docker\s+run[^]*?-v\s+[^\s:]+\.json:[^\s]+", re.IGNORECASE
)
REDLINE_ETC_PATH = re.compile(r"/etc/[a-zA-Z0-9_./-]+")

# 红线 d：源码硬编码国码字符串
FIPS_TWO_LETTER_CODES = [
    "CH", "RU", "IR", "US", "TW", "JA", "KP", "KS", "UK", "IN",
    "FR", "GM", "BR", "SF", "EG", "IS", "PK", "AU", "CA", "MX",
    "IT", "SP", "NL", "SW", "NO", "FI", "PL", "TU", "AG", "SU",
]

ISO_THREE_LETTER_CODES = [
    "CHN", "RUS", "IRN", "USA", "TWN", "JPN", "PRK", "KOR", "GBR", "IND",
    "FRA", "DEU", "BRA", "ZAF", "EGY", "ISR", "PAK", "AUS", "CAN", "MEX",
    "ITA", "ESP", "NLD", "SWE", "NOR", "FIN", "POL", "TUR", "DZA",
]

# ISO 三字码任何位置都拦截（包括注释/日志/路径）；FIPS 两字码仅在
# FIPS_TO_ISO 字典字面（value 段）允许出现，其它位置一律拦截。


def _is_country_map_dict_line(line: str) -> bool:
    """判断行是否在 FIPS_TO_ISO 字典字面内部（仅 value 段允许出现 FIPS 两字码）。"""
    # 简化：字典字面行（{ 开头 / 续行 / }）+ 包含 "X": "YY" 形态。
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return False
    return bool(re.search(r'"[A-Z]{2}"\s*:\s*"[A-Z]{3}"', line))


def scan_forbidden_imports(path: Path, source: str) -> List[Tuple[int, str]]:
    """红线 a/b/c。"""
    failures: List[Tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if REDLINE_FRED_PROXY.search(line):
            failures.append((lineno, "P0: from optim_config import FRED_PROXY 严禁"))
        if REDLINE_SCAN_WEAK_SIGNALS.search(line):
            failures.append((lineno, "P0: import scan_weak_signals 任何形式严禁"))
        if REDLINE_BIND_MOUNT.search(line):
            failures.append((lineno, "P0: 单文件 bind mount 严禁（与目录挂载冲突）"))
        if REDLINE_ETC_PATH.search(line):
            failures.append((lineno, "P0: 源码出现 /etc/... 路径"))
    return failures


def scan_fips_codes(path: Path, source: str) -> List[Tuple[int, str]]:
    """FIPS 两字码拦截：除 FIPS_TO_ISO 字典字面 key/value 段外不许出现。"""
    failures: List[Tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        # 字典字面行：整行跳过（key 与 value 都是协议级硬编码，唯一允许位置）
        if path.name == "gdelt_country_map.py" and _is_country_map_dict_line(line):
            continue
        # 注释行跳过（避免被 selftest/文档示例误伤；本文件本身无国家名注释）
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for code in FIPS_TWO_LETTER_CODES:
            # 用 word boundary：避免在长标识符中间误命中
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])")
            if pattern.search(line):
                # gdelt_country_map.py 的 selftest 抽样 [\"CH\", \"US\", \"RU\"] 是协议标准用法，
                # 但按本任务书红线：FIPS 两字码**只能在字典字面**出现，selftest 抽样也改用
                # 字典里现成的 key 来访问。这里直接拦截。
                failures.append((
                    lineno,
                    f"P0: FIPS 两字码 '{code}' 在非字典字面位置出现",
                ))
    return failures


def scan_iso_codes(path: Path, source: str) -> List[Tuple[int, str]]:
    """ISO 三字码拦截：任何位置（包括注释/日志/路径）都拦截。"""
    failures: List[Tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        for code in ISO_THREE_LETTER_CODES:
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])")
            if pattern.search(line):
                # gdelt_country_map.py 字典字面 value 是协议级硬编码（唯一允许位置）
                if path.name == "gdelt_country_map.py" and _is_country_map_dict_line(line):
                    continue
                failures.append((
                    lineno,
                    f"P0: ISO 三字码 '{code}' 硬编码出现",
                ))
    return failures


# ── 入口 ──────────────────────────────────────────────────────────────────


def scan_file(path: Path) -> List[Tuple[int, str]]:
    """对一个文件跑全部静态闸，返回 [(line_no, reason), ...]。"""
    if not path.is_file():
        return [(0, f"文件不存在: {path}")]
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = path.read_text(encoding="utf-8", errors="replace")

    failures: List[Tuple[int, str]] = []
    failures.extend(scan_forbidden_imports(path, source))
    failures.extend(scan_fips_codes(path, source))
    failures.extend(scan_iso_codes(path, source))
    return failures


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="T01 静态闸门扫描（P0 拦截）")
    args = ap.parse_args(argv)

    targets = [FETCHER_PATH, COUNTRY_MAP_PATH]
    all_failures: List[Tuple[Path, int, str]] = []
    for path in targets:
        for line_no, reason in scan_file(path):
            all_failures.append((path, line_no, reason))
            print(f"P0_GATE_FAIL: {path}:{line_no} {reason}")

    if all_failures:
        print(f"\n=== static_gate_check.py: {len(all_failures)} P0 违规 (exit 1) ===")
        return 1

    print("=== static_gate_check.py: 0 P0 违规 (exit 0) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))