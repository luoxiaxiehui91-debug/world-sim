"""文档自动生成工具：从代码提取结构化信息，刷新 INDEX.md 和 FILE_MANIFEST.md 对应节。

用法：
    python 核心代码/gen_docs.py --target scheduler   # 刷新 INDEX.md 定时任务表
    python 核心代码/gen_docs.py --target ntfy         # 刷新 INDEX.md ntfy指令表
    python 核心代码/gen_docs.py --target manifest     # 刷新 FILE_MANIFEST.md 模块清单
    python 核心代码/gen_docs.py --target all          # 全部刷新
"""
import argparse
import ast
import importlib.util
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CORE = ROOT / "核心代码"
INDEX_MD = ROOT / "INDEX.md"
MANIFEST_MD = ROOT / "docs" / "FILE_MANIFEST.md"

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def replace_section(filepath: Path, section_header: str, new_table: str):
    """替换 md 文件中指定节的表格（## 标题 后的连续表格行）。"""
    content = filepath.read_text(encoding="utf-8")
    # 找到节标题位置
    header_pattern = rf"## {re.escape(section_header)}\n"
    m_header = re.search(header_pattern, content)
    if not m_header:
        print(f"  警告：未找到节 '## {section_header}'，跳过")
        return
    # 从节标题之后找第一个连续表格块（包含表头+分隔行+数据行）
    after = content[m_header.end():]
    m_table = re.search(r"((?:\|[^\n]*\n)+)", after)
    if not m_table:
        print(f"  警告：节 '## {section_header}' 下未找到表格，跳过")
        return
    table_start = m_header.end() + m_table.start()
    table_end = m_header.end() + m_table.end()
    new_content = content[:table_start] + new_table + content[table_end:]
    filepath.write_text(new_content, encoding="utf-8")
    print(f"  ✓ 已更新 {filepath.name} 中的 '{section_header}' 节")


# ── 1. scheduler → INDEX.md 定时任务表 ───────────────────────────────────────

WEEKDAY_MAP = {"1-7": "每日", "1-5": "工作日", "5": "周五", "1": "周一"}

def gen_scheduler_table():
    spec = importlib.util.spec_from_file_location("scheduler", CORE / "scheduler.py")
    mod = importlib.util.module_from_spec(spec)
    # 只执行顶层赋值，跳过可能报错的函数调用
    src = (CORE / "scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    jobs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "JOBS":
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Tuple) and len(elt.elts) >= 5:
                            name = ast.literal_eval(elt.elts[0])
                            hhmm = ast.literal_eval(elt.elts[1])
                            weekdays = ast.literal_eval(elt.elts[2])
                            dom = ast.literal_eval(elt.elts[3])
                            cmd_parts = [ast.literal_eval(e) for e in elt.elts[4].elts
                                         if isinstance(e, ast.Constant)]
                            script = next((p for p in cmd_parts if p.endswith(".py")), "")
                            freq = "每月1日" if dom == 1 else WEEKDAY_MAP.get(weekdays, weekdays)
                            time_str = f"{hhmm[:2]}:{hhmm[2:]}"
                            jobs.append((name, time_str, freq, script))

    header = "| 任务 | 时间 | 频率 | 命令 | 状态 |\n|:---|:---|:---|:---|:---|\n"
    rows = "".join(f"| {n} | {t} | {f} | `{s}` | ✅ |\n" for n, t, f, s in jobs)
    table = header + rows

    replace_section(INDEX_MD, "定时任务（scheduler.py）", table)


# ── 2. ntfy_listener → INDEX.md ntfy指令速查表 ────────────────────────────────

def gen_ntfy_table():
    src = (CORE / "ntfy_listener.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    rows = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("cmd_"):
            docstring = ast.get_docstring(node)
            if not docstring:
                continue
            cmd = node.name[4:]  # 去掉 cmd_ 前缀
            desc = docstring.split("。")[0].split("：")[0].strip()
            rows.append((cmd, desc))

    header = "| 指令 | 效果 |\n|:-----|:-----|\n"
    table_rows = "".join(f"| `1900 {cmd}` | {desc} |\n" for cmd, desc in rows)
    table = header + table_rows

    replace_section(INDEX_MD, "ntfy 指令速查", table)


def replace_subsection(filepath: Path, subsection_header: str, new_table: str):
    """替换 md 文件中指定三级子节（### 标题）的表格。"""
    content = filepath.read_text(encoding="utf-8")
    header_pattern = rf"### {re.escape(subsection_header)}\n"
    m_header = re.search(header_pattern, content)
    if not m_header:
        print(f"  警告：未找到子节 '### {subsection_header}'，跳过")
        return
    after = content[m_header.end():]
    m_table = re.search(r"((?:\|[^\n]*\n)+)", after)
    if not m_table:
        print(f"  警告：子节 '### {subsection_header}' 下未找到表格，跳过")
        return
    table_start = m_header.end() + m_table.start()
    table_end = m_header.end() + m_table.end()
    new_content = content[:table_start] + new_table + content[table_end:]
    filepath.write_text(new_content, encoding="utf-8")
    print(f"  ✓ 已更新 {filepath.name} 中的 '{subsection_header}' 子节")


# ── 3. 核心代码/ → FILE_MANIFEST.md 离线工具子节 ─────────────────────────────

OFFLINE_TOOLS = {
    "build_rag_index.py": ("重建 ChromaDB 向量索引", "docker exec ... python3 build_rag_index.py"),
    "build_report_data.py": ("知识库数据采集", "手动执行"),
    "diag_p0.py": ("P0 阶段诊断工具", "手动执行"),
    "check_doc_sync.py": ("pre-commit 联动文档检查脚本", "自动（pre-commit hook）"),
    "check_doc_drift.py": ("文档漂移巡检，发现运行区 py 比 CHANGELOG 新则 ntfy 告警", "自动（scheduler 每日 10:00）"),
    "gen_docs.py": ("从代码生成 INDEX.md/FILE_MANIFEST.md 对应节", "python 核心代码/gen_docs.py --target all"),
}


def gen_manifest_table():
    header = "| 文件 | 职责 | 调用方式 |\n|:---|:---|:---|\n"
    rows = "".join(
        f"| `{name}` | {desc} | {how} |\n"
        for name, (desc, how) in OFFLINE_TOOLS.items()
    )
    table = header + rows
    replace_subsection(MANIFEST_MD, "离线工具（不在自动调度中）", table)


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="刷新自动生成的文档节")
    parser.add_argument("--target", choices=["scheduler", "ntfy", "manifest", "all"],
                        required=True)
    args = parser.parse_args()

    targets = ["scheduler", "ntfy", "manifest"] if args.target == "all" else [args.target]

    for t in targets:
        print(f"\n→ 生成 {t}...")
        if t == "scheduler":
            gen_scheduler_table()
        elif t == "ntfy":
            gen_ntfy_table()
        elif t == "manifest":
            gen_manifest_table()

    print("\n完成。请检查修改内容后 git add 对应文档。")


if __name__ == "__main__":
    main()
