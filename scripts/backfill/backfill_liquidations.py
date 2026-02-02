"""
Backfill Liquidations: maximum available (7 days for USDT-M), for all symbols in settings.symbols.
Uses data.Collector (REST) and data.Storage; writes to DATABASE_URL (Postgres) when set, else SQLite.
Paginates by 100 records per request (Binance limit).
Requires API key authentication.

Note: Binance only retains 7 days of historical liquidation data for USDT-Margined futures.

Run from project root: python scripts/backfill/backfill_liquidations.py
"""

import logging
import sys
import time
from pathlib import Path

import requests

# Run from project root so config and data are importable
if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings, setup_logging, secrets
from data import Collector, Storage

logger = logging.getLogger(__name__)

# 7 days in milliseconds (USDT-M retention limit)
MS_PER_7D = int(7 * 24 * 3600 * 1000)

DELAY_SEC = 0.1
MAX_429_RETRIES = 5
LIMIT = 100  # Binance limit for this endpoint


def fetch_force_orders_with_retry(
    collector: Collector,
    symbol: str,
    *,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int,
) -> list:
    """Call collector.fetch_force_orders; on 429, sleep Retry-After and retry up to MAX_429_RETRIES."""
    for attempt in range(MAX_429_RETRIES):
        try:
            return collector.fetch_force_orders(
                symbol=symbol,
                auto_close_type="LIQUIDATION",  # Only liquidations
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
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
    
    # Check if API key is available
    if not secrets.binance_api_key or not secrets.binance_api_secret:
        logger.error("API key and secret required for liquidations backfill")
        print("ERROR: API key and secret required. Set BINANCE_API_KEY and BINANCE_API_SECRET in .env")
        return
    
    symbols = settings.symbols
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - MS_PER_7D
    run_start = time.perf_counter()

    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()

    logger.info("Starting liquidations backfill: %s symbols, target: 7 days", len(symbols))
    db_target = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    logger.info("Target: %s", db_target)
    logger.info("Note: Binance only retains 7 days of historical liquidation data")

    total_written = 0
    failed = []

    for i, symbol in enumerate(symbols):
        print(f"  {i + 1}/{len(symbols)} {symbol} ...", flush=True)
        logger.info("Symbol %s/%s: %s", i + 1, len(symbols), symbol)
        cursor_ms = start_time_ms
        symbol_rows = 0
        
        try:
            while cursor_ms < end_time_ms:
                rows = fetch_force_orders_with_retry(
                    collector,
                    symbol,
                    start_time=cursor_ms,
                    end_time=end_time_ms,
                    limit=LIMIT,
                )
                if not rows:
                    break
                
                storage.write_liquidations(symbol, rows)
                symbol_rows += len(rows)
                total_written += len(rows)
                
                # Move cursor to last time + 1
                # Use 'time' field or 'updateTime' if available
                last_time = rows[-1].get("time") or rows[-1].get("updateTime", 0)
                cursor_ms = last_time + 1
                time.sleep(DELAY_SEC)
            
            print(f"  {i + 1}/{len(symbols)} {symbol}: {symbol_rows} rows", flush=True)
            logger.info("  %s/%s %s: %s rows", i + 1, len(symbols), symbol, symbol_rows)
        except ValueError as e:
            logger.error("API key error: %s", e)
            print(f"ERROR: {e}")
            return
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
