"""Minimal booking interface: record order/trade, query positions. Consumes execution outcomes."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from config import settings

# SQLite-only schema (Postgres schema is managed by Alembic)
BOOKING_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue TEXT NOT NULL,
    book_id TEXT NOT NULL DEFAULT 'default',
    exchange_order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue TEXT NOT NULL,
    book_id TEXT NOT NULL DEFAULT 'default',
    exchange_trade_id TEXT,
    order_id INTEGER,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    commission REAL DEFAULT 0,
    traded_at INTEGER NOT NULL,
    notes TEXT,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
CREATE TABLE IF NOT EXISTS positions (
    book_id TEXT NOT NULL DEFAULT 'default',
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_price REAL NOT NULL,
    updated_at INTEGER NOT NULL,
    notes TEXT,
    PRIMARY KEY (book_id, symbol)
);
CREATE TABLE IF NOT EXISTS balances (
    venue TEXT NOT NULL,
    book_id TEXT NOT NULL DEFAULT 'default',
    asset TEXT NOT NULL,
    free REAL NOT NULL DEFAULT 0,
    locked REAL NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (venue, book_id, asset)
);
CREATE TABLE IF NOT EXISTS adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue TEXT NOT NULL,
    book_id TEXT NOT NULL DEFAULT 'default',
    type TEXT NOT NULL,
    asset_or_symbol TEXT NOT NULL,
    delta_or_value REAL NOT NULL,
    reason TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    created_by TEXT,
    notes TEXT
);
"""


def _engine_url(db_path: Optional[str] = None, database_url: Optional[str] = None) -> str:
    """Resolve engine URL: DATABASE_URL if set, else SQLite at db_path."""
    if database_url:
        return database_url
    if settings.database_url:
        return settings.database_url
    path = Path(db_path or settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.resolve()}"


def _is_postgres(url: str) -> bool:
    return url.strip().startswith("postgresql") or url.strip().startswith("postgres+")


def _parse_symbol(symbol: str) -> tuple[str, str]:
    """Parse symbol string to extract base and quote assets.
    
    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT", "ETHBTC")
        
    Returns:
        Tuple of (base_asset, quote_asset)
        
    Raises:
        ValueError: If symbol cannot be parsed
    """
    # Common quote assets in order of preference (longest first for proper matching)
    quote_assets = ["USDT", "BUSD", "USDC", "BTC", "ETH", "BNB"]
    
    # Try matching longest quote asset suffix first
    for quote in sorted(quote_assets, key=len, reverse=True):
        if symbol.endswith(quote):
            base = symbol[:-len(quote)]
            if base:  # Ensure base is not empty
                return (base, quote)
    
    # If no match found, raise error
    raise ValueError(f"Could not parse symbol {symbol}: no recognized quote asset found")


class Ledger:
    """Trade/position ledger: record orders and trades, query positions. Uses DATABASE_URL when set."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        database_url: Optional[str] = None,
    ) -> None:
        url = _engine_url(db_path=db_path, database_url=database_url)
        self._engine = create_engine(url, echo=False)
        if not _is_postgres(url):
            self._init_schema()

    def _init_schema(self) -> None:
        with self._engine.connect() as conn:
            for stmt in BOOKING_SCHEMA.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(text(stmt))
            conn.commit()

    def record_order(
        self,
        venue: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        status: str,
        created_at: int,
        exchange_order_id: Optional[str] = None,
        price: Optional[float] = None,
        updated_at: Optional[int] = None,
        book_id: str = "default",
        notes: Optional[str] = None,
    ) -> int:
        """Record an order; returns ledger order id. Idempotent: returns existing id if order already exists."""
        with self._engine.connect() as conn:
            # Idempotency check: if exchange_order_id provided, check if order already exists
            if exchange_order_id:
                existing = conn.execute(
                    text("""
                        SELECT id FROM orders
                        WHERE venue = :venue AND book_id = :book_id AND exchange_order_id = :exchange_order_id
                    """),
                    {
                        "venue": venue,
                        "book_id": book_id,
                        "exchange_order_id": exchange_order_id,
                    },
                ).fetchone()
                if existing:
                    return existing[0]
            
            try:
                result = conn.execute(
                    text("""
                        INSERT INTO orders
                        (venue, book_id, exchange_order_id, symbol, side, order_type, quantity, price, status, created_at, updated_at, notes)
                        VALUES (:venue, :book_id, :exchange_order_id, :symbol, :side, :order_type, :quantity, :price, :status, :created_at, :updated_at, :notes)
                        RETURNING id
                    """),
                    {
                        "venue": venue,
                        "book_id": book_id,
                        "exchange_order_id": exchange_order_id,
                        "symbol": symbol,
                        "side": side.upper(),
                        "order_type": order_type.upper(),
                        "quantity": quantity,
                        "price": price,
                        "status": status.upper(),
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "notes": notes,
                    },
                )
                conn.commit()
                row = result.fetchone()
                return row[0] if row else 0
            except IntegrityError:
                # Handle PostgreSQL unique constraint violation
                conn.rollback()
                # Query for existing order
                existing = conn.execute(
                    text("""
                        SELECT id FROM orders
                        WHERE venue = :venue AND book_id = :book_id AND exchange_order_id = :exchange_order_id
                    """),
                    {
                        "venue": venue,
                        "book_id": book_id,
                        "exchange_order_id": exchange_order_id,
                    },
                ).fetchone()
                if existing:
                    return existing[0]
                raise

    def record_trade(
        self,
        venue: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        traded_at: int,
        exchange_trade_id: Optional[str] = None,
        order_id: Optional[int] = None,
        commission: float = 0.0,
        commission_asset: Optional[str] = None,
        book_id: str = "default",
        notes: Optional[str] = None,
    ) -> int:
        """Record a trade (fill) and update position and balances. Returns ledger trade id. Idempotent."""
        with self._engine.connect() as conn:
            # Idempotency check: if exchange_trade_id provided, check if trade already exists
            if exchange_trade_id:
                existing = conn.execute(
                    text("""
                        SELECT id FROM trades
                        WHERE venue = :venue AND book_id = :book_id AND exchange_trade_id = :exchange_trade_id
                    """),
                    {
                        "venue": venue,
                        "book_id": book_id,
                        "exchange_trade_id": exchange_trade_id,
                    },
                ).fetchone()
                if existing:
                    return existing[0]
            
            try:
                # Insert trade
                result = conn.execute(
                    text("""
                        INSERT INTO trades
                        (venue, book_id, exchange_trade_id, order_id, symbol, side, quantity, price, commission, traded_at, notes)
                        VALUES (:venue, :book_id, :exchange_trade_id, :order_id, :symbol, :side, :quantity, :price, :commission, :traded_at, :notes)
                        RETURNING id
                    """),
                    {
                        "venue": venue,
                        "book_id": book_id,
                        "exchange_trade_id": exchange_trade_id,
                        "order_id": order_id,
                        "symbol": symbol,
                        "side": side.upper(),
                        "quantity": quantity,
                        "price": price,
                        "commission": commission,
                        "traded_at": traded_at,
                        "notes": notes,
                    },
                )
                row = result.fetchone()
                trade_id = row[0] if row else 0
                
                # Update position
                self._update_position(conn, symbol, side, quantity, price, traded_at, book_id)
                
                # Update balances
                self._update_balances(conn, venue, symbol, side, quantity, price, commission, commission_asset, traded_at, book_id)
                
                # Update order status if order_id provided
                if order_id:
                    self._update_order_status_from_trades(conn, order_id)
                
                conn.commit()
                return trade_id
            except IntegrityError:
                # Handle PostgreSQL unique constraint violation
                conn.rollback()
                # Query for existing trade
                if exchange_trade_id:
                    existing = conn.execute(
                        text("""
                            SELECT id FROM trades
                            WHERE venue = :venue AND book_id = :book_id AND exchange_trade_id = :exchange_trade_id
                        """),
                        {
                            "venue": venue,
                            "book_id": book_id,
                            "exchange_trade_id": exchange_trade_id,
                        },
                    ).fetchone()
                    if existing:
                        return existing[0]
                raise

    def _update_position(
        self,
        conn: Any,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        updated_at: int,
        book_id: str = "default",
    ) -> None:
        """Update positions table from a trade (side, quantity, price)."""
        row = conn.execute(
            text("SELECT quantity, avg_price FROM positions WHERE book_id = :book_id AND symbol = :symbol"),
            {"book_id": book_id, "symbol": symbol},
        ).fetchone()
        if row:
            q, avg = float(row[0]), float(row[1])
            if side.upper() == "BUY":
                new_q = q + quantity
                new_avg = (avg * q + price * quantity) / new_q if new_q else avg
            else:
                new_q = q - quantity
                new_avg = avg
            if abs(new_q) < 1e-12:
                conn.execute(
                    text("DELETE FROM positions WHERE book_id = :book_id AND symbol = :symbol"),
                    {"book_id": book_id, "symbol": symbol},
                )
            else:
                conn.execute(
                    text("""
                        UPDATE positions SET quantity = :q, avg_price = :avg, updated_at = :t
                        WHERE book_id = :book_id AND symbol = :symbol
                    """),
                    {"book_id": book_id, "symbol": symbol, "q": new_q, "avg": new_avg, "t": updated_at},
                )
        else:
            if side.upper() == "SELL":
                quantity = -quantity
            conn.execute(
                text("""
                    INSERT INTO positions (book_id, symbol, quantity, avg_price, updated_at)
                    VALUES (:book_id, :symbol, :quantity, :price, :updated_at)
                """),
                {"book_id": book_id, "symbol": symbol, "quantity": quantity, "price": price, "updated_at": updated_at},
            )
    
    def _update_balances(
        self,
        conn: Any,
        venue: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        commission: float,
        commission_asset: Optional[str],
        traded_at: int,
        book_id: str = "default",
    ) -> None:
        """Update balances table from a trade (base, quote, commission assets)."""
        try:
            base_asset, quote_asset = _parse_symbol(symbol)
        except ValueError:
            # Log warning but don't fail trade insert
            import logging
            logging.warning(f"Could not parse symbol {symbol} for balance update, skipping")
            return
        
        # Determine commission asset (use provided or default to quote)
        comm_asset = commission_asset or quote_asset
        
        is_postgres = _is_postgres(str(self._engine.url))
        
        # Update base asset balance
        if side.upper() == "BUY":
            base_delta = quantity
        else:
            base_delta = -quantity
        
        if is_postgres:
            conn.execute(
                text("""
                    INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                    VALUES (:venue, :book_id, :asset, :delta, 0, :updated_at)
                    ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                        free = balances.free + :delta,
                        updated_at = :updated_at
                """),
                {
                    "venue": venue,
                    "book_id": book_id,
                    "asset": base_asset,
                    "delta": base_delta,
                    "updated_at": traded_at,
                },
            )
        else:
            # SQLite
            conn.execute(
                text("""
                    INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                    VALUES (:venue, :book_id, :asset, :delta, 0, :updated_at)
                    ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                        free = balances.free + :delta,
                        updated_at = :updated_at
                """),
                {
                    "venue": venue,
                    "book_id": book_id,
                    "asset": base_asset,
                    "delta": base_delta,
                    "updated_at": traded_at,
                },
            )
        
        # Update quote asset balance
        if side.upper() == "BUY":
            quote_delta = -(quantity * price)  # Spend quote
        else:
            quote_delta = quantity * price  # Receive quote
        
        if is_postgres:
            conn.execute(
                text("""
                    INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                    VALUES (:venue, :book_id, :asset, :delta, 0, :updated_at)
                    ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                        free = balances.free + :delta,
                        updated_at = :updated_at
                """),
                {
                    "venue": venue,
                    "book_id": book_id,
                    "asset": quote_asset,
                    "delta": quote_delta,
                    "updated_at": traded_at,
                },
            )
        else:
            # SQLite
            conn.execute(
                text("""
                    INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                    VALUES (:venue, :book_id, :asset, :delta, 0, :updated_at)
                    ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                        free = balances.free + :delta,
                        updated_at = :updated_at
                """),
                {
                    "venue": venue,
                    "book_id": book_id,
                    "asset": quote_asset,
                    "delta": quote_delta,
                    "updated_at": traded_at,
                },
            )
        
        # Update commission asset balance (always subtract commission)
        if commission > 0:
            if is_postgres:
                conn.execute(
                    text("""
                        INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                        VALUES (:venue, :book_id, :asset, :delta, 0, :updated_at)
                        ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                            free = balances.free + :delta,
                            updated_at = :updated_at
                    """),
                    {
                        "venue": venue,
                        "book_id": book_id,
                        "asset": comm_asset,
                        "delta": -commission,
                        "updated_at": traded_at,
                    },
                )
            else:
                # SQLite
                conn.execute(
                    text("""
                        INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                        VALUES (:venue, :book_id, :asset, :delta, 0, :updated_at)
                        ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                            free = balances.free + :delta,
                            updated_at = :updated_at
                    """),
                    {
                        "venue": venue,
                        "book_id": book_id,
                        "asset": comm_asset,
                        "delta": -commission,
                        "updated_at": traded_at,
                    },
                )
    
    def _update_order_status_from_trades(self, conn: Any, order_id: int) -> None:
        """Update order status based on filled quantity from trades."""
        # Get order quantity
        order_row = conn.execute(
            text("SELECT quantity FROM orders WHERE id = :order_id"),
            {"order_id": order_id},
        ).fetchone()
        if not order_row:
            return
        
        order_quantity = float(order_row[0])
        
        # Sum filled quantity from trades
        filled_row = conn.execute(
            text("""
                SELECT COALESCE(SUM(quantity), 0), MAX(traded_at)
                FROM trades WHERE order_id = :order_id
            """),
            {"order_id": order_id},
        ).fetchone()
        
        if filled_row:
            filled_quantity = float(filled_row[0])
            latest_trade_time = filled_row[1]
            
            # Determine status
            if filled_quantity >= order_quantity - 1e-12:  # Account for floating point
                new_status = "FILLED"
            elif filled_quantity > 0:
                new_status = "PARTIALLY_FILLED"
            else:
                return  # No fills yet, don't update
            
            # Update order status
            conn.execute(
                text("""
                    UPDATE orders SET status = :status, updated_at = :updated_at
                    WHERE id = :order_id
                """),
                {
                    "order_id": order_id,
                    "status": new_status,
                    "updated_at": latest_trade_time,
                },
            )

    def get_positions(self, symbol: Optional[str] = None, book_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return positions: list of dicts with book_id, symbol, quantity, avg_price, updated_at, notes."""
        sql = "SELECT book_id, symbol, quantity, avg_price, updated_at, notes FROM positions WHERE 1=1"
        params: dict = {}
        if symbol is not None:
            sql += " AND symbol = :symbol"
            params["symbol"] = symbol
        if book_id is not None:
            sql += " AND book_id = :book_id"
            params["book_id"] = book_id
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
        return [
            {
                "book_id": r[0],
                "symbol": r[1],
                "quantity": float(r[2]),
                "avg_price": float(r[3]),
                "updated_at": r[4],
                "notes": r[5],
            }
            for r in rows
        ]

    def get_orders(
        self,
        symbol: Optional[str] = None,
        venue: Optional[str] = None,
        book_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query recorded orders."""
        sql = "SELECT id, venue, book_id, exchange_order_id, symbol, side, order_type, quantity, price, status, created_at, updated_at, notes FROM orders WHERE 1=1"
        params: dict = {}
        if symbol:
            sql += " AND symbol = :symbol"
            params["symbol"] = symbol
        if venue:
            sql += " AND venue = :venue"
            params["venue"] = venue
        if book_id:
            sql += " AND book_id = :book_id"
            params["book_id"] = book_id
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = limit
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
        return [
            {
                "id": r[0],
                "venue": r[1],
                "book_id": r[2],
                "exchange_order_id": r[3],
                "symbol": r[4],
                "side": r[5],
                "order_type": r[6],
                "quantity": float(r[7]),
                "price": float(r[8]) if r[8] is not None else None,
                "status": r[9],
                "created_at": r[10],
                "updated_at": r[11],
                "notes": r[12],
            }
            for r in rows
        ]

    def get_trades(
        self,
        symbol: Optional[str] = None,
        venue: Optional[str] = None,
        book_id: Optional[str] = None,
        exchange_trade_id: Optional[str] = None,
        order_id: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query recorded trades."""
        sql = "SELECT id, venue, book_id, exchange_trade_id, order_id, symbol, side, quantity, price, commission, traded_at, notes FROM trades WHERE 1=1"
        params: dict = {}
        if symbol:
            sql += " AND symbol = :symbol"
            params["symbol"] = symbol
        if venue:
            sql += " AND venue = :venue"
            params["venue"] = venue
        if book_id:
            sql += " AND book_id = :book_id"
            params["book_id"] = book_id
        if exchange_trade_id:
            sql += " AND exchange_trade_id = :exchange_trade_id"
            params["exchange_trade_id"] = exchange_trade_id
        if order_id is not None:
            sql += " AND order_id = :order_id"
            params["order_id"] = order_id
        sql += " ORDER BY traded_at DESC"
        if limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = limit
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
        return [
            {
                "id": r[0],
                "venue": r[1],
                "book_id": r[2],
                "exchange_trade_id": r[3],
                "order_id": r[4],
                "symbol": r[5],
                "side": r[6],
                "quantity": float(r[7]),
                "price": float(r[8]),
                "commission": float(r[9]),
                "traded_at": r[10],
                "notes": r[11],
            }
            for r in rows
        ]
    
    def update_order_status(
        self,
        ledger_order_id: int,
        status: str,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Update order status and optionally record adjustment."""
        import time
        updated_at = int(time.time() * 1000)  # Current time in milliseconds
        
        with self._engine.connect() as conn:
            # Update order status
            conn.execute(
                text("""
                    UPDATE orders SET status = :status, updated_at = :updated_at
                    WHERE id = :order_id
                """),
                {
                    "order_id": ledger_order_id,
                    "status": status.upper(),
                    "updated_at": updated_at,
                },
            )
            
            # Update notes if provided
            if notes is not None:
                conn.execute(
                    text("UPDATE orders SET notes = :notes WHERE id = :order_id"),
                    {
                        "order_id": ledger_order_id,
                        "notes": notes,
                    },
                )
            
            # Record adjustment if reason provided
            if reason:
                # Get order details for adjustment
                order_row = conn.execute(
                    text("SELECT venue, book_id FROM orders WHERE id = :order_id"),
                    {"order_id": ledger_order_id},
                ).fetchone()
                if order_row:
                    venue, book_id = order_row[0], order_row[1]
                    conn.execute(
                        text("""
                            INSERT INTO adjustments
                            (venue, book_id, type, asset_or_symbol, delta_or_value, reason, created_at, notes)
                            VALUES (:venue, :book_id, :type, :asset_or_symbol, :delta_or_value, :reason, :created_at, :notes)
                        """),
                        {
                            "venue": venue,
                            "book_id": book_id,
                            "type": "order_status",
                            "asset_or_symbol": str(ledger_order_id),
                            "delta_or_value": 0.0,  # Not used for order_status type
                            "reason": reason,
                            "created_at": updated_at,
                            "notes": notes,
                        },
                    )
            
            conn.commit()
    
    def get_order_by_exchange_id(
        self,
        venue: str,
        exchange_order_id: str,
        book_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get order by exchange order ID. Returns None if not found."""
        sql = "SELECT id, venue, book_id, exchange_order_id, symbol, side, order_type, quantity, price, status, created_at, updated_at, notes FROM orders WHERE venue = :venue AND exchange_order_id = :exchange_order_id"
        params: dict = {"venue": venue, "exchange_order_id": exchange_order_id}
        if book_id:
            sql += " AND book_id = :book_id"
            params["book_id"] = book_id
        
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            row = result.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "venue": row[1],
                "book_id": row[2],
                "exchange_order_id": row[3],
                "symbol": row[4],
                "side": row[5],
                "order_type": row[6],
                "quantity": float(row[7]),
                "price": float(row[8]) if row[8] is not None else None,
                "status": row[9],
                "created_at": row[10],
                "updated_at": row[11],
                "notes": row[12],
            }
    
    def record_adjustment(
        self,
        venue: str,
        book_id: str,
        type: str,
        asset_or_symbol: str,
        delta_or_value: float,
        reason: str,
        created_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> int:
        """Record an adjustment and update target table. Returns adjustment id."""
        import time
        created_at = int(time.time() * 1000)  # Current time in milliseconds
        
        with self._engine.connect() as conn:
            # Insert adjustment record
            result = conn.execute(
                text("""
                    INSERT INTO adjustments
                    (venue, book_id, type, asset_or_symbol, delta_or_value, reason, created_at, created_by, notes)
                    VALUES (:venue, :book_id, :type, :asset_or_symbol, :delta_or_value, :reason, :created_at, :created_by, :notes)
                    RETURNING id
                """),
                {
                    "venue": venue,
                    "book_id": book_id,
                    "type": type,
                    "asset_or_symbol": asset_or_symbol,
                    "delta_or_value": delta_or_value,
                    "reason": reason,
                    "created_at": created_at,
                    "created_by": created_by,
                    "notes": notes,
                },
            )
            row = result.fetchone()
            adjustment_id = row[0] if row else 0
            
            # Update target table based on type
            if type == "balance":
                # Update balances.free
                is_postgres = _is_postgres(str(self._engine.url))
                if is_postgres:
                    conn.execute(
                        text("""
                            INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                            VALUES (:venue, :book_id, :asset, :value, 0, :updated_at)
                            ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                                free = :value,
                                updated_at = :updated_at
                        """),
                        {
                            "venue": venue,
                            "book_id": book_id,
                            "asset": asset_or_symbol,
                            "value": delta_or_value,
                            "updated_at": created_at,
                        },
                    )
                else:
                    # SQLite
                    conn.execute(
                        text("""
                            INSERT INTO balances (venue, book_id, asset, free, locked, updated_at)
                            VALUES (:venue, :book_id, :asset, :value, 0, :updated_at)
                            ON CONFLICT (venue, book_id, asset) DO UPDATE SET
                                free = :value,
                                updated_at = :updated_at
                        """),
                        {
                            "venue": venue,
                            "book_id": book_id,
                            "asset": asset_or_symbol,
                            "value": delta_or_value,
                            "updated_at": created_at,
                        },
                    )
            elif type == "position":
                # Update positions.quantity
                conn.execute(
                    text("""
                        UPDATE positions SET quantity = :value, updated_at = :updated_at
                        WHERE book_id = :book_id AND symbol = :symbol
                    """),
                    {
                        "book_id": book_id,
                        "symbol": asset_or_symbol,
                        "value": delta_or_value,
                        "updated_at": created_at,
                    },
                )
            elif type == "order_status":
                # Update orders.status
                order_id = int(asset_or_symbol)
                conn.execute(
                    text("""
                        UPDATE orders SET status = :status, updated_at = :updated_at
                        WHERE id = :order_id
                    """),
                    {
                        "order_id": order_id,
                        "status": str(int(delta_or_value)) if delta_or_value else "CANCELED",
                        "updated_at": created_at,
                    },
                )
            
            conn.commit()
            return adjustment_id
    
    def get_balances(
        self,
        venue: Optional[str] = None,
        book_id: Optional[str] = None,
        asset: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query balances. Returns list of dicts with venue, book_id, asset, free, locked, updated_at."""
        sql = "SELECT venue, book_id, asset, free, locked, updated_at FROM balances WHERE 1=1"
        params: dict = {}
        if venue:
            sql += " AND venue = :venue"
            params["venue"] = venue
        if book_id:
            sql += " AND book_id = :book_id"
            params["book_id"] = book_id
        if asset:
            sql += " AND asset = :asset"
            params["asset"] = asset
        sql += " ORDER BY venue, book_id, asset"
        
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
        return [
            {
                "venue": r[0],
                "book_id": r[1],
                "asset": r[2],
                "free": float(r[3]),
                "locked": float(r[4]),
                "updated_at": r[5],
            }
            for r in rows
        ]
    
    def get_adjustments(
        self,
        venue: Optional[str] = None,
        book_id: Optional[str] = None,
        type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query adjustments. Returns list of dicts with all adjustment fields."""
        sql = "SELECT id, venue, book_id, type, asset_or_symbol, delta_or_value, reason, created_at, created_by, notes FROM adjustments WHERE 1=1"
        params: dict = {}
        if venue:
            sql += " AND venue = :venue"
            params["venue"] = venue
        if book_id:
            sql += " AND book_id = :book_id"
            params["book_id"] = book_id
        if type:
            sql += " AND type = :type"
            params["type"] = type
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = limit
        
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
        return [
            {
                "id": r[0],
                "venue": r[1],
                "book_id": r[2],
                "type": r[3],
                "asset_or_symbol": r[4],
                "delta_or_value": float(r[5]),
                "reason": r[6],
                "created_at": r[7],
                "created_by": r[8],
                "notes": r[9],
            }
            for r in rows
        ]
