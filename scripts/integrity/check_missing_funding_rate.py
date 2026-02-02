"""
Check for missing funding rate records.
Funding rate updates every 8 hours (00:00, 08:00, 16:00 UTC).

Run from project root: python scripts/integrity/check_missing_funding_rate.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from config import settings
from data import Storage

# Funding rate updates every 8 hours
FUNDING_INTERVAL_HOURS = 8
FUNDING_INTERVAL_MS = FUNDING_INTERVAL_HOURS * 3600 * 1000

# Check last 30 days by default
DAYS_BACK = 30


def round_down_to_funding_time(dt: datetime) -> datetime:
    """Round down datetime to the nearest funding rate time (00:00, 08:00, 16:00 UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Funding times are at 00:00, 08:00, 16:00 UTC
    hour = dt.hour
    funding_hour = (hour // FUNDING_INTERVAL_HOURS) * FUNDING_INTERVAL_HOURS
    
    return dt.replace(hour=funding_hour, minute=0, second=0, microsecond=0)


def generate_expected_funding_times(start_time: datetime, end_time: datetime) -> pd.DatetimeIndex:
    """Generate expected funding rate timestamps (every 8 hours)."""
    # Ensure UTC timezone
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    # Round down to funding rate boundaries
    start_aligned = round_down_to_funding_time(start_time)
    end_aligned = round_down_to_funding_time(end_time)
    
    # Generate timestamps (every 8 hours)
    return pd.date_range(
        start=start_aligned,
        end=end_aligned,
        freq=f"{FUNDING_INTERVAL_HOURS}H",
        inclusive="left",
        tz="UTC",
    )


def check_symbol(storage: Storage, symbol: str, start_time: datetime, end_time: datetime) -> dict:
    """Check for missing funding rate records for a single symbol. Returns report dict."""
    # Ensure UTC timezone
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    # Get stored funding rate data
    rows = storage.read_funding_rate(symbol=symbol, start_time=int(start_time.timestamp() * 1000), end_time=int(end_time.timestamp() * 1000))
    
    if not rows:
        return {
            "symbol": symbol,
            "status": "no_data",
            "total_expected": 0,
            "total_found": 0,
            "missing_count": 0,
            "coverage_pct": 0.0,
            "gaps": [],
        }
    
    df = pd.DataFrame(
        rows,
        columns=["funding_time", "funding_rate", "mark_price"],
    )
    # Convert to UTC-aware datetime
    df["datetime"] = pd.to_datetime(df["funding_time"], unit="ms", utc=True)
    
    # Round down to funding rate boundaries
    start_time_aligned = round_down_to_funding_time(start_time)
    end_time_aligned = round_down_to_funding_time(end_time)
    
    # Filter to time range
    df_filtered = df[(df["datetime"] >= start_time_aligned) & (df["datetime"] < end_time_aligned)].copy()
    
    if len(df_filtered) == 0:
        return {
            "symbol": symbol,
            "status": "no_recent_data",
            "total_expected": 0,
            "total_found": 0,
            "missing_count": 0,
            "coverage_pct": 0.0,
            "gaps": [],
            "latest_data": df["datetime"].max().isoformat() if len(df) > 0 else None,
        }
    
    # Generate expected timestamps
    expected_times = generate_expected_funding_times(start_time_aligned, end_time_aligned)
    
    # Normalize found timestamps to funding rate boundaries
    found_times_normalized = set(
        round_down_to_funding_time(ts.to_pydatetime()) for ts in df_filtered["datetime"]
    )
    
    # Find missing records
    missing_times = [t for t in expected_times if round_down_to_funding_time(t.to_pydatetime()) not in found_times_normalized]
    
    # Group consecutive missing records into gaps
    gaps = []
    if missing_times:
        missing_sorted = sorted([t.to_pydatetime() if hasattr(t, 'to_pydatetime') else t for t in missing_times])
        
        gap_start = missing_sorted[0]
        gap_end = gap_start
        
        for i in range(1, len(missing_sorted)):
            time_diff_hours = (missing_sorted[i] - gap_end).total_seconds() / 3600
            if time_diff_hours == FUNDING_INTERVAL_HOURS:
                gap_end = missing_sorted[i]
            else:
                # Gap ended, save it
                duration_hours = (gap_end - gap_start).total_seconds() / 3600
                gaps.append({
                    "start": gap_start.isoformat(),
                    "end": gap_end.isoformat(),
                    "duration_hours": int(duration_hours) + FUNDING_INTERVAL_HOURS,
                    "missing_records": int(duration_hours / FUNDING_INTERVAL_HOURS) + 1,
                })
                gap_start = missing_sorted[i]
                gap_end = gap_start
        
        # Add last gap
        duration_hours = (gap_end - gap_start).total_seconds() / 3600
        gaps.append({
            "start": gap_start.isoformat(),
            "end": gap_end.isoformat(),
            "duration_hours": int(duration_hours) + FUNDING_INTERVAL_HOURS,
            "missing_records": int(duration_hours / FUNDING_INTERVAL_HOURS) + 1,
        })
    
    total_expected = len(expected_times)
    total_found = len(df_filtered)
    missing_count = len(missing_times)
    coverage_pct = (total_found / total_expected * 100) if total_expected > 0 else 0.0
    
    return {
        "symbol": symbol,
        "status": "ok" if missing_count == 0 else "missing_records",
        "total_expected": total_expected,
        "total_found": total_found,
        "missing_count": missing_count,
        "coverage_pct": coverage_pct,
        "gaps": gaps,
        "earliest_data": df_filtered["datetime"].min().isoformat(),
        "latest_data": df_filtered["datetime"].max().isoformat(),
    }


def main() -> int:
    storage = Storage()
    symbols = settings.symbols
    
    # Calculate time range (all in UTC)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=DAYS_BACK)
    
    # Round down to funding rate boundaries
    start_time_aligned = round_down_to_funding_time(start_time)
    end_time_aligned = round_down_to_funding_time(end_time)
    
    print(f"Checking missing funding rate records for last {DAYS_BACK} days (UTC)")
    print(f"Funding rate updates every {FUNDING_INTERVAL_HOURS} hours (00:00, 08:00, 16:00 UTC)")
    print(f"Time range: {start_time_aligned.isoformat()} → {end_time_aligned.isoformat()}")
    print(f"Symbols to check: {len(symbols)}")
    print("=" * 80)
    print()
    
    reports = []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Checking {symbol}...", end=" ", flush=True)
        report = check_symbol(storage, symbol, start_time_aligned, end_time_aligned)
        reports.append(report)
        
        if report["status"] == "no_data":
            print("[X] NO DATA")
        elif report["status"] == "no_recent_data":
            latest = report.get("latest_data", "unknown")
            print(f"[!] NO RECENT DATA (latest: {latest})")
        elif report["missing_count"] == 0:
            print(f"[OK] ({report['total_found']} records, {report['coverage_pct']:.1f}% coverage)")
        else:
            print(f"[!] MISSING {report['missing_count']} records ({report['coverage_pct']:.1f}% coverage)")
    
    print()
    print("=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)
    print()
    
    # Summary statistics
    total_symbols = len(reports)
    ok_symbols = sum(1 for r in reports if r["status"] == "ok")
    missing_symbols = sum(1 for r in reports if r["status"] == "missing_records")
    no_data_symbols = sum(1 for r in reports if r["status"] == "no_data")
    no_recent_symbols = sum(1 for r in reports if r["status"] == "no_recent_data")
    
    total_expected = sum(r["total_expected"] for r in reports)
    total_found = sum(r["total_found"] for r in reports)
    total_missing = sum(r["missing_count"] for r in reports)
    overall_coverage = (total_found / total_expected * 100) if total_expected > 0 else 0.0
    
    print(f"Total symbols checked: {total_symbols}")
    print(f"  [OK] Complete (100%): {ok_symbols}")
    print(f"  [!] Missing records: {missing_symbols}")
    print(f"  [X] No recent data: {no_recent_symbols}")
    print(f"  [X] No data at all: {no_data_symbols}")
    print()
    print(f"Overall coverage: {overall_coverage:.2f}%")
    print(f"  Expected records: {total_expected:,}")
    print(f"  Found records: {total_found:,}")
    print(f"  Missing records: {total_missing:,}")
    print()
    
    # Detailed report for symbols with missing records
    symbols_with_gaps = [r for r in reports if r["gaps"]]
    if symbols_with_gaps:
        print("=" * 80)
        print("SYMBOLS WITH MISSING RECORDS")
        print("=" * 80)
        print()
        
        for report in sorted(symbols_with_gaps, key=lambda x: x["missing_count"], reverse=True):
            print(f"Symbol: {report['symbol']}")
            print(f"  Coverage: {report['coverage_pct']:.2f}% ({report['total_found']}/{report['total_expected']} records)")
            print(f"  Missing: {report['missing_count']} records")
            print(f"  Data range: {report.get('earliest_data', 'N/A')} → {report.get('latest_data', 'N/A')}")
            print(f"  Gaps: {len(report['gaps'])}")
            
            # Show first 5 gaps
            for i, gap in enumerate(report['gaps'][:5], 1):
                print(f"    Gap {i}: {gap['start']} → {gap['end']} ({gap['duration_hours']} hours, {gap['missing_records']} records)")
            
            if len(report['gaps']) > 5:
                print(f"    ... and {len(report['gaps']) - 5} more gaps")
            print()
    
    # Symbols with no recent data
    if no_recent_symbols > 0:
        print("=" * 80)
        print("SYMBOLS WITH NO RECENT DATA (last 30 days)")
        print("=" * 80)
        print()
        
        for report in [r for r in reports if r["status"] == "no_recent_data"]:
            latest = report.get("latest_data", "unknown")
            print(f"  {report['symbol']}: Latest data at {latest}")
        print()
    
    # Symbols with no data at all
    if no_data_symbols > 0:
        print("=" * 80)
        print("SYMBOLS WITH NO DATA")
        print("=" * 80)
        print()
        
        for report in [r for r in reports if r["status"] == "no_data"]:
            print(f"  {report['symbol']}")
        print()
    
    # Return exit code: 0 if all OK, 1 if any issues
    if missing_symbols > 0 or no_recent_symbols > 0 or no_data_symbols > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
