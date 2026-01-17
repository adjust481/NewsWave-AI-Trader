"""
Streamlit App: News-Driven AI Portfolio Manager

A web interface for the multi-strategy AI PM with news-driven historical patterns.
Supports both rule-based and optional LLM modes with automatic fallback.

Usage:
    # Rule-based mode (recommended for demo)
    streamlit run app.py

    # LLM mode (optional, requires API key)
    export AI_PM_USE_LLM=1
    export GEMINI_API_KEY="your_key"
    streamlit run app.py
"""

import os
from typing import Any, Dict, List

import streamlit as st

from news_replay import (
    NewsCase,
    load_news_cases,
    filter_cases,
    summarize_cases,
    analyze_pattern_with_llm,
    get_symbol_stats,
)
from strategies.ai_pm import decide_strategy, reset_state
from strategies.router import StrategyRouter
from infra.position_sizing import calculate_kelly_position


# =============================================================================
# Helper Functions
# =============================================================================

@st.cache_data
def _load_cases() -> List[NewsCase]:
    """Load news cases with caching."""
    return load_news_cases()


def format_pct(value: float) -> str:
    """Format a decimal return as a percentage string with sign."""
    if value is None:
        return "N/A"
    pct = value * 100
    return f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"


def build_demo_market_state(latest_case: NewsCase, hist_pattern: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a demo market state based on the latest case and historical pattern.

    This mimics the logic from demo_news_driven.py to create realistic market conditions
    based on the pattern's expected returns.
    """
    avg_3d = hist_pattern.get("avg_return_3d", 0) or 0
    confidence = hist_pattern.get("confidence_level", "low")

    # Determine market state based on pattern strength
    if avg_3d > 0.10 and confidence in {"medium", "high"}:
        pm_ask, op_bid, best_ask, mode = 0.45, 0.60, 0.40, "arb"
    elif avg_3d > 0.05:
        pm_ask, op_bid, best_ask, mode = 0.48, 0.55, 0.46, "arb"
    elif avg_3d < -0.05:
        pm_ask, op_bid, best_ask, mode = 0.50, 0.51, 0.52, None
    else:
        pm_ask, op_bid, best_ask, mode = 0.50, 0.51, 0.38, "sniper"

    spread = op_bid - pm_ask

    return {
        "mode": mode,
        "pm_ask": pm_ask,
        "pm_bid": pm_ask - 0.01,
        "op_ask": op_bid + 0.02,
        "op_bid": op_bid,
        "spread": spread,
        "best_ask": best_ask,
        "best_bid": best_ask - 0.01,
        "symbol": latest_case.symbol,
        "event_date": latest_case.event_date,
        "news_headline": latest_case.news_headline,
        "news_summary": latest_case.news_summary,
        "historical_pattern": hist_pattern,
        "gas_cost_usd": 0.0,
    }


def build_custom_market_state(
    selected_symbol: str,
    pattern: Dict[str, Any],
    custom_headline: str,
    custom_summary: str,
    reference_case: NewsCase,
) -> Dict[str, Any]:
    """Build a synthetic market state for custom news scenarios."""
    avg_3d = pattern.get("avg_return_3d", 0) or 0
    confidence = pattern.get("confidence_level", "low")

    # Determine market state based on pattern strength
    if avg_3d > 0.10 and confidence in {"medium", "high"}:
        pm_ask, op_bid, best_ask, mode = 0.45, 0.60, 0.40, "arb"
    elif avg_3d > 0.05:
        pm_ask, op_bid, best_ask, mode = 0.48, 0.55, 0.46, "arb"
    elif avg_3d < -0.05:
        pm_ask, op_bid, best_ask, mode = 0.50, 0.51, 0.52, None
    else:
        pm_ask, op_bid, best_ask, mode = 0.50, 0.51, 0.38, "sniper"

    spread = op_bid - pm_ask

    return {
        "mode": mode,
        "pm_ask": pm_ask,
        "pm_bid": pm_ask - 0.01,
        "op_ask": op_bid + 0.02,
        "op_bid": op_bid,
        "spread": spread,
        "best_ask": best_ask,
        "best_bid": best_ask - 0.01,
        "symbol": selected_symbol,
        "event_date": reference_case.event_date,
        "news_headline": custom_headline or f"Custom scenario for {selected_symbol}",
        "news_summary": custom_summary or reference_case.news_summary,
        "historical_pattern": pattern,
        "gas_cost_usd": 0.0,
    }


# =============================================================================
# Main App
# =============================================================================

def main():
    st.set_page_config(
        page_title="News-Driven AI PM",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ========== Top: Title + Intro ==========
    st.title("🧠 News-Driven AI Portfolio Manager")
    st.markdown(
        "An AI portfolio manager that reads news, learns from historical price reactions, "
        "and routes capital across arbitrage and sniper strategies."
    )

    # ========== Load Data ==========
    cases = _load_cases()
    if not cases:
        st.error("❌ No news cases loaded. Please check data/news_cases.csv.")
        return

    symbols = sorted({c.symbol for c in cases})
    symbol_stats = get_symbol_stats(cases)

    # ========== Sidebar: LLM Status ==========
    st.sidebar.header("⚙️ System Status")

    # LLM Status
    use_llm = os.environ.get("AI_PM_USE_LLM", "0") == "1"
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    st.sidebar.info(f"""
**LLM Mode:** {"ON" if use_llm else "OFF"}
**API Key:** {"[set]" if has_key else "[not set]"}

*LLM mode is controlled via environment variables.*
    """)

    # ========== Top Opportunities Radar ==========
    st.markdown("### 📡 Top Opportunities Radar")

    col_left, col_right = st.columns(2)

    MIN_SAMPLES = 2  # Filter out single-sample noise

    # Left column: Top symbols by avg_return_3d
    with col_left:
        st.markdown("**📈 Top avg 3D return**")

        # Filter and sort
        candidates = [s for s in symbol_stats if s["count"] >= MIN_SAMPLES]
        if candidates:
            top_by_avg = sorted(
                candidates,
                key=lambda x: x["avg_return_3d"],
                reverse=True,
            )[:3]

            for row in top_by_avg:
                arrow = "🟢" if row["avg_return_3d"] > 0 else "🔴"
                st.markdown(
                    f"- {arrow} `{row['symbol']}` · "
                    f"avg 3D: **{row['avg_return_3d']:.1%}** · "
                    f"n={int(row['count'])}"
                )
        else:
            st.caption("No symbols with enough samples yet.")

    # Right column: Top symbols by sample count
    with col_right:
        st.markdown("**📊 Most frequent symbols**")

        if symbol_stats:
            top_by_count = sorted(
                symbol_stats,
                key=lambda x: x["count"],
                reverse=True,
            )[:3]

            for row in top_by_count:
                st.markdown(
                    f"- `{row['symbol']}` · samples: **{int(row['count'])}** · "
                    f"avg 3D: {row['avg_return_3d']:.1%}"
                )
        else:
            st.caption("No historical cases loaded.")

    st.caption(
        "This radar summarizes which symbols have the strongest average 3D moves "
        "and which have the most historical samples in the dataset."
    )

    # ========== Tabs ==========
    tab_replay, tab_custom = st.tabs(["📜 Historical Replay", "🧪 Custom News Lab"])

    # ========== TAB 1: Historical Replay ==========
    with tab_replay:
        st.markdown("---")

        # Symbol Selection
        default_idx = symbols.index("BLUE") if "BLUE" in symbols else 0
        symbol = st.selectbox("Symbol", symbols, index=default_idx, key="replay_symbol")

        # Filter cases for selected symbol
        symbol_cases = filter_cases(cases, symbol=symbol)
        if not symbol_cases:
            st.error(f"No cases found for {symbol}")
            return

        # Event Selection
        def _format_case_option(c):
            # Assuming NewsCase has case_id field; if not, use index
            cid = getattr(c, "case_id", "?")
            title = c.news_headline[:40] + "..." if len(c.news_headline) > 40 else c.news_headline
            return f"{cid} · {c.event_date} · {title}"

        case_options = [_format_case_option(c) for c in symbol_cases]
        selected_idx = st.selectbox(
            "Historical event",
            list(range(len(symbol_cases))),
            format_func=lambda i: case_options[i],
            index=len(symbol_cases) - 1,  # Default to latest
            key="replay_event",
        )
        selected_case = symbol_cases[selected_idx]

        # ========== Main Area: News Card + Stats ==========
        st.markdown("---")

        col_news, col_stats = st.columns([1.2, 1.0])

        # Left: News Event Card
        with col_news:
            st.subheader("📰 News Event")

            st.markdown(f"**Symbol:** `{selected_case.symbol}`")
            st.markdown(f"**Event date:** {selected_case.event_date}")
            st.markdown(
                f"**Regime:** `{selected_case.regime}` · "
                f"**Tag:** `{selected_case.source_tag}`"
            )

            st.markdown("---")

            st.markdown(f"**Headline**  \n{selected_case.news_headline}")
            st.markdown(f"**Summary**  \n{selected_case.news_summary}")

            # Show returns inline
            st.markdown(
                f"**Returns:** 1D: {format_pct(selected_case.return_1d)} · "
                f"3D: {format_pct(selected_case.return_3d)} · "
                f"7D: {format_pct(selected_case.return_7d)}"
            )

        # Right: Historical Performance & Pattern
        with col_stats:
            st.subheader("📊 Historical Performance")

            summary = summarize_cases(symbol_cases)

            st.markdown(f"- Sample count: **{summary['count']}**")
            st.markdown(
                f"- Avg 1D return: **{format_pct(summary['avg_return_1d'])}** "
                f"(positive ratio: {summary['pos_ratio_1d']:.0%})"
            )
            st.markdown(
                f"- Avg 3D return: **{format_pct(summary['avg_return_3d'])}** "
                f"(positive ratio: {summary['pos_ratio_3d']:.0%})"
            )
            st.markdown(
                f"- Avg 7D return: **{format_pct(summary['avg_return_7d'])}** "
                f"(positive ratio: {summary['pos_ratio_7d']:.0%})"
            )

            st.markdown("---")
            st.markdown("#### 🧬 Pattern Analysis")

            # Analyze pattern with LLM (or fallback to rule-based)
            try:
                pattern = analyze_pattern_with_llm(symbol_cases, force_llm=False)
            except Exception as e:
                st.warning(f"⚠️ Pattern analysis error: {repr(e)[:80]}")
                pattern = {
                    "pattern_name": "unknown",
                    "avg_return_3d": summary.get("avg_return_3d", 0),
                    "confidence": 0.5,
                    "confidence_level": "low",
                    "typical_horizon": "3d",
                    "analysis_method": "rule_based",
                    "note": "Fallback due to error",
                }

            st.markdown(f"**Pattern name:** {pattern.get('pattern_name', 'N/A')}")
            st.markdown(
                f"**Avg return (3D):** {format_pct(pattern.get('avg_return_3d', 0))} · "
                f"**Confidence:** {pattern.get('confidence_level', pattern.get('confidence', 'low'))}"
            )
            st.markdown(f"**Typical horizon:** {pattern.get('typical_horizon', 'n/a')}")

            # Show note/status
            note = pattern.get('note')
            if note:
                if "not enabled" in note.lower():
                    st.info(f"ℹ️ {note}")
                elif "error" in note.lower() or "fallback" in note.lower():
                    st.warning(f"⚠️ {note}")
                else:
                    st.success(f"✅ {note}")

            analysis_method = pattern.get('analysis_method')
            if analysis_method:
                st.caption(f"Analysis method: `{analysis_method}`")

        # ========== AI PM Decision & Routed Orders ==========
        st.markdown("---")
        st.subheader("🤖 AI PM Decision & Routed Orders")

        # Build market state
        market_state = build_demo_market_state(selected_case, pattern)

        # Reset AI PM state for clean decision
        reset_state()

        # Get AI PM decision
        try:
            decision = decide_strategy(market_state)
        except Exception as e:
            st.error(f"❌ AI PM decision error: {repr(e)[:80]}")
            return

        # Get router orders
        try:
            router = StrategyRouter(verbose=False)
            orders = router.on_tick(market_state)
        except Exception as e:
            st.error(f"❌ Router error: {repr(e)[:80]}")
            return

        # === Kelly-based sizing for UI demo only ===
        BASE_CAPITAL = 10_000.0  # Demo account with $10k
        MIN_FRACTION = 0.02  # Minimum edge threshold (2%)

        # Determine win/loss ratio based on strategy
        win_loss_ratio = 2.0 if decision["chosen_strategy"] == "sniper" else 1.2

        # Calculate Kelly position with all details
        kelly = calculate_kelly_position(
            total_capital=BASE_CAPITAL,
            ai_confidence=decision.get("confidence", 0.5),
            win_loss_ratio=win_loss_ratio,
        )

        # Check if edge is strong enough to trade
        kelly_rejects_trade = kelly["fraction_applied"] < MIN_FRACTION

        if kelly_rejects_trade:
            # Edge too weak - suggest no trade
            st.warning(
                f"⚠️ Kelly-adjusted fraction is very small ({kelly['fraction_applied']:.3f}). "
                "Suggested action: **no trade** (edge not strong enough)."
            )
            orders = []
        else:
            # Apply Kelly sizing to orders (UI only, doesn't affect router logic)
            for order in orders:
                price = float(order.price)
                if price > 0:
                    kelly_size = kelly["notional"] / price
                    order.size = round(kelly_size, 2)

        col_decision, col_orders = st.columns([1.0, 1.2])

        # Left: AI PM Decision
        with col_decision:
            st.markdown("##### 🎯 AI PM Decision")
            st.markdown(f"**Chosen strategy:** `{decision['chosen_strategy']}`")
            st.markdown(f"**Risk mode:** `{decision['risk_mode']}`")
            st.markdown(f"**Confidence:** {decision['confidence']:.2f}")

            st.markdown("**Reasoning**")
            # Use a styled code block for better readability
            st.markdown(
                f"""<div style='background-color:#1e1e1e;
                              padding:0.75rem;
                              border-radius:0.5rem;
                              font-size:0.9rem;
                              font-family:monospace;'>
                    {decision['reason']}
                </div>""",
                unsafe_allow_html=True,
            )

            # Kelly-style Position Sizing (Demo Display Only)
            st.markdown("##### 📐 Position Sizing (Kelly-style, demo)")

            st.markdown(f"- Base capital: **${BASE_CAPITAL:,.2f}**")
            st.markdown(
                f"- Raw Kelly fraction: **{kelly['fraction_raw']:.3f}**  "
                f"(full Kelly, theoretical)"
            )
            st.markdown(
                f"- Half Kelly: **{kelly['fraction_half']:.3f}**  "
                f"(more realistic)"
            )
            st.markdown(
                f"- Applied fraction: **{kelly['fraction_applied']:.3f}**  "
                f"(capped at 20%)"
            )
            st.markdown(
                f"- Suggested notional: **${kelly['notional']:,.2f}**"
            )

            if kelly_rejects_trade:
                st.caption(
                    f"Note: Kelly suggests that the edge is too weak (<{MIN_FRACTION:.0%} of capital). "
                    "In this demo, the PM chooses to stay out and not place any orders."
                )
            else:
                st.caption(
                    "Note: In this web demo, order sizes shown on the right use this Kelly-adjusted notional "
                    "(half Kelly, capped at 20% of capital)."
                )

        # Right: Routed Orders
        with col_orders:
            st.markdown("##### 📦 Routed Orders")
            if not orders:
                if kelly_rejects_trade:
                    st.info("ℹ️ No orders – Kelly suggests standing aside for this setup (edge too weak).")
                else:
                    st.info("ℹ️ No orders generated for this scenario.")
            else:
                for i, order in enumerate(orders, start=1):
                    # Extract order details
                    side = order.side
                    size = order.size
                    price = order.price

                    # Extract metadata
                    strategy_name = decision["chosen_strategy"]
                    risk = decision["risk_mode"]
                    if hasattr(order, 'meta') and order.meta:
                        strategy_name = order.meta.get("routing_mode", strategy_name)
                        risk = order.meta.get("ai_risk_mode", risk)

                    st.markdown(
                        f"**Order {i}**  \n"
                        f"- Side: `{side}`  \n"
                        f"- Size: `{size:.2f}`  \n"
                        f"- Price: `{price:.2f}`  \n"
                        f"- Strategy: `{strategy_name}`  \n"
                        f"- Risk: `{risk}`"
                    )
                    if i < len(orders):
                        st.markdown("---")

        # Summary explanation
        st.markdown("---")
        st.markdown("### 💡 Summary")

        strategy_name = decision.get("chosen_strategy", "unknown")
        risk_mode = decision.get("risk_mode", "normal")
        avg_3d = pattern.get("avg_return_3d", 0) or 0

        if avg_3d > 0.10:
            pattern_desc = "strong positive 3D returns"
        elif avg_3d < -0.05:
            pattern_desc = "negative 3D returns"
        else:
            pattern_desc = "mixed or neutral 3D returns"

        analysis_status = (
            "attempted to use LLM for enhanced analysis but fell back to rule-based mode"
            if "fallback" in pattern.get("note", "").lower() or "error" in pattern.get("note", "").lower()
            else "used LLM for pattern analysis"
            if pattern.get("analysis_method") == "llm"
            else "used rule-based analysis"
        )

        st.info(
            f"In this scenario, the AI PM chose **{strategy_name.upper()}** with "
            f"**{risk_mode.upper()}** risk mode because the historical pattern shows "
            f"**{pattern_desc}** ({format_pct(avg_3d)} average). "
            f"The system {analysis_status}."
        )

    # ========== TAB 2: Custom News Lab ==========
    with tab_custom:
        st.subheader("🧪 Custom News Lab")
        st.markdown(
            "Type a hypothetical headline and let the AI PM react based on historical patterns "
            "for the selected symbol."
        )
        st.markdown("---")

        col_inputs, col_stats = st.columns([1.2, 1.0])

        # Left: Inputs
        with col_inputs:
            # Symbol selection
            default_idx = symbols.index("BLUE") if "BLUE" in symbols else 0
            custom_symbol = st.selectbox("Symbol", symbols, index=default_idx, key="custom_symbol")

            # Event type selection
            event_type = st.selectbox(
                "Event type / pattern",
                [
                    "Auto detect from symbol history",
                    "Positive macro / ETF news",
                    "Negative regulation / FUD",
                    "Company earnings beat",
                    "Security incident / exploit",
                ],
                index=0,
            )

            # Custom headline and summary
            custom_headline = st.text_input("Custom headline", "")
            custom_summary = st.text_area("Custom summary (optional)", "")

        # Filter cases by symbol
        custom_symbol_cases = filter_cases(cases, symbol=custom_symbol)

        # Optionally filter by event type
        filtered_cases = custom_symbol_cases
        if event_type != "Auto detect from symbol history" and custom_symbol_cases:
            # Simple tag-based filtering
            if "Positive" in event_type:
                tag_filtered = [c for c in custom_symbol_cases if "利好" in c.source_tag or "positive" in c.source_tag.lower()]
                if tag_filtered:
                    filtered_cases = tag_filtered
            elif "Negative" in event_type or "FUD" in event_type:
                tag_filtered = [c for c in custom_symbol_cases if "利空" in c.source_tag or "negative" in c.source_tag.lower() or "fud" in c.source_tag.lower()]
                if tag_filtered:
                    filtered_cases = tag_filtered

        # Right: Stats and Pattern
        with col_stats:
            st.markdown("#### 📊 Historical Pattern for This Symbol")

            if not filtered_cases:
                st.warning(f"No historical cases found for {custom_symbol}")
            else:
                summary = summarize_cases(filtered_cases)

                st.markdown(f"- Sample count: **{summary['count']}**")
                st.markdown(
                    f"- Avg 3D return: **{format_pct(summary['avg_return_3d'])}** "
                    f"(positive ratio: {summary['pos_ratio_3d']:.0%})"
                )
                st.markdown(
                    f"- Avg 7D return: **{format_pct(summary['avg_return_7d'])}** "
                    f"(positive ratio: {summary['pos_ratio_7d']:.0%})"
                )

                st.markdown("---")

                # Add Gemini button for deeper analysis
                ask_gemini = st.button("🔍 Ask Gemini for deeper analysis", key="custom_ask_gemini")

                # Analyze pattern
                try:
                    custom_pattern = analyze_pattern_with_llm(filtered_cases, force_llm=ask_gemini)
                except Exception as e:
                    st.caption(f"⚠️ Pattern analysis error: {repr(e)[:60]}")
                    custom_pattern = {
                        "pattern_name": "unknown",
                        "avg_return_3d": summary.get("avg_return_3d", 0),
                        "confidence": 0.5,
                        "confidence_level": "low",
                        "typical_horizon": "3d",
                        "analysis_method": "rule_based",
                        "note": "Fallback due to error",
                    }

                st.markdown(f"**Pattern:** {custom_pattern.get('pattern_name', 'N/A')}")
                st.markdown(
                    f"**Avg return (3D):** {format_pct(custom_pattern.get('avg_return_3d', 0))} · "
                    f"**Confidence:** {custom_pattern.get('confidence_level', 'low')}"
                )

                # Show analysis method and note
                analysis_method = custom_pattern.get('analysis_method', 'unknown')
                note = custom_pattern.get('note')

                if analysis_method == "llm":
                    st.success(f"✅ {note}")
                elif analysis_method == "rule_based_fallback":
                    st.warning(f"⚠️ {note}")
                elif note:
                    st.info(f"ℹ️ {note}")

                st.caption(f"Analysis method: `{analysis_method}`")

        # Show AI PM decision only if headline is provided
        if not custom_headline.strip():
            st.markdown("---")
            st.info("💡 Enter a headline above to see how the AI PM would react.")
        else:
            if not filtered_cases:
                st.error("Cannot generate decision without historical data for this symbol.")
            else:
                st.markdown("---")
                st.subheader("🤖 AI PM Decision for This Custom Event")

                # Build custom market state
                reference_case = filtered_cases[-1]
                custom_market_state = build_custom_market_state(
                    custom_symbol,
                    custom_pattern,
                    custom_headline,
                    custom_summary,
                    reference_case,
                )

                # Reset AI PM state
                reset_state()

                # Get AI PM decision
                try:
                    custom_decision = decide_strategy(custom_market_state)
                except Exception as e:
                    st.error(f"❌ AI PM decision error: {repr(e)[:80]}")
                    return

                # Get router orders
                try:
                    custom_router = StrategyRouter(verbose=False)
                    custom_orders = custom_router.on_tick(custom_market_state)
                except Exception as e:
                    st.error(f"❌ Router error: {repr(e)[:80]}")
                    return

                # Kelly sizing
                BASE_CAPITAL = 10_000.0
                MIN_FRACTION = 0.02

                win_loss_ratio = 2.0 if custom_decision["chosen_strategy"] == "sniper" else 1.2

                custom_kelly = calculate_kelly_position(
                    total_capital=BASE_CAPITAL,
                    ai_confidence=custom_decision.get("confidence", 0.5),
                    win_loss_ratio=win_loss_ratio,
                )

                kelly_rejects_trade = custom_kelly["fraction_applied"] < MIN_FRACTION

                if kelly_rejects_trade:
                    st.warning(
                        f"⚠️ Kelly-adjusted fraction is very small ({custom_kelly['fraction_applied']:.3f}). "
                        "Suggested action: **no trade** (edge not strong enough)."
                    )
                    custom_orders = []
                else:
                    for order in custom_orders:
                        price = float(order.price)
                        if price > 0:
                            kelly_size = custom_kelly["notional"] / price
                            order.size = round(kelly_size, 2)

                col_decision, col_orders = st.columns([1.0, 1.2])

                # Left: Decision
                with col_decision:
                    st.markdown("##### 🎯 AI PM Decision")
                    st.markdown(f"**Chosen strategy:** `{custom_decision['chosen_strategy']}`")
                    st.markdown(f"**Risk mode:** `{custom_decision['risk_mode']}`")
                    st.markdown(f"**Confidence:** {custom_decision['confidence']:.2f}")

                    st.markdown("**Reasoning**")
                    st.markdown(
                        f"""<div style='background-color:#1e1e1e;
                                      padding:0.75rem;
                                      border-radius:0.5rem;
                                      font-size:0.9rem;
                                      font-family:monospace;'>
                            {custom_decision['reason']}
                        </div>""",
                        unsafe_allow_html=True,
                    )

                    # Kelly sizing
                    st.markdown("##### 📐 Position Sizing (Kelly-style, demo)")
                    st.markdown(f"- Base capital: **${BASE_CAPITAL:,.2f}**")
                    st.markdown(f"- Applied fraction: **{custom_kelly['fraction_applied']:.3f}**")
                    st.markdown(f"- Suggested notional: **${custom_kelly['notional']:,.2f}**")

                    if kelly_rejects_trade:
                        st.caption(
                            f"Note: Kelly suggests edge is too weak (<{MIN_FRACTION:.0%}). No trade recommended."
                        )

                # Right: Orders
                with col_orders:
                    st.markdown("##### 📦 Routed Orders")
                    if not custom_orders:
                        if kelly_rejects_trade:
                            st.info("ℹ️ No orders – Kelly suggests standing aside (edge too weak).")
                        else:
                            st.info("ℹ️ No orders generated for this scenario.")
                    else:
                        for i, order in enumerate(custom_orders, start=1):
                            side = order.side
                            size = order.size
                            price = order.price

                            strategy_name = custom_decision["chosen_strategy"]
                            risk = custom_decision["risk_mode"]
                            if hasattr(order, 'meta') and order.meta:
                                strategy_name = order.meta.get("routing_mode", strategy_name)
                                risk = order.meta.get("ai_risk_mode", risk)

                            st.markdown(
                                f"**Order {i}**  \n"
                                f"- Side: `{side}`  \n"
                                f"- Size: `{size:.2f}`  \n"
                                f"- Price: `{price:.2f}`  \n"
                                f"- Strategy: `{strategy_name}`  \n"
                                f"- Risk: `{risk}`"
                            )
                            if i < len(custom_orders):
                                st.markdown("---")


if __name__ == "__main__":
    main()
