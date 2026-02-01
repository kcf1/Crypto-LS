"""Minimal booking interface: record order/trade, query positions. Consumes execution outcomes."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text

from config import settings

# SQLite-only schema (Postgres schema is managed by Alembic)
BOOKING_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue TEXT NOT NULL,
    exchange_order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue TEXT NOT NULL,
    exchange_trade_id TEXT,
    order_id INTEGER,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    commission REAL DEFAULT 0,
    traded_at INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT NOT NULL PRIMARY KEY,
    quantity REAL NOT NULL,
    avg_price REAL NOT NULL,
    updated_at INTEGER NOT NULL
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
    ) -> int:
        """Record an order; returns ledger order id."""
        with self._engine.connect() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO orders
                    (venue, exchange_order_id, symbol, side, order_type, quantity, price, status, created_at, updated_at)
                    VALUES (:venue, :exchange_order_id, :symbol, :side, :order_type, :quantity, :price, :status, :created_at, :updated_at)
                    RETURNING id
                """),
                {
                    "venue": venue,
                    "exchange_order_id": exchange_order_id,
                    "symbol": symbol,
                    "side": side.upper(),
                    "order_type": order_type.upper(),
                    "quantity": quantity,
                    "price": price,
                    "status": status.upper(),
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
            )
            conn.commit()
            row = result.fetchone()
            return row[0] if row else 0

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
    ) -> int:
        """Record a trade (fill) and update position. Returns ledger trade id."""
        with self._engine.connect() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO trades
                    (venue, exchange_trade_id, order_id, symbol, side, quantity, price, commission, traded_at)
                    VALUES (:venue, :exchange_trade_id, :order_id, :symbol, :side, :quantity, :price, :commission, :traded_at)
                    RETURNING id
                """),
                {
                    "venue": venue,
                    "exchange_trade_id": exchange_trade_id,
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side.upper(),
                    "quantity": quantity,
                    "price": price,
                    "commission": commission,
                    "traded_at": traded_at,
                },
            )
            conn.commit()
            row = result.fetchone()
            trade_id = row[0] if row else 0
            self._update_position(conn, symbol, side, quantity, price, traded_at)
            return trade_id

    def _update_position(
        self,
        conn: Any,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        updated_at: int,
    ) -> None:
        """Update positions table from a trade (side, quantity, price)."""
        row = conn.execute(
            text("SELECT quantity, avg_price FROM positions WHERE symbol = :symbol"),
            {"symbol": symbol},
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
                conn.execute(text("DELETE FROM positions WHERE symbol = :symbol"), {"symbol": symbol})
            else:
                conn.execute(
                    text("""
                        UPDATE positions SET quantity = :q, avg_price = :avg, updated_at = :t
                        WHERE symbol = :symbol
                    """),
                    {"symbol": symbol, "q": new_q, "avg": new_avg, "t": updated_at},
                )
        else:
            if side.upper() == "SELL":
                quantity = -quantity
            conn.execute(
                text("""
                    INSERT INTO positions (symbol, quantity, avg_price, updated_at)
                    VALUES (:symbol, :quantity, :price, :updated_at)
                """),
                {"symbol": symbol, "quantity": quantity, "price": price, "updated_at": updated_at},
            )
        conn.commit()

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return positions: list of dicts with symbol, quantity, avg_price, updated_at."""
        sql = "SELECT symbol, quantity, avg_price, updated_at FROM positions"
        params: dict = {}
        if symbol is not None:
            sql += " WHERE symbol = :symbol"
            params["symbol"] = symbol
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
        return [
            {
                "symbol": r[0],
                "quantity": float(r[1]),
                "avg_price": float(r[2]),
                "updated_at": r[3],
            }
            for r in rows
        ]

    def get_orders(
        self,
        symbol: Optional[str] = None,
        venue: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query recorded orders."""
        sql = "SELECT id, venue, exchange_order_id, symbol, side, order_type, quantity, price, status, created_at, updated_at FROM orders WHERE 1=1"
        params: dict = {}
        if symbol:
            sql += " AND symbol = :symbol"
            params["symbol"] = symbol
        if venue:
            sql += " AND venue = :venue"
            params["venue"] = venue
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
                "exchange_order_id": r[2],
                "symbol": r[3],
                "side": r[4],
                "order_type": r[5],
                "quantity": float(r[6]),
                "price": float(r[7]) if r[7] is not None else None,
                "status": r[8],
                "created_at": r[9],
                "updated_at": r[10],
            }
            for r in rows
        ]

    def get_trades(
        self,
        symbol: Optional[str] = None,
        venue: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query recorded trades."""
        sql = "SELECT id, venue, exchange_trade_id, order_id, symbol, side, quantity, price, commission, traded_at FROM trades WHERE 1=1"
        params: dict = {}
        if symbol:
            sql += " AND symbol = :symbol"
            params["symbol"] = symbol
        if venue:
            sql += " AND venue = :venue"
            params["venue"] = venue
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
                "exchange_trade_id": r[2],
                "order_id": r[3],
                "symbol": r[4],
                "side": r[5],
                "quantity": float(r[6]),
                "price": float(r[7]),
                "commission": float(r[8]),
                "traded_at": r[9],
            }
            for r in rows
        ]
