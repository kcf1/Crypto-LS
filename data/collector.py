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
            
            # Handle empty or invalid responses (could be due to rate limits)
            if not isinstance(raw, list):
                logger.warning("fetch_funding_rate %s: invalid response format: %s", symbol, type(raw))
                return []
            
            if not raw:
                logger.debug("fetch_funding_rate %s: empty response (may be rate limited)", symbol)
                return []
            
            # Binance funding rate: [funding_time, funding_rate, mark_price]
            # Handle empty strings by converting to None, then to 0.0 if needed
            rows = []
            for r in raw:
                try:
                    # Skip if missing required fields
                    if "fundingTime" not in r:
                        logger.warning("Skipping row missing fundingTime: %s", r)
                        continue
                    
                    funding_rate_str = r.get("fundingRate", "")
                    mark_price_str = r.get("markPrice", "")
                    
                    # Convert empty strings to 0.0
                    funding_rate = float(funding_rate_str) if funding_rate_str and funding_rate_str.strip() else 0.0
                    mark_price = float(mark_price_str) if mark_price_str and mark_price_str.strip() else 0.0
                    
                    rows.append(
                        (
                            int(r["fundingTime"]),
                            funding_rate,
                            mark_price,
                        )
                    )
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(
                        "Skipping invalid funding rate row for %s: %s (error: %s)",
                        symbol,
                        r,
                        e,
                    )
                    continue
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
            
            # Handle empty or invalid responses (could be due to rate limits)
            if not isinstance(raw, list):
                logger.warning("fetch_open_interest_hist %s %s: invalid response format: %s", symbol, period, type(raw))
                return []
            
            if not raw:
                logger.debug("fetch_open_interest_hist %s %s: empty response (may be rate limited)", symbol, period)
                return []
            
            # Binance open interest: list of dicts with timestamp, sumOpenInterest, sumOpenInterestValue
            rows = []
            for r in raw:
                try:
                    # Skip if missing required fields
                    if not isinstance(r, dict) or "timestamp" not in r:
                        logger.warning("Skipping invalid open interest row: %s", r)
                        continue
                    
                    timestamp_val = r.get("timestamp")
                    oi_val = r.get("sumOpenInterest", "")
                    oi_value_val = r.get("sumOpenInterestValue", "")
                    
                    # Convert empty strings/None to 0.0
                    timestamp = int(timestamp_val) if timestamp_val else 0
                    sum_open_interest = float(oi_val) if oi_val and str(oi_val).strip() else 0.0
                    sum_open_interest_value = float(oi_value_val) if oi_value_val and str(oi_value_val).strip() else 0.0
                    
                    rows.append(
                        (
                            timestamp,
                            sum_open_interest,
                            sum_open_interest_value,
                        )
                    )
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(
                        "Skipping invalid open interest row for %s %s: %s (error: %s)",
                        symbol,
                        period,
                        r,
                        e,
                    )
                    continue
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

    def fetch_basis(
        self,
        symbol: str,  # API uses "pair" but we'll map symbol to pair
        period: str,  # "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[tuple]:
        """
        Fetch basis (premium index) data from Binance Futures API.
        Returns list of tuples: (timestamp, basis_rate, basis, futures_price, index_price).
        """
        url = f"{self._fapi_base}/futures/data/basis"
        params: dict[str, Any] = {
            "pair": symbol,  # API uses "pair" parameter
            "contractType": "PERPETUAL",
            "period": period,
            "limit": limit or min(500, self._limit),  # Max 500
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            
            if not isinstance(raw, list):
                logger.warning("fetch_basis %s %s: invalid response format: %s", symbol, period, type(raw))
                return []
            
            if not raw:
                logger.debug("fetch_basis %s %s: empty response", symbol, period)
                return []
            
            rows = []
            for r in raw:
                try:
                    if not isinstance(r, dict) or "timestamp" not in r:
                        logger.warning("Skipping invalid basis row: %s", r)
                        continue
                    
                    rows.append((
                        int(r["timestamp"]),
                        float(r.get("basisRate", 0.0) or 0.0),
                        float(r.get("basis", 0.0) or 0.0),
                        float(r.get("futuresPrice", 0.0) or 0.0),
                        float(r.get("indexPrice", 0.0) or 0.0),
                    ))
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning("Skipping invalid basis row for %s %s: %s (error: %s)", symbol, period, r, e)
                    continue
            logger.debug("fetch_basis %s %s: %s rows", symbol, period, len(rows))
            return rows
        except Exception as e:
            logger.warning("fetch_basis failed %s %s: %s", symbol, period, e, exc_info=True)
            raise

    def fetch_global_long_short_account(
        self,
        symbol: str,
        period: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[tuple]:
        """
        Fetch global long/short account ratio from Binance Futures API.
        Returns list of tuples: (timestamp, long_short_ratio, long_account, short_account).
        """
        url = f"{self._fapi_base}/futures/data/globalLongShortAccountRatio"
        params: dict[str, Any] = {
            "symbol": symbol,
            "period": period,
            "limit": limit or min(500, self._limit),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            
            if not isinstance(raw, list):
                logger.warning("fetch_global_long_short_account %s %s: invalid response format: %s", symbol, period, type(raw))
                return []
            
            if not raw:
                logger.debug("fetch_global_long_short_account %s %s: empty response", symbol, period)
                return []
            
            rows = []
            for r in raw:
                try:
                    if not isinstance(r, dict) or "timestamp" not in r:
                        logger.warning("Skipping invalid global_long_short_account row: %s", r)
                        continue
                    
                    rows.append((
                        int(r["timestamp"]),
                        float(r.get("longShortRatio", 0.0) or 0.0),
                        float(r.get("longAccount", 0.0) or 0.0),
                        float(r.get("shortAccount", 0.0) or 0.0),
                    ))
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning("Skipping invalid global_long_short_account row for %s %s: %s (error: %s)", symbol, period, r, e)
                    continue
            logger.debug("fetch_global_long_short_account %s %s: %s rows", symbol, period, len(rows))
            return rows
        except Exception as e:
            logger.warning("fetch_global_long_short_account failed %s %s: %s", symbol, period, e, exc_info=True)
            raise

    def fetch_top_long_short_account(
        self,
        symbol: str,
        period: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[tuple]:
        """
        Fetch top trader long/short account ratio from Binance Futures API.
        Returns list of tuples: (timestamp, long_short_ratio, long_account, short_account).
        """
        url = f"{self._fapi_base}/futures/data/topLongShortAccountRatio"
        params: dict[str, Any] = {
            "symbol": symbol,
            "period": period,
            "limit": limit or min(500, self._limit),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            
            if not isinstance(raw, list):
                logger.warning("fetch_top_long_short_account %s %s: invalid response format: %s", symbol, period, type(raw))
                return []
            
            if not raw:
                logger.debug("fetch_top_long_short_account %s %s: empty response", symbol, period)
                return []
            
            rows = []
            for r in raw:
                try:
                    if not isinstance(r, dict) or "timestamp" not in r:
                        logger.warning("Skipping invalid top_long_short_account row: %s", r)
                        continue
                    
                    rows.append((
                        int(r["timestamp"]),
                        float(r.get("longShortRatio", 0.0) or 0.0),
                        float(r.get("longAccount", 0.0) or 0.0),
                        float(r.get("shortAccount", 0.0) or 0.0),
                    ))
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning("Skipping invalid top_long_short_account row for %s %s: %s (error: %s)", symbol, period, r, e)
                    continue
            logger.debug("fetch_top_long_short_account %s %s: %s rows", symbol, period, len(rows))
            return rows
        except Exception as e:
            logger.warning("fetch_top_long_short_account failed %s %s: %s", symbol, period, e, exc_info=True)
            raise

    def fetch_top_long_short_position(
        self,
        symbol: str,
        period: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[tuple]:
        """
        Fetch top trader long/short position ratio from Binance Futures API.
        Returns list of tuples: (timestamp, long_short_ratio, long_position, short_position).
        """
        url = f"{self._fapi_base}/futures/data/topLongShortPositionRatio"
        params: dict[str, Any] = {
            "symbol": symbol,
            "period": period,
            "limit": limit or min(500, self._limit),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            
            if not isinstance(raw, list):
                logger.warning("fetch_top_long_short_position %s %s: invalid response format: %s", symbol, period, type(raw))
                return []
            
            if not raw:
                logger.debug("fetch_top_long_short_position %s %s: empty response", symbol, period)
                return []
            
            rows = []
            for r in raw:
                try:
                    if not isinstance(r, dict) or "timestamp" not in r:
                        logger.warning("Skipping invalid top_long_short_position row: %s", r)
                        continue
                    
                    rows.append((
                        int(r["timestamp"]),
                        float(r.get("longShortRatio", 0.0) or 0.0),
                        float(r.get("longPosition", 0.0) or 0.0),
                        float(r.get("shortPosition", 0.0) or 0.0),
                    ))
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning("Skipping invalid top_long_short_position row for %s %s: %s (error: %s)", symbol, period, r, e)
                    continue
            logger.debug("fetch_top_long_short_position %s %s: %s rows", symbol, period, len(rows))
            return rows
        except Exception as e:
            logger.warning("fetch_top_long_short_position failed %s %s: %s", symbol, period, e, exc_info=True)
            raise

    def fetch_taker_buy_sell_vol(
        self,
        symbol: str,
        period: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[tuple]:
        """
        Fetch taker buy/sell volume from Binance Futures API.
        Returns list of tuples: (timestamp, buy_sell_ratio, buy_vol, sell_vol, buy_vol_value, sell_vol_value).
        """
        url = f"{self._fapi_base}/futures/data/takerBuySellVol"
        params: dict[str, Any] = {
            "symbol": symbol,
            "period": period,
            "limit": limit or min(500, self._limit),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            
            if not isinstance(raw, list):
                logger.warning("fetch_taker_buy_sell_vol %s %s: invalid response format: %s", symbol, period, type(raw))
                return []
            
            if not raw:
                logger.debug("fetch_taker_buy_sell_vol %s %s: empty response", symbol, period)
                return []
            
            rows = []
            for r in raw:
                try:
                    if not isinstance(r, dict) or "timestamp" not in r:
                        logger.warning("Skipping invalid taker_buy_sell_vol row: %s", r)
                        continue
                    
                    rows.append((
                        int(r["timestamp"]),
                        float(r.get("buySellRatio", 0.0) or 0.0),
                        float(r.get("buyVol", 0.0) or 0.0),
                        float(r.get("sellVol", 0.0) or 0.0),
                        float(r.get("buyVolValue", 0.0) or 0.0),
                        float(r.get("sellVolValue", 0.0) or 0.0),
                    ))
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning("Skipping invalid taker_buy_sell_vol row for %s %s: %s (error: %s)", symbol, period, r, e)
                    continue
            logger.debug("fetch_taker_buy_sell_vol %s %s: %s rows", symbol, period, len(rows))
            return rows
        except Exception as e:
            logger.warning("fetch_taker_buy_sell_vol failed %s %s: %s", symbol, period, e, exc_info=True)
            raise
