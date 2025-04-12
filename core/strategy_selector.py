# file: core/strategy_selector.py
from core.strategy import multi_timeframe_sma_strategy

def select_strategy(strategy_name):
    if strategy_name == "multi_sma":
        return multi_timeframe_sma_strategy, {
            "short": 3,
            "long": 10,
            "fast_interval": "1m",
            "slow_interval": "5m",
            "points": 50
        }
    else:
        raise ValueError(f"Unknown strategy '{strategy_name}'")
