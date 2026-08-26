"""llm_pilot.py — LLM 决策试点 mixin v2（ADR-0012 选项A）

TIANJI_LLM_PILOT=1 时 use_llm 决策走 GLM-Z1-9B（sim_mc usage，免费档）。
审计：每次决策写 /app/macro_data/logs/llm_pilot_audit.log（agent/动作/来源/原文），
进程退出时打印统计——LLM 决策占比过低 = 试点无效，须排查而非采信结果。
"""
import os


class LLMPilotMixin:
    """混入需要 LLM 决策试点的 Agent 类（置于 MacroAgent 之前）。"""

    LLM_PERSONA = ""
    _AUDIT_PATH = "/app/macro_data/logs/llm_pilot_audit.log"

    def _audit(self, line: str):
        try:
            os.makedirs(os.path.dirname(self._AUDIT_PATH), exist_ok=True)
            from datetime import datetime
            with open(self._AUDIT_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
        except Exception:
            pass

    def _decide_llm(self, ctx: dict) -> str:
        if os.environ.get("TIANJI_LLM_PILOT") != "1":
            a = self._decide_soul(ctx).action
            self._audit(f"{self.agent_id} SOUL(开关未开) -> {a}")
            return a
        raw = ""
        try:
            from core.llm_client import call_llm, parse_action
            signals = self._snapshot_signals(ctx)
            sig_text = "\n".join(f"- {k}: {v}" for k, v in signals.items())
            actions = ", ".join(self.VALID_ACTIONS)
            prompt = (
                f"你是全球宏观推演模拟中的角色：{self.LLM_PERSONA}。\n"
                f"当前市场信号（数值仅为读数）：\n{sig_text}\n\n"
                f"你可以选择的行动：{actions}\n"
                f"基于你的角色立场与当前信号，选一个最符合你利益的行动。\n"
                f"只回答一行，格式严格为：ACTION: 动作名"
            )
            raw = call_llm(prompt, max_tokens=256)
            action = parse_action(raw, self.VALID_ACTIONS)
            self._audit(f"{self.agent_id} LLM -> {action} | raw={raw.strip()[:60]!r}")
            return action
        except Exception as e:
            self._audit(f"{self.agent_id} LLM异常({e}) -> 回退soul")
            a = self._decide_soul(ctx).action
            self._audit(f"{self.agent_id} SOUL_FALLBACK -> {a}")
            return a
