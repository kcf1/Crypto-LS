"""
Quick test to verify API key authentication is working.
Tests a simple authenticated endpoint first before trying liquidations.

Run from project root: python scripts/backfill/test_auth.py
"""

import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import secrets
from data.futures_auth import add_auth_params, get_auth_headers
import requests

def test_api_key():
    """Test API key authentication with a simple endpoint."""
    print("Testing API Key Authentication...")
    print(f"API Key (first 10 chars): {secrets.binance_data_api_key[:10] if secrets.binance_data_api_key else 'NOT SET'}...")
    print(f"API Secret (first 10 chars): {secrets.binance_data_api_secret[:10] if secrets.binance_data_api_secret else 'NOT SET'}...")
    print()
    
    if not secrets.binance_data_api_key or not secrets.binance_data_api_secret:
        print("ERROR: API keys not set in .env file")
        print("Set BINANCE_DATA_API_KEY and BINANCE_DATA_API_SECRET")
        return False
    
    # Test with a simple authenticated endpoint: account info
    url = "https://fapi.binance.com/fapi/v2/account"
    params = {}
    params = add_auth_params(params)
    headers = get_auth_headers()
    
    print(f"Testing endpoint: {url}")
    print(f"Headers: {headers}")
    print(f"Params: {list(params.keys())}")
    print()
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print("SUCCESS: Authentication working!")
            print(f"Account assets: {len(data.get('assets', []))} assets")
            return True
        else:
            print(f"ERROR: {resp.status_code}")
            print(f"Response: {resp.text[:500]}")
            return False
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return False

if __name__ == "__main__":
    success = test_api_key()
    sys.exit(0 if success else 1)
