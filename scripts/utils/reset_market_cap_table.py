"""
Reset market_cap table (truncate) then run test backfill.
Run from project root: python scripts/utils/reset_market_cap_table.py
"""

import subprocess
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import text

from data.storage import Storage, _engine_url, _is_postgres


def reset_market_cap_table() -> None:
    """Truncate (Postgres) or delete all rows (SQLite) from market_cap."""
    url = _engine_url()
    engine = Storage()._engine
    with engine.connect() as conn:
        if _is_postgres(url):
            conn.execute(text("TRUNCATE TABLE market_cap"))
        else:
            conn.execute(text("DELETE FROM market_cap"))
        conn.commit()
    print("market_cap table reset (all rows removed).")


if __name__ == "__main__":
    reset_market_cap_table()
    # Run test backfill
    print("\nRunning test backfill...\n")
    root = Path(__file__).resolve().parent.parent.parent
    rc = subprocess.run(
        [sys.executable, str(root / "scripts" / "backfill" / "test_backfill_market_cap.py")],
        cwd=str(root),
    )
    sys.exit(rc.returncode)
