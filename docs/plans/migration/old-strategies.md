# Trading Strategies Reference

## Overview

All strategies inherit `BaseStrategy` (sklearn-style `.fit()` / `.predict()`) and produce **position as % of capital** (e.g. 0.5 = 50% long, -0.3 = 30% short).

---

## Strategy Summary

| Strategy              | Type        | Purpose                                         | Fitted in fit_models? |
|-----------------------|-------------|-------------------------------------------------|------------------------|
| **VolScaleStrategy**  | Vol scaling | Target-vol scaling baseline                     | No                     |
| **WedThuStrategy**    | Calendar    | Long Wed / Short Thu seasonality                | Yes (10% weight)       |
| **EmaVolStrategy**    | Trend       | EMA crossover with vol tilt                     | Yes (20% weight)       |
| **AccelVolStrategy**  | Trend       | EMA acceleration (momentum-of-momentum)         | Yes (15% weight)       |
| **BreakVolStrategy**  | Breakout    | Range breakout with smoothing                   | Yes (20% weight)       |
| **BlockVolStrategy**  | Trend       | Block momentum (HH + HL structure)              | Yes (15% weight)       |
| **BuySellVolStrategy**| Flow        | Taker buy/sell ratio (Binance volume flow)      | No                     |
| **RevStrategy**       | Reversal    | Short-term mean reversion with volume filter    | Yes (10% weight)       |
| **OrthAlphaStrategy** | Alpha       | Momentum-orthogonal alpha via RollingOLS        | Yes (20% weight)       |
| **WeightedOrthAlphaStrategy** | Alpha | Same, vol-weighted RollingWLS             | No                     |

---

## Detailed Strategy Descriptions

### VolScaleStrategy

**Purpose:** Simple volatility-targeting baseline. Inverse-volatility position sizing with no directional view; useful as a reference or building block.

**Signal flow:**
1. Volatility forecast: Rogers-Satchell (OHLC) with window ≈ 40% of `vol_window`, annualized
2. Raw position: `pos_raw = target_vol / v`
3. Calibrate `to_target_scaler` so in-sample PnL vol = `target_vol`
4. Final: `pos = pos_raw × to_target_scaler × strat_weight`

**Parameters:** `vol_window` (e.g. 24×30 h), `target_vol`, `strat_weight`  
**Inputs:** `close` (OHLC required for Rogers-Satchell)

---

### WedThuStrategy

**Purpose:** Calendar effect — long on Wednesday, short on Thursday, neutral otherwise. Exploits weekly patterns in crypto returns.

**Signal flow:**
1. Binary: `s = +1` on Wed bars, `s = -1` on Thu bars, else 0; shift forward (predict next bar)
2. Volatility: separate EWM std for Wed and Thu bars (scaled vol window = `vol_window / 7`)
3. Raw position: `pos_raw = s × target_vol / v`; interpolate `v` across index
4. Calibrate `to_target_scaler` from in-sample PnL
5. Final: `pos = pos_raw × to_target_scaler × strat_weight`

**Parameters:** `vol_window`, `target_vol`, `strat_weight`  
**Inputs:** `close`

---

### EmaVolStrategy

**Purpose:** Classic trend-following EMA crossover, standardized and modulated by volatility regime. Reduces size in high-vol regimes via Weibull CDF.

**Signal flow:**
1. EMA crossover: `s = fast_ema - slow_ema` (fast = `fast_ema_window`, slow = fast × `slow_ema_multiplier`)
2. Standardize: `s = s / s.ewm(vol_window).std()`, clip to ±2
3. Volatility: Rogers-Satchell, annualized
4. Vol tilt: `vol_tilt = 1 - Weibull_CDF(v; c, scale)` — reduces exposure when vol is high
5. Alpha blend: `tilt = (1-α) + α × vol_tilt`; combined `f = s × tilt`
6. Strategy decay (optional): EWM of rolling PnL → `decay ∈ [0.75, 1.0]` when strategy underperforms
7. Raw position: `pos_raw = target_vol / v × f × decay`
8. Calibrate `to_target_scaler` from in-sample PnL
9. Final: `pos = pos_raw × to_target_scaler × strat_weight`

**Parameters:** `fast_ema_window`, `slow_ema_multiplier`, `vol_window`, `weibull_c`, `alpha`, `fit_decay`, `target_vol`, `strat_weight`  
**Inputs:** `close`

---

### AccelVolStrategy

**Purpose:** Momentum-of-momentum: uses the *acceleration* of the EMA crossover (diff of standardized level) rather than level itself. Captures trend inflection and strength changes.

**Signal flow:**
1. Level: `s_level = (fast_ema - slow_ema) / std`, standardized
2. Acceleration: `s_accel_raw = s_level.diff(diff_window)` where `diff_window = fast_ema_window × diff_multiplier`
3. Re-standardize: `s_accel = s_accel_raw / s_accel_raw.ewm(vol_window).std()`, clip ±2
4. Vol tilt: same Weibull CDF as EmaVolStrategy
5. Combined: `f = s_accel × tilt`; strategy decay as in EmaVolStrategy
6. Position: `pos_raw = target_vol / v × f × decay`; calibrate scaler; final with `strat_weight`

**Parameters:** `fast_ema_window`, `slow_ema_multiplier`, `diff_multiplier`, `vol_window`, `weibull_c`, `alpha`, `fit_decay`, `target_vol`, `strat_weight`  
**Inputs:** `close`

---

### BreakVolStrategy

**Purpose:** Range breakout — where price sits relative to rolling high/low. Long above midpoint, short below, scaled by range and vol regime.

**Signal flow:**
1. Rolling: `h = rolling_max(breakout_window)`, `l = rolling_min(breakout_window)`, `mid = (h+l)/2`, `rng = h-l`
2. Raw breakout: `s_raw = (price - mid) / rng × 2` (normalized to ±1)
3. Smooth: `s_smooth = s_raw.ewm(span=smooth_window).mean()`
4. Volatility: Rogers-Satchell; vol tilt via Weibull; strategy decay optional
5. Combined: `f = s_smooth × tilt × decay`
6. Position: `pos_raw = target_vol / v × f`; calibrate scaler; final with `strat_weight`

**Parameters:** `breakout_window`, `smooth_window`, `vol_window`, `weibull_c`, `alpha`, `fit_decay`, `target_vol`, `strat_weight`  
**Inputs:** `close`

---

### BlockVolStrategy

**Purpose:** Block momentum — "higher high + higher low" over blocks. Captures sustained directional structure (trend continuation) rather than single-bar breakouts.

**Signal flow:**
1. Rolling high/low: `h`, `l` over `block_window`
2. Block changes: `hh = h.diff(block_window)`, `ll = l.diff(block_window)` — how much higher current block vs prior
3. Normalized: `s_raw = (hh + ll) / 2 / (h - l)`
4. Smooth: `s = s_raw.ewm(span=smooth_window).mean()`, clip ±2
5. Vol tilt and strategy decay as in other strategies
6. Position: `pos_raw = target_vol / v × f × decay`; calibrate scaler; final with `strat_weight`

**Parameters:** `block_window`, `smooth_window`, `vol_window`, `weibull_c`, `alpha`, `fit_decay`, `target_vol`, `strat_weight`  
**Inputs:** `close`

---

### BuySellVolStrategy

**Purpose:** Order-flow signal using taker buy volume vs total volume. High buy ratio → bullish pressure; low → bearish. Uses Binance `taker_buy_base_vol` and `volume`.

**Signal flow:**
1. Buy/sell ratio: `bsr_raw = EMA(taker_buy_base_vol) / EMA(volume)`, smoothed
2. Z-score: `bsr_z = (bsr_raw - mean) / std` over `vol_window`, clip ±2
3. Volatility: Rogers-Satchell; vol tilt via Weibull
4. Combined: `f = bsr_z × tilt`
5. Position: `pos_raw = f × target_vol / v`; calibrate scaler; final with `strat_weight`

**Parameters:** `volume_window`, `smooth_window`, `vol_window`, `weibull_c`, `alpha`, `target_vol`, `strat_weight`  
**Inputs:** `close`, `taker_buy_base_vol`, `volume` (Binance klines)

---

### RevStrategy

**Purpose:** Short-term mean reversion. Fades extreme short-term momentum when volume decay is high (indicating exhaustion).

**Signal flow:**
1. Volatility: Rogers-Satchell (or EWM std)
2. Volume decay: min-max normalize volume EWM over `vol_window` → `vlm_z ∈ [0,1]`
3. Momentum z-score: `ret_z = EMA(returns) / vol` over `reversal_window`
4. Reversal: `rev = -sign(ret_z)` only when `|ret_z| > reversal_threshold` and `vlm_z > volume_threshold`
5. Position: `pos_raw = rev × target_vol / vol_annualized`; calibrate scaler; final with `strat_weight`

**Parameters:** `vol_window`, `reversal_window`, `reversal_threshold`, `volume_threshold`, `target_vol`, `strat_weight`  
**Inputs:** `close`, `volume`

---

### OrthAlphaStrategy

**Purpose:** Extract alpha orthogonal to classic momentum. Regresses forward risk-adjusted returns on momentum; residuals are "pure alpha" uncorrelated with momentum.

**Signal flow:**
1. Momentum: `dp = (fast_ema - slow_ema) / std`, clip ±2
2. Target: `y = forward_return / vol` (risk-adjusted)
3. Rolling OLS: `y ~ const + dp.shift(forward_window)`; extract `const` (alpha) and t-value
4. Alpha signal: standardize alpha residual, clip ±2; optionally tilt by t-value (`t_tilt`)
5. Strategy decay: EWM of rolling PnL
6. Position: `pos_raw = target_vol / v × alpha_signal × decay`; calibrate scaler; final with `strat_weight`

**Parameters:** `forward_window`, `vol_window`, `regression_window`, `alpha` (tilt weight), `fit_decay`, `target_vol`, `strat_weight`  
**Inputs:** `close`

---

### WeightedOrthAlphaStrategy

**Purpose:** Same as OrthAlphaStrategy but uses **RollingWLS** with weights = `1 / vol²` to down-weight high-vol periods in the regression. More robust alpha estimate.

**Signal flow:** Identical to OrthAlphaStrategy except `RollingWLS(y, X, weights=1/vol²)` instead of RollingOLS.  
**Parameters / Inputs:** Same as OrthAlphaStrategy.

---

## Common Building Blocks

| Component       | Formula / Logic                                                                 |
|----------------|----------------------------------------------------------------------------------|
| **Volatility** | Rogers-Satchell: `fast_func.rogers_satchell_volatility(X, window)` × √ANNUAL_BARS |
| **Vol tilt**   | `vol_tilt = 1 - Weibull_CDF(v; c, scale)` — scale = `cdf_median × 1.5`; reduces size when vol is high |
| **Strategy decay** | `strat_pnl = EWM(position × returns, span=24×90)`; `decay = 0.75 + 0.25 × (-clip(strat_pnl/defactor, -2, 2) / 2)` — deflates when strategy underperforms |
| **Target vol** | `to_target_scaler = target_vol / actual_pnl_vol` fitted in-sample               |
| **Position**   | `pos = signal × target_vol / asset_vol × to_target_scaler × strat_weight`       |

---

## Model Lifecycle

- **Fit:** `fit_models.py` runs offline — fits each strategy per symbol with configured variants (e.g. EmaVolStrategy at 24, 48, 96, 192 h), saves to `models/{symbol}/*.joblib`
- **Load:** `strat_io.load_model()` at rebalance time
- **Predict:** `model.one_step_predict(bars)` returns latest position %; aggregated by simple sum across all models per asset

---

## Current Fit Parameters (fit_models.py)

**Global settings**
- `target_vol = 0.30`
- Data: `read_mtbars(symbol, limit=24*360*10)` (10 years of 1H bars)
- `bars['volume'] = bars['tick_volume']`

**Per-strategy configuration**

| Strategy | strat_weight | Variants | Parameters |
|----------|--------------|----------|------------|
| **EmaVolStrategy** | 0.20 | `fast_ema_window` ∈ [24, 48, 96, 192] | `slow_ema_multiplier=2`, `vol_window=720`, `weibull_c=2`, `alpha=1.0`, `fit_decay=True` |
| **AccelVolStrategy** | 0.15 | `fast_ema_window` ∈ [24, 48, 96, 192] | `slow_ema_multiplier=2`, `diff_multiplier=1.0`, `vol_window=720`, `weibull_c=2`, `alpha=1.0`, `fit_decay=True` |
| **BreakVolStrategy** | 0.20 | `breakout_window` ∈ [48, 96, 192, 384] | `smooth_window=12`, `vol_window=720`, `weibull_c=2`, `alpha=1.0`, `fit_decay=True` |
| **BlockVolStrategy** | 0.15 | `block_window` ∈ [48, 96, 192, 384] | `smooth_window=12`, `vol_window=720`, `weibull_c=2`, `alpha=1.0`, `fit_decay=True` |
| **WedThuStrategy** | 0.10 | `vol_window` ∈ [1440, 4320] (60d, 180d) | `target_vol=0.30` |
| **RevStrategy** | 0.10 | `reversal_window` ∈ [6, 9, 12, 15] | `vol_window=720`, `reversal_threshold=2.0`, `volume_threshold=0.3` |
| **OrthAlphaStrategy** | 0.20 | `forward_window` ∈ [24, 48, 96, 192] | `vol_window=720`, `regression_window=720`, `alpha=1.0`, `fit_decay=True` |

**Notes:**
- Variant weight = `strat_weight / len(variants)` (e.g. EmaVol 0.20/4 = 0.05 per variant)
- All strategies use `target_vol=0.30` unless noted
- Parameters are in hours (1H bars)
