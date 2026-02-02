"""
Page: Plot Basis data.
Visualize basis (basis_rate, basis, futures_price, index_price) over time. 5m period.
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

@st.cache_resource
def get_storage():
    return Storage()

PERIOD = "5m"
DEFAULT_DAYS_BACK = 7

st.title("Basis")
st.caption("Plot basis (premium index) data from Storage. 5m period; Binance retains ~30 days.")

utc_now = datetime.now(timezone.utc)
st.info(f"🕐 Current UTC: **{utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}**")

storage = get_storage()
symbols = settings.symbols

with st.sidebar:
    symbol = st.selectbox("Symbol", symbols, index=0, help="Symbol to plot.")
    days_back = st.slider("Days back", min_value=1, max_value=30, value=DEFAULT_DAYS_BACK, help="Days of data (max 30 from API).")
    show_prices = st.checkbox("Show Futures & Index Price", value=True, help="Secondary y-axis: futures_price, index_price.")
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

end_time_ms = int(utc_now.timestamp() * 1000)
start_time_ms = int((utc_now - timedelta(days=days_back)).timestamp() * 1000)

rows = storage.read_basis(symbol=symbol, period=PERIOD, start_time=start_time_ms, end_time=end_time_ms)

if not rows:
    st.warning(f"No basis data for **{symbol}** ({PERIOD}) in the last {days_back} days. Run test_backfill_basis.py or backfill_basis.py first.")
    st.stop()

df = pd.DataFrame(rows, columns=["timestamp", "basis_rate", "basis", "futures_price", "index_price"])
df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
df = df.sort_values("datetime").reset_index(drop=True)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Records", f"{len(df):,}")
with col2:
    st.metric("Date Range", f"{df['datetime'].min().strftime('%Y-%m-%d')} to {df['datetime'].max().strftime('%Y-%m-%d')}")
with col3:
    st.metric("Current Basis Rate", f"{df['basis_rate'].iloc[-1]:.6f}")
with col4:
    st.metric("Current Basis", f"{df['basis'].iloc[-1]:.4f}")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Avg Basis Rate", f"{df['basis_rate'].mean():.6f}")
with col2:
    st.metric("Current Futures Price", f"${df['futures_price'].iloc[-1]:,.2f}")
with col3:
    st.metric("Current Index Price", f"${df['index_price'].iloc[-1]:,.2f}")
with col4:
    st.metric("Avg Basis", f"{df['basis'].mean():.4f}")

if show_prices:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.5],
        subplot_titles=(f"{symbol} Basis Rate (last {days_back} days)", f"{symbol} Futures & Index Price"),
    )
    fig.add_trace(
        go.Scatter(
            x=df["datetime"], y=df["basis_rate"], mode="lines+markers", name="Basis Rate",
            line=dict(color="#1f77b4", width=1.5), marker=dict(size=3),
            hovertemplate="Time: %{x}<br>Basis Rate: %{y:.6f}<extra></extra>",
        ),
        row=1, col=1,
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=1, col=1)
    fig.add_trace(
        go.Scatter(x=df["datetime"], y=df["futures_price"], mode="lines", name="Futures Price", line=dict(color="#ff7f0e")),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["datetime"], y=df["index_price"], mode="lines", name="Index Price", line=dict(color="#2ca02c")),
        row=2, col=1,
    )
    fig.update_layout(height=700, showlegend=True, hovermode="x unified", template="plotly_white")
    fig.update_xaxes(title_text="Time (UTC)", row=2, col=1)
    fig.update_yaxes(title_text="Basis Rate", row=1, col=1)
    fig.update_yaxes(title_text="Price (USD)", row=2, col=1)
else:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["datetime"], y=df["basis_rate"], mode="lines+markers", name="Basis Rate",
            line=dict(color="#1f77b4", width=1.5), marker=dict(size=3),
            hovertemplate="Time: %{x}<br>Basis Rate: %{y:.6f}<extra></extra>",
        ),
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(height=450, showlegend=True, hovermode="x unified", template="plotly_white", xaxis_title="Time (UTC)", yaxis_title="Basis Rate")

st.plotly_chart(fig, use_container_width=True)

with st.expander("📊 View Raw Data"):
    st.dataframe(df[["datetime", "basis_rate", "basis", "futures_price", "index_price"]].style.format({"basis_rate": "{:.6f}", "basis": "{:.4f}", "futures_price": "${:,.2f}", "index_price": "${:,.2f}"}), use_container_width=True, height=400)
