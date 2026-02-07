"""
Page: Mean reversion backtest on EOD data.

Signal = fades extreme short-term momentum when volume decay is high (indicating exhaustion).
Short-term mean reversion with volume filter. Standardized and vol-matched position.
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
    cost_metrics,
)

TIMEFRAME_5M = "5m"
BARS_PER_HOUR = 12  # 5m bars per hour

st.title("Mean reversion backtest")
st.caption(
    "5m data aggregated to hourly bars, signal = -sign(momentum) when |momentum| > threshold and volume decay > threshold, "
    "vol-matched position. Cum return = cumsum(log return)."
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
    vol_look1 = st.slider("Vol window (hours)", 24, 1440, 720, key="vol1_mr")
    reversal_look1 = st.slider("Reversal window (hours)", 1, 24, 6, key="rev1_mr")
    reversal_thresh1 = st.slider("Reversal threshold", 0.5, 3.0, 2.0, 0.1, key="rev_thresh1_mr")
    volume_thresh1 = st.slider("Volume threshold", 0.1, 0.9, 0.3, 0.05, key="vol_thresh1_mr")
    cap1 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap1_mr")

    st.subheader("Strategy 2")
    vol_look2 = st.slider("Vol window (hours)", 24, 1440, 720, key="vol2_mr")
    reversal_look2 = st.slider("Reversal window (hours)", 1, 24, 9, key="rev2_mr")
    reversal_thresh2 = st.slider("Reversal threshold", 0.5, 3.0, 2.0, 0.1, key="rev_thresh2_mr")
    volume_thresh2 = st.slider("Volume threshold", 0.1, 0.9, 0.3, 0.05, key="vol_thresh2_mr")
    cap2 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap2_mr")

    st.subheader("Strategy 3")
    vol_look3 = st.slider("Vol window (hours)", 24, 1440, 720, key="vol3_mr")
    reversal_look3 = st.slider("Reversal window (hours)", 1, 24, 12, key="rev3_mr")
    reversal_thresh3 = st.slider("Reversal threshold", 0.5, 3.0, 2.0, 0.1, key="rev_thresh3_mr")
    volume_thresh3 = st.slider("Volume threshold", 0.1, 0.9, 0.3, 0.05, key="vol_thresh3_mr")
    cap3 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap3_mr")

    st.divider()
    target_vol = st.slider("Target vol (ann) — all series", 0.05, 0.50, 0.30, 0.01, key="target_vol_mr")

    st.divider()
    show_raw = st.checkbox("Show Raw", value=True, key="show_raw_mr")
    show_s1 = st.checkbox("Show Strategy 1", value=True, key="show_s1_mr")
    show_s2 = st.checkbox("Show Strategy 2", value=True, key="show_s2_mr")
    show_s3 = st.checkbox("Show Strategy 3", value=True, key="show_s3_mr")
    show_avg = st.checkbox("Show Avg (1+2+3)", value=True, key="show_avg_mr")
    show_reg = st.checkbox("Show Reg (β≥0)", value=True, key="show_reg_mr")

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
volume = hourly["volume"]
dates = hourly["datetime"]


def run_strategy(
    vol_window: int,
    reversal_window: int,
    reversal_threshold: float,
    volume_threshold: float,
    target_vol_ann: float,
    cap: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Mean reversion strategy: fades extreme momentum when volume decay is high.
    
    Returns: (pnl, position, signal)
    """
    # 1. Volatility estimation
    vol_estimator = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR)
    vol_annualized = vol_estimator * np.sqrt(TRADING_HOURS_PER_YEAR)
    
    # 2. Volume decay: min-max normalize volume EWM
    volume_ewm = volume.ewm(span=vol_window, adjust=False).mean()
    volume_min = volume_ewm.rolling(window=vol_window).min()
    volume_max = volume_ewm.rolling(window=vol_window).max()
    volume_range = (volume_max - volume_min).clip(lower=VOL_FLOOR)
    volume_z = (volume_ewm - volume_min) / volume_range  # [0, 1]
    
    # 3. Momentum z-score: EMA(returns) / vol
    ret_ema = ret.ewm(span=reversal_window, adjust=False).mean()
    ret_z = ret_ema / vol_estimator
    
    # 4. Reversal signal: -sign(ret_z) only when conditions met
    signal = pd.Series(0.0, index=ret.index)
    condition = (ret_z.abs() > reversal_threshold) & (volume_z > volume_threshold)
    signal[condition] = -np.sign(ret_z[condition])
    
    # 5. Position sizing
    target_hourly = target_vol_ann / np.sqrt(TRADING_HOURS_PER_YEAR)
    position = (signal * target_hourly / vol_annualized).clip(-cap, cap)
    
    # 6. PnL calculation
    pnl = position.shift(1) * ret
    pnl = pnl.fillna(0)
    
    return pnl, position, signal


pnl1, pos1, s1 = run_strategy(vol_look1, reversal_look1, reversal_thresh1, volume_thresh1, target_vol, cap1)
pnl2, pos2, s2 = run_strategy(vol_look2, reversal_look2, reversal_thresh2, volume_thresh2, target_vol, cap2)
pnl3, pos3, s3 = run_strategy(vol_look3, reversal_look3, reversal_thresh3, volume_thresh3, target_vol, cap3)

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
    title=f"{symbol} Cumulative log return (mean reversion)",
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

cm_raw = cost_metrics(turnover_raw, stats_raw["Ann vol (%)"], stats_raw["Sharpe"])
cm1 = cost_metrics(turnover1, stats1["Ann vol (%)"], stats1["Sharpe"])
cm2 = cost_metrics(turnover2, stats2["Ann vol (%)"], stats2["Sharpe"])
cm3 = cost_metrics(turnover3, stats3["Ann vol (%)"], stats3["Sharpe"])
cm_avg = cost_metrics(turnover_avg, stats_avg["Ann vol (%)"], stats_avg["Sharpe"])
cm_reg = cost_metrics(turnover_reg, stats_reg["Ann vol (%)"], stats_reg["Sharpe"])

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
    ("Holding period (days)", cm_raw["Holding period (days)"], cm1["Holding period (days)"], cm2["Holding period (days)"], cm3["Holding period (days)"], cm_avg["Holding period (days)"], cm_reg["Holding period (days)"]),
    ("Ann cost (%)", cm_raw["Ann cost (%)"], cm1["Ann cost (%)"], cm2["Ann cost (%)"], cm3["Ann cost (%)"], cm_avg["Ann cost (%)"], cm_reg["Ann cost (%)"]),
    ("Cost/vol", cm_raw["Cost/vol"], cm1["Cost/vol"], cm2["Cost/vol"], cm3["Cost/vol"], cm_avg["Cost/vol"], cm_reg["Cost/vol"]),
    ("Net Sharpe", cm_raw["Net Sharpe"], cm1["Net Sharpe"], cm2["Net Sharpe"], cm3["Net Sharpe"], cm_avg["Net Sharpe"], cm_reg["Net Sharpe"]),
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
    st.caption("Signal: -sign(momentum) when |momentum z-score| > reversal_threshold and volume_z > volume_threshold, vol-matched × cap.")
