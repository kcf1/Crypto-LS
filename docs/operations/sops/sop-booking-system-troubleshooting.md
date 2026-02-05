# SOP: Booking System Troubleshooting and Fixes

## Purpose

This SOP provides a systematic approach to diagnose and fix issues in the booking system, including orders, trades, positions, balances, and data synchronization problems.

## Prerequisites

- Access to order-executor service API (default: `http://localhost:8000`)
- Access to Docker containers (if running via Docker)
- Access to database (PostgreSQL or SQLite)
- Access to service logs
- Understanding of booking system architecture (see [Booking System Architecture](../../plans/architecture/booking-system-and-recon.md))

## Overview

The booking system consists of:
- **Order Executor Service**: HTTP API + Redis stream consumer for order placement and booking
- **Fill Sync Service**: Background service that syncs fills from Binance
- **Database**: PostgreSQL/SQLite storing orders, trades, positions, balances
- **Redis**: Message queue for order placement
- **GUI**: Streamlit interface for manual operations

## Troubleshooting Flow

```
1. Initial Assessment
   ↓
2. Check Service Health
   ↓
3. Verify GUI Data Display (if GUI screenshot provided)
   ↓
4. Check Database Issues
   ↓
5. Check API Issues
   ↓
6. Check Data Transmission Issues
   ↓
7. Run Reconciliation Checks
   ↓
8. Apply Fixes
   ↓
9. Verify Fixes
```

---

## Step 1: Initial Assessment

### 1.1 Gather Information

**Collect the following:**
- **Symptom description**: What is wrong? (e.g., "Orders not appearing", "Trades missing", "Balances incorrect")
- **GUI screenshot** (if available): Shows what the user sees
- **Error messages**: From GUI, API, or logs
- **Timeframe**: When did the issue start?
- **Affected book_id**: Which book(s) are affected?
- **Affected symbols**: Which trading pairs?

**Document:**
```bash
# Create a troubleshooting log
echo "Issue: [description]" > troubleshooting_log.txt
echo "Time: $(date)" >> troubleshooting_log.txt
echo "Book ID: [book_id]" >> troubleshooting_log.txt
echo "Symbols: [symbols]" >> troubleshooting_log.txt
```

### 1.2 Identify Issue Category

**Common issue categories:**
- **Data missing**: Orders/trades/positions/balances not appearing
- **Data incorrect**: Wrong values, mismatched quantities
- **Data duplication**: Same record appearing multiple times
- **Sync issues**: Data not syncing from Binance
- **API errors**: Endpoints returning errors
- **Service down**: Services not running

### 1.3 Distinguish Actual Issues from Expected Behavior

**Before proceeding with troubleshooting, verify if the observed behavior is actually an issue or expected system behavior.**

#### Expected Behaviors (NOT Issues)

**Fill Sync Delays:**
- **Expected**: Fill sync runs every **60 seconds** (configurable)
- **Expected**: Trades may not appear immediately after order placement
- **Expected**: There can be a delay of up to 60 seconds before fills are synced
- **Check**: If trade was placed less than 60 seconds ago, wait and check again
- **Action**: Only investigate if delay exceeds 2 minutes

**Order Status Updates:**
- **Expected**: Order status updates from `NEW` → `PARTIALLY_FILLED` → `FILLED` as trades are recorded
- **Expected**: Status updates happen when fill sync runs (not instant)
- **Check**: Verify order was placed more than 60 seconds ago before investigating
- **Action**: Check fill-sync logs to confirm sync cycle completed

**Position/Balance Updates:**
- **Expected**: Positions and balances update only when trades are recorded
- **Expected**: Updates happen after fill sync runs (not instant)
- **Expected**: Positions/balances are derived from trades, not polled from exchange
- **Check**: Verify trades exist before expecting position/balance updates
- **Action**: Only investigate if trades exist but positions/balances are wrong

**Fill Sync Scope:**
- **Expected**: Fill sync only processes **unfilled orders** (`NEW` or `PARTIALLY_FILLED`)
- **Expected**: Filled orders are skipped by fill sync
- **Expected**: Fill sync uses order-driven approach (finds orders first, then fetches their trades)
- **Check**: Verify order status - if already `FILLED`, fill sync won't process it
- **Action**: This is expected behavior, not an issue

**GUI Cache:**
- **Expected**: Streamlit GUI caches API responses (TTL: 10-60 seconds depending on endpoint)
- **Expected**: GUI may show stale data until cache expires
- **Check**: Refresh GUI or wait for cache TTL to expire
- **Action**: Clear browser cache or restart Streamlit if needed

**Book Filtering:**
- **Expected**: Data is filtered by `book_id` - records from other books won't appear
- **Expected**: If no `book_id` filter, all books' data is shown
- **Check**: Verify correct `book_id` is being used in filters
- **Action**: Check if data exists in other books

**Reconciliation Timing:**
- **Expected**: Reconciliations compare ledger vs exchange - some mismatches are normal
- **Expected**: Small timing differences (< 60 seconds) are expected due to sync delays
- **Expected**: Reconciliations should be run periodically (daily), not continuously
- **Check**: Verify if mismatch is within expected sync window
- **Action**: Only investigate persistent mismatches (> 2 minutes old)

**Testnet vs Production:**
- **Expected**: Testnet orders won't appear in production data and vice versa
- **Expected**: `USE_TESTNET_FOR_ORDERS` setting determines which environment is used
- **Check**: Verify `.env` configuration matches expected environment
- **Action**: This is expected behavior based on configuration

**MARKET Order Price:**
- **Expected**: MARKET orders show `Price: N/A` in the GUI
- **Expected**: MARKET orders don't have a fixed price - they execute at market price
- **Expected**: The actual execution price is recorded in trades, not in the order record
- **Expected**: Binance API may not return `price` field for MARKET orders
- **Check**: Verify order type is MARKET - if so, N/A is correct
- **Action**: This is expected behavior - check trades for actual execution prices

**Order Created Timestamp:**
- **Expected**: Orders should have a `created_at` timestamp
- **Issue**: If Binance doesn't return `time` field, timestamp may be missing or 0
- **Check**: Verify if `created_at` is 0 or missing in database
- **Action**: This is a bug - should use current time as fallback if Binance doesn't provide timestamp

#### Actual Issues (Require Investigation)

**Persistent Missing Data:**
- **Issue**: Trades missing after 2+ minutes from order placement
- **Issue**: Orders not appearing in database after placement
- **Issue**: Positions/balances not updating after trades are recorded
- **Action**: Proceed with troubleshooting steps

**Data Inconsistencies:**
- **Issue**: Order status says `FILLED` but sum of trades < order quantity
- **Issue**: Position quantity doesn't match sum of trades
- **Issue**: Balance doesn't match sum of trades
- **Action**: Run reconciliation checks (Step 7)

**Service Failures:**
- **Issue**: Services not running or crashing
- **Issue**: API endpoints returning 5xx errors
- **Issue**: Database connection failures
- **Action**: Check service health (Step 2)

**Sync Failures:**
- **Issue**: Fill sync service not running
- **Issue**: Fill sync errors in logs
- **Issue**: Binance API errors preventing sync
- **Action**: Check data transmission issues (Step 6)

**Duplicate Records:**
- **Issue**: Same trade appearing multiple times
- **Issue**: Same order appearing multiple times
- **Action**: Check database issues (Step 4)

#### Decision Matrix

**Ask these questions:**

1. **Timing**: How long ago did the event occur?
   - < 60 seconds → **Wait** (expected delay)
   - 60-120 seconds → **Monitor** (may be in progress)
   - > 120 seconds → **Investigate** (likely issue)

2. **Service Status**: Are services running?
   - Services down → **Issue** (Step 2)
   - Services up → Continue investigation

3. **Data Existence**: Does data exist in database?
   - Not in DB → **Issue** (investigate)
   - In DB but not in GUI → **Cache issue** (Step 3.2)
   - In DB and GUI → **Not an issue**

4. **Order Status**: What is the order status?
   - `NEW` or `PARTIALLY_FILLED` → Fill sync should process it
   - `FILLED` or `CANCELLED` → Fill sync skips it (expected)

5. **Reconciliation**: What do reconciliations show?
   - All recs pass → **Not an issue**
   - Some recs fail → **Issue** (Step 7)

**Document your findings:**
```bash
echo "Is this an actual issue? [YES/NO]" >> troubleshooting_log.txt
echo "Reason: [explanation]" >> troubleshooting_log.txt
echo "Expected behavior: [description]" >> troubleshooting_log.txt
```

---

## Step 2: Check Service Health

### 2.1 Check Order Executor Service

```bash
# Check if service is running
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "healthy",
#   "database_connected": true,
#   "redis_connected": true
# }
```

**If service is down:**
```bash
# Check Docker container status
docker compose ps order-executor

# Check logs
docker compose logs --tail=50 order-executor

# Restart service
docker compose restart order-executor

# If still failing, check for errors
docker compose logs order-executor | grep -i error
```

### 2.2 Check Fill Sync Service

```bash
# Check if service is running
docker compose ps fill-sync

# Check logs
docker compose logs --tail=50 fill-sync

# Look for errors
docker compose logs fill-sync | grep -i error
```

### 2.3 Check Database Connection

```bash
# Via order-executor health endpoint
curl http://localhost:8000/health | jq '.database_connected'

# Direct database check (PostgreSQL)
docker compose exec postgres psql -U postgres -d crypto_ls -c "SELECT 1;"

# Direct database check (SQLite)
sqlite3 data.db "SELECT 1;"
```

### 2.4 Check Redis Connection

```bash
# Via order-executor health endpoint
curl http://localhost:8000/health | jq '.redis_connected'

# Direct Redis check
docker compose exec redis redis-cli ping
# Expected: PONG
```

**If services are unhealthy:**
- Check Docker logs for errors
- Verify environment variables (`.env` file)
- Check network connectivity between services
- Verify resource limits (CPU, memory)

---

## Step 3: Verify GUI Data Display (if GUI screenshot provided)

### 3.1 Compare GUI with Database

**If GUI shows incorrect/missing data:**

1. **Check what GUI is fetching:**
   ```bash
   # Check browser network tab (F12) for API calls
   # Or check GUI logs
   ```

2. **Verify API response matches database:**
   ```bash
   # Get orders via API
   curl "http://localhost:8000/orders?book_id=test_book&limit=10" | jq
   
   # Get orders directly from database
   docker compose exec postgres psql -U postgres -d crypto_ls -c "SELECT * FROM orders WHERE book_id='test_book' LIMIT 10;"
   ```

3. **Compare values:**
   - Do IDs match?
   - Do quantities match?
   - Do timestamps match?
   - Are there records in DB but not in GUI? (API filter issue)
   - Are there records in GUI but not in DB? (Cache issue)

### 3.2 Check GUI Cache

**Streamlit caches API responses:**
- Clear browser cache
- Restart Streamlit app
- Check `@st.cache_data` TTL values in GUI code

### 3.3 Verify API Filters

**Check if filters are working correctly:**
```bash
# Test with different filters
curl "http://localhost:8000/orders?book_id=test_book" | jq '.orders | length'
curl "http://localhost:8000/orders?symbol=BTCUSDT" | jq '.orders | length'
curl "http://localhost:8000/orders" | jq '.orders | length'
```

**Expected:** Filtered results should be subsets of unfiltered results.

---

## Step 4: Check Database Issues

### 4.1 Check Database Connectivity

```bash
# PostgreSQL
docker compose exec postgres psql -U postgres -d crypto_ls -c "\dt"

# SQLite
sqlite3 data.db ".tables"
```

### 4.2 Check Data Integrity

**Check for missing foreign keys:**
```sql
-- Check trades without matching orders
SELECT t.* FROM trades t
LEFT JOIN orders o ON t.order_id = o.id
WHERE t.order_id IS NOT NULL AND o.id IS NULL;

-- Check trades with invalid book_id
SELECT t.* FROM trades t
LEFT JOIN books b ON t.book_id = b.id
WHERE b.id IS NULL;

-- Check orders with invalid book_id
SELECT o.* FROM orders o
LEFT JOIN books b ON o.book_id = b.id
WHERE b.id IS NULL;
```

### 4.3 Check Data Consistency

**Verify order status matches filled quantity:**
```sql
-- Orders marked FILLED but sum of trades < order quantity
SELECT o.id, o.quantity, o.status,
       COALESCE(SUM(t.quantity), 0) as filled_qty
FROM orders o
LEFT JOIN trades t ON t.order_id = o.id
WHERE o.status = 'FILLED'
GROUP BY o.id, o.quantity, o.status
HAVING COALESCE(SUM(t.quantity), 0) < o.quantity - 0.000000000001;
```

**Verify positions match trades:**
```sql
-- Compare position quantity with sum of trades
SELECT p.symbol, p.book_id, p.quantity as pos_qty,
       SUM(CASE WHEN t.side = 'BUY' THEN t.quantity ELSE -t.quantity END) as calc_qty
FROM positions p
LEFT JOIN trades t ON t.symbol = p.symbol AND t.book_id = p.book_id
GROUP BY p.symbol, p.book_id, p.quantity
HAVING ABS(p.quantity - COALESCE(SUM(CASE WHEN t.side = 'BUY' THEN t.quantity ELSE -t.quantity END), 0)) > 0.000000000001;
```

### 4.4 Check for Duplicate Records

```sql
-- Duplicate trades (same exchange_trade_id)
SELECT exchange_trade_id, COUNT(*) as count
FROM trades
WHERE exchange_trade_id IS NOT NULL
GROUP BY exchange_trade_id
HAVING COUNT(*) > 1;

-- Duplicate orders (same exchange_order_id)
SELECT exchange_order_id, COUNT(*) as count
FROM orders
WHERE exchange_order_id IS NOT NULL
GROUP BY exchange_order_id
HAVING COUNT(*) > 1;
```

### 4.5 Check Database Schema

```bash
# Verify tables exist
docker compose exec postgres psql -U postgres -d crypto_ls -c "\d orders"
docker compose exec postgres psql -U postgres -d crypto_ls -c "\d trades"
docker compose exec postgres psql -U postgres -d crypto_ls -c "\d positions"
docker compose exec postgres psql -U postgres -d crypto_ls -c "\d balances"
docker compose exec postgres psql -U postgres -d crypto_ls -c "\d books"
```

**If schema issues:**
```bash
# Run migrations
python -m alembic upgrade head

# Check migration status
python -m alembic current
python -m alembic history
```

---

## Step 5: Check API Issues

### 5.1 Test API Endpoints

**Health check:**
```bash
curl http://localhost:8000/health
```

**Get orders:**
```bash
curl "http://localhost:8000/orders?limit=10" | jq
```

**Get trades:**
```bash
curl "http://localhost:8000/trades?limit=10" | jq
```

**Get positions:**
```bash
curl "http://localhost:8000/positions" | jq
```

**Get balances:**
```bash
curl "http://localhost:8000/balances" | jq
```

### 5.2 Check API Error Responses

**Look for error patterns:**
```bash
# Check service logs for errors
docker compose logs order-executor | grep -i error | tail -20

# Check for specific error codes
docker compose logs order-executor | grep -E "(500|400|404|503)"
```

### 5.3 Verify API Request/Response Format

**Check request format:**
```bash
# Place test order
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "side": "BUY",
    "order_type": "LIMIT",
    "quantity": 0.001,
    "price": 50000,
    "book_id": "test_book"
  }' | jq
```

**Check response format:**
- Status code (200 = success, 4xx = client error, 5xx = server error)
- Response body structure
- Error messages (if any)

### 5.4 Check API Rate Limits

**If getting rate limit errors:**
- Check Binance API rate limits
- Check service request frequency
- Add delays between requests if needed

---

## Step 6: Check Data Transmission Issues

### 6.1 Check Redis Streams (for automated orders)

```bash
# Check Redis stream for orders
docker compose exec redis redis-cli XREAD COUNT 10 STREAMS orders:stream 0

# Check stream length
docker compose exec redis redis-cli XLEN orders:stream

# Check consumer groups
docker compose exec redis redis-cli XINFO GROUPS orders:stream
```

**If Redis issues:**
- Check Redis connectivity (Step 2.4)
- Check consumer group status
- Verify messages are being produced
- Check for message backlog

### 6.2 Check HTTP Requests (for manual orders)

**Monitor HTTP requests:**
```bash
# Check order-executor logs for HTTP requests
docker compose logs order-executor | grep -E "(POST|GET|PUT|DELETE)" | tail -20

# Check for request timeouts
docker compose logs order-executor | grep -i timeout
```

### 6.3 Check Fill Sync Data Flow

**Verify fill sync is working:**
```bash
# Check fill-sync logs
docker compose logs fill-sync | tail -50

# Look for sync activity
docker compose logs fill-sync | grep -i "synced\|fill\|trade"

# Check for errors
docker compose logs fill-sync | grep -i error
```

**Verify fills are being recorded:**
```bash
# Check recent trades in database
docker compose exec postgres psql -U postgres -d crypto_ls -c "
  SELECT id, symbol, side, quantity, price, traded_at, order_id
  FROM trades
  ORDER BY traded_at DESC
  LIMIT 10;
"
```

### 6.4 Check Binance API Integration

**Test Binance API connectivity:**
```bash
# Check Binance API keys (via test script)
python scripts/test/test_binance_api_keys.py

# Check order placement
python scripts/test/test_order_placement.py
```

**Common Binance API issues:**
- Invalid API keys
- IP whitelist restrictions
- Testnet vs production mismatch
- Rate limits exceeded
- Symbol not available

---

## Step 7: Run Reconciliation Checks

### 7.1 Run All Reconciliations

```bash
# Run reconciliation checks
python scripts/integrity/check_booking_recon.py --book-id test_book

# Or via API
curl "http://localhost:8000/admin/reconciliation?book_id=test_book" | jq
```

**Review reconciliation report:**
- **Rec 1 (Orders vs Trades)**: Check filled quantity consistency
- **Rec 2 (Trades vs Binance)**: Check for missing/extra trades
- **Rec 3 (Positions vs Trades)**: Check position quantity consistency
- **Rec 4 (Positions vs Binance)**: Compare with exchange positions
- **Rec 5 (Orders vs Binance)**: Check order status consistency
- **Rec 6 (Balances vs Binance)**: Compare balances with exchange

### 7.2 Identify Specific Issues

**From reconciliation report, identify:**
- Which rec(s) failed?
- What are the mismatches?
- How many records are affected?
- What is the root cause?

**Common root causes:**
- Missing fills (Rec 2)
- Wrong order status (Rec 1, Rec 5)
- Position drift (Rec 3)
- Balance drift (Rec 6)
- Extra records (Rec 2, Rec 5)

---

## Step 8: Apply Fixes

### 8.1 Use Automated Fix Script

**Dry run first (preview changes):**
```bash
python scripts/integrity/fix_reconciliation_breaks.py \
  --book-id test_book \
  --dry-run \
  --fix all
```

**Apply fixes:**
```bash
# Fix specific rec
python scripts/integrity/fix_reconciliation_breaks.py \
  --book-id test_book \
  --fix rec2

# Fix all recs
python scripts/integrity/fix_reconciliation_breaks.py \
  --book-id test_book \
  --auto-fix
```

### 8.2 Manual Fixes (if automated script doesn't cover)

**Missing trades:**
```bash
# Re-run fill sync for symbol
# (Fill sync will automatically pick up missing trades)

# Or manually add trade via API
curl -X POST http://localhost:8000/admin/manual-trade \
  -H "Content-Type: application/json" \
  -d '{
    "venue": "binance_spot",
    "book_id": "test_book",
    "symbol": "BTCUSDT",
    "side": "BUY",
    "quantity": 0.001,
    "price": 50000,
    "exchange_trade_id": "12345",
    "traded_at": 1234567890000
  }'
```

**Rebuild positions:**
```bash
# Via API
curl -X POST http://localhost:8000/admin/rebuild-positions \
  -H "Content-Type: application/json" \
  -d '{"book_id": "test_book"}'

# Or via script
python scripts/utils/rebuild_positions.py --book-id test_book
```

**Rebuild balances:**
```bash
# Via API
curl -X POST http://localhost:8000/admin/rebuild-balances \
  -H "Content-Type: application/json" \
  -d '{"book_id": "test_book"}'

# Or via script
python scripts/utils/rebuild_balances.py --book-id test_book
```

**Update order status:**
```sql
-- Direct SQL update (use with caution)
UPDATE orders
SET status = 'FILLED', updated_at = 1234567890000
WHERE id = 123;
```

**Create adjustment (for manual overrides):**
```bash
curl -X POST http://localhost:8000/admin/adjustments \
  -H "Content-Type: application/json" \
  -d '{
    "venue": "binance_spot",
    "book_id": "test_book",
    "type": "balance",
    "asset_or_symbol": "USDT",
    "delta_or_value": 100.0,
    "reason": "Manual deposit correction",
    "created_by": "admin"
  }'
```

### 8.3 Fix Service Issues

**If services are failing:**
```bash
# Restart services
docker compose restart order-executor
docker compose restart fill-sync

# Rebuild if code changed
docker compose build order-executor
docker compose up -d order-executor
```

**If database connection issues:**
```bash
# Check database is running
docker compose ps postgres

# Check connection string in .env
grep DATABASE_URL .env

# Test connection
docker compose exec postgres psql -U postgres -d crypto_ls -c "SELECT 1;"
```

---

## Step 9: Verify Fixes

### 9.1 Re-run Reconciliation

```bash
# Run reconciliations again
python scripts/integrity/check_booking_recon.py --book-id test_book

# Verify all recs pass
```

### 9.2 Verify GUI Display

**Check GUI shows correct data:**
- Refresh GUI
- Verify data matches database
- Check filters work correctly
- Verify no errors in browser console

### 9.3 Verify API Responses

```bash
# Test API endpoints
curl "http://localhost:8000/orders?book_id=test_book" | jq
curl "http://localhost:8000/trades?book_id=test_book" | jq
curl "http://localhost:8000/positions?book_id=test_book" | jq
curl "http://localhost:8000/balances?book_id=test_book" | jq
```

### 9.4 Monitor for Recurrence

**Watch logs for a few minutes:**
```bash
# Monitor order-executor logs
docker compose logs -f order-executor

# Monitor fill-sync logs
docker compose logs -f fill-sync
```

---

## Common Issues and Quick Fixes

### Issue: Orders Not Appearing

**Quick checks:**
1. Check service health (Step 2.1)
2. Check database for orders (Step 4.2)
3. Check API response (Step 5.1)
4. Check GUI cache (Step 3.2)

**Fix:**
- Restart order-executor service
- Clear GUI cache
- Check book_id filter

### Issue: Trades Missing

**Quick checks:**
1. Check fill-sync service (Step 2.2)
2. Run Rec 2 (Step 7.1)
3. Check Binance API (Step 6.4)

**Fix:**
- Restart fill-sync service
- Run fix script for Rec 2 (Step 8.1)
- Manually sync fills for symbol

### Issue: Positions Incorrect

**Quick checks:**
1. Run Rec 3 (Step 7.1)
2. Check trades (Step 4.3)

**Fix:**
- Rebuild positions (Step 8.2)

### Issue: Balances Incorrect

**Quick checks:**
1. Run Rec 6 (Step 7.1)
2. Check trades (Step 4.3)

**Fix:**
- Rebuild balances (Step 8.2)
- Check for missing trades first

### Issue: Duplicate Records

**Quick checks:**
1. Check database (Step 4.4)
2. Check idempotency logic

**Fix:**
- Remove duplicates manually (with caution)
- Check idempotency checks in code

---

## Escalation

**If issue persists after following this SOP:**

1. **Document findings:**
   - Issue description
   - Steps taken
   - Error messages
   - Reconciliation report
   - Logs (last 100 lines)

2. **Check related documentation:**
   - [Booking System Architecture](../../plans/architecture/booking-system-and-recon.md)
   - [Booking Operations Guide](../../operations/operations/booking-and-recon.md)

3. **Review code:**
   - Check recent commits
   - Review error handling
   - Check for known issues

4. **Contact:**
   - System administrator
   - Development team
   - Database administrator (if DB issues)

---

## Prevention

**Regular maintenance:**
- Run reconciliations daily (automated or manual)
- Monitor service logs
- Check service health regularly
- Review reconciliation reports

**Best practices:**
- Always use dry-run before applying fixes
- Document all manual changes
- Create adjustments for manual overrides
- Keep audit trail intact

---

## Related Documents

- [Booking System Architecture](../../plans/architecture/booking-system-and-recon.md)
- [Booking Operations Guide](../../operations/operations/booking-and-recon.md)
- [Create Book via API](./sop-create-book-via-api.md)
- [Fix Reconciliation Scripts](../../../scripts/integrity/fix_reconciliation_breaks.py)
