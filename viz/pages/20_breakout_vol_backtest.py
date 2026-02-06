"""
Page: Breakout Vol strategy backtest on EOD data.

Signal = Range breakout (price relative to rolling high/low) with Weibull CDF vol tilt
and strategy decay. Long above midpoint, short below, scaled by range and vol regime.
Three PnL series with changeable parameters; toggle-able plot; enhanced stats table.
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
from sklearn.linear_model import RidgeCV

from config import settings
from data import Storage

TIMEFRAME_5M = "5m"
TRADING_DAYS = 252
VOL_FLOOR = 1e-8

st.title("Breakout Vol strategy backtest")
st.caption(
    "EOD close, signal = (price - mid) / range × 2, smoothed, with Weibull CDF vol tilt "
    "and strategy decay; vol-matched position. Cum return = cumsum(log return)."
)

storage = Storage()
symbols = settings.symbols

with st.sidebar:
    symbol = st.selectbox(
        "Symbol",
        symbols,
        index=0,
        help="Symbol (from settings.symbols).",
    )
    db_label = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    st.caption(f"Storage: {db_label}")

    st.divider()
    st.subheader("Strategy 1")
    breakout_window1 = st.slider("Breakout window (days)", 5, 100, 20, key="breakout1_bv")
    smooth_window1 = st.slider("Smooth window (days)", 1, 30, 5, key="smooth1_bv")
    vol_look1 = st.slider("Vol window (days)", 5, 90, 30, key="vol1_bv")
    weibull_c1 = st.slider("Weibull shape (c)", 0.5, 3.0, 1.5, 0.1, key="weibull_c1_bv")
    alpha_blend1 = st.slider("Alpha blend", 0.0, 1.0, 0.5, 0.1, key="alpha1_bv")
    use_decay1 = st.checkbox("Use strategy decay", value=True, key="decay1_bv")
    cap1 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap1_bv")

    st.subheader("Strategy 2")
    breakout_window2 = st.slider("Breakout window (days)", 5, 100, 20, key="breakout2_bv")
    smooth_window2 = st.slider("Smooth window (days)", 1, 30, 5, key="smooth2_bv")
    vol_look2 = st.slider("Vol window (days)", 5, 90, 30, key="vol2_bv")
    weibull_c2 = st.slider("Weibull shape (c)", 0.5, 3.0, 1.5, 0.1, key="weibull_c2_bv")
    alpha_blend2 = st.slider("Alpha blend", 0.0, 1.0, 0.5, 0.1, key="alpha2_bv")
    use_decay2 = st.checkbox("Use strategy decay", value=True, key="decay2_bv")
    cap2 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap2_bv")

    st.subheader("Strategy 3")
    breakout_window3 = st.slider("Breakout window (days)", 5, 100, 20, key="breakout3_bv")
    smooth_window3 = st.slider("Smooth window (days)", 1, 30, 5, key="smooth3_bv")
    vol_look3 = st.slider("Vol window (days)", 5, 90, 30, key="vol3_bv")
    weibull_c3 = st.slider("Weibull shape (c)", 0.5, 3.0, 1.5, 0.1, key="weibull_c3_bv")
    alpha_blend3 = st.slider("Alpha blend", 0.0, 1.0, 0.5, 0.1, key="alpha3_bv")
    use_decay3 = st.checkbox("Use strategy decay", value=True, key="decay3_bv")
    cap3 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap3_bv")

    st.divider()
    target_vol = st.slider("Target vol (ann) — all series", 0.05, 0.50, 0.15, 0.01, key="target_vol_bv")

    st.divider()
    show_raw = st.checkbox("Show Raw", value=True, key="show_raw_bv")
    show_s1 = st.checkbox("Show Strategy 1", value=True, key="show_s1_bv")
    show_s2 = st.checkbox("Show Strategy 2", value=True, key="show_s2_bv")
    show_s3 = st.checkbox("Show Strategy 3", value=True, key="show_s3_bv")
    show_avg = st.checkbox("Show Avg (1+2+3)", value=True, key="show_avg_bv")
    show_reg = st.checkbox("Show Reg (β≥0)", value=True, key="show_reg_bv")

rows = storage.read_ohlcv(symbol=symbol, timeframe=TIMEFRAME_5M)
if not rows:
    st.warning(
        f"No **5m** OHLCV data for **{symbol}**. "
        "Run `scripts/utils/download_last_24h.py` or `scripts/backfill/update_5y_5m.py` first."
    )
    st.stop()

df = pd.DataFrame(
    rows,
    columns=["open_time", "open", "high", "low", "close", "volume", "close_time"],
)
df["datetime"] = pd.to_datetime(df["open_time"], unit="ms")
df["date"] = df["datetime"].dt.date
# Aggregate to EOD: last close, max high, min low for Rogers-Satchell
eod = df.groupby("date", as_index=False).agg(
    close=("close", "last"),
    high=("high", "max"),
    low=("low", "min"),
    open=("open", "first"),
)
eod = eod.sort_values("date").reset_index(drop=True)

# Log return
eod["ret"] = np.log(eod["close"] / eod["close"].shift(1))
eod = eod.dropna(subset=["ret"]).reset_index(drop=True)
close = eod["close"]
ret = eod["ret"]
dates = eod["date"]
high = eod["high"]
low = eod["low"]
open_price = eod["open"]


def rogers_satchell_volatility(high: pd.Series, low: pd.Series, open_price: pd.Series, close: pd.Series, window: int) -> pd.Series:
    """
    Rogers-Satchell volatility estimator using OHLC data.
    """
    h_c = np.log(high / close)
    l_c = np.log(low / close)
    h_o = np.log(high / open_price)
    l_o = np.log(low / open_price)
    rs = h_c * (h_c - h_o) + l_c * (l_c - l_o)
    rs_vol = np.sqrt(rs.rolling(window=window).mean()) * np.sqrt(TRADING_DAYS)
    return rs_vol.clip(lower=VOL_FLOOR)


def weibull_vol_tilt(vol_series: pd.Series, weibull_c: float) -> pd.Series:
    """
    Volatility tilt using Weibull CDF: vol_tilt = 1 - Weibull_CDF(v; c, scale)
    where scale = cdf_median × 1.5
    """
    # Calculate median for scale
    vol_median = vol_series.median()
    scale = vol_median * 1.5
    
    # Weibull CDF: 1 - exp(-(x/scale)^c)
    vol_normalized = vol_series / scale
    weibull_cdf = 1 - np.exp(-(vol_normalized ** weibull_c))
    
    # Vol tilt: reduces exposure when vol is high
    vol_tilt = 1 - weibull_cdf
    return vol_tilt.clip(0, 1)


def strategy_decay(position: pd.Series, returns: pd.Series, defactor: float = 0.1) -> pd.Series:
    """
    Strategy decay: EWM of rolling PnL → decay ∈ [0.75, 1.0] when strategy underperforms.
    """
    strat_pnl = (position * returns).ewm(span=24 * 90, adjust=False).mean()
    decay_raw = -np.clip(strat_pnl / defactor, -2, 2) / 2
    decay = 0.75 + 0.25 * decay_raw
    return decay.clip(0.75, 1.0)


def run_strategy(
    breakout_window: int,
    smooth_window: int,
    vol_window: int,
    weibull_c: float,
    alpha_blend: float,
    use_decay: bool,
    target_vol_ann: float,
    cap: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Breakout Vol strategy with Weibull CDF vol tilt and strategy decay.
    
    Returns: (pnl, position, signal)
    """
    # 1. Rolling high/low
    rolling_high = close.rolling(window=breakout_window).max()
    rolling_low = close.rolling(window=breakout_window).min()
    mid = (rolling_high + rolling_low) / 2
    rng = (rolling_high - rolling_low).clip(lower=VOL_FLOOR)
    
    # 2. Raw breakout: s_raw = (price - mid) / rng × 2 (normalized to ±1)
    signal_raw = (close - mid) / rng * 2
    
    # 3. Smooth: s_smooth = s_raw.ewm(span=smooth_window).mean()
    signal_smooth = signal_raw.ewm(span=smooth_window, adjust=False).mean()
    
    # 4. Volatility: Rogers-Satchell (or EWM std as fallback)
    try:
        vol_estimator = rogers_satchell_volatility(high, low, open_price, close, vol_window)
    except:
        vol_estimator = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR) * np.sqrt(TRADING_DAYS)
    
    # 5. Vol tilt: Weibull CDF
    vol_tilt = weibull_vol_tilt(vol_estimator, weibull_c)
    
    # 6. Alpha blend: tilt = (1-α) + α × vol_tilt
    tilt = (1 - alpha_blend) + alpha_blend * vol_tilt
    
    # 7. Combined signal
    signal_combined = signal_smooth * tilt
    
    # 8. Strategy decay (optional)
    decay = pd.Series(1.0, index=ret.index)
    if use_decay:
        # Need position for decay calculation, so we'll do iterative approach
        # First pass without decay
        target_daily = target_vol_ann / np.sqrt(TRADING_DAYS)
        position_temp = (signal_combined * target_daily / vol_estimator).clip(-cap, cap)
        decay = strategy_decay(position_temp, ret)
        signal_combined = signal_combined * decay
    
    # 9. Position sizing
    target_daily = target_vol_ann / np.sqrt(TRADING_DAYS)
    position = (signal_combined * target_daily / vol_estimator).clip(-cap, cap)
    
    # 10. PnL calculation
    pnl = position.shift(1) * ret
    pnl = pnl.fillna(0)
    
    return pnl, position, signal_smooth


pnl1, pos1, s1 = run_strategy(breakout_window1, smooth_window1, vol_look1, weibull_c1, alpha_blend1, use_decay1, target_vol, cap1)
pnl2, pos2, s2 = run_strategy(breakout_window2, smooth_window2, vol_look2, weibull_c2, alpha_blend2, use_decay2, target_vol, cap2)
pnl3, pos3, s3 = run_strategy(breakout_window3, smooth_window3, vol_look3, weibull_c3, alpha_blend3, use_decay3, target_vol, cap3)

# Reg: 4 models
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

# Avg of 3
pos_avg = (pos1 + pos2 + pos3) / 3
pnl_avg = pos_avg.shift(1) * ret
pnl_avg = pnl_avg.fillna(0)

# Rescale all series to match target vol
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

# Cum return
cumret_raw = ret_scaled.cumsum()
cumret1 = np.log(1 + pnl1).cumsum()
cumret2 = np.log(1 + pnl2).cumsum()
cumret3 = np.log(1 + pnl3).cumsum()
cumret_avg = np.log(1 + pnl_avg).cumsum()
cumret_reg = np.log(1 + pnl_reg).cumsum()

fig = go.Figure()
if show_raw:
    fig.add_trace(go.Scatter(x=dates, y=cumret_raw, mode="lines", name="Raw", line=dict(width=2)))
if show_s1:
    fig.add_trace(go.Scatter(x=dates, y=cumret1, mode="lines", name="Strategy 1", line=dict(width=1.5)))
if show_s2:
    fig.add_trace(go.Scatter(x=dates, y=cumret2, mode="lines", name="Strategy 2", line=dict(width=1.5)))
if show_s3:
    fig.add_trace(go.Scatter(x=dates, y=cumret3, mode="lines", name="Strategy 3", line=dict(width=1.5)))
if show_avg:
    fig.add_trace(go.Scatter(x=dates, y=cumret_avg, mode="lines", name="Avg (1+2+3)", line=dict(width=2)))
if show_reg:
    fig.add_trace(go.Scatter(x=dates, y=cumret_reg, mode="lines", name="Reg (β≥0)", line=dict(width=2)))
fig.update_layout(
    title=f"{symbol} Cumulative log return (Breakout Vol with Weibull tilt)",
    xaxis_title="Date",
    yaxis_title="Cumulative log return",
    template="plotly_white",
    height=500,
    showlegend=True,
)
fig.update_xaxes(rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

# Stats (copy helper functions from block_momentum)
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


def cvar95(series: pd.Series) -> float:
    q = series.quantile(0.05)
    return float(series[series <= q].mean()) * 100


def cdd95(cumlog: pd.Series) -> float:
    level = np.exp(cumlog) - 1
    peak = level.cummax()
    drawdown = peak - level
    q = drawdown.quantile(0.95)
    return float(drawdown[drawdown >= q].mean()) * 100


def kurtosis_monthly(series: pd.Series, trading_days: int = 252) -> float:
    if len(series) > 30:
        if isinstance(series.index, pd.DatetimeIndex):
            monthly_ret = series.resample('M').sum()
        else:
            monthly_ret = series.groupby(series.index // 21).sum()
    else:
        monthly_ret = series
    return float(monthly_ret.kurtosis())


def sortino_ratio(pnl: pd.Series, risk_free_rate: float = 0.0, trading_days: int = 252) -> float:
    excess_return = pnl.mean() * trading_days - risk_free_rate
    downside_returns = pnl[pnl < 0]
    if len(downside_returns) == 0:
        return np.inf if excess_return > 0 else np.nan
    downside_std = downside_returns.std() * np.sqrt(trading_days)
    return excess_return / downside_std if downside_std > 1e-12 else np.nan


def hit_rate(pnl: pd.Series) -> float:
    return float((pnl > 0).sum() / len(pnl)) * 100 if len(pnl) > 0 else np.nan


def profit_factor(pnl: pd.Series) -> float:
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    return float(gross_profit / gross_loss) if gross_loss > 1e-12 else np.inf


def annual_turnover(position: pd.Series) -> float:
    return float(position.diff().abs().mean()) * TRADING_DAYS


def build_stats(ret_series: pd.Series, is_raw: bool, trading_days: int = 252) -> dict:
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

st.caption(f"Total days: {len(eod)} | {eod['date'].min()} → {eod['date'].max()}")
st.caption(
    f"Reg (β≥0): 4 models (1d/5d/10d/30d fwd ret/vol), avg betas = [{beta_reg[0]:.3f}, {beta_reg[1]:.3f}, {beta_reg[2]:.3f}] "
    f"(1d: [{beta_1d[0]:.2f},{beta_1d[1]:.2f},{beta_1d[2]:.2f}] 5d: [{beta_5d[0]:.2f},{beta_5d[1]:.2f},{beta_5d[2]:.2f}] "
    f"10d: [{beta_10d[0]:.2f},{beta_10d[1]:.2f},{beta_10d[2]:.2f}] 30d: [{beta_30d[0]:.2f},{beta_30d[1]:.2f},{beta_30d[2]:.2f}])"
)
st.caption("Signal: (price - mid) / range × 2, smoothed, × Weibull CDF vol tilt (reduces size in high vol), × strategy decay (optional), vol-matched × cap.")
