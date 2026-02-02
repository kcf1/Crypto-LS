"""
Test script: Backfill Top Long/Short Account for first 10 symbols only.
Quick test to verify collection works before running full backfill.

Run from project root: python scripts/backfill/test_backfill_top_long_short_account.py
"""

import logging
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings, setup_logging
from data import Collector, Storage

logger = logging.getLogger(__name__)

DAYS_BACK = 7
MS_PER_DAY = int(24 * 3600 * 1000)
DELAY_SEC = 0.2
MAX_429_RETRIES = 5
MAX_EMPTY_RETRIES = 3
EMPTY_RETRY_DELAY = 0.5
LIMIT = 500
PERIOD = "5m"


def fetch_with_retry(collector, symbol, period, *, start_time=None, end_time=None, limit=500):
    """Call collector.fetch_top_long_short_account with retry logic."""
    for attempt in range(MAX_429_RETRIES):
        try:
            rows = collector.fetch_top_long_short_account(
                symbol=symbol, period=period,
                start_time=start_time, end_time=end_time, limit=limit,
            )
            if not rows and attempt < MAX_EMPTY_RETRIES:
                logger.warning("Empty response for %s %s (attempt %s), retrying", symbol, period, attempt + 1)
                time.sleep(EMPTY_RETRY_DELAY)
                continue
            return rows
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < MAX_429_RETRIES - 1:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning("429 rate limit, sleeping %s s", retry_after)
                time.sleep(retry_after)
                continue
            raise
    return []


def main():
    setup_logging()
    symbols = settings.symbols[:10]
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - (DAYS_BACK * MS_PER_DAY)

    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()

    logger.info("TEST: Top Long/Short Account backfill for %s symbols, period=%s, last %s days", len(symbols), PERIOD, DAYS_BACK)

    total_written = 0
    for i, symbol in enumerate(tqdm(symbols, desc="Symbols")):
        symbol_rows = 0
        current_end_time = end_time_ms

        while current_end_time > start_time_ms:
            rows = fetch_with_retry(collector, symbol, PERIOD, start_time=start_time_ms, end_time=current_end_time, limit=LIMIT)
            if not rows:
                break

            filtered_rows = [r for r in rows if start_time_ms <= r[0] <= end_time_ms]
            if filtered_rows:
                storage.write_top_long_short_account(symbol, PERIOD, filtered_rows)
                symbol_rows += len(filtered_rows)
                total_written += len(filtered_rows)

            oldest_ts = min(r[0] for r in rows)
            if oldest_ts <= start_time_ms:
                break
            current_end_time = oldest_ts - 1
            time.sleep(DELAY_SEC)

        logger.info("%s: %s rows", symbol, symbol_rows)

    logger.info("TEST COMPLETE: %s total rows written", total_written)


if __name__ == "__main__":
    main()
