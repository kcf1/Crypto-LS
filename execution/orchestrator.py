"""Booking orchestrator: integrates order execution with booking ledger."""

from typing import Any, Dict, List, Optional

from binance.exceptions import BinanceAPIException

from booking.ledger import Ledger
from config import settings
from execution.order_manager import OrderManager


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
        book_id: str = "default",
        since: Optional[int] = None,
        limit: int = 100,
    ) -> List[int]:
        """Sync all fills for a symbol from exchange and book them.
        
        Args:
            symbol: Trading pair
            book_id: Book identifier
            since: Start timestamp in milliseconds (optional)
            limit: Maximum number of trades to fetch
            
        Returns:
            List of ledger trade IDs
        """
        # Get trades from exchange
        kwargs: Dict[str, Any] = {"limit": limit}
        if since:
            kwargs["startTime"] = since
        
        trades = self._order_manager.get_my_trades(symbol=symbol, **kwargs)
        
        ledger_trade_ids = []
        for trade in trades:
            # Extract fields
            exchange_trade_id = str(trade.get("id", ""))
            side = trade.get("side", "").upper()
            quantity = float(trade.get("qty", "0"))
            price = float(trade.get("price", "0"))
            commission = float(trade.get("commission", "0"))
            commission_asset = trade.get("commissionAsset")
            traded_at = trade.get("time", 0)
            order_id_from_exchange = trade.get("orderId")
            
            # Idempotency check
            existing_trades = self._ledger.get_trades(
                venue=self._venue,
                book_id=book_id,
                exchange_trade_id=exchange_trade_id,
            )
            if existing_trades:
                ledger_trade_ids.append(existing_trades[0]["id"])
                continue
            
            # Resolve ledger order_id from exchange order_id
            ledger_order_id = None
            if order_id_from_exchange:
                order = self._ledger.get_order_by_exchange_id(
                    venue=self._venue,
                    exchange_order_id=str(order_id_from_exchange),
                    book_id=book_id,
                )
                if order:
                    ledger_order_id = order["id"]
            
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
