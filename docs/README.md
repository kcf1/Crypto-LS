# Documentation

This directory contains all project documentation organized by category.

## Directory Structure

```
docs/
├── README.md                    # This file
├── ARCHITECTURE.md              # System architecture and data flow
│
├── operations/                  # Operations Manuals (HOW TO USE/MAINTAIN)
│   ├── README.md               # Operations index
│   ├── docker-setup.md         # Docker services setup guide
│   ├── monitoring.md           # Monitoring and troubleshooting guide
│   ├── data-integrity.md       # Data integrity framework
│   └── gui/                     # GUI Tools Manuals
│       └── redisinsight-usage-manual.md
│
├── implementation/              # Implementation Progress (WHAT WAS DONE)
│   ├── README.md               # Implementation index
│   ├── booking-system/         # Booking system implementation
│   ├── redis-migration/        # Redis migration progress
│   └── resources/              # Resource estimates
│
└── plans/                       # Plans & Architecture (FUTURE/REFERENCE)
    ├── README.md               # Plans index
    ├── architecture/           # Architecture designs
    ├── migration/              # Migration plans
    ├── features/               # Feature plans
    └── checklists/             # Implementation checklists
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

**Purpose:** How to use, maintain, and troubleshoot the system

Practical guides for day-to-day operations:
- **Docker Setup** - Setting up and managing Docker services
- **Monitoring** - Monitoring, troubleshooting, and maintenance
- **Data Integrity** - Running integrity checks and interpreting results
- **GUI Tools** - RedisInsight and other GUI tools

See [Operations Manuals](operations/README.md) for details.

### Implementation Progress (`implementation/`)

**Purpose:** Track what has been implemented and in-progress work

Documentation about completed implementations:
- **Booking System** - Implementation summary and progress
- **Redis Migration** - Phase completion and test results
- **Resources** - Resource estimates for implemented features

See [Implementation Documentation](implementation/README.md) for details.

### Plans & Architecture (`plans/`)

**Purpose:** Future plans, architecture designs, and reference documentation

- **Architecture** - System architecture designs (reference)
  - [Order & Booking Services Architecture](plans/architecture/order-booking-services-architecture.md)
  - [Booking System & Reconciliations](plans/architecture/booking-system-and-recon.md)
- **Migration Plans** - Step-by-step migration guides
  - [Redis Migration Plan](plans/migration/redis-migration-plan.md)
- **Feature Plans** - Future feature specifications
  - [Futures Market Data Collection](plans/features/futures-market-data-collection.md)
  - [Feature Processing Layer](plans/features/feature-processing-layer.md)
  - [Multi-Factor Long-Short Strategy](plans/features/multi-factor-long-short-strategy.md)
- **Checklists** - Implementation checklists and templates

See [Plans & Architecture](plans/README.md) for details.

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
