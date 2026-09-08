# -*- coding: utf-8 -*-
"""reports_ttl_cleanup.py — 报告文件 TTL 清理（P3）

扫描报告源目录 docs/分析报告 + docs/仿真报告，删除超过保留期的 .md 报告，
防止报告目录与开阳报告索引（data/reports_index.json）无限膨胀。

背景：宏观分析每工作日跑 3 次，每次末尾产出一份展望简报（us/china/both），
此前报告目录无清理机制，文件数随天数线性增长（2026-09-08 实测 190 份源报告）。

设计（骨架与 news_ttl_cleanup.py 同源）：
  - TTL_DAYS 默认 90 天（与 news.articles TTL 同口径），环境变量 REPORTS_TTL_DAYS 可覆盖
  - 日期判定：文件名内日期优先（YYYY-MM-DD，其次紧凑 YYYYMMDD），无日期回退文件 mtime
  - 只删源目录；副本 data/reports/ 与索引由已注册的 reports_index 任务（0735/2035）自行同步
  - --dry-run 只打印不删除；异常仅记日志不阻断
  - 由 scheduler 每日 03:10 触发（错开 news_ttl_cleanup 03:00）

用法：
  python3 reports_ttl_cleanup.py            # 执行清理
  python3 reports_ttl_cleanup.py --dry-run  # 只打印将删除的清单
"""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from optim_config import WORKSPACE
except Exception:  # 与 scheduler.py / generate_reports_index.py 同口径 fail-loud
    print("FATAL: cannot import optim_config.WORKSPACE", flush=True)
    sys.exit(1)

TTL_DAYS = int(os.environ.get("REPORTS_TTL_DAYS", "90"))
REPORT_DIRS = ["分析报告", "仿真报告"]

_TAG = "[reports_ttl_cleanup]"


def _report_date(name: str, mtime: float) -> datetime.date:
    """文件名日期优先（YYYY-MM-DD / YYYYMMDD），失败回退 mtime。"""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", name)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return datetime.datetime.fromtimestamp(mtime).date()


def run(dry_run: bool = False) -> int:
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=TTL_DAYS)
    print(f"{_TAG} 开始清理，保留最近 {TTL_DAYS} 天（早于 {cutoff.isoformat()} 删除）"
          + ("，dry-run 未落盘" if dry_run else ""), flush=True)

    total = 0
    for d in REPORT_DIRS:
        src = os.path.join(WORKSPACE, "docs", d)
        if not os.path.isdir(src):
            print(f"{_TAG} [SKIP] 目录不存在: {src}", flush=True)
            continue
        stale = []
        for name in sorted(os.listdir(src)):
            if not name.lower().endswith(".md"):
                continue
            path = os.path.join(src, name)
            if not os.path.isfile(path):
                continue
            if _report_date(name, os.path.getmtime(path)) < cutoff:
                stale.append((name, path))
        print(f"{_TAG} {d}：共 {len([n for n in os.listdir(src) if n.lower().endswith('.md')])} 份报告，"
              f"超期 {len(stale)} 份", flush=True)
        for name, path in stale:
            if dry_run:
                print(f"{_TAG} [DRY] 将删除 {d}/{name}", flush=True)
            else:
                try:
                    os.remove(path)
                    print(f"{_TAG} [OK] 删除 {d}/{name}", flush=True)
                except Exception as e:
                    print(f"{_TAG} [WARN] 删除失败 {d}/{name}：{e}", flush=True)
                    continue
            total += 1

    print(f"{_TAG} 完成，超期报告 {total} 份（dry-run={dry_run}）。"
          f"副本 data/reports/ 与索引由 reports_index 任务（0735/2035）同步。", flush=True)
    return total


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
