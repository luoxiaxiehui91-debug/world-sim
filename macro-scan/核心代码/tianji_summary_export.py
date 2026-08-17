# -*- coding: utf-8 -*-
"""tianji_summary_export.py — 天玑汇总导出（08-17 新增，供开阳天玑 Tab 只读展示）

从 PG tianji schema 查预测/推理/权重汇总 → 写 data/tianji_summary.json（tmp+rename 原子写）。
由 scheduler "I30" 每 30 分钟触发；PG 不可读时降级写 {ok:false}，不阻断调度。

数据结构（开阳 kaiyang TianjiTab 消费）：
  ok / schema_version / updated(aware +08:00)
  predictions: {total, by_type{type:count}, by_status{status:count}, recent[≤10]}
  reasoning_trace: {total}
  weight_update_log: {total, recent[≤5]}
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pg_read import connect  # noqa: E402  只读 PG 连接（_Row 行工厂，datetime 已归一化文本）

DATA_DIR = os.environ.get("OPENCLAW_WORKSPACE", "/workspace") + "/data"
OUT_PATH = os.path.join(DATA_DIR, "tianji_summary.json")


def _query(conn, sql, params=()):
    """执行只读查询，返回 list[dict]（列名 → 值）。失败抛异常由调用方兜底。"""
    cur = conn.execute(sql, params)
    cols = [d.name for d in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def main() -> int:
    now_str = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    payload = {
        "ok": True,
        "schema_version": "1.0",
        "updated": now_str,
    }
    try:
        conn = connect()
        if conn is None:
            raise RuntimeError("PG 读连接不可用（WORLDSIM_APP_PW 缺失或连接失败）")
        with conn:
            # ── predictions（天璇→天玑预测存档）─────────────────
            payload["predictions"] = {
                "total": _query(conn, "SELECT count(*) AS n FROM predictions")[0]["n"],
                "by_type": {r["type"]: r["n"] for r in _query(
                    conn, "SELECT type, count(*) AS n FROM predictions GROUP BY type ORDER BY n DESC")},
                "by_status": {r["status"]: r["n"] for r in _query(
                    conn, "SELECT status, count(*) AS n FROM predictions GROUP BY status ORDER BY n DESC")},
                "recent": _query(
                    conn,
                    "SELECT id, created_at, due_at, scenario_id, type, prediction_target_type, "
                    "LEFT(content, 100) AS content, target_direction, target_threshold, "
                    "final_prob, confidence_tier, status "
                    "FROM predictions ORDER BY created_at DESC LIMIT 10"),
            }
            # ── reasoning_trace（推理溯源）──────────────────────
            payload["reasoning_trace"] = {
                "total": _query(conn, "SELECT count(*) AS n FROM reasoning_trace")[0]["n"],
            }
            # ── weight_update_log（玉衡权重更新）────────────────
            payload["weight_update_log"] = {
                "total": _query(conn, "SELECT count(*) AS n FROM weight_update_log")[0]["n"],
                "recent": _query(
                    conn,
                    "SELECT id, updated_at, signal_name, target_type, "
                    "weight_before, weight_after, reason "
                    "FROM weight_update_log ORDER BY id DESC LIMIT 5"),
            }
    except Exception as e:
        payload["ok"] = False
        payload["error"] = str(e)
        print(f"[tianji_summary] 导出失败：{e}", flush=True)

    tmp = OUT_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        os.rename(tmp, OUT_PATH)
        print(f"[tianji_summary] 已写入 {OUT_PATH}（ok={payload.get('ok')}）", flush=True)
        return 0
    except Exception as e:
        print(f"[tianji_summary] 写文件失败：{e}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
