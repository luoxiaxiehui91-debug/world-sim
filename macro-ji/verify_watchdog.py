"""
verify_watchdog.py — 天玑容器触发 watchdog（T2 共享触发文件机制）

轮询 /app/macro_data/tianji_trigger.json（天枢 scheduler 写入），检出未处理 trigger
即执行 tianji_verifier.py（验证+反哺），完成后将 trigger 置 processed 并归档。

幂等键：trigger 的 batch_id/date 唯一；processed 后不再重复执行。
复用 sim_trigger 成熟模式：目录挂载 + 原子写（tmp → os.rename），禁单文件 bind。
"""
import json
import os
import subprocess
import sys
import time

DATA_DIR = os.environ.get("TIANJI_DATA_DIR", "/app/macro_data")
TRIGGER_PATH = os.path.join(DATA_DIR, "tianji_trigger.json")
POLL_INTERVAL = 3.0
VERIFIER = [sys.executable, os.path.join("/app", "tianji_verifier.py")]


def _mark_processed(trigger: dict) -> None:
    """原子写回 processed 状态（tmp → os.rename，避免半写）。"""
    trigger["processed"] = True
    trigger["processed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    tmp = TRIGGER_PATH + ".watchdog.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trigger, f, ensure_ascii=False, indent=2)
    os.rename(tmp, TRIGGER_PATH)


def _run_verifier() -> tuple:
    """执行 tianji_verifier.py（无参数跑主流程），返回 (exit_code, 输出尾部)。"""
    try:
        r = subprocess.run(VERIFIER, capture_output=True, text=True, timeout=600)
        return r.returncode, (r.stdout or "")[-800:] + (r.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT after 600s"
    except Exception as e:
        return -2, f"ERROR: {e}"


def main() -> int:
    print(f"[watchdog] start: poll {TRIGGER_PATH} every {POLL_INTERVAL}s", flush=True)
    while True:
        try:
            if not os.path.exists(TRIGGER_PATH):
                time.sleep(POLL_INTERVAL)
                continue
            with open(TRIGGER_PATH, encoding="utf-8") as f:
                trigger = json.load(f)
            if trigger.get("processed"):
                time.sleep(POLL_INTERVAL)
                continue
            batch_id = trigger.get("batch_id") or trigger.get("date") or "unknown"
            print(f"[watchdog] trigger detected: batch={batch_id}", flush=True)
            code, tail = _run_verifier()
            print(f"[watchdog] verifier exit={code}\n{tail}", flush=True)
            trigger["last_result"] = {"exit": code, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            _mark_processed(trigger)
            print(f"[watchdog] batch={batch_id} processed (exit={code})", flush=True)
        except json.JSONDecodeError:
            print("[watchdog] trigger JSON 损坏（半写？），等待下轮", flush=True)
        except Exception as e:
            print(f"[watchdog] ERROR: {e}", flush=True)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
