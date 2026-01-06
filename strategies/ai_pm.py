# strategies/ai_pm.py
"""
AI Portfolio Manager Stub

Step 3C: Decoupled decision logic for the StrategyRouter.
This module acts as the "brain" that decides which strategy to use.

Current Implementation: Deterministic stub that mimics hardcoded rules.
Future: Can be replaced with actual AI/ML model without changing the router.

The key insight is that the Router now asks "What should I do?" to this module,
rather than containing the decision logic itself. This separation allows:
1. Easy testing of decision logic in isolation
2. Swapping in different decision engines (rule-based, ML, LLM, etc.)
3. A/B testing different decision strategies
"""

from typing import Any, Dict


def decide_strategy(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decide which strategy to use based on market state/stats.

    This is a STUB implementation that uses deterministic rules.
    It checks the "mode" field in the input to decide the strategy.

    In the future, this function can be replaced with:
    - ML model inference
    - LLM API call
    - More sophisticated rule engine
    - Ensemble of multiple decision methods

    Args:
        stats: Dictionary containing market state and metadata.
               Expected fields:
               - "mode": str - Hint for which strategy ("arb", "sniper", etc.)
               - Other market data fields as needed

    Returns:
        Dict containing:
        - "chosen_strategy": str - Name of strategy to use ("ou_arb", "sniper")
        - "risk_mode": str - Risk level ("defensive", "aggressive", "normal")
        - "reason": str - Human-readable explanation of the decision
        - "confidence": float - Confidence score (0.0 to 1.0)
    """
    mode = stats.get("mode")

    # Rule 1: Explicit arbitrage mode
    if mode == "arb":
        return {
            "chosen_strategy": "ou_arb",
            "risk_mode": "defensive",
            "reason": "Arbitrage opportunity detected",
            "confidence": 0.95,
        }

    # Rule 2: Explicit sniper mode
    if mode == "sniper":
        return {
            "chosen_strategy": "sniper",
            "risk_mode": "aggressive",
            "reason": "Trend sniper signal",
            "confidence": 0.80,
        }

    # Rule 3: Infer from market data if no explicit mode
    # Check if arbitrage data is present and profitable
    pm_ask = stats.get("pm_ask")
    op_bid = stats.get("op_bid")
    if pm_ask is not None and op_bid is not None:
        if pm_ask > 0 and op_bid > 0:
            spread = op_bid - pm_ask
            if spread > 0.002:  # Min spread threshold
                return {
                    "chosen_strategy": "ou_arb",
                    "risk_mode": "defensive",
                    "reason": f"Arbitrage spread detected: {spread:.4f}",
                    "confidence": min(0.5 + spread * 10, 0.99),
                }

    # Rule 4: Check if sniper data is present
    best_ask = stats.get("best_ask") or stats.get("current_ask")
    if best_ask is not None and best_ask > 0:
        # Sniper is available as fallback
        return {
            "chosen_strategy": "sniper",
            "risk_mode": "normal",
            "reason": "Sniper mode available, no arb opportunity",
            "confidence": 0.60,
        }

    # Default: Safe fallback to arbitrage (conservative)
    return {
        "chosen_strategy": "ou_arb",
        "risk_mode": "normal",
        "reason": "Default safety fallback",
        "confidence": 0.50,
    }


def get_risk_parameters(risk_mode: str) -> Dict[str, Any]:
    """
    Get risk parameters based on risk mode.

    Helper function to translate risk_mode into concrete parameters
    that strategies can use.

    Args:
        risk_mode: One of "defensive", "normal", "aggressive"

    Returns:
        Dict with risk parameters:
        - "position_scale": float - Multiplier for position size
        - "max_exposure": float - Maximum portfolio exposure
        - "stop_loss_pct": float - Stop loss percentage
    """
    risk_configs = {
        "defensive": {
            "position_scale": 0.5,
            "max_exposure": 0.3,
            "stop_loss_pct": 0.02,
        },
        "normal": {
            "position_scale": 1.0,
            "max_exposure": 0.5,
            "stop_loss_pct": 0.05,
        },
        "aggressive": {
            "position_scale": 1.5,
            "max_exposure": 0.8,
            "stop_loss_pct": 0.10,
        },
    }

    return risk_configs.get(risk_mode, risk_configs["normal"])
