#!/usr/bin/env python3
"""Python cron replacement for macro-scan container.
Avoids seccomp/fork restrictions that break cron daemon.
Run as: python3 /app/scheduler.py >> /var/log/macro-scan/scheduler.log 2>&1

## 任务隐式依赖关系（CON-6）
时间间隔已足够保证正确顺序，无需额外同步：
  disaster (05:25) → [无依赖]
  fred_fetch (05:30) → [无依赖]
  gpr_fetch (05:40) → [无依赖，与 fred_fetch 同类，30s 后]
  china_fetch (05:45) → [无依赖]
  grv_update (06:10) → 依赖 gpr_fetch (05:40) + fred_fetch (05:30)，预留 30min
  weak_signal (06:00) → 依赖 gpr_fetch (05:40)，预留 20min
  situation_detect (06:30) → 依赖 weak_signal (06:00)，预留 30min
  daily_narrative (07:00) → 依赖 grv_update (06:10) + situation_detect (06:30)
  morning (07:30) → 依赖 daily_narrative (07:00)，预留 30min
  us_daily/china_daily (20:00/20:15) → 独立，不依赖白天任务
所有任务通过 subprocess.Popen 后台非阻塞启动，调度线程不等待完成。
"""
import subprocess, time, sys, os, datetime, json

# T1-2 可观测性：心跳+任务计数（零风险，纯写日志，出错不阻断调度器）
try:
    from observability import observe
except Exception:
    observe = None

# P0-D 修复：状态文件路径常量单点取自 optim_config（跨容器契约 §6.4）
# 禁止再各自用 dirname(__file__) 推导（会落非持久卷 /data）
try:
    from optim_config import DATA_DIR, now_iso_utc
except Exception:
    # fail-loud：无法导入 optim_config 属于部署配置错误，禁止静默 fallback
    print("FATAL: cannot import optim_config.DATA_DIR (deployment config error)", flush=True)
    sys.exit(1)

WORKDIR = "/app"
PYTHON  = "/usr/local/bin/python3"
LOG_DIR = "/var/log/macro-scan"

JOBS = [
    # name,         hhmm,   weekdays(1-5=Mon-Fri, 1-7=all), dom(day-of-month, None=any), command
    ("disaster",    "I15", "1-7", None, [PYTHON, "fetch_disaster_signals.py"]),  # 自然灾害信号（事件档 每15分；08-14 提频与地震对齐）
    ("fred_fetch",  "0530", "1-7", None, [PYTHON, "fetch_fred_history.py"]),
    ("gscpi",       "0532", "1-7", None, [PYTHON, "fetch_gscpi.py"]),          # NY Fed GSCPI（落盘 GSCPI.csv；ADR-01 门禁重定义；错峰 fred_fetch 0530，morning 0730 前落盘）
    ("compute_fci", "0535", "1-7", None, [PYTHON, "compute_fci.py"]),  # L1 FCI 双轨（依赖 fred_fetch 刷新 fred_history）
    ("fred_freshness", "0540", "1-7", None, [PYTHON, "fred_freshness.py", "--all"]),  # data-freshness：FRED 新鲜度闸 + stale + FCI 探针（依赖 fred_fetch 0530 + compute_fci 0535）
    ("compute_probit", "0540", "1-7", None, [PYTHON, "compute_probit.py"]),  # L3 probit
    ("tianji_trigger","0942", "1-7", None, [PYTHON, "write_tianji_trigger.py"]),       # 天玑 trigger 写入（T2：watchdog 检触发执行验证；dom=None 每日触发，08-06 修 dom=1 笔误）
    ("tianji_summary","I30", "1-7", None, [PYTHON, "tianji_summary_export.py"]),        # 天玑汇总导出（08-17：PG tianji 预测/推理/权重 → data/tianji_summary.json 供开阳天玑 Tab）
    ("tianxuan_grv","I30", "1-7", None, [PYTHON, "tianxuan_grv_export.py"]),             # 天璇 GRV 轨迹导出（08-27 F1：扫 docs/仿真报告 *_grv_traj.json → data/tianxuan_grv.json 供开阳天璇 Tab）
    ("gpr_fetch",   "0540", "1-7", None, [PYTHON, "fetch_gpr.py"]),
    ("china_fetch", "0545", "1-7", None, [PYTHON, "fetch_china_data.py"]),
    ("world_macro", "0550", "1-7", None, [PYTHON, "fetch_world_macro.py"]),
    ("fx_fetch",    "0555", "1-7", None, [PYTHON, "fetch_fx.py"]),
    ("crypto",      "I10", "1-7", None, [PYTHON, "fetch_crypto.py"]),         # CoinGecko（事件档 每10分；08-14 提频 4320/月=43% 贴 50% 月限）
    ("weak_signal", "0000", "1-7", None, [PYTHON, "scan_weak_signals.py"]),
    ("weak_signal", "0600", "1-7", None, [PYTHON, "scan_weak_signals.py"]),
    ("weak_signal", "1200", "1-7", None, [PYTHON, "scan_weak_signals.py"]),
    ("weak_signal", "1800", "1-7", None, [PYTHON, "scan_weak_signals.py"]),
    ("sanctions",   "0605", "1-7", None, [PYTHON, "fetch_sanctions.py"]),
    # ── 新接入 P0+P1 源（fetcher_base 适配层；常驻进程、独立时间槽、互不阻塞）──
    # 喂 GRV 的源（earthquake / energy）排在大盘 grv_update 06:10 之前，保证当天先落盘
    ("earthquake",  "I5",  "1-7", None, [PYTHON, "fetch_earthquake.py"]),   # P0 USGS 地震（事件档 每5分；08-14 提频，USGS 无硬限）
    ("safecast_nuke", "I60", "1-7", None, [PYTHON, "fetch_safecast_nuke.py"]), # SafeCast 核电站辐射 CPM（事件档 每60分；历史归档均值 2016-2023，低频拉取避免刷免费 API）
    ("gdelt_geo",   "I15", "1-7", None, [PYTHON, "fetch_gdelt_geo.py", "--incremental"]),  # P1 GDELT 地理事件点（事件档 每15分；产出 news_geo.jsonl + 派生 news_geo.json，供开阳事件图层）
    ("energy",      "I60", "1-7", None, [PYTHON, "fetch_energy.py"]),       # P1 电网/能源（小时档；08-14 提频，碳强度近实时受益）
    # 以下不喂 GRV，仅落盘交叉验证/事件源，错峰在 grv_update 之后
    ("crypto_extra","I5",  "1-7", None, [PYTHON, "fetch_crypto_extra.py"]), # P1 Binance/Kraken 冗余行情（事件档 每5分；08-14 提频，公共端慷慨）
    ("news",        "I30",  "1-7", None, [PYTHON, "fetch_news.py"]),         # P1 GDELT DOC 2.0 + MarketAux（30min=MarketAux 48% 贴 50% 水位，实时性）
    ("hdx",         "0620", "1-7", None, [PYTHON, "fetch_hdx.py"]),          # P1 人道/危机冲击
    # 新增 BDI / FAO（T01/T02：fetcher_base 适配层；仅落盘，不喂 GRV）
    # BDI 实时拉取本环境不可行（Stooq OpenResty 验 TLS 指纹 + Chromium 下载不可达，详见 CHANGELOG v3.6.0），
    # 改为读取本地预置历史 CSV：data/bdi_history.csv（运维从 Windows 浏览器导出 Stooq bmd.csv 后放入）。
    ("bdi",         "0625", "1-7", None, [PYTHON, "fetch_bdi.py"]),           # P0 波罗的海干散货指数（本地 CSV，日频）
    ("fao",         "0925", "1-7", 1,    [PYTHON, "fetch_fao.py"]),           # P0 FAO 粮食价格指数（每月1日 dom=1）
    # 新增 商品/航空/中观（T1/T2/T3：fetcher_base 适配层；仅落盘，不喂 GRV，错峰）
    ("commodity_yahoo",    "I15", "1-7", None, [PYTHON, "fetch_commodity_yahoo.py"]),   # P0 Yahoo 商品/股市（每 15 分钟，08-14 起即时化）
    ("airtraffic_opensky", "I30", "1-7", None, [PYTHON, "fetch_airtraffic_opensky.py"]), # P0 OpenSky 航空（30min；08-14 提频 48/日=12%≪200/日 50% 水位，观察后评估 I15）
    ("airroutes",       "0950", "1-7", None, [PYTHON, "fetch_airroutes.py"]), # P2 OpenFlights 全球航线网（日档 0950；结构数据日更远超所需，08-14 air 图层静态航线网）
    ("spacelaunch",     "0705", "1-7", None, [PYTHON, "fetch_spacelaunch.py"]), # P2 Next Spaceflight 发射记录（日档 0705；发射事件低频，08-14 space 图层）
    ("health_geo",      "I60", "1-7", None, [PYTHON, "fetch_health_geo.py"]), # P2 GDELT 卫生事件（60min；增量拉新 slot，08-15 health 图层）
    ("news_titles",     "I120", "1-7", None, [PYTHON, "fetch_news_titles.py"]), # P2 新闻标题预抓（2h 增量；news_geo 弹框真实标题静态缓存，08-16）
    ("energy_eia",         "0630", "1-7", None, [PYTHON, "fetch_energy_eia.py"]),          # P0 EIA 能源（日频，错峰 commodity_yahoo 0626）
    ("china_meso",         "0930", "1-7", 1,    [PYTHON, "fetch_china_meso.py"]),          # P0 AkShare 中观（每月1日，错峰 fao 0925）
    # 地震为实时外生冲击，日内再刷 3 次（错峰，不与白天任务冲突）

    ("grv_update",  "0610", "1-7", None, [PYTHON, "geo_risk_vector.py"]),
    ("morning",     "0730", "1-5", None, [PYTHON, "run_macro_analysis.py", "--country", "both", "--depth", "quick"]),
    ("us_daily",    "2000", "1-5", None, [PYTHON, "run_macro_analysis.py", "--country", "us", "--depth", "standard"]),
    ("china_daily", "2015", "1-5", None, [PYTHON, "run_macro_analysis.py", "--country", "china", "--depth", "standard"]),
    # R-1 开阳报告索引（报告产出后 5 分钟触发：晨报 0730 后 / 晚报 2000-2015 后）
    ("reports_index","0735", "1-5", None, [PYTHON, "generate_reports_index.py"]),
    ("reports_index","2035", "1-7", None, [PYTHON, "generate_reports_index.py"]),
    ("kb_update",   "0905", "1-7", 1,    [PYTHON, "update_kb_numbers.py"]),
    ("firms",       "0908", "1-7", None, [PYTHON, "fetch_firms.py"]),           # NASA FIRMS 火点直连（crucix 退场前置，先于 climate 0910）
        ("climate",     "0910", "1-7", None, [PYTHON, "fetch_climate_signals.py"]),
    ("kiwisdr",     "0602", "1-7", None, [PYTHON, "fetch_kiwisdr.py"]),          # KiwiSDR 目录（sdr_summary.json；日更1-2次；错峰 weak_signal 0600，先于 narrative_proc 0710 消费）
    ("daily_narrative", "0700", "1-7", None, [PYTHON, "daily_narrative.py"]),
    ("news_export",  "I15", "1-7", None, [PYTHON, "news_exporter.py"]),         # macro-sim JSON 导出
    ("narrative_proc","0710", "1-7", None, [PYTHON, "narrative_processor.py"]),  # 天玑 叙事预处理（叙事块写入+密度监测）
    ("defense_rss",   "I60", "1-7", None, [PYTHON, "fetch_defense_rss.py"]),     # T1-3 防务RSS（小时档；08-14 提频，RSS 持续无 key）
    # news_geo_feed（P3-A NER）已于 2026-08-11 停调度：gdelt_geo --incremental 直接派生 news_geo.json（路线 A）
    ("situation_detect", "0630", "1-7", None, [PYTHON, "situation_detector.py"]),
    ("weekly_synthesis", "2000", "5",  None, [PYTHON, "weekly_synthesis.py"]),       # 周五20:00
    ("health_push",  "2100", "1-7", None, [PYTHON, "-c",
        "from observability import daily_health_push; daily_health_push()"
    ]),  # 每日健康摘要推送（三数字：GRV时间戳/降级fetcher数/predictions行数）
    ("slow_vars",   "0935", "1-7", 1,   [PYTHON, "slow_variables.py"]),              # 天玑 慢变量更新（每月1日）
    ("spacetrack",  "0615", "1-7", None, [PYTHON, "fetch_spacetrack.py"]),            # Space-Track 卫星统计（日频，06:15）
    ("market_quotes","I15","1-7", None, [PYTHON, "market_quotes.py"]),               # 市场行情快照整合（commodity+crypto，I15 跟 crypto 走——crypto 源已 I15 采集，整合导出提频零外部请求）
    ("news_prune",  "0920", "1-7", 1,   [PYTHON, "-c",
        "import sys; sys.path.insert(0,'.'); import news_db; "
        "from optim_config import DATA_DIR; import os; "
        "db=os.path.join(DATA_DIR,'news.db'); "
        "n=news_db.prune_old_articles(db,90); print(f'[prune] 删除 {n} 篇旧文章')"
    ]),  # 每月1日，保留90天滚动窗口
    ("silent_probe", "I120", "1-7", None, [PYTHON, "silent_failure_probe.py"]),  # P0 静默失败探针：双写差/心跳/产物新鲜度→ntfy（每2小时兜底）
]

LOG_FILES = {
    "fred_fetch":  f"{LOG_DIR}/fred.log",
    "fred_freshness": f"{LOG_DIR}/fred_freshness.log",
    "compute_fci": f"{LOG_DIR}/compute_fci.log",
    "gpr_fetch":   f"{LOG_DIR}/gpr_fetch.log",
    "china_fetch": f"{LOG_DIR}/china.log",
    "weak_signal": f"{LOG_DIR}/scan.log",
    "morning":     f"{LOG_DIR}/morning.log",
    "us_daily":    f"{LOG_DIR}/us_daily.log",
    "china_daily": f"{LOG_DIR}/china_daily.log",
    "verify":      f"{LOG_DIR}/verify.log",
    "kb_update":   f"{LOG_DIR}/kb_update.log",
    "grv_update":  f"{LOG_DIR}/grv.log",
    "daily_narrative": f"{LOG_DIR}/daily_narrative.log",
    "firms":       f"{LOG_DIR}/firms.log",
        "climate":     f"{LOG_DIR}/climate.log",
    "situation_detect": f"{LOG_DIR}/situation_detect.log",
    "disaster":    f"{LOG_DIR}/disaster.log",
    "world_macro": f"{LOG_DIR}/world_macro.log",
    "fx_fetch":    f"{LOG_DIR}/fx.log",
    "crypto":      f"{LOG_DIR}/crypto.log",
    "sanctions":   f"{LOG_DIR}/sanctions.log",
    "earthquake":  f"{LOG_DIR}/earthquake.log",
    "gdelt_geo":   f"{LOG_DIR}/gdelt_geo.log",
    "energy":      f"{LOG_DIR}/energy.log",
    "crypto_extra":f"{LOG_DIR}/crypto_extra.log",
    "news":        f"{LOG_DIR}/news.log",
    "hdx":         f"{LOG_DIR}/hdx.log",
    "bdi":         f"{LOG_DIR}/bdi.log",
    "fao":         f"{LOG_DIR}/fao.log",
    "commodity_yahoo":   f"{LOG_DIR}/commodity_yahoo.log",
    "airtraffic_opensky":f"{LOG_DIR}/airtraffic_opensky.log",
    "airroutes":f"{LOG_DIR}/airroutes.log",
    "spacelaunch":f"{LOG_DIR}/spacelaunch.log",
    "health_geo":f"{LOG_DIR}/health_geo.log",
    "energy_eia":        f"{LOG_DIR}/energy_eia.log",
    "china_meso":        f"{LOG_DIR}/china_meso.log",
    "weekly_synthesis": f"{LOG_DIR}/weekly_synthesis.log",
    "dashboard":    f"{LOG_DIR}/dashboard.log",
    "verify_auto": f"{LOG_DIR}/verify_auto.log",
    "news_prune":  f"{LOG_DIR}/news_prune.log",
    "news_export": f"{LOG_DIR}/news_export.log",
    "narrative_proc":  f"{LOG_DIR}/narrative_proc.log",
    "defense_rss":     f"{LOG_DIR}/defense_rss.log",
    "slow_vars":       f"{LOG_DIR}/slow_vars.log",
    "health_push":     f"{LOG_DIR}/health_push.log",
    "spacetrack":      f"{LOG_DIR}/spacetrack.log",
    "market_quotes":   f"{LOG_DIR}/market_quotes.log",
    "compute_probit":  f"{LOG_DIR}/compute_probit.log",
    "tianji_trigger": f"{LOG_DIR}/tianji_trigger.log",
    "tianji_summary": f"{LOG_DIR}/tianji_summary.log",
    "tianxuan_grv":   f"{LOG_DIR}/tianxuan_grv.log",
    "reports_index": f"{LOG_DIR}/reports_index.log",
}

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[SCHED] {ts} {msg}"
    print(line, flush=True)

def job_log(name, msg):
    log_file = LOG_FILES.get(name, f"{LOG_DIR}/{name}.log")
    try:
        with open(log_file, "a") as f:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[SCHED] {ts} {msg}\n")
    except Exception as e:
        log(f"Cannot write {log_file}: {e}")

def get_hhmm_wd():
    now = datetime.datetime.now()
    return now.strftime("%H%M"), now.isoweekday(), now.day  # Mon=1 Sun=7

def parse_interval(sched_hhmm):
    """子小时间隔语法：'I15' = 每15分钟。返回间隔分钟数或 None。"""
    if isinstance(sched_hhmm, str) and len(sched_hhmm) > 1 and sched_hhmm[0] in "iI" and sched_hhmm[1:].isdigit():
        v = int(sched_hhmm[1:])
        return v if 1 <= v <= 1440 else None
    return None

def wd_dom_ok(wd, dom, sched_wd, sched_dom):
    """weekday / day-of-month 准入检查（interval 与每日档共用）。"""
    if sched_dom is not None and dom != sched_dom:
        return False
    if sched_wd == "1-7":
        return True
    for part in sched_wd.split(","):
        if "-" in part:
            try:
                start, end = int(part.split("-")[0]), int(part.split("-")[1])
                if start <= wd <= end:
                    return True
            except (ValueError, IndexError):
                pass
        elif str(wd) == part.strip():
            return True
    return False

def should_run(sched_hhmm, sched_wd, sched_dom=None):
    hhmm, wd, dom = get_hhmm_wd()
    interval = parse_interval(sched_hhmm)
    if interval:
        mins = int(hhmm[0:2]) * 60 + int(hhmm[2:4])
        if mins % interval != 0:
            return False
        return wd_dom_ok(wd, dom, sched_wd, sched_dom)
    if hhmm != sched_hhmm:
        return False
    return wd_dom_ok(wd, dom, sched_wd, sched_dom)

last_run = {}  # (job_name, sched_hhmm) -> last_run_ts
_last_run_ts = {}   # job_name -> last fired timestamp（供状态落盘）
_last_run_ok = {}   # job_name -> bool（最近一次是否成功；P0-D 修复：不再默认 True 占位，由真实 spawn 结果驱动）
# P0-D 修复：状态/暂停文件统一走 DATA_DIR（optim_config 单点），落持久卷 /workspace/data
_STATE_PATH  = os.path.join(DATA_DIR, "scheduler_state.json")
_PAUSE_PATH  = os.path.join(DATA_DIR, "control_pause.json")
_last_state_dump = 0.0   # 上次落盘时间


def _load_paused() -> set:
    """读取 control_server 写入的暂停集合。"""
    try:
        with open(_PAUSE_PATH, encoding="utf-8") as f:
            return set(json.load(f).get("paused", []))
    except Exception:
        return set()


def _dump_state():
    """每 60s 把运行时状态落盘，供 control_server 读取。P0-D：含 heartbeat 供健康探测。"""
    global _last_state_dump
    now = time.time()
    if now - _last_state_dump < 60:
        return
    _last_state_dump = now
    try:
        import datetime as _dt
        jobs_meta = {}
        for job_name, sched_hhmm, *_ in JOBS:
            jobs_meta[job_name] = {
                "schedule":    sched_hhmm,
                "last_run_ts": _last_run_ts.get(job_name),
                "last_ok":     _last_run_ok.get(job_name, False),  # P0-D：不再默认 True
            }
        state = {
            "updated": now_iso_utc(),
            "heartbeat": now,
            "jobs": list(jobs_meta.keys()),
            **jobs_meta,
        }
        tmp = _STATE_PATH + ".tmp"
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, _STATE_PATH)
    except Exception as e:
        log(f"[scheduler] 状态落盘失败（非阻断）: {e}")


def _load_last_run():
    """C7 修复：启动时从 scheduler_state.json 恢复 last_run_ts，避免重启后丢失（无法区分从未运行 vs 重启过）。

    持久化语义：job 级 last_run_ts 写入 state 文件（_dump_state 每 60s 落盘），
    重启后从这里恢复内存表；若文件不存在（首次部署）则保持空 dict。
    与未来 worldsim-pg 方案的映射：此恢复逻辑未来切 PG 时改为读状态表。
    """
    global last_run, _last_run_ts
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            st = json.load(f)
        recovered = 0
        for job_name, meta in st.items():
            if isinstance(meta, dict) and "last_run_ts" in meta:
                lr = meta.get("last_run_ts")
                if lr is not None:
                    _last_run_ts[job_name] = lr
                    recovered += 1
        log(f"[scheduler] C7 恢复 last_run_ts: {recovered} 个 job 从状态文件恢复")
    except Exception as e:
        log(f"[scheduler] C7 恢复失败（首次部署或无状态文件，非阻断）: {e}")


def main():
    log("Python scheduler started (seccomp-free)")
    _load_last_run()

    # P0-D 修复：启动断言 DATA_DIR 必须落在持久卷 /workspace/data。
    # 项目红线：任何兜底必须留痕；此处不做静默 fallback，不满足即 fail-loud 退出。
    if DATA_DIR != "/workspace/data":
        log(f"[scheduler] FATAL: DATA_DIR={DATA_DIR} != /workspace/data，状态文件将落非持久卷，拒绝启动")
        print(f"FATAL: DATA_DIR={DATA_DIR} != /workspace/data", flush=True)
        sys.exit(1)
    log(f"[scheduler] DATA_DIR assertion OK: {DATA_DIR}")

    # 启动完整性校验（source_dimension_map 遗漏映射会导致 GRV 维度静默接收零数据）
    try:
        from startup_checks import run_all_checks
        run_all_checks(strict=True)
    except RuntimeError as e:
        log(f"[startup_checks] FATAL: {e}")
        raise
    except Exception as e:
        log(f"[startup_checks] 校验模块加载失败（非阻断）: {e}")

    while True:
        # T1-2: 心跳（每轮循环打一次，30s 间隔）
        if observe:
            try:
                observe.heartbeat()
            except Exception:
                pass

        for job_name, sched_hhmm, sched_wd, sched_dom, cmd in JOBS:
            now_ts = time.time()
            interval = parse_interval(sched_hhmm)
            hhmm, wd, dom = get_hhmm_wd()

            if interval:
                # 事件档：按当日分钟数对间隔取模触发（每 interval 分钟一次）
                mins = int(hhmm[0:2]) * 60 + int(hhmm[2:4])
                if mins % interval != 0:
                    continue
                if not wd_dom_ok(wd, dom, sched_wd, sched_dom):
                    continue
                key = (job_name, sched_hhmm, mins // interval)
                min_gap = interval * 60 - 10
            else:
                if hhmm != sched_hhmm:
                    continue
                if not wd_dom_ok(wd, dom, sched_wd, sched_dom):
                    continue
                key = (job_name, sched_hhmm)
                min_gap = 3000  # 每日档：50 分钟内不重复触发

            if key in last_run and now_ts - last_run[key] < min_gap:
                continue

            # A3a: 检查是否被控制面板暂停
            _paused = _load_paused()
            if job_name in _paused:
                continue

            log(f"FIRING: {job_name} ({' '.join(cmd[1:])})")
            last_run[key] = now_ts
            _last_run_ts[job_name] = now_ts
            job_log(job_name, f"=== Job started: {' '.join(cmd[1:])} ===")

            # Spawn job in background
            log_file = LOG_FILES.get(job_name, f"{LOG_DIR}/{job_name}.log")
            try:
                with open(log_file, "a") as lf:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=WORKDIR,
                        stdout=lf,
                        stderr=subprocess.STDOUT
                    )
                    log(f"Job spawned PID={proc.pid}: {job_name}")
                    job_log(job_name, f"Job PID={proc.pid}")
                    # P0-D：spawn 成功即记 last_ok=True（真实结果，非硬编码 True）
                    _last_run_ok[job_name] = True
                    # T1-2: 任务触发计数
                    if observe:
                        try:
                            observe.job_fired(job_name)
                        except Exception:
                            pass
            except Exception as e:
                log(f"Job spawn failed: {job_name} {e}")
                job_log(job_name, f"Job spawn ERROR: {e}")
                _last_run_ok[job_name] = False

        # A3a: 定期落盘调度器状态供 control_server 读取
        _dump_state()
        time.sleep(30)

if __name__ == "__main__":
    main()
