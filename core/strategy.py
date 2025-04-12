# core/strategy.py
import pandas as pd
from core.api_client import get_stock_history

def simple_sma_strategy(symbol, short=5, long=20, interval="5m", points=50):
    data = get_stock_history(symbol, interval=interval, points=points)
    if not data or len(data) < long:
        return "hold"

    df = pd.DataFrame(data)
    df['SMA_short'] = df['price'].rolling(window=short).mean()
    df['SMA_long'] = df['price'].rolling(window=long).mean()
    df['Signal'] = (df['SMA_short'] > df['SMA_long']).astype(int)
    df['Position'] = df['Signal'].diff()

    # Use only the last known crossover signal
    latest = df.iloc[-1]
    if latest['Position'] == 1:
        return "buy"
    elif latest['Position'] == -1:
        return "sell"
    return "hold"
