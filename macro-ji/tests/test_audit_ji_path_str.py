# -*- coding: utf-8 -*-
"""
回归测试（审计发现 #4 HIGH correctness）: verify_hypothesis.update_path_weights

锁定 bug: 在 commit 写回分支，源码用 `PATHS_FILE + ".tmp"` 构造临时文件名，
但 PATHS_FILE 是 pathlib.Path，`Path + str` 抛 TypeError，被 except 吞掉，
导致 propagation_paths.yaml 的 calibration_score 永不落盘。

本测试断言【正确】行为: commit=True 时更新后的 calibration_score 真正写入
yaml 文件。因 bug 仍存在, 用 xfail(strict=True) 标注 —— 修复后会 xpass 触发
strict 失败, 强制摘掉标记, 转为活体守卫。

顶部自注入 sys.path 使 verify_hypothesis 可在任意 cwd 下 import。
"""

import os
import sys

import pytest
import yaml

# macro-ji 根目录 = 本文件所在 tests 目录的上一级
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import verify_hypothesis  # noqa: E402


@pytest.mark.xfail(
    strict=True,
    reason="审计发现 #4: update_path_weights 用 `Path + str` 抛 TypeError 被吞, "
    "calibration_score 永不落盘",
)
def test_update_path_weights_persists_calibration_score(tmp_path, monkeypatch):
    # 构造一个合法的 propagation_paths.yaml, 含一条会被路由命中的路径
    paths_file = tmp_path / "propagation_paths.yaml"
    initial = {
        "paths": [
            {
                "id": "geo_taiwan_diplomatic",
                "source": "manual_calibrated",
                "enabled": True,
                "calibration_score": 0.5,
            }
        ]
    }
    paths_file.write_text(
        yaml.dump(initial, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    # 将模块级 PATHS_FILE 指向临时文件 (保持 pathlib.Path, 以复现 Path+str 场景)
    monkeypatch.setattr(verify_hypothesis, "PATHS_FILE", paths_file)

    # label 含 "台海" → 路由到 geo_taiwan_diplomatic; spx=-8.5 → hit=True
    results = [
        {
            "entry_id": "e1",
            "label": "台海危机推演",
            "actual": {"spx_actual": -8.5},
        }
    ]

    updates = verify_hypothesis.update_path_weights(results, commit=True)

    # 预期: 命中并计算出新分 (0.5 → 0.55)
    assert "geo_taiwan_diplomatic" in updates
    expected_new = updates["geo_taiwan_diplomatic"]["new"]

    # 关键断言: 新的 calibration_score 必须真正写回磁盘
    on_disk = yaml.safe_load(paths_file.read_text(encoding="utf-8"))
    disk_score = on_disk["paths"][0]["calibration_score"]
    assert disk_score == expected_new, (
        f"calibration_score 未落盘: 磁盘={disk_score} 期望={expected_new}"
    )
