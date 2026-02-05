# GUI Tools Manuals

This directory contains usage manuals for GUI tools used in the Crypto-LS system.

## Available GUI Tools

### RedisInsight

**Official Redis GUI** - Web-based interface for managing and monitoring Redis.

- **[Usage Manual](redisinsight-usage-manual.md)** - Comprehensive guide to using RedisInsight
  - Browser - Key management
  - CLI - Command execution
  - Profiler - Performance monitoring
  - Analysis - Database insights
  - Streams management
  - Common operations
  - Troubleshooting

- **[Setup Guide](redis-gui-setup.md)** - How to set up and access RedisInsight
  - Docker configuration
  - Connection setup
  - Basic usage

## Access

### RedisInsight
- **URL:** http://localhost:5540
- **Start:** `docker compose up -d redisinsight`
- **Stop:** `docker compose stop redisinsight`

## Related Documentation

- **[Operations Manuals](../README.md)** - Other operations guides
- **[Redis Migration Implementation](../../implementation/redis-migration/)** - Redis implementation progress
