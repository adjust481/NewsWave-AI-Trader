# test_backtest_router.py
"""
Test for StrategyRouter with BacktestEngine.
"""
from strategies.router import StrategyRouter
from engine.backtest import BacktestEngine


def main():
    router = StrategyRouter()
    engine = BacktestEngine(strategy=router, initial_cash=1000.0)

    # Short timeline: one arb tick, one sniper tick
    series = [
        {
            "mode": "arb",
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.55,
            "op_bid": 0.54,
            "gas_cost_usd": 0.0,
        },
        {
            "mode": "sniper",
            "best_ask": 0.40,  # Changed from current_ask to best_ask
            "best_bid": 0.39,
            "gas_cost_usd": 0.0,
        },
    ]

    result = engine.run(series)

    # BacktestResult is a dataclass, so use dot-attribute access
    print("\n=== Backtest Result ===")
    print(f"Strategy: {result.strategy_name}")
    print(f"Initial Cash: ${result.initial_cash:.2f}")
    print(f"Final Equity: ${result.final_equity:.2f}")
    print(f"Total Return: {result.total_return:.2%}")
    print(f"Total Trades: {result.total_trades}")

    print("\nEquity Curve:")
    for i, eq in enumerate(result.equity_curve):
        print(f"  Tick {i}: ${eq:.2f}")

    print("\nTrades:")
    for trade in result.trades:
        routing = trade.meta.get("routing_mode", "unknown") if trade.meta else "unknown"
        print(f"  [{routing}] {trade.side} {trade.size:.2f} @ ${trade.price:.4f}")


if __name__ == "__main__":
    main()
