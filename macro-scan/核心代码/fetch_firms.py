# -*- coding: utf-8 -*-
"""
fetch_firms.py — NASA FIRMS 卫星火点直连采集（替代 Crucix 接入）

数据源：NASA FIRMS API（VIIRS_SNPP_NRT + VIIRS_NOAA20_NRT 近实时活跃火点）
  端点：https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/world/{DAY_COUNT}/{DATE}
  窗口：DAY_COUNT=2（最近2天 ≈ 贴近 Crucix 的 24-48h 聚合语义，且比经代理处理更及时）
输出：data/firms_fire.json
  { total_hotspots, high_confidence, active_fire_regions[], date, source, upstream_date, fetched_at }
调用：日档（建议 0908，先于 fetch_climate_signals 的 0910 月档）
设计：纯重写，零借鉴 Crucix 代码（AGPL-3.0 边界）。crucix 退场后本模块为唯一火点源。

恢复注记（2026-08-04）：原源码 08-03 被 deploy.sh rsync --delete 抹除（与 compute_fci.py 同因，
未 git add）。本文件由幸存 pyc（fetch_firms.cpython-311.pyc, mtime 07-31）反编译 + pycdas 反汇编
逐函数重建，行为等价验证：与 pyc 各跑一次对比 firms_fire.json 数值一致。
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
    _REQ_OK = True
except ImportError:
    _REQ_OK = False

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = Path(__file__).parent.parent
    DATA_DIR = str(Path(WORKSPACE) / 'data')

# 代理配置（2026-08-06 修复：原读 FRED_PROXY（env 不存在）→ 代理回退永久失效；改为 optim_config.PROXY_URL > env OUTBOUND_PROXY）
try:
    from optim_config import PROXY_URL
except ImportError:
    PROXY_URL = os.environ.get('OUTBOUND_PROXY', '')

PROXY_URL = os.environ.get('OUTBOUND_PROXY', '') or PROXY_URL
FIRMS_MAP_KEY = os.environ.get('FIRMS_MAP_KEY', '9b78dded5710647a7fd003b5da5a216d')
FIRMS_OUTPUT = os.path.join(DATA_DIR, 'firms_fire.json')
_PROXIES = {
    'http': PROXY_URL,
    'https': PROXY_URL,
} if PROXY_URL else None

REGION_HOTSPOT_THRESHOLD = 500
DAY_COUNT = 2
VIIRS_SOURCES = ('VIIRS_SNPP_NRT', 'VIIRS_NOAA20_NRT')


def _fetch_source_csv(date_str, source):
    '''直连单个 VIIRS 源的 area CSV；直连失败回退代理。
    2026-08-06 修复：改 stream 分块下载——一次性 GET 下载全球 2 天 NRT CSV 体量过大、
    120s 超时拿不到数据（实测 stream 分块可正常拉到稠密火点记录）。
    timeout=(connect, read)：连接 15s，读 300s 足够下载大数据量。'''
    url = (
        f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/'
        f'{FIRMS_MAP_KEY}/{source}/world/{DAY_COUNT}/{date_str}'
    )
    try:
        resp = requests.get(url, timeout=(15, 300), stream=True)
    except Exception:
        if _PROXIES:
            resp = requests.get(url, timeout=(15, 300), stream=True, proxies=_PROXIES)
        else:
            raise
    if resp.status_code != 200:
        return ''
    chunks = []
    for chunk in resp.iter_content(chunk_size=65536):
        if chunk:
            chunks.append(chunk)
    return b''.join(chunks).decode('utf-8', errors='ignore')


def _aggregate(csv_texts):
    '''合并多源 CSV 并聚合成 (total, high_conf, regions)。按 (lat,lng,date,time) 去重。'''
    seen = set()
    total = 0
    high_conf = 0
    grid = {}
    for txt in csv_texts:
        lines = txt.splitlines()
        if len(lines) < 2:
            continue
        for row in lines[1:]:
            parts = row.split(',')
            if len(parts) < 10:
                continue
            try:
                lat = float(parts[0])
                lng = float(parts[1])
            except (ValueError, IndexError):
                continue
            dedup = (round(lat, 3), round(lng, 3), parts[5].strip(), parts[6].strip())
            if dedup in seen:
                continue
            seen.add(dedup)
            total += 1
            if parts[9].strip().lower() == 'h':
                high_conf += 1
            lat_band = int(lat // 10) * 10
            lng_band = int(lng // 10) * 10
            lat_lbl = f'{lat_band}N' if lat >= 0 else f'{-lat_band}S'
            lng_lbl = f'{lng_band}E' if lng >= 0 else f'{-lng_band}W'
            key = f'{lat_lbl}_{lng_lbl}'
            grid[key] = grid.get(key, 0) + 1
    # 只保留热点 ≥ 阈值 的格子（与 fetch_climate_signals 的消费口径一致）
    regions = sorted(k for k, v in grid.items() if v > REGION_HOTSPOT_THRESHOLD)
    return total, high_conf, regions


def fetch_and_save(date_str=None):
    '''主流程：拉两个源 → 聚合 → 写 firms_fire.json。'''
    if not _REQ_OK:
        print('[fetch_firms] requests 不可用，跳过')
        return {}

    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    print(f'[fetch_firms] 拉取 NASA FIRMS {VIIRS_SOURCES} world/{DAY_COUNT} @ {date_str}')

    csvs = []
    for src in VIIRS_SOURCES:
        t = _fetch_source_csv(date_str, src)
        if not t:
            continue
        csvs.append(t)
        print(f'  [fetch_firms] {src}: {len(t.splitlines()) - 1} 行')

    if not csvs:
        print('[fetch_firms] 所有源均无数据，写入 0 值失败文件')
        # 2026-08-10 加固（D6 静默降级红线 #8）：全源失败必须落 0 值失败文件（明确失败态），
        # 禁止静默缺文件——否则下游 fetch_climate_signals 读旧文件误以为数据新鲜
        failed_result = {
            'fetched_at': datetime.now().isoformat(timespec='seconds')[:19],
            'date': date_str,
            'total_hotspots': 0,
            'high_confidence': 0,
            'active_fire_regions': [],
            'source': f'NASA FIRMS {",".join(VIIRS_SOURCES)} (direct)',
            'upstream_window_days': DAY_COUNT,
            'status': 'failed',
            'error': 'all sources returned no data',
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(FIRMS_OUTPUT, 'w', encoding='utf-8') as f:
                json.dump(failed_result, f, ensure_ascii=False, indent=2)
            print(f'[fetch_firms] 失败态已落盘 {FIRMS_OUTPUT}（status=failed）')
        except Exception as e:
            print(f'[fetch_firms] 失败态落盘失败: {e}')
        # 2026-08-07 fail-loud（红线 #8）：全源失败必须告警，禁止静默跳过
        try:
            from ntfy_utils import push_text
            push_text("⚠️ FIRMS 数据源异常", f"fetch_firms 全源失败（{VIIRS_SOURCES}），已落 0 值失败文件，date={date_str}")
        except Exception as e:
            print(f'[fetch_firms] fail-loud 告警失败: {e}')
        return failed_result

    total, high_conf, regions = _aggregate(csvs)

    # 2026-08-07 fail-loud（红线 #8）：全球 2 天 NRT 双源火点常态 7 万+，双零 = 异常信号（API 返回空/解析丢失），必须告警
    if total == 0 and high_conf == 0:
        try:
            from ntfy_utils import push_text
            push_text("⚠️ FIRMS 返回 0 火点", f"fetch_firms 聚合为 0（date={date_str}），疑似 NASA API 异常；下游 climate/R11 将失去火点输入")
        except Exception as e:
            print(f'[fetch_firms] fail-loud 告警失败: {e}')

    result = {
        'fetched_at': datetime.now().isoformat(timespec='seconds')[:19],
        'date': date_str,
        'total_hotspots': total,
        'high_confidence': high_conf,
        'active_fire_regions': regions,
        'source': f'NASA FIRMS {",".join(VIIRS_SOURCES)} (direct)',
        'upstream_window_days': DAY_COUNT,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(FIRMS_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f'[fetch_firms] 完成：total={total} high={high_conf} regions={len(regions)}')
    except Exception as e:
        print(f'[fetch_firms] 写入失败: {e}')

    return result


if __name__ == '__main__':
    fetch_and_save()
