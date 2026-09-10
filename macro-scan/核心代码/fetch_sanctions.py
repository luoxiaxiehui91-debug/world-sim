#!/usr/bin/env python3
"""
fetch_sanctions.py — 制裁风险信号（OpenSanctions bulk data，方案 B）

方案 B（已拍板）：
  保留 OpenSanctions 的 bulk data（原始数据文件）做轻量国别制裁暴露聚合，
  彻底划掉自托管检索容器（该容器需 8GB RAM + 60GB 盘，价值在模糊人名筛查——
  本系统只做国别暴露聚合，用不上）。

数据来源：OpenSanctions「sanctions」数据集（CC BY-NC，非商用内部系统不触发授权约束）。
  bulk data 发布地址（官方「latest」重定向直取最新发布，免去解析 run 时间戳）：
    https://data.opensanctions.org/datasets/latest/sanctions/targets.simple.csv
  说明：OpenSanctions 实际发布的简化表格式文件是 targets.simple.csv（不是 entities.csv，
       官方未提供 entities.csv）。该 CSV 含 `countries` 列，值为 ISO-2 国家代码、
       以 `;` 分隔，内容是「居住国 / 国籍 / 公司注册地」等关联国家。

输出契约：data/sanctions_risk.json
  {
    "status":                "ok" | "unavailable",
    "global_sanctions_risk": 0–100 全局制裁暴露基线（GRV 直接消费此值）,
    "by_country": { ISO3: {"count": int, "risk": 0–100}, ... },  # 20 个跟踪国国别明细,
    "total_sanctioned":      int,    # 全数据集被制裁目标实体总数（近似）,
    "source":                "opensanctions_bulk",
    "dataset":               "sanctions",
    "cache_used":            bool,   # 本次是否使用了本地缓存（未重新下载）,
    "updated":               "as-of 时间戳（fetcher_base.save_json 注入）"
  }
  geo_risk_vector.py 直接读 sanctions_risk.json 的 global_sanctions_risk 填 grv_latest.json 的 sanctions_risk。

降级：下载 / 解析失败 → status=unavailable；若本地有上次良值则保留、不覆盖、绝不 crash。
缓存：下载文件落本地缓存（data/sanctions_cache/），仅当缓存 >7 天陈旧才重下
      （制裁存量变化慢，避免每日重抓数百 MB）。
调度：scheduler.py 06:05（grv_update 06:10 前完成）。

─────────────────────────────────────────────────────────────────────────
sanctions_risk 公式说明（务必可读）
─────────────────────────────────────────────────────────────────────────
输入：对每个实体取 `countries` 字段，统计 20 个跟踪国各自「关联制裁实体数」count[c]。

1) 国别结构暴露分 country_risk[c]（0–100），对数压缩 + 饱和：
       country_risk[c] = 100 * ln(count[c] + 1) / ln(SATURATION_COUNT + 1)，上限 100
   其中 SATURATION_COUNT = 25000（调参常量，含义：一个国家的关联制裁实体数达到
   25000 即触顶为 100 分；当前任何单一跟踪国都未到该量级，留有余量同时压缩长尾）。
   现实意义：被制裁实体数越多 → 该国与全球制裁宇宙的结构纠缠越深 → 暴露基线越高。
   用对数而非线性，是因为实体数在国别间极度偏斜（俄/伊/中成千上万，西方民主国仅个位数），
   线性会把俄压到接近满分而让其他国家几乎不可见；对数把动态范围压到可读区间。

2) 全局制裁基线 global_sanctions_risk（0–100），均值 + 最大值混合：
       global = 0.4 * mean(country_risk) + 0.6 * max(country_risk)
   现实意义：
     - 0.6 权重给「单一最暴露国」（最坏热点）：保证被长期重制裁的国家（如 RUS）把全局基线
       持久托高，即便当天没有任何制裁大新闻，基线仍偏高——这正是系统要的「持久制裁基线」。
     - 0.4 权重给「20 国跨均值」（广度）：反映制裁暴露在主要经济体间的普遍程度。
   结果是一个稳定、结构性的 0–100 基线，不受每日新闻标题驱动。
"""
import os
import csv
import json
import math
import time

try:
    from optim_config import DATA_DIR, OPEN_SANCTIONS_DATA_URL, PROXY_URL
except ImportError:
    _cfg = FetcherBase.load_config_with_fallback(
        ["DATA_DIR", "OPEN_SANCTIONS_DATA_URL", "PROXY_URL"],
        {
            "DATA_DIR": FetcherBase.default_data_dir(),
            "OPEN_SANCTIONS_DATA_URL": (
                "https://data.opensanctions.org/datasets/latest/sanctions/targets.simple.csv",
                "OPEN_SANCTIONS_DATA_URL",
            ),
            "PROXY_URL": ("", "PROXY_URL"),
        },
    )
    DATA_DIR = _cfg["DATA_DIR"]
    OPEN_SANCTIONS_DATA_URL = _cfg["OPEN_SANCTIONS_DATA_URL"]
    PROXY_URL = _cfg["PROXY_URL"]

from fetcher_base import FetcherBase

# 20 个跟踪国（ISO 3166-1 alpha-3）
TRACKED_COUNTRIES = [
    "USA", "CHN", "DEU", "JPN", "GBR", "FRA", "IND", "BRA", "RUS", "ZAF",
    "MEX", "KOR", "CAN", "AUS", "ITA", "ESP", "IDN", "TUR", "SAU", "IRN",
]

# ISO3 → ISO2（OpenSanctions `countries` 列为 ISO2 代码，匹配时大小写不敏感）
_ISO3_TO_ISO2 = {
    "USA": "US", "CHN": "CN", "DEU": "DE", "JPN": "JP", "GBR": "GB",
    "FRA": "FR", "IND": "IN", "BRA": "BR", "RUS": "RU", "ZAF": "ZA",
    "MEX": "MX", "KOR": "KR", "CAN": "CA", "AUS": "AU", "ITA": "IT",
    "ESP": "ES", "IDN": "ID", "TUR": "TR", "SAU": "SA", "IRN": "IR",
}
_ISO2_TO_ISO3 = {v: k for k, v in _ISO3_TO_ISO2.items()}

# 饱和常量：关联制裁实体数达到该值即触顶 100 分（见文件头公式说明）
SATURATION_COUNT = 25000

OUTPUT_FILE = "sanctions_risk.json"
CACHE_SUBDIR = "sanctions_cache"
CACHE_FILE = "targets.simple.csv"


class SanctionsFetcher(FetcherBase):
    name = "sanctions"
    rate_interval = 0.5
    output_file = OUTPUT_FILE
    feeds_grv = True
    schedule = "0605"
    cache_ttl = 7 * 86400       # 制裁存量变化慢，本地缓存 7 天；过期才重下
    download_timeout = 300      # 大文件下载超时（秒）

    # 由配置注入；允许在子类/运行时覆盖
    data_url = OPEN_SANCTIONS_DATA_URL
    proxy_url = PROXY_URL
    tracked = TRACKED_COUNTRIES

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self._last_cache_used = False

    # ── 下载（直连失败 → 走代理 → 仍失败降级） ────────────────────────
    def _download(self, url: str):
        """带降级：先直连，直连失败且配置了代理则走代理。均失败返回 None。"""
        self.proxies = None
        r = self.request(url, timeout=self.download_timeout)
        if r is not None:
            return r
        if self.proxy_url:
            self.logger.warning("[sanctions] 直连失败，尝试走代理 %s", self.proxy_url)
            self.proxies = {"http": self.proxy_url, "https": self.proxy_url}
            r = self.request(url, timeout=self.download_timeout)
            if r is not None:
                return r
        return None

    def _ensure_bulk_data(self) -> str | None:
        """返回本地缓存 CSV 路径；必要时下载。失败返回 None（交由 collect 降级）。"""
        cache_path = os.path.join(self.data_dir, CACHE_SUBDIR, CACHE_FILE)
        self._last_cache_used = False

        # 缓存新鲜度检查（<7 天直接用缓存，避免每日重抓数百 MB）
        if os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < self.cache_ttl:
                self._last_cache_used = True
                self.logger.info(
                    "[sanctions] 使用本地缓存（%.1f 天前，< %.0f 天阈值）",
                    age / 86400.0, self.cache_ttl / 86400.0,
                )
                return cache_path
            self.logger.info(
                "[sanctions] 缓存 %.1f 天，超过阈值 %.0f 天，重新下载",
                age / 86400.0, self.cache_ttl / 86400.0,
            )

        # 下载（直连，失败走代理）
        self.logger.info("[sanctions] 下载 bulk data: %s", self.data_url)
        r = self._download(self.data_url)
        if r is None:
            self.logger.error("[sanctions] bulk data 下载失败（直连 + 代理均失败）")
            return None
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            tmp = cache_path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(r.content)
            os.replace(tmp, cache_path)
            self.logger.info("[sanctions] 已缓存到 %s (%d bytes)", cache_path, len(r.content))
        except Exception as e:
            self.logger.error("[sanctions] 写缓存失败: %s", e)
            return None
        return cache_path

    # ── 国别聚合 ──────────────────────────────────────────────────
    @staticmethod
    def _country_risk(count: int) -> float:
        """国别结构暴露分（0–100）：对数压缩 + 饱和。见文件头公式说明。"""
        if count <= 0:
            return 0.0
        risk = 100.0 * math.log(count + 1) / math.log(SATURATION_COUNT + 1)
        return round(min(risk, 100.0), 1)

    def _aggregate(self, csv_path: str):
        """逐行流式解析 CSV（内存安全），统计 20 国关联制裁实体数。

        返回 (counts: {ISO3: int}, total: int, found_col: bool)。
        found_col=False 表示 CSV 缺少 countries/country 列（解析异常亦置 False）。
        """
        counts = {iso3: 0 for iso3 in self.tracked}
        total = 0
        found_col = False
        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                lower_map = {h.lower(): h for h in (reader.fieldnames or [])}
                col_name = lower_map.get("countries") or lower_map.get("country")
                if col_name is None:
                    self.logger.error(
                        "[sanctions] CSV 无 countries/country 列，表头=%s", reader.fieldnames
                    )
                    return counts, total, False
                found_col = True
                for row in reader:
                    total += 1
                    cell = row.get(col_name) or ""
                    if not cell:
                        continue
                    # 嵌套 CSV 用 `;` 分隔国家代码
                    for code in cell.split(";"):
                        code = (code or "").strip().upper()
                        iso3 = _ISO2_TO_ISO3.get(code)
                        if iso3 is not None:
                            counts[iso3] += 1
        except Exception as e:
            self.logger.error("[sanctions] 解析失败: %s", e)
            return counts, total, False
        return counts, total, found_col

    # ── 主采集 ────────────────────────────────────────────────────
    def collect(self):
        csv_path = self._ensure_bulk_data()
        if csv_path is None:
            return {
                "status": "unavailable",
                "reason": "bulk_data_unavailable",
                "source": "opensanctions_bulk",
            }

        counts, total, found_col = self._aggregate(csv_path)
        if not found_col:
            self.logger.error("[sanctions] 未找到 countries 列，无法聚合，降级 unavailable")
            return {
                "status": "unavailable",
                "reason": "countries_column_missing",
                "source": "opensanctions_bulk",
            }

        by_country = {iso3: {"count": cnt, "risk": self._country_risk(cnt)}
                      for iso3, cnt in counts.items()}
        risks = [v["risk"] for v in by_country.values()]
        mean_risk = sum(risks) / len(risks) if risks else 0.0
        max_risk = max(risks) if risks else 0.0
        # 全局基线 = 0.4 * 均值 + 0.6 * 最大值（见文件头公式说明）
        global_risk = round(0.4 * mean_risk + 0.6 * max_risk, 1)

        self.logger.info(
            "[sanctions] 聚合完成 total=%d，global=%.1f，max_country=%s(%.1f)",
            total, global_risk,
            max(by_country, key=lambda k: by_country[k]["risk"]),
            max_risk,
        )
        return {
            "status": "ok",
            "global_sanctions_risk": global_risk,
            "by_country": by_country,
            "total_sanctioned": total,
            "source": "opensanctions_bulk",
            "dataset": "sanctions",
            "cache_used": self._last_cache_used,
        }

def main():
    fetcher = SanctionsFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[sanctions] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") == "ok":
        fetcher.save_json(OUTPUT_FILE, result)
        print(
            f"[sanctions] 完成 status=ok，global={result.get('global_sanctions_risk')}，"
            f"total={result.get('total_sanctioned')}，cache_used={result.get('cache_used')}"
        )
    else:
        # 降级：若本地有上次良值则保留，不覆盖；否则写 unavailable 标记供下游感知
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[sanctions] 降级 unavailable，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, result)
            print("[sanctions] 降级 unavailable，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
