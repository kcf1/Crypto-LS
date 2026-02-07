# Books Management Feature Plan

## Overview

Add a `books` table to manage book definitions and metadata, replacing free-text `book_id` inputs with validated book selection. This ensures data integrity and provides better UX for book management.

## Goals

1. **Data Integrity**: Ensure only valid book IDs exist in the system
2. **Better UX**: Replace free-text inputs with dropdowns showing book names
3. **Book Management**: Allow creating, editing, and managing books via GUI
4. **Backward Compatibility**: Ensure existing "default" book continues to work

---

## Database Schema Design

### Books Table

```sql
CREATE TABLE books (
    id TEXT PRIMARY KEY,                    -- book_id (e.g., "default", "test", "strategy_1")
    name TEXT NOT NULL,                     -- Display name (e.g., "Default Book", "Test Book")
    description TEXT,                       -- Optional description
    venue TEXT NOT NULL,                    -- Venue this book belongs to (e.g., "binance_spot")
    is_active BOOLEAN NOT NULL DEFAULT TRUE, -- Whether book is active (can be deactivated)
    created_at INTEGER NOT NULL,            -- Timestamp when book was created
    updated_at INTEGER,                     -- Timestamp when book was last updated
    created_by TEXT,                       -- User/system that created the book
    notes TEXT                             -- Additional notes
);

-- Indexes
CREATE INDEX idx_books_venue ON books(venue);
CREATE INDEX idx_books_active ON books(is_active);
```

### Schema Rationale

1. **`id` (TEXT PRIMARY KEY)**:
   - The book_id used throughout the system
   - Must be unique, lowercase, alphanumeric + underscores
   - Examples: "default", "test", "strategy_1", "long_short"

2. **`name` (TEXT NOT NULL)**:
   - Human-readable display name
   - Shown in dropdowns and UI
   - Examples: "Default Book", "Test Trading Book", "Long/Short Strategy"

3. **`description` (TEXT)**:
   - Optional longer description
   - Can explain book purpose, strategy, etc.

4. **`venue` (TEXT NOT NULL)**:
   - Links book to a specific venue
   - Allows multiple books per venue
   - Default: "binance_spot"

5. **`is_active` (BOOLEAN)**:
   - Allows deactivating books without deleting them
   - Inactive books won't appear in dropdowns
   - Historical data remains intact

6. **`created_at` / `updated_at` (INTEGER)**:
   - Audit timestamps (milliseconds since epoch)

7. **`created_by` (TEXT)**:
   - Tracks who created the book
   - Can be user ID, system, or API key identifier

8. **`notes` (TEXT)**:
   - Free-form notes about the book

### Foreign Key Constraints (Optional - Future Enhancement)

For strict referential integrity, we could add foreign keys:
- `orders.book_id` → `books.id`
- `trades.book_id` → `books.id`
- `positions.book_id` → `books.id`
- `balances.book_id` → `books.id`
- `adjustments.book_id` → `books.id`

**Note**: We'll skip foreign keys initially to allow flexibility, but can add them later.

---

## Migration Strategy

### Phase 1: Create Books Table

1. **Alembic Migration**: Create `007_add_books_table.py`
   - Create `books` table
   - Insert default book: `id="default", name="Default Book", venue="binance_spot", is_active=true`
   - No foreign keys initially (for flexibility)

### Phase 2: Update Ledger Methods

2. **Add Book Management Methods**:
   - `ledger.create_book(id, name, description, venue, created_by, notes) -> str`
   - `ledger.get_books(venue=None, active_only=True) -> List[Dict]`
   - `ledger.update_book(id, name=None, description=None, is_active=None, notes=None) -> bool`
   - `ledger.get_book(id) -> Optional[Dict]`
   - `ledger.validate_book_id(book_id, venue) -> bool` (checks if book exists)

### Phase 3: Update Order Executor API

3. **Add Book Management Endpoints**:
   - `GET /books` - List all books (with filters: venue, active_only)
   - `GET /books/<id>` - Get book by ID
   - `POST /books` - Create new book
   - `PUT /books/<id>` - Update book
   - `DELETE /books/<id>` - Deactivate book (soft delete via is_active=false)

### Phase 4: Update GUI

4. **Update Order Management GUI**:
   - Replace `book_id` text inputs with dropdowns
   - Show book names in dropdown, store book IDs
   - Add "Book Management" tab with:
     - List of books (table view)
     - Create new book form
     - Edit book form
     - Deactivate/activate books

---

## API Design

### GET /books

List books with optional filters.

**Query Parameters**:
- `venue` (optional): Filter by venue
- `active_only` (optional, default=true): Only return active books

**Response**:
```json
{
  "books": [
    {
      "id": "default",
      "name": "Default Book",
      "description": "Main trading book",
      "venue": "binance_spot",
      "is_active": true,
      "created_at": 1234567890000,
      "updated_at": 1234567890000,
      "created_by": "system",
      "notes": null
    }
  ],
  "count": 1
}
```

### GET /books/<id>

Get specific book by ID.

**Response**:
```json
{
  "id": "default",
  "name": "Default Book",
  "description": "Main trading book",
  "venue": "binance_spot",
  "is_active": true,
  "created_at": 1234567890000,
  "updated_at": 1234567890000,
  "created_by": "system",
  "notes": null
}
```

### POST /books

Create a new book.

**Request Body**:
```json
{
  "id": "test",
  "name": "Test Book",
  "description": "Book for testing orders",
  "venue": "binance_spot",
  "notes": "Created for testing"
}
```

**Response**: 201 Created with book data

**Validation**:
- `id` must be unique
- `id` must match pattern: `^[a-z0-9_]+$` (lowercase, alphanumeric, underscores)
- `name` is required
- `venue` defaults to `settings.venue` if not provided

### PUT /books/<id>

Update an existing book.

**Request Body** (all fields optional):
```json
{
  "name": "Updated Book Name",
  "description": "Updated description",
  "is_active": true,
  "notes": "Updated notes"
}
```

**Response**: 200 OK with updated book data

### DELETE /books/<id>

Deactivate a book (soft delete).

**Response**: 200 OK with deactivated book data

**Note**: Sets `is_active=false` instead of actually deleting.

---

## GUI Design

### Book Management Tab

**Layout**:
1. **Create Book Form** (at top, collapsible)
   - Fields: ID, Name, Description, Venue (dropdown), Notes
   - Validation: ID format, uniqueness check
   - Submit button

2. **Books List** (table view)
   - Columns: ID, Name, Description, Venue, Active Status, Created At, Actions
   - Actions: Edit, Deactivate/Activate
   - Filter: By venue, active/inactive

3. **Edit Book Modal/Form** (when Edit clicked)
   - Pre-filled with book data
   - Fields: Name, Description, Active Status, Notes
   - Save/Cancel buttons

### Updated Order Placement Tab

**Changes**:
- Replace `book_id` text input with dropdown
- Dropdown shows: `{name} ({id})` format
- Example: "Default Book (default)"
- Filtered by current venue (from settings)
- Only shows active books

### Updated Query Tabs

**Changes**:
- Replace `book_id` text inputs with dropdowns
- Same format as order placement
- Optional "All Books" option for queries

---

## Validation Rules

### Book ID Format
- Pattern: `^[a-z0-9_]+$`
- Length: 1-50 characters
- Must start with letter or number (not underscore)
- Examples: ✅ "default", "test", "strategy_1"
- Examples: ❌ "Default", "test-book", "test book", "_test"

### Book Name
- Required
- Length: 1-100 characters
- Can contain any characters (for display)

### Uniqueness
- `id` must be unique across all books
- Check before insert/update

---

## Backward Compatibility

1. **Default Book**: Auto-create "default" book if missing during migration
2. **Existing Data**: All existing orders/trades/positions/balances with `book_id="default"` continue to work
3. **API**: Existing API calls without book validation continue to work (but will validate going forward)
4. **GUI**: Old text inputs still work, but dropdown is preferred

---

## Implementation Steps

1. ✅ **Design Schema** (this document)
2. ⏳ **Create Alembic Migration** (`007_add_books_table.py`)
3. ⏳ **Add Ledger Methods** (`booking/ledger.py`)
4. ⏳ **Add API Endpoints** (`scripts/services/run_order_executor.py`)
5. ⏳ **Update GUI** (`viz/pages/15_order_management.py`)
6. ⏳ **Add Validation** (book_id format, uniqueness)
7. ⏳ **Testing** (create books, place orders, verify data integrity)

---

## Future Enhancements

1. **Foreign Key Constraints**: Add FK constraints for strict referential integrity
2. **Book Permissions**: Add user/role-based access control per book
3. **Book Settings**: Add book-specific settings (risk limits, etc.)
4. **Book Analytics**: Add book-level P&L, performance metrics
5. **Book Templates**: Pre-defined book templates for common strategies

---

## Questions to Consider

1. **Should we allow deleting books?** → No, use soft delete (is_active=false)
2. **Should books be venue-specific?** → Yes, each book belongs to a venue
3. **Should we validate book_id in all API calls?** → Yes, but make it optional initially
4. **What happens to orders with invalid book_id?** → Validation error, don't allow creation

---

## Estimated Effort

- **Database Migration**: 1 hour
- **Ledger Methods**: 2 hours
- **API Endpoints**: 2 hours
- **GUI Updates**: 3 hours
- **Testing**: 2 hours
- **Total**: ~10 hours

---

## Last Updated

2025-02-02
