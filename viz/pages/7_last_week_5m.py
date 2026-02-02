"""
Page: Plot last week of 5m OHLCV data.
Similar to Check OHLC data page, but filters to last 7 days of 5m data only.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime, timedelta, timezone

from config import settings
from data import Storage

TIMEFRAME_5M = "5m"
DAYS_BACK = 7

st.title("Last week 5m OHLCV")
st.caption(f"Plot last {DAYS_BACK} days of 5-minute OHLCV data from Storage (Postgres or SQLite).")

# Show current UTC time
utc_now = datetime.now(timezone.utc)
st.info(f"🕐 Current UTC time: **{utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}**")

storage = Storage()
symbols = settings.symbols

with st.sidebar:
    symbol = st.selectbox(
        "Symbol",
        symbols,
        index=0,
        help="Symbol to plot (from settings.symbols).",
    )
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

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
df["datetime"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)

# Filter to last 7 days (use UTC)
cutoff_time = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
df_filtered = df[df["datetime"] >= cutoff_time].copy()

if len(df_filtered) == 0:
    st.warning(
        f"No **5m** OHLCV data for **{symbol}** in the last {DAYS_BACK} days. "
        f"Latest data: {df['datetime'].max()}"
    )
    st.stop()

fig = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.03,
    row_heights=[0.7, 0.3],
    subplot_titles=(f"{symbol} {TIMEFRAME_5M} (last {DAYS_BACK} days)", "Volume"),
)
fig.add_trace(
    go.Candlestick(
        x=df_filtered["datetime"],
        open=df_filtered["open"],
        high=df_filtered["high"],
        low=df_filtered["low"],
        close=df_filtered["close"],
        name="OHLC",
    ),
    row=1,
    col=1,
)
fig.add_trace(
    go.Bar(x=df_filtered["datetime"], y=df_filtered["volume"], name="Volume"),
    row=2,
    col=1,
)
fig.update_layout(
    xaxis_rangeslider_visible=False,
    template="plotly_white",
    height=600,
)
fig.update_xaxes(title_text="Time", row=2, col=1)

st.plotly_chart(fig, use_container_width=True)

with st.expander("Raw data (last 100 rows)"):
    st.dataframe(df_filtered.tail(100), use_container_width=True)

st.caption(
    f"Filtered rows: {len(df_filtered)} | "
    f"{df_filtered['datetime'].min()} → {df_filtered['datetime'].max()} | "
    f"Total available: {len(df)} rows"
)
