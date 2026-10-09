#!/usr/bin/env python3
"""pre-commit 联动文档检查（2026-10-09 修复版）。

背景：本脚本属「文档同步保障机制」（2026-06-29 建立）。原版判据为旧仓库
结构（独立 macro-scan 仓库：`核心代码/`、`TuiYan_CHANGELOG.md`）且未接入
现役 hook 体系（core.hooksPath=.gethooks），从未生效。2026-10-09 重写：
  - 路径适配 monorepo（world-sim/macro-scan/…）
  - 判据收敛为「底线矩阵」（与项目实际惯例一致，其余联动项为人工 checklist）：
      ★ 任何 macro-scan/核心代码/*.py 变更 → 须同步 CHANGELOG.md + VERSION
      ★ 新增/删除 核心代码/*.py → 还须同步 docs/FILE_MANIFEST.md
  - 接入方式：.gethooks/pre-commit 第 3 关（git config core.hooksPath .gethooks）

用法：无需参数，在仓库根运行（pre-commit hook 或手动排障）。
返回：0 = 通过；1 = 有缺失（打印明细）。
"""
import subprocess
import sys

CODE_PREFIX = "macro-scan/核心代码/"
CHANGELOG = "macro-scan/CHANGELOG.md"
VERSION = "macro-scan/VERSION"
FILE_MANIFEST = "macro-scan/docs/FILE_MANIFEST.md"


def get_staged_files() -> set:
    """本次 staged 的文件集合（相对仓库根路径）。"""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "diff", "--cached",
         "--name-only", "--diff-filter=ACDMRT"],
        capture_output=True, text=True, encoding="utf-8",
    )
    return set(f for f in result.stdout.strip().splitlines() if f)


def get_staged_added_deleted_py() -> list:
    """staged 中新增/删除的 核心代码 py（A/D 状态）。"""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "diff", "--cached",
         "--name-only", "--diff-filter=AD"],
        capture_output=True, text=True, encoding="utf-8",
    )
    return [f for f in result.stdout.strip().splitlines()
            if f.startswith(CODE_PREFIX) and f.endswith(".py")]


def compute_missing(staged: set, added_deleted: list) -> dict:
    """底线矩阵判据（纯函数，便于单测）。
    返回 {缺失文档: [触发它的文件, ...]}。"""
    missing = {}
    code_changed = sorted(f for f in staged
                          if f.startswith(CODE_PREFIX) and f.endswith(".py"))
    if code_changed:
        for doc in (CHANGELOG, VERSION):
            if doc not in staged:
                missing.setdefault(doc, []).extend(code_changed)
    if added_deleted:
        if FILE_MANIFEST not in staged:
            missing.setdefault(FILE_MANIFEST, []).extend(sorted(added_deleted))
    return missing


def main() -> int:
    staged = get_staged_files()
    if not staged:
        return 0

    missing = compute_missing(staged, get_staged_added_deleted_py())
    if not missing:
        return 0

    print("\n✗ 联动文档未更新，请补充后重新 git add：\n")
    for doc, triggers in missing.items():
        print(f"  {', '.join(triggers)} 已改 → {doc} 未在 staged 中")
    print("\n（判据 = macro-scan/AGENTS.md「改代码后必须同步的文档」中 ★ 两行；"
          "其余联动项为人工 checklist）\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
