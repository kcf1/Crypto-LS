"""Persist and query raw OHLCV data; schema and access patterns for raw series only."""

import logging
from pathlib import Path
from typing import List, Optional, Sequence

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
