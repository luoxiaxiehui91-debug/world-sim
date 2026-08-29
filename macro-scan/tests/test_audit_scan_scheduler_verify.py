#!/usr/bin/env python3
"""回归测试（审计发现 #13 HIGH correctness）：scheduler.py 的 JOBS 缺失 verify_predictions 作业。

背景：
  - entrypoint.sh 用 `python3 scheduler.py` 取代 cron，且从不启动 cron/crond
    （seccomp 阻断 cron fork）。因此只有 scheduler.py 的 JOBS 列表里的作业会自动运行。
  - crontab 里定义了 `verify_predictions.py`（每月1日 09:00，见 crontab 第 23 行），
    但 scheduler.py 的 JOBS 里没有对应作业 → 月度预测校验从未自动运行，验证闭环断裂。

期望（正确）行为：scheduler.py 的 JOBS 列表应包含一个运行 verify_predictions.py 的作业。

当前代码缺失该作业，因此本测试对当前代码会失败 → 用 xfail(strict=True) 标注。
一旦有人补上 verify_predictions 作业，测试转 xpass → strict 触发失败，
强制摘掉标记，测试转为活体守卫。

实现说明：不 import scheduler（其顶层 `from optim_config import ...` 失败会 sys.exit(1)，
会杀掉测试进程），改为读取源码并正则解析 JOBS 块。
"""
import os
import re
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

_SCHEDULER_SRC = os.path.join(_CORE, "scheduler.py")


def _extract_jobs_block(src: str) -> str:
    """截取 `JOBS = [ ... ]` 列表块的源码文本（用于避免误匹配 LOG_FILES/注释等其它区域）。"""
    m = re.search(r"^JOBS\s*=\s*\[", src, flags=re.MULTILINE)
    assert m is not None, "在 scheduler.py 中未找到 JOBS 列表定义"
    start = m.end()
    depth = 1  # 已消费开头的 '['
    i = start
    while i < len(src) and depth > 0:
        c = src[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        i += 1
    assert depth == 0, "JOBS 列表括号不闭合"
    return src[start:i]


@pytest.mark.xfail(
    strict=True,
    reason="审计发现 #13 HIGH correctness: scheduler.py 的 JOBS 缺 verify_predictions 作业，"
    "月度预测校验从未自动运行（entrypoint 不启 cron）",
)
def test_scheduler_jobs_includes_verify_predictions():
    with open(_SCHEDULER_SRC, encoding="utf-8") as f:
        src = f.read()

    jobs_block = _extract_jobs_block(src)

    # crontab 里的月度校验作业运行 verify_predictions.py；JOBS 里应有对应命令。
    assert "verify_predictions.py" in jobs_block, (
        "scheduler.py 的 JOBS 列表中缺少运行 verify_predictions.py 的作业；"
        "crontab 定义了它但 entrypoint.sh 从不启动 cron，导致月度预测校验永不自动运行"
    )
