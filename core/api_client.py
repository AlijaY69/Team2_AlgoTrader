import requests
from requests.auth import HTTPBasicAuth
import time

BASE_URL = "http://82.29.197.23:8000"
USER_ID = "2"
PASSWORD = "Ahojpepiku45"
auth = HTTPBasicAuth(USER_ID, PASSWORD)

def get_stocks():
    return requests.get(f"{BASE_URL}/stocks", auth=auth).json()

def get_stock_history(symbol, interval="5m", points=50):
    params = {"interval": interval, "points": points}
    return requests.get(f"{BASE_URL}/stocks/{symbol}/history", params=params, auth=auth).json()

def get_market_data(symbol, auth):
    try:
        stock_resp = requests.get(f"{BASE_URL}/stocks", auth=HTTPBasicAuth(*auth))
        orderbook_resp = requests.get(f"{BASE_URL}/orderbook/?symbol={symbol}", auth=HTTPBasicAuth(*auth))
        return {
            "stock": next((s for s in stock_resp.json() if s["symbol"] == symbol), None),
            "orderbook": orderbook_resp.json()
        }
    except Exception as e:
        print(f"❌ Error fetching market data: {e}")
        return None

def get_account(auth):
    try:
        resp = requests.get(f"{BASE_URL}/accounts/{USER_ID}", auth=HTTPBasicAuth(*auth))
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"❌ Error fetching account: {e}")
        return None

def place_order(user_id, symbol, side, quantity, order_type="market", limit_price=None, auth=None):
    data = {
        "user_id": user_id,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type
    }
    if order_type == "limit":
        data["limit_price"] = limit_price

    try:
        resp = requests.post(f"{BASE_URL}/orders/", json=data, auth=HTTPBasicAuth(*auth))
        resp.raise_for_status()
        if resp.status_code == 400:  # Handle API overloads and rate-limits
            print(f"⚠️ Rate limit hit or bad request: {resp.text}")
            time.sleep(2)  # Add some delay if necessary
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Order failed: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}")
        return None

def cancel_all_orders_aggressively(auth):
    """ Aggressively cancel all orders but with rate limits to avoid overwhelming the API. """
    orders = get_orders(auth)
    if not orders:
        print("No orders to cancel.")
        return
    for order in orders:
        order_id = order.get("order_id")
        if order_id:
            cancel_order(order_id, auth)
            time.sleep(0.15)  # Aggressive but more controlled cancellation interval
        else:
            print("⚠️ Missing order ID for cancellation.")
    print("✅ All orders attempted for cancellation.")


def get_orders(auth):
    """ Fetch all open orders to process cancellation. """
    try:
        orders_resp = requests.get(f"{BASE_URL}/orders", auth=auth)
        orders_resp.raise_for_status()
        return orders_resp.json()  # List of active orders
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching orders: {e}")
        return []

def cancel_order(order_id, auth):
    """ Attempt to cancel a single order using DELETE method. """
    try:
        resp = requests.delete(f"{BASE_URL}/orders/{order_id}/cancel", auth=auth)
        resp.raise_for_status()
        print(f"❎ Canceled order: {order_id}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to cancel order {order_id}: {e}")

def cancel_all_orders(auth):
    """ Cancel all orders one by one. """
    orders = get_orders(auth)
    if not orders:
        print("No orders to cancel.")
        return
    for order in orders:
        order_id = order.get("order_id")
        if order_id:
            cancel_order(order_id, auth)
        else:
            print("⚠️ Missing order ID for cancellation.")
    print("✅ All orders attempted for cancellation.")

