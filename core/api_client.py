# core/api_client.py
import requests
from requests.auth import HTTPBasicAuth
import json
import os

# Load credentials from config
with open("config.json", "r") as f:
    config = json.load(f)

BASE_URL = config["base_url"]
USER_ID = str(config["user_id"])
PASSWORD = config["password"]

auth = HTTPBasicAuth(USER_ID, PASSWORD)

def get_stock_history(symbol, interval="5m", points=50):
    params = {"interval": interval, "points": points}
    url = f"{BASE_URL}/stocks/{symbol}/history"
    try:
        response = requests.get(url, params=params, auth=auth)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"⚠️ Error fetching history for {symbol}: {e}")
        return []

def get_market_data(symbol):
    try:
        response = requests.get(f"{BASE_URL}/stocks", auth=auth)
        response.raise_for_status()
        stocks = response.json()
        return next((s for s in stocks if s["symbol"] == symbol), None)
    except requests.RequestException as e:
        print(f"⚠️ Error fetching market data: {e}")
        return None

def place_order(symbol, side, quantity, order_type="market", limit_price=None):
    payload = {
        "user_id": USER_ID,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type
    }
    if order_type == "limit":
        payload["limit_price"] = limit_price

    try:
        response = requests.post(f"{BASE_URL}/orders/", json=payload, auth=auth)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"❌ Order failed: {e}")
        return None
