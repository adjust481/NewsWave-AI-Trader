# strategies/router.py

"""
Strategy Router - AI-Driven Multi-Strategy Switching

Step 3C: Router that delegates decision-making to the AI PM module.

Architecture:
1. Router receives market_state
2. Router calls ai_pm.decide_strategy() to get decision
3. Router maps decision to concrete strategy instance
4. Router executes chosen strategy and annotates orders with AI metadata

The router itself is a BaseStrategy, so it can be used directly with
BacktestEngine without any modifications.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from .base import BaseStrategy, OrderInstruction
from .ou_arb import OUArbStrategy
from .sniper import SniperStrategy
from .ai_pm import decide_strategy, get_risk_parameters


class RoutingMode(Enum):
    """
    Which strategy was selected for the current tick.
    """
    NONE = "none"           # No strategy triggered
    OU_ARB = "ou_arb"       # Arbitrage strategy selected
    SNIPER = "sniper"       # Sniper strategy selected


class StrategyRouter(BaseStrategy):
    """
    AI-Driven Strategy Router.

    A composite strategy that holds multiple child strategies and routes
    market data to the appropriate one based on AI PM decisions.

    The decision logic is decoupled into ai_pm.py, allowing:
    - Easy testing of decision logic in isolation
    - Swapping decision engines without changing the router
    - A/B testing different decision strategies

    Example usage:
        # With default strategies
        router = StrategyRouter()

        # With custom strategies
        ou = OUArbStrategy(min_profit_rate=0.01)
        sniper = SniperStrategy(target_price=0.60, min_gap=0.03)
        router = StrategyRouter(ou_strategy=ou, sniper_strategy=sniper)

        # Use with BacktestEngine
        engine = BacktestEngine(router, initial_cash=10000)
        result = engine.run(market_data)
    """

    def __init__(
        self,
        name: str = "router",
        ou_strategy: Optional[OUArbStrategy] = None,
        sniper_strategy: Optional[SniperStrategy] = None,
        verbose: bool = False,
    ) -> None:
        """
        Initialize the Strategy Router.

        Uses composition: child strategies are injected or created with defaults.

        Args:
            name: Router name for identification.
            ou_strategy: OUArbStrategy instance, or None for default.
            sniper_strategy: SniperStrategy instance, or None for default.
            verbose: If True, print AI PM decisions to console.
        """
        super().__init__(name)

        # Composition: hold child strategies
        self.ou_strategy = ou_strategy or OUArbStrategy(name="ou_arb")
        self.sniper_strategy = sniper_strategy or SniperStrategy(name="sniper")
        self.verbose = verbose

        # Tracking: which strategy was used last (for debugging/logging)
        self.last_routing_mode: RoutingMode = RoutingMode.NONE
        self.last_decision: Optional[Dict[str, Any]] = None
        self.routing_stats: Dict[str, int] = {
            "ou_arb": 0,
            "sniper": 0,
            "none": 0,
        }

    def choose_strategy(self, market_state: Dict[str, Any]) -> Optional[BaseStrategy]:
        """
        Use AI PM to choose which strategy to execute.

        This method delegates to ai_pm.decide_strategy() and maps
        the decision to a concrete strategy instance.

        Args:
            market_state: Dictionary containing market data.

        Returns:
            BaseStrategy instance to use, or None if no action.
        """
        # Call the AI PM to get decision
        decision = decide_strategy(market_state)
        self.last_decision = decision

        if self.verbose:
            print(f"AI PM Says: {decision['reason']} "
                  f"[strategy={decision['chosen_strategy']}, "
                  f"risk={decision['risk_mode']}, "
                  f"confidence={decision['confidence']:.2f}]")

        # Map decision to strategy instance
        chosen = decision.get("chosen_strategy")

        if chosen == "ou_arb":
            return self.ou_strategy
        elif chosen == "sniper":
            return self.sniper_strategy
        else:
            return None

    def on_tick(self, market_state: Dict[str, Any]) -> List[OrderInstruction]:
        """
        Route the market tick to the appropriate strategy.

        Decision Flow:
        1. Call choose_strategy() to get AI PM decision
        2. Check if chosen strategy has a valid opportunity
        3. Execute strategy and annotate orders with AI metadata

        Args:
            market_state: Dictionary containing market data.

        Returns:
            List[OrderInstruction]: Orders from the selected strategy,
                                   or empty list if no opportunity.
        """
        # Get AI PM decision
        chosen_strategy = self.choose_strategy(market_state)

        if chosen_strategy is None:
            self.last_routing_mode = RoutingMode.NONE
            self.routing_stats["none"] += 1
            return []

        # Check if the chosen strategy actually has an opportunity
        has_opportunity = False
        if chosen_strategy == self.ou_strategy:
            has_opportunity = self._check_ou_opportunity(market_state)
            if has_opportunity:
                return self._route_to_ou(market_state)
        elif chosen_strategy == self.sniper_strategy:
            has_opportunity = self._check_sniper_opportunity(market_state)
            if has_opportunity:
                return self._route_to_sniper(market_state)

        # AI chose a strategy but no actual opportunity exists
        self.last_routing_mode = RoutingMode.NONE
        self.routing_stats["none"] += 1
        return []

    def _check_ou_opportunity(self, market_state: Dict[str, Any]) -> bool:
        """
        Check if OUArbStrategy has a valid opportunity.
        """
        pm_ask = market_state.get("pm_ask")
        op_bid = market_state.get("op_bid")

        if pm_ask is None or op_bid is None:
            return False

        if pm_ask <= 0 or op_bid <= 0:
            return False

        return self.ou_strategy.is_opportunity(market_state)

    def _check_sniper_opportunity(self, market_state: Dict[str, Any]) -> bool:
        """
        Check if SniperStrategy has a valid opportunity.
        """
        best_ask = market_state.get("best_ask") or market_state.get("current_ask")

        if best_ask is None or best_ask <= 0:
            return False

        return self.sniper_strategy.is_opportunity(market_state)

    def _route_to_ou(self, market_state: Dict[str, Any]) -> List[OrderInstruction]:
        """
        Route to OUArbStrategy and annotate with AI metadata.
        """
        self.last_routing_mode = RoutingMode.OU_ARB
        self.routing_stats["ou_arb"] += 1

        orders = self.ou_strategy.on_tick(market_state)

        # Annotate orders with router and AI PM metadata
        for order in orders:
            if order.meta is None:
                order.meta = {}
            order.meta["routed_by"] = self.name
            order.meta["routing_mode"] = "ou_arb"
            # Add AI PM decision metadata
            if self.last_decision:
                order.meta["ai_reason"] = self.last_decision.get("reason")
                order.meta["ai_risk_mode"] = self.last_decision.get("risk_mode")
                order.meta["ai_confidence"] = self.last_decision.get("confidence")

        return orders

    def _route_to_sniper(self, market_state: Dict[str, Any]) -> List[OrderInstruction]:
        """
        Route to SniperStrategy and annotate with AI metadata.
        """
        self.last_routing_mode = RoutingMode.SNIPER
        self.routing_stats["sniper"] += 1

        orders = self.sniper_strategy.on_tick(market_state)

        # Annotate orders with router and AI PM metadata
        for order in orders:
            if order.meta is None:
                order.meta = {}
            order.meta["routed_by"] = self.name
            order.meta["routing_mode"] = "sniper"
            # Add AI PM decision metadata
            if self.last_decision:
                order.meta["ai_reason"] = self.last_decision.get("reason")
                order.meta["ai_risk_mode"] = self.last_decision.get("risk_mode")
                order.meta["ai_confidence"] = self.last_decision.get("confidence")

        return orders

    def get_last_decision(self) -> Optional[Dict[str, Any]]:
        """
        Get the last AI PM decision.

        Returns:
            Dict with decision details, or None if no decision made yet.
        """
        return self.last_decision

    def get_routing_stats(self) -> Dict[str, Any]:
        """
        Get routing statistics.

        Returns:
            Dict with counts of how many times each strategy was selected.
        """
        total = sum(self.routing_stats.values())
        return {
            "total_ticks": total,
            "ou_arb_count": self.routing_stats["ou_arb"],
            "sniper_count": self.routing_stats["sniper"],
            "no_action_count": self.routing_stats["none"],
            "ou_arb_pct": (self.routing_stats["ou_arb"] / total * 100) if total > 0 else 0,
            "sniper_pct": (self.routing_stats["sniper"] / total * 100) if total > 0 else 0,
            "no_action_pct": (self.routing_stats["none"] / total * 100) if total > 0 else 0,
        }

    def reset_stats(self) -> None:
        """Reset routing statistics."""
        self.routing_stats = {"ou_arb": 0, "sniper": 0, "none": 0}
        self.last_routing_mode = RoutingMode.NONE
        self.last_decision = None

    def get_child_strategies(self) -> Dict[str, BaseStrategy]:
        """
        Get the child strategies.

        Returns:
            Dict mapping strategy names to instances.
        """
        return {
            "ou_arb": self.ou_strategy,
            "sniper": self.sniper_strategy,
        }
