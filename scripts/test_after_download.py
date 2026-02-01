"""
Test script: verify expected result after download_last_24h.py has run.
Uses only settings: first 10 symbols, configured timeframes; storage uses DATABASE_URL (Postgres) when set, else SQLite.
Checks that storage has OHLCV data with row counts in expected range for 24h.
Run from project root: python scripts/test_after_download.py
"""

import re
import sys
from pathlib import Path

# Run from project root so config and data are importable
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from data import Storage

# 24h in minutes
MINUTES_PER_DAY = 24 * 60


def _expected_rows_24h(interval: str) -> tuple[int, int]:
    """Return (min_expected, max_expected) rows for 24h of data for Binance interval."""
    interval = interval.strip().lower()
    # e.g. 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d
    m = re.match(r"^(\d+)(m|h|d)$", interval)
    if not m:
        return (1, 2000)
    num, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        count = MINUTES_PER_DAY // num
    elif unit == "h":
        count = 24 // num
    else:
        count = 1
    count = max(1, count)
    min_r = int(count * 0.7)
    max_r = int(count * 1.1) + 1
    return (min_r, max_r)


def main() -> int:
    storage = Storage()
    symbols = settings.symbols[:10]
    timeframes = settings.timeframes
    errors = []
    for symbol in symbols:
        for timeframe in timeframes:
            rows = storage.read_ohlcv(symbol=symbol, timeframe=timeframe)
            if not rows:
                errors.append(f"{symbol} {timeframe}: no data")
                continue
            n = len(rows)
            min_r, max_r = _expected_rows_24h(timeframe)
            if n < min_r or n > max_r:
                errors.append(f"{symbol} {timeframe}: expected {min_r}-{max_r} rows for 24h, got {n}")

    if errors:
        print("FAILED:")
        for e in errors:
            print(f"  {e}")
        return 1
    print("OK: all expected symbol/timeframe pairs have data in expected range.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
