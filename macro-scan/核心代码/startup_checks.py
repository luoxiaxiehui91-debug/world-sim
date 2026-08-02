"""
startup_checks.py — 天枢启动完整性校验

在 scheduler.py 启动时调用 run_all_checks()。
任何校验失败都抛出 RuntimeError，阻断天枢启动（强制失败优于静默错误）。

校验项：
  1. source_dimension_map.yaml 完整性：所有 primary 维度必须是已知的 GRV 11维之一。
  2. 关键数据目录存在性：DATA_DIR / fred_history / grv_latest.json 路径可达。
"""

import os
import sys

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR  = os.path.join(WORKSPACE, "data")

_CONFIG_DIR = os.path.join(WORKSPACE, "config")
_SOURCE_DIM_MAP = os.path.join(_CONFIG_DIR, "source_dimension_map.yaml")

# GRV 11个已知维度（与 geo_risk_vector.py 保持一致）
KNOWN_GRV_DIMENSIONS = {
    "global_composite",
    "taiwan_strait",
    "russia_europe",
    "middle_east_energy",
    "us_china_strategic",
    "sanctions_risk",
    "energy_grid_risk",
    "disaster_risk",
    "climate_risk",
    "japan_monetary",
    "seismic_risk",
    "social_stress",      # R09：社会情绪压力（v3.8.3 接入）
    "cultural_friction",  # R10：文化摩擦（v3.8.3 接入）
}


def check_source_dimension_map() -> list[str]:
    """
    校验 source_dimension_map.yaml：
    - 文件必须存在
    - 每个 source 的 primary 字段必须是 KNOWN_GRV_DIMENSIONS 之一
    返回错误列表，空列表表示校验通过。
    """
    errors = []

    if not os.path.exists(_SOURCE_DIM_MAP):
        errors.append(f"source_dimension_map.yaml 不存在: {_SOURCE_DIM_MAP}")
        return errors

    try:
        import yaml
        with open(_SOURCE_DIM_MAP, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        errors.append(f"source_dimension_map.yaml 解析失败: {e}")
        return errors

    sources = cfg.get("sources", {})
    if not sources:
        errors.append("source_dimension_map.yaml 中 sources 节为空")
        return errors

    unknown_dims = []
    for src_name, src_cfg in sources.items():
        primary = src_cfg.get("primary", "")
        if primary not in KNOWN_GRV_DIMENSIONS:
            unknown_dims.append(f"  {src_name}: primary='{primary}' 不在已知 GRV 维度中")

    if unknown_dims:
        errors.append(
            "source_dimension_map.yaml 存在未知维度映射（遗漏映射会导致 GRV 维度静默接收零数据）：\n"
            + "\n".join(unknown_dims)
        )

    return errors


def check_data_dirs() -> list[str]:
    """校验关键数据目录和文件是否可达（警告级，不阻断启动）。"""
    warnings = []
    fred_dir = os.path.join(DATA_DIR, "fred_history")
    grv_latest = os.path.join(DATA_DIR, "grv_latest.json")

    if not os.path.isdir(DATA_DIR):
        warnings.append(f"DATA_DIR 不存在: {DATA_DIR}")
    if not os.path.isdir(fred_dir):
        warnings.append(f"fred_history 目录不存在: {fred_dir}")
    if not os.path.exists(grv_latest):
        warnings.append(f"grv_latest.json 不存在（天枢尚未首次产出）: {grv_latest}")

    return warnings


def run_all_checks(strict: bool = True):
    """
    运行所有启动校验。
    strict=True（默认）：source_dimension_map 校验失败则 raise RuntimeError 阻断启动。
    strict=False：仅打印警告，不阻断（用于测试环境）。
    """
    print("[startup_checks] 运行天枢启动完整性校验...")

    # 强制校验：source_dimension_map
    errors = check_source_dimension_map()
    if errors:
        msg = "startup_checks 发现严重问题：\n" + "\n".join(errors)
        if strict:
            raise RuntimeError(msg)
        else:
            print(f"[startup_checks] ⚠️ WARNING（非严格模式）:\n{msg}")
    else:
        print("[startup_checks] ✅ source_dimension_map.yaml 校验通过")

    # 软警告：数据目录
    warnings = check_data_dirs()
    for w in warnings:
        print(f"[startup_checks] ⚠️ {w}")

    if not errors and not warnings:
        print("[startup_checks] ✅ 所有校验通过")


if __name__ == "__main__":
    strict = "--strict" in sys.argv or len(sys.argv) == 1
    run_all_checks(strict=strict)
