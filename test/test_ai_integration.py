# test_ai_integration.py
"""
Test AI PM Integration with StrategyRouter

Verifies that:
1. AI PM decide_strategy() is called by the router
2. Router correctly maps AI decisions to strategy instances
3. Order metadata contains AI PM decision info (reason, risk_mode)
4. Both sniper and arb modes work correctly
"""

import sys


def test_ai_pm_decide_strategy():
    """Test the AI PM module directly."""
    from strategies.ai_pm import decide_strategy

    print("=" * 60)
    print("TEST 1: AI PM decide_strategy() function")
    print("=" * 60)

    # Test mode="arb"
    result = decide_strategy({"mode": "arb"})
    assert result["chosen_strategy"] == "ou_arb", f"Expected ou_arb, got {result['chosen_strategy']}"
    assert result["risk_mode"] == "defensive", f"Expected defensive, got {result['risk_mode']}"
    assert result["reason"] == "Arbitrage opportunity detected"
    print(f"✓ mode='arb' -> {result}")

    # Test mode="sniper"
    result = decide_strategy({"mode": "sniper"})
    assert result["chosen_strategy"] == "sniper", f"Expected sniper, got {result['chosen_strategy']}"
    assert result["risk_mode"] == "aggressive", f"Expected aggressive, got {result['risk_mode']}"
    assert result["reason"] == "Trend sniper signal"
    print(f"✓ mode='sniper' -> {result}")

    # Test default (no mode)
    result = decide_strategy({})
    assert result["chosen_strategy"] == "ou_arb", f"Expected ou_arb (default), got {result['chosen_strategy']}"
    assert result["reason"] == "Default safety fallback"
    print(f"✓ no mode -> {result}")

    print("\n✅ TEST 1 PASSED: AI PM decide_strategy() works correctly\n")


def test_router_uses_ai_pm():
    """Test that StrategyRouter calls AI PM and routes correctly."""
    from strategies.router import StrategyRouter, RoutingMode

    print("=" * 60)
    print("TEST 2: Router uses AI PM for decisions")
    print("=" * 60)

    router = StrategyRouter(verbose=True)

    # Test 1: Sniper mode with valid opportunity
    market_state_sniper = {
        "mode": "sniper",
        "best_ask": 0.40,  # Below target (0.50) - min_gap (0.02) = 0.48
        "best_bid": 0.39,
        "gas_cost_usd": 0.0,
    }

    print("\nTest 2a: Sniper mode with opportunity")
    orders = router.on_tick(market_state_sniper)

    # Verify AI PM was called and decision stored
    decision = router.get_last_decision()
    assert decision is not None, "AI PM decision should be stored"
    assert decision["chosen_strategy"] == "sniper", f"Expected sniper, got {decision['chosen_strategy']}"
    assert decision["risk_mode"] == "aggressive", f"Expected aggressive, got {decision['risk_mode']}"
    print(f"  AI Decision: {decision}")

    # Verify orders were generated
    assert len(orders) > 0, "Should have generated orders"
    assert orders[0].side == "BUY", "Sniper should generate BUY order"
    print(f"  Orders: {len(orders)} generated")

    # Verify order metadata contains AI PM info
    assert orders[0].meta is not None, "Order should have metadata"
    assert orders[0].meta.get("routing_mode") == "sniper", "routing_mode should be sniper"
    assert orders[0].meta.get("ai_reason") == "Trend sniper signal", "ai_reason should be set"
    assert orders[0].meta.get("ai_risk_mode") == "aggressive", "ai_risk_mode should be aggressive"
    print(f"  Order metadata: {orders[0].meta}")

    # Verify routing mode
    assert router.last_routing_mode == RoutingMode.SNIPER, "Should have routed to sniper"
    print("  ✓ Router correctly picked Sniper strategy")

    # Test 2: Arb mode with valid opportunity
    print("\nTest 2b: Arb mode with opportunity")
    router.reset_stats()

    market_state_arb = {
        "mode": "arb",
        "pm_ask": 0.45,
        "pm_bid": 0.44,
        "op_ask": 0.55,
        "op_bid": 0.54,  # spread = 0.54 - 0.45 = 0.09 > threshold
    }

    orders = router.on_tick(market_state_arb)

    decision = router.get_last_decision()
    assert decision["chosen_strategy"] == "ou_arb"
    assert decision["risk_mode"] == "defensive"
    print(f"  AI Decision: {decision}")

    assert len(orders) == 2, "Arb should generate 2 orders (BUY + SELL)"
    assert orders[0].meta.get("ai_reason") == "Arbitrage opportunity detected"
    assert router.last_routing_mode == RoutingMode.OU_ARB
    print("  ✓ Router correctly picked OU Arb strategy")

    print("\n✅ TEST 2 PASSED: Router correctly uses AI PM\n")


def test_router_with_backtest():
    """Test full integration: Router + AI PM + BacktestEngine."""
    from strategies.router import StrategyRouter
    from engine.backtest import BacktestEngine

    print("=" * 60)
    print("TEST 3: Full integration with BacktestEngine")
    print("=" * 60)

    router = StrategyRouter(verbose=False)
    engine = BacktestEngine(strategy=router, initial_cash=1000.0)

    # Mixed market data
    series = [
        # Tick 0: Arb opportunity
        {
            "mode": "arb",
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.55,
            "op_bid": 0.54,
        },
        # Tick 1: Sniper opportunity
        {
            "mode": "sniper",
            "best_ask": 0.40,
            "best_bid": 0.39,
        },
        # Tick 2: No opportunity (prices too high)
        {
            "mode": "sniper",
            "best_ask": 0.55,
            "best_bid": 0.54,
        },
    ]

    result = engine.run(series)

    print(f"  Initial cash: ${result.initial_cash:.2f}")
    print(f"  Final equity: ${result.final_equity:.2f}")
    print(f"  Total return: {result.total_return:.2%}")
    print(f"  Total trades: {result.total_trades}")

    # Verify trades have AI metadata
    for trade in result.trades:
        assert trade.meta is not None, "Trade should have metadata"
        assert "ai_reason" in trade.meta, "Trade should have ai_reason"
        print(f"  Trade: {trade.side} @ ${trade.price:.4f} - {trade.meta.get('ai_reason')}")

    # Check routing stats
    stats = router.get_routing_stats()
    print(f"\n  Routing stats: {stats}")
    assert stats["ou_arb_count"] >= 1, "Should have at least 1 arb route"
    assert stats["sniper_count"] >= 1, "Should have at least 1 sniper route"

    print("\n✅ TEST 3 PASSED: Full integration works\n")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print(" AI PM INTEGRATION TESTS")
    print("=" * 60 + "\n")

    try:
        test_ai_pm_decide_strategy()
        test_router_uses_ai_pm()
        test_router_with_backtest()

        print("=" * 60)
        print(" ALL TESTS PASSED! ✅")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
