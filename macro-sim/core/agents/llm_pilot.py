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


    _TB_WINDOW = 60.0   # 滑动窗口秒数
    _TPM_SOFT = 45000.0 # TPM 软上限（官方 50000 留余量）

    def _throttle(self, est_tokens: int):
        """滑动窗口令牌桶：估算最近 60s 已耗 tokens，不足则等待。"""
        import time as _t
        now = _t.time()
        hist = getattr(LLMPilotMixin, "_tok_hist", [])
        hist = [t for t in hist if now - t[0] < self._TB_WINDOW]
        used = sum(x[1] for x in hist)
        if used + est_tokens > self._TPM_SOFT:
            wait = self._TB_WINDOW - (now - hist[0][0]) + 0.5 if hist else 1.0
            print(f"[llm_pilot] TPM 节流 {wait:.0f}s（近窗 {used:.0f} tokens）", flush=True)
            _t.sleep(max(wait, 0.5))
            hist = [t for t in LLMPilotMixin._tok_hist if _t.time() - t[0] < self._TB_WINDOW]
        hist.append((now, est_tokens))
        LLMPilotMixin._tok_hist = hist

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
            self._throttle(1500)
            raw = call_llm(prompt, max_tokens=1024)  # 蓝图v3：放开思考链（免费档不计费）
            action = parse_action(raw, self.VALID_ACTIONS)
            self._audit(f"{self.agent_id} LLM -> {action} | raw={raw.strip()[:60]!r}")
            return action
        except Exception as e:
            self._audit(f"{self.agent_id} LLM异常({e}) -> 回退soul")
            a = self._decide_soul(ctx).action
            self._audit(f"{self.agent_id} SOUL_FALLBACK -> {a}")
            return a
