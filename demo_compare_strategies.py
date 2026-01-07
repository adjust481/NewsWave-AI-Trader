# demo_compare_strategies.py
"""
Strategy Comparison Demo (Hackathon Edition)

Compares the behavior of three configurations on the same market data:
1. OU Only:     OUArbStrategy (arbitrage)
2. Sniper Only: SniperStrategy (directional)
3. Router:      StrategyRouter (AI PM switching)

This script demonstrates how the Router correctly switches between
strategies based on market conditions, with clear visibility into
AI PM decisions.
"""

from typing import Any, Dict, List, Optional

from strategies.base import BaseStrategy, OrderInstruction
from strategies.ou_arb import OUArbStrategy
from strategies.sniper import SniperStrategy
from strategies.router import StrategyRouter


# =============================================================================
# HELPERS
# =============================================================================

def describe_orders(orders: List[OrderInstruction], show_router_info: bool = False) -> str:
    """
    Format a list of OrderInstructions into a human-readable string.

    Args:
        orders: List of order instructions.
        show_router_info: If True, show router-specific metadata.

    Returns:
        Formatted string like "BUY 100@0.45; SELL 100@0.60 [router=ou_arb reason=...]"
    """
    if not orders:
        return "(no action)"

    parts = []
    for order in orders:
        # Basic order info
        order_str = f"{order.side} {order.size:.0f}@{order.price:.2f}"

        # Extract metadata
        meta_parts = []
        if order.meta:
            # For router orders, show routing info
            if show_router_info:
                routing_mode = order.meta.get("routing_mode")
                ai_reason = order.meta.get("ai_reason")
                if routing_mode:
                    meta_parts.append(f"router={routing_mode}")
                if ai_reason:
                    meta_parts.append(f"reason={ai_reason}")
            else:
                # For standalone strategies, show their reason
                reason = order.meta.get("reason")
                strategy = order.meta.get("strategy") or order.meta.get("platform")
                if strategy:
                    meta_parts.append(f"strategy={strategy}")
                if reason:
                    meta_parts.append(f"reason={reason}")

        if meta_parts:
            order_str += f" [{' '.join(meta_parts)}]"

        parts.append(order_str)

    return "; ".join(parts)


# =============================================================================
# BUILD SERIES
# =============================================================================

def build_series() -> List[Dict[str, Any]]:
    """
    Build a synthetic market data series with distinct phases.

    Phases:
    - A (Neutral):  No opportunity for either strategy (ticks 0-2)
    - B (Arb):      Large spread between PM and OP (ticks 3-5)
    - C (Sniper):   Price drops below target (ticks 6-8)
    - D (Both):     Both opportunities exist (ticks 9-10)
    - E (Neutral):  Back to quiet (ticks 11-13)

    Returns:
        List of market state dictionaries.
    """
    series = []

    # ===== PHASE A: NEUTRAL (Ticks 0-2) =====
    for i in range(3):
        series.append({
            "tick": i,
            "phase": "A",
            "phase_name": "neutral",
            "mode": None,
            # Arb: no spread
            "pm_ask": 0.50,
            "pm_bid": 0.49,
            "op_ask": 0.51,
            "op_bid": 0.50,
            # Sniper: price too high (0.52 > 0.48 trigger)
            "best_ask": 0.52,
            "best_bid": 0.51,
            "gas_cost_usd": 0.0,
        })

    # ===== PHASE B: ARB OPPORTUNITY (Ticks 3-5) =====
    for i in range(3, 6):
        series.append({
            "tick": i,
            "phase": "B",
            "phase_name": "arb",
            "mode": "arb",
            # Arb: BIG spread = 0.60 - 0.45 = 0.15
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.62,
            "op_bid": 0.60,
            # Sniper: price too high (0.55 > 0.48)
            "best_ask": 0.55,
            "best_bid": 0.54,
            "gas_cost_usd": 0.0,
        })

    # ===== PHASE C: SNIPER OPPORTUNITY (Ticks 6-8) =====
    prices = [0.35, 0.38, 0.41]
    for i, price in enumerate(prices):
        series.append({
            "tick": 6 + i,
            "phase": "C",
            "phase_name": "sniper",
            "mode": "sniper",
            # Arb: no spread
            "pm_ask": 0.50,
            "pm_bid": 0.49,
            "op_ask": 0.51,
            "op_bid": 0.50,
            # Sniper: price drops! (< 0.48 trigger)
            "best_ask": price,
            "best_bid": price - 0.01,
            "gas_cost_usd": 0.0,
        })

    # ===== PHASE D: BOTH OPPORTUNITIES (Ticks 9-10) =====
    for i in range(9, 11):
        series.append({
            "tick": i,
            "phase": "D",
            "phase_name": "both",
            "mode": "arb",  # AI PM picks arb when both available
            # Arb: spread = 0.58 - 0.42 = 0.16
            "pm_ask": 0.42,
            "pm_bid": 0.41,
            "op_ask": 0.60,
            "op_bid": 0.58,
            # Sniper: also opportunity (0.40 < 0.48)
            "best_ask": 0.40,
            "best_bid": 0.39,
            "gas_cost_usd": 0.0,
        })

    # ===== PHASE E: BACK TO NEUTRAL (Ticks 11-13) =====
    for i in range(11, 14):
        series.append({
            "tick": i,
            "phase": "E",
            "phase_name": "neutral",
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


# =============================================================================
# RUN STRATEGY
# =============================================================================

def run_with(strategy: BaseStrategy, series: List[Dict]) -> Dict[str, Any]:
    """
    Run a strategy on the given series and collect orders by tick.

    Args:
        strategy: Strategy instance to run.
        series: Market data series.

    Returns:
        Dict with:
        - "orders_by_tick": Dict[int, List[OrderInstruction]]
        - "total_orders": int
    """
    orders_by_tick: Dict[int, List[OrderInstruction]] = {}
    total_orders = 0

    for market_state in series:
        tick = market_state["tick"]
        orders = strategy.on_tick(market_state)
        orders_by_tick[tick] = orders
        total_orders += len(orders)

    return {
        "orders_by_tick": orders_by_tick,
        "total_orders": total_orders,
    }


# =============================================================================
# PRETTY PRINT
# =============================================================================

def pretty_print_comparison(
    series: List[Dict],
    ou_result: Dict[str, Any],
    sniper_result: Dict[str, Any],
    router_result: Dict[str, Any],
) -> None:
    """
    Print a clear tick-by-tick comparison of all three strategies.

    Args:
        series: Original market data series.
        ou_result: Result from OU-only run.
        sniper_result: Result from Sniper-only run.
        router_result: Result from Router run.
    """
    ou_orders = ou_result["orders_by_tick"]
    sniper_orders = sniper_result["orders_by_tick"]
    router_orders = router_result["orders_by_tick"]

    current_phase = None

    for state in series:
        tick = state["tick"]
        phase = state["phase"]
        phase_name = state["phase_name"]
        mode = state.get("mode")

        # Print phase header when phase changes
        if phase != current_phase:
            current_phase = phase
            print(f"\n{'─' * 70}")
            print(f" PHASE {phase}: {phase_name.upper()}")
            print(f"{'─' * 70}")

        # Market state summary
        pm_ask = state.get("pm_ask", 0)
        op_bid = state.get("op_bid", 0)
        best_ask = state.get("best_ask", 0)
        spread = op_bid - pm_ask if pm_ask and op_bid else 0

        print(f"\n[t={tick:02d}] mode={mode or 'None':<7} "
              f"pm_ask={pm_ask:.2f} op_bid={op_bid:.2f} (spread={spread:.2f}) "
              f"best_ask={best_ask:.2f}")

        # OU Only
        ou = ou_orders.get(tick, [])
        ou_str = describe_orders(ou, show_router_info=False)
        print(f"  OU Only   -> {ou_str}")

        # Sniper Only
        sniper = sniper_orders.get(tick, [])
        sniper_str = describe_orders(sniper, show_router_info=False)
        print(f"  Sniper    -> {sniper_str}")

        # Router (with AI PM info)
        router = router_orders.get(tick, [])
        router_str = describe_orders(router, show_router_info=True)
        print(f"  Router    -> {router_str}")


def print_summary(
    ou_result: Dict[str, Any],
    sniper_result: Dict[str, Any],
    router_result: Dict[str, Any],
    router_strategy: StrategyRouter,
) -> None:
    """
    Print final summary statistics.

    Args:
        ou_result: Result from OU-only run.
        sniper_result: Result from Sniper-only run.
        router_result: Result from Router run.
        router_strategy: The router instance (for routing stats).
    """
    print(f"\n{'=' * 70}")
    print(" SUMMARY")
    print(f"{'=' * 70}")
    print(f"{'Strategy':<20} {'Total Orders':>15}")
    print(f"{'-' * 40}")
    print(f"{'OU Only':<20} {ou_result['total_orders']:>15}")
    print(f"{'Sniper Only':<20} {sniper_result['total_orders']:>15}")
    print(f"{'Router (AI PM)':<20} {router_result['total_orders']:>15}")

    # Router-specific stats
    stats = router_strategy.get_routing_stats()
    print(f"\nRouter Routing Breakdown:")
    print(f"  - OU Arb chosen:    {stats['ou_arb_count']:>3} ticks ({stats['ou_arb_pct']:.1f}%)")
    print(f"  - Sniper chosen:    {stats['sniper_count']:>3} ticks ({stats['sniper_pct']:.1f}%)")
    print(f"  - No action:        {stats['no_action_count']:>3} ticks ({stats['no_action_pct']:.1f}%)")


def print_key_decisions(
    series: List[Dict],
    router_result: Dict[str, Any],
) -> None:
    """
    Highlight key ticks where the router made interesting decisions.

    Args:
        series: Original market data series.
        router_result: Result from Router run.
    """
    print(f"\n{'=' * 70}")
    print(" KEY ROUTER DECISIONS")
    print(f"{'=' * 70}")

    router_orders = router_result["orders_by_tick"]

    # Find interesting ticks
    key_ticks = [
        (3, "First arb opportunity"),
        (6, "First sniper opportunity"),
        (9, "Both opportunities (arb takes priority)"),
    ]

    for tick, description in key_ticks:
        if tick >= len(series):
            continue

        state = series[tick]
        orders = router_orders.get(tick, [])

        print(f"\n[t={tick:02d}] {description}")
        print(f"  Market: mode={state.get('mode')}, "
              f"spread={state['op_bid'] - state['pm_ask']:.2f}, "
              f"best_ask={state['best_ask']:.2f}")

        if orders:
            for order in orders:
                routing_mode = order.meta.get("routing_mode", "?") if order.meta else "?"
                ai_reason = order.meta.get("ai_reason", "?") if order.meta else "?"
                print(f"  -> {order.side} {order.size:.0f}@{order.price:.2f}")
                print(f"     Router chose: {routing_mode}")
                print(f"     AI PM reason: {ai_reason}")
        else:
            print("  -> (no action)")


# =============================================================================
# OPTIONAL PLOT
# =============================================================================

def plot_equity_curves(
    series: List[Dict],
    ou_strategy: OUArbStrategy,
    sniper_strategy: SniperStrategy,
    router_strategy: StrategyRouter,
) -> None:
    """
    Plot equity curves using BacktestEngine (optional).

    This uses the full BacktestEngine for accurate equity tracking.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[Note] matplotlib not installed, skipping plot.")
        return

    from engine.backtest import BacktestEngine

    # Run full backtests
    ou_engine = BacktestEngine(ou_strategy, initial_cash=1000.0)
    sniper_engine = BacktestEngine(sniper_strategy, initial_cash=1000.0)
    router_engine = BacktestEngine(router_strategy, initial_cash=1000.0)

    ou_result = ou_engine.run(series)
    sniper_result = sniper_engine.run(series)
    router_result = router_engine.run(series)

    # Plot
    fig, ax = plt.subplots(figsize=(12, 6))
    ticks = list(range(len(ou_result.equity_curve)))

    ax.plot(ticks, ou_result.equity_curve, label=f"OU Only (${ou_result.final_equity:.0f})",
            marker="o", linewidth=2)
    ax.plot(ticks, sniper_result.equity_curve, label=f"Sniper Only (${sniper_result.final_equity:.0f})",
            marker="s", linewidth=2)
    ax.plot(ticks, router_result.equity_curve, label=f"Router (${router_result.final_equity:.0f})",
            marker="^", linewidth=2, color="green")

    # Phase backgrounds
    ax.axvspan(-0.5, 2.5, alpha=0.1, color="gray")
    ax.axvspan(2.5, 5.5, alpha=0.1, color="blue")
    ax.axvspan(5.5, 8.5, alpha=0.1, color="orange")
    ax.axvspan(8.5, 10.5, alpha=0.1, color="purple")
    ax.axvspan(10.5, 13.5, alpha=0.1, color="gray")

    ax.set_xlabel("Tick")
    ax.set_ylabel("Equity ($)")
    ax.set_title("Equity Curve Comparison: OU vs Sniper vs Router (AI PM)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("equity_comparison.png", dpi=150)
    print(f"\n[Plot saved to 'equity_comparison.png']")

    # Print final equities
    print(f"\nFinal Equities:")
    print(f"  OU Only:       ${ou_result.final_equity:.2f} ({ou_result.total_return:+.1%})")
    print(f"  Sniper Only:   ${sniper_result.final_equity:.2f} ({sniper_result.total_return:+.1%})")
    print(f"  Router (AI PM):${router_result.final_equity:.2f} ({router_result.total_return:+.1%})")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """
    Main entry point: run comparison demo.
    """
    print("=" * 70)
    print(" DEMO: Compare OU / Sniper / Router on synthetic series")
    print(" Shows how Router switches strategies based on AI PM decisions")
    print("=" * 70)

    # 1. Build series
    series = build_series()
    print(f"\nGenerated {len(series)} ticks across 5 phases:")
    print("  A: Neutral (0-2)  -> No opportunity")
    print("  B: Arb (3-5)      -> Arbitrage spread")
    print("  C: Sniper (6-8)   -> Price below target")
    print("  D: Both (9-10)    -> Both opportunities")
    print("  E: Neutral (11-13)-> Back to quiet")

    # 2. Instantiate strategies
    ou_strategy = OUArbStrategy(
        name="ou_arb",
        min_profit_rate=0.005,
        min_spread_multiplier=0.5,
    )

    sniper_strategy = SniperStrategy(
        name="sniper",
        target_price=0.50,
        min_gap=0.02,
        position_size=50.0,
    )

    # Router with fresh child strategies
    router_strategy = StrategyRouter(
        name="router",
        ou_strategy=OUArbStrategy(name="ou_arb"),
        sniper_strategy=SniperStrategy(name="sniper", target_price=0.50, min_gap=0.02),
        verbose=False,
    )

    # 3. Run all strategies
    print("\nRunning strategies...")
    ou_result = run_with(ou_strategy, series)
    sniper_result = run_with(sniper_strategy, series)
    router_result = run_with(router_strategy, series)

    # 4. Pretty print tick-by-tick comparison
    pretty_print_comparison(series, ou_result, sniper_result, router_result)

    # 5. Print key router decisions
    print_key_decisions(series, router_result)

    # 6. Print summary
    print_summary(ou_result, sniper_result, router_result, router_strategy)

    # 7. Optional: Plot equity curves
    # Re-instantiate strategies since they may have state
    ou_strategy2 = OUArbStrategy(name="ou_arb")
    sniper_strategy2 = SniperStrategy(name="sniper", target_price=0.50, min_gap=0.02)
    router_strategy2 = StrategyRouter(name="router")
    plot_equity_curves(series, ou_strategy2, sniper_strategy2, router_strategy2)

    print(f"\n{'=' * 70}")
    print(" DEMO COMPLETE")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
