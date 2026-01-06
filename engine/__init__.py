# engine/__init__.py
"""
Backtesting Engine Module

Provides the core simulation and backtesting infrastructure.
"""

from .backtest import BacktestEngine, BacktestResult, Trade, run_quick_backtest

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "Trade",
    "run_quick_backtest",
]
