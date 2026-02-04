---
name: Booking System Implementation
overview: "Implement the complete booking system as designed: database schema (balances, adjustments), Ledger enhancements (idempotency, balance updates, order status updates, adjustments), fill sync service, orchestrator layer, reconciliation scripts, and rebuild utilities."
todos:
  - id: db-schema
    content: "Create Alembic migration 006: add balances and adjustments tables"
    status: pending
  - id: ledger-idempotency
    content: Add idempotency checks to Ledger.record_order and record_trade
    status: pending
  - id: ledger-balances
    content: Add balance updates to Ledger.record_trade (base, quote, commission assets)
    status: pending
  - id: ledger-order-status
    content: Add Ledger.update_order_status and get_order_by_exchange_id
    status: pending
  - id: ledger-adjustments
    content: Add Ledger.record_adjustment and get_adjustments/get_balances methods
    status: pending
  - id: orchestrator
    content: "Create execution/orchestrator.py: BookingOrchestrator with place_order, cancel_order, sync_fills methods"
    status: pending
  - id: fill-sync-service
    content: "Create scripts/services/run_fill_sync.py: periodic fill sync for active symbols"
    status: pending
  - id: rebuild-positions
    content: "Create scripts/utils/rebuild_positions.py: rebuild positions table from trades"
    status: pending
  - id: rebuild-balances
    content: "Create scripts/utils/rebuild_balances.py: rebuild balances table from trades"
    status: pending
  - id: reconciliation
    content: "Create scripts/integrity/check_booking_recon.py: all 6 reconciliations with JSON report"
    status: pending
  - id: tests
    content: Add unit tests for Ledger enhancements and BookingOrchestrator
    status: pending
  - id: docs
    content: Update booking plan doc with implementation status and usage examples
    status: pending
isProject: false
---

# Booking System Implementation Plan

## Overview

Build the complete booking system per [booking-system-and-recon.md](docs/plans/booking-system-and-recon.md): database schema additions (balances, adjustments), Ledger enhancements (idempotency checks, balance updates, order status updates, adjustments), fill sync service, orchestrator layer, reconciliation scripts, and rebuild utilities.

## Current State

- **Ledger** (`booking/ledger.py`): Basic `record_order`, `record_trade` (updates positions), `get_positions`, `get_orders`, `get_trades`. Missing: idempotency checks, balance updates, order status updates, adjustments.
- **Execution** (`execution/order_manager.py`, `execution/binance/client.py`): Complete for exchange I/O (place/cancel/query orders, get fills).
- **Database**: Alembic migration `001` has `orders`, `trades`, `positions`. Missing: `balances`, `adjustments` tables.
- **No orchestrator**: No layer that calls execution then booking.
- **No fill sync**: No service that fetches fills and books them.
- **No reconciliations**: No scripts to compare ledger vs exchange or ledger vs itself.

## Binance API Response Structures

### Order Response (`create_order`, `get_order`)

From python-binance `create_order()` and `get_order()`:

```python
{
    "orderId": int,                    # Exchange order ID (e.g., 12345678)
    "symbol": str,                     # Trading pair (e.g., "BTCUSDT")
    "status": str,                     # NEW, PARTIALLY_FILLED, FILLED, CANCELED, PENDING_CANCEL, REJECTED, EXPIRED
    "executedQty": str,                # Filled quantity (as string, e.g., "0.001")
    "origQty": str,                    # Original quantity (as string)
    "price": str,                      # Order price (as string, e.g., "50000.00")
    "side": str,                       # BUY or SELL
    "type": str,                       # LIMIT, MARKET, STOP_LOSS, STOP_LOSS_LIMIT, TAKE_PROFIT, TAKE_PROFIT_LIMIT, LIMIT_MAKER
    "time": int,                       # Creation timestamp (milliseconds)
    "updateTime": int,                 # Last update timestamp (milliseconds)
    "timeInForce": str,                # GTC, IOC, FOK
    "cummulativeQuoteQty": str,       # Cumulative quote quantity filled (as string)
    "clientOrderId": str,             # Optional client order ID
    "stopPrice": str,                  # Optional stop price
    "icebergQty": str,                 # Optional iceberg quantity
    "isWorking": bool,                 # Whether order is active
    "workingTime": int,                # Working time timestamp
}
```

**Mapping to ledger `orders` table:**

- `orderId` → `exchange_order_id` (convert to string for storage)
- `symbol` → `symbol`
- `side` → `side` (normalize to uppercase)
- `type` → `order_type` (normalize to uppercase)
- `origQty` → `quantity` (convert string to float)
- `price` → `price` (convert string to float, nullable for MARKET orders)
- `status` → `status` (normalize to uppercase)
- `time` → `created_at`
- `updateTime` → `updated_at`

### Trade Response (`get_my_trades`)

From python-binance `get_my_trades()`:

```python
{
    "id": int,                         # Trade ID (exchange_trade_id, e.g., 123456)
    "orderId": int,                    # Associated order ID
    "symbol": str,                     # Trading pair (e.g., "BTCUSDT")
    "price": str,                      # Trade price (as string, e.g., "50000.00")
    "qty": str,                        # Trade quantity (as string, e.g., "0.001")
    "commission": str,                 # Commission amount (as string, e.g., "0.000001")
    "commissionAsset": str,            # Asset commission was paid in (e.g., "BTC", "USDT")
    "time": int,                       # Trade timestamp (milliseconds)
    "side": str,                       # BUY or SELL
    "buyer": bool,                     # Whether account was buyer
    "maker": bool,                     # Whether account was maker
    "quoteQty": str,                  # Quote asset quantity (as string)
}
```

**Mapping to ledger `trades` table:**

- `id` → `exchange_trade_id` (convert to string for storage)
- `orderId` → resolve to `order_id` (ledger FK) via `get_order_by_exchange_id()`
- `symbol` → `symbol`
- `side` → `side` (normalize to uppercase)
- `qty` → `quantity` (convert string to float)
- `price` → `price` (convert string to float)
- `commission` → `commission` (convert string to float)
- `time` → `traded_at`
- `commissionAsset` → used for balance updates (not stored directly)

### Account Balance Response (`get_account`)

From python-binance `get_account()`:

```python
{
    "makerCommission": int,            # Maker commission rate (0-10000, basis points)
    "takerCommission": int,            # Taker commission rate
    "buyerCommission": int,             # Buyer commission rate
    "sellerCommission": int,            # Seller commission rate
    "canTrade": bool,                  # Can trade flag
    "canWithdraw": bool,               # Can withdraw flag
    "canDeposit": bool,                # Can deposit flag
    "updateTime": int,                 # Last account update timestamp (milliseconds)
    "accountType": str,                # Account type (e.g., "SPOT")
    "balances": [                       # Array of balance objects
        {
            "asset": str,               # Asset symbol (e.g., "BTC", "USDT", "ETH")
            "free": str,                # Available balance (as string, e.g., "1.23456789")
            "locked": str               # Locked balance (as string, e.g., "0.00100000")
        },
        ...
    ],
    "permissions": [str],              # Account permissions array
    "uid": int                         # User ID
}
```

**Mapping to ledger `balances` table:**

- Each item in `balances` array → one row in `balances` table
- `asset` → `asset`
- `free` → `free` (convert string to float)
- `locked` → `locked` (convert string to float)
- `updateTime` → `updated_at` (for reconciliation, not per-asset)
- `venue` → set to `"binance_spot"` (or from settings)

**Note:** Binance returns balances for ALL assets (even zero balances). For reconciliation, compare ledger balances (non-zero only) vs Binance balances (filter non-zero).

## Detailed Database Schema

### 1. Orders Table (existing, from migration 001, updated in 006)

```sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Ledger order ID (auto-increment)
    venue TEXT NOT NULL,                    -- Exchange venue (e.g., "binance_spot")
    book_id TEXT NOT NULL DEFAULT 'default', -- Book/strategy identifier (e.g., "default", "long_short", "trend_following")
    exchange_order_id TEXT,                -- Binance orderId (as string, nullable until order placed)
    symbol TEXT NOT NULL,                  -- Trading pair (e.g., "BTCUSDT")
    side TEXT NOT NULL,                    -- BUY or SELL (uppercase)
    order_type TEXT NOT NULL,              -- LIMIT, MARKET, etc. (uppercase)
    quantity REAL NOT NULL,                -- Original order quantity (float)
    price REAL,                            -- Order price (float, nullable for MARKET)
    status TEXT NOT NULL,                  -- NEW, PARTIALLY_FILLED, FILLED, CANCELED, etc. (uppercase)
    created_at INTEGER NOT NULL,           -- Creation timestamp (milliseconds)
    updated_at INTEGER,                    -- Last update timestamp (milliseconds, nullable)
    notes TEXT                             -- Free-text notes/comments (nullable, for future use)
);
```

**Indexes:**

- Unique index on `(venue, book_id, exchange_order_id)` for idempotency (when `exchange_order_id` is not NULL)
- Index on `(venue, book_id, symbol, created_at)` for queries
- Index on `book_id` for book-filtered queries

**Idempotency key:** `(venue, book_id, exchange_order_id)` - must be unique per exchange order per book.

### 2. Trades Table (existing, from migration 001, updated in 006)

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Ledger trade ID (auto-increment)
    venue TEXT NOT NULL,                     -- Exchange venue (e.g., "binance_spot")
    book_id TEXT NOT NULL DEFAULT 'default', -- Book/strategy identifier (e.g., "default", "long_short", "trend_following")
    exchange_trade_id TEXT,                 -- Binance trade id (as string, nullable)
    order_id INTEGER,                        -- FK to orders.id (nullable if trade not linked to order)
    symbol TEXT NOT NULL,                    -- Trading pair (e.g., "BTCUSDT")
    side TEXT NOT NULL,                      -- BUY or SELL (uppercase)
    quantity REAL NOT NULL,                  -- Trade quantity (float)
    price REAL NOT NULL,                     -- Trade price (float)
    commission REAL DEFAULT 0,               -- Commission amount (float)
    traded_at INTEGER NOT NULL,              -- Trade timestamp (milliseconds)
    notes TEXT,                              -- Free-text notes/comments (nullable, for future use)
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
```

**Indexes:**

- Unique index on `(venue, book_id, exchange_trade_id)` for idempotency (when `exchange_trade_id` is not NULL)
- Index on `(venue, book_id, symbol, traded_at)` for queries
- Index on `(order_id)` for order-trade joins
- Index on `book_id` for book-filtered queries

**Idempotency key:** `(venue, book_id, exchange_trade_id)` - must be unique per exchange trade per book.

**Note:** Commission asset is not stored directly; it's extracted from Binance `commissionAsset` field during booking and used for balance updates.

### 3. Positions Table (existing, from migration 001, updated in 006)

```sql
CREATE TABLE positions (
    book_id TEXT NOT NULL DEFAULT 'default', -- Book/strategy identifier (e.g., "default", "long_short", "trend_following")
    symbol TEXT NOT NULL,                    -- Trading pair (e.g., "BTCUSDT")
    quantity REAL NOT NULL,                  -- Current position quantity (float, positive=long, negative=short)
    avg_price REAL NOT NULL,                 -- Volume-weighted average price (VWAP, float)
    updated_at INTEGER NOT NULL,             -- Last update timestamp (milliseconds)
    notes TEXT,                               -- Free-text notes/comments (nullable, for future use)
    PRIMARY KEY (book_id, symbol)
);
```

**Indexes:**

- Primary key on `(book_id, symbol)` (composite)
- Index on `book_id` for book-filtered queries
- Index on `symbol` for symbol-filtered queries (across books)

**Note:** Positions are materialized (updated on every trade). Can be rebuilt from `trades` table. Each book maintains separate positions per symbol.

### 4. Balances Table (NEW - migration 006)

```sql
CREATE TABLE balances (
    venue TEXT NOT NULL,                -- Exchange venue (e.g., "binance_spot")
    book_id TEXT NOT NULL DEFAULT 'default', -- Book/strategy identifier (e.g., "default", "long_short", "trend_following")
    asset TEXT NOT NULL,                 -- Asset symbol (e.g., "BTC", "USDT", "ETH")
    free REAL NOT NULL DEFAULT 0,       -- Available balance (float)
    locked REAL NOT NULL DEFAULT 0,     -- Locked balance (in orders, etc., float)
    updated_at INTEGER NOT NULL,        -- Last update timestamp (milliseconds)
    PRIMARY KEY (venue, book_id, asset)
);
```

**Indexes:**

- Primary key on `(venue, book_id, asset)` (composite unique constraint)
- Index on `venue` for venue-filtered queries
- Index on `book_id` for book-filtered queries
- Index on `(venue, asset)` for cross-book asset queries (optional, for total asset balance across books)

**Update logic:**

- On trade booking (`record_trade`):
  - Base asset: BUY → `free += quantity`, SELL → `free -= quantity`
  - Quote asset: BUY → `free -= quantity * price`, SELL → `free += quantity * price`
  - Commission asset: `free -= commission`
  - Set `updated_at = traded_at`
- Use `INSERT ... ON CONFLICT (venue, asset) UPDATE` for PostgreSQL
- Use `INSERT ... ON CONFLICT (venue, asset) DO UPDATE` for SQLite

**Symbol parsing:** Extract base/quote from symbol (e.g., "BTCUSDT" → base="BTC", quote="USDT"). Handle edge cases:

- Standard pairs: `{BASE}{QUOTE}` (e.g., BTCUSDT, ETHBTC)
- Assume quote is common quote assets (USDT, BUSD, BTC, ETH, BNB) in order of preference
- For non-standard pairs, may need symbol metadata table (future enhancement)

### 5. Adjustments Table (NEW - migration 006)

```sql
CREATE TABLE adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Adjustment ID (auto-increment)
    venue TEXT NOT NULL,                    -- Exchange venue (e.g., "binance_spot")
    type TEXT NOT NULL,                     -- Adjustment type: "balance", "position", "order_status"
    asset_or_symbol TEXT NOT NULL,          -- Asset (for balance) or symbol (for position) or order_id (for order_status)
    delta_or_value REAL NOT NULL,           -- Delta (for balance/position) or new value (for order_status, if applicable)
    reason TEXT NOT NULL,                   -- Reason for adjustment (free text)
    created_at INTEGER NOT NULL,            -- Creation timestamp (milliseconds)
    created_by TEXT,                        -- Creator identifier (optional, e.g., "operator", "system", "admin")
    notes TEXT                              -- Free-text notes/comments (nullable, for future use, additional context beyond reason)
);
```

**Indexes:**

- Index on `(venue, type, created_at)` for queries
- Index on `venue` for venue-filtered queries

**Adjustment types:**

- `balance`: Updates `balances.free` (or `balances.locked`) for given `asset`
- `position`: Updates `positions.quantity` (and optionally `avg_price`) for given `symbol`
- `order_status`: Updates `orders.status` for given order (where `asset_or_symbol` is ledger order ID as string)

**Note:** Adjustments table is **audit-only**. Real state lives in `balances`, `positions`, `orders`. When applying adjustment:

1. Update target table (`balances`, `positions`, or `orders.status`)
2. Insert audit row into `adjustments`

## Booking System Conventions

### Venue Naming

- Use consistent venue identifiers: `"binance_spot"` for Binance Spot, `"binance_futures"` for Binance Futures (future)
- Store in `settings.venue` or derive from exchange client

### Symbol Format

- Binance uses uppercase symbols: `"BTCUSDT"`, `"ETHBTC"`, etc.
- Store as-is (uppercase) in database
- Extract base/quote by parsing symbol string (assume standard format `{BASE}{QUOTE}`)

### Timestamps

- All timestamps in **milliseconds** (Unix timestamp * 1000)
- Binance API returns milliseconds
- Store as `BIGINT` in PostgreSQL, `INTEGER` in SQLite

### Status Values

- Normalize all status strings to **uppercase**
- Order statuses: `NEW`, `PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `PENDING_CANCEL`, `REJECTED`, `EXPIRED`
- Side values: `BUY`, `SELL` (uppercase)

### Numeric Precision

- Binance returns quantities/prices as **strings** (to preserve precision)
- Convert to `float` for storage (Python `float` has ~15-17 decimal digits precision)
- For high-precision requirements, consider `Decimal` type (future enhancement)

### Commission Handling

- Commission asset comes from Binance `commissionAsset` field
- Default to quote asset if `commissionAsset` not provided
- Update balances for commission asset: `free -= commission`

### Idempotency Strategy

- **Orders:** Check `(venue, exchange_order_id)` before insert. If exists, return existing `id` (don't raise error).
- **Trades:** Check `(venue, exchange_trade_id)` before insert. If exists, return existing `id` (skip insert).
- Use `SELECT ... WHERE` before `INSERT` for idempotency checks (or use database unique constraints + handle conflicts).

## Implementation Tasks

### Phase 1: Database Schema

**1.1 Alembic migration for balances and adjustments (PostgreSQL)**

- Create `alembic/versions/006_add_balances_and_adjustments.py`
- **Database priority:** PostgreSQL is primary (via `DATABASE_URL`). SQLite is fallback only for local dev without Docker.
- **Add `book_id` column to existing tables (migration 006):**
  - Add `book_id` (String, NOT NULL, default 'default') to `orders` table
  - Add `book_id` (String, NOT NULL, default 'default') to `trades` table
  - Update `positions` table: change primary key from `symbol` to `(book_id, symbol)`, add `book_id` column
  - Update unique constraints: `orders` unique on `(venue, book_id, exchange_order_id)`, `trades` unique on `(venue, book_id, exchange_trade_id)`
- **Add `notes` column to tables (migration 006):**
  - Add `notes` (String, nullable) to `orders` table - for order comments, strategy notes, etc.
  - Add `notes` (String, nullable) to `trades` table - for trade comments, execution notes, etc.
  - Add `notes` (String, nullable) to `positions` table - for position rationale, strategy notes, etc.
  - Add `notes` (String, nullable) to `adjustments` table - for additional context beyond `reason` field
- **Balances table:**
  - Columns: `venue` (String, NOT NULL), `book_id` (String, NOT NULL, default 'default'), `asset` (String, NOT NULL), `free` (Float, NOT NULL, default 0), `locked` (Float, NOT NULL, default 0), `updated_at` (BigInteger, NOT NULL)
  - Primary key: `(venue, book_id, asset)` (composite) using `sa.PrimaryKeyConstraint('venue', 'book_id', 'asset')`
  - Index on `venue` for venue-filtered queries using `op.create_index('ix_balances_venue', 'balances', ['venue'])`
  - Index on `book_id` for book-filtered queries using `op.create_index('ix_balances_book_id', 'balances', ['book_id'])`
- **Adjustments table:**
  - Columns: `id` (Integer, PK, autoincrement), `venue` (String, NOT NULL), `book_id` (String, NOT NULL, default 'default'), `type` (String, NOT NULL), `asset_or_symbol` (String, NOT NULL), `delta_or_value` (Float, NOT NULL), `reason` (String, NOT NULL), `created_at` (BigInteger, NOT NULL), `created_by` (String, nullable)
  - Index on `(venue, book_id, type, created_at)` for queries using `op.create_index('ix_adjustments_venue_book_type_created', 'adjustments', ['venue', 'book_id', 'type', 'created_at'])`
  - Index on `venue` for venue-filtered queries
  - Index on `book_id` for book-filtered queries
  - `type` values: `"balance"`, `"position"`, `"order_status"` (enforce in application code, not DB constraint)
- **Add unique constraints for idempotency (in migration 006):**
  - Unique constraint on `orders(venue, book_id, exchange_order_id)` where `exchange_order_id IS NOT NULL` (for idempotency)
  - Unique constraint on `trades(venue, book_id, exchange_trade_id)` where `exchange_trade_id IS NOT NULL` (for idempotency)
  - Use `sa.UniqueConstraint('venue', 'book_id', 'exchange_order_id', name='uq_orders_venue_book_exchange_id')` and similar for trades
  - Note: These constraints allow same exchange_order_id/exchange_trade_id in different books (for multi-book setups)
- **Update SQLite fallback schema in `booking/ledger.py` `BOOKING_SCHEMA`:**
  - Update `orders` table: add `book_id TEXT NOT NULL DEFAULT 'default'`, add `notes TEXT`
  - Update `trades` table: add `book_id TEXT NOT NULL DEFAULT 'default'`, add `notes TEXT`
  - Update `positions` table: change primary key to `(book_id, symbol)`, add `book_id` column, add `notes TEXT`
  - Add `CREATE TABLE IF NOT EXISTS balances (...)` with same structure (use `PRIMARY KEY (venue, book_id, asset)` for SQLite)
  - Add `CREATE TABLE IF NOT EXISTS adjustments (...)` with same structure including `notes TEXT`
  - SQLite fallback is only used when `DATABASE_URL` is not set (local dev without Docker)
  - Note: SQLite unique constraints handled via application-level idempotency checks
- **Add venue configuration:**
  - Add `venue: str = "binance_spot"` to `config/settings.py` (or derive from exchange client in orchestrator)
  - Use `settings.venue` throughout booking system for consistency

### Phase 2: Ledger Enhancements

**2.1 Idempotency checks**

- **PostgreSQL:** Unique constraints on `(venue, book_id, exchange_order_id)` and `(venue, book_id, exchange_trade_id)` enforce idempotency at DB level. Handle `IntegrityError` on conflict and return existing `id`.
- **Application-level check (for both PostgreSQL and SQLite fallback):**
  - `record_order`: Check if `(venue, book_id, exchange_order_id)` already exists before insert. If exists, return existing `id` (don't raise error). Use `SELECT ... WHERE venue=:venue AND book_id=:book_id AND exchange_order_id=:exchange_order_id`.
  - `record_trade`: Check if `(venue, book_id, exchange_trade_id)` already exists. If exists, return existing `id` (skip insert). Use `SELECT ... WHERE venue=:venue AND book_id=:book_id AND exchange_trade_id=:exchange_trade_id`.
- **Error handling:** On PostgreSQL unique constraint violation, catch `IntegrityError` and query for existing record to return its `id`.
- **Book ID parameter:** All methods accept `book_id: str = "default"` parameter. Default to `"default"` for backward compatibility.

**2.2 Balance updates in `record_trade**`

- After inserting trade, update balances for base asset, quote asset, and commission asset.
- **Symbol parsing:** Extract base/quote from `symbol` string (e.g., "BTCUSDT" → base="BTC", quote="USDT")
  - Standard format: `{BASE}{QUOTE}` (e.g., BTCUSDT, ETHBTC, ADAUSDT)
  - Common quote assets (in order of preference): USDT, BUSD, USDC, BTC, ETH, BNB
  - Algorithm: Try matching longest quote asset suffix first (e.g., "BTCUSDT" → try "USDT" first, then "BTC")
  - Edge cases: Handle 3-letter bases (e.g., "ADAUSDT"), 4-letter bases (e.g., "LINKUSDT"), stablecoins (e.g., "USDCUSDT")
  - If parsing fails, log warning and skip balance update (or use symbol metadata table in future)
- **Commission asset:** Use `commissionAsset` from Binance trade response if available, else default to quote asset
- **Balance update logic:**
  - Base asset: BUY → `free += quantity`, SELL → `free -= quantity`
  - Quote asset: BUY → `free -= quantity * price` (spend quote), SELL → `free += quantity * price` (receive quote)
  - Commission asset: `free -= commission` (always subtract commission)
- **Database update (PostgreSQL-first):**
  - Primary: Use PostgreSQL `INSERT ... ON CONFLICT (venue, book_id, asset) DO UPDATE SET free=..., locked=..., updated_at=...`
  - Fallback (SQLite, only if `DATABASE_URL` not set): Use `INSERT ... ON CONFLICT (venue, book_id, asset) DO UPDATE SET ...` (SQLite 3.24+ supports ON CONFLICT)
  - Update `updated_at` to `traded_at` (trade timestamp)
  - Detect database type via `_is_postgres()` helper and use appropriate syntax
  - Update balances for the specific `book_id` (each book maintains separate balances)
- **Transaction safety:** Wrap trade insert + balance updates in a single transaction (already handled by `record_trade` connection context)
- **Error handling:**
  - Symbol parsing failures: Log warning, skip balance update (don't fail trade insert)
  - Balance update failures: Transaction rollback (handled by connection context)
  - Commission asset resolution: Default to quote asset if `commission_asset` not provided
  - Missing exchange_order_id when resolving order_id: Log warning, proceed with `order_id=None`

**2.3 Order status updates**

- Add `update_order_status(ledger_order_id: int, status: str, reason: Optional[str] = None) -> None`: UPDATE `orders.status` and `updated_at`; optionally INSERT into `adjustments` if `reason` provided.
- Add helper `get_order_by_exchange_id(venue: str, exchange_order_id: str, book_id: Optional[str] = None) -> Optional[Dict]` to resolve ledger order id from exchange order id. If `book_id` provided, filter by book; otherwise search across all books (for backward compatibility).
- **Update method signatures:** Add `book_id: str = "default"` parameter to:
  - `record_order(..., book_id: str = "default", notes: Optional[str] = None)` - add optional `notes` parameter
  - `record_trade(..., book_id: str = "default", notes: Optional[str] = None)` - add optional `notes` parameter
  - `get_positions(book_id: Optional[str] = None, symbol: Optional[str] = None)` - filter by book_id if provided, return `notes` in result dicts
  - `get_orders(book_id: Optional[str] = None, ...)` - filter by book_id if provided, return `notes` in result dicts
  - `get_trades(book_id: Optional[str] = None, ...)` - filter by book_id if provided, return `notes` in result dicts
- **Update `update_order_status`:** Add optional `notes: Optional[str] = None` parameter to update order notes when changing status
- **Update `record_adjustment`:** Add optional `notes: Optional[str] = None` parameter for additional context
- **Automatic order status updates:** In `record_trade()` or `sync_fills_for_order()`, after booking fills, update order status:
  - Calculate `SUM(trades.quantity WHERE order_id=...)` vs `orders.quantity`
  - If sum >= order quantity: set status to `FILLED`
  - If sum > 0 but < order quantity: set status to `PARTIALLY_FILLED`
  - Update `orders.updated_at` to latest trade `traded_at`

**2.4 Adjustments**

- Add `record_adjustment(venue: str, book_id: str, type: str, asset_or_symbol: str, delta_or_value: float, reason: str, created_by: Optional[str] = None, notes: Optional[str] = None) -> int`: INSERT into `adjustments` with `book_id` and optional `notes`; then UPDATE `balances` or `positions` or `orders.status` based on `type` for the specific book. Return adjustment id.
- For `type='balance'`: UPDATE `balances` SET `free = :delta_or_value` (or `free += :delta_or_value` if delta) WHERE `venue=:venue AND book_id=:book_id AND asset=:asset_or_symbol`. For `type='position'`: UPDATE `positions` SET `quantity = :delta_or_value` (or similar) WHERE `book_id=:book_id AND symbol=:asset_or_symbol`. For `type='order_status'`: UPDATE `orders.status` WHERE id matches (if `asset_or_symbol` is order id).

**2.5 Query methods**

- Add `get_balances(venue: Optional[str] = None, book_id: Optional[str] = None, asset: Optional[str] = None) -> List[Dict]`: SELECT from `balances` with optional filters. Return list of dicts with `venue`, `book_id`, `asset`, `free`, `locked`, `updated_at`.
- Add `get_adjustments(venue: Optional[str] = None, book_id: Optional[str] = None, type: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]`: SELECT from `adjustments` with optional filters, ORDER BY `created_at DESC`. Return list of dicts with all adjustment fields.

**2.6 Helper utilities**

- **Symbol parsing function:** Create `_parse_symbol(symbol: str) -> tuple[str, str]` helper:
  - Input: symbol string (e.g., "BTCUSDT")
  - Output: `(base_asset, quote_asset)` tuple (e.g., ("BTC", "USDT"))
  - Algorithm: Match longest quote asset suffix from common quotes list: `["USDT", "BUSD", "USDC", "BTC", "ETH", "BNB"]`
  - Handle edge cases: 3-letter bases (ADA), 4-letter bases (LINK), stablecoin pairs
  - If no match found, raise `ValueError` or return `(symbol, None)` and log warning
  - Place in `booking/ledger.py` as private method or in `booking/utils.py` as public utility
- **Commission asset resolution:** In `record_trade`, accept optional `commission_asset: Optional[str]` parameter. If None, use quote asset from symbol parsing.
- **Update `record_trade` signature:** Add `commission_asset: Optional[str] = None` parameter to accept commission asset from Binance trade response.

### Phase 3: Orchestrator Layer

**3.1 Create `execution/orchestrator.py**`

- Class `BookingOrchestrator` that takes `OrderManager` and `Ledger`.
- **Method `place_order(symbol, side, quantity, order_type, price=None, book_id: str = "default", ...) -> Dict`:**
  - Use `venue = settings.venue` (or derive from exchange client)
  - Use `book_id` parameter (defaults to `"default"` for single-book setups)
  - Call `OrderManager.submit_market()` or `submit_limit()` based on `order_type`
  - On success, extract from Binance response:
    - `exchange_order_id = str(response["orderId"])` (convert int to string)
    - `status = response["status"].upper()` (normalize to uppercase)
    - `created_at = response["time"]` (milliseconds)
    - `updated_at = response.get("updateTime")` (may be None)
    - `executed_qty = float(response.get("executedQty", "0"))` (convert string to float)
  - Idempotency check: Call `Ledger.get_order_by_exchange_id(venue, exchange_order_id, book_id)`; if exists, return existing order (don't re-book)
  - Call `Ledger.record_order(venue, book_id, symbol, side, order_type, quantity, status, created_at, exchange_order_id, price, updated_at)`
  - **Locked balance update (future enhancement):** When order placed, update `balances.locked`:
    - BUY order: lock quote asset (`locked += quantity * price`)
    - SELL order: lock base asset (`locked += quantity`)
    - For now, skip locked balance updates (Phase 2 focuses on free balance only)
  - Return dict: `{"ledger_order_id": int, "exchange_order_id": str, "status": str, "symbol": str, ...}`
  - On exchange error (BinanceAPIException), log and raise (don't book order)
- **Method `cancel_order(ledger_order_id: Optional[int] = None, exchange_order_id: Optional[str] = None, symbol: str, ...) -> Dict`:**
  - Resolve `exchange_order_id`: if `ledger_order_id` provided, call `Ledger.get_orders(id=ledger_order_id)` to get `exchange_order_id`; else use provided `exchange_order_id`
  - Call `OrderManager.cancel(symbol, order_id=int(exchange_order_id))`
  - On success, extract `status` from response (should be "CANCELED")
  - Call `Ledger.update_order_status(ledger_order_id, "CANCELED")` (resolve `ledger_order_id` if needed)
  - Return cancellation result dict
- **Method `sync_fills_for_order(symbol: str, exchange_order_id: str, ledger_order_id: int, book_id: str = "default") -> List[int]`:**
  - Call `OrderManager.get_fills(symbol, orderId=int(exchange_order_id))` (or `get_my_trades` with filter)
  - For each fill in response:
    - Extract: `exchange_trade_id = str(trade["id"])`, `side = trade["side"].upper()`, `quantity = float(trade["qty"])`, `price = float(trade["price"])`, `commission = float(trade["commission"])`, `commission_asset = trade.get("commissionAsset")`, `traded_at = trade["time"]`
    - Idempotency check: Call `Ledger.get_trades(venue, book_id=book_id, exchange_trade_id=exchange_trade_id)`; if exists, skip
    - Call `Ledger.record_trade(venue, book_id, symbol, side, quantity, price, traded_at, exchange_trade_id, ledger_order_id, commission, commission_asset)` (commission asset handled in `record_trade`)
  - Return list of ledger trade IDs
- **Method `sync_fills_for_symbol(symbol: str, book_id: str = "default", since: Optional[int] = None, limit: int = 100) -> List[int]`:**
  - Call `OrderManager.get_my_trades(symbol, limit=limit, startTime=since)` (Binance API params)
  - For each trade in response:
    - Extract same fields as above
    - Idempotency check: Skip if trade already booked (check by `venue, book_id, exchange_trade_id`)
    - Resolve `ledger_order_id`: if `trade["orderId"]` exists, call `Ledger.get_order_by_exchange_id(venue, str(trade["orderId"]), book_id)`; else `None`
    - Call `Ledger.record_trade(venue, book_id, ...)` with resolved `order_id`
  - Return list of ledger trade IDs

### Phase 4: Fill Sync Service

**4.1 Create `scripts/services/run_fill_sync.py**`

- Script that runs fill sync periodically (e.g. every 1-5 minutes).
- Use `BookingOrchestrator`; for each symbol in `settings.symbols` (or active symbols from ledger), call `sync_fills_for_symbol(symbol, since=last_sync_time)`.
- Track last sync time per symbol (e.g. in-memory or small state file).
- Handle errors gracefully (log, continue to next symbol).
- Optionally: also sync fills immediately after placing an order (can be called from orchestrator or separate helper).

**4.2 Integration with existing services**

- Consider adding fill sync as a separate Docker service (similar to `data-updater`) or as part of a "booking worker" that also handles order placement. For now, keep as standalone script that can be run via cron or systemd.

### Phase 5: Rebuild Utilities

**5.1 Create `scripts/utils/rebuild_positions.py**`

- Script that rebuilds `positions` table from `trades`: DELETE all positions (or filter by `book_id` if rebuilding specific book); GROUP BY `book_id, symbol`, compute `quantity = SUM(quantity * CASE side WHEN 'BUY' THEN 1 ELSE -1 END)`, `avg_price = SUM(price * quantity) / SUM(quantity)` (VWAP); INSERT into `positions`. Handle zero positions (delete or skip). Each book maintains separate positions per symbol.

**5.2 Create `scripts/utils/rebuild_balances.py**`

- Script that rebuilds `balances` table from `trades`: DELETE all balances (or filter by `book_id` if rebuilding specific book); for each trade, extract base/quote assets from symbol; replay trades into `free` per asset per book (base: BUY +, SELL -; quote: BUY -, SELL +; commission: -). Handle commission asset (from trade or default). INSERT/UPDATE balances per `(venue, book_id, asset)`. Set `updated_at` to latest `traded_at` per asset per book. Each book maintains separate balances.

### Phase 6: Reconciliation Scripts

**6.1 Create `scripts/integrity/check_booking_recon.py**`

- Script that runs all 6 reconciliations:
- **Rec 1 (order vs trades)**: For each order, `SUM(trades.quantity WHERE order_id=...)` vs `orders.quantity`; check `orders.status` consistent with fills. Report mismatches.
- **Rec 2 (trades vs Binance)**: Fetch `get_my_trades` for symbols with recent trades; match by `(venue, exchange_trade_id)`; compare symbol, side, quantity, price, time. Report missing/extra trades.
- **Rec 3 (position vs trades)**: For each `(book_id, symbol)`, `positions.quantity` vs derived from trades (SUM signed quantity, VWAP) filtered by `book_id`. Report mismatches per book.
- **Rec 4 (position vs Binance)**: Fetch `get_account()` or positions from Binance; compare to ledger positions. Note: Binance doesn't have book concept, so compare total positions across all books vs Binance, or compare per-book if book isolation is maintained at exchange level.
- **Rec 5 (orders vs Binance)**: Fetch open orders + recent order history; match by `exchange_order_id`; compare status, quantity, filled qty. Report mismatches.
- **Rec 6 (balances vs Binance)**: Fetch `get_account()` balances; compare `free`, `locked` per asset to ledger balances. Note: Binance doesn't have book concept, so compare sum of balances across all books vs Binance, or compare per-book if book isolation is maintained at exchange level. Report mismatches per book (or total if books share capital).
- Output: JSON report (similar to existing integrity checks) with per-rec results, mismatches, and summary. Save to `reports/integrity/booking_recon_<timestamp>.json` and text summary.

**6.2 Add to `scripts/integrity/run_integrity_checks.py**`

- Add booking reconciliation to the integrity check runner (optional, can run separately).

### Phase 7: Testing & Documentation

**7.1 Unit tests**

- Test `Ledger` idempotency (duplicate order/trade inserts).
- Test balance updates in `record_trade` (base, quote, commission assets).
- Test `update_order_status`, `record_adjustment`.
- Test `BookingOrchestrator` place/cancel/sync flows.

**7.2 Integration tests**

- Test full flow: place order → book order → sync fills → verify positions/balances.
- Test rebuild scripts (rebuild positions/balances from trades).
- Test reconciliation scripts (mock Binance responses or use testnet).

**7.3 Update documentation**

- Update `docs/plans/booking-system-and-recon.md` with implementation status.
- Add usage examples for orchestrator, fill sync, rebuild, recs.

## Implementation Order

1. **Phase 1** (Database schema) - Foundation
2. **Phase 2** (Ledger enhancements) - Core booking logic
3. **Phase 3** (Orchestrator) - Integration layer
4. **Phase 4** (Fill sync) - Automated fill booking
5. **Phase 5** (Rebuild utilities) - Recovery tools
6. **Phase 6** (Reconciliations) - Validation
7. **Phase 7** (Testing & docs) - Quality assurance

## Key Files to Modify/Create

- `alembic/versions/006_add_balances_and_adjustments.py` (new)
- `booking/ledger.py` (enhance: idempotency, balances, order status, adjustments)
- `execution/orchestrator.py` (new)
- `scripts/services/run_fill_sync.py` (new)
- `scripts/utils/rebuild_positions.py` (new)
- `scripts/utils/rebuild_balances.py` (new)
- `scripts/integrity/check_booking_recon.py` (new)
- `scripts/integrity/run_integrity_checks.py` (update, optional)
- `config/settings.py` (add `venue` field, optionally add `default_book_id` field)

## Notes

- **Idempotency is critical:** Always check `(venue, book_id, exchange_order_id)` and `(venue, book_id, exchange_trade_id)` before inserts. Use database unique constraints where possible, handle conflicts gracefully. Each book maintains separate orders/trades (same exchange_order_id can exist in different books).
- **Book ID:** All booking operations accept `book_id` parameter (defaults to `"default"` for single-book setups). Each book maintains separate positions and balances. For multi-book setups, books can share capital (sum balances) or isolate capital (separate balances per book).
- **Balance updates:** Must handle base/quote extraction from symbol (e.g., BTCUSDT → BTC, USDT). Consider edge cases (non-USDT pairs, commission in different asset). Use helper function for symbol parsing.
- **Adjustments table is audit-only:** Real state is in `positions`, `balances`, `orders`. When applying adjustment, update target table + insert audit row. Don't derive state from adjustments table.
- **Fill sync:** Can be run after each order (short delay) + periodically. Consider rate limits (Binance allows many `get_my_trades` calls). Use `startTime` parameter to fetch only new trades.
- **Reconciliations are read-only:** Compare, report; they don't update the ledger. Fixes are manual (fill sync, rebuild, adjustments) or via orchestrator.
- **Binance API responses:** All numeric fields come as strings; convert to float for storage. Timestamps are in milliseconds. Status strings should be normalized to uppercase.
- **Symbol parsing:** Use longest-match algorithm for quote assets. Common quotes: USDT, BUSD, USDC, BTC, ETH, BNB (in order of preference). Handle 3-4 letter bases and stablecoin pairs.
- **Commission handling:** Use `commissionAsset` from Binance trade response if available, else default to quote asset. Always subtract commission from commission asset balance.
- **Transaction safety:** Wrap trade insert + balance updates in single transaction (already handled by connection context in `record_trade`).

## Schema Summary


| Table         | Primary Key               | Idempotency Key                       | Key Fields                                                                                    |
| ------------- | ------------------------- | ------------------------------------- | --------------------------------------------------------------------------------------------- |
| `orders`      | `id` (auto)               | `(venue, book_id, exchange_order_id)` | venue, book_id, exchange_order_id, symbol, side, order_type, quantity, price, status, notes   |
| `trades`      | `id` (auto)               | `(venue, book_id, exchange_trade_id)` | venue, book_id, exchange_trade_id, order_id, symbol, side, quantity, price, commission, notes |
| `positions`   | `(book_id, symbol)`       | N/A (materialized)                    | book_id, symbol, quantity, avg_price, updated_at, notes                                       |
| `balances`    | `(venue, book_id, asset)` | `(venue, book_id, asset)`             | venue, book_id, asset, free, locked, updated_at                                               |
| `adjustments` | `id` (auto)               | N/A (audit only)                      | venue, book_id, type, asset_or_symbol, delta_or_value, reason, created_at, notes              |


**Database priority:** PostgreSQL is primary (via `DATABASE_URL`). SQLite is fallback only when `DATABASE_URL` is not set (local dev without Docker). All production deployments use PostgreSQL.

**Venue convention:** Use `"binance_spot"` for Binance Spot trading (store in settings or derive from client).

**Timestamp convention:** All timestamps in milliseconds (Unix timestamp * 1000). Binance API returns milliseconds.