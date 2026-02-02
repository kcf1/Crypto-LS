"""Load API keys and secrets from environment; no secrets in code."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


class Secrets:
    """Secrets loaded from environment variables."""

    # Data Collection API Keys (Read-only, for liquidations data)
    @property
    def binance_data_api_key(self) -> str:
        """API key for data collection (read-only). Falls back to legacy key if not set."""
        return _get("BINANCE_DATA_API_KEY") or _get("BINANCE_API_KEY")

    @property
    def binance_data_api_secret(self) -> str:
        """API secret for data collection (read-only). Falls back to legacy secret if not set."""
        return _get("BINANCE_DATA_API_SECRET") or _get("BINANCE_API_SECRET")

    # Trading API Keys (Read + Trade, for order management)
    @property
    def binance_trading_api_key(self) -> str:
        """API key for trading/order management. Falls back to legacy key if not set."""
        return _get("BINANCE_TRADING_API_KEY") or _get("BINANCE_API_KEY")

    @property
    def binance_trading_api_secret(self) -> str:
        """API secret for trading/order management. Falls back to legacy secret if not set."""
        return _get("BINANCE_TRADING_API_SECRET") or _get("BINANCE_API_SECRET")

    # Legacy API Keys (for backward compatibility)
    @property
    def binance_api_key(self) -> str:
        """Legacy: Single API key. Use BINANCE_DATA_API_KEY and BINANCE_TRADING_API_KEY instead."""
        return _get("BINANCE_API_KEY")

    @property
    def binance_api_secret(self) -> str:
        """Legacy: Single API secret. Use BINANCE_DATA_API_SECRET and BINANCE_TRADING_API_SECRET instead."""
        return _get("BINANCE_API_SECRET")

    # Testnet API Keys
    @property
    def binance_testnet_api_key(self) -> str:
        return _get("BINANCE_TESTNET_API_KEY")

    @property
    def binance_testnet_api_secret(self) -> str:
        return _get("BINANCE_TESTNET_API_SECRET")


secrets = Secrets()
