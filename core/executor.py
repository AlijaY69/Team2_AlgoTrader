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

# --- Session State ---
last_signal = None
last_price = None
pending_limit_order_id = None
pending_limit_timestamp = None
session_start_time = time.time()
last_exposure_time = None
total_limit_orders = 0
total_market_orders = 0
total_signals = 0
last_networth = None

# --- MAIN LOOP ---
def run_trading_loop(interval=60):
    global last_signal, last_price, pending_limit_order_id, pending_limit_timestamp
    global last_exposure_time, total_limit_orders, total_market_orders, total_signals, last_networth

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🌀 Starting trading loop on {symbol}, interval = {interval}s")

    while True:
        loop_start = time.time()

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

        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 💼 Cash=${cash:.2f} | {symbol}={position} | NW=${net_worth:.2f}")
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📈 Price=${current_price:.2f} | Volatility={volatility:.4f}")

        try:
            signal = strategy_fn(symbol, **strategy_params)
        except Exception as e:
            print(f"❌ Strategy Error: {e}")
            time.sleep(interval)
            continue

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📊 Strategy Signal: {signal}")
        total_signals += 1

        # Cancel stale orders
        if pending_limit_order_id and time.time() - pending_limit_timestamp > stale_limit_lifetime:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Cancelling stale LIMIT order ID {pending_limit_order_id}")
            cancel_order(pending_limit_order_id, auth)
            pending_limit_order_id = None
            pending_limit_timestamp = None
            last_signal = None

        # Trade decision pipeline
        if signal != last_signal and signal in ["buy", "sell"]:
            has_held_long = position > 0 and net_worth < (cash + position * current_price * 0.995)
            price_delta = abs((last_price or current_price) - current_price) / current_price
            loosen_filters = abs(volatility) * 100 > 1.5 or has_held_long or price_delta > 0.01

            print(f"[FILTER] ΔPrice={price_delta:.4f} | HeldLong={has_held_long} | Loosen={loosen_filters}")

            band_confirm = confirm_with_volatility_band(current_price, current_price, volatility)
            ob_confirm = confirm_with_orderbook_pressure(orderbook, signal)
            print(f"[FILTER CHECK] Band={band_confirm} | OB={ob_confirm} | Raw={signal}")

            if not loosen_filters and band_confirm != signal:
                print("❌ Blocked by volatility band filter")
                continue
            if not loosen_filters and not ob_confirm:
                print("❌ Blocked by orderbook pressure filter")
                continue

            quantity = compute_position_size(cash, current_price, volatility)
            print(f"📐 Computed Qty: {quantity} | Volatility={volatility:.4f}")

            if signal == "sell" and position == 0:
                print("⚠️ Cannot SELL — no holdings.")
                continue

            order_type = "market" if volatility > 0.08 else "limit"
            limit_price = None if order_type == "market" else limit_order_price(signal, current_price)
            print(f"📝 Order Type: {order_type.upper()} | Limit Price: {limit_price or '—'}")

            response = place_order(
                user_id=user_id,
                symbol=symbol,
                side=signal,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                auth=auth
            )

            print(f"✅ Order Placed: {response}")

            if response:
                log_trade(symbol, signal, quantity, current_price, volatility, order_type, cash, net_worth)

                if order_type == "limit" and "order_id" in response:
                    pending_limit_order_id = response["order_id"]
                    pending_limit_timestamp = time.time()

                if order_type == "market":
                    total_market_orders += 1
                else:
                    total_limit_orders += 1

                if position == 0 and signal == "buy":
                    last_exposure_time = loop_start

            last_signal = signal

        else:
            print(f"⏸ No signal change.")

        # --- Session Metrics ---
        if last_exposure_time and position > 0:
            exposure_duration = time.time() - last_exposure_time
            print(f"⏱️ Holding HACK for {exposure_duration:.1f} seconds")
        if last_networth is not None:
            delta = net_worth - last_networth
            print(f"💰 Net Worth Δ: {'+' if delta >= 0 else ''}{delta:.2f}")
        last_networth = net_worth
        last_price = current_price

        print(f"📊 Orders — Limit: {total_limit_orders}, Market: {total_market_orders}, Signals: {total_signals}")
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
