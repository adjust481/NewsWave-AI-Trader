# demo_compare_strategies.py
"""
Strategy Comparison Demo

Compares the behavior of three configurations on the same market data:
1. OU Only:     OUArbStrategy (arbitrage)
2. Sniper Only: SniperStrategy (directional)
3. Router:      StrategyRouter (AI PM switching)

This script demonstrates how the Router correctly switches between
strategies based on market conditions.
"""

from typing import Any, Dict, List

from strategies.ou_arb import OUArbStrategy
from strategies.sniper import SniperStrategy
from strategies.router import StrategyRouter
from engine.backtest import BacktestEngine, BacktestResult


def build_series() -> List[Dict[str, Any]]:
    """
    Build a synthetic market data series with distinct phases.

    Phases:
    - A (Quiet):   No opportunity for either strategy
    - B (Arb):     Large spread between PM and OP (arb opportunity)
    - C (Sniper):  Price drops below target (sniper opportunity)
    - D (Both):    Both opportunities exist (router should pick arb)
    - E (Neutral): Back to quiet

    Returns:
        List of market state dictionaries.
    """
    series = []

    # ===== PHASE A: QUIET (Ticks 0-2) =====
    # pm_ask ≈ op_bid (no arb spread)
    # best_ask > 0.48 (no sniper trigger, since target=0.50, min_gap=0.02)
    for i in range(3):
        series.append({
            "tick": i,
            "phase": "A_quiet",
            "mode": None,  # No explicit mode
            # Arb data: small spread, no opportunity
            "pm_ask": 0.50,
            "pm_bid": 0.49,
            "op_ask": 0.51,
            "op_bid": 0.50,  # spread = 0.50 - 0.50 = 0 (no opportunity)
            # Sniper data: price too high
            "best_ask": 0.52,
            "best_bid": 0.51,
            "gas_cost_usd": 0.0,
        })

    # ===== PHASE B: ARB OPPORTUNITY (Ticks 3-5) =====
    # op_bid >> pm_ask (large spread)
    # best_ask still high (no sniper trigger)
    for i in range(3, 6):
        series.append({
            "tick": i,
            "phase": "B_arb",
            "mode": "arb",  # Explicit arb mode for AI PM
            # Arb data: BIG spread = 0.60 - 0.45 = 0.15
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.62,
            "op_bid": 0.60,  # spread = 0.60 - 0.45 = 0.15 (big opportunity!)
            # Sniper data: price still high (0.55 > 0.48 trigger)
            "best_ask": 0.55,
            "best_bid": 0.54,
            "gas_cost_usd": 0.0,
        })

    # ===== PHASE C: SNIPER OPPORTUNITY (Ticks 6-8) =====
    # pm_ask ≈ op_bid (no arb)
    # best_ask drops very low (below 0.48 trigger)
    for i in range(6, 9):
        price = 0.35 + (i - 6) * 0.03  # 0.35, 0.38, 0.41
        series.append({
            "tick": i,
            "phase": "C_sniper",
            "mode": "sniper",  # Explicit sniper mode for AI PM
            # Arb data: no spread
            "pm_ask": 0.50,
            "pm_bid": 0.49,
            "op_ask": 0.51,
            "op_bid": 0.50,  # spread = 0
            # Sniper data: price drops! (< 0.48 trigger)
            "best_ask": price,
            "best_bid": price - 0.01,
            "gas_cost_usd": 0.0,
        })

    # ===== PHASE D: BOTH OPPORTUNITIES (Ticks 9-10) =====
    # Both arb AND sniper conditions are met
    # Router should pick arb (higher priority)
    for i in range(9, 11):
        series.append({
            "tick": i,
            "phase": "D_both",
            "mode": "arb",  # AI PM will pick arb
            # Arb data: spread = 0.58 - 0.42 = 0.16
            "pm_ask": 0.42,
            "pm_bid": 0.41,
            "op_ask": 0.60,
            "op_bid": 0.58,
            # Sniper data: also opportunity (0.40 < 0.48)
            "best_ask": 0.40,
            "best_bid": 0.39,
            "gas_cost_usd": 0.0,
        })

    # ===== PHASE E: BACK TO QUIET (Ticks 11-13) =====
    # Price recovers, no opportunities
    for i in range(11, 14):
        series.append({
            "tick": i,
            "phase": "E_quiet",
            "mode": None,
            "pm_ask": 0.50,
            "pm_bid": 0.49,
            "op_ask": 0.51,
            "op_bid": 0.50,
            "best_ask": 0.52,
            "best_bid": 0.51,
            "gas_cost_usd": 0.0,
        })

    return series


def run_with(strategy_name: str, strategy: Any, series: List[Dict]) -> BacktestResult:
    """
    Run backtest with given strategy and print summary.

    Args:
        strategy_name: Display name for logging.
        strategy: Strategy instance (BaseStrategy subclass).
        series: Market data series.

    Returns:
        BacktestResult from the backtest.
    """
    engine = BacktestEngine(strategy=strategy, initial_cash=1000.0)
    result = engine.run(series)

    print(f"\n{'='*60}")
    print(f" {strategy_name}")
    print(f"{'='*60}")
    print(f"  Initial Cash:   ${result.initial_cash:.2f}")
    print(f"  Final Equity:   ${result.final_equity:.2f}")
    print(f"  Total Return:   {result.total_return:.2%}")
    print(f"  Total Trades:   {result.total_trades}")
    print(f"  Max Drawdown:   {result.max_drawdown:.2%}")

    if result.trades:
        print(f"\n  Sample Trades (first 5):")
        for trade in result.trades[:5]:
            meta_info = ""
            if trade.meta:
                routing = trade.meta.get("routing_mode", "")
                reason = trade.meta.get("reason", trade.meta.get("ai_reason", ""))
                if routing:
                    meta_info = f" [via {routing}]"
                if reason:
                    meta_info += f" ({reason})"
            print(f"    Tick {trade.tick}: {trade.side} {trade.size:.2f} @ ${trade.price:.4f}{meta_info}")

    return result


def compare_tick_by_tick(
    series: List[Dict],
    ou_result: BacktestResult,
    sniper_result: BacktestResult,
    router_result: BacktestResult,
) -> None:
    """
    Print a detailed tick-by-tick comparison for key phases.

    Args:
        series: Original market data series.
        ou_result: Result from OU-only backtest.
        sniper_result: Result from Sniper-only backtest.
        router_result: Result from Router backtest.
    """
    print("\n" + "=" * 70)
    print(" TICK-BY-TICK COMPARISON (Key Phases)")
    print("=" * 70)

    # Build trade lookup by tick
    def trades_at_tick(result: BacktestResult, tick: int) -> List:
        return [t for t in result.trades if t.tick == tick]

    def describe_action(trades: List) -> str:
        if not trades:
            return "No Action"
        actions = []
        for t in trades:
            routing = ""
            if t.meta and t.meta.get("routing_mode"):
                routing = f" via {t.meta['routing_mode']}"
            actions.append(f"{t.side} {t.size:.1f}@${t.price:.2f}{routing}")
        return ", ".join(actions)

    # Key ticks to compare
    key_ticks = [
        (0, "A_quiet", "Phase A (Quiet) - No opportunity"),
        (4, "B_arb", "Phase B (Arb) - Arb opportunity only"),
        (7, "C_sniper", "Phase C (Sniper) - Sniper opportunity only"),
        (9, "D_both", "Phase D (Both) - Both opportunities"),
        (12, "E_quiet", "Phase E (Quiet) - Back to normal"),
    ]

    for tick, phase, description in key_ticks:
        if tick >= len(series):
            continue

        state = series[tick]
        print(f"\n--- Tick {tick}: {description} ---")
        print(f"    Market: mode={state.get('mode')}, "
              f"pm_ask={state.get('pm_ask')}, op_bid={state.get('op_bid')}, "
              f"best_ask={state.get('best_ask')}")

        ou_trades = trades_at_tick(ou_result, tick)
        sniper_trades = trades_at_tick(sniper_result, tick)
        router_trades = trades_at_tick(router_result, tick)

        print(f"    [OU Only]     -> {describe_action(ou_trades)}")
        print(f"    [Sniper Only] -> {describe_action(sniper_trades)}")
        print(f"    [Router]      -> {describe_action(router_trades)}")


def plot_equity_curves(
    ou_result: BacktestResult,
    sniper_result: BacktestResult,
    router_result: BacktestResult,
) -> None:
    """
    Plot equity curves for all three strategies.

    Args:
        ou_result: Result from OU-only backtest.
        sniper_result: Result from Sniper-only backtest.
        router_result: Result from Router backtest.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[Note] matplotlib not installed, skipping plot.")
        print("       Install with: pip install matplotlib")
        return

    fig, ax = plt.subplots(figsize=(12, 6))

    ticks = list(range(len(ou_result.equity_curve)))

    ax.plot(ticks, ou_result.equity_curve, label="OU Only", marker="o", linewidth=2)
    ax.plot(ticks, sniper_result.equity_curve, label="Sniper Only", marker="s", linewidth=2)
    ax.plot(ticks, router_result.equity_curve, label="Router (AI PM)", marker="^", linewidth=2)

    ax.set_xlabel("Tick")
    ax.set_ylabel("Equity ($)")
    ax.set_title("Equity Curve Comparison: OU vs Sniper vs Router (AI PM)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Add phase annotations
    ax.axvspan(0, 2.5, alpha=0.1, color="gray", label="Phase A (Quiet)")
    ax.axvspan(2.5, 5.5, alpha=0.1, color="blue")
    ax.axvspan(5.5, 8.5, alpha=0.1, color="green")
    ax.axvspan(8.5, 10.5, alpha=0.1, color="purple")
    ax.axvspan(10.5, 13.5, alpha=0.1, color="gray")

    # Add text labels for phases
    ax.text(1, ax.get_ylim()[1] * 0.98, "A\nQuiet", ha="center", va="top", fontsize=8)
    ax.text(4, ax.get_ylim()[1] * 0.98, "B\nArb", ha="center", va="top", fontsize=8)
    ax.text(7, ax.get_ylim()[1] * 0.98, "C\nSniper", ha="center", va="top", fontsize=8)
    ax.text(9.5, ax.get_ylim()[1] * 0.98, "D\nBoth", ha="center", va="top", fontsize=8)
    ax.text(12, ax.get_ylim()[1] * 0.98, "E\nQuiet", ha="center", va="top", fontsize=8)

    plt.tight_layout()
    plt.savefig("equity_comparison.png", dpi=150)
    print("\n[Plot saved to 'equity_comparison.png']")
    plt.show()


def main():
    """
    Main entry point: run comparison and display results.
    """
    print("\n" + "=" * 70)
    print(" STRATEGY COMPARISON DEMO")
    print(" Comparing: OU Only vs Sniper Only vs Router (AI PM)")
    print("=" * 70)

    # 1. Build market data series
    series = build_series()
    print(f"\nGenerated {len(series)} ticks of market data")
    print("Phases: A(quiet) -> B(arb) -> C(sniper) -> D(both) -> E(quiet)")

    # 2. Instantiate strategies
    # Use same parameters for fair comparison
    ou_strategy = OUArbStrategy(
        name="ou_arb",
        min_profit_rate=0.005,  # 0.5%
        min_spread_multiplier=0.5,
    )

    sniper_strategy = SniperStrategy(
        name="sniper",
        target_price=0.50,
        min_gap=0.02,  # Trigger when best_ask < 0.48
        position_size=50.0,
    )

    router_strategy = StrategyRouter(
        name="router",
        ou_strategy=OUArbStrategy(name="ou_arb"),
        sniper_strategy=SniperStrategy(name="sniper", target_price=0.50, min_gap=0.02),
        verbose=False,
    )

    # 3. Run backtests
    ou_result = run_with("OU ONLY (Arbitrage)", ou_strategy, series)
    sniper_result = run_with("SNIPER ONLY (Directional)", sniper_strategy, series)
    router_result = run_with("ROUTER (AI PM Switching)", router_strategy, series)

    # 4. Tick-by-tick comparison
    compare_tick_by_tick(series, ou_result, sniper_result, router_result)

    # 5. Summary comparison
    print("\n" + "=" * 70)
    print(" FINAL COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Strategy':<25} {'Final Equity':>15} {'Return':>10} {'Trades':>8}")
    print("-" * 60)
    print(f"{'OU Only':<25} ${ou_result.final_equity:>14.2f} {ou_result.total_return:>9.2%} {ou_result.total_trades:>8}")
    print(f"{'Sniper Only':<25} ${sniper_result.final_equity:>14.2f} {sniper_result.total_return:>9.2%} {sniper_result.total_trades:>8}")
    print(f"{'Router (AI PM)':<25} ${router_result.final_equity:>14.2f} {router_result.total_return:>9.2%} {router_result.total_trades:>8}")

    # 6. Router-specific stats
    stats = router_strategy.get_routing_stats()
    print(f"\nRouter Routing Stats:")
    print(f"  - OU Arb:    {stats['ou_arb_count']} ticks ({stats['ou_arb_pct']:.1f}%)")
    print(f"  - Sniper:    {stats['sniper_count']} ticks ({stats['sniper_pct']:.1f}%)")
    print(f"  - No Action: {stats['no_action_count']} ticks ({stats['no_action_pct']:.1f}%)")

    # 7. Plot equity curves
    plot_equity_curves(ou_result, sniper_result, router_result)

    print("\n" + "=" * 70)
    print(" DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
