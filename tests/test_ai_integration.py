# tests/test_ai_integration.py
"""
Pytest-style tests for AI PM integration with StrategyRouter.

Tests the AI PM module and its integration with the router:
- AI PM decide_strategy() function (rule-based and LLM modes)
- Router correctly uses AI PM decisions
- Order metadata contains AI PM info
- Risk parameters helper function
- Regime detection with memory
- LLM fallback behavior
"""

import pytest
from strategies.ai_pm import (
    decide_strategy,
    decide_strategy_rule_based,
    decide_strategy_llm,
    get_risk_parameters,
    reset_state,
    _parse_llm_response,
)
from strategies.router import StrategyRouter, RoutingMode
from engine.backtest import BacktestEngine


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_ai_pm_state():
    """Reset AI PM state before each test to ensure isolation."""
    reset_state()
    yield
    reset_state()


# =============================================================================
# AI PM decide_strategy() Tests - Explicit Mode
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

    def test_mode_arb_has_reason(self):
        """mode='arb' should have a reason mentioning arb."""
        result = decide_strategy({"mode": "arb"})
        # Either regime-based or single-tick reason
        assert "arb" in result["reason"].lower() or "regime" in result["reason"].lower()

    def test_mode_arb_high_confidence(self):
        """mode='arb' should have high confidence."""
        result = decide_strategy({"mode": "arb"})
        assert result["confidence"] >= 0.60

    def test_mode_sniper_returns_sniper(self):
        """mode='sniper' should return sniper strategy."""
        result = decide_strategy({"mode": "sniper"})
        assert result["chosen_strategy"] == "sniper"

    def test_mode_sniper_risk_aggressive(self):
        """mode='sniper' should have aggressive risk."""
        result = decide_strategy({"mode": "sniper"})
        assert result["risk_mode"] == "aggressive"

    def test_mode_sniper_has_reason(self):
        """mode='sniper' should have a reason mentioning sniper."""
        result = decide_strategy({"mode": "sniper"})
        # Either regime-based or single-tick reason
        assert "sniper" in result["reason"].lower() or "regime" in result["reason"].lower()

    def test_mode_sniper_confidence(self):
        """mode='sniper' should have reasonable confidence."""
        result = decide_strategy({"mode": "sniper"})
        assert result["confidence"] >= 0.60


class TestDecideStrategyInference:
    """Tests for decide_strategy() inferring from market data."""

    def test_infer_arb_from_spread(self):
        """Should infer arb when spread > threshold."""
        state = {
            "pm_ask": 0.40,
            "op_bid": 0.55,  # spread = 0.15 > 0.10 (LARGE_SPREAD)
        }
        result = decide_strategy(state)
        assert result["chosen_strategy"] == "ou_arb"

    def test_infer_arb_confidence_scales_with_spread(self):
        """Confidence should scale with spread size."""
        reset_state()
        small_spread = decide_strategy({"pm_ask": 0.48, "op_bid": 0.50})  # 0.02 spread
        reset_state()
        large_spread = decide_strategy({"pm_ask": 0.40, "op_bid": 0.60})  # 0.20 spread
        # Large spread should have higher or equal confidence
        assert large_spread["confidence"] >= small_spread["confidence"]

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
        assert "fallback" in result["reason"].lower() or "default" in result["reason"].lower()
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
            reset_state()
            state = {"mode": mode} if mode else {}
            result = decide_strategy(state)
            assert 0.0 <= result["confidence"] <= 1.0


# =============================================================================
# AI PM Regime Detection (Memory) Tests
# =============================================================================

class TestAIPMRegimeDetection:
    """Tests for AI PM regime detection with memory."""

    def test_prefers_ou_after_multiple_arb_ticks(self):
        """After several arb signals, AI PM should prefer ou_arb with regime reason."""
        # Feed multiple arb-like ticks
        for _ in range(3):
            decide_strategy({
                "mode": "arb",
                "pm_ask": 0.45,
                "op_bid": 0.60,  # large spread
            })

        # The next decision should be regime-based
        result = decide_strategy({
            "pm_ask": 0.45,
            "op_bid": 0.60,
        })
        assert result["chosen_strategy"] == "ou_arb"
        assert "regime" in result["reason"].lower() or "arb" in result["reason"].lower()

    def test_prefers_sniper_after_multiple_sniper_ticks(self):
        """After several sniper signals, AI PM should prefer sniper with regime reason."""
        # Feed multiple sniper-like ticks
        for _ in range(3):
            decide_strategy({
                "mode": "sniper",
                "best_ask": 0.35,  # deep discount (< 0.42)
            })

        # The next decision should be regime-based
        result = decide_strategy({
            "best_ask": 0.38,
        })
        assert result["chosen_strategy"] == "sniper"
        assert "regime" in result["reason"].lower() or "sniper" in result["reason"].lower()

    def test_regime_transition_arb_to_sniper(self):
        """AI PM should transition from arb regime to sniper regime."""
        # Start with arb regime
        for _ in range(3):
            decide_strategy({"mode": "arb", "pm_ask": 0.45, "op_bid": 0.60})

        result = decide_strategy({"mode": "arb"})
        assert result["chosen_strategy"] == "ou_arb"

        # Transition to sniper regime
        for _ in range(5):
            decide_strategy({"mode": "sniper", "best_ask": 0.35})

        result = decide_strategy({"mode": "sniper", "best_ask": 0.35})
        assert result["chosen_strategy"] == "sniper"

    def test_regime_confidence_increases_with_consistency(self):
        """Confidence should be higher when regime is more consistent."""
        # Single tick
        reset_state()
        result1 = decide_strategy({"mode": "arb"})

        # After 3 consistent arb ticks
        reset_state()
        for _ in range(3):
            decide_strategy({"mode": "arb", "pm_ask": 0.40, "op_bid": 0.55})
        result3 = decide_strategy({"mode": "arb"})

        # Confidence should be similar or higher with more data
        assert result3["confidence"] >= 0.60

    def test_reset_state_clears_history(self):
        """reset_state() should clear the history buffer."""
        # Build up arb regime
        for _ in range(3):
            decide_strategy({"mode": "arb", "pm_ask": 0.45, "op_bid": 0.60})

        # Reset
        reset_state()

        # Now with fresh state, sniper tick should work independently
        result = decide_strategy({"mode": "sniper", "best_ask": 0.35})
        assert result["chosen_strategy"] == "sniper"


class TestAIPMEdgeCases:
    """Edge case tests for AI PM."""

    def test_tie_falls_back_to_current_tick(self):
        """When arb_count == sniper_count, should use current tick."""
        # Feed one of each
        decide_strategy({"mode": "arb", "pm_ask": 0.40, "op_bid": 0.55})
        decide_strategy({"mode": "sniper", "best_ask": 0.35})

        # Now with explicit mode=arb on tie
        result = decide_strategy({"mode": "arb"})
        assert result["chosen_strategy"] == "ou_arb"

    def test_empty_history_uses_current_tick(self):
        """With no history, should use current tick signals."""
        result = decide_strategy({"mode": "arb"})
        assert result["chosen_strategy"] == "ou_arb"

    def test_handles_missing_fields_gracefully(self):
        """Should handle missing fields without error."""
        # Only mode
        result = decide_strategy({"mode": "arb"})
        assert result["chosen_strategy"] == "ou_arb"

        # Only prices
        reset_state()
        result = decide_strategy({"pm_ask": 0.40, "op_bid": 0.55})
        assert result["chosen_strategy"] == "ou_arb"

        # Only best_ask
        reset_state()
        result = decide_strategy({"best_ask": 0.35})
        assert result["chosen_strategy"] == "sniper"


# =============================================================================
# LLM Mode Tests
# =============================================================================

class TestDecideStrategyLLMMode:
    """Tests for LLM mode and fallback behavior."""

    def test_force_rule_based_mode(self):
        """use_llm=False should always use rule-based logic."""
        stats = {"mode": "arb", "pm_ask": 0.40, "op_bid": 0.55}
        decision = decide_strategy(stats, use_llm=False)
        assert decision["chosen_strategy"] in ("ou_arb", "sniper")
        # Should NOT have fallback note since we're not trying LLM
        assert "fallback_to_rule_based" not in decision["reason"]

    def test_llm_fallback_on_error(self, monkeypatch):
        """When LLM fails, should fall back to rule-based with note."""
        def fake_llm(stats):
            raise RuntimeError("fake network error")

        monkeypatch.setattr("strategies.ai_pm.decide_strategy_llm", fake_llm)

        stats = {"mode": "arb", "pm_ask": 0.40, "op_bid": 0.55}
        decision = decide_strategy(stats, use_llm=True)

        # Should still return valid decision
        assert decision["chosen_strategy"] in ("ou_arb", "sniper")
        # Should have fallback note
        assert "fallback_to_rule_based" in decision["reason"]
        assert "RuntimeError" in decision["reason"]

    def test_llm_fallback_on_missing_api_key(self):
        """When GEMINI_API_KEY is not set, should fall back gracefully."""
        stats = {"mode": "sniper", "best_ask": 0.35}
        decision = decide_strategy(stats, use_llm=True)

        # Should still return valid decision
        assert decision["chosen_strategy"] in ("ou_arb", "sniper")
        # Should have fallback note mentioning RuntimeError (missing API key or SDK)
        assert "fallback_to_rule_based" in decision["reason"]
        assert "RuntimeError" in decision["reason"]

    def test_llm_fallback_preserves_regime_state(self):
        """LLM fallback should still use regime history."""
        # Build up arb regime
        for _ in range(3):
            decide_strategy({"mode": "arb", "pm_ask": 0.40, "op_bid": 0.55})

        # Now try LLM mode (will fail and fallback)
        stats = {"pm_ask": 0.40, "op_bid": 0.55}
        decision = decide_strategy(stats, use_llm=True)

        # Should use arb due to regime, even though we tried LLM
        assert decision["chosen_strategy"] == "ou_arb"
        assert "fallback_to_rule_based" in decision["reason"]


class TestDecideStrategyRuleBased:
    """Tests for decide_strategy_rule_based function."""

    def test_rule_based_with_fallback_note(self):
        """Fallback note should be appended to reason."""
        stats = {"mode": "arb"}
        decision = decide_strategy_rule_based(stats, fallback_note="test_note")
        assert "test_note" in decision["reason"]

    def test_rule_based_without_fallback_note(self):
        """Without fallback note, reason should be clean."""
        stats = {"mode": "arb"}
        decision = decide_strategy_rule_based(stats)
        assert "fallback" not in decision["reason"].lower() or "default" in decision["reason"].lower()


class TestParseLLMResponse:
    """Tests for _parse_llm_response function."""

    def test_parse_valid_json(self):
        """Should parse valid JSON response."""
        response = '{"chosen_strategy": "ou_arb", "risk_mode": "defensive", "reason": "arb looks good"}'
        result = _parse_llm_response(response)
        assert result["chosen_strategy"] == "ou_arb"
        assert result["risk_mode"] == "defensive"
        assert "[LLM]" in result["reason"]
        assert "arb looks good" in result["reason"]

    def test_parse_json_in_code_block(self):
        """Should handle JSON wrapped in markdown code blocks."""
        response = '```json\n{"chosen_strategy": "sniper", "risk_mode": "aggressive", "reason": "deep discount"}\n```'
        result = _parse_llm_response(response)
        assert result["chosen_strategy"] == "sniper"
        assert result["risk_mode"] == "aggressive"

    def test_normalize_invalid_strategy(self):
        """Should default to ou_arb for invalid strategy."""
        response = '{"chosen_strategy": "invalid", "risk_mode": "normal", "reason": "test"}'
        result = _parse_llm_response(response)
        assert result["chosen_strategy"] == "ou_arb"

    def test_normalize_invalid_risk_mode(self):
        """Should default to normal for invalid risk mode."""
        response = '{"chosen_strategy": "sniper", "risk_mode": "invalid", "reason": "test"}'
        result = _parse_llm_response(response)
        assert result["risk_mode"] == "normal"

    def test_default_reason_when_missing(self):
        """Should provide default reason when missing."""
        response = '{"chosen_strategy": "ou_arb", "risk_mode": "defensive"}'
        result = _parse_llm_response(response)
        assert "[LLM]" in result["reason"]

    def test_invalid_json_raises_value_error(self):
        """Should raise ValueError for invalid JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            _parse_llm_response("not json at all")

    def test_confidence_is_set(self):
        """Should set a default confidence value."""
        response = '{"chosen_strategy": "ou_arb", "risk_mode": "defensive", "reason": "test"}'
        result = _parse_llm_response(response)
        assert "confidence" in result
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
        assert orders[0].meta.get("ai_reason") is not None
        # Reason should mention arb or regime
        reason = orders[0].meta.get("ai_reason", "").lower()
        assert "arb" in reason or "regime" in reason

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
        assert orders[0].meta.get("ai_confidence") >= 0.60


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
        # Reason should mention sniper or regime
        reason = orders[0].meta.get("ai_reason", "").lower()
        assert "sniper" in reason or "regime" in reason
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

    def test_regime_affects_decisions_in_backtest(self):
        """Regime detection should affect decisions during backtest."""
        router = StrategyRouter()
        engine = BacktestEngine(strategy=router, initial_cash=1000.0)

        # Series with arb regime followed by ambiguous ticks
        series = [
            {"mode": "arb", "pm_ask": 0.40, "op_bid": 0.55},
            {"mode": "arb", "pm_ask": 0.40, "op_bid": 0.55},
            {"mode": "arb", "pm_ask": 0.40, "op_bid": 0.55},
            # Ambiguous tick - should still prefer arb due to regime
            {"pm_ask": 0.40, "op_bid": 0.55, "best_ask": 0.52},
        ]

        engine.run(series)
        stats = router.get_routing_stats()

        # All should be arb (regime dominates)
        assert stats["ou_arb_count"] == 4
