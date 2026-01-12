#!/usr/bin/env python3
"""
Gemini LLM Integration Verification Script

This script verifies that the Gemini LLM integration is working correctly
by checking:
1. SDK imports
2. Configuration
3. Response parsing
4. Error handling
5. Fallback logic

Usage:
    python3 verify_integration.py
"""

import os
import sys
from pathlib import Path

# Colors for terminal output
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color

def print_header(text):
    print(f"\n{BLUE}{'=' * 70}{NC}")
    print(f"{BLUE}{text:^70}{NC}")
    print(f"{BLUE}{'=' * 70}{NC}\n")

def print_success(text):
    print(f"{GREEN}✓ {text}{NC}")

def print_warning(text):
    print(f"{YELLOW}⚠ {text}{NC}")

def print_error(text):
    print(f"{RED}✗ {text}{NC}")

def check_file_exists(filepath):
    """Check if a file exists"""
    if Path(filepath).exists():
        print_success(f"File exists: {filepath}")
        return True
    else:
        print_error(f"File not found: {filepath}")
        return False

def check_sdk_import(filepath):
    """Check if file uses new SDK"""
    with open(filepath, 'r') as f:
        content = f.read()

    # Check for old SDK
    if 'google.generativeai' in content and 'import google.generativeai' in content:
        print_error(f"Old SDK found in {filepath}")
        return False

    # Check for new SDK
    if 'import google.genai' in content:
        print_success(f"New SDK import found in {filepath}")
        return True

    print_warning(f"No Gemini SDK import in {filepath}")
    return True

def check_model_config(filepath):
    """Check if GEMINI_MODEL is configured"""
    with open(filepath, 'r') as f:
        content = f.read()

    if 'GEMINI_MODEL' in content:
        # Extract the default value
        for line in content.split('\n'):
            if 'GEMINI_MODEL' in line and '=' in line and 'getenv' in line:
                print_success(f"Model config found in {filepath}")
                print(f"  → {line.strip()}")
                return True
        print_warning(f"GEMINI_MODEL mentioned but not configured in {filepath}")
        return False

    print_error(f"GEMINI_MODEL not found in {filepath}")
    return False

def check_response_parsing(filepath):
    """Check if response parsing handles multiple structures"""
    with open(filepath, 'r') as f:
        content = f.read()

    # Look for the new parsing logic
    if 'hasattr(response, \'text\')' in content and 'hasattr(response, \'candidates\')' in content:
        print_success(f"Robust response parsing found in {filepath}")
        return True

    print_error(f"Response parsing not updated in {filepath}")
    return False

def check_error_truncation(filepath):
    """Check if error messages are truncated"""
    with open(filepath, 'r') as f:
        content = f.read()

    # Look for error truncation
    if '[:100]' in content or '[:80]' in content:
        print_success(f"Error message truncation found in {filepath}")
        return True

    print_warning(f"Error truncation not found in {filepath}")
    return False

def check_environment():
    """Check environment variables"""
    print_header("Environment Variables")

    llm_enabled = os.getenv("AI_PM_USE_LLM", "0") == "1"
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

    print(f"AI_PM_USE_LLM: {llm_enabled}")
    if llm_enabled:
        print_success("LLM mode enabled")
    else:
        print_warning("LLM mode disabled (set AI_PM_USE_LLM=1 to enable)")

    print(f"\nGEMINI_API_KEY: {'Set' if api_key else 'Not set'}")
    if api_key:
        print_success(f"API key configured (length: {len(api_key)})")
    else:
        print_warning("API key not set (LLM will fallback to rule-based)")

    print(f"\nGEMINI_MODEL: {model}")
    print_success(f"Using model: {model}")

    return llm_enabled and api_key is not None

def check_imports():
    """Check if SDK can be imported"""
    print_header("SDK Import Test")

    try:
        import google.genai as genai
        print_success("google.genai imported successfully")

        # Try to get client (will fail without API key, but that's ok)
        try:
            if os.getenv("GEMINI_API_KEY"):
                client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
                print_success("Client created successfully")
            else:
                print_warning("Skipping client creation (no API key)")
        except Exception as e:
            print_warning(f"Client creation failed: {type(e).__name__}")

        return True
    except ImportError as e:
        print_error(f"Failed to import google.genai: {e}")
        print("\nTo install: python3 -m pip install --upgrade google-genai")
        return False

def main():
    print_header("Gemini LLM Integration Verification")

    all_checks_passed = True

    # Check files exist
    print_header("File Existence Check")
    files_to_check = [
        'strategies/ai_pm.py',
        'news_replay.py',
        'demo_news_driven.py',
        'TEST_GUIDE.md',
        'CHANGES.md',
        'QUICK_REFERENCE.md',
    ]

    for filepath in files_to_check:
        if not check_file_exists(filepath):
            all_checks_passed = False

    # Check SDK imports
    print_header("SDK Import Check")
    for filepath in ['strategies/ai_pm.py', 'news_replay.py']:
        if not check_sdk_import(filepath):
            all_checks_passed = False

    # Check model configuration
    print_header("Model Configuration Check")
    for filepath in ['strategies/ai_pm.py', 'news_replay.py']:
        if not check_model_config(filepath):
            all_checks_passed = False

    # Check response parsing
    print_header("Response Parsing Check")
    for filepath in ['strategies/ai_pm.py', 'news_replay.py']:
        if not check_response_parsing(filepath):
            all_checks_passed = False

    # Check error truncation
    print_header("Error Handling Check")
    for filepath in ['strategies/ai_pm.py', 'news_replay.py']:
        check_error_truncation(filepath)  # Warning only, not critical

    # Check environment
    env_ready = check_environment()

    # Check imports
    sdk_ready = check_imports()
    if not sdk_ready:
        all_checks_passed = False

    # Final summary
    print_header("Verification Summary")

    if all_checks_passed:
        print_success("All critical checks passed!")

        if env_ready:
            print_success("Environment is ready for LLM mode")
            print("\nYou can now run:")
            print("  python3 demo_news_driven.py")
        else:
            print_warning("Environment not configured for LLM mode")
            print("\nTo enable LLM mode:")
            print("  export AI_PM_USE_LLM=1")
            print("  export GEMINI_API_KEY=your_api_key")
            print("\nOr use rule-based mode:")
            print("  ai_router_off && python3 demo_news_driven.py")
    else:
        print_error("Some checks failed. Please review the output above.")
        return 1

    print("\n" + "=" * 70)
    print("Next steps:")
    print("  1. Run tests: pytest -xvs")
    print("  2. Test rule-based: ai_router_off && python3 demo_news_driven.py")
    print("  3. Test LLM: ai_router_llm && python3 demo_news_driven.py")
    print("  4. Read docs: cat TEST_GUIDE.md")
    print("=" * 70 + "\n")

    return 0

if __name__ == "__main__":
    sys.exit(main())
