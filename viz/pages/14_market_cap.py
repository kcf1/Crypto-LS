"""
Page: Plot Market Cap data.
Visualize market capitalization and related metrics over time (daily snapshots from CoinGecko).
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

DEFAULT_DAYS_BACK = 30  # Market cap updates daily, so 30 days = 30 data points

st.title("Market Cap")
st.caption(f"Plot market capitalization and related metrics from CoinGecko (daily snapshots). Data updates once per day.")

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
    
    show_price = st.checkbox(
        "Show Price",
        value=True,
        help="Display current price on secondary chart.",
    )
    
    show_supply = st.checkbox(
        "Show Supply Metrics",
        value=True,
        help="Display circulating supply and total supply.",
    )
    
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

# Calculate time range
end_time_ms = int(utc_now.timestamp() * 1000)
start_time_ms = int((utc_now - timedelta(days=days_back)).timestamp() * 1000)

# Read market cap data
rows = storage.read_market_cap(
    symbol=symbol,
    start_time=start_time_ms,
    end_time=end_time_ms,
)

if not rows:
    st.warning(
        f"No market cap data for **{symbol}** in the last {days_back} days. "
        "Run `scripts/backfill/backfill_market_cap.py` first."
    )
    st.stop()

# If only one data point, suggest running backfill for history
if len(rows) == 1:
    st.info(
        "Only **one snapshot** is stored. To see a time series, run the backfill: "
        "`python scripts/backfill/backfill_market_cap.py --days 7 --limit 20` "
        "(or omit `--limit` for all symbols; use `--days 30` for a full month)."
    )

df = pd.DataFrame(
    rows,
    columns=[
        "timestamp", "market_cap", "circulating_supply", "total_supply", "max_supply",
        "market_cap_rank", "fully_diluted_valuation", "current_price", "total_volume",
        "high_24h", "low_24h", "price_change_24h", "price_change_percentage_24h",
        "market_cap_change_24h", "market_cap_change_percentage_24h",
    ],
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
    current_mc = df["market_cap"].iloc[-1]
    st.metric("Current Market Cap", f"${current_mc/1e9:.2f}B" if current_mc >= 1e9 else f"${current_mc/1e6:.2f}M")
with col4:
    current_price = df["current_price"].iloc[-1]
    st.metric("Current Price", f"${current_price:,.2f}")

# Additional statistics
col1, col2, col3, col4 = st.columns(4)
with col1:
    avg_mc = df["market_cap"].mean()
    st.metric("Avg Market Cap", f"${avg_mc/1e9:.2f}B" if avg_mc >= 1e9 else f"${avg_mc/1e6:.2f}M")
with col2:
    current_rank = df["market_cap_rank"].iloc[-1] if df["market_cap_rank"].iloc[-1] is not None else "N/A"
    st.metric("Market Cap Rank", f"#{current_rank}" if current_rank != "N/A" else "N/A")
with col3:
    current_circ_supply = df["circulating_supply"].iloc[-1]
    st.metric("Circulating Supply", f"{current_circ_supply/1e9:.2f}B" if current_circ_supply >= 1e9 else f"{current_circ_supply/1e6:.2f}M")
with col4:
    current_volume = df["total_volume"].iloc[-1]
    st.metric("24h Volume", f"${current_volume/1e9:.2f}B" if current_volume >= 1e9 else f"${current_volume/1e6:.2f}M")

# Calculate number of subplots needed
num_subplots = 1  # Market cap is always shown
if show_price:
    num_subplots += 1
if show_supply:
    num_subplots += 1

# Create subplots
subplot_titles = [f"{symbol} Market Cap (last {days_back} days)"]
if show_price:
    subplot_titles.append(f"{symbol} Price")
if show_supply:
    subplot_titles.append(f"{symbol} Supply")

fig = make_subplots(
    rows=num_subplots,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.05,
    subplot_titles=subplot_titles,
    specs=[[{"secondary_y": False}] for _ in range(num_subplots)],
)

row_idx = 1

# Plot Market Cap
fig.add_trace(
    go.Scatter(
        x=df["datetime"],
        y=df["market_cap"],
        mode="lines+markers",
        name="Market Cap",
        line=dict(color="#1f77b4", width=2),
        marker=dict(size=5, color="#1f77b4"),
        hovertemplate="<b>%{fullData.name}</b><br>"
        "Date: %{x}<br>"
        "Market Cap: $%{y:,.0f}<br>"
        "<extra></extra>",
    ),
    row=row_idx,
    col=1,
)

# Add market cap rank annotation if available
if df["market_cap_rank"].notna().any():
    fig.add_trace(
        go.Scatter(
            x=df[df["market_cap_rank"].notna()]["datetime"],
            y=df[df["market_cap_rank"].notna()]["market_cap"],
            mode="markers+text",
            name="Rank",
            text=df[df["market_cap_rank"].notna()]["market_cap_rank"].astype(int).astype(str),
            textposition="top center",
            marker=dict(size=8, color="red", symbol="diamond"),
            hovertemplate="<b>Rank</b><br>"
            "Date: %{x}<br>"
            "Rank: #%{text}<br>"
            "<extra></extra>",
            showlegend=False,
        ),
        row=row_idx,
        col=1,
    )

row_idx += 1

# Plot Price if enabled
if show_price:
    fig.add_trace(
        go.Scatter(
            x=df["datetime"],
            y=df["current_price"],
            mode="lines+markers",
            name="Price",
            line=dict(color="#ff7f0e", width=2),
            marker=dict(size=4, color="#ff7f0e"),
            hovertemplate="<b>%{fullData.name}</b><br>"
            "Date: %{x}<br>"
            "Price: $%{y:,.2f}<br>"
            "<extra></extra>",
        ),
        row=row_idx,
        col=1,
    )
    
    # Add 24h high/low if available
    if df["high_24h"].notna().any() and df["low_24h"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=df["datetime"],
                y=df["high_24h"],
                mode="lines",
                name="24h High",
                line=dict(color="green", width=1, dash="dash"),
                opacity=0.5,
                hovertemplate="<b>24h High</b><br>Date: %{x}<br>High: $%{y:,.2f}<extra></extra>",
            ),
            row=row_idx,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["datetime"],
                y=df["low_24h"],
                mode="lines",
                name="24h Low",
                line=dict(color="red", width=1, dash="dash"),
                opacity=0.5,
                hovertemplate="<b>24h Low</b><br>Date: %{x}<br>Low: $%{y:,.2f}<extra></extra>",
            ),
            row=row_idx,
            col=1,
        )
    
    row_idx += 1

# Plot Supply if enabled
if show_supply:
    fig.add_trace(
        go.Scatter(
            x=df["datetime"],
            y=df["circulating_supply"],
            mode="lines+markers",
            name="Circulating Supply",
            line=dict(color="#2ca02c", width=2),
            marker=dict(size=4, color="#2ca02c"),
            hovertemplate="<b>%{fullData.name}</b><br>"
            "Date: %{x}<br>"
            "Circulating Supply: %{y:,.0f}<br>"
            "<extra></extra>",
        ),
        row=row_idx,
        col=1,
    )
    
    if df["total_supply"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=df[df["total_supply"].notna()]["datetime"],
                y=df[df["total_supply"].notna()]["total_supply"],
                mode="lines+markers",
                name="Total Supply",
                line=dict(color="#9467bd", width=2),
                marker=dict(size=4, color="#9467bd"),
                hovertemplate="<b>%{fullData.name}</b><br>"
                "Date: %{x}<br>"
                "Total Supply: %{y:,.0f}<br>"
                "<extra></extra>",
            ),
            row=row_idx,
            col=1,
        )
    
    if df["max_supply"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=df[df["max_supply"].notna()]["datetime"],
                y=df[df["max_supply"].notna()]["max_supply"],
                mode="lines+markers",
                name="Max Supply",
                line=dict(color="#8c564b", width=2, dash="dot"),
                marker=dict(size=4, color="#8c564b"),
                hovertemplate="<b>%{fullData.name}</b><br>"
                "Date: %{x}<br>"
                "Max Supply: %{y:,.0f}<br>"
                "<extra></extra>",
            ),
            row=row_idx,
            col=1,
        )
    
    row_idx += 1

# Update layout
fig.update_layout(
    height=300 * num_subplots,
    showlegend=True,
    hovermode="x unified",
    template="plotly_white",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
)

# Update x-axes
for i in range(1, num_subplots + 1):
    fig.update_xaxes(
        title_text="Date (UTC)" if i == num_subplots else "",
        row=i,
        col=1,
        showgrid=True,
        gridwidth=1,
        gridcolor="lightgray",
    )

# Update y-axes
fig.update_yaxes(
    title_text="Market Cap (USD)",
    row=1,
    col=1,
    showgrid=True,
    gridwidth=1,
    gridcolor="lightgray",
    tickformat="$,.0f",
)

if show_price:
    fig.update_yaxes(
        title_text="Price (USD)",
        row=2,
        col=1,
        showgrid=True,
        gridwidth=1,
        gridcolor="lightgray",
        tickformat="$,.2f",
    )

if show_supply:
    supply_row = 3 if show_price else 2
    fig.update_yaxes(
        title_text="Supply",
        row=supply_row,
        col=1,
        showgrid=True,
        gridwidth=1,
        gridcolor="lightgray",
        tickformat=",.0f",
    )

st.plotly_chart(fig, use_container_width=True)

# Display additional metrics
st.subheader("24h Changes")
col1, col2, col3, col4 = st.columns(4)
with col1:
    latest_change_24h = df["price_change_24h"].iloc[-1]
    latest_change_pct_24h = df["price_change_percentage_24h"].iloc[-1]
    if latest_change_24h is not None and latest_change_pct_24h is not None:
        st.metric(
            "Price Change (24h)",
            f"${latest_change_24h:,.2f}",
            f"{latest_change_pct_24h:.2f}%",
        )
    else:
        st.metric("Price Change (24h)", "N/A")
with col2:
    latest_mc_change_24h = df["market_cap_change_24h"].iloc[-1]
    latest_mc_change_pct_24h = df["market_cap_change_percentage_24h"].iloc[-1]
    if latest_mc_change_24h is not None and latest_mc_change_pct_24h is not None:
        st.metric(
            "Market Cap Change (24h)",
            f"${latest_mc_change_24h/1e9:.2f}B" if abs(latest_mc_change_24h) >= 1e9 else f"${latest_mc_change_24h/1e6:.2f}M",
            f"{latest_mc_change_pct_24h:.2f}%",
        )
    else:
        st.metric("Market Cap Change (24h)", "N/A")
with col3:
    latest_volume = df["total_volume"].iloc[-1]
    st.metric("24h Volume", f"${latest_volume/1e9:.2f}B" if latest_volume >= 1e9 else f"${latest_volume/1e6:.2f}M")
with col4:
    latest_fdv = df["fully_diluted_valuation"].iloc[-1]
    if latest_fdv is not None:
        st.metric("Fully Diluted Valuation", f"${latest_fdv/1e9:.2f}B" if latest_fdv >= 1e9 else f"${latest_fdv/1e6:.2f}M")
    else:
        st.metric("Fully Diluted Valuation", "N/A")

# Display data table (optional, collapsed by default); show date only (daily data)
with st.expander("📊 View Raw Data"):
    display_df = df[
        [
            "datetime", "market_cap", "market_cap_rank", "current_price",
            "circulating_supply", "total_supply", "max_supply",
            "total_volume", "price_change_percentage_24h", "market_cap_change_percentage_24h",
        ]
    ].copy()
    # Daily data: show date only (no time) to avoid redundant 00:00:00
    display_df["date"] = display_df["datetime"].dt.strftime("%Y-%m-%d")
    display_df = display_df.drop(columns=["datetime"])
    cols = ["date"] + [c for c in display_df.columns if c != "date"]
    display_df = display_df[cols]
    
    # Format columns for display
    display_df["market_cap"] = display_df["market_cap"].apply(lambda x: f"${x/1e9:.2f}B" if x >= 1e9 else f"${x/1e6:.2f}M")
    display_df["current_price"] = display_df["current_price"].apply(lambda x: f"${x:,.2f}")
    display_df["circulating_supply"] = display_df["circulating_supply"].apply(lambda x: f"{x/1e9:.2f}B" if x >= 1e9 else f"{x/1e6:.2f}M")
    display_df["total_supply"] = display_df["total_supply"].apply(lambda x: f"{x/1e9:.2f}B" if pd.notna(x) and x >= 1e9 else (f"{x/1e6:.2f}M" if pd.notna(x) else "N/A"))
    display_df["max_supply"] = display_df["max_supply"].apply(lambda x: f"{x/1e9:.2f}B" if pd.notna(x) and x >= 1e9 else (f"{x/1e6:.2f}M" if pd.notna(x) else "N/A"))
    display_df["total_volume"] = display_df["total_volume"].apply(lambda x: f"${x/1e9:.2f}B" if x >= 1e9 else f"${x/1e6:.2f}M")
    display_df["price_change_percentage_24h"] = display_df["price_change_percentage_24h"].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
    display_df["market_cap_change_percentage_24h"] = display_df["market_cap_change_percentage_24h"].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
    display_df["market_cap_rank"] = display_df["market_cap_rank"].apply(lambda x: f"#{int(x)}" if pd.notna(x) else "N/A")
    
    st.dataframe(
        display_df,
        use_container_width=True,
        height=400,
    )
