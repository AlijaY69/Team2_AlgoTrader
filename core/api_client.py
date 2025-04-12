# file: core/api_client.py
import requests
from requests.auth import HTTPBasicAuth

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
    # Combines stock data and orderbook
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

def get_account():
    return requests.get(f"{BASE_URL}/accounts/{USER_ID}", auth=auth).json()

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
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Order failed: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}")
        return None
