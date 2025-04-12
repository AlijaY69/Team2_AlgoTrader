# file: core/strategy_selector.py
from core.strategy import simple_sma_strategy
# Future: from core.other_strategy import volatility_strategy

def select_strategy(strategy_name):
    if strategy_name == "simple_sma":
        return simple_sma_strategy, {"short": 5, "long": 20}
    # elif strategy_name == "volatility":
    #     return volatility_strategy, {"threshold": 0.25}
    else:
        raise ValueError(f"Unknown strategy '{strategy_name}'")
