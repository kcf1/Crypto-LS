"""Binance manager: runs enabled dataset collectors (klines, later trades, depth)."""

import asyncio
import logging
from typing import Any, List, Optional, Sequence

from data.streams.binance.klines import KlinesCollector

logger = logging.getLogger(__name__)


class BinanceManager:
    """
    One manager per source. Holds config and list of dataset collectors;
    run() starts their writer (and later stream) tasks. No collection logic here.
    """

    def __init__(
        self,
        storage: Any,
        symbols: Optional[Sequence[str]] = None,
        timeframes: Optional[Sequence[str]] = None,
        use_testnet: bool = True,
    ) -> None:
        from config import settings

        self._storage = storage
        self._symbols = list(symbols or settings.symbols)
        self._timeframes = list(timeframes or settings.timeframes)
        self._use_testnet = use_testnet
        self._collectors: List[Any] = [
            KlinesCollector(
                symbols=self._symbols,
                timeframes=self._timeframes,
                storage=self._storage,
            ),
        ]

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run all enabled dataset collectors until stop_event is set."""
        names = [c.name for c in self._collectors]
        logger.info("BinanceManager starting collectors: %s", names)
        await asyncio.gather(*(c.run(stop_event) for c in self._collectors))
        logger.info("BinanceManager stopped")
