"""
calibrator.py — 前50步校准循环（C1-1a/C3-3a 终局裁决版，2026-08-08）

流程：
  1. 加载最近50个月历史数据
  2. 逐月跑仿真，每步结束后对比真实外生变量（delta 口径）
  3. 相对误差 > 阈值时调用 GLM-Z1-9B 分析偏差，输出参数调整指令
  4. 记录每步误差和参数变更到 calibration_log.jsonl
  5. 三守卫（活跃率/参数塌缩/调参次数带）校验，返回校准质量评分（0~100）

C1-1a（2026-08-08 终局裁决）：
  误差口径改"相对变化方向"——_derive_endogenous_targets 产出的 soft target 语义
  本就是期望 delta，但旧主循环拿仿真绝对值比 target → 语义错配（把期望 delta 当
  绝对水平）。修复：主循环保留 prev_simulated，sim_delta = sim_now − sim_last 比
  target；第一步（无 prev）跳过触发但照常记 sim 值；error_series 取 49 点。
  配套：target 系数按仿真 delta 尺度重标定（探针测 m_v，T_v=α·m_v）；触发改
  per-variable 相对度量 |e|/|t|>0.5（scale-free）；评分改一致性率
  score=100×Σw_i×consistency_rate_i；LLM 喂数真传 sim_delta（非改措辞）。

C3-3a（2026-08-08 终局裁决）：
  ERROR_WEIGHTS 删 em_capital_outflow（0.15→0 权重重分配 0.40/0.35/0.25），
  移除依据=结构自锁（clamp[0,1]+target可负+CAPITAL_CONTROLS自举阈值0.5不可达）
  + 校准日志 943 行实证（148 次调 A7，141 次追 outflow 纯浪费）。
  权重语义改为"一致性率评分权重"，不再乘误差。

守卫（qa-review 定稿，硬闸，score 单独不再作验收依据）：
  A 活跃率：每变量 act_frac=#{|Δ|≥0.005}/49 ≥30%，silence_frac=#{|tgt|≥0.03 且
    |Δ|<0.005}/49 ≤50%（ε_act=0.005=最小单Agent行动 0.12×0.04）
  B 参数塌缩：agent collapsed = sensitivity≤0.10 且 magnitude≤0.10（校验下限允许
    0.0）；≥2 个"误差变量写者"塌缩 → FAIL（防 LLM 把参数调向 0 双闸全过）
  C 调参次数带：len(param_changes)：<5 FAIL（没发生校准）/ >50 FAIL（churn）；
    10-30 目标带；5-10/30-50 复核

样本过滤（_step_eligibility，data/qa 统一定稿，三处共用杜绝口径分叉）：
  N 中性怠工  |tgt|<0.03 且 |Δ|<0.05    → score 记 0 误差；rate 排除
  U 中性乱动  |tgt|<0.03 且 |Δ|≥0.05    → score 罚 |Δ|；rate 排除
  S 有信号不响应 |tgt|≥0.03 且 |Δ|<0.005 → score 罚 ≈|tgt|；rate 排除但计
    silence_frac（最危险类，双保险）
  T 可测      |tgt|≥0.03 且 |Δ|≥0.005   → score 全量 |Δ−tgt|（异号×1.5）；rate 计入分母

探针（run_probe，两段都禁开调参）：
  段1 诊断 12-15 步：死变量名单（m_v≈0 或一致率低）、sentiment/lp 双写相关矩阵
  段2 标定 50 步：delta-error 稳态分布 → m_v/std/P90/active_rate/consistency_rate
  产出 /app/data/calib_probe.json（σ/ρ/P90/active_rate/consistency_rate/target_scale）
  口径决策树（段1产出后走）：
    旧 score>76 且 新一致率<60% → 改 delta 口径
    新一致率也 <60% → 禁动 compute_error，查假收敛/阻尼
    两者都 >60% → 原样，只上相对触发
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


# C1-1a/C3-3a：权重改为 3 变量（C3 移除 em_capital_outflow），语义=一致性率评分权重
# （不再乘误差；评分 score=100×Σw_i×consistency_rate_i，见 run_calibration）
ERROR_WEIGHTS = {
    "market_sentiment":       0.40,  # 市场情绪，最多 Agent 直接影响
    "bank_credit_tightening": 0.35,  # 信贷紧缩，商业银行/美联储 Agent 驱动
    "liquidity_premium":      0.25,  # 流动性溢价，对冲基金/机构 Agent 驱动
}

# 外生变量列表（Teacher Forcing 只注入这些，不覆盖内生变量）
EXOGENOUS_VARS = {"grv", "credit_spread", "t10y2y", "dff",
                  "grv_energy", "us_china_grv", "vix"}

# C1-1a：per-variable 相对触发阈值（主触发，scale-free）。|e_i|/|target_i|>0.5 触发。
# 调参次数健康带会动态调整 0.5→0.65（过热）/→0.35（过松），状态存 calib_tuning_state.json
RELATIVE_TRIGGER = 0.5
# 限流：每 2 步最多 1 次 LLM 调用（防级联振荡）
LLM_RATE_LIMIT_STEPS = 2
# qa 口径边界：|target| 低于此视为中性（N/U 类）；data 建议 0.10（min 真实驱动），
# qa 主口径 0.03（最小有意义目标 0.06 的一半）——按终局文档四类表采用 0.03，
# 若探针显示 S 类过多可上调（见 calib_probe.json 注释）
EPS_TGT = 0.03
# qa 口径活性边界：|sim_delta| 低于此 = 无行动（最小单 Agent 行动 0.12×0.04=0.0048）
EPS_ACT = 0.005
# score 轴宽恕阈值（N 类 |Δ|<0.05 记 0 误差）
DELTA_DEAD = 0.05

CALIB_LOG_PATH  = Path("/app/output/calibration_log.jsonl")
PROBE_PATH      = Path("/app/data/calib_probe.json")
TUNING_STATE_PATH = Path("/app/data/calib_tuning_state.json")
# 缓存版本：C1-1a/C3-3a 后评分口径改变，旧缓存（无 version 或 version<2）不可复用；
# v2.0.29 A+D 修复（damping floor + MONTHLY_SCALE 0.12→0.25）改变引擎动力学 → bump 3
CACHE_VERSION = 3
# 旧 ERROR_THRESHOLD 保留为常量（外部引用兼容；触发已改 per-var 相对度量）
ERROR_THRESHOLD_LEGACY = 0.20

# v2.0.24 修复：校准 prompt 显式标注 17 个 Agent 名称映射，防 LLM 幻觉
# （实测 LLM 曾把 A5=机构投资者误认为"沙特"——S5_saudi 混淆；A4 已挂起不应被调参）
AGENT_NAME_HINT = (
    "Agent 名称映射（调参时严格按此识别，勿凭编号猜测）：\n"
    "  A1=美联储  A2=商业银行  A3=对冲基金  A4=能源国(已挂起，勿调)  A5=机构投资者(养老金/主权基金，非沙特)\n"
    "  A6=媒体  A7=新兴市场央行  A8=中国央行/财政  A9=美国财政部  A10=散户  A11=欧央行  A12=日央行\n"
    "  S1=美国(主权)  S2=中国(主权)  S3=欧盟(主权)  S4=俄罗斯(主权)  S5=沙特-OPEC(主权)\n"
)


def _soul_hint(soul_agents: dict[str, list[str]] | None) -> str:
    """
    动态生成"可调派系权重的 Agent 及派系名"提示（v3 §5.5 A 路）。
    仅列出实际挂 soul 的 Agent，防 LLM 对无 soul Agent 发派系权重指令（幻觉派系名崩溃）。
    """
    if not soul_agents:
        return "当前无 Agent 可调派系权重（均无 soul），只调三参数"
    parts = []
    for aid, factions in soul_agents.items():
        parts.append(f"{aid}({','.join(factions)})")
    return "仅限挂 soul 的 Agent: " + " / ".join(parts)


def _derive_endogenous_targets(prev_row: dict, curr_row: dict) -> dict:
    """
    从相邻两月外生变量变化推导内生变量的"期望方向目标"（delta 语义）。

    逻辑（C1-1a 去相关，arch 定稿）：
    - GRV↑ → market_sentiment 应下降（负相关）
    - credit_spread↑ → bank_credit_tightening 应上升（正相关）
    - credit_spread↑ + t10y2y↑ → liquidity_premium 应上升（双重压力；
      去掉 grv×0.4 共享驱动，防 lp/outflow 目标重复计数——lp 绑 cs+t10y2y）

    返回值：{var: soft_target}，soft_target 是 [-1, 1] 范围的期望 **delta**。
    误差 = |sim_delta − soft_target|（delta 口径），方向相反时惩罚更大。
    系数经探针按仿真 delta 尺度重标定（TARGET_SCALES 从 calib_probe.json 读）。
    """
    grv_delta    = curr_row.get("grv", 50) - prev_row.get("grv", 50)
    cs_delta     = curr_row.get("credit_spread", 250) - prev_row.get("credit_spread", 250)
    t10y2y_delta = curr_row.get("t10y2y", -10) - prev_row.get("t10y2y", -10)

    # 归一化到 [-1, 1]（基于历史典型变化幅度）
    grv_signal    = max(-1.0, min(1.0, grv_delta / 10.0))      # ±10 分 GRV 变化视为满幅
    cs_signal     = max(-1.0, min(1.0, cs_delta / 50.0))       # ±50bp credit spread 变化视为满幅
    t10y2y_signal = max(-1.0, min(1.0, t10y2y_delta / 20.0))   # ±20bp 10Y2Y 变化视为满幅

    targets = {
        # GRV↑ → 情绪↓（负相关）；强度 × 0.5 因为情绪变化通常滞后且温和
        "market_sentiment":       -grv_signal * 0.5,

        # credit_spread↑ → 信贷收紧↑（正相关）
        "bank_credit_tightening": cs_signal * 0.6,

        # credit_spread↑ + t10y2y↑ → 流动性溢价↑（双重压力；C1-1a 去 grv 共享驱动）
        "liquidity_premium":      (cs_signal * 0.4 + t10y2y_signal * 0.3),
    }

    # C1-1a 幅度标定：从 calib_probe.json 读探针标定的 scale（target 系数按仿真
    # delta 尺度重标定，T_v=α·m_v）。探针未跑时 scale=1.0（原始系数）。
    scales = _load_target_scales()
    for var in targets:
        targets[var] *= scales.get(var, 1.0)
    return targets


def _load_target_scales() -> dict:
    """从 calib_probe.json 读取探针标定的 target 系数（T_v=α·m_v 落地）。
    文件缺失/损坏 → 返回 {}（用原始系数）。"""
    try:
        if PROBE_PATH.exists():
            data = json.loads(PROBE_PATH.read_text(encoding="utf-8"))
            return data.get("target_scale", {}) or {}
    except Exception as _e:
        print(f"  [calibrator] calib_probe.json 读取失败（用原始系数）: {_e}")
    return {}


def _step_eligibility(sim_delta: float, tgt: float) -> str:
    """
    样本过滤统一口径（data/qa 定稿，三处共用杜绝分叉）：
    N 中性怠工 / U 中性乱动 / S 有信号不响应 / T 可测
    """
    abs_t = abs(tgt)
    abs_d = abs(sim_delta)
    if abs_t < EPS_TGT:
        # 中性（无外生驱动）
        return "N" if abs_d < DELTA_DEAD else "U"
    # 有信号
    return "S" if abs_d < EPS_ACT else "T"


def compute_error_legacy(simulated: dict, targets: dict) -> float:
    """
    旧口径误差（绝对值 vs target）——仅供探针段1决策树对比（error_old 字段），
    不再用于触发/评分（C1-1a 后主口径为 delta）。
    """
    total = 0.0
    for var, weight in ERROR_WEIGHTS.items():
        sim = simulated.get(var, 0.0)
        tgt = targets.get(var, 0.0)
        raw_err = abs(sim - tgt)
        if tgt != 0 and sim * tgt < 0:
            raw_err = min(raw_err * 1.5, 1.0)
        total += weight * min(raw_err, 1.0)
    return round(total, 4)


def compute_error(sim_delta: dict, targets: dict, per_var: bool = False):
    """
    计算内生变量的加权误差（delta 口径，C1-1a）。

    sim_delta: 本步仿真变化量（sim_now − sim_last），逐变量。
    targets: _derive_endogenous_targets 产生的 soft target（[-1,1]，期望 delta）。

    误差计算（经 _step_eligibility 过滤）：
    - T 可测：|Δ−tgt|（方向相反 ×1.5 惩罚，沿用旧语义）
    - N 中性怠工：记 0 误差
    - U 中性乱动：罚 |Δ|（不稳定）
    - S 有信号不响应：罚 ≈|tgt|（欠响应=真故障）

    per_var=True → 返回 {var: err}；否则返回加权和。
    """
    errs = {}
    for var, weight in ERROR_WEIGHTS.items():
        d = sim_delta.get(var, 0.0)
        t = targets.get(var, 0.0)
        cls = _step_eligibility(d, t)
        if cls == "T":
            raw_err = abs(d - t)
            # 方向相反时额外惩罚（d 和 t 异号且都不为 0）
            if t != 0 and d * t < 0:
                raw_err = min(raw_err * 1.5, 1.0)
            errs[var] = min(raw_err, 1.0)
        elif cls == "N":
            errs[var] = 0.0
        elif cls == "U":
            errs[var] = min(abs(d), 1.0)
        else:  # S 有信号不响应
            errs[var] = min(abs(t), 1.0)
    if per_var:
        return errs
    total = sum(ERROR_WEIGHTS[var] * errs[var] for var in ERROR_WEIGHTS)
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
    sim_delta: dict,
    targets: dict,
    error: float,
    error_history: list[dict] | None = None,
    soul_agents: dict[str, list[str]] | None = None,
) -> list[dict]:
    """
    调用 GLM-Z1-9B 分析误差，返回参数调整指令列表。
    每条指令：{"agent": "A2", "param": "threshold", "old": 0.5, "new": 0.35, "reason": "..."}
    soul_agents: {agent_id: [派系名, ...]} —— 仅这些 Agent 可调派系权重（v3 §5.5 A 路，
    动态生成提示防 LLM 对无 soul Agent 发派系权重指令——08-07 对照组实测 LLM 幻觉"看涨派系"崩溃）

    C1-1a：喂数真传 sim_delta（dev_str 显示 Δ 与 target 的偏差，非仿真绝对值）；
    删除 em_capital_outflow 驱动提示行（C3-3a，防悬空指令）。
    """
    try:
        from core.llm_client import call_llm

        # 找出偏差最大的内生变量（delta 口径）
        deviations = []
        for var in ERROR_WEIGHTS:
            d = sim_delta.get(var, 0.0)
            t = targets.get(var, 0.0)
            direction = "✓同向" if (t == 0 or d * t >= 0) else "✗反向"
            cls = _step_eligibility(d, t)
            cls_tag = {"T": "可测", "N": "中性怠工", "U": "中性乱动", "S": "欠响应"}[cls]
            deviations.append(
                f"  {var}: Δ={d:+.3f} 期望Δ={t:+.3f} [{direction}|{cls_tag}]"
            )
        dev_str = "\n".join(deviations)

        params_str = json.dumps(agent_params_summary, ensure_ascii=False, indent=2)

        history_str = ""
        if error_history and len(error_history) > 1:
            history_lines = []
            for h in error_history:
                history_lines.append(
                    f"  步{h['step']}: 误差={h['error_new']:.3f}"
                    f" sentiment偏差={h['sentiment_delta']:+.3f}"
                    f" credit_tight偏差={h['credit_delta']:+.3f}"
                )
            # C1-1a 趋势判据改比率制（量纲无关，data 定稿）：
            # ratio = late_mean / early_mean（均用 error_new 新口径）
            errors = [h["error_new"] for h in error_history]
            mid = max(1, len(errors) // 2)
            early_mean = sum(errors[:mid]) / mid
            late_mean  = sum(errors[mid:]) / max(1, len(errors) - mid)
            # guard：两半段均值均 < 0.01 → 持平（完美拟合防除零）
            if early_mean < 0.01 and late_mean < 0.01:
                trend_label = "➡ 误差持平（接近完美拟合）"
            elif late_mean > early_mean * 1.2:
                trend_label = "⬆ 误差上升趋势（调参效果变差）"
            elif late_mean < early_mean * 0.8:
                trend_label = "⬇ 误差下降趋势（调参有效）"
            else:
                trend_label = "➡ 误差震荡/持平"
            history_str = (
                f"\n过去{len(error_history)}步误差序列（新口径）：\n"
                + "\n".join(history_lines)
                + f"\n趋势：{trend_label}（前半均值={early_mean:.3f}，近半均值={late_mean:.3f}）\n"
            )

        prompt = (
            f"你是宏观仿真系统的校准专家。当前月份：{step_label}\n\n"
            f"内生变量仿真变化量(Δ) vs 期望变化(Δ目标，由GRV/利差变化推导)：\n{dev_str}\n\n"
            f"综合误差：{error:.3f}（相对误差>0.5 触发调整）\n"
            f"注意：误差标准是方向一致性（Δ 与期望 Δ 同向），✗反向比幅度偏差更严重；"
            f"标[欠响应]的变量=有信号但仿真几乎没动，是必须修的真故障。\n"
            f"{history_str}\n"
            f"当前Agent参数：\n{params_str}\n\n"
            f"{AGENT_NAME_HINT}\n"
            f"请分析：哪些Agent的参数导致内生变量方向错误？给出1-3条具体调整指令。\n"
            f"market_sentiment 主要由 A3(对冲基金)/A6(媒体)/A10(散户) 驱动。\n"
            f"bank_credit_tightening 主要由 A1(美联储)/A2(商业银行) 驱动。\n"
            f"liquidity_premium 主要由 A3/A5(机构投资者) 驱动。\n"
            f"每条指令格式（严格JSON数组）：\n"
            f'[{{"agent":"A2","param":"threshold","new":0.35,"reason":"信贷收紧触发太迟"}}]\n'
            f"只输出JSON数组。param可以是 sensitivity/threshold/magnitude 之一，\n"
            f"或派系权重路径 internal_factions.<派系名>.weight（{_soul_hint(soul_agents)}；\n"
            f"权重区间 0.01~0.9，且同 Agent 各派系权重之和应≈1.0，调整时尽量保持总权重不变）。"
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
            if not (isinstance(inst, dict)
                    and "agent" in inst
                    and "param" in inst
                    and "new" in inst):
                continue
            param = inst["param"]
            new_val = float(inst["new"])
            if param in ("sensitivity", "threshold", "magnitude") and 0.0 <= new_val <= 2.0:
                valid.append(inst)
            elif param.startswith("internal_factions.") and param.endswith(".weight") and 0.01 <= new_val <= 0.9:
                valid.append(inst)
        return valid

    except Exception as e:
        print(f"  [calibrator] LLM 调参失败（跳过）：{e}")
        return []


# ── 三守卫（qa-review 定稿，硬闸）────────────────────────────

# 误差变量写者清单（simulation.py gm 规则核实）：用于守卫 B 参数塌缩检查
# 2026-08-08 A2 写者补丁：market_sentiment 补 A2（simulation.py:138 EASE_CREDIT 写 -0.08*m，
# 原清单漏 A2——守卫 B 塌缩判定不受影响，但清单与 gm 规则必须一致）
ERROR_VAR_WRITERS = {
    "market_sentiment":       ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12"],
    "bank_credit_tightening": ["A1", "A2", "A11"],
    "liquidity_premium":      ["A2", "A3", "A4", "A5", "A10", "A11", "A12"],
}


def check_guards(
    param_changes: list[dict],
    agents: dict,
    delta_samples: dict[str, list[float]],
    tgt_samples: dict[str, list[float]],
    n_steps: int,
) -> dict:
    """
    三守卫硬闸（qa 定稿）：
    A 活跃率：act_frac≥30% 且 silence_frac≤50%（防死仿真恒不动）
    B 参数塌缩：<2 个误差变量写者 collapsed（sensitivity≤0.10 且 magnitude≤0.10）
    C 调参次数带：5≤N≤50（10-30 目标带）
    返回 {guard: bool, detail: ...}；score 单独不再作验收依据。
    """
    guards = {}

    # 守卫 A：活跃率（逐变量）
    a_detail = {}
    a_pass = True
    for var in ERROR_WEIGHTS:
        deltas = delta_samples.get(var, [])
        tgts   = tgt_samples.get(var, [])
        if not deltas or n_steps == 0:
            act_frac = 0.0
            silence_frac = 1.0
        else:
            act_frac = sum(1 for d in deltas if abs(d) >= EPS_ACT) / len(deltas)
            silence_frac = sum(
                1 for d, t in zip(deltas, tgts) if abs(t) >= EPS_TGT and abs(d) < EPS_ACT
            ) / len(deltas)
        ok = act_frac >= 0.30 and silence_frac <= 0.50
        a_detail[var] = {"act_frac": round(act_frac, 3), "silence_frac": round(silence_frac, 3), "pass": ok}
        if not ok:
            a_pass = False
    guards["A_active"] = {"pass": a_pass, "detail": a_detail}

    # 守卫 B：参数塌缩（防 LLM 调 sensitivity/magnitude 向 0 双闸全过）
    # 写者 = 所有误差变量写者的并集（ERROR_VAR_WRITERS 的 values）
    writer_aids = sorted({aid for aids in ERROR_VAR_WRITERS.values() for aid in aids})
    collapsed = []
    for aid in writer_aids:
        if aid in agents:
            p = agents[aid].params
            if getattr(p, "sensitivity", 1.0) <= 0.10 and getattr(p, "magnitude", 1.0) <= 0.10:
                collapsed.append(aid)
    b_pass = len(collapsed) < 2
    guards["B_collapse"] = {"pass": b_pass, "collapsed": collapsed, "threshold": "≥2 writers → FAIL"}

    # 守卫 C：调参次数带（防阈值过紧每步触发 / 过松永不触发）
    n = len(param_changes)
    if n < 5:
        c_pass = False
        c_label = "FAIL（没发生校准=死仿真或阈值永不触发）"
    elif n > 50:
        c_pass = False
        c_label = "FAIL（churn，历史实证 133/50=2.66/step）"
    elif 10 <= n <= 30:
        c_pass = True
        c_label = "目标带"
    else:
        c_pass = True
        c_label = "复核带（5-10 或 30-50）"
    guards["C_tuning"] = {"pass": c_pass, "n_changes": n, "label": c_label, "target_band": "10-30"}

    all_pass = a_pass and b_pass and c_pass
    guards["all_pass"] = all_pass
    return guards


def _write_tuning_state(n_changes: int, consistency: float, p90_probe: float, relative_trigger: float):
    """调参次数健康带第二道闸：N>30 → 阈值过紧（0.5→0.65）；N<10 且一致率<60% → 过松（→0.35）。
    状态写 /app/data/calib_tuning_state.json，供下次校准读取调整 RELATIVE_TRIGGER。"""
    try:
        next_trigger = relative_trigger
        if n_changes > 30:
            next_trigger = min(0.65, relative_trigger + 0.15)   # 过热 → 阈值调紧
        elif n_changes < 10 and consistency < 0.60:
            next_trigger = max(0.35, relative_trigger - 0.15)   # 过松 → 阈值调松
        state = {
            "relative_trigger": round(next_trigger, 2),
            "eps_target": EPS_TGT,
            "last_run": {
                "n_changes": n_changes,
                "consistency": round(consistency, 3),
                "p90_probe": round(p90_probe, 4),
            },
            "updated": datetime.now().isoformat(),
        }
        TUNING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TUNING_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as _e:
        print(f"  [calibrator] calib_tuning_state.json 写入失败（非阻断）: {_e}")


def _load_relative_trigger(default: float = RELATIVE_TRIGGER) -> float:
    """从 calib_tuning_state.json 读取上次健康带建议的 relative_trigger。"""
    try:
        if TUNING_STATE_PATH.exists():
            state = json.loads(TUNING_STATE_PATH.read_text(encoding="utf-8"))
            return float(state.get("relative_trigger", default))
    except Exception:
        pass
    return default


# ── 探针（C1-1a 幅度标定数据源，两段都禁开调参）────────────────

def run_probe(
    grv_path:  str = "/app/macro_data/grv_history.jsonl",
    fred_path: str = "/app/macro_data/fred_history",
    probe_steps: int = 50,
    config_path: str = "/app/config/agents.yaml",
) -> dict:
    """
    探针：固定参数、不调参、只记 sim_delta/target 序列，测 delta-error 稳态分布。
    产出 per-var：m_v=median|sim_delta|（死变量判定/T_v 标定）、std、P90(error)、
    active_rate、consistency_rate、ρ 相关矩阵、target_scale 建议（T_v=α·m_v，α∈[1.5,2.5]）。
    写 /app/data/calib_probe.json。
    段1 诊断（12-15 步）与段2 标定（50 步）共用本函数，差别=步数与测量目标。
    """
    print(f"[calibrator] 探针开始（{probe_steps} 步，固定参数禁调参）...")
    history = load_monthly_history(grv_path, fred_path, months=probe_steps + 6)
    if len(history) < probe_steps:
        probe_steps = len(history)
    calibration_data = history[-probe_steps:]
    baseline_row     = history[-(probe_steps + 1)] if len(history) > probe_steps else history[0]

    agents, _global_cfg = load_agents(config_path)
    # 校准期 S 类挂起（与 run_calibration 同规则）
    for _aid, _agent in agents.items():
        if _aid.startswith("S"):
            _agent.activation_prob = 0.0

    initial_world = make_world_from_history_row(
        calibration_data[0], baseline_row, label=calibration_data[0]["date"]
    )
    initial_world.total_cycles = probe_steps
    model = MacroSimModel(initial_world, agents=agents, use_llm=False)

    prev_simulated = None
    delta_by_var = {v: [] for v in ERROR_WEIGHTS}
    tgt_by_var   = {v: [] for v in ERROR_WEIGHTS}
    err_by_var   = {v: [] for v in ERROR_WEIGHTS}
    active_pairs = {v: [] for v in ERROR_WEIGHTS}   # (d, t) 仅 T 类
    all_pairs    = {v: [] for v in ERROR_WEIGHTS}   # (d, t) 所有步（ρ 矩阵用）
    ease_decisions_main = 0   # 主探针顺带观察：A2 选中 EASE_CREDIT 的步数（ship 闸以子探针为准）
    silence_by_var = {v: 0 for v in ERROR_WEIGHTS}  # S 类计数（D 触发条件 ① silence_frac>50%）

    for i, row in enumerate(calibration_data):
        exogenous_inject = {
            k: v for k, v in row.items()
            if k in EXOGENOUS_VARS and hasattr(model.world, k)
        }
        snapshot = model.step(inject_world=exogenous_inject)
        simulated_values = {k: snapshot.get(k, 0.0) for k in ERROR_WEIGHTS}
        if snapshot.get("actions", {}).get("A2") == "EASE_CREDIT":
            ease_decisions_main += 1

        prev_row = calibration_data[i - 1] if i > 0 else baseline_row
        endogenous_targets = _derive_endogenous_targets(prev_row, row)

        if prev_simulated is None:
            prev_simulated = simulated_values   # 第一步只记 sim 值，无 delta
            continue
        sim_delta = {v: simulated_values[v] - prev_simulated[v] for v in ERROR_WEIGHTS}
        prev_simulated = simulated_values

        for v in ERROR_WEIGHTS:
            d = sim_delta[v]
            t = endogenous_targets[v]
            delta_by_var[v].append(d)
            tgt_by_var[v].append(t)
            all_pairs[v].append((d, t))
            cls = _step_eligibility(d, t)
            if cls == "T":
                active_pairs[v].append((d, t))
                err_by_var[v].append(abs(d - t) * (1.5 if d * t < 0 else 1.0))
            elif cls == "N":
                err_by_var[v].append(0.0)
            elif cls == "U":
                err_by_var[v].append(abs(d))
            else:  # S
                err_by_var[v].append(abs(t))
                silence_by_var[v] += 1

    # 统计
    probe = {"steps": probe_steps, "n_delta_steps": len(delta_by_var[list(ERROR_WEIGHTS)[0]]),
             "per_var": {}, "rho": {}, "p90_probe": 0.0, "generated": datetime.now().isoformat()}
    for v in ERROR_WEIGHTS:
        ds = delta_by_var[v]
        es = err_by_var[v]
        pairs = active_pairs[v]
        m_v = statistics.median([abs(d) for d in ds]) if ds else 0.0
        consistency = (
            sum(1 for d, t in pairs if d * t >= 0) / len(pairs) if pairs else 0.0
        )
        active_rate = len(pairs) / len(ds) if ds else 0.0
        n_delta = len(ds) if ds else 1
        probe["per_var"][v] = {
            "m_v": round(m_v, 5),                       # median|sim_delta| → 死变量判定/T_v 标定
            "std_delta": round(statistics.pstdev(ds), 5) if len(ds) > 1 else 0.0,
            "p90_error": round(sorted(es)[int(len(es) * 0.9)] if es else 0.0, 4),
            "active_rate": round(active_rate, 3),
            "consistency_rate": round(consistency, 3),
            "silence_frac": round(silence_by_var[v] / n_delta, 3),  # S 类占比（D 触发条件 ①）
            "n_active": len(pairs),
            "dead": m_v < 0.002,                        # δ_min：死变量走 C3 不标定
            "target_scale": round(2.0 * m_v / max(1e-9, abs(_median_target(v, tgt_by_var[v]))), 3)
            if m_v > 0 and _median_target(v, tgt_by_var[v]) > 1e-9 else 1.0,
        }

    # ρ 相关矩阵（sentiment/lp 双写检测）
    for v1 in ERROR_WEIGHTS:
        probe["rho"][v1] = {}
        for v2 in ERROR_WEIGHTS:
            if v1 == v2:
                probe["rho"][v1][v2] = 1.0
                continue
            s1 = delta_by_var[v1]
            s2 = delta_by_var[v2]
            n = min(len(s1), len(s2))
            if n < 3:
                probe["rho"][v1][v2] = 0.0
                continue
            m1, m2 = statistics.mean(s1[:n]), statistics.mean(s2[:n])
            num = sum((a - m1) * (b - m2) for a, b in zip(s1[:n], s2[:n]))
            d1 = sum((a - m1) ** 2 for a in s1[:n]) ** 0.5
            d2 = sum((b - m2) ** 2 for b in s2[:n]) ** 0.5
            probe["rho"][v1][v2] = round(num / (d1 * d2), 3) if d1 and d2 else 0.0

    all_errors = [e for v in ERROR_WEIGHTS for e in err_by_var[v]]
    probe["p90_probe"] = round(sorted(all_errors)[int(len(all_errors) * 0.9)] if all_errors else 0.0, 4)
    # 加权典型误差（score 分母重锚参考）
    probe["avg_weighted_error"] = round(
        sum(ERROR_WEIGHTS[v] * (statistics.mean(err_by_var[v]) if err_by_var[v] else 1.0)
            for v in ERROR_WEIGHTS), 4)

    # EASE 定向探针两级（ship 闸，calib-fix-review 终局）：
    # 独立子探针强制初始 bank_credit_tightening=0.3（[0,1] clamp 吃 0 起步写入测不出落地），
    # 测 ①决策层 EASE_CREDIT 可达性 ②写层负 delta 落地。主探针顺带观察决策层。
    ease_probe = _run_ease_probe(
        calibration_data, baseline_row, probe_steps, config_path,
        ease_initial_credit=0.3,
    )
    probe["ease_probe"] = ease_probe
    probe["ease_decisions_main"] = ease_decisions_main  # 主探针窗口顺带观察（ship 闸以子探针为准）

    PROBE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROBE_PATH.write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[calibrator] 探针完成，已写 {PROBE_PATH}")
    for v in ERROR_WEIGHTS:
        p = probe["per_var"][v]
        print(f"  {v}: m_v={p['m_v']} active={p['active_rate']} "
              f"consistency={p['consistency_rate']} p90={p['p90_error']}"
              f"{' [死变量→C3]' if p['dead'] else ''}")
    # D 触发条件诊断（A+D 修复批次，任一触发→上 D=0.25 已实施；此处对照打印）
    _print_d_trigger_check(probe)
    # 决策树提示（data R4）
    _print_probe_decision_tree(probe)
    return probe


def _run_ease_probe(
    calibration_data: list[dict],
    baseline_row: dict,
    probe_steps: int,
    config_path: str,
    ease_initial_credit: float = 0.3,
) -> dict:
    """
    EASE 定向探针两级（ship 闸，calib-fix-review 终局 2026-08-08）：
    验证 A2 EASE_CREDIT 在引擎中可达且写层落地。校准对 bank_credit_tightening
    的负向调节依赖 EASE（唯一负写者），若决策层永假或 clamp 吃写入，校准结果不可信。

    两级判定：
      ① 决策层：EASE_CREDIT 被选中步数 >0（ease_signal ∧ ¬tighten_signal 可达性，
        financial.py:80-86 if-elif tighten 先判，受压窗口 A3 SHORT/A6 PANIC 可见即挡死 EASE）
      ② 写层：EASE 选中步中 bank_credit_tightening 快照差 ≤ -0.005 落地
        （[0,1] clamp 吃 0 起步写入 → 前置初始 bank_credit_tightening>0，默认 0.3）

    ship 闸：①≥1 且 ②≥1 → PASS（EASE 可达，ship 放行）；
      ①=0 → FAIL（ease_signal 永假，EASE 判据降级——校准不阻塞但 ship 阻塞，拆三条件：
      spread<200 / tightening<threshold×0.3 / grv_stress<threshold×0.3）；
      ①≥1 但 ②=0 → FAIL（clamp 截断负写入，[0,1] clamp 吃 0 起步写入）。

    独立子探针：强制初始 bank_credit_tightening=0.3，与主探针同历史窗口，不污染主探针统计。
    """
    print(f"[calibrator] EASE 定向探针开始（{probe_steps} 步，初始 credit={ease_initial_credit}）...")
    agents, _global_cfg = load_agents(config_path)
    # 校准期 S 类挂起（与 run_probe 主探针同规则）
    for _aid, _agent in agents.items():
        if _aid.startswith("S"):
            _agent.activation_prob = 0.0

    initial_world = make_world_from_history_row(
        calibration_data[0], baseline_row, label=calibration_data[0]["date"]
    )
    initial_world.total_cycles = probe_steps
    # 前置：EASE 落地需要 level>0（[0,1] clamp 吃 0 起步写入测不出落地）
    if hasattr(initial_world, "bank_credit_tightening"):
        initial_world.bank_credit_tightening = ease_initial_credit
    model = MacroSimModel(initial_world, agents=agents, use_llm=False)

    ease_decisions = 0    # ① 决策层
    ease_landed = 0       # ② 写层落地
    ease_deltas: list[float] = []
    prev_credit = ease_initial_credit
    for row in calibration_data:
        exogenous_inject = {
            k: v for k, v in row.items()
            if k in EXOGENOUS_VARS and hasattr(model.world, k)
        }
        snapshot = model.step(inject_world=exogenous_inject)
        cur_credit = snapshot.get("bank_credit_tightening", prev_credit)
        if snapshot.get("actions", {}).get("A2") == "EASE_CREDIT":
            ease_decisions += 1
            d = cur_credit - prev_credit
            ease_deltas.append(round(d, 5))
            if d <= -0.005:
                ease_landed += 1
        prev_credit = cur_credit

    if ease_decisions >= 1 and ease_landed >= 1:
        gate, advice = "PASS", "EASE 两级可达：校准负向调节有对应机制，ship 放行"
    elif ease_decisions == 0:
        gate = "FAIL"
        advice = ("决策层 EASE=0：ease_signal 永假（financial.py:75-79 三条件 "
                  "spread<200 ∧ tightening<threshold×0.3 ∧ grv_stress<threshold×0.3，"
                  "且 tighten 先判挡死受压窗口）。EASE 判据降级——校准不阻塞但 ship 阻塞，"
                  "拆三条件定位")
    else:
        gate = "FAIL"
        advice = (f"决策层 EASE={ease_decisions} 但写层落地={ease_landed}："
                  f"[0,1] clamp 截断负写入（credit 贴 0 起步）→ 校准负向调节不可达，ship 阻塞")

    result = {
        "gate": gate,
        "ease_decisions": ease_decisions,
        "ease_landed": ease_landed,
        "ease_credit_deltas": ease_deltas,
        "initial_credit": ease_initial_credit,
        "advice": advice,
    }
    print(f"[calibrator] EASE 定向探针：决策层={ease_decisions} 落地={ease_landed} → ship 闸 {gate}")
    return result


def _print_d_trigger_check(probe: dict):
    """
    D 触发条件诊断打印（A+D 修复批次终局，2026-08-08）：
    A 引擎 clamp 口径下任一触发 → 上 D=0.25（本批次已实施 D，此处对照打印留痕）。
      ① silence_frac > 50%
      ② act_frac < 30%
      ③ m_v < 0.005 死线（诊断）；m_v 0.025/0.05 降监控参考线
        （data-fix 反证：sentiment m_v 在 0.12 保留下恒 0.005~0.010，
        固定绝对数触发线=变相强制 D，故仅作参考线不自动触发）
    """
    print("\n[calibrator] D 触发条件对照（A 引擎 clamp 口径，D=0.25 已实施）：")
    for v in ERROR_WEIGHTS:
        p = probe["per_var"][v]
        flags = []
        if p["silence_frac"] > 0.50:
            flags.append(f"①silence_frac={p['silence_frac']:.0%}>50%")
        if p["active_rate"] < 0.30:
            flags.append(f"②act_frac={p['active_rate']:.0%}<30%")
        if p["m_v"] < 0.005:
            flags.append(f"③m_v={p['m_v']}<0.005 死线")
        elif p["m_v"] < 0.05:
            flags.append(f"参考线: m_v={p['m_v']}∈[0.025,0.05) 降监控")
        status = " 触发" + " | ".join(flags) if flags else " 未触发"
        print(f"  {v}:{status}")


def _median_target(var: str, tgt_list: list[float]) -> float:
    return statistics.median([abs(t) for t in tgt_list]) if tgt_list else 0.0


def _print_probe_decision_tree(probe: dict):
    """口径决策树（data R4）：探针段1产出后走，打印建议不自动改代码。"""
    print("\n[calibrator] 口径决策树提示（data R4）：")
    for v in ERROR_WEIGHTS:
        p = probe["per_var"][v]
        if p["consistency_rate"] < 0.60:
            print(f"  ⚠ {v} 新口径一致率 {p['consistency_rate']:.0%} < 60%："
                  f"若旧口径 score>76 → 应改 delta 口径；新口径仍 <60% → 禁动 compute_error，"
                  f"查假收敛/阻尼")
        else:
            print(f"  ✓ {v} 新口径一致率 {p['consistency_rate']:.0%} ≥ 60%：原样只上相对触发")


def run_calibration(
    grv_path:  str = "/app/macro_data/grv_history.jsonl",
    fred_path: str = "/app/macro_data/fred_history",
    calib_steps: int = 50,
    error_threshold: float = ERROR_THRESHOLD_LEGACY,
    config_path: str = "/app/config/agents.yaml",
) -> dict:
    """
    主校准函数（C1-1a delta 口径 + C3-3a 三变量）。
    返回：{
      "score": 0~100（一致性率加权，非旧误差公式）,
      "agents": {agent_id: AgentParams.to_dict()},
      "error_series": [float × (calib_steps−1)]（第一步无 delta 不记）,
      "param_changes": [{step, agent, param, old, new, reason}],
      "llm_calls": int, "adjustment_steps": int,
      "guards": {...}, "relative_trigger": float,
    }
    """
    # 读取上次健康带建议的触发阈值
    trigger = _load_relative_trigger()

    # D6 fix: 尝试加载校准缓存（v2.2 从旧版移植；<7 天直接跳过 50 步校准）
    # C1-1a/C3-3a：缓存版本升级到 CACHE_VERSION=2，旧缓存（评分口径不同）不可复用
    # v2.0.29 A+D：bump 3（引擎动力学改变，旧缓存失效——防 <7 天命中旧引擎缓存）
    _cache_path = Path("/app/data/calibration_cache.json")
    try:
        if _cache_path.exists():
            with open(_cache_path, encoding="utf-8") as _cf:
                _cache = json.load(_cf)
            _ver = _cache.get("calib_version", 1)
            _ts = datetime.fromisoformat(_cache.get("timestamp", "2000-01-01"))
            _age_days = (datetime.now() - _ts).total_seconds() / 86400
            if _ver >= CACHE_VERSION and _age_days < 7:
                print(f"[calibrator] 命中校准缓存（v{_ver}，{_age_days:.1f}天前，score={_cache.get('score')}），跳过50步校准")
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
            elif _ver < CACHE_VERSION:
                print(f"[calibrator] 缓存版本 v{_ver} < v{CACHE_VERSION}（评分口径已变），重新校准")
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

    agents, _global_cfg = load_agents(config_path)

    # v2.0.27 修复（question 20260808-world-deduction-calibration-s-class-disturbance）：
    # 校准期 S 类主权 Agent activation_prob 置 0——校准是 50 个月历史拟合（2022-06→2026-07），
    # S 类主权行为 08-07 才激活（A 类激活 commit 4aaa5fde），历史期本不该有它们参与；
    # 校准循环 model.step() 会让 S 类按 0.35 激活并写 grv_dimensions/sentiment 扰动内生变量
    # （实测 3 步 6 次激活 → score 0，A/B 双组 0.70/0.67 一致证明与 3 soul 试点无关）。
    # 注意：仅校准期生效，不影响预测期（run_prediction 重新 load_agents 拿原始 activation_prob）。
    for _aid, _agent in agents.items():
        if _aid.startswith("S"):
            _agent.activation_prob = 0.0
    _n_s = sum(1 for a in agents if a.startswith("S"))
    print(f"[calibrator] 校准期 S 类主权 Agent 已挂起（{_n_s} 个，activation_prob=0）——历史拟合期无主权行为")

    initial_world = make_world_from_history_row(
        calibration_data[0], baseline_row, label=calibration_data[0]["date"]
    )
    initial_world.total_cycles = calib_steps

    model = MacroSimModel(initial_world, agents=agents, use_llm=False)

    error_series  = []
    param_changes = []
    llm_calls     = 0
    error_history: deque = deque(maxlen=5)
    CALIB_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # C1-1a：delta 口径滚动缓存
    prev_simulated = None
    last_llm_step  = -999
    delta_samples = {v: [] for v in ERROR_WEIGHTS}   # 守卫 A 用
    tgt_samples   = {v: [] for v in ERROR_WEIGHTS}   # 守卫 A 用
    active_pairs  = {v: [] for v in ERROR_WEIGHTS}   # 一致性率用（仅 T 类）

    print(f"[calibrator] 开始校准，{calib_steps} 步（relative_trigger={trigger}）...")
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

        # C1-1a：第一步（无 prev）跳过触发但照常记 sim 值（评审：不可用 initial_world
        # 当 prev——它四内生变量=0.0，step0 的 delta 退化为绝对值，重演原 bug）
        if prev_simulated is None:
            prev_simulated = simulated_values
            step_label = row["date"]
            print(f"  步 {i+1:02d}/{calib_steps} [{step_label}] 第一步（无 prev，跳过触发，仅记录）")
            continue

        sim_delta = {v: simulated_values[v] - prev_simulated[v] for v in ERROR_WEIGHTS}
        prev_simulated = simulated_values

        # 记录守卫样本 + 一致性率样本
        for v in ERROR_WEIGHTS:
            d = sim_delta[v]
            t = endogenous_targets[v]
            delta_samples[v].append(d)
            tgt_samples[v].append(t)
            if _step_eligibility(d, t) == "T":
                active_pairs[v].append((d, t))

        error = compute_error(sim_delta, endogenous_targets)
        error_series.append(error)
        error_history.append({
            "step":          i + 1,
            # C1-1a：双口径字段——error_old 供错位诊断对比（决策树第一分支），
            # error_new 供渲染与趋势；sim_delta_*/target_* 存逐变量原始值（两层级）
            "error_old":     compute_error_legacy(simulated_values, endogenous_targets),
            "error_new":     round(error, 4),
            "sentiment_delta": sim_delta["market_sentiment"] - endogenous_targets["market_sentiment"],
            "credit_delta":    sim_delta["bank_credit_tightening"] - endogenous_targets["bank_credit_tightening"],
            "sim_delta":     {k: round(v, 4) for k, v in sim_delta.items()},
            "target":        {k: round(v, 4) for k, v in endogenous_targets.items()},
        })

        step_label = row["date"]
        print(
            f"  步 {i+1:02d}/{calib_steps} [{step_label}] 误差={error:.3f}"
            f"  sentimentΔ={sim_delta['market_sentiment']:+.3f}"
            f"(期望Δ{endogenous_targets['market_sentiment']:+.3f})",
            end=""
        )

        # C1-1a：per-variable 相对触发（主触发，scale-free）+ 限流
        should_trigger = False
        for v in ERROR_WEIGHTS:
            d = sim_delta[v]
            t = endogenous_targets[v]
            cls = _step_eligibility(d, t)
            if cls == "T":
                denom = abs(t) if abs(t) > 1e-9 else 1e-9
                if abs(d - t) / denom > trigger:
                    should_trigger = True
                    break
            elif cls == "S":
                # 有信号不响应 = 欠响应真故障，必须触发（data 定稿）
                should_trigger = True
                break

        if should_trigger and (i + 1 - last_llm_step) >= LLM_RATE_LIMIT_STEPS:
            last_llm_step = i + 1
            llm_calls += 1
            print(f" ← 相对误差>0.5/欠响应，调参中...", end="")
            params_summary = {aid: agent.params.to_dict() for aid, agent in agents.items()}
            # v3 §5.5 A 路：动态传挂 soul 的 Agent（agent_id → 派系名列表），防 LLM 对无 soul Agent 幻觉派系名
            soul_agents = {
                aid: list((a.soul or {}).get("internal_factions", {}).keys())
                for aid, a in agents.items() if a.soul
            }
            instructions = _call_llm_for_adjustment(
                params_summary, step_label, sim_delta, endogenous_targets, error,
                error_history=list(error_history),
                soul_agents=soul_agents,
            )
            for inst in instructions:
                agent_id = inst["agent"]
                param    = inst["param"]
                new_val  = float(inst["new"])
                reason   = inst.get("reason", "")
                if agent_id in agents:
                    # v3 §5.5 A 路：支持 soul 派系权重路径（internal_factions.{faction}.weight）
                    if param.startswith("internal_factions."):
                        fname = param.split(".")[1]
                        factions = (agents[agent_id].soul or {}).get("internal_factions", {})
                        old_val = factions.get(fname, {}).get("weight", 0.33) if isinstance(factions.get(fname), dict) else 0.33
                    else:
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

    # ── 评分（C1-1a：一致性率，非旧误差公式）────────────────
    consistency_rates = {}
    for v in ERROR_WEIGHTS:
        pairs = active_pairs[v]
        consistency_rates[v] = (
            sum(1 for d, t in pairs if d * t >= 0) / len(pairs) if pairs else 0.0
        )
    score = round(100 * sum(
        ERROR_WEIGHTS[v] * consistency_rates[v] for v in ERROR_WEIGHTS
    ), 1)
    avg_consistency = sum(consistency_rates.values()) / len(consistency_rates)

    # 旧口径 avg_error 保留字段（run.py 显示用；新口径下=加权平均误差）
    avg_error = statistics.mean(error_series) if error_series else 1.0

    # 三守卫（qa 硬闸）
    n_delta_steps = len(delta_samples[list(ERROR_WEIGHTS)[0]])
    guards = check_guards(param_changes, agents, delta_samples, tgt_samples, n_delta_steps)

    # 调参次数健康带（第二道闸，qa 要求）
    _write_tuning_state(len(param_changes), avg_consistency, _load_p90_probe(), trigger)

    result = {
        "score":         score,
        "avg_error":     round(avg_error, 4),
        "avg_consistency": round(avg_consistency, 3),
        "consistency_rates": {k: round(v, 3) for k, v in consistency_rates.items()},
        "agents":        {aid: a.params.to_dict() for aid, a in agents.items()},
        "error_series":  error_series,
        "param_changes": param_changes,
        "calib_steps":   calib_steps,
        "llm_calls":     llm_calls,
        "adjustment_steps": len(set(c["step"] for c in param_changes)),
        "relative_trigger": trigger,
        "guards":        guards,
    }

    # D6 fix: 写校准缓存（v2 版本），下次启动时若 <7 天直接加载跳过50步校准
    try:
        cache_path = Path("/app/data/calibration_cache.json")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "calib_version": CACHE_VERSION,
            "timestamp": datetime.now().isoformat(),
            "score": score,
            "agents": result["agents"],
        }
        with open(cache_path, "w", encoding="utf-8") as _cf:
            json.dump(cache_data, _cf, ensure_ascii=False, indent=2)
        print(f"[calibrator] 校准缓存已写入 {cache_path}")
    except Exception as _ce:
        print(f"[calibrator] 缓存写入失败（非阻断）: {_ce}")

    print(f"\n[calibrator] 完成。一致性率评分：{score}/100（加权），平均误差：{avg_error:.4f}")
    print(f"  守卫: A_active={'PASS' if guards['A_active']['pass'] else 'FAIL'} "
          f"B_collapse={'PASS' if guards['B_collapse']['pass'] else 'FAIL'} "
          f"C_tuning={'PASS' if guards['C_tuning']['pass'] else 'FAIL'}")
    if not guards["all_pass"]:
        print(f"  ⚠️ 守卫未全过——score 不作验收依据，请按守卫详情修（见 result['guards']）")
    elif score < 60:
        print(f"  ⚠️ 评分低于60，预测可信度有限")

    return result


def _load_p90_probe() -> float:
    """读 calib_probe.json 的 p90_probe 供 score 分母重锚参考（fallback 副指标）。"""
    try:
        if PROBE_PATH.exists():
            return float(json.loads(PROBE_PATH.read_text(encoding="utf-8")).get("p90_probe", 0.0))
    except Exception:
        pass
    return 0.0


# ── 运行时自检（ADR-0011 accepted，2026-08-07）──────────────────
# 防 D2/D3 式静默降级：旧版副本残留（同名函数后定义覆盖）或 ERROR_WEIGHTS 被
# 覆盖为外生版时，模块加载即抛异常——「声称已修」不再可能从未生效。
def _self_check():
    import sys as _sys
    import inspect as _insp

    # 1. ERROR_WEIGHTS 必须是内生版签名（C3-3a：3 变量，不含 outflow）
    _required = {"market_sentiment", "bank_credit_tightening", "liquidity_premium"}
    _missing = _required - set(ERROR_WEIGHTS)
    if _missing:
        raise RuntimeError(
            f"calibrator 自检失败：ERROR_WEIGHTS 缺内生变量 {sorted(_missing)}（可能被旧版覆盖）")
    if "em_capital_outflow" in ERROR_WEIGHTS:
        raise RuntimeError("calibrator 自检失败：ERROR_WEIGHTS 含 em_capital_outflow（C3-3a 已移除，旧版覆盖）")
    if "grv" in ERROR_WEIGHTS:
        raise RuntimeError("calibrator 自检失败：ERROR_WEIGHTS 含外生变量 grv（旧版覆盖）")

    # 2. 关键函数定义唯一性（防重复代码残留，D2/D3 教训）
    # 注意：用 "def X(" 精确匹配，防 compute_error_legacy 之类带后缀函数误计数
    _mod_src = _insp.getsource(_sys.modules[__name__])
    for _fn in ("run_calibration", "compute_error(", "build_history_range", "run_probe"):
        _cnt = _mod_src.count(f"def {_fn}")
        if _cnt != 1:
            raise RuntimeError(
                f"calibrator 自检失败：{_fn} 定义 {_cnt} 次（期望 1，存在重复代码残留）")


# C1-1a 兼容占位：旧 ERROR_THRESHOLD 语义已被相对触发取代，保留常量供外部引用
ERROR_THRESHOLD_LEGACY = 0.20

_self_check()
