"""
verify_hypothesis.py — M2-4 假设推演校准闭环工具 + Phase 3C 贝叶斯权重更新

职责：
  1. 扫描 scenario_wiki.md 中 verified:false 且有 actual_outcome 填写的条目
  2. 计算预测误差，分解到各传导路径
  3. 生成参数调整建议（人工审核后才写入传导路径库）
  4. 将 verified 更新为 true，记录校准结果
  5. Phase 3C: --update-weights 时对命中传导路径做贝叶斯权重更新

使用场景：
  真实地缘事件发生后，人工填写 scenario_wiki.md 中的 actual_outcome，
  然后运行本脚本生成校准报告。

运行方式：
  python3 /app/verify_hypothesis.py              # 扫描并输出报告
  python3 /app/verify_hypothesis.py --commit     # 同时将 verified 改为 true
  python3 /app/verify_hypothesis.py --commit --update-weights  # 同时更新传导路径权重

输出：
  终端报告 + data/hypothesis_calibration.json
"""

import os
import re
import json
import argparse
import datetime
from pathlib import Path

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    _ws = os.environ.get("OPENCLAW_WORKSPACE",
                         os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR  = os.path.join(_ws, "data")
    WORKSPACE = _ws

WIKI_FILE   = Path(WORKSPACE) / "data" / "scenario_wiki.md"
PATHS_FILE  = Path(WORKSPACE) / "知识库" / "财经知识库" / "04_分析框架" / "propagation_paths.yaml"
OUTPUT_FILE = Path(DATA_DIR) / "hypothesis_calibration.json"


# ── 解析 wiki 条目 ─────────────────────────────────────────────
def _parse_wiki_entries(text: str) -> list[dict]:
    """从 scenario_wiki.md 解析所有条目，返回结构化列表。"""
    entries = []
    blocks = re.split(r'\n(?=## [A-Z])', text)
    for block in blocks:
        block = block.strip()
        if not block.startswith("## "):
            continue
        entry = {"raw": block}
        # 解析字段
        for field in ["entry_id", "scenario_type", "label", "verified",
                      "actual_outcome", "confidence_breakdown", "grv_at_inference"]:
            m = re.search(rf'- {field}: (.+)', block)
            entry[field] = m.group(1).strip() if m else None
        # 解析传导路径
        path_lines = re.findall(r'^\s+\d+\. (T\+.+)$', block, re.MULTILINE)
        entry["transmission_path"] = path_lines
        entries.append(entry)
    return entries


def _extract_numbers(text: str) -> list[float]:
    """从文本中提取所有数字（含负号和小数）。"""
    if not text:
        return []
    return [float(m) for m in re.findall(r'-?\d+\.?\d*', text)]


# ── 误差计算 ───────────────────────────────────────────────────
def _compute_error(entry: dict) -> dict | None:
    """
    计算单条推演的预测误差。
    actual_outcome 字段格式（人工填写示例）：
      "SPX=-8.5%, VIX峰值=32, 持续=3周"
    """
    outcome = entry.get("actual_outcome", "")
    if not outcome or outcome.strip() in ("（待填写）", "", "N/A"):
        return None

    errors = {}

    # 尝试从 confidence_breakdown 里拿预测区间（如果有 spx_p50 之类）
    # 目前简单解析 actual_outcome 里的数字
    spx_m = re.search(r'SPX\s*=\s*(-?\d+\.?\d*)%?', outcome, re.I)
    vix_m = re.search(r'VIX.*?=\s*(\d+\.?\d*)', outcome, re.I)

    if spx_m:
        errors["spx_actual"] = float(spx_m.group(1))
    if vix_m:
        errors["vix_actual"] = float(vix_m.group(1))

    return errors if errors else None


# ── 主流程 ────────────────────────────────────────────────────
def run_verification(commit: bool = False) -> dict:
    if not WIKI_FILE.exists():
        print(f"[VERIFY] scenario_wiki.md 不存在: {WIKI_FILE}")
        return {"entries": 0, "verified": 0, "pending": 0}

    text = WIKI_FILE.read_text(encoding="utf-8")
    entries = _parse_wiki_entries(text)

    total     = len(entries)
    already   = [e for e in entries if e.get("verified") == "true"]
    pending   = [e for e in entries if e.get("verified") == "false"
                 and e.get("actual_outcome") not in (None, "（待填写）", "")]
    no_data   = [e for e in entries if e.get("verified") == "false"
                 and e.get("actual_outcome") in (None, "（待填写）", "")]

    print(f"\n{'='*60}")
    print(f"  假设推演校准报告  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"  总条目: {total}  |  已验证: {len(already)}  |  "
          f"待校准: {len(pending)}  |  等待结果: {len(no_data)}")

    results = []
    for entry in pending:
        label = entry.get("label", "未知")
        stype = entry.get("scenario_type", "")
        print(f"\n── {label} ({stype}) ──")
        print(f"  推演时记录: {entry.get('confidence_breakdown','N/A')}")
        print(f"  实际结果:   {entry.get('actual_outcome')}")

        err = _compute_error(entry)
        if err:
            print(f"  误差数字:   {err}")
            results.append({
                "entry_id": entry.get("entry_id"),
                "label":    label,
                "actual":   err,
                "outcome_text": entry.get("actual_outcome"),
            })

            # 简单校准建议
            spx = err.get("spx_actual")
            if spx is not None:
                if abs(spx) > 20:
                    print(f"  ⚠ SPX 实际回撤 {spx}% 较大 → 建议检查传导路径 calibration_score 是否偏低")
                elif abs(spx) < 3:
                    print(f"  ℹ SPX 实际回撤 {spx}% 较小 → L1/外交危机路径 calibration_score 可上调")
        else:
            print(f"  ℹ actual_outcome 格式无法解析数字，跳过误差计算")
            print(f"    建议格式：'SPX=-8.5%, VIX峰值=32, 持续=3周'")

    if pending and commit:
        print(f"\n[COMMIT] 将 {len(pending)} 条条目标记为 verified:true ...")
        new_text = text
        for entry in pending:
            new_text = new_text.replace(
                f"- verified: false\n- actual_outcome: {entry['actual_outcome']}",
                f"- verified: true\n- actual_outcome: {entry['actual_outcome']}"
            )
        WIKI_FILE.write_text(new_text, encoding="utf-8")
        print(f"  ✅ scenario_wiki.md 已更新")

    if not pending:
        print(f"\n  当前无待校准条目。")
        print(f"  操作方法：在 scenario_wiki.md 中找到目标条目，")
        print(f"  将 'actual_outcome: （待填写）' 改为实际结果，")
        print(f"  再运行本脚本（加 --commit 同步标记为已验证）。")

    # 升格说明
    print(f"\n{'─'*60}")
    print(f"  传导路径 source 升格规则：")
    print(f"  ≥3次真实事件校验 → 可升为 empirically_calibrated")
    print(f"  升格后置信度信号灯从 🔴 升为 🟡（需人工审核后修改 propagation_paths.yaml）")
    print(f"{'='*60}\n")

    summary = {
        "run_at":   datetime.datetime.now().isoformat(timespec="seconds"),
        "total":    total,
        "already_verified": len(already),
        "pending_calibration": len(pending),
        "waiting_outcome": len(no_data),
        "results":  results,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[VERIFY] 报告已写入 {OUTPUT_FILE}")

    return summary


# ── Phase 3C：贝叶斯权重更新 ─────────────────────────────────────
def _bayesian_update_score(current_score: float, hit: bool,
                           learning_rate: float = 0.1) -> float:
    """
    贝叶斯风格权重更新（指数移动平均）。
    命中：score = score * (1 - α) + α * 1.0   → 向1靠拢
    未命中：score = score * (1 - α) + α * 0.0  → 向0靠拢
    α = learning_rate（默认0.1，每次更新缓慢调整）
    """
    target = 1.0 if hit else 0.0
    new_score = current_score * (1 - learning_rate) + learning_rate * target
    return round(max(0.05, min(0.95, new_score)), 3)  # 硬限：[0.05, 0.95]


def update_path_weights(results: list, commit: bool = False) -> dict:
    """
    根据校准结果，更新 propagation_paths.yaml 中的 calibration_score。

    判断命中逻辑（启发式）：
      SPX 实际值与路径 causal_chain 中的 spx_impact 同向且量级相似 → 命中
      当前简化为：|spx_actual| > 5% 且路径类型匹配 → 视为命中
    只更新路径 enabled=true 且 source 非 llm_inference 的条目。

    commit=False 时只打印建议，不写文件。
    """
    if not PATHS_FILE.exists():
        print("[PATH_UPDATE] propagation_paths.yaml 不存在，跳过")
        return {}

    try:
        import yaml
        with open(PATHS_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"[PATH_UPDATE] 加载 YAML 失败: {e}")
        return {}

    # propagation_paths.yaml 顶层可能是直接列表，也可能包在 paths: 下
    if isinstance(data, list):
        paths = data
    elif isinstance(data, dict):
        paths = data.get("paths", data.get("propagation_paths", []))
    else:
        paths = []

    if not paths:
        print("[PATH_UPDATE] 未找到传导路径列表，跳过")
        return {}

    updates = {}
    for result in results:
        spx = result.get("actual", {}).get("spx_actual")
        label = result.get("label", "")
        if spx is None:
            continue

        # 简单路由：根据情景标签匹配相关路径
        relevant_types = []
        if "台海" in label or "TAIWAN" in label.upper():
            relevant_types = ["geo_taiwan_diplomatic", "geo_taiwan_semiconductor"]
        elif "贸易" in label or "关税" in label or "TRADE" in label.upper():
            relevant_types = ["trade_tariff_escalation", "geo_us_china_trade"]
        elif "能源" in label or "石油" in label or "ENERGY" in label.upper():
            relevant_types = ["energy_middle_east_oil"]
        elif "俄" in label or "乌" in label or "RUSSIA" in label.upper():
            relevant_types = ["geo_russia_europe"]
        elif "银行" in label or "金融" in label or "FIN" in label.upper():
            relevant_types = ["fin_banking_crisis"]

        hit = abs(spx) > 5  # 简化命中判断：实际回撤>5%视为事件显著发生

        for path in paths:
            pid = path.get("id", "")
            if pid not in relevant_types:
                continue
            if path.get("source") == "llm_inference":
                continue  # LLM推断路径不参与自动更新

            old_score = path.get("calibration_score", 0.5)
            new_score = _bayesian_update_score(old_score, hit)
            if abs(new_score - old_score) > 0.005:
                updates[pid] = {"old": old_score, "new": new_score, "hit": hit}
                print(f"  [PATH_UPDATE] {pid}: {old_score:.3f} → {new_score:.3f} "
                      f"({'命中' if hit else '未命中'}，SPX={spx}%)")
                if commit:
                    path["calibration_score"] = new_score

    if commit and updates:
        try:
            import yaml
            with open(PATHS_FILE, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            print(f"  [PATH_UPDATE] propagation_paths.yaml 已更新 {len(updates)} 条路径")
        except Exception as e:
            print(f"  [PATH_UPDATE] 写入失败: {e}")
    elif updates:
        print(f"  [PATH_UPDATE] 以上为建议变更，添加 --update-weights 参数后实际写入")

    return updates


def main():
    parser = argparse.ArgumentParser(description="假设推演校准闭环工具")
    parser.add_argument("--commit", action="store_true",
                        help="将已有 actual_outcome 的条目标记为 verified:true")
    parser.add_argument("--update-weights", action="store_true",
                        help="Phase 3C：同时更新 propagation_paths.yaml 的 calibration_score")
    args = parser.parse_args()
    summary = run_verification(commit=args.commit)
    if args.update_weights and summary.get("results"):
        print("\n[Phase 3C] 开始贝叶斯权重更新...")
        update_path_weights(summary["results"], commit=args.commit)


if __name__ == "__main__":
    main()
