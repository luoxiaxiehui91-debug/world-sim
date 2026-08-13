"""
narrative_processor.py — 叙事预处理模块

每日天枢调度后调用，将所有数据源的新闻/文章写入 narrative_chunks 表。
按 source_dimension_map.yaml 分配 GRV 维度，计算 staleness_tau，
供天璇激活时按需取用。

设计：
- 只做写入，不做 embedding（embedding 在阶段二加）
- 同维度同来源同日内容去重（content hash）
- 路径 B 叙事密度监测：每日更新 narrative_density_flags
"""

import os
import json
import hashlib
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR  = os.path.join(WORKSPACE, "data")

try:
    from tianji_db import (
        get_connection, save_narrative_chunk,
        get_narrative_chunks_for_dimension,
    )
except ImportError:
    raise ImportError("tianji_db.py 未找到，请先运行 tianji_db.py 初始化数据库")

# E0-A: 旁路双写 worldsim-pg（非阻断，异常自吞，绝不阻断 SQLite 主流程）
from pg_write_collection import (
    upsert_tianji_narrative_density_flag, delete_tianji_narrative_density_flag,
)

# ── source_dimension_map ──────────────────────────────────────────────────────
# 每个数据源的文章默认分配到哪个 GRV 维度
# 格式：source_id -> {primary_dimension, secondary_dimension, staleness_tau, source_type}
# 实际生产中从 source_dimension_map.yaml 读取，此处提供硬编码 fallback

DEFAULT_SOURCE_MAP = {
    # 新闻类（综合）
    "marketaux":        {"primary": "global_composite",      "tau": 72,  "type": "financial_news"},
    "currents":         {"primary": "global_composite",      "tau": 72,  "type": "news"},
    "rsshub_caixin":    {"primary": "us_china_strategic",    "tau": 72,  "type": "chinese_media"},
    "rsshub_yicai":     {"primary": "us_china_strategic",    "tau": 72,  "type": "chinese_media"},
    "rsshub_wsj":       {"primary": "global_composite",      "tau": 72,  "type": "financial_news"},
    "rsshub_bbc":       {"primary": "global_composite",      "tau": 72,  "type": "news"},
    "rsshub_reuters":   {"primary": "global_composite",      "tau": 72,  "type": "financial_news"},
    "rsshub_nikkei":    {"primary": "japan_monetary",        "tau": 72,  "type": "financial_news"},
    "rsshub_eastmoney": {"primary": "us_china_strategic",    "tau": 72,  "type": "chinese_media"},
    "rsshub_ft":        {"primary": "global_composite",      "tau": 72,  "type": "financial_news"},
    # 防务/军事类
    "aljazeera":        {"primary": "middle_east_energy",    "tau": 72,  "type": "news"},
    "defense_one":      {"primary": "taiwan_strait",         "tau": 120, "type": "defense_media"},
    "war_on_rocks":     {"primary": "russia_europe",         "tau": 120, "type": "defense_media"},
    # 制裁/地缘
    "opensanctions":    {"primary": "sanctions_risk",        "tau": 240, "type": "official_statement"},
    # 能源
    "energy_eia":       {"primary": "energy_grid_risk",      "tau": 168, "type": "official_data"},
    # 灾害
    "gdacs":            {"primary": "disaster_risk",         "tau": 48,  "type": "humanitarian"},
    "hdx":              {"primary": "disaster_risk",         "tau": 240, "type": "humanitarian"},
    # 气候
    "climate_signals":  {"primary": "climate_risk",          "tau": 240, "type": "official_data"},
    # ── Crucix 信号桶（DEPRECATED：crucix 已退场，无上游数据源，下游零消费）──
    "crucix_gscpi":     {"primary": "global_composite",      "tau": 48,  "type": "osint"},
    "crucix_nuke":      {"primary": "taiwan_strait",         "tau": 24,  "type": "osint"},
    "crucix_air":       {"primary": "taiwan_strait",         "tau": 24,  "type": "osint"},
    "crucix_sdr":       {"primary": "sanctions_risk",        "tau": 24,  "type": "osint"},
    "kiwisdr_sdr":     {"primary": "global_composite",     "tau": 24,  "type": "osint"},
    # 中国宏观
    "akshare_china":    {"primary": "us_china_strategic",    "tau": 240, "type": "official_data"},
    "akshare_world":    {"primary": "global_composite",      "tau": 240, "type": "official_data"},
}

# GRV 维度列表（与 geo_risk_vector.py 保持一致）
GRV_DIMENSIONS = [
    "taiwan_strait",
    "us_china_strategic",
    "russia_europe",
    "middle_east_energy",
    "global_composite",
    "climate_risk",
    "disaster_risk",
    "sanctions_risk",
    "seismic_risk",
    "energy_grid_risk",
    "japan_monetary",
]

# 关键词分类规则（基于内容自动补充 secondary_dimension）
KEYWORD_RULES = {
    "taiwan_strait":      ["台海", "台湾", "Taiwan", "PLA", "解放军", "台积电", "TSMC"],
    "us_china_strategic": ["中美", "US-China", "贸易战", "trade war", "芯片", "chip", "半导体"],
    "russia_europe":      ["俄罗斯", "Russia", "乌克兰", "Ukraine", "NATO", "北约", "天然气"],
    "middle_east_energy": ["以色列", "Israel", "伊朗", "Iran", "沙特", "Saudi", "OPEC", "胡塞"],
    "sanctions_risk":     ["制裁", "sanction", "实体清单", "entity list", "OFAC"],
    "energy_grid_risk":   ["石油", "oil", "天然气", "gas", "能源", "energy", "EIA"],
    "japan_monetary":     ["日本", "Japan", "日元", "yen", "日银", "BOJ", "植田"],
    "climate_risk":       ["气候", "climate", "ENSO", "El Nino", "野火", "wildfire"],
    "disaster_risk":      ["飓风", "hurricane", "洪水", "flood", "地震", "earthquake", "台风"],
    "seismic_risk":       ["地震", "earthquake", "seismic", "USGS", "里氏"],
    "global_composite":   ["美联储", "Fed", "通胀", "inflation", "GDP", "衰退", "recession"],
}


def _content_hash(content: str, dimension: str) -> str:
    return hashlib.md5(f"{dimension}:{content[:200]}".encode()).hexdigest()


def _detect_secondary_dimension(content: str, primary: str) -> str | None:
    """基于关键词规则检测 secondary_dimension（不与 primary 相同）。"""
    text = content.lower()
    scores = {}
    for dim, keywords in KEYWORD_RULES.items():
        if dim == primary:
            continue
        count = sum(1 for kw in keywords if kw.lower() in text)
        if count > 0:
            scores[dim] = count
    if not scores:
        return None
    return max(scores, key=scores.get)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def load_source_map() -> dict:
    """尝试从 YAML 加载，失败时用硬编码 fallback。"""
    yaml_path = os.path.join(WORKSPACE, "config", "source_dimension_map.yaml")
    if os.path.exists(yaml_path):
        try:
            import yaml
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("sources", DEFAULT_SOURCE_MAP)
        except Exception as e:
            print(f"[narrative_processor] YAML加载失败，使用fallback: {e}")
    return DEFAULT_SOURCE_MAP


# ── 核心入口：处理一篇文章 ────────────────────────────────────────────────────

def ingest_article(
    source_id: str,
    content: str,
    timestamp: str = None,
    source_map: dict = None,
    dry_run: bool = False,
) -> dict:
    """
    处理一篇文章，写入 narrative_chunks。
    返回 {status, dimension, token_count}。
    """
    if source_map is None:
        source_map = DEFAULT_SOURCE_MAP

    cfg = source_map.get(source_id, {
        "primary": "global_composite", "tau": 72, "type": "news"
    })

    primary_dim  = cfg.get("primary", "global_composite")
    tau          = cfg.get("tau", 72)
    source_type  = cfg.get("type", "news")
    ts           = timestamp or datetime.now(timezone.utc).isoformat()

    # 关键词规则补充 secondary
    secondary_dim = _detect_secondary_dimension(content, primary_dim)

    token_count = _estimate_tokens(content)

    chunk = {
        "source_id":           source_id,
        "source_type":         source_type,
        "primary_dimension":   primary_dim,
        "secondary_dimension": secondary_dim,
        "timestamp":           ts,
        "content":             content,
        "token_count":         token_count,
        "staleness_tau":       tau,
    }

    if not dry_run:
        # 去重检查：同维度同 hash 跳过
        chash = _content_hash(content, primary_dim)
        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT id FROM narrative_chunks WHERE source_id=? AND content LIKE ? LIMIT 1",
                (source_id, content[:100] + "%")
            ).fetchone()
            if existing:
                return {"status": "duplicate_skipped", "dimension": primary_dim}
        finally:
            conn.close()

        save_narrative_chunk(chunk)

    return {"status": "ok", "dimension": primary_dim, "token_count": token_count}


# ── 批量摄取：从现有 JSON 数据文件 ───────────────────────────────────────────


def ingest_from_json_file(json_path: str, source_id: str, content_field: str = "content"):
    """从 fetcher 输出的 JSON 文件摄取文章（通用入口）。"""
    if not os.path.exists(json_path):
        return 0
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0

    articles = data if isinstance(data, list) else data.get("articles", [])
    source_map = load_source_map()
    count = 0
    for item in articles:
        content = item.get(content_field) or item.get("title", "")
        if not content or len(content) < 20:
            continue
        ts = item.get("published_at") or item.get("updated") or datetime.now(timezone.utc).isoformat()
        result = ingest_article(source_id=source_id, content=content,
                                timestamp=ts, source_map=source_map)
        if result["status"] == "ok":
            count += 1
    return count


# ── 路径 B：叙事密度监测 ────────────────────────────────────────────────────

def update_density_flags(window_days: int = 30):
    """
    计算各维度过去24h新文章数的 Z-score，Z>2.0 写入 narrative_density_flags。
    冷启动不足30天时退化为简单阈值（当日数量 > 过去7天均值×1.5）。
    """
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc)
        yesterday = (now - timedelta(hours=24)).isoformat()

        for dim in GRV_DIMENSIONS:
            # 今日数量
            today_count = conn.execute("""
                SELECT COUNT(*) FROM narrative_chunks
                WHERE primary_dimension=? AND timestamp >= ?
            """, (dim, yesterday)).fetchone()[0]

            # 历史日均（window_days 天）
            history_start = (now - timedelta(days=window_days)).isoformat()
            hist_rows = conn.execute("""
                SELECT DATE(timestamp) as d, COUNT(*) as cnt
                FROM narrative_chunks
                WHERE primary_dimension=? AND timestamp >= ?
                GROUP BY DATE(timestamp)
                ORDER BY d DESC
            """, (dim, history_start)).fetchall()

            if len(hist_rows) < 7:
                # 冷启动：简单阈值
                if len(hist_rows) >= 1:
                    avg_7 = sum(r[1] for r in hist_rows) / len(hist_rows)
                    if today_count > avg_7 * 1.5:
                                            conn.execute("""
                        INSERT OR REPLACE INTO narrative_density_flags
                          (dimension, flagged_at, z_score, consumed)
                        VALUES (?, ?, ?, 0)
                    """, (dim, now.isoformat(), 1.6))
                    upsert_tianji_narrative_density_flag(dim, now.isoformat(), 1.6, 0)
                continue

            counts = [r[1] for r in hist_rows]
            mean   = sum(counts) / len(counts)
            variance = sum((c - mean)**2 for c in counts) / len(counts)
            std    = math.sqrt(variance) if variance > 0 else 1.0
            z      = (today_count - mean) / std

            if z > 2.0:
                conn.execute("""
                    INSERT OR REPLACE INTO narrative_density_flags
                      (dimension, flagged_at, z_score, consumed)
                    VALUES (?, ?, ?, 0)
                """, (dim, now.isoformat(), round(z, 2)))
                upsert_tianji_narrative_density_flag(dim, now.isoformat(), round(z, 2), 0)
            else:
                # 清除旧 flag
                conn.execute(
                    "DELETE FROM narrative_density_flags WHERE dimension=?", (dim,)
                )
                delete_tianji_narrative_density_flag(dim)

        conn.commit()
    finally:
        conn.close()


def get_flagged_dimensions() -> dict[str, float]:
    """返回当前被路径B标记的维度及其Z-score。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT dimension, z_score FROM narrative_density_flags WHERE consumed=0"
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


def mark_flags_consumed(dimensions: list[str]):
    """天璇消费完叙事块后标记 consumed=1。"""
    conn = get_connection()
    try:
        for dim in dimensions:
            conn.execute(
                "UPDATE narrative_density_flags SET consumed=1 WHERE dimension=?", (dim,)
            )
        conn.commit()
    finally:
        conn.close()


# ── 天璇取用接口 ────────────────────────────────────────────────────────────

def get_narrative_context_for_trigger(
    triggered_dimensions: list[str],
    total_token_budget: int = 8000,
) -> dict[str, str]:
    """
    天璇激活时调用。
    triggered_dimensions: 触发推演的 GRV 维度列表
    返回 {dimension: narrative_text} 字典，总 token 不超过 budget。
    """
    flagged = get_flagged_dimensions()

    # 按维度分配 token 预算
    per_dim_budget = {}
    base_budget = 2000
    boosted_budget = 3000

    for dim in triggered_dimensions:
        per_dim_budget[dim] = boosted_budget if dim in flagged else base_budget

    # 如果总预算超限，按比例压缩
    total_allocated = sum(per_dim_budget.values())
    if total_allocated > total_token_budget:
        scale = total_token_budget / total_allocated
        per_dim_budget = {k: int(v * scale) for k, v in per_dim_budget.items()}

    result = {}
    consumed_flags = []

    for dim in triggered_dimensions:
        chunks = get_narrative_chunks_for_dimension(
            dimension=dim,
            max_tokens=per_dim_budget.get(dim, base_budget),
        )
        if not chunks:
            continue

        texts = []
        for chunk in chunks:
            src = chunk.get("source_id", "unknown")
            content = chunk.get("content", "")
            texts.append(f"[{src}] {content}")

        result[dim] = "\n\n".join(texts)

        if dim in flagged:
            consumed_flags.append(dim)

    if consumed_flags:
        mark_flags_consumed(consumed_flags)

    return result


# ── 日常调度入口 ────────────────────────────────────────────────────────────

def run_daily_narrative_processing():
    """scheduler.py 在日采完成后调用。"""
    print("[narrative_processor] 开始叙事预处理...")

    # 2. 从各 fetcher JSON 摄取（列举关键文件）
    json_sources = [
        (os.path.join(DATA_DIR, "sanctions_risk.json"),     "opensanctions",  "description"),
        (os.path.join(DATA_DIR, "energy.json"),             "energy_eia",     "summary"),
        (os.path.join(DATA_DIR, "disaster_signals.json"),   "gdacs",          "description"),
        (os.path.join(DATA_DIR, "hdx_latest.json"),         "hdx",            "description"),
        (os.path.join(DATA_DIR, "climate_signals.json"),    "climate_signals","summary"),
        (os.path.join(DATA_DIR, "sdr_summary.json"),      "kiwisdr_sdr",   "description"),
    ]
    count_json = 0
    for path, src_id, field in json_sources:
        count_json += ingest_from_json_file(path, src_id, field)

    # 3. 更新叙事密度监测
    update_density_flags()

    flagged = get_flagged_dimensions()
    print(f"[narrative_processor] 完成：JSON{count_json}条")
    if flagged:
        print(f"[narrative_processor] 叙事密度突增维度: {list(flagged.keys())}")
    else:
        print("[narrative_processor] 无叙事密度突增")


if __name__ == "__main__":
    from tianji_db import run_migration
    run_migration()
    run_daily_narrative_processing()
