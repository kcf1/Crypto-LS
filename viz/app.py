"""
Streamlit app: Crypto-LS viz. Home; use sidebar for pages (e.g. Check OHLC data).
Run from project root: streamlit run viz/app.py
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
)

st.title("Crypto-LS Viz")
st.markdown(
    "Use the **sidebar** to open pages:\n"
    "- **Check OHLC data** — plot downloaded OHLC + volume (symbol/timeframe selectors).\n"
    "- **Eod bar** — plot EOD close derived from 5m data (last 5m close per day).\n"
    "- **Vol-target backtest** — EOD vol-target backtest with log returns, 3 strategies, and annualized stats.\n"
    "- **Trend-following backtest** — EOD trend signal (fast/slow EMA), standardized, vol-matched position.\n"
    "- **Trend-following (volatility regime)** — Same as above with position scaled by rolling 1pct vol regime (lookback slider).\n"
    "- **Channel-breakout backtest** — Signal = (price - mid) / channel range × 3, 2d EMA smooth; vol-matched position."
)
st.caption("Data from Storage (DATABASE_URL when set, else SQLite). Extensible for backtesting later.")
