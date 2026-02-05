"""Order lifecycle: submit, cancel, status, fills. Uses Binance client (and later other execution modules)."""

from typing import Any, Optional

from config import settings
from execution.binance.client import BinanceClient


class OrderManager:
    """Submit/cancel orders and query status/fills via execution clients."""

    def __init__(self, binance_client: Optional[BinanceClient] = None) -> None:
        # Use testnet for orders if configured, otherwise use default
        if binance_client is None:
            binance_client = BinanceClient(use_testnet=settings.use_testnet_for_orders)
        self._binance = binance_client

    def submit_market(
        self,
        symbol: str,
        side: str,
        quantity: Optional[float] = None,
        quote_order_qty: Optional[float] = None,
    ) -> dict:
        """Submit market order. Provide quantity in base or quote_order_qty in quote."""
        return self._binance.create_order(
            symbol=symbol,
            side=side,
            order_type="MARKET",
            quantity=quantity,
            quote_order_qty=quote_order_qty,
        )

    def submit_limit(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC",
    ) -> dict:
        """Submit limit order."""
        return self._binance.create_order(
            symbol=symbol,
            side=side,
            order_type="LIMIT",
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
        )

    def cancel(self, symbol: str, order_id: int) -> dict:
        """Cancel order by id."""
        return self._binance.cancel_order(symbol=symbol, order_id=order_id)

    def status(self, symbol: str, order_id: int) -> dict:
        """Get order status."""
        return self._binance.get_order(symbol=symbol, order_id=order_id)

    def get_fills(self, symbol: str, order_id: Optional[int] = None, **kwargs: Any) -> list:
        """Get fills (trades) for symbol. Optional order_id filter via kwargs."""
        return self._binance.get_my_trades(symbol=symbol, **kwargs)

    def open_orders(self, symbol: Optional[str] = None) -> list:
        """Get open orders, optionally for one symbol."""
        return self._binance.get_open_orders(symbol=symbol)
