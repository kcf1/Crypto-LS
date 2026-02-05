"""Booking reconciliation: compare ledger vs exchange and ledger vs itself.

Performs 6 reconciliations:
1. Orders vs trades (filled quantity consistency)
2. Trades vs Binance (missing/extra trades)
3. Positions vs trades (position quantity consistency)
4. Positions vs Binance (position comparison)
5. Orders vs Binance (order status consistency)
6. Balances vs Binance (balance comparison)
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from booking.ledger import Ledger
from config import settings
from execution.binance.client import BinanceClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def rec1_orders_vs_trades(ledger: Ledger, book_id: Optional[str] = None) -> Dict[str, Any]:
    """Rec 1: Orders vs trades - check filled quantity consistency."""
    logger.info("Running Rec 1: Orders vs Trades")
    
    mismatches = []
    # Only check VALID orders and trades (default behavior, but explicit for clarity)
    orders = ledger.get_orders(book_id=book_id, record_status="VALID")
    
    for order in orders:
        order_id = order["id"]
        order_quantity = order["quantity"]
        order_status = order["status"]
        
        # Sum filled quantity from VALID trades only
        trades = ledger.get_trades(order_id=order_id, book_id=book_id, record_status="VALID")
        filled_quantity = sum(t["quantity"] for t in trades)
        
        # Check consistency
        tolerance = 1e-12
        if abs(filled_quantity - order_quantity) > tolerance and order_status == "FILLED":
            mismatches.append({
                "order_id": order_id,
                "exchange_order_id": order["exchange_order_id"],
                "symbol": order["symbol"],
                "order_quantity": order_quantity,
                "filled_quantity": filled_quantity,
                "difference": filled_quantity - order_quantity,
                "status": order_status,
            })
        elif filled_quantity > order_quantity + tolerance:
            mismatches.append({
                "order_id": order_id,
                "exchange_order_id": order["exchange_order_id"],
                "symbol": order["symbol"],
                "order_quantity": order_quantity,
                "filled_quantity": filled_quantity,
                "difference": filled_quantity - order_quantity,
                "status": order_status,
                "issue": "filled_quantity_exceeds_order_quantity",
            })
    
    return {
        "name": "Orders vs Trades",
        "total_orders": len(orders),
        "mismatches": mismatches,
        "passed": len(mismatches) == 0,
    }


def rec2_trades_vs_binance(ledger: Ledger, binance_client: BinanceClient, book_id: Optional[str] = None) -> Dict[str, Any]:
    """Rec 2: Trades vs Binance - check for missing/extra trades."""
    logger.info("Running Rec 2: Trades vs Binance")
    
    # Get symbols with recent trades (last 7 days)
    seven_days_ago = int((time.time() - 7 * 24 * 3600) * 1000)
    
    # Only check VALID trades (default behavior, but explicit for clarity)
    trades = ledger.get_trades(book_id=book_id, record_status="VALID")
    recent_trades = [t for t in trades if t["traded_at"] >= seven_days_ago]
    
    symbols_with_trades = set(t["symbol"] for t in recent_trades)
    
    missing_trades = []
    extra_trades = []
    
    for symbol in symbols_with_trades:
        try:
            # Get trades from Binance (last 7 days)
            binance_trades = binance_client.get_my_trades(
                symbol=symbol,
                startTime=seven_days_ago,
                limit=1000,
            )
            
            # Build sets for comparison
            ledger_trade_ids = set(
                str(t["exchange_trade_id"]) for t in recent_trades
                if t["symbol"] == symbol and t["exchange_trade_id"]
            )
            binance_trade_ids = set(str(t.get("id", "")) for t in binance_trades)
            
            # Find missing (in Binance but not in ledger)
            missing = binance_trade_ids - ledger_trade_ids
            for trade_id in missing:
                trade = next((t for t in binance_trades if str(t.get("id", "")) == trade_id), None)
                if trade:
                    missing_trades.append({
                        "symbol": symbol,
                        "exchange_trade_id": trade_id,
                        "side": trade.get("side"),
                        "quantity": trade.get("qty"),
                        "price": trade.get("price"),
                        "time": trade.get("time"),
                    })
            
            # Find extra (in ledger but not in Binance)
            # These are trades that exist in ledger but not in Binance
            extra = ledger_trade_ids - binance_trade_ids
            for trade_id in extra:
                trade = next(
                    (t for t in recent_trades if str(t.get("exchange_trade_id", "")) == trade_id),
                    None
                )
                if trade:
                    extra_trades.append({
                        "symbol": symbol,
                        "exchange_trade_id": trade_id,
                        "ledger_trade_id": trade.get("id"),
                        "side": trade.get("side"),
                        "quantity": trade.get("quantity"),
                        "price": trade.get("price"),
                        "traded_at": trade.get("traded_at"),
                        "order_id": trade.get("order_id"),
                    })
            
        except Exception as e:
            logger.error(f"Error fetching Binance trades for {symbol}: {e}")
            continue
    
    return {
        "name": "Trades vs Binance",
        "symbols_checked": len(symbols_with_trades),
        "missing_trades": missing_trades,
        "extra_trades": extra_trades,
        "passed": len(missing_trades) == 0 and len(extra_trades) == 0,
    }


def rec3_positions_vs_trades(ledger: Ledger, book_id: Optional[str] = None) -> Dict[str, Any]:
    """Rec 3: Positions vs trades - check position quantity consistency."""
    logger.info("Running Rec 3: Positions vs Trades")
    
    positions = ledger.get_positions(book_id=book_id)
    mismatches = []
    
    for position in positions:
        book_id_val = position["book_id"]
        symbol = position["symbol"]
        ledger_quantity = position["quantity"]
        ledger_avg_price = position["avg_price"]
        
        # Calculate position from VALID trades only
        trades = ledger.get_trades(symbol=symbol, book_id=book_id_val, record_status="VALID")
        calculated_quantity = sum(
            t["quantity"] if t["side"] == "BUY" else -t["quantity"]
            for t in trades
        )
        
        # Calculate VWAP
        if calculated_quantity != 0:
            total_cost = sum(
                t["quantity"] * t["price"] if t["side"] == "BUY" else -t["quantity"] * t["price"]
                for t in trades
            )
            calculated_avg_price = total_cost / calculated_quantity
        else:
            calculated_avg_price = 0.0
        
        tolerance = 1e-12
        if abs(ledger_quantity - calculated_quantity) > tolerance:
            mismatches.append({
                "book_id": book_id_val,
                "symbol": symbol,
                "ledger_quantity": ledger_quantity,
                "calculated_quantity": calculated_quantity,
                "difference": calculated_quantity - ledger_quantity,
                "ledger_avg_price": ledger_avg_price,
                "calculated_avg_price": calculated_avg_price,
            })
    
    return {
        "name": "Positions vs Trades",
        "total_positions": len(positions),
        "mismatches": mismatches,
        "passed": len(mismatches) == 0,
    }


def rec4_positions_vs_binance(ledger: Ledger, binance_client: BinanceClient, book_id: Optional[str] = None) -> Dict[str, Any]:
    """Rec 4: Positions vs Binance - compare ledger positions with exchange."""
    logger.info("Running Rec 4: Positions vs Binance")
    
    # Get account info from Binance
    try:
        account = binance_client.get_account()
        binance_balances = {b["asset"]: float(b["free"]) + float(b["locked"]) for b in account.get("balances", [])}
    except Exception as e:
        logger.error(f"Error fetching Binance account: {e}")
        return {
            "name": "Positions vs Binance",
            "error": str(e),
            "passed": False,
        }
    
    # Get ledger positions (sum across all books if book_id not specified)
    positions = ledger.get_positions(book_id=book_id)
    
    # Convert positions to asset balances (for spot trading, positions are in base assets)
    # This is a simplified comparison - in reality, you'd need to handle each symbol separately
    mismatches = []
    
    # For each position, check if base asset balance matches
    for position in positions:
        symbol = position["symbol"]
        quantity = position["quantity"]
        
        # Parse symbol to get base asset
        try:
            from booking.ledger import _parse_symbol
            base_asset, _ = _parse_symbol(symbol)
        except Exception as e:
            logger.warning(f"Could not parse symbol {symbol}: {e}")
            continue
        
        # Compare with Binance balance
        binance_balance = binance_balances.get(base_asset, 0.0)
        
        # Note: This comparison assumes single book or sum across books
        # For multi-book setups, you'd need to sum ledger balances across books
        tolerance = 1e-12
        if abs(quantity - binance_balance) > tolerance:
            mismatches.append({
                "symbol": symbol,
                "base_asset": base_asset,
                "ledger_quantity": quantity,
                "binance_balance": binance_balance,
                "difference": binance_balance - quantity,
            })
    
    return {
        "name": "Positions vs Binance",
        "total_positions": len(positions),
        "mismatches": mismatches,
        "passed": len(mismatches) == 0,
    }


def rec5_orders_vs_binance(ledger: Ledger, binance_client: BinanceClient, book_id: Optional[str] = None) -> Dict[str, Any]:
    """Rec 5: Orders vs Binance - check order status consistency."""
    logger.info("Running Rec 5: Orders vs Binance")
    
    # Get open orders and recent orders from ledger (last 7 days)
    # Only check VALID orders (default behavior, but explicit for clarity)
    seven_days_ago = int((time.time() - 7 * 24 * 3600) * 1000)
    all_orders = ledger.get_orders(book_id=book_id, record_status="VALID")
    recent_orders = [o for o in all_orders if o.get("created_at", 0) >= seven_days_ago]
    
    mismatches = []
    extra_orders = []  # Orders in ledger but not in Binance
    
    for order in recent_orders:
        if not order["exchange_order_id"]:
            continue
        
        symbol = order["symbol"]
        exchange_order_id = order["exchange_order_id"]
        
        try:
            # Get order from Binance
            binance_order = binance_client.get_order(symbol=symbol, order_id=int(exchange_order_id))
            
            # Compare status
            ledger_status = order["status"]
            binance_status = binance_order.get("status", "").upper()
            
            if ledger_status != binance_status:
                mismatches.append({
                    "ledger_order_id": order["id"],
                    "exchange_order_id": exchange_order_id,
                    "symbol": symbol,
                    "ledger_status": ledger_status,
                    "binance_status": binance_status,
                    "issue": "status_mismatch",
                })
            
            # Compare quantities
            ledger_quantity = order["quantity"]
            binance_quantity = float(binance_order.get("origQty", "0"))
            binance_filled = float(binance_order.get("executedQty", "0"))
            
            tolerance = 1e-12
            if abs(ledger_quantity - binance_quantity) > tolerance:
                mismatches.append({
                    "ledger_order_id": order["id"],
                    "exchange_order_id": exchange_order_id,
                    "symbol": symbol,
                    "issue": "quantity_mismatch",
                    "ledger_quantity": ledger_quantity,
                    "binance_quantity": binance_quantity,
                    "binance_filled": binance_filled,
                })
                
        except Exception as e:
            # Order might not exist on exchange
            error_msg = str(e).lower()
            if "does not exist" in error_msg or "-2013" in error_msg or "not found" in error_msg:
                # Order doesn't exist in Binance - mark as extra
                extra_orders.append({
                    "ledger_order_id": order["id"],
                    "exchange_order_id": exchange_order_id,
                    "symbol": symbol,
                    "ledger_status": order["status"],
                    "created_at": order.get("created_at"),
                    "reason": "order_not_found_on_exchange",
                })
            else:
                # Other error (e.g., API error) - log but don't mark as extra
                logger.debug(f"Could not fetch order {exchange_order_id} from Binance: {e}")
            continue
    
    return {
        "name": "Orders vs Binance",
        "total_orders_checked": len([o for o in recent_orders if o["exchange_order_id"]]),
        "mismatches": mismatches,
        "extra_orders": extra_orders,
        "passed": len(mismatches) == 0 and len(extra_orders) == 0,
    }


def rec6_balances_vs_binance(ledger: Ledger, binance_client: BinanceClient, book_id: Optional[str] = None) -> Dict[str, Any]:
    """Rec 6: Balances vs Binance - compare ledger balances with exchange."""
    logger.info("Running Rec 6: Balances vs Binance")
    
    # Get Binance balances
    try:
        account = binance_client.get_account()
        binance_balances = {
            b["asset"]: {
                "free": float(b["free"]),
                "locked": float(b["locked"]),
            }
            for b in account.get("balances", [])
        }
    except Exception as e:
        logger.error(f"Error fetching Binance account: {e}")
        return {
            "name": "Balances vs Binance",
            "error": str(e),
            "passed": False,
        }
    
    # Get ledger balances (sum across all books if book_id not specified)
    ledger_balances_raw = ledger.get_balances(book_id=book_id)
    
    # Sum balances by asset across books (if multiple books)
    ledger_balances: Dict[str, Dict[str, float]] = {}
    for balance in ledger_balances_raw:
        asset = balance["asset"]
        if asset not in ledger_balances:
            ledger_balances[asset] = {"free": 0.0, "locked": 0.0}
        ledger_balances[asset]["free"] += balance["free"]
        ledger_balances[asset]["locked"] += balance["locked"]
    
    mismatches = []
    
    # Compare balances
    all_assets = set(ledger_balances.keys()) | set(binance_balances.keys())
    
    for asset in all_assets:
        ledger_free = ledger_balances.get(asset, {}).get("free", 0.0)
        ledger_locked = ledger_balances.get(asset, {}).get("locked", 0.0)
        binance_free = binance_balances.get(asset, {}).get("free", 0.0)
        binance_locked = binance_balances.get(asset, {}).get("locked", 0.0)
        
        tolerance = 1e-12
        if abs(ledger_free - binance_free) > tolerance or abs(ledger_locked - binance_locked) > tolerance:
            mismatches.append({
                "asset": asset,
                "ledger_free": ledger_free,
                "ledger_locked": ledger_locked,
                "binance_free": binance_free,
                "binance_locked": binance_locked,
                "free_difference": binance_free - ledger_free,
                "locked_difference": binance_locked - ledger_locked,
            })
    
    return {
        "name": "Balances vs Binance",
        "total_assets_checked": len(all_assets),
        "mismatches": mismatches,
        "passed": len(mismatches) == 0,
    }


def main() -> int:
    """Run all booking reconciliations and generate report."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run booking reconciliations")
    parser.add_argument(
        "--book-id",
        type=str,
        default=None,
        help="Book ID to reconcile (reconciles all if not specified)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/integrity",
        help="Output directory for reports",
    )
    args = parser.parse_args()
    
    logger.info("Starting booking reconciliation")
    logger.info(f"Book ID: {args.book_id or 'all'}")
    
    ledger = Ledger()
    binance_client = BinanceClient()
    
    # Run all reconciliations
    results = []
    
    results.append(rec1_orders_vs_trades(ledger, book_id=args.book_id))
    results.append(rec2_trades_vs_binance(ledger, binance_client, book_id=args.book_id))
    results.append(rec3_positions_vs_trades(ledger, book_id=args.book_id))
    results.append(rec4_positions_vs_binance(ledger, binance_client, book_id=args.book_id))
    results.append(rec5_orders_vs_binance(ledger, binance_client, book_id=args.book_id))
    results.append(rec6_balances_vs_binance(ledger, binance_client, book_id=args.book_id))
    
    # Generate summary
    total_checks = len(results)
    passed_checks = sum(1 for r in results if r.get("passed", False))
    failed_checks = total_checks - passed_checks
    
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "book_id": args.book_id,
        "total_checks": total_checks,
        "passed": passed_checks,
        "failed": failed_checks,
        "results": results,
    }
    
    # Save JSON report
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"booking_recon_{timestamp_str}.json"
    
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    logger.info(f"JSON report saved to {json_path}")
    
    # Print text summary
    print("=" * 80)
    print("BOOKING RECONCILIATION REPORT")
    print("=" * 80)
    print(f"Timestamp: {summary['timestamp']}")
    print(f"Book ID: {args.book_id or 'all'}")
    print(f"Total Checks: {total_checks}")
    print(f"Passed: {passed_checks}")
    print(f"Failed: {failed_checks}")
    print()
    
    for result in results:
        name = result["name"]
        passed = result.get("passed", False)
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {name}")
        
        if not passed:
            mismatches = result.get("mismatches", [])
            if mismatches:
                print(f"  Mismatches: {len(mismatches)}")
                # Show first few mismatches
                for mismatch in mismatches[:3]:
                    print(f"    - {mismatch}")
                if len(mismatches) > 3:
                    print(f"    ... and {len(mismatches) - 3} more")
        print()
    
    print(f"Full report: {json_path}")
    print("=" * 80)
    
    return 0 if failed_checks == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
