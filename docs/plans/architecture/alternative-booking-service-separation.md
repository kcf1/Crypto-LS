# Alternative Architecture: Booking Service Separation

**Status:** Alternative Design (Not Implemented)  
**Created:** 2025-02-05  
**Current Architecture:** Monolithic order-executor service

## Overview

This document outlines an alternative architecture where booking management operations are separated from order execution into a dedicated service. This is **not** the current implementation but serves as a reference for future architectural decisions.

## Current Architecture

**Single Service: `order-executor`**
- Order placement (Redis Stream + HTTP API)
- Query endpoints (orders, trades, positions, balances)
- Admin operations (manual bookings, rebuilds, reconciliation)
- Book management (CRUD operations)
- Health checks

## Alternative Architecture: Two-Service Split

### Option A: Split by Responsibility

#### Service 1: `order-executor` (Core Execution)
**Purpose:** High-performance order execution and queries

**Responsibilities:**
- ✅ Order placement via HTTP API
- ✅ Redis Stream consumer for automated orders
- ✅ Order cancellation
- ✅ Query endpoints (read-only):
  - `GET /orders` - List orders
  - `GET /orders/<id>` - Get order details
  - `GET /trades` - List trades
  - `GET /positions` - List positions
  - `GET /balances` - List balances
- ✅ Health checks

**Characteristics:**
- High throughput, low latency
- Stateless (can scale horizontally)
- Read-heavy workload
- No write operations except order placement

**Dependencies:**
- `Ledger` (read operations)
- `BookingOrchestrator` (order execution)
- Redis (stream consumption)
- Binance API (order placement)

**Scaling:**
- Can run multiple instances
- Load balanced for HTTP requests
- Each instance consumes from Redis stream (consumer group)

---

#### Service 2: `booking-admin` (Management)
**Purpose:** Administrative and configuration operations

**Responsibilities:**
- ✅ Book management:
  - `GET /books` - List books
  - `GET /books/<id>` - Get book details
  - `POST /books` - Create book
  - `PUT /books/<id>` - Update book
  - `DELETE /books/<id>` - Deactivate book
- ✅ Manual operations:
  - `POST /admin/trades` - Manual trade booking
  - `POST /admin/orders` - Manual order booking
  - `POST /admin/adjustments` - Manual adjustments
- ✅ Maintenance operations:
  - `POST /admin/rebuild-positions` - Rebuild positions table
  - `POST /admin/rebuild-balances` - Rebuild balances table
  - `GET /admin/reconciliation` - Run reconciliation checks
- ✅ Health checks

**Characteristics:**
- Low frequency, high-privilege operations
- Write-heavy workload
- Stateful operations (rebuilds, reconciliation)
- Requires authentication/authorization

**Dependencies:**
- `Ledger` (full read/write access)
- Database (direct access for rebuilds)

**Scaling:**
- Single instance (or small number)
- No horizontal scaling needed
- Can be deployed separately from execution service

---

### Option B: Split by Access Pattern

#### Service 1: `order-executor` (Hot Path)
**Purpose:** Real-time order execution

**Responsibilities:**
- Order placement (HTTP + Redis)
- Order cancellation
- Redis Stream consumer
- Read-only queries for real-time data

#### Service 2: `booking-api` (Management API)
**Purpose:** All management and configuration

**Responsibilities:**
- Book management
- Admin operations
- Reconciliation
- Historical queries (if needed)

---

## Implementation Details

### Shared Components

Both services would share:
- `booking/ledger.py` - Database access layer
- `config/settings.py` - Configuration
- Database connection (PostgreSQL)
- Same database schema

### Service Communication

**Option 1: Direct Database Access**
- Both services connect to same database
- No inter-service communication needed
- Simpler architecture
- Risk: Database becomes bottleneck

**Option 2: API Communication**
- `booking-admin` exposes API
- `order-executor` calls `booking-admin` for book validation
- More complex, adds network latency
- Better separation of concerns

**Recommended:** Option 1 (Direct Database) for simplicity

### Deployment

```yaml
# docker-compose.yml
services:
  order-executor:
    build:
      dockerfile: Dockerfile.executor
    ports:
      - "8000:8000"
    environment:
      SERVICE_MODE: execution  # Only enable execution endpoints
    deploy:
      replicas: 3  # Scale horizontally
  
  booking-admin:
    build:
      dockerfile: Dockerfile.booking-admin
    ports:
      - "8001:8000"
    environment:
      SERVICE_MODE: admin  # Only enable admin endpoints
    deploy:
      replicas: 1  # Single instance
```

### Code Structure

```
scripts/services/
├── run_order_executor.py      # Execution service
└── run_booking_admin.py       # Admin service

# Shared
booking/
└── ledger.py                  # Used by both services
```

### Endpoint Routing

**order-executor:**
```python
# Only execution and query endpoints
@app.route("/orders", methods=["POST", "GET"])
@app.route("/orders/<id>", methods=["GET"])
@app.route("/orders/<id>/cancel", methods=["POST"])
@app.route("/trades", methods=["GET"])
@app.route("/positions", methods=["GET"])
@app.route("/balances", methods=["GET"])
@app.route("/health", methods=["GET"])
```

**booking-admin:**
```python
# Only admin and management endpoints
@app.route("/books", methods=["GET", "POST"])
@app.route("/books/<id>", methods=["GET", "PUT", "DELETE"])
@app.route("/admin/trades", methods=["POST"])
@app.route("/admin/orders", methods=["POST"])
@app.route("/admin/adjustments", methods=["POST"])
@app.route("/admin/rebuild-positions", methods=["POST"])
@app.route("/admin/rebuild-balances", methods=["POST"])
@app.route("/admin/reconciliation", methods=["GET"])
@app.route("/health", methods=["GET"])
```

## When to Consider This Split

### Triggers for Separation

1. **Different Security Requirements**
   - Admin operations need stricter authentication
   - Different access control policies
   - Audit logging requirements

2. **Scaling Mismatch**
   - Execution needs many instances (high throughput)
   - Admin needs few instances (low frequency)
   - Different resource requirements

3. **Deployment Independence**
   - Admin changes frequently (new features)
   - Execution changes rarely (stability critical)
   - Different release cycles

4. **Performance Isolation**
   - Admin operations are CPU/memory intensive (rebuilds)
   - Admin operations impact execution performance
   - Need to isolate heavy operations

5. **Team Separation**
   - Different teams own execution vs. admin
   - Different development workflows
   - Different on-call responsibilities

6. **Compliance Requirements**
   - Admin operations need separate audit trails
   - Different compliance requirements
   - Regulatory separation needed

## Migration Strategy

If deciding to split:

### Phase 1: Preparation
1. Extract shared `Ledger` into separate module (already done)
2. Create service configuration flags (`SERVICE_MODE`)
3. Add feature flags to enable/disable endpoints

### Phase 2: Create Admin Service
1. Create `run_booking_admin.py`
2. Copy admin endpoints to new service
3. Deploy alongside existing service
4. Route admin traffic to new service

### Phase 3: Remove Admin from Executor
1. Remove admin endpoints from `order-executor`
2. Update documentation
3. Update GUI to point to correct services

### Phase 4: Optimize
1. Scale services independently
2. Add service-specific optimizations
3. Monitor performance improvements

## Trade-offs

### Advantages

✅ **Separation of Concerns**
- Clear boundaries between execution and management
- Easier to reason about each service

✅ **Independent Scaling**
- Scale execution horizontally
- Keep admin single-instance

✅ **Security Isolation**
- Different authentication for admin
- Reduced attack surface for execution

✅ **Deployment Flexibility**
- Deploy admin changes without affecting execution
- Different release cycles

✅ **Performance Isolation**
- Heavy admin operations don't impact execution
- Better resource utilization

### Disadvantages

❌ **Increased Complexity**
- Two services to deploy and monitor
- More moving parts
- Inter-service communication (if needed)

❌ **Code Duplication**
- Shared `Ledger` code
- Potential for inconsistency
- More code to maintain

❌ **Operational Overhead**
- Two services to monitor
- Two sets of logs
- More complex debugging

❌ **Over-Engineering Risk**
- May be unnecessary for small scale
- Adds complexity without clear benefit
- Premature optimization

## Recommendation

**For Current Scale:** Keep monolithic architecture
- Simpler to operate
- Sufficient for current needs
- Easier to maintain

**Consider Split When:**
- Admin operations impact execution performance
- Need different scaling strategies
- Security/compliance requirements demand separation
- Team structure benefits from separation

## References

- Current implementation: `scripts/services/run_order_executor.py`
- Ledger implementation: `booking/ledger.py`
- Docker configuration: `docker-compose.yml`
- Books management plan: `docs/plans/features/books-management.md`
