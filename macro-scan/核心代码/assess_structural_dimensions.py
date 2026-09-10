"""
结构层季度评估模块

使用 LLM 对四个慢变量维度进行校准打分，结果写入 structural_priors.json，
供 run_monte_carlo() 作为体制先验修改传导系数。

维度：政治稳健性 / 社会凝聚力 / 技术扰动 / 气候物理风险 / 金融体系脆弱性 / 人口老龄化压力

运行方式：
  python assess_structural_dimensions.py           # 有效期内跳过，过期则重评
  python assess_structural_dimensions.py --force   # 强制重新评估
  python assess_structural_dimensions.py --show    # 只显示当前分数
"""

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta

import requests

try:
    from optim_config import ANTHROPIC_API_KEY, DATA_DIR, WORKSPACE
except ImportError:
    _ws = os.environ.get("OPENCLAW_WORKSPACE",
                         os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR          = os.path.join(_ws, "data")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    WORKSPACE         = _ws

STRUCTURAL_PRIORS_FILE = os.path.join(DATA_DIR, "structural_priors.json")
VALIDITY_DAYS          = 90   # 季度更新

_http_proxy  = os.environ.get("HTTP_PROXY")
_https_proxy = os.environ.get("HTTPS_PROXY")
_API_PROXY = {"http": _http_proxy, "https": _https_proxy} if (_http_proxy or _https_proxy) else None

# ── 维度定义与评分锚点 ─────────────────────────────────────────────────────────
DIMENSION_RUBRICS = {
    "political_stability": {
        "zh": "政治稳健性",
        "desc": "主要经济体（美/欧/中/日/新兴市场）政策可预期性与制度稳定性",
        "anchors": {
            "100": "政策高度可预期，制度稳健，选举结果不影响基本经济方向",
            "75":  "选举基本完成，政策路径较清晰，少数尾部不确定性",
            "50":  "多个主要选举待定，存在显著政策方向不确定性（历史基准）",
            "25":  "民粹主义抬头，贸易/财政政策面临结构性反转，多地治理能力下降",
            "0":   "主要经济体出现合法性危机，宪法框架受威胁（如2011年欧债危机峰值）",
        },
        "mc_impact": "低分 → 危机概率上调，信用冲击→GDP 传导系数增大",
    },
    "social_cohesion": {
        "zh": "社会凝聚力",
        "desc": "主要经济体社会极化程度、不平等趋势与机构信任度",
        "anchors": {
            "100": "基尼系数改善，机构信任高，无大规模社会运动",
            "75":  "温和不平等，偶发抗议，政治极化可控",
            "50":  "中等极化，间歇性抗议，机构信任受损（历史基准）",
            "25":  "高度极化，频繁大规模抗议，社会凝聚力显著下降",
            "0":   "严重社会撕裂，抗议演变为系统性政治危机（如2019年智利）",
        },
        "mc_impact": "低分 → 消费信心拖累增强，经济冲击政治传导系数增大",
    },
    "tech_disruption": {
        "zh": "技术扰动强度",
        "desc": "AI/自动化对劳动力市场和产业结构的结构性冲击（未来12个月视野）",
        "anchors": {
            "0":   "技术变化平缓，就业结构稳定",
            "25":  "AI 在特定行业初步渗透，整体就业影响尚不显著",
            "50":  "AI 开始替代中等技能工作，部分行业出现结构性失业压力",
            "75":  "大规模职业替代，工资增长停滞，不平等加速扩大",
            "100": "技术扰动引发系统性失业危机，社会保障体系承压",
        },
        "mc_impact": "高分 → 劳动力市场对利率冲击敏感性上升",
    },
    "climate_physical_risk": {
        "zh": "气候物理风险",
        "desc": "气候物理风险对粮食、能源、基础设施的传导压力（当前至未来12个月）",
        "anchors": {
            "0":   "气候平稳，无显著农业减产或能源中断",
            "25":  "局部极端天气，小幅影响特定农业区",
            "50":  "多个农业区受干旱/洪涝影响，粮食价格有压力",
            "75":  "显著 El Niño/La Niña，全球粮食供应受扰，移民压力上升",
            "100": "多重极端气候叠加，引发系统性粮食危机和能源冲击",
        },
        "mc_impact": "高分 → 油价→CPI 传导系数增强，新兴市场社会稳定性降低",
    },
    "financial_fragility": {
        "zh": "金融体系脆弱性",
        "desc": "银行体系健康度、信贷周期位置、影子银行风险与资产质量（当前至未来12个月）",
        "anchors": {
            "0":   "银行资本充足，信用利差正常，信贷周期早期，无系统性压力",
            "25":  "局部压力（如商业地产），但整体可控，信用利差小幅扩大",
            "50":  "信贷标准开始收紧，部分机构压力上升，信贷/GDP缺口接近警戒（历史基准）",
            "75":  "多领域信贷紧缩，信用利差显著扩大，影子银行或NPL压力显现",
            "100": "系统性银行业危机，信贷冻结，类2008年或亚洲危机水平",
        },
        "mc_impact": "高分 → 危机概率显著上调，信贷收缩 GDP 乘数下降，传导系数增大",
    },
    "demographic_pressure": {
        "zh": "人口老龄化压力",
        "desc": "主要经济体人口结构压力：老龄化速度、生育率、劳动参与率下降对潜在增速的拖累（5-10年视野）",
        "anchors": {
            "0":   "人口红利持续释放，劳动参与率高，生育率接近更替水平（印度/越南当前）",
            "25":  "轻度老龄化，移民或政策可缓冲，劳动力仍净增长",
            "50":  "老龄化明显但尚可管理，劳动参与率温和下降（历史基准）",
            "75":  "劳动年龄人口绝对减少，养老金财政压力大，消费结构老龄化",
            "100": "极端老龄化（日本/韩国水平），劳动力骤减，财政失衡加速，人口开始负增长",
        },
        "mc_impact": "高分 → 潜在 GDP 增速上限下调，养老财政拖累消费，长期增长天花板下移",
    },
}


# ── 知识库上下文 ───────────────────────────────────────────────────────────────
def _read_kb_context() -> str:
    """读取知识库中用于结构评估的 4 个关键文档（每个截取前 2500 字符），找不到则返回提示字符串。"""
    kb_root = os.environ.get("KB_ROOT") or os.path.join(WORKSPACE, "知识库")
    kb_dir  = os.path.join(kb_root, "财经知识库")
    targets = [
        os.path.join(kb_dir, "专题报告", "2026全球宏观基准情景.md"),
        os.path.join(kb_dir, "中国", "中国信用脉冲与房地产周期.md"),
        os.path.join(kb_dir, "专题报告", "15_金融体系脆弱性.md"),
        os.path.join(kb_dir, "专题报告", "16_人口结构与劳动力.md"),
    ]
    chunks = []
    for path in targets:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                chunks.append(f"### {os.path.basename(path)}\n{f.read()[:2500]}")
    return ("\n\n---\n\n".join(chunks) if chunks
            else "（知识库文档未找到，请基于当前公开信息评估。"
                 "如需建立自己的知识库，运行 python3 scripts/init_kb.py，"
                 "详见 docs/KB_SETUP.md）")


# ── 评估 Prompt ────────────────────────────────────────────────────────────────
def _build_prompt(context: str) -> str:
    """拼装给 Claude 的结构评估 prompt（注入知识库上下文 + 六维评分标准 + JSON 输出格式）。"""
    today     = date.today().isoformat()
    valid_end = (date.today() + timedelta(days=VALIDITY_DAYS)).isoformat()

    rubric_text = ""
    for key, dim in DIMENSION_RUBRICS.items():
        anchors = "\n".join(f"      {s}分: {d}" for s, d in dim["anchors"].items())
        rubric_text += f"\n**{dim['zh']}（{key}）**\n定义: {dim['desc']}\n评分锚点:\n{anchors}\nMC影响: {dim['mc_impact']}\n"

    return f"""你是一位严谨的全球宏观分析师，正在为量化世界推演系统进行季度结构层评估。

今日日期: {today}

## 背景知识（来自系统知识库）

{context}

## 评估任务

对以下六个结构维度评分（0-100），视野为当前至未来12个月（人口维度为5-10年）。
{rubric_text}

## 输出要求

只输出合法 JSON，不要加任何说明文字或代码块标记：

{{
  "assessed_at": "{today}",
  "dimensions": {{
    "political_stability":   {{"score": <整数>, "confidence": "<high|medium|low>", "key_factors": ["<因素1>","<因素2>","<因素3>"], "reasoning": "<2-3句判断依据>"}},
    "social_cohesion":       {{"score": <整数>, "confidence": "<high|medium|low>", "key_factors": ["<因素1>","<因素2>","<因素3>"], "reasoning": "<2-3句判断依据>"}},
    "tech_disruption":       {{"score": <整数>, "confidence": "<high|medium|low>", "key_factors": ["<因素1>","<因素2>","<因素3>"], "reasoning": "<2-3句判断依据>"}},
    "climate_physical_risk": {{"score": <整数>, "confidence": "<high|medium|low>", "key_factors": ["<因素1>","<因素2>","<因素3>"], "reasoning": "<2-3句判断依据>"}},
    "financial_fragility":   {{"score": <整数>, "confidence": "<high|medium|low>", "key_factors": ["<因素1>","<因素2>","<因素3>"], "reasoning": "<2-3句判断依据>"}},
    "demographic_pressure":  {{"score": <整数>, "confidence": "<high|medium|low>", "key_factors": ["<因素1>","<因素2>","<因素3>"], "reasoning": "<2-3句判断依据>"}}
  }},
  "composite_fragility": <0-100整数，权重：政治25%+社会25%+气候20%+技术10%+金融15%+人口5%，50=历史均值>,
  "valid_until": "{valid_end}",
  "assessment_notes": "<整体主要不确定性，1-2句>"
}}"""


# ── LLM 调用 ──────────────────────────────────────────────────────────────────
def _call_anthropic(prompt: str, api_key: str) -> str:
    """直接调用 Anthropic messages API（claude-sonnet-4-6，max_tokens=2048，走企业代理）。"""
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        },
        proxies=_API_PROXY,
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Anthropic API 错误 {resp.status_code}: {resp.text[:300]}")
    return resp.json()["content"][0]["text"]


def _parse_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON；先尝试直接 parse，再用 regex 定位 {} 块。"""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        return json.loads(m.group())
    raise ValueError(f"无法从响应提取 JSON:\n{text[:400]}")


# ── 主评估流程 ─────────────────────────────────────────────────────────────────
def run_assessment(force: bool = False) -> dict:
    """执行季度结构评估：读 KB → 构建 prompt → 调用 Claude → 写 JSON 结果。
    有效期内（VALIDITY_DAYS）自动跳过，force=True 可强制重评。"""
    if not force and os.path.exists(STRUCTURAL_PRIORS_FILE):
        with open(STRUCTURAL_PRIORS_FILE, encoding="utf-8") as f:
            existing = json.load(f)
        if date.today().isoformat() <= existing.get("valid_until", "2000-01-01"):
            print(f"[结构评估] 当前评估有效至 {existing['valid_until']}，跳过（--force 可强制重评）")
            return existing

    api_key = ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[结构评估] 未设置 ANTHROPIC_API_KEY，跳过。")
        return {}

    print(f"[结构评估] 开始季度评估（{date.today().isoformat()}）...")
    context = _read_kb_context()
    prompt  = _build_prompt(context)

    print("  调用 LLM 评估六个结构维度...")
    raw    = _call_anthropic(prompt, api_key)
    priors = _parse_json(raw)
    priors["assessment_model"] = "claude-sonnet-4-6"

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STRUCTURAL_PRIORS_FILE, "w", encoding="utf-8") as f:
        json.dump(priors, f, ensure_ascii=False, indent=2)

    # 追加历史记录（用于追踪季度漂移趋势）
    history_file = os.path.join(DATA_DIR, "structural_priors_history.jsonl")
    with open(history_file, "a", encoding="utf-8") as hf:
        hf.write(json.dumps(priors, ensure_ascii=False) + "\n")

    _print_summary(priors)
    return priors


def _print_summary(priors: dict) -> None:
    """打印结构评估摘要表（六维得分 + 综合脆弱性指数 + 主要不确定性）。"""
    dims = priors.get("dimensions", {})
    sep  = "─" * 52
    print(f"\n{sep}")
    print(f"  结构层评估  {priors.get('assessed_at', '?')}  →  有效至 {priors.get('valid_until', '?')}")
    print(f"  综合脆弱性：{priors.get('composite_fragility', '?')}/100  "
          f"（50=历史均值，越高越脆弱）")
    print(sep)
    for key, dim_def in DIMENSION_RUBRICS.items():
        d     = dims.get(key, {})
        score = d.get("score", "?")
        conf  = d.get("confidence", "?")
        rsn   = d.get("reasoning", "")[:55]
        print(f"  {dim_def['zh']:12s}  {str(score):>3}/100  [{conf}]  {rsn}...")
    print(sep)
    if priors.get("assessment_notes"):
        print(f"  注: {priors['assessment_notes']}")
    print()


# ── MC 集成接口（供 run_macro_analysis.py 调用） ───────────────────────────────
def load_structural_priors() -> dict:
    """读取结构先验；若文件不存在或过期超过30天宽限期则返回 {}"""
    if not os.path.exists(STRUCTURAL_PRIORS_FILE):
        return {}
    try:
        with open(STRUCTURAL_PRIORS_FILE, encoding="utf-8") as f:
            priors = json.load(f)
        grace = (date.today() - timedelta(days=30)).isoformat()
        if priors.get("valid_until", "2000-01-01") < grace:
            return {}
        return priors
    except Exception:
        return {}


def compute_structural_mc_adjustments(priors: dict) -> dict:
    """
    将结构先验转换为 MC 传导系数调整量。

    返回键：
      crisis_prob_adj    — 危机概率加成（加到 _crisis_prob）
      gdp_drag_adj       — GDP 拖累（%，正值=拖累）
      oil_cpi_mult       — 油价→CPI 传导系数乘数（1.0=不调整）
      unrate_sensitivity — 利率→失业率传导系数乘数（1.0=不调整）
      potential_gdp_drag — 潜在 GDP 增速结构性拖累（人口老龄化，正值=拖累）
    """
    if not priors:
        return {}

    dims = priors.get("dimensions", {})
    pol  = dims.get("political_stability",  {}).get("score", 50)
    soc  = dims.get("social_cohesion",      {}).get("score", 70)
    tech = dims.get("tech_disruption",      {}).get("score", 40)
    clim = dims.get("climate_physical_risk",{}).get("score", 40)
    fin  = dims.get("financial_fragility",  {}).get("score", 45)
    dem  = dims.get("demographic_pressure", {}).get("score", 50)

    # 政治脆弱（低于基准50分）+ 金融脆弱（高于基准45分）共同推高危机概率
    # 各自最大贡献 8% 和 8%，叠加上限 12%
    pol_contrib = round((50 - pol) / 50 * 0.08, 3)
    fin_contrib = round(max(0.0, (fin - 45) / 55 * 0.08), 3)
    crisis_prob_adj = round(min(0.12, pol_contrib + fin_contrib), 3)

    return {
        "crisis_prob_adj":    crisis_prob_adj,
        # 社会撕裂（低于基准70分）+ 人口压力（高于基准50分）叠加 GDP 拖累，最大 0.6%
        "gdp_drag_adj":       round(min(0.6, max(0.0, (70 - soc) / 100 * 0.4)
                                            + max(0.0, (dem - 50) / 100 * 0.2)), 3),
        # 气候风险（高于基准40分），油价通胀传导增强，最大 1.5x
        "oil_cpi_mult":       round(1.0 + max(0.0, (clim - 40) / 100 * 0.5), 2),
        # 技术扰动（高于基准40分），劳动力市场利率敏感性上升，最大 1.3x
        "unrate_sensitivity": round(1.0 + max(0.0, (tech - 40) / 100 * 0.3), 2),
        # 人口老龄化（高于基准50分），潜在 GDP 增速结构性下调，最大约 -0.5ppt（dem=100时）
        "potential_gdp_drag": round(max(0.0, (dem - 50) / 100 * 1.0), 3),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="结构层季度评估")
    parser.add_argument("--force", action="store_true", help="强制重新评估（忽略有效期）")
    parser.add_argument("--show",  action="store_true", help="只显示当前分数，不重评")
    args = parser.parse_args()

    if args.show:
        p = load_structural_priors()
        if p:
            _print_summary(p)
            adj = compute_structural_mc_adjustments(p)
            print("MC 传导系数调整量:")
            for k, v in adj.items():
                print(f"  {k}: {v}")
        else:
            print("尚无有效的结构评估文件。运行不带 --show 的命令生成。")
        sys.exit(0)

    run_assessment(force=args.force)
