#!/usr/bin/env python3
"""GRV 维度漂移巡检（2026-10-18，P1 三层脱节的防复发守卫）。

背景：question 20261018-...-grv-dimension-three-layer-disconnect 的根因第二条 ——
07-14 修 japan_monetary 时只补了单个维度，**没有建防复发机制**，3 个月后再以更大范围复发
（后端算了 18 个键、前端只映射 11 个、综合分只用 3 个输入，其中 5 个维度「算了完全不用」、
1 个「不显示却影响综合分」）。

⚠️ 为什么不能复用前端的 `missingKeys`（`grvAdapter.ts:40-45`）：它只遍历**已映射**项、
报「映射有、上游缺」；从不扫上游多出的键 ⇒ **方向相反**，发现不了「上游算了、前端没映射」。
本脚本两个方向都查。

检查项：
  1. 【A/B 类复发】上游产出了、前端没映射：grv_latest 数值键 − 非维度键 − 映射键 ≠ ∅ ⇒ 告警
  2. 【数据缺失】前端映射了、上游没产出：映射键 − grv_latest 键 ≠ ∅ ⇒ 告警
  3. 【综合分黑箱】参与 global_composite 的 grv 字段（从 geo_risk_vector.py 动态解析）
     若不在前端映射 ⇒ 告警（B 类「看不见却影响结论」的直接守门）
  4. 【仪器自检】输入不可读 / 映射表解析为空 ⇒ **响亮失败**（防止守卫自己变成静默失败源）

失败 → ntfy 推送（内容不含任何密钥值）→ exit 1；全过 → 静默 exit 0。
用法：check_grv_dimensions.py [--heartbeat]（heartbeat=全过时也推一条，供心跳防「脚本死了没声音」）
      [--grv PATH] [--ts PATH] [--py PATH]（供对照实验注入副本，不碰真文件）
依赖 env：NTFY_TOPIC（cron.d 提供；缺省只打印不推送）。
"""
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(os.environ.get("REPO_DIR", Path(__file__).resolve().parent.parent))
RUNTIME = Path(os.environ.get("RUNTIME_DIR", REPO.parent / "macro-scan"))

DEFAULT_GRV = RUNTIME / "data" / "grv_latest.json"
DEFAULT_TS = REPO / "kaiyang" / "src" / "config" / "grvDimensions.ts"
DEFAULT_PY = REPO / "macro-scan" / "核心代码" / "geo_risk_vector.py"

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

# 非维度顶层键：_schema_version/_derived_meta 为结构字段（下划线前缀自动排除），
# 其余为时间戳/原始值/质量标记，不是归一化维度 ⇒ 不参与对账，否则每次误报。
# 新增同类键时请同步此集合（并在输出里打印实际分类供人工复核）。
NON_DIMENSION_KEYS = {
    "updated", "gdelt_updated", "gpr_twn_raw", "gpr_twn_date", "source_quality",
}

# 已裁定「暂不映射」的维度（A 类待用户逐维决策；决策落地后应从本集合移除并补映射）。
# ⚠️ 这里不是豁免缺陷，只是把「已知未决」与「新漂移」区分开，避免告警文案误导。
DECIDED_UNMAPPED = set()


def _push(title: str, message: str) -> None:
    if not NTFY_TOPIC:
        print(f"[ntfy 未配置] {title}\n{message}")
        return
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title.encode("utf-8")[:200], "Tags": "warning"},
        )
        urllib.request.urlopen(req, timeout=8).read()
    except Exception as e:
        print(f"[ntfy 推送失败（非阻断）] {e}")


def load_backend_keys(grv_path: Path):
    """返回 (数值键集合, 全部顶层键集合)；不可读/为空 ⇒ 抛异常（仪器失效必须响亮）。"""
    if not grv_path.exists():
        raise RuntimeError(f"grv_latest.json 不存在：{grv_path}")
    data = json.loads(grv_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"grv_latest.json 顶层不是对象：{grv_path}")
    numeric = {k for k, v in data.items()
               if isinstance(v, (int, float)) and not isinstance(v, bool)}
    if not numeric:
        raise RuntimeError(f"grv_latest.json 无数值键（仪器失效？）：{grv_path}")
    return numeric, set(data.keys())


def load_mapped_keys(ts_path: Path):
    """从 grvDimensions.ts 解析 sourceKey；解析不到 ⇒ 抛异常（仪器失效）。"""
    if not ts_path.exists():
        raise RuntimeError(f"grvDimensions.ts 不存在：{ts_path}")
    src = ts_path.read_text(encoding="utf-8")
    keys = re.findall(r"sourceKey:\s*'([^']+)'", src)
    # 兼容 JS 对象写法（无引号 key）与双引号
    keys += re.findall(r'sourceKey:\s*"([^"]+)"', src)
    keys = [k for k in keys if k]
    if not keys:
        raise RuntimeError(f"grvDimensions.ts 未解析到任何 sourceKey：{ts_path}")
    # 条目计数以 sourceKey 为准：按 `{\n id: '` 计数会漏掉块内带注释的条目（japan_monetary 即如此）
    return set(keys), len(set(keys))


def load_composite_inputs(py_path: Path, backend_keys):
    """从 geo_risk_vector.py 的 global_composite 公式里，挑出来自 grv 输出的字段名。"""
    if not py_path.exists():
        return set()
    src = py_path.read_text(encoding="utf-8")
    block = []
    for line in src.split("\n"):
        if "global_composite" in line and "=" in line:
            block.append(line)
    if not block:
        return set()
    text = "\n".join(block)
    idents = set(re.findall(r"\b([a-z][a-z0-9_]{3,})\b", text))
    return {i for i in idents if i in backend_keys}


def main() -> int:
    argv = sys.argv[1:]
    heartbeat = "--heartbeat" in argv

    def opt(name, default):
        return Path(argv[argv.index(name) + 1]) if name in argv else Path(default)

    grv_path = opt("--grv", DEFAULT_GRV)
    ts_path = opt("--ts", DEFAULT_TS)
    py_path = opt("--py", DEFAULT_PY)

    try:
        backend, all_keys = load_backend_keys(grv_path)
        mapped, n_dims = load_mapped_keys(ts_path)
    except Exception as e:
        msg = f"仪器失效（守卫自身不可用，必须人工介入）：{e}"
        print(msg)
        _push("GRV 维度守卫 · 仪器失效", msg)
        return 1

    dims = {k for k in backend if not k.startswith("_") and k not in NON_DIMENSION_KEYS}
    unmapped = dims - mapped                    # ① 上游算了、前端没显示
    missing_upstream = mapped - all_keys        # ② 前端映射了、上游没产出
    composite_inputs = load_composite_inputs(py_path, backend)
    blind_in_composite = composite_inputs - mapped  # ③ 影响综合分却看不见

    print(f"[GRV 对账] 上游数值键 {len(backend)}（维度 {len(dims)}） / 前端映射 {n_dims} / "
          f"综合分 grv 输入 {sorted(composite_inputs)}")
    print(f"[GRV 对账] ①未映射(算了不显示) {len(unmapped)}: {sorted(unmapped)}")
    print(f"[GRV 对账] ②映射了但上游缺失 {len(missing_upstream)}: {sorted(missing_upstream)}")
    print(f"[GRV 对账] ③进综合分却未映射 {len(blind_in_composite)}: {sorted(blind_in_composite)}")

    problems = []
    if unmapped:
        known = sorted(unmapped & DECIDED_UNMAPPED)
        fresh = sorted(unmapped - DECIDED_UNMAPPED)
        if fresh:
            problems.append(f"① 上游算了但前端未映射（新）{len(fresh)}: {fresh}")
        if known:
            problems.append(f"① 已登记未决（A 类待处置）{len(known)}: {known}")
    if missing_upstream:
        problems.append(f"② 前端映射但上游无数据 {len(missing_upstream)}: {sorted(missing_upstream)}")
    if blind_in_composite:
        problems.append(f"③ 参与综合分但未映射（看不见却影响结论）{len(blind_in_composite)}: "
                        f"{sorted(blind_in_composite)}")

    if not problems:
        if heartbeat:
            _push("GRV 维度守卫 · 心跳", "三项对账全过：无未映射 / 无缺失 / 综合分输入均可见")
        return 0

    msg = "\n".join(problems)
    print("[GRV 对账] 发现问题：\n" + msg)
    _push("GRV 维度守卫 · 发现漂移", msg[:900])
    return 1


if __name__ == "__main__":
    sys.exit(main())