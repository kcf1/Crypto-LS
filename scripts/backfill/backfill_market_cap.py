"""
Backfill Market Cap: current and historical data for all symbols in settings.symbols.

Run from project root: python scripts/backfill/backfill_market_cap.py [--days N] [--limit N]
  --days N   Backfill last N days of history (default: 30). Use 7 for a quick run.
  --limit N  Limit to first N symbols (default: all). Use 20 for a quick run.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from tqdm import tqdm

# Run from project root
if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings, setup_logging
from data.coingecko_collector import CoinGeckoCollector, midnight_utc_today_ms
from data import Storage

logger = logging.getLogger(__name__)

# Backfill last 30 days by default
DAYS_BACK_DEFAULT = 30

DELAY_SEC = 1.0  # 1 second delay between API calls (respects free tier rate limits)
MAX_429_RETRIES = 5


def fetch_market_cap_with_retry(
    collector: CoinGeckoCollector,
    symbols: list[str],
) -> list:
    """Call collector with retry logic."""
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


def fetch_historical_with_retry(
    collector: CoinGeckoCollector,
    coin_id: str,
    date: str,
) -> dict | None:
    """Call collector.fetch_historical_market_cap with retry logic."""
    for attempt in range(MAX_429_RETRIES):
        try:
            result = collector.fetch_historical_market_cap(coin_id, date)
            return result
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < MAX_429_RETRIES - 1:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning(
                    "429 rate limit for %s on %s, sleeping %s s (attempt %s/%s)",
                    coin_id,
                    date,
                    retry_after,
                    attempt + 1,
                    MAX_429_RETRIES,
                )
                time.sleep(retry_after)
                continue
            raise
    return None


def get_coin_id_mapping(collector: CoinGeckoCollector, symbols: list[str]) -> dict[str, str]:
    """
    Build mapping from Binance symbol to CoinGecko coin ID.
    
    Returns dict: {binance_symbol: coin_id}
    """
    logger.info("Fetching coin list from CoinGecko to build symbol mapping...")
    coins_list = collector.fetch_coins_list()
    
    # Create mapping: CoinGecko symbol -> coin ID
    symbol_to_id = {}
    for coin in coins_list:
        cg_symbol = coin.get("symbol", "").lower()
        coin_id = coin.get("id", "")
        if cg_symbol and coin_id:
            symbol_to_id[cg_symbol] = coin_id
    
    # Map Binance symbols to CoinGecko IDs
    binance_to_id = {}
    for binance_symbol in symbols:
        cg_symbol = collector._binance_to_coingecko_symbol(binance_symbol)
        if cg_symbol in symbol_to_id:
            binance_to_id[binance_symbol] = symbol_to_id[cg_symbol]
        else:
            logger.warning("%s: CoinGecko symbol '%s' not found in coin list", binance_symbol, cg_symbol)
    
    logger.info("Built mapping for %s/%s symbols", len(binance_to_id), len(symbols))
    return binance_to_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill CoinGecko market cap data.")
    parser.add_argument("--days", type=int, default=DAYS_BACK_DEFAULT, help="Backfill last N days (default: 30)")
    parser.add_argument("--limit", type=int, default=None, help="Limit to first N symbols (default: all)")
    args = parser.parse_args()
    
    days_back = args.days
    symbols = settings.symbols
    if args.limit is not None:
        symbols = symbols[: args.limit]
    
    setup_logging()
    collector = CoinGeckoCollector(delay_sec=DELAY_SEC)
    storage = Storage()
    
    logger.info("Starting Market Cap backfill: %s symbols, target: %s days", len(symbols), days_back)
    
    # Step 1: Fetch current market cap for all symbols (use midnight UTC today = one row per day, no duplicates)
    logger.info("Step 1: Fetching current market cap data...")
    current_timestamp = midnight_utc_today_ms()
    
    # Batch symbols (max 50 per CoinGecko API request)
    batch_size = 50
    total_current_written = 0
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size
        
        logger.info("Processing current data batch %s/%s: %s symbols", batch_num, total_batches, len(batch))
        
        try:
            results = fetch_market_cap_with_retry(collector, batch)
            
            if not results:
                logger.warning("Batch %s: No data returned", batch_num)
                continue
            
            # Write to storage
            rows_by_symbol = {}
            for binance_symbol, market_data in results:
                if binance_symbol not in rows_by_symbol:
                    rows_by_symbol[binance_symbol] = []
                
                row_tuple = collector.market_data_to_tuple(market_data, current_timestamp)
                rows_by_symbol[binance_symbol].append(row_tuple)
            
            for symbol, rows in rows_by_symbol.items():
                try:
                    storage.write_market_cap(symbol, rows)
                    total_current_written += len(rows)
                    logger.debug("%s: wrote %s current market cap record(s)", symbol, len(rows))
                except Exception as e:
                    logger.warning("%s: failed to write current market cap: %s", symbol, e)
            
            if i + batch_size < len(symbols):
                time.sleep(DELAY_SEC)
                
        except Exception as e:
            logger.warning("Current data batch %s failed: %s", batch_num, e, exc_info=True)
    
    logger.info("Current data: %s records written", total_current_written)
    
    # Step 2: Fetch historical data (last days_back days)
    logger.info("Step 2: Fetching historical market cap data (last %s days)...", days_back)
    
    # Build symbol to coin ID mapping
    symbol_to_coin_id = get_coin_id_mapping(collector, symbols)
    
    # Generate list of dates to fetch
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days_back)
    
    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=1)
    
    logger.info("Fetching historical data for %s dates (from %s to %s)", len(dates), start_date, end_date)
    
    total_historical_written = 0
    failed_historical = []
    
    # Process each symbol
    for symbol in tqdm(symbols, desc="Symbols", unit="symbol"):
        if symbol not in symbol_to_coin_id:
            logger.warning("%s: Skipping historical data (no CoinGecko ID mapping)", symbol)
            continue
        
        coin_id = symbol_to_coin_id[symbol]
        
        # Process each date
        for date in dates:
            date_str = date.strftime("%d-%m-%Y")
            
            try:
                historical_data = fetch_historical_with_retry(collector, coin_id, date_str)
                
                if historical_data is None:
                    logger.debug("%s: No historical data for %s", symbol, date_str)
                    continue
                
                # Convert date to timestamp (midnight UTC)
                date_dt = datetime.combine(date, datetime.min.time(), tzinfo=timezone.utc)
                timestamp = int(date_dt.timestamp() * 1000)
                
                # Convert to tuple format
                row_tuple = collector.market_data_to_tuple(historical_data, timestamp)
                
                # Write to storage
                storage.write_market_cap(symbol, [row_tuple])
                total_historical_written += 1
                
                # Respect rate limits
                time.sleep(DELAY_SEC)
                
            except Exception as e:
                logger.warning("%s: Failed to fetch historical data for %s: %s", symbol, date_str, e)
                failed_historical.append((symbol, date_str, str(e)))
    
    logger.info("Historical data: %s records written", total_historical_written)
    
    total_written = total_current_written + total_historical_written
    logger.info(
        "COMPLETE: %s total records written (%s current + %s historical)",
        total_written,
        total_current_written,
        total_historical_written,
    )
    
    if failed_historical:
        logger.warning("Failed historical fetches: %s", len(failed_historical))
        for symbol, date_str, error in failed_historical[:10]:  # Show first 10
            logger.warning("  %s %s: %s", symbol, date_str, error)


if __name__ == "__main__":
    main()
