"""
Check for missing global long/short account records.
Updates every 5 minutes (5m period).

Run from project root: python scripts/integrity/check_missing_global_long_short_account.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from config import settings
from data import Storage

PERIOD = "5m"
INTERVAL_MINUTES = 5
INTERVAL_MS = INTERVAL_MINUTES * 60 * 1000
DAYS_BACK = 7


def round_down_to_5min(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    rounded_minutes = (dt.minute // INTERVAL_MINUTES) * INTERVAL_MINUTES
    return dt.replace(minute=rounded_minutes, second=0, microsecond=0)


def generate_expected_timestamps(start_time: datetime, end_time: datetime) -> pd.DatetimeIndex:
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    start_aligned = round_down_to_5min(start_time)
    end_aligned = round_down_to_5min(end_time)
    return pd.date_range(start=start_aligned, end=end_aligned, freq=f"{INTERVAL_MINUTES}min", inclusive="left", tz="UTC")


def check_symbol(storage: Storage, symbol: str, period: str, start_time: datetime, end_time: datetime) -> dict:
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    rows = storage.read_global_long_short_account(
        symbol=symbol,
        period=period,
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

    df = pd.DataFrame(rows, columns=["timestamp", "long_short_ratio", "long_account", "short_account"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

    start_time_aligned = round_down_to_5min(start_time)
    end_time_aligned = round_down_to_5min(end_time)
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

    expected_times = generate_expected_timestamps(start_time_aligned, end_time_aligned)
    found_times_normalized = set(round_down_to_5min(ts.to_pydatetime()) for ts in df_filtered["datetime"])
    missing_times = [t for t in expected_times if round_down_to_5min(t.to_pydatetime()) not in found_times_normalized]

    gaps = []
    if missing_times:
        missing_sorted = sorted([t.to_pydatetime() if hasattr(t, "to_pydatetime") else t for t in missing_times])
        gap_start = missing_sorted[0]
        gap_end = gap_start
        for i in range(1, len(missing_sorted)):
            time_diff_minutes = (missing_sorted[i] - gap_end).total_seconds() / 60
            if time_diff_minutes == INTERVAL_MINUTES:
                gap_end = missing_sorted[i]
            else:
                duration_minutes = (gap_end - gap_start).total_seconds() / 60
                gaps.append({
                    "start": gap_start.isoformat(),
                    "end": gap_end.isoformat(),
                    "duration_minutes": int(duration_minutes) + INTERVAL_MINUTES,
                    "missing_records": int(duration_minutes / INTERVAL_MINUTES) + 1,
                })
                gap_start = missing_sorted[i]
                gap_end = gap_start
        duration_minutes = (gap_end - gap_start).total_seconds() / 60
        gaps.append({
            "start": gap_start.isoformat(),
            "end": gap_end.isoformat(),
            "duration_minutes": int(duration_minutes) + INTERVAL_MINUTES,
            "missing_records": int(duration_minutes / INTERVAL_MINUTES) + 1,
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


def save_results(
    reports: list,
    summary: dict,
    start_time: datetime,
    end_time: datetime,
    output_dir: Path,
    hours_back: int | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    time_range = {"start": start_time.isoformat(), "end": end_time.isoformat()}
    if hours_back is not None:
        time_range["hours_back"] = hours_back
    else:
        time_range["days_back"] = DAYS_BACK
    json_data = {
        "check_time": datetime.now(timezone.utc).isoformat(),
        "time_range": time_range,
        "period": PERIOD,
        "interval_minutes": INTERVAL_MINUTES,
        "summary": summary,
        "symbol_reports": reports,
    }
    json_path = output_dir / f"missing_global_long_short_account_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    txt_path = output_dir / f"missing_global_long_short_account_{timestamp}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("GLOBAL LONG/SHORT ACCOUNT DATA INTEGRITY CHECK REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Check Time: {datetime.now(timezone.utc).isoformat()} UTC\n")
        f.write(f"Time Range: {start_time.isoformat()} → {end_time.isoformat()}\n")
        f.write(f"Window: {hours_back} hours\n" if hours_back is not None else f"Days Back: {DAYS_BACK}\n")
        f.write(f"Period: {PERIOD} (every {INTERVAL_MINUTES} min)\n")
        f.write(f"Symbols Checked: {summary['total_symbols']}\n\n")
        f.write("SUMMARY\n" + "-" * 80 + "\n")
        f.write(f"Total symbols: {summary['total_symbols']}\n")
        f.write(f"  [OK] Complete: {summary['ok_symbols']}\n")
        f.write(f"  [!] Missing records: {summary['missing_symbols']}\n")
        f.write(f"  [X] No recent data: {summary['no_recent_symbols']}\n")
        f.write(f"  [X] No data: {summary['no_data_symbols']}\n\n")
        f.write(f"Overall coverage: {summary['overall_coverage']:.2f}%\n")
        f.write(f"  Expected: {summary['total_expected']:,}  Found: {summary['total_found']:,}  Missing: {summary['total_missing']:,}\n\n")
        symbols_with_gaps = [r for r in reports if r["gaps"]]
        if symbols_with_gaps:
            f.write("SYMBOLS WITH MISSING RECORDS\n" + "=" * 80 + "\n\n")
            for report in sorted(symbols_with_gaps, key=lambda x: x["missing_count"], reverse=True):
                f.write(f"  {report['symbol']}: {report['missing_count']} missing ({report['coverage_pct']:.1f}% coverage)\n")
                for i, gap in enumerate(report["gaps"][:5], 1):
                    f.write(f"    Gap {i}: {gap['start']} → {gap['end']} ({gap['missing_records']} records)\n")
    return json_path, txt_path


def main(hours: int | None = None) -> int:
    storage = Storage()
    symbols = settings.symbols
    end_time = datetime.now(timezone.utc)
    if hours is not None:
        start_time = end_time - timedelta(hours=hours)
        window_label = f"{hours} hours"
    else:
        start_time = end_time - timedelta(days=DAYS_BACK)
        window_label = f"{DAYS_BACK} days"
    start_time_aligned = round_down_to_5min(start_time)
    end_time_aligned = round_down_to_5min(end_time)
    project_root = Path(__file__).resolve().parent.parent.parent
    output_dir = project_root / "reports" / "integrity"

    print(f"Checking missing global long/short account records for last {window_label} (UTC)")
    print(f"Period: {PERIOD}  Time range: {start_time_aligned.isoformat()} → {end_time_aligned.isoformat()}")
    print(f"Symbols: {len(symbols)}\n" + "=" * 80)

    reports = []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}...", end=" ", flush=True)
        report = check_symbol(storage, symbol, PERIOD, start_time_aligned, end_time_aligned)
        reports.append(report)
        if report["status"] == "no_data":
            print("[X] NO DATA")
        elif report["status"] == "no_recent_data":
            print(f"[!] NO RECENT (latest: {report.get('latest_data', '?')})")
        elif report["missing_count"] == 0:
            print(f"[OK] {report['total_found']} records, {report['coverage_pct']:.1f}%")
        else:
            print(f"[!] MISSING {report['missing_count']} ({report['coverage_pct']:.1f}%)")

    print("\n" + "=" * 80 + "\nSUMMARY\n" + "=" * 80)
    ok = sum(1 for r in reports if r["status"] == "ok")
    missing_sym = sum(1 for r in reports if r["status"] == "missing_records")
    no_recent = sum(1 for r in reports if r["status"] == "no_recent_data")
    no_data = sum(1 for r in reports if r["status"] == "no_data")
    total_expected = sum(r["total_expected"] for r in reports)
    total_found = sum(r["total_found"] for r in reports)
    total_missing = sum(r["missing_count"] for r in reports)
    overall = (total_found / total_expected * 100) if total_expected > 0 else 0.0

    print(f"Total symbols: {len(reports)}  [OK]: {ok}  [!] Missing: {missing_sym}  [X] No recent: {no_recent}  [X] No data: {no_data}")
    print(f"Overall coverage: {overall:.2f}%  Expected: {total_expected:,}  Found: {total_found:,}  Missing: {total_missing:,}\n")

    summary = {
        "total_symbols": len(reports),
        "ok_symbols": ok,
        "missing_symbols": missing_sym,
        "no_recent_symbols": no_recent,
        "no_data_symbols": no_data,
        "total_expected": total_expected,
        "total_found": total_found,
        "total_missing": total_missing,
        "overall_coverage": overall,
    }
    json_path, txt_path = save_results(
        reports, summary, start_time_aligned, end_time_aligned, output_dir, hours_back=hours
    )
    print(f"Report: {txt_path}\nJSON: {json_path}")

    return 0 if (missing_sym == 0 and no_recent == 0 and no_data == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
