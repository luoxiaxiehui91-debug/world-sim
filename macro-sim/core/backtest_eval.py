#!/usr/bin/env python3
"""
backtest_eval.py — 天璇推演验证标尺（蓝图 v3 阶段 0 交付物，ADR-0012a）

用法：
  python3 backtest_eval.py --sim /app/reports/xxx_sim_history.jsonl \
      --hist-months 50 --label "事件名" [--engine soul|llm] [--save-baseline]

指标定义（预注册锁定，蓝图 v3 阶段 0）：
  1. GRV 轨迹相似度：一阶差分 Pearson 相关，窗口=全预测期
  2. 方向命中率：月度 Δgrv ±0.5 分带（升/降/平）
  3. 波动率匹配：模拟 std ÷ 历史 std ∈ [0.5, 2.0]
  4. 关键月份偏差表：|Δ真实grv| 前 3
  5. 基线存档：gate_baseline.json
输出：一页纸 markdown 报告 + 基线 JSON。
"""
import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/app")
from core.world_state import load_monthly_history

DIR_BAND = 0.5
NL = chr(10)


def direction(delta):
    return "升" if delta > DIR_BAND else ("降" if delta < -DIR_BAND else "平")


def pearson(a, b):
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da > 0 and db > 0 else float("nan")


def load_sim(path):
    out = []
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln or ln.startswith("__meta__:"):
            continue
        d = json.loads(ln)
        out.append({"grv": d.get("grv")})
    return out


def evaluate(sim_g, real_hist, start_idx, label, engine):
    n = min(len(sim_g), len(real_hist) - start_idx)
    sg = [s["grv"] for s in sim_g[:n]]
    rg = [r["grv"] for r in real_hist[start_idx:start_idx + n]]

    sd = [sg[i + 1] - sg[i] for i in range(n - 1)]
    rd = [rg[i + 1] - rg[i] for i in range(n - 1)]
    corr = pearson(sd, rd)

    hits, rows, prev_s, prev_r = 0, [], sg[0], rg[0]
    for j in range(1, n):
        ps, pr = direction(sg[j] - prev_s), direction(rg[j] - prev_r)
        hit = ps == pr
        hits += hit
        rows.append({"month": real_hist[start_idx + j].get("date", "+" + str(j)),
                     "pred": ps, "real": pr, "hit": bool(hit)})
        prev_s, prev_r = sg[j], rg[j]
    rate = hits / max(len(rows), 1)

    def std(x):
        m = sum(x) / len(x)
        return (sum((v - m) ** 2 for v in x) / max(len(x) - 1, 1)) ** 0.5

    vol_ratio = round(std(sd) / std(rd), 3) if std(rd) > 0 else float("inf")

    key_rows = sorted(range(len(rows)),
                      key=lambda i: abs(rg[i + 1] - rg[i]), reverse=True)[:3]
    key_rows = [rows[i] for i in sorted(key_rows)]

    return {"label": label, "engine": engine, "months": n,
            "corr": round(corr, 3), "hits": hits, "dir_total": len(rows),
            "dir_rate": round(rate, 3), "vol_ratio": vol_ratio,
            "vol_pass": bool(0.5 <= vol_ratio <= 2.0),
            "key_months": key_rows, "dir_detail": rows}


def one_pager(res, baseline=None):
    L = ["# 推演验证标尺报告 · " + res["label"], "",
         "引擎：" + res["engine"] + "　窗口：" + str(res["months"]) + " 个月　生成：" +
         datetime.now().strftime("%Y-%m-%d %H:%M"), "",
         "## 核心指标",
         "- GRV 差分相关系数：**" + str(res["corr"]) + "**",
         "- 方向命中率：**" + str(res["hits"]) + "/" + str(res["dir_total"]) +
         " = " + format(res["dir_rate"], ".0%") + "**（随机基线 33%）",
         "- 波动率比值：**" + str(res["vol_ratio"]) + "**（通过带 0.5~2.0）",
         "", "## 关键月份偏差", "| 月份 | 预测 | 现实 | 命中 |", "|---|---|---|---|"]
    for r in res["key_months"]:
        L.append("| %s | %s | %s | %s |" % (
            r["month"], r["pred"], r["real"], "✓" if r["hit"] else "✗"))
    if baseline:
        L += ["", "## 与裸推基线对比",
              "| 指标 | 基线 | 本次 |", "|---|---|---|"]
        for k, name in [("corr", "差分相关"), ("dir_rate", "方向命中率"), ("vol_ratio", "波动率比")]:
            L.append("| %s | %s | %s |" % (name, baseline.get(k), res.get(k)))
    return NL.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", required=True)
    ap.add_argument("--start-idx", type=int, default=None)
    ap.add_argument("--hist-months", type=int, default=50)
    ap.add_argument("--label", default="未命名推演")
    ap.add_argument("--engine", default="unknown")
    ap.add_argument("--out", default="/app/reports")
    ap.add_argument("--save-baseline", action="store_true")
    a = ap.parse_args()

    real = load_monthly_history(months=a.hist_months)
    sim = load_sim(a.sim)
    start = a.start_idx if a.start_idx is not None else len(real) - len(sim)

    res = evaluate(sim, real, max(start, 1), a.label, a.engine)

    bl_path = Path(a.out) / "gate_baseline.json"
    bl_path.parent.mkdir(parents=True, exist_ok=True)
    baseline = None
    if a.save_baseline or not bl_path.exists():
        bl_path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        baseline = json.loads(bl_path.read_text(encoding="utf-8"))

    report = one_pager(res, baseline)
    rp = Path(a.out) / (datetime.now().strftime("%Y%m%d_%H%M") + "_标尺_" + a.label + ".md")
    rp.write_text(report, encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("corr", "hits", "dir_rate", "vol_ratio", "vol_pass")},
                     ensure_ascii=False))
    print("report:", rp)


if __name__ == "__main__":
    main()
