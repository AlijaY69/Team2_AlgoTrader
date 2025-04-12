
# file: core/session_stats.py
from datetime import datetime

class SessionStats:
    def __init__(self):
        self.reset()

    def reset(self):
        self.start_time = datetime.now()
        self.total_signals = 0
        self.orders_placed = 0
        self.limit_orders = 0
        self.unfilled_limit_orders = 0
        self.last_position_entry_time = None
        self.max_drawdown = 0
        self.last_networth = None
        self.signal_history = []

    def record_signal(self, signal):
        self.total_signals += 1
        self.signal_history.append(signal)

    def record_order(self, order_type):
        self.orders_placed += 1
        if order_type == "limit":
            self.limit_orders += 1

    def record_limit_unfilled(self):
        self.unfilled_limit_orders += 1

    def update_drawdown(self, networth):
        if self.last_networth is None:
            self.last_networth = networth
        else:
            dd = (self.last_networth - networth) / self.last_networth
            if dd > self.max_drawdown:
                self.max_drawdown = dd

    def update_position_time(self, holding):
        if holding and self.last_position_entry_time is None:
            self.last_position_entry_time = datetime.now()
        elif not holding and self.last_position_entry_time:
            self.last_position_entry_time = None

    def exposure_duration_minutes(self):
        if self.last_position_entry_time:
            delta = datetime.now() - self.last_position_entry_time
            return round(delta.total_seconds() / 60, 2)
        return 0

    def summary(self):
        return {
            "Total Signals": self.total_signals,
            "Orders Placed": self.orders_placed,
            "Limit Orders": self.limit_orders,
            "Unfilled Limit Orders": self.unfilled_limit_orders,
            "Exposure Duration (min)": self.exposure_duration_minutes(),
            "Max Drawdown (%)": round(self.max_drawdown * 100, 2),
            "Signal Flips": self._count_flips()
        }

    def _count_flips(self):
        flips = 0
        for i in range(1, len(self.signal_history)):
            if self.signal_history[i] != self.signal_history[i-1] and self.signal_history[i] in ["buy", "sell"]:
                flips += 1
        return flips
