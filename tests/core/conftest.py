"""Pytest configuration for core tests.

All tests in tests/core/ are v2 (CLI-first, headless) functionality.
"""

import pytest


def pytest_collection_modifyitems(items):
    """Automatically mark all tests in this directory as v2."""
    for item in items:
        # Check if the test is in the core directory
        if "/tests/core/" in str(item.fspath):
            item.add_marker(pytest.mark.v2)
