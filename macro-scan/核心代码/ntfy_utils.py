"""
ntfy_utils.py — ntfy 推送工具集（无循环依赖版）

从 ntfy_listener.py 拆出：push_file / push_text_with_priority / push_markdown
供 weekly_synthesis.py / signal_synthesizer.py / grv_threshold.py 等模块安全 import，
避免这些模块直接 import ntfy_listener 时产生循环依赖。
"""
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

import requests

NTFY_REPORT_TOPIC = os.environ.get("NTFY_TOPIC", "")


def _proxies():
    """ntfy 请求强制直连（CF-2 修复：代理对 ntfy.sh HTTPS 不稳定）。"""
    return None


def push_text(title: str, message: str):
    """推送纯文本消息到 ntfy（支持 emoji 和中文标题）。"""
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
        logging.warning(f"ntfy push_text 失败: {e}")


def push_text_with_priority(title: str, message: str, priority: int = 3):
    """推送文本消息，支持 ntfy priority 字段（1=min … 5=urgent）。"""
    if not NTFY_REPORT_TOPIC:
        return
    try:
        requests.post(
            "https://ntfy.sh/",
            json={"topic": NTFY_REPORT_TOPIC, "title": title, "message": message,
                  "priority": priority},
            proxies=_proxies(),
            timeout=30,
        )
    except Exception as e:
        logging.warning(f"ntfy push_text_with_priority 失败: {e}")


def push_file(title: str, filepath: Path):
    """以 PUT 上传文件附件；标题/文件名中文先 utf-8→latin-1 转换规避 Header 限制。"""
    if not NTFY_REPORT_TOPIC:
        return
    try:
        _title = title.encode("utf-8").decode("latin-1")
        _fname = filepath.name.encode("utf-8").decode("latin-1")
        with open(filepath, "rb") as _f:
            requests.put(
                f"https://ntfy.sh/{NTFY_REPORT_TOPIC}",
                data=_f.read(),
                headers={
                    "Title": _title,
                    "Filename": _fname,
                    "Message": "​".encode("utf-8").decode("latin-1"),
                    "Content-Type": "text/markdown; charset=utf-8",
                },
                proxies=_proxies(),
                timeout=60,
            )
    except Exception as e:
        logging.warning(f"ntfy push_file 失败: {e}")


def push_markdown(title: str, text: str, filename_prefix: str = "report"):
    """把长内容写临时 .md 文件，再用 push_file() 发附件。

    短消息（<200字）仍可用 push_text()；本函数专为长内容报告设计。
    失败时自动降级为 push_text()（截断至 500 字）。
    """
    if not NTFY_REPORT_TOPIC or not text:
        return
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", prefix=f"{filename_prefix}_{ts}_",
            encoding="utf-8", delete=False
        ) as f:
            f.write(text)
            tmp_path = Path(f.name)
        push_file(title, tmp_path)
        tmp_path.unlink(missing_ok=True)
    except Exception as e:
        logging.warning(f"push_markdown 失败，降级文本: {e}")
        push_text(title, text[:500])
