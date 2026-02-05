# Order & Booking Services Architecture

## Overview

This document describes the complete architecture for order execution and booking services, including automatic order processing, manual booking capabilities, and reconciliation fixes.

## Architecture Decision: Combined Service

**Decision:** Use a **combined Order Executor Service** that handles both order placement and booking in a single service.

**Rationale:**
- Simpler architecture for single bot use case
- Atomic operations (place + book together)
- Easier to debug and maintain
- Can add manual booking/admin endpoints to same service
- Sufficient for current needs; can split later if needed

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Strategy Services / External Systems                           │
│  (Generate trading signals)                                     │
│  └─→ Redis Stream: 'order_stream'                               │
└─────────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│  Order Executor Service (Combined)                              │
│  scripts/services/run_order_executor.py                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Automatic Order Processing (Redis Consumer)            │  │
│  │  ├─ Listen to 'order_stream'                             │  │
│  │  ├─ Place order on exchange (OrderManager)              │  │
│  │  ├─ Book order to ledger (Ledger.record_order)          │  │
│  │  ├─ Sync fills immediately                               │  │
│  │  └─ ACK message                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Admin/Manual Endpoints (HTTP API)                       │  │
│  │  ├─ POST /admin/trades - Manual trade booking           │  │
│  │  ├─ POST /admin/orders - Manual order booking            │  │
│  │  ├─ POST /admin/adjustments - Create adjustment          │  │
│  │  ├─ POST /admin/rebuild-positions - Rebuild positions    │  │
│  │  ├─ POST /admin/rebuild-balances - Rebuild balances     │  │
│  │  └─ GET /admin/reconciliation - Run reconciliation      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Query Endpoints (HTTP API)                             │  │
│  │  ├─ GET /orders - List orders                           │  │
│  │  ├─ GET /orders/<id> - Get order                        │  │
│  │  ├─ GET /positions - Get positions                      │  │
│  │  ├─ GET /balances - Get balances                        │  │
│  │  └─ GET /trades - List trades                           │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│  Booking System (Ledger)                                        │
│  booking/ledger.py                                              │
│  ├─ Orders table                                                │
│  ├─ Trades table                                                │
│  ├─ Positions table                                            │
│  ├─ Balances table                                             │
│  └─ Adjustments table                                          │
└─────────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│  Fill Sync Service (Backup)                                     │
│  scripts/services/run_fill_sync.py                              │
│  ├─ Runs every 60 seconds                                       │
│  ├─ Syncs fills for all symbols                                 │
│  └─ Catches any missed fills                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Service Components

### 1. Order Executor Service

**File:** `scripts/services/run_order_executor.py`

**Responsibilities:**
- Consume order requests from Redis Stream
- Place orders on exchange via `BookingOrchestrator`
- Book orders and trades to ledger
- Sync fills immediately after order placement
- Provide admin endpoints for manual operations
- Provide query endpoints for order/trade/position/balance data

**Technology:**
- Redis Streams (consumer group pattern)
- Flask/FastAPI for HTTP API
- Uses existing `BookingOrchestrator` and `Ledger`

**Endpoints:**

**Automatic Order Processing:**
- Redis Stream consumer (no HTTP endpoint, listens to `order_stream`)

**Query Endpoints:**
- `GET /health` - Health check
- `GET /orders` - List orders (query params: `book_id`, `symbol`, `limit`)
- `GET /orders/<id>` - Get order by ledger ID
- `GET /positions` - Get positions (query params: `book_id`, `symbol`)
- `GET /balances` - Get balances (query params: `book_id`, `asset`)
- `GET /trades` - List trades (query params: `book_id`, `symbol`, `limit`)

**Admin/Manual Endpoints:**
- `POST /admin/trades` - Manually book a trade
- `POST /admin/orders` - Manually book an order
- `POST /admin/adjustments` - Create adjustment (for reconciliation fixes)
- `POST /admin/rebuild-positions` - Rebuild positions table
- `POST /admin/rebuild-balances` - Rebuild balances table
- `GET /admin/reconciliation` - Run reconciliation and return results

**Order Cancellation:**
- `POST /orders/<id>/cancel` - Cancel order (via `BookingOrchestrator.cancel_order()`)

### 2. Fill Sync Service

**File:** `scripts/services/run_fill_sync.py` (already exists)

**Responsibilities:**
- Periodic fill synchronization (every 60 seconds)
- Backup mechanism to catch any missed fills
- Syncs fills for all symbols in `settings.symbols`

**Status:** Already implemented, no changes needed

### 3. Redis Service

**Image:** `redis:7-alpine`

**Configuration:**
- Stream: `order_stream` (for order requests)
- Consumer Group: `order_executors`
- Persistence: AOF enabled
- Memory limit: 256 MB (configurable)

**Status:** Needs to be added to `docker-compose.yml`

## Data Flow

### Automatic Order Flow

```
1. Strategy Service generates signal
   ↓
2. Strategy Service publishes to Redis Stream:
   r.xadd('order_stream', {
       'symbol': 'BTCUSDT',
       'side': 'BUY',
       'quantity': 0.001,
       'order_type': 'MARKET',
       'book_id': 'trend_following',
       'notes': 'EMA crossover signal'
   })
   ↓
3. Order Executor Service (Redis consumer):
   - Reads message from stream
   - Calls BookingOrchestrator.place_order()
   - Order placed on exchange
   - Order booked to ledger
   - Fills synced immediately
   - ACK message
   ↓
4. Result: Order placed, booked, fills synced, positions/balances updated
```

### Manual Trade Booking Flow

```
1. Admin/User calls HTTP endpoint:
   POST /admin/trades
   {
       "venue": "binance_spot",
       "book_id": "default",
       "symbol": "BTCUSDT",
       "side": "BUY",
       "quantity": 0.001,
       "price": 50000,
       "traded_at": 1707123456000,
       "exchange_trade_id": "12345",
       "commission": 0.000001,
       "commission_asset": "BTC",
       "notes": "Manual trade from Binance website"
   }
   ↓
2. Order Executor Service:
   - Validates request
   - Calls Ledger.record_trade() directly
   - Trade booked, positions/balances updated
   ↓
3. Result: Trade booked without going through exchange
```

### Reconciliation Fix Flow

```
1. Run reconciliation:
   GET /admin/reconciliation
   OR
   python scripts/integrity/check_booking_recon.py
   ↓
2. Review mismatches in report
   ↓
3. Fix via adjustment:
   POST /admin/adjustments
   {
       "venue": "binance_spot",
       "book_id": "default",
       "type": "balance",
       "asset_or_symbol": "USDT",
       "delta_or_value": 1000.0,
       "reason": "Reconciliation fix: missing deposit",
       "created_by": "admin"
   }
   ↓
4. Adjustment applied:
   - Balance updated
   - Adjustment recorded in audit table
   ↓
5. Re-run reconciliation to verify fix
```

## Implementation Checklist

### Phase 1: Core Order Executor Service

- [ ] **Create `scripts/services/run_order_executor.py`**
  - Redis Stream consumer (consumer group pattern)
  - Flask/FastAPI HTTP server
  - Order processing logic (calls `BookingOrchestrator`)
  - Admin endpoints for manual operations
  - Query endpoints for data access

- [ ] **Create `Dockerfile.executor`**
  - Base image: `python:3.11-slim`
  - Install dependencies (including `redis`, `flask`, `flask-cors`)
  - Copy code (config, data, scripts, booking, execution, alembic)
  - CMD: Run `run_order_executor.py`

- [ ] **Update `requirements.txt`**
  - Add `redis>=5.0.0`
  - Add `flask>=3.0.0`
  - Add `flask-cors>=4.0.0`

- [ ] **Update `docker-compose.yml`**
  - Add `redis` service
  - Add `order-executor` service
  - Configure environment variables
  - Set resource limits

### Phase 2: Admin Interface

- [ ] **Create Streamlit Admin Panel** (`viz/pages/admin.py`)
  - Manual trade booking form
  - Manual order booking form
  - Adjustment creation form
  - Rebuild tools (positions, balances)
  - Reconciliation viewer
  - Order/trade/position/balance query interface

- [ ] **Create CLI Tools** (`scripts/admin/`)
  - `manual_trade.py` - CLI for manual trade booking
  - `manual_order.py` - CLI for manual order booking
  - `create_adjustment.py` - CLI for adjustments
  - `rebuild_all.py` - CLI wrapper for rebuild scripts

### Phase 3: Integration & Testing

- [ ] **Update `BookingOrchestrator.place_order()`**
  - Add immediate fill sync (non-blocking, with error handling)
  - Log warnings if fill sync fails (will be caught by fill-sync service)

- [ ] **Create example strategy service**
  - Example script showing how to publish orders to Redis Stream
  - Documentation on order message format

- [ ] **Update documentation**
  - Add order executor service to `docs/ARCHITECTURE.md`
  - Create usage guide for admin endpoints
  - Create guide for manual operations

## Changes Needed vs Current Codebase

### New Files to Create

1. **`scripts/services/run_order_executor.py`** (NEW)
   - Redis Stream consumer
   - HTTP API server (Flask/FastAPI)
   - Admin endpoints
   - Query endpoints

2. **`Dockerfile.executor`** (NEW)
   - Docker image for order executor service

3. **`scripts/admin/manual_trade.py`** (NEW)
   - CLI tool for manual trade booking

4. **`scripts/admin/manual_order.py`** (NEW)
   - CLI tool for manual order booking

5. **`scripts/admin/create_adjustment.py`** (NEW)
   - CLI tool for creating adjustments

6. **`viz/pages/admin.py`** (NEW)
   - Streamlit admin panel page

7. **`docs/plans/architecture/order-booking-services-architecture.md`** (THIS FILE)
   - Architecture documentation

### Files to Modify

1. **`requirements.txt`**
   - Add: `redis>=5.0.0`
   - Add: `flask>=3.0.0`
   - Add: `flask-cors>=4.0.0`

2. **`docker-compose.yml`**
   - Add `redis` service:
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
     ```
   
   - Add `order-executor` service:
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
         REDIS_URL: redis://redis:6379/0
         ORDER_EXECUTOR_PORT: 8000
         ORDER_EXECUTOR_HOST: 0.0.0.0
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
   
   - Add `redis_data` volume:
     ```yaml
     volumes:
       postgres_data:
       redis_data:
     ```

3. **`execution/orchestrator.py`** (MINOR UPDATE)
   - Update `place_order()` to sync fills immediately (non-blocking)
   - Add error handling for fill sync (log warning, don't fail)

4. **`docs/ARCHITECTURE.md`** (UPDATE)
   - Add Order Executor Service section
   - Add Redis service section
   - Update service dependencies
   - Add order flow diagrams

5. **`.env.example`** (UPDATE)
   - Add `REDIS_URL=redis://localhost:6379/0`
   - Add `ORDER_EXECUTOR_PORT=8000`
   - Add `ORDER_EXECUTOR_HOST=0.0.0.0`

### Files That Don't Need Changes

- `booking/ledger.py` - Already has all needed methods
- `execution/order_manager.py` - Already complete
- `execution/binance/client.py` - Already complete
- `scripts/services/run_fill_sync.py` - Already complete
- `scripts/utils/rebuild_positions.py` - Already complete
- `scripts/utils/rebuild_balances.py` - Already complete
- `scripts/integrity/check_booking_recon.py` - Already complete

## Service Dependencies

```
order-executor
├─ depends_on: postgres (healthy)
├─ depends_on: redis (started)
└─ uses: BookingOrchestrator → OrderManager → BinanceClient
    └─ uses: Ledger → PostgreSQL

fill-sync
├─ depends_on: postgres (healthy)
└─ uses: BookingOrchestrator → OrderManager → BinanceClient
    └─ uses: Ledger → PostgreSQL

data-updater
├─ depends_on: postgres (healthy)
└─ uses: Storage → PostgreSQL
```

## Message Format

### Order Request (Redis Stream)

```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "quantity": 0.001,
  "order_type": "MARKET",
  "price": null,
  "quote_order_qty": 100.0,
  "time_in_force": "GTC",
  "book_id": "default",
  "notes": "EMA crossover signal",
  "strategy_id": "trend_following_v1"
}
```

**Required fields:**
- `symbol` (string): Trading pair
- `side` (string): "BUY" or "SELL"

**Optional fields:**
- `quantity` (float): Base asset quantity (for MARKET/LIMIT)
- `quote_order_qty` (float): Quote asset quantity (for MARKET)
- `order_type` (string): "MARKET", "LIMIT", etc. (default: "MARKET")
- `price` (float): Limit price (required for LIMIT orders)
- `time_in_force` (string): "GTC", "IOC", "FOK" (default: "GTC")
- `book_id` (string): Book/strategy identifier (default: "default")
- `notes` (string): Optional notes
- `strategy_id` (string): Strategy identifier for tracking

## Manual Operations

### Manual Trade Booking

**Use cases:**
- Trade executed manually on Binance website
- Trade from external system not using order executor
- Backfill historical trades
- Fix missing trades from reconciliation

**Via HTTP API:**
```bash
curl -X POST http://localhost:8000/admin/trades \
  -H "Content-Type: application/json" \
  -d '{
    "venue": "binance_spot",
    "book_id": "default",
    "symbol": "BTCUSDT",
    "side": "BUY",
    "quantity": 0.001,
    "price": 50000,
    "traded_at": 1707123456000,
    "exchange_trade_id": "12345",
    "commission": 0.000001,
    "commission_asset": "BTC",
    "notes": "Manual trade from Binance website"
  }'
```

**Via Streamlit Admin Panel:**
- Navigate to Admin → Manual Trade
- Fill form and submit

**Via CLI:**
```bash
python scripts/admin/manual_trade.py \
  --symbol BTCUSDT \
  --side BUY \
  --quantity 0.001 \
  --price 50000 \
  --book-id default
```

### Manual Order Booking

**Use cases:**
- Order placed manually on Binance
- Backfill order history
- Fix missing orders from reconciliation

**Via HTTP API:**
```bash
curl -X POST http://localhost:8000/admin/orders \
  -H "Content-Type: application/json" \
  -d '{
    "venue": "binance_spot",
    "book_id": "default",
    "symbol": "BTCUSDT",
    "side": "BUY",
    "order_type": "LIMIT",
    "quantity": 0.001,
    "price": 50000,
    "status": "FILLED",
    "exchange_order_id": "12345678",
    "created_at": 1707123456000,
    "notes": "Manual order from Binance"
  }'
```

### Adjustments (Reconciliation Fixes)

**Use cases:**
- Balance mismatch (missing deposit/withdrawal)
- Position mismatch (calculation error)
- Order status mismatch (manual correction)

**Via HTTP API:**
```bash
curl -X POST http://localhost:8000/admin/adjustments \
  -H "Content-Type: application/json" \
  -d '{
    "venue": "binance_spot",
    "book_id": "default",
    "type": "balance",
    "asset_or_symbol": "USDT",
    "delta_or_value": 1000.0,
    "reason": "Reconciliation fix: missing deposit",
    "created_by": "admin",
    "notes": "Deposit from bank transfer"
  }'
```

**Adjustment types:**
- `balance`: Update `balances.free` for asset
- `position`: Update `positions.quantity` for symbol
- `order_status`: Update `orders.status` for order

### Rebuild Operations

**Use cases:**
- Position/balance calculation errors
- Data corruption
- After manual data fixes

**Via HTTP API:**
```bash
# Rebuild positions
curl -X POST http://localhost:8000/admin/rebuild-positions \
  -H "Content-Type: application/json" \
  -d '{"book_id": "default"}'

# Rebuild balances
curl -X POST http://localhost:8000/admin/rebuild-balances \
  -H "Content-Type: application/json" \
  -d '{"book_id": "default"}'
```

**Via CLI:**
```bash
python scripts/utils/rebuild_positions.py --book-id default
python scripts/utils/rebuild_balances.py --book-id default
```

## Reconciliation Workflow

### Step 1: Run Reconciliation

```bash
# Via HTTP API
curl http://localhost:8000/admin/reconciliation?book_id=default

# Via CLI
python scripts/integrity/check_booking_recon.py --book-id default
```

### Step 2: Review Report

Report includes:
- Orders vs trades mismatches
- Trades vs Binance mismatches
- Positions vs trades mismatches
- Positions vs Binance mismatches
- Orders vs Binance mismatches
- Balances vs Binance mismatches

### Step 3: Fix Issues

**Missing trades:**
- Book manually via `/admin/trades`
- Or run fill sync to catch up

**Balance mismatches:**
- Create adjustment via `/admin/adjustments`
- Or rebuild balances if calculation error

**Position mismatches:**
- Rebuild positions if calculation error
- Or book missing trades

**Order status mismatches:**
- Update order status via adjustment
- Or sync fills to update status automatically

### Step 4: Verify Fix

Re-run reconciliation to verify all issues resolved.

## Error Handling

### Order Placement Failures

- **Exchange API error:** Log error, don't book order, return error to caller
- **Booking error:** Log error, order placed but not booked (needs manual fix)
- **Fill sync error:** Log warning, order booked, fills will be caught by fill-sync service

### Redis Connection Failures

- **Consumer:** Retry connection with exponential backoff
- **Publisher:** Fail fast, return error to strategy service

### Database Connection Failures

- **Booking:** Retry with exponential backoff
- **Query:** Return error, don't crash service

## Monitoring & Logging

### Logs

- **Order placement:** Log all orders placed (exchange_order_id, ledger_order_id, status)
- **Fill sync:** Log fills synced (trade_id, symbol, quantity)
- **Manual operations:** Log all admin operations (who, what, when)
- **Errors:** Log all errors with full stack traces

### Metrics (Future Enhancement)

- Orders placed per minute
- Fill sync latency
- Redis queue depth
- Database query latency
- Error rates

## Security Considerations

### Admin Endpoints

- **Authentication:** Add API key authentication for admin endpoints
- **Authorization:** Restrict admin endpoints to internal network only
- **Rate limiting:** Prevent abuse of admin endpoints

### Redis

- **Password:** Set Redis password in production
- **Network:** Don't expose Redis port publicly
- **TLS:** Use Redis TLS in production (if supported)

### Database

- **Credentials:** Store in `.env`, never commit
- **Connection:** Use Docker network, don't expose PostgreSQL port publicly

## Deployment

### Local Development

```bash
# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f order-executor

# Test order placement
python scripts/examples/publish_order.py
```

### Production

1. **Set environment variables:**
   - `REDIS_URL`
   - `DATABASE_URL`
   - `BINANCE_TRADING_API_KEY`
   - `BINANCE_TRADING_API_SECRET`

2. **Start services:**
   ```bash
   docker compose up -d postgres redis order-executor fill-sync
   ```

3. **Monitor:**
   ```bash
   docker compose logs -f order-executor
   ```

## Testing

### Unit Tests

- Test `BookingOrchestrator` methods
- Test `Ledger` methods
- Test admin endpoint handlers

### Integration Tests

- Test order flow: Redis → Order Executor → Exchange → Ledger
- Test manual booking flow
- Test adjustment flow
- Test reconciliation

### Manual Testing

1. **Place test order:**
   ```python
   import redis
   r = redis.Redis(host='localhost', port=6379)
   r.xadd('order_stream', {
       'symbol': 'BTCUSDT',
       'side': 'BUY',
       'quote_order_qty': 10.0,
       'order_type': 'MARKET',
       'book_id': 'test'
   })
   ```

2. **Check order booked:**
   ```bash
   curl http://localhost:8000/orders?book_id=test
   ```

3. **Check positions updated:**
   ```bash
   curl http://localhost:8000/positions?book_id=test
   ```

## Future Enhancements

### Phase 1 (Current)
- ✅ Combined order executor service
- ✅ Redis Streams for order queue
- ✅ Admin endpoints for manual operations
- ✅ Fill sync service (backup)

### Phase 2 (Future)
- [ ] Web UI for admin operations (Streamlit admin panel)
- [ ] API authentication (API keys)
- [ ] Order priority queue (sorted sets)
- [ ] Order batching (group multiple orders)

### Phase 3 (Advanced)
- [ ] Split order service and booking service (if needed)
- [ ] Multiple order executor workers (scaling)
- [ ] Order routing (multiple exchanges)
- [ ] Risk management layer (pre-order checks)

## Summary

**Architecture:** Combined Order Executor Service (places orders + books them)

**Key Components:**
1. Order Executor Service (Redis consumer + HTTP API)
2. Fill Sync Service (backup, periodic)
3. Redis (message queue)
4. Admin endpoints (manual operations)
5. Streamlit Admin Panel (GUI)

**Benefits:**
- Simple architecture
- Manual booking capability
- Reconciliation fixes via adjustments
- GUI and API access
- Can split later if needed

**Next Steps:**
1. Implement order executor service
2. Add Redis to docker-compose
3. Create admin endpoints
4. Create Streamlit admin panel
5. Test end-to-end flow
