import pandas as pd
from core.api_client import get_stock_history, get_market_data
import numpy as np

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
    if not is_volatile_enough(df_fast, threshold=0.005):  # Updated threshold
        return "hold"

    if fast_signal == 1 and slow_trend == 1:
        return "buy"
    elif fast_signal == -1 and slow_trend == 0:
        return "sell"
    else:
        return "hold"

# --- Filters ---
def is_volatile_enough(df, threshold=0.005):  # Increased threshold
    df['pct_change'] = df['price'].pct_change()
    recent_vol = df['pct_change'].rolling(window=3).std().iloc[-1]
    return recent_vol > threshold

def confirm_with_volatility_band(price, sma_long, volatility, multiplier=1.25):
    if price < sma_long - multiplier * sma_long * volatility:
        return "buy"
    elif price > sma_long + multiplier * sma_long * volatility:
        return "sell"
    return "hold"

def confirm_with_orderbook_pressure(orderbook, direction, threshold=1.2, levels=5):
    """
    Confirms whether the orderbook pressure supports a buy or sell action by considering multiple levels.

    Arguments:
    - orderbook (dict): Orderbook data containing buy and sell orders.
    - direction (str): Direction of the order, either "buy" or "sell".
    - threshold (float): Ratio of buy to sell pressure required to execute the order.
    - levels (int): Number of order levels to evaluate for pressure (more levels means deeper evaluation).

    Returns:
    - bool: True if orderbook pressure supports the direction, False otherwise.
    """
    buy_key = "buy_orders" if "buy_orders" in orderbook else "buy"
    sell_key = "sell_orders" if "sell_orders" in orderbook else "sell"

    # Summing the volumes at multiple price levels
    buy_qty = sum([level.get("volume", level.get("quantity", 0)) for level in orderbook.get(buy_key, [])[:levels]])
    sell_qty = sum([level.get("volume", level.get("quantity", 0)) for level in orderbook.get(sell_key, [])[:levels]])

    if buy_qty == 0 or sell_qty == 0:
        return True

    ratio = buy_qty / sell_qty

    if direction == "buy" and ratio > threshold:
        return True
    if direction == "sell" and ratio < 1 / threshold:
        return True

    return False

# --- Orders ---
def limit_order_price(signal, current_price, buffer_pct=0.005):  # Reduced buffer
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

# --- Dynamic Weighted SMA ---
def compute_dynamic_weighted_sma(symbol, auth, short_period=10, long_period=20, volatility=0.05):
    """
    Compute the dynamic weighted SMA based on volatility.

    Arguments:
    - symbol: The stock symbol (string)
    - auth: The authentication tuple (string, string)
    - short_period: The short period for the SMA (int)
    - long_period: The long period for the SMA (int)
    - volatility: The current volatility (float)

    Returns:
    - weighted_sma: The dynamically adjusted weighted SMA (float)
    """
    
    # Get historical market data (e.g., closing prices)
    market_data = get_market_data(symbol, auth)  # Pass the auth parameter here
    historical_prices = market_data.get("history", {}).get("prices", [])

    if len(historical_prices) < long_period:
        print(f"⚠️ Insufficient historical data for {symbol}. Only {len(historical_prices)} data points available.")
        # Return a fallback value (e.g., the current price or NaN)
        return None  # Or you can return the current price as a fallback

    # Extract closing prices
    close_prices = [price['close'] for price in historical_prices[-long_period:]]  # Last 'long_period' prices

    # Calculate SMAs
    short_sma = np.mean(close_prices[-short_period:])  # Short-term SMA (most recent short_period prices)
    long_sma = np.mean(close_prices)  # Long-term SMA (average of the last 'long_period' prices)

    # Adjust the weight based on volatility
    weight = max(0.1, min(1, 1 - volatility))  # Adjust weight inversely to volatility (higher volatility = lower weight)
    
    # Calculate the weighted SMA by blending short and long SMAs based on volatility
    weighted_sma = short_sma * weight + long_sma * (1 - weight)

    return weighted_sma
