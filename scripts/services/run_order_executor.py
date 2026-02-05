"""Order Executor Service: Redis Stream consumer + HTTP API for order placement and booking.

This service provides:
- Redis Stream consumer for automated order processing
- HTTP API for order placement and queries
- Admin endpoints for manual operations
- Query endpoints for orders, trades, positions, balances
"""

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis
from flask import Flask, jsonify, request
from flask_cors import CORS

# Add project root to path
if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from binance.exceptions import BinanceAPIException
from booking.ledger import Ledger
from config import settings
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

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize components
orchestrator = BookingOrchestrator()
ledger = Ledger()

# Redis configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_STREAM_NAME = "order_stream"
REDIS_CONSUMER_GROUP = "order_executors"
REDIS_CONSUMER_NAME = f"executor-{os.getpid()}"

# Initialize Redis client
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()  # Test connection
    logger.info(f"Connected to Redis at {REDIS_URL}")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    redis_client = None

# HTTP Server configuration
HTTP_HOST = os.environ.get("ORDER_EXECUTOR_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("ORDER_EXECUTOR_PORT", "8000"))


def ensure_consumer_group() -> None:
    """Ensure Redis consumer group exists."""
    if not redis_client:
        return
    
    try:
        redis_client.xgroup_create(
            name=REDIS_STREAM_NAME,
            groupname=REDIS_CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        logger.info(f"Created consumer group: {REDIS_CONSUMER_GROUP}")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug(f"Consumer group {REDIS_CONSUMER_GROUP} already exists")
        else:
            logger.error(f"Failed to create consumer group: {e}")
            raise


def parse_redis_message(msg_data: Dict[str, str]) -> Dict[str, Any]:
    """Parse Redis Stream message data into order parameters."""
    order_data = {}
    
    # Required fields
    if "symbol" in msg_data:
        order_data["symbol"] = msg_data["symbol"]
    if "side" in msg_data:
        order_data["side"] = msg_data["side"]
    
    # Optional fields
    if "quantity" in msg_data:
        try:
            order_data["quantity"] = float(msg_data["quantity"])
        except (ValueError, TypeError):
            pass
    
    if "quote_order_qty" in msg_data:
        try:
            order_data["quote_order_qty"] = float(msg_data["quote_order_qty"])
        except (ValueError, TypeError):
            pass
    
    if "order_type" in msg_data:
        order_data["order_type"] = msg_data["order_type"]
    else:
        order_data["order_type"] = "MARKET"
    
    if "price" in msg_data:
        try:
            order_data["price"] = float(msg_data["price"])
        except (ValueError, TypeError):
            pass
    
    if "time_in_force" in msg_data:
        order_data["time_in_force"] = msg_data["time_in_force"]
    
    if "book_id" in msg_data:
        order_data["book_id"] = msg_data["book_id"]
    else:
        order_data["book_id"] = "default"
    
    if "notes" in msg_data:
        order_data["notes"] = msg_data["notes"]
    
    if "strategy_id" in msg_data:
        if "notes" not in order_data:
            order_data["notes"] = ""
        order_data["notes"] += f" Strategy: {msg_data['strategy_id']}"
    
    return order_data


def process_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process an order (called by both Redis consumer and HTTP endpoint).
    
    Note: Immediate fill sync is handled by BookingOrchestrator.place_order().
    """
    try:
        result = orchestrator.place_order(**order_data)
        return result
    except BinanceAPIException as e:
        logger.error(f"Order placement failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing order: {e}", exc_info=True)
        raise


def consume_redis_orders() -> None:
    """Redis Stream consumer loop (runs in background thread)."""
    if not redis_client:
        logger.warning("Redis not available, skipping Redis consumer")
        return
    
    ensure_consumer_group()
    
    logger.info(f"Starting Redis Stream consumer: {REDIS_CONSUMER_NAME}")
    logger.info(f"Stream: {REDIS_STREAM_NAME}, Group: {REDIS_CONSUMER_GROUP}")
    
    while True:
        try:
            # Read messages from stream
            messages = redis_client.xreadgroup(
                groupname=REDIS_CONSUMER_GROUP,
                consumername=REDIS_CONSUMER_NAME,
                streams={REDIS_STREAM_NAME: ">"},
                count=1,
                block=1000,  # Block for 1 second
            )
            
            for stream_name, msgs in messages:
                for msg_id, msg_data in msgs:
                    try:
                        logger.info(f"Received order from Redis Stream: {msg_id}")
                        
                        # Parse message
                        order_data = parse_redis_message(msg_data)
                        
                        # Process order
                        result = process_order(order_data)
                        
                        # ACK message
                        redis_client.xack(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, msg_id)
                        logger.info(
                            f"Order processed successfully: "
                            f"ledger_order_id={result.get('ledger_order_id')}, "
                            f"exchange_order_id={result.get('exchange_order_id')}"
                        )
                    except Exception as e:
                        logger.error(f"Error processing message {msg_id}: {e}", exc_info=True)
                        # Don't ACK on error - message will be retried
                        # In production, you might want to send to dead letter queue
        
        except redis.exceptions.ConnectionError:
            logger.error("Redis connection lost, retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected error in Redis consumer: {e}", exc_info=True)
            time.sleep(5)


# ============================================================================
# HTTP API Endpoints
# ============================================================================

@app.route("/health", methods=["GET"])
def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "order-executor",
        "redis_connected": redis_client is not None and redis_client.ping() if redis_client else False,
    }), 200


@app.route("/orders", methods=["POST"])
def place_order() -> Dict[str, Any]:
    """Place an order via HTTP API."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        if "symbol" not in data or "side" not in data:
            return jsonify({"error": "symbol and side are required"}), 400
        
        # Validate book_id if provided
        book_id = data.get("book_id", "default")
        if not ledger.validate_book_id(book_id, venue=settings.venue):
            return jsonify({
                "error": f"Invalid or inactive book_id: {book_id}",
                "type": "ValueError"
            }), 400
        
        # Process order
        result = process_order(data)
        return jsonify(result), 201
    
    except BinanceAPIException as e:
        logger.error(f"Binance API error: {e}")
        return jsonify({"error": str(e), "type": "BinanceAPIException"}), 400
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({"error": str(e), "type": "ValueError"}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return jsonify({"error": str(e), "type": "Exception"}), 500


@app.route("/orders", methods=["GET"])
def list_orders() -> Dict[str, Any]:
    """List orders with optional filters."""
    try:
        book_id = request.args.get("book_id")
        symbol = request.args.get("symbol")
        record_status = request.args.get("record_status")  # Optional: VALID, INVALID, DELETED, etc.
        limit = request.args.get("limit", type=int, default=100)
        
        orders = ledger.get_orders(
            venue=settings.venue,
            book_id=book_id,
            symbol=symbol,
            record_status=record_status,  # Defaults to VALID if None
            limit=limit,
        )
        
        return jsonify({
            "orders": orders,
            "count": len(orders),
        }), 200
    
    except Exception as e:
        logger.error(f"Error listing orders: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id: int) -> Dict[str, Any]:
    """Get order by ledger ID."""
    try:
        # Allow querying by record_status if needed (defaults to VALID)
        record_status = request.args.get("record_status")
        orders = ledger.get_orders(venue=settings.venue, record_status=record_status, limit=1000)
        order = next((o for o in orders if o["id"] == order_id), None)
        
        if not order:
            return jsonify({"error": "Order not found"}), 404
        
        return jsonify(order), 200
    
    except Exception as e:
        logger.error(f"Error getting order: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/orders/<int:order_id>/cancel", methods=["POST"])
def cancel_order(order_id: int) -> Dict[str, Any]:
    """Cancel an order."""
    try:
        data = request.json or {}
        book_id = data.get("book_id", "default")
        
        # Get order to find symbol and exchange_order_id (only VALID orders)
        orders = ledger.get_orders(venue=settings.venue, book_id=book_id, record_status="VALID", limit=1000)
        order = next((o for o in orders if o["id"] == order_id), None)
        
        if not order:
            return jsonify({"error": "Order not found"}), 404
        
        # Cancel order
        result = orchestrator.cancel_order(
            symbol=order["symbol"],
            ledger_order_id=order_id,
            exchange_order_id=order.get("exchange_order_id"),
            book_id=book_id,
        )
        
        return jsonify(result), 200
    
    except BinanceAPIException as e:
        logger.error(f"Binance API error: {e}")
        return jsonify({"error": str(e), "type": "BinanceAPIException"}), 400
    except Exception as e:
        logger.error(f"Error canceling order: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/positions", methods=["GET"])
def get_positions() -> Dict[str, Any]:
    """Get positions with optional filters."""
    try:
        book_id = request.args.get("book_id")
        symbol = request.args.get("symbol")
        
        positions = ledger.get_positions(
            book_id=book_id,
            symbol=symbol,
        )
        
        return jsonify({
            "positions": positions,
            "count": len(positions),
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting positions: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/balances", methods=["GET"])
def get_balances() -> Dict[str, Any]:
    """Get balances with optional filters."""
    try:
        book_id = request.args.get("book_id")
        asset = request.args.get("asset")
        
        balances = ledger.get_balances(
            venue=settings.venue,
            book_id=book_id,
            asset=asset,
        )
        
        return jsonify({
            "balances": balances,
            "count": len(balances),
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting balances: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/trades", methods=["GET"])
def list_trades() -> Dict[str, Any]:
    """List trades with optional filters."""
    try:
        book_id = request.args.get("book_id")
        symbol = request.args.get("symbol")
        record_status = request.args.get("record_status")  # Optional: VALID, INVALID, DELETED, etc.
        limit = request.args.get("limit", type=int, default=100)
        
        trades = ledger.get_trades(
            venue=settings.venue,
            book_id=book_id,
            symbol=symbol,
            record_status=record_status,  # Defaults to VALID if None
            limit=limit,
        )
        
        return jsonify({
            "trades": trades,
            "count": len(trades),
        }), 200
    
    except Exception as e:
        logger.error(f"Error listing trades: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Admin Endpoints
# ============================================================================

@app.route("/admin/trades", methods=["POST"])
def manual_trade() -> Dict[str, Any]:
    """Manually book a trade (no exchange call)."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        required = ["venue", "book_id", "symbol", "side", "quantity", "price", "traded_at"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({"error": f"Missing required fields: {missing}"}), 400
        
        # Book trade directly
        trade_id = ledger.record_trade(
            venue=data["venue"],
            book_id=data["book_id"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=float(data["quantity"]),
            price=float(data["price"]),
            traded_at=int(data["traded_at"]),
            exchange_trade_id=data.get("exchange_trade_id"),
            order_id=data.get("order_id"),
            commission=data.get("commission", 0.0),
            commission_asset=data.get("commission_asset"),
            notes=data.get("notes"),
        )
        
        return jsonify({
            "ledger_trade_id": trade_id,
            "message": "Trade booked successfully",
        }), 201
    
    except Exception as e:
        logger.error(f"Error booking manual trade: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/orders", methods=["POST"])
def manual_order() -> Dict[str, Any]:
    """Manually book an order (no exchange call)."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        required = ["venue", "book_id", "symbol", "side", "order_type", "quantity", "status"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({"error": f"Missing required fields: {missing}"}), 400
        
        # Book order directly
        order_id = ledger.record_order(
            venue=data["venue"],
            book_id=data["book_id"],
            symbol=data["symbol"],
            side=data["side"],
            order_type=data["order_type"],
            quantity=float(data["quantity"]),
            status=data["status"],
            created_at=int(data.get("created_at", time.time() * 1000)),
            exchange_order_id=data.get("exchange_order_id"),
            price=data.get("price"),
            updated_at=data.get("updated_at"),
            notes=data.get("notes"),
        )
        
        return jsonify({
            "ledger_order_id": order_id,
            "message": "Order booked successfully",
        }), 201
    
    except Exception as e:
        logger.error(f"Error booking manual order: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/adjustments", methods=["POST"])
def create_adjustment() -> Dict[str, Any]:
    """Create an adjustment (for reconciliation fixes)."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        required = ["venue", "book_id", "type", "asset_or_symbol", "delta_or_value", "reason"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({"error": f"Missing required fields: {missing}"}), 400
        
        # Record adjustment
        adj_id = ledger.record_adjustment(
            venue=data["venue"],
            book_id=data["book_id"],
            adj_type=data["type"],
            asset_or_symbol=data["asset_or_symbol"],
            delta_or_value=float(data["delta_or_value"]),
            reason=data["reason"],
            created_by=data.get("created_by"),
            notes=data.get("notes"),
        )
        
        return jsonify({
            "adjustment_id": adj_id,
            "message": "Adjustment created successfully",
        }), 201
    
    except Exception as e:
        logger.error(f"Error creating adjustment: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/rebuild-positions", methods=["POST"])
def rebuild_positions_endpoint() -> Dict[str, Any]:
    """Rebuild positions table from trades."""
    try:
        data = request.json or {}
        book_id = data.get("book_id")
        
        rebuild_positions(ledger, book_id)
        
        return jsonify({
            "message": "Positions rebuilt successfully",
            "book_id": book_id or "all",
        }), 200
    
    except Exception as e:
        logger.error(f"Error rebuilding positions: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/rebuild-balances", methods=["POST"])
def rebuild_balances_endpoint() -> Dict[str, Any]:
    """Rebuild balances table from trades."""
    try:
        data = request.json or {}
        book_id = data.get("book_id")
        
        rebuild_balances(ledger, book_id)
        
        return jsonify({
            "message": "Balances rebuilt successfully",
            "book_id": book_id or "all",
        }), 200
    
    except Exception as e:
        logger.error(f"Error rebuilding balances: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/reconciliation", methods=["GET"])
def run_reconciliation() -> Dict[str, Any]:
    """Run reconciliation checks and return results."""
    try:
        from execution.binance.client import BinanceClient
        
        book_id = request.args.get("book_id")
        
        # Initialize Binance client for reconciliation
        binance_client = BinanceClient()
        
        # Run all reconciliation checks
        results = {
            "rec1_orders_vs_trades": rec1_orders_vs_trades(ledger, book_id),
            "rec2_trades_vs_binance": rec2_trades_vs_binance(ledger, binance_client, book_id),
            "rec3_positions_vs_trades": rec3_positions_vs_trades(ledger, book_id),
            "rec4_positions_vs_binance": rec4_positions_vs_binance(ledger, binance_client, book_id),
            "rec5_orders_vs_binance": rec5_orders_vs_binance(ledger, binance_client, book_id),
            "rec6_balances_vs_binance": rec6_balances_vs_binance(ledger, binance_client, book_id),
        }
        
        # Determine overall status
        all_passed = all(r.get("passed", False) for r in results.values())
        
        return jsonify({
            "status": "passed" if all_passed else "failed",
            "checks": results,
        }), 200
    
    except Exception as e:
        logger.error(f"Error running reconciliation: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Book Management Endpoints
# ============================================================================

@app.route("/books", methods=["GET"])
def list_books() -> Dict[str, Any]:
    """List books with optional filters."""
    try:
        venue = request.args.get("venue")
        active_only = request.args.get("active_only", "true").lower() in ("true", "1", "yes")
        
        books = ledger.get_books(venue=venue, active_only=active_only)
        
        return jsonify({
            "books": books,
            "count": len(books),
        }), 200
    
    except Exception as e:
        logger.error(f"Error listing books: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/books/<book_id>", methods=["GET"])
def get_book(book_id: str) -> Dict[str, Any]:
    """Get book by ID."""
    try:
        book = ledger.get_book(book_id)
        
        if not book:
            return jsonify({"error": "Book not found"}), 404
        
        return jsonify(book), 200
    
    except Exception as e:
        logger.error(f"Error getting book: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/books", methods=["POST"])
def create_book() -> Dict[str, Any]:
    """Create a new book."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        if "id" not in data or "name" not in data:
            return jsonify({"error": "id and name are required"}), 400
        
        # Get venue from data or use default
        venue = data.get("venue") or settings.venue
        
        # Create book
        book_id = ledger.create_book(
            book_id=data["id"],
            name=data["name"],
            venue=venue,
            description=data.get("description"),
            created_by=data.get("created_by"),
            notes=data.get("notes"),
        )
        
        # Return created book
        book = ledger.get_book(book_id)
        return jsonify(book), 201
    
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({"error": str(e), "type": "ValueError"}), 400
    except Exception as e:
        logger.error(f"Error creating book: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/books/<book_id>", methods=["PUT"])
def update_book(book_id: str) -> Dict[str, Any]:
    """Update a book."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Update book
        updated = ledger.update_book(
            book_id=book_id,
            name=data.get("name"),
            description=data.get("description"),
            is_active=data.get("is_active"),
            notes=data.get("notes"),
        )
        
        if not updated:
            return jsonify({"error": "Book not found"}), 404
        
        # Return updated book
        book = ledger.get_book(book_id)
        return jsonify(book), 200
    
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({"error": str(e), "type": "ValueError"}), 400
    except Exception as e:
        logger.error(f"Error updating book: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/books/<book_id>", methods=["DELETE"])
def delete_book(book_id: str) -> Dict[str, Any]:
    """Deactivate a book (soft delete)."""
    try:
        # Check if book exists
        book = ledger.get_book(book_id)
        if not book:
            return jsonify({"error": "Book not found"}), 404
        
        # Deactivate book (set is_active=false)
        updated = ledger.update_book(book_id=book_id, is_active=False)
        
        if not updated:
            return jsonify({"error": "Failed to deactivate book"}), 500
        
        # Return deactivated book
        book = ledger.get_book(book_id)
        return jsonify({
            **book,
            "message": "Book deactivated successfully",
        }), 200
    
    except Exception as e:
        logger.error(f"Error deactivating book: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Main Entry Point
# ============================================================================

def main() -> None:
    """Main entry point: start Redis consumer and HTTP server."""
    logger.info("Starting Order Executor Service")
    logger.info(f"Redis URL: {REDIS_URL}")
    logger.info(f"HTTP Server: {HTTP_HOST}:{HTTP_PORT}")
    
    # Start Redis consumer in background thread
    if redis_client:
        redis_thread = threading.Thread(target=consume_redis_orders, daemon=True)
        redis_thread.start()
        logger.info("Redis Stream consumer thread started")
    else:
        logger.warning("Redis not available, Redis consumer disabled")
    
    # Start HTTP server
    logger.info(f"Starting HTTP server on {HTTP_HOST}:{HTTP_PORT}")
    app.run(host=HTTP_HOST, port=HTTP_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
