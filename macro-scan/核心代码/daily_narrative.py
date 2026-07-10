"""
daily_narrative.py — 每日世界摘要

每天 07:00 自动运行，合成"今天世界3件最值得关注的事"推送到 ntfy。
即使没有触发阈值也会推送——"今天一切平稳"本身也是有价值的信息。

不触发完整分析流程（节约 LLM 调用），只做轻量摘要。
"""
import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from optim_config import DATA_DIR, WORKSPACE, FRED_API_KEY
except ImportError:
    WORKSPACE = Path(__file__).parent.parent
    DATA_DIR  = str(Path(WORKSPACE) / "data")
    FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

WEAK_SIGNAL_LOG  = os.path.join(DATA_DIR, "weak_signal_log.json")
GRV_FILE         = os.path.join(DATA_DIR, "grv_latest.json")
NEWS_DB_PATH     = os.path.join(DATA_DIR, "news.db")
NARRATIVE_CACHE  = os.path.join(DATA_DIR, "daily_narrative_cache.json")
POLITICAL_CAL    = os.path.join(WORKSPACE, "知识库", "political_calendar.yaml")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")


# ── 数据读取 ──────────────────────────────────────────────────────────────────

def _load_recent_signals(hours: int = 24) -> list:
    """读取近 N 小时的弱信号告警（从 weak_signal_log.json）。"""
    if not os.path.exists(WEAK_SIGNAL_LOG):
        return []
    try:
        with open(WEAK_SIGNAL_LOG, "r", encoding="utf-8") as f:
            log = json.load(f)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = []
        for entry in (log if isinstance(log, list) else []):
            ts_str = entry.get("timestamp") or entry.get("date", "")
            try:
                if "T" in ts_str:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                else:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    recent.append(entry)
            except Exception:
                pass
        return recent[-20:]  # 最多20条
    except Exception:
        return []


def _load_grv() -> dict:
    """读取最新 GRV 地缘风险向量。"""
    if not os.path.exists(GRV_FILE):
        return {}
    try:
        with open(GRV_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _query_top_news(limit: int = 5) -> list:
    """从 news.db 取昨日至今被打标签的文章标题（最高频类别各1条）。"""
    if not os.path.exists(NEWS_DB_PATH):
        return []
    try:
        conn = sqlite3.connect(NEWS_DB_PATH, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()[:19]
        rows = conn.execute("""
            SELECT a.title, ac.category
            FROM articles a
            JOIN article_categories ac ON a.id = ac.article_id
            WHERE a.ingested_at >= ?
            ORDER BY a.ingested_at DESC
            LIMIT ?
        """, (cutoff, limit * 3)).fetchall()
        conn.close()
        seen_cats = set()
        result = []
        for title, cat in rows:
            if cat not in seen_cats and title:
                seen_cats.add(cat)
                result.append((title, cat))
                if len(result) >= limit:
                    break
        return result
    except Exception:
        return []


def _load_political_calendar(days_ahead: int = 30) -> list:
    """读取未来 N 天内的高重要性政治事件。"""
    events = []
    if not os.path.exists(POLITICAL_CAL):
        return events
    try:
        import yaml
        with open(POLITICAL_CAL, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        today = datetime.now().date()
        deadline = today + timedelta(days=days_ahead)
        for ev in (data or {}).get("events", []):
            date_str = str(ev.get("date", ""))
            if "xx" in date_str.lower():
                continue
            try:
                ev_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
                if today <= ev_date <= deadline and ev.get("importance") == "HIGH":
                    events.append({
                        "date": str(ev_date),
                        "name": ev.get("name", ""),
                        "notes": ev.get("notes", ""),
                    })
            except Exception:
                pass
        events.sort(key=lambda x: x["date"])
    except Exception:
        pass
    return events[:3]


def _load_situation_context() -> str:
    """读取情境记忆的上下文摘要（区分已确认/待确认）。"""
    try:
        _dir = os.path.dirname(os.path.abspath(__file__))
        if _dir not in sys.path:
            sys.path.insert(0, _dir)
        from situation_tracker import list_situations
        situations = list_situations()
        confirmed = [s for s in situations
                     if s.get("status") in ("watching", "escalating", "de-escalating")
                     and not s.get("needs_review", False)]
        pending = [s for s in situations if s.get("needs_review", False)]

        lines = []
        if confirmed:
            labels = {"escalating": "🔴升级中", "de-escalating": "🟡缓和中", "watching": "🔵观察中"}
            lines.append("[正在追踪的情况]")
            for s in confirmed[:4]:
                lbl = labels.get(s.get("status", "watching"), "观察中")
                lines.append(f"  ▸ {s['name']}（{lbl}）")
                if s.get("notes"):
                    lines.append(f"    {s['notes'][:50]}")
        if pending:
            lines.append(f"[待确认话题] {len(pending)}个自动检测到的新话题（发 1900 situations 查看）")
        return "\n".join(lines)
    except Exception:
        return ""


def _load_climate_context() -> str:
    """读取气候信号摘要（Phase 2：接入 climate_signals.json）。"""
    climate_path = os.path.join(DATA_DIR, "climate_signals.json")
    if not os.path.exists(climate_path):
        return ""
    try:
        with open(climate_path, encoding="utf-8") as f:
            data = json.load(f)
        risk_score = data.get("climate_risk_score", 0)
        if risk_score < 25:
            return ""  # 低风险不注入
        oni = data.get("oni", {})
        level = data.get("risk_level", "低")
        lines = [f"[气候信号] 气候风险={level}（{risk_score:.0f}/100）"]
        if oni.get("value") is not None:
            lines.append(f"  厄尔尼诺指数 ONI={oni['value']:.1f}（{oni.get('status', '')}）")
            if oni.get("interpretation"):
                lines.append(f"  {oni['interpretation']}")
        return "\n".join(lines)
    except Exception:
        return ""


def _load_disaster_context() -> str:
    """读取自然灾害信号摘要（接入 disaster_signals.json）。"""
    try:
        _dir = os.path.dirname(os.path.abspath(__file__))
        if _dir not in sys.path:
            sys.path.insert(0, _dir)
        from fetch_disaster_signals import get_context as _dc
        return _dc()
    except Exception:
        return ""


def _load_last_narrative() -> str:
    """读取昨天的摘要（用于 diff 去重）。"""
    if not os.path.exists(NARRATIVE_CACHE):
        return ""
    try:
        with open(NARRATIVE_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return cache.get(yesterday, "")
    except Exception:
        return ""


def _save_narrative(text: str):
    """缓存今日摘要（保留最近7天）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    cache = {}
    if os.path.exists(NARRATIVE_CACHE):
        try:
            with open(NARRATIVE_CACHE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass
    # 只保留最近7天
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    cache = {k: v for k, v in cache.items() if k >= cutoff}
    cache[today] = text
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NARRATIVE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── 核心逻辑 ──────────────────────────────────────────────────────────────────

def _build_prompt(signals: list, grv: dict, top_news: list,
                  calendar: list, situation_ctx: str, last_narrative: str,
                  climate_ctx: str = "", disaster_ctx: str = "") -> str:
    """构建 daily_narrative 的 LLM prompt。"""
    today_str = datetime.now().strftime("%Y年%m月%d日 %A")

    lines = [f'今天是 {today_str}。请根据以下信息，生成一份简洁的"今日世界摘要"。']
    lines.append("")

    # 弱信号
    if signals:
        lines.append("[最近24h触发的弱信号告警]")
        for s in signals[:8]:
            indicator = s.get("indicator_name") or s.get("indicator", "")
            level = s.get("level", "")
            value = s.get("value", "")
            lines.append(f"  - {indicator}: {level} （值={value}）")
    else:
        lines.append("[最近24h弱信号] 无异常告警。")

    lines.append("")

    # 气候信号（Phase 2 新增）
    if climate_ctx:
        lines.append(climate_ctx)
        lines.append("")

    # 自然灾害信号（score≥25时注入）
    if disaster_ctx:
        lines.append(disaster_ctx)
        lines.append("")

    # GRV
    if grv:
        lines.append("[地缘风险向量 GRV（0-100）]")
        grv_map = {
            "taiwan_strait":      "台海",
            "us_china_strategic": "中美战略",
            "russia_europe":      "俄欧",
            "middle_east_energy": "中东能源",
        }
        for key, label in grv_map.items():
            val = grv.get(key)
            if val is not None:
                lines.append(f"  - {label}: {val:.1f}")

    lines.append("")

    # 情境事件
    if situation_ctx:
        lines.append(situation_ctx)
        lines.append("")

    # 近期新闻标题
    if top_news:
        lines.append("[近期标记文章（标题）]")
        for title, cat in top_news:
            lines.append(f"  [{cat}] {title[:60]}")
        lines.append("")

    # 政治日历
    if calendar:
        lines.append("[未来30天重要事件]")
        for ev in calendar:
            lines.append(f"  - {ev['date']}: {ev['name']}")
            if ev.get("notes"):
                lines.append(f"    （{ev['notes'][:50]}）")
        lines.append("")

    # 昨日摘要（去重参考）
    if last_narrative:
        lines.append("[昨日摘要（参考，避免重复）]")
        lines.append(last_narrative[:300])
        lines.append("")

    lines.append("---")
    lines.append("输出要求：")
    lines.append("1. 用中文写3条，每条1-2句话，不超过60字")
    lines.append('2. 格式：① 最重要的正在演化事件 ② 最值得注意的数据信号 ③ 即将发生的关键节点（无则写"近期无重大事件节点"）')
    lines.append('3. 如果今天一切平稳，直接说"当前未检测到异常信号"，简单说明当前哪些领域需要持续关注')
    lines.append("4. 不要加标题、不要加日期、不要加免责声明、不要超过150字")

    return "\n".join(lines)


def generate() -> str:
    """生成今日摘要文字（不推送）。"""
    print("[daily_narrative] 开始生成今日摘要...")

    signals       = _load_recent_signals(hours=24)
    grv           = _load_grv()
    top_news      = _query_top_news(limit=5)
    calendar      = _load_political_calendar(days_ahead=30)
    situation_ctx  = _load_situation_context()
    last_narrative = _load_last_narrative()
    climate_ctx    = _load_climate_context()
    disaster_ctx   = _load_disaster_context()  # 新增：自然灾害信号

    print(f"  信号={len(signals)} GRV维度={len(grv)} 新闻={len(top_news)} "
          f"日历={len(calendar)} 气候={'有' if climate_ctx else '无'} "
          f"灾害={'有' if disaster_ctx else '无'}")

    prompt = _build_prompt(signals, grv, top_news, calendar, situation_ctx,
                           last_narrative, climate_ctx, disaster_ctx)

    # 调用 LLM
    try:
        _dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, _dir)
        from hybrid_llm import reason
        system = "你是世界情势分析助手，专注于每日要点摘要，言简意赅，不添加没有依据的判断。"
        narrative = reason(prompt, system=system, mode="auto", max_tokens=300)
        narrative = narrative.strip()
    except Exception as e:
        print(f"  [WARN] LLM调用失败，使用纯数据摘要: {e}")
        # 降级：纯数据摘要
        lines = []
        if signals:
            top_sig = signals[0]
            ind = top_sig.get("indicator_name") or top_sig.get("indicator", "未知指标")
            lv = top_sig.get("level", "告警")
            lines.append(f"① {ind} 触发{lv}，需持续关注。")
        else:
            lines.append("① 近24小时未检测到异常告警信号。")

        if grv:
            tw = grv.get("taiwan_strait")
            if tw and tw >= 60:
                lines.append(f"② 台海GRV={tw:.1f}，处于偏高区间（警戒线68）。")
            else:
                lines.append("② 各地缘维度当前无超阈值信号。")
        else:
            lines.append("② GRV数据暂不可用。")

        if calendar:
            ev = calendar[0]
            lines.append(f"③ 近期重要节点：{ev['date']} {ev['name']}。")
        else:
            lines.append("③ 近期无重大事件节点。")

        narrative = "\n".join(lines)

    _save_narrative(narrative)
    print("[daily_narrative] 生成完成。")
    return narrative


def push(narrative: str):
    """推送摘要到 ntfy。"""
    if not NTFY_TOPIC:
        print("[daily_narrative] NTFY_TOPIC 未配置，跳过推送")
        return
    try:
        import requests as _req
        today_str = datetime.now().strftime("%m月%d日")
        _req.post(
            "https://ntfy.sh/",
            json={
                "topic": NTFY_TOPIC,
                "title": f"📡 今日世界摘要 {today_str}",
                "message": narrative,
                "priority": 2,
            },
            timeout=30,
        )
        print("[daily_narrative] ntfy 推送完成")
    except Exception as e:
        print(f"[daily_narrative] 推送失败: {e}")


if __name__ == "__main__":
    narrative = generate()
    print("\n--- 今日摘要 ---")
    print(narrative)
    print("---")
    push(narrative)
