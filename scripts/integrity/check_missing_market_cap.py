"""
Check for missing market cap records.
Market cap data is collected as daily snapshots (1 record per symbol per day).

Run from project root: python scripts/integrity/check_missing_market_cap.py [--hours N]
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from config import settings
from data import Storage

# Market cap updates daily (1 snapshot per day)
DAYS_BACK = 30


def round_down_to_midnight(dt: datetime) -> datetime:
    """Round down datetime to midnight UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def generate_expected_dates(start_time: datetime, end_time: datetime) -> pd.DatetimeIndex:
    """Generate expected daily timestamps (one per day at midnight UTC)."""
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    # Round down to midnight boundaries
    start_aligned = round_down_to_midnight(start_time)
    end_aligned = round_down_to_midnight(end_time)
    
    # Generate daily timestamps
    return pd.date_range(
        start=start_aligned,
        end=end_aligned,
        freq="D",
        inclusive="left",
        tz="UTC",
    )


def check_symbol(storage: Storage, symbol: str, start_time: datetime, end_time: datetime) -> dict:
    """Check for missing market cap records for a single symbol. Returns report dict."""
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    # Get stored market cap data
    rows = storage.read_market_cap(
        symbol=symbol,
        start_time=int(start_time.timestamp() * 1000),
        end_time=int(end_time.timestamp() * 1000),
    )
    
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
        columns=[
            "timestamp", "market_cap", "circulating_supply", "total_supply", "max_supply",
            "market_cap_rank", "fully_diluted_valuation", "current_price", "total_volume",
            "high_24h", "low_24h", "price_change_24h", "price_change_percentage_24h",
            "market_cap_change_24h", "market_cap_change_percentage_24h",
        ],
    )
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    
    # Round down to midnight boundaries
    start_time_aligned = round_down_to_midnight(start_time)
    end_time_aligned = round_down_to_midnight(end_time)
    
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
    
    # Normalize found timestamps to midnight boundaries
    found_dates_normalized = set(
        round_down_to_midnight(ts.to_pydatetime()).date() for ts in df_filtered["datetime"]
    )
    
    # Generate expected dates
    expected_dates = generate_expected_dates(start_time_aligned, end_time_aligned)
    expected_dates_set = set(d.date() for d in expected_dates)
    
    # Find missing dates
    missing_dates = sorted(expected_dates_set - found_dates_normalized)
    
    # Group consecutive missing dates into gaps
    gaps = []
    if missing_dates:
        gap_start = missing_dates[0]
        gap_end = gap_start
        
        for i in range(1, len(missing_dates)):
            if (missing_dates[i] - gap_end).days == 1:
                gap_end = missing_dates[i]
            else:
                # Gap ended, save it
                duration_days = (gap_end - gap_start).days + 1
                gaps.append({
                    "start": datetime.combine(gap_start, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
                    "end": datetime.combine(gap_end, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
                    "duration_days": duration_days,
                    "missing_records": duration_days,
                })
                gap_start = missing_dates[i]
                gap_end = gap_start
        
        # Add last gap
        duration_days = (gap_end - gap_start).days + 1
        gaps.append({
            "start": datetime.combine(gap_start, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
            "end": datetime.combine(gap_end, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
            "duration_days": duration_days,
            "missing_records": duration_days,
        })
    
    total_expected = len(expected_dates)
    total_found = len(found_dates_normalized)
    missing_count = len(missing_dates)
    coverage_pct = (total_found / total_expected * 100) if total_expected > 0 else 0.0
    
    return {
        "symbol": symbol,
        "status": "ok" if missing_count == 0 else "missing_data",
        "total_expected": total_expected,
        "total_found": total_found,
        "missing_count": missing_count,
        "coverage_pct": round(coverage_pct, 2),
        "gaps": gaps,
        "earliest_data": df_filtered["datetime"].min().isoformat(),
        "latest_data": df_filtered["datetime"].max().isoformat(),
    }


def save_results(
    reports: list,
    summary: dict,
    start_time: datetime,
    end_time: datetime,
    output_dir: Path,
    hours_back: int | None = None,
) -> tuple[Path, Path]:
    """Save results to JSON and text files. Returns paths to saved files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    time_range = {"start": start_time.isoformat(), "end": end_time.isoformat()}
    if hours_back is not None:
        time_range["hours_back"] = hours_back
    else:
        time_range["days_back"] = DAYS_BACK
    
    # Save JSON report
    json_data = {
        "check_time": datetime.now(timezone.utc).isoformat(),
        "time_range": time_range,
        "summary": summary,
        "symbol_reports": reports,
    }
    
    json_path = output_dir / f"missing_market_cap_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # Save text report
    txt_path = output_dir / f"missing_market_cap_{timestamp}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("MARKET CAP DATA INTEGRITY CHECK REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Check Time: {datetime.now(timezone.utc).isoformat()} UTC\n")
        f.write(f"Time Range: {start_time.isoformat()} → {end_time.isoformat()}\n")
        f.write(f"Window: {hours_back} hours\n" if hours_back is not None else f"Days Back: {DAYS_BACK}\n")
        f.write(f"Update Frequency: Daily snapshots (1 record per symbol per day)\n")
        f.write(f"Symbols Checked: {summary['total_symbols']}\n")
        f.write("\n")
        f.write("SUMMARY\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total symbols checked: {summary['total_symbols']}\n")
        f.write(f"  [OK] Complete (100%): {summary['ok_symbols']}\n")
        f.write(f"  [!] Missing records: {summary['missing_symbols']}\n")
        f.write(f"  [X] No recent data: {summary['no_recent_symbols']}\n")
        f.write(f"  [X] No data at all: {summary['no_data_symbols']}\n")
        f.write("\n")
        f.write(f"Overall coverage: {summary['overall_coverage']:.2f}%\n")
        f.write(f"  Expected records: {summary['total_expected']:,}\n")
        f.write(f"  Found records: {summary['total_found']:,}\n")
        f.write(f"  Missing records: {summary['total_missing']:,}\n")
        f.write("\n")
        
        # Symbols with missing records
        symbols_with_gaps = [r for r in reports if r["gaps"]]
        if symbols_with_gaps:
            f.write("=" * 80 + "\n")
            f.write("SYMBOLS WITH MISSING RECORDS\n")
            f.write("=" * 80 + "\n\n")
            for report in sorted(symbols_with_gaps, key=lambda x: x["missing_count"], reverse=True):
                f.write(f"Symbol: {report['symbol']}\n")
                f.write(f"  Coverage: {report['coverage_pct']:.2f}% ({report['total_found']}/{report['total_expected']} records)\n")
                f.write(f"  Missing: {report['missing_count']} records\n")
                f.write(f"  Data range: {report.get('earliest_data', 'N/A')} → {report.get('latest_data', 'N/A')}\n")
                f.write(f"  Gaps: {len(report['gaps'])}\n")
                for i, gap in enumerate(report['gaps'][:10], 1):
                    f.write(f"    Gap {i}: {gap['start']} → {gap['end']} ({gap['duration_days']} days, {gap['missing_records']} records)\n")
                if len(report['gaps']) > 10:
                    f.write(f"    ... and {len(report['gaps']) - 10} more gaps\n")
                f.write("\n")
        
        # Symbols with no recent data
        no_recent = [r for r in reports if r["status"] == "no_recent_data"]
        if no_recent:
            f.write("=" * 80 + "\n")
            window_txt = f"last {hours_back} hours" if hours_back is not None else f"last {DAYS_BACK} days"
            f.write(f"SYMBOLS WITH NO RECENT DATA ({window_txt})\n")
            f.write("=" * 80 + "\n\n")
            for report in no_recent:
                latest = report.get("latest_data", "unknown")
                f.write(f"  {report['symbol']}: Latest data at {latest}\n")
            f.write("\n")
        
        # Symbols with no data
        no_data = [r for r in reports if r["status"] == "no_data"]
        if no_data:
            f.write("=" * 80 + "\n")
            f.write("SYMBOLS WITH NO DATA\n")
            f.write("=" * 80 + "\n\n")
            for report in no_data:
                f.write(f"  {report['symbol']}\n")
            f.write("\n")
    
    return json_path, txt_path


def main(hours: int | None = None) -> int:
    storage = Storage()
    symbols = settings.symbols
    
    # Calculate time range (all in UTC)
    end_time = datetime.now(timezone.utc)
    if hours is not None:
        start_time = end_time - timedelta(hours=hours)
        window_label = f"{hours} hours"
    else:
        start_time = end_time - timedelta(days=DAYS_BACK)
        window_label = f"{DAYS_BACK} days"
    
    # Round down to midnight boundaries
    start_time_aligned = round_down_to_midnight(start_time)
    end_time_aligned = round_down_to_midnight(end_time)
    
    # Setup output directory
    project_root = Path(__file__).resolve().parent.parent.parent
    output_dir = project_root / "reports" / "integrity"
    
    print(f"Checking missing market cap records for last {window_label} (UTC)")
    print(f"Market cap updates daily (1 snapshot per symbol per day)")
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
    missing_symbols = sum(1 for r in reports if r["status"] == "missing_data")
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
                print(f"    Gap {i}: {gap['start']} → {gap['end']} ({gap['duration_days']} days, {gap['missing_records']} records)")
            
            if len(report['gaps']) > 5:
                print(f"    ... and {len(report['gaps']) - 5} more gaps")
            print()
    
    # Symbols with no recent data
    if no_recent_symbols > 0:
        print("=" * 80)
        print(f"SYMBOLS WITH NO RECENT DATA (last {window_label})")
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
    
    # Save results to files
    summary = {
        "total_symbols": total_symbols,
        "ok_symbols": ok_symbols,
        "missing_symbols": missing_symbols,
        "no_recent_symbols": no_recent_symbols,
        "no_data_symbols": no_data_symbols,
        "total_expected": total_expected,
        "total_found": total_found,
        "total_missing": total_missing,
        "overall_coverage": overall_coverage,
    }
    
    json_path, txt_path = save_results(
        reports, summary, start_time_aligned, end_time_aligned, output_dir, hours_back=hours
    )
    print(f"Report saved to: {txt_path}")
    print(f"JSON report saved to: {json_path}")
    print()
    
    # Return exit code: 0 if all OK, 1 if any issues
    if missing_symbols > 0 or no_recent_symbols > 0 or no_data_symbols > 0:
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check for missing market cap records.")
    parser.add_argument(
        "--hours",
        type=int,
        default=None,
        metavar="N",
        help="Check last N hours (e.g. 48). If omitted, uses default window.",
    )
    args = parser.parse_args()
    sys.exit(main(hours=args.hours))
