#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R3 验收脚本（qa-r2b 定稿，三合一）：多 seed 探针 + 机读判定 + 回退闸。

铁律
----
- 验收证据只用新探针多 seed median（禁 calibration_cache；禁 CHANGELOG 散文作判定输入）
- 判定只读落盘工件：output/calib_probe_seed{seed}_v2030c.json + output/baseline_v2030b.json
- fail-fast：任何一步 FAIL → 整体 FAIL，输出 p̂/CI/违规变量名/seed

判定顺序
--------
1) dead/silence 硬闸：任一变量 dead=True 或 silence_frac>0.50 → FAIL（最先）
2) 合并 CI 下限：跨 5 seed 合并加权一致率（eligible 变量，权重 0.40/0.35/0.25）
   Wilson 95% CI 下限 ≥0.55
3) 合并点估：p̂ ≥0.60
4) per-seed：全部 5 seed 各自加权一致率 ≥0.50
5) 其余项（全 pass）：
   a) per-var grv↑/↓ 两桶均≥0.60（eligible 变量；桶 n≥5 才判定，<5 记 skip+warn）
   b) credit 复活四指标（median 跨 seed）：n_active≥20 ∧ m_v≥0.01 ∧ act≥0.30 ∧ silence≤0.50
   c) 三守卫 A/B/C 全 pass（A/B 由探针落盘重建；C 在探针语境=禁调参，记 N/A-pass）
   d) EASE gate=='PASS'（逐 seed）
   e) 回退闸：seed 42/7/123 weighted ≥ baseline−0.10
   f) rho(sim,target) 与离线 rho(target,driver) 方向一致（|offline|>0.05 才判）

运行
----
容器内（数据在 /app/macro_data）：
    python scripts/run_probe_acceptance.py            # 全量 5 seed（跑探针 + 判定）
    python scripts/run_probe_acceptance.py --smoke    # 仅 seed42 冒烟（不判闸，只出数值）
    python scripts/run_probe_acceptance.py --seeds 42,7
    python scripts/run_probe_acceptance.py --read-only  # 只读已落盘工件判定（不重跑，防覆盖）

R4a 说明
--------
- weighted 直接复用探针落盘权威精确值 weighted_consistency_exact（未舍入 consistency，
  round 仅展示；R4a 复核点 1 锁定单一权威路径，消除 0.001/0.003 双口径差）
- merged 输出显式标注 eligible 池与 N（加权有效样本量，非名义配对总数）
- rho 窗口 target 零膨胀字段：per_var target_nonzero_frac + target_sd（data-r2 判别）
- --read-only 只读判定模式：防随机重跑覆盖工件
- 硬闸短路也输出 merged/credit_median（FAIL 也带证据）
- 汇总落盘 per-var/per-seed n_active（data-r2：CI 精确化、seed 级 cluster 校正前提）

R4c 说明（dead 语义修正，qa-r2b+data-r2 双会签）
---------------------------------------------
- dead 新语义 = act_frac<0.10 OR m_v_active<0.002（m_v_active=行动步 median|d|）——credit
  act 0.388 / m_v_active 0.335 → dead=False（旧 m_v 全步 median 把部分活跃误判真死）
- 两层口径：闸②③合并 = per-var 跨 seed 合计 n_active≥20（merged_eligible，credit 5 seed
  合计 93 入池）；闸④ per-seed = per-seed n_active≥20（per_seed_weighted，era-independent）
- 5b credit 复活 m_v 统一 m_v_active 口径
- act∈[0.10,0.30)=insufficient 语义文档化（非死但活性不足：guard A FAIL + p̂ 稀释偏 FAIL）
"""

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.calibrator as cal  # noqa: E402

ERROR_WEIGHTS = cal.ERROR_WEIGHTS
SEEDS = [42, 7, 123, 2024, 777]
ARTIFACT_TAG = "v2030c"
OUTPUT_DIR = ROOT / "output"
BASELINE_PATH = OUTPUT_DIR / "baseline_v2030b.json"
Z95 = 1.96

# 回退闸基线（weighted 来源 baseline_v2030b.json，启动时读取，禁止硬编码进判定）
ROLLBACK_SEEDS = [42, 7, 123]


# ── 工具 ─────────────────────────────────────────────────

def wilson_lower(k: float, n: float, z: float = Z95) -> float:
    """Wilson score 区间下界（k/n 为加权计数比例）。"""
    if n <= 0:
        return 0.0
    p = k / n
    z2 = z * z
    center = (k + z2 / 2.0) / (n + z2)
    margin = z / (n + z2) * math.sqrt(p * (1 - p) * n + z2 / 4.0)
    return center - margin


def pearson(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    ma, mb = statistics.mean(a[:n]), statistics.mean(b[:n])
    num = sum((x - ma) * (y - mb) for x, y in zip(a[:n], b[:n]))
    da = sum((x - ma) ** 2 for x in a[:n]) ** 0.5
    db = sum((y - mb) ** 2 for y in b[:n]) ** 0.5
    return num / (da * db) if da and db else 0.0


def rebuild_samples(probe: dict) -> dict:
    """从落盘 steps 重建 T 类 (d,t) 元组 + 全步 (d,t) 样本（判定口径=落盘工件）。"""
    steps = probe.get("steps", [])
    t_pairs = {v: [] for v in ERROR_WEIGHTS}   # (d, t) 仅 T 类
    all_pairs = {v: [] for v in ERROR_WEIGHTS}  # (d, t) 全部
    for rec in steps:
        for v in ERROR_WEIGHTS:
            d = rec["per_var"][v]["d"]
            t = rec["per_var"][v]["t"]
            all_pairs[v].append((d, t))
            if cal._step_eligibility(d, t) == "T":
                t_pairs[v].append((d, t))
    return {"t": t_pairs, "all": all_pairs}


def var_stats(probe: dict, samples: dict) -> dict:
    """从落盘工件重算 per-var 关键统计（consistency/n_active/m_v/m_v_active/act/silence/dead）。
    R4c：dead 改新语义 = act_frac<0.10 OR m_v_active<0.002（m_v_active=median|d| over 行动步），
    与 calibrator.py 同口径；m_v（全步 median）仅作参考。"""
    pv = probe["per_var"]
    out = {}
    for v in ERROR_WEIGHTS:
        pairs = samples["t"][v]
        allp = samples["all"][v]
        ds = [d for d, _t in allp]
        tgts = [t for _d, t in allp]
        n_delta = len(ds) or 1
        consistency = (sum(1 for d, t in pairs if d * t >= 0) / len(pairs)) if pairs else 0.0
        silence = sum(1 for d, t in allp if abs(t) >= cal.EPS_TGT and abs(d) < cal.EPS_ACT) / n_delta
        act = len(pairs) / n_delta
        m_v = statistics.median([abs(d) for d in ds]) if ds else 0.0
        act_ds = [d for d in ds if abs(d) > 0]
        m_v_active = statistics.median([abs(d) for d in act_ds]) if act_ds else 0.0
        dead = (act < 0.10) or (m_v_active < cal.DEAD_M_V)
        out[v] = {
            "n_active": len(pairs),
            "consistency_rate": consistency,
            "m_v": m_v,
            "m_v_active": m_v_active,
            "act_frac": act,
            "silence_frac": silence,
            "dead": dead,
            "eligible": cal._eligible_for_weighted({
                "sufficient": len(pairs) >= cal.MIN_N_ACTIVE,
                "dead": dead,
                "silence_frac": silence,
            }),
        }
    return out


def merged_eligible(stats_list: list[dict], var: str) -> bool:
    """R4c 合并口径（闸②③）：per-var 跨 seed 合计 n_active≥20 ∧ median dead=False ∧
    median silence≤0.50。credit R4b 5 seed 合计 93（21+18+16+19+19）≥20 → 入合并池，
    即使部分 seed 单 seed n_active<20（单 seed 活性不足由闸④ per-seed 口径单独表达）。"""
    total_n = sum(s[var]["n_active"] for s in stats_list)
    med_dead = statistics.median([1 if s[var]["dead"] else 0 for s in stats_list]) == 0
    med_sil = statistics.median([s[var]["silence_frac"] for s in stats_list])
    return total_n >= 20 and med_dead and med_sil <= 0.50


def merged_pooled(seeds_stats: list[dict]) -> tuple[float, float, float, float, list]:
    """跨 seed 合并加权一致率：p̂、N、K、Wilson CI 下限 + eligible 池（变量清单）。
    R4c 两层口径：合并（闸②③）用 merged_eligible（跨 seed 合计 n_active≥20，credit 入池）；
    单 seed 活性不足（per-seed n_active<20）由闸④ per-seed 口径表达——两层互不替代。
    N 是加权有效样本量（Σ w_v×n_vs），非名义配对总数——CI 宽度据此解读，防误读。
    R4a-2：consistency 取自 var_stats（落盘 steps 重算未舍入），与 consistency_rate_exact 同值。"""
    N = K = 0.0
    pool: list[str] = []
    for v in ERROR_WEIGHTS:
        if not merged_eligible(seeds_stats, v):
            continue
        pool.append(v)
        w = ERROR_WEIGHTS[v]
        for st in seeds_stats:
            n = st[v]["n_active"]
            k = st[v]["consistency_rate"] * n
            N += w * n
            K += w * k
    p_hat = K / N if N > 0 else 0.0
    return p_hat, N, K, wilson_lower(K, N), pool


def offline_rho_target_driver(probe: dict) -> dict:
    """离线 rho(target, driver)——target 是外生确定性函数，从落盘 steps 复算。
    driver：sentiment→grv_delta / credit→cs_delta / liquidity→cs_delta+t10y2y_delta。"""
    steps = probe.get("steps", [])
    res = {}
    for v in ERROR_WEIGHTS:
        ts = [rec["per_var"][v]["t"] for rec in steps]
        if v == "market_sentiment":
            drv = [rec["grv_delta"] for rec in steps]
        elif v == "bank_credit_tightening":
            drv = [rec["cs_delta"] for rec in steps]
        else:
            drv = [rec["cs_delta"] + rec["t10y2y_delta"] for rec in steps]
        res[v] = pearson(ts, drv)
    return res


# ── 判定器 ───────────────────────────────────────────────

class Verdict:
    def __init__(self):
        self.failures = []   # (step_label, message)
        self.warnings = []

    def fail(self, label: str, msg: str):
        self.failures.append((label, msg))

    def warn(self, msg: str):
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.failures


def evaluate(probes: dict, baseline: dict) -> Verdict:
    v = Verdict()
    seeds = list(probes.keys())
    seeds_stats = [probes[sd]["stats"] for sd in seeds]

    # R4a（qa-r2b advisory ②）：merged/credit_median 无条件先算——硬闸 FAIL 也带证据，
    # 避免 FAIL 时连"离达标差多少"都不知道。eligible 池与 N 显式标注（N 是加权有效样本量）。
    p_hat, N, K, ci_lower, pool = merged_pooled(seeds_stats)
    probes["_merged"] = {
        "p_hat": p_hat, "N": N, "K": K, "ci_lower": ci_lower,
        "eligible_pool": pool,
        "pool_note": f"eligible 池={pool or '空'}；N={N:.1f} 为加权有效样本量（Σw×n_active），非名义配对总数",
    }
    med = {}
    for ind in ("n_active", "m_v_active", "act_frac", "silence_frac"):
        vals = [probes[sd]["stats"]["bank_credit_tightening"][ind] for sd in seeds]
        med[ind] = statistics.median(vals)
    # R4c：act∈[0.10,0.30) 语义文档化——非死但活性不足：guard A（act≥0.30）FAIL +
    # 稀释 p̂（大量零 intent 步拉低 active 样本占比）保守偏 FAIL；由二者共同表达，不设独立闸。
    probes["_credit_median"] = med
    probes["_activity_semantics"] = (
        "act∈[0.10,0.30)=insufficient（非死但活性不足）：guard A act≥0.30 FAIL + 零 intent 步"
        "稀释 active 样本 → p̂ 保守偏 FAIL；act<0.10=dead。credit R4b median act=0.388 ∈ adequate。"
    )

    # ── 1) dead/silence 硬闸（最先；R4c dead 新语义 = act_frac<0.10 OR m_v_active<0.002）──
    for sd in seeds:
        for var, s in probes[sd]["stats"].items():
            if s["dead"]:
                v.fail("1-dead/silence",
                       f"seed{sd} {var} dead=True（act_frac={s['act_frac']:.3f} 或 "
                       f"m_v_active={s['m_v_active']:.4f} < {cal.DEAD_M_V}）")
            if s["silence_frac"] > 0.50:
                v.fail("1-dead/silence",
                       f"seed{sd} {var} silence_frac={s['silence_frac']:.2f} > 0.50")
    if v.failures:
        return v

    # ── 2) 合并 CI 下限 ≥0.55 ──
    if ci_lower < 0.55:
        v.fail("2-merged-CI", f"合并 CI 下限 {ci_lower:.3f} < 0.55（p̂={p_hat:.3f}, N={N:.1f}, eligible 池={pool}）")
        return v

    # ── 3) 合并点估 ≥0.60 ──
    if p_hat < 0.60:
        v.fail("3-merged-point", f"合并点估 p̂={p_hat:.3f} < 0.60（N={N:.1f}）")
        return v

    # ── 4) per-seed ≥0.50 ──
    for sd in seeds:
        if probes[sd]["weighted"] < 0.50:
            v.fail("4-per-seed", f"seed{sd} weighted={probes[sd]['weighted']:.3f} < 0.50")
    if v.failures:
        return v

    # ── 5a) per-var grv↑/↓ 两桶均≥0.60（eligible 变量，桶 n≥5）──
    for sd in seeds:
        for var, s in probes[sd]["stats"].items():
            if not s["eligible"]:
                continue
            pv = probes[sd]["raw"]["per_var"][var]
            for bucket, val, n in (("grv_up", pv["consistency_grv_up"], pv["n_grv_up"]),
                                   ("grv_down", pv["consistency_grv_down"], pv["n_grv_down"])):
                if val is None or n < 5:
                    if val is not None:
                        v.warn(f"seed{sd} {var} {bucket} 样本 n={n}<5，跳过判定")
                    continue
                if val < 0.60:
                    v.fail("5a-grv-bucket",
                           f"seed{sd} {var} {bucket} consistency={val:.3f} < 0.60（n={n}）")
    if v.failures:
        return v

    # ── 5b) credit 复活四指标（median 跨 seed；m_v_active 口径，R4c 统一；顶部已预计算）──
    med = probes["_credit_median"]
    if not (med["n_active"] >= 20 and med["m_v_active"] >= 0.01
            and med["act_frac"] >= 0.30 and med["silence_frac"] <= 0.50):
        v.fail("5b-credit-revive",
               f"credit median 未复活：n_active={med['n_active']} m_v_active={med['m_v_active']:.4f} "
               f"act={med['act_frac']:.2f} silence={med['silence_frac']:.2f}")

    # ── 5c) 三守卫 A/B/C（C 探针语境 N/A-pass）──
    # A：由落盘 stats 重建（act≥0.30 ∧ silence≤0.50 逐 var，任一 FAIL → 闸 FAIL）
    guard_a_pass = all(s["act_frac"] >= 0.30 and s["silence_frac"] <= 0.50
                       for sd in seeds for s in probes[sd]["stats"].values())
    if not guard_a_pass:
        v.fail("5c-guard-A", "存在变量 act_frac<0.30 或 silence_frac>0.50（守卫 A FAIL）")
    # B：加载 agents 查塌缩写者（与 calibrator.check_guards 同规则）
    try:
        _cfg = "/app/config/agents.yaml"
        if not Path(_cfg).exists():
            _cfg = str(ROOT / "config" / "agents.yaml")
        agents, _g = cal.load_agents(_cfg)
        writer_aids = sorted({aid for aids in cal.ERROR_VAR_WRITERS.values() for aid in aids})
        collapsed = [aid for aid in writer_aids
                     if aid in agents and getattr(agents[aid].params, "sensitivity", 1.0) <= 0.10
                     and getattr(agents[aid].params, "magnitude", 1.0) <= 0.10]
        if len(collapsed) >= 2:
            v.fail("5c-guard-B", f"写者参数塌缩 ≥2：{collapsed}")
    except Exception as e:
        v.warn(f"守卫 B 检查跳过：{e}")

    # ── 5d) EASE gate=='PASS'（逐 seed）──
    for sd in seeds:
        gate = probes[sd]["raw"].get("ease_probe", {}).get("gate")
        if gate != "PASS":
            v.fail("5d-ease", f"seed{sd} EASE gate={gate} ≠ PASS")

    # ── 5e) 回退闸：seed42/7/123 weighted ≥ baseline−0.10 ──
    floors = baseline.get("rollback_floor", {})
    for sd in ROLLBACK_SEEDS:
        floor = floors.get(str(sd))
        if floor is None:
            v.warn(f"回退闸缺 seed{sd} 基线 floor，跳过")
            continue
        if probes[str(sd)]["weighted"] < floor:
            v.fail("5e-rollback",
                   f"seed{sd} weighted={probes[str(sd)]['weighted']:.3f} < 基线-0.10={floor:.3f}")

    # ── 5f) rho(sim,target) 与离线 rho(target,driver) 方向一致 ──
    for sd in seeds:
        offline = offline_rho_target_driver(probes[sd]["raw"])
        sim = probes[sd]["raw"].get("rho_sim_target", {})
        for var in ERROR_WEIGHTS:
            r_off = offline.get(var, 0.0)
            r_sim = sim.get(var, 0.0)
            if abs(r_off) < 0.05:
                continue
            if r_sim * r_off < 0:
                v.fail("5f-rho-sign",
                       f"seed{sd} {var} rho_sim_target={r_sim:.3f} 与离线 rho(target,driver)={r_off:.3f} 方向相反")

    return v


# ── 主流程 ───────────────────────────────────────────────

def per_seed_weighted(stats: dict) -> float:
    """R4c 闸④ per-seed 口径：per-seed eligible（n_active≥20 ∧ ¬dead ∧ silence≤0.50）的
    加权一致率，用 steps 重算未舍入 consistency——与探针 weighted_consistency_exact 同公式，
    但适用当前 dead 语义（旧工件探针 dead 若过期，此重算保证 era-independent）。"""
    w_ok = sum(ERROR_WEIGHTS[v] for v in ERROR_WEIGHTS if stats[v]["eligible"])
    w_cons = sum(ERROR_WEIGHTS[v] * stats[v]["consistency_rate"]
                 for v in ERROR_WEIGHTS if stats[v]["eligible"])
    return round(w_cons / w_ok, 6) if w_ok > 0 else None


def run_one_seed(seed: int, data_root: str, out_dir: Path, smoke: bool = False) -> dict:
    """跑单 seed 探针并落盘 artifacts（判定只读落盘工件）。"""
    grv_path = f"{data_root}/grv_history.jsonl"
    fred_path = f"{data_root}/fred_history"
    # 探针默认写 /app/data/calib_probe.json——验收按 seed 落盘到 output，避免互相覆盖
    cal.PROBE_PATH = out_dir / f"calib_probe_seed{seed}_{ARTIFACT_TAG}.json"
    probe = cal.run_probe(grv_path=grv_path, fred_path=fred_path,
                          probe_steps=50, config_path=f"{data_root}/../config/agents.yaml",
                          seed=seed)
    # 主探针内部已写 PROBE_PATH；此处确保 artifact 落盘（含 steps）
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"calib_probe_seed{seed}_{ARTIFACT_TAG}.json").write_text(
        json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    samples = rebuild_samples(probe)
    stats = var_stats(probe, samples)
    # R4c：闸④ per-seed weighted 由 stats（steps 重算 + 当前 dead 语义）计算，era-independent；
    # 与探针落盘 weighted_consistency_exact 同公式（新工件下数值一致），单一权威精确路径。
    weighted = per_seed_weighted(stats)
    entry = {"weighted": weighted, "stats": stats, "raw": probe}
    if smoke:
        print(f"[smoke] seed{seed} weighted={weighted} | credit="
              f"{stats['bank_credit_tightening']}")
    return entry


def load_one_seed(seed: int, out_dir: Path, smoke: bool = False) -> dict:
    """R4a（--read-only）：只读已落盘工件做判定，不重跑 run_probe（防随机重跑覆盖工件）。"""
    path = out_dir / f"calib_probe_seed{seed}_{ARTIFACT_TAG}.json"
    if not path.exists():
        raise FileNotFoundError(f"缺失工件 {path}——--read-only 模式需先跑过全量/该 seed 探针")
    probe = json.loads(path.read_text(encoding="utf-8"))
    samples = rebuild_samples(probe)
    stats = var_stats(probe, samples)
    weighted = per_seed_weighted(stats)
    entry = {"weighted": weighted, "stats": stats, "raw": probe}
    if smoke:
        print(f"[read-only] seed{seed} weighted={weighted} | credit="
              f"{stats['bank_credit_tightening']}")
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description="R3/R4a 多 seed 探针验收 + 回退闸")
    ap.add_argument("--seeds", default=",".join(map(str, SEEDS)))
    ap.add_argument("--smoke", action="store_true", help="仅 seed42 冒烟（不判闸）")
    ap.add_argument("--data-root", default="/app/macro_data",
                    help="外生数据根目录（容器默认 /app/macro_data）")
    ap.add_argument("--out-dir", default=str(OUTPUT_DIR))
    ap.add_argument("--read-only", action="store_true",
                    help="只读已落盘工件做判定，不重跑 run_probe（防随机重跑覆盖工件）")
    args = ap.parse_args()

    seeds = [42] if args.smoke else [int(s) for s in args.seeds.split(",") if s]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    probes = {}
    for sd in seeds:
        if args.read_only:
            probes[str(sd)] = load_one_seed(sd, out_dir, smoke=args.smoke)
        else:
            probes[str(sd)] = run_one_seed(sd, args.data_root, out_dir, smoke=args.smoke)
        print(f"[acceptance] seed{sd} 完成 weighted={probes[str(sd)]['weighted']}")

    if args.smoke:
        print("\n[smoke] 冒烟完成（未判闸，仅验证脚本可跑 + 落盘工件可读）")
        return 0

    baseline = {}
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    else:
        print(f"[acceptance] WARN 未找到 {BASELINE_PATH}——回退闸 5e 将跳过")

    verdict = evaluate(probes, baseline)

    # R4a（data-r2）：per-var/per-seed n_active 落盘（CI 精确化、seed 级 cluster 校正前提）
    n_active_table = {}
    for sd in seeds:
        n_active_table[str(sd)] = {v: probes[str(sd)]["stats"][v]["n_active"]
                                   for v in ERROR_WEIGHTS}
    # R4a（data-r2 零膨胀判别）：rho 窗口 target 非零比例 + target SD（从落盘 per_var 读；
    # 旧工件（R3 期）无此字段 → .get 兜底 None，防 --read-only 对混合代工件崩溃）
    rho_target_stats = {}
    for sd in seeds:
        pv = probes[str(sd)]["raw"].get("per_var", {})
        rho_target_stats[str(sd)] = {
            v: {"target_nonzero_frac": pv.get(v, {}).get("target_nonzero_frac"),
                "target_sd": pv.get(v, {}).get("target_sd")}
            for v in ERROR_WEIGHTS
        }

    # R4a：S 类 why-no-action 归因（credit 决策路径，R4b info_delay 决策用）落盘+打印
    s_class_table = {}
    for sd in seeds:
        s_class_table[str(sd)] = {
            v: probes[str(sd)]["raw"].get("per_var", {}).get(v, {}).get("s_class_attribution")
            for v in ERROR_WEIGHTS
        }

    # 汇总输出
    summary = {
        "verdict": "PASS" if verdict.ok else "FAIL",
        "seeds": seeds,
        "mode": "read-only" if args.read_only else "probe",
        "per_seed_weighted": {str(sd): probes[str(sd)]["weighted"] for sd in seeds},
        "n_active_table": n_active_table,
        "rho_target_stats": rho_target_stats,
        "s_class_table": s_class_table,
        "merged": probes.get("_merged"),
        "credit_median": probes.get("_credit_median"),
        "failures": [{"step": s, "msg": m} for s, m in verdict.failures],
        "warnings": verdict.warnings,
    }
    (out_dir / "acceptance_v2030c.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n========== R3/R4a 验收判定 ==========")
    m = summary["merged"] or {}
    print(f"合并点估 p̂={m.get('p_hat')}  CI 下限={m.get('ci_lower')}  "
          f"N={m.get('N')}  eligible 池={m.get('eligible_pool')}")
    print(f"per-seed weighted: { {k: v for k, v in summary['per_seed_weighted'].items()} }")
    print(f"n_active table: {n_active_table}")
    for sd, rts in (rho_target_stats or {}).items():
        print(f"rho target 零膨胀 (seed{sd}): "
              + ", ".join(f"{v}: nonz={rts[v]['target_nonzero_frac']} sd={rts[v]['target_sd']}"
                          for v in ERROR_WEIGHTS))
    cm = summary.get("credit_median") or {}
    if cm:
        print(f"credit median: n_active={cm['n_active']} m_v_active={cm['m_v_active']:.4f} "
              f"act={cm['act_frac']:.2f} silence={cm['silence_frac']:.2f}")
    if probes.get("_activity_semantics"):
        print(f"[语义] {probes['_activity_semantics']}")
    for sd, tbl in (s_class_table or {}).items():
        ca = (tbl or {}).get("bank_credit_tightening") or {}
        if ca.get("n_s"):
            print(f"credit S 类归因 (seed{sd}): activation_gate={ca.get('activation_gate')} "
                  f"rate_limit={ca.get('rate_limit')} tighten_signal_false={ca.get('tighten_signal_false')} "
                  f"n_s={ca.get('n_s')}")
    for step, msg in verdict.failures:
        print(f"  FAIL [{step}] {msg}")
    for msg in verdict.warnings:
        print(f"  WARN {msg}")
    print(f"VERDICT: {summary['verdict']}")
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
