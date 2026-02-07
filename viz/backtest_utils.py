"""
Shared utilities for backtest visualization pages.

This module contains common functions used across multiple backtest pages:
- Data resampling (intraday to daily)
- Statistics calculations
- Volatility rescaling
- Ridge aggregation (forward return combination)
- Common constants
"""

import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import RidgeCV
except ImportError:
    RidgeCV = None
try:
    from sklearn.cross_decomposition import PLSRegression
except ImportError:
    PLSRegression = None

# Constants (crypto 24/7: use 360 days per year)
TRADING_DAYS = 360  # Days per year for annualized statistics
TRADING_HOURS_PER_YEAR = 24 * 360  # 8640 hours (intraday position sizing)
VOL_FLOOR = 1e-8
# Cost: 15 bps per trip for cost-adjusted metrics
COST_BPS_PER_TRIP = 15


# ============================================================================
# Data Resampling
# ============================================================================

def resample_pnl_to_daily(pnl_series: pd.Series, dates: pd.Series) -> pd.Series:
    """
    Resample intraday PnL to daily by summing PnL within each day.
    
    PnL is additive, so we sum all intraday PnL values within each calendar day.
    This is necessary because:
    1. PnL is additive (sum of hourly PnL = daily PnL)
    2. Statistics should be calculated on daily data for meaningful annualization
    3. Avoids inflated Sharpe ratios from high-frequency data
    
    Args:
        pnl_series: Intraday PnL series (e.g., hourly PnL from 5m data)
        dates: Corresponding datetime series (must be datetime-like, e.g., pd.Timestamp)
    
    Returns:
        Daily PnL series (sum of intraday PnL per day)
    
    Example:
        # Hourly PnL: [0.001, 0.002, -0.001, 0.003, ...] (24 values per day)
        # Daily PnL: [0.025, ...] (sum of 24 hourly values)
    """
    df = pd.DataFrame({'date': dates, 'pnl': pnl_series})
    df['date_only'] = pd.to_datetime(df['date']).dt.date
    daily_pnl = df.groupby('date_only', as_index=False).agg(pnl=('pnl', 'sum'))
    return daily_pnl['pnl'].reset_index(drop=True)


def prepare_daily_stats_series(
    pnl1: pd.Series,
    pnl2: pd.Series,
    pnl3: pd.Series,
    pnl_avg: pd.Series,
    pnl_reg: pd.Series,
    ret_scaled: pd.Series,
    dates: pd.Series,
) -> tuple:
    """
    Prepare daily series for statistics calculation.
    
    Checks if data is intraday and resamples to daily if needed.
    Returns tuple of (pnl1_for_stats, pnl2_for_stats, pnl3_for_stats, 
                     pnl_avg_for_stats, pnl_reg_for_stats, ret_scaled_for_stats)
    
    Args:
        pnl1, pnl2, pnl3: Strategy PnL series
        pnl_avg: Average strategy PnL series
        pnl_reg: Regression-combined strategy PnL series
        ret_scaled: Scaled raw return series
        dates: Corresponding datetime series
    
    Returns:
        Tuple of 6 Series (all daily, ready for statistics)
    """
    # Check if data is intraday (hourly from 5m)
    is_intraday = len(pnl1) > 252 or isinstance(
        dates.iloc[0] if hasattr(dates, 'iloc') else dates[0], pd.Timestamp
    )
    
    if is_intraday:
        # Resample to daily before statistics
        pnl1_daily = resample_pnl_to_daily(pnl1, dates)
        pnl2_daily = resample_pnl_to_daily(pnl2, dates)
        pnl3_daily = resample_pnl_to_daily(pnl3, dates)
        pnl_avg_daily = resample_pnl_to_daily(pnl_avg, dates)
        pnl_reg_daily = resample_pnl_to_daily(pnl_reg, dates)
        ret_scaled_daily = resample_pnl_to_daily(ret_scaled, dates)
        
        return (
            pnl1_daily,
            pnl2_daily,
            pnl3_daily,
            pnl_avg_daily,
            pnl_reg_daily,
            ret_scaled_daily,
        )
    else:
        # Already daily or lower frequency, use as-is
        return (pnl1, pnl2, pnl3, pnl_avg, pnl_reg, ret_scaled)


# ============================================================================
# Ridge Aggregation (forward return combination)
# ============================================================================

# Forward return horizons: hourly backtests use 24h/48h/96h/192h; daily backtests use 1d/5d/10d/30d
RIDGE_HORIZONS_HOURLY = (24, 48, 96, 192)   # periods (hours)
RIDGE_LABELS_HOURLY = ("24h", "48h", "96h", "192h")
RIDGE_HORIZONS_DAILY = (1, 5, 10, 30)       # periods (days)
RIDGE_LABELS_DAILY = ("1d", "5d", "10d", "30d")


def ridge_aggregation(
    pos1: pd.Series,
    pos2: pd.Series,
    pos3: pd.Series,
    ret: pd.Series,
    vol_ewm_span: int = 30,
    is_intraday_hourly: bool = False,
    train_fraction: float = 0.5,
    min_samples: int = 10,
) -> tuple[np.ndarray, list[np.ndarray], tuple[str, ...]]:
    """
    Combine three position series using Ridge regression on forward vol-normalized returns.

    For each forward horizon, fits: y = forward_return / vol ~ X @ beta, where X = [pos1, pos2, pos3].
    Training uses first half of data only; RidgeCV 5-fold for alpha. Returns average of the 4 betas.

    - **Hourly data**: forward horizons 24h, 48h, 96h, 192h (labels "24h", "48h", "96h", "192h").
    - **Daily (EOD) data**: forward horizons 1d, 5d, 10d, 30d (labels "1d", "5d", "10d", "30d").

    Args:
        pos1, pos2, pos3: Position series (same length as ret).
        ret: Return series.
        vol_ewm_span: EWM span for volatility estimate.
        is_intraday_hourly: If True, use 24h/48h/96h/192h horizons; if False, use 1d/5d/10d/30d.
        train_fraction: Fraction of valid data used for training (default 0.5).
        min_samples: Minimum samples to fit Ridge; otherwise use equal weights.

    Returns:
        beta_reg: Average of 4 horizon betas, shape (3,).
        betas: List of 4 coefficient arrays, one per horizon.
        horizon_labels: Tuple of 4 strings for display (e.g. ("24h", "48h", "96h", "192h")).
    """
    if RidgeCV is None:
        default_beta = np.array([1.0 / 3, 1.0 / 3, 1.0 / 3])
        if is_intraday_hourly:
            return default_beta, [default_beta] * 4, RIDGE_LABELS_HOURLY
        return default_beta, [default_beta] * 4, RIDGE_LABELS_DAILY

    vol_ret = ret.ewm(span=vol_ewm_span, adjust=False).std().clip(lower=VOL_FLOOR)
    X = np.column_stack([pos1.values, pos2.values, pos3.values])
    default_beta = np.array([1.0 / 3, 1.0 / 3, 1.0 / 3])

    if is_intraday_hourly:
        horizons = RIDGE_HORIZONS_HOURLY
        labels = RIDGE_LABELS_HOURLY
    else:
        horizons = RIDGE_HORIZONS_DAILY
        labels = RIDGE_LABELS_DAILY

    betas = []
    for horizon in horizons:
        fwd_ret = ret.rolling(horizon).sum().shift(-horizon)
        vol_h = vol_ret * np.sqrt(horizon)
        y_h = (fwd_ret / vol_h).replace([np.inf, -np.inf], np.nan).values
        valid = ~(np.isnan(X).any(axis=1) | np.isnan(y_h))
        X_v, y_v = X[valid], y_h[valid]
        if X_v.shape[0] > min_samples:
            split_idx = int(X_v.shape[0] * train_fraction)
            X_train, y_train = X_v[:split_idx], y_v[:split_idx]
            ridge = RidgeCV(cv=5, alphas=np.logspace(-6, 6, 13))
            ridge.fit(X_train, y_train)
            betas.append(ridge.coef_)
        else:
            betas.append(default_beta)

    beta_reg = (np.array(betas[0]) + np.array(betas[1]) + np.array(betas[2]) + np.array(betas[3])) / 4
    return beta_reg, betas, labels


def ridge_aggregation_multi(
    positions: list[pd.Series],
    ret: pd.Series,
    vol_ewm_span: int = 30,
    is_intraday_hourly: bool = False,
    train_fraction: float = 0.5,
    min_samples: int = 10,
) -> tuple[np.ndarray, list[np.ndarray], tuple[str, ...]]:
    """
    Combine N position series using Ridge regression on forward vol-normalized returns.

    Same logic as ridge_aggregation but accepts arbitrary number of position series.

    Returns:
        beta_reg: Average of 4 horizon betas, shape (N,).
        betas: List of 4 coefficient arrays, one per horizon.
        horizon_labels: Tuple of 4 strings for display.
    """
    n = len(positions)
    if n == 0:
        raise ValueError("positions must not be empty")
    default_beta = np.ones(n) / n
    if RidgeCV is None:
        if is_intraday_hourly:
            return default_beta, [default_beta] * 4, RIDGE_LABELS_HOURLY
        return default_beta, [default_beta] * 4, RIDGE_LABELS_DAILY

    vol_ret = ret.ewm(span=vol_ewm_span, adjust=False).std().clip(lower=VOL_FLOOR)
    X = np.column_stack([p.values for p in positions])

    if is_intraday_hourly:
        horizons = RIDGE_HORIZONS_HOURLY
        labels = RIDGE_LABELS_HOURLY
    else:
        horizons = RIDGE_HORIZONS_DAILY
        labels = RIDGE_LABELS_DAILY

    betas = []
    for horizon in horizons:
        fwd_ret = ret.rolling(horizon).sum().shift(-horizon)
        vol_h = vol_ret * np.sqrt(horizon)
        y_h = (fwd_ret / vol_h).replace([np.inf, -np.inf], np.nan).values
        valid = ~(np.isnan(X).any(axis=1) | np.isnan(y_h))
        X_v, y_v = X[valid], y_h[valid]
        if X_v.shape[0] > min_samples:
            split_idx = int(X_v.shape[0] * train_fraction)
            X_train, y_train = X_v[:split_idx], y_v[:split_idx]
            ridge = RidgeCV(cv=5, alphas=np.logspace(-6, 6, 13))
            ridge.fit(X_train, y_train)
            betas.append(ridge.coef_)
        else:
            betas.append(default_beta)

    beta_reg = np.mean(betas, axis=0)
    return beta_reg, betas, labels


def pls_aggregation_multi(
    positions: list[pd.Series],
    ret: pd.Series,
    vol_ewm_span: int = 30,
    is_intraday_hourly: bool = False,
    train_fraction: float = 0.5,
    min_samples: int = 10,
    n_components: int | None = None,
) -> tuple[np.ndarray, list[np.ndarray], tuple[str, ...]]:
    """
    Combine N position series using PLS regression on forward vol-normalized returns.
    Same structure as ridge_aggregation_multi: 4 horizons, train on first fraction, average betas.

    Returns:
        beta_pls: Average of 4 horizon coefficient arrays, shape (N,).
        betas: List of 4 coefficient arrays, one per horizon.
        horizon_labels: Tuple of 4 strings for display.
    """
    n = len(positions)
    if n == 0:
        raise ValueError("positions must not be empty")
    default_beta = np.ones(n) / n
    if PLSRegression is None:
        if is_intraday_hourly:
            return default_beta, [default_beta] * 4, RIDGE_LABELS_HOURLY
        return default_beta, [default_beta] * 4, RIDGE_LABELS_DAILY

    vol_ret = ret.ewm(span=vol_ewm_span, adjust=False).std().clip(lower=VOL_FLOOR)
    X = np.column_stack([p.values for p in positions])

    if is_intraday_hourly:
        horizons = RIDGE_HORIZONS_HOURLY
        labels = RIDGE_LABELS_HOURLY
    else:
        horizons = RIDGE_HORIZONS_DAILY
        labels = RIDGE_LABELS_DAILY

    n_comp = n_components if n_components is not None else min(10, n - 1, 50)
    n_comp = max(1, min(n_comp, n - 1))

    betas = []
    for horizon in horizons:
        fwd_ret = ret.rolling(horizon).sum().shift(-horizon)
        vol_h = vol_ret * np.sqrt(horizon)
        y_h = (fwd_ret / vol_h).replace([np.inf, -np.inf], np.nan).values
        valid = ~(np.isnan(X).any(axis=1) | np.isnan(y_h))
        X_v, y_v = X[valid], y_h[valid]
        if X_v.shape[0] > min_samples:
            split_idx = int(X_v.shape[0] * train_fraction)
            X_train, y_train = X_v[:split_idx], y_v[:split_idx]
            pls = PLSRegression(n_components=n_comp)
            pls.fit(X_train, y_train)
            betas.append(pls.coef_.ravel())
        else:
            betas.append(default_beta)

    beta_pls = np.mean(betas, axis=0)
    return beta_pls, betas, labels


# ============================================================================
# Volatility Rescaling
# ============================================================================

def rescale_to_target_vol(
    pnl_series: pd.Series,
    pos_series: pd.Series | None,
    target_vol_ann: float,
    is_intraday: bool = False,
) -> tuple[pd.Series, pd.Series | None]:
    """
    Rescale PnL and position series to match target annualized volatility.
    
    Args:
        pnl_series: PnL series to rescale
        pos_series: Position series to rescale (optional)
        target_vol_ann: Target annualized volatility (e.g., 0.30 for 30%)
        is_intraday: If True, uses hourly scaling; if False, uses daily scaling
    
    Returns:
        Tuple of (pnl_scaled, pos_scaled)
    """
    if is_intraday:
        target_vol_period = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    else:
        target_vol_period = target_vol_ann / np.sqrt(TRADING_DAYS)
    
    sd = pnl_series.std()
    scale = target_vol_period / sd if sd > VOL_FLOOR else 1.0
    pnl_scaled = pnl_series * scale
    pos_scaled = pos_series * scale if pos_series is not None else None
    return pnl_scaled, pos_scaled


# ============================================================================
# Statistics Helper Functions
# ============================================================================

def level_from_log(cumlog: pd.Series) -> pd.Series:
    """
    Convert cumulative log returns to level (price-like series).
    
    Args:
        cumlog: Cumulative log return series
    
    Returns:
        Level series: exp(cumlog) - 1
    """
    return np.exp(cumlog) - 1


def max_drawdown(cumlog: pd.Series) -> float:
    """
    Maximum drawdown from cumulative log returns: peak cumlog - trough cumlog.
    
    Args:
        cumlog: Cumulative log return series
    
    Returns:
        Maximum drawdown in log space, scaled by 100 (e.g., 15.5 for 0.155 log)
    """
    peak = cumlog.cummax()
    dd = peak - cumlog
    return float(dd.max()) * 100


def avg_drawdown(cumlog: pd.Series) -> float:
    """
    Average drawdown from cumulative log returns: peak cumlog - cumlog at each time.
    
    Args:
        cumlog: Cumulative log return series
    
    Returns:
        Average drawdown in log space, scaled by 100
    """
    peak = cumlog.cummax()
    dd = peak - cumlog
    return float(dd.mean()) * 100


def alpha_beta(pnl: pd.Series, bench: pd.Series, trading_days: int = TRADING_DAYS) -> tuple[float, float]:
    """
    Calculate alpha and beta relative to benchmark.
    
    Expects daily data (already resampled from intraday if needed).
    
    Args:
        pnl: Strategy PnL series (daily)
        bench: Benchmark return series (daily)
        trading_days: Number of trading days per year (default 252)
    
    Returns:
        Tuple of (alpha_annualized, beta)
    """
    m = pnl.notna() & bench.notna()
    p = pnl[m].values
    b = bench[m].values
    if len(p) < 2 or b.var() == 0:
        return np.nan, np.nan
    beta = np.cov(p, b)[0, 1] / b.var()
    alpha = p.mean() - beta * b.mean()
    return alpha * trading_days, beta


def cvar95(series: pd.Series) -> float:
    """
    Conditional Value at Risk (CVaR) at 95% confidence level.
    Also known as Expected Shortfall (ES). Returns the expected loss given that
    loss exceeds the 95% VaR threshold.
    
    Args:
        series: Return/PnL series
    
    Returns:
        CVaR95 as percentage
    """
    q = series.quantile(0.05)
    return float(series[series <= q].mean()) * 100


def es95(series: pd.Series) -> float:
    """
    Expected Shortfall (ES) at 95% - same as CVaR95.
    
    Args:
        series: Return/PnL series
    
    Returns:
        ES95 as percentage
    """
    return cvar95(series)


def cdd95(cumlog: pd.Series) -> float:
    """
    Conditional Drawdown at Risk (CDD) at 95%: expected drawdown when drawdown >= 95th percentile.
    Drawdown = peak cumlog - cumlog.
    
    Args:
        cumlog: Cumulative log return series
    
    Returns:
        CDD95 in log space, scaled by 100
    """
    peak = cumlog.cummax()
    drawdown = peak - cumlog
    q = drawdown.quantile(0.95)
    return float(drawdown[drawdown >= q].mean()) * 100


def kurtosis_monthly(series: pd.Series, trading_days: int = TRADING_DAYS) -> float:
    """
    Calculate monthly kurtosis.
    
    Aggregates daily returns to monthly, then calculates kurtosis.
    Expects daily data (already resampled from intraday if needed).
    
    Args:
        series: Daily return/PnL series
        trading_days: Number of trading days per year (default 252)
    
    Returns:
        Kurtosis of monthly returns
    """
    if len(series) > 30:
        if isinstance(series.index, pd.DatetimeIndex):
            monthly_ret = series.resample('M').sum()
        else:
            monthly_ret = series.groupby(series.index // (trading_days // 12)).sum()
    else:
        monthly_ret = series
    return float(monthly_ret.kurtosis())


def sortino_ratio(
    pnl: pd.Series,
    risk_free_rate: float = 0.0,
    trading_days: int = TRADING_DAYS,
) -> float:
    """
    Sortino ratio: excess return / downside deviation.
    
    Uses only negative returns for volatility calculation.
    Expects daily data (already resampled from intraday if needed).
    
    Args:
        pnl: Daily PnL series
        risk_free_rate: Risk-free rate (annualized, default 0.0)
        trading_days: Number of trading days per year (default 252)
    
    Returns:
        Sortino ratio (float or np.inf if no downside)
    """
    excess_return = pnl.mean() * trading_days - risk_free_rate
    downside_returns = pnl[pnl < 0]
    if len(downside_returns) == 0:
        return np.inf if excess_return > 0 else np.nan
    downside_std = downside_returns.std() * np.sqrt(trading_days)
    return excess_return / downside_std if downside_std > VOL_FLOOR else np.nan


def hit_rate(pnl: pd.Series) -> float:
    """
    Hit rate: percentage of positive return periods.
    
    Args:
        pnl: PnL series
    
    Returns:
        Hit rate as percentage (e.g., 55.5 for 55.5%)
    """
    return float((pnl > 0).sum() / len(pnl)) * 100 if len(pnl) > 0 else np.nan


def profit_factor(pnl: pd.Series) -> float:
    """
    Profit factor: gross profit / gross loss.
    
    Ratio of sum of positive returns to absolute sum of negative returns.
    
    Args:
        pnl: PnL series
    
    Returns:
        Profit factor (float or np.inf if no losses)
    """
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    return float(gross_profit / gross_loss) if gross_loss > VOL_FLOOR else np.inf


def annual_turnover(position: pd.Series, is_intraday: bool = False) -> float:
    """
    Calculate annual turnover.

    Args:
        position: Position series
        is_intraday: If True, uses hourly scaling; if False, uses daily scaling

    Returns:
        Annual turnover
    """
    if is_intraday:
        return float(position.diff().abs().mean()) * TRADING_HOURS_PER_YEAR
    else:
        return float(position.diff().abs().mean()) * TRADING_DAYS


def buffer_position(
    position: pd.Series,
    factor: float = 5.0,
) -> pd.Series:
    """
    Buffer position: only update when the gap between target and buffered exceeds a threshold.
    The decision is based on (target - true position), not on step changes in target.

    - Gap = target[t] - buffered[t-1]. When we do not update, buffered stays fixed so the gap
      can accumulate as the target moves in later steps.
    - Threshold = factor × mean(|Δposition|). We update (set buffered[t] = target[t]) only when
      |gap| > threshold. Using average absolute change ties the rule to typical step size,
      so buffering has a visible effect on turnover.

    Args:
        position: Target position series
        factor: Threshold = factor × mean(|position.diff()|) (default 2.0)

    Returns:
        Buffered position series (same index as position)
    """
    arr = np.asarray(position, dtype=float)
    abs_changes = np.abs(np.diff(arr))
    avg_abs_change = np.nanmean(abs_changes)
    print(f"[buffer_position] avg_abs_change={avg_abs_change}")
    if avg_abs_change <= 0 or not np.isfinite(avg_abs_change):
        print("[buffer_position] early return: avg_abs_change <= 0 or not finite, returning position unchanged")
        return pd.Series(arr, index=position.index)
    threshold = float(factor * avg_abs_change)
    out = arr.copy()
    for i in range(1, len(out)):
        if np.abs(arr[i] - out[i - 1]) <= threshold:
            out[i] = out[i - 1]
    return pd.Series(out, index=position.index)


def cost_metrics(
    ann_turnover: float,
    ann_vol_pct: float,
    sharpe: float,
    trading_days: int = TRADING_DAYS,
    cost_bps_per_trip: float = COST_BPS_PER_TRIP,
) -> dict:
    """
    Cost-adjusted metrics from turnover and vol/sharpe.

    - Holding period (days) = days_in_year / ann_turnover
    - Ann trading cost (%) = ann_turnover * (cost_bps_per_trip / 10000) * 100
    - Cost/vol = ann_cost_pct / ann_vol_pct
    - Net Sharpe = sharpe - cost_to_vol

    Args:
        ann_turnover: Annual turnover
        ann_vol_pct: Annualized vol in % (e.g. 20 for 20%)
        sharpe: Raw Sharpe ratio
        trading_days: Days per year (default TRADING_DAYS)
        cost_bps_per_trip: Cost in bps per round-trip (default 15)

    Returns:
        Dict with "Holding period (days)", "Ann cost (%)", "Cost/vol", "Net Sharpe"
    """
    if ann_turnover and ann_turnover > 0:
        holding_period_days = trading_days / ann_turnover
        ann_cost_pct = ann_turnover * (cost_bps_per_trip / 10000) * 100
    else:
        holding_period_days = np.nan
        ann_cost_pct = 0.0
    cost_to_vol = ann_cost_pct / ann_vol_pct if (ann_vol_pct and ann_vol_pct > 0) else np.nan
    net_sharpe = (float(sharpe) - cost_to_vol) if not np.isnan(sharpe) and not np.isnan(cost_to_vol) else np.nan
    if np.isnan(net_sharpe) and not np.isnan(sharpe) and (not ann_vol_pct or ann_vol_pct <= 0):
        net_sharpe = float(sharpe)
    return {
        "Holding period (days)": holding_period_days,
        "Ann cost (%)": ann_cost_pct,
        "Cost/vol": cost_to_vol if not np.isnan(cost_to_vol) else 0.0,
        "Net Sharpe": net_sharpe,
    }


# ============================================================================
# Main Statistics Builder
# ============================================================================

def build_stats(
    ret_series: pd.Series,
    is_raw: bool,
    trading_days: int = TRADING_DAYS,
    include_all_metrics: bool = True,
) -> dict:
    """
    Build comprehensive statistics dictionary.
    
    Enhanced build_stats with all metrics including CVaR95, CDD95, Sortino,
    Kurtosis, Hit Rate, and Profit Factor.
    Expects DAILY data (already resampled from intraday if needed).
    
    Args:
        ret_series: Daily return/PnL series (already resampled from intraday if needed)
        is_raw: True if raw returns (log returns), False if PnL series
        trading_days: Number of trading days per year (default 252)
        include_all_metrics: If True, includes all metrics; if False, includes only basic metrics
    
    Returns:
        Dictionary with statistics metrics
    """
    if is_raw:
        r = ret_series
        ann_ret = r.mean() * trading_days * 100
        ann_vol = r.std() * np.sqrt(trading_days) * 100
        cumlog = r.cumsum()
    else:
        r = ret_series
        ann_ret = r.mean() * trading_days * 100
        ann_vol = r.std() * np.sqrt(trading_days) * 100
        cumlog = np.log(1 + r).cumsum()
    
    sharpe = ann_ret / ann_vol if ann_vol else np.nan
    max_dd = max_drawdown(cumlog)
    calmar = ann_ret / max_dd if max_dd else np.nan
    avg_dd = avg_drawdown(cumlog)
    skew = float(r.skew()) if len(r) else np.nan
    
    stats = {
        "Ann return (%)": ann_ret,
        "Ann vol (%)": ann_vol,
        "Sharpe": sharpe,
        "Max DD (%)": max_dd,
        "Avg DD (%)": avg_dd,
        "Calmar": calmar,
        "Skewness": skew,
    }
    
    if include_all_metrics:
        stats.update({
            "Sortino": sortino_ratio(r, trading_days=trading_days),
            "CDD95 (%)": cdd95(cumlog),
            "Kurtosis (mth)": kurtosis_monthly(r, trading_days=trading_days),
            "CVaR95 (%)": cvar95(r),
            "Hit Rate (%)": hit_rate(r),
            "Profit Factor": profit_factor(r),
        })
    else:
        # For older backtests that use simpler stats
        stats["ES95 (%)"] = es95(r)
    
    return stats
