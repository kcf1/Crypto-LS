# Multi-Factor Long/Short Strategy Architecture

This document outlines the planned architecture for a multi-factor long/short strategy with conviction-based position sizing.

## Table of Contents

1. [Strategy Overview](#strategy-overview)
2. [Architecture Approaches](#architecture-approaches)
3. [Recommended Architecture](#recommended-architecture)
4. [Implementation Details](#implementation-details)
5. [Factor Definitions](#factor-definitions)
6. [Risk Management](#risk-management)
7. [Backtesting Framework](#backtesting-framework)

## Strategy Overview

### Goals

- Trade a concentrated portfolio (5-15 assets)
- Use cross-sectional signals to determine long/short direction
- Apply conviction-based sizing (market timing element)
- Implement disciplined entry/exit with stops

### Key Characteristics

| Dimension | Description |
|-----------|-------------|
| Universe | 5-15 liquid crypto assets |
| Positions | Variable (0 to max), not always invested |
| Signal use | Cross-sectional ranks + absolute conviction |
| Exposure | Time-varying based on conviction |
| Exit logic | Signal decay + stops |
| Rebalance | Daily or intraday |

## Architecture Approaches

### Approach 1: Rank-Based Risk Parity

```
raw data → feature → cross-sectional model → rank → risk parity L/S on top/bottom → rebalance
```

**Pros:**
- Simple, robust, well-understood
- Risk parity handles vol differences
- Ranks are stable

**Cons:**
- Loses information (only ordinal)
- Fixed number of positions
- Doesn't exploit conviction levels

**Best for:** Baseline strategy, first implementation

### Approach 2: Portfolio Optimization

```
raw data → feature → cross-sectional model → optimizer → weights → rebalance
```

**Pros:**
- Uses full signal magnitude
- Incorporates covariance
- Theoretically optimal

**Cons:**
- Estimation error in covariance
- Can be unstable
- Risk of overfitting

**Best for:** Second iteration after rank-based proves concept

### Approach 3: Threshold + Trailing Stop (Single Asset)

```
raw data → feature → model → threshold entry → threshold/trailing exit
```

**Pros:**
- Selective (high-conviction only)
- Trailing stops protect profits
- Lower turnover potential

**Cons:**
- Many parameters to tune
- Harder to maintain neutrality
- Signal timing critical

**Best for:** Single-asset or concentrated portfolios, not cross-sectional L/S

### Recommended: Conviction-Scaled Cross-Sectional L/S (Hybrid)

Combines cross-sectional direction with conviction-based sizing:

```
Cross-Sectional Analysis  →  DIRECTION (who to L, who to S)
Absolute Signal Strength  →  CONVICTION (how much to trade)
Risk Management           →  SIZING (position limits, stops)
```

## Recommended Architecture

### Layer Structure

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     LAYER 1: CROSS-SECTIONAL SIGNAL                     │
│                                                                         │
│  For each asset i at time t:                                           │
│    1. Compute raw features (momentum, funding, basis, etc.)            │
│    2. Z-score cross-sectionally → z_i(t)                               │
│    3. Combine factors → composite_alpha_i(t)                           │
│    4. Rank assets → rank_i(t)                                          │
│                                                                         │
│  Output: alpha_i(t) and rank_i(t) for each asset                       │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     LAYER 2: CONVICTION SCORING                         │
│                                                                         │
│  conviction_i(t) = f(                                                  │
│      |alpha_i(t)|,           # absolute signal strength                │
│      rank_spread(t),         # dispersion in cross-section             │
│      signal_persistence(t),  # signal stability over time              │
│      regime_indicator(t),    # market conditions                       │
│  )                                                                      │
│                                                                         │
│  Output: conviction_i(t) ∈ [0, 1] for each asset                       │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     LAYER 3: POSITION MANAGEMENT                        │
│                                                                         │
│  Entry Logic:                                                          │
│    IF rank_i ∈ top_k AND conviction_i > entry_threshold:               │
│        target_weight_i = +base_weight * conviction_scale               │
│    IF rank_i ∈ bottom_k AND conviction_i > entry_threshold:            │
│        target_weight_i = -base_weight * conviction_scale               │
│                                                                         │
│  Exit Logic:                                                           │
│    - Signal decay: conviction_i < exit_threshold                       │
│    - Rank flip: asset no longer in top/bottom k                        │
│    - Stop loss: drawdown > max_loss per position                       │
│    - Trailing stop: retrace from peak                                  │
│                                                                         │
│  Output: target_weight_i(t) with explicit entry/exit triggers          │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     LAYER 4: PORTFOLIO CONSTRAINTS                      │
│                                                                         │
│  - Max gross exposure (e.g., 1.5x)                                     │
│  - Max position size per asset (e.g., 20%)                             │
│  - Dollar neutrality (optional): sum(long) ≈ sum(short)                │
│  - Vol targeting: scale portfolio to target vol                        │
│                                                                         │
│  Output: final_weight_i(t) respecting all constraints                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Module Structure

```
alpha/
├── __init__.py
├── factors.py           # Individual factor definitions
├── combiner.py          # Factor weighting (equal, IC-weighted, ML)
└── signal.py            # Combined alpha signal per asset

portfolio/
├── __init__.py
├── conviction.py        # Conviction scoring
├── position_manager.py  # Entry/exit logic with state
├── risk_model.py        # Vol estimation, correlation
├── optimizer.py         # Weight optimization (optional)
└── constructor.py       # Final weights with constraints

backtest/
├── __init__.py
├── engine.py            # Core backtest loop
├── metrics.py           # Performance statistics
└── analysis.py          # Factor analysis, attribution
```

## Implementation Details

### Core Classes

```python
# alpha/signal.py
class CrossSectionalSignal:
    """Compute cross-sectional alpha signals."""
    
    def __init__(
        self,
        symbols: List[str],
        factor_weights: Dict[str, float] = None,
    ):
        self.symbols = symbols
        self.factor_weights = factor_weights or {
            'momentum_20d': 0.25,
            'momentum_60d': 0.25,
            'funding_zscore': 0.20,
            'basis_zscore': 0.15,
            'oi_momentum': 0.15,
        }
    
    def compute(self, date: pd.Timestamp) -> pd.DataFrame:
        """
        Compute signals for all assets at given date.
        
        Returns DataFrame with columns:
        - alpha: composite signal (higher = more bullish)
        - rank: cross-sectional rank (1 = highest alpha)
        - conviction: signal strength [0, 1]
        """
        # 1. Compute raw features
        features = self._compute_features(date)
        
        # 2. Z-score cross-sectionally
        features_z = self._cross_sectional_zscore(features)
        
        # 3. Combine factors
        alpha = self._combine_factors(features_z)
        
        # 4. Rank
        rank = alpha.rank(ascending=False)
        
        # 5. Conviction
        conviction = self._compute_conviction(alpha)
        
        return pd.DataFrame({
            'alpha': alpha,
            'rank': rank,
            'conviction': conviction,
        })
```

```python
# portfolio/conviction.py
class ConvictionScorer:
    """Compute conviction scores from alpha signals."""
    
    def __init__(
        self,
        method: str = 'simple',  # 'simple', 'dispersion', 'persistence', 'agreement'
    ):
        self.method = method
    
    def score(self, alpha: pd.Series, history: pd.DataFrame = None) -> pd.Series:
        """
        Compute conviction scores.
        
        Args:
            alpha: Current alpha signals (index=symbol)
            history: Historical alpha DataFrame for persistence calc
            
        Returns:
            Conviction scores [0, 1]
        """
        if self.method == 'simple':
            # Simple: normalized absolute z-score
            return self._simple_conviction(alpha)
        elif self.method == 'dispersion':
            # With dispersion: signal quality
            return self._dispersion_conviction(alpha)
        elif self.method == 'persistence':
            # With persistence: signal stability
            return self._persistence_conviction(alpha, history)
        elif self.method == 'agreement':
            # Multi-factor agreement
            return self._agreement_conviction(alpha)
    
    def _simple_conviction(self, alpha: pd.Series) -> pd.Series:
        """conviction = abs(alpha) / max(abs(alpha)), capped at 1"""
        alpha_abs = alpha.abs()
        return (alpha_abs / alpha_abs.max()).clip(0, 1)
    
    def _dispersion_conviction(self, alpha: pd.Series) -> pd.Series:
        """conviction = abs(alpha) * dispersion_quality"""
        alpha_abs = alpha.abs()
        dispersion = alpha.std()
        quality = min(1.0, dispersion / 0.5)  # full conviction if spread > 0.5 std
        return (alpha_abs / alpha_abs.max() * quality).clip(0, 1)
```

```python
# portfolio/position_manager.py
class PositionManager:
    """Manage positions with entry/exit logic."""
    
    def __init__(
        self,
        n_long: int = 3,
        n_short: int = 3,
        entry_threshold: float = 0.5,
        exit_threshold: float = 0.3,
        stop_loss_pct: float = 0.05,
        trailing_stop_pct: float = 0.03,
        max_position_pct: float = 0.20,
    ):
        self.n_long = n_long
        self.n_short = n_short
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.stop_loss_pct = stop_loss_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.max_position_pct = max_position_pct
        
        # State
        self.positions = {}  # symbol -> PositionState
    
    def generate_targets(
        self,
        signals: pd.DataFrame,
        prices: pd.Series,
    ) -> pd.Series:
        """
        Generate target weights based on signals and current positions.
        
        Args:
            signals: DataFrame with alpha, rank, conviction
            prices: Current prices per symbol
            
        Returns:
            Target weights per symbol
        """
        targets = pd.Series(0.0, index=signals.index)
        
        # Identify candidates
        long_candidates = signals.nsmallest(self.n_long, 'rank').index
        short_candidates = signals.nlargest(self.n_short, 'rank').index
        
        for sym in signals.index:
            sig = signals.loc[sym]
            current_pos = self.positions.get(sym)
            
            # Check exits first
            if current_pos is not None:
                should_exit = self._check_exit(sym, sig, prices[sym], current_pos)
                if should_exit:
                    targets[sym] = 0.0
                    del self.positions[sym]
                else:
                    targets[sym] = current_pos['weight']
                continue
            
            # Check entries
            if sig['conviction'] >= self.entry_threshold:
                if sym in long_candidates:
                    weight = self.max_position_pct * sig['conviction']
                    targets[sym] = weight
                    self._open_position(sym, weight, prices[sym])
                elif sym in short_candidates:
                    weight = -self.max_position_pct * sig['conviction']
                    targets[sym] = weight
                    self._open_position(sym, weight, prices[sym])
        
        return targets
    
    def _check_exit(self, sym, sig, price, pos) -> bool:
        """Check if position should be exited."""
        # 1. Conviction decay
        if sig['conviction'] < self.exit_threshold:
            return True
        
        # 2. Stop loss
        pnl_pct = self._calc_pnl_pct(pos, price)
        if pnl_pct < -self.stop_loss_pct:
            return True
        
        # 3. Trailing stop
        drawdown = self._calc_drawdown(pos, price)
        if drawdown > self.trailing_stop_pct:
            return True
        
        return False
```

### State Machine

```
                    ┌──────────────┐
         ┌─────────►│     FLAT     │◄─────────┐
         │          └──────┬───────┘          │
         │                 │                  │
    Exit Signal      Entry Signal        Exit Signal
    (any of 4)       (rank + conviction)  (any of 4)
         │                 │                  │
         │          ┌──────▼───────┐          │
         │          │  CANDIDATE   │          │
         │          │  (waiting)   │          │
         │          └──────┬───────┘          │
         │                 │                  │
         │           conviction >             │
         │           entry_threshold          │
         │                 │                  │
    ┌────┴────┐      ┌─────▼─────┐      ┌────┴────┐
    │  LONG   │      │   ENTRY   │      │  SHORT  │
    │ POSITION│◄─────┤  EXECUTE  ├─────►│POSITION │
    └─────────┘      └───────────┘      └─────────┘
```

## Factor Definitions

### Factors from Available Data

| Factor | Data Source | Formula | Hypothesis |
|--------|-------------|---------|------------|
| `momentum_20d` | OHLCV | `log(close_t / close_{t-20})` | Winners continue |
| `momentum_60d` | OHLCV | `log(close_t / close_{t-60})` | Longer-term trend |
| `reversal_5d` | OHLCV | `-log(close_t / close_{t-5})` | Short-term mean reversion |
| `funding_zscore` | funding_rate | `(fr - mean) / std` | High funding = crowded, expect reversal |
| `basis_zscore` | basis | `(basis - mean) / std` | Extreme basis = arb pressure |
| `oi_momentum` | open_interest | `pct_change(oi, 5)` | Rising OI + price = confirmation |
| `ls_ratio_zscore` | long_short_account | `(lsr - mean) / std` | Positioning extremes revert |
| `vol_adjusted_ret` | OHLCV | `returns / volatility` | Risk-adjusted performance |

### Factor Combination

```python
# Default equal-weight combination
factor_weights = {
    'momentum_20d': 0.20,
    'momentum_60d': 0.15,
    'reversal_5d': 0.10,
    'funding_zscore': -0.20,  # negative: high funding is bearish
    'basis_zscore': -0.15,    # negative: high basis is bearish
    'oi_momentum': 0.10,
    'ls_ratio_zscore': -0.10, # negative: crowded long is bearish
}

# Composite alpha
alpha = sum(weight * feature_zscore for feature, weight in factor_weights.items())
```

## Risk Management

### Position-Level Controls

| Control | Parameter | Default | Description |
|---------|-----------|---------|-------------|
| Max position | `max_position_pct` | 20% | Max weight per asset |
| Stop loss | `stop_loss_pct` | 5% | Hard stop from entry |
| Trailing stop | `trailing_stop_pct` | 3% | Stop from peak |
| Entry threshold | `entry_threshold` | 0.5 | Min conviction to enter |
| Exit threshold | `exit_threshold` | 0.3 | Conviction level to exit |

### Portfolio-Level Controls

| Control | Parameter | Default | Description |
|---------|-----------|---------|-------------|
| Max gross | `max_gross_exposure` | 150% | Total |long| + |short| |
| Target vol | `target_vol` | 15% | Annualized portfolio vol target |
| Max positions | `n_long + n_short` | 6 | Max simultaneous positions |

### Vol-Adjusted Stops

For crypto's high volatility, use vol-adjusted stops:

```python
def vol_adjusted_stop(base_stop: float, current_vol: float, base_vol: float = 0.50) -> float:
    """
    Adjust stop based on current volatility.
    
    Args:
        base_stop: Base stop percentage (e.g., 0.05 for 5%)
        current_vol: Current annualized volatility
        base_vol: Reference volatility (e.g., 50% annual for crypto)
        
    Returns:
        Adjusted stop percentage
    """
    vol_ratio = current_vol / base_vol
    return base_stop * vol_ratio
```

## Backtesting Framework

### Core Loop

```python
class CrossSectionalBacktest:
    """Backtest engine for cross-sectional L/S strategies."""
    
    def __init__(
        self,
        symbols: List[str],
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        rebalance_freq: str = '1D',
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.rebalance_freq = rebalance_freq
        
        self.signal_generator = CrossSectionalSignal(symbols)
        self.position_manager = PositionManager()
    
    def run(self) -> pd.DataFrame:
        """Run backtest, return daily portfolio returns."""
        results = []
        
        for date in self._rebalance_dates():
            # 1. Compute signals (point-in-time)
            signals = self.signal_generator.compute(date)
            
            # 2. Get current prices
            prices = self._get_prices(date)
            
            # 3. Generate target weights
            targets = self.position_manager.generate_targets(signals, prices)
            
            # 4. Calculate next-period returns
            next_returns = self._get_returns(date, self._next_date(date))
            portfolio_ret = (targets * next_returns).sum()
            
            results.append({
                'date': date,
                'return': portfolio_ret,
                'gross_exposure': targets.abs().sum(),
                'net_exposure': targets.sum(),
                'n_long': (targets > 0).sum(),
                'n_short': (targets < 0).sum(),
            })
        
        return pd.DataFrame(results)
```

### Metrics

```python
def compute_metrics(returns: pd.Series) -> Dict[str, float]:
    """Compute standard backtest metrics."""
    trading_days = 252
    
    ann_return = returns.mean() * trading_days
    ann_vol = returns.std() * np.sqrt(trading_days)
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0
    
    cumret = (1 + returns).cumprod()
    peak = cumret.cummax()
    drawdown = (peak - cumret) / peak
    max_dd = drawdown.max()
    
    calmar = ann_return / max_dd if max_dd > 0 else 0
    
    return {
        'ann_return': ann_return,
        'ann_vol': ann_vol,
        'sharpe': sharpe,
        'max_drawdown': max_dd,
        'calmar': calmar,
        'skewness': returns.skew(),
        'kurtosis': returns.kurtosis(),
    }
```

## Suggested Parameters for Crypto

| Parameter | Suggested | Rationale |
|-----------|-----------|-----------|
| `n_long` | 3-4 | Concentrated bets |
| `n_short` | 3-4 | Balanced L/S |
| `entry_threshold` | 0.5 | Moderate conviction |
| `exit_threshold` | 0.3 | Allow signal decay |
| `stop_loss_pct` | 5-10% | Crypto volatility |
| `trailing_stop_pct` | 3-5% | Protect profits |
| `max_position_pct` | 15-25% | Concentration limit |
| `target_vol` | 15-25% | Reasonable for crypto |
| `rebalance_freq` | Daily/4h | 24/7 trading |

## Implementation Roadmap

1. **Phase 1: Basic Cross-Sectional**
   - Implement factor computation from existing data
   - Simple rank-based L/S (Approach 1)
   - Basic backtest metrics

2. **Phase 2: Conviction Scoring**
   - Add conviction layer
   - Implement variable exposure
   - Test different conviction methods

3. **Phase 3: Position Management**
   - Add entry/exit logic
   - Implement stop losses
   - State tracking

4. **Phase 4: Risk Controls**
   - Vol targeting
   - Position limits
   - Correlation monitoring

5. **Phase 5: Live Trading**
   - Connect to execution layer
   - Real-time signal generation
   - Order management

## Related Documents

- [Feature Processing Layer](./feature-processing-layer.md) - Feature computation
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System overview
