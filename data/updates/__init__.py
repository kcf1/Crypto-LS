"""
Data update tasks registry.

General entry point is scripts/run_data_updater.py (e.g. Docker). Each data
source is one subprocess/task module with run(). One task failure does not stop others.
"""

import logging
from typing import Callable, List

from data.updates import binance_ohlcv

logger = logging.getLogger(__name__)

# Registry: (name, run) per data source; add new sources here.
TASKS: List[tuple[str, Callable[[], None]]] = [
    ("binance_ohlcv", binance_ohlcv.run),
]


def run_all() -> None:
    """Run all registered tasks; log and continue on per-task exceptions."""
    for name, task_run in TASKS:
        try:
            task_run()
        except Exception as e:
            logger.exception("Task %s failed: %s", name, e)
