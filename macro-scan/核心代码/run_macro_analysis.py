#!/usr/bin/env python3
"""
实时宏观分析脚本 - P5工作流落地实现
整合：FRED指标 + akshare中国数据 + RAG知识库 + 危机对照 + Ollama推理

完整分析管道（8步骤）：
  Step 1  获取当前指标快照（FRED + akshare，失败时回退缓存）
  Step 2  计算衰退/通胀风险评分（LEI加权框架，0-100分）
  Step 3  匹配历史危机情景（CSV指标欧几里德距离匹配）
  Step 4  RAG知识库检索（pgvector向量检索 → TF-IDF降级）
  Step 5  体制检测 + 蒙特卡洛概率模拟（5000路径，12个月）
  Step 6  构建LLM提示词（注入数据+信号+RAG上下文）
  Step 7  调用Ollama推理（降级链：qwen3 → mimo → 纯数据报告）
  Step 8  保存报告（按国家/深度幂等命名，避免cron重复执行）

支持参数：
  --country  us | china | both（默认 us）
  --depth    quick | standard | deep（默认 standard）
  --topic    综合 | 衰退 | 通胀 | 市场 | 地缘（默认 综合）
  --force    跳过幂等检查，强制重跑

作者：宏观经济专家Agent
日期：2026-05-12
"""

import os
import sys
import json
import time
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import uuid
import io
import subprocess

# 体制检测模块
from regime_detector import detect_regime, get_coefficients

# 评分函数模块（从 scorer.py 提取）
from scorer import (
    score_recession_risk,
    score_inflation_risk,
    score_china_recession_risk,
    score_china_inflation_risk,
    match_crisis,
    match_china_crisis,
)

# 数据获取层（FRED + 中国指标 + 缓存管理，从 data_fetcher.py 导入）
from data_fetcher import (
    _get_kb_dir_hash,
    _detect_fred_proxy,
    get_fred_latest,
    get_fred_with_yoy,
    get_current_snapshot,
    get_china_current_snapshot,
)

# MC 引擎模块（蒙特卡洛/情景模拟，从 mc_engine.py 导入）
from mc_engine import (
    FEEDBACK_LOOPS,
    SCENARIOS,
    run_china_monte_carlo,
    run_stress_test,
    compare_all_scenarios,
)

# 行业轮动模块（可选，失败不阻断主流程）
try:
    from sector_rotation import get_sector_rotation_context
    _SECTOR_ROTATION_AVAILABLE = True
except ImportError:
    _SECTOR_ROTATION_AVAILABLE = False
    print("[SR] sector_rotation 模块未安装，行业轮动数据将跳过")

# 中国经济指标 akshare 数据源（替代已关闭的 NeoData）
try:
    from fetch_china_data_akshare import fetch_china_akshare
    _AKSHARE_CN_AVAILABLE = True
except ImportError:
    _AKSHARE_CN_AVAILABLE = False
    print("[AK] fetch_china_data_akshare 模块未找到，中国指标将使用降级方案")

# RAG 向量检索引擎（pgvector + bge-m3，可选；不可用时自动降级 TF-IDF）
try:
    from rag_engine import rag_query_vec as _rag_query_vec, rag_query as _rag_engine_query
    _RAG_VEC_AVAILABLE = True
except ImportError:
    _RAG_VEC_AVAILABLE = False
    _rag_engine_query = None

# 强制 UTF-8 输出（解决 Windows PowerShell/CMD 环境乱码问题）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# =========================
# 配置区
# =========================

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
# Ollama 已废弃（CF-8），保留变量仅供 rag_engine 向后兼容
# （08-23 清理：Ollama 于 CF-8 废弃，原 OLLAMA_* 死常量已删除——全仓库无 11434 实际调用）

# 项目根目录（优先用环境变量，容器内 OPENCLAW_WORKSPACE=/workspace）
BASE_DIR   = os.environ.get("OPENCLAW_WORKSPACE",
             os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_DIR             = os.path.join(BASE_DIR, "知识库", "财经知识库")
REPORT_DIR         = os.path.join(BASE_DIR, "docs", "分析报告")
SYSTEM_PROMPT_FILE = os.path.join(BASE_DIR, "system_prompt.md")

CRISIS_CSV = os.path.join(KB_DIR, "02_核心变量因果链", "历史情景_量化指标.csv")
CACHE_FILE = os.path.join(REPORT_DIR, ".indicator_cache.json")  # FRED失败时的缓存回退
LOG_DIR    = os.path.join(BASE_DIR, "logs")
_LOCK_FILE = os.path.join(LOG_DIR, ".run_macro_analysis.lock")

# 代理配置 — 由 data_fetcher 统一管理，此处引用保持兼容
import data_fetcher as _df_mod

def _get_fred_proxies():
    """返回当前生效的 FRED 代理配置（由 data_fetcher 动态检测更新）。"""
    return _df_mod.FRED_PROXIES

# ProSearch 路径（在线搜索技能）
PROSEARCH_SCRIPT = ""  # 本机无 QClaw，跳过 ProSearch
GEO_SEARCH_FILE = os.path.join(REPORT_DIR, ".geo_search_cache.json")
GEO_EVENT_LOG = os.path.join(KB_DIR, "02_核心变量因果链", "地缘事件日志.json")

# =========================
# RAG TF-IDF 模块级缓存
# =========================
_RAG_CACHE: Dict = {
    "vectorizer": None,
    "matrix": None,
    "doc_names": None,
    "docs": None,
    "dir_hash": None,
}

def _get_kb_dir_hash(kb_dir: str) -> str:
    """計算知識庫目錄哈希 - 已迁移至 data_fetcher.py，此处仅为向后兼容保留"""
    from data_fetcher import _get_kb_dir_hash as _df_hash
    return _df_hash(kb_dir)

def search_geopolitical_events(freshness: str = "7d", cnt: int = 5) -> str:
    """
    读取本地地缘事件日志 + 知识库检索，汇总近期地缘政治动态。
    优先显示 active=true 的事件，最多返回 cnt 条，附传导路径摘要。
    """
    from datetime import datetime, timedelta

    try:
        # ── Part1：读取结构化事件日志 ──────────────────────────────────────
        log_path = GEO_EVENT_LOG
        events_out = []

        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 计算时间截止点
            freshness_days = {"24h": 1, "7d": 7, "30d": 30}.get(freshness, 7)
            cutoff = datetime.now() - timedelta(days=freshness_days)

            for ev in data.get("events", []):
                if not ev.get("active", True):
                    continue
                ev_date_str = ev.get("date", "")
                try:
                    ev_date = datetime.strptime(ev_date_str, "%Y-%m-%d")
                    if ev_date < cutoff:
                        continue
                except ValueError:
                    pass  # 日期解析失败时仍纳入（active事件）

                # 风险影响摘要
                risk = ev.get("risk_impact", {})
                risk_parts = []
                for dim, detail in risk.items():
                    change = detail.get("change", 0)
                    if change != 0:
                        arrow = "↑" if change > 0 else "↓"
                        risk_parts.append(f"{dim}{arrow}{abs(change)}")

                paths = ev.get("transmission_paths", {})
                st = paths.get("short_term", "")
                watch = paths.get("key_watch", [])
                watch_str = "；".join(watch[:2]) if watch else ""

                lines = [f"**{ev.get('event', '')}**（{ev_date_str}）"]
                lines.append(f"  {ev.get('summary', '')}")
                if risk_parts:
                    lines.append(f"  风险变化：{' | '.join(risk_parts)}")
                if st:
                    lines.append(f"  短期传导：{st[:80]}")
                if watch_str:
                    lines.append(f"  关键观察：{watch_str}")

                events_out.append("\n".join(lines))
                if len(events_out) >= cnt:
                    break

        # ── Part2：TF-IDF 知识库补充检索 ────────────────────────────────────
        geo_kb = os.path.join(KB_DIR, "15_国际形势")
        kb_snippets = []
        if os.path.exists(geo_kb):
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity
                import numpy as np

                docs, names = [], []
                for fname in sorted(os.listdir(geo_kb)):
                    if fname.endswith(".md"):
                        fpath = os.path.join(geo_kb, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read().strip()
                            if len(content) > 100:
                                docs.append(content[:2000])
                                names.append(fname)
                        except Exception:
                            pass

                if docs:
                    query = "地缘政治 贸易战 台海 中东 俄乌 关税 制裁"
                    vec = TfidfVectorizer(analyzer="char", ngram_range=(1, 3),
                                         max_features=20000, sublinear_tf=True)
                    mat = vec.fit_transform(docs)
                    qv = vec.transform([query])
                    scores = cosine_similarity(qv, mat)[0]
                    top = np.argsort(scores)[::-1][:2]
                    for idx in top:
                        if scores[idx] > 0.05:
                            kb_snippets.append(f"[KB:{names[idx]}] {docs[idx][:300]}")
            except Exception:
                pass

        # ── 汇总输出 ─────────────────────────────────────────────────────────
        if not events_out and not kb_snippets:
            return "[近期无结构化地缘事件记录]"

        result_lines = []
        if events_out:
            result_lines.extend(events_out)
        if kb_snippets:
            result_lines.append("\n**知识库补充**：")
            result_lines.extend(kb_snippets)

        return "\n\n".join(result_lines)

    except Exception as e:
        return f"[地缘事件读取异常: {str(e)[:80]}]"


def load_geo_event_adjustments() -> Dict:
    """兼容旧调用：从最新活跃事件提取 change 值（保留原逻辑）。"""
    try:
        if not os.path.exists(GEO_EVENT_LOG):
            return {}
        with open(GEO_EVENT_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
        latest_active = next((e for e in events if e.get("active")), events[0] if events else None)
        if not latest_active:
            return {}
        risk_impact = latest_active.get("risk_impact", {})
        adjustments = {k: v.get("change", 0) for k, v in risk_impact.items()}
        adjustments["latest_event"] = f"{latest_active.get('event', '')} ({latest_active.get('date', '')})"
        adjustments["event_summary"] = latest_active.get("summary", "")[:200]
        return adjustments
    except Exception as e:
        print(f"  [WARN] 加载事件日志失败: {str(e)[:50]}")
        return {}


def compute_geo_risk_matrix() -> Tuple[str, Dict]:
    """
    聚合所有活跃事件的地缘政治风险矩阵。
    对每个风险维度，取最新事件的 'after' 值作为当前水平。
    计算所有活跃事件的净累计变化（change之和）。

    Returns:
        (markdown_table, dimension_levels)
        markdown_table: 已格式化的Markdown字符串，供注入prompt
        dimension_levels: {dimension: current_level} 当前风险水平字典
    """
    DIM_LABELS = {
        "taiwan_strait":    "台海局势",
        "tech_decoupling":  "科技脱钩",
        "global_trade":     "全球贸易",
        "energy_shock":     "能源冲击",
        "us_credit_risk":   "美债信用",
        "fx_pressure":      "汇率压力",
        "yen_carry_unwind": "日元套利平仓",
    }

    try:
        if not os.path.exists(GEO_EVENT_LOG):
            return "", {}
        with open(GEO_EVENT_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
        if not events:
            return "", {}

        active_events = [e for e in events if e.get("active", False)]
        if not active_events:
            active_events = events[:3]

        # 对每个维度：取最近日期中所有活跃事件里 after 值最高的（同日多事件取最大）
        current_level: Dict[str, int] = {}
        net_change: Dict[str, int] = {}
        sorted_events = sorted(active_events, key=lambda e: e.get("date", ""), reverse=True)
        for dim in DIM_LABELS:
            best_level = None
            best_date  = ""
            for evt in sorted_events:
                impact = evt.get("risk_impact", {}).get(dim)
                if not impact:
                    continue
                evt_date = evt.get("date", "")
                after_val = impact.get("after", impact.get("before", 5))
                # Only consider events on the most-recent date that mentions this dim
                if best_date and evt_date < best_date:
                    break
                best_date = evt_date
                if best_level is None or after_val > best_level:
                    best_level = after_val
            if best_level is not None:
                current_level[dim] = best_level
            net_change[dim] = sum(
                evt.get("risk_impact", {}).get(dim, {}).get("change", 0)
                for evt in active_events
            )

        if not current_level:
            return "", {}

        # 构建 Markdown 表格
        def risk_bar(level: int) -> str:
            filled = min(level, 10)
            return "█" * filled + "░" * (10 - filled)

        def change_arrow(chg: int) -> str:
            if chg > 0: return f"↑{chg}"
            if chg < 0: return f"↓{abs(chg)}"
            return "→"

        lines = ["## 地缘政治风险矩阵（当前态势）",
                 "| 风险维度 | 当前水平 | 风险条 | 净变化 |",
                 "|:--------|:-------:|:-------|:------:|"]
        for dim, label in DIM_LABELS.items():
            lv = current_level.get(dim)
            if lv is None:
                continue
            chg = net_change.get(dim, 0)
            bar = risk_bar(lv)
            arrow = change_arrow(chg)
            lines.append(f"| {label} | {lv}/10 | {bar} | {arrow} |")
        table = "\n".join(lines)
        return table, current_level

    except Exception as e:
        print(f"  [WARN] 地缘风险矩阵计算失败: {e}")
        return "", {}


# =========================
# Layer 1: 数据输入层（函数已迁移至 data_fetcher.py）
# =========================

# =========================
# Layer 1: 数据输入层（函数已迁移至 data_fetcher.py）
# =========================


def rag_query(query: str, n_results: int = 5) -> List[str]:
    """知识库检索：委托 rag_engine.rag_query()（向量优先 + TF-IDF fallback 均在引擎内处理）。"""
    if _rag_engine_query is not None:
        return _rag_engine_query(query, n_results, KB_DIR)
    # rag_engine 不可用时的最终兜底（TF-IDF 内联，仅作安全网）
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        kb_dir = KB_DIR
        if not os.path.exists(kb_dir):
            return []

        SKIP_PATTERNS = {"README.md", "readme.md", "数据字典.md"}
        SKIP_PREFIX = ("00_知识库", "00_快速参考", "README")

        dir_hash = _get_kb_dir_hash(kb_dir)
        if (_RAG_CACHE["dir_hash"] == dir_hash
                and _RAG_CACHE["vectorizer"] is not None
                and _RAG_CACHE["docs"] is not None):
            docs = _RAG_CACHE["docs"]
            doc_names = _RAG_CACHE["doc_names"]
            vectorizer = _RAG_CACHE["vectorizer"]
            tfidf_matrix = _RAG_CACHE["matrix"]
        else:
            docs, doc_names = [], []
            for root, _, files in os.walk(kb_dir):
                for fname in sorted(files):
                    if not fname.endswith(".md"):
                        continue
                    if fname in SKIP_PATTERNS or any(fname.startswith(p) for p in SKIP_PREFIX):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read().strip()
                        if len(content) > 200:
                            docs.append(content[:5000])
                            doc_names.append(fpath)
                    except Exception:
                        pass

            if not docs:
                return []

            vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3),
                                         max_features=60000, sublinear_tf=True)
            tfidf_matrix = vectorizer.fit_transform(docs)
            _RAG_CACHE["vectorizer"] = vectorizer
            _RAG_CACHE["matrix"] = tfidf_matrix
            _RAG_CACHE["docs"] = docs
            _RAG_CACHE["doc_names"] = doc_names
            _RAG_CACHE["dir_hash"] = dir_hash

        query_vec = vectorizer.transform([query])
        scores = cosine_similarity(query_vec, tfidf_matrix)[0]
        top_indices = np.argsort(scores)[-n_results:][::-1]
        results = []
        for idx in top_indices:
            if scores[idx] < 0.05:
                continue
            name = os.path.relpath(doc_names[idx], kb_dir)
            full_text = docs[idx]
            best_snippet = full_text[:800]
            if len(full_text) > 800:
                window_size = 800
                step = 400
                win_vecs = vectorizer.transform([
                    full_text[i:i + window_size]
                    for i in range(0, len(full_text) - window_size, step)
                ])
                win_scores = cosine_similarity(query_vec, win_vecs)[0]
                best_win_idx = int(np.argmax(win_scores))
                if win_scores[best_win_idx] > 0:
                    offset = best_win_idx * step
                    best_snippet = full_text[offset:offset + window_size]
            snippet = best_snippet.replace("\n\n\n", "\n\n").strip()
            results.append(f"【{name}】\n{snippet}")
        return results
    except Exception as e:
        print(f"  [TF-IDF RAG] 检索失败: {e}")
        return []


# =========================
# Layer 3: 推理输出层
# =========================

_SYSTEM_PROMPT = None  # 懒加载缓存，每个进程只读一次文件


def _get_system_prompt() -> dict:
    import logging
    """读取 system_prompt.md，解析四个 ## 小节；文件缺失时使用内置默认值。"""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is not None:
        return _SYSTEM_PROMPT

    _defaults = {
        "role": "你是一位{country}宏观经济学家，请基于以下信息，撰写一份结构化分析报告。",
        "china": (
            "1. **核心判断**（100字）：当前中国经济处于什么阶段？复苏/放缓/衰退/滞胀？给出明确阶段定位，注意区分\"复苏\"与\"恢复性增长\"。\n"
            "2. **主要风险**（200字）：列出1-3个最重要的风险因素，每个风险需说明：①触发条件 ②传导路径（如：房地产下滑→地方财政收入减少→基建投资放缓→GDP拖累）③可能的阻断条件。利用知识库中的因果链数据。\n"
            "3. **国际环境**（100字）：分析美国货币政策和全球需求对中国的影响（美联储利率路径、中美利差、地缘贸易摩擦、全球供应链变化）。\n"
            "4. **情景分析**（300字）：结合蒙特卡洛模拟概率区间，给出3种情景（基准/乐观/悲观），包含①概率 ②关键假设 ③GDP增速/CPI/PPI预测值 ④触发条件。基准情景概率不超过70%。\n"
            "5. **政策建议**（200字）：对人民银行当前货币政策（降准/降息/LPR调整）和财政政策的评价，给出具体政策预期（时间表、力度判断）。如果存在通缩压力，应明确提出应对建议。\n"
            "6. **大类资产影响**（150字）：A股/国债/人民币/大宗商品的3个月方向判断，给出具体配置建议（超配/低配/标配）。\n"
            "7. **领先指标追踪**（100字）：未来1-3个月需重点关注的2-3个指标，说明关注理由。\n"
            "8. **预警新闻边际影响**（100字）  ⚠️ 必须引用具体数值，不能只写笼统描述。"
        ),
        "us": (
            "1. **核心判断**（100字）：当前宏观环境处于什么阶段？扩张/放缓/衰退/滞胀？给出明确阶段定位。\n"
            "2. **主要风险**（200字）：列出1-3个最重要的风险因素，每个风险需说明：①触发条件 ②传导路径（从哪个变量到哪个变量）③可能的阻断条件。利用知识库中的因果链数据。\n"
            "3. **国际环境**（100字）：分析当前全球经济环境对美国的影响（中国经济、欧洲政策、地缘事件、大宗商品市场）。\n"
            "4. **情景分析**（300字）：结合蒙特卡洛衰退概率（已提供区间），给出3种情景（基准/乐观/悲观），每个情景包含①概率 ②关键假设 ③GDP/CPI/失业率预测值 ④触发条件。基准情景概率不超过70%。\n"
            "5. **政策建议**（200字）：对美联储当前立场的评价，以及具体的政策预期（下次FOMC动作、时间表、概率判断）。如果建议降息/加息，需给出具体bp数和时间节点。\n"
            "6. **大类资产影响**（150字）：股票/债券/大宗商品/汇率的3个月方向判断，给出具体配置建议（超配/低配/标配）。\n"
            "7. **领先指标追踪**（100字）：关注消费者信心/新屋开工/职位空缺等领先指标的最新读数及其信号含义。\n"
            "8. **预警新闻边际影响**（100字）  ⚠️ 必须引用具体数值，不能只写笼统描述。"
        ),
        "word_limit": "请用简洁的中文撰写，总字数控制在1600字以内。",
    }

    if not os.path.exists(SYSTEM_PROMPT_FILE):
        logging.info("[SystemPrompt] system_prompt.md 不存在，使用内置默认值")
        _SYSTEM_PROMPT = _defaults
        return _SYSTEM_PROMPT

    try:
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as _f:
            _raw = _f.read()
        _sections = {}
        _cur_key = None
        _buf = []
        for _line in _raw.splitlines():
            if _line.startswith("## "):
                if _cur_key:
                    _sections[_cur_key] = "\n".join(_buf).strip()
                _cur_key = _line[3:].strip()
                _buf = []
            elif _line.strip() == "---":
                pass
            else:
                if _cur_key is not None:
                    _buf.append(_line)
        if _cur_key:
            _sections[_cur_key] = "\n".join(_buf).strip()
        _SYSTEM_PROMPT = {
            "role":       _sections.get("角色定义")         or _defaults["role"],
            "china":      _sections.get("分析要求 · 中国版") or _defaults["china"],
            "us":         _sections.get("分析要求 · 美国版") or _defaults["us"],
            "word_limit": _sections.get("字数与格式要求")    or _defaults["word_limit"],
        }
        logging.info(f"[SystemPrompt] 已加载 {SYSTEM_PROMPT_FILE}")
    except Exception as _exc:
        logging.warning(f"[SystemPrompt] 加载失败({_exc})，使用内置默认值")
        _SYSTEM_PROMPT = _defaults
    return _SYSTEM_PROMPT


def format_news_for_prompt(json_path: str = None, country: str = "us") -> str:
    """读取 latest_news.json，格式化为 prompt 注入文本。无文件时返回空字符串。"""
    if json_path is None:
        json_path = os.path.join(BASE_DIR, "data", "latest_news.json")
    if not os.path.exists(json_path):
        return ""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            alerts = json.load(f)
        if not alerts:
            return ""

        # 中国模式：区分本地/全球信号，防止LLM将WTI/JPY等误用为中国PPI/CPI
        _GLOBAL_KEYWORDS = ("WTI", "原油", "日本", "日元", "JPY", "日经",
                            "EUR", "欧元", "英镑", "GBP", "VIX", "标普",
                            "美债", "美国国债", "穆迪美国", "Moody", "LIBOR")
        def _is_global(item: dict) -> bool:
            title = item.get("title", item.get("indicator", ""))
            return any(kw in title for kw in _GLOBAL_KEYWORDS)

        lines = ["\n## 实时预警信号（弱信号扫描结果，请在「第8条」中逐一引用具体数值）"]

        if country == "china":
            lines.append(
                "\n⚠️ 以下信号分两类：【中国本地】直接反映中国经济；【全球背景】为间接传导，"
                "分析时禁止将全球指标数值（如WTI油价）直接用作中国本土指标（如中国PPI）的数值。\n"
            )
        else:
            lines.append("\n【预警明细——第8条分析时必须引用以下数值】\n")

        alert_order = {"CRISIS": 1, "STRESS": 2, "WARNING": 3}
        alerts_sorted = sorted(alerts, key=lambda x: alert_order.get(x.get("alert_type", "WARNING"), 99))

        for item in alerts_sorted:
            atype     = item.get("alert_type", "WARNING")
            indicator = item.get("title", item.get("indicator", "未知指标"))
            current   = item.get("current", "")
            z_score   = item.get("z_score", "")
            direction = item.get("direction", "")
            date      = item.get("date", "")
            val_part  = f"当前值={current}" if current else "（无当前值）"
            z_part    = f" | Z-score={z_score}" if z_score else ""
            dir_part  = f" | {direction}" if direction else ""
            tag       = "【全球背景】" if (country == "china" and _is_global(item)) else "【中国本地】" if country == "china" else ""
            lines.append(f"  ◆ [{atype}] {tag}{indicator} → {val_part}{z_part}{dir_part} （日期：{date}）")
            titles = item.get("trigger_titles", [])
            if titles:
                lines.append(f"    代表文章：{' | '.join(titles[:3])}")

        lines.append("\n⚠️ 第8条必须包含至少2个上述具体数值（如Z=4.59、GDP=4.2%等），不得只写笼统描述。")
        return "\n".join(lines)
    except Exception as e:
        print(f"  [News] 读取 latest_news.json 失败：{e}")
        return ""


def generate_report(
    indicators: Dict,
    recession_result: Tuple[str, int, List],
    inflation_result: Tuple[str, int, List],
    crisis_matches: List[Tuple[str, float, str]],
    rag_chunks: List[str],
    country: str = "us",
    news_text: str = "",
    geo_events: str = "",
    mc_result: dict = None,
    regime: str = "normal",
    intl_context: str = "",
    spillover_text: str = "",
    crucix_context: str = "",
    narrative_context: str = "",
) -> str:
    """构建LLM提示词并调用LLM生成分析报告。

    流程：
    1. 组装数据表格（去重，跳过内部键）
    2. 构建蒙特卡洛摘要（季度路径表）
    3. 按国家拼接提示词（中文8条/美国8条，含数据锚点）
    4. 调用 call_llm_primary()（主链 auto=MiMo→SiliconFlow；失败纯数据报告）
    5. 附加LEI指数块、溢出分析块

    Returns:
        完整报告文本（Markdown格式）
    """

    # 数据质量注意（China数据不可用时）
    data_note = indicators.get("_data_note", "")

    # 组装数据表格
    SKIP_DISPLAY_KEYS = {"_crucix", "VIXCLS", "FEDFUNDS", "BAMLH0A0HYM2EY", "_data_note"}
    data_lines = []
    seen_names = set()
    for sid, info in indicators.items():
        if sid.startswith("_") or sid in SKIP_DISPLAY_KEYS:
            continue
        name = info.get("name", sid)
        if name in seen_names:
            continue
        seen_names.add(name)
        if info.get("value") is not None:
            source_mark = " [缓存]" if info.get("source") == "cache" else ""
            val = info['value']
            val_str = f"{float(val):.4f}" if isinstance(val, (int, float)) else str(val)
            data_lines.append(f"- {name}：{val_str}（{info['date']}）{source_mark}")
    data_table = "\n".join(data_lines)

    # 组装信号
    r_label, r_score, r_signals = recession_result
    i_label, i_score, i_signals = inflation_result

    recession_signals = "\n".join([f"  - {s[0]}：{s[1]}" for s in r_signals]) or "  无明显衰退信号"
    inflation_signals = "\n".join([f"  - {s[0]}：{s[1]}" for s in i_signals]) or "  无明显通胀压力"

    # 历史情景
    crisis_text = "\n".join([f"  {i+1}. {c[0]}（匹配度：{c[1]}%）— {c[2]}" for i, c in enumerate(crisis_matches)])

    # RAG上下文（放大到600字符以获取更多内容）
    rag_text = "\n\n".join([f"[{i+1}] {chunk[:600]}" for i, chunk in enumerate(rag_chunks)])

    # 蒙特卡洛摘要（注入定量概率分布）
    mc_section = ""
    if mc_result:
        cal = "[历史校准]" if mc_result.get("calibrated") else "[固定参数]"
        gdp = mc_result.get("gdp", {})
        ur  = mc_result.get("unrate", {})
        cpi = mc_result.get("cpi", {})
        fb  = mc_result.get("feedback", [])
        # 季度路径预测（3/6/12个月节点）
        q = mc_result.get("quarterly", {})
        quarterly_lines = []
        if q:
            gdp_q = q.get("gdp", {})
            cpi_q = q.get("cpi", {})
            ur_q  = q.get("unrate", {})
            quarterly_lines.append("- 季度路径预测（中位数路径）：")
            quarterly_lines.append(
                f"  | 时间节点 | GDP增速 | CPI | 失业率 |"
            )
            quarterly_lines.append("  |:-------:|:------:|:---:|:------:|")
            for m, label in [(3, "3个月"), (6, "6个月"), (12, "12个月")]:
                g = gdp_q.get(f"m{m}", "—")
                c = cpi_q.get(f"m{m}", "—")
                u = ur_q.get(f"m{m}", "—")
                quarterly_lines.append(f"  | {label} | {g}% | {c}% | {u}% |")
        quarterly_text = "\n".join(quarterly_lines)
        mc_section = f"""
## 蒙特卡洛定量模拟（12个月，5000路径）{cal}
- 体制：{regime} | 压力信号：{mc_result.get('stress_signals', '?')}/7
- 衰退概率：{mc_result.get('recession_prob', '?')}% | 危机态概率：{mc_result.get('crisis_state_pct', '?')}%
- GDP分布：均值 {gdp.get('mean', '?')}%，5%分位 {gdp.get('p5', '?')}%，95%分位 {gdp.get('p95', '?')}%
- 失业率分布：均值 {ur.get('mean', '?')}%，95%分位 {ur.get('p95', '?')}%
- CPI分布：均值 {cpi.get('mean', '?')}%，95%分位 {cpi.get('p95', '?')}%
- 活跃反馈回路：{', '.join([f'{k}({v:.1f}%)' for k, v in fb[:3]]) if fb else '无'}
{quarterly_text}"""

    # 加载外部 system prompt（懒加载，缺文件时自动降级内置值）
    _sp = _get_system_prompt()

    # 按国家调整提示词
    if country == "china":
        country_ctx = "中国"
        analysis_req = _sp["china"]
        # 数据锚点：把实测值显式注入，防止LLM幻觉或用全球数据替代中国数据
        _anchor = []
        for _k, _label in [("ppi","PPI同比"), ("cpi","CPI同比"), ("pmi_mfg","制造业PMI"),
                            ("gdp_growth","GDP增速"), ("industrial_va","工业增加值"), ("m2_growth","M2增速")]:
            _v = indicators.get(_k, {}).get("value") if isinstance(indicators, dict) else None
            if _v is not None:
                _anchor.append(f"{_label}={_v:+.2f}%" if _label not in ("制造业PMI",) else f"{_label}={_v:.1f}")
        if _anchor:
            analysis_req += (
                f"\n\n⚠️ 数据基准（严禁幻觉）：当前中国实测值为 {', '.join(_anchor)}。"
                "情景分析中的预测数字必须从这些基准值合理推演，禁止生成与上表矛盾的数字（例如：若PPI实测为负，情景不得预测PPI为正两位数）。"
                "知识库/RAG历史内容引用时须标注[历史参考]，不得作为当前实际值使用。"
            )
    else:
        country_ctx = "美国"
        analysis_req = _sp["us"]

    # 国际环境辅助数据（欧洲/日本）
    intl_section = f"\n## 全球环境参考\n{intl_context}" if intl_context else ""

    # 地缘政治风险矩阵
    geo_matrix_table, _geo_levels = compute_geo_risk_matrix()
    geo_matrix_section = f"\n{geo_matrix_table}\n" if geo_matrix_table else ""

    # 反馈回路激活状态（中国版 vs 美国版）
    if country == "china":
        feedback_section = evaluate_feedback_loops_china(indicators)
    else:
        feedback_section = evaluate_feedback_loops_status(indicators)

    # 领先经济指标合成评分（中国版 vs 美国版）
    if country == "china":
        lei_section = compute_lei_composite_china(indicators)
    else:
        lei_section = compute_lei_composite(indicators)

    # 跨国溢出分析（仅 both 模式传入）
    spillover_section = f"\n{spillover_text}\n" if spillover_text else ""

    # 构建提示词
    data_note_section = f"\n> **数据注意**: {data_note}\n" if data_note else ""
    _role_line  = _sp["role"].replace("{country}", country_ctx)
    _word_limit = _sp["word_limit"]
    prompt = f"""{_role_line}
{data_note_section}
## 当前{country_ctx}宏观数据（{datetime.now().strftime("%Y-%m-%d")}）
{data_table}

## 衰退风险评估
风险等级：{r_label}（{r_score}/100）
触发信号：
{recession_signals}

## 通胀风险评估
风险等级：{i_label}（{i_score}/100）
触发信号：
{inflation_signals}
{mc_section}{geo_matrix_section}{feedback_section}
{lei_section}
{spillover_section}
## 历史情景对照
最匹配的危机情景：
{crisis_text}

## 知识库相关背景（RAG检索）
{rag_text}
{intl_section}
## 实时预警新闻（弱信号扫描）
{news_text}

## 最新地缘政治事件
{geo_events}
{crucix_context}
{narrative_context}
## 分析要求：
{analysis_req}

{_word_limit}
"""

    return prompt


def _mimo_fallback(prompt: str) -> str:
    """Ollama 不可用时尝试 MiMo（仅在 OPENAI_COMPAT_URL 已配置时生效）"""
    if not os.environ.get("OPENAI_COMPAT_URL"):
        return ""
    try:
        from hybrid_llm import call_openai_compat
        print("  [MiMo] LLM 不可用，降级 MiMo...")
        return call_openai_compat(prompt)
    except Exception as e:
        print(f"  [MiMo] 调用失败: {e}")
        return ""


def call_llm_primary(prompt: str, mode: str = "local") -> str:
    """调用 LLM 生成分析报告（08-23 由 call_ollama 更名——Ollama 早在 CF-8 废弃，
    本函数从未发起过 11434 请求，实际直接走 hybrid_llm.reason()）。

    主链与降级（任一失败自动切换下一级）：
      1. hybrid_llm.reason(mode)：mode="auto"（默认）→ MiMo → Claude(未配跳过) → SiliconFlow；
         mode="local" → 强制 SiliconFlow Qwen3.5-27B
      2. MiMo API 兜底（_mimo_fallback）
      3. 空字符串（调用方负责降级到 _make_fallback_section）
    """
    print(f"\n[5/7] 调用LLM生成报告（mode={mode}）...")

    # 统一走 hybrid_llm（SiliconFlow 为默认后端）
    try:
        from hybrid_llm import reason
        print(f"[call_llm_primary] mode={mode} | prompt_chars={len(prompt)} → 调用 hybrid_llm.reason()")
        return reason(prompt, mode=mode, max_tokens=6144)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[call_llm_primary] hybrid_llm 失败（{type(e).__name__}: {e}），尝试 MiMo 降级...")

    # MiMo 降级
    try:
        result = _mimo_fallback(prompt)
        if result:
            print(f"[call_llm_primary] MiMo 降级成功，result_chars={len(result)}")
            return result
    except Exception as e:
        print(f"[call_llm_primary] MiMo 也失败: {type(e).__name__}: {e}")

    print(f"[call_llm_primary] 全部 LLM 失败，返回空字符串（触发 fallback section）")
    return ""


def _make_fallback_section(
    country: str,
    indicators: Dict,
    recession_result,
    inflation_result,
    mc: Optional[Dict],
    regime: str,
) -> str:
    """LLM不可用时的结构化降级报告（纯Python，无需LLM）"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    country_zh = {"us": "美国", "china": "中国"}.get(country, country)
    rec_level = recession_result[0] if recession_result else "—"
    rec_score = recession_result[1] if recession_result else 0
    inf_level = inflation_result[0] if inflation_result else "—"
    inf_score = inflation_result[1] if inflation_result else 0
    regime_zh = {"normal": "常态", "stress": "压力", "crisis": "危机"}.get(regime, regime)

    lines = [
        f"## {country_zh}宏观快照（{now_str}）",
        f"> ⚠️ LLM 不可用，以下为纯数据自动报告",
        "",
        f"**体制：{regime_zh}** | 衰退风险：{rec_level}（{rec_score}/100） | 通胀风险：{inf_level}（{inf_score}/100）",
        "",
    ]

    # 核心指标快照
    KEY_INDICATORS = {
        "us":    ["CPIAUCSL", "PCEPI", "PPIACO", "GDPC1", "UNRATE",
                  "DFF", "DGS10", "DCOILWTICO", "SP500", "SAHM_RULE", "BAA10Y"],
        "china": ["gdp_growth", "cpi", "ppi", "pmi_mfg", "m2_growth", "real_estate_price"],
    }
    keys = KEY_INDICATORS.get(country, list(indicators.keys())[:10])

    lines += ["### 核心指标", "| 指标 | 最新值 | 日期 |", "|:----|:---:|:---:|"]
    for k in keys:
        d = indicators.get(k, {})
        name = d.get("name", k)
        val  = d.get("value")
        date = d.get("date", "")
        if val is not None:
            val_str = f"{val:.2f}" if isinstance(val, float) else str(val)
            lines.append(f"| {name} | {val_str} | {date[:7] if date else '—'} |")
    lines.append("")

    # MC 模拟结果
    if mc:
        rec_prob = mc.get("recession_prob", 0)
        gdp  = mc.get("gdp", {})
        cpi  = mc.get("cpi", {})
        unr  = mc.get("unemployment", {})
        cal  = "（历史校准）" if mc.get("calibrated") else ""
        lines += [
            "### Monte Carlo 模拟结果",
            f"- **衰退概率**：{rec_prob}% {cal}",
            f"- **GDP** 均值 {gdp.get('mean','—')}%，5% 分位 {gdp.get('p5','—')}%，95% 分位 {gdp.get('p95','—')}%",
        ]
        if cpi.get("mean") is not None:
            lines.append(f"- **CPI** 均值 {cpi.get('mean','—')}%")
        if unr.get("mean") is not None:
            lines.append(f"- **失业率** 均值 {unr.get('mean','—')}%")
        lines.append("")

    lines.append("> *自动降级报告。使用 `--reasoning claude` 可获得 LLM 叙事分析。*")
    return "\n".join(lines)


# =========================
# Layer 4: 蒙特卡洛模拟层
# =========================


def compute_cross_country_spillover(
    us_mc: dict,
    china_mc: dict,
    us_indicators: dict | None = None,
    china_indicators: dict | None = None,
) -> str:
    """
    基于跨国传导矩阵，计算中美经济相互溢出影响（多渠道 v2）。
    渠道：GDP传导、油价渠道、美国信用/财政风险渠道、贸易关税渠道。
    系数来源：知识库/04_跨国联动矩阵/跨国传导矩阵_中美欧日联动系数.md
    """
    if not us_mc or not china_mc:
        return ""

    try:
        ind    = us_indicators or {}
        cn_ind = china_indicators or {}

        # ── 1. GDP传导（6M滞后，历史回归系数）──────────────────────
        US_TO_CN_6M = -0.45   # 美国GDP偏离2.5%基准每1ppt → 中国GDP 6M
        CN_TO_US_6M = -0.18   # 中国GDP偏离5.0%基准每1ppt → 美国GDP 6M

        us_base = us_mc.get("gdp", {}).get("mean", 2.4)
        us_p5   = us_mc.get("gdp", {}).get("p5",   1.4)
        cn_base = china_mc.get("gdp", {}).get("mean", 4.8)
        cn_p5   = china_mc.get("gdp", {}).get("p5",   3.5)

        gdp_us_on_cn_base = US_TO_CN_6M * (us_base - 2.5)
        gdp_us_on_cn_p5   = US_TO_CN_6M * (us_p5   - 2.5)
        gdp_cn_on_us_base = CN_TO_US_6M * (cn_base - 5.0)
        gdp_cn_on_us_p5   = CN_TO_US_6M * (cn_p5   - 5.0)

        rows = [
            f"| 美国GDP({us_base:.1f}%) | 中国GDP | {gdp_us_on_cn_base:+.2f}ppt | {gdp_us_on_cn_p5:+.2f}ppt | 出口需求↓→制造业PMI（6M）|",
            f"| 中国GDP({cn_base:.1f}%) | 美国GDP | {gdp_cn_on_us_base:+.2f}ppt | {gdp_cn_on_us_p5:+.2f}ppt | 贸易直接传导（6M）|",
        ]

        # ── 2. 油价渠道（双向；WTI高于$80触发）────────────────────
        oil = ind.get("DCOILWTICO", {}).get("value")
        oil_on_us_base = oil_on_us_p5 = 0.0
        oil_on_cn_base = oil_on_cn_p5 = 0.0
        if oil is not None and oil > 80:
            # IMF研究：$10/桶↑ → 美国GDP约-0.09ppt（6-9M，含消费挤压）
            # 中国能源高度对外依存：$10/桶↑ → -0.07ppt（进口成本+制造利润）
            excess_tens  = (oil - 80) / 10
            oil_on_us_base = -0.09 * excess_tens
            oil_on_cn_base = -0.07 * excess_tens
            p5_mult = 1.5 if oil > 110 else 1.2   # WTI>110：需求破坏效应加速
            oil_on_us_p5 = oil_on_us_base * p5_mult
            oil_on_cn_p5 = oil_on_cn_base * p5_mult
            rows.append(
                f"| 油价(WTI {oil:.0f}$) | 美国GDP | {oil_on_us_base:+.2f}ppt | {oil_on_us_p5:+.2f}ppt | PPI↑→CPI↑→消费需求挤压（6-9M）|"
            )
            rows.append(
                f"| 油价(WTI {oil:.0f}$) | 中国GDP | {oil_on_cn_base:+.2f}ppt | {oil_on_cn_p5:+.2f}ppt | 能源进口成本↑→制造利润压缩（6M）|"
            )

        # ── 3. 美国信用/财政风险渠道 → 中国资本流动 ────────────────
        baa10y = ind.get("BAA10Y", {}).get("value")
        credit_on_cn_base = credit_on_cn_p5 = 0.0
        if baa10y is not None and baa10y > 1.5:
            # 穆迪警告+信用利差↑ → 全球避险 → EM资本外流
            # 每100bp超过1.5%基准 → 中国GDP -0.10ppt（人民币贬压+PBOC两难，3M）
            excess = baa10y - 1.5
            credit_on_cn_base = -0.10 * excess
            credit_on_cn_p5   = -0.18 * excess
            rows.append(
                f"| 美国信用风险(BAA {baa10y:.2f}%) | 中国GDP | {credit_on_cn_base:+.2f}ppt | {credit_on_cn_p5:+.2f}ppt | 美债利率↑→EM资本外流→人民币贬压（3M）|"
            )

        # ── 4. 贸易/关税压力渠道（PPI-CPI差代理关税成本传导）───────
        ppi = ind.get("PPIACO", {}).get("value")
        cpi = ind.get("CPIAUCSL", {}).get("value")
        trade_on_cn_base = trade_on_cn_p5 = 0.0
        if ppi is not None and cpi is not None and ppi > cpi + 3:
            # PPI-CPI超额差 > 3ppt = 上游成本未传导终端 → 关税+供应链重组
            # 中国出口商受影响：进口关税+报复关税 → 每1ppt超额 -0.06ppt/季度传导
            ppi_cpi_excess = min(ppi - cpi - 3, 8)
            trade_on_cn_base = -0.06 * ppi_cpi_excess / 4
            trade_on_cn_p5   = trade_on_cn_base * 1.5
            if abs(trade_on_cn_base) > 0.02:
                rows.append(
                    f"| 贸易关税压力(PPI-CPI差{ppi-cpi:.1f}ppt) | 中国出口GDP | {trade_on_cn_base:+.2f}ppt | {trade_on_cn_p5:+.2f}ppt | 供应链重组+关税不确定性（9M）|"
                )

        # ── 5. 综合叠加行（多渠道同向激活时）────────────────────────
        total_cn_base = (gdp_us_on_cn_base + oil_on_cn_base
                         + credit_on_cn_base + trade_on_cn_base)
        total_cn_p5   = (gdp_us_on_cn_p5   + oil_on_cn_p5
                         + credit_on_cn_p5   + trade_on_cn_p5)
        total_us_base = gdp_cn_on_us_base + oil_on_us_base
        total_us_p5   = gdp_cn_on_us_p5   + oil_on_us_p5

        active_extra = sum([
            oil is not None and oil > 80,
            baa10y is not None and baa10y > 1.5,
            ppi is not None and cpi is not None and ppi > cpi + 3,
        ])
        if active_extra >= 1:
            rows.append(
                f"| **综合叠加（{1 + active_extra}渠道）** | **中国GDP净影响** | **{total_cn_base:+.2f}ppt** | **{total_cn_p5:+.2f}ppt** | 各渠道同向叠加 |"
            )
            rows.append(
                f"| **综合叠加（{1 + active_extra}渠道）** | **美国GDP净影响** | **{total_us_base:+.2f}ppt** | **{total_us_p5:+.2f}ppt** | 各渠道同向叠加 |"
            )

        lines = [
            "\n## 跨国传导溢出分析（多渠道矩阵 v2，基准6M滞后）",
            "| 冲击来源 | 目标 | 基准情景影响 | 悲观情景影响 | 主要渠道 |",
            "|:--------|:-----|:----------:|:----------:|:--------|",
        ] + rows

        note = (
            "\n> **渠道说明**：GDP传导（6M，历史回归系数）；"
            "油价渠道（$10/桶基准 → -0.07~0.09ppt，IMF估算）；"
            "信用渠道（BAA10Y超额利差→EM资本外流，3M）；"
            "贸易渠道（PPI-CPI超额差→供应链重组，9M）。"
            "悲观情景：GDP取P5分位，其他渠道×1.2~1.5放大系数。"
            "基准参照：美国2.5% / 中国5.0%。"
        )
        lines.append(note)
        return "\n".join(lines)

    except Exception as e:
        print(f"  [跨国溢出v2] 计算失败: {e}")
        return ""


def _build_both_synopsis(
    us_recession, us_inflation, cn_recession, cn_inflation,
    us_mc, cn_mc, regime, spillover_text, us_indicators,
) -> str:
    """
    中美对比模式：自动生成开篇综合研判摘要（无 LLM 调用）。
    包含：风险评分对比、MC关键概率、萨姆规则、体制状态、溢出摘要。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    us_rec_label, us_rec_score, _ = us_recession
    us_inf_label, us_inf_score, _ = us_inflation
    cn_rec_label, cn_rec_score, _ = cn_recession
    cn_inf_label, cn_inf_score, _ = cn_inflation

    us_rec_prob = f"{us_mc['recession_prob']:.1f}%" if us_mc else "—"
    cn_rec_prob = f"{cn_mc['recession_prob']:.1f}%" if cn_mc else "—"
    us_gdp_med = f"{us_mc['gdp']['mean']:.2f}%" if us_mc else "—"
    cn_gdp_med = f"{cn_mc['gdp']['mean']:.2f}%" if cn_mc else "—"

    sahm_val = us_indicators.get("SAHM_RULE", {}).get("value")
    sahm_str = (f"{sahm_val:.3f} " + ("🔴触发" if sahm_val >= 0.5 else "🟡接近" if sahm_val >= 0.3 else "🟢正常")
                if sahm_val is not None else "—")

    regime_zh = {"normal": "常态", "stress": "压力", "crisis": "危机"}.get(regime, regime)

    lines = [
        f"# 中美宏观综合研判（自动生成 · {now}）\n",
        "## 一、中美风险评分对比",
        "| 维度 | 美国 | 中国 |",
        "|:----|:---:|:---:|",
        f"| 衰退风险 | {us_rec_label}（{us_rec_score}/100）| {cn_rec_label}（{cn_rec_score}/100）|",
        f"| 通胀风险 | {us_inf_label}（{us_inf_score}/100）| {cn_inf_label}（{cn_inf_score}/100）|",
        f"| MC衰退概率 | {us_rec_prob} | {cn_rec_prob} |",
        f"| MC GDP中位 | {us_gdp_med} | {cn_gdp_med} |",
        f"| 体制状态 | {regime_zh} | — |",
        f"| 萨姆规则（美） | {sahm_str} | — |",
    ]

    if spillover_text:
        lines.append("\n## 二、跨国传导溢出摘要")
        lines.append(spillover_text)

    lines.append("\n> 以下为美国、中国独立报告（含各自详细分析）。")
    return "\n".join(lines)


def get_global_context() -> str:
    """
    从 FRED 抓取欧洲、日本、英国、印度的关键宏观指标，组成国际环境文字段落。
    失败时返回空字符串（不阻断主流程）。
    mode: "rate"=直接显示值, "yoy_m"=月频YoY%, "yoy_q"=季频YoY%
    超过 730 天的数据自动跳过（避免过期数据误导 LLM）。
    """
    from datetime import datetime as _dt, timedelta as _td
    _STALE_CUTOFF = (_dt.now() - _td(days=900)).strftime("%Y-%m-%d")

    EU_SERIES = [
        ("IRLTLT01EZM156N",    "欧元区10Y国债收益率", "rate"),
        ("ECBDFR",             "ECB存款利率",          "rate"),
        ("CP0000EZ19M086NEST", "欧元区CPI同比%",       "yoy_m"),
        ("CLVMNACSCAB1GQEA19", "欧元区GDP同比%",       "yoy_q"),
        ("LRHUTTTTEZM156S",    "欧元区失业率",          "rate"),
    ]
    JP_SERIES = [
        ("IRLTLT01JPM156N", "日本10Y国债收益率", "rate"),
        ("FPCPITOTLZGJPN",  "日本CPI同比%",      "rate"),
        ("LRUNTTTTJPM156S", "日本失业率",          "rate"),
    ]
    GB_SERIES = [
        ("IRLTLT01GBM156N", "英国10Y国债收益率", "rate"),
        ("CPALTT01GBM659N", "英国CPI同比%",      "rate"),
        ("LRHUTTTTGBM156S", "英国失业率",          "rate"),
    ]
    IN_SERIES = [
        ("INDCPIALLMINMEI", "印度CPI指数", "yoy_m"),
    ]

    lines = []
    _detect_fred_proxy()

    def _safe_fetch(sid, mode):
        try:
            if mode == "yoy_m":
                d, v, yoy = get_fred_with_yoy(sid, n_lags=12)
                if d and d >= _STALE_CUTOFF:
                    return d, yoy if yoy is not None else v
            elif mode == "yoy_q":
                d, v, yoy = get_fred_with_yoy(sid, n_lags=4)
                if d and d >= _STALE_CUTOFF:
                    return d, yoy if yoy is not None else v
            else:
                d, v = get_fred_latest(sid)
                if d and d >= _STALE_CUTOFF and v is not None:
                    return d, v
        except Exception:
            pass
        return None, None

    def _build_section(series_list):
        data = {}
        for sid, name, mode in series_list:
            d, v = _safe_fetch(sid, mode)
            if v is not None:
                data[name] = f"{v:.2f}（{d}）"
        return data

    eu_data = _build_section(EU_SERIES)
    jp_data = _build_section(JP_SERIES)
    gb_data = _build_section(GB_SERIES)
    in_data = _build_section(IN_SERIES)

    if eu_data:
        lines.append("**欧元区**：" + "，".join(f"{k} {v}" for k, v in eu_data.items()))
    if jp_data:
        lines.append("**日本**：" + "，".join(f"{k} {v}" for k, v in jp_data.items()))
    if gb_data:
        lines.append("**英国**：" + "，".join(f"{k} {v}" for k, v in gb_data.items()))
    if in_data:
        lines.append("**印度**：" + "，".join(f"{k} {v}" for k, v in in_data.items()))

    return "\n".join(lines) if lines else ""





def compute_lei_composite(indicators: dict) -> str:
    """
    合成领先经济指标（LEI Composite）评分。
    基于 Conference Board LEI 方法论，从10个子指标加权合成前瞻衰退信号。
    返回 Markdown 字符串，供注入 LLM 提示词。
    """
    def _v(key, default=None):
        val = indicators.get(key, {}).get("value", default)
        return val if val is not None else default

    scores = []
    details = []

    # 1. 10Y-2Y 利差（权重：15%）— 正常>0.5%, 警告-0.5%~0.5%, 衰退<-0.5%
    t10y2y = _v("T10Y2Y", 0.5)
    if t10y2y > 1.0:
        s1, l1 = 100, f"利差+{t10y2y:.2f}% 曲线正斜率"
    elif t10y2y > 0:
        s1, l1 = 60, f"利差+{t10y2y:.2f}% 中性"
    elif t10y2y > -0.5:
        s1, l1 = 30, f"利差{t10y2y:.2f}% 轻度倒挂"
    else:
        s1, l1 = 0, f"利差{t10y2y:.2f}% 深度倒挂 ⚠"
    scores.append((s1, 0.15))
    details.append(f"收益率曲线 {s1}/100: {l1}")

    # 2. 初请失业金（权重：15%）— <200k 强劲, 200-250k 正常, >350k 衰退
    icsa = _v("ICSA", 220000) / 1000  # 转换为千人
    if icsa < 200:
        s2, l2 = 100, f"初请{icsa:.0f}k 就业强劲"
    elif icsa < 250:
        s2, l2 = 70, f"初请{icsa:.0f}k 正常"
    elif icsa < 350:
        s2, l2 = 40, f"初请{icsa:.0f}k 偏弱 ⚠"
    else:
        s2, l2 = 0, f"初请{icsa:.0f}k 急剧恶化 🔴"
    scores.append((s2, 0.15))
    details.append(f"初请失业金 {s2}/100: {l2}")

    # 3. 职位空缺/失业比（权重：12%）— 空缺数/失业人数，>1.2正常, <0.8警告
    jolts = _v("JTSJOL", 7000)  # 职位空缺（千）
    unrate = _v("UNRATE", 4.3)
    labor_force_approx = 165000  # 美国劳动力约1.65亿
    unemployed_est = unrate / 100 * labor_force_approx / 1000  # 千人
    if unemployed_est > 0:
        jtu_ratio = jolts / unemployed_est
        if jtu_ratio > 1.5:
            s3, l3 = 100, f"岗位空缺/失业比{jtu_ratio:.2f}，劳动力极度稀缺"
        elif jtu_ratio > 1.0:
            s3, l3 = 75, f"岗位空缺/失业比{jtu_ratio:.2f}，供需均衡偏紧"
        elif jtu_ratio > 0.7:
            s3, l3 = 40, f"岗位空缺/失业比{jtu_ratio:.2f}，就业市场降温 ⚠"
        else:
            s3, l3 = 10, f"岗位空缺/失业比{jtu_ratio:.2f}，供大于求 🔴"
    else:
        s3, l3 = 50, "职位空缺比率不可用"
    scores.append((s3, 0.12))
    details.append(f"职位/失业比 {s3}/100: {l3}")

    # 4. 消费者信心（权重：10%）— Michigan CSI，>80正常, 50-80警告, <50衰退前兆
    umcsent = _v("UMCSENT", 65.0)
    if umcsent > 90:
        s4, l4 = 100, f"消费信心{umcsent:.0f}，乐观"
    elif umcsent > 70:
        s4, l4 = 75, f"消费信心{umcsent:.0f}，正常"
    elif umcsent > 55:
        s4, l4 = 40, f"消费信心{umcsent:.0f}，悲观 ⚠"
    else:
        s4, l4 = 10, f"消费信心{umcsent:.0f}，深度悲观 🔴"
    scores.append((s4, 0.10))
    details.append(f"消费者信心 {s4}/100: {l4}")

    # 5. 工业产出（权重：10%）— INDPRO同比（代理用绝对值，>100扩张）
    indpro = _v("INDPRO", 100.0)
    if indpro > 105:
        s5, l5 = 100, f"工业产出指数{indpro:.1f}，强劲扩张"
    elif indpro > 100:
        s5, l5 = 70, f"工业产出指数{indpro:.1f}，温和扩张"
    elif indpro > 97:
        s5, l5 = 35, f"工业产出指数{indpro:.1f}，轻度收缩 ⚠"
    else:
        s5, l5 = 5, f"工业产出指数{indpro:.1f}，显著收缩 🔴"
    scores.append((s5, 0.10))
    details.append(f"工业产出 {s5}/100: {l5}")

    # 6. 信用利差（权重：10%）— BAA10Y，<1.5%宽松, >3.5%收紧, >5%危机
    baa10y = _v("BAA10Y", 2.0)
    if baa10y < 1.5:
        s6, l6 = 100, f"BAA利差{baa10y:.2f}%，信用极度宽松"
    elif baa10y < 2.5:
        s6, l6 = 75, f"BAA利差{baa10y:.2f}%，信用正常"
    elif baa10y < 3.5:
        s6, l6 = 40, f"BAA利差{baa10y:.2f}%，信用偏紧 ⚠"
    else:
        s6, l6 = 5, f"BAA利差{baa10y:.2f}%，信用市场压力 🔴"
    scores.append((s6, 0.10))
    details.append(f"信用利差 {s6}/100: {l6}")

    # 7. 萨姆规则（权重：12%）— 0→100映射到0.5~0
    sahm = _v("SAHM_RULE", 0.0)
    if sahm < 0.1:
        s7, l7 = 100, f"萨姆{sahm:.2f}，衰退风险极低"
    elif sahm < 0.3:
        s7, l7 = 60, f"萨姆{sahm:.2f}，正常范围"
    elif sahm < 0.5:
        s7, l7 = 20, f"萨姆{sahm:.2f}，接近衰退阈值 ⚠"
    else:
        s7, l7 = 0, f"萨姆{sahm:.2f} ≥0.5，衰退触发 🔴"
    scores.append((s7, 0.12))
    details.append(f"萨姆规则 {s7}/100: {l7}")

    # 8. 新屋开工（权重：8%）— >1400k正常, <1000k弱
    houst = _v("HOUST", 1400.0)
    if houst > 1600:
        s8, l8 = 100, f"新屋开工{houst:.0f}k，建筑旺盛"
    elif houst > 1300:
        s8, l8 = 70, f"新屋开工{houst:.0f}k，正常"
    elif houst > 1000:
        s8, l8 = 35, f"新屋开工{houst:.0f}k，放缓 ⚠"
    else:
        s8, l8 = 5, f"新屋开工{houst:.0f}k，低迷 🔴"
    scores.append((s8, 0.08))
    details.append(f"新屋开工 {s8}/100: {l8}")

    # 9. 高收益债利差（权重：8%）— BAMLH0A0HYM2（百分点）
    hy_spread = _v("BAMLH0A0HYM2", 4.0)
    if hy_spread < 3.0:
        s9, l9 = 100, f"高收益利差{hy_spread:.2f}%，信用市场极宽松"
    elif hy_spread < 4.5:
        s9, l9 = 70, f"高收益利差{hy_spread:.2f}%，正常"
    elif hy_spread < 7.0:
        s9, l9 = 35, f"高收益利差{hy_spread:.2f}%，信用收紧 ⚠"
    else:
        s9, l9 = 5, f"高收益利差{hy_spread:.2f}%，信用危机风险 🔴"
    scores.append((s9, 0.08))
    details.append(f"高收益利差 {s9}/100: {l9}")

    # 10. 房贷利率（权重：0%/参考）— MORTGAGE30US，作为信息展示不计入得分
    mortgage = _v("MORTGAGE30US", 7.0)
    if mortgage is not None and mortgage > 0:
        if mortgage < 5.0:
            m_note = f"房贷{mortgage:.2f}%，历史低位"
        elif mortgage < 7.0:
            m_note = f"房贷{mortgage:.2f}%，正常偏高"
        else:
            m_note = f"房贷{mortgage:.2f}%，高位抑制住房 ⚠"
        details.append(f"房贷利率 —/100: {m_note}")

    # 11. 实际利率（参考）— DFII10（10Y TIPS实际收益率）
    real_rate = _v("DFII10")
    ffr_val = _v("DFF") or _v("FEDFUNDS")
    cpi_val = _v("CPIAUCSL", 3.0)
    if real_rate is not None:
        # DFII10是市场定价的实际利率
        if real_rate > 2.5:
            rr_note = f"10Y实际利率{real_rate:.2f}%，紧缩偏强（历史高位）⚠"
        elif real_rate > 1.0:
            rr_note = f"10Y实际利率{real_rate:.2f}%，温和正利率"
        elif real_rate > 0:
            rr_note = f"10Y实际利率{real_rate:.2f}%，接近中性"
        else:
            rr_note = f"10Y实际利率{real_rate:.2f}%，负实际利率（刺激性）"
        details.append(f"10Y实际利率 —/100: {rr_note}")
    elif ffr_val and cpi_val:
        implied_real = round(ffr_val - cpi_val, 2)
        note = "负实际利率（刺激性）" if implied_real < 0 else "正实际利率"
        details.append(f"名义实际利率 —/100: FFR{ffr_val:.2f}%-CPI{cpi_val:.2f}%={implied_real:+.2f}ppt ({note})")

    # ── 加权合成 ──────────────────────────────────────────────
    total_weight = sum(w for _, w in scores)
    composite = sum(s * w for s, w in scores) / total_weight if total_weight > 0 else 50

    if composite >= 75:
        signal = "🟢 扩张强劲"
        horizon = "未来6个月衰退概率极低（<5%）"
    elif composite >= 55:
        signal = "🟡 温和扩张"
        horizon = "未来6个月衰退概率低（5-15%），需监控下行风险"
    elif composite >= 35:
        signal = "🟠 增长放缓"
        horizon = "未来6个月衰退概率中等（15-35%），警戒状态"
    else:
        signal = "🔴 衰退风险"
        horizon = "未来6个月衰退概率高（>35%），建议防御"

    lines = [
        f"\n## 领先经济指标合成评分（LEI Composite）",
        f"**综合得分：{composite:.0f}/100 | {signal}**",
        f"> {horizon}",
        "",
        "| 指标 | 得分 | 说明 |",
        "|:----|:---:|:----|",
    ]
    for d in details:
        parts = d.split(": ", 1)
        name_score = parts[0]
        desc = parts[1] if len(parts) > 1 else ""
        name_parts = name_score.rsplit(" ", 1)
        name = name_parts[0]
        score_str = name_parts[1] if len(name_parts) > 1 else ""
        lines.append(f"| {name} | {score_str} | {desc} |")

    return "\n".join(lines)


def compute_lei_composite_china(indicators: dict) -> str:
    """
    中国领先经济指标合成评分（China LEI Composite）。
    基于7个子指标加权合成，信号方向与US LEI对齐（越高越好）。
    返回 Markdown 字符串，供注入 LLM 提示词。
    """
    def _v(key, default=None):
        val = indicators.get(key, {}).get("value", default)
        return val if val is not None else default

    scores = []
    details = []

    # 1. 制造业PMI（权重 20%）— 扩张/收缩最直接信号
    pmi_mfg = _v("pmi_mfg", 50.0)
    if pmi_mfg > 52:
        s1, l1 = 100, f"制造业PMI {pmi_mfg:.1f}，扩张强劲"
    elif pmi_mfg > 50:
        s1, l1 = 70, f"制造业PMI {pmi_mfg:.1f}，温和扩张"
    elif pmi_mfg > 49:
        s1, l1 = 35, f"制造业PMI {pmi_mfg:.1f}，轻度收缩 ⚠"
    else:
        s1, l1 = 5, f"制造业PMI {pmi_mfg:.1f}，深度收缩 🔴"
    scores.append((s1, 0.20))
    details.append(f"制造业PMI {s1}/100: {l1}")

    # 2. 综合PMI（权重 12%）— 制造+服务业综合
    pmi_comp = _v("pmi_composite", 51.0)
    if pmi_comp > 53:
        s2, l2 = 100, f"综合PMI {pmi_comp:.1f}，全面扩张"
    elif pmi_comp > 51:
        s2, l2 = 72, f"综合PMI {pmi_comp:.1f}，温和扩张"
    elif pmi_comp > 50:
        s2, l2 = 45, f"综合PMI {pmi_comp:.1f}，勉强扩张"
    else:
        s2, l2 = 10, f"综合PMI {pmi_comp:.1f}，综合收缩 ⚠"
    scores.append((s2, 0.12))
    details.append(f"综合PMI {s2}/100: {l2}")

    # 3. 工业增加值增速（权重 15%）— 实体经济领先信号
    iva = _v("industrial_va", 5.0)
    if iva > 7:
        s3, l3 = 100, f"工业增加值 {iva:.1f}%，增长强劲"
    elif iva > 5:
        s3, l3 = 70, f"工业增加值 {iva:.1f}%，增长正常"
    elif iva > 3:
        s3, l3 = 40, f"工业增加值 {iva:.1f}%，增长偏弱 ⚠"
    else:
        s3, l3 = 5, f"工业增加值 {iva:.1f}%，增长低迷 🔴"
    scores.append((s3, 0.15))
    details.append(f"工业增加值 {s3}/100: {l3}")

    # 4. M2同比（权重 13%）— 货币/信贷先行指标
    m2 = _v("m2_growth", 9.0)
    if m2 > 11:
        s4, l4 = 90, f"M2增速 {m2:.1f}%，货币宽松充裕"
    elif m2 > 8.5:
        s4, l4 = 70, f"M2增速 {m2:.1f}%，正常"
    elif m2 > 6:
        s4, l4 = 35, f"M2增速 {m2:.1f}%，流动性偏紧 ⚠"
    else:
        s4, l4 = 5, f"M2增速 {m2:.1f}%，信贷收缩预警 🔴"
    scores.append((s4, 0.13))
    details.append(f"M2增速 {s4}/100: {l4}")

    # 5. GDP增速相对目标（权重 15%）— 实现"5%左右"目标的进度
    gdp = _v("gdp_growth", 5.0)
    if gdp >= 5.5:
        s5, l5 = 100, f"GDP {gdp:.1f}%，超出目标"
    elif gdp >= 4.8:
        s5, l5 = 75, f"GDP {gdp:.1f}%，基本达目标"
    elif gdp >= 4.0:
        s5, l5 = 40, f"GDP {gdp:.1f}%，低于目标 ⚠"
    else:
        s5, l5 = 5, f"GDP {gdp:.1f}%，显著低于目标 🔴"
    scores.append((s5, 0.15))
    details.append(f"GDP增速 {s5}/100: {l5}")

    # 6. CPI（权重 10%）— 价格稳定信号（1-3%为健康区间）
    cpi = _v("cpi", 1.5)
    if 1.5 <= cpi <= 3.0:
        s6, l6 = 100, f"CPI {cpi:.1f}%，价格稳定健康"
    elif 0.5 <= cpi < 1.5:
        s6, l6 = 55, f"CPI {cpi:.1f}%，通缩压力温和"
    elif cpi > 3.0:
        s6, l6 = 40, f"CPI {cpi:.1f}%，通胀偏高 ⚠"
    elif cpi < 0:
        s6, l6 = 5, f"CPI {cpi:.1f}%，通缩已现 🔴"
    else:
        s6, l6 = 30, f"CPI {cpi:.1f}%，接近通缩区间"
    scores.append((s6, 0.10))
    details.append(f"CPI价格 {s6}/100: {l6}")

    # 7. PPI（权重 15%）— 上游价格/出口竞争力先行指标
    ppi = _v("ppi", 0.0)
    if 0 <= ppi <= 3:
        s7, l7 = 100, f"PPI {ppi:.1f}%，成本正常"
    elif ppi > 3:
        s7, l7 = 50, f"PPI {ppi:.1f}%，上游成本偏高 ⚠"
    elif ppi > -2:
        s7, l7 = 40, f"PPI {ppi:.1f}%，轻度通缩"
    else:
        s7, l7 = 5, f"PPI {ppi:.1f}%，深度通缩—企业利润受压 🔴"
    scores.append((s7, 0.15))
    details.append(f"PPI上游 {s7}/100: {l7}")

    # ── 加权合成 ──────────────────────────────────────────────
    total_weight = sum(w for _, w in scores)
    composite = sum(s * w for s, w in scores) / total_weight if total_weight > 0 else 50

    if composite >= 75:
        signal = "🟢 扩张强劲"
        horizon = "经济运行健康，未来6个月增速放缓概率低（<10%）"
    elif composite >= 55:
        signal = "🟡 温和扩张"
        horizon = "增长温和，政策宽松空间充足，需关注通缩/PMI拐点"
    elif composite >= 35:
        signal = "🟠 增长放缓"
        horizon = "增长动力减弱，面临通缩或需求不足压力，政策刺激预期增强"
    else:
        signal = "🔴 下行风险"
        horizon = "多项指标同步走弱，政策托底力度需显著加强"

    lines = [
        f"\n## 中国领先指标合成评分（China LEI）",
        f"**综合得分：{composite:.0f}/100 | {signal}**",
        f"> {horizon}",
        "",
        "| 指标 | 得分 | 说明 |",
        "|:----|:---:|:----|",
    ]
    for d in details:
        parts = d.split(": ", 1)
        name_score = parts[0]
        desc = parts[1] if len(parts) > 1 else ""
        name_parts = name_score.rsplit(" ", 1)
        name = name_parts[0]
        score_str = name_parts[1] if len(name_parts) > 1 else ""
        lines.append(f"| {name} | {score_str} | {desc} |")

    return "\n".join(lines)


def evaluate_feedback_loops_china(indicators: dict) -> str:
    """
    中国经济反馈回路评估（C1-C6）。
    不同于美国版（F1-F6），中国面临以下特有回路：
    C1: 房地产-信贷螺旋（负面最大风险）
    C2: 出口-汇率-PMI 传导链
    C3: 地方政府融资平台（城投债）压力
    C4: 通缩-利润-投资负螺旋
    C5: 美联储-中美利差-资本外流
    C6: 货币政策-信贷扩张效率

    返回 Markdown 表格。
    """
    def _v(key, default=None):
        val = indicators.get(key, {}).get("value", default)
        return val if val is not None else default

    gdp = _v("gdp_growth", 5.0)
    cpi = _v("cpi", 1.5)
    ppi = _v("ppi", 0.0)
    pmi = _v("pmi_mfg", 50.0)
    m2  = _v("m2_growth", 9.0)
    rows = []

    # ── C1: 房地产-信贷螺旋 ─────────────────────────────────────────────
    # 代理：GDP低于4.5% + PPI通缩 → 地产下行拖累信贷
    if gdp is not None and gdp < 4.0 and ppi is not None and ppi < -1:
        c1_status = "🔴 激活风险（负螺旋）"
        c1_note = f"GDP {gdp:.1f}%低位 + PPI {ppi:.1f}%通缩，房地产-信贷双压"
    elif gdp is not None and gdp < 4.5:
        c1_status = "🟡 潜在压力"
        c1_note = f"GDP {gdp:.1f}%接近政策底线，地产传导风险"
    else:
        c1_status = "🟢 休眠"
        c1_note = f"GDP {gdp:.1f}%，信贷压力可控"
    rows.append(("C1 房地产-信贷螺旋", c1_status, c1_note))

    # ── C2: 出口-PMI传导 ─────────────────────────────────────────────────
    # 制造业PMI < 50 反映出口需求可能回落
    if pmi is not None and pmi < 49:
        c2_status = "🟡 收缩信号"
        c2_note = f"PMI {pmi:.1f}<49，制造订单萎缩，出口可能承压"
    elif pmi is not None and pmi > 52:
        c2_status = "🟢 扩张"
        c2_note = f"PMI {pmi:.1f}>52，出口制造动能充足"
    else:
        c2_status = "🟢 中性"
        c2_note = f"PMI {pmi:.1f}，需求温和"
    rows.append(("C2 出口-制造-PMI链", c2_status, c2_note))

    # ── C3: 地方融资平台压力 ─────────────────────────────────────────────
    # 代理：M2增速 < 8% → 流动性偏紧 → 城投再融资压力
    if m2 is not None and m2 < 7:
        c3_status = "🔴 高压（城投风险）"
        c3_note = f"M2 {m2:.1f}%，城投再融资利率压力"
    elif m2 is not None and m2 < 9:
        c3_status = "🟡 温和"
        c3_note = f"M2 {m2:.1f}%，流动性偏紧"
    else:
        c3_status = "🟢 充裕"
        c3_note = f"M2 {m2:.1f}%，政府债流动性充裕"
    rows.append(("C3 地方融资平台", c3_status, c3_note))

    # ── C4: 通缩-利润-投资负螺旋 ─────────────────────────────────────────
    if ppi is not None and ppi < -2:
        c4_status = "🔴 激活（通缩螺旋）"
        c4_note = f"PPI {ppi:.1f}%，企业利润受压→投资意愿下降"
    elif ppi is not None and cpi is not None and ppi < 0 and cpi < 1:
        c4_status = "🟡 早期信号"
        c4_note = f"PPI {ppi:.1f}% + CPI {cpi:.1f}%，通缩压力积累"
    elif cpi is not None and cpi > 0:
        c4_status = "🟢 休眠"
        c4_note = f"CPI {cpi:.1f}%，通缩螺旋风险低"
    else:
        c4_status = "⚪ 数据不足"
        c4_note = "—"
    rows.append(("C4 通缩-利润-投资螺旋", c4_status, c4_note))

    # ── C5: 中美利差-资本外流 ─────────────────────────────────────────────
    # 注：中国10Y约1.65%（2026-05 PBOC宽松背景），美国10Y约4.39%；利差倒挂（美>中）不利于人民币
    cn_10y_approx = 1.65  # 近似值（无实时数据）；2026-05 据PBOC宽松+低通胀背景更新
    us_10y = indicators.get("DGS10", {}).get("value")
    if us_10y is not None:
        spread = cn_10y_approx - us_10y
        if spread < -2:
            c5_status = "🔴 资本外流压力"
            c5_note = f"中美利差约{spread:.2f}ppt（中国低于美国），汇率承压"
        elif spread < -1:
            c5_status = "🟡 利差倒挂"
            c5_note = f"中美利差约{spread:.2f}ppt，外资回报压力"
        else:
            c5_status = "🟢 利差正常"
            c5_note = f"中美利差约{spread:.2f}ppt"
    else:
        c5_status = "⚪ 数据不足"
        c5_note = "—"
    rows.append(("C5 中美利差-资本流动", c5_status, c5_note))

    # ── C6: 货币政策信贷效率 + 泰勒规则偏差 ─────────────────────────────────
    # 宽货币但信贷未扩张 → 货币政策传导受阻（"推绳子"困境）
    # 中国泰勒规则代理: i_taylor = 2.5%(中性) + 1.5*(CPI-2%) + 0.5*(GDP_gap)
    # 假设潜在GDP约5%；LPR1Y优先从实时 indicators 读取（HYP-7），fallback 3.10
    cn_lpr_approx = (indicators.get("cn_lpr") or {}).get("value") or 3.10
    if cpi is not None and gdp is not None:
        gdp_gap = gdp - 5.0  # 相对于5%潜在增速的缺口
        cn_taylor_rate = 2.5 + 1.5 * (cpi - 2.0) + 0.5 * gdp_gap
        gap = cn_lpr_approx - cn_taylor_rate
        if gap > 1.0:
            c6_status = "🟡 偏紧（高于泰勒规则）"
            c6_note = f"LPR~{cn_lpr_approx:.1f}% > 泰勒{cn_taylor_rate:.1f}%（+{gap:.1f}ppt），仍有降息空间"
        elif gap < -1.0:
            c6_status = "🟡 偏松（低于泰勒规则）"
            c6_note = f"LPR~{cn_lpr_approx:.1f}% < 泰勒{cn_taylor_rate:.1f}%（{gap:.1f}ppt），货币偏宽"
        else:
            c6_status = "🟢 基本中性"
            c6_note = f"LPR~{cn_lpr_approx:.1f}%，泰勒规则{cn_taylor_rate:.1f}%，偏差{gap:+.1f}ppt"
        # 叠加推绳子检查
        if m2 is not None and m2 > 10 and pmi is not None and pmi < 50:
            c6_status = "🟡 宽货币效率不足"
            c6_note += f"；M2 {m2:.1f}%但PMI {pmi:.1f}<50，传导受阻"
    elif m2 is not None and m2 > 10 and pmi is not None and pmi < 50:
        c6_status = "🟡 传导受阻（推绳子）"
        c6_note = f"M2 {m2:.1f}%但PMI {pmi:.1f}<50，宽货币未能刺激需求"
    elif m2 is not None and m2 > 9:
        c6_status = "🟢 正常传导"
        c6_note = f"M2 {m2:.1f}%，货币政策有效"
    else:
        c6_status = "⚪ 偏紧"
        c6_note = f"M2 {m2:.1f}% 偏低，货币供应不足"
    rows.append(("C6 货币政策传导效率", c6_status, c6_note))

    # ── 合并输出 ──────────────────────────────────────────────────────────
    lines = [
        "\n## 中国经济反馈回路（C1-C6）",
        "| 回路 | 当前状态 | 关键指标 |",
        "|:----|:--------|:--------|",
    ]
    for name, status, note in rows:
        lines.append(f"| {name} | {status} | {note} |")

    active = [r[0] for r in rows if "激活" in r[1] or "高压" in r[1]]
    if active:
        lines.append(f"\n> **当前活跃风险回路**：{', '.join(active)}。需重点关注传导路径与政策对冲。")
    else:
        lines.append("\n> 各回路目前均无明显激活信号，经济整体平稳但通缩压力需持续跟踪。")

    return "\n".join(lines)


def evaluate_feedback_loops_status(indicators: dict) -> str:
    """
    根据当前指标评估 F1-F6 反馈回路激活状态。
    参数来源：知识库/05_反馈回路参数/反馈回路F1-F6量化参数.md

    返回 Markdown 表格，注入 LLM 提示词。
    """
    def _v(key, default=None):
        val = indicators.get(key, {}).get("value", default)
        return val if val is not None else default

    # 提取常用指标
    cpi   = _v("CPIAUCSL", 3.0)    # CPI同比%
    ppi   = _v("PPIACO", 0.0)      # PPI同比%
    unrate = _v("UNRATE", 4.3)     # 失业率%
    gdp   = _v("GDPC1", 2.5)       # GDP同比%
    ffr   = _v("DFF") or _v("FEDFUNDS", 4.5)  # 联邦基金利率%
    t10y2y = _v("T10Y2Y", 0.0)     # 10Y-2Y利差%
    vix   = _v("VIXCLS", 18.0)     # VIX
    baa_spread = _v("BAMLH0A0HYM2", 3.5)  # 高收益利差%
    oil   = _v("DCOILWTICO", 80.0) # WTI原油 $/桶
    delinquency = _v("DRCCLACBS")  # 信用卡违约率%（可能None）

    rows = []

    # ── F1: 信贷-增长螺旋 ─────────────────────────────────────────────────
    # 正螺旋（泡沫）: GDP>3% 且 信贷条件宽松（利差<2.5%）
    # 负螺旋（衰退）: GDP<0 或 违约率>5%（如有数据）
    f1_neg = (gdp is not None and gdp < 0) or (delinquency is not None and delinquency > 5.0)
    f1_pos = (gdp is not None and gdp > 3.5) and (baa_spread is not None and baa_spread < 2.5)
    if f1_neg:
        f1_status = "🔴 激活（负螺旋）"
        f1_note = f"GDP {gdp:.1f}%，信贷可能收缩"
    elif f1_pos:
        f1_status = "🟡 激活（正泡沫）"
        f1_note = f"GDP {gdp:.1f}%，利差{baa_spread:.1f}%偏低"
    else:
        f1_status = "🟢 潜伏/休眠"
        f1_note = f"GDP {gdp:.1f}%，利差{baa_spread:.1f}%"
    rows.append(("F1 信贷-增长螺旋", f1_status, f1_note))

    # ── F2: 通胀-工资螺旋 ─────────────────────────────────────────────────
    # 知识库：自持条件=工资实际增速>3%连续6个月；代理：CPI>4% + UNRATE<4%
    f2_active = (cpi is not None and cpi > 4.0) and (unrate is not None and unrate < 4.0)
    f2_latent = (cpi is not None and cpi > 3.0) and (unrate is not None and unrate < 4.5)
    if f2_active:
        f2_status = "🔴 高风险激活"
        f2_note = f"CPI {cpi:.1f}%，失业率{unrate:.1f}%→工资压力大"
    elif f2_latent:
        f2_status = "🟡 潜在（劳动市场偏紧）"
        f2_note = f"CPI {cpi:.1f}%，失业率{unrate:.1f}%"
    else:
        f2_status = "🟢 休眠"
        f2_note = f"CPI {cpi:.1f}%，失业率{unrate:.1f}%"
    rows.append(("F2 通胀-工资螺旋", f2_status, f2_note))

    # ── F3: 资产价格-财富效应 ──────────────────────────────────────────────
    # 正回路（繁荣）: VIX<15；负回路（崩盘）: VIX>35
    if vix is not None and vix > 35:
        f3_status = "🔴 负向激活（风险崩盘）"
        f3_note = f"VIX {vix:.1f}，财富缩水加速"
    elif vix is not None and vix < 15:
        f3_status = "🟡 正向激活（泡沫风险）"
        f3_note = f"VIX {vix:.1f}，过度乐观"
    else:
        f3_status = "🟢 中性"
        f3_note = f"VIX {vix:.1f}"
    rows.append(("F3 资产价格-财富效应", f3_status, f3_note))

    # ── F4: 货币政策-泰勒规则 ─────────────────────────────────────────────
    # 泰勒规则: i* = 2.5 + 2.0 + 1.5*(CPI-2.0) + 0.5*(4.5-UNRATE)*(-1)
    # 简化：过度紧缩/过度宽松
    if ffr is not None and cpi is not None and unrate is not None:
        output_gap = (unrate - 4.5) * (-1)  # 奥肯定律：失业率偏高→负产出缺口
        taylor_rate = 2.5 + 2.0 + 1.5 * (cpi - 2.0) + 0.5 * output_gap
        gap = ffr - taylor_rate
        if abs(gap) < 0.5:
            f4_status = "🟢 正常（与泰勒规则吻合）"
            f4_note = f"实际{ffr:.1f}% vs 泰勒{taylor_rate:.1f}%（偏差{gap:+.1f}ppt）"
        elif gap > 0.5:
            f4_status = "🟡 偏紧缩（抑制需求）"
            f4_note = f"实际{ffr:.1f}% > 泰勒{taylor_rate:.1f}%（+{gap:.1f}ppt）"
        else:
            f4_status = "🟡 偏宽松（通胀风险）"
            f4_note = f"实际{ffr:.1f}% < 泰勒{taylor_rate:.1f}%（{gap:.1f}ppt）"
    else:
        f4_status = "⚪ 数据不足"
        f4_note = "—"
    rows.append(("F4 货币政策-泰勒规则", f4_status, f4_note))

    # ── F5: 汇率-经常账户 ────────────────────────────────────────────────
    # 我们暂无汇率和贸易数据，用利差逻辑代理：利差倒挂→资本外流→汇率压力
    if t10y2y is not None and t10y2y < -0.5:
        f5_status = "🟡 利差倒挂→资本流动压力"
        f5_note = f"10Y-2Y {t10y2y:.2f}%，历史上预示衰退与汇率波动"
    elif t10y2y is not None and t10y2y > 1.5:
        f5_status = "🟢 正常斜率，资金流稳定"
        f5_note = f"10Y-2Y {t10y2y:.2f}%"
    else:
        f5_status = "🟢 中性"
        f5_note = f"10Y-2Y {t10y2y:.2f}%" if t10y2y is not None else "数据缺失"
    rows.append(("F5 汇率-经常账户", f5_status, f5_note))

    # ── F6: 流动性陷阱-财政替代 ──────────────────────────────────────────
    # ZLB激活条件：政策利率<0.5%
    if ffr is not None and ffr < 0.5:
        f6_status = "🔴 ZLB激活，货币政策失效"
        f6_note = f"FFR {ffr:.2f}%，需要财政政策主导"
    elif ffr is not None and ffr < 1.5:
        f6_status = "🟡 逼近ZLB（宽松空间有限）"
        f6_note = f"FFR {ffr:.2f}%"
    else:
        f6_status = "🟢 政策空间充足"
        f6_note = f"FFR {ffr:.2f}%，降息空间{ffr-0.25:.2f}ppt"
    rows.append(("F6 流动性陷阱-财政替代", f6_status, f6_note))

    # ── F7: 油价滞胀循环 ────────────────────────────────────────────────────
    # 当前情景：WTI>100 + CPI>3% → 供给推通胀持续 → 联储无法降息 → 需求压制
    dgs10 = _v("DGS10", 4.0)
    if oil is not None and oil > 100 and cpi is not None and cpi > 3:
        f7_status = "🔴 激活（油价-通胀双压）"
        f7_note = f"WTI {oil:.0f}$/桶，CPI {cpi:.1f}%，降息空间受限"
    elif oil is not None and oil > 85 and cpi is not None and cpi > 2.5:
        f7_status = "🟡 潜在（油价偏高+通胀粘性）"
        f7_note = f"WTI {oil:.0f}$，CPI {cpi:.1f}%"
    else:
        f7_status = "🟢 休眠"
        f7_note = f"WTI {oil:.0f}$，CPI {cpi:.1f}%" if oil is not None else "—"
    rows.append(("F7 油价-滞胀循环", f7_status, f7_note))

    # ── F8: 财政利率螺旋 ────────────────────────────────────────────────────
    # 穆迪警告（2026-05-18）：高债务 → 信用溢价 → 利息支出↑ → 赤字扩大循环
    baa10y_raw = _v("BAA10Y", 1.5)
    if dgs10 is not None and dgs10 > 4.8 and baa10y_raw is not None and baa10y_raw > 1.8:
        f8_status = "🔴 激活（财政-信用压力叠加）"
        f8_note = f"10Y {dgs10:.2f}%，BAA利差{baa10y_raw:.2f}%→利息支出螺旋"
    elif dgs10 is not None and dgs10 > 4.5 and baa10y_raw is not None and baa10y_raw > 1.5:
        f8_status = "🟡 潜在（穆迪警告已发出）"
        f8_note = f"10Y {dgs10:.2f}%，BAA {baa10y_raw:.2f}%，3-5年内评级风险"
    else:
        f8_status = "🟢 休眠"
        f8_note = f"10Y {dgs10:.2f}%，债务可持续性暂稳" if dgs10 is not None else "—"
    rows.append(("F8 财政-利率螺旋", f8_status, f8_note))

    # ── 合并输出 ──────────────────────────────────────────────────────────
    lines = [
        "\n## 反馈回路激活状态（F1-F8）",
        "| 回路 | 当前状态 | 关键指标 |",
        "|:----|:--------|:--------|",
    ]
    for name, status, note in rows:
        lines.append(f"| {name} | {status} | {note} |")

    # ── 主导回路提示（含萨姆规则）─────────────────────────────────────────────
    active = [r[0] for r in rows if "激活" in r[1] or "高风险" in r[1]]
    sahm_note = ""
    sahm_val = indicators.get("SAHM_RULE", {}).get("value")
    if sahm_val is not None:
        sahm_note = f"  萨姆规则：{sahm_val:.3f}（{'🔴≥0.5触发' if sahm_val >= 0.5 else '🟡≥0.3接近' if sahm_val >= 0.3 else '🟢正常'}）"
    if active:
        lines.append(f"\n> **当前主导回路**：{', '.join(active)}。分析时需特别关注其放大效应与破解路径。")
    else:
        lines.append("\n> 当前各回路均处于休眠/潜伏状态，宏观系统相对稳定。")
    if sahm_note:
        lines.append(f">{sahm_note}")

    return "\n".join(lines)



def _cleanup_error_log(max_days: int = 30):
    """清理超过 max_days 天的错误日志条目。"""
    log_file = Path(LOG_DIR) / "analysis_errors.log"
    if not log_file.exists():
        return
    try:
        text = log_file.read_text(encoding="utf-8", errors="ignore")
        # 按分隔符切分条目
        entries = text.split("\n" + "=" * 60)
        cutoff = datetime.now().timestamp() - max_days * 86400
        kept = []
        for entry in entries:
            if not entry.strip():
                continue
            # 尝试解析时间戳 [YYYY-MM-DD HH:MM:SS]
            import re
            m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', entry)
            if m:
                try:
                    ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
                    if ts >= cutoff:
                        kept.append(entry)
                except ValueError:
                    kept.append(entry)
            else:
                kept.append(entry)  # 格式不明，保留
        if len(kept) < len(entries):
            log_file.write_text(
                ("\n" + "=" * 60).join(kept).lstrip(),
                encoding="utf-8"
            )
    except Exception:
        pass


def _cleanup_old_reports(keep_days: int = 30):
    """清理 REPORT_DIR 及 docx 子目录中超过 keep_days 天的旧报告文件。"""
    import time as _time
    cutoff = _time.time() - keep_days * 86400
    cleaned = 0
    for d in [Path(REPORT_DIR), Path(REPORT_DIR) / "docx"]:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.is_file() and f.suffix in (".md", ".docx") and f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    cleaned += 1
                except OSError:
                    pass
    if cleaned:
        print(f"[清理] 已删除 {cleaned} 个超过 {keep_days} 天的旧报告")


def _acquire_lock():
    """获取运行锁，防止 cron 重叠。返回 fd（成功）或 None（已有实例在跑）。"""
    import errno
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
        # 锁文件存在，检查 PID 是否仍活着
        try:
            with open(_LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                print(f"[LOCK] 已有实例运行（PID={pid}），本次跳过")
                return None
            except (ProcessLookupError, AttributeError):
                pass  # 进程已死，清理残留锁
            except PermissionError:
                print(f"[LOCK] 已有实例运行（PID={pid}，权限不足），本次跳过")
                return None
        except (ValueError, IOError):
            pass
        try:
            os.remove(_LOCK_FILE)
        except OSError:
            pass
        fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    return fd


def _release_lock(fd):
    """释放运行锁。"""
    if fd is not None:
        try:
            os.close(fd)
            os.remove(_LOCK_FILE)
        except OSError:
            pass


def _log_error(country: str, depth: str, topic: str, error_msg: str, traceback_str: str = ""):
    """写入错误日志到 logs/analysis_errors.log（超10MB自动轮转）"""
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(exist_ok=True, parents=True)
    log_file = log_dir / "analysis_errors.log"
    # 10MB 轮转：旧文件重命名为 .1，再写新文件
    if log_file.exists() and log_file.stat().st_size > 10 * 1024 * 1024:
        old = log_dir / "analysis_errors.log.1"
        if old.exists():
            old.unlink()
        log_file.rename(old)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{timestamp}] 宏观分析失败\n")
        f.write(f"  参数: topic={topic}, country={country}, depth={depth}\n")
        f.write(f"  错误: {error_msg}\n")
        if traceback_str:
            f.write(f"  堆栈:\n{traceback_str}\n")
    print(f"[ERROR-LOG] 错误已记录到 {log_file}")


def save_report(report: str, topic: str = "综合", country: str = "us", depth: str = "standard", is_fallback: bool = None) -> str:
    """保存报告到文件，同时触发 ntfy 推送和知识库回纳。

    文件命名格式：YYYY-MM-DD_HH-MM_宏观分析_<国家>_<主题>_<深度>.md
    同步生成 docx（如有 md_report_to_docx.py 脚本，否则跳过）。
    ntfy 推送：标题含 [LLM]/[降级] 标记，正文即报告 Markdown 原文。
    知识库回纳：将报告存入 知识库/分析报告历史/，供 RAG 检索参考。

    Args:
        is_fallback: 是否为降级报告。None 时回退到字符串检测（向后兼容）；
                    both 模式时由调用方传入（仅当中美双方均降级才为 True）。
    """
    # 检查报告内容有效性
    if not report or not report.strip():
        _log_error(country, depth, topic, "报告内容为空")
        print("[ERROR] 报告内容为空，跳过保存")
        return ""
    if report.strip() in ("生成失败", "生成失败。", "error", "failed"):
        _log_error(country, depth, topic, f"LLM返回失败标记: {report.strip()}")
        print("[ERROR] 报告生成失败（LLM返回失败标记），跳过保存")
        return ""
    if len(report.strip()) < 100:
        _log_error(country, depth, topic, f"报告内容过短({len(report.strip())}字符)，可能是生成失败: {report.strip()[:80]}")
        print(f"[ERROR] 报告内容过短({len(report.strip())}字符)，跳过保存")
        return ""
    
    country_label = {"us": "美国", "china": "中国", "both": "中美"}.get(country, country)
    depth_label = {"quick": "速报", "standard": "标准", "deep": "深度"}.get(depth, depth)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = os.path.join(REPORT_DIR,
               f"{timestamp}_宏观分析_{country_label}_{topic}_{depth_label}.md")

    os.makedirs(os.path.dirname(filename), exist_ok=True)

    is_fallback = is_fallback if is_fallback is not None else ("LLM 不可用" in report or "自动降级报告" in report)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# 宏观分析报告 - {country_label}{topic}（{depth_label}）\n\n")
        f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"国家：{country_label} | 深度：{depth_label}\n\n")
        if is_fallback:
            f.write("> **[降级模式]** LLM 不可用，本报告由纯数据规则自动生成，非 LLM 叙事分析。\n\n")
        f.write("---\n\n")
        f.write(report)
    
    # 转换为 Word 文档，输出到报告目录下的 docx 子目录
    docs_dir = os.path.join(REPORT_DIR, "docx")
    os.makedirs(docs_dir, exist_ok=True)
    docx_filename = os.path.join(docs_dir, Path(filename).stem + ".docx")
    convert_script = ""  # 本机无 md_report_to_docx.py，跳过 Word 转换
    python_exe = sys.executable
    if convert_script and os.path.exists(convert_script):
        try:
            result = subprocess.run([python_exe, convert_script, filename, "-o", docx_filename],
                                   capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                print(f"[FILE] Word 版本已保存：{docx_filename}")
            else:
                print(f"[WARN] Word 转换失败：{result.stderr[:200]}")
        except Exception as e:
            print(f"[WARN] Word 转换异常：{e}")
    
    # 回纳入知识库
    try:
        kb_dir = os.path.join(KB_DIR, "07_分析报告")
        os.makedirs(kb_dir, exist_ok=True)
        kb_filename = os.path.join(kb_dir, Path(filename).name)
        
        # 追加元数据头，便于RAG检索
        metadata = (
            f"# 宏观分析报告 - {country_label}{topic}（{depth_label}）\n\n"
            f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- 国家：{country_label} | 深度：{depth_label}\n"
            f"- 标签：宏观分析, {country_label}, {topic}\n\n"
            f"---\n\n"
            f"{report}"
        )
        with open(kb_filename, "w", encoding="utf-8") as f:
            f.write(metadata)
        print(f"[KB] 已回纳入知识库：{kb_filename}")
    except Exception as e:
        print(f"[WARN] 知识库回纳失败：{e}")
    
    print(f"\n[FILE] 报告已保存：{filename}")

    # ntfy 推送（PUT raw body + UTF-8 伪 Latin-1 编码）
    _ntfy_topic = os.environ.get("NTFY_TOPIC", "")
    if _ntfy_topic:
        try:
            mode_tag = "[降级]" if is_fallback else "[LLM]"
            _title = f"{mode_tag} {country_label}{topic} 报告已生成"
            _title_safe = _title.encode("utf-8").decode("latin-1")
            _fname_safe = Path(filename).name.encode("utf-8").decode("latin-1")
            _proxies = None  # \u4ee3\u7406\u5bfc\u81f4 ntfy SSL \u9519\u8bef + \u901f\u5ea6\u61625\u500d\uff0c\u5f3a\u5236\u76f4\u8fde\uff08NAS\u5b9e\u6d4b\u9a8c\u8bc1\uff09
            with open(filename, "rb") as _f:
                requests.put(
                    f"https://ntfy.sh/{_ntfy_topic}",
                    data=_f.read(),
                    headers={
                        "Title": _title_safe,
                        "Filename": _fname_safe,
                    "Message": "\u200b".encode("utf-8").decode("latin-1"),
                        "Content-Type": "text/markdown; charset=utf-8",
                    },
                    proxies=_proxies,
                    timeout=60,  # \u5927\u6587\u4ef6\u62a5\u544a\u9700\u8981\u8db3\u591f\u8d85\u65f6\uff08NAS\u5b9e\u6d4b15s\u4e0d\u591f\uff09
                )
        except Exception as e:
            print(f"[WARN] ntfy 推送失败: {e}")

    return filename




# =========================
# 主流程
# =========================

def _check_idempotent(country: str, depth: str) -> Optional[str]:
    """幂等检查：今天同一 country+depth 是否已有报告，有则返回文件路径"""
    report_dir = Path(REPORT_DIR)
    if not report_dir.exists():
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    country_label = {"us": "美国", "china": "中国", "both": "中美"}.get(country, country)
    depth_label = {"quick": "速报", "standard": "标准", "deep": "深度"}.get(depth, depth)
    for f in report_dir.iterdir():
        if not f.name.startswith(today):
            continue
        if country_label in f.name and depth_label in f.name:
            return str(f)
    # 兼容旧格式（无 country/depth 标记），同一天同 country+depth 只保留1份
    # 旧格式全叫 xxx_宏观分析_综合.md，无法区分，跳过
    return None


def _run_backtest():
    """
    回测验证：读取 predictions_log.json，对已到期记录抓取真实 FRED 数据，
    计算预测误差并更新 status/accuracy 字段。
    """
    from optim_config import PREDICTIONS_LOG
    import requests as _req

    print("\n" + "=" * 60)
    print("预测回测验证")
    print("=" * 60)

    if not os.path.exists(PREDICTIONS_LOG):
        print("predictions_log.json 不存在，无记录可验证。")
        return

    with open(PREDICTIONS_LOG, encoding="utf-8") as f:
        log = json.load(f)

    today = datetime.now().date()
    pending = [e for e in log if e.get("status") == "pending"]
    due = [e for e in pending if e.get("verify_after", "9999") <= str(today)]

    print(f"总记录: {len(log)}  |  待验证: {len(pending)}  |  已到期: {len(due)}")

    if not due:
        print("\n暂无到期需验证的预测记录。")
        _show_pending_summary(pending)
        return

    updated = 0
    for entry in due:
        pid = entry["id"][:8]
        created = entry.get("created_at", "")[:10]
        verify_after = entry.get("verify_after", "")
        print(f"\n[验证] {pid}... | 创建:{created} | 验证期:{verify_after}")

        # 抓取实际 GDP、UNRATE、CPI
        actuals = {}
        try:
            # GDP（GDPC1）
            gdp_url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id=GDPC1&api_key={FRED_API_KEY}"
                f"&file_type=json&sort_order=desc&limit=5"
            )
            gdp_resp = _req.get(gdp_url, timeout=8, proxies=_get_fred_proxies())
            if gdp_resp.status_code == 200:
                obs = gdp_resp.json().get("observations", [])
                for ob in obs:
                    v = ob.get("value", ".")
                    if v not in (".", ""):
                        # 计算 YoY
                        obs_all_url = (
                            f"https://api.stlouisfed.org/fred/series/observations"
                            f"?series_id=GDPC1&api_key={FRED_API_KEY}"
                            f"&file_type=json&sort_order=asc&limit=8"
                            f"&observation_end={ob['date']}"
                        )
                        obs2 = _req.get(obs_all_url, timeout=8, proxies=_get_fred_proxies())
                        if obs2.status_code == 200:
                            hist = [x for x in obs2.json().get("observations", []) if x["value"] not in (".", "")]
                            if len(hist) >= 5:
                                curr = float(hist[-1]["value"])
                                prev = float(hist[-5]["value"])
                                if prev > 0:
                                    actuals["gdp_actual"] = round((curr - prev) / prev * 100, 2)
                        break
        except Exception as e:
            print(f"  [WARN] GDP实际值获取失败: {e}")

        try:
            # UNRATE
            ur_url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id=UNRATE&api_key={FRED_API_KEY}"
                f"&file_type=json&sort_order=desc&limit=2"
            )
            ur_resp = _req.get(ur_url, timeout=8, proxies=_get_fred_proxies())
            if ur_resp.status_code == 200:
                obs = ur_resp.json().get("observations", [])
                for ob in obs:
                    v = ob.get("value", ".")
                    if v not in (".", ""):
                        actuals["unrate_actual"] = float(v)
                        break
        except Exception as e:
            print(f"  [WARN] UNRATE实际值获取失败: {e}")

        try:
            # CPI YoY
            cpi_url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id=CPIAUCSL&api_key={FRED_API_KEY}"
                f"&file_type=json&sort_order=desc&limit=15"
            )
            cpi_resp = _req.get(cpi_url, timeout=8, proxies=_get_fred_proxies())
            if cpi_resp.status_code == 200:
                obs = sorted(
                    [o for o in cpi_resp.json().get("observations", []) if o["value"] not in (".", "")],
                    key=lambda x: x["date"]
                )
                if len(obs) >= 13:
                    curr_cpi = float(obs[-1]["value"])
                    prev_cpi = float(obs[-13]["value"])
                    if prev_cpi > 0:
                        actuals["cpi_actual"] = round((curr_cpi - prev_cpi) / prev_cpi * 100, 2)
        except Exception as e:
            print(f"  [WARN] CPI实际值获取失败: {e}")

        if not actuals:
            print(f"  [SKIP] 实际数据获取失败，保留 pending 状态")
            continue

        # 计算误差
        preds = entry.get("predictions", {})
        accuracy = {}

        if "gdp_actual" in actuals and preds.get("gdp_p50") is not None:
            err = round(actuals["gdp_actual"] - preds["gdp_p50"], 2)
            in_range = (preds.get("gdp_p10", -99) <= actuals["gdp_actual"] <= preds.get("gdp_p90", 99))
            accuracy["gdp"] = {
                "predicted_p50": preds["gdp_p50"],
                "actual": actuals["gdp_actual"],
                "error": err,
                "in_p10_p90_range": in_range,
            }
            print(f"  GDP: 预测{preds['gdp_p50']:.2f}% → 实际{actuals['gdp_actual']:.2f}%（误差{err:+.2f}ppt，{'✅区间内' if in_range else '❌区间外'}）")

        if "unrate_actual" in actuals and preds.get("unrate_p50") is not None:
            err = round(actuals["unrate_actual"] - preds["unrate_p50"], 2)
            accuracy["unrate"] = {
                "predicted_p50": preds["unrate_p50"],
                "actual": actuals["unrate_actual"],
                "error": err,
            }
            print(f"  UNRATE: 预测{preds['unrate_p50']:.2f}% → 实际{actuals['unrate_actual']:.2f}%（误差{err:+.2f}ppt）")

        if "cpi_actual" in actuals and preds.get("cpi_yoy_p50") is not None:
            err = round(actuals["cpi_actual"] - preds["cpi_yoy_p50"], 2)
            accuracy["cpi"] = {
                "predicted_p50": preds["cpi_yoy_p50"],
                "actual": actuals["cpi_actual"],
                "error": err,
            }
            print(f"  CPI: 预测{preds['cpi_yoy_p50']:.2f}% → 实际{actuals['cpi_actual']:.2f}%（误差{err:+.2f}ppt）")

        # 更新记录
        entry["actuals"] = actuals
        entry["accuracy"] = accuracy
        entry["status"] = "verified"
        entry["verified_at"] = datetime.now().isoformat()
        updated += 1

    if updated > 0:
        with open(PREDICTIONS_LOG, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        print(f"\n已更新 {updated} 条验证记录。")

    _show_pending_summary([e for e in log if e.get("status") == "pending"])

    # 验证完成后自动显示滚动精度报告
    report = compute_rolling_accuracy_report(window_months=6)
    print("\n" + report)


def _show_pending_summary(pending: list):
    """显示待验证预测记录摘要"""
    if not pending:
        return
    print(f"\n待验证预测（{len(pending)}条）：")
    print(f"{'ID':^10} {'创建日期':^12} {'验证期':^12} {'GDP预测':^10} {'衰退概率':^8}")
    print("-" * 55)
    for e in sorted(pending, key=lambda x: x.get("verify_after", ""))[-10:]:
        pid = e["id"][:8]
        created = e.get("created_at", "")[:10]
        verify = e.get("verify_after", "—")
        gdp = e.get("predictions", {}).get("gdp_p50")
        rec = e.get("predictions", {}).get("recession_prob_pct")
        gdp_str = f"{gdp:.2f}%" if gdp is not None else "—"
        rec_str = f"{rec:.1f}%" if rec is not None else "—"
        print(f"{pid:^10} {created:^12} {verify:^12} {gdp_str:^10} {rec_str:^8}")


def compute_rolling_accuracy_report(window_months: int = None) -> str:
    """
    读取 predictions_log.json（已 verified 记录），生成：
      1. 滚动窗口命中率（最近 N 个月，默认从 optim_config 读取）
      2. 体制条件准确率（normal vs stress）
      3. 衰退概率区间校准（5个分段）
    返回 Markdown 格式报告字符串。
    """
    import math
    from optim_config import PREDICTIONS_LOG, GDP_HIT_TOLERANCE
    try:
        from optim_config import ROLLING_ACCURACY_WINDOW_MONTHS
    except ImportError:
        ROLLING_ACCURACY_WINDOW_MONTHS = 6
    if window_months is None:
        window_months = ROLLING_ACCURACY_WINDOW_MONTHS

    if not os.path.exists(PREDICTIONS_LOG):
        return "predictions_log.json 不存在。"

    with open(PREDICTIONS_LOG, encoding="utf-8") as f:
        log = json.load(f)

    verified = [e for e in log
                if e.get("status") == "verified"
                and e.get("scenario") not in ("baseline_cn",)]
    if not verified:
        return "暂无已验证的美国预测记录，无法计算精度。"

    verified.sort(key=lambda x: x.get("verify_after", ""))

    # ── 1. 全量统计 ───────────────────────────────────────────────────────────
    gdp_errors, gdp_hits, gdp_tried = [], [], 0
    cpi_errors, unrate_errors = [], []
    for r in verified:
        acc = r.get("accuracy", {})
        if acc.get("gdp_hit") is not None:
            gdp_tried += 1
            gdp_hits.append(1 if acc["gdp_hit"] else 0)
            e = acc.get("gdp_error")
            if e is not None:
                gdp_errors.append(e)
        if acc.get("cpi_error") is not None:
            cpi_errors.append(acc["cpi_error"])
        if acc.get("unrate_error") is not None:
            unrate_errors.append(acc["unrate_error"])

    def _mae(errs): return sum(abs(x) for x in errs) / len(errs) if errs else None
    def _rmse(errs):
        return math.sqrt(sum(x**2 for x in errs) / len(errs)) if errs else None

    total_hit_rate = sum(gdp_hits) / len(gdp_hits) * 100 if gdp_hits else None

    # ── 2. 滚动窗口（最近 window_months 个月） ────────────────────────────────
    from datetime import date as _date
    cutoff_str = (_date.today().replace(
        month=max(1, _date.today().month - window_months % 12),
        year=_date.today().year - window_months // 12,
    )).isoformat()

    recent = [r for r in verified if r.get("verify_after", "") >= cutoff_str]
    recent_hits = [1 if r.get("accuracy", {}).get("gdp_hit") else 0
                   for r in recent if r.get("accuracy", {}).get("gdp_hit") is not None]
    recent_hit_rate = sum(recent_hits) / len(recent_hits) * 100 if recent_hits else None
    recent_gdp_errors = [r.get("accuracy", {}).get("gdp_error")
                         for r in recent if r.get("accuracy", {}).get("gdp_error") is not None]

    # ── 3. 体制条件准确率 ─────────────────────────────────────────────────────
    regime_stats: dict = {}
    for r in verified:
        regime = r.get("regime", "normal")
        acc = r.get("accuracy", {})
        if acc.get("gdp_hit") is None:
            continue
        if regime not in regime_stats:
            regime_stats[regime] = {"hits": 0, "total": 0, "errors": []}
        regime_stats[regime]["total"] += 1
        if acc["gdp_hit"]:
            regime_stats[regime]["hits"] += 1
        e = acc.get("gdp_error")
        if e is not None:
            regime_stats[regime]["errors"].append(e)

    # ── 4. 衰退概率区间校准 ────────────────────────────────────────────────────
    # 区间：[0-20), [20-40), [40-60), [60-80), [80-100]
    # 实际衰退 = actuals 中 gdp_growth < 0 代理（无直接衰退标签时）
    calibration_bins = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
    bin_stats = {b: {"n": 0, "realized": 0} for b in calibration_bins}
    for r in verified:
        rec_pct = r.get("predictions", {}).get("recession_prob_pct")
        gdp_actual = r.get("actuals", {}).get("gdp_growth")
        if rec_pct is None or gdp_actual is None:
            continue
        recession_realized = 1 if gdp_actual < 0 else 0
        for (lo, hi) in calibration_bins:
            if lo <= rec_pct < hi:
                bin_stats[(lo, hi)]["n"] += 1
                bin_stats[(lo, hi)]["realized"] += recession_realized
                break

    # ── 5. 组装报告 ───────────────────────────────────────────────────────────
    lines = [
        f"## 预测精度分析报告（{_date.today().isoformat()}）",
        "",
        f"### 总量统计（共 {len(verified)} 条已验证记录）",
        "",
        "| 指标 | 全量值 | 最近{n}个月 |".format(n=window_months),
        "|:----|:---:|:---:|",
        f"| GDP命中率 (±{GDP_HIT_TOLERANCE}ppt) | "
        f"{f'{total_hit_rate:.0f}%' if total_hit_rate is not None else '—'} | "
        f"{f'{recent_hit_rate:.0f}%（n={len(recent_hits)}）' if recent_hit_rate is not None else '—'} |",
        f"| GDP MAE | "
        f"{f'{_mae(gdp_errors):.3f}ppt' if _mae(gdp_errors) is not None else '—'} | "
        f"{f'{_mae(recent_gdp_errors):.3f}ppt' if _mae(recent_gdp_errors) is not None else '—'} |",
        f"| GDP RMSE | "
        f"{f'{_rmse(gdp_errors):.3f}ppt' if _rmse(gdp_errors) is not None else '—'} | — |",
        f"| CPI MAE | {f'{_mae(cpi_errors):.3f}ppt' if _mae(cpi_errors) is not None else '—'} | — |",
        f"| 失业率 MAE | {f'{_mae(unrate_errors):.3f}ppt' if _mae(unrate_errors) is not None else '—'} | — |",
        "",
    ]

    if regime_stats:
        lines.append("### 体制条件准确率")
        lines.append("")
        lines.append("| 体制 | 记录数 | GDP命中率 | MAE |")
        lines.append("|:----|:---:|:---:|:---:|")
        for regime, st in sorted(regime_stats.items()):
            hr = st["hits"] / st["total"] * 100 if st["total"] > 0 else None
            mae = _mae(st["errors"])
            lines.append(f"| {regime} | {st['total']} | "
                         f"{f'{hr:.0f}%' if hr is not None else '—'} | "
                         f"{f'{mae:.3f}ppt' if mae is not None else '—'} |")
        lines.append("")

    # 校准表（仅当有足够数据时）
    cal_total = sum(st["n"] for st in bin_stats.values())
    if cal_total >= 5:
        lines.append("### 衰退概率区间校准（预测概率 vs 实际衰退率）")
        lines.append("")
        lines.append("| 预测概率区间 | 记录数 | 实际衰退率 | 校准偏差 |")
        lines.append("|:---|:---:|:---:|:---:|")
        for (lo, hi), st in bin_stats.items():
            if st["n"] == 0:
                lines.append(f"| [{lo}–{min(hi,100)}%) | 0 | — | — |")
                continue
            realized_rate = st["realized"] / st["n"] * 100
            midpoint = (lo + min(hi - 1, 100)) / 2
            bias = realized_rate - midpoint
            lines.append(f"| [{lo}–{min(hi,100)}%) | {st['n']} | "
                         f"{realized_rate:.0f}% | {bias:+.0f}ppt |")
        lines.append("")
        lines.append("> 校准偏差 = 实际衰退率 − 预测概率区间中点；接近 0 表示校准良好")
        lines.append("")

    return "\n".join(lines)


def run_macro_analysis(
        topic: str = "综合", depth: str = "standard", country: str = "us", reasoning: str = "auto", force: bool = False) -> Dict:
    """
    主分析流程（8步骤，完整管道入口）

    Args:
        topic:     "综合" | "衰退" | "通胀" | "市场" | "地缘"（影响RAG查询词和报告侧重）
        depth:     "quick"（约5分钟，跳过蒙特卡洛）| "standard"（约15分钟）| "deep"（约30分钟，更多路径）
        country:   "us" | "china" | "both"（影响数据源、评分函数、提示词模板）
        reasoning: "auto"（默认；USE_EXTERNAL_LLM=1时：MiMo→Claude→SiliconFlow）| "local"（强制SiliconFlow）| "claude"（强制Claude API）
        force:     True时跳过幂等检查，允许cron当天重跑（用于手动触发修正）

    Returns:
        dict，含键：report(str), filename(str), indicators(dict), recession(tuple),
               inflation(tuple), crises(list), monte_carlo(dict), idempotent_skip(bool)
    """
    
    # 幂等检查：cron自动触发时，今天已跑过则跳过；force=True时跳过检查
    if not force:
        existing = _check_idempotent(country, depth)
        if existing:
            print(f"[IDEMPOTENT] 今天已存在 {country}/{depth} 报告：{existing}")
            print("[IDEMPOTENT] 跳过重复执行，直接返回已有报告")
            with open(existing, "r", encoding="utf-8") as f:
                existing_report = f.read()
            return {
                "report": existing_report,
                "filename": existing,
                "indicators": {},
                "recession": None,
                "inflation": None,
                "crises": [],
                "monte_carlo": None,
                "idempotent_skip": True,
            }
    
    print("=" * 60)
    country_name = {"us": "美国", "china": "中国", "both": "中美对比"}.get(country, country)
    print(f"宏观分析：{topic} | 深度：{depth} | 国家：{country_name}")
    print("=" * 60)
    
    # Step 1: 获取当前数据
    us_indicators: dict = {}
    china_indicators: dict = {}
    us_recession = us_inflation = cn_recession = cn_inflation = None
    mc = china_mc = None
    if country == "us":
        indicators = get_current_snapshot()
        us_indicators = indicators
    elif country == "china":
        indicators = get_china_current_snapshot()
        china_indicators = indicators
    else:  # both
        us_indicators = get_current_snapshot()
        china_indicators = get_china_current_snapshot()
        indicators = {"us": us_indicators, "china": china_indicators}
    
    # Step 2: 衰退/通胀评分（按国家选择评分函数）
    print("\n[2/7] 计算风险评分...")
    _ind_for_score = us_indicators if country == "both" else indicators
    if country == "china":
        recession = score_china_recession_risk(indicators)
        inflation = score_china_inflation_risk(indicators)
    else:
        recession = score_recession_risk(_ind_for_score)
        inflation = score_inflation_risk(_ind_for_score)
    
    print(f"  衰退风险：{recession[0]}（{recession[1]}/100）")
    print(f"  通胀风险：{inflation[0]}（{inflation[1]}/100）")
    
    # 加载地缘事件调整
    geo_adj = load_geo_event_adjustments()
    if geo_adj:
        print(f"\n  [地缘事件调整] 最新事件：{geo_adj.get('latest_event', 'None')}")
        if geo_adj.get('taiwan_strait', 0) != 0:
            print(f"    台海风险：{geo_adj.get('taiwan_strait', 0)}（{geo_adj.get('event_summary', '')[:50]}）")
        if geo_adj.get('tech_decoupling', 0) != 0:
            print(f"    科技脱钩风险：{geo_adj.get('tech_decoupling', 0)}")
        if geo_adj.get('global_trade', 0) != 0:
            print(f"    贸易碎片化风险：{geo_adj.get('global_trade', 0)}")
    
    # Step 3: 历史情景匹配（按国家选择）
    print("\n[3/7] 匹配历史情景...")
    _ind_for_crisis = us_indicators if country == "both" else indicators
    if country == "china":
        crises = match_china_crisis(indicators)
        if crises:
            print(f"  最匹配：{crises[0][0]}（得分：{crises[0][1]:.1f}）")
    else:
        crises = match_crisis(_ind_for_crisis)
        if crises:
            print(f"  最匹配：{crises[0][0]}（得分：{crises[0][1]}）")
    
    # Step 4: RAG检索（按国家调整查询词）
    print("\n[4/7] 检索知识库...")
    if country == "china":
        query_map = {
            "综合": "中国经济宏观分析GDP PMI通胀通缩",
            "衰退": "中国经济下行制造业PMI收缩房地产风险",
            "通胀": "中国CPI PPI通胀货币政策人民银行",
            "市场": "A股市场流动性人民币汇率",
            "地缘": "地缘冲突中美贸易供应链",
        }
    else:
        query_map = {
            "综合": "宏观经济分析框架衰退通胀资产配置",
            "衰退": "衰退风险利差倒挂失业率上升信贷收缩",
            "通胀": "CPI通胀原油货币供应M2工资传导",
            "市场": "股市暴跌流动性枯竭信用利差扩大",
            "地缘": "地缘冲突能源供应供应链大宗商品",
        }
    query = query_map.get(topic, query_map["综合"])

    regime = "normal"  # 默认值，Step 5 覆盖；防止 Step 4 RAG 段读取前 UnboundLocalError
    # 多维度 RAG 查询：优先指标感知查询（最有针对性），然后是 regime 查询，最后是通用查询
    # 注意：实际执行数由 len(rag_chunks) >= 8 早退出控制，无需在此截断
    dynamic_queries = []   # 指标感知（优先级最高）
    regime_queries  = []   # regime 专项
    base_queries    = []   # 国家通用固定查询（兜底）

    # 指标感知：根据当前数值触发
    # regime 可能值: "normal" | "stress" | "crisis"（来自 regime_detector.py）
    if regime in ("stress", "crisis"):
        regime_queries.append("市场压力历史危机流动性枯竭信用利差")
    if regime == "crisis":
        regime_queries.append("金融危机传导机制系统性风险去杠杆")
    try:
        _vix    = float(us_indicators.get("VIX",    {}).get("value", 0) or 0)
        _t10y2y = float(us_indicators.get("T10Y2Y", {}).get("value", 0) or 0)
        _baa10y = float(us_indicators.get("BAA10Y", {}).get("value", 0) or 0)
        _cpi    = float(us_indicators.get("CPIAUCSL", {}).get("value", 0) or 0)
        _unrate = float(us_indicators.get("UNRATE",  {}).get("value", 0) or 0)
        _dff    = float(us_indicators.get("DFF",     {}).get("value", 0) or 0)
        if _vix > 25:
            dynamic_queries.append("VIX恐慌指数波动率上升历史案例风险规避")
        if _t10y2y < -0.3:
            dynamic_queries.append("收益率曲线倒挂衰退预警历史倒挂持续时间")
        if _baa10y > 3.0:
            dynamic_queries.append("信用利差扩大企业债违约风险历史案例")
        if _cpi > 3.0:
            dynamic_queries.append("通胀持续性美联储加息路径滞胀风险")
        if _unrate > 5.0:
            dynamic_queries.append("失业率上升劳动力市场衰退触发机制")
        if _dff > 4.5:
            dynamic_queries.append("高利率环境资产配置衰退历史案例联储降息预期")
    except Exception:
        pass

    if country in ("china", "both"):
        try:
            _cn_ind = china_indicators if country == "both" else indicators
            _cn_pmi = float(
                _cn_ind.get("pmi_mfg", {}).get("value", 51) or
                _cn_ind.get("pmi_composite", {}).get("value", 51) or 51
            )
            _cn_ppi = float(_cn_ind.get("ppi", {}).get("value", 0) or 0)
            if _cn_pmi < 50:
                dynamic_queries.append("中国制造业PMI萎缩区间历史案例经济下行")
            if _cn_ppi < -1.0:
                dynamic_queries.append("中国PPI通缩产能过剩企业利润压缩历史")
        except Exception:
            pass

    # 通用固定查询：当指标感知查询不足以填满 8 块时补充
    if country in ("us", "both"):
        base_queries.append("美联储货币政策利率决策FOMC")
        base_queries.append("通胀传导机制PPI价格压力历史案例")
    if country in ("china", "both"):
        base_queries.append("中国货币政策人民银行LPR降息")
        base_queries.append("中国经济复苏房地产债务风险")

    # 合并：动态 → regime → 通用（优先级由高到低）
    secondary_queries = dynamic_queries + regime_queries + base_queries

    seen_names = set()
    rag_chunks = []
    for q in [query] + secondary_queries:
        for chunk in rag_query(q, n_results=2):
            fname = chunk.split("\n")[0][:60]
            if fname not in seen_names:
                seen_names.add(fname)
                rag_chunks.append(chunk)
            if len(rag_chunks) >= 8:
                break
        if len(rag_chunks) >= 8:
            break

    print(f"  检索到 {len(rag_chunks)} 个相关段落（多维度查询）")

    # Step 4.1: 行业轮动数据（仅美国/综合模式，紧接 RAG 检索之后）
    if _SECTOR_ROTATION_AVAILABLE and country in ("us", "both"):
        print("\n[4.1] 获取行业轮动数据（~7s）...")
        sector_rotation_ctx = get_sector_rotation_context()
        if sector_rotation_ctx:
            rag_chunks.append(sector_rotation_ctx)
            print(f"  [SR] 行业轮动数据已注入 rag_chunks（{len(sector_rotation_ctx)} 字符）")
        else:
            print("  [SR] 行业轮动数据不可用，已跳过")

    # Step 4.5: 在线搜索最新地缘事件
    print("\n[4.5] 搜索最新地缘政治事件...")
    geo_events = search_geopolitical_events(freshness="7d", cnt=5)
    print(f"  {geo_events[:100]}...")
    
    # Step 4.8: 读取弱信号扫描预警新闻
    print("\n[4.8] 读取预警新闻...")
    news_text = format_news_for_prompt(country=country if country != "both" else "us")
    if news_text:
        print(f"  注入 {len(news_text)} 字符的预警新闻")
    else:
        print("  无预警新闻")

    # Step 4.9: 获取欧洲/日本/英国全球背景数据
    print("\n[4.9] 获取全球背景数据（欧/日/英）...")
    intl_context = get_global_context()
    if intl_context:
        print(f"  全球背景 {len(intl_context)} 字符")

    # ── 体制检测（模块05，提前到LLM前，结果注入prompt）───────────────────────
    print("\n[5/7] 体制检测 + 蒙特卡洛模拟...")
    regime, stress_signals = "normal", 0
    mc = None
    crucix_context = ""
    try:
        _ind_for_regime = us_indicators if country == "both" else indicators
        regime, stress_signals = detect_regime(_ind_for_regime)
        coeffs = get_coefficients(regime)
        print(f"  [体制] {regime} | 压力信号 {stress_signals}/7 | {coeffs['description']}")

        # gscpi_warn + crucix_context（供 generate_report 注入 prompt）
        try:
            from regime_detector import get_regime_info
            _ri = get_regime_info(_ind_for_regime)
            _gscpi_warn  = _ri.get("gscpi_warn", False)
            _gscpi_value = _ri.get("gscpi_value")
        except Exception:
            _gscpi_warn, _gscpi_value = False, None

        _cx = (_ind_for_regime if country != "both" else us_indicators).get("_crucix") or {}
        _cx_lines = []
        if _gscpi_warn and _gscpi_value is not None:
            _cx_lines.append(f"- ⚠️ 全球供应链压力指数（GSCPI）= {_gscpi_value:.2f}【elevated，高于警戒阈值 1.5】")
        elif _gscpi_value is not None:
            _cx_lines.append(f"- 全球供应链压力指数（GSCPI）= {_gscpi_value:.2f}")
        _nuke = _cx.get("nuke") or []
        for _n in _nuke:
            if _n.get("anom"):
                _cx_lines.append(f"- ⚠️ 核辐射异常：{_n.get('site', '未知站点')} CPM={_n.get('cpm', '?')}")
        crucix_context = ("\n## Crucix 实时多源信号\n" + "\n".join(_cx_lines)) if _cx_lines else ""
        if crucix_context:
            print(f"  [Crucix] 注入 {len(_cx_lines)} 条实时信号到 prompt")

        # 叙事上下文注入（天玑 narrative_processor）
        narrative_context = ""
        try:
            from narrative_processor import get_narrative_context_for_trigger
            from geo_risk_vector import compute_grv
            import json as _json, os as _os
            _grv_path = _os.path.join(_os.environ.get("OPENCLAW_WORKSPACE", "/workspace"), "data", "grv_latest.json")
            _grv = {}
            if _os.path.exists(_grv_path):
                with open(_grv_path, encoding="utf-8") as _f:
                    _grv = _json.load(_f)
            # 取偏离度最高的维度作为触发维度
            _grv_dims = ["taiwan_strait", "us_china_strategic", "russia_europe",
                         "middle_east_energy", "sanctions_risk", "energy_grid_risk"]
            _triggered = [d for d in _grv_dims if float(_grv.get(d, 0)) > 60]
            if not _triggered:
                _triggered = ["global_composite"]
            _nar_chunks = get_narrative_context_for_trigger(_triggered, total_token_budget=6000)
            if _nar_chunks:
                _nar_lines = []
                for dim, text in _nar_chunks.items():
                    _nar_lines.append(f"\n### 叙事信号 — {dim}\n{text[:1500]}")
                narrative_context = "\n## 叙事上下文（天玑预处理）\n" + "\n".join(_nar_lines)
                print(f"  [叙事] 注入 {len(_nar_chunks)} 个维度叙事上下文")
        except Exception as _ne:
            print(f"  [叙事] 叙事上下文加载跳过：{_ne}")

        # 美国蒙特卡洛
        if country in ("us", "both"):
            from monte_carlo_v2 import run_monte_carlo_compat
            _us_ind = us_indicators if country == "both" else indicators
            mc = run_monte_carlo_compat(_us_ind, coeffs)
            if mc:
                mc["stress_signals"] = stress_signals
                cal_status = "[历史校准]" if mc.get("calibrated") else "[固定参数]"
                print(f"  [美国MC] 衰退概率: {mc['recession_prob']}% {cal_status}")
                print(f"  [美国MC] GDP分布: 均值{mc['gdp']['mean']}%, 5%分位{mc['gdp']['p5']}%")

        # 中国蒙特卡洛
        china_mc = None
        if country in ("china", "both"):
            _cn_ind = china_indicators if country == "both" else indicators
            china_mc = run_china_monte_carlo(_cn_ind)
            if china_mc:
                print(f"  [中国MC] 衰退概率: {china_mc['recession_prob']}%")

        # 跨国溢出（both模式下，MC双边均有结果时计算）
        spillover_text = ""
        if country == "both" and mc and china_mc:
            spillover_text = compute_cross_country_spillover(
                mc, china_mc, us_indicators, china_indicators
            )
            if spillover_text:
                print("  [跨国溢出v2] 中美多渠道传导矩阵计算完成")
    except Exception as e:
        print(f"  [体制/MC] 警告：{e}")
        coeffs = get_coefficients("normal")

    # Step 5: 生成报告（现在 mc_result 已可用）
    if country == "both":
        # 独立计算中美各自的风险评分
        us_recession  = score_recession_risk(us_indicators)
        us_inflation  = score_inflation_risk(us_indicators)
        cn_recession  = score_china_recession_risk(china_indicators)
        cn_inflation  = score_china_inflation_risk(china_indicators)

        # 中美各自的历史情景匹配
        us_crises = match_crisis(us_indicators)
        cn_crises = match_china_crisis(china_indicators)

        # 美国报告
        us_prompt = generate_report(
            indicators=us_indicators,
            recession_result=us_recession,
            inflation_result=us_inflation,
            crisis_matches=us_crises,
            rag_chunks=rag_chunks,
            country="us",
            news_text=news_text,
            geo_events=geo_events,
            mc_result=mc,
            regime=regime,
            intl_context=intl_context,
            spillover_text=spillover_text,
            crucix_context=crucix_context,
            narrative_context=narrative_context,
        )
        us_report = call_llm_primary(us_prompt, mode=reasoning)
        if not us_report or not us_report.strip():
            print("  [降级] 美国报告 LLM 不可用，自动生成数据报告")
            us_report = _make_fallback_section("us", us_indicators, us_recession, us_inflation, mc, regime)

        # 中国报告
        cn_query = query_map_cn = {
            "综合": "中国经济宏观分析GDP PMI通胀通缩",
        }.get(topic, "中国经济宏观分析GDP PMI通胀通缩")
        cn_chunks = rag_query(cn_query, n_results=3)
        cn_news_text = format_news_for_prompt(country="china")

        china_prompt = generate_report(
            indicators=china_indicators,
            recession_result=cn_recession,
            inflation_result=cn_inflation,
            crisis_matches=cn_crises,
            rag_chunks=cn_chunks,
            country="china",
            news_text=cn_news_text,
            geo_events=geo_events,
            mc_result=china_mc,
            regime=regime,
            intl_context=intl_context,
            spillover_text=spillover_text,
            crucix_context=crucix_context,
            narrative_context=narrative_context,
        )
        china_report = call_llm_primary(china_prompt, mode=reasoning)
        if not china_report or not china_report.strip():
            print("  [降级] 中国报告 LLM 不可用，自动生成数据报告")
            china_report = _make_fallback_section("china", china_indicators, cn_recession, cn_inflation, china_mc, regime)

        # 合并报告（前置自动生成的综合研判摘要）
        synopsis = _build_both_synopsis(
            us_recession=us_recession, us_inflation=us_inflation,
            cn_recession=cn_recession, cn_inflation=cn_inflation,
            us_mc=mc, cn_mc=china_mc,
            regime=regime, spillover_text=spillover_text,
            us_indicators=us_indicators,
        )
        report = synopsis + "\n\n---\n\n# 美国宏观分析\n\n" + us_report + "\n\n---\n\n# 中国宏观分析\n\n" + china_report
    else:
        prompt = generate_report(
            indicators=indicators,
            recession_result=recession,
            inflation_result=inflation,
            crisis_matches=crises,
            rag_chunks=rag_chunks,
            country=country,
            news_text=news_text,
            geo_events=geo_events,
            mc_result=mc if country == "us" else (china_mc if country == "china" else None),
            regime=regime,
            intl_context=intl_context,
            crucix_context=crucix_context,
            narrative_context=narrative_context,
        )
        report = call_llm_primary(prompt, mode=reasoning)

    # 检查报告生成是否成功；LLM不可用时降级为纯数据报告
    if not report or not report.strip():
        print(f"  [降级] LLM 不可用，自动生成结构化数据报告")
        _log_error(country, depth, topic, "LLM返回空报告，已降级为纯数据报告")
        _mc_for_fallback = mc if country == "us" else (china_mc if country == "china" else mc)
        report = _make_fallback_section(country, indicators, recession, inflation, _mc_for_fallback, regime)
    
    # ── 体制检测（模块05） ────────────────────────────────────────────────────
    # 已在 Step 5 之前完成，regime / stress_signals / mc / coeffs 均已就绪

    # Step 6: 蒙特卡洛摘要输出（MC 已在前面运行）
    if mc:
        cal_status = "[历史校准]" if mc.get("calibrated") else "[固定参数]"
        print(f"\n[6/7] 蒙特卡洛已完成 {cal_status}（已注入报告prompt）")
        print(f"  衰退概率: {mc['recession_prob']}% | GDP均值: {mc['gdp']['mean']}%")
    else:
        print("\n[6/7] 蒙特卡洛跳过（无有效数据）")
    
    # Step 7: 保存报告
    # Bug #2 fix: per-section fallback 检测——仅当 中美双方均降级 时才加 [降级模式] banner
    # Bug #3 fix: country != both 时 us_report/china_report 未定义
    if country == "both":
        us_is_fallback = "LLM 不可用" in us_report
        china_is_fallback = "LLM 不可用" in china_report
        combined_is_fallback = us_is_fallback and china_is_fallback
    else:
        combined_is_fallback = "LLM 不可用" in report
    filename = save_report(report, topic, country, depth, is_fallback=combined_is_fallback)
    
    # ── 模块01：记录预测到日志 ────────────────────────────────────────────
    # 说明：
    #   - 只在有蒙特卡洛结果时记录（美国分析）
    #   - 中国分析暂无蒙特卡洛，不记录
    #   - 使用 adapter.py 做格式转换
    # ────────────────────────────────────────────────────────────────────────
    try:
        from adapter import map_mc_results, map_risk_scores
        from prediction_logger import log_prediction

        if mc and country != "china":
            mc_mapped = map_mc_results(mc)
            # both 模式使用独立的 us_recession/us_inflation；us/单国模式用 recession/inflation
            _us_rec = us_recession if country == "both" else recession
            _us_inf = us_inflation if country == "both" else inflation
            risk_mapped = map_risk_scores(_us_rec, _us_inf)

            # both 模式的 indicators 是嵌套字典，取 us 子集
            _ind_for_log = us_indicators if country == "both" else indicators
            indicators_clean = {k: v for k, v in _ind_for_log.items() if k != '_crucix'}

            prediction_id = log_prediction(
                indicators=indicators_clean,
                mc_results=mc_mapped,
                risk_scores=risk_mapped,
                scenario_label="baseline",
                horizon_months=3,
                regime=regime,
                stress_signals=stress_signals,
            )

            if prediction_id:
                print(f"[预测日志] 已记录：{prediction_id[:8]}...")

            # both 模式：同时记录中国MC预测（若有数据）
            if country == "both" and china_mc:
                cn_mc_mapped = map_mc_results(china_mc)
                cn_risk = map_risk_scores(cn_recession, cn_inflation)
                cn_ind_clean = {k: v for k, v in china_indicators.items()
                                if k not in ('_crucix', '_data_note')}
                cn_pred_id = log_prediction(
                    indicators=cn_ind_clean,
                    mc_results=cn_mc_mapped,
                    risk_scores=cn_risk,
                    scenario_label="baseline_cn",
                    horizon_months=3,
                    regime=regime,
                    stress_signals=stress_signals,
                )
                if cn_pred_id:
                    print(f"[预测日志] 中国已记录：{cn_pred_id[:8]}...")

        elif country == "china":
            print("[预测日志] 中国分析暂无蒙特卡洛模拟，跳过记录")
        else:
            print("[预测日志] 无蒙特卡洛结果，跳过记录")

    except Exception as e:
        print(f"[预测日志] 警告：记录失败 - {e}")
        # 不中断主流程，只打印警告

    # ── SQLite 预测追踪（ForecastTracker，5体制完整分布）────────────────────────
    try:
        from forecast_tracker import ForecastTracker

        _ft = ForecastTracker()

        def _ft_predictions(mc_dict):
            return {
                "gdp_p50":    mc_dict.get("gdp", {}).get("mean"),
                "gdp_p10":    mc_dict.get("gdp", {}).get("p5"),
                "gdp_p90":    mc_dict.get("gdp", {}).get("p95"),
                "unrate_p50": mc_dict.get("unrate", {}).get("mean"),
                "cpi_p50":    mc_dict.get("cpi", {}).get("mean"),
            }

        if mc and country != "china":
            _regime_probs = mc.get("regime_probs") or {}
            if not _regime_probs:
                # 旧版 MC 无 regime_probs，用 recession_prob 构造近似值
                _rp = mc.get("recession_prob", 0) / 100
                _regime_probs = {"recession": _rp, "soft_landing": max(0, 1 - _rp - 0.05),
                                 "deep_recession": 0.0, "stagflation": 0.05, "crisis_vix": 0.0}
            _ind_snap = us_indicators if country == "both" else indicators
            _ft.log_forecast(
                probs=_regime_probs,
                predictions=_ft_predictions(mc),
                input_state={k: v for k, v in _ind_snap.items() if k != '_crucix'},
                scenario="baseline",
                horizon_months=3,
                country="us",
                regime=regime or "normal",
                stress_signals=stress_signals or 0,
            )
            print("[ForecastTracker] 美国预测已入库")

        if country == "both" and china_mc:
            _cn_probs = china_mc.get("regime_probs") or {}
            if not _cn_probs:
                _rp = china_mc.get("recession_prob", 0) / 100
                _cn_probs = {"recession": _rp, "soft_landing": max(0, 1 - _rp - 0.05),
                             "deep_recession": 0.0, "stagflation": 0.05, "crisis_vix": 0.0}
            _ft.log_forecast(
                probs=_cn_probs,
                predictions=_ft_predictions(china_mc),
                input_state={k: v for k, v in china_indicators.items()
                             if k not in ('_crucix', '_data_note')},
                scenario="baseline_cn",
                horizon_months=3,
                country="cn",
                regime=regime or "normal",
                stress_signals=stress_signals or 0,
            )
            print("[ForecastTracker] 中国预测已入库")

    except Exception as e:
        print(f"[ForecastTracker] 警告：入库失败 - {e}")

    # ── 月度简报（Executive Briefing）─────────────────────────────────────────
    outlook_filename = ""
    try:
        _us_ind_out  = us_indicators  if country == "both" else (indicators if country == "us" else {})
        _cn_ind_out  = china_indicators if country in ("both", "china") else None
        _us_mc_out   = mc          if country in ("us", "both") else None
        _cn_mc_out   = china_mc    if country in ("both", "china") else None
        _us_rec_out  = us_recession if country == "both" else (recession if country == "us" else None)
        _us_inf_out  = us_inflation if country == "both" else (inflation  if country == "us" else None)
        _cn_rec_out  = cn_recession if country == "both" else (recession  if country == "china" else None)
        _cn_inf_out  = cn_inflation if country == "both" else (inflation   if country == "china" else None)

        outlook_md = generate_monthly_outlook(
            us_indicators  = _us_ind_out,
            china_indicators = _cn_ind_out,
            us_mc          = _us_mc_out,
            china_mc       = _cn_mc_out,
            us_recession   = _us_rec_out,
            us_inflation   = _us_inf_out,
            cn_recession   = _cn_rec_out,
            cn_inflation   = _cn_inf_out,
            regime         = regime,
            spillover_text = spillover_text,
        )
        # 保存到独立文件
        report_dir = Path(REPORT_DIR)
        report_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        outlook_filename = str(report_dir / f"月度简报_{today}_{country}.md")
        with open(outlook_filename, "w", encoding="utf-8") as f:
            f.write(outlook_md)
        print(f"[月度简报] 已生成：{outlook_filename}")
    except Exception as e:
        print(f"[月度简报] 警告：生成失败 - {e}")

    # 返回结果
    return {
        "report": report,
        "filename": filename,
        "outlook_filename": outlook_filename,
        "indicators": indicators,
        "recession": recession,
        "inflation": inflation,
        "crises": crises,
        "monte_carlo": mc,
    }











def score_global_recession_risk() -> str:
    """
    从 FRED 拉取欧元区、日本、英国、印度的关键指标，
    计算各经济体的简化衰退风险评分，输出全球风险对比表。

    评分逻辑（每经济体 0-100）：
      - 失业率变化趋势（vs 历史低位）
      - 通胀 vs 目标偏离（过高=滞胀风险，过低=通缩风险）
      - 10年期国债收益率曲线（与政策利率差）
      - PMI（若可得）
    返回 Markdown 表格字符串。
    """
    from datetime import date as _date

    _detect_fred_proxy()

    def _sfetch(sid):
        try:
            d, v = get_fred_latest(sid)
            return v
        except Exception:
            return None

    def _region_score(unrate, unrate_low, cpi, cpi_target,
                      gov10y, policy_rate, pmi=None):
        """
        生成 0-100 风险分。返回 (score, signals)。
        """
        sc = 0
        sigs = []
        # 失业率：高于历史低位 2ppt → +20
        if unrate is not None and unrate_low is not None:
            gap = unrate - unrate_low
            if gap >= 3: sc += 25; sigs.append(f"失业率高于低点{gap:.1f}ppt")
            elif gap >= 1.5: sc += 15; sigs.append(f"失业率上升{gap:.1f}ppt")
            elif gap >= 0.5: sc += 5
        # 通胀偏离：高>1ppt → 滞胀风险；低<0.5 → 通缩风险
        if cpi is not None and cpi_target is not None:
            dev = cpi - cpi_target
            if dev > 3: sc += 20; sigs.append(f"通胀严重超标+{dev:.1f}ppt")
            elif dev > 1: sc += 12; sigs.append(f"通胀超标+{dev:.1f}ppt")
            elif dev < -1: sc += 15; sigs.append(f"通缩压力({cpi:.1f}%<目标)")
            elif dev < 0: sc += 5
        # 利率曲线（10Y - policy rate）
        if gov10y is not None and policy_rate is not None:
            spread = gov10y - policy_rate
            if spread < -0.5: sc += 20; sigs.append(f"曲线倒挂{spread:.2f}%")
            elif spread < 0: sc += 10; sigs.append(f"曲线平坦{spread:.2f}%")
            elif spread > 2: sc += 5; sigs.append(f"曲线极陡(财政压力?)")
        # PMI
        if pmi is not None:
            if pmi < 47: sc += 15; sigs.append(f"PMI深度收缩({pmi:.1f})")
            elif pmi < 49: sc += 8; sigs.append(f"PMI收缩({pmi:.1f})")
            elif pmi < 50: sc += 3
        return min(sc, 100), sigs

    # ── 数据拉取 ─────────────────────────────────────────────────────────────
    # 欧元区
    eu_unrate   = _sfetch("LRHUTTTTEZM156S")  # 失业率
    eu_cpi      = _sfetch("CPIEURO")           # CPI YoY
    eu_10y      = _sfetch("IRLTLT01EZM156N")   # 10Y
    eu_policy   = _sfetch("ECBDFR")            # ECB存款利率（代理政策利率）
    # 日本
    jp_unrate   = _sfetch("LRUNTTTTJPM156S")
    jp_cpi      = _sfetch("CPALTT01JPM659N")
    jp_10y      = _sfetch("IRLTLT01JPM156N")
    jp_policy   = 0.5                          # BOJ 当前利率近似（静态）
    # 英国
    gb_unrate   = _sfetch("LRUNTTTTGBM156S")
    gb_cpi      = _sfetch("CPALTT01GBM659N")
    gb_10y      = _sfetch("IRLTLT01GBM156N")
    gb_policy   = _sfetch("IUDSOIA")           # BoE SONIA（隔夜利率代理）
    # 印度：PMI 可得，CPI 指数需计算 YoY
    in_pmi      = _sfetch("INDPMIMANMISMEI")
    in_cpi_idx  = _sfetch("INDCPIALLMINMEI")

    # 历史低位参考（从 optim_config 读取，有则用，否则使用近5年经验值）
    try:
        from optim_config import (EU_UNRATE_HISTORICAL_LOW as EU_UNRATE_LOW,
                                  JP_UNRATE_HISTORICAL_LOW as JP_UNRATE_LOW,
                                  GB_UNRATE_HISTORICAL_LOW as GB_UNRATE_LOW,
                                  IN_PMI_EXPANSION_BENCH)
    except ImportError:
        EU_UNRATE_LOW = 6.0
        JP_UNRATE_LOW = 2.5
        GB_UNRATE_LOW = 3.7
        IN_PMI_EXPANSION_BENCH = 55.0

    eu_sc, eu_sigs = _region_score(eu_unrate, EU_UNRATE_LOW, eu_cpi, 2.0, eu_10y, eu_policy)
    jp_sc, jp_sigs = _region_score(jp_unrate, JP_UNRATE_LOW, jp_cpi, 2.0, jp_10y, jp_policy)
    gb_sc, gb_sigs = _region_score(gb_unrate, GB_UNRATE_LOW, gb_cpi, 2.0, gb_10y, gb_policy)
    # 印度：仅 PMI（数据覆盖有限）
    in_sc = 0
    in_sigs = []
    if in_pmi is not None:
        if in_pmi < 50: in_sc += 15; in_sigs.append(f"制造业PMI收缩({in_pmi:.1f})")
        elif in_pmi > 55: in_sigs.append(f"制造业PMI扩张({in_pmi:.1f})")

    def _risk_icon(s):
        if s >= 55: return "🔴"
        if s >= 35: return "🟡"
        return "🟢"

    def _fmt(v, fmt=".1f"):
        return f"{v:{fmt}}" if v is not None else "—"

    rows = [
        f"\n## 全球主要经济体衰退风险评分（{_date.today().isoformat()}）",
        "",
        "| 经济体 | 风险分 | 信号 | 失业率 | CPI | 10Y利率 |",
        "|:----|:---:|:---|:---:|:---:|:---:|",
        f"| 🇪🇺 欧元区 | {_risk_icon(eu_sc)} {eu_sc} | "
        f"{' / '.join(eu_sigs) if eu_sigs else '—'} | "
        f"{_fmt(eu_unrate)}% | {_fmt(eu_cpi)}% | {_fmt(eu_10y)}% |",
        f"| 🇯🇵 日本 | {_risk_icon(jp_sc)} {jp_sc} | "
        f"{' / '.join(jp_sigs) if jp_sigs else '—'} | "
        f"{_fmt(jp_unrate)}% | {_fmt(jp_cpi)}% | {_fmt(jp_10y)}% |",
        f"| 🇬🇧 英国 | {_risk_icon(gb_sc)} {gb_sc} | "
        f"{' / '.join(gb_sigs) if gb_sigs else '—'} | "
        f"{_fmt(gb_unrate)}% | {_fmt(gb_cpi)}% | {_fmt(gb_10y)}% |",
        f"| 🇮🇳 印度 | {_risk_icon(in_sc)} {in_sc} | "
        f"{' / '.join(in_sigs) if in_sigs else '—'} | — | — | — |",
        "",
        "> 评分方法：失业率变化(25pt)+通胀偏离(20pt)+曲线利差(20pt)+PMI(15pt)，满分100。",
        "> 数据源：FRED（OECD协调数据）。政策利率部分为近似值，仅供参考。",
    ]

    # 对美国 spillover：如果超过2个主要经济体分数>40，则提示全球同步衰退风险
    high_risk_regions = sum(1 for s in [eu_sc, jp_sc, gb_sc, in_sc] if s >= 35)
    if high_risk_regions >= 3:
        rows.append(
            f"\n⚠️ **全球同步衰退警告**：{high_risk_regions}/4个经济体风险分≥35，"
            "历史上此情形使美国衰退概率提升10-20ppt（需激活 F4 新兴市场传染回路）"
        )
    elif high_risk_regions >= 2:
        rows.append(
            f"\n🟡 **全球需求下行**：{high_risk_regions}/4个经济体风险偏高，"
            "可能削减美国出口需求，GDP预测区间左尾风险上升约5ppt。"
        )

    return "\n".join(rows)



    """
    反馈回路敏感性分析：量化每个反馈回路触发对衰退概率的边际影响。

    方法：
      - 基准MC：当前指标状态
      - 对每个 FEEDBACK_LOOP，构造"刚好触发"的最小指标扰动（trigger conditions）
      - 运行MC，记录衰退概率变化 ΔP
      - 输出排序后的敏感性表
    """
    try:
        from monte_carlo_v2 import run_monte_carlo_compat
        import copy

        regime_base, _ = detect_regime(base_indicators)
        coeffs_base    = get_coefficients(regime_base)
        mc_base        = run_monte_carlo_compat(base_indicators, coeffs_base, n_sim=n_sim)
        if not mc_base:
            return "[敏感性分析] 基准MC失败"

        base_rec = mc_base["recession_prob"]

        # 每个回路的"触发冲击"配置：{loop_name: {指标: 新值}}
        TRIGGER_SHOCKS = {
            "F1_通胀工资螺旋":  {"CPIAUCSL": {"value": 5.5},  "UNRATE": {"value": 3.8}},
            "F2_债务通缩":      {"GDPC1":    {"value": -0.5}},
            "F3_银行挤兑":      {"BAA10Y":   {"value": 3.2}},
            "F4_新兴市场传染":  {"DCOILWTICO":{"value": 135.0}},
            "F5_保证金螺旋":    {"VIXCLS":   {"value": 38.0}},
            "F6_美元流动性枯竭":{"BAA10Y":   {"value": 2.7},  "T10Y2Y": {"value": -0.6}},
            "F7_油价滞胀循环":  {"DCOILWTICO":{"value": 110.0},"CPIAUCSL": {"value": 3.8}},
            "F8_财政利率螺旋":  {"DGS10":    {"value": 4.8},  "BAA10Y": {"value": 1.8}},
        }

        results = []
        for fname, shock_vals in TRIGGER_SHOCKS.items():
            try:
                shocked = copy.deepcopy(base_indicators)
                for k, v in shock_vals.items():
                    if k in shocked:
                        shocked[k]["value"] = v["value"]
                    else:
                        shocked[k] = {"value": v["value"], "date": "2026-05-01"}

                regime_s, _ = detect_regime(shocked)
                coeffs_s    = get_coefficients(regime_s)
                mc_s        = run_monte_carlo_compat(shocked, coeffs_s, n_sim=n_sim)
                if not mc_s:
                    continue

                delta   = mc_s["recession_prob"] - base_rec
                active  = "✅" if FEEDBACK_LOOPS.get(fname, {}).get("trigger",
                          lambda x: False)(base_indicators) else "—"
                results.append((fname, mc_s["recession_prob"], delta, active))
            except Exception:
                continue

        # 按Δ降序排列
        results.sort(key=lambda x: -x[2])

        lines = [
            f"\n## 反馈回路敏感性分析（基准衰退概率：{base_rec:.1f}%）",
            "",
            "| 回路 | 触发后概率 | ΔP | 当前已激活 | 风险等级 |",
            "|:----|:--------:|:--:|:--------:|:--------:|",
        ]
        for fname, rec_s, delta, active in results:
            clean = fname.replace("_", " ")
            icon  = "🔴" if delta >= 15 else ("🟡" if delta >= 7 else "🟢")
            lines.append(f"| {clean} | {rec_s:.1f}% | {delta:+.1f}ppt | {active} | {icon} |")

        lines.append(f"\n> 触发冲击采用最小必要扰动（刚好跨越触发阈值）。n={n_sim}路径。")
        lines.append("> 🔴 ≥15ppt升幅 · 🟡 ≥7ppt · 🟢 <7ppt")
        return "\n".join(lines)
    except Exception as e:
        return f"[敏感性分析失败] {e}"


def generate_monthly_outlook(
    us_indicators: Dict,
    china_indicators: Optional[Dict],
    us_mc: Optional[Dict],
    china_mc: Optional[Dict],
    us_recession: Optional[Tuple],
    us_inflation: Optional[Tuple],
    cn_recession: Optional[Tuple],
    cn_inflation: Optional[Tuple],
    regime: str = "normal",
    spillover_text: str = "",
) -> str:
    """
    生成月度一页简报（Executive Briefing）。
    纯Python计算，无LLM调用。产出结构：
      1. 综合警戒级别（复合评分）
      2. 美中核心指标快照
      3. 活跃反馈回路 TOP-3
      4. 地缘风险快照（来自geo_events日志）
      5. 关键监控阈值红绿灯（10项）
      6. 30天关键观察日历
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    def _v(ind: Dict, key: str, default=None):
        val = ind.get(key, {}).get("value", default)
        return val if val is not None else default

    # ── 1. 综合警戒级别 ─────────────────────────────────────────────────────
    # 分量：US衰退(0-100), CN衰退(0-100), 活跃回路数(×7), Geo能源(×5)
    us_rec_score  = us_recession[1]  if us_recession  else 0
    cn_rec_score  = cn_recession[1]  if cn_recession  else 0
    us_inf_score  = us_inflation[1]  if us_inflation  else 0

    # 活跃反馈回路计数
    active_loops: List[str] = []
    try:
        combined_ind = {**us_indicators, **(china_indicators or {})} if us_indicators else (china_indicators or {})
        for fname, floop in FEEDBACK_LOOPS.items():
            try:
                if floop["trigger"](combined_ind):
                    active_loops.append(fname)
            except Exception:
                pass
    except Exception:
        pass

    # 地缘能源冲击分
    _, geo_levels = compute_geo_risk_matrix()
    geo_energy    = geo_levels.get("energy_shock", 3)
    geo_credit    = geo_levels.get("us_credit_risk", 3)
    geo_trade     = geo_levels.get("global_trade", 4)

    # 复合警戒评分（0-100）
    composite = (
        us_rec_score  * 0.25 +
        cn_rec_score  * 0.20 +
        us_inf_score  * 0.15 +
        len(active_loops) / 8 * 100 * 0.15 +
        (geo_energy + geo_credit + geo_trade) / 30 * 100 * 0.25
    )
    composite = min(100, max(0, composite))

    if composite >= 80:
        alert_icon, alert_label = "⛔", f"极高警戒 ({composite:.0f}/100)"
    elif composite >= 65:
        alert_icon, alert_label = "🔴", f"高警戒 ({composite:.0f}/100)"
    elif composite >= 50:
        alert_icon, alert_label = "🟠", f"中高警戒 ({composite:.0f}/100)"
    elif composite >= 35:
        alert_icon, alert_label = "🟡", f"中等警戒 ({composite:.0f}/100)"
    else:
        alert_icon, alert_label = "🟢", f"低警戒 ({composite:.0f}/100)"

    regime_zh = {"normal": "常态", "stress": "压力", "crisis": "危机"}.get(regime, regime)

    lines = [
        f"# 月度宏观简报（Executive Briefing）",
        f"> 生成时间：{now_str}　|　体制状态：**{regime_zh}**　|　综合警戒：{alert_icon} **{alert_label}**",
        "",
    ]

    # ── 2. 美中核心指标快照 ───────────────────────────────────────────────────
    lines.append("## 一、美中核心指标快照")
    lines.append("")
    lines.append("| 指标 | 美国 | 中国 | 说明 |")
    lines.append("|:----|:---:|:---:|:-----|")

    def _fmt(v, suffix="", dec=2):
        return f"{v:.{dec}f}{suffix}" if v is not None else "—"

    cn_ind = china_indicators or {}

    cpi_us  = _v(us_indicators, "CPIAUCSL")
    cpi_cn  = _v(cn_ind, "cpi")
    ppi_us  = _v(us_indicators, "PPIACO")
    ppi_cn  = _v(cn_ind, "ppi")
    gdp_us  = _v(us_indicators, "GDPC1")
    gdp_cn  = _v(cn_ind, "gdp_growth")
    unr_us  = _v(us_indicators, "UNRATE")
    unr_cn  = _v(cn_ind, "unemployment")
    pmi_us  = _v(us_indicators, "MANEMP") or _v(us_indicators, "PAYEMS")
    pmi_cn  = _v(cn_ind, "pmi_mfg")
    oil     = _v(us_indicators, "DCOILWTICO")
    dgs10   = _v(us_indicators, "DGS10")
    vix     = _v(us_indicators, "VIXCLS")
    baa     = _v(us_indicators, "BAA10Y")
    ffr     = _v(us_indicators, "DFF") or _v(us_indicators, "FEDFUNDS")
    lpr_cn  = _v(cn_ind, "lpr_1y")
    m2_cn   = _v(cn_ind, "m2_growth")

    rows_snap = [
        ("CPI同比(%)",   _fmt(cpi_us, "%"), _fmt(cpi_cn, "%"), "美国通胀持续高企，中国轻度通缩"),
        ("PPI同比(%)",   _fmt(ppi_us, "%"), _fmt(ppi_cn, "%"), "美国上游压力，中国PPI持续收缩"),
        ("GDP增速(%)",   _fmt(gdp_us, "%"), _fmt(gdp_cn, "%"), "两国均低于潜在增速"),
        ("失业率(%)",    _fmt(unr_us, "%"), _fmt(unr_cn, "%", dec=1), "美国接近NAIRU"),
        ("制造业PMI",    "—",               _fmt(pmi_cn, "", dec=1), "中国制造业轻度收缩"),
        ("政策利率(%)",  _fmt(ffr, "%"),    _fmt(lpr_cn, "%(LPR)"), "美中利差已倒置"),
        ("M2增速(%)",    "—",               _fmt(m2_cn, "%"), "中国M2增速但实体信贷弱"),
        ("WTI原油($/桶)",_fmt(oil, "$"),    "—", "能源成本推通胀"),
        ("10Y美债(%)",   _fmt(dgs10, "%"),  "—", "含~20bp信用溢价"),
        ("VIX恐慌指数",  _fmt(vix, "", dec=1),"—", ">30为市场恐慌"),
    ]
    for row in rows_snap:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")

    # 风险评分行
    lines.append("")
    us_rl  = us_recession[0]  if us_recession  else "—"
    us_rs  = us_recession[1]  if us_recession  else 0
    cn_rl  = cn_recession[0]  if cn_recession  else "—"
    cn_rs  = cn_recession[1]  if cn_recession  else 0
    us_il  = us_inflation[0]  if us_inflation  else "—"
    us_is  = us_inflation[1]  if us_inflation  else 0
    cn_il  = cn_inflation[0]  if cn_inflation  else "—"
    cn_is  = cn_inflation[1]  if cn_inflation  else 0
    us_rp  = f"{us_mc['recession_prob']:.1f}%" if us_mc else "—"
    cn_rp  = f"{china_mc['recession_prob']:.1f}%" if china_mc else "—"
    us_gm  = f"{us_mc['gdp']['mean']:.2f}%" if us_mc else "—"
    cn_gm  = f"{china_mc['gdp']['mean']:.2f}%" if china_mc else "—"

    lines.append("**风险评分**")
    lines.append("")
    lines.append("| 评分维度 | 美国 | 中国 |")
    lines.append("|:--------|:---:|:---:|")
    lines.append(f"| 衰退风险（加权）| {us_rl} {us_rs}/100 | {cn_rl} {cn_rs}/100 |")
    lines.append(f"| 通胀/通缩风险   | {us_il} {us_is}/100 | {cn_il} {cn_is}/100 |")
    lines.append(f"| MC衰退概率      | {us_rp} | {cn_rp} |")
    lines.append(f"| MC GDP 12M均值  | {us_gm} | {cn_gm} |")

    # ── 3. 活跃反馈回路 TOP-3 ─────────────────────────────────────────────────
    lines.append("")
    lines.append("## 二、活跃反馈回路（优先级排序）")
    lines.append("")

    LOOP_PRIORITY = {
        "F7_油价滞胀循环": 1, "F8_财政利率螺旋": 2,
        "F2_债务通缩": 3, "F1_通胀工资螺旋": 4,
        "F6_美元流动性枯竭": 5, "F3_银行挤兑": 6,
        "F4_新兴市场传染": 7, "F5_保证金螺旋": 8,
    }
    LOOP_DESC = {
        "F7_油价滞胀循环": "WTI>100+CPI>3% → 供给侧通胀 → 联储两难 → 需求压制",
        "F8_财政利率螺旋": "DGS10>4.5%+信用溢价↑ → 利息支出↑ → 赤字扩大 → 评级压力",
        "F2_债务通缩": "GDP<0 → 债务实际负担加重 → 信贷收缩 → GDP进一步下滑",
        "F1_通胀工资螺旋": "CPI>5%+失业率<4% → 工资上涨 → 通胀持续 → 加息循环",
        "F6_美元流动性枯竭": "信用利差>2.5%+收益曲线倒挂 → 银行间流动性收紧",
        "F3_银行挤兑": "BAA利差>3% → 银行资产减值 → 挤兑风险",
        "F4_新兴市场传染": "WTI>130$ → 输入性通胀 → EM货币危机",
        "F5_保证金螺旋": "VIX>35 → 强制平仓 → 资产抛售加速",
    }

    sorted_active = sorted(active_loops, key=lambda x: LOOP_PRIORITY.get(x, 99))
    if sorted_active:
        for i, fname in enumerate(sorted_active[:5], 1):
            desc = LOOP_DESC.get(fname, "")
            clean = fname.replace("_", " ")
            lines.append(f"**{i}. 🔴 {clean}**  ")
            lines.append(f"   {desc}")
            lines.append("")
    else:
        lines.append("> 当前无活跃反馈回路。宏观系统相对稳定。")
        lines.append("")

    if len(active_loops) < len(FEEDBACK_LOOPS):
        dormant = [x for x in FEEDBACK_LOOPS if x not in active_loops]
        lines.append(f"*休眠（{len(dormant)}）*：{', '.join(x.replace('_', ' ') for x in dormant[:4])}{'...' if len(dormant)>4 else ''}")
        lines.append("")

    # ── 4. 地缘风险快照 ───────────────────────────────────────────────────────
    lines.append("## 三、地缘风险快照")
    lines.append("")

    GEO_THRESHOLDS = {
        "taiwan_strait": (5, 7), "tech_decoupling": (6, 8),
        "global_trade": (6, 8), "energy_shock": (7, 9),
        "us_credit_risk": (6, 8), "fx_pressure": (6, 8),
        "yen_carry_unwind": (6, 8),
    }
    GEO_LABELS = {
        "taiwan_strait": "台海局势", "tech_decoupling": "科技脱钩",
        "global_trade": "全球贸易", "energy_shock": "能源冲击",
        "us_credit_risk": "美债信用", "fx_pressure": "汇率压力",
        "yen_carry_unwind": "日元套利",
    }
    geo_table_md, _ = compute_geo_risk_matrix()

    lines.append("| 维度 | 评分 | 状态 |")
    lines.append("|:----|:---:|:-----|")
    for dim, label in GEO_LABELS.items():
        lv = geo_levels.get(dim)
        if lv is None:
            continue
        warn, crit = GEO_THRESHOLDS.get(dim, (6, 8))
        if lv >= crit:
            icon = "🔴"
        elif lv >= warn:
            icon = "🟡"
        else:
            icon = "🟢"
        lines.append(f"| {label} | {lv}/10 | {icon} |")
    lines.append("")

    # 最高风险维度提示
    if geo_levels:
        top_dim = max(geo_levels, key=lambda d: geo_levels[d])
        top_lv = geo_levels[top_dim]
        top_label = GEO_LABELS.get(top_dim, top_dim)
        if top_lv >= 7:
            lines.append(f"> **主要地缘风险**：{top_label}（{top_lv}/10）是当前最高风险维度，需重点监控。")
            lines.append("")

    # ── 5. 关键阈值红绿灯 ─────────────────────────────────────────────────────
    lines.append("## 四、关键监控阈值（当前状态）")
    lines.append("")
    lines.append("| 指标 | 当前值 | 警戒阈值 | 状态 | 含义 |")
    lines.append("|:----|:-----:|:-------:|:----:|:----|")

    def _tl(val, warn, crit, higher_is_worse=True, fmt=".2f", suffix=""):
        if val is None:
            return "⚪ 数据缺失"
        if higher_is_worse:
            if val >= crit:   return "🔴 超阈值"
            if val >= warn:   return "🟡 接近阈值"
            return "🟢 正常"
        else:
            if val <= crit:   return "🔴 超阈值"
            if val <= warn:   return "🟡 接近阈值"
            return "🟢 正常"

    def _fv(val, fmt=".2f", suffix=""):
        return f"{val:{fmt}}{suffix}" if val is not None else "—"

    wti     = _v(us_indicators, "DCOILWTICO")
    vix_v   = _v(us_indicators, "VIXCLS")
    dgs10_v = _v(us_indicators, "DGS10")
    baa_v   = _v(us_indicators, "BAA10Y")
    cpi_v   = _v(us_indicators, "CPIAUCSL")
    pce_v   = _v(us_indicators, "PCEPI")
    sahm_v  = us_indicators.get("SAHM_RULE", {}).get("value")
    t10y2y_v= _v(us_indicators, "T10Y2Y")
    ppi_v   = _v(us_indicators, "PPIACO")

    thresholds = [
        ("WTI原油($/桶)",       wti,      100, 120,  True,  ".0f", "$",  "能源冲击临界→通胀加速"),
        ("VIX恐慌指数",         vix_v,     25,  35,  True,  ".1f", "",   "市场压力→流动性收紧"),
        ("10Y美债(%)",          dgs10_v,   4.5, 5.0, True,  ".2f", "%",  "财政成本临界→信用风险"),
        ("BAA信用利差(%)",      baa_v,     2.0, 2.5, True,  ".2f", "%",  "银行信贷收紧→融资困难"),
        ("CPI同比(%)",          cpi_v,     3.5, 4.5, True,  ".2f", "%",  "二次通胀确认→联储两难"),
        ("核心PCE(%)",          pce_v,     3.0, 3.5, True,  ".2f", "%",  "联储关键目标锚"),
        ("PPI同比(%)",          ppi_v,     7.0, 10.0,True,  ".2f", "%",  "上游通胀待传导→CPI↑"),
        ("萨姆规则",            sahm_v,    0.3, 0.5, True,  ".3f", "",   "≥0.5触发衰退信号"),
        ("10Y-2Y利差(%)",       t10y2y_v, -0.5,-0.8, False, ".2f", "%",  "倒挂→衰退先行指标"),
        ("中国CPI(%)",          cpi_cn,   -0.5,-1.0, False, ".2f", "%",  "通缩加深→需求萎缩"),
    ]

    for name, val, warn, crit, hiw, fmt, sfx, meaning in thresholds:
        cur_str = _fv(val, fmt, sfx)
        # warn_str depends on direction
        if hiw:
            warn_str = f"{warn}{sfx}"
        else:
            warn_str = f"{warn}{sfx}"
        status = _tl(val, warn, crit, hiw, fmt, sfx)
        lines.append(f"| {name} | {cur_str} | {warn_str} | {status} | {meaning} |")

    lines.append("")

    # 快速统计
    red_count    = sum(1 for t in thresholds if _tl(t[1], t[2], t[3], t[4]) == "🔴 超阈值")
    yellow_count = sum(1 for t in thresholds if _tl(t[1], t[2], t[3], t[4]) == "🟡 接近阈值")
    lines.append(f"> **阈值状态**：🔴 超阈值 {red_count} 项　🟡 接近阈值 {yellow_count} 项　（共10项监控）")
    lines.append("")

    # ── 6. 30天关键观察日历 ────────────────────────────────────────────────────
    lines.append("## 五、30天关键观察日历")
    lines.append("")
    lines.append("| 时间 | 事件 | 关键问题 | 资产影响 |")
    lines.append("|:----|:----|:--------|:--------|")

    # 基于2026-05的固定事件（会随日历变化，此处为当前估算）
    calendar_events = [
        ("2026-06初",  "OPEC+ 6月产量会议",
         "是否维持减产？增产信号vs延续",
         "增产→WTI↓$10+，通胀缓和；维持减产→能源压力延续"),
        ("2026-06中",  "美联储FOMC会议（6月）",
         "是否暂停/加息？点阵图更新",
         "加息25bp→美元↑，股市↓，中国汇率压力↑"),
        ("2026-06",    "美国6月国债拍卖（30Y）",
         "覆盖率是否 <2.0x？外国买家撤退",
         "<2.0x触发10Y收益率上行10-20bp，信用溢价扩大"),
        ("2026-06",    "日本央行6/7月会议",
         "是否加息10-25bp？日元套利平仓风险",
         "加息→USD/JPY↓→日元套利仓位平仓→全球风险资产短暂冲击"),
        ("持续",       "特朗普访华后续落地",
         "关税减免幅度？芯片管制松动？能源采购协议？",
         "实质减免关税→A股+5%~10%，CNY升值1-2%"),
        ("2026-06",    "美国消费者信心（密歇根）",
         "是否跌破50？（当前53.3）",
         "<50确认消费下滑→衰退概率+5-10ppt"),
        ("2026-07初",  "美国非农就业报告",
         "失业率是否升破4.3%？萨姆规则更新",
         "失业率>4.3%→萨姆规则接近0.5触发→降息预期重燃"),
    ]

    for date, event, question, impact in calendar_events:
        lines.append(f"| {date} | {event} | {question} | {impact} |")

    lines.append("")

    # ── 6. 全球主要经济体风险概览 ─────────────────────────────────────────────
    try:
        global_risk_md = score_global_recession_risk()
        if global_risk_md:
            lines.append("## 六、全球主要经济体风险概览")
            lines.append("")
            # 只提取表格行和概览警告（去掉冗余的 ## 标题）
            for gline in global_risk_md.split("\n"):
                if gline.startswith("##"):
                    continue  # 跳过次级标题，避免嵌套混乱
                lines.append(gline)
    except Exception:
        pass

    # ── 尾注 ──────────────────────────────────────────────────────────────────
    lines.append("---")
    lines.append(f"*本简报由 `generate_monthly_outlook()` 自动生成 · {now_str}*")
    lines.append(f"*数据来源：FRED API + 本地知识库 · 体制：{regime_zh} · 活跃回路：{len(active_loops)}/8*")

    return "\n".join(lines)


# ── 知识库新鲜度检查 ────────────────────────────────────────────────────────────
def _check_kb_freshness(stale_days: int = 180) -> None:
    """扫描专题报告目录，对超过 stale_days 天未修改的 .md 文件发出提示。"""
    report_dir = os.path.join(KB_DIR, "专题报告")
    if not os.path.isdir(report_dir):
        return
    from datetime import timedelta
    cutoff = datetime.now().timestamp() - stale_days * 86400
    stale = []
    for fname in sorted(os.listdir(report_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(report_dir, fname)
        mtime = os.path.getmtime(fpath)
        if mtime < cutoff:
            age_days = int((datetime.now().timestamp() - mtime) / 86400)
            stale.append((age_days, fname))
    if stale:
        sep = "─" * 56
        print(f"\n{sep}")
        print(f"  [知识库提示] 以下 {len(stale)} 篇报告超过 {stale_days} 天未更新：")
        for age, fname in stale:
            print(f"    {age:4d}天  {fname}")
        print(f"  建议在下次分析前更新上述报告。")
        print(f"{sep}\n")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="实时宏观分析脚本")
    parser.add_argument("--topic", type=str, default="综合",
                        choices=["综合", "衰退", "通胀", "市场", "地缘"],
                        help="分析主题")
    parser.add_argument("--depth", type=str, default="standard",
                        choices=["quick", "standard", "deep"],
                        help="分析深度")
    parser.add_argument("--country", type=str, default="us",
                        choices=["us", "china", "both"],
                        help="分析国家")
    parser.add_argument("--reasoning", type=str, default="auto",
                        choices=["local", "claude", "auto", "claudecode", "openai"],
                        help="推理模式：auto=MiMo优先+SiliconFlow降级（默认），local=SiliconFlow，claude=Claude API，openai=OpenAI兼容端点，claudecode=通过Claude Code交互")
    parser.add_argument("--force", action="store_true",
                        help="强制重跑，跳过幂等检查（手动触发时使用）")
    parser.add_argument("--scenario", type=str, default=None,
                        choices=list(SCENARIOS.keys()),
                        help="压力测试情景：stress_energy/stress_recession/stress_credit")
    parser.add_argument("--compare-scenarios", action="store_true",
                        help="一次性对比所有压力情景衰退概率（追加到报告）")
    parser.add_argument("--sensitivity", action="store_true",
                        help="反馈回路敏感性分析：量化各回路对衰退概率的边际影响")
    parser.add_argument("--backtest", action="store_true",
                        help="回测验证：检查到期预测记录并计算准确率")
    parser.add_argument("--rolling-accuracy", action="store_true",
                        help="滚动精度报告：计算近6个月预测命中率、MAE、体制条件准确率（不重新验证）")
    parser.add_argument("--global-risk", action="store_true",
                        help="全球风险扫描：计算欧元区/日本/英国/印度衰退风险评分并评估对美国的溢出效应")
    parser.add_argument("--assess-structure", action="store_true",
                        help="结构层评估：调用LLM对政治/社会/技术/气候四维度打分，更新structural_priors.json")
    parser.add_argument("--force-structure", action="store_true",
                        help="配合 --assess-structure：强制重评（忽略有效期）")

    # 假设推演与压力测试互斥（两者路径完全不同）
    _hyp_group = parser.add_mutually_exclusive_group()
    _hyp_group.add_argument("--hypothesis", type=str, default=None,
                        help="假设推演：自然语言情景输入，如 \"台海军事冲突升级\" 或 \"台海+油价\"；"
                             "不计入预测校验，严格与 --scenario 互斥")
    parser.add_argument("--hypothesis-severity", type=str, default=None,
                        choices=["L1", "L2", "L3"],
                        help="与 --hypothesis 联用，覆盖自动检测的烈度级别（L1/L2/L3）")

    args = parser.parse_args()

    # 假设推演模式（独立运行，不执行标准分析流程）
    if getattr(args, "hypothesis", None):
        from hypothesis_engine import run_hypothesis
        from optim_config import ensure_dirs
        ensure_dirs()
        _lock_fd = _acquire_lock()
        if _lock_fd is None:
            sys.exit(0)
        try:
            # 拉取实时指标（假设推演需要当前数据作背景参考）
            print("[假设推演] 拉取实时背景指标...")
            try:
                _hyp_ind = get_current_snapshot()
            except Exception as _e:
                print(f"  [WARN] 指标拉取失败，使用空字典: {_e}")
                _hyp_ind = {}

            def _push_hypothesis(title: str, body: str, filename: str = None):
                """ntfy 推送假设推演报告。"""
                _ntfy_topic = os.environ.get("NTFY_TOPIC", "")
                if not _ntfy_topic:
                    return
                try:
                    _title_safe = title.encode("utf-8").decode("latin-1")
                    if filename and os.path.exists(filename):
                        _fname_safe = Path(filename).name.encode("utf-8").decode("latin-1")
                        with open(filename, "rb") as _f:
                            requests.put(
                                f"https://ntfy.sh/{_ntfy_topic}",
                                data=_f.read(),
                                headers={
                                    "Title": _title_safe,
                                    "Filename": _fname_safe,
                                    "Message": "\u200b".encode("utf-8").decode("latin-1"),
                                    "Content-Type": "text/markdown; charset=utf-8",
                                },
                                proxies=None,
                                timeout=60,
                            )
                    else:
                        requests.post(
                            f"https://ntfy.sh/{_ntfy_topic}",
                            json={"title": title, "message": body[:4000]},
                            proxies=None,
                            timeout=30,
                        )
                except Exception as _pe:
                    print(f"[WARN] ntfy 推送失败: {_pe}")

            result = run_hypothesis(
                hypothesis_text=args.hypothesis,
                indicators=_hyp_ind,
                rag_query_fn=rag_query,
                call_llm_fn=call_llm_primary,
                push_fn=_push_hypothesis,
                depth=getattr(args, "depth", "standard"),
                severity_override=getattr(args, "hypothesis_severity", None),
            )
            print("\n" + "=" * 60)
            print("[假设推演] 完成！")
            print("=" * 60)
            print(f"报告文件：{result['filename']}")
            print(f"情景：{result['scenario']['label']}  烈度：{result['scenario']['severity']}")
        finally:
            _release_lock(_lock_fd)
        sys.exit(0)

    # 回测模式：独立运行，不执行正常分析
    if args.backtest:
        _run_backtest()
        sys.exit(0)

    # 全球风险扫描（独立模式）
    if getattr(args, "global_risk", False):
        print(score_global_recession_risk())
        sys.exit(0)

    # 结构层评估（独立模式）
    if getattr(args, "assess_structure", False):
        try:
            from assess_structural_dimensions import run_assessment
            run_assessment(force=getattr(args, "force_structure", False))
        except ImportError as e:
            print(f"[结构评估] 模块导入失败: {e}")
        sys.exit(0)

    # 滚动精度报告（独立模式）
    if getattr(args, "rolling_accuracy", False):
        print(compute_rolling_accuracy_report(window_months=6))
        sys.exit(0)

    # 启动时确保目录存在（避免 optim_config import 时副作用）
    from optim_config import ensure_dirs
    ensure_dirs()

    # 启动时清理过期错误日志和旧报告
    _cleanup_error_log(max_days=30)
    _cleanup_old_reports(keep_days=30)

    # 并发锁：防止 cron 触发重叠
    _lock_fd = _acquire_lock()
    if _lock_fd is None:
        sys.exit(0)

    # 知识库新鲜度检查（不阻断运行，只提示）
    _check_kb_freshness(stale_days=180)

    try:
        result = run_macro_analysis(topic=args.topic, depth=args.depth, country=args.country, reasoning=args.reasoning, force=args.force)

        if result.get("idempotent_skip"):
            print("\n" + "=" * 60)
            print("[IDEMPOTENT] 今日已有报告，跳过重复执行")
            print("=" * 60)
            print(f"已有报告：{result['filename']}")
        else:
            print("\n" + "=" * 60)
            print("分析完成！")
            print("=" * 60)
            print(f"报告文件：{result['filename']}")
            if result.get("outlook_filename"):
                print(f"月度简报：{result['outlook_filename']}")

            # 压力测试（如果指定）
            if args.scenario:
                base_ind = result.get("indicators", {})
                if base_ind:
                    print(f"\n[压力测试] 开始运行情景：{args.scenario}")
                    stress_summary = run_stress_test(base_ind, args.scenario)
                    print(stress_summary)
                    # 追加到报告文件
                    filename = result.get("filename", "")
                    if filename and os.path.exists(filename):
                        with open(filename, "a", encoding="utf-8") as f:
                            f.write("\n\n---\n")
                            f.write(stress_summary)
                            f.write("\n")
                        print(f"压力测试结果已追加至：{filename}")

            # 全情景对比
            if getattr(args, "compare_scenarios", False):
                base_ind = result.get("indicators", {})
                if base_ind:
                    print(f"\n[情景对比] 开始比较所有情景...")
                    compare_table = compare_all_scenarios(base_ind)
                    print(compare_table)
                    filename = result.get("filename", "")
                    if filename and os.path.exists(filename):
                        with open(filename, "a", encoding="utf-8") as f:
                            f.write("\n\n---\n")
                            f.write(compare_table)
                            f.write("\n")
                        print(f"情景对比已追加至：{filename}")

            # 反馈回路敏感性分析
            if getattr(args, "sensitivity", False):
                base_ind = result.get("indicators", {})
                if base_ind:
                    print(f"\n[敏感性分析] 开始计算反馈回路边际影响...")
                    sensitivity_table = compute_feedback_sensitivity(base_ind)
                    print(sensitivity_table)
                    filename = result.get("filename", "")
                    if filename and os.path.exists(filename):
                        with open(filename, "a", encoding="utf-8") as f:
                            f.write("\n\n---\n")
                            f.write(sensitivity_table)
                            f.write("\n")
                        print(f"敏感性分析已追加至：{filename}")

            print(f"\n简报预览：\n")
            print(result["report"][:500] + "...")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _log_error(args.country, args.depth, args.topic, str(e), tb)
        print(f"\n[FATAL] 分析失败: {e}")
        print(f"[FATAL] 错误已记录到 {os.path.join(LOG_DIR, 'analysis_errors.log')}")
        raise SystemExit(1)
    finally:
        _release_lock(_lock_fd)
