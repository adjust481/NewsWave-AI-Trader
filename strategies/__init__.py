# strategies/__init__.py
"""
Trading Strategies Module

This module provides the strategy interface and concrete implementations
for the multi-strategy router architecture.
"""

from .base import BaseStrategy, OrderInstruction
from .ou_arb import OUArbStrategy
from .sniper import SniperStrategy

__all__ = [
    "BaseStrategy",
    "OrderInstruction",
    "OUArbStrategy",
    "SniperStrategy",
]
