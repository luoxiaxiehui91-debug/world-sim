"""
run.py — macro-sim v2 入口

用法：
    python run.py --daemon          守护模式：等待 sim_trigger.json 自动跑
    python run.py --run             手动触发一次完整仿真（校准+预测）
    python run.py --predict-only    跳过校准，直接用默认参数预测（快速测试用）
"""

import argparse
import json
import os
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path


NTFY_URL    = "https://ntfy.sh/***REMOVED***"
REPORT_DIR  = Path(os.environ.get("REPORT_DIR", "/app/reports"))
TRIGGER_PATH = Path("/app/macro_data/sim_trigger.json")


# ── 完整仿真流程 ──────────────────────────────────────────

def run_full_simulation(
    level: int = 2,
    event: str = "手动触发",
    config_path: str = "/app/config/agents.yaml",
    force_activate_all: bool = False,
    as_of_month: str | None = None,
) -> dict:
    """
    完整仿真：校准（前50步）+ 预测（后50步）。
    返回结果摘要。
    """
    from core.world_state import load_from_macro_scan
    from core.calibrator import run_calibration
    from core.bifurcation import run_prediction

    print(f"\n{'='*60}")
    print(f"macro-sim v2 仿真启动")
    print(f"触发：{event}（L{level}）{'  [全激活模式]' if force_activate_all else ''}"
          f"{'  政权情景 as_of=' + as_of_month if as_of_month else ''}")
    print(f"{'='*60}")

    # 08-17 政权分片：解析 as_of_month 对应的 regime 标签（报告展示用）
    regime_label = ""
    if as_of_month:
        try:
            from core.simulation import load_agents
            _ag, _ = load_agents(config_path, as_of_month=as_of_month)
            _labels = {a.soul.get("_regime_label", "") for a in _ag.values()
                       if a.soul and a.soul.get("_regime_label")}
            regime_label = "、".join(sorted(l for l in _labels if l))
            print(f"  政权情景：{regime_label or as_of_month}")
        except Exception as _e:
            print(f"  [regime] 标签解析跳过：{_e}")

    # ── 0. 加载军事背景卡片（SIPRI静态，注入推演context）────────
    military_backdrop = ""
    try:
        import sys as _sys, os as _os
        _backdrop_path = _os.path.join(
            _os.environ.get("OPENCLAW_WORKSPACE", "/workspace"),
            "data", "static", "military_backdrop.md"
        )
        if _os.path.exists(_backdrop_path):
            with open(_backdrop_path, encoding="utf-8") as _f:
                military_backdrop = _f.read()
            print(f"  [SIPRI] 军事背景卡片加载（{len(military_backdrop)}字符）")
    except Exception as _e:
        print(f"  [SIPRI] 背景卡片加载跳过：{_e}")

    # ── 1. 校准循环（前50个月历史）────────────────────────
    print("\n[1/3] 校准循环（前50个月历史数据拟合）...")
    calib_result = run_calibration(config_path=config_path)
    score = calib_result["score"]
    print(f"      校准评分：{score}/100")

    # ── 2. 加载当前真实状态（预测起点）──────────────────────
    print("\n[2/3] 加载当前真实状态...")
    world = load_from_macro_scan(situation_level=level)
    world.trigger_event = event
    print(f"      GRV={world.grv:.1f}  t10y2y={world.t10y2y:.1f}bp  "
          f"credit_spread={world.credit_spread:.0f}bp  dff={world.dff:.2f}%")

    # ── 3. 预测循环（后50个月）───────────────────────────
    print("\n[3/3] 预测循环（Monte Carlo × 100，预测未来50个月）...")
    paths = run_prediction(
        initial_world=world,
        calibrated_agent_params=calib_result["agents"],
        n_runs=100,
        predict_steps=24,
        config_path=config_path,
        force_activate_all=force_activate_all,
        as_of_month=as_of_month,
    )

    # ── 生成报告 ──────────────────────────────────────────
    report_path = _write_report(world, calib_result, paths, level, event, regime_label=regime_label)

    # ── 天玑存档钩子 ──────────────────────────────────────
    _archive_to_tianji(world, paths, calib_result, event, level, report_path)

    # ── ntfy 推送 ─────────────────────────────────────────
    _send_ntfy(world, calib_result, paths, report_path)

    return {
        "score":       score,
        "n_paths":     len(paths),
        "report_path": str(report_path) if report_path else None,
    }


def run_predict_only(
    level: int = 2,
    event: str = "快速测试",
    config_path: str = "/app/config/agents.yaml",
):
    """跳过校准，直接用默认参数预测（快速测试用）"""
    from core.world_state import load_from_macro_scan
    from core.bifurcation import run_prediction

    print("\n[predict-only] 跳过校准，使用默认Agent参数")
    world = load_from_macro_scan(situation_level=level)
    world.trigger_event = event

    paths = run_prediction(
        initial_world=world,
        calibrated_agent_params={},  # 空 = 使用 agents.yaml 默认值
        n_runs=100,
        predict_steps=24,
        config_path=config_path,
    )

    calib_result = {"score": 0, "avg_error": 0, "param_changes": [], "error_series": []}
    report_path = _write_report(world, calib_result, paths, level, event)
    _archive_to_tianji(world, paths, calib_result, event, level, report_path)

    _send_ntfy(world, calib_result, paths, report_path)


# ── 报告生成 ──────────────────────────────────────────────

def _read_version() -> str:
    for p in [Path(__file__).parent / "VERSION", Path("/app/VERSION")]:
        try:
            v = p.read_text().strip()
            if v:
                return v
        except Exception:
            pass
    return "?"


def _readable_trigger(event: str) -> str:
    """08-16：触发源可读化——占位值/空值转成人话，正常 GRV 触发原样保留。"""
    if not event or event == "自动触发":
        return "自动触发（GRV 超阈值）"
    if event == "初始状态":
        return "初始化触发（非 GRV 超阈值，sim_trigger 初始化/手动写入）"
    return event


def _write_report(world, calib_result: dict, paths: list, level: int, event: str,
                  regime_label: str = "") -> Path | None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    score    = calib_result.get("score", 0)
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")
    fname    = datetime.now().strftime("%Y-%m-%d_%H-%M") + f"_演化_L{level}_校准{score}.md"
    out_path = REPORT_DIR / fname

    # ── 参照值（用于判断高/低/升/降）──────────────────────
    GRV_HIST_P50 = 60.0   # 历史中位数估算
    GRV_HIST_P85 = 80.0   # 历史 p85 估算
    SPREAD_NORMAL = 150.0  # 正常信用利差基准

    def grv_label(v):
        if v >= 85:   return "极高压区"
        if v >= 70:   return "高压区"
        if v >= 50:   return "中等"
        return "低压"

    def sentiment_label(v):
        if v < -0.5:  return "深度压力"
        if v < -0.2:  return "温和压力"
        if v < 0.1:   return "基本中性"
        return "乐观"

    def arrow(start, end):
        diff = end - start
        if diff > 3:   return "↑"
        if diff < -3:  return "↓"
        return "→"

    # ── 已知因果关系 ──────────────────────────────────────
    TRIGGER_MAP = {
        "对冲基金大规模做空":         ["媒体放大恐慌情绪", "散户恐慌性抛售", "机构投资者降险"],
        "媒体放大恐慌情绪":           ["散户恐慌性抛售"],
        "散户恐慌性抛售":             ["商业银行收紧信贷"],
        "商业银行收紧信贷":           ["新兴市场实施资本管制", "OPEC+减产"],
        "美联储降息25bp":             ["欧央行降息25bp", "商业银行放松信贷"],
        "美联储紧急降息50bp":         ["欧央行降息25bp"],
        "日本央行放弃YCC（套息危机）": ["对冲基金大规模做空", "机构投资者降险"],
        "中国财政大规模刺激":         ["媒体保持中性报道"],
    }

    lines = [
        f"# 宏观演化仿真报告 — {now_str[:10]}",
        f"",
        f"**触发**：{_readable_trigger(event)}  |  **级别**：L{level}  |  "
        f"**预测范围**：未来 24 个月  |  "
        f"**校准**：{score}/100 {'✅' if score >= 60 else '⚠️'}"
        + (f"  |  **政权情景**：{regime_label}" if regime_label else ""),
        f"",
        f"---",
        f"",
        f"## 一、核心结论",
        f"",
    ]

    # GRV 当前定位描述
    grv_now = world.grv
    lines.append(
        f"GRV 当前 **{grv_now:.1f}**（{grv_label(grv_now)}，"
        f"{'高于' if grv_now >= GRV_HIST_P85 else '低于'} 历史 p85={GRV_HIST_P85:.0f}），"
        f"信用利差 {world.credit_spread:.0f}bp，收益率曲线斜率 {world.t10y2y:.0f}bp。"
    )
    lines.append("")

    # 路径对比表
    if paths:
        header = "| 维度 |" + "".join(f" {p.label}（{p.probability:.0%}） |" for p in paths)
        sep    = "|---|" + "---|" * len(paths)
        lines += [header, sep]

        # GRV 终值行（用各路径自己的起点做方向箭头）
        row = "| GRV 24个月后 |"
        for p in paths:
            a = arrow(p.initial_grv_mean, p.final_grv_mean)
            row += f" {p.final_grv_mean:.1f} {a}（{grv_label(p.final_grv_mean)}） |"
        lines.append(row)

        # 情绪行
        row = "| 市场情绪 |"
        for p in paths:
            row += f" {p.final_sentiment_mean:+.2f}（{sentiment_label(p.final_sentiment_mean)}） |"
        lines.append(row)

        # 信用利差行
        row = "| 信用利差 |"
        for p in paths:
            a = arrow(world.credit_spread, p.final_credit_spread_mean)
            row += f" {p.final_credit_spread_mean:.0f}bp {a} |"
        lines.append(row)

        # GRV 走势行
        row = "| 走势 |"
        for p in paths:
            row += f" {p.grv_trend} |"
        lines.append(row)

        # 关键驱动行（去重，取前两个不同 Agent 驱动）
        row = "| 主要驱动 |"
        for p in paths:
            # 简化事件名：去掉 Agent 名前缀（action_labels 里已含 Agent 语义，用 agent_name 替代）
            _ACTION_VERB = {
                "A1:CUT_50BP": "紧急降息50bp",  "A1:CUT_25BP": "降息25bp",
                "A1:HIKE_25BP": "加息25bp",     "A1:VERBAL_INTERVENTION": "口头干预",
                "A2:TIGHTEN_CREDIT": "收紧信贷", "A2:EASE_CREDIT": "放松信贷",
                "A3:SHORT_MARKET": "大规模做空", "A3:DECREASE_RISK": "降险",
                "A3:INCREASE_RISK": "加仓做多",  "A4:CUT_SUPPLY": "减产",
                "A4:INCREASE_SUPPLY": "增产",    "A5:DECREASE_RISK": "降险",
                "A5:INCREASE_RISK": "加仓",      "A6:AMPLIFY_FEAR": "放大恐慌",
                "A6:AMPLIFY_OPTIMISM": "放大乐观","A7:CAPITAL_CONTROLS": "资本管制",
                "A7:RAISE_RATES": "加息",        "A7:CUT_25BP": "降息",
                "A8:CUT_RRR": "降准",            "A8:CUT_LPR": "降LPR",
                "A8:FISCAL_STIMULUS_CN": "财政刺激","A8:CNY_INTERVENTION": "汇率干预",
                "A8:TIGHTEN_CN": "货币收紧",     "A9:FISCAL_STIMULUS": "财政刺激",
                "A9:DEBT_CEILING_RISK": "债务上限危机","A9:FISCAL_TIGHTEN": "财政收紧",
                "A10:PANIC_SELL": "恐慌性抛售",  "A10:FOMO_BUY": "追涨买入",
                "A11:CUT_25BP": "降息25bp",      "A11:HIKE_25BP": "加息25bp",
                "A11:QE_EXPAND": "扩大QE",                       "A12:ABANDON_YCC": "放弃YCC",
                "A12:EASE_YCC": "放松YCC",       "A12:EMERGENCY_EASE": "紧急宽松",
                "A13:INCREASE_RISK": "逆向抄底",  "A13:DECREASE_RISK": "温和降险",
            }
            seen, top = set(), []
            for ev in p.key_events:
                aid = ev.get("agent_id", "")
                aname = ev.get("agent_name", "")
                verb = _ACTION_VERB.get(f"{aid}:{ev.get('action', '')}", ev["event"])
                label = f"{aname}·{verb}" if aname else ev["event"]
                if label not in seen:
                    seen.add(label)
                    top.append(label)
                if len(top) == 2:
                    break
            row += f" {'、'.join(top) if top else '—'} |"
        lines.append(row)

        lines.append("")

    # ── 08-17 政权更迭事件（跨 100 runs 聚合统计）────────────────
    gov_stats = next((getattr(p, "governance_stats", {}) for p in paths
                      if getattr(p, "governance_stats", {})), {})
    if gov_stats:
        AGENT_CN = {"S1_usa": "美国", "S2_china": "中国", "S3_eu": "欧盟",
                    "S4_russia": "俄罗斯", "S5_saudi": "沙特",
                    "S6_japan": "日本", "S7_korea": "韩国"}
        lines += ["---", "", "## 政权更迭事件（Monte Carlo 100 runs 聚合）", ""]
        for aid, st in gov_stats.items():
            t_t = st.get("election_transition", 0)
            t_h = st.get("election_hold", 0)
            t_b = st.get("succession_break", 0)
            runs = st.get("runs_triggered", 0)
            total = t_t + t_h + t_b
            if total == 0:
                continue
            pct = lambda n: f"{n / total * 100:.0f}%"
            # run 级触发率（100 runs 中多少 run 发生实质更迭）
            runs_pct = f"{runs / 100.0 * 100:.0f}%" if runs else "0%"
            months = sorted({m for m in st.get("months", []) if m})
            detail = []
            if t_t:
                detail.append(f"换届转向 {pct(t_t)}")
            if t_h:
                detail.append(f"换届延续 {pct(t_h)}")
            if t_b:
                detail.append(f"继承/政变 {pct(t_b)}")
            labels = list(dict.fromkeys(st.get("labels", [])))[:2]
            lines.append(
                f"- **{AGENT_CN.get(aid, aid)}**：{'；'.join(detail)}"
                f"（月 {'、'.join(str(m) for m in months)}；"
                f"{runs_pct} runs 发生实质更迭）"
                + (f" — {' / '.join(labels)}" if labels else "")
            )
        lines.append("")

    lines += [
        f"---",
        f"",
        f"## 二、路径详情",
        f"",
    ]

    # ── 各路径详情 ────────────────────────────────────────
    for path in paths:
        lines += [
            f"### {path.label}（{path.probability:.0%}）— {path.grv_trend}",
            f"",
            f"起点 GRV {path.initial_grv_mean:.1f} → 终点 {path.final_grv_mean:.1f}"
            f"（{grv_label(path.final_grv_mean)}），"
            f"情绪 {path.final_sentiment_mean:+.2f}，信用利差 {path.final_credit_spread_mean:.0f}bp",
            f"",
        ]

        if path.key_events:
            lines.append("**传导链**：")
            lines.append("")
            lines.append("```")

            events_by_step = {}
            for ev in path.key_events:
                events_by_step.setdefault(ev["step"], []).append(ev)

            prev_events = set()
            for step in sorted(events_by_step):
                step_evs = events_by_step[step]
                for ev in step_evs:
                    name = ev["event"]
                    freq = ev["frequency"]
                    agent_name = ev.get("agent_name", "")
                    agent_tag = f"[{agent_name}] " if agent_name else ""
                    triggered_by = next(
                        (p for p in prev_events if name in TRIGGER_MAP.get(p, [])),
                        None
                    )
                    if triggered_by:
                        short = triggered_by[:12] + ".." if len(triggered_by) > 14 else triggered_by
                        lines.append(f"  {ev['month']:5s}  ↳ {agent_tag}{name}（{freq:.0%}）← {short}")
                    else:
                        lines.append(f"  {ev['month']:5s}    {agent_tag}{name}（{freq:.0%}）")
                prev_events = {ev["event"] for ev in step_evs}

            lines.append("```")
            lines.append("")

        if path.narrative:
            from core.narrative_format import format_narrative
            lines += format_narrative(path.narrative)

        # 08-16 Agent 参与度（24 个月 × N runs 聚合）：谁动了、动了几次、谁在静默
        if path.agent_participation:
            lines.append("")
            lines.append("**Agent 参与度**（24 个月 × 该路径 runs 聚合；行动=真正产出动作的步）")
            lines.append("")
            lines.append("| Agent | 行动次数 | 行动步数/24 | 无行动步数 | 主要行动 |")
            lines.append("|-------|:--------:|:----------:|:----------:|---------|")
            for aid, st in path.agent_participation.items():
                top_acts = []
                for act, cnt in list(st["actions"].items())[:2]:
                    verb = _ACTION_VERB.get(f"{aid}:{act}", act)
                    top_acts.append(f"{verb}×{cnt}")
                lines.append(
                    f"| {st['name']} | {st['acts']} | {st['steps']} | {st['silent_steps']} "
                    f"| {'、'.join(top_acts) or '—'} |"
                )
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── 月度演化进度条 ────────────────────────────────────
    if paths and any(p.monthly_grv for p in paths):
        lines += [
            f"## 三、月度演化进度条",
            f"",
            f"> 每行 = 1个月。GRV 值为该路径 Monte Carlo 样本均值。触发原因来自静态传导知识库。",
            f"",
        ]

        # 推算预测起始月（YYYY-MM）
        from datetime import timedelta
        start_dt = datetime.now().replace(day=1)
        # 起始月标签列表：月 +1 → 月 +N
        def month_label(offset: int) -> str:
            y = start_dt.year + (start_dt.month - 1 + offset) // 12
            m = (start_dt.month - 1 + offset) % 12 + 1
            return f"{y}-{m:02d}"

        # 把 key_events 按 step 建索引（每条路径独立）
        def events_index(path):
            idx = {}
            for ev in path.key_events:
                idx.setdefault(ev["step"], []).append(ev)
            return idx

        # 触发原因：静态表 + 动态补充
        TRIGGER_REASONS_STATIC = {
            "对冲基金大规模做空":         f"GRV突破高压阈值，机构做空信号触发",
            "对冲基金降险":               "市场情绪恶化，主动降低风险敞口",
            "商业银行收紧信贷":           "做空/恐慌引发流动性担忧",
            "散户恐慌性抛售":             "媒体恐慌放大 / 做空信号外溢",
            "媒体放大恐慌情绪":           "GRV高位 + 情绪下行，负面报道增加",
            "媒体保持中性报道":           "GRV未突破极端阈值，情绪相对平稳",
            "美联储降息25bp":             "情绪恶化 + 利差扩大，触发政策响应",
            "美联储紧急降息50bp":         "市场深度压力，触发紧急宽松",
            "美联储加息25bp":             "通胀压力持续，收紧货币",
            "美联储口头干预":             "GRV高位但情绪尚可，言语安抚",
            "新兴市场实施资本管制":       "美元利率压力 + 信贷收紧引发资本外流",
            "新兴市场央行加息":           "资本外流压力 + 汇率贬值风险",
            "日本央行放弃YCC（套息危机）": "美联储加息积压，套息交易强制平仓",
            "日本央行放松YCC上限":        "国债收益率压力上升，被动调整",
            "日本央行紧急宽松":           "套息平仓冲击流动性，紧急响应",
            "中国财政大规模刺激":         "国内信用收缩，逆周期财政托底",
            "中国央行降准":              "信用脉冲收缩，降准释放流动性",
            "中国央行降LPR":             "实体融资成本高企，引导利率下行",
            "中国央行汇率干预":           "资本外流 + 人民币贬值压力",
            "欧央行降息25bp":             "跟随美联储宽松周期",
            "欧央行扩大QE":              "欧元区经济下行压力加大",
            "OPEC+减产":                 "全球需求预期下降，能源国保价减产",
            "OPEC+增产":                 "地缘缓和 + 市场份额竞争",
            "机构投资者降险":             "波动性上升，组合对冲压力",
            "机构投资者加仓":             "估值回落，风险溢价修复",
            "美国财政刺激":               "经济下行压力 + 政治周期",
            "美国债务上限危机信号":        "财政谈判僵局，违约风险上升",
            "美国财政收紧":               "通胀压力 + 债务可持续性考量",
            "散户追涨买入":               "市场回暖，FOMO情绪触发",
        }

        # 计算分叉点：找第一个路径间 GRV 差距 > 5 的步骤
        fork_step = None
        if len(paths) > 1:
            max_steps = min(len(p.monthly_grv) for p in paths)
            for s in range(max_steps):
                grvs = [p.monthly_grv[s] for p in paths]
                if max(grvs) - min(grvs) > 5.0:
                    fork_step = s
                    break

        if fork_step is not None:
            lines += [
                f"**分叉点**：月 +{fork_step+1}（{month_label(fork_step)}）之前各路径走势基本一致，"
                f"之后开始分化。",
                f"",
            ]

        for path in paths:
            if not path.monthly_grv:
                continue
            ev_idx = events_index(path)
            n_steps = len(path.monthly_grv)

            lines += [
                f"### {path.label}（{path.probability:.0%}）— {path.grv_trend}",
                f"",
                f"```",
            ]

            prev_grv = world.grv   # 用全局起点作第 0 步前值
            for step in range(n_steps):
                grv_now = path.monthly_grv[step]
                diff = grv_now - prev_grv
                a = "↑" if diff > 2 else ("↓" if diff < -2 else "→")
                label = month_label(step)
                sentiment_now = path.monthly_sentiment[step] if path.monthly_sentiment else None
                sent_str = f"  情绪{sentiment_now:+.2f}" if sentiment_now is not None else ""

                header = f"月 +{step+1:2d}（{label}）： GRV {prev_grv:.1f} → {grv_now:.1f} {a}{sent_str}"
                lines.append(header)

                step_events = ev_idx.get(step, [])
                for ev in step_events:
                    reason = TRIGGER_REASONS_STATIC.get(ev["event"], "")
                    reason_str = f"  [因：{reason}]" if reason else ""
                    freq_str = f"  （{ev['frequency']:.0%}路径）"
                    agent_name = ev.get("agent_name", "")
                    agent_tag = f"[{agent_name}] " if agent_name else ""
                    lines.append(f"  · {agent_tag}{ev['event']}{freq_str}{reason_str}")

                prev_grv = grv_now

            lines.append("```")
            lines.append("")

    # ── 校准说明（放最后）────────────────────────────────
    lines += [
        f"## 四、校准说明",
        f"",
        f"评分 {score}/100，平均误差 {calib_result.get('avg_error', 0):.4f}，"
        f"参数调整 {len(calib_result.get('param_changes', []))} 次。",
        f"校准期：2022-06 至 2026-07（{calib_result.get('calib_steps', 50)} 个月）。",
        f"",
    ]

    if calib_result.get("param_changes"):
        lines.append("**近期主要调整**：")
        lines.append("")
        for ch in calib_result["param_changes"][-3:]:
            lines.append(
                f"- `{ch['agent']}.{ch['param']}` {ch['old']} → {ch['new']}  "
                f"（{ch['step']}，{ch.get('reason', '')}）"
            )
        lines.append("")

    lines += [
        f"---",
        f"",
        f"*macro-sim {_read_version()} | 每步=1个月 | Monte Carlo × 100*",
    ]

    try:
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n报告已写入：{out_path}")
        return out_path
    except Exception as e:
        print(f"[警告] 报告写入失败：{e}")
        return None


# ── 天玑存档钩子（P0-D2: SQLite → PG tianji schema）───────────────────────

_PG_CONN = None  # 模块级缓存连接（连接丢失自动重连）


def _pg_connect_with_retry(psycopg_mod, pw: str):
    """建立 psycopg 连接，失败重试 3 次指数退避（2^0 / 2^1 / 2^2 秒）。"""
    last_err = None
    for attempt in range(3):
        try:
            return psycopg_mod.connect(
                host="worldsim-pg",
                port=5432,
                dbname="worldsim",
                user="worldsim_app",
                password=pw,
                options="-c search_path=tianji,public",
            )
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"连接 worldsim-pg 失败（重试 3 次）：{last_err}")


def _pg_conn():
    """返回 PG 连接（search_path=tianji,public）；模块级缓存，连接丢失自动重连。

    psycopg 未安装或 WORLDSIM_APP_PW 缺失 → raise RuntimeError（fail-fast，不静默）。
    """
    global _PG_CONN
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError(
            f"psycopg 未安装，无法连接 worldsim-pg（P0-D2 需 psycopg[binary]>=3.1）：{e}"
        ) from e
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        raise RuntimeError("WORLDSIM_APP_PW 未注入，无法连接 worldsim-pg（fail-fast，不静默）")
    if _PG_CONN is None or _PG_CONN.closed:
        _PG_CONN = _pg_connect_with_retry(psycopg, pw)
    return _PG_CONN


def _invalidate_pg_conn():
    """A1 (2026-08-15, QA 实测): 失效模块级缓存连接，置 None。

    事务失败后连接处于 aborted 态（InFailedSqlTransaction），psycopg 要求先 rollback
    才能继续；若缓存仍指向已关/aborted 连接，daemon 周期存档会持续失败。置 None 后
    下次 _pg_conn() 重建新连接（自愈）。
    """
    global _PG_CONN
    _PG_CONN = None


def _archive_to_tianji(world, paths: list, calib_result: dict, event: str, level: int, report_path):
    """
    推演完成后把可验证预测写入 PG tianji.predictions / reasoning_trace（P0-D2 转 PG）。
    失败时 ntfy 告警 + return，不阻断主流程（保留去静默语义）。
    """
    import json as _json
    from datetime import timedelta, timezone

    try:
        conn = _pg_conn()
    except Exception as e:
        print(f"[tianji] 无法连接 worldsim-pg：{e}")
        try:
            _send_ntfy_simple("天璇预测存档失败", f"无法连接 worldsim-pg：{e}\nscenario 未落表，玉衡反馈链将无样本。")
        except Exception:
            pass
        return

    try:
        now = datetime.now(timezone.utc)  # aware，psycopg 写 TIMESTAMPTZ 必须 aware（防 TZ 差 8h）
        scenario_id = f"sim_{now.strftime('%Y%m%d_%H%M')}_{event[:20]}"
        archived = 0

        def _prediction_id(ptype: str, path_label: str) -> str:
            """M31 修复：确定性主键（scenario + 路径 + 类型哈希）——
            原 uuid4 每次不同，ON CONFLICT(id) DO NOTHING 恒 no-op → 同 scenario 重跑
            插重复行；确定性 id 使同 scenario 内重试/重跑真正去重。"""
            import hashlib as _h
            return "p-" + _h.sha1(
                f"{scenario_id}|{path_label}|{ptype}".encode("utf-8")
            ).hexdigest()[:24]

        for path in paths:
            if path.probability < 0.05:
                continue

            # ── 1. GRV 方向性预测（自动验证，3 个月时间窗口）────────────────
            if hasattr(path, "final_grv_mean") and path.final_grv_mean is not None:
                grv_diff = path.final_grv_mean - world.grv
                if grv_diff > 5:
                    direction, conf_tier = "up", "HIGH" if path.probability > 0.3 else "LOW"
                elif grv_diff < -5:
                    direction, conf_tier = "down", "HIGH" if path.probability > 0.3 else "LOW"
                else:
                    direction, conf_tier = "neutral", "VERY_LOW"

                due_at = (now + timedelta(days=90)).isoformat()  # 3 个月验证窗口
                pred_id = _prediction_id("grv", path.label)

                conn.execute("""
                    INSERT INTO predictions
                      (id, created_at, due_at, scenario_id, type, prediction_target_type,
                       content, outcome_definition, target_metric, target_direction,
                       target_threshold, b_prob, b_sample_count,
                       final_prob, confidence_tier, time_horizon, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO NOTHING
                """, (
                    pred_id,
                    now.isoformat(),
                    due_at,
                    scenario_id,
                    "quantitative",
                    "grv_direction",
                    (f"{event} 情景下，{path.label}路径（{path.probability:.0%}）："
                     f"3个月后 GRV global_composite 预计 {direction}（当前 {world.grv:.1f}，"
                     f"仿真终值 {path.final_grv_mean:.1f}）"),
                    (f"3个月后 grv_history.jsonl 中 global_composite 变化幅度"
                     f"{'超过' if direction != 'neutral' else '不超过'} +5/-5 阈值"),
                    "global_composite",  # D12 fix: target_metric 与 content/outcome_definition 一致
                    direction,
                    round(world.grv, 1),          # target_threshold = 当前基准
                    round(path.probability, 4),    # b_prob
                    100,                           # b_sample_count = MC 次数
                    round(path.probability, 4),    # final_prob
                    conf_tier,
                    "quarterly",
                    "pending",
                ))

                # 推理溯源
                causal_chains = [
                    {"chain_id": f"chain_{i:02d}",
                     "nodes": [ev.get("event", ""), "GRV变化"],
                     "confidence": ev.get("frequency", 0.5),
                     "source": "simulation"}
                    for i, ev in enumerate(path.key_events[:5])
                ]
                conn.execute("""
                    INSERT INTO reasoning_trace
                      (prediction_id, agent_id, input_signals, historical_match,
                       confidence_basis, llm_adjustment, causal_chains, reasoning)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    pred_id,
                    "macro-sim",
                    _json.dumps([
                        {"signal_name": "grv",           "value": world.grv,           "weight": 1.0},
                        {"signal_name": "credit_spread",  "value": world.credit_spread, "weight": 0.5},
                        {"signal_name": "t10y2y",         "value": world.t10y2y,        "weight": 0.3},
                    ], ensure_ascii=False),
                    f"校准评分{calib_result.get('score', 0)}/100",
                    "historical_freq",
                    0.0,
                    _json.dumps(causal_chains, ensure_ascii=False),
                    f"仿真路径：{path.label}，触发事件：{event}，GRV变化{grv_diff:+.1f}",
                ))
                archived += 1

            # ── 2. 地缘关键事件（人工验证，6 个月窗口）──────────────────────
            for ev in path.key_events[:2]:
                if ev.get("frequency", 0) < 0.2:
                    continue
                # M31 修复：确定性主键（含事件名，同 scenario 重跑去重）
                geo_id = _prediction_id("geo", f"{path.label}|{ev.get('event', '')}")
                # 08-18 描述清晰化：content 带路径 GRV 上下文；outcome_definition 带现实判定标准
                grv_ctx = ""
                grv_end = getattr(path, "final_grv_mean", None)
                if grv_end is not None and hasattr(world, "grv"):
                    grv_ctx = f"（GRV {world.grv:.0f}→{grv_end:.0f}）"
                content = (f"{path.label}路径{grv_ctx}：{ev.get('event', '')} "
                           f"（仿真频率{ev.get('frequency', 0):.0%}）")
                _crit = ev.get("criterion") or ""
                outcome = f"6个月内是否发生：{ev.get('event', '')}"
                if _crit:
                    outcome += f"。判定标准：{_crit}"
                # 08-18 动作 key 落库（自动验证分派用，不依赖中文名反查）
                _a_key = f"{ev.get('agent_id', '')}:{ev.get('action', '')}"
                conn.execute("""
                    INSERT INTO predictions
                      (id, created_at, due_at, scenario_id, type, prediction_target_type,
                       content, outcome_definition, action_key,
                       final_prob, confidence_tier, time_horizon, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'awaiting_human')
                    ON CONFLICT (id) DO NOTHING
                """, (
                    geo_id,
                    now.isoformat(),
                    (now + timedelta(days=180)).isoformat(),
                    scenario_id,
                    "geopolitical",
                    "geopolitical_event",
                    content,
                    outcome,
                    _a_key if _a_key != ":" else None,
                    round(ev.get("frequency", 0.5), 4),
                    "LOW",
                    "monthly",
                ))
                archived += 1

        conn.commit()
        print(f"[tianji] ✅ 存档 {archived} 条预测 → PG tianji.predictions  scenario_id={scenario_id}")

    except Exception as e:
        print(f"[tianji] 存档失败（不影响主流程）：{e}")
        import traceback; traceback.print_exc()
        # A1 (2026-08-15, QA 实测): 事务失败后连接处于 aborted 态（InFailedSqlTransaction），
        # psycopg 要求先 rollback 才能继续——先 rollback 清 aborted 事务（close 前安全收尾），
        # 模块级缓存由 finally 统一失效，下次 _pg_conn() 重建新连接（自愈）。
        try:
            conn.rollback()
        except Exception:
            pass
        # P0-D D4 (2026-08-15, 全量审查 H20 去静默): 存档失败不再静默——
        # 之前宽 except 吞错导致"仿真成功但 0 条落表"数月无人察觉。
        try:
            _send_ntfy_simple("天璇预测存档失败", f"{e}\nscenario 未落表，玉衡反馈链将无样本。")
        except Exception:
            pass
    finally:
        conn.close()
        _invalidate_pg_conn()  # A1: close 后同步清缓存，避免缓存仍指向已关/aborted 连接


# ── 天玑 V1 评分 ──────────────────────────────────────────



# ── ntfy 推送 ─────────────────────────────────────────────

def _send_ntfy_simple(title: str, message: str):
    """轻量 ntfy 推送（天玑评分等单行通知用）。"""
    try:
        req = urllib.request.Request(
            NTFY_URL,
            data=json.dumps({"title": title, "message": message}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception as e:
        print(f"[天玑] ntfy 推送失败: {e}")


def _send_ntfy(world, calib_result: dict, paths: list, report_path=None):
    score = calib_result.get("score", 0)
    score_str = f"校准{score}分" if score > 0 else "跳过校准"

    path_summaries = []
    for p in paths:
        path_summaries.append(
            f"{p.label}（{p.probability:.0%}）：GRV{p.grv_trend}至{p.final_grv_mean:.0f}"
        )

    report_note = f"\n报告：{report_path.name}" if report_path else ""

    body = (
        f"🌐 宏观演化仿真完成（{score_str}）\n"
        f"起点：GRV={world.grv:.1f}  利差={world.credit_spread:.0f}bp\n"
        f"预测未来2年（每步=1个月）：\n"
        + "\n".join(path_summaries)
        + report_note
    )

    try:
        req = urllib.request.Request(
            NTFY_URL,
            data=body.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
        print("ntfy 推送成功")
    except Exception as e:
        print(f"[警告] ntfy 推送失败：{e}")


# ── 入口 ──────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="macro-sim v2 宏观演化仿真")
    parser.add_argument("--daemon",       action="store_true", help="守护模式")
    parser.add_argument("--run",          action="store_true", help="手动触发一次完整仿真")
    parser.add_argument("--predict-only", action="store_true", help="跳过校准直接预测（测试）")
    parser.add_argument("--level",        type=int, default=2)
    parser.add_argument("--event",        type=str, default="手动触发")
    parser.add_argument("--force-activate-all", action="store_true",
                        help="试验：跳过 activation_prob 掷骰，每步给所有 Agent 决策机会（保留冷却）")
    parser.add_argument("--as-of", type=str, default=None, metavar="YYYY-MM",
                        help="政权情景：预测期使用该月的 soul regime（如 2026-08=现行 / 2027-01=更迭后）")
    args = parser.parse_args()

    CONFIG_PATH = str(Path(__file__).parent / "config/agents.yaml")

    if args.daemon:
        print(f"[daemon] macro-sim v2 守护模式启动，轮询 {TRIGGER_PATH}")
        while True:
            if TRIGGER_PATH.exists() and TRIGGER_PATH.stat().st_size > 0:
                try:
                    trigger_data = json.loads(TRIGGER_PATH.read_text())
                    # ⛔ 08-16 21:4x 修复（死循环）：H18 契约下触发判定必须是
                    # triggered == true——原"文件存在且 >0 字节即触发"与"写回
                    # 已消费合法 JSON（存在且 >0 字节）"冲突 → 每次跑完写回又
                    # 触发 → 每 ~2 分钟跑一次完整仿真 + 推一条 ntfy（实测 13:24
                    # 起 9+ 次）。已消费态（triggered:false）必须跳过。
                    if trigger_data.get("triggered") is not True:
                        time.sleep(10)
                        continue
                    level  = int(trigger_data.get("level", 2))
                    event  = trigger_data.get("event", "自动触发")
                    print(f"[daemon] 触发：L{level} — {event}")
                    # H18 (2026-08-16, 全量审查): 清空改写"已消费"状态——原 write_text("")
                    # 把文件变 0 字节，开阳前端当持久状态 fetch → JSON.parse('') 崩 →
                    # '读取失败:sim_trigger.json'。新契约：sim_trigger.json 永远合法 JSON
                    # （触发态 triggered:true / 已消费态 consumed:true + last 信息），
                    # 开阳可显示"上次触发已消费"而不报错。写失败不影响仿真主流程。
                    try:
                        TRIGGER_PATH.write_text(json.dumps({
                            "schema_version": "1.0",
                            "triggered":      False,
                            "consumed":       True,
                            "level":          level,
                            "event":          event,
                            "reason":         event,
                            "triggered_at":   trigger_data.get("triggered_at"),
                            "consumed_at":    datetime.now(timezone.utc).isoformat(),
                        }, ensure_ascii=False), encoding="utf-8")
                    except Exception:
                        pass
                    run_full_simulation(level=level, event=event, config_path=CONFIG_PATH,
                                        force_activate_all=args.force_activate_all,
                                        as_of_month=args.as_of)
                except Exception as e:
                    print(f"[daemon] 仿真失败：{e}")
                    try:
                        req = urllib.request.Request(
                            NTFY_URL,
                            data=f"[macro-sim v2] 仿真失败：{e}".encode("utf-8"),
                            headers={"Content-Type": "text/plain; charset=utf-8"},
                            method="POST",
                        )
                        with urllib.request.urlopen(req, timeout=5):
                            pass
                    except Exception:
                        pass
            time.sleep(60)

    elif args.run:
        run_full_simulation(level=args.level, event=args.event, config_path=CONFIG_PATH,
                            force_activate_all=args.force_activate_all,
                            as_of_month=args.as_of)

    elif args.predict_only:
        run_predict_only(level=args.level, event=args.event, config_path=CONFIG_PATH)

    else:
        parser.print_help()
