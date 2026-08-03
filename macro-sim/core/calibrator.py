"""
calibrator.py — 前50步校准循环

流程：
  1. 加载最近50个月历史数据
  2. 逐月跑仿真，每步结束后对比真实外生变量
  3. 误差 > 阈值时调用 GLM-Z1-9B 分析偏差，输出参数调整指令
  4. 记录每步误差和参数变更到 calibration_log.jsonl
  5. 返回校准质量评分（0~100）和校准后的 Agent 参数

D2/D3 fix（2026-08-03）：
  原误差函数测量的全是外生变量（grv/credit_spread/t10y2y/dff），Agent 行动
  物理上无法改变 GRV，导致 LLM 调参方向系统性错误。
  修复后改为测量内生变量（market_sentiment/bank_credit_tightening/
  liquidity_premium/em_capital_outflow），这些变量直接由 Agent 行动驱动。

  "期望值"计算逻辑：
  - 从相邻两月 GRV/t10y2y/credit_spread 变化方向推导内生变量应有的方向
  - 例如 GRV↑ → market_sentiment 应该下降（负相关），credit_spread↑ → bank_credit_tightening↑
  - 期望值 = 前一步实际内生变量 × 方向系数 × 强度
  - 使用方向误差（符号不对 = 大误差），而非绝对值误差
"""

import copy
import json
import os
import re
import statistics
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.world_state import (
    MacroWorldState,
    load_monthly_history,
    make_world_from_history_row,
)
from core.simulation import MacroSimModel, load_agents


# D2/D3 fix：误差目标改为内生变量，这些变量由 Agent 行动直接驱动
# GRV/dff 已移除（外生变量，Agent 无法改变，测量无意义）
ERROR_WEIGHTS = {
    "market_sentiment":       0.35,  # 市场情绪，最多 Agent 直接影响
    "bank_credit_tightening": 0.30,  # 信贷紧缩，商业银行/美联储 Agent 驱动
    "liquidity_premium":      0.20,  # 流动性溢价，对冲基金/机构 Agent 驱动
    "em_capital_outflow":     0.15,  # 新兴市场资本外流，多 Agent 联合驱动
}

# 外生变量列表（Teacher Forcing 只注入这些，不覆盖内生变量）
EXOGENOUS_VARS = {"grv", "credit_spread", "t10y2y", "dff",
                  "grv_energy", "us_china_grv", "vix"}

ERROR_THRESHOLD = 0.20   # 内生变量误差阈值（比外生变量稍宽松，因目标是方向而非精确值）
CALIB_LOG_PATH  = Path("/app/output/calibration_log.jsonl")


def _derive_endogenous_targets(prev_row: dict, curr_row: dict) -> dict:
    """
    从相邻两月外生变量变化推导内生变量的"期望方向目标"。

    逻辑：
    - GRV↑ → market_sentiment 应下降（风险上升→情绪变坏）
    - credit_spread↑ → bank_credit_tightening 应上升（利差扩大→信贷收紧）
    - GRV↑ AND credit_spread↑ → liquidity_premium 应上升（双重压力→流动性溢价）
    - GRV↑ AND t10y2y↓ → em_capital_outflow 应上升（避险→新兴市场资金外流）

    返回值：{var: soft_target}
    soft_target 是 [-1, 1] 范围的期望值，代表"这个变量应该在哪个方向、多强"。
    误差 = |simulated - soft_target|，方向相反时惩罚更大。
    """
    grv_delta    = curr_row.get("grv", 50) - prev_row.get("grv", 50)
    cs_delta     = curr_row.get("credit_spread", 250) - prev_row.get("credit_spread", 250)
    t10y2y_delta = curr_row.get("t10y2y", -10) - prev_row.get("t10y2y", -10)

    # 归一化到 [-1, 1]（基于历史典型变化幅度）
    grv_signal    = max(-1.0, min(1.0, grv_delta / 10.0))      # ±10 分 GRV 变化视为满幅
    cs_signal     = max(-1.0, min(1.0, cs_delta / 50.0))       # ±50bp credit spread 变化视为满幅
    t10y2y_signal = max(-1.0, min(1.0, t10y2y_delta / 20.0))   # ±20bp 10Y2Y 变化视为满幅

    return {
        # GRV↑ → 情绪↓（负相关）；强度 × 0.5 因为情绪变化通常滞后且温和
        "market_sentiment":       -grv_signal * 0.5,

        # credit_spread↑ → 信贷收紧↑（正相关）
        "bank_credit_tightening": cs_signal * 0.6,

        # GRV↑ + credit_spread↑ → 流动性溢价↑（两信号叠加）
        "liquidity_premium":      (grv_signal * 0.4 + cs_signal * 0.3),

        # GRV↑ + t10y2y↓ → 新兴市场资本外流↑（避险 + 曲线倒挂双重压力）
        "em_capital_outflow":     (grv_signal * 0.4 - t10y2y_signal * 0.3),
    }


def compute_error(simulated: dict, targets: dict) -> float:
    """
    计算内生变量的加权方向误差。
    targets: 由 _derive_endogenous_targets 产生的 soft target（[-1,1]）。
    simulated: model.step() 快照中的内生变量值。

    误差计算：
    - 方向一致（同号）：线性误差
    - 方向相反（异号）：误差翻倍惩罚（鼓励方向正确优先于幅度准确）
    """
    total = 0.0
    for var, weight in ERROR_WEIGHTS.items():
        sim = simulated.get(var, 0.0)
        tgt = targets.get(var, 0.0)
        raw_err = abs(sim - tgt)
        # 方向相反时额外惩罚（sim 和 tgt 异号且都不为 0）
        if tgt != 0 and sim * tgt < 0:
            raw_err = min(raw_err * 1.5, 1.0)
        total += weight * min(raw_err, 1.0)
    return round(total, 4)


def build_history_range(history: list[dict]) -> dict:
    """从历史数据计算内生目标变量的范围（用于 LLM prompt 上下文，不再用于归一化）"""
    ranges = {}
    for var in ERROR_WEIGHTS:
        # 内生变量历史数据中没有真实记录，用 [-1, 1] 作为标准范围
        ranges[var] = (-1.0, 1.0)
    return ranges


def _call_llm_for_adjustment(
    agent_params_summary: dict,
    step_label: str,
    simulated: dict,
    targets: dict,
    error: float,
    error_history: list[dict] | None = None,
) -> list[dict]:
    """
    调用 GLM-Z1-9B 分析误差，返回参数调整指令列表。
    每条指令：{"agent": "A2", "param": "threshold", "old": 0.5, "new": 0.35, "reason": "..."}
    """
    try:
        from core.llm_client import call_llm

        # 找出偏差最大的内生变量
        deviations = []
        for var in ERROR_WEIGHTS:
            sim = simulated.get(var, 0.0)
            tgt = targets.get(var, 0.0)
            direction = "✓同向" if (tgt == 0 or sim * tgt >= 0) else "✗反向"
            deviations.append(
                f"  {var}: 仿真={sim:+.3f} 期望方向={tgt:+.3f} [{direction}]"
            )
        dev_str = "\n".join(deviations)

        params_str = json.dumps(agent_params_summary, ensure_ascii=False, indent=2)

        history_str = ""
        if error_history and len(error_history) > 1:
            history_lines = []
            for h in error_history:
                history_lines.append(
                    f"  步{h['step']}: 误差={h['error']:.3f}"
                    f" sentiment偏差={h['sentiment_delta']:+.3f}"
                    f" credit_tight偏差={h['credit_delta']:+.3f}"
                )
            errors = [h["error"] for h in error_history]
            mid = max(1, len(errors) // 2)
            trend_early = sum(errors[:mid]) / mid
            trend_late  = sum(errors[mid:]) / max(1, len(errors) - mid)
            if trend_late > trend_early + 0.03:
                trend_label = "⬆ 误差上升趋势（调参效果变差）"
            elif trend_late < trend_early - 0.03:
                trend_label = "⬇ 误差下降趋势（调参有效）"
            else:
                trend_label = "➡ 误差震荡/持平"
            history_str = (
                f"\n过去{len(error_history)}步误差序列：\n"
                + "\n".join(history_lines)
                + f"\n趋势：{trend_label}（前半均值={trend_early:.3f}，近半均值={trend_late:.3f}）\n"
            )

        prompt = (
            f"你是宏观仿真系统的校准专家。当前月份：{step_label}\n\n"
            f"内生变量仿真值 vs 期望方向（由GRV/利差变化推导）：\n{dev_str}\n\n"
            f"综合误差：{error:.3f}（>{ERROR_THRESHOLD}触发调整）\n"
            f"注意：误差标准是方向一致性，✗反向比幅度偏差更严重。\n"
            f"{history_str}\n"
            f"当前Agent参数：\n{params_str}\n\n"
            f"请分析：哪些Agent的参数导致内生变量方向错误？给出1-3条具体调整指令。\n"
            f"market_sentiment 主要由 A3(对冲基金)/A6(媒体)/A10(散户) 驱动。\n"
            f"bank_credit_tightening 主要由 A1(美联储)/A2(商业银行) 驱动。\n"
            f"liquidity_premium 主要由 A3/A5(机构投资者) 驱动。\n"
            f"em_capital_outflow 主要由 A7(新兴市场) 驱动。\n"
            f"每条指令格式（严格JSON数组）：\n"
            f'[{{"agent":"A2","param":"threshold","new":0.35,"reason":"信贷收紧触发太迟"}}]\n'
            f"只输出JSON数组。param只能是sensitivity/threshold/magnitude之一。"
        )

        raw = call_llm(prompt, use_minimax=False)
        if not raw:
            return []

        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not match:
            return []

        instructions = json.loads(match.group())
        valid = []
        for inst in instructions:
            if (isinstance(inst, dict)
                    and "agent" in inst
                    and "param" in inst
                    and "new" in inst
                    and inst["param"] in ("sensitivity", "threshold", "magnitude")
                    and 0.0 <= float(inst["new"]) <= 2.0):
                valid.append(inst)
        return valid

    except Exception as e:
        print(f"  [calibrator] LLM 调参失败（跳过）：{e}")
        return []


def run_calibration(
    grv_path:  str = "/app/macro_data/grv_history.jsonl",
    fred_path: str = "/app/macro_data/fred_history",
    calib_steps: int = 50,
    error_threshold: float = ERROR_THRESHOLD,
    config_path: str = "/app/config/agents.yaml",
) -> dict:
    """
    主校准函数。
    返回：{
      "score": 0~100,
      "agents": {agent_id: AgentParams.to_dict()},
      "error_series": [float × calib_steps],
      "param_changes": [{step, agent, param, old, new, reason}],
    }
    """
    print(f"[calibrator] 加载历史数据（最近{calib_steps}个月）...")
    history = load_monthly_history(grv_path, fred_path, months=calib_steps + 6)

    if len(history) < calib_steps:
        print(f"[calibrator] 历史数据不足：只有 {len(history)} 条，需要 {calib_steps} 条")
        calib_steps = len(history)

    history_range = build_history_range(history)
    calibration_data = history[-calib_steps:]
    baseline_row     = history[-(calib_steps + 1)] if len(history) > calib_steps else history[0]

    agents, _global_cfg = load_agents(config_path)
    initial_world = make_world_from_history_row(
        calibration_data[0], baseline_row, label=calibration_data[0]["date"]
    )
    initial_world.total_cycles = calib_steps

    model = MacroSimModel(initial_world, agents=agents, use_llm=False)

    error_series  = []
    param_changes = []
    error_history: deque = deque(maxlen=5)
    CALIB_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"[calibrator] 开始校准，{calib_steps} 步...")
    for i, row in enumerate(calibration_data):
        # D2/D3 fix: Teacher Forcing 只注入外生变量，不覆盖内生变量
        exogenous_inject = {
            k: v for k, v in row.items()
            if k in EXOGENOUS_VARS and hasattr(model.world, k)
        }

        # 先自由跑一步（Phase 1-3），然后注入外生变量
        snapshot = model.step(inject_world=exogenous_inject)
        simulated_values = {k: snapshot.get(k, 0.0) for k in ERROR_WEIGHTS}

        # D2/D3 fix: 误差目标改为内生变量期望方向（从相邻外生变量变化推导）
        prev_row = calibration_data[i - 1] if i > 0 else baseline_row
        endogenous_targets = _derive_endogenous_targets(prev_row, row)

        error = compute_error(simulated_values, endogenous_targets)
        error_series.append(error)
        error_history.append({
            "step":          i + 1,
            "error":         error,
            "sentiment_delta": simulated_values["market_sentiment"] - endogenous_targets["market_sentiment"],
            "credit_delta":    simulated_values["bank_credit_tightening"] - endogenous_targets["bank_credit_tightening"],
        })

        step_label = row["date"]
        print(
            f"  步 {i+1:02d}/{calib_steps} [{step_label}] 误差={error:.3f}"
            f"  sentiment={simulated_values['market_sentiment']:+.3f}"
            f"(期望{endogenous_targets['market_sentiment']:+.3f})",
            end=""
        )

        if error > error_threshold:
            print(f" ← 超阈值({error_threshold})，调参中...", end="")
            params_summary = {aid: agent.params.to_dict() for aid, agent in agents.items()}
            instructions = _call_llm_for_adjustment(
                params_summary, step_label, simulated_values, endogenous_targets, error,
                error_history=list(error_history),
            )
            for inst in instructions:
                agent_id = inst["agent"]
                param    = inst["param"]
                new_val  = float(inst["new"])
                reason   = inst.get("reason", "")
                if agent_id in agents:
                    old_val = getattr(agents[agent_id].params, param)
                    agents[agent_id].apply_param_adjustment(param, new_val)
                    change = {
                        "step": step_label, "agent": agent_id,
                        "param": param, "old": round(old_val, 3),
                        "new": round(new_val, 3), "reason": reason,
                    }
                    param_changes.append(change)
                    with open(CALIB_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(change, ensure_ascii=False) + "\n")
                    print(f"\n    → {agent_id}.{param}: {old_val:.3f} → {new_val:.3f}  ({reason})")
        else:
            print()

    avg_error = statistics.mean(error_series) if error_series else 1.0
    score = max(0, round(100 * (1 - avg_error / 0.5)))

    result = {
        "score":         score,
        "avg_error":     round(avg_error, 4),
        "agents":        {aid: a.params.to_dict() for aid, a in agents.items()},
        "error_series":  error_series,
        "param_changes": param_changes,
        "calib_steps":   calib_steps,
    }

    # D6 fix: 写校准缓存，下次启动时若 <7 天直接加载跳过50步校准
    try:
        cache_path = Path("/app/data/calibration_cache.json")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "score": score,
            "agents": result["agents"],
        }
        with open(cache_path, "w", encoding="utf-8") as _cf:
            json.dump(cache_data, _cf, ensure_ascii=False, indent=2)
        print(f"[calibrator] 校准缓存已写入 {cache_path}")
    except Exception as _ce:
        print(f"[calibrator] 缓存写入失败（非阻断）: {_ce}")

    print(f"\n[calibrator] 完成。评分：{score}/100，平均误差：{avg_error:.4f}")
    if score < 60:
        print(f"  ⚠️ 评分低于60，预测可信度有限")

    return result
import json
import os
import re
import statistics
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.world_state import (
    MacroWorldState,
    load_monthly_history,
    make_world_from_history_row,
)
from core.simulation import MacroSimModel, load_agents


# 误差权重（设计文档确认值，后续测试调整）
ERROR_WEIGHTS = {
    "grv":           0.4,
    "credit_spread": 0.3,
    "t10y2y":        0.2,
    "dff":           0.1,
}
ERROR_THRESHOLD = 0.15   # 超过此值触发参数调整
CALIB_LOG_PATH  = Path("/app/output/calibration_log.jsonl")


def compute_error(simulated: dict, actual: dict, history_range: dict) -> float:
    """
    计算加权归一化误差。
    history_range: {var: (min_val, max_val)} 用于归一化，避免不同量纲变量的影响。
    """
    total = 0.0
    for var, weight in ERROR_WEIGHTS.items():
        sim_val  = simulated.get(var, 0)
        act_val  = actual.get(var, 0)
        lo, hi   = history_range.get(var, (0, 1))
        denom    = max(hi - lo, 1e-6)
        err      = abs(sim_val - act_val) / denom
        total   += weight * min(err, 1.0)   # 单个误差最大贡献1.0
    return round(total, 4)


def build_history_range(history: list[dict]) -> dict:
    """从历史数据计算每个变量的范围，用于归一化"""
    ranges = {}
    for var in ERROR_WEIGHTS:
        vals = [row[var] for row in history if var in row]
        if vals:
            ranges[var] = (min(vals), max(vals))
        else:
            ranges[var] = (0, 1)
    return ranges


def _call_llm_for_adjustment(
    agent_params_summary: dict,
    step_label: str,
    simulated: dict,
    actual: dict,
    error: float,
    error_history: list[dict] | None = None,
) -> list[dict]:
    """
    调用 GLM-Z1-9B 分析误差，返回参数调整指令列表。
    每条指令：{"agent": "A2", "param": "threshold", "old": 0.5, "new": 0.35, "reason": "..."}
    error_history: 最近 N 步的误差序列（含方向信息），用于识别 overshoot/undershoot 模式。
    """
    try:
        from core.llm_client import call_llm

        # 找出偏差最大的变量
        deviations = []
        for var in ERROR_WEIGHTS:
            sim = simulated.get(var, 0)
            act = actual.get(var, 0)
            deviations.append(f"  {var}: 仿真={sim:.2f} 实际={act:.2f} 差={sim-act:+.2f}")
        dev_str = "\n".join(deviations)

        params_str = json.dumps(agent_params_summary, ensure_ascii=False, indent=2)

        # 构建误差历史描述
        history_str = ""
        if error_history and len(error_history) > 1:
            history_lines = []
            for h in error_history:
                history_lines.append(
                    f"  步{h['step']}: 误差={h['error']:.3f}"
                    f" GRV偏差={h['grv_delta']:+.1f}"
                    f" credit偏差={h['credit_delta']:+.1f}"
                )
            # 趋势摘要：最近5步误差均值 vs 前半段均值，判断整体趋势
            errors = [h["error"] for h in error_history]
            mid = max(1, len(errors) // 2)
            trend_early = sum(errors[:mid]) / mid
            trend_late  = sum(errors[mid:]) / max(1, len(errors) - mid)
            if trend_late > trend_early + 0.03:
                trend_label = "⬆ 误差上升趋势（调参效果变差）"
            elif trend_late < trend_early - 0.03:
                trend_label = "⬇ 误差下降趋势（调参有效）"
            else:
                trend_label = "➡ 误差震荡/持平（可能参数反复横跳）"
            history_str = (
                f"\n过去{len(error_history)}步误差序列（识别趋势用）：\n"
                + "\n".join(history_lines)
                + f"\n趋势摘要：{trend_label}（前半均值={trend_early:.3f}，近半均值={trend_late:.3f}）\n"
                + "\n注意：若某变量连续3步以上同向偏差，说明对应Agent参数存在系统性偏置。\n"
            )

        prompt = (
            f"你是宏观仿真系统的校准专家。当前月份：{step_label}\n\n"
            f"仿真结果 vs 实际数据：\n{dev_str}\n\n"
            f"综合误差：{error:.3f}（>0.15触发调整）\n"
            f"{history_str}\n"
            f"当前Agent参数（sensitivity/threshold/magnitude各1.0为基准）：\n{params_str}\n\n"
            f"请分析：哪些Agent的哪个参数导致了偏差？给出1-3条具体调整指令。\n"
            f"规则：若误差序列显示某参数连续3步 overshoot（仿真持续>实际），"
            f"减小对应 magnitude，不要反向调整；undershoot 则增大。\n"
            f"每条指令格式（严格JSON数组）：\n"
            f'[{{"agent":"A2","param":"threshold","new":0.35,"reason":"商业银行触发信贷收紧太迟"}}]\n'
            f"只输出JSON数组，不要其他文字。param只能是sensitivity/threshold/magnitude之一。"
        )

        raw = call_llm(prompt, use_minimax=False)
        if not raw:
            return []

        # 过滤 <think> 块
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # 提取 JSON 数组
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not match:
            return []

        instructions = json.loads(match.group())
        valid = []
        for inst in instructions:
            if (isinstance(inst, dict)
                    and "agent" in inst
                    and "param" in inst
                    and "new" in inst
                    and inst["param"] in ("sensitivity", "threshold", "magnitude")
                    and 0.0 <= float(inst["new"]) <= 2.0):
                valid.append(inst)
        return valid

    except Exception as e:
        print(f"  [calibrator] LLM 调参失败（跳过）：{e}")
        return []


def run_calibration(
    grv_path:  str = "/app/macro_data/grv_history.jsonl",
    fred_path: str = "/app/macro_data/fred_history",
    calib_steps: int = 50,
    error_threshold: float = ERROR_THRESHOLD,
    config_path: str = "/app/config/agents.yaml",
) -> dict:
    """
    主校准函数。
    返回：{
      "score": 0~100,
      "agents": {agent_id: AgentParams.to_dict()},
      "error_series": [float × calib_steps],
      "param_changes": [{step, agent, param, old, new, reason}],
    }

    D6 fix：启动时检查校准缓存（/app/data/calibration_cache.json），
    若时间戳 <7 天则直接加载缓存参数，跳过50步校准。
    """
    # D6: 尝试加载校准缓存
    _cache_path = Path("/app/data/calibration_cache.json")
    try:
        if _cache_path.exists():
            with open(_cache_path, encoding="utf-8") as _cf:
                _cache = json.load(_cf)
            _ts = datetime.fromisoformat(_cache.get("timestamp", "2000-01-01"))
            _age_days = (datetime.now() - _ts).total_seconds() / 86400
            if _age_days < 7:
                print(f"[calibrator] 命中校准缓存（{_age_days:.1f}天前，score={_cache.get('score')}），跳过50步校准")
                agents, _ = load_agents(config_path)
                for aid, p in _cache.get("agents", {}).items():
                    if aid in agents:
                        agents[aid].params.sensitivity = p.get("sensitivity", 1.0)
                        agents[aid].params.threshold   = p.get("threshold", 0.5)
                        agents[aid].params.magnitude   = p.get("magnitude", 1.0)
                return {
                    "score":        _cache.get("score", 50),
                    "avg_error":    0.0,
                    "agents":       _cache.get("agents", {}),
                    "error_series": [],
                    "param_changes": [],
                    "calib_steps":  0,
                    "_from_cache":  True,
                }
    except Exception as _ce:
        print(f"[calibrator] 缓存读取失败，执行完整校准: {_ce}")

    print(f"[calibrator] 加载历史数据（最近{calib_steps}个月）...")
    history = load_monthly_history(grv_path, fred_path, months=calib_steps + 6)

    if len(history) < calib_steps:
        print(f"[calibrator] 历史数据不足：只有 {len(history)} 条，需要 {calib_steps} 条")
        calib_steps = len(history)

    history_range = build_history_range(history)
    calibration_data = history[-calib_steps:]
    baseline_row     = history[-(calib_steps + 1)] if len(history) > calib_steps else history[0]

    # 初始化 Agent 和世界状态
    agents, _global_cfg = load_agents(config_path)
    initial_world = make_world_from_history_row(
        calibration_data[0], baseline_row, label=calibration_data[0]["date"]
    )
    initial_world.total_cycles = calib_steps

    model = MacroSimModel(initial_world, agents=agents, use_llm=False)

    error_series  = []
    param_changes = []
    error_history: deque = deque(maxlen=5)   # 滑动窗口：最近5步误差+方向
    CALIB_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"[calibrator] 开始校准，{calib_steps} 步...")
    for i, row in enumerate(calibration_data):
        actual_values = {
            "grv":           row["grv"],
            "credit_spread": row["credit_spread"],
            "t10y2y":        row["t10y2y"],
            "dff":           row["dff"],
        }

        # 先自由跑一步（不注入真实值），得到仿真预测
        snapshot = model.step(inject_world=None)
        simulated_values = {k: snapshot.get(k, 0) for k in ERROR_WEIGHTS}

        # 计算误差，记录方向信息
        error = compute_error(simulated_values, actual_values, history_range)
        error_series.append(error)
        error_history.append({
            "step":         i + 1,
            "error":        error,
            "grv_delta":    simulated_values["grv"] - actual_values["grv"],
            "credit_delta": simulated_values["credit_spread"] - actual_values["credit_spread"],
        })

        step_label = row["date"]
        print(f"  步 {i+1:02d}/{calib_steps} [{step_label}] 误差={error:.3f}"
              f"  sim_GRV={simulated_values['grv']:.1f} real={actual_values['grv']:.1f}", end="")

        # 误差超阈值 → LLM 调参（传入滑动窗口）
        if error > error_threshold:
            print(f" ← 超阈值({error_threshold})，调参中...", end="")
            params_summary = {
                aid: agent.params.to_dict()
                for aid, agent in agents.items()
            }
            instructions = _call_llm_for_adjustment(
                params_summary, step_label, simulated_values, actual_values, error,
                error_history=list(error_history),
            )
            for inst in instructions:
                agent_id = inst["agent"]
                param    = inst["param"]
                new_val  = float(inst["new"])
                reason   = inst.get("reason", "")
                if agent_id in agents:
                    old_val = getattr(agents[agent_id].params, param)
                    agents[agent_id].apply_param_adjustment(param, new_val)
                    change = {
                        "step": step_label, "agent": agent_id,
                        "param": param, "old": round(old_val, 3),
                        "new": round(new_val, 3), "reason": reason,
                    }
                    param_changes.append(change)
                    # 写入校准日志
                    with open(CALIB_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(change, ensure_ascii=False) + "\n")
                    print(f"\n    → {agent_id}.{param}: {old_val:.3f} → {new_val:.3f}  ({reason})")

        else:
            print()

        # 每步结束后用真实外生值修正世界状态，防止误差无限累积
        # （校准期的仿真是"能感知真实环境的受限仿真"，不是完全自由演化）
        for key, val in actual_values.items():
            if hasattr(model.world, key):
                setattr(model.world, key, val)

    # 计算综合评分
    avg_error = statistics.mean(error_series) if error_series else 1.0
    score = max(0, round(100 * (1 - avg_error / 0.5)))   # 误差0=100分，误差0.5=0分

    result = {
        "score":        score,
        "avg_error":    round(avg_error, 4),
        "agents":       {aid: a.params.to_dict() for aid, a in agents.items()},
        "error_series": error_series,
        "param_changes": param_changes,
        "calib_steps":  calib_steps,
    }

    # D6 fix: 写校准缓存，下次启动时若 <7 天直接加载跳过50步校准
    try:
        _cache_path2 = Path("/app/data/calibration_cache.json")
        _cache_path2.parent.mkdir(parents=True, exist_ok=True)
        _cache_data2 = {
            "timestamp": datetime.now().isoformat(),
            "score": score,
            "agents": result["agents"],
        }
        with open(_cache_path2, "w", encoding="utf-8") as _cf2:
            json.dump(_cache_data2, _cf2, ensure_ascii=False, indent=2)
        print(f"[calibrator] 校准缓存已写入 {_cache_path2}")
    except Exception as _ce2:
        print(f"[calibrator] 缓存写入失败（非阻断）: {_ce2}")

    print(f"\n[calibrator] 完成。评分：{score}/100，平均误差：{avg_error:.4f}")
    if score < 60:
        print(f"  ⚠️ 评分低于60，预测可信度有限")

    return result
