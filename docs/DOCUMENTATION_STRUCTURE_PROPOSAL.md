# Documentation Structure Proposal

## Current Issues

1. **Operations directory** mixes:
   - Operations manuals (how to use/maintain)
   - Implementation summaries (what was done)
   - Phase completion docs (implementation progress)
   - Resource estimates (planning docs)

2. **Plans directory** mixes:
   - Architecture designs (reference docs)
   - Implementation checklists (implementation docs)
   - Migration plans (implementation docs)
   - Feature plans (future plans)

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
│   │   └── phase-completion/          # Phase completion docs
│   │
│   ├── redis-migration/               # Redis Migration Implementation
│   │   ├── summary.md                 # Migration summary
│   │   ├── phase1-infrastructure.md    # Phase 1 completion
│   │   ├── phase1-test-results.md      # Phase 1 test results
│   │   └── phase-completion/          # Future phase docs
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

## Directory Purposes

### `/operations/` - Operations Manuals
**Purpose:** How to use, maintain, and troubleshoot the system
**Content:**
- Setup guides
- Daily operations
- Monitoring procedures
- Troubleshooting guides
- GUI usage manuals
- SOPs (Standard Operating Procedures)

**Audience:** Operators, DevOps, Support

### `/implementation/` - Implementation Progress
**Purpose:** Track what has been implemented and in-progress work
**Content:**
- Implementation summaries
- Phase completion documents
- Test results
- Resource estimates (for implemented features)
- Progress tracking

**Audience:** Developers, Project Managers

### `/plans/` - Plans & Architecture
**Purpose:** Future plans, architecture designs, and reference documentation
**Content:**
- Architecture designs (reference)
- Migration plans (future work)
- Feature plans (future features)
- Implementation checklists (templates/guides)

**Audience:** Architects, Developers, Stakeholders

## Migration Plan

### Step 1: Create New Structure
1. Create `docs/implementation/` directory
2. Create `docs/implementation/booking-system/`
3. Create `docs/implementation/redis-migration/`
4. Create `docs/implementation/resources/`
5. Create `docs/plans/architecture/`
6. Create `docs/plans/migration/`
7. Create `docs/plans/features/`
8. Create `docs/plans/checklists/`
9. Create `docs/operations/gui/`

### Step 2: Move Files

**From `docs/operations/` to `docs/implementation/booking-system/`:**
- `booking-system-implementation-summary.md` → `summary.md`
- `order-booking-services-summary.md` → (merge into summary or keep separate)

**From `docs/operations/` to `docs/implementation/redis-migration/`:**
- `phase1-infrastructure-setup-complete.md` → `phase1-infrastructure.md`
- `phase1-redis-connectivity-test-results.md` → `phase1-test-results.md`
- `order-booking-services-summary.md` → `summary.md` (if Redis-related)

**From `docs/operations/` to `docs/implementation/resources/`:**
- `resource-estimation-new-architecture.md` → `redis-architecture-resources.md`

**From `docs/operations/` to `docs/operations/gui/`:**
- `redisinsight-usage-manual.md`
- `redis-gui-setup.md`

**From `docs/plans/` to `docs/plans/architecture/`:**
- `order-booking-services-architecture.md`
- `booking-system-and-recon.md`

**From `docs/plans/` to `docs/plans/migration/`:**
- `redis-migration-plan.md`

**From `docs/plans/` to `docs/plans/features/`:**
- `feature-processing-layer.md`
- `futures-market-data-collection.md`
- `multi-factor-long-short-strategy.md`

**From `docs/plans/` to `docs/plans/checklists/`:**
- `order-booking-services-implementation-checklist.md` → `order-booking-services-checklist.md`

### Step 3: Update READMEs
- Update `docs/operations/README.md`
- Create `docs/implementation/README.md`
- Update `docs/plans/README.md` (create if doesn't exist)
- Create `docs/operations/gui/README.md`

### Step 4: Update Cross-References
- Update links in all moved files
- Update links in `docs/ARCHITECTURE.md`
- Update links in main `docs/README.md`

## Benefits

1. **Clear Separation:**
   - Operations = How to use/maintain
   - Implementation = What was done/progress
   - Plans = Future work/reference

2. **Better Organization:**
   - Related docs grouped together
   - Easy to find what you need
   - Clear purpose for each directory

3. **Scalability:**
   - Easy to add new features/implementations
   - Clear structure for new team members
   - Better maintenance

4. **Audience Clarity:**
   - Operators know where to look
   - Developers know where to document
   - Architects know where to plan

## Alternative Structure (Simpler)

If the above is too complex, a simpler version:

```
docs/
├── operations/           # Operations Manuals (HOW TO)
│   ├── gui/             # GUI tools
│   └── ...              # Other ops manuals
│
├── implementation/       # Implementation Progress (WHAT WAS DONE)
│   ├── booking-system/
│   ├── redis-migration/
│   └── resources/
│
└── plans/               # Plans & Architecture (FUTURE/REFERENCE)
    ├── architecture/    # Architecture designs
    ├── migrations/      # Migration plans
    ├── features/       # Feature plans
    └── checklists/     # Implementation checklists
```

This keeps the same separation but with fewer nested directories.
