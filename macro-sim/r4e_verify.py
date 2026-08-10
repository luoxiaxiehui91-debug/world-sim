import core.calibrator as c
from core.agents.financial import CommercialBankAgent
from core.agents.base import AgentParams
a2 = CommercialBankAgent(agent_id="A2", role="x", info_delay=1, activation_prob=0.7,
                         params=AgentParams(sensitivity=1.0, threshold=0.5, magnitude=1.0))
base = {"credit_spread": 300, "bank_credit_tightening": 0.3, "grv_stress": 0.55,
        "vix_stress": 0.1, "visible_actions": {}, "credit_spread_delta": -10}
out = "CACHE=" + str(c.CACHE_VERSION)
out += " grv055_csdown=" + a2._decide_rules(base)
out += " grv06_csdown=" + a2._decide_rules({**base, "grv_stress": 0.6})
out += " neutral_spread300=" + a2._decide_rules({**base, "credit_spread_delta": 0.0})
out += " tighten_csup=" + a2._decide_rules({**base, "credit_spread_delta": 10})
open("/app/output/r4e_verify.txt", "w").write(out)
