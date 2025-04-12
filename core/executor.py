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
interval = config.get("interval", 2)
stale_limit_lifetime = config.get("limit_lifetime", 180)
cooldown_period = config.get("cooldown", 90)
auth = (str(user_id), config["password"])

strategy_fn, strategy_params = select_strategy(config.get("strategy", "multi_sma"))

# --- State ---
last_signal = None
last_price = None
pending_limit_order_id = None
pending_limit_timestamp = None
last_trade_time = 0
last_networth = None
total_limit_orders = 0
total_market_orders = 0
total_signals = 0
last_exposure_time = None

# --- MAIN LOOP ---
def run_trading_loop(interval=2):
    global last_signal, last_price, pending_limit_order_id, pending_limit_timestamp
    global last_trade_time, last_networth, total_limit_orders, total_market_orders, total_signals
    global last_exposure_time

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🌀 Starting trading loop on {symbol}, interval = {interval}s")

    while True:
        loop_start = time.time()
        account = get_account(auth)
        cash = float(account.get("cash", 0))
        positions = account.get("open_positions") or account.get("positions") or {}
        position = positions.get(symbol, 0)

        market_data = get_market_data(symbol, auth)
        if not market_data or "stock" not in market_data:
            print("⚠️ Skipping iteration — Market data fetch failed.")
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

        # Cooldown enforcement
        time_since_last_trade = loop_start - last_trade_time
        if signal in ["buy", "sell"] and time_since_last_trade < cooldown_period:
            print(f"🕒 Cooldown active ({time_since_last_trade:.1f}s < {cooldown_period}s) — skipping trade.")
            continue

        # Stale order handling
        if pending_limit_order_id:
            age = time.time() - pending_limit_timestamp
            if age > stale_limit_lifetime:
                print(f"🔄 Cancelling stale LIMIT order (age={age:.1f}s): {pending_limit_order_id}")
                cancel_order(pending_limit_order_id, auth)
                pending_limit_order_id = None
                pending_limit_timestamp = None
                last_signal = None
            else:
                print(f"⏳ Pending LIMIT Order ID {pending_limit_order_id} live for {age:.1f}s")

        # Execute trade if signal changed
        if signal != last_signal and signal in ["buy", "sell"]:
            has_held_long = position > 0 and net_worth < (cash + position * current_price * 0.995)
            price_delta = abs((last_price or current_price) - current_price) / current_price
            loosen_filters = abs(volatility) * 100 > 1.5 or has_held_long or price_delta > 0.01

            print(f"[FILTER] ΔPrice={price_delta:.4f} | HeldLong={has_held_long} | Loosen={loosen_filters}")

            band_confirm = confirm_with_volatility_band(current_price, current_price, volatility)
            ob_confirm = confirm_with_orderbook_pressure(orderbook, signal)
            print(f"[FILTER CHECK] Band={band_confirm} | OB={ob_confirm} | Raw={signal}")

            if not loosen_filters and band_confirm != signal:
                print("❌ Rejected by volatility band filter")
                continue
            if not loosen_filters and not ob_confirm:
                print("❌ Rejected by orderbook pressure filter")
                continue

            quantity = compute_position_size(cash, current_price, volatility)
            print(f"📐 Quantity: {quantity} | Volatility={volatility:.4f}")
            if signal == "sell" and position == 0:
                print("⚠️ Cannot SELL — no holdings.")
                continue

            # --- Forced LIMIT Order ---
            buffer_pct = 0.002  # 0.2%
            limit_price = round(current_price * (1 - buffer_pct), 2) if signal == "buy" else round(current_price * (1 + buffer_pct), 2)
            order_type = "limit"
            print(f"📝 LIMIT Order → Side: {signal.upper()} @ ${limit_price:.2f}")

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
                if "order_id" in response:
                    pending_limit_order_id = response["order_id"]
                    pending_limit_timestamp = time.time()

                last_trade_time = loop_start
                total_limit_orders += 1
                if signal == "buy" and position == 0:
                    last_exposure_time = loop_start

            last_signal = signal

        else:
            print(f"⏸ No signal change.")

        if last_exposure_time and position > 0:
            print(f"⏱️ Exposure Duration: {time.time() - last_exposure_time:.1f}s")
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
