# Operations Manuals

This directory contains operation manuals and guides for managing and maintaining the Crypto-LS system.

## Available Manuals

### [Docker Setup](docker-setup.md)
Complete guide for setting up and managing Docker services:
- PostgreSQL database setup
- Data updater service configuration
- pgAdmin web interface
- Service management commands
- Database migrations

### [Monitoring](monitoring.md)
Comprehensive monitoring and troubleshooting guide:
- Service status checks
- Data updater monitoring
- Database monitoring
- Log viewing and analysis
- Performance monitoring
- Troubleshooting common issues
- Health checks and alerts

### [Booking & Reconciliation](booking-and-recon.md) **[WIP]**
Booking system and reconciliation operations (planned):
- No separate balance-monitoring service; ledger updated from booked trades only
- Fill-sync job (periodic and/or after each order); reconciliation job (e.g. daily)
- See [Booking System & Reconciliations Plan](../plans/booking-system-and-recon.md) for full design

### [Data Integrity](data-integrity.md)
Data integrity checking framework and operations guide:
- Running integrity checks
- Missing bars detection
- Report interpretation
- Scheduling checks
- Monitoring and alerts
- Extending the framework
- Troubleshooting

### [SOP: Adding New Data Table](sop-add-new-data-table.md)
Standard Operating Procedure for adding new data collection tables:
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
docker logs -f crypto-ls-data-updater
```

### Stop Services
```bash
docker compose down
```

## Related Documentation

- [Data Integrity](data-integrity.md) - Data quality checks and integrity framework (this directory)
- [Reports README](../../reports/README.md) - Data integrity reports documentation

## Contributing

When adding new operation manuals:
1. Place them in this directory
2. Update this README with a link and brief description
3. Follow the existing markdown format and structure
