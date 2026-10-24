"""
update_kb_numbers.py — 知识库数值字段自动更新脚本

运行时机：每月 1 日 09:05（`scheduler.py:96`，dom=1）
作用范围：仅替换 .md 文件中的数值字段，不修改叙事段落
完成后：自动重建 RAG 索引，发 ntfy 通知

退出码语义（v3.8.86 起，fail-loud）：
    0 = 全部环节成功
    1 = 下列任一成立：目标文件缺失 / 必中锚点 0 命中 / 数值规则全灭 /
        RAG 索引重建失败 / ntfy 推送失败
    「部分数值规则未命中」不判失败，但会 WARN 记日志并写进通知正文。

KB 根目录解析：
    优先环境变量 `KB_ROOT`；否则按候选目录取第一个存在的
    （容器内真实挂载是 `/workspace/知识库`，`/app` 平铺导致 `APP_DIR.parent` 为 `/`，
    曾因此解析出并不存在的 `/知识库`，使本脚本连续数月空转，CHG-20261023T080227）。

用法：
    docker exec macro-scan-macro-scan-1 python3 /app/update_kb_numbers.py
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


def _resolve_kb_root() -> Path:
    """解析知识库根目录。

    历史坑（CHG-20261023T080227）：容器内 `/app` 是平铺的 bind mount，
    `APP_DIR.parent` 解析成 `/`，于是 KB_ROOT 变成并不存在的 `/知识库`；
    四个更新函数全部走「文件不存在」早退，脚本却仍 exit 0 打印「完成。」。
    ⇒ 改为候选目录探测：env 优先，其次取第一个真实存在的目录。
    """
    env = os.environ.get("KB_ROOT")
    if env:
        return Path(env)
    candidates = [
        Path("/workspace/知识库"),      # 容器内真实挂载（docker-compose volumes）
        APP_DIR.parent / "知识库",      # 历史布局：<runtime>/知识库
        APP_DIR / "知识库",             # 兜底：与脚本同级的副本
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]  # 都不存在时返回首选，由 main() 的文件缺失断言响亮失败


KB_ROOT  = _resolve_kb_root()
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
    """读取最新 regime_history.json，返回当前体制字符串。

    ⚠️ 已知契约缺口（2026-10-24 实测，未修，见 CHG-20261024T*）：
    `regime_detector._save_history()` 落盘的记录只有
    `{quarter, vix, baa10y, t10y2y, unrate_3m, vix_z, baA_z, t10_z}` —— **没有 `regime` 键**；
    当前体制存在模块级 `_prev_regime` 里，从不写文件。
    ⇒ 本函数**恒返回 "unknown"**。调用方（`update_sector_rotation`）据此跳过写入，
    宁可不更新也不把 `unknown` 塞进知识库。要真正恢复需统一读写契约（落盘 regime）。
    """
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

def _apply_rules(file_path: Path, rules: list, name: str) -> dict:
    """应用替换规则并回传结果，供 main() 做写入量断言。

    rules 每项为 ``(pattern, repl, desc)`` 或 ``(pattern, repl, desc, required)``；
    ``repl`` 可为字符串（支持 ``\\g<1>`` 反向引用）或 callable（收到 match 对象）。

    ``required=True`` 表示「必中锚点」：它 0 命中说明文档结构已变，
    即使其它规则命中也不能算成功（否则文件被写、mtime 变新，会掩盖数值没更新）。

    返回 dict：
        name / missing_file / hits（总命中）/ data_hits（非锚点命中）/
        missed（未命中描述）/ required_missed（未命中的锚点）
    """
    res = {"name": name, "missing_file": False, "hits": 0, "data_hits": 0,
           "missed": [], "required_missed": []}
    if not file_path.exists():
        log.warning(f"文件不存在: {name}（{file_path}）")
        res["missing_file"] = True
        return res

    log.info(f"更新 {name}:")
    # 🔴 必须按字节读写：KB 里这几份文档是 **CRLF** 行尾，用 read_text/write_text
    # 会被通用换行转换整份改写成 LF ⇒ git diff 变成整文件替换（测试 T1 实测 234 行全变）。
    text = file_path.read_bytes().decode("utf-8")
    for rule in rules:
        pattern, repl, desc = rule[0], rule[1], rule[2]
        required = bool(rule[3]) if len(rule) > 3 else False
        new_text, n = re.subn(pattern, repl, text)
        if n:
            log.info(f"  ✓ {desc}（{n} 处）")
            text = new_text
            res["hits"] += n
            if not required:
                res["data_hits"] += n
        else:
            log.warning(f"  ✗ 未匹配: {desc}" + ("【必中锚点】" if required else ""))
            res["missed"].append(desc)
            if required:
                res["required_missed"].append(desc)

    if res["hits"]:
        # 原子写入（同样按字节写，保 CRLF 原样）
        tmp = file_path.with_suffix(".tmp")
        tmp.write_bytes(text.encode("utf-8"))
        os.replace(tmp, file_path)
    return res



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

    # 最后更新时间戳（必中锚点：它 0 命中即说明文件结构已变，此时其余规则也不可信）
    today = datetime.now().strftime("%Y-%m-%d")
    rules.append((
        r"(\*最后更新：)([\d\-]+)",
        r"\g<1>" + today,
        f"更新时间戳 → {today}",
        True,
    ))

    return _apply_rules(f, rules, "2026全球宏观基准情景.md")


def update_central_bank_framework(fred: dict):
    """央行决策框架.md — FFR / CPI / 泰勒规则"""
    f = KB_DIR / "04_分析框架" / "央行决策框架.md"

    rules = []
    if fred.get("DFF"):
        ffr = f"{fred['DFF']:.2f}%"
        # v3.8.86：旧规则 `(FFR.*?)([\d.]+%)(.*?实际)` 强制要求数字后跟「实际」，
        # 而文档实为 `- FFR 当前 = 3.63%（2024年9月开始…` ⇒ 永久 0 命中。
        # 改用行内锚点，避免 `.*?` 跨句误伤「FFR稳定在3.5-3.75%区间」那句。
        rules.append((r"(FFR 当前\s*=\s*)([\d.]+%)", r"\g<1>" + ffr, f"FFR → {ffr}"))

    if fred.get("CPIAUCSL_YOY"):
        cpi = f"{fred['CPIAUCSL_YOY']:.2f}%"
        rules.append((r"(CPI\s+)([\d.]+%)", r"\g<1>" + cpi, f"CPI → {cpi}"))

    return _apply_rules(f, rules, "央行决策框架.md")


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
    today = datetime.now().strftime("%Y-%m")
    rules = []

    # 🔴 regime 拿不到有效值时**不写**（v3.8.87）：
    # `regime_detector` 把当前体制存在模块级 `_prev_regime`、**从不落盘**，
    # 而本脚本去读 `regime_history.json` 的 `regime` 键（那批记录里根本没有该键）
    # ⇒ 恒拿不到，旧逻辑会把 `体制：**unknown**` 写进知识库并被 RAG 向量化。
    # 拿不到就跳过 + warning，宁可不更新也不塞垃圾。
    if regime and regime != "unknown":
        label = regime_labels.get(regime, regime)
        # label 形如 "后期周期 / 滞胀边界（增速放缓+通胀粘性）" —— 名称 + 内层描述括号；
        # 文档原结构是 `**名称**（描述）`。旧写法只替换 `**…**` 内部，
        # 外层 `（描述）` 留着 ⇒ 写成 `**…（描述）**（描述）`，括号重复（v3.8.87 修）。
        if "（" in label and label.endswith("）"):
            name, _, rest = label.partition("（")
            desc = rest[:-1]
        else:
            name, desc = label, ""

        def _repl(m, nm=name, ds=desc):
            return m.group(1) + nm + m.group(2) + (("（%s）" % ds) if ds else "")

        rules.append((
            r"(体制：\*\*)[^*]*(\*\*)(（[^）]*）)?",
            _repl,
            f"当前体制 → {name}（{desc}）" if desc else f"当前体制 → {name}",
        ))
    else:
        log.warning(f"体制值为 {regime!r}（regime_history.json 无 regime 键 / 读不到），"
                    f"跳过体制规则，不写入知识库")

    rules.append((
        # v3.8.86：闭合括号原写成半角 `\)`，文档实为全角 `）` ⇒ 永久 0 命中
        r"(当前体制映射（)\d{4}-\d{2}(）)",
        r"\g<1>" + today + r"\2",
        f"体制映射日期 → {today}",
        True,
    ))
    return _apply_rules(f, rules, "板块轮动与经济周期.md")


def update_geo_events_meta():
    """地缘事件日志.json — 仅更新 meta.last_checked 时间戳（内容不自动改）

    v3.8.86：改为**定点替换**，不再 json.loads→json.dumps 整体重排
    （重排会把整份文件格式化，等同整文件改写，且丢失原有键序/缩进风格）。
    """
    f = KB_DIR / "02_核心变量因果链" / "地缘事件日志.json"
    if not f.exists():
        log.warning(f"文件不存在: 地缘事件日志.json（{f}）")
        return
    try:
        text = f.read_bytes().decode("utf-8")
        # 字段实名是 `last_update`（schema 里没有 `last_checked`）。旧实现写的是
        # `data["meta"]["last_checked"]` ⇒ 每次 KeyError 被 except 吞成一行 warning，
        # 等于从未更新过。此处按 docstring 原意更新 `last_update`。
        new_text, n = re.subn(
            r'("last_update"\s*:\s*")[^"]*(")',
            r"\g<1>" + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + r"\2",
            text,
            count=1,
        )
        if n == 0:
            log.warning("地缘事件日志：未找到 last_update 字段，未修改")
            return
        tmp = f.with_suffix(".tmp")
        tmp.write_bytes(new_text.encode("utf-8"))
        os.replace(tmp, f)
        log.info("  ✓ 地缘事件日志 last_update 更新")
    except Exception as e:
        log.warning(f"地缘事件日志更新失败: {e}")


# ── 内部工具 ───────────────────────────────────────────────
# v3.8.86：原 `replace_in_file` / `_apply_simple_rules` / `_apply_lambda_rules`
# 三个写文件入口合并为 `_apply_rules`（见上），以便统一回传写入量做断言。



def rebuild_rag_index() -> bool:
    """重建向量索引。返回 True=成功 / False=失败（供调用方 fail-loud）。"""
    idx_script = APP_DIR / "build_rag_index.py"
    if not idx_script.exists():
        log.warning("build_rag_index.py 不存在，跳过向量索引重建")
        return True   # 脚本本就不存在属环境既定状态，不算本次失败
    import subprocess
    log.info("重建 RAG 向量索引...")
    try:
        r = subprocess.run([sys.executable, str(idx_script)],
                           capture_output=True, text=True, timeout=300)
    except Exception as e:
        log.error(f"  ✗ 向量索引重建异常: {e}")
        return False
    if r.returncode == 0:
        log.info("  ✓ 向量索引重建完成")
        return True
    # 诊断信息：stderr 常常为空（子进程把错误打到 stdout），两个都记
    log.error(f"  ✗ 向量索引重建失败 rc={r.returncode}")
    log.error(f"    stderr: {(r.stderr or '')[:300]}")
    log.error(f"    stdout: {(r.stdout or '')[:300]}")
    return False


def send_ntfy(title: str, body: str) -> bool:
    """推送通知。返回 True=已发送 / False=失败（供调用方 fail-loud）。

    用 `requests.put(json=...)`：标题与正文走 **JSON body**，不进 HTTP header ⇒ 中文不会
    触发 latin-1 编码错误（旧写法 `headers={"Title": title}` 对中文标题必然抛
    `UnicodeEncodeError`，见 question 20261018-...-kb-update-silent-failure.md）。
    模板来源：`scripts/check_llm_config.py::_push`（周一心跳实测可发中文）。
    """
    if not NTFY_TOPIC:
        log.warning("NTFY_TOPIC 未配置，跳过推送")
        return False
    try:
        import requests
        proxies = {"https": OUTBOUND_PROXY, "http": OUTBOUND_PROXY} if OUTBOUND_PROXY else None
        requests.put(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            json={"topic": NTFY_TOPIC, "title": title, "message": body},
            timeout=15,
            proxies=proxies,
        )
        return True
    except Exception as e:
        log.error(f"ntfy 发送失败: {e}")
        return False


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
    _cpi_yoy = None
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
            _cpi_yoy = ex.submit(_get_cpi_yoy).result(timeout=15)
    except Exception as e:
        # v3.8.86：旧实现无条件 `fred["CPIAUCSL_YOY"] = None`，会把 fetch_fred_series
        # 已经拿到的值冲掉 ⇒ CPI 规则被静默跳过。改为「算出来才覆盖，否则保留原值」。
        log.warning(f"CPI 同比计算失败，沿用已拉取值: {e}")
    if _cpi_yoy is not None:
        fred["CPIAUCSL_YOY"] = _cpi_yoy
    else:
        fred.setdefault("CPIAUCSL_YOY", None)

    log.info(f"  FFR={fred.get('DFF')} UNRATE={fred.get('UNRATE')} CPI_YOY={fred.get('CPIAUCSL_YOY')}")

    log.info("拉取中国数据...")
    china = fetch_china_data()

    log.info("读取当前体制...")
    regime = get_current_regime()
    log.info(f"  当前体制: {regime}")

    # 2. 更新各文件（v3.8.86：回传写入量，供下方断言使用）
    applied = [
        update_macro_baseline(fred, china, regime),
        update_central_bank_framework(fred),
        update_sector_rotation(regime),
    ]
    update_geo_events_meta()

    # 2b. 写入量断言 —— 三条互相独立的失败条件
    #     ① 文件缺失：路径/挂载问题（本次踩的坑）② 必中锚点未命中：文档结构已变
    #     ③ 数值规则全灭：数据没拉到或规则整体失效 ⇒ 等于没更新
    missing    = [r["name"] for r in applied if r["missing_file"]]
    anchor_bad = [f'{r["name"]} → {"、".join(r["required_missed"])}'
                  for r in applied if r["required_missed"]]
    data_hits  = sum(r["data_hits"] for r in applied)
    partial    = [f'{r["name"]} → {d}'
                  for r in applied for d in r["missed"] if d not in r["required_missed"]]

    log.info(f"写入统计：数值命中 {data_hits} 处，未命中 {len(partial)} 条，"
             f"缺文件 {len(missing)} 个，锚点失败 {len(anchor_bad)} 个")

    # 3. 重建 RAG 索引
    ok_rag = rebuild_rag_index()

    # 4. 通知
    today = datetime.now().strftime("%Y-%m-%d")
    summary_lines = [
        f"FFR: {fred.get('DFF', 'N/A')}%",
        f"UNRATE: {fred.get('UNRATE', 'N/A')}%",
        f"CPI YoY: {fred.get('CPIAUCSL_YOY', 'N/A'):.2f}%" if fred.get('CPIAUCSL_YOY') else "CPI: N/A",
        f"体制: {regime}",
        f"数值命中: {data_hits} 处",
    ]
    if partial:
        summary_lines.append("")
        summary_lines.append(f"⚠️ 未命中的数值规则（{len(partial)} 条，需人工核对文档措辞）：")
        summary_lines.extend(f"  · {p}" for p in partial[:8])
        if len(partial) > 8:
            summary_lines.append(f"  · …其余 {len(partial) - 8} 条见日志")
    summary_lines.extend([
        "",
        "⚠️ 叙事段落、地缘事件需人工/AI审阅",
        "参考：知识库/KB_UPDATE_GUIDE.md",
    ])
    ok_ntfy = send_ntfy(
        f"知识库数值已自动更新 {today}",
        "\n".join(summary_lines)
    )

    # 5. 判定（fail-loud）
    problems = []
    if missing:
        problems.append(f"目标文件缺失: {'、'.join(missing)}")
    if anchor_bad:
        problems.append(f"必中锚点未命中: {'; '.join(anchor_bad)}")
    if data_hits == 0:
        problems.append("数值规则全部未命中（等于没更新）")
    if not ok_rag:
        problems.append("RAG 索引重建失败")
    if not ok_ntfy:
        problems.append("ntfy 推送失败")

    log.info("=" * 50)
    if problems:
        log.error(f"未完成：{'；'.join(problems)} —— 脚本以非零退出码结束（面板将如实标记为失败）")
        log.info("=" * 50)
        sys.exit(1)
    log.info("完成。叙事段落和地缘事件请参考 KB_UPDATE_GUIDE.md 进行人工审阅。")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
