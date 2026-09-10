#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
init_kb.py — 知识库骨架初始化（bootstrap）

本仓库开源的是**框架与逻辑**；知识库（研究内容）需要你自己建立。
本脚本生成一份最小可用的知识库骨架，使各分析链路能够运行起来。

⚠️ 生成的全部内容均为**示例 / 占位**，仅用于演示目录约定与文件格式。
   请按 docs/KB_SETUP.md 的说明替换为你自己的研究内容。

用法：
    python3 scripts/init_kb.py                  # 生成到 <仓库根>/macro-scan/知识库
    python3 scripts/init_kb.py --dest <路径>     # 生成到指定位置
    python3 scripts/init_kb.py --force          # 覆盖已存在的文件（默认跳过）
    python3 scripts/init_kb.py --list           # 只列出将生成的文件

生成后如需让容器使用，请在 .env 中设置：
    KB_ROOT=<知识库根目录>      （默认 <项目根>/知识库）
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = REPO_ROOT / "macro-scan" / "知识库"

BANNER = "<!-- ⚠️ 本文件由 scripts/init_kb.py 生成的示例骨架，请替换为你自己的内容 -->\n"

# ──────────────────────────────────────────────────────────────────────
# 文件内容
# ──────────────────────────────────────────────────────────────────────

FILES = {}

FILES["README.md"] = """# 知识库（Knowledge Base）

> ⚠️ 这是 `scripts/init_kb.py` 生成的**示例骨架**。本目录**不纳入 git 版本控制**，
> 属于你自己的数据资产，请替换为真实研究内容。

## 为什么是独立的？

本仓库开源的是**框架与逻辑**（数据采集、指标计算、RAG 检索、蒙特卡洛推演、报告生成），
而知识库是**你的研究积累**——指标体系、因果链、历史案例、分析框架。

两者分离有两个好处：

1. **版权清晰**：第三方内容（研报、付费数据）不会随仓库分发
2. **各建各库**：每个人建适合自己的知识库，框架保持一致

## 目录约定

```
知识库/
├── political_calendar.yaml        # 政治/宏观日历（daily_narrative 读取）
└── 财经知识库/                     # 知识库主体（RAG 索引范围）
    ├── 02_核心变量因果链/           # 因果链、历史情景、校准参数
    ├── 04_分析框架/                 # 分析框架、传导路径
    ├── 专题报告/                    # 专题研究（RAG 主要来源）
    ├── 15_国际形势/                 # 国际形势观察
    ├── 04_跨国联动矩阵/             # 跨国传导系数
    └── 中国/                        # 分经济体研究
```

## 两类文件

| 类型 | 作用 | 缺失后果 |
|---|---|---|
| **数据文件**（`.csv` / `.json` / `.yaml`） | 被代码直接读取，驱动计算 | 对应功能**降级**（多数有兜底，不会崩溃） |
| **研究文档**（`.md`） | 被 RAG 索引，作为 LLM 分析上下文 | 检索内容为空，分析质量下降 |

## 下一步

参见 `docs/KB_SETUP.md`：

- 每个目录放什么、格式要求
- 如何接入你自己的数据源
- 如何重建 RAG 索引（`build_rag_index.py`）
"""

FILES["political_calendar.yaml"] = """# political_calendar.yaml — 全球政治与宏观日历
# 维护方式：手动编辑（热挂载，立即生效）
# date 格式：YYYY-MM-DD（确定日期）或 YYYY-MM-xx（月内待确认）
# importance: HIGH / MEDIUM / LOW
# category: MACRO / POLITICAL / GEO / TRADE / ENERGY
#
# ⚠️ 示例条目，请替换为真实日历

events:
  - date: "2026-01-01"
    name: "示例：某央行议息会议"
    category: MACRO
    importance: HIGH
    notes: "示例条目 — 请替换。可填写预期结果、关注点等"

  - date: "2026-03-xx"
    name: "示例：某重要会议（月内待定）"
    category: POLITICAL
    importance: MEDIUM
    notes: "日期未定时用 YYYY-MM-xx 格式"

  - date: "2026-06-15"
    name: "示例：某国选举 / 峰会"
    category: GEO
    importance: HIGH
    notes: "示例条目"
"""

# ── CSV：scorer.py 的危机匹配基准 ──
CSV_HEADER = ("crisis,start_date,end_date,type,severity,gdp_peak_trough_pct,"
              "unemp_peak_pct,sp500_drawdown_pct,pct_10y_trough,policy_key_rate_cut,"
              "policy_qe,recovery_years,oil_price_change_pct,inflation_peak_pct,"
              "credit_spread_peak_bp,yield_curve_min_pct,policy_response_months,"
              "key_lessons,crisis_category,taiwan_strait_relevance,vix_peak")
CSV_ROW = ("示例_资产泡沫破裂,2000-03,2002-10,示例类型,中,-1.5%,6.0%,-49%,3.5%,"
           "示例_基准利率下调,示例_未启用,2,示例_-20%,示例_3.0%,示例_+350bp,"
           "示例_-0.5%,示例_18,示例条目_请替换为你自己的研究内容,示例_不适用,示例_不适用,示例_40")
CSV_ROW2 = ("示例_供给冲击型衰退,2008-09,2009-06,示例类型,高,-4.0%,10.0%,-57%,2.0%,"
            "示例_快速降息,示例_已启用,4,示例_+50%,示例_5.0%,示例_+1800bp,"
            "示例_-0.2%,示例_12,示例条目_请替换,示例_不适用,示例_不适用,示例_80")

FILES["财经知识库/02_核心变量因果链/历史情景_量化指标.csv"] = (
    CSV_HEADER + "\n" + CSV_ROW + "\n" + CSV_ROW2 + "\n"
)

# ── JSON：mc_engine / monte_carlo_v2 的波动率校准参数 ──
_cal = {}
for _sym, _type in [("UNRATE", "rate"), ("GDPC1", "level"), ("CPIAUCSL", "level")]:
    _cal[_sym] = {
        "name": _sym, "type": _type,
        "full_sample_vol": 0.01, "full_mean_annual": 0.0,
        "vol_5y": None, "vol_1y": None,
        "normal_vol": 0.01, "crisis_vol": 0.03,
        "crisis_vol_ratio": 3.0, "current_vol": 0.01, "current_vol_pct": 33.0,
        "_note": "示例值，请用你的真实数据重新标定",
    }
_cal["_mc_calibration"] = {
    "UNRATE_monthly_std": 0.01, "UNRATE_crisis_multiplier": 3.0,
    "GDPC1_monthly_std": 0.005, "GDPC1_crisis_multiplier": 2.0,
    "CPIAUCSL_monthly_std": 0.002, "CPIAUCSL_crisis_multiplier": 2.0,
    "_note": "示例值（波动率校准），请替换",
}
FILES["财经知识库/02_核心变量因果链/波动率校准参数.json"] = (
    json.dumps(_cal, ensure_ascii=False, indent=2) + "\n")

# ── JSON：地缘事件日志 ──
_geo = {
    "meta": {"last_update": "2026-01-01", "count": 0,
             "_note": "示例结构；事件按 docs/KB_SETUP.md 的 schema 追加"},
    "schema": {
        "id": "E001 递增", "date": "YYYY-MM-DD", "event": "事件名",
        "summary": "简述", "key_signals": ["信号1", "信号2"],
        "risk_impact": "风险影响描述",
        "transmission_paths": ["传导路径1"],
        "active": True,
    },
    "events": [],
    "_note": "示例文件（events 为空）。请按 schema 追加你自己的地缘事件。",
}
FILES["财经知识库/02_核心变量因果链/地缘事件日志.json"] = (
    json.dumps(_geo, ensure_ascii=False, indent=2) + "\n")

# ── YAML：传导路径（hypothesis_engine / macro-ji 使用） ──
FILES["财经知识库/04_分析框架/propagation_paths.yaml"] = """# propagation_paths.yaml — 宏观情景传导路径知识库
# 供 hypothesis_engine.py 结构化注入 [PATHS] 节点使用
#
# 字段说明：
#   id:               唯一标识符
#   scenario_type:    对应 hypothesis_templates.yaml 的情景类型
#   subtype:          情景子类型
#   label:            人可读名称
#   calibration_score: 综合置信度 [0-1]
#   data_quality:     数据来源质量说明
#   causal_chain:     传导链步骤列表
#     - step:        步骤编号
#       event:       触发事件描述
#       lag_days:    传导时滞（天）
#       magnitude:   {base, range}
#       confidence:  该步置信度
#       source:      来源标注
#
# ⚠️ 以下为示例路径，请替换为你自己的研究结论

- id: example_oil_shock
  scenario_type: EXAMPLE
  subtype: SUPPLY_SHOCK
  label: 示例_油价冲击 → 通胀上行 → 加息 → 需求回落
  calibration_score: 0.50
  last_verified: 2026-01
  data_quality: 示例数据（请替换为你的历史验证记录）
  causal_chain:
    - step: 1
      event: 原油供给中断，油价大幅上行
      lag_days: 0
      magnitude: {base: 20, range: [10, 40]}
      confidence: 0.70
      source: example
    - step: 2
      event: 能源分项推升 CPI，通胀预期上行
      lag_days: 30
      magnitude: {base: 1.0, range: [0.3, 2.0]}
      confidence: 0.65
      source: example
    - step: 3
      event: 央行收紧，实际利率上行，需求回落
      lag_days: 90
      magnitude: {base: -0.5, range: [-1.5, 0.0]}
      confidence: 0.55
      source: example
"""

# ── .md：RAG 索引来源（只能 .md 进索引） ──
_MD_EXAMPLE = BANNER + """
# {title}

> 本文件为示例骨架，请替换为你的真实研究内容。
> 说明：知识库中的 `.md` 文件会被 `build_rag_index.py` 建立向量索引，
> 作为 LLM 分析的检索上下文；请把研究结论写在 `.md` 里。

## 一、指标体系

{body}

## 二、使用方法

1. 按本目录约定组织内容
2. 修改后重新构建索引：`docker exec <容器> python3 build_rag_index.py`
3. 索引会随检索请求生效，无需重启服务
"""

FILES["财经知识库/专题报告/2026全球宏观基准情景.md"] = _MD_EXAMPLE.format(
    title="2026 全球宏观基准情景（示例）",
    body="""在此写明你对主要经济体的基准判断：增长、通胀、政策路径、主要风险。

- 美国：（示例）增长放缓但未衰退，通胀缓慢回落，政策进入观察期
- 中国：（示例）结构性调整持续，政策以稳为主
- 欧元区：（示例）外需偏弱，财政约束上升

> 以上均为占位文字，**请替换**。""")

FILES["财经知识库/21_专题报告/2026全球宏观基准情景.md"] = _MD_EXAMPLE.format(
    title="2026 全球宏观基准情景（示例 · 数值更新目标）",
    body="""本文件与 `专题报告/2026全球宏观基准情景.md` 同源；`update_kb_numbers.py`
会尝试在本文件中按既定格式更新数值字段。

**请替换为你的真实研究内容。**""")

FILES["财经知识库/专题报告/15_金融体系脆弱性.md"] = _MD_EXAMPLE.format(
    title="金融体系脆弱性观察（示例）",
    body="""在此记录你对金融体系脆弱性的观察框架，例如：

- 信用利差与融资条件
- 银行体系杠杆与流动性
- 影子银行与期限错配

**请替换为你的真实研究内容。**""")

FILES["财经知识库/04_分析框架/央行决策框架.md"] = _MD_EXAMPLE.format(
    title="央行决策框架（示例）",
    body="""在此写明你使用央行反应函数的框架，例如泰勒规则的输入与阈值：

- 通胀缺口
- 产出/就业缺口
- 政策利率路径

**请替换为你的真实研究内容。**""")

FILES["财经知识库/04_分析框架/板块轮动与经济周期.md"] = _MD_EXAMPLE.format(
    title="板块轮动与经济周期（示例）",
    body="""在此记录经济周期与资产轮动的对应关系，例如：

- 复苏期 → 顺周期行业
- 过热期 → 大宗商品
- 衰退期 → 防御性资产

**请替换为你的真实研究内容。**""")

FILES["财经知识库/中国/中国信用脉冲与房地产周期.md"] = _MD_EXAMPLE.format(
    title="中国信用脉冲与房地产周期（示例）",
    body="""在此记录信用脉冲与房地产周期的传导关系与观察指标。

**请替换为你的真实研究内容。**""")

FILES["财经知识库/15_国际形势/示例_国际形势观察.md"] = _MD_EXAMPLE.format(
    title="国际形势观察（示例）",
    body="""在此记录国际形势的观察要点。该目录会被地缘政治检索模块扫描。

**请替换为你的真实研究内容。**""")

FILES["财经知识库/04_跨国联动矩阵/示例_跨国传导系数.md"] = _MD_EXAMPLE.format(
    title="跨国传导系数（示例）",
    body="""在此记录经济体之间的传导系数，例如中美在 GDP、油价、信用、关税等渠道的溢出强度。

**请替换为你的真实研究内容。**""")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="生成知识库骨架（示例内容，请替换为你的真实研究）")
    ap.add_argument("--dest", default=str(DEFAULT_DEST),
                    help=f"知识库根目录（默认 {DEFAULT_DEST}）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    ap.add_argument("--list", action="store_true", help="只列出将生成的文件")
    args = ap.parse_args()

    dest = Path(args.dest).expanduser().resolve()

    if args.list:
        print(f"目标: {dest}")
        for rel in sorted(FILES):
            print(f"  {rel}")
        return 0

    print("=" * 66)
    print("知识库骨架初始化")
    print("=" * 66)
    print(f"目标目录: {dest}")
    if dest.exists() and any(dest.iterdir()):
        print("⚠️  目标目录已存在且非空")
    print()

    created = skipped = 0
    for rel in sorted(FILES):
        fp = dest / rel
        if fp.exists() and not args.force:
            print(f"  ─ 已存在，跳过: {rel}")
            skipped += 1
            continue
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(FILES[rel], encoding="utf-8")
        print(f"  ✓ 生成: {rel}")
        created += 1

    print()
    print("=" * 66)
    print(f"完成：新建 {created} 个，跳过 {skipped} 个")
    print("=" * 66)
    print()
    print("下一步：")
    print(f"  1. 阅读 {dest / 'README.md'}")
    print("  2. 阅读 docs/KB_SETUP.md 了解各文件的格式要求")
    print("  3. 替换示例内容为你自己的研究")
    print("  4. 如需指定其他位置，在 .env 中设置 KB_ROOT=<知识库根目录>")
    print("  5. 构建 RAG 索引（可选，需 SILICONFLOW_API_KEY）：")
    print("       docker exec macro-scan-macro-scan-1 python3 build_rag_index.py")
    print()
    print("⚠️  生成内容均为示例，请勿直接用于生产判断。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
