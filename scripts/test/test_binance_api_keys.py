"""Test Binance API keys (testnet and production)."""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from execution.binance.client import BinanceClient
from config import settings, secrets
from binance.exceptions import BinanceAPIException


def test_testnet_keys():
    """Test testnet API keys."""
    print("=" * 60)
    print("Testing Binance Testnet API Keys")
    print("=" * 60)
    
    testnet_key = secrets.binance_testnet_api_key
    testnet_secret = secrets.binance_testnet_api_secret
    
    print(f"\nTestnet API Key: {testnet_key[:10]}...{testnet_key[-10:] if len(testnet_key) > 20 else ''}")
    print(f"Testnet Secret: {'*' * 20} (hidden)")
    
    if not testnet_key or not testnet_secret:
        print("❌ ERROR: Testnet API keys are not set!")
        return False
    
    try:
        client = BinanceClient(use_testnet=True)
        print("\n✅ Testnet client created successfully")
        
        # Test account access
        print("\nTesting account access...")
        account = client.get_account()
        print(f"✅ Account access successful")
        print(f"   Account type: {account.get('accountType', 'N/A')}")
        print(f"   Balances: {len(account.get('balances', []))} assets")
        
        # Test if we can query orders (read permission)
        print("\nTesting order query permissions...")
        try:
            open_orders = client.get_open_orders(symbol="BTCUSDT")
            print(f"✅ Order query successful: {len(open_orders)} open orders for BTCUSDT")
        except Exception as e:
            print(f"⚠️  Order query test skipped: {e}")
        
        print("\n✅ Testnet API keys are valid and have proper permissions!")
        return True
        
    except BinanceAPIException as e:
        print(f"\n❌ Binance API Error: {e}")
        print(f"   Error code: {e.code}")
        print(f"   Error message: {e.message}")
        
        if e.code == -2015:
            print("\n⚠️  Possible issues:")
            print("   - API key is invalid or expired")
            print("   - API key doesn't have trading permissions")
            print("   - IP address not whitelisted")
            print("   - Using production keys on testnet (or vice versa)")
        
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_production_keys():
    """Test production API keys."""
    print("\n" + "=" * 60)
    print("Testing Binance Production API Keys")
    print("=" * 60)
    
    prod_key = secrets.binance_trading_api_key
    prod_secret = secrets.binance_trading_api_secret
    
    print(f"\nProduction API Key: {prod_key[:10]}...{prod_key[-10:] if len(prod_key) > 20 else ''}")
    print(f"Production Secret: {'*' * 20} (hidden)")
    
    if not prod_key or not prod_secret:
        print("❌ ERROR: Production API keys are not set!")
        return False
    
    try:
        client = BinanceClient(use_testnet=False)
        print("\n✅ Production client created successfully")
        
        # Test account access
        print("\nTesting account access...")
        account = client.get_account()
        print(f"✅ Account access successful")
        print(f"   Account type: {account.get('accountType', 'N/A')}")
        print(f"   Balances: {len(account.get('balances', []))} assets")
        
        print("\n✅ Production API keys are valid!")
        return True
        
    except BinanceAPIException as e:
        print(f"\n❌ Binance API Error: {e}")
        print(f"   Error code: {e.code}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    print(f"\nCurrent Settings:")
    print(f"  use_testnet: {settings.use_testnet}")
    print(f"  use_testnet_for_orders: {settings.use_testnet_for_orders}")
    
    # Test testnet keys (since USE_TESTNET_FOR_ORDERS=true)
    testnet_ok = test_testnet_keys()
    
    # Optionally test production keys
    # test_production_keys()
    
    sys.exit(0 if testnet_ok else 1)
