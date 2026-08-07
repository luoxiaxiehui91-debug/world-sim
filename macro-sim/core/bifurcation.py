"""
bifurcation.py — 路径分叉检测 + Monte Carlo 预测循环

流程：
  1. 用校准后的 Agent 参数，从当前真实状态出发
  2. Monte Carlo × 100，每次给初始内生变量加微小随机扰动
  3. 每步检测 grv 和 market_sentiment 的分布形状（双峰 → 分叉点）
  4. 按聚类分组（最多3条路径，低于10%的不展开）
  5. 每条路径提取关键节点 + LLM 生成叙事
"""

import copy
import json
import random
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.world_state import MacroWorldState, apply_sentiment_delta
from core.simulation import MacroSimModel, load_agents
from core.agents.base import AgentParams


def _get_military_backdrop_snippet() -> str:
    """读取 SIPRI 军事背景卡片的摘要段（前600字符），注入推演叙事 prompt。"""
    try:
        import os
        path = os.path.join(
            os.environ.get("OPENCLAW_WORKSPACE", "/workspace"),
            "data", "static", "military_backdrop.md"
        )
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # 只取核心数据段，避免 token 过长
        lines = [l for l in content.split("\n") if l.strip() and not l.startswith("#") and not l.startswith(">")]
        snippet = "\n".join(lines[:15])[:600]
        return f"\n【军事结构背景参考（SIPRI）】\n{snippet}\n\n"
    except Exception:
        return ""


@dataclass
class PathResult:
    """一条演化路径的完整结果"""
    label: str              # "路径A", "路径B", "路径C"
    probability: float      # 该路径占 Monte Carlo 总次数的比例
    run_indices: list[int]  # 属于该路径的 run 编号
    # 关键节点：(步数, agent_role, action, 说明)
    key_events: list[dict] = field(default_factory=list)
    # 终态统计
    final_grv_mean: float = 0.0
    final_grv_std: float = 0.0
    initial_grv_mean: float = 0.0   # 该路径的真实起点 GRV（受扰动影响）
    final_sentiment_mean: float = 0.0
    final_credit_spread_mean: float = 0.0
    grv_trend: str = ""        # "持续上升" / "先升后降" / "回落" / "横盘"
    narrative: str = ""        # LLM 生成
    consistency_warning: str = ""  # 非空时表示该路径有较多 run 检测到行动矛盾
    # 逐月演化数据（step 0 = 第1个月）
    monthly_grv: list[float] = field(default_factory=list)           # 每步路径均值 GRV
    monthly_sentiment: list[float] = field(default_factory=list)     # 每步路径均值 sentiment


MIN_PATH_PROBABILITY = 0.05   # 低于此概率的路径不展开（设计文档确认10%，实测降至5%）


def _add_initial_noise(world: MacroWorldState, seed: int) -> MacroWorldState:
    """
    给初始状态加随机扰动，制造路径多样性。

    两层扰动：
    1. 内生变量：微小初始差异
    2. 外生变量起点：GRV/利差也加扰动，反映"当前读数本身的不确定性"
       以及不同假设场景（乐观起点 vs 悲观起点）
    """
    rng = random.Random(seed)
    w = copy.deepcopy(world)

    # 内生变量扰动
    noise_config = {
        "market_sentiment":       0.15,
        "bank_credit_tightening": 0.05,
        "fund_risk_appetite":     0.08,
        "liquidity_premium":      0.04,
        "energy_supply_risk":     0.05,
        "em_capital_outflow":     0.05,
        "retail_panic":           0.08,
        "china_credit_impulse":   0.10,
        "us_fiscal_pressure":     0.05,
        "yen_carry_risk":         0.06,
    }
    for var, scale in noise_config.items():
        current = getattr(w, var, 0.0)
        noise   = rng.gauss(0, scale)
        if var == "china_credit_impulse":
            setattr(w, var, max(-1.0, min(1.0, current + noise)))
        else:
            setattr(w, var, max(0.0, min(1.0, current + noise)))

    # 外生变量扰动：反映起点不确定性 + 模拟不同宏观情景
    # GRV：±8点（约历史月度波动1σ），制造"地缘紧张加剧 vs 缓和"两种起点
    w.grv          = max(0.0, w.grv          + rng.gauss(0, 8.0))
    w.grv_baseline = max(0.0, w.grv_baseline + rng.gauss(0, 4.0))
    w.grv_energy   = max(0.0, w.grv_energy   + rng.gauss(0, 5.0))
    # 利率/利差：±15bp
    w.t10y2y       = w.t10y2y       + rng.gauss(0, 15.0)
    w.credit_spread = max(100.0, w.credit_spread + rng.gauss(0, 15.0))
    # VIX 基线也跟着 GRV 调整
    w.vix          = max(10.0, 15.0 + w.grv * 0.15 + rng.gauss(0, 1.5))
    w.vix_baseline = max(10.0, 15.0 + w.grv_baseline * 0.15)

    w.sim_id = f"mc_{seed}"
    return w


def _detect_bifurcation(grv_series: list[list[float]]) -> Optional[int]:
    """
    在每步检测 GRV 分布是否出现双峰（简化版双峰检测）。
    grv_series[step][run] = grv 值
    返回第一个分叉步，None 表示无明显分叉。
    """
    n_steps = len(grv_series)
    for step in range(5, n_steps):   # 前5步不检测（太早）
        vals = grv_series[step]
        if len(vals) < 10:
            continue
        mean = statistics.mean(vals)
        std  = statistics.stdev(vals)
        if std < 2.0:
            continue   # 分布太紧，不是双峰

        # 简化双峰检测：看均值两侧各1σ范围内的点数是否都超过15%
        left_count  = sum(1 for v in vals if v < mean - std * 0.5)
        right_count = sum(1 for v in vals if v > mean + std * 0.5)
        n = len(vals)
        if left_count / n > 0.15 and right_count / n > 0.15:
            return step

    return None


def _cluster_runs(final_grv_values: list[float], n_clusters: int = 2) -> list[list[int]]:
    """
    简单 k-means 按 GRV 终值聚类，返回每个簇的 run 索引列表。
    最多允许3个簇，低于10%的簇会被合并到最近的簇。
    """
    if not final_grv_values:
        return []

    n = len(final_grv_values)
    indexed = sorted(enumerate(final_grv_values), key=lambda x: x[1])
    sorted_vals = [v for _, v in indexed]
    sorted_idx  = [i for i, _ in indexed]

    # 找自然断点（相邻差值最大的位置）
    diffs = [sorted_vals[i+1] - sorted_vals[i] for i in range(len(sorted_vals)-1)]

    if n_clusters == 2:
        split_at = [diffs.index(max(diffs))]
    else:  # 3 clusters
        top2 = sorted(range(len(diffs)), key=lambda i: -diffs[i])[:2]
        split_at = sorted(top2)

    clusters = []
    prev = 0
    for sp in split_at:
        clusters.append(sorted_idx[prev:sp+1])
        prev = sp + 1
    clusters.append(sorted_idx[prev:])

    # 过滤低于10%的簇
    filtered = [c for c in clusters if len(c) / n >= MIN_PATH_PROBABILITY]
    if not filtered:
        filtered = [list(range(n))]

    return filtered


def _extract_key_events(history_list: list[list[dict]], run_indices: list[int]) -> list[dict]:
    """
    从该路径的所有 run 里提取出现频率最高的关键行动（出现 > 40% 的 run 才算）。
    返回按步数排序的关键节点列表，每条记录含 agent_id 字段，供报告做归因展示。
    """
    # Agent ID → 简短角色名（供报告展示用）
    AGENT_NAMES = {
        "A1": "Fed",       "A2": "商业银行",     "A3": "对冲基金",
        "A4": "能源国",    "A5": "机构",          "A6": "媒体",
        "A7": "新兴市场央行", "A8": "PBOC",       "A9": "美财政",
        "A10": "散户",     "A11": "ECB",          "A12": "BOJ",
        # v2.2 A 类主权 Agent（S 编号体系）
        "S1_usa": "美国",  "S2_china": "中国",    "S3_eu": "欧盟",
        "S4_russia": "俄罗斯", "S5_saudi": "沙特-OPEC",
    }

    n_runs   = len(run_indices)
    # action_counts[step][agent_role:action] = 出现次数
    from collections import Counter
    step_counts: dict[int, Counter] = {}

    for run_i in run_indices:
        if run_i >= len(history_list):
            continue
        history = history_list[run_i]
        for snap in history:
            step = snap["cycle"]
            for agent_id, action in snap.get("actions", {}).items():
                if action in ("HOLD", "NO_ACTION"):
                    continue
                key = f"{agent_id}:{action}"
                if step not in step_counts:
                    step_counts[step] = Counter()
                step_counts[step][key] += 1

    key_events = []
    action_labels = {
        "A1:CUT_50BP":            "美联储紧急降息50bp",
        "A1:CUT_25BP":            "美联储降息25bp",
        "A1:HIKE_25BP":           "美联储加息25bp",
        "A1:VERBAL_INTERVENTION": "美联储口头干预",
        "A2:TIGHTEN_CREDIT":      "商业银行收紧信贷",
        "A2:EASE_CREDIT":         "商业银行放松信贷",
        "A3:SHORT_MARKET":        "对冲基金大规模做空",
        "A3:DECREASE_RISK":       "对冲基金降险",
        "A3:INCREASE_RISK":       "对冲基金加仓做多",
        "A4:CUT_SUPPLY":          "OPEC+减产",
        "A4:INCREASE_SUPPLY":     "OPEC+增产",
        "A5:DECREASE_RISK":       "机构投资者降险",
        "A5:INCREASE_RISK":       "机构投资者加仓",
        "A6:AMPLIFY_FEAR":        "媒体放大恐慌情绪",
        "A6:NEUTRAL_REPORT":      "媒体保持中性报道",
        "A6:AMPLIFY_OPTIMISM":    "媒体放大乐观情绪",
        "A7:CAPITAL_CONTROLS":    "新兴市场实施资本管制",
        "A7:RAISE_RATES":         "新兴市场央行加息",
        "A7:CUT_25BP":            "新兴市场央行降息",
        "A8:CUT_RRR":             "中国央行降准",
        "A8:CUT_LPR":             "中国央行降LPR",
        "A8:FISCAL_STIMULUS_CN":  "中国财政大规模刺激",
        "A8:CNY_INTERVENTION":    "中国央行汇率干预",
        "A8:TIGHTEN_CN":          "中国货币政策收紧",
        "A9:FISCAL_STIMULUS":     "美国财政刺激",
        "A9:DEBT_CEILING_RISK":   "美国债务上限危机信号",
        "A9:FISCAL_TIGHTEN":      "美国财政收紧",
        "A10:PANIC_SELL":         "散户恐慌性抛售",
        "A10:FOMO_BUY":           "散户追涨买入",
        "A11:CUT_25BP":           "欧央行降息25bp",
        "A11:HIKE_25BP":          "欧央行加息25bp",
        "A11:QE_EXPAND":          "欧央行扩大QE",
        "A11:QE_TIGHTEN":         "欧央行缩减QE",
        "A12:ABANDON_YCC":        "日本央行放弃YCC（套息危机）",
        "A12:EASE_YCC":           "日本央行放松YCC上限",
        "A12:EMERGENCY_EASE":     "日本央行紧急宽松",
    }

    for step in sorted(step_counts.keys()):
        for key, count in step_counts[step].most_common(2):
            if count / n_runs > 0.40:   # 超过40%的run出现此事件
                agent_id, action = key.split(":", 1)
                label = action_labels.get(key, f"{agent_id}:{action}")
                key_events.append({
                    "step":       step,
                    "month":      f"第{step+1}个月",
                    "agent_id":   agent_id,
                    "agent_name": AGENT_NAMES.get(agent_id, agent_id),
                    "action":     action,
                    "event":      label,
                    "frequency":  round(count / n_runs, 2),
                })

    return key_events[:8]   # 最多8个关键节点


def _generate_narrative(path: PathResult, world: MacroWorldState) -> str:
    """用 GLM-Z1-9B 为该路径生成叙事——含触发原因、因果链、整体定性"""
    try:
        from core.llm_client import call_llm

        # 构建带因果关系的事件描述
        TRIGGER_REASONS = {
            "对冲基金大规模做空":         f"GRV={world.grv:.0f} 超过高压阈值，机构判断风险上升",
            "对冲基金降险":               f"市场情绪恶化，降低风险敞口",
            "商业银行收紧信贷":           "对冲基金做空 / 散户恐慌引发流动性担忧",
            "散户恐慌性抛售":             "媒体放大恐慌 / 对冲基金做空信号外溢",
            "媒体放大恐慌情绪":           f"GRV 高位 + 市场情绪下行，负面报道增加",
            "媒体保持中性报道":           "GRV 未突破极端阈值，市场情绪相对平稳",
            "美联储降息25bp":             "市场情绪恶化、信用利差扩大，触发政策响应",
            "美联储紧急降息50bp":         "市场深度压力，触发紧急宽松",
            "美联储口头干预":             "GRV 高位但情绪尚可，言语安抚市场",
            "新兴市场实施资本管制":       "美元利率压力 + 信贷收紧引发资本外流",
            "日本央行放弃YCC（套息危机）": "美联储加息压力积累，套息交易平仓触发",
            "中国财政大规模刺激":         "国内信用收缩，逆周期财政托底",
            "欧央行降息25bp":             "跟随美联储宽松周期",
            "OPEC+减产":                  "全球需求预期下降，能源国保价减产",
        }

        events_with_reasons = []
        for e in path.key_events:
            reason = TRIGGER_REASONS.get(e["event"], "")
            reason_str = f"（原因：{reason}）" if reason else ""
            events_with_reasons.append(
                f"  第{e['step']+1}个月：{e['event']}{reason_str} — {e['frequency']:.0%}路径出现"
            )
        if events_with_reasons:
            events_str = "\n".join(events_with_reasons)
        else:
            events_str = "  无显著事件"

        grv_range = f"GRV {path.initial_grv_mean:.0f}->{path.final_grv_mean:.0f}({path.grv_trend})"
        sent_final = f"sentiment={path.final_sentiment_mean:+.2f}"
        spread_final = f"spread={path.final_credit_spread_mean:.0f}bp"

        prompt = (
            "你是宏观风险分析师，解读一条Monte Carlo仿真路径。\n\n"
            f"起始：GRV={world.grv:.1f}，spread={world.credit_spread:.0f}bp，"
            f"t10y2y={world.t10y2y:.0f}bp，dff={world.dff:.2f}%\n"
            f"路径概率：{path.probability:.0%}\n"
            f"24个月走势：{grv_range}，{sent_final}，{spread_final}\n\n"
            f"关键事件（含触发原因）：\n{events_str}\n\n"
            + (_get_military_backdrop_snippet()) +
            "请按以下结构输出，每项一句话，共3句：\n"
            "1. **情景定性** 这条路径是什么性质（金融危机/慢性高压/政策托底/平稳缓和等）\n"
            "2. **核心传导链** 谁触发了谁，怎么演化的\n"
            "3. **对你的影响** 投资者需要警惕什么\n"
            "不要重复数字，语言直接简洁。"
        )

        raw = call_llm(prompt, use_minimax=False)
        if not raw:
            return ""
        return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    except Exception as e:
        print(f"  [bifurcation] 叙事生成失败：{e}")
        return ""


def run_prediction(
    initial_world: MacroWorldState,
    calibrated_agent_params: dict,   # {agent_id: {sensitivity, threshold, magnitude}}
    n_runs: int = 100,
    predict_steps: int = 24,
    config_path: str = "/app/config/agents.yaml",
    bleed_params_override: dict = None,
) -> list[PathResult]:
    """
    预测循环主函数。
    返回路径列表（已过滤低概率路径，按概率降序）。
    """
    print(f"\n[bifurcation] 预测循环：{n_runs}次 × {predict_steps}步")

    # v2.2 A5：Board 基线预置（GRV 派生，/100 归一化；跨仿真的每日基线）
    try:
        from core.board_baseline import derive_board_baseline
        _grv_dim = getattr(initial_world, "grv_dimensions", None) or {}
        derive_board_baseline(_grv_dim or {})
        print(f"[bifurcation] Board 基线已预置（{len(_grv_dim)} 个 GRV 维度）")
    except Exception as e:
        print(f"[bifurcation] Board 基线预置跳过：{e}")

    # 加载 Agent 并应用校准后的参数
    agents_template, _global_cfg = load_agents(config_path)
    for agent_id, params_dict in calibrated_agent_params.items():
        if agent_id in agents_template:
            agents_template[agent_id].params = AgentParams.from_dict(params_dict)

    all_histories: list[list[dict]] = []
    grv_by_step: list[list[float]] = [[] for _ in range(predict_steps)]

    for run_i in range(n_runs):
        random.seed(run_i)
        world = _add_initial_noise(initial_world, seed=run_i)
        world.total_cycles = predict_steps
        agents = copy.deepcopy(agents_template)
        model  = MacroSimModel(world, agents=agents, use_llm=False,
                               bleed_params_override=bleed_params_override)
        history = model.run()

        # 一致性校验：检查该 run 是否存在跨 Agent 行动矛盾
        from core.consistency_validator import validate_run_actions
        run_issues = validate_run_actions(history, use_llm=False)
        if run_issues:
            if history:
                history[-1]["_consistency_issues"] = run_issues

        all_histories.append(history)

        for step_i, snap in enumerate(history):
            grv_by_step[step_i].append(snap["grv"])

        if (run_i + 1) % 20 == 0:
            print(f"  完成 {run_i+1}/{n_runs}...")

    # 检测分叉点
    bifurcation_step = _detect_bifurcation(grv_by_step)
    if bifurcation_step is not None:
        print(f"  检测到分叉点：第 {bifurcation_step+1} 个月")
    else:
        print(f"  未检测到明显分叉，按终态 GRV 聚类")

    # 用终态 sentiment 聚类（比 GRV 更能区分路径方向）
    final_sent_values = [h[-1]["market_sentiment"] for h in all_histories]
    final_grv_values  = [h[-1]["grv"] for h in all_histories]
    sent_std = statistics.stdev(final_sent_values)
    grv_std  = statistics.stdev(final_grv_values)

    print(f"  终态分布：sentiment std={sent_std:.3f}，GRV std={grv_std:.2f}")

    # 决定聚类数量：用两个维度中分散度更大的
    # 2026-08-06 路径多样性修复：sentiment 主判据阈值 0.05 → 0.15——
    # sentiment 带 0.995 衰减 + damping 均值回归，std 常态 <0.15（如 0.131），
    # 强制用 sentiment 聚类导致路径 B 簇 <5% 被 MIN_PATH_PROBABILITY 过滤（坍缩假象）。
    # GRV 才是"风险路径"语义维度（std=4.8 真实分歧），sentiment std <0.15 时改用 GRV 聚类。
    primary_vals = final_sent_values if sent_std > 0.15 else final_grv_values
    primary_std  = sent_std if sent_std > 0.15 else grv_std

    if primary_std < 0.05:
        n_clusters = 1
    elif primary_std < 0.20:
        n_clusters = 2
    else:
        n_clusters = 3

    clusters = _cluster_runs(primary_vals, n_clusters=n_clusters)
    path_labels = ["路径A", "路径B", "路径C"]

    paths = []
    for ci, cluster in enumerate(clusters):
        prob = len(cluster) / n_runs
        if prob < MIN_PATH_PROBABILITY:
            continue

        label = path_labels[ci] if ci < len(path_labels) else f"路径{ci+1}"

        # 统计该路径的终态
        final_grv_vals   = [all_histories[i][-1]["grv"] for i in cluster]
        final_sent_vals  = [all_histories[i][-1]["market_sentiment"] for i in cluster]
        final_spread_vals = [all_histories[i][-1]["credit_spread"] for i in cluster]

        # GRV 趋势判断
        grv_vals_path = [
            statistics.mean([all_histories[i][step]["grv"] for i in cluster])
            for step in range(predict_steps)
        ]
        sent_vals_path = [
            statistics.mean([all_histories[i][step]["market_sentiment"] for i in cluster])
            for step in range(predict_steps)
        ]
        grv_start = grv_vals_path[0]
        grv_mid   = grv_vals_path[predict_steps // 2]
        grv_end   = grv_vals_path[-1]
        if grv_end > grv_start + 5:
            trend = "持续上升"
        elif grv_end < grv_start - 5:
            trend = "持续回落"
        elif grv_mid > grv_start + 5 and grv_end < grv_mid - 3:
            trend = "先升后降"
        else:
            trend = "基本横盘"

        path = PathResult(
            label=label,
            probability=round(prob, 2),
            run_indices=cluster,
            initial_grv_mean=round(grv_start, 1),
            final_grv_mean=round(statistics.mean(final_grv_vals), 1),
            final_grv_std=round(statistics.stdev(final_grv_vals) if len(final_grv_vals) > 1 else 0, 1),
            final_sentiment_mean=round(statistics.mean(final_sent_vals), 3),
            final_credit_spread_mean=round(statistics.mean(final_spread_vals), 1),
            grv_trend=trend,
            monthly_grv=[round(v, 1) for v in grv_vals_path],
            monthly_sentiment=[round(v, 3) for v in sent_vals_path],
        )

        path.key_events = _extract_key_events(all_histories, cluster)

        # 汇总该路径内有矛盾的 run 比例
        issue_run_count = sum(
            1 for i in cluster
            if (i < len(all_histories)
                and all_histories[i]
                and all_histories[i][-1].get("_consistency_issues"))
        )
        if issue_run_count > len(cluster) * 0.3:
            path.consistency_warning = (
                f"{issue_run_count}/{len(cluster)} runs 检测到 Agent 行动逻辑矛盾"
            )

        path.narrative  = _generate_narrative(path, initial_world)
        paths.append(path)
        print(f"  {label}（{prob:.0%}）：GRV {grv_start:.1f}→{grv_end:.1f}，{trend}")

    # 按概率降序排列
    paths.sort(key=lambda p: -p.probability)
    return paths
