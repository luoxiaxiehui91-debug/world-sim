'''
compute_fci.py — L1 金融条件指数（FCI，Financial Conditions Index）

方案 v3 §7.3 实现：对 5 个 FRED 长序列做 PCA，第一主成分即 FCI。
约定：**FCI 越高 = 金融条件越紧**（与 Chicago NFCI 同向）。

━━ 双轨设计（2026-07-31 实测后定稿，务必先读）━━━━━━━━━━━━━━━━━━━━━━━━━━━

初版用「滚动 504 日窗口 + 窗口内 z-score」，与 NFCI 水平相关性仅 +0.065，sanity
不过。诊断（见 CHANGELOG）证明**方向与符号锁定都是对的**——问题在于滚动标准化
把水平信息当趋势去掉了：每个点都拿自己前 504 天做基准，指数被强制去趋势，而 NFCI
是一条有慢趋势的水平指数。改用全样本标准化后水平相关性 = **+0.832**。

但全样本 PCA 每次都用到「未来」数据，是 look-ahead。**Chicago Fed 自己的 NFCI 也
是每周全样本重估、整条历史被修订的**——所以"修订型"并非缺陷，而是这类指数的固有
性质，前提是**必须标注、且禁止拿它做回测**。

故本模块同时产出两条序列，并在字段级硬标注用途：

  fci_revised  全样本 PCA，每次运行整条重估（会修订历史）
               ✅ 用于：当期读数 / 日报 / 仪表盘 / 与 NFCI 对照
               ❌ 禁止：任何回测、预测验证、Brier 打分（含 look-ahead）

  fci_pit      扩展窗 PCA（只用 <= t 的数据），无 look-ahead
               ✅ 用于：回测 / 预测验证 / 天玑 Brier 打分
               ⚠️ 前期样本短，读数偏噪；与 NFCI 水平相关性 +0.467（低于 revised）

这与 §7.5 GED「年度冻结快照禁当当前信号」是同一条铁律的镜像面：
那边是"拿陈旧数据冒充实时"，这边是"拿修订数据冒充当时可得"。两者都必须 fail-loud。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

用法：
  python compute_fci.py              # 重估并落盘
  python compute_fci.py --sanity     # 仅跑 NFCI 相关性检查，不落盘
  python compute_fci.py --pit-burnin 504

输出：
  data/fci_daily.csv        双轨完整序列（revised 每次重写，pit 值稳定）
  data/fci_vintage_log.csv  append-only 版本轨迹（G4：每次运行追加一行）
  data/fci_latest.json      最新读数快照（供 GRV / 日报消费）

四道质量闸门（方案 §7.4）：
  G2 禁 fillna(0)  —— 缺失只做有限前向填充，填不上就剔除并计数，绝不补零
  G3 覆盖率闸      —— 成分数 <4/5 或样本不足 → 退出码 2，不写任何输出
  G4 输出溯源      —— as_of / data_vintage / schema_version + append-only 版本日志
  （G1 口径断言属 probit，不在本模块）

恢复注记（2026-08-04）：
  原 3342 行源码 08-03 被 deploy.sh 的 rsync --delete 抹除（未 git add），幸 pyc 幸存。
  本文件由 pyc 反编译（pycdc，容器内编译）+ 122KB 反汇编文本逐函数重建，
  与 pyc 行为等价性已由 sanity PASS 与落盘产物哈希比对验证。
'''
import os
import sys
import json
import argparse
from datetime import datetime, timezone
import numpy as np
import pandas as pd

SCHEMA_VERSION = 'fci-1.1'

BASE_DIR = os.environ.get('OPENCLAW_WORKSPACE',
                          os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
HIST_DIR = os.path.join(DATA_DIR, 'fred_history')
OUT_CSV  = os.path.join(DATA_DIR, 'fci_daily.csv')
OUT_LOG  = os.path.join(DATA_DIR, 'fci_vintage_log.csv')
OUT_JSON = os.path.join(DATA_DIR, 'fci_latest.json')

# (series_id, 名称, 方向: -1 = 越高越宽松需取反，1 = 越高越紧)
COMPONENTS = [
    ('T10Y2Y',      '期限利差(10Y-2Y)',  -1),
    ('BAA10Y',      '投资级信用利差',     1),
    ('BAMLH0A0HYM2', '高收益债利差',      1),
    ('VIXCLS',      '波动率VIX',         1),
    ('DTWEXBGS',    '贸易加权美元',      1),
]
# 符号锁定锚：信用利差块载荷和必须为正（>0 表示"利差走阔 = FCI 升高 = 更紧"）
SIGN_ANCHOR = ['BAA10Y', 'BAMLH0A0HYM2']

ANCHOR_SERIES = 'NFCI'
PIT_BURNIN    = 504        # 扩展窗 burn-in（≈ 2 年交易日）
FFILL_LIMIT   = 5          # G2：缺失最多前向填充 5 日（补节假日错位）
MIN_COMPONENTS = 4         # G3：成分数闸（5 缺 1 仍可算，缺 2 拒绝）
MIN_PANEL_ROWS = 252       # G3：面板行数闸（< 1 年交易日拒绝）
SANITY_CORR_MIN = 0.6      # sanity：revised vs NFCI 水平相关阈值

USAGE_POLICY = {
    'fci_revised': {
        'allow': ['nowcast', 'dashboard', 'alerting'],
        'deny':  ['backtest', 'verification', 'brier'],
        'note':  '全样本重估，含 look-ahead，历史会被修订',
    },
    'fci_pit': {
        'allow': ['backtest', 'verification', 'brier', 'nowcast'],
        'deny':  [],
        'note':  '扩展窗，仅用 <= t 数据，无 look-ahead',
    },
}


def _load_series(series_id=None):
    '''读取单个 FRED 序列 CSV，返回 DatetimeIndex 的 float Series。'''
    path = os.path.join(HIST_DIR, f'{series_id}.csv')
    if not os.path.exists(path):
        raise FileNotFoundError(f'缺少序列: {path}')
    df = pd.read_csv(path)
    if 'date' not in df.columns or 'value' not in df.columns:
        raise ValueError(f'{series_id}.csv 列名异常: {list(df.columns)}')
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df = df.dropna(subset=['date']).drop_duplicates(subset=['date'], keep='last')
    return df.set_index('date')['value'].sort_index()


def build_panel(verbose=None):
    '''
    构造对齐后的成分面板（已方向归一为「越大 = 越紧」）。

    G2 铁律：缺失值只做 limit=FFILL_LIMIT 的前向填充（补节假日错位），
    填不上的行直接剔除并计数，**绝不 fillna(0)** —— z-score 语境里 0 = 常态，
    补零 = 静默捏造「无压力」观测，属静默降级病族。
    '''
    raw = {}
    meta = []
    for sid, name, orient in COMPONENTS:
        s = _load_series(sid)
        raw[sid] = s
        meta.append({
            'series_id': sid,
            'name':      name,
            'orient':    orient,
            'rows':      int(len(s)),
            'first':     s.index.min().strftime('%Y-%m-%d'),
            'last':      s.index.max().strftime('%Y-%m-%d'),
        })

    panel = pd.DataFrame(raw).sort_index()
    n_union = len(panel)

    starts = [raw[sid].index.min() for sid, _, _ in COMPONENTS]
    binding = min(meta, key=lambda m: m['rows'])  # 行数最少的序列 = 面板约束项
    panel = panel[panel.index >= max(starts)]

    panel = panel.ffill(limit=FFILL_LIMIT)
    before = len(panel)
    panel = panel.dropna(how='any')
    dropped = before - len(panel)

    # 方向归一：orient=-1 的序列取反（越大 = 越紧）
    for sid, _, orient in COMPONENTS:
        if orient < 0:
            panel[sid] = -panel[sid]

    if verbose:
        print(f'[panel] 并集 {n_union} 行 → 共同区间 {before} 行 → 剔除残缺 {dropped} 行 → 可用 {len(panel)} 行')
        print(f'[panel] 区间 {panel.index.min().date()} ~ {panel.index.max().date()}')
        print(f'[panel] 约束项：{binding["series_id"]}（{binding["rows"]} 行，自 {binding["first"]}）'
              f'—— FRED 对 ICE 系列仅提供约 3 年滚动历史')
    return panel, meta, dropped, binding


def _pc1(z=None, anchor_pos=None):
    '''对已标准化矩阵求 PC1，返回 (载荷 w, 解释方差占比)。含符号锁定。'''
    cm = np.corrcoef(z.values, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cm)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    eigvals = eigvals[order]
    w = eigvecs[:, 0]
    if w[anchor_pos].sum() < 0:
        w = -w
    return w, float(eigvals[0] / eigvals.sum())


def _standardize(df=None):
    sd = df.std(ddof=0)
    mu = df.mean()
    if (sd <= 1e-12).any():
        raise ValueError(f'零方差成分: {list(sd[sd <= 1e-12].index)}')
    return (df - mu) / sd


def compute_revised(panel=None, anchor_pos=None, verbose=None):
    '''全样本 PCA（每次运行整条重估）—— 与 NFCI 可比的水平指数。'''
    z = _standardize(panel)
    w, vr = _pc1(z, anchor_pos)
    s = pd.Series(z.values @ w, index=panel.index, name='fci_revised')
    if verbose:
        load_str = ', '.join(f'{c}:{v:+.3f}' for c, v in zip(panel.columns, w))
        print(f'[revised] 全样本 PCA  PC1 解释方差={vr:.1%}  载荷={{{load_str}}}')
    return s, w, vr


def compute_pit(panel=None, anchor_pos=None, burnin=None, verbose=True):
    '''扩展窗 PCA（每点只用 <= t 的数据）—— 无 look-ahead，供回测/验证。'''
    if len(panel) <= burnin:
        raise ValueError(f'G3 拒绝：面板 {len(panel)} 行 <= PIT burn-in {burnin} 行')
    vrs, vals, idx = [], [], []
    for i in range(burnin, len(panel) + 1):
        hist = panel.iloc[:i]
        try:
            z = _standardize(hist)
            w, vr = _pc1(z, anchor_pos)
            vals.append(float(z.iloc[-1].values @ w))
            vrs.append(vr)
        except ValueError:
            vals.append(np.nan)
            vrs.append(np.nan)
        idx.append(panel.index[i - 1])
    s = pd.Series(vals, index=pd.DatetimeIndex(idx), name='fci_pit')
    if verbose:
        print(f'[pit] 扩展窗 PCA  burn-in={burnin}  输出 {len(s)} 点  起 {s.index.min().date()}  '
              f'PC1均解释方差={np.nanmean(vrs):.1%}')
    return s


def _corr_vs_nfci(s=None, nfci=None):
    j = pd.concat([nfci.rename('nfci'), s.rename('x')], axis=1, sort=True).sort_index()
    j['x'] = j['x'].ffill(limit=FFILL_LIMIT)
    j = j.dropna()
    if len(j) < 20:
        return None
    return {
        'corr_level':    round(float(j['x'].corr(j['nfci'])), 4),
        'corr_diff':     round(float(j['x'].diff().corr(j['nfci'].diff())), 4),
        'n_overlap':     int(len(j)),
        'overlap_range': f'{j.index.min().date()} ~ {j.index.max().date()}',
    }


def sanity_vs_nfci(revised=None, pit=None, verbose=None):
    '''对照 NFCI 的 sanity 闸：revised 水平相关 ≥ SANITY_CORR_MIN 才 PASS。'''
    try:
        nfci = _load_series(ANCHOR_SERIES)
    except FileNotFoundError:
        return {'status': 'SKIP', 'reason': f'{ANCHOR_SERIES}.csv 未采集'}

    r = _corr_vs_nfci(revised, nfci)
    p = _corr_vs_nfci(pit, nfci)
    if r is None:
        return {'status': 'SKIP', 'reason': '重叠样本不足 20 点'}

    status = 'PASS' if r['corr_level'] >= SANITY_CORR_MIN else 'FAIL'
    res = {
        'status':      status,
        'threshold':   SANITY_CORR_MIN,
        'gate_on':     'fci_revised.corr_level',
        'fci_revised': r,
        'fci_pit':     p,
    }
    if verbose:
        icon = 'OK' if status == 'PASS' else '!!'
        print(f'[sanity] {icon} revised vs NFCI  水平={r["corr_level"]:+.3f}  '
              f'变化={r["corr_diff"]:+.3f}  n={r["n_overlap"]}  (阈值 {SANITY_CORR_MIN})')
        print(f'[sanity]    pit vs NFCI      水平={p["corr_level"]:+.3f}  '
              f'变化={p["corr_diff"]:+.3f}  n={p["n_overlap"]}  (仅参考，不作闸门)')
    return res


def write_outputs(panel, revised, pit, w, vr, meta, binding, sanity, dropped, burnin, verbose=True):
    '''G4 输出溯源：三件套落盘（csv 重写 / 版本日志 append-only / latest 快照）。'''
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
    vintage = min(m['last'] for m in meta)

    df = pd.DataFrame({'fci_revised': revised}).join(pit, how='left')
    df.insert(0, 'date', df.index.strftime('%Y-%m-%d'))
    df['pit_available'] = df['fci_pit'].notna().astype(int)
    for c, wi in zip(panel.columns, w):
        df[f'load_{c}'] = round(float(wi), 4)
    df['pc1_var_ratio'] = round(vr, 4)
    df['as_of'] = now
    df['data_vintage'] = vintage
    df['schema_version'] = SCHEMA_VERSION
    df.to_csv(OUT_CSV, index=False)

    last_pit = pit.dropna()
    log_row = pd.DataFrame([{
        'as_of': now,
        'data_vintage': vintage,
        'schema_version': SCHEMA_VERSION,
        'date': df['date'].iloc[-1],
        'fci_revised': round(float(revised.iloc[-1]), 6),
        'fci_pit': round(float(last_pit.iloc[-1]), 6) if len(last_pit) else '',
        'pc1_var_ratio': round(vr, 4),
        'n_components': len(panel.columns),
        'panel_rows': len(panel),
        'rows_dropped': dropped,
        'sanity_status': sanity.get('status', ''),
        'sanity_corr_level': sanity.get('fci_revised', {}).get('corr_level', ''),
    }])
    log_row.to_csv(OUT_LOG, mode='a', index=False, header=not os.path.exists(OUT_LOG))

    payload = {
        'schema_version': SCHEMA_VERSION,
        'as_of': now,
        'data_vintage': vintage,
        'date': df['date'].iloc[-1],
        'fci_revised': round(float(revised.iloc[-1]), 6),
        'fci_pit': round(float(last_pit.iloc[-1]), 6) if len(last_pit) else None,
        'interpretation': '越高 = 金融条件越紧（与 Chicago NFCI 同向）；单位 = 标准差',
        'usage_policy': USAGE_POLICY,
        'method': {
            'revised': '全样本 PCA，每次运行整条重估',
            'pit': f'扩展窗 PCA，burn-in={burnin} 交易日',
            'sign_anchor': SIGN_ANCHOR,
            'pc1_var_ratio': round(vr, 4),
            'loadings': {c: round(float(wi), 4) for c, wi in zip(panel.columns, w)},
        },
        'panel': {
            'rows': int(len(panel)),
            'range': f'{panel.index.min().date()} ~ {panel.index.max().date()}',
            'rows_dropped_incomplete': int(dropped),
            'binding_constraint': binding,
        },
        'components': meta,
        'sanity_vs_nfci': sanity,
    }
    _tmp_322 = OUT_JSON + ".tmp"
    with open(_tmp_322, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(_tmp_322, OUT_JSON)


def main():
    ap = argparse.ArgumentParser(description='L1 金融条件指数（FCI）—— 双轨 PCA')
    ap.add_argument('--pit-burnin', type=int, default=PIT_BURNIN,
                    help=f'PIT 轨 burn-in 交易日（默认 {PIT_BURNIN} ≈ 24 个月）')
    ap.add_argument('--sanity', action='store_true', help='仅跑 sanity 检查，不落盘')
    args = ap.parse_args()

    print(f'=== L1 FCI  schema={SCHEMA_VERSION}  pit_burnin={args.pit_burnin}')

    # P1 修复（fci-gate-not-consumed）：消费 fred_gate_status.json——
    # gate_ok=false（上游拉取不一致/落后）→ 冻结不落库 fail-loud（--sanity 跳过）
    if not args.sanity:
        _gate_path = os.path.join(DATA_DIR, 'fred_gate_status.json')
        if os.path.exists(_gate_path):
            try:
                with open(_gate_path, encoding='utf-8') as _gf:
                    _gate = json.load(_gf)
                if not _gate.get('gate_ok', True):
                    print(f'ERROR: 拉取一致性闸 FAIL（{_gate_path}）——FCI 冻结不落库', file=sys.stderr)
                    sys.exit(3)
            except Exception as _ge:
                print(f'WARN: gate 读取失败（不阻塞）: {_ge}', file=sys.stderr)

    panel, meta, dropped, binding = build_panel(verbose=True)

    # G3 覆盖率闸：不满足即退出，不写任何输出
    if len(panel.columns) < MIN_COMPONENTS:
        print(f'ERROR: G3 拒绝 —— 成分数 {len(panel.columns)} < {MIN_COMPONENTS}')
        sys.exit(2)
    if len(panel) < MIN_PANEL_ROWS:
        print(f'ERROR: G3 拒绝 —— 面板 {len(panel)} 行 < {MIN_PANEL_ROWS}')
        sys.exit(2)

    anchor_pos = [list(panel.columns).index(c) for c in SIGN_ANCHOR]
    revised, w, vr = compute_revised(panel, anchor_pos, verbose=True)
    pit = compute_pit(panel, anchor_pos, args.pit_burnin, verbose=True)
    sanity = sanity_vs_nfci(revised, pit, verbose=True)

    if args.sanity:
        print(json.dumps(sanity, ensure_ascii=False, indent=2))
        sys.exit(0 if sanity.get('status') in ('PASS', 'SKIP') else 3)

    write_outputs(panel, revised, pit, w, vr, meta, binding, sanity, dropped,
                  args.pit_burnin)

    print('\n最近 5 个交易日：')
    tail = pd.DataFrame({'revised': revised, 'fci_pit': pit}).tail(5)
    for d, r in tail.iterrows():
        pv = f'{r["fci_pit"]:+.3f}' if pd.notna(r['fci_pit']) else '  n/a '
        print(f'  {d.date()}  revised={r["revised"]:+.3f}   pit={pv}')

    if sanity.get('status') == 'FAIL':
        print(f'\n!! sanity 未达阈（{sanity["fci_revised"]["corr_level"]} < {SANITY_CORR_MIN}）'
              f'：请复核成分方向与符号锁定，勿直接上线。')
        sys.exit(3)


if __name__ == '__main__':
    main()
