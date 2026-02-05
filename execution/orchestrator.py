"""Booking orchestrator: integrates order execution with booking ledger."""

import logging
from typing import Any, Dict, List, Optional

from binance.exceptions import BinanceAPIException

from booking.ledger import Ledger
from config import settings
from execution.order_manager import OrderManager

logger = logging.getLogger(__name__)


class BookingOrchestrator:
    """Orchestrates order placement, cancellation, and fill synchronization with booking."""

    def __init__(
        self,
        order_manager: Optional[OrderManager] = None,
        ledger: Optional[Ledger] = None,
        venue: Optional[str] = None,
    ) -> None:
        """Initialize orchestrator with order manager and ledger.
        
        Args:
            order_manager: OrderManager instance (creates default if None)
            ledger: Ledger instance (creates default if None)
            venue: Venue identifier (defaults to settings.venue)
        """
        self._order_manager = order_manager or OrderManager()
        self._ledger = ledger or Ledger()
        self._venue = venue or settings.venue

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: Optional[float] = None,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        quote_order_qty: Optional[float] = None,
        time_in_force: str = "GTC",
        book_id: str = "default",
        notes: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Place order on exchange and book it in ledger.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: Order side ("BUY" or "SELL")
            quantity: Base asset quantity (for MARKET/LIMIT orders)
            order_type: Order type ("MARKET", "LIMIT", etc.)
            price: Limit price (required for LIMIT orders)
            quote_order_qty: Quote asset quantity (alternative to quantity for MARKET orders)
            time_in_force: Time in force ("GTC", "IOC", "FOK")
            book_id: Book/strategy identifier
            notes: Optional notes for the order
            **kwargs: Additional order parameters
            
        Returns:
            Dict with ledger_order_id, exchange_order_id, status, symbol, etc.
            
        Raises:
            BinanceAPIException: If order placement fails on exchange
        """
        try:
            # Place order on exchange
            if order_type.upper() == "MARKET":
                response = self._order_manager.submit_market(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    quote_order_qty=quote_order_qty,
                )
            elif order_type.upper() == "LIMIT":
                if price is None:
                    raise ValueError("price is required for LIMIT orders")
                response = self._order_manager.submit_limit(
                    symbol=symbol,
                    side=side,
                    quantity=quantity or 0.0,
                    price=price,
                    time_in_force=time_in_force,
                )
            else:
                # Use generic create_order for other types
                response = self._order_manager._binance.create_order(
                    symbol=symbol,
                    side=side,
                    type=order_type,
                    quantity=quantity,
                    price=price,
                    quoteOrderQty=quote_order_qty,
                    timeInForce=time_in_force,
                    **kwargs,
                )
            
            # Extract fields from Binance response
            exchange_order_id = str(response.get("orderId", ""))
            status = response.get("status", "").upper()
            created_at = response.get("time", 0)
            updated_at = response.get("updateTime")
            executed_qty = float(response.get("executedQty", "0"))
            order_price = response.get("price")
            if order_price:
                order_price = float(order_price)
            
            # Idempotency check: see if order already booked
            existing_order = self._ledger.get_order_by_exchange_id(
                venue=self._venue,
                exchange_order_id=exchange_order_id,
                book_id=book_id,
            )
            if existing_order:
                return {
                    "ledger_order_id": existing_order["id"],
                    "exchange_order_id": exchange_order_id,
                    "status": existing_order["status"],
                    "symbol": symbol,
                    "side": side.upper(),
                    "order_type": order_type.upper(),
                    "quantity": existing_order["quantity"],
                    "price": existing_order["price"],
                    "executed_qty": executed_qty,
                    "created_at": existing_order["created_at"],
                    "updated_at": existing_order["updated_at"],
                    "already_booked": True,
                }
            
            # Book order in ledger
            ledger_order_id = self._ledger.record_order(
                venue=self._venue,
                book_id=book_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=float(response.get("origQty", quantity or 0)),
                status=status,
                created_at=created_at,
                exchange_order_id=exchange_order_id,
                price=order_price,
                updated_at=updated_at,
                notes=notes,
            )
            
            # Immediately sync fills for the order (non-blocking, with error handling)
            try:
                self.sync_fills_for_order(
                    symbol=symbol,
                    exchange_order_id=exchange_order_id,
                    ledger_order_id=ledger_order_id,
                    book_id=book_id,
                )
            except Exception as e:
                # Log error but don't fail order placement if fill sync fails
                logger.warning(f"Failed to sync fills for order {exchange_order_id}: {e}")
            
            return {
                "ledger_order_id": ledger_order_id,
                "exchange_order_id": exchange_order_id,
                "status": status,
                "symbol": symbol,
                "side": side.upper(),
                "order_type": order_type.upper(),
                "quantity": float(response.get("origQty", quantity or 0)),
                "price": order_price,
                "executed_qty": executed_qty,
                "created_at": created_at,
                "updated_at": updated_at,
                "already_booked": False,
            }
        except BinanceAPIException as e:
            # Log error but don't book order if exchange placement failed
            import logging
            logging.error(f"Order placement failed: {e}")
            raise

    def cancel_order(
        self,
        symbol: str,
        ledger_order_id: Optional[int] = None,
        exchange_order_id: Optional[str] = None,
        book_id: str = "default",
    ) -> Dict[str, Any]:
        """Cancel order on exchange and update ledger status.
        
        Args:
            symbol: Trading pair
            ledger_order_id: Ledger order ID (used to resolve exchange_order_id if provided)
            exchange_order_id: Exchange order ID (used directly if provided)
            book_id: Book identifier
            
        Returns:
            Dict with cancellation result
        """
        # Resolve exchange_order_id
        if exchange_order_id is None:
            if ledger_order_id is None:
                raise ValueError("Either ledger_order_id or exchange_order_id must be provided")
            orders = self._ledger.get_orders(limit=1)
            order = next((o for o in orders if o["id"] == ledger_order_id), None)
            if not order:
                raise ValueError(f"Order {ledger_order_id} not found")
            exchange_order_id = order["exchange_order_id"]
            if not exchange_order_id:
                raise ValueError(f"Order {ledger_order_id} has no exchange_order_id")
        
        # Cancel on exchange
        response = self._order_manager.cancel(symbol=symbol, order_id=int(exchange_order_id))
        
        # Extract status from response
        status = response.get("status", "").upper()
        if not status:
            status = "CANCELED"
        
        # Update ledger order status
        if ledger_order_id is None:
            order = self._ledger.get_order_by_exchange_id(
                venue=self._venue,
                exchange_order_id=exchange_order_id,
                book_id=book_id,
            )
            if order:
                ledger_order_id = order["id"]
        
        if ledger_order_id:
            self._ledger.update_order_status(
                ledger_order_id=ledger_order_id,
                status=status,
                reason="Order canceled via orchestrator",
            )
        
        return {
            "ledger_order_id": ledger_order_id,
            "exchange_order_id": exchange_order_id,
            "status": status,
            "symbol": symbol,
        }

    def sync_fills_for_order(
        self,
        symbol: str,
        exchange_order_id: str,
        ledger_order_id: int,
        book_id: str = "default",
    ) -> List[int]:
        """Sync fills (trades) for a specific order from exchange and book them.
        
        Args:
            symbol: Trading pair
            exchange_order_id: Exchange order ID
            ledger_order_id: Ledger order ID
            book_id: Book identifier
            
        Returns:
            List of ledger trade IDs
        """
        # Get fills from exchange (filter by orderId)
        fills = self._order_manager.get_fills(symbol=symbol, orderId=int(exchange_order_id))
        # Filter fills by orderId (Binance API may return all trades, filter client-side)
        fills = [f for f in fills if str(f.get("orderId", "")) == exchange_order_id]
        
        ledger_trade_ids = []
        for fill in fills:
            # Extract fields from Binance trade response
            exchange_trade_id = str(fill.get("id", ""))
            side = fill.get("side", "").upper()
            quantity = float(fill.get("qty", "0"))
            price = float(fill.get("price", "0"))
            commission = float(fill.get("commission", "0"))
            commission_asset = fill.get("commissionAsset")
            traded_at = fill.get("time", 0)
            
            # Idempotency check
            existing_trades = self._ledger.get_trades(
                venue=self._venue,
                book_id=book_id,
                exchange_trade_id=exchange_trade_id,
            )
            if existing_trades:
                ledger_trade_ids.append(existing_trades[0]["id"])
                continue
            
            # Book trade
            trade_id = self._ledger.record_trade(
                venue=self._venue,
                book_id=book_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                traded_at=traded_at,
                exchange_trade_id=exchange_trade_id,
                order_id=ledger_order_id,
                commission=commission,
                commission_asset=commission_asset,
            )
            ledger_trade_ids.append(trade_id)
        
        return ledger_trade_ids

    def sync_fills_for_symbol(
        self,
        symbol: str,
        book_id: Optional[str] = None,
        since: Optional[int] = None,
        limit: int = 100,
    ) -> List[int]:
        """Sync fills for unfilled orders of a symbol from exchange and book them.
        
        Order-driven approach:
        1. Find unfilled orders (NEW or PARTIALLY_FILLED) for the symbol
        2. For each order, fetch trades from Binance using orderId filter
        3. Compare trade IDs with existing trades to find new fills
        4. Record new trades (order status automatically updated)
        
        Args:
            symbol: Trading pair
            book_id: Optional book identifier filter (None = all books)
            since: Start timestamp in milliseconds (optional, for Binance API)
            limit: Maximum number of trades to fetch per order
            
        Returns:
            List of ledger trade IDs for newly recorded trades
        """
        # Get unfilled orders for this symbol
        unfilled_statuses = ["NEW", "PARTIALLY_FILLED"]
        unfilled_orders = []
        for status in unfilled_statuses:
            orders = self._ledger.get_orders(
                symbol=symbol,
                venue=self._venue,
                book_id=book_id,
                status=status,
            )
            unfilled_orders.extend(orders)
        
        if not unfilled_orders:
            logger.debug(f"No unfilled orders found for {symbol}")
            return []
        
        logger.info(f"Found {len(unfilled_orders)} unfilled orders for {symbol}")
        
        ledger_trade_ids = []
        
        # Process each unfilled order
        for order in unfilled_orders:
            order_id = order["id"]
            exchange_order_id = order["exchange_order_id"]
            order_book_id = order["book_id"]
            order_side = order["side"]
            
            try:
                # Fetch trades for this specific order from Binance
                # Binance API supports orderId filter (more efficient: 5 weight vs 20)
                kwargs: Dict[str, Any] = {
                    "limit": limit,
                    "orderId": int(exchange_order_id),  # Binance API filter by orderId (camelCase)
                }
                if since:
                    kwargs["startTime"] = since
                
                try:
                    binance_trades = self._order_manager.get_fills(symbol=symbol, **kwargs)
                except Exception as api_error:
                    # Handle case where orderId might be invalid (order cancelled, doesn't exist, etc.)
                    error_msg = str(api_error).lower()
                    if "invalid" in error_msg or "not found" in error_msg or "-2013" in error_msg:
                        logger.debug(
                            f"Order {exchange_order_id} not found or invalid on exchange "
                            f"(may have been cancelled or doesn't exist): {api_error}"
                        )
                        # Order might have been cancelled externally - skip it
                        continue
                    raise  # Re-raise if it's a different error
                
                if not binance_trades:
                    continue
                
                # Get existing trades for this order from ledger
                existing_trades = self._ledger.get_trades(
                    venue=self._venue,
                    book_id=order_book_id,
                    order_id=order_id,
                )
                existing_trade_ids = {t["exchange_trade_id"] for t in existing_trades}
                
                # Process each trade from Binance
                for trade in binance_trades:
                    exchange_trade_id = str(trade.get("id", ""))
                    
                    # Skip if we already have this trade
                    if exchange_trade_id in existing_trade_ids:
                        continue
                    
                    # Extract trade fields
                    # Try multiple ways to get side (Binance API varies by endpoint)
                    side = trade.get("side", "").upper() if trade.get("side") else ""
                    if not side:
                        # For futures, might have isBuyer field
                        is_buyer = trade.get("isBuyer")
                        if is_buyer is not None:
                            side = "BUY" if is_buyer else "SELL"
                        else:
                            # Fall back to order side if trade doesn't have it
                            side = order_side.upper()
                    
                    quantity = float(trade.get("qty", trade.get("quantity", "0")))
                    price = float(trade.get("price", "0"))
                    commission = float(trade.get("commission", "0"))
                    commission_asset = trade.get("commissionAsset")
                    traded_at = trade.get("time", 0)
                    
                    # Record the trade (order status will be auto-updated)
                    trade_id = self._ledger.record_trade(
                        venue=self._venue,
                        book_id=order_book_id,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        price=price,
                        traded_at=traded_at,
                        exchange_trade_id=exchange_trade_id,
                        order_id=order_id,
                        commission=commission,
                        commission_asset=commission_asset,
                    )
                    ledger_trade_ids.append(trade_id)
                    logger.debug(
                        f"Recorded new fill: trade_id={trade_id}, order_id={order_id}, "
                        f"exchange_trade_id={exchange_trade_id}"
                    )
                
            except Exception as e:
                logger.warning(
                    f"Error syncing fills for order {order_id} (exchange_order_id={exchange_order_id}): {e}",
                    exc_info=True,
                )
                continue
        
        return ledger_trade_ids
