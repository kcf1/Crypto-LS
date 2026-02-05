# Redis Migration Plan

## Overview

This document outlines the step-by-step migration plan from the current architecture to the new Redis-based architecture with Order Executor Service.

## Migration Goals

1. Add Redis service without breaking existing functionality
2. Implement Order Executor Service (Redis consumer + HTTP API)
3. Add Redis caching to Data Updater (optional, additive)
4. Maintain backward compatibility throughout migration
5. Zero downtime migration (if possible)

## Current State

**Services Running:**
- PostgreSQL (database)
- pgAdmin (optional, database admin)
- Data Updater (collects OHLCV and futures data)

**Services Not Yet Implemented:**
- Order Executor Service
- Fill Sync Service (code exists, not in docker-compose)
- Strategy Services (future)

## Migration Phases

### Phase 1: Infrastructure Setup (No Breaking Changes)

**Goal:** Add Redis service and dependencies without affecting existing services.

**Tasks:**
1. ✅ Add Redis to `requirements.txt`
   - Add `redis>=5.0.0`
   - Add `flask>=3.0.0`
   - Add `flask-cors>=4.0.0`

2. ✅ Add Redis service to `docker-compose.yml`
   ```yaml
   redis:
     image: redis:7-alpine
     container_name: crypto-ls-redis
     ports:
       - "6379:6379"
     volumes:
       - redis_data:/data
     command: >
       redis-server
       --appendonly yes
       --maxmemory 256mb
       --maxmemory-policy allkeys-lru
     deploy:
       resources:
         limits:
           memory: 256M
           cpus: '0.2'
     healthcheck:
       test: ["CMD", "redis-cli", "ping"]
       interval: 10s
       timeout: 3s
       retries: 3
   ```

3. ✅ Add Redis volume to `docker-compose.yml`
   ```yaml
   volumes:
     postgres_data:
     redis_data:
   ```

4. ✅ Update `.env.example`
   ```bash
   REDIS_URL=redis://localhost:6379/0
   ORDER_EXECUTOR_PORT=8000
   ORDER_EXECUTOR_HOST=0.0.0.0
   ```

5. ✅ Test Redis connectivity
   - Start Redis: `docker compose up -d redis`
   - Test: `docker compose exec redis redis-cli ping`
   - Should return: `PONG`

**Validation:**
- ✅ All existing services still work
- ✅ Redis is accessible from other services
- ✅ No breaking changes

**Rollback Plan:**
- Remove Redis service from docker-compose.yml
- Services continue to work without Redis

**Estimated Time:** 30 minutes

---

### Phase 2: Order Executor Service (Core Implementation)

**Goal:** Create Order Executor Service with Redis consumer and HTTP API.

**Tasks:**
1. ✅ Create `Dockerfile.executor`
   ```dockerfile
   FROM python:3.11-slim
   ENV PYTHONUNBUFFERED=1
   WORKDIR /app

   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   COPY config config
   COPY data data
   COPY scripts scripts
   COPY booking booking
   COPY execution execution
   COPY alembic alembic

   CMD ["python", "scripts/services/run_order_executor.py"]
   ```

2. ✅ Create `scripts/services/run_order_executor.py`
   - Redis Stream consumer (consumer group: `order_executors`)
   - Flask HTTP server
   - Order processing logic (calls `BookingOrchestrator.place_order()`)
   - Admin endpoints (manual operations)
   - Query endpoints (orders, trades, positions, balances)

3. ✅ Add Order Executor service to `docker-compose.yml`
   ```yaml
   order-executor:
     build:
       context: .
       dockerfile: Dockerfile.executor
     container_name: crypto-ls-order-executor
     env_file:
       - .env
     environment:
       DATABASE_URL: postgresql://crypto:crypto@postgres:5432/cryptols
       REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
       ORDER_EXECUTOR_PORT: ${ORDER_EXECUTOR_PORT:-8000}
       ORDER_EXECUTOR_HOST: ${ORDER_EXECUTOR_HOST:-0.0.0.0}
     ports:
       - "8000:8000"
     depends_on:
       postgres:
         condition: service_healthy
       redis:
         condition: service_started
     restart: unless-stopped
     deploy:
       resources:
         limits:
           memory: 512M
           cpus: '0.5'
   ```

4. ✅ Update `execution/orchestrator.py`
   - Add immediate fill sync in `place_order()` (non-blocking)

5. ✅ Test Order Executor Service
   - Start: `docker compose up -d order-executor`
   - Health check: `curl http://localhost:8000/health`
   - Test manual order: `curl -X POST http://localhost:8000/orders -d '{...}'`

**Validation:**
- ✅ Order Executor starts successfully
- ✅ Health endpoint returns 200
- ✅ Can place orders via HTTP API
- ✅ Orders are booked to ledger
- ✅ Redis consumer is listening (check logs)

**Rollback Plan:**
- Stop Order Executor: `docker compose stop order-executor`
- Remove from docker-compose.yml
- Existing services unaffected

**Estimated Time:** 4-6 hours

---

### Phase 3: Fill Sync Service (Add to Docker Compose)

**Goal:** Add Fill Sync Service to docker-compose (code already exists).

**Tasks:**
1. ✅ Add Fill Sync service to `docker-compose.yml`
   ```yaml
   fill-sync:
     build:
       context: .
       dockerfile: Dockerfile.updater
     container_name: crypto-ls-fill-sync
     env_file:
       - .env
     environment:
       DATABASE_URL: postgresql://crypto:crypto@postgres:5432/cryptols
     command: ["python", "scripts/services/run_fill_sync.py"]
     depends_on:
       postgres:
         condition: service_healthy
     restart: unless-stopped
     deploy:
       resources:
         limits:
           memory: 256M
           cpus: '0.2'
   ```

2. ✅ Test Fill Sync Service
   - Start: `docker compose up -d fill-sync`
   - Check logs: `docker compose logs -f fill-sync`
   - Verify fills are synced every 60 seconds

**Validation:**
- ✅ Fill Sync starts successfully
- ✅ Syncs fills every 60 seconds
- ✅ Books trades to ledger

**Rollback Plan:**
- Stop Fill Sync: `docker compose stop fill-sync`
- Remove from docker-compose.yml

**Estimated Time:** 30 minutes

---

### Phase 4: Redis Caching (Optional, Additive)

**Goal:** Add Redis caching to Data Updater for faster market data access.

**Tasks:**
1. ✅ Update `data/updates/binance_ohlcv.py`
   - After writing to database, cache latest bar in Redis
   ```python
   # After storage.write_ohlcv(bars)
   latest_bar = bars[-1]
   redis_client.setex(
       f"market_data:{symbol}:{timeframe}",
       60,  # TTL: 60 seconds
       json.dumps(latest_bar)
   )
   ```

2. ✅ Update other data update tasks (optional)
   - Funding rate cache
   - Open interest cache
   - Basis cache

3. ✅ Test caching
   - Verify cache keys are created
   - Verify TTL is set correctly
   - Verify cache is refreshed

**Validation:**
- ✅ Cache keys are created
- ✅ Cache values are correct
- ✅ TTL works (keys expire)
- ✅ Database writes still work

**Rollback Plan:**
- Remove caching code from data updater
- Services continue to work (just slower)

**Estimated Time:** 1-2 hours

---

### Phase 5: Admin Interface (Manual Operations)

**Goal:** Add admin endpoints and Streamlit admin panel for manual operations.

**Tasks:**
1. ✅ Admin endpoints (already in Order Executor)
   - `POST /admin/trades` - Manual trade booking
   - `POST /admin/orders` - Manual order booking
   - `POST /admin/adjustments` - Create adjustment
   - `POST /admin/rebuild-positions` - Rebuild positions
   - `POST /admin/rebuild-balances` - Rebuild balances
   - `GET /admin/reconciliation` - Run reconciliation

2. ✅ Create Streamlit admin panel (`viz/pages/admin.py`)
   - Manual trade booking form
   - Manual order booking form
   - Adjustment creation form
   - Rebuild tools
   - Reconciliation viewer
   - Query interface

3. ✅ Create CLI tools (`scripts/admin/`)
   - `manual_trade.py`
   - `manual_order.py`
   - `create_adjustment.py`

4. ✅ Test admin operations
   - Test HTTP endpoints
   - Test Streamlit panel
   - Test CLI tools

**Validation:**
- ✅ All admin endpoints work
- ✅ Streamlit panel loads
- ✅ Manual operations book correctly
- ✅ Rebuilds work correctly

**Rollback Plan:**
- Remove admin endpoints (but keep core functionality)
- Remove Streamlit admin page

**Estimated Time:** 3-4 hours

---

### Phase 6: Strategy Integration (Future)

**Goal:** Update strategy services to publish orders to Redis Stream.

**Tasks:**
1. ✅ Create example strategy service (`scripts/examples/publish_order.py`)
   - Shows how to publish orders to Redis Stream
   - Demonstrates order message format

2. ✅ Update strategy documentation
   - Document Redis Stream message format
   - Document order placement flow

3. ✅ Test strategy integration
   - Publish test order to Redis Stream
   - Verify Order Executor processes it
   - Verify order is booked

**Validation:**
- ✅ Strategies can publish orders
- ✅ Orders are processed correctly
- ✅ Orders are booked to ledger

**Rollback Plan:**
- Strategies can still use HTTP API directly
- No breaking changes

**Estimated Time:** 1-2 hours

---

## Testing Strategy

### Unit Tests
- Test Redis connection
- Test order processing logic
- Test admin endpoint handlers

### Integration Tests
- Test order flow: Redis → Order Executor → Exchange → Ledger
- Test manual booking flow
- Test adjustment flow
- Test reconciliation

### Manual Testing Checklist

**Phase 1 (Infrastructure):**
- [ ] Redis starts successfully
- [ ] Redis is accessible from other services
- [ ] Existing services still work

**Phase 2 (Order Executor):**
- [ ] Order Executor starts successfully
- [ ] Health endpoint returns 200
- [ ] Can place order via HTTP API
- [ ] Order is booked to ledger
- [ ] Redis consumer is listening

**Phase 3 (Fill Sync):**
- [ ] Fill Sync starts successfully
- [ ] Syncs fills every 60 seconds
- [ ] Books trades to ledger

**Phase 4 (Caching):**
- [ ] Cache keys are created
- [ ] Cache values are correct
- [ ] TTL works

**Phase 5 (Admin Interface):**
- [ ] Admin endpoints work
- [ ] Streamlit panel loads
- [ ] Manual operations work
- [ ] Rebuilds work

**Phase 6 (Strategy Integration):**
- [ ] Strategies can publish orders
- [ ] Orders are processed correctly

---

## Rollback Procedures

### Phase 1 Rollback
```bash
# Remove Redis from docker-compose.yml
docker compose stop redis
docker compose rm redis
# Edit docker-compose.yml to remove redis service
```

### Phase 2 Rollback
```bash
# Stop Order Executor
docker compose stop order-executor
docker compose rm order-executor
# Edit docker-compose.yml to remove order-executor service
```

### Phase 3 Rollback
```bash
# Stop Fill Sync
docker compose stop fill-sync
docker compose rm fill-sync
# Edit docker-compose.yml to remove fill-sync service
```

### Phase 4 Rollback
```bash
# Remove caching code from data updater
# Revert changes to data/updates/*.py
# Restart data-updater
docker compose restart data-updater
```

### Phase 5 Rollback
```bash
# Remove admin endpoints (optional)
# Remove Streamlit admin page (optional)
# Core functionality still works
```

### Full Rollback
```bash
# Revert to previous git commit
git checkout dev
git reset --hard <previous-commit>
# Restart all services
docker compose down
docker compose up -d
```

---

## Migration Timeline

| Phase | Duration | Dependencies | Risk Level |
|-------|----------|--------------|-----------|
| Phase 1: Infrastructure | 30 min | None | Low |
| Phase 2: Order Executor | 4-6 hours | Phase 1 | Medium |
| Phase 3: Fill Sync | 30 min | Phase 1 | Low |
| Phase 4: Caching | 1-2 hours | Phase 1 | Low |
| Phase 5: Admin Interface | 3-4 hours | Phase 2 | Low |
| Phase 6: Strategy Integration | 1-2 hours | Phase 2 | Low |

**Total Estimated Time:** 10-15 hours

**Recommended Approach:**
- Phase 1-3: Complete first (core functionality)
- Phase 4-5: Complete next (enhancements)
- Phase 6: Complete last (future integration)

---

## Success Criteria

### Phase 1 Success
- ✅ Redis service running
- ✅ All existing services still work
- ✅ No breaking changes

### Phase 2 Success
- ✅ Order Executor running
- ✅ Can place orders via HTTP API
- ✅ Orders are booked to ledger
- ✅ Redis consumer working

### Phase 3 Success
- ✅ Fill Sync running
- ✅ Fills synced every 60 seconds
- ✅ Trades booked to ledger

### Phase 4 Success
- ✅ Cache keys created
- ✅ Cache values correct
- ✅ Database writes still work

### Phase 5 Success
- ✅ Admin endpoints work
- ✅ Streamlit panel works
- ✅ Manual operations work

### Phase 6 Success
- ✅ Strategies can publish orders
- ✅ Orders processed correctly

---

## Post-Migration Tasks

1. ✅ Monitor logs for errors
2. ✅ Monitor Redis memory usage
3. ✅ Monitor Order Executor CPU/memory
4. ✅ Verify order processing latency
5. ✅ Run reconciliation checks
6. ✅ Update documentation
7. ✅ Train team on new architecture

---

## Risk Assessment

### Low Risk
- Phase 1: Infrastructure (additive, no breaking changes)
- Phase 3: Fill Sync (code already exists)
- Phase 4: Caching (optional, additive)

### Medium Risk
- Phase 2: Order Executor (new service, but uses existing code)
- Phase 5: Admin Interface (new features, but optional)

### High Risk
- None identified (all phases are additive or optional)

---

## Communication Plan

### Before Migration
- Notify team of migration plan
- Schedule migration window (if needed)
- Prepare rollback plan

### During Migration
- Test each phase before proceeding
- Document any issues encountered
- Update team on progress

### After Migration
- Verify all services working
- Run reconciliation checks
- Update documentation
- Share lessons learned

---

## Notes

- All phases are designed to be **additive** (no breaking changes)
- Each phase can be **rolled back independently**
- Migration can be done **incrementally** (one phase at a time)
- **Zero downtime** migration possible (add services, don't remove existing ones)

---

## References

- Architecture Document: `docs/plans/architecture/order-booking-services-architecture.md`
- Implementation Checklist: `docs/plans/checklists/order-booking-services-checklist.md`
- Resource Estimation: `docs/operations/resource-estimation-new-architecture.md`
- Summary: `docs/operations/order-booking-services-summary.md`
