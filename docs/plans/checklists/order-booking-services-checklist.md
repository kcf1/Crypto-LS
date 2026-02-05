# Order & Booking Services Implementation Checklist

## Overview

This document lists all changes needed to implement the order and booking services architecture as described in `order-booking-services-architecture.md`.

## Current State

**What exists:**
- ✅ `BookingOrchestrator` - Places orders and books them
- ✅ `Ledger` - Complete booking system with all methods
- ✅ `OrderManager` - Exchange order placement
- ✅ `run_fill_sync.py` - Fill sync service (already implemented)
- ✅ Rebuild utilities (positions, balances)
- ✅ Reconciliation scripts

**What's missing:**
- ❌ Order Executor Service (Redis consumer + HTTP API)
- ❌ Redis service in docker-compose
- ❌ Admin endpoints for manual operations
- ❌ Streamlit admin panel
- ❌ CLI tools for manual operations
- ❌ Example strategy service (publishes to Redis)

## Implementation Checklist

### Phase 1: Core Infrastructure

#### 1.1 Add Dependencies

**File:** `requirements.txt`

**Changes:**
```python
# Add these lines:
redis>=5.0.0
flask>=3.0.0
flask-cors>=4.0.0
```

**Status:** ⬜ Not started

---

#### 1.2 Create Dockerfile for Order Executor

**File:** `Dockerfile.executor` (NEW)

**Content:**
```dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config config
COPY data data
COPY scripts scripts
COPY booking booking
COPY execution execution
COPY alembic alembic

CMD ["python", "scripts/services/run_order_executor.py"]
```

**Status:** ⬜ Not started

---

#### 1.3 Add Redis Service to Docker Compose

**File:** `docker-compose.yml`

**Changes:**
Add Redis service:
```yaml
redis:
  image: redis:7-alpine
  container_name: crypto-ls-redis
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  command: >
    redis-server
    --appendonly yes
    --maxmemory 256mb
    --maxmemory-policy allkeys-lru
  deploy:
    resources:
      limits:
        memory: 256M
        cpus: '0.2'
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 3s
    retries: 3
```

Add order-executor service:
```yaml
order-executor:
  build:
    context: .
    dockerfile: Dockerfile.executor
  container_name: crypto-ls-order-executor
  env_file:
    - .env
  environment:
    DATABASE_URL: postgresql://crypto:crypto@postgres:5432/cryptols
    REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
    ORDER_EXECUTOR_PORT: ${ORDER_EXECUTOR_PORT:-8000}
    ORDER_EXECUTOR_HOST: ${ORDER_EXECUTOR_HOST:-0.0.0.0}
  ports:
    - "8000:8000"
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_started
  restart: unless-stopped
  deploy:
    resources:
      limits:
        memory: 512M
        cpus: '0.5'
```

Add fill-sync service:
```yaml
fill-sync:
  build:
    context: .
    dockerfile: Dockerfile.updater
  container_name: crypto-ls-fill-sync
  env_file:
    - .env
  environment:
    DATABASE_URL: postgresql://crypto:crypto@postgres:5432/cryptols
  command: ["python", "scripts/services/run_fill_sync.py"]
  depends_on:
    postgres:
      condition: service_healthy
  restart: unless-stopped
  deploy:
    resources:
      limits:
        memory: 256M
        cpus: '0.2'
```

Update volumes section:
```yaml
volumes:
  postgres_data:
  redis_data:
```

**Status:** ⬜ Not started

---

#### 1.4 Update Environment Variables

**File:** `.env.example`

**Changes:**
Add:
```bash
# Redis
REDIS_URL=redis://localhost:6379/0

# Order Executor
ORDER_EXECUTOR_PORT=8000
ORDER_EXECUTOR_HOST=0.0.0.0
```

**Status:** ⬜ Not started

---

### Phase 2: Order Executor Service

#### 2.1 Create Order Executor Service

**File:** `scripts/services/run_order_executor.py` (NEW)

**Required Components:**
1. Redis Stream consumer (consumer group: `order_executors`)
2. Flask HTTP server
3. Order processing logic (calls `BookingOrchestrator.place_order()`)
4. Immediate fill sync after order placement
5. Admin endpoints (manual operations)
6. Query endpoints (orders, trades, positions, balances)

**Key Functions:**
- `consume_orders()` - Redis Stream consumer loop
- `process_order()` - Process single order from stream
- Flask routes for HTTP API

**Status:** ⬜ Not started

**Estimated Lines of Code:** ~400-500 lines

---

#### 2.2 Update BookingOrchestrator for Immediate Fill Sync

**File:** `execution/orchestrator.py`

**Changes:**
In `place_order()` method, after booking order, add:
```python
# Sync fills immediately (non-blocking, don't fail if it errors)
try:
    if result.get("exchange_order_id") and result.get("ledger_order_id"):
        self.sync_fills_for_order(
            symbol=symbol,
            exchange_order_id=result["exchange_order_id"],
            ledger_order_id=result["ledger_order_id"],
            book_id=book_id,
        )
except Exception as e:
    import logging
    logging.warning(f"Immediate fill sync failed: {e}, will be caught by periodic service")
```

**Status:** ⬜ Not started

---

### Phase 3: Admin Interface

#### 3.1 Create Streamlit Admin Panel

**File:** `viz/pages/admin.py` (NEW)

**Required Pages/Tabs:**
1. **Manual Trade Booking**
   - Form: symbol, side, quantity, price, traded_at, commission, etc.
   - Submit button → calls `Ledger.record_trade()`

2. **Manual Order Booking**
   - Form: symbol, side, order_type, quantity, price, status, exchange_order_id, etc.
   - Submit button → calls `Ledger.record_order()`

3. **Adjustments**
   - Form: type, asset_or_symbol, delta_or_value, reason, created_by
   - Submit button → calls `Ledger.record_adjustment()`

4. **Rebuild Tools**
   - Buttons: Rebuild Positions, Rebuild Balances
   - Calls rebuild scripts

5. **Reconciliation**
   - Button: Run Reconciliation
   - Display results in table/JSON

6. **Query Interface**
   - Tabs: Orders, Trades, Positions, Balances
   - Filters: book_id, symbol, asset
   - Display in tables

**Status:** ⬜ Not started

**Estimated Lines of Code:** ~300-400 lines

---

#### 3.2 Create CLI Tools

**File:** `scripts/admin/manual_trade.py` (NEW)

**Functionality:**
- CLI arguments: symbol, side, quantity, price, book_id, etc.
- Calls `Ledger.record_trade()` directly
- Prints result

**Status:** ⬜ Not started

---

**File:** `scripts/admin/manual_order.py` (NEW)

**Functionality:**
- CLI arguments: symbol, side, order_type, quantity, price, status, exchange_order_id, etc.
- Calls `Ledger.record_order()` directly
- Prints result

**Status:** ⬜ Not started

---

**File:** `scripts/admin/create_adjustment.py` (NEW)

**Functionality:**
- CLI arguments: type, asset_or_symbol, delta_or_value, reason, etc.
- Calls `Ledger.record_adjustment()` directly
- Prints result

**Status:** ⬜ Not started

---

### Phase 4: Examples & Documentation

#### 4.1 Create Example Strategy Service

**File:** `scripts/examples/publish_order.py` (NEW)

**Functionality:**
- Example script showing how to publish orders to Redis Stream
- Demonstrates order message format
- Can be used for testing

**Status:** ⬜ Not started

---

#### 4.2 Update Architecture Documentation

**File:** `docs/ARCHITECTURE.md`

**Changes:**
- Add Order Executor Service section
- Add Redis service section
- Update service dependencies diagram
- Add order flow diagrams

**Status:** ⬜ Not started

---

#### 4.3 Create Usage Guide

**File:** `docs/operations/order-executor-usage.md` (NEW)

**Content:**
- How to start services
- How to place orders (Redis Stream)
- How to use admin endpoints
- How to use Streamlit admin panel
- How to fix reconciliation issues
- Troubleshooting guide

**Status:** ⬜ Not started

---

### Phase 5: Testing

#### 5.1 Unit Tests

**Files:** `tests/test_order_executor.py` (NEW)

**Test Cases:**
- Order processing from Redis Stream
- Admin endpoint handlers
- Error handling
- Idempotency

**Status:** ⬜ Not started

---

#### 5.2 Integration Tests

**Files:** `tests/test_order_flow.py` (NEW)

**Test Cases:**
- End-to-end: Redis → Order Executor → Exchange → Ledger
- Manual booking flow
- Adjustment flow
- Reconciliation flow

**Status:** ⬜ Not started

---

## Summary of Changes

### New Files to Create (8 files)

1. ✅ `docs/plans/architecture/order-booking-services-architecture.md` - Architecture doc
2. ✅ `docs/plans/checklists/order-booking-services-checklist.md` - This file
3. ⬜ `Dockerfile.executor` - Docker image for order executor
4. ⬜ `scripts/services/run_order_executor.py` - Main order executor service
5. ⬜ `viz/pages/admin.py` - Streamlit admin panel
6. ⬜ `scripts/admin/manual_trade.py` - CLI tool
7. ⬜ `scripts/admin/manual_order.py` - CLI tool
8. ⬜ `scripts/admin/create_adjustment.py` - CLI tool
9. ⬜ `scripts/examples/publish_order.py` - Example strategy
10. ⬜ `docs/operations/order-executor-usage.md` - Usage guide

### Files to Modify (5 files)

1. ⬜ `requirements.txt` - Add redis, flask, flask-cors
2. ⬜ `docker-compose.yml` - Add redis, order-executor, fill-sync services
3. ⬜ `.env.example` - Add REDIS_URL, ORDER_EXECUTOR_PORT, ORDER_EXECUTOR_HOST
4. ⬜ `execution/orchestrator.py` - Add immediate fill sync in place_order()
5. ⬜ `docs/ARCHITECTURE.md` - Update with new services

### Files That Don't Need Changes

- ✅ `booking/ledger.py` - Already complete
- ✅ `execution/order_manager.py` - Already complete
- ✅ `execution/binance/client.py` - Already complete
- ✅ `scripts/services/run_fill_sync.py` - Already complete
- ✅ `scripts/utils/rebuild_positions.py` - Already complete
- ✅ `scripts/utils/rebuild_balances.py` - Already complete
- ✅ `scripts/integrity/check_booking_recon.py` - Already complete

## Implementation Order

1. **Phase 1:** Infrastructure (Redis, Docker, dependencies)
2. **Phase 2:** Order Executor Service (core functionality)
3. **Phase 3:** Admin Interface (manual operations)
4. **Phase 4:** Examples & Documentation
5. **Phase 5:** Testing

## Estimated Effort

- **Phase 1:** 1-2 hours (infrastructure setup)
- **Phase 2:** 4-6 hours (order executor service)
- **Phase 3:** 3-4 hours (admin interface)
- **Phase 4:** 1-2 hours (examples & docs)
- **Phase 5:** 2-3 hours (testing)

**Total:** ~11-17 hours

## Dependencies

**External:**
- Redis 7+ (Docker image)
- Flask 3.0+ (Python package)
- redis-py 5.0+ (Python package)

**Internal:**
- `BookingOrchestrator` (already exists)
- `Ledger` (already exists)
- `OrderManager` (already exists)
- `BinanceClient` (already exists)

## Testing Strategy

### Manual Testing

1. **Start services:**
   ```bash
   docker compose up -d postgres redis order-executor fill-sync
   ```

2. **Publish test order:**
   ```python
   import redis
   r = redis.Redis(host='localhost', port=6379)
   r.xadd('order_stream', {'symbol': 'BTCUSDT', 'side': 'BUY', 'quote_order_qty': 10.0})
   ```

3. **Verify order booked:**
   ```bash
   curl http://localhost:8000/orders
   ```

4. **Test manual booking:**
   ```bash
   curl -X POST http://localhost:8000/admin/trades -d '{...}'
   ```

5. **Test reconciliation:**
   ```bash
   curl http://localhost:8000/admin/reconciliation
   ```

### Automated Testing

- Unit tests for order processing logic
- Integration tests for end-to-end flow
- Test admin endpoints
- Test error handling

## Rollout Plan

### Step 1: Local Development
- Implement all components locally
- Test with testnet API keys
- Verify all flows work

### Step 2: Staging/Testing
- Deploy to test environment
- Run integration tests
- Test with small amounts

### Step 3: Production
- Deploy to production
- Monitor logs closely
- Start with small order sizes
- Gradually increase

## Notes

- All manual operations are idempotent (safe to retry)
- Fill sync service acts as backup (catches missed fills)
- Admin endpoints should have authentication in production
- Redis persistence ensures no order loss on restart
- All operations are logged for audit trail
