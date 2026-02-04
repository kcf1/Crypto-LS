# Booking System & Reconciliations Plan

This document captures the planned design for the booking system, tables, workflow, and reconciliations. Status: **WIP**.

## Table of Contents

1. [Overview](#overview)
2. [Tables](#tables)
3. [Booking Workflow](#booking-workflow)
4. [Reconciliations](#reconciliations)
5. [Related Docs](#related-docs)

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

### 5. Margin (future)

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

---

## Related Docs

- [Architecture Overview](../ARCHITECTURE.md) — system architecture; execution/booking marked WIP.
- [Multi-Factor Long/Short Strategy](multi-factor-long-short-strategy.md) — strategy layer that will consume positions and drive orders.
