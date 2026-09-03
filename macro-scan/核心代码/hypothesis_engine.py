"""
假设推演引擎 — M0 基线实现
Step 0: 情景解析 + scenario_wiki 检索
Step 3B: 历史类比（基于 calibrate_mc.py 13条危机数据）
Step 4B: 按情景类型强制 RAG 查询
Step 6B: 构建假设模式 LLM 提示词
Step 8B: 保存推演报告（严格不入预测库）
Step 9:  异步 Wiki 编译（daemon thread）
"""

import os
import re
import uuid
import logging
import hashlib
import threading
import datetime
from pathlib import Path
from typing import Optional

import yaml

# ── 路径常量 ─────────────────────────────────────────────────
_HERE = Path(__file__).parent
TEMPLATES_FILE = _HERE / "hypothesis_templates.yaml"
SYSTEM_PROMPT_FILE = _HERE / "system_prompt_hypothesis.md"

WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", "/workspace"))
REPORT_DIR = WORKSPACE / "docs" / "分析报告"
WIKI_FILE  = WORKSPACE / "data" / "scenario_wiki.md"
LOG_DIR    = Path("/var/log/macro-scan")
LOG_FILE   = LOG_DIR / "hypothesis.log"

# ── 日志 ─────────────────────────────────────────────────────
def _get_wiki_logger():
    logger = logging.getLogger("hypothesis_wiki")
    if not logger.handlers:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        h = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger

# ── 模板加载 ─────────────────────────────────────────────────
_templates_cache = None
_templates_mtime = 0.0
_wiki_lock = threading.Lock()  # HYP-4: wiki 文件追加写入锁，防止并发条目交错

def _load_templates() -> dict:
    global _templates_cache, _templates_mtime
    try:
        mtime = TEMPLATES_FILE.stat().st_mtime
        if _templates_cache is None or mtime != _templates_mtime:
            with open(TEMPLATES_FILE, encoding="utf-8") as f:
                _templates_cache = yaml.safe_load(f)
            _templates_mtime = mtime
    except Exception as e:
        logging.warning(f"[HYP] 模板加载失败: {e}，使用空模板")
        _templates_cache = _templates_cache or {}
    return _templates_cache or {}


# ── ScenarioParser ────────────────────────────────────────────
class ScenarioParser:
    """
    将自然语言输入解析为标准化情景对象。
    支持：别名快速映射 + 关键词匹配 + 烈度词检测
    """

    def __init__(self):
        self.templates = _load_templates()

    def parse(self, text: str, severity_override: Optional[str] = None) -> dict:
        text_lower = text.strip()
        aliases = self.templates.get("aliases", {})

        # 1. 别名精确匹配
        for alias, info in aliases.items():
            if alias in text_lower:
                sev = severity_override or info.get("severity", "L2")
                result = {
                    "scenario_type": info["type"],
                    "subtype":       info.get("subtype", ""),
                    "severity":      sev,
                    "label":         info["label"],
                    "raw_input":     text,
                    "confidence":    0.95,
                }
                return self._enrich(result)

        # 2. 关键词分类匹配
        categories = self.templates.get("categories", {})
        scores = {}
        for cat_code, cat_info in categories.items():
            kws_zh = cat_info.get("keywords_zh", [])
            kws_en = [k.lower() for k in cat_info.get("keywords_en", [])]
            hits = sum(1 for kw in kws_zh if kw in text_lower)
            hits += sum(1 for kw in kws_en if kw in text_lower.lower())
            if hits:
                scores[cat_code] = hits

        # 3. 烈度检测
        severity_params = self.templates.get("severity_params", {})
        detected_sev = None
        for sev_code, sev_info in severity_params.items():
            for kw in sev_info.get("keywords", []):
                if kw.lower() in text_lower.lower():
                    detected_sev = sev_code
                    break

        severity = severity_override or detected_sev or "L2"

        if scores:
            best_cat = max(scores, key=lambda k: scores[k])
            confidence = min(0.9, 0.5 + scores[best_cat] * 0.1)
            result = {
                "scenario_type": best_cat,
                "subtype":       "GENERAL",
                "severity":      severity,
                "label":         text[:60],
                "raw_input":     text,
                "confidence":    confidence,
            }
            return self._enrich(result)

        # 4. 兜底
        return {
            "scenario_type": "GEO",
            "subtype":       "UNKNOWN",
            "severity":      severity,
            "label":         text[:60],
            "raw_input":     text,
            "confidence":    0.3,
            "synergies":     [],
            "is_compound":   False,
            "components":    [],
        }

    def parse_compound(self, text: str, severity_override: str = None) -> dict:
        """解析组合情景（用 + 分隔，最多3个）。"""
        parts = [p.strip() for p in text.split("+")][:3]
        if len(parts) == 1:
            result = self.parse(parts[0], severity_override=severity_override)
            result["is_compound"] = False
            result["components"] = []
            return result

        components = [self.parse(p, severity_override=severity_override) for p in parts]
        primary = components[0]
        primary["is_compound"] = True
        primary["components"] = components[1:]
        primary["label"] = " + ".join(c["label"] for c in components)
        primary["synergies"] = self._check_synergies(components)
        return primary

    def _enrich(self, result: dict) -> dict:
        result.setdefault("synergies", [])
        result.setdefault("is_compound", False)
        result.setdefault("components", [])
        return result

    def _check_synergies(self, components: list) -> list:
        rules = self.templates.get("synergy_rules", [])
        types = [c["scenario_type"] for c in components]
        matched = []
        for rule in rules:
            if rule["primary"] in types and rule["secondary"] in types:
                matched.append(rule.get("note", ""))
        return matched


# ── scenario_wiki 操作 ────────────────────────────────────────
def load_wiki_entries() -> list:
    if not WIKI_FILE.exists():
        return []
    content = WIKI_FILE.read_text(encoding="utf-8")
    entries = []
    blocks = re.split(r'\n(?=## [A-Z])', content)
    for block in blocks:
        block = block.strip()
        if block.startswith("## "):
            entries.append(block)
    return entries


def search_wiki(scenario: dict, max_results: int = 3) -> list:
    """关键词匹配检索 scenario_wiki（M0，无 ChromaDB）。"""
    entries = load_wiki_entries()
    if not entries:
        return []

    stype = scenario.get("scenario_type", "")
    label = scenario.get("label", "")
    raw   = scenario.get("raw_input", "")

    keywords = set()
    keywords.add(stype)
    keywords.update(w for w in re.findall(r'[一-鿿]{2,}|[A-Z]{2,}', label + " " + raw))

    scored = []
    for entry in entries:
        score = sum(1 for kw in keywords if kw in entry)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:max_results]]


# ── 历史危机类比（Step 3B）────────────────────────────────────
def get_historical_analogies(scenario: dict) -> dict:
    try:
        import sys
        sys.path.insert(0, str(_HERE))
        from calibrate_mc import load_historical_scenarios
        import numpy as np
    except ImportError as e:
        logging.warning(f"[HYP] calibrate_mc 导入失败: {e}")
        return {"best": None, "second": None, "impacts": {}, "raw": []}

    scenarios = load_historical_scenarios()
    stype = scenario.get("scenario_type", "")
    severity = scenario.get("severity", "L2")

    # 引用模块级常量（已提升，消除了原先 TRADE/CRISIS 双重赋值 bug）
    type_field_kws = TYPE_FIELD_MAP.get(stype, [])
    priority_kws = TYPE_KEYWORDS.get(stype, [])

    rated = []
    for s in scenarios:
        name = s.get("name", "")
        lessons = s.get("lessons", "")
        crisis_type = s.get("crisis_category", "")
        score = sum(1 for kw in priority_kws if kw in name or kw in lessons)
        score += sum(1 for kw in type_field_kws if kw in name or kw in lessons)

        # crisis_category 直接命中加分
        cat_score_map = {
            "GEO":    ["geopolitical_standoff", "military_conflict",
                       "large_scale_invasion", "territorial_annexation",
                       "terrorist_attack", "non_state_conflict"],
            "FIN":    ["financial_crisis", "banking_crisis"],
            "ENERGY": ["revolution_energy", "energy_shock", "political_instability"],
            "TRADE":  ["trade_tech_war", "sanctions_asymmetric"],
            "MACRO":  ["monetary_tightening", "debt_crisis"],
            "CRISIS": ["pandemic", "systemic_crisis"],
        }
        if crisis_type in cat_score_map.get(stype, []):
            score += 3

        # 台海情景额外加权（TAIWAN子类型 tw_rel ×2，GENERAL ×1）
        tw_rel = s.get("taiwan_strait_relevance", 0)
        if stype == "GEO" and scenario.get("subtype") == "TAIWAN":
            score += tw_rel * 2
        elif stype == "GEO" and scenario.get("subtype") == "GENERAL":
            score += tw_rel

        rated.append((score, s))
    rated.sort(key=lambda x: x[0], reverse=True)

    # CSV 中 sp500_drawdown_pct 部分条目存的是回撤绝对值（正数），统一取负
    def _to_drawdown(v):
        return v if v < 0 else -v

    sp500_vals = [_to_drawdown(s["sp500"]) for s in scenarios if s.get("sp500") is not None]
    # 优先用 CSV 真实 vix_peak，无则退回 sp500×0.8 估算
    vix_vals = [s["vix_peak"] for s in scenarios if s.get("vix_peak") is not None]
    if not vix_vals:
        vix_vals = [abs(v) * 0.8 for v in sp500_vals]
    gdp_vals   = [s["gdp_drop"] for s in scenarios if s.get("gdp_drop") is not None]

    if severity == "L4":
        # L4 极端尾部（核冲突/全球大疫等）无历史样本：对历史类比 percentile 做
        # 系数外推属伪精确，禁用（ADR-0014）。输出固定情景假设区间（专家判断，
        # 非历史校准）；后续完整方案=概率型/情景型分组推演（backlog P3）。
        impacts = {
            "spx_pct":   {"p10": -60.0, "p50": -45.0, "p90": -30.0,
                          "source": "L4情景假设（非历史校准）"},
            "vix_delta": {"p10": 50.0, "p50": 70.0, "p90": 90.0,
                          "source": "L4情景假设（非历史校准）"},
            "gdp_pct":   {"p10": -30.0, "p50": -20.0, "p90": -10.0,
                          "source": "L4情景假设（非历史校准）"},
        }
    else:
        severity_mult = {"L1": 0.5, "L2": 1.0, "L3": 1.8}.get(severity, 1.0)

        impacts = {}
        if sp500_vals:
            impacts["spx_pct"] = {
                "p10": round(float(np.percentile(sp500_vals, 10)) * severity_mult, 1),
                "p50": round(float(np.percentile(sp500_vals, 50)) * severity_mult, 1),
                "p90": round(float(np.percentile(sp500_vals, 90)) * severity_mult, 1),
                "source": "历史类比（非MC）",
            }
        if vix_vals:
            impacts["vix_delta"] = {
                "p10": round(float(np.percentile(vix_vals, 10)) * severity_mult, 1),
                "p50": round(float(np.percentile(vix_vals, 50)) * severity_mult, 1),
                "p90": round(float(np.percentile(vix_vals, 90)) * severity_mult, 1),
                "source": "历史类比（非MC）",
            }
        if gdp_vals:
            impacts["gdp_pct"] = {
                "p10": round(float(np.percentile(gdp_vals, 10)) * severity_mult, 1),
                "p50": round(float(np.percentile(gdp_vals, 50)) * severity_mult, 1),
                "p90": round(float(np.percentile(gdp_vals, 90)) * severity_mult, 1),
                "source": "历史类比（非MC）",
            }

    best   = rated[0][1] if len(rated) > 0 else None
    second = rated[1][1] if len(rated) > 1 else None

    return {
        "best":         best["name"] if best else None,
        "best_lessons": best["lessons"] if best else "",
        "second":       second["name"] if second else None,
        "impacts":      impacts,
        "raw":          [s for _, s in rated[:5]],
    }


# ── 传导路径库检索（Step 4B 前置）────────────────────────────
# ── 模块级常量：历史类比类型映射 ─────────────────────────────────────────────
# type_field_map：CSV type 字段关键词（用于场景→历史案例的字段级匹配）
# 原先定义在 get_historical_analogies() 函数内部，且 TRADE/CRISIS 各有两次赋值（第二次静默覆盖第一次）
TYPE_FIELD_MAP = {    "GEO":      ["地缘", "军事", "战争", "供给侧",
                 "伊朗", "霍尔木兹", "波斯湾", "中东", "以色列", "沙特",
                 "印度", "巴基斯坦", "马六甲", "苏伊士", "航道",
                 "土耳其", "里拉", "尼日利亚", "埃及", "非洲", "太空", "卫星"],
    "TRADE":    ["贸易", "制裁", "稀土", "矿产", "锂", "钴",
                 "稀土管制", "战略矿产", "资源武器化"],
    "CRISIS":   ["疫情", "系统", "地震", "海啸", "火山", "自然灾害",
                 "核泄漏", "AI监管", "量子", "太空冲突", "无人机", "卫星攻击",
                 "冲击"],
    "FIN":      ["金融", "货币", "杠杆", "主权"],
    "ENERGY":   ["供给侧", "石油", "能源"],
    "MACRO":    ["通缩", "激进货币"],
    "SOCIAL":   ["社会", "抗议", "动荡", "政变"],
    "POLITICAL":["政治", "政权", "制度"],
    "RELIGIOUS":["宗教", "族群", "极端"],
    "CLIMATE":  ["气候", "极端天气", "厄尔尼诺", "拉尼娜", "粮食", "干旱", "洪灾", "季风"],
    "CULTURAL": ["文化", "抵制", "软实力", "消费者", "品牌", "媒体封杀"],
}

# type_keywords：用于场景文本的关键词得分匹配
TYPE_KEYWORDS = {
    "GEO":      ["战争", "冲突", "危机", "俄乌", "海湾", "科索沃", "石油危机", "供给冲击", "地缘",
                 "伊朗", "霍尔木兹", "波斯湾", "中东", "以色列", "真主党", "哈马斯",
                 "沙特", "阿布盖格", "胡塞", "红海", "印度", "克什米尔",
                 "马六甲", "苏伊士", "巴拿马", "航道封锁", "曼德海峡",
                 "巴基斯坦", "土耳其", "里拉", "尼日利亚", "埃及", "非洲",
                 "太空", "卫星", "反卫星", "ASAT"],
    "FIN":      ["金融", "银行", "次贷", "流动性", "LTCM", "欧债", "货币危机"],
    "ENERGY":   ["石油", "能源", "OPEC", "油价", "供给侧", "石油危机"],
    "TRADE":    ["贸易", "关税", "制裁", "亚洲金融",
                 "稀土", "锂矿", "钴", "镍", "战略矿产", "矿产禁令", "资源武器化"],
    "MACRO":    ["衰退", "通胀", "滞胀", "债务", "沃尔克", "加息", "萧条"],
    "CRISIS":   ["疫情", "危机", "系统", "新冠", "黑色",
                 "地震", "海啸", "火山", "自然灾害", "核泄漏",
                 "AI监管", "人工智能法案", "量子突破", "太空冲突", "无人机蜂群", "卫星攻击"],
    "SOCIAL":   ["抗议", "政变", "动乱", "民众", "革命", "政权更迭"],
    "POLITICAL":["政变", "政治危机", "宪政", "选举争议", "政权"],
    "RELIGIOUS":["宗教", "极端主义", "圣战", "族群冲突", "sectarian"],
    "CLIMATE":  ["厄尔尼诺", "拉尼娜", "ONI", "粮食危机", "粮食价格", "主产区减产",
                 "旱灾", "洪灾", "极端天气", "台风", "飓风", "季风失败", "农业减产"],
    "CULTURAL": ["抵制", "软实力", "品牌禁止", "消费者抵制", "官媒参与",
                 "本土替代", "供应链重构", "文化冲突", "信息战"],
}

from hypothesis_config import DIM_MAP

_PATHS_FILE = (Path(os.environ.get("OPENCLAW_WORKSPACE", "/workspace"))
               / "知识库" / "财经知识库" / "04_分析框架" / "propagation_paths.yaml")
_paths_cache = None
_paths_mtime = 0.0

def _cal_decay(p: dict) -> float:
    """置信度时间衰减（P2-5，question calibration-score-no-decay）。

    验证证据随时间过期：effective = score * max(0.5, 0.98 ** 距 last_verified 年数)。
    无 last_verified 锚点的路径不衰减（factor=1.0）。参数可调，见 CHG-20260903T110600。
    """
    lv = p.get("last_verified")
    if not lv:
        return 1.0
    try:
        from datetime import datetime, timezone
        lv = str(lv)[:10]
        try:
            dt = datetime.strptime(lv, "%Y-%m-%d")
        except ValueError:
            dt = datetime.strptime(lv[:7], "%Y-%m")  # yaml 锚点形如 2022-08
        dt = dt.replace(tzinfo=timezone.utc)
        years = max(0.0, (datetime.now(timezone.utc) - dt).days / 365.25)
        return round(max(0.5, 0.98 ** years), 3)
    except Exception:
        return 1.0


def _load_propagation_paths() -> list:
    global _paths_cache, _paths_mtime
    try:
        mtime = _PATHS_FILE.stat().st_mtime
        if _paths_cache is None or mtime != _paths_mtime:
            with open(_PATHS_FILE, encoding="utf-8") as f:
                _paths_cache = yaml.safe_load(f) or []
            _paths_mtime = mtime
    except Exception as e:
        logging.warning(f"[HYP] 传导路径库加载失败: {e}")
        _paths_cache = _paths_cache or []
    return _paths_cache or []


def get_propagation_paths(scenario: dict, max_results: int = 2) -> list:
    """按情景类型和子类型检索最相关的传导路径（最多 max_results 条）。"""
    paths = _load_propagation_paths()
    stype   = scenario.get("scenario_type", "")
    subtype = scenario.get("subtype", "")
    raw     = scenario.get("raw_input", "").lower()
    label   = scenario.get("label", "").lower()

    scored = []
    for p in paths:
        score = 0
        if p.get("scenario_type") == stype:
            score += 2
        if p.get("subtype") and p["subtype"] == subtype:
            score += 3
        # 标签关键词匹配
        pid = p.get("id", "")
        plabel = p.get("label", "").lower()
        for kw in [stype.lower(), subtype.lower()]:
            if kw and kw in pid:
                score += 1
        for kw in re.findall(r'[一-鿿]{2,}|[a-z]{3,}', raw + " " + label):
            if kw in plabel:
                score += 1
        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Phase 2：复合情景额外匹配跨域路径（applicable_scenarios 字段）
    if scenario.get("is_compound") and scenario.get("components"):
        secondary_types = {c["scenario_type"] for c in scenario["components"]}
        existing_ids = {p["id"] for _, p in scored}
        for p in paths:
            applicable = p.get("applicable_scenarios", [])
            if applicable and secondary_types & set(applicable) and p["id"] not in existing_ids:
                scored.append((1, p))  # 跨域路径给基础分1
        scored.sort(key=lambda x: x[0], reverse=True)

    return [p for _, p in scored[:max_results]]


def _format_path_for_prompt(path: dict) -> str:
    """将单条传导路径格式化为 LLM 可读的 Markdown 段落。"""
    lines = []
    cal = path.get("calibration_score", "N/A")
    qual = path.get("data_quality", "")
    lines.append(f"**{path.get('label', path.get('id', '?'))}**  "
                 f"（置信度 {cal}，数据来源：{qual}）")
    chain = path.get("causal_chain", [])
    if chain:
        lines.append("传导链：")
        for step in chain:
            src_tag = "" if step.get("source") != "llm_inference" else " ⚠LLM推断"
            mag = step.get("magnitude", {})
            lines.append(
                f"  T+{step.get('lag_days', '?')}天  {step['event']}"
                f"  幅度≈{mag.get('base','?')}%（区间{mag.get('range','?')}）{src_tag}"
            )
    amp = [f["factor"] for f in path.get("amplifying_factors", [])]
    dam = [f["factor"] for f in path.get("dampening_factors", [])]
    if amp:
        lines.append(f"放大因素：{' | '.join(amp[:3])}")
    if dam:
        lines.append(f"降温因素：{' | '.join(dam[:3])}")
    note = path.get("notes", "").strip()
    if note:
        lines.append(f"注：{note[:150]}")
    return "\n".join(lines)



def _detect_feedback_loops(paths: list) -> list[str]:
    """
    检测传导路径集合中是否存在正反馈环（A→B→C→A 型自我放大）。
    返回检测到的反馈环描述列表。

    原理：把所有路径的因果链步骤提取为有向边集合，
    然后检查是否有步骤的"输出"又出现在其他步骤的"输入"中，
    形成闭合链。这是粗粒度检测，基于关键词匹配。
    """
    # 已知的正反馈环模式（关键词对：前驱词 → 后继词）
    FEEDBACK_PATTERNS = [
        ("货币贬值", "进口通胀", "通胀→贬值→更多通胀（货币危机正反馈）"),
        ("资本外逃", "货币贬值", "资本外逃→贬值→更多外逃（货币危机正反馈）"),
        ("通胀", "社会压力", "通胀→社会压力→政策失当→更多通胀（社会-通胀螺旋）"),
        ("信用收缩", "资产价格", "信用收缩→资产下跌→更多抵押品不足（金融加速器）"),
        ("粮食价格", "社会压力", "粮食涨价→社会动荡→政治不稳→政策更差→更多通胀"),
        ("政治危机", "资本外逃", "政治危机→外资撤出→货币贬值→更多政治压力"),
    ]

    # 汇总所有路径中出现的事件描述
    all_events = []
    for p in paths:
        for step in p.get("causal_chain", []):
            ev = step.get("event", "")
            if ev:
                all_events.append(ev)

    events_text = " ".join(all_events)
    detected = []
    for kw1, kw2, description in FEEDBACK_PATTERNS:
        if kw1 in events_text and kw2 in events_text:
            detected.append(description)

    return detected

def get_rag_queries_for_scenario(scenario: dict) -> list:
    templates = _load_templates()
    stype = scenario.get("scenario_type", "")
    cat = templates.get("categories", {}).get(stype, {})
    queries = list(cat.get("rag_queries", []))
    queries.append("macro_regime_framework宏观体制切换")
    return queries


# ── 接近度计算（Step 2 扩展，M0 stub）────────────────────────
def compute_proximity(scenario: dict, current_indicators: dict) -> dict:
    """M0 stub，M3 后实现完整逻辑。"""
    return {"level": "green", "pct": 0.0, "note": "接近度计算 M3 后实现"}


# ── M2-1：4维综合置信度计算 ───────────────────────────────────
def compute_confidence(
    scenario: dict,
    analogies: dict,
    matched_paths: list,
    grv: dict | None = None,
    wiki_entries: list | None = None,
) -> dict:
    """
    4维置信度框架（调和平均）：
      历史锚定强度   40%  — 有多少相关地缘历史案例支持
      传导路径完整性 25%  — 传导链中有数据支持的步骤占比
      信号时效性     20%  — 当前 GRV 是否与情景方向一致
      内部一致性     15%  — scenario_wiki 历次推演变异系数

    永远不能升格到 🟢 的情景：核威慑升级、政权崩溃、推演跨度>12个月
    返回 dict：score/breakdown/signal/notes
    """
    stype   = scenario.get("scenario_type", "")
    subtype = scenario.get("subtype", "")
    sev     = scenario.get("severity", "L2")

    # ── 维度1：历史锚定强度（0-1）────────────────────────────
    raw_list = analogies.get("raw", [])
    geo_cats = {"geopolitical_standoff", "military_conflict", "large_scale_invasion",
                "territorial_annexation", "terrorist_attack", "non_state_conflict",
                "trade_tech_war", "sanctions_asymmetric",
                # Phase 2 新增：气候/社会/政治/文化类别
                "climate_food_shock", "climate_el_nino", "climate_la_nina", "climate_no_crisis",
                "social_unrest", "social_political_unrest",
                "political_coup", "debt_social_collapse",
                "cultural_trade_boycott", "religious_violence_energy",
                # 新增中东/航道案例（HQ-20260611）
                "geo_middle_east_energy", "geo_shipping_disruption",
                # 新增自然灾害/科技案例
                "natural_disaster_supply_chain", "earthquake_nuclear",
                "tech_regulation_impact", "rare_earth_sanctions"}
    relevant = [s for s in raw_list
                if s.get("crisis_category", "") in geo_cats
                or s.get("taiwan_strait_relevance", 0) >= 3]
    n_relevant = len(relevant)
    # ≥3条相关案例且最佳类比质量>0.6 → 升格条件
    best_tw = raw_list[0].get("taiwan_strait_relevance", 0) if raw_list else 0
    d1_raw = min(n_relevant / 5.0, 1.0)                # 5条以上满分
    if n_relevant < 2:
        d1_note = f"仅{n_relevant}条相关历史案例，样本极小"
    elif n_relevant < 3:
        d1_note = f"{n_relevant}条相关案例，不足升格门槛（需≥3条）"
    else:
        d1_note = f"{n_relevant}条相关案例，锚定充分"
    d1 = round(d1_raw, 3)

    # ── 维度2：传导路径完整性（0-1）──────────────────────────
    if not matched_paths:
        d2 = 0.2
        d2_note = "无预定义传导路径，依赖LLM推理"
    else:
        all_steps, data_steps = 0, 0
        for p in matched_paths:
            for step in p.get("causal_chain", []):
                all_steps += 1
                if step.get("source", "") != "llm_inference":
                    data_steps += 1
        ratio = data_steps / all_steps if all_steps else 0
        # 加权：路径 calibration_score 平均值
        avg_cal = sum(p.get("calibration_score", 0.3) * _cal_decay(p) for p in matched_paths) / len(matched_paths)
        d2 = round((ratio * 0.6 + avg_cal * 0.4), 3)
        d2_note = f"传导链{data_steps}/{all_steps}步有数据支持，路径平均置信度{avg_cal:.2f}"

    # ── 维度3：信号时效性（0-1）──────────────────────────────
    if grv is None:
        # 尝试读 grv_latest.json
        try:
            import json as _j, os as _o
            from optim_config import DATA_DIR as _dd
            _p = _o.path.join(_dd, "grv_latest.json")
            if _o.path.exists(_p):
                with open(_p, encoding="utf-8") as _f:
                    grv = _j.load(_f)
        except Exception:
            grv = None

    if grv is None or grv.get("source_quality") == "stub":
        d3 = 0.3
        d3_note = "无实时GRV信号，使用默认值"
    else:
        # 引用模块级常量 DIM_MAP（已外置到 hypothesis_config.py）
        grv_key = DIM_MAP.get(stype, "global_composite")
        grv_val = grv.get(grv_key)
        if grv_val is None or not isinstance(grv_val, (int, float)):
            d3 = 0.3
            d3_note = f"GRV[{grv_key}]无数据或类型异常"
        else:
            # 0-100 分映射：>50 高风险→信号一致→高置信；<20 低风险→信号相反→低置信
            d3 = round(min(max(grv_val / 100.0, 0.1), 0.9), 3)
            # 社会/政治/宗教类：置信度上限🟡（0.65），永不升🟢
            if stype in ("SOCIAL", "POLITICAL", "RELIGIOUS"):
                d3 = min(d3, 0.65)
            quality = grv.get("source_quality", "unknown")
            d3_note = f"GRV[{grv_key}]={grv_val:.1f}/100（{quality}）"

    # ── 维度4：内部一致性（0-1）──────────────────────────────
    entries = wiki_entries or []
    if len(entries) < 2:
        d4 = 0.5   # 数据不足，中性
        d4_note = f"推演次数{len(entries)}次，不足计算变异系数（需≥5次）"
    else:
        # 从 wiki entry 文本里提取 SPX 数字做粗略 CV 估算
        import re as _re
        spx_nums = []
        for e in entries:
            nums = _re.findall(r'SPX.*?(-?\d+\.?\d*)%', e)
            spx_nums.extend(float(n) for n in nums)
        if len(spx_nums) >= 2:
            import statistics as _st
            try:
                cv = abs(_st.stdev(spx_nums) / _st.mean(spx_nums)) if _st.mean(spx_nums) != 0 else 1.0
                d4 = round(max(0.1, 1.0 - cv), 3)
                d4_note = f"{len(entries)}次推演，CV={cv:.2f}（{'稳定' if cv<0.2 else '有漂移'}）"
            except Exception:
                d4 = 0.5
                d4_note = "CV计算异常，使用默认值"
        else:
            d4 = 0.5
            d4_note = f"{len(entries)}次推演，无法提取SPX数字"

    # ── 调和平均 ──────────────────────────────────────────────
    weights = [(d1, 0.40), (d2, 0.25), (d3, 0.20), (d4, 0.15)]
    # 调和平均：1 / Σ(w/d)，防止某维极低值主导
    try:
        harm = 1.0 / sum(w / max(d, 0.01) for d, w in weights)
    except ZeroDivisionError:
        harm = 0.1
    score = round(min(harm, 0.99), 3)

    # ── 永不升格到🟢 的条件 ─────────────────────────────────
    no_green_triggers = []
    label_lower = scenario.get("label", "").lower() + scenario.get("raw_input", "").lower()
    if any(kw in label_lower for kw in ["核", "nuclear", "政权崩溃", "regime collapse"]):
        no_green_triggers.append("含核威慑/政权崩溃场景")
    if sev in ("L3", "L4"):
        no_green_triggers.append(f"{sev}烈度（极端场景）")

    # ── 信号灯 ────────────────────────────────────────────────
    # 注意：系统设计永不输出🟢（高风险场景不给"已验证"标签）
    # 两个置信度档位均为🟡，仅通过 score 数值区分高低
    if no_green_triggers:
        signal = "🔴"
        signal_reason = "永不升格：" + "；".join(no_green_triggers)
    elif score >= 0.45:
        signal = "🟡"
        signal_reason = "置信度中等，可供参考" if score >= 0.65 else "置信度较低，需谨慎解读"
    else:
        signal = "🔴"
        signal_reason = "置信度不足，仅供方向性参考"

    # 升格条件检查（🔴→🟡）
    upgrade_notes = []
    if n_relevant < 3:
        upgrade_notes.append(f"需≥3条相关案例（现{n_relevant}条）")
    if d2 < 0.4:
        upgrade_notes.append("传导路径数据覆盖率不足")
    if len(entries) < 5:
        upgrade_notes.append(f"需≥5次推演积累（现{len(entries)}次）")

    return {
        "score":   score,
        "signal":  signal,
        "signal_reason": signal_reason,
        "breakdown": {
            "historical_anchor":  {"score": d1, "weight": 0.40, "note": d1_note},
            "path_completeness":  {"score": d2, "weight": 0.25, "note": d2_note},
            "signal_freshness":   {"score": d3, "weight": 0.20, "note": d3_note},
            "internal_consistency":{"score": d4, "weight": 0.15, "note": d4_note},
        },
        "upgrade_conditions": upgrade_notes,
        "no_green_triggers":  no_green_triggers,
    }


# ── 构建假设模式 LLM 提示词（Step 6B）────────────────────────
def build_hypothesis_prompt(
    scenario: dict,
    analogies: dict,
    wiki_entries: list,
    rag_chunks: list,
    indicators: dict,
    base_vix: float = 20.0,
    matched_paths: list | None = None,
    conf: dict | None = None,
) -> str:
    """HYP-5: matched_paths / conf 由调用方传入，避免与 run_hypothesis 重复计算导致不一致。"""
    if SYSTEM_PROMPT_FILE.exists():
        system_section = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    else:
        system_section = "你是宏观情景分析引擎，处于假设推演模式。"

    sev_label = _load_templates().get("severity_params", {}).get(
        scenario.get("severity", "L2"), {}
    ).get("name", scenario.get("severity", "L2"))

    lines = [system_section, "\n---\n"]

    # ── [HYPOTHESIS] 假设前提 + 置信度 ───────────────────────
    lines.append("## [HYPOTHESIS] 假设前提")
    lines.append(f"情景：**{scenario['label']}**")
    lines.append(f"类型：{scenario['scenario_type']}  |  烈度：{scenario.get('severity','L2')}（{sev_label}）")
    lines.append(f"原始输入：{scenario['raw_input']}")
    if scenario.get("is_compound") and scenario.get("components"):
        lines.append("组合叠加：" + " + ".join(c["label"] for c in scenario["components"]))
    if scenario.get("synergies"):
        lines.append("协同效应：" + "；".join(scenario["synergies"]))

    # 置信度分解注入 [HYPOTHESIS] 节（优先使用传入值，避免重复计算）
    if matched_paths is None:
        matched_paths = get_propagation_paths(scenario)
    if conf is None:
        conf = compute_confidence(
            scenario=scenario,
            analogies=analogies,
            matched_paths=matched_paths,
            wiki_entries=wiki_entries,
        )
    bd = conf["breakdown"]
    lines.append(f"\n综合置信度：**{conf['score']:.2f} / 1.00**  {conf['signal']}  {conf['signal_reason']}")
    bar_map = {0.0: "░░░░░░░░░░", 0.1: "█░░░░░░░░░", 0.2: "██░░░░░░░░",
               0.3: "███░░░░░░░", 0.4: "████░░░░░░", 0.5: "█████░░░░░",
               0.6: "██████░░░░", 0.7: "███████░░░", 0.8: "████████░░",
               0.9: "█████████░", 1.0: "██████████"}
    def _bar(v):
        k = round(v * 10) / 10
        return bar_map.get(k, "░░░░░░░░░░")
    lines.append(f"  历史锚定  {_bar(bd['historical_anchor']['score'])} {bd['historical_anchor']['score']:.2f}  [{bd['historical_anchor']['note']}]")
    lines.append(f"  传导路径  {_bar(bd['path_completeness']['score'])} {bd['path_completeness']['score']:.2f}  [{bd['path_completeness']['note']}]")
    lines.append(f"  信号时效  {_bar(bd['signal_freshness']['score'])} {bd['signal_freshness']['score']:.2f}  [{bd['signal_freshness']['note']}]")
    lines.append(f"  内部一致  {_bar(bd['internal_consistency']['score'])} {bd['internal_consistency']['score']:.2f}  [{bd['internal_consistency']['note']}]")
    if conf.get("upgrade_conditions"):
        lines.append(f"  升格条件：" + "；".join(conf["upgrade_conditions"]))
    lines.append("")

    # ── [WIKI] ───────────────────────────────────────────────
    if wiki_entries:
        lines.append("## [WIKI] 历史推演记录（来自 scenario_wiki）")
        for entry in wiki_entries:
            lines.append(entry[:800])
        lines.append("")
    else:
        lines.append("## [WIKI] 历史推演记录")
        lines.append("（首次推演该情景，暂无历史记录可对比）")
        lines.append("")

    # ── [PATHS] 传导路径库 ────────────────────────────────────
    if matched_paths:
        lines.append("## [PATHS] 传导路径库（结构化数据）")
        lines.append("引用本节步骤时请标注步骤编号（如 [PATHS-1-T+7天]）；"
                     "⚠LLM推断标记的步骤不得作为定量依据。")
        for i, p in enumerate(matched_paths, 1):
            lines.append(f"\n### PATHS-{i}")
            lines.append(_format_path_for_prompt(p))
        lines.append("")

        # 反馈环检测（Phase 3C 增强）
        feedback_loops = _detect_feedback_loops(matched_paths)
        if feedback_loops:
            lines.append("## [FEEDBACK] ⚠️ 检测到正反馈环")
            lines.append("以下传导机制存在自我放大倾向，冲击烈度可能超过线性预测：")
            for fl in feedback_loops:
                lines.append(f"  • {fl}")
            lines.append("推演时请明确标注是否进入了正反馈加速阶段，并给出触发/打断反馈环的条件。")
            lines.append("")
    else:
        lines.append("## [PATHS] 传导路径库")
        lines.append("（当前情景无预定义路径，依赖 [CRISIS] 历史类比和 LLM 推理）")
        lines.append("")

    # ── [CRISIS] 历史危机类比 ─────────────────────────────────
    lines.append("## [CRISIS] 历史危机类比数据")
    if analogies.get("best"):
        lines.append(f"- 最相似案例：{analogies['best']}")
        if analogies.get("best_lessons"):
            lines.append(f"  关键教训：{analogies['best_lessons'][:200]}")
    if analogies.get("second"):
        lines.append(f"- 次相似案例：{analogies['second']}")
    impacts = analogies.get("impacts", {})
    if impacts.get("spx_pct"):
        d = impacts["spx_pct"]
        lines.append(f"- 标普500历史类比区间：P10={d['p10']}% / P50={d['p50']}% / P90={d['p90']}%（{d['source']}）")
    if impacts.get("vix_delta"):
        d = impacts["vix_delta"]
        lines.append(f"- VIX冲击历史类比区间：+{d['p10']} / +{d['p50']} / +{d['p90']}（{d['source']}）")
    lines.append("")

    # ── [KB] 知识库检索 ───────────────────────────────────────
    if rag_chunks:
        lines.append("## [KB] 知识库检索结果")
        for i, chunk in enumerate(rag_chunks[:5], 1):
            lines.append(f"### KB-{i}")
            lines.append(chunk[:600])
        lines.append("")

    # ── [DATA] 实时指标 + GDELT ───────────────────────────────
    lines.append("## [DATA] 实时指标快照（背景参考，不被假设覆盖）")
    for kid in ["VIX", "T10Y2Y", "BAA10Y", "DFF", "CPIAUCSL", "UNRATE"]:
        ind = indicators.get(kid, {})
        if ind and ind.get("value") is not None:
            lines.append(f"- {kid}: {ind['value']} （{ind.get('date','N/A')}）")

    try:
        import json as _json, os as _os
        from optim_config import DATA_DIR as _DATA_DIR
        _gdelt_path = _os.path.join(_DATA_DIR, "gdelt_scores.json")
        if _os.path.exists(_gdelt_path):
            with open(_gdelt_path, encoding="utf-8") as _f:
                _gd = _json.load(_f)
            _scores = _gd.get("scores", {})
            _updated = _gd.get("updated", "N/A")
            lines.append(f"\n## [GEO] GDELT 实时地缘信号（更新：{_updated}）")
            lines.append("（来自 scan_weak_signals.py 每6h采集，0-100分）")
            _focus_map = {
                "GEO":    ["TWN", "CHN", "USA", "PRK", "JPN"],
                "ENERGY": ["IRN", "SAU", "ISR", "RUS"],
                "TRADE":  ["USA", "CHN", "DEU", "JPN"],
            }
            _focus = _focus_map.get(scenario.get("scenario_type", ""), ["USA", "CHN", "RUS", "TWN"])
            for _c in _focus:
                _mil_s  = _scores.get("military", {}).get(_c, 0)
                _sanc_s = _scores.get("sanction", {}).get(_c, 0)
                if _mil_s > 0.1 or _sanc_s > 0.1:
                    lines.append(f"- {_c}: 军事压力={_mil_s:.1f}/100  制裁强度={_sanc_s:.1f}/100")
    except Exception:
        pass

    lines.append("")

    # ── 输出指令（收紧版）────────────────────────────────────
    lines.append("## 输出指令")
    lines.append(
        f"请按 system_prompt_hypothesis.md 规定的格式，"
        f"输出「[假设推演] {scenario['label']}（{scenario.get('severity','L2')}）」完整分析报告。\n"
        f"**强制要求：**\n"
        f"1. 传导路径叙事必须引用 [PATHS-N-T+X天] 步骤编号\n"
        f"2. 带⚠LLM推断标记的步骤不得作为定量依据，引用时须注明'估算'\n"
        f"3. 置信度信号灯沿用上方计算结果（{conf['signal']} {conf['score']:.2f}），不得自行美化\n"
        f"4. 量化区间需标注来源（历史数据/路径库/LLM估算）"
    )

    return "\n".join(lines)


# ── 保存推演报告（Step 8B）────────────────────────────────────
def save_hypothesis_report(report: str, scenario: dict) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    label_safe = re.sub(r'[^一-鿿A-Za-z0-9_]', '_', scenario.get("label", "unknown"))[:30]
    sev = scenario.get("severity", "L2")
    filename = REPORT_DIR / f"[假设]_{label_safe}_{sev}_{date_str}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)
    logging.info(f"[HYP] 推演报告已保存: {filename}")
    return str(filename)


# ── Step 9: 异步 Wiki 编译 ────────────────────────────────────
def _compile_wiki_entry(report: str, scenario: dict, indicators: dict,
                        conf: dict | None = None):
    """HYP-2: conf 由调用方传入（run_hypothesis Step 6B 已算好），不再用空参重算。"""
    logger = _get_wiki_logger()
    try:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        entry_id = str(uuid.uuid4())
        stype   = scenario.get("scenario_type", "")
        subtype = scenario.get("subtype", "")
        sev     = scenario.get("severity", "L2")
        label   = scenario.get("label", "")
        key     = f"{stype}-{subtype}-{sev}".upper()

        path_lines = re.findall(r'T\+[^\n]+', report)[:6]
        transmission = "\n".join(f"    {i+1}. {p.strip()}" for i, p in enumerate(path_lines))
        if not transmission:
            transmission = "    （未能从报告中提取传导路径）"

        snap_vix = indicators.get("VIX", {}).get("value", "N/A")
        snap_t10 = indicators.get("T10Y2Y", {}).get("value", "N/A")

        # M2-2 新增字段
        # grv_at_inference：推演时刻 GRV 快照
        try:
            import json as _jj, os as _oo
            from optim_config import DATA_DIR as _ddd
            _gp = _oo.path.join(_ddd, "grv_latest.json")
            if _oo.path.exists(_gp):
                with open(_gp, encoding="utf-8") as _ff:
                    _grv_snap = _jj.load(_ff)
                _snap_grv = (f"taiwan={_grv_snap.get('taiwan_strait','N/A')} "
                             f"us_china={_grv_snap.get('us_china_strategic','N/A')} "
                             f"quality={_grv_snap.get('source_quality','N/A')}")
            else:
                _snap_grv = "N/A"
        except Exception:
            _snap_grv = "N/A"

        # confidence_breakdown：4维置信度摘要（使用传入的真实推演置信度）
        try:
            _conf = conf or compute_confidence(scenario={
                "scenario_type": stype, "subtype": subtype,
                "severity": sev, "label": label, "raw_input": label,
            }, analogies={}, matched_paths=[], wiki_entries=[])
            _bd = _conf["breakdown"]
            _conf_summary = (
                f"score={_conf['score']} signal={_conf['signal']} "
                f"anchor={_bd['historical_anchor']['score']} "
                f"path={_bd['path_completeness']['score']} "
                f"freshness={_bd['signal_freshness']['score']} "
                f"consistency={_bd['internal_consistency']['score']}"
            )
        except Exception:
            _conf_summary = "N/A"

        # key_assumptions：从报告首500字提取假设句
        _assumption_lines = [
            ln.strip() for ln in report[:500].splitlines()
            if any(kw in ln for kw in ["假设", "前提", "若", "如果", "假定", "assume", "given"])
        ]
        _key_assumptions = " | ".join(_assumption_lines[:3]) or "（未提取）"

        content_hash = hashlib.sha256(report[:2000].encode("utf-8")).hexdigest()[:16]

        entry = (
            f"\n## {key} [{now}]\n"
            f"- entry_id: {entry_id}\n"
            f"- content_hash: sha256:{content_hash}\n"
            f"- scenario_type: {stype} / severity: {sev}\n"
            f"- label: {label}\n"
            f'- input_snapshot: {{time: "{now}", vix: {snap_vix}, t10y2y: {snap_t10}}}\n'
            f"- grv_at_inference: {_snap_grv}\n"
            f"- confidence_breakdown: {_conf_summary}\n"
            f"- key_assumptions: {_key_assumptions}\n"
            f"- verified: false\n"
            f"- actual_outcome: （待填写）\n"
            f"- falsifiability_type: counterfactual\n"
            f"- transmission_path:\n{transmission}\n"
            f"- ref_count: 0\n"
            f"- entry_version: 2\n"
            f"- status: active\n\n"
        )

        with _wiki_lock:
            if not WIKI_FILE.exists():
                WIKI_FILE.parent.mkdir(parents=True, exist_ok=True)
                WIKI_FILE.write_text(
                    "# Scenario Wiki — 假设推演知识库\n\n"
                    "> 自动维护，由每次推演后异步编译生成。\n\n---\n",
                    encoding="utf-8",
                )

            # HYP-4b: content_hash 检查在锁内执行，防止 TOCTOU 竞态导致重复写入
            existing = WIKI_FILE.read_text(encoding="utf-8")
            if content_hash in existing:
                logger.info(f"[WIKI] content_hash 重复，跳过: {content_hash}")
                return

            with open(WIKI_FILE, "a", encoding="utf-8") as f:
                f.write(entry)

        logger.info(f"[WIKI] 新条目已追加: {key} [{now}] hash={content_hash}")

    except Exception as e:
        logger.error(f"[WIKI] 编译失败: {e}", exc_info=True)


def async_compile_wiki(report: str, scenario: dict, indicators: dict,
                       conf: dict | None = None):
    t = threading.Thread(
        target=_compile_wiki_entry,
        args=(report, scenario, indicators, conf),
        daemon=False,  # HYP-4/CON-5: 非 daemon，SIGTERM 时等待 wiki 写完
    )
    t.start()
    logging.info("[HYP] Step 9 Wiki 编译已在后台启动")


# ── 完整假设推演入口 ──────────────────────────────────────────
def run_hypothesis(
    hypothesis_text: str,
    indicators: dict,
    rag_query_fn,
    call_llm_fn,
    push_fn=None,
    depth: str = "standard",
    severity_override: str = None,
) -> dict:
    print(f"\n{'='*60}")
    print(f"[假设推演] 开始处理：{hypothesis_text}")
    print("="*60)
    conf = None  # HYP-1: 确保 conf 始终有初始值，避免 dir() 检查歧义

    # Step 0: 情景解析
    print("\n[H0] 解析情景...")
    parser = ScenarioParser()
    scenario = parser.parse_compound(hypothesis_text, severity_override=severity_override)
    print(f"  类型: {scenario['scenario_type']}  烈度: {scenario['severity']}  置信度: {scenario['confidence']:.0%}")
    print(f"  标签: {scenario['label']}")
    if scenario.get("synergies"):
        print(f"  协同效应: {'; '.join(scenario['synergies'])}")

    # Step 0b: wiki 检索
    print("\n[H0b] 检索 scenario_wiki...")
    wiki_entries = search_wiki(scenario)
    if wiki_entries:
        print(f"  命中 {len(wiki_entries)} 条历史推演记录")
    else:
        print("  首次推演该情景，无历史记录")

    # Step 3B: 历史类比
    print("\n[H3] 匹配历史危机类比...")
    analogies = get_historical_analogies(scenario)
    if analogies.get("best"):
        print(f"  最近似: {analogies['best']}")
    if analogies.get("second"):
        print(f"  次近似: {analogies['second']}")

    # Step 4B: 按情景类型强制 RAG 查询
    print("\n[H4] 情景专项知识库检索...")
    rag_queries = get_rag_queries_for_scenario(scenario)
    rag_chunks = []
    seen = set()
    for q in rag_queries:
        try:
            for chunk in rag_query_fn(q, n_results=2):
                fname = chunk[:60]
                if fname not in seen:
                    seen.add(fname)
                    rag_chunks.append(chunk)
        except Exception:
            pass
        if len(rag_chunks) >= 6:
            break
    print(f"  检索到 {len(rag_chunks)} 个相关段落")

    # Step 6B: 构建提示词（HYP-5: 一次性算好 matched_paths + conf，传给 build_prompt，不重复计算）
    print("\n[H6] 构建假设推演提示词...")
    matched_paths_for_conf = get_propagation_paths(scenario)
    conf = compute_confidence(
        scenario=scenario,
        analogies=analogies,
        matched_paths=matched_paths_for_conf,
        wiki_entries=wiki_entries,
    )
    print(f"  综合置信度: {conf['score']:.3f}  {conf['signal']}")
    base_vix = float(indicators.get("VIX", {}).get("value", 20.0) or 20.0)
    prompt = build_hypothesis_prompt(
        scenario=scenario,
        analogies=analogies,
        wiki_entries=wiki_entries,
        rag_chunks=rag_chunks,
        indicators=indicators,
        base_vix=base_vix,
        matched_paths=matched_paths_for_conf,
        conf=conf,
    )
    print(f"  提示词长度: {len(prompt)} 字符")

    # Step 7: 调用 LLM 推理
    print("\n[H7] 调用 LLM 推理（假设推演模式）...")

    if depth == "deep":
        # Phase 3B：多步推理链（deep 模式）
        try:
            # 第一轮：识别关键不确定因素
            print("  [deep] 第一轮：识别关键不确定因素...")
            round1_prompt = (
                f"情景：{scenario['label']}（{scenario.get('severity','L2')}）\n"
                f"当前宏观数据摘要（VIX={base_vix:.1f}）\n\n"
                "仅列出此情景下最关键的3个不确定因素，每个用一句话描述，格式：\n"
                "1. [因素名称]：[描述]\n2. ...\n3. ...\n不需要其他内容。"
            )
            factors_text = call_llm_fn(round1_prompt, mode="auto") or ""
            if not factors_text.strip() or factors_text.startswith("[LLM"):
                raise ValueError("第一轮因素识别返回空或 LLM 不可用，降级为标准模式")
            print(f"  [deep] 关键因素：{factors_text[:200]}")

            # 第二轮：对每个因素估计概率区间
            print("  [deep] 第二轮：概率区间估计...")
            round2_prompt = (
                f"情景：{scenario['label']}\n"
                f"以下3个关键不确定因素：\n{factors_text}\n\n"
                "请为每个因素给出：悲观概率（%）/ 基准概率（%）/ 乐观概率（%），格式：\n"
                "1. 悲观XX% / 基准XX% / 乐观XX%\n不需要其他解释。"
            )
            probs_text = call_llm_fn(round2_prompt, mode="auto") or ""
            if not probs_text.strip() or probs_text.startswith("[LLM"):
                raise ValueError("第二轮概率估计返回空或 LLM 不可用，降级为标准模式")
            print(f"  [deep] 概率分布：{probs_text[:200]}")

            # 第三轮：综合推演
            print("  [deep] 第三轮：综合推演...")
            deep_suffix = (
                f"\n\n## [深度分析·多步推理]\n"
                f"**关键不确定因素**：\n{factors_text}\n\n"
                f"**概率分布估计**：\n{probs_text}\n\n"
                "请在以上分析基础上，综合给出最终推演结论和情景树（乐观/基准/悲观三条路径）。"
            )
            report = call_llm_fn(prompt + deep_suffix, mode="auto")
        except Exception as _deep_e:
            print(f"  [deep] 多步推理中断：{_deep_e}，降级为标准模式")
            report = call_llm_fn(prompt, mode="auto")
    else:
        report = call_llm_fn(prompt, mode="auto")

    # 降级链
    if not report or not report.strip():
        print("  [降级L1] LLM 不可用，尝试返回缓存推演...")
        if wiki_entries:
            report = _make_cache_fallback(scenario, wiki_entries)
            print("  已返回缓存推演结果")
        else:
            report = _make_static_fallback(scenario, analogies)
            print("  [降级L2] 已返回静态降级报告")

    # Step 8B: 保存报告（严格不入预测库）
    print("\n[H8] 保存假设推演报告...")
    filename = save_hypothesis_report(report, scenario)
    print(f"  报告已保存: {filename}")

    # ntfy 推送
    if push_fn:
        sev_label = _load_templates().get("severity_params", {}).get(
            scenario.get("severity", "L2"), {}
        ).get("name", scenario.get("severity", "L2"))
        push_fn(
            f"[假设推演] {scenario['label']}（{sev_label}）",
            report,
            filename=filename,
        )

    # Step 9: 异步 Wiki 编译（传入本次推演的真实 conf，HYP-2）
    async_compile_wiki(report, scenario, indicators, conf=conf)

    return {"filename": filename, "scenario": scenario, "report": report,
            "confidence": conf}


# ── 降级函数 ─────────────────────────────────────────────────
def _make_cache_fallback(scenario: dict, wiki_entries: list) -> str:
    label = scenario.get("label", "未知情景")
    sev   = scenario.get("severity", "L2")
    entry = wiki_entries[0][:1200] if wiki_entries else "无记录"
    return (
        f"# [假设推演 · 缓存] {label}（{sev}）\n\n"
        "> **降级模式**：LLM 当前不可用，以下为 scenario_wiki 中最近匹配的历史推演记录。\n\n"
        f"{entry}\n\n"
        "*[假设] 标签推演不计入月度预测校验。*"
    )


def _make_static_fallback(scenario: dict, analogies: dict) -> str:
    label = scenario.get("label", "未知情景")
    sev   = scenario.get("severity", "L2")
    best  = analogies.get("best", "无")
    impacts = analogies.get("impacts", {})
    spx = impacts.get("spx_pct", {})
    spx_line = ""
    if spx:
        spx_line = f"- 标普500 历史类比：P50={spx.get('p50','N/A')}%（区间：{spx.get('p10','N/A')}% ~ {spx.get('p90','N/A')}%）\n"
    return (
        f"# [假设推演 · 静态降级] {label}（{sev}）\n\n"
        "> **静态降级**：LLM 不可用且无历史推演缓存，以下为历史类比数据（无叙事分析）。\n\n"
        f"## 历史类比\n- 最近似案例：{best}\n\n"
        f"## 量化参考（历史类比，非本情景验证）\n"
        + spx_line
        + "\n*[假设] 标签推演不计入月度预测校验。*"
    )


# ── subprocess 调用专用简化入口 ───────────────────────────────
def run_hypothesis_simple(hypothesis_text: str, depth: str = "standard") -> dict:
    """
    供 subprocess 调用的简化入口（signal_synthesizer、grv_threshold 等独立进程使用）。

    signal_synthesizer.py 和 grv_threshold.py 通过 subprocess.Popen 启动，
    无法从父进程接收 Python 对象参数。此函数自行从磁盘构造所需依赖，
    委托给完整的 run_hypothesis，保持行为一致。

    任一依赖不可用时优雅降级，不向调用方抛出 TypeError。
    """
    import json as _j
    import os as _o

    # 从 grv_latest.json 构造最小 indicators（仅置信度计算需要，非实时 FRED 数据）
    indicators: dict = {}
    try:
        from optim_config import DATA_DIR as _dd
        _gp = _o.path.join(_dd, "grv_latest.json")
        if _o.path.exists(_gp):
            with open(_gp, encoding="utf-8") as _f:
                _grv = _j.load(_f)
            indicators["VIX"]    = {"value": None, "date": _grv.get("updated", "N/A")}
            indicators["T10Y2Y"] = {"value": None, "date": "N/A"}
    except Exception:
        pass

    def _rag_fn(query: str, n_results: int = 2) -> list:
        try:
            from rag_engine import query as _q
            return _q(query, n_results=n_results)
        except Exception:
            return []

    def _llm_fn(prompt: str, mode: str = "auto", **kw):
        from hybrid_llm import reason
        return reason(prompt, mode=mode, **kw)

    return run_hypothesis(
        hypothesis_text=hypothesis_text,
        indicators=indicators,
        rag_query_fn=_rag_fn,
        call_llm_fn=_llm_fn,
        depth=depth,
    )
