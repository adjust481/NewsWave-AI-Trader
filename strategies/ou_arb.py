# strategies/ou_arb.py
"""
OU-based Arbitrage Strategy

Migrated from: core.py -> SharedBacktestEngine._execute_opportunity
This strategy exploits price discrepancies between Polymarket (PM) and Opinion (OP)
when OP lags behind PM due to lower liquidity.
"""

from typing import Any, Dict, List
from .base import BaseStrategy, OrderInstruction


class OUArbStrategy(BaseStrategy):
    """
    OU Mean-Reversion Arbitrage Strategy.

    Detects arbitrage opportunities when the spread between Opinion (OP) bid
    and Polymarket (PM) ask exceeds a minimum threshold. Exploits the fact
    that OP tends to lag PM due to lower liquidity.

    Trade direction: Buy PM (at ask) -> Sell OP (at bid)
    Profitable when: op_bid > pm_ask + costs
    """

    def __init__(
        self,
        name: str = "ou_arb",
        min_profit_rate: float = 0.005,
        min_spread_multiplier: float = 0.5,
    ) -> None:
        """
        Initialize the OU Arbitrage Strategy.

        Args:
            name: Strategy name for logging/identification.
            min_profit_rate: Minimum profit rate threshold (default 0.5% = 0.005).
            min_spread_multiplier: Multiplier applied to min_profit_rate for
                                   early filtering (default 0.5 means we require
                                   at least 50% of min_profit_rate to proceed).
        """
        super().__init__(name)
        self.min_profit_rate = min_profit_rate
        self.min_spread_multiplier = min_spread_multiplier

    def on_tick(self, market_state: Dict[str, Any]) -> List[OrderInstruction]:
        """
        Evaluate market state and generate order instructions if arbitrage exists.

        Args:
            market_state: Dictionary containing market data with at least:
                {
                    "pm_ask": float,    # Polymarket best ask price (buy price)
                    "pm_bid": float,    # Polymarket best bid price
                    "op_ask": float,    # Opinion best ask price
                    "op_bid": float,    # Opinion best bid price (sell price)
                    # Optional fields used if available:
                    "pm_liquidity": float,  # Available PM liquidity (USD)
                    "op_liquidity": float,  # Available OP liquidity (USD)
                    "timestamp": Any,       # Current timestamp
                }

        Returns:
            List[OrderInstruction]: Empty list if no opportunity, otherwise
                                    a list containing BUY (PM) and SELL (OP)
                                    instructions.
        """
        # Extract required prices
        pm_ask = market_state.get("pm_ask")
        op_bid = market_state.get("op_bid")

        # Validate required fields
        if pm_ask is None or op_bid is None:
            return []

        if pm_ask <= 0 or op_bid <= 0:
            return []

        # Calculate gross spread: profit margin before fees
        # Positive spread means OP is overpriced relative to PM
        gross_spread = op_bid - pm_ask

        # Early exit: spread too small to be worth considering
        min_threshold = self.min_profit_rate * self.min_spread_multiplier
        if gross_spread < min_threshold:
            return []

        # Arbitrage opportunity detected!
        # Direction: Buy PM (cheap) -> Sell OP (expensive)

        # Calculate suggested size based on available liquidity
        pm_liquidity = market_state.get("pm_liquidity", 0)
        op_liquidity = market_state.get("op_liquidity", 0)
        max_size = min(pm_liquidity, op_liquidity) if pm_liquidity > 0 and op_liquidity > 0 else 100.0

        # Build order instructions
        instructions = [
            OrderInstruction(
                side="BUY",
                size=max_size,
                price=pm_ask,
                meta={
                    "platform": "polymarket",
                    "reason": "arb_buy_cheap",
                    "gross_spread": gross_spread,
                    "spread_pct": gross_spread / pm_ask if pm_ask > 0 else 0,
                }
            ),
            OrderInstruction(
                side="SELL",
                size=max_size,
                price=op_bid,
                meta={
                    "platform": "opinion",
                    "reason": "arb_sell_expensive",
                    "gross_spread": gross_spread,
                    "spread_pct": gross_spread / pm_ask if pm_ask > 0 else 0,
                }
            ),
        ]

        return instructions

    def compute_spread(self, pm_ask: float, op_bid: float) -> float:
        """
        Compute the gross spread between platforms.

        Args:
            pm_ask: Polymarket ask price.
            op_bid: Opinion bid price.

        Returns:
            float: Gross spread (op_bid - pm_ask). Positive = opportunity.
        """
        return op_bid - pm_ask

    def is_opportunity(self, market_state: Dict[str, Any]) -> bool:
        """
        Quick check if there's a potential arbitrage opportunity.

        Args:
            market_state: Market state dictionary.

        Returns:
            bool: True if spread exceeds minimum threshold.
        """
        pm_ask = market_state.get("pm_ask", 0)
        op_bid = market_state.get("op_bid", 0)

        if pm_ask <= 0 or op_bid <= 0:
            return False

        gross_spread = op_bid - pm_ask
        return gross_spread >= (self.min_profit_rate * self.min_spread_multiplier)
