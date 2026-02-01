"""App and trading parameters, timeframes, symbols, feature flags."""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Settings:
    """Single source of truth for configuration used by data, execution, and booking."""

    # App
    env: str = "development"
    log_level: str = "INFO"

    # Trading
    default_symbol: str = "BTCUSDT"
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    default_timeframe: str = "1h"
    timeframes: List[str] = field(default_factory=lambda: ["1m", "5m", "15m", "1h", "4h", "1d"])

    # Data
    db_path: str = "data.db"
    ohlcv_limit_per_request: int = 1000

    # Feature flags
    use_testnet: bool = True


settings = Settings()
