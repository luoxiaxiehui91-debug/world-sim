#!/usr/bin/env python3
"""
fetch_bdi.py — 波罗的海干散货指数（BDI / Baltic Dry Index，本地历史 CSV 源）

v3.6.0 起：实时拉取（Stooq OpenResty 验 TLS/HTTP2 指纹 + Playwright Chromium
下载不可达）在本环境不可行，改为读取运维预置的本地历史 CSV：data/bdi_history.csv。

CSV 约定（首行表头，列名灵活自动识别）：
  - 日期列：date / Date / 日期 / 时间
  - 数值列：bdi / BDI / close / Close / index / Index / value / 收盘 / 指数
  - 兼容 Stooq 导出格式：Date,Open,High,Low,Close（取 Close）
  - 无表头兜底：第 1 列日期、最后一列数值

典型获取方式（在 Windows 本机正常浏览器操作，绕开容器出网限制）：
  打开 https://stooq.com/q/d/l/?s=bmd&i=d → 浏览器自动过 PoW → 下载 bmd.csv
  → 重命名为 bdi_history.csv → 放入 <仓库根>/macro-scan/data/

输出契约：data/bdi.json
  {
    "status":      "ok",
    "bdi_index":   float,                       # 末行数值
    "series":      [ {date, value}, ... ],      # 全量（按日期升序）
    "source":      "local_csv",
    "csv_path":    "...",
    "updated":     as-of,
    "_schema_version": "1.0"
  }

调度：scheduler.py 06:25（日频）。feeds_grv=False，仅落盘供下游消费。
缺失 CSV 时 collect 返回 None → 保留上次良值（首跑写 unavailable 标记）。
"""
import os
import io
import csv
import logging

from fetcher_base import FetcherBase, Status

# ── 配置回退（统一取代重复 ImportError 块）────────────────────
_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR"],
    {"DATA_DIR": FetcherBase.default_data_dir()},
)
DATA_DIR = _cfg["DATA_DIR"]

OUTPUT_FILE = "bdi.json"
CSV_FILE = "bdi_history.csv"

DATE_HINTS = ("date", "日期", "时间")
VALUE_HINTS = ("bdi", "index", "close", "value", "收盘", "指数")


class BdiFetcher(FetcherBase):
    """BDI 采集器：读取本地预置历史 CSV（不依赖外网）。"""

    name = "bdi"
    rate_interval = 0.0
    output_file = OUTPUT_FILE
    feeds_grv = False
    schedule = "0625"

    # ── 列自动识别 ────────────────────────────────────────────
    def _resolve_columns(self, header):
        """返回 (date_idx, val_idx)。优先按列名 hint 匹配，否则兜底首列/末列。"""
        hdr = [h.strip().lower() for h in header]
        date_idx = None
        for i, h in enumerate(hdr):
            if any(k in h for k in DATE_HINTS):
                date_idx = i
                break
        val_idx = None
        for i, h in enumerate(hdr):
            if any(k in h for k in VALUE_HINTS):
                val_idx = i
                break
        if date_idx is None:
            date_idx = 0
        if val_idx is None:
            val_idx = len(hdr) - 1
        return date_idx, val_idx

    def _parse_csv(self, text):
        """解析 CSV 文本 → (bdi_index, series)。无有效数据返回 (None, None)。"""
        reader = csv.reader(io.StringIO(text.strip()))
        rows = [r for r in reader if r and any(c.strip() for c in r)]
        if len(rows) < 1:
            return None, None
        # 判断是否有表头
        first = [c.strip().lower() for c in rows[0]]
        has_header = any(
            (any(k in " ".join(first) for k in DATE_HINTS + VALUE_HINTS))
            or (c.lower() in ("date", "open", "high", "low", "close"))
            for c in first
        ) or (len(first) >= 2 and first[0] in ("date", "日期") )
        data_rows = rows[1:] if has_header else rows
        if not data_rows:
            return None, None
        date_idx, val_idx = self._resolve_columns(rows[0])
        series = []
        for r in data_rows:
            if max(date_idx, val_idx) >= len(r):
                continue
            d = r[date_idx].strip()
            try:
                v = float(r[val_idx])
            except (ValueError, TypeError):
                continue
            if not d:
                continue
            series.append({"date": d, "value": v})
        if not series:
            return None, None
        series.sort(key=lambda x: x["date"])  # 按日期升序
        return series[-1]["value"], series

    # ── 采集入口 ──────────────────────────────────────────────
    def collect(self):
        csv_path = os.path.join(self.data_dir, CSV_FILE)
        if not os.path.isfile(csv_path):
            self.logger.warning("[bdi] 本地历史 CSV 未找到：%s，跳过（保留旧值）", csv_path)
            return None
        try:
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                text = f.read()
        except Exception as e:
            self.logger.warning("[bdi] 读取 CSV 失败：%s", e)
            return None
        bdi_index, series = self._parse_csv(text)
        if bdi_index is None:
            self.logger.warning("[bdi] CSV 解析失败（无有效数据点），保留旧值")
            return None
        return {
            "status": Status.OK,
            "bdi_index": bdi_index,
            "series": series,
            "source": "local_csv",
            "csv_path": csv_path,
        }

    # _is_good 采用基类默认 ok-only（status == "ok"），无需覆写。


def main():
    fetcher = BdiFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[bdi] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == Status.OK:
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[bdi] 完成 status=ok，bdi_index={result.get('bdi_index')}，"
              f"series 点数={len(result.get('series', []))}，source={result.get('source')}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[bdi] 降级，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, result)
            print("[bdi] 降级，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
