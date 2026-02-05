# Plan: Futures Market Data Collection

This plan follows the [SOP: Adding New Data Table](../operations/sop-add-new-data-table.md) to add four new Binance Futures market data types: **Basis**, **Global Long/Short Ratio (Accounts)**, **Top Trader Long/Short Ratio (Accounts)**, and **Top Trader Long/Short Ratio (Positions)**. (Taker Buy/Sell Volume is Coin-M only, not USDT-M; dropped.)

**Data retention:** All endpoints expose only the **last 30 days** of data.

---

## Summary Table

| Data Type | Endpoint | Period | Primary Key | Update Freq |
|-----------|----------|--------|-------------|-------------|
| Basis | `/futures/data/basis` | 5m–1d | (symbol, period, timestamp) | Per period |
| Global L/S (Accounts) | `/futures/data/globalLongShortAccountRatio` | 5m–1d | (symbol, period, timestamp) | Per period |
| Top Trader L/S (Accounts) | `/futures/data/topLongShortAccountRatio` | 5m–1d | (symbol, period, timestamp) | Per period |
| Top Trader L/S (Positions) | `/futures/data/topLongShortPositionRatio` | 5m–1d | (symbol, period, timestamp) | Per period |

---

## Step 1: Planning (Per Data Type)

### 1.1 Basis

- **API:** `GET {fapi_base}/futures/data/basis`
- **Params:** `pair` (e.g. BTCUSDT), `contractType=PERPETUAL`, `period` (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d), `limit` (default 30, max 500), optional `startTime`, `endTime`
- **Response:** `timestamp`, `symbol` (pair), `basis`, `basisRate`, `futuresPrice`, `indexPrice`, etc.
- **Retention:** 30 days
- **Schema:** `basis(symbol, period, timestamp, basis_rate, basis, futures_price, index_price)` — store only needed fields; PK `(symbol, period, timestamp)`
- **Strategy:** Time-based pagination; tail refresh last 1–2 periods; 429 retry; empty response handling

### 1.2 Global Long/Short Ratio (Accounts)

- **API:** `GET {fapi_base}/futures/data/globalLongShortAccountRatio`
- **Params:** `symbol`, `period` (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d), `limit` (max 500), optional `startTime`, `endTime`
- **Response:** `timestamp`, `symbol`, `longShortRatio`, `longAccount`, `shortAccount`
- **Retention:** 30 days
- **Schema:** `global_long_short_account(symbol, period, timestamp, long_short_ratio, long_account, short_account)`; PK `(symbol, period, timestamp)`
- **Strategy:** Same as Basis

### 1.3 Top Trader Long/Short Ratio (Accounts)

- **API:** `GET {fapi_base}/futures/data/topLongShortAccountRatio`
- **Params:** `symbol`, `period`, `limit`, optional `startTime`, `endTime`
- **Response:** `timestamp`, `symbol`, `longShortRatio`, `longAccount`, `shortAccount` (top 20% traders by margin)
- **Schema:** `top_long_short_account(symbol, period, timestamp, long_short_ratio, long_account, short_account)`; PK `(symbol, period, timestamp)`
- **Strategy:** Same as Basis

### 1.4 Top Trader Long/Short Ratio (Positions)

- **API:** `GET {fapi_base}/futures/data/topLongShortPositionRatio`
- **Params:** `symbol`, `period`, `limit`, optional `startTime`, `endTime`
- **Response:** `timestamp`, `symbol`, `longShortRatio`, `longPosition`, `shortPosition` (top 20% by margin)
- **Schema:** `top_long_short_position(symbol, period, timestamp, long_short_ratio, long_position, short_position)`; PK `(symbol, period, timestamp)`
- **Strategy:** Same as Basis

---

## Step 2: Database Migration

- **File:** `alembic/versions/003_add_futures_market_data.py`
- **Revises:** `002`
- **Tables to create:**
  1. `basis` — symbol, period, timestamp, basis_rate, basis, futures_price, index_price (or minimal set)
  2. `global_long_short_account` — symbol, period, timestamp, long_short_ratio, long_account, short_account
  3. `top_long_short_account` — symbol, period, timestamp, long_short_ratio, long_account, short_account
  4. `top_long_short_position` — symbol, period, timestamp, long_short_ratio, long_position, short_position
- **Indexes:** `(symbol, period)` for each table for read queries.
- **Run:** `alembic upgrade head`

---

## Step 3: Collector Methods (`data/collector.py`)

Add four methods; base URL: `self._fapi_base + "/futures/data/"`.

| Method | URL path | Returns (tuple) |
|--------|----------|------------------|
| `fetch_basis` | `basis` | (timestamp, basis_rate, basis, futures_price, index_price) — match chosen schema |
| `fetch_global_long_short_account` | `globalLongShortAccountRatio` | (timestamp, long_short_ratio, long_account, short_account) |
| `fetch_top_long_short_account` | `topLongShortAccountRatio` | (timestamp, long_short_ratio, long_account, short_account) |
| `fetch_top_long_short_position` | `topLongShortPositionRatio` | (timestamp, long_short_ratio, long_position, short_position) |

- **Basis:** use `pair` + `contractType=PERPETUAL`; map `symbol` in code if API returns pair.
- **Common:** `symbol` (or pair for basis), `period`, `start_time`, `end_time`, `limit`; parse JSON; return list of tuples; handle empty/invalid response and 429 (raise or retry in task layer).
- Reuse patterns from `fetch_open_interest_hist` and `fetch_funding_rate`.

---

## Step 4: Storage Methods (`data/storage.py`)

For each of the four data types:

- **Write:** `write_basis(symbol, period, rows)`, `write_global_long_short_account(...)`, etc. Use `ON CONFLICT (symbol, period, timestamp) DO UPDATE SET ...` (or equivalent) for upsert.
- **Read:** `read_basis(symbol, period, start_time, end_time)` → list of tuples; same for the other four.
- **Latest:** `get_latest_basis_time(symbol, period)`, `get_latest_global_long_short_account_time(symbol, period)`, etc. Return max timestamp or None.

Define SQL constants and use parameterized queries; follow existing `write_open_interest` / `read_open_interest` style.

---

## Step 5: Update Tasks (`data/updates/`)

Create four task modules:

- `binance_basis.py`
- `binance_global_long_short_account.py`
- `binance_top_long_short_account.py`
- `binance_top_long_short_position.py`

Each task:

- Uses Collector + Storage; respects `settings.symbols` and chosen `period` (e.g. `5m` for consistency with open interest).
- Gets latest timestamp per (symbol, period); if none, skip (no backfill from task).
- Requests last N periods (tail refresh, e.g. 2–3) and new data after latest; writes via Storage.
- Implements 429 retry (e.g. Retry-After) and short delay between symbols.
- Logs success/failure per symbol.

---

## Step 6: Register Tasks (`data/updates/__init__.py`)

- Import the four new task modules.
- Append to `TASKS`:  
  `("binance_basis", binance_basis.run)`,  
  `("binance_global_long_short_account", ...)`,  
  `("binance_top_long_short_account", ...)`,  
  `("binance_top_long_short_position", ...)`.

---

## Step 7: Test Scripts (First 10 Symbols)

Create under `scripts/backfill/`:

- `test_backfill_basis.py`
- `test_backfill_global_long_short_account.py`
- `test_backfill_top_long_short_account.py`
- `test_backfill_top_long_short_position.py`

Each script:

- Runs for `settings.symbols[:10]`.
- Uses a short range (e.g. 7 days) and one period (e.g. `5m`).
- Implements time-based pagination (oldest-first or newest-first per API behavior), retries for 429 and empty response, delay between requests.
- Uses `tqdm` for progress (e.g. per symbol).
- Calls Collector then Storage; logs row counts and errors.

---

## Step 8: Backfill Scripts (All Symbols)

Create under `scripts/backfill/`:

- `backfill_basis.py`
- `backfill_global_long_short_account.py`
- `backfill_top_long_short_account.py`
- `backfill_top_long_short_position.py`

Each script:

- Runs for all `settings.symbols`.
- Backfills full 30 days (or less if API limits).
- Same pagination and retry logic as test script; no tqdm required but logging per symbol recommended.
- Writes only rows within the chosen time range.

---

## Step 9: Test Run and Data Verification (SOP 9.4–9.5)

- **Run test scripts:**  
  `python scripts/backfill/test_backfill_basis.py` (and the other three).
- **Verify:** DB row counts, time range, no duplicate (symbol, period, timestamp); spot-check values vs API.
- **Integrity check scripts:** Add under `scripts/integrity/`:
  - `check_missing_basis.py`
  - `check_missing_global_long_short_account.py`
  - `check_missing_top_long_short_account.py`
  - `check_missing_top_long_short_position.py`
- Each integrity script: generate expected timestamps for last 30 days (or 7 for quick check) from period; compare with stored data; output missing count, coverage %, and gaps; write report to `reports/integrity/` (e.g. JSON).

---

## Step 10: Script Testing (SOP 9.6)

- **Collector:** Quick test per method (e.g. one symbol, one period, limit 10); assert non-empty and tuple shape.
- **Storage:** Write a few rows, read back, `get_latest_*_time`; assert consistency.
- **Update task:** Run each task once; check logs and DB for new/updated rows.

---

## Step 11: Full Backfill (All Symbols)

- Run all four backfill scripts.
- Monitor logs and rate limits.
- Run all five integrity checks and fix any gaps (e.g. re-run backfill for affected symbols).

---

## Step 12: Update Service

- Rebuild: `docker compose build data-updater`
- Restart: `docker compose up -d --force-recreate data-updater`
- Verify: `docker compose ps` and logs; confirm all four tasks run on schedule and write data.

---

## Step 13: Visualization (Optional)

Add Streamlit pages under `viz/pages/` (e.g. `10_basis.py`, `11_global_long_short_account.py`, …; four pages). Each page:

- Symbol and period selector; time range (e.g. last 7–30 days).
- Load via corresponding `storage.read_*`.
- Show summary stats and Plotly chart(s); optional raw table.
- Handle empty data; follow pattern of `8_open_interest.py` / `9_funding_rate.py`.
- Register in `viz/app.py` sidebar.

---

## Step 14: Documentation

- **ARCHITECTURE.md:** Add the four tables and tasks to Database and Data Flow sections; mention 30-day retention.
- **data/updates/README.md:** List the four new tasks.
- **reports/README.md:** Document the four new integrity report types if added.

---

## Checklist (SOP-Aligned)

- [ ] **Planning** — API, schema, and strategy defined for all four (above).
- [ ] **Database** — Migration 003 created and applied; migration 004 drops taker_buy_sell_vol; indexes in place.
- [ ] **Collector** — Four fetch methods implemented and tested.
- [ ] **Storage** — Four write/read/get_latest methods implemented and tested.
- [ ] **Update tasks** — Four task files created and registered.
- [ ] **Test scripts** — Four test backfill scripts (first 10 symbols, 7 days).
- [ ] **Backfill scripts** — Four full backfill scripts (all symbols, 30 days).
- [ ] **Test run** — All test scripts run; DB and integrity checks pass.
- [ ] **Integrity scripts** — Four check_missing_* scripts; reports produced.
- [ ] **Script testing** — Collector, storage, and task tests done.
- [ ] **Full backfill** — All four backfills run; integrity reports reviewed.
- [ ] **Service** — Data-updater rebuilt and restarted; tasks running.
- [ ] **Viz** — Optional: four Streamlit pages added and tested.
- [ ] **Docs** — ARCHITECTURE, data/updates/README, reports/README updated.

---

## File Summary

| Category | Files to create/update |
|----------|-------------------------|
| Migration | `alembic/versions/003_add_futures_market_data.py`, `004_drop_taker_buy_sell_vol.py` |
| Collector | `data/collector.py` (add 4 methods) |
| Storage | `data/storage.py` (add 4×3 methods + SQL) |
| Tasks | `data/updates/binance_basis.py`, `binance_global_long_short_account.py`, `binance_top_long_short_account.py`, `binance_top_long_short_position.py` |
| Registry | `data/updates/__init__.py` |
| Test backfill | `scripts/backfill/test_backfill_basis.py` (+ 3) |
| Backfill | `scripts/backfill/backfill_basis.py` (+ 3) |
| Integrity | `scripts/integrity/check_missing_basis.py` (+ 3) |
| Viz | `viz/pages/10_basis.py` (+ 3 optional), `viz/app.py` |
| Docs | `docs/ARCHITECTURE.md`, `data/updates/README.md`, `reports/README.md` |

This plan is ready to implement step-by-step following the SOP.
