# tests/conftest.py
"""
Pytest configuration file.

Adds the project root to sys.path so that imports like
`from strategies.ou_arb import OUArbStrategy` work when running pytest.
"""

import sys
from pathlib import Path

# Project root is the parent of the tests/ directory
ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)

if root_str not in sys.path:
    sys.path.insert(0, root_str)
