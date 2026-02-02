"""
Page: Plot Global Long/Short Account Ratio.
Visualize long_short_ratio, long_account, short_account over time. 5m period.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta, timezone

from config import settings
from data import Storage

@st.cache_resource
def get_storage():
    return Storage()

PERIOD = "5m"
DEFAULT_DAYS_BACK = 7

st.title("Global Long/Short Account Ratio")
st.caption("Plot global long/short account ratio (all traders). 5m period; Binance retains ~30 days.")

utc_now = datetime.now(timezone.utc)
st.info(f"🕐 Current UTC: **{utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}**")

storage = get_storage()
symbols = settings.symbols

with st.sidebar:
    symbol = st.selectbox("Symbol", symbols, index=0, help="Symbol to plot.")
    days_back = st.slider("Days back", min_value=1, max_value=30, value=DEFAULT_DAYS_BACK, help="Days of data (max 30 from API).")
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

end_time_ms = int(utc_now.timestamp() * 1000)
start_time_ms = int((utc_now - timedelta(days=days_back)).timestamp() * 1000)

rows = storage.read_global_long_short_account(symbol=symbol, period=PERIOD, start_time=start_time_ms, end_time=end_time_ms)

if not rows:
    st.warning(f"No global long/short account data for **{symbol}** ({PERIOD}) in the last {days_back} days. Run test_backfill_global_long_short_account.py first.")
    st.stop()

df = pd.DataFrame(rows, columns=["timestamp", "long_short_ratio", "long_account", "short_account"])
df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
df = df.sort_values("datetime").reset_index(drop=True)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Records", f"{len(df):,}")
with col2:
    st.metric("Date Range", f"{df['datetime'].min().strftime('%Y-%m-%d')} to {df['datetime'].max().strftime('%Y-%m-%d')}")
with col3:
    st.metric("Current L/S Ratio", f"{df['long_short_ratio'].iloc[-1]:.4f}")
with col4:
    st.metric("Long % / Short %", f"{df['long_account'].iloc[-1]*100:.2f}% / {df['short_account'].iloc[-1]*100:.2f}%")

fig = go.Figure()
fig.add_trace(go.Scatter(x=df["datetime"], y=df["long_short_ratio"], mode="lines+markers", name="Long/Short Ratio", line=dict(color="#1f77b4", width=1.5), marker=dict(size=3)))
fig.add_trace(go.Scatter(x=df["datetime"], y=df["long_account"], mode="lines", name="Long Account %", line=dict(color="#2ca02c", width=1)))
fig.add_trace(go.Scatter(x=df["datetime"], y=df["short_account"], mode="lines", name="Short Account %", line=dict(color="#d62728", width=1)))
fig.add_hline(y=1.0, line_dash="dash", line_color="gray", opacity=0.5, annotation_text="1.0")
fig.update_layout(height=500, showlegend=True, hovermode="x unified", template="plotly_white", xaxis_title="Time (UTC)", yaxis_title="Ratio / %", title=f"{symbol} Global L/S Account (last {days_back} days)")
st.plotly_chart(fig, use_container_width=True)

with st.expander("📊 View Raw Data"):
    display_df = df[["datetime", "long_short_ratio", "long_account", "short_account"]].copy()
    display_df["long_account"] = (display_df["long_account"] * 100).round(2).astype(str) + "%"
    display_df["short_account"] = (display_df["short_account"] * 100).round(2).astype(str) + "%"
    st.dataframe(display_df.style.format({"long_short_ratio": "{:.4f}"}), use_container_width=True, height=400)
