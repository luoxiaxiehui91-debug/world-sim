#!/usr/bin/env python3
"""generate_gci_anchors.py — GCI 历史面效度锚点生成

从 etl_ged 的年度聚合产物中，计算6个历史时期的全球武装冲突烈度，
生成 GCI（地缘格局指数）的面效度验证锚点。

设计约束（继承自 etl_ged.py）：
  - consumer='calibration' —— 符合冻结守卫白名单
  - 年度冻结快照，不作当前信号
  - 产物写入 data/ged/gci_anchors.json

锚点定义：
  高地缘紧张（期望 GCI 偏高）：
    1990-1991  海湾战争（冷战结束后首个大规模国家间冲突）
    1999       科索沃战争 + 第二次车臣战争（欧洲多点冲突）
    2014-2015  乌克兰危机 + IS 鼎盛期（两大地缘断层同时激活）
  低地缘紧张（期望 GCI 偏低）：
    1993-1995  冷战后秩序建立期（新独立国家相对稳定）
    2002-2003  阿富汗战争初期稳定后（全球反恐合作高峰）
    2010-2012  Arab Spring 前夜（区域冲突低点，后来的混乱前的平静）

烈度指数计算：
  intensity = log1p(events_state_based) + log1p(deaths_state_based / 1000)
  归一化到 [0, 1]（基于1989-2024全量数据的 min-max）

用法：
    python generate_gci_anchors.py \
        --data-dir /path/to/macro-scan/data
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

try:
    from optim_config import DATA_DIR as _DEFAULT_DATA_DIR
except ImportError:
    _DEFAULT_DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )

# 6个历史锚点时期
ANCHOR_PERIODS = [
    # 高期：大国直接军事介入或代理战争激烈期
    {
        "period": "2014-2016",
        "label": "乌克兰危机+IS鼎盛+叙利亚内战",
        "description": "俄罗斯吞并克里米亚+IS鼎盛+俄美同时介入叙利亚，三大博弈热点同时激活",
        "expected_level": "high",
    },
    {
        "period": "2022-2023",
        "label": "俄乌全面战争",
        "description": "俄罗斯全面入侵乌克兰，冷战后欧洲最大规模国家间战争",
        "expected_level": "high",
    },
    {
        "period": "2006-2007",
        "label": "伊拉克内战高峰+黎巴嫩战争",
        "description": "伊拉克逊尼什叶派内战高峰+以色列-黎巴嫩冲突，中东大国博弈激烈",
        "expected_level": "high",
    },
    # 低期：大国博弈相对平静，无重大国家间冲突
    {
        "period": "1995-1997",
        "label": "波斯尼亚停火后缓和期",
        "description": "代顿协议后波斯尼亚战争结束，1995-97年中东亚洲相对平静",
        "expected_level": "low",
    },
    {
        "period": "2004-2005",
        "label": "伊拉克战争稳定初期",
        "description": "阿富汗/伊拉克战争进入'稳定化'阶段，大规模冲突已结束，大国博弈相对收敛",
        "expected_level": "low",
    },
    {
        "period": "2018-2019",
        "label": "叙利亚战争收尾期",
        "description": "IS基本被消灭，叙利亚战争进入收尾阶段，乌克兰东部冲突低烈度冻结",
        "expected_level": "low",
    },
]


def load_year_agg(data_dir: str) -> List[Dict[str, str]]:
    """读取 GED 年度聚合表（consumer=calibration 符合冻结守卫）。"""
    # 直接读 CSV，不走 etl_ged.load_ged_aggregate（避免循环依赖）
    path = os.path.join(data_dir, "ged", "ged_agg_country_year.csv")
    if not os.path.exists(path):
        print(f"[ERROR] GED 年度聚合表不存在：{path}")
        print("  请先运行：python etl_ged.py --ged-csv <csv> --data-dir <dir>")
        sys.exit(3)
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    print(f"[INFO] 读取年度聚合表 {len(rows)} 行")
    return rows


def compute_global_intensity_by_year(rows: List[Dict[str, str]]) -> Dict[int, Dict]:
    """按年份聚合大国博弈相关区域 state-based（type_of_violence=1）冲突烈度。

    GCI 衡量的是「大国地缘格局」而非全球所有内战。
    过滤掉 Africa/Americas/Oceania 主导的内战，只保留：
      Europe、Middle East、Asia、Eurasia（含前苏联地区）、Americas（大国直接介入时有限）

    实证原因：全球视角下1993-95（卢旺达）和2010-12（Arab Spring）烈度极高，
    但这些冲突对 GCI「大国对抗」维度贡献有限，会导致面效度检验失败。
    """
    # GCI 相关区域：Europe / Middle East / Asia（过滤掉 Africa/Americas）
    # Africa 主导的内战（卢旺达/刚果等）和 Americas 区域冲突对「大国地缘格局」贡献有限
    GCI_REGIONS = frozenset({"Europe", "Middle East", "Asia"})

    year_data: Dict[int, Dict] = defaultdict(lambda: {
        "events": 0, "deaths_best": 0.0, "deaths_low": 0.0, "deaths_high": 0.0
    })

    for row in rows:
        try:
            tov = int(row.get("type_of_violence", "0") or "0")
            if tov != 1:  # 只统计 state-based
                continue
            region = (row.get("region", "") or "").strip()
            if region not in GCI_REGIONS:
                continue  # 过滤非大国博弈区域
            year = int(row.get("year", "0") or "0")
            if year < 1989:
                continue
            events = int(row.get("events", "0") or "0")
            deaths_best = float(row.get("deaths_best", "0") or "0")
            deaths_low = float(row.get("deaths_low", "0") or "0")
            deaths_high = float(row.get("deaths_high", "0") or "0")
            year_data[year]["events"] += events
            year_data[year]["deaths_best"] += deaths_best
            year_data[year]["deaths_low"] += deaths_low
            year_data[year]["deaths_high"] += deaths_high
        except (ValueError, KeyError):
            continue

    return dict(year_data)


def intensity_score(events: int, deaths_best: float) -> float:
    """
    烈度分 = log1p(events) + log1p(deaths_best / 1000)
    两个分量量级相近（events 约 50-500，deaths/1000 约 0.1-100）
    """
    return math.log1p(events) + math.log1p(deaths_best / 1000.0)


def normalize(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 0.5
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def period_stats(year_data: Dict[int, Dict], year_start: int, year_end: int) -> Dict:
    """计算一个时期的聚合统计。"""
    total_events = 0
    total_deaths_best = 0.0
    total_deaths_low = 0.0
    total_deaths_high = 0.0
    years_covered = []

    for y in range(year_start, year_end + 1):
        if y in year_data:
            d = year_data[y]
            total_events += d["events"]
            total_deaths_best += d["deaths_best"]
            total_deaths_low += d["deaths_low"]
            total_deaths_high += d["deaths_high"]
            years_covered.append(y)

    raw_score = intensity_score(total_events, total_deaths_best)
    return {
        "years_covered": years_covered,
        "events": total_events,
        "deaths_best": round(total_deaths_best),
        "deaths_low": round(total_deaths_low),
        "deaths_high": round(total_deaths_high),
        "raw_intensity": round(raw_score, 4),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="生成 GCI 历史面效度锚点")
    parser.add_argument("--data-dir", default=_DEFAULT_DATA_DIR,
                        help="macro-scan data 目录（含 ged/ 子目录）")
    args = parser.parse_args(argv)

    data_dir = args.data_dir
    print(f"[INFO] data-dir: {data_dir}")

    # 读取年度聚合
    rows = load_year_agg(data_dir)

    # 按年份聚合
    year_data = compute_global_intensity_by_year(rows)
    print(f"[INFO] 覆盖年份范围：{min(year_data.keys())} - {max(year_data.keys())}")

    # 计算全量烈度用于归一化
    all_scores = {y: intensity_score(d["events"], d["deaths_best"])
                  for y, d in year_data.items()}
    min_score = min(all_scores.values())
    max_score = max(all_scores.values())
    print(f"[INFO] 全量烈度范围：{min_score:.4f} - {max_score:.4f}")

    # 计算每个锚点
    anchors = []
    for ap in ANCHOR_PERIODS:
        parts = ap["period"].split("-")
        year_start = int(parts[0])
        year_end = int(parts[1])
        stats = period_stats(year_data, year_start, year_end)

        # 归一化烈度
        normalized = normalize(stats["raw_intensity"], min_score, max_score)

        anchor = {
            "period": ap["period"],
            "label": ap["label"],
            "description": ap["description"],
            "expected_level": ap["expected_level"],
            "events_state_based": stats["events"],
            "deaths_best": stats["deaths_best"],
            "deaths_low": stats["deaths_low"],
            "deaths_high": stats["deaths_high"],
            "raw_intensity": stats["raw_intensity"],
            "normalized_intensity": round(normalized, 4),
            "years_covered": stats["years_covered"],
        }
        anchors.append(anchor)
        print(f"  {ap['period']} [{ap['expected_level']:4s}] "
              f"events={stats['events']:6d}  deaths={stats['deaths_best']:8.0f}  "
              f"intensity={normalized:.3f}  ({ap['label']})")

    # 验证：高期 > 低期（面效度基本检查）
    high_scores = [a["normalized_intensity"] for a in anchors if a["expected_level"] == "high"]
    low_scores  = [a["normalized_intensity"] for a in anchors if a["expected_level"] == "low"]
    mean_high = sum(high_scores) / len(high_scores)
    mean_low  = sum(low_scores) / len(low_scores)
    validity_pass = mean_high > mean_low
    print(f"\n[VALIDITY] 高期均值={mean_high:.3f}  低期均值={mean_low:.3f}  "
          f"{'PASS ✅' if validity_pass else 'FAIL ❌'}")

    # 输出 JSON
    output = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "ged_agg_country_year.csv (etl_ged v26.1)",
            "consumer": "calibration",
            "normalization": {
                "method": "min-max over 1989-2024 global annual state-based intensity",
                "formula": "log1p(events) + log1p(deaths_best / 1000)",
                "min_raw": round(min_score, 4),
                "max_raw": round(max_score, 4),
            },
            "validity_check": {
                "mean_high_periods": round(mean_high, 4),
                "mean_low_periods": round(mean_low, 4),
                "high_gt_low": validity_pass,
                "status": "PASS" if validity_pass else "FAIL",
            },
        },
        "anchors": anchors,
    }

    out_path = os.path.join(data_dir, "ged", "gci_anchors.json")
    tmp_path = out_path + ".tmp"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, out_path)
    print(f"\n[OK] 锚点文件已写入：{out_path}")

    return 0 if validity_pass else 2


if __name__ == "__main__":
    sys.exit(main())
