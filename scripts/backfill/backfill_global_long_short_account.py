"""
Backfill Global Long/Short Account: ~30 days, 5m period, all symbols.
Binance retains ~30 days. Run from project root: python scripts/backfill/backfill_global_long_short_account.py
"""

import logging
import sys
import time
from pathlib import Path

import requests

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings, setup_logging
from data import Collector, Storage

logger = logging.getLogger(__name__)

MS_PER_30D = int(30 * 24 * 3600 * 1000)
DELAY_SEC = 0.2
MAX_429_RETRIES = 5
MAX_EMPTY_RETRIES = 3
EMPTY_RETRY_DELAY = 0.5
LIMIT = 500
PERIOD = "5m"


def fetch_with_retry(collector, symbol, period, *, start_time=None, end_time=None, limit=500):
    for attempt in range(MAX_429_RETRIES):
        try:
            rows = collector.fetch_global_long_short_account(
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
    symbols = settings.symbols
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - MS_PER_30D

    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()

    logger.info("Global Long/Short Account backfill: %s symbols, period=%s, ~30 days", len(symbols), PERIOD)
    run_start = time.perf_counter()
    total_written = 0
    failed = []

    for i, symbol in enumerate(symbols):
        print(f"  {i + 1}/{len(symbols)} {symbol} ...", flush=True)
        symbol_rows = 0
        current_end_time = end_time_ms

        try:
            while current_end_time > start_time_ms:
                rows = fetch_with_retry(
                    collector, symbol, PERIOD,
                    start_time=start_time_ms, end_time=current_end_time, limit=LIMIT,
                )
                if not rows:
                    break

                filtered_rows = [r for r in rows if start_time_ms <= r[0] <= end_time_ms]
                if filtered_rows:
                    storage.write_global_long_short_account(symbol, PERIOD, filtered_rows)
                    symbol_rows += len(filtered_rows)
                    total_written += len(filtered_rows)

                oldest_ts = min(r[0] for r in rows)
                if oldest_ts <= start_time_ms:
                    break
                current_end_time = oldest_ts - 1
                time.sleep(DELAY_SEC)

            expected = int(MS_PER_30D / (5 * 60 * 1000))
            coverage = (symbol_rows / expected * 100) if expected > 0 else 0
            print(f"  {i + 1}/{len(symbols)} {symbol}: {symbol_rows} rows (~{coverage:.1f}%)", flush=True)
        except Exception as e:
            print(f"  {i + 1}/{len(symbols)} {symbol}: FAILED {e}", flush=True)
            failed.append((symbol, str(e)))
        time.sleep(DELAY_SEC)

    elapsed = time.perf_counter() - run_start
    print(f"Done: {total_written} rows in {elapsed / 60:.1f} min.")
    if failed:
        print(f"Failed ({len(failed)}):", [s for s, _ in failed])


if __name__ == "__main__":
    main()
