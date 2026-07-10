"""
alert_config.py — 弱信号扫描配置常量

原先定义在 scan_weak_signals.py 顶部/内部，迁出后：
- 关键词扩展只改本文件
- 扫描逻辑与配置解耦，可独立单测
- scan_weak_signals.py 从此处 import

## 类别与推演维度的关系（CFG-6）
ALERT_KEYWORDS 的类别分两类用途：

【同时触发 alert + 进入推演维度】（有 hypothesis_config.DIM_MAP 对应）
  信用风险 → FIN → global_composite
  衰退信号 → MACRO → global_composite
  地缘升级 → GEO → taiwan_strait
  流动性危机 → FIN → global_composite
  日元套利 → JAPAN → japan_monetary
  社会政治危机 → SOCIAL/POLITICAL → global_composite
  宗教族群冲突 → RELIGIOUS → global_composite
  通胀失控 → MACRO → global_composite
  能源政治 → ENERGY → middle_east_energy
  自然灾害 → CRISIS → global_composite

【仅触发 alert，暂无专属推演维度】
  文化贸易摩擦 — 对应 DIM_MAP CULTURAL，当前借用 global_composite（无专属 GRV 字段）
  战略矿产 — 对应 DIM_MAP TRADE，us_china_strategic（战略矿产管制归入中美博弈维度）
  科技竞争 — 对应 DIM_MAP TRADE，us_china_strategic（AI/量子/卫星竞争归入中美博弈维度）
"""

# ── 新闻关键词分类 ────────────────────────────────────────────────────────────
ALERT_KEYWORDS = {
    "信用风险":   ["债务违约", "信用危机", "银行挤兑", "default", "bank run", "credit crunch"],
    "衰退信号":   ["经济衰退", "GDP萎缩", "recession", "negative growth"],
    "通胀失控":   ["恶性通胀", "hyperinflation", "通胀超预期"],
    "地缘升级":   ["军事冲突", "战争", "台海", "核威胁", "制裁升级", "military conflict"],
    "流动性危机": ["流动性危机", "liquidity crisis", "市场冻结", "margin call"],
    "日元套利":   ["日银加息", "BOJ rate hike", "日元暴升", "yen surge", "carry trade unwind", "套利平仓"],
    # ↑ 触发后走 hypothesis_config.DIM_MAP["JAPAN"] → grv_latest.json japan_monetary 维度
    "社会政治危机": ["政变", "coup", "uprising", "civil unrest", "regime change",
                    "社会动乱", "政治危机", "大规模抗议", "mass protest", "political crisis"],
    "宗教族群冲突": ["宗教冲突", "sectarian", "jihad", "ethnic cleansing",
                    "tribal conflict", "族群暴力", "宗教暴力", "communal violence"],
    "能源政治":     ["OPEC", "oil embargo", "energy crisis", "pipeline attack",
                    "能源危机", "石油禁运", "输油管", "oil supply cut",
                    "Strait of Hormuz", "霍尔木兹", "Red Sea", "红海", "Houthi", "胡塞",
                    "Iran nuclear", "伊朗核", "Suez Canal", "苏伊士", "Malacca", "马六甲"],
    "文化贸易摩擦": ["抵制", "boycott", "cultural tension", "soft power conflict",
                    "新疆", "human rights sanctions", "文化冲突", "舆论战",
                    "information warfare", "media ban", "cultural boycott"],
    "战略矿产":     ["稀土", "rare earth", "稀土管制", "lithium", "锂矿", "cobalt", "钴",
                    "nickel", "镍", "critical minerals", "矿产禁令", "资源武器化",
                    "tungsten", "钨", "gallium", "镓", "germanium", "锗"],
    "科技竞争":     ["AI监管", "AI regulation", "人工智能法案", "AI Act",
                    "量子计算", "quantum computing", "量子突破",
                    "反卫星", "anti-satellite", "ASAT", "卫星攻击", "太空冲突",
                    "无人机蜂群", "drone swarm", "网络战", "cyber warfare"],
    "自然灾害":     ["大地震", "earthquake", "海啸", "tsunami", "火山爆发",
                    "volcanic eruption", "核泄漏", "nuclear leak",
                    "洪灾严重", "extreme flood", "热浪", "heat wave"],
}

# ── GDELT Actor 类型代码 ──────────────────────────────────────────────────────
_ACTOR_REL_ETH = {"REL", "ETH", "SEP"}        # 宗教/族群/分裂主义组织
_ACTOR_REGIME  = {"REB", "OPP"}               # 叛乱武装/反对派（政权不稳指标）
_ACTOR_CULTURE = {"EDU", "MED", "IGO", "NGO"} # 文化摩擦：教育/媒体/国际组织/NGO
# 注：MIL/GOV 不作为 regime 触发因子，避免与 _CAMEO_MILITARY 重叠

# ── GDELT 关注国家（3位 ISO 代码） ──────────────────────────────────────────
_WATCH_COUNTRIES = {
    "USA", "CHN", "RUS", "IRN", "PRK", "ISR",
    "UKR", "TWN", "SAU", "DEU", "FRA", "JPN",
    "IND", "PAK", "TUR", "NGA", "EGY",
}
