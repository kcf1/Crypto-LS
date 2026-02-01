"""Data package: raw ingestion (collector) and persistence (storage)."""

from data.collector import Collector
from data.storage import Storage

__all__ = ["Collector", "Storage"]
