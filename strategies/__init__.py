# strategies/__init__.py
"""
Trading Strategies Module

This module provides the strategy interface and concrete implementations
for the multi-strategy router architecture.
"""

from .base import BaseStrategy, OrderInstruction
from .ou_arb import OUArbStrategy
from .sniper import SniperStrategy
from .router import StrategyRouter, RoutingMode
from .ai_pm import decide_strategy, get_risk_parameters

__all__ = [
    "BaseStrategy",
    "OrderInstruction",
    "OUArbStrategy",
    "SniperStrategy",
    "StrategyRouter",
    "RoutingMode",
    "decide_strategy",
    "get_risk_parameters",
]
