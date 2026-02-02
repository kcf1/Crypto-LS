"""
Binance Liquidations incremental update task.

Fetches new liquidation orders after the last stored record. Requires API key authentication.
Uses Collector + Storage + settings (delay, 429 retry). Registered in data.updates;
the general entry point (run_data_updater.py) invokes run() at fixed interval.
"""

import logging
import time
from typing import Dict, List, Optional

import requests

from config import settings, secrets
from data import Collector, Storage

logger = logging.getLogger(__name__)

DELAY_SEC = 0.1
MAX_429_RETRIES = 5
LIMIT = 100  # Max 100 for this endpoint


def _fetch_force_orders_with_retry(
    collector: Collector,
    symbol: str,
    *,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int,
) -> List[Dict]:
    """Call collector.fetch_force_orders; on 429, sleep Retry-After and retry."""
    for attempt in range(MAX_429_RETRIES):
        try:
            return collector.fetch_force_orders(
                symbol=symbol,
                auto_close_type="LIQUIDATION",  # Only liquidations, not ADL
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
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
    """One-shot Binance Liquidations incremental update."""
    # Check if API key is available
    if not secrets.binance_api_key or not secrets.binance_api_secret:
        logger.debug("Skip liquidations: API key not configured")
        return
    
    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()

    for symbol in settings.symbols:
        latest = storage.get_latest_liquidation_time(symbol)
        start_time_ms = latest + 1 if latest is not None else None
        
        try:
            rows = _fetch_force_orders_with_retry(
                collector,
                symbol,
                start_time=start_time_ms,
                limit=LIMIT,
            )
            if not rows:
                continue
            
            storage.write_liquidations(symbol, rows)
            logger.info("%s: wrote %s liquidation records", symbol, len(rows))
        except ValueError as e:
            # API key not configured
            logger.debug("Skip liquidations: %s", e)
            return
        except Exception as e:
            logger.warning("%s liquidations incremental update failed: %s", symbol, e)
        time.sleep(DELAY_SEC)
