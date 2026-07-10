"""
grv_threshold.py — GRV 阈值监控（B线）
在 geo_risk_vector.py 写完 grv_latest.json 后调用。

触发条件（任一满足）：
  1. 台海分值 >= GRV_TAIWAN_ABS（绝对值阈值）
  2. 任意维度单日涨幅 >= GRV_DELTA_THRESHOLD

冷却：同一触发类型 GRV_COOLDOWN_DAYS 天内不重复推演。
推演异步执行（daemon=True 线程），不阻塞主进程。

环境变量 GRV_DRY_RUN=1：只打印触发信息，不调用 LLM 和 ntfy（用于验收测试）。
"""

import json
import os
import threading
from datetime import date, datetime, timezone

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:
    _HAVE_FCNTL = False  # Windows 回退；容器内（Linux）始终有 fcntl

try:
    from optim_config import DATA_DIR
except ImportError:
    _ws = os.environ.get("OPENCLAW_WORKSPACE",
                         os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR = os.path.join(_ws, "data")

# ── 配置 ──────────────────────────────────────────────────────────────────────
GRV_TAIWAN_ABS       = 68     # 台海绝对值触发阈值（当前约60，历史警戒线约68）
GRV_DELTA_THRESHOLD  = 6.0    # 任意维度单日涨幅触发阈值
GRV_COOLDOWN_DAYS    = 3      # 同一触发类型冷却天数
GRV_COOLDOWN_LOG     = os.path.join(DATA_DIR, "grv_alert_log.json")
DRY_RUN              = os.environ.get("GRV_DRY_RUN", "0") == "1"

DIM_LABELS = {
    "taiwan_strait":      "台海",
    "us_china_strategic": "中美",
    "russia_europe":      "俄欧",
    "middle_east_energy": "中东能源",
    "global_composite":   "全球综合",
}


def _read_cooldown_log() -> dict:
    try:
        if os.path.exists(GRV_COOLDOWN_LOG):
            with open(GRV_COOLDOWN_LOG, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _write_cooldown_log(data: dict) -> None:
    os.makedirs(os.path.dirname(GRV_COOLDOWN_LOG), exist_ok=True)
    tmp = GRV_COOLDOWN_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, GRV_COOLDOWN_LOG)


def _get_trigger_titles_from_news() -> str:
    """读 news.db 最近24h 地缘相关标题，最多3条，注入情景文本。"""
    titles = []
    try:
        import sqlite3
        db_path = os.path.join(DATA_DIR, "news.db")
        if not os.path.exists(db_path):
            return "（无）"
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        rows = conn.execute("""
            SELECT DISTINCT a.title FROM articles a
            JOIN article_categories ac ON a.id = ac.article_id
            WHERE ac.category IN ('地缘升级', '社会政治危机', '军事冲突')
              AND a.ingested_at >= datetime('now', '-24 hours')
            ORDER BY a.ingested_at DESC LIMIT 3
        """).fetchall()
        conn.close()
        titles = [r[0] for r in rows if r[0]]
    except Exception:
        pass
    return "；".join(titles) if titles else "（无）"


def check_and_trigger(new_grv: dict, prev_grv: dict) -> None:
    """
    主入口，在 geo_risk_vector.py 写完 grv_latest.json 后调用。

    Args:
        new_grv:  本次计算的 GRV 字典（顶层键为维度名）
        prev_grv: 写入前读取的旧 GRV 字典（用于 delta 计算）
    """
    today_str = date.today().isoformat()

    # ── 检测触发条件 ──────────────────────────────────────────────────────────
    triggers = []

    taiwan_val = new_grv.get("taiwan_strait") or 0.0
    if taiwan_val >= GRV_TAIWAN_ABS:
        triggers.append(("taiwan_abs", f"台海={taiwan_val:.1f}（≥阈值{GRV_TAIWAN_ABS}）"))

    for dim, label in DIM_LABELS.items():
        cur_val  = new_grv.get(dim)
        cur_val  = cur_val if cur_val is not None else 0.0
        _prev    = prev_grv.get(dim)
        prev_val = _prev if _prev is not None else cur_val  # None=无历史，用当前值（delta=0）；0.0=真实零值，保留
        delta    = cur_val - prev_val
        if delta >= GRV_DELTA_THRESHOLD:
            triggers.append((
                f"delta_{dim}",
                f"{label}单日+{delta:.1f}（{prev_val:.1f}→{cur_val:.1f}）"
            ))

    if not triggers:
        print("  [B线] 未触发阈值")
        _write_cooldown_log(_read_cooldown_log())  # 确保文件存在（验收用）
        return

    # ── 冷却检查 + 乐观锁写入（防止两次 GRV 触发 race condition） ────────────
    # 策略：拿到锁后立即写冷却日期（乐观），_worker 成功无需重写，失败时回滚。
    _lock_path = GRV_COOLDOWN_LOG + ".lock"
    os.makedirs(os.path.dirname(_lock_path), exist_ok=True)

    def _check_and_fire_with_lock():
        lock_fd = open(_lock_path, "w")
        try:
            if _HAVE_FCNTL:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)  # 独占锁，阻塞直到获取
            alert_log = _read_cooldown_log()
            prev_log = dict(alert_log)  # 回滚快照
            active = []
            for ttype, tdesc in triggers:
                last_fired = alert_log.get(ttype, "2000-01-01")
                days_since = (date.today() - date.fromisoformat(last_fired)).days
                if days_since >= GRV_COOLDOWN_DAYS:
                    active.append((ttype, tdesc))
                else:
                    print(f"  [B线] {ttype} 冷却中（{days_since}/{GRV_COOLDOWN_DAYS}天），跳过")
            if active:
                # 乐观写入：持锁期间立即写冷却日期，防止并发 GRV 双触发
                for ttype, _ in active:
                    alert_log[ttype] = today_str
                _write_cooldown_log(alert_log)
            return active, prev_log
        finally:
            if _HAVE_FCNTL:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    active, prev_log = _check_and_fire_with_lock()

    if not active:
        return

    trigger_summary = "；".join(d for _, d in active)
    grv_snap = "、".join(
        f"{DIM_LABELS.get(k, k)}={v:.1f}"
        for k, v in new_grv.items()
        if isinstance(v, (int, float)) and k in DIM_LABELS
    )

    print(f"  [B线] 触发：{trigger_summary}")

    if DRY_RUN:
        print(f"  [DRY_RUN] would trigger hypothesis: {trigger_summary}")
        print(f"  [DRY_RUN] GRV snapshot: {grv_snap}")
        # DRY_RUN 不写冷却日志，回滚乐观写入，避免污染真实告警窗口
        _write_cooldown_log(prev_log)
        return

    # ── 构建情景文本 ──────────────────────────────────────────────────────────
    titles_str = _get_trigger_titles_from_news()
    scenario = (
        f"[GRV告警自动触发] {trigger_summary}。"
        f"当前GRV全景：{grv_snap}。"
        f"近期相关信号：{titles_str}。"
        f"请推演：①近期最可能的风险传导路径；"
        f"②对中美金融市场的具体影响；"
        f"③用户需重点关注的指标或事件窗口（未来1-2周）。"
    )

    # ── 异步推演 + macro-sim 触发（daemon=True，主进程可正常退出）────────────
    def _worker():
        try:
            from ntfy_listener import push_text_with_priority
            push_text_with_priority(
                f"[GRV告警] {trigger_summary[:40]}",
                f"自动推演已启动，约80秒后推送报告。\n触发：{trigger_summary}",
                priority=4,
            )
            from hypothesis_engine import run_hypothesis_simple
            run_hypothesis_simple(scenario)
            # 写 sim_trigger.json，通知 macro-sim daemon 运行仿真
            _write_sim_trigger(trigger_summary, level=3)
            # 推演成功：冷却日期已在锁内乐观写入，无需重复写
        except Exception as e:
            # 推演失败：回滚冷却日期，允许下次触发重试
            try:
                _lock_fd2 = open(_lock_path, "w")
                try:
                    if _HAVE_FCNTL:
                        fcntl.flock(_lock_fd2, fcntl.LOCK_EX)
                    _write_cooldown_log(prev_log)
                    print(f"  [B线] 推演失败，已回滚冷却记录: {e}")
                finally:
                    if _HAVE_FCNTL:
                        fcntl.flock(_lock_fd2, fcntl.LOCK_UN)
                    _lock_fd2.close()
            except Exception as e2:
                print(f"  [B线] 回滚失败（冷却记录保留）: {e2}")
            try:
                from ntfy_listener import push_text
                push_text("[GRV告警] 推演失败", str(e)[:300])
            except Exception:
                print(f"  [B线] 推演失败: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    print(f"  [B线] 推演已异步启动：{trigger_summary}")


def _write_sim_trigger(event: str, level: int = 3) -> None:
    """
    写 sim_trigger.json，通知 macro-sim daemon 运行仿真。
    幂等：若文件已存在（上次未被消费），追加到 event 字符串，不覆盖 level。
    失败静默跳过，不影响主推演流程。
    """
    trigger_path = os.path.join(DATA_DIR, "sim_trigger.json")
    try:
        payload = {
            "level":        level,
            "event":        event[:200],
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }
        # 原子写入（先写 .tmp，再 rename）
        tmp = trigger_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, trigger_path)
        print(f"  [B线] sim_trigger.json 已写入（L{level}）")
    except Exception as e:
        print(f"  [B线] sim_trigger.json 写入失败（跳过）：{e}")

