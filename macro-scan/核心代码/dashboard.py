"""
模块06（v2）：预测追踪 Dashboard
修复：
  - HTML bug：risk_color 用 color='{x}' 改为 color: {x}（CSS语法）
  - gdp_growth_p50 → gdp_p50（与模块01键名对齐）
  - charts_html 未使用导致每张图被渲染两次 → 改用单次渲染
  - 外部 CDN 改为内嵌 plotly.js（支持离线）
  - 路径改用 config.py
"""
import json
import os
from datetime import datetime
from collections import Counter

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.offline as pyo
except ImportError:
    raise ImportError("请先安装: pip install plotly pandas")

from optim_config import (PREDICTIONS_LOG, WEAK_SIGNAL_LOG, GDP_HIT_TOLERANCE,
                    DASHBOARD_OUTPUT)

import glob as _glob


def load_latest_monthly_outlook() -> str:
    """加载最新月度简报Markdown内容，返回HTML片段（含基础格式化）。"""
    report_dir = os.path.join(os.path.dirname(DASHBOARD_OUTPUT), "..", "docs", "分析报告")
    report_dir = os.path.abspath(report_dir)
    pattern = os.path.join(report_dir, "月度简报_*.md")
    files = sorted(_glob.glob(pattern), reverse=True)
    if not files:
        return ""
    latest = files[0]
    try:
        with open(latest, "r", encoding="utf-8") as f:
            content = f.read()
        # 基础 Markdown → HTML 转换（仅标题、加粗、表格行）
        import re
        lines = []
        in_table = False
        for line in content.split("\n"):
            if line.startswith("# "):
                lines.append(f"<h2 style='margin:12px 0 4px'>{line[2:]}</h2>")
            elif line.startswith("## "):
                lines.append(f"<h3 style='margin:10px 0 4px;color:#555'>{line[3:]}</h3>")
            elif line.startswith("> "):
                lines.append(f"<blockquote style='border-left:3px solid #aaa;padding-left:8px;color:#666;margin:4px 0'>{line[2:]}</blockquote>")
            elif line.startswith("|"):
                if not in_table:
                    lines.append("<table style='border-collapse:collapse;width:100%;font-size:13px'>")
                    in_table = True
                if re.match(r"^\|[-: |]+\|$", line):
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                td = "".join(f"<td style='border:1px solid #ddd;padding:4px 8px'>{c}</td>" for c in cells)
                lines.append(f"<tr>{td}</tr>")
            else:
                if in_table:
                    lines.append("</table>")
                    in_table = False
                line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
                lines.append(f"<p style='margin:2px 0;font-size:13px'>{line}</p>" if line.strip() else "<br>")
        if in_table:
            lines.append("</table>")
        filename = os.path.basename(latest)
        return f"<p style='color:#888;font-size:12px'>来源：{filename}</p>" + "\n".join(lines)
    except Exception:
        return ""


def load_predictions() -> list[dict]:
    """从 PREDICTIONS_LOG 加载历史预测记录（JSON数组），文件不存在返回空列表。"""
    if not os.path.exists(PREDICTIONS_LOG):
        return []
    with open(PREDICTIONS_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


def load_signals() -> list[dict]:
    """从 WEAK_SIGNAL_LOG 加载弱信号预警记录（JSON数组），文件不存在返回空列表。"""
    if not os.path.exists(WEAK_SIGNAL_LOG):
        return []
    with open(WEAK_SIGNAL_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


def build_accuracy_chart(predictions: list[dict]) -> go.Figure:
    """图1：命中率趋势（仅 verified 记录）。"""
    verified = [p for p in predictions if p.get("status") == "verified"]
    if not verified:
        fig = go.Figure()
        fig.add_annotation(text="暂无已验证的预测记录", x=0.5, y=0.5,
                           xref="paper", yref="paper", showarrow=False, font_size=16)
        fig.update_layout(title="预测命中率（数据累积中）")
        return fig

    dates, hits, errors = [], [], []
    for p in sorted(verified, key=lambda x: x.get("verify_after", "")):
        acc = p.get("accuracy", {})
        if acc.get("gdp_hit") is not None:
            dates.append(p["verify_after"])
            hits.append(1 if acc["gdp_hit"] else 0)
            errors.append(acc.get("gdp_abs_error", 0))

    window = min(5, len(hits))
    rolling_hit_rate = []
    for i in range(len(hits)):
        start = max(0, i - window + 1)
        rate = sum(hits[start:i+1]) / (i - start + 1) * 100
        rolling_hit_rate.append(rate)

    fig = make_subplots(rows=2, cols=1,
                        subplot_titles=("GDP预测命中率（滚动%）", "GDP预测误差（ppt）"))
    fig.add_trace(go.Scatter(x=dates, y=rolling_hit_rate, mode="lines+markers",
                             name="命中率%", line=dict(color="#2196F3", width=2)),
                  row=1, col=1)
    fig.add_hline(y=50, line_dash="dash", line_color="gray", row=1, col=1)
    fig.add_trace(go.Bar(x=dates, y=errors, name="绝对误差(ppt)",
                         marker_color=["#F44336" if e > GDP_HIT_TOLERANCE else "#4CAF50"
                                       for e in errors]),
                  row=2, col=1)
    fig.update_layout(title="预测精度追踪", height=500, showlegend=True)
    return fig


def build_prediction_vs_actual_chart(predictions: list[dict]) -> go.Figure:
    """图2：GDP预测值 vs 实际值散点图。"""
    verified = [p for p in predictions
                if p.get("status") == "verified"
                and p.get("actuals", {}).get("gdp_growth") is not None]

    if not verified:
        fig = go.Figure()
        fig.add_annotation(text="暂无已验证数据", x=0.5, y=0.5,
                           xref="paper", yref="paper", showarrow=False)
        fig.update_layout(title="预测 vs 实际（数据积累中）")
        return fig

    pred_vals, actual_vals, labels = [], [], []
    for p in verified:
        pred = p["predictions"].get("gdp_p50")   # ← 修复：gdp_p50（模块01键名）
        actual = p["actuals"]["gdp_growth"]
        if pred is not None:
            pred_vals.append(pred)
            actual_vals.append(actual)
            labels.append(p["verify_after"])

    if not pred_vals:
        fig = go.Figure()
        fig.add_annotation(text="预测值缺失（gdp_p50）", x=0.5, y=0.5,
                           xref="paper", yref="paper", showarrow=False)
        return fig

    min_val = min(min(pred_vals), min(actual_vals)) - 0.5
    max_val = max(max(pred_vals), max(actual_vals)) + 0.5

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pred_vals, y=actual_vals, mode="markers+text",
        text=labels, textposition="top center",
        marker=dict(size=10, color="#FF9800", line=dict(width=1, color="white")),
        name="预测 vs 实际"
    ))
    fig.add_trace(go.Scatter(x=[min_val, max_val], y=[min_val, max_val],
                             mode="lines", name="完美预测线",
                             line=dict(color="gray", dash="dash")))
    fig.add_trace(go.Scatter(x=[min_val, max_val],
                             y=[min_val + GDP_HIT_TOLERANCE, max_val + GDP_HIT_TOLERANCE],
                             mode="lines", name=f"+{GDP_HIT_TOLERANCE}ppt容差",
                             line=dict(color="#4CAF50", dash="dot", width=1)))
    fig.add_trace(go.Scatter(x=[min_val, max_val],
                             y=[min_val - GDP_HIT_TOLERANCE, max_val - GDP_HIT_TOLERANCE],
                             mode="lines", name=f"-{GDP_HIT_TOLERANCE}ppt容差",
                             line=dict(color="#4CAF50", dash="dot", width=1),
                             fill="tonexty", fillcolor="rgba(76,175,80,0.1)"))
    fig.update_layout(
        title="GDP增速：预测值 vs 实际值",
        xaxis_title="预测值 (ppt)", yaxis_title="实际值 (ppt)",
        height=450
    )
    return fig


def build_risk_score_chart(predictions: list[dict]) -> go.Figure:
    """图3：风险评分历史走势。"""
    records = [(p["created_at"][:10], p.get("risk_scores", {}).get("overall", 0))
               for p in predictions if p.get("risk_scores")]
    if not records:
        fig = go.Figure()
        fig.add_annotation(text="暂无风险评分数据", x=0.5, y=0.5,
                           xref="paper", yref="paper", showarrow=False)
        return fig

    dates, scores = zip(*sorted(records))
    colors = ["#F44336" if s >= 60 else "#FF9800" if s >= 40 else "#4CAF50"
              for s in scores]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=dates, y=scores, marker_color=colors, name="综合风险分"))
    fig.add_hline(y=60, line_dash="dash", line_color="#F44336",
                  annotation_text="高风险阈值(60)", annotation_position="right")
    fig.add_hline(y=40, line_dash="dash", line_color="#FF9800",
                  annotation_text="中等风险(40)", annotation_position="right")
    fig.update_layout(title="综合风险评分历史", yaxis_range=[0, 100], height=350)
    return fig


def build_weak_signal_chart(signals: list[dict]) -> go.Figure:
    """图4：弱信号预警频率（近90天）。"""
    if not signals:
        fig = go.Figure()
        fig.add_annotation(text="暂无弱信号数据", x=0.5, y=0.5,
                           xref="paper", yref="paper", showarrow=False)
        fig.update_layout(title="弱信号预警（数据积累中）")
        return fig

    daily = Counter(s["date"] for s in signals)
    dates = sorted(daily.keys())[-90:]
    counts = [daily.get(d, 0) for d in dates]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=dates, y=counts,
                         marker_color=["#F44336" if c >= 3 else "#FF9800" if c >= 1
                                       else "#E0E0E0" for c in counts],
                         name="预警数量"))
    fig.update_layout(title="弱信号预警频率（近90天）", height=300)
    return fig


def build_regime_chart(predictions: list[dict]) -> go.Figure:
    """图5：体制切换历史（若有 regime 字段）。"""
    regime_records = [(p["created_at"][:10], p.get("regime", "unknown"))
                      for p in predictions if p.get("regime")]
    if not regime_records:
        fig = go.Figure()
        fig.add_annotation(text="体制切换数据将在启用模块05后出现",
                           x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        fig.update_layout(title="体制切换历史")
        return fig

    dates, regimes = zip(*sorted(regime_records))
    y_vals = [1 if r == "stress" else 0 for r in regimes]
    colors = ["#F44336" if r == "stress" else "#4CAF50" for r in regimes]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=dates, y=y_vals, marker_color=colors,
                         name="体制", text=regimes, textposition="inside"))
    fig.update_layout(
        title="体制切换历史（红=压力体制，绿=常态体制）",
        yaxis=dict(tickvals=[0, 1], ticktext=["常态", "压力"]),
        height=250
    )
    return fig


def generate_summary_stats(predictions: list[dict]) -> str:
    """生成顶部摘要统计 HTML。"""
    total = len(predictions)
    verified = [p for p in predictions if p.get("status") == "verified"]
    n_verified = len(verified)

    us_preds = [p for p in predictions if p.get("scenario") not in ("baseline_cn",)]
    cn_preds = [p for p in predictions if p.get("scenario") in ("baseline_cn",)]

    hits = sum(1 for p in verified
               if p.get("scenario") not in ("baseline_cn",)
               and p.get("accuracy", {}).get("gdp_hit"))
    gdp_tried = sum(1 for p in verified
                    if p.get("scenario") not in ("baseline_cn",)
                    and p.get("accuracy", {}).get("gdp_hit") is not None)
    hit_rate = hits / gdp_tried * 100 if gdp_tried > 0 else 0

    stress_count = sum(1 for p in predictions if p.get("regime") == "stress")
    latest_risk = next(
        (p.get("risk_scores", {}).get("overall") for p in reversed(predictions)
         if p.get("risk_scores")), None
    )
    risk_color = ("#F44336" if (latest_risk or 0) >= 60 else
                  "#FF9800" if (latest_risk or 0) >= 40 else "#4CAF50")

    card_style = ("background:#fff; border-radius:8px; padding:16px; flex:1; "
                  "min-width:140px; box-shadow:0 2px 8px rgba(0,0,0,0.1); text-align:center;")

    return f"""
    <div style="display:flex; gap:20px; margin:20px 0; flex-wrap:wrap;">
      <div style="{card_style}">
        <div style="font-size:32px; font-weight:bold; color:#2196F3;">{total}</div>
        <div style="color:#666; margin-top:4px;">总预测记录</div>
        <div style="color:#aaa; font-size:11px; margin-top:2px;">美国{len(us_preds)} / 中国{len(cn_preds)}</div>
      </div>
      <div style="{card_style}">
        <div style="font-size:32px; font-weight:bold; color:#4CAF50;">{hit_rate:.0f}%</div>
        <div style="color:#666; margin-top:4px;">美国GDP命中率（±{GDP_HIT_TOLERANCE}ppt）</div>
      </div>
      <div style="{card_style}">
        <div style="font-size:32px; font-weight:bold; color: {risk_color};">
          {latest_risk if latest_risk is not None else 'N/A'}
        </div>
        <div style="color:#666; margin-top:4px;">最新综合风险分</div>
      </div>
      <div style="{card_style}">
        <div style="font-size:32px; font-weight:bold; color:#FF9800;">{stress_count}</div>
        <div style="color:#666; margin-top:4px;">压力体制记录数</div>
      </div>
    </div>
    """


def _render_div(fig: go.Figure, first: bool = False) -> str:
    """渲染为 HTML div；第一个图内嵌 plotly.js（支持离线），其余引用它。"""
    return pyo.plot(fig, include_plotlyjs=first, output_type="div")


def generate_dashboard():
    """主函数：生成完整 HTML Dashboard。"""
    print("加载数据...")
    predictions = load_predictions()
    signals = load_signals()
    print(f"  预测记录：{len(predictions)} 条")
    print(f"  信号记录：{len(signals)} 条")

    print("加载月度简报...")
    outlook_html = load_latest_monthly_outlook()
    if outlook_html:
        outlook_panel = f'<div class="chart-card"><h2 style="color:#333;margin-top:0">月度宏观简报（Executive Briefing）</h2>{outlook_html}</div>'
    else:
        outlook_panel = ""

    print("生成图表...")
    figs = [
        build_accuracy_chart(predictions),
        build_prediction_vs_actual_chart(predictions),
        build_risk_score_chart(predictions),
        build_weak_signal_chart(signals),
        build_regime_chart(predictions),
    ]

    summary_html = generate_summary_stats(predictions)

    # 第一个 div 内嵌 plotly.js（include_plotlyjs=True），其余共享（False）
    # 这样离线也能正常显示，无需外部 CDN
    chart_divs = [_render_div(fig, first=(i == 0)) for i, fig in enumerate(figs)]

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <title>宏观推演系统 Dashboard</title>
  <style>
    body {{ font-family: -apple-system, 'PingFang SC', sans-serif;
            background: #f5f5f5; margin: 0; padding: 20px; }}
    h1   {{ color: #333; margin-bottom: 4px; }}
    .subtitle {{ color: #888; margin-bottom: 20px; font-size: 14px; }}
    .chart-card {{ background: #fff; border-radius: 8px; padding: 16px; margin: 16px 0;
                   box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  </style>
</head>
<body>
  <h1>宏观推演系统 Dashboard</h1>
  <p class="subtitle">更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} |
     数据源：FRED + NeoData + 自建多源</p>
  {outlook_panel}
  {summary_html}
  {''.join(f'<div class="chart-card">{div}</div>' for div in chart_divs)}
</body>
</html>"""

    os.makedirs(os.path.dirname(DASHBOARD_OUTPUT), exist_ok=True)
    with open(DASHBOARD_OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDashboard 已生成：{DASHBOARD_OUTPUT}")
    print("用浏览器打开即可查看（支持离线，无需网络）。")


if __name__ == "__main__":
    generate_dashboard()
