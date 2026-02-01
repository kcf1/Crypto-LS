"""Main bot entrypoint; config, data, execution, and booking wired."""

from config import settings, secrets
from data import Collector, Storage
from execution import BinanceClient, OrderManager
from booking import Ledger


def main() -> None:
    """Entrypoint: load config and run (extensible for data/execution/booking)."""
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
    print(f"Config loaded: env={settings.env}, default_symbol={settings.default_symbol}")


if __name__ == "__main__":
    main()
