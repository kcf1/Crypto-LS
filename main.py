"""Main bot entrypoint; config, data, execution, and booking wired."""

import logging

from config import settings, secrets, setup_logging
from data import Collector, Storage
from execution import BinanceClient, OrderManager
from booking import Ledger

logger = logging.getLogger(__name__)


def main() -> None:
    """Entrypoint: load config and run (extensible for data/execution/booking)."""
    setup_logging()
    # Config: single source of truth for all modules
    _ = settings
    _ = secrets
    # Data: collector (raw ingest), storage (raw OHLCV)
    storage = Storage(db_path=settings.db_path)
    collector = Collector(use_testnet=settings.use_testnet)
    # Execution: Binance client, order manager
    binance_client = BinanceClient()
    order_manager = OrderManager(binance_client=binance_client)
    # Booking: ledger for orders/trades/positions
    ledger = Ledger(db_path=settings.db_path)
    _ = (storage, collector, order_manager, ledger)
    logger.info(
        "Config loaded: env=%s, default_symbol=%s",
        settings.env,
        settings.default_symbol,
    )


if __name__ == "__main__":
    main()
