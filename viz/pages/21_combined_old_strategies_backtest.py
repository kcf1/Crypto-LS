"""
Page: Combined old strategies backtest (all variants, no sliders).

Combines all strategy variants from docs/plans/migration/old-strategies.md:
WedThu(2), EmaVol(4), AccelVol(4), BreakVol(4), BlockVol(4), Rev(4), OrthAlpha(4) = 26 variants.
Two combination modes: fixed fit_models variant weights or ridge aggregation.
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
    resample_pnl_to_daily,
    rescale_to_target_vol as rescale_to_target_vol_util,
    build_stats,
    alpha_beta,
    annual_turnover,
    ridge_aggregation_multi,
    pls_aggregation_multi,
    cost_metrics,
    buffer_position,
)

TIMEFRAME_5M = "5m"
TARGET_VOL = 0.30
CAP = 3.0

# Variants and weights from fit_models (docs/plans/migration/old-strategies.md)
# Variant weight = strat_weight / len(variants). All use target_vol=0.30.
WEDTHU_VOL_WINDOWS = [1440, 4320]   # 60d, 180d; strat_weight 0.10 → 0.05 each
EMAVOL_FAST_EMA = [24, 48, 96, 192]  # strat_weight 0.20 → 0.05 each
ACCELVOL_FAST_EMA = [24, 48, 96, 192]  # strat_weight 0.15 → 0.0375 each
BREAKVOL_BREAKOUT_WINDOW = [48, 96, 192, 384]  # strat_weight 0.20 → 0.05 each
BLOCKVOL_BLOCK_WINDOW = [48, 96, 192, 384]  # strat_weight 0.15 → 0.0375 each
REV_REVERSAL_WINDOW = [6, 9, 12, 15]  # strat_weight 0.10 → 0.025 each
ORTHALPHA_FORWARD_WINDOW = [24, 48, 96, 192]  # strat_weight 0.20 → 0.05 each

VOL_WINDOW_DEFAULT = 720
STD_LOOKBACK = 720
SMOOTH_WINDOW = 12
REVERSAL_THRESHOLD = 2.0
VOLUME_THRESHOLD = 0.3
REGRESSION_WINDOW = 720

st.title("Combined old strategies backtest")
st.caption(
    "5m → hourly. All variants from old-strategies.md: WedThu(2), EmaVol(4), AccelVol(4), BreakVol(4), "
    "BlockVol(4), Rev(4), OrthAlpha(4) = 26 variants. Weighted: fixed fit_models variant weights. Ridge: learned."
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

col_main, col_controls = st.columns([3, 1])

with col_controls:
    show_raw = st.checkbox("Show Raw", value=True, key="show_raw_comb")
    show_weighted = st.checkbox("Show Weighted", value=True, key="show_weighted_comb")
    show_buffered = st.checkbox("Show Weighted (buffered)", value=True, key="show_buffered_comb")
    show_ridge = st.checkbox("Show Ridge", value=True, key="show_ridge_comb")
    show_ridge_buffered = st.checkbox("Show Ridge (buffered)", value=True, key="show_ridge_buffered_comb")
    show_pls = st.checkbox("Show PLS", value=True, key="show_pls_comb")
    show_pls_buffered = st.checkbox("Show PLS (buffered)", value=True, key="show_pls_buffered_comb")

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

hourly["ret"] = np.log(hourly["close"] / hourly["close"].shift(1))
hourly = hourly.dropna(subset=["ret"]).reset_index(drop=True)
close = hourly["close"]
ret = hourly["ret"]
volume = hourly["volume"]
dates = hourly["datetime"]
high = hourly["high"]
low = hourly["low"]
open_price = hourly["open"]
hourly["weekday"] = pd.to_datetime(hourly["datetime"]).dt.dayofweek


def rogers_satchell_volatility(high: pd.Series, low: pd.Series, open_price: pd.Series, close: pd.Series, window: int) -> pd.Series:
    h_c = np.log(high / close)
    l_c = np.log(low / close)
    h_o = np.log(high / open_price)
    l_o = np.log(low / open_price)
    rs = h_c * (h_c - h_o) + l_c * (l_c - l_o)
    rs_vol = np.sqrt(rs.rolling(window=window).mean()) * np.sqrt(TRADING_HOURS_PER_YEAR)
    return rs_vol.clip(lower=VOL_FLOOR)


def weibull_vol_tilt(vol_series: pd.Series, weibull_c: float) -> pd.Series:
    vol_median = vol_series.median()
    scale = vol_median * 1.5
    vol_normalized = vol_series / scale
    weibull_cdf = 1 - np.exp(-(vol_normalized ** weibull_c))
    return (1 - weibull_cdf).clip(0, 1)


def strategy_decay(position: pd.Series, returns: pd.Series, defactor: float = 0.1) -> pd.Series:
    strat_pnl = (position * returns).ewm(span=24 * 90, adjust=False).mean()
    decay_raw = -np.clip(strat_pnl / defactor, -2, 2) / 2
    return (0.75 + 0.25 * decay_raw).clip(0.75, 1.0)


# ---- WedThu (10%) ----
def run_wed_thu(vol_window: int, target_vol_ann: float, cap: float) -> tuple[pd.Series, pd.Series]:
    signal_raw = pd.Series(0.0, index=ret.index)
    signal_raw[hourly["weekday"] == 2] = 1.0
    signal_raw[hourly["weekday"] == 3] = -1.0
    signal = signal_raw.shift(1).fillna(0)
    vol_estimator = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR)
    vol_annualized = vol_estimator * np.sqrt(TRADING_HOURS_PER_YEAR)
    target_hourly = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (signal * target_hourly / vol_annualized).clip(-cap, cap)
    pnl = position.shift(1) * ret
    return pnl.fillna(0), position


# ---- EmaVol (20%) ----
def run_ema_vol(fast_ema: int, slow_mult: int, std_lookback: int, vol_window: int,
                weibull_c: float, alpha_blend: float, use_decay: bool, target_vol_ann: float, cap: float) -> tuple[pd.Series, pd.Series]:
    slow_span = int(fast_ema * slow_mult)
    fast_ema_s = close.ewm(span=fast_ema, adjust=False).mean()
    slow_ema_s = close.ewm(span=slow_span, adjust=False).mean()
    signal_raw = fast_ema_s - slow_ema_s
    signal_std_series = signal_raw.ewm(span=std_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    signal_std = (signal_raw / signal_std_series).clip(-2, 2)
    try:
        vol_est = rogers_satchell_volatility(high, low, open_price, close, vol_window)
    except Exception:
        vol_est = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR) * np.sqrt(TRADING_HOURS_PER_YEAR)
    vol_tilt = weibull_vol_tilt(vol_est, weibull_c)
    tilt = (1 - alpha_blend) + alpha_blend * vol_tilt
    signal_combined = signal_std * tilt
    if use_decay:
        target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
        pos_temp = (signal_combined * target_h / vol_est).clip(-cap, cap)
        decay = strategy_decay(pos_temp, ret)
        signal_combined = signal_combined * decay
    target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (signal_combined * target_h / vol_est).clip(-cap, cap)
    pnl = position.shift(1) * ret
    return pnl.fillna(0), position


# ---- AccelVol (15%) ----
def run_accel_vol(fast_ema: int, slow_mult: int, diff_mult: float, std_lookback: int, vol_window: int,
                  weibull_c: float, alpha_blend: float, use_decay: bool, target_vol_ann: float, cap: float) -> tuple[pd.Series, pd.Series]:
    slow_span = int(fast_ema * slow_mult)
    fast_ema_s = close.ewm(span=fast_ema, adjust=False).mean()
    slow_ema_s = close.ewm(span=slow_span, adjust=False).mean()
    signal_level_raw = fast_ema_s - slow_ema_s
    signal_level_std_series = signal_level_raw.ewm(span=std_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    signal_level = (signal_level_raw / signal_level_std_series).clip(-2, 2)
    diff_window = int(fast_ema * diff_mult)
    signal_accel_raw = signal_level.diff(diff_window)
    signal_accel_std_series = signal_accel_raw.ewm(span=std_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    signal_accel = (signal_accel_raw / signal_accel_std_series).clip(-2, 2)
    try:
        vol_est = rogers_satchell_volatility(high, low, open_price, close, vol_window)
    except Exception:
        vol_est = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR) * np.sqrt(TRADING_HOURS_PER_YEAR)
    vol_tilt = weibull_vol_tilt(vol_est, weibull_c)
    tilt = (1 - alpha_blend) + alpha_blend * vol_tilt
    signal_combined = signal_accel * tilt
    if use_decay:
        target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
        pos_temp = (signal_combined * target_h / vol_est).clip(-cap, cap)
        decay = strategy_decay(pos_temp, ret)
        signal_combined = signal_combined * decay
    target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (signal_combined * target_h / vol_est).clip(-cap, cap)
    pnl = position.shift(1) * ret
    return pnl.fillna(0), position


# ---- BreakVol (20%) ----
def run_break_vol(breakout_window: int, smooth_window: int, vol_window: int,
                  weibull_c: float, alpha_blend: float, use_decay: bool, target_vol_ann: float, cap: float) -> tuple[pd.Series, pd.Series]:
    rolling_high = close.rolling(window=breakout_window).max()
    rolling_low = close.rolling(window=breakout_window).min()
    mid = (rolling_high + rolling_low) / 2
    rng = (rolling_high - rolling_low).clip(lower=VOL_FLOOR)
    signal_raw = (close - mid) / rng * 2
    signal_smooth = signal_raw.ewm(span=smooth_window, adjust=False).mean()
    try:
        vol_est = rogers_satchell_volatility(high, low, open_price, close, vol_window)
    except Exception:
        vol_est = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR) * np.sqrt(TRADING_HOURS_PER_YEAR)
    vol_tilt = weibull_vol_tilt(vol_est, weibull_c)
    tilt = (1 - alpha_blend) + alpha_blend * vol_tilt
    signal_combined = signal_smooth * tilt
    if use_decay:
        target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
        pos_temp = (signal_combined * target_h / vol_est).clip(-cap, cap)
        decay = strategy_decay(pos_temp, ret)
        signal_combined = signal_combined * decay
    target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (signal_combined * target_h / vol_est).clip(-cap, cap)
    pnl = position.shift(1) * ret
    return pnl.fillna(0), position


# ---- BlockVol (15%) ----
def run_block_vol(block_window: int, smooth_window: int, vol_window: int,
                  weibull_c: float, alpha_blend: float, use_decay: bool, target_vol_ann: float, cap: float) -> tuple[pd.Series, pd.Series]:
    rolling_high = close.rolling(window=block_window).max()
    rolling_low = close.rolling(window=block_window).min()
    hh = rolling_high.diff(block_window)
    ll = rolling_low.diff(block_window)
    block_range = (rolling_high - rolling_low).clip(lower=VOL_FLOOR)
    signal_raw = (hh + ll) / 2 / block_range
    signal_smooth = signal_raw.ewm(span=smooth_window, adjust=False).mean().clip(-2, 2)
    try:
        vol_est = rogers_satchell_volatility(high, low, open_price, close, vol_window)
    except Exception:
        vol_est = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR) * np.sqrt(TRADING_HOURS_PER_YEAR)
    vol_tilt = weibull_vol_tilt(vol_est, weibull_c)
    tilt = (1 - alpha_blend) + alpha_blend * vol_tilt
    signal_combined = signal_smooth * tilt
    if use_decay:
        target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
        pos_temp = (signal_combined * target_h / vol_est).clip(-cap, cap)
        decay = strategy_decay(pos_temp, ret)
        signal_combined = signal_combined * decay
    target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (signal_combined * target_h / vol_est).clip(-cap, cap)
    pnl = position.shift(1) * ret
    return pnl.fillna(0), position


# ---- Rev (10%) ----
def run_rev(vol_window: int, reversal_window: int, reversal_threshold: float, volume_threshold: float,
            target_vol_ann: float, cap: float) -> tuple[pd.Series, pd.Series]:
    vol_estimator = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR)
    vol_annualized = vol_estimator * np.sqrt(TRADING_HOURS_PER_YEAR)
    volume_ewm = volume.ewm(span=vol_window, adjust=False).mean()
    volume_min = volume_ewm.rolling(window=vol_window).min()
    volume_max = volume_ewm.rolling(window=vol_window).max()
    volume_range = (volume_max - volume_min).clip(lower=VOL_FLOOR)
    volume_z = (volume_ewm - volume_min) / volume_range
    ret_ema = ret.ewm(span=reversal_window, adjust=False).mean()
    ret_z = ret_ema / vol_estimator
    signal = pd.Series(0.0, index=ret.index)
    condition = (ret_z.abs() > reversal_threshold) & (volume_z > volume_threshold)
    signal[condition] = -np.sign(ret_z[condition])
    target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (signal * target_h / vol_annualized).clip(-cap, cap)
    pnl = position.shift(1) * ret
    return pnl.fillna(0), position


# ---- OrthAlpha (20%) ----
def run_orth_alpha(fast_ema: int, slow_mult: int, forward_window: int, regression_window: int,
                   vol_lookback: int, use_decay: bool, target_vol_ann: float, cap: float) -> tuple[pd.Series, pd.Series]:
    slow_span = int(fast_ema * slow_mult)
    fast_ema_s = close.ewm(span=fast_ema, adjust=False).mean()
    slow_ema_s = close.ewm(span=slow_span, adjust=False).mean()
    momentum_raw = fast_ema_s - slow_ema_s
    momentum_std = momentum_raw.ewm(span=vol_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    momentum = (momentum_raw / momentum_std).clip(-2, 2)
    vol_estimator = ret.ewm(span=vol_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    n = forward_window
    y = ret.rolling(n).sum()
    X_series = momentum.shift(n)
    start_idx = n
    y_roll = y.iloc[start_idx:].astype(float)
    X_roll = X_series.iloc[start_idx:].astype(float)
    valid = y_roll.notna() & X_roll.notna()
    y_roll = y_roll[valid]
    X_roll = X_roll[valid]
    alpha_signal = pd.Series(0.0, index=ret.index)
    if len(y_roll) >= regression_window:
        exog = add_constant(X_roll.values)
        window = max(3, min(regression_window, len(y_roll) - 1))
        rol = RollingOLS(y_roll.values, exog, window=window).fit(params_only=True)
        if hasattr(rol.params, "iloc"):
            alpha_vals = rol.params.iloc[:, 0].values
        else:
            alpha_vals = rol.params[:, 0]
        alpha_series = pd.Series(alpha_vals, index=y_roll.index)
        alpha_signal = alpha_series.reindex(ret.index).ffill().fillna(0)
    alpha_std = alpha_signal.ewm(span=vol_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    alpha_normalized = (alpha_signal / alpha_std).clip(-2, 2)
    if use_decay:
        target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
        pos_temp = (alpha_normalized * target_h / vol_estimator).clip(-cap, cap)
        decay = strategy_decay(pos_temp, ret)
        alpha_normalized = alpha_normalized * decay
    vol_annualized = vol_estimator * np.sqrt(TRADING_HOURS_PER_YEAR)
    target_h = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (alpha_normalized * target_h / vol_annualized).clip(-cap, cap)
    pnl = position.shift(1) * ret
    return pnl.fillna(0), position


# Run all strategy variants per old-strategies.md (fit_models config)
positions = []
weights = []

for vw in WEDTHU_VOL_WINDOWS:
    _, pos = run_wed_thu(vol_window=vw, target_vol_ann=TARGET_VOL, cap=CAP)
    positions.append(pos)
    weights.append(0.10 / len(WEDTHU_VOL_WINDOWS))

for fast in EMAVOL_FAST_EMA:
    _, pos = run_ema_vol(fast_ema=fast, slow_mult=2, std_lookback=STD_LOOKBACK, vol_window=VOL_WINDOW_DEFAULT,
                         weibull_c=2, alpha_blend=1.0, use_decay=True, target_vol_ann=TARGET_VOL, cap=CAP)
    positions.append(pos)
    weights.append(0.20 / len(EMAVOL_FAST_EMA))

for fast in ACCELVOL_FAST_EMA:
    _, pos = run_accel_vol(fast_ema=fast, slow_mult=2, diff_mult=1.0, std_lookback=STD_LOOKBACK, vol_window=VOL_WINDOW_DEFAULT,
                           weibull_c=2, alpha_blend=1.0, use_decay=True, target_vol_ann=TARGET_VOL, cap=CAP)
    positions.append(pos)
    weights.append(0.15 / len(ACCELVOL_FAST_EMA))

for bw in BREAKVOL_BREAKOUT_WINDOW:
    _, pos = run_break_vol(breakout_window=bw, smooth_window=SMOOTH_WINDOW, vol_window=VOL_WINDOW_DEFAULT,
                           weibull_c=2, alpha_blend=1.0, use_decay=True, target_vol_ann=TARGET_VOL, cap=CAP)
    positions.append(pos)
    weights.append(0.20 / len(BREAKVOL_BREAKOUT_WINDOW))

for bw in BLOCKVOL_BLOCK_WINDOW:
    _, pos = run_block_vol(block_window=bw, smooth_window=SMOOTH_WINDOW, vol_window=VOL_WINDOW_DEFAULT,
                           weibull_c=2, alpha_blend=1.0, use_decay=True, target_vol_ann=TARGET_VOL, cap=CAP)
    positions.append(pos)
    weights.append(0.15 / len(BLOCKVOL_BLOCK_WINDOW))

for rw in REV_REVERSAL_WINDOW:
    _, pos = run_rev(vol_window=VOL_WINDOW_DEFAULT, reversal_window=rw, reversal_threshold=REVERSAL_THRESHOLD,
                     volume_threshold=VOLUME_THRESHOLD, target_vol_ann=TARGET_VOL, cap=CAP)
    positions.append(pos)
    weights.append(0.10 / len(REV_REVERSAL_WINDOW))

for fw in ORTHALPHA_FORWARD_WINDOW:
    _, pos = run_orth_alpha(fast_ema=24, slow_mult=2, forward_window=fw, regression_window=REGRESSION_WINDOW,
                            vol_lookback=VOL_WINDOW_DEFAULT, use_decay=True, target_vol_ann=TARGET_VOL, cap=CAP)
    positions.append(pos)
    weights.append(0.20 / len(ORTHALPHA_FORWARD_WINDOW))

# Weighted combination (fixed fit_models variant weights)
pos_weighted = sum(w * p for w, p in zip(weights, positions))
pnl_weighted = pos_weighted.shift(1) * ret
pnl_weighted = pnl_weighted.fillna(0)

# Buffered: position only changes when gap > factor × mean(|Δposition|); default factor=2
pos_weighted_buffered = buffer_position(pos_weighted, factor=15.0)
pnl_weighted_buffered = pos_weighted_buffered.shift(1) * ret
pnl_weighted_buffered = pnl_weighted_buffered.fillna(0)

# Ridge aggregation
beta_reg, betas, horizon_labels = ridge_aggregation_multi(
    positions, ret, vol_ewm_span=30, is_intraday_hourly=True
)
pos_ridge = sum(beta_reg[i] * positions[i] for i in range(len(positions)))
pnl_ridge = pos_ridge.shift(1) * ret
pnl_ridge = pnl_ridge.fillna(0)

# Buffered ridge (same factor as weighted buffered)
pos_ridge_buffered = buffer_position(pos_ridge, factor=15.0)
pnl_ridge_buffered = pos_ridge_buffered.shift(1) * ret
pnl_ridge_buffered = pnl_ridge_buffered.fillna(0)

# PLS aggregation (same horizons as ridge)
beta_pls, betas_pls, horizon_labels_pls = pls_aggregation_multi(
    positions, ret, vol_ewm_span=30, is_intraday_hourly=True
)
pos_pls = sum(beta_pls[i] * positions[i] for i in range(len(positions)))
pnl_pls = pos_pls.shift(1) * ret
pnl_pls = pnl_pls.fillna(0)
pos_pls_buffered = buffer_position(pos_pls, factor=15.0)
pnl_pls_buffered = pos_pls_buffered.shift(1) * ret
pnl_pls_buffered = pnl_pls_buffered.fillna(0)

# Rescale all
ret_scaled, _ = rescale_to_target_vol_util(ret, None, TARGET_VOL, is_intraday=True)
pnl_weighted, pos_weighted = rescale_to_target_vol_util(pnl_weighted, pos_weighted, TARGET_VOL, is_intraday=True)
pnl_weighted_buffered, pos_weighted_buffered = rescale_to_target_vol_util(
    pnl_weighted_buffered, pos_weighted_buffered, TARGET_VOL, is_intraday=True
)
pnl_ridge, pos_ridge = rescale_to_target_vol_util(pnl_ridge, pos_ridge, TARGET_VOL, is_intraday=True)
pnl_ridge_buffered, pos_ridge_buffered = rescale_to_target_vol_util(
    pnl_ridge_buffered, pos_ridge_buffered, TARGET_VOL, is_intraday=True
)
pnl_pls, pos_pls = rescale_to_target_vol_util(pnl_pls, pos_pls, TARGET_VOL, is_intraday=True)
pnl_pls_buffered, pos_pls_buffered = rescale_to_target_vol_util(
    pnl_pls_buffered, pos_pls_buffered, TARGET_VOL, is_intraday=True
)

# Cum returns
cumret_raw = ret_scaled.cumsum()
cumret_weighted = np.log(1 + pnl_weighted).cumsum()
cumret_buffered = np.log(1 + pnl_weighted_buffered).cumsum()
cumret_ridge = np.log(1 + pnl_ridge).cumsum()
cumret_ridge_buffered = np.log(1 + pnl_ridge_buffered).cumsum()
cumret_pls = np.log(1 + pnl_pls).cumsum()
cumret_pls_buffered = np.log(1 + pnl_pls_buffered).cumsum()

# Daily series for stats
ret_daily = resample_pnl_to_daily(ret_scaled, dates)
pnl_weighted_daily = resample_pnl_to_daily(pnl_weighted, dates)
pnl_buffered_daily = resample_pnl_to_daily(pnl_weighted_buffered, dates)
pnl_ridge_daily = resample_pnl_to_daily(pnl_ridge, dates)
pnl_ridge_buffered_daily = resample_pnl_to_daily(pnl_ridge_buffered, dates)
pnl_pls_daily = resample_pnl_to_daily(pnl_pls, dates)
pnl_pls_buffered_daily = resample_pnl_to_daily(pnl_pls_buffered, dates)

stats_raw = build_stats(ret_daily, is_raw=True)
stats_weighted = build_stats(pnl_weighted_daily, is_raw=False)
stats_buffered = build_stats(pnl_buffered_daily, is_raw=False)
stats_ridge = build_stats(pnl_ridge_daily, is_raw=False)
stats_ridge_buffered = build_stats(pnl_ridge_buffered_daily, is_raw=False)
stats_pls = build_stats(pnl_pls_daily, is_raw=False)
stats_pls_buffered = build_stats(pnl_pls_buffered_daily, is_raw=False)

alpha_weighted, beta_weighted = alpha_beta(pnl_weighted_daily, ret_daily)
alpha_buffered, beta_buffered = alpha_beta(pnl_buffered_daily, ret_daily)
alpha_ridge, beta_ridge = alpha_beta(pnl_ridge_daily, ret_daily)
alpha_ridge_buffered, beta_ridge_buffered = alpha_beta(pnl_ridge_buffered_daily, ret_daily)
alpha_pls, beta_pls_out = alpha_beta(pnl_pls_daily, ret_daily)
alpha_pls_buffered, beta_pls_buffered_out = alpha_beta(pnl_pls_buffered_daily, ret_daily)

turnover_weighted = annual_turnover(pos_weighted, is_intraday=True)
turnover_buffered = annual_turnover(pos_weighted_buffered, is_intraday=True)
turnover_ridge = annual_turnover(pos_ridge, is_intraday=True)
turnover_ridge_buffered = annual_turnover(pos_ridge_buffered, is_intraday=True)
turnover_pls = annual_turnover(pos_pls, is_intraday=True)
turnover_pls_buffered = annual_turnover(pos_pls_buffered, is_intraday=True)

cm_raw = cost_metrics(0.0, stats_raw["Ann vol (%)"], stats_raw["Sharpe"])
cm_weighted = cost_metrics(turnover_weighted, stats_weighted["Ann vol (%)"], stats_weighted["Sharpe"])
cm_buffered = cost_metrics(turnover_buffered, stats_buffered["Ann vol (%)"], stats_buffered["Sharpe"])
cm_ridge = cost_metrics(turnover_ridge, stats_ridge["Ann vol (%)"], stats_ridge["Sharpe"])
cm_ridge_buffered = cost_metrics(turnover_ridge_buffered, stats_ridge_buffered["Ann vol (%)"], stats_ridge_buffered["Sharpe"])
cm_pls = cost_metrics(turnover_pls, stats_pls["Ann vol (%)"], stats_pls["Sharpe"])
cm_pls_buffered = cost_metrics(turnover_pls_buffered, stats_pls_buffered["Ann vol (%)"], stats_pls_buffered["Sharpe"])

fig = go.Figure()
if show_raw:
    fig.add_trace(go.Scatter(x=dates, y=cumret_raw, mode="lines", name="Raw", line=dict(width=2)))
if show_weighted:
    fig.add_trace(go.Scatter(x=dates, y=cumret_weighted, mode="lines", name="Weighted", line=dict(width=2)))
if show_buffered:
    fig.add_trace(go.Scatter(x=dates, y=cumret_buffered, mode="lines", name="Weighted (buffered)", line=dict(width=2)))
if show_ridge:
    fig.add_trace(go.Scatter(x=dates, y=cumret_ridge, mode="lines", name="Ridge", line=dict(width=2)))
if show_ridge_buffered:
    fig.add_trace(go.Scatter(x=dates, y=cumret_ridge_buffered, mode="lines", name="Ridge (buffered)", line=dict(width=2)))
if show_pls:
    fig.add_trace(go.Scatter(x=dates, y=cumret_pls, mode="lines", name="PLS", line=dict(width=2)))
if show_pls_buffered:
    fig.add_trace(go.Scatter(x=dates, y=cumret_pls_buffered, mode="lines", name="PLS (buffered)", line=dict(width=2)))
fig.update_layout(
    title=f"{symbol} Combined old strategies (all variants)",
    xaxis_title="Date",
    yaxis_title="Cumulative log return",
    template="plotly_white",
    height=500,
    showlegend=True,
)
fig.update_xaxes(rangeslider_visible=False)

with col_main:
    st.plotly_chart(fig, use_container_width=True)

# Position level (under PnL)
fig_pos = go.Figure()
if show_weighted:
    fig_pos.add_trace(go.Scatter(x=dates, y=pos_weighted, mode="lines", name="Weighted", line=dict(width=1)))
if show_buffered:
    fig_pos.add_trace(go.Scatter(x=dates, y=pos_weighted_buffered, mode="lines", name="Weighted (buffered)", line=dict(width=1)))
if show_ridge:
    fig_pos.add_trace(go.Scatter(x=dates, y=pos_ridge, mode="lines", name="Ridge", line=dict(width=1)))
if show_ridge_buffered:
    fig_pos.add_trace(go.Scatter(x=dates, y=pos_ridge_buffered, mode="lines", name="Ridge (buffered)", line=dict(width=1)))
if show_pls:
    fig_pos.add_trace(go.Scatter(x=dates, y=pos_pls, mode="lines", name="PLS", line=dict(width=1)))
if show_pls_buffered:
    fig_pos.add_trace(go.Scatter(x=dates, y=pos_pls_buffered, mode="lines", name="PLS (buffered)", line=dict(width=1)))
fig_pos.update_layout(
    title=f"{symbol} Position",
    xaxis_title="Date",
    yaxis_title="Position",
    template="plotly_white",
    height=300,
    showlegend=True,
)
fig_pos.update_xaxes(rangeslider_visible=False)
with col_main:
    st.plotly_chart(fig_pos, use_container_width=True)

# Position change time series (under PnL)
pos_chg_weighted = pos_weighted.diff()
pos_chg_buffered = pos_weighted_buffered.diff()
pos_chg_ridge = pos_ridge.diff()
pos_chg_ridge_buffered = pos_ridge_buffered.diff()
pos_chg_pls = pos_pls.diff()
pos_chg_pls_buffered = pos_pls_buffered.diff()
fig_pos_chg = go.Figure()
fig_pos_chg.add_trace(go.Scatter(x=dates, y=pos_chg_weighted, mode="lines", name="Weighted Δpos", line=dict(width=1)))
fig_pos_chg.add_trace(go.Scatter(x=dates, y=pos_chg_buffered, mode="lines", name="Weighted buffered Δpos", line=dict(width=1)))
fig_pos_chg.add_trace(go.Scatter(x=dates, y=pos_chg_ridge, mode="lines", name="Ridge Δpos", line=dict(width=1)))
fig_pos_chg.add_trace(go.Scatter(x=dates, y=pos_chg_ridge_buffered, mode="lines", name="Ridge buffered Δpos", line=dict(width=1)))
fig_pos_chg.add_trace(go.Scatter(x=dates, y=pos_chg_pls, mode="lines", name="PLS Δpos", line=dict(width=1)))
fig_pos_chg.add_trace(go.Scatter(x=dates, y=pos_chg_pls_buffered, mode="lines", name="PLS buffered Δpos", line=dict(width=1)))
fig_pos_chg.update_layout(
    title=f"{symbol} Position change (Δ position)",
    xaxis_title="Date",
    yaxis_title="Position change",
    template="plotly_white",
    height=300,
    showlegend=True,
)
fig_pos_chg.update_xaxes(rangeslider_visible=False)
with col_main:
    st.plotly_chart(fig_pos_chg, use_container_width=True)

# Histogram of position change
pos_chg_flat = pos_chg_weighted.dropna()
fig_hist = go.Figure()
fig_hist.add_trace(go.Histogram(x=pos_chg_flat, name="Weighted Δpos", nbinsx=80))
fig_hist.update_layout(
    title=f"{symbol} Histogram of position change",
    xaxis_title="Position change",
    yaxis_title="Count",
    template="plotly_white",
    height=300,
    showlegend=False,
)
with col_main:
    st.plotly_chart(fig_hist, use_container_width=True)

rows_table = [
    ("Ann return (%)", stats_raw["Ann return (%)"], stats_weighted["Ann return (%)"], stats_buffered["Ann return (%)"], stats_ridge["Ann return (%)"], stats_ridge_buffered["Ann return (%)"], stats_pls["Ann return (%)"], stats_pls_buffered["Ann return (%)"]),
    ("Ann vol (%)", stats_raw["Ann vol (%)"], stats_weighted["Ann vol (%)"], stats_buffered["Ann vol (%)"], stats_ridge["Ann vol (%)"], stats_ridge_buffered["Ann vol (%)"], stats_pls["Ann vol (%)"], stats_pls_buffered["Ann vol (%)"]),
    ("Sharpe", stats_raw["Sharpe"], stats_weighted["Sharpe"], stats_buffered["Sharpe"], stats_ridge["Sharpe"], stats_ridge_buffered["Sharpe"], stats_pls["Sharpe"], stats_pls_buffered["Sharpe"]),
    ("Sortino", stats_raw["Sortino"], stats_weighted["Sortino"], stats_buffered["Sortino"], stats_ridge["Sortino"], stats_ridge_buffered["Sortino"], stats_pls["Sortino"], stats_pls_buffered["Sortino"]),
    ("Max DD (%)", stats_raw["Max DD (%)"], stats_weighted["Max DD (%)"], stats_buffered["Max DD (%)"], stats_ridge["Max DD (%)"], stats_ridge_buffered["Max DD (%)"], stats_pls["Max DD (%)"], stats_pls_buffered["Max DD (%)"]),
    ("CDD95 (%)", stats_raw["CDD95 (%)"], stats_weighted["CDD95 (%)"], stats_buffered["CDD95 (%)"], stats_ridge["CDD95 (%)"], stats_ridge_buffered["CDD95 (%)"], stats_pls["CDD95 (%)"], stats_pls_buffered["CDD95 (%)"]),
    ("Calmar", stats_raw["Calmar"], stats_weighted["Calmar"], stats_buffered["Calmar"], stats_ridge["Calmar"], stats_ridge_buffered["Calmar"], stats_pls["Calmar"], stats_pls_buffered["Calmar"]),
    ("Ann turnover", 0.0, turnover_weighted, turnover_buffered, turnover_ridge, turnover_ridge_buffered, turnover_pls, turnover_pls_buffered),
    ("Holding period (days)", cm_raw["Holding period (days)"], cm_weighted["Holding period (days)"], cm_buffered["Holding period (days)"], cm_ridge["Holding period (days)"], cm_ridge_buffered["Holding period (days)"], cm_pls["Holding period (days)"], cm_pls_buffered["Holding period (days)"]),
    ("Ann cost (%)", cm_raw["Ann cost (%)"], cm_weighted["Ann cost (%)"], cm_buffered["Ann cost (%)"], cm_ridge["Ann cost (%)"], cm_ridge_buffered["Ann cost (%)"], cm_pls["Ann cost (%)"], cm_pls_buffered["Ann cost (%)"]),
    ("Cost/vol", cm_raw["Cost/vol"], cm_weighted["Cost/vol"], cm_buffered["Cost/vol"], cm_ridge["Cost/vol"], cm_ridge_buffered["Cost/vol"], cm_pls["Cost/vol"], cm_pls_buffered["Cost/vol"]),
    ("Net Sharpe", cm_raw["Net Sharpe"], cm_weighted["Net Sharpe"], cm_buffered["Net Sharpe"], cm_ridge["Net Sharpe"], cm_ridge_buffered["Net Sharpe"], cm_pls["Net Sharpe"], cm_pls_buffered["Net Sharpe"]),
    ("Alpha vs raw (ann %)", np.nan, alpha_weighted * 100 if not np.isnan(alpha_weighted) else np.nan, alpha_buffered * 100 if not np.isnan(alpha_buffered) else np.nan, alpha_ridge * 100 if not np.isnan(alpha_ridge) else np.nan, alpha_ridge_buffered * 100 if not np.isnan(alpha_ridge_buffered) else np.nan, alpha_pls * 100 if not np.isnan(alpha_pls) else np.nan, alpha_pls_buffered * 100 if not np.isnan(alpha_pls_buffered) else np.nan),
    ("Beta vs raw", np.nan, beta_weighted, beta_buffered, beta_ridge, beta_ridge_buffered, beta_pls_out, beta_pls_buffered_out),
]
stats_df = pd.DataFrame(
    rows_table,
    columns=["Metric", "Raw", "Weighted", "Weighted (buffered)", "Ridge", "Ridge (buffered)", "PLS", "PLS (buffered)"],
).set_index("Metric")

with col_main:
    st.dataframe(stats_df.style.format("{:.2f}", na_rep="-"), use_container_width=True)
    st.caption(f"Total hourly bars: {len(hourly)} | {hourly['datetime'].min()} → {hourly['datetime'].max()} (from {len(df_5m)} 5m bars)")
    st.caption(
        f"Weighted: WedThu(2×5%), EmaVol(4×5%), AccelVol(4×3.75%), BreakVol(4×5%), BlockVol(4×3.75%), "
        f"Rev(4×2.5%), OrthAlpha(4×5%). Ridge/PLS: 4 horizons ({'/'.join(horizon_labels)}), 26 variant betas."
    )
