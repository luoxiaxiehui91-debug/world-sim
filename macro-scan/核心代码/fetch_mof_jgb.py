#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_mof_jgb.py — 日本 10Y 国债收益率日频源（日本财务省 MOF）

背景：FRED 上 `IRLTLT01JPM156N`（日本 10Y）仅有 OECD **月/季/年** 系列，无日频版本，
官方最新长期滞后（2026-09 时仍停在 2026-06-01，滞后约 99 天），导致开阳日债 feed
与探针新鲜度告警长期无解（question 20260903-fred-japan-jgb-lag-probe-spam 解法 A）。

MOF 提供两个公开 CSV（无鉴权 / 无 PoW），入口页：
  https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm
  - jgbcme.csv（Current Data）            —— 仅当月
  - historical/jgbcme_all.csv（1974~）    —— 全量日频（约 1.2MB / 13k 行）
二者互补（all 覆盖到上月末，current 覆盖当月），故**每次都拉两个并取并集**，
同日期以 current 为准。顺便规避 current 月度文件跨月重置导致的丢数风险。

写入策略：
  - 只补本地 CSV 末行日期**之后**的新日期（首次运行即补 FRED 末行 2026-06-01 之后），
    既有 FRED 月度历史保持不动（避免改写历史影响回测/窗口语义）。
    ⇒ 口径切换点 = 本地 CSV 原末行的次日（见 CHANGELOG v3.8.39）。
  - 按 date 去重（keep=last）+ 排序 + tmp→os.replace 原子写回
    （data 为目录挂载；红线：跨容器文件契约禁单文件 bind + os.replace）。
  - 失败（网络/解析/无有效行）→ 打印 WARN/ERROR 并非零退出，**保留上次成功值，不写 0**
    （吸取 spacetrack 把失败粉饰成 ok+全 0 的教训）。

用法：
  python3 fetch_mof_jgb.py            # 采集并写回
  python3 fetch_mof_jgb.py --dry-run  # 只打印将要新增的行，不写盘
  python3 fetch_mof_jgb.py --check    # 只打印本地 CSV 现状
"""

import csv
import os
import re
import shutil
import sys
from datetime import datetime

import requests

# ── 配置 ────────────────────────────────────────────────────────────────────

SERIES_ID = "IRLTLT01JPM156N"          # 沿用 FRED 序列名，下游零改动
TENOR = "10Y"                          # 按表头名定位，禁硬编码列下标

MOF_BASE = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate"
URL_ALL = f"{MOF_BASE}/historical/jgbcme_all.csv"
URL_CUR = f"{MOF_BASE}/jgbcme.csv"

# 脚本所在目录的上级 = 项目根目录（与 fetch_fred_history.py / fetch_gscpi.py 同款）
BASE_DIR = os.environ.get("OPENCLAW_WORKSPACE",
           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST_DIR = os.path.join(BASE_DIR, "data", "fred_history")
OUT_CSV = os.path.join(HIST_DIR, f"{SERIES_ID}.csv")

# 代理（参照 fetch_firms.py / fetch_gscpi.py：optim_config.PROXY_URL > env OUTBOUND_PROXY）
try:
    from optim_config import PROXY_URL
except ImportError:
    PROXY_URL = os.environ.get("OUTBOUND_PROXY", "")
PROXY_URL = os.environ.get("OUTBOUND_PROXY", "") or PROXY_URL
_PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

TIMEOUT = (15, 60)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

_DATE_RE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")


# ── 下载 / 解析 ─────────────────────────────────────────────────────────────

def _download(url: str, label: str) -> str | None:
    """直连优先，失败回退代理；仍失败返回 None（不抛，交调用方降级）。"""
    for attempt, proxies in ((1, None), (2, _PROXIES)):
        try:
            r = requests.get(url, timeout=TIMEOUT,
                             headers={"User-Agent": UA}, proxies=proxies)
            if r.status_code != 200:
                print(f"[WARN] MOF {label}: HTTP {r.status_code}")
                continue
            r.encoding = r.encoding or "utf-8"
            return r.text
        except Exception as e:
            print(f"[WARN] MOF {label}: {'直连' if attempt == 1 else '代理'}失败 {e}")
    return None


def _parse(text: str, label: str) -> dict:
    """
    解析 MOF CSV → {YYYY-MM-DD: value}
    - 首行是标题行（如 "Interest Rate (September 2026)"），**次行才是列头**
    - 日期 `YYYY/M/D` 无前导零 → 规整为 `YYYY-MM-DD`
    - 休市日空行 / 值为 `-` 或空 → 跳过
    """
    out: dict = {}
    header = None
    col = None
    for row in csv.reader(text.splitlines()):
        if not row or not row[0].strip():
            continue
        if header is None:
            if row[0].strip() == "Date" and TENOR in [c.strip() for c in row]:
                header = [c.strip() for c in row]
                col = header.index(TENOR)
            continue
        m = _DATE_RE.match(row[0].strip())
        if not m or col is None or col >= len(row):
            continue
        raw = row[col].strip()
        if raw in ("", "-"):
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        y, mo, d = (int(x) for x in m.groups())
        out[f"{y:04d}-{mo:02d}-{d:02d}"] = val
    if header is None:
        raise RuntimeError(f"MOF {label}: 未找到含 '{TENOR}' 的列头，结构可能已变更")
    print(f"[MOF] {label}: 解析 {len(out)} 行")
    return out


# ── 本地 CSV 读写 ───────────────────────────────────────────────────────────

def _load_local() -> dict:
    """读本地 CSV → {date: value_str}；文件不存在返回 {}。"""
    if not os.path.exists(OUT_CSV):
        return {}
    out: dict = {}
    with open(OUT_CSV, "r", encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.reader(f)):
            if i == 0 or not row or not row[0].strip():
                continue
            out[row[0].strip()] = row[1].strip() if len(row) > 1 else ""
    return out


def _write_local(rows: dict) -> None:
    """原子写回：备份 → tmp 写 → os.replace。"""
    os.makedirs(HIST_DIR, exist_ok=True)
    if os.path.exists(OUT_CSV):
        bak = f"{OUT_CSV}.bak-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
        shutil.copy2(OUT_CSV, bak)
        print(f"[MOF] 已备份 {os.path.basename(bak)}")
    tmp = OUT_CSV + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for d in sorted(rows):
            w.writerow([d, rows[d]])
    os.replace(tmp, OUT_CSV)


# ── 主流程 ──────────────────────────────────────────────────────────────────

def fetch_and_save(dry_run: bool = False) -> int:
    remote: dict = {}
    for url, label in ((URL_ALL, "all"), (URL_CUR, "current")):
        text = _download(url, label)
        if text:
            remote.update(_parse(text, label))   # current 后更新 → 覆盖 all 同日期
        else:
            print(f"[WARN] MOF {label} 拉取失败，跳过（另一个源仍可用则继续）")
    if not remote:
        raise RuntimeError("MOF 两个源均拉取失败，保留上次成功值")

    local = _load_local()
    cutoff = max(local) if local else None
    new = {d: v for d, v in remote.items() if cutoff is None or d > cutoff}
    new = dict(sorted(new.items()))

    print(f"[MOF] 本地 {len(local)} 行，末行 {cutoff or '（无）'}；"
          f"远端 {len(remote)} 行（最新 {max(remote)}）；新增 {len(new)} 行")
    if not new:
        print("[SKIP] 无新数据（上游尚未更新）")
        return 0

    first, last = min(new), max(new)
    print(f"[MOF] 新增区间 {first} ~ {last}，末值 {new[last]}")

    if dry_run:
        print("[DRY-RUN] 未写盘")
        return 0

    merged = dict(local)
    merged.update(new)
    _write_local(merged)
    print(f"[MOF] 写入 {OUT_CSV}：{len(local)} → {len(merged)} 行，末行 {max(merged)}={merged[max(merged)]}")
    return 0


def check_existing() -> int:
    local = _load_local()
    if not local:
        print("[CHECK] 本地 CSV 不存在")
        return 1
    last = max(local)
    print(f"[CHECK] {SERIES_ID} 尾行 {last} = {local[last]}（本地 {len(local)} 行）")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="MOF 日本国债日频收益率采集（10Y → data/fred_history/IRLTLT01JPM156N.csv）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要新增的行，不写盘")
    ap.add_argument("--check", action="store_true", help="仅校验本地 CSV，不下载")
    args = ap.parse_args()
    try:
        if args.check:
            sys.exit(check_existing())
        sys.exit(fetch_and_save(dry_run=args.dry_run))
    except Exception as e:
        print(f"[ERROR] fetch_mof_jgb: {e}")
        sys.exit(1)
