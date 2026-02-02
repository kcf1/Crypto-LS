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
    Also retries on empty responses (likely rate limiting) up to MAX_EMPTY_RETRIES.
    
    Common failure reasons:
    - HTTP 429: Rate limit exceeded (1000 req/5min IP limit)
    - HTTP 418: IP banned (2min-3days, escalates on repeat offenses)
    - Empty response: Likely rate limit
    - HTTP 400: Invalid parameters (symbol, period, time range)
    - Network errors: Timeout, connection failure
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
            status_code = e.response.status_code
            if status_code == 429 and attempt < MAX_429_RETRIES - 1:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning("429 rate limit for %s %s, sleeping %s s (attempt %s/%s)", 
                             symbol, period, retry_after, attempt + 1, MAX_429_RETRIES)
                time.sleep(retry_after)
                continue
            elif status_code == 418:
                logger.error("418 IP banned for %s %s - wait 2min-3days. Response: %s", 
                           symbol, period, e.response.text)
                raise Exception(f"IP banned (HTTP 418) - wait before retrying") from e
            elif status_code == 400:
                logger.error("400 Bad Request for %s %s - check symbol/period/time range. Response: %s", 
                           symbol, period, e.response.text)
                raise Exception(f"Bad Request (HTTP 400): {e.response.text}") from e
            else:
                logger.error("HTTP %s error for %s %s: %s", status_code, symbol, period, e.response.text)
                raise
        except requests.exceptions.Timeout as e:
            logger.error("Timeout for %s %s (attempt %s/%s): %s", symbol, period, attempt + 1, MAX_429_RETRIES, e)
            if attempt < MAX_429_RETRIES - 1:
                time.sleep(5)  # Wait before retrying timeout
                continue
            raise
        except requests.exceptions.ConnectionError as e:
            logger.error("Connection error for %s %s (attempt %s/%s): %s", symbol, period, attempt + 1, MAX_429_RETRIES, e)
            if attempt < MAX_429_RETRIES - 1:
                time.sleep(5)  # Wait before retrying connection error
                continue
            raise
    return []


def main() -> None:
    setup_logging()
    
    print("Starting open interest backfill...\n")
    
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
        logger.info("  Target time range: %s to %s (%.1f days)", 
                   start_time_ms, end_time_ms, (end_time_ms - start_time_ms) / (24 * 3600 * 1000))
        symbol_rows = 0
        batch_count = 0
        
        try:
            consecutive_empty = 0
            MAX_CONSECUTIVE_EMPTY = 3  # Break after 3 consecutive empty responses (after retries)
            
            # For pagination: keep startTime fixed, move endTime backward
            # Binance returns data in reverse chronological order (newest first)
            current_end_time = end_time_ms
            
            while current_end_time > start_time_ms:
                batch_count += 1
                logger.debug("  Batch %s: Requesting startTime=%s, endTime=%s (range: %.1f days)", 
                           batch_count, start_time_ms, current_end_time,
                           (current_end_time - start_time_ms) / (24 * 3600 * 1000))
                
                rows = fetch_open_interest_with_retry(
                    collector,
                    symbol,
                    PERIOD,
                    start_time=start_time_ms,
                    end_time=current_end_time,
                    limit=LIMIT,
                )
                
                if not rows:
                    # After retries in fetch_open_interest_with_retry, if still empty, handle gaps
                    consecutive_empty += 1
                    logger.warning("  Batch %s: Empty response (consecutive empty: %s/%s)", 
                                 batch_count, consecutive_empty, MAX_CONSECUTIVE_EMPTY)
                    if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                        logger.info("  %s: Stopping after %s consecutive empty responses (likely reached end of available data)", 
                                  symbol, consecutive_empty)
                        break
                    # Move endTime backward by 1 hour to skip potential gaps
                    current_end_time -= 3600 * 1000
                    logger.debug("  Skipping gap: moving endTime backward by 1 hour to %s", current_end_time)
                    continue
                
                # Reset empty counter on successful fetch
                consecutive_empty = 0
                
                # Log batch details
                if rows:
                    # Check data order: compare first and last timestamps
                    first_ts = rows[0][0]
                    last_ts = rows[-1][0]
                    
                    # Determine order: if first < last, data is chronological (oldest first)
                    # If first > last, data is reverse chronological (newest first)
                    if first_ts < last_ts:
                        # Chronological order: rows[0] is oldest, rows[-1] is newest
                        oldest_ts = first_ts
                        newest_ts = last_ts
                        data_order = "chronological (oldest first)"
                    else:
                        # Reverse chronological: rows[0] is newest, rows[-1] is oldest
                        newest_ts = first_ts
                        oldest_ts = last_ts
                        data_order = "reverse chronological (newest first)"
                    
                    range_days = abs(newest_ts - oldest_ts) / (24 * 3600 * 1000)
                    logger.info("  Batch %s: Received %s rows, order: %s, oldest: %s, newest: %s, range: %.1f days", 
                              batch_count, len(rows), data_order, oldest_ts, newest_ts, range_days)
                    logger.debug("  Batch %s: First row timestamp: %s, Last row timestamp: %s", 
                               batch_count, rows[0][0], rows[-1][0])
                
                # Filter rows to only include those within our time range
                # Binance might return data outside the requested range
                filtered_rows = [r for r in rows if start_time_ms <= r[0] <= end_time_ms]
                filtered_out = len(rows) - len(filtered_rows)
                
                if filtered_out > 0:
                    logger.warning("  Batch %s: Filtered out %s rows outside time range (kept %s)", 
                                 batch_count, filtered_out, len(filtered_rows))
                
                if filtered_rows:
                    storage.write_open_interest(symbol, PERIOD, filtered_rows)
                    symbol_rows += len(filtered_rows)
                    total_written += len(filtered_rows)
                    logger.debug("  Batch %s: Wrote %s rows to storage (total for symbol: %s)", 
                               batch_count, len(filtered_rows), symbol_rows)
                else:
                    logger.warning("  Batch %s: No rows within time range after filtering", batch_count)
                
                # Determine oldest timestamp based on data order
                # Check if data is chronological (oldest first) or reverse chronological (newest first)
                if rows:
                    first_ts = rows[0][0]
                    last_ts = rows[-1][0]
                    if first_ts < last_ts:
                        # Chronological: rows[0] is oldest, rows[-1] is newest
                        oldest_timestamp = first_ts
                        newest_timestamp = last_ts
                    else:
                        # Reverse chronological: rows[0] is newest, rows[-1] is oldest
                        oldest_timestamp = last_ts
                        newest_timestamp = first_ts
                else:
                    oldest_timestamp = current_end_time
                    newest_timestamp = current_end_time
                
                logger.info("  Batch %s: Oldest timestamp: %s, start_time_ms: %s, diff: %.1f days", 
                          batch_count, oldest_timestamp, start_time_ms,
                          (oldest_timestamp - start_time_ms) / (24 * 3600 * 1000))
                
                # Stop if we've reached or passed the start time
                if oldest_timestamp <= start_time_ms:
                    logger.info("  %s: Reached start_time_ms (%s), stopping pagination. Total batches: %s, Total rows: %s", 
                              symbol, start_time_ms, batch_count, symbol_rows)
                    break
                
                # Move endTime backward: set to oldest record's timestamp - 1ms
                # This gets the next batch going backward in time
                prev_end_time = current_end_time
                current_end_time = oldest_timestamp - 1
                step_days = (prev_end_time - current_end_time) / (24 * 3600 * 1000)
                logger.info("  Batch %s: Moving endTime backward: %s -> %s (step: %.1f days, remaining: %.1f days)", 
                           batch_count, prev_end_time, current_end_time, step_days,
                           (current_end_time - start_time_ms) / (24 * 3600 * 1000))
                
                # Safety check: if step is too small, we might be stuck
                if step_days < 0.01:  # Less than ~14 minutes
                    logger.warning("  Batch %s: Step size very small (%.3f days), possible pagination issue. "
                                 "Oldest: %s, Prev endTime: %s. Continuing anyway.", 
                                 batch_count, step_days, oldest_timestamp, prev_end_time)
                    # Don't break - continue to next batch
                    # The issue might be that we're getting the same data, so we need to move further back
                
                time.sleep(DELAY_SEC)
            
            # Log final status
            if current_end_time <= start_time_ms:
                logger.info("  %s: Completed pagination (reached start_time_ms)", symbol)
            else:
                logger.warning("  %s: Stopped pagination but current_end_time (%s) > start_time_ms (%s). "
                             "This may indicate incomplete data collection.", 
                             symbol, current_end_time, start_time_ms)
            
            expected_rows = int((end_time_ms - start_time_ms) / (5 * 60 * 1000))  # 5-minute intervals
            coverage_pct = (symbol_rows / expected_rows * 100) if expected_rows > 0 else 0
            print(f"  {i + 1}/{len(symbols)} {symbol}: {symbol_rows} rows (expected: ~{expected_rows}, coverage: {coverage_pct:.1f}%)", flush=True)
            logger.info("  %s/%s %s: %s rows (expected: ~%s, coverage: %.1f%%)", 
                       i + 1, len(symbols), symbol, symbol_rows, expected_rows, coverage_pct)
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
