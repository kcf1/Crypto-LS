"""
Data integrity checking framework.

Provides base classes and utilities for running data quality checks.
"""

from .base import IntegrityCheck, IntegrityCheckResult

__all__ = ["IntegrityCheck", "IntegrityCheckResult"]
