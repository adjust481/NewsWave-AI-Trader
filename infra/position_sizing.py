"""
Position Sizing Utilities

Kelly-style position sizing for display purposes in demos.
This module does NOT affect actual order sizing in the router.
"""

from typing import Dict


def calculate_kelly_position(
    total_capital: float,
    ai_confidence: float,
    win_loss_ratio: float = 2.0,
    max_fraction: float = 0.20,
) -> Dict[str, float]:
    """
    Safe Kelly-style position sizing based on AI confidence.

    Args:
        total_capital: Total account capital (e.g. 10_000).
        ai_confidence: Model confidence in [0.0, 1.0], interpreted as win probability p.
        win_loss_ratio: b in Kelly formula, >0. For example:
            - sniper strategies might have higher payoff, b ~ 2.0
            - arbitrage-like trades might be closer to b ~ 1.2
        max_fraction: Hard cap on fraction of capital, default 20%.

    Returns:
        A dict with:
        {
          "fraction_raw": f,        # raw Kelly fraction (unclipped)
          "fraction_half": f_safe,  # half Kelly
          "fraction_applied": f_final,  # final clipped fraction in [0, max_fraction]
          "notional": notional_size  # suggested notional size = total_capital * f_final
        }

    Example:
        >>> kelly = calculate_kelly_position(10000, 0.65, 2.0)
        >>> kelly["notional"]
        750.0
    """
    # Clamp confidence to [0, 1]
    p = max(0.0, min(ai_confidence, 1.0))
    q = 1.0 - p
    b = max(win_loss_ratio, 1e-6)  # Avoid division by zero

    # Standard Kelly: f* = (b*p - q) / b
    f_raw = (b * p - q) / b

    # Half Kelly: more conservative
    f_half = 0.5 * f_raw

    # Final applied fraction: no negative, no more than max_fraction
    f_final = max(0.0, min(f_half, max_fraction))

    notional = total_capital * f_final

    return {
        "fraction_raw": f_raw,
        "fraction_half": f_half,
        "fraction_applied": f_final,
        "notional": notional,
    }
