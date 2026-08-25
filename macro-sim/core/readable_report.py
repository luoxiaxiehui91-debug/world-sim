#!/usr/bin/env python3
"""
readable_report.py — 天璇推演「人话版」报告生成器（2026-08-24）

替代编年史形态（用户拍板废弃）。三层结构：一句话结论 / 你可能想问(Q&A) / 按季度看，
文末附原始参数表（本地拼接，不耗 LLM token）。

与编年史的关键差异（吸取 08-23 烧 400 万 token 教训）：
  - 单次调用出全篇（不分卷串行）；max_tokens 收紧 2000
  - 喂给 LLM 前本地先把黑话翻译成人话（AGENT_NAMES/ACTION_ZH/DIM_ZH），输出自然零代号
  - prompt 显式禁止残留代号；LLM 失败降级为词典机械替换模板（永远有产出）

用法：
  python3 readable_report.py --replay <sim_history.jsonl> --event "事件名" \
      --label 路径A [--out /app/reports/xxx.md]
模型解析：llm_config.json usages.readable（控制台可切），缺省 DeepSeek-V4-Flash。
"""
import json
import re
from pathlib import Path

# ── 黑话词典（权威来源 config/agents.yaml id/name 对 + 动作/维度枚举） ──────────
AGENT_NAMES = {
    "A1": "美联储", "A2": "商业银行", "A3": "对冲基金", "A5": "机构投资者",
    "A6": "媒体/舆论", "A7": "新兴市场央行", "A8": "中国央行/财政", "A9": "美国财政部",
    "A10": "散户", "A11": "欧洲央行", "A12": "日本央行", "A13": "保险/养老长线资金",
    "S1_usa": "美国", "S2_china": "中国", "S3_eu": "欧盟", "S4_russia": "俄罗斯",
    "S5_saudi": "沙特-OPEC", "S6_japan": "日本", "S7_korea": "韩国",
}
ACTION_ZH = {
    "HOLD": "按兵不动", "CUT_50BP": "大幅降息0.5个百分点", "CUT_25BP": "降息0.25个百分点",
    "HIKE_25BP": "加息0.25个百分点", "TIGHTEN_CREDIT": "收紧贷款标准",
    "INCREASE_RISK": "加仓风险资产", "DECREASE_RISK": "减仓转向避险",
    "SHORT_MARKET": "做空市场", "AMPLIFY_FEAR": "渲染恐慌情绪",
    "AMPLIFY_OPTIMISM": "鼓吹乐观情绪", "PANIC_SELL": "恐慌性抛售",
    "FOMO_BUY": "害怕踏空追涨买入", "ABANDON_YCC": "放弃收益率曲线控制",
    "DIPLOMATIC_ENGAGE": "开展外交接触", "MILITARY_DEPLOYMENT": "进行军事部署",
    "IMPOSE_SANCTIONS": "施加制裁", "ALLIANCE_REINFORCE": "强化军事同盟",
    "CUT_OUTPUT": "削减石油产量", "INCREASE_OUTPUT": "增加石油产量",
}
DIM_ZH = {
    "taiwan_strait": "台海局势", "us_china_strategic": "中美战略博弈",
    "russia_europe": "俄欧对峙", "middle_east_energy": "中东能源",
    "global_composite": "全球综合风险", "south_china_sea": "南海局势",
    "korean_peninsula": "朝鲜半岛", "india_pacific": "印太", "global_south": "全球南方",
    "climate_risk": "气候风险", "disaster_risk": "灾害风险",
    "sanctions_risk": "制裁风险", "seismic_risk": "地震风险",
    "energy_grid_risk": "能源电网风险", "japan_monetary": "日本货币政策",
    "social_stress": "社会压力", "cultural_friction": "文化摩擦",
}
DELTA_ZH = {
    "market_sentiment": "市场情绪", "bank_credit_tightening": "银行信贷收紧度",
    "liquidity_premium": "流动性溢价", "retail_panic": "散户恐慌度",
    "fund_risk_appetite": "机构风险偏好", "energy_supply_risk": "能源供应风险",
    "fed_rate_change": "政策利率变动", "yen_carry_risk": "日元套息交易风险",
    "em_capital_outflow": "新兴市场资本外流", "china_credit_impulse": "中国信贷脉冲",
    "us_fiscal_pressure": "美国财政压力",
}


def _zh_agent(aid: str) -> str:
    return AGENT_NAMES.get(aid, aid)


def _zh_action(act: str) -> str:
    return ACTION_ZH.get(act, act)


def _zh_dim(key: str) -> str:
    k = key.replace("grv_dim.", "").replace("grv_dim_", "")
    return DIM_ZH.get(k, k)


def _zh_delta(k: str) -> str:
    if k.startswith("grv_dim"):
        return _zh_dim(k)
    return DELTA_ZH.get(k, k)


def _fmt_step_human(step_i: int, snap: dict) -> str:
    """一步快照 → **已翻译成人话** 的紧凑记录（LLM 输入零代号）。"""
    month = step_i + 1
    parts = [f"【第{month}个月】全球风险指数 {snap.get('grv', '?')} 分"
             f"（满分100），市场情绪读数 {snap.get('market_sentiment', '?')}"
             f"（-1极恐慌~+1极乐观），企业借债成本比国债高 {snap.get('credit_spread', '?')} 个基点"]
    for aid, act in (snap.get("actions") or {}).items():
        parts.append(f"  {_zh_agent(aid)}选择{_zh_action(str(act))}")
    for k, v in list((snap.get("delta") or {}).items())[:6]:
        try:
            parts.append(f"  影响：{_zh_delta(str(k))}变动 {float(v):+.4g}")
        except (TypeError, ValueError):
            pass
    for ev in snap.get("_governance_events") or []:
        parts.append(f"  政权大事：{_zh_agent(ev.get('agent', ''))}发生 {ev.get('label', '') or ev.get('type', '')}")
    return "\n".join(parts)


def _resolve_readable():
    """llm_config.json usages.readable（控制台可切）；key 回落 env。缺省 V4-Flash。"""
    import os
    base, key, model = "https://api.siliconflow.cn/v1", "", "deepseek-ai/DeepSeek-V4-Flash"
    try:
        cfg = (json.load(open("/app/macro_data/llm_config.json", encoding="utf-8"))
               .get("usages", {}).get("readable", {}))
        if cfg:
            base = cfg.get("base_url") or base
            model = cfg.get("model") or model
    except Exception:
        pass
    key = key or os.environ.get("SILICONFLOW_API_KEY", "")
    if not key:
        raise ValueError("readable: 无 api_key")
    return base.rstrip("/"), key, model


def _call(base_url, api_key, model, prompt, max_tokens=2000):
    """流式调用（同 chronicler._call 思路：块间空闲即超时，出字就不算失败）。"""
    import urllib.request, time as _t
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps({"model": model,
                         "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": max_tokens, "temperature": 0.6,
                         "stream": True}).encode(),
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json",
                 "Accept": "text/event-stream"})
    last_err = None
    for _attempt in range(2):
        parts, t0 = [], _t.time()
        try:
            resp = urllib.request.urlopen(req, timeout=300)
            buf = ""
            print(f"[readable] urlopen ok t=0s", flush=True)
            while True:
                chunk = resp.read(256)
                now = _t.time()
                if now - t0 > 30 and len(parts) == 0:
                    print(f"[readable] waiting... t={now-t0:.0f}s", flush=True)
                    t0_log = now
                now2 = _t.time()
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
            full = "".join(parts)
            print(f"[readable] done t={_t.time()-t0:.0f}s chars={len(full)}", flush=True)
            if full:
                return full
            last_err = RuntimeError("流结束无内容")
        except Exception as e:
            last_err = e
            print(f"[readable] err: {e}", flush=True)
            if parts:
                return "".join(parts)
    raise last_err


def _fallback_template(hist, event):
    """LLM 失败兜底：词典机械替换拼装（保证永远有产出）。"""
    n = len(hist)
    g0, g1 = hist[0].get("grv"), hist[-1].get("grv")
    trend = "上升" if g1 > g0 else "下降"
    worst = max(range(n), key=lambda i: -(hist[i].get("market_sentiment") or 0))
    lines = [f"# {event} · 人话版（机械模板）\n",
             f"## 一句话结论\n未来{n}个月，全球风险指数从 {g0} 分{'升至' if trend == '上升' else '降至'} {g1} 分。\n",
             f"## 最紧张的时刻\n第 {worst+1} 个月市场情绪最低（读数 {hist[worst].get('market_sentiment')}），"
             f"当月主要动向：" + "；".join(
                 f"{_zh_agent(a)}{_zh_action(str(a))}" for a, x in (hist[worst].get("actions") or {}).items()) + "。\n",
             "\n> 注：AI 叙事生成失败，以上为词典机械替换的最小可用版本。"]
    return "\n".join(lines)


def generate_readable(hist, event: str, out_path: Path,
                      label: str = "", probability: float = None,
                      n_runs: int = None) -> Path | None:
    n = len(hist)
    g0, g1 = hist[0].get("grv"), hist[-1].get("grv")

    conf_line = ""
    if probability is not None:
        pct = f"{probability:.0%}"
        basis = f"（{n_runs} 次模拟）" if n_runs else ""
        conf_line = (
            f"\n## 这个预测有多可靠？\n"
            f"模型先做了 {basis.strip('（）')} 平行的数学推演，本文讲的是其中出现最多的一条世界线——"
            f"约 **{pct}** 的推演走向了与它相近的剧情，其余推演则分叉去了别的走向。"
            "请注意两点：① 它是「如果触发事件发生，风险如何演化」的条件推演，不代表事件本身会发生；"
            "② AI 叙事只写了这条主线路径，其余分叉剧情未展开（完整分布见正式报告）。\n")

    records = "\n".join(_fmt_step_human(i, s) for i, s in enumerate(hist))
    prompt = (
        "你是资深财经专栏作者。根据下面的推演模拟记录，写给普通读者看的深度短文《"
        + event + "：如果成真，世界会怎样》。这不是流水账，是一篇有观点的导读。\n\n"
        "严格按以下结构输出（markdown）：\n\n"
        "# " + event + "：如果成真，世界会怎样\n\n"
        "## 一句话结论\n（风险指数起点→终点 + 用一个比喻概括整个剧情，如『温水煮青蛙』『过山车』）\n\n"
        "## 三条主线\n（通读全部记录后，提炼出推动剧情的 2-3 条主线，每条一个小标题。"
        "每条主线写清楚：谁在推动 → 关键转折在哪个月 → 对其他方面造成了什么连锁影响 → 这条线的结局或现状。"
        "重复发生的同类事件合并叙述，只强调次数和累计效果，不要逐月罗列。）\n\n"
        "## 三个值得记住的时刻\n（挑出记录中最重要的 3 个转折月份，每个 1-2 句话讲清『那个月发生了什么、为什么它是转折』）\n\n"
        "## 如果你是旁观者\n（2-3 句：普通读者该从这个故事里记住什么、现实中对应盯住什么信号。）\n\n"
        "写作铁律：\n"
        "1. 记录已译成白话。输出中禁止出现 A1/S6_japan/HOLD/GRV 这类代号——用中文名称（散户、日本、全球风险指数）；\n"
        "2. 引用的数字必须来自记录，并用大白话解释含义；除此之外的解释、归纳、比喻是鼓励的——你要做的是分析师不是抄录员；\n"
        "3. 全文 700-1000 字。宁可精炼有洞见，不要全面但像会议纪要。\n\n"
        "【背景】触发事件：" + event + "；共 " + str(n) + " 个月模拟。\n\n【推演记录】\n" + records)

    base_url, api_key, model = _resolve_readable()
    md = None
    try:
        body = _call(base_url, api_key, model, prompt, max_tokens=2000)
        # 代号残留检查：正文出现裸 agent 代号 → 提示但不拒收（附注标记）
        leaks = re.findall(r"\b(?:A\d{1,2}|S\d_[a-z]+)\b", body)
        header_prob = f"{probability:.0%}" if probability is not None else None
        title = f"# 《{event}》人话版\n" if not body.lstrip().startswith("#") else ""
        note = ""
        if leaks:
            note = f"\n> ⚠️ 机检提示：正文仍残留 {len(leaks)} 处代号（{sorted(set(leaks))[:5]}…），请以附录对照阅读。\n"
        md = title + body.strip() + note + conf_line
    except Exception as e:
        print(f"[readable] LLM 失败，降级机械模板: {e}", flush=True)
        md = _fallback_template(hist, event)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"[readable] 已写入 {out_path}")
    return out_path


def replay_from_jsonl(jsonl_path, event, out_path, label="路径A",
                      probability=None, n_runs=None):
    hist = []
    meta_prob, meta_n = None, None
    for ln in open(jsonl_path, encoding="utf-8"):
        ln = ln.strip()
        if ln.startswith("__meta__:"):
            try:
                m = json.loads(ln[len("__meta__:"):])
                meta_prob = m.get("probability")
                meta_n = m.get("n_runs")
            except Exception:
                pass
            continue
        if ln:
            hist.append(json.loads(ln))
    if not hist:
        raise ValueError("JSONL 为空")
    return generate_readable(hist, event, Path(out_path), label=label,
                             probability=probability if probability is not None else meta_prob,
                             n_runs=n_runs or meta_n)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--event", required=True)
    ap.add_argument("--label", default="路径A")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = replay_from_jsonl(a.replay, a.event, a.out, label=a.label)
    print("done:", r)
