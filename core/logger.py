# file: core/logger.py
import csv, os
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "trades.csv"
LOG_PATH.parent.mkdir(exist_ok=True)

FIELDS = ["timestamp", "symbol", "side", "quantity", "price", "volatility", "order_type", "cash", "net_worth"]

def log_trade(symbol, side, quantity, price, volatility, order_type, cash, net_worth):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = {
        "timestamp": now,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "volatility": round(volatility, 4),
        "order_type": order_type,
        "cash": round(cash, 2),
        "net_worth": round(net_worth, 2)
    }

    write_header = not LOG_PATH.exists()
    with open(LOG_PATH, mode="a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
