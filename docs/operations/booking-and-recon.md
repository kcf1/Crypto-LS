# Booking & Reconciliation Operations

Operations guide for the booking system and reconciliations. Design and workflow are defined in the [Booking System & Reconciliations Architecture](../plans/architecture/booking-system-and-recon.md). Status: **WIP**.

## Summary

- **Ledger** (orders, trades, positions, balances) is updated only from **booked trades**. No separate service polls the exchange to refresh balances or positions into the ledger.
- **Fill sync** runs periodically (and/or after each order) to fetch new fills from the exchange and book them; that path updates positions and balances.
- **Reconciliations** run on a schedule (e.g. daily) and compare the ledger to the exchange; they produce reports and alerts and do not update the ledger.

## Services / jobs (when implemented)

| Job | Purpose | Suggested schedule |
|-----|---------|--------------------|
| Fill sync | Fetch recent trades from exchange, book new fills (idempotent). Updates positions and balances. | Every 1–5 min (or after each order); or a small worker loop. |
| Reconciliations | Run all 6 recs (order vs trades; trades vs Binance; position vs trades; position vs Binance; orders vs Binance; balances vs Binance). Report drift. | Daily (e.g. after market close), or twice daily / before rebalance. |

## Operations workflow

1. **Ongoing:** Strategy places orders → orders booked on place; fill-sync job runs periodically → new fills booked → positions and balances stay current.
2. **Daily:** Run reconciliation job → review report → investigate and fix any drift.

## When recs break (runbook)

No GUI required. Use scripts, CLI, and (when needed) controlled SQL.

### Step 1: Identify

- From the recon report: which rec(s) failed (1–6) and what is the mismatch (ledger value vs exchange value, missing rows, extra rows).

### Step 2: Root cause (by rec)

| Rec | Typical cause | Fix direction |
|-----|----------------|----------------|
| 1 Order vs trades | Missed fill, wrong order status | Book missing fill or update order status from exchange. |
| 2 Trades vs Binance | We’re missing a fill (exchange has it) | Run fill sync; if still missing, add trade via script (`Ledger.record_trade` with exchange data). |
| 3 Position vs trades | Position table out of sync with trades | Rebuild positions from trades (script). |
| 4 Position vs Binance | Same as 2 or 6 (missing trades or wrong balances) | Fix trades/balances first, then re-run recs. |
| 5 Orders vs Binance | Order status or we missed an order | Update ledger order status from exchange; or add missing order. |
| 6 Balances vs Binance | Missing trades or balance update bug | Fix trades; rebuild balances from trades or add documented adjustment. |

### Step 3: Fix (no GUI)

- **Missed fill:** Re-run fill sync for the symbol/period. If the fill is old and not in range, add it via a script that calls `Ledger.record_trade(...)` with data from the exchange (exchange_trade_id, order_id, symbol, side, quantity, price, traded_at, commission). Re-run recs.
- **Position drift (Rec 3):** Run a rebuild script: compute position per symbol from trades (SUM of signed quantity, VWAP), then replace/update the `positions` table. Re-run recs.
- **Balance drift (Rec 6):** After ensuring all trades are in the ledger (Rec 2 clean), rebuild balances from trades (script that replays trades into free/locked per asset). If exchange has a balance we can’t explain (e.g. deposit/withdraw), add a one-off adjustment with a documented reason. Re-run recs.
- **Order status:** Update `orders.status` (and `updated_at`) from exchange (SQL or `Ledger.update_order_status`). Re-run recs.

### Step 4: Re-run recs

- After each fix, run the reconciliation job again and confirm the affected rec(s) pass.

### Rules

- **Do not** edit existing trade rows in place; use **adjustment/correction entries** (separate row or table) if you must correct, and document the reason.
- Prefer: book missing trades, rebuild positions/balances from trades, and align order status to the exchange.
- For edge cases (deposit/withdraw, manual trade on exchange, accept exchange as truth): use the **manual override / adjustments** path — see [Booking System & Reconciliations Architecture](../plans/architecture/booking-system-and-recon.md#manual-override--adjustments). Every override must record who, when, why, and what.

## Related

- [Booking System & Reconciliations Architecture](../plans/architecture/booking-system-and-recon.md) — full design, tables, workflow, rec list.
- [Architecture](../ARCHITECTURE.md) — execution/booking modules (WIP).
