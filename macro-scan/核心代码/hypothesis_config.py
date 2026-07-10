"""
hypothesis_config.py — 假设推演类型映射常量

原先定义在 hypothesis_engine.py 的函数内部（compute_confidence），
提升为模块级常量后：新增推演类型只改本文件，不碰引擎逻辑。

TYPE_FIELD_MAP / TYPE_KEYWORDS — 已在 P1 修复时提升，亦定义于此处供独立导入。
DIM_MAP — GRV 维度映射（类型 → grv_latest.json 字段名）。
"""

# ── GRV 维度映射：推演类型 → grv_latest.json 字段名 ─────────────────────────
# SOCIAL/POLITICAL/RELIGIOUS 无专属维度，借用 global_composite（置信度天花板🟡）
DIM_MAP = {
    "GEO":      "taiwan_strait",
    "TRADE":    "us_china_strategic",
    "ENERGY":   "middle_east_energy",
    "FIN":      "global_composite",
    "MACRO":    "global_composite",
    "CRISIS":   "global_composite",
    "SOCIAL":   "global_composite",
    "POLITICAL":"global_composite",
    "RELIGIOUS":"global_composite",   # CFG-9: 宗教冲突不限中东，改用中性 global_composite
    "CLIMATE":  "climate_risk",       # grv_latest.json 暂无时回退 0.3（compute_confidence 已处理）
    "CULTURAL": "global_composite",   # CFG-2: cultural_friction 字段尚未实现，改用 global_composite
    "JAPAN":    "japan_monetary",     # 日元套利平仓风险，专属维度
}
