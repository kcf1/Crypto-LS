"""Fill sync service: periodically syncs fills from Binance and books them."""

import time
import logging
from typing import Dict, Optional

from booking.ledger import Ledger
from config import settings
from execution.orchestrator import BookingOrchestrator

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _sleep_until_next_aligned_minute(interval_sec: int) -> None:
    """Sleep until the next aligned minute mark (e.g., :00, :05, :10 for 5-minute intervals)."""
    current_time = time.time()
    current_second = int(current_time) % (interval_sec)
    sleep_time = interval_sec - current_second
    if sleep_time > 0:
        logger.info(f"Sleeping {sleep_time} seconds until next aligned {interval_sec}s mark")
        time.sleep(sleep_time)


def main() -> None:
    """Main fill sync loop."""
    logger.info("Starting fill sync service")
    
    # Initialize components
    orchestrator = BookingOrchestrator()
    ledger = Ledger()
    
    # Configuration
    sync_interval_sec = 60  # Sync every 1 minute (configurable)
    book_id = "default"  # Default book ID
    
    # Track last sync time per symbol (in-memory, resets on restart)
    last_sync_times: Dict[str, int] = {}
    
    # Sleep until aligned minute mark
    _sleep_until_next_aligned_minute(sync_interval_sec)
    
    logger.info(f"Fill sync service started. Interval: {sync_interval_sec}s, Book ID: {book_id}")
    
    while True:
        try:
            cycle_start = time.time()
            logger.info("Starting fill sync cycle")
            
            # Get active symbols (symbols with recent trades or open orders)
            # For now, sync all symbols in settings.symbols
            # In production, you might want to only sync symbols with recent activity
            symbols_to_sync = settings.symbols
            
            total_trades_synced = 0
            errors = 0
            
            for symbol in symbols_to_sync:
                try:
                    # Get last sync time for this symbol
                    since = last_sync_times.get(symbol)
                    
                    # Sync fills for symbol
                    trade_ids = orchestrator.sync_fills_for_symbol(
                        symbol=symbol,
                        book_id=book_id,
                        since=since,
                        limit=100,  # Fetch up to 100 trades per sync
                    )
                    
                    if trade_ids:
                        logger.info(f"Synced {len(trade_ids)} fills for {symbol}")
                        total_trades_synced += len(trade_ids)
                        # Update last sync time to latest trade time
                        # Get latest trade time from ledger
                        trades = ledger.get_trades(symbol=symbol, book_id=book_id, limit=1)
                        if trades:
                            last_sync_times[symbol] = trades[0]["traded_at"]
                    else:
                        # Update last sync time to current time if no new trades
                        if since is None:
                            last_sync_times[symbol] = int(time.time() * 1000)
                    
                    # Small delay to avoid rate limits
                    time.sleep(0.1)
                    
                except Exception as e:
                    errors += 1
                    logger.error(f"Error syncing fills for {symbol}: {e}", exc_info=True)
                    continue
            
            cycle_duration = time.time() - cycle_start
            logger.info(
                f"Fill sync cycle completed. "
                f"Trades synced: {total_trades_synced}, Errors: {errors}, Duration: {cycle_duration:.2f}s"
            )
            
            # Sleep until next aligned interval
            _sleep_until_next_aligned_minute(sync_interval_sec)
            
        except KeyboardInterrupt:
            logger.info("Fill sync service stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error in fill sync service: {e}", exc_info=True)
            # Sleep before retrying
            time.sleep(60)


if __name__ == "__main__":
    main()
