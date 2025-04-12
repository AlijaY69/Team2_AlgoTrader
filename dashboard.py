# file: dashboard.py
import streamlit as st
import json, time
import matplotlib.pyplot as plt
from pathlib import Path
from core.api_client import get_account, get_market_data, place_order, cancel_all_orders
from core.strategy_selector import select_strategy
from core.strategy import (
    compute_position_size,
    limit_order_price,
    confirm_with_orderbook_pressure,
    confirm_with_volatility_band,
)

# --- Load Config ---
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

user_id = config["user_id"]
symbol = config["symbol"]
strategy_name = config.get("strategy", "simple_sma")
auth = (str(user_id), config["password"])
strategy_fn, strategy_params = select_strategy(strategy_name)

# --- Layout ---
st.set_page_config(page_title="AlgoTrader Dashboard", layout="wide")
st.title("📈 Real-Time Trading Dashboard")

# --- Load Data ---
account = get_account(auth)
market_data = get_market_data(symbol, auth)
signal = strategy_fn(symbol, **strategy_params)

cash = float(account.get("cash", 0))
position = account.get("open_positions", {}).get(symbol, 0)
current_price = market_data["stock"]["price"]
volatility = market_data["stock"]["volatility"]
orderbook = market_data.get("orderbook", {})
net_worth = account.get("networth", cash + position * current_price)

# --- Columns ---
col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("💼 Account")
    st.metric("Cash", f"${cash:.2f}")
    st.metric(f"Position: {symbol}", position)
    st.metric("Net Worth", f"${net_worth:.2f}")

with col2:
    st.subheader("💲 Market")
    st.metric("Current Price", f"${current_price:.2f}")
    st.metric("Volatility", f"{volatility:.2%}")

with col3:
    st.subheader("🧠 Signal")
    st.metric("Last Signal", signal.upper())

# --- Signal Explanation ---
st.markdown("### 🔍 Signal Explanation")
explanation = ""
confirmed = True

sma_long = strategy_params.get("sma_long") or strategy_params.get("long", 20)
band_check = confirm_with_volatility_band(current_price, current_price, volatility)
if band_check != signal:
    explanation += "❌ Rejected by volatility band filter\n"
    confirmed = False

ob_check = confirm_with_orderbook_pressure(orderbook, signal)
if not ob_check:
    explanation += "❌ Rejected by order book pressure filter\n"
    confirmed = False

if confirmed and signal in ["buy", "sell"]:
    explanation += f"✅ {signal.upper()} signal confirmed by SMA crossover, volatility, and orderbook."
else:
    explanation += f"💤 Holding — SMA or filter(s) blocked trade."

st.code(explanation.strip(), language="markdown")

# --- Order Book View ---
with st.expander("📚 Order Book"):
    st.write("🔵 Buy Orders")
    st.json(orderbook.get("buy_orders", []))
    st.write("🔴 Sell Orders")
    st.json(orderbook.get("sell_orders", []))

# --- Raw Debugging (for sanity check) ---
with st.expander("🐞 Raw Orderbook Data"):
    st.json(orderbook)

# --- Depth Chart ---
st.markdown("### 📊 Order Book Depth Chart")

# Parse correct keys
buy_levels = orderbook.get("buy_orders", [])
sell_levels = orderbook.get("sell_orders", [])

# Extract and sort safely
buy_prices = [level.get("price") for level in buy_levels if "price" in level]
buy_volumes = [level.get("volume", level.get("quantity", 0)) for level in buy_levels]
sell_prices = [level.get("price") for level in sell_levels if "price" in level]
sell_volumes = [level.get("volume", level.get("quantity", 0)) for level in sell_levels]

# Ensure non-empty
if buy_prices and sell_prices:
    buy_sorted = sorted(zip(buy_prices, buy_volumes), key=lambda x: -x[0])
    sell_sorted = sorted(zip(sell_prices, sell_volumes), key=lambda x: x[0])

    buy_prices_sorted, buy_volumes_sorted = zip(*buy_sorted)
    sell_prices_sorted, sell_volumes_sorted = zip(*sell_sorted)

    buy_cumvol = [sum(buy_volumes_sorted[:i+1]) for i in range(len(buy_volumes_sorted))]
    sell_cumvol = [sum(sell_volumes_sorted[:i+1]) for i in range(len(sell_volumes_sorted))]

    fig, ax = plt.subplots()
    ax.step(buy_prices_sorted, buy_cumvol, label="Buy (Demand)", where="post", color='green')
    ax.step(sell_prices_sorted, sell_cumvol, label="Sell (Supply)", where="post", color='red')
    ax.set_xlabel("Price ($)")
    ax.set_ylabel("Cumulative Volume")
    ax.set_title("Order Book Depth")
    ax.legend()
    st.pyplot(fig)
else:
    st.warning("⚠️ No valid order book data available to plot.")

# --- Manual Override ---
st.markdown("### 🎮 Manual Signal Override")
override_col1, override_col2, override_col3 = st.columns(3)
override_result = ""

def handle_manual_order(side):
    qty = compute_position_size(cash, current_price, volatility)
    order_type = "market" if volatility > 0.08 else "limit"
    limit_price = None if order_type == "market" else limit_order_price(side, current_price)
    response = place_order(
        user_id=user_id,
        symbol=symbol,
        side=side,
        quantity=qty,
        order_type=order_type,
        limit_price=limit_price,
        auth=auth
    )
    return f"{side.upper()} order sent (qty={qty}, type={order_type}) → {response}"

with override_col1:
    if st.button("📥 Force BUY"):
        override_result = handle_manual_order("buy")
with override_col2:
    if st.button("📤 Force SELL"):
        if position > 0:
            override_result = handle_manual_order("sell")
        else:
            override_result = "⚠️ Cannot SELL — No holdings!"
with override_col3:
    if st.button("🛑 Cancel ALL"):
        result = cancel_all_orders(auth)
        if result.get("status") == "success":
            override_result = f"✅ Cancelled all orders: {result.get('canceled', [])}"
        else:
            override_result = f"❌ Failed to cancel orders: {result}"

if override_result:
    st.success(override_result)

# --- Refresh ---
st.caption("⏳ Auto-refreshes every 60 seconds")
time.sleep(60)
st.rerun()
