"""
Home page: welcome and overview.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

st.title("Crypto-LS Viz")
st.markdown(
    "Welcome to Crypto-LS Visualization Dashboard. "
    "Use the **sidebar** to navigate between different data views and backtesting tools."
)
st.caption("Data from Storage (DATABASE_URL when set, else SQLite). Extensible for backtesting later.")
