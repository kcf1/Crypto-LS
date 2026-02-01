"""
General entry point for the data updater process.

Runs at a fixed interval: run all registered tasks (one subprocess/task per
data source), then sleep UPDATER_INTERVAL_SEC. Each task's exceptions are
caught so one failure does not stop others. Used by the Docker data-updater
service; add new sources in data/updates/ and register in TASKS.

Run from project root: python scripts/run_data_updater.py
"""

import logging
import sys
import time
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings, setup_logging
from data.updates import run_all

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    interval = settings.updater_interval_sec
    logger.info("Data updater started; interval=%s s", interval)
    while True:
        try:
            run_all()
        except Exception as e:
            logger.exception("run_all failed: %s", e)
        time.sleep(interval)


if __name__ == "__main__":
    main()
