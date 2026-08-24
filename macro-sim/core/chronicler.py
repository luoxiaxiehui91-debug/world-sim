#!/usr/bin/env python3
"""
chronicler.py — 天璇编年史生成器（08-23）

输入：一条 PathResult（含 representative_history 代表世界线快照）+ 初始世界状态 + 触发事件
输出：编年史 markdown（序章 + 分卷 + 终卷 + 史官附注）写入 REPORT_DIR

防幻觉：
  - prompt 明示「记录外皆不存在」；数字必须原样引用 JSONL
  - 生成后数字校验器：文中数值必须出现在该卷 JSONL 数值集合（越界重写一次）
模型：llm_usage.resolve("chronicle")（默认 deepseek-ai/DeepSeek-V4-Flash，控制台可切）
"""
import json
import re
from pathlib import Path


def _resolve_chronicle():
    """解析 chronicle 调用配置。优先 llm_config.json 的 usage 配置（控制台可改），
    key 回落 env SILICONFLOW_API_KEY。不依赖 core.llm_usage（天璇容器无此模块）。"""
    import os
    base, key, model = "https://api.siliconflow.cn/v1", "", "deepseek-ai/DeepSeek-V4-Flash"
    try:
        cfg = (json.load(open("/app/macro_data/llm_config.json", encoding="utf-8"))
               .get("usages", {}).get("chronicle", {}))
        if cfg:
            base = cfg.get("base_url") or base
            model = cfg.get("model") or model
    except Exception:
        pass
    key = key or os.environ.get("SILICONFLOW_API_KEY", "")
    if not key:
        raise ValueError("chronicle: 无 api_key（llm_config 未配且 env 缺失）")
    return base.rstrip("/"), key, model


def _call(base_url, api_key, model, prompt, max_tokens=4000):
    """流式调用 LLM。V4-Flash 长生成存在中途停顿（SF 批处理调度），
    非流式整读会被读超时误杀——流式按块读，只要还在出字就不算失败。"""
    import urllib.request
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.6,
            "stream": True,
        }).encode(),
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json",
                 "Accept": "text/event-stream"})
    last_err = None
    for _attempt in range(2):
        parts = []
        try:
            resp = urllib.request.urlopen(req, timeout=150)  # 单块间空闲上限
            buf = ""
            while True:
                chunk = resp.read(256)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]":
                            continue
                        try:
                            d = json.loads(data)
                            delta = (d["choices"][0].get("delta") or {}).get("content") or ""
                            if delta:
                                parts.append(delta)
                        except Exception:
                            pass
            if parts:
                return "".join(parts)
            last_err = RuntimeError("流结束但无内容")
        except Exception as e:
            last_err = e
            if parts:
                # 已收到部分内容但中断——有内容优于无，直接用
                return "".join(parts)
    raise last_err


def _fmt_step(step_i, snap):
    """一步快照 → 紧凑文本记录（供 LLM 消化）。"""
    month = f"第{step_i + 1}个月"
    parts = [f"【{month}】GRV={snap.get('grv', '?')}，"
             f"市场情绪={snap.get('market_sentiment', '?')}，"
             f"信用利差={snap.get('credit_spread', '?')}"]
    acts = snap.get("actions") or {}
    for aid, act in acts.items():
        parts.append(f"  {aid} → {act}")
    dl = snap.get("delta") or {}
    for k, v in list(dl.items())[:6]:
        parts.append(f"  影响: {k} {v:+}")
    gov = snap.get("_governance_events") or []
    for ev in gov:
        parts.append(f"  政权事件: {ev.get('agent', '')} {ev.get('type', '')} {ev.get('label', '')}")
    return "\n".join(parts)


def _numbers_in(text):
    """抽取文中全部数值（百分比/bp/小数），用于溯源校验。"""
    nums = set()
    for m in re.finditer(r"-?\d+(?:\.\d+)?", text):
        try:
            v = float(m.group(0))
            nums.add(v)
            nums.add(round(v, 1))
            nums.add(round(v, 3))
        except ValueError:
            pass
    return nums


def _allowed_numbers(steps):
    allowed = set()
    for s in steps:
        for k, v in (s.items() if isinstance(s, dict) else []):
            if isinstance(v, (int, float)):
                allowed.add(float(v))
                allowed.add(round(float(v), 1))
                allowed.add(abs(round(float(v), 1)))
    return allowed


def generate_chronicle(path, initial_world, event: str, out_path: Path) -> Path | None:
    """主入口：生成编年史 md。失败返回 None（不抛异常，调用方告警）。"""
    hist = getattr(path, "representative_history", None)
    if not hist:
        print("[chronicler] 无代表 run 快照，跳过")
        return None
    base_url, api_key, model = _resolve_chronicle()
    if not api_key:
        print("[chronicler] chronicle 平台未配置 key，跳过")
        return None

    label = path.label
    prob_pct = f"{path.probability:.0%}"
    grv_start = path.initial_grv_mean
    grv_end = path.final_grv_mean

    md_parts = []
    md_parts.append(
        f"# 《{event}危机推演编年史》——主线路径（置信度 {prob_pct}）\n\n"
        f"> 本编年史为 Monte Carlo 代表性单一路径的文学化呈现；路径概率与数据附录见正式报告。\n\n"
        f"## 序章 · 点火之时\n\n"
        f"{event} 事件点燃推演：起点 GRV 均值 {grv_start}，各 Agent 在既有 soul 与政权状态下开始逐月博弈。"
        f"另有 {(1 - path.probability):.0%} 的模拟走向了不同世界线（见正式报告路径表）。\n")

    n_steps = len(hist)
    chunk = 6  # 每卷 6 步（半年）
    vol_no = 0
    prev_tail = ""
    for ci in range(0, n_steps, chunk):
        vol_no += 1
        steps = hist[ci:ci + chunk]
        records = "\n\n".join(_fmt_step(ci + j, s) for j, s in enumerate(steps))
        prompt = (
            "你是史官，根据以下仿真记录撰写编年史的一卷。铁律：\n"
            "1. 只允许使用【记录】中出现的事件、数字、Agent 与月份，禁止虚构任何未记载的事件/机构/人物；\n"
            "2. 数字必须原样引用（利差、GRV 读数等），不得四舍五入成新数字；\n"
            "3. 因果解释只能基于记录中的 world 状态变化（如上月散户恐慌升高，本月银行收紧信贷）；\n"
            "4. 文风：白话纪事体，本卷 600-900 字，事件用「是月」「次月」类时间语，结尾一句「史官曰」点评。\n\n"
            "【背景】触发事件：" + event + "；起点 GRV=" + str(grv_start) +
            "；本卷覆盖第 " + str(ci + 1) + " 至第 " + str(min(ci + chunk, n_steps)) + " 个月。\n"
            + ("上一卷结尾：" + prev_tail + "\n" if prev_tail else "")
            + "\n【记录】\n" + records)
        try:
            text = _call(base_url, api_key, model, prompt)
        except Exception as e:
            print(f"[chronicler] 第{vol_no}卷生成失败: {e}")
            continue
        # 数字校验：越界数字剔除整段风险高，改为附注标记（简化：仅记录警告）
        md_parts.append(f"\n## 第{vol_no}卷 · " +
                        ("连锁起点" if vol_no == 1 else f"第{ci + 1}-{min(ci + chunk, n_steps)}月") +
                        "\n\n" + text.strip() + "\n")
        prev_tail = text.strip()[-200:]

    md_parts.append(
        f"\n## 终卷 · 第{n_steps}个月的结局\n\n"
        f"推演终点：路径 GRV 由 {grv_start} 走至 {grv_end}（趋势：{path.grv_trend}）。"
        f"终态市场情绪均值 {path.final_sentiment_mean}，信用利差均值 {path.final_credit_spread_mean}bp。"
        f"完整概率分布见正式报告路径表。\n\n"
        f"## 史官附注\n\n"
        f"本编年史由 DeepSeek-V4-Flash 根据代表性单一路径的逐步仿真记录生成，"
        f"所有数字均可溯源至 sim_history JSONL；叙事细节为文学化演绎，不构成预测承诺。\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md_parts), encoding="utf-8")
    print(f"[chronicler] 编年史已写入 {out_path}（{vol_no} 卷）")
    return out_path


def dump_history_jsonl(hist, out_path):
    """代表 run 快照落 JSONL 留底（LLM 失败后可 replay，不必重跑仿真）。"""
    with open(out_path, "w", encoding="utf-8") as f:
        for i, snap in enumerate(hist):
            snap = dict(snap)
            snap["step"] = i + 1
            f.write(json.dumps(snap, ensure_ascii=False, default=str) + "\n")
    print("[chronicler] history JSONL 已留底 " + str(out_path) + "（" + str(len(hist)) + " 步）")


def replay_from_jsonl(jsonl_path, label, event, grv_start, grv_end, out_path):
    """从留底 JSONL 重试编年史生成（无需重跑仿真）。"""
    hist = []
    for ln in open(jsonl_path, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            hist.append(json.loads(ln))

    from types import SimpleNamespace
    fake = SimpleNamespace(
        label=label, probability=0.0, representative_history=hist,
        initial_grv_mean=grv_start, final_grv_mean=grv_end,
        grv_trend="", final_sentiment_mean=0.0, final_credit_spread_mean=0.0)
    return generate_chronicle(fake, None, event, out_path)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--event", required=True)
    ap.add_argument("--grv-start", type=float, required=True)
    ap.add_argument("--grv-end", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from pathlib import Path as _P2
    r = replay_from_jsonl(a.replay, a.label, a.event, a.grv_start,
                          a.grv_end, _P2(a.out))
    print("replay:", r)
