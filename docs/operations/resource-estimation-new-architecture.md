# Resource Estimation for New Architecture (with Redis & Order Executor)

## Overview

This document estimates CPU, RAM, disk, and network resources needed for the new architecture with Redis and Order Executor Service.

## Current Architecture Resources

| Service | RAM | CPU | Notes |
|---------|-----|-----|-------|
| PostgreSQL | 512M | 0.2-0.5 cores | Database |
| pgAdmin | 512M | 0.1 cores | Optional, only when needed |
| Data Updater | 768M | 0.3-0.5 cores | Runs every 5 minutes |

**Current Total:** ~1.8GB RAM (without pgAdmin: ~1.3GB)

---

## New Architecture Resources

### Assumptions

- **Symbols tracked:** 100 symbols (from `settings.symbols`)
- **Data updater frequency:** Every 5 minutes (300 seconds)
- **Fill sync frequency:** Every 60 seconds
- **Order volume scenarios:**
  - **Low:** 1-10 orders/hour
  - **Medium:** 10-100 orders/hour
  - **High:** 100-1000 orders/hour

---

## 1. Redis Service

### Memory Estimation

#### A. Redis Streams (Order Queue)

**Order Stream (`order_stream`):**
- Message size: ~500 bytes per order message (JSON)
- Retention: 24 hours (configurable)

**Low volume (10 orders/hour):**
- Messages/day: 10 × 24 = 240 messages
- Memory: 240 × 500 bytes = 120 KB
- **Estimated:** ~200 KB (with overhead)

**Medium volume (100 orders/hour):**
- Messages/day: 100 × 24 = 2,400 messages
- Memory: 2,400 × 500 bytes = 1.2 MB
- **Estimated:** ~2 MB (with overhead)

**High volume (1000 orders/hour):**
- Messages/day: 1000 × 24 = 24,000 messages
- Memory: 24,000 × 500 bytes = 12 MB
- **Estimated:** ~20 MB (with overhead)

#### B. Market Data Cache

**Cache keys:**
- Format: `market_data:{symbol}:{timeframe}`
- Symbols: 100 symbols
- Timeframes: 1 timeframe (5m) initially, could expand to 3-5
- Value size: ~200 bytes per bar (JSON)

**Cache size:**
- Keys: 100 symbols × 1 timeframe = 100 keys
- Value per key: 200 bytes
- Total: 100 × 200 bytes = 20 KB
- **Estimated:** ~50 KB (with Redis overhead)

**TTL:** 60 seconds (refreshed every 5 minutes by data-updater)

#### C. Rate Limiting Counters

**Keys:**
- `rate_limit:binance:orders` (1 key)
- `rate_limit:binance:api` (1 key)
- `rate_limit:strategy:*` (optional, ~5-10 keys)

**Size:**
- Counter value: 8 bytes (integer)
- Keys: ~10 keys × 8 bytes = 80 bytes
- **Estimated:** ~1 KB (with overhead)

#### D. Distributed Locks

**Keys:**
- Format: `lock:order:{symbol}:{timestamp}`
- Active locks: ~1-5 at any time
- Size: ~50 bytes per lock
- **Estimated:** ~1 KB

#### E. Redis Overhead

- Base Redis process: ~10-15 MB
- AOF persistence buffer: ~5-10 MB
- Consumer groups metadata: ~1-2 MB
- **Total overhead:** ~20-30 MB

### Redis Memory Summary

| Component | Low Volume | Medium Volume | High Volume |
|-----------|------------|---------------|-------------|
| Order Stream | 200 KB | 2 MB | 20 MB |
| Market Data Cache | 50 KB | 50 KB | 50 KB |
| Rate Limits | 1 KB | 1 KB | 1 KB |
| Locks | 1 KB | 1 KB | 1 KB |
| Redis Overhead | 25 MB | 25 MB | 25 MB |
| **Total** | **~26 MB** | **~28 MB** | **~46 MB** |

**Recommended:** **256 MB** (with 5x headroom for growth)

### CPU Estimation

- **Idle:** ~0.01-0.05 cores
- **Low volume:** ~0.05-0.1 cores
- **Medium volume:** ~0.1-0.2 cores
- **High volume:** ~0.2-0.5 cores

**Recommended:** **0.2 cores** (sufficient for medium-high volume)

### Disk Estimation

- **AOF persistence:** ~10-50 MB (depending on volume)
- **RDB snapshots:** Optional, ~5-10 MB
- **Total:** ~50-100 MB

**Recommended:** **100 MB** disk space

### Network Estimation

- **Incoming:** Order messages + cache writes
  - Low: ~1 KB/min = ~1.4 KB/s
  - Medium: ~10 KB/min = ~170 bytes/s
  - High: ~100 KB/min = ~1.7 KB/s
- **Outgoing:** Cache reads + stream consumption
  - Low: ~5 KB/min = ~85 bytes/s
  - Medium: ~50 KB/min = ~850 bytes/s
  - High: ~500 KB/min = ~8.5 KB/s

**Recommended:** Minimal network usage (< 10 KB/s)

---

## 2. Order Executor Service

### Memory Estimation

#### A. Python Process Base

- Python interpreter: ~30-40 MB
- Flask/FastAPI: ~10-15 MB
- Redis client: ~5 MB
- SQLAlchemy: ~10-15 MB
- Binance client: ~5 MB
- **Base:** ~60-80 MB

#### B. Application Code

- Imported modules: ~20-30 MB
- **Total base:** ~80-110 MB

#### C. Runtime Memory

- **HTTP request handling:** ~1-5 MB per concurrent request
- **Redis consumer:** ~5-10 MB (background thread)
- **Order processing:** ~1-2 MB per order (temporary)
- **Database connections:** ~2-5 MB (connection pool)

**Concurrent requests:**
- Low: 1-2 concurrent requests → ~10-20 MB
- Medium: 5-10 concurrent requests → ~30-50 MB
- High: 20-50 concurrent requests → ~80-150 MB

#### D. Memory Summary

| Scenario | Base | Runtime | Total |
|----------|------|---------|-------|
| Low volume | 100 MB | 20 MB | **120 MB** |
| Medium volume | 100 MB | 50 MB | **150 MB** |
| High volume | 100 MB | 150 MB | **250 MB** |

**Recommended:** **512 MB** (with 2x headroom for spikes)

### CPU Estimation

- **Idle (HTTP server waiting):** ~0.01-0.05 cores
- **Processing order (Redis consumer):**
  - Low: ~0.05-0.1 cores
  - Medium: ~0.1-0.3 cores
  - High: ~0.3-0.8 cores
- **HTTP request handling:**
  - Low: ~0.05-0.1 cores
  - Medium: ~0.1-0.2 cores
  - High: ~0.2-0.5 cores

**Total CPU:**
- Low: ~0.1-0.2 cores
- Medium: ~0.2-0.5 cores
- High: ~0.5-1.3 cores

**Recommended:** **0.5 cores** (sufficient for medium-high volume)

### Disk Estimation

- **Application code:** ~50-100 MB (Docker image)
- **Logs:** ~10-50 MB/day (rotating)
- **Total:** ~100-150 MB

**Recommended:** **200 MB** disk space

### Network Estimation

- **Incoming (HTTP):**
  - Low: ~1 request/min = ~100 bytes/s
  - Medium: ~10 requests/min = ~1 KB/s
  - High: ~100 requests/min = ~10 KB/s
- **Outgoing (HTTP responses):**
  - Low: ~1 KB/min = ~17 bytes/s
  - Medium: ~10 KB/min = ~170 bytes/s
  - High: ~100 KB/min = ~1.7 KB/s
- **Redis (bidirectional):**
  - Low: ~1 KB/min = ~17 bytes/s
  - Medium: ~10 KB/min = ~170 bytes/s
  - High: ~100 KB/min = ~1.7 KB/s
- **Binance API (outgoing):**
  - Low: ~1 request/min = ~500 bytes/s
  - Medium: ~10 requests/min = ~5 KB/s
  - High: ~100 requests/min = ~50 KB/s

**Total network:**
- Low: ~1 KB/s
- Medium: ~7 KB/s
- High: ~55 KB/s

**Recommended:** Minimal network usage (< 100 KB/s)

---

## 3. Fill Sync Service

### Memory Estimation

- **Python process base:** ~60-80 MB (similar to Order Executor)
- **Runtime memory:** ~10-20 MB (lightweight, periodic)
- **Total:** ~70-100 MB

**Recommended:** **256 MB** (with headroom)

### CPU Estimation

- **Idle:** ~0.01 cores
- **Active (every 60s):** ~0.1-0.2 cores (brief spikes)
- **Average:** ~0.05 cores

**Recommended:** **0.2 cores**

### Disk Estimation

- **Application code:** ~50-100 MB
- **Logs:** ~5-20 MB/day
- **Total:** ~100 MB

**Recommended:** **100 MB** disk space

### Network Estimation

- **Database queries:** ~1-5 KB/min = ~20-80 bytes/s
- **Binance API:** ~10-50 KB/min = ~170-850 bytes/s
- **Total:** ~200 bytes/s - 1 KB/s

**Recommended:** Minimal network usage (< 2 KB/s)

---

## 4. Data Updater Service (Updated)

### Additional Memory (Redis Caching)

- **Redis client:** +5 MB
- **Cache operations:** +5-10 MB
- **Total additional:** ~10-15 MB

**New total:** ~780-800 MB (was 768M)

**Recommended:** **768 MB** (unchanged, Redis overhead minimal)

---

## Total Resource Summary

### Low Volume (1-10 orders/hour)

| Service | RAM | CPU | Disk | Network |
|---------|-----|-----|------|---------|
| PostgreSQL | 512M | 0.2-0.5 | 10GB+ | Low |
| pgAdmin | 512M | 0.1 | 100MB | Low |
| Data Updater | 768M | 0.3-0.5 | 100MB | Low |
| **Redis** | **256M** | **0.2** | **100MB** | **< 10 KB/s** |
| **Order Executor** | **512M** | **0.5** | **200MB** | **< 10 KB/s** |
| **Fill Sync** | **256M** | **0.2** | **100MB** | **< 2 KB/s** |
| **Total** | **~2.8 GB** | **~1.5 cores** | **~10.5 GB** | **Low** |

### Medium Volume (10-100 orders/hour)

| Service | RAM | CPU | Disk | Network |
|---------|-----|-----|------|---------|
| PostgreSQL | 512M | 0.2-0.5 | 10GB+ | Low |
| pgAdmin | 512M | 0.1 | 100MB | Low |
| Data Updater | 768M | 0.3-0.5 | 100MB | Low |
| **Redis** | **256M** | **0.2** | **100MB** | **< 10 KB/s** |
| **Order Executor** | **512M** | **0.5** | **200MB** | **< 10 KB/s** |
| **Fill Sync** | **256M** | **0.2** | **100MB** | **< 2 KB/s** |
| **Total** | **~2.8 GB** | **~1.5 cores** | **~10.5 GB** | **Low** |

### High Volume (100-1000 orders/hour)

| Service | RAM | CPU | Disk | Network |
|---------|-----|-----|------|---------|
| PostgreSQL | 512M | 0.3-0.8 | 10GB+ | Medium |
| pgAdmin | 512M | 0.1 | 100MB | Low |
| Data Updater | 768M | 0.3-0.5 | 100MB | Low |
| **Redis** | **512M** | **0.5** | **200MB** | **< 50 KB/s** |
| **Order Executor** | **1 GB** | **1.0** | **500MB** | **< 100 KB/s** |
| **Fill Sync** | **256M** | **0.2** | **100MB** | **< 2 KB/s** |
| **Total** | **~3.5 GB** | **~2.5 cores** | **~11 GB** | **Medium** |

---

## Recommended Docker Compose Resource Limits

```yaml
services:
  redis:
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.2'
  
  order-executor:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
  
  fill-sync:
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.2'
```

**For high volume, increase:**
- Redis: 512M RAM, 0.5 CPU
- Order Executor: 1GB RAM, 1.0 CPU

---

## Host Machine Requirements

### Minimum (Low-Medium Volume)

- **RAM:** 4 GB (2.8 GB used + 1.2 GB OS overhead)
- **CPU:** 2 cores (1.5 used + 0.5 OS overhead)
- **Disk:** 20 GB (10.5 GB data + 5 GB OS + 5 GB headroom)
- **Network:** 10 Mbps (sufficient for low-medium traffic)

### Recommended (All Scenarios)

- **RAM:** 8 GB (comfortable headroom)
- **CPU:** 4 cores (can handle high volume)
- **Disk:** 50 GB (plenty of room for database growth)
- **Network:** 100 Mbps (sufficient for all scenarios)

### Production (High Volume)

- **RAM:** 16 GB (scaling headroom)
- **CPU:** 8 cores (can run multiple order executors)
- **Disk:** 100 GB+ (database growth)
- **Network:** 1 Gbps (high-frequency trading)

---

## Cost Estimation (Cloud Hosting)

### AWS EC2 (Example)

**Low-Medium Volume:**
- Instance: `t3.medium` (2 vCPU, 4 GB RAM)
- Cost: ~$30-40/month

**High Volume:**
- Instance: `t3.large` (2 vCPU, 8 GB RAM)
- Cost: ~$60-80/month

### DigitalOcean Droplet

**Low-Medium Volume:**
- Droplet: 4 GB RAM, 2 vCPU
- Cost: ~$24/month

**High Volume:**
- Droplet: 8 GB RAM, 4 vCPU
- Cost: ~$48/month

### VPS (Local/On-Premise)

**Hardware cost:** One-time purchase
- Mini PC: $200-400 (8GB RAM, 4 cores)
- Power: ~$5-10/month

---

## Scaling Considerations

### When to Scale Up

1. **Redis memory > 80%:** Increase Redis RAM limit
2. **Order Executor CPU > 80%:** Increase CPU or add more instances
3. **Order queue depth > 1000:** Add more Order Executor instances
4. **Database CPU > 80%:** Optimize queries or upgrade database

### Horizontal Scaling

- **Multiple Order Executors:** Can run 2-3 instances consuming from same Redis Stream
- **Consumer Groups:** Redis Streams support multiple consumers in same group
- **Load Balancing:** Use nginx/traefik for HTTP endpoints

### Vertical Scaling

- **Increase RAM:** For higher order volumes
- **Increase CPU:** For faster processing
- **Upgrade Database:** For larger datasets

---

## Summary

**New Services Added:**
- Redis: 256 MB RAM, 0.2 CPU
- Order Executor: 512 MB RAM, 0.5 CPU
- Fill Sync: 256 MB RAM, 0.2 CPU

**Total Additional Resources:**
- RAM: +1 GB
- CPU: +0.9 cores
- Disk: +400 MB
- Network: Minimal (< 20 KB/s)

**Total System Resources (Low-Medium Volume):**
- RAM: ~2.8 GB (was ~1.8 GB)
- CPU: ~1.5 cores (was ~1.0 core)
- Disk: ~10.5 GB (was ~10 GB)
- Network: Low (unchanged)

**Recommendation:** 4 GB RAM, 2 CPU cores minimum for comfortable operation.
