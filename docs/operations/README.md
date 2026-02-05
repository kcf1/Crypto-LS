# Operations Manuals

This directory contains operation manuals and guides for managing and maintaining the Crypto-LS system.

**Purpose:** How to use, maintain, and troubleshoot the system

## Directory Structure

```
operations/
├── setup/              # Setup & Configuration
│   ├── docker-setup.md
│   └── api-keys-setup.md
│
├── monitoring/         # Monitoring & Maintenance
│   ├── monitoring.md
│   └── data-integrity.md
│
├── operations/         # Daily Operations
│   └── booking-and-recon.md
│
└── sops/              # Standard Operating Procedures
    └── sop-add-new-data-table.md
```

## Available Manuals

### Setup & Configuration (`setup/`)

**Initial setup and configuration guides:**

- **[Docker Setup](setup/docker-setup.md)**
  - PostgreSQL database setup
  - Data updater service configuration
  - pgAdmin web interface
  - Service management commands
  - Database migrations

- **[API Keys Setup](setup/api-keys-setup.md)**
  - Binance API keys configuration
  - Separate keys for data collection vs trading
  - Testnet setup

### Monitoring & Maintenance (`monitoring/`)

**Monitoring, troubleshooting, and maintenance:**

- **[Monitoring](monitoring/monitoring.md)**
  - Service status checks
  - Data updater monitoring
  - Database monitoring
  - Log viewing and analysis
  - Performance monitoring
  - Troubleshooting common issues
  - Health checks and alerts

- **[Data Integrity](monitoring/data-integrity.md)**
  - Running integrity checks
  - Missing bars detection
  - Report interpretation
  - Scheduling checks
  - Monitoring and alerts
  - Extending the framework
  - Troubleshooting

- **[RedisInsight GUI](monitoring/redis-gui-setup.md)**
  - RedisInsight setup and access
  - Connecting to Redis
  - Basic usage

- **[RedisInsight Usage Manual](monitoring/redisinsight-usage-manual.md)**
  - Comprehensive RedisInsight guide
  - Browser - Key management
  - CLI - Command execution
  - Profiler - Performance monitoring
  - Analysis - Database insights
  - Streams management
  - Common operations
  - Troubleshooting

### Daily Operations (`operations/`)

**Day-to-day operational procedures:**

- **[Booking & Reconciliation](operations/booking-and-recon.md)** **[WIP]**
  - Booking system operations
  - Reconciliation procedures
  - Manual override and adjustments
  - See [Booking System Architecture](../../plans/architecture/booking-system-and-recon.md) for full design

### Standard Operating Procedures (`sops/`)

**SOPs for common tasks:**

- **[SOP: Adding New Data Table](sops/sop-add-new-data-table.md)**
  - Planning and design
  - Database migration
  - Collector and storage methods
  - Update tasks and backfill scripts
  - Testing and verification
  - Service updates
  - Complete checklist


## Quick Reference

### Start Services
```bash
docker compose up -d
```

### Check Status
```bash
docker compose ps
```

### View Logs
```bash
docker compose logs -f crypto-ls-data-updater
```

### Stop Services
```bash
docker compose down
```

## Related Documentation

- **[Implementation Progress](../implementation/README.md)** - What has been implemented
- **[Plans & Architecture](../plans/README.md)** - Future plans and architecture designs
- **[System Architecture](../ARCHITECTURE.md)** - Overall system architecture
- **[Reports README](../../reports/README.md)** - Data integrity reports documentation

## Contributing

When adding new operation manuals:

1. Place them in the appropriate subdirectory:
   - Setup guides → `setup/`
   - Monitoring guides → `monitoring/`
   - Daily operations → `operations/`
   - SOPs → `sops/`
   - GUI tools → `gui/`
2. Update this README with a link and brief description
3. Follow the existing markdown format and structure
