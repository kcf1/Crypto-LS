"""
Shared utilities for backtest visualization pages.

This module contains common functions used across multiple backtest pages:
- Data resampling (intraday to daily)
- Statistics calculations
- Volatility rescaling
- Common constants
"""

import numpy as np
import pandas as pd

# Constants
TRADING_DAYS = 252  # For daily/annualized statistics
TRADING_HOURS_PER_YEAR = 24 * 252  # 6048 hours (for intraday position sizing)
VOL_FLOOR = 1e-8


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
    Calculate maximum drawdown from cumulative log returns.
    
    Args:
        cumlog: Cumulative log return series
    
    Returns:
        Maximum drawdown as percentage (e.g., 15.5 for 15.5%)
    """
    level = level_from_log(cumlog)
    peak = level.cummax()
    dd = peak - level
    return float(dd.max()) * 100


def avg_drawdown(cumlog: pd.Series) -> float:
    """
    Calculate average drawdown from cumulative log returns.
    
    Args:
        cumlog: Cumulative log return series
    
    Returns:
        Average drawdown as percentage
    """
    level = level_from_log(cumlog)
    peak = level.cummax()
    dd = peak - level
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
    Conditional Drawdown at Risk (CDD) at 95% confidence level.
    Expected drawdown given that drawdown exceeds the 95th percentile threshold.
    
    Args:
        cumlog: Cumulative log return series
    
    Returns:
        CDD95 as percentage
    """
    level = np.exp(cumlog) - 1
    peak = level.cummax()
    drawdown = peak - level
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
