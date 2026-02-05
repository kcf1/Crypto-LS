"""
Order Management: Manual order placement and testing GUI.

Connects to order-executor service API for placing orders, viewing trades, positions, and balances.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import requests
import streamlit as st
from datetime import datetime
import pandas as pd

# Add project root to path for config access
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from config import settings
from data.storage import Storage

# Order Executor API Configuration
ORDER_EXECUTOR_URL = "http://localhost:8000"


@st.cache_data(ttl=10)
def get_latest_close_price(symbol: str, timeframe: str = "5m") -> Optional[float]:
    """Get the latest close price for a symbol from the database."""
    try:
        storage = Storage()
        # Get latest open_time first
        latest_time = storage.get_latest_open_time(symbol.upper(), timeframe)
        if not latest_time:
            return None
        
        # Get the bar with that open_time
        bars = storage.read_ohlcv(
            symbol=symbol.upper(),
            timeframe=timeframe,
            from_time=latest_time,
            to_time=latest_time,
            limit=1
        )
        if bars and len(bars) > 0:
            # Return the close price from the latest bar
            # Format: (open_time, open, high, low, close, volume, close_time)
            return float(bars[-1][4])  # close is at index 4
        return None
    except Exception:
        # Silently fail - price will default to 0.0
        return None


def check_service_health() -> bool:
    """Check if order-executor service is running."""
    try:
        response = requests.get(f"{ORDER_EXECUTOR_URL}/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def place_order(order_data: Dict) -> Dict:
    """Place an order via API."""
    try:
        response = requests.post(
            f"{ORDER_EXECUTOR_URL}/orders",
            json=order_data,
            timeout=10
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def get_orders(symbol: Optional[str] = None, book_id: Optional[str] = None, limit: int = 50) -> Dict:
    """Get orders from API."""
    try:
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        if book_id:
            params["book_id"] = book_id
        response = requests.get(f"{ORDER_EXECUTOR_URL}/orders", params=params, timeout=5)
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def get_trades(symbol: Optional[str] = None, book_id: Optional[str] = None, limit: int = 50) -> Dict:
    """Get trades from API."""
    try:
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        if book_id:
            params["book_id"] = book_id
        response = requests.get(f"{ORDER_EXECUTOR_URL}/trades", params=params, timeout=5)
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def get_positions(symbol: Optional[str] = None, book_id: Optional[str] = None) -> Dict:
    """Get positions from API."""
    try:
        params = {}
        if symbol:
            params["symbol"] = symbol
        if book_id:
            params["book_id"] = book_id
        response = requests.get(f"{ORDER_EXECUTOR_URL}/positions", params=params, timeout=5)
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def get_balances(asset: Optional[str] = None, book_id: Optional[str] = None) -> Dict:
    """Get balances from API."""
    try:
        params = {}
        if asset:
            params["asset"] = asset
        if book_id:
            params["book_id"] = book_id
        response = requests.get(f"{ORDER_EXECUTOR_URL}/balances", params=params, timeout=5)
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def get_books(venue: Optional[str] = None, active_only: bool = True) -> Dict:
    """Get books from API."""
    try:
        params = {"active_only": "true" if active_only else "false"}
        if venue:
            params["venue"] = venue
        response = requests.get(f"{ORDER_EXECUTOR_URL}/books", params=params, timeout=5)
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


# Load books for dropdowns (cache for performance)
@st.cache_data(ttl=60)
def load_books_for_dropdown():
    """Load active books for dropdown selection."""
    result = get_books(venue=settings.venue, active_only=True)
    if result["success"]:
        books = result["data"].get("books", [])
        # Return as list of tuples: (display_name, book_id)
        return [(f"{b['name']} ({b['id']})", b['id']) for b in books]
    return [("Default Book (default)", "default")]


def create_book(book_data: Dict) -> Dict:
    """Create a new book."""
    try:
        response = requests.post(
            f"{ORDER_EXECUTOR_URL}/books",
            json=book_data,
            timeout=5
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def update_book(book_id: str, book_data: Dict) -> Dict:
    """Update a book."""
    try:
        response = requests.put(
            f"{ORDER_EXECUTOR_URL}/books/{book_id}",
            json=book_data,
            timeout=5
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def delete_book(book_id: str) -> Dict:
    """Deactivate a book."""
    try:
        response = requests.delete(
            f"{ORDER_EXECUTOR_URL}/books/{book_id}",
            timeout=5
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def cancel_order(order_id: int) -> Dict:
    """Cancel an order."""
    try:
        response = requests.post(
            f"{ORDER_EXECUTOR_URL}/orders/{order_id}/cancel",
            json={},
            timeout=5
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def rebuild_positions() -> Dict:
    """Rebuild positions table."""
    try:
        response = requests.post(
            f"{ORDER_EXECUTOR_URL}/admin/rebuild-positions",
            json={},
            timeout=30
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def rebuild_balances() -> Dict:
    """Rebuild balances table."""
    try:
        response = requests.post(
            f"{ORDER_EXECUTOR_URL}/admin/rebuild-balances",
            json={},
            timeout=30
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


# Page Title
st.title("📊 Order Management")
st.caption("Manual order placement and testing interface for order-executor service")

# Check service health
if not check_service_health():
    st.error("⚠️ Order Executor Service is not running!")
    st.info("Please start the order-executor service: `docker compose up -d order-executor`")
    st.stop()

st.success("✅ Order Executor Service is running")

# Tabs for different functions
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Place Order",
    "Orders",
    "Trades",
    "Positions",
    "Balances",
    "Admin",
    "Book Management"
])

# Tab 1: Place Order
with tab1:
    st.header("Place New Order")
    
    with st.form("place_order_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            symbol = st.text_input("Symbol", value="BTCUSDT", help="Trading pair (e.g., BTCUSDT)")
            side = st.selectbox("Side", ["BUY", "SELL"])
            order_type = st.selectbox("Order Type", ["MARKET", "LIMIT"], help="MARKET executes immediately, LIMIT waits for price")
        
        with col2:
            quantity = st.number_input("Quantity", min_value=0.0, value=0.001, step=0.001, format="%.6f", help="Base asset quantity")
            
            # Get latest close price for default
            symbol_upper = symbol.upper() if symbol else "BTCUSDT"
            latest_close = get_latest_close_price(symbol_upper)
            default_price = latest_close if latest_close else 0.0
            
            # Show latest price info
            if latest_close:
                st.caption(f"💡 Latest close: {latest_close:.2f} USDT")
            
            price_help = f"Required for LIMIT orders. Default: Latest close ({default_price:.2f} USDT)" if default_price > 0 else "Required for LIMIT orders"
            price = st.number_input(
                "Price", 
                min_value=0.0, 
                value=default_price, 
                step=0.01, 
                format="%.2f", 
                help=price_help
            )
            # Book selection dropdown
            book_options = load_books_for_dropdown()
            if book_options:
                selected_book_display = st.selectbox(
                    "Book",
                    options=[opt[0] for opt in book_options],
                    index=0 if book_options else None,
                    help="Select book for this order"
                )
                book_id = next((opt[1] for opt in book_options if opt[0] == selected_book_display), "default")
            else:
                book_id = st.text_input("Book ID", value="default", help="Book identifier (fallback if no books loaded)")
        
        notes = st.text_input("Notes (optional)", value="", help="Additional notes for this order")
        
        submitted = st.form_submit_button("Place Order", type="primary")
        
        if submitted:
            if not symbol:
                st.error("Symbol is required")
            elif order_type == "LIMIT" and price <= 0:
                st.error("Price is required for LIMIT orders")
            elif quantity <= 0:
                st.error("Quantity must be greater than 0")
            else:
                order_data = {
                    "symbol": symbol.upper(),
                    "side": side,
                    "order_type": order_type,
                    "quantity": quantity,
                    "book_id": book_id,
                }
                
                if order_type == "LIMIT" and price > 0:
                    order_data["price"] = price
                    order_data["time_in_force"] = "GTC"
                
                if notes:
                    order_data["notes"] = notes
                
                with st.spinner("Placing order..."):
                    result = place_order(order_data)
                
                if result["success"]:
                    st.success("✅ Order placed successfully!")
                    st.json(result["data"])
                else:
                    st.error(f"❌ Failed to place order: {result.get('error', 'Unknown error')}")

# Tab 2: Orders
with tab2:
    st.header("Order History")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        filter_symbol = st.text_input("Filter by Symbol (optional)", value="", placeholder="e.g., BTCUSDT")
    with col2:
        # Book filter dropdown
        book_options = load_books_for_dropdown()
        book_options_with_all = [("All Books", "")] + book_options
        selected_book_filter = st.selectbox(
            "Filter by Book",
            options=[opt[0] for opt in book_options_with_all],
            index=0,
            key="orders_book_filter"
        )
        filter_book_id = next((opt[1] for opt in book_options_with_all if opt[0] == selected_book_filter), None)
    with col3:
        limit = st.number_input("Limit", min_value=1, max_value=500, value=50)
    
    if st.button("Refresh Orders", type="primary"):
        with st.spinner("Loading orders..."):
            result = get_orders(
                symbol=filter_symbol.upper() if filter_symbol else None,
                book_id=filter_book_id if filter_book_id else None,
                limit=limit
            )
        
        if result["success"]:
            orders = result["data"].get("orders", [])
            st.success(f"✅ Found {len(orders)} orders")
            
            if orders:
                # Convert to DataFrame for table display
                orders_data = []
                for order in orders:
                    created_str = ""
                    created_at = order.get('created_at')
                    # Handle both None and 0 values (0 means timestamp not provided)
                    if created_at and created_at > 0:
                        created = datetime.fromtimestamp(created_at / 1000)
                        created_str = created.strftime('%Y-%m-%d %H:%M:%S')
                    elif created_at == 0:
                        created_str = "N/A (timestamp not available)"
                    
                    orders_data.append({
                        "ID": order.get('id'),
                        "Symbol": order.get('symbol', 'N/A'),
                        "Side": order.get('side', 'N/A'),
                        "Type": order.get('order_type', 'N/A'),
                        "Status": order.get('status', 'N/A'),
                        "Quantity": f"{order.get('quantity', 0):.6f}",
                        "Price": f"{order.get('price', 0):.2f}" if order.get('price') else "N/A",
                        "Executed Qty": f"{order.get('executed_qty', 0):.6f}",
                        "Exchange ID": str(order.get('exchange_order_id', 'N/A')),
                        "Book ID": order.get('book_id', 'N/A'),
                        "Created": created_str,
                        "Notes": order.get('notes', '')[:50] + "..." if order.get('notes') and len(order.get('notes', '')) > 50 else order.get('notes', ''),
                    })
                
                df_orders = pd.DataFrame(orders_data)
                st.dataframe(df_orders, use_container_width=True, hide_index=True)
                
                # Cancel buttons for active orders
                active_orders = [o for o in orders if o.get('status') in ['NEW', 'PARTIALLY_FILLED']]
                if active_orders:
                    st.subheader("Cancel Orders")
                    num_cols = min(3, len(active_orders))
                    cancel_cols = st.columns(num_cols)
                    cancel_idx = 0
                    for order in active_orders:
                        with cancel_cols[cancel_idx % num_cols]:
                            if st.button(f"Cancel #{order.get('id')}", key=f"cancel_{order.get('id')}", use_container_width=True):
                                cancel_result = cancel_order(order['id'])
                                if cancel_result["success"]:
                                    st.success("Order cancelled!")
                                    st.rerun()
                                else:
                                    st.error(f"Failed: {cancel_result.get('error')}")
                        cancel_idx += 1
            else:
                st.info("No orders found")
        else:
            st.error(f"❌ Failed to load orders: {result.get('error', 'Unknown error')}")

# Tab 3: Trades
with tab3:
    st.header("Trade History")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        filter_symbol = st.text_input("Filter by Symbol (optional)", value="", key="trade_symbol", placeholder="e.g., BTCUSDT")
    with col2:
        # Book filter dropdown
        book_options = load_books_for_dropdown()
        book_options_with_all = [("All Books", "")] + book_options
        selected_book_filter = st.selectbox(
            "Filter by Book",
            options=[opt[0] for opt in book_options_with_all],
            index=0,
            key="trades_book_filter"
        )
        filter_book_id = next((opt[1] for opt in book_options_with_all if opt[0] == selected_book_filter), None)
    with col3:
        limit = st.number_input("Limit", min_value=1, max_value=500, value=50, key="trade_limit")
    
    if st.button("Refresh Trades", type="primary", key="refresh_trades"):
        with st.spinner("Loading trades..."):
            result = get_trades(
                symbol=filter_symbol.upper() if filter_symbol else None,
                book_id=filter_book_id if filter_book_id else None,
                limit=limit
            )
        
        if result["success"]:
            trades = result["data"].get("trades", [])
            st.success(f"✅ Found {len(trades)} trades")
            
            if trades:
                # Convert to DataFrame for table display
                trades_data = []
                for trade in trades:
                    traded_str = ""
                    if trade.get('traded_at'):
                        traded = datetime.fromtimestamp(trade['traded_at'] / 1000)
                        traded_str = traded.strftime('%Y-%m-%d %H:%M:%S')
                    
                    total_value = trade.get('quantity', 0) * trade.get('price', 0)
                    commission_str = ""
                    if trade.get('commission'):
                        commission_str = f"{trade.get('commission', 0):.6f} {trade.get('commission_asset', '')}"
                    
                    trades_data.append({
                        "ID": trade.get('id'),
                        "Symbol": trade.get('symbol', 'N/A'),
                        "Side": trade.get('side', 'N/A'),
                        "Quantity": f"{trade.get('quantity', 0):.6f}",
                        "Price": f"{trade.get('price', 0):.2f}",
                        "Total": f"{total_value:.2f}",
                        "Commission": commission_str or "N/A",
                        "Order ID": trade.get('order_id', 'N/A'),
                        "Exchange Trade ID": trade.get('exchange_trade_id', 'N/A'),
                        "Book ID": trade.get('book_id', 'N/A'),
                        "Traded At": traded_str,
                    })
                
                df_trades = pd.DataFrame(trades_data)
                st.dataframe(df_trades, use_container_width=True, hide_index=True)
            else:
                st.info("No trades found")
        else:
            st.error(f"❌ Failed to load trades: {result.get('error', 'Unknown error')}")

# Tab 4: Positions
with tab4:
    st.header("Current Positions")
    
    col1, col2 = st.columns(2)
    with col1:
        filter_symbol = st.text_input("Filter by Symbol (optional)", value="", key="pos_symbol", placeholder="e.g., BTCUSDT")
    with col2:
        # Book filter dropdown
        book_options = load_books_for_dropdown()
        book_options_with_all = [("All Books", "")] + book_options
        selected_book_filter = st.selectbox(
            "Filter by Book",
            options=[opt[0] for opt in book_options_with_all],
            index=0,
            key="positions_book_filter"
        )
        filter_book_id = next((opt[1] for opt in book_options_with_all if opt[0] == selected_book_filter), None)
    
    if st.button("Refresh Positions", type="primary", key="refresh_positions"):
        with st.spinner("Loading positions..."):
            result = get_positions(
                symbol=filter_symbol.upper() if filter_symbol else None,
                book_id=filter_book_id if filter_book_id else None
            )
        
        if result["success"]:
            positions = result["data"].get("positions", [])
            st.success(f"✅ Found {len(positions)} positions")
            
            if positions:
                # Convert to DataFrame for table display
                positions_data = []
                for pos in positions:
                    updated_str = ""
                    if pos.get('updated_at'):
                        updated = datetime.fromtimestamp(pos['updated_at'] / 1000)
                        updated_str = updated.strftime('%Y-%m-%d %H:%M:%S')
                    
                    total_value = pos.get('quantity', 0) * pos.get('avg_price', 0) if pos.get('avg_price') else 0
                    
                    positions_data.append({
                        "Symbol": pos.get('symbol', 'N/A'),
                        "Quantity": f"{pos.get('quantity', 0):.6f}",
                        "Avg Price": f"{pos.get('avg_price', 0):.2f}" if pos.get('avg_price') else "N/A",
                        "Total Value": f"{total_value:.2f}" if pos.get('avg_price') else "N/A",
                        "Book ID": pos.get('book_id', 'N/A'),
                        "Venue": pos.get('venue', 'N/A'),
                        "Updated At": updated_str,
                    })
                
                df_positions = pd.DataFrame(positions_data)
                st.dataframe(df_positions, use_container_width=True, hide_index=True)
            else:
                st.info("No positions found")
        else:
            st.error(f"❌ Failed to load positions: {result.get('error', 'Unknown error')}")

# Tab 5: Balances
with tab5:
    st.header("Account Balances")
    
    col1, col2 = st.columns(2)
    with col1:
        filter_asset = st.text_input("Filter by Asset (optional)", value="", key="balance_asset", placeholder="e.g., USDT")
    with col2:
        # Book filter dropdown
        book_options = load_books_for_dropdown()
        book_options_with_all = [("All Books", "")] + book_options
        selected_book_filter = st.selectbox(
            "Filter by Book",
            options=[opt[0] for opt in book_options_with_all],
            index=0,
            key="balances_book_filter"
        )
        filter_book_id = next((opt[1] for opt in book_options_with_all if opt[0] == selected_book_filter), None)
    
    if st.button("Refresh Balances", type="primary", key="refresh_balances"):
        with st.spinner("Loading balances..."):
            result = get_balances(
                asset=filter_asset.upper() if filter_asset else None,
                book_id=filter_book_id if filter_book_id else None
            )
        
        if result["success"]:
            balances = result["data"].get("balances", [])
            st.success(f"✅ Found {len(balances)} balances")
            
            if balances:
                # Convert to DataFrame for table display
                balances_data = []
                for bal in balances:
                    updated_str = ""
                    if bal.get('updated_at'):
                        updated = datetime.fromtimestamp(bal['updated_at'] / 1000)
                        updated_str = updated.strftime('%Y-%m-%d %H:%M:%S')
                    
                    total_balance = bal.get('free', 0) + bal.get('locked', 0)
                    
                    balances_data.append({
                        "Asset": bal.get('asset', 'N/A'),
                        "Free": f"{bal.get('free', 0):.6f}",
                        "Locked": f"{bal.get('locked', 0):.6f}",
                        "Total": f"{total_balance:.6f}",
                        "Book ID": bal.get('book_id', 'N/A'),
                        "Venue": bal.get('venue', 'N/A'),
                        "Updated At": updated_str,
                    })
                
                df_balances = pd.DataFrame(balances_data)
                st.dataframe(df_balances, use_container_width=True, hide_index=True)
                
                # Summary by asset
                if balances:
                    st.subheader("Summary by Asset")
                    asset_summary = {}
                    for bal in balances:
                        asset = bal.get('asset', 'UNKNOWN')
                        if asset not in asset_summary:
                            asset_summary[asset] = {'free': 0.0, 'locked': 0.0}
                        asset_summary[asset]['free'] += bal.get('free', 0)
                        asset_summary[asset]['locked'] += bal.get('locked', 0)
                    
                    summary_data = []
                    for asset, totals in asset_summary.items():
                        summary_data.append({
                            "Asset": asset,
                            "Total Free": f"{totals['free']:.6f}",
                            "Total Locked": f"{totals['locked']:.6f}",
                            "Grand Total": f"{totals['free'] + totals['locked']:.6f}",
                        })
                    
                    df_summary = pd.DataFrame(summary_data)
                    st.dataframe(df_summary, use_container_width=True, hide_index=True)
            else:
                st.info("No balances found")
        else:
            st.error(f"❌ Failed to load balances: {result.get('error', 'Unknown error')}")

# Tab 6: Admin
with tab6:
    st.header("Admin Functions")
    st.warning("⚠️ Admin functions - use with caution")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Rebuild Positions")
        st.caption("Rebuild positions table from trades")
        if st.button("Rebuild Positions", type="primary", key="rebuild_pos"):
            with st.spinner("Rebuilding positions..."):
                result = rebuild_positions()
            if result["success"]:
                st.success("✅ Positions rebuilt successfully!")
                st.json(result["data"])
            else:
                st.error(f"❌ Failed: {result.get('error', 'Unknown error')}")
    
    with col2:
        st.subheader("Rebuild Balances")
        st.caption("Rebuild balances table from trades")
        if st.button("Rebuild Balances", type="primary", key="rebuild_bal"):
            with st.spinner("Rebuilding balances..."):
                result = rebuild_balances()
            if result["success"]:
                st.success("✅ Balances rebuilt successfully!")
                st.json(result["data"])
            else:
                st.error(f"❌ Failed: {result.get('error', 'Unknown error')}")

# Tab 7: Book Management
with tab7:
    st.header("📚 Book Management")
    st.caption("Create, edit, and manage trading books")
    
    # Load books for display
    if st.button("Refresh Books", type="primary", key="refresh_books"):
        st.rerun()
    
    # Get books
    result = get_books(venue=settings.venue, active_only=False)
    
    if result["success"]:
        books = result["data"].get("books", [])
        st.success(f"✅ Found {len(books)} books")
        
        # Create Book Form
        with st.expander("➕ Create New Book", expanded=False):
            with st.form("create_book_form"):
                col1, col2 = st.columns(2)
                with col1:
                    new_book_id = st.text_input("Book ID *", value="", help="Lowercase, alphanumeric + underscores (e.g., test_book)")
                    new_book_name = st.text_input("Book Name *", value="", help="Display name (e.g., Test Book)")
                    new_venue = st.selectbox("Venue", options=[settings.venue], index=0)
                with col2:
                    new_description = st.text_area("Description", value="", help="Optional description")
                    new_notes = st.text_area("Notes", value="", help="Optional notes")
                
                create_submitted = st.form_submit_button("Create Book", type="primary")
                
                if create_submitted:
                    if not new_book_id or not new_book_name:
                        st.error("Book ID and Name are required")
                    else:
                        book_data = {
                            "id": new_book_id.lower().strip(),
                            "name": new_book_name.strip(),
                            "venue": new_venue,
                            "description": new_description.strip() if new_description else None,
                            "notes": new_notes.strip() if new_notes else None,
                        }
                        
                        with st.spinner("Creating book..."):
                            create_result = create_book(book_data)
                        
                        if create_result["success"]:
                            st.success("✅ Book created successfully!")
                            st.json(create_result["data"])
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to create book: {create_result.get('error', 'Unknown error')}")
        
        # Books List
        if books:
            st.subheader("Books List")
            for book in books:
                status_color = "🟢" if book.get("is_active") else "🔴"
                status_text = "Active" if book.get("is_active") else "Inactive"
                
                with st.expander(f"{status_color} {book.get('name')} ({book.get('id')}) - {status_text}"):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.write(f"**ID:** {book.get('id')}")
                        st.write(f"**Name:** {book.get('name')}")
                        st.write(f"**Venue:** {book.get('venue')}")
                        if book.get('description'):
                            st.write(f"**Description:** {book.get('description')}")
                        if book.get('notes'):
                            st.write(f"**Notes:** {book.get('notes')}")
                        if book.get('created_at'):
                            created = datetime.fromtimestamp(book['created_at'] / 1000)
                            st.caption(f"Created: {created.strftime('%Y-%m-%d %H:%M:%S')}")
                        if book.get('created_by'):
                            st.caption(f"Created by: {book.get('created_by')}")
                    
                    with col2:
                        # Edit form
                        with st.form(f"edit_book_{book.get('id')}"):
                            edit_name = st.text_input("Name", value=book.get('name', ''), key=f"edit_name_{book.get('id')}")
                            edit_description = st.text_area("Description", value=book.get('description') or '', key=f"edit_desc_{book.get('id')}")
                            edit_is_active = st.checkbox("Active", value=book.get('is_active', True), key=f"edit_active_{book.get('id')}")
                            edit_notes = st.text_area("Notes", value=book.get('notes') or '', key=f"edit_notes_{book.get('id')}")
                            
                            col_edit1, col_edit2 = st.columns(2)
                            with col_edit1:
                                if st.form_submit_button("💾 Update", use_container_width=True):
                                    update_data = {
                                        "name": edit_name.strip(),
                                        "description": edit_description.strip() if edit_description else None,
                                        "is_active": edit_is_active,
                                        "notes": edit_notes.strip() if edit_notes else None,
                                    }
                                    
                                    with st.spinner("Updating book..."):
                                        update_result = update_book(book.get('id'), update_data)
                                    
                                    if update_result["success"]:
                                        st.success("✅ Book updated!")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Failed: {update_result.get('error')}")
                            
                            with col_edit2:
                                if st.form_submit_button("🗑️ Deactivate" if book.get('is_active') else "✅ Activate", use_container_width=True):
                                    # Toggle active status
                                    toggle_result = update_book(book.get('id'), {"is_active": not book.get('is_active')})
                                    if toggle_result["success"]:
                                        st.success("✅ Book status updated!")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Failed: {toggle_result.get('error')}")
        else:
            st.info("No books found. Create your first book using the form above.")
    else:
        st.error(f"❌ Failed to load books: {result.get('error', 'Unknown error')}")
