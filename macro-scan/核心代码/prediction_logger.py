"""
模块01（v2）：预测日志
修复：
  - 路径改用 config.py
  - ID 改用 uuid4 避免同日重复
  - 新增 regime/stress_signals 字段（与模块05联动）
  - log_prediction() 检查同日同场景重复，不写入重复条目
"""
import json
import uuid
from datetime import datetime, date
from optim_config import PREDICTIONS_LOG, GDP_HIT_TOLERANCE, UNRATE_HIT_TOLERANCE
from optim_config import PREDICTIONS_LOG, GDP_HIT_TOLERANCE, UNRATE_HIT_TOLERANCE, now_iso_utc


def log_prediction(
    indicators: dict,
    mc_results: dict,
    risk_scores: dict,
    scenario_label: str = "baseline",
    horizon_months: int = 3,
    regime: str | None = None,
    stress_signals: int | None = None,
) -> str | None:
    """
    追加一条预测记录到 predictions_log.json。
    若今日同场景已有记录则跳过，返回 None。

    Parameters
    ----------
    indicators     : 当前指标快照 {"FEDFUNDS": 4.33, "UNRATE": 4.1, ...}
    mc_results     : 蒙特卡洛输出
                     必须包含的 key（值为 float 或 None）：
                       recession_prob  — 衰退概率（%）
                       gdp_p50         — GDP增速中位数（ppt）
                       gdp_p10         — GDP增速悲观情景（ppt）
                       gdp_p90         — GDP增速乐观情景（ppt）
                       unrate_p50      — 失业率中位数（%）
                       cpi_p50         — CPI YoY中位数（%）
    risk_scores    : {"overall": 42, "credit": 6, "geo": 3, ...}
    scenario_label : "baseline" / "stress" / 自定义情景名
    horizon_months : 预测时间跨度（月），默认3
    regime         : "normal" / "stress"（来自模块05 detect_regime）
    stress_signals : 压力信号数量（来自模块05）
    """
    import os, math
    os.makedirs(os.path.dirname(PREDICTIONS_LOG), exist_ok=True)

    log = _load_log()

    # 去重：今日同场景已有记录则跳过
    today = date.today().isoformat()
    existing = [e for e in log
                if e.get("created_at", "")[:10] == today
                and e.get("scenario") == scenario_label]
    if existing:
        print(f"[预测日志] 今日已有 {scenario_label} 记录，跳过写入。")
        return None

    # 计算验证到期日（3个月后的1号）
    verify_date = _add_months(date.today(), horizon_months).replace(day=1).isoformat()

    # 清理 NaN
    def _clean(v):
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return round(v, 4) if isinstance(v, float) else v

    entry = {
        "id": str(uuid.uuid4()),
        "created_at": now_iso_utc(),
        "scenario": scenario_label,
        "horizon_months": horizon_months,
        "verify_after": verify_date,
        "status": "pending",

        # 体制信息（模块05）
        "regime": regime,
        "stress_signals": stress_signals,

        # 指标快照
        "input_snapshot": {k: _clean(v) for k, v in (indicators or {}).items()},

        # 预测值（key名与模块02验证引擎严格对应）
        "predictions": {
            "recession_prob_pct": _clean(mc_results.get("recession_prob")),
            "gdp_p50":            _clean(mc_results.get("gdp_p50")),
            "gdp_p10":            _clean(mc_results.get("gdp_p10")),
            "gdp_p90":            _clean(mc_results.get("gdp_p90")),
            "unrate_p50":         _clean(mc_results.get("unrate_p50")),
            "cpi_yoy_p50":        _clean(mc_results.get("cpi_p50")),
        },

        "risk_scores": {k: _clean(v) for k, v in (risk_scores or {}).items()},

        # 验证结果（由模块02填入）
        "actuals": None,
        "accuracy": None,
        "verified_at": None,
    }

    log.append(entry)
    _save_log(log)
    print(f"[预测日志] 已记录 {entry['id'][:8]}… | 场景:{scenario_label} | 验证期:{verify_date}")
    return entry["id"]


def get_pending_verifications() -> list[dict]:
    """返回已到验证期、状态仍为 pending 的记录。"""
    today = date.today().isoformat()
    return [e for e in _load_log()
            if e.get("status") == "pending" and e.get("verify_after", "") <= today]


# ── 内部工具 ──────────────────────────────────────────────────────────────────
def _load_log() -> list:
    """从 PREDICTIONS_LOG 加载日志数组，文件不存在返回空列表。"""
    import os
    if not os.path.exists(PREDICTIONS_LOG):
        return []
    with open(PREDICTIONS_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_log(log: list):
    """将日志数组原子写入 PREDICTIONS_LOG，防止20:00/20:05并发写入导致记录丢失。"""
    import os
    tmp = PREDICTIONS_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PREDICTIONS_LOG)


def _add_months(d: date, months: int) -> date:
    """安全地给日期加 N 个月（处理月末边界，如 1月31日+1月=2月28日）。"""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    import calendar
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# ── 独立运行：打印日志摘要 ────────────────────────────────────────────────────
if __name__ == "__main__":
    log = _load_log()
    pending = [e for e in log if e["status"] == "pending"]
    verified = [e for e in log if e["status"] == "verified"]
    print(f"预测日志：共 {len(log)} 条 | 待验证 {len(pending)} | 已验证 {len(verified)}")
    for e in log[-5:]:
        p = e.get("predictions", {})
        print(f"  {e['id'][:8]}… {e['created_at'][:10]} "
              f"场景:{e['scenario']} 衰退概率:{p.get('recession_prob_pct')}% "
              f"体制:{e.get('regime','?')} 状态:{e['status']}")
