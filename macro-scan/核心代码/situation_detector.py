"""
situation_detector.py — 情境自动涌现检测器（Phase 2，v1.0）

每日 06:30 运行（弱信号扫描 06:00 结束后）。
从 news.db 最近7天文章中提取高频话题簇，
通过 LLM 判断是否为新兴情况，写入 situations.yaml。

设计原则：
  - 宁漏不滥：LLM 判断"跳过"比新建更容易
  - 人在回路：auto_generated=true 的条目需用户48h内确认
  - 职责边界：只处理 ALERT_KEYWORDS 之外的新话题
  - 非阻断：失败不影响其他任务

包含9项安全设计：中文分词/EWMA基线/持续时间过滤/关键词边界/
                   LLM上限/JSON容错/分级推送/自动恢复/降级
"""
import json
import os
import re
import sqlite3
import sys
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = Path(__file__).parent.parent
    DATA_DIR  = str(Path(WORKSPACE) / "data")

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

NEWS_DB_PATH       = os.path.join(DATA_DIR, "news.db")
SITUATIONS_FILE    = os.path.join(DATA_DIR, "situations.yaml")
ARCHIVE_FILE       = os.path.join(DATA_DIR, "situations_archive.yaml")
NTFY_TOPIC         = os.environ.get("NTFY_TOPIC", "")

# 已知类别关键词（情境检测应跳过这些，避免与 signal_synthesizer 重叠）
from alert_config import ALERT_KEYWORDS
_EXISTING_KWS = {kw.lower() for kws in ALERT_KEYWORDS.values() for kw in kws}
assert len(_EXISTING_KWS) > 0, "ALERT_KEYWORDS 为空，alert_config 加载失败"

# 每次最多传给 LLM 的候选话题数
_MAX_CANDIDATES = 10
# TF-IDF 触发阈值（补丁2：频率比≥1.5 + 持续≥3天）
_FREQ_RATIO_THRESHOLD = 1.5
_MIN_DAYS_ACTIVE = 3


# ── 补丁1：中文分词 ─────────────────────────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    """中英文混合分词：中文用 jieba，英文直接分割。"""
    try:
        import jieba
        # 中文分词
        words = list(jieba.cut(text))
        # 过滤停用词和单字
        stop = {"的", "了", "在", "是", "和", "与", "或", "但", "而", "也", "对",
                "中", "于", "及", "等", "被", "为", "从", "以", "将", "已",
                "a", "an", "the", "is", "in", "to", "of", "and", "for"}
        return [w for w in words if len(w) > 1 and w.lower() not in stop]
    except ImportError:
        # jieba 不可用时降级为简单分割
        tokens = re.findall(r'[一-鿿]{2,}|[a-zA-Z]{3,}', text)
        return tokens


# ── 数据读取 ─────────────────────────────────────────────────────────────────
def _fetch_recent_articles(days: int = 7) -> list[dict]:
    """从 news.db 读取最近 N 天的文章。"""
    if not os.path.exists(NEWS_DB_PATH):
        return []
    try:
        import pg_read as _pg
        conn = _pg.connect()
        if conn is None:
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()[:19]
        rows = conn.execute("""
            SELECT title, ingested_at FROM news.articles
            WHERE ingested_at >= %s
            ORDER BY ingested_at DESC
            LIMIT 2000
        """, (cutoff,)).fetchall()
        conn.close()
        return [{"title": r[0], "date": r[1][:10]} for r in rows if r[0]]
    except Exception as e:
        print(f"[detector] news.db 读取失败: {e}")
        return []


def _fetch_baseline_articles(days: int = 30) -> list[dict]:
    """读取过去 30 天文章用于基线计算。"""
    if not os.path.exists(NEWS_DB_PATH):
        return []
    try:
        import pg_read as _pg
        conn = _pg.connect()
        if conn is None:
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()[:19]
        rows = conn.execute("""
            SELECT title, ingested_at FROM news.articles
            WHERE ingested_at >= %s
            ORDER BY ingested_at DESC
            LIMIT 10000
        """, (cutoff,)).fetchall()
        conn.close()
        return [{"title": r[0], "date": r[1][:10]} for r in rows if r[0]]
    except Exception:
        return []


# ── 补丁2：EWMA 基线 + 话题聚类 ──────────────────────────────────────────────
def _compute_word_freq(articles: list[dict]) -> dict[str, dict[str, int]]:
    """返回 {word: {date: count}}，按日期统计词频。"""
    freq = defaultdict(lambda: defaultdict(int))
    for art in articles:
        words = _tokenize(art.get("title", ""))
        date = art.get("date", "")
        for w in words:
            if w.lower() not in _EXISTING_KWS:  # 补丁4：跳过已知关键词
                freq[w][date] += 1
    return freq


def _compute_ewma_baseline(daily_counts: dict[str, int], span: int = 14) -> float:
    """用指数加权移动平均（EWMA）计算基线频率。"""
    if not daily_counts:
        return 0.0
    dates = sorted(daily_counts.keys())
    values = [daily_counts[d] for d in dates]
    alpha = 2 / (span + 1)
    ewma = values[0]
    for v in values[1:]:
        ewma = alpha * v + (1 - alpha) * ewma
    return ewma


def _detect_emerging_topics(recent: list[dict], baseline: list[dict]) -> list[dict]:
    """
    检测新兴话题：7日频率 vs EWMA基线 ≥ 2.0，且持续 ≥ 3 天。
    返回候选话题列表，每条含 word/freq_ratio/active_days/sample_titles。
    """
    recent_freq = _compute_word_freq(recent)
    baseline_freq = _compute_word_freq(baseline)

    candidates = []
    for word, date_counts in recent_freq.items():
        # 补丁3：持续时间过滤（至少3天出现）
        active_days = sum(1 for v in date_counts.values() if v > 0)
        if active_days < _MIN_DAYS_ACTIVE:
            continue

        recent_total = sum(date_counts.values())
        baseline_all = baseline_freq.get(word, {})
        baseline_val = _compute_ewma_baseline(baseline_all) * 7  # 换算为7日预期量
        if baseline_val < 1:
            baseline_val = 1  # 避免除零

        ratio = recent_total / baseline_val
        if ratio < _FREQ_RATIO_THRESHOLD:
            continue

        # 取代表标题（含该词的最新3条）
        sample = [a["title"] for a in recent if word in a.get("title", "")][:3]

        candidates.append({
            "word": word,
            "freq_ratio": round(ratio, 2),
            "active_days": active_days,
            "recent_count": recent_total,
            "sample_titles": sample,
        })

    # 按频率比降序，取前 _MAX_CANDIDATES 个（补丁5：LLM输入上限）
    candidates.sort(key=lambda x: -x["freq_ratio"])
    return candidates[:_MAX_CANDIDATES]


# ── 情境状态读取 ─────────────────────────────────────────────────────────────
def _load_current_situations() -> list[dict]:
    try:
        import yaml
        if os.path.exists(SITUATIONS_FILE):
            with open(SITUATIONS_FILE, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return (data or {}).get("situations", [])
    except Exception:
        pass
    return []


# ── 补丁6：LLM 判断 + JSON 多层容错 ─────────────────────────────────────────
def _ask_llm(candidates: list[dict], existing: list[dict]) -> list[dict]:
    """调用 LLM 判断候选话题是否为新兴情况。"""
    if not candidates:
        return []

    existing_names = [s.get("name", "") for s in existing if not s.get("needs_review", False)]
    candidate_text = "\n".join(
        f"- 词汇：{c['word']}（频率比={c['freq_ratio']}x，活跃{c['active_days']}天）\n"
        f"  代表标题：{'; '.join(c['sample_titles'][:2])}"
        for c in candidates
    )

    prompt = (
        f"以下是过去7天新出现的高频新闻话题（已排除已知金融/地缘类别）：\n\n"
        f"{candidate_text}\n\n"
        f"当前已追踪的情况：{', '.join(existing_names) or '无'}\n\n"
        "对每个候选话题，判断：\n"
        "1. 是否代表一个正在发展的新情况（非已追踪事件的延伸）\n"
        "2. 如果是，输出JSON对象：\n"
        '   {"name": "简短名称(10字以内)", "category": "GEO/MACRO/SOCIAL/CLIMATE/POLITICAL/CULTURAL",\n'
        '    "status": "watching或escalating", "signal_keywords": ["关键词1", "关键词2"],\n'
        '    "reason": "一句话说明"}\n'
        "3. 如果是噪音或已追踪事件的延伸，输出字符串 \"skip\"\n\n"
        "注意：宁可漏报，不要误报。对不确定的情况选择skip。\n"
        "输出格式：JSON数组，每个元素对应一个候选话题。"
    )

    try:
        from hybrid_llm import reason
        raw = reason(prompt, system="你是世界情势分析助手，专注判断新兴话题是否值得追踪。",
                     mode="auto", max_tokens=800)
        return _parse_llm_response_safe(raw)
    except Exception as e:
        print(f"[detector] LLM 调用失败: {e}")
        return []


def _parse_llm_response_safe(raw: str) -> list[dict]:
    """补丁6：多层容错JSON解析。"""
    if not raw:
        return []

    # 尝试1：直接解析
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
    except Exception:
        pass

    # 尝试2：提取 markdown code block
    match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, list):
                return [r for r in result if isinstance(r, dict)]
        except Exception:
            pass

    # 尝试3：提取任意 [...] 内容
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, list):
                return [r for r in result if isinstance(r, dict)]
        except Exception:
            pass

    print(f"[detector] LLM 响应格式无法解析，跳过本次：{raw[:200]}")
    return []


# ── 写入 situations.yaml ─────────────────────────────────────────────────────
def _save_new_situation(sit_data: dict, freq_ratio: float):
    """写入新情况到 situations.yaml，带 needs_review 标记。"""
    try:
        import yaml
        situations = _load_current_situations()

        sit_id = hashlib.md5(sit_data["name"].encode()).hexdigest()[:8]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 补丁7：初始状态决策
        status = "escalating" if freq_ratio >= 3.0 else "watching"

        new_entry = {
            "id": sit_id,
            "name": sit_data.get("name", ""),
            "category": sit_data.get("category", "MACRO"),
            "status": status,
            "started": today,
            "last_updated": today,
            "signal_keywords": sit_data.get("signal_keywords", []),
            "linked_indicators": [],
            "recent_signals": [],
            "notes": sit_data.get("reason", ""),
            "auto_generated": True,
            "needs_review": True,
        }
        situations.append(new_entry)

        os.makedirs(DATA_DIR, exist_ok=True)
        _tmp_303 = SITUATIONS_FILE + ".tmp"
        with open(_tmp_303, "w", encoding="utf-8") as f:
            yaml.dump({"situations": situations}, f,
                      allow_unicode=True, default_flow_style=False, sort_keys=False)
        os.replace(_tmp_303, SITUATIONS_FILE)

        print(f"  [detector] 新情况已写入：{new_entry['name']}（{new_entry['category']}，needs_review=true）")
        return new_entry
    except Exception as e:
        print(f"  [detector] 写入失败: {e}")
        return None


# ── 补丁8：archived 条目自动恢复 ─────────────────────────────────────────────
def _check_archived_escalation(recent: list[dict]):
    """检查归档条目的关键词是否在近期新闻中再次高频出现（自动恢复）。"""
    if not os.path.exists(ARCHIVE_FILE):
        return
    try:
        import yaml
        with open(ARCHIVE_FILE, encoding="utf-8") as f:
            archive_data = yaml.safe_load(f) or {}
        archived = archive_data.get("archived", [])

        for item in archived:
            keywords = item.get("signal_keywords", [])
            if not keywords:
                continue
            recent_count = sum(
                1 for a in recent
                if any(kw.lower() in (a.get("title") or "").lower() for kw in keywords)
            )
            old_avg = item.get("last_avg_ratio", 1.0)
            if recent_count > max(old_avg, 1) * 3.0:
                print(f"  [detector] 归档话题再次升温：{item['name']}，恢复追踪")
                _save_new_situation({
                    "name": item["name"],
                    "category": item.get("category", "MACRO"),
                    "signal_keywords": keywords,
                    "reason": "自动恢复：话题再次高频（频率激增>3倍）",
                }, freq_ratio=2.0)
                _push_notification(
                    f"🔔 {item['name']}再次升温",
                    f"已自动恢复追踪（话题频率激增）",
                    priority=3
                )
    except Exception as e:
        print(f"  [detector] 归档恢复检查失败（非阻断）: {e}")


# ── 补丁补充：推送 ────────────────────────────────────────────────────────────
def _push_notification(title: str, msg: str, priority: int = 3):
    """通过 ntfy 推送通知。"""
    if not NTFY_TOPIC:
        return
    try:
        import requests
        requests.post(
            "https://ntfy.sh/",
            json={"topic": NTFY_TOPIC, "title": title, "message": msg, "priority": priority},
            timeout=15,
        )
    except Exception as e:
        print(f"  [detector] ntfy 推送失败: {e}")


# ── 主入口 ───────────────────────────────────────────────────────────────────
def run():
    """主检测流程（补丁9：顶层异常捕获，非阻断）。"""
    try:
        print("[situation_detector] 开始检测新兴话题...")

        recent   = _fetch_recent_articles(days=7)
        baseline = _fetch_baseline_articles(days=30)

        if len(recent) < 10:
            print(f"  [detector] 近7天文章不足（{len(recent)}篇），跳过")
            return

        # 检查归档条目是否需要恢复
        _check_archived_escalation(recent)

        # 话题聚类
        candidates = _detect_emerging_topics(recent, baseline)
        if not candidates:
            print("  [detector] 无新话题候选，结束")
            return

        print(f"  [detector] 发现 {len(candidates)} 个候选话题，调用 LLM 判断...")

        existing = _load_current_situations()
        llm_results = _ask_llm(candidates, existing)

        new_count = 0
        for i, result in enumerate(llm_results):
            if isinstance(result, str) and result.lower() == "skip":
                continue
            if not isinstance(result, dict):
                continue
            if not result.get("name"):
                continue

            # 检查是否与已有情况重名
            existing_names = {s.get("name", "").lower() for s in existing}
            if result["name"].lower() in existing_names:
                continue

            # 获取对应候选的频率比
            freq_ratio = candidates[i]["freq_ratio"] if i < len(candidates) else 2.0
            entry = _save_new_situation(result, freq_ratio)
            if entry:
                new_count += 1
                # 补丁：分级推送
                if freq_ratio >= 3.0:
                    _push_notification(
                        f"🔍 新兴情况：{entry['name']}（{entry['category']}）",
                        f"{result.get('reason', '')}\n发送 1900 confirm_situation {entry['id']} 确认追踪",
                        priority=4
                    )
                else:
                    # 中低优先级：只发一条汇总（避免打扰）
                    pass  # 汇总推送可在主循环外统一处理

        if new_count > 0:
            print(f"  [detector] 新增 {new_count} 个待确认情况，已推送通知")
        else:
            print("  [detector] LLM 判断：无需新建情况")

    except Exception as e:
        print(f"[situation_detector] 运行失败（非阻断）: {e}")


if __name__ == "__main__":
    run()
