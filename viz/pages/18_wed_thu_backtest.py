"""
Page: Wed/Thu calendar effect backtest on EOD data.

Signal = long on Wednesday, short on Thursday, neutral otherwise. Exploits weekly patterns
in crypto returns. Standardized and vol-matched position.
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

st.title("Wed/Thu calendar effect backtest")
st.caption(
    "EOD close, signal = +1 on Wed, -1 on Thu, 0 otherwise; shift forward (predict next bar). "
    "Vol-matched position. Cum return = cumsum(log return)."
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
    vol_look1 = st.slider("Vol window (days)", 5, 90, 30, key="vol1_wt")
    cap1 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap1_wt")

    st.subheader("Strategy 2")
    vol_look2 = st.slider("Vol window (days)", 5, 90, 30, key="vol2_wt")
    cap2 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap2_wt")

    st.subheader("Strategy 3")
    vol_look3 = st.slider("Vol window (days)", 5, 90, 30, key="vol3_wt")
    cap3 = st.slider("Position cap", 0.5, 5.0, 3.0, 0.1, key="cap3_wt")

    st.divider()
    target_vol = st.slider("Target vol (ann) — all series", 0.05, 0.50, 0.15, 0.01, key="target_vol_wt")

    st.divider()
    show_raw = st.checkbox("Show Raw", value=True, key="show_raw_wt")
    show_s1 = st.checkbox("Show Strategy 1", value=True, key="show_s1_wt")
    show_s2 = st.checkbox("Show Strategy 2", value=True, key="show_s2_wt")
    show_s3 = st.checkbox("Show Strategy 3", value=True, key="show_s3_wt")
    show_avg = st.checkbox("Show Avg (1+2+3)", value=True, key="show_avg_wt")
    show_reg = st.checkbox("Show Reg (β≥0)", value=True, key="show_reg_wt")

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
eod = df.groupby("date", as_index=False).agg(close=("close", "last"))
eod = eod.sort_values("date").reset_index(drop=True)

# Log return
eod["ret"] = np.log(eod["close"] / eod["close"].shift(1))
eod = eod.dropna(subset=["ret"]).reset_index(drop=True)
close = eod["close"]
ret = eod["ret"]
dates = eod["date"]

# Get day of week (0=Monday, 6=Sunday)
eod["weekday"] = pd.to_datetime(eod["date"]).dt.dayofweek


def run_strategy(
    vol_window: int,
    target_vol_ann: float,
    cap: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Wed/Thu calendar strategy: long Wed, short Thu, neutral otherwise.
    
    Returns: (pnl, position, signal)
    """
    # 1. Binary signal: +1 on Wed (2), -1 on Thu (3), else 0
    signal_raw = pd.Series(0.0, index=ret.index)
    signal_raw[eod["weekday"] == 2] = 1.0   # Wednesday
    signal_raw[eod["weekday"] == 3] = -1.0  # Thursday
    
    # 2. Shift forward (predict next bar)
    signal = signal_raw.shift(1).fillna(0)
    
    # 3. Volatility: separate EWM std for Wed and Thu bars (scaled vol window = vol_window / 7)
    vol_scaled_window = max(1, int(vol_window / 7))
    
    # Separate volatility for Wed and Thu
    wed_mask = eod["weekday"] == 2
    thu_mask = eod["weekday"] == 3
    
    vol_wed = ret[wed_mask].ewm(span=vol_scaled_window, adjust=False).std().clip(lower=VOL_FLOOR)
    vol_thu = ret[thu_mask].ewm(span=vol_scaled_window, adjust=False).std().clip(lower=VOL_FLOOR)
    
    # Interpolate volatility across index
    vol_estimator = ret.ewm(span=vol_window, adjust=False).std().clip(lower=VOL_FLOOR)
    
    # Use separate vol for Wed/Thu where available, otherwise use general vol
    vol_combined = vol_estimator.copy()
    if len(vol_wed) > 0:
        vol_combined[wed_mask] = vol_wed.values if len(vol_wed) == wed_mask.sum() else vol_estimator[wed_mask]
    if len(vol_thu) > 0:
        vol_combined[thu_mask] = vol_thu.values if len(vol_thu) == thu_mask.sum() else vol_estimator[thu_mask]
    
    # 4. Position sizing
    target_daily = target_vol_ann / np.sqrt(TRADING_DAYS)
    position = (signal * target_daily / vol_combined).clip(-cap, cap)
    
    # 5. PnL calculation
    pnl = position.shift(1) * ret
    pnl = pnl.fillna(0)
    
    return pnl, position, signal


pnl1, pos1, s1 = run_strategy(vol_look1, target_vol, cap1)
pnl2, pos2, s2 = run_strategy(vol_look2, target_vol, cap2)
pnl3, pos3, s3 = run_strategy(vol_look3, target_vol, cap3)

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
    title=f"{symbol} Cumulative log return (Wed/Thu calendar effect)",
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
st.caption("Signal: +1 on Wed, -1 on Thu, 0 otherwise; shift forward; vol-matched × cap.")
