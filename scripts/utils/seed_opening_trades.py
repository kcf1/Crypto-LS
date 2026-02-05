"""Seed the ledger with initialization trades to match current exchange positions.

Use once when the ledger is empty (or after reset) and the exchange already has
positions/balances. Creates one synthetic "opening" trade per symbol so that
ledger positions and balances align with the exchange (Rec 4 / Rec 6 can then pass).

Fetches account data from Binance testnet; records into ledger with venue=settings.venue
(binance_spot) so all booking stays under spot venue.

Usage:
    # Dry run (show what would be booked)
    python scripts/utils/seed_opening_trades.py --dry-run

    # Seed from testnet into ledger (venue=binance_spot)
    python scripts/utils/seed_opening_trades.py --yes

    # Fetch from spot instead
    python scripts/utils/seed_opening_trades.py --spot --yes
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from booking.ledger import Ledger, _parse_symbol
from config import settings
from execution.binance.client import BinanceClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_ticker_price(client: BinanceClient, symbol: str) -> Optional[float]:
    """Get last price for symbol from exchange."""
    try:
        ticker = client.client.get_symbol_ticker(symbol=symbol)
        if ticker and "lastPrice" in ticker:
            return float(ticker["lastPrice"])
    except Exception as e:
        logger.warning("Could not get ticker for %s: %s", symbol, e)
    return None


def seed_opening_trades(
    ledger: Ledger,
    binance_client: BinanceClient,
    venue: str,
    book_id: str = "default",
    symbols: Optional[List[str]] = None,
    min_quantity: float = 1e-9,
    dry_run: bool = False,
) -> int:
    """Create one synthetic BUY trade per symbol so ledger position matches exchange base-asset balance.

    Returns number of trades recorded (or would be recorded if dry_run).
    """
    symbols = symbols or [settings.default_symbol]
    account = binance_client.get_account()
    balances = {b["asset"]: float(b.get("free", 0) or 0) for b in account.get("balances", [])}
    ts = int(time.time() * 1000)
    recorded = 0

    for symbol in symbols:
        try:
            base, _ = _parse_symbol(symbol)
        except ValueError:
            logger.warning("Skipping symbol %s (could not parse base asset)", symbol)
            continue

        free = balances.get(base, 0.0)
        if free < min_quantity:
            continue

        price = get_ticker_price(binance_client, symbol)
        if price is None or price <= 0:
            logger.warning("Skipping %s: no valid price", symbol)
            continue

        exchange_trade_id = f"INIT_{ts}_{symbol}"
        if dry_run:
            logger.info(
                "[DRY RUN] Would record opening trade: %s BUY %s @ %s (book_id=%s, venue=%s)",
                symbol,
                free,
                price,
                book_id,
                venue,
            )
            recorded += 1
            continue

        try:
            trade_id = ledger.record_trade(
                venue=venue,
                book_id=book_id,
                symbol=symbol,
                side="BUY",
                quantity=free,
                price=price,
                traded_at=ts,
                exchange_trade_id=exchange_trade_id,
                order_id=None,
                commission=0.0,
                commission_asset=None,
                notes="Opening position from exchange (seed_opening_trades)",
            )
            logger.info("Recorded opening trade %s: %s BUY %s @ %s (trade_id=%s)", symbol, symbol, free, price, trade_id)
            recorded += 1
        except Exception as e:
            logger.error("Failed to record opening trade for %s: %s", symbol, e)

    return recorded


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed ledger with initialization trades from current exchange positions."
    )
    parser.add_argument(
        "--spot",
        action="store_true",
        help="Fetch from Binance spot API (default: fetch from testnet)",
    )
    parser.add_argument(
        "--book-id",
        default="default",
        help="Book to record opening trades into (default: default)",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Symbols to seed (default: use settings.default_symbol only, e.g. BTCUSDT)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only log what would be recorded",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation",
    )
    args = parser.parse_args()

    # Always record with spot venue; fetch from testnet unless --spot
    venue = settings.venue
    use_testnet = not args.spot
    binance_client = BinanceClient(use_testnet=use_testnet)
    ledger = Ledger()

    if not args.yes and not args.dry_run:
        try:
            source = "spot" if args.spot else "testnet"
            answer = input(
                f"Fetch from {source}, record into book_id={args.book_id} (venue={venue})? [y/N] "
            ).strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes"):
            logger.info("Aborted")
            return 0

    n = seed_opening_trades(
        ledger=ledger,
        binance_client=binance_client,
        venue=venue,
        book_id=args.book_id,
        symbols=args.symbols,
        dry_run=args.dry_run,
    )
    logger.info("Done. %s opening trade(s) %s", n, "would be recorded" if args.dry_run else "recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
