"""Fix trades with empty side (backfill from linked order or Binance).

Per SOP: ensure trade data is consistent. Trades with empty side are backfilled from:
1. Linked order (orders.side) when trade.order_id is set
2. Binance get_my_trades when no order (uses testnet)

Usage:
    python scripts/integrity/fix_empty_trade_side.py [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from booking.ledger import Ledger
from execution.binance.client import BinanceClient
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_trades_with_empty_side(ledger: Ledger):
    """Return list of trades where side is NULL or empty string."""
    with ledger._engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, book_id, symbol, exchange_trade_id, order_id, traded_at
                FROM trades
                WHERE (side IS NULL OR side = '')
                ORDER BY traded_at DESC
            """)
        )
        rows = result.fetchall()
    return [
        {
            "id": r[0],
            "book_id": r[1],
            "symbol": r[2],
            "exchange_trade_id": r[3],
            "order_id": r[4],
            "traded_at": r[5],
        }
        for r in rows
    ]


def get_order_side(ledger: Ledger, order_id: int) -> Optional[str]:
    """Return order side (BUY/SELL) for the given order id."""
    with ledger._engine.connect() as conn:
        row = conn.execute(
            text("SELECT side FROM orders WHERE id = :order_id"),
            {"order_id": order_id},
        ).fetchone()
    return row[0].strip().upper() if row and row[0] and str(row[0]).strip() else None


def get_side_from_binance(binance_client: BinanceClient, symbol: str, exchange_trade_id: str, traded_at: int) -> Optional[str]:
    """Fetch trade from Binance get_my_trades and return side (BUY/SELL)."""
    try:
        # Request a window around traded_at (ms)
        start = max(0, traded_at - 60 * 60 * 1000)
        end = traded_at + 60 * 60 * 1000
        trades = binance_client.get_my_trades(symbol=symbol, startTime=start, endTime=end, limit=100)
        for t in trades:
            if str(t.get("id", "")) == str(exchange_trade_id):
                side = (t.get("side") or "").strip().upper()
                if side in ("BUY", "SELL"):
                    return side
                is_buyer = t.get("isBuyer")
                if is_buyer is not None:
                    return "BUY" if is_buyer else "SELL"
                return None
    except Exception as e:
        logger.warning(f"Binance get_my_trades for {symbol} failed: {e}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix trades with empty side")
    parser.add_argument("--dry-run", action="store_true", help="Only report what would be updated")
    args = parser.parse_args()

    ledger = Ledger()
    empty = get_trades_with_empty_side(ledger)
    if not empty:
        logger.info("No trades with empty side found")
        return 0

    logger.info(f"Found {len(empty)} trade(s) with empty side")
    binance_client = BinanceClient(use_testnet=True)
    updated = 0
    skipped = 0

    for trade in empty:
        tid, order_id, symbol, exchange_trade_id, traded_at = (
            trade["id"],
            trade["order_id"],
            trade["symbol"],
            trade["exchange_trade_id"],
            trade["traded_at"],
        )
        side = None
        source = None
        if order_id:
            side = get_order_side(ledger, order_id)
            source = "order"
        if not side and exchange_trade_id and symbol:
            side = get_side_from_binance(binance_client, symbol, exchange_trade_id, traded_at or 0)
            source = "binance"
        if side:
            if args.dry_run:
                logger.info(f"[DRY RUN] Would set trade id={tid} side={side} (from {source})")
            else:
                ledger.update_trade_side(tid, side)
                logger.info(f"Updated trade id={tid} side={side} (from {source})")
            updated += 1
        else:
            logger.warning(f"Could not determine side for trade id={tid} (symbol={symbol}, exchange_trade_id={exchange_trade_id})")
            skipped += 1

    logger.info(f"Done: updated={updated}, skipped={skipped}")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
