# Add Record Status Columns to Orders, Trades, and Adjustments Tables

## Purpose

Add a `record_status` column to `orders`, `trades`, and `adjustments` tables to properly track data validity, allowing records to be marked as invalid, deleted, or cancelled without losing audit trail.

## Current State

- **Orders**: Has `status` field (NEW, PARTIALLY_FILLED, FILLED, CANCELLED) for order execution status
- **Trades**: No status field - currently using `notes` field to mark invalid trades (e.g., "[INVALID] Not found in Binance")
- **Adjustments**: No status field - transactional records that may need to be invalidated
- **Problem**: No clean way to filter invalid/deleted records in queries
- **Problem**: Reconciliation fix script marks invalid trades via notes, not a proper status field

## Schema Changes

### Orders Table
Added column:
- `record_status` TEXT NOT NULL DEFAULT 'VALID'

### Trades Table
Added column:
- `record_status` TEXT NOT NULL DEFAULT 'VALID'

### Adjustments Table
Added column:
- `record_status` TEXT NOT NULL DEFAULT 'VALID'

## Record Status Values

**For Orders:**
- `VALID` - Normal, valid order record (default)
- `CANCELLED` - Order was cancelled (redundant with `status='CANCELLED'` but useful for filtering)
- `INVALID` - Order doesn't exist on exchange (reconciliation issue)
- `DELETED` - Soft delete (order removed but kept for audit)

**For Trades:**
- `VALID` - Normal, valid trade record (default)
- `INVALID` - Trade doesn't exist on exchange (reconciliation issue)
- `DELETED` - Soft delete (trade removed but kept for audit)

**For Adjustments:**
- `VALID` - Normal, valid adjustment record (default)
- `INVALID` - Adjustment was made in error and should be ignored
- `DELETED` - Soft delete (adjustment removed but kept for audit)
- `CANCELLED` - Adjustment was cancelled

**Note**: `status` field in orders tracks execution status (NEW/FILLED/etc), while `record_status` tracks data validity/state.

## Migration Strategy

### Step 1: Create Alembic Migrations ✅
- ✅ Migration `ab1a5935976a`: Add `record_status` column to `orders` table (default: 'VALID')
- ✅ Migration `ab1a5935976a`: Add `record_status` column to `trades` table (default: 'VALID')
- ✅ Migration `415e7c6ce82e`: Add `record_status` column to `adjustments` table (default: 'VALID')
- ✅ Set existing records to 'VALID'
- ✅ Create indexes on `record_status` for all three tables (for filtering)

### Step 2: Update Ledger Methods ✅
- ✅ Update `record_order()` to accept optional `record_status` parameter
- ✅ Update `record_trade()` to accept optional `record_status` parameter
- ✅ Update `record_adjustment()` to accept optional `record_status` parameter
- ✅ Update `get_orders()` to filter by `record_status` (default: only VALID)
- ✅ Update `get_trades()` to filter by `record_status` (default: only VALID)
- ✅ Update `get_adjustments()` to filter by `record_status` (default: only VALID)
- ✅ Update `get_order_by_exchange_id()` to include `record_status`
- ✅ Add `update_order_record_status()` method
- ✅ Add `update_trade_record_status()` method
- ✅ Add `update_adjustment_record_status()` method

### Step 3: Update Reconciliation Scripts ✅
- ✅ Update `check_booking_recon.py` to filter by `record_status="VALID"`
- ✅ Update `fix_reconciliation_breaks.py` to use `update_trade_record_status()` instead of notes
- ✅ Update all reconciliation queries to exclude invalid records

### Step 4: Update API Endpoints ✅
- ✅ Add optional `record_status` filter to `/orders` endpoint
- ✅ Add optional `record_status` filter to `/trades` endpoint
- ✅ Update cancel order endpoint to only query VALID orders

### Step 5: Update Orchestrator and Services ✅
- ✅ Update `orchestrator.py` to filter by `record_status="VALID"` when querying
- ✅ Update rebuild scripts (`rebuild_positions.py`, `rebuild_balances.py`) to only use VALID trades

### Step 6: Update GUI ⏳
- ⏳ Add filter for record status
- ⏳ Show record status in tables
- ⏳ Optionally hide invalid/deleted records by default

## Benefits

1. **Clean Filtering**: Easy to filter valid vs invalid records in queries
2. **Audit Trail**: Invalid/deleted records preserved but clearly marked
3. **Data Integrity**: Clear distinction between execution status and data validity
4. **Reconciliation**: Easier to identify and handle invalid records
5. **Performance**: Indexed status column for faster filtering

## Backward Compatibility

- Default value 'VALID' ensures existing records remain valid
- Existing code continues to work (defaults to VALID)
- Optional parameter allows gradual migration

## Implementation Order

1. ✅ Create migration plan (this document)
2. ✅ Create Alembic migrations (`ab1a5935976a`, `415e7c6ce82e`)
3. ✅ Update Ledger methods (`booking/ledger.py`)
4. ✅ Update reconciliation scripts (`check_booking_recon.py`, `fix_reconciliation_breaks.py`)
5. ✅ Update API endpoints (`scripts/services/run_order_executor.py`)
6. ✅ Update orchestrator and rebuild scripts (`execution/orchestrator.py`, `scripts/utils/rebuild_*.py`)
7. ✅ Run database migrations
8. ⏳ Update GUI (`viz/pages/15_order_management.py`) - Pending
9. ✅ Update documentation (this document)

## Related Files

- ✅ `alembic/versions/ab1a5935976a_add_record_status_columns.py` - Orders and trades migration
- ✅ `alembic/versions/415e7c6ce82e_add_record_status_to_adjustments.py` - Adjustments migration
- ✅ `booking/ledger.py` - Updated all methods to support `record_status`
- ✅ `scripts/integrity/check_booking_recon.py` - Updated to filter by `record_status`
- ✅ `scripts/integrity/fix_reconciliation_breaks.py` - Updated to use `record_status` instead of notes
- ✅ `scripts/services/run_order_executor.py` - Updated API endpoints
- ✅ `execution/orchestrator.py` - Updated to filter by `record_status`
- ✅ `scripts/utils/rebuild_positions.py` - Updated to only use VALID trades
- ✅ `scripts/utils/rebuild_balances.py` - Updated to only use VALID trades
- ⏳ `viz/pages/15_order_management.py` - GUI updates pending

## Usage Examples

### Marking a Trade as Invalid
```python
from booking.ledger import Ledger

ledger = Ledger()
ledger.update_trade_record_status(
    ledger_trade_id=123,
    record_status="INVALID",
    notes="Not found in Binance - marked by reconciliation"
)
```

### Querying Only Valid Orders
```python
# Default behavior - only returns VALID orders
orders = ledger.get_orders(book_id="test_book")

# Explicitly request only VALID orders
orders = ledger.get_orders(book_id="test_book", record_status="VALID")

# Get all orders including invalid ones
orders = ledger.get_orders(book_id="test_book", record_status=None)
```

### API Endpoint Usage
```bash
# Get only valid orders (default)
curl http://localhost:8000/orders?book_id=test_book

# Get all orders including invalid
curl http://localhost:8000/orders?book_id=test_book&record_status=

# Get only invalid orders
curl http://localhost:8000/orders?book_id=test_book&record_status=INVALID
```

## Migration Notes

- **Migration Date**: 2026-02-06
- **Database**: Migrations applied successfully
- **Services**: Restart required to load updated code
  ```bash
  docker compose restart order-executor fill-sync
  ```
