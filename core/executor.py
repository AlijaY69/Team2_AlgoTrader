# file: core/executor.py
from pathlib import Path
import time
import json
import pandas as pd
import sys

from core.api_client import get_market_data, place_order, get_account
from core.strategy import simple_sma_strategy, limit_order_price

# Load config
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

user_id = config["user_id"]
symbol = config["symbol"]
quantity = config["quantity"]
auth = (str(user_id), config["password"])

def run_trading_loop(interval=60):
    last_signal = None
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🌀 Starting trading loop on {symbol}, interval = {interval}s")

    while True:
        market_data = get_market_data(symbol, auth)
        if not market_data or "stock" not in market_data:
            print("⚠️ Skipping iteration due to failed market data fetch.")
            time.sleep(interval)
            continue

        current_price = market_data["stock"]["price"]
        print(f"💲 Current Price: {current_price}")

        try:
            signal = simple_sma_strategy(symbol)
        except Exception as e:
            print(f"❌ Strategy Error: {e}")
            time.sleep(interval)
            continue

        print(f"📊 Strategy Signal: {signal}")

        if signal != last_signal and signal in ["buy", "sell"]:
            limit_price = limit_order_price(signal, current_price)
            print(f"📥 Placing LIMIT order to {signal.upper()} {quantity} at ${limit_price:.2f}")

            response = place_order(
                user_id=user_id,
                symbol=symbol,
                side=signal,
                quantity=quantity,
                order_type="limit",
                limit_price=limit_price,
                auth=auth
            )
            print(f"✅ Order Response: {response}")
            last_signal = signal
        else:
            print("⏸ No signal change, no action taken.")

        time.sleep(interval)

# 🧪 CLI ARG HANDLER
if __name__ == "__main__":
    if "--live" in sys.argv:
        run_trading_loop()
    else:
        result = simple_sma_strategy(symbol)
        if result in ["buy", "sell"]:
            dummy_price = 100
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🧪 Signal: {result} — would place limit at {limit_order_price(result, dummy_price):.2f}")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🧪 Manual test result: {result}")
