"""Data updater: incremental OHLCV with tail refresh. Run as subprocess from dataupdater process."""

from data.updater.incremental import run_incremental_update

__all__ = ["run_incremental_update"]
