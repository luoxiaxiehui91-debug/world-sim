#!/usr/bin/env python3
"""
llm_judge.py — L3 行为类预测 LLM 判定器（08-23，天玑验证域）

定位：L1(FRED 判定器)→L2(关键词单向确认) 都返回 None 时，用行为判定标准 +
到期窗口内新闻标题喂 LLM（DeepSeek-V4-Flash）做三值判定（1 发生 / 0.5 部分 /
0 未发生 / null 证据不足）。

防污染（保护 Brier/BSS 校准）：
  - 自动落库门槛：outcome=1 需 confidence>=0.70；
    outcome=0 需 confidence>=0.85 且窗口文章总数>=200（「没搜到≠没发生」防线）
  - 不满足门槛 → 仅写 llm_outcome/llm_confidence/llm_note 建议字段，status 保持
    awaiting_human 由人工复核（开阳面板显示建议+证据加速）
  - 自动落库一律 verified_by="auto_llm"（与 auto/human 来源隔离，
    出现系统性误判可一条 SQL 全量回滚）

依赖：SILICONFLOW_API_KEY env（macro-ji/.env）；tianji_db.get_connection()；
predictions 表需含列 llm_outcome/llm_confidence/llm_note。
"""
import json
import os
import re
import urllib.request

MODEL = os.environ.get("VERIFY_LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
SF_URL = "https://api.siliconflow.cn/v1/chat/completions"

# 行为判定标准（与 macro-sim/core/bifurcation.py _ACTION_CRITERIA 同源；跨容器复制）
ACTION_CRITERIA = {
    "A2:TIGHTEN_CREDIT": "商业银行收紧信贷",
    "A2:EASE_CREDIT": "商业银行放松信贷",
    "A3:SHORT_MARKET": "对冲基金大规模做空",
    "A3:DECREASE_RISK": "对冲基金降险",
    "A3:INCREASE_RISK": "对冲基金加仓做多",
    "A4:CUT_OUTPUT": "OPEC+减产",
    "A4:CUT_SUPPLY": "OPEC+减产",
    "A5:DECREASE_RISK": "机构投资者降险",
    "A5:INCREASE_RISK": "机构投资者加仓",
    "A6:AMPLIFY_FEAR": "媒体放大恐慌情绪",
    "A6:NEUTRAL_REPORT": "媒体保持中性报道",
    "A6:AMPLIFY_OPTIMISM": "媒体放大乐观情绪",
    "A7:CAPITAL_CONTROLS": "新兴市场实施资本管制",
    "A10:PANIC_SELL": "散户恐慌性抛售",
    "A10:FOMO_BUY": "散户追涨买入",
    "A11:CUT_25BP": "欧央行降息25bp",
    "A12:ABANDON_YCC": "日本央行放弃YCC（套息危机）",
    "A13:INCREASE_RISK": "长线资金逆向抄底",
    "A13:DECREASE_RISK": "长线资金温和降险",
}

# 新闻标题预筛检索词（ILIKE 匹配）
KEYWORD_HINTS = {
    "A6:AMPLIFY_FEAR": ["恐慌", "崩盘", "暴跌", "危机", "抛售", "悲观"],
    "A10:PANIC_SELL": ["散户", "抛售", "卖出", "赎回", "流出", "清仓"],
    "A10:FOMO_BUY": ["散户", "追涨", "涌入", "买入", "开户"],
    "A2:EASE_CREDIT": ["降准", "降息", "宽松", "信贷", "放贷", "流动性"],
    "A2:TIGHTEN_CREDIT": ["收紧", "加息", "信贷紧缩", "提高利率", "缩表"],
    "A3:INCREASE_RISK": ["对冲基金", "加仓", "做多", "风险资产", "杠杆"],
    "A3:SHORT_MARKET": ["做空", "空头", "对冲基金", "沽空"],
    "A3:DECREASE_RISK": ["对冲基金", "降险", "减仓", "去杠杆"],
    "A4:CUT_OUTPUT": ["减产", "削减产出", "OPEC", "停产"],
    "A12:ABANDON_YCC": ["日本央行", "YCC", "收益率曲线", "货币政策", "日元"],
}


def fetch_window_news(due_at, keywords, limit=40):
    """查 [due_at-90d, due_at+30d] 窗口内命中检索词的新闻标题。"""
    from tianji_db import get_connection

    conds = " OR ".join(["title ILIKE %s"] * len(keywords))
    sql = (
        "SELECT title, source, published_at FROM news.articles "
        "WHERE published_at BETWEEN (%s)::timestamptz - interval '90 days' "
        "AND (%s)::timestamptz + interval '30 days' AND (" + conds + ") "
        "ORDER BY published_at DESC LIMIT %s"
    )
    params = [due_at, due_at] + ["%" + k + "%" for k in keywords] + [limit]
    conn = get_connection()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _call_llm(prompt):
    req = urllib.request.Request(
        SF_URL,
        data=json.dumps({
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.1,
        }).encode(),
        headers={"Authorization": "Bearer " + os.environ["SILICONFLOW_API_KEY"],
                 "Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=90).read())
    return r["choices"][0]["message"]["content"]


def judge_prediction(pred):
    """单条判定。返回 dict 或 None（无标准/零候选/解析失败——均留人工）。"""
    ak = pred.get("action_key") or ""
    criteria = ACTION_CRITERIA.get(ak)
    if not criteria:
        return None
    hints = KEYWORD_HINTS.get(ak) or [criteria]
    arts = fetch_window_news(pred.get("due_at"), hints)
    window_total = len(arts)
    if window_total == 0:
        return None
    titles = "\n".join(
        str(i) + ". [" + str(a.get("published_at", ""))[:10] + "|" + str(a.get("source", "")) + "] "
        + str(a.get("title", ""))
        for i, a in enumerate(arts, 1))
    prompt = (
        "你是宏观预测验证员。判断以下预测在时间窗内是否于现实发生。\n"
        "【动作】" + ak + "｜判定标准：" + criteria + "\n"
        "【预测内容】" + (pred.get("content") or "(无描述)") + "\n"
        "【到期时间】" + str(pred.get("due_at")) + "\n"
        "【窗内命中新闻】（共 " + str(window_total) + " 条命中检索词）\n" + titles +
        "\n规则：\n"
        "- 只有新闻明确表明判定标准所述行为已发生才输出 1；\n"
        "- 明确证据显示未发生/被证伪才输出 0（要求窗口新闻总量>=200 篇证明覆盖充分）；\n"
        "- 部分/间接证据输出 0.5；证据不足输出 null。\n"
        '只输出 JSON：{"outcome": 1, "confidence": 0.9, "evidence": ["标题"], "reason": "一句话"}'
    )
    raw = _call_llm(prompt)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        out = json.loads(m.group(0))
    except Exception:
        return None
    outcome = out.get("outcome")
    conf = float(out.get("confidence") or 0)
    if outcome not in (0, 0.5, 1, None):
        return None
    suggestion_only = True
    if outcome == 1 and conf >= 0.70:
        suggestion_only = False
    elif outcome == 0 and conf >= 0.85 and window_total >= 200:
        suggestion_only = False
    return {"outcome": outcome, "confidence": round(conf, 2),
            "evidence": out.get("evidence") or [], "reason": out.get("reason") or "",
            "suggestion_only": suggestion_only, "window_count": window_total}


def run_expired_judgments(dry_run=False):
    """扫描已到期且无 L3 结果的 awaiting_human 行为类预测并判定。"""
    from tianji_db import get_connection

    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, action_key, content, due_at, final_prob FROM predictions "
            "WHERE status='awaiting_human' AND action_key IS NOT NULL "
            "AND due_at IS NOT NULL AND due_at <= NOW() AND llm_outcome IS NULL")
        rows = cur.fetchall()
    finally:
        conn.close()
    stat = {"total": len(rows), "auto": 0, "suggested": 0, "skipped": 0}
    for pred in rows:
        try:
            r = judge_prediction(pred)
        except Exception as e:
            print("[llm_judge] " + str(pred["id"]) + " 异常: " + str(e)[:120])
            stat["skipped"] += 1
            continue
        if r is None:
            stat["skipped"] += 1
            continue
        if dry_run:
            print("[llm_judge][DRY] " + str(pred["id"]) + " " + str(pred["action_key"])
                  + " → " + str(r["outcome"]) + " conf=" + str(r["confidence"]))
            continue
        conn = get_connection()
        try:
            if not r["suggestion_only"]:
                from tianji_db import update_prediction_verified
                update_prediction_verified(
                    prediction_id=pred["id"], outcome_value=r["outcome"],
                    brier_score=round((pred.get("final_prob", 0.5) - r["outcome"]) ** 2, 4),
                    verified_by="auto_llm",
                    human_note="【自动-L3】conf=" + str(r["confidence"]) + " " + r["reason"][:200],
                )
                stat["auto"] += 1
            else:
                note = ("LLM建议=" + str(r["outcome"]) + " conf=" + str(r["confidence"])
                        + " " + r["reason"][:150] + "｜证据:" + "; ".join(r["evidence"][:3]))[:500]
                conn.execute(
                    "UPDATE predictions SET llm_outcome=%s, llm_confidence=%s, llm_note=%s WHERE id=%s",
                    (r["outcome"], r["confidence"], note, pred["id"]))
                conn.commit()
                stat["suggested"] += 1
        finally:
            conn.close()
    return stat


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run_expired_judgments(dry_run=args.dry_run), ensure_ascii=False))
