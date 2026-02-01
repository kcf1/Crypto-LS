"""
Binance OHLCV incremental update task.

One subprocess per data source; this is the Binance OHLCV source. Fetches new
bars after the last stored bar and re-fetches the last N bars (tail refresh)
so real-time corrections from the API overwrite existing rows. Uses Collector +
Storage + settings (delay, 429 retry). Registered in data.updates; the general
entry point (run_data_updater.py) invokes run() at fixed interval.
"""

import logging
import re
import time
from typing import List, Optional

import requests

from config import settings
from data import Collector, Storage

logger = logging.getLogger(__name__)

TAIL_BARS = 3
DELAY_SEC = 0.1
MAX_429_RETRIES = 5

# Binance interval -> milliseconds (e.g. 5m -> 300_000, 1h -> 3_600_000)
_INTERVAL_MS: dict[str, int] = {}
for m in [1, 3, 5, 15, 30]:
    _INTERVAL_MS[f"{m}m"] = m * 60 * 1000
for h in [1, 2, 4, 6, 8, 12]:
    _INTERVAL_MS[f"{h}h"] = h * 3600 * 1000
for d in [1, 3]:
    _INTERVAL_MS[f"{d}d"] = d * 86400 * 1000
_INTERVAL_MS["1w"] = 7 * 86400 * 1000


def _interval_to_ms(interval: str) -> int:
    """Return interval duration in milliseconds (e.g. '5m' -> 300_000)."""
    if interval in _INTERVAL_MS:
        return _INTERVAL_MS[interval]
    m = re.match(r"^(\d+)([mhd])$", interval.lower())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "m":
            return n * 60 * 1000
        if unit == "h":
            return n * 3600 * 1000
        if unit == "d":
            return n * 86400 * 1000
    raise ValueError(f"Unsupported interval: {interval!r}")


def _fetch_klines_with_retry(
    collector: Collector,
    symbol: str,
    interval: str,
    *,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int,
) -> List[tuple]:
    """Call collector.fetch_klines; on 429, sleep Retry-After and retry."""
    for attempt in range(MAX_429_RETRIES):
        try:
            return collector.fetch_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < MAX_429_RETRIES - 1:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning(
                    "429 rate limit, sleeping %s s (attempt %s)", retry_after, attempt + 1
                )
                time.sleep(retry_after)
                continue
            raise
    return []


def run() -> None:
    """One-shot Binance OHLCV incremental update (tail refresh + new bars)."""
    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()
    timeframe = settings.default_timeframe
    interval_ms = _interval_to_ms(timeframe)
    limit = settings.ohlcv_limit_per_request

    for symbol in settings.symbols:
        latest = storage.get_latest_open_time(symbol, timeframe)
        if latest is None:
            logger.debug("Skip %s %s: no stored data", symbol, timeframe)
            continue
        start_time_ms = max(0, latest - (TAIL_BARS - 1) * interval_ms)
        try:
            rows = _fetch_klines_with_retry(
                collector,
                symbol,
                timeframe,
                start_time=start_time_ms,
                limit=limit,
            )
            if not rows:
                continue
            storage.write_ohlcv(symbol, timeframe, rows)
            logger.info("%s %s: wrote %s rows (tail refresh + new)", symbol, timeframe, len(rows))
        except Exception as e:
            logger.warning("%s %s incremental update failed: %s", symbol, timeframe, e)
        time.sleep(DELAY_SEC)
