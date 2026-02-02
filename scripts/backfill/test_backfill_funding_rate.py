"""
Test script: Backfill Funding Rate for first 10 symbols only.
Quick test to verify funding rate collection works before running full backfill.

Run from project root: python scripts/backfill/test_backfill_funding_rate.py
"""

import logging
import sys
import time
from pathlib import Path

import requests

# Run from project root so config and data are importable
if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings, setup_logging
from data import Collector, Storage

logger = logging.getLogger(__name__)

# Test with shorter time range: last 30 days instead of 5 years
DAYS_BACK = 30
MS_PER_30D = int(DAYS_BACK * 24 * 3600 * 1000)

DELAY_SEC = 0.2
MAX_429_RETRIES = 5
MAX_EMPTY_RETRIES = 3  # Retry if empty response (could be rate limit)
EMPTY_RETRY_DELAY = 2.0  # Wait 2 seconds before retrying empty response
LIMIT = 1000  # Binance limit


def fetch_funding_rate_with_retry(
    collector: Collector,
    symbol: str,
    *,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int,
) -> list:
    """
    Call collector.fetch_funding_rate; on 429, sleep Retry-After and retry up to MAX_429_RETRIES.
    Also retries on empty responses (could indicate rate limiting) up to MAX_EMPTY_RETRIES.
    """
    for attempt in range(MAX_429_RETRIES):
        try:
            rows = collector.fetch_funding_rate(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
            
            # Retry if empty response (could be rate limit or temporary issue)
            if not rows and attempt < MAX_EMPTY_RETRIES:
                logger.warning(
                    "Empty response for %s (attempt %s/%s), retrying after %s s",
                    symbol,
                    attempt + 1,
                    MAX_EMPTY_RETRIES,
                    EMPTY_RETRY_DELAY,
                )
                time.sleep(EMPTY_RETRY_DELAY)
                continue
            
            return rows
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < MAX_429_RETRIES - 1:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning("429 rate limit, sleeping %s s (attempt %s)", retry_after, attempt + 1)
                time.sleep(retry_after)
                continue
            raise
    return []


def main() -> None:
    setup_logging()
    # Test with first 10 symbols only
    symbols = settings.symbols[:10]
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - MS_PER_30D
    run_start = time.perf_counter()

    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()

    logger.info("TEST: Funding rate backfill for %s symbols, last %s days", len(symbols), DAYS_BACK)
    db_target = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    logger.info("Target: %s", db_target)

    total_written = 0
    failed = []

    for i, symbol in enumerate(symbols):
        print(f"  {i + 1}/{len(symbols)} {symbol} ...", flush=True)
        logger.info("Symbol %s/%s: %s", i + 1, len(symbols), symbol)
        cursor_ms = start_time_ms
        symbol_rows = 0
        
        try:
            while cursor_ms < end_time_ms:
                rows = fetch_funding_rate_with_retry(
                    collector,
                    symbol,
                    start_time=cursor_ms,
                    end_time=end_time_ms,
                    limit=LIMIT,
                )
                if not rows:
                    break
                
                storage.write_funding_rate(symbol, rows)
                symbol_rows += len(rows)
                total_written += len(rows)
                
                # Move cursor to last funding_time + 1
                cursor_ms = rows[-1][0] + 1
                time.sleep(DELAY_SEC)
            
            print(f"  {i + 1}/{len(symbols)} {symbol}: {symbol_rows} rows", flush=True)
            logger.info("  %s/%s %s: %s rows", i + 1, len(symbols), symbol, symbol_rows)
        except Exception as e:
            print(f"  {i + 1}/{len(symbols)} {symbol}: FAILED {e}", flush=True)
            logger.warning("  %s/%s %s failed: %s", i + 1, len(symbols), symbol, e)
            failed.append((symbol, str(e)))
        time.sleep(DELAY_SEC)

    elapsed_sec = time.perf_counter() - run_start
    logger.info(
        "TEST COMPLETE: %s total rows written to %s in %.1f sec",
        total_written,
        db_target,
        elapsed_sec,
    )
    if failed:
        logger.warning("Failed symbols (%s): %s", len(failed), [s for s, _ in failed])
        print(f"FAILED: {len(failed)} symbols")
    else:
        print(f"SUCCESS: {total_written} rows written in {elapsed_sec:.1f} sec.")


if __name__ == "__main__":
    main()
