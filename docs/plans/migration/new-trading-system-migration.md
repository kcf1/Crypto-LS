# Migration Plan: Current System → Solo Runner Trading System Architecture

**Target:** [NEW-TRADING-SYSTEM-ARCHITECTURE.md](../architecture/NEW-TRADING-SYSTEM-ARCHITECTURE.md)  
**Status:** Draft  
**Date:** Feb 2026

## 1. Overview

This plan describes how to migrate from the current order-execution and booking setup to the full **Solo Runner Trading System** architecture: 10 services, 8 Redis streams, clear separation of Market Data → Decision → Risk → Order Gateway → Fill Sync → OMS → Position Keeper, plus Heartbeat Monitor, Reconciler, and Kill Switch.

### 1.1 Current State (as of migration baseline)

| Area | Current | Notes |
|------|---------|--------|
| **Redis** | Single stream `order_stream`, consumer group `order_executors` | See [redis-migration-plan.md](./redis-migration-plan.md) |
| **Order path** | Strategy/HTTP → Order Executor (place + book in one service) | `run_order_executor.py` consumes `order_stream`, calls `BookingOrchestrator.place_order()` |
| **Fill Sync** | Standalone service; polls broker API, books via Orchestrator/Ledger | No Redis streams; not fed by Order Gateway |
| **Market data** | Data Updater (OHLCV/futures to DB) | No live ticks stream |
| **Admin** | HTTP API on Order Executor (`/admin/*`) | No `redis.manual_commands` stream |
| **Safety / ops** | No Heartbeat Monitor, Reconciler, or Kill Switch | Per-architecture these are net-new |

### 1.2 Target State (from architecture doc)

- **Streams:** `redis.ticks` → `redis.order_intent` → `redis.orders_approved` → (brokers) → `redis.fills_raw` → `redis.fills_normalized` → `redis.booking_events`; plus `redis.heartbeats`, `redis.kill_switch`, `redis.manual_commands`.
- **Services:** Market Data, Decision, Risk, Order Gateway, Fill Sync, OMS (6a), Position Keeper (6b), Admin, Heartbeat Monitor, Reconciler, Kill Switch.
- **Storage:** PostgreSQL remains canonical (orders, fills, positions, pnl, configs, risk_limits); Redis for streams + live ticks (TTL 1h) + heartbeats (TTL 5m).

### 1.3 Migration strategy: infra first, then new services

**Recommendation: migrate current infrastructure first, then implement new services.**

- **Infra first:** Move the existing order path onto the new stream names and minimal pipeline (e.g. `order_intent` → `orders_approved` → current Order Executor) with no new behavior. That way the system already runs on the target topology and stream contracts before we add Heartbeat Monitor, Reconciler, Kill Switch, Decision, Market Data, or split Order Executor into Risk / Order Gateway / OMS / Position Keeper.
- **Then new services:** Add observability and safety (Heartbeat, Reconciler, Kill Switch), then decompose the order path (Risk, Order Gateway, Fill Sync streams, OMS, Position Keeper), then Decision and Market Data, then Admin streams.

Benefits: fewer moving parts during cutover, validation of new streams with current (known-good) behavior, and new services land on a stable pipeline.

---

## 2. Gap Analysis: What Migrations Are Needed

### 2.1 Redis stream topology

| Migration | Current | Target |
|-----------|---------|--------|
| **Stream names and pipeline** | One stream: `order_stream` | Multiple: `order_intent`, `orders_approved`, `fills_raw`, `fills_normalized`, `booking_events`, `ticks`, `heartbeats`, `kill_switch`, `manual_commands` |
| **Consumer roles** | Single consumer: Order Executor on `order_stream` | Risk on `order_intent`; Order Gateway on `orders_approved`; Fill Sync (and OMS) on `fills_*`; OMS on `fills_normalized`; Position Keeper on `booking_events` |
| **Producers** | External/strategy → `order_stream` | Market Data → `ticks`; Decision → `order_intent`; Risk → `orders_approved`; Order Gateway → `fills_raw`; Fill Sync → `fills_normalized`; OMS → `booking_events`; Admin → `manual_commands`, `kill_switch`; All services → `heartbeats` |

**Implication:** Introduce new streams and consumer groups incrementally; keep `order_stream` working until the new pipeline is in place, then deprecate.

### 2.2 Service decomposition

| Migration | Current | Target |
|-----------|---------|--------|
| **Order Executor** | One service: consume orders → place → book (Ledger) | Split into: **Risk** (order_intent → orders_approved), **Order Gateway** (orders_approved → brokers + fills_raw), **OMS** (fills_normalized → booking_events + DB), **Position Keeper** (booking_events → positions/PnL in DB). Admin HTTP can move to **Admin** service that writes `manual_commands`. |
| **Fill Sync** | Polls broker API, books via Orchestrator/Ledger | Consume `fills_raw` (from Order Gateway) + broker API reconciliation; produce `fills_normalized`; OMS consumes and writes to DB + `booking_events`. |
| **Decision service** | None (strategies in viz/backtest or external) | New service: read `redis.ticks` + DB → produce `redis.order_intent`. |
| **Market Data** | Data Updater (batch OHLCV) | Add live feed path → `redis.ticks` (and optionally DB). |
| **Admin** | HTTP on Order Executor | Optional: Admin service (e.g. GUI) → `redis.manual_commands`; Risk/OMS consume for manual orders/fixes. |

### 2.3 New services (not present today)

| Service | Purpose | Migration work |
|---------|---------|----------------|
| **Heartbeat Monitor** | Consume `redis.heartbeats`; kill/restart unhealthy services | New service; all existing services must emit heartbeats. |
| **Reconciler** | DB vs broker drift → alerts (Slack/Email) | New service; may reuse existing `check_booking_recon` logic. |
| **Kill Switch** | All services read `redis.kill_switch`; emergency halt | New service (writer); all order-path services must respect it. |
| **Admin (stream-based)** | GUI → `redis.manual_commands` | New or refactor existing admin UI to publish to stream. |

### 2.4 Data and schema

- **PostgreSQL:** Target lists `orders, fills, positions, pnl, configs, risk_limits`. Current ledger already has orders, trades (fills), positions, balances, adjustments. Migration: ensure schema and naming align with architecture (e.g. risk_limits table if not present).
- **Redis:** Add TTLs for live ticks (1h) and heartbeats (5m); define stream key names and payloads per architecture doc.

---

## 3. Migration Workstreams

### WS1: Redis stream topology and contracts

- Define and document stream names, consumer group names, and payload schemas for: `order_intent`, `orders_approved`, `fills_raw`, `fills_normalized`, `booking_events`, `ticks`, `heartbeats`, `kill_switch`, `manual_commands`.
- Add code/config to create streams and consumer groups on startup (or via init script).
- Keep `order_stream` + current consumer until replacement path is validated.

### WS2: Risk service (order_intent → orders_approved)

- New service (e.g. `run_risk.py`): consume `redis.order_intent` (and optionally `redis.manual_commands` for manual orders).
- Pre-trade checks (e.g. risk_limits, position limits); produce to `redis.orders_approved` with optional `risk_score`.
- Order Executor’s “consume and place” logic will later move to Order Gateway.

### WS3: Order Gateway (orders_approved → brokers → fills_raw)

- New or refactored service: consume `redis.orders_approved`, call broker APIs (existing execution layer), write broker fill info to `redis.fills_raw`.
- Reuse current `BookingOrchestrator`/exchange adapter only for execution; do not book here (booking moves to OMS).

### WS4: Fill Sync and fills_normalized

- Extend Fill Sync: consume `redis.fills_raw`; merge with broker API reconciliation; produce `redis.fills_normalized` (with `order_id` and normalized fields).
- OMS will consume `redis.fills_normalized` (see WS5).

### WS5: OMS (6a) and Position Keeper (6b)

- **OMS:** Consume `redis.fills_normalized` (and optionally `redis.manual_commands` for manual fixes); persist orders/fills to DB; emit `redis.booking_events` (e.g. status, filled_qty).
- **Position Keeper:** Consume `redis.booking_events`; maintain positions/PnL in DB (continuous aggregation). Split out from current “place + book” logic so that booking and position aggregation are separate.

### WS6: Decision service and Market Data → ticks

- **Market Data:** Add path to publish live ticks to `redis.ticks` (and optionally DB). May extend Data Updater or add a small real-time feed process.
- **Decision:** New service: read `redis.ticks` + DB (e.g. strategy config, risk); produce `redis.order_intent`. Connects to strategy layer (see [old-strategies.md](./old-strategies.md) for strategy reference).

### WS7: Admin and manual_commands

- Admin GUI/API publishes manual orders and fixes to `redis.manual_commands`.
- Risk and OMS consume `manual_commands` (manual order path and fixes). Can keep HTTP admin API as a thin layer that writes to the stream.

### WS8: Heartbeat Monitor, Reconciler, Kill Switch

- **Heartbeat Monitor:** New service; consume `redis.heartbeats`; implement policy (e.g. restart if lag or missing heartbeat). All services that must be monitored emit to `redis.heartbeats` with `service`, `lag_ms`, TTL 5m.
- **Reconciler:** New service; compare DB vs broker (reuse or wrap `scripts/integrity/check_booking_recon.py`); send alerts (Slack/Email).
- **Kill Switch:** All order-path and critical services read `redis.kill_switch`; on `action: halt`, stop sending new orders and optionally drain. Admin or dedicated service writes to `redis.kill_switch`.

---

## 4. Phased Migration Plan

Phasing follows **infra first, then new services**: migrate the current order path onto the new stream topology with minimal new code, then add observability/safety and decompose services.

### Phase 0: Baseline and stream contracts (no behavior change)

- **Goal:** Define stream names, payloads, and consumer groups; add init/health checks for Redis streams.
- **Deliverables:** Design doc or appendix in this plan for each stream’s schema; optional script to create consumer groups.
- **Validation:** Redis streams exist; existing `order_stream` still works.

### Phase 1: Migrate current infra to new streams (infra first)

- **Goal:** Run the **current** order path on the new stream names; no new services and no behavior change.
- Introduce `redis.order_intent` and `redis.orders_approved` with documented payloads and consumer groups.
- **Option A (recommended):** Order Executor is updated to consume `orders_approved` instead of `order_stream`. Add a **pass-through Risk** (or bridge) that consumes `order_intent` and produces `orders_approved` (no real risk checks yet). Add a **bridge** that consumes `order_stream` and produces `order_intent` so existing strategy/HTTP publishers keep working without change. Flow: `order_stream` → bridge → `order_intent` → pass-through Risk → `orders_approved` → Order Executor (place+book unchanged).
- **Option B:** Publishers are updated to write to `order_intent`; pass-through Risk → `orders_approved`; Order Executor consumes `orders_approved`; `order_stream` is deprecated after cutover.
- **Deliverables:** Order Executor consumes `orders_approved`; bridge(s) and pass-through Risk in place; current place+book logic unchanged.
- **Validation:** Same orders as today flow through new streams; no double booking; `order_stream` can be retired once bridge is the only producer of `order_intent` (if using Option A).

**Exit criteria:** Current behavior runs on `order_intent` → `orders_approved` → Order Executor; no new services beyond a trivial Risk/bridge.

### Phase 2: New services — observability and safety

- **2a – Heartbeat Monitor**  
  - Implement Heartbeat Monitor service; define `redis.heartbeats` format and TTL.  
  - Add heartbeat emission to Order Executor (and optionally Data Updater, Fill Sync, Risk/bridge).  
  - No change to order flow.

- **2b – Reconciler**  
  - Implement Reconciler service; run DB vs broker checks on a schedule; plug into Slack/Email alerts.  
  - Reuse existing reconciliation scripts where possible.

- **2c – Kill Switch**  
  - Implement Kill Switch writer (e.g. from Admin or CLI); define `redis.kill_switch` payload.  
  - Add kill-switch check in Order Executor (and in Risk when it gets real logic): do not place new orders when halt is active.

**Exit criteria:** Heartbeat Monitor, Reconciler, and Kill Switch run in production; order path still order_intent → orders_approved → Order Executor.

### Phase 3: Real Risk and stream pipeline

- Replace pass-through Risk with **real Risk** service: pre-trade checks (risk_limits, position limits), produce `orders_approved` with optional `risk_score`.
- Order Executor continues to consume `orders_approved` and do place+book. No split of Order Executor yet.

**Exit criteria:** Risk enforces checks; orders_approved only contains approved orders; Order Executor unchanged.

### Phase 4: Order Gateway and fills_raw / fills_normalized

- **Order Gateway:** New service: consume `redis.orders_approved`; place orders via broker API; write to `redis.fills_raw`.
- **Fill Sync:** Consume `redis.fills_raw`; reconcile with broker API; produce `redis.fills_normalized`.
- **OMS (minimal):** Consume `redis.fills_normalized`; book to Ledger (orders + trades); emit `redis.booking_events`.
- **Position Keeper:** Consume `redis.booking_events`; update positions/PnL in DB.
- Remove “place + book” from Order Executor; Order Executor either removed or limited to HTTP admin and query API (no stream consumption).

**Exit criteria:** Full path: order_intent → Risk → orders_approved → Order Gateway → fills_raw → Fill Sync → fills_normalized → OMS → booking_events → Position Keeper → DB.

### Phase 5: Split 6 → 6a (OMS) + 6b (Position Keeper)

- Formalize OMS as the only writer of order/fill state and `booking_events`.
- Position Keeper is the only writer of positions/PnL from events. Ensure idempotency and replay capability (e.g. from `booking_events` or DB snapshot).

**Exit criteria:** Clear ownership: OMS = order lifecycle + booking_events; Position Keeper = positions/PnL aggregation.

### Phase 6: Decision service and Market Data → ticks

- **Market Data:** Publish live ticks to `redis.ticks` (and DB if required).
- **Decision:** Consume `redis.ticks` and DB; produce `redis.order_intent`. Wire to strategy layer (see [old-strategies.md](./old-strategies.md)).
- Remove `order_stream` → `order_intent` bridge; strategy flow is ticks → Decision → order_intent.

**Exit criteria:** Live flow from ticks to order_intent; no dependency on `order_stream`.

### Phase 7: Admin and manual_commands

- Admin (GUI or API) publishes manual orders and fixes to `redis.manual_commands`.
- Risk and OMS consume `manual_commands` for manual orders and adjustments.
- Deprecate or reduce direct HTTP booking endpoints in favor of stream-based manual path.

**Exit criteria:** Manual interventions go through `redis.manual_commands`; Risk/OMS handle them; audit trail in place.

### Phase 8: Cleanup and deprecation

- Remove `order_stream` and any bridge code.
- Remove or repurpose Order Executor container (e.g. only Admin + query API).
- Finalize stream key naming; document in architecture and runbooks.
- Update [redis-migration-plan.md](./redis-migration-plan.md) to state “migrated to new-trading-system streams.”

---

## 5. Dependencies and Ordering

- **Phase 0** is prerequisite for all stream-based work.
- **Phase 1 (infra first):** Migrate current path to new streams only; no new services (except trivial bridge/pass-through Risk). Validates topology with known-good behavior.
- **Phase 2:** Add new services (Heartbeat, Reconciler, Kill Switch) on top of the migrated pipeline.
- **Phase 3:** Real Risk logic; still single Order Executor doing place+book.
- **Phase 4:** Decompose into Order Gateway, Fill Sync streams, OMS, Position Keeper; depends on Phase 1–3.
- **Phase 5** refines Phase 4; **Phase 6** (Decision + ticks) can start once Phase 3 is stable.
- **Phase 7** (Admin/manual_commands) can overlap with Phase 4–6.
- **Phase 8** after all paths use the new streams.

---

## 6. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Double booking or missed fills during cutover | Run Reconciler frequently; use Fill Sync as backup; consider short parallel run (old + new path) with same orders disabled on one path. |
| Stream backlog or consumer lag | Heartbeat Monitor + lag alerts; tune consumer group and block time; document `xinfo streams` in daily ops. |
| Kill Switch not respected everywhere | Centralize “can place order?” check in Risk and Order Gateway; document which services must check `redis.kill_switch`. |
| Schema drift between streams and DB | Document payload schemas; add minimal validation on produce/consume; version stream payloads if needed. |

---

## 7. Success Criteria (EOD migration)

- All 8 architecture streams in use with documented producers/consumers.
- Services: Market Data, Decision, Risk, Order Gateway, Fill Sync, OMS, Position Keeper, Admin, Heartbeat Monitor, Reconciler, Kill Switch implemented and running.
- Order flow: ticks → order_intent → orders_approved → brokers → fills_raw → fills_normalized → booking_events → DB (orders, fills, positions, pnl).
- No dependency on `order_stream`.
- Daily ops checklist (architecture doc) and emergency recovery steps validated.
- [NEW-TRADING-SYSTEM-ARCHITECTURE.md](../architecture/NEW-TRADING-SYSTEM-ARCHITECTURE.md) and this plan kept in sync with any naming or flow changes.

---

## 8. Related Documents

- [NEW-TRADING-SYSTEM-ARCHITECTURE.md](../architecture/NEW-TRADING-SYSTEM-ARCHITECTURE.md) — target architecture.
- [order-booking-services-architecture.md](../architecture/order-booking-services-architecture.md) — current combined Order Executor design.
- [redis-migration-plan.md](./redis-migration-plan.md) — Redis and Order Executor rollout (current state).
- [old-strategies.md](./old-strategies.md) — strategy reference for Decision service.
