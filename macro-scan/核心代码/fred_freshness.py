"""
fred_freshness.py — FRED 数据新鲜度监控 + 拉取一致性闸（data-freshness 修复）

职责（Spec 3.4 / 第 7 章）：
1. symbol 级一致性检查：DCOILWTICO/BAMLH0A0HYM2/DGS3MO/ICSA 四 symbol 必须全部成功，
   且各自 local_latest 距 FRED 源最新 ≤ 1 交易日（FRED 各序列发布滞后不同，按序列自身比对）。
2. 拉取一致性闸：任一 symbol 失败/落后超容差 → gate_ok=false，写 fred_gate_status.json，
   供 compute_fci（批次2恢复）消费：本次日度重算不落库冻结值。
3. 新鲜度监控：每日生成 fred_freshness.json 清单（symbol/latest_date/status），
   latest_date 距今 > 3 交易日 → stale；连续 2 日 stale → critical（priority 提级）。
4. FCI 面板健康探针：fci_latest.json data_vintage 每日比对，连续冻结 → 告警。
5. 告警通道：ntfy（NTFY_BASE_URL 支持，默认 https://ntfy.sh/，可切 NAS 自托管）。

用法：
  python fred_freshness.py --all        # 清单 + 闸 + stale + FCI 探针（每日调度）
  python fred_freshness.py --gate       # 仅拉取一致性闸
  python fred_freshness.py --fci-probe  # 仅 FCI data_vintage 探针
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

try:
    from optim_config import DATA_DIR
except Exception:
    DATA_DIR = "/workspace/data"

HIST_DIR = os.path.join(DATA_DIR, "fred_history")
MANIFEST_FILE = os.path.join(DATA_DIR, "fred_freshness.json")
GATE_FILE = os.path.join(DATA_DIR, "fred_gate_status.json")
STALE_STATE_FILE = os.path.join(DATA_DIR, "fred_stale_state.json")
FCI_PROBE_STATE_FILE = os.path.join(DATA_DIR, "fred_fci_probe_state.json")
FCI_LATEST_FILE = os.path.join(DATA_DIR, "fci_latest.json")

# 四 symbol 一致性批次（Spec 3.4）：全部成功 + 各自 ≤1 交易日落后 FRED 源最新
FRESH_SYMBOLS = ["DCOILWTICO", "BAMLH0A0HYM2", "DGS3MO", "ICSA"]
TOLERANCE_TRADING_DAYS = 1      # 与 FRED 源最新允许的最大交易日落后
STALE_TRADING_DAYS = 3           # 距今 >3 交易日 → stale
CRITICAL_CONSECUTIVE = 2         # 连续 2 日 stale → critical


def _busday_diff(d1: date, d2: date) -> int:
    """两个日期之间的工作日差（FRED 为交易日序列，忽略节假日误差，容忍度场景足够）。"""
    try:
        import numpy as np
        return int(np.busday_count(d1, d2))
    except Exception:
        # numpy 不可用时的兜底：按周一~周五近似（留痕：仅 fallback 场景）
        days = 0
        cur = d1
        while cur < d2:
            if cur.weekday() < 5:
                days += 1
            cur += timedelta(days=1)
        return days


def _parse(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def latest_local(series_id: str):
    """读本地 CSV 最大日期，无文件/异常返回 None。"""
    path = os.path.join(HIST_DIR, f"{series_id}.csv")
    if not os.path.exists(path):
        return None
    try:
        import pandas as pd
        df = pd.read_csv(path)
        if df.empty or "date" not in df.columns:
            return None
        return str(df["date"].max())
    except Exception:
        return None


def fred_source_latest(series_id: str, fred=None):
    """查 FRED 源该序列最新观测日期（不带则惰性建 fredapi 实例）。

    用 observation_start 限定近 45 天窗口，避免每次全量下载历史（数据新鲜度只需最新日期）。
    """
    try:
        if fred is None:
            from fredapi import Fred
            fred = Fred(api_key=os.environ.get("FRED_API_KEY", "REDACTED_FRED_KEY"))
        start = (date.today() - timedelta(days=45)).isoformat()
        s = fred.get_series(series_id, observation_start=start)
        if s is None or s.empty:
            return None
        s = s.dropna()
        if s.empty:
            return None
        return s.index.max().strftime("%Y-%m-%d")
    except Exception:
        return None


def build_manifest(fred=None) -> list:
    """生成 symbol 清单：symbol/latest_date/source_latest/status。"""
    manifest = []
    for sid in FRESH_SYMBOLS:
        loc = latest_local(sid)
        src = fred_source_latest(sid, fred)
        status = "ok"
        if loc is None:
            status = "missing"
        elif src is not None:
            try:
                diff = _busday_diff(_parse(loc), _parse(src))
                if diff > TOLERANCE_TRADING_DAYS:
                    status = "lagging"
            except Exception:
                status = "unknown"
        # P2 修复（fred-freshness-status-misleading）：增 fresh/lag_days 分离展示——
        # status=ok 仅是"本地 vs 源一致性"，不表达新鲜度；fresh 用日历天宽松判定（≈交易日）
        import datetime as _dt
        _lag = None
        _fresh = None
        if loc:
            try:
                _ld = _parse(loc)
                _lag = (_dt.date.today() - _ld).days
                _fresh = _lag <= 5
            except Exception:
                pass
        manifest.append({
            "symbol": sid,
            "latest_date": loc,
            "source_latest": src,
            "status": status,
            "fresh": _fresh,
            "lag_days": _lag,
        })
    return manifest


def check_gate(manifest: list) -> tuple:
    """拉取一致性闸：全部成功且无落后超容差 → gate_ok=True。返回 (ok, reasons)。"""
    reasons = []
    for m in manifest:
        if m["status"] == "missing":
            reasons.append(f"{m['symbol']}: 本地无数据（missing）")
        elif m["status"] == "lagging":
            reasons.append(
                f"{m['symbol']}: local={m['latest_date']} 落后 FRED={m['source_latest']} "
                f"超 {TOLERANCE_TRADING_DAYS} 交易日"
            )
        elif m["status"] == "unknown":
            reasons.append(f"{m['symbol']}: 日期解析异常（unknown）")
    return (len(reasons) == 0, reasons)


def write_gate(gate_ok: bool, reasons: list, manifest: list) -> None:
    """写闸状态文件；compute_fci（批次2）消费 gate_ok 决定是否落库冻结值。"""
    payload = {
        "gate_ok": gate_ok,
        "as_of": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tolerance_trading_days": TOLERANCE_TRADING_DAYS,
        "reasons": reasons,
        "symbols": manifest,
    }
    tmp = GATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, GATE_FILE)


def write_manifest(manifest: list) -> None:
    payload = {
        "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "symbols": manifest,
    }
    tmp = MANIFEST_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MANIFEST_FILE)


def _load_json(path: str, default: dict) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def stale_check(manifest: list) -> list:
    """新鲜度：latest_date 距今 >3 交易日 → stale；连续 2 日 → critical。返回告警消息列表。"""
    state = _load_json(STALE_STATE_FILE, {"consecutive": {}})
    consecutive = state.get("consecutive", {})
    today = date.today()
    alerts = []
    for m in manifest:
        sid = m["symbol"]
        loc = m.get("latest_date")
        if not loc:
            continue
        try:
            lag = _busday_diff(_parse(loc), today)
        except Exception:
            continue
        if lag > STALE_TRADING_DAYS:
            consecutive[sid] = consecutive.get(sid, 0) + 1
            level = "critical" if consecutive[sid] >= CRITICAL_CONSECUTIVE else "stale"
            priority = 4 if level == "critical" else 3
            alerts.append(
                f"[{level}] FRED {sid} 新鲜度过期：latest={loc}，距今 {lag} 交易日 "
                f"(阈值 >{STALE_TRADING_DAYS}，连续 {consecutive[sid]} 日)。建议：检查拉取链路/手动补跑。"
            )
            # ntfy priority 单独推送
            _push(priority, f"FRED {sid} {level}", alerts[-1])
        else:
            consecutive[sid] = 0
    _save_json(STALE_STATE_FILE, {"consecutive": consecutive, "checked": today.isoformat()})
    return alerts


def fci_probe() -> list:
    """FCI 面板健康探针：fci_latest.data_vintage 每日比对，连续冻结 → 告警。"""
    if not os.path.exists(FCI_LATEST_FILE):
        return []
    try:
        with open(FCI_LATEST_FILE, encoding="utf-8") as f:
            latest = json.load(f)
        vintage = str(latest.get("data_vintage", ""))
    except Exception:
        return []
    if not vintage:
        return []
    state = _load_json(FCI_PROBE_STATE_FILE, {"last_vintage": None, "freeze_days": 0})
    freeze_days = 0
    if state.get("last_vintage") == vintage:
        freeze_days = state.get("freeze_days", 0) + 1
    else:
        freeze_days = 0
    _save_json(FCI_PROBE_STATE_FILE, {
        "last_vintage": vintage,
        "freeze_days": freeze_days,
        "checked": datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    if freeze_days >= CRITICAL_CONSECUTIVE:
        msg = (
            f"[critical] FCI data_vintage 连续 {freeze_days} 日冻结于 {vintage}。"
            "建议：检查 compute_fci / FRED 拉取是否停摆。"
        )
        _push(4, "FCI data_vintage 冻结", msg)
        return [msg]
    return []


def _push(priority: int, title: str, message: str) -> None:
    """ntfy 告警（主通道）。复用 ntfy_utils，支持 NTFY_BASE_URL。"""
    try:
        from ntfy_utils import push_text_with_priority
        push_text_with_priority(title, message, priority)
    except Exception as e:
        # 留痕：告警通道故障不静默吞掉（写日志，仍继续）
        try:
            import logging
            logging.warning(f"fred_freshness ntfy push 失败: {e}")
        except Exception:
            print(f"ntfy push 失败: {e}", flush=True)


def run_gate(alert: bool = True) -> tuple:
    """拉取一致性闸主流程。返回 (gate_ok, manifest)。fetch_fred_history 拉取后调用。"""
    manifest = build_manifest()
    gate_ok, reasons = check_gate(manifest)
    write_manifest(manifest)
    write_gate(gate_ok, reasons, manifest)
    if alert and not gate_ok:
        detail = "；".join(reasons) if reasons else "四 symbol 全部失败"
        _push(4, "FRED 拉取一致性闸 FAIL", f"本次日度重算不落库冻结值。{detail}。建议：人工检查 FRED API/代理。")
    return gate_ok, manifest


def main():
    import argparse
    parser = argparse.ArgumentParser(description="FRED 新鲜度监控 + 拉取一致性闸")
    parser.add_argument("--all", action="store_true", help="闸 + stale + FCI 探针")
    parser.add_argument("--gate", action="store_true", help="仅拉取一致性闸")
    parser.add_argument("--fci-probe", action="store_true", help="仅 FCI data_vintage 探针")
    args = parser.parse_args()

    if args.fci_probe:
        fci_probe()
        return
    if args.gate or args.all:
        gate_ok, manifest = run_gate(alert=True)
        print(f"[fred_freshness] gate_ok={gate_ok}")
        if args.all:
            stale_check(manifest)
            fci_probe()
        return
    # 默认 --all
    gate_ok, manifest = run_gate(alert=True)
    print(f"[fred_freshness] gate_ok={gate_ok}")
    stale_check(manifest)
    fci_probe()


if __name__ == "__main__":
    main()
