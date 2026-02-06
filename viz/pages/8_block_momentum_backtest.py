"""
Page: Block momentum backtest on EOD data.

Signal = "higher high + higher low" over blocks. Captures sustained directional structure
(trend continuation) rather than single-bar breakouts. Standardized and vol-matched position.
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
from sklearn.linear_model import RidgeCV

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
)

TIMEFRAME_5M = "5m"
BARS_PER_HOUR = 12  # 5m bars per hour

st.title("Block momentum backtest")
st.caption(
    "5m data aggregated to hourly bars, signal = (higher high + higher low) / range over blocks, "
    "with Weibull CDF vol tilt and strategy decay; vol-matched position. Cum return = cumsum(log return)."
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
    block1 = st.slider("Block window (hours)", 24, 500, 48, key="block1_bm")
    smooth1 = st.slider("Smooth window (hours)", 1, 48, 12, key="smooth1_bm")
    vol_look1 = st.slider("Vol window (hours)", 24, 1440, 720, key="vol1_bm")
    weibull_c1 = st.slider("Weibull shape (c)", 0.5, 3.0, 2.0, 0.1, key="weibull_c1_bm")
    alpha_blend1 = st.slider("Alpha blend", 0.0, 1.0, 1.0, 0.1, key="alpha1_bm")
    use_decay1 = st.checkbox("Use strategy decay", value=True, key="decay1_bm")
    cap1 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap1_bm")

    st.subheader("Strategy 2")
    block2 = st.slider("Block window (hours)", 24, 500, 96, key="block2_bm")
    smooth2 = st.slider("Smooth window (hours)", 1, 48, 12, key="smooth2_bm")
    vol_look2 = st.slider("Vol window (hours)", 24, 1440, 720, key="vol2_bm")
    weibull_c2 = st.slider("Weibull shape (c)", 0.5, 3.0, 2.0, 0.1, key="weibull_c2_bm")
    alpha_blend2 = st.slider("Alpha blend", 0.0, 1.0, 1.0, 0.1, key="alpha2_bm")
    use_decay2 = st.checkbox("Use strategy decay", value=True, key="decay2_bm")
    cap2 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap2_bm")

    st.subheader("Strategy 3")
    block3 = st.slider("Block window (hours)", 24, 500, 192, key="block3_bm")
    smooth3 = st.slider("Smooth window (hours)", 1, 48, 12, key="smooth3_bm")
    vol_look3 = st.slider("Vol window (hours)", 24, 1440, 720, key="vol3_bm")
    weibull_c3 = st.slider("Weibull shape (c)", 0.5, 3.0, 2.0, 0.1, key="weibull_c3_bm")
    alpha_blend3 = st.slider("Alpha blend", 0.0, 1.0, 1.0, 0.1, key="alpha3_bm")
    use_decay3 = st.checkbox("Use strategy decay", value=True, key="decay3_bm")
    cap3 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap3_bm")

    st.divider()
    target_vol = st.slider("Target vol (ann) — all series", 0.05, 0.50, 0.30, 0.01, key="target_vol_bm")

    st.divider()
    show_raw = st.checkbox("Show Raw", value=True, key="show_raw_bm")
    show_s1 = st.checkbox("Show Strategy 1", value=True, key="show_s1_bm")
    show_s2 = st.checkbox("Show Strategy 2", value=True, key="show_s2_bm")
    show_s3 = st.checkbox("Show Strategy 3", value=True, key="show_s3_bm")
    show_avg = st.checkbox("Show Avg (1+2+3)", value=True, key="show_avg_bm")
    show_reg = st.checkbox("Show Reg (β≥0)", value=True, key="show_reg_bm")

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
high = hourly["high"]
low = hourly["low"]
open_price = hourly["open"]


def rogers_satchell_volatility(high: pd.Series, low: pd.Series, open_price: pd.Series, close: pd.Series, window: int) -> pd.Series:
    """Rogers-Satchell volatility estimator using OHLC data."""
    h_c = np.log(high / close)
    l_c = np.log(low / close)
    h_o = np.log(high / open_price)
    l_o = np.log(low / open_price)
    rs = h_c * (h_c - h_o) + l_c * (l_c - l_o)
    rs_vol = np.sqrt(rs.rolling(window=window).mean()) * np.sqrt(TRADING_HOURS_PER_YEAR)
    return rs_vol.clip(lower=VOL_FLOOR)


def weibull_vol_tilt(vol_series: pd.Series, weibull_c: float) -> pd.Series:
    """Volatility tilt using Weibull CDF: vol_tilt = 1 - Weibull_CDF(v; c, scale)"""
    vol_median = vol_series.median()
    scale = vol_median * 1.5
    vol_normalized = vol_series / scale
    weibull_cdf = 1 - np.exp(-(vol_normalized ** weibull_c))
    vol_tilt = 1 - weibull_cdf
    return vol_tilt.clip(0, 1)


def strategy_decay(position: pd.Series, returns: pd.Series, defactor: float = 0.1) -> pd.Series:
    """Strategy decay: EWM of rolling PnL → decay ∈ [0.75, 1.0] when strategy underperforms."""
    strat_pnl = (position * returns).ewm(span=24 * 90, adjust=False).mean()
    decay_raw = -np.clip(strat_pnl / defactor, -2, 2) / 2
    decay = 0.75 + 0.25 * decay_raw
    return decay.clip(0.75, 1.0)


def run_strategy(
    block_window: int,
    smooth_window: int,
    vol_window: int,
    weibull_c: float,
    alpha_blend: float,
    use_decay: bool,
    target_vol_ann: float,
    cap: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Block momentum strategy: higher high + higher low over blocks.
    With Weibull CDF vol tilt and strategy decay.
    
    Returns: (pnl, position, signal)
    """
    # 1. Rolling high/low over block window
    rolling_high = close.rolling(window=block_window).max()
    rolling_low = close.rolling(window=block_window).min()
    
    # 2. Block changes: how much higher current block vs prior block
    hh = rolling_high.diff(block_window)  # Higher high change
    ll = rolling_low.diff(block_window)   # Higher low change
    
    # 3. Normalized signal: (hh + ll) / 2 / range
    block_range = (rolling_high - rolling_low).clip(lower=VOL_FLOOR)
    signal_raw = (hh + ll) / 2 / block_range
    
    # 4. Smooth and clip
    signal_smooth = signal_raw.ewm(span=smooth_window, adjust=False).mean()
    signal = signal_smooth.clip(-2, 2)
    
    # 5. Volatility estimation (Rogers-Satchell or EWM std)
    try:
        vol_estimator = rogers_satchell_volatility(high, low, open_price, close, vol_window)
    except:
        vol_estimator = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR) * np.sqrt(TRADING_HOURS_PER_YEAR)
    
    # 6. Vol tilt: Weibull CDF
    vol_tilt = weibull_vol_tilt(vol_estimator, weibull_c)
    
    # 7. Alpha blend: tilt = (1-α) + α × vol_tilt
    tilt = (1 - alpha_blend) + alpha_blend * vol_tilt
    
    # 8. Combined signal
    signal_combined = signal * tilt
    
    # 9. Strategy decay (optional)
    decay = pd.Series(1.0, index=ret.index)
    if use_decay:
        target_hourly = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
        position_temp = (signal_combined * target_hourly / vol_estimator).clip(-cap, cap)
        decay = strategy_decay(position_temp, ret)
        signal_combined = signal_combined * decay
    
    # 10. Position sizing
    target_hourly = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (signal_combined * target_hourly / vol_estimator).clip(-cap, cap)
    
    # 11. PnL calculation
    pnl = position.shift(1) * ret
    pnl = pnl.fillna(0)
    
    return pnl, position, signal


pnl1, pos1, s1 = run_strategy(block1, smooth1, vol_look1, weibull_c1, alpha_blend1, use_decay1, target_vol, cap1)
pnl2, pos2, s2 = run_strategy(block2, smooth2, vol_look2, weibull_c2, alpha_blend2, use_decay2, target_vol, cap2)
pnl3, pos3, s3 = run_strategy(block3, smooth3, vol_look3, weibull_c3, alpha_blend3, use_decay3, target_vol, cap3)

# Reg: 4 models (1d / 5d / 10d / 30d forward vol-normalized return = β·positions), RidgeCV 5-fold, train on first half only
vol_ret = ret.ewm(span=30, adjust=False).std().clip(lower=VOL_FLOOR)
X = np.column_stack([pos1.values, pos2.values, pos3.values])
default_beta = np.array([1.0 / 3, 1.0 / 3, 1.0 / 3])
betas = []
for horizon in (1, 5, 10, 30):
    fwd_ret = ret.rolling(horizon).sum().shift(-horizon)
    vol_h = vol_ret * np.sqrt(horizon)
    y_h = (fwd_ret / vol_h).replace([np.inf, -np.inf], np.nan).values
    valid = ~(np.isnan(X).any(axis=1) | np.isnan(y_h))
    X_v, y_v = X[valid], y_h[valid]
    if X_v.shape[0] > 10:
        split_idx = X_v.shape[0] // 2
        X_train, y_train = X_v[:split_idx], y_v[:split_idx]
        ridge = RidgeCV(cv=5, alphas=np.logspace(-6, 6, 13))
        ridge.fit(X_train, y_train)
        b = ridge.coef_
        betas.append(b)
    else:
        betas.append(default_beta)
beta_1d, beta_5d, beta_10d, beta_30d = betas[0], betas[1], betas[2], betas[3]
beta_reg = (np.array(beta_1d) + np.array(beta_5d) + np.array(beta_10d) + np.array(beta_30d)) / 4
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
    title=f"{symbol} Cumulative log return (block momentum)",
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
        f"Reg (β≥0): 4 models (1h/5h/10h/30h fwd ret/vol), avg betas = [{beta_reg[0]:.3f}, {beta_reg[1]:.3f}, {beta_reg[2]:.3f}] "
        f"(1h: [{beta_1d[0]:.2f},{beta_1d[1]:.2f},{beta_1d[2]:.2f}] 5h: [{beta_5d[0]:.2f},{beta_5d[1]:.2f},{beta_5d[2]:.2f}] "
        f"10h: [{beta_10d[0]:.2f},{beta_10d[1]:.2f},{beta_10d[2]:.2f}] 30h: [{beta_30d[0]:.2f},{beta_30d[1]:.2f},{beta_30d[2]:.2f}])"
    )
    st.caption("Signal: (higher high + higher low) / range over blocks, smoothed, × Weibull CDF vol tilt, × strategy decay (optional), vol-matched × cap.")
