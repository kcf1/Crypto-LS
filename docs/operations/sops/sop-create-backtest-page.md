# SOP: Creating a Backtest Visualization Page

This SOP documents the step-by-step process for creating a new backtest visualization page in the Streamlit app, following the established patterns used in existing backtest pages (vol-target, trend-following, channel-breakout).

## Overview

A backtest page typically includes:
1. **Data Loading** - Fetch OHLCV data from storage
2. **Sidebar Controls** - Symbol selector, strategy parameters, display toggles
3. **Strategy Logic** - Core backtest function(s) that compute positions and PnL
4. **Visualization** - Plotly chart showing cumulative returns
5. **Statistics Table** - Performance metrics comparison across strategies
6. **Registration** - Add page to `app.py` navigation

---

## Step 1: Create the Page File

### 1.1 File Location and Naming

- **Location**: `viz/pages/`
- **Naming**: `{number}_{descriptive_name}_backtest.py`
  - Use sequential numbering (check existing pages for next number)
  - Use descriptive name matching the strategy (e.g., `7_momentum_backtest.py`)
  - Keep `_backtest.py` suffix for consistency

### 1.2 File Template Structure

```python
"""
Page: [Strategy name] backtest on EOD data.

[Brief description of signal and position logic]
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
# Add sklearn imports if using regression/ML (e.g., RidgeCV)

from config import settings
from data import Storage
from viz.backtest_utils import (
    TRADING_DAYS,
    TRADING_HOURS_PER_YEAR,
    VOL_FLOOR,
    prepare_daily_stats_series,
    rescale_to_target_vol as rescale_to_target_vol_util,
    build_stats,
    alpha_beta,
    annual_turnover,
    cost_metrics,
)

# Constants (if page-specific, otherwise use from utils)
TIMEFRAME_5M = "5m"
# Note: TRADING_DAYS=360 (crypto 24/7), TRADING_HOURS_PER_YEAR=8640, VOL_FLOOR from viz.backtest_utils
# Use TRADING_DAYS for annualization in statistics (after resampling to daily)
# Use TRADING_HOURS_PER_YEAR only for intraday position sizing and volatility calculations

# Page title and caption
st.title("[Strategy Name] backtest")
st.caption("[Brief description of signal logic and position calculation]")

# [Rest of the code follows...]
```

---

## Step 2: Set Up Layout and Controls

### 2.1 Layout: Left Sidebar + Main Area with Right Controls

**Sliders and strategy controls go on the right** of the main content area, not in the left sidebar. Use this layout:

- **Left sidebar (`st.sidebar`)**: Symbol selector and database label only.
- **Main area**: Two columns — **left column (`col_main`)** for charts and statistics table, **right column (`col_controls`)** for all sliders and display toggles.

```python
storage = Storage()
symbols = settings.symbols

# Left sidebar: symbol and storage info only
with st.sidebar:
    symbol = st.selectbox(
        "Symbol",
        symbols,
        index=0,
        help="Symbol (from settings.symbols).",
    )
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

# Main area: wide left column (content) + narrow right column (controls)
col_main, col_controls = st.columns([3, 1])
```

**Important**: All strategy parameter sliders and display checkboxes must be placed inside `with col_controls:` so they appear on the **right**. All charts (`st.plotly_chart`) and the statistics table (`st.dataframe`) must be placed inside `with col_main:`.

### 2.2 Strategy Parameter Sections (Right Column)

**Pattern**: Create 3 strategy variants with independent parameters. Place all of these inside `with col_controls:`.

```python
with col_controls:
    st.subheader("Strategy 1")
    param1_1 = st.slider("Parameter 1", min_val, max_val, default_val, step, key="param1_1")
    param1_2 = st.slider("Parameter 2", min_val, max_val, default_val, step, key="param1_2")
    # ... more parameters

    st.subheader("Strategy 2")
    param2_1 = st.slider("Parameter 1", min_val, max_val, default_val, step, key="param2_1")
    # ... (use unique keys: param2_*, param3_*)

    st.subheader("Strategy 3")
    param3_1 = st.slider("Parameter 1", min_val, max_val, default_val, step, key="param3_1")
    # ...

    st.divider()
    target_vol = st.slider("Target vol (ann) — all series", 0.05, 0.50, 0.15, 0.01, key="target_vol")
```

**Key Naming Convention**: Use unique keys for each slider to avoid conflicts (e.g., `fast1`, `fast2`, `fast3` or `channel1_cb`, `channel2_cb`).

### 2.3 Display Toggles (Right Column)

Place display toggles in the same right column, still inside `with col_controls:`:

```python
    st.divider()
    show_raw = st.checkbox("Show Raw", value=True, key="show_raw_[suffix]")
    show_s1 = st.checkbox("Show Strategy 1", value=True, key="show_s1_[suffix]")
    show_s2 = st.checkbox("Show Strategy 2", value=True, key="show_s2_[suffix]")
    show_s3 = st.checkbox("Show Strategy 3", value=True, key="show_s3_[suffix]")
    show_avg = st.checkbox("Show Avg (1+2+3)", value=True, key="show_avg_[suffix]")
    show_reg = st.checkbox("Show Reg (β≥0)", value=True, key="show_reg_[suffix]")
```

**Note**: Use unique suffix in keys (e.g., `_tf` for trend-following, `_cb` for channel-breakout) to avoid conflicts when switching pages.

---

## Step 3: Load and Prepare Data

### 3.1 Load OHLCV Data

```python
rows = storage.read_ohlcv(symbol=symbol, timeframe=TIMEFRAME_5M)
if not rows:
    st.warning(
        f"No **5m** OHLCV data for **{symbol}**. "
        "Run `scripts/utils/download_last_24h.py` or `scripts/backfill/update_5y_5m.py` first."
    )
    st.stop()
```

### 3.2 Convert to EOD (End-of-Day) Data

**For EOD-based strategies**:

```python
df = pd.DataFrame(
    rows,
    columns=["open_time", "open", "high", "low", "close", "volume", "close_time"],
)
df["datetime"] = pd.to_datetime(df["open_time"], unit="ms")
df["date"] = df["datetime"].dt.date

# Aggregate to EOD (last close per day)
eod = df.groupby("date", as_index=False).agg(close=("close", "last"))
eod = eod.sort_values("date").reset_index(drop=True)

# Calculate log returns
eod["ret"] = np.log(eod["close"] / eod["close"].shift(1))
eod = eod.dropna(subset=["ret"]).reset_index(drop=True)

# Extract series for calculations
close = eod["close"]
ret = eod["ret"]
dates = eod["date"]
```

### 3.3 Convert to Intraday Bars (e.g., Hourly from 5m)

**For intraday-based strategies** (e.g., hourly bars from 5m data):

```python
df_5m = pd.DataFrame(
    rows,
    columns=["open_time", "open", "high", "low", "close", "volume", "close_time"],
)
df_5m["datetime"] = pd.to_datetime(df_5m["open_time"], unit="ms")
df_5m = df_5m.sort_values("datetime").reset_index(drop=True)

# Aggregate 5m to hourly bars
df_5m["hour"] = df_5m["datetime"].dt.floor("H")
hourly = df_5m.groupby("hour", as_index=False).agg(
    open=("open", "first"),
    high=("high", "max"),
    low=("low", "min"),
    close=("close", "last"),
    volume=("volume", "sum"),
)
hourly = hourly.sort_values("hour").reset_index(drop=True)
hourly["datetime"] = hourly["hour"]

# Calculate log returns (hourly)
hourly["ret"] = np.log(hourly["close"] / hourly["close"].shift(1))
hourly = hourly.dropna(subset=["ret"]).reset_index(drop=True)

# Extract series for calculations
close = hourly["close"]
ret = hourly["ret"]
dates = hourly["datetime"]
high = hourly["high"]
low = hourly["low"]
open_price = hourly["open"]

# Note: PnL will be calculated at hourly frequency, but MUST be resampled to daily
# before statistics (see Step 9.0)
```

---

## Step 4: Implement Strategy Function

### 4.1 Strategy Function Template

```python
def run_strategy(
    param1: int,
    param2: float,
    target_vol_ann: float,
    cap: float,
    # Add strategy-specific parameters
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Returns: (pnl, position, signal)
    - pnl: daily PnL series (position.shift(1) * ret)
    - position: position series (for turnover calculation)
    - signal: signal series (optional, for debugging/display)
    """
    # 1. Calculate signal
    # [Strategy-specific signal logic]
    
    # 2. Volatility estimation
    vol_estimator = ret.ewm(span=vol_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
    
    # 3. Position sizing (vol-matched)
    target_daily = target_vol_ann / np.sqrt(TRADING_DAYS)
    position = (signal * target_daily / vol_estimator).clip(-cap, cap)
    
    # 4. PnL calculation (shift position by 1 to avoid lookahead)
    pnl = position.shift(1) * ret
    pnl = pnl.fillna(0)
    
    return pnl, position, signal
```

### 4.2 Common Signal Patterns

**Trend Following (EMA Crossover)**:
```python
fast_ema = close.ewm(span=fast_lookback, adjust=False).mean()
slow_ema = close.ewm(span=slow_span, adjust=False).mean()
signal_raw = fast_ema - slow_ema
signal_std_series = signal_raw.ewm(span=std_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
signal_std = (signal_raw / signal_std_series).clip(-3, 3)
```

**Channel Breakout**:
```python
rolling_high = close.rolling(window=channel_lookback).max()
rolling_low = close.rolling(window=channel_lookback).min()
mid = (rolling_high + rolling_low) / 2
channel_range = (rolling_high - rolling_low).clip(lower=VOL_FLOOR)
signal_raw = (close - mid) / channel_range * 3
signal_smooth = signal_raw.ewm(span=SIGNAL_SMOOTH_SPAN, adjust=False).mean()
```

### 4.3 Run Strategies

```python
pnl1, pos1, s1 = run_strategy(param1_1, param1_2, target_vol, cap1)
pnl2, pos2, s2 = run_strategy(param2_1, param2_2, target_vol, cap2)
pnl3, pos3, s3 = run_strategy(param3_1, param3_2, target_vol, cap3)
```

---

## Step 5: Optional Aggregations

### 5.1 Simple Average

```python
pos_avg = (pos1 + pos2 + pos3) / 3
pnl_avg = pos_avg.shift(1) * ret
pnl_avg = pnl_avg.fillna(0)
```

### 5.2 Regression-Based Combination (Optional)

Use the shared `ridge_aggregation()` from `viz.backtest_utils`. It uses different forward-return horizons by data frequency:

- **Hourly data** (intraday): forward return labels **24h, 48h, 96h, 192h** (horizons 24, 48, 96, 192 periods).
- **Daily (EOD) data**: forward return labels **1d, 5d, 10d, 30d** (horizons 1, 5, 10, 30 periods).

Ridge fits vol-normalized forward returns on positions; trains on first half of data; returns average of the 4 horizon betas.

```python
from viz.backtest_utils import ridge_aggregation

# is_intraday_hourly=True for hourly bars (e.g. 5m→hourly), False for EOD
beta_reg, betas, horizon_labels = ridge_aggregation(
    pos1, pos2, pos3, ret, vol_ewm_span=30, is_intraday_hourly=False
)
# betas[0]..betas[3] correspond to horizon_labels[0]..horizon_labels[3] (e.g. "1d","5d","10d","30d" or "24h","48h","96h","192h")

pos_reg = beta_reg[0] * pos1 + beta_reg[1] * pos2 + beta_reg[2] * pos3
pnl_reg = pos_reg.shift(1) * ret
pnl_reg = pnl_reg.fillna(0)
```

For captions, use `horizon_labels` (e.g. `f"Reg: 4 models ({'/'.join(horizon_labels)} fwd ret/vol)"`).

**Many series (e.g. combined strategies):** Use `ridge_aggregation_multi(positions, ret, ...)` or `pls_aggregation_multi(positions, ret, ...)` from `viz.backtest_utils`. Same 4 horizons and train fraction; PLS uses `n_components` (default `min(10, n-1)`). Both return `(beta, betas, horizon_labels)`; combine with `pos = sum(beta[i] * positions[i] for i in range(len(positions)))`.

---

## Step 6: Rescale to Target Volatility

### 6.1 Rescaling Function

**Important**: Use the shared `rescale_to_target_vol` function from `viz.backtest_utils`. Do not define this function locally.

```python
# For EOD (daily) data:
ret_scaled, _ = rescale_to_target_vol_util(ret, None, target_vol, is_intraday=False)
pnl1, pos1 = rescale_to_target_vol_util(pnl1, pos1, target_vol, is_intraday=False)
pnl2, pos2 = rescale_to_target_vol_util(pnl2, pos2, target_vol, is_intraday=False)
pnl3, pos3 = rescale_to_target_vol_util(pnl3, pos3, target_vol, is_intraday=False)
pnl_avg, pos_avg = rescale_to_target_vol_util(pnl_avg, pos_avg, target_vol, is_intraday=False)
pnl_reg, pos_reg = rescale_to_target_vol_util(pnl_reg, pos_reg, target_vol, is_intraday=False)

# For intraday (hourly) data:
ret_scaled, _ = rescale_to_target_vol_util(ret, None, target_vol, is_intraday=True)
pnl1, pos1 = rescale_to_target_vol_util(pnl1, pos1, target_vol, is_intraday=True)
# ... (same pattern, but with is_intraday=True)
```

**Note**: The `rescale_to_target_vol_util` function automatically handles the correct volatility scaling based on the `is_intraday` parameter.

---

## Step 7: Calculate Cumulative Returns

```python
# Raw: cumsum of log returns
cumret_raw = ret_scaled.cumsum()

# Strategies: cumsum of log(1 + pnl)
cumret1 = np.log(1 + pnl1).cumsum()
cumret2 = np.log(1 + pnl2).cumsum()
cumret3 = np.log(1 + pnl3).cumsum()
cumret_avg = np.log(1 + pnl_avg).cumsum()
cumret_reg = np.log(1 + pnl_reg).cumsum()
```

---

## Step 8: Create Plotly Chart

### 8.1 Chart Setup

```python
fig = go.Figure()

if show_raw:
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumret_raw,
            mode="lines",
            name="Raw",
            line=dict(width=2),
        )
    )

if show_s1:
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumret1,
            mode="lines",
            name="Strategy 1",
            line=dict(width=1.5),
        )
    )

# Repeat for s2, s3, avg, reg...

fig.update_layout(
    title=f"{symbol} Cumulative log return ([strategy name])",
    xaxis_title="Date",
    yaxis_title="Cumulative log return",
    template="plotly_white",
    height=500,
    showlegend=True,
)
fig.update_xaxes(rangeslider_visible=False)
with col_main:
    st.plotly_chart(fig, use_container_width=True)
```

**Note**: The chart is placed inside `with col_main:` so it appears on the **left**; sliders remain on the right.

---

## Step 9: Statistics Table

### 9.0 Resample Intraday Data to Daily (if applicable)

**Important**: For all intraday series (e.g., 5m, 1h data), you must resample PnL to daily frequency before calculating statistics. This ensures meaningful annualized metrics and avoids inflated Sharpe ratios from high-frequency data.

**Use the shared `prepare_daily_stats_series` function from `viz.backtest_utils`**:

```python
# Prepare daily series for statistics (resample if intraday)
pnl1_for_stats, pnl2_for_stats, pnl3_for_stats, pnl_avg_for_stats, pnl_reg_for_stats, ret_scaled_for_stats = prepare_daily_stats_series(
    pnl1, pnl2, pnl3, pnl_avg, pnl_reg, ret_scaled, dates
)
```

This function automatically:
- Detects if data is intraday (checks length > 252 or datetime type)
- Resamples intraday PnL to daily by summing PnL within each day
- Returns daily series ready for statistics calculation
- For EOD data, returns series as-is (no resampling needed)

**Note**: 
- For EOD (end-of-day) data, the function will skip resampling automatically
- For intraday data (5m aggregated to hourly, or any sub-daily frequency), always use this function
- The resampling sums PnL within each day (not averaging), as PnL is additive
- Statistics are then calculated on daily PnL and annualized using `TRADING_DAYS = 360` (crypto 24/7)

### 9.1 Helper Functions

**Important**: **DO NOT define these functions locally**. All statistics helper functions are available in `viz.backtest_utils` and should be imported and used directly.

**Available functions in `viz.backtest_utils`**:
- `build_stats()` - Main statistics builder (supports full and simplified metrics)
- `alpha_beta()` - Calculate alpha and beta vs benchmark
- `annual_turnover()` - Calculate annual turnover
- `cost_metrics(ann_turnover, ann_vol_pct, sharpe)` - Holding period (days), Ann cost (%), Cost/vol, Net Sharpe (15 bps per trip assumed)
- `buffer_position(position, factor=2.0)` - Buffered position: only updates when gap > factor × mean(|Δposition|) (default factor 2; affects turnover)
- `max_drawdown()`, `avg_drawdown()`, `cvar95()`, `cdd95()`, `kurtosis_monthly()`, `sortino_ratio()`, `hit_rate()`, `profit_factor()` - Individual metric functions

**Usage**:
```python
# For pages with full metrics (hourly backtests):
stats_raw = build_stats(ret_scaled_for_stats, is_raw=True)
stats1 = build_stats(pnl1_for_stats, is_raw=False)
# ... etc

# For pages with simplified metrics (EOD backtests):
stats_raw = build_stats(ret_scaled_for_stats, is_raw=True, include_all_metrics=False)
stats1 = build_stats(pnl1_for_stats, is_raw=False, include_all_metrics=False)
# ... etc

# Alpha/Beta:
alpha1, beta1 = alpha_beta(pnl1_for_stats, ret_scaled_for_stats)

# Turnover (specify is_intraday parameter):
turnover1 = annual_turnover(pos1, is_intraday=False)  # For EOD data
turnover1 = annual_turnover(pos1, is_intraday=True)    # For hourly data
```

**If you need a function that doesn't exist in utils**:
1. Check if it's truly page-specific (only used in one page) → define locally
2. If it's common/shared functionality → add it to `viz/backtest_utils.py` first, then import and use it
3. Never duplicate common functions across multiple pages

### 9.2 Build Statistics Table

**Important**: Use the resampled daily series (`*_for_stats`) for all statistics calculations if you resampled in Step 9.0.

```python
# Use daily resampled series if applicable (from Step 9.0)
# For hourly backtests (full metrics):
stats_raw = build_stats(ret_scaled_for_stats, is_raw=True)
stats1 = build_stats(pnl1_for_stats, is_raw=False)
stats2 = build_stats(pnl2_for_stats, is_raw=False)
stats3 = build_stats(pnl3_for_stats, is_raw=False)
stats_avg = build_stats(pnl_avg_for_stats, is_raw=False)
stats_reg = build_stats(pnl_reg_for_stats, is_raw=False)

# For EOD backtests (simplified metrics):
stats_raw = build_stats(ret_scaled_for_stats, is_raw=True, include_all_metrics=False)
stats1 = build_stats(pnl1_for_stats, is_raw=False, include_all_metrics=False)
# ... etc

# Alpha/Beta calculations also use daily series
alpha1, beta1 = alpha_beta(pnl1_for_stats, ret_scaled_for_stats)
alpha2, beta2 = alpha_beta(pnl2_for_stats, ret_scaled_for_stats)
alpha3, beta3 = alpha_beta(pnl3_for_stats, ret_scaled_for_stats)
alpha_avg, beta_avg = alpha_beta(pnl_avg_for_stats, ret_scaled_for_stats)
alpha_reg, beta_reg_out = alpha_beta(pnl_reg_for_stats, ret_scaled_for_stats)

# Turnover: Use original position series (not resampled)
# Specify is_intraday parameter based on your data frequency
turnover_raw = 0.0
turnover1 = annual_turnover(pos1, is_intraday=False)  # For EOD data
turnover2 = annual_turnover(pos2, is_intraday=False)
turnover3 = annual_turnover(pos3, is_intraday=False)
turnover_avg = annual_turnover(pos_avg, is_intraday=False)
turnover_reg = annual_turnover(pos_reg, is_intraday=False)

# For hourly data:
# turnover1 = annual_turnover(pos1, is_intraday=True)
# ... etc

# Cost-adjusted metrics (add cost_metrics to backtest_utils imports): holding period, ann cost, cost/vol, net sharpe (15 bps per trip)
cm_raw = cost_metrics(turnover_raw, stats_raw["Ann vol (%)"], stats_raw["Sharpe"])
cm1 = cost_metrics(turnover1, stats1["Ann vol (%)"], stats1["Sharpe"])
cm2 = cost_metrics(turnover2, stats2["Ann vol (%)"], stats2["Sharpe"])
cm3 = cost_metrics(turnover3, stats3["Ann vol (%)"], stats3["Sharpe"])
cm_avg = cost_metrics(turnover_avg, stats_avg["Ann vol (%)"], stats_avg["Sharpe"])
cm_reg = cost_metrics(turnover_reg, stats_reg["Ann vol (%)"], stats_reg["Sharpe"])

rows_table = [
    ("Ann return (%)", stats_raw["Ann return (%)"], stats1["Ann return (%)"], stats2["Ann return (%)"], stats3["Ann return (%)"], stats_avg["Ann return (%)"], stats_reg["Ann return (%)"]),
    ("Ann vol (%)", stats_raw["Ann vol (%)"], stats1["Ann vol (%)"], stats2["Ann vol (%)"], stats3["Ann vol (%)"], stats_avg["Ann vol (%)"], stats_reg["Ann vol (%)"]),
    ("Sharpe", stats_raw["Sharpe"], stats1["Sharpe"], stats2["Sharpe"], stats3["Sharpe"], stats_avg["Sharpe"], stats_reg["Sharpe"]),
    ("Sortino", stats_raw["Sortino"], stats1["Sortino"], stats2["Sortino"], stats3["Sortino"], stats_avg["Sortino"], stats_reg["Sortino"]),
    ("Max DD (%)", stats_raw["Max DD (%)"], stats1["Max DD (%)"], stats2["Max DD (%)"], stats3["Max DD (%)"], stats_avg["Max DD (%)"], stats_reg["Max DD (%)"]),
    ("CDD95 (%)", stats_raw["CDD95 (%)"], stats1["CDD95 (%)"], stats2["CDD95 (%)"], stats3["CDD95 (%)"], stats_avg["CDD95 (%)"], stats_reg["CDD95 (%)"]),
    ("Avg DD (%)", stats_raw["Avg DD (%)"], stats1["Avg DD (%)"], stats2["Avg DD (%)"], stats3["Avg DD (%)"], stats_avg["Avg DD (%)"], stats_reg["Avg DD (%)"]),
    ("Calmar", stats_raw["Calmar"], stats1["Calmar"], stats2["Calmar"], stats3["Calmar"], stats_avg["Calmar"], stats_reg["Calmar"]),
    ("Skewness", stats_raw["Skewness"], stats1["Skewness"], stats2["Skewness"], stats3["Skewness"], stats_avg["Skewness"], stats_reg["Skewness"]),
    ("Kurtosis (mth)", stats_raw["Kurtosis (mth)"], stats1["Kurtosis (mth)"], stats2["Kurtosis (mth)"], stats3["Kurtosis (mth)"], stats_avg["Kurtosis (mth)"], stats_reg["Kurtosis (mth)"]),
    ("CVaR95 (%)", stats_raw["CVaR95 (%)"], stats1["CVaR95 (%)"], stats2["CVaR95 (%)"], stats3["CVaR95 (%)"], stats_avg["CVaR95 (%)"], stats_reg["CVaR95 (%)"]),
    ("Hit Rate (%)", stats_raw["Hit Rate (%)"], stats1["Hit Rate (%)"], stats2["Hit Rate (%)"], stats3["Hit Rate (%)"], stats_avg["Hit Rate (%)"], stats_reg["Hit Rate (%)"]),
    ("Profit Factor", stats_raw["Profit Factor"], stats1["Profit Factor"], stats2["Profit Factor"], stats3["Profit Factor"], stats_avg["Profit Factor"], stats_reg["Profit Factor"]),
    ("Ann turnover", turnover_raw, turnover1, turnover2, turnover3, turnover_avg, turnover_reg),
    # Cost-adjusted metrics (holding period = days_in_year/turnover; 15 bps per trip; net sharpe = sharpe - cost/vol)
    ("Holding period (days)", cm_raw["Holding period (days)"], cm1["Holding period (days)"], cm2["Holding period (days)"], cm3["Holding period (days)"], cm_avg["Holding period (days)"], cm_reg["Holding period (days)"]),
    ("Ann cost (%)", cm_raw["Ann cost (%)"], cm1["Ann cost (%)"], cm2["Ann cost (%)"], cm3["Ann cost (%)"], cm_avg["Ann cost (%)"], cm_reg["Ann cost (%)"]),
    ("Cost/vol", cm_raw["Cost/vol"], cm1["Cost/vol"], cm2["Cost/vol"], cm3["Cost/vol"], cm_avg["Cost/vol"], cm_reg["Cost/vol"]),
    ("Net Sharpe", cm_raw["Net Sharpe"], cm1["Net Sharpe"], cm2["Net Sharpe"], cm3["Net Sharpe"], cm_avg["Net Sharpe"], cm_reg["Net Sharpe"]),
    ("Alpha vs raw (ann %)", np.nan, alpha1 * 100 if not np.isnan(alpha1) else np.nan, alpha2 * 100 if not np.isnan(alpha2) else np.nan, alpha3 * 100 if not np.isnan(alpha3) else np.nan, alpha_avg * 100 if not np.isnan(alpha_avg) else np.nan, alpha_reg * 100 if not np.isnan(alpha_reg) else np.nan),
    ("Beta vs raw", np.nan, beta1, beta2, beta3, beta_avg, beta_reg_out),
]

stats_df = pd.DataFrame(
    rows_table,
    columns=["Metric", "Raw", "Strategy 1", "Strategy 2", "Strategy 3", "Avg (1+2+3)", "Reg (β≥0)"],
).set_index("Metric")

with col_main:
    st.dataframe(stats_df.style.format("{:.2f}", na_rep="-"), use_container_width=True)
```

**Note**: The statistics table is placed inside `with col_main:` so it appears on the left with the chart; sliders stay on the right.

### 9.3 Captions

```python
with col_main:
    st.caption(f"Total days: {len(eod)} | {eod['date'].min()} → {eod['date'].max()}")
    st.caption(f"[Additional strategy-specific information]")
```

---

## Step 10: Register Page in app.py

### 10.1 Add to Pages List

Edit `viz/app.py`:

```python
pages = [
    # ... existing pages ...
    st.Page("pages/6_channel_breakout_backtest.py", title="Channel-Breakout Backtest", icon="📊"),
    st.Page("pages/7_[your_page].py", title="[Your Strategy] Backtest", icon="📈"),  # Add here
    # ... rest of pages ...
]
```

### 10.2 Add to Sidebar Navigation

In the sidebar section:

```python
with st.expander("🎯 Backtesting", expanded=False):
    # ... existing links ...
    st.page_link("pages/7_[your_page].py", label="[Your Strategy] Backtest", icon="📈")
    st.caption("[Brief description of the strategy]")
```

---

## Step 11: Testing Checklist

- [ ] Page loads without errors
- [ ] Symbol selector works and data loads correctly
- [ ] All sliders update strategy parameters correctly
- [ ] Display toggles show/hide series correctly
- [ ] Chart displays all enabled series
- [ ] Statistics table shows correct values (including new metrics: Sortino, CDD95, Kurtosis, CVaR95, Hit Rate, Profit Factor)
- [ ] Page appears in navigation sidebar
- [ ] No console errors or warnings
- [ ] Test with different symbols
- [ ] Test edge cases (insufficient data, extreme parameters)

---

## Statistics Metrics Reference

### Standard Metrics (Original SOP)

- **Ann return (%)**: Annualized mean return
- **Ann vol (%)**: Annualized volatility (standard deviation)
- **Sharpe**: Sharpe ratio (return / volatility)
- **Max DD (%)**: Maximum drawdown from peak
- **Avg DD (%)**: Average drawdown from peak
- **Calmar**: Return / Max DD ratio
- **Skewness**: Skewness of return distribution
- **ES95 (%)**: Expected Shortfall at 95% (mean of worst 5% returns)

### Additional Metrics (New)

- **Sortino**: Sortino ratio (return / downside deviation) - uses only negative returns for volatility
- **CDD95 (%)**: Conditional Drawdown at Risk at 95% - expected drawdown when drawdown exceeds 95th percentile
- **Kurtosis (mth)**: Monthly kurtosis - measures tail heaviness of monthly return distribution
- **CVaR95 (%)**: Conditional Value at Risk at 95% - same as ES95 (expected loss in worst 5% scenarios)
- **Hit Rate (%)**: Percentage of positive return periods
- **Profit Factor**: Ratio of gross profit to gross loss (sum of wins / abs(sum of losses))

### Comparison Metrics

- **Alpha vs raw (ann %)**: Annualized alpha relative to raw returns benchmark
- **Beta vs raw**: Beta relative to raw returns benchmark
- **Ann turnover**: Annual turnover (mean absolute position change × trading days)

---

## Common Patterns and Best Practices

### Pattern 1: Volatility Floor
Always clip volatility estimates to avoid division by zero:
```python
vol_estimator = ret.ewm(span=vol_lookback, adjust=False).std().clip(lower=VOL_FLOOR)
```

### Pattern 2: Position Shift
Always shift position by 1 period to avoid lookahead bias:
```python
pnl = position.shift(1) * ret
```

### Pattern 3: Fill NaN Values
Fill NaN values in PnL series:
```python
pnl = pnl.fillna(0)
```

### Pattern 4: Unique Keys
Use unique keys for all Streamlit widgets to avoid conflicts:
```python
# Good
st.slider("Fast lookback", key="fast1_tf")
st.slider("Fast lookback", key="fast2_tf")

# Bad (will conflict)
st.slider("Fast lookback", key="fast1")
st.slider("Fast lookback", key="fast1")  # Conflict!
```

### Pattern 5: Consistent Constants
Import shared constants from `viz.backtest_utils`:
```python
from viz.backtest_utils import TRADING_DAYS, TRADING_HOURS_PER_YEAR, VOL_FLOOR

TIMEFRAME_5M = "5m"  # Page-specific constant
# Use TRADING_DAYS, TRADING_HOURS_PER_YEAR, VOL_FLOOR from utils
```

### Pattern 7: Use Shared Utils Module
**Always use functions from `viz.backtest_utils` for common operations**:

1. **Import common functions**:
   ```python
   from viz.backtest_utils import (
       TRADING_DAYS,
       TRADING_HOURS_PER_YEAR,
       VOL_FLOOR,
       prepare_daily_stats_series,
       rescale_to_target_vol as rescale_to_target_vol_util,
       build_stats,
       alpha_beta,
       annual_turnover,
   )
   ```

2. **Use utils functions instead of defining locally**:
   - ✅ **DO**: `pnl1_for_stats, ... = prepare_daily_stats_series(...)`
   - ❌ **DON'T**: Define `resample_pnl_to_daily()` locally
   - ✅ **DO**: `ret_scaled, _ = rescale_to_target_vol_util(ret, None, target_vol, is_intraday=False)`
   - ❌ **DON'T**: Define `rescale_to_target_vol()` locally
   - ✅ **DO**: `stats1 = build_stats(pnl1_for_stats, is_raw=False)`
   - ❌ **DON'T**: Define `build_stats()`, `max_drawdown()`, `alpha_beta()`, etc. locally

3. **If a function doesn't exist in utils**:
   - **Is it page-specific?** (only used in one page) → Define locally
   - **Is it common/shared?** (used in multiple pages or likely to be reused) → **Add to `viz/backtest_utils.py` first**, then import and use it

4. **Never duplicate common functions** across multiple pages. This ensures:
   - Consistency across all backtest pages
   - Single source of truth for bug fixes
   - Easier maintenance and updates

### Pattern 6: Resample Intraday to Daily Before Statistics
For all intraday data (5m, hourly, etc.), always resample PnL to daily before calculating statistics using `prepare_daily_stats_series()`:
```python
# After calculating hourly PnL from 5m data
pnl1_for_stats, pnl2_for_stats, ..., ret_scaled_for_stats = prepare_daily_stats_series(
    pnl1, pnl2, pnl3, pnl_avg, pnl_reg, ret_scaled, dates
)
stats1 = build_stats(pnl1_for_stats, is_raw=False)  # Use daily series
```
This ensures:
- Meaningful annualized metrics (not inflated by high frequency)
- Consistent comparison across different timeframes
- Proper Sharpe/Sortino ratios (annualized from daily, not intraday)

---

## Example: Complete Minimal Backtest Page

See `viz/pages/3_vol_target_backtest.py` for a simpler example without regression aggregation.

---

## Troubleshooting

### Issue: Page not appearing in navigation
- **Solution**: Check that page is added to both `pages` list and sidebar in `app.py`

### Issue: Slider values conflicting between page visits
- **Solution**: Ensure all widget keys are unique (use suffix like `_tf`, `_cb`)

### Issue: Chart not updating when parameters change
- **Solution**: Streamlit automatically reruns on widget change; check for caching issues

### Issue: Statistics showing NaN
- **Solution**: Check for division by zero, insufficient data, or invalid calculations

### Issue: Performance is slow
- **Solution**: Consider caching data loading with `@st.cache_data` (be careful with mutable data)

---

## Related Documentation

- [Streamlit Documentation](https://docs.streamlit.io/)
- [Plotly Python Documentation](https://plotly.com/python/)
- Existing backtest pages:
  - `viz/pages/3_vol_target_backtest.py` - Simple vol-target example
  - `viz/pages/4_trend_following_backtest.py` - Trend-following with regression
  - `viz/pages/6_channel_breakout_backtest.py` - Channel breakout example

---

## Last Updated

2025-02-06

## Changelog

- **2025-02-06**: Documented layout: sliders on the right.
  - Step 2 renamed to "Set Up Layout and Controls"; added 2.1 "Layout: Left Sidebar + Main Area with Right Controls".
  - Sliders and display toggles go in `col_controls` (right column); charts and stats table go in `col_main` (left).
  - Left sidebar contains only symbol selector and database label.
  - Step 8 and Step 9.2/9.3 updated to show `with col_main:` for chart and dataframe/captions.
- **2025-02-06**: Added requirement to use shared `viz.backtest_utils` module:
  - Updated Step 1 to import common functions from `viz.backtest_utils`
  - Updated Step 6 to use `rescale_to_target_vol_util()` instead of local function
  - Updated Step 9.0 to use `prepare_daily_stats_series()` instead of local `resample_pnl_to_daily()`
  - Updated Step 9.1 to remove local function definitions and use utils functions
  - Added Pattern 7: Use Shared Utils Module with guidance on when to add functions to utils
  - Updated Pattern 5 and Pattern 6 to reference utils module
- **2025-02-06**: Added requirement to resample intraday data to daily before statistics:
  - Added `prepare_daily_stats_series()` function for intraday → daily aggregation
  - Updated `build_stats()` and helper functions to expect daily data
  - Added Step 9.0 with resampling instructions
  - Updated statistics calculation to use daily resampled series
- **2025-02-06**: Added additional statistics metrics:
  - Sortino ratio (downside deviation-based Sharpe)
  - CDD95 (Conditional Drawdown at Risk)
  - Kurtosis (monthly)
  - CVaR95 (Conditional Value at Risk)
  - Hit Rate (percentage of positive periods)
  - Profit Factor (gross profit / gross loss)
