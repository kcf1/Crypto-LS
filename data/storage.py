"""Persist and query raw OHLCV data; schema and access patterns for raw series only."""

import logging
from pathlib import Path
from typing import List, Optional, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# In-memory schema: raw OHLCV candles
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


class Storage:
    """Persist and query raw OHLCV. Uses SQLite by default; configurable via engine."""

    def __init__(self, db_path: str = "data.db") -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{path}", echo=False)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)
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
        conn = self._engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.executemany(
                """
                INSERT OR REPLACE INTO ohlcv
                (symbol, timeframe, open_time, open, high, low, close, volume, close_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (symbol, timeframe, r[0], r[1], r[2], r[3], r[4], r[5], r[6])
                    for r in rows
                ],
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
        finally:
            conn.close()

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
