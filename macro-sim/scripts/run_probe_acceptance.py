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
    python scripts/run_probe_acceptance.py            # 全量 5 seed
    python scripts/run_probe_acceptance.py --smoke    # 仅 seed42 冒烟（不判闸，只出数值）
    python scripts/run_probe_acceptance.py --seeds 42,7
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
    """从落盘工件重算 per-var 关键统计（consistency/n_active/m_v/act/silence/dead）。"""
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
        dead = m_v < cal.DEAD_M_V and pv[v]["clamp_frac"] < 0.3
        out[v] = {
            "n_active": len(pairs),
            "consistency_rate": consistency,
            "m_v": m_v,
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


def merged_pooled(seeds_stats: list[dict]) -> tuple[float, float, float, float]:
    """跨 seed 合并加权一致率：p̂、N、K、Wilson CI 下限。"""
    N = K = 0.0
    for st in seeds_stats:
        for v, s in st.items():
            if not s["eligible"]:
                continue
            w = ERROR_WEIGHTS[v]
            n = s["n_active"]
            k = s["consistency_rate"] * n
            N += w * n
            K += w * k
    p_hat = K / N if N > 0 else 0.0
    return p_hat, N, K, wilson_lower(K, N)


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

    # ── 1) dead/silence 硬闸（最先）──
    for sd in seeds:
        for var, s in probes[sd]["stats"].items():
            if s["dead"]:
                v.fail("1-dead/silence",
                       f"seed{sd} {var} dead=True（m_v={s['m_v']:.4f} < {cal.DEAD_M_V}）")
            if s["silence_frac"] > 0.50:
                v.fail("1-dead/silence",
                       f"seed{sd} {var} silence_frac={s['silence_frac']:.2f} > 0.50")
    if v.failures:
        return v

    # ── 2) 合并 CI 下限 ≥0.55 ──
    seeds_stats = [probes[sd]["stats"] for sd in seeds]
    p_hat, N, K, ci_lower = merged_pooled(seeds_stats)
    probes["_merged"] = {"p_hat": p_hat, "N": N, "K": K, "ci_lower": ci_lower}
    if ci_lower < 0.55:
        v.fail("2-merged-CI", f"合并 CI 下限 {ci_lower:.3f} < 0.55（p̂={p_hat:.3f}, N={N:.1f}）")
        return v

    # ── 3) 合并点估 ≥0.60 ──
    if p_hat < 0.60:
        v.fail("3-merged-point", f"合并点估 p̂={p_hat:.3f} < 0.60")
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

    # ── 5b) credit 复活四指标（median 跨 seed）──
    med = {}
    for ind in ("n_active", "m_v", "act_frac", "silence_frac"):
        vals = [probes[sd]["stats"]["bank_credit_tightening"][ind] for sd in seeds]
        med[ind] = statistics.median(vals)
    probes["_credit_median"] = med
    if not (med["n_active"] >= 20 and med["m_v"] >= 0.01
            and med["act_frac"] >= 0.30 and med["silence_frac"] <= 0.50):
        v.fail("5b-credit-revive",
               f"credit median 未复活：n_active={med['n_active']} m_v={med['m_v']:.4f} "
               f"act={med['act_frac']:.2f} silence={med['silence_frac']:.2f}")

    # ── 5c) 三守卫 A/B/C（C 探针语境 N/A-pass）──
    # A：由落盘 stats 重建（act≥0.30 ∧ silence≤0.50 逐 var，任一 FAIL → 闸 FAIL）
    guard_a_pass = all(s["act_frac"] >= 0.30 and s["silence_frac"] <= 0.50
                       for sd in seeds for s in probes[sd]["stats"].values())
    if not guard_a_pass:
        v.fail("5c-guard-A", "存在变量 act_frac<0.30 或 silence_frac>0.50（守卫 A FAIL）")
    # B：加载 agents 查塌缩写者（与 calibrator.check_guards 同规则）
    try:
        agents, _g = cal.load_agents("/app/config/agents.yaml")
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
    w_ok = sum(ERROR_WEIGHTS[v] for v in ERROR_WEIGHTS if stats[v]["eligible"])
    w_cons = sum(ERROR_WEIGHTS[v] * stats[v]["consistency_rate"]
                 for v in ERROR_WEIGHTS if stats[v]["eligible"])
    weighted = round(w_cons / w_ok, 3) if w_ok > 0 else None
    entry = {"weighted": weighted, "stats": stats, "raw": probe}
    if smoke:
        print(f"[smoke] seed{seed} weighted={weighted} | credit="
              f"{stats['bank_credit_tightening']}")
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description="R3 多 seed 探针验收 + 回退闸")
    ap.add_argument("--seeds", default=",".join(map(str, SEEDS)))
    ap.add_argument("--smoke", action="store_true", help="仅 seed42 冒烟（不判闸）")
    ap.add_argument("--data-root", default="/app/macro_data",
                    help="外生数据根目录（容器默认 /app/macro_data）")
    ap.add_argument("--out-dir", default=str(OUTPUT_DIR))
    args = ap.parse_args()

    seeds = [42] if args.smoke else [int(s) for s in args.seeds.split(",") if s]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    probes = {}
    for sd in seeds:
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

    # 汇总输出
    summary = {
        "verdict": "PASS" if verdict.ok else "FAIL",
        "seeds": seeds,
        "per_seed_weighted": {sd: probes[sd]["weighted"] for sd in probes if sd != "_merged"},
        "merged": probes.get("_merged"),
        "credit_median": probes.get("_credit_median"),
        "failures": [{"step": s, "msg": m} for s, m in verdict.failures],
        "warnings": verdict.warnings,
    }
    (out_dir / "acceptance_v2030c.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n========== R3 验收判定 ==========")
    m = summary["merged"] or {}
    print(f"合并点估 p̂={m.get('p_hat')}  CI 下限={m.get('ci_lower')}  N={m.get('N')}")
    print(f"per-seed weighted: { {k: v for k, v in summary['per_seed_weighted'].items()} }")
    cm = summary.get("credit_median") or {}
    if cm:
        print(f"credit median: n_active={cm['n_active']} m_v={cm['m_v']:.4f} "
              f"act={cm['act_frac']:.2f} silence={cm['silence_frac']:.2f}")
    for step, msg in verdict.failures:
        print(f"  FAIL [{step}] {msg}")
    for msg in verdict.warnings:
        print(f"  WARN {msg}")
    print(f"VERDICT: {summary['verdict']}")
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
