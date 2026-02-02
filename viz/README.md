# Streamlit visualisation (Crypto-LS)

Sanity checks for downloaded OHLCV data; extensible for backtesting later.

## Setup

From project root:

```bash
pip install -r requirements.txt
```

(Includes `streamlit` and `plotly`.)

## Run

From **project root**:

```bash
python -m streamlit run viz/app.py
```

(Use `python -m streamlit` so the correct Python with streamlit installed is used; `streamlit` may not be on PATH.)

Browser opens at `http://localhost:8501`. Use the sidebar to pick **Symbol** and **Timeframe** (from `config.settings`). Candlestick + volume chart and a raw-data expander are shown.

## Data

- Reads from **Storage** (Postgres when `DATABASE_URL` is set, else SQLite).
- Run `scripts/utils/download_last_24h.py` first if you have no data.

## Later

- Add backtesting views and metrics in this app as needed.
