"""
monte_carlo_v2.py — 增强型蒙特卡洛模拟
新增：跳跃扩散（Merton模型）+ GARCH(1,1)波动率聚类
对比原版：使用固定波动率的简单GBM随机游走

使用方法：
    from monte_carlo_v2 import run_monte_carlo_v2
    result = run_monte_carlo_v2(current_metrics, n_paths=5000, model='garch_jump')

版本：v5（5轮精炼）| 日期：2026-05-19
"""

import numpy as np
from scipy.stats import norm, poisson, lognorm
from typing import Dict, Optional, Literal
import json
import os
from pathlib import Path

def _load_calibration_file() -> Dict:
    """从知识库加载波动率校准参数（JSON），失败时静默返回空字典，模拟器自动回退默认参数。"""
    try:
        _base = os.environ.get(
            "OPENCLAW_WORKSPACE",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        _kb_root = os.environ.get("KB_ROOT") or os.path.join(_base, "知识库")
        cal_path = os.path.join(_kb_root, "财经知识库",
                                "02_核心变量因果链", "波动率校准参数.json")
        if os.path.exists(cal_path):
            with open(cal_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

_CAL = _load_calibration_file()
_CAL_AVAILABLE = bool(_CAL.get("_mc_calibration"))


# ============================================================
# 参数配置（基于知识库文档标定）
# ============================================================

VARIABLES = ['gdp_growth', 'inflation', 'unemployment', 'fed_funds_rate',
             'vix', 'sp500_return', 'china_gdp']

PARAMS = {
    'gdp_growth': {
        'mu': 2.2,          # 长期均值（%）
        'theta': 0.35,      # 均值回归速度
        'sigma': 1.8,       # 扩散系数
        'omega': 0.003,     # GARCH基础项
        'alpha': 0.12,      # ARCH项
        'beta': 0.82,       # GARCH持久项
        'lambda_jump': 0.10,  # 每年跳跃频率（经济冲击）
        'mu_jump': -2.5,      # 跳跃均值（%，负=衰退冲击）
        'sigma_jump': 2.0,    # 跳跃标准差（%）
        'min_val': -15.0,   # 边界
        'max_val': 15.0,
    },
    'inflation': {
        'mu': 2.0,
        'theta': 0.25,
        'sigma': 0.8,
        'omega': 0.001,
        'alpha': 0.08,
        'beta': 0.86,
        'lambda_jump': 0.08,
        'mu_jump': 1.5,     # 通胀冲击偏正（%）
        'sigma_jump': 1.0,
        'min_val': -2.0,
        'max_val': 20.0,
    },
    'unemployment': {
        'mu': 4.5,
        'theta': 0.40,
        'sigma': 0.6,
        'omega': 0.0008,
        'alpha': 0.10,
        'beta': 0.85,
        'lambda_jump': 0.12,
        'mu_jump': 2.5,     # 失业率上升冲击（%）
        'sigma_jump': 1.5,
        'min_val': 2.0,
        'max_val': 25.0,
    },
    'fed_funds_rate': {
        'mu': 3.0,
        'theta': 0.20,
        'sigma': 0.5,
        'omega': 0.0005,
        'alpha': 0.07,
        'beta': 0.88,
        'lambda_jump': 0.05,
        'mu_jump': 0.0,
        'sigma_jump': 0.010,
        'min_val': 0.0,
        'max_val': 20.0,
    },
    'vix': {
        'mu': 18.0,
        'theta': 0.50,
        'sigma': 6.0,
        'omega': 0.5,
        'alpha': 0.15,
        'beta': 0.80,
        'lambda_jump': 0.20,    # VIX跳跃频率更高
        'mu_jump': 8.0,         # 正向跳跃（风险事件→VIX飙升）
        'sigma_jump': 5.0,
        'min_val': 9.0,
        'max_val': 100.0,
    },
    'sp500_return': {
        'mu': 7.5,            # 年化预期收益（%）
        'theta': 0.10,
        'sigma': 18.0,        # 年化波动率
        'omega': 0.00002,
        'alpha': 0.085,       # S&P500 GARCH参数（历史标定）
        'beta': 0.910,
        'lambda_jump': 0.15,
        'mu_jump': -8.0,      # 负向跳跃（股灾冲击）
        'sigma_jump': 6.0,
        'min_val': -80.0,
        'max_val': 60.0,
    },
    'china_gdp': {
        'mu': 5.0,
        'theta': 0.30,
        'sigma': 2.0,
        'omega': 0.004,
        'alpha': 0.10,
        'beta': 0.84,
        'lambda_jump': 0.08,
        'mu_jump': -3.0,      # 中国GDP跳跃冲击（%）
        'sigma_jump': 2.0,
        'min_val': -8.0,
        'max_val': 15.0,
    },
}

DT = 1 / 12  # 月度步长（年）


# ============================================================
# 相关性矩阵（变量间协同运动）
# ============================================================

def _build_correlation_matrix(regime='normal'):
    """
    构建变量间相关性矩阵
    regime='normal'（常态）或 'crisis'（危机期，相关性增强）
    """
    if regime == 'normal':
        # 行/列顺序：gdp, inflation, unemployment, ffr, vix, sp500, china_gdp
        corr = np.array([
            [1.0,  0.3,  -0.6,  0.2,  -0.5,  0.5,   0.4],   # gdp
            [0.3,  1.0,  -0.2,  0.6,  -0.2,  -0.1,  0.1],   # inflation
            [-0.6, -0.2,  1.0,  -0.3,  0.5,  -0.6,  -0.3],  # unemployment
            [0.2,  0.6,  -0.3,  1.0,  -0.3,  -0.2,  0.1],   # ffr
            [-0.5, -0.2,  0.5,  -0.3,  1.0,  -0.7,  -0.4],  # vix
            [0.5,  -0.1, -0.6, -0.2,  -0.7,  1.0,   0.3],   # sp500
            [0.4,  0.1,  -0.3,  0.1,  -0.4,  0.3,   1.0],   # china_gdp
        ])
    else:  # crisis
        # 危机期：相关性收敛（普遍绝对值增大）
        corr = np.array([
            [1.0,  0.4,  -0.75, 0.3,  -0.7,  0.7,   0.55],
            [0.4,  1.0,  -0.3,  0.7,  -0.3,  -0.2,  0.15],
            [-0.75,-0.3,  1.0,  -0.4,  0.7,  -0.8,  -0.5],
            [0.3,  0.7,  -0.4,  1.0,  -0.4,  -0.3,  0.15],
            [-0.7, -0.3,  0.7,  -0.4,  1.0,  -0.85, -0.55],
            [0.7,  -0.2, -0.8, -0.3,  -0.85, 1.0,   0.5],
            [0.55, 0.15, -0.5,  0.15, -0.55, 0.5,   1.0],
        ])
    # 保证正定性
    eigvals = np.linalg.eigvalsh(corr)
    if eigvals.min() < 0:
        corr += (-eigvals.min() + 1e-6) * np.eye(len(VARIABLES))
    return corr


# ============================================================
# 核心模拟引擎
# ============================================================

class MonteCarloV2:
    """
    增强型蒙特卡洛模拟器（v2）
    支持：GBM / 跳跃扩散 / GARCH / GARCH+跳跃
    """

    def __init__(
        self,
        model: Literal['gbm', 'jump', 'garch', 'garch_jump'] = 'garch_jump',
        n_paths: int = 5000,
        horizon: int = 24,
        seed: Optional[int] = None,
    ):
        self.model = model
        self.n_paths = n_paths
        self.horizon = horizon
        self.rng = np.random.default_rng(seed)

    def _cholesky(self, vix_current: float) -> np.ndarray:
        """根据当前VIX决定使用常态或危机相关性矩阵，迭代扰动确保正定性。"""
        regime = 'crisis' if vix_current > 25 else 'normal'
        corr = _build_correlation_matrix(regime)
        eps = 1e-6
        for _ in range(10):
            try:
                return np.linalg.cholesky(corr)
            except np.linalg.LinAlgError:
                corr += eps * np.eye(len(VARIABLES))
                eps *= 10
        # 兜底：对角矩阵（放弃相关性，保证不崩溃）
        print("[MC] Cholesky分解失败，回退对角矩阵（相关性丢失）")
        return np.eye(len(VARIABLES))

    def _get_params(self, vix_current: float) -> Dict:
        """
        VIX>25 时对衰退敏感变量切换危机档 OU 参数：
          - lambda_jump × 3：经济冲击频率上升
          - theta × 0.5：均值回归减慢（坏状态持续更久）
          - mu_jump × 1.5（仅负向跳跃变量）：冲击幅度加大
        其他变量保持基准参数不变。
        """
        import copy
        params = copy.deepcopy(PARAMS)
        if vix_current <= 25:
            return params

        # 衰退敏感变量
        crisis_vars = {
            'gdp_growth':    {'lambda_jump': 3.0, 'theta': 0.5, 'mu_jump': 1.5},
            'unemployment':  {'lambda_jump': 3.0, 'theta': 0.5},
            'sp500_return':  {'lambda_jump': 3.0, 'theta': 0.5, 'mu_jump': 1.5},
        }
        for var, multipliers in crisis_vars.items():
            p = params[var]
            p['lambda_jump'] *= multipliers['lambda_jump']
            p['theta']       *= multipliers['theta']
            if 'mu_jump' in multipliers and p['mu_jump'] < 0:
                p['mu_jump'] *= multipliers['mu_jump']

        return params

    def run(self, initial_state: Dict[str, float]) -> Dict:
        """
        执行蒙特卡洛模拟

        Args:
            initial_state: 当前宏观变量值字典，键必须包含VARIABLES中的变量

        Returns:
            包含路径统计和概率指标的字典
        """
        n_vars = len(VARIABLES)
        var_index = {v: i for i, v in enumerate(VARIABLES)}

        # 根据初始VIX选择参数档位（常态 or 危机）
        vix_current = initial_state.get('vix', 18.0)
        params = self._get_params(vix_current)

        # 初始化路径存储 [path, time_step, variable]
        paths = np.zeros((self.n_paths, self.horizon + 1, n_vars))
        for j, var in enumerate(VARIABLES):
            paths[:, 0, j] = initial_state.get(var, params[var]['mu'])

        # GARCH方差初始化
        sigma2 = np.zeros((self.n_paths, n_vars))
        for j, var in enumerate(VARIABLES):
            sigma2[:, j] = params[var].get('sigma', 1.0) ** 2

        # GARCH残差历史（存储上一步的 σ·z，用于下一步 eps_prev；初始化为0）
        eps_paths = np.zeros((self.n_paths, n_vars))

        # Cholesky分解（基于初始VIX）
        L = self._cholesky(vix_current)

        for t in range(self.horizon):
            # 生成相关标准正态随机数 [n_paths, n_vars]
            raw_z = self.rng.standard_normal((self.n_paths, n_vars))
            corr_z = raw_z @ L.T  # 施加相关性

            current = paths[:, t, :]  # [n_paths, n_vars]

            for j, var in enumerate(VARIABLES):
                p = params[var]
                x = current[:, j]

                # ---- Step 1: 计算当前步长波动率 ----
                if self.model in ('garch', 'garch_jump'):
                    eps_prev = eps_paths[:, j]  # 上一步实际残差（σ·z），而非状态偏离均值
                    sigma2[:, j] = (
                        p['omega']
                        + p['alpha'] * eps_prev ** 2
                        + p['beta'] * sigma2[:, j]
                    )
                    sigma2[:, j] = np.maximum(sigma2[:, j], 1e-8)
                    sigma = np.sqrt(sigma2[:, j])
                else:
                    sigma = np.full(self.n_paths, p['sigma'])

                # ---- Step 2: OU均值回归漂移 ----
                drift = p['theta'] * (p['mu'] - x) * DT

                # ---- Step 3: 扩散项 ----
                diffusion = sigma * np.sqrt(DT) * corr_z[:, j]
                if self.model in ('garch', 'garch_jump'):
                    eps_paths[:, j] = sigma * corr_z[:, j]  # 保存本步残差（σ·z，不含DT）

                # ---- Step 4: 跳跃项 ----
                jump = np.zeros(self.n_paths)
                if self.model in ('jump', 'garch_jump'):
                    n_jumps = self.rng.poisson(p['lambda_jump'] * DT, self.n_paths)
                    jump_mask = n_jumps > 0
                    if jump_mask.any():
                        jump_sizes = self.rng.normal(
                            p['mu_jump'], p['sigma_jump'],
                            jump_mask.sum()
                        )
                        jump[jump_mask] = jump_sizes * n_jumps[jump_mask]

                # ---- Step 5: 合并并施加边界 ----
                x_new = x + drift + diffusion + jump
                x_new = np.clip(x_new, p['min_val'], p['max_val'])
                paths[:, t + 1, j] = x_new

        return self._summarize(paths, var_index)

    def _summarize(self, paths: np.ndarray, var_index: Dict) -> Dict:
        """计算分位数、概率指标等统计量"""
        result = {}

        # 各变量分位数
        for var in VARIABLES:
            j = var_index[var]
            final_vals = paths[:, -1, j]
            result[var] = {
                'median': float(np.percentile(final_vals, 50)),
                'p10': float(np.percentile(final_vals, 10)),
                'p25': float(np.percentile(final_vals, 25)),
                'p75': float(np.percentile(final_vals, 75)),
                'p90': float(np.percentile(final_vals, 90)),
                'mean': float(np.mean(final_vals)),
                'std': float(np.std(final_vals)),
                'path_median': [
                    float(np.percentile(paths[:, t, j], 50))
                    for t in range(paths.shape[1])
                ],
            }

        # ---- 宏观情景概率 ----
        gdp_j = var_index['gdp_growth']
        unemp_j = var_index['unemployment']
        infl_j = var_index['inflation']
        vix_j = var_index['vix']

        final_gdp = paths[:, -1, gdp_j]
        peak_unemp = paths[:, :, unemp_j].max(axis=1)
        final_infl = paths[:, -1, infl_j]
        peak_vix = paths[:, :, vix_j].max(axis=1)

        # 衰退：GDP持续2季度负增长
        any_negative_gdp = (paths[:, :, gdp_j] < 0).sum(axis=1) >= 2
        result['probabilities'] = {
            'recession': float(np.mean(any_negative_gdp)),
            'deep_recession': float(np.mean(final_gdp < -3.0)),
            'soft_landing': float(np.mean(
                (final_gdp > 1.5) & (peak_unemp < 5.5) & (final_infl < 3.0)
            )),
            'stagflation': float(np.mean(
                (final_gdp < 1.0) & (final_infl > 4.0)
            )),
            'crisis_vix': float(np.mean(peak_vix > 40)),
            'high_inflation': float(np.mean(final_infl > 5.0)),
            'deflation_risk': float(np.mean(final_infl < 0.5)),
        }

        result['model_used'] = self.model
        result['n_paths'] = self.n_paths
        result['horizon_months'] = self.horizon

        return result


# ============================================================
# 便捷接口
# ============================================================

def run_monte_carlo_v2(
    current_metrics: Dict,
    n_paths: int = 5000,
    horizon: int = 24,
    model: str = 'garch_jump',
    seed: Optional[int] = 42,
    save_path: Optional[str] = None,
) -> Dict:
    """
    一键运行增强型蒙特卡洛模拟

    Args:
        current_metrics: 当前宏观指标（从run_macro_analysis.py输出获取）
        n_paths: 模拟路径数（默认5000）
        horizon: 预测期（月，默认24个月=2年）
        model: 模型类型 'gbm'|'jump'|'garch'|'garch_jump'
        seed: 随机种子（None=不固定）
        save_path: 结果保存路径（JSON格式，None=不保存）

    Returns:
        包含各变量分位数和情景概率的字典
    """
    sim = MonteCarloV2(model=model, n_paths=n_paths, horizon=horizon, seed=seed)
    result = sim.run(current_metrics)

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存至: {save_path}")

    return result


def compare_models(current_metrics: Dict, n_paths: int = 2000) -> Dict:
    """
    对比4种模型的结果差异，用于评估v2相对v1的改进
    """
    comparison = {}
    for model in ['gbm', 'jump', 'garch', 'garch_jump']:
        result = run_monte_carlo_v2(
            current_metrics, n_paths=n_paths,
            model=model, seed=42
        )
        comparison[model] = {
            'recession_prob': result['probabilities']['recession'],
            'soft_landing_prob': result['probabilities']['soft_landing'],
            'gdp_p10': result['gdp_growth']['p10'],
            'gdp_p90': result['gdp_growth']['p90'],
            'vix_crisis_prob': result['probabilities']['crisis_vix'],
        }

    # 打印对比表
    print("\n==== 模型对比（衰退概率 & 软着陆概率）====")
    print(f"{'模型':^15} {'衰退概率':^10} {'软着陆':^10} {'GDP_P10':^10} {'GDP_P90':^10}")
    print("-" * 60)
    for model, metrics in comparison.items():
        print(
            f"{model:^15} "
            f"{metrics['recession_prob']:.1%}   "
            f"{metrics['soft_landing_prob']:.1%}   "
            f"{metrics['gdp_p10']:+.2f}%   "
            f"{metrics['gdp_p90']:+.2f}%"
        )

    return comparison


# ============================================================
# 主程序（独立测试）
# ============================================================

if __name__ == '__main__':
    print("=== monte_carlo_v2.py 独立测试 ===\n")

    # 测试用当前指标（2026年5月假设值）
    test_metrics = {
        'gdp_growth': 2.1,
        'inflation': 3.0,
        'unemployment': 4.2,
        'fed_funds_rate': 4.5,
        'vix': 20,
        'sp500_return': 12.0,
        'china_gdp': 4.8,
    }

    print("当前输入指标:")
    for k, v in test_metrics.items():
        print(f"  {k}: {v}")

    print("\n--- 运行 GARCH+跳跃扩散模型（5000路径，24个月）---")
    result = run_monte_carlo_v2(
        test_metrics,
        n_paths=5000,
        horizon=24,
        model='garch_jump',
    )

    print("\n== 情景概率 ==")
    for key, val in result['probabilities'].items():
        print(f"  {key:25s}: {val:.1%}")

    print("\n== GDP增速预测（12个月后）==")
    gdp = result['gdp_growth']
    print(f"  P10: {gdp['p10']:.2f}%  P25: {gdp['p25']:.2f}%  中位: {gdp['median']:.2f}%  P75: {gdp['p75']:.2f}%  P90: {gdp['p90']:.2f}%")

    print("\n--- 对比4种模型差异 ---")
    compare_models(test_metrics, n_paths=1000)

    print("\n✅ monte_carlo_v2.py 测试完成")


# ============================================================
# v1 兼容层 — 返回 run_macro_analysis.py 期望的格式
# ============================================================

def run_monte_carlo_compat(indicators: Dict, coeffs: Dict = None,
                           n_sim: int = 5000, n_months: int = 12) -> Dict:
    """
    v1 兼容接口。
    输入/输出格式与 run_macro_analysis.py 的 run_monte_carlo() 完全一致，
    内部使用 GARCH+跳跃扩散模型替代原始 GBM。

    参数:
        indicators: run_macro_analysis.py 的指标字典
            例: {'GDPC1': {'value': 2.1}, 'CPIAUCSL': {'value': 3.0},
                 'UNRATE': {'value': 4.2}, 'FEDFUNDS': {'value': 4.5}, ...}
        coeffs: 体制系数（v2内部自行决定体制，此参数保留但未使用）
        n_sim: 模拟路径数
        n_months: 预测月数

    返回:
        v1 格式字典:
        {
            'recession_prob': float,  # 衰退概率 (%)
            'gdp': {'mean': float, 'p5': float, 'p95': float},
            'unrate': {'mean': float, 'p5': float, 'p95': float},
            'sp500': {'mean': float, 'p5': float, 'p95': float},
            'feedback': {},
        }
    """
    def _get(keys):
        """从 indicators 中依次尝试多个键取值"""
        for k in keys:
            v = indicators.get(k, {})
            if isinstance(v, dict):
                val = v.get('value')
            else:
                val = v
            if val is not None:
                return float(val)
        return None

    # 构建 v2 所需的 metrics
    # VIX 在 run_macro_analysis 里存为 "VIX"，scan_weak_signals 里存为 "VIXCLS"，都兼容
    sp500_raw = _get(['SP500', 'sp500_return'])
    # SP500 若为价格水平（>100），转换为近似年化收益率；若已是收益率直接使用
    if sp500_raw and sp500_raw > 100:
        sp500_return = 7.0   # 价格水平无法在单点推算收益率，用长期历史均值兜底
    else:
        sp500_return = sp500_raw or 7.0

    metrics = {
        'gdp_growth':    _get(['GDPC1', 'gdp_growth']) or 2.5,
        'inflation':     _get(['CPIAUCSL', 'cpi', 'inflation']) or 3.0,
        'unemployment':  _get(['UNRATE', 'unemployment']) or 4.3,
        'fed_funds_rate': _get(['FEDFUNDS', 'DFF', 'fed_funds_rate']) or 5.0,
        'vix':           _get(['VIXCLS', 'VIX', 'vix']) or 20.0,   # 兼容三种 key
        'sp500_return':  sp500_return,
        'china_gdp':     5.0,   # US模拟不传入中国数据，使用合理默认值
    }

    result = run_monte_carlo_v2(
        current_metrics=metrics,
        n_paths=n_sim,
        horizon=n_months,
        model='garch_jump',
    )

    probs = result.get('probabilities', {})
    gdp = result.get('gdp_growth', {})
    unrate = result.get('unemployment', {})
    sp500 = result.get('sp500_return', {})
    inflation = result.get('inflation', {})

    # 季度路径分位数（从 path_median 中提取3/6/12/24个月节点）
    def _quarterly_path(var_key, milestones=(3, 6, 12)):
        path = result.get(var_key, {}).get('path_median', [])
        out = {}
        for m in milestones:
            if m < len(path):
                out[f"m{m}"] = round(path[m], 2)
        return out

    quarterly = {
        'gdp':    _quarterly_path('gdp_growth'),
        'cpi':    _quarterly_path('inflation'),
        'unrate': _quarterly_path('unemployment'),
    }

    return {
        'recession_prob': round(probs.get('recession', 0) * 100, 1),
        'crisis_state_pct': round(probs.get('crisis_vix', 0) * 100, 1),
        'calibrated': _CAL_AVAILABLE,
        'regime_probs': {                          # 完整5体制概率（原始分数，供forecast_tracker使用）
            'recession':      round(probs.get('recession', 0), 4),
            'deep_recession': round(probs.get('deep_recession', 0), 4),
            'soft_landing':   round(probs.get('soft_landing', 0), 4),
            'stagflation':    round(probs.get('stagflation', 0), 4),
            'crisis_vix':     round(probs.get('crisis_vix', 0), 4),
        },
        'gdp': {
            'mean': round(gdp.get('median', 2.0), 2),
            'p5': round(gdp.get('p10', 0.0), 2),
            'p95': round(gdp.get('p90', 4.0), 2),
        },
        'unrate': {
            'mean': round(unrate.get('median', 4.5), 2),
            'p5': round(unrate.get('p10', 3.5), 2),
            'p95': round(unrate.get('p90', 6.0), 2),
        },
        'cpi': {
            'mean': round(inflation.get('median', 3.0), 2),
            'p5':   round(inflation.get('p10',   2.0), 2),
            'p95':  round(inflation.get('p90',   5.0), 2),
        },
        'sp500': {
            'mean': round(sp500.get('median', 7.0), 1),
            'p5': round(sp500.get('p10', -20.0), 1),
            'p95': round(sp500.get('p90', 25.0), 1),
        },
        'quarterly': quarterly,
        'feedback': {},
    }
