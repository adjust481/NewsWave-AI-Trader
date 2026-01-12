#!/usr/bin/env python3
"""
Quick Demo Runner - Test Gemini LLM Integration

This script provides an interactive way to test the Gemini LLM integration
with different configurations.

Usage:
    python3 demo_runner.py [mode]

Modes:
    rule    - Rule-based mode (no LLM)
    llm     - LLM mode (requires API key)
    test    - Run all tests
    verify  - Verify integration
"""

import os
import sys
import subprocess
from pathlib import Path

def print_banner(text):
    """Print a banner"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")

def print_config():
    """Print current configuration"""
    print("Current Configuration:")
    print(f"  AI_PM_USE_LLM: {os.getenv('AI_PM_USE_LLM', '0')}")
    print(f"  GEMINI_API_KEY: {'Set' if os.getenv('GEMINI_API_KEY') else 'Not set'}")
    print(f"  GEMINI_MODEL: {os.getenv('GEMINI_MODEL', 'gemini-2.0-flash-exp (default)')}")
    print()

def run_rule_based():
    """Run demo in rule-based mode"""
    print_banner("Running Demo - Rule-Based Mode")

    # Clear LLM settings
    env = os.environ.copy()
    env.pop('AI_PM_USE_LLM', None)
    env.pop('GEMINI_API_KEY', None)

    print("Configuration: LLM disabled")
    print()

    subprocess.run(['python3', 'demo_news_driven.py'], env=env)

def run_llm():
    """Run demo in LLM mode"""
    print_banner("Running Demo - LLM Mode")

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("⚠️  GEMINI_API_KEY not set!")
        print("\nTo enable LLM mode:")
        print("  export GEMINI_API_KEY='your_api_key'")
        print("  python3 demo_runner.py llm")
        print("\nOr use your configured function:")
        print("  ai_router_llm")
        print("  python3 demo_runner.py llm")
        return

    env = os.environ.copy()
    env['AI_PM_USE_LLM'] = '1'

    print(f"Configuration: LLM enabled")
    print(f"  API Key: {api_key[:20]}...")
    print(f"  Model: {env.get('GEMINI_MODEL', 'gemini-2.0-flash-exp (default)')}")
    print()

    subprocess.run(['python3', 'demo_news_driven.py'], env=env)

def run_tests():
    """Run pytest suite"""
    print_banner("Running Test Suite")
    subprocess.run(['python3', '-m', 'pytest', '-xvs'])

def run_verify():
    """Run verification script"""
    print_banner("Running Integration Verification")
    subprocess.run(['python3', 'verify_integration.py'])

def show_help():
    """Show help message"""
    print_banner("Gemini LLM Integration - Demo Runner")

    print("Usage:")
    print("  python3 demo_runner.py [mode]")
    print()
    print("Modes:")
    print("  rule    - Run demo in rule-based mode (no LLM)")
    print("  llm     - Run demo in LLM mode (requires API key)")
    print("  test    - Run pytest suite")
    print("  verify  - Run integration verification")
    print("  help    - Show this help message")
    print()
    print("Examples:")
    print("  # Rule-based mode")
    print("  python3 demo_runner.py rule")
    print()
    print("  # LLM mode (set API key first)")
    print("  export GEMINI_API_KEY='your_key'")
    print("  python3 demo_runner.py llm")
    print()
    print("  # Custom model")
    print("  export GEMINI_MODEL='gemini-1.5-flash'")
    print("  python3 demo_runner.py llm")
    print()
    print("  # Run tests")
    print("  python3 demo_runner.py test")
    print()
    print("Quick Commands:")
    print("  ai_router_off  # Disable LLM and cd to project")
    print("  ai_router_llm  # Enable LLM and cd to project")
    print()

def main():
    """Main entry point"""
    # Check if we're in the right directory
    if not Path('demo_news_driven.py').exists():
        print("Error: demo_news_driven.py not found")
        print("Please run this script from the project root directory:")
        print("  cd ~/Desktop/ai_quant_router")
        print("  python3 demo_runner.py")
        return 1

    # Get mode from command line
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else 'help'

    if mode == 'rule':
        run_rule_based()
    elif mode == 'llm':
        run_llm()
    elif mode == 'test':
        run_tests()
    elif mode == 'verify':
        run_verify()
    elif mode == 'help':
        show_help()
    else:
        print(f"Unknown mode: {mode}")
        print("Run 'python3 demo_runner.py help' for usage information")
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())
