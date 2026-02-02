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

### [Data Integrity](data-integrity.md)
Data integrity checking framework and operations guide:
- Running integrity checks
- Missing bars detection
- Report interpretation
- Scheduling checks
- Monitoring and alerts
- Extending the framework
- Troubleshooting

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
