"""Test order placement with testnet API keys."""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from execution.order_manager import OrderManager
from config import settings
from binance.exceptions import BinanceAPIException


def test_order_placement():
    """Test placing a small test order."""
    print("=" * 60)
    print("Testing Order Placement")
    print("=" * 60)
    
    print(f"\nSettings:")
    print(f"  use_testnet_for_orders: {settings.use_testnet_for_orders}")
    
    try:
        # Create OrderManager (should use testnet if use_testnet_for_orders=True)
        order_manager = OrderManager()
        print("\n✅ OrderManager created")
        
        # Check what client is being used
        client = order_manager._binance
        print(f"  Using testnet: {client._use_testnet}")
        
        # Try to place a very small market order
        print("\nAttempting to place test order...")
        print("  Symbol: BTCUSDT")
        print("  Side: BUY")
        print("  Type: MARKET")
        print("  Quantity: 0.0001 BTC")
        
        response = order_manager.submit_market(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.0001
        )
        
        print(f"\n✅ Order placed successfully!")
        print(f"  Order ID: {response.get('orderId')}")
        print(f"  Status: {response.get('status')}")
        return True
        
    except BinanceAPIException as e:
        print(f"\n❌ Binance API Error: {e}")
        print(f"   Error code: {e.code}")
        print(f"   Error message: {e.message}")
        
        if e.code == -2015:
            print("\n⚠️  Error -2015: Invalid API-key, IP, or permissions for action")
            print("\nPossible causes:")
            print("  1. API key doesn't have 'Enable Trading' permission")
            print("  2. IP whitelist is enabled and Docker IP not whitelisted")
            print("  3. API key is for wrong environment (production vs testnet)")
            print("\nTo fix:")
            print("  1. Go to Binance Testnet API Management:")
            print("     https://testnet.binance.vision/")
            print("  2. Check your API key permissions")
            print("  3. Ensure 'Enable Trading' is checked")
            print("  4. If IP whitelist is enabled, add Docker container IP or disable it")
        
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_order_placement()
    sys.exit(0 if success else 1)
