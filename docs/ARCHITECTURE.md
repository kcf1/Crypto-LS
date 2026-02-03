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

Crypto-LS is a cryptocurrency trading system focused on:
- **Market Data Collection**: Automated collection of OHLCV (Open, High, Low, Close, Volume) data from Binance Spot
- **Futures Data Collection**: Automated collection of funding rates, open interest, basis (premium index), and long/short ratios (global and top trader account & position) from Binance Futures
- **Data Integrity**: Automated checks to ensure data quality and completeness
- **Strategy Backtesting**: Streamlit-based visualization and backtesting tools
- **Order Management**: Framework for order execution and booking (future)

The system is containerized using Docker and uses PostgreSQL as the primary database.

## Services

### Docker Services

The system runs three Docker services defined in `docker-compose.yml`:

#### 1. PostgreSQL (`postgres`)
- **Image**: `postgres:16-alpine`
- **Container**: `crypto-ls-postgres`
- **Port**: `5432` (mapped to host)
- **Database**: `cryptols`
- **User/Password**: `crypto/crypto`
- **Volume**: `postgres_data` (persistent storage)
- **Health Check**: `pg_isready` every 5 seconds
- **Purpose**: Primary data storage for OHLCV data and booking records

#### 2. pgAdmin (`pgadmin`)
- **Image**: `dpage/pgadmin4:latest`
- **Container**: `crypto-ls-pgadmin`
- **Port**: `5050` (mapped to host)
- **Purpose**: Web-based database administration interface
- **Access**: http://localhost:5050 (admin@example.com / admin)

#### 3. Data Updater (`data-updater`)
- **Build**: Custom image from `Dockerfile.updater`
- **Container**: `crypto-ls-data-updater`
- **Script**: `scripts/services/run_data_updater.py`
- **Interval**: 300 seconds (5 minutes), aligned to :05, :10, :15, etc.
- **Restart Policy**: `unless-stopped`
- **Dependencies**: Waits for PostgreSQL to be healthy
- **Purpose**: Continuously collects OHLCV from Binance Spot and futures data (funding rate, open interest, basis, global/top long-short account & position) from Binance Futures API

### Service Startup Order

1. PostgreSQL starts and becomes healthy
2. pgAdmin starts (depends on postgres)
3. Data Updater starts (waits for postgres to be healthy)

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

**Booking Tables** (orders, trades, positions)
- Defined in Alembic but not yet actively used
- Framework for future order execution tracking

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

### 2. Data Consumption Flow

```
PostgreSQL Database
    ↓
Storage.read_ohlcv()
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

### 3. Data Integrity Flow

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
- **`run_data_updater.py`**: Main data collection scheduler (runs all registered tasks)
- **`check_missing_bars.py`**, **`check_missing_funding_rate.py`**, **`check_missing_open_interest.py`**: Integrity checks
- **`check_missing_basis.py`**, **`check_missing_global_long_short_account.py`**, **`check_missing_top_long_short_account.py`**, **`check_missing_top_long_short_position.py`**: Futures market data integrity (7 days, 5m)
- **`run_integrity_checks.py`**: Runner for all integrity checks
- **`download_last_24h.py`**: One-time OHLCV data download script
- **`update_5y_5m.py`**: Historical OHLCV data backfill script (5 years, 5m)
- **`backfill_funding_rate.py`**: Historical funding rate backfill script (5 years)
- **`backfill_open_interest.py`**: Historical open interest backfill script (~30 days, 5m)
- **`backfill_basis.py`**, **`backfill_global_long_short_account.py`**, **`backfill_top_long_short_account.py`**, **`backfill_top_long_short_position.py`**: Futures market data backfill (~30 days, 5m)
- **`backfill_liquidations.py`**: Historical liquidations backfill script (7 days, requires API key, available but not actively used)
- **`test_*.py`**: Testing and validation scripts

#### `viz/`
- **`app.py`**: Streamlit main application
- **`pages/`**: Individual Streamlit pages for visualization and backtesting

#### `execution/` (Future)
- **`binance/client.py`**: Binance execution API client
- **`order_manager.py`**: Order management logic

#### `booking/` (Future)
- **`ledger.py`**: Order and trade booking

### Module Dependencies

```
scripts/services/run_data_updater.py
    ↓
data/updates/__init__.py
    ├─ binance_ohlcv.py ──→ Collector (Spot API)
    ├─ binance_funding_rate.py ──→ Collector (Futures API)
    ├─ binance_open_interest.py ──→ Collector (Futures API)
    ├─ binance_basis.py, binance_global_long_short_account.py, binance_top_long_short_account.py, binance_top_long_short_position.py ──→ Collector (Futures API)
    ↓
data/collector.py ──→ Binance Spot/Futures APIs
data/storage.py ──→ PostgreSQL
```

## Operations Flow

### Startup Sequence

1. **Start Docker Services**
   ```bash
   docker compose up -d
   ```

2. **PostgreSQL Initialization**
   - Container starts
   - Health check runs every 5 seconds
   - Database `cryptols` created
   - Schema applied via Alembic (if needed)

3. **Data Updater Initialization**
   - Waits for PostgreSQL to be healthy
   - Calculates next aligned 5-minute mark
   - Sleeps until alignment
   - Starts collection loop

### Normal Operation

1. **Every 5 Minutes** (aligned to :05, :10, :15, etc.)
   - Data updater wakes up
   - Runs all registered tasks concurrently:
     - **OHLCV Task**: Fetches new 5m bars from Spot API
     - **Funding Rate Task**: Checks for new funding rates (updates every 8h, skips if no new data)
     - **Open Interest Task**: Fetches new 5m open interest records
     - **Basis, Global L/S Account, Top L/S Account, Top L/S Position Tasks**: Fetches new 5m futures market data (~30 days retention)
   - Each task:
     - Fetches new data from Binance
     - Writes to database
     - Logs results
   - Sleeps until next aligned mark

2. **Data Integrity Checks** (scheduled separately)
   - Run `scripts/integrity/check_missing_bars.py` or `scripts/integrity/run_integrity_checks.py`
   - Generate reports in `reports/integrity/`
   - Alert on coverage issues

3. **Visualization** (on-demand)
   - Start Streamlit: `streamlit run viz/app.py`
   - Access pages via web interface
   - Pages query database via `Storage.read_ohlcv()`

### Error Handling

- **Task Failures**: Each task's exceptions are caught and logged; one failure doesn't stop others
- **Rate Limiting**: 429 errors handled with exponential backoff
- **Database Errors**: Logged and re-raised
- **Service Restarts**: `data-updater` has `restart: unless-stopped` policy

## Configuration

### Environment Variables

Set in `.env` file or Docker environment:

- **`DATABASE_URL`**: PostgreSQL connection string
  - Format: `postgresql://user:password@host:port/database`
  - Default (Docker): `postgresql://crypto:crypto@postgres:5432/cryptols`
  - Local: `postgresql://crypto:crypto@localhost:5432/cryptols`

- **`UPDATER_INTERVAL_SEC`**: Data collection interval in seconds
  - Default: `300` (5 minutes)

- **`BINANCE_DATA_API_KEY`**: Binance API key for data collection (read-only, reserved for future use)
- **`BINANCE_DATA_API_SECRET`**: Binance API secret for data collection (read-only, reserved for future use)
- **`BINANCE_TRADING_API_KEY`**: Binance API key for trading/order management (read + trade)
- **`BINANCE_TRADING_API_SECRET`**: Binance API secret for trading/order management
- **`BINANCE_API_KEY`**: Legacy single API key (fallback if separate keys not set)
- **`BINANCE_API_SECRET`**: Legacy single API secret (fallback if separate keys not set)
- **`BINANCE_TESTNET_API_KEY`**: Testnet API key
- **`BINANCE_TESTNET_API_SECRET`**: Testnet API secret

### Settings (`config/settings.py`)

- **Symbols**: `TOP_100_SYMBOLS` (100 USDT pairs) - used for both Spot and Futures
- **Default Timeframe**: `5m`
- **OHLCV Limit**: `1000` bars per API request
- **Open Interest Period**: `5m` (default)
- **Funding Rate Collection**: Enabled by default
- **Logging**: File-based logging to `logs/app.log`

### Docker Configuration

- **`docker-compose.yml`**: Service definitions
- **`Dockerfile.updater`**: Data updater container image
- **Volumes**: `postgres_data` for database persistence

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

See `docs/operations/monitoring.md` for detailed monitoring procedures.

### Key Metrics

- **Service Status**: `docker compose ps`
- **Data Collection Logs**: `docker logs -f crypto-ls-data-updater`
- **Database Size**: Query `pg_database_size('cryptols')`
- **Latest Data**: Query `MAX(open_time)` per symbol
- **Coverage**: Run integrity checks

### Health Checks

- **PostgreSQL**: Built-in health check in Docker
- **Data Updater**: Check container status and logs
- **Data Integrity**: Automated checks via `check_missing_bars.py`

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

- **Operations Manuals**: `docs/operations/`
  - `docker-setup.md`: Docker setup and configuration
  - `monitoring.md`: Monitoring and troubleshooting
  - `data-integrity.md`: Data integrity framework
- **Reports**: `reports/README.md`
- **Visualization**: `viz/README.md`
