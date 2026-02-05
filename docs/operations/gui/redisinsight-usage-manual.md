# RedisInsight GUI Usage Manual

## Table of Contents

1. [Getting Started](#getting-started)
2. [Connecting to Redis](#connecting-to-redis)
3. [Browser - Key Management](#browser---key-management)
4. [CLI - Command Execution](#cli---command-execution)
5. [Profiler - Performance Monitoring](#profiler---performance-monitoring)
6. [Analysis - Database Insights](#analysis---database-insights)
7. [Redis Streams Management](#redis-streams-management)
8. [Common Operations](#common-operations)
9. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Accessing RedisInsight

1. **Start RedisInsight:**
   ```bash
   docker compose up -d redis redisinsight
   ```

2. **Open Browser:**
   - URL: http://localhost:5540
   - Wait 30-60 seconds for initialization

3. **First Launch:**
   - You'll see a welcome screen
   - Click "Add Redis Database" or "Connect to Redis"

---

## Connecting to Redis

### Connection Settings

**For Docker Network (Recommended):**
- **Host:** `redis` (Docker service name)
- **Port:** `6379`
- **Database Alias:** `Crypto-LS Redis`
- **Username:** (leave empty)
- **Password:** (leave empty)

**For Host Machine:**
- **Host:** `localhost`
- **Port:** `6379`
- **Database Alias:** `Crypto-LS Redis`
- **Username:** (leave empty)
- **Password:** (leave empty)

### Adding Multiple Connections

You can add multiple Redis instances:
1. Click "Add Redis Database" button
2. Enter connection details
3. Each connection appears in the sidebar

### Testing Connection

After adding a connection:
- Click on the database name in the sidebar
- If connected successfully, you'll see the database overview
- If connection fails, check:
  - Redis is running: `docker compose ps redis`
  - Port 6379 is accessible
  - No firewall blocking

---

## Browser - Key Management

### Viewing Keys

1. **Navigate to Browser:**
   - Click on your Redis database
   - Click "Browser" tab (left sidebar)

2. **Key List:**
   - All keys displayed in a table
   - Shows: Key name, Type, TTL, Size
   - Default view: First 100 keys

3. **Filtering Keys:**
   - Use search box at top
   - Supports pattern matching (e.g., `order:*`, `*USDT*`)
   - Filter by type: String, Hash, List, Set, Sorted Set, Stream

### Key Operations

#### View Key Value
- Click on any key to view its value
- For complex types (Hash, List), see structured view

#### Edit Key Value
1. Click on key
2. Click "Edit" button
3. Modify value
4. Click "Save"

#### Delete Key
1. Select key(s) in list
2. Click "Delete" button (trash icon)
3. Confirm deletion

#### Add New Key
1. Click "Add Key" button
2. Enter key name
3. Select type (String, Hash, List, Set, Sorted Set)
4. Enter value
5. Set TTL (optional)
6. Click "Add"

#### Copy Key
1. Click on key
2. Click "Copy" button
3. Key name/value copied to clipboard

### Key Patterns

**Common Patterns:**
- `order:*` - All order keys
- `market_data:*` - All market data keys
- `*:BTCUSDT` - All keys ending with BTCUSDT
- `rate_limit:*` - All rate limit keys

---

## CLI - Command Execution

### Accessing CLI

1. Click on your Redis database
2. Click "CLI" tab (left sidebar)
3. Command prompt appears at bottom

### Features

- **Auto-complete:** Type command, press Tab for suggestions
- **Syntax Highlighting:** Commands and responses color-coded
- **Command History:** Use Up/Down arrows to navigate history
- **Multi-line Commands:** Press Shift+Enter for new line

### Common Commands

#### String Operations
```redis
# Set a value
SET mykey "myvalue"

# Get a value
GET mykey

# Set with expiration
SETEX mykey 60 "myvalue"  # Expires in 60 seconds

# Increment counter
INCR counter
```

#### Hash Operations
```redis
# Set hash field
HSET user:1 name "John" age 30

# Get hash field
HGET user:1 name

# Get all hash fields
HGETALL user:1
```

#### List Operations
```redis
# Add to list
LPUSH mylist "item1"
RPUSH mylist "item2"

# Get list range
LRANGE mylist 0 -1

# Get list length
LLEN mylist
```

#### Stream Operations (for Order Queue)
```redis
# Add message to stream
XADD order_stream * symbol BTCUSDT side BUY quantity 0.001

# Read messages from stream
XREAD STREAMS order_stream 0

# Read with consumer group
XREADGROUP GROUP order_executors consumer1 STREAMS order_stream >
```

#### Key Management
```redis
# List all keys (use with caution)
KEYS *

# List keys with pattern
KEYS order:*

# Check if key exists
EXISTS mykey

# Get key TTL
TTL mykey

# Delete key
DEL mykey

# Delete multiple keys
DEL key1 key2 key3
```

#### Information Commands
```redis
# Get Redis info
INFO server
INFO memory
INFO stats

# Get database size
DBSIZE

# Get key type
TYPE mykey
```

### Executing Commands

1. Type command in CLI prompt
2. Press Enter to execute
3. Response appears below command
4. Errors shown in red

### Tips

- Use `KEYS *` sparingly (slow on large databases)
- Use `SCAN` for iterating keys (safer)
- Check command syntax with auto-complete
- Use `HELP <command>` for command help

---

## Profiler - Performance Monitoring

### Accessing Profiler

1. Click on your Redis database
2. Click "Profiler" tab (left sidebar)
3. Click "Start Profiler" button

### Features

- **Real-time Monitoring:** See commands as they execute
- **Command Details:** Command, arguments, execution time
- **Slow Commands:** Identify performance bottlenecks
- **Filtering:** Filter by command type, execution time

### Using Profiler

#### Start Profiling
1. Click "Start Profiler"
2. Commands appear in real-time
3. See command, client, execution time

#### Analyze Results
- **Slow Commands:** Commands taking > 1ms highlighted
- **Command Frequency:** See which commands run most
- **Client Info:** See which clients execute commands

#### Stop Profiling
- Click "Stop Profiler" button
- Results remain visible until cleared

### Use Cases

- **Debug Slow Queries:** Find commands taking too long
- **Monitor Order Processing:** Watch order_stream commands
- **Performance Tuning:** Identify optimization opportunities

---

## Analysis - Database Insights

### Accessing Analysis

1. Click on your Redis database
2. Click "Analysis" tab (left sidebar)
3. Click "Run Analysis" button

### Reports Available

#### Memory Analysis
- **Total Memory:** Current memory usage
- **Memory by Key Type:** Breakdown by data type
- **Largest Keys:** Keys using most memory
- **Key Patterns:** Memory usage by key pattern

#### Key Statistics
- **Total Keys:** Number of keys in database
- **Keys by Type:** Count by data type
- **Key Distribution:** Keys per pattern

#### Performance Metrics
- **Hit Rate:** Cache hit/miss ratio
- **Evictions:** Keys evicted (if maxmemory reached)
- **Commands/sec:** Throughput metrics

### Using Analysis

1. **Run Analysis:**
   - Click "Run Analysis"
   - Wait for analysis to complete (may take time)

2. **View Reports:**
   - Memory report
   - Key statistics
   - Performance metrics

3. **Export Results:**
   - Click "Export" to download report
   - Useful for documentation

### Optimization Tips

- **Large Keys:** Consider splitting into smaller keys
- **High Memory:** Review maxmemory policy
- **Many Keys:** Consider key expiration (TTL)
- **Slow Commands:** Optimize queries or use indexes

---

## Redis Streams Management

### Viewing Streams

1. Navigate to Browser
2. Filter by type: "Stream"
3. Click on stream name (e.g., `order_stream`)

### Stream Operations

#### View Stream Messages
1. Click on stream
2. See messages in chronological order
3. Each message shows:
   - Message ID
   - Fields (key-value pairs)
   - Timestamp

#### Add Message to Stream
1. Click "Add Message" button
2. Enter field name-value pairs
3. Click "Add"
   - Or use CLI: `XADD order_stream * field1 value1 field2 value2`

#### Read Messages
- **From Beginning:** `XREAD STREAMS order_stream 0`
- **New Messages:** `XREAD STREAMS order_stream $`
- **Consumer Group:** `XREADGROUP GROUP order_executors consumer1 STREAMS order_stream >`

#### Consumer Groups
1. View consumer groups for stream
2. See pending messages
3. Monitor consumer lag

### Order Stream Example

**View Order Stream:**
```redis
# In Browser, filter for "order_stream"
# Or in CLI:
XREAD STREAMS order_stream 0
```

**Add Test Order:**
```redis
XADD order_stream * symbol BTCUSDT side BUY quantity 0.001 order_type MARKET book_id default
```

**Read Orders:**
```redis
XREADGROUP GROUP order_executors executor1 STREAMS order_stream >
```

---

## Common Operations

### Monitoring Order Queue

1. **View Order Stream:**
   - Browser → Filter: `order_stream`
   - See pending orders

2. **Check Queue Depth:**
   ```redis
   XLEN order_stream
   ```

3. **Monitor Processing:**
   - Profiler → Watch XREADGROUP commands
   - See order processing in real-time

### Checking Cache

1. **View Market Data Cache:**
   - Browser → Filter: `market_data:*`
   - See cached OHLCV bars

2. **Check Cache Hit Rate:**
   - Analysis → Performance Metrics
   - View cache statistics

### Rate Limiting Monitoring

1. **View Rate Limit Counters:**
   - Browser → Filter: `rate_limit:*`
   - See current counters

2. **Check Counter Values:**
   ```redis
   GET rate_limit:binance:orders
   ```

### Debugging

1. **Check Redis Logs:**
   ```bash
   docker compose logs redis
   ```

2. **Monitor Commands:**
   - Profiler → Start Profiler
   - See all commands in real-time

3. **Check Memory:**
   - Analysis → Memory Report
   - Identify memory issues

---

## Troubleshooting

### Connection Issues

**Problem:** Can't connect to Redis

**Solutions:**
1. Verify Redis is running:
   ```bash
   docker compose ps redis
   ```

2. Check Redis logs:
   ```bash
   docker compose logs redis
   ```

3. Test connection from CLI:
   ```bash
   docker compose exec redis redis-cli ping
   ```

4. Try different host:
   - Use `redis` (Docker network)
   - Use `localhost` (host machine)

### Performance Issues

**Problem:** RedisInsight is slow

**Solutions:**
1. Reduce key count in view (use filters)
2. Use SCAN instead of KEYS
3. Check Redis memory usage
4. Restart RedisInsight:
   ```bash
   docker compose restart redisinsight
   ```

### Missing Keys

**Problem:** Keys not showing in Browser

**Solutions:**
1. Check if keys exist:
   ```redis
   EXISTS mykey
   KEYS mykey*
   ```

2. Clear filters in Browser
3. Refresh view (F5)
4. Check key TTL (may have expired)

### Stream Issues

**Problem:** Can't read from stream

**Solutions:**
1. Verify stream exists:
   ```redis
   EXISTS order_stream
   TYPE order_stream
   ```

2. Check stream length:
   ```redis
   XLEN order_stream
   ```

3. Verify consumer group exists:
   ```redis
   XINFO GROUPS order_stream
   ```

### Memory Issues

**Problem:** Redis out of memory

**Solutions:**
1. Check memory usage:
   ```redis
   INFO memory
   ```

2. Review large keys:
   - Analysis → Largest Keys

3. Check eviction policy:
   ```redis
   CONFIG GET maxmemory-policy
   ```

4. Clear old keys:
   - Browser → Filter old keys → Delete

---

## Keyboard Shortcuts

- **Ctrl+K / Cmd+K:** Focus command line
- **Ctrl+L / Cmd+L:** Clear console
- **Up/Down Arrow:** Navigate command history
- **Tab:** Auto-complete command
- **Esc:** Cancel current operation

---

## Best Practices

1. **Use Filters:** Don't load all keys at once
2. **Monitor Performance:** Use Profiler regularly
3. **Regular Analysis:** Run analysis weekly
4. **Backup Important Data:** Export before major changes
5. **Test Commands:** Use CLI for testing before production
6. **Watch Memory:** Monitor memory usage regularly
7. **Use Patterns:** Leverage key patterns for organization

---

## Additional Resources

- **Redis Documentation:** https://redis.io/docs/
- **RedisInsight Docs:** https://redis.io/docs/latest/integrate/redisinsight/
- **Redis Commands:** https://redis.io/commands/
- **Redis Streams:** https://redis.io/docs/data-types/streams/

---

## Quick Reference

### Common Redis Commands

```redis
# Connection
PING                    # Test connection
INFO                    # Server information

# Keys
KEYS pattern           # List keys (use SCAN for production)
EXISTS key             # Check if key exists
DEL key                # Delete key
TTL key                # Get time to live
TYPE key               # Get key type

# Strings
SET key value          # Set value
GET key                # Get value
INCR key               # Increment counter

# Streams
XADD stream * field value    # Add message
XREAD STREAMS stream 0      # Read messages
XLEN stream                 # Stream length
XINFO STREAM stream         # Stream info

# Info
INFO memory            # Memory statistics
INFO stats             # Statistics
DBSIZE                 # Database size
```

### RedisInsight Navigation

- **Browser:** Key management and viewing
- **CLI:** Command execution
- **Profiler:** Performance monitoring
- **Analysis:** Database insights
- **Settings:** Connection management

---

**Last Updated:** 2025-02-02  
**Version:** 1.0
