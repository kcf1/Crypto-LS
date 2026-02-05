# Plans & Architecture Documentation

This directory contains **future plans**, **architecture designs**, and **reference documentation** for the Crypto-LS system.

## Purpose

This directory contains:
- Architecture designs (reference documentation)
- Migration plans (future work)
- Feature plans (future features)
- Implementation checklists (templates/guides)

**Note:** This is different from:
- **`../operations/`** - How to use/maintain the system (operations manuals)
- **`../implementation/`** - What has been implemented (implementation progress)

## Structure

```
plans/
├── architecture/          # Architecture Designs (Reference)
│   ├── order-booking-services-architecture.md
│   └── booking-system-and-recon.md
│
├── migration/             # Migration Plans
│   └── redis-migration-plan.md
│
├── features/              # Feature Plans (Future)
│   ├── feature-processing-layer.md
│   ├── futures-market-data-collection.md
│   └── multi-factor-long-short-strategy.md
│
└── checklists/            # Implementation Checklists
    └── order-booking-services-checklist.md
```

## Documentation Categories

### Architecture (`architecture/`)

Reference documentation for system architecture and design:

- **[Order & Booking Services Architecture](architecture/order-booking-services-architecture.md)**
  - Complete architecture for order execution and booking services
  - Service components and responsibilities
  - Data flow diagrams
  - Manual operations guide

- **[Booking System & Reconciliations](architecture/booking-system-and-recon.md)**
  - Booking system design
  - Reconciliation workflows

### Migration Plans (`migration/`)

Step-by-step migration plans:

- **[Redis Migration Plan](migration/redis-migration-plan.md)**
  - Phase-by-phase migration plan
  - Tasks, validation, rollback procedures
  - Testing strategy

### Feature Plans (`features/`)

Future feature plans and specifications:

- **[Feature Processing Layer](features/feature-processing-layer.md)**
- **[Futures Market Data Collection](features/futures-market-data-collection.md)**
- **[Multi-Factor Long-Short Strategy](features/multi-factor-long-short-strategy.md)**

### Implementation Checklists (`checklists/`)

Templates and checklists for implementation:

- **[Order & Booking Services Checklist](checklists/order-booking-services-checklist.md)**
  - Detailed implementation checklist
  - File-by-file changes
  - Phase-by-phase implementation plan

## Using This Documentation

### For Architects
- Review architecture designs in `architecture/`
- Reference designs when planning new features

### For Developers
- Use migration plans in `migration/` for step-by-step guidance
- Follow implementation checklists in `checklists/`
- Reference architecture designs for understanding system design

### For Project Managers
- Review feature plans in `features/` for roadmap
- Track implementation progress using checklists

## Related Documentation

- **[Implementation Progress](../implementation/README.md)** - What has been implemented
- **[Operations Manuals](../operations/README.md)** - How to use/maintain the system
- **[System Architecture](../ARCHITECTURE.md)** - Overall system architecture
