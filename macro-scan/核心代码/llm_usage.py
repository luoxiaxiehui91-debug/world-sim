#!/usr/bin/env python3
"""
llm_usage.py — LLM 使用点统一登记 + 运行时配置（08-16，开阳控制台统一修改模型）

背景：系统多处调用 LLM（MiMo / Claude / SiliconFlow / MiniMax），模型散落在环境变量
与代码常量里。此模块提供：
  1. LLM_USAGES 静态清单（每个使用点的 id/名称/用途/默认平台/默认模型）
  2. PLATFORMS 内置平台清单（id/名称/默认 base_url/预置模型列表）
  3. llm_config.json 运行时配置（data 目录，天枢/天璇共享；配置优先于默认）
  4. resolve(usage_id) —— 调用方按使用点解析 (base_url, api_key, model)
  5. get_model / set_usage —— 控制 API 读写

配置文件契约（data/llm_config.json，v2.0，原子写）：
  {
    "schema_version": "2.0",
    "updated": "ISO",
    "platforms": {                        # 用户自定义平台（可选；内置平台见 PLATFORMS）
      "custom1": {"name": "公司内网", "base_url": "https://.../v1", "models": ["m1", "m2"]}
    },
    "usages": {                           # 使用点覆盖（只存被修改过的）
      "translate_titles": {"platform": "mimo", "model": "mimo-v2.5", "api_key": "sk-..."}
    }
  }

接入方式：
  from llm_usage import resolve, get_model
  cfg = resolve("translate_titles")   # dict(base_url, api_key, model) 或 None
  model = get_model("translate_titles") or TRANSLATE_MODEL
"""

import datetime
import json
import os

# data 根（天枢运行时数据目录；天璇挂载为 /app/macro_data）
DATA_DIR = os.environ.get(
    "WORLDSIM_DATA_DIR",
    "/vol2/1000/software/macro-scan/data"
    if os.path.isdir("/vol2/1000/software/macro-scan/data")
    else "/workspace/data",
)
CONFIG_PATH = os.path.join(DATA_DIR, "llm_config.json")


# ── 内置平台清单 ────────────────────────────────────────────────────
# id → {name, base_url, models[预置模型，供前端下拉], default_model}
PLATFORMS = {
    "mimo": {
        "name": "小米 MiMo",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "models": ["mimo-v2.5"],
        "default_model": "mimo-v2.5",
    },
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["THUDM/GLM-Z1-9B-0414", "Qwen/Qwen3-8B", "deepseek-ai/DeepSeek-V4-Flash", "tencent/Hunyuan-MT-7B"],
        "default_model": "THUDM/GLM-Z1-9B-0414",
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
        "default_model": "gpt-4o",
    },
}


# ── LLM 使用点静态清单 ────────────────────────────────────────────
# platform: 默认平台 id；default_model: None = 跟随平台默认/环境变量
LLM_USAGES = [
    {
        "id": "translate_titles",
        "name": "新闻标题翻译",
        "purpose": "fetch_news_titles.py 标题英→中（LLM 逐条并发 4）",
        "platform": "mimo",
        "default_model": "mimo-v2.5",
        "container": "tianshu",
        "adjustable": True,
    },
    {
        "id": "openai_compat",
        "name": "通用 OpenAI 兼容",
        "purpose": "hybrid_llm.call_openai_compat 无显式 usage 的调用（含 run_macro_analysis 宏观分析）",
        "platform": "mimo",
        "default_model": None,  # 跟随环境变量 OPENAI_COMPAT_MODEL
        "container": "tianshu",
        "adjustable": True,
    },
    {
        "id": "rag_embedding",
        "name": "知识库嵌入",
        "purpose": "RAG 向量检索（rag_engine 入库 + 查询；bge-m3，SiliconFlow /v1/embeddings）",
        "platform": "siliconflow",
        "default_model": "BAAI/bge-m3",
        "container": "tianshu",
        "adjustable": True,
    },
    {
        "id": "verify_llm",
        "name": "天玑行为判定器",
        "purpose": "L3 行为类预测自动验证（_ACTION_CRITERIA+新闻标题→三值判定，macro-ji llm_judge.py）",
        "platform": "siliconflow",
        "default_model": "deepseek-ai/DeepSeek-V4-Flash",
        "container": "tianji",
        "adjustable": True,
    },
    {
        "id": "chronicle",
        "name": "天璇编年史生成",
        "purpose": "仿真 history JSONL → 编年史读物分章生成（core/chronicler.py，长文 max_tokens 4000+）",
        "platform": "siliconflow",
        "default_model": "deepseek-ai/DeepSeek-V4-Flash",
        "container": "tianxuan",
        "adjustable": True,
    },
    {
        "id": "sim_mc",
        "name": "天璇 Monte Carlo",
        "purpose": "macro-sim llm_client SILICONFLOW_MODEL（MC 默认 GLM-Z1-9B）",
        "platform": "siliconflow",
        "default_model": "THUDM/GLM-Z1-9B-0414",
        "container": "tianxuan",
        "adjustable": True,
    },
    {
        "id": "sim_narrative",
        "name": "天璇 叙事合成",
        "purpose": "macro-sim llm_client QWEN_LARGE（叙事用更强模型）",
        "platform": "siliconflow",
        "default_model": "deepseek-ai/DeepSeek-V4-Flash",
        "container": "tianxuan",
        "adjustable": True,
    },
]
_USAGE_IDS = {u["id"] for u in LLM_USAGES}


# ── 配置读写 ───────────────────────────────────────────────────────

def load_config() -> dict:
    """读 llm_config.json；不存在/损坏 → 空配置（全部走默认）。"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict) and isinstance(cfg.get("usages"), dict):
            return cfg
    except Exception:
        pass
    return {"schema_version": "2.0", "platforms": {}, "usages": {}}


def save_config(cfg: dict) -> bool:
    """原子写 llm_config.json。返回是否成功。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        cfg["schema_version"] = "2.0"
        cfg["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
        return True
    except Exception as e:
        print(f"[llm_usage] 写配置失败: {e}")
        return False


def _all_platforms() -> dict:
    """内置平台 + 用户自定义平台合并。"""
    cfg = load_config()
    p = dict(PLATFORMS)
    p.update(cfg.get("platforms") or {})
    return p


def get_platform(pid: str) -> dict | None:
    return _all_platforms().get(pid)


def get_model(usage_id: str) -> str | None:
    """返回某使用点在配置里覆盖的模型；未配置返回 None（调用方走默认）。"""
    if usage_id not in _USAGE_IDS:
        return None
    try:
        return load_config().get("usages", {}).get(usage_id, {}).get("model") or None
    except Exception:
        return None


def _static_default_platform(usage_id: str) -> str | None:
    """LLM_USAGES 静态清单里的默认平台（08-17 修复 LLM①：静态默认此前形同虚设，
    仅 effective_models 展示用，resolve 返 None 导致调用方回落 env）。"""
    for item in LLM_USAGES:
        if item.get("id") == usage_id:
            return item.get("platform")
    return None


def resolve(usage_id: str) -> dict | None:
    """按使用点解析完整调用配置 {base_url, api_key, model}。
    配置覆盖（平台 + 模型 + key）> 使用点静态默认平台 + 平台默认模型（08-17 补上，
    原逻辑未配置即返 None → 调用方回落 env，静态默认失效）。
    未配置 api_key 时返回 None（调用方 fallback env）。"""
    if usage_id not in _USAGE_IDS:
        return None
    try:
        u = load_config().get("usages", {}).get(usage_id) or {}
        pid = u.get("platform") or _static_default_platform(usage_id)
        plat = _all_platforms().get(pid) if pid else None
        if not plat:
            return None
        base_url = (plat.get("base_url") or "").rstrip("/")
        if not base_url:
            return None
        model = u.get("model") or plat.get("default_model")
        return {
            "base_url": base_url,
            "api_key": u.get("api_key") or None,
            "model": model,
            "platform": pid,
        }
    except Exception:
        return None


def resolve_embedding(usage_id: str = "rag_embedding") -> dict | None:
    """嵌入模型专用解析：返回 {embed_url, api_key, model}——embed_url = base_url
    + '/embeddings'（OpenAI 兼容端点，chat 与 embeddings 路径不同）。"""
    cfg = resolve(usage_id)
    if not cfg:
        return None
    return {
        "embed_url": f"{cfg['base_url']}/embeddings",
        "api_key": cfg.get("api_key"),
        "model": cfg.get("model"),
    }


def set_usage(usage_id: str, platform: str, model: str,
              api_key: str | None = None) -> tuple[bool, str]:
    """控制台修改使用点（平台 + 模型 + 可选 key）。platform 必须在清单内。
    落盘时附带 base_url 展开值——天璇等跨容器消费者无需平台清单即可解析。"""
    if usage_id not in _USAGE_IDS:
        return False, f"未知使用点: {usage_id}"
    platform = (platform or "").strip()
    model = (model or "").strip()
    if not platform:
        return False, "平台不能为空"
    if not model:
        return False, "模型名不能为空"
    plat = _all_platforms().get(platform)
    if not plat:
        return False, f"未知平台: {platform}"
    cfg = load_config()
    cfg.setdefault("usages", {})
    # 08-18 修复：首次写预填充——文件缺失/损坏时 usages 为空，若只写当前 1 条会
    # 生成"部分固化"配置（其余 5 个使用点不在文件里，面板看不出异常）。用静态清单
    # 预填全部使用点（key 留空走 env），保证任何时刻文件都是完整 6 条。
    if not cfg["usages"]:
        for _item in LLM_USAGES:
            _uid = _item["id"]
            _pid = _item.get("platform") or ""
            _plat = _all_platforms().get(_pid)
            _model = _item.get("default_model") or ""
            if not _plat or not _model:
                continue  # openai_compat default_model=None → 跳过，由调用方显式设置
            cfg["usages"][_uid] = {
                "platform": _pid,
                "model": _model,
                "base_url": (_plat.get("base_url") or "").rstrip("/"),
            }
    entry = dict(cfg["usages"].get(usage_id) or {})
    entry["platform"] = platform
    entry["model"] = model
    entry["base_url"] = (plat.get("base_url") or "").rstrip("/")
    # api_key：显式传非空 → 更新；传 None → 保留原值（前端不发回显，避免覆盖）
    if api_key is not None:
        entry["api_key"] = api_key.strip() or None
    cfg["usages"][usage_id] = entry
    if save_config(cfg):
        return True, "ok"
    return False, "写配置失败"


def _mask_key(k: str | None) -> str | None:
    if not k:
        return None
    if len(k) <= 8:
        return "***"
    return f"{k[:4]}***{k[-4:]}"


def effective_models() -> list[dict]:
    """清单 + 当前生效配置（给控制 API / 开阳展示；key 脱敏）。"""
    cfg = load_config().get("usages", {})
    platforms = _all_platforms()
    out = []
    for u in LLM_USAGES:
        override = cfg.get(u["id"]) or {}
        pid = override.get("platform") or u["platform"]
        plat = platforms.get(pid) or {}
        default_model = (u["default_model"]
                         or plat.get("default_model")
                         or "（env 默认）")
        model = override.get("model") or default_model
        out.append({
            **u,
            "platform": pid,
            "platform_name": plat.get("name") or pid,
            "base_url": plat.get("base_url") or "",
            "model": model,
            "default_model": default_model,
            "api_key_masked": _mask_key(override.get("api_key")),
            "overridden": bool(override.get("platform") or override.get("model")),
        })
    return out


_PLAT_MODELS_CACHE: dict = {}      # pid -> (ts, [model_id])
_PLAT_MODELS_TTL = 3600.0          # 1h：模型清单变化低频，避免面板每次开都外呼

def fetch_platform_models(platform_id: str) -> list[str]:
    """实时拉取平台可用模型全集（OpenAI 兼容 /models 端点，1h 内存缓存）。
    供开阳控制台下拉动内置；失败抛异常，调用方应回落静态 models 清单。
    返回已按 id 排序、剔除明显非对话类（tts/asr/voice）。"""
    import json as _json
    import os as _os
    import time as _time
    import re as _re
    import urllib.request as _urllib_request

    now = _time.time()
    hit = _PLAT_MODELS_CACHE.get(platform_id)
    if hit and now - hit[0] < _PLAT_MODELS_TTL:
        return hit[1]
    plat = _all_platforms().get(platform_id)
    if not plat:
        raise ValueError(f"未知平台: {platform_id}")
    env_name = {"siliconflow": "SILICONFLOW_API_KEY", "mimo": "OPENAI_COMPAT_KEY",
                "openai": "OPENAI_API_KEY"}.get(platform_id, "")
    key = _os.environ.get(env_name, "")
    if not key:
        raise ValueError(f"平台 {platform_id} 未配置 API key（env {env_name}）")
    base = (plat.get("base_url") or "").rstrip("/")
    req = _urllib_request.Request(
        base + "/models", headers={"Authorization": "Bearer " + key})
    r = _json.loads(_urllib_request.urlopen(req, timeout=20).read())
    models = sorted(m.get("id") or "" for m in r.get("data", []) if m.get("id"))
    models = [m for m in models if not _re.search(r"(tts|asr|voice)", m, _re.I)]
    _PLAT_MODELS_CACHE[platform_id] = (now, models)
    return models


def platform_options() -> list[dict]:
    """平台选项清单（开阳下拉；内置 + 自定义）。"""
    return [
        {"id": pid, "name": p.get("name") or pid,
         "base_url": p.get("base_url") or "", "models": p.get("models") or [],
         "default_model": p.get("default_model") or ""}
        for pid, p in _all_platforms().items()
    ]


if __name__ == "__main__":
    print("=== 平台 ===")
    for p in platform_options():
        print(" ", p["id"], "|", p["name"], "|", p["base_url"])
    print("=== 使用点 ===")
    for u in effective_models():
        flag = " [已覆盖]" if u["overridden"] else ""
        key = f" | key={u['api_key_masked']}" if u["api_key_masked"] else ""
        print(f"  {u['id']:<18} {u['platform']:<12} {u['model']}{flag}{key}")
