# -*- coding: utf-8 -*-
"""write_tianji_trigger.py — 天枢侧写天玑触发文件（T2 机制）

由天枢 scheduler 的 tianji_trigger job（0942 每日）调用：向共享 data 目录写
tianji_trigger.json，天玑容器 verify_watchdog.py 轮询检出后执行验证。

幂等：batch_id = 日期；watchdog 处理完置 processed=true 原地回写，重复调度不重复执行。
原子写：tmp → os.rename（防半写；与 sim_trigger 同构，禁单文件 bind mount 是容器侧纪律）。
"""
import json
import os
import time
from datetime import date

# 与天玑容器 verify_watchdog.py 的 TIANJI_DATA_DIR 同源（宿主机同一 data 目录）
DATA_DIR = os.environ.get("OPENCLAW_WORKSPACE", "/workspace") + "/data"
TRIGGER_PATH = os.path.join(DATA_DIR, "tianji_trigger.json")


def main() -> int:
    batch_id = date.today().isoformat()
    payload = {
        "batch_id": batch_id,
        "date": batch_id,
        "triggered_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "tianshu-scheduler-tianji_trigger",
        "processed": False,
    }
    try:
        # 若已有同批 trigger 且未处理，不覆盖（保持 pending 状态）
        if os.path.exists(TRIGGER_PATH):
            with open(TRIGGER_PATH, encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("batch_id") == batch_id and not existing.get("processed"):
                print(f"[tianji_trigger] batch={batch_id} 已有未处理 trigger，跳过重写")
                return 0
        tmp = TRIGGER_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.rename(tmp, TRIGGER_PATH)
        print(f"[tianji_trigger] written batch={batch_id} → {TRIGGER_PATH}")
        return 0
    except Exception as e:
        print(f"[tianji_trigger] ERROR: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
