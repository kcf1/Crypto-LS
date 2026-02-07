"""Investigate trade status issues according to SOP.

This script investigates trades where:
- test_book trades should be VALID (correct)
- default book trades should be INVALID (not correct)

Usage:
    python scripts/integrity/investigate_trade_status.py --symbol BTCUSDT
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from booking.ledger import Ledger
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def investigate_trades(
    ledger: Ledger,
    symbol: Optional[str] = None,
    book_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Investigate trades and their record_status.
    
    Returns:
        Dictionary with investigation results
    """
    logger.info("Investigating trades...")
    logger.info(f"Symbol: {symbol or 'all'}")
    logger.info(f"Book ID: {book_id or 'all'}")
    
    # Get ALL trades (including INVALID) for investigation
    all_trades = ledger.get_trades(
        symbol=symbol,
        book_id=book_id,
        record_status=None,  # Get all statuses
    )
    
    # Also query directly to get all statuses (since get_trades defaults to VALID)
    from sqlalchemy import text
    with ledger._engine.connect() as conn:
        sql = "SELECT id, venue, book_id, exchange_trade_id, order_id, symbol, quantity, price, traded_at, record_status, notes FROM trades WHERE 1=1"
        params: dict = {}
        if symbol:
            sql += " AND symbol = :symbol"
            params["symbol"] = symbol
        if book_id:
            sql += " AND book_id = :book_id"
            params["book_id"] = book_id
        sql += " ORDER BY traded_at DESC"
        result = conn.execute(text(sql), params)
        rows = result.fetchall()
    
    trades = [
        {
            "id": r[0],
            "venue": r[1],
            "book_id": r[2],
            "exchange_trade_id": r[3],
            "order_id": r[4],
            "symbol": r[5],
            "quantity": float(r[6]),
            "price": float(r[7]),
            "traded_at": r[8],
            "record_status": r[9],
            "notes": r[10],
        }
        for r in rows
    ]
    
    # Group by book_id
    trades_by_book: Dict[str, List[Dict[str, Any]]] = {}
    for trade in trades:
        book = trade["book_id"]
        if book not in trades_by_book:
            trades_by_book[book] = []
        trades_by_book[book].append(trade)
    
    # Analyze each book
    analysis = {}
    for book, book_trades in trades_by_book.items():
        valid_count = sum(1 for t in book_trades if t["record_status"] == "VALID")
        invalid_count = sum(1 for t in book_trades if t["record_status"] == "INVALID")
        
        # Check for contradictions (notes say INVALID but status is VALID)
        contradictions = []
        for trade in book_trades:
            notes = trade.get("notes", "") or ""
            status = trade["record_status"]
            if "[INVALID]" in notes.upper() and status == "VALID":
                contradictions.append({
                    "id": trade["id"],
                    "exchange_trade_id": trade["exchange_trade_id"],
                    "record_status": status,
                    "notes": notes[:100] if notes else None,
                })
        
        analysis[book] = {
            "total": len(book_trades),
            "valid": valid_count,
            "invalid": invalid_count,
            "contradictions": contradictions,
            "trades": book_trades,
        }
    
    return {
        "symbol": symbol,
        "book_id": book_id,
        "total_trades": len(trades),
        "trades_by_book": analysis,
    }


def fix_trade_statuses(
    ledger: Ledger,
    symbol: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Fix trade statuses according to user requirements:
    - test_book trades should be VALID (correct)
    - default book trades should be INVALID (not correct)
    
    Args:
        ledger: Ledger instance
        symbol: Symbol to fix (e.g., BTCUSDT)
        dry_run: If True, only show what would be changed
    """
    logger.info("Fixing trade statuses...")
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Dry run: {dry_run}")
    
    # Get all trades for this symbol
    from sqlalchemy import text
    with ledger._engine.connect() as conn:
        sql = """
            SELECT id, venue, book_id, exchange_trade_id, order_id, symbol, 
                   quantity, price, traded_at, record_status, notes 
            FROM trades 
            WHERE symbol = :symbol
            ORDER BY traded_at DESC
        """
        result = conn.execute(text(sql), {"symbol": symbol})
        rows = result.fetchall()
    
    trades = [
        {
            "id": r[0],
            "venue": r[1],
            "book_id": r[2],
            "exchange_trade_id": r[3],
            "order_id": r[4],
            "symbol": r[5],
            "quantity": float(r[6]),
            "price": float(r[7]),
            "traded_at": r[8],
            "record_status": r[9],
            "notes": r[10],
        }
        for r in rows
    ]
    
    fixes_needed = []
    
    for trade in trades:
        book_id = trade["book_id"]
        current_status = trade["record_status"]
        expected_status = None
        reason = None
        
        # Determine expected status based on book_id
        if book_id == "test_book":
            expected_status = "VALID"
            reason = "test_book trades should be VALID (correct)"
        elif book_id == "default":
            expected_status = "INVALID"
            reason = "default book trades should be INVALID (not correct)"
        else:
            # Skip other books
            continue
        
        # Check if fix is needed
        if current_status != expected_status:
            fixes_needed.append({
                "trade_id": trade["id"],
                "exchange_trade_id": trade["exchange_trade_id"],
                "book_id": book_id,
                "current_status": current_status,
                "expected_status": expected_status,
                "reason": reason,
                "notes": trade.get("notes"),
            })
    
    if not fixes_needed:
        logger.info("No fixes needed - all trades have correct status")
        return {"fixed": 0, "skipped": 0}
    
    logger.info(f"Found {len(fixes_needed)} trades that need status fixes:")
    for fix in fixes_needed:
        logger.info(
            f"  Trade ID {fix['trade_id']} (exchange_trade_id: {fix['exchange_trade_id']}): "
            f"{fix['current_status']} → {fix['expected_status']} ({fix['reason']})"
        )
    
    if dry_run:
        logger.info("[DRY RUN] Would fix the above trades")
        return {"fixed": len(fixes_needed), "skipped": 0, "dry_run": True}
    
    # Apply fixes
    fixed = 0
    skipped = 0
    
    for fix in fixes_needed:
        try:
            ledger.update_trade_record_status(
                ledger_trade_id=fix["trade_id"],
                record_status=fix["expected_status"],
                notes=f"Status corrected: {fix['current_status']} → {fix['expected_status']}. "
                      f"Reason: {fix['reason']}. "
                      f"Original notes: {fix.get('notes', '') or ''}",
            )
            logger.info(
                f"Fixed trade {fix['trade_id']}: {fix['current_status']} → {fix['expected_status']}"
            )
            fixed += 1
        except Exception as e:
            logger.error(f"Error fixing trade {fix['trade_id']}: {e}")
            skipped += 1
    
    return {"fixed": fixed, "skipped": skipped, "dry_run": False}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Investigate and fix trade status issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Investigate trades
  python scripts/integrity/investigate_trade_status.py --symbol BTCUSDT --investigate

  # Dry run (show what would be fixed)
  python scripts/integrity/investigate_trade_status.py --symbol BTCUSDT --fix --dry-run

  # Fix trades
  python scripts/integrity/investigate_trade_status.py --symbol BTCUSDT --fix
        """,
    )
    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Symbol to investigate (e.g., BTCUSDT)",
    )
    parser.add_argument(
        "--book-id",
        type=str,
        default=None,
        help="Book ID to investigate (optional)",
    )
    parser.add_argument(
        "--investigate",
        action="store_true",
        help="Investigate trades and show current status",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix trade statuses (test_book=VALID, default=INVALID)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    args = parser.parse_args()
    
    if not args.investigate and not args.fix:
        parser.error("Must specify --investigate or --fix")
    
    ledger = Ledger()
    
    if args.investigate:
        logger.info("=" * 80)
        logger.info("INVESTIGATION MODE")
        logger.info("=" * 80)
        
        results = investigate_trades(ledger, symbol=args.symbol, book_id=args.book_id)
        
        print("\n" + "=" * 80)
        print("INVESTIGATION RESULTS")
        print("=" * 80)
        print(f"Symbol: {results['symbol']}")
        print(f"Book ID: {results['book_id'] or 'all'}")
        print(f"Total Trades: {results['total_trades']}")
        print()
        
        for book_id, analysis in results["trades_by_book"].items():
            print(f"Book: {book_id}")
            print(f"  Total: {analysis['total']}")
            print(f"  VALID: {analysis['valid']}")
            print(f"  INVALID: {analysis['invalid']}")
            print(f"  Contradictions (notes say INVALID but status is VALID): {len(analysis['contradictions'])}")
            
            if analysis['contradictions']:
                print("  Contradictions:")
                for c in analysis['contradictions']:
                    print(f"    - Trade ID {c['id']} (exchange_trade_id: {c['exchange_trade_id']})")
                    print(f"      Status: {c['record_status']}")
                    print(f"      Notes: {c['notes'][:100] if c['notes'] else 'None'}")
            
            print()
            print("  All trades:")
            for trade in analysis['trades']:
                print(
                    f"    ID {trade['id']}: exchange_trade_id={trade['exchange_trade_id']}, "
                    f"book_id={trade['book_id']}, status={trade['record_status']}, "
                    f"order_id={trade['order_id']}"
                )
            print()
    
    if args.fix:
        logger.info("=" * 80)
        logger.info("FIX MODE")
        logger.info("=" * 80)
        
        results = fix_trade_statuses(ledger, symbol=args.symbol, dry_run=args.dry_run)
        
        print("\n" + "=" * 80)
        print("FIX RESULTS")
        print("=" * 80)
        print(f"Fixed: {results['fixed']}")
        print(f"Skipped: {results['skipped']}")
        if results.get('dry_run'):
            print("\nThis was a dry run. Run without --dry-run to apply fixes.")
        print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
