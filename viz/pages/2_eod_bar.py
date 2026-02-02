"""
Page: End-of-day bar. EOD close derived from 5m data (last 5m close per day).
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import settings
from data import Storage

TIMEFRAME_5M = "5m"

st.title("End-of-day close")
st.caption("EOD close derived from 5m data: last 5m bar close per calendar day.")

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
df["datetime"] = pd.to_datetime(df["open_time"], unit="ms")
df["date"] = df["datetime"].dt.date

# Last 5m bar per day => EOD close
eod = df.groupby("date", as_index=False).agg(
    close=("close", "last"),
    open_time=("open_time", "last"),
)
eod = eod.sort_values("date").reset_index(drop=True)

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=eod["date"],
        y=eod["close"],
        mode="lines+markers",
        name="EOD close",
        line=dict(width=2),
    )
)
fig.update_layout(
    title=f"{symbol} EOD close (from 5m)",
    xaxis_title="Date",
    yaxis_title="Close",
    template="plotly_white",
    height=500,
    showlegend=True,
)
fig.update_xaxes(rangeslider_visible=False)

st.plotly_chart(fig, use_container_width=True)

with st.expander("Raw EOD close (last 100 days)"):
    st.dataframe(eod.tail(100), use_container_width=True)

st.caption(f"Total days: {len(eod)} | {eod['date'].min()} → {eod['date'].max()}")
