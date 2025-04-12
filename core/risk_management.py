def should_trade(portfolio: dict, signal: str, symbol: str) -> bool:
    if signal == "buy" and symbol in portfolio.get("positions", {}):
        return False  # Already holding
    if signal == "sell" and symbol not in portfolio.get("positions", {}):
        return False  # Nothing to sell
    return True