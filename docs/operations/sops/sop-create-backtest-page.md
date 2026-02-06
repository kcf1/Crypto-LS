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

# Constants
TIMEFRAME_5M = "5m"
TRADING_DAYS = 252
VOL_FLOOR = 1e-8

# Page title and caption
st.title("[Strategy Name] backtest")
st.caption("[Brief description of signal logic and position calculation]")

# [Rest of the code follows...]
```

---

## Step 2: Set Up Sidebar Controls

### 2.1 Standard Sidebar Components

Every backtest page should include:

```python
storage = Storage()
symbols = settings.symbols

with st.sidebar:
    # Symbol selector
    symbol = st.selectbox(
        "Symbol",
        symbols,
        index=0,
        help="Symbol (from settings.symbols).",
    )
    
    # Database label (informational)
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")
    
    st.divider()
    
    # Strategy parameter sections (see 2.2)
    # Display toggles (see 2.3)
```

### 2.2 Strategy Parameter Sections

**Pattern**: Create 3 strategy variants with independent parameters

```python
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
# Shared parameters (e.g., target vol)
target_vol = st.slider("Target vol (ann) — all series", 0.05, 0.50, 0.15, 0.01, key="target_vol")
```

**Key Naming Convention**: Use unique keys for each slider to avoid conflicts (e.g., `fast1`, `fast2`, `fast3` or `channel1_cb`, `channel2_cb`).

### 2.3 Display Toggles

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

```python
from sklearn.linear_model import RidgeCV

vol_ret = ret.ewm(span=30, adjust=False).std().clip(lower=VOL_FLOOR)
X = np.column_stack([pos1.values, pos2.values, pos3.values])
default_beta = np.array([1.0 / 3, 1.0 / 3, 1.0 / 3])
betas = []

for horizon in (1, 5, 10, 30):
    fwd_ret = ret.rolling(horizon).sum().shift(-horizon)
    vol_h = vol_ret * np.sqrt(horizon)
    y_h = (fwd_ret / vol_h).replace([np.inf, -np.inf], np.nan).values
    valid = ~(np.isnan(X).any(axis=1) | np.isnan(y_h))
    X_v, y_v = X[valid], y_h[valid]
    
    if X_v.shape[0] > 10:
        split_idx = X_v.shape[0] // 2
        X_train, y_train = X_v[:split_idx], y_v[:split_idx]
        ridge = RidgeCV(cv=5, alphas=np.logspace(-6, 6, 13))
        ridge.fit(X_train, y_train)
        b = ridge.coef_
        betas.append(b)
    else:
        betas.append(default_beta)

beta_1d, beta_5d, beta_10d, beta_30d = betas[0], betas[1], betas[2], betas[3]
beta_reg = (np.array(beta_1d) + np.array(beta_5d) + np.array(beta_10d) + np.array(beta_30d)) / 4
pos_reg = beta_reg[0] * pos1 + beta_reg[1] * pos2 + beta_reg[2] * pos3
pnl_reg = pos_reg.shift(1) * ret
pnl_reg = pnl_reg.fillna(0)
```

---

## Step 6: Rescale to Target Volatility

### 6.1 Rescaling Function

```python
target_vol_daily = target_vol / np.sqrt(TRADING_DAYS)

def rescale_to_target_vol(pnl_series: pd.Series, pos_series: pd.Series = None) -> tuple:
    sd = pnl_series.std()
    scale = target_vol_daily / sd if sd > 1e-12 else 1.0
    pnl_scaled = pnl_series * scale
    pos_scaled = pos_series * scale if pos_series is not None else None
    return pnl_scaled, pos_scaled

ret_scaled, _ = rescale_to_target_vol(ret, None)
pnl1, pos1 = rescale_to_target_vol(pnl1, pos1)
pnl2, pos2 = rescale_to_target_vol(pnl2, pos2)
pnl3, pos3 = rescale_to_target_vol(pnl3, pos3)
pnl_avg, pos_avg = rescale_to_target_vol(pnl_avg, pos_avg)
pnl_reg, pos_reg = rescale_to_target_vol(pnl_reg, pos_reg)
```

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
st.plotly_chart(fig, use_container_width=True)
```

---

## Step 9: Statistics Table

### 9.1 Helper Functions

```python
def level_from_log(cumlog: pd.Series) -> pd.Series:
    return np.exp(cumlog) - 1

def max_drawdown(cumlog: pd.Series) -> float:
    level = level_from_log(cumlog)
    peak = level.cummax()
    dd = peak - level
    return float(dd.max()) * 100

def avg_drawdown(cumlog: pd.Series) -> float:
    level = level_from_log(cumlog)
    peak = level.cummax()
    dd = peak - level
    return float(dd.mean()) * 100

def alpha_beta(pnl: pd.Series, bench: pd.Series) -> tuple[float, float]:
    m = pnl.notna() & bench.notna()
    p = pnl[m].values
    b = bench[m].values
    if len(p) < 2 or b.var() == 0:
        return np.nan, np.nan
    beta = np.cov(p, b)[0, 1] / b.var()
    alpha = p.mean() - beta * b.mean()
    return alpha * TRADING_DAYS, beta

def es95(series: pd.Series) -> float:
    """Expected Shortfall (ES) at 95% - same as CVaR95."""
    q = series.quantile(0.05)
    return float(series[series <= q].mean()) * 100

def cvar95(series: pd.Series) -> float:
    """
    Conditional Value at Risk (CVaR) at 95% confidence level.
    Also known as Expected Shortfall (ES). Returns the expected loss given that loss exceeds the 95% VaR threshold.
    Note: This is equivalent to es95() above.
    """
    q = series.quantile(0.05)
    return float(series[series <= q].mean()) * 100

def cdd95(cumlog: pd.Series) -> float:
    """
    Conditional Drawdown at Risk (CDD) at 95% confidence level.
    Expected drawdown given that drawdown exceeds the 95% threshold.
    """
    level = np.exp(cumlog) - 1
    peak = level.cummax()
    drawdown = peak - level
    q = drawdown.quantile(0.95)
    return float(drawdown[drawdown >= q].mean()) * 100

def kurtosis_monthly(series: pd.Series, trading_days: int = 252) -> float:
    """
    Monthly kurtosis.
    Aggregates daily returns to monthly, then calculates kurtosis.
    """
    # Resample to monthly (assuming daily data)
    # If data is already monthly, use directly
    if len(series) > 30:  # Likely daily data
        # Group by month if datetime index, otherwise group by ~21 day chunks
        if isinstance(series.index, pd.DatetimeIndex):
            monthly_ret = series.resample('M').sum()
        else:
            # For integer index, group by ~21 day periods (approximate month)
            monthly_ret = series.groupby(series.index // 21).sum()
    else:
        monthly_ret = series
    
    return float(monthly_ret.kurtosis())

def sortino_ratio(pnl: pd.Series, risk_free_rate: float = 0.0, trading_days: int = 252) -> float:
    """
    Sortino ratio: excess return / downside deviation.
    Uses only negative returns for volatility calculation.
    """
    excess_return = pnl.mean() * trading_days - risk_free_rate
    downside_returns = pnl[pnl < 0]
    if len(downside_returns) == 0:
        return np.inf if excess_return > 0 else np.nan
    downside_std = downside_returns.std() * np.sqrt(trading_days)
    return excess_return / downside_std if downside_std > 1e-12 else np.nan

def hit_rate(pnl: pd.Series) -> float:
    """
    Hit rate: percentage of positive returns.
    """
    return float((pnl > 0).sum() / len(pnl)) * 100 if len(pnl) > 0 else np.nan

def profit_factor(pnl: pd.Series) -> float:
    """
    Profit factor: gross profit / gross loss.
    Ratio of sum of positive returns to absolute sum of negative returns.
    """
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    return float(gross_profit / gross_loss) if gross_loss > 1e-12 else np.inf

def annual_turnover(position: pd.Series) -> float:
    return float(position.diff().abs().mean()) * TRADING_DAYS

def build_stats(ret_series: pd.Series, is_raw: bool, trading_days: int = 252) -> dict:
    """
    Enhanced build_stats with all metrics including CVaR95, CDD95, Sortino, Kurtosis, Hit Rate, and Profit Factor.
    """
    if is_raw:
        r = ret_series
        ann_ret = r.mean() * trading_days * 100
        ann_vol = r.std() * np.sqrt(trading_days) * 100
        cumlog = r.cumsum()
    else:
        r = ret_series
        ann_ret = r.mean() * trading_days * 100
        ann_vol = r.std() * np.sqrt(trading_days) * 100
        cumlog = np.log(1 + r).cumsum()
    
    sharpe = ann_ret / ann_vol if ann_vol else np.nan
    sortino = sortino_ratio(r, trading_days=trading_days)
    max_dd = max_drawdown(cumlog)
    cdd95_val = cdd95(cumlog)
    calmar = ann_ret / max_dd if max_dd else np.nan
    avg_dd = avg_drawdown(cumlog)
    skew = float(r.skew()) if len(r) else np.nan
    kurt_mth = kurtosis_monthly(r, trading_days=trading_days)
    cvar95_val = cvar95(r)
    hit_rate_val = hit_rate(r)
    profit_factor_val = profit_factor(r)
    
    return {
        "Ann return (%)": ann_ret,
        "Ann vol (%)": ann_vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "Max DD (%)": max_dd,
        "CDD95 (%)": cdd95_val,
        "Avg DD (%)": avg_dd,
        "Calmar": calmar,
        "Skewness": skew,
        "Kurtosis (mth)": kurt_mth,
        "CVaR95 (%)": cvar95_val,
        "Hit Rate (%)": hit_rate_val,
        "Profit Factor": profit_factor_val,
    }
```

### 9.2 Build Statistics Table

```python
stats_raw = build_stats(ret_scaled, is_raw=True)
stats1 = build_stats(pnl1, is_raw=False)
stats2 = build_stats(pnl2, is_raw=False)
stats3 = build_stats(pnl3, is_raw=False)
stats_avg = build_stats(pnl_avg, is_raw=False)
stats_reg = build_stats(pnl_reg, is_raw=False)

alpha1, beta1 = alpha_beta(pnl1, ret_scaled)
alpha2, beta2 = alpha_beta(pnl2, ret_scaled)
alpha3, beta3 = alpha_beta(pnl3, ret_scaled)
alpha_avg, beta_avg = alpha_beta(pnl_avg, ret_scaled)
alpha_reg, beta_reg_out = alpha_beta(pnl_reg, ret_scaled)

turnover_raw = 0.0
turnover1 = annual_turnover(pos1)
turnover2 = annual_turnover(pos2)
turnover3 = annual_turnover(pos3)
turnover_avg = annual_turnover(pos_avg)
turnover_reg = annual_turnover(pos_reg)

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
    ("Alpha vs raw (ann %)", np.nan, alpha1 * 100 if not np.isnan(alpha1) else np.nan, alpha2 * 100 if not np.isnan(alpha2) else np.nan, alpha3 * 100 if not np.isnan(alpha3) else np.nan, alpha_avg * 100 if not np.isnan(alpha_avg) else np.nan, alpha_reg * 100 if not np.isnan(alpha_reg) else np.nan),
    ("Beta vs raw", np.nan, beta1, beta2, beta3, beta_avg, beta_reg_out),
]

stats_df = pd.DataFrame(
    rows_table,
    columns=["Metric", "Raw", "Strategy 1", "Strategy 2", "Strategy 3", "Avg (1+2+3)", "Reg (β≥0)"],
).set_index("Metric")

st.dataframe(stats_df.style.format("{:.2f}", na_rep="-"), use_container_width=True)
```

### 9.3 Captions

```python
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
Use shared constants at the top:
```python
TIMEFRAME_5M = "5m"
TRADING_DAYS = 252
VOL_FLOOR = 1e-8
```

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

- **2025-02-06**: Added additional statistics metrics:
  - Sortino ratio (downside deviation-based Sharpe)
  - CDD95 (Conditional Drawdown at Risk)
  - Kurtosis (monthly)
  - CVaR95 (Conditional Value at Risk)
  - Hit Rate (percentage of positive periods)
  - Profit Factor (gross profit / gross loss)
