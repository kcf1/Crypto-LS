"""Raw data ingestion from Binance (REST klines). Output: raw OHLCV; no indicator logic."""

import logging
from typing import Any, List, Optional

import requests

from config import settings

logger = logging.getLogger(__name__)

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TESTNET_KLINES_URL = "https://testnet.binance.vision/api/v3/klines"


class Collector:
    """Ingest raw OHLCV from Binance public REST. No auth required for klines."""

    def __init__(
        self,
        use_testnet: bool = True,
        limit_per_request: Optional[int] = None,
    ) -> None:
        self._base = BINANCE_TESTNET_KLINES_URL if use_testnet else BINANCE_KLINES_URL
        self._limit = limit_per_request or settings.ohlcv_limit_per_request

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
