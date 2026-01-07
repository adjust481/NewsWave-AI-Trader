# tests/test_backtest_router.py
"""
Pytest-style tests for BacktestEngine with StrategyRouter.

Tests the integration between:
- BacktestEngine: Runs strategies on market data series
- StrategyRouter: Routes to child strategies based on AI PM decisions
"""

import pytest
from strategies.router import StrategyRouter
from strategies.ou_arb import OUArbStrategy
from strategies.sniper import SniperStrategy
from engine.backtest import BacktestEngine, BacktestResult


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def router():
    """Fresh router instance."""
    return StrategyRouter()


@pytest.fixture
def engine(router):
    """BacktestEngine with router strategy."""
    return BacktestEngine(strategy=router, initial_cash=1000.0)


@pytest.fixture
def arb_tick():
    """Market state with arb opportunity."""
    return {
        "mode": "arb",
        "pm_ask": 0.45,
        "pm_bid": 0.44,
        "op_ask": 0.55,
        "op_bid": 0.54,
    }


@pytest.fixture
def sniper_tick():
    """Market state with sniper opportunity."""
    return {
        "mode": "sniper",
        "best_ask": 0.40,
        "best_bid": 0.39,
    }


@pytest.fixture
def no_opportunity_tick():
    """Market state with no opportunity."""
    return {
        "mode": "sniper",
        "best_ask": 0.55,
        "best_bid": 0.54,
    }


# =============================================================================
# BacktestResult Tests
# =============================================================================

class TestBacktestResult:
    """Tests for BacktestResult dataclass."""

    def test_result_is_dataclass(self, engine, arb_tick):
        """BacktestEngine.run() should return a BacktestResult dataclass."""
        result = engine.run([arb_tick])
        assert isinstance(result, BacktestResult)

    def test_result_has_strategy_name(self, engine, arb_tick):
        """Result should include strategy name."""
        result = engine.run([arb_tick])
        assert result.strategy_name == "router"

    def test_result_has_initial_cash(self, engine, arb_tick):
        """Result should track initial cash."""
        result = engine.run([arb_tick])
        assert result.initial_cash == 1000.0

    def test_result_has_equity_curve(self, engine, arb_tick, sniper_tick):
        """Result should include equity curve with one entry per tick (no initial)."""
        series = [arb_tick, sniper_tick]
        result = engine.run(series)
        # BacktestEngine records equity after each tick (not before)
        assert len(result.equity_curve) == len(series)

    def test_result_has_trades_list(self, engine, arb_tick):
        """Result should include list of executed trades."""
        result = engine.run([arb_tick])
        assert isinstance(result.trades, list)
        assert len(result.trades) > 0


# =============================================================================
# Engine Execution Tests
# =============================================================================

class TestBacktestEngineExecution:
    """Tests for BacktestEngine execution."""

    def test_arb_tick_generates_trades(self, engine, arb_tick):
        """Arb tick should generate 2 trades (BUY + SELL)."""
        result = engine.run([arb_tick])
        assert result.total_trades == 2

    def test_sniper_tick_generates_trade(self, engine, sniper_tick):
        """Sniper tick should generate 1 trade (BUY)."""
        result = engine.run([sniper_tick])
        assert result.total_trades == 1

    def test_no_opportunity_no_trades(self, engine, no_opportunity_tick):
        """Tick with no opportunity should generate 0 trades."""
        result = engine.run([no_opportunity_tick])
        assert result.total_trades == 0

    def test_mixed_series(self, engine, arb_tick, sniper_tick, no_opportunity_tick):
        """Mixed series should process all ticks correctly."""
        series = [arb_tick, sniper_tick, no_opportunity_tick]
        result = engine.run(series)
        # arb=2, sniper=1, none=0 -> total=3
        assert result.total_trades == 3


# =============================================================================
# Trade Metadata Tests
# =============================================================================

class TestTradeMetadata:
    """Tests for trade metadata from router."""

    def test_arb_trades_have_routing_mode(self, engine, arb_tick):
        """Arb trades should have routing_mode='ou_arb'."""
        result = engine.run([arb_tick])
        for trade in result.trades:
            assert trade.meta is not None
            assert trade.meta.get("routing_mode") == "ou_arb"

    def test_sniper_trades_have_routing_mode(self, engine, sniper_tick):
        """Sniper trades should have routing_mode='sniper'."""
        result = engine.run([sniper_tick])
        for trade in result.trades:
            assert trade.meta is not None
            assert trade.meta.get("routing_mode") == "sniper"

    def test_trades_have_ai_reason(self, engine, arb_tick):
        """Trades should include AI PM reason."""
        result = engine.run([arb_tick])
        for trade in result.trades:
            assert trade.meta is not None
            assert "ai_reason" in trade.meta

    def test_trades_have_ai_risk_mode(self, engine, arb_tick):
        """Trades should include AI risk mode."""
        result = engine.run([arb_tick])
        for trade in result.trades:
            assert trade.meta.get("ai_risk_mode") is not None


# =============================================================================
# Equity Tracking Tests
# =============================================================================

class TestEquityTracking:
    """Tests for equity curve and returns."""

    def test_first_equity_after_trades(self, engine, arb_tick):
        """First equity curve entry is equity after the first tick's trades."""
        result = engine.run([arb_tick])
        # After arb trades, equity should be different from initial cash
        # (Arb BUY then SELL should result in profit)
        assert len(result.equity_curve) == 1
        assert result.equity_curve[0] == result.final_equity

    def test_final_equity_calculated(self, engine, arb_tick):
        """final_equity should be the last equity curve value."""
        result = engine.run([arb_tick])
        assert result.final_equity == result.equity_curve[-1]

    def test_total_return_calculated(self, engine, arb_tick):
        """total_return should be (final - initial) / initial."""
        result = engine.run([arb_tick])
        expected_return = (result.final_equity - result.initial_cash) / result.initial_cash
        assert abs(result.total_return - expected_return) < 0.0001


# =============================================================================
# Standalone Strategy Tests
# =============================================================================

class TestBacktestWithStandaloneStrategies:
    """Tests for BacktestEngine with individual strategies (not router)."""

    def test_ou_strategy_alone(self, arb_tick):
        """BacktestEngine should work with OUArbStrategy directly."""
        ou = OUArbStrategy(name="ou_direct")
        engine = BacktestEngine(strategy=ou, initial_cash=1000.0)
        result = engine.run([arb_tick])
        assert result.strategy_name == "ou_direct"
        assert result.total_trades == 2

    def test_sniper_strategy_alone(self, sniper_tick):
        """BacktestEngine should work with SniperStrategy directly."""
        sniper = SniperStrategy(name="sniper_direct", target_price=0.50, min_gap=0.02)
        engine = BacktestEngine(strategy=sniper, initial_cash=1000.0)
        result = engine.run([sniper_tick])
        assert result.strategy_name == "sniper_direct"
        assert result.total_trades == 1
