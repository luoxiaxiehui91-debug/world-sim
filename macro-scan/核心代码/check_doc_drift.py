#!/usr/bin/env python3
"""文档漂移巡检：检测 /app/*.py 是否比 TuiYan_CHANGELOG.md 更新。

定位：侦测"直接改 NAS 运行区但未更新文档"的行为。
若发现漂移超过 DRIFT_THRESHOLD_MINUTES 分钟，通过 ntfy 推送告警。
"""
import os
import sys
import time
import requests
from pathlib import Path

# 容器内：/app；本地测试时通过 MACRO_SCAN_WORKDIR 指定或自动用脚本所在目录
_script_dir = Path(__file__).resolve().parent
WORKDIR = Path(os.environ.get("MACRO_SCAN_WORKDIR", str(_script_dir)))
CHANGELOG = WORKDIR.parent / "TuiYan_CHANGELOG.md" if (WORKDIR.parent / "TuiYan_CHANGELOG.md").exists() else WORKDIR / "TuiYan_CHANGELOG.md"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
DRIFT_THRESHOLD_MINUTES = 30


def _push(title: str, message: str):
    if not NTFY_TOPIC:
        print(f"[drift] ntfy未配置，跳过推送：{title} / {message}")
        return
    try:
        requests.put(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            json={"topic": NTFY_TOPIC, "title": title, "message": message},
            timeout=10,
            proxies=None,
        )
    except Exception as e:
        print(f"[drift] ntfy推送失败：{e}")


def main():
    if not CHANGELOG.exists():
        print(f"[drift] CHANGELOG 不存在：{CHANGELOG}，跳过")
        return 0

    changelog_mtime = CHANGELOG.stat().st_mtime
    py_files = list(WORKDIR.glob("*.py"))

    # 找出比 CHANGELOG 新超过阈值的 py 文件
    threshold_secs = DRIFT_THRESHOLD_MINUTES * 60
    drifted = []
    for f in py_files:
        delta = f.stat().st_mtime - changelog_mtime
        if delta > threshold_secs:
            drifted.append((f.name, delta))

    if not drifted:
        print(f"[drift] 无漂移，CHANGELOG 已是最新（检查了 {len(py_files)} 个 .py 文件）")
        return 0

    # 按漂移时间排序，最大的在前
    drifted.sort(key=lambda x: -x[1])
    lines = []
    for name, delta in drifted[:5]:  # 最多列出5个
        mins = int(delta // 60)
        lines.append(f"  {name}（比CHANGELOG新 {mins} 分钟）")

    summary = "\n".join(lines)
    total = len(drifted)
    msg = (
        f"共 {total} 个 .py 文件比 TuiYan_CHANGELOG.md 新超过 {DRIFT_THRESHOLD_MINUTES} 分钟，"
        f"疑似直接改了运行区未更新文档：\n{summary}\n\n"
        f"请回源码区补齐 CHANGELOG + VERSION 后走 git commit 流程。"
    )
    print(f"[drift] ⚠️ 发现漂移：{total} 个文件\n{summary}")
    _push("⚠️ 推演系统文档漂移告警", msg)
    return 1


if __name__ == "__main__":
    sys.exit(main())
