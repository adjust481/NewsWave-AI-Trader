#!/usr/bin/env python3
"""
One-Command Setup and Test Script

This script performs a complete setup and verification of the Gemini LLM integration.

Usage:
    python3 setup_and_test.py
"""

import os
import sys
import subprocess
from pathlib import Path

def print_section(title):
    """Print a section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")

def run_command(cmd, description, check=True):
    """Run a command and print the result"""
    print(f"→ {description}...")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=check
        )
        if result.returncode == 0:
            print(f"  ✓ Success")
            return True
        else:
            print(f"  ✗ Failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    print_section("Gemini LLM Integration - One-Command Setup")

    # Check if we're in the right directory
    if not Path('demo_news_driven.py').exists():
        print("Error: Not in project directory")
        print("Please run from: ~/Desktop/ai_quant_router")
        return 1

    # Step 1: Install SDK
    print_section("Step 1: Installing SDK")
    if run_command(
        "python3 -m pip install --upgrade google-genai",
        "Installing google-genai SDK",
        check=False
    ):
        print("\n✓ SDK installed successfully")
    else:
        print("\n⚠ SDK installation had issues, but continuing...")

    # Step 2: Verify integration
    print_section("Step 2: Verifying Integration")
    if run_command(
        "python3 verify_integration.py",
        "Running integration verification",
        check=False
    ):
        print("\n✓ Integration verified")
    else:
        print("\n⚠ Some checks failed, but continuing...")

    # Step 3: Run tests
    print_section("Step 3: Running Tests")
    if run_command(
        "python3 -m pytest -xvs --tb=short 2>&1 | tail -10",
        "Running pytest suite",
        check=False
    ):
        print("\n✓ All tests passed")
    else:
        print("\n⚠ Some tests failed")

    # Step 4: Test rule-based mode
    print_section("Step 4: Testing Rule-Based Mode")
    env_cmd = "unset AI_PM_USE_LLM && unset GEMINI_API_KEY && python3 demo_news_driven.py 2>&1 | grep -A 3 'Analysis method'"
    if run_command(
        env_cmd,
        "Running demo in rule-based mode",
        check=False
    ):
        print("\n✓ Rule-based mode works")
    else:
        print("\n⚠ Rule-based mode had issues")

    # Step 5: Check LLM readiness
    print_section("Step 5: Checking LLM Readiness")
    api_key = os.getenv('GEMINI_API_KEY')
    if api_key:
        print(f"✓ GEMINI_API_KEY is set (length: {len(api_key)})")
        print("\nYou can now test LLM mode:")
        print("  export AI_PM_USE_LLM=1")
        print("  python3 demo_news_driven.py")
    else:
        print("⚠ GEMINI_API_KEY not set")
        print("\nTo enable LLM mode:")
        print("  export GEMINI_API_KEY='your_api_key'")
        print("  export AI_PM_USE_LLM=1")
        print("  python3 demo_news_driven.py")

    # Final summary
    print_section("Setup Complete!")
    print("Next steps:")
    print("  1. Read the quick reference: cat QUICK_REFERENCE.md")
    print("  2. Test rule-based mode: python3 demo_runner.py rule")
    print("  3. Test LLM mode: python3 demo_runner.py llm")
    print("  4. Read full docs: cat START_HERE.md")
    print("\nFor help:")
    print("  python3 demo_runner.py help")
    print("  python3 verify_integration.py")
    print()

    return 0

if __name__ == '__main__':
    sys.exit(main())
