"""
统一配置文件 — 所有模块从这里导入路径和常量。
修改系统环境时只需改这一个文件。

本地化修改（2026-05-18）：
  - AUTH_GATEWAY_PORT 默认值从 "19000" 改为 "28789"
  - 重命名为 optim_config.py，避免与 run_macro_analysis.py 冲突

2026-05-21 补充：
  - 新增 LEI 阈值（AWHMAN/PERMIT）
  - 新增全球风险区域失业率历史低位参考
  - 新增滚动精度报告窗口配置
"""

import os

# ── 工作区根目录（优先从环境变量读取，便于迁移） ──────────────────────────────
WORKSPACE = os.environ.get(
    "OPENCLAW_WORKSPACE",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# ── 数据目录 ───────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(WORKSPACE, "data")

def ensure_dirs() -> None:
    """创建运行所需目录，由入口脚本在 __main__ 中调用（避免 import 时副作用）。"""
    os.makedirs(DATA_DIR, exist_ok=True)

# ── 关键文件路径 ───────────────────────────────────────────────────────────────
PREDICTIONS_LOG   = os.path.join(DATA_DIR, "predictions_log.json")
WEAK_SIGNAL_LOG   = os.path.join(DATA_DIR, "weak_signal_log.json")
KB_ROOT           = os.environ.get("KB_ROOT") or os.path.join(WORKSPACE, "知识库")
KB_DIR            = os.path.join(KB_ROOT, "财经知识库")
GEO_EVENTS_LOG    = os.path.join(KB_DIR,
                                  "02_核心变量因果链", "地缘事件日志.json")
MAIN_SCRIPT       = os.path.join(WORKSPACE, "核心代码", "run_macro_analysis.py")
KNOWLEDGE_BASE    = KB_DIR

# ── 推送配置（已迁移至 ntfy，此端口仅供 scan_weak_signals.py NeoData 接口使用）──
AUTH_GATEWAY_PORT = os.environ.get("AUTH_GATEWAY_PORT", "28789")
# CFG-3: PUSH_ENDPOINT / CRUCIX_ENDPOINT / CRUCIX_REMOTE_URL 均已删除（死代码，无任何调用者）
# 实际推送走 ntfy_listener.py；crucix 已于 08-12 退场（G0 PASS + D1 gscpi 改 NY Fed CSV 唯一源，删 :3117 分支）

# ── FRED API ───────────────────────────────────────────────────────────────────
# 优先从环境变量读取，如未设置则使用默认 Key
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# ── CoinGecko Demo API（加密资产快照，免费档 100 RPM / ~1万月）──
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")

# ── OpenSanctions bulk data 端点（制裁风险快照，方案 B：国别暴露聚合）──
# 用官方「latest」重定向直取最新发布，免去解析 run 时间戳；
# 实际发布文件为 targets.simple.csv（简化表格式，含 countries 列），
# OpenSanctions 未提供 entities.csv。如需切换数据集/格式在此覆盖。
OPEN_SANCTIONS_DATA_URL = os.environ.get(
    "OPEN_SANCTIONS_DATA_URL",
    "https://data.opensanctions.org/datasets/latest/sanctions/targets.simple.csv",
)

# ── 出站代理（NAS 出口，部分外部源直连不可达时走此，与 FRED 代理一致）──
PROXY_URL = os.environ.get("PROXY_URL", "")

# ── 新接入源配置（P0+P1，env 可覆盖）─────────────────────────────────────────
# P0 — USGS 地震（真免key，实时 GeoJSON feed，带 time 时间戳）
USGS_EARTHQUAKE_URL = os.environ.get(
    "USGS_EARTHQUAKE_URL",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson",
)

# P1 — 能源/电网（英国 Carbon Intensity / National Grid ESO，NESO 公开 API 免key）
UK_CARBON_INTENSITY_BASE = os.environ.get(
    "UK_CARBON_INTENSITY_BASE", "https://api.carbonintensity.org.uk"
)
# National Grid ESO (NESO) BMRS 需免费 API key；未配则降级（见 fetch_energy.py 说明）
NATIONAL_GRID_ESO_BMRS_KEY = os.environ.get("NATIONAL_GRID_ESO_BMRS_KEY", "")

# P1 — 气象/太阳能（需 key）
NREL_API_KEY = os.environ.get("NREL_API_KEY", "")
NREL_PVWATTS_URL = os.environ.get(
    "NREL_PVWATTS_URL", "https://developer.nrel.gov/api/pvwatts/v8.json"
)
AEMET_API_KEY = os.environ.get("AEMET_API_KEY", "")
AEMET_BASE = os.environ.get("AEMET_BASE", "https://opendata.aemet.es/opendata/api")

# P1 — 加密冗余行情（Binance / Kraken 公共端，免key）
BINANCE_API_BASE = os.environ.get("BINANCE_API_BASE", "https://api.binance.com")
KRAKEN_API_BASE = os.environ.get("KRAKEN_API_BASE", "https://api.kraken.com")

# P1 — 新闻/情报聚合（均需 key）
MARKETAUX_API_KEY = os.environ.get("MARKETAUX_API_KEY", "")
MARKETAUX_API_URL = os.environ.get(
    "MARKETAUX_API_URL", "https://api.marketaux.com/v1/news/all"
)
CURRENTS_API_KEY = os.environ.get("CURRENTS_API_KEY", "")
CURRENTS_API_URL = os.environ.get(
    "CURRENTS_API_URL", "https://api.currentsapi.services/v1/latest-news"
)
SUGRA_API_KEY = os.environ.get("SUGRA_API_KEY", "")
SUGRA_API_URL = os.environ.get(
    "SUGRA_API_URL", "https://api.sugra.ai/v1/observations"
)

# ── EIA（美国能源信息署，免费注册 key，~9000次/小时限额）────────────────────────
EIA_API_KEY = os.environ.get("EIA_API_KEY", "")

# P1 — HDX（人道/危机数据集，CKAN API 免 token）
HDX_API_BASE = os.environ.get("HDX_API_BASE", "https://data.humdata.org/api/3/action")
HDX_QUERY = os.environ.get("HDX_QUERY", "humanitarian OR conflict OR crisis")

# ── 外部 LLM API ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.environ.get("OPENAI_API_KEY", "")

# ── Dashboard 输出路径 ─────────────────────────────────────────────────────────
DASHBOARD_OUTPUT = os.environ.get(
    "DASHBOARD_OUTPUT",
    os.path.join(WORKSPACE, "docs", "macro_dashboard.html")
)

# ── 验证精度容差（ppt） ────────────────────────────────────────────────────────
GDP_HIT_TOLERANCE    = 1.5   # GDP预测命中容差 ±1.5ppt
UNRATE_HIT_TOLERANCE = 0.5   # 失业率命中容差 ±0.5ppt
CPI_HIT_TOLERANCE    = 0.8   # CPI YoY命中容差 ±0.8ppt

# FRED 数据最大可接受滞后（天）：超出视为数据不可用，不进行验证
FRED_MAX_LAG_DAYS = 45

# ── 弱信号阈值 ────────────────────────────────────────────────────────────────
ZSCORE_WARN_THRESHOLD  = 2.0   # ⚠️ 注意
ZSCORE_ALERT_THRESHOLD = 3.0   # 🚨 警报
NEWS_FREQ_WARN_RATIO   = 3.0   # 近7天日均是90天均值的3倍触发注意
NEWS_FREQ_ALERT_RATIO  = 5.0   # 5倍触发警报

# ── LEI 先行指标阈值（score_recession_risk 使用） ─────────────────────────────
AWHMAN_WARN_THRESHOLD  = 40.5  # 制造业周工时（小时）警戒线：低于此值为偏弱
AWHMAN_CRIT_THRESHOLD  = 40.0  # 低于此值为偏低（历史衰退前常见）
PERMIT_WARN_THRESHOLD  = 1400  # 建筑许可（千套，SAAR）警戒线
PERMIT_CRIT_THRESHOLD  = 1200  # 低于此值为低迷（领先住宅投资下行）

# ── 全球风险评分：各经济体失业率近5年历史低位参考 ────────────────────────────
# 用于 score_global_recession_risk() 计算失业率偏离幅度
EU_UNRATE_HISTORICAL_LOW = 6.0   # 欧元区近5年低位（2019年约6.0%）
JP_UNRATE_HISTORICAL_LOW = 2.5   # 日本近5年低位（2022-2023约2.5%）
GB_UNRATE_HISTORICAL_LOW = 3.7   # 英国近5年低位（2022年约3.7%）
IN_PMI_EXPANSION_BENCH   = 55.0  # 印度制造业PMI"强扩张"基准线

# ── 滚动精度报告窗口（月） ────────────────────────────────────────────────────
ROLLING_ACCURACY_WINDOW_MONTHS = 6  # compute_rolling_accuracy_report 默认窗口

# ── 结构层评估文件 ─────────────────────────────────────────────────────────────
STRUCTURAL_PRIORS_FILE = os.path.join(DATA_DIR, "structural_priors.json")
NEWS_EXPORT_PATH       = os.path.join(DATA_DIR, "news_export.json")

# ── 核心 FRED 指标（美国） ────────────────────────────────────────────────────
# 原定义在 data_fetcher.py，迁至此处作为唯一配置源（与欧元区/日本阈值常量同处）
KEY_INDICATORS = {
    # 利率
    "DGS10": "10Y国债收益率",
    "DFF": "联邦基金利率",
    "T10Y2Y": "10Y-2Y利差",
    "BAA10Y": "BAA-10Y信用利差",
    # 经济
    "GDPC1": "GDP实际增长",
    "UNRATE": "失业率",
    "ICSA": "初请失业金人数",
    "PAYEMS": "非农就业",
    "MANEMP": "制造业就业",
    "JTSJOL": "职位空缺数",
    "INDPRO": "工业产出指数",
    # 通胀
    "CPIAUCSL": "CPI同比",
    "PCEPI": "核心PCE同比",
    "PPIACO": "PPI同比",
    "M2SL": "M2同比",
    # 资产
    "DCOILWTICO": "WTI原油",
    "SP500": "标普500",
    # 领先指标
    "UMCSENT": "消费者信心指数",
    "HOUST": "新屋开工数",
    "DTWEXBGS": "贸易加权美元指数",
    "AWHMAN": "制造业平均周工时",
    "PERMIT": "建筑许可数",
    # 通胀预期
    "DFII10": "10Y TIPS实际收益率",
    # 信用市场
    "BAMLH0A0HYM2": "高收益债利差",
    "MORTGAGE30US": "30年期房贷利率",
    # ── 欧元区（FRED 镜像序列） ───────────────────────────────────────────────
    "IRLTLT01EZM156N":  "欧元区10Y国债收益率",
    "LRUNTTTTEZQ156S":  "欧元区失业率",
    "CP0000EZ19M086NEST": "欧元区CPI同比",
    "MABMM301EZM189S":  "欧元区M1同比",
    # ── 日本（FRED 镜像序列） ─────────────────────────────────────────────────
    "IRLTLT01JPM156N":  "日本10Y国债收益率",
    "LRUNTTTTJPM156S":  "日本失业率",
    "JPNCPIALLMINMEI":  "日本CPI同比",
}


from datetime import datetime, timezone


def now_iso_utc() -> str:
    """Aware UTC ISO timestamp (+00:00, not truncated). Single source for created_at/generated_at."""
    return datetime.now(timezone.utc).isoformat()


def now_iso_local() -> str:
    """Aware local ISO timestamp (+08:00). Display/local-semantic fields only."""
    return datetime.now(timezone.utc).astimezone().isoformat()
