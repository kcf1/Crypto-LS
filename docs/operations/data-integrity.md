# Data Integrity Framework

This document describes the data integrity checking framework for Crypto-LS.

## Overview

The data integrity framework provides automated checks to ensure data quality and completeness. Reports are saved with timestamps for historical tracking and analysis.

## Architecture

```
data/integrity/
├── __init__.py      # Module exports
└── base.py          # Base classes for integrity checks

scripts/
├── check_missing_bars.py      # Missing bars check implementation
└── run_integrity_checks.py    # Runner for all checks

reports/integrity/
├── missing_bars_*.json        # JSON reports (machine-readable)
└── missing_bars_*.txt         # Text reports (human-readable)
```

## Available Checks

### 1. Missing Bars Check

**Script:** `scripts/check_missing_bars.py`

**Purpose:** Checks for missing 5-minute OHLCV bars in the last 48 hours.

**What it checks:**
- Verifies all expected 5-minute bars exist for configured symbols
- Identifies gaps in data collection
- Reports symbols with no recent data
- Reports symbols with no data at all

**Output:**
- JSON report with structured data
- Text report for human review
- Console output with summary

**Exit codes:**
- `0`: All checks passed
- `1`: Issues found (missing bars, no data, etc.)

## Running Checks

### Manual Execution

```bash
# Run missing bars check
python scripts/check_missing_bars.py

# Run all integrity checks
python scripts/run_integrity_checks.py
```

### Scheduled Execution

#### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily or every N hours
4. Action: Start a program
   - Program: `python`
   - Arguments: `scripts/run_integrity_checks.py`
   - Start in: `F:\Document\GitHub\Crypto-LS`

#### Linux/Mac Cron

```bash
# Edit crontab
crontab -e

# Add line to run every 6 hours
0 */6 * * * cd /path/to/Crypto-LS && python scripts/run_integrity_checks.py >> logs/integrity.log 2>&1
```

#### Docker

Add to `docker-compose.yml`:

```yaml
services:
  integrity-checker:
    build:
      context: .
      dockerfile: Dockerfile.updater
    command: python scripts/run_integrity_checks.py
    volumes:
      - ./reports:/app/reports
    environment:
      - DATABASE_URL=${DATABASE_URL}
    restart: "no"
```

Schedule with cron/Task Scheduler:
```bash
docker compose run --rm integrity-checker
```

## Report Format

### JSON Report Structure

```json
{
  "check_time": "2026-02-02T08:48:32+00:00",
  "time_range": {
    "start": "2026-01-31T08:45:00+00:00",
    "end": "2026-02-02T08:45:00+00:00",
    "hours_back": 48
  },
  "summary": {
    "total_symbols": 100,
    "ok_symbols": 89,
    "missing_symbols": 0,
    "no_recent_symbols": 10,
    "no_data_symbols": 1,
    "total_expected": 51264,
    "total_found": 51264,
    "total_missing": 0,
    "overall_coverage": 100.0
  },
  "symbol_reports": [
    {
      "symbol": "BTCUSDT",
      "status": "ok",
      "total_expected": 576,
      "total_found": 576,
      "missing_count": 0,
      "coverage_pct": 100.0,
      "gaps": [],
      "earliest_data": "2026-01-31T08:45:00+00:00",
      "latest_data": "2026-02-02T08:40:00+00:00"
    }
  ]
}
```

### Text Report

Human-readable format with:
- Summary statistics
- Detailed gap information
- Lists of problematic symbols

## Extending the Framework

### Adding a New Check

1. **Create check script** in `scripts/`:
   ```python
   from data.integrity import IntegrityCheck, IntegrityCheckResult
   from datetime import datetime, timezone
   
   def main() -> int:
       # Your check logic
       result = IntegrityCheckResult(
           check_name="my_check",
           check_time=datetime.now(timezone.utc),
           status="ok",
           summary={"key": "value"},
           details=[],
       )
       
       check = IntegrityCheck("my_check")
       check.save_result(result)
       
       return 0 if result.status == "ok" else 1
   ```

2. **Add to runner** (`scripts/run_integrity_checks.py`):
   ```python
   from scripts.my_check import main as my_check_main
   
   # In main():
   exit_code = my_check_main()
   exit_codes.append(exit_code)
   ```

3. **Document** in this file and `reports/README.md`

## Monitoring and Alerts

### Recommended Monitoring

1. **Coverage Thresholds:**
   - Warning: Coverage < 99%
   - Critical: Coverage < 95%

2. **Missing Data Patterns:**
   - Specific symbols consistently missing data
   - Time-based patterns (e.g., always missing during certain hours)
   - Increasing gap sizes over time

3. **Automated Alerts:**
   - Email/Slack notifications on failure
   - Dashboard integration for visualization
   - Log aggregation for trend analysis

### Report Retention

Reports are timestamped. Consider cleanup:

```bash
# Keep last 30 days
find reports/integrity -name "*.json" -mtime +30 -delete
find reports/integrity -name "*.txt" -mtime +30 -delete
```

Or implement retention in the check scripts.

## Best Practices

1. **Run checks regularly:** Every 6-12 hours for production systems
2. **Review reports:** Check for patterns and trends
3. **Set up alerts:** Automate notifications for failures
4. **Track metrics:** Monitor coverage trends over time
5. **Document issues:** Keep notes on known data gaps and resolutions

## Troubleshooting

### Check fails but data looks fine

- Verify timezone handling (all UTC)
- Check 5-minute boundary alignment
- Review recent data collection logs

### Reports not saving

- Check `reports/integrity/` directory exists
- Verify write permissions
- Check disk space

### False positives

- Ensure time range alignment (5-minute boundaries)
- Verify data collection schedule matches check timing
- Review gap detection logic

## Related Documentation

- `reports/README.md` - Report directory structure
- [Monitoring](monitoring.md) - Docker service monitoring
- [Docker Setup](docker-setup.md) - Database setup
