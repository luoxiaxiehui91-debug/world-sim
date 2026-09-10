"""
optim_config.py — 天玑容器精简路径模块（macro-ji）

只声明天玑内核三件需要的最小常量：DATA_DIR/WORKSPACE/FRED_API_KEY。
DATA_DIR 显式指向挂载卷 /app/macro_data（宿主机上的天枢数据目录），
绝不用 __file__ 推导（防落非持久卷，P0-D 同族红线）。
"""
import os

WORKSPACE = os.environ.get("OPENCLAW_WORKSPACE", "/app")
DATA_DIR  = os.environ.get("TIANJI_DATA_DIR", "/app/macro_data")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")


# ── 验证域存量收编追加（2026-08-24）：verify_predictions 自天枢迁入所需 ──
# 保持精简哲学：只加迁入脚本实际 import 的常量（对齐天枢版 L120-125/L31 数值）
PREDICTIONS_LOG   = os.path.join(DATA_DIR, "predictions_log.json")
FRED_MAX_LAG_DAYS = 45      # FRED 新鲜度最大容忍滞后（天）
GDP_HIT_TOLERANCE    = 1.5  # GDP 预测命中容差 ±1.5ppt
UNRATE_HIT_TOLERANCE = 0.5  # 失业率命中容差 ±0.5ppt
CPI_HIT_TOLERANCE    = 0.8  # CPI YoY 命中容差 ±0.8ppt
