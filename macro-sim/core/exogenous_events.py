#!/usr/bin/env python3
"""
exogenous_events.py — 外生事件注入层（蓝图 v3 阶段 2 交付物）

设计原则（ADR-0012a）：
- 事件只通过三类显式通道进入仿真：感知 / 动作掩码 / 参数覆盖
- 禁止直接改写状态变量（保护行为真实性检验）
- 注入后 N 步无内生响应 → 告警（防静默失效）

事件库来源 v1：从 grv_history.jsonl 的维度月度变化自动抽取
（|Δ维度| ≥ 阈值即记为该维度的事件月），人工可在 JSONL 上润色。
"""
import json
import os
from pathlib import Path

GRV_HIST = "/app/macro_data/grv_history.jsonl"
DIM_KEYS = {
    "middle_east_energy": "中东能源",
    "russia_europe": "俄欧冲突",
    "taiwan_strait": "台海局势",
    "us_china_strategic": "中美博弈",
    "climate_risk": "气候风险",
    "sanctions_risk": "制裁风险",
    "japan_monetary": "日元货币",
    "social_stress": "社会压力",
}
DELTA_THRESHOLD = 8.0  # 维度月变化超过此值记为事件


def build_events_from_history(grv_path: str = GRV_HIST,
                              threshold: float = DELTA_THRESHOLD,
                              start_month: str = None,
                              end_month: str = None) -> list[dict]:
    """扫描 GRV 历史维度变化，自动生成事件条目（按月聚合）。
    start_month/end_month："YYYY-MM" 窗口过滤（默认全历史）。"""
    rows = {}
    with open(grv_path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            d = json.loads(ln)
            ts = d.get("updated", "")[:7]
            if ts and ts not in rows:
                rows[ts] = d
    months = sorted(rows.keys())
    events = []
    for prev_m, cur_m in zip(months, months[1:]):
        p, c = rows[prev_m], rows[cur_m]
        changes = []
        for key, name in DIM_KEYS.items():
            pv = float(p.get(key) or 0)
            cv = float(c.get(key) or 0)
            dv = cv - pv
            if abs(dv) >= threshold:
                arrow = "↑" if dv > 0 else "↓"
                changes.append(f"{name}{arrow}{abs(dv):.0f}")
        if start_month and cur_m < start_month:
            continue
        if end_month and cur_m > end_month:
            continue
        if changes:
            events.append({
                "month": cur_m,
                "summary": f"现实事件冲击：{'；'.join(changes)}",
                "channels": {"perception": [e for e in changes],
                             "action_mask": {}, "param_override": {}},
                "source": "auto_grv_dims",
            })
    return events


class ExogenousInjector:
    """按月向仿真注入外生事件（三通道）。"""

    def __init__(self, events: list[dict], alert_steps: int = 2):
        self.by_month = {e["month"]: e for e in events}
        self.alert_steps = alert_steps
        self.pending_alert = None  # (month, steps_since)

    def inject(self, ctx: dict, month: str) -> dict:
        """把该月事件写入 agent ctx（感知通道）。返回事件摘要或 None。"""
        ev = self.by_month.get(month)
        if not ev:
            return None
        ctx["exogenous_events"] = ev["channels"]["perception"]
        # 传导监控挂起：等待后续步的响应检查
        self.pending_alert = (month, 0)
        return ev["summary"]

    def check_response(self, month: str, grv_delta: float):
        """注入后各步调用：|Δgrv|>0.5 视为有内生响应，解除告警。"""
        if self.pending_alert and abs(grv_delta) > 0.5:
            self.pending_alert = None
        elif self.pending_alert:
            m, n = self.pending_alert
            self.pending_alert = (m, n + 1)
            if n + 1 >= self.alert_steps:
                print(f"[exo] ⚠️ 传导失败告警：{m} 月事件注入后 {n+1} 步无内生响应",
                      flush=True)
                self.pending_alert = None

    def mask_actions(self, agent_id: str, month: str,
                     valid_actions: list[str]) -> list[str]:
        """动作掩码通道（v1 预留：事件库 action_mask 为空时不修改）。"""
        ev = self.by_month.get(month)
        if ev and agent_id in (ev["channels"]["action_mask"] or {}):
            allowed = ev["channels"]["action_mask"][agent_id]
            return [a for a in valid_actions if a in allowed] or valid_actions
        return valid_actions


if __name__ == "__main__":
    evs = build_events_from_history()
    print(f"[exo] 自动抽取事件月数：{len(evs)}")
    for e in evs[:6]:
        print(" ", e["month"], e["summary"])
