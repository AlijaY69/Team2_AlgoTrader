# core/executor.py
import time
import json
import pandas as pd
from core.api_client import get_market_data, place_order
from core.strategy import simple_sma_strategy

with open("config.json", "r") as f:
    config = json.load(f)

symbol = config["symbol"]
quantity = config["quantity"]

def run_trading_loop(interval=60):
    last_signal = None
    print(f"🚀 Starting strategy loop on {symbol} every {interval}s...\n")

    while True:
        signal = simple_sma_strategy(symbol)
        print(f"📊 Signal: {signal}")

        if signal != last_signal and signal in ["buy", "sell"]:
            print(f"🛒 Executing market order: {signal.upper()} {quantity} {symbol}")
            result = place_order(symbol, side=signal, quantity=quantity)
            print(f"✅ Order Result: {result}\n")
            last_signal = signal
        else:
            print("⏸ No trade executed.\n")

        time.sleep(interval)

# Optional: run once for debug
if __name__ == "__main__":
    print("🧪 Manual test result:", simple_sma_strategy(symbol))
