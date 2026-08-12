#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
world-sim 文档链接断链检查器（防漂移手动体检工具；可选接 pre-commit 作自动门禁）。
- 遍历 repo 内所有 .md（跳过 data/.git/dist/node_modules/__pycache__/archive/知识库）
- 提取 markdown 链接 [text](target)，解析相对路径，校验目标文件是否存在
- 退出码 0=无断链，1=有断链
- 用法：python check-doc-links.py [repo_root]   例：python docs/check-doc-links.py S:/world-sim
- 纪律：任何文档增删/移动/改名后手动跑一次，确认零新增断链再提交（个人仓库不接自动拦截）
"""
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
SKIP_DIRS = {"data", ".git", "node_modules", "dist", "__pycache__", "archive", "知识库"}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
BAD_TOKENS = [
    r"S:\docs\INDEX.md",
    "S:/docs/INDEX.md",
]


def main():
    broken = []
    warned = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            try:
                txt = open(p, encoding="utf-8").read()
            except Exception:
                continue
            for m in LINK_RE.finditer(txt):
                tgt = m.group(1).strip()
                if tgt.startswith(("#", "http://", "https://", "mailto:")):
                    continue
                if any(tgt == bt or tgt.startswith(bt) for bt in BAD_TOKENS):
                    warned.append((p, tgt))
                    continue
                if tgt.startswith("/"):
                    cand = os.path.normpath(os.path.join(ROOT, tgt.lstrip("/")))
                else:
                    cand = os.path.normpath(os.path.join(os.path.dirname(p), tgt))
                base = cand.split("#")[0]
                if base and not os.path.exists(base):
                    broken.append((p, tgt))

    rel = lambda x: os.path.relpath(x, ROOT)
    print(f"扫描根: {os.path.abspath(ROOT)}")
    print(f"断链数量: {len(broken)}")
    for p, t in broken:
        print(f"  ✗ {rel(p)}  ->  {t}")
    print(f"遗留坏令牌: {len(warned)}")
    for p, t in warned:
        print(f"  ⚠ {rel(p)}  ->  {t}")
    if not broken and not warned:
        print("✓ 无断链、无遗留坏令牌")
    sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
