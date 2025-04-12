import time, json, argparse
from pathlib import Path
from core.api_client import (
    get_market_data,
    place_order,
    get_account
)
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

# --- STATE ---
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

# --- PASSIVE LAYERED LIMITS ---
def maintain_passive_limit_orders(symbol, current_price, cash, position, volatility, auth, levels=3, spread_base=0.03, max_spread=0.15):
    """ Adds volatility consideration to the passive grid strategy """
    spread = min(spread_base + 0.5 * volatility, max_spread)
    base_qty = compute_position_size(cash, current_price, volatility)
    passive_qty = max(1, int(base_qty * 0.5))

    print(f"🧮 Spread={spread:.2%}, Passive Qty={passive_qty}")

    for i in range(1, levels + 1):
        offset = spread * i
        buy_price = round(current_price * (1 - offset), 2)
        sell_price = round(current_price * (1 + offset), 2)

        resp_buy = place_order(
            user_id=str(user_id),
            symbol=symbol,
            side="buy",
            quantity=passive_qty,
            order_type="limit",
            limit_price=buy_price,
            auth=auth
        )
        print(f"🟢 Layer {i} BUY @ {buy_price:.2f} → {resp_buy}")

        if position >= passive_qty:
            resp_sell = place_order(
                user_id=str(user_id),
                symbol=symbol,
                side="sell",
                quantity=passive_qty,
                order_type="limit",
                limit_price=sell_price,
                auth=auth
            )
            print(f"🔴 Layer {i} SELL @ {sell_price:.2f} → {resp_sell}")
        else:
            print(f"⚠️ Skipped SELL layer {i} — not enough inventory ({position})")


# --- MAIN LOOP ---
def adjust_volatility_filter(cooldown_period, last_trade_time, volatility, default_threshold=0.005, relaxed_threshold=0.008):
    """ Dynamically adjusts the volatility filter if idle time exceeds cooldown period """
    if time.time() - last_trade_time > cooldown_period:
        # Relax volatility threshold due to inactivity
        print("Relaxing volatility threshold due to inactivity")
        return relaxed_threshold
    return default_threshold

def run_trading_loop(interval=2):
    global last_signal, last_price, pending_limit_order_id, pending_limit_timestamp
    global last_trade_time, last_networth, total_limit_orders, total_market_orders, total_signals
    global last_exposure_time

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 Trading {symbol} at {interval}s intervals")

    while True:
        loop_start = time.time()
        account = get_account(auth)
        cash = float(account.get("cash", 0))
        positions = account.get("open_positions") or account.get("positions") or {}
        position = positions.get(symbol, 0)

        market_data = get_market_data(symbol, auth)
        if not market_data or "stock" not in market_data:
            print("⚠️ Skipping — no market data")
            time.sleep(interval)
            continue

        current_price = market_data["stock"]["price"]
        volatility = market_data["stock"].get("volatility", 0)
        net_worth = float(account.get("networth", cash + position * current_price))
        orderbook = market_data.get("orderbook", {})

        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 💰 Cash=${cash:.2f} | Pos={position} | NW=${net_worth:.2f} | Price=${current_price:.2f} | Vol={volatility:.2%}")

        try:
            signal = strategy_fn(symbol, **strategy_params)
        except Exception as e:
            print(f"❌ Strategy error: {e}")
            time.sleep(interval)
            continue

        print(f"📊 Signal: {signal}")
        total_signals += 1

        if signal in ["buy", "sell"] and (loop_start - last_trade_time) < cooldown_period:
            print(f"🕒 Cooldown active — skipping ({loop_start - last_trade_time:.1f}s)")
            continue

        if pending_limit_order_id:
            age = time.time() - pending_limit_timestamp
            if age > stale_limit_lifetime:
                # Place market order as a backup if the limit order is stale
                print(f"❌ Limit order {pending_limit_order_id} is stale, placing market order instead.")
                resp = place_order(
                    user_id=user_id,
                    symbol=symbol,
                    side=signal,
                    quantity=qty,
                    order_type="market",
                    auth=auth
                )
                print(f"✅ Market order executed: {resp}")
                pending_limit_order_id = None  # Reset pending limit order
                last_trade_time = time.time()  # Log the trade time
            else:
                print(f"⏳ LIMIT order {pending_limit_order_id} alive for {age:.1f}s")

        if signal != last_signal and signal in ["buy", "sell"]:
            has_held_long = position > 0 and net_worth < (cash + position * current_price * 0.995)
            price_delta = abs((last_price or current_price) - current_price) / current_price
            loosen = volatility > 0.015 or has_held_long or price_delta > 0.01

            print(f"[FILTER] ΔPrice={price_delta:.4f} | HeldLong={has_held_long} | Loosen={loosen}")
            volatility_threshold = adjust_volatility_filter(cooldown_period, last_trade_time, volatility)
            if not is_volatile_enough(df_fast, threshold=volatility_threshold):
                print("❌ Blocked by volatility filter")
                continue

            band_ok = confirm_with_volatility_band(current_price, current_price, volatility)
            ob_ok = confirm_with_orderbook_pressure(orderbook, signal)

            if not loosen and band_ok != signal:
                print("❌ Blocked by band filter")
                continue
            if not loosen and not ob_ok:
                print("❌ Blocked by orderbook filter")
                continue

            qty = compute_position_size(cash, current_price, volatility)
            if signal == "sell" and position < qty:
                print("⚠️ Cannot SELL — insufficient holdings")
                continue

            buffer_pct = 0.005  # Tighter limit buffer
            limit_price = round(current_price * (1 - buffer_pct), 2) if signal == "buy" else round(current_price * (1 + buffer_pct), 2)

            print(f"📝 LIMIT {signal.upper()} @ {limit_price:.2f} x{qty}")
            resp = place_order(
                user_id=user_id,
                symbol=symbol,
                side=signal,
                quantity=qty,
                order_type="limit",
                limit_price=limit_price,
                auth=auth
            )

            print(f"✅ Execution Result: {resp}")
            if resp:
                log_trade(symbol, signal, qty, current_price, volatility, "limit", cash, net_worth)
                if "order_id" in resp:
                    pending_limit_order_id = resp["order_id"]
                    pending_limit_timestamp = time.time()
                last_trade_time = loop_start
                total_limit_orders += 1
                if signal == "buy" and position == 0:
                    last_exposure_time = loop_start

            last_signal = signal
        else:
            print("⏸ Signal unchanged.")

        maintain_passive_limit_orders(symbol, current_price, cash, position, volatility, auth)

        if last_exposure_time and position > 0:
            print(f"⏱️ Exposure: {time.time() - last_exposure_time:.1f}s")
        if last_networth is not None:
            delta = net_worth - last_networth
            print(f"💸 Net Worth Δ: {'+' if delta >= 0 else ''}{delta:.2f}")
        last_networth = net_worth
        last_price = current_price

        print(f"📊 Stats — Limit: {total_limit_orders} | Market: {total_market_orders} | Signals: {total_signals}")
        time.sleep(interval)

# --- CLI ENTRY ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run in continuous trading mode")
    args = parser.parse_args()

    if args.live:
        run_trading_loop(interval)
    else:
        signal = strategy_fn(symbol, **strategy_params)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🧪 Would {signal.upper()} now!" if signal in ["buy", "sell"] else f"🧪 Signal: {signal}")
