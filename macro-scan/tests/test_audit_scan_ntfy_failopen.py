#!/usr/bin/env python3
"""审计回归测试 #10/#11 (HIGH security)：ntfy_listener.parse_command 的 fail-open 缺陷。

背景（审计发现）：
  parse_command 在 NTFY_CMD_SECRET 未设（空字符串）时，跳过整个密钥校验分支
  （`if NTFY_CMD_SECRET:` 为假），直接把任意公共主题消息解析为可执行命令。
  这是 fail-open：任何人在公共 ntfy.sh 主题发一条消息即可触发指令。
  安全立场应为 fail-closed —— 未配置密钥时必须【拒绝】命令（返回 None）。

当前代码存在该 bug，因此本测试断言【正确/期望】的 fail-closed 行为，
对当前代码会失败，用 xfail(strict=True) 标注。
  - bug 存在时 → xfailed（CI 绿）
  - bug 修复后 → xpassed → strict 触发失败 → 强制摘除标记，转为活体守卫。
"""
import os
import sys

import pytest

# 将「核心代码」目录加入 sys.path（与本模块现有测试一致的注入方式）
_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.abspath(os.path.join(_HERE, "..", "核心代码"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import ntfy_listener  # noqa: E402


@pytest.mark.xfail(
    strict=True,
    reason="审计发现 #10/#11 HIGH: NTFY_CMD_SECRET 未设时 parse_command fail-open 接受任意命令，应 fail-closed 拒绝",
)
def test_parse_command_fail_closed_when_secret_unset(monkeypatch):
    """未配置密钥时 parse_command 应拒绝命令（返回 None），而非接受。"""
    # 强制模拟“密钥未配置”场景（模块级常量，直接 monkeypatch 覆盖）
    monkeypatch.setattr(ntfy_listener, "NTFY_CMD_SECRET", "")

    result = ntfy_listener.parse_command("status")

    # 期望的安全行为：无密钥配置 → fail-closed → 拒绝，返回 None。
    # 当前实现会返回 ("status", []) —— 接受了未鉴权命令（fail-open）。
    assert result is None, (
        "NTFY_CMD_SECRET 未设时应拒绝命令(fail-closed)，"
        "但 parse_command 接受并解析了它"
    )
