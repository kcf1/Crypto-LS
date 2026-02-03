"""
Test script: Backfill Market Cap for first 10 symbols only.
Quick test to verify market cap collection works before running full backfill.

Run from project root: python scripts/backfill/test_backfill_market_cap.py
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
from data.coingecko_collector import CoinGeckoCollector, midnight_utc_today_ms
from data import Storage

logger = logging.getLogger(__name__)

DELAY_SEC = 1.0  # 1 second delay between API calls
MAX_429_RETRIES = 5


def fetch_market_cap_with_retry(
    collector: CoinGeckoCollector,
    symbols: list[str],
) -> list:
    """Call collector with retry logic for 429 errors."""
    for attempt in range(MAX_429_RETRIES):
        try:
            results = collector.fetch_market_cap(symbols)
            return results
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < MAX_429_RETRIES - 1:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning(
                    "429 rate limit, sleeping %s s (attempt %s/%s)",
                    retry_after,
                    attempt + 1,
                    MAX_429_RETRIES,
                )
                time.sleep(retry_after)
                continue
            raise
    return []


def main() -> None:
    setup_logging()
    
    # Test with first 10 symbols only
    symbols = settings.symbols[:10]
    
    collector = CoinGeckoCollector(delay_sec=DELAY_SEC)
    storage = Storage()
    
    # Use midnight UTC today so one row per (symbol, day); no duplicates
    current_timestamp = midnight_utc_today_ms()
    run_start = time.perf_counter()
    
    logger.info("TEST: Market cap backfill for %s symbols", len(symbols))
    db_target = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    logger.info("Target: %s", db_target)
    
    total_written = 0
    failed = []
    
    # Batch symbols (max 50 per CoinGecko API request)
    batch_size = 50
    
    for i, symbol in enumerate(tqdm(symbols, desc="Symbols", unit="symbol")):
        try:
            # Fetch market cap data for this symbol
            results = fetch_market_cap_with_retry(collector, [symbol])
            
            if not results:
                logger.warning("%s: No data returned from CoinGecko", symbol)
                failed.append((symbol, "No data returned"))
                continue
            
            # Find result for this symbol
            symbol_data = None
            for binance_symbol, market_data in results:
                if binance_symbol == symbol:
                    symbol_data = market_data
                    break
            
            if symbol_data is None:
                logger.warning("%s: Symbol not found in CoinGecko response", symbol)
                failed.append((symbol, "Symbol not found"))
                continue
            
            # Convert to storage format
            row_tuple = collector.market_data_to_tuple(symbol_data, current_timestamp)
            
            # Write to storage
            storage.write_market_cap(symbol, [row_tuple])
            total_written += 1
            
            logger.info("%s: wrote 1 market cap record", symbol)
            
            # Respect rate limits
            if i < len(symbols) - 1:
                time.sleep(DELAY_SEC)
                
        except Exception as e:
            logger.warning("%s failed: %s", symbol, e, exc_info=True)
            failed.append((symbol, str(e)))
    
    elapsed_sec = time.perf_counter() - run_start
    logger.info(
        "TEST COMPLETE: %s total records written to %s in %.1f sec",
        total_written,
        db_target,
        elapsed_sec,
    )
    
    if failed:
        logger.warning("Failed symbols (%s): %s", len(failed), [s for s, _ in failed])
        print(f"FAILED: {len(failed)} symbols")
    else:
        print(f"SUCCESS: {total_written} records written in {elapsed_sec:.1f} sec.")


if __name__ == "__main__":
    main()
