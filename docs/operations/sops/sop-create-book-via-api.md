# SOP: Create Book via API

## Purpose

This SOP describes how to create a new trading book using the order-executor API. Books are used to group and organize orders, trades, positions, and balances.

## Prerequisites

- Order-executor service must be running
- Access to the order-executor API (default: `http://localhost:8000`)
- `curl` command available (or PowerShell/HTTP client)

## Book ID Format Requirements

- **Format**: Lowercase letters, numbers, and underscores only
- **Pattern**: `^[a-z0-9_]+$`
- **Examples**: 
  - ✅ `test_book`, `prod_main`, `arbitrage_1`, `strategy_a`
  - ❌ `Test-Book` (uppercase), `test.book` (dots), `test book` (spaces)

## Step-by-Step Process

### Step 1: Verify Service is Running

Check if order-executor service is accessible:

```bash
# Check service health
curl http://localhost:8000/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "database_connected": true,
  "redis_connected": true
}
```

**If service is not running:**
```bash
docker compose ps order-executor
docker compose up -d order-executor
```

---

### Step 2: Suggest Book Details

Before creating a book, prepare the following details:

#### Required Fields

- **`id`**: Unique book identifier (lowercase, alphanumeric + underscores)
- **`name`**: Display name for the book

#### Optional Fields

- **`venue`**: Trading venue (defaults to `binance_spot` if not provided)
- **`description`**: Description of the book's purpose
- **`notes`**: Additional notes
- **`created_by`**: Creator identifier (optional)

#### Book Detail Suggestions

**For Testing:**
```json
{
  "id": "test_book",
  "name": "Test Book",
  "venue": "binance_spot",
  "description": "Test book for development and testing",
  "notes": "Created for API testing purposes"
}
```

**For Production:**
```json
{
  "id": "prod_main",
  "name": "Production Main Book",
  "venue": "binance_spot",
  "description": "Main production trading book",
  "notes": "Primary book for live trading"
}
```

**For Strategy-Specific:**
```json
{
  "id": "strategy_arbitrage",
  "name": "Arbitrage Strategy Book",
  "venue": "binance_spot",
  "description": "Book for arbitrage trading strategy",
  "notes": "Isolated book for arbitrage positions"
}
```

**For Paper Trading:**
```json
{
  "id": "paper_trading",
  "name": "Paper Trading Book",
  "venue": "binance_spot",
  "description": "Simulated trading without real funds",
  "notes": "Used for strategy testing with virtual funds"
}
```

---

### Step 3: Review and Approve Book Details

**Review Checklist:**
- [ ] Book ID follows format requirements (lowercase, alphanumeric + underscores)
- [ ] Book ID is unique (not already exists)
- [ ] Name is descriptive and clear
- [ ] Venue matches your trading venue
- [ ] Description explains the book's purpose

**Check if Book Already Exists:**
```bash
# List all books
curl http://localhost:8000/books

# Check specific book
curl http://localhost:8000/books/test_book
```

**If book exists, you'll get:**
```json
{
  "id": "test_book",
  "name": "Test Book",
  ...
}
```

**If book doesn't exist, you'll get:**
```json
{
  "error": "Book not found"
}
```

---

### Step 4: Create Book via API

Once book details are approved, create the book:

#### Using curl (Linux/Mac/Git Bash)

```bash
curl -X POST http://localhost:8000/books \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test_book",
    "name": "Test Book",
    "venue": "binance_spot",
    "description": "Test book for development and testing",
    "notes": "Created for API testing purposes"
  }'
```

#### Using PowerShell (Windows)

```powershell
$body = @{
    id = "test_book"
    name = "Test Book"
    venue = "binance_spot"
    description = "Test book for development and testing"
    notes = "Created for API testing purposes"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/books -Method Post -Body $body -ContentType "application/json"
```

#### Using Python

```python
import requests

book_data = {
    "id": "test_book",
    "name": "Test Book",
    "venue": "binance_spot",
    "description": "Test book for development and testing",
    "notes": "Created for API testing purposes"
}

response = requests.post("http://localhost:8000/books", json=book_data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

---

### Step 5: Verify Book Creation

**Expected Success Response (HTTP 201):**
```json
{
  "id": "test_book",
  "name": "Test Book",
  "description": "Test book for development and testing",
  "venue": "binance_spot",
  "is_active": true,
  "created_at": 1707123456789,
  "updated_at": null,
  "created_by": null,
  "notes": "Created for API testing purposes"
}
```

**Verify the book was created:**
```bash
# Get the created book
curl http://localhost:8000/books/test_book

# List all books (should include the new one)
curl http://localhost:8000/books
```

---

## Error Handling

### Error: Book Already Exists

**Response (HTTP 400):**
```json
{
  "error": "Book with id 'test_book' already exists",
  "type": "ValueError"
}
```

**Solution:** Choose a different book ID or update the existing book instead.

---

### Error: Invalid Book ID Format

**Response (HTTP 400):**
```json
{
  "error": "book_id must match pattern ^[a-z0-9_]+$ (got: Test-Book)",
  "type": "ValueError"
}
```

**Solution:** Use lowercase letters, numbers, and underscores only.

---

### Error: Missing Required Fields

**Response (HTTP 400):**
```json
{
  "error": "id and name are required"
}
```

**Solution:** Ensure both `id` and `name` are provided in the request.

---

### Error: Service Not Available

**Response:**
```
curl: (7) Failed to connect to localhost port 8000: Connection refused
```

**Solution:**
1. Check if order-executor service is running:
   ```bash
   docker compose ps order-executor
   ```
2. Start the service if not running:
   ```bash
   docker compose up -d order-executor
   ```
3. Wait a few seconds for service to start, then retry

---

### Error: Database Connection Failed

**Response (HTTP 500):**
```json
{
  "error": "Database connection error"
}
```

**Solution:**
1. Check PostgreSQL is running:
   ```bash
   docker compose ps postgres
   ```
2. Verify database connection in service logs:
   ```bash
   docker logs crypto-ls-order-executor --tail 50
   ```
3. Check database migration status:
   ```bash
   alembic current
   alembic upgrade head
   ```

---

## Post-Creation Steps

### 1. Verify Book in GUI

1. Open Streamlit GUI: `streamlit run viz/app.py`
2. Navigate to "Order Management" → "Book Management" tab
3. Verify the new book appears in the list
4. Check that book is marked as "Active" (🟢)

### 2. Test Book Usage

Create a test order using the new book:

```bash
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "side": "BUY",
    "order_type": "MARKET",
    "quantity": 0.001,
    "book_id": "test_book"
  }'
```

### 3. Verify Foreign Key Constraint

The book should now be referenced in:
- Orders table (`orders.book_id`)
- Trades table (`trades.book_id`)
- Positions table (`positions.book_id`)
- Balances table (`balances.book_id`)
- Adjustments table (`adjustments.book_id`)

---

## Quick Reference

### Minimal Book Creation

```bash
curl -X POST http://localhost:8000/books \
  -H "Content-Type: application/json" \
  -d '{"id":"minimal_book","name":"Minimal Book"}'
```

### Full Book Creation

```bash
curl -X POST http://localhost:8000/books \
  -H "Content-Type: application/json" \
  -d '{
    "id": "full_book",
    "name": "Full Book",
    "venue": "binance_spot",
    "description": "Complete book with all fields",
    "notes": "Additional notes",
    "created_by": "admin"
  }'
```

### List All Books

```bash
curl http://localhost:8000/books
```

### Get Specific Book

```bash
curl http://localhost:8000/books/test_book
```

### Update Book

```bash
curl -X PUT http://localhost:8000/books/test_book \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Book Name",
    "description": "Updated description"
  }'
```

### Deactivate Book

```bash
curl -X DELETE http://localhost:8000/books/test_book
```

---

## Related Documentation

- Books Management Plan: `docs/plans/features/books-management.md`
- Order Executor Service: `scripts/services/run_order_executor.py`
- Ledger Implementation: `booking/ledger.py`
- Database Schema: `alembic/versions/007_add_books_table.py`

---

## Revision History

- **2025-02-05**: Initial version created
