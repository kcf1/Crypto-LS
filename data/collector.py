"""Raw data ingestion from Binance (REST klines and futures). Output: raw OHLCV and futures data."""

import logging
from typing import Any, Dict, List, Optional

import requests

from config import settings
from data.futures_auth import add_auth_params, get_auth_headers

logger = logging.getLogger(__name__)

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TESTNET_KLINES_URL = "https://testnet.binance.vision/api/v3/klines"

# Futures API endpoints (USDT-Margined)
BINANCE_FAPI_BASE = "https://fapi.binance.com"
BINANCE_FAPI_TESTNET_BASE = "https://testnet.binancefuture.com"


class Collector:
    """Ingest raw OHLCV and futures data from Binance public REST."""

    def __init__(
        self,
        use_testnet: bool = True,
        limit_per_request: Optional[int] = None,
    ) -> None:
        self._base = BINANCE_TESTNET_KLINES_URL if use_testnet else BINANCE_KLINES_URL
        self._fapi_base = BINANCE_FAPI_TESTNET_BASE if use_testnet else BINANCE_FAPI_BASE
        self._limit = limit_per_request or settings.ohlcv_limit_per_request
        self._use_testnet = use_testnet

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[tuple]:
        """
        Fetch raw klines (OHLCV). Returns list of tuples:
        (open_time, open, high, low, close, volume, close_time).
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit or self._limit,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        try:
            resp = requests.get(self._base, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            # Binance kline: [open_time, open, high, low, close, volume, close_time, ...]
            rows = [
                (
                    int(c[0]),
                    float(c[1]),
                    float(c[2]),
                    float(c[3]),
                    float(c[4]),
                    float(c[5]),
                    int(c[6]),
                )
                for c in raw
            ]
            logger.debug(
                "fetch_klines %s %s: %s rows",
                symbol,
                interval,
                len(rows),
            )
            return rows
        except Exception as e:
            logger.warning(
                "fetch_klines failed %s %s: %s",
                symbol,
                interval,
                e,
                exc_info=True,
            )
            raise

    def fetch_funding_rate(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[tuple]:
        """
        Fetch funding rate history from Binance Futures API.
        Returns list of tuples: (funding_time, funding_rate, mark_price).
        """
        url = f"{self._fapi_base}/fapi/v1/fundingRate"
        params: dict[str, Any] = {
            "symbol": symbol,
            "limit": limit or self._limit,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            # Binance funding rate: [funding_time, funding_rate, mark_price]
            rows = [
                (
                    int(r["fundingTime"]),
                    float(r["fundingRate"]),
                    float(r["markPrice"]),
                )
                for r in raw
            ]
            logger.debug("fetch_funding_rate %s: %s rows", symbol, len(rows))
            return rows
        except Exception as e:
            logger.warning(
                "fetch_funding_rate failed %s: %s",
                symbol,
                e,
                exc_info=True,
            )
            raise

    def fetch_open_interest_hist(
        self,
        symbol: str,
        period: str,  # "5m", "15m", "1h", etc.
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[tuple]:
        """
        Fetch open interest history from Binance Futures API.
        Returns list of tuples: (timestamp, sum_open_interest, sum_open_interest_value).
        """
        url = f"{self._fapi_base}/futures/data/openInterestHist"
        params: dict[str, Any] = {
            "symbol": symbol,
            "period": period,
            "limit": limit or min(500, self._limit),  # Max 500 for this endpoint
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            # Binance open interest: [timestamp, sumOpenInterest, sumOpenInterestValue]
            rows = [
                (
                    int(r["timestamp"]),
                    float(r["sumOpenInterest"]),
                    float(r["sumOpenInterestValue"]),
                )
                for r in raw
            ]
            logger.debug("fetch_open_interest_hist %s %s: %s rows", symbol, period, len(rows))
            return rows
        except Exception as e:
            logger.warning(
                "fetch_open_interest_hist failed %s %s: %s",
                symbol,
                period,
                e,
                exc_info=True,
            )
            raise

    def fetch_force_orders(
        self,
        symbol: Optional[str] = None,
        auto_close_type: Optional[str] = None,  # "LIQUIDATION" or "ADL"
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch liquidation orders from Binance Futures API.
        Requires API key authentication.
        Returns list of dictionaries with liquidation order data.
        """
        from config import secrets
        
        if not secrets.binance_data_api_key or not secrets.binance_data_api_secret:
            raise ValueError("API key and secret required for fetch_force_orders")
        
        url = f"{self._fapi_base}/fapi/v1/forceOrders"
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = symbol
        if auto_close_type is not None:
            params["autoCloseType"] = auto_close_type
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if limit is not None:
            params["limit"] = min(limit, 100)  # Max 100 for this endpoint
        else:
            params["limit"] = 100
        
        # Add authentication
        params = add_auth_params(params)
        headers = get_auth_headers()
        
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            logger.debug("fetch_force_orders %s: %s rows", symbol or "all", len(raw))
            return raw
        except Exception as e:
            logger.warning(
                "fetch_force_orders failed %s: %s",
                symbol or "all",
                e,
                exc_info=True,
            )
            raise
