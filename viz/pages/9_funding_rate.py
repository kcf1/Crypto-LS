"""
Page: Plot Funding Rate data.
Visualize funding rate and mark price over time.
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

DEFAULT_DAYS_BACK = 30  # Funding rates update every 8 hours, so 30 days = ~90 data points

st.title("Funding Rate")
st.caption(f"Plot funding rate and mark price data from Storage (Postgres or SQLite). Funding rates update every 8 hours (00:00, 08:00, 16:00 UTC).")

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
        max_value=365,
        value=DEFAULT_DAYS_BACK,
        help="Number of days of historical data to display.",
    )
    
    show_mark_price = st.checkbox(
        "Show Mark Price",
        value=True,
        help="Display mark price on secondary y-axis.",
    )
    
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

# Calculate time range
end_time_ms = int(utc_now.timestamp() * 1000)
start_time_ms = int((utc_now - timedelta(days=days_back)).timestamp() * 1000)

# Read funding rate data
rows = storage.read_funding_rate(
    symbol=symbol,
    start_time=start_time_ms,
    end_time=end_time_ms,
)

if not rows:
    st.warning(
        f"No funding rate data for **{symbol}** in the last {days_back} days. "
        "Run `scripts/backfill/backfill_funding_rate.py` first."
    )
    st.stop()

df = pd.DataFrame(
    rows,
    columns=["funding_time", "funding_rate", "mark_price"],
)
df["datetime"] = pd.to_datetime(df["funding_time"], unit="ms", utc=True)

# Sort by datetime (should already be sorted, but ensure)
df = df.sort_values("datetime").reset_index(drop=True)

# Calculate funding rate as percentage for display
df["funding_rate_pct"] = df["funding_rate"] * 100

# Display statistics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Records", f"{len(df):,}")
with col2:
    st.metric("Date Range", f"{df['datetime'].min().strftime('%Y-%m-%d')} to {df['datetime'].max().strftime('%Y-%m-%d')}")
with col3:
    current_fr = df["funding_rate"].iloc[-1]
    st.metric("Current Funding Rate", f"{current_fr:.6f}", f"{current_fr * 100:.4f}%")
with col4:
    st.metric("Current Mark Price", f"${df['mark_price'].iloc[-1]:,.2f}")

# Additional statistics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Avg Funding Rate", f"{df['funding_rate'].mean():.6f}", f"{df['funding_rate'].mean() * 100:.4f}%")
with col2:
    st.metric("Min Funding Rate", f"{df['funding_rate'].min():.6f}", f"{df['funding_rate'].min() * 100:.4f}%")
with col3:
    st.metric("Max Funding Rate", f"{df['funding_rate'].max():.6f}", f"{df['funding_rate'].max() * 100:.4f}%")
with col4:
    st.metric("Avg Mark Price", f"${df['mark_price'].mean():,.2f}")

# Create subplots
if show_mark_price:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.6, 0.4],
        subplot_titles=(
            f"{symbol} Funding Rate (last {days_back} days)",
            f"{symbol} Mark Price",
        ),
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]],
    )
else:
    fig = make_subplots(
        rows=1,
        cols=1,
        subplot_titles=(f"{symbol} Funding Rate (last {days_back} days)",),
    )

# Plot Funding Rate
fig.add_trace(
    go.Scatter(
        x=df["datetime"],
        y=df["funding_rate"],
        mode="lines+markers",
        name="Funding Rate",
        line=dict(color="#1f77b4", width=1.5),
        marker=dict(size=4, color="#1f77b4"),
        hovertemplate="<b>%{fullData.name}</b><br>"
        "Time: %{x}<br>"
        "Funding Rate: %{y:.6f} (%{customdata:.4f}%)<br>"
        "<extra></extra>",
        customdata=df["funding_rate_pct"],
    ),
    row=1,
    col=1,
)

# Add zero line for funding rate
fig.add_hline(
    y=0,
    line_dash="dash",
    line_color="gray",
    opacity=0.5,
    annotation_text="Zero",
    row=1,
    col=1,
)

# Plot Mark Price if enabled
if show_mark_price:
    fig.add_trace(
        go.Scatter(
            x=df["datetime"],
            y=df["mark_price"],
            mode="lines",
            name="Mark Price",
            line=dict(color="#ff7f0e", width=1.5),
            hovertemplate="<b>%{fullData.name}</b><br>"
            "Time: %{x}<br>"
            "Mark Price: $%{y:,.2f}<br>"
            "<extra></extra>",
        ),
        row=2,
        col=1,
    )

# Update layout
fig.update_layout(
    height=800 if show_mark_price else 500,
    showlegend=True,
    hovermode="x unified",
    xaxis_title="Time (UTC)",
    yaxis_title="Funding Rate",
    yaxis2_title="Mark Price (USD)" if show_mark_price else None,
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
    row=2 if show_mark_price else 1,
    col=1,
    showgrid=True,
    gridwidth=1,
    gridcolor="lightgray",
)

# Update y-axes
fig.update_yaxes(
    title_text="Funding Rate",
    row=1,
    col=1,
    showgrid=True,
    gridwidth=1,
    gridcolor="lightgray",
    tickformat=".6f",
)

if show_mark_price:
    fig.update_yaxes(
        title_text="Mark Price (USD)",
        row=2,
        col=1,
        showgrid=True,
        gridwidth=1,
        gridcolor="lightgray",
        tickformat="$,.2f",
    )

st.plotly_chart(fig, use_container_width=True)

# Display data table (optional, collapsed by default)
with st.expander("📊 View Raw Data"):
    display_df = df[["datetime", "funding_rate", "funding_rate_pct", "mark_price"]].copy()
    display_df["funding_rate_pct"] = display_df["funding_rate_pct"].apply(lambda x: f"{x:.4f}%")
    st.dataframe(
        display_df.style.format(
            {
                "funding_rate": "{:.6f}",
                "mark_price": "${:,.2f}",
            }
        ),
        use_container_width=True,
        height=400,
    )
