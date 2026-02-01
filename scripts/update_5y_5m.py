"""
Update OHLCV: last 5 years, 5m interval, for all symbols in settings.symbols.
Uses data.Collector (REST) and data.Storage; writes to DATABASE_URL (Postgres) when set, else SQLite.
Paginates by 1000 candles per request (Binance limit).

Binance Spot API limits (IP-based; logging in does NOT increase the limit):
- Request weight: 1200 per minute (conservative); klines weight = 1 per request.
- Exceeding returns 429; repeated violations can cause IP ban (418).
- Script uses a delay between requests; 429 triggers retry after Retry-After seconds.

Each batch is validated (OHLC consistency) and verified (read-back); if not, batch is redownloaded up to MAX_BATCH_RETRIES before moving on. Delay: DELAY_SEC = 0.1 (safer).

Run from project root: python scripts/update_5y_5m.py
"""

import logging
import math
import sys
import time
from pathlib import Path

import requests

# Run from project root so config and data are importable
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings, setup_logging
from data import Collector, Storage

logger = logging.getLogger(__name__)

# 5 years in milliseconds
SECONDS_PER_5Y = 5 * 365.25 * 24 * 3600
MS_PER_5Y = int(SECONDS_PER_5Y * 1000)

# 5m candles in 5 years: 5 * 365.25 * 24 * 60 / 5
CANDLES_5M_PER_5Y = int(5 * 365.25 * 24 * 60 / 5)

# Rough bytes per row (symbol + timeframe + 7 numeric cols + index overhead)
BYTES_PER_ROW_ESTIMATE = 120

# Binance: klines weight = 1; 1200 weight/min (conservative). Some docs say 6000/min.
BINANCE_WEIGHT_PER_MIN = 1200
KLINES_WEIGHT = 1

# Delay between requests (sec). 0.1 => ~600/min (safer).
DELAY_SEC = 0.1
MAX_429_RETRIES = 5
MAX_BATCH_RETRIES = 3  # redownload batch if validation or read-back check fails


def _estimate_size_mb(num_symbols: int, interval: str = "5m") -> float:
    """Estimate DB size in MB for given symbol count and 5y 5m data."""
    if interval != "5m":
        raise ValueError("Estimate only for 5m")
    total_rows = num_symbols * CANDLES_5M_PER_5Y
    return (total_rows * BYTES_PER_ROW_ESTIMATE) / (1024 * 1024)


def _estimate_requests(num_symbols: int) -> int:
    """Number of API requests for 5y 5m: ceil(candles_per_symbol / 1000) per symbol."""
    requests_per_symbol = math.ceil(CANDLES_5M_PER_5Y / 1000)
    return num_symbols * requests_per_symbol


def _estimate_duration_sec(num_requests: int, delay_sec: float) -> float:
    """Estimated runtime in seconds with given delay between requests."""
    return num_requests * delay_sec


def _validate_ohlcv_rows(rows: list) -> bool:
    """Check OHLC consistency: low <= open,close <= high; low <= high; open > 0."""
    for r in rows:
        open_t, open_p, high, low, close, volume, close_t = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        if open_p <= 0 or high <= 0 or low < 0:
            return False
        if low > high:
            return False
        if low > min(open_p, close) or high < max(open_p, close):
            return False
    return True


def fetch_klines_with_retry(
    collector: Collector,
    symbol: str,
    interval: str,
    *,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int,
) -> list:
    """Call collector.fetch_klines; on 429, sleep Retry-After and retry up to MAX_429_RETRIES."""
    for attempt in range(MAX_429_RETRIES):
        try:
            return collector.fetch_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < MAX_429_RETRIES - 1:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning("429 rate limit, sleeping %s s (attempt %s)", retry_after, attempt + 1)
                time.sleep(retry_after)
                continue
            raise
    return []


def fetch_batch_and_verify(
    collector: Collector,
    storage: Storage,
    symbol: str,
    interval: str,
    cursor_ms: int,
    end_time_ms: int,
    limit: int,
    delay_sec: float,
) -> tuple[list, int]:
    """
    Fetch a batch, validate OHLC, write, then verify read-back. On failure, redownload up to MAX_BATCH_RETRIES.
    Returns (rows, next_cursor_ms). If no rows, next_cursor_ms = end_time_ms to break loop.
    """
    for batch_attempt in range(MAX_BATCH_RETRIES):
        rows = fetch_klines_with_retry(
            collector,
            symbol,
            interval,
            start_time=cursor_ms,
            end_time=end_time_ms,
            limit=limit,
        )
        if not rows:
            return [], end_time_ms
        if not _validate_ohlcv_rows(rows):
            logger.warning(
                "Batch validation failed %s %s start=%s (attempt %s), redownloading",
                symbol,
                interval,
                cursor_ms,
                batch_attempt + 1,
            )
            time.sleep(delay_sec)
            continue
        storage.write_ohlcv(symbol, interval, rows)
        from_time = rows[0][0]
        to_time = rows[-1][0]
        read_back = storage.read_ohlcv(symbol, interval, from_time=from_time, to_time=to_time)
        if len(read_back) < len(rows):
            logger.warning(
                "Read-back check failed %s %s: wrote %s, got %s (attempt %s), redownloading",
                symbol,
                interval,
                len(rows),
                len(read_back),
                batch_attempt + 1,
            )
            time.sleep(delay_sec)
            continue
        next_cursor = rows[-1][6] + 1
        return rows, next_cursor
    logger.error(
        "Batch failed after %s retries %s %s start=%s",
        MAX_BATCH_RETRIES,
        symbol,
        interval,
        cursor_ms,
    )
    return [], end_time_ms


def main() -> None:
    setup_logging()
    interval = "5m"
    symbols = settings.symbols
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - MS_PER_5Y
    run_start = time.perf_counter()

    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()

    logger.info("Starting 5y 5m update: %s symbols, interval=%s", len(symbols), interval)

    est_mb = _estimate_size_mb(len(symbols))
    total_rows_est = len(symbols) * CANDLES_5M_PER_5Y
    num_requests = _estimate_requests(len(symbols))
    limit = settings.ohlcv_limit_per_request  # 1000
    delay_sec = DELAY_SEC
    est_sec = _estimate_duration_sec(num_requests, delay_sec)
    est_min = est_sec / 60
    min_minutes_by_weight = num_requests * KLINES_WEIGHT / BINANCE_WEIGHT_PER_MIN
    print(
        f"Update 5y 5m: {len(symbols)} symbols, ~{CANDLES_5M_PER_5Y} candles/symbol, "
        f"~{total_rows_est} total rows, est. DB size ~{est_mb:.1f} MB"
    )
    print(
        f"Requests: ~{num_requests} (1000 candles/request). "
        f"Est. time at {delay_sec}s delay: ~{est_min:.0f} min. "
        f"Binance limit: {BINANCE_WEIGHT_PER_MIN} weight/min (klines=1); min time ~{min_minutes_by_weight:.0f} min if no delay."
    )
    logger.info(
        "Update 5y 5m: %s symbols, ~%s candles/symbol, ~%s total rows, est. size ~%.1f MB",
        len(symbols),
        CANDLES_5M_PER_5Y,
        total_rows_est,
        est_mb,
    )
    db_target = "Postgres (DATABASE_URL)" if settings.database_url else f"SQLite ({settings.db_path})"
    logger.info("Target: %s", db_target)

    limit = settings.ohlcv_limit_per_request  # 1000
    total_written = 0
    failed = []

    for i, symbol in enumerate(symbols):
        print(f"  {i + 1}/{len(symbols)} {symbol} ...", flush=True)
        logger.info("Symbol %s/%s: %s", i + 1, len(symbols), symbol)
        cursor_ms = start_time_ms
        symbol_rows = 0
        try:
            while cursor_ms < end_time_ms:
                rows, cursor_ms = fetch_batch_and_verify(
                    collector,
                    storage,
                    symbol,
                    interval,
                    cursor_ms,
                    end_time_ms,
                    limit,
                    delay_sec,
                )
                if not rows:
                    break
                symbol_rows += len(rows)
                total_written += len(rows)
                time.sleep(delay_sec)
            print(f"  {i + 1}/{len(symbols)} {symbol}: {symbol_rows} rows", flush=True)
            logger.info("  %s/%s %s: %s rows", i + 1, len(symbols), symbol, symbol_rows)
        except Exception as e:
            print(f"  {i + 1}/{len(symbols)} {symbol}: FAILED {e}", flush=True)
            logger.warning("  %s/%s %s failed: %s", i + 1, len(symbols), symbol, e)
            failed.append((symbol, str(e)))
        time.sleep(delay_sec)

    elapsed_sec = time.perf_counter() - run_start
    logger.info(
        "Done: %s total rows written to %s in %.1f min",
        total_written,
        db_target,
        elapsed_sec / 60,
    )
    if failed:
        logger.warning("Failed symbols (%s): %s", len(failed), [s for s, _ in failed])
    print(f"Done: {total_written} rows in {elapsed_sec / 60:.1f} min. Run scripts/test_after_5y_5m.py to verify.")


if __name__ == "__main__":
    main()
