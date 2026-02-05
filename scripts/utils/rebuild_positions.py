"""Rebuild positions table from trades table."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from booking.ledger import Ledger
from config import settings
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def rebuild_positions(ledger: Ledger, book_id: Optional[str] = None) -> None:
    """Rebuild positions table from trades.
    
    Args:
        ledger: Ledger instance
        book_id: Optional book_id to rebuild specific book (rebuilds all if None)
    """
    logger.info(f"Starting positions rebuild{' for book_id=' + book_id if book_id else ''}")
    
    with ledger._engine.connect() as conn:
        # Delete existing positions (filtered by book_id if provided)
        if book_id:
            conn.execute(
                text("DELETE FROM positions WHERE book_id = :book_id"),
                {"book_id": book_id},
            )
            logger.info(f"Deleted existing positions for book_id={book_id}")
        else:
            conn.execute(text("DELETE FROM positions"))
            logger.info("Deleted all existing positions")
        
        # Rebuild positions from trades
        # GROUP BY book_id, symbol
        # Compute quantity = SUM(quantity * CASE side WHEN 'BUY' THEN 1 ELSE -1 END)
        # Compute avg_price = SUM(price * quantity) / SUM(quantity) (VWAP)
        if book_id:
            result = conn.execute(
                text("""
                    SELECT
                        book_id,
                        symbol,
                        SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) as quantity,
                        CASE 
                            WHEN SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) != 0
                            THEN SUM(price * quantity) / SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END)
                            ELSE 0
                        END as avg_price,
                        MAX(traded_at) as updated_at
                    FROM trades
                    WHERE book_id = :book_id AND record_status = 'VALID'
                    GROUP BY book_id, symbol
                    HAVING ABS(SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END)) > 1e-12
                """),
                {"book_id": book_id},
            )
        else:
            result = conn.execute(
                text("""
                    SELECT
                        book_id,
                        symbol,
                        SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) as quantity,
                        CASE 
                            WHEN SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) != 0
                            THEN SUM(price * quantity) / SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END)
                            ELSE 0
                        END as avg_price,
                        MAX(traded_at) as updated_at
                    FROM trades
                    WHERE record_status = 'VALID'
                    GROUP BY book_id, symbol
                    HAVING ABS(SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END)) > 1e-12
                """),
            )
        
        rows = result.fetchall()
        positions_inserted = 0
        
        for row in rows:
            book_id_val, symbol, quantity, avg_price, updated_at = row
            if abs(float(quantity)) < 1e-12:
                continue  # Skip zero positions
            
            conn.execute(
                text("""
                    INSERT INTO positions (book_id, symbol, quantity, avg_price, updated_at)
                    VALUES (:book_id, :symbol, :quantity, :avg_price, :updated_at)
                """),
                {
                    "book_id": book_id_val,
                    "symbol": symbol,
                    "quantity": float(quantity),
                    "avg_price": float(avg_price),
                    "updated_at": updated_at,
                },
            )
            positions_inserted += 1
        
        conn.commit()
        logger.info(f"Rebuilt {positions_inserted} positions")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Rebuild positions table from trades")
    parser.add_argument(
        "--book-id",
        type=str,
        default=None,
        help="Book ID to rebuild (rebuilds all if not specified)",
    )
    args = parser.parse_args()
    
    ledger = Ledger()
    rebuild_positions(ledger, book_id=args.book_id)
    logger.info("Positions rebuild completed")


if __name__ == "__main__":
    main()
