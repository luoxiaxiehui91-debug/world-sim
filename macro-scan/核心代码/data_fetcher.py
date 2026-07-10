#!/usr/bin/env python3
"""
数据获取层（Layer A）

从 run_macro_analysis.py 提取的数据获取函数：
- 缓存管理：_load_cache, _save_cache, _cache_age_days, _is_cache_stale
- FRED代理检测：_detect_fred_proxy, _try_set_fred_proxy
- 中国数据解析：_parse_calendar_table, _parse_domestic_table, _try_extract_china,
                _get_china_from_local_csv, get_china_indicator
- FRED数据获取：get_fred_latest, get_fred_with_yoy, _compute_sahm_rule
- 快照获取：get_current_snapshot, get_china_current_snapshot
- RAG工具：_get_kb_dir_hash
"""

import os
import json
import time
import requests
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# =========================
# 配置常量（与 run_macro_analysis.py 保持同步）
# =========================

from optim_config import (
    FRED_API_KEY,
    WORKSPACE as BASE_DIR,
    KEY_INDICATORS,
)

REPORT_DIR = os.path.join(BASE_DIR, "docs", "分析报告")
CACHE_FILE = os.path.join(REPORT_DIR, ".indicator_cache.json")

# 代理配置（FRED API可能需要代理访问）
FRED_PROXIES = None  # 默认不用代理；如需代理设为 {"https": "http://192.168.31.108:7890"}
# 自动检测：如果直接访问FRED 403，尝试NAS代理
_AUTO_PROXY_TESTED = False

# 追踪连续403计数（超过阈值时切换代理）
_FRED_403_COUNT = 0
_FRED_403_THRESHOLD = 2  # 连续2次403就尝试切换代理

# KEY_INDICATORS 已迁至 optim_config.py，此处通过 import 使用

# 核心NeoData指标（中国）
# 每个指标包含: query(NeoData查询词), name(显示名), filter(结果过滤关键词), priority(优先表)
CHINA_INDICATORS = {
    # 经济增长
    "gdp_growth": {"query": "中国GDP增速", "name": "GDP增速", "filter": "GDP年率", "priority": "calendar",
                   "fallback_queries": ["GDP年率", "中国国内生产总值"]},
    "industrial_va": {"query": "规模以上工业增加值", "name": "工业增加值", "filter": "增加值年率", "priority": "calendar",
                      "fallback_queries": ["工业增加值:同比"]},
    # 通胀
    "cpi": {"query": "中国CPI", "name": "CPI同比", "filter": "CPI年率", "priority": "calendar",
            "fallback_queries": ["居民消费价格指数", "CPI同比"]},
    "ppi": {"query": "工业生产者出厂价格PPI", "name": "PPI同比", "filter": "PPI年率", "priority": "calendar",
            "fallback_queries": ["PPI同比", "PPI年率", "工业品出厂价格"]},
    # PMI
    "pmi_mfg": {"query": "中国制造业PMI", "name": "制造业PMI", "filter": "制造业PMI", "priority": "calendar",
                "fallback_queries": ["PMI", "制造业采购经理指数"]},
    "pmi_composite": {"query": "非制造业商务活动指数", "name": "综合PMI", "filter": "综合PMI", "priority": "domestic",
                      "fallback_queries": ["非制造业PMI", "服务业PMI"]},
    # 货币
    "m2_growth": {"query": "中国M2", "name": "M2同比", "filter": "(M2):同比", "priority": "domestic",
                  "fallback_queries": ["M2同比", "广义货币供应量"]},
    # 利率（HYP-7：供 scorer.py 泰勒缺口计算，替代硬编码 3.10）
    "cn_lpr": {"query": "贷款市场报价利率LPR", "name": "LPR1年期(%)", "filter": "LPR", "priority": "domestic",
               "fallback_queries": ["LPR", "贷款基准利率"]},
}

# 中国经济指标 akshare 数据源（替代已关闭的 NeoData）
try:
    from fetch_china_data_akshare import fetch_china_akshare
    _AKSHARE_CN_AVAILABLE = True
except ImportError:
    _AKSHARE_CN_AVAILABLE = False


# =========================
# RAG 工具函数
# =========================

def _get_kb_dir_hash(kb_dir: str) -> str:
    """计算知识库目录的内容哈希（基于各文件mtime），用于缓存失效检测。"""
    import hashlib
    h = hashlib.md5()
    try:
        for root, _, files in os.walk(kb_dir):
            for fname in sorted(files):
                if fname.endswith(".md"):
                    fpath = os.path.join(root, fname)
                    try:
                        mtime = os.path.getmtime(fpath)
                        h.update(f"{fpath}:{mtime:.0f}".encode())
                    except Exception:
                        pass
    except Exception:
        pass
    return h.hexdigest()


# =========================
# Layer A: 数据获取层
# =========================

def _load_cache() -> Dict:
    """加载指标缓存（含时间戳元数据）"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cache(cache: Dict):
    """保存指标缓存（写入时间戳元数据）"""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        cache["_meta"] = {"last_update": datetime.now().isoformat()}
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        # 追加中国指标历史时序（JSONL）
        try:
            from optim_config import DATA_DIR
            cn_snapshot = {
                k[3:]: v for k, v in cache.items()
                if k.startswith("CN_") and isinstance(v, dict)
            }
            if cn_snapshot:
                hist_path = os.path.join(DATA_DIR, "china_history.jsonl")
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(hist_path, "a", encoding="utf-8") as hf:
                    hf.write(json.dumps(
                        {"date": datetime.now().strftime("%Y-%m-%d"), "snapshot": cn_snapshot},
                        ensure_ascii=False,
                    ) + "\n")
        except Exception:
            pass
    except Exception:
        pass


def _cache_age_days(key: str) -> float:
    """计算缓存条目的年龄（天），返回 -1 表示无缓存"""
    cache = _load_cache()
    entry = cache.get(key)
    if not entry:
        return -1
    # 优先用 _meta.last_update，否则用条目的 date 字段推算
    last_update = cache.get("_meta", {}).get("last_update")
    if last_update:
        try:
            ts = datetime.fromisoformat(last_update)
            return (datetime.now() - ts).days
        except Exception:
            pass
    # fallback: 用条目 date 字段
    entry_date = entry.get("date", "")
    if entry_date and len(entry_date) >= 10:
        try:
            d = datetime.strptime(entry_date[:10], "%Y-%m-%d")
            return (datetime.now() - d).days
        except Exception:
            pass
    return -1


def _is_cache_stale(key: str, max_days: int = 7) -> bool:
    """检查缓存是否过期"""
    age = _cache_age_days(key)
    if age < 0:
        return True  # 无缓存 = 过期
    return age > max_days


def _detect_fred_proxy():
    """自动检测FRED API是否需要代理访问（首次检测）"""
    global FRED_PROXIES, _AUTO_PROXY_TESTED
    if _AUTO_PROXY_TESTED:
        return FRED_PROXIES
    _AUTO_PROXY_TESTED = True
    _try_set_fred_proxy()
    return FRED_PROXIES


def _try_set_fred_proxy() -> bool:
    """尝试切换到NAS代理（403时自动调用）"""
    global FRED_PROXIES
    # 代理地址优先取环境变量，容器内未设置则用默认LAN地址
    proxy_host = os.environ.get("OUTBOUND_PROXY", "http://192.168.31.108:7890")
    if not proxy_host:
        return False
    # 支持两种格式：完整 URL "http://host:port" 或裸地址 "host:port"
    proxy_url = proxy_host if proxy_host.startswith("http") else f"http://{proxy_host}"
    nas_proxy = {"https": proxy_url}
    try:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={}&file_type=json&limit=1&sort_order=desc".format(FRED_API_KEY),
            timeout=15, proxies=nas_proxy
        )
        if r.status_code == 200:
            FRED_PROXIES = nas_proxy
            print("  [FRED] 切换NAS代理成功")
            return True
        else:
            print(f"  [FRED] NAS代理返回{r.status_code}")
    except Exception as e:
        print(f"  [FRED] NAS代理不可用: {e}")
    return False


def _parse_calendar_table(content: str) -> List[Dict]:
    """解析日历表格（有现值/前值/预测值列）"""
    lines = content.strip().split('\n')
    if len(lines) < 2:
        return []
    header_line = None
    data_lines = []
    for line in lines:
        if '---' not in line and line.strip().startswith('|'):
            if header_line is None:
                header_line = line
            else:
                data_lines.append(line)
    if not data_lines or not header_line:
        return []
    header_cols = [c.strip() for c in header_line.split('|')]
    header_cols = [c for c in header_cols if c]
    results = []
    for line in data_lines:
        cols = [c.strip() for c in line.split('|')]
        cols = [c for c in cols if c]
        if len(cols) < 3:
            continue
        row = {}
        for i, h in enumerate(header_cols):
            if i < len(cols):
                row[h] = cols[i]
        results.append(row)
    # 按日期降序排序（最新在前）
    results.sort(key=lambda r: r.get("日期", "0").replace("/", ""), reverse=True)
    return results


def _parse_domestic_table(content: str) -> List[Dict]:
    """解析国内宏观指标表格"""
    lines = content.strip().split('\n')
    if len(lines) < 2:
        return []
    header_line = None
    data_lines = []
    for line in lines:
        if '---' not in line and line.strip().startswith('|'):
            if header_line is None:
                header_line = line
            else:
                data_lines.append(line)
    if not data_lines or not header_line:
        return []
    header_cols = [c.strip() for c in header_line.split('|')]
    header_cols = [c for c in header_cols if c]
    results = []
    for line in data_lines:
        cols = [c.strip() for c in line.split('|')]
        cols = [c for c in cols if c]
        if len(cols) < 4:
            continue
        row = {}
        for i, h in enumerate(header_cols):
            if i < len(cols):
                row[h] = cols[i]
        results.append(row)
    # 按统计截止日期降序排序（最新在前）
    def parse_date(s):
        # 格式: 20260331000000 -> 2026-03-31
        if not s or len(s) < 8:
            return "0"
        return s[:8]
    results.sort(key=lambda r: parse_date(r.get("统计截止日期", "0")), reverse=True)
    return results


def _try_extract_china(query_text: str, filter_kw: str) -> Tuple[Optional[str], Optional[float]]:
    """从NeoData提取中国数据的核心逻辑（被主函数和备用查询共用）"""
    blocks = []  # NeoData 已关闭
    if not blocks:
        return None, None

    # Phase 1: 日历表（含现值，最准确）
    for block in blocks:
        block_content = block.get("content", "")
        item_type = block.get("type", "")
        if "日历" in item_type and "现值" in block_content:
            rows = _parse_calendar_table(block_content)
            china_rows = [r for r in rows if "中国" in r.get("事件名称", "") or "中国" in r.get("地区", "")]
            if filter_kw:
                china_rows = [r for r in china_rows if filter_kw in r.get("事件名称", "")]
            if china_rows:
                row = china_rows[0]
                val_str = row.get("现值", "")
                if val_str and val_str not in ("--", "未公布", ""):
                    try:
                        val = float(val_str.replace("%", "").replace(",", ""))
                        return row.get("日期", ""), val
                    except ValueError:
                        pass

    # Phase 2: 国内宏观表（需过滤非中国数据）
    for block in blocks:
        block_content = block.get("content", "")
        item_type = block.get("type", "")
        if "国内宏观" in item_type and "数值" in block_content:
            rows = _parse_domestic_table(block_content)
            if filter_kw:
                filtered = [r for r in rows if filter_kw in r.get("指标名称", "")]
            else:
                filtered = rows
            cn_rows = [r for r in filtered if any(src in r.get("来源", "")
                       for src in ["国家统计局", "中国人民银行", "海关总署", "商务部"])]
            if not cn_rows:
                cn_rows = filtered
            if cn_rows:
                row = cn_rows[0]
                val_str = row.get("数值", "")
                if val_str and val_str not in ("--", "-"):
                    try:
                        val = float(val_str.replace("%", "").replace(",", ""))
                        date_str = row.get("统计截止日期", "")
                        return date_str, val
                    except ValueError:
                        pass

    return None, None


def _get_china_from_local_csv(indicator_key: str) -> tuple[str | None, float | None]:
    """
    从 data/china_history/ 读取中国指标最新值（fetch_china_data.py 生成）。
    用于 NeoData 失败时的本地数据层回退。
    mapping:
      gdp_growth     → gdp_growth.csv      (World Bank 年度)
      cpi            → cpi_yoy.csv         (FRED 衍生月频)
      pmi_mfg        → pmi_mfg.csv         (AkShare NBS 月频)
      m2_growth      → m2_growth.csv       (World Bank 年度)
      ppi            → ppi_yoy.csv         (AkShare NBS 月频)
      industrial_va  → industrial_output.csv (AkShare NBS 月频)
      pmi_composite  → (无本地源，跳过)
    """
    from optim_config import DATA_DIR
    _LOCAL_MAP = {
        "gdp_growth":   "gdp_growth",
        "cpi":          "cpi_yoy",
        "pmi_mfg":      "pmi_mfg",
        "m2_growth":    "m2_growth",
        "ppi":          "ppi_yoy",
        "industrial_va":"industrial_output",
    }
    local_id = _LOCAL_MAP.get(indicator_key)
    if not local_id:
        return None, None
    try:
        import pandas as pd
        path = os.path.join(DATA_DIR, "china_history", f"{local_id}.csv")
        if not os.path.exists(path):
            return None, None
        df = pd.read_csv(path).dropna(subset=["value"]).sort_values("date")
        if df.empty:
            return None, None
        last = df.iloc[-1]
        return str(last["date"]), float(last["value"])
    except Exception:
        return None, None


def get_china_indicator(indicator_key: str) -> Tuple[Optional[str], Optional[float]]:
    """
    获取中国指标数据（v5 akshare全量版）
    策略：akshare → 本地CSV回退 → 缓存回退
    """
    # NeoData 已关闭；优先用 akshare 全量替代（7个指标均已验证）
    if _AKSHARE_CN_AVAILABLE:
        date, value = fetch_china_akshare(indicator_key)
        if value is not None:
            print(f"    [AK] {indicator_key}: {value} ({date})")
            return date, value
        print(f"    [AK] {indicator_key} 无数据，降级到本地CSV")
    spec = CHINA_INDICATORS.get(indicator_key)
    if not spec:
        return None, None

    query_text = spec["query"]
    filter_kw = spec.get("filter", "")

    # 主查询
    date, value = _try_extract_china(query_text, filter_kw)
    if date is not None:
        return date, value

    # 备用查询关键词
    fallback_queries = spec.get("fallback_queries", [])
    for fbq in fallback_queries:
        date, value = _try_extract_china(fbq, filter_kw)
        if date is not None:
            print('    [备用查询成功] ' + fbq)
            return date, value

    # 本地 CSV 回退（fetch_china_data.py 生成的历史文件）
    date, value = _get_china_from_local_csv(indicator_key)
    if date is not None:
        print(f"    [LOCAL-CSV] {spec['name']}: {value} ({date})")
        return date, value

    # 缓存回退（仅当缓存不过期时使用）
    cache = _load_cache()
    cache_key = f"CN_{indicator_key}"
    if cache_key in cache and not _is_cache_stale(cache_key, max_days=3):
        cached = cache[cache_key]
        print(f"    [CACHED] {spec['name']}: {cached.get('value')} ({cached.get('date')})")
        return cached.get("date"), cached.get("value")

    return None, None


def get_fred_latest(series_id: str, retries: int = 3) -> Tuple[Optional[str], Optional[float]]:
    """获取FRED序列的最新值（含重试逻辑）"""
    for attempt in range(retries):
        try:
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&limit=14&sort_order=desc"
            )
            resp = requests.get(url, timeout=10, proxies=FRED_PROXIES)

            # FRED限速: 429 = too many requests
            if resp.status_code == 429:
                wait = (attempt + 1) * 2  # 2s, 4s, 6s
                print(f"  [FRED] {series_id} 限速，等待{wait}秒重试({attempt+1}/{retries})...")
                import time; time.sleep(wait)
                continue

            # 403 = Akamai WAF封锁，动态切换代理
            if resp.status_code == 403:
                global _FRED_403_COUNT
                _FRED_403_COUNT += 1
                if _FRED_403_COUNT >= _FRED_403_THRESHOLD and not FRED_PROXIES:
                    _try_set_fred_proxy()
                    _FRED_403_COUNT = 0
                if FRED_PROXIES:
                    continue  # 用代理重试

            data = resp.json()

            if "observations" in data and len(data["observations"]) > 0:
                obs = data["observations"][0]  # sort_order=desc → index 0 is latest
                value = float(obs["value"]) if obs["value"] != "." else None
                return obs["date"], value
            return None, None
        except Exception as e:
            if attempt < retries - 1:
                import time; time.sleep((attempt + 1) * 1)
                continue
            print(f"  [FRED] {series_id} 获取失败: {e}")
            return None, None
    return None, None


def get_fred_with_yoy(series_id: str, n_lags: int = 12, retries: int = 3) -> Tuple[Optional[str], Optional[float], Optional[float]]:
    """获取FRED序列最新值 + 同比值（单次API调用，减少限速风险）
    Returns: (date, latest_value, yoy_pct) 或 (None, None, None)
    """
    for attempt in range(retries):
        try:
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={FRED_API_KEY}"
                f"&file_type=json&limit={n_lags + 2}&sort_order=desc"
            )
            resp = requests.get(url, timeout=10, proxies=FRED_PROXIES)

            if resp.status_code == 429:
                import time; time.sleep((attempt + 1) * 3)
                continue

            if resp.status_code == 403:
                global _FRED_403_COUNT
                _FRED_403_COUNT += 1
                if _FRED_403_COUNT >= _FRED_403_THRESHOLD and not FRED_PROXIES:
                    _try_set_fred_proxy()
                    _FRED_403_COUNT = 0
                if FRED_PROXIES:
                    continue

            data = resp.json()
            obs = data.get("observations", [])

            if not obs:
                return None, None, None

            # 最新值
            latest_obs = obs[0]
            latest_val = float(latest_obs["value"]) if latest_obs["value"] != "." else None
            date = latest_obs["date"]

            # 同比值
            yoy_val = None
            if len(obs) > n_lags and latest_val is not None:
                year_ago = obs[n_lags]
                old_val = float(year_ago["value"]) if year_ago["value"] != "." else None
                if old_val and old_val != 0:
                    yoy_val = round((latest_val / old_val - 1) * 100, 2)

            return date, latest_val, yoy_val

        except Exception as e:
            if attempt < retries - 1:
                import time; time.sleep((attempt + 1) * 1)
                continue
            return None, None, None
    return None, None, None


def _compute_sahm_rule() -> Optional[float]:
    """
    计算萨姆规则（Sahm Rule）指标值。
    定义：当前3个月失业率均值 - 过去12个月最低3个月失业率均值
    阈值：≥ 0.5 → 衰退大概率已开始（历史准确率100%，1970-2023）
    参考：知识库/08_美联储政策框架/美联储政策反应函数与决策框架.md
    """
    if not FRED_API_KEY:
        return None
    try:
        from datetime import timedelta
        import math
        start_date = (datetime.now() - timedelta(days=600)).strftime("%Y-%m-%d")
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=UNRATE&api_key={FRED_API_KEY}"
            f"&file_type=json&observation_start={start_date}&sort_order=asc"
        )
        resp = requests.get(url, timeout=10, proxies=FRED_PROXIES)
        if resp.status_code != 200:
            return None
        obs = resp.json().get("observations", [])
        vals = []
        for o in obs:
            try:
                v = float(o["value"])
                if not math.isnan(v):
                    vals.append(v)
            except (ValueError, KeyError):
                pass
        if len(vals) < 15:
            return None
        # 当前3个月均值
        current_3m = sum(vals[-3:]) / 3
        # 过去12个月最低3个月均值（在 vals[-15:-3] 范围内）
        window_start = max(0, len(vals) - 15)
        window_end = len(vals) - 3
        min_3m = float("inf")
        for i in range(window_start, window_end):
            if i + 3 <= len(vals):
                avg = sum(vals[i:i + 3]) / 3
                if avg < min_3m:
                    min_3m = avg
        if min_3m == float("inf"):
            return None
        return round(current_3m - min_3m, 3)
    except Exception as e:
        print(f"  [萨姆规则] 计算失败: {e}")
        return None


def get_current_snapshot() -> Dict:
    """获取所有核心指标的当前快照（原始值 + YoY），失败时回退缓存"""
    print("\n[1/7] 获取实时指标...")
    snapshot = {}
    cache = _load_cache()
    updated_cache = {}
    import time

    # 首次调用时自动检测是否需要代理
    _detect_fred_proxy()

    # 需要YoY的指标及lookback（月度=12, 季度=4）
    yoy_lags = {
        "CPIAUCSL": 12, "PCEPI": 12, "PPIACO": 12, "M2SL": 12, "GDPC1": 4
    }

    for sid, name in KEY_INDICATORS.items():
        if sid in yoy_lags:
            # 需要YoY的指标：一次API调用获取原始值+YoY
            n_lags = yoy_lags[sid]
            date, raw_val, yoy_val = get_fred_with_yoy(sid, n_lags=n_lags)
            if raw_val is not None:
                snapshot[sid] = {"name": name, "date": date, "value": raw_val, "raw": raw_val}
                if yoy_val is not None:
                    snapshot[sid]["value"] = yoy_val  # 分析报告用YoY
                    print(f"  [OK] {name}: {yoy_val:.2f}% ({date})")
                else:
                    print(f"  [OK] {name}: {raw_val:.2f} ({date}) [同比计算失败]")
                # 缓存成功获取的值
                updated_cache[sid] = {"date": date, "value": yoy_val if yoy_val is not None else raw_val, "raw": raw_val}
            else:
                # 回退到缓存
                if sid in cache:
                    cached = cache[sid]
                    snapshot[sid] = {"name": name, "date": cached.get("date"), "value": cached.get("value"), "raw": cached.get("raw")}
                    updated_cache[sid] = cached
                    print(f"  [CACHED] {name}: {cached.get('value')} ({cached.get('date')}) [API失败，使用缓存]")
                else:
                    snapshot[sid] = {"name": name, "date": None, "value": None}
                    print(f"  [FAIL] {name}: 无数据（无缓存）")
        else:
            # 率值指标：直接获取最新值
            date, value = get_fred_latest(sid)
            snapshot[sid] = {"name": name, "date": date, "value": value}
            if value is not None:
                updated_cache[sid] = {"date": date, "value": value}
                print(f"  [OK] {name}: {value:.4f} ({date})")
            else:
                # 回退到缓存
                if sid in cache:
                    cached = cache[sid]
                    snapshot[sid] = {"name": name, "date": cached.get("date"), "value": cached.get("value")}
                    updated_cache[sid] = cached
                    print(f"  [CACHED] {name}: {cached.get('value')} ({cached.get('date')}) [API失败，使用缓存]")
                else:
                    print(f"  [FAIL] {name}: 无数据（无缓存）")
        time.sleep(0.5)

    # 更新缓存（保留未成功的旧缓存）
    for k, v in cache.items():
        if k not in updated_cache:
            updated_cache[k] = v
    _save_cache(updated_cache)

    # 数据新鲜度检查：对使用了过期缓存的指标发出警告
    stale_warnings = []
    for sid in KEY_INDICATORS:
        entry = snapshot.get(sid, {})
        if entry.get("value") is not None and _cache_age_days(sid) > 7:
            stale_warnings.append(f"{entry.get('name')}")
    if stale_warnings:
        print(f"  [WARN] 以下指标数据超过7天: {', '.join(stale_warnings)}")

    # VIX：Yahoo Finance优先，失败则FRED VIXCLS，最后缓存回退
    vix_val = None
    vix_date = None
    vix_source = None
    try:
        yf_url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=5d&interval=1d"
        yf_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        yf_resp = requests.get(yf_url, headers=yf_headers, timeout=8)
        if yf_resp.status_code == 200:
            yf_meta = yf_resp.json()["chart"]["result"][0]["meta"]
            vix_val = yf_meta["regularMarketPrice"]
            vix_date = datetime.now().strftime("%Y-%m-%d")
            vix_source = "Yahoo"
    except Exception:
        pass

    if vix_val is None:
        # 尝试 FRED VIXCLS（日频，滞后1天）
        try:
            fred_url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id=VIXCLS&api_key={FRED_API_KEY}"
                f"&file_type=json&sort_order=desc&limit=5"
            )
            fred_vix = requests.get(fred_url, timeout=8, proxies=FRED_PROXIES)
            if fred_vix.status_code == 200:
                obs = fred_vix.json().get("observations", [])
                for ob in obs:
                    v = ob.get("value", ".")
                    if v not in (".", ""):
                        vix_val = float(v)
                        vix_date = ob.get("date", "")
                        vix_source = "FRED"
                        break
        except Exception:
            pass

    if vix_val is None and "VIX" in cache and not _is_cache_stale("VIX", max_days=3):
        cached = cache["VIX"]
        vix_val = cached.get("value")
        vix_date = cached.get("date")
        vix_source = "cache"

    if vix_val is not None:
        snapshot["VIX"] = {"name": "VIX波动率", "date": vix_date, "value": vix_val}
        snapshot["VIXCLS"] = snapshot["VIX"]
        updated_cache["VIX"] = {"date": vix_date, "value": vix_val}
        print(f"  [OK] VIX波动率: {vix_val:.2f} ({vix_source})")
    else:
        snapshot["VIX"] = {"name": "VIX波动率", "date": None, "value": None}
        snapshot["VIXCLS"] = snapshot["VIX"]
        print(f"  [SKIP] VIX: 所有数据源均不可用")

    # GPR 地缘政治风险指数（月度，从 fred_history CSV 读最新值）
    for _gpr_id, _gpr_name in [
        ("GPRC_TWN", "台湾GPR指数"),
        ("GPRC_CHN", "中国GPR指数"),
        ("GPR",      "全球GPR指数"),
    ]:
        try:
            _gpr_path = os.path.join(BASE_DIR, "data", "fred_history", f"{_gpr_id}.csv")
            if os.path.exists(_gpr_path):
                _gdf = pd.read_csv(_gpr_path)
                if not _gdf.empty:
                    _gdf = _gdf.dropna(subset=["value"]).sort_values("date")
                    _last = _gdf.iloc[-1]
                    snapshot[_gpr_id] = {"name": _gpr_name, "date": _last["date"],
                                          "value": round(float(_last["value"]), 1)}
                    print(f"  [OK] {_gpr_name}: {_last['value']:.1f} ({_last['date']})")
        except Exception as _e:
            print(f"  [SKIP] {_gpr_name}: {_e}")

    # 萨姆规则（需要历史失业率，独立计算）
    sahm_val = _compute_sahm_rule()
    if sahm_val is not None:
        sahm_label = "🔴 触发！" if sahm_val >= 0.5 else ("🟡 接近" if sahm_val >= 0.3 else "🟢 正常")
        snapshot["SAHM_RULE"] = {"name": "萨姆规则", "date": datetime.now().strftime("%Y-%m-%d"),
                                  "value": sahm_val}
        print(f"  [OK] 萨姆规则: {sahm_val:.3f} {sahm_label}（阈值≥0.5触发衰退预警）")
    else:
        print("  [SKIP] 萨姆规则: 计算失败（失业率历史数据不足）")

    # Crucix 实时数据（gscpi / nuke / sdr / air）注入 _crucix 键
    try:
        from optim_config import CRUCIX_REMOTE_URL as _CRUCIX_URL
        _cx_resp = requests.get(_CRUCIX_URL, timeout=8)
        if _cx_resp.status_code == 200:
            _cx = _cx_resp.json()
            snapshot["_crucix"] = {
                "gscpi":    _cx.get("gscpi"),
                "nuke":     _cx.get("nuke"),
                "sdr":      _cx.get("sdr"),
                "air":      _cx.get("air"),
                "markets":  {
                    "vix": (_cx.get("markets") or {}).get("vix"),
                },
            }
            _gscpi_val = (snapshot["_crucix"]["gscpi"] or {}).get("value")
            print(f"  [OK] Crucix: gscpi={_gscpi_val}, nuke={len(snapshot['_crucix']['nuke'] or [])}, sdr={bool(_cx.get('sdr'))}")
        else:
            snapshot["_crucix"] = {}
            print(f"  [SKIP] Crucix: HTTP {_cx_resp.status_code}")
    except Exception as _cx_e:
        snapshot["_crucix"] = {}
        print(f"  [SKIP] Crucix: {_cx_e}")

    return snapshot


def get_china_current_snapshot() -> Dict:
    """获取中国当前宏观经济快照（NeoData API + 缓存回退 + FRED二级回退）"""
    print("\n[1/7] 获取中国实时指标...")
    snapshot = {}
    cache = _load_cache()
    updated_cache = dict(cache)  # 复制旧缓存

    for key, spec in CHINA_INDICATORS.items():
        name = spec["name"]
        date, value = get_china_indicator(key)
        source = "realtime"
        cache_key = f"CN_{key}"
        if value is not None:
            # 判断是否为缓存数据（日期不是今天）
            if date and date != datetime.now().strftime("%Y-%m-%d") and cache_key in cache:
                source = "cache"
            print(f"  [OK] {name}: {value:.2f} ({date}) [{'缓存' if source=='cache' else '实时'}]")
            updated_cache[cache_key] = {"date": date, "value": value}
        else:
            # 检查缓存（已在 get_china_indicator 内处理，此处仅打印）
            if cache_key in cache:
                source = "cache"
                cached = cache[cache_key]
                print(f"  [CACHED] {name}: {cached.get('value')} ({cached.get('date')}) [缓存]")
                snapshot[key] = {"name": name, "date": cached.get("date"), "value": cached.get("value"), "source": "cache"}
                continue
            else:
                print(f"  [FAIL] {name}: 无数据（无缓存）")
        snapshot[key] = {"name": name, "date": date, "value": value, "source": source}
        time.sleep(0.3)  # 避免过快请求

    _save_cache(updated_cache)

    # FRED 二级回退：当 NeoData 全部失败且无缓存时，尝试 FRED OECD 中国系列
    valid_count = sum(1 for v in snapshot.values() if isinstance(v, dict) and v.get("value") is not None)
    if valid_count == 0:
        print("  [FRED二级回退] NeoData全部失败，尝试FRED OECD中国指标...")
        _china_fred_map = {
            "cpi":         ("CHNCPIALLMINMEI",  "CPI同比"),
            "pmi_mfg":     ("CHNPMIMANMISMEI",  "制造业PMI"),
            "unemployment":("LRUNTTTTCNM156S",  "城镇调查失业率"),  # 新增：中国协调失业率
        }
        for key, (fred_sid, name) in _china_fred_map.items():
            try:
                fred_url = (
                    f"https://api.stlouisfed.org/fred/series/observations"
                    f"?series_id={fred_sid}&api_key={FRED_API_KEY}"
                    f"&file_type=json&sort_order=desc&limit=3"
                )
                resp = requests.get(fred_url, timeout=8, proxies=FRED_PROXIES)
                if resp.status_code == 200:
                    obs = resp.json().get("observations", [])
                    for ob in obs:
                        v_str = ob.get("value", ".")
                        if v_str not in (".", ""):
                            val = float(v_str)
                            dt = ob.get("date", "")
                            snapshot[key] = {"name": name, "date": dt, "value": val, "source": "FRED"}
                            updated_cache[f"CN_{key}"] = {"date": dt, "value": val}
                            print(f"  [FRED-CN] {name}: {val:.2f} ({dt})")
                            break
            except Exception:
                pass

        if sum(1 for v in snapshot.values() if isinstance(v, dict) and v.get("value") is not None) == 0:
            snapshot["_data_note"] = "⚠️ 中国实时数据完全不可用（NeoData+FRED均失败）。以下分析基于宏观背景推断，参考意义有限。"
            print("  [WARN] 中国数据全部不可用，将在报告中标注")

    # World Bank 三级回退：免费公开API，补充GDP增速（FRED不提供）
    if not snapshot.get("gdp_growth", {}).get("value"):
        try:
            wb_url = (
                "https://api.worldbank.org/v2/country/CN/indicator/NY.GDP.MKTP.KD.ZG"
                "?format=json&mrv=3&per_page=3"
            )
            resp = requests.get(wb_url, timeout=8, proxies=FRED_PROXIES)
            if resp.status_code == 200:
                data = resp.json()
                if len(data) >= 2 and data[1]:
                    for rec in data[1]:
                        if rec.get("value") is not None:
                            val = round(float(rec["value"]), 2)
                            dt = rec.get("date", "")
                            snapshot["gdp_growth"] = {
                                "name": "GDP增速", "date": dt, "value": val, "source": "WorldBank"
                            }
                            print(f"  [WB-CN] GDP增速: {val}% ({dt})")
                            break
        except Exception:
            pass

    _save_cache(updated_cache)
    return snapshot
