"""File-based logging setup. Call setup_logging() once at app/script startup."""

import logging
from pathlib import Path

from config.settings import settings


def setup_logging() -> None:
    """Configure root logger to write to a file in settings.log_dir. Idempotent."""
    root = logging.getLogger()
    if any(h for h in root.handlers if getattr(h, "baseFilename", None)):
        return  # already have a file handler
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_path = Path(settings.log_dir) / settings.log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level)
