import json, math
EPS_TGT = 0.03
EPS_ACT = 0.005
seeds = [42, 7, 123, 2024, 777]
w = {"market_sentiment": 0.40, "bank_credit_tightening": 0.35, "liquidity_premium": 0.25}
print("=== 1. credit silence 距 0.50 缺口 ===")
for sd in seeds:
    p = json.load(open(f"output/calib_probe_seed{sd}_v2030c.json", encoding="utf-8"))
    n_s = 0
    n_delta = 0
    for r in p["steps"]:
        d = r["per_var"]["bank_credit_tightening"]["d"]
        t = r["per_var"]["bank_credit_tightening"]["t"]
        n_delta += 1
        if abs(t) >= EPS_TGT and abs(d) < EPS_ACT:
            n_s += 1
    print(f"seed{sd}: n_s={n_s}/{n_delta} silence={n_s/n_delta:.3f} 距0.50需减S步={n_s-0.50*n_delta:.1f}")
print("=== 2. credit 入池后合并 p_hat 投影（R4d 实际 consistency）===")
total_N = 0.0
total_K = 0.0
for sd in seeds:
    p = json.load(open(f"output/calib_probe_seed{sd}_v2030c.json", encoding="utf-8"))
    pairs = {v: [] for v in w}
    for r in p["steps"]:
        for v in w:
            d = r["per_var"][v]["d"]
            t = r["per_var"][v]["t"]
            if abs(t) >= EPS_TGT and abs(d) >= EPS_ACT:
                pairs[v].append((d, t))
    for v, pp in pairs.items():
        c = sum(1 for d, t in pp if d * t >= 0) / len(pp) if pp else 0
        total_N += w[v] * len(pp)
        total_K += w[v] * c * len(pp)
p_hat = total_K / total_N
z = 1.96
z2 = z * z
ci = (total_K + z2 / 2) / (total_N + z2) - z / (total_N + z2) * math.sqrt(p_hat * (1 - p_hat) * total_N + z2 / 4)
print(f"p_hat={p_hat:.4f} CI下限={ci:.4f} N={total_N:.1f}")
