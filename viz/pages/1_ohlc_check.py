"""
Page: Check downloaded OHLC data. Plot candlestick + volume for selected symbol/timeframe.
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

from config import settings
from data import Storage

st.title("Check downloaded OHLC data")
st.caption("Plot OHLC and volume from Storage (Postgres or SQLite).")

storage = Storage()
symbols = settings.symbols
timeframes = settings.timeframes

with st.sidebar:
    symbol = st.selectbox(
        "Symbol",
        symbols,
        index=0,
        help="Symbol to plot (from settings.symbols).",
    )
    timeframe = st.selectbox(
        "Timeframe",
        timeframes,
        index=0,
        help="Timeframe (from settings.timeframes).",
    )
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

rows = storage.read_ohlcv(symbol=symbol, timeframe=timeframe)

if not rows:
    st.warning(
        f"No OHLCV data for **{symbol}** / **{timeframe}**. "
        "Run `scripts/download_last_24h.py` first."
    )
    st.stop()

df = pd.DataFrame(
    rows,
    columns=["open_time", "open", "high", "low", "close", "volume", "close_time"],
)
df["datetime"] = pd.to_datetime(df["open_time"], unit="ms")

fig = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.03,
    row_heights=[0.7, 0.3],
    subplot_titles=(f"{symbol} {timeframe}", "Volume"),
)
fig.add_trace(
    go.Candlestick(
        x=df["datetime"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="OHLC",
    ),
    row=1,
    col=1,
)
fig.add_trace(
    go.Bar(x=df["datetime"], y=df["volume"], name="Volume"),
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
    st.dataframe(df.tail(100), use_container_width=True)

st.caption(f"Total rows: {len(df)} | {df['datetime'].min()} → {df['datetime'].max()}")
