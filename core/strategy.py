# file: core/strategy.py
import pandas as pd
from core.api_client import get_stock_history

# --- Core Strategy ---
def multi_timeframe_sma_strategy(symbol, short=3, long=10, fast_interval="1m", slow_interval="5m", points=50):
    df_fast = pd.DataFrame(get_stock_history(symbol, interval=fast_interval, points=points))
    df_slow = pd.DataFrame(get_stock_history(symbol, interval=slow_interval, points=points))

    if df_fast.empty or df_slow.empty or 'price' not in df_fast.columns or 'price' not in df_slow.columns:
        print("⚠️ Not enough data for multi-timeframe strategy")
        return "hold"

    # FAST chart crossovers
    df_fast['SMA_short'] = df_fast['price'].rolling(window=short).mean()
    df_fast['SMA_long'] = df_fast['price'].rolling(window=long).mean()
    df_fast['Signal'] = (df_fast['SMA_short'] > df_fast['SMA_long']).astype(int)
    df_fast['Position'] = df_fast['Signal'].diff()

    # SLOW chart trend confirmation
    df_slow['SMA_short'] = df_slow['price'].rolling(window=short).mean()
    df_slow['SMA_long'] = df_slow['price'].rolling(window=long).mean()
    df_slow['Momentum'] = df_slow['SMA_short'] - df_slow['SMA_long']
    df_slow['Trend'] = (df_slow['Momentum'] > 0).astype(int)

    df_fast = df_fast.dropna(subset=['Position']).copy()
    df_slow = df_slow.dropna(subset=['Trend']).copy()

    if df_fast.empty or df_slow.empty:
        return "hold"

    fast_signal = df_fast.iloc[-1]["Position"]
    slow_trend = df_slow.iloc[-1]["Trend"]

    # 🚀 Loosen volatility to encourage trade during moderate noise
    if not is_volatile_enough(df_fast, threshold=0.0035):
        return "hold"

    if fast_signal == 1 and slow_trend == 1:
        return "buy"
    elif fast_signal == -1 and slow_trend == 0:
        return "sell"
    else:
        return "hold"

# --- Filters ---
def is_volatile_enough(df, threshold=0.0035):
    df['pct_change'] = df['price'].pct_change()
    recent_vol = df['pct_change'].rolling(window=3).std().iloc[-1]
    return recent_vol > threshold

def confirm_with_volatility_band(price, sma_long, volatility, multiplier=1.25):
    if price < sma_long - multiplier * sma_long * volatility:
        return "buy"
    elif price > sma_long + multiplier * sma_long * volatility:
        return "sell"
    return "hold"

def confirm_with_orderbook_pressure(orderbook, direction, threshold=1.2):
    buy_key = "buy_orders" if "buy_orders" in orderbook else "buy"
    sell_key = "sell_orders" if "sell_orders" in orderbook else "sell"

    buy_qty = sum([level.get("volume", level.get("quantity", 0)) for level in orderbook.get(buy_key, [])])
    sell_qty = sum([level.get("volume", level.get("quantity", 0)) for level in orderbook.get(sell_key, [])])

    if buy_qty == 0 or sell_qty == 0:
        return True

    ratio = buy_qty / sell_qty

    if direction == "buy" and ratio > threshold:
        return True
    if direction == "sell" and ratio < 1 / threshold:
        return True

    return False

# --- Orders ---
def limit_order_price(signal, current_price, buffer_pct=0.0075):
    if signal == "buy":
        return round(current_price * (1 + buffer_pct), 2)
    elif signal == "sell":
        return round(current_price * (1 - buffer_pct), 2)
    return current_price

def compute_position_size(cash, current_price, volatility, cash_pct=0.08, max_per_trade=600, min_qty=1):
    budget = min(cash * cash_pct, max_per_trade)
    if current_price <= 0:
        return 0
    qty = int(budget // current_price)
    if volatility > 0.15:
        qty = int(qty * 0.7)
    return max(qty, min_qty)
