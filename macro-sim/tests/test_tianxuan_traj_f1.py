# -*- coding: utf-8 -*-
"""
回归测试：F1 天璇 GRV 轨迹落盘 —— run._write_grv_trajectory
（macro-sim · 天璇 → 天枢 export → 开阳展示 三段链的最上游产出）

目的
----
锁定天璇结构化轨迹 JSON 的契约，天枢 tianxuan_grv_export.py 与开阳 TianxuanGrvRaw 都依赖它：
1. 合法 JSON、带版本护栏 producer/traj_schema（M4：跨子系统 schema 无版本护栏会静默漂移）。
2. months / 每路径 monthly_grv / monthly_grv_std 三者长度对齐 == horizon（==24）。
3. baseline_grv 透传自 world.grv（M11：开阳画 month-0 观测锚点用）。
4. 原子写：成功后无残留 .tmp。
5. paths 为空时降级不崩（首次/异常路径产出为空仍写文件，天枢/前端据此占位）。

运行方式
--------
    cd /s/world-sim/macro-sim && python tests/test_tianxuan_traj_f1.py

自包含纯 Python 脚本，不依赖 pytest（macro-sim 未安装 pytest）。
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run as run_mod
from core.bifurcation import PathResult

_PASSED = []


def _t(name, fn):
    fn()
    _PASSED.append(name)
    print(f"  ✓ {name}")


# ── 工装 ─────────────────────────────────────────────────

class _W:
    """最小 world 替身：_write_grv_trajectory 只读 .grv 作 baseline。"""
    def __init__(self, grv):
        self.grv = grv


def _mk_path(label, prob, n=24, base=60.0):
    """一条真实 PathResult（含 F1/M2 新增 monthly_grv_std），24 步逐月轨迹。"""
    return PathResult(
        label=label, probability=prob, run_indices=list(range(10)),
        initial_grv_mean=base, final_grv_mean=base + 5.0, final_grv_std=2.0,
        grv_trend="持续上升",
        monthly_grv=[round(base + i * 0.5, 1) for i in range(n)],
        monthly_grv_std=[round(1.0 + i * 0.1, 1) for i in range(n)],
    )


def _write_and_load(paths, world=None):
    """在临时目录内落盘并读回：返回 (payload_or_None, json_files, tmp_files)。"""
    world = world or _W(72.0)
    d = tempfile.mkdtemp(prefix="grv_traj_test_")
    orig = run_mod.REPORT_DIR
    try:
        run_mod.REPORT_DIR = Path(d)
        run_mod._write_grv_trajectory(
            paths, world, level=2, event="单测",
            report_stem="2026-08-27_10-00_演化_L2_校准0",
        )
        json_files = list(Path(d).glob("*_grv_traj.json"))
        tmp_files = list(Path(d).glob("*.tmp"))
        payload = json.loads(json_files[0].read_text(encoding="utf-8")) if json_files else None
        return payload, json_files, tmp_files
    finally:
        run_mod.REPORT_DIR = orig


# ── 1) 合法 JSON + 版本护栏 + 长度对齐 + baseline 透传 ────────

def test_writes_valid_json_with_schema_and_aligned_lengths():
    paths = [_mk_path("路径A", 0.6), _mk_path("路径B", 0.4)]
    payload, json_files, tmp_files = _write_and_load(paths, _W(72.0))

    assert len(json_files) == 1, f"应恰好落盘一份轨迹 JSON（实测 {len(json_files)}）"
    assert payload is not None, "轨迹 JSON 应为合法可解析"
    # M4 版本护栏（天枢 export 据此校验，缺失则拒收）
    assert payload["producer"] == "macro-sim", f"producer 必须为 macro-sim（实测 {payload.get('producer')}）"
    assert payload["traj_schema"] == "1.0", f"traj_schema 必须为 1.0（实测 {payload.get('traj_schema')}）"
    # M11 观测锚点透传
    assert payload["baseline_grv"] == 72.0, f"baseline_grv 应透传 world.grv=72.0（实测 {payload.get('baseline_grv')}）"
    # 长度三者对齐 == horizon == 24
    assert payload["horizon_months"] == 24, f"horizon 应为 24（实测 {payload.get('horizon_months')}）"
    assert len(payload["months"]) == 24, f"months 长度应为 24（实测 {len(payload['months'])}）"
    for p in payload["paths"]:
        assert len(p["monthly_grv"]) == 24, f"{p['label']} monthly_grv 长度应为 24（实测 {len(p['monthly_grv'])}）"
        assert len(p["monthly_grv_std"]) == 24, f"{p['label']} monthly_grv_std 长度应为 24（实测 {len(p['monthly_grv_std'])}）"


# ── 2) 原子写：成功后无残留 .tmp ─────────────────────────────

def test_no_tmp_residual_after_success():
    paths = [_mk_path("路径A", 1.0)]
    _payload, _json_files, tmp_files = _write_and_load(paths)
    assert tmp_files == [], f"原子 rename 后不应残留 .tmp（实测 {tmp_files}）"


# ── 3) months 为未来 YYYY-MM ─────────────────────────────────

def test_months_are_future_yyyy_mm():
    paths = [_mk_path("路径A", 1.0)]
    payload, _jf, _tf = _write_and_load(paths)
    pat = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    assert all(pat.match(m) for m in payload["months"]), f"months 应全为 YYYY-MM（实测 {payload['months'][:3]}...）"
    # 严格递增（逐月推进，无重复/回绕错误）
    assert payload["months"] == sorted(payload["months"]), "months 应按月严格递增"
    assert len(set(payload["months"])) == 24, "months 不应有重复月份"


# ── 4) paths 为空时降级不崩 ──────────────────────────────────

def test_empty_paths_degrades_gracefully():
    payload, json_files, _tf = _write_and_load([])  # 空路径（首次/异常产出）
    assert len(json_files) == 1, "空路径也应写出文件（供天枢/前端占位）"
    assert payload["paths"] == [], "空路径 payload.paths 应为 []"
    assert payload["horizon_months"] == 0, "无路径时 horizon 为 0"
    assert payload["months"] == [], "无路径时 months 为 []"
    # 版本护栏仍在（探针/schema 稳定锚点）
    assert payload["producer"] == "macro-sim" and payload["traj_schema"] == "1.0"


# ── 主入口 ───────────────────────────────────────────────

def main():
    print("test_tianxuan_traj_f1: 天璇 GRV 轨迹落盘契约")
    _t("test_writes_valid_json_with_schema_and_aligned_lengths", test_writes_valid_json_with_schema_and_aligned_lengths)
    _t("test_no_tmp_residual_after_success", test_no_tmp_residual_after_success)
    _t("test_months_are_future_yyyy_mm", test_months_are_future_yyyy_mm)
    _t("test_empty_paths_degrades_gracefully", test_empty_paths_degrades_gracefully)
    print(f"全部通过（{len(_PASSED)} 组）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
