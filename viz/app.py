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
    "- **Eod bar** — plot EOD close derived from 5m data (last 5m close per day)."
)
st.caption("Data from Storage (DATABASE_URL when set, else SQLite). Extensible for backtesting later.")
