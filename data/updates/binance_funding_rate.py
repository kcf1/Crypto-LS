"""
Binance Funding Rate incremental update task.

Fetches new funding rate records after the last stored record and re-fetches the last
record (tail refresh) so real-time corrections from the API overwrite existing rows.
Funding rate updates every 8 hours (00:00, 08:00, 16:00 UTC), but we check every
5 mins and skip if no new data. Uses Collector + Storage + settings (delay, 429 retry).
Registered in data.updates; the general entry point (run_data_updater.py) invokes run() at fixed interval.
"""

import logging
import time
from typing import List, Optional

import requests

from config import settings
from data import Collector, Storage

logger = logging.getLogger(__name__)

TAIL_RECORDS = 1  # Refresh last funding rate in case of corrections
DELAY_SEC = 0.1
MAX_429_RETRIES = 5
FUNDING_INTERVAL_MS = 8 * 3600 * 1000  # 8 hours in milliseconds


def _fetch_funding_rate_with_retry(
    collector: Collector,
    symbol: str,
    *,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int,
) -> List[tuple]:
    """Call collector.fetch_funding_rate; on 429, sleep Retry-After and retry."""
    for attempt in range(MAX_429_RETRIES):
        try:
            return collector.fetch_funding_rate(
                symbol=symbol,
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
    """One-shot Binance Funding Rate incremental update (tail refresh + new records)."""
    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()
    limit = settings.ohlcv_limit_per_request

    for symbol in settings.symbols:
        latest = storage.get_latest_funding_time(symbol)
        if latest is None:
            logger.debug("Skip %s: no stored funding rate data", symbol)
            continue
        
        # Calculate start time: latest - (TAIL_RECORDS - 1) * FUNDING_INTERVAL_MS
        start_time_ms = max(0, latest - (TAIL_RECORDS - 1) * FUNDING_INTERVAL_MS)
        
        try:
            rows = _fetch_funding_rate_with_retry(
                collector,
                symbol,
                start_time=start_time_ms,
                limit=limit,
            )
            if not rows:
                continue
            
            storage.write_funding_rate(symbol, rows)
            logger.info("%s: wrote %s funding rate records (tail refresh + new)", symbol, len(rows))
        except Exception as e:
            logger.warning("%s funding rate incremental update failed: %s", symbol, e)
        time.sleep(DELAY_SEC)
