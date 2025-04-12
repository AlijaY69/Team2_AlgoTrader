# file: core/executor.py
import time, json, argparse
from pathlib import Path
from core.api_client import get_market_data, place_order, get_account, cancel_order
from core.strategy_selector import select_strategy
from core.strategy import (
    compute_position_size,
    limit_order_price,
    confirm_with_orderbook_pressure,
    confirm_with_volatility_band
)
from core.logger import log_trade

# --- CONFIG LOAD ---
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

user_id = config["user_id"]
symbol = config["symbol"]
strategy_name = config.get("strategy", "multi_sma")
interval = config.get("interval", 60)
stale_limit_lifetime = config.get("limit_lifetime", 180)
auth = (str(user_id), config["password"])

strategy_fn, strategy_params = select_strategy(strategy_name)

last_signal = None
last_price = None
pending_limit_order_id = None
pending_limit_timestamp = None

# --- MAIN LOOP ---
def run_trading_loop(interval=60):
    global last_signal, last_price, pending_limit_order_id, pending_limit_timestamp
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🌀 Starting trading loop on {symbol}, interval = {interval}s")

    while True:
        account = get_account(auth)
        cash = float(account.get("cash", 0))
        positions = account.get("open_positions") or account.get("positions") or {}
        position = positions.get(symbol, 0)

        market_data = get_market_data(symbol, auth)
        if not market_data or "stock" not in market_data:
            print("⚠️ Skipping iteration due to failed market data fetch.")
            time.sleep(interval)
            continue

        current_price = market_data["stock"]["price"]
        volatility = market_data["stock"].get("volatility", 0)
        net_worth = float(account.get("networth", cash + position * current_price))
        orderbook = market_data.get("orderbook", {})

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 💼 Account: Cash = ${cash:.2f} | {symbol} = {position} | Net Worth = ${net_worth:.2f}")
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 💲 Current Price: {current_price:.2f}")

        try:
            signal = strategy_fn(symbol, **strategy_params)
        except Exception as e:
            print(f"❌ Strategy Error: {e}")
            time.sleep(interval)
            continue

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📊 Strategy Signal: {signal}")

        # Cancel stale orders
        if pending_limit_order_id and time.time() - pending_limit_timestamp > stale_limit_lifetime:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Cancelling stale LIMIT order ID {pending_limit_order_id}")
            cancel_order(pending_limit_order_id, auth)
            pending_limit_order_id = None
            pending_limit_timestamp = None
            last_signal = None

        # Only act if signal has changed
        if signal != last_signal and signal in ["buy", "sell"]:
            has_held_long = position > 0 and net_worth < (cash + position * current_price * 0.995)
            signal_strength = abs(volatility) * 100
            price_delta = abs((last_price or current_price) - current_price) / current_price
            loosen_filters = signal_strength > 1.5 or has_held_long or price_delta > 0.01

            print(f"[FILTER] Loosened: {loosen_filters} | ΔPrice: {price_delta:.4f} | Held Long: {has_held_long}")

            band_confirm = confirm_with_volatility_band(current_price, current_price, volatility)
            ob_confirm = confirm_with_orderbook_pressure(orderbook, signal)

            print(f"[FILTER CHECK] Band: {band_confirm} | OB: {ob_confirm} | Raw: {signal}")

            if not loosen_filters and band_confirm != signal:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ Blocked by volatility band")
                continue

            if not loosen_filters and not ob_confirm:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ Blocked by orderbook pressure")
                continue

            quantity = compute_position_size(cash, current_price, volatility)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📐 Quantity: {quantity} | Volatility: {volatility:.3f}")

            if signal == "sell" and position == 0:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Cannot SELL — you hold 0 shares.")
                continue

            if volatility > 0.08:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⚡ Using MARKET order (High Volatility)")
                order_type = "market"
                limit_price = None
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🧠 Using LIMIT order (Low Volatility)")
                order_type = "limit"
                limit_price = limit_order_price(signal, current_price)

            response = place_order(
                user_id=user_id,
                symbol=symbol,
                side=signal,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                auth=auth
            )

            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ Order Placed: {response}")

            if response:
                log_trade(symbol, signal, quantity, current_price, volatility, order_type, cash, net_worth)

            if order_type == "limit" and response and "order_id" in response:
                pending_limit_order_id = response["order_id"]
                pending_limit_timestamp = time.time()

            last_signal = signal

        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⏸ No signal change.")

        last_price = current_price
        time.sleep(interval)

# --- CLI ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run in continuous trading mode")
    args = parser.parse_args()

    if args.live:
        run_trading_loop(interval)
    else:
        signal = strategy_fn(symbol, **strategy_params)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🧪 Would {signal.upper()} now!" if signal in ["buy", "sell"] else f"🧪 Manual test result: {signal}")
