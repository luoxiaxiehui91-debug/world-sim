#!/usr/bin/env python3
"""
ntfy 双向指令监听器：订阅指令主题，解析命令，触发分析或返回状态消息。

CF-2 修复（2026-05-27）：ntfy 请求强制直连，不走代理。
  原因：NAS mihomo 代理对 ntfy.sh 的 HTTPS 连接不稳定（SSL EOF / ProxyError），
  与 run_macro_analysis.py 的 NA-1 修复同理。直连测试通过（3.6s vs 代理 4.2s+SSL错误）。
"""
import os
import time
import subprocess
import threading
import requests
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime

# ── 本地模块 ──────────────────────────────────────────────────
from ntfy_utils import push_file, push_text_with_priority, push_markdown
from optim_config import DATA_DIR
from situation_tracker import (
    get_context, format_for_ntfy, list_situations,
    update_situation, update as update_situations,
)
from hybrid_llm import reason as llm_reason

# ── 配置 ──────────────────────────────────────────────────────
NTFY_CMD_TOPIC    = os.environ.get("NTFY_CMD_TOPIC", "")
NTFY_REPORT_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_CMD_SECRET   = os.environ.get("NTFY_CMD_SECRET", "")
OUTBOUND_PROXY    = os.environ.get("OUTBOUND_PROXY", "")
WORKSPACE         = Path(os.environ.get("OPENCLAW_WORKSPACE", "/workspace"))
REPORT_DIR        = WORKSPACE / "docs" / "分析报告"

VALID_COUNTRIES = {"china", "us", "both"}
VALID_DEPTHS    = {"quick", "standard", "deep"}


# ── 推送工具 ──────────────────────────────────────────────────
def _proxies():
    """返回 None（ntfy 请求强制直连，不走代理）。

    CF-2: 代理对 ntfy.sh HTTPS 不稳定（SSLEOFError / ProxyError），
    直连更快更稳。FRED 等其他请求仍由各自模块自行决定是否走代理。
    """
    return None

def push_text(title: str, message: str):
    """通过 ntfy JSON body 推送文本消息（支持 emoji 和中文标题，规避 latin-1 限制）。"""
    if not NTFY_REPORT_TOPIC:
        return
    try:
        requests.post(
            "https://ntfy.sh/",
            json={"topic": NTFY_REPORT_TOPIC, "title": title, "message": message},
            proxies=_proxies(),
            timeout=30,
        )
    except Exception as e:
        logging.warning(f"推送失败: {e}")


# push_file / push_text_with_priority 已移至 ntfy_utils.py（避免循环导入）


# ── 指令解析 ──────────────────────────────────────────────────
def parse_command(message: str):
    """返回 (cmd, args) 或 None（密钥错误 / 格式无效）。"""
    parts = message.strip().split()
    if not parts:
        return None
    if NTFY_CMD_SECRET:
        if parts[0] != NTFY_CMD_SECRET:
            return None
        parts = parts[1:]
    if not parts:
        return None
    return parts[0].lower(), [p.lower() for p in parts[1:]]


# ── 指令处理 ──────────────────────────────────────────────────
def cmd_analysis(country: str, args: list):
    """触发宏观分析报告生成（异步执行，立即返回不阻塞轮询循环）。"""
    depth = args[0] if args and args[0] in VALID_DEPTHS else "standard"
    country_label = {"china": "中国", "us": "美国", "both": "中美"}.get(country, country)
    push_text(f"[指令] 开始生成{country_label}报告", f"depth={depth}，请稍候（约5-15分钟）")

    def _run():
        result = subprocess.run(
            ["python3", "run_macro_analysis.py", "--country", country, "--depth", depth, "--force"],
            capture_output=True, text=True, cwd="/app",
        )
        if result.returncode != 0:
            push_text("⚠️ 分析失败", (result.stderr or result.stdout or "未知错误")[-400:])

    threading.Thread(target=_run, daemon=True).start()


def cmd_status():
    """推送容器运行时间、最新报告文件名、news.db 文章数、定时任务计划等系统状态摘要。"""
    lines = []

    # 容器运行时间
    try:
        uptime_s = float(open("/proc/uptime").read().split()[0])
        h, m = divmod(int(uptime_s) // 60, 60)
        lines.append(f"容器运行：{h}h {m}m")
    except Exception:
        lines.append("容器运行：未知")

    # 最新报告
    if REPORT_DIR.exists():
        reports = sorted(REPORT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if reports:
            r = reports[0]
            ts = datetime.fromtimestamp(r.stat().st_mtime).strftime("%m-%d %H:%M")
            lines.append(f"最新报告：{r.name[:28]}… ({ts})")
        else:
            lines.append("最新报告：无")
    else:
        lines.append("最新报告：目录不存在")

    # news.db 文章数
    try:
        import pg_read as _pg
        conn = _pg.connect()
        if conn is not None:
            count = conn.execute("SELECT COUNT(*) FROM news.articles").fetchone()[0]
            conn.close()
            lines.append(f"新闻库：{count} 篇")
        else:
            lines.append("新闻库：未找到")
    except Exception:
        lines.append("新闻库：读取失败")

    lines.append("定时任务：07:30晨报 / 20:00美国 / 20:15中国 / 每月1日校验")
    push_text("📊 系统状态", "\n".join(lines))


def cmd_last(args: list):
    """以文件附件形式重新推送最新分析报告，args[0] 可指定 china/us/both 过滤。"""
    if not REPORT_DIR.exists():
        push_text("⚠️ 无报告", "报告目录不存在")
        return

    reports = sorted(REPORT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    if args and args[0] in VALID_COUNTRIES:
        label = {"china": "中国", "us": "美国", "both": "中美"}[args[0]]
        reports = [r for r in reports if label in r.name]

    if not reports:
        push_text("⚠️ 无报告", "找不到匹配的报告")
        return

    latest = reports[0]
    ts = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%m-%d %H:%M")
    push_file(f"[重发] {latest.stem[:24]} ({ts})", latest)


def cmd_news():
    """触发新闻弱信号扫描（异步执行，立即返回不阻塞轮询循环）。"""
    push_text("[指令] 开始新闻扫描", "scan_weak_signals.py 运行中…")

    def _run():
        result = subprocess.run(
            ["python3", "scan_weak_signals.py"],
            capture_output=True, text=True, cwd="/app",
        )
        output = (result.stdout or result.stderr or "无输出").strip().splitlines()
        summary = "\n".join(output[-15:])
        if result.returncode == 0:
            push_text("🗞 新闻扫描完成", summary)
        else:
            push_text("⚠️ 新闻扫描失败", summary)

    threading.Thread(target=_run, daemon=True).start()


def cmd_verify():
    """触发预测校验（异步执行，立即返回不阻塞轮询循环）。"""
    push_text("[指令] 开始预测校验", "verify_predictions.py 运行中…")

    def _run():
        result = subprocess.run(
            ["python3", "verify_predictions.py"],
            capture_output=True, text=True, cwd="/app",
        )
        output = (result.stdout or result.stderr or "无输出").strip().splitlines()
        summary = "\n".join(output[-15:])
        if result.returncode == 0:
            push_text("✅ 预测校验完成", summary)
        else:
            push_text("⚠️ 预测校验失败", summary)

    threading.Thread(target=_run, daemon=True).start()


def cmd_hypothesis(args: list):
    """触发假设推演：hypothesis <情景描述> [L1|L2|L3] [deep]。"""
    if not args:
        push_text("⚠️ 用法错误", "格式：hypothesis 台海冲突升级 [L2] [deep]\n示例：hypothesis 台海 L2\n深度：hypothesis 台海封锁 L3 deep")
        return

    # 解析 depth（可选末尾参数 "deep"）
    depth = "standard"
    scenario_parts = list(args)
    if scenario_parts and scenario_parts[-1].lower() == "deep":
        depth = "deep"
        scenario_parts.pop()

    # 解析烈度（可选最后一个参数为 L1/L2/L3）
    severity = None
    if scenario_parts and scenario_parts[-1].upper() in ("L1", "L2", "L3"):
        severity = scenario_parts.pop().upper()
    scenario_text = " ".join(scenario_parts)

    sev_label = {"L1": "压力/紧张", "L2": "冲突/震荡", "L3": "危机/断裂"}.get(severity or "L2", "")
    depth_label = "深度多步推理（约15-20分钟）" if depth == "deep" else "标准（约5-10分钟）"
    push_text(
        f"[假设推演] 开始处理：{scenario_text}",
        f"烈度：{severity or 'L2（自动）'}（{sev_label}）\n模式：{depth_label}",
    )

    def _run():
        cmd = ["python3", "run_macro_analysis.py", "--hypothesis", scenario_text,
               "--depth", depth]
        if severity:
            cmd += ["--hypothesis-severity", severity]
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd="/app",
        )
        if result.returncode != 0:
            push_text("⚠️ 假设推演失败", (result.stderr or result.stdout or "未知错误")[-400:])

    threading.Thread(target=_run, daemon=True).start()


def cmd_ask(args: list):
    """自由提问：根据当前系统快照回答任意问题（Q&A 模式，约15-30秒）。"""
    if not args:
        push_text("⚠️ 用法错误", "格式：ask <你的问题>\n示例：ask 现在最值得担心的3件事？")
        return

    question = " ".join(args)
    push_text("[问答] 处理中…", f"问题：{question[:60]}\n（约15-30秒）")

    def _run():
        try:
            # 读取快速上下文
            context_parts = []

            # GRV
            try:
                import json as _json
                _grv_path = _json.loads(open(f"{DATA_DIR}/grv_latest.json").read()) \
                    if __import__("os").path.exists(f"{DATA_DIR}/grv_latest.json") else {}
                if _grv_path:
                    grv_lines = ["[地缘风险 GRV]"]
                    for k, label in [("taiwan_strait","台海"),("us_china_strategic","中美"),
                                     ("russia_europe","俄欧"),("middle_east_energy","中东能源")]:
                        v = _grv_path.get(k)
                        if v is not None:
                            grv_lines.append(f"  {label}: {v:.1f}")
                    context_parts.append("\n".join(grv_lines))
            except Exception:
                pass

            # 情境事件
            try:
                ctx = get_context(max_events=4)
                if ctx:
                    context_parts.append(ctx)
            except Exception:
                pass

            # 最近信号
            try:
                import json as _json, os as _os
                _log_path = _os.path.join(DATA_DIR, "weak_signal_log.json")
                if _os.path.exists(_log_path):
                    _log = _json.load(open(_log_path, encoding="utf-8"))
                    recent = (_log if isinstance(_log, list) else [])[-5:]
                    if recent:
                        sig_lines = ["[近期弱信号]"]
                        for s in recent:
                            sig_lines.append(f"  {s.get('indicator_name','')} {s.get('level','')} {s.get('value','')}")
                        context_parts.append("\n".join(sig_lines))
            except Exception:
                pass

            context = "\n\n".join(context_parts) if context_parts else "（当前无缓存数据）"

            prompt = (
                f"用户问题：{question}\n\n"
                f"当前系统数据快照：\n{context}\n\n"
                "请根据以上数据直接回答用户问题，用中文，简洁准确，200字以内。"
                "如果数据不足以回答，明确说明缺少哪方面的数据，不要猜测。"
            )

            system = "你是宏观世界分析助手，回答基于提供的数据快照，言简意赅，区分已知事实和推断。"
            answer = llm_reason(prompt, system=system, mode="auto", max_tokens=400)
            push_markdown(f"💬 {question[:30]}…", answer.strip(), "ask")

        except Exception as e:
            push_text("⚠️ 问答失败", f"错误：{str(e)[:200]}")

    threading.Thread(target=_run, daemon=True).start()


def cmd_situations(args: list):
    """列出当前追踪的所有事件状态。"""
    try:
        all_sits = list_situations()
        pending = [s for s in all_sits if s.get("needs_review", False)]
        main_text = format_for_ntfy()
        if pending:
            pending_text = "\n⏳ 待确认话题：\n" + "\n".join(
                f"  [{s['id']}] {s['name']}（{s.get('category','?')}）"
                for s in pending
            )
            main_text = main_text + pending_text + "\n\n确认：1900 confirm_situation <id>\n忽略：1900 dismiss_situation <id>"
        push_text("🗺 追踪事件", main_text)
    except Exception as e:
        push_text("⚠️ 事件列表失败", str(e)[:200])


def cmd_confirm_situation(args: list):
    """确认追踪自动检测的新情况，去掉 needs_review 标记。"""
    if not args:
        push_text("⚠️ 用法", "格式：confirm_situation <id>")
        return
    sit_id = args[0]
    try:
        # 先找到名称用于提示
        sits = list_situations()
        name = next((s.get("name", sit_id) for s in sits if s.get("id") == sit_id), sit_id)
        ok = update_situation(sit_id, needs_review=False, auto_confirmed=True)
        if ok:
            push_text("✅ 已确认追踪", f'"{name}" 已开始正式追踪')
        else:
            push_text("⚠️ 未找到", f"ID={sit_id} 不存在，发 1900 situations 查看列表")
    except Exception as e:
        push_text("⚠️ 确认失败", str(e)[:200])


def cmd_dismiss_situation(args: list):
    """忽略并归档自动检测的情况（话题再次升温会自动恢复）。"""
    if not args:
        push_text("⚠️ 用法", "格式：dismiss_situation <id>")
        return
    sit_id = args[0]
    try:
        import yaml as _yaml
        import os as _os
        from datetime import datetime as _dt, timezone as _tz

        # 找到目标情况
        sits = list_situations()
        target = next((s for s in sits if s.get("id") == sit_id), None)
        if not target:
            push_text("⚠️ 未找到", f"ID={sit_id}")
            return

        # 写入归档文件
        archive_file = _os.path.join(DATA_DIR, "situations_archive.yaml")
        archive = {}
        if _os.path.exists(archive_file):
            with open(archive_file, encoding="utf-8") as f:
                archive = _yaml.safe_load(f) or {}
        archived_list = archive.get("archived", [])
        import copy as _copy
        archived_entry = _copy.deepcopy(target)
        archived_entry["dismissed_at"] = _dt.now(_tz.utc).isoformat()
        archived_entry["dismissal_reason"] = "user"
        archived_list.append(archived_entry)
        _tmp_379 = archive_file + ".tmp"
        with open(_tmp_379, "w", encoding="utf-8") as f:
            _yaml.dump({"archived": archived_list}, f, allow_unicode=True,
                       default_flow_style=False, sort_keys=False)
        os.replace(_tmp_379, archive_file)

        # 从主文件移除（标记 status=resolved，触发 situation_tracker 过滤）
        update_situation(sit_id, status="resolved", dismissed_at=_dt.now(_tz.utc).isoformat())

        push_text("🗑 已归档", f'情况"{target.get("name","")}"已忽略。话题再次升温时会自动提醒。')
    except Exception as e:
        push_text("⚠️ 归档失败", str(e)[:200])


def cmd_narrative():
    """立即生成并推送今日世界摘要（不等待07:00定时任务）。"""
    push_text("[摘要] 生成中…", "今日世界摘要，约15秒…")

    def _run():
        try:
            from daily_narrative import generate
            text = generate()
            from datetime import datetime
            today_str = datetime.now().strftime("%m月%d日")
            push_markdown(f"📡 今日世界摘要 {today_str}", text, "narrative")
        except Exception as e:
            push_text("⚠️ 摘要生成失败", str(e)[:200])

    threading.Thread(target=_run, daemon=True).start()


def cmd_weekly():
    """立即生成并推送本周综合报告。"""
    push_text("[周报] 生成中…", "本周世界综合回顾，约20秒…")

    def _run():
        try:
            from weekly_synthesis import generate
            text = generate()
            from datetime import datetime
            week_str = datetime.now().strftime("第%V周")
            push_markdown(f"📊 本周世界回顾 {week_str}", text, "weekly")
        except Exception as e:
            push_text("⚠️ 周报生成失败", str(e)[:200])

    threading.Thread(target=_run, daemon=True).start()


def cmd_help():
    """推送所有可用指令列表（含语法示例）到 ntfy。"""
    push_text("📋 可用指令", (
        "（所有指令前加密钥）\n"
        "\n分析报告：\n"
        "  china / us / both\n"
        "  china quick  / us deep  等\n"
        "\n自由问答（Q&A）：\n"
        "  ask 现在最值得担心的3件事？\n"
        "  ask 台海最近有什么新动向？\n"
        "  ask 美联储下次会议预期？\n"
        "\n摘要与事件：\n"
        "  narrative  立即生成今日摘要\n"
        "  weekly     立即生成本周综合回顾\n"
        "  situations 查看追踪事件状态（含待确认）\n"
        "  confirm_situation <id>  确认追踪新情况\n"
        "  dismiss_situation <id>  忽略/归档某情况\n"
        "\n查询：\n"
        "  status   系统状态\n"
        "  last     最新报告附件\n"
        "  last china/us/both\n"
        "  help     本帮助\n"
        "\n触发子模块：\n"
        "  news     新闻弱信号扫描\n"
        "  verify   预测命中率校验\n"
        "\n假设推演：\n"
        "  hypothesis 台海冲突升级\n"
        "  hypothesis 台海 L2\n"
        "  hypothesis 台海+油价 L2   （组合情景）\n"
        "  hypothesis 台海封锁 L3 deep  （多步推理）\n"
        "\n信号合成（synthesis）：\n"
        "  synthesize <rule_id>     手动触发某条合成规则（跳过冷却）\n"
        "  silence <rule_id> [7d]   静默某条规则 N 天（默认7天）"
    ))


def cmd_synthesize(args: list):
    """手动触发指定 synthesis 规则（跳过冷却检查）。"""
    if not args:
        push_text("⚠️ 用法错误", "格式：synthesize <rule_id>\n示例：synthesize R06_protest_political_crisis")
        return
    rule_id = args[0]
    push_text_with_priority(f"[指令] 手动触发规则：{rule_id}", "signal_synthesizer 运行中…", priority=3)

    def _run():
        result = subprocess.run(
            ["python3", "signal_synthesizer.py", "--force-rule", rule_id],
            capture_output=True, text=True, cwd="/app",
        )
        output = (result.stdout or result.stderr or "无输出").strip().splitlines()
        summary = "\n".join(output[-15:])
        if result.returncode == 0:
            push_text_with_priority(f"[自动推演] {rule_id}", summary, priority=2)
        else:
            push_text(f"⚠️ 规则触发失败：{rule_id}", summary)

    threading.Thread(target=_run, daemon=True).start()


def cmd_silence(args: list):
    """静默指定 synthesis 规则 N 天（写入虚拟冷却记录）。"""
    if not args:
        push_text("⚠️ 用法错误", "格式：silence <rule_id> [天数]\n示例：silence R06_protest_political_crisis 7d")
        return
    rule_id = args[0]
    days = 7
    if len(args) > 1:
        try:
            days = int(args[1].rstrip("d"))
        except ValueError:
            pass

    try:
        import sqlite3 as _sq
        import json as _json
        import os as _os
        from datetime import datetime as _dt, timezone as _tz
        db_path = _os.path.join(DATA_DIR, "news.db")
        now_str = _dt.now(_tz.utc).isoformat()
        summary = _json.dumps({"silence_days": days}, ensure_ascii=False)
        # 08-18 P0-4 硬化：_PG_ONLY=1 走 PG 旁路；非 _PG_ONLY 但 SQLite 已删（P6）
        # → 禁止 sqlite3.connect 复生空库（recreate/env 丢失时的地雷守卫）
        if _os.environ.get("WORLDSIM_SQLITE_OFF") == "1":
            import pg_write_collection as _pwc
            log_id = _pwc._next_id("news.synthesis_log")
            if log_id:
                _pwc.upsert_synthesis_log(log_id, rule_id, now_str, None, summary,
                                         "", 0, 0, "user_silence")
            push_text(f"[状态] 规则已静默", f"规则：{rule_id}\n静默天数：{days}天")
            return
        if not _os.path.exists(db_path):
            push_text("[状态] 规则已静默", f"规则：{rule_id}\n静默天数：{days}天（SQLite 已退役，未落库）")
            return
        conn = _sq.connect(db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        with conn:
            cur = conn.execute("""
                INSERT INTO synthesis_log
                (rule_id, triggered_at, trigger_summary, suppress_reason)
                VALUES (?, ?, ?, 'user_silence')
            """, (rule_id, now_str, summary))
            log_id = cur.lastrowid
        conn.close()
        # E0-C/P3: 同步落 PG（非阻断）
        try:
            from pg_write_collection import upsert_synthesis_log
            upsert_synthesis_log(log_id, rule_id, now_str, None, summary,
                                 "", 0, 0, "user_silence")
        except Exception:
            pass
        push_text(f"[状态] 规则已静默", f"规则：{rule_id}\n静默天数：{days}天")
    except Exception as e:
        push_text("⚠️ 静默失败", str(e)[:200])


def handle(message: str):
    """解析并分派指令：密钥验证 → 命令路由 → 推送结果（未知指令推送 help 提示）。"""
    result = parse_command(message)
    if result is None:
        logging.warning(f"忽略（密钥错误或格式无效）: {message!r}")
        return
    cmd, args = result
    logging.info(f"执行指令: {cmd} {args}")

    if cmd in VALID_COUNTRIES:
        cmd_analysis(cmd, args)
    elif cmd == "status":
        cmd_status()
    elif cmd == "last":
        cmd_last(args)
    elif cmd == "news":
        cmd_news()
    elif cmd == "verify":
        cmd_verify()
    elif cmd == "hypothesis":
        cmd_hypothesis(args)
    elif cmd == "synthesize":
        cmd_synthesize(args)
    elif cmd == "silence":
        cmd_silence(args)
    elif cmd == "ask":
        cmd_ask(args)
    elif cmd in ("situations", "situation"):
        cmd_situations(args)
    elif cmd in ("confirm_situation", "confirm"):
        cmd_confirm_situation(args)
    elif cmd in ("dismiss_situation", "dismiss"):
        cmd_dismiss_situation(args)
    elif cmd == "narrative":
        cmd_narrative()
    elif cmd in ("weekly", "week"):
        cmd_weekly()
    elif cmd == "help":
        cmd_help()
    else:
        push_text("⚠️ 未知指令", f"不认识'{cmd}'，发送'help' 查看可用指令")


# ── 主循环 ────────────────────────────────────────────────────
def listen():
    """主轮询循环（30s 间隔），用 since= 过滤历史消息，每轮调用 handle() 分派指令。
    轮询而非流式订阅，防止代理截断长连接。"""
    if not NTFY_CMD_TOPIC:
        logging.error("NTFY_CMD_TOPIC 未配置，监听器退出")
        return

    since = str(int(time.time())) + "s"
    url = f"https://ntfy.sh/{NTFY_CMD_TOPIC}/json"

    logging.info(f"开始轮询指令主题: {NTFY_CMD_TOPIC}（每30秒）")
    while True:
        try:
            params = {"poll": "1", "since": since}
            with requests.get(url, params=params, proxies=_proxies(), timeout=(10, 30)) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode("utf-8"))
                        msg_id = data.get("id", "")
                        msg = data.get("message", "")
                        if msg:
                            logging.info(f"收到消息: {msg!r}")
                            handle(msg)
                        if msg_id:
                            since = msg_id
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            logging.warning(f"轮询失败: {e}")
        time.sleep(30)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [LISTENER] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    listen()
