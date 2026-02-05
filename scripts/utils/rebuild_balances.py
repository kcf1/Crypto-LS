"""Rebuild balances table from trades table."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from booking.ledger import Ledger, _parse_symbol, _is_postgres
from config import settings
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def rebuild_balances(ledger: Ledger, book_id: Optional[str] = None) -> None:
    """Rebuild balances table from trades.
    
    Args:
        ledger: Ledger instance
        book_id: Optional book_id to rebuild specific book (rebuilds all if None)
    """
    logger.info(f"Starting balances rebuild{' for book_id=' + book_id if book_id else ''}")
    
    is_postgres = _is_postgres(str(ledger._engine.url))
    
    with ledger._engine.connect() as conn:
        # Delete existing balances (filtered by book_id if provided)
        if book_id:
            conn.execute(
                text("DELETE FROM balances WHERE book_id = :book_id"),
                {"book_id": book_id},
            )
            logger.info(f"Deleted existing balances for book_id={book_id}")
        else:
            conn.execute(text("DELETE FROM balances"))
            logger.info("Deleted all existing balances")
        
        # Get all trades (filtered by book_id if provided)
        if book_id:
            trades_result = conn.execute(
                text("""
                    SELECT venue, book_id, symbol, side, quantity, price, commission, traded_at
                    FROM trades
                    WHERE book_id = :book_id AND record_status = 'VALID'
                    ORDER BY traded_at ASC
                """),
                {"book_id": book_id},
            )
        else:
            trades_result = conn.execute(
                text("""
                    SELECT venue, book_id, symbol, side, quantity, price, commission, traded_at
                    FROM trades
                    WHERE record_status = 'VALID'
                    ORDER BY traded_at ASC
                """),
            )
        
        trades = trades_result.fetchall()
        logger.info(f"Processing {len(trades)} trades")
        
        # Track balances per (venue, book_id, asset)
        balances: dict = {}  # Key: (venue, book_id, asset), Value: {"free": float, "updated_at": int}
        
        for trade in trades:
            venue, book_id_val, symbol, side, quantity, price, commission, traded_at = trade
            quantity = float(quantity)
            price = float(price)
            commission = float(commission)
            
            try:
                base_asset, quote_asset = _parse_symbol(symbol)
            except ValueError:
                logger.warning(f"Could not parse symbol {symbol}, skipping balance update")
                continue
            
            # Determine commission asset (default to quote)
            # Note: We don't have commission_asset stored in trades table,
            # so we default to quote asset
            commission_asset = quote_asset
            
            # Update base asset balance
            key_base = (venue, book_id_val, base_asset)
            if key_base not in balances:
                balances[key_base] = {"free": 0.0, "locked": 0.0, "updated_at": traded_at}
            
            if side.upper() == "BUY":
                balances[key_base]["free"] += quantity
            else:
                balances[key_base]["free"] -= quantity
            balances[key_base]["updated_at"] = max(balances[key_base]["updated_at"], traded_at)
            
            # Update quote asset balance
            key_quote = (venue, book_id_val, quote_asset)
            if key_quote not in balances:
                balances[key_quote] = {"free": 0.0, "locked": 0.0, "updated_at": traded_at}
            
            if side.upper() == "BUY":
                balances[key_quote]["free"] -= quantity * price  # Spend quote
            else:
                balances[key_quote]["free"] += quantity * price  # Receive quote
            balances[key_quote]["updated_at"] = max(balances[key_quote]["updated_at"], traded_at)
            
            # Update commission asset balance
            if commission > 0:
                key_comm = (venue, book_id_val, commission_asset)
                if key_comm not in balances:
                    balances[key_comm] = {"free": 0.0, "locked": 0.0, "updated_at": traded_at}
                
                balances[key_comm]["free"] -= commission
                balances[key_comm]["updated_at"] = max(balances[key_comm]["updated_at"], traded_at)
        
        # Insert/update balances
        balances_inserted = 0
        for (venue, book_id_val, asset), balance_data in balances.items():
            # Skip zero balances (optional - you might want to keep them)
            if abs(balance_data["free"]) < 1e-12 and abs(balance_data["locked"]) < 1e-12:
                continue
            
            if is_postgres:
                conn.execute(
                    text("""
                        INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                        VALUES (:venue, :book_id, :asset, :free, :locked, :updated_at)
                        ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                            free = :free,
                            locked = :locked,
                            updated_at = :updated_at
                    """),
                    {
                        "venue": venue,
                        "book_id": book_id_val,
                        "asset": asset,
                        "free": balance_data["free"],
                        "locked": balance_data["locked"],
                        "updated_at": balance_data["updated_at"],
                    },
                )
            else:
                # SQLite
                conn.execute(
                    text("""
                        INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                        VALUES (:venue, :book_id, :asset, :free, :locked, :updated_at)
                        ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                            free = :free,
                            locked = :locked,
                            updated_at = :updated_at
                    """),
                    {
                        "venue": venue,
                        "book_id": book_id_val,
                        "asset": asset,
                        "free": balance_data["free"],
                        "locked": balance_data["locked"],
                        "updated_at": balance_data["updated_at"],
                    },
                )
            balances_inserted += 1
        
        conn.commit()
        logger.info(f"Rebuilt {balances_inserted} balance records")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Rebuild balances table from trades")
    parser.add_argument(
        "--book-id",
        type=str,
        default=None,
        help="Book ID to rebuild (rebuilds all if not specified)",
    )
    args = parser.parse_args()
    
    ledger = Ledger()
    rebuild_balances(ledger, book_id=args.book_id)
    logger.info("Balances rebuild completed")


if __name__ == "__main__":
    main()
