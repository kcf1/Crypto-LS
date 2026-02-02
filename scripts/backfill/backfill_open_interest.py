"""
Backfill Open Interest: maximum available (~30 days), 5m period, for all symbols in settings.symbols.
Uses data.Collector (REST) and data.Storage; writes to DATABASE_URL (Postgres) when set, else SQLite.
Paginates by 500 records per request (Binance limit).

Note: Binance only retains ~30 days of historical open interest data.

Run from project root: python scripts/backfill/backfill_open_interest.py
"""

import logging
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

# Run from project root so config and data are importable
if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings, setup_logging
from data import Collector, Storage

logger = logging.getLogger(__name__)

# ~30 days in milliseconds
MS_PER_30D = int(30 * 24 * 3600 * 1000)

DELAY_SEC = 0.2  # Increased delay to reduce rate limit issues
MAX_429_RETRIES = 5
MAX_EMPTY_RETRIES = 3  # Retry if empty response (could be rate limit)
EMPTY_RETRY_DELAY = 2.0  # Wait 2 seconds before retrying empty response
LIMIT = 500  # Binance limit for this endpoint
PERIOD = "5m"  # 5-minute periods


def fetch_open_interest_with_retry(
    collector: Collector,
    symbol: str,
    period: str,
    *,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int,
) -> list:
    """
    Call collector.fetch_open_interest_hist; on 429, sleep Retry-After and retry up to MAX_429_RETRIES.
    Also retries on empty responses (could indicate rate limiting) up to MAX_EMPTY_RETRIES.
    """
    for attempt in range(MAX_429_RETRIES):
        try:
            rows = collector.fetch_open_interest_hist(
                symbol=symbol,
                period=period,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
            
            # Retry if empty response (could be rate limit or temporary issue)
            if not rows and attempt < MAX_EMPTY_RETRIES:
                logger.warning(
                    "Empty response for %s %s (attempt %s/%s), retrying after %s s",
                    symbol,
                    period,
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
    
    # Wait 60 minutes before starting backfill
    WAIT_MINUTES = 60
    WAIT_SECONDS = WAIT_MINUTES * 60
    
    print(f"Waiting {WAIT_MINUTES} minutes before starting backfill...")
    print("Press Ctrl+C to cancel and start immediately\n")
    
    try:
        # Show progress bar for 60 minutes (update every second)
        with tqdm(total=WAIT_SECONDS, desc="Waiting", unit="s", ncols=100, bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}s [{elapsed}<{remaining}]") as pbar:
            for _ in range(WAIT_SECONDS):
                time.sleep(1)
                pbar.update(1)
    except KeyboardInterrupt:
        print("\n\nStarting backfill immediately (wait cancelled)")
    
    print("\nStarting open interest backfill...\n")
    
    symbols = settings.symbols
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - MS_PER_30D
    run_start = time.perf_counter()

    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()

    logger.info("Starting open interest backfill: %s symbols, period=%s, target: ~30 days", len(symbols), PERIOD)
    db_target = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    logger.info("Target: %s", db_target)
    logger.info("Note: Binance only retains ~30 days of historical data")

    total_written = 0
    failed = []

    for i, symbol in enumerate(symbols):
        print(f"  {i + 1}/{len(symbols)} {symbol} ...", flush=True)
        logger.info("Symbol %s/%s: %s", i + 1, len(symbols), symbol)
        cursor_ms = start_time_ms
        symbol_rows = 0
        
        try:
            while cursor_ms < end_time_ms:
                rows = fetch_open_interest_with_retry(
                    collector,
                    symbol,
                    PERIOD,
                    start_time=cursor_ms,
                    end_time=end_time_ms,
                    limit=LIMIT,
                )
                if not rows:
                    break
                
                storage.write_open_interest(symbol, PERIOD, rows)
                symbol_rows += len(rows)
                total_written += len(rows)
                
                # Move cursor to last timestamp + 1
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
        "Done: %s total rows written to %s in %.1f min",
        total_written,
        db_target,
        elapsed_sec / 60,
    )
    if failed:
        logger.warning("Failed symbols (%s): %s", len(failed), [s for s, _ in failed])
    print(f"Done: {total_written} rows in {elapsed_sec / 60:.1f} min.")


if __name__ == "__main__":
    main()
