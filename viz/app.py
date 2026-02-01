"""
Streamlit app: OHLCV sanity checks from stored data (Postgres or SQLite).
Symbol/timeframe selectors, candlestick + volume chart.
Run from project root: streamlit run viz/app.py
"""

import sys
from pathlib import Path

# Ensure project root is on path when run as streamlit run viz/app.py
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import settings
from data import Storage

st.set_page_config(
    page_title="Crypto-LS OHLCV",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("OHLCV sanity checks")
st.caption("Data from Storage (DATABASE_URL when set, else SQLite). Extensible for backtesting later.")

storage = Storage()
symbols = settings.symbols
timeframes = settings.timeframes

with st.sidebar:
    symbol = st.selectbox(
        "Symbol",
        symbols,
        index=0,
        help="Symbol to visualise (from settings.symbols).",
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
    st.warning(f"No OHLCV data for **{symbol}** / **{timeframe}**. Run `scripts/download_last_24h.py` first.")
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
