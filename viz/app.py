"""
Streamlit app: Crypto-LS viz. Home; use sidebar for pages.
Run from project root: streamlit run viz/app.py

Uses st.navigation with position="hidden" so only the custom grouped sidebar is shown.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

st.set_page_config(
    page_title="Crypto-LS Viz",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Crypto-LS Visualization Dashboard",
    },
)

# Define all pages; use position="hidden" to hide the default nav list.
# Paths are relative to this file (viz/app.py), so pages live in viz/pages/
pages = [
    st.Page("pages/0_home.py", title="Home", icon="🏠"),
    st.Page("pages/1_ohlc_check.py", title="Check OHLC Data", icon="📊"),
    st.Page("pages/2_eod_bar.py", title="EOD Bar", icon="📅"),
    st.Page("pages/7_last_week_5m.py", title="Last Week 5m OHLCV", icon="🕐"),
    st.Page("pages/3_vol_target_backtest.py", title="Vol-Target Backtest", icon="📉"),
    st.Page("pages/4_trend_following_backtest.py", title="Trend-Following Backtest", icon="📈"),
    st.Page("pages/5_trend_following_regime.py", title="Trend-Following (Regime)", icon="🔄"),
    st.Page("pages/6_channel_breakout_backtest.py", title="Channel-Breakout Backtest", icon="📊"),
    st.Page("pages/8_open_interest.py", title="Open Interest", icon="💹"),
    st.Page("pages/9_funding_rate.py", title="Funding Rate", icon="💰"),
    st.Page("pages/10_basis.py", title="Basis", icon="📐"),
    st.Page("pages/11_global_long_short_account.py", title="Global Long/Short Account", icon="👥"),
    st.Page("pages/12_top_long_short_account.py", title="Top Long/Short Account", icon="🏆"),
    st.Page("pages/13_top_long_short_position.py", title="Top Long/Short Position", icon="📊"),
    st.Page("pages/14_market_cap.py", title="Market Cap", icon="💎"),
]

pg = st.navigation(pages, position="hidden")

# Custom sidebar: grouped navigation only (no duplicate default list)
with st.sidebar:
    st.header("📊 Navigation")
    st.page_link("pages/0_home.py", label="Home", icon="🏠")

    with st.expander("📈 OHLCV Data (Spot)", expanded=False):
        st.page_link("pages/1_ohlc_check.py", label="Check OHLC Data", icon="📊")
        st.caption("Plot downloaded OHLC + volume (symbol/timeframe selectors)")
        st.page_link("pages/2_eod_bar.py", label="EOD Bar", icon="📅")
        st.caption("Plot EOD close derived from 5m data")
        st.page_link("pages/7_last_week_5m.py", label="Last Week 5m OHLCV", icon="🕐")
        st.caption("Plot last 7 days of 5-minute candlestick + volume")

    with st.expander("🎯 Backtesting", expanded=False):
        st.page_link("pages/3_vol_target_backtest.py", label="Vol-Target Backtest", icon="📉")
        st.caption("EOD vol-target backtest with log returns, 3 strategies")
        st.page_link("pages/4_trend_following_backtest.py", label="Trend-Following Backtest", icon="📈")
        st.caption("EOD trend signal (fast/slow EMA), standardized, vol-matched")
        st.page_link("pages/5_trend_following_regime.py", label="Trend-Following (Regime)", icon="🔄")
        st.caption("Same as above with position scaled by volatility regime")
        st.page_link("pages/6_channel_breakout_backtest.py", label="Channel-Breakout Backtest", icon="📊")
        st.caption("Signal = (price - mid) / channel range × 3, 2d EMA smooth")

    with st.expander("⚡ Futures Market Data (Binance)", expanded=False):
        st.page_link("pages/8_open_interest.py", label="Open Interest", icon="💹")
        st.caption("Plot open interest (sum_open_interest and sum_open_interest_value)")
        st.page_link("pages/9_funding_rate.py", label="Funding Rate", icon="💰")
        st.caption("Plot funding rate and mark price (updates every 8 hours)")
        st.page_link("pages/10_basis.py", label="Basis", icon="📐")
        st.caption("Plot basis (premium index: basis_rate, basis, futures_price, index_price)")
        st.page_link("pages/11_global_long_short_account.py", label="Global Long/Short Account", icon="👥")
        st.caption("Plot global long/short account ratio (all traders; 5m)")
        st.page_link("pages/12_top_long_short_account.py", label="Top Long/Short Account", icon="🏆")
        st.caption("Plot top trader long/short account ratio (5m)")
        st.page_link("pages/13_top_long_short_position.py", label="Top Long/Short Position", icon="📊")
        st.caption("Plot top trader long/short position ratio (5m)")

    with st.expander("🌐 External Data (CoinGecko)", expanded=False):
        st.page_link("pages/14_market_cap.py", label="Market Cap", icon="💎")
        st.caption("Plot market capitalization and related metrics (daily snapshots)")

    st.divider()
    st.caption("💡 Tip: Use expanders to navigate between page groups")

pg.run()
