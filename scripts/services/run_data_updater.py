"""
General entry point for the data updater process.

Runs at a fixed interval aligned to 5-minute marks (:05, :10, :15, etc.):
run all registered tasks (one subprocess/task per data source), then sleep
until the next aligned time. Each task's exceptions are caught so one failure
does not stop others. Used by the Docker data-updater service; add new sources
in data/updates/ and register in TASKS.

Run from project root: python scripts/services/run_data_updater.py
"""

import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings, setup_logging
from data.updates import run_all

logger = logging.getLogger(__name__)


def _sleep_until_next_aligned_minute(interval_sec: int) -> None:
    """Sleep until the next time aligned to interval_sec (e.g., :05, :10, :15 for 300s)."""
    now = datetime.now()
    interval_minutes = interval_sec // 60
    
    # Calculate the next aligned minute mark
    current_minute = now.minute
    current_second = now.second + now.microsecond / 1_000_000
    
    # Find which mark we're currently in
    current_mark = (current_minute // interval_minutes) * interval_minutes
    
    # Next mark is the next interval
    next_mark = current_mark + interval_minutes
    
    # If we're exactly at a mark (or very close), use the next one
    if current_minute == current_mark and current_second < 1:
        # We're at the mark, wait for the next one
        next_mark = current_mark + interval_minutes
    
    # Handle wrap-around to next hour
    if next_mark >= 60:
        next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_time = now.replace(minute=next_mark, second=0, microsecond=0)
    
    sleep_seconds = (next_time - now).total_seconds()
    if sleep_seconds > 0:
        logger.debug("Sleeping %.1f s until %s", sleep_seconds, next_time.strftime("%H:%M:%S"))
        time.sleep(sleep_seconds)


def main() -> None:
    setup_logging()
    # Ensure Docker sees activity: add stdout handler so docker logs shows output
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-5s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(sh)
    interval = settings.updater_interval_sec
    logger.info("Data updater started; interval=%s s (aligned to %d-minute marks)", interval, interval // 60)
    
    # Wait until the next aligned minute mark before starting
    _sleep_until_next_aligned_minute(interval)
    
    while True:
        try:
            run_all()
        except Exception as e:
            logger.exception("run_all failed: %s", e)
        try:
            _sleep_until_next_aligned_minute(interval)
        except Exception as e:
            logger.exception("Sleep until next aligned minute failed: %s", e)
            time.sleep(interval)  # fallback: wait one full interval


if __name__ == "__main__":
    main()
