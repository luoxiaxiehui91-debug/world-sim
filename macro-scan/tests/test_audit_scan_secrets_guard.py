#!/usr/bin/env python3
"""审计发现 #1/#3/#21 — 硬编码凭证泄露守卫（回归测试）。

背景：多个 fetcher 把真实凭证硬编码进受版本控制的源文件：
  - fetch_spacetrack.py  : os.environ.get("SPACETRACK_ID"/"SPACETRACK_PASS", <真实邮箱/密码>)
  - fetch_firms.py       : os.environ.get("FIRMS_MAP_KEY", <真实 NASA key>)
  - fetch_fred_ultra.py  : FRED_API_KEY = "<真实 FRED key>"（明文赋值，连 env 都不读）

安全期望：凭证只应来自环境变量/密钥文件，源码中不得出现真实凭证明文，
env fallback 的默认值不得是非空硬编码凭证（应为 None/空串）。

本测试纯文件读取 + 正则，不 import 任何被测模块（避免触网/依赖副作用）。
因为这是【已确认但尚未修复】的 bug，测试断言【正确/安全】行为，
对当前代码必然失败，故用 @pytest.mark.xfail(strict=True) 标注。
一旦有人清掉硬编码凭证 → xpass → strict 失败，强制摘掉标记，测试转为活体守卫。
"""
import os
import re

import pytest

# macro-scan 根目录 = tests/ 的父目录
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))

# 受审查的源文件（相对 macro-scan 根）
_TARGET_FILES = [
    os.path.join("核心代码", "fetch_spacetrack.py"),
    os.path.join("核心代码", "fetch_firms.py"),
    os.path.join("知识库", "财经知识库", "01_核心变量因果链", "fetch_fred_ultra.py"),
    os.path.join("知识库", "财经知识库", "02_核心变量因果链", "fetch_fred_ultra.py"),
]

# 已知泄露的真实凭证字面量（读真实源码确认于 2026-08-29）。
# 这些字符串绝不应出现在任何受版本控制的源文件中。
_LEAKED_SECRET_LITERALS = [
    "REDACTED_SPACETRACK_ID",              # Space-Track 账号邮箱
    "REDACTED_SPACETRACK_PASS",                   # Space-Track 密码
    "REDACTED_FIRMS_KEY",  # NASA FIRMS MAP_KEY
    "REDACTED_FRED_KEY",  # FRED API key
]

# 凭证类环境变量名（其 env.get 默认值不得是非空硬编码）
_CRED_ENV_NAMES = [
    "SPACETRACK_ID",
    "SPACETRACK_PASS",
    "FIRMS_MAP_KEY",
    "FRED_API_KEY",
]


def _read(rel_path):
    p = os.path.join(_ROOT, rel_path)
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


@pytest.mark.xfail(
    strict=True,
    reason="审计发现 #1/#3/#21: fetch_spacetrack/fetch_firms/fetch_fred_ultra "
           "把真实凭证硬编码为 env 默认值或明文，尚未修复",
)
def test_no_hardcoded_credentials_in_source():
    violations = []

    for rel in _TARGET_FILES:
        abs_p = os.path.join(_ROOT, rel)
        assert os.path.exists(abs_p), f"目标文件不存在，路径需更新: {rel}"
        src = _read(rel)

        # 1) 已知泄露凭证字面量绝不应出现
        for secret in _LEAKED_SECRET_LITERALS:
            if secret in src:
                violations.append(f"{rel}: 含已知泄露凭证字面量 <{secret[:6]}...>")

        # 2) os.environ.get("<CRED>", "<非空字面量>") 形式的硬编码默认值
        for name in _CRED_ENV_NAMES:
            pat = re.compile(
                r"os\.environ\.get\(\s*['\"]" + re.escape(name)
                + r"['\"]\s*,\s*['\"]([^'\"]+)['\"]"
            )
            for m in pat.finditer(src):
                default_val = m.group(1)
                if default_val.strip():
                    violations.append(
                        f"{rel}: os.environ.get('{name}', ...) 带非空硬编码默认值"
                    )

        # 3) 顶层明文赋值 FRED_API_KEY = "<非空字面量>"
        for name in _CRED_ENV_NAMES:
            pat2 = re.compile(
                r"^" + re.escape(name) + r"\s*=\s*['\"]([^'\"]+)['\"]",
                re.MULTILINE,
            )
            for m in pat2.finditer(src):
                if m.group(1).strip():
                    violations.append(f"{rel}: {name} 明文赋值真实凭证")

    assert not violations, "发现硬编码凭证:\n" + "\n".join(violations)
