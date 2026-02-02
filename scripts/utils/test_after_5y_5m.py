"""
Test script: verify expected result after update_5y_5m.py has run.
Uses settings.symbols and 5m only; storage from DATABASE_URL (Postgres) when set, else SQLite.
Checks that each symbol has OHLCV data with row count in expected range for 5 years of 5m.
Run from project root: python scripts/utils/test_after_5y_5m.py
"""

import sys
from pathlib import Path

# Run from project root so config and data are importable
if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings
from data import Storage

# 5m candles in 5 years (must match update_5y_5m.py)
CANDLES_5M_PER_5Y = int(5 * 365.25 * 24 * 60 / 5)


def _expected_rows_5y_5m() -> tuple[int, int]:
    """Return (min_expected, max_expected) rows for 5 years of 5m data."""
    count = CANDLES_5M_PER_5Y
    min_r = int(count * 0.7)   # allow gaps (e.g. late-listed symbols)
    max_r = int(count * 1.05) + 1
    return (min_r, max_r)


def main() -> int:
    storage = Storage()
    symbols = settings.symbols
    interval = "5m"
    min_r, max_r = _expected_rows_5y_5m()

    errors = []
    for symbol in symbols:
        rows = storage.read_ohlcv(symbol=symbol, timeframe=interval)
        if not rows:
            errors.append(f"{symbol} {interval}: no data")
            continue
        n = len(rows)
        if n < min_r or n > max_r:
            errors.append(f"{symbol} {interval}: expected {min_r}-{max_r} rows for 5y 5m, got {n}")

    if errors:
        print("FAILED:")
        for e in errors:
            print(f"  {e}")
        print(f"  ({len(errors)} / {len(symbols)} symbols failed)")
        return 1
    print(f"OK: all {len(symbols)} symbols have 5m data in expected range ({min_r}-{max_r} rows).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
