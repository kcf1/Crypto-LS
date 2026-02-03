"""Raw data ingestion from CoinGecko API. Output: market cap and related market data."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"

# Retry when rate limit (429) is reached
DEFAULT_RETRY_AFTER_SEC = 60
MAX_429_RETRIES = 5


def midnight_utc_today_ms() -> int:
    """Return start of today (midnight) in UTC as milliseconds since epoch. Use for daily snapshots to avoid duplicates."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp() * 1000)


class CoinGeckoCollector:
    """Ingest raw market cap data from CoinGecko public REST API."""

    def __init__(self, delay_sec: float = 1.0) -> None:
        """
        Initialize CoinGecko collector.
        
        Args:
            delay_sec: Delay between API requests (default 1.0s to respect free tier rate limits)
        """
        self._base = COINGECKO_API_BASE
        self._delay_sec = delay_sec

    def _binance_to_coingecko_symbol(self, binance_symbol: str) -> str:
        """
        Convert Binance symbol to CoinGecko symbol.
        
        Example: BTCUSDT -> btc
        """
        # Remove USDT suffix and convert to lowercase
        base = binance_symbol.replace("USDT", "").lower()
        return base

    def _get_with_retry(self, url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        """GET request with retry on 429 (rate limit). Sleeps Retry-After seconds then retries up to MAX_429_RETRIES."""
        for attempt in range(MAX_429_RETRIES):
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                if attempt < MAX_429_RETRIES - 1:
                    retry_after = int(resp.headers.get("Retry-After", DEFAULT_RETRY_AFTER_SEC))
                    logger.warning(
                        "429 rate limit, sleeping %s s (attempt %s/%s)",
                        retry_after,
                        attempt + 1,
                        MAX_429_RETRIES,
                    )
                    time.sleep(retry_after)
                    continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()  # unreachable but for type safety
        return resp

    def fetch_coins_list(self) -> List[Dict[str, Any]]:
        """
        Fetch all coins list from CoinGecko.
        
        Returns list of dicts with keys: id, symbol, name
        This can be cached as it rarely changes.
        """
        url = f"{self._base}/coins/list"
        try:
            resp = self._get_with_retry(url)
            coins = resp.json()
            logger.debug("fetch_coins_list: fetched %s coins", len(coins))
            return coins
        except Exception as e:
            logger.warning("fetch_coins_list failed: %s", e, exc_info=True)
            raise

    def fetch_market_cap(
        self,
        symbols: List[str],
        vs_currency: str = "usd",
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Fetch current market cap data for multiple symbols.
        
        Args:
            symbols: List of Binance symbols (e.g., ["BTCUSDT", "ETHUSDT"])
            vs_currency: Target currency (default: "usd")
        
        Returns:
            List of tuples: (binance_symbol, market_data_dict)
            Each market_data_dict contains all fields from CoinGecko /coins/markets endpoint
        """
        if not symbols:
            return []
        
        # Convert Binance symbols to CoinGecko symbols
        coingecko_symbols = [self._binance_to_coingecko_symbol(s) for s in symbols]
        # CoinGecko accepts max 50 symbols per request
        max_per_request = 50
        
        results = []
        for i in range(0, len(coingecko_symbols), max_per_request):
            batch_symbols = coingecko_symbols[i:i + max_per_request]
            batch_binance = symbols[i:i + max_per_request]
            
            url = f"{self._base}/coins/markets"
            params: Dict[str, Any] = {
                "vs_currency": vs_currency,
                "symbols": ",".join(batch_symbols),
                "order": "market_cap_desc",
                "per_page": len(batch_symbols),
                "page": 1,
            }
            
            try:
                resp = self._get_with_retry(url, params)
                market_data = resp.json()
                
                if not isinstance(market_data, list):
                    logger.warning("fetch_market_cap: invalid response format for symbols %s", batch_symbols)
                    continue
                
                # Create mapping from CoinGecko symbol to Binance symbol
                symbol_map = {cg_sym: bin_sym for cg_sym, bin_sym in zip(batch_symbols, batch_binance)}
                
                # Match returned data to Binance symbols
                for item in market_data:
                    cg_symbol = item.get("symbol", "").lower()
                    if cg_symbol in symbol_map:
                        binance_symbol = symbol_map[cg_symbol]
                        results.append((binance_symbol, item))
                    else:
                        logger.debug("fetch_market_cap: CoinGecko symbol %s not in batch", cg_symbol)
                
                logger.debug(
                    "fetch_market_cap: fetched %s records for batch %s/%s",
                    len(market_data),
                    i // max_per_request + 1,
                    (len(coingecko_symbols) + max_per_request - 1) // max_per_request,
                )
                
                # Respect rate limits
                if i + max_per_request < len(coingecko_symbols):
                    time.sleep(self._delay_sec)
                    
            except Exception as e:
                logger.warning("fetch_market_cap failed for batch %s: %s", batch_symbols, e, exc_info=True)
                raise
        
        return results

    def fetch_historical_market_cap(
        self,
        coin_id: str,
        date: str,
        vs_currency: str = "usd",
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch historical market cap data for a specific date.
        
        Args:
            coin_id: CoinGecko coin ID (e.g., "bitcoin")
            date: Date in format "dd-mm-yyyy" (e.g., "29-01-2026")
            vs_currency: Target currency (default: "usd")
        
        Returns:
            Dict with historical market data, or None if not found
        """
        url = f"{self._base}/coins/{coin_id}/history"
        params: Dict[str, Any] = {
            "date": date,
            "localization": "false",
        }
        
        try:
            resp = self._get_with_retry(url, params)
            data = resp.json()
            
            if "market_data" not in data:
                logger.warning("fetch_historical_market_cap: no market_data for %s on %s", coin_id, date)
                return None
            
            market_data = data["market_data"]
            
            # Extract relevant fields
            result = {
                "id": data.get("id"),
                "symbol": data.get("symbol", "").lower(),
                "name": data.get("name"),
                "current_price": market_data.get("current_price", {}).get(vs_currency),
                "market_cap": market_data.get("market_cap", {}).get(vs_currency),
                "market_cap_rank": market_data.get("market_cap_rank"),
                "fully_diluted_valuation": market_data.get("fully_diluted_valuation", {}).get(vs_currency),
                "total_volume": market_data.get("total_volume", {}).get(vs_currency),
                "high_24h": market_data.get("high_24h", {}).get(vs_currency),
                "low_24h": market_data.get("low_24h", {}).get(vs_currency),
                "price_change_24h": market_data.get("price_change_24h", {}).get(vs_currency),
                "price_change_percentage_24h": market_data.get("price_change_percentage_24h", {}).get(vs_currency),
                "market_cap_change_24h": market_data.get("market_cap_change_24h", {}).get(vs_currency),
                "market_cap_change_percentage_24h": market_data.get("market_cap_change_percentage_24h", {}).get(vs_currency),
                "circulating_supply": market_data.get("circulating_supply"),
                "total_supply": market_data.get("total_supply"),
                "max_supply": market_data.get("max_supply"),
            }
            
            logger.debug("fetch_historical_market_cap: fetched data for %s on %s", coin_id, date)
            return result
            
        except Exception as e:
            logger.warning("fetch_historical_market_cap failed for %s on %s: %s", coin_id, date, e, exc_info=True)
            raise

    def market_data_to_tuple(
        self,
        market_data: Dict[str, Any],
        timestamp: int,
    ) -> tuple:
        """
        Convert CoinGecko market data dict to tuple format for storage.
        
        Returns tuple: (timestamp, market_cap, circulating_supply, total_supply, max_supply,
                       market_cap_rank, fully_diluted_valuation, current_price, total_volume,
                       high_24h, low_24h, price_change_24h, price_change_percentage_24h,
                       market_cap_change_24h, market_cap_change_percentage_24h)
        """
        return (
            timestamp,
            float(market_data.get("market_cap") or 0),
            float(market_data.get("circulating_supply") or 0),
            float(market_data.get("total_supply") or 0),
            float(market_data.get("max_supply")) if market_data.get("max_supply") is not None else None,
            int(market_data.get("market_cap_rank")) if market_data.get("market_cap_rank") is not None else None,
            float(market_data.get("fully_diluted_valuation") or 0) if market_data.get("fully_diluted_valuation") is not None else None,
            float(market_data.get("current_price") or 0),
            float(market_data.get("total_volume") or 0),
            float(market_data.get("high_24h")) if market_data.get("high_24h") is not None else None,
            float(market_data.get("low_24h")) if market_data.get("low_24h") is not None else None,
            float(market_data.get("price_change_24h")) if market_data.get("price_change_24h") is not None else None,
            float(market_data.get("price_change_percentage_24h")) if market_data.get("price_change_percentage_24h") is not None else None,
            float(market_data.get("market_cap_change_24h")) if market_data.get("market_cap_change_24h") is not None else None,
            float(market_data.get("market_cap_change_percentage_24h")) if market_data.get("market_cap_change_percentage_24h") is not None else None,
        )
