"""
Data update tasks registry.

General entry point is scripts/run_data_updater.py (e.g. Docker). Each data
source is one task module with run(). Tasks run simultaneously (threads) so
one source does not block another; one task failure does not stop others.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List

from data.updates import (
    binance_ohlcv,
    binance_funding_rate,
    binance_open_interest,
)

logger = logging.getLogger(__name__)

# Registry: (name, run) per data source; add new sources here.
TASKS: List[tuple[str, Callable[[], None]]] = [
    ("binance_ohlcv", binance_ohlcv.run),
    ("binance_funding_rate", binance_funding_rate.run),
    ("binance_open_interest", binance_open_interest.run),
]


def run_all() -> None:
    """Run all registered tasks simultaneously (one thread per source); log per-task exceptions."""
    if not TASKS:
        return
    with ThreadPoolExecutor(max_workers=len(TASKS)) as executor:
        future_to_name = {executor.submit(task_run): name for name, task_run in TASKS}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                future.result()
            except Exception as e:
                logger.exception("Task %s failed: %s", name, e)
