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


NTFY_URL    = "http://192.168.31.108:2586/macro-tsx-9005"
REPORT_DIR  = Path(os.environ.get("REPORT_DIR", "/app/reports"))
TRIGGER_PATH = Path("/app/sim_trigger.json")


# ── 完整仿真流程 ──────────────────────────────────────────

def run_full_simulation(
    level: int = 2,
    event: str = "手动触发",
    config_path: str = "/app/config/agents.yaml",
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
    print(f"触发：{event}（L{level}）")
    print(f"{'='*60}")

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
    )

    # ── 生成报告 ──────────────────────────────────────────
    report_path = _write_report(world, calib_result, paths, level, event)

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


def _write_report(world, calib_result: dict, paths: list, level: int, event: str) -> Path | None:
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
        f"**触发**：{event}  |  **级别**：L{level}  |  "
        f"**预测范围**：未来 24 个月  |  "
        f"**校准**：{score}/100 {'✅' if score >= 60 else '⚠️'}",
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

        # 关键驱动行（去重，取前两个不同事件）
        row = "| 主要驱动 |"
        for p in paths:
            seen, top = set(), []
            for ev in p.key_events:
                if ev["event"] not in seen:
                    seen.add(ev["event"])
                    top.append(ev["event"])
                if len(top) == 2:
                    break
            row += f" {'、'.join(top) if top else '—'} |"
        lines.append(row)

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
                    triggered_by = next(
                        (p for p in prev_events if name in TRIGGER_MAP.get(p, [])),
                        None
                    )
                    if triggered_by:
                        short = triggered_by[:12] + ".." if len(triggered_by) > 14 else triggered_by
                        lines.append(f"  {ev['month']:5s}  ↳ {name}（{freq:.0%}）← {short}")
                    else:
                        lines.append(f"  {ev['month']:5s}    {name}（{freq:.0%}）")
                prev_events = {ev["event"] for ev in step_evs}

            lines.append("```")
            lines.append("")

        if path.narrative:
            import re as _re
            # 清理 LLM 可能输出的数字前缀（"1. " "2.\n" 等）
            narrative = _re.sub(r'\n\d+\.\s*\n?', '\n', path.narrative).strip()
            parts  = _re.split(r'【[^】]+】', narrative)
            labels = _re.findall(r'【([^】]+)】', narrative)
            if len(labels) >= 2 and len(parts) >= 2:
                lines.append("")
                for label, content in zip(labels, parts[1:]):
                    content = content.strip().lstrip('：:').strip()
                    if content:
                        lines.append(f"**{label}**：{content}")
                lines.append("")
            else:
                lines += ["", narrative, ""]

        lines.append("---")
        lines.append("")

    # ── 校准说明（放最后）────────────────────────────────
    lines += [
        f"## 三、校准说明",
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


# ── ntfy 推送 ─────────────────────────────────────────────

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
        f"预测未来4年（每步=1个月）：\n"
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
    args = parser.parse_args()

    CONFIG_PATH = str(Path(__file__).parent / "config/agents.yaml")

    if args.daemon:
        print(f"[daemon] macro-sim v2 守护模式启动，轮询 {TRIGGER_PATH}")
        while True:
            if TRIGGER_PATH.exists() and TRIGGER_PATH.stat().st_size > 0:
                try:
                    trigger_data = json.loads(TRIGGER_PATH.read_text())
                    level  = int(trigger_data.get("level", 2))
                    event  = trigger_data.get("event", "自动触发")
                    print(f"[daemon] 触发：L{level} — {event}")
                    TRIGGER_PATH.write_text("")  # 清空
                    run_full_simulation(level=level, event=event, config_path=CONFIG_PATH)
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
        run_full_simulation(level=args.level, event=args.event, config_path=CONFIG_PATH)

    elif args.predict_only:
        run_predict_only(level=args.level, event=args.event, config_path=CONFIG_PATH)

    else:
        parser.print_help()
