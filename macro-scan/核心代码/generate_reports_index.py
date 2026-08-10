#!/usr/bin/env python3
"""generate_reports_index.py — 开阳报告模块数据源生成（R-1）

扫描天枢 docs/分析报告 + docs/仿真报告 目录，产出开阳可读的报告索引：
  1. 生成 data/reports_index.json（{type,title,path,updated} 清单，最新置顶）
  2. 把 .md 报告复制到 data/reports/（kaiyang nginx 容器已把 macro-scan/data
     只读挂载为 /usr/share/nginx/html/data，开阳浏览器可直接 fetch）

类型分类（按文件名关键词，缺失时按目录兜底）：
  宏观分析 / 月度简报 / 假设推演 / 演化仿真 / 预测追踪

用法：
  python3 generate_reports_index.py            # 扫描 + 复制 + 写索引
  python3 generate_reports_index.py --dry-run  # 只打印将执行的动作，不落盘

调度建议：每日报告产出后执行一次（如 07:35 晨报之后 / 20:30 晚报之后），
在 scheduler.py JOBS 中注册一行即可（见本文件末尾注释）。

依赖：仅标准库。路径常量取自 optim_config（单点，落持久卷 /workspace/data）。
"""

import datetime
import hashlib
import os
import re
import shutil
import sys

try:
    from optim_config import DATA_DIR, WORKSPACE
except Exception:  # 部署配置错误时 fail-loud（与 scheduler.py 同口径）
    print("FATAL: cannot import optim_config.WORKSPACE/DATA_DIR", flush=True)
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────────────────────────
DOCS_DIR = os.path.join(WORKSPACE, "docs")
REPORT_DIRS = ["分析报告", "仿真报告"]        # docs 下的报告源目录
OUT_JSON = os.path.join(DATA_DIR, "reports_index.json")
REPORTS_OUT = os.path.join(DATA_DIR, "reports")   # 报告副本目录（相对 DATA_BASE_URL 的 reports/）

# 类型关键词 → 类型名（顺序即优先级）。文件名同时含多类关键词时取靠前者。
TYPE_PATTERNS = [
    ("假设推演", ["假设"]),
    ("宏观分析", ["宏观分析"]),
    ("月度简报", ["月度简报"]),
    ("演化仿真", ["演化"]),
    ("预测追踪", ["预测"]),
]

# 目录兜底：某目录下的报告若关键词均不命中，按目录判定类型
DIR_FALLBACK = {
    "分析报告": "宏观分析",
    "仿真报告": "演化仿真",
}

SCHEMA_VERSION = "1.0"


def _classify_type(filename: str, source_dir: str) -> str:
    """按文件名关键词分类；全部不命中时按来源目录兜底。"""
    for type_name, keywords in TYPE_PATTERNS:
        if any(k in filename for k in keywords):
            return type_name
    return DIR_FALLBACK.get(source_dir, "宏观分析")


def _report_date(filename: str, mtime: float) -> str:
    """从文件名提取日期（优先 YYYY-MM-DD，其次紧凑 YYYYMMDD），失败回退文件 mtime。"""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def _clean_title(stem: str) -> str:
    """从文件名主干提取可读标题：去日期前缀 / 方括号标记，_ → 间隔符。"""
    s = re.sub(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_", "", stem)
    s = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", s)
    s = re.sub(r"^\[[^\]]*\]_?", "", s)
    s = re.sub(r"_+", " · ", s).strip(" ·")
    return s or stem


def _report_id(path: str) -> str:
    return "r-" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]


def scan_reports() -> list[dict]:
    """扫描两个报告目录，返回报告元数据列表（含源路径与目标文件名）。"""
    reports = []
    for source_dir in REPORT_DIRS:
        src = os.path.join(DOCS_DIR, source_dir)
        if not os.path.isdir(src):
            print(f"[SKIP] 目录不存在: {src}")
            continue
        for name in sorted(os.listdir(src)):
            if not name.lower().endswith(".md"):
                continue
            src_path = os.path.join(src, name)
            if not os.path.isfile(src_path):
                continue
            mtime = os.path.getmtime(src_path)
            stem, _ext = os.path.splitext(name)
            reports.append({
                "id": _report_id(src_path),
                "type": _classify_type(name, source_dir),
                "title": _clean_title(stem),
                "filename": name,
                "src": src_path,
                "updated": _report_date(name, mtime),
                "source": source_dir,
            })
    # 最新置顶：按日期降序，同日按文件名降序（稳定、可复现）
    reports.sort(key=lambda r: (r["updated"], r["filename"]), reverse=True)
    return reports


def sync_report_files(reports: list[dict], dry_run: bool) -> int:
    """把报告 .md 复制到 data/reports/，并清理该目录下已不在清单中的旧文件。
    返回复制/清理动作计数。"""
    os.makedirs(REPORTS_OUT, exist_ok=True)
    # 目录需世界可遍历（nginx uid 101 读 .md 需经目录）
    try:
        os.chmod(REPORTS_OUT, 0o755)
    except OSError:
        pass
    moved = 0

    # 1) 复制/更新清单内报告（content 变化才重写，避免无谓 IO）
    for r in reports:
        dst = os.path.join(REPORTS_OUT, r["filename"])
        r["path"] = os.path.join("reports", r["filename"])
        same = os.path.isfile(dst) and os.path.getsize(dst) == os.path.getsize(r["src"])
        if same:
            # 已存在同尺寸文件：仍确保世界可读（源文件权限混杂，部分 660）
            if not dry_run:
                try:
                    os.chmod(dst, 0o644)
                except OSError:
                    pass
            continue
        if dry_run:
            print(f"[DRY] 复制 {r['src']} → {dst}")
        else:
            shutil.copy2(r["src"], dst)
            # nginx 容器 worker 以 uid 101 运行，源文件权限混杂（部分 660）
            # 复制后强制世界可读，否则 :8080 对 .md 返回 403（kaiyang 只读挂载）
            os.chmod(dst, 0o644)
            print(f"[OK] 复制 {r['filename']} → data/reports/")
        moved += 1

    # 2) 清理不在清单中的旧 .md（保持 data/reports/ 与索引一致）
    wanted = {r["filename"] for r in reports}
    for name in sorted(os.listdir(REPORTS_OUT)):
        if not name.lower().endswith(".md"):
            continue
        if name in wanted:
            continue
        if dry_run:
            print(f"[DRY] 清理旧文件 data/reports/{name}")
        else:
            os.remove(os.path.join(REPORTS_OUT, name))
            print(f"[OK] 清理旧文件 data/reports/{name}")
        moved += 1
    return moved


def write_index(reports: list[dict], dry_run: bool) -> None:
    """生成 data/reports_index.json。仅输出契约字段（不含容器内部路径）。"""
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    payload = []
    for r in reports:
        # 契约字段：id/type/title/filename/path/updated（剥离 src/source 内部字段，
        # 遵守 DATA_CONTRACT「禁止绝对路径进入数据契约」口径）
        payload.append({
            "id": r["id"],
            "type": r["type"],
            "title": r["title"],
            "filename": r["filename"],
            "path": r["path"],
            "updated": r["updated"],
        })
    index = {
        "schema_version": SCHEMA_VERSION,
        "updated": now,
        "reports": payload,
    }
    if dry_run:
        print(f"[DRY] 写 {OUT_JSON}（{len(reports)} 条）")
        return
    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUT_JSON)
    print(f"[OK] 写 {OUT_JSON}（{len(reports)} 条）")


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    reports = scan_reports()
    if not reports:
        print("[WARN] 未发现任何 .md 报告，跳过复制与索引写入（保持现状）")
        return
    # 各类型计数
    by_type: dict[str, int] = {}
    for r in reports:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    print(f"[INFO] 扫描到 {len(reports)} 份报告：{by_type}")

    moved = sync_report_files(reports, dry_run)
    write_index(reports, dry_run)
    print(f"[INFO] 完成：报告 {len(reports)} 份，文件动作 {moved} 项"
          + ("（dry-run，未落盘）" if dry_run else ""))


if __name__ == "__main__":
    import json  # noqa: F401  (延迟导入，避免 import 阶段副作用)
    main()
