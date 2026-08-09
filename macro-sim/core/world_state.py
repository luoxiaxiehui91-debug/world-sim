"""
world_state.py — 宏观世界状态 v2

变化：
- 新增内生变量：retail_panic / china_credit_impulse / us_fiscal_pressure / yen_carry_risk
- get_agent_context() 输出绝对压力信号（grv_stress/vix_stress/yield_inverted）
- load_monthly_history()：加载月度历史数据，供校准循环使用
- load_from_macro_scan()：从当前真实数据加载初始状态（保留）
"""

from dataclasses import dataclass, field
from datetime import datetime, date
import copy


@dataclass
class MacroWorldState:
    # ── 外生变量（有历史真值，校准时对比）────────────────
    vix: float
    vix_baseline: float
    grv: float
    grv_baseline: float
    grv_energy: float
    grv_energy_baseline: float
    grv_military: float
    grv_trade: float
    us_china_grv: float       # 中美战略维度（A8专用）
    t10y2y: float             # 收益率曲线斜率 bps
    credit_spread: float      # 信用利差 bps (BAA-10Y)
    dff: float                # 联邦基金利率 %
    situation_level: int
    # R4d：credit_spread 月变化量（bps）——A2 方向对齐用（docs/r4c-b-a2-direction-alignment.md）。
    # 校准循环在 step 前设置（prev_row vs curr_row）；非校准运行默认 0.0 → A2 方向闸不触发、
    # 生产路径逐字节不变。
    credit_spread_delta: float = 0.0
    # D7 fix: 补充 6 个 GRV 维度，使仿真输入与天枢产出的 11 维对齐
    climate_risk: float = 0.0       # 气候风险 [0,100]，来自 fetch_climate_signals
    disaster_risk: float = 0.0      # 灾害风险 [0,100]，来自 fetch_disaster_signals
    sanctions_risk: float = 0.0     # 制裁风险 [0,100]，来自 fetch_sanctions
    seismic_risk: float = 0.0       # 地震压力 [0,100]，来自 fetch_earthquake
    energy_grid_risk: float = 0.0   # 能源电网压力 [0,100]，来自 fetch_energy
    japan_monetary: float = 0.0     # 日元货币压力 [0,100]，来自 DEXJPUS+JGB
    social_stress: float = 0.0      # 社会情绪压力 [0,100]，来自 gdelt_scores（R09，v3.8.3）
    cultural_friction: float = 0.0  # 文化摩擦 [0,100]，来自 gdelt_scores（R10，v3.8.3）

    # A 类激活（v2.2，D1）：GRV 全维度原始 0-100 值（grv_latest.json 透传），
    # 供 S 类主权 Agent 的 soul trigger 直接引用（russia_europe/taiwan_strait/global_composite 等）
    # 也作为 sovereign 行动 delta 的写入目标（0-100 量纲直写，绕过 _apply_delta clamp(0,1) 截断）
    grv_dimensions: dict = field(default_factory=dict)

    # ── 内生变量（仿真中演化）────────────────────────────
    fed_rate_change: float = 0.0
    bank_credit_tightening: float = 0.0
    fund_risk_appetite: float = 0.0
    market_sentiment: float = 0.0
    energy_supply_risk: float = 0.0
    liquidity_premium: float = 0.0
    em_capital_outflow: float = 0.0
    consecutive_negative_steps: int = 0
    # v2 新增
    retail_panic: float = 0.0         # 散户恐慌程度 [0,1]
    china_credit_impulse: float = 0.0 # 中国信用脉冲 [-1,1]，正=扩张
    us_fiscal_pressure: float = 0.0   # 美国财政压力 [0,1]
    yen_carry_risk: float = 0.0       # 日元套息平仓风险 [0,1]
    usd_cny: float = 7.1              # 美元/人民币汇率
    ecb_rate: float = 3.0             # 欧央行利率 %
    sp500_change: float = 0.0         # 标普500 6个月涨跌幅 [0,1] 归一（负=下跌）
    # 慢变量（月频，来自 slow_variables.json，Sprint-2 注入）
    irp: float = 0.0   # 国际关系压力指数 [0,1]
    ucri: float = 0.0  # 城市化/集中化风险指数 [0,1]
    gci: float = 0.0   # 全球冲突强度指数 [0,1]

    # ── 仿真元数据 ────────────────────────────────────────
    cycle: int = 0
    total_cycles: int = 100
    step_label: str = ""      # 如 "2024-01"，校准期用于标记月份
    trigger_event: str = ""
    recent_news: list = field(default_factory=list)
    sim_id: str = ""
    trigger_date: str = ""

    def get_agent_context(self, agent_role: str, soul: dict = None) -> dict:
        """
        包含相对 delta + 绝对压力信号。
        所有角色都能看到基础字段，角色专属字段另外追加。
        soul 参数（v2.2，D1）：S 类主权 Agent 传入 soul 文件内容，
        用于把 internal_state/resources 字段（economic_buffer_months 等）注入 ctx，
        使 soul 内的派系 trigger / red_line_triggers 能读到。
        """
        vix_shift    = (self.vix - self.vix_baseline) / max(self.vix_baseline, 1)
        grv_shift    = (self.grv - self.grv_baseline) / 100.0
        energy_shift = (self.grv_energy - self.grv_energy_baseline) / 100.0

        # 绝对压力信号
        grv_stress  = round(max(0.0, (self.grv - 50.0) / 50.0), 3)
        vix_stress  = round(max(0.0, (self.vix - 18.0) / 30.0), 3)
        yield_inv   = 1 if self.t10y2y < -20 else 0

        ctx = {
            "external_pressure_shift": round((vix_shift + grv_shift) / 2, 3),
            "internal_stress": round(
                self.market_sentiment * -0.5 + self.bank_credit_tightening * 0.5, 3
            ),
            "liquidity_tension": round(self.liquidity_premium, 3),
            "grv_stress":    grv_stress,
            "vix_stress":    vix_stress,
            "yield_inverted": yield_inv,
            "market_sentiment": round(self.market_sentiment, 3),
            "credit_spread_delta": round(self.credit_spread_delta, 4),  # R4d：A2 方向对齐
            "cycle": self.cycle,
        }

        if agent_role in ("hedge_fund", "institution"):
            ctx["vix_shift"]         = round(vix_shift, 3)
            ctx["t10y2y"]            = self.t10y2y
            ctx["fund_risk_appetite"] = round(self.fund_risk_appetite, 3)
            ctx["credit_tightening"] = round(self.bank_credit_tightening, 3)
            # D7: 制裁风险和地震/灾害压力影响全球避险情绪
            ctx["sanctions_risk"]  = round(self.sanctions_risk / 100.0, 3)
            ctx["disaster_risk"]   = round(self.disaster_risk / 100.0, 3)
            ctx["seismic_risk"]    = round(self.seismic_risk / 100.0, 3)

        if agent_role == "fed":
            ctx["fed_rate_change"] = self.fed_rate_change
            ctx["credit_spread"]   = self.credit_spread
            ctx["dff"]             = self.dff

        if agent_role == "commercial_bank":
            ctx["credit_spread"]        = self.credit_spread
            ctx["bank_credit_tightening"] = round(self.bank_credit_tightening, 3)
            ctx["liquidity_premium"]    = round(self.liquidity_premium, 3)

        if agent_role == "energy_gov":
            ctx["energy_tension"] = round(
                energy_shift + self.energy_supply_risk + self.grv_energy / 100.0, 3
            )
            # D7: 能源电网和气候信号对能源国决策有直接影响
            ctx["energy_grid_risk"] = round(self.energy_grid_risk / 100.0, 3)
            ctx["climate_risk"]     = round(self.climate_risk / 100.0, 3)

        if agent_role == "media":
            ctx["recent_news"]      = self.recent_news[:3]
            # R09/R10：社会压力和文化摩擦是媒体放大的核心驱动
            ctx["social_stress"]    = round(self.social_stress / 100.0, 3)
            ctx["cultural_friction"] = round(self.cultural_friction / 100.0, 3)

        if agent_role == "em_central_bank":
            ctx["em_capital_outflow"] = round(self.em_capital_outflow, 3)
            ctx["dff_shift"]          = round(self.fed_rate_change / 100.0, 3)

        if agent_role == "china_pboc":
            ctx["china_credit_impulse"] = round(self.china_credit_impulse, 3)
            ctx["us_china_grv"]         = round(self.us_china_grv, 3)
            ctx["usd_cny"]              = round(self.usd_cny, 4)

        if agent_role == "us_treasury":
            ctx["us_fiscal_pressure"] = round(self.us_fiscal_pressure, 3)

        if agent_role == "boj":
            ctx["yen_carry_risk"]  = round(self.yen_carry_risk, 3)
            # D7: japan_monetary 直接驱动 BOJ 决策
            ctx["japan_monetary"]  = round(self.japan_monetary / 100.0, 3)

        if agent_role == "ecb":
            ctx["ecb_rate"] = round(self.ecb_rate, 2)

        if agent_role in ("hedge_fund", "institution"):
            ctx["sp500_change"] = round(self.sp500_change, 4)

        if agent_role == "retail":
            ctx["retail_panic"] = round(self.retail_panic, 3)

        # ── S 类主权 Agent 专属（v2.2，D1/B1/C1 修复）────────────
        # 从 grv_dimensions 透传 GRV 维度（0-100 原生量纲，与 soul trigger 语义一致），
        # 从 soul internal_state/resources 注入经济缓冲/国内压力等字段，
        # ctx["board"] 由 simulation.step() 注入（避免 world_state ↔ sovereign 循环 import）。
        if agent_role in ("usa", "china", "eu", "russia", "opec_core"):
            gd = self.grv_dimensions
            # GRV 维度（缺失时安全默认；us_china_strategic/global_composite 默认 50 = 中性）
            ctx["russia_europe"]       = float(gd.get("russia_europe", 0.0))
            ctx["taiwan_strait"]       = float(gd.get("taiwan_strait", 0.0))
            ctx["us_china_strategic"]  = float(gd.get("us_china_strategic", 50.0))
            ctx["global_composite"]    = float(gd.get("global_composite", 50.0))
            ctx["middle_east_energy"]  = float(gd.get("middle_east_energy", 0.0))
            ctx["sanctions_risk"]      = float(gd.get("sanctions_risk", 0.0))
            ctx["energy_grid_risk"]    = float(gd.get("energy_grid_risk", 0.0))
            ctx["climate_risk"]        = float(gd.get("climate_risk", 0.0))
            ctx["social_stress"]       = float(gd.get("social_stress", 0.0))
            # soul 内部状态（economic_buffer_months 在 internal_state 或 resources 二选一）
            st = (soul or {}).get("internal_state", {}) or {}
            rs = (soul or {}).get("resources", {}) or {}
            ctx["domestic_political_pressure"] = float(st.get("domestic_political_pressure", 0.0))
            # v2.2 验证迭代（结构性多空）：危机深化 → 国内政治压力上升
            # （market_sentiment -0.5 → 压力 0.75），让 domestic_lobby/stability_faction
            # 等约束派在高压下也有触发路径 —— 高压时不再是"全体一致鹰派"，出现反制声音
            ctx["domestic_political_pressure"] = max(
                ctx["domestic_political_pressure"],
                max(0.0, -self.market_sentiment * 1.5),
            )
            ctx["economic_buffer_months"] = float(
                st.get("economic_buffer_months", rs.get("economic_buffer_months", 0.0))
            )
            ctx["wti_price"] = float(st.get("wti_price_ref", 80.0))

        return ctx

    def to_dict(self) -> dict:
        return {
            "cycle":         self.cycle,
            "step_label":    self.step_label,
            "vix":           round(self.vix, 2),
            "grv":           round(self.grv, 2),
            "grv_energy":    round(self.grv_energy, 2),
            "us_china_grv":  round(self.us_china_grv, 2),
            "t10y2y":        round(self.t10y2y, 1),
            "credit_spread": round(self.credit_spread, 1),
            "dff":           round(self.dff, 2),
            "market_sentiment":       round(self.market_sentiment, 3),
            "bank_credit_tightening": round(self.bank_credit_tightening, 3),
            "liquidity_premium":      round(self.liquidity_premium, 3),
            "energy_supply_risk":     round(self.energy_supply_risk, 3),
            "em_capital_outflow":     round(self.em_capital_outflow, 3),
            "retail_panic":           round(self.retail_panic, 3),
            "china_credit_impulse":   round(self.china_credit_impulse, 3),
            "us_fiscal_pressure":     round(self.us_fiscal_pressure, 3),
            "yen_carry_risk":         round(self.yen_carry_risk, 3),
            "usd_cny":                round(self.usd_cny, 4),
            "ecb_rate":               round(self.ecb_rate, 2),
            "sp500_change":           round(self.sp500_change, 4),
            "consecutive_negative_steps": self.consecutive_negative_steps,
            # D7: 6个新GRV维度
            "climate_risk":     round(self.climate_risk, 1),
            "disaster_risk":    round(self.disaster_risk, 1),
            "sanctions_risk":   round(self.sanctions_risk, 1),
            "seismic_risk":     round(self.seismic_risk, 1),
            "energy_grid_risk": round(self.energy_grid_risk, 1),
            "japan_monetary":   round(self.japan_monetary, 1),
            "social_stress":    round(self.social_stress, 1),
            "cultural_friction": round(self.cultural_friction, 1),
            # v2.2 D1：GRV 全维度（sovereign 行动 delta 直写后的最新值，供报告/天玑）
            "grv_dimensions":   {k: round(float(v), 1) for k, v in self.grv_dimensions.items()},
        }

    def get_observable_values(self) -> dict:
        """校准循环用：返回有历史真值的外生变量，用于计算误差"""
        return {
            "grv":           self.grv,
            "credit_spread": self.credit_spread,
            "t10y2y":        self.t10y2y,
            "dff":           self.dff,
        }


# ── 出血规则参数 ──────────────────────────────────────────
BLEED_PARAMS = {
    "vix_bleed_threshold":       -0.5,
    "vix_bleed_steps":            3,
    "vix_bleed_rate":             2.0,
    "vix_bleed_max":             20.0,
    # R4h ②-A（v2.0.39）：yen_carry bleed 专用封顶——原出血5 无上限（+5.0/步持续到
    # vix 峰值 162-238，vix_stress>1.0 豁免恒真 → TIGHTEN wrong 100% 豁免放行）。
    # 实测 vix 存量主源=yen_carry bleed（sentiment bleed +2.0 从未触发，delta 分布 0/5.0）。
    # R4h ①-C（v2.0.40）：cap 19 → 17（① 引入 act_prob 0.76 后 M6 余量 3：wrong 12≤17）。
    # ② 参数扫描（5 seed 探针，单一 decay 口径）：cap=19 + decay=0.20 → vix 峰值 53.3
    # （162-238 大幅收敛，vix>48 步 21-36），TIGHTEN wrong 16≤17（裁决闸达标 18→16）、
    # M2 silence diff 全 seed ≤+0.041（防沉默回归）、vix_stress 峰值 1.18>0.35（A2 触发线保持）。
    # 边界（② 口径）：cap<19 → wrong 少但 M2 超（cap18: wrong14 但 seed2024 +0.062）；cap>19 → wrong 超 17。
    # ① 联合口径（cap17 + act_prob 0.76 + ease_ok）：TIGHTEN wrong 12≤17、EASE wrong 0。
    "vix_yen_carry_bleed_max":  17.0,
    "grv_bleed_threshold":        0.6,
    "grv_bleed_rate":             0.5,   # 降速：原3.0太猛，50步内推到上限导致路径无差异
    "credit_spread_bleed_rate":   8.0,
    # v2 新增
    "yen_carry_bleed_threshold":  0.7,   # 套息平仓触发流动性危机
    "yen_carry_vix_impact":       5.0,   # 套息平仓每步 VIX 上升幅度
    "retail_panic_sentiment":    -0.15,  # 散户恐慌每步对情绪的拖累
}


def apply_bleed_rules(world: MacroWorldState, params: dict = None):
    if params is None:
        params = BLEED_PARAMS

    vix_delta_total = world.vix - world.vix_baseline

    # 出血1：情绪崩溃 → VIX 上升
    if (world.market_sentiment < params["vix_bleed_threshold"]
            and world.consecutive_negative_steps >= params["vix_bleed_steps"]
            and vix_delta_total < params["vix_bleed_max"]):
        world.vix += params["vix_bleed_rate"]

    # 出血2：能源供给风险 → GRV 能源维度上升
    if world.energy_supply_risk > params["grv_bleed_threshold"]:
        world.grv_energy += params["grv_bleed_rate"]          # 无上限截断
        world.grv += params["grv_bleed_rate"] * 0.3

    # 出血3：信贷收紧 → 信用利差扩大
    if world.bank_credit_tightening > 0.5:
        world.credit_spread += params["credit_spread_bleed_rate"]

    # 出血4：资本外流 → 收益率曲线进一步倒挂
    if world.em_capital_outflow > 0.4:
        world.t10y2y -= 5.0

    # 出血5（v2）：日元套息平仓 → VIX 跳升（非线性）
    # R4h ②-A（v2.0.39）：加 vix_delta_total < vix_yen_carry_bleed_max 封顶（原无上限，
    # vix 存量锁边 162-238 → 豁免恒真 → TIGHTEN wrong 100% 豁免放行）。语义：套息平仓
    # 仍是"真危机"（vix 单步 +5.0 跳变），但存量受上限约束，不再无界累积。
    if (world.yen_carry_risk > params["yen_carry_bleed_threshold"]
            and vix_delta_total < params.get("vix_yen_carry_bleed_max", params["vix_bleed_max"])):
        world.vix += params["yen_carry_vix_impact"]
        world.liquidity_premium = min(1.0, world.liquidity_premium + 0.2)

    # 出血6（v2）：散户恐慌 → 情绪持续下拉
    if world.retail_panic > 0.5:
        apply_sentiment_delta(world, params["retail_panic_sentiment"])


def apply_sentiment_delta(world: MacroWorldState, raw_delta: float):
    s = world.market_sentiment
    # 2026-08-08 A 修复（calib-fix-review 终局）：damping 下限。
    # 原 1/(1+3|s|) 在 s=-1 时压到 0.25 → 与 MONTHLY_SCALE=0.12 双压，
    # sentiment 钉死 -1.0 欠响应（46/50 步 floor）根因之一。
    # 初版 floor 0.5（只放大 |s|≥1/3 极端区）实测仍不足（贴边 54% > 50%，
    # 正 delta 18% < 20%）→ 按终局裁决授权升 A=1.0（damping 恒 1，恢复不受压缩）。
    damping = max(1.0, 1.0 / (1.0 + 3.0 * abs(s)))
    world.market_sentiment = max(-1.0, min(1.0, s + raw_delta * damping))


def apply_natural_decay(world: MacroWorldState):
    # 月度时间步长：衰减速率大幅放慢（原0.97是日度感觉，月度改为0.995）
    world.market_sentiment       *= 0.995
    world.bank_credit_tightening *= 0.97
    world.liquidity_premium      *= 0.93
    world.energy_supply_risk     *= 0.98
    world.retail_panic           *= 0.80   # 散户情绪消退快
    world.yen_carry_risk         *= 0.92
    # D4 fix: 补充 4 个遗漏变量，防止无均值回归导致单调漂移锁边
    world.fund_risk_appetite     *= 0.90
    world.em_capital_outflow     *= 0.93
    world.us_fiscal_pressure     *= 0.97
    world.china_credit_impulse   *= 0.92   # 信用脉冲均值回归到 0

    # GRV 均值回归
    world.grv = world.grv * 0.97 + world.grv_baseline * 0.03
    world.grv_energy = world.grv_energy * 0.97 + world.grv_energy_baseline * 0.03

    # R4h ②-A（v2.0.39）：vix 均值回归（D4 fix 遗漏变量——无 decay 存量不回吐，
    # vix 单调漂移锁边 162-238，vix_stress>1.0 豁免恒真 → TIGHTEN wrong 100% 豁免放行）。
    # 与 D4 其余变量同语义：vix 每步向 baseline 回归 20% 偏离量（0.80/0.20）。
    # 配合 yen_carry bleed 封顶（vix_delta<19）→ vix 峰值≈53.3（162-238 收敛，豁免部分开），
    # vix_stress 峰值 1.18 > 0.35（A2 vix 触发线保持活跃，防过度压制）。
    world.vix = world.vix * 0.80 + world.vix_baseline * 0.20


# ── 月度历史数据加载（校准循环用）────────────────────────

def load_monthly_history(
    grv_path:  str = "/app/macro_data/grv_history.jsonl",
    fred_path: str = "/app/macro_data/fred_history",
    months:    int = 50,
) -> list[dict]:
    """
    加载最近 N 个月的历史数据，每条对应一个月。
    返回列表，每条：{"date": "2024-01", "grv": ..., "t10y2y": ..., "credit_spread": ..., "dff": ...}
    供校准循环逐步读取真实值。
    """
    import json, csv, os
    from collections import defaultdict

    # ── 读 GRV 月度数据 ───────────────────────────────────
    grv_monthly = {}
    try:
        with open(grv_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                ts = d.get("updated", "")[:7]  # "YYYY-MM"
                if ts and ts not in grv_monthly:
                    grv_monthly[ts] = {
                        "grv":              d.get("global_composite") or 50.0,
                        "grv_energy":       d.get("middle_east_energy") or 0.0,
                        "grv_military":     ((d.get("russia_europe") or 0) + (d.get("taiwan_strait") or 0)) / 200,
                        "grv_trade":        (d.get("us_china_strategic") or 0) / 100,
                        "us_china_grv":     d.get("us_china_strategic") or 50.0,
                        # D7 扩展维度（校准期与预测期输入空间对齐）
                        "climate_risk":     float(d.get("climate_risk") or 0.0),
                        "disaster_risk":    float(d.get("disaster_risk") or 0.0),
                        "sanctions_risk":   float(d.get("sanctions_risk") or 0.0),
                        "seismic_risk":     float(d.get("seismic_risk") or 0.0),
                        "energy_grid_risk": float(d.get("energy_grid_risk") or 0.0),
                        "japan_monetary":   float(d.get("japan_monetary") or 0.0),
                        "social_stress":    float(d.get("social_stress") or 0.0),
                        "cultural_friction":float(d.get("cultural_friction") or 0.0),
                    }
    except Exception as e:
        print(f"[world_state] GRV 历史读取失败：{e}")

    # ── 读 FRED 月度数据（日度降采样取月末值）───────────────
    fred_monthly = defaultdict(dict)

    def read_fred_csv(filename: str, key: str):
        path = os.path.join(fred_path, filename)
        try:
            with open(path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    dt = row.get("date", "")[:7]
                    val = row.get("value", "")
                    if dt and val and val != ".":
                        fred_monthly[dt][key] = float(val)  # 同月后面的覆盖前面，取月末
        except Exception as e:
            print(f"[world_state] FRED {filename} 读取失败：{e}")

    read_fred_csv("T10Y2Y.csv", "t10y2y")
    read_fred_csv("BAA10Y.csv", "credit_spread")
    read_fred_csv("DFF.csv",    "dff")
    read_fred_csv("ECBDFR.csv", "ecb_rate")   # D14 fix: 欧央行存款利率
    read_fred_csv("DEXCHUS.csv","usd_cny")    # D14 fix: 美元/人民币汇率

    # T10Y2Y 和 BAA10Y 单位是 %，转换成 bps（×100）
    for dt in fred_monthly:
        if "t10y2y" in fred_monthly[dt]:
            fred_monthly[dt]["t10y2y"] *= 100
        if "credit_spread" in fred_monthly[dt]:
            fred_monthly[dt]["credit_spread"] *= 100

    # ── 合并，取最近 months 个月 ─────────────────────────
    all_dates = sorted(set(list(grv_monthly.keys()) + list(fred_monthly.keys())))
    # 只取有 GRV 数据的月份
    valid_dates = [d for d in all_dates if d in grv_monthly][-months:]

    # GRV 3个月移动平均平滑（降低月度±30剧烈波动对校准的冲击）
    _grv_keys = (
        "grv", "grv_energy", "grv_military", "grv_trade", "us_china_grv",
        # D7 扩展维度随主维度一起平滑，保持校准期与预测期输入空间一致
        "climate_risk", "disaster_risk", "sanctions_risk", "seismic_risk",
        "energy_grid_risk", "japan_monetary", "social_stress", "cultural_friction",
    )
    _raw_grv_seq = [grv_monthly[d] for d in valid_dates]
    _smoothed_grv = []
    for i, dt in enumerate(valid_dates):
        window = _raw_grv_seq[max(0, i - 2): i + 1]  # 最多取前2个月+当月=3个月
        smoothed = {}
        for k in _grv_keys:
            vals = [w[k] for w in window if k in w and w[k] is not None]
            smoothed[k] = sum(vals) / len(vals) if vals else grv_monthly[dt].get(k, 50.0)
        _smoothed_grv.append(smoothed)

    result = []
    for i, dt in enumerate(valid_dates):
        grv_d  = _smoothed_grv[i]
        fred_d = fred_monthly.get(dt, {})
        result.append({
            "date":             dt,
            "grv":              grv_d.get("grv", 50.0),
            "grv_energy":       grv_d.get("grv_energy", 0.0),
            "grv_military":     grv_d.get("grv_military", 0.0),
            "grv_trade":        grv_d.get("grv_trade", 0.0),
            "us_china_grv":     grv_d.get("us_china_grv", 50.0),
            "t10y2y":           fred_d.get("t10y2y", -10.0),
            "credit_spread":    fred_d.get("credit_spread", 250.0),
            "dff":              fred_d.get("dff", 5.0),
            "ecb_rate":         fred_d.get("ecb_rate", 3.0),   # D14 fix
            "usd_cny":          fred_d.get("usd_cny", 7.1),    # D14 fix
            # D7 扩展维度（使校准期 MacroWorldState 与预测期输入空间一致）
            "climate_risk":     grv_d.get("climate_risk", 0.0),
            "disaster_risk":    grv_d.get("disaster_risk", 0.0),
            "sanctions_risk":   grv_d.get("sanctions_risk", 0.0),
            "seismic_risk":     grv_d.get("seismic_risk", 0.0),
            "energy_grid_risk": grv_d.get("energy_grid_risk", 0.0),
            "japan_monetary":   grv_d.get("japan_monetary", 0.0),
            "social_stress":    grv_d.get("social_stress", 0.0),
            "cultural_friction":grv_d.get("cultural_friction", 0.0),
        })

    return result


def make_world_from_history_row(row: dict, prev_row: dict = None, label: str = "") -> "MacroWorldState":
    """
    从历史数据一行构建 MacroWorldState。
    prev_row 用于计算 baseline（30天前的值）。
    """
    baseline = prev_row if prev_row else row
    vix = 15.0 + row["grv"] * 0.15

    def _f(val, default=0.0):
        return float(val) if val is not None else default

    return MacroWorldState(
        vix=float(vix),
        vix_baseline=float(15.0 + _f(baseline["grv"], 50) * 0.15),
        grv=_f(row["grv"], 50.0),
        grv_baseline=_f(baseline["grv"], 50.0),
        grv_energy=_f(row["grv_energy"]),
        grv_energy_baseline=_f(baseline["grv_energy"]),
        grv_military=_f(row["grv_military"]),
        grv_trade=_f(row["grv_trade"]),
        us_china_grv=_f(row["us_china_grv"], 50.0),
        t10y2y=_f(row["t10y2y"], -10.0),
        credit_spread=_f(row["credit_spread"], 250.0),
        dff=_f(row["dff"], 5.0),
        # D14 fix: ecb_rate/usd_cny 从历史行读取，不再硬编码（历史无此字段时 fallback）
        ecb_rate=_f(row.get("ecb_rate"), 3.0),
        usd_cny=_f(row.get("usd_cny"), 7.1),
        # D7 扩展维度（历史行有则用，无则安全默认 0.0）
        climate_risk=_f(row.get("climate_risk"), 0.0),
        disaster_risk=_f(row.get("disaster_risk"), 0.0),
        sanctions_risk=_f(row.get("sanctions_risk"), 0.0),
        seismic_risk=_f(row.get("seismic_risk"), 0.0),
        energy_grid_risk=_f(row.get("energy_grid_risk"), 0.0),
        japan_monetary=_f(row.get("japan_monetary"), 0.0),
        social_stress=_f(row.get("social_stress"), 0.0),
        cultural_friction=_f(row.get("cultural_friction"), 0.0),
        # v2.2 D1：历史模式下能对齐的 GRV 维度（russia_europe/taiwan_strait 无法从聚合分离，留 0）
        grv_dimensions={
            "global_composite":     _f(row["grv"], 50.0),
            "middle_east_energy":   _f(row.get("grv_energy"), 0.0),
            "us_china_strategic":   _f(row.get("us_china_grv"), 50.0),
            "sanctions_risk":       _f(row.get("sanctions_risk"), 0.0),
            "energy_grid_risk":     _f(row.get("energy_grid_risk"), 0.0),
            "climate_risk":         _f(row.get("climate_risk"), 0.0),
            "disaster_risk":        _f(row.get("disaster_risk"), 0.0),
            "social_stress":        _f(row.get("social_stress"), 0.0),
            "cultural_friction":    _f(row.get("cultural_friction"), 0.0),
        },
        situation_level=2,
        step_label=label or row.get("date", ""),
        total_cycles=100,
        sim_id=f"hist_{label}",
    )


def load_from_macro_scan(
    grv_path:  str = "/app/macro_data/grv_latest.json",
    fred_path: str = "/app/macro_data/fred_history",
    news_export_path: str = "/app/macro_data/news_export.json",
    situation_level: int = 1,
    label: str = "live",
) -> "MacroWorldState":
    """从当前真实数据加载初始状态（预测循环起点用）"""
    import json, csv, os

    _GRV_SCHEMA  = "1.0"
    _NEWS_SCHEMA = "1.0"

    with open(grv_path) as f:
        grv = json.load(f)
    grv_ver = grv.get("_schema_version")
    if grv_ver != _GRV_SCHEMA:
        raise RuntimeError(f"grv schema 不兼容：期望{_GRV_SCHEMA}，实际{grv_ver!r}")

    grv_composite = grv.get("global_composite", 50.0)
    grv_energy    = grv.get("middle_east_energy", 0.0)
    grv_military  = (grv.get("russia_europe", 0) + grv.get("taiwan_strait", 0)) / 200
    grv_trade     = grv.get("us_china_strategic", 0) / 100
    us_china_grv  = grv.get("us_china_strategic", 50.0)
    # D7: 读取天枢产出的6个额外GRV维度（缺失时安全默认值）
    climate_risk     = float(grv.get("climate_risk") or 0.0)
    disaster_risk    = float(grv.get("disaster_risk") or 0.0)
    sanctions_risk   = float(grv.get("sanctions_risk") or 0.0)
    seismic_risk     = float(grv.get("seismic_risk") or 0.0)
    energy_grid_risk = float(grv.get("energy_grid_risk") or 0.0)
    japan_monetary   = float(grv.get("japan_monetary") or 0.0)
    # R09/R10：social_stress/cultural_friction 现在由 geo_risk_vector 透传到 grv_latest.json
    social_stress    = float(grv.get("social_stress") or 0.0)
    cultural_friction = float(grv.get("cultural_friction") or 0.0)

    def read_latest(filename):
        path = os.path.join(fred_path, filename)
        try:
            with open(path) as f:
                rows = [r for r in csv.DictReader(f) if r["value"] and r["value"] != "."]
            return float(rows[-1]["value"]) if rows else None
        except Exception:
            return None

    def read_baseline(filename, lookback=6):
        path = os.path.join(fred_path, filename)
        try:
            with open(path) as f:
                rows = [r for r in csv.DictReader(f) if r["value"] and r["value"] != "."]
            return float(rows[max(0, len(rows) - lookback * 22)]["value"]) if rows else None
        except Exception:
            return None

    t10y2y_raw    = read_latest("T10Y2Y.csv")
    credit_raw    = read_latest("BAA10Y.csv")
    dff_raw       = read_latest("DFF.csv")
    dexjpus_raw   = read_latest("DEXJPUS.csv")
    dexchus_raw   = read_latest("DEXCHUS.csv")
    ecbdfr_raw    = read_latest("ECBDFR.csv")
    sp500_latest  = read_latest("SP500.csv")
    sp500_6m_ago  = read_baseline("SP500.csv", lookback=6)

    # FRED 存储单位是 %，t10y2y 和 credit_spread 换算成 bps（×100）
    t10y2y        = (t10y2y_raw * 100) if t10y2y_raw is not None else -10.0
    credit_spread = (credit_raw * 100) if credit_raw is not None else 250.0
    dff           = dff_raw if dff_raw is not None else 5.0

    # DEXJPUS → yen_carry_risk，>155 高风险，按 (val-120)/50 归一化到 [0,1]
    yen_carry_risk = 0.0
    if dexjpus_raw is not None:
        yen_carry_risk = max(0.0, min(1.0, (dexjpus_raw - 120.0) / 50.0))

    # DEXCHUS → usd_cny
    usd_cny = dexchus_raw if dexchus_raw is not None else 7.1

    # ECBDFR → ecb_rate（单位直接是 %）
    ecb_rate = ecbdfr_raw if ecbdfr_raw is not None else 3.0

    # SP500 6个月涨跌幅
    sp500_change = 0.0
    if sp500_latest is not None and sp500_6m_ago is not None and sp500_6m_ago != 0:
        sp500_change = (sp500_latest - sp500_6m_ago) / sp500_6m_ago

    grv_hist_path = os.path.join(os.path.dirname(grv_path), "grv_history.jsonl")
    grv_baseline_val = grv_composite
    grv_energy_baseline_val = grv_energy
    try:
        with open(grv_hist_path) as f:
            lines = f.readlines()
        if len(lines) >= 6:
            old = json.loads(lines[-6])
            grv_baseline_val = old.get("global_composite") or grv_composite
            me = old.get("middle_east_energy")
            grv_energy_baseline_val = me if me is not None else grv_energy
    except Exception:
        pass

    vix = 15.0 + grv_composite * 0.15
    vix_baseline = 15.0 + grv_baseline_val * 0.15

    recent_news = []
    trigger_event = ""
    try:
        with open(news_export_path) as f:
            export = json.load(f)
        if export.get("_schema_version") != _NEWS_SCHEMA:
            raise RuntimeError("news schema 不兼容")
        articles = export.get("articles", [])
        recent_news = [a["title"] for a in articles[:5]]
        trigger_event = articles[0]["title"] if articles else ""
    except RuntimeError:
        raise
    except Exception:
        pass

    # 读取 daily_digest.json（macro-scan daily_narrative 写出，仅用当日数据）
    daily_digest_path = os.path.join(os.path.dirname(fred_path), "daily_digest.json")
    try:
        if os.path.exists(daily_digest_path):
            with open(daily_digest_path, encoding="utf-8") as f:
                digest = json.load(f)
            if digest.get("date") == datetime.now().strftime("%Y-%m-%d"):
                recent_news.extend(digest.get("bullets", []))
    except Exception as e:
        print(f"[world_state] daily_digest.json 读取失败（非阻断）: {e}")

    # 从 situations.yaml 读取 escalating 事件，补充 trigger_event 和 recent_news
    situations_path = os.path.join(os.path.dirname(fred_path), "situations.yaml")
    try:
        import yaml
        with open(situations_path) as f:
            sit_data = yaml.safe_load(f)
        escalating = [s for s in sit_data.get("situations", []) if s.get("status") == "escalating"]
        for sit in escalating:
            name = sit.get("name", "")
            signals = sit.get("recent_signals", [])
            first_signal = signals[0] if signals else ""
            if not trigger_event and name:
                trigger_event = name
            if name and first_signal:
                recent_news.append(f"[{name}] {first_signal}")
        recent_news = recent_news[:8]
    except Exception as e:
        print(f"[world_state] situations.yaml 读取失败：{e}")

    # 读取慢变量（slow_variables.json，月频，Sprint-2 注入）
    irp = ucri = gci = 0.0
    slow_var_path = os.path.join(os.path.dirname(fred_path), "slow_variables.json")
    try:
        if os.path.exists(slow_var_path):
            with open(slow_var_path, encoding="utf-8") as f:
                sv = json.load(f)
            irp  = float(sv.get("irp",  0.0) or 0.0)
            ucri = float(sv.get("ucri", 0.0) or 0.0)
            gci  = float(sv.get("gci",  0.0) or 0.0)
    except Exception as e:
        print(f"[world_state] slow_variables.json 读取失败（非阻断）: {e}")

    return MacroWorldState(
        vix=float(vix), vix_baseline=float(vix_baseline),
        grv=float(grv_composite), grv_baseline=float(grv_baseline_val),
        grv_energy=float(grv_energy), grv_energy_baseline=float(grv_energy_baseline_val),
        grv_military=float(grv_military),
        grv_trade=float(grv_trade),
        us_china_grv=float(us_china_grv),
        t10y2y=float(t10y2y),
        credit_spread=float(credit_spread),
        dff=float(dff),
        yen_carry_risk=float(yen_carry_risk),
        usd_cny=float(usd_cny),
        ecb_rate=float(ecb_rate),
        sp500_change=float(sp500_change),
        # v2.2 D1：GRV 全维度原始 0-100 值（soul trigger 直接引用）
        grv_dimensions={
            k: float(v) for k, v in grv.items()
            if isinstance(v, (int, float)) and k != "_schema_version"
        },
        # D7: 6个新GRV维度
        climate_risk=climate_risk,
        disaster_risk=disaster_risk,
        sanctions_risk=sanctions_risk,
        seismic_risk=seismic_risk,
        energy_grid_risk=energy_grid_risk,
        japan_monetary=japan_monetary,
        social_stress=social_stress,
        cultural_friction=cultural_friction,
        # 慢变量（Sprint-2）
        irp=irp, ucri=ucri, gci=gci,
        situation_level=situation_level,
        trigger_event=trigger_event,
        recent_news=recent_news,
        total_cycles=100,
        sim_id=label,
        trigger_date=datetime.now().strftime("%Y-%m-%d"),
        step_label=datetime.now().strftime("%Y-%m"),
    )
