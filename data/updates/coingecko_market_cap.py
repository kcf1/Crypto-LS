"""
CoinGecko Market Cap incremental update task.

Fetches current market cap data for all symbols and stores daily snapshots.
Uses CoinGeckoCollector + Storage + settings. Do not register in data.updates yet;
registration is done after all tests pass.
"""

import logging
import time
from typing import List

import requests

from config import settings
from data.coingecko_collector import CoinGeckoCollector, midnight_utc_today_ms
from data import Storage

logger = logging.getLogger(__name__)

DELAY_SEC = 1.0  # 1 second delay between API calls (respects free tier rate limits)
MAX_429_RETRIES = 5


def _fetch_market_cap_with_retry(
    collector: CoinGeckoCollector,
    symbols: List[str],
) -> List[tuple]:
    """Call collector.fetch_market_cap; on 429, sleep Retry-After and retry."""
    for attempt in range(MAX_429_RETRIES):
        try:
            results = collector.fetch_market_cap(symbols)
            return results
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
    """One-shot CoinGecko Market Cap incremental update (daily snapshot)."""
    collector = CoinGeckoCollector(delay_sec=DELAY_SEC)
    storage = Storage()
    
    # Use midnight UTC today so one row per (symbol, day); multiple runs same day upsert, no duplicates
    current_timestamp = midnight_utc_today_ms()
    
    # Batch symbols (max 50 per CoinGecko API request)
    batch_size = 50
    symbols = settings.symbols
    
    total_written = 0
    failed_symbols = []
    
    logger.info("Starting CoinGecko market cap update for %s symbols", len(symbols))
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size
        
        logger.info("Processing batch %s/%s: %s symbols", batch_num, total_batches, len(batch))
        
        try:
            # Fetch market cap data for this batch
            results = _fetch_market_cap_with_retry(collector, batch)
            
            if not results:
                logger.warning("Batch %s: No data returned", batch_num)
                continue
            
            # Convert to storage format and write
            rows_by_symbol = {}
            for binance_symbol, market_data in results:
                if binance_symbol not in rows_by_symbol:
                    rows_by_symbol[binance_symbol] = []
                
                # Convert market data dict to tuple
                row_tuple = collector.market_data_to_tuple(market_data, current_timestamp)
                rows_by_symbol[binance_symbol].append(row_tuple)
            
            # Write to storage
            for symbol, rows in rows_by_symbol.items():
                try:
                    storage.write_market_cap(symbol, rows)
                    total_written += len(rows)
                    logger.info("%s: wrote %s market cap record(s)", symbol, len(rows))
                except Exception as e:
                    logger.warning("%s: failed to write market cap: %s", symbol, e)
                    failed_symbols.append(symbol)
            
            # Respect rate limits
            if i + batch_size < len(symbols):
                time.sleep(DELAY_SEC)
                
        except Exception as e:
            logger.warning("Batch %s failed: %s", batch_num, e, exc_info=True)
            failed_symbols.extend(batch)
    
    logger.info(
        "CoinGecko market cap update complete: %s records written, %s symbols failed",
        total_written,
        len(failed_symbols),
    )
    
    if failed_symbols:
        logger.warning("Failed symbols: %s", failed_symbols)
