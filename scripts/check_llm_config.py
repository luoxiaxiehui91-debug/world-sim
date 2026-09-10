#!/usr/bin/env python3
"""LLM 配置漂移巡检（09-03，ADR-0015 / question llm-config-doc-drift Enforcement）。

背景：09-02 换模型只更新了运行区真源+CHANGELOG，兜底模板/文档/compose 漂移 15 处
（question 20260903-world-deduction-llm-config-doc-drift）。set_usage 已挂模板自动再生钩子，
本脚本兜住其余漂移面：SSH 手改真源、文档旧模型名、密钥文件安全面。

检查项：
  1. 运行区真源 data/llm_config.json vs 兜底模板 config/llm_config.default.json
  2. 兜底模板 vs git 真源模板（漂移=有已再生改动未 commit）
  3. 活跃文档残留旧模型名（MiniMax-M3 / Qwen3.5-27B / OPENAI_COMPAT_MODEL；
     CHANGELOG/archive/reviews/知识库/ROADMAP 属历史不扫；含「退役/已切换/已移除/已删除/历史/归档」注释行放行）
  4. config/.env 安全面：权限 0600、git check-ignore 通过、无明文入 truth config（api_key 字段）
  5. git pre-commit hook 在位且可执行（拒绝 .env 入库，防泄漏 GitHub）

失败 → ntfy 推送（内容不含任何密钥值）→ exit 1；全过 → 静默 exit 0。
用法：check_llm_config.py [--heartbeat]（heartbeat=全过时也推一条，供周一心跳防「脚本死了没声音」）
依赖 env：NTFY_TOPIC（cron.d 提供；缺省只打印不推送）。
"""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(os.environ.get("REPO_DIR", Path(__file__).resolve().parent.parent))
RUNTIME = Path(os.environ.get("RUNTIME_DIR", REPO.parent / "macro-scan"))
TRUTH_PATH = RUNTIME / "data" / "llm_config.json"
TEMPLATE_PATH = RUNTIME / "config" / "llm_config.default.json"
REPO_TEMPLATE = REPO / "macro-scan" / "config" / "llm_config.default.json"
SECRETS_PATH = RUNTIME / "config" / ".env"

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

STALE_PATTERNS = ["MiniMax-M3", "Qwen3.5-27B", "OPENAI_COMPAT_MODEL"]
# 命中豁免词：历史叙述/规则文本语境（含旧模型名但非「现状残留」）。
# 例：STATUS 历史段「全仓切 deepseek」、版本表「MiniMax-M3主力」、规则「禁留 OPENAI_COMPAT_MODEL」。
# 真残留=无动作词的静态现状句（如「当前默认 MiniMax-M3」），不含这些词，不会被误豁免。
ALLOW_MARKERS = ("退役", "已切换", "已移除", "已删除", "历史", "归档",
                 "收敛", "下线", "切换", "禁留", "主力", "迁移", "重构",
                 "修复", "轮换", "清理", "删除", "切走", "→", "->")
# 目录名级跳过：archive/archived/reviews 为历史归档（可能出现在 macro-scan/docs 等任意层级）
SKIP_DIRS = {".git", "node_modules", "dist", "archived", "archive", "reviews",
             "__pycache__", "知识库"}
SCAN_EXTS = {".md", ".py", ".json", ".yml", ".yaml", ".ts", ".tsx"}


def _push(title: str, message: str):
    if not NTFY_TOPIC:
        print(f"[llmcheck] NTFY_TOPIC 未配置，跳过推送：{title} / {message}")
        return
    try:
        import requests
        requests.put(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            json={"topic": NTFY_TOPIC, "title": title, "message": message},
            timeout=10,
            proxies=None,
        )
    except Exception as e:
        print(f"[llmcheck] ntfy 推送失败：{e}")


def _load_json(p: Path):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"__error__": str(e)}


def check_truth_vs_template(problems: list[str]):
    truth = _load_json(TRUTH_PATH)
    tmpl = _load_json(TEMPLATE_PATH)
    if "__error__" in truth:
        problems.append(f"真源不可读/损坏: {TRUTH_PATH} ({truth['__error__']})")
        return
    if "__error__" in tmpl:
        problems.append(f"兜底模板不可读/损坏: {TEMPLATE_PATH} ({tmpl['__error__']})")
        return
    tu = truth.get("usages") or {}
    mu = tmpl.get("usages") or {}
    if set(tu) != set(mu):
        only_t = sorted(set(tu) - set(mu))
        only_m = sorted(set(mu) - set(tu))
        problems.append(f"真源/模板使用点集合不一致（仅真源:{only_t} 仅模板:{only_m}）")
    for uid in sorted(set(tu) & set(mu)):
        for field in ("platform", "model", "base_url"):
            if tu[uid].get(field) != mu[uid].get(field):
                problems.append(
                    f"使用点 {uid}.{field} 漂移：真源={tu[uid].get(field)} 模板={mu[uid].get(field)}")
    if (truth.get("platforms") or {}) != (tmpl.get("platforms") or {}):
        problems.append("自定义 platforms 节真源/模板不一致")


def check_template_vs_git(problems: list[str]):
    try:
        a = TEMPLATE_PATH.read_bytes()
        b = REPO_TEMPLATE.read_bytes()
        if a != b:
            problems.append(
                "运行区兜底模板与 git 真源模板不一致（模板已自动再生未 commit；"
                "请同步 macro-scan/config/llm_config.default.json 后 git commit）")
    except Exception as e:
        problems.append(f"模板对账失败: {e}")


def check_stale_model_names(problems: list[str]):
    hits = []
    for root, dirs, files in os.walk(REPO):
        rel_root = Path(root).relative_to(REPO).as_posix()
        if rel_root == ".":
            rel_root = ""
        dirs[:] = [d for d in dirs
                   if d not in SKIP_DIRS and f"{rel_root}/{d}".strip("/") not in SKIP_DIRS]
        for fn in files:
            p = Path(root) / fn
            if p.resolve() == Path(__file__).resolve():
                continue  # 不扫自身（docstring/STALE_PATTERNS 含模型名属定义非残留）
            # TuiYan_CHANGELOG.md 等带前缀的变更历史同样不扫（isinstance 判定）
            if ("CHANGELOG" in Path(fn).name or Path(fn).name == "ROADMAP.md"):
                continue
            if p.suffix not in SCAN_EXTS:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if any(m in line for m in ALLOW_MARKERS):
                    continue
                for pat in STALE_PATTERNS:
                    if pat in line:
                        hits.append(f"{p.relative_to(REPO)}:{i}: {line.strip()[:100]}")
    if hits:
        problems.append("活跃文件残留旧模型名（若属合法注释请加「已退役/已切换」标记）:\n  " + "\n  ".join(hits[:10]))


def check_secrets_safety(problems: list[str]):
    # 运行区 config/.env（repo 外）：查权限与格式
    if SECRETS_PATH.exists():
        mode = stat.S_IMODE(SECRETS_PATH.stat().st_mode)
        if mode != 0o600:
            problems.append(f"config/.env 权限为 {oct(mode)}，应为 0o600")
        for i, line in enumerate(SECRETS_PATH.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s or s.split("=", 1)[0].strip() != s.split("=", 1)[0]:
                problems.append(f"config/.env 第{i}行格式异常（应为 KEY=value）")
        # 密钥不得出现在 git 工作树内（运行区路径本身在 repo 外，check-ignore 无意义）
        for i, line in enumerate(SECRETS_PATH.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k = s.split("=", 1)[0].strip()
            v = s.split("=", 1)[1].strip()
            if v and len(v) >= 8:
                # 防呆：密钥值出现在 git 跟踪文件里 = 泄漏
                hits = subprocess.run(
                    ["git", "-C", str(REPO), "grep", "-l", "--", v],
                    capture_output=True, text=True).stdout.strip()
                if hits:
                    problems.append(f"密钥 {k} 的值泄漏进 git 跟踪文件：{hits[:200]}")
                break
    # git 侧：repo 内对应路径（macro-scan/config/.env）必须被 check-ignore 命中（若有人 add 会被拒）
    repo_secret = REPO / "macro-scan" / "config" / ".env"
    r = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", str(repo_secret)])
    if r.returncode != 0:
        problems.append("git 侧 macro-scan/config/.env 未被 gitignore 覆盖（check-ignore 未命中）——泄漏风险！")
    truth_text = TRUTH_PATH.read_text(encoding="utf-8") if TRUTH_PATH.exists() else ""
    if '"api_key"' in truth_text:
        problems.append("真源 llm_config.json 含 api_key 字段（config 永不带 key 不变量被破坏）")


def check_precommit_hook(problems: list[str]):
    hook = REPO / ".git" / "hooks" / "pre-commit"
    if not hook.exists():
        problems.append("git pre-commit hook 缺失（应拒绝 .env 入库，见 ADR-0015）")
        return
    if not os.access(hook, os.X_OK):
        problems.append("git pre-commit hook 无执行权限")


def main() -> int:
    heartbeat = "--heartbeat" in sys.argv
    problems: list[str] = []
    check_truth_vs_template(problems)
    check_template_vs_git(problems)
    check_stale_model_names(problems)
    check_secrets_safety(problems)
    check_precommit_hook(problems)

    if problems:
        msg = f"LLM 配置巡检发现 {len(problems)} 项漂移：\n\n" + "\n\n".join(problems)
        print(f"[llmcheck] ⚠️ 发现漂移：{len(problems)} 项")
        print(msg)
        _push("⚠️ 推演系统 LLM 配置漂移告警", msg[:3500])
        return 1

    print(f"[llmcheck] 全过（真源=模板=git；文档无旧模型名；.env 安全面 OK；hook 在位）")
    if heartbeat:
        _push("✅ LLM 配置巡检心跳", "本周 LLM 配置漂移巡检全过（真源/模板/git 一致，密钥安全面正常）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
