"""Reset all booking records (orders, trades, positions, balances, adjustments).

Use this for a clean slate before re-testing the booking flow. Optionally resets
the books table so you can recreate books via API.

Usage:
    # Reset all booking data (prompt for confirmation)
    python scripts/utils/reset_booking_records.py

    # Skip confirmation
    python scripts/utils/reset_booking_records.py --yes

    # Also delete all books (you will need to recreate e.g. default, unallocated via API)
    python scripts/utils/reset_booking_records.py --include-books --yes
"""

import argparse
import logging
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from booking.ledger import Ledger
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def reset_booking_records(ledger: Ledger, include_books: bool = False) -> dict:
    """Delete all rows from booking tables. Returns dict of table -> deleted count.

    Order: trades (FK to orders), orders, positions, balances, adjustments; then books if requested.
    """
    tables_and_order = [
        "trades",
        "orders",
        "positions",
        "balances",
        "adjustments",
    ]
    if include_books:
        tables_and_order.append("books")

    counts = {}
    with ledger._engine.connect() as conn:
        for table in tables_and_order:
            result = conn.execute(text(f"DELETE FROM {table}"))
            counts[table] = result.rowcount
            logger.info("Deleted %s rows from %s", result.rowcount, table)
        conn.commit()

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset all booking records (orders, trades, positions, balances, adjustments)."
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "--include-books",
        action="store_true",
        help="Also delete all rows from the books table (recreate via POST /books if needed)",
    )
    args = parser.parse_args()

    ledger = Ledger()

    if not args.yes:
        msg = "This will DELETE all orders, trades, positions, balances, and adjustments."
        if args.include_books:
            msg += " It will also DELETE all books."
        msg += " Continue? [y/N] "
        try:
            answer = input(msg).strip().lower()
        except EOFError:
            answer = "n"
        if answer != "y" and answer != "yes":
            logger.info("Aborted")
            return 0

    counts = reset_booking_records(ledger, include_books=args.include_books)
    total = sum(counts.values())
    logger.info("Reset complete. Total rows deleted: %s", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
