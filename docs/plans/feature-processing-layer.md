# Feature Processing Layer Architecture

This document outlines the planned feature processing layer to transform raw market data into ready-to-use features for strategy development.

## Table of Contents

1. [Motivation](#motivation)
2. [Current Architecture](#current-architecture)
3. [Proposed Architecture](#proposed-architecture)
4. [Implementation Plan](#implementation-plan)
5. [Feature Definitions](#feature-definitions)
6. [Storage Strategy](#storage-strategy)

## Motivation

### Current Pain Points

1. **Repeated Computation**: Each Streamlit page recomputes the same features (EMAs, returns, volatility) every time
2. **Inconsistency Risk**: Different pages might compute features slightly differently
3. **Performance**: Computing features on raw data every query is inefficient for large datasets
4. **Scalability**: As strategies grow, duplication increases

### Benefits of Feature Layer

1. **Consistency**: All strategies use identical feature definitions
2. **Performance**: Pre-computed features load faster
3. **Extensibility**: Easy to add new features once
4. **Testing**: Test feature logic independently from strategies
5. **ML-Ready**: Clean feature layer enables future ML models

## Current Architecture

```
Raw Data Layer (data/)
    ↓
Visualization/Strategy Layer (viz/)
```

Current flow:
- `data/collector.py` → Fetches raw data from Binance
- `data/storage.py` → Stores raw OHLCV, funding rates, open interest, etc.
- `viz/pages/*.py` → Reads raw data, computes features on-the-fly, runs backtests

## Proposed Architecture

```
Raw Data Layer (data/)
    ↓
Feature Layer (NEW: features/)
    ↓
Strategy/Visualization Layer (viz/)
```

### Module Structure

```
features/
├── __init__.py           # Feature registry and utilities
├── technical.py          # Price-based features
│   ├── compute_returns()
│   ├── compute_ema()
│   ├── compute_volatility()
│   ├── compute_atr()
│   └── compute_rsi()
├── fundamental.py        # Futures/derivatives features
│   ├── compute_funding_zscore()
│   ├── compute_basis_zscore()
│   ├── compute_oi_momentum()
│   └── compute_funding_cumulative()
├── sentiment.py          # Positioning features
│   ├── compute_ls_ratio_zscore()
│   ├── compute_ls_momentum()
│   └── compute_top_trader_positioning()
├── cross_sectional.py    # Cross-asset features
│   ├── cross_sectional_zscore()
│   ├── cross_sectional_rank()
│   └── sector_relative()
└── storage.py            # Feature persistence (optional)
    ├── write_features()
    ├── read_features()
    └── get_or_compute()
```

## Implementation Plan

### Phase 1: Standardized Computation Functions

Create `features/` module with pure computation functions.

```python
# features/technical.py
"""Technical analysis features computed from OHLCV data."""

import numpy as np
import pandas as pd

def compute_returns(
    close: pd.Series,
    periods: int = 1,
    log: bool = True,
) -> pd.Series:
    """
    Compute returns from close prices.
    
    Args:
        close: Close price series
        periods: Number of periods for return calculation
        log: If True, compute log returns; else simple returns
        
    Returns:
        Return series
    """
    if log:
        return np.log(close / close.shift(periods))
    else:
        return close.pct_change(periods)


def compute_ema(
    series: pd.Series,
    span: int,
    adjust: bool = False,
) -> pd.Series:
    """
    Compute exponential moving average.
    
    Args:
        series: Input series
        span: EMA span (decay in terms of span)
        adjust: Whether to adjust for imbalanced weights at start
        
    Returns:
        EMA series
    """
    return series.ewm(span=span, adjust=adjust).mean()


def compute_volatility(
    returns: pd.Series,
    window: int = 20,
    annualize: bool = True,
    trading_periods: int = 252,
) -> pd.Series:
    """
    Compute rolling volatility from returns.
    
    Args:
        returns: Return series (daily)
        window: Rolling window size
        annualize: Whether to annualize
        trading_periods: Number of trading periods per year
        
    Returns:
        Volatility series
    """
    vol = returns.ewm(span=window, adjust=False).std()
    if annualize:
        vol = vol * np.sqrt(trading_periods)
    return vol


def compute_momentum(
    close: pd.Series,
    lookback: int = 20,
) -> pd.Series:
    """
    Compute price momentum (cumulative return over lookback).
    
    Args:
        close: Close price series
        lookback: Lookback period in days
        
    Returns:
        Momentum series
    """
    return np.log(close / close.shift(lookback))


def compute_mean_reversion(
    close: pd.Series,
    lookback: int = 5,
) -> pd.Series:
    """
    Compute short-term mean reversion signal (negative momentum).
    
    Args:
        close: Close price series
        lookback: Short lookback for reversal
        
    Returns:
        Reversal signal (negative = recent winners)
    """
    return -np.log(close / close.shift(lookback))
```

```python
# features/fundamental.py
"""Fundamental features from futures/derivatives data."""

import numpy as np
import pandas as pd


def compute_funding_zscore(
    funding_rate: pd.Series,
    lookback: int = 30,
) -> pd.Series:
    """
    Compute z-score of funding rate relative to recent history.
    
    Args:
        funding_rate: Funding rate series
        lookback: Lookback for mean/std calculation
        
    Returns:
        Z-scored funding rate
    """
    mean = funding_rate.rolling(lookback).mean()
    std = funding_rate.rolling(lookback).std()
    return (funding_rate - mean) / std.clip(lower=1e-8)


def compute_basis_zscore(
    basis: pd.Series,
    lookback: int = 30,
) -> pd.Series:
    """
    Compute z-score of basis relative to recent history.
    
    Args:
        basis: Basis (futures - spot) series
        lookback: Lookback for mean/std calculation
        
    Returns:
        Z-scored basis
    """
    mean = basis.rolling(lookback).mean()
    std = basis.rolling(lookback).std()
    return (basis - mean) / std.clip(lower=1e-8)


def compute_oi_momentum(
    open_interest: pd.Series,
    lookback: int = 5,
) -> pd.Series:
    """
    Compute open interest momentum (% change).
    
    Args:
        open_interest: Open interest series
        lookback: Lookback period
        
    Returns:
        OI momentum (% change)
    """
    return open_interest.pct_change(lookback)


def compute_funding_cumulative(
    funding_rate: pd.Series,
    lookback: int = 7,
) -> pd.Series:
    """
    Compute cumulative funding over lookback period.
    
    Args:
        funding_rate: Funding rate series (per 8h)
        lookback: Number of funding periods to sum
        
    Returns:
        Cumulative funding
    """
    return funding_rate.rolling(lookback).sum()
```

```python
# features/cross_sectional.py
"""Cross-sectional features across multiple assets."""

import pandas as pd
import numpy as np


def cross_sectional_zscore(
    df: pd.DataFrame,
    columns: list = None,
) -> pd.DataFrame:
    """
    Z-score features cross-sectionally (across assets at each time).
    
    Args:
        df: DataFrame with index=symbol, columns=features
        columns: Specific columns to z-score (None = all)
        
    Returns:
        Z-scored DataFrame
    """
    if columns is None:
        columns = df.columns
    
    result = df.copy()
    for col in columns:
        mean = df[col].mean()
        std = df[col].std()
        result[col] = (df[col] - mean) / std if std > 1e-8 else 0
    return result


def cross_sectional_rank(
    series: pd.Series,
    ascending: bool = False,
    pct: bool = False,
) -> pd.Series:
    """
    Rank assets cross-sectionally.
    
    Args:
        series: Series with index=symbol
        ascending: If False, highest value gets rank 1
        pct: If True, return percentile rank [0, 1]
        
    Returns:
        Rank series
    """
    ranks = series.rank(ascending=ascending)
    if pct:
        ranks = ranks / len(series)
    return ranks
```

### Phase 2: Feature Caching/Persistence

Add optional persistence for expensive computations.

```python
# features/storage.py
"""Feature persistence and caching."""

from typing import Optional, List
import pandas as pd
from data.storage import Storage


class FeatureStore:
    """Cache and persist computed features."""
    
    def __init__(self, storage: Storage):
        self.storage = storage
        self._cache = {}
    
    def get_or_compute(
        self,
        symbol: str,
        feature_name: str,
        compute_fn: callable,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        use_cache: bool = True,
    ) -> pd.Series:
        """
        Get feature from cache/storage or compute if not available.
        
        Args:
            symbol: Asset symbol
            feature_name: Name of feature
            compute_fn: Function to compute feature if not cached
            start_time: Start timestamp
            end_time: End timestamp
            use_cache: Whether to use in-memory cache
            
        Returns:
            Feature series
        """
        cache_key = (symbol, feature_name, start_time, end_time)
        
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        # Compute feature
        result = compute_fn()
        
        if use_cache:
            self._cache[cache_key] = result
        
        return result
    
    def clear_cache(self):
        """Clear in-memory cache."""
        self._cache = {}
```

### Phase 3: Feature Tables (Optional)

For frequently-used features, create dedicated database tables.

```sql
-- Alembic migration for feature tables

CREATE TABLE ohlcv_features (
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    timestamp BIGINT NOT NULL,
    returns_1d FLOAT,
    returns_5d FLOAT,
    returns_20d FLOAT,
    volatility_20d FLOAT,
    volatility_60d FLOAT,
    ema_20 FLOAT,
    ema_50 FLOAT,
    momentum_20d FLOAT,
    momentum_60d FLOAT,
    PRIMARY KEY (symbol, timeframe, timestamp)
);

CREATE INDEX ix_ohlcv_features_symbol_timeframe 
ON ohlcv_features (symbol, timeframe);
```

## Feature Definitions

### Technical Features

| Feature | Formula | Lookback | Description |
|---------|---------|----------|-------------|
| `returns_1d` | `log(close_t / close_{t-1})` | 1 | Daily log return |
| `returns_5d` | `log(close_t / close_{t-5})` | 5 | Weekly log return |
| `momentum_20d` | `log(close_t / close_{t-20})` | 20 | Monthly momentum |
| `momentum_60d` | `log(close_t / close_{t-60})` | 60 | Quarterly momentum |
| `reversal_5d` | `-log(close_t / close_{t-5})` | 5 | Short-term reversal |
| `volatility_20d` | `ewm_std(returns, 20) * sqrt(252)` | 20 | Rolling annualized vol |
| `ema_20` | `ewm_mean(close, 20)` | 20 | 20-day EMA |

### Fundamental Features

| Feature | Formula | Lookback | Description |
|---------|---------|----------|-------------|
| `funding_zscore` | `(fr - mean(fr, 30)) / std(fr, 30)` | 30 | Funding rate z-score |
| `funding_cumulative_7d` | `sum(fr, 7 periods)` | 7 | 7-period cumulative funding |
| `basis_zscore` | `(basis - mean, 30) / std(basis, 30)` | 30 | Basis z-score |
| `oi_momentum_5d` | `pct_change(oi, 5)` | 5 | OI momentum |

### Sentiment Features

| Feature | Formula | Lookback | Description |
|---------|---------|----------|-------------|
| `ls_ratio_zscore` | `(lsr - mean(lsr, 30)) / std(lsr, 30)` | 30 | Long/short ratio z-score |
| `ls_momentum` | `pct_change(lsr, 5)` | 5 | L/S ratio momentum |

## Storage Strategy

### Recommended Approach: Hybrid

1. **Compute on-the-fly** for development and research
2. **Cache in memory** during backtests (session-scoped)
3. **Persist to tables** only for production features used in live trading

### When to Persist

- Feature computation takes >1 second
- Feature is used across multiple strategies
- Feature requires expensive joins or aggregations
- Feature is needed for real-time signals

### When NOT to Persist

- Feature is simple (single-column transformation)
- Feature parameters are frequently tuned
- Feature is experimental

## Migration Path

1. Create `features/` module with computation functions
2. Refactor existing viz pages to use feature functions
3. Add caching layer for backtest performance
4. (Optional) Add persistence for production features
5. Update ARCHITECTURE.md to document new layer

## Related Documents

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System overview
- [Multi-Factor Long/Short Strategy](./multi-factor-long-short-strategy.md) - Strategy using features
