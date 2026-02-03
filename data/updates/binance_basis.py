"""
Binance Basis incremental update task.

Fetches new basis records after the last stored record and re-fetches the last
N records (tail refresh) so real-time corrections from the API overwrite existing rows.
Uses Collector + Storage + settings (delay, 429 retry). Registered in data.updates;
the general entry point (run_data_updater.py) invokes run() at fixed interval.
"""

import logging
import time
from typing import List, Optional

import requests

from config import settings
from data import Collector, Storage

logger = logging.getLogger(__name__)

TAIL_RECORDS = 3  # Refresh last 3 records (15 minutes for 5m period)
DELAY_SEC = 0.1
MAX_429_RETRIES = 5
PERIOD = "5m"  # 5-minute periods
PERIOD_MS = 5 * 60 * 1000  # 5 minutes in milliseconds


def _fetch_basis_with_retry(
    collector: Collector,
    symbol: str,
    period: str,
    *,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int,
) -> List[tuple]:
    """Call collector.fetch_basis; on 429, sleep Retry-After and retry."""
    for attempt in range(MAX_429_RETRIES):
        try:
            return collector.fetch_basis(
                symbol=symbol,
                period=period,
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
    """One-shot Binance Basis incremental update (tail refresh + new records)."""
    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()
    limit = min(500, settings.ohlcv_limit_per_request)  # Max 500 for this endpoint
    now_ms = int(time.time() * 1000)
    end_time_ms = now_ms + 60000  # now + 1 min so latest 5m bucket included

    for symbol in settings.symbols:
        latest = storage.get_latest_basis_time(symbol, PERIOD)
        start_time_ms: Optional[int] = None
        end_time_param: Optional[int] = None
        if latest is not None:
            # Incremental: request [latest - tail, end_time] so API returns tail + new (pass both for compatibility)
            start_time_ms = max(0, latest - (TAIL_RECORDS - 1) * PERIOD_MS)
            end_time_param = end_time_ms
        # else: bootstrap with no start/end -> API returns most recent data

        try:
            rows = _fetch_basis_with_retry(
                collector,
                symbol,
                PERIOD,
                start_time=start_time_ms,
                end_time=end_time_param,
                limit=limit,
            )
            if not rows:
                continue
            storage.write_basis(symbol, PERIOD, rows)
            logger.info("%s %s: wrote %s basis records (tail refresh + new)", symbol, PERIOD, len(rows))
        except Exception as e:
            logger.warning("%s %s basis incremental update failed: %s", symbol, PERIOD, e)
        time.sleep(DELAY_SEC)
