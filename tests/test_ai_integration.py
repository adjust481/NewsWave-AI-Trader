# tests/test_ai_integration.py
"""
Pytest-style tests for AI PM integration with StrategyRouter.

Tests the AI PM module and its integration with the router:
- AI PM decide_strategy() function
- Router correctly uses AI PM decisions
- Order metadata contains AI PM info
- Risk parameters helper function
"""

import pytest
from strategies.ai_pm import decide_strategy, get_risk_parameters
from strategies.router import StrategyRouter, RoutingMode
from engine.backtest import BacktestEngine


# =============================================================================
# AI PM decide_strategy() Tests
# =============================================================================

class TestDecideStrategyModeExplicit:
    """Tests for decide_strategy() with explicit mode."""

    def test_mode_arb_returns_ou_arb(self):
        """mode='arb' should return ou_arb strategy."""
        result = decide_strategy({"mode": "arb"})
        assert result["chosen_strategy"] == "ou_arb"

    def test_mode_arb_risk_defensive(self):
        """mode='arb' should have defensive risk."""
        result = decide_strategy({"mode": "arb"})
        assert result["risk_mode"] == "defensive"

    def test_mode_arb_reason(self):
        """mode='arb' should have arb reason."""
        result = decide_strategy({"mode": "arb"})
        assert result["reason"] == "Arbitrage opportunity detected"

    def test_mode_arb_high_confidence(self):
        """mode='arb' should have high confidence."""
        result = decide_strategy({"mode": "arb"})
        assert result["confidence"] == 0.95

    def test_mode_sniper_returns_sniper(self):
        """mode='sniper' should return sniper strategy."""
        result = decide_strategy({"mode": "sniper"})
        assert result["chosen_strategy"] == "sniper"

    def test_mode_sniper_risk_aggressive(self):
        """mode='sniper' should have aggressive risk."""
        result = decide_strategy({"mode": "sniper"})
        assert result["risk_mode"] == "aggressive"

    def test_mode_sniper_reason(self):
        """mode='sniper' should have sniper reason."""
        result = decide_strategy({"mode": "sniper"})
        assert result["reason"] == "Trend sniper signal"

    def test_mode_sniper_confidence(self):
        """mode='sniper' should have 0.80 confidence."""
        result = decide_strategy({"mode": "sniper"})
        assert result["confidence"] == 0.80


class TestDecideStrategyInference:
    """Tests for decide_strategy() inferring from market data."""

    def test_infer_arb_from_spread(self):
        """Should infer arb when spread > threshold."""
        state = {
            "pm_ask": 0.40,
            "op_bid": 0.50,  # spread = 0.10 > 0.002
        }
        result = decide_strategy(state)
        assert result["chosen_strategy"] == "ou_arb"
        assert "spread" in result["reason"].lower()

    def test_infer_arb_confidence_scales_with_spread(self):
        """Confidence should scale with spread size."""
        small_spread = decide_strategy({"pm_ask": 0.49, "op_bid": 0.50})
        large_spread = decide_strategy({"pm_ask": 0.40, "op_bid": 0.60})
        assert large_spread["confidence"] > small_spread["confidence"]

    def test_fallback_to_sniper_when_no_spread(self):
        """Should fallback to sniper when no arb spread."""
        state = {
            "pm_ask": 0.50,
            "op_bid": 0.50,  # no spread
            "best_ask": 0.45,  # sniper data present
        }
        result = decide_strategy(state)
        assert result["chosen_strategy"] == "sniper"

    def test_default_fallback_when_no_data(self):
        """Should default to ou_arb safety fallback."""
        result = decide_strategy({})
        assert result["chosen_strategy"] == "ou_arb"
        assert result["reason"] == "Default safety fallback"
        assert result["confidence"] == 0.50


class TestDecideStrategyReturnStructure:
    """Tests for decide_strategy() return structure."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = decide_strategy({})
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys."""
        result = decide_strategy({})
        assert "chosen_strategy" in result
        assert "risk_mode" in result
        assert "reason" in result
        assert "confidence" in result

    def test_confidence_in_range(self):
        """Confidence should be between 0 and 1."""
        for mode in [None, "arb", "sniper"]:
            state = {"mode": mode} if mode else {}
            result = decide_strategy(state)
            assert 0.0 <= result["confidence"] <= 1.0


# =============================================================================
# get_risk_parameters() Tests
# =============================================================================

class TestGetRiskParameters:
    """Tests for get_risk_parameters() helper."""

    def test_defensive_risk(self):
        """Defensive risk should have conservative parameters."""
        params = get_risk_parameters("defensive")
        assert params["position_scale"] == 0.5
        assert params["max_exposure"] == 0.3
        assert params["stop_loss_pct"] == 0.02

    def test_normal_risk(self):
        """Normal risk should have moderate parameters."""
        params = get_risk_parameters("normal")
        assert params["position_scale"] == 1.0
        assert params["max_exposure"] == 0.5
        assert params["stop_loss_pct"] == 0.05

    def test_aggressive_risk(self):
        """Aggressive risk should have high-risk parameters."""
        params = get_risk_parameters("aggressive")
        assert params["position_scale"] == 1.5
        assert params["max_exposure"] == 0.8
        assert params["stop_loss_pct"] == 0.10

    def test_unknown_risk_defaults_to_normal(self):
        """Unknown risk mode should default to normal."""
        params = get_risk_parameters("unknown")
        assert params["position_scale"] == 1.0


# =============================================================================
# Router + AI PM Integration Tests
# =============================================================================

class TestRouterAIPMIntegration:
    """Tests for StrategyRouter using AI PM."""

    def test_router_calls_ai_pm(self):
        """Router should call AI PM and store decision."""
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

    def test_router_annotates_orders_with_ai_reason(self):
        """Orders should have ai_reason from AI PM."""
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
        assert orders[0].meta.get("ai_reason") == "Arbitrage opportunity detected"

    def test_router_annotates_orders_with_ai_risk_mode(self):
        """Orders should have ai_risk_mode from AI PM."""
        router = StrategyRouter()
        state = {
            "mode": "sniper",
            "best_ask": 0.40,
            "best_bid": 0.39,
        }
        orders = router.on_tick(state)

        assert len(orders) > 0
        assert orders[0].meta.get("ai_risk_mode") == "aggressive"

    def test_router_annotates_orders_with_ai_confidence(self):
        """Orders should have ai_confidence from AI PM."""
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
        assert orders[0].meta.get("ai_confidence") == 0.95


class TestRouterAIPMSniperIntegration:
    """Tests for Router + AI PM with Sniper strategy."""

    def test_sniper_mode_routes_correctly(self):
        """Sniper mode should route to sniper strategy."""
        router = StrategyRouter()
        state = {
            "mode": "sniper",
            "best_ask": 0.40,
            "best_bid": 0.39,
        }
        orders = router.on_tick(state)

        assert router.last_routing_mode == RoutingMode.SNIPER
        assert len(orders) == 1
        assert orders[0].side == "BUY"

    def test_sniper_orders_have_correct_metadata(self):
        """Sniper orders should have correct AI metadata."""
        router = StrategyRouter()
        state = {
            "mode": "sniper",
            "best_ask": 0.40,
            "best_bid": 0.39,
        }
        orders = router.on_tick(state)

        assert orders[0].meta.get("routing_mode") == "sniper"
        assert orders[0].meta.get("ai_reason") == "Trend sniper signal"
        assert orders[0].meta.get("ai_risk_mode") == "aggressive"


# =============================================================================
# Full Integration: Router + AI PM + BacktestEngine
# =============================================================================

class TestFullIntegration:
    """Tests for complete integration: Router + AI PM + BacktestEngine."""

    def test_backtest_processes_mixed_series(self):
        """BacktestEngine should process mixed arb/sniper ticks."""
        router = StrategyRouter()
        engine = BacktestEngine(strategy=router, initial_cash=1000.0)

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
            # Tick 2: No opportunity
            {
                "mode": "sniper",
                "best_ask": 0.55,
                "best_bid": 0.54,
            },
        ]

        result = engine.run(series)

        # arb=2, sniper=1, none=0 -> 3 trades
        assert result.total_trades == 3

    def test_backtest_trades_have_ai_metadata(self):
        """All trades should have AI metadata."""
        router = StrategyRouter()
        engine = BacktestEngine(strategy=router, initial_cash=1000.0)

        series = [
            {"mode": "arb", "pm_ask": 0.45, "pm_bid": 0.44, "op_ask": 0.55, "op_bid": 0.54},
            {"mode": "sniper", "best_ask": 0.40, "best_bid": 0.39},
        ]

        result = engine.run(series)

        for trade in result.trades:
            assert trade.meta is not None
            assert "ai_reason" in trade.meta
            assert trade.meta.get("routing_mode") in ["ou_arb", "sniper"]

    def test_routing_stats_correct_after_backtest(self):
        """Router stats should match actual routing."""
        router = StrategyRouter()
        engine = BacktestEngine(strategy=router, initial_cash=1000.0)

        series = [
            {"mode": "arb", "pm_ask": 0.45, "pm_bid": 0.44, "op_ask": 0.55, "op_bid": 0.54},
            {"mode": "sniper", "best_ask": 0.40, "best_bid": 0.39},
            {"mode": "sniper", "best_ask": 0.55, "best_bid": 0.54},  # no opportunity
        ]

        engine.run(series)
        stats = router.get_routing_stats()

        assert stats["ou_arb_count"] == 1
        assert stats["sniper_count"] == 1
        assert stats["no_action_count"] == 1
        assert stats["total_ticks"] == 3
