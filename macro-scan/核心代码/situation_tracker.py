"""
situation_tracker.py — 情境记忆：追踪正在演化的事件

每次弱信号扫描后自动调用 update()，根据 signal_keywords 匹配新文章，
更新事件状态（calm/watching/escalating/de-escalating/resolved）。

供 daily_narrative.py / hypothesis_engine.py / ntfy Q&A 调用。
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = Path(__file__).parent.parent
    DATA_DIR = str(Path(WORKSPACE) / "data")

SITUATIONS_FILE = os.path.join(DATA_DIR, "situations.yaml")
NEWS_DB_PATH    = os.path.join(DATA_DIR, "news.db")

_STATUS_LABELS = {
    "calm":          "平静",
    "watching":      "观察中",
    "escalating":    "升级中",
    "de-escalating": "缓和中",
    "resolved":      "已解决",
}

# ── 默认初始事件（文件不存在时自动生成） ─────────────────────────────────────
_DEFAULT_SITUATIONS = [
    {
        "id": "trade_war_2025",
        "name": "2025美中关税战",
        "category": "TRADE",
        "status": "watching",
        "started": "2025-01-01",
        "last_updated": "2026-06-10",
        "signal_keywords": ["关税", "tariff", "贸易战", "trade war", "145%", "贸易摩擦"],
        "linked_indicators": ["global_trade_tension", "GPRC_CHN"],
        "recent_signals": [],
        "notes": "日内瓦峰会90天暂停，2026-08到期后走向待观察",
    },
    {
        "id": "taiwan_strait_2026",
        "name": "台海紧张态势",
        "category": "GEO",
        "status": "watching",
        "started": "2024-01-01",
        "last_updated": "2026-06-10",
        "signal_keywords": ["台海", "台湾", "Taiwan", "解放军", "PLA", "台独", "两岸"],
        "linked_indicators": ["GPRC_TWN", "taiwan_strait"],
        "recent_signals": [],
        "notes": "GRV台海当前=60.2，进入观察区间（警戒线68）",
    },
    {
        "id": "fed_rate_cycle_2024",
        "name": "美联储降息周期",
        "category": "MACRO",
        "status": "watching",
        "started": "2024-09-18",
        "last_updated": "2026-06-10",
        "signal_keywords": ["美联储", "Fed", "FOMC", "降息", "rate cut", "货币政策", "利率"],
        "linked_indicators": ["FEDFUNDS", "T10Y2Y"],
        "recent_signals": [],
        "notes": "已降息多次，2026年路径取决于通胀与就业双目标",
    },
    {
        "id": "china_economy_rebalance",
        "name": "中国经济再平衡",
        "category": "MACRO",
        "status": "watching",
        "started": "2023-01-01",
        "last_updated": "2026-06-10",
        "signal_keywords": ["中国经济", "房地产", "刺激政策", "内需", "通缩", "deflation", "CPI"],
        "linked_indicators": ["pmi_mfg", "cpi", "gdp_growth"],
        "recent_signals": [],
        "notes": "内需疲弱+房地产债务去杠杆，政策刺激效果待观察",
    },
    {
        "id": "russia_ukraine_war",
        "name": "俄乌冲突",
        "category": "GEO",
        "status": "watching",
        "started": "2022-02-24",
        "last_updated": "2026-06-10",
        "signal_keywords": ["俄罗斯", "乌克兰", "Russia", "Ukraine", "俄乌", "制裁", "sanctions"],
        "linked_indicators": ["GPRC_RUS", "russia_europe", "DCOILWTICO"],
        "recent_signals": [],
        "notes": "持续消耗战阶段，欧洲能源依赖已基本切断",
    },
    {
        "id": "ai_regulation_evolution",
        "name": "AI监管演进",
        "category": "TECH",
        "status": "watching",
        "started": "2023-11-01",
        "last_updated": "2026-06-10",
        "signal_keywords": ["AI监管", "AI regulation", "人工智能法", "AI Act", "算法监管", "GPU出口"],
        "linked_indicators": [],
        "recent_signals": [],
        "notes": "欧盟AI法案生效，美国行政令+立法并行，中国算法监管细化",
    },
]


def _load_situations() -> List[Dict]:
    """加载 situations.yaml，不存在则初始化默认事件列表。"""
    if not os.path.exists(SITUATIONS_FILE):
        _save_situations(_DEFAULT_SITUATIONS)
        return _DEFAULT_SITUATIONS

    if _YAML_OK:
        try:
            with open(SITUATIONS_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data.get("situations", []) if data else []
        except Exception as e:
            print(f"[situation_tracker] YAML加载失败: {e}")
            return []
    else:
        # yaml 不可用时降级为 JSON（兼容性）
        json_path = SITUATIONS_FILE.replace(".yaml", ".json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return _DEFAULT_SITUATIONS


def _save_situations(situations: List[Dict]):
    """保存事件列表到 situations.yaml（或 .json 降级）。"""
    os.makedirs(DATA_DIR, exist_ok=True)

    if _YAML_OK:
        try:
            import yaml
            with open(SITUATIONS_FILE, "w", encoding="utf-8") as f:
                yaml.dump({"situations": situations}, f,
                          allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception as e:
            print(f"[situation_tracker] YAML保存失败: {e}")
    else:
        json_path = SITUATIONS_FILE.replace(".yaml", ".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(situations, f, ensure_ascii=False, indent=2)


def _query_recent_articles(keywords: List[str], days: int = 3) -> List[str]:
    """从 news.db 查找近 N 天内匹配关键词的文章标题（最多5条）。"""
    if not os.path.exists(NEWS_DB_PATH):
        return []
    try:
        conn = sqlite3.connect(NEWS_DB_PATH, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()[:19]
        titles = []
        for kw in keywords[:3]:  # 只用前3个关键词，避免查询过慢
            rows = conn.execute("""
                SELECT title FROM articles
                WHERE title LIKE ?
                  AND ingested_at >= ?
                ORDER BY ingested_at DESC
                LIMIT 3
            """, (f"%{kw}%", cutoff)).fetchall()
            for row in rows:
                t = row[0]
                if t and t not in titles:
                    titles.append(t)
                if len(titles) >= 5:
                    break
            if len(titles) >= 5:
                break
        conn.close()
        return titles[:5]
    except Exception as e:
        print(f"[situation_tracker] news.db查询失败: {e}")
        return []


def _determine_status_change(situation: Dict, new_signals: List[str]) -> Optional[str]:
    """根据新信号数量判断是否需要更新状态。返回新状态或 None（不变）。"""
    current = situation.get("status", "watching")
    if current in ("resolved",):
        return None

    n = len(new_signals)
    if n == 0:
        # 无信号：escalating/de-escalating/watching → calm
        if current in ("escalating", "de-escalating", "watching"):
            return "calm"
    elif n <= 2:
        # 少量信号：calm → watching
        if current == "calm":
            return "watching"
    else:
        # 3+ 信号：calm/watching/de-escalating → escalating
        if current in ("calm", "watching", "de-escalating"):
            return "escalating"
    return None


def _trigger_light_hypothesis(situation: Dict):
    """
    事件升级到 escalating 时，异步触发一次轻量假设推演并推送摘要。
    使用 subprocess 非阻断，失败不影响主流程。
    """
    try:
        import subprocess as _sp, sys as _sys
        name = situation.get("name", "")
        category = situation.get("category", "GEO")
        # 用事件名称直接触发推演，L1 轻量级
        _sp.Popen(
            [_sys.executable, "run_macro_analysis.py",
             "--hypothesis", name, "--hypothesis-severity", "L1"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        print(f"  [situation_tracker] 触发轻量推演：{name}（升级到 escalating）")
    except Exception as _e:
        print(f"  [situation_tracker] 轻量推演触发失败（非阻断）: {_e}")


def update():
    """
    更新所有事件的 recent_signals 和 status。

    每次弱信号扫描结束后调用（非阻断，异常不影响主流程）。
    scan_articles: 本次扫描获取的文章列表（可选），优先用 news.db 查询。
    """
    try:
        situations = _load_situations()
        changed = False
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for sit in situations:
            if sit.get("status") == "resolved":
                continue
            keywords = sit.get("signal_keywords", [])
            if not keywords:
                continue

            new_signals = _query_recent_articles(keywords, days=3)
            old_signals = sit.get("recent_signals", [])

            if new_signals != old_signals or sit.get("last_updated") != now:
                sit["recent_signals"] = new_signals
                sit["last_updated"] = now

                new_status = _determine_status_change(sit, new_signals)
                if new_status and new_status != sit.get("status"):
                    old_status = sit.get("status", "watching")
                    print(f"[situation_tracker] 事件状态变化: {sit['name']} "
                          f"{old_status} → {new_status}")
                    sit["status"] = new_status

                    # 状态升级到 escalating 时：自动触发轻量假设推演（非阻断）
                    if new_status == "escalating" and old_status != "escalating":
                        _trigger_light_hypothesis(sit)

                changed = True

        if changed:
            _save_situations(situations)
            print(f"[situation_tracker] 已更新 {len(situations)} 个事件")

    except Exception as e:
        print(f"[situation_tracker] update() 失败（非阻断）: {e}")


def get_context(max_events: int = 6) -> str:
    """
    返回当前活跃事件的格式化摘要字符串，供 LLM prompt 注入。

    只返回 watching/escalating/de-escalating 状态的事件。
    """
    try:
        situations = _load_situations()
        active = [s for s in situations
                  if s.get("status") in ("watching", "escalating", "de-escalating")]
        active.sort(key=lambda x: (
            0 if x.get("status") == "escalating" else
            1 if x.get("status") == "de-escalating" else 2
        ))
        active = active[:max_events]

        if not active:
            return ""

        lines = ["[SITUATIONS] 当前正在追踪的事件："]
        for s in active:
            status_label = _STATUS_LABELS.get(s.get("status", "watching"), "观察中")
            name = s.get("name", "未命名")
            notes = s.get("notes", "")
            recent = s.get("recent_signals", [])
            recent_str = ""
            if recent:
                recent_str = f"\n    近期信号：{recent[0][:40]}…" if recent else ""
            lines.append(f"  ▸ {name}（{status_label}）{recent_str}")
            if notes:
                lines.append(f"    注：{notes}")
        return "\n".join(lines)

    except Exception as e:
        print(f"[situation_tracker] get_context() 失败: {e}")
        return ""


def list_situations() -> List[Dict]:
    """返回完整事件列表（供 ntfy cmd 展示）。"""
    return _load_situations()


def add_situation(name: str, category: str, keywords: List[str],
                  notes: str = "") -> str:
    """添加新事件。返回成功/失败消息。"""
    import hashlib
    situations = _load_situations()
    new_id = hashlib.md5(name.encode()).hexdigest()[:8]
    situations.append({
        "id": new_id,
        "name": name,
        "category": category.upper(),
        "status": "watching",
        "started": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "signal_keywords": keywords,
        "linked_indicators": [],
        "recent_signals": [],
        "notes": notes,
    })
    _save_situations(situations)
    return f"已添加事件：{name}（ID={new_id}）"


def update_situation(sit_id: str, **updates) -> bool:
    """
    原子性更新单个情况的字段（供 ntfy_listener 等调用，避免直接操作 YAML 文件）。
    返回 True 表示找到并更新成功，False 表示未找到。
    """
    situations = _load_situations()
    for s in situations:
        if s.get("id") == sit_id:
            s.update(updates)
            s["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            _save_situations(situations)
            return True
    return False


def format_for_ntfy() -> str:
    """生成 ntfy 推送格式的事件状态摘要。"""
    situations = _load_situations()
    active = [s for s in situations if s.get("status") != "resolved"]

    if not active:
        return "当前没有追踪中的事件。"

    lines = []
    for s in active:
        icon = {"escalating": "🔴", "de-escalating": "🟡",
                "watching": "🔵", "calm": "⚪"}.get(s.get("status", "watching"), "🔵")
        status_label = _STATUS_LABELS.get(s.get("status", "watching"), "观察中")
        lines.append(f"{icon} {s['name']}（{status_label}）")
        if s.get("recent_signals"):
            lines.append(f"   └ {s['recent_signals'][0][:45]}…")

    return "\n".join(lines)


if __name__ == "__main__":
    # 直接运行：打印当前事件状态
    print(format_for_ntfy())
    print("\n--- context 注入预览 ---")
    print(get_context())
