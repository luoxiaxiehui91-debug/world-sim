"""pre-commit hook：检查联动文档是否已随代码一起 staged。"""
import subprocess
import sys

# 联动矩阵：改了左边的文件，右边的文档必须在 staged 中
MATRIX = [
    # (触发文件匹配, [必须同时 staged 的文档])
    (lambda f: f.startswith("核心代码/") and f.endswith(".py"),
     ["TuiYan_CHANGELOG.md", "VERSION"]),
    (lambda f: f == "核心代码/scheduler.py",
     ["INDEX.md"]),
    (lambda f: f == "核心代码/hybrid_llm.py",
     ["INDEX.md"]),
    (lambda f: f == "核心代码/ntfy_listener.py",
     ["INDEX.md"]),
    (lambda f: f in ("Dockerfile", "entrypoint.sh"),
     ["INDEX.md"]),
    (lambda f: f == "核心代码/geo_risk_vector.py",
     ["AGENTS.md", "世界推演系统_人类说明文档.md"]),
    (lambda f: f == "核心代码/regime_detector.py",
     ["AGENTS.md"]),
    (lambda f: f in ("核心代码/hypothesis_engine.py", "核心代码/hypothesis_config.py"),
     ["AGENTS.md"]),
    (lambda f: f == "核心代码/scorer.py",
     ["AGENTS.md"]),
    (lambda f: f in ("核心代码/situation_tracker.py", "核心代码/situation_detector.py"),
     ["世界推演系统_人类说明文档.md"]),
]

# 新增或删除 py 文件时需要更新 FILE_MANIFEST
PY_ADD_DELETE_DOCS = ["docs/FILE_MANIFEST.md"]


def get_staged_files():
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "diff", "--cached",
         "--name-only", "--diff-filter=ACDMRT"],
        capture_output=True, text=True, encoding="utf-8"
    )
    return set(f for f in result.stdout.strip().splitlines() if f)


def get_staged_added_deleted_py():
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "diff", "--cached",
         "--name-only", "--diff-filter=AD"],
        capture_output=True, text=True, encoding="utf-8"
    )
    return [f for f in result.stdout.strip().splitlines()
            if f.startswith("核心代码/") and f.endswith(".py")]


def main():
    staged = get_staged_files()
    if not staged:
        return 0

    missing = {}  # doc -> [触发它的文件]

    # 检查联动矩阵
    for match_fn, required_docs in MATRIX:
        triggered_by = [f for f in staged if match_fn(f)]
        if not triggered_by:
            continue
        for doc in required_docs:
            if doc not in staged:
                missing.setdefault(doc, []).extend(triggered_by)

    # 检查新增/删除 py 文件
    add_del = get_staged_added_deleted_py()
    if add_del:
        for doc in PY_ADD_DELETE_DOCS:
            if doc not in staged:
                missing.setdefault(doc, []).extend(add_del)

    if not missing:
        return 0

    print("\n✗ 联动文档未更新，请补充后重新 git add：\n")
    for doc, triggers in missing.items():
        trigger_str = ", ".join(set(triggers))
        print(f"  {trigger_str} 已改 → {doc} 未在 staged 中")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
