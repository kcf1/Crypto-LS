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

    @property
    def binance_api_key(self) -> str:
        return _get("BINANCE_API_KEY")

    @property
    def binance_api_secret(self) -> str:
        return _get("BINANCE_API_SECRET")

    @property
    def binance_testnet_api_key(self) -> str:
        return _get("BINANCE_TESTNET_API_KEY")

    @property
    def binance_testnet_api_secret(self) -> str:
        return _get("BINANCE_TESTNET_API_SECRET")


secrets = Secrets()
