# -*- coding: utf-8 -*-
"""tianxuan_grv_export.py — 天璇推演 GRV 轨迹导出（F1，2026-08-27 新增，供开阳天璇 Tab 只读展示）

三段链（权责铁律：天枢是开阳 feed 的唯一产出方）：
  天璇 macro-sim 写 docs/仿真报告/<stem>_grv_traj.json（自己的报告目录，不直写 feed）
    → 本脚本扫报告目录取最新一份 → 导出 data/tianxuan_grv.json（tmp+rename 原子写）
    → 开阳 kaiyang TianxuanTab 只读展示

由 scheduler "I30" 每 30 分钟触发。设计要点：
  - M4 防静默：源缺失/解析失败/版本护栏不符 → 醒目告警 + 保留上一份有效 feed（不静默写空）；
    仅当从无 feed 且无源（首次预测前）→ 写空 feed（带 schema_version+generated_at，给探针稳定锚点）。
  - M3 认识论：feed 标 is_scenario:true / kernel_label="天璇·数学基线"（不含"官方"）；
    当前三段链【不含】天玑校验此轨迹，不写任何"天玑校验"背书。
  - M6 幂等：最新源 generated_at == 现有 feed generated_at → 跳过重写（不动 mtime，避免恒显"刚刷新"）。

feed 数据结构（开阳 TianxuanGrvRaw 消费）：
  schema_version / is_scenario / kernel / kernel_label / disclaimer
  generated_at（透传天璇产出时刻）/ exported_at（天枢导出时刻）/ source_file
  level / event / horizon_months / baseline_grv
  months[N] / paths[{label,probability,grv_trend,initial/final_grv_mean,final_grv_std,monthly_grv[N],monthly_grv_std[N]}]
"""
import glob
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from optim_config import DATA_DIR, WORKSPACE
except Exception:  # 部署配置错误时 fail-loud（与 generate_reports_index.py / scheduler.py 同口径）
    print("FATAL: cannot import optim_config.WORKSPACE/DATA_DIR", flush=True)
    sys.exit(1)

SRC_DIR  = os.path.join(WORKSPACE, "docs", "仿真报告")   # 天璇报告目录（两容器共享 NAS 目录）
OUT_PATH = os.path.join(DATA_DIR, "tianxuan_grv.json")

SCHEMA_VERSION = "1.0"
KERNEL         = "math-mc"
KERNEL_LABEL   = "天璇·数学基线"
DISCLAIMER     = "数学蒙特卡洛基线；非事实、非投资建议。"

# 从天璇 traj payload 透传到 feed 的字段（原样搬运，天枢不改数值）
_PASSTHRU_TOP  = ("level", "event", "horizon_months", "baseline_grv", "months")
_PASSTHRU_PATH = ("label", "probability", "grv_trend", "initial_grv_mean",
                  "final_grv_mean", "final_grv_std", "monthly_grv", "monthly_grv_std")


def _now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_existing_feed():
    """读现有 feed（用于 M6 幂等比对 + M4 保留旧值）；不存在/损坏返回 None。"""
    if not os.path.exists(OUT_PATH):
        return None
    try:
        return _load_json(OUT_PATH)
    except Exception:
        return None


def _atomic_write(payload: dict) -> int:
    tmp = OUT_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, OUT_PATH)
        print(f"[tianxuan_grv] 已写入 {OUT_PATH}"
              f"（paths={len(payload.get('paths', []))} generated_at={payload.get('generated_at')}）",
              flush=True)
        return 0
    except Exception as e:
        print(f"[tianxuan_grv] 写文件失败：{e}", flush=True)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return 1


def _empty_feed() -> dict:
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "is_scenario":    True,
        "kernel":         KERNEL,
        "kernel_label":   KERNEL_LABEL,
        "disclaimer":     DISCLAIMER,
        "generated_at":   None,          # 尚无天璇推演
        "exported_at":    now,
        "source_file":    None,
        "months":         [],
        "paths":          [],
    }


def _build_feed(traj: dict, src_name: str) -> dict:
    feed = {
        "schema_version": SCHEMA_VERSION,
        "is_scenario":    True,
        "kernel":         KERNEL,
        "kernel_label":   KERNEL_LABEL,
        "disclaimer":     DISCLAIMER,
        "generated_at":   traj.get("generated_at"),   # 透传天璇产出时刻
        "exported_at":    _now(),                      # 天枢导出时刻
        "source_file":    src_name,
    }
    for k in _PASSTHRU_TOP:
        feed[k] = traj.get(k)
    feed["paths"] = [
        {k: p.get(k) for k in _PASSTHRU_PATH}
        for p in (traj.get("paths") or [])
    ]
    return feed


def main() -> int:
    existing = _read_existing_feed()

    # ── 1. 扫报告目录取最新一份 *_grv_traj.json ──
    try:
        cands = glob.glob(os.path.join(SRC_DIR, "*_grv_traj.json"))
    except Exception as e:
        print(f"[tianxuan_grv] 报告目录扫描失败：{e}", flush=True)
        cands = []

    if not cands:
        if existing is not None:
            print("[tianxuan_grv] 源目录暂无轨迹，保留现有 feed（不动）", flush=True)
            return 0
        print("[tianxuan_grv] 源目录暂无轨迹且无现有 feed，写空 feed（首次锚点）", flush=True)
        return _atomic_write(_empty_feed())

    newest = max(cands, key=os.path.getmtime)
    src_name = os.path.basename(newest)

    # ── 2. 解析 + M4 版本护栏 ──
    try:
        traj = _load_json(newest)
    except Exception as e:
        # M4：源损坏不静默写空——保留旧 feed，醒目告警
        print(f"[tianxuan_grv][ERROR] 最新源 {src_name} 解析失败：{e}", flush=True)
        if existing is not None:
            print("[tianxuan_grv] 保留现有 feed（不覆盖）", flush=True)
            return 1
        print("[tianxuan_grv] 无现有 feed，写空 feed 兜底", flush=True)
        _atomic_write(_empty_feed())
        return 1

    producer = traj.get("producer")
    tschema  = str(traj.get("traj_schema") or "")
    if producer != "macro-sim" or tschema.split(".")[0] != "1":
        # M4：版本护栏不符 = schema 漂移，拒收，保留旧 feed
        print(f"[tianxuan_grv][ERROR] 源 {src_name} 版本护栏不符"
              f"（producer={producer!r} traj_schema={tschema!r}），拒收", flush=True)
        if existing is not None:
            print("[tianxuan_grv] 保留现有 feed（不覆盖）", flush=True)
            return 1
        _atomic_write(_empty_feed())
        return 1

    # ── 3. M6 幂等：源 generated_at 未变则跳过重写 ──
    src_gen = traj.get("generated_at")
    if existing is not None and src_gen and existing.get("generated_at") == src_gen:
        print(f"[tianxuan_grv] generated_at 未变（{src_gen}），跳过重写（幂等）", flush=True)
        return 0

    # ── 4. 构建 feed + 原子写 ──
    return _atomic_write(_build_feed(traj, src_name))


if __name__ == "__main__":
    sys.exit(main())
