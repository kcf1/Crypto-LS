"""Binance-specific client: auth, rate limits, REST. Used by collector and order placement."""

from typing import Any, Optional

from binance.client import Client as BinanceApiClient
from binance.exceptions import BinanceAPIException

from config import secrets, settings


def _format_decimal(value: float, max_decimals: int = 20) -> str:
    """Format number as string without scientific notation (Binance rejects e.g. 1e-05)."""
    s = f"{value:.{max_decimals}f}".rstrip("0").rstrip(".")
    return s


class BinanceClient:
    """Thin wrapper around python-binance Client with config-driven auth and testnet."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        use_testnet: Optional[bool] = None,
    ) -> None:
        use_testnet = use_testnet if use_testnet is not None else settings.use_testnet
        if use_testnet:
            key = api_key or secrets.binance_testnet_api_key
            sec = api_secret or secrets.binance_testnet_api_secret
        else:
            # Use trading API key for order management (falls back to legacy key)
            key = api_key or secrets.binance_trading_api_key
            sec = api_secret or secrets.binance_trading_api_secret
        self._client = BinanceApiClient(key, sec, testnet=use_testnet)
        self._use_testnet = use_testnet

    @property
    def client(self) -> BinanceApiClient:
        """Raw Binance API client for advanced use."""
        return self._client

    def get_account(self) -> dict:
        """Return account info (balances, etc.)."""
        return self._client.get_account()

    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Optional[float] = None,
        quote_order_qty: Optional[float] = None,
        price: Optional[float] = None,
        time_in_force: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        """Place order. See Binance API for params (quantity, price, timeInForce, etc.)."""
        params: dict = {"symbol": symbol, "side": side.upper(), "type": order_type.upper()}
        if quantity is not None:
            params["quantity"] = _format_decimal(float(quantity))
        if quote_order_qty is not None:
            params["quoteOrderQty"] = _format_decimal(float(quote_order_qty))
        if price is not None:
            params["price"] = _format_decimal(float(price))
        if time_in_force is not None:
            params["timeInForce"] = time_in_force
        params.update(kwargs)
        return self._client.create_order(**params)

    def get_order(self, symbol: str, order_id: int) -> dict:
        """Get order by id."""
        return self._client.get_order(symbol=symbol, orderId=order_id)  # noqa: N803

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel order."""
        return self._client.cancel_order(symbol=symbol, orderId=order_id)  # noqa: N803

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Get open orders, optionally filtered by symbol."""
        return self._client.get_open_orders(symbol=symbol or "")

    def get_my_trades(self, symbol: str, **kwargs: Any) -> list:
        """Get trades for symbol (fills)."""
        return self._client.get_my_trades(symbol=symbol, **kwargs)
