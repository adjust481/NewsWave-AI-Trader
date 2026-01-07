# tests/test_strategies.py
"""
Pytest-style tests for individual strategies: OUArbStrategy and SniperStrategy.

Tests are organized by strategy and scenario.
"""

import pytest
from strategies.ou_arb import OUArbStrategy
from strategies.sniper import SniperStrategy


# =============================================================================
# OUArbStrategy Tests
# =============================================================================

class TestOUArbStrategy:
    """Tests for the OUArbStrategy (arbitrage)."""

    def test_no_spread_no_orders(self):
        """When there's no spread between PM and OP, no orders should be generated."""
        ou = OUArbStrategy(name="ou_test")
        state = {
            "pm_ask": 0.50,
            "pm_bid": 0.49,
            "op_ask": 0.50,
            "op_bid": 0.49,
        }
        orders = ou.on_tick(state)
        assert len(orders) == 0

    def test_negative_spread_no_orders(self):
        """When spread is negative (OP bid < PM ask), no orders."""
        ou = OUArbStrategy(name="ou_test")
        state = {
            "pm_ask": 0.55,
            "pm_bid": 0.54,
            "op_ask": 0.50,
            "op_bid": 0.49,
        }
        orders = ou.on_tick(state)
        assert len(orders) == 0

    def test_large_spread_generates_orders(self):
        """When spread is large (op_bid - pm_ask > threshold), should generate orders."""
        ou = OUArbStrategy(name="ou_test")
        state = {
            "pm_ask": 0.40,
            "pm_bid": 0.39,
            "op_ask": 0.61,
            "op_bid": 0.60,
        }
        orders = ou.on_tick(state)
        assert len(orders) == 2
        # First order: BUY on PM
        assert orders[0].side == "BUY"
        assert orders[0].price == 0.40
        # Second order: SELL on OP
        assert orders[1].side == "SELL"
        assert orders[1].price == 0.60

    def test_order_sizes_match(self):
        """Both legs of the arb should have matching sizes."""
        ou = OUArbStrategy(name="ou_test")
        state = {
            "pm_ask": 0.40,
            "pm_bid": 0.39,
            "op_ask": 0.61,
            "op_bid": 0.60,
        }
        orders = ou.on_tick(state)
        assert len(orders) == 2
        assert orders[0].size == orders[1].size

    def test_missing_fields_no_orders(self):
        """Missing price fields should not cause errors, just no orders."""
        ou = OUArbStrategy(name="ou_test")
        orders = ou.on_tick({})
        assert len(orders) == 0

    def test_is_opportunity_true_when_spread(self):
        """is_opportunity should return True when there's a valid spread."""
        ou = OUArbStrategy(name="ou_test")
        state = {
            "pm_ask": 0.40,
            "pm_bid": 0.39,
            "op_ask": 0.61,
            "op_bid": 0.60,
        }
        assert ou.is_opportunity(state) is True

    def test_is_opportunity_false_when_no_spread(self):
        """is_opportunity should return False when there's no valid spread."""
        ou = OUArbStrategy(name="ou_test")
        state = {
            "pm_ask": 0.50,
            "pm_bid": 0.49,
            "op_ask": 0.51,
            "op_bid": 0.50,
        }
        assert ou.is_opportunity(state) is False


# =============================================================================
# SniperStrategy Tests
# =============================================================================

class TestSniperStrategy:
    """Tests for the SniperStrategy (directional)."""

    def test_price_too_high_no_buy(self):
        """When best_ask > target - min_gap, should not generate BUY."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        state = {"best_ask": 0.55, "best_bid": 0.54}
        orders = sniper.on_tick(state)
        assert len(orders) == 0

    def test_price_at_threshold_generates_buy(self):
        """When best_ask == target - min_gap, should generate BUY (gap >= min_gap)."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        state = {"best_ask": 0.48, "best_bid": 0.47}
        orders = sniper.on_tick(state)
        # At exactly the threshold, gap == min_gap, which triggers (>=, not >)
        assert len(orders) == 1
        assert orders[0].side == "BUY"

    def test_price_below_threshold_generates_buy(self):
        """When best_ask < target - min_gap, should generate BUY."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        state = {"best_ask": 0.40, "best_bid": 0.39}
        orders = sniper.on_tick(state)
        assert len(orders) == 1
        assert orders[0].side == "BUY"
        assert orders[0].price == 0.40

    def test_buy_order_size_is_shares(self):
        """BUY order size is in shares (position_size / price), not USD."""
        sniper = SniperStrategy(
            name="sniper_test",
            target_price=0.50,
            min_gap=0.02,
            position_size=100.0,  # $100 USD
        )
        state = {"best_ask": 0.40, "best_bid": 0.39}
        orders = sniper.on_tick(state)
        assert len(orders) == 1
        # shares = position_size_usd / price = 100 / 0.40 = 250
        assert orders[0].size == 250.0

    def test_take_profit_requires_position_in_market_state(self):
        """SELL for take-profit should only trigger if market_state has_position=True."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        # Price above target, but no has_position in market_state
        state = {"best_ask": 0.60, "best_bid": 0.55}
        orders = sniper.on_tick(state)
        assert len(orders) == 0

    def test_take_profit_with_position_flag(self):
        """When has_position=True in market_state and price > target, should generate SELL."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        # has_position flag is in market_state, not on the strategy object
        state = {"best_ask": 0.60, "best_bid": 0.55, "has_position": True}
        orders = sniper.on_tick(state)
        assert len(orders) == 1
        assert orders[0].side == "SELL"
        assert orders[0].price == 0.55

    def test_supports_current_ask_field(self):
        """Should also work with 'current_ask' field name."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        state = {"current_ask": 0.40, "current_bid": 0.39}
        orders = sniper.on_tick(state)
        assert len(orders) == 1
        assert orders[0].side == "BUY"

    def test_is_opportunity_true_when_below_threshold(self):
        """is_opportunity should return True when price below threshold."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        state = {"best_ask": 0.40, "best_bid": 0.39}
        assert sniper.is_opportunity(state) is True

    def test_is_opportunity_false_when_above_threshold(self):
        """is_opportunity should return False when price above threshold."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        state = {"best_ask": 0.55, "best_bid": 0.54}
        assert sniper.is_opportunity(state) is False

    def test_missing_fields_no_orders(self):
        """Missing price fields should not cause errors, just no orders."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        orders = sniper.on_tick({})
        assert len(orders) == 0

    def test_order_metadata_contains_strategy_info(self):
        """Order metadata should contain strategy info."""
        sniper = SniperStrategy(name="sniper_test", target_price=0.50, min_gap=0.02)
        state = {"best_ask": 0.40, "best_bid": 0.39}
        orders = sniper.on_tick(state)
        assert len(orders) == 1
        assert orders[0].meta is not None
        assert "strategy" in orders[0].meta or "reason" in orders[0].meta
