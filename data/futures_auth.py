"""Authentication helpers for Binance Futures API (USER_DATA endpoints)."""

import hashlib
import hmac
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from config import secrets

logger = logging.getLogger(__name__)


def sign_request(params: Dict[str, Any], api_secret: str) -> str:
    """
    Generate HMAC-SHA256 signature for Binance API request.
    
    Args:
        params: Request parameters dictionary
        api_secret: Binance API secret key
        
    Returns:
        Signature string (hex)
    """
    query_string = urlencode(sorted(params.items()))
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def add_auth_params(params: Dict[str, Any], api_key: Optional[str] = None, api_secret: Optional[str] = None) -> Dict[str, Any]:
    """
    Add authentication parameters (timestamp and signature) to request params.
    
    Args:
        params: Request parameters dictionary
        api_key: Binance API key (optional, for headers)
        api_secret: Binance API secret (required for signature)
        
    Returns:
        Updated params dictionary with timestamp and signature
    """
    if not api_secret:
        api_secret = secrets.binance_data_api_secret
    
    if not api_secret:
        raise ValueError("API secret required for authenticated requests")
    
    params = params.copy()
    params["timestamp"] = int(time.time() * 1000)
    params["signature"] = sign_request(params, api_secret)
    return params


def get_auth_headers(api_key: Optional[str] = None) -> Dict[str, str]:
    """
    Get authentication headers for Binance API requests.
    
    Args:
        api_key: Binance API key (optional, uses secrets if not provided)
        
    Returns:
        Headers dictionary with X-MBX-APIKEY
    """
    if not api_key:
        api_key = secrets.binance_data_api_key
    
    if not api_key:
        raise ValueError("API key required for authenticated requests")
    
    return {"X-MBX-APIKEY": api_key}
