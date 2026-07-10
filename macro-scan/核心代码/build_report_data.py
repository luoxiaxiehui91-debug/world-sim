"""
build_report_data.py — 知识库专题报告数据采集

B部分：从本地 fred_history/ 提取危机期间关键统计
C部分：tvly 网络搜索补充数据（可跳过）
输出：data/report_data/{topic}_data.json，供 Claude 撰写知识库报告

用法：
  python build_report_data.py --topic 2008金融海啸 --start 2007-06 --end 2010-12
  python build_report_data.py --topic 日本失去十年 --start 1989-01 --end 2003-12
  python build_report_data.py --topic 中国房地产危机 --start 2020-01 --end 2025-12
  python build_report_data.py --topic 美国财政可持续性 --start 2010-01 --end 2026-05
  python build_report_data.py --topic 2008金融海啸 --start 2007-06 --end 2010-12 --no-search
  python build_report_data.py --list-topics
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas 未安装，请运行: pip install pandas")
    sys.exit(1)

# ── 路径配置 ──────────────────────────────────────────────────────────────────

BASE_DIR    = os.environ.get("OPENCLAW_WORKSPACE",
              os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST_DIR    = os.path.join(BASE_DIR, "data", "fred_history")
OUTPUT_DIR  = os.path.join(BASE_DIR, "data", "report_data")

# ── 序列元数据 ────────────────────────────────────────────────────────────────

SERIES_META = {
    "DFF":          "联邦基金利率",
    "DGS10":        "10年期国债收益率",
    "DGS2":         "2年期国债收益率",
    "T10Y2Y":       "收益率曲线(10Y-2Y)",
    "CPIAUCSL":     "CPI(城市所有项目)",
    "PCEPI":        "核心PCE",
    "PPIACO":       "PPI(所有商品)",
    "GDPC1":        "实际GDP",
    "UNRATE":       "失业率",
    "PAYEMS":       "非农就业(千人)",
    "SP500":        "标普500",
    "DCOILWTICO":   "WTI原油",
    "BAA10Y":       "BAA-10Y信用利差",
    "BAMLH0A0HYM2": "高收益债利差",
    "M2SL":         "M2货币供应",
    "UMCSENT":      "消费者信心",
    "DTWEXBGS":     "贸易加权美元指数",
    "HOUST":        "新屋开工(千套)",
    "PERMIT":       "建筑许可(千套)",
    "INDPRO":       "工业产出指数",
}

# ── 预定义专题配置 ─────────────────────────────────────────────────────────────

TOPIC_CONFIG = {
    "2008金融海啸": {
        "desc": "2007-2009次贷危机与全球金融海啸",
        "start": "2007-06",
        "end": "2010-12",
        "series": ["DFF", "DGS10", "DGS2", "T10Y2Y", "BAA10Y", "BAMLH0A0HYM2",
                   "UNRATE", "CPIAUCSL", "GDPC1", "HOUST", "M2SL", "SP500",
                   "DCOILWTICO", "UMCSENT", "PAYEMS"],
        "queries": [
            "2008 financial crisis subprime mortgage CDO CDS mechanism statistics GDP decline",
            "Lehman Brothers collapse 2008 timeline contagion mechanism key dates",
            "Federal Reserve TARP QE1 response 2008 crisis Fed funds rate cut timeline",
        ],
        "notes": "SP500/BAMLH0A0HYM2 FRED本地历史不含2007年数据（FRED免费限制），数字需从web补充",
    },
    "日本失去十年": {
        "desc": "日本1990年代资产泡沫与资产负债表衰退",
        "start": "1989-01",
        "end": "2003-12",
        "series": ["DFF", "DGS10", "CPIAUCSL", "GDPC1", "UNRATE", "SP500",
                   "DCOILWTICO"],  # 美国对照数据；日本数据需从web获取
        "queries": [
            "Japan lost decade 1990 asset bubble Nikkei real estate GDP deflation statistics",
            "Japan bubble economy collapse 1990 land prices stock market peak statistics",
            "Bank of Japan zero interest rate policy 1999 deflation quantitative easing effectiveness",
        ],
        "notes": "FRED主要为美国数据，日本Nikkei/GDP/利率等需从web搜索补充；美国数据仅供对照",
    },
    "中国房地产危机": {
        "desc": "中国2021年以来房地产债务危机与内需压力",
        "start": "2020-01",
        "end": "2026-05",
        "series": ["DCOILWTICO", "DFF", "DGS10", "T10Y2Y", "DTWEXBGS",
                   "BAA10Y", "CPIAUCSL", "GDPC1"],
        "queries": [
            "China real estate crisis Evergrande Country Garden 2021 2024 GDP impact housing starts decline statistics",
            "China property sector debt 2023 2024 new home sales floor space investment decline data",
            "PBOC monetary policy 2023 2024 deflation CPI PPI China interest rate constraints",
        ],
        "notes": "中国国内数据(PMI/房价/GDP)不在FRED，全部依赖web搜索；FRED仅提供全球宏观背景",
    },
    "美国财政可持续性": {
        "desc": "美国债务上限、财政赤字与主权债务可持续性",
        "start": "2010-01",
        "end": "2026-05",
        "series": ["DFF", "DGS10", "DGS2", "T10Y2Y", "M2SL", "BAA10Y",
                   "BAMLH0A0HYM2", "CPIAUCSL", "GDPC1", "UNRATE"],
        "queries": [
            "US national debt GDP ratio 2024 2025 interest payments fiscal deficit CBO projections",
            "US debt ceiling crisis 2011 S&P downgrade 2023 Fitch downgrade market impact statistics",
            "US fiscal dominance debt spiral interest rate risk 2025 2026 sovereign debt sustainability",
        ],
        "notes": "FRED利率/信用利差数据完整；债务总量/利息占比/CBO预测需从web获取",
    },
}

# ── FRED 统计提取 ──────────────────────────────────────────────────────────────

def extract_fred_stats(series_id: str, start: str, end: str) -> dict | None:
    """提取单个 FRED 序列在指定时间段内的关键统计"""
    path = os.path.join(HIST_DIR, f"{series_id}.csv")
    if not os.path.exists(path):
        return None

    try:
        df = pd.read_csv(path).dropna(subset=["value"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        start_dt = pd.to_datetime(start)
        end_dt   = pd.to_datetime(end)

        # 危机期间数据
        mask = (df["date"] >= start_dt) & (df["date"] <= end_dt)
        crisis_df = df[mask].copy()
        if len(crisis_df) < 3:
            return None

        vals  = crisis_df["value"].tolist()
        dates = crisis_df["date"].dt.strftime("%Y-%m-%d").tolist()

        max_val  = max(vals)
        min_val  = min(vals)
        max_idx  = vals.index(max_val)
        min_idx  = vals.index(min_val)

        result = {
            "name":           SERIES_META.get(series_id, series_id),
            "data_range":     f"{dates[0]} ~ {dates[-1]}",
            "points":         len(vals),
            "start_val":      round(vals[0],  4),
            "end_val":        round(vals[-1], 4),
            "max_val":        round(max_val,  4),
            "max_date":       dates[max_idx],
            "min_val":        round(min_val,  4),
            "min_date":       dates[min_idx],
            "net_change":     round(vals[-1] - vals[0], 4),
            "net_change_pct": round((vals[-1] - vals[0]) / abs(vals[0]) * 100, 2) if vals[0] != 0 else None,
        }

        # 危机前12个月基线
        pre_start = (start_dt - pd.DateOffset(months=12)).strftime("%Y-%m-%d")
        pre_mask  = (df["date"] >= pre_start) & (df["date"] < start_dt)
        pre_df    = df[pre_mask]
        if not pre_df.empty:
            pre_mean = round(float(pre_df["value"].mean()), 4)
            result["pre_crisis_mean"] = pre_mean
            result["max_deviation_from_pre"] = round(max_val - pre_mean, 4)
            result["min_deviation_from_pre"] = round(min_val - pre_mean, 4)

        return result

    except Exception as e:
        return {"error": str(e)}


# ── tvly 网络搜索 ──────────────────────────────────────────────────────────────

def run_tvly_search(query: str) -> dict:
    """运行 tvly CLI 搜索，返回原始结果"""
    env = os.environ.copy()
    env["PYTHONUTF8"]        = "1"
    env["PYTHONIOENCODING"]  = "utf-8"
    # 代理仅在已有环境变量时继承，不强制注入 SAP proxy（在家/NAS 环境不需要）

    try:
        proc = subprocess.run(
            ["tvly", "search", "--json", query],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=45,
        )
        raw = proc.stdout.strip()
        if not raw and proc.stderr:
            return {"query": query, "status": "error", "raw": proc.stderr.strip()[:500]}

        # 尝试解析 JSON，否则保留原始文本
        try:
            data = json.loads(raw)
            return {"query": query, "status": "ok", "results": data}
        except json.JSONDecodeError:
            return {"query": query, "status": "ok", "raw_text": raw[:3000]}

    except subprocess.TimeoutExpired:
        return {"query": query, "status": "timeout"}
    except FileNotFoundError:
        return {"query": query, "status": "tvly_not_found",
                "hint": "tvly 未在 PATH 中，请运行: pip install tavily-python 并确认 tvly 命令可用"}
    except Exception as e:
        return {"query": query, "status": "error", "raw": str(e)}


# ── 主流程 ────────────────────────────────────────────────────────────────────

def build_report_data(topic: str, start: str, end: str, no_search: bool = False) -> dict:
    """采集专题报告数据（B+C步骤）：从本地 FRED 缓存提取统计值 + tvly 搜索，
    输出 JSON 文件并附 Claude 撰写提示，供后续人工触发 LLM 撰写 Markdown 专题报告。"""
    print(f"\n{'='*60}")
    print(f"专题：{topic}")
    print(f"时间范围：{start} ~ {end}")
    print(f"{'='*60}")

    config  = TOPIC_CONFIG.get(topic, {})
    series  = config.get("series", list(SERIES_META.keys()))
    queries = config.get("queries", [f"{topic} statistics GDP decline historical data"])
    notes   = config.get("notes", "")

    # ── B：FRED 统计提取 ───────────────────────────────────────────────────────
    print(f"\n[B] FRED 历史统计提取 ({len(series)} 个序列)...")
    fred_stats = {}
    missing    = []

    for sid in series:
        stats = extract_fred_stats(sid, start, end)
        if stats is None:
            missing.append(sid)
            print(f"  ✗ {sid:20s} — 本地无数据")
        elif "error" in stats:
            missing.append(sid)
            print(f"  ✗ {sid:20s} — {stats['error']}")
        else:
            fred_stats[sid] = stats
            name = stats["name"]
            print(f"  ✓ {sid:20s} {name:20s}  "
                  f"{stats['start_val']} → {stats['end_val']}  "
                  f"(max={stats['max_val']}@{stats['max_date']}, min={stats['min_val']}@{stats['min_date']})")

    print(f"\n  有效序列：{len(fred_stats)}，缺失：{len(missing)}")
    if missing:
        print(f"  缺失列表：{', '.join(missing)}")

    # ── C：tvly 网络搜索 ────────────────────────────────────────────────────────
    web_results = []
    if no_search:
        print(f"\n[C] 已跳过 tvly 搜索（--no-search）")
    else:
        print(f"\n[C] tvly 网络搜索 ({len(queries)} 条查询)...")
        for i, q in enumerate(queries, 1):
            print(f"  [{i}/{len(queries)}] {q[:70]}...")
            result = run_tvly_search(q)
            web_results.append(result)
            status = result.get("status", "?")
            if status == "ok":
                r_count = len(result.get("results", [])) if isinstance(result.get("results"), list) else "raw"
                print(f"         → {status} ({r_count} 条结果)")
            else:
                print(f"         → {status}: {result.get('hint', result.get('raw', ''))[:80]}")

    # ── 汇总输出 ───────────────────────────────────────────────────────────────
    output = {
        "topic":        topic,
        "period":       f"{start} ~ {end}",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "config_notes": notes,
        "fred_stats":   fred_stats,
        "fred_missing": missing,
        "web_search":   web_results,
        "write_prompt": _write_prompt(topic, start, end, notes, missing),
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe_name  = topic.replace("/", "_").replace(" ", "_")
    out_path   = os.path.join(OUTPUT_DIR, f"{safe_name}_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"输出：{out_path}")
    print(f"{'='*60}")
    print(f"\n[下一步] 运行以下命令让 Claude 撰写报告：")
    print(f"  读取 {out_path}")
    print(f"  参照 专题报告/09_1970年代滞胀全景.md 的格式写 {topic}.md")

    return output


def _write_prompt(topic: str, start: str, end: str, notes: str, missing: list) -> str:
    """生成给 Claude 的撰写提示"""
    prompt = f"""请基于本 JSON 文件中的 fred_stats 和 web_search 数据，
撰写《{topic}》专题报告（Markdown格式），放入知识库 专题报告/ 目录。

格式要求（参照 09_1970年代滞胀全景.md 和 10_1997亚洲金融危机.md）：
1. 标题 + 元数据（整理时间、数据来源）
2. 一、为什么值得研究 + 对2026年的意义
3. 二、结构性根源/背景（含时间线代码块）
4. 三、关键事件展开（含数据表格）
5. 四、政策应对与争议
6. 五、与其他危机的连锁（如有）
7. 六、复苏路径
8. 七、与2026年当前的对照表
9. 八、关键传导机制汇总（供 MC 模型参考）
10. 关联文件

注意：
- fred_stats 中的数字已从 FRED 原始数据提取，请直接使用，注明"FRED数据"
- web_search 中的数字注明搜索来源
- 缺失的 FRED 序列：{', '.join(missing) if missing else '无'}
- {notes if notes else '无特殊说明'}
"""
    return prompt


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    """CLI 入口：解析 --topic/--start/--end/--no-search 参数，调用 build_report_data。"""
    parser = argparse.ArgumentParser(description="知识库专题报告数据采集（B+C步骤）")
    parser.add_argument("--topic",     type=str, help="专题名称（见 --list-topics）")
    parser.add_argument("--start",     type=str, help="开始日期，格式 YYYY-MM 或 YYYY-MM-DD")
    parser.add_argument("--end",       type=str, help="结束日期，格式 YYYY-MM 或 YYYY-MM-DD")
    parser.add_argument("--no-search", action="store_true", help="跳过 tvly 网络搜索（仅提取 FRED 数据）")
    parser.add_argument("--list-topics", action="store_true", help="列出预定义专题")
    args = parser.parse_args()

    if args.list_topics:
        print(f"\n{'预定义专题':20s}  {'建议时间范围':22s}  说明")
        print("-" * 80)
        for name, cfg in TOPIC_CONFIG.items():
            print(f"{name:20s}  {cfg['start']} ~ {cfg['end']}  {cfg['desc']}")
        return

    if not args.topic:
        parser.error("请指定 --topic（或用 --list-topics 查看预定义专题）")

    # 使用预定义配置的默认时间范围
    cfg = TOPIC_CONFIG.get(args.topic, {})
    start = args.start or cfg.get("start")
    end   = args.end   or cfg.get("end")

    if not start or not end:
        parser.error("请指定 --start 和 --end（或使用预定义专题名称自动套用范围）")

    build_report_data(args.topic, start, end, no_search=args.no_search)


if __name__ == "__main__":
    main()
