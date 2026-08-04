"""compute_fci.py — L1 金融条件指数（FCI）

P0-A 恢复占位（2026-08-04）：原 3342 行源码被 deploy.sh 的 rsync --delete 抹除（未 git add），
幸存 pyc（compute_fci.cpython-311.pyc，mtime 07-31）与容器 Python 3.11 字节码版本匹配、可完整运行
（sanity PASS：PC1 42.3% / NFCI 水平相关 +0.829 / 区间推进到 08-03）。

本文件为薄包装：加载 __pycache__ 下 pyc 并转发 main()。源码恢复（pycdc 真版需 C++ 编译，
NAS 无 gcc/cmake；反汇编文本已备份 .workbuddy/research/evidence/_compute_fci_disasm.txt）列为
后续开放项，不影响生产功能。
"""
import importlib.util
import os
import sys

_PYC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__pycache__", "compute_fci.cpython-311.pyc")

def _load():
    spec = importlib.util.spec_from_file_location("compute_fci_impl", _PYC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_mod = None

def main():
    global _mod
    _mod = _load()
    _mod.main()

if __name__ == "__main__":
    main()
