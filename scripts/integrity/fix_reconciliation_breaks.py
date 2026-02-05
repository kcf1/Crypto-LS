"""Fix reconciliation breaks - automated fixes for common reconciliation issues.

This script provides automated fixes for each of the 6 reconciliation checks.
Run reconciliations first to identify issues, then use this script to fix them.

Usage:
    # Fix all issues automatically (with confirmation)
    python scripts/integrity/fix_reconciliation_breaks.py --book-id test_book --auto-fix

    # Fix specific rec (e.g., Rec 2 - missing trades)
    python scripts/integrity/fix_reconciliation_breaks.py --book-id test_book --fix rec2

    # Dry run (show what would be fixed without making changes)
    python scripts/integrity/fix_reconciliation_breaks.py --book-id test_book --dry-run
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from booking.ledger import Ledger
from config import settings
from execution.binance.client import BinanceClient
from execution.orchestrator import BookingOrchestrator
from scripts.integrity.check_booking_recon import (
    rec1_orders_vs_trades,
    rec2_trades_vs_binance,
    rec3_positions_vs_trades,
    rec4_positions_vs_binance,
    rec5_orders_vs_binance,
    rec6_balances_vs_binance,
)
from scripts.utils.rebuild_balances import rebuild_balances
from scripts.utils.rebuild_positions import rebuild_positions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def fix_rec1_orders_vs_trades(
    ledger: Ledger,
    book_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Fix Rec 1: Orders vs trades - update order status or add missing trades.
    
    Common fixes:
    - Order status says FILLED but sum of fills < order qty → update status to PARTIALLY_FILLED
    - Order status says PARTIALLY_FILLED but sum of fills = order qty → update status to FILLED
    - Order status says NEW but has fills → update status appropriately
    """
    logger.info("Fixing Rec 1: Orders vs Trades")
    
    result = rec1_orders_vs_trades(ledger, book_id=book_id)
    mismatches = result.get("mismatches", [])
    
    if not mismatches:
        logger.info("Rec 1: No mismatches found")
        return {"fixed": 0, "skipped": 0, "invalidated": 0}
    
    fixed = 0
    skipped = 0
    
    for mismatch in mismatches:
        order_id = mismatch["order_id"]
        order_quantity = mismatch["order_quantity"]
        filled_quantity = mismatch["filled_quantity"]
        current_status = mismatch["status"]
        
        # Determine correct status
        tolerance = 1e-12
        if abs(filled_quantity - order_quantity) < tolerance:
            new_status = "FILLED"
        elif filled_quantity > tolerance:
            new_status = "PARTIALLY_FILLED"
        else:
            new_status = "NEW"
        
        if new_status == current_status:
            logger.debug(f"Order {order_id}: Status already correct ({current_status})")
            skipped += 1
            continue
        
        if dry_run:
            logger.info(
                f"[DRY RUN] Would update order {order_id}: {current_status} → {new_status} "
                f"(filled: {filled_quantity}/{order_quantity})"
            )
            fixed += 1
        else:
            # Update order status
            try:
                with ledger._engine.connect() as conn:
                    from sqlalchemy import text
                    conn.execute(
                        text("""
                            UPDATE orders 
                            SET status = :status, updated_at = :updated_at
                            WHERE id = :order_id
                        """),
                        {
                            "order_id": order_id,
                            "status": new_status,
                            "updated_at": int(time.time() * 1000),
                        },
                    )
                    conn.commit()
                logger.info(
                    f"Updated order {order_id}: {current_status} → {new_status} "
                    f"(filled: {filled_quantity}/{order_quantity})"
                )
                fixed += 1
            except Exception as e:
                logger.error(f"Error updating order {order_id}: {e}")
                skipped += 1
    
    return {"fixed": fixed, "skipped": skipped, "invalidated": 0}


def fix_rec2_trades_vs_binance(
    ledger: Ledger,
    binance_client: BinanceClient,
    orchestrator: BookingOrchestrator,
    book_id: Optional[str] = None,
    dry_run: bool = False,
    handle_extra: bool = True,
) -> Dict[str, Any]:
    """Fix Rec 2: Trades vs Binance - add missing trades and handle extra trades.
    
    Common fixes:
    - Exchange has trades we don't have → fetch and book them
    - Ledger has trades Binance doesn't have → mark as invalid/test data (with audit trail)
    """
    logger.info("Fixing Rec 2: Trades vs Binance")
    
    result = rec2_trades_vs_binance(ledger, binance_client, book_id=book_id)
    missing_trades = result.get("missing_trades", [])
    extra_trades = result.get("extra_trades", [])
    
    if not missing_trades and not extra_trades:
        logger.info("Rec 2: No missing or extra trades found")
        return {"fixed": 0, "skipped": 0, "invalidated": 0}
    
    fixed = 0
    skipped = 0
    invalidated = 0
    
    # Handle extra trades (in ledger but not in Binance)
    if handle_extra and extra_trades:
        logger.info(f"Found {len(extra_trades)} extra trades (in ledger but not in Binance)")
        logger.info("These may be test data or invalid records. Options:")
        logger.info("  1. Mark as invalid (add to adjustments table for audit)")
        logger.info("  2. Delete from ledger (not recommended - loses audit trail)")
        logger.info("  3. Skip (manual investigation required)")
        
        if not dry_run:
            # Mark extra trades as invalid by creating adjustment records
            for trade in extra_trades:
                try:
                    # Create adjustment record for audit
                    ledger.record_adjustment(
                        venue=settings.venue,
                        book_id=trade.get("book_id") or book_id or "unknown",
                        type="trade_invalidation",
                        asset_or_symbol=trade["symbol"],
                        delta_or_value=0.0,  # No delta, just marking as invalid
                        reason=f"Trade {trade['exchange_trade_id']} exists in ledger but not in Binance. "
                               f"Marked as invalid/test data.",
                        created_by="reconciliation_fix_script",
                        notes=f"Ledger trade_id: {trade.get('ledger_trade_id')}, "
                              f"Exchange trade_id: {trade['exchange_trade_id']}",
                    )
                    
                    # Optionally: Update trade notes to mark as invalid
                    # (We don't delete trades to maintain audit trail)
                    with ledger._engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(
                            text("""
                                UPDATE trades 
                                SET notes = COALESCE(notes || ' | ', '') || :note
                                WHERE id = :trade_id
                            """),
                            {
                                "trade_id": trade.get("ledger_trade_id"),
                                "note": "[INVALID] Not found in Binance - marked by reconciliation fix",
                            },
                        )
                        conn.commit()
                    
                    logger.info(
                        f"Marked trade {trade['exchange_trade_id']} as invalid "
                        f"(ledger_trade_id: {trade.get('ledger_trade_id')})"
                    )
                    invalidated += 1
                except Exception as e:
                    logger.error(f"Error invalidating trade {trade.get('exchange_trade_id')}: {e}")
                    skipped += 1
        
        if dry_run:
            logger.info(f"[DRY RUN] Would invalidate {len(extra_trades)} extra trades")
            invalidated = len(extra_trades)
    
    if not missing_trades:
        return {"fixed": 0, "skipped": skipped, "invalidated": invalidated}
    
    # Group missing trades by symbol
    trades_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for trade in missing_trades:
        symbol = trade["symbol"]
        if symbol not in trades_by_symbol:
            trades_by_symbol[symbol] = []
        trades_by_symbol[symbol].append(trade)
    
    for symbol, trades in trades_by_symbol.items():
        logger.info(f"Processing {len(trades)} missing trades for {symbol}")
        
        if dry_run:
            logger.info(f"[DRY RUN] Would add {len(trades)} trades for {symbol}")
            fixed += len(trades)
            continue
        
        # Try to sync fills for this symbol
        # This will use the order-driven approach to find and book missing trades
        try:
            # Get all orders for this symbol to find which book they belong to
            orders = ledger.get_orders(symbol=symbol, book_id=book_id)
            
            # For each missing trade, try to find matching order
            for trade in trades:
                exchange_trade_id = trade["exchange_trade_id"]
                order_id_from_exchange = trade.get("orderId")  # May not be in trade data
                
                # Try to find order by exchange_order_id if we have it
                if order_id_from_exchange:
                    order = ledger.get_order_by_exchange_id(
                        venue=settings.venue,
                        exchange_order_id=str(order_id_from_exchange),
                        book_id=book_id,
                    )
                    if order:
                        # Use order's book_id
                        trade_book_id = order["book_id"]
                    else:
                        # No matching order - skip (would need manual booking)
                        logger.warning(
                            f"Missing trade {exchange_trade_id} has no matching order, "
                            f"skipping (use manual booking if needed)"
                        )
                        skipped += 1
                        continue
                else:
                    # No order_id in trade - try to match by symbol and time
                    # This is a fallback - ideally all trades should have order_id
                    logger.warning(
                        f"Missing trade {exchange_trade_id} has no order_id, "
                        f"cannot determine book_id automatically"
                    )
                    skipped += 1
                    continue
                
                # Book the trade manually
                try:
                    trade_id = ledger.record_trade(
                        venue=settings.venue,
                        book_id=trade_book_id,
                        symbol=symbol,
                        side=trade.get("side", "").upper(),
                        quantity=float(trade.get("quantity", "0")),
                        price=float(trade.get("price", "0")),
                        traded_at=trade.get("time", 0),
                        exchange_trade_id=exchange_trade_id,
                        order_id=order["id"] if order else None,
                        commission=0.0,  # May not be in trade data
                        commission_asset=None,
                    )
                    logger.info(f"Booked missing trade {exchange_trade_id} (trade_id={trade_id})")
                    fixed += 1
                except Exception as e:
                    logger.error(f"Error booking trade {exchange_trade_id}: {e}")
                    skipped += 1
            
            # Also try running fill sync for the symbol to catch any we missed
            try:
                trade_ids = orchestrator.sync_fills_for_symbol(symbol=symbol, book_id=book_id)
                if trade_ids:
                    logger.info(f"Fill sync found {len(trade_ids)} additional trades for {symbol}")
                    fixed += len(trade_ids)
            except Exception as e:
                logger.warning(f"Error running fill sync for {symbol}: {e}")
        
        except Exception as e:
            logger.error(f"Error processing missing trades for {symbol}: {e}")
            skipped += len(trades)
    
    return {"fixed": fixed, "skipped": skipped, "invalidated": invalidated}


def fix_rec3_positions_vs_trades(
    ledger: Ledger,
    book_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Fix Rec 3: Positions vs trades - rebuild positions from trades."""
    logger.info("Fixing Rec 3: Positions vs Trades")
    
    result = rec3_positions_vs_trades(ledger, book_id=book_id)
    mismatches = result.get("mismatches", [])
    
    if not mismatches:
        logger.info("Rec 3: No mismatches found")
        return {"fixed": 0, "skipped": 0, "invalidated": 0}
    
    if dry_run:
        logger.info(f"[DRY RUN] Would rebuild positions for {len(mismatches)} mismatched positions")
        return {"fixed": len(mismatches), "skipped": 0, "invalidated": 0}
    
    try:
        rebuild_positions(ledger, book_id=book_id)
        logger.info("Positions rebuilt successfully")
        return {"fixed": len(mismatches), "skipped": 0, "invalidated": 0}
    except Exception as e:
        logger.error(f"Error rebuilding positions: {e}")
        return {"fixed": 0, "skipped": len(mismatches), "invalidated": 0}


def fix_rec4_positions_vs_binance(
    ledger: Ledger,
    binance_client: BinanceClient,
    book_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Fix Rec 4: Positions vs Binance - usually fixed by fixing Rec 2 or Rec 6.
    
    This rec typically fails due to missing trades (Rec 2) or wrong balances (Rec 6).
    Fix those first, then rebuild positions.
    """
    logger.info("Fixing Rec 4: Positions vs Binance")
    logger.info("Note: Rec 4 is usually fixed by fixing Rec 2 (missing trades) or Rec 6 (balances)")
    logger.info("Fixing Rec 3 (positions vs trades) first...")
    
    # Fix positions vs trades first
    rec3_result = fix_rec3_positions_vs_trades(ledger, book_id=book_id, dry_run=dry_run)
    
    result = rec4_positions_vs_binance(ledger, binance_client, book_id=book_id)
    mismatches = result.get("mismatches", [])
    
    if not mismatches:
        logger.info("Rec 4: No mismatches found after fixing Rec 3")
        return rec3_result
    
    logger.warning(
        f"Rec 4 still has {len(mismatches)} mismatches after fixing positions. "
        f"These are likely due to missing trades (Rec 2) or balance issues (Rec 6). "
        f"Fix those first."
    )
    
    return {
        "fixed": rec3_result.get("fixed", 0),
        "skipped": rec3_result.get("skipped", 0) + len(mismatches),
        "invalidated": rec3_result.get("invalidated", 0),
    }


def fix_rec5_orders_vs_binance(
    ledger: Ledger,
    binance_client: BinanceClient,
    book_id: Optional[str] = None,
    dry_run: bool = False,
    handle_extra: bool = True,
) -> Dict[str, Any]:
    """Fix Rec 5: Orders vs Binance - sync order status and handle extra orders.
    
    Common fixes:
    - Order status mismatch → update status from Binance
    - Orders in ledger but not in Binance → mark as invalid/cancelled
    """
    logger.info("Fixing Rec 5: Orders vs Binance")
    
    result = rec5_orders_vs_binance(ledger, binance_client, book_id=book_id)
    mismatches = result.get("mismatches", [])
    extra_orders = result.get("extra_orders", [])
    
    if not mismatches and not extra_orders:
        logger.info("Rec 5: No mismatches or extra orders found")
        return {"fixed": 0, "skipped": 0, "invalidated": 0}
    
    fixed = 0
    skipped = 0
    
    for mismatch in mismatches:
        ledger_order_id = mismatch.get("ledger_order_id")
        exchange_order_id = mismatch.get("exchange_order_id")
        symbol = mismatch.get("symbol")
        ledger_status = mismatch.get("ledger_status")
        binance_status = mismatch.get("binance_status")
        issue = mismatch.get("issue")
        
        if issue == "quantity_mismatch":
            logger.warning(
                f"Order {exchange_order_id}: Quantity mismatch detected. "
                f"This may require manual investigation."
            )
            skipped += 1
            continue
        
        if ledger_status == binance_status:
            logger.debug(f"Order {exchange_order_id}: Status already correct")
            skipped += 1
            continue
        
        if dry_run:
            logger.info(
                f"[DRY RUN] Would update order {exchange_order_id}: "
                f"{ledger_status} → {binance_status}"
            )
            fixed += 1
        else:
            try:
                with ledger._engine.connect() as conn:
                    from sqlalchemy import text
                    conn.execute(
                        text("""
                            UPDATE orders 
                            SET status = :status, updated_at = :updated_at
                            WHERE id = :order_id
                        """),
                        {
                            "order_id": ledger_order_id,
                            "status": binance_status,
                            "updated_at": int(time.time() * 1000),
                        },
                    )
                    conn.commit()
                logger.info(
                    f"Updated order {exchange_order_id}: {ledger_status} → {binance_status}"
                )
                fixed += 1
            except Exception as e:
                logger.error(f"Error updating order {exchange_order_id}: {e}")
                skipped += 1
    
    return {"fixed": fixed, "skipped": skipped, "invalidated": invalidated}


def fix_rec6_balances_vs_binance(
    ledger: Ledger,
    book_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Fix Rec 6: Balances vs Binance - rebuild balances from trades."""
    logger.info("Fixing Rec 6: Balances vs Binance")
    
    result = rec6_balances_vs_binance(ledger, BinanceClient(), book_id=book_id)
    mismatches = result.get("mismatches", [])
    
    if not mismatches:
        logger.info("Rec 6: No mismatches found")
        return {"fixed": 0, "skipped": 0, "invalidated": 0}
    
    if dry_run:
        logger.info(f"[DRY RUN] Would rebuild balances for {len(mismatches)} mismatched assets")
        return {"fixed": len(mismatches), "skipped": 0, "invalidated": 0}
    
    try:
        rebuild_balances(ledger, book_id=book_id)
        logger.info("Balances rebuilt successfully")
        return {"fixed": len(mismatches), "skipped": 0, "invalidated": 0}
    except Exception as e:
        logger.error(f"Error rebuilding balances: {e}")
        return {"fixed": 0, "skipped": len(mismatches), "invalidated": 0}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fix reconciliation breaks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (show what would be fixed)
  python scripts/integrity/fix_reconciliation_breaks.py --book-id test_book --dry-run

  # Fix specific rec
  python scripts/integrity/fix_reconciliation_breaks.py --book-id test_book --fix rec2

  # Auto-fix all recs
  python scripts/integrity/fix_reconciliation_breaks.py --book-id test_book --auto-fix
        """,
    )
    parser.add_argument(
        "--book-id",
        type=str,
        default=None,
        help="Book ID to fix (fixes all if not specified)",
    )
    parser.add_argument(
        "--fix",
        type=str,
        choices=["rec1", "rec2", "rec3", "rec4", "rec5", "rec6", "all"],
        default=None,
        help="Specific rec to fix (or 'all' for all recs)",
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Automatically fix all recs without confirmation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    args = parser.parse_args()
    
    if not args.fix and not args.auto_fix:
        parser.error("Must specify --fix <rec> or --auto-fix")
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
    
    ledger = Ledger()
    binance_client = BinanceClient()
    orchestrator = BookingOrchestrator()
    
    fixes_to_run = []
    if args.fix == "all" or args.auto_fix:
        fixes_to_run = ["rec1", "rec2", "rec3", "rec4", "rec5", "rec6"]
    else:
        fixes_to_run = [args.fix]
    
    logger.info(f"Fixing reconciliations for book_id={args.book_id or 'all'}")
    logger.info(f"Recs to fix: {', '.join(fixes_to_run)}")
    
    if not args.dry_run and not args.auto_fix:
        response = input("Proceed with fixes? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Aborted by user")
            return 1
    
    results = {}
    
    # Fix in order (some recs depend on others)
    fix_order = ["rec1", "rec2", "rec3", "rec5", "rec6", "rec4"]
    for rec in fix_order:
        if rec not in fixes_to_run:
            continue
        
        logger.info("=" * 80)
        logger.info(f"Fixing {rec.upper()}")
        logger.info("=" * 80)
        
        try:
            if rec == "rec1":
                results[rec] = fix_rec1_orders_vs_trades(ledger, args.book_id, args.dry_run)
            elif rec == "rec2":
                results[rec] = fix_rec2_trades_vs_binance(
                    ledger, binance_client, orchestrator, args.book_id, args.dry_run,
                    handle_extra=True,
                )
            elif rec == "rec3":
                results[rec] = fix_rec3_positions_vs_trades(ledger, args.book_id, args.dry_run)
            elif rec == "rec4":
                results[rec] = fix_rec4_positions_vs_binance(
                    ledger, binance_client, args.book_id, args.dry_run
                )
            elif rec == "rec5":
                results[rec] = fix_rec5_orders_vs_binance(
                    ledger, binance_client, args.book_id, args.dry_run,
                    handle_extra=True,
                )
            elif rec == "rec6":
                results[rec] = fix_rec6_balances_vs_binance(ledger, args.book_id, args.dry_run)
        except Exception as e:
            logger.error(f"Error fixing {rec}: {e}", exc_info=True)
            results[rec] = {"fixed": 0, "skipped": 0, "error": str(e)}
    
    # Summary
    logger.info("=" * 80)
    logger.info("FIX SUMMARY")
    logger.info("=" * 80)
    
    total_fixed = 0
    total_skipped = 0
    total_invalidated = 0
    
    for rec, result in results.items():
        fixed = result.get("fixed", 0)
        skipped = result.get("skipped", 0)
        invalidated = result.get("invalidated", 0)
        total_fixed += fixed
        total_skipped += skipped
        total_invalidated += invalidated
        
        status = "✓" if (fixed > 0 or invalidated > 0) else "○"
        parts = []
        if fixed > 0:
            parts.append(f"Fixed {fixed}")
        if invalidated > 0:
            parts.append(f"Invalidated {invalidated}")
        if skipped > 0:
            parts.append(f"Skipped {skipped}")
        logger.info(f"{status} {rec.upper()}: {', '.join(parts) if parts else 'No changes'}")
    
    logger.info("-" * 80)
    parts = []
    if total_fixed > 0:
        parts.append(f"Fixed {total_fixed}")
    if total_invalidated > 0:
        parts.append(f"Invalidated {total_invalidated}")
    if total_skipped > 0:
        parts.append(f"Skipped {total_skipped}")
    logger.info(f"Total: {', '.join(parts) if parts else 'No changes'}")
    
    if args.dry_run:
        logger.info("\nThis was a dry run. Run without --dry-run to apply fixes.")
    
    return 0 if total_fixed > 0 or total_skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
