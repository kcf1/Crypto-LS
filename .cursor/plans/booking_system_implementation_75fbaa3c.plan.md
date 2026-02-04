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

## Implementation Tasks

### Phase 1: Database Schema

**1.1 Alembic migration for balances and adjustments**

- Create `alembic/versions/006_add_balances_and_adjustments.py`
- Add `balances` table: `venue` (String), `asset` (String), `free` (Float), `locked` (Float, default 0), `updated_at` (BigInteger). Primary key: `(venue, asset)`. Index on `venue`.
- Add `adjustments` table: `id` (Integer, PK), `venue` (String), `type` (String: balance|position|order_status), `asset_or_symbol` (String), `delta_or_value` (Float), `reason` (String), `created_at` (BigInteger), `created_by` (String, optional). Index on `(venue, type, created_at)`.
- Update SQLite schema in `booking/ledger.py` `BOOKING_SCHEMA` to match (for dev/test).

### Phase 2: Ledger Enhancements

**2.1 Idempotency checks**

- `record_order`: Check if `(venue, exchange_order_id)` already exists before insert. If exists, return existing `id` (or raise/log). Use `SELECT ... WHERE venue=:venue AND exchange_order_id=:exchange_order_id`.
- `record_trade`: Check if `(venue, exchange_trade_id)` already exists. If exists, return existing `id` (skip insert). Use `SELECT ... WHERE venue=:venue AND exchange_trade_id=:exchange_trade_id`.

**2.2 Balance updates in `record_trade`**

- After inserting trade, update balances for base asset, quote asset, and commission asset.
- Extract base/quote from `symbol` (e.g. BTCUSDT → BTC, USDT). Handle commission asset (from trade or default to quote).
- For base asset: BUY → `free += quantity`, SELL → `free -= quantity`.
- For quote asset: BUY → `free -= quantity * price`, SELL → `free += quantity * price`.
- For commission asset: `free -= commission`.
- Use `ON CONFLICT (venue, asset) UPDATE` for PostgreSQL, or `INSERT ... ON CONFLICT` for SQLite. Update `updated_at` to `traded_at`.

**2.3 Order status updates**

- Add `update_order_status(ledger_order_id: int, status: str, reason: Optional[str] = None) -> None`: UPDATE `orders.status` and `updated_at`; optionally INSERT into `adjustments` if `reason` provided.
- Add helper `get_order_by_exchange_id(venue: str, exchange_order_id: str) -> Optional[Dict]` to resolve ledger order id from exchange order id.

**2.4 Adjustments**

- Add `record_adjustment(venue: str, type: str, asset_or_symbol: str, delta_or_value: float, reason: str, created_by: Optional[str] = None) -> int`: INSERT into `adjustments`; then UPDATE `balances` or `positions` or `orders.status` based on `type`. Return adjustment id.
- For `type='balance'`: UPDATE `balances` SET `free = :delta_or_value` (or `free += :delta_or_value` if delta). For `type='position'`: UPDATE `positions` SET `quantity = :delta_or_value` (or similar). For `type='order_status'`: UPDATE `orders.status` WHERE id matches (if `asset_or_symbol` is order id).

**2.5 Query methods**

- Add `get_balances(venue: Optional[str] = None, asset: Optional[str] = None) -> List[Dict]`: SELECT from `balances` with optional filters.
- Add `get_adjustments(venue: Optional[str] = None, type: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]`: SELECT from `adjustments` with optional filters, ORDER BY `created_at DESC`.

### Phase 3: Orchestrator Layer

**3.1 Create `execution/orchestrator.py`**

- Class `BookingOrchestrator` that takes `OrderManager` and `Ledger`.
- Method `place_order(symbol, side, quantity, order_type, price=None, ...) -> Dict`: Call `OrderManager.submit_*`; on success, extract `exchange_order_id`, `status`, `time`; idempotency check + `Ledger.record_order(...)`; return dict with `ledger_order_id`, `exchange_order_id`, `status`. On exchange error, log and raise (don't book).
- Method `cancel_order(ledger_order_id: Optional[int] = None, exchange_order_id: Optional[str] = None, symbol: str, ...) -> Dict`: Resolve `exchange_order_id` if needed; call `OrderManager.cancel`; on success, `Ledger.update_order_status(..., "CANCELED")`; return result.
- Method `sync_fills_for_order(symbol: str, exchange_order_id: str, ledger_order_id: int) -> List[int]`: Call `OrderManager.get_fills(symbol, orderId=exchange_order_id)` (or `get_my_trades` and filter); for each fill, idempotency check + `Ledger.record_trade(...)` with `order_id=ledger_order_id`; return list of ledger trade ids.
- Method `sync_fills_for_symbol(symbol: str, since: Optional[int] = None, limit: int = 100) -> List[int]`: Call `OrderManager.get_my_trades(symbol, limit=limit, startTime=since)`; for each trade, idempotency check + resolve `ledger_order_id` from `exchange_order_id` (or None if not found); `Ledger.record_trade(...)`; return list of ledger trade ids.

### Phase 4: Fill Sync Service

**4.1 Create `scripts/services/run_fill_sync.py`**

- Script that runs fill sync periodically (e.g. every 1-5 minutes).
- Use `BookingOrchestrator`; for each symbol in `settings.symbols` (or active symbols from ledger), call `sync_fills_for_symbol(symbol, since=last_sync_time)`.
- Track last sync time per symbol (e.g. in-memory or small state file).
- Handle errors gracefully (log, continue to next symbol).
- Optionally: also sync fills immediately after placing an order (can be called from orchestrator or separate helper).

**4.2 Integration with existing services**

- Consider adding fill sync as a separate Docker service (similar to `data-updater`) or as part of a "booking worker" that also handles order placement. For now, keep as standalone script that can be run via cron or systemd.

### Phase 5: Rebuild Utilities

**5.1 Create `scripts/utils/rebuild_positions.py`**

- Script that rebuilds `positions` table from `trades`: DELETE all positions; GROUP BY symbol, compute `quantity = SUM(quantity * CASE side WHEN 'BUY' THEN 1 ELSE -1 END)`, `avg_price = SUM(price * quantity) / SUM(quantity)` (VWAP); INSERT into `positions`. Handle zero positions (delete or skip).

**5.2 Create `scripts/utils/rebuild_balances.py`**

- Script that rebuilds `balances` table from `trades`: DELETE all balances; for each trade, extract base/quote assets from symbol; replay trades into `free` per asset (base: BUY +, SELL -; quote: BUY -, SELL +; commission: -). Handle commission asset (from trade or default). INSERT/UPDATE balances per `(venue, asset)`. Set `updated_at` to latest `traded_at` per asset.

### Phase 6: Reconciliation Scripts

**6.1 Create `scripts/integrity/check_booking_recon.py`**

- Script that runs all 6 reconciliations:
- **Rec 1 (order vs trades)**: For each order, `SUM(trades.quantity WHERE order_id=...)` vs `orders.quantity`; check `orders.status` consistent with fills. Report mismatches.
- **Rec 2 (trades vs Binance)**: Fetch `get_my_trades` for symbols with recent trades; match by `(venue, exchange_trade_id)`; compare symbol, side, quantity, price, time. Report missing/extra trades.
- **Rec 3 (position vs trades)**: For each symbol, `positions.quantity` vs derived from trades (SUM signed quantity, VWAP). Report mismatches.
- **Rec 4 (position vs Binance)**: Fetch `get_account()` or positions from Binance; compare to ledger positions. Report mismatches.
- **Rec 5 (orders vs Binance)**: Fetch open orders + recent order history; match by `exchange_order_id`; compare status, quantity, filled qty. Report mismatches.
- **Rec 6 (balances vs Binance)**: Fetch `get_account()` balances; compare `free`, `locked` per asset to ledger balances. Report mismatches.
- Output: JSON report (similar to existing integrity checks) with per-rec results, mismatches, and summary. Save to `reports/integrity/booking_recon_<timestamp>.json` and text summary.

**6.2 Add to `scripts/integrity/run_integrity_checks.py`**

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

## Notes

- Idempotency is critical: always check `(venue, exchange_order_id)` and `(venue, exchange_trade_id)` before inserts.
- Balance updates must handle base/quote extraction from symbol (e.g. BTCUSDT → BTC, USDT). Consider edge cases (non-USDT pairs, commission in different asset).
- Adjustments table is audit-only; real state is in `positions`, `balances`, `orders`. When applying adjustment, update target table + insert audit row.
- Fill sync can be run after each order (short delay) + periodically. Consider rate limits (Binance allows many `get_my_trades` calls).
- Reconciliations are read-only (compare, report); they don't update the ledger. Fixes are manual (fill sync, rebuild, adjustments) or via orchestrator.