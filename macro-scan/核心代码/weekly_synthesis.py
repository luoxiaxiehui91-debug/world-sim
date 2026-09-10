"""
weekly_synthesis.py — 周度综合报告

每周五 20:00 自动运行，生成一周回顾：
- 本周哪些信号持续积累（趋势而非单次脉冲）
- 情境事件状态变化（哪些升级/缓和）
- 上周推演的假设有没有在现实中出现迹象
- GRV 周度变化对比
- 即将到来的政治日历节点

比每日摘要更宏观，聚焦"7天内世界发生了什么"而非今天。
"""
import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = Path(__file__).parent.parent
    DATA_DIR  = str(Path(WORKSPACE) / "data")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
REPORT_DIR = Path(WORKSPACE) / "docs" / "分析报告"
_APP_DIR   = os.path.dirname(os.path.abspath(__file__))


# ── 数据读取 ──────────────────────────────────────────────────────────────────

def _load_weekly_signals(days: int = 7) -> list:
    """过去7天所有弱信号告警，按类别聚合频率。"""
    sig_path = os.path.join(DATA_DIR, "weak_signal_log.json")
    if not os.path.exists(sig_path):
        return []
    try:
        with open(sig_path, encoding="utf-8") as f:
            log = json.load(f)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()[:19]
        recent = []
        for entry in (log if isinstance(log, list) else []):
            ts = entry.get("timestamp") or entry.get("date", "")
            if ts[:19] >= cutoff:
                recent.append(entry)
        # 按 indicator_name 聚合
        counts: dict[str, int] = {}
        levels: dict[str, str] = {}
        for s in recent:
            name = s.get("indicator_name") or s.get("indicator", "未知")
            counts[name] = counts.get(name, 0) + 1
            # 记录最高等级
            lv = s.get("level", "")
            if lv == "[警报]" or (lv == "[注意]" and levels.get(name) != "[警报]"):
                levels[name] = lv
        # 只返回触发≥2次的（真正持续积累）
        result = []
        for name, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            if cnt >= 2:
                result.append({"indicator": name, "count": cnt, "level": levels.get(name, "")})
        return result[:10]
    except Exception:
        return []


def _load_grv_history() -> tuple[dict, dict]:
    """读取当前 GRV 和一周前 GRV（从 grv_latest.json 只有当前值，需从历史JSONL估算）。"""
    current_grv = {}
    grv_path = os.path.join(DATA_DIR, "grv_latest.json")
    if os.path.exists(grv_path):
        try:
            with open(grv_path, encoding="utf-8") as f:
                current_grv = json.load(f)
        except Exception:
            pass

    # 从 gdelt_history.jsonl 取7天前的值（近似）
    prev_grv = {}
    hist_path = os.path.join(DATA_DIR, "gdelt_history.jsonl")
    if os.path.exists(hist_path):
        try:
            target_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            with open(hist_path, encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("date", "") <= target_date:
                        prev_grv = entry.get("scores", {})
        except Exception:
            pass

    return current_grv, prev_grv


def _load_situation_changes() -> list:
    """获取过去7天情境事件的状态变化摘要。"""
    try:
        if _APP_DIR not in sys.path:
            sys.path.insert(0, _APP_DIR)
        from situation_tracker import list_situations
        situations = list_situations()
        result = []
        for s in situations:
            name = s.get("name", "")
            status = s.get("status", "watching")
            updated = s.get("last_updated", "")
            recent_sigs = s.get("recent_signals", [])
            cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            if updated >= cutoff:
                result.append({
                    "name": name,
                    "status": status,
                    "recent_signal": recent_sigs[0][:60] if recent_sigs else "",
                })
        return result
    except Exception:
        return []


def _load_recent_reports(days: int = 7) -> list:
    """获取本周生成的分析报告列表。"""
    if not REPORT_DIR.exists():
        return []
    cutoff = (datetime.now() - timedelta(days=days)).timestamp()
    reports = []
    for p in sorted(REPORT_DIR.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.stat().st_mtime >= cutoff and not p.name.startswith("[假设]"):
            reports.append(p.stem[:50])
    return reports[:5]


def _load_political_calendar_next(days: int = 14) -> list:
    """接下来14天的重要政治节点。"""
    kb_root  = Path(os.environ.get("KB_ROOT") or (Path(WORKSPACE) / "知识库"))
    cal_path = kb_root / "political_calendar.yaml"
    if not cal_path.exists():
        return []
    try:
        import yaml
        with open(cal_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        today = datetime.now().date()
        deadline = today + timedelta(days=days)
        events = []
        for ev in (data or {}).get("events", []):
            ds = str(ev.get("date", ""))
            if "xx" in ds.lower():
                continue
            try:
                ev_date = datetime.strptime(ds[:10], "%Y-%m-%d").date()
                if today <= ev_date <= deadline and ev.get("importance") in ("HIGH", "MEDIUM"):
                    events.append({"date": str(ev_date), "name": ev.get("name", ""),
                                   "importance": ev.get("importance", "")})
            except Exception:
                pass
        return sorted(events, key=lambda x: x["date"])[:5]
    except Exception:
        return []


# ── 核心生成 ─────────────────────────────────────────────────────────────────

def generate() -> str:
    """生成周度综合报告文字。"""
    print("[weekly_synthesis] 开始生成周度综合报告...")

    week_signals   = _load_weekly_signals(days=7)
    current_grv, prev_grv = _load_grv_history()
    sit_changes    = _load_situation_changes()
    recent_reports = _load_recent_reports(days=7)
    calendar_next  = _load_political_calendar_next(days=14)

    # 计算 GRV 变化
    grv_changes = []
    for key, label in [
        ("taiwan_strait",      "台海"),
        ("us_china_strategic", "中美"),
        ("russia_europe",      "俄欧"),
        ("middle_east_energy", "中东能源"),
    ]:
        cur = current_grv.get(key)
        if cur is not None and isinstance(cur, (int, float)):
            grv_changes.append({"label": label, "current": round(cur, 1)})

    # 构建 LLM prompt
    lines = [
        f"今天是{datetime.now().strftime('%Y年%m月%d日')}（周五）。请生成一份简洁的**本周世界综合回顾**（约300字）。",
        "",
    ]

    if week_signals:
        lines.append("[本周持续积累的弱信号（触发≥2次）]")
        for s in week_signals[:6]:
            lines.append(f"  - {s['indicator']}（{s['count']}次触发，{s['level']}）")
        lines.append("")

    if grv_changes:
        lines.append("[当前 GRV 地缘风险向量]")
        for g in grv_changes:
            lines.append(f"  {g['label']}: {g['current']}")
        lines.append("")

    if sit_changes:
        lines.append("[本周情境事件动态]")
        for s in sit_changes[:4]:
            status_label = {"escalating": "🔴升级", "de-escalating": "🟡缓和",
                            "watching": "🔵观察", "calm": "⚪平静"}.get(s["status"], s["status"])
            lines.append(f"  ▸ {s['name']}（{status_label}）")
            if s["recent_signal"]:
                lines.append(f"    最新：{s['recent_signal']}")
        lines.append("")

    if calendar_next:
        lines.append("[未来14天重要节点]")
        for ev in calendar_next:
            imp = "⚡" if ev["importance"] == "HIGH" else "📌"
            lines.append(f"  {imp} {ev['date']}: {ev['name']}")
        lines.append("")

    lines.extend([
        "---",
        "输出要求：",
        "1. 用中文，约300字，分三段：①本周最重要的趋势变化 ②需要关注的积累信号 ③未来一周的关键节点",
        "2. 聚焦'持续7天的趋势'而非单次事件，体现周度视角",
        "3. 结尾给出一句话的风险状态评价（高/中/低）",
        "4. 不要加标题，不要加日期，不要加免责声明",
    ])

    prompt = "\n".join(lines)

    try:
        from hybrid_llm import reason
        system = "你是宏观世界分析助手，专注周度趋势综合，突出持续积累而非单次冲击。"
        report = reason(prompt, system=system, mode="auto", max_tokens=600)
        report = report.strip()
    except Exception as e:
        print(f"  [WARN] LLM 失败，使用数据摘要: {e}")
        parts = []
        if week_signals:
            top3 = [s["indicator"] for s in week_signals[:3]]
            parts.append(f"本周持续触发信号：{'、'.join(top3)}")
        if grv_changes:
            top = max(grv_changes, key=lambda x: x["current"])
            parts.append(f"当前最高 GRV 维度：{top['label']}={top['current']}")
        if calendar_next:
            parts.append(f"近期节点：{calendar_next[0]['date']} {calendar_next[0]['name']}")
        report = "；".join(parts) if parts else "本周无显著异常信号。"

    print("[weekly_synthesis] 生成完成。")
    return report


def push(report: str):
    """推送到 ntfy（长内容以 .md 附件发送）。"""
    if not NTFY_TOPIC:
        return
    try:
        from ntfy_utils import push_markdown
        week_str = datetime.now().strftime("第%V周 %m/%d")
        push_markdown(f"📊 本周世界回顾 {week_str}", report, "weekly")
        print("[weekly_synthesis] ntfy 推送完成")
    except Exception as e:
        print(f"[weekly_synthesis] 推送失败: {e}")


if __name__ == "__main__":
    report = generate()
    print("\n--- 本周综合报告 ---")
    print(report)
    print("---")
    push(report)
