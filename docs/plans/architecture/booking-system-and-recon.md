# Booking System & Reconciliations Plan

This document captures the planned design for the booking system, tables, workflow, and reconciliations. Status: **WIP**.

## Table of Contents

1. [Overview](#overview)
2. [Tables](#tables)
3. [Booking Workflow](#booking-workflow)
4. [Manual override / adjustments](#manual-override--adjustments)
5. [Services & operations workflow](#services--operations-workflow)
6. [Reconciliations](#reconciliations)
7. [Related Docs](#related-docs)

---

## Overview

- **Execution** = exchange I/O only (place/cancel/query orders and fills). No persistence.
- **Booking** = internal source of truth: orders, trades, positions, balances. Persisted in DB.
- **Orchestration** = submits via execution, then books outcomes; syncs fills into the ledger.
- **Position** = materialized table (Option 2), updated on every trade; can be rebuilt from trades.

---

## Tables

### 1. Orders

- One row per submitted order.
- **Key fields:** venue, exchange_order_id, symbol, side, order_type, quantity, price, **status** (NEW / PARTIALLY_FILLED / FILLED / CANCELED), created_at, updated_at.
- Idempotency: key by (venue, exchange_order_id) to avoid double-booking on retries.

### 2. Trades

- One row per fill (exchange trade).
- **Key fields:** venue, exchange_trade_id, order_id (FK to orders), symbol, side, quantity, price, commission, traded_at.
- Idempotency: unique on (venue, exchange_trade_id).
- Recording a trade updates the **positions** table (and **balances** table).

### 3. Positions (materialized)

- One row per (venue,) symbol with current quantity and avg_price.
- Updated on every trade (running total / VWAP).
- Can be rebuilt from trades if needed. Recon: position vs trades (derived) and position vs Binance.

### 4. Balances

- **Purpose:** Wallet balance per asset (spot) for booking and for reconciliation with the exchange.
- **Table: `balances`**

| Column     | Type    | Description                          |
|------------|---------|--------------------------------------|
| venue      | TEXT    | e.g. `binance_spot`                  |
| asset      | TEXT    | e.g. `USDT`, `BTC`, `ETH`           |
| free       | REAL    | Available balance                    |
| locked     | REAL    | Locked (in orders, etc.); default 0 |
| updated_at | INTEGER | Last update time (e.g. ms)          |

- **Primary key:** (venue, asset).
- **Maintained by:** On every booked trade, update base asset, quote asset, and commission asset rows (free ± quantity or quote amount or commission).
- **Recon:** Balances vs Binance balances — one rec per asset (free, locked).

### 5. Adjustments (manual overrides)

- **Purpose:** Audit trail for manual overrides (balance/position/order status corrections) that the normal flow (fill sync, rebuild) doesn’t handle.
- **Table: `adjustments`** (or equivalent): one row per override; columns include venue, type (balance | position | order_status), asset_or_symbol, delta_or_value, reason, created_at, created_by. See [Manual override / adjustments](#manual-override--adjustments).
- **Role:** The adjustments table **only records** that an override was made (who, when, why, what). It does **not** feed into other tables for reads. The **actual** state after an override lives in `positions`, `balances`, or `orders` — we update those tables directly and insert an audit row into `adjustments`. So: one table for audit; real changes are direct updates to the other tables.

### 6. Margin (future)

- When adding futures: separate table for margin/account state (wallet balance, available balance, initial margin, maintenance margin, margin level, etc.). One row per venue (or snapshot per time). Not part of current spot booking.

---

## Booking Workflow

### Order placement

1. Strategy/orchestrator decides: place order (symbol, side, quantity, type, etc.).
2. Call execution: `OrderManager.submit_market(...)` or `submit_limit(...)`.
3. On exchange error: do not book; log and stop.
4. On success: idempotency check (venue, exchange_order_id); then `Ledger.record_order(..., status=NEW or FILLED if market filled immediately)`.
5. Return/store ledger_order_id for fill matching.

### Fill / trade booking

1. Obtain fills (poll `get_fills` / `get_my_trades` or WebSocket).
2. For each fill: idempotency check (venue, exchange_trade_id). If already booked, skip.
3. Resolve ledger order id from exchange_order_id.
4. `Ledger.record_trade(...)` — ledger updates positions (and balances).
5. Optionally update order status to FILLED / PARTIALLY_FILLED in ledger.

### Cancel order

1. Resolve exchange_order_id (from ledger if needed).
2. `OrderManager.cancel(symbol, order_id)`.
3. On success: update ledger order status to CANCELED (requires Ledger method for order status update).

### Fill sync

- After placing an order: short delay then fetch fills for that orderId and book.
- Periodically: fetch recent trades for active symbols and book any new exchange_trade_ids.
- Before critical actions: quick sync so ledger is up to date.

---

## Manual override / adjustments

You **do** need a defined manual override path for cases the normal flow (fill sync, rebuild from trades) cannot handle. Without it, you have no auditable way to correct exchange errors, manual trades on the exchange, deposits/withdrawals, or “accept exchange as truth” when ledger is wrong.

### When to use

- **Exchange error or disputed fill** — exchange shows a fill we don’t want to book as-is, or we must align to a corrected value.
- **Manual trade on exchange** — trade was placed outside the system (e.g. on the website); we need to reflect it in the ledger.
- **Deposit / withdrawal** — balance change not from a booked trade; we need to adjust balance (and optionally position) with a reason.
- **Accept exchange as truth** — after investigation, we decide ledger is wrong and we set position/balance/order status to match the exchange, with a documented reason.
- **One-off correction** — bug in booking, missed sync window, or migration; we need a single auditable correction.

### What to provide (audit)

Every manual override must record: **who** (operator or system id), **when** (timestamp), **why** (reason code or free text), and **what** (affected entity and change). No silent edits.

### How adjustments relate to other tables

- **Adjustments table = audit only.** It does **not** “flow into” other tables for reads. There is no derivation like “position = SUM(trades) + SUM(adjustments)” for normal reads.
- **Real changes = direct updates.** When you apply a manual override, you (1) **update the target table** (`positions`, `balances`, or `orders.status`) and (2) **insert a row** into `adjustments` (who, when, why, what). So the live state is always in `positions`, `balances`, and `orders`; `adjustments` only records that an override happened.
- **Rebuild from trades:** When you “rebuild positions/balances from trades” (e.g. after a bug), you recompute from `trades` only and overwrite `positions`/`balances`. Adjustments are **not** replayed in that rebuild — any prior manual overrides would be lost unless you also replay adjustments or re-apply them. So use rebuild for “get back in sync from trades”; use adjustments when you’ve deliberately overridden and want that state to stay.

### Minimal design

1. **Adjustments table (recommended)**  
   - One row per manual adjustment. Example columns: `id`, `venue`, `type` (e.g. `balance`, `position`, `order_status`), `asset_or_symbol`, `delta_or_value`, `reason`, `created_at`, `created_by`.  
   - When applying an adjustment: **directly update** `positions` or `balances` (or `orders.status`) and **insert** the adjustment row. No other table reads from `adjustments` for current state.

2. **Order status override**  
   - UPDATE `orders.status` (and `updated_at`); optionally INSERT into `adjustments` for audit. E.g. `Ledger.update_order_status(ledger_order_id, status, reason=None)` that does both.

3. **Balance / position override**  
   - UPDATE `balances` or `positions`; INSERT into `adjustments`. E.g. `Ledger.record_adjustment(venue, type, asset_or_symbol, delta_or_value, reason, created_by)` that performs the update(s) and inserts the audit row. Single entry point so every override is recorded.

4. **No direct edit of trades**  
   - Do not update or delete existing trade rows for overrides. Use direct updates to positions/balances (and the adjustments audit row) or, in rare cases, insert a synthetic “correction trade” with a clear marker and reason. That keeps trade history immutable and audit-friendly.

### Summary

- **Yes, manual override mechanisms are needed** for edge cases and one-off corrections.  
- Provide a **controlled, auditable path**: adjustments table + optional `update_order_status` with reason, and a single way to apply balance/position overrides that always writes an adjustment row.  
- Use **adjustments** (or synthetic correction entries) rather than editing trades in place.

---

## Services & operations workflow

### Design choice: no separate balance-monitoring service

- **Ledger balances and positions are updated only from transactions (booked trades).** There is no separate service that continuously polls Binance to “refresh” balances or positions in the ledger.
- **Reconciliations** compare the ledger (orders, trades, positions, balances) to the exchange **on a schedule** (e.g. daily). They do not drive ledger updates; they only detect drift and produce reports/alerts.

So: **update from transactions → run recs on a schedule (e.g. daily).** No need for a data service that constantly monitors balances for ledger updates.

### Services / jobs

| Component | What it does | How it runs |
|-----------|-----------------------------|----------------------------------------|
| **Order placement** | Strategy/orchestrator places orders via execution and books each order in the ledger. | On demand (when strategy decides to trade). |
| **Fill sync** | Fetches recent trades from the exchange (e.g. `get_my_trades`), books any new fills into the ledger (idempotent by `exchange_trade_id`). Updates positions and balances via `record_trade`. | **After each order** (short delay) + **scheduled job** (e.g. every 1–5 minutes) for active symbols, or a single loop in a small “booking worker” that runs continuously. |
| **Reconciliations** | Runs all 6 recs (order vs trades; trades vs Binance; position vs trades; position vs Binance; orders vs Binance; balances vs Binance). Produces a report and alerts on drift. | **Scheduled** (e.g. daily, or after market close). No need for real-time recs. |

### Recommended ops flow

1. **Ongoing**
   - Orders are placed by the strategy; each order is booked when placed.
   - **Fill sync** runs periodically (e.g. every 1–5 min) so new fills are booked soon after they occur. Optionally also run fill sync immediately after each order. Ledger positions and balances stay in sync with booked trades only (no separate balance poll for ledger updates).
2. **Daily (or configurable)**
   - Run the **reconciliation job** (all 6 recs).
   - Review report; investigate and fix any drift (e.g. missed fill, manual trade on exchange, bug).
   - Optionally: run recs twice daily or before/after large rebalances.

### Summary

- **Do not** add a service that constantly polls Binance balances to update the ledger. Balances (and positions) are updated only when trades are booked in the fill-sync path.
- **Do** run a **fill-sync** task periodically (and/or after each order) so fills are booked promptly.
- **Do** run **reconciliations on a schedule** (e.g. daily); use the report to catch and fix drift.

---

## Reconciliations

| # | Recon                        | Scope              | Recs                    |
|---|------------------------------|--------------------|-------------------------|
| 1 | Order vs trades (ledger)     | Per order          | 1 per order             |
| 2 | Trades vs Binance trades     | Per trade          | 1 per trade in window   |
| 3 | Position vs trades (ledger)  | Per symbol         | 1 per (venue+) symbol   |
| 4 | Position vs Binance positions| Per symbol         | 1 per symbol            |
| 5 | Orders vs Binance orders     | Per order          | 1 per order in scope    |
| 6 | Balances vs Binance balances | Per asset          | 1 per asset             |
| 7 | Open orders (ledger vs exchange) | Optional      | **Hold** — skip for now |

### What each recon checks

- **1. Order vs trades:** For each order, `SUM(trades.quantity WHERE order_id=...)` vs order quantity; order status consistent with fills.
- **2. Trades vs Binance:** Match by (venue, exchange_trade_id); compare symbol, side, quantity, price, time.
- **3. Position vs trades:** For each symbol, `positions.quantity` (and avg_price) vs derived from trades (SUM of signed quantity, VWAP).
- **4. Position vs Binance:** Ledger positions vs exchange account/positions (e.g. spot balances or futures positions).
- **5. Orders vs Binance:** Ledger orders (open + recent) vs exchange order state; match by exchange_order_id; compare status, quantity, filled qty.
- **6. Balances vs Binance:** Per asset: ledger balances (free, locked) vs Binance `get_account()` balances.

### When recs break (runbook)

1. **Identify** which rec(s) failed and what the mismatch is (from the recon report: ledger value vs exchange value, missing rows, etc.).
2. **Root cause** (common cases):
   - **Rec 1 (order vs trades):** Order status says FILLED but sum of fills &lt; order qty, or vice versa → usually a missed fill or wrong status.
   - **Rec 2 (trades vs Binance):** Exchange has a trade we don’t have → missed fill. We have a trade exchange doesn’t → wrong exchange_trade_id or wrong venue/symbol.
   - **Rec 3 (position vs trades):** Position table doesn’t match SUM(trades) → position table drift (bug or partial update). Fix by **rebuilding positions from trades** (script: delete positions, recompute from trades and insert).
   - **Rec 4 (position vs Binance):** Ledger position ≠ exchange → often same as Rec 2 (missing/extra trades in ledger) or Rec 6 (balance). Fix trades/balances first.
   - **Rec 5 (orders vs Binance):** We have an order exchange doesn’t, or status differs → update ledger order status from exchange; if we missed an order, add it (or treat as manual trade and book as needed).
   - **Rec 6 (balances vs Binance):** Ledger balance ≠ exchange → usually missing trades in ledger (fix Rec 2) or balance update bug. After fixing trades, **rebuild balances from trades** (script) or re-run fill sync for affected assets; if still off, one-off adjustment entry (document reason).
3. **Fix without a GUI:**
   - **Missed fill:** Run **fill sync** again for the symbol/period (idempotent). If fill sync doesn’t pick it up (e.g. old), add the trade via script calling `Ledger.record_trade(...)` with exchange_trade_id, order_id, qty, price, time from the exchange. Then re-run recs.
   - **Position drift (Rec 3):** Run a **rebuild script**: derive positions from trades (SUM signed quantity, VWAP per symbol), replace contents of `positions` table (or update rows). Re-run recs.
   - **Balance drift (Rec 6):** Ensure all trades are booked (Rec 2 clean); then **rebuild balances from trades** (script that replays trades into free/locked per asset) or add a one-off **adjustment** (e.g. extra row or adjustment table) with a documented reason. Re-run recs.
   - **Order status wrong:** Update `orders.status` (and `updated_at`) via SQL or a small `Ledger.update_order_status(ledger_order_id, status)`; use exchange as source of truth. Re-run recs.
4. **Don’t** edit trade rows in place for audit; if you must “correct”, add an **adjustment/correction entry** (separate row or table) and document. Prefer fixing by booking missing trades or rebuilding derived tables (positions, balances) from trades.

---

## Related Docs

- [Architecture Overview](../ARCHITECTURE.md) — system architecture; execution/booking marked WIP.
- [Booking & Reconciliation Operations](../operations/booking-and-recon.md) — ops summary and job schedule.
- [Multi-Factor Long/Short Strategy](multi-factor-long-short-strategy.md) — strategy layer that will consume positions and drive orders.
