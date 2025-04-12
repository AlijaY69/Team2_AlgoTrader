# file: core/executor.py
import time, json, argparse
from pathlib import Path
import pandas as pd

from core.api_client import get_market_data, place_order, get_account
from core.strategy_selector import select_strategy
from core.strategy import compute_position_size, orderbook_pressure  # ✅ Added orderbook_pressure

# 🧾 Load config
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

user_id = config["user_id"]
symbol = config["symbol"]
strategy_name = config.get("strategy", "simple_sma")
interval = config.get("interval", 60)
auth = (str(user_id), config["password"])

strategy_fn, strategy_params = select_strategy(strategy_name)

# 🌀 Real-time trading loop
def run_trading_loop(interval=60):
    last_signal = None
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🌀 Starting trading loop on {symbol}, interval = {interval}s")

    while True:
        account = get_account(auth)
        cash = float(account.get("cash", 0))
        position = account.get("positions", {}).get(symbol, 0)
        net_worth = cash + position * account.get("stock_prices", {}).get(symbol, 0)

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 💼 Account: Cash = ${cash:.2f} | {symbol} = {position} | Net Worth = ${net_worth:.2f}")

        market_data = get_market_data(symbol, auth)
        if not market_data or "stock" not in market_data:
            print("⚠️ Skipping iteration due to failed market data fetch.")
            time.sleep(interval)
            continue

        current_price = market_data["stock"]["price"]
        volatility = market_data["stock"].get("volatility", 0)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 💲 Current Price: {current_price:.2f}")

        try:
            signal = strategy_fn(symbol, **strategy_params)
        except Exception as e:
            print(f"❌ Strategy Error: {e}")
            time.sleep(interval)
            continue

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📊 Strategy Signal: {signal}")

        # 🧭 Adjust signal based on orderbook pressure
        pressure = orderbook_pressure(market_data["orderbook"])
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🧭 Orderbook Pressure: {pressure}")

        if pressure == "buy" and signal == "sell":
            print("⚠️ SELL signal overridden by BUY pressure → holding")
            signal = "hold"
        elif pressure == "sell" and signal == "buy":
            print("⚠️ BUY signal overridden by SELL pressure → holding")
            signal = "hold"

        if signal != last_signal and signal in ["buy", "sell"]:
            quantity = compute_position_size(cash, current_price, volatility)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📐 Quantity Computed: {quantity} (Volatility = {volatility:.3f})")

            if signal == "sell" and position == 0:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Cannot SELL — you hold 0 shares.")
            else:
                response = place_order(
                    user_id=user_id,
                    symbol=symbol,
                    side=signal,
                    quantity=quantity,
                    order_type="market",
                    auth=auth
                )
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ Order response: {response}")
                last_signal = signal
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⏸ No signal change, no action taken.")

        time.sleep(interval)

# 🧠 CLI support
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run in continuous trading mode")
    args = parser.parse_args()

    if args.live:
        run_trading_loop(interval)
    else:
        signal = strategy_fn(symbol, **strategy_params)
        if signal in ["buy", "sell"]:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🧪 Would {signal.upper()} now!")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🧪 Manual test result: {signal}")
