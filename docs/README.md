# Documentation

This directory contains all project documentation organized by category.

## Directory Structure

```
docs/
├── README.md           # This file
├── ARCHITECTURE.md     # System architecture and data flow
└── operations/         # Operation manuals and guides
    ├── README.md       # Operations index
    ├── docker-setup.md # Docker services setup guide
    ├── monitoring.md   # Monitoring and troubleshooting guide
    └── data-integrity.md # Data integrity framework
```

## Documentation Categories

### Architecture (`ARCHITECTURE.md`)

Comprehensive system overview:
- **Services** - Docker services and their roles
- **Database** - Schema and data structure
- **Data Flow** - How data moves through the system
- **Module Architecture** - Code organization and dependencies
- **Operations Flow** - Startup, normal operation, error handling
- **Configuration** - Environment variables and settings

### Operations Manuals (`operations/`)

Practical guides for day-to-day operations:
- **Docker Setup** - Setting up and managing Docker services
- **Monitoring** - Monitoring, troubleshooting, and maintenance
- **Data Integrity** - Running integrity checks and interpreting results

See [Operations Manuals](operations/README.md) for details.

## Other Documentation

Additional documentation located in the project:
- **reports/README.md** - Data integrity reports documentation
- **viz/README.md** - Streamlit visualization documentation

## Contributing

When adding new documentation:
1. Place operation manuals in `docs/operations/`
2. Place framework/architecture docs in `docs/` root or appropriate subdirectory
3. Update relevant README files with links
4. Follow existing markdown formatting conventions
