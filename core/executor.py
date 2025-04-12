# file: core/executor.py
from pathlib import Path
import time
import json
import argparse

from core.api_client import get_market_data, place_order, get_account
from core.strategy import simple_sma_strategy, limit_order_price

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

user_id = config["user_id"]
symbol = config["symbol"]
quantity = config["quantity"]
auth = (str(user_id), config["password"])

def run_trading_loop(interval=60):
    last_signal = None
    print(f"[{timestamp()}] 🌀 Starting trading loop on {symbol}, interval = {interval}s")

    while True:
        market_data = get_market_data(symbol, auth)
        if not market_data or "stock" not in market_data:
            print(f"[{timestamp()}] ⚠️ Skipping iteration: bad market data")
            time.sleep(interval)
            continue

        current_price = market_data["stock"]["price"]

        # 👁 Show account snapshot
        acc = get_account(auth)
        if acc:
            shares = acc["positions"].get(symbol, 0)
            print(f"[{timestamp()}] 💼 Account: Cash = ${acc['cash']:.2f} | {symbol} = {shares} | Net Worth = ${acc['net_worth']:.2f}")

        print(f"[{timestamp()}] 💲 Current Price: {current_price:.2f}")

        try:
            signal = simple_sma_strategy(symbol)
        except Exception as e:
            print(f"[{timestamp()}] ❌ Strategy Error: {e}")
            time.sleep(interval)
            continue

        print(f"[{timestamp()}] 📊 Strategy Signal: {signal}")

        if signal != last_signal and signal in ["buy", "sell"]:
            limit_price = limit_order_price(signal, current_price)
            print(f"[{timestamp()}] 📥 Placing LIMIT order to {signal.upper()} {quantity} at ${limit_price:.2f}")

            response = place_order(
                user_id=user_id,
                symbol=symbol,
                side=signal,
                quantity=quantity,
                order_type="limit",
                limit_price=limit_price,
                auth=auth
            )
            print(f"[{timestamp()}] ✅ Order Response: {response}")
            last_signal = signal
        else:
            print(f"[{timestamp()}] ⏸ No signal change, no action taken.")

        time.sleep(interval)

def timestamp():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# CLI: python -m core.executor --live
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run live trading loop")
    args = parser.parse_args()

    if args.live:
        run_trading_loop()
    else:
        result = simple_sma_strategy(symbol)
        if result in ["buy", "sell"]:
            print(f"[{timestamp()}] 🧪 Signal: {result} — would place limit order at {limit_order_price(result, 100)}")
        else:
            print(f"[{timestamp()}] 🧪 Manual test result: {result}")
