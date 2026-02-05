# Redis GUI Setup - RedisInsight

## Overview

RedisInsight is the official Redis GUI tool, similar to pgAdmin for PostgreSQL. It provides a web-based interface for managing and monitoring Redis.

## Features

- **Visual Data Browser** - Browse, filter, and visualize Redis keys and data structures
- **Real-time Command Profiler** - Analyze every command sent to Redis
- **Advanced CLI** - Intelligent auto-complete and syntax highlighting
- **Database Analysis** - Optimize performance and memory usage
- **AI-powered Redis Copilot** - Assistant for Redis operations
- **Support for Redis Modules** - RedisSearch, RedisJSON, RedisGraph, etc.

## Setup

RedisInsight has been added to `docker-compose.yml` and is configured to connect to the Redis service.

### Start RedisInsight

```bash
# Start Redis and RedisInsight
docker compose up -d redis redisinsight

# Or start all services
docker compose up -d
```

### Access RedisInsight

1. Open your browser and go to: **http://localhost:5540**
2. On first launch, you'll see a welcome screen
3. Click "Add Redis Database" or "Connect to Redis"
4. Enter connection details:
   - **Host:** `redis` (Docker service name) or `localhost` (from host)
   - **Port:** `6379`
   - **Database Alias:** `Crypto-LS Redis` (or any name you prefer)
   - **Username:** (leave empty, Redis doesn't use auth by default)
   - **Password:** (leave empty, Redis doesn't use auth by default)

### Alternative: Connect from Host Machine

If connecting from your host machine (not Docker network):
- **Host:** `localhost`
- **Port:** `6379`

## Usage

### Browse Keys

1. Click on your Redis database connection
2. Navigate to "Browser" tab
3. View all keys, filter by pattern, or search

### Execute Commands

1. Go to "CLI" tab
2. Type Redis commands (e.g., `KEYS *`, `GET mykey`)
3. Use auto-complete for command suggestions

### Monitor Performance

1. Go to "Profiler" tab
2. See real-time command execution
3. Analyze slow commands and performance

### Database Analysis

1. Go to "Analysis" tab
2. View memory usage, key patterns
3. Get optimization recommendations

## Resource Usage

- **Memory:** 512 MB limit
- **CPU:** 0.5 cores limit
- **Port:** 5540 (mapped to host)

## Stopping RedisInsight

```bash
# Stop RedisInsight (Redis continues running)
docker compose stop redisinsight

# Start again when needed
docker compose start redisinsight
```

## Alternative: Redis Commander (Lightweight Option)

If you prefer a lighter-weight option, you can use Redis Commander instead:

```yaml
redis-commander:
  image: rediscommander/redis-commander:latest
  container_name: crypto-ls-redis-commander
  environment:
    REDIS_HOSTS: local:redis:6379
  ports:
    - "8081:8081"
  depends_on:
    - redis
  restart: unless-stopped
```

Access at: http://localhost:8081

## Notes

- RedisInsight stores its configuration in a Docker volume (`redisinsight_data`)
- Your Redis connections and settings persist across container restarts
- RedisInsight is optional - Redis can be used via CLI or programmatically without it
- Similar to pgAdmin, you can run Redis without RedisInsight when not needed

## Troubleshooting

### Can't Connect to Redis

1. Verify Redis is running: `docker compose ps redis`
2. Check Redis logs: `docker compose logs redis`
3. Try connecting with host `localhost` instead of `redis`

### RedisInsight Won't Start

1. Check logs: `docker compose logs redisinsight`
2. Verify port 5540 is not in use: `netstat -an | findstr 5540` (Windows)
3. Check Docker resources: `docker stats redisinsight`

### Connection Timeout

- Make sure Redis service is healthy: `docker compose ps redis`
- Check if Redis is accessible: `docker compose exec redis redis-cli ping`
