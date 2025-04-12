# file: core/strategy.py
import pandas as pd
from core.api_client import get_stock_history

def simple_sma_strategy(symbol, short=5, long=20, interval="5m", points=50):
    # 🔹 Load historical price data
    df = pd.DataFrame(get_stock_history(symbol, interval=interval, points=points))
    if df.empty or 'price' not in df.columns:
        print(f"⚠️ No data returned for symbol {symbol}")
        return "hold"

    # 🔹 Compute moving averages
    df['SMA_short'] = df['price'].rolling(window=short).mean()
    df['SMA_long'] = df['price'].rolling(window=long).mean()
    df['Signal'] = (df['SMA_short'] > df['SMA_long']).astype(int)
    df['Position'] = df['Signal'].diff()

    # ✅ Copy clean subset before mutation
    df_clean = df.dropna(subset=['SMA_short', 'SMA_long', 'Signal', 'Position']).copy()
    if df_clean.empty:
        print("⚠️ Not enough data to generate a signal yet.")
        return "hold"

    # ⛔ Filter out weak signals under low volatility
    if not is_volatile_enough(df_clean, threshold=0.005):
        return "hold"

    # 🧠 Use last row for signal
    last_signal_row = df_clean.iloc[-1]
    if last_signal_row["Position"] == 1:
        return "buy"
    elif last_signal_row["Position"] == -1:
        return "sell"
    else:
        return "hold"

def is_volatile_enough(df, threshold=0.005):
    df['pct_change'] = df['price'].pct_change()
    recent_vol = df['pct_change'].rolling(window=5).std().iloc[-1]
    return recent_vol > threshold

def limit_order_price(signal, current_price, buffer_pct=0.01):
    if signal == "buy":
        return round(current_price * (1 + buffer_pct), 2)
    elif signal == "sell":
        return round(current_price * (1 - buffer_pct), 2)
    return current_price

def compute_position_size(cash, current_price, volatility, cash_pct=0.05, max_per_trade=500, min_qty=1):
    """
    Dynamically compute quantity based on account cash, volatility, and price.
    """
    budget = min(cash * cash_pct, max_per_trade)
    if current_price <= 0:
        return 0

    qty = int(budget // current_price)

    # Optional: reduce quantity under high volatility
    if volatility > 0.15:
        qty = int(qty * 0.7)  # Reduce by 30%

    return max(qty, min_qty)

def orderbook_pressure(orderbook, threshold=1.3):
    """
    Returns 'buy', 'sell', or 'neutral' based on volume imbalance.
    """
    buy_qty = sum([level['quantity'] for level in orderbook.get('buy', [])])
    sell_qty = sum([level['quantity'] for level in orderbook.get('sell', [])])

    if sell_qty == 0 or buy_qty == 0:
        return "neutral"

    ratio = buy_qty / sell_qty

    if ratio > threshold:
        return "buy"
    elif ratio < 1 / threshold:
        return "sell"
    else:
        return "neutral"
