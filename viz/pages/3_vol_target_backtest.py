"""
Page: Volatility-targeting backtest on EOD data.

Three PnL series with changeable parameters (span, target vol, cap); toggle-able
on the plot. Cumulative return = cumsum of log returns. Stats table: Raw + Strategy 1–3.
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

TIMEFRAME_5M = "5m"
TRADING_DAYS = 252
VOL_FLOOR = 1e-8

st.title("Vol-target backtest")
st.caption("EOD close, log returns, EWM vol, rebalance to target vol. Cum return = cumsum(log return).")

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

    st.divider()
    st.subheader("Strategy 1")
    span1 = st.slider("Vol window (days)", 5, 90, 30, key="span1")
    target_vol1 = st.slider("Target vol (ann)", 0.05, 0.50, 0.15, 0.01, key="tv1")
    cap1 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap1")

    st.subheader("Strategy 2")
    span2 = st.slider("Vol window (days)", 5, 90, 30, key="span2")
    target_vol2 = st.slider("Target vol (ann)", 0.05, 0.50, 0.15, 0.01, key="tv2")
    cap2 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap2")

    st.subheader("Strategy 3")
    span3 = st.slider("Vol window (days)", 5, 90, 30, key="span3")
    target_vol3 = st.slider("Target vol (ann)", 0.05, 0.50, 0.15, 0.01, key="tv3")
    cap3 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap3")

    st.divider()
    show_raw = st.checkbox("Show Raw", value=True, key="show_raw")
    show_s1 = st.checkbox("Show Strategy 1", value=True, key="show_s1")
    show_s2 = st.checkbox("Show Strategy 2", value=True, key="show_s2")
    show_s3 = st.checkbox("Show Strategy 3", value=True, key="show_s3")

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
ret = eod["ret"]
dates = eod["date"]

# Cum return raw = cumsum(log return)
cumret_raw = ret.cumsum()

def run_strategy(span: int, target_vol_ann: float, cap: float) -> tuple[pd.Series, pd.Series]:
    vol = ret.ewm(span=span, adjust=False).std()
    vol = vol.clip(lower=VOL_FLOOR)
    target_daily = target_vol_ann / np.sqrt(TRADING_DAYS)
    position = (target_daily / vol).clip(0, cap)
    pnl = position.shift(1) * ret
    pnl = pnl.fillna(0)
    return pnl, position

pnl1, pos1 = run_strategy(span1, target_vol1, cap1)
pnl2, pos2 = run_strategy(span2, target_vol2, cap2)
pnl3, pos3 = run_strategy(span3, target_vol3, cap3)

# Cum return strategy = cumsum(log(1+pnl))
cumret1 = np.log(1 + pnl1).cumsum()
cumret2 = np.log(1 + pnl2).cumsum()
cumret3 = np.log(1 + pnl3).cumsum()

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
fig.update_layout(
    title=f"{symbol} Cumulative log return (vol-target backtest)",
    xaxis_title="Date",
    yaxis_title="Cumulative log return",
    template="plotly_white",
    height=500,
    showlegend=True,
)
fig.update_xaxes(rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

# Stats: same date index for all series
def level_from_log(cumlog: pd.Series) -> pd.Series:
    return np.exp(cumlog) - 1

def max_drawdown(cumlog: pd.Series) -> float:
    level = level_from_log(cumlog)
    peak = level.cummax()
    dd = peak - level  # peak - trough, no denominator
    return float(dd.max()) * 100  # as %

def avg_drawdown(cumlog: pd.Series) -> float:
    level = level_from_log(cumlog)
    peak = level.cummax()
    dd = peak - level  # peak - trough, no denominator
    return float(dd.mean()) * 100  # as %

def alpha_beta(pnl: pd.Series, bench: pd.Series) -> tuple[float, float]:
    m = pnl.notna() & bench.notna()
    p = pnl[m].values
    b = bench[m].values
    if len(p) < 2 or b.var() == 0:
        return np.nan, np.nan
    beta = np.cov(p, b)[0, 1] / b.var()
    alpha = p.mean() - beta * b.mean()
    return alpha * TRADING_DAYS, beta

def es95(series: pd.Series) -> float:
    q = series.quantile(0.05)
    return float(series[series <= q].mean()) * 100

def annual_turnover(position: pd.Series) -> float:
    """Annual turnover = mean absolute daily position change * 252."""
    return float(position.diff().abs().mean()) * TRADING_DAYS

def build_stats(
    ret_series: pd.Series,
    name: str,
    is_raw: bool,
) -> dict:
    if is_raw:
        r = ret_series
        ann_ret = r.mean() * TRADING_DAYS * 100
        ann_vol = r.std() * np.sqrt(TRADING_DAYS) * 100
        cumlog = r.cumsum()
    else:
        r = ret_series
        ann_ret = r.mean() * TRADING_DAYS * 100
        ann_vol = r.std() * np.sqrt(TRADING_DAYS) * 100
        cumlog = np.log(1 + r).cumsum()
    sharpe = ann_ret / ann_vol if ann_vol else np.nan
    max_dd = max_drawdown(cumlog)
    calmar = ann_ret / max_dd if max_dd else np.nan  # ann_ret and max_dd in %
    avg_dd = avg_drawdown(cumlog)
    skew = float(r.skew()) if len(r) else np.nan
    es = es95(r)
    return {
        "Ann return (%)": ann_ret,
        "Ann vol (%)": ann_vol,
        "Sharpe": sharpe,
        "Max DD (%)": max_dd,
        "Avg DD (%)": avg_dd,
        "Calmar": calmar,
        "Skewness": skew,
        "ES95 (%)": es,
    }

stats_raw = build_stats(ret, "Raw", is_raw=True)
stats1 = build_stats(pnl1, "Strategy 1", is_raw=False)
stats2 = build_stats(pnl2, "Strategy 2", is_raw=False)
stats3 = build_stats(pnl3, "Strategy 3", is_raw=False)

alpha1, beta1 = alpha_beta(pnl1, ret)
alpha2, beta2 = alpha_beta(pnl2, ret)
alpha3, beta3 = alpha_beta(pnl3, ret)

# Annual turnover: raw = 0 (buy-and-hold), strategy = mean |d position| * 252
turnover_raw = 0.0
turnover1 = annual_turnover(pos1)
turnover2 = annual_turnover(pos2)
turnover3 = annual_turnover(pos3)

rows_table = [
    ("Ann return (%)", stats_raw["Ann return (%)"], stats1["Ann return (%)"], stats2["Ann return (%)"], stats3["Ann return (%)"]),
    ("Ann vol (%)", stats_raw["Ann vol (%)"], stats1["Ann vol (%)"], stats2["Ann vol (%)"], stats3["Ann vol (%)"]),
    ("Sharpe", stats_raw["Sharpe"], stats1["Sharpe"], stats2["Sharpe"], stats3["Sharpe"]),
    ("Max DD (%)", stats_raw["Max DD (%)"], stats1["Max DD (%)"], stats2["Max DD (%)"], stats3["Max DD (%)"]),
    ("Avg DD (%)", stats_raw["Avg DD (%)"], stats1["Avg DD (%)"], stats2["Avg DD (%)"], stats3["Avg DD (%)"]),
    ("Calmar", stats_raw["Calmar"], stats1["Calmar"], stats2["Calmar"], stats3["Calmar"]),
    ("Skewness", stats_raw["Skewness"], stats1["Skewness"], stats2["Skewness"], stats3["Skewness"]),
    ("ES95 (%)", stats_raw["ES95 (%)"], stats1["ES95 (%)"], stats2["ES95 (%)"], stats3["ES95 (%)"]),
    ("Ann turnover", turnover_raw, turnover1, turnover2, turnover3),
    ("Alpha vs raw (ann %)", np.nan, alpha1 * 100 if not np.isnan(alpha1) else np.nan, alpha2 * 100 if not np.isnan(alpha2) else np.nan, alpha3 * 100 if not np.isnan(alpha3) else np.nan),
    ("Beta vs raw", np.nan, beta1, beta2, beta3),
]
stats_df = pd.DataFrame(
    rows_table,
    columns=["Metric", "Raw", "Strategy 1", "Strategy 2", "Strategy 3"],
).set_index("Metric")
st.dataframe(stats_df.style.format("{:.2f}", na_rep="-"), use_container_width=True)

st.caption(f"Total days: {len(eod)} | {eod['date'].min()} → {eod['date'].max()}")
