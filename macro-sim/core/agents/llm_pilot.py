#!/usr/bin/env python3
"""
llm_pilot.py — LLM 决策试点 mixin v4（ADR-0012a 阶段 3）
功能：审计日志 / TPM 令牌桶 / max_tokens=1024 / 外生事件钩子 / 动态 persona
开关：TIANJI_LLM_PILOT=1 启用；未设置时回退 soul 决策（行为与主线一致）。
"""
import os

NL = chr(10)


class LLMPilotMixin:
    """混入需要 LLM 决策试点的 Agent 类（置于 MacroAgent 之前）。"""

    LLM_PERSONA = ""          # str=全类共用；dict=按 agent_id 取
    _AUDIT_PATH = "/app/macro_data/logs/llm_pilot_audit.log"
    _EXO_LOOKUP = None        # callable(agent_id, month_str) -> str|None
    _TB_WINDOW = 60.0         # 令牌桶滑动窗口秒数
    _TPM_SOFT = 45000.0       # TPM 软上限（官方 50000 留余量）

    def _audit(self, line):
        try:
            from datetime import datetime
            os.makedirs(os.path.dirname(self._AUDIT_PATH), exist_ok=True)
            with open(self._AUDIT_PATH, "a", encoding="utf-8") as f:
                f.write("[" + datetime.now().strftime("%H:%M:%S") + "] " + line + "\n")
        except Exception:
            pass

    def _llm_persona(self):
        if isinstance(self.LLM_PERSONA, dict):
            return self.LLM_PERSONA.get(self.agent_id, "主权决策者")
        return self.LLM_PERSONA

    def _throttle(self, est_tokens):
        import time as _t
        now = _t.time()
        hist = [t for t in getattr(LLMPilotMixin, "_tok_hist", [])
                if now - t[0] < self._TB_WINDOW]
        used = sum(x[1] for x in hist)
        if used + est_tokens > self._TPM_SOFT and hist:
            wait = max(self._TB_WINDOW - (now - hist[0][0]), 0.5)
            print("[llm_pilot] TPM 节流 %.0fs（近窗 %.0f tokens）" % (wait, used),
                  flush=True)
            _t.sleep(wait)
            hist = [t for t in LLMPilotMixin._tok_hist
                    if _t.time() - t[0] < self._TB_WINDOW]
        hist.append((now, est_tokens))
        LLMPilotMixin._tok_hist = hist

    def _decide_llm(self, ctx: dict) -> str:
        aid = getattr(self, "agent_id", type(self).__name__)
        if os.environ.get("TIANJI_LLM_PILOT") != "1":
            a = self._decide_soul(ctx).action
            self._audit(aid + " SOUL(开关未开) -> " + a)
            return a
        try:
            from core.llm_client import call_llm, parse_action
            signals = self._snapshot_signals(ctx)
            sig_text = NL.join("- %s: %s" % (k, v) for k, v in signals.items())
            actions = ", ".join(self.VALID_ACTIONS)
            exo_line = ""
            if type(self)._EXO_LOOKUP:
                month = ctx.get("month") or ctx.get("date") or ""
                ev = type(self)._EXO_LOOKUP(aid, month)
                if ev:
                    exo_line = NL + "本月现实世界正在发生：" + ev + NL
            prompt = (
                "你是全球宏观推演模拟中的角色：" + self._llm_persona() + "。" + NL +
                "当前市场信号（数值仅为读数）：" + NL + sig_text + NL + NL +
                (exo_line if exo_line else "") +
                "你可以选择的行动：" + actions + NL +
                "基于你的角色立场、本月现实冲击与当前信号，选一个最符合你利益的行动。" + NL +
                "只回答一行，格式严格为：ACTION: 动作名")
            self._throttle(1500)
            raw = call_llm(prompt, max_tokens=1024)
            action = parse_action(raw, self.VALID_ACTIONS)
            self._audit("%s LLM -> %s | raw=%r" % (aid, action, (raw or "").strip()[:60]))
            return action
        except Exception as e:
            self._audit("%s LLM异常(%s) -> 回退soul" % (aid, e))
            a = self._decide_soul(ctx).action
            self._audit(aid + " SOUL_FALLBACK -> " + a)
            return a
