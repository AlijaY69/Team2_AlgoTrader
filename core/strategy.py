# file: core/strategy.py
import pandas as pd
from core.api_client import get_stock_history

def simple_sma_strategy(symbol, short=5, long=20, interval="5m", points=50):
    df = pd.DataFrame(get_stock_history(symbol, interval=interval, points=points))
    if df.empty or 'price' not in df.columns:
        print(f"⚠️ No data returned for symbol {symbol}")
        return "hold"

    df['SMA_short'] = df['price'].rolling(window=short).mean()
    df['SMA_long'] = df['price'].rolling(window=long).mean()
    df['Signal'] = (df['SMA_short'] > df['SMA_long']).astype(int)
    df['Position'] = df['Signal'].diff()

    df_clean = df.dropna(subset=['SMA_short', 'SMA_long', 'Signal', 'Position'])
    if df_clean.empty:
        print("⚠️ Not enough data to generate a signal yet.")
        return "hold"

    last_signal_row = df_clean.iloc[-1]
    if last_signal_row["Position"] == 1:
        return "buy"
    elif last_signal_row["Position"] == -1:
        return "sell"
    else:
        return "hold"

def limit_order_price(signal, current_price, buffer_pct=0.01):
    """
    Adds a small price buffer to current market price to act like a controlled market order.
    """
    if signal == "buy":
        return round(current_price * (1 + buffer_pct), 2)
    elif signal == "sell":
        return round(current_price * (1 - buffer_pct), 2)
    return current_price
