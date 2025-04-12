from pathlib import Path
import streamlit as st
import json, time, os
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path
from core.api_client import get_account, get_market_data, place_order, cancel_all_orders
from core.strategy_selector import select_strategy
from core.strategy import (
    compute_position_size,
    limit_order_price,
    confirm_with_orderbook_pressure,
    confirm_with_volatility_band,
    compute_dynamic_weighted_sma  # Importing the dynamic SMA function
)
from core.logger import log_trade  # Import the logging function

# --- Config ---
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
LOG_PATH = "logs/trades.csv"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)
user_id = config["user_id"]
symbol = config["symbol"]
strategy_name = config.get("strategy", "multi_sma")
auth = (str(user_id), config["password"])
strategy_fn, strategy_params = select_strategy(strategy_name)

# --- Page Setup ---
st.set_page_config(page_title="Unified AlgoTrader Dashboard", layout="wide")
st.sidebar.title("📊 Navigation")
view = st.sidebar.radio("Select view", ["📈 Live Dashboard", "📚 Trade History"])

# === View 1: LIVE DASHBOARD ===
if view == "📈 Live Dashboard":
    st.title("📈 Real-Time Trading Dashboard")
    account = get_account(auth)
    market_data = get_market_data(symbol, auth)

    # Fetch current volatility and calculate dynamic weighted SMA
    volatility = market_data["stock"]["volatility"]
    weighted_sma = compute_dynamic_weighted_sma(symbol, auth, short_period=10, long_period=20, volatility=volatility)

    # Fetch current price and check if it's valid (i.e., not None)
    current_price = market_data["stock"].get("price")

    # Debugging: Log the values to see why they might be None
    st.write(f"Current Price: {current_price}, Weighted SMA: {weighted_sma}")

    # Add validation for None values
    if current_price is None:
        st.warning("Current price is missing.")
        current_price = 0  # Fallback value (or another appropriate value)
    
    if weighted_sma is None:
        st.warning("Weighted SMA is missing.")
        weighted_sma = 0  # Fallback value (or another appropriate value)
    
    # Signal generation based on the weighted SMA
    signal = "buy" if current_price > weighted_sma else "sell"

    cash = float(account.get("cash", 0))
    position = account.get("open_positions", {}).get(symbol, 0)
    net_worth = account.get("networth", cash + position * current_price)
    orderbook = market_data.get("orderbook", {})

    # Display account, market, and signal metrics
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

    # Signal explanation with the dynamic weighted SMA logic
    st.markdown("### 🔍 Signal Explanation")
    explanation = ""
    confirmed = True
    band_check = confirm_with_volatility_band(current_price, current_price, volatility)
    if band_check != signal:
        explanation += "❌ Rejected by volatility band filter\n"
        confirmed = False
    ob_check = confirm_with_orderbook_pressure(orderbook, signal)
    if not ob_check:
        explanation += "❌ Rejected by order book pressure filter\n"
        confirmed = False
    if confirmed and signal in ["buy", "sell"]:
        explanation += f"✅ {signal.upper()} confirmed by Weighted SMA, volatility, and orderbook."
    else:
        explanation += f"💤 Holding — blocked by filters or SMA."
    st.code(explanation.strip(), language="markdown")

    with st.expander("📚 Order Book"):
        st.write("🔵 Buy Orders")
        st.json(orderbook.get("buy_orders", []))
        st.write("🔴 Sell Orders")
        st.json(orderbook.get("sell_orders", []))

    with st.expander("🐞 Raw Orderbook Data"):
        st.json(orderbook)

    st.markdown("### 📊 Order Book Depth Chart")
    buy_levels = orderbook.get("buy_orders", [])
    sell_levels = orderbook.get("sell_orders", [])
    buy_prices = [level.get("price") for level in buy_levels if "price" in level]
    buy_volumes = [level.get("volume", level.get("quantity", 0)) for level in buy_levels]
    sell_prices = [level.get("price") for level in sell_levels if "price" in level]
    sell_volumes = [level.get("volume", level.get("quantity", 0)) for level in sell_levels]
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

    # Manual Signal Override
    st.markdown("### 🎮 Manual Signal Override")
    override_col1, override_col2, override_col3 = st.columns(3)
    override_result = ""

    def handle_manual_order(side):
        qty = compute_position_size(cash, current_price, volatility)
        order_type = "market" if volatility > 0.08 else "limit"
        limit_price = None if order_type == "market" else limit_order_price(side, current_price)
        response = place_order(user_id=user_id, symbol=symbol, side=side, quantity=qty, order_type=order_type, limit_price=limit_price, auth=auth)

        # Log the trade after it is placed
        log_trade(symbol=symbol, side=side, quantity=qty, price=current_price, volatility=volatility, order_type=order_type, cash=cash, net_worth=net_worth)

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

    st.caption("⏳ Auto-refreshes every 60 seconds")
    time.sleep(60)
    st.rerun()

# === View 2: TRADE LOG ===
elif view == "📚 Trade History":
    st.title("📚 Trade History")

    # Check if trade logs exist
    if not os.path.exists(LOG_PATH):
        st.warning("No trades logged yet.")
        st.stop()

    # Load and prepare data
    df = pd.read_csv(LOG_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.sort_values("timestamp", ascending=False, inplace=True)

    # Add color-coded metrics for profit/loss
    latest_trade = df.iloc[0]
    profit_loss = latest_trade["net_worth"] - latest_trade["cash"]

    st.metric("🕒 Last Trade", latest_trade["timestamp"].strftime("%Y-%m-%d %H:%M:%S"))
    st.metric("📈 Last Price", f"${latest_trade['price']:.2f}")
    st.metric("📦 Last Position Size", f"{latest_trade['quantity']} {latest_trade['symbol']}")
    st.metric("💰 Net Worth", f"${latest_trade['net_worth']:.2f}")
    st.metric("⚡ Volatility", f"{latest_trade['volatility']:.2%}")
    st.metric("💸 Cash", f"${latest_trade['cash']:.2f}")
    st.metric("📐 Order Type", latest_trade["order_type"].upper())
    st.metric("🔁 Trade Direction", latest_trade["side"].upper())

    # Adding profit/loss with color feedback
    if profit_loss >= 0:
        st.metric("💵 Profit/Loss", f"+${profit_loss:.2f}", delta_color="normal")  # "normal" for positive values
    else:
        st.metric("💵 Profit/Loss", f"${profit_loss:.2f}", delta_color="inverse")  # "inverse" for negative values

    # Filter options for better interaction
    st.markdown("### 🔎 Filter Trade History")
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        start_date = st.date_input("Start Date", df["timestamp"].min())
    with filter_col2:
        end_date = st.date_input("End Date", df["timestamp"].max())
    with filter_col3:
        order_type = st.selectbox("Order Type", df["order_type"].unique())

    # Filter the data based on user input
    filtered_df = df[
        (df["timestamp"] >= pd.to_datetime(start_date)) & 
        (df["timestamp"] <= pd.to_datetime(end_date)) & 
        (df["order_type"] == order_type)
    ]

    st.dataframe(filtered_df, use_container_width=True)

    # Plotting net worth over time
    st.markdown("### 📊 Net Worth Over Time")
    df_chart = df.copy().sort_values("timestamp")
    st.line_chart(df_chart.set_index("timestamp")[["net_worth"]])

    # Scatter plot for Profit/Loss by date
    st.markdown("### 📈 Profit/Loss Scatter")
    df['profit_loss'] = df["net_worth"] - df["cash"]
    st.scatter_chart(df.set_index("timestamp")[["profit_loss"]])
