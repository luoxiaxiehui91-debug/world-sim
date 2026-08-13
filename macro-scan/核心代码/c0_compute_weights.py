"""
c0_compute_weights.py — world-sim 天枢 · C0 加权接线（一次性验证脚本，不接 scheduler）

职责（用户拍板方向 A）：
  grain = (source_id, target_type)
  source_id   = FRED 序列 id（如 'DGS10'，对应 indicators.model_ver='fred-DGS10'）
  target_type = GRV 11 维（合法 target_type 词表，取自 source_dimension_map.yaml 的
              primary 集合）：climate_risk / disaster_risk / energy_grid_risk /
              global_composite / japan_monetary / middle_east_energy / russia_europe /
              sanctions_risk / seismic_risk / taiwan_strait / us_china_strategic。
              这是 grv_weights.yaml weights 子树里 get_weights_for_target() 消费的
              合法 target_type 集合（grep GRV / dimension / global_composite 得出）。

  权重由 FRED 历史数据派生（逆滚动波动率 / 变异系数，禁前视泄漏），双写：
    - indicator_weights（PG 权威表，CREATE TABLE 见 sql/02_indicator_weights.sql）
    - grv_weights.yaml 的 weights 子树（只动 FRED series-id 颗粒的键，
      保留其他 source 级键与 version/baseline_snapshot 等元键）
  并验证 get_weights_for_target(target_type) 能读回派生权重。

环境前提（本环境实测 indicators 为空，需先补数）：
  --backfill  从 FRED CSV 历史（B1 同源数据，data/fred_history/*.csv）回填 indicators，
              使 C0 可基于真实数据派生。CSV 路径默认 /workspace/data/fred_history。
  回填仅写 indicators，不属于 C0 权重逻辑；C0 运行本身对 indicators 零干扰。

连接：环境变量 WORLDSIM_APP_PW；host=worldsim-pg port=5432 dbname=worldsim user=worldsim_app
      任何连接/查询/写入异常都被捕获并以 (0,0) 返回，不向上抛异常（与 pg_write_indicators 一致）。

红线：本脚本只读 indicators、只写 indicator_weights + grv_weights.yaml 的 weights 子树，
      不改 scheduler/fetcher_base/contracts/news_db，不改 weights 之外的 yaml 键。
"""

import os
import sys
import json
import math
import shutil
import argparse
import statistics
from datetime import date, datetime, timezone
from collections import defaultdict

# ── 路径解析（不依赖 CWD，按 __file__ 反推 + 容器内候选）─────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))


def _resolve_yaml_path(override=None):
    """grv_weights.yaml 权威路径：容器内为 /workspace/config/grv_weights.yaml。"""
    candidates = []
    if override:
        candidates.append(override)
    if os.environ.get("GRV_WEIGHTS_PATH"):
        candidates.append(os.environ["GRV_WEIGHTS_PATH"])
    candidates += [
        "/workspace/config/grv_weights.yaml",
        os.path.join(_HERE, "..", "config", "grv_weights.yaml"),
        os.path.join(_HERE, "config", "grv_weights.yaml"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    # 都不存在则落到容器内权威路径（首次由本脚本创建）
    return os.path.abspath(override or "/workspace/config/grv_weights.yaml")


def _resolve_csv_dir(override=None):
    candidates = []
    if override:
        candidates.append(override)
    if os.environ.get("FRED_HISTORY_DIR"):
        candidates.append(os.environ["FRED_HISTORY_DIR"])
    candidates += [
        "/workspace/data/fred_history",
        os.path.join(_HERE, "..", "data", "fred_history"),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return os.path.abspath(c)
    return None


# ── 连接 ─────────────────────────────────────────────────────────────────────
def pg_connect():
    """复用 pg_write_indicators 的连接范式；失败返回 None（不抛）。"""
    try:
        import psycopg
    except Exception as e:
        print(f"ERROR [c0] psycopg 不可用: {e}")
        return None
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        print("ERROR [c0] 环境变量 WORLDSIM_APP_PW 未设置")
        return None
    try:
        return psycopg.connect(
            "host=worldsim-pg port=5432 dbname=worldsim user=worldsim_app",
            password=pw, connect_timeout=10,
        )
    except Exception as e:
        print(f"ERROR [c0] 连接 worldsim-pg 失败: {e}")
        return None


# ── DDL（与 sql/02_indicator_weights.sql 保持一致，用于幂等建表）─────────────────
_DDL = """
CREATE TABLE IF NOT EXISTS indicator_weights (
  source_id      VARCHAR(64)  NOT NULL,
  target_type    VARCHAR(64)  NOT NULL,
  weight         DOUBLE PRECISION NOT NULL,
  weight_min     DOUBLE PRECISION NOT NULL DEFAULT 0.05,
  weight_max     DOUBLE PRECISION NOT NULL DEFAULT 5.00,
  effective_from DATE         NOT NULL DEFAULT CURRENT_DATE,
  approved_by    VARCHAR(64),
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
  PRIMARY KEY (source_id, target_type),
  CHECK (weight BETWEEN weight_min AND weight_max)
);
CREATE INDEX IF NOT EXISTS idx_indicator_weights_target
  ON indicator_weights (target_type);
"""


def ensure_table(conn):
    try:
        with conn.cursor() as cur:
            cur.execute(_DDL)
        conn.commit()
        return True
    except Exception as e:
        print(f"ERROR [c0] 建表 indicator_weights 失败: {e}")
        conn.rollback()
        return False


# ── 环境前提：从 FRED CSV 历史回填 indicators（B1 同源语义）──────────────────────
def backfill_indicators_from_csv(csv_dir):
    """把 data/fred_history/*.csv（date,value）按 B1 语义写进 indicators。幂等。"""
    try:
        from pg_write_indicators import upsert_indicator_rows
    except Exception as e:
        print(f"ERROR [c0] 无法导入 pg_write_indicators: {e}")
        return (0, 0)
    if not csv_dir or not os.path.isdir(csv_dir):
        print(f"ERROR [c0] FRED CSV 目录不存在: {csv_dir}")
        return (0, 0)
    files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
    print(f"[c0] backfill：发现 {len(files)} 个 FRED CSV，目录={csv_dir}")
    total = (0, 0)
    for fn in sorted(files):
        sid = fn[:-4]
        path = os.path.join(csv_dir, fn)
        try:
            import csv as _csv
            rows = []
            with open(path, newline="", encoding="utf-8") as fh:
                rdr = _csv.reader(fh)
                header = next(rdr, None)
                for r in rdr:
                    if len(r) < 2:
                        continue
                    d, v = r[0].strip(), r[1].strip()
                    if not d or not v:
                        continue
                    try:
                        val = float(v)
                    except ValueError:
                        continue
                    rows.append({
                        "indicator_key": sid,
                        "as_of": d[:10],
                        "data_vintage": date.today().isoformat(),
                        "horizon": "actual",
                        "value": val,
                        "ci_low": None,
                        "ci_high": None,
                        "model_ver": f"fred-{sid}",
                        "created_at": datetime.now(timezone.utc),
                        "schema_version": "1.0",
                        "status": "ok",
                    })
            if not rows:
                continue
            # 去重：CSV 可能因增量追加出现重复 as_of，同一 (indicator_key,as_of,
            # horizon,model_ver,data_vintage) 唯一约束下 unnest 批量 upsert 会整批失败。
            # 按 as_of 去重（保留最后出现=最近一次抓取），不影响指标语义。
            _dedup = {}
            for _r in rows:
                _dedup[_r["as_of"]] = _r
            if len(_dedup) != len(rows):
                print(f"  [backfill] {sid}: 去重 {len(rows)}→{len(_dedup)} 行"
                      f"（CSV 含重复 as_of）")
            rows = list(_dedup.values())
            res = upsert_indicator_rows(rows)
            total = (total[0] + res[0], total[1] + res[1])
            print(f"  [backfill] {sid}: +{res[0]}/u{res[1]} ({len(rows)} 行)")
        except Exception as e:
            print(f"WARN [c0] backfill {sid} 失败（跳过）: {e}")
    print(f"[c0] backfill 汇总 inserted={total[0]} updated={total[1]}")
    return total


# ── 读 FRED 数据 ─────────────────────────────────────────────────────────────
def load_fred_series(conn):
    """读 indicators 中 model_ver LIKE 'fred-%' 的 ok 行，按 indicator_key 分组。
    返回 {indicator_key: [(as_of_date, value, data_vintage_date), ...]}（按 as_of 升序）。"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indicator_key, as_of, value, data_vintage "
                "FROM indicators "
                "WHERE model_ver LIKE 'fred-%' AND status='ok' AND value IS NOT NULL "
                "ORDER BY indicator_key, as_of"
            )
            raw = cur.fetchall()
    except Exception as e:
        print(f"ERROR [c0] 读取 indicators 失败: {e}")
        return {}
    series = {}
    for ik, as_of, value, dv in raw:
        series.setdefault(ik, []).append((as_of, float(value), dv))
    print(f"[c0] 读取 FRED 序列 {len(series)} 个，总 ok 行 {len(raw)}")
    return series


# ── 文档化种子映射：FRED series_id → 合法 target_type（GRV 11 维）────────────────
# 合法 target_type = source_dimension_map.yaml 的 primary 集合（GRV 11 维）。
# 映射原则（FRED 宏观/地缘序列 → 其最能佐证的维度）：
#   · 绝大多数美国/全球宏观序列（利率、通胀、增长、就业、股指、信用、美元、GPR 综指、
#     GSCPI 供应链压力）归 global_composite（宽口径合成信号）。
#   · 日本序列（日债、日失业率、USD/JPY）→ japan_monetary。
#   · 离岸人民币(DEXCHUS)、中国地缘风险(GPRC_CHN) → us_china_strategic。
#   · WTI 原油(DCOILWTICO) → energy_grid_risk。
#   · 小麦/玉米(PWHEAMTUSDM/PMAIZMTUSDM, 气候→粮食) → climate_risk。
#   · 俄罗斯地缘风险(GPRC_RUS) → russia_europe；台湾地缘风险(GPRC_TWN) → taiwan_strait。
# 未列出的序列归 'uncategorized' 并 WARN（不静默丢弃）。
FRED_SEED = {
    # ── 利率 & 货币政策（全球宏观合成）──
    "DFF":            "global_composite",
    "DGS10":          "global_composite",
    "DGS2":           "global_composite",
    "DGS3MO":         "global_composite",
    "T10Y2Y":         "global_composite",
    "T10Y3M":         "global_composite",
    "ECBDFR":         "global_composite",
    # ── 通胀（全球宏观合成）──
    "CPIAUCSL":       "global_composite",
    "T5YIE":          "global_composite",
    "PCEPI":          "global_composite",
    "PPIACO":         "global_composite",
    # ── 经济增长 & 就业（全球宏观合成）──
    "GDPC1":          "global_composite",
    "UNRATE":         "global_composite",
    "PAYEMS":         "global_composite",
    "INDPRO":         "global_composite",
    "ICSA":           "global_composite",
    "HOUST":          "global_composite",
    "PERMIT":         "global_composite",
    "UMCSENT":        "global_composite",
    # ── 资产 & 商品 ──
    "SP500":          "global_composite",
    "VIXCLS":         "global_composite",
    "DTWEXBGS":       "global_composite",
    "PCOPPUSDM":      "global_composite",   # 铜：全球工业金属，归合成
    "DCOILWTICO":     "energy_grid_risk",   # WTI 原油
    # ── 信用 & 金融压力（全球宏观合成）──
    "BAA10Y":         "global_composite",
    "BAMLH0A0HYM2":   "global_composite",
    "NFCI":           "global_composite",
    "M2SL":           "global_composite",
    "WDTGAL":         "global_composite",   # TGA 流动性
    # ── 欧洲（欧元序列归合成；俄地缘单列）──
    "IRLTLT01EZM156N":    "global_composite",
    "CP0000EZ19M086NEST": "global_composite",
    "CLVMNACSCAB1GQEA19": "global_composite",
    "IRLTLT01GBM156N":    "global_composite",
    "CPALTT01GBM659N":    "global_composite",
    "LRHUTTTTGBM156S":    "global_composite",
    # ── 日本（monetary 维）──
    "IRLTLT01JPM156N":    "japan_monetary",
    "LRUNTTTTJPM156S":    "japan_monetary",
    "DEXJPUS":            "japan_monetary",
    # ── 中美战略（离岸人民币 + 中国地缘风险）──
    "DEXCHUS":        "us_china_strategic",
    "GPRC_CHN":       "us_china_strategic",
    # ── 气候→粮食 ──
    "PWHEAMTUSDM":    "climate_risk",       # 小麦
    "PMAIZMTUSDM":    "climate_risk",       # 玉米
    # ── 地缘风险指数家族（GPR）──
    "GPR":            "global_composite",
    "GPRA":           "global_composite",
    "GPRT":           "global_composite",
    "GPRC_USA":       "global_composite",
    "GPRC_RUS":       "russia_europe",
    "GPRC_TWN":       "taiwan_strait",
    "GSCPI":          "global_composite",   # 全球供应链压力指数
}

DEFAULT_TARGET = "uncategorized"        # 未映射序列的兜底（显式 WARN，不静默丢）
WEIGHT_FLOOR = 0.05
WEIGHT_CEIL = 5.00
APPROVED_BY = "c0_compute_weights"


# ── 打分（禁前视泄漏：只用历史值与 as_of 排序，一阶差分 stddev_samp）──────────────
def _score_series(points):
    """points: [(as_of, value, dv), ...] 升序。返回 (coverage, inv_cv, vintage_lag_days)。"""
    vals = [p[1] for p in points]
    n = len(vals)
    if n == 0:
        return 0.0, 0.0, 9999
    coverage = len([v for v in vals if v is not None]) / n
    diffs = [vals[i] - vals[i - 1] for i in range(1, n)]
    if len(diffs) >= 2:
        std = statistics.stdev(diffs)          # 滚动一阶差分的样本标准差
    else:
        std = 0.0
    mean_abs = abs(sum(vals) / n) if n else 0.0
    cv = std / (mean_abs + 1e-9)              # 变异系数（尺度无关）
    inv_cv = 1.0 / (cv + 1e-6)                # 逆波动率：越稳越高
    # vintage 滞后（禁前视：仅用已存在的 data_vintage 下界）
    try:
        max_dv = max(p[2] for p in points if p[2] is not None)
        if isinstance(max_dv, str):
            max_dv = date.fromisoformat(str(max_dv)[:10])
        lag = (date.today() - max_dv).days
    except Exception:
        lag = 0
    lag = max(lag, 0)
    return coverage, inv_cv, lag


def compute_weights(series):
    """派生权重。返回行列表 [(source_id, target_type, weight), ...]，已 round(.,5)。"""
    # 1) 每序列算分
    scored = {}   # source_id -> (target_type, raw_score)
    unmapped = []
    for sid, points in series.items():
        coverage, inv_cv, lag = _score_series(points)
        if sid in FRED_SEED:
            tt = FRED_SEED[sid]
        else:
            tt = DEFAULT_TARGET
            unmapped.append(sid)
            print(f"WARN [c0] 序列 {sid} 无种子映射 → 归 '{DEFAULT_TARGET}'（未静默丢弃）")
        fresh = 1.0 / (1.0 + lag / 180.0)        # vintage 滞后因子（≤1）
        raw = coverage * fresh * inv_cv
        scored[sid] = (tt, raw)

    # 2) 同 target_type 内按逆波动率归一（权重和=1）
    by_tt = defaultdict(list)
    for sid, (tt, raw) in scored.items():
        by_tt[tt].append((sid, raw))
    rows = []
    for tt, items in by_tt.items():
        tot = sum(r for _, r in items)
        if tot <= 0:
            # 防 0 除：平均分配（仍 clip）
            share = 1.0 / len(items)
            for sid, _ in items:
                w = round(min(max(share, WEIGHT_FLOOR), WEIGHT_CEIL), 5)
                rows.append((sid, tt, w))
            continue
        for sid, raw in items:
            w = raw / tot                      # 归一
            w = min(max(w, WEIGHT_FLOOR), WEIGHT_CEIL)   # 与 weight_matrix clip 一致
            rows.append((sid, tt, round(w, 5)))
    print(f"[c0] 派生权重：{len(rows)} 行，覆盖 {len(by_tt)} 个 target_type"
          + (f"，未映射 {len(unmapped)} 个" if unmapped else ""))
    return rows


# ── 命名空间冲突防护 ─────────────────────────────────────────────────────────
# grv_weights.yaml 的 weights 子树以 source_id 为顶层键；部分 FRED 序列 id（如 GPR/
# GSCPI）可能与既有「source 级键」（同名 fetcher 注册的名字）撞键，直接写会污染既有
# source 条目。检测到冲突时给该 FRED id 加 'fred.' 前缀（PG 与 yaml 同步加前缀，
# 保证一致且绝不覆盖既有 source 条目）。生产环境 41 个官方 FRED 序列无冲突，此步为空操作。
#
# 判定「既有键」是否为本脚本自己上一轮写入的 FRED 键：本脚本写入的键其 target_type 子键
# 必为 GRV 11 维子集；既有 source 级键的子键是中文场景名（不在 GRV 维内）。据此区分，
# 只对真正的 source 级键加前缀，避免把自身上一轮写入的键误判为冲突（否则破坏幂等）。
GRV_DIMS = frozenset({
    "climate_risk", "disaster_risk", "energy_grid_risk", "global_composite",
    "japan_monetary", "middle_east_energy", "russia_europe", "sanctions_risk",
    "seismic_risk", "taiwan_strait", "us_china_strategic",
})


def _looks_like_own_fred_key(entry):
    if not isinstance(entry, dict) or not entry:
        return False
    return set(entry.keys()).issubset(GRV_DIMS)


def resolve_source_ids(rows, yaml_path):
    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            existing = (yaml.safe_load(f) or {}).get("weights", {})
    except Exception:
        existing = {}
    resolved = []
    collided = []
    for sid, tt, w in rows:
        ent = existing.get(sid)
        if isinstance(ent, dict) and not _looks_like_own_fred_key(ent):
            # 既有键是 source 级键（子键为中文场景名）→ 冲突，加前缀防污染
            ns = "fred." + sid
            collided.append((sid, ns))
            resolved.append((ns, tt, w))
        else:
            # 不存在，或既有的就是本脚本自己写的 FRED 键（GRV 维子键）→ 保持原 id
            resolved.append((sid, tt, w))
    if collided:
        print(f"WARN [c0] FRED id 与既有 source 键冲突，已加 fred. 前缀防污染："
              f"{[c[0] for c in collided]}")
    return resolved



# ── 双写 1/2：PG indicator_weights ────────────────────────────────────────────
def upsert_weights(conn, rows):
    """unnest + ON CONFLICT(source_id,target_type) DO UPDATE + RETURNING(xmax=0) 计数。"""
    if not rows:
        return (0, 0)
    eff = date.today()
    sql = """
    INSERT INTO indicator_weights
        (source_id, target_type, weight, weight_min, weight_max, effective_from, approved_by)
    SELECT
        unnest(%(sid)s::varchar[]),
        unnest(%(tt)s::varchar[]),
        unnest(%(w)s::double precision[]),
        unnest(%(wmin)s::double precision[]),
        unnest(%(wmax)s::double precision[]),
        unnest(%(eff)s::date[]),
        unnest(%(appr)s::varchar[])
    ON CONFLICT (source_id, target_type) DO UPDATE SET
        weight = EXCLUDED.weight,
        weight_min = EXCLUDED.weight_min,
        weight_max = EXCLUDED.weight_max,
        effective_from = EXCLUDED.effective_from,
        approved_by = EXCLUDED.approved_by
    RETURNING (xmax = 0) AS did_insert
    """
    params = {
        "sid": [r[0] for r in rows],
        "tt": [r[1] for r in rows],
        "w": [float(r[2]) for r in rows],
        "wmin": [WEIGHT_FLOOR] * len(rows),
        "wmax": [WEIGHT_CEIL] * len(rows),
        "eff": [eff] * len(rows),
        "appr": [APPROVED_BY] * len(rows),
    }
    try:
        inserted = updated = 0
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for rec in cur:
                if rec[0]:
                    inserted += 1
                else:
                    updated += 1
        conn.commit()
        return (inserted, updated)
    except Exception as e:
        print(f"ERROR [c0] 写入 indicator_weights 失败: {e}")
        conn.rollback()
        return (0, 0)


# ── 双写 2/2：grv_weights.yaml weights 子树（保留其他键，先备份）────────────────
def sync_yaml(rows, yaml_path):
    """只写 weights 子树里 FRED series-id 颗粒的键；保留 version/initialized_at/
    last_updated/audit_applied/baseline_snapshot/slow_variables_weights 及 source 级键。
    落盘前先备份。"""
    try:
        import yaml
    except Exception as e:
        print(f"ERROR [c0] yaml 不可用: {e}")
        return False
    if not os.path.isfile(yaml_path):
        print(f"WARN [c0] yaml 不存在，将新建: {yaml_path}")
        data = {}
    else:
        # 备份
        bak = yaml_path + ".c0bak"
        try:
            shutil.copy2(yaml_path, bak)
            print(f"[c0] 已备份 yaml → {bak}")
        except Exception as e:
            print(f"WARN [c0] 备份 yaml 失败: {e}")
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    weights = data.setdefault("weights", {})
    for sid, tt, w in rows:
        weights.setdefault(sid, {})[tt] = round(float(w), 5)

    data["last_updated"] = date.today().isoformat()
    try:
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=True,
                           default_flow_style=False)
        print(f"[c0] 已同步 yaml weights → {yaml_path}")
        return True
    except Exception as e:
        print(f"ERROR [c0] 写 yaml 失败: {e}")
        return False


def dump_json_backup(rows, path):
    try:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": APPROVED_BY,
            "grain": ["source_id", "target_type"],
            "target_type_vocab": "GRV 11 dimensions",
            "weights": [
                {"source_id": r[0], "target_type": r[1], "weight": r[2]}
                for r in rows
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[c0] 权重 JSON 备份 → {path}")
    except Exception as e:
        print(f"WARN [c0] JSON 备份失败: {e}")


# ── 验证 ─────────────────────────────────────────────────────────────────────
def verify(conn, rows, yaml_path):
    ok = True
    # (a) PG count == len(rows)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM indicator_weights")
            pg_count = cur.fetchone()[0]
        print(f"[verify] indicator_weights count={pg_count} / 派生行数={len(rows)}")
        if pg_count != len(rows):
            print(f"  FAIL: count 不一致")
            ok = False
        else:
            print("  PASS: count 一致")
    except Exception as e:
        print(f"  ERROR: {e}")
        ok = False

    # (b) get_weights_for_target 读回（用 weight_matrix 现函数，证明不报错且值对）
    #     只比对【本次 FRED 派生】的 (source_id,target_type) 键，避免与 yaml 中既有
    #     source 级键（如 marketaux 的 global_composite）误判。
    try:
        import weight_matrix
        weight_matrix.WEIGHTS_PATH = yaml_path
        tt_to_sids = defaultdict(list)
        for sid, tt, w in rows:
            tt_to_sids[tt].append((sid, w))
        sample_tt = max(tt_to_sids, key=lambda k: len(tt_to_sids[k]))
        got = weight_matrix.get_weights_for_target(sample_tt)
        print(f"[verify] get_weights_for_target('{sample_tt}') 读回 {len(got)} 项"
              f"（含既有 source 级键 + 本次 FRED 键）")
        mismatch = []
        for sid, w in tt_to_sids[sample_tt]:
            g = got.get(sid)
            if g is None or round(float(g), 5) != round(float(w), 5):
                mismatch.append((sid, w, g))
        if mismatch:
            print(f"  FAIL: 读回值不一致 {mismatch[:5]}")
            ok = False
        else:
            print(f"  PASS: get_weights_for_target 读回与 PG 派生一致（{sample_tt}）")
    except Exception as e:
        print(f"  ERROR: get_weights_for_target 验证异常: {e}")
        ok = False

    # (c) yaml weights == PG（round 5）
    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            yd = yaml.safe_load(f) or {}
        yw = yd.get("weights", {})
        pgmap = {(r[0], r[1]): r[2] for r in rows}
        bad = []
        for (sid, tt), w in pgmap.items():
            yval = yw.get(sid, {}).get(tt)
            if yval is None or round(float(yval), 5) != round(float(w), 5):
                bad.append((sid, tt, w, yval))
        if bad:
            print(f"  FAIL: yaml 与 PG 不一致 {bad[:5]}")
            ok = False
        else:
            print("  PASS: yaml weights 与 PG 一致（round 5）")
    except Exception as e:
        print(f"  ERROR: yaml 比对异常: {e}")
        ok = False

    return ok


# ── 主流程 ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="C0 加权派生权重（一次性验证）")
    ap.add_argument("--backfill", action="store_true",
                    help="先从 FRED CSV 历史回填 indicators（环境补数，非 C0 逻辑）")
    ap.add_argument("--csv-dir", default=None, help="FRED CSV 历史目录")
    ap.add_argument("--yaml", default=None, help="grv_weights.yaml 路径（覆盖自动探测）")
    ap.add_argument("--json-backup", default="/tmp/c0_weights_backup.json",
                    help="权重 JSON 备份路径")
    ap.add_argument("--skip-verify", action="store_true", help="跳过验证步骤")
    args = ap.parse_args()

    yaml_path = _resolve_yaml_path(args.yaml)
    print(f"[c0] grv_weights.yaml → {yaml_path}")

    conn = pg_connect()
    if conn is None:
        print("[c0] 无法连接 PG，退出 (0,0)")
        return (0, 0)

    if args.backfill:
        csv_dir = _resolve_csv_dir(args.csv_dir)
        print(f"[c0] 环境补数：回填 indicators（CSV={csv_dir}）")
        backfill_indicators_from_csv(csv_dir)

    if not ensure_table(conn):
        conn.close()
        return (0, 0)

    series = load_fred_series(conn)
    if not series:
        print("[c0] 无 FRED 数据可派生（请先 --backfill）。退出。")
        conn.close()
        return (0, 0)

    rows = compute_weights(series)
    rows = resolve_source_ids(rows, yaml_path)   # 防 FRED id 与既有 source 键撞键
    ins, upd = upsert_weights(conn, rows)
    print(f"[c0] indicator_weights upsert: inserted={ins} updated={upd}")

    sync_yaml(rows, yaml_path)
    dump_json_backup(rows, args.json_backup)

    if not args.skip_verify:
        verify(conn, rows, yaml_path)

    conn.close()
    return (ins, upd)


if __name__ == "__main__":
    res = main()
    print(f"[c0] DONE inserted={res[0]} updated={res[1]}")
