# Data Integrity Reports

This directory contains reports from data integrity checks.

## Structure

```
reports/
├── integrity/          # Data integrity check reports
│   ├── missing_bars_*.json              # OHLCV bars integrity (JSON)
│   ├── missing_bars_*.txt                # OHLCV bars integrity (text)
│   ├── missing_funding_rate_*.json       # Funding rate integrity (JSON)
│   ├── missing_funding_rate_*.txt       # Funding rate integrity (text)
│   ├── missing_open_interest_*.json      # Open interest integrity (JSON)
│   ├── missing_open_interest_*.txt      # Open interest integrity (text)
│   ├── missing_basis_*.json              # Basis integrity (JSON)
│   ├── missing_basis_*.txt               # Basis integrity (text)
│   ├── missing_global_long_short_account_*.json
│   ├── missing_global_long_short_account_*.txt
│   ├── missing_top_long_short_account_*.json
│   ├── missing_top_long_short_account_*.txt
│   ├── missing_top_long_short_position_*.json
│   └── missing_top_long_short_position_*.txt
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

### Missing Funding Rate Check

Checks for missing funding rate records in the last 30 days for all configured symbols. Funding rates update every 8 hours (00:00, 08:00, 16:00 UTC).

**Files:**
- `missing_funding_rate_YYYYMMDD_HHMMSS.json` - Machine-readable JSON report
- `missing_funding_rate_YYYYMMDD_HHMMSS.txt` - Human-readable text report

**Report Contents:**
- Summary statistics (total symbols, coverage, missing records)
- Detailed gap information for symbols with missing funding rate data
- List of symbols with no recent data
- List of symbols with no data at all

### Missing Open Interest Check

Checks for missing open interest records in the last 7 days for all configured symbols. Open interest updates every 5 minutes.

**Files:**
- `missing_open_interest_YYYYMMDD_HHMMSS.json` - Machine-readable JSON report
- `missing_open_interest_YYYYMMDD_HHMMSS.txt` - Human-readable text report

**Report Contents:**
- Summary statistics (total symbols, coverage, missing records)
- Detailed gap information for symbols with missing open interest data
- List of symbols with no recent data
- List of symbols with no data at all

### Missing Basis Check

Checks for missing basis (premium index) records in the last 7 days for all configured symbols. Basis updates every 5 minutes. Binance retains ~30 days.

**Files:** `missing_basis_YYYYMMDD_HHMMSS.json`, `missing_basis_YYYYMMDD_HHMMSS.txt`

### Missing Global Long/Short Account Check

Checks for missing global long/short account ratio records in the last 7 days (5m period, ~30 days retention).

**Files:** `missing_global_long_short_account_YYYYMMDD_HHMMSS.json`, `missing_global_long_short_account_YYYYMMDD_HHMMSS.txt`

### Missing Top Long/Short Account Check

Checks for missing top-trader long/short account ratio records in the last 7 days (5m period, ~30 days retention).

**Files:** `missing_top_long_short_account_YYYYMMDD_HHMMSS.json`, `missing_top_long_short_account_YYYYMMDD_HHMMSS.txt`

### Missing Top Long/Short Position Check

Checks for missing top-trader long/short position ratio records in the last 7 days (5m period, ~30 days retention).

**Files:** `missing_top_long_short_position_YYYYMMDD_HHMMSS.json`, `missing_top_long_short_position_YYYYMMDD_HHMMSS.txt`

## Running Checks

### Manual Execution

```bash
# Run missing bars check
python scripts/integrity/check_missing_bars.py

# Run funding rate check
python scripts/integrity/check_missing_funding_rate.py

# Run open interest check
python scripts/integrity/check_missing_open_interest.py

# Run futures market data checks (basis, global/top L/S account & position)
python scripts/integrity/check_missing_basis.py
python scripts/integrity/check_missing_global_long_short_account.py
python scripts/integrity/check_missing_top_long_short_account.py
python scripts/integrity/check_missing_top_long_short_position.py

# Run all integrity checks
python scripts/integrity/run_integrity_checks.py
```

### Scheduled Execution

#### Linux/Mac (cron)

Add to crontab (`crontab -e`):

```bash
# Run integrity checks every 6 hours
0 */6 * * * cd /path/to/Crypto-LS && python scripts/integrity/run_integrity_checks.py >> logs/integrity.log 2>&1
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
    command: python scripts/integrity/run_integrity_checks.py
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

# Windows PowerShell equivalent
Get-ChildItem reports/integrity -Filter *.json | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
Get-ChildItem reports/integrity -Filter *.txt | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
```

## Monitoring

- Check reports regularly to identify data collection issues
- Set up alerts if coverage drops below thresholds
- Monitor for patterns in missing data (specific symbols, time ranges)

## Exit Codes

- `0`: All checks passed
- `1`: One or more checks failed (missing data, errors, etc.)

Use exit codes for automated monitoring and alerting.
