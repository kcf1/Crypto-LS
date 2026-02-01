"""Klines collector: queue + writer task; stream tasks added later."""

import asyncio
from typing import Any, Optional, Sequence, Tuple

# Kline item: (symbol, timeframe, candle_tuple)
# candle_tuple: (open_time, open, high, low, close, volume, close_time)
KlineItem = Tuple[str, str, Tuple[Any, ...]]


class KlinesCollector:
    """
    Collects kline (OHLCV) items into a queue; one writer task drains to storage.
    Stream tasks will be added later; they will push parsed kline events into self._queue.
    """

    name: str = "klines"

    def __init__(
        self,
        symbols: Sequence[str],
        timeframes: Sequence[str],
        storage: Any,
        queue_maxsize: int = 0,
    ) -> None:
        self._symbols = list(symbols)
        self._timeframes = list(timeframes)
        self._storage = storage
        self._queue: asyncio.Queue[Optional[KlineItem]] = asyncio.Queue(maxsize=queue_maxsize or 0)

    async def _writer_task(self, stop_event: asyncio.Event) -> None:
        """Async writer: get from queue, run sync write in executor."""
        loop = asyncio.get_event_loop()
        while not stop_event.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if item is None:
                break
            symbol, timeframe, row = item
            await loop.run_in_executor(
                None,
                lambda s=symbol, t=timeframe, r=row: self._storage.write_ohlcv(s, t, [r]),
            )

    async def run(self, stop_event: asyncio.Event) -> None:
        """
        Start writer task (and later stream tasks); run until stop_event is set.
        No collection operations yet – stream tasks will push into self._queue later.
        """
        writer = asyncio.create_task(self._writer_task(stop_event))
        # Stream tasks will be added here; they will push (symbol, timeframe, candle_tuple) into self._queue.
        await stop_event.wait()
        self._queue.put_nowait(None)
        await writer
