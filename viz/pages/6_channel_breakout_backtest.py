"""
Page: Channel-breakout backtest on EOD data.

Signal = (price - (rolling_high+rolling_low)/2) / (rolling_high - rolling_low) * 3,
smoothed with 2d EMA; position = vol-matched trend strength (signal * target_vol / vol_estimator).
Three PnL series with changeable parameters; same stats table as trend-following.
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
    rescale_to_target_vol as rescale_to_target_vol_util,
    build_stats,
    alpha_beta,
    annual_turnover,
)

TIMEFRAME_5M = "5m"
VOL_FLOOR = 1e-8
SIGNAL_SMOOTH_SPAN = 2  # 2d EMA on raw channel signal

st.title("Channel-breakout backtest")
st.caption(
    "EOD close, signal = (price - mid) / (high - low) × 3, smoothed 2d EMA; vol-matched position. Cum return = cumsum(log return)."
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
    channel1 = st.slider("Channel lookback (days)", 1, 30, 20, key="channel1_cb")
    vol_look1 = st.slider("Vol-estimator lookback (days)", 5, 90, 30, key="vol1_cb")
    cap1 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap1_cb")

    st.subheader("Strategy 2")
    channel2 = st.slider("Channel lookback (days)", 1, 30, 15, key="channel2_cb")
    vol_look2 = st.slider("Vol-estimator lookback (days)", 5, 90, 30, key="vol2_cb")
    cap2 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap2_cb")

    st.subheader("Strategy 3")
    channel3 = st.slider("Channel lookback (days)", 1, 30, 10, key="channel3_cb")
    vol_look3 = st.slider("Vol-estimator lookback (days)", 5, 90, 30, key="vol3_cb")
    cap3 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap3_cb")

    st.divider()
    target_vol = st.slider("Target vol (ann) — all series", 0.05, 0.50, 0.15, 0.01, key="target_vol_cb")

    st.divider()
    show_raw = st.checkbox("Show Raw", value=True, key="show_raw_cb")
    show_s1 = st.checkbox("Show Strategy 1", value=True, key="show_s1_cb")
    show_s2 = st.checkbox("Show Strategy 2", value=True, key="show_s2_cb")
    show_s3 = st.checkbox("Show Strategy 3", value=True, key="show_s3_cb")
    show_avg = st.checkbox("Show Avg (1+2+3)", value=True, key="show_avg_cb")
    show_reg = st.checkbox("Show Reg (β≥0)", value=True, key="show_reg_cb")

rows = storage.read_ohlcv(symbol=symbol, timeframe=TIMEFRAME_5M)
if not rows:
    st.warning(
        f"No **5m** OHLCV data for **{symbol}**. "
        "Run `scripts/utils/download_last_24h.py` or `scripts/backfill/update_5y_5m.py` first."
    )
    st.stop()

df = pd.DataFrame(
    rows,
    columns=["open_time", "open", "high", "low", "close", "volume", "close_time"],
)
df["datetime"] = pd.to_datetime(df["open_time"], unit="ms")
df["date"] = df["datetime"].dt.date
eod = df.groupby("date", as_index=False).agg(close=("close", "last"))
eod = eod.sort_values("date").reset_index(drop=True)

# Log return
eod["ret"] = np.log(eod["close"] / eod["close"].shift(1))
eod = eod.dropna(subset=["ret"]).reset_index(drop=True)
close = eod["close"]
ret = eod["ret"]
dates = eod["date"]


def run_strategy(
    channel_lookback: int,
    vol_lookback: int,
    target_vol_ann: float,
    cap: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    rolling_high = close.rolling(window=channel_lookback).max()
    rolling_low = close.rolling(window=channel_lookback).min()
    mid = (rolling_high + rolling_low) / 2
    channel_range = (rolling_high - rolling_low).clip(lower=VOL_FLOOR)
    signal_raw = (close - mid) / channel_range * 3
    signal_smooth = signal_raw.ewm(span=SIGNAL_SMOOTH_SPAN, adjust=False).mean()
    vol_estimator = ret.ewm(span=vol_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    target_daily = target_vol_ann / np.sqrt(TRADING_DAYS)
    position = (signal_smooth * target_daily / vol_estimator).clip(-cap, cap)
    pnl = position.shift(1) * ret
    pnl = pnl.fillna(0)
    return pnl, position, signal_smooth


pnl1, pos1, s1 = run_strategy(channel1, vol_look1, target_vol, cap1)
pnl2, pos2, s2 = run_strategy(channel2, vol_look2, target_vol, cap2)
pnl3, pos3, s3 = run_strategy(channel3, vol_look3, target_vol, cap3)

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
        # Use first half of data for training
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

# Rescale all series to match target vol
target_vol_daily = target_vol / np.sqrt(TRADING_DAYS)


def rescale_to_target_vol(pnl_series: pd.Series, pos_series: pd.Series = None) -> tuple:
    sd = pnl_series.std()
    scale = target_vol_daily / sd if sd > 1e-12 else 1.0
    pnl_scaled = pnl_series * scale
    pos_scaled = pos_series * scale if pos_series is not None else None
    return pnl_scaled, pos_scaled


ret_scaled, _ = rescale_to_target_vol(ret, None)
pnl1, pos1 = rescale_to_target_vol(pnl1, pos1)
pnl2, pos2 = rescale_to_target_vol(pnl2, pos2)
pnl3, pos3 = rescale_to_target_vol(pnl3, pos3)
pnl_avg, pos_avg = rescale_to_target_vol(pnl_avg, pos_avg)
pnl_reg, pos_reg = rescale_to_target_vol(pnl_reg, pos_reg)

# Cum return
cumret_raw = ret_scaled.cumsum()
cumret1 = np.log(1 + pnl1).cumsum()
cumret2 = np.log(1 + pnl2).cumsum()
cumret3 = np.log(1 + pnl3).cumsum()
cumret_avg = np.log(1 + pnl_avg).cumsum()
cumret_reg = np.log(1 + pnl_reg).cumsum()

fig = go.Figure()
if show_raw:
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumret_raw,
            mode="lines",
            name="Raw",
            line=dict(width=2),
        )
    )
if show_s1:
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumret1,
            mode="lines",
            name="Strategy 1",
            line=dict(width=1.5),
        )
    )
if show_s2:
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumret2,
            mode="lines",
            name="Strategy 2",
            line=dict(width=1.5),
        )
    )
if show_s3:
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumret3,
            mode="lines",
            name="Strategy 3",
            line=dict(width=1.5),
        )
    )
if show_avg:
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumret_avg,
            mode="lines",
            name="Avg (1+2+3)",
            line=dict(width=2),
        )
    )
if show_reg:
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumret_reg,
            mode="lines",
            name="Reg (β≥0)",
            line=dict(width=2),
        )
    )
fig.update_layout(
    title=f"{symbol} Cumulative log return (channel breakout)",
    xaxis_title="Date",
    yaxis_title="Cumulative log return",
    template="plotly_white",
    height=500,
    showlegend=True,
)
fig.update_xaxes(rangeslider_visible=False)
with col_main:
    st.plotly_chart(fig, use_container_width=True)

# Stats: use shared module (simpler stats for EOD backtests)


stats_raw = build_stats(ret_scaled, is_raw=True, include_all_metrics=False)
stats1 = build_stats(pnl1, is_raw=False, include_all_metrics=False)
stats2 = build_stats(pnl2, is_raw=False, include_all_metrics=False)
stats3 = build_stats(pnl3, is_raw=False, include_all_metrics=False)
stats_avg = build_stats(pnl_avg, is_raw=False, include_all_metrics=False)
stats_reg = build_stats(pnl_reg, is_raw=False, include_all_metrics=False)

alpha1, beta1 = alpha_beta(pnl1, ret_scaled)
alpha2, beta2 = alpha_beta(pnl2, ret_scaled)
alpha3, beta3 = alpha_beta(pnl3, ret_scaled)
alpha_avg, beta_avg = alpha_beta(pnl_avg, ret_scaled)
alpha_reg, beta_reg_out = alpha_beta(pnl_reg, ret_scaled)

turnover_raw = 0.0
turnover1 = annual_turnover(pos1, is_intraday=False)
turnover2 = annual_turnover(pos2, is_intraday=False)
turnover3 = annual_turnover(pos3, is_intraday=False)
turnover_avg = annual_turnover(pos_avg, is_intraday=False)
turnover_reg = annual_turnover(pos_reg, is_intraday=False)

rows_table = [
    ("Ann return (%)", stats_raw["Ann return (%)"], stats1["Ann return (%)"], stats2["Ann return (%)"], stats3["Ann return (%)"], stats_avg["Ann return (%)"], stats_reg["Ann return (%)"]),
    ("Ann vol (%)", stats_raw["Ann vol (%)"], stats1["Ann vol (%)"], stats2["Ann vol (%)"], stats3["Ann vol (%)"], stats_avg["Ann vol (%)"], stats_reg["Ann vol (%)"]),
    ("Sharpe", stats_raw["Sharpe"], stats1["Sharpe"], stats2["Sharpe"], stats3["Sharpe"], stats_avg["Sharpe"], stats_reg["Sharpe"]),
    ("Max DD (%)", stats_raw["Max DD (%)"], stats1["Max DD (%)"], stats2["Max DD (%)"], stats3["Max DD (%)"], stats_avg["Max DD (%)"], stats_reg["Max DD (%)"]),
    ("Avg DD (%)", stats_raw["Avg DD (%)"], stats1["Avg DD (%)"], stats2["Avg DD (%)"], stats3["Avg DD (%)"], stats_avg["Avg DD (%)"], stats_reg["Avg DD (%)"]),
    ("Calmar", stats_raw["Calmar"], stats1["Calmar"], stats2["Calmar"], stats3["Calmar"], stats_avg["Calmar"], stats_reg["Calmar"]),
    ("Skewness", stats_raw["Skewness"], stats1["Skewness"], stats2["Skewness"], stats3["Skewness"], stats_avg["Skewness"], stats_reg["Skewness"]),
    ("ES95 (%)", stats_raw["ES95 (%)"], stats1["ES95 (%)"], stats2["ES95 (%)"], stats3["ES95 (%)"], stats_avg["ES95 (%)"], stats_reg["ES95 (%)"]),
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
    
    st.caption(f"Total days: {len(eod)} | {eod['date'].min()} → {eod['date'].max()}")
    st.caption(
        f"Reg (β≥0): 4 models (1d/5d/10d/30d fwd ret/vol), avg betas = [{beta_reg[0]:.3f}, {beta_reg[1]:.3f}, {beta_reg[2]:.3f}] "
        f"(1d: [{beta_1d[0]:.2f},{beta_1d[1]:.2f},{beta_1d[2]:.2f}] 5d: [{beta_5d[0]:.2f},{beta_5d[1]:.2f},{beta_5d[2]:.2f}] "
        f"10d: [{beta_10d[0]:.2f},{beta_10d[1]:.2f},{beta_10d[2]:.2f}] 30d: [{beta_30d[0]:.2f},{beta_30d[1]:.2f},{beta_30d[2]:.2f}])"
    )
    st.caption("Signal: (close - (roll_high+roll_low)/2) / (roll_high - roll_low) × 3, then 2d EMA; position = vol-matched × cap.")
