"""
Test script: download last 24 hours of OHLCV for all configured symbols and timeframes.
Uses data.Collector (REST) and data.Storage; writes to settings.db_path (SQLite) by default.
Run from project root: python scripts/download_last_24h.py
"""

import time
from pathlib import Path

# Run from project root so config and data are importable
import sys
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from data import Collector, Storage


def main() -> None:
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - 24 * 3600 * 1000

    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage(db_path=settings.db_path)

    symbols = settings.symbols
    timeframes = settings.timeframes
    total = len(symbols) * len(timeframes)
    ok = 0
    failed = []

    for i, symbol in enumerate(symbols):
        for timeframe in timeframes:
            try:
                rows = collector.fetch_klines(
                    symbol=symbol,
                    interval=timeframe,
                    start_time=start_time_ms,
                    end_time=end_time_ms,
                )
                if rows:
                    storage.write_ohlcv(symbol, timeframe, rows)
                    ok += 1
            except Exception as e:
                failed.append((symbol, timeframe, str(e)))
            time.sleep(0.05)

    print(f"Downloaded last 24h: {ok}/{total} symbol/timeframe pairs written to {settings.db_path}")
    if failed:
        print(f"Failed ({len(failed)}):")
        for s, t, err in failed[:10]:
            print(f"  {s} {t}: {err}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")


if __name__ == "__main__":
    main()
