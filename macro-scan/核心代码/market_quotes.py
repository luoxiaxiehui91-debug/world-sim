#!/usr/bin/env python3
"""
market_quotes.py — 市场行情快照整合器

读取天枢已采集的数据文件，整合成 kaiyang 经济面板所需的统一快照格式。
不直接调用外部 API，只做数据整合。调度：06:30（commodity 06:26 / crypto 06:00 之后）。

输出：data/market_quotes.json
格式：
{
  "_schema_version": "1.0",
  "updated": "...",
  "indexes": [{key, name, price, change_pct, unit}],
  "crypto":  [{key, name, price, change_pct, unit}],
  "energy":  [{key, name, price, change_pct, unit}],
  "metals":  [{key, name, price, change_pct, unit}],
  "macro":   [{key, name, value, unit, date}]
}
"""
import csv
import json
import os
import datetime
from datetime import timezone

try:
    from optim_config import DATA_DIR
except ImportError:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _last_csv_value(filename: str):
    """从 fred_history 读最新值。"""
    path = os.path.join(DATA_DIR, "fred_history", filename)
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("value") and r["value"] != "."]
        if rows:
            last = rows[-1]
            return float(last["value"]), last.get("date", "")
    except Exception:
        pass
    return None, None


def build_market_quotes():
    now = datetime.datetime.now(timezone.utc).isoformat()[:19]

    # ── 商品/股市快照 ──────────────────────────────────────
    cy = _load_json(os.path.join(DATA_DIR, "commodity_yahoo.json")) or {}
    commodities = cy.get("commodities", {})

    def _spark5(key: str):
        """读 commodity_history/{key}.csv 最近5条价格，返回列表或 None。"""
        path = os.path.join(DATA_DIR, "commodity_history", f"{key}.csv")
        try:
            with open(path, newline="", encoding="utf-8") as f:
                rows = [r for r in csv.DictReader(f) if r.get("value")]
            rows = rows[-5:]
            if len(rows) < 2:
                return None
            prices = []
            for r in rows:
                try:
                    prices.append(float(r["value"]))
                except (ValueError, TypeError):
                    pass
            return prices if len(prices) >= 2 else None
        except Exception:
            return None

    def _cy(key):
        c = commodities.get(key, {})
        q = {
            "key":        key,
            "name":       c.get("name", key),
            "price":      c.get("price"),
            "change_pct": c.get("change_pct"),
            "unit":       c.get("unit", ""),
            "as_of":      c.get("as_of"),
        }
        spark = _spark5(key)
        if spark:
            q["spark5"] = spark
        return q

    indexes = [_cy(k) for k in ("sp500", "dji", "nasdaq_c", "rut") if k in commodities]
    energy  = [_cy(k) for k in ("wti", "brent", "nat_gas") if k in commodities]
    metals  = [_cy(k) for k in ("gold", "silver", "copper") if k in commodities]

    # ── 加密货币 ──────────────────────────────────────────
    cr = _load_json(os.path.join(DATA_DIR, "crypto_history", "crypto_latest.json")) or {}
    coins = cr.get("coins", [])
    crypto = []
    for c in coins:
        if c.get("symbol") in ("btc", "eth"):
            crypto.append({
                "key":        c["symbol"],
                "name":       c.get("name", c["symbol"].upper()),
                "price":      c.get("price"),
                "change_pct": c.get("price_change_24h_pct"),
                "unit":       "USD",
            })

    # ── FRED 宏观 ──────────────────────────────────────────
    macro_defs = [
        ("VIXCLS",   "VIX",          ""),
        ("DFF",      "Fed Funds",     "%"),
        ("BAA10Y",   "HY Spread",     "%"),
        ("T10Y2Y",   "10Y-2Y",        "%"),
        ("DTWEXBGS", "USD Index",     ""),
        ("M2SL",     "M2 Supply",     "B$"),
        ("ICSA",     "Jobless Claims",""),
        ("MORTGAGE30US", "30Y Mortgage", "%"),
    ]
    macro = []
    for ticker, label, unit in macro_defs:
        val, date = _last_csv_value(f"{ticker}.csv")
        if val is not None:
            # M2: 显示为万亿
            if ticker == "M2SL":
                val = round(val / 1000, 1)
                unit = "T$"
            macro.append({
                "key":   ticker,
                "name":  label,
                "value": round(val, 4),
                "unit":  unit,
                "date":  date,
            })

    output = {
        "_schema_version": "1.0",
        "updated":         now,
        "indexes":         indexes,
        "crypto":          crypto,
        "energy":          energy,
        "metals":          metals,
        "macro":           macro,
    }

    out_path = os.path.join(DATA_DIR, "market_quotes.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[market_quotes] 写入 {out_path}")
    print(f"  indexes={len(indexes)} crypto={len(crypto)} energy={len(energy)} metals={len(metals)} macro={len(macro)}")
    return output


if __name__ == "__main__":
    build_market_quotes()
