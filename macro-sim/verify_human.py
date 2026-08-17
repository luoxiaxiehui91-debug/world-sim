# -*- coding: utf-8 -*-
"""verify_human.py — 地缘预测人工验证 CLI（08-17 新增，填补"待人工"验证渠道缺口）

predictions 表里 status='awaiting_human' 的地缘事件预测设计上"等人工验证"，
此前系统没有任何入口（自动验证只处理 quantitative/pending）。本脚本提供：

  python verify_human.py --list                  # 列出全部待人工验证预测
  python verify_human.py --verify <id> \
      --outcome <0|1|0.5> [--note "备注"]        # 验证一条（0=未发生 1=发生 0.5=部分/不确定）

验证后：status → verified，outcome_value 落库，brier = (final_prob − outcome)²，
verified_by = 'human'（与自动验证 verified_by='auto' 区分），human_note 存备注。
幂等：已 verified 的预测拒绝重复验证。

连接：psycopg 直连 worldsim-pg（search_path=tianji,public，与 run.py 落表同机制）。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

PG_HOST = os.environ.get("WORLDSIM_PG_HOST", "worldsim-pg")
PG_PORT = int(os.environ.get("WORLDSIM_PG_PORT", "5432"))
PG_DB = "worldsim"
PG_USER = "worldsim_app"


def _connect():
    try:
        import psycopg
    except ImportError as e:
        sys.exit(f"[verify_human] psycopg 未安装：{e}")
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        sys.exit("[verify_human] WORLDSIM_APP_PW 未注入（fail-fast）")
    last_err = None
    for attempt in range(3):
        try:
            return psycopg.connect(
                host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER,
                password=pw, options="-c search_path=tianji,public",
            )
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    sys.exit(f"[verify_human] 连接 worldsim-pg 失败（重试 3 次）：{last_err}")


def _fetch_dicts(cur):
    """psycopg3 默认 row=tuple：用 description 列名组装 dict。"""
    cols = [d.name for d in cur.description] if cur.description else []
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def cmd_list(conn, due_days: int):
    """列出全部 awaiting_human（可选仅看距 due_at 剩余天数 ≤ due_days 的到期项）。"""
    cur = conn.execute(
        "SELECT id, created_at, due_at, scenario_id, final_prob, confidence_tier, "
        "LEFT(content, 100) AS content, LEFT(outcome_definition, 100) AS outcome, human_note "
        "FROM predictions WHERE status = 'awaiting_human' "
        "ORDER BY due_at ASC, created_at DESC"
    )
    rows = _fetch_dicts(cur)
    if not rows:
        print("[verify_human] 无待人工验证预测")
        return 0
    now = datetime.now().astimezone()
    print(f"[verify_human] 待人工验证 {len(rows)} 条：")
    print()
    for r in rows:
        due = r["due_at"] if isinstance(r["due_at"], datetime) else (
            datetime.fromisoformat(r["due_at"]) if r["due_at"] else None)
        days = (due - now).days if due else None
        if due_days is not None and (days is None or days > due_days):
            continue
        flag = "已到期" if days is not None and days < 0 else f"剩{days}天"
        due_str = due.strftime("%Y-%m-%d") if due else "—"
        print(f"  {r['id']}")
        print(f"    {r['content'] or '—'}")
        print(f"    [概率 {r['final_prob']:.0%} · {r['confidence_tier']}] 验证至 {due_str}（{flag}）")
        if r["human_note"]:
            print(f"    备注：{r['human_note']}")
    return 0


def cmd_verify(conn, pred_id: str, outcome: float, note: str | None):
    """验证一条：0/1/0.5 → status=verified, outcome_value, brier, verified_by=human。"""
    if outcome not in (0.0, 0.5, 1.0):
        sys.exit("[verify_human] --outcome 必须为 0（未发生）/ 1（发生）/ 0.5（部分/不确定）")
    cur = conn.execute(
        "SELECT id, status, final_prob, LEFT(content, 80) AS content "
        "FROM predictions WHERE id = %s", (pred_id,))
    rows = _fetch_dicts(cur)
    if not rows:
        sys.exit(f"[verify_human] 预测不存在：{pred_id}")
    r = rows[0]
    if r["status"] != "awaiting_human":
        sys.exit(f"[verify_human] 预测 {pred_id} 当前状态={r['status']}，仅 awaiting_human 可人工验证（幂等拒绝）")
    brier = round((float(r["final_prob"]) - outcome) ** 2, 4)
    with conn:
        cur = conn.execute(
            "UPDATE predictions SET status = 'verified', outcome_value = %s, "
            "brier_score = %s, verified_at = CURRENT_TIMESTAMP, verified_by = 'human', "
            "human_note = %s WHERE id = %s",
            (outcome, brier, note, pred_id))
    print(f"[verify_human] {pred_id} 验证成功")
    print(f"    {r['content']}")
    print(f"    outcome={outcome}（0=未发生 1=发生 0.5=部分）| brier={brier} | verified_by=human")
    if note:
        print(f"    备注：{note}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="地缘预测人工验证（awaiting_human → verified）")
    p.add_argument("--list", action="store_true", help="列出待人工验证预测")
    p.add_argument("--due-days", type=int, default=None, help="仅显示距验证截止剩余天数≤N（配合 --list）")
    p.add_argument("--verify", type=str, default=None, metavar="ID", help="验证指定预测 id")
    p.add_argument("--outcome", type=float, default=None, help="0=未发生 / 1=发生 / 0.5=部分或不确定")
    p.add_argument("--note", type=str, default=None, help="人工备注（存 human_note）")
    args = p.parse_args()

    conn = _connect()
    if args.verify:
        if args.outcome is None:
            sys.exit("[verify_human] --verify 需要 --outcome 0|1|0.5")
        return cmd_verify(conn, args.verify, args.outcome, args.note)
    return cmd_list(conn, args.due_days)


if __name__ == "__main__":
    sys.exit(main())
