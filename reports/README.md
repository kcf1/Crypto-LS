# Data Integrity Reports

This directory contains reports from data integrity checks.

## Structure

```
reports/
├── integrity/          # Data integrity check reports
│   ├── missing_bars_*.json    # JSON format reports
│   └── missing_bars_*.txt      # Human-readable text reports
└── README.md           # This file
```

## Reports

### Missing Bars Check

Checks for missing 5-minute OHLCV bars in the last 48 hours for all configured symbols.

**Files:**
- `missing_bars_YYYYMMDD_HHMMSS.json` - Machine-readable JSON report
- `missing_bars_YYYYMMDD_HHMMSS.txt` - Human-readable text report

**Report Contents:**
- Summary statistics (total symbols, coverage, missing bars)
- Detailed gap information for symbols with missing data
- List of symbols with no recent data
- List of symbols with no data at all

## Running Checks

### Manual Execution

```bash
# Run missing bars check
python scripts/check_missing_bars.py

# Run all integrity checks
python scripts/run_integrity_checks.py
```

### Scheduled Execution

#### Linux/Mac (cron)

Add to crontab (`crontab -e`):

```bash
# Run integrity checks every 6 hours
0 */6 * * * cd /path/to/Crypto-LS && python scripts/run_integrity_checks.py >> logs/integrity.log 2>&1
```

#### Windows (Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (e.g., every 6 hours)
4. Set action: Start a program
5. Program: `python`
6. Arguments: `scripts/run_integrity_checks.py`
7. Start in: `F:\Document\GitHub\Crypto-LS`

#### Docker (if running in container)

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
    restart: "no"  # Run on schedule, not continuously
```

Then schedule with cron or Task Scheduler to run:
```bash
docker compose run --rm integrity-checker
```

## Report Retention

Reports are saved with timestamps. Consider implementing a cleanup script to remove old reports:

```bash
# Keep only last 30 days of reports
find reports/integrity -name "*.json" -mtime +30 -delete
find reports/integrity -name "*.txt" -mtime +30 -delete
```

## Monitoring

- Check reports regularly to identify data collection issues
- Set up alerts if coverage drops below thresholds
- Monitor for patterns in missing data (specific symbols, time ranges)

## Exit Codes

- `0`: All checks passed
- `1`: One or more checks failed (missing data, errors, etc.)

Use exit codes for automated monitoring and alerting.
