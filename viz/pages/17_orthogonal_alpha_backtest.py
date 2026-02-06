"""
Page: Orthogonal alpha backtest on EOD data.

Signal = momentum-orthogonal alpha via rolling OLS regression. Extracts alpha uncorrelated
with classic momentum. Standardized and vol-matched position.
Three PnL series with changeable parameters; toggle-able plot; enhanced stats table.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from statsmodels.regression.rolling import RollingOLS
from statsmodels.tools import add_constant

from config import settings
from data import Storage
from viz.backtest_utils import (
    TRADING_DAYS,
    TRADING_HOURS_PER_YEAR,
    VOL_FLOOR,
    prepare_daily_stats_series,
    rescale_to_target_vol as rescale_to_target_vol_util,
    build_stats,
    alpha_beta,
    annual_turnover,
    ridge_aggregation,
)

TIMEFRAME_5M = "5m"
BARS_PER_HOUR = 12  # 5m bars per hour

st.title("Orthogonal alpha backtest")
st.caption(
    "5m data aggregated to hourly bars, signal = alpha orthogonal to momentum via rolling OLS, "
    "with strategy decay; vol-matched position. Cum return = cumsum(log return)."
)

storage = Storage()
symbols = settings.symbols

with st.sidebar:
    symbol = st.selectbox(
        "Symbol",
        symbols,
        index=0,
        help="Symbol (from settings.symbols).",
    )
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

# Create two columns: main content (left) and controls (right)
col_main, col_controls = st.columns([3, 1])

with col_controls:
    st.subheader("Strategy 1")
    fast1 = st.slider("Fast EMA (hours)", 12, 300, 24, key="fast1_oa")
    slow_mult1 = st.slider("Slow multiple", 2, 8, 2, key="slow_mult1_oa")
    forward1 = st.slider("Forward window (hours)", 12, 300, 24, key="forward1_oa")
    reg_window1 = st.slider("Regression window (hours)", 168, 2160, 720, key="reg_window1_oa")
    vol_look1 = st.slider("Vol window (hours)", 24, 1440, 720, key="vol1_oa")
    use_decay1 = st.checkbox("Use strategy decay", value=True, key="decay1_oa")
    cap1 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap1_oa")

    st.subheader("Strategy 2")
    fast2 = st.slider("Fast EMA (hours)", 12, 300, 48, key="fast2_oa")
    slow_mult2 = st.slider("Slow multiple", 2, 8, 2, key="slow_mult2_oa")
    forward2 = st.slider("Forward window (hours)", 12, 300, 48, key="forward2_oa")
    reg_window2 = st.slider("Regression window (hours)", 168, 2160, 720, key="reg_window2_oa")
    vol_look2 = st.slider("Vol window (hours)", 24, 1440, 720, key="vol2_oa")
    use_decay2 = st.checkbox("Use strategy decay", value=True, key="decay2_oa")
    cap2 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap2_oa")

    st.subheader("Strategy 3")
    fast3 = st.slider("Fast EMA (hours)", 12, 300, 96, key="fast3_oa")
    slow_mult3 = st.slider("Slow multiple", 2, 8, 2, key="slow_mult3_oa")
    forward3 = st.slider("Forward window (hours)", 12, 300, 96, key="forward3_oa")
    reg_window3 = st.slider("Regression window (hours)", 168, 2160, 720, key="reg_window3_oa")
    vol_look3 = st.slider("Vol window (hours)", 24, 1440, 720, key="vol3_oa")
    use_decay3 = st.checkbox("Use strategy decay", value=True, key="decay3_oa")
    cap3 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap3_oa")

    st.divider()
    target_vol = st.slider("Target vol (ann) — all series", 0.05, 0.50, 0.30, 0.01, key="target_vol_oa")

    st.divider()
    show_raw = st.checkbox("Show Raw", value=True, key="show_raw_oa")
    show_s1 = st.checkbox("Show Strategy 1", value=True, key="show_s1_oa")
    show_s2 = st.checkbox("Show Strategy 2", value=True, key="show_s2_oa")
    show_s3 = st.checkbox("Show Strategy 3", value=True, key="show_s3_oa")
    show_avg = st.checkbox("Show Avg (1+2+3)", value=True, key="show_avg_oa")
    show_reg = st.checkbox("Show Reg (β≥0)", value=True, key="show_reg_oa")

rows = storage.read_ohlcv(symbol=symbol, timeframe=TIMEFRAME_5M)
if not rows:
    st.warning(
        f"No **5m** OHLCV data for **{symbol}**. "
        "Run `scripts/utils/download_last_24h.py` or `scripts/backfill/update_5y_5m.py` first."
    )
    st.stop()

df_5m = pd.DataFrame(
    rows,
    columns=["open_time", "open", "high", "low", "close", "volume", "close_time"],
)
df_5m["datetime"] = pd.to_datetime(df_5m["open_time"], unit="ms")
df_5m = df_5m.sort_values("datetime").reset_index(drop=True)

# Aggregate 5m to hourly bars
df_5m["hour"] = df_5m["datetime"].dt.floor("H")
hourly = df_5m.groupby("hour", as_index=False).agg(
    open=("open", "first"),
    high=("high", "max"),
    low=("low", "min"),
    close=("close", "last"),
    volume=("volume", "sum"),
)
hourly = hourly.sort_values("hour").reset_index(drop=True)
hourly["datetime"] = hourly["hour"]

# Log return (hourly)
hourly["ret"] = np.log(hourly["close"] / hourly["close"].shift(1))
hourly = hourly.dropna(subset=["ret"]).reset_index(drop=True)
close = hourly["close"]
ret = hourly["ret"]
dates = hourly["datetime"]


def strategy_decay(position: pd.Series, returns: pd.Series, defactor: float = 0.1) -> pd.Series:
    """Strategy decay: EWM of rolling PnL → decay ∈ [0.75, 1.0] when strategy underperforms."""
    strat_pnl = (position * returns).ewm(span=24 * 90, adjust=False).mean()
    decay_raw = -np.clip(strat_pnl / defactor, -2, 2) / 2
    decay = 0.75 + 0.25 * decay_raw
    return decay.clip(0.75, 1.0)


def run_strategy(
    fast_ema: int,
    slow_multiple: int,
    forward_window: int,
    regression_window: int,
    vol_lookback: int,
    use_decay: bool,
    target_vol_ann: float,
    cap: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Orthogonal alpha strategy: extracts alpha uncorrelated with momentum.
    With strategy decay.
    
    Returns: (pnl, position, signal)
    """
    # 1. Momentum signal: (fast_ema - slow_ema) / std, clip ±2
    slow_span = int(fast_ema * slow_multiple)
    fast_ema_series = close.ewm(span=fast_ema, adjust=False).mean()
    slow_ema_series = close.ewm(span=slow_span, adjust=False).mean()
    momentum_raw = fast_ema_series - slow_ema_series
    momentum_std = momentum_raw.ewm(span=vol_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    momentum = (momentum_raw / momentum_std).clip(-2, 2)
    
    # 2. Volatility for risk adjustment
    vol_estimator = ret.ewm(span=vol_lookback, adjust=False).std().clip(lower=VOL_FLOOR)

    # 3. y = current (backward) return over last n periods; X = momentum n periods ago (aligned to current)
    # No future data: y_t = return from t-n to t, X_t = signal at t-n
    n = forward_window
    y = ret.rolling(n).sum()  # backward-looking: current return (price now minus price n back)
    X_series = momentum.shift(n)  # signals n periods back, shifted so row t has signal at t-n

    # 4. Align: valid from index n onward; RollingOLS on (y, X)
    start_idx = n
    y_roll = y.iloc[start_idx:].astype(float)
    X_roll = X_series.iloc[start_idx:].astype(float)
    valid = y_roll.notna() & X_roll.notna()
    y_roll = y_roll[valid]
    X_roll = X_roll[valid]
    if len(y_roll) < regression_window:
        alpha_signal = pd.Series(0.0, index=ret.index)
    else:
        exog = add_constant(X_roll.values)
        window = max(3, min(regression_window, len(y_roll) - 1))  # need window > n_regressors (2)
        rol = RollingOLS(y_roll.values, exog, window=window).fit(params_only=True)
        # Intercept is first column (const)
        if hasattr(rol.params, "iloc"):
            alpha_vals = rol.params.iloc[:, 0].values
        else:
            alpha_vals = rol.params[:, 0]
        alpha_series = pd.Series(alpha_vals, index=y_roll.index)
        # Latest few bars: use last available const from period-matched model
        alpha_signal = alpha_series.reindex(ret.index).ffill().fillna(0)
    
    # 5. Standardize alpha signal
    alpha_std = alpha_signal.ewm(span=vol_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    alpha_normalized = (alpha_signal / alpha_std).clip(-2, 2)
    
    # 6. Strategy decay (optional)
    decay = pd.Series(1.0, index=ret.index)
    if use_decay:
        target_hourly = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
        position_temp = (alpha_normalized * target_hourly / vol_estimator).clip(-cap, cap)
        decay = strategy_decay(position_temp, ret)
        alpha_normalized = alpha_normalized * decay
    
    # 7. Position sizing
    vol_estimator_annualized = vol_estimator * np.sqrt(TRADING_HOURS_PER_YEAR)
    target_hourly = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (alpha_normalized * target_hourly / vol_estimator_annualized).clip(-cap, cap)
    
    # 8. PnL calculation
    pnl = position.shift(1) * ret
    pnl = pnl.fillna(0)
    
    return pnl, position, alpha_normalized


pnl1, pos1, s1 = run_strategy(fast1, slow_mult1, forward1, reg_window1, vol_look1, use_decay1, target_vol, cap1)
pnl2, pos2, s2 = run_strategy(fast2, slow_mult2, forward2, reg_window2, vol_look2, use_decay2, target_vol, cap2)
pnl3, pos3, s3 = run_strategy(fast3, slow_mult3, forward3, reg_window3, vol_look3, use_decay3, target_vol, cap3)

# Reg: 4 models (24h/48h/96h/192h forward vol-normalized return)
beta_reg, betas, horizon_labels = ridge_aggregation(pos1, pos2, pos3, ret, vol_ewm_span=30, is_intraday_hourly=True)
beta_24h, beta_48h, beta_96h, beta_192h = betas[0], betas[1], betas[2], betas[3]
pos_reg = beta_reg[0] * pos1 + beta_reg[1] * pos2 + beta_reg[2] * pos3
pnl_reg = pos_reg.shift(1) * ret
pnl_reg = pnl_reg.fillna(0)

# Avg of 3
pos_avg = (pos1 + pos2 + pos3) / 3
pnl_avg = pos_avg.shift(1) * ret
pnl_avg = pnl_avg.fillna(0)

# Rescale all series to match target vol (hourly data)
ret_scaled, _ = rescale_to_target_vol_util(ret, None, target_vol, is_intraday=True)
pnl1, pos1 = rescale_to_target_vol_util(pnl1, pos1, target_vol, is_intraday=True)
pnl2, pos2 = rescale_to_target_vol_util(pnl2, pos2, target_vol, is_intraday=True)
pnl3, pos3 = rescale_to_target_vol_util(pnl3, pos3, target_vol, is_intraday=True)
pnl_avg, pos_avg = rescale_to_target_vol_util(pnl_avg, pos_avg, target_vol, is_intraday=True)
pnl_reg, pos_reg = rescale_to_target_vol_util(pnl_reg, pos_reg, target_vol, is_intraday=True)

# Cum return
cumret_raw = ret_scaled.cumsum()
cumret1 = np.log(1 + pnl1).cumsum()
cumret2 = np.log(1 + pnl2).cumsum()
cumret3 = np.log(1 + pnl3).cumsum()
cumret_avg = np.log(1 + pnl_avg).cumsum()
cumret_reg = np.log(1 + pnl_reg).cumsum()

fig = go.Figure()
if show_raw:
    fig.add_trace(go.Scatter(x=dates, y=cumret_raw, mode="lines", name="Raw", line=dict(width=2)))
if show_s1:
    fig.add_trace(go.Scatter(x=dates, y=cumret1, mode="lines", name="Strategy 1", line=dict(width=1.5)))
if show_s2:
    fig.add_trace(go.Scatter(x=dates, y=cumret2, mode="lines", name="Strategy 2", line=dict(width=1.5)))
if show_s3:
    fig.add_trace(go.Scatter(x=dates, y=cumret3, mode="lines", name="Strategy 3", line=dict(width=1.5)))
if show_avg:
    fig.add_trace(go.Scatter(x=dates, y=cumret_avg, mode="lines", name="Avg (1+2+3)", line=dict(width=2)))
if show_reg:
    fig.add_trace(go.Scatter(x=dates, y=cumret_reg, mode="lines", name="Reg (β≥0)", line=dict(width=2)))
fig.update_layout(
    title=f"{symbol} Cumulative log return (orthogonal alpha)",
    xaxis_title="Date",
    yaxis_title="Cumulative log return",
    template="plotly_white",
    height=500,
    showlegend=True,
)
fig.update_xaxes(rangeslider_visible=False)
with col_main:
    st.plotly_chart(fig, use_container_width=True)

# Prepare daily series for statistics (resample if intraday)
pnl1_for_stats, pnl2_for_stats, pnl3_for_stats, pnl_avg_for_stats, pnl_reg_for_stats, ret_scaled_for_stats = prepare_daily_stats_series(
    pnl1, pnl2, pnl3, pnl_avg, pnl_reg, ret_scaled, dates
)


stats_raw = build_stats(ret_scaled_for_stats, is_raw=True)
stats1 = build_stats(pnl1_for_stats, is_raw=False)
stats2 = build_stats(pnl2_for_stats, is_raw=False)
stats3 = build_stats(pnl3_for_stats, is_raw=False)
stats_avg = build_stats(pnl_avg_for_stats, is_raw=False)
stats_reg = build_stats(pnl_reg_for_stats, is_raw=False)

alpha1, beta1 = alpha_beta(pnl1_for_stats, ret_scaled_for_stats)
alpha2, beta2 = alpha_beta(pnl2_for_stats, ret_scaled_for_stats)
alpha3, beta3 = alpha_beta(pnl3_for_stats, ret_scaled_for_stats)
alpha_avg, beta_avg = alpha_beta(pnl_avg_for_stats, ret_scaled_for_stats)
alpha_reg, beta_reg_out = alpha_beta(pnl_reg_for_stats, ret_scaled_for_stats)

turnover_raw = 0.0
turnover1 = annual_turnover(pos1, is_intraday=True)
turnover2 = annual_turnover(pos2, is_intraday=True)
turnover3 = annual_turnover(pos3, is_intraday=True)
turnover_avg = annual_turnover(pos_avg, is_intraday=True)
turnover_reg = annual_turnover(pos_reg, is_intraday=True)

rows_table = [
    ("Ann return (%)", stats_raw["Ann return (%)"], stats1["Ann return (%)"], stats2["Ann return (%)"], stats3["Ann return (%)"], stats_avg["Ann return (%)"], stats_reg["Ann return (%)"]),
    ("Ann vol (%)", stats_raw["Ann vol (%)"], stats1["Ann vol (%)"], stats2["Ann vol (%)"], stats3["Ann vol (%)"], stats_avg["Ann vol (%)"], stats_reg["Ann vol (%)"]),
    ("Sharpe", stats_raw["Sharpe"], stats1["Sharpe"], stats2["Sharpe"], stats3["Sharpe"], stats_avg["Sharpe"], stats_reg["Sharpe"]),
    ("Sortino", stats_raw["Sortino"], stats1["Sortino"], stats2["Sortino"], stats3["Sortino"], stats_avg["Sortino"], stats_reg["Sortino"]),
    ("Max DD (%)", stats_raw["Max DD (%)"], stats1["Max DD (%)"], stats2["Max DD (%)"], stats3["Max DD (%)"], stats_avg["Max DD (%)"], stats_reg["Max DD (%)"]),
    ("CDD95 (%)", stats_raw["CDD95 (%)"], stats1["CDD95 (%)"], stats2["CDD95 (%)"], stats3["CDD95 (%)"], stats_avg["CDD95 (%)"], stats_reg["CDD95 (%)"]),
    ("Avg DD (%)", stats_raw["Avg DD (%)"], stats1["Avg DD (%)"], stats2["Avg DD (%)"], stats3["Avg DD (%)"], stats_avg["Avg DD (%)"], stats_reg["Avg DD (%)"]),
    ("Calmar", stats_raw["Calmar"], stats1["Calmar"], stats2["Calmar"], stats3["Calmar"], stats_avg["Calmar"], stats_reg["Calmar"]),
    ("Skewness", stats_raw["Skewness"], stats1["Skewness"], stats2["Skewness"], stats3["Skewness"], stats_avg["Skewness"], stats_reg["Skewness"]),
    ("Kurtosis (mth)", stats_raw["Kurtosis (mth)"], stats1["Kurtosis (mth)"], stats2["Kurtosis (mth)"], stats3["Kurtosis (mth)"], stats_avg["Kurtosis (mth)"], stats_reg["Kurtosis (mth)"]),
    ("CVaR95 (%)", stats_raw["CVaR95 (%)"], stats1["CVaR95 (%)"], stats2["CVaR95 (%)"], stats3["CVaR95 (%)"], stats_avg["CVaR95 (%)"], stats_reg["CVaR95 (%)"]),
    ("Hit Rate (%)", stats_raw["Hit Rate (%)"], stats1["Hit Rate (%)"], stats2["Hit Rate (%)"], stats3["Hit Rate (%)"], stats_avg["Hit Rate (%)"], stats_reg["Hit Rate (%)"]),
    ("Profit Factor", stats_raw["Profit Factor"], stats1["Profit Factor"], stats2["Profit Factor"], stats3["Profit Factor"], stats_avg["Profit Factor"], stats_reg["Profit Factor"]),
    ("Ann turnover", turnover_raw, turnover1, turnover2, turnover3, turnover_avg, turnover_reg),
    ("Alpha vs raw (ann %)", np.nan, alpha1 * 100 if not np.isnan(alpha1) else np.nan, alpha2 * 100 if not np.isnan(alpha2) else np.nan, alpha3 * 100 if not np.isnan(alpha3) else np.nan, alpha_avg * 100 if not np.isnan(alpha_avg) else np.nan, alpha_reg * 100 if not np.isnan(alpha_reg) else np.nan),
    ("Beta vs raw", np.nan, beta1, beta2, beta3, beta_avg, beta_reg_out),
]
stats_df = pd.DataFrame(
    rows_table,
    columns=["Metric", "Raw", "Strategy 1", "Strategy 2", "Strategy 3", "Avg (1+2+3)", "Reg (β≥0)"],
).set_index("Metric")
with col_main:
    st.dataframe(stats_df.style.format("{:.2f}", na_rep="-"), use_container_width=True)
    
    st.caption(f"Total hourly bars: {len(hourly)} | {hourly['datetime'].min()} → {hourly['datetime'].max()} (from {len(df_5m)} 5m bars)")
    st.caption(
        f"Reg (β≥0): 4 models ({'/'.join(horizon_labels)} fwd ret/vol), avg betas = [{beta_reg[0]:.3f}, {beta_reg[1]:.3f}, {beta_reg[2]:.3f}] "
        f"({horizon_labels[0]}: [{beta_24h[0]:.2f},{beta_24h[1]:.2f},{beta_24h[2]:.2f}] {horizon_labels[1]}: [{beta_48h[0]:.2f},{beta_48h[1]:.2f},{beta_48h[2]:.2f}] "
        f"{horizon_labels[2]}: [{beta_96h[0]:.2f},{beta_96h[1]:.2f},{beta_96h[2]:.2f}] {horizon_labels[3]}: [{beta_192h[0]:.2f},{beta_192h[1]:.2f},{beta_192h[2]:.2f}])"
    )
    st.caption(
    "Signal: y = current return (backward n-period), X = momentum n periods back; RollingOLS(y ~ const + X); "
    "const (alpha orthogonal to momentum) = signal; latest bars use last available const. Standardized, × decay, vol-matched × cap."
)
