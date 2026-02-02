# Standard Operating Procedure: Adding a New Data Table

This SOP documents the step-by-step process for adding a new data collection table to the Crypto-LS system, following the established patterns used for funding rate, open interest, and other data types.

## Overview

Adding a new data table involves:
1. **Planning** - Understand the data source API and requirements
2. **Database Schema** - Create Alembic migration
3. **Collector Method** - Add API fetch method
4. **Storage Methods** - Add database write/read methods
5. **Update Task** - Create incremental update task
6. **Register Task** - Add to task registry
7. **Test Script** - Create test backfill for first 10 symbols
8. **Backfill Script** - Create full backfill script
9. **Update Service** - Rebuild and restart Docker service
10. **Visualization** (Optional) - Create Streamlit page

---

## Step 1: Planning

### 1.1 Research the Data Source

- **API Endpoint**: Identify the exact endpoint URL and parameters
- **Response Format**: Understand the response structure
- **Rate Limits**: Check request weights and rate limits
- **Data Retention**: Determine historical data availability (e.g., 30 days, 1 year, unlimited)
- **Update Frequency**: How often does the data update? (e.g., every 5 minutes, every 8 hours)
- **Authentication**: Does it require API keys?

### 1.2 Design the Database Schema

- **Primary Key**: Determine unique identifier (e.g., `(symbol, timestamp)`, `(symbol, period, timestamp)`)
- **Columns**: List all fields to store
- **Indexes**: Plan indexes for common query patterns (e.g., `(symbol, period)`)
- **Data Types**: Choose appropriate types (String, BigInteger for timestamps, Float for prices/rates)

### 1.3 Plan Collection Strategy

- **Incremental Updates**: How to track latest data? (timestamp, ID-based)
- **Tail Refresh**: How many records to re-fetch for corrections? (typically 1-3)
- **Pagination**: How to paginate through historical data? (time-based, ID-based)
- **Error Handling**: What errors to handle? (429 rate limits, empty responses, timeouts)

---

## Step 2: Database Migration

### 2.1 Create Alembic Migration File

**File**: `alembic/versions/XXX_add_<table_name>.py`

**Template**:
```python
"""Add <table_name> table.

Revision ID: XXX
Revises: <previous_revision>
Create Date: YYYY-MM-DD
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "XXX"
down_revision: Union[str, None] = "<previous_revision>"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "<table_name>",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        # Add other columns
        sa.PrimaryKeyConstraint("symbol", "timestamp"),  # Adjust as needed
    )
    op.create_index(
        "ix_<table_name>_symbol",
        "<table_name>",
        ["symbol"],
        unique=False,
    )

def downgrade() -> None:
    op.drop_index("ix_<table_name>_symbol", table_name="<table_name>")
    op.drop_table("<table_name>")
```

### 2.2 Run Migration

```bash
# From project root
alembic upgrade head
```

**Verify**: Check database schema using pgAdmin or `psql`.

---

## Step 3: Collector Method

### 3.1 Add Fetch Method to `data/collector.py`

**Pattern**:
```python
def fetch_<data_type>(
    self,
    symbol: str,  # or pair, depending on API
    # ... other required parameters
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[tuple]:
    """
    Fetch <data_type> from Binance API.
    Returns list of tuples: (timestamp, field1, field2, ...).
    """
    url = f"{self._fapi_base}/<endpoint>"  # or self._base for Spot
    params: dict[str, Any] = {
        "symbol": symbol,  # or "pair" if API uses pair
        "limit": limit or self._limit,
    }
    if start_time is not None:
        params["startTime"] = start_time
    if end_time is not None:
        params["endTime"] = end_time
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        raw = resp.json()
        
        # Handle empty responses
        if not isinstance(raw, list):
            logger.warning("fetch_<data_type> %s: invalid response format", symbol)
            return []
        if not raw:
            logger.debug("fetch_<data_type> %s: empty response", symbol)
            return []
        
        # Parse response and return tuples
        rows = []
        for r in raw:
            rows.append((
                int(r["timestamp"]),  # or appropriate field
                float(r["field1"]),
                float(r["field2"]),
                # ... other fields
            ))
        return rows
    except Exception as e:
        logger.warning("fetch_<data_type> failed %s: %s", symbol, e, exc_info=True)
        raise
```

**Key Points**:
- Handle empty responses gracefully
- Convert empty strings to None/0.0 where appropriate
- Use appropriate base URL (`_base` for Spot, `_fapi_base` for Futures)
- Return list of tuples matching your storage method signature

---

## Step 4: Storage Methods

### 4.1 Add Methods to `data/storage.py`

**Pattern** (following `write_open_interest` / `read_open_interest`):

```python
# SQL constant
<DATA_TYPE>_UPSERT_SQL = """
INSERT INTO <table_name> (symbol, timestamp, field1, field2, ...)
VALUES (:symbol, :timestamp, :field1, :field2, ...)
ON CONFLICT (symbol, timestamp) DO UPDATE SET
  field1 = EXCLUDED.field1,
  field2 = EXCLUDED.field2,
  ...
"""

def write_<data_type>(
    self,
    symbol: str,
    rows: Sequence[tuple],  # (timestamp, field1, field2, ...)
) -> None:
    """Write <data_type> rows."""
    if not rows:
        return
    with self._engine.connect() as conn:
        try:
            for r in rows:
                conn.execute(
                    text(self.<DATA_TYPE>_UPSERT_SQL),
                    {
                        "symbol": symbol,
                        "timestamp": r[0],
                        "field1": r[1],
                        "field2": r[2],
                        # ... map tuple fields to SQL params
                    },
                )
            conn.commit()
        except Exception as e:
            logger.error("write_<data_type> failed symbol=%s rows=%s: %s", symbol, len(rows), e, exc_info=True)
            raise

def read_<data_type>(
    self,
    symbol: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> List[tuple]:
    """
    Read <data_type> rows for a symbol.
    Returns list of tuples: (timestamp, field1, field2, ...).
    """
    sql = """
        SELECT timestamp, field1, field2, ...
        FROM <table_name>
        WHERE symbol = :symbol
    """
    params: dict[str, Any] = {"symbol": symbol}
    if start_time is not None:
        sql += " AND timestamp >= :start_time"
        params["start_time"] = start_time
    if end_time is not None:
        sql += " AND timestamp < :end_time"
        params["end_time"] = end_time
    sql += " ORDER BY timestamp ASC"
    
    with self._engine.connect() as conn:
        result = conn.execute(text(sql), params)
        rows = result.fetchall()
    return [(int(r[0]), float(r[1]), float(r[2]), ...) for r in rows]

def get_latest_<data_type>_time(self, symbol: str) -> Optional[int]:
    """Return the latest (max) timestamp for the given symbol, or None if no rows."""
    sql = """
        SELECT MAX(timestamp) FROM <table_name>
        WHERE symbol = :symbol
    """
    with self._engine.connect() as conn:
        result = conn.execute(text(sql), {"symbol": symbol})
        row = result.fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])
```

**Key Points**:
- Use `ON CONFLICT UPDATE` for upsert logic (or `DO NOTHING` if duplicates should be ignored)
- Handle empty rows gracefully
- Return tuples matching collector method format
- Use appropriate timestamp field name (e.g., `funding_time`, `timestamp`)

---

## Step 5: Update Task

### 5.1 Create Task File

**File**: `data/updates/binance_<data_type>.py`

**Template** (following `binance_open_interest.py` pattern):

```python
"""
Binance <Data Type> incremental update task.

Fetches new records after the last stored record and re-fetches the last
N records (tail refresh) so real-time corrections from the API overwrite existing rows.
Uses Collector + Storage + settings (delay, 429 retry). Registered in data.updates;
the general entry point (run_data_updater.py) invokes run() at fixed interval.
"""

import logging
import time
from typing import List, Optional

import requests

from config import settings
from data import Collector, Storage

logger = logging.getLogger(__name__)

TAIL_RECORDS = 3  # Refresh last 3 records (adjust based on update frequency)
DELAY_SEC = 0.1
MAX_429_RETRIES = 5
# Add any data-type-specific constants

def _fetch_<data_type>_with_retry(
    collector: Collector,
    symbol: str,
    *,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int,
) -> List[tuple]:
    """Call collector.fetch_<data_type>; on 429, sleep Retry-After and retry."""
    for attempt in range(MAX_429_RETRIES):
        try:
            return collector.fetch_<data_type>(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < MAX_429_RETRIES - 1:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning(
                    "429 rate limit, sleeping %s s (attempt %s)", retry_after, attempt + 1
                )
                time.sleep(retry_after)
                continue
            raise
    return []

def run() -> None:
    """One-shot Binance <Data Type> incremental update (tail refresh + new records)."""
    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()
    limit = settings.ohlcv_limit_per_request  # or appropriate limit

    for symbol in settings.symbols:
        latest = storage.get_latest_<data_type>_time(symbol)
        if latest is None:
            logger.debug("Skip %s: no stored <data_type> data", symbol)
            continue
        
        # Calculate start time for tail refresh
        # Adjust based on update frequency (e.g., 8 hours for funding rate, 5 minutes for open interest)
        start_time_ms = max(0, latest - (TAIL_RECORDS - 1) * INTERVAL_MS)
        
        try:
            rows = _fetch_<data_type>_with_retry(
                collector,
                symbol,
                start_time=start_time_ms,
                limit=limit,
            )
            if not rows:
                continue
            
            storage.write_<data_type>(symbol, rows)
            logger.info("%s: wrote %s <data_type> records (tail refresh + new)", symbol, len(rows))
        except Exception as e:
            logger.warning("%s <data_type> incremental update failed: %s", symbol, e)
        time.sleep(DELAY_SEC)
```

**Key Points**:
- Follow the same pattern as existing tasks
- Calculate tail refresh start time based on update frequency
- Handle missing data gracefully (skip if no stored data)
- Log successes and failures

---

## Step 6: Register Task

### 6.1 Update `data/updates/__init__.py`

Add import and register task:

```python
from data.updates import (
    binance_ohlcv,
    binance_funding_rate,
    binance_open_interest,
    binance_<data_type>,  # Add import
)

# Registry: (name, run) per data source; add new sources here.
TASKS: List[tuple[str, Callable[[], None]]] = [
    ("binance_ohlcv", binance_ohlcv.run),
    ("binance_funding_rate", binance_funding_rate.run),
    ("binance_open_interest", binance_open_interest.run),
    ("binance_<data_type>", binance_<data_type>.run),  # Add task
]
```

**Verify**: Check that the import works and task is registered.

---

## Step 7: Test Script (First 10 Symbols)

### 7.1 Create Test Backfill Script

**File**: `scripts/backfill/test_backfill_<data_type>.py`

**Template** (following `test_backfill_open_interest.py` pattern):

```python
"""
Test script: Backfill <Data Type> for first 10 symbols only.
Quick test to verify collection works before running full backfill.

Run from project root: python scripts/backfill/test_backfill_<data_type>.py
"""

import logging
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

# Run from project root
if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings, setup_logging
from data import Collector, Storage

logger = logging.getLogger(__name__)

# Test with shorter time range first
DAYS_BACK = 7  # Adjust based on data availability
MS_PER_DAY = int(24 * 3600 * 1000)

DELAY_SEC = 0.2
MAX_429_RETRIES = 5
MAX_EMPTY_RETRIES = 3
EMPTY_RETRY_DELAY = 0.5
LIMIT = 500  # Adjust based on API limit

def fetch_<data_type>_with_retry(
    collector: Collector,
    symbol: str,
    *,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int,
) -> list:
    """Call collector with retry logic for 429 and empty responses."""
    # Similar to update task, but with empty response retry logic
    # ... implementation

def main() -> None:
    setup_logging()
    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()
    
    # Test with first 10 symbols
    symbols = settings.symbols[:10]
    
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - (DAYS_BACK * MS_PER_DAY)
    
    logger.info("TEST: <Data Type> backfill for %s symbols, last %s days", len(symbols), DAYS_BACK)
    
    for symbol in tqdm(symbols, desc="Symbols"):
        # Pagination logic here
        # ... fetch and write data
        
    logger.info("TEST: Completed backfill for %s symbols", len(symbols))

if __name__ == "__main__":
    main()
```

**Key Points**:
- Limit to first 10 symbols for testing
- Use `tqdm` for progress bars
- Test with shorter time range (e.g., 7 days)
- Include comprehensive logging for debugging
- Handle pagination correctly (especially for APIs that return newest-first)

---

## Step 8: Backfill Script (All Symbols)

### 8.1 Create Full Backfill Script

**File**: `scripts/backfill/backfill_<data_type>.py`

**Template** (following `backfill_open_interest.py` pattern):

```python
"""
Backfill <Data Type>: maximum available historical data, for all symbols in settings.symbols.

Run from project root: python scripts/backfill/backfill_<data_type>.py
"""

import logging
import sys
import time
from pathlib import Path

import requests

# Run from project root
if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings, setup_logging
from data import Collector, Storage

logger = logging.getLogger(__name__)

DAYS_BACK = 30  # Adjust based on data availability
MS_PER_DAY = int(24 * 3600 * 1000)

DELAY_SEC = 0.2
MAX_429_RETRIES = 5
LIMIT = 500  # Adjust based on API limit

def fetch_<data_type>_with_retry(
    collector: Collector,
    symbol: str,
    *,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int,
) -> list:
    """Call collector with retry logic."""
    # Similar to test script, but may omit empty response retries for full backfill
    # ... implementation

def main() -> None:
    setup_logging()
    collector = Collector(use_testnet=settings.use_testnet)
    storage = Storage()
    
    symbols = settings.symbols
    
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - (DAYS_BACK * MS_PER_DAY)
    
    logger.info("Starting <Data Type> backfill: %s symbols, target: %s days", len(symbols), DAYS_BACK)
    
    for symbol in symbols:
        # Pagination logic here
        # ... fetch and write data
        
    logger.info("Completed backfill for %s symbols", len(symbols))

if __name__ == "__main__":
    main()
```

**Key Points**:
- Process all symbols in `settings.symbols`
- Use maximum available historical data
- Implement proper pagination (handle APIs that return newest-first vs oldest-first)
- Add comprehensive logging for batch progress
- Filter rows to ensure only data within time range is saved

---

## Step 9: Test Run (First 10 Symbols)

### 9.1 Run Test Script

```bash
# From project root
python scripts/backfill/test_backfill_<data_type>.py
```

### 9.2 Verify Results

- **Check Logs**: Review output for errors or warnings
- **Check Database**: Verify data was written correctly
  ```sql
  SELECT COUNT(*), MIN(timestamp), MAX(timestamp) 
  FROM <table_name> 
  WHERE symbol = 'BTCUSDT';
  ```
- **Verify Data Quality**: Check for gaps, duplicates, or incorrect values
- **Check Coverage**: Ensure expected number of records for time range

### 9.3 Fix Issues

- **Pagination Issues**: Adjust pagination logic if data is missing or duplicated
- **Error Handling**: Improve error handling based on observed failures
- **Rate Limits**: Adjust delays if hitting rate limits
- **Data Parsing**: Fix parsing if data format differs from expected

---

## Step 10: Full Backfill (All Symbols)

### 10.1 Run Full Backfill Script

```bash
# From project root
python scripts/backfill/backfill_<data_type>.py
```

**Note**: This may take a long time depending on:
- Number of symbols (100+)
- Historical data range
- API rate limits
- Network speed

### 10.2 Monitor Progress

- Watch logs for errors
- Check database periodically for progress
- Monitor for rate limit issues

### 10.3 Verify Completion

- Check all symbols have data
- Verify date ranges match expectations
- Run data integrity checks if available

---

## Step 11: Update Service

### 11.1 Rebuild Docker Container

```bash
# Rebuild the data-updater container with new code
docker compose build data-updater
```

### 11.2 Restart Service

```bash
# Restart with force recreate to ensure latest code
docker compose up -d --force-recreate data-updater
```

### 11.3 Verify Service is Running

```bash
# Check container status
docker compose ps

# Check logs
docker logs --tail 100 crypto-ls-data-updater

# Or check log file inside container
docker exec crypto-ls-data-updater cat /app/logs/app.log | tail -50
```

### 11.4 Verify Task is Executing

- Check logs for task execution messages
- Verify data is being collected incrementally
- Monitor for any errors

---

## Step 12: Visualization (Optional)

### 12.1 Create Streamlit Page

**File**: `viz/pages/<number>_<data_type>.py`

Follow the pattern from `8_open_interest.py` or `9_funding_rate.py`:

- Symbol selector
- Time range slider
- Statistics display
- Plotly charts
- Raw data table

### 12.2 Update `viz/app.py`

Add the new page to the sidebar navigation list.

### 12.3 Test Visualization

```bash
streamlit run viz/app.py
```

Navigate to the new page and verify it displays data correctly.

---

## Step 13: Documentation

### 13.1 Update Architecture Documentation

**File**: `docs/ARCHITECTURE.md`

- Add new table to Database section
- Add new task to Data Flow section
- Update Module Architecture section
- Add to Operations Flow section

### 13.2 Update Reports Documentation (if applicable)

**File**: `reports/README.md`

If you created integrity checks, document the new report types.

### 13.3 Update Data Updates README

**File**: `data/updates/README.md`

Add the new task to the "Implemented" section.

---

## Checklist

Use this checklist to ensure all steps are completed:

- [ ] **Planning**
  - [ ] API endpoint researched
  - [ ] Database schema designed
  - [ ] Collection strategy planned

- [ ] **Database**
  - [ ] Alembic migration created
  - [ ] Migration tested (`alembic upgrade head`)
  - [ ] Schema verified in database

- [ ] **Collector**
  - [ ] `fetch_<data_type>()` method added
  - [ ] Error handling implemented
  - [ ] Empty response handling added

- [ ] **Storage**
  - [ ] `write_<data_type>()` method added
  - [ ] `read_<data_type>()` method added
  - [ ] `get_latest_<data_type>_time()` method added
  - [ ] SQL upsert logic tested

- [ ] **Update Task**
  - [ ] Task file created (`data/updates/binance_<data_type>.py`)
  - [ ] Tail refresh logic implemented
  - [ ] Error handling added
  - [ ] Task registered in `data/updates/__init__.py`

- [ ] **Test Script**
  - [ ] Test script created (`scripts/backfill/test_backfill_<data_type>.py`)
  - [ ] Limited to first 10 symbols
  - [ ] Progress bars added (`tqdm`)
  - [ ] Comprehensive logging added

- [ ] **Backfill Script**
  - [ ] Full backfill script created (`scripts/backfill/backfill_<data_type>.py`)
  - [ ] Pagination logic implemented correctly
  - [ ] Handles all symbols
  - [ ] Comprehensive logging added

- [ ] **Testing**
  - [ ] Test script runs successfully
  - [ ] Data verified in database
  - [ ] Full backfill runs successfully
  - [ ] All symbols have data

- [ ] **Service Update**
  - [ ] Docker container rebuilt
  - [ ] Service restarted
  - [ ] Task executing correctly
  - [ ] Incremental updates working

- [ ] **Visualization** (Optional)
  - [ ] Streamlit page created
  - [ ] Page added to sidebar
  - [ ] Visualization tested

- [ ] **Documentation**
  - [ ] Architecture docs updated
  - [ ] Reports docs updated (if applicable)
  - [ ] Data updates README updated

---

## Common Patterns and Examples

### Pattern 1: Time-Based Pagination (Newest-First API)

For APIs that return newest-first (like open interest):

```python
# Start from current time, move backward
current_end_time = end_time_ms
start_time_ms = end_time_ms - (DAYS_BACK * MS_PER_DAY)

while True:
    rows = fetch_data(start_time=start_time_ms, end_time=current_end_time, limit=LIMIT)
    if not rows:
        break
    
    # Filter rows to time range
    filtered_rows = [r for r in rows if start_time_ms <= r[0] < end_time_ms]
    
    # Find oldest timestamp
    oldest_timestamp = min(r[0] for r in rows)
    
    # Move backward
    current_end_time = oldest_timestamp - 1
    
    # Stop condition
    if oldest_timestamp <= start_time_ms:
        break
```

### Pattern 2: ID-Based Pagination

For APIs that support `fromId` pagination:

```python
from_id = None  # Start from most recent
while True:
    rows = fetch_data(from_id=from_id, limit=LIMIT)
    if not rows:
        break
    
    # Process rows
    # ...
    
    # Get last ID for next batch
    from_id = rows[-1][0] + 1  # Adjust based on ID field
```

### Pattern 3: Time-Based Pagination (Oldest-First API)

For APIs that return oldest-first:

```python
current_start_time = start_time_ms
end_time_ms = int(time.time() * 1000)

while current_start_time < end_time_ms:
    rows = fetch_data(start_time=current_start_time, end_time=end_time_ms, limit=LIMIT)
    if not rows:
        break
    
    # Process rows
    # ...
    
    # Move forward
    newest_timestamp = max(r[0] for r in rows)
    current_start_time = newest_timestamp + 1
```

---

## Troubleshooting

### Issue: No Data After Backfill

**Check**:
- API endpoint URL is correct
- Parameters are correct (symbol format, time range)
- Database migration ran successfully
- Data is being written (check logs)

**Solution**: Verify API response format matches expected format, check database for any errors.

### Issue: Missing Data (Gaps)

**Check**:
- Pagination logic is correct
- Stop conditions are working
- Time range filtering is correct

**Solution**: Review pagination logic, add more detailed logging, verify API behavior.

### Issue: Rate Limit Errors

**Check**:
- Delay between requests
- Request weight per call
- Concurrent requests

**Solution**: Increase delays, reduce batch sizes, implement exponential backoff.

### Issue: Duplicate Data

**Check**:
- Primary key constraint
- Upsert logic (ON CONFLICT UPDATE)
- Pagination overlap

**Solution**: Verify primary key, check for pagination overlap, ensure upsert logic is correct.

### Issue: Service Not Collecting Data

**Check**:
- Task is registered in `TASKS` list
- Container was rebuilt
- Service is running
- Logs show task execution

**Solution**: Verify task registration, rebuild container, check logs for errors.

---

## Related Documentation

- [Architecture Overview](../ARCHITECTURE.md) - System architecture
- [Data Integrity](data-integrity.md) - Data quality checks
- [Monitoring](monitoring.md) - Service monitoring
- [Docker Setup](docker-setup.md) - Docker service management

---

## Examples

### Completed Implementations

1. **Funding Rate** (`funding_rate` table)
   - Updates every 8 hours
   - Primary key: `(symbol, funding_time)`
   - Tail refresh: 1 record

2. **Open Interest** (`open_interest` table)
   - Updates every 5 minutes
   - Primary key: `(symbol, period, timestamp)`
   - Tail refresh: 3 records
   - 30-day historical limit

3. **OHLCV** (`ohlcv` table)
   - Updates every 5 minutes
   - Primary key: `(symbol, timeframe, open_time)`
   - Tail refresh: 3 bars

Refer to these implementations as reference examples when adding new data types.
