"""
混合LLM调用层：日常简报用 SiliconFlow，复杂推演可选 Claude API。
"""
import os
import time
import requests
import concurrent.futures
from optim_config import ANTHROPIC_API_KEY
from llm_usage import get_model as llm_usage_get_model
from llm_usage import resolve, get_secret

_TMP_DIR = os.environ.get("TMPDIR", "/tmp")
CLAUDECODE_PROMPT_FILE   = os.path.join(_TMP_DIR, "llm_prompt.txt")
CLAUDECODE_RESPONSE_FILE = os.path.join(_TMP_DIR, "llm_response.txt")
CLAUDECODE_TIMEOUT       = 600   # 秒

SILICONFLOW_URL   = "https://api.siliconflow.cn/v1"
SILICONFLOW_MODEL = os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V4-Flash")


_PG_HOST_LLM = "worldsim-pg"
_PG_PORT_LLM = 5432
_PG_DB_LLM   = "worldsim"
_PG_USER_LLM = "worldsim_app"


def _log_token_usage(usage_id=None, platform=None, model=None, prompt_tokens=None,
                     completion_tokens=None, total_tokens=None, call_ms=None,
                     ok=True, err=None):
    """LLM 用量记账（CHG-20260924T002608）：非侵入，任何异常只提示、绝不中断主流程。"""
    try:
        pw = os.environ.get("WORLDSIM_APP_PW")
        if not pw:
            return
        import psycopg
        conn = psycopg.connect(host=_PG_HOST_LLM, port=_PG_PORT_LLM, dbname=_PG_DB_LLM,
                               user=_PG_USER_LLM, password=pw, autocommit=True,
                               connect_timeout=5)
        try:
            conn.execute(
                "INSERT INTO public.llm_token_usage (usage_id, platform, model,"
                " prompt_tokens, completion_tokens, total_tokens, call_ms, ok, err)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (usage_id, platform, model, prompt_tokens, completion_tokens,
                 total_tokens, call_ms, ok, (str(err)[:500] if err else None)),
            )
        finally:
            conn.close()
    except Exception as e:
        print(f"[llm_token_usage] 记账失败(不影响主流程): {type(e).__name__}: {str(e)[:120]}")


def _sf_key() -> str:
    """SiliconFlow 密钥（09-03 ADR-0015：config/.env 优先热读取 → env 兜底；
    由模块级常量改为调用时读取，控制台改 key 免 recreate 即时生效）。"""
    return get_secret("SILICONFLOW_API_KEY") or ""

# （08-23：MiniMax 平台退役，相关常量与调用函数已删除）

# 平台 id → env 变量名（call_openai_compat 按 resolved.platform 取默认 key）
_PLATFORM_ENV_KEYS = {
    "siliconflow": "SILICONFLOW_API_KEY",
    "mimo_plan": "OPENAI_COMPAT_KEY",
    "mimo_api": "MIMO_API_KEY",
}

# 重试配置
_CALL_LOCAL_MAX_RETRIES = 1      # 空响应/可重试错误最多重试次数（1次重试+原始=共2次即降级）
_CALL_LOCAL_RETRY_DELAY = 5      # 重试间隔（秒）

# 宏观推演专用 system prompt
MACRO_SYSTEM_PROMPT = """你是一位严谨的宏观经济推演专家，擅长多步因果链分析。

分析要求：
1. 每个推演步骤必须说明：变量→传导机制→下游影响，并给出方向和量级估计
2. 区分短期（1-3个月）、中期（3-12个月）、长期（>12个月）影响
3. 明确说明关键假设和主要不确定性来源
4. 结论给出概率区间，而非单点预测
5. 如果与历史案例有可比性，请引用并说明异同

禁止：空泛描述、无依据的断言、忽略不确定性。"""


def _estimate_tokens(text: str) -> int:
    """粗估 token 数（英文约4字符/token，中文约2字符/token）。"""
    chinese = sum(1 for c in text if '一' <= c <= '鿿')
    other   = len(text) - chinese
    return chinese // 2 + other // 4


def call_claudecode(prompt: str, system: str = "") -> str:
    """通过文件与 Claude Code 交互：写 prompt，等待响应文件出现。
    用 PID 命名文件，避免多进程互相抢占。
    """
    pid = os.getpid()
    _tmp = os.environ.get("TMPDIR", "/tmp")
    prompt_file   = os.path.join(_tmp, f"llm_prompt_{pid}.txt")
    response_file = os.path.join(_tmp, f"llm_response_{pid}.txt")
    pid_pointer   = os.path.join(_tmp, "llm_latest_pid.txt")

    # 清理本 PID 可能的残留
    for f in (prompt_file, response_file):
        if os.path.exists(f):
            try: os.remove(f)
            except OSError: pass

    # 写 PID 指针（方便外部找到当前 prompt 文件）
    os.makedirs(_tmp, exist_ok=True)
    with open(pid_pointer, "w", encoding="utf-8") as f:
        f.write(str(pid))

    # 写 prompt
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(f"[SYSTEM]\n{system or MACRO_SYSTEM_PROMPT}\n\n[PROMPT]\n{prompt}")

    print(f"[claudecode] prompt 已写入 {prompt_file}，等待 Claude Code 响应...")

    deadline = time.time() + CLAUDECODE_TIMEOUT
    while time.time() < deadline:
        if os.path.exists(response_file):
            time.sleep(0.8)   # 等写入完成
            try:
                with open(response_file, "r", encoding="utf-8") as f:
                    response = f.read().strip()
                if response:
                    for f in (response_file, prompt_file, pid_pointer):
                        try: os.remove(f)
                        except OSError: pass
                    return response
            except (FileNotFoundError, PermissionError):
                pass  # 文件刚好被其他进程抢走，继续轮询
        time.sleep(2)

    raise TimeoutError(f"Claude Code 未在 {CLAUDECODE_TIMEOUT}s 内响应")


def _do_siliconflow_request(prompt: str, system: str, max_tokens: int):
    """执行单次 SiliconFlow API 请求，返回 (result_str, response_obj, elapsed)。
    result_str 为 None 表示空响应（需要重试）。
    抛出可重试异常（HTTPError 429/503）或不可重试异常。
    """
    start_ts = time.time()
    try:
        resp = requests.post(
            f"{SILICONFLOW_URL}/chat/completions",
            headers={"Authorization": f"Bearer {_sf_key()}", "Content-Type": "application/json"},
            json={
                "model": SILICONFLOW_MODEL,
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system or MACRO_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
            },
            timeout=180,
        )
        elapsed = time.time() - start_ts
        rl_remain = resp.headers.get("X-RateLimit-Remaining", "N/A")
        rl_reset  = resp.headers.get("X-RateLimit-Reset", "N/A")
        print(f"[call_local] RESPONSE | status={resp.status_code} elapsed={elapsed:.1f}s rateLimit_remain={rl_remain} reset={rl_reset}")
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        elapsed = time.time() - start_ts
        status = e.response.status_code if e.response is not None else 0
        print(f"[call_local] HTTP ERROR | status={status} elapsed={elapsed:.1f}s body={e.response.text[:500]}")
        # 429/503 可重试
        if status in (429, 503):
            raise _RetryableError(f"HTTP {status}, 可重试") from e
        raise
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_ts
        print(f"[call_local] TIMEOUT | elapsed={elapsed:.1f}s (>{180}s)")
        raise _RetryableError("请求超时, 可重试")
    except Exception as e:
        elapsed = time.time() - start_ts
        import traceback
        print(f"[call_local] ERROR | elapsed={elapsed:.1f}s exception={type(e).__name__}: {e}")
        traceback.print_exc()
        raise

    try:
        result = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"SiliconFlow 响应格式异常: {e} | 原始响应: {resp.text[:300]}")

    if not result:
        # 空响应，标记为可重试
        return None, resp, elapsed

    return result, resp, elapsed


class _RetryableError(Exception):
    """可重试的异常标记。"""
    pass


def call_local(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    """调用 SiliconFlow API 生成报告（原 Ollama 接口，已迁移至 SiliconFlow）。

    支持自动重试：空响应、429/503、超时时自动重试最多 _CALL_LOCAL_MAX_RETRIES 次。
    """
    if not _sf_key():
        raise ValueError("SILICONFLOW_API_KEY 未设置")

    prompt_tokens = _estimate_tokens(prompt)
    system_tokens = _estimate_tokens(system or MACRO_SYSTEM_PROMPT)
    total_tokens = prompt_tokens + system_tokens
    print(f"[call_local] START | prompt_tokens≈{prompt_tokens} system_tokens≈{system_tokens} total≈{total_tokens} max_tokens={max_tokens}")

    last_error = None
    for attempt in range(1, _CALL_LOCAL_MAX_RETRIES + 2):  # 1次原始 + N次重试
        if attempt > 1:
            delay = _CALL_LOCAL_RETRY_DELAY * (attempt - 1)
            print(f"[call_local] RETRY #{attempt-1}/{_CALL_LOCAL_MAX_RETRIES} | 等待 {delay}s...")
            time.sleep(delay)

        try:
            result, resp, elapsed = _do_siliconflow_request(prompt, system, max_tokens)
            if result is None:
                # 空响应
                print(f"[call_local] 空响应 | attempt={attempt} elapsed={elapsed:.1f}s")
                last_error = ValueError(f"SiliconFlow 返回空响应（模型={SILICONFLOW_MODEL}）")
                continue  # 重试
            print(f"[call_local] OK | result_chars={len(result)} elapsed={elapsed:.1f}s attempt={attempt}")
            try:
                _u = (resp.json() or {}).get("usage") or {}
                _log_token_usage(
                    usage_id=None, platform="siliconflow", model=SILICONFLOW_MODEL,
                    prompt_tokens=_u.get("prompt_tokens"), completion_tokens=_u.get("completion_tokens"),
                    total_tokens=_u.get("total_tokens"),
                    call_ms=int(elapsed * 1000), ok=True,
                )
            except Exception:
                pass
            return result
        except _RetryableError as e:
            print(f"[call_local] 可重试错误 | attempt={attempt} error={e}")
            last_error = e
            continue  # 重试
        except Exception:
            raise  # 不可重试错误，直接抛出

    # 所有重试耗尽
    if last_error:
        raise last_error
    raise ValueError(f"SiliconFlow 返回空响应（模型={SILICONFLOW_MODEL}，重试{_CALL_LOCAL_MAX_RETRIES}次后仍失败）")


def call_openai_compat(prompt: str, system: str = "", max_tokens: int = 4096,
                       model: str | None = None, usage: str | None = None) -> str:
    """用 OpenAI 兼容端点调用 LLM（如 MiMo），无需 openai 包，直接用 requests。
    优先级：usage 配置（llm_usage resolve：base_url/api_key/model 全配置化）→
    显式 model 参数 → env OPENAI_COMPAT_MODEL。08-16：接入 llm_usage 统一配置。"""
    resolved = resolve(usage) if usage else None
    base_url = (resolved or {}).get("base_url") or os.environ.get("OPENAI_COMPAT_URL", "").rstrip("/")
    # 08-23：平台→env key 映射（翻译切硅基流动后 config 不配 key 时按 platform 取对应 env，
    # 防止拿 OPENAI_COMPAT_KEY(mimo) 调 SiliconFlow 的跨平台 401）
    _plat_env_key = _PLATFORM_ENV_KEYS.get((resolved or {}).get("platform") or "", "")
    api_key  = ((resolved or {}).get("api_key")
                or (get_secret(_plat_env_key) if _plat_env_key else None)
                or get_secret("OPENAI_COMPAT_KEY") or ANTHROPIC_API_KEY)
    model    = (model
                or (resolved or {}).get("model")
                or llm_usage_get_model(usage or "openai_compat")
                or os.environ.get("CLAUDE_MODEL", "gpt-4o"))
    if not base_url:
        raise ValueError("未设置 OPENAI_COMPAT_URL")
    if not api_key:
        raise ValueError("未设置 OPENAI_COMPAT_KEY 或 ANTHROPIC_API_KEY")

    if _estimate_tokens(prompt) > 150_000:
        prompt = prompt[:400_000] + "\n\n[输入过长，已截断]"

    print(f"[call_openai_compat] START | prompt_tokens={_estimate_tokens(prompt)} max_tokens={max_tokens} url={base_url}")
    start_ts = time.time()
    # 08-18 修复：mimo 端点间歇 20-30% "200 + 空 body"（fetch_news_titles 30% 标题
    # 翻译失败保留英文的根因）——空响应/请求异常（429/5xx）重试 2 次（指数退避 2s/4s）。
    # 格式异常（KeyError/IndexError）不重试（端点格式错，重试无意义，快速失败）。
    for _attempt in range(3):
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system or MACRO_SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                },
                timeout=180,
            )
            elapsed = time.time() - start_ts
            rl_remain = resp.headers.get("X-RateLimit-Remaining", "N/A")
            rl_reset  = resp.headers.get("X-RateLimit-Reset", "N/A")
            print(f"[call_openai_compat] RESPONSE | status={resp.status_code} elapsed={elapsed:.1f}s rateLimit_remain={rl_remain}")
            resp.raise_for_status()
            try:
                result = resp.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                raise ValueError(f"OpenAI兼容端点响应格式异常: {e} | 原始响应: {resp.text[:300]}")
            if not result:
                raise ValueError("OpenAI兼容端点返回空响应")
            print(f"[call_openai_compat] OK | result_chars={len(result)} elapsed={time.time()-start_ts:.1f}s")
            try:
                _u = (resp.json() or {}).get("usage") or {}
                _log_token_usage(
                    usage_id=usage, platform=(resolved or {}).get("platform"), model=model,
                    prompt_tokens=_u.get("prompt_tokens"), completion_tokens=_u.get("completion_tokens"),
                    total_tokens=_u.get("total_tokens"),
                    call_ms=int((time.time() - start_ts) * 1000), ok=True,
                )
            except Exception:
                pass
            return result
        except ValueError as e:
            if "空响应" in str(e) and _attempt < 2:
                _backoff = 2 * (_attempt + 1)
                print(f"[call_openai_compat] 空响应重试 {_attempt+1}/2（{_backoff}s）")
                time.sleep(_backoff)
                continue
            raise
        except requests.RequestException as e:
            if _attempt < 2:
                _backoff = 2 * (_attempt + 1)
                print(f"[call_openai_compat] 请求异常重试 {_attempt+1}/2（{_backoff}s）: {str(e)[:60]}")
                time.sleep(_backoff)
                continue
            raise


def call_claude(prompt: str, system: str = "", max_tokens: int = 4096) -> str:
    """调用 Anthropic Claude API（需 ANTHROPIC_API_KEY 和 anthropic 包）。"""
    if not ANTHROPIC_API_KEY:
        raise ValueError("未设置 ANTHROPIC_API_KEY")

    try:
        import anthropic
    except ImportError:
        raise ImportError("请先安装: pip install anthropic")

    # 超长输入保护：超过 150K token 截断
    if _estimate_tokens(prompt) > 150_000:
        prompt = prompt[:400_000] + "\n\n[输入过长，已截断]"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system or MACRO_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# CON-3: auto 模式降级链总超时上限（秒）；防止降级链阻塞主线程
# 2026-08-24 恢复：46764e85a 删 MiniMax 批次误删本常量定义，致 reason("auto") NameError
_AUTO_TOTAL_TIMEOUT = int(os.environ.get("LLM_AUTO_TIMEOUT", "300"))
_CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

def reason(prompt: str, system: str = "", mode: str = "auto",
           max_tokens: int = 3000) -> str:
    """
    统一推理入口。

    mode:
      "local"      → SiliconFlow（Qwen3.5-27B）
      "claude"     → 强制 Claude API（需 ANTHROPIC_API_KEY）
      "claudecode" → 通过文件与 Claude Code CLI 交互
      "openai"     → OpenAI 兼容端点（MiMo）
      "auto"       → MiniMax-M3 → MiMo v2.5 → SiliconFlow DeepSeek-V4-Flash（总超时 _AUTO_TOTAL_TIMEOUT s）
    """
    # 思维链模型 reasoning 消耗大量 token，强制最小值保护
    max_tokens = max(max_tokens, 8192)

    if mode == "claudecode":
        return call_claudecode(prompt, system)
    if mode == "local":
        return call_local(prompt, system, max_tokens)
    if mode == "claude":
        return call_claude(prompt, system, max_tokens)
    if mode == "openai":
        return call_openai_compat(prompt, system, max_tokens)
    # auto：MiMo v2.5 → SiliconFlow DeepSeek-V4-Flash
    # CON-3: 用 ThreadPoolExecutor 限制整个 auto 降级链的总等待时间
    # 注意：不使用 `with` 语句，避免 __exit__ 调用 shutdown(wait=True) 使超时失效
    def _auto_chain():
        # 08-23：链首为 MiMo（原首选平台已退役）；失败降 SiliconFlow
        if os.environ.get("OPENAI_COMPAT_URL"):
            try:
                return call_openai_compat(prompt, system, max_tokens)
            except Exception as e:
                print(f"[hybrid_llm] MiMo 失败，降级 SiliconFlow: {e}")
        return call_local(prompt, system, max_tokens)

    _ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    _future = _ex.submit(_auto_chain)
    try:
        return _future.result(timeout=_AUTO_TOTAL_TIMEOUT)
    except concurrent.futures.TimeoutError:
        _ex.shutdown(wait=False, cancel_futures=True)  # 不阻塞等待，让后台线程自然结束
        print(f"[hybrid_llm] auto 降级链超过总超时 {_AUTO_TOTAL_TIMEOUT}s，返回纯数据占位")
        return f"[LLM超时] 降级链总耗时超过 {_AUTO_TOTAL_TIMEOUT}s\n\n原始数据（节选）：{prompt[:1000]}"
    except Exception as e:
        _ex.shutdown(wait=False, cancel_futures=True)
        print(f"[hybrid_llm] 所有LLM均失败，返回纯数据占位: {e}")
        return f"[LLM不可用] {e}\n\n原始数据（节选）：{prompt[:1000]}"
