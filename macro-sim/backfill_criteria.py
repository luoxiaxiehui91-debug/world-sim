# -*- coding: utf-8 -*-
"""backfill_criteria.py — 历史预测判据回填（08-18）

predictions 表里 08-18 之前的 geo 预测（awaiting_human）outcome_definition 无"判定标准"，
本脚本按 content 中的事件名反查 _ACTION_CRITERIA，回填 outcome_definition。

用法：python3 backfill_criteria.py [--dry-run]
"""
import argparse
import os
import re
import sys
import time


def _connect():
    import psycopg
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        sys.exit("[backfill] WORLDSIM_APP_PW 未注入（fail-fast）")
    last_err = None
    for attempt in range(3):
        try:
            return psycopg.connect(
                host="worldsim-pg", port=5432, dbname="worldsim", user="worldsim_app",
                password=pw, options="-c search_path=tianji,public")
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    sys.exit(f"[backfill] 连接失败：{last_err}")


def extract_event_name(content: str) -> str | None:
    """从预测 content 提取事件名（两种格式兼容）：
      新：路径A路径（GRV 60→62）：媒体放大恐慌情绪 （仿真频率44%）
      旧：WorkBuddy-daemon-verify-20260806 情景下 路径A路径：媒体保持中性报道 （仿真频率46%）
    """
    m = re.search(r"：(.+?)\s*（仿真频率", content)
    return m.group(1).strip() if m else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="只统计不更新")
    args = p.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from core.bifurcation import label_to_action_key, criterion_for_action, _ACTION_CRITERIA

    conn = _connect()
    cur = conn.execute(
        "SELECT id, content, outcome_definition FROM predictions "
        "WHERE status = 'awaiting_human' AND outcome_definition NOT LIKE '%判定标准%'")
    rows = [dict(zip([d.name for d in cur.description], r)) for r in cur.fetchall()]
    print(f"[backfill] 待回填 {len(rows)} 条（awaiting_human 且无判据）")

    updated = 0
    unmatched: dict[str, int] = {}
    for r in rows:
        name = extract_event_name(r["content"] or "")
        if not name:
            unmatched["<无事件名>"] = unmatched.get("<无事件名>", 0) + 1
            continue
        # 事件名可能是中文 label（反查 key）或旧版直接存的动作 key（如 "A4:CUT_OUTPUT"）
        if name in _ACTION_CRITERIA:
            key = name
        else:
            key = label_to_action_key(name)
        crit = criterion_for_action(key) if key else ""
        if not crit:
            unmatched[name] = unmatched.get(name, 0) + 1
            continue
        new_outcome = f"{r['outcome_definition']}。判定标准：{crit}"
        if args.dry_run:
            print(f"  [dry] {r['id'][:12]}… {name} → {crit}")
        else:
            conn.execute(
                "UPDATE predictions SET outcome_definition = %s WHERE id = %s",
                (new_outcome, r["id"]))
        updated += 1

    if not args.dry_run:
        conn.commit()
    print(f"[backfill] 回填 {updated} 条（{'dry-run 未写库' if args.dry_run else '已写库'}）")
    if unmatched:
        print(f"[backfill] 未匹配事件名 {len(unmatched)} 种：")
        for name, n in sorted(unmatched.items(), key=lambda x: -x[1]):
            print(f"    {name} ×{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
