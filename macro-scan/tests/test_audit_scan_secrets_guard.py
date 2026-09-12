#!/usr/bin/env python3
"""审计发现 #1/#3/#21 — 硬编码凭证泄露守卫（活体守卫）。

背景：多个 fetcher 曾把真实凭证硬编码进受版本控制的源文件（已修复于 2026-08-29）：
  - fetch_spacetrack.py  : os.environ.get("SPACETRACK_ID"/"SPACETRACK_PASS", <真实邮箱/密码>)
  - fetch_firms.py       : os.environ.get("FIRMS_MAP_KEY", <真实 NASA key>)
  - fetch_fred_ultra.py  : FRED_API_KEY = "<真实 FRED key>"（明文赋值，连 env 都不读）

安全期望：凭证只应来自环境变量/密钥文件，源码中不得出现真实凭证明文，
env fallback 的默认值不得是非空硬编码凭证（应为 None/空串）。

本测试纯文件读取 + 正则，不 import 任何被测模块（避免触网/依赖副作用）。
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

# 2026-09-12 删除：原「已知泄露真实凭证字面量」黑名单规则（原 _LEAKED_SECRET_LITERALS）。
# 该黑名单实际存放的是脱敏后遗留的**占位符**（REDACTED_*），而真实凭证与占位符恒不相等、
# 也不含 REDACTED 子串 → 该规则对未来任何真实凭证命中概率为 0（属「把占位符当秘密」的范畴错误）；
# 其唯一能命中的恰是占位符字面量自身，曾误报 核心代码/fetch_spacetrack.py:4 的注释致 CI 假阳性。
# 凭证防护由规则 2（env fallback 非空硬编码默认值）与规则 3（顶层明文赋值）承担。
# 溯源：questions/world-deduction/20260912-world-deduction-secrets-guard-placeholder-false-positive.md
#       CHG-20260912T101550-world-deduction

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



def test_no_hardcoded_credentials_in_source():
    violations = []
    missing = []

    for rel in _TARGET_FILES:
        abs_p = os.path.join(_ROOT, rel)
        if not os.path.exists(abs_p):
            # 知识库内容不随仓库分发（见 docs/KB_SETUP.md）。未初始化知识库时
            # 这些文件本就不存在，属预期情况，跳过而不判失败。
            missing.append(rel)
            continue
        src = _read(rel)

        # 规则 1（已知泄露字面量黑名单）已于 2026-09-12 删除：其黑名单实际是占位符（REDACTED_*），
        # 对真实凭证的检测能力恒为 0（真实凭证与占位符恒不相等），曾误报注释致 CI 失败。

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

    if missing:
        print(f"\n[info] 跳过 {len(missing)} 个未纳管文件（知识库未初始化，属预期）:")
        for m in missing:
            print(f"        {m}")

    assert not violations, "发现硬编码凭证:\n" + "\n".join(violations)
