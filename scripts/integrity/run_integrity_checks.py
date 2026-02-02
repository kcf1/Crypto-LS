"""
Run all data integrity checks.

This script can be scheduled to run regularly (e.g., via cron or task scheduler)
to monitor data quality.

Run from project root: python scripts/integrity/run_integrity_checks.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.integrity.check_missing_bars import main as check_missing_bars_main
from scripts.integrity.check_missing_basis import main as check_missing_basis_main
from scripts.integrity.check_missing_global_long_short_account import main as check_missing_global_long_short_account_main
from scripts.integrity.check_missing_top_long_short_account import main as check_missing_top_long_short_account_main
from scripts.integrity.check_missing_top_long_short_position import main as check_missing_top_long_short_position_main


def main() -> int:
    """Run all integrity checks and return combined exit code."""
    print("=" * 80)
    print("DATA INTEGRITY CHECKS")
    print("=" * 80)
    print(f"Started at: {datetime.now(timezone.utc).isoformat()} UTC")
    print()
    
    exit_codes = []
    
    # Run missing bars check
    print("Running: Missing Bars Check")
    print("-" * 80)
    exit_code = check_missing_bars_main()
    exit_codes.append(exit_code)
    print()
    
    # Futures market data (5m)
    print("Running: Missing Basis Check")
    print("-" * 80)
    exit_codes.append(check_missing_basis_main())
    print()
    
    print("Running: Missing Global Long/Short Account Check")
    print("-" * 80)
    exit_codes.append(check_missing_global_long_short_account_main())
    print()
    
    print("Running: Missing Top Long/Short Account Check")
    print("-" * 80)
    exit_codes.append(check_missing_top_long_short_account_main())
    print()
    
    print("Running: Missing Top Long/Short Position Check")
    print("-" * 80)
    exit_codes.append(check_missing_top_long_short_position_main())
    print()
    
    # Summary
    print("=" * 80)
    print("INTEGRITY CHECKS SUMMARY")
    print("=" * 80)
    print(f"Completed at: {datetime.now(timezone.utc).isoformat()} UTC")
    print(f"Total checks: {len(exit_codes)}")
    print(f"Passed: {sum(1 for code in exit_codes if code == 0)}")
    print(f"Failed: {sum(1 for code in exit_codes if code != 0)}")
    print()
    
    # Return 0 if all passed, 1 if any failed
    return 0 if all(code == 0 for code in exit_codes) else 1


if __name__ == "__main__":
    sys.exit(main())
