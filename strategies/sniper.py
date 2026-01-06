# strategies/sniper.py
"""
Sniper Strategy - Directional Taker Logic

Migrated from: paper.py -> SniperTradingEngine.calculate_opportunity
This strategy buys when the market price drops below a target "fair value".

Core Logic (Taker perspective):
- I believe the asset is worth `target_price`
- When market ask < target_price - min_gap, I buy
- The bigger the discount, the more confident the opportunity
"""

from typing import Any, Dict, List, Optional
from .base import BaseStrategy, OrderInstruction


class SniperStrategy(BaseStrategy):
    """
    Directional Sniper Strategy.

    A taker strategy that buys when the market price drops significantly
    below a user-defined target price (fair value belief).

    Trade direction: BUY when price is low, SELL when price exceeds target
    Buy triggers when: best_ask < target_price - min_gap
    Sell triggers when: best_bid > target_price (take profit)

    Example:
        - Target price: $0.50 (I believe this asset is worth 50 cents)
        - Min gap: 0.02 ($0.02 absolute)
        - Buy trigger: when ask < $0.48
        - Sell trigger: when bid > $0.50
    """

    def __init__(
        self,
        name: str = "sniper",
        target_price: float = 0.50,
        min_gap: float = 0.02,
        position_size: float = 50.0,
    ) -> None:
        """
        Initialize the Sniper Strategy.

        Args:
            name: Strategy name for logging/identification.
            target_price: Your belief of the asset's fair value (0-1 for prediction markets).
            min_gap: Minimum discount required to trigger a buy (absolute, not %).
            position_size: Default trade size in USD.
        """
        super().__init__(name)
        self.target_price = target_price
        self.min_gap = min_gap
        self.position_size = position_size

    def on_tick(self, market_state: Dict[str, Any]) -> List[OrderInstruction]:
        """
        Evaluate market state and generate order instructions if opportunity exists.

        Args:
            market_state: Dictionary containing market data with at least:
                {
                    "best_ask": float,          # Current best ask (buy price)
                    "best_bid": float,          # Current best bid (sell price)
                    # Optional fields:
                    "gas_cost_usd": float,      # Estimated gas cost in USD
                    "position_size": float,     # Override default position size
                    "current_balance": float,   # Available balance
                    "timestamp": Any,           # Current timestamp
                }

        Returns:
            List[OrderInstruction]: Empty list if no opportunity, otherwise
                                    a BUY or SELL instruction.
        """
        # Extract prices - support both naming conventions
        best_ask = market_state.get("best_ask") or market_state.get("current_ask")
        best_bid = market_state.get("best_bid") or market_state.get("current_bid")

        # Validate required fields
        if best_ask is None or best_ask <= 0:
            return []

        gas_cost_usd = market_state.get("gas_cost_usd", 0.0)
        size = market_state.get("position_size", self.position_size)

        # --- Check for SELL opportunity (take profit) ---
        # Only trigger take-profit if we have a position (indicated by has_position flag)
        has_position = market_state.get("has_position", False)
        if has_position and best_bid is not None and best_bid > self.target_price:
            shares = size / best_bid if best_bid > 0 else 0
            return [
                OrderInstruction(
                    side="SELL",
                    size=shares,
                    price=best_bid,
                    meta={
                        "strategy": "sniper",
                        "reason": "take_profit",
                        "target_price": self.target_price,
                        "price_gap": best_bid - self.target_price,
                    }
                )
            ]

        # --- Check for BUY opportunity (entry) ---
        # Calculate price gap: how much below target the ask is
        price_gap = self.target_price - best_ask

        # Must be at least min_gap below target to trigger
        if price_gap < self.min_gap:
            return []

        # Calculate expected profit
        shares = size / best_ask
        expected_value = shares * self.target_price
        total_cost = size + gas_cost_usd
        expected_profit = expected_value - total_cost

        # Only buy if profitable after costs
        if expected_profit <= 0:
            return []

        # Build BUY instruction
        return [
            OrderInstruction(
                side="BUY",
                size=shares,
                price=best_ask,
                meta={
                    "strategy": "sniper",
                    "reason": "sniper_entry",
                    "target_price": self.target_price,
                    "price_gap": price_gap,
                    "price_gap_pct": (price_gap / self.target_price * 100) if self.target_price > 0 else 0,
                    "expected_profit": expected_profit,
                }
            )
        ]

    def calculate_opportunity(
        self,
        current_ask: float,
        gas_cost_usd: float = 0.0,
        position_size: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculate sniper opportunity metrics.

        Args:
            current_ask: Current market ask price (what you'd pay to buy)
            gas_cost_usd: Estimated gas cost in USD
            position_size: Trade size in USD (uses default if None)

        Returns:
            Dict with opportunity analysis.
        """
        size = position_size if position_size is not None else self.position_size

        # Price gap calculation (positive = underpriced = opportunity)
        price_gap = self.target_price - current_ask

        # Calculate shares acquired at current price
        shares_acquired = size / current_ask if current_ask > 0 else 0

        # Expected value if price reaches target
        expected_value = shares_acquired * self.target_price

        # Total cost including gas
        total_cost = size + gas_cost_usd

        # Expected profit
        expected_profit = expected_value - total_cost

        # Opportunity conditions
        has_opportunity = (
            price_gap >= self.min_gap and
            expected_profit > 0 and
            current_ask > 0
        )

        return {
            "has_opportunity": has_opportunity,
            "current_ask": current_ask,
            "target_price": self.target_price,
            "price_gap": price_gap,
            "price_gap_pct": (price_gap / self.target_price * 100) if self.target_price > 0 else 0,
            "shares_acquired": shares_acquired,
            "expected_value": expected_value,
            "total_cost": total_cost,
            "gas_cost": gas_cost_usd,
            "expected_profit": expected_profit,
        }

    def is_opportunity(self, market_state: Dict[str, Any]) -> bool:
        """
        Quick check if there's a sniper opportunity.

        Args:
            market_state: Market state dictionary with at least "best_ask".

        Returns:
            bool: True if price is sufficiently below target.
        """
        current_ask = market_state.get("best_ask") or market_state.get("current_ask", 0)
        gas_cost = market_state.get("gas_cost_usd", 0)

        if current_ask <= 0:
            return False

        opportunity = self.calculate_opportunity(current_ask, gas_cost)
        return opportunity["has_opportunity"]

    def get_trigger_price(self) -> float:
        """
        Get the price at which the sniper would trigger a buy.

        Returns:
            float: Maximum ask price that would trigger a buy
        """
        return self.target_price - self.min_gap

    def update_target(self, new_target: float) -> None:
        """
        Update the target price.

        Args:
            new_target: New target price (0-1 for prediction markets)
        """
        self.target_price = new_target
