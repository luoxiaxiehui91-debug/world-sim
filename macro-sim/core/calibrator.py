"""
calibrator.py — 前50步校准循环

流程：
  1. 加载最近50个月历史数据
  2. 逐月跑仿真，每步结束后对比真实外生变量
  3. 误差 > 阈值时调用 GLM-Z1-9B 分析偏差，输出参数调整指令
  4. 记录每步误差和参数变更到 calibration_log.jsonl
  5. 返回校准质量评分（0~100）和校准后的 Agent 参数
"""

import copy
import json
import os
import re
import statistics
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
) -> list[dict]:
    """
    调用 GLM-Z1-9B 分析误差，返回参数调整指令列表。
    每条指令：{"agent": "A2", "param": "threshold", "old": 0.5, "new": 0.35, "reason": "..."}
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

        prompt = (
            f"你是宏观仿真系统的校准专家。当前月份：{step_label}\n\n"
            f"仿真结果 vs 实际数据：\n{dev_str}\n\n"
            f"综合误差：{error:.3f}（>0.15触发调整）\n\n"
            f"当前Agent参数（sensitivity/threshold/magnitude各1.0为基准）：\n{params_str}\n\n"
            f"请分析：哪些Agent的哪个参数导致了偏差？给出1-3条具体调整指令。\n"
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
    """
    print(f"[calibrator] 加载历史数据（最近{calib_steps}个月）...")
    history = load_monthly_history(grv_path, fred_path, months=calib_steps + 6)

    if len(history) < calib_steps:
        print(f"[calibrator] 历史数据不足：只有 {len(history)} 条，需要 {calib_steps} 条")
        calib_steps = len(history)

    history_range = build_history_range(history)
    calibration_data = history[-calib_steps:]
    baseline_row     = history[-(calib_steps + 1)] if len(history) > calib_steps else history[0]

    # 初始化 Agent 和世界状态
    agents = load_agents(config_path)
    initial_world = make_world_from_history_row(
        calibration_data[0], baseline_row, label=calibration_data[0]["date"]
    )
    initial_world.total_cycles = calib_steps

    model = MacroSimModel(initial_world, agents=agents, use_llm=False)

    error_series  = []
    param_changes = []
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

        # 计算误差
        error = compute_error(simulated_values, actual_values, history_range)
        error_series.append(error)

        step_label = row["date"]
        print(f"  步 {i+1:02d}/{calib_steps} [{step_label}] 误差={error:.3f}"
              f"  sim_GRV={simulated_values['grv']:.1f} real={actual_values['grv']:.1f}", end="")

        # 误差超阈值 → LLM 调参
        if error > error_threshold:
            print(f" ← 超阈值({error_threshold})，调参中...", end="")
            params_summary = {
                aid: agent.params.to_dict()
                for aid, agent in agents.items()
            }
            instructions = _call_llm_for_adjustment(
                params_summary, step_label, simulated_values, actual_values, error
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

    print(f"\n[calibrator] 完成。评分：{score}/100，平均误差：{avg_error:.4f}")
    if score < 60:
        print(f"  ⚠️ 评分低于60，预测可信度有限")

    return result
