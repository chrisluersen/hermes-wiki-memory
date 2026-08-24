"""Run the standalone plugin tests after installing collection-time stubs."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

# Pytest imports the repository-root plugin __init__.py while determining the
# package hierarchy. Load the standalone-test bootstrap before collection so
# the plugin's real Hermes imports remain strict in production.
runpy.run_path(str(ROOT / "conftest.py"))

requested = sys.argv[1:] or [str(ROOT / "tests"), "-q"]
raise SystemExit(pytest.main(["--rootdir", str(ROOT / "tests"), *requested]))
