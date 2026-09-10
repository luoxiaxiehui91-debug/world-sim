"""
update_kb_numbers.py — 知识库数值字段自动更新脚本

运行时机：每月1日 cron（建议跟在 verify_predictions 之后）
作用范围：仅替换 .md 文件中的数值字段，不修改叙事段落
完成后：自动重建 RAG 索引，发 ntfy 通知

用法：
    docker exec macro-scan python /app/update_kb_numbers.py
"""

import os
import re
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# ── 路径配置 ──────────────────────────────────────────────
APP_DIR  = Path(__file__).parent
KB_ROOT  = Path(os.environ.get("KB_ROOT") or (APP_DIR.parent / "知识库"))
KB_DIR   = KB_ROOT / "财经知识库"
DATA_DIR = APP_DIR.parent / "data"

OUTBOUND_PROXY = os.environ.get("OUTBOUND_PROXY", "")
NTFY_TOPIC     = os.environ.get("NTFY_TOPIC", "")
FRED_API_KEY   = ""
try:
    from optim_config import FRED_API_KEY
except ImportError:
    FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("kb_update")

# ── 数据获取 ──────────────────────────────────────────────

def fetch_fred_series(series_ids: list[str], timeout: int = 15) -> dict:
    """从 FRED 批量拉取最新值，返回 {series_id: float}"""
    import concurrent.futures

    def _get_one(sid):
        try:
            from fredapi import Fred
            fred = Fred(api_key=FRED_API_KEY)
            s = fred.get_series(sid)
            return sid, float(s.dropna().iloc[-1])
        except Exception as e:
            log.warning(f"FRED {sid} 失败: {e}")
            return sid, None

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(_get_one, sid): sid for sid in series_ids}
        for f in concurrent.futures.as_completed(futures, timeout=timeout * len(series_ids)):
            try:
                sid, val = f.result(timeout=timeout)
                results[sid] = val
            except Exception:
                results[futures[f]] = None
    return results


def fetch_china_data() -> dict:
    """从 akshare 拉取中国核心指标，失败返回 None"""
    try:
        sys.path.insert(0, str(APP_DIR))
        from fetch_china_data_akshare import get_china_indicator
        keys = ["pmi_mfg", "cpi", "ppi", "gdp_growth", "m2_growth"]
        return {k: get_china_indicator(k) for k in keys}
    except Exception as e:
        log.warning(f"akshare 中国数据失败: {e}")
        return {}


def get_current_regime() -> str:
    """读取最新 regime_history.json，返回当前体制字符串"""
    try:
        hist_file = DATA_DIR / "regime_history.json"
        if hist_file.exists():
            data = json.loads(hist_file.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data[-1].get("regime", "unknown")
    except Exception as e:
        log.warning(f"体制读取失败: {e}")
    return "unknown"

# ── 文件更新工具 ───────────────────────────────────────────

def replace_in_file(file_path: Path, replacements: list[tuple]) -> int:
    """
    replacements: [(pattern, new_value, description), ...]
    返回实际替换次数
    """
    if not file_path.exists():
        log.warning(f"文件不存在: {file_path}")
        return 0

    text = file_path.read_text(encoding="utf-8")
    count = 0
    for pattern, new_val, desc in replacements:
        new_text, n = re.subn(pattern, new_val, text)
        if n:
            log.info(f"  ✓ {desc} → {new_val.strip()}")
            text = new_text
            count += n
        else:
            log.warning(f"  ✗ 未匹配: {desc}")

    if count:
        # 原子写入
        tmp = file_path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, file_path)

    return count


# ── 各文件更新规则 ─────────────────────────────────────────

def update_macro_baseline(fred: dict, china: dict, regime: str):
    """2026全球宏观基准情景.md — 数据表格数值"""
    f = KB_DIR / "21_专题报告" / "2026全球宏观基准情景.md"

    rules = []

    # 联邦基金利率
    if fred.get("DFF"):
        ffr = f"{fred['DFF']:.2f}%"
        rules.append((
            r"(联邦基金利率.*?\*\*)([\d.]+%)",
            lambda m: m.group(1) + ffr,
            f"FFR → {ffr}"
        ))

    # 失业率
    if fred.get("UNRATE"):
        unrate = f"{fred['UNRATE']:.1f}%"
        rules.append((
            r"(\| UNRATE\s*\|.*?\*\*)([\d.]+%)",
            lambda m: m.group(1) + unrate,
            f"UNRATE → {unrate}"
        ))

    # CPI
    if fred.get("CPIAUCSL_YOY"):
        cpi = f"{fred['CPIAUCSL_YOY']:.2f}%"
        rules.append((
            r"(\| CPI YoY\s*\|.*?\*\*)([\d.]+%)",
            lambda m: m.group(1) + cpi,
            f"CPI YoY → {cpi}"
        ))

    # 萨姆规则（从 FRED SAHMREALTIME 系列，若无则跳过）
    if fred.get("SAHMREALTIME"):
        sahm = f"{fred['SAHMREALTIME']:.1f}"
        rules.append((
            r"(萨姆规则.*?\*\*)([\d.]+)",
            lambda m: m.group(1) + sahm,
            f"萨姆规则 → {sahm}"
        ))

    # 最后更新时间戳
    today = datetime.now().strftime("%Y-%m-%d")
    rules.append((
        r"(\*最后更新：)([\d\-]+)",
        r"\g<1>" + today,
        f"更新时间戳 → {today}"
    ))

    _apply_lambda_rules(f, rules, "2026全球宏观基准情景.md")


def update_central_bank_framework(fred: dict):
    """央行决策框架.md — FFR / CPI / 泰勒规则"""
    f = KB_DIR / "04_分析框架" / "央行决策框架.md"

    rules = []
    if fred.get("DFF"):
        ffr = f"{fred['DFF']:.2f}%"
        rules.append((r"(FFR.*?)([\d.]+%)(.*?实际)", r"\g<1>" + ffr + r"\3", f"FFR → {ffr}"))

    if fred.get("CPIAUCSL_YOY"):
        cpi = f"{fred['CPIAUCSL_YOY']:.2f}%"
        rules.append((r"(CPI\s+)([\d.]+%)", r"\g<1>" + cpi, f"CPI → {cpi}"))

    _apply_simple_rules(f, rules, "央行决策框架.md")


def update_sector_rotation(regime: str):
    """板块轮动与经济周期.md — 当前体制映射段落"""
    f = KB_DIR / "04_分析框架" / "板块轮动与经济周期.md"

    regime_labels = {
        "expansion":     "扩张期（GDP↑，通胀可控）",
        "stagflation":   "滞胀期（增速↓，通胀↑）",
        "late_cycle":    "后期周期 / 滞胀边界（增速放缓+通胀粘性）",
        "recession":     "衰退期（GDP↓，通胀↓）",
        "crisis":        "危机期（VIX>40，流动性冲击）",
        "soft_landing":  "软着陆（增速温和，通胀回落）",
    }
    label = regime_labels.get(regime, regime)
    today = datetime.now().strftime("%Y-%m")

    rules = [
        (
            r"(体制：\*\*)[^*]+(\*\*)",
            r"\g<1>" + label + r"\2",
            f"当前体制 → {label}"
        ),
        (
            r"(当前体制映射（)\d{4}-\d{2}(\))",
            r"\g<1>" + today + r"\2",
            f"体制映射日期 → {today}"
        ),
    ]
    _apply_simple_rules(f, rules, "板块轮动与经济周期.md")


def update_geo_events_meta():
    """地缘事件日志.json — 仅更新 meta.last_update 时间戳（内容不自动改）"""
    f = KB_DIR / "02_核心变量因果链" / "地缘事件日志.json"
    if not f.exists():
        return
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        data["meta"]["last_checked"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, f)
        log.info("  ✓ 地缘事件日志 last_checked 更新")
    except Exception as e:
        log.warning(f"地缘事件日志更新失败: {e}")


# ── 内部工具 ───────────────────────────────────────────────

def _apply_simple_rules(f: Path, rules: list, name: str):
    if not f.exists():
        log.warning(f"文件不存在: {name}")
        return
    log.info(f"更新 {name}:")
    replacements = [(p, r, d) for p, r, d in rules]
    replace_in_file(f, replacements)


def _apply_lambda_rules(f: Path, rules: list, name: str):
    """支持 lambda replacement 的版本"""
    if not f.exists():
        log.warning(f"文件不存在: {name}")
        return
    log.info(f"更新 {name}:")
    text = f.read_text(encoding="utf-8")
    count = 0
    for pattern, repl, desc in rules:
        if callable(repl):
            new_text = re.sub(pattern, repl, text)
        else:
            new_text, n = re.subn(pattern, repl, text)
            count += n
        if new_text != text:
            log.info(f"  ✓ {desc}")
            text = new_text
            count += 1
        else:
            log.warning(f"  ✗ 未匹配: {desc}")
    if count:
        tmp = f.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, f)


def rebuild_rag_index():
    """重建向量索引"""
    idx_script = APP_DIR / "build_rag_index.py"
    if not idx_script.exists():
        log.warning("build_rag_index.py 不存在，跳过向量索引重建")
        return
    import subprocess
    log.info("重建 RAG 向量索引...")
    r = subprocess.run([sys.executable, str(idx_script)], capture_output=True, text=True, timeout=300)
    if r.returncode == 0:
        log.info("  ✓ 向量索引重建完成")
    else:
        log.warning(f"  ✗ 向量索引重建失败: {r.stderr[:200]}")


def send_ntfy(title: str, body: str):
    try:
        import urllib.request
        proxies = {"https": OUTBOUND_PROXY} if OUTBOUND_PROXY else {}
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode(),
            headers={"Title": title, "Priority": "default"},
            method="POST"
        )
        if OUTBOUND_PROXY:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"https": OUTBOUND_PROXY})
            )
            opener.open(req, timeout=10)
        else:
            urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.warning(f"ntfy 发送失败: {e}")


# ── 主流程 ─────────────────────────────────────────────────

def main():
    log.info("=" * 50)
    log.info("知识库数值自动更新开始")
    log.info("=" * 50)

    # 1. 拉取数据
    log.info("拉取 FRED 数据...")
    fred_raw = fetch_fred_series([
        "DFF",           # 联邦基金利率
        "UNRATE",        # 失业率
        "CPIAUCSL",      # CPI（需手动算同比，见下）
        "SAHMREALTIME",  # 萨姆规则
        "DGS10",         # 10Y 美债收益率
        "DGS2",          # 2Y 美债收益率
        "BAMLH0A0HYM2",  # HY 利差
    ])

    # CPI 同比：需要12个月前的值，用简化计算
    fred = dict(fred_raw)
    try:
        from fredapi import Fred
        import concurrent.futures
        def _get_cpi_yoy():
            f2 = Fred(api_key=FRED_API_KEY)
            s = f2.get_series("CPIAUCSL")
            s = s.dropna()
            if len(s) >= 13:
                return (s.iloc[-1] / s.iloc[-13] - 1) * 100
            return None
        with concurrent.futures.ThreadPoolExecutor(1) as ex:
            fred["CPIAUCSL_YOY"] = ex.submit(_get_cpi_yoy).result(timeout=15)
    except Exception:
        fred["CPIAUCSL_YOY"] = None

    log.info(f"  FFR={fred.get('DFF')} UNRATE={fred.get('UNRATE')} CPI_YOY={fred.get('CPIAUCSL_YOY')}")

    log.info("拉取中国数据...")
    china = fetch_china_data()

    log.info("读取当前体制...")
    regime = get_current_regime()
    log.info(f"  当前体制: {regime}")

    # 2. 更新各文件
    update_macro_baseline(fred, china, regime)
    update_central_bank_framework(fred)
    update_sector_rotation(regime)
    update_geo_events_meta()

    # 3. 重建 RAG 索引
    rebuild_rag_index()

    # 4. 通知
    today = datetime.now().strftime("%Y-%m-%d")
    summary_lines = [
        f"FFR: {fred.get('DFF', 'N/A')}%",
        f"UNRATE: {fred.get('UNRATE', 'N/A')}%",
        f"CPI YoY: {fred.get('CPIAUCSL_YOY', 'N/A'):.2f}%" if fred.get('CPIAUCSL_YOY') else "CPI: N/A",
        f"体制: {regime}",
        "",
        "⚠️ 叙事段落、地缘事件需人工/AI审阅",
        "参考：知识库/KB_UPDATE_GUIDE.md",
    ]
    send_ntfy(
        f"知识库数值已自动更新 {today}",
        "\n".join(summary_lines)
    )

    log.info("=" * 50)
    log.info("完成。叙事段落和地缘事件请参考 KB_UPDATE_GUIDE.md 进行人工审阅。")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
