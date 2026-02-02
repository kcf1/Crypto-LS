"""
Page: Plot Open Interest data.
Visualize open interest (sum_open_interest and sum_open_interest_value) over time.
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

# Clear Streamlit cache to ensure latest Storage methods are loaded
@st.cache_resource
def get_storage():
    return Storage()

PERIOD = "5m"  # 5-minute periods
DEFAULT_DAYS_BACK = 7

st.title("Open Interest")
st.caption(f"Plot open interest data (sum_open_interest and sum_open_interest_value) from Storage (Postgres or SQLite).")

# Show current UTC time
utc_now = datetime.now(timezone.utc)
st.info(f"🕐 Current UTC time: **{utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}**")

storage = get_storage()
symbols = settings.symbols

with st.sidebar:
    symbol = st.selectbox(
        "Symbol",
        symbols,
        index=0,
        help="Symbol to plot (from settings.symbols).",
    )
    
    days_back = st.slider(
        "Days back",
        min_value=1,
        max_value=30,
        value=DEFAULT_DAYS_BACK,
        help="Number of days of historical data to display (max 30 days available from Binance).",
    )
    
    show_value = st.checkbox(
        "Show Open Interest Value (USD)",
        value=True,
        help="Display sum_open_interest_value in USD on secondary y-axis.",
    )
    
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

# Calculate time range
end_time_ms = int(utc_now.timestamp() * 1000)
start_time_ms = int((utc_now - timedelta(days=days_back)).timestamp() * 1000)

# Read open interest data
rows = storage.read_open_interest(
    symbol=symbol,
    period=PERIOD,
    start_time=start_time_ms,
    end_time=end_time_ms,
)

if not rows:
    st.warning(
        f"No **{PERIOD}** open interest data for **{symbol}** in the last {days_back} days. "
        "Run `scripts/backfill/backfill_open_interest.py` or `scripts/backfill/test_backfill_open_interest.py` first."
    )
    st.stop()

df = pd.DataFrame(
    rows,
    columns=["timestamp", "sum_open_interest", "sum_open_interest_value"],
)
df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

# Sort by datetime (should already be sorted, but ensure)
df = df.sort_values("datetime").reset_index(drop=True)

# Display statistics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Records", f"{len(df):,}")
with col2:
    st.metric("Date Range", f"{df['datetime'].min().strftime('%Y-%m-%d')} to {df['datetime'].max().strftime('%Y-%m-%d')}")
with col3:
    st.metric("Current OI", f"{df['sum_open_interest'].iloc[-1]:,.0f}")
with col4:
    st.metric("Current OI Value", f"${df['sum_open_interest_value'].iloc[-1]:,.0f}")

# Create subplots
if show_value:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.6, 0.4],
        subplot_titles=(
            f"{symbol} Open Interest (last {days_back} days)",
            f"{symbol} Open Interest Value (USD)",
        ),
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]],
    )
else:
    fig = make_subplots(
        rows=1,
        cols=1,
        subplot_titles=(f"{symbol} Open Interest (last {days_back} days)",),
    )

# Plot Open Interest (sum_open_interest)
fig.add_trace(
    go.Scatter(
        x=df["datetime"],
        y=df["sum_open_interest"],
        mode="lines",
        name="Open Interest",
        line=dict(color="#1f77b4", width=1.5),
        hovertemplate="<b>%{fullData.name}</b><br>"
        "Time: %{x}<br>"
        "OI: %{y:,.0f}<br>"
        "<extra></extra>",
    ),
    row=1 if show_value else 1,
    col=1,
)

# Plot Open Interest Value if enabled
if show_value:
    fig.add_trace(
        go.Scatter(
            x=df["datetime"],
            y=df["sum_open_interest_value"],
            mode="lines",
            name="Open Interest Value (USD)",
            line=dict(color="#ff7f0e", width=1.5),
            hovertemplate="<b>%{fullData.name}</b><br>"
            "Time: %{x}<br>"
            "Value: $%{y:,.0f}<br>"
            "<extra></extra>",
        ),
        row=2,
        col=1,
    )

# Update layout
fig.update_layout(
    height=800 if show_value else 500,
    showlegend=True,
    hovermode="x unified",
    xaxis_title="Time (UTC)",
    yaxis_title="Open Interest",
    yaxis2_title="Open Interest Value (USD)" if show_value else None,
    template="plotly_white",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
)

# Update x-axis
fig.update_xaxes(
    title_text="Time (UTC)",
    row=2 if show_value else 1,
    col=1,
    showgrid=True,
    gridwidth=1,
    gridcolor="lightgray",
)

# Update y-axes
fig.update_yaxes(
    title_text="Open Interest",
    row=1,
    col=1,
    showgrid=True,
    gridwidth=1,
    gridcolor="lightgray",
)

if show_value:
    fig.update_yaxes(
        title_text="Open Interest Value (USD)",
        row=2,
        col=1,
        showgrid=True,
        gridwidth=1,
        gridcolor="lightgray",
    )

st.plotly_chart(fig, use_container_width=True)

# Display data table (optional, collapsed by default)
with st.expander("📊 View Raw Data"):
    st.dataframe(
        df[["datetime", "sum_open_interest", "sum_open_interest_value"]].style.format(
            {
                "sum_open_interest": "{:,.0f}",
                "sum_open_interest_value": "${:,.2f}",
            }
        ),
        use_container_width=True,
        height=400,
    )
