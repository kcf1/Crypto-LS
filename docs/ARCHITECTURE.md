# Architecture & Operations Flow

This document describes the overall architecture, data flow, and operations of the Crypto-LS system.

## Table of Contents

1. [System Overview](#system-overview)
2. [Services](#services)
3. [Database](#database)
4. [Data Flow](#data-flow)
5. [Module Architecture](#module-architecture)
6. [Operations Flow](#operations-flow)
7. [Configuration](#configuration)

## System Overview

Crypto-LS is a cryptocurrency trading system with:

- **Market Data Collection**: Automated collection of OHLCV from Binance Spot and futures data (funding rate, open interest, basis, long/short ratios) from Binance Futures
- **Data Integrity**: Automated checks for data quality and completeness
- **Strategy Backtesting**: Streamlit-based visualization and backtesting
- **Order Execution & Booking**: Order Executor service (Redis Stream consumer + HTTP API) for placing orders on Binance and booking to the ledger; Fill Sync service for periodic fill reconciliation

The system is containerized with Docker. PostgreSQL is the primary database; Redis is used for the order stream (consumer group pattern).

## Services

### Docker Services

Services are defined in `docker-compose.yml`. Core services:

#### 1. PostgreSQL (`postgres`)
- **Image**: `postgres:16-alpine`
- **Container**: `crypto-ls-postgres`
- **Port**: `5432`
- **Database**: `cryptols` (user/password: `crypto/crypto`)
- **Volume**: `postgres_data`
- **Health check**: `pg_isready` every 5s
- **Purpose**: Primary storage for OHLCV, futures data, and booking (orders, trades, positions, balances, adjustments)

#### 2. pgAdmin (`pgadmin`)
- **Image**: `dpage/pgadmin4:latest`
- **Container**: `crypto-ls-pgadmin`
- **Port**: `5050`
- **Purpose**: Web UI for database administration (http://localhost:5050; admin@example.com / admin)
- **Note**: Optional; start only when needed to save memory.

#### 3. Redis (`redis`)
- **Image**: `redis:7-alpine`
- **Container**: `crypto-ls-redis`
- **Port**: `6379`
- **Volume**: `redis_data`
- **Config**: AOF persistence; maxmemory 256MB; policy `allkeys-lru`
- **Purpose**: Order stream for automated order flow. Stream name: `order_stream`; consumer group: `order_executors`. Order Executor consumes from this stream, places orders via Binance API, and books to the ledger.

#### 4. Data Updater (`data-updater`)
- **Build**: `Dockerfile.updater`
- **Container**: `crypto-ls-data-updater`
- **Script**: `scripts/services/run_data_updater.py`
- **Interval**: 300s (5 minutes), aligned to :05, :10, :15, etc.
- **Depends on**: postgres (healthy)
- **Purpose**: Collects OHLCV from Binance Spot and futures data (funding rate, open interest, basis, global/top long-short account & position) from Binance Futures API; writes to PostgreSQL.

#### 5. Order Executor (`order-executor`)
- **Build**: `Dockerfile.executor`
- **Container**: `crypto-ls-order-executor`
- **Port**: `8000`
- **Depends on**: postgres (healthy), redis (started)
- **Purpose**: (1) Redis consumer: reads from `order_stream`, places orders via `BookingOrchestrator`, books to Ledger, syncs fills immediately, ACKs messages. (2) HTTP API: health, query orders/positions/balances/trades, place order, cancel order. (3) Admin: manual trade/order booking, adjustments, rebuild positions/balances, reconciliation. See [Order & Booking Services Architecture](plans/architecture/order-booking-services-architecture.md).

#### 6. Fill Sync (`fill-sync`)
- **Build**: `Dockerfile.executor` (same image as Order Executor, different command)
- **Container**: `crypto-ls-fill-sync`
- **Command**: `python scripts/services/run_fill_sync.py`
- **Depends on**: postgres (healthy)
- **Purpose**: Runs every 60 seconds; syncs fills from Binance for configured symbols and books trades to the ledger. Backup for any fills not captured by Order Executor’s immediate sync.

#### 7. RedisInsight (`redisinsight`) — optional
- **Image**: `redis/redisinsight:latest`
- **Container**: `crypto-ls-redisinsight`
- **Port**: `5540`
- **Purpose**: Redis GUI for inspecting streams and keys. Start only when needed.

### Service Startup Order

1. PostgreSQL starts and becomes healthy.
2. pgAdmin and Redis can start (pgAdmin depends on postgres).
3. Data Updater starts after postgres is healthy.
4. Order Executor starts after postgres is healthy and redis is started.
5. Fill Sync starts after postgres is healthy.

## Database

### Schema

The database schema is managed by Alembic migrations (`alembic/versions/`).

#### Current Schema

**Revision 001**: OHLCV and Booking tables

**OHLCV Table** (`ohlcv`)
- **Purpose**: Stores raw OHLCV market data from Binance Spot
- **Primary Key**: `(symbol, timeframe, open_time)`
- **Columns**:
  - `symbol` (String): Trading pair (e.g., "BTCUSDT")
  - `timeframe` (String): Interval (e.g., "5m", "1h")
  - `open_time` (BigInteger): Bar start time (milliseconds since epoch)
  - `open`, `high`, `low`, `close` (Float): OHLC prices
  - `volume` (Float): Trading volume
  - `close_time` (BigInteger): Bar end time (milliseconds)
- **Index**: `ix_ohlcv_symbol_timeframe` on `(symbol, timeframe)`

**Booking Tables** (managed by `booking/ledger.py`)
- **orders**: Order records (ledger id, exchange id, symbol, side, quantity, status, book_id, etc.)
- **trades**: Fill/trade records (linked to orders; quantity, price, commission, exchange_trade_id)
- **positions**: Aggregated position per book/symbol (from trades and adjustments)
- **balances**: Aggregated balance per book/asset (from trades and adjustments)
- **adjustments**: Manual adjustments for reconciliation (balance or position deltas)
- Used by Order Executor (place + book) and Fill Sync; queryable via Order Executor HTTP API.

**Revision 002**: Futures Data tables

**Funding Rate Table** (`funding_rate`)
- **Purpose**: Stores funding rate history from Binance USDT-Margined Futures
- **Primary Key**: `(symbol, funding_time)`
- **Columns**:
  - `symbol` (String): Trading pair (e.g., "BTCUSDT")
  - `funding_time` (BigInteger): Funding rate timestamp (milliseconds)
  - `funding_rate` (Float): Funding rate value
  - `mark_price` (Float): Mark price at funding time
- **Index**: `ix_funding_rate_symbol` on `symbol`
- **Update Frequency**: Every 8 hours (00:00, 08:00, 16:00 UTC)

**Open Interest Table** (`open_interest`)
- **Purpose**: Stores open interest history from Binance Futures
- **Primary Key**: `(symbol, period, timestamp)`
- **Columns**:
  - `symbol` (String): Trading pair (e.g., "BTCUSDT")
  - `period` (String): Period (e.g., "5m", "1h")
  - `timestamp` (BigInteger): Timestamp (milliseconds)
  - `sum_open_interest` (Float): Total open interest in contracts
  - `sum_open_interest_value` (Float): Total open interest value in base asset
- **Index**: `ix_open_interest_symbol_period` on `(symbol, period)`
- **Data Retention**: ~30 days historical data available
- **Update Frequency**: Every 5 minutes (5m periods)

**Liquidations Table** (`liquidations`)
- **Purpose**: Stores liquidation orders from Binance Futures (table exists but not actively collected)
- **Primary Key**: `id` (auto-increment)
- **Columns**:
  - `symbol` (String): Trading pair
  - `time` (BigInteger): Liquidation timestamp
  - `order_id` (BigInteger): Unique order ID (unique index)
  - `side` (String): Order side (BUY/SELL)
  - `order_type` (String): Order type
  - `quantity` (Float): Order quantity
  - `price` (Float): Order price
  - `avg_price` (Float): Average fill price
  - `status` (String): Order status
  - `last_filled_qty` (Float): Last filled quantity
  - `filled_accumulated_qty` (Float): Total filled quantity
  - `trade_time` (BigInteger): Trade timestamp
- **Indexes**: `ix_liquidations_symbol_time` on `(symbol, time)`, unique on `order_id`
- **Status**: Table exists in schema but liquidations collection is disabled. Historical backfill scripts are available if needed.

**Revision 003 / 004**: Futures market data tables (5m period; Binance retains ~30 days)

**Basis Table** (`basis`)
- **Purpose**: Premium index (basis) from Binance Futures
- **Primary Key**: `(symbol, period, timestamp)`
- **Columns**: `symbol`, `period`, `timestamp`, `basis_rate`, `basis`, `futures_price`, `index_price`
- **Index**: `ix_basis_symbol_period` on `(symbol, period)`
- **Update Frequency**: Every 5 minutes

**Global Long/Short Account Table** (`global_long_short_account`)
- **Purpose**: All-traders long/short account ratio (5m)
- **Primary Key**: `(symbol, period, timestamp)`
- **Columns**: `symbol`, `period`, `timestamp`, `long_short_ratio`, `long_account`, `short_account`
- **Index**: `ix_global_long_short_account_symbol_period`
- **Update Frequency**: Every 5 minutes

**Top Long/Short Account Table** (`top_long_short_account`)
- **Purpose**: Top-trader long/short account ratio (5m)
- **Primary Key**: `(symbol, period, timestamp)`
- **Columns**: `symbol`, `period`, `timestamp`, `long_short_ratio`, `long_account`, `short_account`
- **Index**: `ix_top_long_short_account_symbol_period`
- **Update Frequency**: Every 5 minutes

**Top Long/Short Position Table** (`top_long_short_position`)
- **Purpose**: Top-trader long/short position ratio (5m); USDT-M API returns longAccount/shortAccount
- **Primary Key**: `(symbol, period, timestamp)`
- **Columns**: `symbol`, `period`, `timestamp`, `long_short_ratio`, `long_position`, `short_position`
- **Index**: `ix_top_long_short_position_symbol_period`
- **Update Frequency**: Every 5 minutes

**Data Retention**: All four futures market data types: only ~30 days of historical data available from Binance.

**Revision 005**: Market Cap table (CoinGecko external data)

**Market Cap Table** (`market_cap`)
- **Purpose**: Stores market capitalization and related market data from CoinGecko API
- **Primary Key**: `(symbol, timestamp)` - one record per symbol per day
- **Columns**:
  - `symbol` (String): Binance trading pair (e.g., "BTCUSDT")
  - `timestamp` (BigInteger): Snapshot timestamp (milliseconds, midnight UTC)
  - `market_cap` (Float): Market capitalization in USD
  - `circulating_supply` (Float): Circulating supply
  - `total_supply` (Float): Total supply
  - `max_supply` (Float, nullable): Maximum supply
  - `market_cap_rank` (Integer, nullable): Market cap ranking
  - `fully_diluted_valuation` (Float, nullable): Fully diluted valuation (FDV)
  - `current_price` (Float): Current price in USD
  - `total_volume` (Float): 24h trading volume
  - `high_24h` (Float, nullable): 24h high price
  - `low_24h` (Float, nullable): 24h low price
  - `price_change_24h` (Float, nullable): 24h price change
  - `price_change_percentage_24h` (Float, nullable): 24h price change percentage
  - `market_cap_change_24h` (Float, nullable): 24h market cap change
  - `market_cap_change_percentage_24h` (Float, nullable): 24h market cap change percentage
- **Index**: `ix_market_cap_symbol` on `symbol`
- **Update Frequency**: Daily snapshots (once per day)
- **Data Source**: CoinGecko API (external, not Binance)

### Database Access

- **Production**: PostgreSQL (via `DATABASE_URL` environment variable)
- **Development**: SQLite fallback (`data.db`) if `DATABASE_URL` not set
- **Connection**: Handled by `data/storage.py` `Storage` class

## Data Flow

### 1. Data Collection Flow

```
Binance Spot API          Binance Futures API          CoinGecko API
    ↓                           ↓                           ↓
Collector (data/collector.py) - extends to Futures endpoints
CoinGeckoCollector (data/coingecko_collector.py)
    ↓                           ↓                           ↓
Task Registry (data/updates/__init__.py)
    ├─ Binance OHLCV Task
    ├─ Binance Funding Rate Task
    ├─ Binance Open Interest Task
    ├─ Binance Basis Task
    ├─ Binance Global Long/Short Account Task
    ├─ Binance Top Long/Short Account Task
    ├─ Binance Top Long/Short Position Task
    └─ CoinGecko Market Cap Task
    ↓
Storage (data/storage.py)
    ↓
PostgreSQL Database
```

#### Detailed Steps

1. **Scheduler** (`scripts/services/run_data_updater.py`)
   - Runs every 5 minutes, aligned to :05, :10, :15, etc.
   - Calls `data.updates.run_all()`

2. **Task Registry** (`data/updates/__init__.py`)
   - Manages multiple data source tasks
   - Runs tasks concurrently using `ThreadPoolExecutor`
   - Registered tasks:
     - `binance_ohlcv`: Spot OHLCV data
     - `binance_funding_rate`: Futures funding rates
     - `binance_open_interest`: Futures open interest (5m periods)
     - `binance_basis`: Futures basis / premium index (5m, ~30 days)
     - `binance_global_long_short_account`: Futures global L/S account ratio (5m, ~30 days)
     - `binance_top_long_short_account`: Futures top-trader L/S account ratio (5m, ~30 days)
     - `binance_top_long_short_position`: Futures top-trader L/S position ratio (5m, ~30 days)
     - `coingecko_market_cap`: Market cap data from CoinGecko (daily snapshots)

3. **Binance OHLCV Task** (`data/updates/binance_ohlcv.py`)
   - For each symbol in `settings.symbols` (100 symbols):
     - Gets latest stored bar timestamp from database
     - Calculates start time: `latest - (TAIL_BARS - 1) * interval_ms`
     - Fetches new bars + tail refresh (last 3 bars) from Binance Spot API
     - Handles rate limiting (429 errors) with retry logic
     - Writes to database via `Storage.write_ohlcv()`
   - Delay: 0.1 seconds between symbols to avoid rate limits

4. **Binance Funding Rate Task** (`data/updates/binance_funding_rate.py`)
   - For each symbol in `settings.symbols`:
     - Gets latest stored funding_time from database
     - Fetches new funding rates + tail refresh (last 1 record) from Binance Futures API
     - Funding rate updates every 8 hours (00:00, 08:00, 16:00 UTC), but checks every 5 mins
     - Writes to database via `Storage.write_funding_rate()`
   - Delay: 0.1 seconds between symbols

5. **Binance Open Interest Task** (`data/updates/binance_open_interest.py`)
   - For each symbol in `settings.symbols`:
     - Gets latest stored timestamp for period="5m" from database
     - Fetches new open interest records + tail refresh (last 3 records) from Binance Futures API
     - Period: 5m (as configured)
     - Writes to database via `Storage.write_open_interest()`
   - Delay: 0.1 seconds between symbols
   - Note: Only ~30 days of historical data available

6. **Futures market data tasks** (basis, global/top long-short account & position)
   - Each runs like open interest: get latest timestamp, fetch new + tail from Binance Futures, write via Storage
   - Period: 5m; ~30 days historical data available
   - Basis: `/futures/data/basis` (pair, contractType=PERPETUAL, period, limit 500; paginate forward)
   - Global L/S account: `/futures/data/globalLongShortAccountRatio`
   - Top L/S account: `/futures/data/topLongShortAccountRatio`
   - Top L/S position: `/futures/data/topLongShortPositionRatio` (USDT-M returns longAccount/shortAccount)

7. **CoinGecko Market Cap Task** (`data/updates/coingecko_market_cap.py`)
   - Fetches current market cap data for all symbols in `settings.symbols`
   - Uses CoinGecko `/coins/markets` endpoint with `symbols` parameter (batched, max 50 per request)
   - Maps Binance symbols to CoinGecko symbols (e.g., BTCUSDT -> btc)
   - Stores daily snapshot with current timestamp
   - Update frequency: Once per day (daily snapshot)
   - Rate limits: ~30 calls/min (free tier), uses 1 second delay between requests
   - Writes to database via `Storage.write_market_cap()`

8. **Collector** (`data/collector.py`)
   - Makes HTTP requests to Binance REST APIs
   
9. **CoinGeckoCollector** (`data/coingecko_collector.py`)
   - Makes HTTP requests to CoinGecko REST API
   - Methods: `fetch_coins_list()`, `fetch_market_cap()`, `fetch_historical_market_cap()`
   - Handles symbol mapping (Binance -> CoinGecko)
   - Respects rate limits with retry logic
   - **Spot Endpoints**:
     - `/api/v3/klines`: Returns OHLCV tuples
   - **Futures Endpoints** (USDT-Margined):
     - `/fapi/v1/fundingRate`: Returns funding rate tuples `(funding_time, funding_rate, mark_price)`
     - `/futures/data/openInterestHist`: Returns open interest tuples `(timestamp, sum_open_interest, sum_open_interest_value)`
     - `/futures/data/basis`: Returns basis tuples `(timestamp, basis_rate, basis, futures_price, index_price)`
     - `/futures/data/globalLongShortAccountRatio`: Returns L/S account tuples
     - `/futures/data/topLongShortAccountRatio`: Returns top-trader L/S account tuples
     - `/futures/data/topLongShortPositionRatio`: Returns top-trader L/S position tuples (longAccount/shortAccount)
   - Supports testnet and production

8. **Storage** (`data/storage.py`)
   - Uses SQLAlchemy for database access
   - **OHLCV methods**: `write_ohlcv()`, `get_latest_open_time()`, `read_ohlcv()`
   - **Funding Rate methods**: `write_funding_rate()`, `get_latest_funding_time()`
   - **Open Interest methods**: `write_open_interest()`, `get_latest_open_interest_time()`, `read_open_interest()`
   - **Basis methods**: `write_basis()`, `read_basis()`, `get_latest_basis_time()`
   - **Global L/S account methods**: `write_global_long_short_account()`, `read_global_long_short_account()`, `get_latest_global_long_short_account_time()`
   - **Top L/S account methods**: `write_top_long_short_account()`, `read_top_long_short_account()`, `get_latest_top_long_short_account_time()`
   - **Top L/S position methods**: `write_top_long_short_position()`, `read_top_long_short_position()`, `get_latest_top_long_short_position_time()`
   - **Market Cap methods**: `write_market_cap()`, `read_market_cap()`, `get_latest_market_cap_time()` (CoinGecko data)
   - **Liquidations methods**: `write_liquidations()`, `get_latest_liquidation_time()` (available but not actively used)
   - All write methods use ON CONFLICT UPDATE

### 2. Order Execution & Booking Flow

```
Strategy / External System / HTTP API
    ↓
Redis Stream: order_stream (consumer group: order_executors)
    ↓
Order Executor (scripts/services/run_order_executor.py)
    ├─ BookingOrchestrator.place_order() → Binance API
    ├─ Ledger.record_order() / record_trade()
    └─ Immediate fill sync after place
    ↓
PostgreSQL (orders, trades, positions, balances)

Fill Sync (scripts/services/run_fill_sync.py): every 60s, syncs fills from Binance for all symbols, books missed trades to Ledger.
```

Manual operations (manual trade/order, adjustments, rebuilds, reconciliation) go through Order Executor HTTP API (`POST /admin/*`, `GET /admin/reconciliation`).

### 3. Data Consumption Flow (Market Data → Viz)

```
PostgreSQL Database
    ↓
Storage.read_ohlcv() / read_*()
    ↓
Streamlit Pages (viz/pages/)
    ↓
Visualization & Backtesting
```

**Streamlit Pages**:
- `1_ohlc_check.py`: View OHLCV data
- `2_eod_bar.py`: End-of-day analysis
- `3_vol_target_backtest.py`: Volatility targeting backtest
- `4_trend_following_backtest.py`: EMA crossover strategy
- `5_trend_following_regime.py`: Trend following with volatility regime
- `6_channel_breakout_backtest.py`: Channel breakout strategy
- `7_last_week_5m.py`: Last week 5-minute data visualization
- `8_open_interest.py`, `9_funding_rate.py`: Open interest and funding rate
- `10_basis.py`, `11_global_long_short_account.py`, `12_top_long_short_account.py`, `13_top_long_short_position.py`: Futures market data (basis, L/S ratios)

### 4. Data Integrity Flow

```
PostgreSQL Database
    ↓
check_missing_bars.py
    ↓
Gap Detection & Analysis
    ↓
Reports (reports/integrity/)
```

**Integrity Checks**:
- `scripts/integrity/check_missing_bars.py`: Missing 5-minute bars (last 48 hours)
- `scripts/integrity/check_missing_funding_rate.py`: Missing funding rate (last 30 days)
- `scripts/integrity/check_missing_open_interest.py`: Missing open interest (last 7 days)
- `scripts/integrity/check_missing_basis.py`, `check_missing_global_long_short_account.py`, `check_missing_top_long_short_account.py`, `check_missing_top_long_short_position.py`: Missing futures market data (last 7 days, 5m)
- `scripts/integrity/run_integrity_checks.py`: Runs all checks; generates JSON and text reports in `reports/integrity/`

## Module Architecture

### Core Modules

#### `config/`
- **`settings.py`**: Centralized configuration
  - Symbols list (TOP_100_SYMBOLS)
  - Database URL
  - Timeframes
  - Feature flags
- **`logging.py`**: Logging configuration
- **`secrets.py`**: API keys and secrets management

#### `data/`
- **`collector.py`**: Binance API client for fetching klines and futures data
  - Spot endpoints: `/api/v3/klines`
  - Futures endpoints: `/fapi/v1/fundingRate`, `/futures/data/openInterestHist`, `/futures/data/basis`, `/futures/data/globalLongShortAccountRatio`, `/futures/data/topLongShortAccountRatio`, `/futures/data/topLongShortPositionRatio`
- **`futures_auth.py`**: Authentication helpers for Binance Futures API (HMAC-SHA256, available but not actively used)
- **`storage.py`**: Database abstraction layer (SQLAlchemy)
  - OHLCV methods: `write_ohlcv()`, `get_latest_open_time()`, `read_ohlcv()`
  - Funding rate methods: `write_funding_rate()`, `get_latest_funding_time()`
  - Open interest methods: `write_open_interest()`, `get_latest_open_interest_time()`, `read_open_interest()`
  - Basis, global/top L/S account & position: `write_*`, `read_*`, `get_latest_*_time()` for each
  - Liquidations methods: `write_liquidations()`, `get_latest_liquidation_time()` (available but not actively used)
- **`updates/`**: Data update tasks
  - **`__init__.py`**: Task registry and runner
  - **`binance_ohlcv.py`**: Binance Spot OHLCV update task
  - **`binance_funding_rate.py`**: Binance Futures funding rate update task
  - **`binance_open_interest.py`**: Binance Futures open interest update task (5m periods)
  - **`binance_basis.py`**, **`binance_global_long_short_account.py`**, **`binance_top_long_short_account.py`**, **`binance_top_long_short_position.py`**: Futures market data (5m, ~30 days)
- **`integrity/`**: Data integrity checking framework
  - **`base.py`**: Base classes for integrity checks
- **`streams/`**: WebSocket streaming (future use)
  - **`binance/`**: Binance WebSocket implementation

#### `scripts/`
- **`services/run_data_updater.py`**: Data collection scheduler (runs all registered tasks every 5 minutes)
- **`services/run_order_executor.py`**: Order Executor service — Redis Stream consumer for `order_stream` + Flask HTTP API (orders, positions, balances, trades, admin)
- **`services/run_fill_sync.py`**: Fill Sync service — periodic sync of fills from Binance to Ledger (every 60s)
- **`integrity/`**: Integrity check scripts (missing bars, funding rate, open interest, basis, L/S ratios); **`run_integrity_checks.py`** runs all and writes reports to `reports/integrity/`
- **`integrity/check_booking_recon.py`**: Booking reconciliation (orders vs trades, positions vs Binance, etc.); invoked via Order Executor `GET /admin/reconciliation` or standalone
- **`utils/rebuild_positions.py`**, **`utils/rebuild_balances.py`**: Rebuild positions/balances from ledger; used by Order Executor admin endpoints
- **`download_last_24h.py`**, **`update_5y_5m.py`**, **`backfill_*.py`**: One-time and historical backfill scripts
- **`test_*.py`**: Testing and validation scripts

#### `viz/`
- **`app.py`**: Streamlit main application
- **`pages/`**: Individual Streamlit pages for visualization and backtesting

#### `execution/`
- **`binance/client.py`**: Binance Spot execution API client (place/cancel order, etc.)
- **`order_manager.py`**: Order management (place/cancel on exchange)
- **`orchestrator.py`**: `BookingOrchestrator` — coordinates place order on exchange, record order/trades in Ledger, immediate fill sync; used by Order Executor and Fill Sync

#### `booking/`
- **`ledger.py`**: Ledger — records orders, trades, positions, balances, adjustments in PostgreSQL; used by Order Executor and Fill Sync

### Module Dependencies

**Data collection:**
```
scripts/services/run_data_updater.py
    → data/updates/__init__.py → data/collector.py (Binance APIs), data/storage.py → PostgreSQL
```

**Order execution & booking:**
```
Redis (order_stream) → scripts/services/run_order_executor.py
    → execution/orchestrator.py (BookingOrchestrator) → execution/order_manager.py, booking/ledger.py
    → Binance API (place/cancel), PostgreSQL (orders, trades, positions, balances)

scripts/services/run_fill_sync.py
    → execution/orchestrator.py (sync_fills_for_symbol), booking/ledger.py → PostgreSQL
```

## Operations Flow

### Startup Sequence

1. **Start Docker Services**
   ```bash
   docker compose up -d
   ```

2. **PostgreSQL** starts first; health check runs every 5s; database `cryptols` and schema (Alembic) as needed.

3. **Redis** starts; no health dependency for other services (Order Executor only needs redis started).

4. **Data Updater** waits for postgres healthy, then sleeps until next aligned 5-minute mark and starts the collection loop.

5. **Order Executor** waits for postgres healthy and redis started; starts Flask HTTP server and Redis Stream consumer (listens to `order_stream`).

6. **Fill Sync** waits for postgres healthy; sleeps until next aligned minute, then runs a sync cycle every 60s.

### Normal Operation

1. **Every 5 minutes** (data-updater): OHLCV, funding rate, open interest, basis, L/S account and position tasks run; data written to PostgreSQL.

2. **Continuous** (order-executor): Consumes messages from `order_stream`; for each message, places order via Binance, books to Ledger, syncs fills, ACKs. HTTP API (health, orders, positions, balances, trades, admin) available on port 8000.

3. **Every 60 seconds** (fill-sync): Syncs fills from Binance for configured symbols; books any missed trades to Ledger.

4. **Data integrity** (on-demand or scheduled): Run `scripts/integrity/run_integrity_checks.py`; reports in `reports/integrity/`.

5. **Visualization** (on-demand): `streamlit run viz/app.py`; pages read from PostgreSQL via Storage.

### Error Handling

- **Task failures**: Data-updater tasks log exceptions; one failure does not stop others.
- **Rate limiting**: 429 from Binance handled with retries/backoff.
- **Order Executor**: On process error, Redis message is not ACKed and can be retried by another consumer in the group.
- **Restarts**: `data-updater`, `order-executor`, `fill-sync` use `restart: unless-stopped`.

## Configuration

### Environment Variables

Set in `.env` or Docker environment:

- **`DATABASE_URL`**: PostgreSQL connection string (e.g. `postgresql://crypto:crypto@postgres:5432/cryptols` in Docker, `@localhost:5432` locally).
- **`UPDATER_INTERVAL_SEC`**: Data collection interval in seconds (default `300`).
- **`REDIS_URL`**: Redis connection (default in Docker: `redis://redis:6379/0`; local: `redis://localhost:6379/0`). Used by Order Executor for `order_stream`.
- **`ORDER_EXECUTOR_PORT`**, **`ORDER_EXECUTOR_HOST`**: Order Executor HTTP server (default `8000`, `0.0.0.0`).
- **Binance API**: `BINANCE_TRADING_API_KEY` / `BINANCE_TRADING_API_SECRET` for trading and order execution; optional `BINANCE_DATA_API_KEY` / `BINANCE_DATA_API_SECRET` for data; legacy `BINANCE_API_KEY` / `BINANCE_API_SECRET` fallback; testnet keys for testnet.

### Settings (`config/settings.py`)

- **Symbols**: `TOP_100_SYMBOLS` (100 USDT pairs) for Spot and Futures.
- **Default timeframe**: `5m`; OHLCV limit 1000 bars per request; open interest period `5m`.
- **Venue**: Used by Order Executor for order placement (e.g. `binance_spot`).
- **Logging**: File-based to `logs/app.log`; level from config.

### Docker Configuration

- **`docker-compose.yml`**: Defines postgres, pgadmin, redis, redisinsight, data-updater, order-executor, fill-sync.
- **`Dockerfile.updater`**: Data updater image.
- **`Dockerfile.executor`**: Order Executor and Fill Sync image (same image, different command for fill-sync).
- **Volumes**: `postgres_data`, `redis_data`, `redisinsight_data`.

## Data Collection Details

### Incremental Updates

The system uses an incremental update strategy for all data types:

1. **Tail Refresh**: Re-fetches last N records to capture corrections
   - OHLCV: Last 3 bars
   - Funding Rate: Last 1 record
   - Open Interest: Last 3 records (15 minutes for 5m period)
2. **New Records**: Fetches all records after the latest stored timestamp
3. **Upsert Logic**: `ON CONFLICT UPDATE` ensures latest data overwrites old

### Historical Backfill

One-time historical data collection scripts:

- **`backfill_funding_rate.py`**: Backfills up to 5 years of funding rate data
- **`backfill_open_interest.py`**: Backfills maximum available (~30 days) of open interest data
- **`backfill_liquidations.py`**: Backfills maximum available (7 days) of liquidation data (requires API key, available but not actively used)

Run these scripts before starting continuous collection to build historical database.

### Rate Limiting

- **Delay**: 0.1 seconds between symbols
- **429 Handling**: Retries with `Retry-After` header value
- **Max Retries**: 5 attempts per request
- **Futures API Limits**: Different from Spot API; delays help avoid rate limits

### Time Alignment

Data collection runs at aligned 5-minute marks:
- :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55, :00
- Prevents drift and ensures consistent timing
- Funding rate updates every 8 hours but checked every 5 mins (skips if no new data)

### Data Retention Limits

- **OHLCV**: Full historical data available (backfill to 5+ years)
- **Funding Rate**: Full historical data available (backfill to 5+ years)
- **Open Interest**: ~30 days historical data (Binance limitation)

## Monitoring

See `docs/operations/monitoring/monitoring.md` for detailed procedures.

### Key Metrics

- **Service status**: `docker compose ps`
- **Data collection**: `docker logs -f crypto-ls-data-updater`
- **Order Executor**: `docker logs -f crypto-ls-order-executor`; HTTP `GET http://localhost:8000/health`
- **Fill Sync**: `docker logs -f crypto-ls-fill-sync`
- **Redis**: `docker compose exec redis redis-cli ping`; stream info: `redis-cli xinfo streams`
- **Database**: `pg_database_size('cryptols')`; latest data per symbol; run integrity checks for coverage

## Extensibility

### Adding New Data Sources

1. Create module in `data/updates/` (e.g., `other_exchange.py`)
2. Implement `run()` function following the pattern:
   - Get latest timestamp from storage
   - Fetch new data using Collector
   - Write to storage
   - Handle errors and rate limiting
3. Register in `data/updates/__init__.py` `TASKS` list
4. Task runs automatically on next cycle (every 5 minutes)

### Adding New Futures Data Types

1. Add database schema via Alembic migration
2. Add Collector method in `data/collector.py` (use Futures API base URL)
3. Add Storage write/read methods in `data/storage.py`
4. Create update task in `data/updates/` following existing pattern
5. Create historical backfill script in `scripts/` if needed
6. Register task in `data/updates/__init__.py`

### Adding New Integrity Checks

1. Create script in `scripts/` (e.g., `check_data_freshness.py`)
2. Use `data/integrity/base.py` framework
3. Add to `scripts/integrity/run_integrity_checks.py`
4. Reports saved to `reports/integrity/`

### Adding New Streamlit Pages

1. Create file in `viz/pages/` (e.g., `8_new_strategy.py`)
2. Page appears automatically in Streamlit navigation
3. Use `Storage.read_ohlcv()` to query data

## Related Documentation

- **Order & booking**: [Order & Booking Services Architecture](plans/architecture/order-booking-services-architecture.md)
- **Operations**: `docs/operations/` — docker-setup, monitoring, data-integrity
- **Reports**: `reports/README.md`
- **Visualization**: `viz/README.md`
