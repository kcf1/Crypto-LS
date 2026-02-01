"""App and trading parameters, timeframes, symbols, feature flags."""

from dataclasses import dataclass, field
from typing import List

# Top 100 Binance USDT pairs by typical 24h volume / market cap (for market data collection)
_TOP_100_RAW: List[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "SOLUSDT", "TRXUSDT",
    "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT", "LTCUSDT", "BCHUSDT", "UNIUSDT", "ATOMUSDT",
    "XLMUSDT", "ETCUSDT", "XMRUSDT", "FILUSDT", "APTUSDT", "HBARUSDT", "VETUSDT", "NEARUSDT",
    "ICPUSDT", "IMXUSDT", "OPUSDT", "INJUSDT", "SANDUSDT", "RENDERUSDT", "GRTUSDT", "ARBUSDT",
    "FTMUSDT", "MANAUSDT", "ALGOUSDT", "EOSUSDT", "AXSUSDT", "THETAUSDT", "FLOWUSDT", "AAVEUSDT",
    "RPLUSDT", "MKRUSDT", "KAVAUSDT", "CRVUSDT", "SNXUSDT", "COMPUSDT", "ZECUSDT", "LDOUSDT",
    "RUNEUSDT", "STXUSDT", "SUIUSDT", "SEIUSDT", "PEPEUSDT", "WLDUSDT", "BONKUSDT", "FETUSDT",
    "JUPUSDT", "PENDLEUSDT", "BLURUSDT", "DYDXUSDT", "TIAUSDT", "STRKUSDT", "ORDIUSDT", "ARKMUSDT",
    "GALAUSDT", "AGIXUSDT", "CFXUSDT", "ROSEUSDT", "WOOUSDT", "ENSUSDT", "POLUSDT", "MOVRUSDT",
    "MASKUSDT", "API3USDT", "LQTYUSDT", "CVGUSDT", "PYTHUSDT", "DYMUSDT", "MANTAUSDT", "ALTUSDT",
    "JASMYUSDT", "ONDOUSDT", "PIXELUSDT", "SUPERUSDT", "ASTRUSDT", "CELOUSDT", "DARUSDT", "MAGICUSDT",
    "NMRUSDT", "PORTALUSDT", "SKLUSDT", "STEEMUSDT", "TWTUSDT", "XAIUSDT", "AUDIOUSDT", "C98USDT",
    "MINAUSDT", "LINAUSDT", "YGGUSDT", "ACEUSDT", "MEMEUSDT", "IDUSDT", "NTRNUSDT", "MAVUSDT",
    "COMBOUSDT", "RDNTUSDT", "CYBERUSDT", "ARKUSDT", "HOOKUSDT", "SSVUSDT", "JTOUSDT", "EDUUSDT",
]
TOP_100_SYMBOLS: List[str] = _TOP_100_RAW[:100]

@dataclass(frozen=True)
class Settings:
    """Single source of truth for configuration used by data, execution, and booking."""

    # App
    env: str = "development"
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_file: str = "app.log"

    # Trading
    default_symbol: str = "BTCUSDT"
    symbols: List[str] = field(default_factory=lambda: list(TOP_100_SYMBOLS))
    default_timeframe: str = "5m"
    timeframes: List[str] = field(default_factory=lambda: ["5m"])

    # Data
    db_path: str = "data.db"
    ohlcv_limit_per_request: int = 1000

    # Feature flags
    use_testnet: bool = True


settings = Settings()
