# Documentation Restructure Plan

## Proposed Structure

```
docs/
├── README.md                          # Main documentation index
├── ARCHITECTURE.md                    # System architecture (reference)
├── external-data-sources.md           # External data sources reference
│
├── operations/                        # Operations Manuals (HOW TO USE/MAINTAIN)
│   ├── README.md                      # Operations index
│   ├── docker-setup.md                # Docker setup and management
│   ├── monitoring.md                  # Monitoring and troubleshooting
│   ├── data-integrity.md              # Data integrity operations
│   ├── booking-and-recon.md           # Booking and reconciliation ops
│   ├── api-keys-setup.md              # API keys setup
│   ├── sop-add-new-data-table.md      # SOP for adding data tables
│   │
│   └── gui/                           # GUI Tools Manuals
│       ├── README.md                  # GUI tools index
│       ├── redisinsight-usage-manual.md
│       └── redis-gui-setup.md
│
├── implementation/                    # Implementation Progress (WHAT WAS DONE/IN PROGRESS)
│   ├── README.md                      # Implementation index
│   │
│   ├── booking-system/                # Booking System Implementation
│   │   ├── summary.md                 # Implementation summary
│   │
│   ├── redis-migration/               # Redis Migration Implementation
│   │   ├── summary.md                 # Migration summary
│   │   ├── phase1-infrastructure.md   # Phase 1 completion
│   │   └── phase1-test-results.md     # Phase 1 test results
│   │
│   └── resources/                     # Resource Estimates
│       └── redis-architecture-resources.md
│
└── plans/                             # Plans & Architecture (FUTURE/REFERENCE)
    ├── README.md                      # Plans index
    │
    ├── architecture/                  # Architecture Designs (Reference)
    │   ├── order-booking-services-architecture.md
    │   └── booking-system-and-recon.md
    │
    ├── migration/                     # Migration Plans
    │   └── redis-migration-plan.md
    │
    ├── features/                      # Feature Plans (Future)
    │   ├── feature-processing-layer.md
    │   ├── futures-market-data-collection.md
    │   └── multi-factor-long-short-strategy.md
    │
    └── checklists/                    # Implementation Checklists
        └── order-booking-services-checklist.md
```

## File Moves

### Operations → Implementation

1. `operations/booking-system-implementation-summary.md` → `implementation/booking-system/summary.md`
2. `operations/order-booking-services-summary.md` → `implementation/redis-migration/summary.md`
3. `operations/phase1-infrastructure-setup-complete.md` → `implementation/redis-migration/phase1-infrastructure.md`
4. `operations/phase1-redis-connectivity-test-results.md` → `implementation/redis-migration/phase1-test-results.md`
5. `operations/resource-estimation-new-architecture.md` → `implementation/resources/redis-architecture-resources.md`

### Operations → Operations/GUI

6. `operations/redisinsight-usage-manual.md` → `operations/gui/redisinsight-usage-manual.md`
7. `operations/redis-gui-setup.md` → `operations/gui/redis-gui-setup.md`

### Plans → Plans/Architecture

8. `plans/order-booking-services-architecture.md` → `plans/architecture/order-booking-services-architecture.md`
9. `plans/booking-system-and-recon.md` → `plans/architecture/booking-system-and-recon.md`

### Plans → Plans/Migration

10. `plans/redis-migration-plan.md` → `plans/migration/redis-migration-plan.md`

### Plans → Plans/Features

11. `plans/feature-processing-layer.md` → `plans/features/feature-processing-layer.md`
12. `plans/futures-market-data-collection.md` → `plans/features/futures-market-data-collection.md`
13. `plans/multi-factor-long-short-strategy.md` → `plans/features/multi-factor-long-short-strategy.md`

### Plans → Plans/Checklists

14. `plans/order-booking-services-implementation-checklist.md` → `plans/checklists/order-booking-services-checklist.md`

## New READMEs to Create

1. `docs/implementation/README.md`
2. `docs/implementation/booking-system/README.md` (optional)
3. `docs/implementation/redis-migration/README.md` (optional)
4. `docs/operations/gui/README.md`
5. `docs/plans/README.md`
6. `docs/plans/architecture/README.md` (optional)
7. `docs/plans/migration/README.md` (optional)
8. `docs/plans/features/README.md` (optional)
9. `docs/plans/checklists/README.md` (optional)

## Benefits

1. **Clear Separation:**
   - **Operations** = How to use/maintain the system
   - **Implementation** = What has been implemented and progress
   - **Plans** = Future work, architecture, and reference docs

2. **Better Organization:**
   - Related documents grouped together
   - Easy to find what you need
   - Clear purpose for each directory

3. **Scalability:**
   - Easy to add new features/implementations
   - Clear structure for new team members
   - Better maintenance

4. **Audience Clarity:**
   - Operators → `operations/`
   - Developers → `implementation/`
   - Architects/Planners → `plans/`
