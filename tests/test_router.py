# tests/test_router.py
"""
Pytest-style tests for StrategyRouter.

Tests the router's ability to:
- Route to the correct strategy based on mode
- Track routing statistics
- Annotate orders with routing metadata
"""

import pytest
from strategies.router import StrategyRouter, RoutingMode
from strategies.ou_arb import OUArbStrategy
from strategies.sniper import SniperStrategy


class TestStrategyRouterRouting:
    """Tests for routing logic."""

    def test_arb_mode_routes_to_ou(self):
        """When mode='arb', router should use OUArbStrategy."""
        router = StrategyRouter()
        state = {
            "mode": "arb",
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.55,
            "op_bid": 0.54,
        }
        orders = router.on_tick(state)
        assert len(orders) == 2
        assert router.last_routing_mode == RoutingMode.OU_ARB

    def test_sniper_mode_routes_to_sniper(self):
        """When mode='sniper', router should use SniperStrategy."""
        router = StrategyRouter()
        state = {
            "mode": "sniper",
            "best_ask": 0.40,
            "best_bid": 0.39,
        }
        orders = router.on_tick(state)
        assert len(orders) == 1
        assert orders[0].side == "BUY"
        assert router.last_routing_mode == RoutingMode.SNIPER

    def test_sniper_mode_with_current_ask(self):
        """Sniper mode should also work with 'current_ask' field."""
        router = StrategyRouter()
        state = {
            "mode": "sniper",
            "current_ask": 0.40,
            "current_bid": 0.39,
        }
        orders = router.on_tick(state)
        assert len(orders) == 1
        assert orders[0].side == "BUY"

    def test_no_opportunity_returns_empty(self):
        """When no opportunity exists, should return empty list."""
        router = StrategyRouter()
        # mode=arb but no spread
        state = {
            "mode": "arb",
            "pm_ask": 0.50,
            "pm_bid": 0.49,
            "op_ask": 0.51,
            "op_bid": 0.50,
        }
        orders = router.on_tick(state)
        assert len(orders) == 0
        assert router.last_routing_mode == RoutingMode.NONE


class TestStrategyRouterMetadata:
    """Tests for order metadata annotation."""

    def test_arb_orders_have_routing_metadata(self):
        """Arb orders should include routing metadata."""
        router = StrategyRouter()
        state = {
            "mode": "arb",
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.55,
            "op_bid": 0.54,
        }
        orders = router.on_tick(state)
        assert len(orders) == 2
        for order in orders:
            assert order.meta is not None
            assert order.meta.get("routing_mode") == "ou_arb"
            assert order.meta.get("routed_by") == "router"

    def test_sniper_orders_have_routing_metadata(self):
        """Sniper orders should include routing metadata."""
        router = StrategyRouter()
        state = {
            "mode": "sniper",
            "best_ask": 0.40,
            "best_bid": 0.39,
        }
        orders = router.on_tick(state)
        assert len(orders) == 1
        assert orders[0].meta is not None
        assert orders[0].meta.get("routing_mode") == "sniper"
        assert orders[0].meta.get("routed_by") == "router"

    def test_orders_have_ai_reason(self):
        """Orders should include AI PM reason."""
        router = StrategyRouter()
        state = {
            "mode": "arb",
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.55,
            "op_bid": 0.54,
        }
        orders = router.on_tick(state)
        assert len(orders) > 0
        assert orders[0].meta.get("ai_reason") is not None


class TestStrategyRouterStats:
    """Tests for routing statistics."""

    def test_stats_track_ou_arb(self):
        """Stats should track OU arb routing."""
        router = StrategyRouter()
        state = {
            "mode": "arb",
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.55,
            "op_bid": 0.54,
        }
        router.on_tick(state)
        stats = router.get_routing_stats()
        assert stats["ou_arb_count"] == 1
        assert stats["sniper_count"] == 0

    def test_stats_track_sniper(self):
        """Stats should track sniper routing."""
        router = StrategyRouter()
        state = {
            "mode": "sniper",
            "best_ask": 0.40,
            "best_bid": 0.39,
        }
        router.on_tick(state)
        stats = router.get_routing_stats()
        assert stats["sniper_count"] == 1
        assert stats["ou_arb_count"] == 0

    def test_stats_track_no_action(self):
        """Stats should track ticks with no action."""
        router = StrategyRouter()
        # No opportunity
        state = {
            "mode": "arb",
            "pm_ask": 0.50,
            "pm_bid": 0.49,
            "op_ask": 0.51,
            "op_bid": 0.50,
        }
        router.on_tick(state)
        stats = router.get_routing_stats()
        assert stats["no_action_count"] == 1

    def test_stats_calculate_percentages(self):
        """Stats should include percentage breakdown."""
        router = StrategyRouter()
        # 2 arb ticks
        arb_state = {
            "mode": "arb",
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.55,
            "op_bid": 0.54,
        }
        router.on_tick(arb_state)
        router.on_tick(arb_state)

        stats = router.get_routing_stats()
        assert stats["total_ticks"] == 2
        assert stats["ou_arb_pct"] == 100.0

    def test_reset_stats(self):
        """reset_stats should clear all counters."""
        router = StrategyRouter()
        state = {
            "mode": "arb",
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.55,
            "op_bid": 0.54,
        }
        router.on_tick(state)
        router.reset_stats()

        stats = router.get_routing_stats()
        assert stats["total_ticks"] == 0
        assert stats["ou_arb_count"] == 0


class TestStrategyRouterCustomStrategies:
    """Tests for custom strategy injection."""

    def test_custom_ou_strategy(self):
        """Router should use injected OU strategy."""
        custom_ou = OUArbStrategy(name="custom_ou", min_profit_rate=0.01)
        router = StrategyRouter(ou_strategy=custom_ou)

        assert router.ou_strategy is custom_ou
        assert router.ou_strategy.name == "custom_ou"

    def test_custom_sniper_strategy(self):
        """Router should use injected sniper strategy."""
        custom_sniper = SniperStrategy(
            name="custom_sniper",
            target_price=0.60,
            min_gap=0.05,
        )
        router = StrategyRouter(sniper_strategy=custom_sniper)

        assert router.sniper_strategy is custom_sniper
        assert router.sniper_strategy.name == "custom_sniper"

    def test_get_child_strategies(self):
        """get_child_strategies should return both strategies."""
        router = StrategyRouter()
        children = router.get_child_strategies()

        assert "ou_arb" in children
        assert "sniper" in children
        assert isinstance(children["ou_arb"], OUArbStrategy)
        assert isinstance(children["sniper"], SniperStrategy)


class TestStrategyRouterDecision:
    """Tests for AI PM decision tracking."""

    def test_get_last_decision_after_tick(self):
        """get_last_decision should return AI PM decision."""
        router = StrategyRouter()
        state = {
            "mode": "arb",
            "pm_ask": 0.45,
            "pm_bid": 0.44,
            "op_ask": 0.55,
            "op_bid": 0.54,
        }
        router.on_tick(state)

        decision = router.get_last_decision()
        assert decision is not None
        assert decision["chosen_strategy"] == "ou_arb"
        assert decision["risk_mode"] == "defensive"
        assert "reason" in decision
        assert "confidence" in decision

    def test_get_last_decision_initially_none(self):
        """get_last_decision should be None before any ticks."""
        router = StrategyRouter()
        assert router.get_last_decision() is None
