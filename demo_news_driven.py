# demo_news_driven.py
"""
News-Driven AI PM Demo (Step 5)

Demonstrates the full pipeline:
1. Load historical news cases from CSV
2. Filter by symbol and compute statistics
3. Analyze historical pattern (rule-based or LLM)
4. Build a demo market_state with the pattern
5. Call AI PM to get strategy decision
6. Run through StrategyRouter to see orders

Usage:
    python3 demo_news_driven.py           # Default: BLUE
    python3 demo_news_driven.py BTC       # Specify symbol
    python3 demo_news_driven.py NVDA      # Another symbol

Environment variables:
    AI_PM_USE_LLM=1       Enable LLM mode for both pattern analysis and AI PM
    GEMINI_API_KEY=...    Required for LLM mode
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

from news_replay import (
    NewsCase,
    load_news_cases,
    filter_cases,
    summarize_cases,
    analyze_pattern_with_llm,
)
from strategies.ai_pm import decide_strategy, reset_state
from strategies.router import StrategyRouter


# =============================================================================
# HELPERS
# =============================================================================

def _format_pct(value: float) -> str:
    """Format a decimal return as a percentage string with sign."""
    pct = value * 100
    if pct >= 0:
        return f"+{pct:.1f}%"
    else:
        return f"{pct:.1f}%"


def print_pretty_news_report(
    symbol: str,
    cases: List[NewsCase],
    summary: Dict[str, Any],
    pattern: Dict[str, Any],
) -> None:
    """
    Nicely print:
    - Header with symbol and number of samples
    - Each NewsCase: date, headline, 1D/3D returns, short summary
    - Aggregate stats from `summary`
    - Pattern info from `pattern`
    """
    count = int(summary.get("count", len(cases)))

    # Header
    print()
    print("=" * 70)
    print(f"  NEWS REPLAY: {symbol} ({count} historical cases)")
    print("=" * 70)
    print()

    if count == 0:
        print("  (No matching data found)")
        print()
        return

    # Sort cases by date ascending
    sorted_cases = sorted(cases, key=lambda c: c.event_date)

    # List each case
    print("-" * 70)
    print(" HISTORICAL NEWS EVENTS")
    print("-" * 70)
    for i, case in enumerate(sorted_cases, start=1):
        print(f"\n{i}) [{case.event_date}] {case.news_headline}")
        print(f"   Regime: {case.regime}  |  Tag: {case.source_tag}")
        print(f"   Returns: 1D={_format_pct(case.return_1d)}, "
              f"3D={_format_pct(case.return_3d)}, "
              f"7D={_format_pct(case.return_7d)}")
        # Truncate summary if too long
        summary_text = case.news_summary
        if len(summary_text) > 70:
            summary_text = summary_text[:67] + "..."
        print(f"   Summary: {summary_text}")

    # Summary statistics
    print()
    print("-" * 70)
    print(" AGGREGATE STATISTICS")
    print("-" * 70)
    print(f"  Sample count:     {count}")
    print(f"  Avg 1D return:    {_format_pct(summary['avg_return_1d'])} "
          f"(positive: {summary['pos_ratio_1d'] * 100:.0f}%)")
    print(f"  Avg 3D return:    {_format_pct(summary['avg_return_3d'])} "
          f"(positive: {summary['pos_ratio_3d'] * 100:.0f}%)")
    print(f"  Avg 7D return:    {_format_pct(summary['avg_return_7d'])} "
          f"(positive: {summary['pos_ratio_7d'] * 100:.0f}%)")

    # Pattern analysis
    print()
    print("-" * 70)
    print(" HISTORICAL PATTERN ANALYSIS")
    print("-" * 70)
    print(f"  Pattern name:     {pattern.get('pattern_name', 'N/A')}")
    print(f"  Avg return (1D):  {_format_pct(pattern.get('avg_return_1d', 0) or 0)}")
    print(f"  Avg return (3D):  {_format_pct(pattern.get('avg_return_3d', 0) or 0)}")
    print(f"  Avg return (7D):  {_format_pct(pattern.get('avg_return_7d', 0) or 0)}")
    print(f"  Confidence:       {pattern.get('confidence', 0):.2f} ({pattern.get('confidence_level', 'N/A')})")
    print(f"  Typical horizon:  {pattern.get('typical_horizon', 'N/A')}")
    print(f"  Analysis method:  {pattern.get('analysis_method', 'N/A')}")

    # Show comment
    if pattern.get("comment"):
        print(f"  Comment:          {pattern['comment']}")

    # Show LLM status
    if pattern.get("analysis_method") == "llm":
        model_name = pattern.get("llm_model", "unknown")
        print(f"  [Note] LLM analysis: OK (model={model_name})")
    elif pattern.get("error"):
        error_msg = pattern["error"]
        # Truncate long error messages for cleaner display
        if len(error_msg) > 80:
            error_msg = error_msg[:77] + "..."
        print(f"  [Note] LLM error: {error_msg}")

    print()


def build_demo_market_state(
    latest_case: NewsCase,
    pattern: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a single market_state dict to feed into decide_strategy / StrategyRouter.

    Creates a realistic market state based on the pattern's expected returns:
    - If pattern shows strong positive returns -> create arb opportunity
    - Otherwise -> create a more neutral state

    Args:
        latest_case: The most recent NewsCase for context
        pattern: The historical pattern analysis dict

    Returns:
        Dict suitable for decide_strategy() and StrategyRouter.on_tick()
    """
    avg_3d = pattern.get("avg_return_3d", 0)
    confidence = pattern.get("confidence_level", "low")

    # Base prices
    base_price = 0.50

    # Determine market state based on pattern strength
    if avg_3d > 0.10 and confidence in {"medium", "high"}:
        # Strong positive pattern -> create arb opportunity
        # (spread exists, suggesting market inefficiency to exploit)
        pm_ask = 0.45
        op_bid = 0.60
        best_ask = 0.40  # Also sniper opportunity
        mode = "arb"
    elif avg_3d > 0.05:
        # Moderate positive -> mild arb
        pm_ask = 0.48
        op_bid = 0.55
        best_ask = 0.46
        mode = "arb"
    elif avg_3d < -0.05:
        # Negative pattern -> defensive, no clear opportunity
        pm_ask = 0.50
        op_bid = 0.51
        best_ask = 0.52
        mode = None
    else:
        # Neutral -> sniper opportunity (price below target)
        pm_ask = 0.50
        op_bid = 0.51
        best_ask = 0.38  # Deep discount for sniper
        mode = "sniper"

    spread = op_bid - pm_ask

    return {
        # Core market data
        "mode": mode,
        "pm_ask": pm_ask,
        "pm_bid": pm_ask - 0.01,
        "op_ask": op_bid + 0.02,
        "op_bid": op_bid,
        "spread": spread,
        "best_ask": best_ask,
        "best_bid": best_ask - 0.01,

        # News context
        "symbol": latest_case.symbol,
        "event_date": latest_case.event_date,
        "news_headline": latest_case.news_headline,
        "news_summary": latest_case.news_summary,

        # Historical pattern (the key addition from Step 4)
        "historical_pattern": pattern,

        # Misc
        "gas_cost_usd": 0.0,
    }


def print_market_state(market_state: Dict[str, Any]) -> None:
    """Print the demo market state in a readable format."""
    print("-" * 70)
    print(" DEMO MARKET STATE")
    print("-" * 70)
    print(f"  Symbol:       {market_state.get('symbol', 'N/A')}")
    print(f"  Event date:   {market_state.get('event_date', 'N/A')}")
    print(f"  Mode hint:    {market_state.get('mode', 'None')}")
    print()
    print(f"  PM ask:       {market_state.get('pm_ask', 0):.2f}")
    print(f"  OP bid:       {market_state.get('op_bid', 0):.2f}")
    print(f"  Spread:       {market_state.get('spread', 0):.2f}")
    print(f"  Best ask:     {market_state.get('best_ask', 0):.2f}")
    print()

    # Show headline (truncated)
    headline = market_state.get("news_headline", "")
    if len(headline) > 60:
        headline = headline[:57] + "..."
    print(f"  Headline:     {headline}")
    print()


def print_ai_decision(decision: Dict[str, Any]) -> None:
    """Print the AI PM decision in a formatted way."""
    print(f"  Strategy:     {decision.get('chosen_strategy', 'N/A')}")
    print(f"  Risk mode:    {decision.get('risk_mode', 'N/A')}")
    print(f"  Confidence:   {decision.get('confidence', 0):.2f}")
    print()
    print(f"  Reason:")
    # Word-wrap the reason if it's long
    reason = decision.get("reason", "N/A")
    if len(reason) > 65:
        # Simple word wrap
        words = reason.split()
        lines = []
        current_line = "    "
        for word in words:
            if len(current_line) + len(word) + 1 > 70:
                lines.append(current_line)
                current_line = "    " + word
            else:
                current_line += " " + word if current_line.strip() else "    " + word
        if current_line.strip():
            lines.append(current_line)
        print("\n".join(lines))
    else:
        print(f"    {reason}")
    print()


def print_router_orders(orders: List[Any], router: StrategyRouter) -> None:
    """Print the orders generated by the router."""
    if not orders:
        print("  (No orders generated)")
        print()
        print("  This can happen when:")
        print("  - The chosen strategy doesn't find a valid opportunity")
        print("  - Market conditions don't meet strategy thresholds")
        return

    for i, order in enumerate(orders, start=1):
        print(f"  Order {i}:")
        print(f"    Side:     {order.side}")
        print(f"    Size:     {order.size:.2f}")
        print(f"    Price:    {order.price:.2f}")

        if order.meta:
            routing_mode = order.meta.get("routing_mode", "N/A")
            ai_reason = order.meta.get("ai_reason", "N/A")
            ai_risk = order.meta.get("ai_risk_mode", "N/A")
            print(f"    Routed:   {routing_mode}")
            print(f"    Risk:     {ai_risk}")
        print()


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """
    Main entry point for the news-driven demo.
    """
    print()
    print("=" * 70)
    print(" DEMO: News-Driven AI Portfolio Manager")
    print(" Combines historical news patterns with AI PM decision-making")
    print("=" * 70)

    # 1) Load all cases
    cases = load_news_cases()

    if not cases:
        print("\n[ERROR] No news cases loaded.")
        print("Make sure data/news_cases.csv exists and has valid data.")
        return

    print(f"\nLoaded {len(cases)} total news cases from CSV.")

    # 2) Pick a symbol (from CLI arg or default)
    if len(sys.argv) > 1:
        symbol = sys.argv[1].upper()
    else:
        symbol = "BLUE"  # Default demo symbol

    print(f"Analyzing symbol: {symbol}")

    # 3) Filter cases for this symbol
    symbol_cases = filter_cases(cases, symbol=symbol)

    if not symbol_cases:
        print(f"\n[WARN] No news cases found for symbol={symbol}")
        print("Available symbols in the dataset:")
        available = sorted(set(c.symbol for c in cases))
        print(f"  {', '.join(available)}")
        return

    # 4) Compute summary stats
    summary = summarize_cases(symbol_cases)

    # 5) Get historical pattern via LLM (or fallback rule-based)
    #    use_llm=None lets it respect AI_PM_USE_LLM env var
    pattern = analyze_pattern_with_llm(symbol_cases, use_llm=None)

    # 6) Pretty-print the news + stats + pattern
    print_pretty_news_report(symbol, symbol_cases, summary, pattern)

    # 7) Build a demo market_state using the latest case
    latest_case = symbol_cases[-1]
    market_state = build_demo_market_state(latest_case, pattern)

    print()
    print("Using the above historical pattern as a prior, we now simulate a new trading day:")
    print()

    print("=" * 70)
    print(" SIMULATED TRADING SCENARIO")
    print("=" * 70)
    print()
    print_market_state(market_state)

    # 8) Reset AI PM state for clean demo
    reset_state()

    # 9) Call AI PM to get decision
    print("=" * 70)
    print(" AI PM DECISION")
    print("=" * 70)
    print()

    decision = decide_strategy(market_state)
    print_ai_decision(decision)

    # 10) Show raw decision JSON
    print("-" * 70)
    print(" Raw Decision JSON:")
    print("-" * 70)
    print(json.dumps(decision, indent=2, ensure_ascii=False))

    # 11) Run through StrategyRouter to see what orders it produces
    print()
    print("=" * 70)
    print(" STRATEGY ROUTER ORDERS")
    print("=" * 70)
    print()

    router = StrategyRouter(verbose=False)
    orders = router.on_tick(market_state)

    print_router_orders(orders, router)

    # 12) Show router's last decision for transparency
    router_decision = router.get_last_decision()
    if router_decision:
        print("-" * 70)
        print(" Router's AI PM Decision:")
        print("-" * 70)
        print(f"  Strategy chosen: {router_decision.get('chosen_strategy')}")
        print(f"  Risk mode:       {router_decision.get('risk_mode')}")
        print(f"  Confidence:      {router_decision.get('confidence', 0):.2f}")

    # 13) Final summary
    print()
    print("=" * 70)
    print(" DEMO COMPLETE")
    print("=" * 70)
    print()
    print("Key takeaways:")
    print(f"  - Symbol analyzed:        {symbol}")
    print(f"  - Historical cases:       {len(symbol_cases)}")
    print(f"  - Pattern confidence:     {pattern.get('confidence_level', 'N/A')}")
    print(f"  - Avg 3D return:          {_format_pct(pattern.get('avg_return_3d', 0))}")
    print(f"  - AI PM chose:            {decision.get('chosen_strategy', 'N/A')}")
    print(f"  - Risk mode:              {decision.get('risk_mode', 'N/A')}")
    print(f"  - Orders generated:       {len(orders)}")
    print()
    print("  - This demo runs in rule-based mode by default.")
    print("    LLM integration is available but may fall back under quota or network limits.")
    print()
    print("To enable LLM mode, set environment variables:")
    print("  export AI_PM_USE_LLM=1")
    print("  export GEMINI_API_KEY=your_api_key")
    print()


if __name__ == "__main__":
    main()
