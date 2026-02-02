# Monitoring Manual

This guide covers how to monitor and manage the Crypto-LS Docker services, particularly the data collection system.

## Services Overview

The system consists of three Docker services:

1. **postgres** - PostgreSQL 16 database (port 5432)
2. **pgadmin** - Web GUI for database management (port 5050)
3. **data-updater** - Data collection service (runs continuously)

## Service Status

### Check All Services Status

```bash
docker compose ps
```

Expected output:
```
NAME                     IMAGE                    COMMAND                   SERVICE        STATUS                  PORTS
crypto-ls-data-updater   crypto-ls-data-updater   "python scripts/run_…"   data-updater   Up X minutes           
crypto-ls-pgadmin        dpage/pgadmin4:latest   "/entrypoint.sh"          pgadmin        Up X hours              0.0.0.0:5050->80/tcp
crypto-ls-postgres       postgres:16-alpine       "docker-entrypoint.s…"   postgres       Up X hours (healthy)    0.0.0.0:5432->5432/tcp
```

### Check Specific Service Status

```bash
# Check if data-updater is running
docker ps --filter "name=crypto-ls-data-updater"

# Check all containers (including stopped)
docker compose ps -a
```

## Data Updater Monitoring

### View Logs

**Real-time log following:**
```bash
docker logs -f crypto-ls-data-updater
```

**View last N lines:**
```bash
docker logs --tail 50 crypto-ls-data-updater
```

**View all logs:**
```bash
docker logs crypto-ls-data-updater
```

**View logs with timestamps:**
```bash
docker logs -t crypto-ls-data-updater
```

### Expected Log Output

The data-updater runs every 5 minutes, aligned to minute marks (:05, :10, :15, etc.). You should see logs like:

```
INFO:__main__:Data updater started; interval=300 s (aligned to 5-minute marks)
DEBUG:__main__:Sleeping 120.5 s until 10:15:00
INFO:data.updates.binance_ohlcv:BTCUSDT 5m: wrote 150 rows (tail refresh + new)
INFO:data.updates.binance_ohlcv:ETHUSDT 5m: wrote 150 rows (tail refresh + new)
...
```

### Check Container Health

```bash
# Inspect container state
docker inspect crypto-ls-data-updater --format='{{.State.Status}}'

# Check if container is running
docker inspect crypto-ls-data-updater --format='{{.State.Running}}'

# View container start time
docker inspect crypto-ls-data-updater --format='Started: {{.State.StartedAt}}'
```

### Monitor Resource Usage

```bash
# CPU and memory usage
docker stats crypto-ls-data-updater

# One-time stats
docker stats --no-stream crypto-ls-data-updater
```

## Database Monitoring

### Check Database Connection

```bash
# Connect to postgres container
docker exec -it crypto-ls-postgres psql -U crypto -d cryptols

# Check if database is accessible
docker exec crypto-ls-postgres pg_isready -U crypto -d cryptols
```

### Check Data Collection Status

```bash
# Connect to database and check latest data
docker exec -it crypto-ls-postgres psql -U crypto -d cryptols -c "
SELECT symbol, timeframe, MAX(open_time) as latest_time, COUNT(*) as row_count 
FROM ohlcv 
GROUP BY symbol, timeframe 
ORDER BY symbol, timeframe;
"
```

### Check Recent Data Updates

```bash
docker exec -it crypto-ls-postgres psql -U crypto -d cryptols -c "
SELECT symbol, timeframe, MAX(open_time) as latest_time 
FROM ohlcv 
WHERE open_time > EXTRACT(EPOCH FROM NOW() - INTERVAL '1 hour') * 1000
GROUP BY symbol, timeframe
ORDER BY latest_time DESC;
"
```

## Service Management

### Start Services

```bash
# Start all services
docker compose up -d

# Start specific service
docker compose up -d data-updater
```

### Stop Services

```bash
# Stop all services
docker compose down

# Stop specific service (keeps others running)
docker compose stop data-updater

# Stop and remove containers (keeps volumes)
docker compose down
```

### Restart Services

```bash
# Restart all services
docker compose restart

# Restart specific service
docker compose restart data-updater
```

### Rebuild and Restart

```bash
# Rebuild data-updater image and restart
docker compose up -d --build data-updater

# Rebuild all services
docker compose up -d --build
```

## Troubleshooting

### Data Updater Not Running

**Check if container exists:**
```bash
docker compose ps -a | grep data-updater
```

**If container is stopped, start it:**
```bash
docker compose start data-updater
```

**If container exited, check logs:**
```bash
docker logs crypto-ls-data-updater
```

**Restart the service:**
```bash
docker compose restart data-updater
```

### No Logs Appearing

The data-updater waits until the next aligned 5-minute mark before its first run. If you just started it, logs may be empty until the next mark (:05, :10, :15, etc.).

**Check current time alignment:**
- Current time: Check system time
- Next run: Will be at the next :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55, or :00

**Force immediate check (if needed):**
```bash
# Restart to see startup logs
docker compose restart data-updater
docker logs -f crypto-ls-data-updater
```

### Database Connection Issues

**Check if postgres is healthy:**
```bash
docker compose ps | grep postgres
```

**Check postgres logs:**
```bash
docker logs crypto-ls-postgres
```

**Test connection from data-updater container:**
```bash
docker exec crypto-ls-data-updater python -c "
from config import settings
from data import Storage
storage = Storage()
print('Connected:', storage is not None)
"
```

### Data Not Updating

**Check if data-updater is running:**
```bash
docker compose ps data-updater
```

**Check recent logs for errors:**
```bash
docker logs --tail 100 crypto-ls-data-updater | grep -i error
```

**Verify data collection is happening:**
```bash
# Check latest data timestamps
docker exec -it crypto-ls-postgres psql -U crypto -d cryptols -c "
SELECT symbol, MAX(open_time) as latest_time,
       to_timestamp(MAX(open_time)/1000) as latest_datetime
FROM ohlcv 
GROUP BY symbol 
ORDER BY latest_time DESC 
LIMIT 10;
"
```

**Check for API errors:**
```bash
docker logs crypto-ls-data-updater | grep -i "failed\|error\|429\|rate limit"
```

## Performance Monitoring

### Container Resource Limits

Check if containers are hitting resource limits:
```bash
docker stats --no-stream
```

### Database Size

```bash
docker exec -it crypto-ls-postgres psql -U crypto -d cryptols -c "
SELECT 
    pg_size_pretty(pg_database_size('cryptols')) as database_size,
    pg_size_pretty(pg_total_relation_size('ohlcv')) as ohlcv_table_size,
    (SELECT COUNT(*) FROM ohlcv) as total_rows;
"
```

### Data Collection Rate

```bash
# Count rows collected in last hour
docker exec -it crypto-ls-postgres psql -U crypto -d cryptols -c "
SELECT 
    symbol,
    COUNT(*) as rows_last_hour,
    MIN(to_timestamp(open_time/1000)) as earliest,
    MAX(to_timestamp(open_time/1000)) as latest
FROM ohlcv
WHERE open_time > EXTRACT(EPOCH FROM NOW() - INTERVAL '1 hour') * 1000
GROUP BY symbol
ORDER BY rows_last_hour DESC;
"
```

## Alerts and Notifications

### Set Up Log Monitoring

For production, consider setting up log aggregation:

```bash
# Example: Send logs to file
docker logs -f crypto-ls-data-updater >> /var/log/crypto-ls-updater.log 2>&1

# Example: Monitor for errors
docker logs -f crypto-ls-data-updater | grep --line-buffered -i error | while read line; do
    echo "ERROR DETECTED: $line"
    # Add notification logic here
done
```

### Health Check Script

Create a simple health check script:

```bash
#!/bin/bash
# health_check.sh

if ! docker ps | grep -q crypto-ls-data-updater; then
    echo "ERROR: data-updater container is not running"
    exit 1
fi

if ! docker ps | grep -q crypto-ls-postgres; then
    echo "ERROR: postgres container is not running"
    exit 1
fi

echo "OK: All services running"
exit 0
```

## pgAdmin Web Interface

Access the web GUI for database management:

- **URL:** http://localhost:5050
- **Email:** admin@example.com
- **Password:** admin

### Connect to Database in pgAdmin

1. Right-click **Servers** → **Register** → **Server**
2. **General** tab: Name = `cryptols`
3. **Connection** tab:
   - **Host:** `postgres` (Docker service name)
   - **Port:** `5432`
   - **Username:** `crypto`
   - **Password:** `crypto`
4. **Save**

## Useful Commands Summary

```bash
# Status
docker compose ps
docker stats --no-stream

# Logs
docker logs -f crypto-ls-data-updater
docker logs crypto-ls-postgres

# Management
docker compose up -d
docker compose restart data-updater
docker compose stop data-updater
docker compose down

# Database
docker exec -it crypto-ls-postgres psql -U crypto -d cryptols
docker exec crypto-ls-postgres pg_isready -U crypto -d cryptols

# Troubleshooting
docker logs crypto-ls-data-updater
docker inspect crypto-ls-data-updater
docker compose ps -a
```
