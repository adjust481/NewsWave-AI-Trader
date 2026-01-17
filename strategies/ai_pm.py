# strategies/ai_pm.py
"""
AI Portfolio Manager with Rule-Based and LLM Decision Engines

This module acts as the "brain" that decides which strategy to use.
It supports two decision modes:

1. Rule-Based (default): Uses regime detection with short-term memory
   - Tracks recent ticks to identify market regimes
   - Arbitrage regime: frequent large spreads between PM and OP
   - Sniper regime: frequent deep discounts in price

2. LLM-Based (optional): Uses Gemini API to make decisions
   - Builds a structured prompt from market state
   - Parses JSON response for strategy selection
   - Falls back to rule-based on any error

The public interface remains unchanged:
    decide_strategy(stats, use_llm=None) -> Dict[str, Any]

Stats dictionary structure:
    {
        "mode": "arb" | "sniper" | None,      # Hint for which strategy
        "pm_ask": float,                       # Polymarket ask price
        "op_bid": float,                       # Opinion bid price
        "spread": float,                       # Computed spread (optional)
        "best_ask": float,                     # Best ask price for sniper
        "recent_regime_summary": {...},        # Summary of recent regime (optional)
        "historical_pattern": {                # Optional - historical news pattern data
            "pattern_name": str,               # e.g. "广告景气利好"
            "avg_return_1d": float,            # Average 1-day return
            "avg_return_3d": float,            # Average 3-day return
            "avg_return_7d": float,            # Average 7-day return
            "confidence_level": "low" | "medium" | "high",
            "typical_horizon": str,            # e.g. "3d"
        },
    }

Environment variables:
    AI_PM_USE_LLM: Set to "1" to enable LLM mode by default
    GEMINI_API_KEY: Required for actual LLM calls
"""

import json
import os
from collections import deque
from typing import Any, Dict, Optional

# Try to import the new Gemini SDK (optional dependency)
try:
    import google.genai as genai
except ImportError:
    genai = None


# =============================================================================
# Configuration
# =============================================================================

# Environment variable to control LLM usage
USE_LLM_DEFAULT = os.getenv("AI_PM_USE_LLM", "0") == "1"

# Gemini API key (optional - only needed for real LLM calls)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini model name (can be overridden via env var)
# Default: gemini-2.0-flash-exp (latest fast model as of Jan 2025)
# Alternatives: gemini-1.5-flash, gemini-1.5-pro
GEMINI_MODEL = "gemini-1.5-flash"

# Regime detection thresholds
HORIZON = 5              # Rolling window size
LARGE_SPREAD = 0.10      # Threshold for arb signal
DEEP_DISCOUNT = 0.42     # Threshold for sniper signal

# Valid values for normalization
VALID_STRATEGIES = {"ou_arb", "sniper"}
VALID_RISK_MODES = {"defensive", "normal", "aggressive"}


# =============================================================================
# Gemini Client Wrapper
# =============================================================================

def get_gemini_client():
    """
    Get a Gemini client instance.

    Raises:
        RuntimeError: If GEMINI_API_KEY not set or SDK not installed
    """
    if genai is None:
        raise RuntimeError("google.genai SDK not installed. pip install -U google-genai")

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    return genai.Client(api_key=GEMINI_API_KEY)


# =============================================================================
# AI Portfolio Manager Class (Rule-Based Engine)
# =============================================================================

class AIPortfolioManager:
    """
    Rule-based AI Portfolio Manager with regime detection.

    Maintains a rolling window of recent market observations to detect
    whether we're in an "arbitrage-dominated" or "sniper-dominated" regime.
    """

    def __init__(self, horizon: int = HORIZON) -> None:
        """
        Initialize the AI PM.

        Args:
            horizon: Number of recent ticks to consider for regime detection.
        """
        self.horizon = horizon
        self._history: deque = deque(maxlen=horizon)

    def reset_state(self) -> None:
        """Reset the internal state (history buffer)."""
        self._history.clear()

    def _extract_features(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant features from market state for regime detection."""
        pm_ask = stats.get("pm_ask", 0) or 0
        op_bid = stats.get("op_bid", 0) or 0
        best_ask = stats.get("best_ask") or stats.get("current_ask") or 0
        mode = stats.get("mode")

        spread = (op_bid - pm_ask) if (pm_ask > 0 and op_bid > 0) else 0

        is_arb_signal = (spread > LARGE_SPREAD) or (mode == "arb")
        is_sniper_signal = (0 < best_ask < DEEP_DISCOUNT) or (mode == "sniper")

        return {
            "spread": spread,
            "best_ask": best_ask,
            "mode": mode,
            "is_arb_signal": is_arb_signal,
            "is_sniper_signal": is_sniper_signal,
        }

    def _update_history(self, features: Dict[str, Any]) -> None:
        """Add current tick's features to the history buffer."""
        self._history.append(features)

    def _compute_regime_counts(self) -> tuple:
        """Count arb and sniper signals in recent history."""
        arb_count = sum(1 for f in self._history if f.get("is_arb_signal"))
        sniper_count = sum(1 for f in self._history if f.get("is_sniper_signal"))
        return arb_count, sniper_count

    def get_regime_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current regime for LLM context.

        Returns:
            Dict with arb_count, sniper_count, history_len, dominant_regime
        """
        arb_count, sniper_count = self._compute_regime_counts()
        history_len = len(self._history)

        if arb_count > sniper_count:
            dominant = "arb"
        elif sniper_count > arb_count:
            dominant = "sniper"
        else:
            dominant = "neutral"

        return {
            "arb_count": arb_count,
            "sniper_count": sniper_count,
            "history_len": history_len,
            "dominant_regime": dominant,
        }

    def decide(self, stats: Dict[str, Any], fallback_note: Optional[str] = None) -> Dict[str, Any]:
        """
        Decide which strategy to use based on market state and recent regime.

        Args:
            stats: Dictionary containing market state and metadata.
            fallback_note: Optional note to append to reason (e.g., LLM fallback info).

        Returns:
            Dict with chosen_strategy, risk_mode, reason, confidence
        """
        features = self._extract_features(stats)
        self._update_history(features)

        arb_count, sniper_count = self._compute_regime_counts()
        history_len = len(self._history)

        result: Dict[str, Any]

        # Case 1: Arb regime dominates
        if arb_count > sniper_count:
            confidence = min(0.60 + (arb_count / history_len) * 0.35, 0.95)
            result = {
                "chosen_strategy": "ou_arb",
                "risk_mode": "defensive",
                "reason": f"Arb regime detected ({arb_count}/{history_len} recent ticks)",
                "confidence": confidence,
            }

        # Case 2: Sniper regime dominates
        elif sniper_count > arb_count:
            confidence = min(0.60 + (sniper_count / history_len) * 0.30, 0.90)
            result = {
                "chosen_strategy": "sniper",
                "risk_mode": "aggressive",
                "reason": f"Sniper regime detected ({sniper_count}/{history_len} recent ticks)",
                "confidence": confidence,
            }

        # Case 3: Tie or no clear regime - use current tick signals
        else:
            mode = stats.get("mode")

            if mode == "arb":
                result = {
                    "chosen_strategy": "ou_arb",
                    "risk_mode": "defensive",
                    "reason": "Arbitrage opportunity detected",
                    "confidence": 0.95,
                }
            elif mode == "sniper":
                result = {
                    "chosen_strategy": "sniper",
                    "risk_mode": "aggressive",
                    "reason": "Trend sniper signal",
                    "confidence": 0.80,
                }
            elif features["spread"] > 0.002:
                spread = features["spread"]
                result = {
                    "chosen_strategy": "ou_arb",
                    "risk_mode": "defensive",
                    "reason": f"Arbitrage spread detected: {spread:.4f}",
                    "confidence": min(0.5 + spread * 10, 0.99),
                }
            elif features["best_ask"] > 0:
                result = {
                    "chosen_strategy": "sniper",
                    "risk_mode": "normal",
                    "reason": "Sniper mode available, no arb opportunity",
                    "confidence": 0.60,
                }
            else:
                result = {
                    "chosen_strategy": "ou_arb",
                    "risk_mode": "normal",
                    "reason": "Default safety fallback",
                    "confidence": 0.50,
                }

        # Append fallback note if provided
        if fallback_note:
            result["reason"] = f"{result['reason']} ({fallback_note})"

        return result


# =============================================================================
# Module-level singleton instance
# =============================================================================

_ai_pm_instance: Optional[AIPortfolioManager] = None


def _get_ai_pm() -> AIPortfolioManager:
    """Get or create the singleton AI PM instance."""
    global _ai_pm_instance
    if _ai_pm_instance is None:
        _ai_pm_instance = AIPortfolioManager()
    return _ai_pm_instance


# =============================================================================
# LLM-Based Decision Engine
# =============================================================================

def decide_strategy_llm(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use Gemini (LLM) to decide between 'ou_arb' and 'sniper'.

    Args:
        stats: Dictionary containing market state.

    Returns:
        Dict with chosen_strategy, risk_mode, reason, confidence

    Raises:
        RuntimeError: If GEMINI_API_KEY not set or google.genai not installed
        Exception: If LLM call fails or response is invalid
    """
    client = get_gemini_client()

    # Extract current tick data
    pm_ask = stats.get("pm_ask", 0) or 0
    op_bid = stats.get("op_bid", 0) or 0
    best_ask = stats.get("best_ask") or stats.get("current_ask") or 0
    mode = stats.get("mode")
    spread = (op_bid - pm_ask) if (pm_ask > 0 and op_bid > 0) else 0

    # Get regime summary from the rule-based engine
    regime_summary = _get_ai_pm().get_regime_summary()

    # Extract historical pattern if present
    historical_pattern = stats.get("historical_pattern")

    # Build the context for the LLM
    payload = {
        "current_tick": {
            "mode": mode,
            "pm_ask": pm_ask,
            "op_bid": op_bid,
            "best_ask": best_ask,
            "spread": round(spread, 4),
        },
        "recent_regime": {
            "arb_signals": regime_summary["arb_count"],
            "sniper_signals": regime_summary["sniper_count"],
            "window_size": regime_summary["history_len"],
            "dominant": regime_summary["dominant_regime"],
        },
        "historical_pattern": historical_pattern,
    }

    # Build the prompt
    prompt = f"""You are an AI portfolio manager choosing between two strategies:

* "ou_arb": cross-market arbitrage
* "sniper": directional sniper on discounted prices

You will receive:

* current_tick: 当前盘面的价差、买卖盘情况
* recent_regime: 最近 N 个 tick 的 regime 统计（ranging/trending）
* historical_pattern: 过去同类新闻事件的平均涨跌情况和典型周期

请根据这些信息，输出一个 JSON：

{{
  "chosen_strategy": "ou_arb" or "sniper",
  "risk_mode": "defensive" or "normal" or "aggressive",
  "reason": "用简短中文解释你的判断逻辑"
}}

只输出 JSON，不要多余文字。

输入 JSON 如下：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""

    # Call Gemini API with new SDK
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        # Extract text from response - handle different response structures
        if hasattr(response, 'text'):
            text = response.text
        elif hasattr(response, 'candidates') and response.candidates:
            text = response.candidates[0].content.parts[0].text
        else:
            raise RuntimeError("Unexpected Gemini response structure")

        text = text.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(json_lines).strip()

        data = json.loads(text)

    except Exception as e:
        # Wrap any error for consistent handling
        raise RuntimeError(f"LLM error ({type(e).__name__}): {str(e)[:100]}")

    # Validate and normalize
    chosen = data.get("chosen_strategy", "ou_arb")
    if chosen not in VALID_STRATEGIES:
        chosen = "ou_arb"

    risk_mode = data.get("risk_mode", "normal")
    if risk_mode not in VALID_RISK_MODES:
        risk_mode = "normal"

    reason = data.get("reason", "LLM decided without explicit reason.")

    return {
        "chosen_strategy": chosen,
        "risk_mode": risk_mode,
        "reason": f"[LLM] {reason}",
        "confidence": data.get("confidence", 0.95),
    }


def _parse_llm_response(response_text: str) -> Dict[str, Any]:
    """
    Parse and validate the LLM response.

    Args:
        response_text: Raw text response from LLM.

    Returns:
        Validated dict with chosen_strategy, risk_mode, reason, confidence

    Raises:
        ValueError: If response cannot be parsed or validated.
    """
    # Try to extract JSON from response (handle markdown code blocks)
    text = response_text.strip()
    if text.startswith("```"):
        # Extract content between code blocks
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    # Parse JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response: {e}")

    # Validate and normalize chosen_strategy
    chosen_strategy = data.get("chosen_strategy", "").lower()
    if chosen_strategy not in VALID_STRATEGIES:
        chosen_strategy = "ou_arb"  # Default

    # Validate and normalize risk_mode
    risk_mode = data.get("risk_mode", "").lower()
    if risk_mode not in VALID_RISK_MODES:
        risk_mode = "normal"  # Default

    # Get reason
    reason = data.get("reason", "")
    if not reason or not isinstance(reason, str):
        reason = "LLM decision"

    # Prefix reason with [LLM] to distinguish from rule-based
    reason = f"[LLM] {reason}"

    # LLM doesn't return confidence, so we set a reasonable default
    confidence = data.get("confidence", 0.75)

    return {
        "chosen_strategy": chosen_strategy,
        "risk_mode": risk_mode,
        "reason": reason,
        "confidence": confidence,
    }


# =============================================================================
# Rule-Based Decision Engine (Public Wrapper)
# =============================================================================

def decide_strategy_rule_based(
    stats: Dict[str, Any],
    fallback_note: Optional[str] = None
) -> Dict[str, Any]:
    """
    Make a decision using the rule-based engine.

    This is the pure rule-based path that uses regime detection
    with short-term memory, optionally adjusted by historical news patterns.

    Args:
        stats: Dictionary containing market state.
        fallback_note: Optional note to append to reason (e.g., LLM error info).

    Returns:
        Dict with chosen_strategy, risk_mode, reason, confidence
    """
    # Get base decision from regime detection
    result = _get_ai_pm().decide(stats, fallback_note=fallback_note)

    # Extract historical pattern if present
    hp = stats.get("historical_pattern") or {}
    avg_3d = hp.get("avg_return_3d")
    conf_level = hp.get("confidence_level")  # "low" | "medium" | "high" | None
    pattern_name = hp.get("pattern_name")

    # Apply adjustment based on historical pattern
    # Only adjust if we have avg_3d data and confidence is medium or high
    if avg_3d is not None and conf_level in {"medium", "high"}:
        mode = stats.get("mode")

        if avg_3d > 0.10:
            # Strong positive pattern → lean towards sniper and aggression
            # Only override strategy if mode was not explicitly set
            if result["chosen_strategy"] == "ou_arb" and mode is None:
                result["chosen_strategy"] = "sniper"
            result["risk_mode"] = "aggressive"
        elif avg_3d < -0.05:
            # Strong negative pattern → be defensive
            result["risk_mode"] = "defensive"

    # Append historical pattern info to reason if available
    if avg_3d is not None and pattern_name:
        result["reason"] = (
            f"{result['reason']} | hist_pattern={pattern_name} "
            f"avg_3d={avg_3d:.1%} conf={conf_level}"
        )

    return result


# =============================================================================
# Public API
# =============================================================================

def decide_strategy(
    stats: Dict[str, Any],
    use_llm: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Decide which strategy to use based on market state/stats.

    This is the main entry point for the AI PM. It supports two modes:
    - Rule-based (default): Uses regime detection with memory
    - LLM-based (optional): Uses Gemini API for decisions

    Args:
        stats: Dictionary containing market state and metadata.
        use_llm: Override for LLM usage.
               - None: Use environment variable AI_PM_USE_LLM (default)
               - True: Force LLM mode (with fallback on error)
               - False: Force rule-based mode

    Returns:
        Dict containing:
        - "chosen_strategy": str - "ou_arb" or "sniper"
        - "risk_mode": str - "defensive", "normal", or "aggressive"
        - "reason": str - Human-readable explanation
        - "confidence": float - Confidence score (0.0 to 1.0)
    """
    # Determine whether to use LLM
    if use_llm is None:
        use_llm = USE_LLM_DEFAULT

    # Rule-based path (fast path)
    if not use_llm:
        return decide_strategy_rule_based(stats)

    # Check if API key is available before attempting LLM call
    if not GEMINI_API_KEY:
        # Don't add fallback note for missing key - just use rule-based silently
        return decide_strategy_rule_based(stats)

    # LLM path with fallback
    try:
        return decide_strategy_llm(stats)
    except Exception as e:
        # Keep error message concise and user-friendly
        error_msg = str(e)[:60]

        # Map common errors to user-friendly messages
        if "404" in error_msg or "NOT_FOUND" in error_msg:
            fallback_note = "LLM unavailable in this environment"
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
            fallback_note = "LLM quota limit (using rule-based)"
        else:
            fallback_note = "LLM unavailable in this environment"

        return decide_strategy_rule_based(stats, fallback_note=fallback_note)


def reset_state() -> None:
    """
    Reset the AI PM's internal state (history buffer).

    Call this between test runs or when starting a new backtest
    to ensure the AI PM starts fresh without memory of previous ticks.
    """
    _get_ai_pm().reset_state()


def get_risk_parameters(risk_mode: str) -> Dict[str, Any]:
    """
    Get risk parameters based on risk mode.

    Args:
        risk_mode: One of "defensive", "normal", "aggressive"

    Returns:
        Dict with position_scale, max_exposure, stop_loss_pct
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
