# news_replay.py
"""
News Replay Utility Module

Loads news cases from CSV, filters them, computes statistics,
and prints readable reports. Used by AI PM and demo scripts.

Usage:
    python3 news_replay.py
    python3 -m news_replay
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Try to import the new Gemini SDK (optional dependency)
try:
    import google.genai as genai
except ImportError:
    genai = None


# =============================================================================
# Data Model
# =============================================================================

@dataclass
class NewsCase:
    """A single news event with associated price reaction data."""
    case_id: str
    symbol: str
    event_date: str
    news_headline: str
    news_summary: str
    return_1d: float
    return_3d: float
    return_7d: float
    regime: str        # e.g. "trending", "ranging", "mixed"
    source_tag: str


# =============================================================================
# Configuration
# =============================================================================

# Environment variables for LLM control
_USE_LLM_DEFAULT = os.getenv("AI_PM_USE_LLM", "0") == "1"
_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini model name (can be overridden via env var)
# Default: gemini-2.0-flash-exp (latest fast model as of Jan 2025)
# Alternatives: gemini-1.5-flash, gemini-1.5-pro
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")


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

    if not _GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    return genai.Client(api_key=_GEMINI_API_KEY)


# =============================================================================
# Data Loading
# =============================================================================

def load_news_cases(csv_path: str | Path = "data/news_cases.csv") -> List[NewsCase]:
    """
    Load news cases from a CSV file.

    Args:
        csv_path: Path to the CSV file (default: data/news_cases.csv)

    Returns:
        List of NewsCase objects
    """
    cases: List[NewsCase] = []
    path = Path(csv_path)

    if not path.exists():
        print(f"[warn] CSV file not found: {path}")
        return cases

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)

        # Skip header row
        header = next(reader, None)
        if header is None:
            print(f"[warn] Empty CSV file: {path}")
            return cases

        expected_cols = 10  # case_id, symbol, event_date, ..., source_tag

        for row_num, row in enumerate(reader, start=2):
            # Skip empty rows
            if not row or all(cell.strip() == "" for cell in row):
                continue

            # Check column count
            if len(row) != expected_cols:
                print(f"[warn] skip malformed row {row_num}: expected {expected_cols} cols, got {len(row)}")
                continue

            try:
                case = NewsCase(
                    case_id=row[0].strip(),
                    symbol=row[1].strip(),
                    event_date=row[2].strip(),
                    news_headline=row[3].strip(),
                    news_summary=row[4].strip(),
                    return_1d=float(row[5].strip()),
                    return_3d=float(row[6].strip()),
                    return_7d=float(row[7].strip()),
                    regime=row[8].strip(),
                    source_tag=row[9].strip(),
                )
                cases.append(case)
            except ValueError as e:
                print(f"[warn] skip row {row_num} due to parse error: {e}")
                continue

    return cases


# =============================================================================
# Filtering
# =============================================================================

def filter_cases(
    cases: List[NewsCase],
    symbol: Optional[str] = None,
    source_tag: Optional[str] = None,
    regime: Optional[str] = None,
) -> List[NewsCase]:
    """
    Filter news cases by symbol, source_tag substring, or regime.

    Args:
        cases: List of NewsCase to filter
        symbol: If provided, keep only cases with matching symbol (exact match)
        source_tag: If provided, keep only cases whose source_tag contains this substring
        regime: If provided, keep only cases with matching regime (exact match)

    Returns:
        Filtered list of NewsCase
    """
    result = cases

    if symbol is not None:
        result = [c for c in result if c.symbol == symbol]

    if source_tag is not None:
        result = [c for c in result if source_tag in c.source_tag]

    if regime is not None:
        result = [c for c in result if c.regime == regime]

    return result


# =============================================================================
# Statistics
# =============================================================================

def summarize_cases(cases: List[NewsCase]) -> Dict[str, float]:
    """
    Compute summary statistics for a list of news cases.

    Returns:
        Dict with keys:
        - count: number of cases
        - avg_return_1d, avg_return_3d, avg_return_7d: arithmetic mean
        - pos_ratio_1d, pos_ratio_3d, pos_ratio_7d: fraction with return > 0
    """
    n = len(cases)

    if n == 0:
        return {
            "count": 0,
            "avg_return_1d": 0.0,
            "avg_return_3d": 0.0,
            "avg_return_7d": 0.0,
            "pos_ratio_1d": 0.0,
            "pos_ratio_3d": 0.0,
            "pos_ratio_7d": 0.0,
        }

    sum_1d = sum(c.return_1d for c in cases)
    sum_3d = sum(c.return_3d for c in cases)
    sum_7d = sum(c.return_7d for c in cases)

    pos_1d = sum(1 for c in cases if c.return_1d > 0)
    pos_3d = sum(1 for c in cases if c.return_3d > 0)
    pos_7d = sum(1 for c in cases if c.return_7d > 0)

    return {
        "count": n,
        "avg_return_1d": sum_1d / n,
        "avg_return_3d": sum_3d / n,
        "avg_return_7d": sum_7d / n,
        "pos_ratio_1d": pos_1d / n,
        "pos_ratio_3d": pos_3d / n,
        "pos_ratio_7d": pos_7d / n,
    }


# =============================================================================
# Pretty Print
# =============================================================================

def _format_pct(value: float) -> str:
    """Format a decimal return as a percentage string with sign."""
    pct = value * 100
    if pct >= 0:
        return f"+{pct:.1f}%"
    else:
        return f"{pct:.1f}%"


def print_pretty_report(
    title: str,
    cases: List[NewsCase],
    summary: Dict[str, float],
) -> None:
    """
    Print a formatted report of news cases and summary statistics.

    Args:
        title: Report title (e.g., symbol name)
        cases: List of NewsCase to display
        summary: Summary statistics from summarize_cases()
    """
    count = int(summary.get("count", len(cases)))

    # Header
    print()
    print(f"{'=' * 60}")
    print(f"  News Replay: {title} (样本 {count} 条)")
    print(f"{'=' * 60}")
    print()

    if count == 0:
        print("  (无匹配数据)")
        print()
        return

    # Sort cases by date ascending
    sorted_cases = sorted(cases, key=lambda c: c.event_date)

    # List each case
    for i, case in enumerate(sorted_cases, start=1):
        print(f"{i}) {case.event_date}  {case.news_headline}")
        print(f"   Regime: {case.regime}  | Tag: {case.source_tag}")
        print(f"   1D: {_format_pct(case.return_1d)}, "
              f"3D: {_format_pct(case.return_3d)}, "
              f"7D: {_format_pct(case.return_7d)}")
        # Truncate summary if too long
        summary_text = case.news_summary
        if len(summary_text) > 80:
            summary_text = summary_text[:77] + "..."
        print(f"   摘要: {summary_text}")
        print()

    # Summary block
    print("-" * 60)
    print("整体统计：")
    print(f"  - 1日平均涨幅: {_format_pct(summary['avg_return_1d'])} "
          f"(上涨占比 {summary['pos_ratio_1d'] * 100:.0f}%)")
    print(f"  - 3日平均涨幅: {_format_pct(summary['avg_return_3d'])} "
          f"(上涨占比 {summary['pos_ratio_3d'] * 100:.0f}%)")
    print(f"  - 7日平均涨幅: {_format_pct(summary['avg_return_7d'])} "
          f"(上涨占比 {summary['pos_ratio_7d'] * 100:.0f}%)")
    print()


# =============================================================================
# Pattern Analysis (Rule-Based + Optional LLM)
# =============================================================================

def _analyze_pattern_rule_based(cases: List[NewsCase]) -> dict:
    """
    Analyze historical news pattern using rule-based logic.

    Args:
        cases: List of NewsCase to analyze

    Returns:
        Dict with pattern analysis
    """
    summary = summarize_cases(cases)
    count = int(summary.get("count", 0))

    if count == 0:
        return {
            "pattern_name": "no_data",
            "avg_return_1d": None,
            "avg_return_3d": None,
            "avg_return_7d": None,
            "confidence": 0.0,
            "confidence_level": "low",
            "typical_horizon": "3d",
            "analysis_method": "rule_based",
            "comment": "无历史数据",
            "raw_llm_text": None,
            "error": None,
        }

    # Compute confidence based on sample size and consistency
    pos_ratio_3d = summary.get("pos_ratio_3d", 0.5)
    consistency = abs(pos_ratio_3d - 0.5) * 2  # 0 = 50/50, 1 = all same direction

    if count >= 10:
        confidence = 0.8
        confidence_level = "high"
    elif count >= 3:
        confidence = 0.6
        confidence_level = "medium"
    else:
        confidence = 0.4
        confidence_level = "low"

    # Adjust confidence based on consistency
    confidence = min(confidence + consistency * 0.15, 0.95)

    # Determine typical horizon
    avg_1d = abs(summary["avg_return_1d"])
    avg_3d = abs(summary["avg_return_3d"])
    avg_7d = abs(summary["avg_return_7d"])

    if avg_7d >= avg_3d and avg_7d >= avg_1d:
        typical_horizon = "7d"
    elif avg_3d >= avg_1d:
        typical_horizon = "3d"
    else:
        typical_horizon = "1d"

    # Infer pattern name
    if cases:
        first_tag = cases[0].source_tag
        parts = first_tag.split("_")
        if len(parts) >= 2:
            pattern_name = "_".join(parts[1:])
        else:
            pattern_name = first_tag
    else:
        pattern_name = "generic_pattern"

    # Build comment
    avg_3d_pct = summary["avg_return_3d"] * 100
    direction = "上涨" if avg_3d_pct > 0 else "下跌"
    comment = f"样本 {count} 条，平均 3 日{direction} {abs(avg_3d_pct):.1f}%，置信度{confidence_level}"

    return {
        "pattern_name": pattern_name,
        "avg_return_1d": summary["avg_return_1d"],
        "avg_return_3d": summary["avg_return_3d"],
        "avg_return_7d": summary["avg_return_7d"],
        "confidence": confidence,
        "confidence_level": confidence_level,
        "typical_horizon": typical_horizon,
        "analysis_method": "rule_based",
        "comment": comment,
        "raw_llm_text": None,
        "error": None,
    }


def analyze_pattern_with_llm(
    cases: List[NewsCase],
    use_llm: bool | None = None,
    max_cases: int = 5,
) -> dict:
    """
    Analyze historical news pattern, optionally using LLM.

    This function:
    - Tries to use Gemini LLM if use_llm=True and GEMINI_API_KEY is set
    - Falls back to rule-based analysis on any error
    - Never blocks or hangs - fails fast

    Args:
        cases: List of NewsCase to analyze
        use_llm: Override for LLM usage
                 - None: Use AI_PM_USE_LLM env var (default)
                 - True: Try LLM with fallback
                 - False: Use rule-based only
        max_cases: Maximum number of cases to send to LLM (default: 5)

    Returns:
        Dict with pattern analysis:
        {
            "pattern_name": str,
            "avg_return_1d": float | None,
            "avg_return_3d": float | None,
            "avg_return_7d": float | None,
            "confidence": float,
            "confidence_level": str,
            "typical_horizon": str,
            "analysis_method": str,
            "comment": str,
            "raw_llm_text": Optional[str],
            "error": Optional[str],
        }
    """
    # 0) If no cases, return empty pattern
    if not cases:
        return _analyze_pattern_rule_based(cases)

    # 1) Limit sample size to avoid token limits
    sample_cases = cases[:max_cases]

    # 2) Get rule-based result as baseline/fallback
    rb = _analyze_pattern_rule_based(sample_cases)

    # 3) Determine whether to use LLM
    if use_llm is None:
        use_llm = _USE_LLM_DEFAULT

    # 4) Check if LLM is enabled
    if not use_llm:
        rb["error"] = "LLM not enabled (set AI_PM_USE_LLM=1)"
        return rb

    # 5) Try LLM path
    try:
        client = get_gemini_client()

        # Build payload - limit to max_cases to avoid token limits
        payload = [
            {
                "symbol": c.symbol,
                "event_date": c.event_date,
                "summary": c.news_summary,
                "regime": c.regime,
                "return_1d": round(c.return_1d, 4),
                "return_3d": round(c.return_3d, 4),
                "return_7d": round(c.return_7d, 4),
            }
            for c in sample_cases
        ]

        # Build prompt
        prompt = f"""你是一个事件驱动交易员。
下面是同一类新闻的若干历史样本，请你总结这种新闻大致的价格反应模式。

每个样本包含：
* 新闻摘要 summary
* 1日/3日/7日收益 return_1d/return_3d/return_7d
* 可选的 regime（trending/ranging 等）

请你输出一个 JSON，字段为：
* pattern_name: 概括这种新闻类型的名字（用简短中文，例如 "广告_利好"）
* avg_return_1d: 过去样本的 1 日平均收益（小数，例如 0.12 表示 +12%）
* avg_return_3d: 3 日平均收益
* avg_return_7d: 7 日平均收益
* confidence_level: "high" / "medium" / "low"
* typical_horizon: "1d" / "3d" / "7d" 中选一个你认为反应最强的周期
* comment: 用一两句中文解释这个模式的含义

只输出严格的 JSON，不要解释文字。

历史样本 JSON 列表如下：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""

        # Call Gemini API with new SDK
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
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

        # Build result from LLM data with fallback to rule-based
        pattern = {
            "pattern_name": data.get("pattern_name") or rb.get("pattern_name") or "未知模式",
            "avg_return_1d": data.get("avg_return_1d", rb.get("avg_return_1d")),
            "avg_return_3d": data.get("avg_return_3d", rb.get("avg_return_3d")),
            "avg_return_7d": data.get("avg_return_7d", rb.get("avg_return_7d")),
            "confidence": rb.get("confidence", 0.5),  # Keep rule-based confidence
            "confidence_level": data.get("confidence_level", "low"),
            "typical_horizon": data.get("typical_horizon", rb.get("typical_horizon", "3d")),
            "analysis_method": "llm",
            "comment": data.get("comment", rb.get("comment", "")),
            "raw_llm_text": text,
            "error": None,
            "llm_model": _GEMINI_MODEL,  # Track which model was used
        }

        # Validate confidence_level
        if pattern["confidence_level"] not in {"low", "medium", "high"}:
            pattern["confidence_level"] = "low"

        # Validate typical_horizon
        if pattern["typical_horizon"] not in {"1d", "3d", "7d"}:
            pattern["typical_horizon"] = "3d"

        return pattern

    except Exception as e:
        # Fast fallback on any error - keep error message concise
        error_type = type(e).__name__
        error_msg = str(e)[:100]  # Truncate long messages
        rb["analysis_method"] = "rule_based"
        rb["error"] = f"{error_type}: {error_msg}"
        return rb


# =============================================================================
# CLI Entrypoint
# =============================================================================

def main() -> None:
    """Demo entrypoint: load cases and print report for a sample symbol."""
    cases = load_news_cases()

    if not cases:
        print("No news cases loaded. Check data/news_cases.csv")
        return

    # Demo 1: Filter by symbol
    symbol = "BLUE"
    filtered = filter_cases(cases, symbol=symbol)
    summary = summarize_cases(filtered)
    print_pretty_report(symbol, filtered, summary)

    # Demo 2: Filter by source_tag substring (Crypto)
    tag = "Crypto"
    filtered = filter_cases(cases, source_tag=tag)
    summary = summarize_cases(filtered)
    print_pretty_report(f"Tag: {tag}", filtered, summary)

    # Demo 3: Filter by regime
    regime = "trending"
    filtered = filter_cases(cases, regime=regime)
    summary = summarize_cases(filtered)
    print_pretty_report(f"Regime: {regime}", filtered, summary)


if __name__ == "__main__":
    main()
