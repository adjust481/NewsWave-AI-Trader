# engine/backtest.py
"""
Single-Strategy Backtester

A minimal, clean backtesting engine for running a single strategy
against historical market data. Step 3A of the migration.

Design principles:
- Pure Python logic, no I/O inside the loop
- Works with any BaseStrategy implementation
- Simple execution model: market orders at current price
- No leverage, no complex fees (those belong in Step 3B+)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

from strategies.base import BaseStrategy, OrderInstruction


@dataclass
class Trade:
    """
    Record of an executed trade.
    """
    tick: int
    timestamp: Optional[Any]
    side: str               # "BUY" or "SELL"
    price: float            # Execution price
    size: float             # Number of units traded
    cost: float             # Total cost (size * price) for BUY, revenue for SELL
    position_after: float   # Position after this trade
    cash_after: float       # Cash after this trade
    meta: Optional[Dict[str, Any]] = None


@dataclass
class BacktestResult:
    """
    Complete result of a backtest run.
    """
    strategy_name: str
    initial_cash: float
    final_cash: float
    final_position: float
    final_equity: float
    total_return: float         # (final_equity - initial_cash) / initial_cash
    total_trades: int
    winning_trades: int
    losing_trades: int
    equity_curve: List[float]
    trades: List[Trade]

    # Summary statistics
    max_equity: float = 0.0
    min_equity: float = 0.0
    max_drawdown: float = 0.0   # Maximum peak-to-trough decline


class BacktestEngine:
    """
    Single-Strategy Backtester.

    A minimal engine that:
    1. Iterates through market data (list of dicts)
    2. Calls strategy.on_tick() each step
    3. Simulates execution of OrderInstructions
    4. Tracks cash, position, and equity over time

    Execution Model:
    - BUY: Decrease cash by (size * price), increase position by size
    - SELL: Increase cash by (size * price), decrease position by size
    - Assumes market orders fill at the price specified in market_state

    Example usage:
        strategy = SniperStrategy(target_price=0.50, min_gap=0.02)
        engine = BacktestEngine(strategy, initial_cash=10000)
        result = engine.run(market_data)
        print(f"Final equity: {result.final_equity}")
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_cash: float = 10000.0,
    ) -> None:
        """
        Initialize the backtest engine.

        Args:
            strategy: An instance of a BaseStrategy subclass.
            initial_cash: Starting cash balance in USD.
        """
        self.strategy = strategy
        self.initial_cash = initial_cash

        # State variables (reset on each run)
        self.cash: float = initial_cash
        self.position: float = 0.0  # Number of units held
        self.equity_curve: List[float] = []
        self.trades: List[Trade] = []

    def _reset(self) -> None:
        """Reset state for a new backtest run."""
        self.cash = self.initial_cash
        self.position = 0.0
        self.equity_curve = []
        self.trades = []

    def _get_execution_price(
        self,
        market_state: Dict[str, Any],
        side: str
    ) -> Optional[float]:
        """
        Determine the execution price for an order.

        For BUY orders: use ask price (what we pay to buy)
        For SELL orders: use bid price (what we receive when selling)

        Falls back to 'price' or 'mid_price' if bid/ask not available.

        Args:
            market_state: Current market state dictionary.
            side: "BUY" or "SELL"

        Returns:
            Execution price, or None if no valid price found.
        """
        if side == "BUY":
            # Try ask price first (various naming conventions)
            price = (
                market_state.get("best_ask") or
                market_state.get("pm_ask") or
                market_state.get("ask") or
                market_state.get("price") or
                market_state.get("mid_price")
            )
        else:  # SELL
            # Try bid price first
            price = (
                market_state.get("best_bid") or
                market_state.get("op_bid") or
                market_state.get("bid") or
                market_state.get("price") or
                market_state.get("mid_price")
            )

        return price if price and price > 0 else None

    def _get_mark_price(self, market_state: Dict[str, Any]) -> float:
        """
        Get the mark-to-market price for equity calculation.

        Uses mid price if available, otherwise falls back to any available price.

        Args:
            market_state: Current market state dictionary.

        Returns:
            Mark price for valuation.
        """
        # Try mid price first
        if "mid_price" in market_state:
            return market_state["mid_price"]

        # Calculate mid from bid/ask
        bid = (
            market_state.get("best_bid") or
            market_state.get("op_bid") or
            market_state.get("bid") or
            0
        )
        ask = (
            market_state.get("best_ask") or
            market_state.get("pm_ask") or
            market_state.get("ask") or
            0
        )

        if bid > 0 and ask > 0:
            return (bid + ask) / 2

        # Fall back to any price
        return (
            market_state.get("price") or
            bid or
            ask or
            0.5  # Default if nothing available
        )

    def _execute_order(
        self,
        instruction: OrderInstruction,
        market_state: Dict[str, Any],
        tick: int,
    ) -> Optional[Trade]:
        """
        Execute a single order instruction.

        Args:
            instruction: The order to execute.
            market_state: Current market state.
            tick: Current tick index.

        Returns:
            Trade record if executed, None if rejected.
        """
        side = instruction.side.upper()
        size = instruction.size

        # Skip invalid orders
        if size <= 0:
            return None

        # Get execution price
        exec_price = instruction.price  # Use limit price if specified
        if exec_price is None or exec_price <= 0:
            exec_price = self._get_execution_price(market_state, side)

        if exec_price is None or exec_price <= 0:
            return None

        # Calculate cost/revenue
        if side == "BUY":
            cost = size * exec_price

            # Check if we have enough cash
            if cost > self.cash:
                # Reduce size to what we can afford
                size = self.cash / exec_price
                cost = size * exec_price

                if size <= 0:
                    return None

            # Execute: decrease cash, increase position
            self.cash -= cost
            self.position += size

        elif side == "SELL":
            # Check if we have enough position
            if size > self.position:
                size = self.position  # Can only sell what we have

                if size <= 0:
                    return None

            revenue = size * exec_price

            # Execute: increase cash, decrease position
            self.cash += revenue
            self.position -= size
            cost = -revenue  # Negative cost = revenue

        else:
            return None  # Unknown side

        # Create trade record
        trade = Trade(
            tick=tick,
            timestamp=market_state.get("timestamp"),
            side=side,
            price=exec_price,
            size=size,
            cost=cost if side == "BUY" else -cost,
            position_after=self.position,
            cash_after=self.cash,
            meta=instruction.meta,
        )

        return trade

    def run(self, market_data: List[Dict[str, Any]]) -> BacktestResult:
        """
        Run the backtest over the provided market data.

        Args:
            market_data: List of market state dictionaries, one per tick.
                        Each dict should contain price information
                        (e.g., best_ask, best_bid, price, mid_price).

        Returns:
            BacktestResult containing equity curve, trades, and statistics.
        """
        self._reset()

        if not market_data:
            return self._build_result()

        # Track for drawdown calculation
        peak_equity = self.initial_cash
        max_drawdown = 0.0

        # Main backtest loop
        for tick, market_state in enumerate(market_data):
            # 1. Call strategy to get order instructions
            instructions = self.strategy.on_tick(market_state)

            # 2. Execute each instruction
            for instruction in instructions:
                trade = self._execute_order(instruction, market_state, tick)
                if trade:
                    self.trades.append(trade)

            # 3. Calculate current equity (cash + position * mark_price)
            mark_price = self._get_mark_price(market_state)
            equity = self.cash + self.position * mark_price
            self.equity_curve.append(equity)

            # 4. Update drawdown tracking
            if equity > peak_equity:
                peak_equity = equity
            drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return self._build_result(max_drawdown)

    def _build_result(self, max_drawdown: float = 0.0) -> BacktestResult:
        """
        Build the final backtest result.

        Args:
            max_drawdown: Maximum drawdown observed during backtest.

        Returns:
            BacktestResult with all statistics.
        """
        final_equity = self.equity_curve[-1] if self.equity_curve else self.initial_cash
        total_return = (final_equity - self.initial_cash) / self.initial_cash if self.initial_cash > 0 else 0

        # Count winning/losing trades
        winning = 0
        losing = 0
        for i, trade in enumerate(self.trades):
            if trade.side == "SELL" and i > 0:
                # Find the corresponding buy
                # Simple heuristic: compare sell price to average buy price
                # For a proper implementation, we'd track entry prices
                if trade.price > self.trades[i-1].price:
                    winning += 1
                else:
                    losing += 1

        return BacktestResult(
            strategy_name=self.strategy.name,
            initial_cash=self.initial_cash,
            final_cash=self.cash,
            final_position=self.position,
            final_equity=final_equity,
            total_return=total_return,
            total_trades=len(self.trades),
            winning_trades=winning,
            losing_trades=losing,
            equity_curve=self.equity_curve,
            trades=self.trades,
            max_equity=max(self.equity_curve) if self.equity_curve else self.initial_cash,
            min_equity=min(self.equity_curve) if self.equity_curve else self.initial_cash,
            max_drawdown=max_drawdown,
        )


def run_quick_backtest(
    strategy: BaseStrategy,
    market_data: List[Dict[str, Any]],
    initial_cash: float = 10000.0,
) -> BacktestResult:
    """
    Convenience function to run a backtest in one call.

    Args:
        strategy: Strategy instance to test.
        market_data: List of market state dictionaries.
        initial_cash: Starting cash balance.

    Returns:
        BacktestResult with complete statistics.

    Example:
        from strategies.sniper import SniperStrategy

        data = [
            {"best_ask": 0.45, "best_bid": 0.44},
            {"best_ask": 0.42, "best_bid": 0.41},
            {"best_ask": 0.48, "best_bid": 0.47},
            ...
        ]

        strategy = SniperStrategy(target_price=0.50, min_gap=0.02)
        result = run_quick_backtest(strategy, data, initial_cash=1000)
        print(f"Return: {result.total_return:.2%}")
    """
    engine = BacktestEngine(strategy, initial_cash)
    return engine.run(market_data)
