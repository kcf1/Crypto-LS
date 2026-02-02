"""Persist and query raw OHLCV and futures data; schema and access patterns for raw series only."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from config import settings

logger = logging.getLogger(__name__)

# In-memory schema for SQLite only (Postgres schema is managed by Alembic)
OHLCV_SCHEMA = """
CREATE TABLE IF NOT EXISTS ohlcv (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER NOT NULL,
    PRIMARY KEY (symbol, timeframe, open_time)
);
CREATE INDEX IF NOT EXISTS ix_ohlcv_symbol_timeframe ON ohlcv (symbol, timeframe);
"""

# INSERT with ON CONFLICT (works on SQLite 3.24+ and PostgreSQL)
OHLCV_UPSERT_SQL = """
INSERT INTO ohlcv (symbol, timeframe, open_time, open, high, low, close, volume, close_time)
VALUES (:symbol, :timeframe, :open_time, :open, :high, :low, :close, :volume, :close_time)
ON CONFLICT (symbol, timeframe, open_time) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume, close_time = EXCLUDED.close_time
"""


def _engine_url(db_path: Optional[str] = None, database_url: Optional[str] = None) -> str:
    """Resolve engine URL: DATABASE_URL if set, else SQLite at db_path."""
    if database_url:
        return database_url
    url = settings.database_url
    if url:
        return url
    path = Path(db_path or settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.resolve()}"


def _is_postgres(url: str) -> bool:
    return url.strip().startswith("postgresql") or url.strip().startswith("postgres+")


class Storage:
    """Persist and query raw OHLCV. Uses DATABASE_URL (Postgres) when set, else SQLite at db_path."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        database_url: Optional[str] = None,
    ) -> None:
        url = _engine_url(db_path=db_path, database_url=database_url)
        self._engine = create_engine(url, echo=False)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)
        if not _is_postgres(url):
            self._init_schema()

    def _init_schema(self) -> None:
        with self._engine.connect() as conn:
            for stmt in OHLCV_SCHEMA.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(text(stmt))
            conn.commit()

    def session(self) -> Session:
        return self._session_factory()

    def write_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        rows: Sequence[tuple],
    ) -> None:
        """Write raw OHLCV rows. Each row: (open_time, open, high, low, close, volume, close_time)."""
        if not rows:
            return
        with self._engine.connect() as conn:
            try:
                for r in rows:
                    conn.execute(
                        text(OHLCV_UPSERT_SQL),
                        {
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "open_time": r[0],
                            "open": r[1],
                            "high": r[2],
                            "low": r[3],
                            "close": r[4],
                            "volume": r[5],
                            "close_time": r[6],
                        },
                    )
                conn.commit()
            except Exception as e:
                logger.error(
                    "write_ohlcv failed symbol=%s timeframe=%s rows=%s: %s",
                    symbol,
                    timeframe,
                    len(rows),
                    e,
                    exc_info=True,
                )
                raise

    def get_latest_open_time(self, symbol: str, timeframe: str) -> Optional[int]:
        """Return the latest (max) open_time for the given symbol/timeframe, or None if no rows."""
        sql = """
            SELECT MAX(open_time) FROM ohlcv
            WHERE symbol = :symbol AND timeframe = :timeframe
        """
        with self._engine.connect() as conn:
            result = conn.execute(
                text(sql),
                {"symbol": symbol, "timeframe": timeframe},
            )
            row = result.fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    def read_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: Optional[int] = None,
        from_time: Optional[int] = None,
        to_time: Optional[int] = None,
    ) -> List[tuple]:
        """Return raw OHLCV rows (open_time, open, high, low, close, volume, close_time)."""
        sql = """
            SELECT open_time, open, high, low, close, volume, close_time
            FROM ohlcv WHERE symbol = :symbol AND timeframe = :timeframe
        """
        params: dict = {"symbol": symbol, "timeframe": timeframe}
        if from_time is not None:
            sql += " AND open_time >= :from_time"
            params["from_time"] = from_time
        if to_time is not None:
            sql += " AND open_time <= :to_time"
            params["to_time"] = to_time
        sql += " ORDER BY open_time ASC"
        if limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = limit
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            return list(result.fetchall())

    # Funding Rate methods
    FUNDING_RATE_UPSERT_SQL = """
    INSERT INTO funding_rate (symbol, funding_time, funding_rate, mark_price)
    VALUES (:symbol, :funding_time, :funding_rate, :mark_price)
    ON CONFLICT (symbol, funding_time) DO UPDATE SET
      funding_rate = EXCLUDED.funding_rate, mark_price = EXCLUDED.mark_price
    """

    def write_funding_rate(
        self,
        symbol: str,
        rows: Sequence[tuple],  # (funding_time, funding_rate, mark_price)
    ) -> None:
        """Write funding rate rows. Each row: (funding_time, funding_rate, mark_price)."""
        if not rows:
            return
        with self._engine.connect() as conn:
            try:
                for r in rows:
                    conn.execute(
                        text(self.FUNDING_RATE_UPSERT_SQL),
                        {
                            "symbol": symbol,
                            "funding_time": r[0],
                            "funding_rate": r[1],
                            "mark_price": r[2],
                        },
                    )
                conn.commit()
            except Exception as e:
                logger.error(
                    "write_funding_rate failed symbol=%s rows=%s: %s",
                    symbol,
                    len(rows),
                    e,
                    exc_info=True,
                )
                raise

    def read_funding_rate(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[tuple]:
        """
        Read funding rate rows for a symbol.
        Returns list of tuples: (funding_time, funding_rate, mark_price).
        """
        sql = """
            SELECT funding_time, funding_rate, mark_price
            FROM funding_rate
            WHERE symbol = :symbol
        """
        params: dict[str, Any] = {"symbol": symbol}
        if start_time is not None:
            sql += " AND funding_time >= :start_time"
            params["start_time"] = start_time
        if end_time is not None:
            sql += " AND funding_time < :end_time"
            params["end_time"] = end_time
        sql += " ORDER BY funding_time ASC"
        
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
        return [(int(r[0]), float(r[1]), float(r[2])) for r in rows]

    def get_latest_funding_time(self, symbol: str) -> Optional[int]:
        """Return the latest (max) funding_time for the given symbol, or None if no rows."""
        sql = """
            SELECT MAX(funding_time) FROM funding_rate
            WHERE symbol = :symbol
        """
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), {"symbol": symbol})
            row = result.fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    # Open Interest methods
    OPEN_INTEREST_UPSERT_SQL = """
    INSERT INTO open_interest (symbol, period, timestamp, sum_open_interest, sum_open_interest_value)
    VALUES (:symbol, :period, :timestamp, :sum_open_interest, :sum_open_interest_value)
    ON CONFLICT (symbol, period, timestamp) DO UPDATE SET
      sum_open_interest = EXCLUDED.sum_open_interest,
      sum_open_interest_value = EXCLUDED.sum_open_interest_value
    """

    def write_open_interest(
        self,
        symbol: str,
        period: str,
        rows: Sequence[tuple],  # (timestamp, sum_open_interest, sum_open_interest_value)
    ) -> None:
        """Write open interest rows. Each row: (timestamp, sum_open_interest, sum_open_interest_value)."""
        if not rows:
            return
        with self._engine.connect() as conn:
            try:
                for r in rows:
                    conn.execute(
                        text(self.OPEN_INTEREST_UPSERT_SQL),
                        {
                            "symbol": symbol,
                            "period": period,
                            "timestamp": r[0],
                            "sum_open_interest": r[1],
                            "sum_open_interest_value": r[2],
                        },
                    )
                conn.commit()
            except Exception as e:
                logger.error(
                    "write_open_interest failed symbol=%s period=%s rows=%s: %s",
                    symbol,
                    period,
                    len(rows),
                    e,
                    exc_info=True,
                )
                raise

    def get_latest_open_interest_time(self, symbol: str, period: str) -> Optional[int]:
        """Return the latest (max) timestamp for the given symbol/period, or None if no rows."""
        sql = """
            SELECT MAX(timestamp) FROM open_interest
            WHERE symbol = :symbol AND period = :period
        """
        with self._engine.connect() as conn:
            result = conn.execute(
                text(sql),
                {"symbol": symbol, "period": period},
            )
            row = result.fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    # Liquidations methods
    LIQUIDATIONS_INSERT_SQL = """
    INSERT INTO liquidations (
        symbol, time, order_id, side, order_type, quantity, price, avg_price,
        status, last_filled_qty, filled_accumulated_qty, trade_time
    )
    VALUES (
        :symbol, :time, :order_id, :side, :order_type, :quantity, :price, :avg_price,
        :status, :last_filled_qty, :filled_accumulated_qty, :trade_time
    )
    ON CONFLICT (order_id) DO NOTHING
    """

    def write_liquidations(
        self,
        symbol: str,
        rows: Sequence[Dict[str, Any]],  # List of liquidation order dicts
    ) -> None:
        """Write liquidation orders. Handles duplicates by order_id."""
        if not rows:
            return
        with self._engine.connect() as conn:
            try:
                for r in rows:
                    # Binance forceOrders response fields
                    order_id = r.get("orderId") or r.get("id", 0)
                    time_val = r.get("time") or r.get("updateTime", 0)
                    
                    conn.execute(
                        text(self.LIQUIDATIONS_INSERT_SQL),
                        {
                            "symbol": symbol,
                            "time": time_val,
                            "order_id": order_id,
                            "side": r.get("side", ""),
                            "order_type": r.get("type", ""),
                            "quantity": float(r.get("origQty", 0) or r.get("quantity", 0)),
                            "price": float(r.get("price", 0)),
                            "avg_price": float(r.get("avgPrice", 0) or r.get("price", 0)),
                            "status": r.get("status", ""),
                            "last_filled_qty": float(r.get("lastFilledQty", 0) or 0),
                            "filled_accumulated_qty": float(r.get("executedQty", 0) or r.get("cumQty", 0)),
                            "trade_time": time_val,
                        },
                    )
                conn.commit()
            except Exception as e:
                logger.error(
                    "write_liquidations failed symbol=%s rows=%s: %s",
                    symbol,
                    len(rows),
                    e,
                    exc_info=True,
                )
                raise

    def get_latest_liquidation_time(self, symbol: str) -> Optional[int]:
        """Return the latest (max) time for the given symbol, or None if no rows."""
        sql = """
            SELECT MAX(time) FROM liquidations
            WHERE symbol = :symbol
        """
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), {"symbol": symbol})
            row = result.fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])
